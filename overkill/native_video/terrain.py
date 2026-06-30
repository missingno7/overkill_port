"""Native terrain compositor -- render a level's tile map x block bank to indexed pixels (VM-free).

The cold-loaded level data is a tile map (13-column grid of block indices, from ``LEV{n}MAP.BIC``) plus a
block bank (16x16 4bpp tiles, from the de-planarized ``LEV{n}BLX.BIC``).  This composes them into the
level's terrain image -- the part the VM bakes into its page; here it is produced VM-free from the cold
buffers and colorized with the recovered Tandy palette.

Block geometry is from the bank's own item header (``{width=16, stride=2}`` -> a 16-row, 16-px, 128-byte
4bpp block); the tile map indexes the bank.  Pure NumPy; no VM, no video-memory layout.
"""
from __future__ import annotations

import numpy as np

TILE = 16                       # 16x16 pixel tiles
MAP_COLS = 13                   # tile-map stride (13 columns)
BLOCK_BYTES = TILE * TILE // 2  # 128 bytes (4bpp packed, 2 px/byte)


def decode_block_indices(blocks, index: int) -> np.ndarray:
    """Decode block ``index`` from the de-planarized bank to a ``(16, 16)`` 4-bit index tile."""
    off = index * BLOCK_BYTES
    raw = bytes(blocks[off:off + BLOCK_BYTES])
    if len(raw) < BLOCK_BYTES:
        return np.zeros((TILE, TILE), np.uint8)
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(TILE, TILE // 2)
    tile = np.empty((TILE, TILE), np.uint8)
    tile[:, 0::2] = (rows >> 4) & 0x0F  # high nibble = left pixel
    tile[:, 1::2] = rows & 0x0F
    return tile


def block_count(blocks) -> int:
    return len(blocks) // BLOCK_BYTES


def render_terrain_indices(tile_plane, blocks) -> np.ndarray:
    """Render the whole level terrain to an ``(rows*16, 13*16)`` 4-bit index image (VM-free).

    ``tile_plane`` is the cold tile map (13-column block-index grid); ``blocks`` is the de-planarized
    16x16 block bank.  Out-of-range indices (beyond the bank) are left as index 0.
    """
    n_blocks = block_count(blocks)
    tm = np.frombuffer(bytes(tile_plane), dtype=np.uint8)
    rows = len(tm) // MAP_COLS
    grid = tm[: rows * MAP_COLS].reshape(rows, MAP_COLS)
    out = np.zeros((rows * TILE, MAP_COLS * TILE), np.uint8)
    cache: dict[int, np.ndarray] = {}
    for r in range(rows):
        for c in range(MAP_COLS):
            idx = int(grid[r, c])
            if idx >= n_blocks:
                continue
            tile = cache.get(idx)
            if tile is None:
                tile = decode_block_indices(blocks, idx)
                cache[idx] = tile
            out[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE] = tile
    return out
