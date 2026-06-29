"""Domain records for the native frame controller (the VM-free per-frame sequence).

The native frame controller sequences the recovered systems over the native game state,
the way ``1010:9B2E`` sequences them over VM memory.  These records carry the per-frame
input source into the controller and its per-stage results out, so the controller stays a
pure composition of systems with no VM dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from overkill.recovered.domain.object_slots import ObjectPool


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
