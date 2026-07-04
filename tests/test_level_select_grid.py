"""Cold-load the level-select grid positions (level_select_grid_adapter)."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.level_select_grid_adapter import (
    GRID_CELL_COUNT,
    load_level_select_grid_positions,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_level_select_grid_positions_are_a_2x3_planet_layout():
    grid = load_level_select_grid_positions(BUNDLE.read_bytes())
    assert len(grid) == GRID_CELL_COUNT == 6
    xs = [x for x, _ in grid]
    ys = [y for _, y in grid]
    # 3 columns (X = 0x2E/0x53/0x78) x 2 rows (Y = 0x02 top, 0x15 bottom) -- matches the BEDA nav
    assert xs == [0x2E, 0x53, 0x78, 0x2E, 0x53, 0x78]
    assert ys == [0x02, 0x02, 0x02, 0x15, 0x15, 0x15]
