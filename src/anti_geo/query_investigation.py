"""Mode A — search query → engine cites → per-cite actions (+ Mode B for non-UGC)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

from anti_geo.audit.engines import EngineAdapter, get_engine
from anti_geo.decisions import decide_single_source, extract_shared_claim
from anti_geo.fetch import fetch_page
from anti_geo.independence import analyze_independence
from anti_geo.investigation import (
    ReferralProfile,
    investigate_url,
    ugc_share_from_mix,
)
from anti_geo.models import (
    GuardResult,
    IndependenceReport,
    SourceScore,
    UrlAnalysisReport,
)
from anti_geo.permissions import derive_llm_actions
from anti_geo.pipeline import _format_subscores_permissions
from anti_geo.platform_role import classify_content_role, is_ugc_role
from anti_geo.progress import NullProgress, Progress
from anti_geo.retrieval import ScoredChunk
from anti_geo.scorer import score_source
from anti_geo.synthesis_guard import apply_synthesis_guard

# Mode A fast defaults (forensics / --deep uses Mode B CLI caps).
DEFAULT_SITE_WORKERS = 3
DEFAULT_SEED_LIMIT = 5
DEFAULT_MAX_VERIFIED = 15
DEFAULT_MAX_FETCHES_PER_SEED = 12
DEFAULT_MIN_SEEDS_BEFORE_STOP = 3
DEFAULT_CITE_CAP = 15
DEEP_SEED_LIMIT = 12
DEEP_MAX_VERIFIED = 50
DEEP_MAX_FETCHES_PER_SEED = 30
DEEP_MIN_SEEDS_BEFORE_STOP = 4


@dataclass
class CiteInvestigationRow:
    url: str
    is_ugc: bool
    content_role: str
    llm_action: str
    llm_actions: list[str]
    source_trust: float
    endorsement_risk: float
    single_page: UrlAnalysisReport
    referral_profile: ReferralProfile | None = None
    n_verified: int | None = None
    ugc_verified_share: float | None = None
    ugc_verified_count: int | None = None
    mode_b_error: str | None = None


@dataclass
class QueryInvestigationResult:
    query: str
    query_intent: str
    cited_urls: list[str]
    rows: list[CiteInvestigationRow]
    independence: IndependenceReport | None
    guard: GuardResult | None
    claim_entity: str | None
    site_workers: int
    ugc_skipped: int
    mode_b_ran: int
    notes: list[str] = field(default_factory=list)


def _dedupe_urls(urls: list[str], *, cap: int = DEFAULT_CITE_CAP) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        norm = url.rstrip("/").lower()
        if not url or norm in seen:
            continue
        seen.add(norm)
        out.append(url)
        if len(out) >= cap:
            break
    return out


def _llm_actions_for_report(report: UrlAnalysisReport) -> tuple[str, list[str]]:
    if report.permissions and report.subscores:
        return derive_llm_actions(report.permissions, report.subscores)
    return report.recommended_action, [report.recommended_action]


def _score_cite(
    url: str,
    *,
    query: str,
    query_intent: str,
) -> tuple[UrlAnalysisReport, str, bool]:
    fetch = fetch_page(url)
    source = score_source(url, fetch, query=query)
    report = decide_single_source(source, query_intent, query=query)
    role = classify_content_role(url, fetch=fetch, source=source)
    return report, role, is_ugc_role(role)


def _row_from_report(
    report: UrlAnalysisReport,
    *,
    role: str,
    is_ugc: bool,
    profile: ReferralProfile | None = None,
    mode_b_error: str | None = None,
) -> CiteInvestigationRow:
    primary, actions = _llm_actions_for_report(report)
    trust = report.source.trust_score
    endorsement = (
        report.subscores.endorsement_risk
        if report.subscores
        else report.endorsement_risk
    )
    n_verified: int | None = None
    ugc_share: float | None = None
    ugc_count: int | None = None
    if profile is not None and profile.status != "skipped":
        n_verified = profile.n_verified
        ugc_count = profile.mix.get("ugc_thread", 0)
        ugc_share = ugc_share_from_mix(profile.mix, profile.n_verified)

    return CiteInvestigationRow(
        url=report.source.url,
        is_ugc=is_ugc,
        content_role=role,
        llm_action=primary,
        llm_actions=actions,
        source_trust=trust,
        endorsement_risk=endorsement,
        single_page=report,
        referral_profile=profile,
        n_verified=n_verified,
        ugc_verified_share=ugc_share,
        ugc_verified_count=ugc_count,
        mode_b_error=mode_b_error,
    )


def _run_mode_b_for_cite(
    url: str,
    *,
    query: str,
    query_intent: str,
    engine: EngineAdapter | None,
    engine_name: str | None,
    fixture_path: Path | None,
    seed_limit: int,
    seed_mode: str,
    query_delay_s: float,
    max_fetches_per_seed: int,
    max_verified_referrers: int,
    min_seeds_before_verified_stop: int,
    seed_workers: int,
    fetch_workers: int,
    adaptive_stop: bool,
) -> CiteInvestigationRow:
    result = investigate_url(
        url,
        query_intent=query_intent,
        query=query,
        engine_name=None if engine is not None else engine_name,
        engine=engine,
        seed_limit=seed_limit,
        seed_mode=seed_mode,
        fixture_path=fixture_path,
        query_delay_s=query_delay_s,
        max_fetches_per_seed=max_fetches_per_seed,
        max_verified_referrers=max_verified_referrers,
        min_seeds_before_verified_stop=min_seeds_before_verified_stop,
        seed_workers=seed_workers,
        fetch_workers=fetch_workers,
        adaptive_stop=adaptive_stop,
        progress=NullProgress(),
    )
    return _row_from_report(
        result.single_page,
        role=result.content_role,
        is_ugc=False,
        profile=result.referral_profile,
    )


def _build_ranked_chunks(
    rows: list[CiteInvestigationRow],
) -> list[ScoredChunk]:
    ranked: list[ScoredChunk] = []
    for i, row in enumerate(rows):
        src = row.single_page.source
        text = src.text_excerpt or ""
        if not text:
            continue
        ranked.append(
            ScoredChunk(
                chunk_id=f"cite_{i}__main_0",
                url=row.url,
                text=text,
                base_score=1.0 / (i + 1),
                trust_score=src.trust_score,
                semantic_risk=src.semantic_risk,
                endorsement_risk=row.endorsement_risk,
                combined_score=1.0 / (i + 1),
                recommended_action="pass",
            )
        )
    return ranked


def investigate_query(
    query: str,
    *,
    query_intent: str = "commercial",
    engine_name: str = "mock",
    fixture_path: Path | None = None,
    engine: EngineAdapter | None = None,
    site_workers: int = DEFAULT_SITE_WORKERS,
    seed_workers: int = 4,
    fetch_workers: int = 8,
    seed_limit: int = DEFAULT_SEED_LIMIT,
    seed_mode: str = "auto",
    query_delay_s: float = 0.0,
    max_fetches_per_seed: int = DEFAULT_MAX_FETCHES_PER_SEED,
    max_verified_referrers: int = DEFAULT_MAX_VERIFIED,
    min_seeds_before_verified_stop: int = DEFAULT_MIN_SEEDS_BEFORE_STOP,
    adaptive_stop: bool = True,
    cite_cap: int = DEFAULT_CITE_CAP,
    progress: Progress | None = None,
    deep: bool = False,
) -> QueryInvestigationResult:
    """Mode A: query → cites → L1-L3 all; Mode B only for non-UGC (parallel)."""
    prog = progress or NullProgress()
    if deep:
        seed_limit = DEEP_SEED_LIMIT
        max_verified_referrers = DEEP_MAX_VERIFIED
        max_fetches_per_seed = DEEP_MAX_FETCHES_PER_SEED
        min_seeds_before_verified_stop = DEEP_MIN_SEEDS_BEFORE_STOP
        adaptive_stop = False

    resolved = engine or get_engine(engine_name, fixture_path=fixture_path)
    prog.set_status("engine query for citations")
    resp = resolved.query(query)
    cited_urls = _dedupe_urls(resp.cited_urls, cap=cite_cap)
    notes: list[str] = []
    if not cited_urls:
        notes.append("Engine returned no cited URLs.")
        return QueryInvestigationResult(
            query=query,
            query_intent=query_intent,
            cited_urls=[],
            rows=[],
            independence=None,
            guard=None,
            claim_entity=None,
            site_workers=site_workers,
            ugc_skipped=0,
            mode_b_ran=0,
            notes=notes,
        )

    prog.set_counts(0, len(cited_urls), status="score citations")
    non_ugc_urls: list[str] = []
    row_by_url: dict[str, CiteInvestigationRow] = {}
    reports: list[UrlAnalysisReport] = []
    sources_by_url: dict[str, SourceScore] = {}

    for i, url in enumerate(cited_urls):
        prog.set_counts(i, len(cited_urls), status=f"score cite {i + 1}/{len(cited_urls)}")
        report, role, is_ugc = _score_cite(url, query=query, query_intent=query_intent)
        reports.append(report)
        sources_by_url[report.source.url] = report.source
        if is_ugc:
            row = _row_from_report(
                report,
                role=role,
                is_ugc=True,
                profile=ReferralProfile(
                    status="skipped",
                    discovery_status="skipped",
                    confidence="low",
                    notes=["Mode B skipped for UGC cite."],
                ),
            )
            row_by_url[report.source.url] = row
        else:
            non_ugc_urls.append(report.source.url)
    prog.set_counts(len(cited_urls), len(cited_urls), status="citations scored")

    site_workers = max(1, min(site_workers, len(non_ugc_urls) or 1))
    mode_b_errors: dict[str, str] = {}

    if non_ugc_urls and resolved is not None:
        prog.set_status(
            f"Mode B on {len(non_ugc_urls)} non-UGC · site_workers={site_workers}"
        )

        def _job(url: str) -> tuple[str, CiteInvestigationRow | None, str | None]:
            try:
                row = _run_mode_b_for_cite(
                    url,
                    query=query,
                    query_intent=query_intent,
                    engine=resolved,
                    engine_name=engine_name,
                    fixture_path=fixture_path,
                    seed_limit=seed_limit,
                    seed_mode=seed_mode,
                    query_delay_s=query_delay_s,
                    max_fetches_per_seed=max_fetches_per_seed,
                    max_verified_referrers=max_verified_referrers,
                    min_seeds_before_verified_stop=min_seeds_before_verified_stop,
                    seed_workers=seed_workers,
                    fetch_workers=fetch_workers,
                    adaptive_stop=adaptive_stop,
                )
                return url, row, None
            except Exception as exc:
                return url, None, str(exc)

        with ThreadPoolExecutor(max_workers=site_workers) as pool:
            futures = [pool.submit(_job, u) for u in non_ugc_urls]
            for fut in as_completed(futures):
                url, row, err = fut.result()
                if row is not None:
                    row_by_url[row.url] = row
                    # Prefer Mode B single-page scores for sources map.
                    sources_by_url[row.url] = row.single_page.source
                elif err:
                    mode_b_errors[url] = err
                    # Fall back to pre-scored cite row without referral.
                    pre = next(
                        (r for r in reports if r.source.url.rstrip("/").lower()
                         == url.rstrip("/").lower()),
                        None,
                    )
                    if pre:
                        role = classify_content_role(url, source=pre.source)
                        row_by_url[pre.source.url] = _row_from_report(
                            pre,
                            role=role,
                            is_ugc=False,
                            mode_b_error=err,
                        )

    elif non_ugc_urls:
        notes.append("No engine — Mode B skipped for non-UGC cites.")
        for url in non_ugc_urls:
            pre = next(
                (r for r in reports if r.source.url.rstrip("/").lower()
                 == url.rstrip("/").lower()),
                None,
            )
            if pre:
                role = classify_content_role(url, source=pre.source)
                row_by_url[pre.source.url] = _row_from_report(
                    pre, role=role, is_ugc=False
                )

    # Preserve citation order.
    ordered_rows: list[CiteInvestigationRow] = []
    for url in cited_urls:
        match = next(
            (
                row_by_url[k]
                for k in row_by_url
                if k.rstrip("/").lower() == url.rstrip("/").lower()
            ),
            None,
        )
        if match:
            ordered_rows.append(match)

    url_texts = {
        s.url: s.text_excerpt for s in sources_by_url.values() if s.text_excerpt
    }
    independence = analyze_independence(url_texts) if len(url_texts) >= 2 else None
    claim_entity = extract_shared_claim(list(sources_by_url.values()))
    ranked = _build_ranked_chunks(ordered_rows)
    source_permissions = {
        row.url: row.single_page.permissions
        for row in ordered_rows
        if row.single_page.permissions is not None
    }
    guard = None
    if ranked:
        guard = apply_synthesis_guard(
            query,
            ranked,
            sources_by_url,
            query_intent,
            attack_entity=claim_entity,
            source_permissions=source_permissions,
        )

    ugc_skipped = sum(1 for r in ordered_rows if r.is_ugc)
    mode_b_ran = sum(
        1
        for r in ordered_rows
        if not r.is_ugc
        and r.referral_profile is not None
        and r.referral_profile.status != "skipped"
    )
    notes.append(
        f"Mode B skipped for {ugc_skipped} UGC cites; "
        f"ran on {mode_b_ran} non-UGC (site_workers={site_workers})."
    )
    if mode_b_errors:
        notes.append(f"Mode B errors: {len(mode_b_errors)}")

    prog.close(final_status=f"done · cites={len(ordered_rows)}")
    return QueryInvestigationResult(
        query=query,
        query_intent=query_intent,
        cited_urls=cited_urls,
        rows=ordered_rows,
        independence=independence,
        guard=guard,
        claim_entity=claim_entity,
        site_workers=site_workers,
        ugc_skipped=ugc_skipped,
        mode_b_ran=mode_b_ran,
        notes=notes,
    )


def format_query_investigation_report(
    result: QueryInvestigationResult,
    *,
    verbose: bool = False,
) -> str:
    lines = [
        "=" * 60,
        "ANTI-GEO INVESTIGATION (Mode A — query)",
        "=" * 60,
        f"Query: {result.query}",
        f"Intent: {result.query_intent}",
        f"Citations: {len(result.rows)}",
    ]
    if result.claim_entity:
        lines.append(f"Claim entity: {result.claim_entity}")
    lines.append("")
    lines.append("── Sources ──")

    for i, row in enumerate(result.rows, start=1):
        tag = "ugc" if row.is_ugc else "non-ugc"
        lines.append(f"{i}. [{tag}] {row.url}")
        lines.append(
            f"   role={row.content_role}  "
            f"trust={row.source_trust:.2f}  "
            f"endorsement_risk={row.endorsement_risk:.2f}"
        )
        if not row.is_ugc:
            if row.n_verified is not None:
                if row.ugc_verified_share is not None and row.ugc_verified_count is not None:
                    pct = int(round(row.ugc_verified_share * 100))
                    lines.append(f"   Verified connections: {row.n_verified}")
                    lines.append(
                        f"   UGC among verified: {pct}% "
                        f"({row.ugc_verified_count}/{row.n_verified})"
                    )
                else:
                    lines.append(f"   Verified connections: {row.n_verified}")
            elif row.mode_b_error:
                lines.append(f"   Mode B error: {row.mode_b_error}")
            else:
                lines.append("   Verified connections: (skipped / unavailable)")
        lines.append(f"   LLM action: {row.llm_action}")
        if verbose:
            lines.extend(
                "   " + ln if ln else ln
                for ln in _format_subscores_permissions(row.single_page)
            )
        lines.append("")

    lines.append("── Cluster risk ──")
    if result.independence:
        ind = result.independence
        lines.append(
            f"  cluster_count={ind.cluster_count}  "
            f"max_sim={ind.max_cluster_similarity:.3f}  "
            f"coordinated={ind.is_likely_coordinated}"
        )
        if ind.reasons:
            lines.append(f"  reasons: {', '.join(ind.reasons)}")
    else:
        lines.append("  (insufficient texts for independence clustering)")

    if result.guard:
        actions = ", ".join(result.guard.actions) if result.guard.actions else "(none)"
        lines.append(f"  Guard actions: {actions}")
        lines.append(f"  Query response mode: {result.guard.response_mode}")
    else:
        lines.append("  Guard: (not run)")

    lines.append("")
    lines.append("── Notes ──")
    for note in result.notes:
        lines.append(f"  {note}")

    return "\n".join(lines)


def query_investigation_to_dict(result: QueryInvestigationResult) -> dict:
    rows = []
    for row in result.rows:
        entry = {
            "url": row.url,
            "is_ugc": row.is_ugc,
            "content_role": row.content_role,
            "llm_action": row.llm_action,
            "llm_actions": row.llm_actions,
            "source_trust": row.source_trust,
            "endorsement_risk": row.endorsement_risk,
            "n_verified": row.n_verified,
            "ugc_verified_share": row.ugc_verified_share,
            "ugc_verified_count": row.ugc_verified_count,
            "mode_b_error": row.mode_b_error,
            "subscores": asdict(row.single_page.subscores)
            if row.single_page.subscores
            else None,
            "permissions": asdict(row.single_page.permissions)
            if row.single_page.permissions
            else None,
            "referral_profile": None,
        }
        if row.referral_profile is not None:
            rp = row.referral_profile
            entry["referral_profile"] = {
                **asdict(rp),
                "referrers_verified": [asdict(r) for r in rp.referrers_verified],
                "semantic_alignment": asdict(rp.semantic_alignment)
                if rp.semantic_alignment
                else None,
            }
        rows.append(entry)

    return {
        "query": result.query,
        "query_intent": result.query_intent,
        "cited_urls": result.cited_urls,
        "claim_entity": result.claim_entity,
        "site_workers": result.site_workers,
        "ugc_skipped": result.ugc_skipped,
        "mode_b_ran": result.mode_b_ran,
        "notes": result.notes,
        "rows": rows,
        "independence": asdict(result.independence) if result.independence else None,
        "guard": {
            "utterance_type": result.guard.utterance_type,
            "corroborated": result.guard.corroborated,
            "actions": result.guard.actions,
            "response_mode": result.guard.response_mode,
            "safe_answer": result.guard.safe_answer,
        }
        if result.guard
        else None,
    }
