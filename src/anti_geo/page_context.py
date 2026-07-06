from __future__ import annotations

import json
import re

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


def extract_page_context(soup: BeautifulSoup, text: str) -> PageContextSignals:
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

    return PageContextSignals(
        cta_density=cta_density,
        commercial_context_score=commercial_score,
        structure_density=structure_density,
        list_item_count=list_items,
        table_count=tables,
        has_faq_schema=faq_schema,
        flags=flags,
    )
