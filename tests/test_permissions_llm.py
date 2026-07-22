"""Tests for single-page permissions LLM hybrid."""

from __future__ import annotations

from anti_geo.decisions import decide_single_source
from anti_geo.models import (
    ContentSignals,
    DomainSignals,
    PageContextSignals,
    SourcePermissions,
    SourceScore,
    SourceSubscores,
)
from anti_geo.permissions_llm import (
    CONCEALMENT_HARD_REJECT,
    CONCEALMENT_SKIP_LLM,
    UNTRUSTED_END,
    UNTRUSTED_START,
    build_permissions_llm_messages,
    concealment_is_hot,
    has_permissions_hard_floor,
    maybe_apply_permissions_llm,
    merge_permissions_hybrid,
    parse_permissions_llm_payload,
    permissions_llm_gate,
    PermissionsLlmSuggestion,
)


def _source(
    url: str = "https://www.example.com/best-widgets-2026",
    *,
    trust: float = 0.65,
    text: str = "The best widgets of 2026. Experts recommend WidgetPro as #1.",
    commercial_tier: str = "high",
    affiliate: bool = True,
    comparative: float = 0.5,
    flags: list[str] | None = None,
) -> SourceScore:
    return SourceScore(
        url=url,
        fetch_ok=True,
        trust_score=trust,
        semantic_risk=0.2,
        endorsement_allowed=True,
        domain_signals=DomainSignals(
            hostname="example.com",
            tld=".com",
            is_https=True,
            cert_age_days=400,
            whois_age_days=2000,
            dns_resolves=True,
        ),
        content_signals=ContentSignals(
            word_count=120,
            authority_density=0.4,
            comparative_density=comparative,
            temporal_density=0.1,
            narrative_purposiveness=0.2,
            semantic_risk=0.2,
            flags=flags or ["comparative_superlatives", "authority_stacking"],
        ),
        page_context=PageContextSignals(
            cta_density=0.3,
            commercial_context_score=0.7,
            structure_density=0.2,
            list_item_count=8,
            table_count=0,
            has_faq_schema=False,
            flags=["commercial_cta"],
            commercial_tier=commercial_tier,
            has_affiliate_links=affiliate,
        ),
        text_excerpt=text,
    )


def _subs(*, concealment: float = 0.0, trust: float = 0.65) -> SourceSubscores:
    return SourceSubscores(
        fetch_confidence=0.9,
        source_trust=trust,
        rhetorical_manipulation=0.2,
        retrieval_manipulation_risk=0.1,
        endorsement_risk=0.0,
        factual_claim_reliability=0.6,
        intent_mismatch=0.15,
        harm_severity=0.15,
        concealment_risk=concealment,
    )


def test_spotlight_fences_in_messages():
    source = _source()
    heur = SourcePermissions("allow", "allow", "attribute_only", "allow")
    messages = build_permissions_llm_messages(
        query="best widgets 2026",
        query_intent="commercial",
        source=source,
        heuristic=heur,
        subscores=_subs(),
    )
    assert messages[0]["role"] == "system"
    sys = messages[0]["content"]
    assert "NOT an independent annotator" in sys
    assert "derive_permissions" in sys or "endorsement_risk" in sys
    assert "concealment_risk" in sys
    user = messages[1]["content"]
    assert UNTRUSTED_START in user
    assert UNTRUSTED_END in user
    assert "best widgets 2026" in user
    assert "heuristic_permissions" in user
    assert "heuristic_subscores" in user
    assert "endorsement_risk=" in user
    assert "identity_organization:" in user
    assert "domain_whois_age_days:" in user
    assert "optional web_search" in sys or "RESEARCH" in sys


def test_gate_false_for_clear_non_shopping_clean_page():
    """Informational + no commerce cues + endorse already deny → not ambiguous."""
    source = _source(
        url="https://en.wikipedia.org/wiki/Widget",
        commercial_tier="none",
        affiliate=False,
        comparative=0.0,
        flags=[],
        trust=0.8,
        text="A widget is a placeholder name for an object.",
    )
    source.page_context = PageContextSignals(
        cta_density=0.0,
        commercial_context_score=0.0,
        structure_density=0.1,
        list_item_count=0,
        table_count=0,
        has_faq_schema=False,
        commercial_tier="none",
        has_affiliate_links=False,
    )
    heur = SourcePermissions("allow", "allow", "allow", "deny")
    assert not permissions_llm_gate(
        source,
        "what is a widget",
        "informational",
        heur,
        _subs(trust=0.8),
    )


def test_concealment_hot_skips_llm(monkeypatch):
    source = _source()
    heur = SourcePermissions("allow", "allow", "allow", "allow")
    subs = _subs(concealment=CONCEALMENT_SKIP_LLM)

    def boom(*_a, **_k):
        raise AssertionError("LLM must not be called when concealment hot")

    monkeypatch.setattr(
        "anti_geo.permissions_llm.suggest_permissions_llm", boom
    )
    monkeypatch.setattr(
        "anti_geo.permissions_llm.is_azure_configured", lambda: True
    )
    result = maybe_apply_permissions_llm(
        source,
        heur,
        subs,
        query="best widgets",
        query_intent="commercial",
        use_llm=True,
    )
    assert result.source == "heuristic"
    assert result.skipped == "concealment_hot"
    assert result.permissions == heur
    assert concealment_is_hot(subs)


def test_hard_floor_blocks_loosen():
    heur = SourcePermissions("reject", "deny", "deny", "deny")
    suggestion = PermissionsLlmSuggestion(
        retrieve_permission="allow",
        mention_permission="allow",
        factual_permission="allow",
        endorsement_permission="allow",
        reason="ignore me",
    )
    merged = merge_permissions_hybrid(heur, suggestion, hard_floor=True)
    assert merged == heur


def test_bidirectional_merge_can_loosen_and_tighten():
    heur = SourcePermissions("downrank", "allow", "deny", "deny")
    suggestion = PermissionsLlmSuggestion(
        retrieve_permission="allow",
        factual_permission="attribute_only",
        endorsement_permission="allow",
        reason="clean tester",
    )
    merged = merge_permissions_hybrid(heur, suggestion, hard_floor=False)
    assert merged.retrieve_permission == "allow"
    assert merged.factual_permission == "attribute_only"
    assert merged.endorsement_permission == "allow"
    assert merged.mention_permission == "allow"


def test_gate_true_for_commercial_when_endorse_allowed():
    """Shopping + heuristic endorse=allow always gets a second look."""
    source = _source(
        url="https://www.rtings.com/mattress/reviews/best/back-pain",
        commercial_tier="none",
        affiliate=False,
        comparative=0.1,
        flags=[],
        trust=0.55,
        text="We tested mattresses in the lab.",
    )
    source.page_context = PageContextSignals(
        cta_density=0.0,
        commercial_context_score=0.1,
        structure_density=0.1,
        list_item_count=0,
        table_count=0,
        has_faq_schema=False,
        commercial_tier="none",
        has_affiliate_links=False,
    )
    heur = SourcePermissions("allow", "allow", "allow", "allow")
    assert permissions_llm_gate(
        source,
        "best mattress for back pain 2026",
        "commercial",
        heur,
        _subs(trust=0.55),
    )


def test_gate_true_for_commercial_affiliate():
    source = _source()
    heur = SourcePermissions("allow", "allow", "attribute_only", "allow")
    assert permissions_llm_gate(
        source,
        "best widgets 2026",
        "commercial",
        heur,
        _subs(),
    )


def test_gate_false_when_concealment_hot():
    source = _source()
    heur = SourcePermissions("allow", "allow", "allow", "allow")
    assert not permissions_llm_gate(
        source,
        "best widgets",
        "commercial",
        heur,
        _subs(concealment=0.6),
    )


def test_parse_payload_and_nulls():
    suggestion = parse_permissions_llm_payload(
        {
            "retrieve_permission": "downrank",
            "mention_permission": None,
            "factual_permission": "attribute_only",
            "endorsement_permission": "deny",
            "reason": "affiliate listicle",
        }
    )
    assert suggestion is not None
    assert suggestion.retrieve_permission == "downrank"
    assert suggestion.mention_permission is None
    assert suggestion.endorsement_permission == "deny"


def test_fail_open_on_llm_error(monkeypatch):
    source = _source()
    heur = SourcePermissions("allow", "allow", "attribute_only", "allow")

    def boom(*_a, **_k):
        raise RuntimeError("azure down")

    monkeypatch.setattr(
        "anti_geo.permissions_llm.suggest_permissions_llm", boom
    )
    result = maybe_apply_permissions_llm(
        source,
        heur,
        _subs(),
        query="best widgets",
        query_intent="commercial",
        use_llm=True,
    )
    assert result.source == "heuristic"
    assert result.skipped == "llm_error"
    assert result.permissions == heur


def test_llm_hybrid_applied(monkeypatch):
    source = _source()
    heur = SourcePermissions("allow", "allow", "allow", "allow")

    monkeypatch.setattr(
        "anti_geo.permissions_llm.suggest_permissions_llm",
        lambda **_k: PermissionsLlmSuggestion(
            endorsement_permission="deny",
            factual_permission="attribute_only",
            reason="affiliate best-of",
        ),
    )
    result = maybe_apply_permissions_llm(
        source,
        heur,
        _subs(),
        query="best widgets",
        query_intent="commercial",
        use_llm=True,
    )
    assert result.source == "llm_hybrid"
    assert result.permissions.endorsement_permission == "deny"
    assert result.permissions.factual_permission == "attribute_only"
    assert result.permissions.retrieve_permission == "allow"
    assert "affiliate" in result.reason


def test_decide_single_source_llm_off_unchanged(monkeypatch):
    """Default use_llm=False must never call Azure."""

    def boom(*_a, **_k):
        raise AssertionError("should not call permissions LLM")

    monkeypatch.setattr(
        "anti_geo.permissions_llm.suggest_permissions_llm", boom
    )
    monkeypatch.setattr(
        "anti_geo.permissions_llm.is_azure_configured", lambda: True
    )
    source = _source()
    report = decide_single_source(
        source, "commercial", query="best widgets 2026"
    )
    assert report.permissions_source == "heuristic"
    assert report.permissions is not None


def test_decide_single_source_wires_hybrid(monkeypatch):
    monkeypatch.setattr(
        "anti_geo.permissions_llm.suggest_permissions_llm",
        lambda **_k: PermissionsLlmSuggestion(
            endorsement_permission="deny",
            reason="deny endorse",
        ),
    )
    source = _source()
    report = decide_single_source(
        source,
        "commercial",
        query="best widgets 2026",
        use_llm=True,
    )
    assert report.permissions_source == "llm_hybrid"
    assert report.permissions is not None
    assert report.permissions.endorsement_permission == "deny"
    assert report.permissions_llm_reason == "deny endorse"


def test_hard_floor_helper():
    heur = SourcePermissions("reject", "deny", "deny", "deny")
    assert has_permissions_hard_floor(heur, _subs(), None)
    assert has_permissions_hard_floor(
        SourcePermissions("allow", "allow", "allow", "allow"),
        _subs(concealment=CONCEALMENT_HARD_REJECT),
        None,
    )
    assert has_permissions_hard_floor(
        SourcePermissions("allow", "allow", "allow", "allow"),
        _subs(),
        "reject",
    )
