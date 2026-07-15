from anti_geo.models import FetchResult, PageContextSignals
from anti_geo.platform_role import (
    classify_content_role,
    is_parasitic_referrer,
    is_ugc_role,
    registrable_domain,
)


def test_registrable_domain():
    assert registrable_domain("www.pcmag.com") == "pcmag.com"
    assert registrable_domain("uk.pcmag.com") == "pcmag.com"


def test_classify_institutional():
    assert classify_content_role("https://www.nih.gov/health") == "institutional"


def test_classify_ugc_thread():
    assert (
        classify_content_role("https://www.reddit.com/r/laptops/comments/abc123/thread/")
        == "ugc_thread"
    )


def test_classify_linkedin_and_x_as_ugc():
    assert (
        classify_content_role(
            "https://www.linkedin.com/posts/someone_activity-123"
        )
        == "ugc_thread"
    )
    assert (
        classify_content_role("https://www.linkedin.com/feed/update/urn:li:activity:1")
        == "ugc_thread"
    )
    assert (
        classify_content_role("https://x.com/user/status/1234567890") == "ugc_thread"
    )


def test_classify_review_profile():
    assert classify_content_role("https://www.g2.com/products/securevault/reviews") == "review_profile"


def test_classify_editorial_picks():
    assert (
        classify_content_role("https://www.pcmag.com/picks/the-best-budget-laptops")
        == "editorial"
    )


def test_classify_social_posts_are_ugc_not_listicle():
    assert (
        classify_content_role(
            "https://www.example.com/posts/UGwxyz_best-earbuds-rec"
        )
        == "ugc_thread"
    )


def test_classify_medium_style_p_path_is_listicle_not_ugc():
    url = "https://writer.example.com/p/abc123earfun"
    assert classify_content_role(url) == "expert_listicle"
    assert not is_ugc_role(classify_content_role(url))
    assert is_parasitic_referrer(url=url, role="expert_listicle")


def test_plain_blog_parasitic_only_when_high_risk():
    url = "https://example.com/blog/my-review"
    role = classify_content_role(url)
    assert role == "factual_blog"
    assert not is_parasitic_referrer(url=url, role=role, content_high_risk=False)
    assert is_parasitic_referrer(url=url, role=role, content_high_risk=True)


def test_editorial_not_parasitic():
    url = "https://www.pcmag.com/picks/the-best-budget-laptops"
    assert not is_parasitic_referrer(url=url, role="editorial")


def test_is_ugc_role():
    assert is_ugc_role("ugc_thread")
    assert not is_ugc_role("expert_listicle")
    assert not is_ugc_role("editorial")


def test_classify_commercial_product_amazon():
    fetch = FetchResult(
        url="https://www.amazon.com/dp/B08SHN3TZP",
        final_url="https://www.amazon.com/dp/B08SHN3TZP",
        status_code=200,
        ok=True,
        error=None,
        title="Dell Chromebook",
        text="Buy now. Add to cart.",
        link_count=5,
        broken_link_ratio=0.0,
        redirect_count=0,
        response_time_ms=100,
        has_privacy_page=False,
        has_contact_page=False,
        page_context=PageContextSignals(
            cta_density=0.2,
            commercial_context_score=0.7,
            structure_density=0.3,
            list_item_count=0,
            table_count=0,
            has_faq_schema=False,
            flags=["commercial_cta", "affiliate_link_params"],
            commercial_tier="high",
        ),
    )
    assert classify_content_role(fetch.url, fetch=fetch) == "commercial_product"
