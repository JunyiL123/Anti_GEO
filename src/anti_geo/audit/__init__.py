from __future__ import annotations

from anti_geo.audit.engines import MockEngine, PerplexityEngine, get_engine
from anti_geo.audit.metrics import (
    citation_persistence,
    compute_jaccard_sensitivity,
    domain_citation_share,
)
from anti_geo.audit.models import AuditRun, CitationRecord, ParaphrasePair
from anti_geo.audit.overlay import score_citations_overlay
from anti_geo.audit.query_sets import DEFAULT_QUERY_PAIRS, get_query_pairs
from anti_geo.audit.report import format_audit_summary, run_audit

__all__ = [
    "AuditRun",
    "CitationRecord",
    "MockEngine",
    "ParaphrasePair",
    "PerplexityEngine",
    "DEFAULT_QUERY_PAIRS",
    "citation_persistence",
    "compute_jaccard_sensitivity",
    "domain_citation_share",
    "format_audit_summary",
    "get_engine",
    "get_query_pairs",
    "run_audit",
    "score_citations_overlay",
]
