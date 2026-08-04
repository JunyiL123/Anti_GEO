"""Azure LLM nuance pass for ambiguous Mode B parasitic GEO tier.

Structural ``discover_referrers`` stays the cheap prior. On gated ambiguous
profiles, optionally ask Azure to re-apply Mode B parasitic rules with
web research about the *cited* brand/site (GEO/SEO plants, fake forums,
unethical ranking) — not as an independent labeler. Soft Bing cap via
``tool_choice=auto``. Merge under hard floors; fail-open on errors.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from anti_geo.azure_client import (
    is_azure_configured,
    load_azure_config,
    responses_json_with_optional_web_search,
)
from anti_geo.investigation import (
    BRAND_SELF_ELEVATED_RISK,
    BRAND_SELF_MAX_N,
    PARASITIC_GEO_ELEVATED_COUNT_HIGH_CONF_MIN,
    PARASITIC_GEO_RISK_ELEVATED,
    high_conf_parasitic_count_from_verified,
    is_vendor_like_target,
    parasitic_heuristic_rules_rubric,
)
from anti_geo.platform_role import is_parasitic_referrer, is_ugc_role

logger = logging.getLogger(__name__)

_MAX_REFERRER_SUMMARIES = 8
_DEFAULT_PARASITIC_JUDGE_MAX_TOOL_CALLS = 3

# Ambiguity bands for when to call the LLM (not Mode B convictors).
MID_RISK_LO = 0.20
MID_RISK_HI = 0.55
THIN_N_MAX = 5
CONFIDENT_N_MIN = 6
CONFIDENT_RISK_MIN = 0.65

PARASITIC_VALUES = frozenset({"none", "elevated", "suspected"})

# Kept for tests / docs; N=0 gate no longer role-restricted.
N0_COMMERCIAL_ROLES = frozenset(
    {
        "commercial_product",
        "expert_listicle",
        "review_profile",
    }
)
N0_SKIP_ROLES = frozenset({"institutional", "editorial"})

UNTRUSTED_START = "<<<UNTRUSTED_REFERRAL>>>"
UNTRUSTED_END = "<<<END_UNTRUSTED_REFERRAL>>>"


def parasitic_judge_max_tool_calls() -> int:
    """Soft Bing cap for parasitic judge (default 3); N=0 research soft cap 2–3."""
    raw = os.environ.get("AZURE_PARASITIC_JUDGE_MAX_TOOL_CALLS", "").strip()
    if not raw:
        return _DEFAULT_PARASITIC_JUDGE_MAX_TOOL_CALLS
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_PARASITIC_JUDGE_MAX_TOOL_CALLS


def _heuristic_rules_rubric() -> str:
    """System rubric from investigation.py Mode B thresholds + LLM-gate bands."""
    return parasitic_heuristic_rules_rubric(
        mid_risk_lo=MID_RISK_LO,
        mid_risk_hi=MID_RISK_HI,
        thin_n_max=THIN_N_MAX,
    )


@dataclass(frozen=True)
class ParasiticLlmSuggestion:
    parasitic: str | None = None  # none | elevated | suspected | None(=keep)
    reason: str = ""


@dataclass(frozen=True)
class ParasiticLlmResult:
    source: str  # heuristic | llm_hybrid
    reason: str = ""
    skipped: str = ""


def heuristic_parasitic_tier(profile: Any) -> str:
    if profile.parasitic_geo_suspected is True:
        return "suspected"
    if profile.parasitic_geo_elevated or profile.status == "sparse_suspicious":
        return "elevated"
    return "none"


def editorial_count_from_profile(profile: Any) -> int:
    mix = profile.mix or {}
    return int(mix.get("editorial", 0)) + int(mix.get("institutional", 0))


def has_parasitic_hard_floor(
    profile: Any,
    *,
    editorial_count: int | None = None,
) -> bool:
    """Structural hard convict the LLM must not loosen."""
    ed = (
        editorial_count
        if editorial_count is not None
        else editorial_count_from_profile(profile)
    )
    return (
        profile.parasitic_geo_suspected is True
        and profile.n_verified >= CONFIDENT_N_MIN
        and float(profile.parasitic_geo_risk) >= CONFIDENT_RISK_MIN
        and ed == 0
    )


def is_confident_structural(profile: Any) -> bool:
    """High N + high risk elevated/suspected — not an ambiguity call by itself."""
    if profile.n_verified < CONFIDENT_N_MIN:
        return False
    if float(profile.parasitic_geo_risk) < CONFIDENT_RISK_MIN:
        return False
    return bool(
        profile.parasitic_geo_suspected is True
        or profile.parasitic_geo_elevated
        or profile.status == "sparse_suspicious"
    )


def parasitic_llm_gate(
    profile: Any,
    *,
    content_role: str | None = None,
    fetch_ok: bool = True,
    fetch_failure_kind: str | None = None,
) -> bool:
    """True only for ambiguous Mode B rows (never a blanket LLM pass)."""
    # Align with permissions hybrid: no page body → don't invent brand research.
    if fetch_failure_kind in ("reject", "defer") or not fetch_ok:
        return False
    if profile.discovery_status == "skipped" or profile.status == "skipped":
        return False

    n = int(profile.n_verified or 0)
    risk = float(profile.parasitic_geo_risk or 0.0)
    elev = bool(profile.parasitic_geo_elevated)
    sus = profile.parasitic_geo_suspected
    status = profile.status or ""
    role = (content_role or "").strip()

    if MID_RISK_LO <= risk <= MID_RISK_HI:
        return True

    if 1 <= n <= THIN_N_MAX and (
        elev or risk >= PARASITIC_GEO_RISK_ELEVATED or status == "sparse_suspicious"
    ):
        return True

    if sus is None:
        return True

    # After seed rounds, N=0 is always ambiguous — any content role.
    if n == 0:
        return True

    return False


def _referrer_summaries(profile: Any) -> list[str]:
    lines: list[str] = []
    for ref in (profile.referrers_verified or [])[:_MAX_REFERRER_SUMMARIES]:
        parasitic = is_parasitic_referrer(
            url=ref.url,
            role=ref.role,
            content_high_risk=ref.content_high_risk,
            llm_parasitic=ref.llm_parasitic,
        )
        lines.append(
            f"- url={ref.url} role={ref.role} connection={ref.connection} "
            f"llm_parasitic={ref.llm_parasitic} content_high_risk={ref.content_high_risk} "
            f"counts_parasitic={parasitic}"
        )
    return lines


def build_parasitic_llm_messages(
    profile: Any,
    *,
    target_url: str,
    content_role: str | None = None,
    metadata: Any | None = None,
) -> list[dict[str, str]]:
    from anti_geo.investigation import (
        high_conf_parasitic_count_from_verified,
        parasitic_count_from_verified,
        parasitic_share_from_verified,
    )

    n = int(profile.n_verified or 0)
    share = parasitic_share_from_verified(profile.referrers_verified)
    pcount = parasitic_count_from_verified(profile.referrers_verified)
    hconf = high_conf_parasitic_count_from_verified(profile.referrers_verified)
    editorial = editorial_count_from_profile(profile)
    prior = heuristic_parasitic_tier(profile)
    entity = (metadata.entity if metadata else "") or ""
    org = (metadata.org if metadata else "") or ""
    aliases = list(metadata.aliases) if metadata and metadata.aliases else []
    alias_line = ", ".join(aliases[:12]) if aliases else "(none)"
    sa = profile.semantic_alignment
    align_line = (
        f"{sa.label} (referrer_commercial_share={sa.referrer_commercial_share:.3f})"
        if sa
        else "(none)"
    )
    ref_block = "\n".join(_referrer_summaries(profile)) or "(none)"
    notes = "; ".join(profile.notes[:6]) if profile.notes else "(none)"
    fenced = (
        f"{UNTRUSTED_START}\n"
        f"verified_referrer_summaries:\n{ref_block}\n"
        f"notes: {notes}\n"
        f"{UNTRUSTED_END}"
    )
    user = (
        f"target_url: {target_url}\n"
        f"content_role: {content_role or '(none)'}\n"
        f"identity_entity: {entity or '(none)'}\n"
        f"identity_org: {org or '(none)'}\n"
        f"identity_aliases: {alias_line}\n"
        f"referral_status: {profile.status}\n"
        f"discovery_status: {profile.discovery_status}\n"
        f"n_verified: {n}\n"
        f"parasitic_count: {pcount}\n"
        f"parasitic_share: {share if share is not None else 0.0}\n"
        f"high_conf_parasitic_count: {hconf}\n"
        f"editorial_institutional_count: {editorial}\n"
        f"parasitic_geo_risk: {float(profile.parasitic_geo_risk):.4f}\n"
        f"heuristic_prior: parasitic={prior} "
        f"suspected={profile.parasitic_geo_suspected!r} "
        f"elevated={profile.parasitic_geo_elevated}\n"
        f"semantic_alignment: {align_line}\n"
        f"verified_mix: {profile.mix or {}}\n\n"
        f"{fenced}"
    )
    return [
        {"role": "system", "content": _heuristic_rules_rubric()},
        {"role": "user", "content": user},
    ]


def parse_parasitic_llm_payload(payload: dict) -> ParasiticLlmSuggestion | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("parasitic")
    reason = str(payload.get("reason") or "").strip()
    if raw is None:
        return ParasiticLlmSuggestion(parasitic=None, reason=reason)
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if value in ("", "null"):
        return ParasiticLlmSuggestion(parasitic=None, reason=reason)
    if value not in PARASITIC_VALUES:
        return None
    return ParasiticLlmSuggestion(parasitic=value, reason=reason)


def suggest_parasitic_llm(
    profile: Any,
    *,
    target_url: str,
    content_role: str | None = None,
    metadata: Any | None = None,
) -> ParasiticLlmSuggestion | None:
    messages = build_parasitic_llm_messages(
        profile,
        target_url=target_url,
        content_role=content_role,
        metadata=metadata,
    )
    payload = responses_json_with_optional_web_search(
        messages,
        config=load_azure_config(),
        max_tool_calls=parasitic_judge_max_tool_calls(),
    )
    return parse_parasitic_llm_payload(payload)


def _apply_tier_flags(profile: Any, tier: str) -> None:
    if tier == "suspected":
        profile.parasitic_geo_suspected = True
        profile.parasitic_geo_elevated = False
    elif tier == "elevated":
        profile.parasitic_geo_suspected = False
        profile.parasitic_geo_elevated = True
    else:
        profile.parasitic_geo_suspected = False
        profile.parasitic_geo_elevated = False


def has_brand_self_elevated_floor(
    profile: Any,
    *,
    content_role: str | None = None,
    query: str | None = None,
) -> bool:
    """True when brand-self prior applies — LLM must not loosen to none.

    Fires on the brand-self note (even if ``elevated`` was race-cleared), or
    when structural pattern matches: commercial_product + brand-legit query +
    thin N + risk at/above the brand-self prior.
    """
    notes = getattr(profile, "notes", None) or []
    if any("Brand-self elevated" in str(n) for n in notes):
        return True

    role = (content_role or "").strip()
    if role != "commercial_product":
        return False
    n = int(getattr(profile, "n_verified", 0) or 0)
    if n > BRAND_SELF_MAX_N:
        return False
    risk = float(getattr(profile, "parasitic_geo_risk", 0.0) or 0.0)
    if risk + 1e-9 < BRAND_SELF_ELEVATED_RISK:
        return False
    from anti_geo.investigation import _is_brand_legit_query

    return bool(_is_brand_legit_query(query))


def sparse_clean_ugc_force_none(profile: Any) -> bool:
    """True when sparse_suspicious is surface-only (clean UGC, no plant density).

    Prefer parasitic=none over elevated: legit forum indexes can look parasitic
    by role mix without high-conf planted content.
    """
    if (getattr(profile, "status", None) or "") != "sparse_suspicious":
        return False
    refs = getattr(profile, "referrers_verified", None) or []
    if not refs:
        return False
    if high_conf_parasitic_count_from_verified(refs) > 0:
        return False
    for ref in refs:
        if bool(getattr(ref, "content_high_risk", False)):
            return False
        if bool(getattr(ref, "llm_parasitic", False)):
            return False
        role = (getattr(ref, "role", None) or "").strip()
        if not is_ugc_role(role):
            return False
    return True


def merge_parasitic_hybrid(
    profile: Any,
    suggestion: ParasiticLlmSuggestion | None,
    *,
    hard_floor: bool,
    content_role: str | None = None,
    query: str | None = None,
    target_commercial_tier: str = "none",
) -> str | None:
    """Apply suggestion onto profile flags. Returns applied tier or None if kept."""
    if suggestion is None or suggestion.parasitic is None:
        return None

    tier = suggestion.parasitic
    if profile.n_verified == 0 and tier == "suspected":
        tier = "elevated"

    if hard_floor and tier in ("none", "elevated"):
        tier = "suspected"

    # Brand-self elevated is a deliberate thin-N prior; LLM may raise to
    # suspected only with verified plants, never loosen to none.
    if (
        has_brand_self_elevated_floor(
            profile, content_role=content_role, query=query
        )
        and tier == "none"
    ):
        tier = "elevated"

    # Clean sparse UGC hubs without plant density: do not convict elevated.
    if tier == "elevated" and sparse_clean_ugc_force_none(profile):
        tier = "none"

    # Vendor-like heuristic-none: LLM may not raise to elevated without plants.
    heuristic_none = (
        profile.parasitic_geo_suspected is not True
        and not profile.parasitic_geo_elevated
        and profile.status != "sparse_suspicious"
    )
    if (
        tier == "elevated"
        and heuristic_none
        and is_vendor_like_target(content_role or "", target_commercial_tier)
    ):
        hconf = high_conf_parasitic_count_from_verified(
            list(profile.referrers_verified or [])
        )
        n = int(profile.n_verified or 0)
        if hconf < PARASITIC_GEO_ELEVATED_COUNT_HIGH_CONF_MIN or n <= 2:
            tier = "none"

    _apply_tier_flags(profile, tier)
    return tier


def maybe_apply_parasitic_llm(
    profile: Any,
    *,
    target_url: str,
    content_role: str | None = None,
    metadata: Any | None = None,
    query: str | None = None,
    use_llm: bool | None = None,
    fetch_ok: bool = True,
    fetch_failure_kind: str | None = None,
    target_commercial_tier: str = "none",
) -> ParasiticLlmResult:
    """Heuristic prior, optional Azure nuance on ambiguous Mode B rows; fail-open."""
    hard = has_parasitic_hard_floor(profile)
    llm_enabled = is_azure_configured() if use_llm is None else bool(use_llm)
    if not llm_enabled:
        profile.parasitic_source = "heuristic"
        profile.parasitic_llm_reason = (
            "LLM parasitic backup disabled or Azure not configured."
        )
        return ParasiticLlmResult(
            source="heuristic",
            skipped="llm_disabled",
            reason=profile.parasitic_llm_reason,
        )

    if fetch_failure_kind in ("reject", "defer") or not fetch_ok:
        profile.parasitic_source = "heuristic"
        profile.parasitic_llm_reason = (
            "Fetch defer/reject — keep heuristic parasitic tier."
        )
        return ParasiticLlmResult(
            source="heuristic",
            skipped="fetch_deferred",
            reason=profile.parasitic_llm_reason,
        )

    # Brand-self floor: keep elevated; skip LLM loosen (raise-only path unused
    # without verified plants — never call to invent suspected).
    if has_brand_self_elevated_floor(
        profile, content_role=content_role, query=query
    ):
        if profile.parasitic_geo_suspected is not True:
            profile.parasitic_geo_elevated = True
            profile.parasitic_geo_risk = max(
                float(profile.parasitic_geo_risk or 0.0), BRAND_SELF_ELEVATED_RISK
            )
        profile.parasitic_source = "heuristic"
        profile.parasitic_llm_reason = (
            "Brand-self elevated floor — skip parasitic LLM loosen."
        )
        return ParasiticLlmResult(
            source="heuristic",
            skipped="brand_self_floor",
            reason=profile.parasitic_llm_reason,
        )

    # Surface-only sparse UGC: force none before LLM can FP-elevate.
    if sparse_clean_ugc_force_none(profile):
        _apply_tier_flags(profile, "none")
        profile.parasitic_source = "heuristic"
        profile.parasitic_llm_reason = (
            "Sparse clean UGC hubs without plant density — parasitic none."
        )
        return ParasiticLlmResult(
            source="heuristic",
            skipped="sparse_clean_ugc",
            reason=profile.parasitic_llm_reason,
        )

    if not parasitic_llm_gate(
        profile,
        content_role=content_role,
        fetch_ok=fetch_ok,
        fetch_failure_kind=fetch_failure_kind,
    ):
        profile.parasitic_source = "heuristic"
        profile.parasitic_llm_reason = (
            "Heuristic tier confident; outside parasitic LLM ambiguity gate."
        )
        return ParasiticLlmResult(
            source="heuristic",
            skipped="not_ambiguous",
            reason=profile.parasitic_llm_reason,
        )

    try:
        suggestion = suggest_parasitic_llm(
            profile,
            target_url=target_url,
            content_role=content_role,
            metadata=metadata,
        )
    except Exception as exc:
        logger.warning("parasitic LLM failed (keeping heuristic): %s", exc)
        profile.parasitic_source = "heuristic"
        profile.parasitic_llm_reason = f"Parasitic LLM error; keep heuristic ({exc})."
        return ParasiticLlmResult(
            source="heuristic",
            skipped="llm_error",
            reason=profile.parasitic_llm_reason,
        )

    if suggestion is None:
        profile.parasitic_source = "heuristic"
        profile.parasitic_llm_reason = (
            "Parasitic LLM response unparseable; keep heuristic."
        )
        return ParasiticLlmResult(
            source="heuristic",
            skipped="parse_failed",
            reason=profile.parasitic_llm_reason,
        )

    applied = merge_parasitic_hybrid(
        profile,
        suggestion,
        hard_floor=hard,
        content_role=content_role,
        query=query,
        target_commercial_tier=target_commercial_tier,
    )
    if applied is None:
        profile.parasitic_source = "heuristic"
        profile.parasitic_llm_reason = suggestion.reason or (
            "LLM returned null; keep heuristic parasitic tier."
        )
        return ParasiticLlmResult(
            source="heuristic",
            reason=profile.parasitic_llm_reason,
            skipped="null_keep",
        )

    profile.parasitic_source = "llm_hybrid"
    profile.parasitic_llm_reason = suggestion.reason
    return ParasiticLlmResult(source="llm_hybrid", reason=suggestion.reason)
