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


def _subs(
    *,
    concealment: float = 0.0,
    trust: float = 0.65,
    fetch: float = 0.9,
    harm: float = 0.15,
) -> SourceSubscores:
    return SourceSubscores(
        fetch_confidence=fetch,
        source_trust=trust,
        rhetorical_manipulation=0.2,
        retrieval_manipulation_risk=0.1,
        endorsement_risk=0.0,
        factual_claim_reliability=0.6,
        intent_mismatch=0.15,
        harm_severity=harm,
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


def test_concealment_hard_hot_skips_llm(monkeypatch):
    source = _source()
    heur = SourcePermissions("allow", "allow", "allow", "allow")
    subs = _subs(concealment=CONCEALMENT_HARD_REJECT)

    def boom(*_a, **_k):
        raise AssertionError("LLM must not be called when concealment hard-hot")

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
    assert concealment_is_hot(subs, threshold=CONCEALMENT_HARD_REJECT)


def test_soft_concealment_endorse_tighten_only(monkeypatch):
    """Soft concealment [0.5, 0.9) still calls LLM; only endorse may tighten."""
    from anti_geo.permissions_llm import concealment_is_soft

    source = _source()
    heur = SourcePermissions("downrank", "allow", "attribute_only", "allow")
    subs = _subs(concealment=0.6)
    assert concealment_is_soft(subs)

    monkeypatch.setattr(
        "anti_geo.permissions_llm.is_azure_configured", lambda: True
    )
    monkeypatch.setattr(
        "anti_geo.permissions_llm.suggest_permissions_llm",
        lambda **_k: PermissionsLlmSuggestion(
            retrieve_permission="allow",
            mention_permission="deny",
            factual_permission="allow",
            endorsement_permission="deny",
            reason="vendorish soft conceal",
        ),
    )
    result = maybe_apply_permissions_llm(
        source,
        heur,
        subs,
        query="best widgets",
        query_intent="commercial",
        use_llm=True,
    )
    assert result.source == "llm_hybrid"
    assert result.permissions.retrieve_permission == "downrank"
    assert result.permissions.mention_permission == "allow"
    assert result.permissions.factual_permission == "attribute_only"
    assert result.permissions.endorsement_permission == "deny"


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


def test_protect_listicle_retrieve_allow_blocks_downrank():
    heur = SourcePermissions("allow", "allow", "attribute_only", "allow")
    suggestion = PermissionsLlmSuggestion(
        retrieve_permission="downrank",
        factual_permission="attribute_only",
        endorsement_permission="deny",
        reason="commercial packaging",
    )
    merged = merge_permissions_hybrid(
        heur,
        suggestion,
        hard_floor=False,
        protect_listicle_retrieve_allow=True,
    )
    assert merged.retrieve_permission == "allow"
    assert merged.endorsement_permission == "deny"


def test_protect_heuristic_retrieve_downrank_blocks_allow():
    heur = SourcePermissions("downrank", "allow", "require_corroboration", "deny")
    suggestion = PermissionsLlmSuggestion(
        retrieve_permission="allow",
        factual_permission="require_corroboration",
        endorsement_permission="deny",
        reason="high trust vendor",
    )
    merged = merge_permissions_hybrid(
        heur,
        suggestion,
        hard_floor=False,
        protect_heuristic_retrieve_downrank=True,
    )
    assert merged.retrieve_permission == "downrank"


def test_protect_listicle_factual_attribute_only_blocks_escalate():
    heur = SourcePermissions("allow", "allow", "attribute_only", "deny")
    suggestion = PermissionsLlmSuggestion(
        retrieve_permission="allow",
        factual_permission="require_corroboration",
        endorsement_permission="deny",
        reason="affiliate caution",
    )
    merged = merge_permissions_hybrid(
        heur,
        suggestion,
        hard_floor=False,
        protect_listicle_factual_attribute_only=True,
    )
    assert merged.factual_permission == "attribute_only"


def test_protect_listicle_factual_blocks_allow_to_require():
    heur = SourcePermissions("allow", "allow", "allow", "deny")
    suggestion = PermissionsLlmSuggestion(
        factual_permission="require_corroboration",
        reason="caution",
    )
    merged = merge_permissions_hybrid(
        heur,
        suggestion,
        hard_floor=False,
        protect_listicle_factual_attribute_only=True,
    )
    assert merged.factual_permission == "allow"


def test_protect_listicle_allows_allow_to_attribute_only_tighten():
    heur = SourcePermissions("allow", "allow", "allow", "deny")
    suggestion = PermissionsLlmSuggestion(
        factual_permission="attribute_only",
        reason="shopping review quote-cap",
    )
    merged = merge_permissions_hybrid(
        heur,
        suggestion,
        hard_floor=False,
        protect_listicle_factual_attribute_only=True,
    )
    assert merged.factual_permission == "attribute_only"


def test_protect_review_factual_no_allow():
    heur = SourcePermissions("allow", "allow", "attribute_only", "deny")
    suggestion = PermissionsLlmSuggestion(
        retrieve_permission="allow",
        factual_permission="allow",
        endorsement_permission="deny",
        reason="lab tested",
    )
    merged = merge_permissions_hybrid(
        heur,
        suggestion,
        hard_floor=False,
        protect_review_factual_no_allow=True,
    )
    assert merged.factual_permission == "attribute_only"


def test_protect_factual_blog_ao_blocks_allow_on_shopping(monkeypatch):
    source = _source()
    heur = SourcePermissions("allow", "allow", "attribute_only", "deny")
    monkeypatch.setattr(
        "anti_geo.permissions_llm.suggest_permissions_llm",
        lambda **_k: PermissionsLlmSuggestion(
            factual_permission="allow",
            endorsement_permission="deny",
            reason="lab blog",
        ),
    )
    result = maybe_apply_permissions_llm(
        source,
        heur,
        _subs(trust=0.7),
        query="best widgets 2026",
        query_intent="commercial",
        use_llm=True,
        content_role="factual_blog",
    )
    assert result.source == "llm_hybrid"
    assert result.permissions.factual_permission == "attribute_only"
    assert result.permissions.endorsement_permission == "deny"


def test_soft_fetch_floor_skips_llm(monkeypatch):
    source = _source(trust=0.8)
    source.fetch_ok = True
    heur = SourcePermissions("allow", "allow", "attribute_only", "allow")
    monkeypatch.setattr(
        "anti_geo.permissions_llm.suggest_permissions_llm",
        lambda **_k: (_ for _ in ()).throw(AssertionError("should skip")),
    )
    result = maybe_apply_permissions_llm(
        source,
        heur,
        _subs(fetch=0.1, trust=0.8),
        query="fda guidance on widgets",
        query_intent="informational",
        fetch_failure_kind=None,
        use_llm=True,
        content_role="institutional",
    )
    assert result.source == "heuristic"
    assert result.skipped == "soft_fetch_floor"
    assert result.permissions == heur


def test_listicle_factual_clamps_applied_even_when_soft_conceal(monkeypatch):
    """Hard listicle factual clamps fire regardless of soft concealment/harm."""
    source = _source()
    heur = SourcePermissions("allow", "allow", "attribute_only", "deny")
    monkeypatch.setattr(
        "anti_geo.permissions_llm.suggest_permissions_llm",
        lambda **_k: PermissionsLlmSuggestion(
            factual_permission="allow",
            endorsement_permission="deny",
            reason="trusted labs",
        ),
    )
    # Soft concealment → endorse_tighten_only freezes factual; use no concealment
    # but high harm would previously disable protect_listicle — verify clamp holds.
    result = maybe_apply_permissions_llm(
        source,
        heur,
        _subs(harm=0.8, concealment=0.0),
        query="best widgets 2026",
        query_intent="commercial",
        use_llm=True,
        content_role="expert_listicle",
    )
    assert result.source == "llm_hybrid"
    assert result.permissions.factual_permission == "attribute_only"


def test_protect_heuristic_endorsement_deny_blocks_allow():
    heur = SourcePermissions("allow", "allow", "attribute_only", "deny")
    suggestion = PermissionsLlmSuggestion(
        retrieve_permission="allow",
        factual_permission="attribute_only",
        endorsement_permission="allow",
        reason="trusted review",
    )
    merged = merge_permissions_hybrid(
        heur,
        suggestion,
        hard_floor=False,
        protect_heuristic_endorsement_deny=True,
    )
    assert merged.endorsement_permission == "deny"


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


def test_gate_true_when_soft_concealment_shopping():
    """Soft concealment on shopping opens gate for endorse-tighten."""
    source = _source()
    heur = SourcePermissions("downrank", "allow", "allow", "allow")
    assert permissions_llm_gate(
        source,
        "best widgets",
        "commercial",
        heur,
        _subs(concealment=0.6),
    )


def test_gate_false_when_concealment_hard():
    source = _source()
    heur = SourcePermissions("allow", "allow", "allow", "allow")
    assert not permissions_llm_gate(
        source,
        "best widgets",
        "commercial",
        heur,
        _subs(concealment=0.95),
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


def test_rubric_tracks_permissions_constants(monkeypatch):
    """Changing permissions.py thresholds must change the hybrid system prompt."""
    import anti_geo.permissions as permissions

    monkeypatch.setattr(permissions, "CONCEALMENT_REJECT", 0.91)
    monkeypatch.setattr(permissions, "SOURCE_TRUST_DOWNRANK", 0.33)
    text = permissions.permissions_heuristic_rules_rubric()
    assert "concealment_risk >= 0.91" in text
    assert "source_trust < 0.33" in text
    assert "derive_permissions" in text
    assert "KNOWN HEURISTIC BLIND SPOTS" in text
    assert "RESEARCH" in text


def test_rubric_includes_high_stakes_and_commercial(monkeypatch):
    import anti_geo.permissions as permissions
    from anti_geo.config import DefenseConfig

    monkeypatch.setattr(permissions, "HIGH_STAKES_ENDORSE_TRUST_MAX", 0.51)
    text = permissions.permissions_heuristic_rules_rubric(
        DefenseConfig(trust_endorsement_min=0.71, commercial_hedge_min_tier="high")
    )
    assert "high_stakes_medical_claim" in text
    assert "trust < 0.51" in text
    assert "Commercial packaging tighten" in text
    assert "commercial tier >= high" in text
    assert "trust < 0.71" in text


def test_apply_high_stakes_endorsement_deny_same_predicates():
    from anti_geo.permissions import apply_high_stakes_endorsement_deny

    source = _source(
        trust=0.4,
        text="This supplement cured my condition and brought remission.",
        flags=["high_stakes_medical_claim", "comparative_superlatives"],
    )
    heur = SourcePermissions("allow", "allow", "attribute_only", "allow")
    out = apply_high_stakes_endorsement_deny(
        heur,
        source,
        query="is this supplement safe",
        query_intent="informational_high_stakes",
    )
    assert out.endorsement_permission == "deny"
    assert out.retrieve_permission == "allow"

    kept = apply_high_stakes_endorsement_deny(
        heur,
        source,
        query="is this supplement safe",
        query_intent="informational",
    )
    assert kept.endorsement_permission == "allow"
