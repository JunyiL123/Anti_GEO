"""Entity-scoped L1 on Mode B referrers (eligible → score → tighten).

Score all verified referrers that are parasitic surfaces or soft editorial
roles (blogs / listicles / editorials / review profiles). Manipulability is
ordering/telemetry only when a safety cap truncates. Only L1/L3 outcomes
tighten root actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from anti_geo.content_signals import detect_planted_mention, extract_content_signals
from anti_geo.independence import analyze_independence
from anti_geo.models import IndependenceReport, PageSegment
from anti_geo.platform_role import THREAD_PATH_RE, is_parasitic_referrer
from anti_geo.segments import extract_page_segments

# Soft surfaces where page body itself is plantable (blogs, listicles, posts).
EDITABLE_PATH_RE = re.compile(
    r"/(posts?|pulse|feed|status|newsletter)\b|/p/[a-z0-9]"
    r"|/(blog|blogs|article|articles|reviews?|roundup|guides?|picks|best-[\w-]+)\b"
    # Soft complaint/directory surfaces (forum/thread paths use thread_surface instead)
    r"|/(?:customer[-_]reviews?|complaints?|directory|directories)\b",
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

# Soft editorial roles always content-eligible (even if not yet parasitic).
SOFT_EDITORIAL_ROLES = frozenset(
    {"factual_blog", "expert_listicle", "editorial", "review_profile"}
)

# Safety cap for pathological N; normal Mode B stays well under this.
MAX_CONTENT_SCORE = 32
# Legacy aliases (older shortlist API / tests).
MAX_ELEVATED = MAX_CONTENT_SCORE
MAX_FILLER = MAX_CONTENT_SCORE
ELEVATED_PRIORITY = 0.4
REFERRER_CONTENT_K = MAX_CONTENT_SCORE
HIGH_SEMANTIC_RISK = 0.45

# Thread-path alias for triage / older tests (not social/Medium — those use editability).
THREAD_SURFACE_PATH_RE = THREAD_PATH_RE
MANIPULABLE_PATH_RE = THREAD_PATH_RE  # legacy name; thread paths only


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


def content_score_eligible(
    url: str,
    role: str,
    *,
    content_high_risk: bool = False,
) -> bool:
    """True when this verified referrer should get entity-scoped L1.

    Parasitic surfaces always; soft editorial roles always. Commercial /
    institutional pages are skipped unless they already qualify as parasitic
    (e.g. Medium ``/p/`` publish path).
    """
    if is_parasitic_referrer(
        url=url, role=role, content_high_risk=content_high_risk
    ):
        return True
    return role in SOFT_EDITORIAL_ROLES


def _is_parasitic_candidate(cand: ReferrerExcerptCandidate) -> bool:
    return is_parasitic_referrer(
        url=cand.url, role=cand.role, content_high_risk=False
    )


def select_eligible_referrers(
    candidates: list[ReferrerExcerptCandidate],
    *,
    max_score: int = MAX_CONTENT_SCORE,
) -> tuple[list[ReferrerExcerptCandidate], int, int]:
    """Score-all eligible referrers; parasitic first, then manipulability.

    Returns ``(selected, n_parasitic, n_soft_editorial)`` among the selected
    set (soft count excludes those already counted as parasitic).
    """
    if not candidates:
        return [], 0, 0

    with_excerpt = [c for c in candidates if c.excerpt.strip()]
    pool = with_excerpt or []
    eligible = [
        c for c in pool if content_score_eligible(c.url, c.role)
    ]
    if not eligible:
        return [], 0, 0

    def _sort_key(c: ReferrerExcerptCandidate) -> tuple[int, float]:
        # Parasitic first (0), then higher manipulability.
        return (0 if _is_parasitic_candidate(c) else 1, -c.manipulability)

    ranked = sorted(eligible, key=_sort_key)
    selected = ranked[: max(0, max_score)]
    n_para = sum(1 for c in selected if _is_parasitic_candidate(c))
    n_soft = len(selected) - n_para
    return selected, n_para, n_soft


def adaptive_filler_k(n_rest: int, *, max_filler: int = MAX_FILLER) -> int:
    """Deprecated shortlist helper kept for import compatibility."""
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
    """Deprecated alias → :func:`select_eligible_referrers` (ignores tier knobs)."""
    del elevated_threshold, max_filler  # unused; score-all path
    return select_eligible_referrers(candidates, max_score=max_elevated)


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
    """Ordering/telemetry: max(thread_surface, editability). Not a GEO verdict."""
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
    max_score: int = MAX_CONTENT_SCORE,
    k: int | None = None,
    max_filler: int | None = None,
    max_elevated: int | None = None,
    elevated_threshold: float = ELEVATED_PRIORITY,
) -> ReferrerContentSummary:
    """Score all eligible referrers (parasitic + soft editorial) with L1 + L3.

    ``k`` / ``max_filler`` / ``max_elevated`` / ``elevated_threshold`` are
    accepted for call-site compatibility; only ``max_score`` (or legacy
    ``max_elevated`` / ``k`` as cap) limits how many are scored.
    """
    del elevated_threshold  # unused; eligibility is class-based
    if not candidates:
        return ReferrerContentSummary()

    cap = max_score
    if max_elevated is not None:
        cap = max_elevated
    elif k is not None:
        cap = int(k)
    elif max_filler is not None:
        cap = max(MAX_CONTENT_SCORE, int(max_filler))

    selected, n_para, n_soft = select_eligible_referrers(
        candidates, max_score=cap
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
            f"(parasitic={n_para}, soft_editorial={n_soft}); high-risk={high_n}."
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
