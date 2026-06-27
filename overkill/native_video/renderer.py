"""The native backend's layer renderer (it owns colorize + compose, with caches).

The backend does not receive a finished RGB frame — it receives a
:class:`RenderSnapshot` of semantic, palette-independent layers and renders the
image itself here. Cache model (tailored to OVERKILL):

  * **palette LUT cache** — the 16-colour palette as an array, keyed by
    ``palette_version`` (fixed for OVERKILL, but the structure supports fades).
  * **colorized-frame cache** — the composed RGB keyed by
    ``(playfield_version, palette_version)``. When the same source snapshot is
    presented multiple times (held presents at a high refresh over a ~70 Hz
    source) the key is unchanged, so the colorize is served from cache — the main
    high-refresh win. A new game tick bumps ``playfield_version`` → re-render.

Sprite/HUD/effect compositing and interpolation hang off ``render`` as those layers
are lifted; today the playfield indexed layer is the grounded one. Pure NumPy.
"""
from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

import numpy as np

from overkill.native_video import page_raster
from overkill.native_video.frame import RenderSnapshot
from overkill.native_video.page_raster import (
    PLAYFIELD_H,
    PLAYFIELD_W,
    PLAYFIELD_X0,
    PLAYFIELD_Y0,
)


class LayerRenderer:
    """Colorize + compose the semantic layers into the presented RGB, with caches."""

    def __init__(self) -> None:
        self._palette_luts: Dict[int, np.ndarray] = {}
        self._cache_key: Optional[Tuple[int, int]] = None
        self._cache_rgb: Optional[np.ndarray] = None
        self.cache_hits = 0
        self.cache_misses = 0
        self.last_colorize_ms = 0.0

    def palette_lut(self, snapshot: RenderSnapshot) -> np.ndarray:
        """The ``(16,3)`` palette array for ``snapshot``, cached by palette_version."""
        lut = self._palette_luts.get(snapshot.palette_version)
        if lut is None:
            lut = np.array(snapshot.palette, dtype=np.uint8)
            self._palette_luts[snapshot.palette_version] = lut
        return lut

    def _render_composed(self, snapshot: RenderSnapshot) -> Tuple[np.ndarray, bool]:
        """Colorize the composed baseline (cached by ``(composed_version, palette_version)``)."""
        key = (snapshot.composed_version, snapshot.palette_version)
        if key == self._cache_key and self._cache_rgb is not None:
            self.cache_hits += 1
            return self._cache_rgb, True

        self.cache_misses += 1
        t0 = time.perf_counter()
        lut = self.palette_lut(snapshot)
        rgb = page_raster.colorize(snapshot.composed_indices, lut)
        self.last_colorize_ms = (time.perf_counter() - t0) * 1000.0

        self._cache_key = key
        self._cache_rgb = rgb
        return rgb, False

    def render(self, snapshot: RenderSnapshot, *, camera_shift_rows: int = 0) -> Tuple[np.ndarray, bool]:
        """Render ``snapshot`` to ``(H,W,3)`` RGB. Returns ``(rgb, from_cache)``.

        ``camera_shift_rows == 0`` (the source-boundary / held case) renders the
        composed baseline exactly (faithful parity) and may serve from cache.
        ``camera_shift_rows > 0`` overlays the scrolling playfield sublayer shifted
        down by that many rows (camera/scroll interpolation between source ticks);
        the result is a fresh frame (never cached) and leaves the HUD/border intact.
        """
        base, from_cache = self._render_composed(snapshot)
        if camera_shift_rows <= 0 or snapshot.playfield_indices is None:
            return base, from_cache

        lut = self.palette_lut(snapshot)
        out = base.copy()
        y0, y1 = PLAYFIELD_Y0, PLAYFIELD_Y0 + PLAYFIELD_H
        x0, x1 = PLAYFIELD_X0, PLAYFIELD_X0 + PLAYFIELD_W
        rect = snapshot.playfield_indices[y0:y1, x0:x1]
        k = min(int(camera_shift_rows), rect.shape[0])
        shifted = np.empty_like(rect)
        shifted[k:] = rect[: rect.shape[0] - k]
        shifted[:k] = rect[0:1]  # edge-replicate the revealed top strip (≤k rows)
        out[y0:y1, x0:x1] = lut[shifted]
        return out, False
