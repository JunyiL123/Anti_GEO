from anti_geo.investigation import ReferralProfile, tighten_actions_with_referral
from anti_geo.models import PageSegment
from anti_geo.referrer_content import (
    ReferrerExcerptCandidate,
    build_excerpt_candidate,
    content_score_eligible,
    editability_score,
    manipulability_score,
    referrer_content_tighten_extras,
    score_top_referrers,
    select_eligible_referrers,
    thread_surface_score,
)


def test_manipulability_prefers_thread_paths():
    thread = manipulability_score(
        "https://forum.example/r/x/comments/abc/earfun-earbuds/"
    )
    article = manipulability_score("https://news.example/tech/2026/earbud-roundup")
    assert thread > article
    assert thread >= 0.55


def test_manipulability_lower_for_gov():
    score = manipulability_score("https://www.cdc.gov/comments/foo")
    assert score < 0.55


def test_editability_elevates_blogs_and_editorials():
    blog = editability_score(
        "https://news.example/tech/2026/earbud-guide",
        role="factual_blog",
    )
    editorial = editability_score(
        "https://reviews.example/picks/best-earbuds",
        role="editorial",
    )
    product = editability_score(
        "https://shop.example/products/earfun",
        role="commercial_product",
    )
    assert blog >= 0.4
    assert editorial >= 0.5
    assert blog > product
    assert editorial > product
    # No thread path → thread surface stays low; editability drives priority.
    assert thread_surface_score("https://news.example/tech/2026/earbud-guide") == 0.0
    assert manipulability_score(
        "https://news.example/tech/2026/earbud-guide",
        role="factual_blog",
    ) == blog


def test_content_score_eligible_parasitic_and_soft_not_commercial():
    assert content_score_eligible(
        "https://forum.example/r/x/comments/abc/thread/",
        "ugc_thread",
    )
    assert content_score_eligible(
        "https://blog.example/reviews/earfun",
        "factual_blog",
    )
    assert content_score_eligible(
        "https://reviews.example/picks/best",
        "editorial",
    )
    assert not content_score_eligible(
        "https://shop.example/products/earfun",
        "commercial_product",
    )


def test_score_all_eligible_skips_commercial_scores_low_manip_parasitic():
    """Parasitic always scored even with low manipulability; commercial skipped."""
    planted = (
        "I got EarFun buds after my dad recommended them for my commute. "
        "I wear them every day at the gym and the wireless earbuds stay comfortable. "
        "Battery lasts through my podcasts without charging midday."
    )
    filler = "Pricing page for unrelated VPN plans and checkout FAQs."
    cands = [
        ReferrerExcerptCandidate(
            url="https://shop.example/pricing",
            role="commercial_product",
            entity="EarFun",
            manipulability=0.15,
            thread_surface=0.0,
            editability=0.15,
            excerpt=filler,
            segment_role="body",
        ),
        ReferrerExcerptCandidate(
            url="https://blog.example/reviews/earfun-air",
            role="factual_blog",
            entity="EarFun",
            manipulability=0.4,
            thread_surface=0.0,
            editability=0.4,
            excerpt=planted,
            segment_role="body",
        ),
        ReferrerExcerptCandidate(
            # Parasitic path but artificially low manipulability telemetry.
            url="https://forum.example/r/x/comments/abc/earfun/",
            role="ugc_thread",
            entity="EarFun",
            manipulability=0.05,
            thread_surface=0.05,
            editability=0.0,
            excerpt=planted,
            segment_role="comment",
        ),
        ReferrerExcerptCandidate(
            url="https://corp.example/about",
            role="commercial_product",
            entity="EarFun",
            manipulability=0.0,
            thread_surface=0.0,
            editability=0.0,
            excerpt=filler,
            segment_role="body",
        ),
    ]
    summary = score_top_referrers(cands, entity="EarFun")
    urls = {s.url for s in summary.scores if s.scored}
    assert "https://forum.example/r/x/comments/abc/earfun/" in urls
    assert "https://blog.example/reviews/earfun-air" in urls
    assert "https://shop.example/pricing" not in urls
    assert summary.scored == 2
    assert summary.high_risk_count == 2
    extras = referrer_content_tighten_extras(summary)
    assert "attribute_only" in extras


def test_eligible_cap_orders_parasitic_first():
    excerpt = "Neutral mention of EarFun in a product changelog without ranking."
    soft = [
        ReferrerExcerptCandidate(
            url=f"https://blog.example/articles/{i}",
            role="factual_blog",
            entity="EarFun",
            manipulability=0.9,
            editability=0.9,
            excerpt=excerpt,
        )
        for i in range(5)
    ]
    parasitic = [
        ReferrerExcerptCandidate(
            url=f"https://forum.example/r/x/comments/{i}/earfun/",
            role="ugc_thread",
            entity="EarFun",
            manipulability=0.1,
            thread_surface=0.1,
            excerpt=excerpt,
        )
        for i in range(5)
    ]
    selected, n_para, n_soft = select_eligible_referrers(
        soft + parasitic, max_score=6
    )
    assert len(selected) == 6
    assert n_para == 5
    assert n_soft == 1
    # First five selected should be parasitic despite lower manipulability.
    assert all(
        "forum.example" in c.url for c in selected[:5]
    )


def test_score_all_soft_editorial_up_to_cap():
    excerpt = "EarFun notes in documentation."
    cands = [
        ReferrerExcerptCandidate(
            url=f"https://reviews.example/picks/{i}",
            role="editorial",
            entity="EarFun",
            manipulability=0.5,
            editability=0.5,
            excerpt=excerpt,
        )
        for i in range(5)
    ]
    summary = score_top_referrers(cands, entity="EarFun")
    assert summary.scored == 5
    assert "soft_editorial=5" in summary.notes[0]


def test_entity_excerpt_prefers_comment_segment():
    cand = build_excerpt_candidate(
        "https://forum.example/r/x/comments/abc/thread/",
        role="ugc_thread",
        text="main ignored",
        segments=[
            PageSegment("main_0", "main_post", "General discussion about audio gear today.", 0),
            PageSegment(
                "comment_0",
                "comment",
                (
                    "I recently tried EarFun Air Pro 4 after my old buds died and they have been "
                    "surprisingly good for commuting and gym sessions every day this month."
                ),
                1,
            ),
        ],
        entity="EarFun",
        marker="earfun",
    )
    assert cand.segment_role == "comment"
    assert "EarFun" in cand.excerpt
    assert cand.manipulability >= 0.55
    assert cand.thread_surface >= 0.55
    assert cand.editability == 0.0


def test_score_top_detects_planted_and_tightens():
    planted = (
        "I got EarFun buds after my dad recommended them for my commute. "
        "I wear them every day at the gym and the wireless earbuds stay comfortable. "
        "Battery lasts through my podcasts without charging midday."
    )
    clean = (
        "EarFun published firmware notes documenting codec support and known issues. "
        "The changelog lists battery estimation fixes without ranking competitors."
    )
    cands = [
        ReferrerExcerptCandidate(
            url="https://forum.example/r/x/comments/1/a/",
            role="ugc_thread",
            entity="EarFun",
            manipulability=0.9,
            thread_surface=0.9,
            excerpt=planted,
            segment_role="comment",
        ),
        ReferrerExcerptCandidate(
            url="https://forum.example/r/x/comments/2/b/",
            role="ugc_thread",
            entity="EarFun",
            manipulability=0.85,
            thread_surface=0.85,
            excerpt=planted + " Also recommending friends buy the same.",
            segment_role="comment",
        ),
        ReferrerExcerptCandidate(
            url="https://docs.example/earfun/notes",
            role="factual_blog",
            entity="EarFun",
            manipulability=0.1,
            editability=0.1,
            excerpt=clean,
            segment_role="body",
        ),
    ]
    summary = score_top_referrers(cands, entity="EarFun")
    assert summary.scored >= 2
    assert summary.high_risk_count >= 2
    extras = referrer_content_tighten_extras(summary)
    assert "attribute_only" in extras
    assert "block_endorsement" in extras


def test_tighten_content_high_risk_without_mix_flag():
    """37%-style mix stays clean on %, but referrer L1 evidence tightens."""
    profile = ReferralProfile(
        status="sparse",
        discovery_status="success",
        confidence="medium",
        n_verified=19,
        mix={"ugc_thread": 7, "commercial_product": 12},
        geo_suspected=False,
        referrer_content_scored=3,
        referrer_content_high_risk=2,
        referrer_content_coordinated=False,
    )
    primary, actions = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="commercial_product",
    )
    assert primary in ("attribute_only", "block_endorsement")
    assert "attribute_only" in actions


def test_tighten_one_high_risk_soft_downrank():
    profile = ReferralProfile(
        status="sparse",
        discovery_status="success",
        confidence="medium",
        n_verified=12,
        mix={"ugc_thread": 3, "factual_blog": 9},
        geo_suspected=False,
        referrer_content_scored=2,
        referrer_content_high_risk=1,
    )
    primary, actions = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="commercial_product",
    )
    assert primary == "downrank"
    assert "downrank" in actions


def test_linkedin_shaped_path_is_manipulable():
    """Post-shaped paths elevate via editability (soft surface), not thread surface."""
    url = "https://www.example.com/posts/UGcde123_earfun-review"
    assert thread_surface_score(url) == 0.0
    assert editability_score(url) >= 0.55
    assert manipulability_score(url) >= 0.55
