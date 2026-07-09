from anti_geo.eval import build_proxy_benchmark_cases, evaluate_case, evaluate_proxy_suite


def test_proxy_eval_suite_returns_multiple_results():
    results = evaluate_proxy_suite(methods=["identity", "authoritative_mine"])
    assert len(results) == 24
    assert {r.case_name for r in results} == {
        "pm_tools",
        "high_stakes_health",
        "editorial_listicle",
        "navigational_pricing",
        "institutional_health",
        "docs_reference",
        "press_release_info",
        "review_aggregator",
        "ugc_informational",
        "live_wikipedia_reference",
        "live_zapier_editorial",
        "live_nih_reference",
    }


def test_authoritative_attack_raises_pm_semantic_risk_and_hits_guard():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "pm_tools")
    baseline = evaluate_case(case, "identity")
    attacked = evaluate_case(case, "authoritative_mine")

    assert attacked.source_semantic_risk > baseline.source_semantic_risk
    assert attacked.baseline_share >= baseline.baseline_share
    assert attacked.defended_share <= attacked.baseline_share
    assert attacked.guard_type in {"endorsement", "mention"}
    assert any("block" in action for action in attacked.guard_actions) or attacked.source_action in {
        "downrank",
        "block_endorsement",
    }


def test_high_stakes_stats_attack_triggers_stronger_guard():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "high_stakes_health")
    result = evaluate_case(case, "stats_optimization_gpt")

    assert result.source_semantic_risk > 0.0
    assert result.source_endorsement_risk > 0.0
    assert result.guard_type in {"endorsement", "factual_claim", "false_consensus", "mention"}


def test_false_positive_editorial_identity_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "editorial_listicle")
    result = evaluate_case(case, "identity")

    assert result.suite == "false_positive"
    assert result.source_action == "pass"
    assert result.guard_type == "mention"
    assert "block" not in ",".join(result.guard_actions)


def test_false_positive_navigational_identity_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "navigational_pricing")
    result = evaluate_case(case, "identity")

    assert result.source_action == "pass"
    assert result.source_endorsement_risk == 0.0


def test_false_positive_institutional_identity_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "institutional_health")
    result = evaluate_case(case, "identity")

    assert result.source_action == "pass"
    assert result.source_trust >= 0.55


def test_false_positive_docs_identity_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "docs_reference")
    result = evaluate_case(case, "identity")

    assert result.source_action == "pass"
    assert result.source_endorsement_risk == 0.0


def test_false_positive_press_release_info_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "press_release_info")
    result = evaluate_case(case, "identity")

    assert result.source_action == "pass"
    assert result.guard_type == "mention"


def test_false_positive_review_aggregator_identity_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "review_aggregator")
    result = evaluate_case(case, "identity")

    assert result.source_action == "pass"
    assert "block" not in ",".join(result.guard_actions)


def test_false_positive_ugc_identity_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "ugc_informational")
    result = evaluate_case(case, "identity")

    assert result.source_action == "pass"
    assert result.guard_type == "mention"


def test_live_wikipedia_identity_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "live_wikipedia_reference")
    result = evaluate_case(case, "identity")

    assert result.source_action == "pass"
    assert result.source_semantic_risk < 0.2


def test_live_zapier_identity_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "live_zapier_editorial")
    result = evaluate_case(case, "identity")

    assert result.source_action == "pass"
    assert "block" not in ",".join(result.guard_actions)


def test_live_nih_identity_stays_allowed():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "live_nih_reference")
    result = evaluate_case(case, "identity")

    assert result.source_action == "pass"
    assert result.guard_type in {"mention", "factual_claim"}
    assert result.factual_permission in {"allow", "attribute_only", "require_corroboration"}
    assert result.endorsement_permission in {"allow", "deny"}


def test_eval_tracks_permission_fields_separately():
    case = next(c for c in build_proxy_benchmark_cases() if c.name == "pm_tools")
    attacked = evaluate_case(case, "authoritative_mine")
    assert attacked.retrieve_permission in {"allow", "downrank", "defer", "reject"}
    assert attacked.factual_permission in {"allow", "attribute_only", "require_corroboration", "deny"}
    assert attacked.endorsement_permission in {"allow", "deny"}
    assert attacked.guard_response_mode
    assert attacked.source_action in {"pass", "downrank", "block_endorsement", "defer_fetch", "reject"}
