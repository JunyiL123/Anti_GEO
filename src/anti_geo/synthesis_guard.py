from __future__ import annotations

import re

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.content_signals import ENDORSEMENT_RE, mentions_alternatives
from anti_geo.independence import analyze_independence
from anti_geo.models import GuardResult, SourceScore
from anti_geo.retrieval import ScoredChunk

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
        hosts.add(src.domain_signals.hostname or row.url)
    return len(hosts)


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


def apply_synthesis_guard(
    query: str,
    ranked: list[ScoredChunk],
    sources: dict[str, SourceScore],
    query_intent: str = "informational",
    attack_entity: str | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> GuardResult:
    if not ranked:
        return GuardResult("mention", True, f"Q: {query}\n\nA: No sources retrieved.", ["empty_retrieval"])

    lead = ranked[0]
    lead_src = sources.get(lead.url)
    entity = _primary_entity(lead.text, attack_entity)
    actions: list[str] = []

    consensus = detect_false_consensus(ranked, sources, entity)
    if consensus["is_false_consensus"]:
        actions.append("reject_false_consensus")
        safe = (
            f"Q: {query}\n\n"
            f"A: Multiple low-trust sources ({consensus['supporting_urls']} URLs) endorse {entity}, "
            f"but they appear textually coordinated (same cluster) without institutional corroboration. "
            f"I cannot recommend {entity} based on this synthetic consensus."
        )
        return GuardResult("false_consensus", False, safe, actions)

    is_factual = bool(re.search(r"\b(cure[ds]?|remission)\b", lead.text, re.I))
    is_endorsement = bool(ENDORSEMENT_RE.search(lead.text))
    is_balanced = (
        lead_src
        and lead_src.trust_score >= 0.7
        and (_is_institutional(lead_src) or mentions_alternatives(lead.text))
        and ("balanced_hedging" in lead_src.content_signals.flags or mentions_alternatives(lead.text))
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
        return GuardResult("factual_claim", False, safe, actions)

    if is_balanced:
        return GuardResult(
            "mention",
            True,
            f"Q: {query}\n\nA: [{lead.url}] {lead.text[:400]}",
            ["pass_balanced_editorial"],
        )

    corroboration = _count_independent_support(ranked, sources, entity)
    if is_endorsement and lead_src and lead_src.trust_score < config.trust_endorsement_min:
        if corroboration < 2 or not lead_src.endorsement_allowed:
            actions.append("block_endorsement_insufficient_corroboration")
            safe = (
                f"Q: {query}\n\n"
                f"A: [{lead.url}] markets {entity} as a top option with surveys and expert quotes, "
                f"but this comes from a low-trust source (trust={lead_src.trust_score:.2f}). "
                f"I cannot recommend it without independent corroboration."
            )
            return GuardResult("endorsement", corroboration >= 2, safe, actions)

    return GuardResult("mention", True, f"Q: {query}\n\nA: {lead.text[:400]}", ["pass_through"])
