from anti_geo.claim_entity import (
    is_junk_entity,
    is_usable_claim_label,
    is_weak_verify_marker,
    resolve_claim_entity,
)
from anti_geo.decisions import extract_shared_claim
from anti_geo.models import (
    ContentSignals,
    DomainSignals,
    PageIdentity,
    SourceScore,
)


def _src(
    url: str,
    text: str,
    *,
    identity: PageIdentity | None = None,
) -> SourceScore:
    return SourceScore(
        url=url,
        fetch_ok=True,
        trust_score=0.7,
        semantic_risk=0.0,
        endorsement_allowed=True,
        domain_signals=DomainSignals(
            hostname="example.com",
            tld=".com",
            is_https=True,
            cert_age_days=100,
            whois_age_days=1000,
            dns_resolves=True,
        ),
        content_signals=ContentSignals(
            word_count=100,
            authority_density=0.0,
            comparative_density=0.0,
            temporal_density=0.0,
            narrative_purposiveness=0.0,
            semantic_risk=0.0,
        ),
        text_excerpt=text,
        identity=identity,
    )


def test_junk_title_case_entities():
    assert is_junk_entity("Information What Dog")
    assert is_junk_entity("What Dog Is Right")
    assert is_junk_entity("Puppy Information")
    assert is_junk_entity("15 Headphones Forums in")
    assert not is_junk_entity("EarFun Air Pro")
    assert not is_junk_entity("SecureVault Pro")


def test_weak_verify_markers():
    assert is_weak_verify_marker("topics")
    assert is_weak_verify_marker("forum")
    assert is_weak_verify_marker("community")
    assert is_weak_verify_marker("2026")
    assert is_junk_entity("2026")
    assert not is_weak_verify_marker("Audio Science Review")
    assert not is_usable_claim_label("topics")
    assert not is_usable_claim_label("2026")


def test_dog_breeds_uses_query_topic_not_title_junk():
    source = _src(
        "https://www.akc.org/expert-advice/puppy-information/what-dog-is-right-for-me/",
        "Puppy Information What Dog Is Right For Me Finding a dog that fits.",
        identity=PageIdentity(
            site_name="American Kennel Club",
            organization="American Kennel Club",
            brand="American Kennel Club",
            product="",
        ),
    )
    entity = resolve_claim_entity(
        [source],
        query="best dog breeds",
        query_intent="commercial",
        content_roles=["factual_blog"],
        use_llm=False,
    )
    assert entity == "best dog breeds"


def test_feedspot_listicle_product_falls_back_to_query():
    source = _src(
        "https://forums.feedspot.com/headphones_forums/",
        "Top 15 Headphones Forums in 2026",
        identity=PageIdentity(
            site_name="FeedSpot",
            organization="Feedspot",
            brand="Feedspot",
            product="15 Headphones Forums in",
        ),
    )
    entity = resolve_claim_entity(
        [source],
        query="best headphones forum",
        query_intent="commercial",
        content_roles=["commercial_product"],
        use_llm=False,
    )
    assert entity == "best headphones forum"


def test_informational_factual_prefers_query_topic():
    source = _src(
        "https://www.theknot.com/content/romantic-ways-to-propose",
        "Romantic ways to propose",
        identity=PageIdentity(
            site_name="The Knot",
            organization="The Knot",
            brand="The Knot",
            product="",
        ),
    )
    entity = resolve_claim_entity(
        [source],
        query="best ways to propose",
        query_intent="informational",
        content_roles=["factual_blog"],
        use_llm=False,
    )
    assert entity == "best ways to propose"


def test_informational_commercial_page_prefers_product():
    source = _src(
        "https://reviews.example.com/is-earfun-worth-it",
        "Is EarFun Air Pro 4 waterproof? Many owners ask.",
        identity=PageIdentity(
            site_name="Reviews Weekly",
            organization="Reviews Weekly",
            brand="EarFun",
            product="EarFun Air Pro 4",
        ),
    )
    entity = resolve_claim_entity(
        [source],
        query="is earfun air pro 4 waterproof",
        query_intent="informational",
        content_roles=["review_profile"],
        use_llm=False,
    )
    assert entity == "EarFun Air Pro 4"


def test_extract_shared_claim_keeps_best_in_query_fallback():
    source = _src(
        "https://example.com/post",
        "Some generic capitalized Words Here that appear once.",
    )
    assert (
        extract_shared_claim(
            [source], query="best budget wireless earbuds", use_llm=False
        )
        == "best budget wireless earbuds"
    )


def test_claim_entity_rubric_tracks_role_sets(monkeypatch):
    """Changing claim_entity role sets must change the LLM hybrid rubric."""
    import anti_geo.claim_entity as claim_entity

    monkeypatch.setattr(
        claim_entity,
        "_COMMERCIAL_ROLES",
        frozenset(
            {"commercial_product", "review_profile", "expert_listicle", "shop_hub"}
        ),
    )
    text = claim_entity.claim_entity_heuristic_rules_rubric()
    assert "shop_hub" in text
    assert "_heuristic_pick" in text
    assert "JUNK" in text
    assert "Navigational intent" in text
    msgs = claim_entity.build_claim_entity_llm_messages(
        query="best widgets",
        query_intent="commercial",
        topic="best widgets",
        brand=None,
        heuristic="best widgets",
        sources=[],
        content_roles=["factual_blog"],
    )
    assert msgs[0]["content"] == text
    assert "heuristic_pick: best widgets" in msgs[1]["content"]
