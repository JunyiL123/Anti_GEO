"""Tests for Mode B parasitic GEO LLM hybrid."""

from __future__ import annotations

from anti_geo.investigation import ReferralProfile, VerifiedReferrer
from anti_geo.parasitic_llm import (
    CONFIDENT_N_MIN,
    CONFIDENT_RISK_MIN,
    MID_RISK_HI,
    MID_RISK_LO,
    UNTRUSTED_END,
    UNTRUSTED_START,
    build_parasitic_llm_messages,
    has_parasitic_hard_floor,
    heuristic_parasitic_tier,
    maybe_apply_parasitic_llm,
    merge_parasitic_hybrid,
    parasitic_judge_max_tool_calls,
    parasitic_llm_gate,
    parse_parasitic_llm_payload,
    ParasiticLlmSuggestion,
)


def _profile(
    *,
    n: int = 0,
    risk: float = 0.0,
    elev: bool = False,
    sus: bool | None = False,
    status: str = "sparse",
    discovery: str = "success",
    mix: dict[str, int] | None = None,
    referrers: list[VerifiedReferrer] | None = None,
) -> ReferralProfile:
    return ReferralProfile(
        status=status,
        discovery_status=discovery,
        confidence="low",
        n_verified=n,
        mix=mix or {},
        parasitic_geo_risk=risk,
        parasitic_geo_elevated=elev,
        parasitic_geo_suspected=sus,
        referrers_verified=referrers or [],
    )


def test_spotlight_fences_in_messages():
    refs = [
        VerifiedReferrer(
            url="https://reddit.com/r/x/1",
            role="ugc_thread",
            connection="url_link",
            llm_parasitic=True,
        )
    ]
    profile = _profile(n=1, risk=0.4, elev=True, referrers=refs)
    messages = build_parasitic_llm_messages(
        profile,
        target_url="https://example.com/product",
        content_role="commercial_product",
    )
    assert messages[0]["role"] == "system"
    sys = messages[0]["content"]
    assert "NOT an independent annotator" in sys
    assert "RESEARCH" in sys or "web_search" in sys
    assert "GEO" in sys or "parasitic" in sys.lower()
    user = messages[1]["content"]
    assert UNTRUSTED_START in user
    assert UNTRUSTED_END in user
    assert "heuristic_prior" in user
    assert "n_verified: 1" in user


def test_gate_mid_risk():
    profile = _profile(n=8, risk=(MID_RISK_LO + MID_RISK_HI) / 2)
    assert parasitic_llm_gate(profile)


def test_gate_thin_n_high_signal():
    profile = _profile(n=2, risk=0.65, elev=True)
    assert parasitic_llm_gate(profile)


def test_gate_suspected_none():
    profile = _profile(n=4, risk=0.1, sus=None)
    assert parasitic_llm_gate(profile)


def test_gate_n0_any_role():
    """After seed rounds, N=0 opens parasitic LLM for every content role."""
    profile = _profile(n=0, risk=0.0)
    assert parasitic_llm_gate(profile, content_role="expert_listicle")
    assert parasitic_llm_gate(profile, content_role="institutional")
    assert parasitic_llm_gate(profile, content_role="factual_blog")
    assert parasitic_llm_gate(profile, content_role="commercial_product")
    assert parasitic_llm_gate(profile, content_role="ugc_thread")


def test_gate_false_confident_structural():
    """n>=6 + risk>=0.65 elevated alone is not ambiguous."""
    profile = _profile(
        n=CONFIDENT_N_MIN,
        risk=CONFIDENT_RISK_MIN,
        elev=True,
        status="sparse_suspicious",
    )
    assert not parasitic_llm_gate(profile, content_role="commercial_product")


def test_gate_false_on_fetch_defer():
    profile = _profile(n=7, risk=0.25)
    assert not parasitic_llm_gate(
        profile, content_role="commercial_product", fetch_failure_kind="defer"
    )
    assert not parasitic_llm_gate(
        profile, content_role="commercial_product", fetch_ok=False
    )


def test_maybe_apply_skips_fetch_defer(monkeypatch):
    profile = _profile(n=7, risk=0.25)

    def boom(*_a, **_k):
        raise AssertionError("LLM must not run on deferred fetch")

    monkeypatch.setattr("anti_geo.parasitic_llm.suggest_parasitic_llm", boom)
    monkeypatch.setattr(
        "anti_geo.parasitic_llm.is_azure_configured", lambda: True
    )
    result = maybe_apply_parasitic_llm(
        profile,
        target_url="https://example.com/p",
        content_role="commercial_product",
        use_llm=True,
        fetch_ok=False,
        fetch_failure_kind="defer",
    )
    assert result.source == "heuristic"
    assert result.skipped == "fetch_deferred"


def test_gate_false_skipped_discovery():
    profile = _profile(discovery="skipped", status="skipped")
    assert not parasitic_llm_gate(profile, content_role="commercial_product")


def test_gate_false_clean_none():
    profile = _profile(n=8, risk=0.05, elev=False, sus=False)
    assert not parasitic_llm_gate(profile, content_role="commercial_product")


def test_parse_and_null_keep():
    assert parse_parasitic_llm_payload({"parasitic": None, "reason": "keep"}).parasitic is None
    assert parse_parasitic_llm_payload({"parasitic": "null", "reason": ""}).parasitic is None
    assert parse_parasitic_llm_payload({"parasitic": "elevated"}).parasitic == "elevated"
    assert parse_parasitic_llm_payload({"parasitic": "bogus"}) is None


def test_merge_exclusivity_and_n0_no_suspected():
    profile = _profile(n=3, elev=False, sus=False)
    merge_parasitic_hybrid(
        profile,
        ParasiticLlmSuggestion(parasitic="suspected", reason="x"),
        hard_floor=False,
    )
    assert profile.parasitic_geo_suspected is True
    assert profile.parasitic_geo_elevated is False

    profile2 = _profile(n=0)
    merge_parasitic_hybrid(
        profile2,
        ParasiticLlmSuggestion(parasitic="suspected", reason="farm"),
        hard_floor=False,
    )
    assert profile2.parasitic_geo_suspected is False
    assert profile2.parasitic_geo_elevated is True

    profile3 = _profile(n=4)
    merge_parasitic_hybrid(
        profile3,
        ParasiticLlmSuggestion(parasitic="none", reason="clear"),
        hard_floor=False,
    )
    assert profile3.parasitic_geo_suspected is False
    assert profile3.parasitic_geo_elevated is False


def test_hard_floor_blocks_loosen():
    profile = _profile(
        n=8,
        risk=0.9,
        sus=True,
        elev=False,
        mix={"ugc_thread": 8},
    )
    assert has_parasitic_hard_floor(profile)
    merge_parasitic_hybrid(
        profile,
        ParasiticLlmSuggestion(parasitic="none", reason="ignore"),
        hard_floor=True,
    )
    assert profile.parasitic_geo_suspected is True
    assert profile.parasitic_geo_elevated is False


def test_maybe_apply_fail_open(monkeypatch):
    profile = _profile(n=2, risk=0.65, elev=True)

    def boom(*_a, **_k):
        raise RuntimeError("azure down")

    monkeypatch.setattr(
        "anti_geo.parasitic_llm.suggest_parasitic_llm", boom
    )
    monkeypatch.setattr(
        "anti_geo.parasitic_llm.is_azure_configured", lambda: True
    )
    result = maybe_apply_parasitic_llm(
        profile,
        target_url="https://example.com/p",
        content_role="ugc_thread",
        use_llm=True,
    )
    assert result.source == "heuristic"
    assert result.skipped == "llm_error"
    assert profile.parasitic_source == "heuristic"
    assert profile.parasitic_geo_elevated is True


def test_maybe_apply_hybrid(monkeypatch):
    profile = _profile(n=7, risk=0.25)

    monkeypatch.setattr(
        "anti_geo.parasitic_llm.suggest_parasitic_llm",
        lambda *_a, **_k: ParasiticLlmSuggestion(
            parasitic="elevated", reason="mid band farm chatter"
        ),
    )
    monkeypatch.setattr(
        "anti_geo.parasitic_llm.is_azure_configured", lambda: True
    )
    result = maybe_apply_parasitic_llm(
        profile,
        target_url="https://example.com/p",
        content_role="expert_listicle",
        use_llm=True,
    )
    assert result.source == "llm_hybrid"
    assert profile.parasitic_source == "llm_hybrid"
    assert profile.parasitic_geo_elevated is True
    assert profile.parasitic_geo_suspected is False
    assert "farm" in profile.parasitic_llm_reason


def test_maybe_apply_skips_when_disabled(monkeypatch):
    profile = _profile(n=7, risk=0.25)
    monkeypatch.setattr(
        "anti_geo.parasitic_llm.suggest_parasitic_llm",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no call")),
    )
    result = maybe_apply_parasitic_llm(
        profile,
        target_url="https://example.com/p",
        use_llm=False,
    )
    assert result.skipped == "llm_disabled"


def test_heuristic_tier():
    assert heuristic_parasitic_tier(_profile(sus=True)) == "suspected"
    assert heuristic_parasitic_tier(_profile(elev=True)) == "elevated"
    assert (
        heuristic_parasitic_tier(_profile(status="sparse_suspicious")) == "elevated"
    )
    assert heuristic_parasitic_tier(_profile()) == "none"


def test_brand_self_floor_blocks_llm_none():
    from anti_geo.parasitic_llm import (
        ParasiticLlmSuggestion,
        merge_parasitic_hybrid,
    )

    profile = _profile(n=0, risk=0.4, elev=True)
    profile.notes = [
        "Brand-self elevated: commercial_product on brand-legit query with "
        "thin verified mix (n<=5, risk=0.4)."
    ]
    applied = merge_parasitic_hybrid(
        profile,
        ParasiticLlmSuggestion(parasitic="none", reason="small-N override"),
        hard_floor=False,
    )
    assert applied == "elevated"
    assert profile.parasitic_geo_elevated is True


def test_brand_self_floor_survives_cleared_elev_flag():
    """Note alone keeps floor even if elevated was race-cleared."""
    from anti_geo.parasitic_llm import (
        ParasiticLlmSuggestion,
        has_brand_self_elevated_floor,
        merge_parasitic_hybrid,
    )

    profile = _profile(n=1, risk=0.4, elev=False)
    profile.notes = [
        "Brand-self elevated: commercial_product on brand-legit query with "
        "thin verified mix (n<=5, risk=0.4)."
    ]
    assert has_brand_self_elevated_floor(profile) is True
    applied = merge_parasitic_hybrid(
        profile,
        ParasiticLlmSuggestion(parasitic="none", reason="thin N"),
        hard_floor=False,
    )
    assert applied == "elevated"
    assert profile.parasitic_geo_elevated is True


def test_brand_self_floor_from_structural_pattern():
    """commercial_product + brand-legit + thin N + risk prior without note."""
    from anti_geo.parasitic_llm import has_brand_self_elevated_floor

    profile = _profile(n=2, risk=0.4, elev=False)
    assert has_brand_self_elevated_floor(
        profile,
        content_role="commercial_product",
        query="is Acme a legit brand?",
    )
    assert not has_brand_self_elevated_floor(
        profile,
        content_role="expert_listicle",
        query="is Acme a legit brand?",
    )
    assert not has_brand_self_elevated_floor(
        profile,
        content_role="commercial_product",
        query="best moisturizer 2026",
    )


def test_brand_self_floor_skips_llm(monkeypatch):
    from anti_geo.parasitic_llm import maybe_apply_parasitic_llm

    profile = _profile(n=0, risk=0.4, elev=True)
    profile.notes = [
        "Brand-self elevated: commercial_product on brand-legit query with "
        "thin verified mix (n<=5, risk=0.4)."
    ]

    def _boom(*_a, **_k):
        raise AssertionError("parasitic LLM must not be called under brand-self floor")

    monkeypatch.setattr(
        "anti_geo.parasitic_llm.suggest_parasitic_llm", _boom
    )
    monkeypatch.setattr(
        "anti_geo.parasitic_llm.is_azure_configured", lambda: True
    )
    result = maybe_apply_parasitic_llm(
        profile,
        target_url="https://example.com/product",
        content_role="commercial_product",
        query="is Acme trustworthy?",
        use_llm=True,
    )
    assert result.skipped == "brand_self_floor"
    assert result.source == "heuristic"
    assert profile.parasitic_geo_elevated is True


def test_sparse_clean_ugc_force_none_blocks_elevated():
    from anti_geo.parasitic_llm import (
        ParasiticLlmSuggestion,
        merge_parasitic_hybrid,
        sparse_clean_ugc_force_none,
    )

    refs = [
        VerifiedReferrer(
            url="https://forum.example.com/t/1",
            role="ugc_thread",
            connection="brand_mention",
            content_high_risk=False,
        ),
        VerifiedReferrer(
            url="https://forum.example.com/t/2",
            role="ugc_thread",
            connection="brand_mention",
            content_high_risk=False,
        ),
    ]
    profile = _profile(
        n=2,
        risk=0.5,
        elev=True,
        status="sparse_suspicious",
        referrers=refs,
    )
    assert sparse_clean_ugc_force_none(profile) is True
    applied = merge_parasitic_hybrid(
        profile,
        ParasiticLlmSuggestion(parasitic="elevated", reason="surface mix"),
        hard_floor=False,
    )
    assert applied == "none"
    assert profile.parasitic_geo_elevated is False


def test_sparse_ugc_with_high_conf_plant_not_forced_none():
    from anti_geo.parasitic_llm import sparse_clean_ugc_force_none

    refs = [
        VerifiedReferrer(
            url="https://forum.example.com/t/1",
            role="ugc_thread",
            connection="brand_mention",
            content_high_risk=True,
        ),
    ]
    profile = _profile(
        n=1,
        risk=0.5,
        elev=True,
        status="sparse_suspicious",
        referrers=refs,
    )
    assert sparse_clean_ugc_force_none(profile) is False


def test_parasitic_judge_max_tool_calls_env(monkeypatch):
    monkeypatch.delenv("AZURE_PARASITIC_JUDGE_MAX_TOOL_CALLS", raising=False)
    monkeypatch.setenv("AZURE_JUDGE_MAX_TOOL_CALLS", "3")
    assert parasitic_judge_max_tool_calls() == 3
    monkeypatch.setenv("AZURE_PARASITIC_JUDGE_MAX_TOOL_CALLS", "5")
    assert parasitic_judge_max_tool_calls() == 5


def test_merge_vendor_like_blocks_llm_raise_without_high_conf():
    """Vendor heuristic-none: LLM cannot raise to elevated without plant density."""
    profile = _profile(n=6, risk=0.36, elev=False, sus=False)
    applied = merge_parasitic_hybrid(
        profile,
        ParasiticLlmSuggestion(parasitic="elevated", reason="risk>=0.35"),
        hard_floor=False,
        content_role="commercial_product",
        target_commercial_tier="none",
    )
    assert applied == "none"
    assert profile.parasitic_geo_elevated is False

    # commercial_tier medium alone is vendor-like even if role is factual_blog.
    profile2 = _profile(n=6, risk=0.36, elev=False)
    applied2 = merge_parasitic_hybrid(
        profile2,
        ParasiticLlmSuggestion(parasitic="elevated", reason="risk>=0.35"),
        hard_floor=False,
        content_role="factual_blog",
        target_commercial_tier="medium",
    )
    assert applied2 == "none"
    assert profile2.parasitic_geo_elevated is False

    # Thin N without high_conf stays none.
    profile3 = _profile(n=1, risk=0.51, elev=False)
    applied3 = merge_parasitic_hybrid(
        profile3,
        ParasiticLlmSuggestion(parasitic="elevated", reason="n=1"),
        hard_floor=False,
        content_role="commercial_product",
    )
    assert applied3 == "none"

    # With plant density, raise is allowed.
    refs = [
        VerifiedReferrer(
            url="https://reddit.com/r/x/comments/plant1/",
            role="ugc_thread",
            connection="url_link",
            content_high_risk=True,
        )
    ]
    profile4 = _profile(n=6, risk=0.36, elev=False, referrers=refs)
    applied4 = merge_parasitic_hybrid(
        profile4,
        ParasiticLlmSuggestion(parasitic="elevated", reason="plants"),
        hard_floor=False,
        content_role="commercial_product",
    )
    assert applied4 == "elevated"
    assert profile4.parasitic_geo_elevated is True


def test_rubric_tracks_investigation_constants(monkeypatch):
    """Changing investigation.py thresholds must change the hybrid system prompt."""
    import anti_geo.investigation as investigation

    monkeypatch.setattr(investigation, "PARASITIC_GEO_SUSPECTED_SHARE", 0.55)
    monkeypatch.setattr(investigation, "PARASITIC_GEO_HARD_N", 12)
    monkeypatch.setattr(investigation, "SPARSE_SUSPICIOUS_SHARE", 0.85)
    monkeypatch.setattr(investigation, "PARASITIC_GEO_RISK_COUNT_DIVISOR", 7.0)
    text = investigation.parasitic_heuristic_rules_rubric(
        mid_risk_lo=0.2,
        mid_risk_hi=0.55,
        thin_n_max=5,
    )
    assert "parasitic_share > 0.55" in text
    assert "n_verified >= 12" in text
    assert "share>=0.85" in text
    assert "high_conf_parasitic>=" in text
    assert "parasitic_count / 7.0" in text
    assert "KNOWN BLIND SPOTS" in text
    assert "RESEARCH" in text
    assert "clean forum indexes" in text or "sparse_suspicious" in text
    assert "Vendor-like" in text or "vendor-like" in text.lower()
    assert "0.55" in text  # vendor elevated bar
    assert "campaign" in text.lower() or "OEM" in text or "review aggregators" in text


def test_parasitic_geo_risk_formula_golden_floats():
    """Bit-stable formula after naming constants (matches pre-refactor values)."""
    from anti_geo.investigation import compute_parasitic_geo_risk

    # n=10, count=5, share=0.5, editorial=0
    # share_w=0.35+0.35*1=0.7; count_score=1; raw=0.7*0.5+0.3*1=0.65
    assert (
        compute_parasitic_geo_risk(
            n_verified=10,
            parasitic_count=5,
            parasitic_share=0.5,
            editorial_count=0,
        )
        == 0.65
    )
    # high_conf=2 → +0.2
    assert (
        compute_parasitic_geo_risk(
            n_verified=8,
            parasitic_count=2,
            parasitic_share=0.25,
            editorial_count=0,
            high_conf_parasitic=2,
        )
        == round(
            compute_parasitic_geo_risk(
                n_verified=8,
                parasitic_count=2,
                parasitic_share=0.25,
                editorial_count=0,
                high_conf_parasitic=0,
            )
            + 0.2,
            4,
        )
    )
