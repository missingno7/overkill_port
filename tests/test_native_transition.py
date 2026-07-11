"""The vertical screen SQUEEZE/UNSQUEEZE transition (5C46/5960) -- VM-free compositor tests.

The level-start transition (1010:5C9A -> 5C46, called from 971D) draws the level screen with a growing
vertical extent [5901] (6 -> full, +2/retrace): the image unsqueezes open from a thin centre band.
These tests confirm the native `vertical_squeeze_frame` scales into a centred band of the requested
height and matches at the endpoints, and that the height sweep matches the 5C46/5960 [5901] cadence.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.transition import (
    SCREEN_H,
    SCREEN_W,
    SQUEEZE_MIN_H,
    squeeze_heights,
    vertical_squeeze_frame,
)


def _frame():
    # a distinct value per source row so we can see where rows land
    return np.tile(np.arange(SCREEN_H, dtype=np.uint8).reshape(-1, 1) % 16, (1, SCREEN_W))


def test_full_height_is_identity():
    f = _frame()
    assert np.array_equal(vertical_squeeze_frame(f, SCREEN_H), f)
    assert np.array_equal(vertical_squeeze_frame(f, SCREEN_H + 50), f)


def test_zero_height_is_blank():
    assert vertical_squeeze_frame(_frame(), 0).sum() == 0


def test_band_is_centred_and_the_right_height():
    f = _frame()
    h = 40
    out = vertical_squeeze_frame(f, h)
    lit_rows = np.where(out.any(axis=1))[0]
    # the band occupies exactly `h` rows (minus any that scaled to the all-zero source row 0/16k)
    top = (SCREEN_H - h) // 2
    assert out[:top].sum() == 0 and out[top + h:].sum() == 0        # only the centred band is drawn
    assert lit_rows.min() >= top and lit_rows.max() < top + h


def test_height_sweep_matches_5901_cadence():
    up = squeeze_heights(opening=True)
    assert up[0] == SQUEEZE_MIN_H and up[-1] == SCREEN_H
    assert all(b - a == 2 for a, b in zip(up, up[1:]))             # 5C46: [5901] += 2
    assert squeeze_heights(opening=False) == up[::-1]              # 5960: the reverse
