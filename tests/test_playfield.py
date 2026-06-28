"""Unit tests for the native playfield composer (VM-free).

Byte-exact-vs-live validation is in ``overkill/probes/verify_playfield_compose.py``
(30/30 L2 frames); these cover the layered model -- ``playfield = background plate +
sprite layer`` -- headlessly.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.frame import SnapshotSprite, SpriteBlock
from overkill.native_video.page_raster import PLAYFIELD_Y0, PRESENT_ROW_BYTES
from overkill.native_video.playfield import compose_playfield_indices


def _sprite(di, pixels, opaque):
    return SnapshotSprite(1, 2, 0, di, (SpriteBlock(di, pixels, opaque),))


def test_sprites_compose_over_background_plate():
    bg = np.zeros((200, 320), dtype=np.uint8)
    bg[PLAYFIELD_Y0, 0] = 7  # a background star pixel at x=0
    # a 1x2 opaque sprite two source bytes in -> screen x=4
    spr = _sprite(0x4000 + 2, np.full((1, 2), 3, np.uint8), np.ones((1, 2), bool))
    out = compose_playfield_indices(bg, [spr], cursor=0x4000)
    assert out[PLAYFIELD_Y0, 0] == 7         # background star preserved (no sprite there)
    assert out[PLAYFIELD_Y0, 4] == 3         # sprite composited at x=4
    assert out[PLAYFIELD_Y0, 5] == 3


def test_transparent_sprite_pixels_keep_the_background():
    bg = np.zeros((200, 320), dtype=np.uint8)
    bg[PLAYFIELD_Y0, 0] = 9                   # star directly under the sprite's left pixel
    spr = _sprite(0x4000, np.array([[1, 2]], np.uint8), np.array([[False, True]]))
    out = compose_playfield_indices(bg, [spr], cursor=0x4000)
    assert out[PLAYFIELD_Y0, 0] == 9         # transparent sprite pixel -> star shows through
    assert out[PLAYFIELD_Y0, 1] == 2         # opaque sprite pixel -> sprite


def test_does_not_mutate_the_input_background():
    bg = np.zeros((200, 320), dtype=np.uint8)
    bg[PLAYFIELD_Y0, 0] = 7
    before = bg.copy()
    spr = _sprite(0x4000, np.full((2, 2), 5, np.uint8), np.ones((2, 2), bool))
    out = compose_playfield_indices(bg, [spr], cursor=0x4000)
    assert np.array_equal(bg, before)        # caller's plate is untouched
    assert out is not bg


def test_no_sprites_passes_the_plate_through():
    bg = np.zeros((200, 320), dtype=np.uint8)
    bg[10, 20] = 4
    out = compose_playfield_indices(bg, [], cursor=0x4000)
    assert out[10, 20] == 4 and out is not bg


def test_di_shift_translates_the_sprite_layer_over_a_fixed_plate():
    bg = np.zeros((200, 320), dtype=np.uint8)
    spr = _sprite(0x4000, np.full((1, 2), 6, np.uint8), np.ones((1, 2), bool))
    a = compose_playfield_indices(bg, [spr], cursor=0x4000, di_shift=0)
    b = compose_playfield_indices(bg, [spr], cursor=0x4000, di_shift=PRESENT_ROW_BYTES)
    assert a[PLAYFIELD_Y0, 0] == 6           # unshifted: row 0
    assert b[PLAYFIELD_Y0 + 1, 0] == 6       # shifted one source row -> next screen row


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
