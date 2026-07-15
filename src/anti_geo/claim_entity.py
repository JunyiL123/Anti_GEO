"""Intent × source-role claim/topic entity resolution.

Heuristic first; Azure LLM only when candidates are ambiguous or look like
listicle / title junk. Keeps recommendy query words like ``best``.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from anti_geo.azure_client import chat_completion_json, is_azure_configured, load_azure_config
from anti_geo.models import PageIdentity, SourceScore
from anti_geo.platform_role import registrable_domain

logger = logging.getLogger(__name__)

ENTITY_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})\b")

_COMMERCIAL_ROLES = frozenset(
    {"commercial_product", "review_profile", "expert_listicle"}
)
_FACTUAL_ROLES = frozenset({"factual_blog", "institutional", "editorial"})

# Title-case / listicle junk.
_ENTITY_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "for",
        "to",
        "of",
        "in",
        "on",
        "at",
        "by",
        "with",
        "from",
        "your",
        "our",
        "my",
        "me",
        "you",
        "we",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "where",
        "when",
        "why",
        "how",
        "this",
        "that",
        "these",
        "those",
        "right",
        "wrong",
        "information",
        "guide",
        "guides",
        "review",
        "reviews",
        "advice",
        "tips",
        "options",
        "picks",
        "list",
        "lists",
        "article",
        "blog",
        "post",
        "page",
        "home",
        "official",
        "top",
        "updated",
        "contents",
        "forum",
        "forums",
        "community",
        "discussion",
        "thread",
        "threads",
        "topics",
        "topic",
        "directory",
    }
)
_ENTITY_INTERROGATIVES = frozenset(
    {"what", "which", "who", "whom", "whose", "where", "when", "why", "how"}
)

# Weak Mode-B verify markers (generic English / IA chrome).
_WEAK_VERIFY_MARKERS = frozenset(
    {
        "topic",
        "topics",
        "forum",
        "forums",
        "community",
        "discussion",
        "thread",
        "threads",
        "index",
        "home",
        "top",
        "best",
        "reviews",
        "review",
        "guide",
        "blog",
        "news",
        "search",
        "login",
        "about",
        "contact",
        "help",
        "faq",
        "menu",
        "categories",
        "category",
        "tags",
        "tag",
        "latest",
        "popular",
        "trending",
        "messages",
        "posts",
        "users",
        "members",
        "headphones",  # category noun alone is not a brand tie
        "laptop",
        "laptops",
        "earbuds",
        "software",
    }
)


def _entities_in_text(text: str) -> list[str]:
    return [m.group(1) for m in ENTITY_RE.finditer(text or "")]


def normalize_query_topic(query: str | None) -> str | None:
    """Keep recommendy words like 'best' — they are useful topic signal."""
    if not query:
        return None
    topic = " ".join(query.strip().split())
    return topic or None


def is_junk_entity(entity: str) -> bool:
    tokens = [t for t in re.split(r"\s+", entity.strip()) if t]
    if not tokens or len(entity.strip()) < 4:
        return True
    lower = [t.lower().strip(".,!?;:')(\"") for t in tokens]
    if lower[0] in _ENTITY_INTERROGATIVES:
        return True
    # Years / pure short digit tokens ("2026") and digit listicles
    if re.match(r"^\d+\b", entity.strip()):
        return True
    if len(tokens) == 1 and (tokens[0].isdigit() or re.fullmatch(r"20\d{2}", tokens[0])):
        return True
    if lower[-1] in {"in", "for", "with", "and", "or", "to"}:
        return True
    content = [t for t in lower if t not in _ENTITY_STOPWORDS and not t.isdigit()]
    if len(content) == 0:
        return True
    if len(tokens) >= 2 and len(content) / len(tokens) <= 0.5:
        return True
    return False


def is_weak_verify_marker(marker: str) -> bool:
    """True for generic words that must not count as brand_mention ties."""
    text = " ".join((marker or "").strip().lower().split())
    if not text or len(text) < 4:
        return True
    # Calendar / year-only markers match almost every modern page.
    if text.isdigit() or re.fullmatch(r"20\d{2}", text):
        return True
    if text in _WEAK_VERIFY_MARKERS or text in _ENTITY_STOPWORDS:
        return True
    # Single-token category / chrome nouns
    if " " not in text and text.isalpha() and text in _WEAK_VERIFY_MARKERS:
        return True
    return False


def is_usable_claim_label(label: str) -> bool:
    return bool(label) and not is_junk_entity(label) and not is_weak_verify_marker(label)


def _publisher_labels(identity: PageIdentity, url: str) -> set[str]:
    labels: set[str] = set()
    for raw in (
        identity.site_name,
        identity.organization,
        registrable_domain(urlparse(url).netloc or ""),
    ):
        n = " ".join(str(raw or "").strip().split()).lower()
        if len(n) >= 3:
            labels.add(n)
            labels.add(re.sub(r"[^a-z0-9]", "", n))
    return {x for x in labels if x}


def _looks_like_publisher(name: str, identity: PageIdentity, url: str) -> bool:
    n = " ".join(name.strip().split()).lower()
    compact = re.sub(r"[^a-z0-9]", "", n)
    pubs = _publisher_labels(identity, url)
    if n in pubs or compact in pubs:
        return True
    for raw in (identity.site_name, identity.organization):
        pub = " ".join(str(raw or "").strip().split()).lower()
        if pub and n == pub:
            return True
    stem = registrable_domain(urlparse(url).netloc or "").split(".")[0].lower()
    if stem and len(stem) >= 3 and (compact == stem or n.replace(" ", "") == stem):
        return True
    return False


def brand_from_sources(sources: list[SourceScore]) -> str | None:
    """Product/brand when present — skip publisher-only and listicle residue."""
    for source in sources:
        identity = source.identity
        if identity is None:
            continue
        for cand in (identity.product, identity.brand):
            name = " ".join(str(cand or "").strip().split())
            if not name or not is_usable_claim_label(name):
                continue
            if _looks_like_publisher(name, identity, source.url):
                continue
            return name
    return None


def shared_title_case_claim(
    sources: list[SourceScore],
    *,
    min_count: int = 2,
) -> str | None:
    counts: dict[str, int] = {}
    for s in sources:
        for ent in set(_entities_in_text(s.text_excerpt)):
            if not is_usable_claim_label(ent):
                continue
            counts[ent] = counts.get(ent, 0) + 1
    if not counts:
        return None
    best = max(counts, key=counts.get)
    return best if counts[best] >= min_count else None


def _role_sets(content_roles: list[str] | None) -> tuple[bool, bool, bool]:
    roles = [r for r in (content_roles or []) if r]
    commercialish = any(r in _COMMERCIAL_ROLES for r in roles)
    factualish = any(r in _FACTUAL_ROLES for r in roles)
    only_ugc = bool(roles) and all(r == "ugc_thread" for r in roles)
    return commercialish, factualish, only_ugc


def _heuristic_pick(
    *,
    query_intent: str,
    topic: str | None,
    brand: str | None,
    shared: str | None,
    content_roles: list[str] | None,
) -> str | None:
    """Intent × source-role routing (no LLM)."""
    commercialish, factualish, only_ugc = _role_sets(content_roles)
    intent = (query_intent or "informational").strip().lower()

    # Commercial shopping / recommend asks: brand when page looks commercial;
    # else query topic (keep "best …").
    if intent == "commercial":
        if only_ugc:
            return topic or brand or shared
        if brand and (commercialish or not content_roles):
            return brand
        return topic or brand or shared

    # Informational: topic-first for factual/institutional; brand if a
    # commercial/review cite is clearly about a product.
    if intent.startswith("informational"):
        if commercialish and brand:
            return brand
        if factualish or only_ugc or not content_roles:
            return topic or brand or shared
        return topic or brand or shared

    if intent == "navigational":
        return brand or topic or shared

    return topic or brand or shared


def _needs_llm(
    pick: str | None,
    *,
    topic: str | None,
    brand: str | None,
    content_roles: list[str] | None,
) -> bool:
    if pick is None:
        return bool(topic or brand)
    if not is_usable_claim_label(pick):
        return True
    commercialish, factualish, _ = _role_sets(content_roles)
    # Mixed cite set with both brand and topic → ask model once.
    if brand and topic and commercialish and factualish:
        b = brand.lower()
        t = topic.lower()
        if b not in t and t not in b:
            return True
    return False


def _source_snapshots(
    sources: list[SourceScore],
    content_roles: list[str] | None,
) -> list[dict[str, str]]:
    roles = list(content_roles or [])
    out: list[dict[str, str]] = []
    for i, src in enumerate(sources[:5]):
        idn = src.identity
        out.append(
            {
                "url": src.url,
                "role": roles[i] if i < len(roles) else "",
                "brand": (idn.brand if idn else "") or "",
                "product": (idn.product if idn else "") or "",
                "organization": (idn.organization if idn else "") or "",
                "excerpt": (src.text_excerpt or "")[:240],
            }
        )
    return out


def _llm_resolve_claim_entity(
    *,
    query: str | None,
    query_intent: str,
    topic: str | None,
    brand: str | None,
    heuristic: str | None,
    sources: list[SourceScore],
    content_roles: list[str] | None,
) -> str | None:
    snaps = _source_snapshots(sources, content_roles)
    messages = [
        {
            "role": "system",
            "content": (
                "You pick the claim/topic entity for an AI-search defense audit. "
                "Return JSON only: "
                '{"entity":"...", "kind":"brand"|"topic"|"none"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"query_intent: {query_intent}\n"
                f"query: {query or ''}\n"
                f"query_topic_candidate: {topic or ''}\n"
                f"brand_product_candidate: {brand or ''}\n"
                f"heuristic_pick: {heuristic or ''}\n"
                f"source_roles: {content_roles or []}\n"
                f"sources: {snaps}\n\n"
                "Rules:\n"
                "- Informational + factual/institutional/editorial/ugc: prefer the "
                "query topic (keep words like 'best'); only choose a brand/product "
                "if the page is clearly about that one product.\n"
                "- Informational + commercial/review sources: prefer brand/product "
                "when real; else query topic.\n"
                "- Commercial intent: prefer brand/product when real; else query topic.\n"
                "- Never invent entities. Reject listicle titles "
                "('Top 15 … Forums in 2026'), truncated crumbs, and generic words "
                "(topics, forum, community).\n"
                "- If nothing usable, kind=none and entity empty."
            ),
        },
    ]
    payload = chat_completion_json(messages, config=load_azure_config())
    kind = str(payload.get("kind") or "").strip().lower()
    entity = " ".join(str(payload.get("entity") or "").split())
    if kind == "none" or not entity:
        return topic or heuristic
    if not is_usable_claim_label(entity):
        return topic or heuristic
    return entity


def resolve_claim_entity(
    sources: list[SourceScore],
    *,
    query: str | None = None,
    query_intent: str = "informational",
    content_roles: list[str] | None = None,
    use_llm: bool | None = None,
) -> str | None:
    """Resolve claim/topic entity conditioned on intent and cite roles.

    ``use_llm=None`` → call Azure only when configured and the heuristic pick
    looks ambiguous / junk.
    """
    topic = normalize_query_topic(query)
    brand = brand_from_sources(sources)
    shared = shared_title_case_claim(sources, min_count=2)
    pick = _heuristic_pick(
        query_intent=query_intent,
        topic=topic,
        brand=brand,
        shared=shared,
        content_roles=content_roles,
    )
    # Hard fallback: never stick listicle residue when query topic exists.
    if pick and not is_usable_claim_label(pick) and topic:
        pick = topic

    llm_enabled = is_azure_configured() if use_llm is None else use_llm
    if llm_enabled and _needs_llm(
        pick, topic=topic, brand=brand, content_roles=content_roles
    ):
        try:
            return _llm_resolve_claim_entity(
                query=query,
                query_intent=query_intent,
                topic=topic,
                brand=brand,
                heuristic=pick,
                sources=sources,
                content_roles=content_roles,
            )
        except Exception as exc:
            logger.warning("Claim-entity LLM failed, using heuristic: %s", exc)

    return pick or topic or brand or shared
