from __future__ import annotations

import re

from anti_geo.models import ContentSignals

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


def _density(text: str, patterns: list[str]) -> float:
    hits = sum(len(re.findall(p, text.lower())) for p in patterns)
    words = max(len(text.split()), 1)
    return min(1.0, hits / words * 8)


def extract_content_signals(text: str) -> ContentSignals:
    if not text.strip():
        return ContentSignals(
            word_count=0,
            authority_density=0.0,
            comparative_density=0.0,
            temporal_density=0.0,
            narrative_purposiveness=0.0,
            semantic_risk=0.0,
            flags=["empty_content"],
        )

    aa = _density(text, AUTHORITY_PATTERNS)
    ca = _density(text, COMPARATIVE_PATTERNS)
    tc = _density(text, TEMPORAL_PATTERNS)
    np = min(1.0, (aa + ca + _density(text, PURPOSE_PATTERNS)) / 2)
    hedges = _density(text, HEDGE_PATTERNS)

    # Persuasion minus hedging → higher risk on informational queries
    semantic_risk = max(0.0, (0.3 * aa + 0.3 * np + 0.25 * ca + 0.15 * tc) - 0.35 * hedges)

    flags: list[str] = []
    if aa > 0.35:
        flags.append("authority_stacking")
    if ca > 0.35:
        flags.append("comparative_superlatives")
    if re.search(r"\b(cure[ds]?|remission)\b", text, re.I):
        flags.append("high_stakes_medical_claim")
    if hedges > 0.2:
        flags.append("balanced_hedging")

    return ContentSignals(
        word_count=len(text.split()),
        authority_density=aa,
        comparative_density=ca,
        temporal_density=tc,
        narrative_purposiveness=np,
        semantic_risk=semantic_risk,
        flags=flags,
    )
