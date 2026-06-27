"""LayerRenderer: palette colorize correctness + the colorized-frame cache."""
from __future__ import annotations

import pytest

from overkill.native_video.frame import RenderSnapshot, SceneKind
from overkill.native_video.renderer import LayerRenderer


def _np():
    try:
        import numpy as np
        return np
    except Exception:  # pragma: no cover
        pytest.skip("numpy not installed")


_PAL = tuple((i, 2 * i, 3 * i) for i in range(16))


def _snap(np, frame_id, *, version, palette_version=1, fill=0):
    return RenderSnapshot(
        frame_id=frame_id, timestamp=0.0, scene_kind=SceneKind.GAMEPLAY,
        composed_indices=np.full((200, 320), fill, dtype=np.uint8), composed_version=version,
        palette=_PAL, palette_version=palette_version, scroll_cursor=0,
    )


def test_colorizes_indices_through_palette():
    np = _np()
    r = LayerRenderer()
    rgb, cached = r.render(_snap(np, 1, version=1, fill=5))
    assert not cached and rgb.shape == (200, 320, 3)
    assert tuple(rgb[10, 10]) == _PAL[5]


def test_same_version_is_served_from_cache():
    np = _np()
    r = LayerRenderer()
    a, c0 = r.render(_snap(np, 1, version=7))
    b, c1 = r.render(_snap(np, 2, version=7))  # different frame_id, SAME content version
    assert c0 is False and c1 is True
    assert b is a  # identical buffer, no re-colorize
    assert r.cache_hits == 1 and r.cache_misses == 1


def test_new_version_invalidates_cache():
    np = _np()
    r = LayerRenderer()
    r.render(_snap(np, 1, version=1))
    _, cached = r.render(_snap(np, 2, version=2))  # content changed
    assert cached is False
    assert r.cache_misses == 2


def test_palette_version_change_invalidates_cache():
    np = _np()
    r = LayerRenderer()
    r.render(_snap(np, 1, version=1, palette_version=1))
    _, cached = r.render(_snap(np, 1, version=1, palette_version=2))  # e.g. a fade
    assert cached is False


def test_palette_lut_cached_by_version():
    np = _np()
    r = LayerRenderer()
    lut1 = r.palette_lut(_snap(np, 1, version=1, palette_version=3))
    lut2 = r.palette_lut(_snap(np, 2, version=2, palette_version=3))
    assert lut1 is lut2  # same palette_version -> same cached LUT array


def test_camera_shift_overlays_playfield_and_preserves_hud():
    np = _np()
    from overkill.native_video.page_raster import PLAYFIELD_X0, PLAYFIELD_Y0
    r = LayerRenderer()
    snap = RenderSnapshot(
        frame_id=1, timestamp=0.0, scene_kind=SceneKind.GAMEPLAY,
        composed_indices=np.full((200, 320), 1, dtype=np.uint8), composed_version=1,
        palette=_PAL, palette_version=1, scroll_cursor=0,
        playfield_indices=np.full((200, 320), 2, dtype=np.uint8), playfield_version=1,
    )
    out, cached = r.render(snap, camera_shift_rows=3)
    assert cached is False
    # inside the playfield rect -> the (shifted) playfield sublayer (index 2)
    assert tuple(out[PLAYFIELD_Y0 + 50, PLAYFIELD_X0 + 50]) == _PAL[2]
    # outside the rect (HUD/border) -> the composed baseline (index 1), untouched
    assert tuple(out[0, 300]) == _PAL[1]
    assert tuple(out[198, 300]) == _PAL[1]


def test_camera_shift_moves_content_down_with_edge_fill():
    np = _np()
    from overkill.native_video.page_raster import PLAYFIELD_X0, PLAYFIELD_Y0
    r = LayerRenderer()
    playfield = np.full((200, 320), 2, dtype=np.uint8)
    playfield[PLAYFIELD_Y0, :] = 7  # a marker on the top row of the playfield rect
    snap = RenderSnapshot(
        frame_id=1, timestamp=0.0, scene_kind=SceneKind.GAMEPLAY,
        composed_indices=np.full((200, 320), 1, dtype=np.uint8), composed_version=1,
        palette=_PAL, palette_version=1, scroll_cursor=0,
        playfield_indices=playfield, playfield_version=1,
    )
    out, _ = r.render(snap, camera_shift_rows=2)
    # the marker row moved down by 2; the revealed top strip is edge-filled with it
    assert tuple(out[PLAYFIELD_Y0 + 2, PLAYFIELD_X0]) == _PAL[7]
    assert tuple(out[PLAYFIELD_Y0 + 0, PLAYFIELD_X0]) == _PAL[7]
    assert tuple(out[PLAYFIELD_Y0 + 3, PLAYFIELD_X0]) == _PAL[2]
