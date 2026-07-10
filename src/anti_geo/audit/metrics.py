from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from anti_geo.audit.models import CitationRecord
from anti_geo.independence import jaccard


def compute_jaccard_sensitivity(records: list[CitationRecord]) -> tuple[float, float]:
    """
    Mean Jaccard distance and % of paraphrase pairs with different citation sets.
    Pairs are linked via paraphrase_of field.
    """
    by_original: dict[str, set[str]] = {}
    by_paraphrase: dict[str, set[str]] = {}

    for rec in records:
        domains = set(rec.cited_domains)
        if rec.paraphrase_of:
            by_paraphrase[rec.paraphrase_of] = domains
        else:
            by_original[rec.query] = domains

    distances: list[float] = []
    changes = 0
    pairs = 0
    for original, orig_domains in by_original.items():
        para_domains = by_paraphrase.get(original)
        if para_domains is None:
            continue
        pairs += 1
        dist = 1.0 - jaccard(orig_domains, para_domains)
        distances.append(dist)
        if orig_domains != para_domains:
            changes += 1

    mean_jd = sum(distances) / len(distances) if distances else 0.0
    pct_change = (changes / pairs * 100.0) if pairs else 0.0
    return mean_jd, pct_change


def domain_citation_share(records: list[CitationRecord]) -> dict[str, float]:
    counts: dict[str, int] = defaultdict(int)
    total = 0
    for rec in records:
        for domain in set(rec.cited_domains):
            counts[domain] += 1
            total += 1
    if total == 0:
        return {}
    return {d: 100.0 * c / total for d, c in counts.items()}


def citation_persistence(
    records: list[CitationRecord],
    *,
    window_days: int = 7,
) -> float | None:
    """
    P(cited at t | cited at t-window) aggregated over (query, domain) pairs.
    Requires timestamps across multiple days in records.
    """
    by_query_day: dict[tuple[str, str], set[str]] = defaultdict(set)
    for rec in records:
        day = rec.timestamp[:10]
        for domain in rec.cited_domains:
            by_query_day[(rec.query, day)].add(domain)

    days = sorted({k[1] for k in by_query_day})
    if len(days) < 2:
        return None

    hits = 0
    total = 0
    for i, day in enumerate(days):
        if i == 0:
            continue
        prev_day = days[i - 1]
        if (datetime.fromisoformat(day) - datetime.fromisoformat(prev_day)).days > window_days:
            continue
        queries = {q for (q, d) in by_query_day if d == day}
        for query in queries:
            prev_domains = by_query_day.get((query, prev_day), set())
            curr_domains = by_query_day.get((query, day), set())
            for domain in prev_domains:
                total += 1
                if domain in curr_domains:
                    hits += 1
    if total == 0:
        return None
    return hits / total
