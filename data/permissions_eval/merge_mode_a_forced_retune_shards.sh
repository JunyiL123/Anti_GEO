#!/usr/bin/env bash
# Merge two Mode A forced retune shards into one JSON (sorted by page id).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
STAMP="retune_20260727"
A="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_${STAMP}_shard_a.json"
B="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_${STAMP}_shard_b.json"
OUT="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_${STAMP}.json"
PY="/opt/homebrew/opt/python@3.11/bin/python3.11"

"$PY" - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone

a = json.loads(Path("$A").read_text())
b = json.loads(Path("$B").read_text())
by_id = {}
for page in (a.get("pages") or []) + (b.get("pages") or []):
    by_id[page["id"]] = page
pages = sorted(by_id.values(), key=lambda p: int(str(p["id"]).lstrip("p")))
out = {
    "description": a.get("description") or b.get("description"),
    "created_at": datetime.now(timezone.utc).isoformat(),
    "merged_from": ["$A", "$B"],
    "sheet": a.get("sheet") or b.get("sheet"),
    "engine": a.get("engine") or b.get("engine"),
    "query_intent": a.get("query_intent") or b.get("query_intent"),
    "forced_cites": a.get("forced_cites", True),
    "mode_b_ugc": a.get("mode_b_ugc", True),
    "seed_limit": a.get("seed_limit"),
    "max_verified": a.get("max_verified"),
    "skip_ids": sorted(set(a.get("skip_ids") or []) | set(b.get("skip_ids") or [])),
    "n_pages": len(pages),
    "n_ok": sum(1 for p in pages if p.get("ok")),
    "n_error": sum(1 for p in pages if not p.get("ok")),
    "pages": pages,
}
Path("$OUT").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
print(f"merged {OUT} pages={out['n_pages']} ok={out['n_ok']} err={out['n_error']}")
PY
