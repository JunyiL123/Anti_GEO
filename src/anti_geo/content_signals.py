from __future__ import annotations

import re

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.models import ContentSignals, PageContextSignals

AUTHORITY_PATTERNS = [
    r"\baccording to\b",
    r"\bexperts?\b",
    r"\bdr\.?\s+\w+",
    r"\binstitute\b",
    r"\bclinical\b",
    r"\bevidence shows\b",
    r"\bas noted in\b",
    r"\bstud(y|ies)\b",
    r"\d{1,3}%\b",
]
COMPARATIVE_PATTERNS = [
    r"\bbest\b",
    r"\boutperforms?\b",
    r"\bsuperior\b",
    r"\bcompared to\b",
    r"\bbreakthrough\b",
    r"\b#1\b",
    r"\bleading\b",
]
TEMPORAL_PATTERNS = [r"\b20\d{2}\b", r"\blatest\b", r"\bnew\b"]
PURPOSE_PATTERNS = [r"\brecommend\b", r"\bshould\b", r"\bmost practical\b"]
HEDGE_PATTERNS = [
    r"\bdepends on\b",
    r"\bmay\b",
    r"\bcan help\b",
    r"\bno proven cure\b",
    r"\bconsult\b",
    r"\bnone is universally\b",
]
QUOTE_PATTERNS = [
    r'"[^"]{15,}"',
    r"'[^']{15,}'",
    r"\bstates:\s*['\"]",
]
ACCORDING_TO_RE = re.compile(r"\baccording to ([A-Z][^.,;\n]{2,50})", re.I)
QUERY_RECOMMENDATION_RE = re.compile(
    r"\b(best|recommend|should i|top \d|compare|vs\.?|versus)\b",
    re.I,
)
ENDORSEMENT_RE = re.compile(
    r"\b(the best|you should|recommend|go with|breakthrough|widely regarded|outperforms?)\b",
    re.I,
)
TOKEN_RE = re.compile(r"[a-z0-9]+")
QUERY_STOP = frozenset({"a", "an", "the", "is", "are", "what", "how", "for", "to", "of", "in", "on"})


def _density(text: str, patterns: list[str]) -> float:
    hits = sum(len(re.findall(p, text.lower())) for p in patterns)
    words = max(len(text.split()), 1)
    return min(1.0, hits / words * 8)


def _quote_citation_density(text: str) -> float:
    hits = sum(len(re.findall(p, text)) for p in QUOTE_PATTERNS)
    hits += len(ACCORDING_TO_RE.findall(text))
    words = max(len(text.split()), 1)
    return min(1.0, hits / words * 10)


def mentions_alternatives(text: str) -> bool:
    return bool(
        re.search(
            r"\b(options include|alternatives include|include trello|include asana|such as trello|compared to| versus | vs\.|no single app is universally best|everyone has a different workflow|none is universally)\b",
            text,
            re.I,
        )
    )


def query_wants_recommendation(query: str | None) -> bool:
    if not query:
        return False
    return bool(QUERY_RECOMMENDATION_RE.search(query))


def chunk_endorses(text: str, content: ContentSignals) -> bool:
    if ENDORSEMENT_RE.search(text):
        return True
    if content.comparative_density > DEFAULT_CONFIG.comparative_flag_threshold:
        return True
    return "comparative_superlatives" in content.flags


def compute_front_load_score(
    text: str,
    query: str | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> float:
    words = text.split()
    if len(words) < 40:
        return 0.0
    window = config.front_load_window_words
    head = " ".join(words[:window]).lower()
    tail = " ".join(words[window:]).lower()

    if query:
        q_terms = {t for t in TOKEN_RE.findall(query.lower()) if t not in QUERY_STOP and len(t) > 2}
        if not q_terms:
            return 0.0
        head_hits = sum(1 for t in q_terms if t in head)
        tail_hits = sum(1 for t in q_terms if t in tail) if tail else 0
        total = head_hits + tail_hits
        if total == 0:
            return 0.0
        return min(1.0, head_hits / total)

    head_d = _density(head, AUTHORITY_PATTERNS + COMPARATIVE_PATTERNS)
    tail_d = _density(tail, AUTHORITY_PATTERNS + COMPARATIVE_PATTERNS) if tail else 0.0
    total = head_d + tail_d
    if total == 0:
        return 0.0
    return min(1.0, head_d / total)


def extract_content_signals(
    text: str,
    query: str | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> ContentSignals:
    if not text.strip():
        return ContentSignals(
            word_count=0,
            authority_density=0.0,
            comparative_density=0.0,
            temporal_density=0.0,
            narrative_purposiveness=0.0,
            semantic_risk=0.0,
            front_load_score=0.0,
            quote_citation_density=0.0,
            flags=["empty_content"],
        )

    aa = _density(text, AUTHORITY_PATTERNS)
    ca = _density(text, COMPARATIVE_PATTERNS)
    tc = _density(text, TEMPORAL_PATTERNS)
    np = min(1.0, (aa + ca + _density(text, PURPOSE_PATTERNS)) / 2)
    hedges = _density(text, HEDGE_PATTERNS)
    qc = _quote_citation_density(text)
    fl = compute_front_load_score(text, query, config)

    semantic_risk = max(0.0, (0.3 * aa + 0.3 * np + 0.25 * ca + 0.15 * tc) - 0.35 * hedges)
    if fl > 0.6 and semantic_risk > 0:
        semantic_risk = min(1.0, semantic_risk * (1.0 + 0.25 * fl))

    flags: list[str] = []
    if aa > config.authority_flag_threshold:
        flags.append("authority_stacking")
    if ca > config.comparative_flag_threshold:
        flags.append("comparative_superlatives")
    if re.search(r"\b(cure[ds]?|remission)\b", text, re.I):
        flags.append("high_stakes_medical_claim")
    if hedges > config.hedging_flag_threshold:
        flags.append("balanced_hedging")
    if fl > 0.65:
        flags.append("front_loaded")
    if qc > 0.25:
        flags.append("quote_citation_heavy")
    if mentions_alternatives(text):
        flags.append("mentions_alternatives")

    return ContentSignals(
        word_count=len(text.split()),
        authority_density=aa,
        comparative_density=ca,
        temporal_density=tc,
        narrative_purposiveness=np,
        semantic_risk=semantic_risk,
        front_load_score=fl,
        quote_citation_density=qc,
        flags=flags,
    )


def compute_endorsement_risk(
    query: str | None,
    text: str,
    content: ContentSignals,
    trust_score: float,
    page_context: PageContextSignals | None = None,
    query_intent: str = "informational",
    config: DefenseConfig = DEFAULT_CONFIG,
) -> float:
    """Conjunction: only high when query+chunk+trust align on undeserved endorsement."""
    if not query_intent.startswith("informational"):
        return 0.0

    q_rec = query_wants_recommendation(query)
    endorses = chunk_endorses(text, content)
    balanced = "balanced_hedging" in content.flags or "mentions_alternatives" in content.flags

    exploit = max(content.front_load_score, 0.35)
    risk = content.semantic_risk * exploit * (1.0 - trust_score)

    if q_rec:
        risk *= 1.0 if endorses else 0.35
    else:
        risk *= 0.25

    if balanced:
        risk *= 0.2

    if page_context and page_context.commercial_context_score > 0.4 and not q_rec:
        risk *= 0.1

    # Underserved endorsement: recommendation query + persuasive chunk + insufficient trust
    if q_rec and endorses and trust_score < config.trust_endorsement_min and not balanced:
        risk = max(risk, config.endorsement_risk_block)

    return min(1.0, max(0.0, risk))


def action_from_endorsement_risk(risk: float, config: DefenseConfig = DEFAULT_CONFIG) -> str:
    if risk >= config.endorsement_risk_block:
        return "block_endorsement"
    if risk >= config.endorsement_risk_downrank:
        return "downrank"
    return "pass"


def rhetorical_manipulation_score(content: ContentSignals) -> float:
    """Persuasive/rhetorical risk without retrieval front-load amplification."""
    fl = content.front_load_score
    risk = content.semantic_risk
    if fl > 0.6 and risk > 0:
        risk = risk / (1.0 + 0.25 * fl)
    return min(1.0, max(0.0, risk))


def retrieval_manipulation_score(
    content: ContentSignals,
    rhetorical: float | None = None,
) -> float:
    """SEO/front-load manipulation risk, scaled by persuasive content signals."""
    rhet = rhetorical if rhetorical is not None else rhetorical_manipulation_score(content)
    persuasive = max(rhet, content.comparative_density, content.authority_density * 0.5)
    return min(1.0, max(0.0, content.front_load_score * max(0.2, persuasive)))
