"""VM-free unit tests for the native Tandy B800 HUD text composer.

These pin the recovered ``1010:3153`` geometry (expand table, colour mask, four-bank cursor
advance, glyph-cell column advance) and the ``5EDB`` line composition (label escapes + the
four score bytes as eight most-significant-first BCD digits) without any VM -- the synthetic
oracle behind the demo-level ``overkill.probes.verify_native_hud_text`` witness.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.hud_text import (
    BANK_ADVANCE,
    PAGE_SIZE,
    advance_cursor,
    blit_glyph_b800,
    colour_mask_byte,
    compose_status_text_5edb,
    expand_glyph_byte,
)


def test_expand_glyph_byte_matches_ds1514_spread():
    # MSB = leftmost pixel, high nibble = left of each byte (the DS:1514 spread the
    # glyph-leaf witness already pinned against the VM table).
    assert expand_glyph_byte(0x80) == (0xF0, 0x00, 0x00, 0x00)
    assert expand_glyph_byte(0x01) == (0x00, 0x00, 0x00, 0x0F)
    assert expand_glyph_byte(0xAA) == (0xF0, 0xF0, 0xF0, 0xF0)
    assert expand_glyph_byte(0xFF) == (0xFF, 0xFF, 0xFF, 0xFF)
    assert expand_glyph_byte(0x00) == (0x00, 0x00, 0x00, 0x00)
    assert expand_glyph_byte(0x81) == (0xF0, 0x00, 0x00, 0x0F)


def test_colour_mask_byte_replicates_nibble():
    assert colour_mask_byte(0x0C) == 0xCC
    assert colour_mask_byte(0x0E) == 0xEE
    # 3153 keeps only the low nibble in the replicated mask.
    assert colour_mask_byte(0x4C) == 0xCC


def test_advance_cursor_wraps_at_a0_to_next_text_row():
    assert advance_cursor(0x00, 0x0000) == (0x04, 0x0000)
    assert advance_cursor(0x98, 0x0000) == (0x9C, 0x0000)
    # 0x9C + 4 = 0xA0 -> wrap to col 0, row += 0x140.
    assert advance_cursor(0x9C, 0x0000) == (0x00, 0x0140)
    assert advance_cursor(0x9C, 0x0280) == (0x00, 0x03C0)


def test_blit_glyph_b800_opaque_with_bank_advance():
    page = np.zeros(PAGE_SIZE, dtype=np.uint8)
    glyph = [0x80] * 8  # leftmost column lit on every row
    blit_glyph_b800(page, 0xA0, glyph, colour_mask_byte(0x0C))  # mask 0xCC
    # row 0 at di=0xA0: expand(0x80)=(0xF0,0,0,0) & 0xCC -> (0xC0,0,0,0)
    assert page[0xA0] == 0xC0
    assert page[0xA1] == 0x00 and page[0xA2] == 0x00 and page[0xA3] == 0x00
    # rows 1..3 advance one bank each (+0x2000).
    assert page[0xA0 + BANK_ADVANCE] == 0xC0
    assert page[0xA0 + 2 * BANK_ADVANCE] == 0xC0
    assert page[0xA0 + 3 * BANK_ADVANCE] == 0xC0
    # row 4 wraps: 0xA0 + 4*0x2000 = 0x80A0 -> +0x80A0 -> 0x0140.
    assert page[0x0140] == 0xC0


def _synthetic_font() -> np.ndarray:
    font = np.zeros((256, 8), dtype=np.uint8)
    font[0x30, :] = 0x00          # '0' = blank
    font[0x31, :] = 0xFF          # '1' = full
    font[0x32, :] = 0x81          # '2' = outer columns
    font[0x41, :] = 0x80          # 'A' = leftmost column
    return font


def test_compose_score_digits_most_significant_first():
    page = np.zeros(PAGE_SIZE, dtype=np.uint8)
    font = _synthetic_font()
    # score bytes in address order (2314 first); 2314=0x12 -> displays "00000012".
    end = compose_status_text_5edb(page, font=font, label_bytes=[0x00],
                                   score_bytes=[0x12, 0x00, 0x00, 0x00],
                                   colour=0x0C, col=0x00, row_base=0x0000)
    mask = colour_mask_byte(0x0C)  # 0xCC
    # digits 0..5 are '0' (blank) at cols 0,4,8,0xC,0x10,0x14.
    for d in range(6):
        assert page[d * 4] == 0x00
    # digit 6 = '1' (0xFF) at col 0x18 -> di 0x18, all four bytes = 0xCC.
    assert list(page[0x18:0x1C]) == [mask, mask, mask, mask]
    # digit 7 = '2' (0x81) at col 0x1C -> expand(0x81)=(0xF0,0,0,0x0F) & 0xCC.
    assert list(page[0x1C:0x20]) == [0xF0 & mask, 0x00, 0x00, 0x0F & mask]
    # cursor advanced 8 glyphs from col 0 -> 0x20, same row, colour unchanged.
    assert end == {"colour": 0x0C, "col": 0x20, "row_base": 0x0000}


def test_compose_label_honours_cursor_and_colour_escapes():
    page = np.zeros(PAGE_SIZE, dtype=np.uint8)
    font = _synthetic_font()
    # 0x11 row=2 col=5 -> row_base=0x280, col=0x14; 0x10 colour=0x0E; then 'A'; NUL.
    label = [0x11, 0x02, 0x05, 0x10, 0x0E, 0x41, 0x00]
    end = compose_status_text_5edb(page, font=font, label_bytes=label,
                                   score_bytes=[0x00, 0x00, 0x00, 0x00],
                                   colour=0x0C, col=0x00, row_base=0x0000)
    di = 0x14 + 0x280  # 0x294
    # 'A' row 0 = 0x80 -> (0xF0,0,0,0) & 0xEE -> 0xE0.
    assert page[di] == 0xE0
    # after 'A' the cursor advanced to col 0x18; then eight '0' (blank) score digits.
    assert end["colour"] == 0x0E
    assert end["row_base"] == 0x0280
    assert end["col"] == (0x18 + 8 * 4) & 0xFF  # 0x38
