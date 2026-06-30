from __future__ import annotations

import re
import socket
import ssl
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse

from anti_geo.models import DomainSignals, FetchResult

SUSPICIOUS_TLDS = {".xyz", ".top", ".click", ".loan", ".work", ".fit", ".icu"}


def _parse_whois_age_days(hostname: str) -> int | None:
    """Best-effort WHOIS creation date via system whois CLI."""
    try:
        proc = subprocess.run(
            ["whois", hostname],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    output = proc.stdout.lower()
    patterns = [
        r"creation date:\s*([^\n]+)",
        r"created:\s*([^\n]+)",
        r"registered on:\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, output)
        if not match:
            continue
        raw = match.group(1).strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y"):
            try:
                created = datetime.strptime(raw[:19], fmt).replace(tzinfo=timezone.utc)
                return (datetime.now(timezone.utc) - created).days
            except ValueError:
                continue
    return None


def _cert_age_days(hostname: str) -> int | None:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as secure:
                cert = secure.getpeercert()
        not_before = cert.get("notBefore")
        if not not_before:
            return None
        created = datetime.strptime(not_before, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created).days
    except Exception:
        return None


def extract_domain_signals(url: str, fetch: FetchResult) -> DomainSignals:
    parsed = urlparse(fetch.final_url or url)
    hostname = parsed.hostname or ""
    tld = "." + hostname.split(".")[-1] if "." in hostname else hostname
    signals: list[str] = []

    dns_resolves = True
    try:
        socket.getaddrinfo(hostname, 443)
    except socket.gaierror:
        dns_resolves = False
        signals.append("dns_failure")

    is_https = parsed.scheme == "https"
    if not is_https:
        signals.append("no_https")

    whois_age = _parse_whois_age_days(hostname)
    cert_age = _cert_age_days(hostname) if is_https else None

    if whois_age is not None and whois_age < 90:
        signals.append(f"young_domain_{whois_age}d")
    elif whois_age is None and cert_age is not None and cert_age < 60:
        signals.append(f"young_cert_{cert_age}d")

    if tld in SUSPICIOUS_TLDS:
        signals.append(f"suspicious_tld{tld}")

    if fetch.redirect_count > 2:
        signals.append(f"excess_redirects_{fetch.redirect_count}")

    if hostname.count(".") >= 3:
        signals.append("deep_subdomain")

    return DomainSignals(
        hostname=hostname,
        tld=tld,
        is_https=is_https,
        cert_age_days=cert_age,
        whois_age_days=whois_age,
        dns_resolves=dns_resolves,
        signals=signals,
    )
