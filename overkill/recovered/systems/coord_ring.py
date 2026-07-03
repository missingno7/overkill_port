"""Pure recovered delayed-coordinate ring geometry (the ``1010:9CF1`` cursor advance).

The frame controller keeps a **delayed-coordinate ring** -- a small circular buffer of recent object
centres that trailing/tracked objects read from a few frames late (so a follower lags its leader).
The ring data occupies ``DS:A27A .. A339`` (48 ``(x, y)`` word-pair slots, 4 bytes each) and has four
independent write cursors at ``DS:A33A/A33C/A33E/A340``.  Each frame ``1010:9CF1`` advances every cursor
by one slot (``+4`` bytes); a cursor that steps to ``DS:A33A`` (one past the last slot) wraps back to the
ring base ``DS:A27A``.

This module owns that wrap rule as ordinary Python over ordinary values; the VM hook in
``overkill.gameplay.game_state`` (``run_frame_coord_ring_advance_9cf1`` via ``_advance_coord_ring_ptr``)
is a thin adapter that reads each cursor word, calls :func:`advance_coord_ring_ptr`, and writes it back
(replaying the dead ``CMP`` flag for boundary fidelity).

Pure: no VM, no ``cpu``/``mem``, no hooks.  The caller owns the DOS memory layout; this owns only the
rule.
"""
from __future__ import annotations

#: First slot of the ring data region (``DS:A27A``).
COORD_RING_BASE = 0xA27A
#: One past the last slot (``DS:A33A``); a cursor reaching this wraps back to :data:`COORD_RING_BASE`.
COORD_RING_WRAP_AT = 0xA33A
#: Bytes per cursor advance -- one ``(x, y)`` word pair.
COORD_RING_STEP = 0x0004

#: Number of ``(x, y)`` slots in the ring (``(A33A - A27A) / 4``).
COORD_RING_SLOTS = (COORD_RING_WRAP_AT - COORD_RING_BASE) // COORD_RING_STEP  # 48


#: The number of ring write/read cursors 9CF1 advances in lockstep each frame (DS:A33A/A33C/A33E/A340).
COORD_RING_CURSOR_COUNT = 4


def advance_coord_ring_ptr(ptr: int) -> int:
    """One ``9CF1`` cursor advance: step by :data:`COORD_RING_STEP`, wrapping past the ring.

    Returns the next cursor value for ``ptr``: ``ptr + 4`` normally, or :data:`COORD_RING_BASE` when
    that step reaches :data:`COORD_RING_WRAP_AT` (one past the last slot).  ``ptr`` is a raw 16-bit
    ``DS`` offset; the result is masked to 16 bits.
    """
    stepped = (ptr + COORD_RING_STEP) & 0xFFFF
    return COORD_RING_BASE if stepped == COORD_RING_WRAP_AT else stepped


def coord_ring_advance_gate(input_98be: int, a360: int) -> bool:
    """Whether ``9CF1`` advances the ring cursors this frame.

    ``9CF1`` skips the advance only when there is no directional input **and** the axis-response flag is
    clear: ``TEST byte DS:98BE, 0Fh`` == 0 **and** ``DS:A360`` == 0.  So it advances iff the low input
    nibble is non-zero or ``a360`` is non-zero.  (The ``a360`` cell is set by the ``9C01`` axis stage.)
    """
    return (input_98be & 0x0F) != 0 or (a360 & 0xFFFF) != 0


def advance_coord_ring_cursors(cursors) -> tuple[int, ...]:
    """Advance every ring cursor one slot (the ``9CF1`` body once the gate has passed).

    ``cursors`` is the four cursor values ``(A33A, A33C, A33E, A340)``; returns them each advanced by
    :func:`advance_coord_ring_ptr`.  Pure whole-stage form for the native frame loop; the VM adapter
    applies the same advance per cursor in place.
    """
    return tuple(advance_coord_ring_ptr(c) for c in cursors)
