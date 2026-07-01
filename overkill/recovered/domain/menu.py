"""Front-end (intro/title/menu/map) domain records -- the VM-free counterpart of the scenes
shown before/around a level.  Like ``domain/frame_loop.py`` for gameplay, this stays pure:
no ``cpu``/``mem``, only source-level state the native side owns.
"""
from __future__ import annotations

from dataclasses import dataclass

MENU_ATTRACT_TIMEOUT = 0x02EE  # DS:22BF reaching this (750) transitions to the attract-mode demo


@dataclass(frozen=True, slots=True)
class MenuIdleOutcome:
    """Result of one ``1010:558B`` main-menu idle-loop iteration (the hot no-shortcut path)."""

    attract_counter: int
    result: str  # "loop" | "exit" | "attract_timeout"


# 1010:D390-D4B0 -- the level/difficulty selector screen (disassembled 2026-07-02, never
# hooked before this).  DS:BEDA holds a 2x3 grid cell index 0-5: cells 0-4 are real levels,
# cell 5 is a non-level 6th option (see LevelSelectFireResult).  BEDA never wraps -- each of
# the 4 direction handlers REJECTS (leaves BEDA unchanged) at its own boundary, matching the
# ASM's own cmp/jnb-jbe-jz-D445 "reject to idle" branches; there is no modular wraparound.
LEVEL_SELECT_CELL_COUNT = 6
LEVEL_SELECT_UNPLAYABLE_CELL = 5  # BEDA==5 -> DS:2356 sentinel (0xFFFF), not a playable level


@dataclass(frozen=True, slots=True)
class LevelSelectStep:
    """Result of one grid-navigation direction event at the level-select screen.

    ``accepted=False`` means the direction was rejected at a grid boundary (the ASM's own
    jnb/jbe/jz-back-to-D445 branches) -- ``beda`` is unchanged, matching the ASM never writing
    DS:BEDA on that path.
    """

    beda: int
    accepted: bool


@dataclass(frozen=True, slots=True)
class LevelSelectFireResult:
    """Result of confirming the level-select screen (``1010:D424``, reached when FIRE fires).

    ``level`` is the value written to ``DS:2356`` -- the selected grid cell itself for cells
    0-4, or the ``0xFFFF`` sentinel for cell 5 (:data:`LEVEL_SELECT_UNPLAYABLE_CELL`)."""

    level: int
