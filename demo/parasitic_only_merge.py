#!/usr/bin/env python3
"""Re-run Mode B + parasitic LLM; merge ONLY parasitic_* fields into existing sheet.

Does not overwrite retrieve/mention/factual/endorsement or permissions_* fields.
Skips p37 (Trustpilot defer_fetch) by default.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Load .env without printing secrets
_env = ROOT / ".env"
if _env.is_file():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k:
            os.environ.setdefault(k, v)

# Force intended fetch path (shell may leave ANTI_GEO_FETCH=httpx / HEADED=auto).
os.environ["ANTI_GEO_FETCH"] = "auto"
os.environ["ANTI_GEO_FETCH_ARCHIVE"] = "auto"
os.environ["ANTI_GEO_FETCH_HEADED"] = "0"
os.environ.setdefault("ANTI_GEO_BROWSER_TIMEOUT", "35")

from anti_geo.investigation import investigation_to_dict, investigate_url  # noqa: E402

OUT = ROOT / "data/permissions_eval/label_sheet_v0_anti_geo.json"
SKIP_IDS = {"p37"}
PARASITIC_KEYS = (
    "parasitic",
    "parasitic_geo_risk",
    "parasitic_geo_suspected",
    "parasitic_geo_elevated",
    "parasitic_source",
    "parasitic_llm_reason",
)
PERM_KEYS = (
    "retrieve_permission",
    "mention_permission",
    "factual_permission",
    "endorsement_permission",
    "permissions_source",
    "permissions_llm_reason",
)


def _parasitic_tier(profile: dict) -> str:
    if profile.get("parasitic_geo_suspected") is True:
        return "suspected"
    if profile.get("parasitic_geo_elevated") or profile.get("status") == "sparse_suspicious":
        return "elevated"
    return "none"


def extract_parasitic(result) -> dict:
    d = investigation_to_dict(result)
    rp = d.get("referral_profile") or {}
    return {
        "parasitic": _parasitic_tier(rp),
        "parasitic_geo_risk": rp.get("parasitic_geo_risk"),
        "parasitic_geo_suspected": rp.get("parasitic_geo_suspected"),
        "parasitic_geo_elevated": rp.get("parasitic_geo_elevated"),
        "parasitic_source": rp.get("parasitic_source"),
        "parasitic_llm_reason": rp.get("parasitic_llm_reason") or "",
    }


def save(payload: dict) -> None:
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["n_ok"] = sum(1 for p in payload["pages"] if p.get("ok"))
    payload["n_error"] = sum(1 for p in payload["pages"] if not p.get("ok"))
    payload["n_pages"] = len(payload["pages"])
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(OUT)


def main() -> None:
    payload = json.loads(OUT.read_text())
    pages = payload["pages"]
    by_id = {p["id"]: p for p in pages}

    rerun_file = ROOT / "data/permissions_eval/_rerun_ids.txt"
    if rerun_file.exists():
        ids = [x.strip() for x in rerun_file.read_text().split(",") if x.strip()]
        ids = [i for i in ids if i in by_id and i not in SKIP_IDS]
    else:
        ids = [p["id"] for p in pages if p["id"] not in SKIP_IDS]

    notes = payload.setdefault("notes", [])
    notes.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "msg": (
                f"Parasitic-only merge (resume-capable) for up to {len(ids)} pages; "
                f"skip {sorted(SKIP_IDS)}; permissions fields preserved"
            ),
        }
    )
    save(payload)

    already = sum(1 for i in ids if by_id[i].get("_parasitic_rerun_at"))
    print(
        f"Starting parasitic-only merge for {len(ids)} ids "
        f"(already done={already}); skip {sorted(SKIP_IDS)}",
        flush=True,
    )

    for i, pid in enumerate(ids, 1):
        page = by_id[pid]
        pred = page.setdefault("predictions", {})
        if page.get("_parasitic_rerun_at") and not page.get("_parasitic_rerun_error"):
            print(f"[{i}/{len(ids)}] skip {pid} (already parasitic-rerun)", flush=True)
            continue

        url = page.get("url")
        query = page.get("query") or ""
        print(f"[{i}/{len(ids)}] {pid} {(url or '')[:80]}", flush=True)
        perm_before = {k: pred.get(k) for k in PERM_KEYS}
        try:
            result = investigate_url(
                url,
                query_intent="commercial",
                query=query,
                engine_name="azure",
                seed_limit=10,
                seed_mode="auto",
                max_fetches_per_seed=20,
                max_verified_referrers=15,
                seed_workers=3,
                fetch_workers=6,
                progress=None,
            )
            para = extract_parasitic(result)
            for k, v in para.items():
                pred[k] = v
            page["_parasitic_rerun_at"] = datetime.now(timezone.utc).isoformat()
            page.pop("_parasitic_rerun_error", None)
            perm_after = {k: pred.get(k) for k in PERM_KEYS}
            assert perm_before == perm_after, (perm_before, perm_after)
            print(
                f"  → parasitic={para['parasitic']} risk={para['parasitic_geo_risk']} "
                f"para_src={para['parasitic_source']} "
                f"reason={(para['parasitic_llm_reason'] or '')[:120]!r}",
                flush=True,
            )
        except Exception as exc:
            print(f"  ERROR {pid}: {exc}", flush=True)
            page["_parasitic_rerun_error"] = f"{exc}\n{traceback.format_exc()[-600:]}"
        save(payload)

    src: dict[str | None, int] = {}
    for p in payload["pages"]:
        if p["id"] in SKIP_IDS:
            continue
        s = (p.get("predictions") or {}).get("parasitic_source")
        src[s] = src.get(s, 0) + 1
    notes.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "msg": f"Parasitic-only merge finished. source_counts={src}",
        }
    )
    save(payload)
    print(f"Done. source_counts={src}", flush=True)


if __name__ == "__main__":
    main()
