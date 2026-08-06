from anti_geo.query_intent import (
    classify_query_intent_heuristic,
    resolve_query_intent,
)


def test_chicken_parm_is_informational():
    hit = resolve_query_intent("how do i cook chicken parm?", "auto", allow_llm=False)
    assert hit.intent == "informational"
    assert hit.source == "heuristic"


def test_best_budget_laptops_is_commercial():
    hit = resolve_query_intent("best budget laptops", "auto", allow_llm=False)
    assert hit.intent == "commercial"
    assert hit.source == "heuristic"


def test_best_way_howto_stays_informational():
    hit = resolve_query_intent(
        "best way to cook chicken parm", "auto", allow_llm=False
    )
    assert hit.intent == "informational"


def test_what_is_best_product_is_commercial():
    hit = resolve_query_intent("what is the best laptop", "auto", allow_llm=False)
    assert hit.intent == "commercial"


def test_high_stakes_health():
    hit = resolve_query_intent(
        "how to treat chronic fatigue symptoms", "auto", allow_llm=False
    )
    assert hit.intent == "informational_high_stakes"


def test_navigational_login_and_hostname():
    assert resolve_query_intent("taskflow pro login", "auto", allow_llm=False).intent == (
        "navigational"
    )
    assert resolve_query_intent("nih.gov", "auto", allow_llm=False).intent == (
        "navigational"
    )


def test_ambiguous_defaults_without_llm(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    hit = resolve_query_intent("chicken parm", "auto", allow_llm=True)
    assert hit.intent == "informational"
    assert hit.source == "default"
    assert hit.matched_rule == "ambiguous"


def test_llm_fallback_for_ambiguous(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-test")

    def fake_llm(query: str) -> str:
        assert query == "personalized jewellery gifts"
        return "commercial"

    monkeypatch.setattr(
        "anti_geo.query_intent.classify_query_intent_llm", fake_llm
    )
    monkeypatch.setattr("anti_geo.query_intent.is_azure_configured", lambda: True)
    hit = resolve_query_intent("personalized jewellery gifts", "auto")
    assert hit.intent == "commercial"
    assert hit.source == "llm"


def test_manual_intent_passthrough():
    hit = resolve_query_intent("how do i cook chicken parm?", "commercial")
    assert hit.intent == "commercial"
    assert hit.source == "manual"


def test_heuristic_none_when_ambiguous():
    assert classify_query_intent_heuristic("chicken parm") is None
