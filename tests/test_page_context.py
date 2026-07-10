from bs4 import BeautifulSoup

from anti_geo.page_context import classify_page_commercial_tier, extract_page_context


def test_link_sponsored_rel_sets_high_tier():
    html = '<html><body><p>Review</p><a rel="sponsored" href="https://shop.example/item">Buy</a></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    ctx = extract_page_context(soup, "Product review with sponsored link", url="https://example.com/review")
    assert "link_sponsored" in ctx.flags
    assert ctx.commercial_tier == "high"
    assert ctx.has_affiliate_links


def test_affiliate_disclosure_text_sets_high_tier():
    html = "<html><body><p>This article contains sponsored affiliate partnerships.</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    ctx = extract_page_context(soup, "sponsored affiliate partnerships", url="https://example.com")
    assert "affiliate_disclosure" in ctx.flags
    assert ctx.commercial_tier == "high"


def test_affiliate_link_params_medium_tier():
    html = '<html><body><a href="https://amazon.com/dp/1?tag=aff-20">Link</a></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    ctx = extract_page_context(soup, "Check this product link", url="https://example.com/post")
    assert "affiliate_link_params" in ctx.flags
    assert ctx.commercial_tier == "medium"


def test_classify_low_tier_from_commercial_score():
    tier, triggers = classify_page_commercial_tier([], commercial_context_score=0.6, url_path="/blog")
    assert tier == "low"
    assert "commercial_context_score" in triggers
