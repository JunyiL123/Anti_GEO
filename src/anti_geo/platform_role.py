from __future__ import annotations

import re
from urllib.parse import urlparse

from anti_geo.models import FetchResult, PageContextSignals, SourceScore

# Reddit-like comment threads — also drives comment segmentation.
THREAD_PATH_RE = re.compile(
    r"/(comments?|forum|thread|questions|discussion)\b",
    re.I,
)
# LinkedIn / X-style open posting (UGC label + Mode B skip).
# Require end-of-segment so /blog/post-slug does not match.
SOCIAL_POST_PATH_RE = re.compile(r"/(posts?|pulse|feed|status)(?:/|$)", re.I)
# Medium-like publish-on-host paths — parasitic mix, not UGC.
PARASITIC_PUBLISH_PATH_RE = re.compile(r"/p/[a-z0-9]", re.I)

# Back-compat aliases.
UGC_PATH_RE = THREAD_PATH_RE
POST_SHAPED_PATH_RE = re.compile(
    r"/(posts?|pulse|newsletter)\b|/p/[a-z0-9]",
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


def is_thread_path(url: str) -> bool:
    return bool(THREAD_PATH_RE.search(urlparse(url).path or ""))


def is_social_post_path(url: str) -> bool:
    return bool(SOCIAL_POST_PATH_RE.search(urlparse(url).path or ""))


def is_open_posting_path(url: str) -> bool:
    """Thread or social open-posting URL — UGC surfaces."""
    path = urlparse(url).path or ""
    return bool(THREAD_PATH_RE.search(path) or SOCIAL_POST_PATH_RE.search(path))


def is_parasitic_publish_path(url: str) -> bool:
    """Medium-like /p/ publish-host shape — parasitic mix, not UGC."""
    return bool(PARASITIC_PUBLISH_PATH_RE.search(urlparse(url).path or ""))


def is_ugc_role(role: str) -> bool:
    """True for open-posting UGC (forums + LinkedIn/X) — Mode A skips Mode B."""
    return role == "ugc_thread"


def is_parasitic_referrer(
    *,
    url: str,
    role: str,
    content_high_risk: bool = False,
) -> bool:
    """Potential parasitic GEO surface for mix share (unweighted boolean).

    Always: open-posting UGC paths, Medium-like /p/, review_profile.
    Conditional: factual_blog only when L1 already marked high-risk.
    """
    if is_open_posting_path(url) or is_parasitic_publish_path(url):
        return True
    if role == "review_profile" or role == "ugc_thread":
        return True
    if role == "factual_blog" and content_high_risk:
        return True
    return False


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

    # Open posting (Reddit / LinkedIn / X) → UGC.
    if THREAD_PATH_RE.search(path) or SOCIAL_POST_PATH_RE.search(path):
        return "ugc_thread"

    if EDITORIAL_PICKS_RE.search(path):
        return "editorial"

    if REVIEW_PROFILE_RE.search(path):
        return "review_profile"

    # Medium-like /p/ and leftover newsletter shapes — soft publish, not UGC.
    if PARASITIC_PUBLISH_PATH_RE.search(path) or re.search(
        r"/newsletter\b", path, re.I
    ):
        return "expert_listicle"

    page_ctx: PageContextSignals | None = None
    if source and source.page_context:
        page_ctx = source.page_context
    elif fetch and fetch.page_context:
        page_ctx = fetch.page_context

    if PRODUCT_PATH_RE.search(path):
        return "commercial_product"

    # Main-content commercial signals (chrome-only monetization does not raise tier).
    if page_ctx and page_ctx.commercial_tier in ("medium", "high"):
        # Hard sell / PDP-like body → product; affiliate editorial without CTAs → listicle.
        if "commercial_cta" in page_ctx.flags:
            return "commercial_product"
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
