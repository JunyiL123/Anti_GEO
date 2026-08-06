from __future__ import annotations

import re

from anti_geo.claim_entity import (
    brand_from_sources,
    is_junk_entity,
    normalize_query_topic,
    resolve_claim_entity,
    shared_title_case_claim,
)
from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.models import CorroborationReport, SourceScore, UrlAnalysisReport
from anti_geo.permissions import (
    apply_high_stakes_endorsement_deny,
    chunk_endorses_high_stakes,
    derive_permissions,
    summarize_recommended_action,
)
from anti_geo.permissions_llm import maybe_apply_permissions_llm
from anti_geo.subscores import _fetch_failure_kind, compute_subscores

# Back-compat aliases used by older tests/importers.
ENTITY_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})\b")
_is_junk_entity = is_junk_entity
_normalize_query_topic = normalize_query_topic
_brand_from_sources = brand_from_sources
_shared_title_case_claim = shared_title_case_claim


def _entities_in_text(text: str) -> list[str]:
    return [m.group(1) for m in ENTITY_RE.finditer(text or "")]


def extract_shared_claim(
    sources: list[SourceScore],
    *,
    query: str | None = None,
    query_intent: str = "informational",
    content_roles: list[str] | None = None,
    use_llm: bool | None = False,
) -> str | None:
    """Resolve claim entity (defaults ``use_llm=False`` for offline callers)."""
    return resolve_claim_entity(
        sources,
        query=query,
        query_intent=query_intent,
        content_roles=content_roles,
        use_llm=use_llm,
    )


def _has_persuasive_content(source: SourceScore) -> bool:
    flags = source.content_signals.flags
    return (
        "comparative_superlatives" in flags
        or "authority_stacking" in flags
        or source.content_signals.comparative_density > DEFAULT_CONFIG.comparative_flag_threshold
    )


def decide_single_source(
    source: SourceScore,
    query_intent: str = "informational",
    query: str | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
    *,
    use_llm: bool | None = False,
    content_role: str | None = None,
) -> UrlAnalysisReport:
    """Map inferred subscores → permissions → retrieval/synthesis action.

    ``use_llm``: False = offline/heuristic only (default); None = Azure when
    configured (investigate path); True = force attempt when gated.
    """
    from anti_geo.platform_role import classify_content_role

    role = content_role or classify_content_role(source.url, source=source)
    subscores = compute_subscores(source, query, query_intent, config)
    fetch_failure = _fetch_failure_kind(source) if not source.fetch_ok else None
    concealment_flags = (
        list(source.concealment.flags)
        if source.concealment is not None
        else None
    )
    permissions = derive_permissions(
        subscores,
        fetch_failure_kind=fetch_failure,
        has_persuasive_content=_has_persuasive_content(source),
        config=config,
        content_role=role,
        query_intent=query_intent,
        query=query,
        concealment_flags=concealment_flags,
    )
    permissions_source = "heuristic"
    permissions_llm_reason = ""

    permissions = apply_high_stakes_endorsement_deny(
        permissions,
        source,
        query=query,
        query_intent=query_intent,
    )

    llm_hit = maybe_apply_permissions_llm(
        source,
        permissions,
        subscores,
        query=query,
        query_intent=query_intent,
        fetch_failure_kind=fetch_failure,
        use_llm=use_llm,
        config=config,
        content_role=role,
    )
    permissions = llm_hit.permissions
    permissions_source = llm_hit.source
    permissions_llm_reason = llm_hit.reason

    action = summarize_recommended_action(permissions, subscores, config)

    return UrlAnalysisReport(
        query_intent=query_intent,
        source=source,
        recommended_action=action,
        endorsement_risk=subscores.endorsement_risk,
        query=query,
        subscores=subscores,
        permissions=permissions,
        permissions_source=permissions_source,
        permissions_llm_reason=permissions_llm_reason,
    )


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
