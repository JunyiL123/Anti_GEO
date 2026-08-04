#!/usr/bin/env python3
"""Collect Azure engine cites only (no Mode B / permissions) → blind label sheet.

Writes:
  - label_sheet_v1.json          (for human labeling; empty labels, no Anti-GEO preds)
  - label_sheet_v1_cite_raw.json (engine cite lists for debugging)

Does NOT write Anti-GEO permissions/parasitic predictions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from anti_geo.audit.engines import get_engine  # noqa: E402


LABEL_SCHEMA = {
    "retrieve_permission": ["allow", "downrank", "defer", "reject"],
    "mention_permission": ["allow", "deny"],
    "factual_permission": [
        "allow",
        "attribute_only",
        "require_corroboration",
        "deny",
    ],
    "endorsement_permission": ["allow", "deny"],
    "parasitic": ["none", "elevated", "suspected"],
}

LABEL_INSTRUCTIONS = {
    "retrieve_permission": (
        "Should the engine retrieve/use this page at all for this query? "
        "allow | downrank | defer | reject"
    ),
    "mention_permission": "May the answer name/attribute this source? allow | deny",
    "factual_permission": (
        "May the answer use claims from this page as facts? "
        "allow | attribute_only | require_corroboration | deny"
    ),
    "endorsement_permission": (
        "May the answer recommend / crown a pick from this page? allow | deny. "
        "Legal GEO-y marketing alone is not automatic deny — deny when you "
        "would not trust it as advice."
    ),
    "parasitic": (
        "Separate Mode B judgment (not single-page): none | elevated | "
        "suspected. Do not change the four permissions to 'encode' this — "
        "keep them independent."
    ),
}

EMPTY_LABELS = {
    "retrieve_permission": None,
    "mention_permission": None,
    "factual_permission": None,
    "endorsement_permission": None,
    "parasitic": None,
}


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def _read_queries(path: Path) -> list[str]:
    out: list[str] = []
    for line in path.read_text().splitlines():
        q = line.strip()
        if q and not q.startswith("#"):
            out.append(q)
    return out


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _pick_urls(urls: list[str], cap: int) -> list[str]:
    """Prefer unique domains, keep engine order, fill if short."""
    kept: list[str] = []
    seen: set[str] = set()
    for url in urls:
        dom = _domain(url)
        if not dom:
            continue
        if dom in seen and len(kept) >= max(3, cap // 2):
            continue
        seen.add(dom)
        kept.append(url)
        if len(kept) >= cap:
            return kept
    for url in urls:
        if url in kept:
            continue
        kept.append(url)
        if len(kept) >= cap:
            break
    return kept


def _rebuild_sheet(
    raw_rows: list[dict],
    *,
    engine: str,
    max_pages: int,
) -> tuple[dict, dict]:
    pages: list[dict] = []
    query_meta: list[dict] = []
    page_i = 0
    for row in raw_rows:
        query = row["query"]
        picked = list(row.get("kept_urls") or [])
        err = row.get("error")
        query_meta.append(
            {
                "query": query,
                "n_pages": len(picked),
                "intent": "commercial",
                **({"error": err} if err else {}),
            }
        )
        for url in picked:
            page_i += 1
            pages.append(
                {
                    "id": f"v1p{page_i:02d}",
                    "query": query,
                    "url": url,
                    "domain": _domain(url),
                    "source": "engine_cite",
                    "role_hint": None,
                    "note": None,
                    "labels": dict(EMPTY_LABELS),
                }
            )
    now = datetime.now(timezone.utc).isoformat()
    blind = {
        "description": (
            "Permissions paper expansion label sheet (v1): commercial-intent "
            "queries only. Engine cites only — labels empty for human labeling. "
            "Anti-GEO system outputs are NOT in this file. See LABEL_GUIDE.md."
        ),
        "claim_focus": (
            "per-source use rights under commercial recommend queries; "
            "Mode B parasitic evaluated separately and may only tighten actions"
        ),
        "created_at": now,
        "label_schema": LABEL_SCHEMA,
        "label_instructions": LABEL_INSTRUCTIONS,
        "n_queries": len(query_meta),
        "n_pages": len(pages),
        "queries": query_meta,
        "pages": pages,
    }
    raw = {
        "description": "Raw engine cite lists for v1 (no Anti-GEO scoring).",
        "created_at": now,
        "engine": engine,
        "queries": raw_rows,
    }
    return blind, raw


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--queries",
        type=Path,
        default=ROOT / "data/permissions_eval/label_sheet_v1_queries.txt",
    )
    ap.add_argument(
        "--blind-out",
        type=Path,
        default=ROOT / "data/permissions_eval/label_sheet_v1.json",
    )
    ap.add_argument(
        "--raw-out",
        type=Path,
        default=ROOT / "data/permissions_eval/label_sheet_v1_cite_raw.json",
    )
    ap.add_argument("--engine", default="azure")
    ap.add_argument("--max-pages-per-query", type=int, default=6)
    ap.add_argument("--query-delay", type=float, default=1.0)
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Skip queries already present without error in --raw-out",
    )
    args = ap.parse_args()

    _load_dotenv(ROOT / ".env")
    queries = _read_queries(args.queries)
    engine = get_engine(args.engine)

    raw_by_q: dict[str, dict] = {}
    if args.resume and args.raw_out.is_file():
        prev = json.loads(args.raw_out.read_text(encoding="utf-8"))
        for row in prev.get("queries") or []:
            q = row.get("query")
            if q and not row.get("error") and row.get("kept_urls"):
                raw_by_q[q] = row
        print(f"Resume: {len(raw_by_q)} queries already cited", flush=True)

    for i, query in enumerate(queries, 1):
        if query in raw_by_q:
            n = len(raw_by_q[query].get("kept_urls") or [])
            print(f"[{i}/{len(queries)}] skip (resume): {query!r} ({n} cites)", flush=True)
            continue
        print(f"[{i}/{len(queries)}] cite-only: {query!r}", flush=True)
        t0 = time.time()
        try:
            resp = engine.query(query)
            all_urls = list(resp.cited_urls or [])
            picked = _pick_urls(all_urls, args.max_pages_per_query)
            err = None
        except Exception as exc:  # noqa: BLE001
            all_urls, picked, err = [], [], f"{type(exc).__name__}: {exc}"
            print(f"  ERROR: {err}", flush=True)

        raw_by_q[query] = {
            "query": query,
            "elapsed_s": round(time.time() - t0, 2),
            "error": err,
            "n_engine_cites": len(all_urls),
            "cited_urls": all_urls,
            "kept_urls": picked,
        }
        print(f"  kept {len(picked)}/{len(all_urls)} cites", flush=True)

        # Incremental save after each query.
        ordered = [raw_by_q[q] for q in queries if q in raw_by_q]
        blind, raw = _rebuild_sheet(
            ordered, engine=args.engine, max_pages=args.max_pages_per_query
        )
        args.raw_out.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        args.blind_out.write_text(json.dumps(blind, indent=2) + "\n", encoding="utf-8")

        if args.query_delay > 0 and i < len(queries):
            time.sleep(args.query_delay)

    ordered = [raw_by_q[q] for q in queries if q in raw_by_q]
    blind, raw = _rebuild_sheet(
        ordered, engine=args.engine, max_pages=args.max_pages_per_query
    )
    args.raw_out.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    args.blind_out.write_text(json.dumps(blind, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote blind sheet: {args.blind_out} ({blind['n_pages']} pages)")
    print(f"Wrote cite raw:    {args.raw_out}")
    print("Label THIS file only — do not open Anti-GEO pred JSONs while labeling.")


if __name__ == "__main__":
    main()
