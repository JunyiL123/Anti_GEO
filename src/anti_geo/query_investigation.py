"""Mode A — search query → engine cites → L1-L3 + L3 independence.

Non-UGC cites may run Mode B structural referral mix (parasitic-surface proportions),
which can tighten LLM actions. Referrers are not re-scored with L1-L2.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from anti_geo.audit.engines import EngineAdapter, get_engine
from anti_geo.decisions import decide_single_source
from anti_geo.claim_entity import resolve_claim_entity
from anti_geo.fetch import fetch_page
from anti_geo.independence import analyze_independence
from anti_geo.investigation import (
    ReferralProfile,
    investigate_url,
    parasitic_count_from_verified,
    parasitic_share_from_verified,
    tighten_actions_with_referral,
)
from anti_geo.models import (
    FetchResult,
    GuardResult,
    IndependenceReport,
    SourceScore,
    UrlAnalysisReport,
)
from anti_geo.permissions import apply_ugc_site_cite_policy, derive_llm_actions
from anti_geo.pipeline import _format_subscores_permissions
from anti_geo.platform_role import classify_content_role, is_ugc_role
from anti_geo.progress import NullProgress, Progress
from anti_geo.query_intent import resolve_query_intent
from anti_geo.retrieval import ScoredChunk
from anti_geo.scorer import score_source
from anti_geo.synthesis_guard import apply_synthesis_guard

# Mode A fast defaults (forensics / --deep uses Mode B CLI caps).
# site_workers can be high; Azure peak concurrency is capped in azure_client.
DEFAULT_SITE_WORKERS = 8
DEFAULT_SEED_LIMIT = 12
DEFAULT_MAX_VERIFIED = 15
DEFAULT_MAX_FETCHES_PER_SEED = 30
DEFAULT_MIN_SEEDS_BEFORE_STOP = 3
DEFAULT_CITE_CAP: int | None = None  # None = keep every unique engine citation
# When every answer citation is hard-rejected, refill from the grounding pool.
POOL_FALLBACK_MIN_USABLE = 3  # typical AI answers cite ~3–8; aim for a small usable floor
POOL_FALLBACK_TRY = 8  # max pool URLs to attempt before giving up
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
    parasitic_verified_share: float | None = None
    parasitic_verified_count: int | None = None
    mode_b_error: str | None = None
    from_source_pool: bool = False


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
    intent_source: str = "manual"
    intent_rule: str | None = None


def _dedupe_urls(urls: list[str], *, cap: int | None = DEFAULT_CITE_CAP) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        norm = url.rstrip("/").lower()
        if not url or norm in seen:
            continue
        seen.add(norm)
        out.append(url)
        if cap is not None and len(out) >= cap:
            break
    return out


def _llm_actions_for_report(report: UrlAnalysisReport) -> tuple[str, list[str]]:
    if report.permissions and report.subscores:
        return derive_llm_actions(report.permissions, report.subscores)
    return report.recommended_action, [report.recommended_action]


def _cite_is_completely_rejected(report: UrlAnalysisReport) -> bool:
    """True when the LLM must not mention the source at all."""
    if report.permissions and report.permissions.mention_permission == "deny":
        return True
    primary, _ = _llm_actions_for_report(report)
    return primary == "reject"


def _cite_is_usable(report: UrlAnalysisReport) -> bool:
    """False only for complete rejection (no mention allowed)."""
    return not _cite_is_completely_rejected(report)


def _norm_url(url: str) -> str:
    return url.rstrip("/").lower()


def _score_cite(
    url: str,
    *,
    query: str,
    query_intent: str,
) -> tuple[UrlAnalysisReport, str, bool, FetchResult]:
    fetch = fetch_page(url)
    source = score_source(url, fetch, query=query)
    report = decide_single_source(source, query_intent, query=query)
    role = classify_content_role(url, fetch=fetch, source=source)
    return report, role, is_ugc_role(role), fetch


def _row_from_report(
    report: UrlAnalysisReport,
    *,
    role: str,
    is_ugc: bool,
    profile: ReferralProfile | None = None,
    mode_b_error: str | None = None,
    from_source_pool: bool = False,
) -> CiteInvestigationRow:
    working = report
    if is_ugc and report.permissions is not None:
        tightened = apply_ugc_site_cite_policy(report.permissions)
        primary_pre, _ = derive_llm_actions(tightened, report.subscores)
        working = replace(
            report,
            permissions=tightened,
            recommended_action=primary_pre,
        )
    primary, actions = _llm_actions_for_report(working)
    # Structural referral mix may tighten; never from referrer L1-L2 scores.
    primary, actions = tighten_actions_with_referral(
        primary,
        actions,
        profile,
        content_role=role,
        engine_cited=True,
    )
    trust = working.source.trust_score
    endorsement = (
        working.subscores.endorsement_risk
        if working.subscores
        else working.endorsement_risk
    )
    n_verified: int | None = None
    parasitic_share: float | None = None
    parasitic_count: int | None = None
    if profile is not None and profile.status != "skipped":
        n_verified = profile.n_verified
        parasitic_count = parasitic_count_from_verified(profile.referrers_verified)
        parasitic_share = parasitic_share_from_verified(profile.referrers_verified)

    return CiteInvestigationRow(
        url=working.source.url,
        is_ugc=is_ugc,
        content_role=role,
        llm_action=primary,
        llm_actions=actions,
        source_trust=trust,
        endorsement_risk=endorsement,
        single_page=working,
        referral_profile=profile,
        n_verified=n_verified,
        parasitic_verified_share=parasitic_share,
        parasitic_verified_count=parasitic_count,
        mode_b_error=mode_b_error,
        from_source_pool=from_source_pool,
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
    use_llm_connection: bool | None = None,
    use_llm_role: bool | None = None,
    fetch: FetchResult | None = None,
    single_page: UrlAnalysisReport | None = None,
    content_role: str | None = None,
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
        use_llm_connection=use_llm_connection,
        use_llm_role=use_llm_role,
        progress=NullProgress(),
        fetch=fetch,
        single_page=single_page,
        content_role=content_role,
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
    query_intent: str = "auto",
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
    use_llm_connection: bool | None = None,
    use_llm_role: bool | None = None,
    cite_cap: int | None = DEFAULT_CITE_CAP,
    progress: Progress | None = None,
    deep: bool = False,
) -> QueryInvestigationResult:
    """Mode A: query → cites → L1-L3 all; Mode B only for non-UGC (parallel)."""
    prog = progress or NullProgress()
    intent_hit = resolve_query_intent(query, query_intent)
    query_intent = intent_hit.intent
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
    source_pool = _dedupe_urls(getattr(resp, "source_pool_urls", None) or [], cap=None)
    notes: list[str] = []
    if intent_hit.source != "manual":
        rule = f", rule={intent_hit.matched_rule}" if intent_hit.matched_rule else ""
        notes.append(f"Intent resolved via {intent_hit.source}{rule}.")
    if not cited_urls and source_pool:
        cited_urls = source_pool[:POOL_FALLBACK_TRY]
        notes.append(
            f"No answer citations; starting from grounding pool "
            f"({len(cited_urls)} of {len(source_pool)})."
        )
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
            intent_source=intent_hit.source,
            intent_rule=intent_hit.matched_rule,
        )

    prog.set_counts(0, len(cited_urls), status="score citations")
    non_ugc_urls: list[str] = []
    row_by_url: dict[str, CiteInvestigationRow] = {}
    reports: list[UrlAnalysisReport] = []
    sources_by_url: dict[str, SourceScore] = {}
    # Mode A fetch/role cache → Mode B reuses (no second target fetch/score).
    scored_cache: dict[str, tuple[FetchResult, UrlAnalysisReport, str]] = {}
    tried_norms: set[str] = {_norm_url(u) for u in cited_urls}

    def _cache_scored(
        url: str,
        fetch: FetchResult,
        report: UrlAnalysisReport,
        role: str,
    ) -> None:
        scored_cache[url] = (fetch, report, role)
        scored_cache[report.source.url] = (fetch, report, role)
        scored_cache[_norm_url(url)] = (fetch, report, role)
        scored_cache[_norm_url(report.source.url)] = (fetch, report, role)

    def _lookup_scored(
        url: str,
    ) -> tuple[FetchResult, UrlAnalysisReport, str] | None:
        return (
            scored_cache.get(url)
            or scored_cache.get(_norm_url(url))
        )

    def _score_batch(
        urls: list[str],
        *,
        label: str,
        from_pool: bool = False,
    ) -> list[tuple[UrlAnalysisReport, str, bool]]:
        if not urls:
            return []
        workers = max(1, min(site_workers, len(urls)))
        results: list[tuple[int, UrlAnalysisReport, str, bool, FetchResult]] = []

        def _one(
            idx_url: tuple[int, str],
        ) -> tuple[int, UrlAnalysisReport, str, bool, FetchResult]:
            idx, url = idx_url
            report, role, is_ugc, fetch = _score_cite(
                url, query=query, query_intent=query_intent
            )
            return idx, report, role, is_ugc, fetch

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_one, (i, u)): i for i, u in enumerate(urls)}
            done_n = 0
            for fut in as_completed(futures):
                results.append(fut.result())
                done_n += 1
                prog.set_counts(
                    done_n,
                    len(urls),
                    status=f"{label} {done_n}/{len(urls)} (parallel={workers})",
                )
        results.sort(key=lambda row: row[0])
        out: list[tuple[UrlAnalysisReport, str, bool]] = []
        for idx, report, role, is_ugc, fetch in results:
            reports.append(report)
            sources_by_url[report.source.url] = report.source
            _cache_scored(urls[idx], fetch, report, role)
            if is_ugc:
                row_by_url[report.source.url] = _row_from_report(
                    report,
                    role=role,
                    is_ugc=True,
                    profile=ReferralProfile(
                        status="skipped",
                        discovery_status="skipped",
                        confidence="low",
                        notes=["Mode B skipped for UGC cite."],
                    ),
                    from_source_pool=from_pool,
                )
            else:
                non_ugc_urls.append(report.source.url)
                # Placeholder until Mode B (or keep L1-L3 row if Mode B skipped)
                if report.source.url not in row_by_url:
                    row_by_url[report.source.url] = _row_from_report(
                        report,
                        role=role,
                        is_ugc=False,
                        from_source_pool=from_pool,
                    )
            out.append((report, role, is_ugc))
        return out

    answer_scored = _score_batch(cited_urls, label="score cites")
    usable_n = sum(1 for report, _, _ in answer_scored if _cite_is_usable(report))
    prog.set_counts(len(cited_urls), len(cited_urls), status="citations scored")

    if usable_n == 0 and source_pool:
        pool_candidates = [
            u for u in source_pool if _norm_url(u) not in tried_norms
        ][:POOL_FALLBACK_TRY]
        if pool_candidates:
            notes.append(
                f"All {len(cited_urls)} answer citations completely rejected "
                f"(mention denied); trying grounding pool "
                f"(aim ≥{POOL_FALLBACK_MIN_USABLE} usable, try ≤{len(pool_candidates)})."
            )
            # Score pool in small waves so we can stop once we hit the usable floor.
            pool_usable = 0
            offset = 0
            wave = max(1, site_workers)
            while (
                offset < len(pool_candidates)
                and pool_usable < POOL_FALLBACK_MIN_USABLE
            ):
                batch = pool_candidates[offset : offset + wave]
                offset += len(batch)
                for u in batch:
                    tried_norms.add(_norm_url(u))
                    if u not in cited_urls:
                        cited_urls.append(u)
                batch_scored = _score_batch(
                    batch, label="pool fallback", from_pool=True
                )
                pool_usable += sum(
                    1 for report, _, _ in batch_scored if _cite_is_usable(report)
                )
            notes.append(
                f"Pool fallback yielded {pool_usable} usable "
                f"after trying {min(offset, len(pool_candidates))} URLs."
            )
        else:
            notes.append(
                "All answer citations completely rejected (mention denied); "
                "grounding pool empty or exhausted."
            )
    elif usable_n == 0:
        notes.append(
            "All answer citations completely rejected (mention denied); "
            "no grounding pool available."
        )
    # Mode B only for usable non-UGC (rejected answer cites stay L1-L3 only).
    mode_b_targets = [
        u
        for u in non_ugc_urls
        if any(
            _norm_url(r.source.url) == _norm_url(u) and _cite_is_usable(r)
            for r in reports
        )
    ]
    # Preserve order, unique
    seen_mb: set[str] = set()
    mode_b_targets_ordered: list[str] = []
    for u in mode_b_targets:
        n = _norm_url(u)
        if n not in seen_mb:
            seen_mb.add(n)
            mode_b_targets_ordered.append(u)
    non_ugc_urls = mode_b_targets_ordered

    site_workers = max(1, min(site_workers, len(non_ugc_urls) or 1))
    mode_b_errors: dict[str, str] = {}

    if non_ugc_urls and resolved is not None:
        prog.set_counts(
            0,
            len(non_ugc_urls),
            status=f"Mode B 0/{len(non_ugc_urls)} non-UGC · workers={site_workers}",
        )

        def _job(url: str) -> tuple[str, CiteInvestigationRow | None, str | None]:
            try:
                cached = _lookup_scored(url)
                pre_fetch = cached[0] if cached else None
                pre_report = cached[1] if cached else None
                pre_role = cached[2] if cached else None
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
                    use_llm_connection=use_llm_connection,
                    use_llm_role=use_llm_role,
                    fetch=pre_fetch,
                    single_page=pre_report,
                    content_role=pre_role,
                )
                # Preserve from_source_pool flag from pre-score row if present.
                prior = row_by_url.get(url) or next(
                    (
                        row_by_url[k]
                        for k in row_by_url
                        if _norm_url(k) == _norm_url(url)
                    ),
                    None,
                )
                if prior and prior.from_source_pool:
                    row = replace(row, from_source_pool=True)
                return url, row, None
            except Exception as exc:
                return url, None, str(exc)

        mode_b_done = 0
        with ThreadPoolExecutor(max_workers=site_workers) as pool:
            futures = [pool.submit(_job, u) for u in non_ugc_urls]
            for fut in as_completed(futures):
                url, row, err = fut.result()
                mode_b_done += 1
                prog.set_counts(
                    mode_b_done,
                    len(non_ugc_urls),
                    status=(
                        f"Mode B {mode_b_done}/{len(non_ugc_urls)} non-UGC "
                        f"· workers={site_workers}"
                    ),
                )
                if row is not None:
                    row_by_url[row.url] = row
                    sources_by_url[row.url] = row.single_page.source
                elif err:
                    mode_b_errors[url] = err
                    pre = next(
                        (
                            r
                            for r in reports
                            if _norm_url(r.source.url) == _norm_url(url)
                        ),
                        None,
                    )
                    if pre:
                        role = classify_content_role(url, source=pre.source)
                        prior = row_by_url.get(pre.source.url)
                        row_by_url[pre.source.url] = _row_from_report(
                            pre,
                            role=role,
                            is_ugc=False,
                            mode_b_error=err,
                            from_source_pool=bool(prior and prior.from_source_pool),
                        )

    elif non_ugc_urls:
        notes.append("No engine — Mode B skipped for non-UGC cites.")
        for url in non_ugc_urls:
            pre = next(
                (r for r in reports if _norm_url(r.source.url) == _norm_url(url)),
                None,
            )
            if pre and pre.source.url not in row_by_url:
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

    usable_rows = [r for r in ordered_rows if _cite_is_usable(r.single_page)]
    guard_rows = usable_rows if usable_rows else ordered_rows
    url_texts = {
        r.url: r.single_page.source.text_excerpt
        for r in guard_rows
        if r.single_page.source.text_excerpt
    }
    independence = analyze_independence(url_texts) if len(url_texts) >= 2 else None
    claim_entity = resolve_claim_entity(
        [r.single_page.source for r in guard_rows],
        query=query,
        query_intent=query_intent,
        content_roles=[r.content_role for r in guard_rows],
        use_llm=None,
    )
    ranked = _build_ranked_chunks(guard_rows)
    source_permissions = {
        row.url: row.single_page.permissions
        for row in guard_rows
        if row.single_page.permissions is not None
    }
    sources_for_guard = {r.url: r.single_page.source for r in guard_rows}
    guard = None
    if ranked:
        guard = apply_synthesis_guard(
            query,
            ranked,
            sources_for_guard,
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
    notes.append(
        "Per-cite actions: L1-L3, optionally tightened by Mode B structural "
        "parasitic-surface/editorial mix; L3 independence runs on the cite set."
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
        intent_source=intent_hit.source,
        intent_rule=intent_hit.matched_rule,
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
        f"Intent: {result.query_intent} ({result.intent_source}"
        + (f", {result.intent_rule}" if result.intent_rule else "")
        + ")",
        f"Citations: {len(result.rows)}",
    ]
    if result.claim_entity:
        lines.append(f"Claim entity: {result.claim_entity}")
    lines.append("")
    lines.append("── Sources ──")

    for i, row in enumerate(result.rows, start=1):
        tag = "ugc" if row.is_ugc else "non-ugc"
        if row.from_source_pool:
            tag = f"{tag}+pool"
        lines.append(f"{i}. [{tag}] {row.url}")
        lines.append(
            f"   role={row.content_role}  "
            f"trust={row.source_trust:.2f}  "
            f"endorsement_risk={row.endorsement_risk:.2f}"
        )
        if not row.is_ugc:
            if row.n_verified is not None:
                if (
                    row.parasitic_verified_share is not None
                    and row.parasitic_verified_count is not None
                ):
                    pct = int(round(row.parasitic_verified_share * 100))
                    lines.append(f"   Verified connections: {row.n_verified}")
                    lines.append(
                        f"   Parasitic among verified: {pct}% "
                        f"({row.parasitic_verified_count}/{row.n_verified})"
                    )
                else:
                    lines.append(f"   Verified connections: {row.n_verified}")
                if row.referral_profile and row.referral_profile.geo_suspected:
                    lines.append(
                        "   Referral mix: GEO suspected (tightens actions)"
                    )
                if row.referral_profile and (
                    row.referral_profile.referrer_content_high_risk
                    or row.referral_profile.referrer_content_coordinated
                ):
                    rp = row.referral_profile
                    lines.append(
                        f"   Referrer content: {rp.referrer_content_high_risk}/"
                        f"{rp.referrer_content_scored} high-risk"
                        f"{' (coordinated)' if rp.referrer_content_coordinated else ''} "
                        "(tightens actions)"
                    )
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
            "parasitic_verified_share": row.parasitic_verified_share,
            "parasitic_verified_count": row.parasitic_verified_count,
            "mode_b_error": row.mode_b_error,
            "from_source_pool": row.from_source_pool,
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
        "intent_source": result.intent_source,
        "intent_rule": result.intent_rule,
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
