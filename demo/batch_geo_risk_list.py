#!/usr/bin/env python3
"""
Batch Mode A investigations → shard JSON, then merge into a tiered domain list.

Examples:
  PYTHONPATH=src python demo/batch_geo_risk_list.py run \\
    --queries data/geo_risk_batch/queries_shard_a.txt \\
    --out data/geo_risk_batch/shard_a.json

  PYTHONPATH=src python demo/batch_geo_risk_list.py merge \\
    --shards data/geo_risk_batch/shard_a.json data/geo_risk_batch/shard_b.json \\
    --out data/geo_risk_batch/geo_risk_domains.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anti_geo.platform_role import registrable_domain
from anti_geo.progress import make_progress
from anti_geo.query_investigation import (
    DEFAULT_MAX_FETCHES_PER_SEED,
    DEFAULT_MAX_VERIFIED,
    DEFAULT_MIN_SEEDS_BEFORE_STOP,
    DEFAULT_SEED_LIMIT,
    investigate_query,
    query_investigation_to_dict,
)

TIER_ORDER = ("very_high", "high", "medium", "review", "clean")
TIER_RANK = {t: i for i, t in enumerate(TIER_ORDER)}

ON_PAGE_HARD_ACTIONS = frozenset(
    {
        "reject",
        "reject_consensus",
        "block_factual_use",
        "block_endorsement",
    }
)
ON_PAGE_SOFT_ACTIONS = frozenset(
    {
        "attribute_only",
        "require_corroboration",
        "require_authoritative_corroboration",
        "mention_only",
        "downrank",
        "defer_fetch",
    }
)

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
    queries: list[str] = []
    for line in path.read_text().splitlines():
        q = line.strip()
        if q and not q.startswith("#"):
            queries.append(q)
    return queries


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    tmp.replace(path)


def _domain_of(url: str) -> str:
    return registrable_domain(urlparse(url).netloc)


def _row_signals(row: dict[str, Any]) -> dict[str, Any]:
    """Classify on-page vs parasitic severity for one cite row."""
    rp = row.get("referral_profile") or {}
    subs = row.get("subscores") or {}
    semantic = float(
        row.get("semantic_risk")
        if row.get("semantic_risk") is not None
        else subs.get("rhetorical_manipulation")
        or 0.0
    )
    retrieval_manip = float(subs.get("retrieval_manipulation_risk") or 0.0)
    # Hard on-page: LLM hard actions only — style scores are soft telemetry.
    on_page_hard = row.get("llm_action") in ON_PAGE_HARD_ACTIONS and not (
        rp.get("parasitic_geo_suspected") is True
        or (rp.get("referrer_content_high_risk") or 0) >= 2
        or rp.get("referrer_content_coordinated")
    )
    # Soft on-page: elevated rhetoric/retrieval without hard action from page alone
    on_page_soft = (not on_page_hard) and (
        row.get("llm_action") in ON_PAGE_SOFT_ACTIONS
        or semantic >= 0.35
        or retrieval_manip >= 0.35
        or float(row.get("endorsement_risk") or 0.0) >= 0.35
    )

    parasitic_hard = (
        rp.get("parasitic_geo_suspected") is True
        or (rp.get("referrer_content_high_risk") or 0) >= 2
        or bool(rp.get("referrer_content_coordinated"))
    )

    n_verified = int(rp.get("n_verified") or row.get("n_verified") or 0)
    mix = rp.get("mix") or {}
    parasitic_share = row.get("parasitic_verified_share")
    if parasitic_share is None and n_verified > 0:
        from anti_geo.platform_role import is_parasitic_referrer

        refs = rp.get("referrers_verified") or []
        if refs:
            parasit_n = sum(
                1
                for ref in refs
                if is_parasitic_referrer(
                    url=ref.get("url") or "",
                    role=ref.get("role") or "",
                    content_high_risk=bool(ref.get("content_high_risk")),
                )
            )
            parasitic_share = parasit_n / n_verified
    editorial = mix.get("editorial", 0) + mix.get("institutional", 0)

    soft_parasitic_band = (
        n_verified >= 10
        and editorial == 0
        and parasitic_share is not None
        and 0.35 <= float(parasitic_share) <= 0.5
    )
    zero_verified_ai_cite = (
        n_verified == 0
        and rp.get("discovery_status") in ("success", "partial")
        and rp.get("status") not in (None, "inconclusive", "skipped")
        and row.get("content_role") not in ("editorial", "institutional")
    )
    parasitic_soft = (not parasitic_hard) and (
        rp.get("status") == "sparse_suspicious"
        or (rp.get("referrer_content_high_risk") or 0) == 1
        or soft_parasitic_band
        or bool(rp.get("parasitic_geo_elevated"))
        or (
            float(rp.get("parasitic_geo_risk") or 0.0) >= 0.35
            and rp.get("parasitic_geo_suspected") is not True
        )
        or zero_verified_ai_cite
    )

    status = rp.get("status") or ("skipped" if row.get("is_ugc") else "unknown")
    confidence = rp.get("confidence") or "low"
    evidence_strong = (
        (not row.get("is_ugc"))
        and n_verified >= 10
        and status in ("complete", "sparse")
        and confidence != "low"
    )
    # Manual-review path: parasitic_geo_suspected is None (coordinated_commercial)
    needs_manual = rp.get("parasitic_geo_suspected") is None and status in ("complete", "sparse")
    evidence_weak = bool(
        row.get("is_ugc")
        or status in ("inconclusive", "skipped", "sparse_suspicious", "unknown")
        or n_verified < 5
        or needs_manual
    )

    mechanisms: list[str] = []
    if on_page_hard or on_page_soft:
        mechanisms.append("on_page")
    if parasitic_hard or parasitic_soft:
        mechanisms.append("referrer")

    return {
        "on_page_hard": on_page_hard,
        "on_page_soft": on_page_soft,
        "parasitic_hard": parasitic_hard,
        "parasitic_soft": parasitic_soft,
        "evidence_strong": evidence_strong,
        "evidence_weak": evidence_weak,
        "mechanisms": mechanisms,
        "semantic_risk": semantic,
        "retrieval_manipulation_risk": retrieval_manip,
        "n_verified": n_verified,
        "parasitic_geo_suspected": rp.get("parasitic_geo_suspected"),
        "referral_status": status,
        "referral_confidence": confidence,
        "referrer_content_high_risk": rp.get("referrer_content_high_risk") or 0,
        "referrer_content_coordinated": bool(rp.get("referrer_content_coordinated")),
        "llm_action": row.get("llm_action"),
        "is_ugc": bool(row.get("is_ugc")),
    }


def tier_from_signals(sig: dict[str, Any]) -> str:
    oh, ph = sig["on_page_hard"], sig["parasitic_hard"]
    os_, ps = sig["on_page_soft"], sig["parasitic_soft"]
    strong, weak = sig["evidence_strong"], sig["evidence_weak"]

    if oh and ph and strong and not weak:
        return "very_high"
    if (oh or ph) and strong and not weak:
        return "high"
    if oh or ph:
        return "medium"  # hard signal, weak/insufficient sample
    if os_ or ps:
        return "medium" if strong else "review"
    if sig["is_ugc"] or weak or sig["referral_status"] in (
        "inconclusive",
        "skipped",
        "unknown",
    ):
        return "review"
    if sig["llm_action"] in (None, "pass") and not (os_ or ps or oh or ph):
        return "clean"
    return "review"


def enrich_query_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach per-row tier signals; keep original investigation payload."""
    enriched_rows = []
    for row in payload.get("rows") or []:
        sig = _row_signals(row)
        tier = tier_from_signals(sig)
        enriched_rows.append({**row, "list_tier": tier, "tier_signals": sig})
    return {**payload, "rows": enriched_rows}


def run_shard(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    _load_dotenv(root / ".env")

    queries = _read_queries(Path(args.queries))
    out = Path(args.out)
    if args.resume and out.is_file():
        state = json.loads(out.read_text())
        done = {r["query"] for r in state.get("investigations") or [] if not r.get("error")}
        print(f"Resume: {len(done)} queries already done", flush=True)
    else:
        state = {
            "shard": out.stem,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "engine": args.engine,
            "investigations": [],
        }
        done = set()

    pending = [q for q in queries if q not in done]
    print(
        f"Shard {out.name}: {len(pending)} pending / {len(queries)} total "
        f"(AZURE_API_MAX_CONCURRENCY={os.environ.get('AZURE_API_MAX_CONCURRENCY', 'default')})",
        flush=True,
    )

    for i, query in enumerate(pending, 1):
        print(f"\n=== [{i}/{len(pending)}] {query!r} ===", flush=True)
        t0 = time.time()
        progress = make_progress(enabled=True, label=f"Mode A: {query[:40]}", unit="cites")
        try:
            result = investigate_query(
                query,
                query_intent=args.intent,
                engine_name=args.engine,
                site_workers=args.site_workers,
                seed_workers=args.seed_workers,
                fetch_workers=args.fetch_workers,
                seed_limit=DEFAULT_SEED_LIMIT,
                seed_mode=args.seed_mode,
                query_delay_s=args.query_delay,
                max_fetches_per_seed=DEFAULT_MAX_FETCHES_PER_SEED,
                max_verified_referrers=DEFAULT_MAX_VERIFIED,
                min_seeds_before_verified_stop=DEFAULT_MIN_SEEDS_BEFORE_STOP,
                adaptive_stop=True,
                deep=False,
                progress=progress,
            )
            payload = enrich_query_dict(query_investigation_to_dict(result))
            # Attach semantic_risk onto rows from live objects when missing in dict
            for j, row_obj in enumerate(result.rows):
                if j < len(payload["rows"]) and row_obj.single_page and row_obj.single_page.source:
                    payload["rows"][j]["semantic_risk"] = row_obj.single_page.source.semantic_risk
                    # Recompute tier with real semantic_risk
                    sig = _row_signals(payload["rows"][j])
                    payload["rows"][j]["tier_signals"] = sig
                    payload["rows"][j]["list_tier"] = tier_from_signals(sig)
            entry = {
                "query": query,
                "elapsed_s": round(time.time() - t0, 1),
                "error": None,
                "result": payload,
            }
        except Exception as exc:  # noqa: BLE001 — keep shard going
            entry = {
                "query": query,
                "elapsed_s": round(time.time() - t0, 1),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "result": None,
            }
            print(f"ERROR: {entry['error']}", flush=True)

        state["investigations"].append(entry)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write_json(out, state)
        print(
            f"Saved → {out} ({entry['elapsed_s']}s"
            + (f", error={entry['error']}" if entry.get("error") else "")
            + ")",
            flush=True,
        )

    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(out, state)
    print(f"\nShard complete: {out}", flush=True)


def _worse_tier(a: str, b: str) -> str:
    return a if TIER_RANK[a] <= TIER_RANK[b] else b


def merge_shards(args: argparse.Namespace) -> None:
    domains: dict[str, dict[str, Any]] = {}
    query_errors: list[dict[str, Any]] = []

    for shard_path in args.shards:
        data = json.loads(Path(shard_path).read_text())
        for inv in data.get("investigations") or []:
            if inv.get("error"):
                query_errors.append(
                    {"query": inv.get("query"), "error": inv["error"], "shard": str(shard_path)}
                )
                continue
            result = inv.get("result") or {}
            query = result.get("query") or inv.get("query")
            for row in result.get("rows") or []:
                url = row.get("url") or ""
                if not url:
                    continue
                domain = _domain_of(url)
                sig = row.get("tier_signals") or _row_signals(row)
                tier = row.get("list_tier") or tier_from_signals(sig)
                # Re-tier if we now have semantic_risk
                if "semantic_risk" in row:
                    sig = _row_signals(row)
                    tier = tier_from_signals(sig)

                entry = domains.setdefault(
                    domain,
                    {
                        "domain": domain,
                        "list_tier": "clean",
                        "mechanisms": [],
                        "queries_seen": [],
                        "sample_urls": [],
                        "url_tiers": [],
                        "evidence": [],
                    },
                )
                if query and query not in entry["queries_seen"]:
                    entry["queries_seen"].append(query)
                if url not in entry["sample_urls"]:
                    entry["sample_urls"].append(url)
                entry["url_tiers"].append(tier)
                for m in sig.get("mechanisms") or []:
                    if m not in entry["mechanisms"]:
                        entry["mechanisms"].append(m)
                entry["list_tier"] = _worse_tier(entry["list_tier"], tier)
                entry["evidence"].append(
                    {
                        "query": query,
                        "url": url,
                        "list_tier": tier,
                        "llm_action": row.get("llm_action"),
                        "parasitic_geo_suspected": sig.get("parasitic_geo_suspected"),
                        "n_verified": sig.get("n_verified"),
                        "semantic_risk": sig.get("semantic_risk"),
                        "referrer_content_high_risk": sig.get(
                            "referrer_content_high_risk"
                        ),
                        "is_ugc": sig.get("is_ugc"),
                    }
                )

    # ≥2 independent queries gate for very_high / high
    for entry in domains.values():
        nq = len(entry["queries_seen"])
        if entry["list_tier"] in ("very_high", "high") and nq < 2:
            entry["list_tier"] = "medium"
            entry["notes"] = [
                f"Demoted from top tier: only {nq} independent query hit(s)."
            ]
        entry["sample_urls"] = entry["sample_urls"][:8]
        # Keep evidence compact
        entry["evidence"] = entry["evidence"][:20]

    ranked = sorted(
        domains.values(),
        key=lambda e: (TIER_RANK[e["list_tier"]], e["domain"]),
    )
    by_tier = {t: [] for t in TIER_ORDER}
    for e in ranked:
        by_tier[e["list_tier"]].append(e["domain"])

    out_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "tiers": list(TIER_ORDER),
            "very_high": "on-page hard AND parasitic hard AND strong referral evidence",
            "high": "on-page hard OR parasitic hard AND strong referral evidence",
            "medium": "hard signal with weak evidence, OR soft+strong (parasitic_geo_elevated / soft band)",
            "review": "soft/weak/UGC/inconclusive — not clean",
            "clean": "pass with no soft/hard flags and usable referral",
            "domain_gate": "very_high/high require ≥2 independent queries else demote to medium",
            "on_page_hard": "hard LLM actions (reject/block_*) not attributed to parasitic; style alone is soft",
            "on_page_soft": "soft LLM actions and/or elevated rhetoric/retrieval/endorsement_risk telemetry",
            "parasitic_geo_suspected_share": "parasitic share > 0.5 at N≥10 with no editorial",
            "parasitic_geo_risk": "0.5-ish blend of parasitic share + count/5; editorial dampens",
            "parasitic_geo_elevated": "parasitic_geo_risk≥0.35 or soft share band or count≥3@N≥5 → downrank",
        },
        "counts_by_tier": {t: len(by_tier[t]) for t in TIER_ORDER},
        "domains_by_tier": by_tier,
        "domains": ranked,
        "query_errors": query_errors,
        "shards": [str(p) for p in args.shards],
    }
    _atomic_write_json(Path(args.out), out_payload)
    print(json.dumps(out_payload["counts_by_tier"], indent=2))
    print(f"Wrote {args.out} ({len(ranked)} domains)", flush=True)


def _mode_b_to_enriched_row(result: Any) -> dict[str, Any]:
    """Convert Mode B InvestigationResult into a Mode-A-like enriched row."""
    from anti_geo.investigation import (
        investigation_to_dict,
        parasitic_count_from_verified,
        parasitic_share_from_verified,
    )
    from anti_geo.platform_role import is_ugc_role

    payload = investigation_to_dict(result)
    rp = payload.get("referral_profile") or {}
    sp = payload.get("single_page") or {}
    source = sp.get("source") or {}
    role = payload.get("content_role") or ""
    n_verified = rp.get("n_verified")
    refs = getattr(result.referral_profile, "referrers_verified", None) or []
    row = {
        "url": payload.get("target_url"),
        "is_ugc": is_ugc_role(role),
        "content_role": role,
        "llm_action": payload.get("llm_action"),
        "llm_actions": payload.get("llm_actions") or [],
        "source_trust": source.get("trust_score"),
        "endorsement_risk": (sp.get("subscores") or {}).get("endorsement_risk"),
        "n_verified": n_verified,
        "parasitic_verified_share": parasitic_share_from_verified(refs),
        "parasitic_verified_count": parasitic_count_from_verified(refs),
        "mode_b_error": None,
        "subscores": sp.get("subscores"),
        "permissions": sp.get("permissions"),
        "referral_profile": rp,
        "semantic_risk": source.get("semantic_risk"),
        "verdict": payload.get("verdict"),
        "seed_queries": payload.get("seed_queries"),
        "seed_source": payload.get("seed_source"),
    }
    sig = _row_signals(row)
    row["tier_signals"] = sig
    row["list_tier"] = tier_from_signals(sig)
    return row


def run_deep_urls(args: argparse.Namespace) -> None:
    """Deep Mode B over a URL list (UGC-oriented seeds + high verified caps)."""
    root = Path(__file__).resolve().parents[1]
    _load_dotenv(root / ".env")

    from anti_geo.investigation import investigate_url

    urls = _read_queries(Path(args.urls))  # one URL per line
    out = Path(args.out)
    if args.resume and out.is_file():
        state = json.loads(out.read_text())
        done = {
            r.get("target_url")
            for r in state.get("investigations") or []
            if r.get("target_url") and not r.get("error")
        }
        print(f"Resume: {len(done)} URLs already done", flush=True)
    else:
        state = {
            "shard": out.stem,
            "mode": "deep_mode_b",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "engine": args.engine,
            "investigations": [],
        }
        done = set()

    pending = [u for u in urls if u not in done]
    print(
        f"Deep Mode B: {len(pending)} pending / {len(urls)} total "
        f"(AZURE_API_MAX_CONCURRENCY={os.environ.get('AZURE_API_MAX_CONCURRENCY', 'default')})",
        flush=True,
    )

    for i, url in enumerate(pending, 1):
        print(f"\n=== [{i}/{len(pending)}] deep {url} ===", flush=True)
        t0 = time.time()
        progress = make_progress(enabled=True, label=f"Mode B: {url[:40]}", unit="seeds")
        try:
            result = investigate_url(
                url,
                query_intent=args.intent,
                engine_name=args.engine,
                seed_limit=12,
                seed_mode=args.seed_mode,
                query_delay_s=args.query_delay,
                max_fetches_per_seed=30,
                max_verified_referrers=50,
                min_seeds_before_verified_stop=4,
                progress=progress,
                seed_workers=args.seed_workers,
                fetch_workers=args.fetch_workers,
            )
            row = _mode_b_to_enriched_row(result)
            entry = {
                "query": f"mode_b_deep:{url}",
                "target_url": result.target_url,
                "elapsed_s": round(time.time() - t0, 1),
                "error": None,
                "result": {
                    "query": f"mode_b_deep:{url}",
                    "query_intent": args.intent,
                    "cited_urls": [result.target_url],
                    "rows": [row],
                    "notes": [
                        f"Deep Mode B; seeds={result.seed_source}; "
                        f"n_verified={result.referral_profile.n_verified}; "
                        f"parasitic_geo_suspected={result.referral_profile.parasitic_geo_suspected}"
                    ],
                },
            }
        except Exception as exc:  # noqa: BLE001
            entry = {
                "query": f"mode_b_deep:{url}",
                "target_url": url,
                "elapsed_s": round(time.time() - t0, 1),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "result": None,
            }
            print(f"ERROR: {entry['error']}", flush=True)

        state["investigations"].append(entry)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write_json(out, state)
        print(f"Saved → {out} ({entry['elapsed_s']}s)", flush=True)

    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(out, state)
    print(f"\nDeep shard complete: {out}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch GEO risk list builder")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run Mode A over a query list into a shard JSON")
    run_p.add_argument("--queries", type=Path, required=True)
    run_p.add_argument("--out", type=Path, required=True)
    run_p.add_argument("--engine", default="azure", choices=["azure", "perplexity", "mock"])
    run_p.add_argument("--intent", default="commercial")
    run_p.add_argument("--site-workers", type=int, default=4)
    run_p.add_argument("--seed-workers", type=int, default=2)
    run_p.add_argument("--fetch-workers", type=int, default=6)
    run_p.add_argument("--seed-mode", default="auto", choices=["auto", "template", "llm"])
    run_p.add_argument("--query-delay", type=float, default=1.0)
    run_p.add_argument("--resume", action="store_true")

    deep_p = sub.add_parser("deep-urls", help="Deep Mode B over URL list (UGC seeds)")
    deep_p.add_argument("--urls", type=Path, required=True)
    deep_p.add_argument("--out", type=Path, required=True)
    deep_p.add_argument("--engine", default="azure", choices=["azure", "perplexity", "mock"])
    deep_p.add_argument("--intent", default="commercial")
    deep_p.add_argument("--seed-workers", type=int, default=2)
    deep_p.add_argument("--fetch-workers", type=int, default=6)
    deep_p.add_argument("--seed-mode", default="auto", choices=["auto", "template", "llm"])
    deep_p.add_argument("--query-delay", type=float, default=1.5)
    deep_p.add_argument("--resume", action="store_true")

    merge_p = sub.add_parser("merge", help="Merge shard JSONs into tiered domain list")
    merge_p.add_argument("--shards", type=Path, nargs="+", required=True)
    merge_p.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    if args.cmd == "run":
        run_shard(args)
    elif args.cmd == "deep-urls":
        run_deep_urls(args)
    else:
        merge_shards(args)


if __name__ == "__main__":
    main()
