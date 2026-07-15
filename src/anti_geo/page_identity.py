"""Extract brand / org / product identity from page HTML (structured > title)."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from anti_geo.models import PageIdentity
from anti_geo.platform_role import registrable_domain

_LISTICLE_PREFIX_RE = re.compile(
    r"^(the\s+)?(best|top|cheap(est)?|budget)\s+",
    re.I,
)
_LISTICLE_NOISE_RE = re.compile(
    r"\b("
    r"we'?ve\s+tested|buying\s+guide|picks?|reviewed?|reviews?|"
    r"comparison|vs\.?|for\s+20\d{2}|20\d{2}"
    r")\b",
    re.I,
)
_SCHEMA_BRAND_TYPES = frozenset({"Brand", "Organization", "Corporation", "LocalBusiness"})
_SCHEMA_PRODUCT_TYPES = frozenset({"Product", "ProductModel", "SoftwareApplication"})
_GENERIC_ORG_TOKENS = frozenset(
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
        "official",
        "store",
        "shop",
        "product",
        "products",
        "review",
        "reviews",
        "guide",
        "blog",
    }
)
_PATH_SKIP = frozenset(
    {
        "",
        "www",
        "p",
        "product",
        "products",
        "shop",
        "store",
        "buy",
        "pricing",
        "categories",
        "category",
        "reviews",
        "review",
        "best",
        "picks",
        "en",
        "us",
        "uk",
        "index",
        "html",
        "model",
        "gaming-keyboard",
        "audio",
        "headphones",
        "headband",
    }
)
# CMS date folders like /2026/03/… must not become "product".
_PATH_DATE_RE = re.compile(
    r"^(?:"
    r"20\d{2}|"  # year
    r"(?:0?[1-9]|1[0-2])|"  # month
    r"(?:0?[1-9]|[12]\d|3[01])"  # day
    r")$"
)


def strip_listicle_boilerplate(title: str) -> str:
    """Drop Best/Top/… buying-guide skins so title leftovers can be entities."""
    text = " ".join(title.strip().split())
    if not text:
        return ""
    text = _LISTICLE_PREFIX_RE.sub("", text)
    text = _LISTICLE_NOISE_RE.sub(" ", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -–—|,:")
    return text[:120]


def _norm_name(value: str, *, min_len: int = 2, max_len: int = 80) -> str:
    text = " ".join(str(value).strip().split())
    if not text or len(text) < min_len or len(text) > max_len:
        return ""
    if text.lower() in _GENERIC_ORG_TOKENS:
        return ""
    return text


def _as_list(node: object) -> list:
    if node is None:
        return []
    if isinstance(node, list):
        return node
    return [node]


def _schema_types(item: dict) -> set[str]:
    raw = item.get("@type", "")
    if isinstance(raw, list):
        return {str(x) for x in raw}
    if raw:
        return {str(raw)}
    return set()


def _name_from(node: object) -> str:
    if isinstance(node, str):
        return _norm_name(node)
    if isinstance(node, dict):
        for key in ("name", "legalName", "alternateName"):
            if key in node:
                got = _name_from(node[key])
                if got:
                    return got
    return ""


def _walk_jsonld(node: object) -> list[dict]:
    out: list[dict] = []
    if isinstance(node, dict):
        if "@graph" in node:
            for child in _as_list(node["@graph"]):
                out.extend(_walk_jsonld(child))
        else:
            out.append(node)
            for key in ("brand", "manufacturer", "publisher", "provider", "organizer"):
                if key in node:
                    out.extend(_walk_jsonld(node[key]))
    elif isinstance(node, list):
        for child in node:
            out.extend(_walk_jsonld(child))
    return out


def _parse_jsonld_scripts(soup: BeautifulSoup) -> tuple[str, str, str]:
    """Return (organization, brand, product) from JSON-LD when present."""
    organization = ""
    brand = ""
    product = ""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _walk_jsonld(data):
            if not isinstance(item, dict):
                continue
            types = _schema_types(item)
            name = _name_from(item.get("name") or item.get("alternateName"))
            if types & _SCHEMA_PRODUCT_TYPES and name and not product:
                product = name
            if types & _SCHEMA_BRAND_TYPES and name:
                if "Organization" in types or "Corporation" in types or "LocalBusiness" in types:
                    if not organization:
                        organization = name
                if not brand:
                    brand = name
            nested_brand = _name_from(item.get("brand"))
            if nested_brand and not brand:
                brand = nested_brand
            publisher = _name_from(item.get("publisher") or item.get("provider"))
            if publisher and not organization:
                organization = publisher
    return organization, brand, product


def _meta_content(soup: BeautifulSoup, *, prop: str | None = None, name: str | None = None) -> str:
    attrs: dict[str, str] = {}
    if prop:
        attrs["property"] = prop
    if name:
        attrs["name"] = name
    tag = soup.find("meta", attrs=attrs)
    if not tag:
        return ""
    return _norm_name(tag.get("content") or "")


def _path_product_candidate(url: str) -> str:
    """Last distinctive path slug (e.g. aula-f75, whch720n-b)."""
    path = urlparse(url).path.strip("/")
    if not path:
        return ""
    for part in reversed(path.split("/")):
        slug = part.strip().lower()
        if slug in _PATH_SKIP or len(slug) < 4:
            continue
        # Blog CMS dates (/2026/03/…) are not product SKUs.
        if _PATH_DATE_RE.match(slug) or slug.isdigit():
            continue
        if _LISTICLE_PREFIX_RE.match(slug.replace("-", " ")):
            continue
        # Prefer product-like: has digit or multi-token hyphen slug
        if re.search(r"\d", slug) or ("-" in slug and len(slug) >= 6):
            return _norm_name(slug.replace("-", " "), min_len=4, max_len=60)
    return ""


def extract_page_identity(
    soup: BeautifulSoup,
    *,
    url: str = "",
    title: str = "",
) -> PageIdentity:
    """Prefer og/JSON-LD identity; fall back to cleaned title + domain."""
    site_name = (
        _meta_content(soup, prop="og:site_name")
        or _meta_content(soup, name="application-name")
        or _meta_content(soup, name="apple-mobile-web-app-title")
    )
    organization, brand, product = _parse_jsonld_scripts(soup)
    if not brand:
        brand = _meta_content(soup, prop="product:brand") or site_name
    if not product:
        product = _path_product_candidate(url)

    cleaned_title = strip_listicle_boilerplate(
        re.split(r"\s*[|\-–—]\s*", title)[0] if title else ""
    )
    domain = registrable_domain(urlparse(url).netloc) if url else ""
    publisher = domain.split(".")[0] if domain else ""

    if not organization:
        organization = site_name or (publisher if len(publisher) >= 4 else "")
    if not brand:
        brand = organization or site_name
    if not product and cleaned_title and cleaned_title.lower() not in {
        (brand or "").lower(),
        (organization or "").lower(),
        (site_name or "").lower(),
    }:
        # Title leftover only if it doesn't just repeat the publisher.
        if len(cleaned_title) >= 4:
            product = product or cleaned_title

    aliases: list[str] = []
    for cand in (product, brand, organization, site_name, publisher):
        n = _norm_name(cand, min_len=4)
        if not n:
            continue
        # Never promote calendar tokens / pure years into verify aliases.
        if n.isdigit() or _PATH_DATE_RE.match(n.lower()):
            continue
        if n.lower() not in {a.lower() for a in aliases}:
            aliases.append(n)
        # Compact form for multi-word brands (Theo Grace → theograce)
        compact = re.sub(r"[^a-z0-9]", "", n.lower())
        if (
            len(compact) >= 5
            and not compact.isdigit()
            and compact not in {a.lower() for a in aliases}
        ):
            aliases.append(compact)

    return PageIdentity(
        site_name=site_name,
        organization=_norm_name(organization) or organization,
        brand=_norm_name(brand) or brand,
        product=_norm_name(product, min_len=3) or product,
        aliases=aliases,
    )


def identity_from_html(html: str, *, url: str = "", title: str = "") -> PageIdentity:
    if not html.strip():
        return PageIdentity()
    soup = BeautifulSoup(html, "html.parser")
    resolved_title = title
    if not resolved_title and soup.title:
        resolved_title = soup.title.get_text(strip=True)
    return extract_page_identity(soup, url=url, title=resolved_title)
