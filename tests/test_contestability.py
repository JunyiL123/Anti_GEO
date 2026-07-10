from anti_geo.contestability import build_contestability_report
from anti_geo.models import SourcePermissions
from anti_geo.retrieval import ScoredChunk


def test_contestability_diff_baseline_defended():
    baseline = [
        ScoredChunk("a", "https://spam.com", "spam text", 0.9, 0.2, 0.5, 0.5, 0.9, "downrank"),
        ScoredChunk("b", "https://good.com", "balanced editorial", 0.7, 0.8, 0.1, 0.1, 0.7, "pass"),
    ]
    defended = [
        ScoredChunk("b", "https://good.com", "balanced editorial", 0.7, 0.8, 0.1, 0.1, 0.7, "pass"),
    ]
    from anti_geo.models import VisibilityReport

    baseline_pawc = VisibilityReport(
        {"https://spam.com": 60.0, "https://good.com": 40.0},
        {"spam.com": 60.0, "good.com": 40.0},
        "https://spam.com",
        "spam.com",
        60.0,
        True,
    )
    defended_pawc = VisibilityReport(
        {"https://good.com": 100.0},
        {"good.com": 100.0},
        "https://good.com",
        "good.com",
        100.0,
        False,
    )
    report = build_contestability_report(
        "what is the best tool",
        baseline,
        defended,
        baseline_pawc,
        defended_pawc,
        sources={},
        source_permissions={
            "https://spam.com": SourcePermissions("downrank", "allow", "attribute_only", "deny"),
        },
        commercial_assessments={},
    )
    assert len(report.included) == 1
    assert len(report.excluded_alternatives) == 1
    assert report.excluded_alternatives[0].url == "https://spam.com"
    assert report.alternative_pools_available
