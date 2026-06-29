"""Unit tests for the recovered 4FF9 tile/contact probe (probe_tile_contact_4ff9)."""
from __future__ import annotations

from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.tilemap import probe_tile_contact_4ff9

ORIGIN = 0x0000
ROW_BASE = 0x1000
ZERO_OFFSETS = (0,) * 12  # three (dx, dy) pairs of 0 -> probe at the slot point


def _bx(x: int, y: int) -> int:
    """Mirror 5073 + the 4FF9 '+13' to find the first sampled cell (for placing solids)."""
    adjusted = (ORIGIN + x) & 0xFFFF
    x_tile = adjusted >> 4
    y_tile = (y & 0xF0) >> 4
    offset = (ROW_BASE - x_tile * 13 + y_tile) & 0xFFFF
    return (offset + 13) & 0xFFFF


def _tiles(solid_cells: dict[int, int]) -> LevelTileContext:
    plane = [0] * 0x10000
    for cell, raw in solid_cells.items():
        plane[cell] = raw
    class_table = [0] * 0x100
    class_table[0x07] = 1  # raw tile 0x07 maps to a solid class; everything else is clear
    return LevelTileContext(origin_x_word=ORIGIN, row_base_word=ROW_BASE,
                            tile_plane=tuple(plane), class_table=tuple(class_table))


def _probe(x, y, side, tiles):
    return probe_tile_contact_4ff9(object_x_word=x, object_y_word=y, side_index_word=side,
                                   offset_table=ZERO_OFFSETS, tiles=tiles)


def test_invalid_side_is_contact():
    # [BP+8] >= 3 -> the JNB-to-STC exit, regardless of tiles.
    assert _probe(0x20, 0x10, 3, _tiles({})) is True
    assert _probe(0x20, 0x10, 9, _tiles({})) is True


def test_all_clear_is_no_contact():
    assert _probe(0x20, 0x10, 0, _tiles({})) is False


def test_solid_first_cell_is_contact():
    x, y = 0x20, 0x10  # nibble 0 -> 1 column; y aligned -> no adjacent row
    assert _probe(x, y, 0, _tiles({_bx(x, y): 0x07})) is True


def test_single_column_ignores_second_column():
    # nibble 0 -> only one column sampled, so a solid in the second column is NOT seen.
    x, y = 0x20, 0x10
    second_column = (_bx(x, y) - 13) & 0xFFFF
    assert _probe(x, y, 0, _tiles({second_column: 0x07})) is False


def test_second_column_sampled_when_x_nibble_high():
    # adjusted X low nibble > 0Ah -> two columns; solid only in the second column -> contact.
    x, y = 0x2B, 0x10  # nibble 0xB
    second_column = (_bx(x, y) - 13) & 0xFFFF
    assert _probe(x, y, 0, _tiles({second_column: 0x07})) is True


def test_adjacent_y_sampled_when_y_unaligned():
    # Y not 16-aligned -> the neighbouring Y tile (bx+1) is also sampled.
    x, y = 0x20, 0x18  # y nibble 8
    assert _probe(x, y, 0, _tiles({(_bx(x, y) + 1) & 0xFFFF: 0x07})) is True


def test_adjacent_y_not_sampled_when_y_aligned():
    x, y = 0x20, 0x10  # y aligned
    assert _probe(x, y, 0, _tiles({(_bx(x, y) + 1) & 0xFFFF: 0x07})) is False


def test_offset_table_shifts_the_probe_point():
    # A side with dx=+0x10 moves the probe one tile column over; place the solid there.
    offsets = (0x10, 0x00, 0x00, 0x00) + (0,) * 8  # side 0: dx=+0x10, dy=0
    x, y = 0x20, 0x10
    tiles = _tiles({_bx(x + 0x10, y): 0x07})
    assert probe_tile_contact_4ff9(object_x_word=x, object_y_word=y, side_index_word=0,
                                   offset_table=offsets, tiles=tiles) is True
    # Without the offset the same solid is not under the probe.
    assert _probe(x, y, 0, tiles) is False
