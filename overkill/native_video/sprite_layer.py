"""Native sprite layer: composite decoded sprite textures onto the playfield.

The backend renders the frame itself rather than diffing a baked page. This layer
takes the semantic sprite list (``SnapshotSprite`` blocks from the extractor) and
draws each block over a background **index** image at the position the game would
have drawn it, derived from the block's source-page destination ``di`` and the
present ``cursor``:

    the source page ``[9598]`` is linear with a ``0x68``-byte row; the present blit
    maps page row ``r`` (``cursor + r*0x68``) to screen row ``4 + r`` and page byte
    column to screen ``x = byte*2`` (2 px/byte). So a block at ``di`` lands at
    ``screen (4 + (di-cursor)//0x68, ((di-cursor) % 0x68) * 2)``.

Compositing is the faithful op in index space (``opaque ? sprite : background``).
For interpolation the caller shifts a sprite's ``di`` by its per-tick motion before
compositing; the placement math is identical. Verified against the live page by
``overkill/probes/verify_sprite_layer.py``.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np

from overkill.native_video.page_raster import PLAYFIELD_W, PLAYFIELD_Y0, PRESENT_ROW_BYTES, PRESENT_ROWS

# The present blits only the playfield window; sprite pixels outside it are not
# shown (the surrounding HUD/border comes from a separate layer), so sprites clip
# to the playfield, not the whole screen.
_Y_LO, _Y_HI = PLAYFIELD_Y0, PLAYFIELD_Y0 + PRESENT_ROWS   # [4, 196)
_X_LO, _X_HI = 0, PLAYFIELD_W                               # [0, 208)


def block_screen_origin(di: int, cursor: int) -> tuple[int, int]:
    """Screen (y, x) top-left for a source-page block destination ``di``.

    The offset from the cursor is a **signed** 16-bit difference: a block whose
    ``di`` is below the cursor sits above the window (negative row) with only its
    lower rows on screen — ``paste_block`` clips it. ``divmod`` floors, so a
    negative ``rel`` yields a negative row and an in-range column."""
    rel = (di - cursor) & 0xFFFF
    if rel >= 0x8000:
        rel -= 0x10000
    row, col = divmod(rel, PRESENT_ROW_BYTES)
    return PLAYFIELD_Y0 + row, col * 2


def paste_block(screen: np.ndarray, di: int, cursor: int,
                pixels: np.ndarray, opaque: np.ndarray) -> None:
    """Composite one block's opaque pixels onto ``screen`` (H, W) indices in place."""
    y0, x0 = block_screen_origin(di, cursor)
    h, w = pixels.shape
    sy0, sx0 = max(y0, _Y_LO), max(x0, _X_LO)
    sy1, sx1 = min(y0 + h, _Y_HI), min(x0 + w, _X_HI)
    if sy1 <= sy0 or sx1 <= sx0:
        return
    py0, px0 = sy0 - y0, sx0 - x0
    op = opaque[py0:py0 + (sy1 - sy0), px0:px0 + (sx1 - sx0)]
    px = pixels[py0:py0 + (sy1 - sy0), px0:px0 + (sx1 - sx0)]
    dst = screen[sy0:sy1, sx0:sx1]
    dst[op] = px[op]


def composite_sprites(screen: np.ndarray, sprites: Iterable, cursor: int,
                      di_shift: int = 0) -> np.ndarray:
    """Draw every sprite block onto ``screen`` (indices) in draw order, in place.

    ``di_shift`` offsets every block's destination uniformly (whole-frame use); per
    object interpolation instead passes already-shifted ``SnapshotSprite`` blocks."""
    for spr in sprites:
        for b in spr.blocks:
            paste_block(screen, (b.di + di_shift) & 0xFFFF, cursor, b.pixels, b.opaque)
    return screen
