from pathlib import Path

from anti_geo.audit.models import EngineResponse
from anti_geo.investigation import (
    ReferralProfile,
    VerifiedReferrer,
    _is_generic_topic_marker,
    _verify_connection,
    _worth_llm_connection_check,
    assess_semantic_alignment,
    discover_referrers,
    extract_page_metadata,
    generate_seed_queries,
    investigate_url,
    tighten_actions_with_referral,
    verify_connection,
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
    # Without structured identity, fall back to cleaned title (not first title token as org).
    assert meta.entity.lower() != "the"
    assert "laptop" in meta.entity.lower() or "2026" in meta.topic.lower() or meta.org
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


def test_investigate_url_reuses_precomputed_score(monkeypatch):
    fetch = _editorial_fetch()
    from anti_geo.decisions import decide_single_source
    from anti_geo.scorer import score_source

    source = score_source(fetch.url, fetch, query=None)
    report = decide_single_source(source, "commercial", query=None)

    def boom_fetch(url: str, **kwargs):
        raise AssertionError("precomputed path must not fetch")

    monkeypatch.setattr("anti_geo.investigation.fetch_page", boom_fetch)
    result = investigate_url(
        fetch.url,
        query_intent="commercial",
        engine_name=None,
        fetch=fetch,
        single_page=report,
        content_role="editorial",
    )
    assert result.content_role == "editorial"
    assert result.single_page is report
    assert result.referral_profile.status == "skipped"


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
            connection="brand_mention",
            connection_confidence="weak",
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
    assert profile.referrers_verified[0].connection == "url_link"
    assert profile.referrers_verified[0].connection_confidence == "high"
    assert profile.discovery_status in ("success", "partial")


def test_discover_referrers_stops_after_verified_cap(monkeypatch):
    target = "https://www.pcmag.com/picks/the-best-budget-laptops"
    calls = {"n": 0}

    class _CountingEngine:
        name = "counting"

        def query(self, q: str):
            from anti_geo.audit.models import EngineResponse

            calls["n"] += 1
            return EngineResponse(
                text="answer",
                cited_domains=["reddit.com"],
                cited_urls=[f"https://www.reddit.com/r/laptops/comments/{calls['n']}/"],
            )

    def fake_fetch(url: str, **kwargs):
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            ok=True,
            error=None,
            title="Reddit",
            text="See pcmag.com/picks/the-best-budget-laptops for picks.",
            link_count=1,
            broken_link_ratio=0.0,
            redirect_count=0,
            response_time_ms=100,
            has_privacy_page=False,
            has_contact_page=False,
        )

    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    seeds = [f"seed {i}" for i in range(10)]
    profile = discover_referrers(
        target,
        "Budget Laptops",
        seeds,
        _CountingEngine(),
        max_fetches_per_seed=30,
        max_verified_referrers=3,
        min_seeds_before_verified_stop=4,
        seed_workers=1,
        fetch_workers=1,
    )
    assert profile.seed_queries_run == 3
    assert profile.n_verified == 3
    assert any("Stopped after" in note for note in profile.notes)


def test_discover_referrers_parallel_finds_verified(monkeypatch):
    target = "https://www.pcmag.com/picks/the-best-budget-laptops"
    calls = {"n": 0}

    class _Engine:
        name = "parallel"

        def query(self, q: str):
            from anti_geo.audit.models import EngineResponse

            calls["n"] += 1
            i = calls["n"]
            return EngineResponse(
                text="answer",
                cited_domains=["reddit.com"],
                cited_urls=[f"https://www.reddit.com/r/laptops/comments/{i}/"],
            )

    def fake_fetch(url: str, **kwargs):
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            ok=True,
            error=None,
            title="Reddit",
            text="See pcmag.com/picks/the-best-budget-laptops for picks.",
            link_count=1,
            broken_link_ratio=0.0,
            redirect_count=0,
            response_time_ms=100,
            has_privacy_page=False,
            has_contact_page=False,
        )

    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    profile = discover_referrers(
        target,
        "Budget Laptops",
        [f"seed {i}" for i in range(6)],
        _Engine(),
        seed_workers=3,
        fetch_workers=4,
        max_verified_referrers=100,
        min_seeds_before_verified_stop=4,
    )
    assert profile.seed_queries_run == 6
    assert profile.n_verified == 6


def test_parallel_fetch_respects_max_fetches_per_seed(monkeypatch):
    target = "https://www.pcmag.com/picks/the-best-budget-laptops"
    fetch_ok = {"n": 0}

    class _Engine:
        name = "cap"

        def query(self, q: str):
            from anti_geo.audit.models import EngineResponse

            return EngineResponse(
                text="answer",
                cited_domains=["reddit.com"],
                cited_urls=[
                    f"https://www.reddit.com/r/laptops/comments/{i}/" for i in range(40)
                ],
            )

    def fake_fetch(url: str, **kwargs):
        fetch_ok["n"] += 1
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            ok=True,
            error=None,
            title="Reddit",
            text="See pcmag.com/picks/the-best-budget-laptops for picks.",
            link_count=1,
            broken_link_ratio=0.0,
            redirect_count=0,
            response_time_ms=20,
            has_privacy_page=False,
            has_contact_page=False,
        )

    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    profile = discover_referrers(
        target,
        "Budget Laptops",
        ["one seed"],
        _Engine(),
        seed_workers=1,
        fetch_workers=8,
        max_fetches_per_seed=5,
    )
    assert fetch_ok["n"] == 5
    assert profile.n_verified == 5
    assert any("per-seed fetch cap reached" in e for e in profile.discovery_errors)


def test_discover_referrers_shuffles_per_seed(monkeypatch):
    target = "https://example.com/product"
    seen_orders: list[list[str]] = []

    class _ShuffleEngine:
        name = "shuffle"

        def query(self, q: str):
            from anti_geo.audit.models import EngineResponse

            return EngineResponse(
                text="answer",
                cited_domains=["a.com", "b.com", "c.com"],
                cited_urls=[
                    "https://a.com/1",
                    "https://b.com/2",
                    "https://c.com/3",
                ],
            )

    def fake_shuffle(items):
        seen_orders.append(list(items))

    def fake_fetch(url: str, **kwargs):
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

    monkeypatch.setattr("anti_geo.investigation.random.shuffle", fake_shuffle)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    discover_referrers(
        target,
        "Example",
        ["one seed"],
        _ShuffleEngine(),
        max_fetches_per_seed=30,
    )
    assert len(seen_orders) == 1
    assert sorted(seen_orders[0]) == [
        "https://a.com/1",
        "https://b.com/2",
        "https://c.com/3",
    ]


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


def test_is_generic_topic_marker():
    assert _is_generic_topic_marker("best ad blockers")
    assert _is_generic_topic_marker("best budget laptops 2026")
    assert _is_generic_topic_marker("The Best Ad Blockers We've Tested for 2026")
    assert not _is_generic_topic_marker("theograce")
    assert not _is_generic_topic_marker("superblock pro")


def test_verify_connection_rejects_generic_topic_overlap():
    target = "https://www.pcmag.com/picks/best-ad-blockers"
    entity = "The Best Ad Blockers We've Tested for 2026"
    text = "Here are the best ad blockers we recommend for Chrome and Safari."
    assert _verify_connection(text, text, target, entity, org="PCMag") is None


def test_verify_connection_url_link():
    target = "https://www.pcmag.com/picks/the-best-budget-laptops"
    conn = _verify_connection(
        "See pcmag.com/picks/the-best-budget-laptops for editor picks.",
        "See pcmag.com/picks/the-best-budget-laptops for editor picks.",
        target,
        "The Best Cheap Laptops We've Tested for 2026",
        org="PCMag",
    )
    assert conn is not None
    assert conn.kind == "url_link"
    assert conn.confidence == "high"


def test_verify_connection_brand_mention():
    target = "https://shop.theograce.com/products/bracelet"
    conn = _verify_connection(
        "I got a bracelet from theograce and love it.",
        "I got a bracelet from theograce and love it.",
        target,
        "Theo Grace Engraved Bracelet",
        org="Theo Grace",
    )
    assert conn is not None
    assert conn.kind == "brand_mention"
    assert conn.confidence == "weak"
    assert conn.marker == "theograce"


def test_worth_llm_connection_check_accepts_spaced_publisher():
    target = "https://www.pcmag.com/picks/best-budget-laptops"
    text = (
        "PC Magazine's editors ranked the cheapest Chromebooks and Windows "
        "ultrabooks they tested this year in a long comparison."
    )
    assert _worth_llm_connection_check(
        text.lower(), target, "Budget Laptop Buying Guide 2026", org="PCMag"
    )


def test_verify_connection_llm_backup_accepts_paraphrase(monkeypatch):
    target = "https://www.pcmag.com/picks/best-budget-laptops"
    text = (
        "PC Magazine's editors ranked the cheapest Chromebooks and Windows "
        "ultrabooks they tested this year in a long comparison for shoppers."
    )
    assert _verify_connection(text, text, target, "Budget laptops 2026", org="PCMag") is None

    monkeypatch.setattr(
        "anti_geo.investigation.chat_completion_json",
        lambda *a, **k: {
            "refers": True,
            "marker": "PC Magazine's editors ranked",
            "reason": "publisher paraphrase",
        },
    )
    conn = verify_connection(
        text, text, target, "Budget laptops 2026", org="PCMag", use_llm=True
    )
    assert conn is not None
    assert conn.kind == "llm_mention"
    assert conn.confidence == "weak"
    assert "PC Magazine" in conn.marker


def test_verify_connection_llm_backup_rejects_generic_topic(monkeypatch):
    target = "https://www.pcmag.com/picks/best-ad-blockers"
    entity = "The Best Ad Blockers We've Tested for 2026"
    text = (
        "Here are the best ad blockers we recommend for Chrome and Safari "
        "across desktop and mobile browsers in 2026 with extended notes."
    )
    calls = {"n": 0}

    def fake_llm(*a, **k):
        calls["n"] += 1
        return {"refers": True, "marker": "should not run", "reason": "nope"}

    monkeypatch.setattr("anti_geo.investigation.chat_completion_json", fake_llm)
    # No pcmag / publisher signal → lexical gate skips LLM.
    assert verify_connection(text, text, target, entity, org="", use_llm=True) is None
    assert calls["n"] == 0


def test_verify_connection_llm_backup_false_stays_none(monkeypatch):
    target = "https://shop.theograce.com/products/bracelet"
    text = (
        "People talking about theo grace style jewelry trends this season "
        "without naming a specific store or product page to buy from."
    )
    # Deterministic may already hit "theo grace"/"theograce"; force no det hit
    # by using entity tokens that only loosely relate after gate.
    monkeypatch.setattr(
        "anti_geo.investigation._verify_connection",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "anti_geo.investigation.chat_completion_json",
        lambda *a, **k: {"refers": False, "marker": "", "reason": "style only"},
    )
    assert (
        verify_connection(
            text,
            text,
            target,
            "Theo Grace Engraved Bracelet",
            org="Theo Grace",
            use_llm=True,
        )
        is None
    )


def test_discover_referrers_ignores_generic_topic_pages(monkeypatch):
    target = "https://www.pcmag.com/picks/best-ad-blockers"
    engine = _StubEngine(
        {
            "best ad blockers": EngineResponse(
                text="answer",
                cited_domains=["cybernews.com"],
                cited_urls=["https://cybernews.com/best-ad-blockers/"],
            )
        }
    )

    def fake_fetch(url: str, **kwargs):
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            ok=True,
            error=None,
            title="Best ad blockers",
            text="Our roundup of the best ad blockers for privacy in 2026.",
            link_count=1,
            broken_link_ratio=0.0,
            redirect_count=0,
            response_time_ms=100,
            has_privacy_page=False,
            has_contact_page=False,
        )

    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    profile = discover_referrers(
        target,
        "The Best Ad Blockers We've Tested for 2026",
        ["best ad blockers"],
        engine,
        org="PCMag",
    )
    assert profile.n_verified == 0


def test_tighten_geo_suspected_to_attribute_only():
    profile = ReferralProfile(
        status="complete",
        discovery_status="success",
        confidence="medium",
        n_verified=20,
        mix={"ugc_thread": 18},
        geo_suspected=True,
    )
    primary, actions = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="commercial_product",
    )
    assert primary in ("attribute_only", "block_endorsement")
    assert "attribute_only" in actions
    assert "block_endorsement" in actions


def test_tighten_zero_referrers_ai_cited_soft_downrank():
    profile = ReferralProfile(
        status="sparse",
        discovery_status="success",
        confidence="medium",
        n_verified=0,
        mix={},
        geo_suspected=False,
        target_cited_in_answers=2,
    )
    primary, actions = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="commercial_product",
        engine_cited=False,
    )
    assert primary == "downrank"
    assert "downrank" in actions


def test_tighten_zero_referrers_engine_cite_soft_downrank():
    profile = ReferralProfile(
        status="sparse",
        discovery_status="success",
        confidence="medium",
        n_verified=0,
        target_cited_in_answers=0,
    )
    primary, _ = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="factual_blog",
        engine_cited=True,
    )
    assert primary == "downrank"


def test_tighten_zero_referrers_skips_editorial():
    profile = ReferralProfile(
        status="sparse",
        discovery_status="success",
        confidence="medium",
        n_verified=0,
        target_cited_in_answers=3,
    )
    primary, actions = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="editorial",
        engine_cited=True,
    )
    assert primary == "pass"
    assert actions == ["pass"]


def test_tighten_does_not_loosen_reject():
    profile = ReferralProfile(
        status="complete",
        discovery_status="success",
        confidence="medium",
        n_verified=25,
        geo_suspected=True,
    )
    primary, _ = tighten_actions_with_referral(
        "reject",
        ["reject"],
        profile,
        content_role="commercial_product",
    )
    assert primary == "reject"


def test_tighten_editorial_mix_does_not_flag():
    """Editorial/institutional referrers present → no structural mix tighten."""
    profile = ReferralProfile(
        status="complete",
        discovery_status="success",
        confidence="medium",
        n_verified=20,
        mix={"ugc_thread": 10, "editorial": 10},
        geo_suspected=False,
    )
    primary, actions = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="commercial_product",
    )
    assert primary == "pass"
    assert actions == ["pass"]


def _refs(roles_and_urls: list[tuple[str, str]], *, high_risk: bool = False):
    from anti_geo.investigation import VerifiedReferrer

    return [
        VerifiedReferrer(
            url=url,
            role=role,
            connection="brand_mention",
            content_high_risk=high_risk if role == "factual_blog" else False,
        )
        for role, url in roles_and_urls
    ]


def test_tighten_parasitic_soft_band_downranks():
    """Parasitic share 40–60%, no editorial, N>=10 → mild downrank (not hard flag)."""
    refs = _refs(
        [("ugc_thread", f"https://reddit.com/r/x/comments/{i}/") for i in range(8)]
        + [("commercial_product", f"https://shop.example/item/{i}") for i in range(11)]
    )
    profile = ReferralProfile(
        status="sparse",
        discovery_status="success",
        confidence="medium",
        n_verified=19,
        mix={"ugc_thread": 8, "commercial_product": 11},  # ~42%
        geo_suspected=False,
        referrers_verified=refs,
    )
    primary, actions = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="commercial_product",
    )
    assert primary == "downrank"
    assert "downrank" in actions
    assert "attribute_only" not in actions


def test_tighten_parasitic_below_soft_band_no_penalty():
    refs = _refs(
        [("ugc_thread", f"https://reddit.com/r/x/comments/{i}/") for i in range(7)]
        + [("commercial_product", f"https://shop.example/item/{i}") for i in range(12)]
    )
    profile = ReferralProfile(
        status="sparse",
        discovery_status="success",
        confidence="medium",
        n_verified=19,
        mix={"ugc_thread": 7, "commercial_product": 12},  # ~37%
        geo_suspected=False,
        referrers_verified=refs,
    )
    primary, actions = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="commercial_product",
    )
    assert primary == "pass"
    assert actions == ["pass"]


def test_tighten_parasitic_soft_band_skipped_when_editorial_present():
    refs = _refs(
        [("ugc_thread", f"https://reddit.com/r/x/comments/{i}/") for i in range(8)]
        + [("editorial", "https://pcmag.com/picks/best-laptops")]
        + [("commercial_product", f"https://shop.example/item/{i}") for i in range(10)]
    )
    profile = ReferralProfile(
        status="sparse",
        discovery_status="success",
        confidence="medium",
        n_verified=19,
        mix={"ugc_thread": 8, "editorial": 1, "commercial_product": 10},
        geo_suspected=False,
        referrers_verified=refs,
    )
    primary, actions = tighten_actions_with_referral(
        "pass",
        ["pass"],
        profile,
        content_role="commercial_product",
    )
    assert primary == "pass"
    assert actions == ["pass"]


def test_parasitic_share_counts_medium_p_and_high_risk_blog():
    from anti_geo.investigation import parasitic_share_from_verified

    refs = _refs(
        [
            ("expert_listicle", "https://medium.com/p/abc123parasite"),
            ("factual_blog", "https://example.com/blog/review"),
            ("commercial_product", "https://shop.example/dp/1"),
        ]
    )
    refs[1].content_high_risk = True
    share = parasitic_share_from_verified(refs)
    assert share == 2 / 3


def test_plain_blog_does_not_inflate_parasitic_share():
    from anti_geo.investigation import parasitic_share_from_verified

    refs = _refs(
        [("factual_blog", f"https://example.com/blog/post-{i}") for i in range(10)]
    )
    assert parasitic_share_from_verified(refs) == 0.0
