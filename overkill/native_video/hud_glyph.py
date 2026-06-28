"""Native Tandy glyph blit — the index-space form of ``1010:3153`` (the HUD char output).

The VM's `3153` draws an 8x8 glyph into the packed Tandy B800 page: for each of the 8
row bytes it expands each set bit through the table at ``DS:1514`` into an ``0xF`` 4-bit
nibble, ANDs the colour mask ``DS:215C``, and writes two words (8 px) per row, advancing
``di`` by the Tandy bank geometry. Two facts make the native form trivial:

* the ``DS:1514`` expand table is just a **bit -> 0xF-nibble spread** (verified against the
  snapshot: ``80h -> F0 00 00 00``, ``01h -> 00 00 00 0F``, ``AAh -> F0 F0 F0 F0``), so it
  is *generated*, not data; and
* in the backend's **index space** (the ``(H, W)`` 4-bit-index image the renderer composes,
  before the B800 bank packing) the geometry collapses to a plain pixel write.

So natively the blit is: ``pixel = colour`` where the glyph bit is set, ``0`` where clear
(opaque, matching `3153`'s `& colour` write of `0` on clear bits). The font is the 8
bytes/char table at ``DS:1816`` (standard 8x8). This is the leaf of the HUD-digit island;
the score digits are this blit per digit of the recovered ``score_bcd`` at the HUD cursor.
"""
from __future__ import annotations

import numpy as np

GLYPH_H = 8
GLYPH_W = 8


def draw_glyph(indices: np.ndarray, sy: int, sx: int, glyph_rows, color: int) -> np.ndarray:
    """Blit one 8x8 glyph into ``indices`` (H, W uint8 colour indices) at top-left
    ``(sy, sx)``, in place.

    ``glyph_rows`` is the 8-byte glyph (row 0 top, bit 0x80 = leftmost pixel). Opaque:
    each cell pixel becomes ``color`` where the glyph bit is set and ``0`` where clear —
    the index-space equivalent of `3153`'s ``(expand & colour)`` write. Pixels outside
    ``indices`` are clipped.
    """
    h, w = indices.shape
    color &= 0xFF
    for r in range(GLYPH_H):
        yy = sy + r
        if not (0 <= yy < h):
            continue
        row = glyph_rows[r] & 0xFF
        for b in range(GLYPH_W):
            xx = sx + b
            if 0 <= xx < w:
                indices[yy, xx] = color if (row & (0x80 >> b)) else 0
    return indices


def draw_glyph_string(indices: np.ndarray, sy: int, sx: int, chars, font, color: int,
                      advance: int = GLYPH_W) -> np.ndarray:
    """Blit a sequence of ``chars`` left-to-right from ``sy, sx`` using ``font`` (a
    256x8 table of 8-byte glyphs, e.g. the recovered ``DS:1816`` font), ``advance`` px
    apart. Used for the HUD score digits / labels."""
    x = sx
    for ch in chars:
        draw_glyph(indices, sy, x, font[ch & 0xFF], color)
        x += advance
    return indices
