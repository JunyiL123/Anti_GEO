from __future__ import annotations

import re

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.content_signals import (
    action_from_endorsement_risk,
    compute_endorsement_risk,
)
from anti_geo.models import CorroborationReport, SourceScore, UrlAnalysisReport

ENTITY_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})\b")


def _entities_in_text(text: str) -> list[str]:
    return [m.group(1) for m in ENTITY_RE.finditer(text)]


def decide_single_source(
    source: SourceScore,
    query_intent: str = "informational",
    query: str | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> UrlAnalysisReport:
    """Map inferred scores → retrieval/synthesis action."""
    if not source.fetch_ok:
        return UrlAnalysisReport(
            query_intent=query_intent,
            source=source,
            recommended_action="reject",
            query=query,
        )

    endorsement_risk = compute_endorsement_risk(
        query,
        source.text_excerpt,
        source.content_signals,
        source.trust_score,
        source.page_context,
        query_intent,
    )

    if query and query_intent.startswith("informational"):
        action = action_from_endorsement_risk(endorsement_risk, config)
        if (
            query_intent.endswith("high_stakes")
            and "high_stakes_medical_claim" in source.content_signals.flags
            and source.trust_score < 0.55
            and chunk_endorses_high_stakes(source)
        ):
            action = "block_endorsement"
        return UrlAnalysisReport(
            query_intent=query_intent,
            source=source,
            recommended_action=action,
            endorsement_risk=endorsement_risk,
            query=query,
        )

    high_stakes = query_intent.endswith("high_stakes")
    risk = source.semantic_risk
    trust = source.trust_score

    if not query_intent.startswith("informational"):
        action = "pass"
        if high_stakes and risk > config.high_stakes_risk_threshold and trust < config.high_stakes_trust_threshold:
            action = "block_endorsement"
        elif risk > config.downrank_risk_threshold and trust < config.downrank_trust_threshold:
            action = "downrank"
        return UrlAnalysisReport(
            query_intent=query_intent,
            source=source,
            recommended_action=action,
            endorsement_risk=endorsement_risk,
            query=query,
        )

    if high_stakes and risk > config.high_stakes_risk_threshold and trust < config.high_stakes_trust_threshold:
        action = "block_endorsement"
    elif risk > config.downrank_risk_threshold and trust < config.downrank_trust_threshold:
        action = "downrank"
    elif not source.endorsement_allowed:
        action = "block_endorsement"
    else:
        action = "pass"

    return UrlAnalysisReport(
        query_intent=query_intent,
        source=source,
        recommended_action=action,
        endorsement_risk=endorsement_risk,
        query=query,
    )


def chunk_endorses_high_stakes(source: SourceScore) -> bool:
    text = source.text_excerpt.lower()
    return bool(re.search(r"\b(cure[ds]?|remission)\b", text)) and "balanced_hedging" not in source.content_signals.flags


def decide_corroboration_for_claim(
    sources: list[SourceScore],
    claim_entity: str,
    independence_cluster_count: int,
    query_intent: str = "informational",
    config: DefenseConfig = DEFAULT_CONFIG,
) -> CorroborationReport:
    """Endorsement gate from inferred trust + textual independence clusters."""
    supporting: list[str] = []
    institutional = False
    entity_lower = claim_entity.lower()

    for s in sources:
        if entity_lower not in s.text_excerpt.lower():
            continue
        if s.trust_score >= 0.55 and s.endorsement_allowed:
            supporting.append(s.url)
        age = s.domain_signals.whois_age_days
        if s.trust_score >= config.trust_institutional and age is not None and age > 365 * 5:
            institutional = True
        if ".gov" in s.domain_signals.hostname or ".edu" in s.domain_signals.hostname:
            institutional = True

    endorsement_ok = independence_cluster_count >= 2 and len(supporting) >= 2
    if query_intent.startswith("informational") and not institutional:
        endorsement_ok = False

    reasons: list[str] = []
    if independence_cluster_count < 2:
        reasons.append(f"only_{independence_cluster_count}_independent_text_cluster(s)")
    if len(supporting) < 2:
        reasons.append(f"only_{len(supporting)}_trusted_source(s)_mention_{claim_entity}")
    if query_intent.startswith("informational") and not institutional:
        reasons.append("no_institutional_corroboration")

    return CorroborationReport(
        claim_entity=claim_entity,
        supporting_urls=supporting,
        independent_support_count=independence_cluster_count,
        has_institutional_support=institutional,
        endorsement_allowed=endorsement_ok,
        reasons=reasons,
    )


def extract_shared_claim(sources: list[SourceScore]) -> str | None:
    """Find capitalized entity mentioned by multiple sources."""
    counts: dict[str, int] = {}
    for s in sources:
        for ent in set(_entities_in_text(s.text_excerpt)):
            if len(ent) < 4:
                continue
            counts[ent] = counts.get(ent, 0) + 1
    if not counts:
        return None
    best = max(counts, key=counts.get)
    return best if counts[best] >= 1 else None
