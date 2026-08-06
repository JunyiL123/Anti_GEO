"""Azure LLM backup for ambiguous Mode B plant-stance (UGC / review hubs).

Heuristics in ``content_signals.classify_plant_stance`` stay the cheap default.
When a stance-gated parasitic surface lands on unknown / neutral / complaint
(not clear promotional, not already high-conf), optionally ask Azure to
re-apply the same rules on the entity-scoped excerpt. Fail-open to heuristic.
Cap calls per referral profile. Never rewrites Group A permissions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from anti_geo.azure_client import chat_completion_json, is_azure_configured, load_azure_config
from anti_geo.content_signals import (
    PLANT_STANCE_COMPLAINT,
    PLANT_STANCE_NEUTRAL,
    PLANT_STANCE_PROMOTIONAL,
    PLANT_STANCE_UNKNOWN,
    plant_stance_heuristic_rules_rubric,
)
from anti_geo.platform_role import is_open_posting_path, is_parasitic_referrer

logger = logging.getLogger(__name__)

ALLOWED_STANCES = frozenset(
    {
        PLANT_STANCE_PROMOTIONAL,
        PLANT_STANCE_COMPLAINT,
        PLANT_STANCE_NEUTRAL,
        PLANT_STANCE_UNKNOWN,
    }
)
# Clear promotional already hard-counts; high-conf also hard-counts — skip LLM.
AMBIGUOUS_STANCES = frozenset(
    {
        PLANT_STANCE_UNKNOWN,
        PLANT_STANCE_NEUTRAL,
        PLANT_STANCE_COMPLAINT,
    }
)
_STANCE_PRIORITY = {
    PLANT_STANCE_UNKNOWN: 0,
    PLANT_STANCE_NEUTRAL: 1,
    PLANT_STANCE_COMPLAINT: 2,
}
MAX_STANCE_LLM = 4
_LLM_STANCE_EXCERPT = 1800


@dataclass(frozen=True)
class StanceLlmResult:
    stance: str
    reason: str = ""


def _is_stance_gated(url: str, role: str) -> bool:
    if (role or "").strip() in ("ugc_thread", "review_profile"):
        return True
    return is_open_posting_path(url)


def stance_llm_gate(
    *,
    url: str,
    role: str,
    heuristic_stance: str,
    content_high_risk: bool = False,
    llm_parasitic: bool = False,
    excerpt: str = "",
) -> bool:
    """True only for ambiguous stance-gated parasitic UGC/review hubs."""
    if content_high_risk:
        return False
    stance = (heuristic_stance or PLANT_STANCE_UNKNOWN).strip().lower()
    if stance == PLANT_STANCE_PROMOTIONAL:
        return False
    if stance not in AMBIGUOUS_STANCES:
        return False
    if not _is_stance_gated(url, role):
        return False
    if not is_parasitic_referrer(
        url=url,
        role=role,
        content_high_risk=False,
        llm_parasitic=llm_parasitic,
    ):
        return False
    if not (excerpt or "").strip():
        return False
    return True


def _llm_classify_stance(
    url: str,
    excerpt: str,
    *,
    entity: str,
    heuristic_stance: str,
    flags: list[str] | None = None,
) -> StanceLlmResult | None:
    blob = (excerpt or "").strip()[:_LLM_STANCE_EXCERPT]
    if not blob:
        return None
    flag_line = ", ".join(flags or []) or "(none)"
    messages = [
        {
            "role": "system",
            "content": plant_stance_heuristic_rules_rubric(),
        },
        {
            "role": "user",
            "content": (
                f"url: {url}\n"
                f"entity: {entity or '(none)'}\n"
                f"heuristic_stance_prior: {heuristic_stance}\n"
                f"content_flags: {flag_line}\n\n"
                f"referrer_excerpt:\n{blob}"
            ),
        },
    ]
    payload = chat_completion_json(messages, config=load_azure_config())
    stance = str(payload.get("stance") or "").strip().lower()
    if stance not in ALLOWED_STANCES:
        return None
    reason = " ".join(str(payload.get("reason") or "").split())[:240]
    return StanceLlmResult(stance=stance, reason=reason)


def resolve_plant_stance_for_referrer(
    *,
    url: str,
    role: str,
    excerpt: str,
    heuristic_stance: str,
    entity: str = "",
    flags: list[str] | None = None,
    content_high_risk: bool = False,
    llm_parasitic: bool = False,
    use_llm: bool | None = None,
) -> tuple[str, str, str]:
    """Return ``(stance, source, reason)`` — heuristic unless LLM upgrades.

    source is ``heuristic`` | ``llm``. Fail-open keeps heuristic.
    """
    prior = (heuristic_stance or PLANT_STANCE_UNKNOWN).strip().lower()
    if prior not in ALLOWED_STANCES:
        prior = PLANT_STANCE_UNKNOWN
    base = (prior, "heuristic", "")

    if not stance_llm_gate(
        url=url,
        role=role,
        heuristic_stance=prior,
        content_high_risk=content_high_risk,
        llm_parasitic=llm_parasitic,
        excerpt=excerpt,
    ):
        return base

    llm_enabled = is_azure_configured() if use_llm is None else use_llm
    if not llm_enabled:
        return base

    try:
        result = _llm_classify_stance(
            url,
            excerpt,
            entity=entity,
            heuristic_stance=prior,
            flags=flags,
        )
    except Exception as exc:
        logger.warning("LLM plant-stance classify failed (keeping heuristic): %s", exc)
        return base

    if result is None:
        return base
    return (result.stance, "llm", result.reason)


def maybe_resolve_plant_stances(
    verified: list[Any],
    scores_by_url: dict[str, Any],
    *,
    entity: str = "",
    use_llm: bool | None = None,
    max_calls: int = MAX_STANCE_LLM,
) -> int:
    """Optionally LLM-resolve ambiguous UGC/review stances in-place.

    ``scores_by_url`` maps normalized URL → object with ``excerpt`` (and
    optionally scored referrer content). Returns number of LLM upgrades applied.
    """
    llm_enabled = is_azure_configured() if use_llm is None else use_llm
    if not llm_enabled or max_calls <= 0 or not verified:
        return 0

    candidates: list[tuple[int, float, Any, str]] = []
    for ref in verified:
        key = (getattr(ref, "url", "") or "").rstrip("/").lower()
        score = scores_by_url.get(key)
        excerpt = ""
        if score is not None:
            excerpt = str(getattr(score, "excerpt", "") or "")
        stance = (getattr(ref, "content_plant_stance", None) or PLANT_STANCE_UNKNOWN).strip().lower()
        if not stance_llm_gate(
            url=ref.url,
            role=ref.role,
            heuristic_stance=stance,
            content_high_risk=bool(getattr(ref, "content_high_risk", False)),
            llm_parasitic=bool(getattr(ref, "llm_parasitic", False)),
            excerpt=excerpt,
        ):
            continue
        prio = _STANCE_PRIORITY.get(stance, 9)
        manip = float(getattr(ref, "content_manipulability", 0.0) or 0.0)
        candidates.append((prio, -manip, ref, excerpt))

    candidates.sort(key=lambda t: (t[0], t[1]))
    upgraded = 0
    for _, _, ref, excerpt in candidates[:max_calls]:
        prior = (ref.content_plant_stance or PLANT_STANCE_UNKNOWN).strip().lower()
        stance, source, reason = resolve_plant_stance_for_referrer(
            url=ref.url,
            role=ref.role,
            excerpt=excerpt,
            heuristic_stance=prior,
            entity=entity,
            flags=list(getattr(ref, "content_flags", None) or []),
            content_high_risk=bool(ref.content_high_risk),
            llm_parasitic=bool(ref.llm_parasitic),
            use_llm=True,
        )
        if source != "llm":
            continue
        ref.content_plant_stance = stance
        if hasattr(ref, "content_plant_stance_source"):
            ref.content_plant_stance_source = "llm"
        if hasattr(ref, "content_plant_stance_reason"):
            ref.content_plant_stance_reason = reason
        upgraded += 1
    return upgraded
