#!/usr/bin/env python3
"""Run one Mode B investigate_url and merge into a shared combined JSON (flock-safe)."""

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

from anti_geo.investigation import investigation_to_dict, investigate_url
from anti_geo.progress import make_progress


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
                    "sites": {},
                }
            payload.setdefault("sites", {})[site_key] = result
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            tmp = combined_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2) + "\n")
            tmp.replace(combined_path)
        finally:
            if fcntl is not None:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mode B → merge into shared combined.json"
    )
    parser.add_argument("site_key", help="Key under combined.json sites (e.g. feedspot)")
    parser.add_argument("url", help="Target URL")
    parser.add_argument(
        "--combined",
        type=Path,
        default=Path("data/forum_seed_experiment/combined.json"),
        help="Shared JSON path",
    )
    parser.add_argument("--engine", default="azure")
    parser.add_argument("--seed-pack", default="forum", choices=["default", "forum"])
    parser.add_argument("--seed-limit", type=int, default=16)
    parser.add_argument("--max-verified", type=int, default=15)
    parser.add_argument("--intent", default="commercial")
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args()

    progress = make_progress(
        enabled=False if args.no_progress else None,
        label=f"Anti-GEO [{args.site_key}]",
    )
    print(
        f"[{args.site_key}] starting {args.url} → {args.combined}",
        flush=True,
    )
    result = investigate_url(
        args.url,
        query_intent=args.intent,
        engine_name=None if args.engine == "none" else args.engine,
        seed_limit=args.seed_limit,
        seed_pack=args.seed_pack,
        max_verified_referrers=args.max_verified,
        progress=progress,
    )
    payload = investigation_to_dict(result)
    payload["site_key"] = args.site_key
    _merge(args.combined, args.site_key, payload)
    print(
        f"[{args.site_key}] done action={result.llm_action} "
        f"geo_risk={result.referral_profile.geo_risk:.3f} "
        f"elevated={result.referral_profile.geo_elevated} "
        f"suspected={result.referral_profile.geo_suspected} "
        f"N={result.referral_profile.n_verified}",
        flush=True,
    )


if __name__ == "__main__":
    main()
