"""Cold-load the second enemy formation ring (``DS:A844..A894``) -- the re-shuffle slots.

Behavior ``0x20``'s hold phase re-targets enemies to fresh formation slots picked from this ring
(cursor ``DS:A842``, advancing 4 bytes per pick, wrapping at ``A894``; see
``systems/enemy_behaviors.step_enemy_behavior_20``).  Entries are ``(x_raw, y)`` word pairs with x
stored WITHOUT the ``+0x20`` bias the picker applies (``lodsw; add ax,0x20``).  Static game data --
cold == live, test-pinned.
"""
from __future__ import annotations

import struct

from overkill.recovered.systems.enemy_behaviors import (
    SLOT_RING_BASE_A844,
    SLOT_RING_END_A894,
)

DATA_SEGMENT = 0x25CC
SLOT_RING_PAIRS = (SLOT_RING_END_A894 - SLOT_RING_BASE_A844) // 4   # 20 (x_raw, y) pairs


def load_enemy_slot_ring(exe_image: bytes) -> tuple[tuple[int, int], ...]:
    """Read the cold ``A844`` re-shuffle ring as ``(x_raw, y)`` pairs (x without the +0x20 bias)."""
    base = DATA_SEGMENT * 16

    def rw(off: int) -> int:
        return struct.unpack_from("<H", exe_image, base + (off & 0xFFFF))[0]

    return tuple(
        (rw(SLOT_RING_BASE_A844 + i * 4), rw(SLOT_RING_BASE_A844 + i * 4 + 2))
        for i in range(SLOT_RING_PAIRS)
    )
