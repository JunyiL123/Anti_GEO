from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from anti_geo.models import FetchResult
from anti_geo.page_context import extract_page_context
from anti_geo.page_identity import extract_page_identity
from anti_geo.segments import extract_page_segments

# Browser-like UA: some hosts (e.g. Wikipedia) reject custom bot identities.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_LINKS_TO_CHECK = 8
MAX_TEXT_CHARS = 50_000
MIN_USEFUL_WORDS = 30

_BOT_WALL_SNIPPETS = (
    "access denied",
    "just a moment",
    "please enable js",
    "enable javascript",
    "cf-browser-verification",
    "checking your browser",
    "verify you are human",
    "attention required",
    "errors.edgesuite.net",
    "request blocked",
    "bot detection",
)


@dataclass
class _HtmlFetch:
    html: str
    final_url: str
    status_code: int | None
    redirect_count: int
    error: str | None


def _fetch_mode() -> str:
    """auto | httpx | browser — set ANTI_GEO_FETCH env var."""
    return os.environ.get("ANTI_GEO_FETCH", "auto").strip().lower()


def looks_like_bot_wall(status_code: int | None, text: str) -> bool:
    """True when the response looks like a bot block or JS gate, not real content."""
    if status_code in (401, 403, 406, 429, 503):
        return True
    lower = text.lower()
    if any(snippet in lower for snippet in _BOT_WALL_SNIPPETS):
        return True
    return len(text.split()) < MIN_USEFUL_WORDS


def _same_host(base: str, link: str) -> bool:
    return urlparse(base).netloc == urlparse(link).netloc


def _extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:MAX_TEXT_CHARS]


def _fetch_html_httpx(url: str, timeout: float) -> _HtmlFetch:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers=DEFAULT_HEADERS,
        ) as client:
            response = client.get(url)
            return _HtmlFetch(
                html=response.text,
                final_url=str(response.url),
                status_code=response.status_code,
                redirect_count=len(response.history),
                error=None,
            )
    except Exception as exc:  # noqa: BLE001
        return _HtmlFetch(
            html="",
            final_url=url,
            status_code=None,
            redirect_count=0,
            error=str(exc),
        )


_PLAYWRIGHT_LOCK = threading.Lock()


def _fetch_html_playwright(url: str, timeout: float) -> _HtmlFetch | None:
    """Headless Chromium fetch. Returns None if playwright is not installed.

    Sync Playwright is not thread-safe; serialize browser launches.
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    timeout_ms = int(timeout * 1000)
    stealth_script = (
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    try:
        with _PLAYWRIGHT_LOCK, sync_playwright() as playwright:
            browser = None
            for launch_kwargs in (
                {
                    "headless": True,
                    "args": ["--disable-blink-features=AutomationControlled"],
                },
                {
                    "headless": True,
                    "channel": "chrome",
                    "args": ["--disable-blink-features=AutomationControlled"],
                },
                {"headless": True, "channel": "msedge"},
            ):
                try:
                    browser = playwright.chromium.launch(**launch_kwargs)
                    break
                except Exception:
                    continue
            if browser is None:
                return _HtmlFetch(
                    html="",
                    final_url=url,
                    status_code=None,
                    redirect_count=0,
                    error="playwright_browser_unavailable",
                )
            context = browser.new_context(
                user_agent=USER_AGENT,
                locale="en-US",
                viewport={"width": 1366, "height": 768},
            )
            context.add_init_script(stealth_script)
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_function(
                    "() => document.body && document.body.innerText.trim().length > 120",
                    timeout=min(10_000, timeout_ms),
                )
            except PlaywrightTimeout:
                pass
            html = page.content()
            final_url = page.url
            status = response.status if response else None
            browser.close()
            return _HtmlFetch(
                html=html,
                final_url=final_url,
                status_code=status,
                redirect_count=0,
                error=None,
            )
    except Exception as exc:  # noqa: BLE001
        return _HtmlFetch(
            html="",
            final_url=url,
            status_code=None,
            redirect_count=0,
            error=str(exc),
        )


def _check_broken_links(final_url: str, html: str) -> float:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
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
        headers=DEFAULT_HEADERS,
    ) as client:
        for link in unique_links:
            checked += 1
            try:
                response = client.head(link)
                if response.status_code >= 400:
                    broken += 1
            except Exception:
                broken += 1
    return (broken / checked) if checked else 0.0


def _build_fetch_result(
    url: str,
    raw: _HtmlFetch,
    *,
    fetch_engine: str,
    skip_link_check: bool,
    start: float,
) -> FetchResult:
    elapsed = (time.perf_counter() - start) * 1000
    if raw.error:
        return FetchResult(
            url=url,
            final_url=raw.final_url or url,
            status_code=raw.status_code,
            ok=False,
            error=raw.error,
            title="",
            text="",
            link_count=0,
            broken_link_ratio=1.0,
            redirect_count=raw.redirect_count,
            response_time_ms=elapsed,
            has_privacy_page=False,
            has_contact_page=False,
            page_context=None,
            fetch_engine=fetch_engine,
        )

    soup = BeautifulSoup(raw.html, "html.parser")
    visible_text = _extract_visible_text(raw.html)
    page_context = extract_page_context(soup, visible_text, url=raw.final_url or url)
    segments = extract_page_segments(raw.html, raw.final_url or url)

    title = soup.title.get_text(strip=True) if soup.title else ""
    text = visible_text
    identity = extract_page_identity(soup, url=raw.final_url or url, title=title)

    link_count = len(soup.find_all("a", href=True))
    broken_ratio = 0.0 if skip_link_check else _check_broken_links(raw.final_url, raw.html)

    lower_html = raw.html.lower()
    status = raw.status_code or 0
    ok = 200 <= status < 400 and not looks_like_bot_wall(status, text)

    return FetchResult(
        url=url,
        final_url=raw.final_url,
        status_code=raw.status_code,
        ok=ok,
        error=None if ok else str(raw.status_code),
        title=title,
        text=text,
        link_count=link_count,
        broken_link_ratio=broken_ratio,
        redirect_count=raw.redirect_count,
        response_time_ms=elapsed,
        has_privacy_page="privacy" in lower_html,
        has_contact_page="contact" in lower_html,
        page_context=page_context,
        fetch_engine=fetch_engine,
        segments=segments,
        identity=identity,
    )


def _try_browser_fetch(url: str, timeout: float, start: float) -> FetchResult | None:
    """Returns None only when playwright is not installed."""
    raw = _fetch_html_playwright(url, timeout)
    if raw is None:
        return None
    return _build_fetch_result(
        url,
        raw,
        fetch_engine="playwright",
        skip_link_check=True,
        start=start,
    )


def fetch_page(url: str, timeout: float = 12.0, *, force_browser: bool = False) -> FetchResult:
    """Fetch URL and extract visible text + light structural signals.

    Uses httpx by default. On bot walls (403, Cloudflare, Akamai) retries with
    headless Chromium when playwright is installed (ANTI_GEO_FETCH=auto, default).
    """
    start = time.perf_counter()
    mode = _fetch_mode()

    if force_browser or mode == "browser":
        browser_result = _try_browser_fetch(url, timeout, start)
        if browser_result is not None:
            return browser_result
        elapsed = (time.perf_counter() - start) * 1000
        return FetchResult(
            url=url,
            final_url=url,
            status_code=None,
            ok=False,
            error="playwright_not_installed",
            title="",
            text="",
            link_count=0,
            broken_link_ratio=1.0,
            redirect_count=0,
            response_time_ms=elapsed,
            has_privacy_page=False,
            has_contact_page=False,
            page_context=None,
            fetch_engine="playwright",
        )
    raw = _fetch_html_httpx(url, timeout)
    if raw.error:
        if mode != "httpx":
            browser_result = _try_browser_fetch(url, timeout, start)
            if browser_result is not None:
                return browser_result
        return _build_fetch_result(
            url,
            raw,
            fetch_engine="httpx",
            skip_link_check=False,
            start=start,
        )

    preview = _extract_visible_text(raw.html)
    if mode != "httpx" and looks_like_bot_wall(raw.status_code, preview):
        browser_result = _try_browser_fetch(url, timeout, start)
        if browser_result is not None:
            return browser_result

    return _build_fetch_result(
        url,
        raw,
        fetch_engine="httpx",
        skip_link_check=False,
        start=start,
    )
