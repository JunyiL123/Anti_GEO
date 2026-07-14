from __future__ import annotations

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.content_signals import chunk_endorses, query_wants_recommendation
from anti_geo.models import CommercialInfluenceAssessment, SourcePermissions, SourceScore
from anti_geo.subscores import compute_harm_severity

LABEL_TEXT_HIGH = (
    "This answer uses sources with disclosed commercial relationships "
    "(e.g. affiliate or sponsored content). Commercial ties do not necessarily "
    "mean the information is incorrect."
)
LABEL_TEXT_COORDINATED = (
    "Sources supporting this claim appear coordinated and include commercial content."
)
HEDGE_TEXT_MEDIUM = (
    "Note: some cited sources may have commercial interests in the topic discussed."
)

_TIER_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _tier_at_least(tier: str, minimum: str) -> bool:
    return _TIER_RANK.get(tier, 0) >= _TIER_RANK.get(minimum, 0)


def _resolve_tier(
    source: SourceScore,
    chunk_text: str,
) -> tuple[str, list[str]]:
    page_ctx = source.page_context
    if not page_ctx:
        return "none", []

    tier = page_ctx.commercial_tier
    triggers = list(page_ctx.commercial_triggers)

    content = source.content_signals
    if (
        "press_release" in page_ctx.flags
        and "comparative_superlatives" in content.flags
        and tier != "high"
    ):
        tier = "high"
        triggers.append("press_release_with_comparative_superlatives")

    if (
        "commercial_cta" in page_ctx.flags
        and chunk_endorses(chunk_text, content)
        and tier == "low"
    ):
        tier = "medium"
        triggers.append("commercial_cta_with_endorsement")

    return tier, triggers


def _is_shopping_intent(query_intent: str) -> bool:
    return query_intent in ("commercial", "navigational")


def assess_commercial_influence(
    source: SourceScore,
    chunk_text: str,
    query: str | None,
    query_intent: str,
    permissions: SourcePermissions,
    config: DefenseConfig = DEFAULT_CONFIG,
    *,
    is_coordinated: bool = False,
    defended_rank: int | None = None,
) -> CommercialInfluenceAssessment:
    """Evaluate commercial influence policy for one chunk."""
    tier, triggers = _resolve_tier(source, chunk_text)
    q_rec = query_wants_recommendation(query)
    endorses = chunk_endorses(chunk_text, source.content_signals)
    trust = source.trust_score
    harm = compute_harm_severity(query_intent)

    if is_coordinated and _tier_at_least(tier, config.commercial_hedge_min_tier):
        return CommercialInfluenceAssessment(
            tier=tier,
            triggers=triggers + ["coordinated_cluster"],
            retrieval_action="downrank",
            factual_action="deny",
            endorsement_action="deny",
            disclosure_level="label",
            disclosure_text=LABEL_TEXT_COORDINATED,
            response_mode="refuse_endorsement",
        )

    if _is_shopping_intent(query_intent):
        return CommercialInfluenceAssessment(
            tier=tier,
            triggers=triggers,
            disclosure_level="none",
        )

    retrieval_action: str | None = None
    factual_action: str | None = None
    endorsement_action: str | None = None
    disclosure_level = "none"
    disclosure_text = ""
    response_mode: str | None = None

    if tier == "high":
        retrieval_action = "downrank"
        factual_action = "attribute_only"
        endorsement_action = "deny" if endorses or q_rec else "deny" if endorses else None
        if endorses and q_rec:
            endorsement_action = "deny"
            response_mode = "refuse_endorsement" if trust < config.trust_endorsement_min else "attributed_answer"
        elif q_rec and not endorses and trust < config.trust_endorsement_min:
            endorsement_action = "deny"
            response_mode = "attributed_answer"
        else:
            if endorses:
                endorsement_action = "deny"
            response_mode = response_mode or "hedged_answer"

        in_top = defended_rank is not None and defended_rank <= 3
        if in_top or defended_rank == 1:
            disclosure_level = "label"
            disclosure_text = LABEL_TEXT_HIGH

        if harm >= 0.7 and trust < 0.45:
            factual_action = "deny"

    elif tier == "medium":
        if q_rec and endorses:
            endorsement_action = "deny"
            if trust < config.trust_endorsement_min:
                retrieval_action = "downrank"
            factual_action = "require_corroboration"
            disclosure_level = "hedge"
            disclosure_text = HEDGE_TEXT_MEDIUM
            response_mode = "hedged_answer"
        elif q_rec and endorses and trust >= config.trust_endorsement_min:
            endorsement_action = "deny"
            factual_action = "require_corroboration"
            disclosure_level = "hedge"
            disclosure_text = HEDGE_TEXT_MEDIUM
            response_mode = "hedged_answer"

    elif tier == "low":
        if not endorses:
            retrieval_action = "downrank" if permissions.retrieve_permission == "allow" else None

    if (
        tier == "none"
        and "planted_mention" in source.content_signals.flags
        and q_rec
        and not endorses
    ):
        endorsement_action = "deny"
        response_mode = response_mode or "attributed_answer"

    return CommercialInfluenceAssessment(
        tier=tier,
        triggers=triggers,
        retrieval_action=retrieval_action,
        factual_action=factual_action,
        endorsement_action=endorsement_action,
        disclosure_level=disclosure_level,
        disclosure_text=disclosure_text,
        response_mode=response_mode,
    )


_PERMISSION_STRENGTH = {
    "retrieve": {"allow": 0, "downrank": 1, "defer": 2, "reject": 3},
    "mention": {"allow": 0, "deny": 1},
    "factual": {"allow": 0, "attribute_only": 1, "require_corroboration": 2, "deny": 3},
    "endorsement": {"allow": 0, "deny": 1},
}


def _tighten(current: str, proposed: str | None, strength_map: dict[str, int]) -> str:
    if not proposed:
        return current
    if strength_map.get(proposed, 0) > strength_map.get(current, 0):
        return proposed
    return current


def tighten_permissions(
    permissions: SourcePermissions,
    assessment: CommercialInfluenceAssessment,
) -> SourcePermissions:
    """Apply commercial policy — only tighten, never loosen."""
    return SourcePermissions(
        retrieve_permission=_tighten(
            permissions.retrieve_permission,
            assessment.retrieval_action,
            _PERMISSION_STRENGTH["retrieve"],
        ),
        mention_permission=permissions.mention_permission,
        factual_permission=_tighten(
            permissions.factual_permission,
            assessment.factual_action,
            _PERMISSION_STRENGTH["factual"],
        ),
        endorsement_permission=_tighten(
            permissions.endorsement_permission,
            assessment.endorsement_action,
            _PERMISSION_STRENGTH["endorsement"],
        ),
    )
