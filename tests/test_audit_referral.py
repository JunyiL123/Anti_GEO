from pathlib import Path

from anti_geo.audit.engines import MockEngine
from anti_geo.audit.models import CitationRecord
from anti_geo.audit.referral import (
    build_referral_audit_report,
    filter_records_for_target,
    platform_role_citation_share,
)
from anti_geo.audit.report import summarize_audit
from anti_geo.models import FetchResult

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "audit_replays" / "budget_laptops.jsonl"


def _records_from_fixture() -> list[CitationRecord]:
    engine = MockEngine(fixture_path=FIXTURE)
    records: list[CitationRecord] = []
    for query in (
        "best budget laptops 2026",
        "best budget laptops tested",
        "budget laptops buying guide",
    ):
        resp = engine.query(query)
        records.append(
            CitationRecord(
                run_id="test",
                timestamp="2026-07-13T00:00:00+00:00",
                engine="mock",
                query=query,
                paraphrase_of=None,
                response_text=resp.text,
                cited_domains=resp.cited_domains,
                cited_urls=resp.cited_urls,
            )
        )
    return records


def test_platform_role_citation_share():
    records = _records_from_fixture()
    shares = platform_role_citation_share(records)
    assert shares
    assert sum(shares.values()) > 99.0


def test_filter_records_for_target():
    records = _records_from_fixture()
    filtered = filter_records_for_target(records, "pcmag.com")
    assert filtered
    assert all("pcmag.com" in url for rec in filtered for url in rec.cited_urls)


def test_build_referral_audit_report_with_fetches():
    records = _records_from_fixture()
    reddit_url = "https://www.reddit.com/r/laptops/comments/budget2026/"
    fetches = {
        reddit_url: FetchResult(
            url=reddit_url,
            final_url=reddit_url,
            status_code=200,
            ok=True,
            error=None,
            title="Thread",
            text="Check https://www.pcmag.com/picks/the-best-budget-laptops for picks.",
            link_count=1,
            broken_link_ratio=0.0,
            redirect_count=0,
            response_time_ms=50,
            has_privacy_page=False,
            has_contact_page=False,
        )
    }
    report = build_referral_audit_report(
        records,
        "pcmag.com",
        fetches=fetches,
    )
    assert report.citations_sampled > 0
    assert report.platform_role_shares
    assert report.link_graph is not None
    assert report.link_graph.promotion_concentration >= 0


def test_summarize_audit_with_target_domain():
    records = _records_from_fixture()
    summary = summarize_audit(records, target_domain="pcmag.com")
    assert summary.target_domain == "pcmag.com"
    assert summary.platform_role_shares
