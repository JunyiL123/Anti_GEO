"""Entity-scoped L1 on Mode B referrers (triage → shortlist → tighten).

Triage priority = max(thread_surface, editability). Shortlist is two-tier:
elevated-priority referrers are always scored (capped); an adaptive sample of
the remainder fills tier-2. Only L1/L3 outcomes tighten actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from anti_geo.content_signals import detect_planted_mention, extract_content_signals
from anti_geo.independence import analyze_independence
from anti_geo.models import IndependenceReport, PageSegment
from anti_geo.platform_role import THREAD_PATH_RE
from anti_geo.segments import extract_page_segments

# Soft surfaces where page body itself is plantable (blogs, listicles, posts).
# Broader than parasitic mix membership — shortlist aggressively, convict via roles/L1.
EDITABLE_PATH_RE = re.compile(
    r"/(posts?|pulse|feed|status|newsletter)\b|/p/[a-z0-9]"
    r"|/(blog|blogs|article|articles|reviews?|roundup|guides?|picks|best-[\w-]+)\b",
    re.I,
)
# Role baselines for open / soft editorial surfaces (no per-host labels).
EDITABILITY_ROLE_BASE: dict[str, float] = {
    "expert_listicle": 0.55,
    "editorial": 0.5,
    "review_profile": 0.5,
    "factual_blog": 0.4,
    "commercial_product": 0.15,
    "ugc_thread": 0.0,
    "institutional": 0.0,
}
EDITABLE_PATH_BASE = 0.55
# Two-tier shortlist: always score elevated; adaptively sample the rest.
ELEVATED_PRIORITY = 0.4  # factual_blog role baseline and above
MAX_ELEVATED = 16  # hard compute cap on tier-1
MAX_FILLER = 8  # hard cap on adaptive tier-2
REFERRER_CONTENT_K = MAX_FILLER  # backward-compatible alias (max filler)
HIGH_SEMANTIC_RISK = 0.45

# Thread-path alias for triage / older tests (not social/Medium — those use editability).
THREAD_SURFACE_PATH_RE = THREAD_PATH_RE
MANIPULABLE_PATH_RE = THREAD_PATH_RE  # legacy name; thread paths only


def adaptive_filler_k(n_rest: int, *, max_filler: int = MAX_FILLER) -> int:
    """How many non-elevated referrers to score: ~ceil(n_rest/4), clamped.

    Grows with the remainder pool so sparse soft-surface batches still get a
    look, without scoring every commercial page.
    """
    if n_rest <= 0 or max_filler <= 0:
        return 0
    return min(max_filler, max(1, (n_rest + 3) // 4))


def select_referrer_shortlist(
    candidates: list[ReferrerExcerptCandidate],
    *,
    elevated_threshold: float = ELEVATED_PRIORITY,
    max_elevated: int = MAX_ELEVATED,
    max_filler: int = MAX_FILLER,
) -> tuple[list[ReferrerExcerptCandidate], int, int]:
    """Two-tier triage shortlist: (selected, n_elevated_taken, n_filler_taken)."""
    if not candidates:
        return [], 0, 0

    ranked = sorted(candidates, key=lambda c: c.manipulability, reverse=True)
    with_excerpt = [c for c in ranked if c.excerpt.strip()]
    pool = with_excerpt or ranked

    elevated = [
        c for c in pool if c.manipulability >= elevated_threshold
    ][: max(0, max_elevated)]
    elevated_keys = {c.url.rstrip("/").lower() for c in elevated}
    rest = [c for c in pool if c.url.rstrip("/").lower() not in elevated_keys]
    filler_n = adaptive_filler_k(len(rest), max_filler=max_filler)
    selected = elevated + rest[:filler_n]

    # If nothing cleared the elevated bar and filler is disabled, still peek once.
    if not selected and pool:
        selected = pool[:1]
        return selected, 0, 1 if selected[0].manipulability < elevated_threshold else 0

    return selected, len(elevated), min(filler_n, len(rest))


@dataclass
class ReferrerContentScore:
    url: str
    manipulability: float
    excerpt: str
    semantic_risk: float = 0.0
    content_flags: list[str] = field(default_factory=list)
    high_risk: bool = False
    segment_role: str = "body"
    scored: bool = False
    thread_surface: float = 0.0
    editability: float = 0.0


@dataclass
class ReferrerContentSummary:
    scored: int = 0
    high_risk_count: int = 0
    coordinated: bool = False
    independence: IndependenceReport | None = None
    scores: list[ReferrerContentScore] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ReferrerExcerptCandidate:
    url: str
    role: str
    entity: str
    marker: str = ""
    manipulability: float = 0.0
    excerpt: str = ""
    segment_role: str = "body"
    thread_surface: float = 0.0
    editability: float = 0.0


def _host_is_institutional_tld(hostname: str) -> bool:
    host = hostname.lower().removeprefix("www.")
    return host.endswith(".gov") or host.endswith(".edu")


def _clamp01(score: float) -> float:
    return max(0.0, min(1.0, score))


def thread_surface_score(
    url: str,
    *,
    html: str = "",
    segments: list[PageSegment] | None = None,
) -> float:
    """Higher = comment/forum attack surface (path + thread segments)."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    score = 0.0

    if THREAD_SURFACE_PATH_RE.search(path):
        score += 0.55
    if _host_is_institutional_tld(host):
        score -= 0.4

    segs = segments
    if segs is None and html:
        segs = extract_page_segments(html, url)
    if segs:
        comment_n = sum(1 for s in segs if s.role in ("comment", "nested_comment"))
        if comment_n >= 2:
            score += 0.35
        elif comment_n == 1:
            score += 0.15
        if any(s.role == "main_post" for s in segs) and comment_n >= 1:
            score += 0.1

    return _clamp01(score)


def editability_score(
    url: str,
    *,
    role: str = "",
) -> float:
    """Higher = soft surface where page body itself is cheap to plant / buy."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    score = EDITABILITY_ROLE_BASE.get(role, 0.0)
    if EDITABLE_PATH_RE.search(path):
        score = max(score, EDITABLE_PATH_BASE)
    if _host_is_institutional_tld(host):
        score -= 0.4
    return _clamp01(score)


def manipulability_score(
    url: str,
    *,
    html: str = "",
    segments: list[PageSegment] | None = None,
    role: str = "",
) -> float:
    """Shortlist priority: max(thread_surface, editability). Not a GEO verdict."""
    thread = thread_surface_score(url, html=html, segments=segments)
    edit = editability_score(url, role=role)
    return max(thread, edit)


def triage_channels(
    url: str,
    *,
    html: str = "",
    segments: list[PageSegment] | None = None,
    role: str = "",
) -> tuple[float, float, float]:
    """Return (thread_surface, editability, priority)."""
    thread = thread_surface_score(url, html=html, segments=segments)
    edit = editability_score(url, role=role)
    return thread, edit, max(thread, edit)


def entity_scoped_excerpt(
    url: str,
    *,
    html: str = "",
    text: str = "",
    segments: list[PageSegment] | None = None,
    entity: str,
    marker: str = "",
    window: int = 1200,
) -> tuple[str, str]:
    """Return (excerpt, segment_role) mentioning entity/marker; prefer UGC segments."""
    markers = [m for m in (marker, entity) if m and len(m.strip()) >= 2]
    markers_l = [m.lower() for m in markers]

    def _mentions(blob: str) -> bool:
        low = blob.lower()
        return any(m in low for m in markers_l)

    segs = segments
    if segs is None and html:
        segs = extract_page_segments(html, url)
    segs = segs or []
    mentioning = [s for s in segs if s.text and _mentions(s.text)]
    if mentioning:
        comments = [s for s in mentioning if s.role in ("comment", "nested_comment")]
        pick = comments[0] if comments else mentioning[0]
        return pick.text[: window * 2], pick.role

    source = text or ""
    if not source:
        return "", "body"
    low = source.lower()
    hit_at = -1
    for m in markers_l:
        idx = low.find(m)
        if idx >= 0 and (hit_at < 0 or idx < hit_at):
            hit_at = idx
    if hit_at < 0:
        return source[:window], "body"
    start = max(0, hit_at - window // 3)
    end = min(len(source), hit_at + window)
    return source[start:end], "body"


def is_high_risk_content(
    *,
    semantic_risk: float,
    flags: list[str],
    planted: bool,
) -> bool:
    if planted or "planted_mention" in flags:
        return True
    return semantic_risk >= HIGH_SEMANTIC_RISK


def score_excerpt(
    url: str,
    excerpt: str,
    *,
    entity: str,
    manipulability: float,
    segment_role: str = "body",
    thread_surface: float = 0.0,
    editability: float = 0.0,
) -> ReferrerContentScore:
    if not excerpt.strip():
        return ReferrerContentScore(
            url=url,
            manipulability=manipulability,
            excerpt="",
            segment_role=segment_role,
            scored=False,
            thread_surface=thread_surface,
            editability=editability,
        )
    content = extract_content_signals(excerpt, entity=entity)
    planted = detect_planted_mention(excerpt, entity=entity)
    flags = [f for f in content.flags if f != "planted_mention"]
    if planted:
        flags.append("planted_mention")
    high = is_high_risk_content(
        semantic_risk=content.semantic_risk,
        flags=flags,
        planted=planted,
    )
    return ReferrerContentScore(
        url=url,
        manipulability=manipulability,
        excerpt=excerpt[:500],
        semantic_risk=round(content.semantic_risk, 4),
        content_flags=flags,
        high_risk=high,
        segment_role=segment_role,
        scored=True,
        thread_surface=thread_surface,
        editability=editability,
    )


def build_excerpt_candidate(
    url: str,
    *,
    role: str,
    html: str = "",
    text: str = "",
    segments: list[PageSegment] | None = None,
    entity: str,
    marker: str = "",
) -> ReferrerExcerptCandidate:
    segs = segments
    thread, edit, priority = triage_channels(
        url, html=html, segments=segs, role=role
    )
    excerpt, seg_role = entity_scoped_excerpt(
        url,
        html=html,
        text=text,
        segments=segs,
        entity=entity,
        marker=marker,
    )
    return ReferrerExcerptCandidate(
        url=url,
        role=role,
        entity=entity,
        marker=marker,
        manipulability=priority,
        excerpt=excerpt,
        segment_role=seg_role,
        thread_surface=thread,
        editability=edit,
    )


def score_top_referrers(
    candidates: list[ReferrerExcerptCandidate],
    *,
    entity: str,
    k: int | None = None,
    max_filler: int | None = None,
    max_elevated: int = MAX_ELEVATED,
    elevated_threshold: float = ELEVATED_PRIORITY,
) -> ReferrerContentSummary:
    """Score a two-tier shortlist with entity-scoped L1 + independence L3.

    Tier 1: all elevated-priority referrers (up to ``max_elevated``).
    Tier 2: adaptive sample of the remainder (size ~ceil(n_rest/4), capped by
    ``max_filler`` / legacy ``k``). Tighten only from L1/L3 outcomes.
    """
    if not candidates:
        return ReferrerContentSummary()

    filler_cap = MAX_FILLER if max_filler is None and k is None else (
        max_filler if max_filler is not None else int(k or 0)
    )
    selected, n_elev, n_fill = select_referrer_shortlist(
        candidates,
        elevated_threshold=elevated_threshold,
        max_elevated=max_elevated,
        max_filler=filler_cap,
    )

    scores: list[ReferrerContentScore] = []
    for cand in selected:
        scores.append(
            score_excerpt(
                cand.url,
                cand.excerpt,
                entity=entity or cand.entity,
                manipulability=cand.manipulability,
                segment_role=cand.segment_role,
                thread_surface=cand.thread_surface,
                editability=cand.editability,
            )
        )

    scored_ok = [s for s in scores if s.scored and s.excerpt.strip()]
    high_n = sum(1 for s in scored_ok if s.high_risk)
    independence: IndependenceReport | None = None
    coordinated = False
    if len(scored_ok) >= 2:
        independence = analyze_independence({s.url: s.excerpt for s in scored_ok})
        coordinated = bool(independence.is_likely_coordinated)

    notes: list[str] = []
    if scored_ok:
        notes.append(
            f"Scored {len(scored_ok)} referrers "
            f"(elevated={n_elev}, adaptive_filler={n_fill}); high-risk={high_n}."
        )
    if coordinated:
        notes.append("Scored referrer excerpts look textually coordinated.")

    return ReferrerContentSummary(
        scored=len(scored_ok),
        high_risk_count=high_n,
        coordinated=coordinated,
        independence=independence,
        scores=scores,
        notes=notes,
    )


def referrer_content_tighten_extras(summary: ReferrerContentSummary | None) -> list[str]:
    """LLM action extras from referrer content evidence (never mutates trust)."""
    if summary is None or summary.scored <= 0:
        return []
    if summary.high_risk_count >= 2 or summary.coordinated:
        return ["attribute_only", "block_endorsement"]
    if summary.high_risk_count == 1:
        return ["downrank"]
    return []
