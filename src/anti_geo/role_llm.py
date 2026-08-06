"""Azure LLM fallback for ambiguous Mode B referrer roles.

Heuristics in ``platform_role`` stay the cheap default. When a fetched
referrer lands on ``factual_blog`` / ``commercial_product``, optionally ask
Azure to re-label (review hubs, video UGC, review farms with odd paths).
Never downgrades a surface that heuristics already mark parasitic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from anti_geo.azure_client import chat_completion_json, is_azure_configured, load_azure_config
from anti_geo.models import FetchResult
from anti_geo.platform_role import (
    CONTENT_ROLES,
    classify_content_role,
    content_role_heuristic_rules_rubric,
    is_parasitic_referrer,
)

logger = logging.getLogger(__name__)

ALLOWED_ROLES = CONTENT_ROLES

# Heuristic roles that may miss open-posting / review-hub shapes.
AMBIGUOUS_ROLES = frozenset({"factual_blog", "commercial_product"})

_LLM_ROLE_EXCERPT = 2000


@dataclass(frozen=True)
class ResolvedReferrerRole:
    role: str
    role_source: str  # heuristic | llm
    role_reason: str = ""
    llm_parasitic: bool = False


@dataclass(frozen=True)
class RoleLlmResult:
    role: str
    parasitic_surface: bool
    reason: str = ""


def _llm_classify_role(
    url: str,
    title: str,
    text: str,
    *,
    heuristic_role: str,
) -> RoleLlmResult | None:
    excerpt = (text or "").strip()[:_LLM_ROLE_EXCERPT]
    if not excerpt and not (title or "").strip():
        return None
    messages = [
        {
            "role": "system",
            "content": content_role_heuristic_rules_rubric(),
        },
        {
            "role": "user",
            "content": (
                f"url: {url}\n"
                f"title: {title or '(none)'}\n"
                f"heuristic_role_prior: {heuristic_role}\n\n"
                f"page_excerpt:\n{excerpt or '(empty)'}"
            ),
        },
    ]
    payload = chat_completion_json(messages, config=load_azure_config())
    role = str(payload.get("role") or "").strip().lower()
    if role not in ALLOWED_ROLES:
        return None
    raw_para = payload.get("parasitic_surface")
    if isinstance(raw_para, bool):
        parasitic = raw_para
    elif isinstance(raw_para, str):
        parasitic = raw_para.strip().lower() in ("true", "yes", "1")
    else:
        parasitic = False
    reason = " ".join(str(payload.get("reason") or "").split())[:240]
    return RoleLlmResult(role=role, parasitic_surface=parasitic, reason=reason)


def resolve_referrer_role(
    url: str,
    fetch: FetchResult | None = None,
    *,
    use_llm: bool | None = None,
) -> ResolvedReferrerRole:
    """Heuristic role, then optional Azure upgrade for ambiguous leftovers."""
    heuristic = classify_content_role(url, fetch=fetch)
    base = ResolvedReferrerRole(
        role=heuristic,
        role_source="heuristic",
        role_reason="",
        llm_parasitic=False,
    )

    # Already a clear parasitic surface — never LLM-downgrade.
    if is_parasitic_referrer(url=url, role=heuristic, content_high_risk=False):
        return base

    if heuristic not in AMBIGUOUS_ROLES:
        return base

    llm_enabled = is_azure_configured() if use_llm is None else use_llm
    if not llm_enabled:
        return base
    if fetch is None or not fetch.ok:
        return base

    try:
        result = _llm_classify_role(
            url,
            fetch.title or "",
            fetch.text or "",
            heuristic_role=heuristic,
        )
    except Exception as exc:
        logger.warning("LLM referrer role classify failed (keeping heuristic): %s", exc)
        return base

    if result is None:
        return base

    # Prefer LLM role when it re-labels; keep parasitic flag if surface=true
    # even when role stays soft (factual_blog / commercial_product).
    llm_parasitic = bool(result.parasitic_surface) or is_parasitic_referrer(
        url=url, role=result.role, content_high_risk=False
    )
    return ResolvedReferrerRole(
        role=result.role,
        role_source="llm",
        role_reason=result.reason,
        llm_parasitic=llm_parasitic,
    )
