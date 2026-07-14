import io
import time

from anti_geo.progress import NullProgress, ProgressBar, _fmt_duration, make_progress


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_fmt_duration():
    assert _fmt_duration(None) == "--:--"
    assert _fmt_duration(9) == "9s"
    assert _fmt_duration(75) == "1m15s"
    assert _fmt_duration(3661) == "1h01m"


def test_progress_bar_overwrites_same_line():
    buf = _TtyStringIO()
    bar = ProgressBar(label="Test", stream=buf, unit="verified", min_draw_interval_s=0.0)
    bar.set_counts(0, 50, status="start")
    time.sleep(0.05)
    bar.set_counts(12, 50, status="mid")
    bar.close(final_status="done", fill=False)
    out = buf.getvalue()
    assert "\r\033[2K" in out
    assert out.count("\n") == 1  # only the final close newline
    assert "12/50 verified" in out
    assert out.endswith("\n")


def test_null_progress_is_silent():
    prog = NullProgress()
    prog.set_counts(3, 50, status="x")
    prog.close("y")


def test_make_progress_respects_enabled_flag():
    assert isinstance(make_progress(enabled=False), NullProgress)
    buf = io.StringIO()
    bar = make_progress(enabled=True, stream=buf)
    assert isinstance(bar, ProgressBar)
