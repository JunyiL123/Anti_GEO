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


def test_gate_n0_commercial():
    profile = _profile(n=0, risk=0.0)
    assert parasitic_llm_gate(profile, content_role="expert_listicle")
    assert not parasitic_llm_gate(profile, content_role="institutional")
    assert not parasitic_llm_gate(profile, content_role="factual_blog")


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
        content_role="commercial_product",
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


def test_parasitic_judge_max_tool_calls_env(monkeypatch):
    monkeypatch.delenv("AZURE_PARASITIC_JUDGE_MAX_TOOL_CALLS", raising=False)
    monkeypatch.setenv("AZURE_JUDGE_MAX_TOOL_CALLS", "3")
    assert parasitic_judge_max_tool_calls() == 3
    monkeypatch.setenv("AZURE_PARASITIC_JUDGE_MAX_TOOL_CALLS", "5")
    assert parasitic_judge_max_tool_calls() == 5
