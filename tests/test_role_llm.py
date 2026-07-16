"""Offline tests for Mode B LLM referrer-role fallback."""

from __future__ import annotations

import pytest

from anti_geo.models import FetchResult
from anti_geo.platform_role import is_parasitic_referrer
from anti_geo.role_llm import resolve_referrer_role


def _fetch(url: str, *, title: str = "", text: str = "page body about the brand") -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        ok=True,
        error=None,
        title=title,
        text=text,
        link_count=1,
        broken_link_ratio=0.0,
        redirect_count=0,
        response_time_ms=10,
        has_privacy_page=False,
        has_contact_page=False,
    )


def test_llm_upgrades_ambiguous_review_farm(monkeypatch):
    url = "https://jewelryreviewsonline.com/theo-grace-jewelry-review/"
    fetch = _fetch(url, title="Theo Grace Review", text="Full review of theo grace jewelry.")

    def fake_llm(messages, config=None):
        return {
            "role": "review_profile",
            "parasitic_surface": True,
            "reason": "third-party review farm",
        }

    monkeypatch.setattr("anti_geo.role_llm.chat_completion_json", fake_llm)
    monkeypatch.setattr("anti_geo.role_llm.is_azure_configured", lambda: True)

    resolved = resolve_referrer_role(url, fetch, use_llm=True)
    assert resolved.role_source == "llm"
    assert resolved.role == "review_profile"
    assert resolved.llm_parasitic is True
    assert is_parasitic_referrer(
        url=url, role=resolved.role, llm_parasitic=resolved.llm_parasitic
    )


def test_llm_marks_parasitic_without_role_change(monkeypatch):
    """parasitic_surface=true keeps soft role but still counts parasitic."""
    url = "https://www.scam-detector.com/validator/theograce-com-review/"
    fetch = _fetch(url, title="Scam check", text="Trust score for theograce.com")

    def fake_llm(messages, config=None):
        return {
            "role": "factual_blog",
            "parasitic_surface": True,
            "reason": "scam-score farm",
        }

    monkeypatch.setattr("anti_geo.role_llm.chat_completion_json", fake_llm)
    resolved = resolve_referrer_role(url, fetch, use_llm=True)
    assert resolved.role == "factual_blog"
    assert resolved.role_source == "llm"
    assert resolved.llm_parasitic is True
    assert is_parasitic_referrer(
        url=url, role=resolved.role, llm_parasitic=True
    )
    assert not is_parasitic_referrer(
        url=url, role=resolved.role, llm_parasitic=False
    )


def test_no_llm_when_heuristic_already_ugc(monkeypatch):
    url = "https://www.reddit.com/r/laptops/comments/abc123/thread/"
    fetch = _fetch(url, text="reddit thread")
    called = {"n": 0}

    def fake_llm(messages, config=None):
        called["n"] += 1
        return {"role": "factual_blog", "parasitic_surface": False, "reason": "nope"}

    monkeypatch.setattr("anti_geo.role_llm.chat_completion_json", fake_llm)
    resolved = resolve_referrer_role(url, fetch, use_llm=True)
    assert called["n"] == 0
    assert resolved.role_source == "heuristic"
    assert resolved.role == "ugc_thread"
    assert resolved.llm_parasitic is False


def test_no_llm_when_heuristic_review_profile(monkeypatch):
    url = "https://lamfindia.com/review/lemonn"
    fetch = _fetch(url, text="lemonn review")
    called = {"n": 0}

    def fake_llm(messages, config=None):
        called["n"] += 1
        return {"role": "factual_blog", "parasitic_surface": False}

    monkeypatch.setattr("anti_geo.role_llm.chat_completion_json", fake_llm)
    resolved = resolve_referrer_role(url, fetch, use_llm=True)
    assert called["n"] == 0
    assert resolved.role == "review_profile"
    assert resolved.role_source == "heuristic"


def test_fail_open_on_llm_exception(monkeypatch):
    url = "https://example.com/blog/some-article"
    fetch = _fetch(url, text="article about lemonn trading app")

    def boom(messages, config=None):
        raise RuntimeError("azure down")

    monkeypatch.setattr("anti_geo.role_llm.chat_completion_json", boom)
    resolved = resolve_referrer_role(url, fetch, use_llm=True)
    assert resolved.role_source == "heuristic"
    assert resolved.role == "factual_blog"
    assert resolved.llm_parasitic is False


def test_skip_llm_when_disabled(monkeypatch):
    url = "https://example.com/blog/some-article"
    fetch = _fetch(url)
    called = {"n": 0}

    def fake_llm(messages, config=None):
        called["n"] += 1
        return {"role": "review_profile", "parasitic_surface": True}

    monkeypatch.setattr("anti_geo.role_llm.chat_completion_json", fake_llm)
    resolved = resolve_referrer_role(url, fetch, use_llm=False)
    assert called["n"] == 0
    assert resolved.role_source == "heuristic"


def test_invalid_llm_role_keeps_heuristic(monkeypatch):
    url = "https://example.com/blog/some-article"
    fetch = _fetch(url)

    def fake_llm(messages, config=None):
        return {"role": "not_a_role", "parasitic_surface": True}

    monkeypatch.setattr("anti_geo.role_llm.chat_completion_json", fake_llm)
    resolved = resolve_referrer_role(url, fetch, use_llm=True)
    assert resolved.role_source == "heuristic"
    assert resolved.role == "factual_blog"


def test_youtube_heuristic_skips_llm(monkeypatch):
    """Path heuristic already marks YouTube watch as UGC — no LLM call."""
    url = "https://www.youtube.com/watch?v=wX7gdIeon7A"
    fetch = _fetch(url, title="Lemonn review", text="video description")
    called = {"n": 0}

    def fake_llm(messages, config=None):
        called["n"] += 1
        return {"role": "factual_blog", "parasitic_surface": False}

    monkeypatch.setattr("anti_geo.role_llm.chat_completion_json", fake_llm)
    resolved = resolve_referrer_role(url, fetch, use_llm=True)
    assert called["n"] == 0
    assert resolved.role == "ugc_thread"


def test_llm_parasitic_flag_on_is_parasitic_referrer():
    url = "https://example.com/odd-path"
    assert not is_parasitic_referrer(url=url, role="commercial_product")
    assert is_parasitic_referrer(
        url=url, role="commercial_product", llm_parasitic=True
    )
