from __future__ import annotations

from anti_geo.chunking import chunk_from_fetch
from anti_geo.decisions import (
    decide_corroboration_for_claim,
    decide_single_source,
    extract_shared_claim,
)
from anti_geo.fetch import fetch_page
from anti_geo.independence import analyze_independence
from anti_geo.models import UrlAnalysisReport
from anti_geo.retrieval import score_page_chunks
from anti_geo.scorer import score_source
from anti_geo.synthesis_guard import apply_synthesis_guard
from anti_geo.retrieval import defended_rerank


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


def format_report(result: UrlAnalysisReport) -> str:
    s = result.source
    d = s.domain_signals
    c = s.content_signals
    pc = s.page_context
    lines = [
        f"URL: {s.url}",
        f"Query: {result.query or '(none)'}",
        f"Query intent: {result.query_intent}",
        f"Recommended action: {result.recommended_action}",
        f"Endorsement risk: {result.endorsement_risk:.3f}",
        "",
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
    ]
    if pc:
        lines.extend([
            "",
            "── Page context ──",
            f"  Commercial context: {pc.commercial_context_score:.3f}",
            f"  Structure density: {pc.structure_density:.3f}",
            f"  Flags: {', '.join(pc.flags) or 'none'}",
        ])
    lines.extend([
        "",
        "── Scores ──",
        f"  Trust score: {s.trust_score:.3f}",
        f"  Endorsement allowed: {s.endorsement_allowed}",
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
        parts.append(format_report(report))
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
