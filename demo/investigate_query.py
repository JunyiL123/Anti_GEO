#!/usr/bin/env python3
"""
Mode A — investigate a search query via engine citations.

Examples:
  PYTHONPATH=src python demo/investigate_query.py "best budget laptops" --engine mock \\
    --fixture tests/fixtures/audit_replays/budget_laptops.jsonl

  PYTHONPATH=src python demo/investigate_query.py "best personalized jewellery" --engine azure

  # Fast Mode B per non-UGC cite (default: 5 seeds / 15 verified). Use --deep for 50.
  PYTHONPATH=src python demo/investigate_query.py "QUERY" --engine azure --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anti_geo.progress import make_progress
from anti_geo.query_investigation import (
    DEEP_MAX_FETCHES_PER_SEED,
    DEEP_MAX_VERIFIED,
    DEEP_MIN_SEEDS_BEFORE_STOP,
    DEEP_SEED_LIMIT,
    DEFAULT_MAX_FETCHES_PER_SEED,
    DEFAULT_MAX_VERIFIED,
    DEFAULT_MIN_SEEDS_BEFORE_STOP,
    DEFAULT_SEED_LIMIT,
    DEFAULT_SITE_WORKERS,
    format_query_investigation_report,
    investigate_query,
    query_investigation_to_dict,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Anti-GEO Mode A search-query investigation"
    )
    parser.add_argument("query", help="Search / user query to investigate")
    parser.add_argument(
        "--intent",
        default="auto",
        help=(
            "Query intent: auto (heuristics, then LLM if Azure configured), "
            "or informational / informational_high_stakes / commercial / navigational"
        ),
    )
    parser.add_argument(
        "--engine",
        default="azure",
        choices=["mock", "perplexity", "azure"],
        help="Citation engine (default: azure)",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="JSONL replay fixture for --engine mock",
    )
    parser.add_argument(
        "--site-workers",
        type=int,
        default=DEFAULT_SITE_WORKERS,
        help=f"Parallel Mode B jobs across non-UGC cites (default {DEFAULT_SITE_WORKERS})",
    )
    parser.add_argument(
        "--seed-workers",
        type=int,
        default=4,
        help="Parallel seed queries inside each Mode B job (default 4)",
    )
    parser.add_argument(
        "--fetch-workers",
        type=int,
        default=8,
        help="Parallel citation fetches inside each Mode B job (default 8)",
    )
    parser.add_argument(
        "--seed-limit",
        type=int,
        default=None,
        help=f"Max seed queries per non-UGC cite (default {DEFAULT_SEED_LIMIT}; --deep={DEEP_SEED_LIMIT})",
    )
    parser.add_argument(
        "--seed-mode",
        default="auto",
        choices=["auto", "template", "llm"],
        help="Seed query source: auto=Azure LLM if configured else templates",
    )
    parser.add_argument(
        "--query-delay",
        type=float,
        default=0.0,
        help="Seconds between live engine seed queries (rate limiting)",
    )
    parser.add_argument(
        "--max-fetches-per-seed",
        type=int,
        default=None,
        help=f"Max fetches per seed (default {DEFAULT_MAX_FETCHES_PER_SEED})",
    )
    parser.add_argument(
        "--max-verified",
        type=int,
        default=None,
        help=f"Verified referrer cap per non-UGC cite (default {DEFAULT_MAX_VERIFIED})",
    )
    parser.add_argument(
        "--min-seeds-before-stop",
        type=int,
        default=None,
        help=f"Min seeds before verified stop (default {DEFAULT_MIN_SEEDS_BEFORE_STOP})",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help=f"Forensics caps: seeds={DEEP_SEED_LIMIT}, verified={DEEP_MAX_VERIFIED}, "
        f"fetches/seed={DEEP_MAX_FETCHES_PER_SEED} (disables adaptive stop)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full 8 subscores + permissions per cite",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    progress_group = parser.add_mutually_exclusive_group()
    progress_group.add_argument(
        "--progress",
        action="store_true",
        help="Force stderr progress bar + ETA",
    )
    progress_group.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar",
    )
    args = parser.parse_args()

    if args.progress:
        enabled: bool | None = True
    elif args.no_progress:
        enabled = False
    else:
        enabled = None

    deep = args.deep
    seed_limit = args.seed_limit
    if seed_limit is None:
        seed_limit = DEEP_SEED_LIMIT if deep else DEFAULT_SEED_LIMIT
    max_verified = args.max_verified
    if max_verified is None:
        max_verified = DEEP_MAX_VERIFIED if deep else DEFAULT_MAX_VERIFIED
    max_fetches = args.max_fetches_per_seed
    if max_fetches is None:
        max_fetches = DEEP_MAX_FETCHES_PER_SEED if deep else DEFAULT_MAX_FETCHES_PER_SEED
    min_seeds = args.min_seeds_before_stop
    if min_seeds is None:
        min_seeds = DEEP_MIN_SEEDS_BEFORE_STOP if deep else DEFAULT_MIN_SEEDS_BEFORE_STOP

    progress = make_progress(enabled=enabled, label="Anti-GEO Mode A", unit="cites")
    result = investigate_query(
        args.query,
        query_intent=args.intent,
        engine_name=args.engine,
        fixture_path=args.fixture,
        site_workers=args.site_workers,
        seed_workers=args.seed_workers,
        fetch_workers=args.fetch_workers,
        seed_limit=seed_limit,
        seed_mode=args.seed_mode,
        query_delay_s=args.query_delay,
        max_fetches_per_seed=max_fetches,
        max_verified_referrers=max_verified,
        min_seeds_before_verified_stop=min_seeds,
        adaptive_stop=not deep,
        deep=deep,
        progress=progress,
    )

    if args.json:
        print(json.dumps(query_investigation_to_dict(result), indent=2))
    else:
        print(format_query_investigation_report(result, verbose=args.verbose))


if __name__ == "__main__":
    main()
