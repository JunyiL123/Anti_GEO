"""Entity-scoped L1 on Mode B referrers (manipulability triage → top-K → tighten)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from anti_geo.content_signals import detect_planted_mention, extract_content_signals
from anti_geo.independence import analyze_independence
from anti_geo.models import IndependenceReport, PageSegment
from anti_geo.segments import extract_page_segments

# Structural page shapes — not brand/host allowlists.
MANIPULABLE_PATH_RE = re.compile(
    r"/(comments?|forum|thread|questions|discussion|posts?|pulse|feed|status)\b",
    re.I,
)
REFERRER_CONTENT_K = 8
HIGH_SEMANTIC_RISK = 0.45


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


def _host_is_institutional_tld(hostname: str) -> bool:
    host = hostname.lower().removeprefix("www.")
    return host.endswith(".gov") or host.endswith(".edu")


def manipulability_score(
    url: str,
    *,
    html: str = "",
    segments: list[PageSegment] | None = None,
) -> float:
    """Higher = more attack-surface structure (path / thread segments)."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    score = 0.0

    if MANIPULABLE_PATH_RE.search(path):
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

    return max(0.0, score)


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
) -> ReferrerContentScore:
    if not excerpt.strip():
        return ReferrerContentScore(
            url=url,
            manipulability=manipulability,
            excerpt="",
            segment_role=segment_role,
            scored=False,
        )
    content = extract_content_signals(excerpt)
    planted = detect_planted_mention(excerpt, entity=entity)
    flags = list(content.flags)
    if planted and "planted_mention" not in flags:
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
    manip = manipulability_score(url, html=html, segments=segs)
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
        manipulability=manip,
        excerpt=excerpt,
        segment_role=seg_role,
    )


def score_top_referrers(
    candidates: list[ReferrerExcerptCandidate],
    *,
    entity: str,
    k: int = REFERRER_CONTENT_K,
) -> ReferrerContentSummary:
    """Score top-K by manipulability with entity-scoped L1 + independence L3."""
    if not candidates:
        return ReferrerContentSummary()

    ranked = sorted(candidates, key=lambda c: c.manipulability, reverse=True)
    # Prefer candidates with a real excerpt; still allow structure-only if needed.
    with_excerpt = [c for c in ranked if c.excerpt.strip()]
    pool = with_excerpt or ranked
    selected = pool[: max(1, k)]

    scores: list[ReferrerContentScore] = []
    for cand in selected:
        scores.append(
            score_excerpt(
                cand.url,
                cand.excerpt,
                entity=entity or cand.entity,
                manipulability=cand.manipulability,
                segment_role=cand.segment_role,
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
            f"Scored {len(scored_ok)} high-manipulability referrers "
            f"(top-{k} by structure); high-risk={high_n}."
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
