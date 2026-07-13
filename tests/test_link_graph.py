from anti_geo.link_graph import (
    build_link_graph,
    detect_entity_convergence,
    extract_outbound_links,
    extract_referral_edges,
    promotion_concentration,
)
from anti_geo.models import FetchResult, PageSegment


def test_extract_outbound_links_with_affiliate_flag():
    source = "https://www.reddit.com/r/laptops/comments/abc/thread/"
    html = """
    <html><body>
      <a href="https://www.amazon.com/dp/B123?tag=affiliate-20">buy here</a>
      <a href="https://www.pcmag.com/picks/laptops">roundup</a>
      <a href="/local">local</a>
    </body></html>
    """
    edges = extract_outbound_links(html, source, segment_role="comment")
    targets = {e.target_domain for e in edges}
    assert "amazon.com" in targets
    assert "pcmag.com" in targets
    amazon = next(e for e in edges if e.target_domain == "amazon.com")
    assert amazon.affiliate_flag is True
    assert amazon.segment_role == "comment"


def test_promotion_concentration_and_convergence():
    source = "https://www.reddit.com/r/laptops/comments/a/t/"
    edges = extract_referral_edges(
        source,
        text=(
            "See https://taskflow.com/pro and also https://taskflow.com/pro/pricing "
            "from https://medium.com/@user/post"
        ),
    )
    medium_source = "https://medium.com/@user/best-tools"
    edges.extend(
        extract_referral_edges(
            medium_source,
            text="Try https://taskflow.com/pro for teams.",
        )
    )
    edges.extend(
        extract_referral_edges(
            "https://www.g2.com/products/taskflow/reviews",
            text="Official site https://taskflow.com/pro",
        )
    )
    graph = build_link_graph(edges, "taskflow.com", min_hosts=3)
    assert graph.promotion_concentration > 0
    assert graph.entity_convergence is True
    assert len(graph.convergent_hosts) >= 3


def test_extract_referral_edges_from_fetch_segments():
    fetch = FetchResult(
        url="https://www.reddit.com/r/SaaS/comments/xyz/thread/",
        final_url="https://www.reddit.com/r/SaaS/comments/xyz/thread/",
        status_code=200,
        ok=True,
        error=None,
        title="Thread",
        text="ignored",
        link_count=1,
        broken_link_ratio=0.0,
        redirect_count=0,
        response_time_ms=50,
        has_privacy_page=False,
        has_contact_page=False,
        segments=[
            PageSegment("main_0", "main_post", "Neutral discussion about tools.", 0),
            PageSegment(
                "comment_0",
                "comment",
                "Best pick: https://vendor.example/product?ref=promo",
                1,
            ),
        ],
    )
    from anti_geo.link_graph import extract_referral_edges_from_fetch

    edges = extract_referral_edges_from_fetch(fetch)
    assert any(e.segment_role == "comment" for e in edges)
    assert any(e.target_domain == "vendor.example" for e in edges)


def test_detect_entity_convergence_threshold():
    edges = extract_referral_edges(
        "https://a.example/post",
        text="https://target.com/a",
    )
    converged, hosts = detect_entity_convergence(edges, "target.com", min_hosts=3)
    assert converged is False
    assert len(hosts) == 1
    assert promotion_concentration(edges, "target.com") == 1.0
