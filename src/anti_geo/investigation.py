from __future__ import annotations

import logging
import random
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from anti_geo.audit.engines import EngineAdapter, get_engine
from anti_geo.azure_client import chat_completion_json, is_azure_configured, load_azure_config
from anti_geo.decisions import decide_single_source
from anti_geo.fetch import fetch_page
from anti_geo.models import FetchResult, SourceScore, UrlAnalysisReport
from anti_geo.page_identity import strip_listicle_boilerplate
from anti_geo.permissions import derive_llm_actions, merge_llm_actions
from anti_geo.platform_role import (
    classify_content_role,
    is_parasitic_referrer,
    registrable_domain,
)
from anti_geo.progress import NullProgress, Progress
from anti_geo.referrer_content import (
    ReferrerContentSummary,
    ReferrerExcerptCandidate,
    build_excerpt_candidate,
    referrer_content_tighten_extras,
    score_top_referrers,
)
from anti_geo.scorer import score_source
from anti_geo.seed_generation import resolve_seed_queries

logger = logging.getLogger(__name__)

PRODUCT_SEED_TEMPLATES = (
    "best {category} 2026",
    "best {category} under {price}",
    "{entity} review",
    "{entity} vs",
    "is {entity} worth it",
    "top {category} recommendations",
    "best budget {category}",
    "{category} buying guide",
    # Discussion / parasitic-GEO discovery (UGC referrer recall)
    "{entity} reddit",
    "{entity} reddit review",
    "{entity} site:reddit.com",
    "is {entity} legit reddit",
    "{category} reddit recommendations",
    "{entity} forum discussion",
)

INFORMATIONAL_SEED_TEMPLATES = (
    "what is {topic}",
    "{topic} explained",
    "how does {topic} work",
    "{topic} guide",
    "evidence for {topic}",
)

EDITORIAL_SEED_TEMPLATES = (
    "best {category} 2026",
    "best {category} tested",
    "{category} buying guide",
    "top {category} picks",
)

INSTITUTIONAL_SEED_TEMPLATES = (
    "{org} {topic}",
    "official guidance on {topic}",
    "{topic} {org}",
)


@dataclass
class PageMetadata:
    entity: str
    category: str
    topic: str
    price_hint: str
    org: str
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReferrerConnection:
    """Referrer tie to the target. Deterministic first; ``llm_mention`` is backup-only."""

    kind: str  # url_link | brand_mention | llm_mention
    confidence: str  # high | weak
    marker: str = ""


@dataclass
class VerifiedReferrer:
    url: str
    role: str
    connection: str  # url_link | brand_mention | llm_mention
    connection_confidence: str = "high"  # high | weak
    matched_marker: str = ""
    seed_query: str = ""
    # Entity-scoped referrer L1 (eligible parasitic + soft editorial); does not rewrite target trust.
    content_scored: bool = False
    content_high_risk: bool = False
    content_semantic_risk: float = 0.0
    content_flags: list[str] = field(default_factory=list)
    content_manipulability: float = 0.0  # triage priority = max(thread, edit)
    content_thread_surface: float = 0.0
    content_editability: float = 0.0
    content_segment_role: str = ""


@dataclass
class SemanticAlignment:
    target_commercial_tier: str
    referrer_commercial_share: float
    aligned: bool
    label: str  # aligned | mismatch | coordinated_commercial | inconclusive


@dataclass
class ReferralProfile:
    status: str  # skipped | inconclusive | sparse | sparse_suspicious | complete
    discovery_status: str  # skipped | success | partial | failed
    confidence: str  # low | medium | high
    n_verified: int = 0
    mix: dict[str, int] = field(default_factory=dict)
    citations_domain_mix: dict[str, int] = field(default_factory=dict)
    geo_suspected: bool | None = None
    # Continuous referral GEO risk in [0, 1] from parasitic share + count (editorial dampened).
    geo_risk: float = 0.0
    # Soft elevate: downrank / hedge without hard convict (geo_suspected).
    geo_elevated: bool = False
    citations_sampled: int = 0
    seed_queries_run: int = 0
    target_cited_in_answers: int = 0
    semantic_alignment: SemanticAlignment | None = None
    referrers_verified: list[VerifiedReferrer] = field(default_factory=list)
    discovery_errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    referrer_content_scored: int = 0
    referrer_content_high_risk: int = 0
    referrer_content_coordinated: bool = False


# Hard convict: parasitic share above this at N>=10 with no editorial.
GEO_SUSPECTED_SHARE = 0.5
# Soft share band sits just under the hard bar (N>=10, no editorial).
GEO_SOFT_SHARE_LO = 0.35
GEO_SOFT_SHARE_HI = 0.5
# Continuous geo_risk → elevate (downrank) when below hard convict.
GEO_RISK_ELEVATED = 0.35
# Raw parasitic count elevate: N>=5, count>=3, no editorial (Meta brake).
GEO_ELEVATED_MIN_N = 5
GEO_ELEVATED_MIN_PARASITIC = 3


@dataclass
class InvestigationResult:
    target_url: str
    content_role: str
    seed_confidence: str
    seed_source: str  # llm | template
    seed_queries: list[str]
    single_page: UrlAnalysisReport
    llm_action: str
    llm_actions: list[str]
    referral_profile: ReferralProfile
    verdict: str
    metadata: PageMetadata


def _clean_title(title: str) -> str:
    base = re.split(r"\s*[|\-–—]\s*", title)[0].strip()
    return base[:120] if base else ""


def _category_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.lower()
    for part in path.split("/"):
        if part.startswith("best-") or part.startswith("the-best-"):
            return part.replace("-", " ").replace("the ", "").strip()
    qs = parsed.query.lower()
    for key in ("keywords", "q", "search"):
        match = re.search(rf"{key}=([^&]+)", qs)
        if match:
            words = match.group(1).replace("+", " ").split()
            if words:
                return " ".join(words[:4])
    return "product"


def _price_hint_from_text(text: str, url: str) -> str:
    blob = f"{text[:500]} {url}".lower()
    for pattern in (r"under\s+\$?\s*(\d+)", r"under\s+(\d+)\s*dollars", r"\$(\d+)\s*or\s*less"):
        match = re.search(pattern, blob)
        if match:
            return match.group(1)
    return "1000"


def extract_page_metadata(fetch: FetchResult) -> PageMetadata:
    """Prefer structured identity (og/JSON-LD); fall back to cleaned title + domain."""
    from anti_geo.claim_entity import is_usable_claim_label

    url = fetch.final_url or fetch.url
    domain = registrable_domain(urlparse(url).netloc)
    publisher = domain.split(".")[0] if domain else domain
    title = _clean_title(fetch.title or "")
    cleaned = strip_listicle_boilerplate(title)

    identity = fetch.identity
    brand = (identity.brand if identity else "") or ""
    product = (identity.product if identity else "") or ""
    organization = (identity.organization if identity else "") or ""
    site_name = (identity.site_name if identity else "") or ""
    aliases = [
        a
        for a in (list(identity.aliases) if identity and identity.aliases else [])
        if is_usable_claim_label(a)
    ]

    org = organization or site_name or brand or publisher or domain
    # Prefer a concrete product/SKU for seeds + verify markers; else brand; else title.
    # Skip listicle crumbs ("15 Headphones Forums in") and weak chrome ("topics").
    if (
        product
        and is_usable_claim_label(product)
        and product.lower() not in {org.lower(), (brand or "").lower()}
    ):
        entity = product
    elif brand and is_usable_claim_label(brand):
        entity = brand
    elif cleaned and is_usable_claim_label(cleaned):
        entity = cleaned
    elif org and is_usable_claim_label(org):
        entity = org
    else:
        entity = publisher or domain or title

    category = _category_from_url(url)
    topic = cleaned or title or category
    price = _price_hint_from_text(fetch.text or "", fetch.url)

    # Ensure org/entity land in aliases for referrer verification.
    for cand in (entity, org, brand, product, site_name, publisher):
        c = " ".join(str(cand).strip().split())
        if len(c) >= 4 and c.lower() not in {a.lower() for a in aliases}:
            if is_usable_claim_label(c):
                aliases.append(c)

    return PageMetadata(
        entity=entity,
        category=category,
        topic=topic,
        price_hint=price,
        org=org,
        aliases=aliases,
    )


def seed_confidence_for_role(role: str) -> str:
    if role in ("commercial_product", "editorial"):
        return "high"
    if role in ("institutional", "factual_blog"):
        return "medium"
    return "low"


def _normalize_category(category: str) -> str:
    c = category.strip()
    if c.lower().startswith("best "):
        return c[5:].strip()
    return c


DISCUSSION_SEED_TEMPLATES = (
    "{entity} reddit",
    "{entity} reddit review",
    "{entity} site:reddit.com",
    "is {entity} legit reddit",
    "{category} reddit recommendations",
    "{entity} forum discussion",
)

# Experiment pack: forum/directory/complaint queries that surface plantable referrers
# (Feedspot-style discovery). Prefer these early in the seed list when enabled.
FORUM_SEED_TEMPLATES = (
    "{category} forums",
    "best {category} forums",
    "{category} forum directory",
    "best forums for {category}",
    "{entity} forum",
    "{entity} forums list",
    "{entity} forum discussion",
    "{entity} board",
    "{entity} community forum",
    "{entity} site:reddit.com",
    "is {entity} legit forum",
    "{entity} bbb",
    "{entity} complaints",
    "{entity} customer reviews forum",
)


def _seed_ctx(meta: PageMetadata) -> dict[str, str]:
    return {
        "entity": meta.entity,
        "category": _normalize_category(meta.category),
        "topic": meta.topic,
        "price": meta.price_hint,
        "org": meta.org,
    }


def _forum_seed_category(category: str) -> str:
    """Avoid '{category} forums' → 'gaming forums forums'."""
    c = _normalize_category(category)
    c = re.sub(r"\s+forums?$", "", c, flags=re.I).strip()
    return c or _normalize_category(category) or "topic"


def format_seed_templates(
    templates: tuple[str, ...],
    meta: PageMetadata,
    *,
    limit: int,
    category_override: str | None = None,
) -> list[str]:
    ctx = _seed_ctx(meta)
    if category_override is not None:
        ctx["category"] = category_override
    queries: list[str] = []
    for tpl in templates:
        if len(queries) >= limit:
            break
        try:
            q = tpl.format(**ctx).strip()
        except KeyError:
            continue
        if q and q not in queries:
            queries.append(q)
    return queries


def apply_forum_seed_pack(
    queries: list[str],
    meta: PageMetadata,
    *,
    limit: int,
) -> list[str]:
    """Prepend forum/directory/complaint seeds; keep unique up to ``limit``."""
    forum = format_seed_templates(
        FORUM_SEED_TEMPLATES,
        meta,
        limit=limit,
        category_override=_forum_seed_category(meta.category),
    )
    merged: list[str] = []
    for q in forum + list(queries):
        if q and q not in merged:
            merged.append(q)
        if len(merged) >= limit:
            break
    return merged


def shadow_soft_path_metrics(profile: ReferralProfile) -> dict:
    """Candidate soft-path gates for experiments — does not affect live actions."""
    n = profile.n_verified
    parasitic_n = parasitic_count_from_verified(profile.referrers_verified)
    share = parasitic_share_from_verified(profile.referrers_verified)
    share_f = float(share) if share is not None else 0.0
    high_conf_parasitic = high_conf_parasitic_count_from_verified(
        profile.referrers_verified
    )
    return {
        "n_verified": n,
        "parasitic_count": parasitic_n,
        "parasitic_share": share,
        "high_conf_parasitic_count": high_conf_parasitic,
        "editorial_institutional_count": _editorial_institutional_count(profile.mix),
        "geo_suspected_live": profile.geo_suspected,
        "geo_elevated_live": profile.geo_elevated,
        "geo_risk": profile.geo_risk,
        "sparse_suspicious_live": profile.status == "sparse_suspicious",
        "soft_band_live": parasitic_soft_downrank_band(profile),
        "candidate_gates": {
            "parasitic_count_ge_3": parasitic_n >= 3,
            "parasitic_count_ge_2": parasitic_n >= 2,
            "share_ge_0.35_n_ge_5": n >= 5 and share_f >= 0.35,
            "share_ge_0.40_n_ge_5": n >= 5 and share_f >= 0.40,
            "share_ge_0.50_n_ge_5": n >= 5 and share_f >= 0.50,
            "share_gt_0.50_hard": n >= 10 and share_f > GEO_SUSPECTED_SHARE,
            "high_conf_parasitic_ge_2": high_conf_parasitic >= 2,
            "sparse_80_current": n < 10 and n >= 3 and share_f >= 0.80,
            "geo_risk_elevated": profile.geo_risk >= GEO_RISK_ELEVATED,
        },
    }


def generate_seed_queries(role: str, meta: PageMetadata, *, limit: int = 12) -> list[str]:
    category = _normalize_category(meta.category)
    ctx = {
        "entity": meta.entity,
        "category": category,
        "topic": meta.topic,
        "price": meta.price_hint,
        "org": meta.org,
    }
    if role == "commercial_product":
        templates = PRODUCT_SEED_TEMPLATES
    elif role == "editorial":
        templates = EDITORIAL_SEED_TEMPLATES
    elif role == "institutional":
        templates = INSTITUTIONAL_SEED_TEMPLATES
    else:
        templates = INFORMATIONAL_SEED_TEMPLATES

    queries: list[str] = []
    for tpl in templates:
        try:
            q = tpl.format(**ctx).strip()
        except KeyError:
            continue
        if q and q not in queries:
            queries.append(q)
        if len(queries) >= limit:
            break

    # Ensure discussion seeds for commercial / listicle-shaped pages even when
    # the primary template table is short or informational.
    if role in (
        "commercial_product",
        "editorial",
        "expert_listicle",
        "review_profile",
        "factual_blog",
    ):
        for tpl in DISCUSSION_SEED_TEMPLATES:
            if len(queries) >= limit:
                break
            try:
                q = tpl.format(**ctx).strip()
            except KeyError:
                continue
            if q and q not in queries:
                queries.append(q)

    return queries[:limit]


_ORG_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "for",
        "our",
        "your",
        "best",
        "top",
        "new",
        "www",
        "home",
        "store",
        "shop",
        "product",
        "products",
        "review",
        "reviews",
        "guide",
        "blog",
        "cheap",
        "budget",
        "laptops",
        "laptop",
        "headphones",
        "vpn",
        "software",
        "topic",
        "topics",
        "forum",
        "forums",
        "community",
        "discussion",
        "thread",
        "threads",
        "index",
        "messages",
        "posts",
        "members",
        "users",
        "directory",
    }
)

_GENERIC_TOPIC_PATTERNS = (
    re.compile(r"^the\s+best\s+", re.I),
    re.compile(r"^best\s+", re.I),
    re.compile(r"^top\s+", re.I),
    re.compile(r"^cheap(est)?\s+", re.I),
    re.compile(r"^budget\s+", re.I),
    re.compile(r"\bbuying guide\b", re.I),
    re.compile(r"\bpicks?\b", re.I),
    re.compile(r"we'?ve tested", re.I),
    re.compile(r"\bfor\s+20\d{2}\b", re.I),
    re.compile(r"\breview(ed|s)?\b", re.I),
    re.compile(r"\bcomparison(s)?\b", re.I),
    re.compile(r"\bvs\.?\b", re.I),
)


def _is_generic_topic_marker(marker: str) -> bool:
    """True for listicle slugs and headline boilerplate — not target-specific ties."""
    from anti_geo.claim_entity import is_weak_verify_marker

    text = " ".join(marker.strip().lower().split())
    if not text:
        return True
    if is_weak_verify_marker(text):
        return True
    return any(pattern.search(text) for pattern in _GENERIC_TOPIC_PATTERNS)


def _distinctive_markers(
    target_url: str,
    entity: str,
    org: str,
    aliases: list[str] | None = None,
) -> list[str]:
    """Publisher, org, or product tokens that identify the target — not generic topics."""
    markers: list[str] = []
    domain = registrable_domain(urlparse(target_url).netloc)
    publisher = domain.split(".")[0] if domain else ""
    if len(publisher) >= 4 and publisher not in _ORG_STOPWORDS:
        markers.append(publisher)

    candidates: list[str] = []
    if org:
        candidates.append(org)
    if entity:
        candidates.append(entity)
        for chunk in re.split(r"[\|\-–—:]", entity):
            candidates.append(chunk)
    if aliases:
        candidates.extend(aliases)

    for raw in candidates:
        text = " ".join(raw.strip().lower().split())
        if not text or text in _ORG_STOPWORDS:
            continue
        if _is_generic_topic_marker(text):
            continue
        # Single generic category nouns are weak ties.
        if " " not in text and text in _ORG_STOPWORDS:
            continue
        if 4 <= len(text) <= 80:
            markers.append(text)
        compact = re.sub(r"[^a-z0-9]", "", text)
        if 5 <= len(compact) <= 80:
            markers.append(compact)
    return list(dict.fromkeys(markers))


def _target_cited_in_response(cited_urls: list[str], target_url: str) -> bool:
    target_norm = target_url.rstrip("/").lower()
    target_path = urlparse(target_url).path.rstrip("/").lower()
    for url in cited_urls:
        u = url.rstrip("/").lower()
        if u == target_norm:
            return True
        if target_path and target_path in urlparse(url).path.lower():
            return True
    return False


def _citation_domain_mix(citations: set[str]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for url in citations:
        role = classify_content_role(url)
        mix[role] = mix.get(role, 0) + 1
    return mix


def _commercial_roles() -> frozenset[str]:
    return frozenset({"commercial_product", "review_profile", "expert_listicle"})


def assess_semantic_alignment(
    target_role: str,
    verified: list[VerifiedReferrer],
    *,
    target_commercial_tier: str = "none",
) -> SemanticAlignment:
    """Lightweight alignment check: target page tier vs verified referrer roles."""
    if not verified:
        return SemanticAlignment(
            target_commercial_tier=target_commercial_tier,
            referrer_commercial_share=0.0,
            aligned=True,
            label="inconclusive",
        )

    commercial = _commercial_roles()
    n = len(verified)
    commercial_n = sum(1 for r in verified if r.role in commercial)
    share = commercial_n / n

    target_is_commercial = target_role in commercial or target_commercial_tier in (
        "low",
        "medium",
        "high",
    )
    target_is_editorial = target_role in ("editorial", "institutional", "factual_blog")

    if target_is_editorial and share >= 0.7 and commercial_n >= 2:
        return SemanticAlignment(
            target_commercial_tier=target_commercial_tier,
            referrer_commercial_share=share,
            aligned=False,
            label="coordinated_commercial",
        )
    if target_is_commercial and share < 0.3 and n >= 3:
        return SemanticAlignment(
            target_commercial_tier=target_commercial_tier,
            referrer_commercial_share=share,
            aligned=False,
            label="mismatch",
        )
    return SemanticAlignment(
        target_commercial_tier=target_commercial_tier,
        referrer_commercial_share=share,
        aligned=True,
        label="aligned",
    )


def _verify_connection(
    html: str,
    text: str,
    target_url: str,
    entity: str,
    *,
    org: str = "",
    aliases: list[str] | None = None,
) -> ReferrerConnection | None:
    """Return a referrer tie only for explicit links or distinctive brand/publisher mentions."""
    blob = (html + " " + text).lower()
    parsed = urlparse(target_url)
    target_domain = registrable_domain(parsed.netloc)
    path = parsed.path.lower().strip("/")
    target_norm = target_url.rstrip("/").lower()

    if target_norm in blob:
        return ReferrerConnection("url_link", "high", target_norm)
    if target_domain in blob and path and path in blob:
        return ReferrerConnection("url_link", "high", f"{target_domain}/{path}")
    host_path = f"{parsed.netloc.lower()}{parsed.path}".lower()
    if host_path in blob:
        return ReferrerConnection("url_link", "high", host_path)

    for marker in _distinctive_markers(target_url, entity, org, aliases=aliases):
        if marker in blob:
            return ReferrerConnection("brand_mention", "weak", marker)
    return None


_LLM_CONN_MIN_CHARS = 120
_LLM_CONN_EXCERPT = 1800


def _llm_connection_tokens(
    target_url: str,
    entity: str,
    org: str = "",
    aliases: list[str] | None = None,
) -> list[str]:
    tokens: list[str] = []
    for raw in _distinctive_markers(target_url, entity, org, aliases=aliases):
        tokens.append(raw)
        tokens.extend(p for p in re.split(r"[\s\-_/]+", raw) if len(p) >= 4)
    return list(dict.fromkeys(tokens))


def _worth_llm_connection_check(
    blob: str,
    target_url: str,
    entity: str,
    *,
    org: str = "",
    aliases: list[str] | None = None,
) -> bool:
    """Cheap lexical gate so we only spend an LLM call on near-miss pages."""
    if len(blob) < _LLM_CONN_MIN_CHARS:
        return False
    tokens = _llm_connection_tokens(target_url, entity, org, aliases)
    if not tokens:
        return False
    compact = re.sub(r"[^a-z0-9]", "", blob)
    for tok in tokens:
        if tok in blob:
            return True
        compact_tok = re.sub(r"[^a-z0-9]", "", tok)
        if len(compact_tok) >= 4 and compact_tok in compact:
            return True
    return False


def _llm_verify_connection(
    html: str,
    text: str,
    target_url: str,
    entity: str,
    *,
    org: str = "",
    aliases: list[str] | None = None,
) -> ReferrerConnection | None:
    blob = f"{html}\n{text}".strip()
    if not blob:
        return None
    alias_bit = ", ".join(aliases or []) or "(none)"
    messages = [
        {
            "role": "system",
            "content": (
                "You audit whether a web page refers to a specific target site or brand. "
                "Return JSON only: "
                '{"refers":true|false,"marker":"short evidence quote","reason":"..."}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"target_url: {target_url}\n"
                f"entity: {entity}\n"
                f"organization: {org or '(none)'}\n"
                f"aliases: {alias_bit}\n\n"
                "Question: Does this page refer to that target (link, brand, product, "
                "or clear paraphrase)? Do not count generic topic overlap alone "
                "(e.g. 'best ad blockers' without naming the publisher/product).\n"
                "If refers=true, marker must be a short verbatim quote from the page.\n\n"
                f"page_excerpt:\n{blob[:_LLM_CONN_EXCERPT]}"
            ),
        },
    ]
    payload = chat_completion_json(messages, config=load_azure_config())
    refers = payload.get("refers")
    if refers is True or (isinstance(refers, str) and refers.strip().lower() in ("true", "yes")):
        marker = " ".join(str(payload.get("marker") or "").split())[:160]
        if not marker:
            marker = "llm_paraphrase"
        return ReferrerConnection("llm_mention", "weak", marker)
    return None


def verify_connection(
    html: str,
    text: str,
    target_url: str,
    entity: str,
    *,
    org: str = "",
    aliases: list[str] | None = None,
    use_llm: bool | None = None,
) -> ReferrerConnection | None:
    """Deterministic connection check, then optional Azure LLM backup for paraphrases.

    Weak ``brand_mention`` hits are LLM-confirmed when enabled: ``refers=false``
    drops the tie; errors fail-open (keep heuristic). High-confidence
    ``url_link`` hits are never LLM-audited.
    """
    conn = _verify_connection(
        html, text, target_url, entity, org=org, aliases=aliases
    )
    llm_enabled = is_azure_configured() if use_llm is None else use_llm

    if conn is not None:
        if (
            conn.kind == "url_link"
            or conn.confidence == "high"
            or not llm_enabled
            or conn.kind != "brand_mention"
        ):
            return conn
        # Weak brand_mention → confirm with LLM; fail-open on errors.
        try:
            confirmed = _llm_verify_connection(
                html, text, target_url, entity, org=org, aliases=aliases
            )
        except Exception as exc:
            logger.warning("LLM brand_mention confirm failed (keeping heuristic): %s", exc)
            return conn
        if confirmed is None:
            return None
        return conn

    if not llm_enabled:
        return None

    blob = (html + " " + text).lower()
    if not _worth_llm_connection_check(
        blob, target_url, entity, org=org, aliases=aliases
    ):
        return None

    try:
        return _llm_verify_connection(
            html, text, target_url, entity, org=org, aliases=aliases
        )
    except Exception as exc:
        logger.warning("LLM connection verify failed: %s", exc)
        return None


def _role_for_url(url: str, fetch: FetchResult | None = None) -> str:
    return classify_content_role(url, fetch=fetch)


def _apply_referrer_content_scores(
    verified: list[VerifiedReferrer],
    summary: ReferrerContentSummary,
    candidates: list[ReferrerExcerptCandidate] | None = None,
) -> None:
    """Backfill triage channels on all verified; overlay L1 fields on scored eligible."""
    cand_by_url = {
        c.url.rstrip("/").lower(): c for c in (candidates or [])
    }
    for ref in verified:
        key = ref.url.rstrip("/").lower()
        cand = cand_by_url.get(key)
        if cand is not None:
            ref.content_manipulability = cand.manipulability
            ref.content_thread_surface = cand.thread_surface
            ref.content_editability = cand.editability

    by_url = {s.url.rstrip("/").lower(): s for s in summary.scores if s.scored}
    for ref in verified:
        hit = by_url.get(ref.url.rstrip("/").lower())
        if hit is None:
            continue
        ref.content_scored = True
        ref.content_high_risk = hit.high_risk
        ref.content_semantic_risk = hit.semantic_risk
        ref.content_flags = list(hit.content_flags)
        ref.content_manipulability = hit.manipulability
        ref.content_thread_surface = hit.thread_surface
        ref.content_editability = hit.editability
        ref.content_segment_role = hit.segment_role


_RELATED_BRAND_STEM_MIN = 4


def _is_same_brand(referrer_url: str, target_url: str) -> bool:
    r = registrable_domain(urlparse(referrer_url).netloc)
    t = registrable_domain(urlparse(target_url).netloc)
    return bool(r) and r == t


def _domain_stem(registrable: str) -> str:
    """First label of a registrable domain, hyphens stripped for compare."""
    label = (registrable or "").split(".", 1)[0].lower()
    return label.replace("-", "")


def _looks_related_brand(url_a: str, url_b: str) -> bool:
    """True when registrable domains differ but share a long enough stem."""
    a = registrable_domain(urlparse(url_a).netloc)
    b = registrable_domain(urlparse(url_b).netloc)
    if not a or not b or a == b:
        return False
    stem_a = _domain_stem(a)
    stem_b = _domain_stem(b)
    if len(stem_a) < _RELATED_BRAND_STEM_MIN or len(stem_b) < _RELATED_BRAND_STEM_MIN:
        return False
    return stem_a == stem_b


def _llm_same_brand(referrer_url: str, target_url: str) -> bool | None:
    """Ask Azure whether two URLs are the same brand/org. None on failure."""
    ref_reg = registrable_domain(urlparse(referrer_url).netloc)
    tgt_reg = registrable_domain(urlparse(target_url).netloc)
    messages = [
        {
            "role": "system",
            "content": (
                "You decide whether two web URLs belong to the same brand, "
                "organization, or owned property (including regional TLDs and "
                "brand microsites). Return JSON only: "
                '{"same_brand":true|false,"reason":"..."}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"referrer_url: {referrer_url}\n"
                f"referrer_domain: {ref_reg}\n"
                f"target_url: {target_url}\n"
                f"target_domain: {tgt_reg}\n\n"
                "Are these the same brand/organization? "
                "same_brand=true only for owned properties of one org; "
                "false for unrelated sites that merely share a name stem."
            ),
        },
    ]
    payload = chat_completion_json(messages, config=load_azure_config())
    raw = payload.get("same_brand")
    if raw is True or (isinstance(raw, str) and raw.strip().lower() in ("true", "yes")):
        return True
    if raw is False or (isinstance(raw, str) and raw.strip().lower() in ("false", "no")):
        return False
    return None


def _should_skip_same_brand(
    referrer_url: str,
    target_url: str,
    *,
    use_llm: bool | None = None,
    cache: dict[tuple[str, str], bool] | None = None,
) -> bool:
    """Skip same-brand cites: exact eTLD+1 match, or LLM on related-looking stems.

    Related-looking domains with LLM unavailable/error are treated as external
    (do not skip) so real third-party referrers are not hidden.
    """
    ref_reg = registrable_domain(urlparse(referrer_url).netloc)
    tgt_reg = registrable_domain(urlparse(target_url).netloc)
    cache_key = (ref_reg, tgt_reg)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    if _is_same_brand(referrer_url, target_url):
        if cache is not None:
            cache[cache_key] = True
        return True

    if not _looks_related_brand(referrer_url, target_url):
        if cache is not None:
            cache[cache_key] = False
        return False

    llm_enabled = is_azure_configured() if use_llm is None else use_llm
    if not llm_enabled:
        if cache is not None:
            cache[cache_key] = False
        return False

    try:
        verdict = _llm_same_brand(referrer_url, target_url)
    except Exception as exc:
        logger.warning("LLM same_brand check failed (treating as external): %s", exc)
        verdict = None

    skip = verdict is True
    if cache is not None:
        cache[cache_key] = skip
    return skip


@dataclass
class _DiscoveryState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    citations: set[str] = field(default_factory=set)
    citation_sources: dict[str, str] = field(default_factory=dict)
    queries_run: int = 0
    target_cited: int = 0
    verified: list[VerifiedReferrer] = field(default_factory=list)
    seen_verified: set[str] = field(default_factory=set)
    fetched_ok: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    stopped_early: bool = False
    excerpt_candidates: list[ReferrerExcerptCandidate] = field(default_factory=list)
    same_brand_cache: dict[tuple[str, str], bool] = field(default_factory=dict)


def parasitic_count_from_verified(verified: list[VerifiedReferrer]) -> int:
    """Unweighted count of potential parasitic GEO referrers."""
    return sum(
        1
        for ref in verified
        if is_parasitic_referrer(
            url=ref.url,
            role=ref.role,
            content_high_risk=ref.content_high_risk,
        )
    )


def high_conf_parasitic_count_from_verified(
    verified: list[VerifiedReferrer],
) -> int:
    """Parasitic surfaces that also have entity-scoped high-risk content (planted / L1)."""
    return sum(
        1
        for ref in verified
        if ref.content_high_risk
        and is_parasitic_referrer(
            url=ref.url,
            role=ref.role,
            content_high_risk=True,
        )
    )


def parasitic_share_from_verified(
    verified: list[VerifiedReferrer],
) -> float | None:
    """Parasitic proportion among verified referrers; None when N is 0."""
    n = len(verified)
    if n <= 0:
        return None
    return parasitic_count_from_verified(verified) / n


def _editorial_institutional_count(mix: dict[str, int]) -> int:
    return mix.get("editorial", 0) + mix.get("institutional", 0)


def parasitic_soft_downrank_band(profile: ReferralProfile) -> bool:
    """True when parasitic share is elevated but below geo_suspected hard flag.

    Soft band: N >= 10, editorial/institutional absent, share in
    [GEO_SOFT_SHARE_LO, GEO_SOFT_SHARE_HI]. Hard geo_suspected uses share >
    GEO_SUSPECTED_SHARE with the same editorial/N constraints.
    """
    n = profile.n_verified
    if n < 10 or _editorial_institutional_count(profile.mix) > 0:
        return False
    share = parasitic_share_from_verified(profile.referrers_verified)
    return (
        share is not None
        and GEO_SOFT_SHARE_LO <= share <= GEO_SOFT_SHARE_HI
    )


# Content intensifier: +0.1 geo_risk per high-conf parasitic, capped.
GEO_RISK_HIGH_CONF_BOOST = 0.1
GEO_RISK_HIGH_CONF_BOOST_CAP = 0.25
# Elevate with slightly lower raw parasitic count when content confirms plants.
GEO_ELEVATED_HIGH_CONF_MIN = 2
GEO_ELEVATED_HIGH_CONF_PARASITIC_MIN = 2


def compute_referral_geo_risk(
    *,
    n_verified: int,
    parasitic_count: int,
    parasitic_share: float | None,
    editorial_count: int,
    high_conf_parasitic: int = 0,
) -> float:
    """Continuous [0, 1] referral GEO risk from parasitic share + raw count.

    Share weighs more as N grows; count helps small-N campaigns. Real
    editorial/institutional referrers dampen (Meta brake) without a hard
    binary gate that misreads scam-blogs as editorial. High-conf parasitic
    (surface + content_high_risk) adds a small additive boost.
    """
    if n_verified <= 0:
        return 0.0
    share = float(parasitic_share or 0.0)
    count_score = min(1.0, parasitic_count / 5.0)
    share_w = 0.35 + 0.35 * min(1.0, n_verified / 10.0)
    count_w = 1.0 - share_w
    raw = share_w * share + count_w * count_score
    if editorial_count > 0:
        editorial_share = editorial_count / n_verified
        raw *= max(
            0.25,
            1.0 - 0.55 * min(1.0, float(editorial_count)) - 0.35 * editorial_share,
        )
    if high_conf_parasitic > 0:
        raw += min(
            GEO_RISK_HIGH_CONF_BOOST_CAP,
            GEO_RISK_HIGH_CONF_BOOST * float(high_conf_parasitic),
        )
    return round(min(1.0, max(0.0, raw)), 4)


def derive_geo_elevated(
    *,
    geo_suspected: bool | None,
    geo_risk: float,
    n_verified: int,
    parasitic_count: int,
    editorial_count: int,
    status: str,
    soft_share_band: bool,
    high_conf_parasitic: int = 0,
) -> bool:
    """Soft elevate: never silent pass; does not imply hard geo_suspected."""
    if geo_suspected is True:
        return False
    if soft_share_band or status == "sparse_suspicious":
        return True
    if geo_risk >= GEO_RISK_ELEVATED:
        return True
    if (
        parasitic_count >= GEO_ELEVATED_MIN_PARASITIC
        and n_verified >= GEO_ELEVATED_MIN_N
        and editorial_count == 0
    ):
        return True
    # Content-confirmed plants: elevate with a slightly lower parasitic count.
    if (
        high_conf_parasitic >= GEO_ELEVATED_HIGH_CONF_MIN
        and parasitic_count >= GEO_ELEVATED_HIGH_CONF_PARASITIC_MIN
        and n_verified >= GEO_ELEVATED_MIN_N
        and editorial_count == 0
    ):
        return True
    return False


def _referral_mix_decisive(verified: list[VerifiedReferrer]) -> bool:
    """True when parasitic/editorial mix is already enough to stop early (Mode A fast)."""
    n = len(verified)
    if n < 8:
        return False
    mix: dict[str, int] = {}
    for ref in verified:
        mix[ref.role] = mix.get(ref.role, 0) + 1
    editorial = mix.get("editorial", 0) + mix.get("institutional", 0)
    share = parasitic_share_from_verified(verified) or 0.0
    if share >= 0.8 and editorial == 0:
        return True
    if n >= 10 and editorial > 0:
        return True
    return False


def _verified_cap_reached(
    state: _DiscoveryState,
    *,
    min_seeds: int,
    max_verified: int,
    adaptive_stop: bool = False,
) -> bool:
    # Stop as soon as we hit the verified target (min_seeds kept for call-site compat).
    del min_seeds
    if max_verified > 0 and len(state.verified) >= max_verified:
        return True
    if adaptive_stop and _referral_mix_decisive(state.verified):
        return True
    return False


def _engine_query_with_heartbeat(
    engine: EngineAdapter,
    query: str,
    *,
    prog: Progress,
    status_prefix: str,
    interval_s: float = 2.0,
):
    """Run engine.query while refreshing status so long Azure waits don't look hung."""
    t0 = time.monotonic()
    done = threading.Event()

    def _beat() -> None:
        while not done.wait(interval_s):
            waited = int(time.monotonic() - t0)
            prog.set_status(f"{status_prefix} waiting Azure {waited}s")

    thread = threading.Thread(target=_beat, name="anti-geo-azure-beat", daemon=True)
    thread.start()
    try:
        return engine.query(query)
    finally:
        done.set()
        thread.join(timeout=interval_s + 0.5)


def _report_verified(
    prog: Progress,
    state: _DiscoveryState,
    max_verified: int,
    status: str,
) -> None:
    with state.lock:
        n = len(state.verified)
    prog.set_counts(n, max_verified, status=status)


def _parallel_fetch_candidates(
    *,
    candidates: list[str],
    seed_query: str,
    seed_idx: int,
    n_seeds: int,
    target_url: str,
    entity: str,
    org: str,
    max_fetches_per_seed: int,
    max_verified_referrers: int,
    min_seeds_before_verified_stop: int,
    state: _DiscoveryState,
    fetch_workers: int,
    prog: Progress,
    stop: threading.Event,
    adaptive_stop: bool = False,
    aliases: list[str] | None = None,
    use_llm_connection: bool | None = None,
) -> None:
    """Fetch citation pages concurrently; cap on successful fetches and verified total."""
    if not candidates:
        return

    workers = max(1, fetch_workers)
    ok_fetches = 0
    hit_fetch_cap = False
    pending: dict[Future, str] = {}
    cand_iter = iter(candidates)

    def _at_success_budget() -> bool:
        # Reserve in-flight slots so parallel workers cannot overshoot the ok-fetch cap.
        return ok_fetches + len(pending) >= max_fetches_per_seed

    def _should_stop_submitting() -> bool:
        if stop.is_set():
            return True
        if _at_success_budget():
            return True
        with state.lock:
            return _verified_cap_reached(
                state,
                min_seeds=min_seeds_before_verified_stop,
                max_verified=max_verified_referrers,
                adaptive_stop=adaptive_stop,
            )

    def _submit_more(pool: ThreadPoolExecutor) -> None:
        while len(pending) < workers and not _should_stop_submitting():
            try:
                url = next(cand_iter)
            except StopIteration:
                return
            norm = url.rstrip("/").lower()
            with state.lock:
                already = norm in state.fetched_ok
            if already:
                continue
            pending[pool.submit(fetch_page, url, timeout=12.0)] = url

    with ThreadPoolExecutor(max_workers=workers) as pool:
        _submit_more(pool)
        while pending:
            done, _ = wait(set(pending), return_when=FIRST_COMPLETED)
            for fut in done:
                url = pending.pop(fut)
                short = f"seed {seed_idx + 1}/{n_seeds}"
                try:
                    fr = fut.result()
                except Exception as exc:
                    with state.lock:
                        state.errors.append(f"fetch failed ({url}): {exc}")
                    _report_verified(
                        prog,
                        state,
                        max_verified_referrers,
                        f"{short} fetch error",
                    )
                    _submit_more(pool)
                    continue

                if not fr.ok:
                    _report_verified(
                        prog,
                        state,
                        max_verified_referrers,
                        f"{short} fetch fail",
                    )
                    _submit_more(pool)
                    continue

                # Hard cap: ignore extra successes if a race slipped through.
                if ok_fetches >= max_fetches_per_seed:
                    hit_fetch_cap = True
                    continue

                cited_norm = url.rstrip("/").lower()
                final = (fr.final_url or url).rstrip("/")
                conn = verify_connection(
                    fr.text,
                    fr.text,
                    target_url,
                    entity,
                    org=org,
                    aliases=aliases,
                    use_llm=use_llm_connection,
                )
                with state.lock:
                    state.fetched_ok.add(cited_norm)
                    ok_fetches += 1
                    if ok_fetches >= max_fetches_per_seed:
                        hit_fetch_cap = True
                    if final.lower() not in state.seen_verified and conn:
                        state.seen_verified.add(final.lower())
                        ref_url = fr.final_url or url
                        role = _role_for_url(ref_url, fr)
                        state.verified.append(
                            VerifiedReferrer(
                                url=ref_url,
                                role=role,
                                connection=conn.kind,
                                connection_confidence=conn.confidence,
                                matched_marker=conn.marker,
                                seed_query=seed_query,
                            )
                        )
                        state.excerpt_candidates.append(
                            build_excerpt_candidate(
                                ref_url,
                                role=role,
                                text=fr.text or "",
                                segments=list(fr.segments or []),
                                entity=entity,
                                marker=conn.marker,
                            )
                        )
                    if _verified_cap_reached(
                        state,
                        min_seeds=min_seeds_before_verified_stop,
                        max_verified=max_verified_referrers,
                        adaptive_stop=adaptive_stop,
                    ):
                        state.stopped_early = True
                        stop.set()
                    verified_n = len(state.verified)

                _report_verified(
                    prog,
                    state,
                    max_verified_referrers,
                    f"{short} ok_fetch={ok_fetches}/{max_fetches_per_seed} "
                    f"· verified={verified_n}",
                )
                _submit_more(pool)

            if _should_stop_submitting() and not pending:
                break

    if hit_fetch_cap:
        with state.lock:
            state.errors.append(
                f"per-seed fetch cap reached ({max_fetches_per_seed}) for: {seed_query[:40]}"
            )


def discover_referrers(
    target_url: str,
    entity: str,
    seed_queries: list[str],
    engine: EngineAdapter | None,
    *,
    org: str = "",
    aliases: list[str] | None = None,
    max_fetches_per_seed: int = 30,
    max_verified_referrers: int = 50,
    min_seeds_before_verified_stop: int = 4,
    query_delay_s: float = 0.0,
    target_role: str = "unknown",
    target_commercial_tier: str = "none",
    progress: Progress | None = None,
    seed_workers: int = 4,
    fetch_workers: int = 8,
    adaptive_stop: bool = False,
    use_llm_connection: bool | None = None,
) -> ReferralProfile:
    prog = progress or NullProgress()
    if engine is None:
        return ReferralProfile(
            status="skipped",
            discovery_status="skipped",
            confidence="low",
            notes=["Referral discovery skipped (no engine). L1-L3 verdict only."],
        )

    state = _DiscoveryState()
    stop = threading.Event()
    n_seeds = len(seed_queries)
    seed_workers = max(1, min(seed_workers, n_seeds or 1))
    fetch_workers = max(1, fetch_workers)
    query_gate = threading.Lock()
    last_query_start = 0.0

    prog.set_counts(
        0,
        max_verified_referrers,
        status=(
            f"discover 0/{n_seeds} seeds · seed_workers={seed_workers} "
            f"fetch_workers={fetch_workers}"
        ),
    )

    def _process_seed(seed_idx: int, q: str) -> None:
        nonlocal last_query_start
        if stop.is_set():
            return

        short_q = q if len(q) <= 42 else q[:39] + "..."
        status_prefix = (
            f"seed {seed_idx + 1}/{n_seeds} engine · verified={len(state.verified)} · {short_q}"
        )
        _report_verified(prog, state, max_verified_referrers, status_prefix)

        with query_gate:
            if query_delay_s > 0 and last_query_start > 0:
                wait_s = query_delay_s - (time.monotonic() - last_query_start)
                if wait_s > 0:
                    time.sleep(wait_s)
            last_query_start = time.monotonic()

        try:
            resp = _engine_query_with_heartbeat(
                engine,
                q,
                prog=prog,
                status_prefix=status_prefix,
            )
        except Exception as exc:
            with state.lock:
                state.errors.append(f"engine query failed ({q[:40]}...): {exc}")
            _report_verified(
                prog,
                state,
                max_verified_referrers,
                f"seed {seed_idx + 1}/{n_seeds} engine failed",
            )
            return

        with state.lock:
            state.queries_run += 1
            if _target_cited_in_response(resp.cited_urls, target_url):
                state.target_cited += 1
            for url in resp.cited_urls:
                state.citations.add(url)
                state.citation_sources.setdefault(url, q)
            if _verified_cap_reached(
                state,
                min_seeds=min_seeds_before_verified_stop,
                max_verified=max_verified_referrers,
                adaptive_stop=adaptive_stop,
            ):
                # Cap already met by other workers — skip new fetches.
                state.stopped_early = True
                stop.set()

        _report_verified(
            prog,
            state,
            max_verified_referrers,
            f"seed {seed_idx + 1}/{n_seeds} citations={len(resp.cited_urls)}",
        )

        if stop.is_set():
            return

        candidates: list[str] = []
        for cited in resp.cited_urls:
            cited_norm = cited.rstrip("/").lower()
            if cited_norm == target_url.rstrip("/").lower():
                continue
            # Cache lookup under lock; LLM (if any) runs outside the lock.
            ref_reg = registrable_domain(urlparse(cited).netloc)
            tgt_reg = registrable_domain(urlparse(target_url).netloc)
            cache_key = (ref_reg, tgt_reg)
            with state.lock:
                cached = state.same_brand_cache.get(cache_key)
            if cached is None:
                skip_brand = _should_skip_same_brand(
                    cited,
                    target_url,
                    use_llm=use_llm_connection,
                    cache=None,
                )
                with state.lock:
                    state.same_brand_cache.setdefault(cache_key, skip_brand)
                    skip_brand = state.same_brand_cache[cache_key]
            else:
                skip_brand = cached
            if skip_brand:
                continue
            with state.lock:
                already = cited_norm in state.fetched_ok
            if already:
                continue
            candidates.append(cited)
        random.shuffle(candidates)

        _parallel_fetch_candidates(
            candidates=candidates,
            seed_query=q,
            seed_idx=seed_idx,
            n_seeds=n_seeds,
            target_url=target_url,
            entity=entity,
            org=org,
            aliases=aliases,
            max_fetches_per_seed=max_fetches_per_seed,
            max_verified_referrers=max_verified_referrers,
            min_seeds_before_verified_stop=min_seeds_before_verified_stop,
            state=state,
            fetch_workers=fetch_workers,
            prog=prog,
            stop=stop,
            adaptive_stop=adaptive_stop,
            use_llm_connection=use_llm_connection,
        )

        if state.stopped_early:
            stop.set()

    with ThreadPoolExecutor(max_workers=seed_workers) as pool:
        futures = [
            pool.submit(_process_seed, i, q) for i, q in enumerate(seed_queries)
        ]
        for fut in futures:
            try:
                fut.result()
            except Exception as exc:
                with state.lock:
                    state.errors.append(f"seed worker failed: {exc}")

    if state.stopped_early:
        with state.lock:
            if not any("Stopped after" in n for n in state.notes):
                reason = f"cap {max_verified_referrers}"
                if adaptive_stop and _referral_mix_decisive(state.verified):
                    reason = "adaptive mix decisive"
                state.notes.append(
                    f"Stopped after {state.queries_run} seeds: {len(state.verified)} "
                    f"verified referrers ({reason})."
                )

    citations = state.citations
    errors = state.errors
    notes = state.notes
    queries_run = state.queries_run
    target_cited = state.target_cited
    verified = state.verified

    content_summary = score_top_referrers(state.excerpt_candidates, entity=entity)
    _apply_referrer_content_scores(
        verified, content_summary, candidates=state.excerpt_candidates
    )
    notes.extend(content_summary.notes)

    domain_mix = _citation_domain_mix(citations)

    if not citations and errors:
        return ReferralProfile(
            status="inconclusive",
            discovery_status="failed",
            confidence="low",
            citations_sampled=0,
            seed_queries_run=queries_run,
            citations_domain_mix=domain_mix,
            discovery_errors=errors,
            notes=["Discovery failed; do not treat as zero referrers."],
        )

    mix: dict[str, int] = {}
    for ref in verified:
        mix[ref.role] = mix.get(ref.role, 0) + 1

    n = len(verified)
    discovery_status = "success" if not errors else ("partial" if n or citations else "failed")
    alignment = assess_semantic_alignment(
        target_role,
        verified,
        target_commercial_tier=target_commercial_tier,
    )

    if target_cited > 0:
        notes.append(
            f"Target cited in {target_cited}/{queries_run} seed answers "
            "(AI-visible footprint, not a verified referrer)."
        )
    if alignment.label == "coordinated_commercial":
        notes.append(
            "Verified referrers skew commercial while target is editorial — "
            "possible coordinated promotion pattern."
        )
    elif alignment.label == "mismatch":
        notes.append(
            "Verified referrers skew non-commercial while target is product/commercial."
        )

    if n == 0 and errors:
        return ReferralProfile(
            status="inconclusive",
            discovery_status=discovery_status,
            confidence="low",
            citations_sampled=len(citations),
            seed_queries_run=queries_run,
            target_cited_in_answers=target_cited,
            citations_domain_mix=domain_mix,
            semantic_alignment=alignment,
            discovery_errors=errors,
            notes=notes or ["No verified referrers; discovery may be incomplete."],
        )

    if n == 0:
        if not notes:
            notes = [
                "No verified referrers after checking citations. Parasitic GEO footprint unlikely."
            ]
        if target_cited > 0:
            notes.append(
                "AI-cited with zero verified referrers — soft caution "
                "(milder than young-domain WHOIS; action may downrank)."
            )
        return ReferralProfile(
            status="sparse",
            discovery_status="success",
            confidence="medium",
            citations_sampled=len(citations),
            seed_queries_run=queries_run,
            target_cited_in_answers=target_cited,
            citations_domain_mix=domain_mix,
            semantic_alignment=alignment,
            n_verified=0,
            mix={},
            geo_suspected=False,
            notes=notes,
        )

    editorial = _editorial_institutional_count(mix)
    parasitic_share = parasitic_share_from_verified(verified) or 0.0
    parasitic_count = parasitic_count_from_verified(verified)
    high_conf_parasitic = high_conf_parasitic_count_from_verified(verified)
    geo_risk = compute_referral_geo_risk(
        n_verified=n,
        parasitic_count=parasitic_count,
        parasitic_share=parasitic_share,
        editorial_count=editorial,
        high_conf_parasitic=high_conf_parasitic,
    )

    status = "sparse"
    confidence = "low"
    geo_suspected: bool | None = False
    soft_share_note = False

    if n >= 20:
        status = "complete"
        confidence = "medium"
        if parasitic_share > GEO_SUSPECTED_SHARE and editorial == 0:
            geo_suspected = True
            notes.append(
                "Parasitic-surface-heavy verified referrer mix with no editorial/institutional share."
            )
        elif editorial > 0:
            notes.append("Editorial/institutional referrers present — organic buzz likely for large brands.")
        elif editorial == 0 and GEO_SOFT_SHARE_LO <= parasitic_share <= GEO_SOFT_SHARE_HI:
            soft_share_note = True
            notes.append(
                f"Elevated parasitic-surface share ({int(GEO_SOFT_SHARE_LO*100)}–"
                f"{int(GEO_SOFT_SHARE_HI*100)}%) with no editorial/institutional "
                "— soft downrank band."
            )
    elif n >= 10:
        status = "sparse"
        confidence = "medium"
        if parasitic_share > GEO_SUSPECTED_SHARE and editorial == 0:
            geo_suspected = True
            notes.append(
                "Parasitic-surface-heavy referrer mix (medium N) with no editorial/institutional share."
            )
        elif editorial == 0 and GEO_SOFT_SHARE_LO <= parasitic_share <= GEO_SOFT_SHARE_HI:
            soft_share_note = True
            notes.append(
                f"Elevated parasitic-surface share ({int(GEO_SOFT_SHARE_LO*100)}–"
                f"{int(GEO_SOFT_SHARE_HI*100)}%, medium N) with no editorial/institutional "
                "— soft downrank band."
            )
    elif n < 10:
        status = "sparse"
        confidence = "low"
        if parasitic_share >= 0.8 and n >= 3:
            status = "sparse_suspicious"
            notes.append(
                "Small N but homogeneous parasitic surfaces — qualitative suspicion only, not auto-flag."
            )
        else:
            geo_suspected = False
            notes.append("N below mix threshold; profile judgment deferred to L1-L3 / geo_risk.")
    else:
        status = "sparse"
        confidence = "medium"

    if (
        alignment.label == "mismatch"
        and parasitic_share >= 0.8
        and n >= 5
        and editorial == 0
        and geo_suspected is not True
    ):
        geo_suspected = True
        notes.append(
            "Semantic mismatch: commercial target amplified via homogeneous "
            "non-commercial parasitic surfaces."
        )

    if alignment.label == "coordinated_commercial" and geo_suspected is not True:
        geo_suspected = None
        notes.append("Semantic alignment flag — review manually; not auto-convict.")

    soft_band = (
        soft_share_note
        or (
            n >= 10
            and editorial == 0
            and GEO_SOFT_SHARE_LO <= parasitic_share <= GEO_SOFT_SHARE_HI
        )
    )
    geo_elevated = derive_geo_elevated(
        geo_suspected=geo_suspected,
        geo_risk=geo_risk,
        n_verified=n,
        parasitic_count=parasitic_count,
        editorial_count=editorial,
        status=status,
        soft_share_band=soft_band,
        high_conf_parasitic=high_conf_parasitic,
    )
    if geo_elevated and geo_suspected is not True:
        notes.append(
            f"GEO elevated (geo_risk={geo_risk:.2f}, parasitic={parasitic_count}/{n}"
            + (
                f", high_conf={high_conf_parasitic}"
                if high_conf_parasitic
                else ""
            )
            + ") — soft downrank; not a hard geo_suspected convict."
        )

    return ReferralProfile(
        status=status,
        discovery_status=discovery_status,
        confidence=confidence,
        n_verified=n,
        mix=mix,
        citations_domain_mix=domain_mix,
        geo_suspected=geo_suspected,
        geo_risk=geo_risk,
        geo_elevated=geo_elevated,
        citations_sampled=len(citations),
        seed_queries_run=queries_run,
        target_cited_in_answers=target_cited,
        semantic_alignment=alignment,
        referrers_verified=verified,
        discovery_errors=errors,
        notes=notes,
        referrer_content_scored=content_summary.scored,
        referrer_content_high_risk=content_summary.high_risk_count,
        referrer_content_coordinated=content_summary.coordinated,
    )


def _mix_tighten_extras(
    profile: ReferralProfile,
    *,
    content_role: str,
    engine_cited: bool,
) -> list[str]:
    if profile.geo_suspected is True:
        return ["attribute_only", "block_endorsement"]
    if profile.status == "sparse_suspicious":
        return ["attribute_only"]
    if profile.geo_elevated or parasitic_soft_downrank_band(profile):
        return ["downrank"]
    if (
        profile.n_verified == 0
        and profile.discovery_status in ("success", "partial")
        and profile.status != "inconclusive"
        and content_role not in ("editorial", "institutional")
        and (engine_cited or profile.target_cited_in_answers > 0)
    ):
        return ["downrank"]
    return []


def tighten_actions_with_referral(
    primary: str,
    actions: list[str],
    profile: ReferralProfile | None,
    *,
    content_role: str = "",
    engine_cited: bool = False,
) -> tuple[str, list[str]]:
    """Tighten target actions from referrer mix + top-K referrer L1 evidence.

    Does not mutate the target's trust_score. Referrer content extras come from
    entity-scoped L1 on structurally manipulable referrers (not host allowlists).
    """
    if profile is None or profile.status == "skipped":
        return primary, list(actions)

    content_summary = ReferrerContentSummary(
        scored=profile.referrer_content_scored,
        high_risk_count=profile.referrer_content_high_risk,
        coordinated=profile.referrer_content_coordinated,
    )
    extra = [
        *_mix_tighten_extras(
            profile, content_role=content_role, engine_cited=engine_cited
        ),
        *referrer_content_tighten_extras(content_summary),
    ]
    if not extra:
        return primary, list(actions)
    return merge_llm_actions(primary, actions, *extra)


def _build_verdict(
    llm_action: str,
    profile: ReferralProfile,
    content_role: str,
) -> str:
    if profile.status == "skipped":
        return f"L1-L3 primary ({llm_action}); referral profile skipped."
    if profile.status == "inconclusive":
        return (
            f"L1-L3 primary ({llm_action}); "
            "referral profile inconclusive — do not infer clean."
        )
    if profile.geo_suspected:
        return (
            f"GEO suspected from structural parasitic-surface mix (referral tightened); "
            f"primary action: {llm_action}."
        )
    if profile.geo_elevated:
        return (
            f"GEO elevated (geo_risk={profile.geo_risk:.2f}; soft downrank, not hard convict); "
            f"primary action: {llm_action}."
        )
    if profile.referrer_content_high_risk >= 2 or profile.referrer_content_coordinated:
        return (
            f"High-risk referrer content "
            f"(scored={profile.referrer_content_scored}, "
            f"high_risk={profile.referrer_content_high_risk}, "
            f"coordinated={profile.referrer_content_coordinated}); "
            f"primary action: {llm_action}."
        )
    if profile.status == "sparse_suspicious":
        return (
            f"Sparse parasitic-surface footprint (referral tightened); "
            f"primary action: {llm_action}."
        )
    if profile.referrer_content_high_risk == 1:
        return (
            f"One high-risk referrer excerpt — soft downrank; "
            f"primary action: {llm_action}."
        )
    if parasitic_soft_downrank_band(profile):
        return (
            f"Elevated parasitic-surface share (40–60%, no editorial) — soft downrank; "
            f"primary action: {llm_action}."
        )
    if (
        profile.n_verified == 0
        and profile.discovery_status in ("success", "partial")
        and content_role not in ("editorial", "institutional")
        and profile.target_cited_in_answers > 0
    ):
        return (
            f"AI-cited with zero verified referrers (soft caution); "
            f"primary action: {llm_action}."
        )
    if content_role == "editorial":
        return (
            f"Editorial target — L1-L3 primary ({llm_action}); "
            "low external referrer N is expected."
        )
    return f"L1-L3 primary ({llm_action}); referral profile: {profile.status}."


def investigate_url(
    url: str,
    *,
    query_intent: str = "commercial",
    query: str | None = None,
    engine_name: str | None = None,
    seed_limit: int = 12,
    seed_mode: str = "auto",
    fixture_path: Path | None = None,
    query_delay_s: float = 0.0,
    max_fetches_per_seed: int = 30,
    max_verified_referrers: int = 50,
    min_seeds_before_verified_stop: int = 4,
    progress: Progress | None = None,
    seed_workers: int = 4,
    fetch_workers: int = 8,
    adaptive_stop: bool = False,
    use_llm_connection: bool | None = None,
    engine: EngineAdapter | None = None,
    fetch: FetchResult | None = None,
    single_page: UrlAnalysisReport | None = None,
    content_role: str | None = None,
    seed_pack: str = "default",
) -> InvestigationResult:
    """Mode B: L1-L3 + structural referral mix (UGC/editorial) → LLM actions.

    When ``fetch`` and ``single_page`` are provided (Mode A already scored the
    cite), skip the redundant target fetch + L1-L3 pass.
    """
    prog = progress or NullProgress()
    if fetch is not None and single_page is not None:
        prog.set_counts(0, max_verified_referrers, status="reuse scored cite")
        report = single_page
        source = report.source
        role = content_role or classify_content_role(
            url, fetch=fetch, source=source
        )
    else:
        prog.set_counts(0, max_verified_referrers, status="fetch target page")
        fetch = fetch_page(url)
        prog.set_status("score L1-L3")
        source = score_source(url, fetch, query=query)
        report = decide_single_source(source, query_intent, query=query)
        role = content_role or classify_content_role(
            url, fetch=fetch, source=source
        )
    meta = extract_page_metadata(fetch)
    prog.set_status("generate seed queries")
    seeds, seed_source, seed_conf = resolve_seed_queries(
        role,
        meta,
        url=fetch.final_url or url,
        fetch=fetch,
        source=source,
        limit=seed_limit,
        mode=seed_mode,
        seed_pack=seed_pack,
    )
    prog.set_status(f"seeds ready ({len(seeds)}, {seed_source})")

    resolved_engine = engine
    if resolved_engine is None and engine_name and engine_name != "none":
        resolved_engine = get_engine(engine_name, fixture_path=fixture_path)

    commercial_tier = "none"
    if source.page_context and source.page_context.commercial_tier:
        commercial_tier = source.page_context.commercial_tier

    try:
        profile = discover_referrers(
            url,
            meta.entity,
            seeds,
            resolved_engine,
            org=meta.org,
            aliases=meta.aliases,
            query_delay_s=query_delay_s,
            max_fetches_per_seed=max_fetches_per_seed,
            max_verified_referrers=max_verified_referrers,
            min_seeds_before_verified_stop=min_seeds_before_verified_stop,
            target_role=role,
            target_commercial_tier=commercial_tier,
            progress=prog,
            seed_workers=seed_workers,
            fetch_workers=fetch_workers,
            adaptive_stop=adaptive_stop,
            use_llm_connection=use_llm_connection,
        )

        primary, actions = derive_llm_actions(
            report.permissions,
            report.subscores,
        ) if report.permissions and report.subscores else (
            report.recommended_action,
            [report.recommended_action],
        )
        primary, actions = tighten_actions_with_referral(
            primary,
            actions,
            profile,
            content_role=role,
            engine_cited=False,
        )

        verdict = _build_verdict(primary, profile, role)
        hit_cap = profile.n_verified >= max_verified_referrers
        prog.close(
            final_status=f"done · verified={profile.n_verified}/{max_verified_referrers}",
            fill=hit_cap,
        )
    except Exception:
        prog.close(final_status="failed")
        raise

    return InvestigationResult(
        target_url=fetch.final_url or url,
        content_role=role,
        seed_confidence=seed_conf,
        seed_source=seed_source,
        seed_queries=seeds,
        single_page=report,
        llm_action=primary,
        llm_actions=actions,
        referral_profile=profile,
        verdict=verdict,
        metadata=meta,
    )


def investigation_to_dict(result: InvestigationResult) -> dict:
    sp = result.single_page
    payload = {
        "target_url": result.target_url,
        "content_role": result.content_role,
        "seed_confidence": result.seed_confidence,
        "seed_source": result.seed_source,
        "seed_queries": result.seed_queries,
        "metadata": asdict(result.metadata),
        "llm_action": result.llm_action,
        "llm_actions": result.llm_actions,
        "verdict": result.verdict,
        "referral_profile": {
            **asdict(result.referral_profile),
            "referrers_verified": [asdict(r) for r in result.referral_profile.referrers_verified],
            "semantic_alignment": (
                asdict(result.referral_profile.semantic_alignment)
                if result.referral_profile.semantic_alignment
                else None
            ),
        },
        "single_page": {
            "recommended_action": sp.recommended_action,
            "endorsement_risk": sp.endorsement_risk,
            "trust_score": sp.source.trust_score,
            "semantic_risk": sp.source.semantic_risk,
            "retrieval_manipulation_risk": (
                sp.subscores.retrieval_manipulation_risk if sp.subscores else None
            ),
            "concealment_risk": (
                sp.subscores.concealment_risk if sp.subscores else None
            ),
            "concealment_flags": (
                list(sp.source.concealment.flags)
                if sp.source.concealment
                else []
            ),
        },
        "shadow_soft_path": shadow_soft_path_metrics(result.referral_profile),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return payload


def format_investigation_report(result: InvestigationResult) -> str:
    sp = result.single_page
    rp = result.referral_profile
    retrieval_line = (
        f"  Retrieval manipulation: {sp.subscores.retrieval_manipulation_risk:.3f}"
        if sp.subscores
        else "  Retrieval manipulation: n/a"
    )
    concealment = sp.source.concealment
    concealment_line = "  Concealment: none"
    if concealment and concealment.flags:
        concealment_line = (
            f"  Concealment: ratio={concealment.hidden_ratio:.3f} "
            f"flags={concealment.flags} "
            f"excerpt={concealment.excerpt[:120]!r}"
        )
    elif sp.subscores and sp.subscores.concealment_risk > 0:
        concealment_line = f"  Concealment risk: {sp.subscores.concealment_risk:.3f}"
    lines = [
        "=" * 60,
        "ANTI-GEO INVESTIGATION (Mode B)",
        "=" * 60,
        f"Target: {result.target_url}",
        f"Content role: {result.content_role}",
        f"Seed confidence: {result.seed_confidence} ({result.seed_source})",
        f"Entity/topic: {result.metadata.entity}",
        "",
        "── Verdict ──",
        f"  {result.verdict}",
        f"  Primary LLM action: {result.llm_action}",
        f"  All actions: {', '.join(result.llm_actions)}",
        "",
        "── Single-page L1-L2-L3 ──",
        f"  Trust: {sp.source.trust_score:.3f}",
        f"  Semantic risk: {sp.source.semantic_risk:.3f}",
        retrieval_line,
        f"  Endorsement risk: {sp.endorsement_risk:.3f}",
        concealment_line,
        f"  Legacy action: {sp.recommended_action}",
        "",
        "── Referral profile (structural mix; may tighten LLM actions) ──",
        f"  Status: {rp.status}",
        f"  Discovery: {rp.discovery_status}",
        f"  Confidence: {rp.confidence}",
        f"  Citations sampled: {rp.citations_sampled}",
        f"  Seed queries run: {rp.seed_queries_run}",
        f"  Target cited in answers: {rp.target_cited_in_answers}",
        f"  N verified referrers: {rp.n_verified}",
        f"  Citation mix (all): {rp.citations_domain_mix or '{}'}",
        f"  Verified mix: {rp.mix or '{}'}",
        f"  GEO suspected: {rp.geo_suspected}",
        f"  GEO risk: {rp.geo_risk:.3f}  elevated={rp.geo_elevated}",
        f"  Referrer content scored: {rp.referrer_content_scored} "
        f"(high_risk={rp.referrer_content_high_risk}, "
        f"coordinated={rp.referrer_content_coordinated})",
    ]
    if rp.semantic_alignment:
        sa = rp.semantic_alignment
        lines.append(
            f"  Semantic alignment: {sa.label} "
            f"(referrer commercial share {sa.referrer_commercial_share:.0%})"
        )
    if rp.notes:
        lines.append(f"  Notes: {'; '.join(rp.notes)}")
    if rp.discovery_errors:
        lines.append(f"  Discovery errors: {len(rp.discovery_errors)}")
    if rp.referrers_verified:
        lines.extend(["", "── Verified referrers ──"])
        for ref in rp.referrers_verified[:15]:
            marker = f" ({ref.matched_marker})" if ref.matched_marker else ""
            content_bit = ""
            if ref.content_scored:
                risk = "high-risk" if ref.content_high_risk else "ok"
                content_bit = (
                    f" | L1 {risk} sem={ref.content_semantic_risk:.2f}"
                    f" flags={ref.content_flags or []}"
                )
            elif ref.content_manipulability > 0:
                content_bit = (
                    f" | triage={ref.content_manipulability:.2f}"
                    f" (thread={ref.content_thread_surface:.2f}"
                    f" edit={ref.content_editability:.2f})"
                )
            parasitic = is_parasitic_referrer(
                url=ref.url,
                role=ref.role,
                content_high_risk=ref.content_high_risk,
            )
            para_tag = " parasitic" if parasitic else ""
            lines.append(
                f"  [{ref.connection_confidence}] [{ref.role}]{para_tag} "
                f"{ref.connection}{marker}: {ref.url}{content_bit}"
            )
    shadow = shadow_soft_path_metrics(rp)
    gates = shadow["candidate_gates"]
    fired = [name for name, ok in gates.items() if ok]
    lines.extend(
        [
            "",
            "── Shadow soft-path (experiment; not live) ──",
            f"  Parasitic: {shadow['parasitic_count']}/{shadow['n_verified']} "
            f"(share={shadow['parasitic_share']})",
            f"  High-conf parasitic: {shadow['high_conf_parasitic_count']}",
            f"  Live: geo_suspected={shadow['geo_suspected_live']} "
            f"elevated={shadow.get('geo_elevated_live')} "
            f"geo_risk={shadow.get('geo_risk')} "
            f"sparse_suspicious={shadow['sparse_suspicious_live']} "
            f"soft_band={shadow['soft_band_live']}",
            f"  Candidate gates fired: {', '.join(fired) if fired else '(none)'}",
        ]
    )
    lines.extend(["", "── Seed queries (for optional audit) ──"])
    for i, q in enumerate(result.seed_queries, 1):
        lines.append(f"  {i}. {q}")
    return "\n".join(lines)
