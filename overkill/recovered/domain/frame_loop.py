"""Domain records for the native frame controller (the VM-free per-frame sequence).

The native frame controller sequences the recovered systems over the native game state,
the way ``1010:9B2E`` sequences them over VM memory.  These records carry the per-frame
input source into the controller and its per-stage results out, so the controller stays a
pure composition of systems with no VM dependency.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Sequence

from overkill.recovered.domain.object_slots import ObjectPool


class GameplayExit(enum.Enum):
    """Which way the ``1010:97B2`` gameplay frame loop leaves gameplay this frame.

    The frame loop tests three flags 9B2E sets, in this priority (``97CE..97E9``): ``A344`` ->
    ``jmp 9734`` (a scripted "end/transition" command), then ``A342`` -> ``jmp 9902`` (game over),
    then ``A346`` -> ``jmp 9908`` (the death/next-life tail).  The jump TARGETS (9734/9902/9908) are
    not recovered yet, so a native loop treats reaching any of these as a fail-loud boundary.
    """

    SCRIPTED = 0x9734    # A344: scripted-input mode command DS:A47C == 4
    GAME_OVER = 0x9902   # A342 (+A346): the death tail with A97A == 0
    DEATH = 0x9908       # A346 alone: the death/next-life tail with A97A != 0


@dataclass(frozen=True, slots=True)
class GameplayTransition:
    """A gameplay-loop exit the native frame detected this frame (see :class:`GameplayExit`)."""

    exit: GameplayExit

    @property
    def jump_target(self) -> int:
        """The original ``97B2`` jump target IP for this exit (an unrecovered continuation)."""
        return self.exit.value


@dataclass(frozen=True, slots=True)
class FrameInput:
    """The per-frame input source the native controller decodes (replaces the INT 9 path).

    ``control_map`` is the eight-scancode control map the game stores in its data segment
    (DS:213E / DS:2146); ``key_state`` is the scancode-indexed pressed table the native
    input source produces (``input.key_state_from_pressed``) in place of the VM's DS:98C4.
    Both are plain sequences so the controller is independent of how the host gathers keys.
    """

    control_map: Sequence[int]
    key_state: Sequence[int]


@dataclass(frozen=True, slots=True)
class FireControlState:
    """The action/fire fan-out's own carried scratch: ``DS:A980`` latch + ``DS:95DA`` allocator cursor.

    Threaded frame to frame by the native controller, the way the VM keeps these between ``9B2E`` calls
    (``latch_a980`` is written by the entry gate itself; ``cursor_95da`` is the gameplay-pool allocator
    cursor 7573 parks after each spawn).  Everything else ``native_action_fanout_step`` reads -- DS:9790/
    232A/2350/BDAC/A958/BE06, the firing object's position, the weapon schedules -- is still VM-owned
    state, supplied as explicit per-frame inputs until those subsystems are native too (the same "explicit
    external globals" shape as :class:`~overkill.recovered.domain.object_update.ObjectUpdateGlobals`).
    ``cursor_95da`` defaults to the gameplay table base (``0x2B5C``): a safe start for a fresh game state,
    since :func:`~overkill.recovered.systems.objects.object_pool_find_free` scans the whole table and
    wraps, so any starting position within it still finds the first free slot correctly.
    """

    latch_a980: int = 0x0000
    cursor_95da: int = 0x2B5C  # layout-justified: the gameplay table base -- see the class docstring


@dataclass(frozen=True, slots=True)
class FrameAccumulatorShiftOutcome:
    """Result of the ``1010:A940`` per-frame accumulator-shift (the first thing ``A940`` does,
    every frame, unconditionally -- called from ``97B2`` right before the ``A9E0`` object scan).

    ``counter_a8ce`` is a SATURATING counter (``DS:A8CE``): incremented every frame, but frozen
    once it reaches ``0xFFFF`` rather than wrapping -- a deliberate original design choice, not
    an oversight.  ``prev_a8c6``/``prev_a8ca`` are this frame's ENTRY values of ``DS:A8C8``/
    ``DS:A8CC`` shifted into the "previous frame" cells (``DS:A8C6``/``DS:A8CA``); ``DS:A8C8``/
    ``DS:A8CC`` themselves are then unconditionally reset to 0, so whatever they accumulate
    starts fresh each frame (the SAME two cells the ``0x9C`` interstitial's ``B5A9`` prelude also
    force-resets early, on top of this regular per-frame reset -- see the front-end memory)."""

    counter_a8ce: int
    prev_a8c6: int
    prev_a8ca: int


# 1F8F:081D -- the demo/attract-mode counter tick.  A940 calls this once per frame only while
# DS:2356 == 5 (attract-mode demo playback is active -- a SECOND, unrelated meaning of the same
# global the level-select screen uses for its own chosen-cell value; see the frame-controller
# memory's DS:2356 gotcha).  DS:A47E is the SAME "speed bucket" global object_update.py's
# ObjectUpdateGlobals.a47e already threads through elsewhere (an early-global guard, <=2 -> B8F8
# edge-steer) -- reused here as a difficulty/speed scale for how fast this timer reloads.
DEMO_TICK_DEFAULT_RELOAD = 0x78


@dataclass(frozen=True, slots=True)
class DemoCounterTickOutcome:
    """Result of one ``1F8F:081D`` demo/attract-mode counter tick."""

    counter_98a7: int  # DS:98A7 after -- decremented, or reloaded from the speed-bucket table
    counter_98a6: int  # DS:98A6 after -- reset to 0, or incremented


@dataclass(frozen=True, slots=True)
class FrameScanEntryOutcome:
    """Result of ``1010:A940``'s TAIL -- the ``DS:98A8``/``DS:98A9`` edge-detect (unconditional,
    runs every frame regardless of the ``DS:2356==5`` attract-mode branch) plus the ``DS:A8C2``
    boss-latch fork that decides which object-scan entry the frame takes next.

    ``flag_98a9`` mirrors whatever ``flag_98a8`` was AT ENTRY this frame (an edge-detect: "was
    98A8 set last frame" latched into 98A9), and ``flag_98a8`` itself is always cleared to 0.
    ``scan_target`` is ``"boss"`` when the boss latch (``DS:A8C2``, see
    ``ObjectUpdateGlobals.a8c2_boss_mode``/``BOSS_GROUP_LATCH``) is 1 -- the rare, still-unlifted
    ``0xA9DA``->``F797`` path, not modelled past this fork -- or ``"normal"`` (``0xA9E0``, the
    already-recovered object scan, entered with ``CX=0x23``)."""

    flag_98a8: int  # always 0 after
    flag_98a9: int  # 0 or 1 -- mirrors flag_98a8's ENTRY value
    scan_target: str  # "boss" | "normal"


@dataclass(frozen=True, slots=True)
class PlayerFrameStep:
    """Result of the native player sub-step: input decode -> the 9B2E movement bits.

    ``special_pool`` is the view-anchor pool (DS:237C, one slot) after the held direction
    input has been applied; ``input_flags`` is the decoded DS:98BE button byte (the later
    action/fire stages consume it); ``moved`` is whether any direction bit stepped the
    anchor (so a native loop can skip a redundant write/redraw).
    """

    special_pool: ObjectPool
    input_flags: int
    moved: bool
