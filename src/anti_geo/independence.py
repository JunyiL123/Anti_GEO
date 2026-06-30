from __future__ import annotations

import re
from collections import defaultdict

from anti_geo.models import IndependenceReport

TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cluster_by_similarity(texts: dict[str, str], threshold: float = 0.45) -> list[set[str]]:
    urls = list(texts.keys())
    parent = {u: u for u in urls}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    token_map = {u: _tokens(t) for u, t in texts.items()}
    for i, u1 in enumerate(urls):
        for u2 in urls[i + 1 :]:
            if jaccard(token_map[u1], token_map[u2]) >= threshold:
                union(u1, u2)

    clusters: dict[str, set[str]] = defaultdict(set)
    for u in urls:
        clusters[find(u)].add(u)
    return list(clusters.values())


def analyze_independence(url_texts: dict[str, str]) -> IndependenceReport:
    """
    Infer coordination from textual similarity — no campaign_actor metadata.
    """
    urls = list(url_texts.keys())
    pairwise: dict[str, float] = {}
    max_sim = 0.0

    token_map = {u: _tokens(t) for u, t in url_texts.items()}
    for i, u1 in enumerate(urls):
        for u2 in urls[i + 1 :]:
            sim = jaccard(token_map[u1], token_map[u2])
            pairwise[f"{u1} ↔ {u2}"] = round(sim, 3)
            max_sim = max(max_sim, sim)

    clusters = _cluster_by_similarity(url_texts)
    cluster_count = len(clusters)
    reasons: list[str] = []

    if cluster_count < len(urls) and max_sim >= 0.45:
        reasons.append("high_textual_similarity_across_domains")
    if max_sim >= 0.55:
        reasons.append("likely_shared_copy_or_template")

    coordinated = cluster_count == 1 and len(urls) >= 2 and max_sim >= 0.35

    return IndependenceReport(
        urls=urls,
        naive_source_count=len(urls),
        cluster_count=cluster_count,
        max_cluster_similarity=round(max_sim, 3),
        is_likely_coordinated=coordinated,
        pairwise_similarity=pairwise,
        reasons=reasons,
    )
