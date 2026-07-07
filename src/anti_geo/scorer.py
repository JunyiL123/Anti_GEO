from __future__ import annotations

from anti_geo.config import DEFAULT_CONFIG, DefenseConfig
from anti_geo.content_signals import extract_content_signals
from anti_geo.domain_signals import extract_domain_signals
from anti_geo.fetch import fetch_page
from anti_geo.models import FetchResult, SourceScore


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def score_source(
    url: str,
    fetch: FetchResult | None = None,
    query: str | None = None,
    config: DefenseConfig = DEFAULT_CONFIG,
) -> SourceScore:
    """Infer trust from observable signals only — no hardcoded per-domain labels."""
    fetch = fetch or fetch_page(url)
    domain = extract_domain_signals(url, fetch)
    content = extract_content_signals(fetch.text, query, config)

    trust = 0.55
    reasons: list[str] = []

    if not fetch.ok:
        trust -= 0.35
        reasons.append(f"fetch_failed:{fetch.error or fetch.status_code}")

    if fetch.broken_link_ratio > config.broken_link_penalty_ratio:
        trust -= 0.15
        reasons.append(f"broken_links_{fetch.broken_link_ratio:.0%}")

    if not domain.dns_resolves and not fetch.ok:
        trust -= 0.20
        reasons.append("dns_failure")

    if any("suspicious_tld" in s for s in domain.signals):
        trust -= 0.08
        reasons.append("suspicious_tld")

    if any(s.startswith("excess_redirects") for s in domain.signals):
        trust -= 0.06
        reasons.append("excess_redirects")

    if "deep_subdomain" in domain.signals:
        trust -= 0.05
        reasons.append("deep_subdomain")

    if domain.whois_age_days is not None:
        if domain.whois_age_days < config.domain_age_young_days:
            trust -= 0.20
            reasons.append(f"domain_age_{domain.whois_age_days}d")
        elif domain.whois_age_days > config.domain_age_established_days:
            trust += 0.10
            reasons.append("established_domain")
    elif domain.cert_age_days is not None and domain.cert_age_days < 60:
        trust -= 0.08
        reasons.append(f"recent_cert_{domain.cert_age_days}d")

    if not domain.is_https:
        trust -= 0.12
        reasons.append("no_https")

    if fetch.has_privacy_page:
        trust += 0.03
    if fetch.has_contact_page:
        trust += 0.03

    if content.word_count < config.thin_content_words:
        trust -= 0.10
        reasons.append("thin_content")

    if "balanced_hedging" in content.flags:
        trust += 0.08
        reasons.append("editorial_hedging")

    if fetch.page_context and fetch.page_context.commercial_context_score > 0.5:
        trust -= 0.04
        reasons.append("commercial_page_context")

    trust = _clamp(trust)
    endorsement_allowed = (
        trust >= config.trust_endorsement_min
        and fetch.ok
        and fetch.broken_link_ratio <= config.broken_link_block_ratio
        and domain.dns_resolves
    )

    return SourceScore(
        url=fetch.final_url or url,
        fetch_ok=fetch.ok,
        trust_score=trust,
        semantic_risk=content.semantic_risk,
        endorsement_allowed=endorsement_allowed,
        domain_signals=domain,
        content_signals=content,
        page_context=fetch.page_context,
        text_excerpt=fetch.text[:500],
        reasons=reasons,
        fetch_engine=fetch.fetch_engine,
    )
