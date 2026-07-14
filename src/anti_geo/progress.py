"""Lightweight stderr progress / ETA for long CLI runs (no third-party deps)."""

from __future__ import annotations

import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import TextIO, Protocol


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "--:--"
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _term_width(stream: TextIO) -> int:
    try:
        return max(40, shutil.get_terminal_size(fallback=(100, 24)).columns)
    except Exception:
        return 100


class Progress(Protocol):
    def set_counts(self, done: int, total: int, *, status: str = "") -> None: ...
    def set_status(self, status: str) -> None: ...
    def close(self, final_status: str | None = None, *, fill: bool = False) -> None: ...


@dataclass
class NullProgress:
    """No-op progress (tests / --no-progress / non-TTY default)."""

    def set_counts(self, done: int, total: int, *, status: str = "") -> None:
        return None

    def set_status(self, status: str) -> None:
        return None

    def close(self, final_status: str | None = None, *, fill: bool = False) -> None:
        return None


@dataclass
class ProgressBar:
    """Single-line TTY progress bar that overwrites itself in place.

    Prefer ``set_counts`` with a fixed total (e.g. verified / max_verified)
    so the percentage only moves forward.
    """

    label: str = "Progress"
    stream: TextIO = field(default_factory=lambda: sys.stderr)
    width: int = 28
    min_draw_interval_s: float = 0.12
    unit: str = ""
    _done: int = 0
    _total: int = 0
    _status: str = ""
    _t0: float = field(default_factory=time.monotonic)
    _last_draw: float = 0.0
    _last_rendered: str = ""
    _closed: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _isatty: bool = field(init=False, default=True)

    def __post_init__(self) -> None:
        self._isatty = bool(getattr(self.stream, "isatty", lambda: False)())

    def set_counts(self, done: int, total: int, *, status: str = "") -> None:
        with self._lock:
            if self._closed:
                return
            counts_changed = done != self._done or total != self._total
            self._total = max(0, total)
            self._done = max(0, min(done, self._total) if self._total else done)
            if status:
                self._status = status
            # Always redraw when counts change; status-only uses the throttle.
            self._draw(force=counts_changed)

    def set_status(self, status: str) -> None:
        with self._lock:
            if self._closed:
                return
            if status == self._status:
                return
            self._status = status
            self._draw(force=False)

    def close(self, final_status: str | None = None, *, fill: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            if final_status:
                self._status = final_status
            if fill and self._total > 0:
                self._done = self._total
            self._draw(force=True)
            try:
                self.stream.write("\n")
                self.stream.flush()
            except Exception:
                pass
            self._closed = True

    def _eta_s(self) -> float | None:
        if self._done <= 0 or self._total <= 0 or self._done >= self._total:
            return 0.0 if self._done >= self._total > 0 else None
        elapsed = time.monotonic() - self._t0
        rate = self._done / elapsed if elapsed > 0 else 0.0
        if rate <= 0:
            return None
        return (self._total - self._done) / rate

    def _render_line(self) -> str:
        elapsed = time.monotonic() - self._t0
        unit = f" {self.unit}" if self.unit else ""
        if self._total > 0:
            frac = min(1.0, self._done / self._total)
            filled = int(round(self.width * frac))
            bar = "█" * filled + "░" * (self.width - filled)
            pct = f"{frac * 100:5.1f}%"
            counts = f"{self._done}/{self._total}{unit}"
        else:
            bar = "░" * self.width
            pct = "  --%"
            counts = f"{self._done}/?{unit}"
        eta = _fmt_duration(self._eta_s())
        status = f"  {self._status}" if self._status else ""
        line = (
            f"{self.label} [{bar}] {pct} {counts}  "
            f"elapsed {_fmt_duration(elapsed)}  ETA {eta}{status}"
        )
        # Keep to one terminal row so wrapping never looks like a new bar.
        max_cols = _term_width(self.stream) - 1
        if len(line) > max_cols:
            line = line[: max(0, max_cols - 3)] + "..."
        return line

    def _draw(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_draw) < self.min_draw_interval_s:
            return
        line = self._render_line()
        if not force and line == self._last_rendered:
            return
        self._last_draw = now
        self._last_rendered = line
        try:
            if self._isatty:
                # CR + erase line → rewrite same row (no spam).
                self.stream.write(f"\r\033[2K{line}")
            else:
                # Non-TTY (piped/logs): rare newline updates only on force.
                if force:
                    self.stream.write(line + "\n")
            self.stream.flush()
        except Exception:
            pass


def make_progress(
    *,
    enabled: bool | None = None,
    label: str = "Anti-GEO",
    unit: str = "verified",
    stream: TextIO | None = None,
) -> Progress:
    """Create a progress reporter. ``enabled=None`` → on only when stderr is a TTY."""
    out = stream if stream is not None else sys.stderr
    if enabled is None:
        enabled = bool(getattr(out, "isatty", lambda: False)())
    if not enabled:
        return NullProgress()
    return ProgressBar(label=label, stream=out, unit=unit)
