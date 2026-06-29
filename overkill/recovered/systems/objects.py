"""Pure recovered object-system predicates.

No CPU, memory, DOS segment, hook state, or original continuation is allowed in
this module.  These predicates name gameplay decisions once multiple hooks or
traces have constrained their object-slot fields.
"""
from __future__ import annotations

from overkill.recovered.domain.coords import i16, u16
from overkill.recovered.domain.object_behaviors import (
    Ab10Update,
    Aba3Update,
    Ae09MovementStep,
    Ae09Update,
    B73ETargetReachedResolution,
    BossGroupSlotTransition,
    ObjectBoundsTileDecision,
    ObjectDeactivateDispatchDecision,
)
from overkill.recovered.domain.object_slots import (
    FreeSlotAllocation,
    ObjectPool,
    ObjectSlotRecord,
    ObjectSpawnSeed,
    ObjectSpawnSeedA4EA,
)
from overkill.recovered.systems.movement import step_operations_for_direction

# 1010:8209 object-slot spawn template.  Stamps a freshly allocated effect slot
# with a fixed logic-id-14h object at the caller's source position.
OBJECT_SPAWN_SEED_8209_LOGIC_ID = 0x0014
OBJECT_SPAWN_SEED_8209_LINKED_COUNTER_INDEX_NONE = 0xFFFF


def object_spawn_seed_8209(source_x: int, source_y: int) -> ObjectSpawnSeed:
    """Pure 1010:8209 spawn template recovered from the 8209..8247 stamp.

    A new effect slot is initialised as an active ``logic_id=0014h`` object at the
    caller's source ``(X, Y)``, with position and target both set to that source,
    ``direction_or_step=4``, ``hazard_class=4``, ``scan_flag=1``, ``gate=1``,
    ``counter_20=4``, ``variant=0``, and the linked-counter index cleared to
    ``FFFFh`` (no link).  The hook owns the DOS slot pointer and write order; this owns the
    field values.
    """
    x = source_x & 0xFFFF
    y = source_y & 0xFFFF
    return ObjectSpawnSeed(
        active_word=0x0001,
        gate_or_layer=0x0001,
        x_word=x,
        y_word=y,
        direction_or_step=0x0004,
        scan_flag=0x0001,
        hazard_class=0x0004,
        logic_id=OBJECT_SPAWN_SEED_8209_LOGIC_ID,
        counter_20=0x0004,
        variant=0x0000,
        target_x_word=x,
        target_y_word=y,
        linked_counter_index=OBJECT_SPAWN_SEED_8209_LINKED_COUNTER_INDEX_NONE,
    )


# 1010:A4EA object-slot spawn template.  Unlike 8209 this routine allocates its
# own slot first (its leading ``call 7547``); the stamp itself is all constants.
OBJECT_SPAWN_SEED_A4EA_LOGIC_ID = 0x0002


def object_spawn_seed_a4ea() -> ObjectSpawnSeedA4EA:
    """Pure 1010:A4EA spawn template recovered from the A4ED..A50F stamp.

    A freshly allocated slot is initialised as an active ``logic_id=2`` object
    with ``scan_enable_or_solid=1``, ``direction_or_step=0``,
    ``sprite_or_state=32h``, ``scan_flag=0``, ``hazard_class=2`` and
    ``substate=FFFFh``.  The adapter owns the leading allocation and the DOS slot
    pointer; this owns the field values.
    """
    return ObjectSpawnSeedA4EA(
        active_word=0x0001,
        scan_enable_or_solid=0x0001,
        direction_or_step=0x0000,
        sprite_or_state=0x0032,
        scan_flag=0x0000,
        hazard_class=0x0002,
        logic_id=OBJECT_SPAWN_SEED_A4EA_LOGIC_ID,
        substate=0xFFFF,
    )


# 1010:B73E no-substate idle-phase rules.  These are the pure gameplay
# decisions the B73E behavior makes once it is on the FFFFh-substate path,
# recovered as source-level formulas rather than inline ASM arithmetic.
B73E_IDLE_LOW_Y_THRESHOLD = 0x0060
B73E_IDLE_LOW_Y_FRAME_BASE = 0x007F
B73E_IDLE_HIGH_Y_FRAME_BASE = 0x007A
B73E_SPAWN_WINDOW_MIN = 0x02BC
B73E_SPAWN_WINDOW_MAX = 0x02D0


def b73e_idle_sprite_frame(timer: int, y: int) -> int:
    """Pure B73E idle animation-frame selection from the DS:2338 timer.

    The original picks the sprite/animation frame from the shared DS:2338 timer
    with a sign flip for objects above the ``0060h`` Y line: high objects count
    down from ``007Fh`` (``007Fh - timer``), low objects count up from ``007Ah``
    (``timer + 007Ah``).  Returns the 16-bit frame value written to the object's
    sprite/state field.  The adapter still replays the NEG/ADD so 8086 flags
    match the oracle.
    """
    t = timer & 0xFFFF
    if (y & 0xFFFF) < B73E_IDLE_LOW_Y_THRESHOLD:
        return (B73E_IDLE_LOW_Y_FRAME_BASE - t) & 0xFFFF
    return (t + B73E_IDLE_HIGH_Y_FRAME_BASE) & 0xFFFF


B73E_TARGET_RESET_A47E_MAX = 0x0003
B73E_TARGET_RESET_DIRECT_COUNTER_MAX = 0x0005
B73E_TARGET_POSTMOVE_232E_SENTINEL = 0x003F


def b73e_target_reached_resolution(a47e: int, game_counter: int, value_232e: int) -> "B73ETargetReachedResolution":
    """Pure B7BD/B808 dispatch once a B73E object is at its target.

    See :class:`B73ETargetReachedResolution`.  The hook still replays the
    original CMP order so live 8086 flags match the oracle at each branch; this
    function owns the stable 4-way classification.
    """
    if (a47e & 0xFFFF) <= B73E_TARGET_RESET_A47E_MAX:
        return B73ETargetReachedResolution("reset_target_check_2324")
    if (game_counter & 0xFFFF) < B73E_TARGET_RESET_DIRECT_COUNTER_MAX:
        return B73ETargetReachedResolution("reset_target_direct")
    if (value_232e & 0xFFFF) != B73E_TARGET_POSTMOVE_232E_SENTINEL:
        return B73ETargetReachedResolution("postmove")
    return B73ETargetReachedResolution("waypoint_loop")


def b73e_reaches_b808(game_counter: int) -> bool:
    """Pure B73E spawn-window gate recovered from the DS:2340 counter band.

    When the game counter is inside the ``[02BCh, 02D0h]`` band the behavior runs
    the formation spawn-pointer advance at B800; otherwise control reaches B808
    and skips it.  ``True`` means "skip the spawn block" (reaches B808).  The
    adapter keeps the original two-compare order so live flags match the oracle.
    """
    gc = game_counter & 0xFFFF
    return gc < B73E_SPAWN_WINDOW_MIN or gc > B73E_SPAWN_WINDOW_MAX


# 1010:B86D common-path rules.  B86D schedules formation spawns on exact ticks
# of the shared DS:2340 game counter, and picks its outgoing sprite from the sign
# of the global vertical delta DS:2342.  Pure source-level rules; the hook keeps
# the CMP order and owns the 7476 continuation addresses.
B86D_FORMATION_SPAWN_TICKS = (0x02EF, 0x0159, 0x0079)
B86D_OUTGOING_SPRITE_RISING = 0x0075
B86D_OUTGOING_SPRITE_FALLING = 0x0076
B86D_VERTICAL_DELTA_RISING = 0xFFFF


def b86d_formation_spawn_tick_index(game_counter: int) -> int | None:
    """Pure B86D formation-spawn schedule from the DS:2340 counter.

    A formation spawn (CALL 7476) fires only on the exact counter ticks in
    ``B86D_FORMATION_SPAWN_TICKS``; returns the matching variant index (0/1/2) or
    ``None`` when no spawn is scheduled this tick.  The hook still replays the
    chained CMP/JE order and maps the index to the 7476 return address.
    """
    gc = game_counter & 0xFFFF
    for index, tick in enumerate(B86D_FORMATION_SPAWN_TICKS):
        if gc == tick:
            return index
    return None


def b86d_outgoing_sprite_for_delta(vertical_delta: int) -> int:
    """Pure B86D outgoing-sprite selection from the global vertical delta DS:2342.

    A delta of ``FFFFh`` (one pixel up) keeps the rising sprite ``0075h``; any
    other delta uses the falling sprite ``0076h``.  The hook keeps the NEG and
    CMP so 8086 flags match the oracle.
    """
    if (vertical_delta & 0xFFFF) == B86D_VERTICAL_DELTA_RISING:
        return B86D_OUTGOING_SPRITE_RISING
    return B86D_OUTGOING_SPRITE_FALLING


# 1010:AB10 logic_id=6 per-frame update.  The object dies once the level frame
# phase (DS:2384) or the global disable counter (DS:A47C) reaches 0003h; otherwise
# its sprite is the DS:A40C animation byte + 9 and its position is the DS:A414
# animation pair offset by the DS:237C view reference box.
LEVEL_PHASE_DISABLE_THRESHOLD = 0x0003


def level_disable_threshold_reached(value: int) -> bool:
    """True once a level disable counter -- the frame phase ``DS:2384`` or the global
    disable counter ``DS:A47C`` -- has advanced to ``0003h``.  This is the shared
    gate behind several object behaviors (AB10 deactivates, ABA3 branches to ABC0,
    AB77 branches to AB8F): at/after this phase the object stops its normal update."""
    return (value & 0xFFFF) >= LEVEL_PHASE_DISABLE_THRESHOLD


AB10_SPRITE_BASE_OFFSET = 0x0009


def object_logic_ab10(
    frame_phase: int,
    global_disable: int,
    sprite_table_value: int,
    anim_x: int,
    anim_y: int,
    ref_x: int,
    ref_y: int,
) -> Ab10Update:
    """Pure 1010:AB10 update recovered from the AA2B logic_id=6 target.

    ``sprite_table_value`` is the ``DS:A40C[DS:2336]`` animation byte; ``anim_x`` /
    ``anim_y`` are the ``DS:A414`` animation-pair words for the current phase; ``ref_x``
    / ``ref_y`` are the view reference box ``DS:237E`` / ``DS:2380``.  The adapter still
    replays the original CMP order (deactivate-path flags) and the live final ADD
    flags; this owns the deactivate gate and the sprite/position formulas."""
    if level_disable_threshold_reached(frame_phase) or level_disable_threshold_reached(global_disable):
        return Ab10Update(deactivate=True)
    return Ab10Update(
        deactivate=False,
        sprite=(sprite_table_value + AB10_SPRITE_BASE_OFFSET) & 0xFFFF,
        x=(anim_x + ref_x) & 0xFFFF,
        y=(anim_y + ref_y) & 0xFFFF,
    )


AE09_SPRITE_OFFSET = 0x0028


def object_logic_ae09(substate: int, direction_or_step: int) -> Ae09Update:
    """Pure 1010:AE09 update recovered from the EFAE logic_id 0Ch behavior body.

    ``substate`` is the slot countdown timer (DS:[bp+1Ch]); ``direction_or_step`` is
    DS:[bp+6].  While the timer is non-zero it decrements, clearing the direction on
    the frame it reaches zero; the object steps left (``x -= 2``) on the frame the
    timer is zero or has just expired; the outgoing sprite is
    ``direction_or_step + 28h``.  The original's CMP/DEC/SUB/ADD flags are all dead
    at the AF22 tail boundary (AF22's first ops overwrite them), so the adapter needs
    no flag replay -- this rule owns the timer/step/sprite decision."""
    substate &= 0xFFFF
    direction = direction_or_step & 0xFFFF
    new_substate = substate
    if substate != 0:
        new_substate = (substate - 1) & 0xFFFF
        if new_substate == 0:
            direction = 0x0000
    return Ae09Update(
        substate=new_substate,
        direction_or_step=direction,
        decrement_x=(substate == 0 or new_substate == 0),
        sprite=(direction + AE09_SPRITE_OFFSET) & 0xFFFF,
    )


def object_movement_step_ae09(
    substate: int, direction_or_step: int, x_word: int, y_word: int
) -> Ae09MovementStep:
    """Pure per-slot movement transform for the whole 1010:AE09 behavior (logic_id 0Ch).

    Composes the AE09 timer/step decision (:func:`object_logic_ae09`) with the AF22 3-pixel
    direction step that AE09 tails into: apply the optional ``x -= 2`` (``decrement_x``), then
    the 8-way direction step (:func:`step_operations_for_direction`) for the
    (possibly-cleared) ``direction_or_step``.  Returns the slot's post-frame movement fields.

    The AD60 bounds tail + the BD17 deactivation / global side-effects do NOT touch these five
    fields (AD60 only sets the slot ``active`` word and global counters; AE09 passes
    ``add_a278_to_x=False``), so this is the clean native producer for AE09's movement half --
    verifiable produced-vs-VM at AE09's return.  Direction is AF22's verified 0..7 range
    (``object_logic_ae09`` yields the original direction or 0)."""
    upd = object_logic_ae09(substate, direction_or_step)
    x = u16(x_word - 2) if upd.decrement_x else (x_word & 0xFFFF)
    y = y_word & 0xFFFF
    for op in step_operations_for_direction(upd.direction_or_step, 3):
        delta = i16(op.delta_word)
        if op.axis == "x":
            x = u16(x + delta)
        else:
            y = u16(y + delta)
    return Ae09MovementStep(
        substate=upd.substate,
        direction_or_step=upd.direction_or_step,
        sprite_or_state=upd.sprite,
        x_word=x,
        y_word=y,
    )


ABA3_SPRITE_OFFSET = 0x0014


def contact_fanout_count(logic_id: int, fanout_selector: int) -> int:
    """Number of B250 post-contact 9E19 fan-out iterations (the CX loop count).

    ``logic_id`` is the slot's logic id; ``fanout_selector`` is the contact fan-out
    selector DS:BEDC (the difficulty counter).  Logic-id-3 objects scale the count
    with difficulty -- ``0 -> 1``, ``1 -> 3``, otherwise ``5`` -- while every other
    object fans out exactly once."""
    if (logic_id & 0xFFFF) != 0x0003:
        return 1
    selector = fanout_selector & 0xFFFF
    if selector == 0x0000:
        return 1
    if selector == 0x0001:
        return 3
    return 5


def object_logic_aba3(frame_phase: int, scroll_frame: int) -> Aba3Update:
    """Pure 1010:ABA3 decision recovered from the AD04 tracked-object follower.

    ``frame_phase`` is DS:2384; ``scroll_frame`` is DS:233C.  When the level frame
    phase has advanced to ``0003h`` the follower branches to ABC0; otherwise the
    outgoing sprite is ``scroll_frame + 14h``.  This owns the gate decision and the
    sprite formula; the adapter still replays the gate CMP flags for boundary
    fidelity (the sprite ADD flags are dead -- the AC81 call overwrites them)."""
    if level_disable_threshold_reached(frame_phase):
        return Aba3Update(branch_abc0=True)
    return Aba3Update(branch_abc0=False, sprite=(scroll_frame + ABA3_SPRITE_OFFSET) & 0xFFFF)


# Global render-state shared by the A8C7 layer-1 scan and the AD04 logic branch: the
# render mode word DS:BDAC (``1`` = full redraw, no near-camera culling) and the camera
# position DS:2350 (``<= B6h`` = near the left edge).
RENDER_MODE_FULL = 0x0001
CAMERA_NEAR_THRESHOLD = 0x00B6
LAYER1_LAYER_FOREGROUND = 0x0001
# AD04 routes a slot whose sprite/state word equals 0Fh to the ABCA collision handler.
AD04_SPRITE_COLLISION_STATE = 0x000F


def camera_near_outside_full_render(render_mode: int, camera_x: int) -> bool:
    """True when not in full-render mode and the camera sits near the left edge.

    ``render_mode`` is DS:BDAC, ``camera_x`` is DS:2350.  This is the shared near-camera
    gate behind two routines: the A8C7 layer-1 scan suppresses a near-layer slot under
    it, and the AD04 logic branch returns early under it."""
    return (render_mode & 0xFFFF) != RENDER_MODE_FULL and (camera_x & 0xFFFF) <= CAMERA_NEAR_THRESHOLD


def layer1_scan_should_draw(slot: ObjectSlotRecord, render_mode: int, camera_x: int) -> bool:
    """True when the 1010:A8C7 layer-1 scan should issue ``CALL 7596`` for ``slot``.

    Native-state form (Phase 2): takes the slot's :class:`ObjectSlotRecord` plus the two
    globals ``render_mode`` (DS:BDAC) and ``camera_x`` (DS:2350).  In the layer-1 scan
    context the slot's near-layer flag is its ``hazard_class`` word (SS:[bp+16h], the
    ``OFF_DRAW_LAYER`` alias) and its object layer is ``gate_or_layer`` (SS:[bp+0Ah]).  An
    inactive slot never draws.  A near-camera slot
    (:func:`camera_near_outside_full_render`) flagged for the near layer is suppressed.
    Otherwise the slot draws iff it is on the foreground layer.  The adapter still replays
    the per-branch CMP flags for boundary fidelity; this owns the draw decision."""
    if (slot.active_word & 0xFFFF) == 0:
        return False
    if camera_near_outside_full_render(render_mode, camera_x) and (slot.hazard_class & 0xFFFF) == 1:
        return False
    return (slot.gate_or_layer & 0xFFFF) == LAYER1_LAYER_FOREGROUND


# B9F0's horizontal play-area right edge (D0h), shared by both of its X wraps: the
# accumulated target X resets to 20h past it, while the live X resets to a tighter 10h.
B9F0_X_RIGHT_EDGE = 0x00D0
B9F0_TARGET_X_WRAP_RESET = 0x0020
B9F0_X_OVERFLOW_RESET = 0x0010


def b9f0_wrapped_target_x(target_x: int) -> int:
    """The B9F0 follower's target-X after the right-edge wrap (1010:BA13).

    Once the accumulated target X passes the right edge (``> D0h``) it wraps back to the
    left edge (``20h``); otherwise it is unchanged."""
    if (target_x & 0xFFFF) > B9F0_X_RIGHT_EDGE:
        return B9F0_TARGET_X_WRAP_RESET
    return target_x & 0xFFFF


def b9f0_wrapped_x_on_overflow(x: int) -> int:
    """The B9F0 follower's live X after the overshoot-path right-edge wrap (1010:BAB7).

    Once the object's actual X passes the right edge it wraps to 10h -- a tighter left
    margin than the target-X wrap's 20h; otherwise it is unchanged."""
    if (x & 0xFFFF) > B9F0_X_RIGHT_EDGE:
        return B9F0_X_OVERFLOW_RESET
    return x & 0xFFFF


def b9f0_reached_target(slot: ObjectSlotRecord, vertical_delta: int) -> bool:
    """True when the B9F0 follower has reached its target tile (1010:BA1F).

    Native-state form (Phase 2): takes the slot's :class:`ObjectSlotRecord` plus the global
    vertical delta DS:2342.  Reached when the object's Y plus the vertical delta equals the
    target Y *and* its X already equals the target X.  This is the central B9F0 branch: on
    a hit it refreshes the sprite / runs the movement helper, otherwise it routes to BA99.
    The adapter still replays the AX writes and CMP flags around it; this owns the
    decision."""
    return (
        ((slot.y_word + vertical_delta) & 0xFFFF) == (slot.target_y_word & 0xFFFF)
        and (slot.x_word & 0xFFFF) == (slot.target_x_word & 0xFFFF)
    )


B9F0_HELPER_COUNTER_LIMIT = 0x0006


def b9f0_low_counter_runs_helper(counter: int) -> bool:
    """True when the B9F0 follower's level counter DS:A47E is still below 6 (1010:BA33).

    Below this limit B9F0 unconditionally runs its BA5A motion helper; at/above it the
    helper is gated by the periodic difficulty-tick test instead.  Both the reached-target
    and the overshoot branch share this gate."""
    return (counter & 0xFFFF) < B9F0_HELPER_COUNTER_LIMIT


B9F0_HELPER_DIFFICULTY_FAST = 0x0002
B9F0_HELPER_TICK_MASK_FAST = 0x007F
B9F0_HELPER_TICK_MASK_SLOW = 0x00FF


def b9f0_periodic_helper_mask(difficulty: int) -> int:
    """The DS:2340 tick mask gating B9F0's periodic BA5A helper (1010:BA3D).

    On the fast difficulty (DS:BEDC == 2) the helper fires every 128th tick (mask 7Fh);
    otherwise every 256th (mask FFh).  The helper runs when ``tick & mask == mask`` -- the
    tick counter is at the top of its period."""
    if (difficulty & 0xFFFF) == B9F0_HELPER_DIFFICULTY_FAST:
        return B9F0_HELPER_TICK_MASK_FAST
    return B9F0_HELPER_TICK_MASK_SLOW


B9F0_SPAWN_COUNTER_TRIGGER = 0x003F


def b9f0_spawn_counter_ready(counter: int) -> bool:
    """True when B9F0's overshoot spawn counter DS:232E is at 3Fh (1010:BAAD).

    On the overshoot path, once the low-counter helper gate is open, the formation spawn
    (7476) fires only when this counter has reached the top of its 0..3Fh cycle."""
    return (counter & 0xFFFF) == B9F0_SPAWN_COUNTER_TRIGGER


B9F0_SPRITE_FRAME_OFFSET = 0x001C


def b9f0_sprite_from_frame(frame: int) -> int:
    """B9F0's sprite/animation word on the BA67 tail: the global frame DS:233C + 1Ch."""
    return (frame + B9F0_SPRITE_FRAME_OFFSET) & 0xFFFF


PLAYER_CHASE_EXCLUDED_LOGIC_IDS = frozenset({0x0001, 0x0021, 0x0022, 0x0026})
PLAYER_CHASE_CANDIDATE_MAX_X = 0x00E0
PLAYER_CHASE_REQUIRED_HAZARD_CLASS = 0x0004
PLAYER_CHASE_ACQUIRED_MAX_X = 0x00DC
PLAYER_CHASE_INACTIVE_LOGIC_ID = 0x0001


def is_player_chase_target_candidate(slot: ObjectSlotRecord) -> bool:
    """Pure candidate gate recovered from the B15A scan used by B1B0.

    This does not mean "enemy" globally.  It is exactly the object-record family
    that the B1B0 behavior may acquire as its chase/focus target.
    """
    return (
        slot.active_word != 0
        and slot.logic_id not in PLAYER_CHASE_EXCLUDED_LOGIC_IDS
        and (slot.x_word & 0xFFFF) <= PLAYER_CHASE_CANDIDATE_MAX_X
        and slot.hazard_class == PLAYER_CHASE_REQUIRED_HAZARD_CLASS
    )


def is_player_chase_acquired_target_valid(slot: ObjectSlotRecord) -> bool:
    """Pure validity gate for B1B0's already-acquired chase target.

    B1B0 stores the acquired target slot pointer at current-object ``+30h``.
    On later frames it keeps chasing that slot only while the target remains
    active, stays inside the recovered right-side boundary, and has not become
    logic id ``0001h``.  This is still a narrow B1B0 predicate, not a global
    object-life classification.
    """
    return slot.active_word != 0 and (slot.x_word & 0xFFFF) <= PLAYER_CHASE_ACQUIRED_MAX_X and slot.logic_id != PLAYER_CHASE_INACTIVE_LOGIC_ID


# 1010:AD60 bounds/tile tail.  These are the recovered play-field box and the
# tile-probing object family, source-level values rather than archetype names.
OBJECT_BOUNDS_MIN_X = 0x0008
OBJECT_BOUNDS_MAX_X = 0x00E0
OBJECT_BOUNDS_MAX_Y = 0x00C8
OBJECT_BOUNDS_TILE_PROBE_DRAW_LAYER = 0x0002
OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS = (0x0002, 0x0004, 0x000C, 0x0005, 0x0006, 0x0009, 0x0008)


def object_bounds_tile_decision_ad60(
    x: int,
    y: int,
    draw_layer: int,
    logic_id: int,
    tile_probe_suppressed: bool,
) -> ObjectBoundsTileDecision:
    """Pure AD60 branch classification recovered from 1010:AD60.

    AD60 deactivates an object that left the play-field box, otherwise returns
    unless the object is a tile-probing family (draw layer ``0002h``, a probing
    ``logic_id``, and the BDAC probe-suppress flag clear).  The hook/adapter
    still replays the original CMP order so live 8086 flags match the oracle at
    each branch; this function owns the stable branch decision.
    """
    px = x & 0xFFFF
    if px < OBJECT_BOUNDS_MIN_X or px > OBJECT_BOUNDS_MAX_X or (y & 0xFFFF) > OBJECT_BOUNDS_MAX_Y:
        return ObjectBoundsTileDecision("deactivate")
    if (draw_layer & 0xFFFF) != OBJECT_BOUNDS_TILE_PROBE_DRAW_LAYER:
        return ObjectBoundsTileDecision("skip")
    if (logic_id & 0xFFFF) not in OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS:
        return ObjectBoundsTileDecision("skip")
    if tile_probe_suppressed:
        return ObjectBoundsTileDecision("skip")
    return ObjectBoundsTileDecision("tile_probe")


# 1010:C054 deactivate dispatcher families.  These names are still
# dispatcher/source-level, not final gameplay archetype names.
OBJECT_DEACTIVATE_BOSS_GROUP_LOGIC_IDS = (0x0076, 0x0077, 0x0078, 0x0079)
OBJECT_DEACTIVATE_COUNTER_DROP_LOGIC_IDS = (
    0x0061, 0x0062, 0x0065,
    0x0014, 0x0016, 0x0017, 0x0018,
    0x007F, 0x0080, 0x0081,
    0x0093,
    0x001D, 0x001E, 0x0020, 0x0021, 0x0022,
)
OBJECT_DEACTIVATE_DEBUG_BYTE_LOGIC_ID = 0x0093
OBJECT_DEACTIVATE_SCRIPT_AX_BY_LOGIC_ID = {
    0x007E: 0xA79C,
    0x007D: 0xA6F0,
    0x001F: 0xA83E,
    0x001C: 0xA82A,
    0x0015: 0xA5C0,
    0x0013: 0xA4E4,
}



# C054 -> C15B/C194 multi-part boss group transition facts.
# These are source-level state values, not stack/debug glue.
BOSS_GROUP_DEACTIVATED_LOGIC_ID = 0x0001
BOSS_GROUP_TRANSITION_LATCH_CLEAR = 0x0000
BOSS_GROUP_SPRITE_OR_STATE_DEATH = 0x0003


def boss_group_transition_targets(current_slot_base: int, group_pointer_words: tuple[int, ...]) -> tuple[int, ...]:
    """Return sibling boss-part slots transitioned by C15B.

    The original C15B walks four DS:A8BA..A8C0 pointers and skips the pointer
    equal to the current object BP.  Keep this pure so the adapter owns only the
    DOS reads, CALL scratch return words, and C194 side effects.
    """
    current = current_slot_base & 0xFFFF
    return tuple(ptr & 0xFFFF for ptr in group_pointer_words if (ptr & 0xFFFF) != current)


def boss_group_slot_transition_c194(previous_logic_id: int) -> BossGroupSlotTransition:
    """Pure C194 state assignment for one sibling boss part."""
    return BossGroupSlotTransition(
        previous_logic_id=previous_logic_id & 0xFFFF,
        logic_id=BOSS_GROUP_DEACTIVATED_LOGIC_ID,
        transition_latch=BOSS_GROUP_TRANSITION_LATCH_CLEAR,
        sprite_or_state=BOSS_GROUP_SPRITE_OR_STATE_DEATH,
    )

def object_deactivate_dispatch_decision_c054(logic_id: int) -> ObjectDeactivateDispatchDecision:
    """Pure source-like classification recovered from 1010:C054.

    The hook/adapter layer still replays the original CMP order so flags stay
    oracle-compatible.  This pure function owns the stable gameplay dispatcher
    classification: multi-part boss group transition, global counter drop, AX
    script selection, or no observed C054 action.
    """
    selector = logic_id & 0xFFFF
    if selector in OBJECT_DEACTIVATE_BOSS_GROUP_LOGIC_IDS:
        return ObjectDeactivateDispatchDecision("boss_group_transition")
    if selector in OBJECT_DEACTIVATE_COUNTER_DROP_LOGIC_IDS:
        return ObjectDeactivateDispatchDecision("counter_drop")
    ax_script = OBJECT_DEACTIVATE_SCRIPT_AX_BY_LOGIC_ID.get(selector)
    if ax_script is not None:
        return ObjectDeactivateDispatchDecision("script_select", ax_script=ax_script)
    return ObjectDeactivateDispatchDecision("none")


def object_pool_find_free(pool: ObjectPool, cursor: int) -> FreeSlotAllocation:
    """Pure 1010:7573 object-slot allocator over a native ObjectPool.

    Scans up to ``len(pool)`` slots starting at the allocator cursor DS:95DA (``cursor``),
    wrapping at the table end back to the table base, and returns the first slot whose
    active word is zero -- the cursor advances to and parks at that slot.  Returns
    ``offset=None`` (cursor unchanged) when every slot is occupied.  The wrap check is
    repeated every iteration, exactly as the ASM loop target 757A does, so a cursor that
    starts at the table-end sentinel still wraps before the first read.
    """
    base = pool.base & 0xFFFF
    stride = pool.stride & 0xFFFF
    count = len(pool)
    table_end = (base + count * stride) & 0xFFFF
    bx = cursor & 0xFFFF
    for _ in range(count):
        if bx == table_end:
            bx = base
        index = ((bx - base) & 0xFFFF) // stride
        if pool.active_word(index) == 0:
            return FreeSlotAllocation(offset=bx, cursor=bx)
        bx = (bx + stride) & 0xFFFF
    return FreeSlotAllocation(offset=None, cursor=cursor & 0xFFFF)
