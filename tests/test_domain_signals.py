from anti_geo.domain_signals import (
    _apex_hostname,
    _parse_whois_creation_days,
    _should_flag_deep_subdomain,
)

IANA_ORG_SNIPPET = """
domain:       ORG
created:      1985-01-01
source:       IANA
"""

REGISTRAR_SNIPPET = """
Domain Name: cualignment.org
Creation Date: 2025-01-17T17:22:43Z
Registrar: Cloudflare, Inc.
"""


def test_apex_hostname_strips_www():
    assert _apex_hostname("www.cualignment.org") == "cualignment.org"
    assert _apex_hostname("cualignment.org") == "cualignment.org"


def test_whois_parser_prefers_registrar_creation_date_over_iana_tld():
    output = IANA_ORG_SNIPPET + REGISTRAR_SNIPPET
    age = _parse_whois_creation_days("www.cualignment.org", output)
    assert age is not None
    assert age < 600
    assert age > 300


def test_whois_parser_ignores_iana_only_response():
    age = _parse_whois_creation_days("www.example.org", IANA_ORG_SNIPPET)
    assert age is None


def test_gov_edu_hosts_skip_deep_subdomain_flag():
    assert not _should_flag_deep_subdomain("www.ncbi.nlm.nih.gov")
    assert not _should_flag_deep_subdomain("clinicaltrials.gov")
    assert not _should_flag_deep_subdomain("www.med.harvard.edu")
    assert _should_flag_deep_subdomain("a.b.c.example.com")
    assert not _should_flag_deep_subdomain("www.example.com")
