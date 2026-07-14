from __future__ import annotations

import re
from urllib.parse import urlparse

from anti_geo.models import FetchResult, PageContextSignals, SourceScore

UGC_PATH_RE = re.compile(r"/(comments|comment|forum|thread|questions|discussion)\b", re.I)
# Post / newsletter shaped pages — path only, no host brand lists.
POST_SHAPED_PATH_RE = re.compile(
    r"/(posts?|pulse|newsletter)/\b|/(posts?|pulse|newsletter)\b|/p/[a-z0-9]",
    re.I,
)
REVIEW_PROFILE_RE = re.compile(
    r"/(product-reviews/|products/[^/]+/reviews(?:/|$)|/reviews(?:/|$))",
    re.I,
)
EDITORIAL_PICKS_RE = re.compile(r"/(picks|best-|roundup|guide)/", re.I)
PRODUCT_PATH_RE = re.compile(r"/(dp/|product/|products/|shop/|buy/|item/)\b", re.I)


def registrable_domain(hostname: str) -> str:
    host = hostname.lower().removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def is_ugc_role(role: str) -> bool:
    """True for forums/Reddit-style UGC — Mode A skips Mode B on these cites."""
    return role == "ugc_thread"


def classify_content_role(
    url: str,
    *,
    fetch: FetchResult | None = None,
    source: SourceScore | None = None,
) -> str:
    """Infer page role from URL structure and page signals — no domain brand lists."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()

    if host.endswith(".gov") or host.endswith(".edu"):
        return "institutional"

    if UGC_PATH_RE.search(path):
        return "ugc_thread"

    if EDITORIAL_PICKS_RE.search(path):
        return "editorial"

    if REVIEW_PROFILE_RE.search(path):
        return "review_profile"

    if POST_SHAPED_PATH_RE.search(path):
        return "expert_listicle"

    page_ctx: PageContextSignals | None = None
    if source and source.page_context:
        page_ctx = source.page_context
    elif fetch and fetch.page_context:
        page_ctx = fetch.page_context

    if PRODUCT_PATH_RE.search(path) or (
        page_ctx
        and page_ctx.commercial_tier in ("medium", "high")
        and any(f in page_ctx.flags for f in ("commercial_cta", "affiliate_link_params"))
    ):
        return "commercial_product"

    if page_ctx and page_ctx.commercial_tier == "high":
        return "commercial_product"

    if page_ctx and page_ctx.commercial_tier in ("medium", "high"):
        return "expert_listicle"

    if re.search(r"/(wiki|docs|reference|encyclopedia)\b", path):
        return "factual_blog"

    if fetch and fetch.ok and fetch.text:
        text = fetch.text[:2000].lower()
        if re.search(r"\b(buy now|add to cart|free trial|subscribe)\b", text):
            return "commercial_product"
        if re.search(r"\b(affiliate|sponsored|paid partnership)\b", text):
            return "expert_listicle"

    return "factual_blog"
