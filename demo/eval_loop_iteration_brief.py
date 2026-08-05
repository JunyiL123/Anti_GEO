#!/usr/bin/env python3
"""Iteration brief: error buckets + knob-freeze decisions from CM / sheets.

Offline-only. Does not edit src/anti_geo/. Prints which fields are frozen
(already ≥ promote/stop bar) vs active gaps.

Example:
  PYTHONPATH=src python demo/eval_loop_iteration_brief.py \\
    --cm-json data/permissions_eval/confusion_matrices_clamp_20260803_no_defer_match.json \\
    --anti-geo data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_clamp_20260803_no_defer_match.json \\
    --adjudication data/permissions_eval/label_sheet_v0_adjudication.json \\
    --out data/permissions_eval/candidates/iteration_brief_clamp.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_DEMO = Path(__file__).resolve().parent
sys.path.insert(0, str(_DEMO))

from eval_loop_lib import (  # noqa: E402
    DEFAULT_PROTOCOL,
    FIELDS,
    extract_error_buckets,
    field_bars,
    knob_decisions,
    load_json,
    load_protocol,
    macro_f1_from_cm,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cm-json", type=Path, required=True)
    parser.add_argument("--anti-geo", type=Path, default=None)
    parser.add_argument("--adjudication", type=Path, default=None)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/permissions_eval/candidates/iteration_brief.md"),
    )
    args = parser.parse_args()

    protocol = load_protocol(args.protocol)
    cm = load_json(args.cm_json)
    scores = macro_f1_from_cm(cm)
    bars = field_bars(protocol)
    field_meta = (protocol.get("promote_stop_bars") or {}).get("fields") or {}
    decisions = knob_decisions(scores, bars, field_meta=field_meta)

    errors: list[dict] = []
    if args.anti_geo and args.adjudication:
        errors = extract_error_buckets(load_json(args.anti_geo), load_json(args.adjudication))

    freeze = [f for f, d in decisions.items() if d["action"] == "freeze"]
    active = [f for f, d in decisions.items() if d["action"] == "active"]
    monitor = [f for f, d in decisions.items() if d["action"] == "monitor_only"]

    err_by_field = Counter(e["field"] for e in errors)
    # Prefer showing active-field errors first.
    show_errors = sorted(
        errors,
        key=lambda e: (0 if e["field"] in active else 1, e["field"], e["id"]),
    )

    paper = protocol.get("paper") or {}
    lines = [
        "# Eval-loop iteration brief",
        "",
        f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        f"- CM: `{args.cm_json}`",
        f"- Protocol: `{args.protocol}`",
        f"- Primary comparison: `{protocol.get('g0_protocol', {}).get('primary_comparison')}`",
        "",
        "## Knob freeze (do not over-tune)",
        "",
        "If macro-F1 ≥ promote/stop bar → **freeze** knobs for that field "
        "(unless documenting a held-out regression repair).",
        "",
        "| Field | macro-F1 | bar | action | reason |",
        "|---|---:|---:|---|---|",
    ]
    for field in FIELDS:
        d = decisions[field]
        f1 = d["macro_f1"]
        f1_s = "n/a" if f1 is None or f1 != f1 else f"{f1:.3f}"
        bar = d["bar"]
        bar_s = "n/a" if bar is None else f"{bar:.2f}"
        lines.append(
            f"| `{field}` | {f1_s} | {bar_s} | **{d['action']}** | {d['reason']} |"
        )

    lines += [
        "",
        f"**Freeze (no knob changes):** {', '.join(f'`{f}`' for f in freeze) or '(none)'}",
        f"**Active (may change knobs):** {', '.join(f'`{f}`' for f in active) or '(none)'}",
        f"**Monitor only:** {', '.join(f'`{f}`' for f in monitor) or '(none)'}",
        "",
        "## Rotation reminder",
        "",
        "- Add new queries/URLs this iteration (candidate pool).",
        "- Do not tune only on frozen v0 IDs.",
        "- Held-out adjudicated rows are never used to choose knobs this round.",
        "",
        "## Paper framing",
        "",
        f"**Claim-ready:** {paper.get('claim_ready', '')}",
        "",
        "**Not claim-ready:** "
        + "; ".join(f"`{x}`" for x in (paper.get("not_claim_ready") or [])),
        "",
        "## Error buckets (Anti-GEO vs adjudicated)",
        "",
    ]
    if not errors:
        lines.append(
            "_No error list (pass `--anti-geo` and `--adjudication` to attach mismatches)._"
        )
    else:
        lines += [
            "| Field | n mismatches |",
            "|---|---:|",
        ]
        for f in FIELDS:
            lines.append(f"| `{f}` | {err_by_field.get(f, 0)} |")
        lines += ["", "### Active-field mismatches first", ""]
        for e in show_errors:
            if e["field"] not in active and e["field"] not in freeze:
                tag = "monitor"
            elif e["field"] in active:
                tag = "ACTIVE"
            else:
                tag = "frozen-field"
            lines.append(
                f"- [{tag}] `{e['id']}` `{e['field']}`: "
                f"gold=`{e['adjudicated']}` system=`{e['system']}`"
            )

    lines += [
        "",
        "## Next actions",
        "",
        "1. Do **not** edit knobs for frozen fields.",
        "2. Mine ACTIVE mismatches + LABEL_GUIDE (not system rationales) for hypotheses.",
        "3. After a code change: re-run Anti-GEO on protocol sheets → "
        "`permissions_confusion.py` vs adjudicated.",
        "4. Live Anti-GEO / blind API runs only when no other agent owns in-flight artifacts.",
        "",
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Machine-readable sibling.
    out_json = args.out.with_suffix(".json")
    out_json.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "cm_json": str(args.cm_json),
                "protocol": str(args.protocol),
                "decisions": decisions,
                "freeze": freeze,
                "active": active,
                "monitor_only": monitor,
                "n_errors": len(errors),
                "errors_by_field": dict(err_by_field),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.out}")
    print(f"Wrote {out_json}")
    print(f"freeze={freeze} active={active}")


if __name__ == "__main__":
    main()
