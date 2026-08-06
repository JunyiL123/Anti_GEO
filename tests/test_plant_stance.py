"""Mode B plant-stance soft-weighting for hard parasitic share."""

from anti_geo.content_signals import (
    PLANT_STANCE_COMPLAINT,
    PLANT_STANCE_NEUTRAL,
    PLANT_STANCE_PROMOTIONAL,
    PLANT_STANCE_UNKNOWN,
    classify_plant_stance,
)
from anti_geo.investigation import (
    VerifiedReferrer,
    counts_toward_hard_parasitic_share,
    parasitic_count_from_verified,
    parasitic_share_from_verified,
    parasitic_surface_count_from_verified,
)
from anti_geo.referrer_content import score_excerpt


def test_classify_plant_stance_glaze_and_complaint():
    assert (
        classify_plant_stance(
            "I highly recommend this brand, absolutely love the bracelet."
        )
        == PLANT_STANCE_PROMOTIONAL
    )
    assert (
        classify_plant_stance(
            "Never received my order, no refund, this is a scam and terrible."
        )
        == PLANT_STANCE_COMPLAINT
    )
    # Complaint-shaped plant: glaze wins.
    assert (
        classify_plant_stance(
            "Shipping was rough and customer service was slow but I highly "
            "recommend TheoGrace — switched to them after ditching the other brand."
        )
        == PLANT_STANCE_PROMOTIONAL
    )
    assert (
        classify_plant_stance("here is how to export trading data from multiple apps")
        == PLANT_STANCE_NEUTRAL
    )
    assert classify_plant_stance("") == PLANT_STANCE_UNKNOWN


def test_classify_competitor_bash_and_affiliate():
    assert (
        classify_plant_stance(
            "Skip Zerodha, switch from Groww — better than both if you ask me."
        )
        == PLANT_STANCE_PROMOTIONAL
    )
    assert (
        classify_plant_stance(
            "Full review below. Affiliate disclosure: I may earn a commission."
        )
        == PLANT_STANCE_PROMOTIONAL
    )
    assert (
        classify_plant_stance(
            "story text",
            flags=["planted_mention"],
        )
        == PLANT_STANCE_PROMOTIONAL
    )


def test_hard_share_discounts_complaint_ugc_keeps_surface():
    complaint = VerifiedReferrer(
        url="https://www.reddit.com/r/x/comments/abc/shipping_nightmare/",
        role="ugc_thread",
        connection="brand_mention",
        content_scored=True,
        content_high_risk=False,
        content_plant_stance=PLANT_STANCE_COMPLAINT,
    )
    glaze = VerifiedReferrer(
        url="https://www.reddit.com/r/x/comments/def/fathers_day_gift/",
        role="ugc_thread",
        connection="brand_mention",
        content_scored=True,
        content_high_risk=False,
        content_plant_stance=PLANT_STANCE_PROMOTIONAL,
    )
    medium = VerifiedReferrer(
        url="https://medium.com/p/abc123parasite",
        role="expert_listicle",
        connection="url_link",
    )
    shop = VerifiedReferrer(
        url="https://shop.example/dp/1",
        role="commercial_product",
        connection="url_link",
    )
    refs = [complaint, glaze, medium, shop]

    assert parasitic_surface_count_from_verified(refs) == 3  # ugc×2 + medium
    assert parasitic_count_from_verified(refs) == 2  # glaze + medium
    assert parasitic_share_from_verified(refs) == 2 / 4
    assert not counts_toward_hard_parasitic_share(complaint)
    assert counts_toward_hard_parasitic_share(glaze)
    assert counts_toward_hard_parasitic_share(medium)


def test_unscored_ugc_discounted_from_hard_share():
    ref = VerifiedReferrer(
        url="https://www.reddit.com/r/x/comments/zzz/random/",
        role="ugc_thread",
        connection="brand_mention",
        content_scored=False,
        content_plant_stance=PLANT_STANCE_UNKNOWN,
    )
    assert parasitic_surface_count_from_verified([ref]) == 1
    assert parasitic_count_from_verified([ref]) == 0


def test_high_conf_and_coordination_override_complaint():
    complaint = VerifiedReferrer(
        url="https://www.reddit.com/r/x/comments/hr/planted_complaint/",
        role="ugc_thread",
        connection="brand_mention",
        content_scored=True,
        content_high_risk=True,
        content_flags=["planted_mention"],
        content_plant_stance=PLANT_STANCE_COMPLAINT,
    )
    assert counts_toward_hard_parasitic_share(complaint)

    pure = VerifiedReferrer(
        url="https://www.reddit.com/r/x/comments/farm/scam_post/",
        role="ugc_thread",
        connection="brand_mention",
        content_scored=True,
        content_plant_stance=PLANT_STANCE_COMPLAINT,
    )
    assert not counts_toward_hard_parasitic_share(pure)
    assert counts_toward_hard_parasitic_share(pure, coordinated=True)
    assert parasitic_count_from_verified([pure], coordinated=True) == 1


def test_review_profile_stance_gated_directory_not():
    trustpilot = VerifiedReferrer(
        url="https://www.trustpilot.com/review/example.com",
        role="review_profile",
        connection="brand_mention",
        content_scored=True,
        content_plant_stance=PLANT_STANCE_COMPLAINT,
    )
    feedspot = VerifiedReferrer(
        url="https://forums.feedspot.com/pc_gaming_forums/",
        role="expert_listicle",
        connection="url_link",
    )
    assert not counts_toward_hard_parasitic_share(trustpilot)
    assert counts_toward_hard_parasitic_share(feedspot)


def test_score_excerpt_sets_plant_stance():
    hit = score_excerpt(
        "https://reddit.com/r/x/comments/1/",
        (
            "my dad never wears jewelry. got him an engraved bracelet from theograce "
            "for father's day. he texted a photo of himself wearing it. i stared at "
            "it for like 5 minutes. genuinely love how personal it feels every day."
        ),
        entity="theograce",
        manipulability=0.8,
    )
    assert hit.scored
    assert hit.plant_stance == PLANT_STANCE_PROMOTIONAL or "planted_mention" in hit.content_flags

    complaint = score_excerpt(
        "https://reddit.com/r/x/comments/2/",
        (
            "Ordered three weeks ago and never received the package. Customer service "
            "ghosted me. No refund. Absolute scam, do not buy from this company."
        ),
        entity="theograce",
        manipulability=0.8,
    )
    assert complaint.scored
    assert complaint.plant_stance == PLANT_STANCE_COMPLAINT
    assert not complaint.high_risk
