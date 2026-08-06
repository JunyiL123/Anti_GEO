#!/usr/bin/env python3
"""Export Anti-GEO vs blind-draft disagreements for human triage.

Offline-only. Disagreements are for adjudication priority — not paper metrics.
Primary paper CMs remain demo/permissions_confusion.py (anti vs adjudicated).

Example:
  PYTHONPATH=src python demo/eval_loop_disagreement.py \\
    --anti-geo data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_clamp_20260803_no_defer_match.json \\
    --draft data/permissions_eval/label_sheet_v0_adjudication.json \\
    --out-json data/permissions_eval/candidates/disagreements_example.json \\
    --out-md data/permissions_eval/candidates/disagreements_example.md
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

from eval_loop_lib import FIELDS, disagreement_rows, load_json  # noqa: E402


def _write_md(rows: list[dict], path: Path, *, anti: str, draft: str) -> None:
    by_field = Counter(r["field"] for r in rows)
    lines = [
        "# Eval-loop disagreements (system vs draft) — triage only",
        "",
        f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        f"- Anti-GEO: `{anti}`",
        f"- Draft / LLM labels: `{draft}`",
        "",
        "**Not paper gold.** Use to prioritize human adjudication. "
        "Do not optimize F1 against these rows.",
        "",
        "## Counts by field",
        "",
        "| Field | n |",
        "|---|---:|",
    ]
    for f in FIELDS:
        lines.append(f"| `{f}` | {by_field.get(f, 0)} |")
    lines += ["", f"Total: **{len(rows)}**", "", "## Rows", ""]
    for r in rows:
        lines.append(
            f"- `{r['id']}` / `{r['field']}`: system=`{r['system']}` "
            f"draft=`{r['draft']}` — {r.get('url') or ''}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anti-geo", type=Path, required=True)
    parser.add_argument(
        "--draft",
        type=Path,
        required=True,
        help="Sheet with llm_labels / labels / draft_labels (or adjudication llm_labels)",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("data/permissions_eval/candidates/disagreements.json"),
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path("data/permissions_eval/candidates/disagreements.md"),
    )
    args = parser.parse_args()

    anti_doc = load_json(args.anti_geo)
    draft_doc = load_json(args.draft)
    rows = disagreement_rows(anti_doc, draft_doc)

    payload = {
        "description": (
            "System vs blind/draft label disagreements for human triage. "
            "Not a paper metric. Primary CM remains anti_vs_adjudicated."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sources": {"anti_geo": str(args.anti_geo), "draft": str(args.draft)},
        "n_disagreements": len(rows),
        "by_field": dict(Counter(r["field"] for r in rows)),
        "rows": rows,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_md(rows, args.out_md, anti=str(args.anti_geo), draft=str(args.draft))
    print(f"Wrote {args.out_json} ({len(rows)} disagreements)")
    print(f"Wrote {args.out_md}")


if __name__ == "__main__":
    main()
