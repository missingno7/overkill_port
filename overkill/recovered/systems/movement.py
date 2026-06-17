"""Pure recovered movement systems.

No CPU, memory, DOS segment, hook state, or original continuation is allowed in
this module.  These functions are the portable gameplay decisions behind the
ASM-compatible movement hooks.
"""
from __future__ import annotations

from collections.abc import Sequence

from overkill.recovered.domain.coords import i16, u16
from overkill.recovered.domain.directions import direction8
from overkill.recovered.domain.movement import (
    AxisClampStepDecision,
    MovementStepOperation,
    MovementTarget,
    TargetSeekDecision,
    VerticalScrollEdgeDecision,
    VerticalScrollEdgeInput,
)
from overkill.recovered.domain.object_slots import ObjectSlotRecord

TARGET_GRID_MASK_4PX = 0xFFFC
PLAYER_CENTER_TARGET_X_BIAS = 0x000A
PLAYER_CENTER_TARGET_Y_BIAS = 0x000C
TARGET_SEEK_BLOCKED_SENTINEL = 0x00FF

SCROLL_EDGE_VIEW_Y_GATE = 0x00B6
SCROLL_EDGE_TOP_OBJECT_Y = 0x0000
SCROLL_EDGE_BOTTOM_OBJECT_Y = 0x00B0
SCROLL_EDGE_INPUT_BOTTOM_MASK = 0x01
SCROLL_EDGE_INPUT_TOP_MASK = 0x02
SCROLL_EDGE_TOP_BIAS_MIN = 0xFFF8
SCROLL_EDGE_BOTTOM_BIAS_MAX = 0x0008


def encode_target_seek_bits(slot: ObjectSlotRecord, target: MovementTarget) -> int:
    """Return the raw 5DB2 direction-bit nibble for ``slot`` toward ``target``.

    The Y comparison follows the recovered 8086 routine's unsigned CMP/JB/JA
    branch shape.  The X comparison is signed, matching the original JL/JG pair
    after comparing ``slot.x`` with ``target.x``.
    """
    bits = 0
    y = slot.y_word & 0xFFFF
    target_y = target.y_word & 0xFFFF
    if y < target_y:
        bits = 1
    elif y > target_y:
        bits = 2

    if i16(slot.x_word) < i16(target.x_word):
        bits |= 0x0004
    elif i16(slot.x_word) > i16(target.x_word):
        bits |= 0x0008

    return bits & 0xFFFF


def choose_target_seek_direction(
    slot: ObjectSlotRecord,
    target: MovementTarget,
    direction_table: Sequence[int],
) -> TargetSeekDecision:
    """Map the 5DB2 direction-bit nibble through the recovered direction table."""
    bits = encode_target_seek_bits(slot, target)
    mapped = direction_table[bits & 0x000F] & 0x00FF
    return TargetSeekDecision(
        direction_bits=bits,
        mapped_direction=mapped,
        blocked=mapped == TARGET_SEEK_BLOCKED_SENTINEL,
    )


def step_delta_for_direction(direction: int, pixels: int) -> tuple[int, int]:
    """Return the signed ``(dx, dy)`` for one recovered direction-table step."""
    entry = direction8(direction)
    unit_dx, unit_dy = entry.dx_unit, entry.dy_unit
    return u16(unit_dx * pixels), u16(unit_dy * pixels)


def step_operations_for_direction(direction: int, pixels: int) -> tuple[MovementStepOperation, ...]:
    """Return the ordered source-like mutations for an 8-way movement step.

    AEE4/AF22/AF63 share the same direction table and differ only by pixel
    distance.  Order is part of the recovered semantics because the last ADD/SUB
    owns the live 8086 flags at RET.
    """
    entry = direction8(direction)
    delta = pixels & 0xFFFF
    neg_delta = u16(-pixels)
    ops: list[MovementStepOperation] = []
    for component in entry.components:
        if component == "left":
            ops.append(MovementStepOperation("x", neg_delta))
        elif component == "right":
            ops.append(MovementStepOperation("x", delta))
        elif component == "down":
            ops.append(MovementStepOperation("y", delta))
        elif component == "up":
            ops.append(MovementStepOperation("y", neg_delta))
        else:  # pragma: no cover - Literal exhaustiveness guard for future edits.
            raise AssertionError(f"unsupported direction component {component!r}")
    return tuple(ops)


def align_word_to_four(value_word: int) -> int:
    """Return the recovered 4-pixel grid alignment used by B1B0 target chase."""
    return value_word & TARGET_GRID_MASK_4PX


def player_center_target_from_view(view_x_word: int, view_y_word: int) -> MovementTarget:
    """Pure target point used by B1B0 when chasing the current view/player center.

    The original writes ``DS:237E+0Ah`` to target X and ``DS:2380+0Ch`` to
    target Y, then aligns both words to a 4-pixel grid before calling 5DB2.
    """
    return MovementTarget(
        y_word=align_word_to_four(u16(view_y_word + PLAYER_CENTER_TARGET_Y_BIAS)),
        x_word=align_word_to_four(u16(view_x_word + PLAYER_CENTER_TARGET_X_BIAS)),
    )


def two_pass_axis_clamp_step(
    value_word: int,
    *,
    limit_word: int,
    increment: bool,
    below_condition: bool = False,
) -> AxisClampStepDecision:
    """Pure value update behind A5D1/A5EA/A5F9/A607 clamp-step helpers.

    The original routines execute the compare/step body twice by calling the
    next instruction and then returning into the same body once more.  ``below``
    mode is used by A607's unsigned ``JB`` branch; the other siblings step until
    equality with the boundary.
    """
    value = value_word & 0xFFFF
    limit = limit_word & 0xFFFF
    steps = 0
    for _ in range(2):
        should_step = value < limit if below_condition else value != limit
        if should_step:
            value = u16(value + (1 if increment else -1))
            steps += 1
    return AxisClampStepDecision(
        start_word=value_word & 0xFFFF,
        final_word=value,
        step_count=steps,
    )


def one_pixel_axis_step(value_word: int, *, increment: bool) -> AxisClampStepDecision:
    """Pure one-pixel step used by A5D1 when the global no-clamp gate is set."""
    start = value_word & 0xFFFF
    return AxisClampStepDecision(
        start_word=start,
        final_word=u16(start + (1 if increment else -1)),
        step_count=1,
    )


def recover_top_scroll_bias_a662(top_bias_word: int) -> int:
    """Pure A662 top-bias recovery toward zero."""
    top = top_bias_word & 0xFFFF
    return u16(top + 1) if top != 0 else top


def decay_bottom_scroll_bias_a63c(bottom_bias_word: int) -> int:
    """Pure A63C bottom-bias decay toward zero."""
    bottom = bottom_bias_word & 0xFFFF
    return u16(bottom - 1) if bottom != 0 else bottom


def top_scroll_edge_response_a648(*, object_y_word: int, input_bits: int, top_bias_word: int) -> int:
    """Pure top-edge scroll-bias result recovered from A648/A662."""
    obj_y = object_y_word & 0xFFFF
    bits = input_bits & 0xFF
    top = top_bias_word & 0xFFFF
    if obj_y == SCROLL_EDGE_TOP_OBJECT_Y and (bits & SCROLL_EDGE_INPUT_TOP_MASK) != 0:
        return top if top == SCROLL_EDGE_TOP_BIAS_MIN else u16(top - 1)
    return recover_top_scroll_bias_a662(top)


def bottom_scroll_edge_response_a63c(*, object_y_word: int, input_bits: int, bottom_bias_word: int) -> int:
    """Pure bottom-edge scroll-bias result recovered from A616/A63C."""
    obj_y = object_y_word & 0xFFFF
    bits = input_bits & 0xFF
    bottom = bottom_bias_word & 0xFFFF
    if obj_y == SCROLL_EDGE_BOTTOM_OBJECT_Y and (bits & SCROLL_EDGE_INPUT_BOTTOM_MASK) != 0:
        return bottom if bottom == SCROLL_EDGE_BOTTOM_BIAS_MAX else u16(bottom + 1)
    return decay_bottom_scroll_bias_a63c(bottom)


def vertical_scroll_edge_response_a616(state: VerticalScrollEdgeInput) -> VerticalScrollEdgeDecision:
    """Pure final scroll-bias state recovered from the A616 parent helper.

    A616 first gates on the view/progress word, then runs the top-edge response
    and the bottom-edge response in order.  It does not classify gameplay
    entities; it only models the source-level bias globals constrained by the
    verified helpers.
    """
    if (state.view_y_word & 0xFFFF) <= SCROLL_EDGE_VIEW_Y_GATE:
        return VerticalScrollEdgeDecision(
            top_bias_word=state.top_bias_word & 0xFFFF,
            bottom_bias_word=state.bottom_bias_word & 0xFFFF,
            view_gate_open=False,
        )

    top = top_scroll_edge_response_a648(
        object_y_word=state.object_y_word,
        input_bits=state.input_bits,
        top_bias_word=state.top_bias_word,
    )
    bottom = bottom_scroll_edge_response_a63c(
        object_y_word=state.object_y_word,
        input_bits=state.input_bits,
        bottom_bias_word=state.bottom_bias_word,
    )
    return VerticalScrollEdgeDecision(
        top_bias_word=top,
        bottom_bias_word=bottom,
        view_gate_open=True,
    )
