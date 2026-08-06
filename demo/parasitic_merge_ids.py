#!/usr/bin/env python3
"""Merge parasitic_* for one or more page ids (permissions fields untouched)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Prefer caller env; default to auto/httpx-friendly headed-off to avoid browser hangs.
os.environ.setdefault("ANTI_GEO_FETCH", "httpx")
os.environ.setdefault("ANTI_GEO_FETCH_ARCHIVE", "auto")
os.environ["ANTI_GEO_FETCH_HEADED"] = "0"
os.environ.setdefault("ANTI_GEO_BROWSER_TIMEOUT", "35")
from anti_geo.investigation import investigation_to_dict, investigate_url  # noqa: E402

OUT = ROOT / "data/permissions_eval/label_sheet_v0_anti_geo.json"
PERM_KEYS = (
    "retrieve_permission",
    "mention_permission",
    "factual_permission",
    "endorsement_permission",
    "permissions_source",
    "permissions_llm_reason",
)


def _tier(rp: dict) -> str:
    if rp.get("parasitic_geo_suspected") is True:
        return "suspected"
    if rp.get("parasitic_geo_elevated") or rp.get("status") == "sparse_suspicious":
        return "elevated"
    return "none"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="Comma-separated page ids")
    args = ap.parse_args()
    want = [x.strip() for x in args.ids.split(",") if x.strip()]

    payload = json.loads(OUT.read_text())
    by_id = {p["id"]: p for p in payload["pages"]}

    for pid in want:
        page = by_id[pid]
        if page.get("_parasitic_rerun_at") and not page.get("_parasitic_rerun_error"):
            print(f"skip {pid} (already done)", flush=True)
            continue
        pred = page.setdefault("predictions", {})
        perm_before = {k: pred.get(k) for k in PERM_KEYS}
        print(f"{pid} {(page.get('url') or '')[:80]}", flush=True)
        try:
            result = investigate_url(
                page["url"],
                query_intent="commercial",
                query=page.get("query") or "",
                engine_name="azure",
                seed_limit=10,
                seed_mode="auto",
                max_fetches_per_seed=20,
                max_verified_referrers=15,
                seed_workers=3,
                fetch_workers=6,
                progress=None,
            )
            rp = (investigation_to_dict(result).get("referral_profile") or {})
            para = {
                "parasitic": _tier(rp),
                "parasitic_geo_risk": rp.get("parasitic_geo_risk"),
                "parasitic_geo_suspected": rp.get("parasitic_geo_suspected"),
                "parasitic_geo_elevated": rp.get("parasitic_geo_elevated"),
                "parasitic_source": rp.get("parasitic_source"),
                "parasitic_llm_reason": rp.get("parasitic_llm_reason") or "",
            }
            for k, v in para.items():
                pred[k] = v
            page["_parasitic_rerun_at"] = datetime.now(timezone.utc).isoformat()
            page.pop("_parasitic_rerun_error", None)
            assert {k: pred.get(k) for k in PERM_KEYS} == perm_before
            print(
                f"  → parasitic={para['parasitic']} risk={para['parasitic_geo_risk']} "
                f"para_src={para['parasitic_source']} "
                f"reason={(para['parasitic_llm_reason'] or '')[:100]!r}",
                flush=True,
            )
        except Exception as exc:
            print(f"  ERROR {pid}: {exc}", flush=True)
            page["_parasitic_rerun_error"] = f"{exc}\n{traceback.format_exc()[-600:]}"
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp = OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        tmp.replace(OUT)


if __name__ == "__main__":
    main()
