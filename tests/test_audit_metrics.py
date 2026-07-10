from pathlib import Path

from anti_geo.audit.engines import MockEngine, record_from_response
from anti_geo.audit.metrics import citation_persistence, compute_jaccard_sensitivity, domain_citation_share
from anti_geo.audit.models import CitationRecord


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "audit_replays" / "default.jsonl"


def _records_from_fixture() -> list[CitationRecord]:
    engine = MockEngine(fixture_path=FIXTURE)
    records = []
    for pair in [
        ("What are the best moisturizers for dry skin?", None),
        ("Which moisturizers work best for dry skin?", "What are the best moisturizers for dry skin?"),
    ]:
        query, para = pair
        resp = engine.query(query)
        records.append(record_from_response("test", "mock", query, resp, paraphrase_of=para))
    return records


def test_jaccard_sensitivity_on_fixture_pairs():
    engine = MockEngine(fixture_path=FIXTURE)
    records = []
    run_id = "metrics_test"
    for line in FIXTURE.read_text().splitlines():
        import json

        row = json.loads(line)
        q = row["query"]
        para = None
        if "moisturizers work best" in q:
            para = "What are the best moisturizers for dry skin?"
        resp = engine.query(q)
        records.append(record_from_response(run_id, "mock", q, resp, paraphrase_of=para))

    mean_jd, pct_change = compute_jaccard_sensitivity(records)
    assert mean_jd > 0.0
    assert pct_change > 0.0


def test_domain_citation_share():
    records = _records_from_fixture()
    shares = domain_citation_share(records)
    assert shares
    assert abs(sum(shares.values()) - 100.0) < 0.01 or sum(shares.values()) <= 100.0


def test_persistence_requires_multiple_days():
    records = [
        CitationRecord(
            "r1", "2026-01-01T00:00:00", "mock", "q1", None, "", ["a.com"], []
        ),
        CitationRecord(
            "r1", "2026-01-08T00:00:00", "mock", "q1", None, "", ["a.com", "b.com"], []
        ),
    ]
    rate = citation_persistence(records, window_days=7)
    assert rate is not None
    assert 0.0 <= rate <= 1.0
