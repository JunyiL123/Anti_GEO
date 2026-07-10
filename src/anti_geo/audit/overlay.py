from __future__ import annotations

from anti_geo.audit.models import CitationRecord
from anti_geo.pipeline import analyze_url


def score_citations_overlay(
    records: list[CitationRecord],
    *,
    geo_risk_threshold: float = 0.55,
) -> dict:
    """Run analyze_url on cited URLs and summarize GEO/commercial risk."""
    urls_scored: dict[str, dict] = {}
    high_commercial = 0
    high_geo_risk = 0
    total_urls = 0

    for rec in records:
        for url in rec.cited_urls:
            if url in urls_scored:
                entry = urls_scored[url]
            else:
                try:
                    report = analyze_url(url)
                    subscores = report.subscores
                    if subscores is None:
                        continue
                    tier = "none"
                    if report.source.page_context:
                        tier = report.source.page_context.commercial_tier
                    entry = {
                        "url": url,
                        "retrieval_manipulation_risk": subscores.retrieval_manipulation_risk,
                        "commercial_tier": tier,
                        "trust_score": report.source.trust_score,
                    }
                    urls_scored[url] = entry
                except Exception:
                    continue
                total_urls += 1
                if entry["retrieval_manipulation_risk"] >= geo_risk_threshold:
                    high_geo_risk += 1
                if entry["commercial_tier"] == "high":
                    high_commercial += 1

    return {
        "urls_scored": total_urls,
        "geo_risk_share": high_geo_risk / total_urls if total_urls else 0.0,
        "commercial_high_share": high_commercial / total_urls if total_urls else 0.0,
        "top_risk_sources": sorted(
            urls_scored.values(),
            key=lambda x: x["retrieval_manipulation_risk"],
            reverse=True,
        )[:5],
    }
