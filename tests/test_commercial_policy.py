from anti_geo.commercial_policy import assess_commercial_influence, tighten_permissions
from anti_geo.content_signals import ContentSignals
from anti_geo.models import DomainSignals, PageContextSignals, SourcePermissions, SourceScore


def _source(tier: str = "high", text: str = "The best tool is Acme Pro.") -> SourceScore:
    return SourceScore(
        url="https://shop.example.com/review",
        fetch_ok=True,
        trust_score=0.4,
        semantic_risk=0.5,
        endorsement_allowed=False,
        domain_signals=DomainSignals(
            hostname="shop.example.com",
            tld=".com",
            is_https=True,
            cert_age_days=100,
            whois_age_days=200,
            dns_resolves=True,
        ),
        content_signals=ContentSignals(
            word_count=20,
            authority_density=0.4,
            comparative_density=0.5,
            temporal_density=0.1,
            narrative_purposiveness=0.4,
            semantic_risk=0.5,
            flags=["comparative_superlatives"],
        ),
        page_context=PageContextSignals(
            cta_density=0.2,
            commercial_context_score=0.6,
            structure_density=0.2,
            list_item_count=2,
            table_count=0,
            has_faq_schema=False,
            flags=["affiliate_disclosure"],
            commercial_tier=tier,
            commercial_triggers=["affiliate_disclosure"],
            has_affiliate_links=True,
        ),
        text_excerpt=text,
    )


def test_high_tier_blocks_endorsement_on_recommendation_query():
    perms = SourcePermissions("allow", "allow", "allow", "allow")
    assessment = assess_commercial_influence(
        _source(),
        "The best tool is Acme Pro. You should buy it.",
        "what is the best project management tool",
        "informational",
        perms,
        defended_rank=1,
    )
    assert assessment.tier == "high"
    assert assessment.endorsement_action == "deny"
    assert assessment.disclosure_level == "label"


def test_shopping_intent_suppresses_disclosure():
    perms = SourcePermissions("allow", "allow", "allow", "allow")
    assessment = assess_commercial_influence(
        _source(),
        "The best tool is Acme Pro.",
        "buy project management software",
        "commercial",
        perms,
    )
    assert assessment.disclosure_level == "none"


def test_tighten_permissions_never_loosens():
    base = SourcePermissions("allow", "allow", "allow", "allow")
    assessment = assess_commercial_influence(
        _source(),
        "The best tool is Acme Pro.",
        "what is the best tool",
        "informational",
        base,
        defended_rank=1,
    )
    tightened = tighten_permissions(base, assessment)
    assert tightened.endorsement_permission == "deny"
    assert tightened.factual_permission in ("attribute_only", "deny")
