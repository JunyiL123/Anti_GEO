"""Shared helpers for the AI-assisted eval-loop demos (offline-safe)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIELDS = (
    "retrieve_permission",
    "mention_permission",
    "factual_permission",
    "endorsement_permission",
    "parasitic",
)

SCHEMA: dict[str, list[str]] = {
    "retrieve_permission": ["allow", "downrank", "defer", "reject"],
    "mention_permission": ["allow", "deny"],
    "factual_permission": [
        "allow",
        "attribute_only",
        "require_corroboration",
        "deny",
    ],
    "endorsement_permission": ["allow", "deny"],
    "parasitic": ["none", "elevated", "suspected"],
}

DEFAULT_PROTOCOL = Path("data/permissions_eval/eval_loop_protocol.json")
DEFAULT_LABEL_GUIDE = Path("data/permissions_eval/LABEL_GUIDE.md")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_protocol(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or DEFAULT_PROTOCOL)


def field_bars(protocol: dict[str, Any]) -> dict[str, float]:
    fields = (protocol.get("promote_stop_bars") or {}).get("fields") or {}
    out: dict[str, float] = {}
    for name, meta in fields.items():
        if isinstance(meta, dict) and "bar" in meta:
            out[name] = float(meta["bar"])
    return out


def knob_decisions(
    macro_f1_by_field: dict[str, float | None],
    bars: dict[str, float],
    *,
    field_meta: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return per-field freeze/active decisions from macro-F1 vs bars."""
    meta = field_meta or {}
    decisions: dict[str, dict[str, Any]] = {}
    for field in FIELDS:
        bar = bars.get(field)
        score = macro_f1_by_field.get(field)
        role = (meta.get(field) or {}).get("role") if isinstance(meta.get(field), dict) else None
        if role == "monitor_only":
            action = "monitor_only"
            reason = "not a promotion driver"
        elif bar is None or score is None or score != score:  # NaN
            action = "unknown"
            reason = "missing score or bar"
        elif score >= bar:
            action = "freeze"
            reason = f"macro_f1={score:.3f} >= bar={bar:.3f}"
        else:
            action = "active"
            reason = f"macro_f1={score:.3f} < bar={bar:.3f}"
        decisions[field] = {
            "action": action,
            "macro_f1": score,
            "bar": bar,
            "reason": reason,
        }
    return decisions


def anti_preds_from_page(page: dict[str, Any]) -> dict[str, Any]:
    pred = page.get("predictions") or {}
    return {f: pred.get(f) for f in FIELDS}


def draft_labels_from_page(page: dict[str, Any]) -> dict[str, Any]:
    """Prefer llm_labels, then labels, then draft_labels."""
    for key in ("llm_labels", "labels", "draft_labels"):
        block = page.get(key)
        if isinstance(block, dict) and any(block.get(f) is not None for f in FIELDS):
            return {f: block.get(f) for f in FIELDS}
    return {f: None for f in FIELDS}


def page_index(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for page in doc.get("pages") or []:
        pid = page.get("id")
        if pid:
            out[str(pid)] = page
    return out


def disagreement_rows(
    anti_doc: dict[str, Any],
    draft_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare Anti-GEO predictions vs blind/draft labels (triage only)."""
    anti = page_index(anti_doc)
    draft = page_index(draft_doc)
    rows: list[dict[str, Any]] = []
    for pid in sorted(set(anti) & set(draft)):
        a = anti_preds_from_page(anti[pid])
        d = draft_labels_from_page(draft[pid])
        for field in FIELDS:
            av, dv = a.get(field), d.get(field)
            if av is None or dv is None:
                continue
            # Match CM policy: defer is a fetch gate, not a scored retrieve class.
            if field == "retrieve_permission" and (
                str(av) == "defer" or str(dv) == "defer"
            ):
                continue
            if str(av) != str(dv):
                rows.append(
                    {
                        "id": pid,
                        "query": draft[pid].get("query") or anti[pid].get("query"),
                        "url": draft[pid].get("url") or anti[pid].get("url"),
                        "field": field,
                        "system": str(av),
                        "draft": str(dv),
                    }
                )
    return rows


def macro_f1_from_cm(cm_doc: dict[str, Any]) -> dict[str, float | None]:
    """Pull anti_vs_adjudicated macro_f1 per field from permissions_confusion JSON."""
    comps = cm_doc.get("comparisons") or {}
    primary = comps.get("anti_vs_adjudicated") or {}
    fields = primary.get("fields") or {}
    out: dict[str, float | None] = {}
    for field in FIELDS:
        entry = fields.get(field) or {}
        val = entry.get("macro_f1")
        if val is None:
            out[field] = None
        else:
            out[field] = float(val)
    return out


def extract_error_buckets(
    anti_doc: dict[str, Any],
    adj_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    """List Anti-GEO vs adjudicated mismatches for the iteration brief."""
    anti = page_index(anti_doc)
    adj = page_index(adj_doc)
    rows: list[dict[str, Any]] = []
    for pid in sorted(set(anti) & set(adj)):
        a = anti_preds_from_page(anti[pid])
        gold_block = adj[pid].get("adjudicated_labels") or {}
        for field in FIELDS:
            if field == "parasitic":
                pred = anti[pid].get("predictions") or {}
                if pred.get("parasitic_source") is None and a.get(field) is not None:
                    # Still compare if present; CM tooling excludes separately.
                    pass
            gv, av = gold_block.get(field), a.get(field)
            if gv is None or av is None:
                continue
            if field == "retrieve_permission" and (
                str(gv) == "defer" or str(av) == "defer"
            ):
                continue
            if str(gv) != str(av):
                rows.append(
                    {
                        "id": pid,
                        "query": adj[pid].get("query") or anti[pid].get("query"),
                        "url": adj[pid].get("url") or anti[pid].get("url"),
                        "field": field,
                        "adjudicated": str(gv),
                        "system": str(av),
                    }
                )
    return rows
