from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from anti_geo.audit.engines import EngineAdapter, get_engine, record_from_response
from anti_geo.audit.logger import append_record, load_records
from anti_geo.audit.metrics import (
    citation_persistence,
    compute_jaccard_sensitivity,
    domain_citation_share,
)
from anti_geo.audit.models import AuditRun, AuditSummary, CitationRecord
from anti_geo.audit.overlay import score_citations_overlay
from anti_geo.audit.query_sets import get_query_pairs
from anti_geo.audit.referral import build_referral_audit_report, platform_role_citation_share
from anti_geo.config import DEFAULT_CONFIG


def run_audit(
    engine: EngineAdapter,
    *,
    query_set: str = "default",
    log_dir: Path | None = None,
    run_id: str | None = None,
    with_overlay: bool = False,
) -> AuditRun:
    log_dir = log_dir or Path("data/audits")
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    started_at = datetime.now(timezone.utc).isoformat()
    records: list[CitationRecord] = []

    for pair in get_query_pairs(query_set):
        for query, paraphrase_of in ((pair.original, None), (pair.paraphrase, pair.original)):
            response = engine.query(query)
            record = record_from_response(
                run_id, engine.name, query, response, paraphrase_of=paraphrase_of
            )
            records.append(record)
            append_record(record, log_dir)

    return AuditRun(run_id=run_id, engine=engine.name, started_at=started_at, records=records)


def summarize_audit(
    records: list[CitationRecord],
    *,
    with_overlay: bool = False,
    window_days: int = DEFAULT_CONFIG.audit_persistence_window_days,
    target_domain: str | None = None,
    fetches: dict | None = None,
    fetcher=None,
) -> AuditSummary:
    mean_jd, pct_change = compute_jaccard_sensitivity(records)
    shares = domain_citation_share(records)
    persistence = citation_persistence(records, window_days=window_days)

    geo_risk_share = None
    commercial_high_share = None
    if with_overlay:
        overlay = score_citations_overlay(records)
        geo_risk_share = overlay["geo_risk_share"]
        commercial_high_share = overlay["commercial_high_share"]

    platform_role_shares = platform_role_citation_share(records)
    referral_convergence_hosts = None
    if target_domain:
        referral = build_referral_audit_report(
            records,
            target_domain,
            fetches=fetches,
            fetcher=fetcher,
        )
        if referral.link_graph:
            referral_convergence_hosts = len(referral.link_graph.convergent_hosts)

    engine = records[0].engine if records else "unknown"
    return AuditSummary(
        engine=engine,
        query_count=len({r.query for r in records}),
        mean_jaccard_distance=mean_jd,
        pct_citation_change=pct_change,
        domain_shares=shares,
        persistence_rate=persistence,
        geo_risk_share=geo_risk_share,
        commercial_high_share=commercial_high_share,
        target_domain=target_domain,
        platform_role_shares=platform_role_shares,
        referral_convergence_hosts=referral_convergence_hosts,
    )


def format_audit_summary(summary: AuditSummary) -> str:
    lines = [
        f"Engine: {summary.engine}",
        f"Queries: {summary.query_count}",
        f"Mean Jaccard distance (paraphrase sensitivity): {summary.mean_jaccard_distance:.3f}",
        f"% citation set changed: {summary.pct_citation_change:.1f}%",
    ]
    if summary.persistence_rate is not None:
        lines.append(f"Citation persistence: {summary.persistence_rate:.3f}")
    if summary.geo_risk_share is not None:
        lines.append(f"GEO-risk citation share: {summary.geo_risk_share:.1%}")
    if summary.commercial_high_share is not None:
        lines.append(f"High-commercial citation share: {summary.commercial_high_share:.1%}")
    if summary.target_domain:
        lines.append(f"Target domain filter: {summary.target_domain}")
    if summary.platform_role_shares:
        lines.append("Platform role citation mix:")
        for role, share in sorted(summary.platform_role_shares.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"  {role}: {share:.1f}%")
    if summary.referral_convergence_hosts is not None:
        lines.append(f"Referral convergence hosts: {summary.referral_convergence_hosts}")
    if summary.domain_shares:
        lines.append("Domain citation shares:")
        for domain, share in sorted(summary.domain_shares.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"  {domain}: {share:.1f}%")
    return "\n".join(lines)


def save_summary(summary: AuditSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "engine": summary.engine,
                "query_count": summary.query_count,
                "mean_jaccard_distance": summary.mean_jaccard_distance,
                "pct_citation_change": summary.pct_citation_change,
                "domain_shares": summary.domain_shares,
                "persistence_rate": summary.persistence_rate,
                "geo_risk_share": summary.geo_risk_share,
                "commercial_high_share": summary.commercial_high_share,
                "target_domain": summary.target_domain,
                "platform_role_shares": summary.platform_role_shares,
                "referral_convergence_hosts": summary.referral_convergence_hosts,
            },
            indent=2,
        )
    )


def load_and_summarize(log_path: Path, **kwargs) -> AuditSummary:
    return summarize_audit(load_records(log_path), **kwargs)
