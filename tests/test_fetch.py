from anti_geo.fetch import (
    _html_looks_like_cf_challenge,
    fetch_page,
    looks_like_bot_wall,
)
from anti_geo.hosts import is_major_news_host


def test_bot_wall_http_403():
    assert looks_like_bot_wall(403, "Access Denied")


def test_bot_wall_cloudflare_interstitial():
    assert looks_like_bot_wall(200, "Just a moment...")


def test_bot_wall_head_fi_challenge():
    assert looks_like_bot_wall(
        200,
        "Help us keep Head-Fi secure. Checking you are a real Head-Fi'er! "
        + (" nav link " * 40),
        final_url="https://www.head-fi.org/bot/challenge",
    )
    assert looks_like_bot_wall(
        200,
        "Looks like something went wrong while validating "
        + (" keep in mind ad blockers " * 20),
        final_url="https://www.head-fi.org/bot/challenge/failed",
    )


def test_bot_wall_trustpilot_verifying():
    assert looks_like_bot_wall(200, "Verifying your connection... Retrying (1/3)...")


def test_cf_challenge_html_detector():
    assert _html_looks_like_cf_challenge(
        "<html><title>Just a moment...</title><body>Checking your browser</body></html>",
        title="Just a moment...",
    )
    assert _html_looks_like_cf_challenge(
        "<html><body>x</body></html>",
        final_url="https://www.head-fi.org/bot/challenge",
    )
    assert not _html_looks_like_cf_challenge(
        "<html><title>Dietary Supplements</title><body>"
        + (" weight loss fact sheet for consumers " * 40)
        + "</body></html>",
        title="Dietary Supplements",
    )


def test_fixture_fetch_for_cf_url(tmp_path, monkeypatch):
    html = (
        "<html><head><title>Dietary Supplements for Weight Loss - Consumer</title></head>"
        "<body>" + (" weight loss dietary supplements fact sheet " * 50) + "</body></html>"
    )
    name = "ods.od.nih.gov_factsheets_WeightLoss-Consumer.html"
    (tmp_path / name).write_text(html, encoding="utf-8")
    monkeypatch.setenv("ANTI_GEO_FETCH_FIXTURE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTI_GEO_FETCH", "httpx")
    monkeypatch.setenv("ANTI_GEO_FETCH_ARCHIVE", "never")

    def _boom(url: str, timeout: float = 12.0):
        from anti_geo.fetch import _HtmlFetch

        return _HtmlFetch(
            html="<html><title>Just a moment...</title><body>Checking your browser "
            + ("x " * 40)
            + "</body></html>",
            final_url=url,
            status_code=403,
            redirect_count=0,
            error=None,
        )

    monkeypatch.setattr("anti_geo.fetch._fetch_html_httpx", _boom)
    result = fetch_page("https://ods.od.nih.gov/factsheets/WeightLoss-Consumer/")
    assert result.ok is True
    assert result.fetch_engine == "fixture"
    assert "weight loss" in result.text.lower()

def test_bot_wall_akamai_reference():
    assert looks_like_bot_wall(403, "Reference #18.c7cf5868 errors.edgesuite.net")


def test_bot_wall_js_gate():
    assert looks_like_bot_wall(200, "forbes.com Please enable JS and disable any ad blocker")


def test_real_content_not_bot_wall():
    text = " ".join(["word"] * 50)
    assert not looks_like_bot_wall(200, text)


def test_thin_error_page_is_bot_wall():
    assert looks_like_bot_wall(200, "Error 404")


def test_major_news_hosts():
    assert is_major_news_host("www.nytimes.com")
    assert is_major_news_host("https://www.theguardian.com/art/foo")
    assert is_major_news_host("reuters.com")
    assert not is_major_news_host("weloveart.com")


def test_fetch_page_attempts_reddit(monkeypatch):
    """Reddit is fetched normally (Mode A still skips Mode B via UGC role)."""
    calls: list[str] = []

    def _fake_httpx(url: str, timeout: float = 12.0):
        from anti_geo.fetch import _HtmlFetch

        calls.append(url)
        return _HtmlFetch(
            html="<html><head><title>r/python</title></head><body>"
            + (" python community discussion " * 40)
            + "</body></html>",
            final_url=url,
            status_code=200,
            redirect_count=0,
            error=None,
        )

    monkeypatch.setattr("anti_geo.fetch._fetch_html_httpx", _fake_httpx)
    monkeypatch.setenv("ANTI_GEO_FETCH", "httpx")
    result = fetch_page("https://www.reddit.com/r/python/")
    assert calls == ["https://www.reddit.com/r/python/"]
    assert result.ok is True
    assert result.fetch_engine == "httpx"
    assert result.error is None


def test_archive_before_browser_on_bot_wall(monkeypatch):
    """Auto mode: Wayback/fixture before Playwright when httpx hits a bot wall."""
    from anti_geo.fetch import _HtmlFetch
    from anti_geo.models import FetchResult

    browser_calls: list[str] = []

    def _wall(url: str, timeout: float = 12.0):
        return _HtmlFetch(
            html="<html><title>Just a moment...</title><body>Checking your browser "
            + ("x " * 40)
            + "</body></html>",
            final_url=url,
            status_code=403,
            redirect_count=0,
            error=None,
        )

    def _archive(url: str, timeout: float, start: float):
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            ok=True,
            error=None,
            title="Yearly - The HEADPHONE Community",
            text=" ".join(["headphones"] * 80),
            link_count=3,
            broken_link_ratio=0.0,
            redirect_count=0,
            response_time_ms=10.0,
            has_privacy_page=False,
            has_contact_page=False,
            page_context=None,
            fetch_engine="archive",
        )

    def _browser(url: str, timeout: float, start: float):
        browser_calls.append(url)
        raise AssertionError("browser should not run when archive succeeds")

    monkeypatch.setenv("ANTI_GEO_FETCH", "auto")
    monkeypatch.setenv("ANTI_GEO_FETCH_ARCHIVE", "auto")
    monkeypatch.setattr("anti_geo.fetch._fetch_html_httpx", _wall)
    monkeypatch.setattr("anti_geo.fetch._try_archive_fetch", _archive)
    monkeypatch.setattr("anti_geo.fetch._try_browser_fetch", _browser)

    result = fetch_page("https://forum.headphones.com/top")
    assert result.ok is True
    assert result.fetch_engine == "archive"
    assert browser_calls == []


def test_playwright_hard_timeout_returns(monkeypatch):
    """Hung Playwright session must return under the hard wall-clock cap."""
    import time

    from anti_geo.fetch import _HtmlFetch, _fetch_html_playwright

    try:
        import playwright  # noqa: F401
    except ImportError:
        return

    def _hang(url: str, timeout: float):
        time.sleep(30)
        return _HtmlFetch(
            html="",
            final_url=url,
            status_code=None,
            redirect_count=0,
            error=None,
        )

    monkeypatch.setenv("ANTI_GEO_BROWSER_HARD_TIMEOUT", "1")
    monkeypatch.setattr("anti_geo.fetch._fetch_html_playwright_unlocked", _hang)

    started = time.perf_counter()
    hit = _fetch_html_playwright("https://forum.headphones.com/top", timeout=12.0)
    elapsed = time.perf_counter() - started
    assert hit is not None
    assert hit.error == "playwright_hard_timeout"
    assert elapsed < 8.0
