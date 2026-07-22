#!/usr/bin/env python3
"""Run Anti-GEO (heuristics + LLM hybrid) on label_sheet query/URL rows.

Reads only id/query/url — never opens human or LLM label fields.
Writes predicted four permissions + parasitic tier (+ risk float).

Example:
  set -a && source .env && set +a
  PYTHONPATH=src python demo/label_sheet_anti_geo.py \\
    --sheet data/permissions_eval/label_sheet_v0.json \\
    --engine azure \\
    --out data/permissions_eval/label_sheet_v0_anti_geo.json
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anti_geo.investigation import investigation_to_dict, investigate_url
from anti_geo.progress import make_progress


def _parasitic_tier(profile: dict) -> str:
    """Map Mode B flags → label-sheet enum none|elevated|suspected."""
    if profile.get("parasitic_geo_suspected") is True:
        return "suspected"
    if profile.get("parasitic_geo_elevated") or profile.get("status") == "sparse_suspicious":
        return "elevated"
    return "none"


def _load_rows(sheet_path: Path) -> list[dict]:
    sheet = json.loads(sheet_path.read_text())
    rows = []
    for page in sheet.get("pages") or []:
        rows.append(
            {
                "id": page.get("id"),
                "query": page.get("query"),
                "url": page.get("url"),
                "domain": page.get("domain"),
                # provenance only — not used as supervision
                "source": page.get("source"),
                "role_hint": page.get("role_hint"),
            }
        )
    return rows


def _prediction_from_result(result) -> dict:
    d = investigation_to_dict(result)
    sp = d.get("single_page") or {}
    perms = sp.get("permissions") or {}
    rp = d.get("referral_profile") or {}
    return {
        "retrieve_permission": perms.get("retrieve_permission"),
        "mention_permission": perms.get("mention_permission"),
        "factual_permission": perms.get("factual_permission"),
        "endorsement_permission": perms.get("endorsement_permission"),
        "parasitic": _parasitic_tier(rp),
        "parasitic_geo_risk": rp.get("parasitic_geo_risk"),
        "parasitic_geo_suspected": rp.get("parasitic_geo_suspected"),
        "parasitic_geo_elevated": rp.get("parasitic_geo_elevated"),
        "permissions_source": sp.get("permissions_source"),
        "permissions_llm_reason": sp.get("permissions_llm_reason"),
        "content_role": d.get("content_role"),
        "llm_action": d.get("llm_action"),
        "referral_status": rp.get("status"),
        "n_verified": rp.get("n_verified"),
        "target_url_final": d.get("target_url"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Anti-GEO label sheet runner")
    parser.add_argument(
        "--sheet",
        type=Path,
        default=Path("data/permissions_eval/label_sheet_v0.json"),
        help="Label sheet JSON (only query/url/id are read)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/permissions_eval/label_sheet_v0_anti_geo.json"),
    )
    parser.add_argument("--engine", default="azure", choices=["azure", "perplexity", "none"])
    parser.add_argument("--seed-limit", type=int, default=10)
    parser.add_argument("--max-verified", type=int, default=15)
    parser.add_argument("--max-fetches-per-seed", type=int, default=20)
    parser.add_argument("--seed-workers", type=int, default=3)
    parser.add_argument("--fetch-workers", type=int, default=6)
    parser.add_argument("--seed-mode", default="auto", choices=["auto", "template", "llm"])
    parser.add_argument("--intent", default="commercial")
    parser.add_argument("--ids", default="", help="Comma-separated page ids to run (default: all)")
    parser.add_argument("--resume", action="store_true", help="Skip ids already in --out")
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args()

    rows = _load_rows(args.sheet)
    if args.ids.strip():
        want = {x.strip() for x in args.ids.split(",") if x.strip()}
        rows = [r for r in rows if r["id"] in want]

    payload: dict
    if args.resume and args.out.is_file():
        payload = json.loads(args.out.read_text())
        payload.setdefault("pages", [])
    else:
        payload = {
            "description": (
                "Anti-GEO predictions on label_sheet query/URL rows "
                "(heuristics + LLM hybrid). Labels from human/LLM sheets were not used."
            ),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sheet": str(args.sheet),
            "engine": args.engine,
            "seed_limit": args.seed_limit,
            "max_verified": args.max_verified,
            "n_pages": len(rows),
            "pages": [],
        }

    done_ids = {p.get("id") for p in payload["pages"] if p.get("ok")}
    payload["n_pages"] = total = len(rows)
    payload["engine"] = args.engine
    payload["seed_limit"] = args.seed_limit
    payload["max_verified"] = args.max_verified
    for i, row in enumerate(rows, 1):
        pid = row["id"]
        if args.resume and pid in done_ids:
            print(f"[{i}/{total}] skip {pid} (resume)", flush=True)
            continue

        print(f"[{i}/{total}] {pid} {row['url'][:80]}", flush=True)
        progress = make_progress(
            enabled=False if args.no_progress else None,
            label=f"Anti-GEO [{pid}]",
        )
        entry = {
            "id": pid,
            "query": row["query"],
            "url": row["url"],
            "domain": row.get("domain"),
            "ok": False,
            "error": None,
            "predictions": None,
        }
        try:
            result = investigate_url(
                row["url"],
                query_intent=args.intent,
                query=row["query"],
                engine_name=None if args.engine == "none" else args.engine,
                seed_limit=args.seed_limit,
                seed_mode=args.seed_mode,
                max_fetches_per_seed=args.max_fetches_per_seed,
                max_verified_referrers=args.max_verified,
                seed_workers=args.seed_workers,
                fetch_workers=args.fetch_workers,
                progress=progress,
                # use_llm_connection/role default None → Azure when configured
            )
            entry["ok"] = True
            entry["predictions"] = _prediction_from_result(result)
            print(
                f"  → retrieve={entry['predictions']['retrieve_permission']} "
                f"mention={entry['predictions']['mention_permission']} "
                f"factual={entry['predictions']['factual_permission']} "
                f"endorse={entry['predictions']['endorsement_permission']} "
                f"parasitic={entry['predictions']['parasitic']} "
                f"risk={entry['predictions']['parasitic_geo_risk']} "
                f"perm_src={entry['predictions']['permissions_source']}",
                flush=True,
            )
        except Exception as exc:
            entry["error"] = f"{exc}\n{traceback.format_exc()[-800:]}"
            print(f"  ERROR: {exc}", flush=True)

        # Replace prior attempt for same id if any
        payload["pages"] = [p for p in payload["pages"] if p.get("id") != pid]
        payload["pages"].append(entry)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["n_ok"] = sum(1 for p in payload["pages"] if p.get("ok"))
        payload["n_error"] = sum(1 for p in payload["pages"] if not p.get("ok"))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        tmp.replace(args.out)

    print(
        f"Done. wrote {args.out} ok={payload.get('n_ok')} err={payload.get('n_error')}",
        flush=True,
    )


if __name__ == "__main__":
    main()
