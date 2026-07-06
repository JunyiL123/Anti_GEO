from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from anti_geo.models import FetchResult
from anti_geo.page_context import extract_page_context

USER_AGENT = "AntiGEO-Analyzer/0.1 (research; +https://github.com/JunyiL123/Anti_GEO)"
MAX_LINKS_TO_CHECK = 8
MAX_TEXT_CHARS = 50_000


def _same_host(base: str, link: str) -> bool:
    return urlparse(base).netloc == urlparse(link).netloc


def fetch_page(url: str, timeout: float = 12.0) -> FetchResult:
    """Fetch URL and extract visible text + light structural signals."""
    redirects = 0
    start = time.perf_counter()
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.get(url)
            redirects = len(response.history)
            final_url = str(response.url)
            html = response.text
            status = response.status_code
            ok = 200 <= status < 400
    except Exception as exc:  # noqa: BLE001 — surface fetch errors in report
        elapsed = (time.perf_counter() - start) * 1000
        return FetchResult(
            url=url,
            final_url=url,
            status_code=None,
            ok=False,
            error=str(exc),
            title="",
            text="",
            link_count=0,
            broken_link_ratio=1.0,
            redirect_count=0,
            response_time_ms=elapsed,
            has_privacy_page=False,
            has_contact_page=False,
            page_context=None,
        )

    elapsed = (time.perf_counter() - start) * 1000
    soup = BeautifulSoup(html, "html.parser")
    page_context = extract_page_context(soup, re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:MAX_TEXT_CHARS])

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:MAX_TEXT_CHARS]

    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") or href.startswith("mailto:"):
            continue
        absolute = urljoin(final_url, href)
        if _same_host(final_url, absolute):
            links.append(absolute.split("#")[0])

    unique_links = list(dict.fromkeys(links))[:MAX_LINKS_TO_CHECK]
    broken = 0
    checked = 0
    with httpx.Client(
        follow_redirects=True,
        timeout=5.0,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for link in unique_links:
            checked += 1
            try:
                r = client.head(link)
                if r.status_code >= 400:
                    broken += 1
            except Exception:
                broken += 1

    broken_ratio = (broken / checked) if checked else 0.0
    lower_html = html.lower()
    has_privacy = "privacy" in lower_html
    has_contact = "contact" in lower_html

    return FetchResult(
        url=url,
        final_url=final_url,
        status_code=status,
        ok=ok,
        error=None,
        title=title,
        text=text,
        link_count=len(links),
        broken_link_ratio=broken_ratio,
        redirect_count=redirects,
        response_time_ms=elapsed,
        has_privacy_page=has_privacy,
        has_contact_page=has_contact,
        page_context=page_context,
    )
