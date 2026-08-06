"""URL rematch helpers used by demo/label_sheet_anti_geo.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "label_sheet_anti_geo",
    _ROOT / "demo" / "label_sheet_anti_geo.py",
)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)

_match_cite_row = _mod._match_cite_row
_norm_url = _mod._norm_url


def _fake_row(url: str, *, source_url: str | None = None):
    src = source_url if source_url is not None else url
    return SimpleNamespace(
        url=url,
        single_page=SimpleNamespace(source=SimpleNamespace(url=src)),
    )


def test_match_cite_row_percent_parens_vs_decoded():
    sheet = (
        "https://www.thelancet.com/journals/lancet/article/"
        "PIIS0140-6736%2803%2914792-7/fulltext"
    )
    decoded = (
        "https://www.thelancet.com/journals/lancet/article/"
        "PIIS0140-6736(03)14792-7/fulltext"
    )
    rows = [
        _fake_row("https://www.sleepfoundation.org/best-mattress/best-mattress-for-back-pain"),
        _fake_row(decoded, source_url=decoded),
        _fake_row("https://www.rtings.com/mattress/reviews/best/back-pain"),
    ]
    hit = _match_cite_row(rows, sheet, index=1)
    assert hit is rows[1]
    assert _norm_url(sheet) == _norm_url(decoded)


def test_match_cite_row_index_fallback_when_url_unrelated():
    rows = [_fake_row("https://a.example/x"), _fake_row("https://b.example/y")]
    hit = _match_cite_row(rows, "https://other.example/z", index=1)
    assert hit is rows[1]
    assert _match_cite_row(rows, "https://other.example/z") is None
