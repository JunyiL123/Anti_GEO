#!/usr/bin/env python3
"""Confusion matrices: Anti-GEO preds vs adjudicated / human / LLM golds.

Five fields only (4 permissions + 3-class parasitic). Pure stdlib.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FIELDS = (
    "retrieve_permission",
    "mention_permission",
    "factual_permission",
    "endorsement_permission",
    "parasitic",
)

# Ordinal ranks for quadratic weighted kappa (more restrictive / higher risk ↑).
ORDINAL: dict[str, tuple[str, ...]] = {
    "retrieve_permission": ("allow", "downrank", "defer", "reject"),
    "mention_permission": ("allow", "deny"),
    "factual_permission": (
        "allow",
        "attribute_only",
        "require_corroboration",
        "deny",
    ),
    "endorsement_permission": ("allow", "deny"),
    # LABEL_GUIDE: elevated = soft suspicion; suspected = clear plant.
    "parasitic": ("none", "elevated", "suspected"),
}

COMPARISONS = (
    ("anti_vs_adjudicated", "adjudicated", "anti", True),
    ("human_vs_llm", "human", "llm", False),
    ("anti_vs_human", "human", "anti", True),
    ("anti_vs_llm", "llm", "anti", True),
)

# Lead paper fields first in markdown.
MD_FIELD_ORDER = (
    "endorsement_permission",
    "parasitic",
    "factual_permission",
    "retrieve_permission",
    "mention_permission",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _page_map_adjudication(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for page in doc.get("pages") or []:
        pid = page["id"]
        out[pid] = {
            "id": pid,
            "query": page.get("query"),
            "url": page.get("url"),
            "human": dict(page.get("human_labels") or {}),
            "llm": dict(page.get("llm_labels") or {}),
            "adjudicated": dict(page.get("adjudicated_labels") or {}),
        }
    return out


def _page_map_anti(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for page in doc.get("pages") or []:
        pred = page.get("predictions") or {}
        out[page["id"]] = {
            "id": page["id"],
            "anti": {f: pred.get(f) for f in FIELDS},
            "parasitic_source": pred.get("parasitic_source"),
            "ok": page.get("ok", True),
        }
    return out


def _levels(schema: dict[str, list[str]] | None, field: str) -> list[str]:
    if schema and field in schema:
        return list(schema[field])
    return list(ORDINAL[field])


def _matrix(
    pairs: list[tuple[str, str]],
    levels: list[str],
) -> list[list[int]]:
    idx = {lab: i for i, lab in enumerate(levels)}
    n = len(levels)
    m = [[0] * n for _ in range(n)]
    for gold, pred in pairs:
        if gold not in idx or pred not in idx:
            continue
        m[idx[gold]][idx[pred]] += 1
    return m


def _accuracy(m: list[list[int]]) -> float:
    total = sum(sum(r) for r in m)
    if total == 0:
        return float("nan")
    correct = sum(m[i][i] for i in range(len(m)))
    return correct / total


def _macro_f1(m: list[list[int]]) -> float:
    n = len(m)
    f1s: list[float] = []
    for i in range(n):
        tp = m[i][i]
        fp = sum(m[r][i] for r in range(n) if r != i)
        fn = sum(m[i][c] for c in range(n) if c != i)
        if tp == 0 and fp == 0 and fn == 0:
            continue  # class absent — skip for macro
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(0.0 if (prec + rec) == 0 else 2 * prec * rec / (prec + rec))
    return sum(f1s) / len(f1s) if f1s else float("nan")


def _quadratic_weighted_kappa(
    pairs: list[tuple[str, str]],
    order: tuple[str, ...],
) -> float:
    """Cohen's kappa with quadratic weights on ordinal ranks."""
    rank = {lab: i for i, lab in enumerate(order)}
    usable = [(g, p) for g, p in pairs if g in rank and p in rank]
    n = len(usable)
    k = len(order)
    if n == 0 or k < 2:
        return float("nan")

    conf = [[0] * k for _ in range(k)]
    for g, p in usable:
        conf[rank[g]][rank[p]] += 1

    row = [sum(conf[i]) for i in range(k)]
    col = [sum(conf[r][j] for r in range(k)) for j in range(k)]
    denom = float((k - 1) ** 2)

    obs = 0.0
    exp = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / denom
            obs += w * conf[i][j]
            exp += w * (row[i] * col[j] / n)
    obs /= n
    exp /= n
    if exp == 0.0:
        # Perfect agreement on a single class → κ undefined/1 by convention.
        return 1.0 if obs == 0.0 else float("nan")
    if exp == 1.0:
        return float("nan")
    return 1.0 - (obs / exp)


def _off_by_one_rate(
    pairs: list[tuple[str, str]],
    order: tuple[str, ...],
) -> float:
    rank = {lab: i for i, lab in enumerate(order)}
    usable = [(g, p) for g, p in pairs if g in rank and p in rank]
    if not usable:
        return float("nan")
    n_off = sum(1 for g, p in usable if abs(rank[g] - rank[p]) == 1)
    return n_off / len(usable)


def _fmt(x: float) -> str:
    if x != x:  # NaN
        return "n/a"
    return f"{x:.3f}"


def _md_matrix(m: list[list[int]], levels: list[str], row_name: str, col_name: str) -> str:
    header = "| (rows=" + row_name + ") \\ (cols=" + col_name + ") | " + " | ".join(levels) + " |"
    sep = "|---|" + "|".join(["---"] * len(levels)) + "|"
    lines = [header, sep]
    for i, lab in enumerate(levels):
        cells = " | ".join(str(m[i][j]) for j in range(len(levels)))
        lines.append(f"| {lab} | {cells} |")
    return "\n".join(lines)


def evaluate(
    adj_pages: dict[str, dict[str, Any]],
    anti_pages: dict[str, dict[str, Any]],
    schema: dict[str, list[str]],
) -> dict[str, Any]:
    # Mode B missing → exclude from parasitic CMs that involve Anti-GEO.
    parasitic_exclude = sorted(
        pid
        for pid, ap in anti_pages.items()
        if ap.get("parasitic_source") is None
    )

    results: dict[str, Any] = {
        "comparisons": {},
        "parasitic_exclude_ids": parasitic_exclude,
        "parasitic_exclude_note": (
            "Excluded from parasitic matrices involving Anti-GEO when "
            "predictions.parasitic_source is None (Mode B not really run)."
        ),
    }

    for cmp_key, gold_key, pred_key, needs_anti in COMPARISONS:
        if needs_anti:
            ids = sorted(set(adj_pages) & set(anti_pages))
        else:
            ids = sorted(adj_pages)

        field_results: dict[str, Any] = {}
        for field in FIELDS:
            levels = _levels(schema, field)
            pairs: list[tuple[str, str]] = []
            used_ids: list[str] = []
            skipped: list[str] = []

            for pid in ids:
                if field == "parasitic" and needs_anti and pid in parasitic_exclude:
                    skipped.append(pid)
                    continue
                gold_src = adj_pages[pid][gold_key]
                if pred_key == "anti":
                    pred_src = anti_pages[pid]["anti"]
                else:
                    pred_src = adj_pages[pid][pred_key]
                g = gold_src.get(field)
                p = pred_src.get(field)
                if g is None or p is None:
                    skipped.append(pid)
                    continue
                pairs.append((str(g), str(p)))
                used_ids.append(pid)

            m = _matrix(pairs, levels)
            order = ORDINAL[field]
            entry: dict[str, Any] = {
                "levels": levels,
                "n": len(pairs),
                "ids": used_ids,
                "skipped_ids": skipped,
                "matrix": m,
                "accuracy": _accuracy(m),
                "macro_f1": _macro_f1(m),
                "quadratic_weighted_kappa": _quadratic_weighted_kappa(pairs, order),
                "off_by_one_rate": _off_by_one_rate(pairs, order),
                "label_counts_gold": {
                    lab: Counter(g for g, _ in pairs).get(lab, 0) for lab in levels
                },
                "label_counts_pred": {
                    lab: Counter(p for _, p in pairs).get(lab, 0) for lab in levels
                },
            }
            field_results[field] = entry

        results["comparisons"][cmp_key] = {
            "gold": gold_key,
            "pred": pred_key,
            "n_pages_pool": len(ids),
            "fields": field_results,
        }

    return results


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines: list[str] = [
        "# Permissions confusion matrices (Mode A forced)",
        "",
        f"Generated: `{payload['created_at']}`",
        "",
        f"- Adjudication: `{payload['sources']['adjudication']}`",
        f"- Anti-GEO: `{payload['sources']['anti_geo']}`",
        f"- Parasitic Mode-B exclusions (Anti-GEO CMs): "
        f"`{', '.join(payload['parasitic_exclude_ids']) or '(none)'}`",
        "",
        "Five separate matrices per comparison (no fused score). "
        "`parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.",
        "",
    ]

    # Summary table for primary comparison.
    primary = payload["comparisons"]["anti_vs_adjudicated"]["fields"]
    lines += [
        "## Summary — Anti-GEO vs Adjudicated (primary)",
        "",
        "| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for field in MD_FIELD_ORDER:
        e = primary[field]
        lines.append(
            f"| `{field}` | {e['n']} | {_fmt(e['accuracy'])} | {_fmt(e['macro_f1'])} | "
            f"{_fmt(e['quadratic_weighted_kappa'])} | {_fmt(e['off_by_one_rate'])} |"
        )
    lines.append("")

    # Human vs LLM ceiling summary.
    hvl = payload["comparisons"]["human_vs_llm"]["fields"]
    lines += [
        "## Summary — Human vs LLM (label-noise ceiling)",
        "",
        "| Field | n | Accuracy | Macro-F1 | Quad. weighted κ |",
        "|---|---:|---:|---:|---:|",
    ]
    for field in MD_FIELD_ORDER:
        e = hvl[field]
        lines.append(
            f"| `{field}` | {e['n']} | {_fmt(e['accuracy'])} | {_fmt(e['macro_f1'])} | "
            f"{_fmt(e['quadratic_weighted_kappa'])} |"
        )
    lines.append("")

    cmp_titles = {
        "anti_vs_adjudicated": "Anti-GEO vs Adjudicated (primary)",
        "human_vs_llm": "Human vs LLM",
        "anti_vs_human": "Anti-GEO vs Human",
        "anti_vs_llm": "Anti-GEO vs LLM",
    }

    for cmp_key, title in cmp_titles.items():
        block = payload["comparisons"][cmp_key]
        lines += [f"## {title}", ""]
        gold, pred = block["gold"], block["pred"]
        for field in MD_FIELD_ORDER:
            e = block["fields"][field]
            lines += [
                f"### `{field}`",
                "",
                f"n={e['n']}; accuracy={_fmt(e['accuracy'])}; "
                f"macro-F1={_fmt(e['macro_f1'])}; "
                f"κ_w²={_fmt(e['quadratic_weighted_kappa'])}; "
                f"off-by-one={_fmt(e['off_by_one_rate'])}",
                "",
                _md_matrix(e["matrix"], e["levels"], gold, pred),
                "",
            ]
            if field == "parasitic" and e.get("skipped_ids"):
                lines += [
                    f"_Skipped (Mode B missing or null): "
                    f"{', '.join(e['skipped_ids'])}_",
                    "",
                ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adjudication",
        type=Path,
        default=Path("data/permissions_eval/label_sheet_v0_adjudication.json"),
    )
    parser.add_argument(
        "--anti-geo",
        type=Path,
        default=Path(
            "data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced.json"
        ),
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path(
            "data/permissions_eval/confusion_matrices_mode_a_forced.json"
        ),
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path(
            "data/permissions_eval/confusion_matrices_mode_a_forced.md"
        ),
    )
    args = parser.parse_args()

    adj_doc = _load(args.adjudication)
    anti_doc = _load(args.anti_geo)
    schema = adj_doc.get("label_schema") or {
        f: list(ORDINAL[f]) for f in FIELDS
    }

    adj_pages = _page_map_adjudication(adj_doc)
    anti_pages = _page_map_anti(anti_doc)

    # Sanity: adjudicated must be complete.
    missing = []
    for pid, pg in adj_pages.items():
        for f in FIELDS:
            if pg["adjudicated"].get(f) is None:
                missing.append((pid, f))
    if missing:
        raise SystemExit(
            f"adjudicated_labels incomplete ({len(missing)} nulls); "
            f"e.g. {missing[:5]}"
        )

    metrics = evaluate(adj_pages, anti_pages, schema)
    payload = {
        "description": (
            "Confusion matrices for four permissions + 3-class parasitic. "
            "Primary gold = adjudicated_labels; Anti-GEO = Mode A forced preds."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "adjudication": str(args.adjudication),
            "anti_geo": str(args.anti_geo),
        },
        "fields": list(FIELDS),
        "ordinal": {k: list(v) for k, v in ORDINAL.items()},
        "n_adjudication_pages": len(adj_pages),
        "n_anti_geo_pages": len(anti_pages),
        **metrics,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_markdown(payload, args.out_md)

    # Console summary.
    print(f"Wrote {args.out_json}")
    print(f"Wrote {args.out_md}")
    print(
        f"parasitic_exclude={payload['parasitic_exclude_ids']} "
        f"anti_n={len(anti_pages)} adj_n={len(adj_pages)}"
    )
    prim = payload["comparisons"]["anti_vs_adjudicated"]["fields"]
    print("Anti vs Adjudicated:")
    for f in MD_FIELD_ORDER:
        e = prim[f]
        print(
            f"  {f}: n={e['n']} acc={_fmt(e['accuracy'])} "
            f"macroF1={_fmt(e['macro_f1'])} kw2={_fmt(e['quadratic_weighted_kappa'])}"
        )


if __name__ == "__main__":
    main()
