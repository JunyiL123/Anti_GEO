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

  # Azure: LLM seeds (auto when env set) + web_search citation discovery
  export AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
  export AZURE_OPENAI_API_KEY=...
  export AZURE_OPENAI_DEPLOYMENT=gpt-5.5
  PYTHONPATH=src python demo/investigate_url.py URL --engine azure
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
        default=100,
        help="Stop after this many verified referrers (once min seeds met)",
    )
    parser.add_argument(
        "--min-seeds-before-stop",
        type=int,
        default=4,
        help="Minimum seed queries before verified-referrer stop applies",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = investigate_url(
        args.url,
        query_intent=args.intent,
        query=args.query,
        engine_name=None if args.engine == "none" else args.engine,
        seed_limit=args.seed_limit,
        seed_mode=args.seed_mode,
        fixture_path=args.fixture,
        query_delay_s=args.query_delay,
        max_fetches_per_seed=args.max_fetches_per_seed,
        max_verified_referrers=args.max_verified,
        min_seeds_before_verified_stop=args.min_seeds_before_stop,
    )

    if args.json:
        print(json.dumps(investigation_to_dict(result), indent=2))
    else:
        print(format_investigation_report(result))


if __name__ == "__main__":
    main()
