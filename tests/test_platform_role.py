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
    assert registrable_domain("shop.example.co.uk") == "example.co.uk"
    assert registrable_domain("www.example.com.au") == "example.com.au"
    assert registrable_domain("foo.co.uk") == "foo.co.uk"


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


def test_classify_app_store_ratings_as_review_profile():
    indus = "https://www.indusappstore.com/ratings-and-reviews/com.lemonn.app/"
    assert classify_content_role(indus) == "review_profile"
    assert is_parasitic_referrer(url=indus, role="review_profile")
    assert (
        classify_content_role(
            "https://apps.example.com/app/foo/user-reviews/"
        )
        == "review_profile"
    )


def test_classify_youtube_watch_as_ugc_parasitic():
    watch = "https://www.youtube.com/watch?v=wX7gdIeon7A"
    assert classify_content_role(watch) == "ugc_thread"
    assert is_ugc_role(classify_content_role(watch))
    assert is_parasitic_referrer(url=watch, role="ugc_thread")
    shorts = "https://www.youtube.com/shorts/abc123xyz"
    assert classify_content_role(shorts) == "ugc_thread"
    assert is_parasitic_referrer(url=shorts, role="ugc_thread")
    short_link = "https://youtu.be/wX7gdIeon7A"
    assert classify_content_role(short_link) == "ugc_thread"
    # Channel / home are not open-posting video surfaces.
    assert classify_content_role("https://www.youtube.com/") == "factual_blog"
    assert (
        classify_content_role("https://www.youtube.com/channel/UCabcdef")
        == "factual_blog"
    )
    # Generic /watch on other hosts must not become UGC.
    assert (
        classify_content_role("https://www.example.com/watch?v=abc")
        == "factual_blog"
    )


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


def test_forum_subdomain_indexes_are_ugc_not_blog():
    """Discourse-style forum.brand.com/top must not fall through to factual_blog."""
    cases = [
        "https://forum.headphones.com/top",
        "https://forum.headphones.com/latest",
        "https://forum.headphones.com/",
        "https://forums.example.com/c/general/5",
        "https://forum.hifiguides.com/t/how-to-read-graphs/14188",
    ]
    for url in cases:
        role = classify_content_role(url)
        assert role == "ugc_thread", url
        assert is_ugc_role(role), url
        assert is_parasitic_referrer(url=url, role=role), url


def test_classify_board_and_chitchat_as_ugc():
    cutout = (
        "https://www.cutoutandkeep.net/board/general/chit_chat/7886-feedspot"
    )
    assert classify_content_role(cutout) == "ugc_thread"
    assert is_parasitic_referrer(url=cutout, role="ugc_thread")
    assert (
        classify_content_role(
            "https://forum.example.com/threads/welcome-to-the-club.123/"
        )
        == "ugc_thread"
    )
    assert (
        classify_content_role(
            "https://community.example.com/viewtopic.php?t=42"
        )
        == "ugc_thread"
    )
    assert (
        classify_content_role(
            "https://discourse.example.com/t/install-guide/12345"
        )
        == "ugc_thread"
    )


def test_classify_forum_software_url_shapes_as_ugc():
    """Broad coverage across common forum engines (path / query / SaaS host)."""
    cases = [
        # Flarum
        "https://discuss.example.com/d/welcome-to-flarum/12",
        # MyBB SEO
        "https://mybb.example.com/thread-123-hello-world.html",
        "https://mybb.example.com/forum-5-page-2.html",
        # SMF query
        "https://smf.example.com/index.php?topic=456.0",
        "https://smf.example.com/index.php?board=2.0",
        # Vanilla / NodeBB numeric
        "https://vanilla.example.com/discussion/789/slug-here",
        "https://nodebb.example.com/topic/42/some-title",
        # Invision (IPS)
        "https://ips.example.com/index.php?/topic/99-some-title/",
        # phpBB / vBulletin PHP endpoints
        "https://vb.example.com/showthread.php?tid=100",
        "https://phpbb.example.com/viewforum.php?f=3",
        # SaaS forum hosts (arbitrary paths still UGC)
        "https://coolclub.proboards.com/thread/55/promo",
        "https://myboard.forumotion.com/t123-topic",
        "https://shoppers.boards.net/post/999",
    ]
    for url in cases:
        role = classify_content_role(url)
        assert role == "ugc_thread", url
        assert is_parasitic_referrer(url=url, role=role), url


def test_non_forum_query_t_param_not_ugc():
    """Bare ?t= timestamps must not trigger forum detection."""
    url = "https://www.example.com/blog/article?t=1710000000"
    assert classify_content_role(url) == "factual_blog"
    assert not is_parasitic_referrer(url=url, role="factual_blog")


def test_classify_imageboard_urls_as_ugc():
    """4chan-like /res/ threads and imageboard hosts are open-posting surfaces."""
    cases = [
        "https://boards.4chan.org/g/thread/987654321",
        "https://boards.4channel.org/pol/thread/12345",
        "https://boards.4chan.org/b/res/12345678.html",
        "https://8kun.top/qresearch/res/123.html",
        "https://lainchan.org/tech/res/456.html",
        "https://endchan.net/tech/res/789.html",
        # Host alone is enough on known imageboard platforms
        "https://boards.4chan.org/g/",
        "https://cool.4chan.org/xyz/catalog",
    ]
    for url in cases:
        role = classify_content_role(url)
        assert role == "ugc_thread", url
        assert is_parasitic_referrer(url=url, role=role), url


def test_res_path_without_imageboard_context_still_ugc():
    """Classic Futaba /res/N.html paths are thread surfaces on any host."""
    url = "https://imgboard.example.com/tech/res/42.html"
    assert classify_content_role(url) == "ugc_thread"
    assert is_parasitic_referrer(url=url, role="ugc_thread")


def test_classify_bbb_customer_reviews_as_review_profile():
    bbb = (
        "https://www.bbb.org/us/ca/mill-valley/profile/"
        "internet-marketing-services/feedspot-1116-530913/customer-reviews"
    )
    assert classify_content_role(bbb) == "review_profile"
    assert is_parasitic_referrer(url=bbb, role="review_profile")
    assert (
        classify_content_role(
            "https://www.example.com/company/acme/complaints/"
        )
        == "review_profile"
    )


def test_classify_feedspot_style_directory_as_listicle_and_parasitic():
    feedspot = "https://forums.feedspot.com/pc_gaming_forums/"
    assert classify_content_role(feedspot) == "expert_listicle"
    assert not is_ugc_role(classify_content_role(feedspot))
    assert is_parasitic_referrer(url=feedspot, role="expert_listicle")
    grow = "https://reddgrow.example/directory/mental-health/talkspace"
    assert classify_content_role(grow) == "expert_listicle"
    assert is_parasitic_referrer(url=grow, role="expert_listicle")


def test_feedspot_referrer_mix_counts_board_and_bbb():
    """Surfaces from the gaming-forums investigation should count parasitic."""
    refs = [
        (
            "https://www.cutoutandkeep.net/board/general/chit_chat/7886-feedspot",
            "ugc_thread",
        ),
        (
            "https://www.bbb.org/us/ca/mill-valley/profile/"
            "internet-marketing-services/feedspot-1116-530913/customer-reviews",
            "review_profile",
        ),
        (
            "https://www.reddit.com/r/PartneredYoutube/comments/164nqx4/"
            "has_anyone_used_feedspot_to_promote_their_youtube/",
            "ugc_thread",
        ),
        (
            "https://www.scamadviser.com/check-website/feedspot.com",
            "expert_listicle",
        ),
    ]
    parasitic = [
        is_parasitic_referrer(url=u, role=r) for u, r in refs
    ]
    assert parasitic == [True, True, True, False]
