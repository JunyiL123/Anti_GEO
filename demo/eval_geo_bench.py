#!/usr/bin/env python3
"""
Phase B evaluation harness for Anti-GEO.

Default mode is an offline proxy benchmark that approximates Princeton GEO attack
families with deterministic rewrites so it is runnable in CI and without API keys.

Examples:
  PYTHONPATH=src python3 demo/eval_geo_bench.py
  PYTHONPATH=src python3 demo/eval_geo_bench.py --method authoritative_mine --case pm_tools
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anti_geo.eval import PROXY_METHODS, build_proxy_benchmark_cases, evaluate_proxy_suite, summarize_eval_results


def main() -> None:
    all_cases = build_proxy_benchmark_cases()
    parser = argparse.ArgumentParser(description="Phase B Anti-GEO proxy evaluation harness")
    parser.add_argument(
        "--method",
        action="append",
        choices=sorted(PROXY_METHODS),
        help="Limit to one or more proxy GEO methods",
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=[c.name for c in all_cases],
        help="Limit to one or more built-in benchmark cases",
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=sorted({c.suite for c in all_cases}),
        help="Limit to one or more benchmark suites",
    )
    args = parser.parse_args()

    cases = all_cases
    if args.suite:
        allowed_suites = set(args.suite)
        cases = [c for c in cases if c.suite in allowed_suites]
    if args.case:
        allowed = set(args.case)
        cases = [c for c in cases if c.name in allowed]

    results = evaluate_proxy_suite(methods=args.method, cases=cases)
    print(summarize_eval_results(results))


if __name__ == "__main__":
    main()
