"""NativeOverkillVideoBackend: passthrough parity + clock decoupling + diagnostics."""
from __future__ import annotations

import pytest

from overkill.native_video.backend import NativeOverkillVideoBackend
from overkill.native_video.frame import BackendConfig, NativeSourceFrame


def _np():
    try:
        import numpy as np
        return np
    except Exception:  # pragma: no cover
        pytest.skip("numpy not installed")


def _frame(np, frame_id: int, ts: float, fill: int = 0, cursor: int = 0x1000):
    rgb = np.full((200, 320, 3), fill, dtype=np.uint8)
    return NativeSourceFrame(frame_id=frame_id, timestamp=ts, playfield_rgb=rgb, source_cursor=cursor)


def test_present_holds_latest_source_frame_baseline():
    np = _np()
    be = NativeOverkillVideoBackend()
    f = _frame(np, 1, 0.0, fill=7)
    be.submit_source_frame(f)
    out = be.present(0.0)
    # Source-boundary parity: at the frame's arrival the presented RGB *is* the
    # submitted faithful baseline (same buffer, no interpolation).
    assert out.rgb is f.playfield_rgb
    assert out.source_frame_id == 1 and out.alpha == 0.0


def test_present_decoupled_from_source_cadence():
    np = _np()
    be = NativeOverkillVideoBackend()
    be.submit_source_frame(_frame(np, 1, 0.0, fill=1))
    # Present many times (240 Hz) with no new source frame: each holds frame 1.
    for i in range(1, 9):
        out = be.present(i / 240.0)
        assert out.source_frame_id == 1
    # 8 re-presents of the same source frame counted as holds (the first present
    # established it, the next 7 are holds).
    assert be.diagnostics().frame_hold_count == 7
    # A new source frame clears the hold on the next present.
    be.submit_source_frame(_frame(np, 2, 9 / 240.0, fill=2))
    out = be.present(9 / 240.0)
    assert out.source_frame_id == 2 and out.held is False


def test_present_before_submit_is_explicit():
    be = NativeOverkillVideoBackend()
    with pytest.raises(RuntimeError):
        be.present(0.0)


def test_unimplemented_interpolation_flags_raise():
    for flag in ("camera_interpolation", "object_interpolation", "smooth_palette_fades"):
        with pytest.raises(NotImplementedError):
            NativeOverkillVideoBackend(BackendConfig(**{flag: True}))


def test_fps_and_age_diagnostics():
    np = _np()
    be = NativeOverkillVideoBackend()
    be.submit_source_frame(_frame(np, 1, 0.0))
    be.submit_source_frame(_frame(np, 2, 1 / 70.0))   # ~70 Hz source cadence
    out = be.present(1 / 70.0 + 0.002)
    d = be.diagnostics()
    assert round(d.source_fps) == 70
    assert d.source_snapshot_age_ms == pytest.approx(2.0, abs=0.01)
    assert out.held is False
