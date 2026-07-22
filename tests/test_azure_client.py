import threading
import time
from types import SimpleNamespace

from anti_geo.azure_client import (
    AzureOpenAIConfig,
    azure_api_slot,
    extract_urls_from_response,
    load_azure_config,
    query_with_web_search,
    reset_azure_api_semaphore_for_tests,
    responses_json_with_optional_web_search,
)
from anti_geo.seed_generation import resolve_seed_queries


def test_load_azure_config_missing(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    assert load_azure_config() is None


def test_azure_api_slot_caps_concurrency(monkeypatch):
    monkeypatch.setenv("AZURE_API_MAX_CONCURRENCY", "2")
    reset_azure_api_semaphore_for_tests()
    active = 0
    peak = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal active, peak
        with azure_api_slot():
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak <= 2
    reset_azure_api_semaphore_for_tests()


def test_load_azure_config_from_env(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.5")
    cfg = load_azure_config()
    assert cfg is not None
    assert cfg.deployment == "gpt-5.5"
    assert cfg.responses_base_url.endswith("/openai/v1/")


def test_query_with_web_search_forces_tool_choice(monkeypatch):
    """Mode A must force Bing web_search (not auto / generic required)."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.5")
    reset_azure_api_semaphore_for_tests()

    captured: dict = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text="recipe",
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            sources=[
                                SimpleNamespace(
                                    type="url",
                                    url="https://example.com/chicken-parm",
                                )
                            ]
                        ),
                    ),
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                annotations=[
                                    SimpleNamespace(
                                        type="url_citation",
                                        url="https://example.com/chicken-parm",
                                    )
                                ]
                            )
                        ],
                    ),
                ],
            )

    class _FakeClient:
        responses = _FakeResponses()

    monkeypatch.setattr(
        "anti_geo.azure_client.get_azure_responses_client",
        lambda config=None: _FakeClient(),
    )
    text, cited, domains, pool = query_with_web_search("how do i cook chicken parm?")
    assert captured["tool_choice"] == {"type": "web_search"}
    assert captured["tools"] == [{"type": "web_search"}]
    assert "chicken-parm" in cited[0]
    assert text == "recipe"
    reset_azure_api_semaphore_for_tests()


def test_responses_json_optional_web_search_uses_auto_and_cap(monkeypatch):
    """Judge path: tool_choice=auto + soft max_tool_calls (not forced search)."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.5")
    monkeypatch.setenv("AZURE_JUDGE_MAX_TOOL_CALLS", "3")
    reset_azure_api_semaphore_for_tests()

    captured: dict = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text='{"same_brand":false,"reason":"unrelated"}',
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(sources=[]),
                    ),
                    SimpleNamespace(type="message", content=[]),
                ],
            )

    class _FakeClient:
        responses = _FakeResponses()

    monkeypatch.setattr(
        "anti_geo.azure_client.get_azure_responses_client",
        lambda config=None: _FakeClient(),
    )
    payload = responses_json_with_optional_web_search(
        [
            {"role": "system", "content": "Return JSON"},
            {"role": "user", "content": "same brand?"},
        ]
    )
    assert captured["tool_choice"] == "auto"
    assert captured["tools"] == [{"type": "web_search"}]
    assert captured["max_tool_calls"] == 3
    assert payload["same_brand"] is False
    assert payload["_web_search_calls"] == 1
    reset_azure_api_semaphore_for_tests()


def test_extract_urls_prefers_answer_citations_over_search_sources():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="web_search_call",
                action=SimpleNamespace(
                    sources=[
                        SimpleNamespace(url="https://noise.example/a"),
                        SimpleNamespace(url="https://noise.example/b"),
                        SimpleNamespace(url="https://noise.example/c"),
                    ]
                ),
            ),
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                url="https://www.example.com/cited",
                            )
                        ]
                    )
                ],
            ),
        ],
        output_text="see https://www.example.com/cited",
    )
    urls = extract_urls_from_response(response)
    assert urls == ["https://www.example.com/cited"]


def test_extract_urls_does_not_fall_back_to_search_sources():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="web_search_call",
                action=SimpleNamespace(
                    sources=[SimpleNamespace(url="https://fallback.example/x")]
                ),
            )
        ],
        output_text="",
    )
    assert extract_urls_from_response(response) == []


def test_resolve_seed_queries_template_fallback(monkeypatch):
    from anti_geo.investigation import PageMetadata, generate_seed_queries

    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    meta = PageMetadata(
        entity="Example Product",
        category="widgets",
        topic="widgets",
        price_hint="100",
        org="Example",
    )
    queries, source, confidence = resolve_seed_queries(
        "commercial_product",
        meta,
        url="https://example.com/product",
        mode="auto",
        limit=4,
    )
    assert source == "template"
    assert queries == generate_seed_queries("commercial_product", meta, limit=4)
    assert confidence == "high"


def test_resolve_seed_queries_llm(monkeypatch):
    from anti_geo.investigation import PageMetadata

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.5")

    def fake_chat(messages, **kwargs):
        return {
            "queries": [
                "WHO diabetes screening guidelines 2026",
                "latest CDC diabetes prevention recommendations",
            ]
        }

    monkeypatch.setattr("anti_geo.seed_generation.chat_completion_json", fake_chat)
    meta = PageMetadata(
        entity="Diabetes prevention overview",
        category="health",
        topic="diabetes prevention",
        price_hint="1000",
        org="CDC",
    )
    queries, source, confidence = resolve_seed_queries(
        "institutional",
        meta,
        url="https://www.cdc.gov/diabetes/prevention",
        mode="llm",
        limit=5,
    )
    assert source == "llm"
    assert "diabetes" in queries[0].lower()
    assert confidence == "high"
