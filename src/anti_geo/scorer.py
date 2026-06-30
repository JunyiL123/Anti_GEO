from __future__ import annotations

from anti_geo.content_signals import extract_content_signals
from anti_geo.domain_signals import extract_domain_signals
from anti_geo.fetch import fetch_page
from anti_geo.models import FetchResult, SourceScore


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def score_source(url: str, fetch: FetchResult | None = None) -> SourceScore:
    """
    Infer trust from observable signals only — no hardcoded per-domain labels.
    """
    fetch = fetch or fetch_page(url)
    domain = extract_domain_signals(url, fetch)
    content = extract_content_signals(fetch.text)

    trust = 0.55
    reasons: list[str] = []

    if not fetch.ok:
        trust -= 0.35
        reasons.append(f"fetch_failed:{fetch.error or fetch.status_code}")

    if fetch.broken_link_ratio > 0.4:
        trust -= 0.15
        reasons.append(f"broken_links_{fetch.broken_link_ratio:.0%}")

    if domain.whois_age_days is not None:
        if domain.whois_age_days < 90:
            trust -= 0.20
            reasons.append(f"domain_age_{domain.whois_age_days}d")
        elif domain.whois_age_days > 365 * 3:
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

    if content.word_count < 80:
        trust -= 0.10
        reasons.append("thin_content")

    if "balanced_hedging" in content.flags:
        trust += 0.08
        reasons.append("editorial_hedging")

    trust = _clamp(trust)
    endorsement_allowed = trust >= 0.62 and fetch.ok and fetch.broken_link_ratio <= 0.5

    return SourceScore(
        url=fetch.final_url or url,
        fetch_ok=fetch.ok,
        trust_score=trust,
        semantic_risk=content.semantic_risk,
        endorsement_allowed=endorsement_allowed,
        domain_signals=domain,
        content_signals=content,
        text_excerpt=fetch.text[:500],
        reasons=reasons,
    )
