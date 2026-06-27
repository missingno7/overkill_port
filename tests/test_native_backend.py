"""NativeOverkillVideoBackend: renders the snapshot itself, with caching, and a
decoupled present clock."""
from __future__ import annotations

import pytest

from overkill.native_video.backend import NativeOverkillVideoBackend
from overkill.native_video.frame import BackendConfig, RenderSnapshot, SceneKind


def _np():
    try:
        import numpy as np
        return np
    except Exception:  # pragma: no cover
        pytest.skip("numpy not installed")


_PAL = tuple((i * 16, i * 8, i * 4) for i in range(16))


def _frame(np, frame_id: int, ts: float, *, version: int = None, fill: int = 0):
    indices = np.full((200, 320), fill, dtype=np.uint8)
    return RenderSnapshot(
        frame_id=frame_id, timestamp=ts, scene_kind=SceneKind.GAMEPLAY,
        composed_indices=indices, composed_version=frame_id if version is None else version,
        palette=_PAL, palette_version=1, scroll_cursor=0x1000,
    )


def test_present_renders_snapshot_to_rgb():
    np = _np()
    be = NativeOverkillVideoBackend()
    f = _frame(np, 1, 0.0, fill=3)
    be.submit_source_frame(f)
    out = be.present(0.0)
    # The backend OWNS rendering: it colorizes the indexed layer via the palette
    # (it does not receive or pass through an RGB frame).
    assert out.rgb.shape == (200, 320, 3)
    assert tuple(out.rgb[0, 0]) == _PAL[3]
    assert out.source_frame_id == 1 and out.alpha == 0.0 and out.from_cache is False


def test_held_presents_hit_the_render_cache():
    np = _np()
    be = NativeOverkillVideoBackend()
    be.submit_source_frame(_frame(np, 1, 0.0))
    first = be.present(0.0)
    assert first.from_cache is False
    for i in range(1, 4):  # same snapshot presented again (held at high refresh)
        out = be.present(i / 240.0)
        assert out.from_cache is True
        assert out.rgb is first.rgb  # served from cache, not re-colorized
    d = be.diagnostics()
    assert d.cache_misses == 1 and d.cache_hits == 3 and d.frame_hold_count == 3


def test_new_tick_invalidates_cache_and_clears_hold():
    np = _np()
    be = NativeOverkillVideoBackend()
    be.submit_source_frame(_frame(np, 1, 0.0))
    be.present(0.0)
    be.submit_source_frame(_frame(np, 2, 1 / 70.0, fill=9))
    out = be.present(1 / 70.0)
    assert out.source_frame_id == 2 and out.held is False and out.from_cache is False
    assert tuple(out.rgb[0, 0]) == _PAL[9]


def test_present_before_submit_is_explicit():
    with pytest.raises(RuntimeError):
        NativeOverkillVideoBackend().present(0.0)


def test_unimplemented_interpolation_flags_raise():
    for flag in ("object_interpolation", "smooth_palette_fades", "smooth_transitions"):
        with pytest.raises(NotImplementedError):
            NativeOverkillVideoBackend(BackendConfig(**{flag: True}))


def _interp_frame(np, frame_id, ts, cursor, *, composed_fill, playfield_fill):
    return RenderSnapshot(
        frame_id=frame_id, timestamp=ts, scene_kind=SceneKind.GAMEPLAY,
        composed_indices=np.full((200, 320), composed_fill, dtype=np.uint8), composed_version=frame_id,
        palette=_PAL, palette_version=1, scroll_cursor=cursor,
        playfield_indices=np.full((200, 320), playfield_fill, dtype=np.uint8), playfield_version=frame_id,
    )


def test_camera_interpolation_is_implemented_and_parity_holds_at_boundary():
    np = _np()
    be = NativeOverkillVideoBackend(BackendConfig(camera_interpolation=True))  # no longer raises
    be.submit_source_frame(_interp_frame(np, 1, 0.0, 0x4000, composed_fill=1, playfield_fill=2))
    be.submit_source_frame(_interp_frame(np, 2, 1 / 70.0, 0x4000 - 4 * 0x68, composed_fill=3, playfield_fill=4))
    # present exactly at the latest tick's arrival -> alpha 0 -> faithful composed, no shift
    out = be.present(1 / 70.0)
    assert out.alpha == 0.0 and be.diagnostics().camera_interpolation_active is False
    assert tuple(out.rgb[100, 100]) == _PAL[3]  # composed of the latest tick, not the playfield


def test_camera_interpolation_shifts_the_playfield_between_ticks():
    np = _np()
    be = NativeOverkillVideoBackend(BackendConfig(camera_interpolation=True))
    be.submit_source_frame(_interp_frame(np, 1, 0.0, 0x4000, composed_fill=1, playfield_fill=2))
    be.submit_source_frame(_interp_frame(np, 2, 1 / 70.0, 0x4000 - 4 * 0x68, composed_fill=3, playfield_fill=4))
    # halfway to the next predicted tick: alpha ~0.5, 4-row/tick scroll -> shift 2 rows
    out = be.present(1 / 70.0 + (1 / 70.0) * 0.5)
    d = be.diagnostics()
    assert d.camera_interpolation_active is True and 0.4 < d.interpolation_alpha < 0.6
    assert tuple(out.rgb[100, 100]) == _PAL[4]   # playfield sublayer overlaid in the rect
    assert tuple(out.rgb[2, 300]) == _PAL[3]     # HUD (outside rect) stays the composed baseline


def test_fps_and_age_diagnostics():
    np = _np()
    be = NativeOverkillVideoBackend()
    be.submit_source_frame(_frame(np, 1, 0.0))
    be.submit_source_frame(_frame(np, 2, 1 / 70.0))
    be.present(1 / 70.0 + 0.002)
    d = be.diagnostics()
    assert round(d.source_fps) == 70
    assert d.source_snapshot_age_ms == pytest.approx(2.0, abs=0.01)
