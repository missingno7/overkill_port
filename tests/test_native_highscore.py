"""The high-score TABLE read + render (the 532D screen body) -- VM-free unit tests."""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from overkill.native_video.highscore import (
    TABLE_COUNT,
    compose_table,
    player_rank,
    read_table,
    score_digits,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
CONTAINER = ROOT / "assets" / "OVERKILL"
DS = 0x25CC
_HAVE = BUNDLE.is_file() and CONTAINER.exists()


def test_score_digits_are_msb_first_bcd():
    # score bytes little-endian at entry+12; 5EDB prints MSB-first, high nibble then low
    assert score_digits(bytes([0x00, 0x80, 0x00, 0x00])) == "00008000"
    assert score_digits(bytes([0x00, 0x00, 0x45, 0x12])) == "12450000"


def test_player_rank_orders_by_score():
    table = [("A", bytes([0x00, 0x80, 0x00, 0x00])), ("B", bytes([0x00, 0x40, 0x00, 0x00])),
             ("C", bytes([0x00, 0x10, 0x00, 0x00]))]
    assert player_rank(table, bytes([0x00, 0x90, 0x00, 0x00])) == 0     # beats the top
    assert player_rank(table, bytes([0x00, 0x50, 0x00, 0x00])) == 1     # between A and B
    assert player_rank(table, bytes([0x00, 0x05, 0x00, 0x00])) == 3     # off the table (== len)


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_read_table_has_eight_entries():
    from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image
    img = build_cold_level_start_image(BUNDLE.read_bytes(), 0, CONTAINER.read_bytes())
    table = read_table(np.frombuffer(img.data, dtype=np.uint8), DS)
    assert len(table) == TABLE_COUNT
    assert all(isinstance(n, str) and len(s) == 4 for n, s in table)
    # the shipped table is strictly descending by score
    vals = [int.from_bytes(s, "little") for _n, s in table]
    assert vals == sorted(vals, reverse=True)


def test_compose_table_inserts_player_and_keeps_count():
    frame = np.zeros((200, 320), dtype=np.uint8)
    font = np.zeros((256, 8), dtype=np.uint8)
    font[ord("X")] = [0xFF] * 8                     # a solid glyph so the row is non-blank
    table = [("AAA", bytes([0, i, 0, 0])) for i in range(9, 1, -1)]     # 8 entries
    out = compose_table(frame, font, table, sy=8, sx=8, color=7,
                        editing_rank=2, editing_name="XXX", editing_score=bytes([0, 5, 0, 0]),
                        caret=True)
    assert out.shape == frame.shape
    assert out.max() == 7 and frame.max() == 0      # drew into the copy, not the input
