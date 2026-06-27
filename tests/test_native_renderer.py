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
        playfield_indices=np.full((200, 320), fill, dtype=np.uint8), playfield_version=version,
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
