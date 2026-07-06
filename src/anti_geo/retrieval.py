from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.content_signals import extract_content_signals, compute_endorsement_risk, action_from_endorsement_risk
from anti_geo.models import ChunkScore, SourceScore, VisibilityReport

PAWC_POSITION_WEIGHTS = [1.0, 0.62, 0.38, 0.22, 0.15]


@dataclass
class ScoredChunk:
    chunk_id: str
    url: str
    text: str
    base_score: float
    trust_score: float
    semantic_risk: float
    endorsement_risk: float
    combined_score: float
    recommended_action: str


def _host(url: str) -> str:
    return urlparse(url).netloc or url


def compute_pawc(
    ranked: list[ScoredChunk],
    config: DefenseConfig = DEFAULT_CONFIG,
) -> VisibilityReport:
    by_url: dict[str, float] = {}
    by_host: dict[str, float] = {}
    total = 0.0
    for i, row in enumerate(ranked):
        weight = PAWC_POSITION_WEIGHTS[i] if i < len(PAWC_POSITION_WEIGHTS) else 0.1
        contribution = weight * len(row.text.split())
        by_url[row.url] = by_url.get(row.url, 0.0) + contribution
        host = _host(row.url)
        by_host[host] = by_host.get(host, 0.0) + contribution
        total += contribution
    if total == 0:
        return VisibilityReport({}, {}, "", "", 0.0, False)
    by_url_pct = {u: 100.0 * v / total for u, v in by_url.items()}
    by_host_pct = {h: 100.0 * v / total for h, v in by_host.items()}
    dominant_url = max(by_url_pct, key=by_url_pct.get)
    dominant_host = max(by_host_pct, key=by_host_pct.get)
    share = by_host_pct[dominant_host]
    return VisibilityReport(
        by_url=by_url_pct,
        by_host=by_host_pct,
        dominant_url=dominant_url,
        dominant_host=dominant_host,
        dominant_share=share,
        alert=share / 100.0 >= config.pawc_dominance_alert,
    )


def diversify_by_host(ranked: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
    """Cap one chunk per hostname to mitigate visibility hijacking."""
    selected: list[ScoredChunk] = []
    hosts_seen: set[str] = set()
    for row in ranked:
        host = _host(row.url)
        if host in hosts_seen:
            continue
        hosts_seen.add(host)
        selected.append(row)
        if len(selected) >= top_k:
            break
    if len(selected) < top_k:
        seen_ids = {id(r) for r in selected}
        for row in ranked:
            if id(row) in seen_ids:
                continue
            selected.append(row)
            if len(selected) >= top_k:
                break
    return selected


def defended_rerank(
    query: str,
    chunks: list[tuple[str, str, str, float]],
    source: SourceScore,
    query_intent: str = "informational",
    top_k: int = 5,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> tuple[list[ScoredChunk], VisibilityReport]:
    """
    Re-rank retrieved chunks with L1/L2 penalties and endorsement risk.

    chunks: list of (chunk_id, url, text, base_retrieval_score)
    """
    scored: list[ScoredChunk] = []
    for chunk_id, url, text, base in chunks:
        content = extract_content_signals(text, query, config)
        risk = compute_endorsement_risk(
            query,
            text,
            content,
            source.trust_score,
            source.page_context,
            query_intent,
        )
        l1_penalty = 0.0
        if query_intent.startswith("informational"):
            l1_penalty = content.semantic_risk * config.l1_penalty_weight
        l2_penalty = min(0.85, (1.0 - source.trust_score) * config.l2_penalty_weight)
        if source.fetch_ok and source.content_signals.word_count < config.thin_content_words:
            l2_penalty = min(0.85, l2_penalty + 0.05)
        combined = base * (1.0 - l1_penalty) * (1.0 - l2_penalty)
        action = action_from_endorsement_risk(risk, config)
        scored.append(
            ScoredChunk(
                chunk_id=chunk_id,
                url=url,
                text=text,
                base_score=base,
                trust_score=source.trust_score,
                semantic_risk=content.semantic_risk,
                endorsement_risk=risk,
                combined_score=combined,
                recommended_action=action,
            )
        )
    scored.sort(key=lambda r: r.combined_score, reverse=True)
    selected = diversify_by_host(scored, top_k)
    pawc = compute_pawc(selected, config)
    return selected, pawc


def score_page_chunks(
    query: str,
    source: SourceScore,
    chunk_pairs: list[tuple[str, str]],
    query_intent: str = "informational",
    config: DefenseConfig = DEFAULT_CONFIG,
) -> list[ChunkScore]:
    results: list[ChunkScore] = []
    for chunk_id, text in chunk_pairs:
        content = extract_content_signals(text, query, config)
        risk = compute_endorsement_risk(
            query,
            text,
            content,
            source.trust_score,
            source.page_context,
            query_intent,
        )
        results.append(
            ChunkScore(
                chunk_id=chunk_id,
                url=source.url,
                text=text,
                content_signals=content,
                trust_score=source.trust_score,
                endorsement_risk=risk,
                recommended_action=action_from_endorsement_risk(risk, config),
            )
        )
    results.sort(key=lambda c: c.endorsement_risk, reverse=True)
    return results
