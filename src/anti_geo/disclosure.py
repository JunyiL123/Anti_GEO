from __future__ import annotations

import re

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.models import (
    CommercialDisclosure,
    CommercialInfluenceAssessment,
    DisclosureReport,
    GuardResult,
    SourceScore,
)
from anti_geo.contestability import chunk_key
from anti_geo.retrieval import ScoredChunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _token_overlap(text_a: str, text_b: str) -> float:
    a = set(_TOKEN_RE.findall(text_a.lower()))
    b = set(_TOKEN_RE.findall(text_b.lower()))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def chunk_contributes_to_answer(
    chunk: ScoredChunk,
    safe_answer: str,
    *,
    is_lead: bool = False,
    overlap_min: float = DEFAULT_CONFIG.claim_chunk_overlap_min,
) -> bool:
    if is_lead:
        return True
    return _token_overlap(chunk.text, safe_answer) >= overlap_min


def build_disclosure_report(
    defended_chunks: list[ScoredChunk],
    sources: dict[str, SourceScore],
    commercial_assessments: dict[str, CommercialInfluenceAssessment],
    guard: GuardResult,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> DisclosureReport:
    """Build precision-first disclosure report for user-visible labels."""
    disclosures: list[CommercialDisclosure] = []
    lead_key = chunk_key(defended_chunks[0]) if defended_chunks else None

    for chunk in defended_chunks:
        key = chunk_key(chunk)
        assessment = commercial_assessments.get(key)
        if not assessment or assessment.disclosure_level != "label":
            continue
        if not _tier_at_least(assessment.tier, config.commercial_label_min_tier):
            continue
        if not chunk_contributes_to_answer(
            chunk, guard.safe_answer, is_lead=(key == lead_key)
        ):
            continue

        trigger = assessment.triggers[0] if assessment.triggers else assessment.tier
        disclosures.append(
            CommercialDisclosure(
                trigger=trigger,
                source_urls=[chunk.url],
                label_text=assessment.disclosure_text,
                confidence="high",
                applies_to_chunks=[chunk.chunk_id],
            )
        )

    if not disclosures:
        return DisclosureReport(disclosures=[], show_label=False, combined_label_text="")

    unique_texts = list(dict.fromkeys(d.label_text for d in disclosures))
    combined = "\n\n".join(unique_texts)
    return DisclosureReport(
        disclosures=disclosures,
        show_label=True,
        combined_label_text=combined,
    )


def apply_disclosures_to_answer(
    safe_answer: str,
    disclosure_report: DisclosureReport,
) -> str:
    if not disclosure_report.show_label or not disclosure_report.combined_label_text:
        return safe_answer
    return f"## Disclosure\n{disclosure_report.combined_label_text}\n\n{safe_answer}"


_TIER_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _tier_at_least(tier: str, minimum: str) -> bool:
    return _TIER_RANK.get(tier, 0) >= _TIER_RANK.get(minimum, 0)
