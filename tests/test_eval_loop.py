"""Offline unit tests for AI-assisted eval-loop helpers and demos."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_DEMO = _ROOT / "demo"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_lib = _load("eval_loop_lib", _DEMO / "eval_loop_lib.py")


def test_protocol_json_has_g0_and_bars():
    proto = json.loads(
        (_ROOT / "data/permissions_eval/eval_loop_protocol.json").read_text()
    )
    assert proto["live_runs"]["default"] is False
    assert proto["g0_protocol"]["mode_a_forced"] is True
    assert proto["g0_protocol"]["primary_comparison"] == "anti_vs_adjudicated"
    bars = _lib.field_bars(proto)
    assert bars["endorsement_permission"] == 0.85
    assert bars["factual_permission"] == 0.65
    assert bars["retrieve_permission"] == 0.6
    assert "RLHF/RLAIF" in proto["paper"]["not_claim_ready"]


def test_knob_freeze_above_bar():
    bars = {
        "endorsement_permission": 0.85,
        "parasitic": 0.75,
        "factual_permission": 0.65,
        "retrieve_permission": 0.6,
        "mention_permission": 0.95,
    }
    scores = {
        "endorsement_permission": 0.89,
        "parasitic": 0.81,
        "factual_permission": 0.50,
        "retrieve_permission": 0.46,
        "mention_permission": 1.0,
    }
    meta = {
        "mention_permission": {"role": "monitor_only"},
        "endorsement_permission": {"role": "hold"},
        "factual_permission": {"role": "active_gap"},
    }
    d = _lib.knob_decisions(scores, bars, field_meta=meta)
    assert d["endorsement_permission"]["action"] == "freeze"
    assert d["parasitic"]["action"] == "freeze"
    assert d["factual_permission"]["action"] == "active"
    assert d["retrieve_permission"]["action"] == "active"
    assert d["mention_permission"]["action"] == "monitor_only"


def test_disagreement_rows_triage_only():
    anti = {
        "pages": [
            {
                "id": "p1",
                "query": "q",
                "url": "https://example.com/a",
                "predictions": {
                    "retrieve_permission": "allow",
                    "mention_permission": "allow",
                    "factual_permission": "allow",
                    "endorsement_permission": "deny",
                    "parasitic": "none",
                },
            }
        ]
    }
    draft = {
        "pages": [
            {
                "id": "p1",
                "query": "q",
                "url": "https://example.com/a",
                "llm_labels": {
                    "retrieve_permission": "allow",
                    "mention_permission": "allow",
                    "factual_permission": "attribute_only",
                    "endorsement_permission": "deny",
                    "parasitic": "elevated",
                },
            }
        ]
    }
    rows = _lib.disagreement_rows(anti, draft)
    fields = {r["field"] for r in rows}
    assert fields == {"factual_permission", "parasitic"}


def test_blind_judge_rejects_system_leakage():
    judge = _load("blind_label_judge", _DEMO / "blind_label_judge.py")
    with pytest.raises(SystemExit):
        judge._assert_no_system_leakage(
            {"id": "x", "predictions": {"retrieve_permission": "allow"}}
        )


def test_blind_judge_dry_messages_include_guide_not_heuristics():
    judge = _load("blind_label_judge", _DEMO / "blind_label_judge.py")
    msgs = judge._build_messages(
        guide="TEST GUIDE endorsement deny for vendors",
        query="best widget 2026",
        url="https://vendor.example/widget",
        excerpt="Buy now",
    )
    blob = msgs[0]["content"] + msgs[1]["content"]
    assert "TEST GUIDE" in blob
    assert "best widget 2026" in blob
    assert "heuristic_permissions" not in blob
    assert "llm_action" not in blob
    assert "parasitic_geo_risk" not in blob


def test_macro_f1_from_real_cm_if_present():
    path = _ROOT / "data/permissions_eval/confusion_matrices_clamp_20260803_no_defer_match.json"
    if not path.is_file():
        pytest.skip("clamp CM json missing")
    scores = _lib.macro_f1_from_cm(json.loads(path.read_text()))
    assert scores["endorsement_permission"] is not None
    assert scores["endorsement_permission"] > 0.8
    proto = _lib.load_protocol(_ROOT / "data/permissions_eval/eval_loop_protocol.json")
    d = _lib.knob_decisions(
        scores,
        _lib.field_bars(proto),
        field_meta=(proto.get("promote_stop_bars") or {}).get("fields"),
    )
    assert d["endorsement_permission"]["action"] == "freeze"
    assert d["factual_permission"]["action"] == "active"
