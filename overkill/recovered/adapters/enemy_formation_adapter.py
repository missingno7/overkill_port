"""Cold-load the enemy-wave FORMATION table from the OVERKILL data image (VM-free).

The formation spawner (``1010:B5E6``) walks a fixed list of ``(x, y)`` word pairs at ``DS:0xA8D2`` (cursor
``DS:0xA8D0``, reset to ``0xA8D2`` at ``B5A9``; terminated at ``0xA932``), spawning one enemy per pair
(``enemy_spawn_stamp_8209`` + the B5E6 overrides -- schedule ``x -> +0x34`` biased ``+0x20``, ``y ->
+0x32``).  The list is STATIC game data (identical in the cold runtime bundle and a live L1 capture): a
24-enemy formation, three columns (``x`` = 0x50 / 0x38 / 0x20) each an 8-step snake in ``y``.
"""
from __future__ import annotations

import struct

DATA_SEGMENT = 0x25CC
FORMATION_OFFSET = 0xA8D2   # DS:A8D2 -- the (x,y) word-pair list (cursor DS:A8D0 walks it)
FORMATION_END = 0xA932      # the terminator the cursor stops at (B5DE cmp [A8D0],A932)
FORMATION_COUNT = (FORMATION_END - FORMATION_OFFSET) // 4   # 24 enemies (4 bytes = one x,y pair)


def load_enemy_formation_table(exe_image: bytes) -> tuple[tuple[int, int], ...]:
    """Read the cold enemy-wave formation as a tuple of ``(x, y)`` pairs from the runtime data image."""
    base = DATA_SEGMENT * 16

    def rw(off: int) -> int:
        return struct.unpack_from("<H", exe_image, base + (off & 0xFFFF))[0]

    return tuple(
        (rw(FORMATION_OFFSET + i * 4), rw(FORMATION_OFFSET + i * 4 + 2))
        for i in range(FORMATION_COUNT)
    )
