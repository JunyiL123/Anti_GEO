from pathlib import Path

from anti_geo.audit.models import EngineResponse
from anti_geo.investigation import (
    assess_semantic_alignment,
    discover_referrers,
    extract_page_metadata,
    generate_seed_queries,
    investigate_url,
    VerifiedReferrer,
)
from anti_geo.models import FetchResult, PageContextSignals


class _StubEngine:
    name = "stub"

    def __init__(self, responses: dict[str, EngineResponse]) -> None:
        self._responses = responses

    def query(self, q: str) -> EngineResponse:
        return self._responses.get(
            q,
            EngineResponse(text="mock", cited_domains=[], cited_urls=[]),
        )


def _editorial_fetch() -> FetchResult:
    return FetchResult(
        url="https://www.pcmag.com/picks/the-best-budget-laptops",
        final_url="https://www.pcmag.com/picks/the-best-budget-laptops",
        status_code=200,
        ok=True,
        error=None,
        title="The Best Cheap Laptops We've Tested for 2026 | PCMag",
        text=(
            "PCMag editors select and review products independently. "
            "If you buy through affiliate links, we may earn commissions. "
            "Our recommendation for the best budget laptop is the Apple MacBook Neo."
        ),
        link_count=20,
        broken_link_ratio=0.05,
        redirect_count=0,
        response_time_ms=200,
        has_privacy_page=True,
        has_contact_page=True,
        page_context=PageContextSignals(
            cta_density=0.1,
            commercial_context_score=0.2,
            structure_density=0.5,
            list_item_count=10,
            table_count=1,
            has_faq_schema=True,
            flags=["affiliate_disclosure", "list_heavy"],
            commercial_tier="medium",
        ),
    )


def test_extract_metadata_and_editorial_seeds():
    fetch = _editorial_fetch()
    meta = extract_page_metadata(fetch)
    assert "Best Cheap Laptops" in meta.entity or "2026" in meta.entity
    seeds = generate_seed_queries("editorial", meta)
    assert any("best" in s.lower() for s in seeds)
    assert not any(s.startswith("what is The Best") for s in seeds)


def test_discover_referrers_skipped_without_engine():
    profile = discover_referrers(
        "https://example.com/product",
        "Example Product",
        ["best example product"],
        None,
    )
    assert profile.status == "skipped"
    assert profile.discovery_status == "skipped"


def test_discover_referrers_inconclusive_on_engine_failure():
    engine = _StubEngine({})

    def fail_query(q: str) -> EngineResponse:
        raise RuntimeError("api down")

    engine.query = fail_query  # type: ignore[method-assign]
    profile = discover_referrers(
        "https://example.com/product",
        "Example Product",
        ["best widgets"],
        engine,
    )
    assert profile.status == "inconclusive"
    assert profile.discovery_status == "failed"


def test_investigate_url_offline_editorial(monkeypatch):
    fetch = _editorial_fetch()

    def fake_fetch(url: str, **kwargs):
        return fetch

    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    result = investigate_url(
        fetch.url,
        query_intent="commercial",
        engine_name=None,
    )
    assert result.content_role == "editorial"
    assert result.referral_profile.status == "skipped"
    assert result.llm_action in (
        "pass",
        "downrank",
        "attribute_only",
        "mention_only",
        "block_endorsement",
        "defer_fetch",
    )
    assert "L1-L3 primary" in result.verdict


def test_target_cited_in_response():
    target = "https://www.pcmag.com/picks/the-best-budget-laptops"
    from anti_geo.investigation import _target_cited_in_response

    assert _target_cited_in_response(
        ["https://www.reddit.com/r/laptops", target],
        target,
    )
    assert not _target_cited_in_response(
        ["https://www.reddit.com/r/laptops"],
        target,
    )


def test_assess_semantic_alignment_coordinated_commercial():
    refs = [
        VerifiedReferrer(
            url=f"https://amazon.com/p{i}",
            role="commercial_product",
            connection="entity_mention",
        )
        for i in range(3)
    ]
    alignment = assess_semantic_alignment("editorial", refs, target_commercial_tier="medium")
    assert alignment.label == "coordinated_commercial"
    assert alignment.aligned is False


def test_discover_referrers_mock_verification(monkeypatch):
    target = "https://www.pcmag.com/picks/the-best-budget-laptops"
    fixture = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "audit_replays"
        / "budget_laptops.jsonl"
    )
    from anti_geo.audit.engines import MockEngine

    engine = MockEngine(fixture_path=fixture)
    seeds = [
        "best budget laptops 2026",
        "best budget laptops tested",
        "budget laptops buying guide",
        "top budget laptops picks",
    ]

    def fake_fetch(url: str, **kwargs):
        if "reddit.com" in url:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=200,
                ok=True,
                error=None,
                title="Reddit thread",
                text=(
                    "I recommend checking the-best-budget-laptops roundup at "
                    "pcmag.com/picks/the-best-budget-laptops for editor picks."
                ),
                link_count=2,
                broken_link_ratio=0.0,
                redirect_count=0,
                response_time_ms=100,
                has_privacy_page=False,
                has_contact_page=False,
            )
        return FetchResult(
            url=url,
            final_url=url,
            status_code=404,
            ok=False,
            error="not found",
            title="",
            text="",
            link_count=0,
            broken_link_ratio=0.0,
            redirect_count=0,
            response_time_ms=50,
            has_privacy_page=False,
            has_contact_page=False,
        )

    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    profile = discover_referrers(
        target,
        "The Best Cheap Laptops We've Tested for 2026",
        seeds,
        engine,
        target_role="editorial",
        target_commercial_tier="medium",
    )
    assert profile.citations_sampled >= 4
    assert profile.seed_queries_run == 4
    assert profile.target_cited_in_answers >= 1
    assert profile.n_verified >= 1
    assert profile.referrers_verified[0].connection in ("url_link", "entity_mention")
    assert profile.discovery_status in ("success", "partial")


def test_investigate_url_with_mock_engine(monkeypatch):
    fetch = _editorial_fetch()
    fixture = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "audit_replays"
        / "budget_laptops.jsonl"
    )

    def fake_fetch(url: str, **kwargs):
        if url == fetch.url or "pcmag.com" in url:
            return fetch
        if "reddit.com" in url:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=200,
                ok=True,
                error=None,
                title="Reddit",
                text="See pcmag.com/picks/the-best-budget-laptops",
                link_count=1,
                broken_link_ratio=0.0,
                redirect_count=0,
                response_time_ms=100,
                has_privacy_page=False,
                has_contact_page=False,
            )
        return FetchResult(
            url=url,
            final_url=url,
            status_code=404,
            ok=False,
            error="nf",
            title="",
            text="",
            link_count=0,
            broken_link_ratio=0.0,
            redirect_count=0,
            response_time_ms=50,
            has_privacy_page=False,
            has_contact_page=False,
        )

    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    result = investigate_url(
        fetch.url,
        engine_name="mock",
        fixture_path=fixture,
        seed_limit=4,
    )
    assert result.referral_profile.status != "skipped"
    assert result.referral_profile.citations_sampled > 0
