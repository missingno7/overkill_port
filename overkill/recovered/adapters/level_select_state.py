"""Read the D4AA level-select cursor tables from a machine image (ADR-1: the image is the
source of the data), for the native level-select screen."""
from __future__ import annotations

CS = 0x1010
DS = 0x25CC
LEVEL_XY_TABLE = 0xBEDE      # DS: six (AL=x cell-col, AH=y) words -- the BEDA grid positions
OPTION_XY_TABLE = 0xBEEA     # DS: three words -- the BEDC option positions
CELL_PTR_TABLE = 0xD37E      # CS: nine cell pointers (segment offsets, CHOOSE at 0x4000)


def read_level_select_tables(image) -> "tuple[list[int], list[int], list[int]]":
    """``(level_xy[6], option_xy[3], cell_ptrs[9])`` from the image's own tables."""
    level_xy = [image.rw(DS, (LEVEL_XY_TABLE + 2 * k) & 0xFFFF) for k in range(6)]
    option_xy = [image.rw(DS, (OPTION_XY_TABLE + 2 * k) & 0xFFFF) for k in range(3)]
    cell_ptrs = [image.rw(CS, (CELL_PTR_TABLE + 2 * k) & 0xFFFF) for k in range(9)]
    return level_xy, option_xy, cell_ptrs
