from __future__ import annotations

import random
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
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
from anti_geo.progress import NullProgress, Progress
from anti_geo.scorer import score_source
from anti_geo.seed_generation import resolve_seed_queries

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


@dataclass(frozen=True)
class ReferrerConnection:
    """Deterministic referrer tie — no LLM required for tiering."""

    kind: str  # url_link | brand_mention
    confidence: str  # high | weak
    marker: str = ""


@dataclass
class VerifiedReferrer:
    url: str
    role: str
    connection: str  # url_link | brand_mention
    connection_confidence: str = "high"  # high | weak
    matched_marker: str = ""
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
    seed_source: str  # llm | template
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


_ORG_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "for",
        "our",
        "your",
        "best",
        "top",
        "new",
        "www",
    }
)

_GENERIC_TOPIC_PATTERNS = (
    re.compile(r"^the\s+best\s+", re.I),
    re.compile(r"^best\s+", re.I),
    re.compile(r"^top\s+", re.I),
    re.compile(r"^cheap(est)?\s+", re.I),
    re.compile(r"^budget\s+", re.I),
    re.compile(r"\bbuying guide\b", re.I),
    re.compile(r"\bpicks?\b", re.I),
    re.compile(r"we'?ve tested", re.I),
    re.compile(r"\bfor\s+20\d{2}\b", re.I),
    re.compile(r"\breview(ed|s)?\b", re.I),
    re.compile(r"\bcomparison(s)?\b", re.I),
    re.compile(r"\bvs\.?\b", re.I),
)


def _is_generic_topic_marker(marker: str) -> bool:
    """True for listicle slugs and headline boilerplate — not target-specific ties."""
    text = " ".join(marker.strip().lower().split())
    if not text:
        return True
    return any(pattern.search(text) for pattern in _GENERIC_TOPIC_PATTERNS)


def _distinctive_markers(target_url: str, entity: str, org: str) -> list[str]:
    """Publisher, org, or product tokens that identify the target — not generic topics."""
    markers: list[str] = []
    domain = registrable_domain(urlparse(target_url).netloc)
    publisher = domain.split(".")[0] if domain else ""
    if len(publisher) >= 4 and publisher not in _ORG_STOPWORDS:
        markers.append(publisher)
    org_clean = " ".join(org.strip().lower().split())
    if len(org_clean) >= 4 and org_clean not in _ORG_STOPWORDS:
        markers.append(org_clean)
    if entity:
        ent = entity.strip().lower()
        if 4 <= len(ent) <= 80 and not _is_generic_topic_marker(ent):
            markers.append(ent)
        for chunk in re.split(r"[\|\-–—:]", entity):
            chunk = " ".join(chunk.strip().lower().split())
            if 4 <= len(chunk) <= 60 and not _is_generic_topic_marker(chunk):
                markers.append(chunk)
    return list(dict.fromkeys(markers))


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
    *,
    org: str = "",
) -> ReferrerConnection | None:
    """Return a referrer tie only for explicit links or distinctive brand/publisher mentions."""
    blob = (html + " " + text).lower()
    parsed = urlparse(target_url)
    target_domain = registrable_domain(parsed.netloc)
    path = parsed.path.lower().strip("/")
    target_norm = target_url.rstrip("/").lower()

    if target_norm in blob:
        return ReferrerConnection("url_link", "high", target_norm)
    if target_domain in blob and path and path in blob:
        return ReferrerConnection("url_link", "high", f"{target_domain}/{path}")
    host_path = f"{parsed.netloc.lower()}{parsed.path}".lower()
    if host_path in blob:
        return ReferrerConnection("url_link", "high", host_path)

    for marker in _distinctive_markers(target_url, entity, org):
        if marker in blob:
            return ReferrerConnection("brand_mention", "weak", marker)
    return None


def _role_for_url(url: str) -> str:
    return classify_content_role(url)


def _is_same_brand(referrer_url: str, target_url: str) -> bool:
    r = registrable_domain(urlparse(referrer_url).netloc)
    t = registrable_domain(urlparse(target_url).netloc)
    return r == t


@dataclass
class _DiscoveryState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    citations: set[str] = field(default_factory=set)
    citation_sources: dict[str, str] = field(default_factory=dict)
    queries_run: int = 0
    target_cited: int = 0
    verified: list[VerifiedReferrer] = field(default_factory=list)
    seen_verified: set[str] = field(default_factory=set)
    fetched_ok: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    stopped_early: bool = False


def _verified_cap_reached(
    state: _DiscoveryState,
    *,
    min_seeds: int,
    max_verified: int,
) -> bool:
    return state.queries_run >= min_seeds and len(state.verified) >= max_verified


def _parallel_fetch_candidates(
    *,
    candidates: list[str],
    seed_query: str,
    seed_idx: int,
    n_seeds: int,
    target_url: str,
    entity: str,
    org: str,
    max_fetches_per_seed: int,
    max_verified_referrers: int,
    min_seeds_before_verified_stop: int,
    state: _DiscoveryState,
    fetch_workers: int,
    prog: Progress,
    stop: threading.Event,
) -> None:
    """Fetch citation pages concurrently; cap on successful fetches and verified total."""
    if not candidates:
        return

    workers = max(1, fetch_workers)
    ok_fetches = 0
    accounted = 0
    hit_fetch_cap = False
    pending: dict[Future, str] = {}
    cand_iter = iter(candidates)

    def _account(n: int = 1) -> None:
        nonlocal accounted
        accounted += n
        prog.advance(n)

    def _should_stop_submitting() -> bool:
        if stop.is_set():
            return True
        with state.lock:
            return ok_fetches >= max_fetches_per_seed or _verified_cap_reached(
                state,
                min_seeds=min_seeds_before_verified_stop,
                max_verified=max_verified_referrers,
            )

    def _submit_more(pool: ThreadPoolExecutor) -> None:
        while len(pending) < workers and not _should_stop_submitting():
            try:
                url = next(cand_iter)
            except StopIteration:
                return
            norm = url.rstrip("/").lower()
            with state.lock:
                already = norm in state.fetched_ok
            if already:
                _account(1)
                continue
            pending[pool.submit(fetch_page, url, timeout=12.0)] = url

    with ThreadPoolExecutor(max_workers=workers) as pool:
        _submit_more(pool)
        while pending:
            done, _ = wait(set(pending), return_when=FIRST_COMPLETED)
            for fut in done:
                url = pending.pop(fut)
                short = f"seed {seed_idx + 1}/{n_seeds}"
                try:
                    fr = fut.result()
                except Exception as exc:
                    with state.lock:
                        state.errors.append(f"fetch failed ({url}): {exc}")
                    prog.set_status(f"{short} fetch error · verified={len(state.verified)}")
                    _account(1)
                    _submit_more(pool)
                    continue

                if not fr.ok:
                    prog.set_status(
                        f"{short} fetch fail · verified={len(state.verified)}"
                    )
                    _account(1)
                    _submit_more(pool)
                    continue

                cited_norm = url.rstrip("/").lower()
                final = (fr.final_url or url).rstrip("/")
                conn = _verify_connection(
                    fr.text, fr.text, target_url, entity, org=org
                )
                with state.lock:
                    state.fetched_ok.add(cited_norm)
                    ok_fetches += 1
                    if ok_fetches >= max_fetches_per_seed:
                        hit_fetch_cap = True
                    if final.lower() not in state.seen_verified and conn:
                        state.seen_verified.add(final.lower())
                        state.verified.append(
                            VerifiedReferrer(
                                url=fr.final_url or url,
                                role=_role_for_url(fr.final_url or url),
                                connection=conn.kind,
                                connection_confidence=conn.confidence,
                                matched_marker=conn.marker,
                                seed_query=seed_query,
                            )
                        )
                    if _verified_cap_reached(
                        state,
                        min_seeds=min_seeds_before_verified_stop,
                        max_verified=max_verified_referrers,
                    ):
                        state.stopped_early = True
                        stop.set()
                    verified_n = len(state.verified)

                prog.set_status(
                    f"{short} ok_fetch={ok_fetches}/{max_fetches_per_seed} "
                    f"· verified={verified_n}"
                )
                _account(1)
                _submit_more(pool)

            if _should_stop_submitting() and not pending:
                break

    leftover = len(candidates) - accounted
    if leftover > 0:
        prog.advance(leftover)
    if hit_fetch_cap:
        with state.lock:
            state.errors.append(
                f"per-seed fetch cap reached ({max_fetches_per_seed}) for: {seed_query[:40]}"
            )


def discover_referrers(
    target_url: str,
    entity: str,
    seed_queries: list[str],
    engine: EngineAdapter | None,
    *,
    org: str = "",
    max_fetches_per_seed: int = 30,
    max_verified_referrers: int = 100,
    min_seeds_before_verified_stop: int = 4,
    query_delay_s: float = 0.0,
    target_role: str = "unknown",
    target_commercial_tier: str = "none",
    progress: Progress | None = None,
    seed_workers: int = 4,
    fetch_workers: int = 8,
) -> ReferralProfile:
    prog = progress or NullProgress()
    if engine is None:
        return ReferralProfile(
            status="skipped",
            discovery_status="skipped",
            confidence="low",
            notes=["Referral discovery skipped (no engine). L1-L3 verdict only."],
        )

    state = _DiscoveryState()
    stop = threading.Event()
    n_seeds = len(seed_queries)
    seed_workers = max(1, min(seed_workers, n_seeds or 1))
    fetch_workers = max(1, fetch_workers)
    query_gate = threading.Lock()
    last_query_start = 0.0

    prog.add_work(n_seeds)
    prog.set_status(
        f"discover 0/{n_seeds} seeds · seed_workers={seed_workers} "
        f"fetch_workers={fetch_workers}"
    )

    def _process_seed(seed_idx: int, q: str) -> None:
        nonlocal last_query_start
        if stop.is_set():
            prog.advance(1)
            return

        short_q = q if len(q) <= 42 else q[:39] + "..."
        prog.set_status(
            f"seed {seed_idx + 1}/{n_seeds} engine · verified={len(state.verified)} · {short_q}"
        )

        with query_gate:
            if query_delay_s > 0 and last_query_start > 0:
                wait_s = query_delay_s - (time.monotonic() - last_query_start)
                if wait_s > 0:
                    time.sleep(wait_s)
            last_query_start = time.monotonic()

        try:
            resp = engine.query(q)
        except Exception as exc:
            with state.lock:
                state.errors.append(f"engine query failed ({q[:40]}...): {exc}")
            prog.advance(1, status=f"seed {seed_idx + 1}/{n_seeds} engine failed")
            return

        with state.lock:
            state.queries_run += 1
            if _target_cited_in_response(resp.cited_urls, target_url):
                state.target_cited += 1
            for url in resp.cited_urls:
                state.citations.add(url)
                state.citation_sources.setdefault(url, q)
            if _verified_cap_reached(
                state,
                min_seeds=min_seeds_before_verified_stop,
                max_verified=max_verified_referrers,
            ):
                # Cap already met by other workers — skip new fetches.
                state.stopped_early = True
                stop.set()

        prog.advance(1)

        if stop.is_set():
            return

        candidates: list[str] = []
        for cited in resp.cited_urls:
            cited_norm = cited.rstrip("/").lower()
            if cited_norm == target_url.rstrip("/").lower():
                continue
            if _is_same_brand(cited, target_url):
                continue
            with state.lock:
                already = cited_norm in state.fetched_ok
            if already:
                continue
            candidates.append(cited)
        random.shuffle(candidates)
        if candidates:
            prog.add_work(len(candidates))

        _parallel_fetch_candidates(
            candidates=candidates,
            seed_query=q,
            seed_idx=seed_idx,
            n_seeds=n_seeds,
            target_url=target_url,
            entity=entity,
            org=org,
            max_fetches_per_seed=max_fetches_per_seed,
            max_verified_referrers=max_verified_referrers,
            min_seeds_before_verified_stop=min_seeds_before_verified_stop,
            state=state,
            fetch_workers=fetch_workers,
            prog=prog,
            stop=stop,
        )

        if state.stopped_early:
            stop.set()

    with ThreadPoolExecutor(max_workers=seed_workers) as pool:
        futures = [
            pool.submit(_process_seed, i, q) for i, q in enumerate(seed_queries)
        ]
        for fut in futures:
            try:
                fut.result()
            except Exception as exc:
                with state.lock:
                    state.errors.append(f"seed worker failed: {exc}")

    if state.stopped_early:
        with state.lock:
            if not any("Stopped after" in n for n in state.notes):
                state.notes.append(
                    f"Stopped after {state.queries_run} seeds: {len(state.verified)} "
                    f"verified referrers (cap {max_verified_referrers})."
                )

    citations = state.citations
    errors = state.errors
    notes = state.notes
    queries_run = state.queries_run
    target_cited = state.target_cited
    verified = state.verified

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
    elif n >= 10:
        status = "sparse"
        confidence = "medium"
        if ugc_share > 0.6 and editorial == 0:
            geo_suspected = True
            notes.append("UGC-heavy referrer mix (medium N) with no editorial/institutional share.")
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

    if (
        alignment.label == "mismatch"
        and ugc_share >= 0.8
        and n >= 5
        and editorial == 0
        and geo_suspected is not True
    ):
        geo_suspected = True
        notes.append(
            "Semantic mismatch: commercial target amplified via homogeneous non-commercial UGC."
        )

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
    seed_mode: str = "auto",
    fixture_path: Path | None = None,
    query_delay_s: float = 0.0,
    max_fetches_per_seed: int = 30,
    max_verified_referrers: int = 100,
    min_seeds_before_verified_stop: int = 4,
    progress: Progress | None = None,
    seed_workers: int = 4,
    fetch_workers: int = 8,
) -> InvestigationResult:
    """Mode B: URL in → L1-L3 always → optional referral discovery."""
    prog = progress or NullProgress()
    # Setup work units; discovery adds more once seed count / citations are known.
    prog.add_work(3)
    prog.set_status("fetch target page")
    fetch = fetch_page(url)
    prog.advance(1, status="score L1-L3")
    source = score_source(url, fetch, query=query)
    report = decide_single_source(source, query_intent, query=query)
    role = classify_content_role(url, fetch=fetch, source=source)
    meta = extract_page_metadata(fetch)
    prog.advance(1, status="generate seed queries")
    seeds, seed_source, seed_conf = resolve_seed_queries(
        role,
        meta,
        url=fetch.final_url or url,
        fetch=fetch,
        source=source,
        limit=seed_limit,
        mode=seed_mode,
    )
    prog.advance(1, status=f"seeds ready ({len(seeds)}, {seed_source})")

    engine: EngineAdapter | None = None
    if engine_name and engine_name != "none":
        engine = get_engine(engine_name, fixture_path=fixture_path)

    commercial_tier = "none"
    if source.page_context and source.page_context.commercial_tier:
        commercial_tier = source.page_context.commercial_tier

    try:
        profile = discover_referrers(
            url,
            meta.entity,
            seeds,
            engine,
            org=meta.org,
            query_delay_s=query_delay_s,
            max_fetches_per_seed=max_fetches_per_seed,
            max_verified_referrers=max_verified_referrers,
            min_seeds_before_verified_stop=min_seeds_before_verified_stop,
            target_role=role,
            target_commercial_tier=commercial_tier,
            progress=prog,
            seed_workers=seed_workers,
            fetch_workers=fetch_workers,
        )

        primary, actions = derive_llm_actions(
            report.permissions,
            report.subscores,
        ) if report.permissions and report.subscores else (
            report.recommended_action,
            [report.recommended_action],
        )

        verdict = _build_verdict(primary, profile, role)
        prog.close(final_status=f"done · verified={profile.n_verified}")
    except Exception:
        prog.close(final_status="failed")
        raise

    return InvestigationResult(
        target_url=fetch.final_url or url,
        content_role=role,
        seed_confidence=seed_conf,
        seed_source=seed_source,
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
        "seed_source": result.seed_source,
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
        f"Seed confidence: {result.seed_confidence} ({result.seed_source})",
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
            marker = f" ({ref.matched_marker})" if ref.matched_marker else ""
            lines.append(
                f"  [{ref.connection_confidence}] [{ref.role}] "
                f"{ref.connection}{marker}: {ref.url}"
            )
    lines.extend(["", "── Seed queries (for optional audit) ──"])
    for i, q in enumerate(result.seed_queries, 1):
        lines.append(f"  {i}. {q}")
    return "\n".join(lines)
