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


# 1010:D318 -- the interstitial timed-input loop (a Tandy-only frame-script screen reached
# after the 97B2 path).  Each real call redraws/ticks a chain of graphics/sound children (not
# modelled -- pure timing/presentation glue with no decision content of its own), then makes
# ONE small decision: bump DS:BED8, and exit (waiting for FIRE release first) once either the
# timeout is reached or FIRE is pressed, else loop.  Already correctly implemented as a hook
# (overkill.gameplay.frame_orchestration.run_interstitial_timed_input_loop_d318); this only
# extracts that one decision into the pure layer -- same shape as MenuIdleOutcome/558B.
INTERSTITIAL_TIMEOUT = 0x00C8  # DS:BED8 exceeding this (200) forces the timeout exit


@dataclass(frozen=True, slots=True)
class InterstitialTickOutcome:
    """Result of one ``1010:D318`` interstitial-loop iteration's counter/exit decision."""

    counter: int
    result: str  # "loop" | "exit_timeout" | "exit_fire"


# 1010:CE40/CE5C -- the menu-transition input wait, reached after a dirty-cell panel finishes
# presenting.  DS:98C3 is a SHARED "transition triggered" latch used across several unrelated
# front-end screens (also polled directly by the boss-key any-key gate at 1010:07D0), not owned
# exclusively by CE40 -- CE40 only sets it (to the Space scancode 0x39) when FIRE is pressed.
MENU_TRANSITION_LATCH_SPACE_SCANCODE = 0x39


@dataclass(frozen=True, slots=True)
class MenuTransitionWaitOutcome:
    """Result of one ``1010:CE40`` menu-transition-wait iteration."""

    cx: int
    latched_key: int  # DS:98C3 after this iteration
    result: str  # "loop" | "exit_latched" | "exit_timeout"


# 1010:989E -- the Y/N confirmation choice gate (e.g. a "restart level?"/"quit?"-style prompt).
YES_NO_CHOICE_N_CHAR = 0x4E  # 'N'
YES_NO_CHOICE_Y_CHAR = 0x59  # 'Y'


@dataclass(frozen=True, slots=True)
class YesNoChoiceOutcome:
    """Result of one ``1010:989E`` yes/no choice iteration."""

    display_char: int  # DS:22B4 after this iteration -- YES_NO_CHOICE_N_CHAR or _Y_CHAR
    result: str  # "loop" | "exit_no" | "exit_yes"
