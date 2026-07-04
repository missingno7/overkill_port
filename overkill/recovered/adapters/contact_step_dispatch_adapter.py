"""Cold-load the AFD8 contact-step DIRECTION dispatch table (``CS:B022``) -- VM-free.

``1010:AFD8`` is the enemy MOVE-ONE-STEP-WITH-COLLISION worker (called by 21 of the 149 behavior-zoo
handlers -- the xref-scan mega-worker).  Its core (``B00D``) maps the object through the recovered
``5073`` coordinate->tile probe, then dispatches ``jmp cs:[( [bp+0x06] << 1 ) + 0xB022]`` -- an
8-entry jump table keyed on the record's ``+0x06`` DIRECTION field (``OFF_DIRECTION_OR_STEP``):

    key 4 = ``B03C`` step +X   key 0 = ``B07D`` step -X   key 2 = ``B0CC`` step +Y
    key 6 = ``B10F`` step -Y   and the diagonals COMPOSE the axis handlers --
    key 3 = ``B039`` (+Y then +X), key 1 = ``B0C9`` (-X then +Y), key 5 = ``B10C`` (+X then -Y),
    key 7 = ``B07A`` (-Y then -X).

Each axis handler: leading-edge tile-class checks (the recovered ``505B`` lookup; class 0 =
walkable; ``+/-0xD`` = one tile column in the 5073 offset space), the ``DS:215A`` sub-tile sample
counter, the position step on ``+0x02``/``+0x04`` mirrored to ``DS:A438``/``A436``, the ``BDD0``
contact-slot scan, and ``DS:A430 = 1`` on block (``B032``).  The table is STATIC code-segment data
(cold == live, verified by the test), so it cold-loads; the handler BODIES are the next recovery
slice (the pure "step one pixel in direction d with terrain + contact" function over the
``systems/tilemap`` substrate).
"""
from __future__ import annotations

import struct

CODE_SEGMENT = 0x1010

CONTACT_STEP_WORKER_ENTRY = 0xAFD8      # the shared worker (21 zoo callers)
CONTACT_STEP_DISPATCH_OFFSET = 0xB022   # jmp cs:[(+0x06 << 1) + B022]
CONTACT_STEP_DIRECTION_COUNT = 8        # the 8 movement directions (key 8 onward is handler code)
CONTACT_FLAG_CELL = 0xA430              # DS:A430 -- set to 1 on a blocked/contact step


def load_contact_step_dispatch(exe_image: bytes) -> tuple[int, ...]:
    """Read the cold AFD8 direction dispatch table (``CS:B022``): 8 handler offsets, keyed ``+0x06``."""
    base = CODE_SEGMENT * 16
    return tuple(
        struct.unpack_from("<H", exe_image, base + ((CONTACT_STEP_DISPATCH_OFFSET + i * 2) & 0xFFFF))[0]
        for i in range(CONTACT_STEP_DIRECTION_COUNT)
    )
