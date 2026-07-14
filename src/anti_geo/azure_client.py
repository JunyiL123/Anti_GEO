from __future__ import annotations

import json
import os
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s\])>\"']+")

# Cap concurrent Azure calls so Mode A can raise site_workers without
# bursting RPM (web_search + seed chat share this gate).
_DEFAULT_AZURE_API_MAX_CONCURRENCY = 8
_azure_api_sem: threading.Semaphore | None = None
_azure_api_sem_n: int | None = None
_azure_api_sem_lock = threading.Lock()


def azure_api_max_concurrency() -> int:
    raw = os.environ.get("AZURE_API_MAX_CONCURRENCY", "").strip()
    if not raw:
        return _DEFAULT_AZURE_API_MAX_CONCURRENCY
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_AZURE_API_MAX_CONCURRENCY


def _get_azure_api_semaphore() -> threading.Semaphore:
    global _azure_api_sem, _azure_api_sem_n
    n = azure_api_max_concurrency()
    with _azure_api_sem_lock:
        if _azure_api_sem is None or _azure_api_sem_n != n:
            _azure_api_sem = threading.Semaphore(n)
            _azure_api_sem_n = n
        return _azure_api_sem


@contextmanager
def azure_api_slot() -> Iterator[None]:
    """Acquire one global Azure API concurrency slot."""
    sem = _get_azure_api_semaphore()
    sem.acquire()
    try:
        yield
    finally:
        sem.release()


def reset_azure_api_semaphore_for_tests() -> None:
    """Drop the cached semaphore (tests only)."""
    global _azure_api_sem, _azure_api_sem_n
    with _azure_api_sem_lock:
        _azure_api_sem = None
        _azure_api_sem_n = None


@dataclass(frozen=True)
class AzureOpenAIConfig:
    endpoint: str
    api_key: str
    deployment: str
    api_version: str = "2024-12-01-preview"

    @property
    def responses_base_url(self) -> str:
        return f"{self.endpoint.rstrip('/')}/openai/v1/"


def load_azure_config() -> AzureOpenAIConfig | None:
    """Load Azure OpenAI settings from environment (all three required)."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    deployment = (
        os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
        or os.environ.get("AZURE_OPENAI_MODEL_NAME", "").strip()
    )
    if not endpoint or not api_key or not deployment:
        return None
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview").strip()
    return AzureOpenAIConfig(
        endpoint=endpoint,
        api_key=api_key,
        deployment=deployment,
        api_version=api_version,
    )


def is_azure_configured() -> bool:
    return load_azure_config() is not None


def _require_openai():
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError as exc:
        raise ImportError(
            "Azure features require the openai package. Install with: pip install 'openai>=1.40'"
        ) from exc
    return AzureOpenAI, OpenAI


def get_azure_chat_client(config: AzureOpenAIConfig | None = None):
    AzureOpenAI, _ = _require_openai()
    cfg = config or load_azure_config()
    if cfg is None:
        raise ValueError(
            "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, "
            "AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT."
        )
    return AzureOpenAI(
        api_version=cfg.api_version,
        azure_endpoint=cfg.endpoint,
        api_key=cfg.api_key,
    )


def get_azure_responses_client(config: AzureOpenAIConfig | None = None):
    _, OpenAI = _require_openai()
    cfg = config or load_azure_config()
    if cfg is None:
        raise ValueError(
            "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, "
            "AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT."
        )
    return OpenAI(api_key=cfg.api_key, base_url=cfg.responses_base_url)


def chat_completion_json(
    messages: list[dict[str, str]],
    *,
    config: AzureOpenAIConfig | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    cfg = config or load_azure_config()
    if cfg is None:
        raise ValueError("Azure OpenAI is not configured.")
    client = get_azure_chat_client(cfg)
    base_kwargs: dict[str, Any] = {"model": cfg.deployment, "messages": messages}
    if temperature is not None:
        base_kwargs["temperature"] = temperature

    last_exc: Exception | None = None
    with azure_api_slot():
        for extra in ({"response_format": {"type": "json_object"}}, {}):
            try:
                response = client.chat.completions.create(**base_kwargs, **extra)
                raw = response.choices[0].message.content or "{}"
                return _parse_json_object(raw)
            except Exception as exc:
                last_exc = exc
    assert last_exc is not None
    raise last_exc


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Model did not return a JSON object.")


def _domains_from_urls(urls: list[str]) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for url in urls:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if host and host not in seen:
            seen.add(host)
            domains.append(host)
    return domains


def extract_citation_sets(
    response: Any, *, fallback_text: str = ""
) -> tuple[list[str], list[str]]:
    """Split answer citations from the web_search grounding pool.

    Returns ``(answer_urls, source_pool_urls)``, each deduped in order.
    """
    answer_urls: list[str] = []
    source_urls: list[str] = []

    for item in getattr(response, "output", None) or []:
        item_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
        if item_type == "message":
            content_list = getattr(item, "content", None) or (
                item.get("content") if isinstance(item, dict) else []
            )
            for content in content_list or []:
                annotations = getattr(content, "annotations", None) or (
                    content.get("annotations") if isinstance(content, dict) else []
                )
                for ann in annotations or []:
                    ann_type = getattr(ann, "type", None) or (
                        ann.get("type") if isinstance(ann, dict) else None
                    )
                    url = getattr(ann, "url", None) or (
                        ann.get("url") if isinstance(ann, dict) else None
                    )
                    if ann_type == "url_citation" and url:
                        answer_urls.append(url)
        if item_type == "web_search_call":
            action = getattr(item, "action", None) or (
                item.get("action") if isinstance(item, dict) else None
            )
            sources = getattr(action, "sources", None) if action is not None else None
            if sources is None and isinstance(action, dict):
                sources = action.get("sources")
            for source in sources or []:
                url = getattr(source, "url", None) or (
                    source.get("url") if isinstance(source, dict) else None
                )
                if url:
                    source_urls.append(url)

    text = fallback_text or getattr(response, "output_text", "") or ""
    text_urls = _URL_RE.findall(text)

    answer = list(dict.fromkeys(answer_urls))
    pool = list(dict.fromkeys(source_urls or text_urls))
    return answer, pool


def extract_urls_from_response(response: Any, *, fallback_text: str = "") -> list[str]:
    """Collect citation URLs, preferring in-answer annotations over the source pool."""
    answer, pool = extract_citation_sets(response, fallback_text=fallback_text)
    if answer:
        return answer
    return pool


def query_with_web_search(
    query: str,
    *,
    config: AzureOpenAIConfig | None = None,
) -> tuple[str, list[str], list[str], list[str]]:
    """Run grounded web search (always calls Bing ``web_search``).

    Returns ``(text, cited_urls, cited_domains, source_pool_urls)``.
    ``cited_urls`` prefers answer annotations; ``source_pool_urls`` is the full
    grounding set for extreme fallback when all answer cites are rejected.
    """
    cfg = config or load_azure_config()
    if cfg is None:
        raise ValueError("Azure OpenAI is not configured.")
    client = get_azure_responses_client(cfg)
    with azure_api_slot():
        # Force Bing web_search specifically. With tool_choice="auto" the model
        # often answers from memory (zero cites). With tool_choice="required"
        # gpt-5.5 sometimes satisfies the requirement via a calculator/api
        # search that has no URLs — still zero cites for Mode A.
        response = client.responses.create(
            model=cfg.deployment,
            tools=[{"type": "web_search"}],
            tool_choice={"type": "web_search"},
            input=query,
            include=["web_search_call.action.sources"],
        )
    text = getattr(response, "output_text", "") or ""
    answer, pool = extract_citation_sets(response, fallback_text=text)
    cited = answer if answer else pool
    return text, cited, _domains_from_urls(cited), pool
