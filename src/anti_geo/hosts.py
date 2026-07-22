"""Host-level helpers (news outlets)."""

from __future__ import annotations

from urllib.parse import urlparse

# Curated allowlist of major news / wire outlets (explicit domains, not a
# general "looks like news" rule). Used for +trust and factual reliability.
# Prefer structural .gov/.edu boosts for institutions; extend this set sparingly.
MAJOR_NEWS_APEXES = frozenset(
    {
        "nytimes.com",
        "theguardian.com",
        "washingtonpost.com",
        "wsj.com",
        "reuters.com",
        "bbc.com",
        "bbc.co.uk",
        "apnews.com",
        "npr.org",
        "cnn.com",
        "bloomberg.com",
        "ft.com",
        "economist.com",
        "latimes.com",
        "usatoday.com",
        "time.com",
        "theatlantic.com",
        "newyorker.com",
        "politico.com",
        "axios.com",
        "cbsnews.com",
        "nbcnews.com",
        "abcnews.go.com",
        "pbs.org",
        "thehill.com",
        "forbes.com",
        "businessinsider.com",
        "independent.co.uk",
        "telegraph.co.uk",
        "smh.com.au",
        "aljazeera.com",
    }
)


def hostname_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return host.removeprefix("www.")


def apex_of(hostname: str) -> str:
    host = (hostname or "").lower().removeprefix("www.").strip(".")
    if not host:
        return ""
    # Keep multi-label news hosts like abcnews.go.com intact when listed as apex.
    if host in MAJOR_NEWS_APEXES:
        return host
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def is_major_news_host(hostname_or_url: str) -> bool:
    raw = (hostname_or_url or "").lower().strip()
    if not raw:
        return False
    host = hostname_of(raw) if "://" in raw or raw.startswith("//") else raw.removeprefix("www.")
    if host in MAJOR_NEWS_APEXES:
        return True
    return any(host == apex or host.endswith("." + apex) for apex in MAJOR_NEWS_APEXES)
