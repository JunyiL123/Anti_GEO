from __future__ import annotations

from urllib.parse import urlparse

from anti_geo.commercial_policy import assess_commercial_influence
from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.models import (
    CommercialInfluenceAssessment,
    ContestabilityReport,
    IndependenceReport,
    PassageProvenance,
    QueryContextScores,
    SourcePermissions,
    SourceScore,
    VisibilityReport,
)
from anti_geo.retrieval import ScoredChunk


def chunk_key(chunk: ScoredChunk) -> str:
    return f"{chunk.url}|{chunk.chunk_id}"


def _host(url: str) -> str:
    return urlparse(url).netloc or url


def _permissions_summary(perms: SourcePermissions | None) -> str:
    if not perms:
        return ""
    return (
        f"retrieve={perms.retrieve_permission}, "
        f"mention={perms.mention_permission}, "
        f"factual={perms.factual_permission}, "
        f"endorsement={perms.endorsement_permission}"
    )


def _exclusion_reasons(
    chunk: ScoredChunk,
    *,
    in_baseline: bool,
    in_defended: bool,
    commercial_tier: str,
    permissions: SourcePermissions | None,
    is_coordinated: bool,
    baseline_rank: int | None,
    defended_rank: int | None,
) -> list[str]:
    reasons: list[str] = []
    if in_baseline and not in_defended:
        if permissions and permissions.retrieve_permission == "downrank":
            reasons.append("low_trust_or_manipulation_risk")
        if commercial_tier in ("medium", "high"):
            reasons.append("commercial_influence")
        if is_coordinated:
            reasons.append("coordinated_cluster")
        if baseline_rank is not None and defended_rank is None:
            reasons.append("defense_rerank_excluded")
    elif in_baseline and in_defended and baseline_rank and defended_rank:
        if defended_rank > baseline_rank:
            reasons.append("downranked_by_defense")
    return reasons


def build_contestability_report(
    query: str,
    baseline_ranked: list[ScoredChunk],
    defended_ranked: list[ScoredChunk],
    baseline_pawc: VisibilityReport,
    defended_pawc: VisibilityReport,
    sources: dict[str, SourceScore],
    source_permissions: dict[str, SourcePermissions],
    commercial_assessments: dict[str, CommercialInfluenceAssessment],
    independence: IndependenceReport | None = None,
    query_context: QueryContextScores | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> ContestabilityReport:
    is_coordinated = (
        independence.is_likely_coordinated if independence else False
    ) or (query_context.consensus_integrity == "coordinated" if query_context else False)

    baseline_by_id = {chunk_key(c): (i + 1, c) for i, c in enumerate(baseline_ranked)}
    defended_by_id = {chunk_key(c): (i + 1, c) for i, c in enumerate(defended_ranked)}
    defended_ids = set(defended_by_id)

    included: list[PassageProvenance] = []
    for key, (rank, chunk) in defended_by_id.items():
        baseline_rank = baseline_by_id.get(key, (None, None))[0]
        src = sources.get(chunk.url)
        assessment = commercial_assessments.get(key)
        tier = assessment.tier if assessment else (
            src.page_context.commercial_tier if src and src.page_context else "none"
        )
        perms = source_permissions.get(chunk.url)
        included.append(
            PassageProvenance(
                chunk_id=chunk.chunk_id,
                url=chunk.url,
                host=_host(chunk.url),
                text_excerpt=chunk.text[:200],
                baseline_rank=baseline_rank,
                defended_rank=rank,
                status="included" if baseline_rank else "downranked",
                exclusion_reasons=_exclusion_reasons(
                    chunk,
                    in_baseline=key in baseline_by_id,
                    in_defended=True,
                    commercial_tier=tier,
                    permissions=perms,
                    is_coordinated=is_coordinated,
                    baseline_rank=baseline_rank,
                    defended_rank=rank,
                ),
                commercial_tier=tier,
                permissions_summary=_permissions_summary(perms),
            )
        )

    excluded_alternatives: list[PassageProvenance] = []
    for key, (rank, chunk) in baseline_by_id.items():
        if key in defended_ids:
            continue
        src = sources.get(chunk.url)
        perms = source_permissions.get(chunk.url)
        if src and src.page_context:
            tier = src.page_context.commercial_tier
        else:
            tier = "none"
        excluded_alternatives.append(
            PassageProvenance(
                chunk_id=chunk.chunk_id,
                url=chunk.url,
                host=_host(chunk.url),
                text_excerpt=chunk.text[:200],
                baseline_rank=rank,
                defended_rank=None,
                status="excluded",
                exclusion_reasons=_exclusion_reasons(
                    chunk,
                    in_baseline=True,
                    in_defended=False,
                    commercial_tier=tier,
                    permissions=perms,
                    is_coordinated=is_coordinated,
                    baseline_rank=rank,
                    defended_rank=None,
                ),
                commercial_tier=tier,
                permissions_summary=_permissions_summary(perms),
            )
        )
    excluded_alternatives.sort(key=lambda p: p.baseline_rank or 99)
    excluded_alternatives = excluded_alternatives[:5]

    dominance_delta = defended_pawc.dominant_share - baseline_pawc.dominant_share

    return ContestabilityReport(
        query=query,
        included=included,
        excluded_alternatives=excluded_alternatives,
        baseline_pawc=baseline_pawc,
        defended_pawc=defended_pawc,
        dominance_delta=dominance_delta,
        alternative_pools_available=len(excluded_alternatives) > 0,
    )


def contestability_to_json(report: ContestabilityReport) -> dict:
    def _passage(p: PassageProvenance) -> dict:
        return {
            "chunk_id": p.chunk_id,
            "url": p.url,
            "host": p.host,
            "text_excerpt": p.text_excerpt,
            "baseline_rank": p.baseline_rank,
            "defended_rank": p.defended_rank,
            "status": p.status,
            "exclusion_reasons": p.exclusion_reasons,
            "commercial_tier": p.commercial_tier,
            "permissions_summary": p.permissions_summary,
        }

    return {
        "query": report.query,
        "included": [_passage(p) for p in report.included],
        "excluded_alternatives": [_passage(p) for p in report.excluded_alternatives],
        "dominance_delta": report.dominance_delta,
        "alternative_pools_available": report.alternative_pools_available,
        "baseline_dominant_host": report.baseline_pawc.dominant_host if report.baseline_pawc else "",
        "defended_dominant_host": report.defended_pawc.dominant_host if report.defended_pawc else "",
    }


def format_contestability_report(report: ContestabilityReport) -> str:
    lines = [
        "── Contestability ──",
        f"  Alternative pools available: {report.alternative_pools_available}",
        f"  Dominance delta (defended - baseline): {report.dominance_delta:.1f}%",
        "",
        "  Included passages:",
    ]
    for p in report.included:
        lines.append(
            f"    [{p.defended_rank}] {p.url} (baseline={p.baseline_rank}, tier={p.commercial_tier})"
        )
        if p.exclusion_reasons:
            lines.append(f"      reasons: {', '.join(p.exclusion_reasons)}")
    if report.excluded_alternatives:
        lines.append("")
        lines.append("  Excluded alternatives (high baseline rank):")
        for p in report.excluded_alternatives:
            lines.append(f"    [baseline={p.baseline_rank}] {p.url} (tier={p.commercial_tier})")
            if p.exclusion_reasons:
                lines.append(f"      reasons: {', '.join(p.exclusion_reasons)}")
    return "\n".join(lines)


def assess_chunks_commercial(
    defended_ranked: list[ScoredChunk],
    sources: dict[str, SourceScore],
    source_permissions: dict[str, SourcePermissions],
    query: str,
    query_intent: str,
    *,
    is_coordinated: bool = False,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> dict[str, CommercialInfluenceAssessment]:
    assessments: dict[str, CommercialInfluenceAssessment] = {}
    for i, chunk in enumerate(defended_ranked, 1):
        src = sources.get(chunk.url)
        if not src:
            continue
        perms = source_permissions.get(chunk.url)
        if not perms:
            continue
        assessments[chunk_key(chunk)] = assess_commercial_influence(
            src,
            chunk.text,
            query,
            query_intent,
            perms,
            config,
            is_coordinated=is_coordinated,
            defended_rank=i,
        )
    return assessments
