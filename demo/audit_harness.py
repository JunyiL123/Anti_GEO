#!/usr/bin/env python3
"""
Longitudinal audit harness for live answer engines (mock offline, Perplexity live).

Examples:
  PYTHONPATH=src python3 demo/audit_harness.py --engine mock
  PERPLEXITY_API_KEY=... PYTHONPATH=src python3 demo/audit_harness.py --engine perplexity

  PYTHONPATH=src python3 demo/audit_harness.py --engine mock --target-domain pcmag.com
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anti_geo.audit.engines import get_engine
from anti_geo.audit.report import format_audit_summary, run_audit, save_summary, summarize_audit
from anti_geo.audit.referral import build_referral_audit_report, format_referral_audit_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Anti-GEO longitudinal audit harness")
    parser.add_argument("--engine", default="mock", choices=["mock", "perplexity"])
    parser.add_argument("--query-set", default="default")
    parser.add_argument("--log-dir", default="data/audits")
    parser.add_argument("--with-overlay", action="store_true", help="Score cited URLs with analyze_url")
    parser.add_argument("--target-domain", default=None, help="Target domain for referral graph report")
    parser.add_argument("--fixture", default=None, help="Mock engine JSONL fixture path")
    args = parser.parse_args()

    fixture_path = Path(args.fixture) if args.fixture else None
    engine = get_engine(args.engine, fixture_path=fixture_path)
    log_dir = Path(args.log_dir)

    audit_run = run_audit(engine, query_set=args.query_set, log_dir=log_dir)
    summary = summarize_audit(
        audit_run.records,
        with_overlay=args.with_overlay,
        target_domain=args.target_domain,
    )

    print(format_audit_summary(summary))
    if args.target_domain:
        referral = build_referral_audit_report(audit_run.records, args.target_domain)
        print("\n── Referral graph ──")
        print(format_referral_audit_report(referral))

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    summary_path = log_dir / f"summary_{date_str}.json"
    save_summary(summary, summary_path)
    print(f"\nWrote log: {log_dir / audit_run.run_id}.jsonl")
    print(f"Wrote summary: {summary_path}")


if __name__ == "__main__":
    main()
