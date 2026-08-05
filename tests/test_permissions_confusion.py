"""Tests for demo/permissions_confusion.py retrieve-defer exclusion."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "permissions_confusion",
    _ROOT / "demo" / "permissions_confusion.py",
)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)


def test_retrieve_defer_excluded_from_comparison():
    schema = {f: list(_mod.ORDINAL[f]) for f in _mod.FIELDS}
    adj = {
        "p1": {
            "id": "p1",
            "human": {},
            "llm": {},
            "adjudicated": {
                "retrieve_permission": "defer",
                "mention_permission": "allow",
                "factual_permission": "deny",
                "endorsement_permission": "deny",
                "parasitic": "none",
            },
        },
        "p2": {
            "id": "p2",
            "human": {},
            "llm": {},
            "adjudicated": {
                "retrieve_permission": "allow",
                "mention_permission": "allow",
                "factual_permission": "attribute_only",
                "endorsement_permission": "deny",
                "parasitic": "none",
            },
        },
        "p3": {
            "id": "p3",
            "human": {},
            "llm": {},
            "adjudicated": {
                "retrieve_permission": "allow",
                "mention_permission": "allow",
                "factual_permission": "deny",
                "endorsement_permission": "deny",
                "parasitic": "none",
            },
        },
    }
    anti = {
        "p1": {
            "id": "p1",
            "anti": {
                "retrieve_permission": "allow",
                "mention_permission": "allow",
                "factual_permission": "deny",
                "endorsement_permission": "deny",
                "parasitic": "none",
                "parasitic_source": "heuristic",
            },
        },
        "p2": {
            "id": "p2",
            "anti": {
                "retrieve_permission": "defer",
                "mention_permission": "allow",
                "factual_permission": "attribute_only",
                "endorsement_permission": "deny",
                "parasitic": "none",
                "parasitic_source": "heuristic",
            },
        },
        "p3": {
            "id": "p3",
            "anti": {
                "retrieve_permission": "allow",
                "mention_permission": "allow",
                "factual_permission": "deny",
                "endorsement_permission": "deny",
                "parasitic": "none",
                "parasitic_source": "heuristic",
            },
        },
    }
    out = _mod.evaluate(adj, anti, schema)
    ret = out["comparisons"]["anti_vs_adjudicated"]["fields"]["retrieve_permission"]
    assert ret["n"] == 1
    assert ret["ids"] == ["p3"]
    assert "p1" in ret["skipped_ids"] and "p2" in ret["skipped_ids"]
    assert "defer" not in ret["levels"]
