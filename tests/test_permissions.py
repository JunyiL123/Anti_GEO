from anti_geo.config import DEFAULT_CONFIG
from anti_geo.models import QueryContextScores, SourcePermissions, SourceSubscores
from anti_geo.permissions import (
    _derive_endorsement_permission,
    derive_llm_actions,
    derive_permissions,
    merge_llm_actions,
)


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
