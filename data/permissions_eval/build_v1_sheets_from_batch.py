#!/usr/bin/env python3
"""Split a Mode A batch shard into (1) blind human label sheet and (2) Anti-GEO preds.

Blind sheet contains query/url/domain only + empty labels — no permissions,
parasitic, content_role, or llm_action. System preds stay in a separate JSON.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


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


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _parasitic_tier(rp: dict | None) -> str | None:
    if not rp:
        return None
    if rp.get("parasitic_geo_suspected") is True:
        return "suspected"
    if rp.get("parasitic_geo_elevated") or rp.get("status") == "sparse_suspicious":
        return "elevated"
    return "none"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--batch",
        type=Path,
        default=Path(
            "data/permissions_eval/label_sheet_v1_anti_geo_batch.json"
        ),
    )
    ap.add_argument(
        "--blind-out",
        type=Path,
        default=Path("data/permissions_eval/label_sheet_v1.json"),
    )
    ap.add_argument(
        "--preds-out",
        type=Path,
        default=Path(
            "data/permissions_eval/label_sheet_v1_anti_geo_engine_cites.json"
        ),
    )
    ap.add_argument(
        "--max-pages-per-query",
        type=int,
        default=6,
        help="Cap cites kept per query for labeling load (default 6)",
    )
    args = ap.parse_args()

    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    investigations = batch.get("investigations") or []

    blind_pages: list[dict] = []
    pred_pages: list[dict] = []
    query_meta: list[dict] = []
    page_i = 0

    for inv in investigations:
        query = inv.get("query") or ""
        if inv.get("error") or not inv.get("result"):
            query_meta.append(
                {
                    "query": query,
                    "n_pages": 0,
                    "intent": "commercial",
                    "error": inv.get("error"),
                }
            )
            continue
        result = inv["result"]
        rows = list(result.get("rows") or [])
        # Prefer unique domains; keep engine order.
        kept: list[dict] = []
        seen_domains: set[str] = set()
        for row in rows:
            url = row.get("url") or ""
            if not url:
                continue
            dom = _domain(url)
            if dom in seen_domains and len(kept) >= max(3, args.max_pages_per_query // 2):
                continue
            seen_domains.add(dom)
            kept.append(row)
            if len(kept) >= args.max_pages_per_query:
                break
        # If still short, fill remaining without domain filter.
        if len(kept) < args.max_pages_per_query:
            have = {r.get("url") for r in kept}
            for row in rows:
                if row.get("url") in have:
                    continue
                kept.append(row)
                if len(kept) >= args.max_pages_per_query:
                    break

        query_meta.append(
            {
                "query": query,
                "n_pages": len(kept),
                "intent": result.get("query_intent") or "commercial",
            }
        )

        for row in kept:
            page_i += 1
            pid = f"v1p{page_i:02d}"
            url = row["url"]
            perms = row.get("permissions") or {}
            rp = row.get("referral_profile") or {}

            blind_pages.append(
                {
                    "id": pid,
                    "query": query,
                    "url": url,
                    "domain": _domain(url),
                    "source": "engine_cite",
                    "role_hint": None,
                    "note": None,
                    "labels": dict(EMPTY_LABELS),
                }
            )
            pred_pages.append(
                {
                    "id": pid,
                    "query": query,
                    "url": url,
                    "domain": _domain(url),
                    "ok": True,
                    "predictions": {
                        "retrieve_permission": perms.get("retrieve_permission"),
                        "mention_permission": perms.get("mention_permission"),
                        "factual_permission": perms.get("factual_permission"),
                        "endorsement_permission": perms.get(
                            "endorsement_permission"
                        ),
                        "parasitic": _parasitic_tier(rp),
                        "parasitic_geo_risk": rp.get("parasitic_geo_risk"),
                        "parasitic_geo_suspected": rp.get(
                            "parasitic_geo_suspected"
                        ),
                        "parasitic_geo_elevated": rp.get(
                            "parasitic_geo_elevated"
                        ),
                        "parasitic_source": rp.get("parasitic_source"),
                        "permissions_source": row.get("permissions_source"),
                        "permissions_llm_reason": row.get(
                            "permissions_llm_reason"
                        ),
                        "content_role": row.get("content_role"),
                        "llm_action": row.get("llm_action"),
                        "is_ugc": row.get("is_ugc"),
                        "mode_b_error": row.get("mode_b_error"),
                        "n_verified": row.get("n_verified"),
                    },
                }
            )

    now = datetime.now(timezone.utc).isoformat()
    blind = {
        "description": (
            "Permissions paper expansion label sheet (v1): commercial-intent "
            "queries only. Engine cites only — labels empty for human/LLM "
            "labeling. Anti-GEO system outputs are NOT in this file."
        ),
        "claim_focus": (
            "per-source use rights under commercial recommend queries; "
            "Mode B parasitic evaluated separately and may only tighten actions"
        ),
        "created_at": now,
        "label_schema": LABEL_SCHEMA,
        "label_instructions": LABEL_INSTRUCTIONS,
        "n_queries": len(query_meta),
        "n_pages": len(blind_pages),
        "queries": query_meta,
        "pages": blind_pages,
    }
    preds = {
        "description": (
            "Anti-GEO Mode A engine-cite predictions for label_sheet_v1 "
            "(HOLD OUT from human labeling). Not forced-cites protocol — "
            "cites came from the live engine."
        ),
        "created_at": now,
        "batch": str(args.batch),
        "blind_sheet": str(args.blind_out),
        "engine": batch.get("engine"),
        "n_queries": len(query_meta),
        "n_pages": len(pred_pages),
        "queries": query_meta,
        "pages": pred_pages,
        "raw_investigations_ok": sum(
            1 for inv in investigations if not inv.get("error")
        ),
        "raw_investigations_err": sum(
            1 for inv in investigations if inv.get("error")
        ),
    }

    args.blind_out.parent.mkdir(parents=True, exist_ok=True)
    args.blind_out.write_text(json.dumps(blind, indent=2) + "\n", encoding="utf-8")
    args.preds_out.write_text(json.dumps(preds, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote blind sheet: {args.blind_out} ({len(blind_pages)} pages)")
    print(f"Wrote system preds: {args.preds_out} ({len(pred_pages)} pages)")


if __name__ == "__main__":
    main()
