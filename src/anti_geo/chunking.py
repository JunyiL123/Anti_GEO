from __future__ import annotations

import re

from anti_geo.models import FetchResult


CHUNK_MIN_WORDS = 30
CHUNK_MAX_WORDS = 400


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n{2,}|(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return [p.strip() for p in parts if len(p.split()) >= CHUNK_MIN_WORDS]


def chunk_from_text(url: str, text: str, title: str = "") -> list[tuple[str, str]]:
    """Return (chunk_id, text) pairs from plain text."""
    chunks: list[tuple[str, str]] = []
    paragraphs = _split_paragraphs(text)
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]
    if title and paragraphs:
        first = paragraphs[0]
        if title.lower() not in first.lower()[:80]:
            paragraphs[0] = f"{title}. {first}"
    for i, para in enumerate(paragraphs):
        words = para.split()
        if len(words) <= CHUNK_MAX_WORDS:
            chunks.append((f"p{i}", para))
            continue
        for j in range(0, len(words), CHUNK_MAX_WORDS):
            chunks.append((f"p{i}_{j // CHUNK_MAX_WORDS}", " ".join(words[j : j + CHUNK_MAX_WORDS])))
    if not chunks and text.strip():
        chunks.append(("full", text.strip()[: CHUNK_MAX_WORDS * 6]))
    return chunks


def chunk_from_fetch(fetch: FetchResult) -> list[tuple[str, str]]:
    if fetch.segments:
        chunks: list[tuple[str, str]] = []
        for seg in fetch.segments:
            local_chunks = chunk_from_text(fetch.final_url or fetch.url, seg.text)
            for local_id, text in local_chunks:
                chunk_id = f"{seg.role}__{seg.segment_id}_{local_id}"
                chunks.append((chunk_id, text))
        if chunks:
            return chunks
    return chunk_from_text(fetch.final_url or fetch.url, fetch.text, fetch.title)
