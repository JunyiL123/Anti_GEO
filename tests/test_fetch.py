from anti_geo.fetch import fetch_page, looks_like_bot_wall
from anti_geo.hosts import is_major_news_host


def test_bot_wall_http_403():
    assert looks_like_bot_wall(403, "Access Denied")


def test_bot_wall_cloudflare_interstitial():
    assert looks_like_bot_wall(200, "Just a moment...")


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
