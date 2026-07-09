from __future__ import annotations

import re
import socket
import ssl
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse

from anti_geo.models import DomainSignals, FetchResult

SUSPICIOUS_TLDS = {".xyz", ".top", ".click", ".loan", ".work", ".fit", ".icu"}


def _apex_hostname(hostname: str) -> str:
    host = hostname.lower().strip(".")
    if host.startswith("www."):
        return host[4:]
    return host


def _parse_whois_datetime(raw: str) -> datetime | None:
    cleaned = raw.strip()
    formats = (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%b-%Y",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(cleaned[:25], fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def _registrar_whois_block(hostname: str, output: str) -> str:
    """Prefer the registrar record over IANA TLD metadata."""
    apex = _apex_hostname(hostname)
    match = re.search(
        rf"domain name:\s*{re.escape(apex)}\b.*",
        output,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(0) if match else ""


def _parse_whois_creation_days(hostname: str, output: str) -> int | None:
    apex = _apex_hostname(hostname)
    match = re.search(
        rf"domain name:\s*{re.escape(apex)}\b.*",
        output,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    block = match.group(0)
    patterns = [
        r"creation date:\s*([^\n]+)",
        r"created:\s*([^\n]+)",
        r"registered on:\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, block, flags=re.IGNORECASE)
        if not match:
            continue
        created = _parse_whois_datetime(match.group(1))
        if created is None:
            continue
        return (datetime.now(timezone.utc) - created).days
    return None


def _parse_whois_age_days(hostname: str) -> int | None:
    """Best-effort WHOIS creation date via system whois CLI."""
    apex = _apex_hostname(hostname)
    try:
        proc = subprocess.run(
            ["whois", apex],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    return _parse_whois_creation_days(apex, proc.stdout)


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
