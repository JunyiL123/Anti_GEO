from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from anti_geo.models import PageContextSignals

CTA_PATTERNS = [
    r"\bbuy now\b",
    r"\bfree trial\b",
    r"\bget started\b",
    r"\bpricing\b",
    r"\bsubscribe\b",
    r"\badd to cart\b",
    r"\bshop now\b",
]
AFFILIATE_PATTERNS = [
    r"\baffiliate\b",
    r"\bsponsored\b",
    r"\bpaid partnership\b",
]
PRESS_RELEASE_PATTERNS = [
    r"\bfor immediate release\b",
    r"\bpress release\b",
]
# True affiliate/partner tracking — not generic analytics UTMs or bare ref=.
AFFILIATE_LINK_PARAM_RE = re.compile(
    r"(?:"
    r"\baffiliate\b|"
    r"[?&](?:tag|aff(?:iliate)?(?:[_-]?id)?|partner_id|clickid|clid)=|"
    r"/affiliate(?:s)?/"
    r")",
    re.I,
)
_PATH_COMMERCIAL_RE = re.compile(r"/(pricing|buy|shop|cart|checkout|trial)\b", re.I)

HIGH_TIER_FLAGS = frozenset({"affiliate_disclosure", "link_sponsored", "structured_funding"})
MEDIUM_TIER_FLAGS = frozenset({"affiliate_link_params", "press_release", "commercial_cta"})

# Prefer editorial body over site chrome when scoring commercial intent.
_MAIN_CONTENT_SELECTORS = (
    "article",
    "main",
    "[role='main']",
    "[itemprop='articleBody']",
    ".article-body",
    ".article-content",
    ".post-content",
    ".entry-content",
    ".story-body",
    ".content-body",
    "#article-body",
    "#content",
)
_CHROME_TAGS = frozenset({"nav", "footer", "header", "aside"})
_CHROME_ROLES = frozenset(
    {"navigation", "banner", "contentinfo", "complementary", "search"}
)
_CHROME_CLASS_RE = re.compile(
    r"(?:\b|^)(?:"
    r"nav|navbar|header|footer|sidebar|aside|menu|toolbar|"
    r"promo|banner|advert|ads?(?:-|_)|cookie|modal|drawer|"
    r"newsletter-signup|site-chrome"
    r")(?:\b|$)",
    re.I,
)


def _link_has_sponsored_rel(tag: Tag) -> bool:
    rel = tag.get("rel") or []
    if isinstance(rel, str):
        rel = rel.split()
    return any("sponsored" in r.lower() for r in rel)


def _class_id_blob(tag: Tag) -> str:
    classes = " ".join(tag.get("class") or [])
    return f"{tag.name or ''} {classes} {tag.get('id') or ''} {tag.get('role') or ''}"


def _is_chrome_region(tag: Tag) -> bool:
    name = (tag.name or "").lower()
    if name in _CHROME_TAGS:
        return True
    role = (tag.get("role") or "").lower()
    if role in _CHROME_ROLES:
        return True
    return bool(_CHROME_CLASS_RE.search(_class_id_blob(tag)))


def tag_in_chrome(tag: Tag) -> bool:
    """True if tag or an ancestor is site chrome (nav/footer/cookie/menu…)."""
    if not isinstance(tag, Tag):
        return False
    if _is_chrome_region(tag):
        return True
    for parent in tag.parents:
        if not isinstance(parent, Tag):
            continue
        if parent.name in ("html", "body"):
            break
        if _is_chrome_region(parent):
            return True
    return False


def _anchor_in_chrome(tag: Tag) -> bool:
    return tag_in_chrome(tag)


def _main_content_root(soup: BeautifulSoup) -> Tag:
    """Best-effort article/main root; fall back to body."""
    for selector in _MAIN_CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if isinstance(node, Tag) and node.get_text(strip=True):
            return node
    body = soup.body
    if isinstance(body, Tag):
        return body
    return soup


def _iter_content_anchors(root: Tag):
    for tag in root.find_all("a", href=True):
        if _anchor_in_chrome(tag):
            continue
        yield tag


def _content_scope_text(root: Tag) -> str:
    """Visible text under root, skipping chrome subtrees."""
    parts: list[str] = []

    def _walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, str):
                text = child.strip()
                if text:
                    parts.append(text)
                continue
            if not isinstance(child, Tag):
                continue
            name = (child.name or "").lower()
            if name in {"script", "style", "noscript"}:
                continue
            if _is_chrome_region(child):
                continue
            _walk(child)

    _walk(root)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _anchor_under(tag: Tag, root: Tag) -> bool:
    cur: object = tag
    while isinstance(cur, Tag):
        if cur is root:
            return True
        cur = cur.parent
    return False


def _detect_affiliate_links(soup: BeautifulSoup) -> tuple[bool, bool, bool]:
    """Return (main_affiliate, main_sponsored, chrome_monetized)."""
    root = _main_content_root(soup)
    main_affiliate = False
    main_sponsored = False
    for tag in _iter_content_anchors(root):
        href = tag["href"]
        if AFFILIATE_LINK_PARAM_RE.search(href):
            main_affiliate = True
        if _link_has_sponsored_rel(tag):
            main_sponsored = True

    chrome_monetized = False
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        is_monetized = bool(
            AFFILIATE_LINK_PARAM_RE.search(href) or _link_has_sponsored_rel(tag)
        )
        if not is_monetized:
            continue
        if _anchor_in_chrome(tag) or not _anchor_under(tag, root):
            chrome_monetized = True
            break

    return main_affiliate, main_sponsored, chrome_monetized


def _detect_structured_funding(soup: BeautifulSoup) -> bool:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            schema_type = str(item.get("@type", ""))
            if schema_type in ("Product", "Review", "Article"):
                if item.get("sponsor") or item.get("funding"):
                    return True
            if "sponsor" in json.dumps(item).lower() or "funding" in json.dumps(item).lower():
                return True
    return False


def classify_page_commercial_tier(
    flags: list[str],
    commercial_context_score: float,
    url_path: str = "",
) -> tuple[str, list[str]]:
    """Assign page-level commercial tier from HTML/text flags (chunk may upgrade later)."""
    triggers: list[str] = []
    for flag in flags:
        if flag in HIGH_TIER_FLAGS or flag in MEDIUM_TIER_FLAGS:
            triggers.append(flag)

    if any(f in flags for f in HIGH_TIER_FLAGS):
        return "high", triggers

    if any(f in flags for f in MEDIUM_TIER_FLAGS):
        return "medium", triggers

    if commercial_context_score > 0.5 or _PATH_COMMERCIAL_RE.search(url_path):
        if commercial_context_score > 0.5:
            triggers.append("commercial_context_score")
        if _PATH_COMMERCIAL_RE.search(url_path):
            triggers.append("commercial_url_path")
        return "low", triggers

    return "none", triggers


def extract_page_context(soup: BeautifulSoup, text: str, url: str = "") -> PageContextSignals:
    """Infer commercial/editorial page role from HTML — no domain blocklists.

    Commercial link/CTA/disclosure signals are scored on main content when
    possible so nav/footer partner chrome does not dominate.
    """
    root = _main_content_root(soup)
    scope_text = _content_scope_text(root) or text
    lower = scope_text.lower()
    flags: list[str] = []

    cta_hits = sum(len(re.findall(p, lower)) for p in CTA_PATTERNS)
    words = max(len(scope_text.split()), 1)
    cta_density = min(1.0, cta_hits / words * 20)

    if cta_density > 0.15:
        flags.append("commercial_cta")
    if any(re.search(p, lower) for p in AFFILIATE_PATTERNS):
        flags.append("affiliate_disclosure")
    if any(re.search(p, lower) for p in PRESS_RELEASE_PATTERNS):
        flags.append("press_release")

    has_affiliate_links, has_sponsored_rel, chrome_monetized = _detect_affiliate_links(
        soup
    )
    if has_affiliate_links:
        flags.append("affiliate_link_params")
    if has_sponsored_rel:
        flags.append("link_sponsored")
    if chrome_monetized and not (has_affiliate_links or has_sponsored_rel):
        # Soft signal: site sells ads/partners, but article body does not.
        flags.append("site_chrome_monetization")
    if _detect_structured_funding(soup):
        flags.append("structured_funding")

    list_items = len(soup.find_all("li"))
    tables = len(soup.find_all("table"))
    list_ratio = min(1.0, list_items / max(words / 10, 1))

    faq_schema = False
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            schema_type = item.get("@type", "")
            if schema_type == "FAQPage" or "FAQPage" in str(schema_type):
                faq_schema = True
                break

    structure_density = min(
        1.0,
        0.4 * list_ratio + 0.3 * min(1.0, tables / 3) + (0.3 if faq_schema else 0.0),
    )
    if faq_schema:
        flags.append("faq_schema")
    if list_ratio > 0.5:
        flags.append("list_heavy")
    if tables >= 2:
        flags.append("table_heavy")

    commercial_score = min(1.0, cta_density * 0.7 + (0.3 if "commercial_cta" in flags else 0.0))
    url_path = urlparse(url).path if url else ""
    # Chrome-only monetization must not elevate commercial_tier.
    tier_flags = [f for f in flags if f != "site_chrome_monetization"]
    tier, triggers = classify_page_commercial_tier(tier_flags, commercial_score, url_path)

    return PageContextSignals(
        cta_density=cta_density,
        commercial_context_score=commercial_score,
        structure_density=structure_density,
        list_item_count=list_items,
        table_count=tables,
        has_faq_schema=faq_schema,
        flags=flags,
        commercial_tier=tier,
        commercial_triggers=triggers,
        has_affiliate_links=has_affiliate_links or has_sponsored_rel,
    )
