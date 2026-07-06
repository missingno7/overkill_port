"""Pure world-scroll domain types (1010:A66F's forward chain: A6FE -> A74E -> A746).

Only ``origin_x``/``row_base`` (DS:234E/DS:2350) are consumed by
:class:`~overkill.recovered.domain.tilemap.LevelTileContext` (the tile-probe/collision seam the
native object scan reads); the rest (``row_source``/``rows_to_milestone``/``forward_last``) are
carried faithfully anyway because the real ASM reads them back next tick, and keeping them exact
lets a live-VM verify probe compare the WHOLE bookkeeping, not just the two fields that happen to
be gameplay-consumed today.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScrollState:
    """The world-scroll counters DS carries between 9B2E ticks (forward-chain fields only)."""

    origin_x: int          # DS:234E -- sub-row phase, 0-15, wraps every tick
    row_base: int           # DS:2350 -- byte offset into the level's tile_plane (gameplay-consumed)
    row_source: int         # DS:234C -- rendering-only source-row pointer, not tile-probe-consumed
    rows_to_milestone: int  # DS:A978 -- rendering/audio milestone countdown, not tile-probe-consumed
    forward_last: bool      # DS:2354 == 0 -- "last row pull was forward" (audio/render-only)


@dataclass(frozen=True, slots=True)
class ScrollTickOutcome:
    """One forward scroll tick's result, plus whether a new tile row was pulled this tick.

    ``pulled_row`` is the caller's cue that the real ASM's A7EB strip-copy (rendering, not modelled
    here -- see :mod:`overkill.recovered.systems.scroll`) would also have run this tick.
    ``milestone`` (set only by the milestone-composing native step) is the row_base a pulled row
    landed on when it is one of the two once-per-level A66F milestones -- 0x0E52 (the C591 call, a
    Tandy no-op) or 0x0EA0 (the A680 level-end arm) -- else ``None``.
    """

    state: ScrollState
    pulled_row: bool
    milestone: int | None = None
