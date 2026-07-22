"""Mode A query investigation tests."""

from __future__ import annotations

from anti_geo.audit.models import EngineResponse
from anti_geo.investigation import ReferralProfile, VerifiedReferrer
from anti_geo.models import FetchResult, PageContextSignals
from anti_geo.platform_role import is_ugc_role
from anti_geo.query_investigation import (
    format_query_investigation_report,
    investigate_query,
)


class _QueryEngine:
    name = "query_stub"

    def __init__(self, cites: list[str]) -> None:
        self.cites = cites
        self.queries: list[str] = []

    def query(self, q: str) -> EngineResponse:
        self.queries.append(q)
        return EngineResponse(
            text="answer",
            cited_domains=[],
            cited_urls=list(self.cites),
        )


def _fetch_for(url: str, *, title: str, text: str, commercial: bool = False) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        ok=True,
        error=None,
        title=title,
        text=text,
        link_count=5,
        broken_link_ratio=0.0,
        redirect_count=0,
        response_time_ms=50,
        has_privacy_page=False,
        has_contact_page=False,
        page_context=PageContextSignals(
            cta_density=0.4 if commercial else 0.05,
            commercial_context_score=0.7 if commercial else 0.05,
            structure_density=0.3,
            list_item_count=2,
            table_count=0,
            has_faq_schema=False,
            flags=["commercial_cta"] if commercial else [],
            commercial_tier="high" if commercial else "none",
        ),
    )


REDDIT = "https://www.reddit.com/r/laptops/comments/abc123/budget_tip/"
COMMERCIAL = "https://www.brandshop.com/products/neo-laptop"
EDITORIAL = "https://www.pcmag.com/picks/the-best-budget-laptops"


def test_is_ugc_role():
    assert is_ugc_role("ugc_thread")
    assert not is_ugc_role("editorial")
    assert not is_ugc_role("commercial_product")
    assert not is_ugc_role("expert_listicle")


def test_mode_b_skips_linkedin_cite(monkeypatch):
    linkedin = "https://www.linkedin.com/posts/someone_best-widget-rec"
    engine = _QueryEngine([linkedin, COMMERCIAL])
    discover_calls: list[str] = []

    def fake_fetch(url: str, **kwargs):
        if "linkedin.com" in url:
            return _fetch_for(url, title="post", text="saw this widget recommended " * 20)
        return _fetch_for(
            url,
            title="Neo Laptop | BrandShop",
            text="Buy the Neo Laptop now. Add to cart. Free shipping.",
            commercial=True,
        )

    def fake_discover(target_url, entity, seeds, engine, **kwargs):
        discover_calls.append(target_url)
        return ReferralProfile(
            status="sparse",
            discovery_status="success",
            confidence="low",
            n_verified=0,
            mix={},
        )

    monkeypatch.setattr("anti_geo.query_investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.discover_referrers", fake_discover)
    monkeypatch.setattr(
        "anti_geo.investigation.resolve_seed_queries",
        lambda *a, **k: (["s1"], "template", "high"),
    )

    result = investigate_query("best widget", engine=engine, site_workers=1)
    assert any(r.is_ugc and "linkedin.com" in r.url for r in result.rows)
    assert all("linkedin.com" not in u for u in discover_calls)
    assert result.ugc_skipped >= 1


def test_investigate_query_skips_mode_b_for_ugc(monkeypatch):
    engine = _QueryEngine([REDDIT, COMMERCIAL])
    discover_calls: list[str] = []

    def fake_fetch(url: str, **kwargs):
        if "reddit.com" in url:
            return _fetch_for(
                url,
                title="Budget tip thread",
                text=(
                    "My dad got me a neo laptop from BrandShop last month and it "
                    "handles school work fine. Anyway checking capital gains advice."
                ),
            )
        return _fetch_for(
            url,
            title="Neo Laptop | BrandShop",
            text="Buy the Neo Laptop now. Add to cart. Free shipping.",
            commercial=True,
        )

    def fake_discover(target_url, entity, seeds, engine, **kwargs):
        discover_calls.append(target_url)
        return ReferralProfile(
            status="sparse",
            discovery_status="success",
            confidence="medium",
            n_verified=4,
            mix={"ugc_thread": 3, "editorial": 1},
            referrers_verified=[
                VerifiedReferrer(
                    url=f"https://www.reddit.com/r/x/comments/{i}/",
                    role="ugc_thread",
                    connection="brand_mention",
                    connection_confidence="weak",
                )
                for i in range(3)
            ]
            + [
                VerifiedReferrer(
                    url="https://www.pcmag.com/reviews/neo",
                    role="editorial",
                    connection="url_link",
                )
            ],
            notes=["mock"],
        )

    monkeypatch.setattr("anti_geo.query_investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.discover_referrers", fake_discover)
    monkeypatch.setattr(
        "anti_geo.investigation.resolve_seed_queries",
        lambda *a, **k: (["seed a", "seed b"], "template", "high"),
    )

    result = investigate_query(
        "best budget laptop brandshop",
        engine=engine,
        site_workers=2,
        seed_workers=1,
        fetch_workers=1,
        adaptive_stop=True,
    )

    assert REDDIT in result.cited_urls or any("reddit.com" in u for u in result.cited_urls)
    assert any(r.is_ugc for r in result.rows)
    ugc_row = next(r for r in result.rows if r.is_ugc)
    assert ugc_row.n_verified is None or ugc_row.referral_profile.status == "skipped"
    assert ugc_row.llm_action  # always emitted

    non_ugc = [r for r in result.rows if not r.is_ugc]
    assert non_ugc
    assert all(r.n_verified is not None for r in non_ugc)
    assert all(r.parasitic_verified_share is not None for r in non_ugc)
    # discover_referrers must never run against the Reddit cite
    assert all("reddit.com" not in u for u in discover_calls)
    assert any("brandshop.com" in u for u in discover_calls)
    assert result.mode_b_ran >= 1
    assert result.ugc_skipped >= 1


def test_format_hides_verified_lines_for_ugc(monkeypatch):
    engine = _QueryEngine([REDDIT, EDITORIAL])

    def fake_fetch(url: str, **kwargs):
        if "reddit.com" in url:
            return _fetch_for(url, title="thread", text="casual laptop chat " * 20)
        return _fetch_for(
            url,
            title="Best Budget Laptops | PCMag",
            text="Independent editors review budget laptops. Our picks below.",
        )

    def fake_discover(target_url, entity, seeds, engine, **kwargs):
        return ReferralProfile(
            status="complete",
            discovery_status="success",
            confidence="medium",
            n_verified=12,
            mix={"ugc_thread": 10, "editorial": 2},
            referrers_verified=[
                VerifiedReferrer(
                    url=f"https://www.reddit.com/r/x/comments/{i}/",
                    role="ugc_thread",
                    connection="brand_mention",
                )
                for i in range(10)
            ]
            + [
                VerifiedReferrer(
                    url=f"https://www.pcmag.com/reviews/{i}",
                    role="editorial",
                    connection="url_link",
                )
                for i in range(2)
            ],
        )

    monkeypatch.setattr("anti_geo.query_investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.discover_referrers", fake_discover)
    monkeypatch.setattr(
        "anti_geo.investigation.resolve_seed_queries",
        lambda *a, **k: (["s1"], "template", "high"),
    )

    result = investigate_query("best budget laptops", engine=engine, site_workers=1)
    text = format_query_investigation_report(result)
    assert "[ugc]" in text
    assert "[non-ugc]" in text
    assert "LLM action:" in text
    assert "Verified connections:" in text
    assert "Parasitic among verified:" in text
    assert "── Cluster risk ──" in text
    # UGC block should not claim verified connections before its LLM action in a brittle way;
    # ensure the ugc section does not include a verified line immediately under the reddit URL.
    ugc_block = text.split("[ugc]")[1].split("[non-ugc]")[0]
    assert "Verified connections:" not in ugc_block


def test_cluster_section_present_with_two_sources(monkeypatch):
    engine = _QueryEngine([REDDIT, EDITORIAL])
    shared = (
        "The Neo Laptop is a breakthrough device widely regarded as the best budget option "
        "you should buy today for school and work."
    )

    def fake_fetch(url: str, **kwargs):
        if "reddit.com" in url:
            return _fetch_for(url, title="neo", text=shared + " reddit extras")
        return _fetch_for(url, title="neo editorial", text=shared + " pcmag extras")

    monkeypatch.setattr("anti_geo.query_investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    monkeypatch.setattr(
        "anti_geo.investigation.discover_referrers",
        lambda *a, **k: ReferralProfile(
            status="sparse",
            discovery_status="success",
            confidence="low",
            n_verified=0,
            mix={},
        ),
    )
    monkeypatch.setattr(
        "anti_geo.investigation.resolve_seed_queries",
        lambda *a, **k: (["s1"], "template", "high"),
    )

    result = investigate_query("neo laptop review", engine=engine, site_workers=1)
    assert result.independence is not None
    assert result.independence.cluster_count >= 1
    text = format_query_investigation_report(result)
    assert "cluster_count=" in text
    assert result.guard is not None
    assert result.guard.actions


def test_parallel_site_workers_completes(monkeypatch):
    cites = [
        COMMERCIAL,
        "https://www.otherbrand.com/products/widget",
        EDITORIAL,
    ]
    engine = _QueryEngine(cites)
    calls = {"n": 0}

    def fake_fetch(url: str, **kwargs):
        return _fetch_for(
            url,
            title="Product",
            text="Buy now add to cart subscribe free trial " * 10,
            commercial="product" in url or "brand" in url,
        )

    def fake_discover(target_url, entity, seeds, engine, **kwargs):
        calls["n"] += 1
        return ReferralProfile(
            status="sparse",
            discovery_status="success",
            confidence="low",
            n_verified=2,
            mix={"ugc_thread": 2},
        )

    monkeypatch.setattr("anti_geo.query_investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.discover_referrers", fake_discover)
    monkeypatch.setattr(
        "anti_geo.investigation.resolve_seed_queries",
        lambda *a, **k: (["s1", "s2"], "template", "high"),
    )

    result = investigate_query(
        "best widgets",
        engine=engine,
        site_workers=2,
        seed_workers=1,
        fetch_workers=1,
    )
    assert len(result.rows) == 3
    assert calls["n"] == 3  # all non-UGC
    assert result.mode_b_ran == 3


def test_rejected_answer_cites_do_not_use_grounding_pool(monkeypatch):
    from dataclasses import replace

    from anti_geo.decisions import decide_single_source as real_decide

    answer = "https://spam.example/product/bad"
    pool_good = [
        "https://www.pcmag.com/picks/the-best-personalized-jewelry",
        "https://www.wirecutter.com/reviews/best-jewelry/",
    ]

    class _EngineWithPool(_QueryEngine):
        def query(self, q: str) -> EngineResponse:
            resp = super().query(q)
            return EngineResponse(
                text=resp.text,
                cited_domains=resp.cited_domains,
                cited_urls=resp.cited_urls,
                source_pool_urls=list(pool_good),
            )

    eng = _EngineWithPool([answer])

    def fake_fetch(url: str, **kwargs):
        return _fetch_for(
            url,
            title="Best jewelry",
            text="Independent editors review personalized jewelry picks carefully.",
            commercial="spam.example" in url,
        )

    def fake_decide(source, query_intent="informational", query=None):
        report = real_decide(source, query_intent, query=query)
        if "spam.example" in source.url and report.permissions is not None:
            return replace(
                report,
                recommended_action="reject",
                permissions=replace(
                    report.permissions,
                    retrieve_permission="reject",
                    mention_permission="deny",
                ),
            )
        return report

    monkeypatch.setattr("anti_geo.query_investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.query_investigation.decide_single_source", fake_decide)
    monkeypatch.setattr(
        "anti_geo.investigation.discover_referrers",
        lambda *a, **k: ReferralProfile(
            status="sparse",
            discovery_status="success",
            confidence="low",
            n_verified=0,
            mix={},
        ),
    )
    monkeypatch.setattr(
        "anti_geo.investigation.resolve_seed_queries",
        lambda *a, **k: (["s1"], "template", "high"),
    )

    result = investigate_query("best jewelry", engine=eng, site_workers=2)
    assert any("completely rejected" in n for n in result.notes)
    assert result.cited_urls == [answer]
    assert all("pcmag.com" not in r.url and "wirecutter.com" not in r.url for r in result.rows)


def test_adaptive_stop_helper():
    from anti_geo.investigation import _referral_mix_decisive

    few = [
        VerifiedReferrer(
            url=f"https://reddit.com/r/x/comments/{i}/",
            role="ugc_thread",
            connection="brand_mention",
        )
        for i in range(5)
    ]
    assert not _referral_mix_decisive(few)

    heavy = [
        VerifiedReferrer(
            url=f"https://reddit.com/r/x/comments/{i}/",
            role="ugc_thread",
            connection="brand_mention",
        )
        for i in range(8)
    ]
    assert _referral_mix_decisive(heavy)

    relieved = heavy[:7] + [
        VerifiedReferrer(
            url="https://www.pcmag.com/a",
            role="editorial",
            connection="url_link",
        )
    ]
    assert not _referral_mix_decisive(relieved)

    editorial_n = [
        VerifiedReferrer(
            url=f"https://www.pcmag.com/a{i}",
            role="editorial",
            connection="url_link",
        )
        for i in range(10)
    ]
    assert _referral_mix_decisive(editorial_n)


def test_mode_a_zero_verified_soft_downranks_non_editorial(monkeypatch):
    shop = "https://gldn.example/about/personalized-jewelry-guide"
    engine = _QueryEngine([shop])

    def fake_fetch(url: str, **kwargs):
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            ok=True,
            error=None,
            title="Personalized Jewelry Guide | GLDN",
            text=(
                "A careful overview of personalized jewelry materials, engraving options, "
                "and sizing tips for buyers who want durable everyday pieces. "
                "We describe common trade-offs without ranking brands. "
            )
            * 8,
            link_count=12,
            broken_link_ratio=0.0,
            redirect_count=0,
            response_time_ms=80,
            has_privacy_page=True,
            has_contact_page=True,
            page_context=PageContextSignals(
                cta_density=0.05,
                commercial_context_score=0.1,
                structure_density=0.4,
                list_item_count=4,
                table_count=0,
                has_faq_schema=False,
                flags=[],
                commercial_tier="none",
            ),
        )

    monkeypatch.setattr("anti_geo.query_investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    monkeypatch.setattr(
        "anti_geo.investigation.discover_referrers",
        lambda *a, **k: ReferralProfile(
            status="sparse",
            discovery_status="success",
            confidence="medium",
            n_verified=0,
            mix={},
            parasitic_geo_suspected=False,
        ),
    )
    monkeypatch.setattr(
        "anti_geo.investigation.resolve_seed_queries",
        lambda *a, **k: (["s1"], "template", "high"),
    )

    result = investigate_query(
        "personalized jewelry engraving tips",
        query_intent="informational",
        engine=engine,
        site_workers=1,
    )
    row = result.rows[0]
    assert row.n_verified == 0
    assert row.llm_action == "downrank"
    assert "downrank" in row.llm_actions
    assert any("structural parasitic-surface/editorial mix" in n for n in result.notes)


def test_mode_a_parasitic_geo_suspected_tightens_pass(monkeypatch):
    shop = "https://newbrand.example/products/widget"
    engine = _QueryEngine([shop])

    def fake_fetch(url: str, **kwargs):
        return _fetch_for(
            url,
            title="Widget | NewBrand",
            text="Buy the widget now. Best in class. Add to cart today.",
            commercial=True,
        )

    monkeypatch.setattr("anti_geo.query_investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", fake_fetch)
    monkeypatch.setattr(
        "anti_geo.investigation.discover_referrers",
        lambda *a, **k: ReferralProfile(
            status="complete",
            discovery_status="success",
            confidence="medium",
            n_verified=22,
            mix={"ugc_thread": 20},
            parasitic_geo_suspected=True,
            notes=["UGC-heavy verified referrer mix with no editorial/institutional share."],
        ),
    )
    monkeypatch.setattr(
        "anti_geo.investigation.resolve_seed_queries",
        lambda *a, **k: (["s1"], "template", "high"),
    )

    result = investigate_query("best widget brand", engine=engine, site_workers=1)
    row = result.rows[0]
    assert row.llm_action in ("attribute_only", "block_endorsement")
    assert "attribute_only" in row.llm_actions


def test_mode_a_reuses_scored_cite_for_mode_b(monkeypatch):
    """Mode B must not re-fetch/re-score the target after Mode A scoring."""
    engine = _QueryEngine([COMMERCIAL])
    fetch_calls: list[str] = []

    def fake_fetch(url: str, **kwargs):
        fetch_calls.append(url)
        return _fetch_for(
            url,
            title="Neo Laptop | BrandShop",
            text="Buy the Neo Laptop now. Add to cart. Free shipping.",
            commercial=True,
        )

    def boom_fetch(url: str, **kwargs):
        raise AssertionError(f"Mode B must not re-fetch target: {url}")

    monkeypatch.setattr("anti_geo.query_investigation.fetch_page", fake_fetch)
    monkeypatch.setattr("anti_geo.investigation.fetch_page", boom_fetch)
    monkeypatch.setattr(
        "anti_geo.investigation.discover_referrers",
        lambda *a, **k: ReferralProfile(
            status="sparse",
            discovery_status="success",
            confidence="medium",
            n_verified=3,
            mix={"editorial": 2, "ugc_thread": 1},
        ),
    )
    monkeypatch.setattr(
        "anti_geo.investigation.resolve_seed_queries",
        lambda *a, **k: (["s1"], "template", "high"),
    )

    result = investigate_query(
        "best neo laptop",
        engine=engine,
        site_workers=1,
        seed_workers=1,
        fetch_workers=1,
    )
    assert result.mode_b_ran == 1
    assert len(fetch_calls) == 1
    assert fetch_calls[0] == COMMERCIAL
    assert result.rows[0].n_verified == 3
