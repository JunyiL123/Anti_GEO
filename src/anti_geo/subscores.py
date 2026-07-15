from __future__ import annotations

import re
from urllib.parse import urlparse

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.content_signals import (
    compute_endorsement_risk,
    query_wants_recommendation,
    retrieval_manipulation_score,
    rhetorical_manipulation_score,
)
from anti_geo.models import QueryContextScores, SourceScore, SourceSubscores

_PATH_COMMERCIAL_RE = re.compile(r"/(pricing|buy|shop|cart|checkout|trial)\b", re.I)
_PATH_REFERENCE_RE = re.compile(r"/(wiki|baike|docs|reference|encyclopedia)\b", re.I)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _fetch_failure_kind(source: SourceScore) -> str | None:
    reasons = " ".join(source.reasons).lower()
    permanent_markers = (
        "fetch_failed:404",
        "fetch_failed:410",
        "invalid url",
        "unsupported protocol",
    )
    if any(marker in reasons for marker in permanent_markers):
        return "reject"
    if not source.fetch_ok:
        return "defer"
    return None


def compute_fetch_confidence(source: SourceScore) -> float:
    if not source.fetch_ok:
        kind = _fetch_failure_kind(source)
        return 0.0 if kind == "reject" else 0.2

    words = source.content_signals.word_count
    confidence = 0.75
    if words >= 80:
        confidence += 0.15
    elif words >= 40:
        confidence += 0.05
    elif words < 20:
        confidence -= 0.25

    if source.fetch_engine == "playwright":
        confidence += 0.05

    return _clamp(confidence)


def compute_rhetorical_manipulation(source: SourceScore) -> float:
    return rhetorical_manipulation_score(source.content_signals)


def compute_retrieval_manipulation_risk(
    source: SourceScore,
    query: str | None = None,
    rhetorical: float | None = None,
) -> float:
    content = source.content_signals
    rhet = rhetorical if rhetorical is not None else compute_rhetorical_manipulation(source)
    risk = retrieval_manipulation_score(content, rhet)

    page_ctx = source.page_context
    if page_ctx:
        if page_ctx.has_faq_schema and rhet > 0.25:
            risk = min(1.0, risk + 0.12)
        if page_ctx.list_item_count > 8 and rhet > 0.25:
            risk = min(1.0, risk + 0.08)
        if page_ctx.commercial_context_score > 0.45:
            risk = min(1.0, risk + 0.1 * page_ctx.commercial_context_score)

    if query and query_wants_recommendation(query) and rhet > 0.3:
        risk = min(1.0, risk + 0.1)

    return _clamp(risk)


def compute_factual_claim_reliability(
    source: SourceScore,
    query: str | None,
    query_intent: str,
    rhetorical: float,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> float:
    content = source.content_signals
    trust = source.trust_score
    reliability = 0.55

    if "balanced_hedging" in content.flags or "mentions_alternatives" in content.flags:
        reliability += 0.18
    if "quote_citation_heavy" in content.flags:
        reliability += 0.08
    if "established_domain" in source.reasons:
        reliability += 0.1
    if "institutional_tld" in source.reasons:
        reliability += 0.1

    if content.word_count < config.thin_content_words:
        reliability -= 0.18
    if rhetorical > 0.45:
        reliability -= 0.2 * rhetorical

    page_ctx = source.page_context
    if (
        query_intent.startswith("informational")
        and page_ctx
        and page_ctx.commercial_context_score > 0.45
        and not query_wants_recommendation(query)
    ):
        reliability -= 0.2

    if "high_stakes_medical_claim" in content.flags and trust < 0.55:
        reliability -= 0.25

    path = urlparse(source.url).path.lower()
    if _PATH_REFERENCE_RE.search(path):
        reliability += 0.12

    return _clamp(reliability)


def compute_intent_mismatch(
    source: SourceScore,
    query: str | None,
    query_intent: str,
) -> float:
    path = urlparse(source.url).path.lower()
    page_ctx = source.page_context
    content = source.content_signals

    if query_intent in ("commercial", "navigational"):
        if _PATH_COMMERCIAL_RE.search(path):
            return 0.0
        if page_ctx and page_ctx.commercial_context_score > 0.5:
            return 0.15
        return 0.25

    mismatch = 0.0
    if page_ctx and page_ctx.commercial_context_score > 0.5:
        mismatch += 0.45
    if _PATH_COMMERCIAL_RE.search(path):
        mismatch += 0.35
    if "balanced_hedging" in content.flags or "mentions_alternatives" in content.flags:
        mismatch *= 0.3
    if _PATH_REFERENCE_RE.search(path):
        mismatch *= 0.2

    if query and not query_wants_recommendation(query) and mismatch > 0:
        mismatch = min(1.0, mismatch + 0.1)

    return _clamp(mismatch)


def compute_harm_severity(query_intent: str) -> float:
    if query_intent.endswith("high_stakes"):
        return 0.85
    if query_intent.startswith("informational"):
        return 0.35
    return 0.15


def compute_subscores(
    source: SourceScore,
    query: str | None = None,
    query_intent: str = "informational",
    config: DefenseConfig = DEFAULT_CONFIG,
) -> SourceSubscores:
    rhetorical = compute_rhetorical_manipulation(source)
    retrieval = compute_retrieval_manipulation_risk(source, query, rhetorical)
    endorsement_risk = compute_endorsement_risk(
        query,
        source.text_excerpt,
        source.content_signals,
        source.trust_score,
        source.page_context,
        query_intent,
        config,
    )
    factual = compute_factual_claim_reliability(
        source, query, query_intent, rhetorical, config
    )

    return SourceSubscores(
        fetch_confidence=compute_fetch_confidence(source),
        source_trust=source.trust_score,
        rhetorical_manipulation=rhetorical,
        retrieval_manipulation_risk=retrieval,
        endorsement_risk=endorsement_risk,
        factual_claim_reliability=factual,
        intent_mismatch=compute_intent_mismatch(source, query, query_intent),
        harm_severity=compute_harm_severity(query_intent),
    )


def build_query_context_scores(
    independence_cluster_count: int | None = None,
    is_likely_coordinated: bool = False,
    corroboration_strength: float = 0.0,
    visibility_dominance: float = 0.0,
    visibility_alert: bool = False,
) -> QueryContextScores:
    if is_likely_coordinated:
        consensus = "coordinated"
    elif independence_cluster_count is not None and independence_cluster_count < 2:
        consensus = "shaky"
    else:
        consensus = "healthy"

    dominance = visibility_dominance
    if visibility_alert:
        dominance = max(dominance, 0.65)

    return QueryContextScores(
        consensus_integrity=consensus,
        corroboration_strength=corroboration_strength,
        visibility_dominance=dominance,
    )
