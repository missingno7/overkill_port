"""The F9 BOSS KEY fake screen (1010:075F) reads faithfully from the runtime image."""
from __future__ import annotations

import pathlib

from overkill.native_video.boss_key import (
    COLS, ROWS, boss_screen_text, cell_colors, read_boss_screen,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


def test_cell_colors_decode_the_attribute_byte():
    # attr 0x1F -> bright-white fg on blue bg (the classic DOS look)
    fg, bg = cell_colors(0x1F)
    assert fg == (0xFF, 0xFF, 0xFF) and bg == (0x00, 0x00, 0xAA)
    fg, bg = cell_colors(0x07)                       # light-grey on black
    assert fg == (0xAA, 0xAA, 0xAA) and bg == (0x00, 0x00, 0x00)


def test_boss_screen_is_the_snafu_decoy():
    if not BUNDLE.is_file():
        return
    rows = boss_screen_text(BUNDLE.read_bytes())
    assert len(rows) == ROWS
    assert "SNAFU  V4.2" in rows[0]                   # the fake file-manager banner
    assert "File Descriptor" in rows[2]
    assert "F1 = Quit" in rows[22]                    # the function-key legend
    joined = "\n".join(rows)
    assert "COBOL   .HLP" in joined                   # one of the fake files


def test_read_boss_screen_is_full_80x25_of_pairs():
    if not BUNDLE.is_file():
        return
    cells = read_boss_screen(BUNDLE.read_bytes())
    assert len(cells) == COLS * ROWS
    assert all(0 <= ch <= 0xFF and 0 <= at <= 0xFF for ch, at in cells)
