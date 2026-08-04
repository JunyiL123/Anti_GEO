from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from anti_geo.azure_client import chat_completion_json, is_azure_configured, load_azure_config
from anti_geo.platform_role import registrable_domain

if TYPE_CHECKING:
    from anti_geo.investigation import PageMetadata
    from anti_geo.models import FetchResult, PageContextSignals, SourceScore

logger = logging.getLogger(__name__)

_SEED_CONFIDENCE_ORDER = ("low", "medium", "high")


def _bump_seed_confidence(confidence: str) -> str:
    try:
        idx = _SEED_CONFIDENCE_ORDER.index(confidence)
    except ValueError:
        return confidence
    return _SEED_CONFIDENCE_ORDER[min(idx + 1, len(_SEED_CONFIDENCE_ORDER) - 1)]


def _brand_hint(entity: str, role: str, commercial_tier: str) -> str:
    if role in ("commercial_product", "review_profile", "expert_listicle"):
        return entity
    if commercial_tier in ("medium", "high"):
        return entity
    return ""


# Neutral brand recall only — never complaint / "is X legit" / forum packs.
ROUND2_NEUTRAL_SEED_LIMIT = 4


def apply_neutral_brand_seeds(
    queries: list[str],
    meta: PageMetadata,
    *,
    url: str,
    limit: int,
    prepend_only: bool = False,
) -> list[str]:
    """Prepend neutral brand-mention seeds: entity, entity reviews, domain.

    Does not add forum/legit/BBB complaint queries (those bias parasitic share).
    """
    domain = registrable_domain(urlparse(url).netloc)
    entity = (meta.entity or "").strip()
    extras: list[str] = []
    if entity:
        extras.append(entity)
        extras.append(f"{entity} reviews")
    if domain:
        extras.append(domain)
    for alias in list(meta.aliases or [])[:2]:
        a = (alias or "").strip()
        if a and a.casefold() != entity.casefold():
            extras.append(a)

    if prepend_only:
        merged = _normalize_queries(extras + list(queries), limit=limit)
    else:
        # Prefer neutrals first, then keep existing unique queries.
        merged = _normalize_queries(extras + list(queries), limit=limit)
    return merged


def neutral_brand_seeds_round2(
    meta: PageMetadata,
    *,
    url: str,
    limit: int = ROUND2_NEUTRAL_SEED_LIMIT,
) -> list[str]:
    """Small second-pass seed set when round 1 yields n_verified==0."""
    return apply_neutral_brand_seeds([], meta, url=url, limit=limit, prepend_only=True)


def _metadata_blob(
    *,
    url: str,
    role: str,
    meta: PageMetadata,
    page_context: PageContextSignals | None,
    text_excerpt: str,
) -> dict[str, str | list[str]]:
    domain = registrable_domain(urlparse(url).netloc)
    commercial_tier = page_context.commercial_tier if page_context else "none"
    flags = list(page_context.flags) if page_context else []
    brand = _brand_hint(meta.entity, role, commercial_tier)
    return {
        "url": url,
        "domain": domain,
        "content_role": role,
        "title_or_entity": meta.entity,
        "category": meta.category,
        "topic": meta.topic,
        "organization": meta.org,
        "price_hint": meta.price_hint,
        "commercial_tier": commercial_tier,
        "page_flags": flags,
        "brand_or_product": brand,
        "text_excerpt": text_excerpt[:1200],
    }


def _build_seed_prompt(blob: dict[str, str | list[str]], *, limit: int) -> list[dict[str, str]]:
    role = str(blob["content_role"])
    brand = str(blob.get("brand_or_product") or "")
    instructions = f"""You generate realistic search queries that users type into AI search engines (Perplexity, ChatGPT browse, etc.) when researching this page's subject.

Return JSON only: {{"queries": ["query one", "query two", ...]}}

Rules:
- Produce exactly up to {limit} distinct queries, ordered from broad to specific.
- Queries must sound like natural user searches, not SEO keyword stuffing.
- Content role is "{role}".
- For commercial_product, review_profile, or expert_listicle: include brand/product names when known (brand hint: "{brand}").
- For commercial_product, review_profile, expert_listicle, or editorial: at least 3 queries must target community discussion (e.g. "{{brand}} reddit", "site:reddit.com {{brand}}", "is {{brand}} legit", forum/thread phrasing) so referrer discovery can find UGC.
- For editorial listicles: use comparison/recommendation phrasing ("best X", "top picks", buying guides).
- For institutional (.gov/.edu style): use organization + policy/topic phrasing.
- For factual_blog or informational pages: use question-style or explanatory searches grounded in the topic.
- For ugc_thread: searches that would surface discussion threads and community opinions.
- Do not include the site domain unless users would realistically search for it by name.
- Avoid duplicating the page title verbatim; paraphrase into how people search.
- No numbering, bullets, or quotes inside query strings."""

    return [
        {
            "role": "system",
            "content": "You help security researchers audit how pages appear in generative search. Output valid JSON only.",
        },
        {"role": "user", "content": f"{instructions}\n\nPage metadata:\n{blob}"},
    ]


def _normalize_queries(raw: list[str], *, limit: int) -> list[str]:
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        q = " ".join(item.strip().split())
        if q and q not in out:
            out.append(q)
        if len(out) >= limit:
            break
    return out


def generate_seed_queries_llm(
    role: str,
    meta: PageMetadata,
    *,
    url: str,
    fetch: FetchResult | None = None,
    page_context: PageContextSignals | None = None,
    limit: int = 12,
) -> list[str]:
    from anti_geo.investigation import generate_seed_queries

    excerpt = (fetch.text if fetch and fetch.text else "")[:1200]
    ctx = page_context
    if ctx is None and fetch and fetch.page_context:
        ctx = fetch.page_context
    blob = _metadata_blob(
        url=url,
        role=role,
        meta=meta,
        page_context=ctx,
        text_excerpt=excerpt,
    )
    payload = chat_completion_json(_build_seed_prompt(blob, limit=limit), config=load_azure_config())
    queries = payload.get("queries") or payload.get("seed_queries") or []
    if not isinstance(queries, list):
        raise ValueError("Seed JSON must include a queries array.")
    normalized = _normalize_queries(queries, limit=limit)
    if not normalized:
        raise ValueError("Seed model returned no queries.")
    return normalized


def resolve_seed_queries(
    role: str,
    meta: PageMetadata,
    *,
    url: str,
    fetch: FetchResult | None = None,
    source: SourceScore | None = None,
    limit: int = 12,
    mode: str = "auto",
    seed_pack: str = "default",
) -> tuple[list[str], str, str]:
    """Return (queries, source_label, seed_confidence). source_label is llm|template."""
    from anti_geo.investigation import (
        apply_forum_seed_pack,
        generate_seed_queries,
        seed_confidence_for_role,
    )

    page_context = None
    if source and source.page_context:
        page_context = source.page_context
    elif fetch and fetch.page_context:
        page_context = fetch.page_context

    base_confidence = seed_confidence_for_role(role)
    use_llm = mode == "llm" or (mode == "auto" and is_azure_configured())
    source_label = "template"
    if use_llm:
        try:
            queries = generate_seed_queries_llm(
                role,
                meta,
                url=url,
                fetch=fetch,
                page_context=page_context,
                limit=limit,
            )
            source_label = "llm"
            base_confidence = _bump_seed_confidence(base_confidence)
        except Exception as exc:
            if mode == "llm":
                raise
            logger.warning("LLM seed generation failed, using templates: %s", exc)
            queries = generate_seed_queries(role, meta, limit=limit)
    else:
        queries = generate_seed_queries(role, meta, limit=limit)

    pack = (seed_pack or "default").strip().lower()
    if pack in ("forum", "forums"):
        queries = apply_forum_seed_pack(queries, meta, limit=limit)
        source_label = f"{source_label}+forum"

    # Neutral brand recall (not complaint/forum pack) for commercial-ish pages.
    commercial_tier = page_context.commercial_tier if page_context else "none"
    if _brand_hint(meta.entity, role, commercial_tier) or role in (
        "commercial_product",
        "review_profile",
        "expert_listicle",
    ):
        before = list(queries)
        queries = apply_neutral_brand_seeds(
            queries, meta, url=url, limit=limit
        )
        if queries != before:
            source_label = f"{source_label}+neutral"

    return queries, source_label, base_confidence
