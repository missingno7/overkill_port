"""Unit tests for the native HUD glyph blit (VM-free), the index-space form of 1010:3153.

The '0' glyph (recovered from DS:1816) is 3C 66 6E 7E 76 66 3C 00; rendered opaque in
colour 0x0A (the green DS:215C HUD colour) it must reproduce that bitmap exactly.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.hud_glyph import draw_glyph, draw_glyph_string

# '0' from the recovered DS:1816 font.
GLYPH_0 = (0x3C, 0x66, 0x6E, 0x7E, 0x76, 0x66, 0x3C, 0x00)
GREEN = 0x0A


def _expected(glyph, color):
    return np.array(
        [[color if (row & (0x80 >> b)) else 0 for b in range(8)] for row in glyph],
        dtype=np.uint8,
    )


def test_glyph_matches_font_bitmap_opaque():
    idx = np.full((8, 8), 5, dtype=np.uint8)  # non-zero background to prove opacity
    draw_glyph(idx, 0, 0, GLYPH_0, GREEN)
    assert np.array_equal(idx, _expected(GLYPH_0, GREEN))
    # opaque: clear bits became 0, not the background 5
    assert idx[7].tolist() == [0] * 8           # last glyph row is 0x00 -> all black


def test_glyph_sets_colour_where_bit_set():
    idx = np.zeros((8, 8), dtype=np.uint8)
    draw_glyph(idx, 0, 0, GLYPH_0, GREEN)
    # row 0 = 0x3C = ..####.. -> cols 2..5 are green
    assert idx[0].tolist() == [0, 0, GREEN, GREEN, GREEN, GREEN, 0, 0]


def test_glyph_clips_at_edges():
    idx = np.zeros((6, 6), dtype=np.uint8)
    draw_glyph(idx, 3, 3, (0xFF,) * 8, GREEN)   # would overrun; only the in-bounds 3x3 set
    assert (idx[3:, 3:] == GREEN).all()
    assert (idx[:3, :] == 0).all() and (idx[:, :3] == 0).all()


def test_glyph_string_advances_per_char():
    font = [(0,) * 8] * 256
    font[ord("0")] = GLYPH_0
    idx = np.zeros((8, 24), dtype=np.uint8)
    draw_glyph_string(idx, 0, 0, b"000", font, GREEN, advance=8)
    # three '0' glyphs at x=0,8,16 -> each has green at local cols 2..5
    for base in (0, 8, 16):
        assert idx[0, base + 2] == GREEN and idx[0, base + 0] == 0


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
