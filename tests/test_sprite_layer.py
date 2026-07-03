"""Unit tests for the native sprite-layer compositor (VM-free).

Byte-exact-vs-live validation is in ``overkill/probes/verify_sprite_layer.py``;
these cover the placement math + compositing headlessly.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.frame import SnapshotSprite, SpriteBlock
from overkill.native_video.page_raster import PLAYFIELD_W, PLAYFIELD_Y0, PRESENT_ROW_BYTES, PRESENT_ROWS
from overkill.native_video.sprite_layer import (
    block_screen_origin,
    composite_sprites,
    paste_block,
    paste_or_inverted_block,
)


def test_block_origin_maps_di_relative_to_cursor():
    # di == cursor -> top-left of the playfield window.
    assert block_screen_origin(0x4000, 0x4000) == (PLAYFIELD_Y0, 0)
    # one source row further on -> next screen row, same column.
    assert block_screen_origin(0x4000 + PRESENT_ROW_BYTES, 0x4000) == (PLAYFIELD_Y0 + 1, 0)
    # two bytes in -> +4 px on the same row (2 px/byte).
    assert block_screen_origin(0x4002, 0x4000) == (PLAYFIELD_Y0, 4)


def test_block_origin_below_cursor_is_negative_row():
    # di below the cursor sits above the window (signed offset, not wrapped huge).
    y, x = block_screen_origin(0x4000 - PRESENT_ROW_BYTES, 0x4000)
    assert y == PLAYFIELD_Y0 - 1 and x == 0


def test_paste_block_composites_only_opaque_pixels():
    screen = np.zeros((200, 320), dtype=np.uint8)
    pixels = np.array([[3, 4, 5, 6]], dtype=np.uint8)
    opaque = np.array([[True, False, True, False]])
    paste_block(screen, di=0x4000, cursor=0x4000, pixels=pixels, opaque=opaque)
    row = PLAYFIELD_Y0
    assert list(screen[row, 0:4]) == [3, 0, 5, 0]  # transparent pixels keep the background


def test_paste_block_clips_above_the_playfield():
    # a block whose top is above y=4 only paints its rows that fall in the playfield.
    screen = np.zeros((200, 320), dtype=np.uint8)
    pixels = np.full((8, 2), 7, dtype=np.uint8)
    opaque = np.ones((8, 2), dtype=bool)
    # place it 4 source rows above the cursor -> origin row PLAYFIELD_Y0 - 4
    paste_block(screen, di=(0x4000 - 4 * PRESENT_ROW_BYTES) & 0xFFFF, cursor=0x4000,
                pixels=pixels, opaque=opaque)
    assert not screen[:PLAYFIELD_Y0].any()              # nothing painted in the HUD band
    assert (screen[PLAYFIELD_Y0:PLAYFIELD_Y0 + 4, 0:2] == 7).all()


def test_paste_block_clips_at_playfield_right_edge():
    screen = np.zeros((200, 320), dtype=np.uint8)
    pixels = np.full((1, 8), 9, dtype=np.uint8)
    opaque = np.ones((1, 8), dtype=bool)
    # near the right edge so part would fall outside x<208
    paste_block(screen, di=0x4000 + (PRESENT_ROW_BYTES - 2), cursor=0x4000, pixels=pixels, opaque=opaque)
    assert not screen[:, PLAYFIELD_W:].any()            # nothing past the playfield width


def test_composite_sprites_draws_all_blocks_in_order():
    screen = np.zeros((200, 320), dtype=np.uint8)
    spr = SnapshotSprite(
        identity=1, sprite_id=2, anim_phase=0, screen_di=0x4000,
        blocks=(
            SpriteBlock(0x4000, np.full((2, 2), 1, np.uint8), np.ones((2, 2), bool)),
            SpriteBlock(0x4000 + 4 * PRESENT_ROW_BYTES, np.full((2, 2), 2, np.uint8), np.ones((2, 2), bool)),
        ),
    )
    composite_sprites(screen, [spr], cursor=0x4000)
    assert screen[PLAYFIELD_Y0, 0] == 1
    assert screen[PLAYFIELD_Y0 + 4, 0] == 2


def test_paste_or_inverted_block_ors_delta_into_background():
    # OR-inverted (2F40/2ECB): screen |= delta, background-dependent, no opacity mask.
    screen = np.zeros((200, 320), dtype=np.uint8)
    screen[PLAYFIELD_Y0, 0:4] = [0x1, 0x2, 0x0, 0x8]
    delta = np.array([[0x0, 0xF, 0x4, 0x8]], dtype=np.uint8)
    paste_or_inverted_block(screen, di=0x4000, cursor=0x4000, delta=delta)
    # 0x1|0=1, 0x2|0xF=0xF, 0x0|0x4=0x4, 0x8|0x8=0x8
    assert list(screen[PLAYFIELD_Y0, 0:4]) == [0x1, 0xF, 0x4, 0x8]


def test_composite_sprites_dispatches_or_inverted_kind():
    screen = np.zeros((200, 320), dtype=np.uint8)
    screen[PLAYFIELD_Y0, 0:2] = [0x3, 0x0]
    spr = SnapshotSprite(
        identity=1, sprite_id=2, anim_phase=0, screen_di=0x4000,
        blocks=(SpriteBlock(0x4000, np.array([[0x4, 0xF]], np.uint8),
                            np.ones((1, 2), bool), kind="or_inverted"),),
    )
    composite_sprites(screen, [spr], cursor=0x4000)
    assert list(screen[PLAYFIELD_Y0, 0:2]) == [0x3 | 0x4, 0x0 | 0xF]  # OR, not replace


def test_di_shift_translates_every_block():
    a = np.zeros((200, 320), dtype=np.uint8)
    b = np.zeros((200, 320), dtype=np.uint8)
    spr = SnapshotSprite(1, 2, 0, 0x4000,
                         (SpriteBlock(0x4000, np.full((1, 2), 5, np.uint8), np.ones((1, 2), bool)),))
    composite_sprites(a, [spr], cursor=0x4000, di_shift=0)
    composite_sprites(b, [spr], cursor=0x4000, di_shift=PRESENT_ROW_BYTES)  # one row down
    assert a[PLAYFIELD_Y0, 0] == 5 and b[PLAYFIELD_Y0 + 1, 0] == 5
    assert PRESENT_ROWS  # imported constant is used


if __name__ == "__main__":  # pragma: no cover
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
