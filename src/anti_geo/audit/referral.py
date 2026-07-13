from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from anti_geo.audit.models import CitationRecord
from anti_geo.link_graph import (
    LinkGraphReport,
    build_link_graph,
    extract_referral_edges_from_fetch,
)
from anti_geo.models import FetchResult
from anti_geo.platform_role import classify_content_role, registrable_domain


@dataclass
class ReferralAuditReport:
    target_domain: str
    citations_sampled: int
    citations_to_target: int
    platform_role_shares: dict[str, float] = field(default_factory=dict)
    link_graph: LinkGraphReport | None = None
    cited_urls: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def platform_role_citation_share(records: list[CitationRecord]) -> dict[str, float]:
    counts: dict[str, int] = defaultdict(int)
    total = 0
    for rec in records:
        for url in set(rec.cited_urls):
            role = classify_content_role(url)
            counts[role] += 1
            total += 1
    if total == 0:
        return {}
    return {role: 100.0 * count / total for role, count in counts.items()}


def filter_records_for_target(
    records: list[CitationRecord],
    target_domain: str,
) -> list[CitationRecord]:
    target = registrable_domain(target_domain)
    filtered: list[CitationRecord] = []
    for rec in records:
        urls = [
            url
            for url in rec.cited_urls
            if target in registrable_domain(urlparse(url).netloc)
            or target in url.lower()
        ]
        if urls:
            filtered.append(
                CitationRecord(
                    run_id=rec.run_id,
                    timestamp=rec.timestamp,
                    engine=rec.engine,
                    query=rec.query,
                    paraphrase_of=rec.paraphrase_of,
                    response_text=rec.response_text,
                    cited_domains=rec.cited_domains,
                    cited_urls=urls,
                )
            )
    return filtered


def build_referral_audit_report(
    records: list[CitationRecord],
    target_domain: str,
    *,
    fetches: dict[str, FetchResult] | None = None,
    fetcher=None,
    max_fetches: int = 30,
) -> ReferralAuditReport:
    """Build referral graph from audit citations toward a target domain."""
    target = registrable_domain(target_domain)
    cited_urls = sorted({url for rec in records for url in rec.cited_urls})
    platform_shares = platform_role_citation_share(records)
    citations_to_target = sum(
        1
        for url in cited_urls
        if target in registrable_domain(urlparse(url).netloc) or target in url.lower()
    )

    edges = []
    fetched = 0
    for url in cited_urls:
        if fetched >= max_fetches:
            break
        fr = (fetches or {}).get(url)
        if fr is None and fetcher is not None:
            fr = fetcher(url)
            fetched += 1
        elif fr is not None:
            fetched += 1
        if fr is None:
            continue
        edges.extend(extract_referral_edges_from_fetch(fr))

    graph = build_link_graph(edges, target) if edges else None
    notes: list[str] = []
    if citations_to_target:
        notes.append(f"Target domain directly cited in {citations_to_target} audit URLs.")
    if graph and graph.entity_convergence:
        notes.append("Cross-host referral convergence detected toward target.")

    return ReferralAuditReport(
        target_domain=target,
        citations_sampled=len(cited_urls),
        citations_to_target=citations_to_target,
        platform_role_shares=platform_shares,
        link_graph=graph,
        cited_urls=cited_urls,
        notes=notes,
    )


def format_referral_audit_report(report: ReferralAuditReport) -> str:
    lines = [
        f"Target domain: {report.target_domain}",
        f"Citations sampled: {report.citations_sampled}",
        f"Citations mentioning target: {report.citations_to_target}",
    ]
    if report.platform_role_shares:
        lines.append("Platform role mix (cited URLs):")
        for role, share in sorted(report.platform_role_shares.items(), key=lambda x: -x[1]):
            lines.append(f"  {role}: {share:.1f}%")
    if report.link_graph:
        lg = report.link_graph
        lines.append(f"Promotion concentration: {lg.promotion_concentration:.1%}")
        lines.append(f"Convergent hosts: {len(lg.convergent_hosts)}")
        if lg.convergent_hosts:
            lines.append(f"  Hosts: {', '.join(lg.convergent_hosts[:8])}")
        target_edges = [e for e in lg.edges if e.target_domain == lg.target_domain]
        if target_edges:
            lines.append("Referral edges to target:")
            for edge in target_edges[:10]:
                lines.append(
                    f"  [{edge.source_role}/{edge.segment_role}] "
                    f"{edge.source_url} → {edge.target_url}"
                )
    if report.notes:
        lines.append("Notes: " + "; ".join(report.notes))
    return "\n".join(lines)
