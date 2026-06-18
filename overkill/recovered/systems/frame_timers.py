"""Pure recovered frame-timer system.

Source-like logic extracted from the live ``1010:61C7`` hook (the per-frame
countdown the game runs every frame).  The original scans a small table of
16-bit countdown timers and decrements the first non-zero one.  This module owns
that decision as ordinary Python over ordinary values; the VM hook in
``overkill.gameplay.game_state`` is now a thin adapter that decodes the timer
table, calls :func:`step_first_active_timer`, and writes the result back.

Pure: no VM, no ``cpu``/``mem``, no addresses.  The caller (the adapter) owns the
DOS memory layout; this owns only the rule.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FrameTimerStep:
    """Result of one frame-timer step.

    ``counters`` is the table after the step; ``decremented_index`` is which
    counter was decremented, or ``None`` when every counter from ``start_index``
    onward was already zero (nothing changed).
    """

    counters: tuple[int, ...]
    decremented_index: int | None


def step_first_active_timer(counters: tuple[int, ...], start_index: int = 0) -> FrameTimerStep:
    """Decrement the first non-zero countdown timer at or after ``start_index``.

    16-bit wrap; scanning order is table order, matching the original 61C7 scan
    (which begins at the caller-provided slot — 0 for 61C7/61F7, an arbitrary
    in-table slot for 61CA).
    """
    out = list(counters)
    for i in range(start_index, len(out)):
        if out[i] & 0xFFFF:
            out[i] = (out[i] - 1) & 0xFFFF
            return FrameTimerStep(tuple(out), i)
    return FrameTimerStep(tuple(out), None)
