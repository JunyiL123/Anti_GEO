from anti_geo.models import SourcePermissions, SourceSubscores
from anti_geo.permissions import derive_llm_actions, merge_llm_actions


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
