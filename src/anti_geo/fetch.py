from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from anti_geo.concealment import extract_concealment
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
    # Reddit anonymous gate (title often "Please wait for verification").
    "please wait for verification",
    "wait for verification",
    # Head-Fi custom interstitial (not Cloudflare wording).
    "help us keep head-fi secure",
    "real head-fi'er",
    "real head-fi",
    "went wrong while validating",
    "challenge scripts from loading",
    # Trustpilot / similar connection gates.
    "verifying your connection",
    "verifying connection",
)

_ARCHIVE_JUNK_SNIPPETS = (
    "please don't scroll past this",
    "wayback machine is fighting for universal access",
    "can you chip in?",
    "this url has been excluded from the wayback machine",
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


def looks_like_bot_wall(
    status_code: int | None,
    text: str,
    *,
    final_url: str | None = None,
    title: str | None = None,
) -> bool:
    """True when the response looks like a bot block or JS gate, not real content."""
    if status_code in (401, 403, 406, 429, 503):
        return True
    if _url_looks_like_bot_challenge(final_url or ""):
        return True
    blob = f"{title or ''} {text or ''}".lower()
    if any(snippet in blob for snippet in _BOT_WALL_SNIPPETS):
        return True
    return len((text or "").split()) < MIN_USEFUL_WORDS


def _url_looks_like_bot_challenge(url: str) -> bool:
    """Host-specific challenge paths that still return HTTP 200 + chrome text."""
    path = (urlparse(url or "").path or "").lower()
    return "/bot/challenge" in path


def _same_host(base: str, link: str) -> bool:
    return urlparse(base).netloc == urlparse(link).netloc


def _extract_visible_text(html: str) -> str:
    """Visible body text excluding CSS/DOM-concealed subtrees."""
    _, visible = extract_concealment(html, max_chars=MAX_TEXT_CHARS)
    return visible


def _is_transient_http_error(error: str | None) -> bool:
    """True for timeouts / connect blips worth one httpx retry before browser."""
    blob = (error or "").lower()
    markers = (
        "timed out",
        "timeout",
        "connecterror",
        "connect error",
        "connection reset",
        "connection aborted",
        "temporarily unavailable",
        "remote protocol error",
        "server disconnected",
        "network is unreachable",
    )
    return any(m in blob for m in markers)


def _fetch_html_httpx_once(url: str, timeout: float) -> _HtmlFetch:
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


def _fetch_html_httpx(url: str, timeout: float) -> _HtmlFetch:
    """GET with one retry on transient timeouts (slow hosts e.g. Scamadviser)."""
    first = _fetch_html_httpx_once(url, timeout)
    if first.error is None or not _is_transient_http_error(first.error):
        return first
    time.sleep(0.75)
    # Slightly longer read budget on retry; connect-heavy flaps often clear.
    return _fetch_html_httpx_once(url, max(timeout, timeout * 1.5))


_PLAYWRIGHT_LOCK = threading.Lock()

_CF_CHALLENGE_MARKERS = (
    "just a moment",
    "cf-mitigated",
    "challenges.cloudflare.com",
    "performing security verification",
    "verify you are human",
    "checking your browser",
    "attention required",
    "enable javascript and cookies",
    "help us keep head-fi secure",
    "real head-fi'er",
    "went wrong while validating",
    "challenge scripts from loading",
    "verifying your connection",
    "verifying connection",
)


def _html_looks_like_cf_challenge(html: str, *, title: str = "", final_url: str = "") -> bool:
    if _url_looks_like_bot_challenge(final_url):
        return True
    blob = f"{title} {(html or '')[:6000]}".lower()
    return any(marker in blob for marker in _CF_CHALLENGE_MARKERS)


def _browser_timeout_s(timeout: float) -> float:
    """Bot-wall / CF clears often need longer than the httpx timeout."""
    raw = os.environ.get("ANTI_GEO_BROWSER_TIMEOUT", "").strip()
    if raw:
        try:
            return max(timeout, float(raw))
        except ValueError:
            pass
    return max(timeout, 45.0)


def _browser_launch_attempt_count() -> int:
    """Headless chrome + headless chromium (+ optional headed persistent)."""
    return 3 if _headed_fetch_enabled() else 2


def _browser_hard_timeout_s(timeout: float) -> float:
    """Wall-clock cap for the whole Playwright session (all launch attempts).

    ``ANTI_GEO_BROWSER_HARD_TIMEOUT`` overrides (seconds). Default scales with
    per-attempt browser timeout × launch attempts + a small buffer so CF waits
    can finish, while unbounded ``launch`` / ``close`` / ``page.content`` hangs
    cannot block Mode B forever.
    """
    raw = os.environ.get("ANTI_GEO_BROWSER_HARD_TIMEOUT", "").strip()
    if raw:
        try:
            return max(5.0, float(raw))
        except ValueError:
            pass
    per_attempt = _browser_timeout_s(timeout)
    return per_attempt * _browser_launch_attempt_count() + 15.0


def _headed_fetch_enabled() -> bool:
    """Headed Chrome fallback for stubborn CF challenges (Mac overnight OK)."""
    raw = os.environ.get("ANTI_GEO_FETCH_HEADED", "auto").strip().lower()
    if raw in {"1", "true", "yes", "on", "always"}:
        return True
    if raw in {"0", "false", "no", "off", "never"}:
        return False
    return True  # auto → allow headed retry after headless CF fail


def _stealth_init_scripts() -> list[str]:
    return [
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});",
        """
        (() => {
          try {
            window.chrome = window.chrome || { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {
              get: () => [1, 2, 3, 4, 5],
            });
          } catch (e) {}
        })();
        """,
    ]


def _fetch_html_playwright(url: str, timeout: float) -> _HtmlFetch | None:
    """Chromium fetch with soft Cloudflare challenge waiting.

    Sync Playwright is not thread-safe; serialize browser launches.
    On CF interstitials, wait for clearance; optionally retry headed Chrome
    with a persistent profile (cookies survive across fetches).

    A wall-clock hard timeout wraps the whole session so unbounded Playwright
    ops (``launch`` / ``close`` / ``page.content``) cannot block callers forever.
    On hard timeout the global lock may stay held by the daemon worker until it
    exits; later browser callers fail fast with ``playwright_busy`` and fall
    through to archive/fixture via ``_finalize``.
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout  # noqa: F401
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return None

    hard_cap = _browser_hard_timeout_s(timeout)
    # Fail fast if a previous hung session still holds the lock.
    if not _PLAYWRIGHT_LOCK.acquire(timeout=min(2.0, hard_cap)):
        return _HtmlFetch(
            html="",
            final_url=url,
            status_code=None,
            redirect_count=0,
            error="playwright_busy",
        )
    _PLAYWRIGHT_LOCK.release()

    box: dict[str, _HtmlFetch | BaseException | None] = {"result": None, "error": None}

    def _worker() -> None:
        with _PLAYWRIGHT_LOCK:
            try:
                box["result"] = _fetch_html_playwright_unlocked(url, timeout)
            except BaseException as exc:  # noqa: BLE001
                box["error"] = exc

    thread = threading.Thread(target=_worker, name="anti-geo-playwright", daemon=True)
    thread.start()
    thread.join(hard_cap)
    if thread.is_alive():
        return _HtmlFetch(
            html="",
            final_url=url,
            status_code=None,
            redirect_count=0,
            error="playwright_hard_timeout",
        )
    if box["error"] is not None:
        return _HtmlFetch(
            html="",
            final_url=url,
            status_code=None,
            redirect_count=0,
            error=str(box["error"]),
        )
    result = box["result"]
    return result if isinstance(result, _HtmlFetch) else None


def _fetch_html_playwright_unlocked(url: str, timeout: float) -> _HtmlFetch:
    """Playwright body; caller must hold ``_PLAYWRIGHT_LOCK``."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    browser_timeout = _browser_timeout_s(timeout)
    timeout_ms = int(browser_timeout * 1000)
    cf_wait_ms = min(60_000, max(20_000, timeout_ms))
    profile_dir = os.environ.get(
        "ANTI_GEO_BROWSER_PROFILE",
        os.path.join(os.path.expanduser("~"), ".cache", "anti_geo_browser_profile"),
    )

    # Prefer real Chrome; headed persistent profile last for stubborn CF.
    launch_attempts: list[dict] = [
        {
            "mode": "launch",
            "headless": True,
            "channel": "chrome",
            "args": ["--disable-blink-features=AutomationControlled"],
            "ignore_default_args": ["--enable-automation"],
        },
        {
            "mode": "launch",
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled"],
            "ignore_default_args": ["--enable-automation"],
        },
    ]
    if _headed_fetch_enabled():
        launch_attempts.append(
            {
                "mode": "persistent",
                "headless": False,
                "channel": "chrome",
                "args": ["--disable-blink-features=AutomationControlled"],
                "ignore_default_args": ["--enable-automation"],
                "user_data_dir": profile_dir,
            }
        )

    def _attach_stealth(context) -> None:
        for script in _stealth_init_scripts():
            context.add_init_script(script)
        # Cap page.content / title / etc. that otherwise have no timeout.
        context.set_default_timeout(timeout_ms)

    def _load_page(page, *, PlaywrightTimeout) -> _HtmlFetch:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_function(
                "() => document.body && document.body.innerText.trim().length > 120",
                timeout=min(12_000, timeout_ms),
            )
        except PlaywrightTimeout:
            pass

        html = page.content()
        try:
            title = page.title() or ""
        except Exception:
            title = ""

        if _html_looks_like_cf_challenge(html, title=title, final_url=page.url):
            try:
                page.wait_for_function(
                    """() => {
                        const url = (location.href || '').toLowerCase();
                        if (url.includes('/bot/challenge')) return false;
                        const t = (document.title || '').toLowerCase();
                        const body = (document.body && document.body.innerText || '').toLowerCase();
                        if (t.includes('just a moment')) return false;
                        if (t.includes('verifying connection')) return false;
                        if (body.includes('performing security verification')) return false;
                        if (body.includes('checking your browser')) return false;
                        if (body.includes('verifying your connection')) return false;
                        if (body.includes('help us keep head-fi secure')) return false;
                        if (body.includes('incompatible browser extension')) return false;
                        return (document.body && document.body.innerText.trim().length > 400);
                    }""",
                    timeout=cf_wait_ms,
                )
                try:
                    page.wait_for_load_state("networkidle", timeout=min(10_000, cf_wait_ms))
                except PlaywrightTimeout:
                    pass
            except PlaywrightTimeout:
                pass
            html = page.content()
            try:
                title = page.title() or ""
            except Exception:
                pass

        status = response.status if response else None
        if status and status >= 400 and not _html_looks_like_cf_challenge(
            html, title=title, final_url=page.url
        ):
            status = 200
        return _HtmlFetch(
            html=html,
            final_url=page.url,
            status_code=status,
            redirect_count=0,
            error=None,
        )

    def _one_attempt(playwright, launch_kwargs: dict) -> _HtmlFetch | None:
        mode = launch_kwargs.get("mode", "launch")
        try:
            if mode == "persistent":
                os.makedirs(launch_kwargs["user_data_dir"], exist_ok=True)
                context = playwright.chromium.launch_persistent_context(
                    launch_kwargs["user_data_dir"],
                    headless=bool(launch_kwargs.get("headless", False)),
                    channel=launch_kwargs.get("channel"),
                    args=list(launch_kwargs.get("args") or []),
                    ignore_default_args=list(
                        launch_kwargs.get("ignore_default_args") or []
                    ),
                    user_agent=USER_AGENT,
                    locale="en-US",
                    viewport={"width": 1366, "height": 768},
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "Upgrade-Insecure-Requests": "1",
                    },
                )
                _attach_stealth(context)
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    return _load_page(page, PlaywrightTimeout=PlaywrightTimeout)
                finally:
                    context.close()

            browser = playwright.chromium.launch(
                headless=bool(launch_kwargs.get("headless", True)),
                channel=launch_kwargs.get("channel"),
                args=list(launch_kwargs.get("args") or []),
                ignore_default_args=list(launch_kwargs.get("ignore_default_args") or []),
            )
            try:
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    locale="en-US",
                    viewport={"width": 1366, "height": 768},
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "Upgrade-Insecure-Requests": "1",
                    },
                )
                _attach_stealth(context)
                page = context.new_page()
                return _load_page(page, PlaywrightTimeout=PlaywrightTimeout)
            finally:
                browser.close()
        except Exception as exc:  # noqa: BLE001
            return _HtmlFetch(
                html="",
                final_url=url,
                status_code=None,
                redirect_count=0,
                error=str(exc),
            )

    try:
        with sync_playwright() as playwright:
            last: _HtmlFetch | None = None
            for launch_kwargs in launch_attempts:
                hit = _one_attempt(playwright, launch_kwargs)
                if hit is None:
                    continue
                last = hit
                if hit.error:
                    continue
                title_guess = ""
                lower = (hit.html or "").lower()
                if "<title" in lower:
                    try:
                        soup_title = BeautifulSoup(hit.html, "html.parser").title
                        title_guess = (
                            soup_title.get_text(strip=True) if soup_title else ""
                        )
                    except Exception:
                        title_guess = ""
                if not _html_looks_like_cf_challenge(
                    hit.html, title=title_guess, final_url=hit.final_url or url
                ):
                    return hit
            if last is not None:
                return last
            return _HtmlFetch(
                html="",
                final_url=url,
                status_code=None,
                redirect_count=0,
                error="playwright_browser_unavailable",
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
    concealment, visible_text = extract_concealment(
        raw.html, url=raw.final_url or url, max_chars=MAX_TEXT_CHARS
    )
    page_context = extract_page_context(soup, visible_text, url=raw.final_url or url)
    segments = extract_page_segments(raw.html, raw.final_url or url)

    title = soup.title.get_text(strip=True) if soup.title else ""
    text = visible_text
    identity = extract_page_identity(soup, url=raw.final_url or url, title=title)

    link_count = len(soup.find_all("a", href=True))
    broken_ratio = 0.0 if skip_link_check else _check_broken_links(raw.final_url, raw.html)

    lower_html = raw.html.lower()
    status = raw.status_code or 0
    ok = 200 <= status < 400 and not looks_like_bot_wall(
        status, text, final_url=raw.final_url, title=title
    )

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
        concealment=concealment,
    )


def _fixture_root() -> str | None:
    raw = os.environ.get("ANTI_GEO_FETCH_FIXTURE_DIR", "").strip()
    if raw:
        return raw
    # Default: repo data/fetch_fixtures if present
    here = os.path.dirname(os.path.abspath(__file__))
    default = os.path.normpath(os.path.join(here, "..", "..", "data", "fetch_fixtures"))
    return default if os.path.isdir(default) else None


def _fixture_candidates(url: str) -> list[str]:
    """Map URL → possible on-disk HTML fixture basenames."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = (parsed.path or "/").rstrip("/") or "/"
    slug = path.strip("/").replace("/", "_") or "index"
    return [
        f"{host}_{slug}.html",
        f"{host}{path.replace('/', '_')}.html",
    ]


def _try_fixture_fetch(url: str, start: float) -> FetchResult | None:
    root = _fixture_root()
    if not root:
        return None
    for name in _fixture_candidates(url):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                html = fh.read()
        except OSError:
            continue
        if not html.strip():
            continue
        raw = _HtmlFetch(
            html=html,
            final_url=url,
            status_code=200,
            redirect_count=0,
            error=None,
        )
        return _build_fetch_result(
            url,
            raw,
            fetch_engine="fixture",
            skip_link_check=True,
            start=start,
        )
    return None


def _archive_enabled() -> bool:
    raw = os.environ.get("ANTI_GEO_FETCH_ARCHIVE", "auto").strip().lower()
    if raw in {"0", "false", "no", "off", "never"}:
        return False
    return True  # auto/on


def _archive_text_is_junk(text: str, title: str = "") -> bool:
    blob = f"{title} {text}".lower()
    if any(snippet in blob for snippet in _ARCHIVE_JUNK_SNIPPETS):
        return True
    # Soft-404 donation / empty toolbar shells are short and off-topic.
    return len(text.split()) < MIN_USEFUL_WORDS


def _wayback_id_form(wayback_url: str) -> str | None:
    """Convert a toolbar snapshot URL to the raw ``id_`` form."""
    marker = "/web/"
    if marker not in (wayback_url or "") or "id_/" in wayback_url:
        return None
    head, rest = wayback_url.split(marker, 1)
    ts, _, remainder = rest.partition("/")
    if not ts.isdigit() or not remainder:
        return None
    return f"{head}{marker}{ts}id_/{remainder}"


def _wayback_candidate_urls(url: str, timeout: float) -> list[str]:
    """Prefer a concrete snapshot (id_ raw HTML) over the bouncing /web/{url} redirect."""
    candidates: list[str] = []
    try:
        api = f"https://archive.org/wayback/available?url={url}"
        with httpx.Client(timeout=min(max(timeout, 10.0), 20.0), follow_redirects=True) as client:
            resp = client.get(api)
            data = resp.json() if resp.status_code == 200 else {}
        snap = (data.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available") and snap.get("url"):
            snap_url = str(snap["url"]).replace("http://web.archive.org/", "https://web.archive.org/")
            id_url = _wayback_id_form(snap_url)
            if id_url:
                candidates.append(id_url)
            candidates.append(snap_url)
    except Exception:
        pass
    candidates.append(f"https://web.archive.org/web/{url}")
    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _try_archive_fetch(url: str, timeout: float, start: float) -> FetchResult | None:
    """Last-resort Wayback Machine fetch when live origin is CF-walled."""
    if not _archive_enabled():
        return None
    tried: set[str] = set()
    queue = _wayback_candidate_urls(url, timeout)
    while queue:
        archive_url = queue.pop(0)
        if archive_url in tried:
            continue
        tried.add(archive_url)
        raw = _fetch_html_httpx(archive_url, max(timeout, 20.0))
        if raw.error or not raw.html:
            continue
        # If Wayback bounced to a toolbar URL, also try the raw id_ form.
        id_follow = _wayback_id_form(raw.final_url or "")
        if id_follow and id_follow not in tried:
            queue.insert(0, id_follow)
        preview = _extract_visible_text(raw.html)
        title = ""
        try:
            soup_title = BeautifulSoup(raw.html, "html.parser").title
            title = soup_title.get_text(strip=True) if soup_title else ""
        except Exception:
            title = ""
        if looks_like_bot_wall(raw.status_code, preview, title=title):
            continue
        if _html_looks_like_cf_challenge(raw.html, title=title, final_url=raw.final_url or ""):
            continue
        if _archive_text_is_junk(preview, title):
            continue
        # Rewrite final_url back to the live target for scoring/identity.
        patched = _HtmlFetch(
            html=raw.html,
            final_url=url,
            status_code=200 if (raw.status_code or 0) < 400 else raw.status_code,
            redirect_count=raw.redirect_count,
            error=None,
        )
        return _build_fetch_result(
            url,
            patched,
            fetch_engine="archive",
            skip_link_check=True,
            start=start,
        )
    return None


def _result_still_cf_blocked(result: FetchResult) -> bool:
    if _url_looks_like_bot_challenge(result.final_url or ""):
        return True
    if looks_like_bot_wall(
        result.status_code,
        result.text or "",
        final_url=result.final_url,
        title=result.title,
    ):
        return True
    if result.ok and not _html_looks_like_cf_challenge(
        result.text or "", title=result.title or "", final_url=result.final_url or ""
    ):
        # ok pages with real text are fine
        if len((result.text or "").split()) >= MIN_USEFUL_WORDS:
            return False
    return (not result.ok) or _html_looks_like_cf_challenge(
        result.text or "", title=result.title or "", final_url=result.final_url or ""
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


def fetch_page(url: str, timeout: float = 20.0, *, force_browser: bool = False) -> FetchResult:
    """Fetch URL and extract visible text + light structural signals.

    Uses httpx by default (one transient-timeout retry). On bot walls (403,
    Cloudflare, Akamai) prefers a Wayback/fixture fallback when available, then
    retries with Chromium (Playwright) when installed (``ANTI_GEO_FETCH=auto``,
    default). Browser path waits for Cloudflare interstitials and may retry
    headed Chrome (``ANTI_GEO_FETCH_HEADED=auto``), under a hard wall-clock cap
    (``ANTI_GEO_BROWSER_HARD_TIMEOUT``). If still blocked, ``_finalize`` retries
    archive/fixture.

    Default ``timeout`` is 20s: some review/check sites (e.g. Scamadviser)
    regularly exceed a 12s read budget and otherwise fall into brittle
    archive/Playwright paths.
    """
    start = time.perf_counter()
    mode = _fetch_mode()
    browser_timeout = _browser_timeout_s(timeout)

    def _finalize(result: FetchResult) -> FetchResult:
        if not _result_still_cf_blocked(result):
            return result
        archived = _try_archive_fetch(url, timeout, start)
        if archived is not None and archived.ok:
            return archived
        fixture = _try_fixture_fetch(url, start)
        if fixture is not None and fixture.ok:
            return fixture
        return result

    def _archive_or_fixture_before_browser() -> FetchResult | None:
        """Cheap stable fallbacks before Playwright (auto mode only)."""
        if mode != "auto":
            return None
        archived = _try_archive_fetch(url, timeout, start)
        if archived is not None and archived.ok:
            return archived
        fixture = _try_fixture_fetch(url, start)
        if fixture is not None and fixture.ok:
            return fixture
        return None

    if force_browser or mode == "browser":
        browser_result = _try_browser_fetch(url, browser_timeout, start)
        if browser_result is not None:
            return _finalize(browser_result)
        elapsed = (time.perf_counter() - start) * 1000
        empty = FetchResult(
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
        return _finalize(empty)

    raw = _fetch_html_httpx(url, timeout)
    if raw.error:
        if mode != "httpx":
            early = _archive_or_fixture_before_browser()
            if early is not None:
                return early
            browser_result = _try_browser_fetch(url, browser_timeout, start)
            if browser_result is not None:
                return _finalize(browser_result)
        result = _build_fetch_result(
            url,
            raw,
            fetch_engine="httpx",
            skip_link_check=False,
            start=start,
        )
        return _finalize(result)

    preview = _extract_visible_text(raw.html)
    if mode != "httpx" and looks_like_bot_wall(
        raw.status_code, preview, final_url=raw.final_url
    ):
        early = _archive_or_fixture_before_browser()
        if early is not None:
            return early
        browser_result = _try_browser_fetch(url, browser_timeout, start)
        if browser_result is not None:
            return _finalize(browser_result)

    result = _build_fetch_result(
        url,
        raw,
        fetch_engine="httpx",
        skip_link_check=False,
        start=start,
    )
    return _finalize(result)
