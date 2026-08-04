#!/usr/bin/env python3
"""Run Anti-GEO Mode A (forced cites) + Mode B on label_sheet query/URL rows.

Groups sheet pages by query, replaces engine SERP with the sheet URLs for that
query, forces commercial intent, and runs Mode B on UGC cites too so every page
gets parasitic scores. Maps cite rows back to the flat overnight JSON schema.

Example:
  set -a && source .env && set +a
  PYTHONPATH=src python demo/label_sheet_anti_geo.py \\
    --sheet data/permissions_eval/label_sheet_v0.json \\
    --engine azure \\
    --out data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced.json
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from urllib.parse import unquote
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anti_geo.progress import make_progress
from anti_geo.query_investigation import (
    CiteInvestigationRow,
    investigate_query,
)


def _parasitic_tier_from_profile(profile) -> str:
    """Map Mode B flags → label-sheet enum none|elevated|suspected."""
    if profile is None:
        return "none"
    if profile.parasitic_geo_suspected is True:
        return "suspected"
    if profile.parasitic_geo_elevated or profile.status == "sparse_suspicious":
        return "elevated"
    return "none"


def _norm_url(url: str) -> str:
    """Decode %XX so sheet vs fetch final_url encodings still match."""
    return unquote((url or "").rstrip("/")).casefold()


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
                "source": page.get("source"),
                "role_hint": page.get("role_hint"),
            }
        )
    return rows


def _prediction_from_cite_row(row: CiteInvestigationRow) -> dict:
    sp = row.single_page
    perms = sp.permissions
    rp = row.referral_profile
    return {
        "retrieve_permission": perms.retrieve_permission if perms else None,
        "mention_permission": perms.mention_permission if perms else None,
        "factual_permission": perms.factual_permission if perms else None,
        "endorsement_permission": perms.endorsement_permission if perms else None,
        "parasitic": _parasitic_tier_from_profile(rp),
        "parasitic_geo_risk": None if rp is None else rp.parasitic_geo_risk,
        "parasitic_geo_suspected": None if rp is None else rp.parasitic_geo_suspected,
        "parasitic_geo_elevated": None if rp is None else rp.parasitic_geo_elevated,
        "parasitic_source": None if rp is None else rp.parasitic_source,
        "parasitic_llm_reason": None if rp is None else rp.parasitic_llm_reason,
        "permissions_source": getattr(sp, "permissions_source", None),
        "permissions_llm_reason": getattr(sp, "permissions_llm_reason", None) or None,
        "content_role": row.content_role,
        "llm_action": row.llm_action,
        "referral_status": None if rp is None else rp.status,
        "n_verified": row.n_verified if row.n_verified is not None else (
            None if rp is None else rp.n_verified
        ),
        "target_url_final": sp.source.url if sp and sp.source else row.url,
        "is_ugc": row.is_ugc,
        "mode_b_error": row.mode_b_error,
    }


def _match_cite_row(
    rows: list[CiteInvestigationRow],
    url: str,
    *,
    index: int | None = None,
) -> CiteInvestigationRow | None:
    want = _norm_url(url)
    for row in rows:
        if _norm_url(row.url) == want:
            return row
        src = row.single_page.source.url if row.single_page and row.single_page.source else ""
        if _norm_url(src) == want:
            return row
    # Forced-cites preserve input order in result.rows — index fallback.
    if index is not None and 0 <= index < len(rows):
        return rows[index]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Anti-GEO label sheet runner (Mode A forced cites + Mode B on UGC)"
    )
    parser.add_argument(
        "--sheet",
        type=Path,
        default=Path("data/permissions_eval/label_sheet_v0.json"),
        help="Label sheet JSON (only query/url/id are read)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(
            "data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced.json"
        ),
    )
    parser.add_argument("--engine", default="azure", choices=["azure", "perplexity", "none"])
    parser.add_argument("--seed-limit", type=int, default=10)
    parser.add_argument("--max-verified", type=int, default=15)
    parser.add_argument("--max-fetches-per-seed", type=int, default=20)
    parser.add_argument("--seed-workers", type=int, default=3)
    parser.add_argument("--fetch-workers", type=int, default=6)
    parser.add_argument("--site-workers", type=int, default=3)
    parser.add_argument("--seed-mode", default="auto", choices=["auto", "template", "llm"])
    parser.add_argument(
        "--intent",
        default="commercial",
        help="Query intent (default commercial for paper eval; passed as manual)",
    )
    parser.add_argument(
        "--mode-b-ugc",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run Mode B on UGC cites (default: on for this eval)",
    )
    parser.add_argument(
        "--forced-cites",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Replace engine SERP with sheet URLs per query (default: on)",
    )
    parser.add_argument("--ids", default="", help="Comma-separated page ids (default: all)")
    parser.add_argument(
        "--skip-ids",
        default="p37",
        help="Comma-separated page ids to skip (default: p37 Trustpilot)",
    )
    parser.add_argument("--resume", action="store_true", help="Skip ids already ok in --out")
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args()

    rows = _load_rows(args.sheet)
    if args.ids.strip():
        want = {x.strip() for x in args.ids.split(",") if x.strip()}
        rows = [r for r in rows if r["id"] in want]
    skip_ids = {x.strip() for x in args.skip_ids.split(",") if x.strip()}
    if skip_ids:
        rows = [r for r in rows if r["id"] not in skip_ids]

    payload: dict
    if args.resume and args.out.is_file():
        payload = json.loads(args.out.read_text())
        payload.setdefault("pages", [])
    else:
        payload = {
            "description": (
                "Anti-GEO Mode A forced-cites eval on label_sheet rows "
                "(commercial intent; sheet URLs replace SERP; Mode B on UGC). "
                "Human/LLM labels were not used."
            ),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sheet": str(args.sheet),
            "engine": args.engine,
            "query_intent": args.intent,
            "forced_cites": bool(args.forced_cites),
            "mode_b_ugc": bool(args.mode_b_ugc),
            "seed_limit": args.seed_limit,
            "max_verified": args.max_verified,
            "skip_ids": sorted(skip_ids),
            "n_pages": len(rows),
            "pages": [],
        }

    done_ids = {p.get("id") for p in payload["pages"] if p.get("ok")}
    payload["n_pages"] = total = len(rows)
    payload["engine"] = args.engine
    payload["query_intent"] = args.intent
    payload["forced_cites"] = bool(args.forced_cites)
    payload["mode_b_ugc"] = bool(args.mode_b_ugc)
    payload["seed_limit"] = args.seed_limit
    payload["max_verified"] = args.max_verified
    payload["skip_ids"] = sorted(skip_ids)

    # Group by query; drop already-done ids when resuming.
    by_query: dict[str, list[dict]] = defaultdict(list)
    pending = 0
    for row in rows:
        if args.resume and row["id"] in done_ids:
            continue
        by_query[row["query"]].append(row)
        pending += 1

    print(
        f"Mode A forced-cites: {len(by_query)} queries, {pending} pages pending "
        f"(total sheet={total}, resume_done={len(done_ids)}, skip={sorted(skip_ids)})",
        flush=True,
    )

    engine_name = None if args.engine == "none" else args.engine
    qi = 0
    for query, qrows in by_query.items():
        qi += 1
        urls = [r["url"] for r in qrows]
        print(
            f"[query {qi}/{len(by_query)}] n={len(qrows)} {query[:70]!r}",
            flush=True,
        )
        for r in qrows:
            print(f"  · {r['id']} {r['url'][:80]}", flush=True)

        progress = make_progress(
            enabled=False if args.no_progress else None,
            label=f"Mode A [{qi}/{len(by_query)}]",
        )
        try:
            result = investigate_query(
                query,
                query_intent=args.intent,
                engine_name=engine_name or "mock",
                seed_limit=args.seed_limit,
                seed_mode=args.seed_mode,
                max_fetches_per_seed=args.max_fetches_per_seed,
                max_verified_referrers=args.max_verified,
                seed_workers=args.seed_workers,
                fetch_workers=args.fetch_workers,
                site_workers=args.site_workers,
                adaptive_stop=False,
                progress=progress,
                forced_urls=urls if args.forced_cites else None,
                mode_b_ugc=bool(args.mode_b_ugc),
            )
            cite_by_id_error: dict[str, str] = {}
            for i, row in enumerate(qrows):
                cite = _match_cite_row(result.rows, row["url"], index=i)
                entry = {
                    "id": row["id"],
                    "query": row["query"],
                    "url": row["url"],
                    "domain": row.get("domain"),
                    "ok": False,
                    "error": None,
                    "predictions": None,
                    "query_intent": result.query_intent,
                    "intent_source": result.intent_source,
                }
                if cite is None:
                    entry["error"] = (
                        f"No Mode A cite row matched url={row['url']!r}; "
                        f"cited={result.cited_urls!r}"
                    )
                    print(f"  ERROR {row['id']}: {entry['error']}", flush=True)
                else:
                    entry["ok"] = True
                    entry["predictions"] = _prediction_from_cite_row(cite)
                    pred = entry["predictions"]
                    print(
                        f"  → {row['id']} retrieve={pred['retrieve_permission']} "
                        f"mention={pred['mention_permission']} "
                        f"factual={pred['factual_permission']} "
                        f"endorse={pred['endorsement_permission']} "
                        f"parasitic={pred['parasitic']} "
                        f"risk={pred['parasitic_geo_risk']} "
                        f"para_src={pred.get('parasitic_source')} "
                        f"perm_src={pred.get('permissions_source')} "
                        f"role={pred.get('content_role')}",
                        flush=True,
                    )
                    if cite.mode_b_error:
                        cite_by_id_error[row["id"]] = cite.mode_b_error

                payload["pages"] = [
                    p for p in payload["pages"] if p.get("id") != row["id"]
                ]
                payload["pages"].append(entry)

            if cite_by_id_error:
                print(f"  Mode B errors: {cite_by_id_error}", flush=True)

        except Exception as exc:
            err = f"{exc}\n{traceback.format_exc()[-800:]}"
            print(f"  QUERY ERROR: {exc}", flush=True)
            for row in qrows:
                entry = {
                    "id": row["id"],
                    "query": row["query"],
                    "url": row["url"],
                    "domain": row.get("domain"),
                    "ok": False,
                    "error": err,
                    "predictions": None,
                }
                payload["pages"] = [
                    p for p in payload["pages"] if p.get("id") != row["id"]
                ]
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
