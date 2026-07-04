"""Cold-load the object-pass DISPATCH TABLES from the OVERKILL code image (VM-free).

The per-frame object walk (the tail of the ``9B2E``-family controller, ``1010:A9DD..AA2A``) visits
every active record of the effect pool (35 slots via the pointer table ``DS:32CA``) and the gameplay
pool (34 slots via ``DS:8D12``) and runs, per record:

* the TYPE dispatch ``1010:AA2B``: ``bx = [bp+0x16]; shl bx,1; jmp cs:[bx+0xAA36]`` -- an 8-entry
  jump table keyed on the record's ``+0x16`` type field;
* for the enemy types (2 and 4 both route to ``1010:EFAE``): the BEHAVIOR dispatch -- ``EFAE`` first
  mirrors the record position (``[bp+4] -> DS:D1FE``, ``[bp+2] -> DS:D200``), then
  ``bx = [bp+0x18]; shl bx,1; jmp cs:[bx+0xEFC4]`` -- a 149-entry jump table keyed on the record's
  ``+0x18`` behavior index.  The targets are the per-behavior enemy state machines (the "behavior
  zoo", mostly ``1010:7Axx..8Dxx`` and ``F0xx..F7xx``; entry 0 = ``BC45``, the common no-op exit).

Both tables are STATIC code-segment constants, so they cold-load from the static runtime bundle.
This is the structural MAP of the enemy-AI subsystem: which behaviors exist and where each handler
lives.  The handlers themselves are (almost all) unrecovered -- a native runtime must treat every
behavior index it meets as a fail-loud gap until its handler is recovered.
"""
from __future__ import annotations

import struct

CODE_SEGMENT = 0x1010

TYPE_DISPATCH_ENTRY = 0xAA2B      # mov bx,[bp+0x16]; shl bx,1; jmp cs:[bx+0xAA36]
TYPE_DISPATCH_OFFSET = 0xAA36     # the 8-entry type jump table (types 0..7)
TYPE_DISPATCH_COUNT = 8

BEHAVIOR_DISPATCH_ENTRY = 0xEFAE  # position mirror (D1FE/D200) then jmp cs:[(+0x18 << 1)+0xEFC4]
BEHAVIOR_DISPATCH_OFFSET = 0xEFC4  # the 149-entry behavior jump table
BEHAVIOR_DISPATCH_COUNT = 0x95     # behaviors 0x00..0x94 (code resumes at CS:F0EE)

BEHAVIOR_EXIT_BC45 = 0xBC45        # the common no-op exit handler (entry 0 and much filler)


def _cs_words(exe_image: bytes, offset: int, count: int) -> tuple[int, ...]:
    base = CODE_SEGMENT * 16
    return tuple(
        struct.unpack_from("<H", exe_image, base + ((offset + i * 2) & 0xFFFF))[0]
        for i in range(count)
    )


def load_object_type_dispatch(exe_image: bytes) -> tuple[int, ...]:
    """Read the cold object TYPE dispatch table (``CS:AA36``): 8 handler offsets, keyed ``+0x16``."""
    return _cs_words(exe_image, TYPE_DISPATCH_OFFSET, TYPE_DISPATCH_COUNT)


def load_behavior_dispatch_table(exe_image: bytes) -> tuple[int, ...]:
    """Read the cold BEHAVIOR dispatch table (``CS:EFC4``): 149 handler offsets, keyed ``+0x18``."""
    return _cs_words(exe_image, BEHAVIOR_DISPATCH_OFFSET, BEHAVIOR_DISPATCH_COUNT)
