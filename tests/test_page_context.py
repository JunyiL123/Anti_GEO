from bs4 import BeautifulSoup

from anti_geo.page_context import (
    AFFILIATE_LINK_PARAM_RE,
    classify_page_commercial_tier,
    extract_page_context,
)
from anti_geo.platform_role import classify_content_role
from anti_geo.models import FetchResult, PageContextSignals


def test_link_sponsored_rel_sets_high_tier():
    html = (
        "<html><body><article><p>Review</p>"
        '<a rel="sponsored" href="https://shop.example/item">Buy</a>'
        "</article></body></html>"
    )
    soup = BeautifulSoup(html, "html.parser")
    ctx = extract_page_context(soup, "Product review with sponsored link", url="https://example.com/review")
    assert "link_sponsored" in ctx.flags
    assert ctx.commercial_tier == "high"
    assert ctx.has_affiliate_links


def test_affiliate_disclosure_text_sets_high_tier():
    html = (
        "<html><body><article>"
        "<p>This article contains sponsored affiliate partnerships.</p>"
        "</article></body></html>"
    )
    soup = BeautifulSoup(html, "html.parser")
    ctx = extract_page_context(soup, "sponsored affiliate partnerships", url="https://example.com")
    assert "affiliate_disclosure" in ctx.flags
    assert ctx.commercial_tier == "high"


def test_affiliate_link_params_medium_tier():
    html = (
        "<html><body><article>"
        '<a href="https://amazon.com/dp/1?tag=aff-20">Link</a>'
        "</article></body></html>"
    )
    soup = BeautifulSoup(html, "html.parser")
    ctx = extract_page_context(soup, "Check this product link", url="https://example.com/post")
    assert "affiliate_link_params" in ctx.flags
    assert ctx.commercial_tier == "medium"


def test_utm_tracking_alone_is_not_affiliate():
    html = (
        "<html><body><article>"
        '<a href="https://example.com/x?utm_source=newsletter&utm_campaign=spring">Read more</a>'
        "</article></body></html>"
    )
    soup = BeautifulSoup(html, "html.parser")
    assert not AFFILIATE_LINK_PARAM_RE.search(
        "https://example.com/x?utm_source=newsletter&utm_campaign=spring"
    )
    ctx = extract_page_context(soup, "Read more about proposals", url="https://example.com/post")
    assert "affiliate_link_params" not in ctx.flags
    assert ctx.commercial_tier == "none"


def test_chrome_sponsored_does_not_raise_tier():
    html = """
    <html><body>
      <nav><a rel="sponsored" href="https://partner.example/ad">Ad</a></nav>
      <footer><a href="https://shop.example/?tag=footer-20">Shop</a></footer>
      <article>
        <h1>Romantic ways to propose</h1>
        <p>Plan a picnic, write a letter, keep it personal.</p>
      </article>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    ctx = extract_page_context(
        soup,
        "Romantic ways to propose Plan a picnic",
        url="https://www.theknot.com/content/romantic-ways-to-propose",
    )
    assert "link_sponsored" not in ctx.flags
    assert "affiliate_link_params" not in ctx.flags
    assert "site_chrome_monetization" in ctx.flags
    assert ctx.commercial_tier == "none"
    fetch = FetchResult(
        url="https://www.theknot.com/content/romantic-ways-to-propose",
        final_url="https://www.theknot.com/content/romantic-ways-to-propose",
        status_code=200,
        ok=True,
        error=None,
        title="Romantic ways to propose",
        text="Plan a picnic, write a letter, keep it personal.",
        link_count=3,
        broken_link_ratio=0.0,
        redirect_count=0,
        response_time_ms=100,
        has_privacy_page=False,
        has_contact_page=False,
        page_context=ctx,
    )
    assert classify_content_role(fetch.url, fetch=fetch) == "factual_blog"


def test_classify_low_tier_from_commercial_score():
    tier, triggers = classify_page_commercial_tier([], commercial_context_score=0.6, url_path="/blog")
    assert tier == "low"
    assert "commercial_context_score" in triggers


def test_high_affiliate_editorial_without_cta_is_listicle_not_product():
    fetch = FetchResult(
        url="https://example.com/content/romantic-ways-to-propose",
        final_url="https://example.com/content/romantic-ways-to-propose",
        status_code=200,
        ok=True,
        error=None,
        title="Romantic ways to propose",
        text="Plan a picnic.",
        link_count=2,
        broken_link_ratio=0.0,
        redirect_count=0,
        response_time_ms=50,
        has_privacy_page=False,
        has_contact_page=False,
        page_context=PageContextSignals(
            cta_density=0.0,
            commercial_context_score=0.0,
            structure_density=0.2,
            list_item_count=0,
            table_count=0,
            has_faq_schema=False,
            flags=["link_sponsored"],
            commercial_tier="high",
        ),
    )
    assert classify_content_role(fetch.url, fetch=fetch) == "expert_listicle"
