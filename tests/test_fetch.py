from anti_geo.fetch import looks_like_bot_wall


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
