from __future__ import annotations

from anti_geo.chunking import chunk_from_fetch
from anti_geo.decisions import (
    decide_corroboration_for_claim,
    decide_single_source,
    extract_shared_claim,
)
from anti_geo.fetch import fetch_page
from anti_geo.independence import analyze_independence
from anti_geo.models import (
    FetchResult,
    GuardResult,
    QueryContextScores,
    SourcePermissions,
    SourceScore,
    UrlAnalysisReport,
    VisibilityReport,
)
from anti_geo.retrieval import (
    ScoredChunk,
    compute_pawc,
    defended_rerank,
    score_page_chunks,
    tfidf_retrieval_scores,
)
from anti_geo.contestability import (
    assess_chunks_commercial,
    build_contestability_report,
    chunk_key,
    format_contestability_report,
)
from anti_geo.disclosure import apply_disclosures_to_answer, build_disclosure_report
from anti_geo.permissions import apply_commercial_tightening, derive_llm_actions
from anti_geo.scorer import score_source
from anti_geo.subscores import build_query_context_scores
from anti_geo.synthesis_guard import apply_synthesis_guard


def analyze_url(
    url: str,
    query_intent: str = "informational",
    query: str | None = None,
) -> UrlAnalysisReport:
    """
    Production flow for one URL:
      fetch → domain signals → content signals → trust score → decision
    """
    fetch = fetch_page(url)
    source = score_source(url, fetch, query=query)
    return decide_single_source(source, query_intent, query=query)


def analyze_url_chunks(
    url: str,
    query: str,
    query_intent: str = "informational",
) -> dict:
    """Chunk-level scoring for a single URL against a query."""
    fetch = fetch_page(url)
    source = score_source(url, fetch, query=query)
    chunks = chunk_from_fetch(fetch)
    chunk_scores = score_page_chunks(query, source, chunks, query_intent)
    report = decide_single_source(source, query_intent, query=query)
    return {"source_report": report, "chunks": chunk_scores}


def analyze_urls(
    urls: list[str],
    query_intent: str = "informational",
    claim_entity: str | None = None,
    query: str | None = None,
) -> dict:
    """
    Multi-URL flow: score each source, cluster for independence, gate endorsement.
    """
    reports = [analyze_url(u, query_intent, query=query) for u in urls]
    sources = [r.source for r in reports]
    url_texts = {s.url: s.text_excerpt for s in sources if s.text_excerpt}

    independence = analyze_independence(url_texts) if len(url_texts) >= 2 else None
    entity = claim_entity or extract_shared_claim(sources)
    corroboration = None
    if entity and independence:
        corroboration = decide_corroboration_for_claim(
            sources,
            entity,
            independence.cluster_count,
            query_intent,
        )

    return {
        "sources": reports,
        "independence": independence,
        "corroboration": corroboration,
        "claim_entity": entity,
        "query": query,
    }


def analyze_query(
    query: str,
    urls: list[str],
    query_intent: str = "informational",
    claim_entity: str | None = None,
    top_k: int = 5,
    fetches: dict[str, FetchResult] | None = None,
) -> dict:
    """
    Full defended pipeline for a query over multiple URLs:
      fetch → score → chunk → TF-IDF retrieve → defended rerank → PAWC → L3 guard
    """
    sources_by_url: dict[str, SourceScore] = {}
    reports: list[UrlAnalysisReport] = []
    chunk_rows: list[tuple[str, str, str]] = []

    for url in urls:
        fetch = (fetches or {}).get(url) or fetch_page(url)
        source = score_source(url, fetch, query=query)
        sources_by_url[source.url] = source
        reports.append(decide_single_source(source, query_intent, query=query))
        for chunk_id, text in chunk_from_fetch(fetch):
            chunk_rows.append((chunk_id, source.url, text))

    base_scores = tfidf_retrieval_scores(query, [text for _, _, text in chunk_rows])
    chunk_tuples = [
        (chunk_id, url, text, base)
        for (chunk_id, url, text), base in zip(chunk_rows, base_scores, strict=True)
    ]

    baseline_scored = sorted(
        [
            ScoredChunk(
                chunk_id=cid,
                url=url,
                text=text,
                base_score=base,
                trust_score=sources_by_url[url].trust_score,
                semantic_risk=0.0,
                endorsement_risk=0.0,
                combined_score=base,
                recommended_action="pass",
            )
            for cid, url, text, base in chunk_tuples
            if url in sources_by_url
        ],
        key=lambda row: row.combined_score,
        reverse=True,
    )
    baseline_pawc = compute_pawc(baseline_scored[:top_k])

    defended, pawc = defended_rerank(
        query, chunk_tuples, sources_by_url, query_intent, top_k=top_k
    )
    entity = claim_entity or extract_shared_claim([r.source for r in reports])
    source_permissions: dict[str, SourcePermissions] = {
        report.source.url: report.permissions
        for report in reports
        if report.permissions is not None
    }
    url_texts = {s.url: s.text_excerpt for s in sources_by_url.values() if s.text_excerpt}
    independence = analyze_independence(url_texts) if len(url_texts) >= 2 else None
    corroboration = None
    if entity and independence:
        corroboration = decide_corroboration_for_claim(
            list(sources_by_url.values()),
            entity,
            independence.cluster_count,
            query_intent,
        )
    corroboration_strength = 0.0
    if corroboration:
        corroboration_strength = min(
            1.0,
            corroboration.independent_support_count / 3.0 + (0.25 if corroboration.has_institutional_support else 0.0),
        )
    query_context = build_query_context_scores(
        independence_cluster_count=independence.cluster_count if independence else None,
        is_likely_coordinated=independence.is_likely_coordinated if independence else False,
        corroboration_strength=corroboration_strength,
        visibility_dominance=pawc.dominant_share / 100.0 if pawc.dominant_share else 0.0,
        visibility_alert=pawc.alert,
    )
    is_coordinated = (
        independence.is_likely_coordinated if independence else False
    ) or query_context.consensus_integrity == "coordinated"

    commercial_assessments = assess_chunks_commercial(
        defended,
        sources_by_url,
        source_permissions,
        query,
        query_intent,
        is_coordinated=is_coordinated,
    )
    for chunk in defended:
        assessment = commercial_assessments.get(chunk_key(chunk))
        if assessment and chunk.url in source_permissions:
            source_permissions[chunk.url] = apply_commercial_tightening(
                source_permissions[chunk.url], assessment
            )

    lead_commercial = (
        commercial_assessments.get(chunk_key(defended[0])) if defended else None
    )
    guard = apply_synthesis_guard(
        query,
        defended,
        sources_by_url,
        query_intent,
        attack_entity=entity,
        source_permissions=source_permissions,
        query_context=query_context,
        lead_commercial=lead_commercial,
        commercial_assessments=commercial_assessments,
    )

    contestability = build_contestability_report(
        query,
        baseline_scored[:top_k],
        defended,
        baseline_pawc,
        pawc,
        sources_by_url,
        source_permissions,
        commercial_assessments,
        independence=independence,
        query_context=query_context,
    )
    guard.contestability = contestability
    if guard.disclosure_report is None:
        disclosure_report = build_disclosure_report(
            defended, sources_by_url, commercial_assessments, guard
        )
        if disclosure_report.show_label:
            guard.safe_answer = apply_disclosures_to_answer(guard.safe_answer, disclosure_report)
            guard.disclosure_report = disclosure_report
            guard.disclosures = disclosure_report.disclosures

    return {
        "query": query,
        "query_intent": query_intent,
        "sources": reports,
        "sources_by_url": sources_by_url,
        "baseline_ranked": baseline_scored[:top_k],
        "baseline_pawc": baseline_pawc,
        "defended_ranked": defended,
        "pawc": pawc,
        "guard": guard,
        "independence": independence,
        "corroboration": corroboration,
        "query_context": query_context,
        "claim_entity": entity,
        "commercial_assessments": commercial_assessments,
        "contestability": contestability,
    }


def _format_query_context_scores(query_context: QueryContextScores | None) -> list[str]:
    if not query_context:
        return []
    return [
        "",
        "── Query Context Scores (3, multi-source only) ──",
        f"  Consensus integrity: {query_context.consensus_integrity}",
        f"  Corroboration strength: {query_context.corroboration_strength:.3f}",
        f"  Visibility dominance: {query_context.visibility_dominance:.3f}",
    ]


def _format_llm_actions(
    result: UrlAnalysisReport,
    query_context: QueryContextScores | None = None,
    synthesis_response_mode: str | None = None,
    *,
    compact: bool = False,
) -> list[str]:
    if not result.permissions:
        return []
    primary, actions = derive_llm_actions(
        result.permissions,
        result.subscores,
        query_context,
    )
    if compact:
        lines = [
            f"Recommended LLM action: {primary}",
            f"LLM action set: {', '.join(actions)}",
        ]
        if synthesis_response_mode:
            lines.append(f"Synthesis response mode: {synthesis_response_mode}")
        return lines

    lines = [
        "",
        "── Recommended LLM Actions ──",
        f"  Primary: {primary}",
        f"  All actions: {', '.join(actions)}",
    ]
    if synthesis_response_mode:
        lines.append(f"  Synthesis response mode: {synthesis_response_mode}")
    return lines


def _format_report_header(
    result: UrlAnalysisReport,
    query_context: QueryContextScores | None = None,
    synthesis_response_mode: str | None = None,
) -> list[str]:
    s = result.source
    lines = [
        f"URL: {s.url}",
        f"Query: {result.query or '(none)'}",
        f"Query intent: {result.query_intent}",
    ]
    lines.extend(_format_llm_actions(
        result, query_context, synthesis_response_mode, compact=True
    ))
    lines.append(f"Legacy recommended action: {result.recommended_action}")
    lines.append("")
    return lines


def _format_subscores_permissions(
    result: UrlAnalysisReport,
    query_context: QueryContextScores | None = None,
    synthesis_response_mode: str | None = None,
) -> list[str]:
    lines: list[str] = []
    if result.subscores:
        s = result.subscores
        lines.extend([
            "",
            "── Source Subscores (8) ──",
            f"  Fetch confidence: {s.fetch_confidence:.3f}",
            f"  Source trust: {s.source_trust:.3f}",
            f"  Rhetorical manipulation: {s.rhetorical_manipulation:.3f}",
            f"  Retrieval manipulation risk: {s.retrieval_manipulation_risk:.3f}",
            f"  Endorsement risk: {s.endorsement_risk:.3f}",
            f"  Factual claim reliability: {s.factual_claim_reliability:.3f}",
            f"  Intent mismatch: {s.intent_mismatch:.3f}",
            f"  Harm severity: {s.harm_severity:.3f}",
        ])
    lines.extend(_format_query_context_scores(query_context))
    if result.permissions:
        p = result.permissions
        lines.extend([
            "",
            "── Permissions ──",
            f"  Retrieve: {p.retrieve_permission}",
            f"  Mention: {p.mention_permission}",
            f"  Factual: {p.factual_permission}",
            f"  Endorsement: {p.endorsement_permission}",
        ])
    return lines


def format_report(result: UrlAnalysisReport) -> str:
    s = result.source
    d = s.domain_signals
    c = s.content_signals
    pc = s.page_context
    lines = _format_report_header(result)
    lines.extend([
        "── Fetch ──",
        f"  OK: {s.fetch_ok}",
        f"  Engine: {s.fetch_engine}",
        "",
        "── Domain signals (inferred) ──",
        f"  Host: {d.hostname}",
        f"  HTTPS: {d.is_https}",
        f"  WHOIS age (days): {d.whois_age_days if d.whois_age_days is not None else 'unknown'}",
        f"  Cert age (days): {d.cert_age_days if d.cert_age_days is not None else 'unknown'}",
        f"  Flags: {', '.join(d.signals) or 'none'}",
        "",
        "── Content signals (inferred) ──",
        f"  Words: {c.word_count}",
        f"  Semantic risk: {c.semantic_risk:.3f}",
        f"  Front-load score: {c.front_load_score:.3f}",
        f"  Quote/citation density: {c.quote_citation_density:.3f}",
        f"  Authority density: {c.authority_density:.3f}",
        f"  Comparative density: {c.comparative_density:.3f}",
        f"  Flags: {', '.join(c.flags) or 'none'}",
    ])
    if pc:
        lines.extend([
            "",
            "── Page context ──",
            f"  Commercial context: {pc.commercial_context_score:.3f}",
            f"  Structure density: {pc.structure_density:.3f}",
            f"  Flags: {', '.join(pc.flags) or 'none'}",
        ])
    lines.extend(_format_subscores_permissions(result))
    lines.extend([
        "",
        "── Legacy Compatibility ──",
        f"  trust_score: {s.trust_score:.3f}",
        f"  semantic_risk: {s.semantic_risk:.3f}",
        f"  endorsement_allowed: {s.endorsement_allowed}",
        f"  Reasons: {', '.join(s.reasons) or 'none'}",
    ])
    lines.extend([
        "",
        "── Text excerpt ──",
        f"  {s.text_excerpt[:280]}{'...' if len(s.text_excerpt) > 280 else ''}",
    ])
    return "\n".join(lines)


def format_score_report(
    result: UrlAnalysisReport,
    query_context: QueryContextScores | None = None,
    synthesis_response_mode: str | None = None,
) -> str:
    if query_context is None:
        return format_report(result)
    return _format_report_with_context(result, query_context, synthesis_response_mode)


def _format_report_with_context(
    result: UrlAnalysisReport,
    query_context: QueryContextScores,
    synthesis_response_mode: str | None = None,
) -> str:
    s = result.source
    d = s.domain_signals
    c = s.content_signals
    pc = s.page_context
    lines = _format_report_header(result, query_context, synthesis_response_mode)
    lines.extend([
        "── Fetch ──",
        f"  OK: {s.fetch_ok}",
        f"  Engine: {s.fetch_engine}",
        "",
        "── Domain signals (inferred) ──",
        f"  Host: {d.hostname}",
        f"  HTTPS: {d.is_https}",
        f"  WHOIS age (days): {d.whois_age_days if d.whois_age_days is not None else 'unknown'}",
        f"  Cert age (days): {d.cert_age_days if d.cert_age_days is not None else 'unknown'}",
        f"  Flags: {', '.join(d.signals) or 'none'}",
        "",
        "── Content signals (inferred) ──",
        f"  Words: {c.word_count}",
        f"  Semantic risk: {c.semantic_risk:.3f}",
        f"  Front-load score: {c.front_load_score:.3f}",
        f"  Quote/citation density: {c.quote_citation_density:.3f}",
        f"  Authority density: {c.authority_density:.3f}",
        f"  Comparative density: {c.comparative_density:.3f}",
        f"  Flags: {', '.join(c.flags) or 'none'}",
    ])
    if pc:
        lines.extend([
            "",
            "── Page context ──",
            f"  Commercial context: {pc.commercial_context_score:.3f}",
            f"  Structure density: {pc.structure_density:.3f}",
            f"  Flags: {', '.join(pc.flags) or 'none'}",
        ])
    lines.extend(_format_subscores_permissions(result, query_context))
    lines.extend([
        "",
        "── Legacy Compatibility ──",
        f"  trust_score: {s.trust_score:.3f}",
        f"  semantic_risk: {s.semantic_risk:.3f}",
        f"  endorsement_allowed: {s.endorsement_allowed}",
        f"  Reasons: {', '.join(s.reasons) or 'none'}",
        "",
        "── Text excerpt ──",
        f"  {s.text_excerpt[:280]}{'...' if len(s.text_excerpt) > 280 else ''}",
    ])
    return "\n".join(lines)


def format_multi_report(bundle: dict) -> str:
    parts = ["=" * 60, "MULTI-SOURCE ANALYSIS", "=" * 60, ""]
    if bundle.get("query"):
        parts.append(f"Query: {bundle['query']}")
        parts.append("")
    for i, report in enumerate(bundle["sources"], 1):
        parts.append(f"--- Source {i} ---")
        parts.append(format_score_report(report))
        parts.append("")

    ind = bundle.get("independence")
    if ind:
        parts.extend([
            "── Independence (inferred from text, no metadata) ──",
            f"  Naive URL count: {ind.naive_source_count}",
            f"  Text clusters: {ind.cluster_count}",
            f"  Max pairwise similarity: {ind.max_cluster_similarity}",
            f"  Likely coordinated: {ind.is_likely_coordinated}",
            f"  Reasons: {', '.join(ind.reasons) or 'none'}",
        ])
        for pair, sim in ind.pairwise_similarity.items():
            parts.append(f"    {pair}: {sim}")
        parts.append("")

    corr = bundle.get("corroboration")
    if corr:
        parts.extend([
            "── Corroboration gate ──",
            f"  Claim entity: {corr.claim_entity}",
            f"  Independent clusters: {corr.independent_support_count}",
            f"  Institutional support: {corr.has_institutional_support}",
            f"  Endorsement allowed: {corr.endorsement_allowed}",
            f"  Reasons: {', '.join(corr.reasons) or 'none'}",
        ])

    return "\n".join(parts)


def _format_pawc(label: str, pawc: VisibilityReport) -> list[str]:
    if not pawc.by_host:
        return [f"── {label} ──", "  (no chunks ranked)", ""]
    lines = [
        f"── {label} ──",
        f"  Dominant host: {pawc.dominant_host} ({pawc.dominant_share:.1f}%)",
        f"  Dominant URL: {pawc.dominant_url}",
        f"  PAWC alert: {pawc.alert}",
    ]
    for host, share in sorted(pawc.by_host.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"    {host}: {share:.1f}%")
    lines.append("")
    return lines


def _format_ranked_chunks(label: str, ranked: list[ScoredChunk]) -> list[str]:
    lines = [f"── {label} ──"]
    if not ranked:
        lines.extend(["  (empty)", ""])
        return lines
    for i, row in enumerate(ranked, 1):
        lines.append(
            f"  {i}. [{row.url}] base={row.base_score:.3f} combined={row.combined_score:.3f} "
            f"trust={row.trust_score:.2f} action={row.recommended_action}"
        )
        lines.append(f"     {row.text[:120]}{'...' if len(row.text) > 120 else ''}")
    lines.append("")
    return lines


def format_defended_report(bundle: dict) -> str:
    parts = ["=" * 60, "DEFENDED QUERY PIPELINE", "=" * 60, ""]
    parts.append(f"Query: {bundle['query']}")
    parts.append(f"Query intent: {bundle['query_intent']}")
    if bundle.get("claim_entity"):
        parts.append(f"Claim entity: {bundle['claim_entity']}")
    parts.append("")

    guard: GuardResult = bundle["guard"]
    parts.extend([
        "── Recommended LLM Action (synthesis) ──",
        f"  Response mode: {guard.response_mode}",
        f"  Utterance type: {guard.utterance_type}",
        "",
    ])

    for i, report in enumerate(bundle["sources"], 1):
        parts.append(f"--- Source {i} ---")
        parts.append(format_score_report(report, bundle.get("query_context"), guard.response_mode))
        parts.append("")

    parts.extend(_format_ranked_chunks("Baseline retrieval (TF-IDF)", bundle["baseline_ranked"]))
    parts.extend(_format_pawc("Baseline PAWC", bundle["baseline_pawc"]))
    parts.extend(_format_ranked_chunks("Defended rerank (L1+L2)", bundle["defended_ranked"]))
    parts.extend(_format_pawc("Defended PAWC", bundle["pawc"]))

    parts.extend([
        "── L3 synthesis guard ──",
        f"  Utterance type: {guard.utterance_type}",
        f"  Response mode: {guard.response_mode}",
        f"  Corroborated: {guard.corroborated}",
        f"  Actions: {', '.join(guard.actions) or 'none'}",
        "",
        "── Safe answer ──",
        f"  {guard.safe_answer}",
        "",
    ])

    if guard.disclosure_report and guard.disclosure_report.show_label:
        parts.extend([
            "── Commercial disclosure ──",
            f"  {guard.disclosure_report.combined_label_text}",
            "",
        ])

    contestability = bundle.get("contestability") or guard.contestability
    if contestability:
        parts.append(format_contestability_report(contestability))
        parts.append("")

    ind = bundle.get("independence")
    if ind:
        parts.extend([
            "── Independence ──",
            f"  Text clusters: {ind.cluster_count}",
            f"  Likely coordinated: {ind.is_likely_coordinated}",
            "",
        ])

    qctx: QueryContextScores | None = bundle.get("query_context")
    if qctx:
        parts.extend([
            "── Query context scores ──",
            f"  Consensus integrity: {qctx.consensus_integrity}",
            f"  Corroboration strength: {qctx.corroboration_strength:.3f}",
            f"  Visibility dominance: {qctx.visibility_dominance:.3f}",
            "",
        ])

    corr = bundle.get("corroboration")
    if corr:
        parts.extend([
            "── Corroboration gate ──",
            f"  Endorsement allowed: {corr.endorsement_allowed}",
            f"  Reasons: {', '.join(corr.reasons) or 'none'}",
        ])

    return "\n".join(parts)


def bundle_to_json(bundle: dict) -> dict:
    """Serialize defended query bundle for API/UI consumers."""
    from anti_geo.contestability import contestability_to_json

    guard: GuardResult = bundle["guard"]
    contestability = bundle.get("contestability") or guard.contestability
    return {
        "query": bundle["query"],
        "query_intent": bundle["query_intent"],
        "claim_entity": bundle.get("claim_entity"),
        "guard": {
            "utterance_type": guard.utterance_type,
            "corroborated": guard.corroborated,
            "response_mode": guard.response_mode,
            "actions": guard.actions,
            "safe_answer": guard.safe_answer,
            "disclosures": [
                {
                    "trigger": d.trigger,
                    "source_urls": d.source_urls,
                    "label_text": d.label_text,
                    "confidence": d.confidence,
                }
                for d in guard.disclosures
            ],
        },
        "contestability": contestability_to_json(contestability) if contestability else None,
        "baseline_dominant_share": bundle["baseline_pawc"].dominant_share,
        "defended_dominant_share": bundle["pawc"].dominant_share,
    }
