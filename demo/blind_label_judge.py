#!/usr/bin/env python3
"""Blind LABEL_GUIDE-only draft labeler for the AI-assisted eval loop.

Hard rules:
  - Prompt = LABEL_GUIDE + query + URL (+ optional excerpt). Never Anti-GEO
    heuristics, preds, risk floats, mix shares, or llm_action.
  - Writes draft labels only (pages[].llm_labels). Does NOT write adjudicated_labels.
  - Default --dry-run skips API calls (prompt preview / null drafts).

Example:
  PYTHONPATH=src python demo/blind_label_judge.py \\
    --sheet data/permissions_eval/label_sheet_v2_blind.json \\
    --dry-run --ids v2p01 \\
    --out data/permissions_eval/candidates/v2_blind_draft_dryrun.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_DEMO = Path(__file__).resolve().parent
_ROOT = _DEMO.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_DEMO))

from eval_loop_lib import (  # noqa: E402
    DEFAULT_LABEL_GUIDE,
    DEFAULT_PROTOCOL,
    FIELDS,
    SCHEMA,
    load_protocol,
)

_FORBIDDEN_KEYS = (
    "predictions",
    "llm_action",
    "permissions_llm_reason",
    "parasitic_llm_reason",
    "parasitic_geo_risk",
    "parasitic_source",
    "heuristic",
    "subscores",
)


def _domain(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def _assert_no_system_leakage(page: dict[str, Any]) -> None:
    for key in _FORBIDDEN_KEYS:
        if key in page and page[key] not in (None, {}, []):
            raise SystemExit(
                f"Refusing to label {page.get('id')}: page contains system key "
                f"{key!r}. Strip Anti-GEO preds before blind labeling."
            )


def _build_messages(
    *,
    guide: str,
    query: str,
    url: str,
    excerpt: str | None,
) -> list[dict[str, str]]:
    schema_lines = "\n".join(f"- {f}: {' | '.join(SCHEMA[f])}" for f in FIELDS)
    excerpt_block = (excerpt or "").strip()[:4000] or "(no excerpt provided — judge from URL/domain + guide)"
    system = (
        "You are a blind human-rubric labeler for generative-engine source use.\n"
        "Follow ONLY the labeling guide below. Do NOT invent Anti-GEO system "
        "heuristics, thresholds, clamps, or risk floats.\n"
        "Keep Group A (four permissions) independent from Group B (parasitic).\n"
        "Return a single JSON object with keys: "
        + ", ".join(FIELDS)
        + ", and optional brief_reason (string).\n\n"
        "=== LABEL_GUIDE.md ===\n"
        f"{guide}\n"
        "=== end guide ===\n\n"
        f"Allowed enums:\n{schema_lines}\n"
    )
    user = (
        f"query: {query}\n"
        f"url: {url}\n"
        f"domain: {_domain(url)}\n"
        f"excerpt:\n{excerpt_block}\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _validate_labels(raw: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for field in FIELDS:
        val = raw.get(field)
        if val is None:
            raise ValueError(f"missing field {field}")
        s = str(val)
        if s not in SCHEMA[field]:
            raise ValueError(f"invalid {field}={s!r}")
        out[field] = s
    return out


def _label_one(
    *,
    page: dict[str, Any],
    guide: str,
    dry_run: bool,
) -> dict[str, Any]:
    _assert_no_system_leakage(page)
    query = str(page.get("query") or "")
    url = str(page.get("url") or "")
    excerpt = page.get("excerpt") or page.get("text_excerpt")
    messages = _build_messages(guide=guide, query=query, url=url, excerpt=excerpt)

    if dry_run:
        return {
            "llm_labels": {f: None for f in FIELDS},
            "draft_meta": {
                "dry_run": True,
                "prompt_chars": sum(len(m["content"]) for m in messages),
                "system_leakage_checked": True,
                "guide_only": True,
            },
        }

    from anti_geo.azure_client import chat_completion_json, is_azure_configured, load_azure_config

    if not is_azure_configured():
        raise SystemExit("Live labeling needs Azure/OpenAI env")

    payload = chat_completion_json(messages, config=load_azure_config())
    labels = _validate_labels(payload)
    return {
        "llm_labels": labels,
        "draft_meta": {
            "dry_run": False,
            "brief_reason": payload.get("brief_reason"),
            "system_leakage_checked": True,
            "guide_only": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", type=Path, required=True, help="Blind sheet JSON (no preds)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/permissions_eval/candidates/blind_draft_labels.json"),
    )
    parser.add_argument("--guide", type=Path, default=DEFAULT_LABEL_GUIDE)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--ids", default="", help="Comma-separated page ids (default: all)")
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip API; write null drafts + prompt meta (default: on)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip ids that already have complete llm_labels in --out",
    )
    args = parser.parse_args()

    _ = load_protocol(args.protocol)  # validate protocol present
    guide = args.guide.read_text(encoding="utf-8")
    sheet = json.loads(args.sheet.read_text(encoding="utf-8"))
    pages = list(sheet.get("pages") or [])
    if args.ids.strip():
        want = {x.strip() for x in args.ids.split(",") if x.strip()}
        pages = [p for p in pages if p.get("id") in want]

    prior: dict[str, dict] = {}
    if args.resume and args.out.is_file():
        prior_doc = json.loads(args.out.read_text(encoding="utf-8"))
        for p in prior_doc.get("pages") or []:
            prior[str(p["id"])] = p

    def _write(pages_out: list[dict[str, Any]]) -> None:
        payload = {
            "description": (
                "Blind LABEL_GUIDE-only draft labels. Not paper gold. "
                "Human must adjudicate before CM promotion. "
                "No Anti-GEO system outputs were used in the prompt."
            ),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sheet": str(args.sheet),
            "guide": str(args.guide),
            "protocol": str(args.protocol),
            "dry_run": bool(args.dry_run),
            "label_schema": SCHEMA,
            "n_pages": len(pages_out),
            "pages": pages_out,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(args.out.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        tmp.replace(args.out)

    out_pages: list[dict[str, Any]] = []
    for i, page in enumerate(pages, 1):
        pid = str(page.get("id"))
        if args.resume and pid in prior:
            labels = (prior[pid].get("llm_labels") or {})
            if all(labels.get(f) is not None for f in FIELDS):
                out_pages.append(prior[pid])
                print(f"[{i}/{len(pages)}] resume {pid}", flush=True)
                continue
        print(f"[{i}/{len(pages)}] label {pid} …", flush=True)
        try:
            result = _label_one(page=page, guide=guide, dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {pid}: {exc}", flush=True)
            _write(out_pages)
            raise
        row = {
            "id": page.get("id"),
            "query": page.get("query"),
            "url": page.get("url"),
            "domain": page.get("domain") or _domain(str(page.get("url") or "")),
            "source": page.get("source"),
            "role_hint": page.get("role_hint"),
            "llm_labels": result["llm_labels"],
            "draft_meta": result["draft_meta"],
            # Explicit empties — human must adjudicate separately.
            "human_labels": {f: None for f in FIELDS},
            "adjudicated_labels": {f: None for f in FIELDS},
        }
        out_pages.append(row)
        prior[pid] = row
        _write(out_pages)
        lab = result["llm_labels"]
        print(
            f"  → retrieve={lab.get('retrieve_permission')} "
            f"factual={lab.get('factual_permission')} "
            f"endorse={lab.get('endorsement_permission')} "
            f"parasitic={lab.get('parasitic')}",
            flush=True,
        )

    print(
        f"Wrote {args.out} (n={len(out_pages)}, dry_run={args.dry_run}, "
        f"guide_only=True, adjudicated=null)"
    )


if __name__ == "__main__":
    main()
