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
    ChildCoordUpdate,
    DeltaSteerStep,
    MovementStepOperation,
    MovementTarget,
    ObjectDelta5e1b,
    TargetSeekDecision,
    TargetSeekStep,
    VerticalScrollEdgeDecision,
    VerticalScrollEdgeInput,
    ViewAnchorMoveStep,
)
from overkill.recovered.domain.object_slots import ObjectSlotRecord
from overkill.recovered.islands import recovered_island
from overkill.recovered.systems.input import (
    INPUT_DOWN,
    INPUT_LEFT,
    INPUT_RIGHT,
    INPUT_UP,
)

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


@recovered_island(
    asm="1010:5DB2",
    contract="5DB2 direction-bit nibble toward a target (Y unsigned, X signed)",
    status="VERIFIED",
    merge_target="MovementSystem",
)
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


@recovered_island(
    asm="1010:5DB2",
    contract="map the 5DB2 direction-bit nibble through the direction table to a step direction",
    status="VERIFIED",
    merge_target="MovementSystem",
)
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


@recovered_island(
    asm=("1010:AEE4", "1010:AF22", "1010:AF63"),
    contract="signed (dx, dy) for one 8-way direction-table step",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def step_delta_for_direction(direction: int, pixels: int) -> tuple[int, int]:
    """Return the signed ``(dx, dy)`` for one recovered direction-table step."""
    entry = direction8(direction)
    unit_dx, unit_dy = entry.dx_unit, entry.dy_unit
    return u16(unit_dx * pixels), u16(unit_dy * pixels)


@recovered_island(
    asm=("1010:AEE4", "1010:AF22", "1010:AF63"),
    contract="ordered x/y mutations for an 8-way movement step (order = 8086 flag order at RET)",
    status="VERIFIED",
    merge_target="MovementSystem",
)
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


# 1010:5E0C movement-mode dispatch (indexed by DS:2308): mode -> (pixels, repeat) for the step
# routine the table selects.  Recovered from the image: mode 1 -> AF63 (one 2px step), mode 2 ->
# AF60 (two 2px steps), mode 3 -> AEE4 (one 8px step).  Mode 0 (AFA2) and modes >=4 are outside
# the verified set (the 5DB2 lift fails loud on them, so we do too).
MOVEMENT_MODE_STEP_5E0C = {1: (2, 1), 2: (2, 2), 3: (8, 1)}


@recovered_island(
    asm="1010:5DB2",
    contract="whole per-slot 5DB2 target-seek movement: pick direction toward target, then step x/y by 5E0C mode",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def object_target_seek_step_5db2(
    slot_x: int,
    slot_y: int,
    slot_direction: int,
    target: MovementTarget,
    mode: int,
    direction_table: Sequence[int],
) -> TargetSeekStep:
    """Pure whole-5DB2 per-slot movement: the seek direction + the 5E0C mode-dispatched step.

    Picks the direction toward ``target`` (:func:`choose_target_seek_direction`); on the blocked
    branch (mapped FFh) the slot is untouched.  Otherwise writes the mapped direction and steps
    ``x``/``y`` by it, the step distance chosen from the recovered 5E0C table by ``mode``
    (:data:`MOVEMENT_MODE_STEP_5E0C`; AF60's double step is ``repeat=2``).  ``slot_x``/``slot_y``
    are the slot's current position (and the seek inputs); ``slot_direction`` is the slot's current
    ``direction_or_step`` (returned unchanged when blocked).  Models only the slot fields 5DB2
    mutates (+06/+02/+04) -- the DS:A954 direction-bit and DS:230A blocked globals are separate
    state.  Shared by every 5DB2 caller (B729/D281/B1B0 and the b73e/b9f0/8d4f behaviors)."""
    x = slot_x & 0xFFFF
    y = slot_y & 0xFFFF
    decision = choose_target_seek_direction(
        ObjectSlotRecord(
            active_word=0, x_word=x, y_word=y, gate_or_layer=0, link_key=0,
            scan_flag=0, hazard_class=0, logic_id=0, target_x_word=0, target_y_word=0,
        ),
        target,
        direction_table,
    )
    if decision.blocked:
        return TargetSeekStep(slot_direction & 0xFFFF, x, y, blocked=True)
    if mode not in MOVEMENT_MODE_STEP_5E0C:
        raise ValueError(f"unverified 5DB2 movement mode {mode & 0xFFFF:#06x} (5E0C dispatch)")
    pixels, repeat = MOVEMENT_MODE_STEP_5E0C[mode]
    for _ in range(repeat):
        for op in step_operations_for_direction(decision.mapped_direction, pixels):
            delta = i16(op.delta_word)
            if op.axis == "x":
                x = u16(x + delta)
            else:
                y = u16(y + delta)
    return TargetSeekStep(decision.mapped_direction & 0xFFFF, x, y, blocked=False)


# 1010:5E42 delta-steer constants.  The DS:A348 direction bits are y-axis (+1 up / +2 down) | x-axis
# (+4 left / +8 right), set per the delta signs; A348 maps the bit set to a direction or FFh (blocked).
STEER_BIT_Y_NEG = 0x0001
STEER_BIT_Y_POS = 0x0002
STEER_BIT_X_NEG = 0x0004
STEER_BIT_X_POS = 0x0008
STEER_BLOCKED_SENTINEL = 0x00FF
STEER_FAST_STEP_MODE = 0x0003   # DS:2312 == 3 -> AF22 3px step; else AF63 2px


@recovered_island(
    asm="1010:5E1B",
    contract="object-delta helper: signed per-axis deltas = slot - (target + pad), pad 4px solid else 12px",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def object_delta_5e1b(
    slot_x: int,
    slot_y: int,
    target_x: int,
    target_y: int,
    target_scan_flag: int,
) -> ObjectDelta5e1b:
    """Pure whole-5E1B object-delta helper (the input :func:`object_delta_steer_5e42` consumes).

    Fills the slot's signed Y/X movement deltas (+2C/+2A) relative to a target/reference record:
    ``delta = slot - (target + pad)`` per axis, where ``pad`` is 4px when the target is solid (its
    scan flag +14 == 1) else 12px (the same pad for both axes).  Matches the original's
    ``ADD CX,DX`` / ``SUB AX,CX`` order with 16-bit wrap.

    Inputs: the slot's X/Y and the target record's X (+02), Y (+04), and scan flag (+14).
    Output: the two signed delta words.  No CPU/memory -- the adapter owns SS:BP / DS:BX.
    """
    pad = 0x0004 if (target_scan_flag & 0xFFFF) == 0x0001 else 0x000C
    move_delta_y = u16(slot_y - u16(target_y + pad))
    move_delta_x = u16(slot_x - u16(target_x + pad))
    return ObjectDelta5e1b(move_delta_x=move_delta_x, move_delta_y=move_delta_y)


@recovered_island(
    asm="1010:5E42",
    contract="runtime-patched delta-steer: signed deltas -> Bresenham axis pick -> A348 direction -> step",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def object_delta_steer_5e42(
    slot_x: int,
    slot_y: int,
    slot_direction: int,
    move_delta_y: int,
    move_delta_x: int,
    move_step_error: int,
    step_mode: int,
    direction_table: Sequence[int],
) -> DeltaSteerStep:
    """Pure whole-5E42 per-slot delta-steer (the runtime-patched gameplay steering helper).

    Takes the slot's signed Y/X movement deltas (+2C/+2A), the ``move_step_error`` accumulator (+2E),
    the ``step_mode`` (DS:2312), and the DS:A348 direction table.  Picks which axes advance this frame
    by a Bresenham comparison of the deltas' magnitudes against the accumulator: the major axis always
    steps, and the minor axis steps when the accumulator overflows the major magnitude (and the
    accumulator is then reduced).  The per-axis direction bits (set from the delta signs) index A348 to
    a direction; on the FFh sentinel the steer is blocked (direction + x/y untouched, but the
    accumulator is still advanced).  Otherwise it steps x/y by that direction (AF22 3px when
    ``step_mode==3`` else AF63 2px).  Models only the slot fields 5E42 mutates (+06/+2E/+02/+04)."""
    dy = move_delta_y & 0xFFFF
    dx = move_delta_x & 0xFFFF
    dy_neg = (dy & 0x8000) != 0
    dx_neg = (dx & 0x8000) != 0
    ady = u16(-dy) if dy_neg else dy   # 8086 NEG = (-v) & 0xFFFF (abs for a signed word)
    adx = u16(-dx) if dx_neg else dx
    y_bit = STEER_BIT_Y_NEG if dy_neg else STEER_BIT_Y_POS
    x_bit = STEER_BIT_X_NEG if dx_neg else STEER_BIT_X_POS

    err = move_step_error & 0xFFFF
    if ady == adx:
        bits = y_bit | x_bit
    elif ady > adx:                       # y is the major axis
        err = u16(err + adx)
        if err <= ady:
            bits = y_bit
        else:
            err = u16(err - ady)
            bits = y_bit | x_bit
    else:                                 # x is the major axis
        err = u16(err + ady)
        if err <= adx:
            bits = x_bit
        else:
            err = u16(err - adx)
            bits = y_bit | x_bit

    direction = direction_table[bits & 0x00FF] & 0x00FF
    x = slot_x & 0xFFFF
    y = slot_y & 0xFFFF
    if direction == STEER_BLOCKED_SENTINEL:
        return DeltaSteerStep(slot_direction & 0xFFFF, err, x, y, blocked=True)

    pixels = 3 if (step_mode & 0xFFFF) == STEER_FAST_STEP_MODE else 2
    for op in step_operations_for_direction(direction, pixels):
        delta = i16(op.delta_word)
        if op.axis == "x":
            x = u16(x + delta)
        else:
            y = u16(y + delta)
    return DeltaSteerStep(direction & 0xFFFF, err, x, y, blocked=False)


@recovered_island(
    asm="1010:B1B0",
    contract="4-pixel grid alignment of a coordinate word",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def align_word_to_four(value_word: int) -> int:
    """Return the recovered 4-pixel grid alignment used by B1B0 target chase."""
    return value_word & TARGET_GRID_MASK_4PX


@recovered_island(
    asm="1010:B1B0",
    contract="player/view-centre chase target (237E+0Ah, 2380+0Ch, 4-pixel aligned)",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def player_center_target_from_view(view_x_word: int, view_y_word: int) -> MovementTarget:
    """Pure target point used by B1B0 when chasing the current view/player center.

    The original writes ``DS:237E+0Ah`` to target X and ``DS:2380+0Ch`` to
    target Y, then aligns both words to a 4-pixel grid before calling 5DB2.
    """
    return MovementTarget(
        y_word=align_word_to_four(u16(view_y_word + PLAYER_CENTER_TARGET_Y_BIAS)),
        x_word=align_word_to_four(u16(view_x_word + PLAYER_CENTER_TARGET_X_BIAS)),
    )


# The object playfield clamp bounds passed to two_pass_axis_clamp_step by the four
# A5D1/A5EA/A5F9/A607 step helpers: X is confined to [20h, C0h], Y to [00h, B0h].
OBJECT_CLAMP_X_MIN = 0x0020   # 1010:A5D1 leftward step floor
OBJECT_CLAMP_X_MAX = 0x00C0   # 1010:A5EA rightward step ceiling
OBJECT_CLAMP_Y_MIN = 0x0000   # 1010:A5F9 upward step floor
OBJECT_CLAMP_Y_MAX = 0x00B0   # 1010:A607 downward step ceiling


@recovered_island(
    asm=("1010:A5D1", "1010:A5EA", "1010:A5F9", "1010:A607"),
    contract="two-pass clamp/step of an axis word toward a boundary",
    status="VERIFIED",
    merge_target="MovementSystem",
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


@recovered_island(
    asm="1010:A5D1",
    contract="single-pixel axis step when the no-clamp global gate is set",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def one_pixel_axis_step(value_word: int, *, increment: bool) -> AxisClampStepDecision:
    """Pure one-pixel step used by A5D1 when the global no-clamp gate is set."""
    start = value_word & 0xFFFF
    return AxisClampStepDecision(
        start_word=start,
        final_word=u16(start + (1 if increment else -1)),
        step_count=1,
    )


@recovered_island(
    asm=("1010:9B6F", "1010:9B79", "1010:9B83", "1010:9B8D"),
    contract="9B2E movement-bits stage: apply held direction input to the view-anchor "
             "position via the four A5D1/A5EA/A5F9/A607 axis clamp-steps",
    status="VERIFIED",
    merge_target="FrameLoop",
)
def step_view_anchor_by_input(
    x_word: int, y_word: int, input_flags: int, *, no_clamp: bool
) -> ViewAnchorMoveStep:
    """The 9B2E movement-bits stage, composed from the verified axis clamp-steps.

    Frames 9B6F..9B94 of the game-state controller test the four direction bits of
    DS:98BE and, for each held bit, step the player-controlled view-anchor slot
    (DS:237C) one of four ways.  The screen axes are transposed relative to the
    controls (the up/down controls move the slot's X word, left/right its Y):

      * up    (``INPUT_UP``    0x08, A5D1): X toward 0x20 -- or one unclamped pixel
        when the global no-clamp gate DS:A47C is set;
      * down  (``INPUT_DOWN``  0x04, A5EA): X toward 0xC0;
      * right (``INPUT_RIGHT`` 0x01, A607): Y toward 0xB0 (unsigned ``below`` test);
      * left  (``INPUT_LEFT``  0x02, A5F9): Y toward 0x00.

    The bits are applied in the original 9B2E order (up, down, right, left) so two
    opposed directions in one frame resolve exactly as the VM resolves them.  Only
    A5D1 consults the no-clamp gate; the other three always two-pass clamp.
    """
    x = x_word & 0xFFFF
    y = y_word & 0xFFFF
    stepped = False
    if input_flags & INPUT_UP:        # A5D1
        if no_clamp:
            x = one_pixel_axis_step(x, increment=False).final_word
        else:
            x = two_pass_axis_clamp_step(x, limit_word=OBJECT_CLAMP_X_MIN, increment=False).final_word
        stepped = True
    if input_flags & INPUT_DOWN:      # A5EA
        x = two_pass_axis_clamp_step(x, limit_word=OBJECT_CLAMP_X_MAX, increment=True).final_word
        stepped = True
    if input_flags & INPUT_RIGHT:     # A607
        y = two_pass_axis_clamp_step(y, limit_word=OBJECT_CLAMP_Y_MAX, increment=True,
                                     below_condition=True).final_word
        stepped = True
    if input_flags & INPUT_LEFT:      # A5F9
        y = two_pass_axis_clamp_step(y, limit_word=OBJECT_CLAMP_Y_MIN, increment=False).final_word
        stepped = True
    return ViewAnchorMoveStep(x_word=x, y_word=y, stepped=stepped)


CHILD_COORD_Y_MAX = 0x00C0  # 9FEA clamps the child Y into 0..0x00C0 (inclusive)


@recovered_island(
    asm="1010:9FEA",
    contract="linked/child object coordinate update: base + table delta + 2x vertical scroll bias, Y clamped 0..00C0",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def object_child_coord_update_9fea(
    *, source_x: int, source_y: int, x_delta: int, y_delta: int, scroll_bias: int
) -> ChildCoordUpdate:
    """Pure 1010:9FEA child coordinate decision.

    The child's X is the parent's X plus the table X delta.  Its Y is the parent's Y plus
    the table Y delta plus the world vertical scroll bias (DS:A398) applied **twice**, then
    clamped into ``0..0x00C0``: a Y that goes negative (bit 15 set) clamps to 0 (lower), and a
    positive Y above 0x00C0 clamps to 0x00C0 (upper).  ``scroll_bias`` is one DS:A398 word;
    the doubling is the ASM's two sequential adds.
    """
    x_word = (x_delta + source_x) & 0xFFFF
    y_word = (y_delta + source_y + 2 * scroll_bias) & 0xFFFF
    if y_word & 0x8000:
        return ChildCoordUpdate(x_word=x_word, y_word=0x0000, lower_clamped=True, upper_clamped=False)
    if y_word > CHILD_COORD_Y_MAX:
        return ChildCoordUpdate(x_word=x_word, y_word=CHILD_COORD_Y_MAX, lower_clamped=False, upper_clamped=True)
    return ChildCoordUpdate(x_word=x_word, y_word=y_word, lower_clamped=False, upper_clamped=False)


@recovered_island(
    asm="1010:A662",
    contract="top scroll-bias recovery toward zero",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def recover_top_scroll_bias_a662(top_bias_word: int) -> int:
    """Pure A662 top-bias recovery toward zero."""
    top = top_bias_word & 0xFFFF
    return u16(top + 1) if top != 0 else top


@recovered_island(
    asm="1010:A63C",
    contract="bottom scroll-bias decay toward zero",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def decay_bottom_scroll_bias_a63c(bottom_bias_word: int) -> int:
    """Pure A63C bottom-bias decay toward zero."""
    bottom = bottom_bias_word & 0xFFFF
    return u16(bottom - 1) if bottom != 0 else bottom


@recovered_island(
    asm=("1010:A648", "1010:A662"),
    contract="top-edge scroll-bias response to input at the screen top",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def top_scroll_edge_response_a648(*, object_y_word: int, input_bits: int, top_bias_word: int) -> int:
    """Pure top-edge scroll-bias result recovered from A648/A662."""
    obj_y = object_y_word & 0xFFFF
    bits = input_bits & 0xFF
    top = top_bias_word & 0xFFFF
    if obj_y == SCROLL_EDGE_TOP_OBJECT_Y and (bits & SCROLL_EDGE_INPUT_TOP_MASK) != 0:
        return top if top == SCROLL_EDGE_TOP_BIAS_MIN else u16(top - 1)
    return recover_top_scroll_bias_a662(top)


@recovered_island(
    asm=("1010:A616", "1010:A63C"),
    contract="bottom-edge scroll-bias response to input at the screen bottom",
    status="VERIFIED",
    merge_target="MovementSystem",
)
def bottom_scroll_edge_response_a63c(*, object_y_word: int, input_bits: int, bottom_bias_word: int) -> int:
    """Pure bottom-edge scroll-bias result recovered from A616/A63C."""
    obj_y = object_y_word & 0xFFFF
    bits = input_bits & 0xFF
    bottom = bottom_bias_word & 0xFFFF
    if obj_y == SCROLL_EDGE_BOTTOM_OBJECT_Y and (bits & SCROLL_EDGE_INPUT_BOTTOM_MASK) != 0:
        return bottom if bottom == SCROLL_EDGE_BOTTOM_BIAS_MAX else u16(bottom + 1)
    return decay_bottom_scroll_bias_a63c(bottom)


@recovered_island(
    asm="1010:A616",
    contract="view-gated top+bottom scroll-bias state update",
    status="VERIFIED",
    merge_target="MovementSystem",
)
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
