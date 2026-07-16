from __future__ import annotations

import re
from urllib.parse import urlparse

from anti_geo.concealment import CONCEALED_ATTR, mark_concealed_on_soup
from anti_geo.models import PageSegment
from anti_geo.platform_role import THREAD_PATH_RE

_COMMENT_TESTID_RE = re.compile(r"comment", re.I)
_FOOTER_HINTS = ("copyright", "all rights reserved", "privacy policy", "terms of use")


def _is_ugc_url(url: str) -> bool:
    """Thread-shaped pages only — comment/main_post HTML split (not LinkedIn/X)."""
    path = urlparse(url).path.lower()
    return bool(THREAD_PATH_RE.search(path))


def _segment_from_element(tag, role: str, ordinal: int) -> PageSegment | None:
    text = tag.get_text(separator=" ", strip=True)
    if len(text.split()) < 8:
        return None
    return PageSegment(
        segment_id=f"{role}_{ordinal}",
        role=role,
        text=text[:8000],
        ordinal=ordinal,
    )


def extract_page_segments(html: str, url: str) -> list[PageSegment]:
    """Parse structural page segments for UGC/thread pages (comments isolated from main post)."""
    if not html or not html.strip():
        return []

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    mark_concealed_on_soup(soup)
    for tag in list(soup.find_all(attrs={CONCEALED_ATTR: True})):
        tag.decompose()
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    segments: list[PageSegment] = []
    is_ugc = _is_ugc_url(url)

    if is_ugc:
        main_candidates = soup.find_all(["article", "main"], limit=3)
        if not main_candidates:
            main_candidates = [
                el
                for el in soup.find_all(["div", "section"], limit=20)
                if el.get("data-testid") == "post-container"
                or "post" in " ".join(el.get("class", [])).lower()
            ]
        for i, el in enumerate(main_candidates[:1]):
            seg = _segment_from_element(el, "main_post", i)
            if seg:
                segments.append(seg)

        comment_idx = 0
        for el in soup.find_all(["div", "article", "section"]):
            testid = el.get("data-testid") or ""
            classes = " ".join(el.get("class", [])).lower()
            if not (_COMMENT_TESTID_RE.search(testid) or "comment" in classes):
                continue
            role = "nested_comment" if "nested" in classes or "reply" in classes else "comment"
            seg = _segment_from_element(el, role, comment_idx)
            if seg:
                segments.append(seg)
                comment_idx += 1

    if not segments:
        main_el = soup.find("main") or soup.find("article")
        if main_el:
            seg = _segment_from_element(main_el, "main_post", 0)
            if seg:
                segments.append(seg)

    for i, aside in enumerate(soup.find_all("aside", limit=2)):
        seg = _segment_from_element(aside, "sidebar", i)
        if seg:
            segments.append(seg)

    footer_el = soup.find("footer")
    if footer_el:
        seg = _segment_from_element(footer_el, "footer", 0)
        if seg:
            segments.append(seg)

    if segments:
        return segments

    visible = soup.get_text(separator=" ", strip=True)
    if not visible:
        return []

    if is_ugc:
        parts = re.split(r"\n{2,}|(?<=[.!?])\s+(?=[A-Z\"'])", visible)
        parts = [p.strip() for p in parts if len(p.split()) >= 12]
        if len(parts) >= 2:
            segments.append(PageSegment("main_0", "main_post", parts[0], 0))
            for i, part in enumerate(parts[1:], start=1):
                segments.append(PageSegment(f"comment_{i}", "comment", part, i))
            return segments

    return [PageSegment("body_0", "body", visible[:8000], 0)]


def segment_role_from_chunk_id(chunk_id: str) -> str:
    if "__" in chunk_id:
        return chunk_id.split("__", 1)[0]
    return "body"


def segment_trust_ceiling(segment_role: str, page_role: str) -> float:
    ceilings = {
        "main_post": 1.0,
        "body": 1.0,
        "comment": 0.65,
        "nested_comment": 0.55,
        "sidebar": 0.45,
        "footer": 0.35,
    }
    ceiling = ceilings.get(segment_role, 1.0)
    if page_role == "ugc_thread" and segment_role in ("comment", "nested_comment"):
        ceiling = min(ceiling, 0.6)
    if page_role == "review_profile" and segment_role != "main_post":
        ceiling = min(ceiling, 0.5)
    return ceiling


def is_low_trust_segment(segment_role: str, page_role: str) -> bool:
    if segment_role in ("comment", "nested_comment", "sidebar", "footer"):
        return True
    return page_role in ("ugc_thread", "review_profile", "expert_listicle") and segment_role != "main_post"


def segment_retrieval_multiplier(segment_role: str, page_role: str, query_intent: str) -> float:
    """Downweight low-trust fragments so buried UGC promos do not outrank main content."""
    multiplier = 1.0
    if segment_role in ("sidebar", "footer"):
        multiplier = min(multiplier, 0.35)
    if segment_role == "nested_comment":
        multiplier = min(multiplier, 0.45)
    if segment_role == "comment":
        multiplier = min(multiplier, 0.5)
    if page_role == "ugc_thread" and segment_role in ("comment", "nested_comment"):
        multiplier = min(multiplier, 0.4 if query_intent == "commercial" else 0.55)
    return multiplier
