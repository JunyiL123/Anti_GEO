#!/usr/bin/env python3
"""Generate stratified commercial-intent candidate queries for eval-loop expansion.

Writes a *candidate pool* only — never gold. Default is --dry-run (offline templates).
LLM mode requires Azure/OpenAI env and is opt-in via --no-dry-run --llm.

Example:
  PYTHONPATH=src python demo/eval_loop_query_gen.py --dry-run --n 15 \\
    --out data/permissions_eval/candidates/queries_dryrun.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_DEMO = Path(__file__).resolve().parent
_ROOT = _DEMO.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_DEMO))

from eval_loop_lib import DEFAULT_PROTOCOL, load_protocol  # noqa: E402

# Offline strata — mirrors LABEL_GUIDE commercial threat surface without API calls.
_DRY_TEMPLATES: list[tuple[str, str]] = [
    ("vendor_legit", "is {brand} worth buying or a scam 2026"),
    ("affiliate_best", "best {category} 2026 according to reviewers"),
    ("reddit_push", "best {category} reddit recommends 2026"),
    ("supplement_claim", "does {brand} {product} actually work reviews"),
    ("medical_adjacent", "is {brand} compounded {product} safe to buy online"),
    ("forum_index", "{category} forum recommendations vs brand sites"),
    ("coupon_ugc", "{brand} coupon code working reddit"),
    ("comparison", "{brand_a} vs {brand_b} which should I buy"),
]

_FILLERS = [
    {
        "brand": "TheoGrace",
        "category": "personalized jewellery",
        "product": "rings",
        "brand_a": "TheoGrace",
        "brand_b": "Mejuri",
    },
    {
        "brand": "Nucific",
        "category": "weight loss supplements",
        "product": "Bio X4",
        "brand_a": "Nucific",
        "brand_b": "Goli",
    },
    {
        "brand": "ShedRx",
        "category": "semaglutide",
        "product": "semaglutide",
        "brand_a": "ShedRx",
        "brand_b": "Hims",
    },
    {
        "brand": "FlexiSpot",
        "category": "standing desks",
        "product": "desk",
        "brand_a": "FlexiSpot",
        "brand_b": "Uplift",
    },
    {
        "brand": "Aura",
        "category": "smart rings",
        "product": "ring",
        "brand_a": "Aura",
        "brand_b": "Oura",
    },
]


def _dry_queries(n: int) -> list[dict]:
    out: list[dict] = []
    i = 0
    while len(out) < n:
        stratum, tmpl = _DRY_TEMPLATES[i % len(_DRY_TEMPLATES)]
        fill = _FILLERS[i % len(_FILLERS)]
        out.append(
            {
                "query": tmpl.format(**fill),
                "stratum": stratum,
                "intent": "commercial",
                "source": "dry_run_template",
            }
        )
        i += 1
    return out


def _llm_queries(n: int, *, existing: list[str]) -> list[dict]:
    from anti_geo.azure_client import chat_completion_json, is_azure_configured, load_azure_config

    if not is_azure_configured():
        raise SystemExit("LLM mode needs Azure/OpenAI env (is_azure_configured() is False)")

    existing_block = "\n".join(f"- {q}" for q in existing[:40]) or "(none)"
    messages = [
        {
            "role": "system",
            "content": (
                "You generate commercial-intent eval queries for a generative-engine "
                "permissions/parasitic labeling study. Return JSON only: "
                '{"queries":[{"query":"...","stratum":"vendor_legit|affiliate_best|'
                "reddit_push|supplement_claim|medical_adjacent|forum_index|coupon_ugc|"
                'comparison","intent":"commercial"}]}. '
                "Diversify strata. Do not copy existing queries. No URLs."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Generate {n} new commercial-intent queries.\n"
                f"Avoid duplicates of:\n{existing_block}\n"
            ),
        },
    ]
    payload = chat_completion_json(messages, config=load_azure_config())
    rows = payload.get("queries") or []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        q = (row.get("query") or "").strip()
        if not q:
            continue
        out.append(
            {
                "query": q,
                "stratum": row.get("stratum") or "unspecified",
                "intent": row.get("intent") or "commercial",
                "source": "llm",
            }
        )
        if len(out) >= n:
            break
    if len(out) < n:
        raise SystemExit(f"LLM returned only {len(out)}/{n} usable queries")
    return out


def _load_existing(paths: list[Path]) -> list[str]:
    existing: list[str] = []
    for path in paths:
        if path.suffix == ".txt":
            existing.extend(
                ln.strip()
                for ln in path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            )
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, list):
            existing.extend(str(x) for x in doc)
            continue
        if not isinstance(doc, dict):
            continue
        for q in doc.get("queries") or []:
            if isinstance(q, str):
                existing.append(q)
            elif isinstance(q, dict) and q.get("query"):
                existing.append(str(q["query"]))
        for page in doc.get("pages") or []:
            if page.get("query"):
                existing.append(str(page["query"]))
    return list(dict.fromkeys(existing))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=15, help="Number of queries to generate")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/permissions_eval/candidates/queries_pool.json"),
    )
    parser.add_argument(
        "--existing",
        type=Path,
        action="append",
        default=[],
        help="Optional query list / sheet JSON / .txt to avoid duplicates (repeatable)",
    )
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Offline templates (default: on). Use --no-dry-run --llm for API.",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use chat_completion_json (requires --no-dry-run)",
    )
    args = parser.parse_args()

    protocol = load_protocol(args.protocol)
    lo, hi = protocol.get("rotation", {}).get("candidate_batch_size") or [10, 20]
    if args.n < lo or args.n > hi * 2:
        print(
            f"warning: plan cadence suggests ~{lo}-{hi} queries/iteration; got n={args.n}",
            file=sys.stderr,
        )

    existing = _load_existing(args.existing)

    if args.dry_run:
        if args.llm:
            raise SystemExit("Use --no-dry-run --llm together for API generation")
        queries = _dry_queries(args.n)
    else:
        if not args.llm:
            raise SystemExit("Non-dry-run requires --llm (or pass --dry-run)")
        queries = _llm_queries(args.n, existing=existing)

    exist_set = {q.casefold() for q in existing}
    queries = [q for q in queries if q["query"].casefold() not in exist_set]

    payload = {
        "description": (
            "Eval-loop candidate query pool — not gold. "
            "Expand cites separately; draft→adjudicate before paper use."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol": str(args.protocol),
        "dry_run": bool(args.dry_run),
        "n_queries": len(queries),
        "queries": queries,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {args.out} ({len(queries)} queries, dry_run={args.dry_run})")


if __name__ == "__main__":
    main()
