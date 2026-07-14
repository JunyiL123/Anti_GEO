"""Resolve search-query intent: heuristics first, LLM only when ambiguous."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from anti_geo.azure_client import chat_completion_json, is_azure_configured, load_azure_config

logger = logging.getLogger(__name__)

INTENT_LABELS = frozenset(
    {
        "informational",
        "informational_high_stakes",
        "commercial",
        "navigational",
    }
)

DEFAULT_AMBIGUOUS_INTENT = "informational"

# Ordered: first match wins (after hostname short-circuit).
_HIGH_STAKES_RE = re.compile(
    r"\b("
    r"symptom(?:s)?|diagnos(?:e|is|ed)|treat(?:ment|ments|ing)?|cure(?:s|d)?|"
    r"medication(?:s)?|prescription|dose|dosage|side[\s-]?effect|"
    r"cancer|diabetes|depression|anxiety|chronic|disease|illness|"
    r"supplement(?:s)?|vaccine|pregnancy|pregnant|overdose|"
    r"is it safe to|should i take|doctor|physician|clinic|"
    r"lawsuit|attorney|legal advice|will this get me fired|"
    r"invest(?:ing|ment)? advice|retirement account|tax evasion"
    r")\b",
    re.I,
)

_NAVIGATIONAL_PHRASE_RE = re.compile(
    r"\b("
    r"official (?:site|website|page)|homepage|home page|"
    r"log[\s-]?in|sign[\s-]?in|customer portal|"
    r"(?:company|brand) website|"
    r"site:\S+"
    r")\b"
    r"|https?://\S+",
    re.I,
)

_HOSTNAME_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?[\w-]+\.(?:com|org|net|io|gov|edu)(?:/\S*)?$",
    re.I,
)

# "best way/method/..." is usually how-to, not shopping.
_BEST_HOWTO_RE = re.compile(
    r"\bbest (?:way|ways|method|methods|practice|practices|time|times)\b",
    re.I,
)

_COMMERCIAL_RE = re.compile(
    r"\b("
    r"best|top\s*\d+|recommend(?:ed|ation)?|"
    r"buy|purchase|order|shopping|shop for|"
    r"cheap(?:est)?|deal(?:s)?|coupon|discount|pricing|price of|"
    r"worth (?:it|buying)|should i (?:buy|get|switch)|"
    r"vs\.?|versus|compare|comparison|alternative(?:s)? (?:to|for)|"
    r"review(?:s)? of|buying guide|which .+ (?:should|to) (?:i |we )?(?:buy|get|use)|"
    r"affiliate|near me|for sale"
    r")\b",
    re.I,
)

_INFORMATIONAL_RE = re.compile(
    r"\b("
    r"how (?:do|to|can|does|did)|how['’]s|"
    r"what (?:is|are|was|were|does|do|did)|what's|whats|"
    r"why (?:is|are|do|does|did|can|would)|"
    r"when (?:do|does|did|is|are)|"
    r"where (?:do|does|did|is|are|can)|"
    r"who (?:is|are|was|were)|"
    r"explain|define|definition|meaning of|tutorial|"
    r"recipe|cook(?:ing)?|bake(?:ing)?|steps? (?:to|for)|"
    r"guide to|instructions? (?:for|on)|learn (?:how|about)|"
    r"difference between|history of|causes? of"
    r")\b",
    re.I,
)

_HOWTO_OVERRIDE_RE = re.compile(
    r"\b(how (?:do|to|can)|recipe|cook(?:ing)?|bake(?:ing)?|tutorial|explain)\b",
    re.I,
)


@dataclass(frozen=True)
class IntentClassification:
    intent: str
    source: str  # heuristic | llm | default | manual
    matched_rule: str | None = None


def _normalized_query(query: str) -> str:
    return " ".join((query or "").strip().split())


def _looks_like_hostname_query(query: str) -> bool:
    tokens = query.split()
    if not tokens:
        return False
    if len(tokens) == 1 and _HOSTNAME_RE.match(tokens[0]):
        return True
    if len(tokens) <= 3 and _HOSTNAME_RE.match(tokens[0]):
        # e.g. "taskflow.com login", "nih.gov"
        return True
    return False


def classify_query_intent_heuristic(query: str) -> IntentClassification | None:
    """Return a classification if a cheap rule matches; else None (ambiguous)."""
    q = _normalized_query(query)
    if not q:
        return IntentClassification(DEFAULT_AMBIGUOUS_INTENT, "default", "empty")

    if _looks_like_hostname_query(q) or _NAVIGATIONAL_PHRASE_RE.search(q):
        return IntentClassification("navigational", "heuristic", "navigational")
    if _HIGH_STAKES_RE.search(q):
        return IntentClassification(
            "informational_high_stakes", "heuristic", "high_stakes"
        )
    # How-to with "best way..." beats bare commercial "best".
    if _BEST_HOWTO_RE.search(q) or _INFORMATIONAL_RE.search(q):
        if (
            _COMMERCIAL_RE.search(q)
            and not _BEST_HOWTO_RE.search(q)
            and not _HOWTO_OVERRIDE_RE.search(q)
        ):
            # e.g. "what is the best laptop" — commercial recommendation
            return IntentClassification("commercial", "heuristic", "commercial")
        return IntentClassification("informational", "heuristic", "informational")
    if _COMMERCIAL_RE.search(q):
        return IntentClassification("commercial", "heuristic", "commercial")
    return None


def _build_intent_prompt(query: str) -> list[dict[str, str]]:
    labels = ", ".join(sorted(INTENT_LABELS))
    return [
        {
            "role": "system",
            "content": (
                "You classify user search queries for an AI-search integrity system. "
                "Output valid JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Classify this query into exactly one intent label: {labels}.\n\n"
                "Definitions:\n"
                "- informational: how-to, explanations, facts, recipes, tutorials "
                "(not shopping).\n"
                "- informational_high_stakes: health, medical, legal, or safety-critical "
                "advice where getting it wrong can seriously harm someone.\n"
                "- commercial: shopping, product/recommendation, comparisons, pricing, "
                "reviews aimed at buying.\n"
                "- navigational: finding a specific site, login, official page, or URL.\n\n"
                'Return JSON: {"intent": "<label>"}\n\n'
                f"Query: {query}"
            ),
        },
    ]


def classify_query_intent_llm(query: str) -> str:
    payload = chat_completion_json(
        _build_intent_prompt(query),
        config=load_azure_config(),
        temperature=0.0,
    )
    raw = payload.get("intent") or payload.get("query_intent") or ""
    if not isinstance(raw, str):
        raise ValueError("Intent JSON must include an intent string.")
    intent = raw.strip().lower().replace(" ", "_")
    if intent not in INTENT_LABELS:
        raise ValueError(f"Unknown intent from model: {raw!r}")
    return intent


def resolve_query_intent(
    query: str,
    intent: str | None = "auto",
    *,
    allow_llm: bool = True,
) -> IntentClassification:
    """
    Resolve intent for a query.

    - Explicit known labels (not ``auto``) → ``manual``
    - ``auto`` / empty / None → heuristics, then LLM if Azure configured, else default
    """
    requested = (intent or "auto").strip().lower()
    if requested and requested != "auto":
        if requested not in INTENT_LABELS:
            logger.warning("Unknown query intent %r; using as-is", intent)
        return IntentClassification(requested, "manual", None)

    hit = classify_query_intent_heuristic(query)
    if hit is not None:
        return hit

    if allow_llm and is_azure_configured():
        try:
            label = classify_query_intent_llm(query)
            return IntentClassification(label, "llm", None)
        except Exception as exc:
            logger.warning("LLM intent classification failed, using default: %s", exc)

    return IntentClassification(DEFAULT_AMBIGUOUS_INTENT, "default", "ambiguous")
