import io
import time

from anti_geo.progress import NullProgress, ProgressBar, _fmt_duration, make_progress


def test_fmt_duration():
    assert _fmt_duration(None) == "--:--"
    assert _fmt_duration(9) == "9s"
    assert _fmt_duration(75) == "1m15s"
    assert _fmt_duration(3661) == "1h01m"


def test_progress_bar_draws_and_eta():
    buf = io.StringIO()
    bar = ProgressBar(label="Test", stream=buf, min_draw_interval_s=0.0)
    bar.add_work(4)
    bar.advance(1, status="step a")
    time.sleep(0.05)
    bar.advance(1, status="step b")
    bar.close(final_status="done")
    out = buf.getvalue()
    assert "Test [" in out
    assert "ETA" in out
    assert "done" in out
    assert out.endswith("\n")


def test_null_progress_is_silent():
    prog = NullProgress()
    prog.add_work(10)
    prog.advance(3, status="x")
    prog.close("y")


def test_make_progress_respects_enabled_flag():
    assert isinstance(make_progress(enabled=False), NullProgress)
    buf = io.StringIO()
    bar = make_progress(enabled=True, stream=buf)
    assert isinstance(bar, ProgressBar)
