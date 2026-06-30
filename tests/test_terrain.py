"""Unit tests for the native terrain compositor (overkill.native_video.terrain)."""
from __future__ import annotations

import numpy as np

from overkill.native_video.terrain import (
    BLOCK_BYTES,
    MAP_COLS,
    TILE,
    block_count,
    decode_block_indices,
    render_terrain_indices,
)


def test_decode_block_indices_nibble_order():
    # A 16x16 block: row 0 = 0x12,0x34,... -> indices 1,2,3,4,...; high nibble is the left pixel.
    raw = bytes(range(BLOCK_BYTES))  # 128 bytes
    tile = decode_block_indices(raw, 0)
    assert tile.shape == (TILE, TILE)
    assert tile[0, 0] == 0x0 and tile[0, 1] == 0x0   # byte 0 = 0x00
    assert tile[0, 2] == 0x0 and tile[0, 3] == 0x1   # byte 1 = 0x01 -> hi 0, lo 1
    assert tile[1, 0] == 0x0 and tile[1, 1] == 0x8   # row 1 byte 0 = 0x08 -> hi 0, lo 8


def test_decode_block_out_of_range_is_zero():
    assert np.all(decode_block_indices(b"", 5) == 0)


def test_render_terrain_shape_and_placement():
    # 2 blocks; a tiny 2-row x 13-col tile map -> 2*16 x 13*16 indices.
    block0 = bytes([0x11] * BLOCK_BYTES)  # all index 1
    block1 = bytes([0x22] * BLOCK_BYTES)  # all index 2
    blocks = block0 + block1
    assert block_count(blocks) == 2
    tile_plane = bytes([1, 0] + [0] * (MAP_COLS - 2) + [0, 1] + [0] * (MAP_COLS - 2))  # 2 rows
    out = render_terrain_indices(tile_plane, blocks)
    assert out.shape == (2 * TILE, MAP_COLS * TILE)
    assert np.all(out[0:TILE, 0:TILE] == 2)              # row0 col0 -> block 1 (index 2)
    assert np.all(out[0:TILE, TILE:2 * TILE] == 1)       # row0 col1 -> block 0 (index 1)
    assert np.all(out[TILE:2 * TILE, TILE:2 * TILE] == 2)  # row1 col1 -> block 1
