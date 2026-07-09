from __future__ import annotations

import math
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.content_signals import (
    action_from_endorsement_risk,
    compute_endorsement_risk,
    extract_content_signals,
    retrieval_manipulation_score,
    rhetorical_manipulation_score,
)
from anti_geo.decisions import _has_persuasive_content
from anti_geo.models import ChunkScore, SourcePermissions, SourceScore, VisibilityReport
from anti_geo.permissions import derive_permissions
from anti_geo.subscores import _fetch_failure_kind, compute_subscores

PAWC_POSITION_WEIGHTS = [1.0, 0.62, 0.38, 0.22, 0.15]
_TOKEN_RE = re.compile(r"[a-z0-9]+")


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


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _tfidf_vector(tokens: list[str], df: dict[str, int], n_docs: int) -> dict[str, float]:
    counts: dict[str, int] = {}
    for term in tokens:
        counts[term] = counts.get(term, 0) + 1
    vec: dict[str, float] = {}
    for term, tf in counts.items():
        idf = math.log((1 + n_docs) / (1 + df.get(term, 0))) + 1.0
        vec[term] = (1 + math.log(tf)) * idf
    return vec


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _source_permissions(
    source: SourceScore,
    query: str | None,
    query_intent: str,
    config: DefenseConfig,
) -> SourcePermissions:
    subscores = compute_subscores(source, query, query_intent, config)
    fetch_failure = _fetch_failure_kind(source) if not source.fetch_ok else None
    return derive_permissions(
        subscores,
        fetch_failure_kind=fetch_failure,
        has_persuasive_content=_has_persuasive_content(source),
        config=config,
    )


def _dominant_host_trust(sources: dict[str, SourceScore], host: str) -> float | None:
    trusts = [
        source.trust_score
        for url, source in sources.items()
        if _host(url) == host or _host(source.url) == host
    ]
    return min(trusts) if trusts else None


def downrank_dominant_risky_host(
    ranked: list[ScoredChunk],
    sources: dict[str, SourceScore],
    pawc: VisibilityReport,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> list[ScoredChunk]:
    """Apply extra penalty when one low-trust host dominates defended visibility."""
    if not pawc.alert or not pawc.dominant_host:
        return ranked

    dominant_trust = _dominant_host_trust(sources, pawc.dominant_host)
    if dominant_trust is None or dominant_trust >= config.downrank_trust_threshold:
        return ranked

    adjusted: list[ScoredChunk] = []
    penalty = 1.0 - config.dominant_host_penalty
    for row in ranked:
        if _host(row.url) == pawc.dominant_host:
            adjusted.append(
                ScoredChunk(
                    chunk_id=row.chunk_id,
                    url=row.url,
                    text=row.text,
                    base_score=row.base_score,
                    trust_score=row.trust_score,
                    semantic_risk=row.semantic_risk,
                    endorsement_risk=row.endorsement_risk,
                    combined_score=row.combined_score * penalty,
                    recommended_action=row.recommended_action,
                )
            )
        else:
            adjusted.append(row)
    adjusted.sort(key=lambda row: row.combined_score, reverse=True)
    return adjusted


def tfidf_retrieval_scores(query: str, texts: list[str]) -> list[float]:
    """Baseline TF-IDF relevance scores for query–chunk pairs."""
    if not texts:
        return []
    all_docs = [_tokenize(query)] + [_tokenize(text) for text in texts]
    df: dict[str, int] = {}
    for tokens in all_docs:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1
    n_docs = len(all_docs)
    q_vec = _tfidf_vector(_tokenize(query), df, n_docs)
    return [_cosine(q_vec, _tfidf_vector(_tokenize(text), df, n_docs)) for text in texts]


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
    sources: dict[str, SourceScore],
    query_intent: str = "informational",
    top_k: int = 5,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> tuple[list[ScoredChunk], VisibilityReport]:
    """
    Re-rank retrieved chunks with L1/L2 penalties, permission gates, and visibility guard.

    chunks: list of (chunk_id, url, text, base_retrieval_score)
    sources: url → inferred source scores from fetch + domain signals
    """
    scored: list[ScoredChunk] = []
    for chunk_id, url, text, base in chunks:
        source = sources.get(url)
        if source is None:
            continue

        permissions = _source_permissions(source, query, query_intent, config)
        if permissions.retrieve_permission == "reject":
            continue
        if permissions.retrieve_permission == "defer" and base < 0.35:
            continue

        content = extract_content_signals(text, query, config)
        rhetorical = rhetorical_manipulation_score(content)
        retrieval_risk = retrieval_manipulation_score(content, rhetorical)
        source_subscores = compute_subscores(source, query, query_intent, config)

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
            l1_penalty = rhetorical * config.l1_penalty_weight
            l1_penalty = min(
                0.85,
                l1_penalty + retrieval_risk * config.retrieval_manipulation_penalty_weight,
            )
            l1_penalty = min(
                0.85,
                l1_penalty + source_subscores.intent_mismatch * config.intent_mismatch_penalty_weight,
            )

        l2_penalty = min(0.85, (1.0 - source.trust_score) * config.l2_penalty_weight)
        if source.fetch_ok and source.content_signals.word_count < config.thin_content_words:
            l2_penalty = min(0.85, l2_penalty + 0.05)
        if not source.fetch_ok:
            l2_penalty = min(0.85, l2_penalty + config.l2_faulty_penalty)
        if permissions.retrieve_permission == "downrank":
            l2_penalty = min(0.85, l2_penalty + config.retrieve_downrank_penalty)

        combined = base * (1.0 - l1_penalty) * (1.0 - l2_penalty)
        action = action_from_endorsement_risk(risk, config)
        scored.append(
            ScoredChunk(
                chunk_id=chunk_id,
                url=url,
                text=text,
                base_score=base,
                trust_score=source.trust_score,
                semantic_risk=rhetorical,
                endorsement_risk=risk,
                combined_score=combined,
                recommended_action=action,
            )
        )

    scored.sort(key=lambda row: row.combined_score, reverse=True)
    selected = diversify_by_host(scored, top_k)
    pawc = compute_pawc(selected, config)
    if pawc.alert:
        adjusted = downrank_dominant_risky_host(scored, sources, pawc, config)
        selected = diversify_by_host(adjusted, top_k)
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
