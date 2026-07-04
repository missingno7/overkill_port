"""Cold-load the level-select GRID positions from the OVERKILL data image (VM-free).

The level-select screen (``LEVSCR``) draws a cursor over a 2x3 grid of the six planets, indexed by
``DS:BEDA`` (0-5; nav ``D476``/``D480`` = +/-3 row, ``D488``/``D490`` = +/-1 column -- see
``systems/menu``).  The cursor draw (``1010:D4BC``) reads, per cell, the POSITION word
``DS:0xBEDE[BEDA]`` (fed to the ``5A00`` draw-position setter).

The position table is STATIC game data (identical in the cold runtime bundle and a live capture): a clean
2x3 grid -- high byte = column X (0x2E / 0x53 / 0x78), low byte = row Y (0x02 / 0x15).  So it cold-loads.

NOT cold-loadable (deliberately excluded, fail-loud): the per-cell SPRITE pointer ``CS:0xD37E[BEDA]``
(``5A6C`` blit) is RUNTIME-POPULATED -- 0 in the cold image, only filled (to 0x4000 + i*0x8C8) once the
planet-icon sprites decode.  So the sprite association is a render-time concern, not part of the cold
layout.
"""
from __future__ import annotations

import struct

DATA_SEGMENT = 0x25CC
POSITION_TABLE_OFFSET = 0xBEDE   # DS:BEDE[BEDA] -> the 5A00 draw-position word (static)
GRID_CELL_COUNT = 6              # the six planets (BEDA 0..5; cell 5 is the unplayable/sentinel cell)


def load_level_select_grid_positions(exe_image: bytes) -> tuple[tuple[int, int], ...]:
    """Read the cold level-select grid cell positions as ``(x, y)`` pairs (6 cells, a 2x3 layout)."""
    ds = DATA_SEGMENT * 16

    def dsrw(off: int) -> int:
        return struct.unpack_from("<H", exe_image, ds + (off & 0xFFFF))[0]

    return tuple(
        ((pos := dsrw(POSITION_TABLE_OFFSET + i * 2)) >> 8, pos & 0xFF)
        for i in range(GRID_CELL_COUNT)
    )
