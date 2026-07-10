from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EngineResponse:
    text: str
    cited_domains: list[str]
    cited_urls: list[str] = field(default_factory=list)


@dataclass
class CitationRecord:
    run_id: str
    timestamp: str
    engine: str
    query: str
    paraphrase_of: str | None
    response_text: str
    cited_domains: list[str]
    cited_urls: list[str] = field(default_factory=list)


@dataclass
class ParaphrasePair:
    category: str
    original: str
    paraphrase: str


@dataclass
class AuditRun:
    run_id: str
    engine: str
    started_at: str
    records: list[CitationRecord] = field(default_factory=list)


@dataclass
class AuditSummary:
    engine: str
    query_count: int
    mean_jaccard_distance: float
    pct_citation_change: float
    domain_shares: dict[str, float]
    persistence_rate: float | None = None
    geo_risk_share: float | None = None
    commercial_high_share: float | None = None
