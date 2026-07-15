from anti_geo.investigation import ReferralProfile, tighten_actions_with_referral
from anti_geo.models import PageSegment
from anti_geo.referrer_content import (
    ReferrerExcerptCandidate,
    adaptive_filler_k,
    build_excerpt_candidate,
    editability_score,
    manipulability_score,
    referrer_content_tighten_extras,
    score_top_referrers,
    select_referrer_shortlist,
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


def test_editability_priority_beats_zero_thread_in_shortlist():
    """Elevated blogs always enter tier-1; L1 outcomes tighten, not priority alone."""
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
    # max_filler=0 → only elevated tier; blog must be scored.
    summary = score_top_referrers(cands, entity="EarFun", max_filler=0)
    assert summary.scored == 1
    assert summary.scores[0].url == "https://blog.example/reviews/earfun-air"
    assert summary.scores[0].editability >= 0.4
    assert summary.high_risk_count == 1
    extras = referrer_content_tighten_extras(summary)
    assert extras == ["downrank"]


def test_two_tier_always_scores_elevated_plus_adaptive_filler():
    excerpt = "Neutral mention of EarFun in a product changelog without ranking."
    elevated = [
        ReferrerExcerptCandidate(
            url=f"https://blog.example/post/{i}",
            role="factual_blog",
            entity="EarFun",
            manipulability=0.4,
            editability=0.4,
            excerpt=excerpt,
        )
        for i in range(3)
    ]
    rest = [
        ReferrerExcerptCandidate(
            url=f"https://shop.example/p/{i}",
            role="commercial_product",
            entity="EarFun",
            manipulability=0.15,
            editability=0.15,
            excerpt=excerpt,
        )
        for i in range(12)
    ]
    selected, n_elev, n_fill = select_referrer_shortlist(elevated + rest)
    assert n_elev == 3
    # adaptive_filler_k(12) = min(8, ceil(12/4)=3) = 3
    assert n_fill == 3
    assert len(selected) == 6
    assert adaptive_filler_k(0) == 0
    assert adaptive_filler_k(1) == 1
    assert adaptive_filler_k(4) == 1
    assert adaptive_filler_k(5) == 2
    assert adaptive_filler_k(40) == 8


def test_two_tier_scores_all_elevated_up_to_cap():
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
    summary = score_top_referrers(cands, entity="EarFun", max_filler=0)
    assert summary.scored == 5
    assert "elevated=5" in summary.notes[0]


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
    summary = score_top_referrers(cands, entity="EarFun", k=8)
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
