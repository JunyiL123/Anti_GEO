from __future__ import annotations

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.commercial_policy import assess_commercial_influence, tighten_permissions
from anti_geo.models import (
    CommercialInfluenceAssessment,
    QueryContextScores,
    SourcePermissions,
    SourceScore,
    SourceSubscores,
)


def derive_permissions(
    subscores: SourceSubscores,
    query_context: QueryContextScores | None = None,
    fetch_failure_kind: str | None = None,
    has_persuasive_content: bool = False,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> SourcePermissions:
    """Map subscores → explicit retrieve/mention/factual/endorsement permissions."""
    ctx = query_context or QueryContextScores("healthy", 0.0, 0.0)

    retrieve = _derive_retrieve_permission(subscores, ctx, fetch_failure_kind)
    mention = _derive_mention_permission(subscores, fetch_failure_kind)
    factual = _derive_factual_permission(subscores, ctx, fetch_failure_kind)
    endorsement = _derive_endorsement_permission(
        subscores, factual, ctx, has_persuasive_content, config
    )

    return SourcePermissions(
        retrieve_permission=retrieve,
        mention_permission=mention,
        factual_permission=factual,
        endorsement_permission=endorsement,
    )


def _derive_retrieve_permission(
    subscores: SourceSubscores,
    ctx: QueryContextScores,
    fetch_failure_kind: str | None,
) -> str:
    if fetch_failure_kind == "reject":
        return "reject"
    if fetch_failure_kind == "defer" or subscores.fetch_confidence < 0.25:
        return "defer"
    if (
        subscores.retrieval_manipulation_risk >= 0.55
        or subscores.intent_mismatch >= 0.5
        or ctx.visibility_dominance >= 0.6
        or ctx.consensus_integrity == "coordinated"
    ):
        return "downrank"
    if subscores.source_trust < 0.35:
        return "downrank"
    return "allow"


def _derive_mention_permission(
    subscores: SourceSubscores,
    fetch_failure_kind: str | None,
) -> str:
    if fetch_failure_kind == "reject":
        return "deny"
    if subscores.fetch_confidence < 0.1:
        return "deny"
    return "allow"


def _derive_factual_permission(
    subscores: SourceSubscores,
    ctx: QueryContextScores,
    fetch_failure_kind: str | None,
) -> str:
    if fetch_failure_kind in ("reject", "defer") or subscores.fetch_confidence < 0.25:
        return "deny"

    if ctx.consensus_integrity == "coordinated" and subscores.factual_claim_reliability < 0.5:
        return "deny"

    if subscores.harm_severity >= 0.7:
        if subscores.factual_claim_reliability < 0.45 or subscores.source_trust < 0.5:
            return "deny"
        if subscores.factual_claim_reliability < 0.6 or subscores.source_trust < 0.6:
            return "require_corroboration"

    if subscores.source_trust < 0.45 or subscores.factual_claim_reliability < 0.45:
        return "attribute_only"

    if (
        subscores.source_trust >= 0.55
        and subscores.factual_claim_reliability >= 0.55
        and subscores.intent_mismatch < 0.35
    ):
        return "allow"

    return "attribute_only"


def _derive_endorsement_permission(
    subscores: SourceSubscores,
    factual: str,
    ctx: QueryContextScores,
    has_persuasive_content: bool,
    config: DefenseConfig,
) -> str:
    if factual == "deny":
        return "deny"
    if ctx.consensus_integrity == "coordinated":
        return "deny"
    if subscores.endorsement_risk >= config.endorsement_risk_block:
        return "deny"
    # Require a meaningful endorsement-risk floor so 0.001 noise does not
    # block mid-trust encyclopedias / institutional pages.
    if (
        subscores.endorsement_risk >= config.endorsement_risk_trust_gate
        and subscores.source_trust < config.trust_endorsement_min
    ):
        return "deny"
    if has_persuasive_content and subscores.rhetorical_manipulation >= 0.35:
        return "deny"
    if (
        subscores.endorsement_risk >= config.endorsement_risk_downrank
        and subscores.source_trust < config.trust_endorsement_min
    ):
        return "deny"
    return "allow"


_LLM_ACTION_PRIORITY = (
    "reject",
    "reject_consensus",
    "defer_fetch",
    "block_factual_use",
    "block_endorsement",
    "require_corroboration",
    "require_authoritative_corroboration",
    "attribute_only",
    "mention_only",
    "downrank",
    "pass",
)


def derive_llm_actions(
    permissions: SourcePermissions,
    subscores: SourceSubscores | None = None,
    query_context: QueryContextScores | None = None,
) -> tuple[str, list[str]]:
    """Map permissions to explicit LLM-facing actions for retrieval and synthesis."""
    ctx = query_context or QueryContextScores("healthy", 0.0, 0.0)
    actions: list[str] = []

    retrieve = permissions.retrieve_permission
    if retrieve == "reject":
        actions.append("reject")
    elif retrieve == "defer":
        actions.append("defer_fetch")
    elif retrieve == "downrank":
        actions.append("downrank")

    if ctx.consensus_integrity == "coordinated":
        actions.append("reject_consensus")

    if permissions.mention_permission == "deny":
        actions.append("reject")

    factual = permissions.factual_permission
    if factual == "deny":
        actions.append("block_factual_use")
    elif factual == "require_corroboration":
        actions.append("require_corroboration")
        if subscores and subscores.harm_severity >= 0.7:
            actions.append("require_authoritative_corroboration")
    elif factual == "attribute_only":
        actions.append("attribute_only")

    if permissions.endorsement_permission == "deny":
        actions.append("block_endorsement")

    if not actions:
        actions.append("pass")
    elif permissions.mention_permission == "allow" and factual == "allow" and permissions.endorsement_permission == "allow":
        actions.append("pass")
    elif permissions.mention_permission == "allow":
        actions.append("mention_only")

    deduped = list(dict.fromkeys(actions))
    primary = min(deduped, key=lambda action: _LLM_ACTION_PRIORITY.index(action))
    return primary, deduped


def merge_llm_actions(
    primary: str,
    actions: list[str],
    *extra: str,
) -> tuple[str, list[str]]:
    """Tighten (never loosen) primary action by merging extra LLM actions."""
    if not extra:
        return primary, list(actions)
    merged = list(dict.fromkeys([*actions, *extra]))

    def _rank(action: str) -> int:
        try:
            return _LLM_ACTION_PRIORITY.index(action)
        except ValueError:
            return len(_LLM_ACTION_PRIORITY)

    return min(merged, key=_rank), merged


def summarize_recommended_action(
    permissions: SourcePermissions,
    subscores: SourceSubscores,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> str:
    """Backward-compatible summary action from permissions + subscores."""
    if permissions.retrieve_permission == "reject":
        return "reject"
    if permissions.retrieve_permission == "defer":
        return "defer_fetch"
    if permissions.endorsement_permission == "deny":
        if subscores.endorsement_risk >= config.endorsement_risk_downrank:
            return "block_endorsement"
        if subscores.rhetorical_manipulation >= 0.35:
            return "block_endorsement"
    if (
        permissions.retrieve_permission == "downrank"
        or subscores.endorsement_risk >= config.endorsement_risk_downrank
        or (
            subscores.rhetorical_manipulation >= config.downrank_risk_threshold
            and subscores.source_trust < config.downrank_trust_threshold
        )
    ):
        return "downrank"
    return "pass"


def apply_commercial_tightening(
    permissions: SourcePermissions,
    assessment: CommercialInfluenceAssessment,
) -> SourcePermissions:
    """Tighten base permissions using commercial influence assessment."""
    return tighten_permissions(permissions, assessment)


def derive_permissions_with_commercial(
    subscores: SourceSubscores,
    source: SourceScore,
    chunk_text: str,
    query: str | None,
    query_intent: str,
    query_context: QueryContextScores | None = None,
    fetch_failure_kind: str | None = None,
    has_persuasive_content: bool = False,
    config: DefenseConfig = DEFAULT_CONFIG,
    *,
    is_coordinated: bool = False,
) -> tuple[SourcePermissions, CommercialInfluenceAssessment]:
    """Derive permissions and apply commercial policy tightening."""
    base = derive_permissions(
        subscores,
        query_context=query_context,
        fetch_failure_kind=fetch_failure_kind,
        has_persuasive_content=has_persuasive_content,
        config=config,
    )
    assessment = assess_commercial_influence(
        source,
        chunk_text,
        query,
        query_intent,
        base,
        config,
        is_coordinated=is_coordinated,
    )
    return tighten_permissions(base, assessment), assessment
