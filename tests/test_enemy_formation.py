"""Cold-load the enemy-wave formation table (enemy_formation_adapter)."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.enemy_formation_adapter import (
    FORMATION_COUNT,
    load_enemy_formation_table,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_enemy_formation_is_the_24_enemy_three_column_snake():
    table = load_enemy_formation_table(BUNDLE.read_bytes())
    assert len(table) == FORMATION_COUNT == 24
    # three columns at x = 0x50 / 0x38 / 0x20, eight enemies each
    xs = [x for x, _ in table]
    assert xs[0:8] == [0x50] * 8 and xs[8:16] == [0x38] * 8 and xs[16:24] == [0x20] * 8
    # each column is an 8-step snake in y (0x18 apart, spanning 0x00..0xA8)
    assert table[0] == (0x50, 0xA8) and table[7] == (0x50, 0x00)
    assert table[8] == (0x38, 0x00) and table[15] == (0x38, 0xA8)
    assert all(0 <= y <= 0xA8 and y % 0x18 == 0 for _, y in table)
