"""Anti-GEO: production-style URL analysis pipeline."""

from anti_geo.pipeline import (
    analyze_url,
    analyze_url_chunks,
    analyze_urls,
    format_multi_report,
    format_report,
)
from anti_geo.retrieval import compute_pawc, defended_rerank, score_page_chunks
from anti_geo.synthesis_guard import apply_synthesis_guard

__all__ = [
    "analyze_url",
    "analyze_url_chunks",
    "analyze_urls",
    "format_report",
    "format_multi_report",
    "apply_synthesis_guard",
    "defended_rerank",
    "compute_pawc",
    "score_page_chunks",
]
