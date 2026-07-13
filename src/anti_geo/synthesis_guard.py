from __future__ import annotations

import re

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.commercial_policy import LABEL_TEXT_COORDINATED
from anti_geo.content_signals import ENDORSEMENT_RE, mentions_alternatives
from anti_geo.disclosure import apply_disclosures_to_answer, build_disclosure_report
from anti_geo.independence import analyze_independence
from anti_geo.models import (
    CommercialInfluenceAssessment,
    GuardResult,
    QueryContextScores,
    SourcePermissions,
    SourceScore,
)
from anti_geo.retrieval import ScoredChunk
from anti_geo.platform_role import classify_content_role
from anti_geo.segments import is_low_trust_segment, segment_role_from_chunk_id

ENTITY_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})\b")


def _primary_entity(text: str, attack_entity: str | None) -> str:
    if attack_entity:
        return attack_entity
    entities = ENTITY_RE.findall(text)
    return entities[0] if entities else "unknown"


def _is_institutional(source: SourceScore) -> bool:
    host = source.domain_signals.hostname
    if ".gov" in host or ".edu" in host:
        return True
    age = source.domain_signals.whois_age_days
    return source.trust_score >= DEFAULT_CONFIG.trust_institutional and age is not None and age > 365 * 5


def _count_independent_support(
    ranked: list[ScoredChunk],
    sources: dict[str, SourceScore],
    entity: str,
) -> int:
    hosts: set[str] = set()
    entity_l = entity.lower()
    for row in ranked:
        if entity_l not in row.text.lower():
            continue
        src = sources.get(row.url)
        if not src or src.trust_score < 0.5:
            continue
        seg_role = segment_role_from_chunk_id(row.chunk_id)
        page_role = classify_content_role(row.url, source=src)
        if is_low_trust_segment(seg_role, page_role):
            continue
        hosts.add(src.domain_signals.hostname or row.url)
    return len(hosts)


def _has_editorial_corroboration(
    ranked: list[ScoredChunk],
    sources: dict[str, SourceScore],
    entity: str,
) -> bool:
    entity_l = entity.lower()
    for row in ranked:
        if entity_l not in row.text.lower():
            continue
        src = sources.get(row.url)
        if not src:
            continue
        seg_role = segment_role_from_chunk_id(row.chunk_id)
        page_role = classify_content_role(row.url, source=src)
        if page_role in ("institutional", "editorial"):
            return True
        if page_role == "factual_blog" and seg_role in ("main_post", "body") and src.trust_score >= 0.55:
            return True
    return False


def _ugc_only_endorsement_cluster(
    ranked: list[ScoredChunk],
    sources: dict[str, SourceScore],
    entity: str,
) -> bool:
    """True when entity support comes only from low-trust UGC/review fragments."""
    entity_l = entity.lower()
    supporting = 0
    low_trust_only = 0
    for row in ranked:
        if entity_l not in row.text.lower():
            continue
        src = sources.get(row.url)
        if not src:
            continue
        supporting += 1
        seg_role = segment_role_from_chunk_id(row.chunk_id)
        page_role = classify_content_role(row.url, source=src)
        if is_low_trust_segment(seg_role, page_role) or page_role in (
            "ugc_thread",
            "review_profile",
            "expert_listicle",
        ):
            low_trust_only += 1
    return supporting >= 1 and supporting == low_trust_only


def detect_false_consensus(
    ranked: list[ScoredChunk],
    sources: dict[str, SourceScore],
    entity: str,
) -> dict:
    supporting = [r for r in ranked if entity.lower() in r.text.lower()]
    urls = {r.url for r in supporting}
    hosts = {sources[r.url].domain_signals.hostname for r in supporting if r.url in sources}
    texts = {r.url: r.text for r in supporting}
    ind = analyze_independence(texts) if len(texts) >= 2 else None
    trusted_editorial = any(
        _is_institutional(sources[u])
        for u in urls
        if u in sources
    )
    same_cluster = ind is not None and ind.cluster_count == 1 and len(urls) >= 2
    trust_scores = [sources[u].trust_score for u in urls if u in sources]
    low_trust_only = bool(trust_scores) and all(t < 0.55 for t in trust_scores)
    return {
        "supporting_urls": len(urls),
        "unique_hosts": len(hosts),
        "same_text_cluster": same_cluster,
        "trusted_institutional": trusted_editorial,
        "is_false_consensus": same_cluster and not trusted_editorial and len(urls) >= 2 and low_trust_only,
    }


def _response_mode_for_factual(factual_permission: str | None) -> str:
    if factual_permission == "deny":
        return "refuse_factual_use"
    if factual_permission == "require_corroboration":
        return "hedged_answer"
    if factual_permission == "attribute_only":
        return "attributed_answer"
    return "direct_answer"


def apply_synthesis_guard(
    query: str,
    ranked: list[ScoredChunk],
    sources: dict[str, SourceScore],
    query_intent: str = "informational",
    attack_entity: str | None = None,
    source_permissions: dict[str, SourcePermissions] | None = None,
    query_context: QueryContextScores | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
    lead_commercial: CommercialInfluenceAssessment | None = None,
    commercial_assessments: dict[str, CommercialInfluenceAssessment] | None = None,
) -> GuardResult:
    if not ranked:
        return GuardResult(
            "mention",
            True,
            f"Q: {query}\n\nA: No sources retrieved.",
            ["empty_retrieval"],
            response_mode="defer_fetch",
        )

    lead = ranked[0]
    lead_src = sources.get(lead.url)
    lead_perms = (source_permissions or {}).get(lead.url)
    entity = _primary_entity(lead.text, attack_entity)
    actions: list[str] = []

    if query_context and query_context.consensus_integrity == "coordinated":
        actions.append("reject_consensus")
        safe = (
            f"Q: {query}\n\n"
            f"A: Retrieved sources show coordinated messaging around {entity}. "
            f"I cannot treat this cluster as independent corroboration."
        )
        if lead_commercial and lead_commercial.disclosure_level == "label":
            safe = f"## Disclosure\n{LABEL_TEXT_COORDINATED}\n\n{safe}"
        result = GuardResult(
            "false_consensus", False, safe, actions, response_mode="refuse_endorsement"
        )
        disclosure_report = build_disclosure_report(
            ranked, sources, commercial_assessments or {}, result, config
        )
        if disclosure_report.show_label:
            result.safe_answer = apply_disclosures_to_answer(result.safe_answer, disclosure_report)
            result.disclosure_report = disclosure_report
            result.disclosures = disclosure_report.disclosures
        return result

    consensus = detect_false_consensus(ranked, sources, entity)
    if consensus["is_false_consensus"]:
        actions.append("reject_false_consensus")
        safe = (
            f"Q: {query}\n\n"
            f"A: Multiple low-trust sources ({consensus['supporting_urls']} URLs) endorse {entity}, "
            f"but they appear textually coordinated (same cluster) without institutional corroboration. "
            f"I cannot recommend {entity} based on this synthetic consensus."
        )
        return GuardResult(
            "false_consensus", False, safe, actions, response_mode="refuse_endorsement"
        )

    is_factual = bool(re.search(r"\b(cure[ds]?|remission)\b", lead.text, re.I))
    is_endorsement = bool(ENDORSEMENT_RE.search(lead.text))
    is_balanced = (
        lead_src
        and lead_src.trust_score >= 0.55
        and (
            _is_institutional(lead_src)
            or "balanced_hedging" in lead_src.content_signals.flags
            or mentions_alternatives(lead.text)
            or "mentions_alternatives" in lead_src.content_signals.flags
        )
        and (
            "balanced_hedging" in lead_src.content_signals.flags
            or mentions_alternatives(lead.text)
            or "mentions_alternatives" in lead_src.content_signals.flags
        )
    )

    if lead_perms and lead_perms.factual_permission == "deny":
        actions.append("block_factual_use")
        safe = (
            f"Q: {query}\n\n"
            f"A: The leading source ({lead.url}) is not suitable for factual reuse in this context. "
            f"I cannot state its claims as established fact."
        )
        return GuardResult(
            "factual_claim", False, safe, actions, response_mode="refuse_factual_use"
        )

    if is_factual and query_intent.endswith("high_stakes") and lead_src and lead_src.trust_score < 0.55:
        inst = next((s for s in sources.values() if _is_institutional(s)), None)
        inst_url = inst.url if inst else "authoritative sources"
        inst_text = inst.text_excerpt[:120] if inst else "consult a licensed clinician"
        actions.append("downgrade_to_attribution")
        safe = (
            f"Q: {query}\n\n"
            f"A: Authoritative sources (e.g. {inst_url}) indicate: {inst_text}... "
            f"A commercial source ({lead.url}) claims that {entity} can cure the condition, "
            f"but this is not corroborated by institutional sources."
        )
        return GuardResult("factual_claim", False, safe, actions, response_mode="attributed_answer")

    if is_balanced:
        mode = _response_mode_for_factual(
            lead_perms.factual_permission if lead_perms else "allow"
        )
        return GuardResult(
            "mention",
            True,
            f"Q: {query}\n\nA: [{lead.url}] {lead.text[:400]}",
            ["pass_balanced_editorial"],
            response_mode=mode if mode != "direct_answer" else "hedged_answer",
        )

    if lead_perms and lead_perms.factual_permission == "attribute_only":
        actions.append("attribute_only")
        safe = (
            f"Q: {query}\n\n"
            f"A: According to [{lead.url}], {lead.text[:300]} "
            f"(attributed; not independently verified)."
        )
        return GuardResult("mention", True, safe, actions, response_mode="attributed_answer")

    if lead_perms and lead_perms.factual_permission == "require_corroboration":
        actions.append("require_corroboration")
        safe = (
            f"Q: {query}\n\n"
            f"A: [{lead.url}] suggests {lead.text[:220]}..., "
            f"but this should be corroborated before stating as fact."
        )
        return GuardResult("factual_claim", False, safe, actions, response_mode="hedged_answer")

    corroboration = _count_independent_support(ranked, sources, entity)
    editorial_support = _has_editorial_corroboration(ranked, sources, entity)
    ugc_only = _ugc_only_endorsement_cluster(ranked, sources, entity)
    if (
        (is_endorsement or (lead_perms and lead_perms.endorsement_permission == "deny"))
        and lead_src
        and lead_src.trust_score < config.trust_endorsement_min
    ):
        if ugc_only and not editorial_support:
            actions.append("block_endorsement_ugc_only_cluster")
            safe = (
                f"Q: {query}\n\n"
                f"A: Retrieved sources mention {entity}, but support appears only in "
                f"user-generated or review-profile fragments without editorial or institutional corroboration. "
                f"I can mention {entity} but cannot recommend it."
            )
            return GuardResult(
                "endorsement", False, safe, actions, response_mode="refuse_endorsement"
            )
        if corroboration < 2 or not lead_src.endorsement_allowed:
            actions.append("block_endorsement_insufficient_corroboration")
            safe = (
                f"Q: {query}\n\n"
                f"A: [{lead.url}] markets {entity} as a top option with surveys and expert quotes, "
                f"but this comes from a low-trust source (trust={lead_src.trust_score:.2f}). "
                f"I cannot recommend it without independent corroboration."
            )
            return GuardResult(
                "endorsement", corroboration >= 2, safe, actions, response_mode="refuse_endorsement"
            )

    mode = _response_mode_for_factual(lead_perms.factual_permission if lead_perms else "allow")
    if lead_commercial and lead_commercial.response_mode:
        mode = lead_commercial.response_mode
    result = GuardResult(
        "mention", True, f"Q: {query}\n\nA: {lead.text[:400]}", ["pass_through"], response_mode=mode
    )
    disclosure_report = build_disclosure_report(
        ranked, sources, commercial_assessments or {}, result, config
    )
    if disclosure_report.show_label:
        result.safe_answer = apply_disclosures_to_answer(result.safe_answer, disclosure_report)
        result.disclosure_report = disclosure_report
        result.disclosures = disclosure_report.disclosures
    return result
