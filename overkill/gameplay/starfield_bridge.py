"""Bridge: run the recovered starfield parallax move over live VM memory (replaces 1F8F:0922).

``1F8F:0922`` is the per-frame starfield mover (3 parallax layers, ``row=(row+1)%192`` at 2/4/8-frame
cadence) -- previously run-original in the frame orchestration.  This reads the live star stream + layer
counters + gate, advances them with the pure :func:`advance_starfield`, and writes the changed words back,
so the move runs natively (verified byte-exact vs the original via the demo frame verifier).
"""
from __future__ import annotations

from overkill.recovered.domain.starfield import STAR_COUNT, Star, StarfieldState
from overkill.recovered.systems.starfield import advance_starfield

STREAM_OFFSET = 0xC6C1
COUNTER_OFFSETS = (0xC812, 0xC814, 0xC816)
GATE_OFFSET = 0xA95A


def advance_starfield_in_memory(cpu) -> None:
    """Advance the live starfield one frame in place (the native form of 1F8F:0922)."""
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    stars = tuple(
        Star(mem.rw(ds, (STREAM_OFFSET + i * 6) & 0xFFFF),
             mem.rw(ds, (STREAM_OFFSET + i * 6 + 2) & 0xFFFF),
             mem.rw(ds, (STREAM_OFFSET + i * 6 + 4) & 0xFFFF))
        for i in range(STAR_COUNT)
    )
    counters = tuple(mem.rw(ds, o) for o in COUNTER_OFFSETS)
    state = StarfieldState(stars, counters, enabled=mem.rw(ds, GATE_OFFSET) != 0xFFFF)

    new = advance_starfield(state)

    # Only the rows (word0) and the layer counters change; dx/color/gate are untouched.
    for i, star in enumerate(new.stars):
        mem.ww(ds, (STREAM_OFFSET + i * 6) & 0xFFFF, star.row & 0xFFFF)
    for off, value in zip(COUNTER_OFFSETS, new.layer_counters):
        mem.ww(ds, off, value & 0xFFFF)
