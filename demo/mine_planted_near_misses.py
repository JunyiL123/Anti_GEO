#!/usr/bin/env python3
"""
Re-fetch verified referrers from geo-risk shard JSON and triage planting shapes.

Buckets (see diagnose_planted_mention):
  soft_sell_near_miss  — entity present, story+consumer, soft-placement OFF
  hard_endorsement     — open recommend/best language with entity present
  planted_hit          — current planted_mention detector True
  review_framed        — review/comparison framing
  other_l1             — authority / front-load / comparative flags
  clean_or_other       — none of the above

Example:
  PYTHONPATH=src python demo/mine_planted_near_misses.py \\
    --shards data/geo_risk_batch/shard_*.json \\
    --out data/geo_risk_batch/planted_near_misses.json \\
    --limit 80
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anti_geo.content_signals import diagnose_planted_mention
from anti_geo.fetch import fetch_page
from anti_geo.platform_role import registrable_domain
from anti_geo.referrer_content import entity_scoped_excerpt


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


def _publisher(url: str) -> str:
    domain = registrable_domain(urlparse(url).netloc)
    return domain.split(".")[0] if domain else ""


def _entity_candidates(target_url: str, claim_entity: str, ref: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for cand in (
        claim_entity,
        ref.get("matched_marker") or "",
        _publisher(target_url),
    ):
        c = " ".join(str(cand).strip().split())
        if len(c) >= 3 and c.lower() not in {x.lower() for x in out}:
            out.append(c)
    return out


def _collect_jobs(shard_paths: list[Path]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in shard_paths:
        data = json.loads(path.read_text())
        for inv in data.get("investigations") or []:
            result = inv.get("result") or {}
            if not result:
                continue
            claim = str(result.get("claim_entity") or "")
            query = str(result.get("query") or inv.get("query") or "")
            for row in result.get("rows") or []:
                target = str(row.get("url") or "")
                if not target:
                    continue
                rp = row.get("referral_profile") or {}
                for ref in rp.get("referrers_verified") or []:
                    ref_url = str(ref.get("url") or "")
                    if not ref_url:
                        continue
                    key = (target.rstrip("/").lower(), ref_url.rstrip("/").lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    jobs.append(
                        {
                            "shard": path.name,
                            "query": query,
                            "target_url": target,
                            "claim_entity": claim,
                            "ref_url": ref_url,
                            "ref_role": ref.get("role") or "",
                            "matched_marker": ref.get("matched_marker") or "",
                            "seed_query": ref.get("seed_query") or "",
                            "prior_flags": list(ref.get("content_flags") or []),
                            "prior_high_risk": bool(ref.get("content_high_risk")),
                            "manipulability": float(ref.get("content_manipulability") or 0.0),
                        }
                    )
    return jobs


def _priority(job: dict[str, Any]) -> tuple[int, float]:
    """UGC / high-manip first."""
    ugc = 0 if job.get("ref_role") == "ugc_thread" else 1
    return (ugc, -float(job.get("manipulability") or 0.0))


def _diagnose_with_entities(text: str, entities: list[str]) -> tuple[str, dict[str, Any]]:
    """Try each entity candidate; prefer interesting buckets."""
    rank = {
        "soft_sell_near_miss": 0,
        "planted_hit": 1,
        "hard_endorsement": 2,
        "review_framed": 3,
        "other_l1": 4,
        "clean_or_other": 5,
    }
    best_ent = entities[0] if entities else ""
    best = diagnose_planted_mention(text, entity=best_ent or None)
    for ent in entities:
        diag = diagnose_planted_mention(text, entity=ent)
        if rank.get(str(diag["bucket"]), 9) < rank.get(str(best["bucket"]), 9):
            best = diag
            best_ent = ent
        elif diag["bucket"] == best["bucket"] and diag.get("entity_present") and not best.get(
            "entity_present"
        ):
            best = diag
            best_ent = ent
    return best_ent, best  # type: ignore[return-value]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--shards",
        nargs="+",
        type=Path,
        required=True,
        help="Shard JSON paths (glob expansion is shell's job)",
    )
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=80, help="Max referrers to fetch")
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    _load_dotenv(root / ".env")

    jobs = _collect_jobs(args.shards)
    jobs.sort(key=_priority)
    if args.limit > 0:
        jobs = jobs[: args.limit]

    rows: list[dict[str, Any]] = []
    done_urls: set[str] = set()
    if args.resume and args.out.is_file():
        prev = json.loads(args.out.read_text())
        rows = list(prev.get("rows") or [])
        done_urls = {str(r.get("ref_url") or "").rstrip("/").lower() for r in rows}

    pending = [j for j in jobs if j["ref_url"].rstrip("/").lower() not in done_urls]
    print(
        f"jobs={len(jobs)} pending={len(pending)} resume_rows={len(rows)}",
        flush=True,
    )

    for i, job in enumerate(pending, 1):
        ref_url = job["ref_url"]
        entities = _entity_candidates(job["target_url"], job["claim_entity"], job)
        print(f"[{i}/{len(pending)}] {ref_url[:70]} entities={entities}", flush=True)
        try:
            fr = fetch_page(ref_url, timeout=15.0)
        except Exception as exc:  # noqa: BLE001
            rows.append({**job, "error": str(exc), "bucket": "fetch_error"})
            _write(args.out, rows)
            continue

        if not fr.ok or not (fr.text or "").strip():
            rows.append(
                {
                    **job,
                    "error": fr.error or f"status={fr.status_code}",
                    "bucket": "fetch_error",
                }
            )
            _write(args.out, rows)
            time.sleep(args.delay)
            continue

        entity = entities[0] if entities else _publisher(job["target_url"])
        excerpt, seg_role = entity_scoped_excerpt(
            ref_url,
            text=fr.text,
            segments=fr.segments,
            entity=entity,
            marker=str(job.get("matched_marker") or ""),
        )
        if not excerpt.strip():
            excerpt = (fr.text or "")[:1200]
            seg_role = "body"

        used_entity, diag = _diagnose_with_entities(excerpt, entities or [entity])
        rows.append(
            {
                **job,
                "entity_used": used_entity,
                "entities_tried": entities,
                "segment_role": seg_role,
                "excerpt": excerpt[:800],
                "fetch_ok": True,
                "word_count": diag.get("word_count"),
                **{k: diag[k] for k in diag},
            }
        )
        _write(args.out, rows)
        time.sleep(args.delay)

    _write(args.out, rows)
    _print_summary(rows)


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    buckets = Counter(str(r.get("bucket") or "unknown") for r in rows)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_rows": len(rows),
        "counts_by_bucket": dict(buckets),
        "rows": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    tmp.replace(path)


def _print_summary(rows: list[dict[str, Any]]) -> None:
    buckets = Counter(str(r.get("bucket") or "unknown") for r in rows)
    print("\n=== bucket counts ===", flush=True)
    for k, n in buckets.most_common():
        print(f"  {k}: {n}", flush=True)

    interesting = ("soft_sell_near_miss", "hard_endorsement", "planted_hit", "other_l1")
    print("\n=== interesting samples ===", flush=True)
    shown = 0
    for r in rows:
        if r.get("bucket") not in interesting:
            continue
        print(
            f"\n[{r.get('bucket')}] entity={r.get('entity_used')} "
            f"soft_placed={r.get('soft_placed')} endorsement={r.get('hard_endorsement')} "
            f"flags={r.get('l1_flags')}",
            flush=True,
        )
        print(f"  ref: {r.get('ref_url')}", flush=True)
        print(f"  reasons: {r.get('reasons')}", flush=True)
        ex = (r.get("excerpt") or "").replace("\n", " ")
        print(f"  excerpt: {ex[:280]}", flush=True)
        shown += 1
        if shown >= 12:
            break
    if shown == 0:
        print("  (none)", flush=True)


if __name__ == "__main__":
    main()
