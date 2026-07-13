from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from anti_geo.audit.engines import EngineAdapter, get_engine
from anti_geo.decisions import decide_single_source
from anti_geo.fetch import fetch_page
from anti_geo.models import FetchResult, SourceScore, UrlAnalysisReport
from anti_geo.permissions import derive_llm_actions
from anti_geo.platform_role import classify_content_role, registrable_domain
from anti_geo.scorer import score_source

PRODUCT_SEED_TEMPLATES = (
    "best {category} 2026",
    "best {category} under {price}",
    "{entity} review",
    "{entity} vs",
    "is {entity} worth it",
    "top {category} recommendations",
    "best budget {category}",
    "{category} buying guide",
)

INFORMATIONAL_SEED_TEMPLATES = (
    "what is {topic}",
    "{topic} explained",
    "how does {topic} work",
    "{topic} guide",
    "evidence for {topic}",
)

EDITORIAL_SEED_TEMPLATES = (
    "best {category} 2026",
    "best {category} tested",
    "{category} buying guide",
    "top {category} picks",
)

INSTITUTIONAL_SEED_TEMPLATES = (
    "{org} {topic}",
    "official guidance on {topic}",
    "{topic} {org}",
)


@dataclass
class PageMetadata:
    entity: str
    category: str
    topic: str
    price_hint: str
    org: str


@dataclass
class VerifiedReferrer:
    url: str
    role: str
    connection: str  # url_link | entity_mention
    seed_query: str = ""


@dataclass
class SemanticAlignment:
    target_commercial_tier: str
    referrer_commercial_share: float
    aligned: bool
    label: str  # aligned | mismatch | coordinated_commercial | inconclusive


@dataclass
class ReferralProfile:
    status: str  # skipped | inconclusive | sparse | sparse_suspicious | complete
    discovery_status: str  # skipped | success | partial | failed
    confidence: str  # low | medium | high
    n_verified: int = 0
    mix: dict[str, int] = field(default_factory=dict)
    citations_domain_mix: dict[str, int] = field(default_factory=dict)
    geo_suspected: bool | None = None
    citations_sampled: int = 0
    seed_queries_run: int = 0
    target_cited_in_answers: int = 0
    semantic_alignment: SemanticAlignment | None = None
    referrers_verified: list[VerifiedReferrer] = field(default_factory=list)
    discovery_errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class InvestigationResult:
    target_url: str
    content_role: str
    seed_confidence: str
    seed_queries: list[str]
    single_page: UrlAnalysisReport
    llm_action: str
    llm_actions: list[str]
    referral_profile: ReferralProfile
    verdict: str
    metadata: PageMetadata


def _clean_title(title: str) -> str:
    base = re.split(r"\s*[|\-–—]\s*", title)[0].strip()
    return base[:120] if base else ""


def _category_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.lower()
    for part in path.split("/"):
        if part.startswith("best-") or part.startswith("the-best-"):
            return part.replace("-", " ").replace("the ", "").strip()
    qs = parsed.query.lower()
    for key in ("keywords", "q", "search"):
        match = re.search(rf"{key}=([^&]+)", qs)
        if match:
            words = match.group(1).replace("+", " ").split()
            if words:
                return " ".join(words[:4])
    return "product"


def _price_hint_from_text(text: str, url: str) -> str:
    blob = f"{text[:500]} {url}".lower()
    for pattern in (r"under\s+\$?\s*(\d+)", r"under\s+(\d+)\s*dollars", r"\$(\d+)\s*or\s*less"):
        match = re.search(pattern, blob)
        if match:
            return match.group(1)
    return "1000"


def extract_page_metadata(fetch: FetchResult) -> PageMetadata:
    title = _clean_title(fetch.title or "")
    entity = title or registrable_domain(urlparse(fetch.final_url or fetch.url).netloc)
    category = _category_from_url(fetch.final_url or fetch.url)
    topic = title or category
    org = title.split()[0] if title else registrable_domain(urlparse(fetch.url).netloc)
    price = _price_hint_from_text(fetch.text or "", fetch.url)
    return PageMetadata(
        entity=entity,
        category=category,
        topic=topic,
        price_hint=price,
        org=org,
    )


def seed_confidence_for_role(role: str) -> str:
    if role in ("commercial_product", "editorial"):
        return "high"
    if role in ("institutional", "factual_blog"):
        return "medium"
    return "low"


def _normalize_category(category: str) -> str:
    c = category.strip()
    if c.lower().startswith("best "):
        return c[5:].strip()
    return c


def generate_seed_queries(role: str, meta: PageMetadata, *, limit: int = 12) -> list[str]:
    category = _normalize_category(meta.category)
    ctx = {
        "entity": meta.entity,
        "category": category,
        "topic": meta.topic,
        "price": meta.price_hint,
        "org": meta.org,
    }
    if role == "commercial_product":
        templates = PRODUCT_SEED_TEMPLATES
    elif role == "editorial":
        templates = EDITORIAL_SEED_TEMPLATES
    elif role == "institutional":
        templates = INSTITUTIONAL_SEED_TEMPLATES
    else:
        templates = INFORMATIONAL_SEED_TEMPLATES

    queries: list[str] = []
    for tpl in templates:
        try:
            q = tpl.format(**ctx).strip()
        except KeyError:
            continue
        if q and q not in queries:
            queries.append(q)
        if len(queries) >= limit:
            break
    return queries


def _target_connection_markers(target_url: str, entity: str) -> list[str]:
    parsed = urlparse(target_url)
    path = parsed.path.strip("/")
    slug = path.split("/")[-1] if path else ""
    slug_words = slug.replace("-", " ").strip()
    markers = [
        target_url.lower(),
        f"{parsed.netloc.lower()}{parsed.path}".lower(),
        f"{registrable_domain(parsed.netloc)}{parsed.path}".lower(),
    ]
    if slug:
        markers.append(slug.lower())
    if slug_words and len(slug_words) >= 8:
        markers.append(slug_words.lower())
    if entity:
        markers.append(entity.lower())
        # Shorter product-like tokens from title (e.g. "MacBook Neo" from long headline)
        for chunk in re.split(r"[\|\-–—:]", entity):
            chunk = chunk.strip()
            if 4 <= len(chunk) <= 60:
                markers.append(chunk.lower())
    return list(dict.fromkeys(m for m in markers if m))


def _target_cited_in_response(cited_urls: list[str], target_url: str) -> bool:
    target_norm = target_url.rstrip("/").lower()
    target_path = urlparse(target_url).path.rstrip("/").lower()
    for url in cited_urls:
        u = url.rstrip("/").lower()
        if u == target_norm:
            return True
        if target_path and target_path in urlparse(url).path.lower():
            return True
    return False


def _citation_domain_mix(citations: set[str]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for url in citations:
        role = classify_content_role(url)
        mix[role] = mix.get(role, 0) + 1
    return mix


def _commercial_roles() -> frozenset[str]:
    return frozenset({"commercial_product", "review_profile", "expert_listicle"})


def assess_semantic_alignment(
    target_role: str,
    verified: list[VerifiedReferrer],
    *,
    target_commercial_tier: str = "none",
) -> SemanticAlignment:
    """Lightweight alignment check: target page tier vs verified referrer roles."""
    if not verified:
        return SemanticAlignment(
            target_commercial_tier=target_commercial_tier,
            referrer_commercial_share=0.0,
            aligned=True,
            label="inconclusive",
        )

    commercial = _commercial_roles()
    n = len(verified)
    commercial_n = sum(1 for r in verified if r.role in commercial)
    share = commercial_n / n

    target_is_commercial = target_role in commercial or target_commercial_tier in (
        "low",
        "medium",
        "high",
    )
    target_is_editorial = target_role in ("editorial", "institutional", "factual_blog")

    if target_is_editorial and share >= 0.7 and commercial_n >= 2:
        return SemanticAlignment(
            target_commercial_tier=target_commercial_tier,
            referrer_commercial_share=share,
            aligned=False,
            label="coordinated_commercial",
        )
    if target_is_commercial and share < 0.3 and n >= 3:
        return SemanticAlignment(
            target_commercial_tier=target_commercial_tier,
            referrer_commercial_share=share,
            aligned=False,
            label="mismatch",
        )
    return SemanticAlignment(
        target_commercial_tier=target_commercial_tier,
        referrer_commercial_share=share,
        aligned=True,
        label="aligned",
    )


def _verify_connection(
    html: str,
    text: str,
    target_url: str,
    entity: str,
) -> str | None:
    blob = (html + " " + text).lower()
    parsed = urlparse(target_url)
    target_domain = registrable_domain(parsed.netloc)
    if target_domain in blob and parsed.path.lower().strip("/") in blob:
        return "url_link"
    for marker in _target_connection_markers(target_url, entity):
        if len(marker) >= 8 and marker in blob:
            return "url_link" if "/" in marker or ".com" in marker else "entity_mention"
    if entity and len(entity) >= 5:
        ent = entity.lower()
        if ent in blob:
            return "entity_mention"
    return None


def _role_for_url(url: str) -> str:
    return classify_content_role(url)


def _is_same_brand(referrer_url: str, target_url: str) -> bool:
    r = registrable_domain(urlparse(referrer_url).netloc)
    t = registrable_domain(urlparse(target_url).netloc)
    return r == t


def discover_referrers(
    target_url: str,
    entity: str,
    seed_queries: list[str],
    engine: EngineAdapter | None,
    *,
    max_fetches: int = 40,
    query_delay_s: float = 0.0,
    target_role: str = "unknown",
    target_commercial_tier: str = "none",
) -> ReferralProfile:
    if engine is None:
        return ReferralProfile(
            status="skipped",
            discovery_status="skipped",
            confidence="low",
            notes=["Referral discovery skipped (no engine). L1-L3 verdict only."],
        )

    errors: list[str] = []
    citations: set[str] = set()
    citation_sources: dict[str, str] = {}
    queries_run = 0
    target_cited = 0

    for i, q in enumerate(seed_queries):
        if i > 0 and query_delay_s > 0:
            time.sleep(query_delay_s)
        try:
            resp = engine.query(q)
            queries_run += 1
            if _target_cited_in_response(resp.cited_urls, target_url):
                target_cited += 1
            for url in resp.cited_urls:
                citations.add(url)
                citation_sources.setdefault(url, q)
        except Exception as exc:
            errors.append(f"engine query failed ({q[:40]}...): {exc}")

    domain_mix = _citation_domain_mix(citations)

    if not citations and errors:
        return ReferralProfile(
            status="inconclusive",
            discovery_status="failed",
            confidence="low",
            citations_sampled=0,
            seed_queries_run=queries_run,
            citations_domain_mix=domain_mix,
            discovery_errors=errors,
            notes=["Discovery failed; do not treat as zero referrers."],
        )

    verified: list[VerifiedReferrer] = []
    seen_urls: set[str] = set()
    fetches = 0
    for cited in sorted(citations):
        cited_norm = cited.rstrip("/").lower()
        if cited_norm == target_url.rstrip("/").lower():
            continue
        if _is_same_brand(cited, target_url):
            continue
        if fetches >= max_fetches:
            errors.append(f"fetch budget exhausted ({max_fetches})")
            break
        try:
            fr = fetch_page(cited, timeout=12.0)
            fetches += 1
            if not fr.ok:
                continue
            final = (fr.final_url or cited).rstrip("/")
            if final.lower() in seen_urls:
                continue
            conn = _verify_connection(fr.text, fr.text, target_url, entity)
            if conn:
                seen_urls.add(final.lower())
                verified.append(
                    VerifiedReferrer(
                        url=fr.final_url or cited,
                        role=_role_for_url(fr.final_url or cited),
                        connection=conn,
                        seed_query=citation_sources.get(cited, ""),
                    )
                )
        except Exception as exc:
            errors.append(f"fetch failed ({cited}): {exc}")

    mix: dict[str, int] = {}
    for ref in verified:
        mix[ref.role] = mix.get(ref.role, 0) + 1

    n = len(verified)
    discovery_status = "success" if not errors else ("partial" if n or citations else "failed")
    alignment = assess_semantic_alignment(
        target_role,
        verified,
        target_commercial_tier=target_commercial_tier,
    )

    notes: list[str] = []
    if target_cited > 0:
        notes.append(
            f"Target cited in {target_cited}/{queries_run} seed answers "
            "(AI-visible footprint, not a verified referrer)."
        )
    if alignment.label == "coordinated_commercial":
        notes.append(
            "Verified referrers skew commercial while target is editorial — "
            "possible coordinated promotion pattern."
        )
    elif alignment.label == "mismatch":
        notes.append(
            "Verified referrers skew non-commercial while target is product/commercial."
        )

    if n == 0 and errors:
        return ReferralProfile(
            status="inconclusive",
            discovery_status=discovery_status,
            confidence="low",
            citations_sampled=len(citations),
            seed_queries_run=queries_run,
            target_cited_in_answers=target_cited,
            citations_domain_mix=domain_mix,
            semantic_alignment=alignment,
            discovery_errors=errors,
            notes=notes or ["No verified referrers; discovery may be incomplete."],
        )

    if n == 0:
        return ReferralProfile(
            status="sparse",
            discovery_status="success",
            confidence="medium",
            citations_sampled=len(citations),
            seed_queries_run=queries_run,
            target_cited_in_answers=target_cited,
            citations_domain_mix=domain_mix,
            semantic_alignment=alignment,
            n_verified=0,
            mix={},
            geo_suspected=False,
            notes=notes
            or ["No verified referrers after checking citations. Parasitic GEO footprint unlikely."],
        )

    ugc = mix.get("ugc_thread", 0)
    editorial = mix.get("editorial", 0) + mix.get("institutional", 0)
    ugc_share = ugc / n if n else 0.0

    status = "sparse"
    confidence = "low"
    geo_suspected: bool | None = False

    if n >= 20:
        status = "complete"
        confidence = "medium"
        if ugc_share > 0.6 and editorial == 0:
            geo_suspected = True
            notes.append("UGC-heavy verified referrer mix with no editorial/institutional share.")
        elif editorial > 0:
            notes.append("Editorial/institutional referrers present — organic buzz likely for large brands.")
    elif n < 10:
        status = "sparse"
        confidence = "low"
        if ugc_share >= 0.8 and n >= 3:
            status = "sparse_suspicious"
            notes.append("Small N but homogeneous UGC — qualitative suspicion only, not auto-flag.")
        else:
            geo_suspected = False
            notes.append("N below mix threshold; profile judgment deferred to L1-L3.")
    else:
        status = "sparse"
        confidence = "medium"

    if alignment.label == "coordinated_commercial" and geo_suspected is not True:
        geo_suspected = None
        notes.append("Semantic alignment flag — review manually; not auto-convict.")

    return ReferralProfile(
        status=status,
        discovery_status=discovery_status,
        confidence=confidence,
        n_verified=n,
        mix=mix,
        citations_domain_mix=domain_mix,
        geo_suspected=geo_suspected,
        citations_sampled=len(citations),
        seed_queries_run=queries_run,
        target_cited_in_answers=target_cited,
        semantic_alignment=alignment,
        referrers_verified=verified,
        discovery_errors=errors,
        notes=notes,
    )


def _build_verdict(
    llm_action: str,
    profile: ReferralProfile,
    content_role: str,
) -> str:
    if profile.status == "skipped":
        return f"L1-L3 primary ({llm_action}); referral profile skipped."
    if profile.status == "inconclusive":
        return f"L1-L3 primary ({llm_action}); referral profile inconclusive — do not infer clean."
    if profile.geo_suspected:
        return f"GEO suspected (profile + L1-L3); primary action: {llm_action}."
    if profile.status == "sparse_suspicious":
        return f"Sparse UGC-heavy footprint (low confidence); L1-L3 primary ({llm_action})."
    if content_role == "editorial":
        return f"Editorial target — L1-L3 primary ({llm_action}); low external referrer N is expected."
    return f"L1-L3 primary ({llm_action}); referral profile: {profile.status}."


def investigate_url(
    url: str,
    *,
    query_intent: str = "commercial",
    query: str | None = None,
    engine_name: str | None = None,
    seed_limit: int = 12,
    fixture_path: Path | None = None,
    query_delay_s: float = 0.0,
    max_fetches: int = 40,
) -> InvestigationResult:
    """Mode B: URL in → L1-L3 always → optional referral discovery."""
    fetch = fetch_page(url)
    source = score_source(url, fetch, query=query)
    report = decide_single_source(source, query_intent, query=query)
    role = classify_content_role(url, fetch=fetch, source=source)
    meta = extract_page_metadata(fetch)
    seed_conf = seed_confidence_for_role(role)
    seeds = generate_seed_queries(role, meta, limit=seed_limit)

    engine: EngineAdapter | None = None
    if engine_name and engine_name != "none":
        engine = get_engine(engine_name, fixture_path=fixture_path)

    commercial_tier = "none"
    if source.page_context and source.page_context.commercial_tier:
        commercial_tier = source.page_context.commercial_tier

    profile = discover_referrers(
        url,
        meta.entity,
        seeds,
        engine,
        query_delay_s=query_delay_s,
        max_fetches=max_fetches,
        target_role=role,
        target_commercial_tier=commercial_tier,
    )

    primary, actions = derive_llm_actions(
        report.permissions,
        report.subscores,
    ) if report.permissions and report.subscores else (report.recommended_action, [report.recommended_action])

    verdict = _build_verdict(primary, profile, role)

    return InvestigationResult(
        target_url=fetch.final_url or url,
        content_role=role,
        seed_confidence=seed_conf,
        seed_queries=seeds,
        single_page=report,
        llm_action=primary,
        llm_actions=actions,
        referral_profile=profile,
        verdict=verdict,
        metadata=meta,
    )


def investigation_to_dict(result: InvestigationResult) -> dict:
    sp = result.single_page
    payload = {
        "target_url": result.target_url,
        "content_role": result.content_role,
        "seed_confidence": result.seed_confidence,
        "seed_queries": result.seed_queries,
        "metadata": asdict(result.metadata),
        "llm_action": result.llm_action,
        "llm_actions": result.llm_actions,
        "verdict": result.verdict,
        "referral_profile": {
            **asdict(result.referral_profile),
            "referrers_verified": [asdict(r) for r in result.referral_profile.referrers_verified],
            "semantic_alignment": (
                asdict(result.referral_profile.semantic_alignment)
                if result.referral_profile.semantic_alignment
                else None
            ),
        },
        "single_page": {
            "recommended_action": sp.recommended_action,
            "endorsement_risk": sp.endorsement_risk,
            "trust_score": sp.source.trust_score,
            "semantic_risk": sp.source.semantic_risk,
            "retrieval_manipulation_risk": (
                sp.subscores.retrieval_manipulation_risk if sp.subscores else None
            ),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return payload


def format_investigation_report(result: InvestigationResult) -> str:
    sp = result.single_page
    rp = result.referral_profile
    retrieval_line = (
        f"  Retrieval manipulation: {sp.subscores.retrieval_manipulation_risk:.3f}"
        if sp.subscores
        else "  Retrieval manipulation: n/a"
    )
    lines = [
        "=" * 60,
        "ANTI-GEO INVESTIGATION (Mode B)",
        "=" * 60,
        f"Target: {result.target_url}",
        f"Content role: {result.content_role}",
        f"Seed confidence: {result.seed_confidence}",
        f"Entity/topic: {result.metadata.entity}",
        "",
        "── Verdict ──",
        f"  {result.verdict}",
        f"  Primary LLM action: {result.llm_action}",
        f"  All actions: {', '.join(result.llm_actions)}",
        "",
        "── Single-page L1-L2-L3 ──",
        f"  Trust: {sp.source.trust_score:.3f}",
        f"  Semantic risk: {sp.source.semantic_risk:.3f}",
        retrieval_line,
        f"  Endorsement risk: {sp.endorsement_risk:.3f}",
        f"  Legacy action: {sp.recommended_action}",
        "",
        "── Referral profile ──",
        f"  Status: {rp.status}",
        f"  Discovery: {rp.discovery_status}",
        f"  Confidence: {rp.confidence}",
        f"  Citations sampled: {rp.citations_sampled}",
        f"  Seed queries run: {rp.seed_queries_run}",
        f"  Target cited in answers: {rp.target_cited_in_answers}",
        f"  N verified referrers: {rp.n_verified}",
        f"  Citation mix (all): {rp.citations_domain_mix or '{}'}",
        f"  Verified mix: {rp.mix or '{}'}",
        f"  GEO suspected: {rp.geo_suspected}",
    ]
    if rp.semantic_alignment:
        sa = rp.semantic_alignment
        lines.append(
            f"  Semantic alignment: {sa.label} "
            f"(referrer commercial share {sa.referrer_commercial_share:.0%})"
        )
    if rp.notes:
        lines.append(f"  Notes: {'; '.join(rp.notes)}")
    if rp.discovery_errors:
        lines.append(f"  Discovery errors: {len(rp.discovery_errors)}")
    if rp.referrers_verified:
        lines.extend(["", "── Verified referrers ──"])
        for ref in rp.referrers_verified[:15]:
            lines.append(f"  [{ref.role}] {ref.connection}: {ref.url}")
    lines.extend(["", "── Seed queries (for optional audit) ──"])
    for i, q in enumerate(result.seed_queries, 1):
        lines.append(f"  {i}. {q}")
    return "\n".join(lines)
