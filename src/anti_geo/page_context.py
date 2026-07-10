from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

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
AFFILIATE_LINK_PARAM_RE = re.compile(
    r"(affiliate|ref=|utm_source|utm_campaign|tag=|partner_id|clickid)",
    re.I,
)
_PATH_COMMERCIAL_RE = re.compile(r"/(pricing|buy|shop|cart|checkout|trial)\b", re.I)

HIGH_TIER_FLAGS = frozenset({"affiliate_disclosure", "link_sponsored", "structured_funding"})
MEDIUM_TIER_FLAGS = frozenset({"affiliate_link_params", "press_release", "commercial_cta"})


def _link_has_sponsored_rel(tag) -> bool:
    rel = tag.get("rel") or []
    if isinstance(rel, str):
        rel = rel.split()
    return any("sponsored" in r.lower() for r in rel)


def _detect_affiliate_links(soup: BeautifulSoup) -> tuple[bool, bool]:
    """Return (has_affiliate_links, has_sponsored_rel)."""
    has_affiliate = False
    has_sponsored = False
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if AFFILIATE_LINK_PARAM_RE.search(href):
            has_affiliate = True
        if _link_has_sponsored_rel(tag):
            has_sponsored = True
    return has_affiliate, has_sponsored


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
    """Infer commercial/editorial page role from HTML — no domain blocklists."""
    lower = text.lower()
    flags: list[str] = []

    cta_hits = sum(len(re.findall(p, lower)) for p in CTA_PATTERNS)
    words = max(len(text.split()), 1)
    cta_density = min(1.0, cta_hits / words * 20)

    if cta_density > 0.15:
        flags.append("commercial_cta")
    if any(re.search(p, lower) for p in AFFILIATE_PATTERNS):
        flags.append("affiliate_disclosure")
    if any(re.search(p, lower) for p in PRESS_RELEASE_PATTERNS):
        flags.append("press_release")

    has_affiliate_links, has_sponsored_rel = _detect_affiliate_links(soup)
    if has_affiliate_links:
        flags.append("affiliate_link_params")
    if has_sponsored_rel:
        flags.append("link_sponsored")
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
    tier, triggers = classify_page_commercial_tier(flags, commercial_score, url_path)

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
