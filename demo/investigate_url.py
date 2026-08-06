#!/usr/bin/env python3
"""
Mode B — investigate a URL for GEO risk (L1-L3 always; optional referral discovery).

Examples:
  PYTHONPATH=src python demo/investigate_url.py https://www.pcmag.com/picks/the-best-budget-laptops

  PYTHONPATH=src python demo/investigate_url.py https://example.com/product --intent commercial

  PYTHONPATH=src python demo/investigate_url.py URL --engine mock --json

  PYTHONPATH=src python demo/investigate_url.py URL --engine mock \\
    --fixture tests/fixtures/audit_replays/budget_laptops.jsonl

  PERPLEXITY_API_KEY=... PYTHONPATH=src python demo/investigate_url.py URL --engine perplexity

  # OpenAI Platform (or Azure): LLM seeds (auto when env set) + web_search
  export OPENAI_API_KEY=sk-...
  # export OPENAI_MODEL=gpt-5
  PYTHONPATH=src python demo/investigate_url.py URL --engine azure

  # Progress bar + ETA on stderr (auto on TTY; use --no-progress to hide)
  # Parallel discovery: --seed-workers 4 (engine queries) --fetch-workers 8 (citation pages)
  PYTHONPATH=src python demo/investigate_url.py URL --engine azure --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anti_geo.investigation import (
    format_investigation_report,
    investigation_to_dict,
    investigate_url,
)
from anti_geo.progress import make_progress


def main() -> None:
    parser = argparse.ArgumentParser(description="Anti-GEO Mode B URL investigation")
    parser.add_argument("url", help="Target URL to investigate")
    parser.add_argument(
        "--intent",
        default="commercial",
        help="Query intent context (default: commercial for product/editorial pages)",
    )
    parser.add_argument("--query", default=None, help="Optional user query for endorsement gating")
    parser.add_argument(
        "--engine",
        default="none",
        choices=["none", "mock", "perplexity", "azure"],
        help="Referral discovery engine (default: none — L1-L3 only)",
    )
    parser.add_argument("--seed-limit", type=int, default=12, help="Max seed queries")
    parser.add_argument(
        "--seed-mode",
        default="auto",
        choices=["auto", "template", "llm"],
        help="Seed query source: auto=Azure LLM if configured else templates",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="JSONL replay fixture for --engine mock",
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
        default=30,
        help="Max successful page fetches per seed (random order)",
    )
    parser.add_argument(
        "--max-verified",
        type=int,
        default=50,
        help="Stop after this many verified referrers (default 50)",
    )
    parser.add_argument(
        "--min-seeds-before-stop",
        type=int,
        default=4,
        help="Minimum seed queries before verified-referrer stop applies",
    )
    parser.add_argument(
        "--seed-workers",
        type=int,
        default=4,
        help="Parallel Azure/engine seed queries (default 4; use 12 to run all seeds at once)",
    )
    parser.add_argument(
        "--fetch-workers",
        type=int,
        default=8,
        help="Parallel citation page fetches per seed (default 8)",
    )
    parser.add_argument(
        "--seed-pack",
        default="default",
        choices=["default", "forum"],
        help="Seed experiment pack: forum prepends directory/forum/complaint queries",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    progress_group = parser.add_mutually_exclusive_group()
    progress_group.add_argument(
        "--progress",
        action="store_true",
        help="Force stderr progress bar + ETA (default: on when stderr is a TTY)",
    )
    progress_group.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar",
    )
    args = parser.parse_args()

    enabled: bool | None
    if args.progress:
        enabled = True
    elif args.no_progress:
        enabled = False
    else:
        enabled = None  # TTY auto-detect

    progress = make_progress(enabled=enabled, label="Anti-GEO")
    result = investigate_url(
        args.url,
        query_intent=args.intent,
        query=args.query,
        engine_name=None if args.engine == "none" else args.engine,
        seed_limit=args.seed_limit,
        seed_mode=args.seed_mode,
        seed_pack=args.seed_pack,
        fixture_path=args.fixture,
        query_delay_s=args.query_delay,
        max_fetches_per_seed=args.max_fetches_per_seed,
        max_verified_referrers=args.max_verified,
        min_seeds_before_verified_stop=args.min_seeds_before_stop,
        progress=progress,
        seed_workers=args.seed_workers,
        fetch_workers=args.fetch_workers,
    )

    if args.json:
        print(json.dumps(investigation_to_dict(result), indent=2))
    else:
        print(format_investigation_report(result))


if __name__ == "__main__":
    main()
