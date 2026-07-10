"""Anti-GEO: production-style URL analysis pipeline."""

from anti_geo.pipeline import (
    analyze_query,
    analyze_url,
    analyze_url_chunks,
    analyze_urls,
    bundle_to_json,
    format_defended_report,
    format_multi_report,
    format_report,
)
from anti_geo.eval import (
    EvalCase,
    EvalResult,
    build_proxy_benchmark_cases,
    evaluate_case,
    evaluate_proxy_suite,
    summarize_eval_results,
)
from anti_geo.retrieval import compute_pawc, defended_rerank, score_page_chunks, tfidf_retrieval_scores
from anti_geo.synthesis_guard import apply_synthesis_guard

__all__ = [
    "EvalCase",
    "EvalResult",
    "analyze_query",
    "analyze_url",
    "analyze_url_chunks",
    "analyze_urls",
    "bundle_to_json",
    "build_proxy_benchmark_cases",
    "evaluate_case",
    "evaluate_proxy_suite",
    "format_report",
    "format_multi_report",
    "format_defended_report",
    "apply_synthesis_guard",
    "defended_rerank",
    "compute_pawc",
    "score_page_chunks",
    "summarize_eval_results",
    "tfidf_retrieval_scores",
]
