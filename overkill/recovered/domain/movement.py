"""Pure movement records recovered from target-seeking object helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ViewAnchorMoveStep:
    """Post-frame position of the player-controlled view-anchor slot (DS:237C).

    The result of applying one frame's direction input to the view anchor's screen
    position via the four A5D1/A5EA/A5F9/A607 clamp-steps (the 9B2E movement-bits
    stage).  ``stepped`` is whether any direction bit moved it (false when no
    direction was held), kept so a native frame loop can skip a redundant write.
    """

    x_word: int
    y_word: int
    stepped: bool


@dataclass(frozen=True, slots=True)
class ChildCoordUpdate:
    """Result of the 1010:9FEA linked/child-object coordinate update.

    ``x_word``/``y_word`` are the child's new screen X/Y (Y already clamped into
    ``0..0x00C0``); ``lower_clamped``/``upper_clamped`` record whether the Y clamp
    fired at the bottom (Y went negative -> 0, sets DS:A39E) or the top (Y > 0x00C0
    -> 0x00C0, sets DS:A39F).  Pure gameplay outputs only — the DS-memory writes and
    the ASM register/flag choreography stay in the adapter.
    """

    x_word: int
    y_word: int
    lower_clamped: bool
    upper_clamped: bool


@dataclass(frozen=True, slots=True)
class MovementTarget:
    """Copied target point used by the recovered 1010:5DB2 seeker.

    The original globals are ordered as Y then X (``DS:2304``/``DS:2306``).
    The pure record keeps that evidence-shaped order explicit while remaining
    independent from DOS memory.
    """

    y_word: int
    x_word: int


@dataclass(frozen=True, slots=True)
class TargetSeekDecision:
    """Portable result of the recovered 1010:5DB2 target-direction decision."""

    direction_bits: int
    mapped_direction: int
    blocked: bool


@dataclass(frozen=True, slots=True)
class TargetSeekStep:
    """Portable per-slot result of the whole recovered 1010:5DB2 target-seek movement.

    5DB2 picks a direction toward the target (the :class:`TargetSeekDecision`), writes it to
    the slot's ``direction_or_step`` (+06), and steps the slot's ``x``/``y`` by that direction
    via the 5E0C-dispatched step (mode 1 -> AF63 one 2px step, mode 2 -> AF60 two 2px steps,
    mode 3 -> AEE4 one 8px step).  On the blocked branch (direction table -> FFh) it touches
    nothing.  This records only the slot fields 5DB2 mutates -- the DS:A954 direction-bit and
    DS:230A blocked globals are out of scope (separate state)."""

    direction_or_step: int
    x_word: int
    y_word: int
    blocked: bool


@dataclass(frozen=True, slots=True)
class DeltaSteerStep:
    """Portable per-slot result of the recovered runtime-patched 1010:5E42 delta-steer.

    5E42 converts the slot's signed Y/X movement deltas (+2C/+2A) into a direction via a Bresenham
    axis selection against the ``move_step_error`` accumulator (+2E) and the DS:A348 table, then steps
    the slot's x/y by that direction (AF22 3px when DS:2312==3, else AF63 2px).  On the blocked branch
    (table -> FFh) it leaves direction + x/y untouched but the accumulator is still advanced.  This
    records the slot fields 5E42 mutates: ``direction_or_step`` (+06), ``move_step_error`` (+2E), and
    ``x_word``/``y_word``.  The DS:230C/230E/2310 scratch globals are not slot state."""

    direction_or_step: int
    move_step_error: int
    x_word: int
    y_word: int
    blocked: bool


@dataclass(frozen=True, slots=True)
class ObjectDelta5e1b:
    """Portable result of the recovered 1010:5E1B object-delta helper.

    5E1B fills a slot's signed Y/X movement deltas (+2C/+2A) as ``slot - (target + pad)`` toward a
    target/reference record, where ``pad`` is 4px when the target is solid (its scan flag +14 == 1)
    else 12px.  These deltas are exactly the input :class:`DeltaSteerStep` (5E42) consumes, so the two
    compose into a full edge/target steer.  Records only the two delta words 5E1B writes."""

    move_delta_x: int
    move_delta_y: int


@dataclass(frozen=True, slots=True)
class MovementStepOperation:
    """One ordered axis mutation from the recovered 8-way step tables.

    ``axis`` names the object-slot coordinate to mutate.  ``delta_word`` is a
    wrapped signed word so the pure layer can describe both increments and
    decrements without knowing how the ASM adapter will materialize flags.
    """

    axis: Literal["x", "y"]
    delta_word: int


@dataclass(frozen=True, slots=True)
class AxisClampStepDecision:
    """Portable result of the recovered two-pass clamp-step helpers.

    The A5D1/A5EA/A5F9/A607 family performs up to two one-pixel axis mutations
    through the original CALL-next/RET-twice idiom.  The pure result records only
    source-level state; the adapter still owns stack scratch and flags.
    """

    start_word: int
    final_word: int
    step_count: int


@dataclass(frozen=True, slots=True)
class VerticalScrollEdgeInput:
    """Pure input snapshot for the recovered A616/A648 scroll-bias helpers."""

    view_y_word: int
    object_y_word: int
    input_bits: int
    top_bias_word: int
    bottom_bias_word: int


@dataclass(frozen=True, slots=True)
class VerticalScrollEdgeDecision:
    """Portable final scroll-bias state after the recovered edge response."""

    top_bias_word: int
    bottom_bias_word: int
    view_gate_open: bool
