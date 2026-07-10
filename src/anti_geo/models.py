from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PageContextSignals:
    cta_density: float
    commercial_context_score: float
    structure_density: float
    list_item_count: int
    table_count: int
    has_faq_schema: bool
    flags: list[str] = field(default_factory=list)
    commercial_tier: str = "none"
    commercial_triggers: list[str] = field(default_factory=list)
    has_affiliate_links: bool = False


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
    page_context: PageContextSignals | None = None
    fetch_engine: str = "httpx"


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
    front_load_score: float = 0.0
    quote_citation_density: float = 0.0
    flags: list[str] = field(default_factory=list)


@dataclass
class SourceSubscores:
    fetch_confidence: float
    source_trust: float
    rhetorical_manipulation: float
    retrieval_manipulation_risk: float
    endorsement_risk: float
    factual_claim_reliability: float
    intent_mismatch: float
    harm_severity: float


@dataclass
class SourcePermissions:
    retrieve_permission: str  # allow | downrank | defer | reject
    mention_permission: str  # allow | deny
    factual_permission: str  # allow | attribute_only | require_corroboration | deny
    endorsement_permission: str  # allow | deny


@dataclass
class QueryContextScores:
    consensus_integrity: str  # healthy | shaky | coordinated
    corroboration_strength: float
    visibility_dominance: float


@dataclass
class SourceScore:
    url: str
    fetch_ok: bool
    trust_score: float
    semantic_risk: float
    endorsement_allowed: bool
    domain_signals: DomainSignals
    content_signals: ContentSignals
    page_context: PageContextSignals | None = None
    text_excerpt: str = ""
    reasons: list[str] = field(default_factory=list)
    fetch_engine: str = "httpx"


@dataclass
class ChunkScore:
    chunk_id: str
    url: str
    text: str
    content_signals: ContentSignals
    trust_score: float
    endorsement_risk: float
    recommended_action: str


@dataclass
class UrlAnalysisReport:
    query_intent: str
    source: SourceScore
    recommended_action: str  # pass | downrank | block_endorsement | defer_fetch | reject
    endorsement_risk: float = 0.0
    query: str | None = None
    subscores: SourceSubscores | None = None
    permissions: SourcePermissions | None = None


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
    claim_entity: str
    supporting_urls: list[str]
    independent_support_count: int
    has_institutional_support: bool
    endorsement_allowed: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class VisibilityReport:
    by_url: dict[str, float]
    by_host: dict[str, float]
    dominant_url: str
    dominant_host: str
    dominant_share: float
    alert: bool = False


@dataclass
class CommercialInfluenceAssessment:
    tier: str
    triggers: list[str]
    retrieval_action: str | None = None
    factual_action: str | None = None
    endorsement_action: str | None = None
    disclosure_level: str = "none"  # none | hedge | label
    disclosure_text: str = ""
    response_mode: str | None = None


@dataclass
class CommercialDisclosure:
    trigger: str
    source_urls: list[str]
    label_text: str
    confidence: str
    applies_to_chunks: list[str] = field(default_factory=list)


@dataclass
class DisclosureReport:
    disclosures: list[CommercialDisclosure] = field(default_factory=list)
    show_label: bool = False
    combined_label_text: str = ""


@dataclass
class PassageProvenance:
    chunk_id: str
    url: str
    host: str
    text_excerpt: str
    baseline_rank: int | None
    defended_rank: int | None
    status: str
    exclusion_reasons: list[str] = field(default_factory=list)
    commercial_tier: str = "none"
    permissions_summary: str = ""


@dataclass
class ContestabilityReport:
    query: str
    included: list[PassageProvenance] = field(default_factory=list)
    excluded_alternatives: list[PassageProvenance] = field(default_factory=list)
    baseline_pawc: VisibilityReport | None = None
    defended_pawc: VisibilityReport | None = None
    dominance_delta: float = 0.0
    alternative_pools_available: bool = False


@dataclass
class GuardResult:
    utterance_type: str  # mention | endorsement | factual_claim | false_consensus
    corroborated: bool
    safe_answer: str
    actions: list[str] = field(default_factory=list)
    response_mode: str = "direct_answer"
    disclosures: list[CommercialDisclosure] = field(default_factory=list)
    disclosure_report: DisclosureReport | None = None
    contestability: ContestabilityReport | None = None
