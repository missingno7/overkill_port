"""Cold-load the initial starfield state from the OVERKILL data image (VM-free).

The 40-star stream lives at ``DS:0xC6C1`` in the data segment (``0x25CC``), as ``{row, dx, color}``
triples; the layer toggles are ``DS:0xC812/0xC814/0xC816`` and the enable gate is ``DS:0xA95A``.  The
per-star ``dx``/``color`` are fixed game data (confirmed: they match the live runtime exactly, the rows
only scroll), so this reads a valid cold starting :class:`StarfieldState` that
:func:`overkill.recovered.systems.starfield.advance_starfield` then drives identically to the VM.
"""
from __future__ import annotations

import struct

from overkill.recovered.domain.starfield import STAR_COUNT, Star, StarfieldState

DATA_SEGMENT = 0x25CC
STREAM_OFFSET = 0xC6C1
COUNTER_OFFSETS = (0xC812, 0xC814, 0xC816)
GATE_OFFSET = 0xA95A


def load_starfield_state(exe_image: bytes) -> StarfieldState:
    """Read the cold initial :class:`StarfieldState` from the unpacked EXE / runtime data image."""
    base = DATA_SEGMENT * 16

    def rw(off: int) -> int:
        return struct.unpack_from("<H", exe_image, base + (off & 0xFFFF))[0]

    stars = tuple(
        Star(rw(STREAM_OFFSET + i * 6),
             rw(STREAM_OFFSET + i * 6 + 2),
             rw(STREAM_OFFSET + i * 6 + 4))
        for i in range(STAR_COUNT)
    )
    counters = tuple(rw(o) for o in COUNTER_OFFSETS)
    return StarfieldState(stars, counters, enabled=rw(GATE_OFFSET) != 0xFFFF)
