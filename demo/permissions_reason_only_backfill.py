#!/usr/bin/env python3
"""Backfill permissions_source + permissions_llm_reason for empty-reason pages only.

Preserves retrieve/mention/factual/endorsement. Uses flock so concurrent writers
cannot clobber the sheet.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

os.environ.setdefault("ANTI_GEO_FETCH", "auto")
os.environ.setdefault("ANTI_GEO_FETCH_ARCHIVE", "auto")
os.environ.setdefault("ANTI_GEO_FETCH_HEADED", "0")
os.environ.setdefault("ANTI_GEO_BROWSER_TIMEOUT", "35")

from anti_geo.decisions import decide_single_source  # noqa: E402
from anti_geo.fetch import fetch_page  # noqa: E402
from anti_geo.scorer import score_source  # noqa: E402

OUT = ROOT / "data/permissions_eval/label_sheet_v0_anti_geo.json"
LOCK = ROOT / "data/permissions_eval/label_sheet_v0_anti_geo.json.lock"
LOG = ROOT / "data/permissions_eval/label_sheet_v0_anti_geo_permissions_reason_backfill.log"
SKIP = {"p37"}


def locked_update(pid: str, fields: dict) -> None:
    with LOCK.open("a+") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            data = json.loads(OUT.read_text())
            for page in data["pages"]:
                if page.get("id") != pid:
                    continue
                pred = page.setdefault("predictions", {})
                pred.update(fields)
                break
            else:
                raise KeyError(pid)
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            notes = data.setdefault("notes", [])
            notes.append(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "msg": f"permissions-reason backfill wrote {pid}",
                }
            )
            tmp = OUT.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2) + "\n")
            tmp.replace(OUT)
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def main() -> None:
    data = json.loads(OUT.read_text())
    targets = []
    for page in data["pages"]:
        pid = page.get("id")
        if pid in SKIP:
            continue
        reason = ((page.get("predictions") or {}).get("permissions_llm_reason") or "").strip()
        if not reason:
            targets.append(page)

    log = LOG.open("a")

    def emit(msg: str) -> None:
        print(msg, flush=True)
        log.write(msg + "\n")
        log.flush()

    emit(
        f"=== permissions-reason backfill start {datetime.now(timezone.utc).isoformat()} "
        f"n={len(targets)} ids={[p['id'] for p in targets]} skip={sorted(SKIP)}"
    )
    if not targets:
        emit("Nothing to do.")
        log.close()
        return

    for i, page in enumerate(targets, 1):
        pid = page["id"]
        # Re-read URL/query from disk in case sheet moved
        live = json.loads(OUT.read_text())
        page = next(p for p in live["pages"] if p["id"] == pid)
        url = page["url"]
        query = page.get("query") or ""
        kept = {
            k: (page.get("predictions") or {}).get(k)
            for k in (
                "retrieve_permission",
                "mention_permission",
                "factual_permission",
                "endorsement_permission",
            )
        }
        emit(f"[{i}/{len(targets)}] {pid} {url[:90]}")
        try:
            fetch = fetch_page(url, timeout=20.0)
            source = score_source(url, fetch, query=query)
            report = decide_single_source(
                source,
                query_intent="commercial",
                query=query,
                use_llm=True,
            )
            reason = report.permissions_llm_reason or ""
            src = report.permissions_source or "heuristic"
            locked_update(
                pid,
                {
                    "permissions_source": src,
                    "permissions_llm_reason": reason,
                },
            )
            emit(f"  → perm_src={src}")
            emit(f"  → reason_full={reason!r}")
            emit(
                f"  → kept={kept['retrieve_permission']}/{kept['mention_permission']}/"
                f"{kept['factual_permission']}/{kept['endorsement_permission']} "
                f"(live_would_be "
                f"{report.permissions.retrieve_permission}/"
                f"{report.permissions.mention_permission}/"
                f"{report.permissions.factual_permission}/"
                f"{report.permissions.endorsement_permission})"
            )
        except Exception as exc:
            emit(f"  ERROR {exc}\n{traceback.format_exc()[-800:]}")

    data = json.loads(OUT.read_text())
    srcs: Counter[str | None] = Counter()
    n_reason = 0
    still_empty = []
    for p in data["pages"]:
        if p.get("id") in SKIP:
            continue
        pr = p.get("predictions") or {}
        srcs[pr.get("permissions_source")] += 1
        if (pr.get("permissions_llm_reason") or "").strip():
            n_reason += 1
        else:
            still_empty.append(p.get("id"))
    emit(
        f"Done. permissions_source={dict(srcs)} with_reason={n_reason}/41 "
        f"still_empty={still_empty} wrote {OUT}"
    )
    log.close()


if __name__ == "__main__":
    main()
