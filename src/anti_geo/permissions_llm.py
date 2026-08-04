"""Azure LLM nuance pass for ambiguous single-page permissions.

Heuristic ``derive_permissions`` stays the cheap prior. On gated ambiguous
pages (and only when concealment is not hot), optionally ask Azure to
**re-apply Anti-GEO heuristic permission rules with page-reading nuance** —
not to act as an independent human labeler. Passes already-fetched identity /
domain fields; optional Bing ``web_search`` (auto, soft-capped) only for
ownership / reputation / corroboration gaps. Merge is bidirectional under
hard IPI/fetch floors. Untrusted excerpts are spotlight-fenced.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from anti_geo.azure_client import (
    is_azure_configured,
    load_azure_config,
    responses_json_with_optional_web_search,
)
from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.content_signals import chunk_endorses
from anti_geo.models import SourcePermissions, SourceScore, SourceSubscores
from anti_geo.permissions import (
    CONCEALMENT_DOWNRANK,
    CONCEALMENT_REJECT,
    FETCH_CONFIDENCE_DEFER,
    INTENT_MISMATCH_DOWNRANK,
    SHOPPING_LISTICLE_ROLES,
    soft_fetch_floor,
    permissions_heuristic_rules_rubric,
)
from anti_geo.platform_role import classify_content_role

logger = logging.getLogger(__name__)

_LLM_EXCERPT = 2000

# Match permissions.py concealment elevate / reject bands.
CONCEALMENT_SKIP_LLM = CONCEALMENT_DOWNRANK
CONCEALMENT_HARD_REJECT = CONCEALMENT_REJECT

RETRIEVE_VALUES = frozenset({"allow", "downrank", "defer", "reject"})
MENTION_VALUES = frozenset({"allow", "deny"})
FACTUAL_VALUES = frozenset({"allow", "attribute_only", "require_corroboration", "deny"})
ENDORSE_VALUES = frozenset({"allow", "deny"})

UNTRUSTED_START = "<<<UNTRUSTED_PAGE>>>"
UNTRUSTED_END = "<<<END_UNTRUSTED_PAGE>>>"


@dataclass(frozen=True)
class PermissionsLlmSuggestion:
    retrieve_permission: str | None = None
    mention_permission: str | None = None
    factual_permission: str | None = None
    endorsement_permission: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class PermissionsLlmResult:
    permissions: SourcePermissions
    source: str  # heuristic | llm_hybrid
    reason: str = ""
    skipped: str = ""  # why LLM was not applied


def concealment_is_hot(
    subscores: SourceSubscores | None,
    *,
    threshold: float = CONCEALMENT_SKIP_LLM,
) -> bool:
    if subscores is None:
        return False
    return float(subscores.concealment_risk) >= threshold


def concealment_is_hard(
    subscores: SourceSubscores | None,
) -> bool:
    """True only for hard IPI reject band (>=0.9) — full heuristic freeze."""
    return concealment_is_hot(subscores, threshold=CONCEALMENT_HARD_REJECT)


def concealment_is_soft(
    subscores: SourceSubscores | None,
) -> bool:
    """Soft concealment [0.5, 0.9) — still allow endorse-tighten LLM."""
    if subscores is None:
        return False
    risk = float(subscores.concealment_risk)
    return CONCEALMENT_SKIP_LLM <= risk < CONCEALMENT_HARD_REJECT


def has_permissions_hard_floor(
    heuristic: SourcePermissions,
    subscores: SourceSubscores | None,
    fetch_failure_kind: str | None,
) -> bool:
    """IPI/fetch reject floors that the LLM must not loosen."""
    if fetch_failure_kind == "reject":
        return True
    if heuristic.retrieve_permission == "reject":
        return True
    if subscores is not None and subscores.concealment_risk >= CONCEALMENT_HARD_REJECT:
        return True
    return False


def _shopping_intent(query_intent: str) -> bool:
    return query_intent in ("commercial", "navigational")


def _commercialish(source: SourceScore) -> bool:
    ctx = source.page_context
    if ctx is None:
        return False
    if ctx.has_affiliate_links:
        return True
    if ctx.commercial_tier in ("medium", "high"):
        return True
    if ctx.commercial_context_score > 0.45:
        return True
    flags = set(ctx.flags or [])
    if "affiliate_link_params" in flags or "commercial_cta" in flags:
        return True
    return False


def _persuasive(source: SourceScore) -> bool:
    flags = source.content_signals.flags
    if "comparative_superlatives" in flags or "authority_stacking" in flags:
        return True
    if source.content_signals.comparative_density > DEFAULT_CONFIG.comparative_flag_threshold:
        return True
    return chunk_endorses(source.text_excerpt or "", source.content_signals)


def _high_trust(source: SourceScore, config: DefenseConfig) -> bool:
    if source.trust_score >= config.trust_institutional:
        return True
    host = (source.domain_signals.hostname or "").lower()
    if host.endswith(".gov") or host.endswith(".edu"):
        return True
    return source.trust_score >= 0.7


def _content_role(source: SourceScore) -> str:
    return classify_content_role(source.url, source=source)


def permissions_llm_gate(
    source: SourceScore,
    query: str | None,
    query_intent: str,
    heuristic: SourcePermissions,
    subscores: SourceSubscores | None,
    *,
    fetch_failure_kind: str | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> bool:
    """True only for ambiguous single-page cases (never a blanket LLM pass).

    Ambiguous := heuristics are likely blunt on this row, especially:
    - shopping query where endorse was allowed (commercial endorsement_risk≈0 hole)
    - shopping + affiliate/listicle/commercial page packaging
    - shopping + institutional/high-trust (facts vs shopping endorse)
    - vendorish page with factual=allow (self-serve claims)

    Never call when fetch/IPI hard floor or concealment is already hard-hot (>=0.9).
    Soft concealment [0.5, 0.9) may still open for endorse-tighten.
    """
    if fetch_failure_kind in ("reject", "defer"):
        return False
    if not source.fetch_ok:
        return False
    if concealment_is_hard(subscores):
        return False
    if has_permissions_hard_floor(heuristic, subscores, fetch_failure_kind):
        return False

    shopping = _shopping_intent(query_intent)
    commercialish = _commercialish(source)
    persuasive = _persuasive(source)
    high_trust = _high_trust(source, config)
    role = _content_role(source)
    vendorish = role == "commercial_product" or commercialish

    # Soft concealment on shopping rows: reopen LLM so endorse can tighten.
    if concealment_is_soft(subscores) and shopping:
        return True

    # Primary: commercial endorse over-allow hole.
    if shopping and heuristic.endorsement_permission == "allow":
        return True
    # Shopping + commerce/listicle packaging.
    if shopping and commercialish:
        return True
    if shopping and role in ("expert_listicle", "editorial", "review_profile"):
        return True
    # Shopping + institutional / high trust (FDA-on-shopping style).
    if shopping and high_trust:
        return True
    # Non-shopping but endorse allow with persuasive/commercial cues.
    if heuristic.endorsement_permission == "allow" and (persuasive or commercialish):
        return True
    # Vendor self-claims marked factual allow.
    if heuristic.factual_permission == "allow" and vendorish:
        return True
    _ = query
    return False


def build_permissions_llm_messages(
    *,
    query: str | None,
    query_intent: str,
    source: SourceScore,
    heuristic: SourcePermissions,
    subscores: SourceSubscores | None = None,
    content_role: str | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
    has_persuasive_content: bool | None = None,
) -> list[dict[str, str]]:
    """Build spotlight-fenced chat messages with heuristic rules + live subscores."""
    role = content_role or _content_role(source)
    ctx = source.page_context
    tier = ctx.commercial_tier if ctx else "none"
    affiliate = bool(ctx and ctx.has_affiliate_links)
    persuasive = (
        _persuasive(source) if has_persuasive_content is None else has_persuasive_content
    )
    identity = source.identity
    site_name = (identity.site_name if identity else "") or ""
    organization = (identity.organization if identity else "") or ""
    brand = (identity.brand if identity else "") or ""
    product = (identity.product if identity else "") or ""
    aliases = [
        a for a in (list(identity.aliases) if identity and identity.aliases else []) if a
    ][:12]
    alias_line = ", ".join(aliases) if aliases else "(none)"
    ds = source.domain_signals
    whois = ds.whois_age_days if ds.whois_age_days is not None else "unknown"
    cert = ds.cert_age_days if ds.cert_age_days is not None else "unknown"
    excerpt = (source.text_excerpt or "").strip()[:_LLM_EXCERPT]
    fenced = (
        f"{UNTRUSTED_START}\n"
        f"url: {source.url}\n"
        f"title_hint: {site_name or '(none)'}\n"
        f"excerpt:\n{excerpt or '(empty)'}\n"
        f"{UNTRUSTED_END}"
    )
    if subscores is not None:
        sub_line = (
            f"heuristic_subscores: "
            f"fetch_confidence={subscores.fetch_confidence:.3f}, "
            f"source_trust={subscores.source_trust:.3f}, "
            f"rhetorical_manipulation={subscores.rhetorical_manipulation:.3f}, "
            f"retrieval_manipulation_risk={subscores.retrieval_manipulation_risk:.3f}, "
            f"endorsement_risk={subscores.endorsement_risk:.3f}, "
            f"factual_claim_reliability={subscores.factual_claim_reliability:.3f}, "
            f"intent_mismatch={subscores.intent_mismatch:.3f}, "
            f"harm_severity={subscores.harm_severity:.3f}, "
            f"concealment_risk={subscores.concealment_risk:.3f}"
        )
    else:
        sub_line = "heuristic_subscores: (unavailable)"
    user = (
        f"query: {query or '(none)'}\n"
        f"query_intent: {query_intent}\n"
        f"content_role: {role}\n"
        f"commercial_tier: {tier}\n"
        f"has_affiliate_links: {affiliate}\n"
        f"has_persuasive_content: {persuasive}\n"
        f"page_source_trust: {source.trust_score:.3f}\n"
        f"identity_site_name: {site_name or '(none)'}\n"
        f"identity_organization: {organization or '(none)'}\n"
        f"identity_brand: {brand or '(none)'}\n"
        f"identity_product: {product or '(none)'}\n"
        f"identity_aliases: {alias_line}\n"
        f"domain_hostname: {ds.hostname or '(none)'}\n"
        f"domain_tld: {ds.tld or '(none)'}\n"
        f"domain_whois_age_days: {whois}\n"
        f"domain_cert_age_days: {cert}\n"
        f"{sub_line}\n"
        f"heuristic_permissions (prior): "
        f"retrieve={heuristic.retrieve_permission}, "
        f"mention={heuristic.mention_permission}, "
        f"factual={heuristic.factual_permission}, "
        f"endorsement={heuristic.endorsement_permission}\n\n"
        f"{fenced}"
    )
    return [
        {"role": "system", "content": permissions_heuristic_rules_rubric(config)},
        {"role": "user", "content": user},
    ]


def _parse_optional_enum(raw: object, allowed: frozenset[str]) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if value in ("", "null", "none"):
        return None
    if value not in allowed:
        return None
    return value


def parse_permissions_llm_payload(payload: dict) -> PermissionsLlmSuggestion | None:
    if not isinstance(payload, dict):
        return None
    suggestion = PermissionsLlmSuggestion(
        retrieve_permission=_parse_optional_enum(
            payload.get("retrieve_permission"), RETRIEVE_VALUES
        ),
        mention_permission=_parse_optional_enum(
            payload.get("mention_permission"), MENTION_VALUES
        ),
        factual_permission=_parse_optional_enum(
            payload.get("factual_permission"), FACTUAL_VALUES
        ),
        endorsement_permission=_parse_optional_enum(
            payload.get("endorsement_permission"), ENDORSE_VALUES
        ),
        reason=" ".join(str(payload.get("reason") or "").split())[:240],
    )
    if (
        suggestion.retrieve_permission is None
        and suggestion.mention_permission is None
        and suggestion.factual_permission is None
        and suggestion.endorsement_permission is None
    ):
        return None
    return suggestion


def suggest_permissions_llm(
    *,
    query: str | None,
    query_intent: str,
    source: SourceScore,
    heuristic: SourcePermissions,
    subscores: SourceSubscores | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
    content_role: str | None = None,
) -> PermissionsLlmSuggestion | None:
    messages = build_permissions_llm_messages(
        query=query,
        query_intent=query_intent,
        source=source,
        heuristic=heuristic,
        subscores=subscores,
        content_role=content_role,
        config=config,
    )
    payload = responses_json_with_optional_web_search(
        messages, config=load_azure_config()
    )
    return parse_permissions_llm_payload(payload)


def merge_permissions_hybrid(
    heuristic: SourcePermissions,
    suggestion: PermissionsLlmSuggestion | None,
    *,
    hard_floor: bool,
    endorse_tighten_only: bool = False,
    protect_listicle_retrieve_allow: bool = False,
    protect_heuristic_retrieve_downrank: bool = False,
    protect_listicle_factual_attribute_only: bool = False,
    protect_review_factual_no_allow: bool = False,
    protect_heuristic_endorsement_deny: bool = False,
) -> SourcePermissions:
    """Bidirectional field merge; hard IPI/fetch floors keep heuristic.

    When ``endorse_tighten_only`` (soft concealment), only endorsement may
    change, and only allow→deny (tighten).

    When ``protect_listicle_retrieve_allow``, shopping listicle/review with
    heuristic retrieve=allow keeps allow (LLM may still change endorse/factual).

    When ``protect_heuristic_retrieve_downrank``, LLM cannot loosen heuristic
    retrieve=downrank → allow (shopping/brand-legit vendor path).

    When ``protect_listicle_factual_attribute_only``, shopping listicle/review
    heuristic factual in {allow, attribute_only} cannot escalate to
    require_corroboration/deny. Allow→attribute_only tightening is accepted.

    When ``protect_review_factual_no_allow``, shopping listicle/review/factual_blog
    with heuristic factual=attribute_only cannot loosen to allow.

    When ``protect_heuristic_endorsement_deny``, LLM cannot loosen heuristic
    endorsement=deny → allow.
    """
    if suggestion is None or hard_floor:
        return heuristic

    if endorse_tighten_only:
        endorse = heuristic.endorsement_permission
        if (
            suggestion.endorsement_permission == "deny"
            and heuristic.endorsement_permission == "allow"
        ):
            endorse = "deny"
        return SourcePermissions(
            retrieve_permission=heuristic.retrieve_permission,
            mention_permission=heuristic.mention_permission,
            factual_permission=heuristic.factual_permission,
            endorsement_permission=endorse,
        )

    retrieve = (
        suggestion.retrieve_permission
        if suggestion.retrieve_permission is not None
        else heuristic.retrieve_permission
    )
    if (
        protect_listicle_retrieve_allow
        and heuristic.retrieve_permission == "allow"
        and retrieve in ("downrank", "defer", "reject")
    ):
        retrieve = "allow"
    if (
        protect_heuristic_retrieve_downrank
        and heuristic.retrieve_permission == "downrank"
        and retrieve == "allow"
    ):
        retrieve = "downrank"

    factual = (
        suggestion.factual_permission
        if suggestion.factual_permission is not None
        else heuristic.factual_permission
    )
    if (
        protect_listicle_factual_attribute_only
        and heuristic.factual_permission in ("allow", "attribute_only")
        and factual in ("require_corroboration", "deny")
    ):
        factual = heuristic.factual_permission
    if (
        protect_review_factual_no_allow
        and heuristic.factual_permission == "attribute_only"
        and factual == "allow"
    ):
        factual = "attribute_only"

    endorse = (
        suggestion.endorsement_permission
        if suggestion.endorsement_permission is not None
        else heuristic.endorsement_permission
    )
    if (
        protect_heuristic_endorsement_deny
        and heuristic.endorsement_permission == "deny"
        and endorse == "allow"
    ):
        endorse = "deny"

    return SourcePermissions(
        retrieve_permission=retrieve,
        mention_permission=(
            suggestion.mention_permission
            if suggestion.mention_permission is not None
            else heuristic.mention_permission
        ),
        factual_permission=factual,
        endorsement_permission=endorse,
    )


def _brand_legit_query(query: str | None) -> bool:
    if not query or not str(query).strip():
        return False
    # Keep in sync with permissions._BRAND_LEGIT_QUERY_RE
    import re

    return bool(
        re.search(
            r"\b(legit|scam|trustworthy|safe\s+to\s+buy|good\s+brand|real\s+brand|"
            r"worth\s+it|trusted)\b",
            str(query),
            re.I,
        )
    )


def maybe_apply_permissions_llm(
    source: SourceScore,
    heuristic: SourcePermissions,
    subscores: SourceSubscores | None,
    *,
    query: str | None,
    query_intent: str,
    fetch_failure_kind: str | None = None,
    use_llm: bool | None = False,
    config: DefenseConfig = DEFAULT_CONFIG,
    content_role: str | None = None,
) -> PermissionsLlmResult:
    """Heuristic prior, optional Azure nuance on ambiguous rows only; fail-open."""
    # Hard concealment (>=0.9): full freeze. Soft [0.5, 0.9) may still tighten endorse.
    if concealment_is_hard(subscores):
        return PermissionsLlmResult(
            permissions=heuristic,
            source="heuristic",
            skipped="concealment_hot",
            reason="Concealment hard-hot — keep heuristic permissions.",
        )
    hard = has_permissions_hard_floor(heuristic, subscores, fetch_failure_kind)
    if hard:
        return PermissionsLlmResult(
            permissions=heuristic,
            source="heuristic",
            skipped="hard_floor",
            reason="Hard fetch/IPI floor — keep heuristic permissions.",
        )

    llm_enabled = is_azure_configured() if use_llm is None else bool(use_llm)
    if not llm_enabled:
        return PermissionsLlmResult(
            permissions=heuristic,
            source="heuristic",
            skipped="llm_disabled",
            reason="Permissions LLM disabled or Azure not configured.",
        )

    role = (content_role or _content_role(source)).strip()
    # Soft-fetch floor: successful high-trust/UGC/institutional fetch with low
    # confidence — keep heuristic (do not let LLM re-defer/deny).
    if (
        fetch_failure_kind is None
        and source.fetch_ok
        and subscores is not None
        and float(subscores.fetch_confidence) < FETCH_CONFIDENCE_DEFER
        and soft_fetch_floor(
            content_role=role,
            source_trust=float(subscores.source_trust),
            fetch_failure_kind=fetch_failure_kind,
        )
    ):
        return PermissionsLlmResult(
            permissions=heuristic,
            source="heuristic",
            skipped="soft_fetch_floor",
            reason="Soft-fetch floor — keep heuristic permissions.",
        )

    if not permissions_llm_gate(
        source,
        query,
        query_intent,
        heuristic,
        subscores,
        fetch_failure_kind=fetch_failure_kind,
        config=config,
    ):
        return PermissionsLlmResult(
            permissions=heuristic,
            source="heuristic",
            skipped="not_ambiguous",
            reason="Heuristic permissions confident; outside LLM ambiguity gate.",
        )

    endorse_tighten_only = concealment_is_soft(subscores)
    shopping = _shopping_intent(query_intent)
    brand_legit = _brand_legit_query(query)
    intent_ok = (
        subscores is None
        or float(subscores.intent_mismatch) < INTENT_MISMATCH_DOWNRANK
    )
    protect_listicle_retrieve_allow = (
        shopping
        and role in SHOPPING_LISTICLE_ROLES
        and heuristic.retrieve_permission == "allow"
        and intent_ok
        and not concealment_is_hard(subscores)
    )
    protect_heuristic_retrieve_downrank = (
        heuristic.retrieve_permission == "downrank"
        and role == "commercial_product"
        and (shopping or brand_legit)
    )
    # Hard clamps: block invent-require/deny on shopping listicle/review when
    # heuristic is allow/attribute_only; allow→AO tightening is accepted.
    # Block AO→allow loosen on listicle/review/factual_blog.
    protect_listicle_factual_attribute_only = (
        shopping
        and role in SHOPPING_LISTICLE_ROLES
        and heuristic.factual_permission in ("allow", "attribute_only")
    )
    protect_review_factual_no_allow = (
        shopping
        and role in (*SHOPPING_LISTICLE_ROLES, "factual_blog")
        and heuristic.factual_permission == "attribute_only"
    )
    # Endorsement deny is the paper dial — LLM may tighten allow→deny only.
    protect_heuristic_endorsement_deny = (
        heuristic.endorsement_permission == "deny"
    )

    try:
        suggestion = suggest_permissions_llm(
            query=query,
            query_intent=query_intent,
            source=source,
            heuristic=heuristic,
            subscores=subscores,
            config=config,
            content_role=content_role,
        )
    except Exception as exc:
        logger.warning("permissions LLM failed open: %s", exc)
        return PermissionsLlmResult(
            permissions=heuristic,
            source="heuristic",
            skipped="llm_error",
            reason=f"Permissions LLM error (kept heuristic): {exc}",
        )

    merged = merge_permissions_hybrid(
        heuristic,
        suggestion,
        hard_floor=False,
        endorse_tighten_only=endorse_tighten_only,
        protect_listicle_retrieve_allow=protect_listicle_retrieve_allow,
        protect_heuristic_retrieve_downrank=protect_heuristic_retrieve_downrank,
        protect_listicle_factual_attribute_only=protect_listicle_factual_attribute_only,
        protect_review_factual_no_allow=protect_review_factual_no_allow,
        protect_heuristic_endorsement_deny=protect_heuristic_endorsement_deny,
    )
    reason = (suggestion.reason if suggestion else "") or (
        "Soft-concealment endorse-tighten hybrid."
        if endorse_tighten_only
        else "LLM hybrid permissions applied."
    )
    return PermissionsLlmResult(
        permissions=merged,
        source="llm_hybrid",
        reason=reason,
    )
