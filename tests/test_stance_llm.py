"""Offline tests for Mode B plant-stance LLM ambiguity backup."""

from __future__ import annotations

from anti_geo.content_signals import (
    PLANT_STANCE_COMPLAINT,
    PLANT_STANCE_NEUTRAL,
    PLANT_STANCE_PROMOTIONAL,
    PLANT_STANCE_UNKNOWN,
)
from anti_geo.investigation import VerifiedReferrer
from anti_geo.referrer_content import ReferrerContentScore
from anti_geo.stance_llm import (
    maybe_resolve_plant_stances,
    resolve_plant_stance_for_referrer,
    stance_llm_gate,
)


def test_stance_llm_gate_only_ambiguous_ugc():
    url = "https://www.reddit.com/r/x/comments/abc/thread/"
    assert stance_llm_gate(
        url=url,
        role="ugc_thread",
        heuristic_stance=PLANT_STANCE_UNKNOWN,
        excerpt="some body text about the brand",
    )
    assert stance_llm_gate(
        url=url,
        role="ugc_thread",
        heuristic_stance=PLANT_STANCE_COMPLAINT,
        excerpt="never received order scam",
    )
    assert not stance_llm_gate(
        url=url,
        role="ugc_thread",
        heuristic_stance=PLANT_STANCE_PROMOTIONAL,
        excerpt="highly recommend",
    )
    assert not stance_llm_gate(
        url=url,
        role="ugc_thread",
        heuristic_stance=PLANT_STANCE_UNKNOWN,
        content_high_risk=True,
        excerpt="planted already",
    )
    assert not stance_llm_gate(
        url="https://forums.feedspot.com/pc_gaming_forums/",
        role="expert_listicle",
        heuristic_stance=PLANT_STANCE_UNKNOWN,
        excerpt="directory",
    )
    assert not stance_llm_gate(
        url=url,
        role="ugc_thread",
        heuristic_stance=PLANT_STANCE_NEUTRAL,
        excerpt="",
    )


def test_resolve_upgrades_complaint_shaped_plant(monkeypatch):
    url = "https://www.reddit.com/r/x/comments/plant/thread/"
    excerpt = (
        "shipping was rough and customer service slow but honestly I highly "
        "recommend switching — check them out."
    )

    def fake_llm(messages, config=None):
        return {
            "stance": "promotional",
            "reason": "complaint-shaped glaze + CTA",
        }

    monkeypatch.setattr("anti_geo.stance_llm.chat_completion_json", fake_llm)
    monkeypatch.setattr("anti_geo.stance_llm.is_azure_configured", lambda: True)

    stance, source, reason = resolve_plant_stance_for_referrer(
        url=url,
        role="ugc_thread",
        excerpt=excerpt,
        heuristic_stance=PLANT_STANCE_COMPLAINT,
        entity="theograce",
        use_llm=True,
    )
    assert stance == PLANT_STANCE_PROMOTIONAL
    assert source == "llm"
    assert "glaze" in reason or reason


def test_resolve_fail_open_keeps_heuristic(monkeypatch):
    url = "https://www.reddit.com/r/x/comments/fail/thread/"

    def boom(messages, config=None):
        raise RuntimeError("azure down")

    monkeypatch.setattr("anti_geo.stance_llm.chat_completion_json", boom)
    monkeypatch.setattr("anti_geo.stance_llm.is_azure_configured", lambda: True)

    stance, source, _ = resolve_plant_stance_for_referrer(
        url=url,
        role="ugc_thread",
        excerpt="never received refund scam terrible",
        heuristic_stance=PLANT_STANCE_COMPLAINT,
        use_llm=True,
    )
    assert stance == PLANT_STANCE_COMPLAINT
    assert source == "heuristic"


def test_resolve_skips_when_llm_disabled(monkeypatch):
    monkeypatch.setattr("anti_geo.stance_llm.is_azure_configured", lambda: True)
    called = {"n": 0}

    def fake_llm(messages, config=None):
        called["n"] += 1
        return {"stance": "promotional", "reason": "should not run"}

    monkeypatch.setattr("anti_geo.stance_llm.chat_completion_json", fake_llm)
    stance, source, _ = resolve_plant_stance_for_referrer(
        url="https://www.reddit.com/r/x/comments/off/thread/",
        role="ugc_thread",
        excerpt="ambiguous neutral mention of brand",
        heuristic_stance=PLANT_STANCE_NEUTRAL,
        use_llm=False,
    )
    assert called["n"] == 0
    assert stance == PLANT_STANCE_NEUTRAL
    assert source == "heuristic"


def test_maybe_resolve_caps_and_skips_promotional(monkeypatch):
    monkeypatch.setattr("anti_geo.stance_llm.is_azure_configured", lambda: True)
    calls: list[str] = []

    def fake_llm(messages, config=None):
        user = messages[-1]["content"]
        # url line is first
        url_line = user.split("\n", 1)[0]
        calls.append(url_line)
        return {"stance": "promotional", "reason": "upgrade"}

    monkeypatch.setattr("anti_geo.stance_llm.chat_completion_json", fake_llm)

    refs = [
        VerifiedReferrer(
            url=f"https://www.reddit.com/r/x/comments/{i}/",
            role="ugc_thread",
            connection="brand_mention",
            content_plant_stance=PLANT_STANCE_UNKNOWN,
            content_manipulability=float(i),
        )
        for i in range(6)
    ]
    # Already promotional — must not call LLM.
    refs[0].content_plant_stance = PLANT_STANCE_PROMOTIONAL
    scores = {
        r.url.rstrip("/").lower(): ReferrerContentScore(
            url=r.url,
            manipulability=r.content_manipulability,
            excerpt=f"excerpt body for {r.url} with enough text",
            scored=True,
            plant_stance=r.content_plant_stance,
        )
        for r in refs
    }
    upgraded = maybe_resolve_plant_stances(
        refs, scores, entity="brand", use_llm=True, max_calls=3
    )
    assert upgraded == 3
    assert len(calls) == 3
    # Highest manipulability among ambiguous first after unknown priority.
    assert refs[0].content_plant_stance == PLANT_STANCE_PROMOTIONAL
    assert refs[0].content_plant_stance_source == "heuristic"
    assert sum(1 for r in refs if r.content_plant_stance_source == "llm") == 3
