from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from anti_geo.audit.models import CitationRecord, EngineResponse

_URL_RE = re.compile(r"https?://[^\s\])>\"']+")


def _domains_from_urls(urls: list[str]) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for url in urls:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if host and host not in seen:
            seen.add(host)
            domains.append(host)
    return domains


def _extract_urls(text: str) -> list[str]:
    return _URL_RE.findall(text)


class EngineAdapter(Protocol):
    name: str

    def query(self, q: str) -> EngineResponse: ...


class MockEngine:
    """Deterministic engine using fixture JSONL replays."""

    name = "mock"

    def __init__(self, fixture_path: Path | None = None) -> None:
        if fixture_path is None:
            fixture_path = (
                Path(__file__).resolve().parents[3]
                / "tests"
                / "fixtures"
                / "audit_replays"
                / "default.jsonl"
            )
        self._responses: dict[str, EngineResponse] = {}
        if fixture_path.exists():
            for line in fixture_path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                self._responses[row["query"]] = EngineResponse(
                    text=row.get("text", ""),
                    cited_domains=row.get("cited_domains", []),
                    cited_urls=row.get("cited_urls", []),
                )

    def query(self, q: str) -> EngineResponse:
        if q in self._responses:
            return self._responses[q]
        return EngineResponse(
            text=f"Mock answer for: {q}",
            cited_domains=["example.com"],
            cited_urls=["https://example.com/article"],
        )


class PerplexityEngine:
    """Live Perplexity API adapter (requires PERPLEXITY_API_KEY)."""

    name = "perplexity"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("PERPLEXITY_API_KEY", "")
        if not self.api_key:
            raise ValueError("PERPLEXITY_API_KEY is required for PerplexityEngine")

    def query(self, q: str) -> EngineResponse:
        import httpx

        response = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": q}],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        citations = data.get("citations") or []
        cited_urls = list(citations) if citations else _extract_urls(text)
        return EngineResponse(
            text=text,
            cited_domains=_domains_from_urls(cited_urls),
            cited_urls=cited_urls,
        )


class AzureEngine:
    """Azure OpenAI Responses API with built-in web_search (Bing grounding)."""

    name = "azure"

    def query(self, q: str) -> EngineResponse:
        from anti_geo.azure_client import load_azure_config, query_with_web_search

        if load_azure_config() is None:
            raise ValueError(
                "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT."
            )
        text, cited_urls, cited_domains = query_with_web_search(q)
        if not cited_urls:
            cited_urls = _extract_urls(text)
            cited_domains = _domains_from_urls(cited_urls)
        return EngineResponse(
            text=text,
            cited_domains=cited_domains,
            cited_urls=cited_urls,
        )


def get_engine(name: str, *, fixture_path: Path | None = None) -> EngineAdapter:
    if name == "mock":
        return MockEngine(fixture_path=fixture_path)
    if name == "perplexity":
        return PerplexityEngine()
    if name == "azure":
        return AzureEngine()
    raise ValueError(f"Unknown engine: {name}")


def record_from_response(
    run_id: str,
    engine: str,
    query: str,
    response: EngineResponse,
    *,
    paraphrase_of: str | None = None,
    timestamp: str | None = None,
) -> CitationRecord:
    from datetime import datetime, timezone

    return CitationRecord(
        run_id=run_id,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        engine=engine,
        query=query,
        paraphrase_of=paraphrase_of,
        response_text=response.text,
        cited_domains=response.cited_domains,
        cited_urls=response.cited_urls,
    )
