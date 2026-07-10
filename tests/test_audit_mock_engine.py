from pathlib import Path

from anti_geo.audit.engines import MockEngine, get_engine
from anti_geo.audit.report import format_audit_summary, run_audit, summarize_audit


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "audit_replays" / "default.jsonl"


def test_mock_engine_end_to_end(tmp_path):
    engine = MockEngine(fixture_path=FIXTURE)
    audit_run = run_audit(engine, log_dir=tmp_path)
    assert len(audit_run.records) == 12
    summary = summarize_audit(audit_run.records)
    assert summary.query_count == 12
    text = format_audit_summary(summary)
    assert "Jaccard" in text


def test_get_engine_mock():
    engine = get_engine("mock", fixture_path=FIXTURE)
    resp = engine.query("What are the best moisturizers for dry skin?")
    assert "healthline.com" in resp.cited_domains
