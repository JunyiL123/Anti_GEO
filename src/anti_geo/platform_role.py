from __future__ import annotations

import re
from urllib.parse import urlparse

from anti_geo.models import FetchResult, PageContextSignals, SourceScore

# Open-posting / forum thread surfaces. Path keywords + classic forum software
# routes (phpBB, vBulletin, XenForo, MyBB, SMF, Discourse, Flarum, IPS, …).
# Also drives comment segmentation (segments.py) and referrer triage.
THREAD_PATH_RE = re.compile(
    # Segment keywords (…/board/…, …/threads/…, …/topic/…)
    r"/(?:comments?|forums?|threads?|questions?|discussions?|"
    r"boards?|topics?|chit[_-]?chat|message[-_]?boards?|"
    r"showthreads?|forumdisplays?)"
    r"(?:/|$|\?)"
    # Legacy PHP endpoints
    r"|/(?:viewtopic|viewforum|showthread|forumdisplay|showpost|"
    r"printthread|newreply|newthread)\.php"
    # Discourse / Flarum slug+id
    r"|/t/[a-z0-9-]+/\d+"
    r"|/d/[a-z0-9-]+/\d+"
    # Quora / Q&A threads
    r"|/question(?:s)?/"
    # MyBB / SMF pretty URLs: thread-123.html, topic-123-title.html
    r"|/(?:thread|topic|forum|board)-\d+(?:-[a-z0-9_-]+)*(?:\.html?)?(?:/|$|\?)"
    # Vanilla / NodeBB / bbPress numeric discussion routes
    r"|/(?:discussion|topic|forum|thread)/\d+(?:-[a-z0-9_-]+)?(?:/|$|\?)"
    # Invision Community (IPS) pretty index.php?/topic/…
    r"|/index\.php\?/(?:topic|forum|forums|threads?)/"
    # XenForo-style threads/slug.123/ (numeric id after final dot)
    r"|/threads/[a-z0-9_-]+\.\d+(?:/|$|\?)"
    # Imageboard / Futaba-wakaba: /board/res/123.html or /res/123.html
    r"|/(?:[a-z0-9]{1,20}/)?res/\d+(?:\.html?)?(?:/|$|\?)"
    # Imageboard catalog post links: /board/thread/123 (already covered by threads?)
    # Explicit short-board + thread numeric (4chan-style /g/thread/123)
    r"|/[a-z0-9]{1,8}/thread/\d+(?:/|$|\?)",
    re.I,
)

# SMF / vB-style query params on generic scripts (avoid bare ?t= / ?f=).
FORUM_QUERY_RE = re.compile(
    r"(?:[?&](?:topic|board|thread|tid|fid|threadid|forumid)=\d)"
    r"|(?:[?&](?:action)=(?:showthread|forumdisplay|viewtopic|viewforum)\b)",
    re.I,
)

# Forum-hosting SaaS / freeboard platforms — host is the signal, not a brand list.
FORUM_SAAS_HOST_RE = re.compile(
    r"(?:^|\.)(?:"
    r"proboards\.com|boardhost\.com|invisionfree\.com|"
    r"websitetoolbox\.com|freeforums\.net|forumotion\.com|"
    r"createaforum\.com|niceboard\.com|boards\.net|"
    r"vbulletin\.net|discourse\.group|vanillaforums\.com|"
    r"discourse\.com|flarum\.cloud|"
    # Imageboards (4chan-like) — arbitrary board codes, host is the signal
    r"4chan\.org|4channel\.org|4cdn\.org|"
    r"8kun\.top|8ch\.net|lainchan\.org|endchan\.(?:net|org)|"
    r"smuglo\.li|wikichan\.org"
    r")$",
    re.I,
)

# LinkedIn / X-style open posting (UGC label + Mode B skip).
# Require end-of-segment so /blog/post-slug does not match.
SOCIAL_POST_PATH_RE = re.compile(r"/(posts?|pulse|feed|status)(?:/|$)", re.I)
# Medium-like publish-on-host paths — parasitic mix, not UGC.
PARASITIC_PUBLISH_PATH_RE = re.compile(r"/p/[a-z0-9]", re.I)

# User-upload video platforms — watch/shorts (and youtu.be/<id>) are open-posting
# UGC, same mix role as LinkedIn/X posts. Host-scoped so generic /watch sites
# are not swept in.
VIDEO_UGC_HOST_RE = re.compile(
    r"(?:^|\.)(?:youtube\.com|m\.youtube\.com|youtube-nocookie\.com|youtu\.be)$",
    re.I,
)
VIDEO_UGC_PATH_RE = re.compile(r"/(?:watch|shorts)(?:/|$)", re.I)

# Back-compat aliases.
UGC_PATH_RE = THREAD_PATH_RE
POST_SHAPED_PATH_RE = re.compile(
    r"/(posts?|pulse|newsletter)\b|/p/[a-z0-9]",
    re.I,
)

# Product review hubs + complaint / customer-review profiles (BBB-style).
# Includes app-store ratings hubs (…/ratings-and-reviews/…).
REVIEW_PROFILE_RE = re.compile(
    r"/(?:product-reviews/|products/[^/]+/reviews(?:/|$)|"
    r"customer[-_]reviews?(?:/|$)|"
    r"user[-_]reviews?(?:/|$)|"
    r"app[-_]reviews?(?:/|$)|"
    r"ratings[-_]and[-_]reviews?(?:/|$)|"
    r"ratings(?:/|$)|"
    r"complaints?(?:/|$)|"
    r"reviews?(?:/|$)|"
    r"profile/[^?\s]+/(?:customer[-_])?reviews?(?:/|$)|"
    r"review/[a-z0-9_-]+)",
    re.I,
)
EDITORIAL_PICKS_RE = re.compile(r"/(picks|best-|roundup|guide)/", re.I)
PRODUCT_PATH_RE = re.compile(r"/(dp/|product/|products/|shop/|buy/|item/)\b", re.I)

# SEO forum/community directories (Feedspot / GrowReddit-style aggregators).
# Path-shaped only — no per-host brand lists.
FORUM_DIRECTORY_PATH_RE = re.compile(
    r"/(?:directory|directories)(?:/|$)"
    r"|/[a-z0-9_-]+[_-]forums?(?:/|$)"  # gaming_forums/, pc-gaming-forums/
    r"|/best[-_][a-z0-9_-]*forums?(?:/|$)",
    re.I,
)


# Common multi-part public suffixes (no PSL dependency). Hosts ending in these
# use last-three labels so example.co.uk is not mangled to co.uk.
_MULTI_PART_PUBLIC_SUFFIXES = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "net.au",
        "org.au",
        "co.jp",
        "or.jp",
        "ne.jp",
        "com.br",
        "co.in",
        "com.mx",
        "co.nz",
        "co.za",
        "com.sg",
        "com.hk",
        "co.kr",
        "com.tw",
        "com.cn",
        "com.ar",
        "co.il",
    }
)


def registrable_domain(hostname: str) -> str:
    host = hostname.lower().removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 3:
        suffix2 = ".".join(parts[-2:])
        if suffix2 in _MULTI_PART_PUBLIC_SUFFIXES:
            return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def is_forum_saas_host(hostname: str) -> bool:
    """True for freemium / hosted forum platforms (path may be arbitrary)."""
    host = hostname.lower().removeprefix("www.")
    return bool(FORUM_SAAS_HOST_RE.search(host))


def is_forum_subdomain_host(hostname: str) -> bool:
    """forum.* / forums.* hosts — usually real Discourse/phpBB communities."""
    host = hostname.lower().removeprefix("www.")
    return host.startswith("forums.") or host.startswith("forum.")


# Back-compat alias (older name implied "directory"; host alone is not).
is_forum_directory_host = is_forum_subdomain_host


def is_forum_directory_path(url: str) -> bool:
    """True for directory/aggregator URL shapes (Feedspot-like).

    Path patterns only — do not treat bare ``forum.brand.com/top`` as a
    directory; those are live UGC surfaces (see ``is_open_posting_path``).
    """
    parsed = urlparse(url)
    path = parsed.path or ""
    if FORUM_DIRECTORY_PATH_RE.search(path):
        return True
    # Shallow single-segment index ending in forum(s), any host
    # (e.g. /gaming_forums, /pc_gaming_forums).
    stripped = path.strip("/")
    if stripped and "/" not in stripped and re.search(r"forums?$", stripped, re.I):
        return True
    return False


def is_thread_path(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path or ""
    query = parsed.query or ""
    blob = f"{path}?{query}" if query else path
    if THREAD_PATH_RE.search(path) or THREAD_PATH_RE.search(blob):
        return True
    if FORUM_QUERY_RE.search(blob):
        return True
    return False


def is_social_post_path(url: str) -> bool:
    return bool(SOCIAL_POST_PATH_RE.search(urlparse(url).path or ""))


def is_video_ugc_path(url: str) -> bool:
    """YouTube watch/shorts (and youtu.be/<id>) — open-posting UGC surfaces."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if not VIDEO_UGC_HOST_RE.search(host):
        return False
    path = parsed.path or ""
    # youtu.be/<id> short links
    if host == "youtu.be" or host.endswith(".youtu.be"):
        slug = path.strip("/")
        return bool(slug) and "/" not in slug
    return bool(VIDEO_UGC_PATH_RE.search(path))


def is_open_posting_path(url: str) -> bool:
    """Thread or social open-posting URL — UGC surfaces."""
    host = urlparse(url).netloc or ""
    if is_forum_saas_host(host):
        return True
    # forum.brand.com / forums.brand.com — including Discourse indexes (/top,
    # /latest, bare /). Aggregator paths (*_forums, /directory) stay non-UGC.
    if is_forum_subdomain_host(host) and not is_forum_directory_path(url):
        return True
    return (
        is_thread_path(url)
        or is_social_post_path(url)
        or is_video_ugc_path(url)
    )


def is_parasitic_publish_path(url: str) -> bool:
    """Medium-like /p/ publish-host shape — parasitic mix, not UGC."""
    return bool(PARASITIC_PUBLISH_PATH_RE.search(urlparse(url).path or ""))


def is_ugc_role(role: str) -> bool:
    """True for open-posting UGC (forums + LinkedIn/X) — Mode A skips Mode B."""
    return role == "ugc_thread"


def is_parasitic_referrer(
    *,
    url: str,
    role: str,
    content_high_risk: bool = False,
    llm_parasitic: bool = False,
) -> bool:
    """Potential parasitic GEO surface for mix share (unweighted boolean).

    Always: open-posting UGC paths, Medium-like /p/, review_profile,
    forum/community directory aggregators, or Mode B LLM parasitic flag.
    Conditional: factual_blog only when L1 already marked high-risk.
    """
    if llm_parasitic:
        return True
    if is_open_posting_path(url) or is_parasitic_publish_path(url):
        return True
    if is_forum_directory_path(url):
        return True
    if role == "review_profile" or role == "ugc_thread":
        return True
    if role == "factual_blog" and content_high_risk:
        return True
    return False


def classify_content_role(
    url: str,
    *,
    fetch: FetchResult | None = None,
    source: SourceScore | None = None,
) -> str:
    """Infer page role from URL structure and page signals — no domain brand lists."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()

    if host.endswith(".gov") or host.endswith(".edu"):
        return "institutional"

    # Open posting (Reddit / LinkedIn / X / classic forums / forum SaaS) → UGC.
    if is_open_posting_path(url):
        return "ugc_thread"

    if EDITORIAL_PICKS_RE.search(path):
        return "editorial"

    if REVIEW_PROFILE_RE.search(path):
        return "review_profile"

    # Forum/community SEO directories (Feedspot / GrowReddit-style) — listicle, not UGC.
    # Checked before commercial so CTA-heavy directories stay Mode-B-eligible.
    if is_forum_directory_path(url):
        return "expert_listicle"

    # Medium-like /p/ and leftover newsletter shapes — soft publish, not UGC.
    if PARASITIC_PUBLISH_PATH_RE.search(path) or re.search(
        r"/newsletter\b", path, re.I
    ):
        return "expert_listicle"

    page_ctx: PageContextSignals | None = None
    if source and source.page_context:
        page_ctx = source.page_context
    elif fetch and fetch.page_context:
        page_ctx = fetch.page_context

    if PRODUCT_PATH_RE.search(path):
        return "commercial_product"

    # Main-content commercial signals (chrome-only monetization does not raise tier).
    if page_ctx and page_ctx.commercial_tier in ("medium", "high"):
        # Hard sell / PDP-like body → product; affiliate editorial without CTAs → listicle.
        if "commercial_cta" in page_ctx.flags:
            return "commercial_product"
        return "expert_listicle"

    if re.search(r"/(wiki|docs|reference|encyclopedia)\b", path):
        return "factual_blog"

    if fetch and fetch.ok and fetch.text:
        text = fetch.text[:2000].lower()
        if re.search(r"\b(buy now|add to cart|free trial|subscribe)\b", text):
            return "commercial_product"
        if re.search(r"\b(affiliate|sponsored|paid partnership)\b", text):
            return "expert_listicle"

    return "factual_blog"
