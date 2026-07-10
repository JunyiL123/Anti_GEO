from anti_geo.contestability import chunk_key
from anti_geo.disclosure import build_disclosure_report
from anti_geo.models import CommercialInfluenceAssessment, GuardResult, SourceScore
from anti_geo.retrieval import ScoredChunk


def test_no_label_on_low_tier():
    chunk = ScoredChunk("c1", "https://x.com", "text", 0.9, 0.5, 0.1, 0.1, 0.8, "pass")
    guard = GuardResult("mention", True, "Q: q\n\nA: answer text here")
    assessments = {
        chunk_key(chunk): CommercialInfluenceAssessment(
            tier="low",
            triggers=["commercial_context_score"],
            disclosure_level="none",
        )
    }
    report = build_disclosure_report([chunk], {}, assessments, guard)
    assert not report.show_label


def test_label_on_high_tier_lead_chunk():
    chunk = ScoredChunk(
        "c1",
        "https://shop.com",
        "The best product for teams in 2026",
        0.9,
        0.4,
        0.5,
        0.6,
        0.5,
        "block_endorsement",
    )
    guard = GuardResult(
        "mention",
        True,
        "Q: best tool\n\nA: The best product for teams in 2026",
    )
    assessments = {
        chunk_key(chunk): CommercialInfluenceAssessment(
            tier="high",
            triggers=["affiliate_disclosure"],
            disclosure_level="label",
            disclosure_text="Commercial ties noted.",
        )
    }
    report = build_disclosure_report([chunk], {}, assessments, guard)
    assert report.show_label
    assert report.disclosures[0].confidence == "high"
