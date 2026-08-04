from anti_geo.config import DEFAULT_CONFIG
from anti_geo.models import QueryContextScores, SourcePermissions, SourceSubscores
from anti_geo.permissions import (
    _derive_endorsement_permission,
    derive_llm_actions,
    derive_permissions,
    merge_llm_actions,
)


def test_derive_permissions_defer_denies_all_content_use():
    """Failed fetch → defer retrieve; no mention/facts/endorse until re-fetched."""
    subs = SourceSubscores(
        fetch_confidence=0.2,
        source_trust=0.5,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.5,
        intent_mismatch=0.0,
        harm_severity=0.35,
    )
    perms = derive_permissions(subs, fetch_failure_kind="defer")
    assert perms.retrieve_permission == "defer"
    assert perms.mention_permission == "deny"
    assert perms.factual_permission == "deny"
    assert perms.endorsement_permission == "deny"
    primary, actions = derive_llm_actions(perms, subs)
    assert primary == "defer_fetch"
    assert "defer_fetch" in actions
    assert "reject" not in actions


def test_derive_llm_actions_pass_for_clean_source():
    perms = SourcePermissions("allow", "allow", "allow", "allow")
    subscores = SourceSubscores(0.9, 0.7, 0.0, 0.0, 0.0, 0.7, 0.0, 0.35)
    primary, actions = derive_llm_actions(perms, subscores)
    assert primary == "pass"
    assert actions == ["pass"]


def test_derive_llm_actions_block_endorsement_and_factual():
    perms = SourcePermissions("downrank", "allow", "deny", "deny")
    subscores = SourceSubscores(0.8, 0.3, 0.6, 0.5, 0.7, 0.2, 0.1, 0.35)
    primary, actions = derive_llm_actions(perms, subscores)
    assert primary == "block_factual_use"
    assert "downrank" in actions
    assert "block_factual_use" in actions
    assert "block_endorsement" in actions


def test_merge_llm_actions_tightens_only():
    primary, actions = merge_llm_actions("pass", ["pass"], "downrank")
    assert primary == "downrank"
    assert "pass" in actions and "downrank" in actions

    primary, actions = merge_llm_actions("reject", ["reject"], "attribute_only")
    assert primary == "reject"


def test_ugc_site_cite_policy_blocks_endorsement():
    from anti_geo.permissions import apply_ugc_site_cite_policy

    perms = SourcePermissions("allow", "allow", "allow", "allow")
    tightened = apply_ugc_site_cite_policy(perms)
    assert tightened.endorsement_permission == "deny"
    assert tightened.factual_permission == "attribute_only"
    assert tightened.mention_permission == "allow"
    primary, actions = derive_llm_actions(tightened)
    assert primary == "block_endorsement"
    assert "attribute_only" in actions
    assert "mention_only" in actions
    assert "pass" not in actions


def test_tiny_endorsement_risk_does_not_deny_mid_trust():
    """Noise-floor endorsement risk must not block wikipedia-like mid trust."""
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.61,
        rhetorical_manipulation=0.02,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.001,
        factual_claim_reliability=0.67,
        intent_mismatch=0.0,
        harm_severity=0.35,
    )
    perms = derive_permissions(subs)
    assert perms.endorsement_permission == "allow"
    assert perms.factual_permission == "allow"


def test_meaningful_endorsement_risk_still_denies_low_trust():
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.50,
        rhetorical_manipulation=0.1,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.12,
        factual_claim_reliability=0.55,
        intent_mismatch=0.0,
        harm_severity=0.35,
    )
    assert (
        _derive_endorsement_permission(
            subs,
            "attribute_only",
            QueryContextScores("healthy", 0.0, 0.0),
            False,
            DEFAULT_CONFIG,
        )
        == "deny"
    )


def test_high_rhetoric_alone_does_not_deny_endorsement():
    """Weak premise: salesy packaging without high stakes must not block endorse."""
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.8,
        retrieval_manipulation_risk=0.7,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.35,
    )
    perms = derive_permissions(subs, has_persuasive_content=True)
    assert perms.endorsement_permission == "allow"
    assert perms.retrieve_permission == "allow"


def test_high_stakes_persuasive_low_trust_denies_endorsement():
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.50,
        rhetorical_manipulation=0.8,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.85,
    )
    perms = derive_permissions(subs, has_persuasive_content=True)
    assert perms.endorsement_permission == "deny"


def test_retrieval_manipulation_alone_does_not_downrank_retrieve():
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.6,
        retrieval_manipulation_risk=0.9,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.35,
        concealment_risk=0.0,
    )
    perms = derive_permissions(subs)
    assert perms.retrieve_permission == "allow"


def test_concealment_risk_still_downranks_retrieve():
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.1,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.35,
        concealment_risk=0.6,
    )
    perms = derive_permissions(subs)
    assert perms.retrieve_permission == "downrank"


def test_extreme_concealment_rejects_retrieve():
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.1,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.35,
        concealment_risk=0.95,
    )
    perms = derive_permissions(subs)
    assert perms.retrieve_permission == "reject"
    assert perms.factual_permission == "deny"
    assert perms.endorsement_permission == "deny"
    assert perms.mention_permission == "allow"

def test_listicle_soft_concealment_keeps_retrieve_allow_on_shopping():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.1,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.35,
        concealment_risk=0.6,
    )
    perms = derive_permissions(
        subs,
        content_role="expert_listicle",
        query_intent="commercial",
    )
    assert perms.retrieve_permission == "allow"
    assert perms.endorsement_permission == "allow"


def test_clean_vendor_retrieve_allow_but_endorse_deny():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="commercial_product",
        query_intent="commercial",
    )
    assert perms.retrieve_permission == "allow"
    assert perms.endorsement_permission == "deny"


def test_shady_vendor_retrieve_downrank():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.40,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.5,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="commercial_product",
        query_intent="commercial",
    )
    assert perms.retrieve_permission == "downrank"
    assert perms.endorsement_permission == "deny"
    assert perms.factual_permission == "attribute_only"


def test_ugc_hub_soft_fetch_not_defer_or_factual_deny():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.15,
        source_trust=0.55,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.5,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="ugc_thread",
        query_intent="informational",
        fetch_failure_kind=None,
    )
    assert perms.retrieve_permission != "defer"
    assert perms.factual_permission == "attribute_only"
    assert perms.mention_permission == "allow"


def test_institutional_soft_fetch_floor():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.15,
        source_trust=0.80,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.7,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="institutional",
        query_intent="informational",
        fetch_failure_kind=None,
    )
    assert perms.retrieve_permission != "defer"
    assert perms.factual_permission == "attribute_only"
    assert perms.mention_permission == "allow"


def test_high_trust_factual_blog_soft_fetch_floor():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.15,
        source_trust=0.60,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.6,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="factual_blog",
        query_intent="informational",
        fetch_failure_kind=None,
    )
    assert perms.retrieve_permission != "defer"
    assert perms.factual_permission == "attribute_only"


def test_low_trust_factual_blog_soft_fetch_still_defers():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.15,
        source_trust=0.40,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.5,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="factual_blog",
        query_intent="informational",
        fetch_failure_kind=None,
    )
    assert perms.retrieve_permission == "defer"
    assert perms.factual_permission == "deny"


def test_shopping_listicle_concealment_reject_downranks_without_promo():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.1,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.35,
        concealment_risk=0.95,
    )
    perms = derive_permissions(
        subs,
        content_role="expert_listicle",
        query_intent="commercial",
        concealment_flags=["hidden_instruction_pattern"],
    )
    assert perms.retrieve_permission == "downrank"
    # Reject softening does not clear endorse/factual attack cascade for reject;
    # downrank path keeps ordinary endorse/factual derivation.
    assert perms.mention_permission == "allow"


def test_shopping_listicle_concealment_reject_keeps_reject_with_promo():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.1,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.35,
        concealment_risk=0.95,
    )
    perms = derive_permissions(
        subs,
        content_role="expert_listicle",
        query_intent="commercial",
        concealment_flags=[
            "hidden_instruction_pattern",
            "promotional_instruction_pattern",
        ],
    )
    assert perms.retrieve_permission == "reject"
    assert perms.factual_permission == "deny"
    assert perms.endorsement_permission == "deny"


def test_shopping_listicle_concealment_reject_keeps_reject_with_intent():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.1,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.6,
        harm_severity=0.35,
        concealment_risk=0.95,
    )
    perms = derive_permissions(
        subs,
        content_role="review_profile",
        query_intent="commercial",
        concealment_flags=["hidden_instruction_pattern"],
    )
    assert perms.retrieve_permission == "reject"


def test_non_shopping_concealment_still_rejects():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.1,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.35,
        concealment_risk=0.95,
    )
    perms = derive_permissions(
        subs,
        content_role="expert_listicle",
        query_intent="informational",
        concealment_flags=["hidden_instruction_pattern"],
    )
    assert perms.retrieve_permission == "reject"


def test_ugc_hub_very_low_fetch_confidence_still_mentions():
    """Successful UGC hub fetch: mention stays allow below MENTION_DENY bar."""
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.05,
        source_trust=0.55,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.5,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="ugc_thread",
        query_intent="commercial",
        fetch_failure_kind=None,
    )
    assert perms.mention_permission == "allow"
    assert perms.retrieve_permission != "defer"
    # Soft-fetch caps at attribute_only; shopping UGC floor stays attribute_only.
    assert perms.factual_permission == "attribute_only"


def test_brand_legit_vendor_retrieve_downrank_and_factual_floor():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="commercial_product",
        query_intent="commercial",
        query="is TheoGrace a good brand?",
    )
    assert perms.retrieve_permission == "downrank"
    assert perms.factual_permission == "deny"
    assert perms.endorsement_permission == "deny"


def test_shopping_ugc_factual_floor_attribute_only():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.55,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.55,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="ugc_thread",
        query_intent="commercial",
    )
    assert perms.factual_permission == "attribute_only"
    assert perms.retrieve_permission == "allow"


def test_shopping_high_trust_review_quote_caps_to_attribute_only():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    for role in ("review_profile", "expert_listicle"):
        perms = derive_permissions(
            subs,
            content_role=role,
            query_intent="commercial",
        )
        assert perms.factual_permission == "attribute_only", role
        assert perms.retrieve_permission == "allow"


def test_shopping_institutional_high_trust_still_allows_factual():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.80,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.70,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="institutional",
        query_intent="commercial",
    )
    assert perms.factual_permission == "allow"


def test_factual_blog_not_auto_endorse_deny_on_shopping():
    from anti_geo.permissions import derive_permissions
    from anti_geo.models import SourceSubscores
    subs = SourceSubscores(
        fetch_confidence=0.9,
        source_trust=0.70,
        rhetorical_manipulation=0.0,
        retrieval_manipulation_risk=0.0,
        endorsement_risk=0.0,
        factual_claim_reliability=0.65,
        intent_mismatch=0.0,
        harm_severity=0.2,
        concealment_risk=0.0,
    )
    perms = derive_permissions(
        subs,
        content_role="factual_blog",
        query_intent="commercial",
    )
    assert perms.endorsement_permission == "allow"
