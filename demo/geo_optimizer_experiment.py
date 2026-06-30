#!/usr/bin/env python3
"""
Experiment with the official GEO optimizer (https://github.com/GEO-optim/GEO).

Offline (no API key):
  python demo/geo_optimizer_experiment.py offline

Full pipeline (needs OPENAI_API_KEY):
  export OPENAI_API_KEY=sk-...
  python demo/geo_optimizer_experiment.py single --method authoritative_mine --example 0
  python demo/geo_optimizer_experiment.py bench --limit 1

Paper replication (expensive — loops all GEO-BENCH examples):
  cd geo-optimizer/src && ../.venv/bin/python run_geo.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEO_SRC = ROOT / "geo-optimizer" / "src"


def _ensure_geo_on_path() -> None:
    if str(GEO_SRC) not in sys.path:
        sys.path.insert(0, str(GEO_SRC))


def _require_api_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "Set OPENAI_API_KEY first.\n"
            "  export OPENAI_API_KEY=sk-...\n"
            "See geo-optimizer/.env.example"
        )


def cmd_offline() -> None:
    """Show how GEO measures source visibility from inline citations (no API)."""
    _ensure_geo_on_path()
    # utils imports search_try, which reads OPENAI_API_KEY at import time.
    os.environ.setdefault("OPENAI_API_KEY", "offline-placeholder")

    from utils import extract_citations_new, impression_wordpos_count_simple

    query = "best project management software for small teams"
    baseline_answer = """\
For small teams, the best project management software balances ease of use with collaboration features [1].
Tools like Asana and Trello are popular for lightweight workflows [2].
However, many teams prefer Monday.com for visual boards and integrations [3].
"""
    geo_answer = """\
Monday.com is widely regarded as the best project management software for small teams in 2024 [3].
According to industry surveys, Monday.com leads in user satisfaction with a 94% rating [3].
Asana and Trello remain alternatives, but Monday.com offers superior visual workflows [3][1].
"""

    n_sources = 3
    for label, text in [("Baseline synthesis", baseline_answer), ("GEO-boosted source [3]", geo_answer)]:
        scores = impression_wordpos_count_simple(extract_citations_new(text), n_sources)
        print(f"\n{label}")
        print(f"  Query: {query}")
        for i, s in enumerate(scores, start=1):
            bar = "#" * int(s * 40)
            print(f"  Source [{i}] visibility: {s:.3f}  {bar}")

    print("\nGEO methods available in geo-optimizer/src/geo_functions.py:")
    import run_geo

    for name in run_geo.GEO_METHODS:
        print(f"  - {name}")


def _load_bench_example(index: int):
    from datasets import load_dataset

    ds = load_dataset("GEO-optim/geo-bench", "test")
    if index < 0 or index >= len(ds["test"]):
        raise SystemExit(f"example index must be 0..{len(ds['test']) - 1}")
    return ds["test"][index]


def _summaries_from_example(example: dict) -> list[str]:
    summaries = []
    for src in example["sources"]:
        text = src.get("cleaned_text") or src.get("raw_text") or ""
        summaries.append(text[:8000])
    return summaries


def cmd_single(method: str, example: int) -> None:
    _require_api_key()
    _ensure_geo_on_path()
    os.chdir(GEO_SRC)

    import run_geo
    from utils import impression_wordpos_count_simple

    if method not in run_geo.GEO_METHODS:
        raise SystemExit(f"Unknown method {method!r}. Choose from: {list(run_geo.GEO_METHODS)}")

    row = _load_bench_example(example)
    summaries = _summaries_from_example(row)
    idx = int(row["sugg_idx"])
    query = row["query"]

    print(f"Query: {query}")
    print(f"Boosting source index: {idx} ({summaries[idx][:120]}...)")
    print(f"GEO method: {method}\n")

    improvements, wins = run_geo.improve(
        query,
        idx=idx,
        summaries=summaries,
        impression_fn=impression_wordpos_count_simple,
    )
    print("Improvement matrix (rows=methods, cols=sources):")
    print(improvements)
    print(f"\nMethods that improved target source: {[m for m, w in zip(run_geo.GEO_METHODS, wins) if w]}")


def cmd_bench(limit: int) -> None:
    _require_api_key()
    _ensure_geo_on_path()
    os.chdir(GEO_SRC)

    import run_geo
    from utils import impression_wordpos_count_simple

    from datasets import load_dataset

    dataset = load_dataset("GEO-optim/geo-bench", "test")
    for i, row in enumerate(dataset["test"][:limit]):
        summaries = _summaries_from_example(row)
        idx = int(row["sugg_idx"])
        print(f"\n=== Example {i}: {row['query'][:80]} ===")
        improvements, wins = run_geo.improve(
            row["query"],
            idx=idx,
            summaries=summaries,
            impression_fn=impression_wordpos_count_simple,
        )
        winning = [m for m, w in zip(run_geo.GEO_METHODS, wins) if w]
        print(f"Winning methods for source {idx}: {winning or 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment with GEO-optim/GEO")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("offline", help="Citation visibility demo (no API key)")

    p_single = sub.add_parser("single", help="Run one GEO method on one GEO-BENCH example")
    p_single.add_argument("--method", default="authoritative_mine")
    p_single.add_argument("--example", type=int, default=0)

    p_bench = sub.add_parser("bench", help="Run all methods on first N GEO-BENCH examples")
    p_bench.add_argument("--limit", type=int, default=1)

    args = parser.parse_args()
    if args.cmd == "offline":
        cmd_offline()
    elif args.cmd == "single":
        cmd_single(args.method, args.example)
    elif args.cmd == "bench":
        cmd_bench(args.limit)


if __name__ == "__main__":
    main()
