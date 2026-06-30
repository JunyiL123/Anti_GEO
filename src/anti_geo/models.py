from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int | None
    ok: bool
    error: str | None
    title: str
    text: str
    link_count: int
    broken_link_ratio: float
    redirect_count: int
    response_time_ms: float
    has_privacy_page: bool
    has_contact_page: bool


@dataclass
class DomainSignals:
    hostname: str
    tld: str
    is_https: bool
    cert_age_days: int | None
    whois_age_days: int | None
    dns_resolves: bool
    signals: list[str] = field(default_factory=list)


@dataclass
class ContentSignals:
    word_count: int
    authority_density: float
    comparative_density: float
    temporal_density: float
    narrative_purposiveness: float
    semantic_risk: float
    flags: list[str] = field(default_factory=list)


@dataclass
class SourceScore:
    url: str
    fetch_ok: bool
    trust_score: float
    semantic_risk: float
    endorsement_allowed: bool
    domain_signals: DomainSignals
    content_signals: ContentSignals
    text_excerpt: str = ""
    reasons: list[str] = field(default_factory=list)


@dataclass
class UrlAnalysisReport:
    query_intent: str
    source: SourceScore
    recommended_action: str  # pass | downrank | block_endorsement | reject


@dataclass
class IndependenceReport:
    urls: list[str]
    naive_source_count: int
    cluster_count: int
    max_cluster_similarity: float
    is_likely_coordinated: bool
    pairwise_similarity: dict[str, float]
    reasons: list[str] = field(default_factory=list)


@dataclass
class CorroborationReport:
    claim_entity: str | None
    supporting_urls: list[str]
    independent_support_count: int
    has_institutional_support: bool
    endorsement_allowed: bool
    reasons: list[str] = field(default_factory=list)
