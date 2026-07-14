from anti_geo.investigation import ReferralProfile, tighten_actions_with_referral
from anti_geo.models import PageSegment
from anti_geo.referrer_content import (
    ReferrerExcerptCandidate,
    build_excerpt_candidate,
    manipulability_score,
    referrer_content_tighten_extras,
    score_top_referrers,
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
            excerpt=planted,
            segment_role="comment",
        ),
        ReferrerExcerptCandidate(
            url="https://forum.example/r/x/comments/2/b/",
            role="ugc_thread",
            entity="EarFun",
            manipulability=0.85,
            excerpt=planted + " Also recommending friends buy the same.",
            segment_role="comment",
        ),
        ReferrerExcerptCandidate(
            url="https://docs.example/earfun/notes",
            role="factual_blog",
            entity="EarFun",
            manipulability=0.1,
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
    score = manipulability_score("https://www.example.com/posts/UGcde123_earfun-review")
    assert score >= 0.55
