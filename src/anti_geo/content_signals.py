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
PERSONAL_NARRATIVE_RE = re.compile(
    r"\b("
    r"my (?:dad|mom|father|mother|girlfriend|boyfriend|husband|wife|partner|friends?)|"
    r"i (?:got|gave|bought|wear|love|dont|don't|wasn't|wasnt|genuinely)|"
    r"(?:for|on) (?:his|her|my) (?:birthday|anniversary|father'?s day)|"
    r"every day|still (?:holding|thinking)"
    r")\b",
    re.I,
)
CONSUMER_CONTEXT_RE = re.compile(
    r"\b("
    r"bracelet|pendant|necklace|ring|engraved|jewelry|jewellery|gift|"
    r"earbud(?:s)?|headphones?|buds|wireless|"
    r"portfolio|trading|invest(?:ing|or|ments)?|lump sum|long[- ]term|broker|market"
    r")\b",
    re.I,
)
BRAND_IN_NARRATIVE_RE = re.compile(
    r"\b("
    r"(?:got|gave|bought|ordered|wear(?:ing)?|using|collecting)\s+(?:\w+\s+){0,10}?"
    r"(?:from|on|with)\s+[a-z][a-z0-9-]{3,}"
    r"|"
    r"(?:bracelet|pendant|necklace|app|platform)\s+(?:from|on)\s+[a-z][a-z0-9-]{3,}"
    r")\b",
    re.I,
)
REVIEW_FRAMING_RE = re.compile(
    r"\b("
    r"review|reviewed|pros?\b|cons?\b|specs?|unboxing|verdict|"
    r"compared\s+to|versus|\bvs\.?\b|affiliate|sponsored"
    r")\b",
    re.I,
)
ENTITY_PLACEMENT_RE = re.compile(
    r"\b(?:from|on|with|via|using|through|bought\s+(?:at|from)|ordered\s+(?:from|on))\s+",
    re.I,
)
# "I got EarFun buds" / "bought lemonn ..." without an explicit from/on.
ENTITY_ACQUISITION_RE = re.compile(
    r"\b(?:got|gave|bought|ordered|wear(?:ing)?|using|tried|collecting)\b",
    re.I,
)
# Fintech / app planted posts often use the brand as the venue, not "from Brand".
ENTITY_PLATFORM_CONTEXT_RE = re.compile(
    r"\b(portfolio|app|platform|broker|trading|account|lump\s+sum)\b",
    re.I,
)
TOKEN_RE = re.compile(r"[a-z0-9]+")
QUERY_STOP = frozenset({"a", "an", "the", "is", "are", "what", "how", "for", "to", "of", "in", "on"})

# Mode B plant-stance (hard parasitic share): promotional beats complaint.
PLANT_STANCE_PROMOTIONAL = "promotional"
PLANT_STANCE_COMPLAINT = "complaint"
PLANT_STANCE_NEUTRAL = "neutral"
PLANT_STANCE_UNKNOWN = "unknown"

_AFFILIATE_PROMO_RE = re.compile(
    r"\b("
    r"affiliate|sponsored|paid\s+partnership|partner\s+link|my\s+link|"
    r"use\s+(?:my\s+)?code|discount\s+code|promo\s+code|coupon\s+code"
    r")\b",
    re.I,
)
_GLAZE_RE = re.compile(
    r"\b("
    r"highly\s+recommend|must[- ]buy|game[- ]?changer|life[- ]?changing|"
    r"best\s+purchase|absolutely\s+love|genuinely\s+love|obsessed\s+with|"
    r"switched\s+to|go\s+with|check\s+(?:them|it)\s+out|worth\s+every\s+(?:penny|cent)"
    r")\b",
    re.I,
)
_COMPETITOR_BASH_RE = re.compile(
    r"\b("
    r"instead\s+of|skip\s+\w+|don'?t\s+buy\s+\w+|avoid\s+\w+|"
    r"better\s+than\s+\w+|unlike\s+\w+|ditch(?:ed)?\s+\w+|"
    r"switch(?:ed)?\s+(?:from|away\s+from)\s+\w+"
    r")\b",
    re.I,
)
_COMPLAINT_RE = re.compile(
    r"\b("
    r"scam|fraud|ripoff|rip[- ]off|never\s+received|didn'?t\s+arrive|"
    r"no\s+refund|stolen|chargeback|do\s+not\s+buy|don'?t\s+buy|"
    r"customer\s+service|terrible|horrible|worst\s+(?:company|experience)|"
    r"complaint|refund\s+denied|still\s+waiting|ghosted\s+me"
    r")\b",
    re.I,
)


def classify_plant_stance(
    text: str,
    *,
    flags: list[str] | None = None,
) -> str:
    """Classify UGC/review referrer stance for Mode B hard parasitic share.

    Returns one of: promotional | complaint | neutral | unknown.

    Promotional includes glaze, competitor-bash, affiliate promo, and planted
    soft-sell. Any promotional signal wins over co-occurring complaints
    (complaint-shaped plants still count). Empty text → unknown.
    """
    flags_l = [str(f).lower() for f in (flags or [])]
    if "planted_mention" in flags_l or "comparative_superlatives" in flags_l:
        return PLANT_STANCE_PROMOTIONAL

    blob = (text or "").strip()
    if not blob:
        return PLANT_STANCE_UNKNOWN

    promo = bool(
        _AFFILIATE_PROMO_RE.search(blob)
        or _GLAZE_RE.search(blob)
        or _COMPETITOR_BASH_RE.search(blob)
        or ENDORSEMENT_RE.search(blob)
    )
    if promo:
        return PLANT_STANCE_PROMOTIONAL

    if _COMPLAINT_RE.search(blob):
        return PLANT_STANCE_COMPLAINT

    return PLANT_STANCE_NEUTRAL


def plant_stance_heuristic_rules_rubric() -> str:
    """Encode classify_plant_stance for the Mode B stance LLM backup."""
    stances = "|".join(
        (
            PLANT_STANCE_PROMOTIONAL,
            PLANT_STANCE_COMPLAINT,
            PLANT_STANCE_NEUTRAL,
            PLANT_STANCE_UNKNOWN,
        )
    )
    return f"""\
You classify plant stance of a third-party UGC/review referrer for Anti-GEO
Mode B hard parasitic share — NOT an independent free-form labeler. Apply the
SAME rules as anti_geo.content_signals.classify_plant_stance.

Return JSON only:
{{"stance":"<{stances}>","reason":"short"}}

=== Anti-GEO plant-stance heuristic rules (must follow) ===

- promotional: glaze / stealth endorsement, competitor-bash ("skip X, use Brand"),
  affiliate/sponsored/promo-code CTA, planted soft-sell narrative, or flags
  planted_mention / comparative_superlatives. ANY promotional signal wins over
  co-occurring complaints (complaint-shaped plants still count as promotional).
- complaint: organic complaint/scam/refund rant with NO promotional signal.
- neutral: how-to / incidental brand mention without promo or complaint.
- unknown: empty / unusable excerpt.

Do NOT invent promotional stance without textual evidence. Prefer complaint or
neutral over promotional when unsure. This affects Mode B hard share only —
never rewrite retrieve/endorsement permissions.
"""


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


def _entity_variants(entity: str) -> set[str]:
    ent = entity.lower().strip()
    if not ent:
        return set()
    variants = {ent, ent.replace(" ", ""), ent.replace(" ", "-")}
    return {v for v in variants if len(v) >= 3}


def _entity_span_iter(text_lower: str, entity: str):
    """Yield match spans for entity allowing optional spaces (theo grace / theograce)."""
    ent = entity.lower().strip()
    if not ent:
        return
    variants = _entity_variants(entity)
    if " " in ent:
        flexible = re.escape(ent).replace(r"\ ", r"\s*")
        for m in re.finditer(flexible, text_lower):
            yield m
    compact = re.sub(r"[^a-z0-9]", "", ent)
    # Compact brands often appear spaced in posts (“theo grace”).
    if len(compact) >= 6:
        flex_compact = r"\s*".join(re.escape(c) for c in compact)
        for m in re.finditer(flex_compact, text_lower):
            yield m
    for variant in variants:
        for m in re.finditer(re.escape(variant), text_lower):
            yield m


def _entity_soft_placed(text: str, entity: str) -> bool:
    """True when entity is woven into the story as a product/app placement."""
    lower = text.lower()
    if not entity.strip():
        return False
    seen: set[tuple[int, int]] = set()
    for m in _entity_span_iter(lower, entity):
        key = (m.start(), m.end())
        if key in seen:
            continue
        seen.add(key)
        before = lower[max(0, m.start() - 40) : m.start()]
        around = lower[max(0, m.start() - 30) : m.end() + 50]
        if ENTITY_PLACEMENT_RE.search(before):
            return True
        # Acquisition verb shortly before the brand (“I got EarFun buds”).
        if ENTITY_ACQUISITION_RE.search(before):
            return True
        if ENTITY_PLATFORM_CONTEXT_RE.search(around):
            return True
        # Typos / near-word portfolio (porfolio) and concurrent app lists.
        if re.search(r"portfol|invest|lump\s*sum|\band\s+[a-z]{3,}\b", around):
            return True
        if BRAND_IN_NARRATIVE_RE.search(lower[max(0, m.start() - 80) : m.end() + 20]):
            return True
    return False


def detect_planted_mention(text: str, entity: str | None = None) -> bool:
    """
    Conversational brand placement: personal narrative + product context, no superlatives.
    Typical of native Reddit GEO (GrowReddit-style) posts.

    Conservative by design: review/comparison framing and entity-free loose matches
    are treated as non-planted to limit false positives on organic UGC and blogs.
    """
    words = text.split()
    if len(words) < 25:
        return False
    if ENDORSEMENT_RE.search(text):
        return False
    if mentions_alternatives(text):
        return False
    # Editorial / review framing is usually organic product discussion, not planted soft-sell.
    if REVIEW_FRAMING_RE.search(text):
        return False

    has_narrative = bool(PERSONAL_NARRATIVE_RE.search(text))
    has_consumer = bool(CONSUMER_CONTEXT_RE.search(text))
    has_placement = bool(BRAND_IN_NARRATIVE_RE.search(text))

    if not (has_narrative and has_consumer):
        return False

    if entity:
        spans = list(_entity_span_iter(text.lower(), entity))
        if not spans:
            ent_compact = entity.lower().replace(" ", "")
            text_compact = re.sub(r"\s+", "", text.lower())
            if ent_compact not in text_compact and entity.lower() not in text.lower():
                return False
        # Require soft brand placement, not merely entity string somewhere in the thread.
        return _entity_soft_placed(text, entity)

    # Without an entity, require explicit brand-in-narrative placement (stricter).
    return has_placement


def diagnose_planted_mention(text: str, entity: str | None = None) -> dict[str, object]:
    """Explain planted / soft-placement / endorsement gates for mining & labeling.

    ``bucket`` values (mutually oriented for triage, not exclusivity guarantees):
    - planted_hit: detect_planted_mention True
    - soft_sell_near_miss: story+consumer+entity, soft-placement failed (FN candidate)
    - hard_endorsement: open recommend/best language (soft-sell path vetoed)
    - review_framed: review/comparison framing
    - other_l1: authority/front-load/etc without planted
    - clean_or_other: no strong story/endorsement signal
    """
    words = text.split()
    has_narrative = bool(PERSONAL_NARRATIVE_RE.search(text))
    has_consumer = bool(CONSUMER_CONTEXT_RE.search(text))
    has_placement = bool(BRAND_IN_NARRATIVE_RE.search(text))
    review_framed = bool(REVIEW_FRAMING_RE.search(text))
    hard_endorsement = bool(ENDORSEMENT_RE.search(text))
    mentions_alts = mentions_alternatives(text)

    entity_present = False
    soft_placed = False
    if entity:
        spans = list(_entity_span_iter(text.lower(), entity))
        if spans:
            entity_present = True
        else:
            ent_compact = entity.lower().replace(" ", "")
            text_compact = re.sub(r"\s+", "", text.lower())
            entity_present = ent_compact in text_compact or entity.lower() in text.lower()
        soft_placed = _entity_soft_placed(text, entity) if entity_present else False

    planted = detect_planted_mention(text, entity=entity)
    signals = extract_content_signals(text, entity=entity)
    l1_flags = list(signals.flags)

    reasons: list[str] = []
    if len(words) < 25:
        reasons.append("too_short")
    if hard_endorsement:
        reasons.append("hard_endorsement")
    if mentions_alts:
        reasons.append("mentions_alternatives")
    if review_framed:
        reasons.append("review_framed")
    if entity and not entity_present:
        reasons.append("entity_absent")
    if entity_present and not soft_placed:
        reasons.append("soft_placement_failed")
    if not has_narrative:
        reasons.append("no_narrative")
    if not has_consumer:
        reasons.append("no_consumer_context")
    if planted:
        reasons.append("planted_hit")

    if planted:
        bucket = "planted_hit"
    elif hard_endorsement and entity_present:
        bucket = "hard_endorsement"
    elif (
        entity_present
        and has_narrative
        and has_consumer
        and not soft_placed
        and not review_framed
        and not hard_endorsement
        and not mentions_alts
        and len(words) >= 25
    ):
        bucket = "soft_sell_near_miss"
    elif review_framed and entity_present:
        bucket = "review_framed"
    elif any(
        f in l1_flags
        for f in (
            "authority_stacking",
            "comparative_superlatives",
            "front_loaded",
            "quote_citation_heavy",
            "high_stakes_medical_claim",
        )
    ):
        bucket = "other_l1"
    else:
        bucket = "clean_or_other"

    return {
        "bucket": bucket,
        "planted": planted,
        "entity_present": entity_present,
        "soft_placed": soft_placed,
        "has_narrative": has_narrative,
        "has_consumer": has_consumer,
        "has_brand_in_narrative": has_placement,
        "hard_endorsement": hard_endorsement,
        "review_framed": review_framed,
        "mentions_alternatives": mentions_alts,
        "semantic_risk": round(signals.semantic_risk, 4),
        "l1_flags": l1_flags,
        "reasons": reasons,
        "word_count": len(words),
    }


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
    *,
    entity: str | None = None,
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
    if detect_planted_mention(text, entity=entity):
        flags.append("planted_mention")

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

    planted = "planted_mention" in content.flags
    if planted and q_rec and trust_score < config.trust_endorsement_min:
        risk = max(risk, config.endorsement_risk_downrank)

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
