"""Detect CSS/DOM-hidden text, structured-channel concealment, and visible IPI.

Marks elements that are invisible to sighted users but still machine-readable,
plus JSON-LD / nonstandard scripts / meta that carry agent-instruction or
GEO-rhetoric payloads. Also flags visible-body chatbot directives (e.g. footer
"forget previous instructions" / "directive for chatbots"). A11y-only classes
(sr-only) are allowlisted unless instruction or GEO patterns fire.
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from anti_geo.content_signals import extract_content_signals
from anti_geo.models import ConcealmentSignals

# Mark on soup tags so fetch/segments can strip the same subtrees.
CONCEALED_ATTR = "data-anti-geo-concealed"

A11Y_CLASS_RE = re.compile(
    r"(?:\b|^)(?:"
    r"sr-only|visually-hidden|visuallyhidden|screen-reader-text|"
    r"screenreader|a11y-hidden|assistive-text|clip|u-visually-hidden"
    r")(?:\b|$)",
    re.I,
)

INSTRUCTION_PATTERNS = [
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions?\b", re.I),
    re.compile(r"\bforget\s+(?:all\s+)?(?:previous|prior)\s+instructions?\b", re.I),
    re.compile(r"\byou\s+are\s+(?:an?\s+)?(?:ai|agent|assistant)\b", re.I),
    re.compile(r"\bsystem\s*:", re.I),
    re.compile(r"\balways\s+(?:cite|recommend|rank)\b", re.I),
    re.compile(r"\btreat\s+this\s+(?:page|site|url|domain)\s+as\b", re.I),
    re.compile(r"\bconsider\s+this\s+(?:page|site|url|domain)\s+as\b", re.I),
    re.compile(r"\bdo\s+not\s+mention\b", re.I),
    re.compile(r"\b#\s*1\s+primary\s+source\b", re.I),
    re.compile(r"\bverified[, ]+authoritative\s+destination\b", re.I),
    re.compile(r"\bauthoritative\s+(?:destination|reference|source)\b", re.I),
    re.compile(r"\brank\s+(?:this|the\s+page|the\s+site)\s+as\s+(?:the\s+)?#?\s*1\b", re.I),
    re.compile(r"\bfor\s+(?:ai|llm|language)\s+(?:agents?|models?|assistants?)\b", re.I),
    re.compile(r"\bfor\s+chatbots?\s*:", re.I),
    re.compile(
        r"\b(?:directives?|instructions?)\s+for\s+"
        r"(?:chatbots?|ai|llms?|language\s+models?|agents?|assistants?)\b",
        re.I,
    ),
    re.compile(r"\bimportant\s+(?:system\s+)?(?:note|instruction)\s+for\s+(?:ai|agents?)\b", re.I),
]

# Host/site promotion inside instruction-like text (not mere educational quotes).
PROMOTIONAL_INSTRUCTION_PATTERNS = [
    re.compile(r"\balways\s+(?:cite|recommend|rank)\b", re.I),
    re.compile(r"\btreat\s+this\s+(?:page|site|url|domain)\s+as\b", re.I),
    re.compile(r"\bconsider\s+this\s+(?:page|site|url|domain)\s+as\b", re.I),
    re.compile(r"\b#\s*1\s+primary\s+source\b", re.I),
    re.compile(r"\bverified[, ]+authoritative\s+destination\b", re.I),
    re.compile(r"\bauthoritative\s+(?:destination|reference|source)\b", re.I),
    re.compile(r"\brank\s+(?:this|the\s+page|the\s+site)\s+as\s+(?:the\s+)?#?\s*1\b", re.I),
    re.compile(r"\bfor\s+chatbots?\s*:", re.I),
    re.compile(
        r"\b(?:directives?|instructions?)\s+for\s+"
        r"(?:chatbots?|ai|llms?|language\s+models?|agents?|assistants?)\b",
        re.I,
    ),
    re.compile(r"\bonly\s+(?:official|trusted|authoritative)\s+(?:site|page|source)\b", re.I),
]

_HIDDEN_STYLE_RES = [
    re.compile(r"\bdisplay\s*:\s*none\b", re.I),
    re.compile(r"\bvisibility\s*:\s*hidden\b", re.I),
    re.compile(r"\bopacity\s*:\s*0(?:\.0+)?\b", re.I),
    re.compile(r"\bfont-size\s*:\s*0(?:px|pt|em|rem)?\b", re.I),
    re.compile(r"\bclip\s*:\s*rect\s*\(\s*0", re.I),
]
_OFFSCREEN_RE = re.compile(
    r"\b(?:left|top|right|bottom)\s*:\s*-\s*(?:[5-9]\d{2,}|\d{4,})\s*px\b",
    re.I,
)
_POSITIONED_RE = re.compile(r"\bposition\s*:\s*(?:absolute|fixed)\b", re.I)
_ZERO_HEIGHT_RE = re.compile(r"\bheight\s*:\s*0(?:px|pt|em|rem)?\b", re.I)
_OVERFLOW_HIDDEN_RE = re.compile(r"\boverflow\s*:\s*hidden\b", re.I)

_STYLE_RULE_RE = re.compile(
    r"([^{}@][^{]*)\{([^}]*)\}",
    re.S,
)
_META_INTERESTING = frozenset(
    {
        "description",
        "keywords",
        "og:description",
        "og:title",
        "twitter:description",
        "twitter:title",
    }
)
_STRUCTURED_SCRIPT_TYPES = frozenset(
    {
        "application/ld+json",
        "text/llm",
        "text/plain",
        "text/x-llm",
        "application/llm",
    }
)
# Quote-density is excluded: raw JSON-LD is almost always quote_citation_heavy
# because schema values are long "..." strings, which is not GEO rhetoric.
_GEO_L1_FLAGS = frozenset(
    {
        "authority_stacking",
        "comparative_superlatives",
        "front_loaded",
    }
)


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _word_count(text: str) -> int:
    return len(_normalize_ws(text).split()) if text and text.strip() else 0


def _has_instruction_pattern(text: str) -> bool:
    if not text or not text.strip():
        return False
    return any(p.search(text) for p in INSTRUCTION_PATTERNS)


def _has_promotional_instruction(text: str) -> bool:
    """True when instruction-like text also promotes this page/site/host."""
    if not text or not text.strip():
        return False
    return any(p.search(text) for p in PROMOTIONAL_INSTRUCTION_PATTERNS)


def _instruction_excerpt(text: str, max_chars: int = 300) -> str:
    """Return a short window around the first instruction-pattern match."""
    if not text or not text.strip():
        return ""
    for pattern in INSTRUCTION_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + max_chars)
        return _normalize_ws(text[start:end])[:max_chars]
    return ""


def _style_hides(style: str) -> tuple[bool, bool]:
    """Return (is_hidden, is_offscreen)."""
    if not style:
        return False, False
    if any(p.search(style) for p in _HIDDEN_STYLE_RES):
        return True, bool(_OFFSCREEN_RE.search(style) and _POSITIONED_RE.search(style))
    if _ZERO_HEIGHT_RE.search(style) and _OVERFLOW_HIDDEN_RE.search(style):
        return True, False
    if _OFFSCREEN_RE.search(style) and _POSITIONED_RE.search(style):
        return True, True
    return False, False


def _is_a11y_only(tag: Tag) -> bool:
    classes = tag.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    blob = " ".join(classes)
    if tag.get("id"):
        blob = f"{blob} {tag.get('id')}"
    return bool(A11Y_CLASS_RE.search(blob))


def _parse_stylesheet_hidden_selectors(soup: BeautifulSoup) -> tuple[set[str], set[str]]:
    """Class and id selectors whose CSS rules hide content."""
    hidden_classes: set[str] = set()
    hidden_ids: set[str] = set()
    for style_tag in soup.find_all("style"):
        css = style_tag.string or style_tag.get_text() or ""
        for match in _STYLE_RULE_RE.finditer(css):
            selectors, body = match.group(1), match.group(2)
            hides, _ = _style_hides(body)
            if not hides:
                continue
            for part in selectors.split(","):
                part = part.strip()
                for cls in re.findall(r"\.([A-Za-z_][\w-]*)", part):
                    hidden_classes.add(cls.lower())
                for eid in re.findall(r"#([A-Za-z_][\w-]*)", part):
                    hidden_ids.add(eid.lower())
    return hidden_classes, hidden_ids


def _element_is_concealed(
    tag: Tag,
    hidden_classes: set[str],
    hidden_ids: set[str],
) -> tuple[bool, bool, bool]:
    """Return (concealed, offscreen, a11y_allowlisted)."""
    if tag.name in ("script", "style", "noscript", "template"):
        return False, False, False

    a11y = _is_a11y_only(tag)

    if tag.has_attr("hidden"):
        return True, False, a11y
    aria = (tag.get("aria-hidden") or "").strip().lower()
    if aria == "true":
        return True, False, a11y

    style = tag.get("style") or ""
    hides, offscreen = _style_hides(style)
    if hides:
        return True, offscreen, a11y

    classes = tag.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    for cls in classes:
        if cls.lower() in hidden_classes:
            off = "traceback" in cls.lower() or "offscreen" in cls.lower()
            return True, off, a11y

    eid = (tag.get("id") or "").lower()
    if eid and eid in hidden_ids:
        return True, False, a11y

    # Screen-reader-only chrome: exclude from visible text even without CSS hide.
    if a11y:
        return True, False, True

    return False, False, False


def _collect_dom_concealed(
    soup: BeautifulSoup,
) -> tuple[list[Tag], list[str], bool, list[bool]]:
    """Find top-level concealed elements; return tags, texts, any_offscreen, a11y flags."""
    hidden_classes, hidden_ids = _parse_stylesheet_hidden_selectors(soup)
    marked: list[Tag] = []
    texts: list[str] = []
    a11y_flags: list[bool] = []
    any_offscreen = False
    seen: set[int] = set()

    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        if id(tag) in seen:
            continue
        # Skip if an ancestor is already marked concealed.
        if any(id(p) in seen for p in tag.parents if isinstance(p, Tag)):
            continue
        concealed, offscreen, a11y = _element_is_concealed(tag, hidden_classes, hidden_ids)
        if not concealed:
            continue
        text = _normalize_ws(tag.get_text(separator=" ", strip=True))
        if _word_count(text) < 1:
            continue
        marked.append(tag)
        texts.append(text)
        a11y_flags.append(a11y)
        seen.add(id(tag))
        if offscreen:
            any_offscreen = True
        # Mark descendants so strip pass is consistent.
        tag[CONCEALED_ATTR] = "1"
        for child in tag.find_all(True):
            if isinstance(child, Tag):
                child[CONCEALED_ATTR] = "1"
                seen.add(id(child))

    return marked, texts, any_offscreen, a11y_flags


def _structured_channel_texts(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Return list of (channel, text) from JSON-LD / llm scripts / meta."""
    out: list[tuple[str, str]] = []

    for script in soup.find_all("script"):
        stype = (script.get("type") or "").strip().lower()
        if stype not in _STRUCTURED_SCRIPT_TYPES and stype != "":
            # Skip normal JS; empty type with agent text is rare — ignore.
            continue
        if stype == "" or stype in ("text/javascript", "application/javascript", "module"):
            continue
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        if stype == "application/ld+json":
            try:
                data = json.loads(raw)
                text = _normalize_ws(json.dumps(data, ensure_ascii=False))
            except json.JSONDecodeError:
                text = _normalize_ws(raw)
            out.append(("json_ld", text))
        else:
            out.append(("script_llm", _normalize_ws(raw)))

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or "").strip().lower()
        if name not in _META_INTERESTING:
            continue
        content = _normalize_ws(meta.get("content") or "")
        if _word_count(content) < 3:
            continue
        out.append((f"meta:{name}", content))

    return out


def _meta_diverges(meta_text: str, visible_text: str) -> bool:
    """True when meta looks like a distinct payload vs body (or has instructions)."""
    if _has_instruction_pattern(meta_text):
        return True
    meta_tokens = set(re.findall(r"[a-z0-9]{4,}", meta_text.lower()))
    vis_tokens = set(re.findall(r"[a-z0-9]{4,}", visible_text.lower()))
    if not meta_tokens:
        return False
    overlap = len(meta_tokens & vis_tokens) / max(len(meta_tokens), 1)
    return overlap < 0.25 and len(meta_tokens) >= 5


def strip_concealed_elements(soup: BeautifulSoup) -> None:
    """Decompose elements marked as concealed (and script/style/noscript)."""
    for tag in list(soup.find_all(attrs={CONCEALED_ATTR: True})):
        tag.decompose()
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()


def extract_visible_text_from_soup(soup: BeautifulSoup, max_chars: int = 50_000) -> str:
    """Visible body text after stripping concealed + non-content tags."""
    strip_concealed_elements(soup)
    return _normalize_ws(soup.get_text(separator=" ", strip=True))[:max_chars]


def extract_concealment(
    html: str,
    *,
    url: str = "",
    max_chars: int = 50_000,
) -> tuple[ConcealmentSignals, str]:
    """Analyze HTML; return (signals, visible_text).

    Side effect: works on an internal soup copy. Callers that need the same
    concealed marks on their own soup should call ``mark_concealed_on_soup``.
    """
    _ = url  # reserved for future host-scoped heuristics
    if not html or not html.strip():
        empty = ConcealmentSignals()
        return empty, ""

    soup = BeautifulSoup(html, "html.parser")
    signals, visible = _extract_from_soup(soup, max_chars=max_chars)
    if looks_like_paywall(html, visible) and "paywall_suspected" not in signals.flags:
        signals.flags = list(signals.flags) + ["paywall_suspected"]
    return signals, visible


def mark_concealed_on_soup(soup: BeautifulSoup) -> ConcealmentSignals:
    """Mark concealed DOM on *soup* in place; return signals (no visible split)."""
    signals, _ = _extract_from_soup(soup, max_chars=50_000, compute_visible=False)
    return signals


def _extract_from_soup(
    soup: BeautifulSoup,
    *,
    max_chars: int = 50_000,
    compute_visible: bool = True,
) -> tuple[ConcealmentSignals, str]:
    marked, dom_texts, any_offscreen, a11y_flags = _collect_dom_concealed(soup)

    # Visible text: clone-free path when compute_visible — strip on a copy.
    visible_text = ""
    if compute_visible:
        # Work on the same soup after marking: strip then restore is hard.
        # Re-parse from marked soup string would lose marks for segments.
        # Instead: gather visible by walking and skipping concealed.
        visible_text = _visible_text_skipping_marked(soup)[:max_chars]

    structured = _structured_channel_texts(soup)
    structured_parts: list[str] = []
    structured_flagged_parts: list[str] = []
    for channel, text in structured:
        if channel.startswith("meta:"):
            if not _meta_diverges(text, visible_text):
                continue
            structured_flagged_parts.append(text)
            structured_parts.append(text)
        elif channel == "json_ld":
            structured_parts.append(text)
            if _has_instruction_pattern(text) or _json_ld_looks_manipulative(text):
                structured_flagged_parts.append(text)
        else:
            structured_parts.append(text)
            if _has_instruction_pattern(text):
                structured_flagged_parts.append(text)

    # Classify DOM blocks: a11y allowlist vs suspicious.
    suspicious_texts: list[str] = []
    a11y_instruction_texts: list[str] = []
    block_count = 0
    for tag, text, a11y in zip(marked, dom_texts, a11y_flags, strict=True):
        _ = tag
        has_instr = _has_instruction_pattern(text)
        if a11y and not has_instr:
            # Benign screen-reader chrome: keep marked (out of visible) but no flag.
            continue
        block_count += 1
        if a11y and has_instr:
            a11y_instruction_texts.append(text)
        suspicious_texts.append(text)

    hidden_corpus = _normalize_ws(" ".join(suspicious_texts + structured_flagged_parts))
    all_concealed = _normalize_ws(
        " ".join(suspicious_texts + structured_parts + a11y_instruction_texts)
    )[:max_chars]

    vis_words = _word_count(visible_text)
    hid_words = _word_count(" ".join(suspicious_texts))
    struct_words = _word_count(" ".join(structured_parts))
    denom = max(vis_words + hid_words, 1)
    hidden_ratio = hid_words / denom

    flags: list[str] = []
    if suspicious_texts:
        flags.append("css_concealed_content")
    if any_offscreen and suspicious_texts:
        flags.append("offscreen_positioned")
    if structured_flagged_parts or (
        structured_parts and _has_instruction_pattern(" ".join(structured_parts))
    ):
        flags.append("structured_concealed")
    # Always mark structured_concealed when JSON-LD/script carries instructions
    # or when we kept divergent meta; also when any structured text has instructions.
    if structured_parts and (
        _has_instruction_pattern(" ".join(structured_parts))
        or structured_flagged_parts
    ):
        if "structured_concealed" not in flags:
            flags.append("structured_concealed")

    combined_hidden = " ".join(suspicious_texts + structured_parts)
    if _has_instruction_pattern(combined_hidden) or a11y_instruction_texts:
        flags.append("hidden_instruction_pattern")

    # Hidden GEO rhetoric: L1 flags in already-suspicious concealed text only.
    # Do not fall back to all structured_parts — benign JSON-LD would L1-score.
    concealed_for_l1 = " ".join(suspicious_texts + structured_flagged_parts)
    if _word_count(concealed_for_l1) >= 8:
        hidden_sigs = extract_content_signals(concealed_for_l1)
        visible_sigs = extract_content_signals(visible_text) if visible_text else None
        hidden_geo = set(hidden_sigs.flags) & _GEO_L1_FLAGS
        visible_geo = set(visible_sigs.flags) & _GEO_L1_FLAGS if visible_sigs else set()
        if hidden_geo and not (hidden_geo & visible_geo):
            # Divergence: concealed has GEO rhetoric visible lacks (or different).
            if not visible_geo or hidden_geo - visible_geo:
                flags.append("hidden_geo_rhetoric")

    # Visible-body IPI (footer directives, etc.) — same patterns, not CSS-hidden.
    visible_instruction = bool(visible_text and _has_instruction_pattern(visible_text))
    if visible_instruction:
        flags.append("visible_instruction_pattern")

    # Highest-risk excerpt for reports.
    excerpt_src = ""
    if "hidden_instruction_pattern" in flags:
        for t in suspicious_texts + structured_parts + a11y_instruction_texts:
            if _has_instruction_pattern(t):
                excerpt_src = t
                break
    if not excerpt_src and visible_instruction:
        excerpt_src = _instruction_excerpt(visible_text)
    if not excerpt_src and suspicious_texts:
        excerpt_src = max(suspicious_texts, key=_word_count)
    elif not excerpt_src and structured_flagged_parts:
        excerpt_src = structured_flagged_parts[0]
    excerpt = excerpt_src[:300]

    # Drop empty flag noise when nothing suspicious.
    if not suspicious_texts and "structured_concealed" not in flags:
        keep = {"hidden_instruction_pattern", "visible_instruction_pattern"}
        flags = [f for f in flags if f in keep]
        # a11y-only instruction still counts
        if a11y_instruction_texts and "hidden_instruction_pattern" not in flags:
            flags.append("hidden_instruction_pattern")
            if "css_concealed_content" not in flags:
                flags.append("css_concealed_content")
            block_count = max(block_count, len(a11y_instruction_texts))
            hid_words = max(hid_words, _word_count(" ".join(a11y_instruction_texts)))
            denom = max(vis_words + hid_words, 1)
            hidden_ratio = hid_words / denom
        if visible_instruction and "visible_instruction_pattern" not in flags:
            flags.append("visible_instruction_pattern")

    # Promotional IPI: directives that push ranking/recommendation of this site.
    # Educational quotes of "ignore previous instructions" alone do not qualify.
    # Applied after chrome cleanup so the flag is not stripped.
    promo_corpus_parts: list[str] = []
    if "hidden_instruction_pattern" in flags:
        promo_corpus_parts.extend(suspicious_texts)
        promo_corpus_parts.extend(structured_parts)
        promo_corpus_parts.extend(a11y_instruction_texts)
    if "visible_instruction_pattern" in flags and visible_text:
        promo_corpus_parts.append(visible_text)
    if promo_corpus_parts and _has_promotional_instruction(" ".join(promo_corpus_parts)):
        flags.append("promotional_instruction_pattern")

    signals = ConcealmentSignals(
        visible_word_count=vis_words,
        hidden_word_count=hid_words,
        hidden_ratio=round(hidden_ratio, 4),
        hidden_block_count=block_count,
        structured_word_count=struct_words,
        flags=flags,
        excerpt=excerpt,
        concealed_text=all_concealed[:max_chars],
    )
    return signals, visible_text


def _json_ld_looks_manipulative(text: str) -> bool:
    lower = text.lower()
    paymentish = any(
        k in lower
        for k in (
            "missinglicensekey",
            "license key",
            "checkout",
            "stripe",
            "0x",
            "ethereum",
            "api key",
            "paywall",
        )
    )
    softapp = "softwareapplication" in lower.replace(" ", "")
    return paymentish or (softapp and ("offer" in lower or "price" in lower))


def _visible_text_skipping_marked(soup: BeautifulSoup) -> str:
    parts: list[str] = []

    def walk(node: Tag | NavigableString) -> None:
        if isinstance(node, NavigableString):
            parent = node.parent
            if parent and isinstance(parent, Tag):
                if parent.name in ("script", "style", "noscript", "template"):
                    return
                if parent.get(CONCEALED_ATTR):
                    return
            text = str(node).strip()
            if text:
                parts.append(text)
            return
        if not isinstance(node, Tag):
            return
        if node.name in ("script", "style", "noscript", "template"):
            return
        if node.get(CONCEALED_ATTR):
            return
        for child in node.children:
            walk(child)  # type: ignore[arg-type]

    if soup.body:
        walk(soup.body)
    else:
        walk(soup)
    return _normalize_ws(" ".join(parts))


def looks_like_paywall(html: str, visible_text: str = "") -> bool:
    """Heuristic soft/hard paywall detector (nav chrome alone is not enough)."""
    blob = f"{html or ''}\n{visible_text or ''}".lower()
    if not blob.strip():
        return False
    text_hits = (
        "subscribe to continue",
        "subscribe to read",
        "subscribe to unlock",
        "become a subscriber",
        "this article is for subscribers",
        "subscribers only",
        "already a subscriber",
        "create a free account to continue",
        "sign in to continue reading",
        "to continue reading",
        "metered paywall",
    )
    if any(hit in blob for hit in text_hits):
        return True
    if "isaccessibleforfree" in blob.replace(" ", "") and (
        '"isaccessibleforfree":false' in blob.replace(" ", "")
        or '"isaccessibleforfree": false' in blob
    ):
        return True
    # Common paywall widget / gate class/id tokens.
    gate_tokens = (
        "paywall",
        "subscribe-gate",
        "subscription-gate",
        "piano-offer",
        "tp-modal",
        "reg-wall",
        "regwall",
        "subscriber-only",
    )
    return any(token in blob for token in gate_tokens)


def compute_concealment_risk(
    concealment: ConcealmentSignals | None,
    *,
    ratio_alert: float = 0.15,
    words_min: int = 20,
) -> float:
    """Risk from instruction / GEO IPI only.

    Practical split (feeds retrieve permissions):
    - Hidden / structured / promotional-visible IPI → ``>= 0.9`` (reject band)
    - Visible instructional quotes without site promotion → ``0.55`` (downrank)
    - Hidden GEO rhetoric alone → ``0.55`` (downrank)

    CSS hidden-ratio, offscreen chrome, and structured markup alone are ignored:
    paywall gates and news-site nav routinely inflate those without being GEO.
    ``ratio_alert`` / ``words_min`` kept for call-site compatibility.
    """
    _ = (ratio_alert, words_min)
    if concealment is None:
        return 0.0
    flags = set(concealment.flags)
    risk = 0.0
    # Attack-class IPI: concealed channel or visible directives that promote the host.
    if "hidden_instruction_pattern" in flags:
        risk = max(risk, 0.95)
    if "structured_concealed" in flags and (
        "hidden_instruction_pattern" in flags or "promotional_instruction_pattern" in flags
    ):
        risk = max(risk, 0.95)
    if (
        "visible_instruction_pattern" in flags
        and "promotional_instruction_pattern" in flags
    ):
        risk = max(risk, 0.95)
    elif "visible_instruction_pattern" in flags:
        # Educational / explanatory quotes of PI wording — demote, do not auto-reject.
        risk = max(risk, 0.55)
    if "hidden_geo_rhetoric" in flags:
        risk = max(risk, 0.55)
    return min(1.0, risk)
