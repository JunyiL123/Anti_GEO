#!/usr/bin/env python3
"""Run one Mode A investigate_query and merge into a shared combined JSON (flock-safe)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore

from anti_geo.progress import make_progress
from anti_geo.query_investigation import (
    DEFAULT_MAX_VERIFIED,
    DEFAULT_SEED_LIMIT,
    investigate_query,
    query_investigation_to_dict,
)


def _merge(combined_path: Path, site_key: str, result: dict) -> None:
    combined_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = combined_path.with_suffix(combined_path.suffix + ".lock")
    with open(lock_path, "a+", encoding="utf-8") as lock_f:
        if fcntl is not None:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            if combined_path.is_file():
                payload = json.loads(combined_path.read_text())
            else:
                payload = {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "mode": "A",
                    "queries": {},
                }
            payload.setdefault("queries", {})[site_key] = result
            # keep legacy key empty/unused
            payload.setdefault("sites", {})
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            tmp = combined_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2) + "\n")
            tmp.replace(combined_path)
        finally:
            if fcntl is not None:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mode A query investigation → merge into shared combined.json"
    )
    parser.add_argument("slug", help="Key under combined.json queries")
    parser.add_argument("query", help="Search / user query (Mode A)")
    parser.add_argument(
        "--combined",
        type=Path,
        default=Path("data/forum_seed_experiment/combined.json"),
    )
    parser.add_argument("--engine", default="azure")
    parser.add_argument("--intent", default="auto")
    parser.add_argument("--seed-limit", type=int, default=DEFAULT_SEED_LIMIT)
    parser.add_argument("--max-verified", type=int, default=DEFAULT_MAX_VERIFIED)
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args()

    progress = make_progress(
        enabled=False if args.no_progress else None,
        label=f"Anti-GEO Mode A [{args.slug}]",
        unit="cites",
    )
    print(f"[{args.slug}] Mode A query={args.query!r} → {args.combined}", flush=True)
    result = investigate_query(
        args.query,
        query_intent=args.intent,
        engine_name=args.engine,
        seed_limit=args.seed_limit,
        max_verified_referrers=args.max_verified,
        progress=progress,
    )
    payload = query_investigation_to_dict(result)
    payload["slug"] = args.slug
    _merge(args.combined, args.slug, payload)
    cites = [r.url for r in result.rows]
    print(
        f"[{args.slug}] done cites={len(cites)} intent={result.query_intent} "
        f"mode={result.guard.response_mode if result.guard else None}",
        flush=True,
    )
    for i, url in enumerate(cites[:8], 1):
        print(f"  {i}. {url}", flush=True)


if __name__ == "__main__":
    main()
