"""Cold-load the 4D95 canned pseudo-random ring from the OVERKILL data image (VM-free).

``1010:4D95`` (an xref-scan shared worker; e.g. the ``B7F3`` enemy shoot gate samples it) is not an
LCG: it walks a FIXED 16-word ring at ``DS:20A8..20C6`` via the cursor ``DS:20A6`` (+2 per call,
wrapping at ``20C7``) and returns the word.  The ring is static game data, so it cold-loads; the
pure step is ``systems/frame_loop.canned_random_next_4d95``.
"""
from __future__ import annotations

import struct

from overkill.recovered.systems.frame_loop import (
    CANNED_RANDOM_RING_BASE_20A8,
    CANNED_RANDOM_RING_WORDS,
)

DATA_SEGMENT = 0x25CC


def load_canned_random_ring(exe_image: bytes) -> tuple[int, ...]:
    """Read the cold 16-word 4D95 ring (``DS:20A8..20C6``)."""
    base = DATA_SEGMENT * 16
    return tuple(
        struct.unpack_from("<H", exe_image,
                           base + ((CANNED_RANDOM_RING_BASE_20A8 + i * 2) & 0xFFFF))[0]
        for i in range(CANNED_RANDOM_RING_WORDS)
    )
