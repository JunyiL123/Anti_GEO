from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from anti_geo.models import FetchResult, PageSegment
from anti_geo.page_context import AFFILIATE_LINK_PARAM_RE
from anti_geo.platform_role import classify_content_role, registrable_domain

_URL_RE = re.compile(r"https?://[^\s\])>\"']+")


@dataclass
class ReferralEdge:
    source_url: str
    source_role: str
    target_url: str
    target_domain: str
    anchor_text: str
    segment_role: str
    affiliate_flag: bool = False


@dataclass
class LinkGraphReport:
    target_domain: str
    edges: list[ReferralEdge] = field(default_factory=list)
    promotion_concentration: float = 0.0
    convergent_hosts: list[str] = field(default_factory=list)
    entity_convergence: bool = False
    cross_platform_hosts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _normalize_domain(hostname: str) -> str:
    return registrable_domain(hostname.lower().removeprefix("www."))


def _is_external_link(source_url: str, link: str) -> bool:
    src = urlparse(source_url)
    dst = urlparse(link)
    if not dst.netloc:
        return False
    return _normalize_domain(src.netloc) != _normalize_domain(dst.netloc)


def extract_outbound_links(
    html: str,
    source_url: str,
    *,
    segment_role: str = "body",
    source_role: str | None = None,
) -> list[ReferralEdge]:
    """Extract external outbound links from HTML with segment and affiliate context."""
    if not html.strip():
        return []

    from bs4 import BeautifulSoup

    role = source_role or classify_content_role(source_url)
    soup = BeautifulSoup(html, "html.parser")
    edges: list[ReferralEdge] = []
    seen: set[tuple[str, str]] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.startswith("#") or href.startswith("mailto:"):
            continue
        absolute = urljoin(source_url, href)
        if not _is_external_link(source_url, absolute):
            continue
        key = (absolute.rstrip("/").lower(), segment_role)
        if key in seen:
            continue
        seen.add(key)
        anchor_text = anchor.get_text(separator=" ", strip=True)[:200]
        edges.append(
            ReferralEdge(
                source_url=source_url,
                source_role=role,
                target_url=absolute,
                target_domain=_normalize_domain(urlparse(absolute).netloc),
                anchor_text=anchor_text,
                segment_role=segment_role,
                affiliate_flag=bool(AFFILIATE_LINK_PARAM_RE.search(href)),
            )
        )
    return edges


def extract_links_from_text(text: str, source_url: str, *, segment_role: str = "body") -> list[ReferralEdge]:
    """Fallback link extraction from plain text (tests / text-only fetches)."""
    role = classify_content_role(source_url)
    edges: list[ReferralEdge] = []
    seen: set[str] = set()
    for url in _URL_RE.findall(text):
        if not _is_external_link(source_url, url):
            continue
        norm = url.rstrip("/").lower()
        if norm in seen:
            continue
        seen.add(norm)
        edges.append(
            ReferralEdge(
                source_url=source_url,
                source_role=role,
                target_url=url,
                target_domain=_normalize_domain(urlparse(url).netloc),
                anchor_text="",
                segment_role=segment_role,
                affiliate_flag=bool(AFFILIATE_LINK_PARAM_RE.search(url)),
            )
        )
    return edges


def extract_referral_edges(
    source_url: str,
    *,
    html: str | None = None,
    text: str | None = None,
    segments: list[PageSegment] | None = None,
) -> list[ReferralEdge]:
    edges: list[ReferralEdge] = []
    if segments:
        for seg in segments:
            edges.extend(extract_links_from_text(seg.text, source_url, segment_role=seg.role))
    if html:
        edges.extend(extract_outbound_links(html, source_url))
    elif text and not segments:
        edges.extend(extract_links_from_text(text, source_url))

    deduped: list[ReferralEdge] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        key = (edge.target_url.rstrip("/").lower(), edge.segment_role, edge.source_url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)
    return deduped


def extract_referral_edges_from_fetch(fetch: FetchResult, *, html: str | None = None) -> list[ReferralEdge]:
    return extract_referral_edges(
        fetch.final_url or fetch.url,
        html=html,
        text=fetch.text,
        segments=fetch.segments or None,
    )


def promotion_concentration(edges: list[ReferralEdge], target_domain: str) -> float:
    """Share of outbound links that point at target_domain."""
    if not edges:
        return 0.0
    target = _normalize_domain(target_domain)
    hits = sum(1 for edge in edges if edge.target_domain == target)
    return hits / len(edges)


def detect_entity_convergence(
    edges: list[ReferralEdge],
    target_domain: str,
    *,
    min_hosts: int = 3,
) -> tuple[bool, list[str]]:
    """True when unrelated hosts all link to the same target domain."""
    target = _normalize_domain(target_domain)
    hosts: set[str] = set()
    for edge in edges:
        if edge.target_domain != target:
            continue
        hosts.add(_normalize_domain(urlparse(edge.source_url).netloc))
    host_list = sorted(hosts)
    return len(host_list) >= min_hosts, host_list


def build_link_graph(
    edges: list[ReferralEdge],
    target_domain: str,
    *,
    min_hosts: int = 3,
) -> LinkGraphReport:
    converged, hosts = detect_entity_convergence(edges, target_domain, min_hosts=min_hosts)
    concentration = promotion_concentration(edges, target_domain)
    cross_platform = [
        h
        for h in hosts
        if any(
            edge.source_role in ("ugc_thread", "review_profile", "expert_listicle")
            for edge in edges
            if _normalize_domain(urlparse(edge.source_url).netloc) == h
        )
    ]
    notes: list[str] = []
    if converged:
        notes.append(
            f"Entity convergence: {len(hosts)} independent hosts link to {target_domain}."
        )
    if concentration >= 0.5 and edges:
        notes.append(
            f"High promotion concentration ({concentration:.0%}) toward {target_domain}."
        )
    return LinkGraphReport(
        target_domain=_normalize_domain(target_domain),
        edges=edges,
        promotion_concentration=concentration,
        convergent_hosts=hosts,
        entity_convergence=converged,
        cross_platform_hosts=cross_platform,
        notes=notes,
    )


def edges_for_target(edges: list[ReferralEdge], target_domain: str) -> list[ReferralEdge]:
    target = _normalize_domain(target_domain)
    return [edge for edge in edges if edge.target_domain == target]
