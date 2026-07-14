"""Lightweight stderr progress / ETA for long CLI runs (no third-party deps)."""

from __future__ import annotations

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


class Progress(Protocol):
    def add_work(self, n: int) -> None: ...
    def advance(self, n: int = 1, *, status: str = "") -> None: ...
    def set_status(self, status: str) -> None: ...
    def close(self, final_status: str | None = None) -> None: ...


@dataclass
class NullProgress:
    """No-op progress (tests / --no-progress / non-TTY default)."""

    def add_work(self, n: int) -> None:
        return None

    def advance(self, n: int = 1, *, status: str = "") -> None:
        return None

    def set_status(self, status: str) -> None:
        return None

    def close(self, final_status: str | None = None) -> None:
        return None


@dataclass
class ProgressBar:
    """Single-line TTY progress bar with moving-average ETA."""

    label: str = "Progress"
    stream: TextIO = field(default_factory=lambda: sys.stderr)
    width: int = 28
    min_draw_interval_s: float = 0.08
    _done: int = 0
    _total: int = 0
    _status: str = ""
    _t0: float = field(default_factory=time.monotonic)
    _last_draw: float = 0.0
    _closed: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_work(self, n: int) -> None:
        if n <= 0:
            return
        with self._lock:
            if self._closed:
                return
            self._total += n
            self._draw(force=True)

    def advance(self, n: int = 1, *, status: str = "") -> None:
        with self._lock:
            if self._closed:
                return
            if status:
                self._status = status
            self._done += max(0, n)
            if self._total < self._done:
                self._total = self._done
            self._draw()

    def set_status(self, status: str) -> None:
        with self._lock:
            if self._closed:
                return
            self._status = status
            self._draw(force=True)

    def close(self, final_status: str | None = None) -> None:
        with self._lock:
            if self._closed:
                return
            if final_status:
                self._status = final_status
            if self._total > 0:
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

    def _draw(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_draw) < self.min_draw_interval_s:
            return
        self._last_draw = now
        elapsed = now - self._t0
        if self._total > 0:
            frac = min(1.0, self._done / self._total)
            filled = int(round(self.width * frac))
            bar = "█" * filled + "░" * (self.width - filled)
            pct = f"{frac * 100:5.1f}%"
            counts = f"{self._done}/{self._total}"
        else:
            bar = "░" * self.width
            pct = "  --%"
            counts = f"{self._done}/?"
        eta = _fmt_duration(self._eta_s())
        status = f"  {self._status}" if self._status else ""
        line = (
            f"\r{self.label} [{bar}] {pct} {counts}  "
            f"elapsed {_fmt_duration(elapsed)}  ETA {eta}{status}"
        )
        # Keep one terminal line; trim overlong status.
        if len(line) > 118:
            line = line[:115] + "..."
        try:
            self.stream.write(line)
            self.stream.flush()
        except Exception:
            pass


def make_progress(
    *,
    enabled: bool | None = None,
    label: str = "Anti-GEO",
    stream: TextIO | None = None,
) -> Progress:
    """Create a progress reporter. ``enabled=None`` → on only when stderr is a TTY."""
    out = stream if stream is not None else sys.stderr
    if enabled is None:
        enabled = bool(getattr(out, "isatty", lambda: False)())
    if not enabled:
        return NullProgress()
    return ProgressBar(label=label, stream=out)
