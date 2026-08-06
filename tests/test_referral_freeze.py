"""Tests for frozen Mode B referral profiles (eval-loop mix freeze)."""

from __future__ import annotations

from anti_geo.investigation import (
    ReferralProfile,
    VerifiedReferrer,
    referral_profile_from_freeze_dict,
    referral_profile_from_label_pred,
    referral_profile_to_freeze_dict,
)


def test_referral_freeze_roundtrip_preserves_mix_and_flags():
    profile = ReferralProfile(
        status="sparse",
        discovery_status="success",
        confidence="medium",
        n_verified=2,
        mix={"ugc_thread": 1, "review_profile": 1},
        parasitic_geo_suspected=False,
        parasitic_geo_risk=0.22,
        parasitic_geo_elevated=True,
        parasitic_source="heuristic",
        referrers_verified=[
            VerifiedReferrer(
                url="https://reddit.com/r/x/1",
                role="ugc_thread",
                connection="brand_mention",
                connection_confidence="weak",
            ),
            VerifiedReferrer(
                url="https://trustpilot.com/review/x",
                role="review_profile",
                connection="llm_mention",
            ),
        ],
        notes=["orig"],
    )
    blob = referral_profile_to_freeze_dict(profile)
    restored = referral_profile_from_freeze_dict(blob)
    assert restored.n_verified == 2
    assert restored.parasitic_geo_elevated is True
    assert restored.parasitic_geo_risk == 0.22
    assert len(restored.referrers_verified) == 2
    assert restored.referrers_verified[0].url.endswith("/1")
    assert restored.mix["ugc_thread"] == 1


def test_legacy_pred_summary_builds_stub_freeze():
    pred = {
        "parasitic": "elevated",
        "parasitic_geo_elevated": True,
        "parasitic_geo_suspected": False,
        "parasitic_geo_risk": 0.4,
        "parasitic_source": "heuristic",
        "n_verified": 5,
        "referral_status": "sparse_suspicious",
    }
    profile = referral_profile_from_label_pred(pred)
    assert profile is not None
    assert profile.parasitic_geo_elevated is True
    assert profile.n_verified == 5
    assert profile.referrers_verified == []


def test_pred_without_mode_b_returns_none():
    assert referral_profile_from_label_pred({"retrieve_permission": "allow"}) is None
