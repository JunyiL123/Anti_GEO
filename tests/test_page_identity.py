"""Tests for structured page identity + metadata extraction."""

from anti_geo.investigation import (
    _distinctive_markers,
    extract_page_metadata,
    generate_seed_queries,
)
from anti_geo.models import FetchResult, PageContextSignals, PageIdentity
from anti_geo.page_identity import identity_from_html, strip_listicle_boilerplate


def test_path_date_segments_are_not_products():
    from anti_geo.page_identity import _path_product_candidate, identity_from_html

    url = "https://www.headphonesty.com/2026/03/top-audiophile-forums-found-hidden-bias/"
    assert _path_product_candidate(url) != "2026"
    # Year folders skipped; listicle-prefixed long slug is also skipped.
    assert _path_product_candidate(url) in {"", None} or "2026" not in (
        _path_product_candidate(url) or ""
    )

    # Non-listicle product slug after date folders still recovers the SKU.
    sku_url = "https://www.example.com/2026/03/aula-f75-wireless-keyboard/"
    assert _path_product_candidate(sku_url).lower() == "aula f75 wireless keyboard"

    ident = identity_from_html(
        "<html><head><title>Audiophile Forums | Headphonesty</title>"
        '<meta property="og:site_name" content="Headphonesty" /></head><body></body></html>',
        url=url,
        title="Audiophile Forums | Headphonesty",
    )
    assert ident.product != "2026"
    assert "2026" not in {a.lower() for a in ident.aliases}

    fetch = FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        ok=True,
        error=None,
        title="Audiophile Forums | Headphonesty",
        text="Forums discussion.",
        link_count=2,
        broken_link_ratio=0.0,
        redirect_count=0,
        response_time_ms=10,
        has_privacy_page=False,
        has_contact_page=False,
        identity=ident,
    )
    meta = extract_page_metadata(fetch)
    assert "2026" not in {a.lower() for a in meta.aliases}
    markers = _distinctive_markers(
        fetch.url, meta.entity, meta.org, aliases=meta.aliases
    )
    assert "2026" not in markers
    from anti_geo.investigation import _verify_connection

    conn = _verify_connection(
        "Updated March 2026 on many sites.",
        "Updated March 2026 on many sites.",
        fetch.url,
        meta.entity,
        org=meta.org,
        aliases=meta.aliases,
    )
    assert conn is None or conn.marker != "2026"


def test_strip_listicle_boilerplate():
    assert "Cheap Laptops" in strip_listicle_boilerplate(
        "The Best Cheap Laptops We've Tested for 2026"
    )
    assert "best" not in strip_listicle_boilerplate(
        "The Best Cheap Laptops We've Tested for 2026"
    ).lower()


def test_identity_from_jsonld_and_og():
    html = """
    <html><head>
      <title>AULA F75 Wireless Keyboard | RedditRecs</title>
      <meta property="og:site_name" content="RedditRecs" />
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "AULA F75",
        "brand": {"@type": "Brand", "name": "AULA"}
      }
      </script>
    </head><body></body></html>
    """
    ident = identity_from_html(
        html,
        url="https://redditrecs.com/gaming-keyboard/model/aula-f75/",
        title="AULA F75 Wireless Keyboard | RedditRecs",
    )
    assert ident.product == "AULA F75"
    assert ident.brand == "AULA"
    assert ident.site_name == "RedditRecs"
    assert any(a.lower() == "aula f75" for a in ident.aliases)


def test_extract_metadata_prefers_structured_identity():
    html = """
    <html><head>
      <title>WH-CH720N Wireless Headphones | Sony</title>
      <meta property="og:site_name" content="Sony" />
      <script type="application/ld+json">
      {
        "@type": "Product",
        "name": "WH-CH720N",
        "brand": {"@type": "Brand", "name": "Sony"}
      }
      </script>
    </head><body>Sony headphones product page.</body></html>
    """
    from anti_geo.page_identity import identity_from_html

    identity = identity_from_html(
        html,
        url="https://electronics.sony.com/audio/headphones/headband/p/whch720n-b",
        title="WH-CH720N Wireless Headphones | Sony",
    )
    fetch = FetchResult(
        url="https://electronics.sony.com/audio/headphones/headband/p/whch720n-b",
        final_url="https://electronics.sony.com/audio/headphones/headband/p/whch720n-b",
        status_code=200,
        ok=True,
        error=None,
        title="WH-CH720N Wireless Headphones | Sony",
        text="Sony headphones product page.",
        link_count=5,
        broken_link_ratio=0.0,
        redirect_count=0,
        response_time_ms=10,
        has_privacy_page=False,
        has_contact_page=False,
        page_context=PageContextSignals(
            cta_density=0.2,
            commercial_context_score=0.6,
            structure_density=0.3,
            list_item_count=2,
            table_count=0,
            has_faq_schema=False,
            commercial_tier="low",
        ),
        identity=identity,
    )
    meta = extract_page_metadata(fetch)
    assert meta.entity == "WH-CH720N"
    assert meta.org.lower() in {"sony", "sony corporation"} or "sony" in meta.org.lower()
    assert "wh-ch720n" in {a.lower() for a in meta.aliases} or "whch720n" in {
        a.lower().replace("-", "") for a in meta.aliases
    }
    markers = _distinctive_markers(
        fetch.url, meta.entity, meta.org, aliases=meta.aliases
    )
    assert any("wh" in m and "720" in m for m in markers)
    assert "sony" in markers


def test_editorial_metadata_uses_publisher_not_first_title_token():
    fetch = FetchResult(
        url="https://www.pcmag.com/picks/the-best-budget-laptops",
        final_url="https://www.pcmag.com/picks/the-best-budget-laptops",
        status_code=200,
        ok=True,
        error=None,
        title="The Best Cheap Laptops We've Tested for 2026 | PCMag",
        text="PCMag editors select and review products independently.",
        link_count=20,
        broken_link_ratio=0.05,
        redirect_count=0,
        response_time_ms=200,
        has_privacy_page=True,
        has_contact_page=True,
        page_context=PageContextSignals(
            cta_density=0.1,
            commercial_context_score=0.2,
            structure_density=0.5,
            list_item_count=10,
            table_count=1,
            has_faq_schema=True,
            flags=["affiliate_disclosure"],
            commercial_tier="medium",
        ),
        identity=PageIdentity(site_name="PCMag", organization="PCMag", brand="PCMag"),
    )
    meta = extract_page_metadata(fetch)
    assert meta.org.lower() == "pcmag"
    # Entity should not be the leading "The" from the raw title.
    assert meta.entity.lower() != "the"
    seeds = generate_seed_queries("editorial", meta)
    assert any("best" in s.lower() for s in seeds)
