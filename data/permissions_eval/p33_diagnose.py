#!/usr/bin/env python3
"""Diagnose p33: timed stages of investigate_url, explicit step prints."""
from __future__ import annotations

import faulthandler
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

faulthandler.enable()

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    k, v = k.strip(), v.strip().strip("'").strip('"')
    if k and k not in os.environ:
        os.environ[k] = v

from anti_geo.decisions import decide_single_source  # noqa: E402
from anti_geo.audit.engines import get_engine  # noqa: E402
from anti_geo.fetch import fetch_page  # noqa: E402
from anti_geo.investigation import (  # noqa: E402
    discover_referrers,
    extract_page_metadata,
    resolve_seed_queries,
)
from anti_geo.parasitic_llm import maybe_apply_parasitic_llm  # noqa: E402
from anti_geo.permissions import derive_llm_actions  # noqa: E402
from anti_geo.platform_role import classify_content_role  # noqa: E402
from anti_geo.scorer import score_source  # noqa: E402


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}", flush=True)


def main() -> None:
    url = (
        "https://www.headphonesty.com/2025/11/"
        "reddit-comments-most-recommended-headphones-complaints/"
    )
    query = "best headphones forums"
    out = ROOT / "data/permissions_eval/p33_diagnose_result.json"
    t_all = time.monotonic()
    log(f"START url={url}")

    stop = threading.Event()

    def watchdog() -> None:
        while not stop.wait(60):
            log(f"WATCHDOG alive threads={threading.active_count()}")

    threading.Thread(target=watchdog, daemon=True, name="watchdog").start()

    try:
        t0 = time.monotonic()
        log("step fetch_page")
        fetch = fetch_page(url, timeout=12.0)
        log(
            f"fetch done {time.monotonic()-t0:.1f}s engine={fetch.fetch_engine} "
            f"ok={fetch.ok} status={fetch.status_code} err={fetch.error} "
            f"text_len={len(fetch.text or '')}"
        )

        t0 = time.monotonic()
        log("step score_source")
        source = score_source(url, fetch, query=query)
        log(f"score_source done {time.monotonic()-t0:.1f}s fetch_ok={source.fetch_ok}")

        t0 = time.monotonic()
        log("step decide_single_source (may call permissions LLM)")
        report = decide_single_source(source, "commercial", query=query, use_llm=None)
        log(
            f"decide_single_source done {time.monotonic()-t0:.1f}s "
            f"perm_src={getattr(report, 'permissions_source', None)}"
        )

        t0 = time.monotonic()
        log("step classify_content_role")
        role = classify_content_role(url, fetch=fetch, source=source)
        log(f"role done {time.monotonic()-t0:.1f}s role={role}")

        t0 = time.monotonic()
        log("step extract_page_metadata + resolve_seed_queries")
        meta = extract_page_metadata(fetch)
        seeds, seed_source, seed_conf = resolve_seed_queries(
            role,
            meta,
            url=fetch.final_url or url,
            fetch=fetch,
            source=source,
            limit=10,
            mode="auto",
            seed_pack="default",
        )
        log(
            f"seeds done {time.monotonic()-t0:.1f}s n={len(seeds)} "
            f"src={seed_source} conf={seed_conf}"
        )

        engine = get_engine("azure")
        commercial_tier = "none"
        if source.page_context and source.page_context.commercial_tier:
            commercial_tier = source.page_context.commercial_tier

        t0 = time.monotonic()
        log("step discover_referrers (Mode B — likely hang site)")
        profile = discover_referrers(
            url,
            meta.entity,
            seeds,
            engine,
            org=meta.org,
            aliases=meta.aliases,
            max_fetches_per_seed=20,
            max_verified_referrers=15,
            min_seeds_before_verified_stop=4,
            target_role=role,
            target_commercial_tier=commercial_tier,
            seed_workers=3,
            fetch_workers=6,
        )
        log(
            f"discover_referrers done {time.monotonic()-t0:.1f}s "
            f"status={profile.status} n_verified={profile.n_verified} "
            f"risk={profile.parasitic_geo_risk}"
        )

        t0 = time.monotonic()
        log("step parasitic LLM hybrid")
        maybe_apply_parasitic_llm(
            profile,
            target_url=fetch.final_url or url,
            content_role=role,
            metadata=meta,
            use_llm=None,
            fetch_ok=True,
            fetch_failure_kind=None,
        )
        log(
            f"parasitic LLM done {time.monotonic()-t0:.1f}s "
            f"src={getattr(profile, 'parasitic_source', None)} "
            f"risk={profile.parasitic_geo_risk}"
        )

        primary, actions = (
            derive_llm_actions(report.permissions, report.subscores)
            if report.permissions and report.subscores
            else (report.recommended_action, [report.recommended_action])
        )
        elapsed = time.monotonic() - t_all
        summary = {
            "ok": True,
            "elapsed_s": round(elapsed, 1),
            "content_role": role,
            "permissions": {
                "retrieve": report.permissions.retrieve_permission,
                "mention": report.permissions.mention_permission,
                "factual": report.permissions.factual_permission,
                "endorsement": report.permissions.endorsement_permission,
                "source": report.permissions_source,
            },
            "parasitic_geo_risk": profile.parasitic_geo_risk,
            "parasitic_source": getattr(profile, "parasitic_source", None),
            "referral_status": profile.status,
            "n_verified": profile.n_verified,
            "llm_action": primary,
            "seed_source": seed_source,
            "n_seeds": len(seeds),
        }
        out.write_text(json.dumps(summary, indent=2) + "\n")
        log(f"DONE {elapsed:.1f}s {json.dumps(summary)}")
        log(f"wrote {out}")
    except Exception:
        log(f"FAIL after {time.monotonic()-t_all:.1f}s\n{traceback.format_exc()}")
        raise
    finally:
        stop.set()


if __name__ == "__main__":
    main()
