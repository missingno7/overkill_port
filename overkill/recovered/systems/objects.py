"""Pure recovered object-system predicates.

No CPU, memory, DOS segment, hook state, or original continuation is allowed in
this module.  These predicates name gameplay decisions once multiple hooks or
traces have constrained their object-slot fields.
"""
from __future__ import annotations

from collections.abc import Callable

from overkill.recovered.domain.coords import i16, u16
from overkill.recovered.domain.object_behaviors import (
    Ab10Update,
    Aba3Update,
    Ae09MovementStep,
    Ae09SlotUpdate,
    Ae09Update,
    Ae2cSlotUpdate,
    Ae7dSlotUpdate,
    Aed8SlotUpdate,
    B24dSlotUpdate,
    B2cdSlotUpdate,
    B73ETargetReachedResolution,
    B86dDriftUpdate,
    B86dMovementResult,
    B9f0MovementResult,
    BossGroupSlotTransition,
    ObjectBoundsTileDecision,
    ObjectDeactivateDispatchDecision,
    ObjectLogicDispatchAA2B,
)
from overkill.recovered.domain.object_slots import (
    A515LinkSpawn,
    FormationSpawnSeed7476,
    FreeSlotAllocation,
    LinkedEffectSpawnSeed7420,
    ObjectPool,
    ObjectSlotRecord,
    ObjectSpawnSeed,
    ObjectSpawnSeedA4EA,
    PlayerFanoutResult,
    PlayerShotSpawn,
)
from overkill.recovered.domain.tilemap import LevelTileContext, TileProbeInput
from overkill.recovered.domain.movement import MovementTarget
from overkill.recovered.systems.collision import overlap_contact_box_contains
from overkill.recovered.systems.movement import (
    object_delta_5e1b,
    object_delta_steer_5e42,
    object_target_seek_step_5db2,
    step_operations_for_direction,
)
from overkill.recovered.systems.tilemap import (
    TILE_PROBE_COLUMN_STRIDE,
    compute_tile_probe_5073,
    lookup_tile_class_byte,
)

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


# 1010:7420 linked-effect spawn template.  BFC7 runs this when a linked-counter
# group's last member dies; it stamps a freshly allocated effect slot with a
# short-lived visual at the source's staged position (DS:2376 Y / 2378 X / 237A
# type) plus the scroll offset DS:A278.
OBJECT_SPAWN_SEED_7420_HAZARD_CLASS = 0x0005
OBJECT_SPAWN_SEED_7420_SPRITE_BIAS = 0x0046
OBJECT_SPAWN_SEED_7420_Y_FLOOR = 0x00C0
OBJECT_SPAWN_SEED_7420_LINKED_COUNTER_INDEX_NONE = 0xFFFF


def object_spawn_seed_7420(source_x: int, source_y: int, source_type: int,
                           x_offset: int) -> LinkedEffectSpawnSeed7420:
    """Pure 1010:7420 linked-effect spawn template recovered from the 7420 stamp.

    A freshly allocated effect slot is initialised as an active, scan-enabled
    ``hazard_class=5`` / ``logic_id=0`` object at ``X = source_x + x_offset`` (the
    staged DS:2378 plus the scroll offset DS:A278) and ``Y = min(source_y, 00C0h)``
    (the staged DS:2376 clamped to the floor), with ``sprite_or_state = source_type
    + 46h`` and the raw ``source_type`` (DS:237A) also stamped into the record's
    ``+26h`` word; ``transition_latch`` / ``variant`` / ``gate_or_layer`` cleared and
    the linked-counter index set to ``FFFFh`` (the spawned effect is itself
    unlinked).  The adapter owns the leading 7524 allocation and the DOS write
    order; this owns the field values.
    """
    return LinkedEffectSpawnSeed7420(
        active_word=0x0001,
        x_word=(source_x + x_offset) & 0xFFFF,
        y_word=(OBJECT_SPAWN_SEED_7420_Y_FLOOR
                if (source_y & 0xFFFF) > OBJECT_SPAWN_SEED_7420_Y_FLOOR
                else (source_y & 0xFFFF)),
        transition_latch=0x0000,
        scan_flag=0x0001,
        hazard_class=OBJECT_SPAWN_SEED_7420_HAZARD_CLASS,
        logic_id=0x0000,
        linked_counter_index=OBJECT_SPAWN_SEED_7420_LINKED_COUNTER_INDEX_NONE,
        variant=0x0000,
        slot_field_26=source_type & 0xFFFF,
        sprite_or_state=(source_type + OBJECT_SPAWN_SEED_7420_SPRITE_BIAS) & 0xFFFF,
        gate_or_layer=0x0000,
    )


# 1010:7476 formation child spawn template.  B800 stamps a freshly allocated slot with a
# logic_id=0Bh child offset from the parent slot; the final-boss mode (DS:A8C2 == 1) uses
# the wider Y / narrower X offsets.  The view globals DS:2380/237E set the movement deltas.
FORMATION_SPAWN_SEED_7476_Y_OFFSET = 0x000C
FORMATION_SPAWN_SEED_7476_X_OFFSET = 0x000C
FORMATION_SPAWN_SEED_7476_BOSS_Y_OFFSET = 0x001C
FORMATION_SPAWN_SEED_7476_BOSS_X_OFFSET = 0x0008
FORMATION_SPAWN_SEED_7476_VIEW_Y_BIAS = 0x0009


def formation_spawn_seed_7476(slot_x: int, slot_y: int, boss_mode: bool,
                              view_y_2380: int, view_x_237e: int) -> FormationSpawnSeed7476:
    """Pure 1010:7476 formation child spawn template recovered from the B800 -> 7476 stamp.

    The child is placed relative to the parent: ``y = slot_y + 1Ch``/``0Ch`` and
    ``x = slot_x + 08h``/``0Ch`` (the boss-mode pair when ``boss_mode``), stamped as an
    active ``logic_id=0Bh`` / ``hazard_class=2`` / ``sprite_or_state=31h`` child with
    ``scan_enable_or_solid=0`` / ``direction_or_step=0`` / ``gate_or_layer=1`` /
    ``scan_flag=0`` / ``substate=FFFFh``, and given view-relative deltas
    ``move_delta_y = y - (view_y_2380 + 9)`` and ``move_delta_x = x - view_x_237e``.  The
    adapter owns the 7573 allocation, the DS:98C0 -> DS:BEFF side effect, and the write
    order; this owns the field values.
    """
    y_off = FORMATION_SPAWN_SEED_7476_BOSS_Y_OFFSET if boss_mode else FORMATION_SPAWN_SEED_7476_Y_OFFSET
    x_off = FORMATION_SPAWN_SEED_7476_BOSS_X_OFFSET if boss_mode else FORMATION_SPAWN_SEED_7476_X_OFFSET
    y = (slot_y + y_off) & 0xFFFF
    x = (slot_x + x_off) & 0xFFFF
    return FormationSpawnSeed7476(
        y_word=y,
        x_word=x,
        active_word=0x0001,
        scan_enable_or_solid=0x0000,
        direction_or_step=0x0000,
        sprite_or_state=0x0031,
        gate_or_layer=0x0001,
        scan_flag=0x0000,
        hazard_class=0x0002,
        logic_id=0x000B,
        substate=0xFFFF,
        move_delta_y=(y - ((view_y_2380 + FORMATION_SPAWN_SEED_7476_VIEW_Y_BIAS) & 0xFFFF)) & 0xFFFF,
        move_delta_x=(x - view_x_237e) & 0xFFFF,
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


def object_update_b86d_drift(x_word: int, vertical_delta: int, phase_word_2328: int) -> B86dDriftUpdate:
    """Pure 1010:B86D fall-through (formation-drift) slot transform.

    The common B86D path (after the B8F8 edge-steer guard and the A7A0 phase block are both
    skipped): move X by the negated global vertical delta (DS:2342), add one more pixel when the
    DS:2328 phase word is ``0007h``, and select the outgoing sprite from the delta's sign
    (:func:`b86d_outgoing_sprite_for_delta`).  Only X and the sprite change; the formation-spawn
    (CALL 7476) is a separate global side effect and the shared BC4B post-move tail is the next
    stage -- both out of scope for this slot transform.

    Evidence root: 1010:B86D B8BB..B8E9 -- ``ADD [bp+02], -delta`` / ``CMP [2328], 7`` /
    ``INC [bp+02]`` then the b86d_outgoing_sprite NEG+CMP.
    """
    new_x = (x_word - vertical_delta) & 0xFFFF
    if (phase_word_2328 & 0xFFFF) == 0x0007:
        new_x = (new_x + 1) & 0xFFFF
    return B86dDriftUpdate(x_word=new_x, sprite_or_state=b86d_outgoing_sprite_for_delta(vertical_delta))


B86D_EDGE_GUARD = 0x0002              # DS:A47E <= 2 -> B8F8 edge-steer
B86D_X_EDGE = 0x00C0                  # x > C0h -> B8F8 edge-steer
B86D_EDGE_STEER_SPRITE = 0x0076       # the B8F8 edge-steer forces this sprite
B86D_A7A0_THRESHOLD = 0x0028          # DS:A7A0 < 28h -> the A7A0 phase block
B86D_A7A0_SPRITE = 0x0075             # the A7A0 block forces this sprite
B86D_A7A0_BLOCKED_DIRECTION = 0x0004  # direction when the A7A0 5DB2 seek is blocked
B86D_A7A0_SEEK_MODE = 0x0001          # DS:2308 mode the A7A0 block sets before 5DB2 (mode 1)
B86D_LOW_BIT_CLEAR = 0xFFFE           # the A7A0 block clears the low bit of x/y/target before the seek


def object_update_b86d(
    x_word: int,
    y_word: int,
    substate: int,
    direction: int,
    active_word: int,
    target_x: int,
    target_y: int,
    move_step_error: int,
    a47e: int,
    a7a0: int,
    ref_box_x: int,
    ref_box_y: int,
    ref_box_scan: int,
    vertical_delta: int,
    phase_2328: int,
    step_mode: int,
    direction_table,
) -> B86dMovementResult:
    """Pure WHOLE 1010:B86D movement half (logic_id 0x1D) -- the slot at the BC4B handoff.

    Three branches: the B8F8 edge-steer (``a47e`` <= 2 or x > C0h) computes deltas toward the DS:237C
    view box (:func:`object_delta_5e1b`) and steers (:func:`object_delta_steer_5e42`), forcing sprite
    0x76; the A7A0 phase block (``a7a0`` < 28h) clears the low bit of x/y/target and seeks via
    :func:`object_target_seek_step_5db2` (mode 1), forcing sprite 0x75 and direction 4 when blocked;
    else the fall-through formation drift (:func:`object_update_b86d_drift`).  ``substate``/``active`` are
    unchanged here -- BC4B (:func:`object_postmove_bc4b`) owns the post-move y clamp / X-bounds death.
    This is the canonical handler the gate verifies at the BC4B handoff and the native driver composes
    with BC4B; the optional 7476 formation spawn is a global side effect, out of this slot transform."""
    if (a47e & 0xFFFF) <= B86D_EDGE_GUARD or (x_word & 0xFFFF) > B86D_X_EDGE:
        deltas = object_delta_5e1b(x_word, y_word, ref_box_x, ref_box_y, ref_box_scan)
        steer = object_delta_steer_5e42(
            x_word, y_word, direction, deltas.move_delta_y, deltas.move_delta_x,
            move_step_error, step_mode, direction_table,
        )
        return B86dMovementResult(substate, steer.direction_or_step, B86D_EDGE_STEER_SPRITE,
                                  steer.x_word, steer.y_word, active_word)
    if (a7a0 & 0xFFFF) < B86D_A7A0_THRESHOLD:
        target = MovementTarget(y_word=target_y & B86D_LOW_BIT_CLEAR, x_word=target_x & B86D_LOW_BIT_CLEAR)
        seek = object_target_seek_step_5db2(
            x_word & B86D_LOW_BIT_CLEAR, y_word & B86D_LOW_BIT_CLEAR, direction, target,
            B86D_A7A0_SEEK_MODE, direction_table,
        )
        new_dir = B86D_A7A0_BLOCKED_DIRECTION if seek.blocked else seek.direction_or_step
        return B86dMovementResult(substate, new_dir, B86D_A7A0_SPRITE, seek.x_word, seek.y_word, active_word)
    drift = object_update_b86d_drift(x_word, vertical_delta, phase_2328)
    return B86dMovementResult(substate, direction, drift.sprite_or_state, drift.x_word, y_word, active_word)


B9F0_A482_MOVEMENT_SENTINEL = 0xA4E4  # DS:A482 == A4E4h -> the movement paths, else sprite-refresh
B9F0_SEEK_MODE = 0x0001               # DS:2308 mode the Path-D 5DB2 seek uses (mode 1)
B9F0_BA5A_X_NUDGE = 0x0002            # the BA5A helper's post-steer X += 2


def object_update_b9f0(
    x_word: int,
    y_word: int,
    substate: int,
    direction: int,
    active_word: int,
    sprite: int,
    target_x: int,
    target_y: int,
    move_step_error: int,
    move_delta_x: int,
    move_delta_y: int,
    a482: int,
    frame: int,
    vertical_delta: int,
    horizontal_delta: int,
    a47e: int,
    difficulty: int,
    tick: int,
    ref_box_x: int,
    ref_box_y: int,
    ref_box_scan: int,
    step_mode: int,
    direction_table,
) -> B9f0MovementResult:
    """Pure WHOLE 1010:B9F0 movement half (logic_id 0x14) -- the slot at the BC4B handoff.

    Four paths.  Path A (``a482`` != A4E4h): refresh the sprite from the global ``frame``.  Else apply
    the global target deltas to +32/+34 and wrap target X, then: reached-target -> the BA5A motion helper
    (5E1B->5E42, X += 2, sprite refresh) when its low-counter / periodic-tick gate fires, else a plain
    sprite refresh; not reached + x > target -> the overshoot 5E42 step + right-edge X wrap; not reached
    + x <= target -> the 5DB2 seek toward the even-aligned target.  ``substate``/``active`` are unchanged
    here -- BC4B owns the post-move y/active.  The optional 7476 formation spawns are global side effects,
    out of this slot transform.  The canonical handler the gate verifies at the BC4B handoff and the
    native driver composes with object_postmove_bc4b."""
    refreshed = b9f0_sprite_from_frame(frame)
    if (a482 & 0xFFFF) != B9F0_A482_MOVEMENT_SENTINEL:
        return B9f0MovementResult(substate, direction, refreshed, x_word, y_word, active_word)  # Path A

    new_target_y = (target_y + vertical_delta) & 0xFFFF
    new_target_x = b9f0_wrapped_target_x((target_x + horizontal_delta) & 0xFFFF)
    reached = ((y_word + vertical_delta) & 0xFFFF) == new_target_y and (x_word & 0xFFFF) == new_target_x
    if reached:
        helper_fires = b9f0_low_counter_runs_helper(a47e)
        if not helper_fires:
            mask = b9f0_periodic_helper_mask(difficulty)
            helper_fires = (tick & mask) == mask
        if not helper_fires:
            return B9f0MovementResult(substate, direction, refreshed, x_word, y_word, active_word)  # Path B
        deltas = object_delta_5e1b(x_word, y_word, ref_box_x, ref_box_y, ref_box_scan)
        s = object_delta_steer_5e42(
            x_word, y_word, direction, deltas.move_delta_y, deltas.move_delta_x,
            move_step_error, step_mode, direction_table,
        )
        return B9f0MovementResult(substate, s.direction_or_step, refreshed,
                                  (s.x_word + B9F0_BA5A_X_NUDGE) & 0xFFFF, s.y_word, active_word)  # BA5A

    if (x_word & 0xFFFF) > new_target_x:
        s = object_delta_steer_5e42(
            x_word, y_word, direction, move_delta_y, move_delta_x, move_step_error, step_mode, direction_table,
        )
        return B9f0MovementResult(substate, s.direction_or_step, sprite,
                                  b9f0_wrapped_x_on_overflow(s.x_word), s.y_word, active_word)  # Path C

    target = MovementTarget(y_word=new_target_y & 0xFFFE, x_word=new_target_x & 0xFFFE)
    seek = object_target_seek_step_5db2(x_word & 0xFFFE, y_word & 0xFFFE, direction, target, B9F0_SEEK_MODE, direction_table)
    return B9f0MovementResult(substate, seek.direction_or_step, sprite, seek.x_word, seek.y_word, active_word)  # Path D


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


def object_tile_probe_deactivates_ad60(obj_x: int, obj_y: int, tiles: LevelTileContext) -> bool:
    """AD60's tile-probe deactivation trigger (the 1010:AD60 tile path: 5073 +13 -> 505B -> class==1).

    Returns True iff the tile one map row below the moved object -- the recovered 5073 tile offset plus
    the 13-column row stride -- has class 1, the condition under which AD60 routes the object to the
    BD17 deactivate tail.  Composes the recovered 5073 probe (:func:`compute_tile_probe_5073`) and 505B
    class lookup (:func:`lookup_tile_class_byte`) over the level tile data (:class:`LevelTileContext`)."""
    probe = compute_tile_probe_5073(
        TileProbeInput(
            origin_x_word=tiles.origin_x_word,
            row_base_word=tiles.row_base_word,
            object_x_word=obj_x,
            object_y_word=obj_y,
        )
    )
    offset = (probe.tile_offset_word + TILE_PROBE_COLUMN_STRIDE) & 0xFFFF
    raw = tiles.tile_plane[offset] & 0x00FF
    return lookup_tile_class_byte(raw, tiles.class_table) == 1


def object_update_ae09(
    substate: int,
    direction_or_step: int,
    x_word: int,
    y_word: int,
    active_word: int,
    draw_layer: int,
    logic_id: int,
    tile_probe_suppressed: bool,
    tiles: LevelTileContext,
) -> Ae09SlotUpdate:
    """Pure WHOLE per-slot AE09 update (logic_id 0Ch): the movement step + the AD60 bounds/tile -> active.

    Composes :func:`object_movement_step_ae09` (timer/step + AF22 move) with
    :func:`object_bounds_tile_decision_ad60` on the *post-move* position: AD60 ``deactivate`` (out of
    play bounds) clears ``active``; ``skip`` leaves it; ``tile_probe`` samples the tile one row below
    (:func:`object_tile_probe_deactivates_ad60`) and clears ``active`` when that tile has class 1.  The
    BD17 global counter/spawn writes are separate state (not slot fields), out of this transform.  This
    is the complete native slot transform for an AE09 object -- the template for the per-logic-id native
    dispatch (movement primitive + bounds/tile -> the next slot)."""
    move = object_movement_step_ae09(substate, direction_or_step, x_word, y_word)
    decision = object_bounds_tile_decision_ad60(
        move.x_word, move.y_word, draw_layer, logic_id, tile_probe_suppressed=tile_probe_suppressed
    )
    if decision.kind == "deactivate":
        new_active = 0x0000
    elif decision.kind == "skip":
        new_active = active_word & 0xFFFF
    else:  # "tile_probe": deactivate iff the tile one map row below has class 1.
        new_active = 0x0000 if object_tile_probe_deactivates_ad60(move.x_word, move.y_word, tiles) else (active_word & 0xFFFF)
    return Ae09SlotUpdate(
        substate=move.substate,
        direction_or_step=move.direction_or_step,
        sprite_or_state=move.sprite_or_state,
        x_word=move.x_word,
        y_word=move.y_word,
        active_word=new_active,
    )


AED8_AEE4_STEP_PIXELS = 8            # AEE4 steps the slot 8px in its direction
AED8_VERIFIED_DIRECTION_MAX = 7      # AEE4's AEEE table covers directions 0..7
AED8_SUBSTATE_SKIP_OVERLAP = 0x0001  # slot +1E == 1 skips the B250 overlap test (always no-contact)
AED8_CONTACT_DEATH_X = 0xFFFF        # the ADC9 contact tail sets X to FFFFh before AD60


def object_update_aed8(
    substate: int,
    direction_or_step: int,
    x_word: int,
    y_word: int,
    active_word: int,
    substate_1e: int,
    draw_layer: int,
    logic_id: int,
    ref_box_x: int,
    ref_box_y: int,
    a278: int,
    tile_probe_suppressed: bool,
    tiles: LevelTileContext,
) -> Aed8SlotUpdate | None:
    """Pure WHOLE per-slot AED8 update (EFAE logic_id 2): AEE4 step + B250 contact + AD60 -> active.

    Returns ``None`` for the two sub-paths the gate leaves as fallback: the timer-expired death
    (substate decrements to 0) and an AEE4 direction outside the AEEE table's 0..7 range.

    Otherwise: decrement the substate timer, step 8px in the direction (AEE4), pick the B250 tail --
    contact iff ``+1E != 1`` AND the stepped position is inside the DS:237E/2380 view box
    (:func:`overlap_contact_box_contains`) -- then join AD60: no contact -> AD5A adds DS:A278 to X;
    contact -> ADC9 sets X = FFFFh; AD60 (:func:`object_bounds_tile_decision_ad60`) then clears
    ``active`` out of play bounds or (tile-probe family) when the tile one row below has class 1.  AEE4
    and AD60 leave the sprite and direction untouched, so only the four changed fields are returned.
    The B250 fan-out 9E19 status side effects are separate global state, out of this transform."""
    new_substate = (substate - 1) & 0xFFFF
    if new_substate == 0:
        return None  # timer-expired -> the unverified ADC9 death path
    direction = direction_or_step & 0xFFFF
    if direction > AED8_VERIFIED_DIRECTION_MAX:
        return None  # AEE4 direction outside the verified 0..7 table

    x = x_word & 0xFFFF
    y = y_word & 0xFFFF
    for op in step_operations_for_direction(direction, AED8_AEE4_STEP_PIXELS):
        delta = i16(op.delta_word)
        if op.axis == "x":
            x = u16(x + delta)
        else:
            y = u16(y + delta)

    contact = (substate_1e & 0xFFFF) != AED8_SUBSTATE_SKIP_OVERLAP and overlap_contact_box_contains(
        x, y, ref_box_x, ref_box_y
    )
    final_x = AED8_CONTACT_DEATH_X if contact else u16(x + a278)

    decision = object_bounds_tile_decision_ad60(
        final_x, y, draw_layer, logic_id, tile_probe_suppressed=tile_probe_suppressed
    )
    if decision.kind == "deactivate":
        new_active = 0x0000
    elif decision.kind == "skip":
        new_active = active_word & 0xFFFF
    else:  # tile_probe: deactivate iff the tile one map row below has class 1.
        new_active = 0x0000 if object_tile_probe_deactivates_ad60(final_x, y, tiles) else (active_word & 0xFFFF)
    return Aed8SlotUpdate(substate=new_substate, x_word=final_x, y_word=y, active_word=new_active)


B2CD_WAYPOINT_TARGET_X_BIAS = 0x0020   # B2D1: target X = waypoint[0] + 0x20
B2CD_SCROLL_SPECIAL = 0x0E52           # B335: DS:2350 == 0xE52 picks the +0x105 sprite branch
B2CD_WAYPOINT_STRIDE = 0x0004          # B2FF: each reached waypoint advances the +36 pointer by 4 ({X,Y})
B2CD_WAYPOINT_LOOP_CAP = 0x0040        # safety bound on the advance loop (the VM relies on an unreached one)


def b2cd_sprite_offset(direction: int, bdac: int, level: int, scroll: int) -> int | None:
    """B2CD sprite = ``direction`` + a level/BDAC/scroll-dependent constant (recovered B304..B3B0).

    BDAC==1 -> +0x3B; else by level (DS:2356): {1: +0x2A, 2: +0xD2, 3/4/7: +0xEC, 0/5/6: +0x115, but
    scroll==0xE52 picks +0x105 for levels 0/6}.  Returns None for the messy fall-throughs the handler
    leaves unmodelled (level 5 with scroll==0xE52, and any other/unknown level)."""
    d = direction & 0xFFFF
    if (bdac & 0xFFFF) == 0x0001:
        return (d + 0x3B) & 0xFFFF
    lvl = level & 0xFFFF
    if lvl in (0x0000, 0x0005, 0x0006):
        if (scroll & 0xFFFF) == B2CD_SCROLL_SPECIAL:
            if lvl in (0x0000, 0x0006):
                return (d + 0x105) & 0xFFFF
            return None  # level 5 + scroll 0xE52 -> the unmapped fall-through
        return (d + 0x115) & 0xFFFF
    if lvl == 0x0001:
        return (d + 0x2A) & 0xFFFF
    if lvl == 0x0002:
        return (d + 0xD2) & 0xFFFF
    if lvl in (0x0003, 0x0004, 0x0007):
        return (d + 0xEC) & 0xFFFF
    return None


def object_update_b2cd(
    slot_x: int,
    slot_y: int,
    slot_direction: int,
    waypoint_ptr: int,
    read_waypoint_word: Callable[[int], int],
    direction_table,
    bdac: int,
    level: int,
    scroll: int,
) -> B2cdSlotUpdate | None:
    """Pure WHOLE per-slot B2CD update (EFAE logic_id 0x12): waypoint 5DB2 seek + sprite, at BC4B.

    Walks the waypoint list from the +36 pointer: reads the current waypoint ({X, Y} via
    ``read_waypoint_word`` at ``waypoint_ptr``/``+2``), seeks toward {X+0x20, Y} with 5DB2 (mode 2 when
    level 0 or BDAC==1, else 1); while 5DB2 is blocked (the slot has REACHED that waypoint) it advances
    the pointer by 4 and re-seeks toward the next one (the B2FF/jmp-B2CD loop).  When a seek finally moves,
    the sprite is ``b2cd_sprite_offset`` of the new direction and the slot joins BC4B.  Returns None on the
    unmodelled sprite fall-throughs (scroll==0xE52/unknown level) and on the safety cap.  Only
    direction/sprite/x/y change; ``waypoint_ptr`` carries the advanced +36 pointer to write back."""
    mode = 0x0002 if ((level & 0xFFFF) == 0 or (bdac & 0xFFFF) == 0x0001) else 0x0001
    wp = waypoint_ptr & 0xFFFF
    for _ in range(B2CD_WAYPOINT_LOOP_CAP):
        waypoint_x = read_waypoint_word(wp)
        waypoint_y = read_waypoint_word((wp + 2) & 0xFFFF)
        target = MovementTarget(
            y_word=waypoint_y & 0xFFFF,
            x_word=(waypoint_x + B2CD_WAYPOINT_TARGET_X_BIAS) & 0xFFFF,
        )
        seek = object_target_seek_step_5db2(slot_x, slot_y, slot_direction, target, mode, direction_table)
        if not seek.blocked:
            break
        wp = (wp + B2CD_WAYPOINT_STRIDE) & 0xFFFF  # B2FF: reached -> next waypoint, re-seek
    else:
        return None  # safety cap: no unreached waypoint within the bound
    sprite = b2cd_sprite_offset(seek.direction_or_step, bdac, level, scroll)
    if sprite is None:
        return None
    return B2cdSlotUpdate(
        direction_or_step=seek.direction_or_step,
        sprite_or_state=sprite,
        x_word=seek.x_word,
        y_word=seek.y_word,
        waypoint_ptr=wp,
    )


AE2C_DEATH_Y = 0x00C8               # AE2C: dies at y == 0xC8
AE2C_PROBE_TILE_DELTA = 0x000E      # AE4F: tile probe samples 5073-offset + 0xE


def object_update_ae2c(
    x_word: int,
    y_word: int,
    active_word: int,
    draw_layer: int,
    a278: int,
    anim_2326: int,
    tile_probe_suppressed: bool,
    tiles: LevelTileContext,
) -> Ae2cSlotUpdate | None:
    """Pure WHOLE per-slot AE2C update (EFAE logic_id 0x06): scroll-left mover with a tile-gated down-step.

    Sibling of AE7D.  Returns None at y==0xC8 (the ADC9 death).  Else X -= 4; unless Y mod 16 == 8, the
    render mode (BDAC) is clear, and the tile at the 5073 probe + 0xE has class 1 (-> direction 0, no Y
    move), it steers down (direction 1, Y += 4).  The sprite is ``((anim_2326 << 2) & 8) + direction + 8``
    (anim_2326 = DS:2326); then AD5A adds DS:A278 to X and the AD60 tail (0x06 tile-probe family) sets
    ``active``.  substate untouched."""
    y = y_word & 0xFFFF
    if y == AE2C_DEATH_Y:
        return None  # AE31 -> ADC9 death
    x = (x_word - AE7D_X_STEP) & 0xFFFF
    direction = 1
    if (y & 0x0007) == 0 and (y & 0x0008) != 0 and not tile_probe_suppressed:
        probe = compute_tile_probe_5073(TileProbeInput(
            origin_x_word=tiles.origin_x_word, row_base_word=tiles.row_base_word,
            object_x_word=x, object_y_word=y))
        raw = tiles.tile_plane[(probe.tile_offset_word + AE2C_PROBE_TILE_DELTA) & 0xFFFF]
        if lookup_tile_class_byte(raw, tiles.class_table) == 1:
            direction = 0
    if direction == 1:
        y = (y + 4) & 0xFFFF
    sprite = (((anim_2326 << 2) & 0x0008) + direction + 8) & 0xFFFF

    final_x = (x + a278) & 0xFFFF  # AD5A
    decision = object_bounds_tile_decision_ad60(
        final_x, y, draw_layer, 0x0006, tile_probe_suppressed=tile_probe_suppressed)
    if decision.kind == "deactivate":
        new_active = 0x0000
    elif decision.kind == "skip":
        new_active = active_word & 0xFFFF
    else:
        new_active = 0x0000 if object_tile_probe_deactivates_ad60(final_x, y, tiles) else (active_word & 0xFFFF)
    return Ae2cSlotUpdate(
        direction_or_step=direction, sprite_or_state=sprite,
        x_word=final_x, y_word=y, active_word=new_active,
    )


AE7D_X_STEP = 4                     # AE86: X -= 4 (scroll-left move)
AE7D_PROBE_TILE_DELTA = 0x000C      # AE9B: tile probe samples 5073-offset + 0xC
AE7D_UP_DIRECTION = 7               # AEAA: steer up (direction 7, Y -= 4)
AE7D_SPRITE_BIAS = 8                # AEB6: sprite = direction + 8


def object_update_ae7d(
    x_word: int,
    y_word: int,
    active_word: int,
    draw_layer: int,
    a278: int,
    tile_probe_suppressed: bool,
    tiles: LevelTileContext,
) -> Ae7dSlotUpdate | None:
    """Pure WHOLE per-slot AE7D update (EFAE logic_id 0x05): scroll-left mover with a tile-gated up-step.

    Returns None at y==0 (the ADC9 death).  Else X -= 4; unless the slot is 16px-aligned in Y, the render
    mode (BDAC) is clear, and the tile at the 5073 probe + 0xC has class 1 (-> direction 0, no Y move), it
    steers up (direction 7, Y -= 4).  The sprite is direction + 8; then AD5A adds DS:A278 to X and the
    AD60 bounds/tile tail (0x05 is a tile-probe family) sets ``active``.  substate is untouched."""
    y = y_word & 0xFFFF
    if y == 0:
        return None  # AE83 -> ADC9 out-of-bounds death
    x = (x_word - AE7D_X_STEP) & 0xFFFF
    direction = AE7D_UP_DIRECTION
    if (y & 0x000F) == 0 and not tile_probe_suppressed:
        probe = compute_tile_probe_5073(TileProbeInput(
            origin_x_word=tiles.origin_x_word, row_base_word=tiles.row_base_word,
            object_x_word=x, object_y_word=y))
        raw = tiles.tile_plane[(probe.tile_offset_word + AE7D_PROBE_TILE_DELTA) & 0xFFFF]
        if lookup_tile_class_byte(raw, tiles.class_table) == 1:
            direction = 0
    if direction == AE7D_UP_DIRECTION:
        y = (y - 4) & 0xFFFF
    sprite = (direction + AE7D_SPRITE_BIAS) & 0xFFFF

    final_x = (x + a278) & 0xFFFF  # AD5A
    decision = object_bounds_tile_decision_ad60(
        final_x, y, draw_layer, 0x0005, tile_probe_suppressed=tile_probe_suppressed)
    if decision.kind == "deactivate":
        new_active = 0x0000
    elif decision.kind == "skip":
        new_active = active_word & 0xFFFF
    else:
        new_active = 0x0000 if object_tile_probe_deactivates_ad60(final_x, y, tiles) else (active_word & 0xFFFF)
    return Ae7dSlotUpdate(
        direction_or_step=direction, sprite_or_state=sprite,
        x_word=final_x, y_word=y, active_word=new_active,
    )


BE3C_ANIMATE_GATE_ON = 0x0001       # DS:2324 == 1 enables the BE3C animation state machine
BE3C_ANIM_MORPH_COUNT = 0x0009      # BE5A: when the inc'd frame counter hits 9 the object morphs


def object_update_be3c(animate_gate: int, state: int, anim_counter: int, sprite_or_state: int) -> int | None:
    """Pure BE3C (EFAE logic_id 0x01) animation -> the new ``sprite_or_state`` (+08), or None to skip.

    BE3C gates on DS:2324 (``!= 1`` -> straight to the BC45 post-move, slot unchanged), else increments
    the frame counter (+22) and dispatches by the slot state (+14) through the CS:BE54 jump table.  State
    0 -> BC45 (unchanged).  State 1 (BE5A) is a frame-counter sprite animation: while the inc'd counter
    is not 9 the sprite is set to that counter (BEA4) and it joins BC45; at 9 it morphs to a new logic id
    (returned as None -- the rare transition, not modelled here).  States 2/3 (BEB0/7E83) are other
    animation sub-behaviours absent from the verified demos (None).  Only the sprite field changes here;
    substate/direction/x/y/active are untouched (the caller composes them + the BC45 post-move)."""
    if (animate_gate & 0xFFFF) != BE3C_ANIMATE_GATE_ON or (state & 0xFFFF) == 0:
        return sprite_or_state & 0xFFFF          # gate off or state 0 -> BC45, slot unchanged
    if (state & 0xFFFF) == 0x0001:
        counter = (anim_counter + 1) & 0xFFFF    # BE46: inc [bp+22]
        if counter == BE3C_ANIM_MORPH_COUNT:
            return None                          # BE60: the morph transition (logic id change)
        return counter                           # BEA4: sprite = the frame counter
    return None                                  # states 2/3: unmodelled animation sub-behaviours


def object_update_b24d(
    x_word: int,
    y_word: int,
    direction_or_step: int,
    active_word: int,
    substate_1e: int,
    move_delta_x: int,
    move_delta_y: int,
    move_step_error: int,
    step_mode: int,
    direction_table,
    draw_layer: int,
    logic_id: int,
    ref_box_x: int,
    ref_box_y: int,
    a278: int,
    tile_probe_suppressed: bool,
    tiles: LevelTileContext,
) -> B24dSlotUpdate:
    """Pure WHOLE per-slot B24D update (EFAE logic_id 0x0B): 5E42 steer + B250 contact + AD60 -> active.

    B24D calls the 5E42 delta-steer (``object_delta_steer_5e42``), then the same B250 selector + AD5A/
    ADC9 -> AD60 tail as AED8: contact iff ``+1E != 1`` AND the steered point is inside the DS:237E/2380
    box (``overlap_contact_box_contains``); no contact -> AD5A adds DS:A278 to X, contact -> ADC9 sets
    X = FFFFh; then AD60 (``object_bounds_tile_decision_ad60``) clears ``active`` out of play bounds (for
    logic_id 0x0B, not a tile-probe family, so only the bounds branch applies).  Substate + sprite are
    untouched.  The in-box contact's 9E19 fan-out is a separate global side effect, out of scope here.
    """
    steer = object_delta_steer_5e42(
        x_word, y_word, direction_or_step, move_delta_y, move_delta_x, move_step_error,
        step_mode, direction_table,
    )
    contact = (substate_1e & 0xFFFF) != AED8_SUBSTATE_SKIP_OVERLAP and overlap_contact_box_contains(
        steer.x_word, steer.y_word, ref_box_x, ref_box_y
    )
    final_x = AED8_CONTACT_DEATH_X if contact else u16(steer.x_word + a278)

    decision = object_bounds_tile_decision_ad60(
        final_x, steer.y_word, draw_layer, logic_id, tile_probe_suppressed=tile_probe_suppressed
    )
    if decision.kind == "deactivate":
        new_active = 0x0000
    elif decision.kind == "skip":
        new_active = active_word & 0xFFFF
    else:  # tile_probe: deactivate iff the tile one map row below has class 1.
        new_active = 0x0000 if object_tile_probe_deactivates_ad60(final_x, steer.y_word, tiles) else (active_word & 0xFFFF)
    return B24dSlotUpdate(
        direction_or_step=steer.direction_or_step,
        x_word=final_x,
        y_word=steer.y_word,
        active_word=new_active,
        move_step_error=steer.move_step_error,
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


# 1010:B15A rotating target-candidate scan.  DS:A43A is a cursor that rotates through the effect/contact
# table (DS:23B4, 0x23 slots); the scan wraps back to the base when it reaches the adjacent gameplay table
# (DS:2B5C = the effect table's end).  Shared by the B1B0 chase behaviour and the A515 link spawn.  The
# geometry (base, the wrap limit, and the 0x23-step budget = one full rotation) is taken from the pool the
# caller snapshots, so no memory-layout constant is hard-coded here.


def native_b15a_scan(effect_pool: ObjectPool, cursor: int) -> tuple[int | None, int]:
    """Pure WHOLE 1010:B15A rotating target-candidate scan over the effect/contact pool.

    Scans up to one full table rotation (``len(effect_pool)`` slots) from the rotating cursor ``DS:A43A``
    for the first :func:`is_player_chase_target_candidate` slot.  A cursor at/over the table end (the
    adjacent gameplay base) wraps to the effect base WITHOUT consuming a budget step (matching the ASM's
    top-of-loop ``cmp/continue``).  Returns ``(found_offset | None, new_cursor)``: on a hit the cursor parks
    at ``found + stride`` and the offset is the found slot's DS offset; on a miss (budget exhausted) the
    offset is None and the cursor is unchanged unless the scan wrapped (then it is left at the effect base).
    ``effect_pool`` must be the whole DS:23B4 table snapshot (its ``base``/``stride``/length give the
    geometry)."""
    base = effect_pool.base & 0xFFFF
    stride = effect_pool.stride & 0xFFFF
    wrap_limit = (base + len(effect_pool) * stride) & 0xFFFF   # the table end = the adjacent gameplay base
    cx = len(effect_pool)
    bx = cursor & 0xFFFF
    a43a = cursor & 0xFFFF
    while True:
        if bx >= wrap_limit:
            a43a = base
            bx = base
            continue
        index = ((bx - base) & 0xFFFF) // stride
        record = ObjectSlotRecord(
            active_word=effect_pool.active_word(index),
            x_word=effect_pool.x_word(index),
            y_word=effect_pool.y_word(index),
            gate_or_layer=effect_pool.word_at(index, 0x0A),
            link_key=effect_pool.word_at(index, 0x0E),
            scan_flag=effect_pool.word_at(index, 0x14),
            hazard_class=effect_pool.word_at(index, 0x16),
            logic_id=effect_pool.logic_id(index),
        )
        if is_player_chase_target_candidate(record):
            a43a = (bx + stride) & 0xFFFF
            return (bx, a43a)
        bx = (bx + stride) & 0xFFFF
        cx -= 1
        if cx == 0:
            return (None, a43a)


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


# 1010:AA2B first-level object-logic dispatch: the per-frame object handler chosen
# from the slot's draw_layer (0-7) through the CS:AA36 jump table.  Address-rooted
# handler names (draw layers 2 and 4 share the EFAE second-level family dispatcher);
# the adapter owns the CS:AA36 table -> IP mapping.
OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER = (
    "postmove_prelude_bc45",   # 0 -> 1010:BC45 (run_object_postmove_prelude_bc45)
    "tracked_logic_ad04",      # 1 -> 1010:AD04
    "family_dispatch_efae",    # 2 -> 1010:EFAE (second-level family dispatch)
    "action_44af",             # 3 -> 1010:44AF
    "family_dispatch_efae",    # 4 -> 1010:EFAE (shares the EFAE dispatcher)
    "collision_tail_aac2",     # 5 -> 1010:AAC2
    "logic_ab10",              # 6 -> 1010:AB10 (object_logic_ab10)
    "handler_c3f8",            # 7 -> 1010:C3F8
)


def object_logic_dispatch_aa2b(draw_layer: int) -> ObjectLogicDispatchAA2B:
    """Pure source-like first-level object-logic routing recovered from 1010:AA2B.

    AA2B doubles the slot's ``draw_layer`` and indexes the CS:AA36 jump table to pick
    the per-frame object handler.  This owns the recovered draw-layer -> handler
    routing for the eight defined layers (0-7); the adapter replays the original
    ``BX = layer*2`` index, the table read, and the IP jump, and cross-checks this
    decision.  Raises ``ValueError`` for an out-of-range draw layer -- the original
    table has no entry there, so the adapter must fall back to the live read rather
    than this guessing.
    """
    dl = draw_layer & 0xFFFF
    if dl >= len(OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER):
        raise ValueError(f"no AA2B object-logic handler for draw layer {dl:#06x}")
    return ObjectLogicDispatchAA2B(OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER[dl])


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


# A41A single-slot player-shot variants -- the A958-state cs:A42C jump-table targets the A067 weapon-fire
# fanout dispatches per shot (the A4D7/A490/A499 bodies in gameplay/action_spawns.py, made VM-free here).
A41A_SHOT_Y_BIAS = 0x0004                              # A4D7/A490/A499: Y = schedule [si+4] + 4
A41A_SHOT_SINGLE_SLOT_STATES = (0x0000, 0x0001, 0x0002)  # A4D7 / A490 / A499 (3/4 are pairs, 5 -> 44AF)
A490_SHOT_SPRITE = 0x0033                              # A490 (state 1): A4D7 + this sprite override
A499_SHOT_DIR_DEFAULT = 0x0007                         # A499 (state 2): direction when A3EC == FFFFh
A499_SHOT_DIR_HIGH_Y = 0x0001                          # A499: direction when A3EC == FFFFh and src Y > 58h
A499_SHOT_Y_THRESHOLD = 0x0058
A499_SHOT_SPRITE_DIR1 = 0x0019                         # A499 sprite when direction == 1
A499_SHOT_SPRITE_OTHER = 0x001F                        # A499 sprite otherwise


def native_a41a_shot(pool: ObjectPool, cursor: int, state: int,
                     source_x: int, source_y: int, a3ec: int) -> PlayerShotSpawn | None:
    """Pure WHOLE A41A single-slot player-shot spawn (the A958 state 0/1/2 cs:A42C targets).

    Allocates a gameplay slot (:func:`object_pool_find_free` over DS:95DA), stamps the A4EA seed
    (:func:`object_spawn_seed_a4ea`), then the shot position (``X = source_x``, ``Y = source_y + 4`` from
    the weapon-schedule entry ``[si+2]``/``[si+4]``) and the per-state overrides: state 1 (A490) sets
    sprite 33h; state 2 (A499) sets direction from ``a3ec`` (or 7, or 1 when ``a3ec == FFFFh`` and
    ``source_y`` > 58h) and sprite 19h when that direction is 1 else 1Fh.  Returns None for the multi-slot
    states (3/4 -> A438/A464), state 5 (44AF), and a full pool (the 7550 recycle fallback is unmodelled)."""
    if (state & 0xFFFF) not in A41A_SHOT_SINGLE_SLOT_STATES:
        return None
    alloc = object_pool_find_free(pool, cursor)
    if alloc.offset is None:
        return None  # pool full -> the 7550 recycle path (not modelled)
    seed = object_spawn_seed_a4ea()
    direction = seed.direction_or_step
    sprite = seed.sprite_or_state
    st = state & 0xFFFF
    if st == 0x0001:        # A490
        sprite = A490_SHOT_SPRITE
    elif st == 0x0002:      # A499
        direction = a3ec & 0xFFFF
        if direction == 0xFFFF:
            direction = A499_SHOT_DIR_DEFAULT
            if (source_y & 0xFFFF) > A499_SHOT_Y_THRESHOLD:
                direction = A499_SHOT_DIR_HIGH_Y
        sprite = A499_SHOT_SPRITE_DIR1 if direction == A499_SHOT_DIR_HIGH_Y else A499_SHOT_SPRITE_OTHER
    return PlayerShotSpawn(
        slot_offset=alloc.offset, new_cursor=alloc.cursor,
        active_word=seed.active_word, scan_enable_or_solid=seed.scan_enable_or_solid,
        direction_or_step=direction, sprite_or_state=sprite,
        scan_flag=seed.scan_flag, hazard_class=seed.hazard_class,
        logic_id=seed.logic_id, substate=seed.substate,
        x_word=source_x & 0xFFFF, y_word=(source_y + A41A_SHOT_Y_BIAS) & 0xFFFF,
    )


# A41A two-slot pair variants (A958 state 3/4 -> A464/A438 -> run_a438_pair).  Each state overrides the
# spawned slots' logic_id (+18) and sprite (+8); the second shot's X is the first's + 8.
A41A_PAIR_STATES = {0x0003: (0x0007, 0x0037), 0x0004: (0x0008, 0x0035)}  # state -> (logic_id +18, sprite +8)
A41A_PAIR_X_OFFSET = 0x0008                            # the second shot's X = the first's + 8 (A438 tail)


def _player_shot_slot(seed: ObjectSpawnSeedA4EA, alloc: FreeSlotAllocation,
                      x: int, y: int, logic_id: int, sprite: int,
                      direction: int | None = None, substate: int | None = None) -> PlayerShotSpawn:
    """One A41A-family player-shot slot: the A4EA seed with X/Y + logic_id/sprite overrides applied.

    ``direction`` overrides the seed's ``direction_or_step`` when given (A1C8's second shot picks its
    direction from the input bits); ``substate`` overrides the seed's ``substate`` (A114's burst stamps 7);
    the A41A/A378 callers leave both None to keep the seed's values."""
    return PlayerShotSpawn(
        slot_offset=alloc.offset, new_cursor=alloc.cursor,
        active_word=seed.active_word, scan_enable_or_solid=seed.scan_enable_or_solid,
        direction_or_step=(seed.direction_or_step if direction is None else direction & 0xFFFF),
        sprite_or_state=sprite & 0xFFFF,
        scan_flag=seed.scan_flag, hazard_class=seed.hazard_class,
        logic_id=logic_id & 0xFFFF,
        substate=(seed.substate if substate is None else substate & 0xFFFF),
        x_word=x & 0xFFFF, y_word=y & 0xFFFF,
    )


def native_a41a_pair(pool: ObjectPool, cursor: int, state: int,
                     source_x: int, source_y: int, a3a0: int
                     ) -> tuple[PlayerShotSpawn, PlayerShotSpawn] | None:
    """Pure WHOLE A41A two-slot player-shot pair (the A958 state 3/4 cs:A42C targets A464/A438).

    Gated by ``DS:A3A0 == 0`` (no spawn otherwise).  Allocates two gameplay slots -- the first is marked
    active so :func:`object_pool_find_free` skips it for the second (the VM stamps the A4EA seed, which
    sets ``active``, before the second allocation) -- each stamped with the A4EA seed + ``{X, Y =
    source_y + 4}`` and the per-state ``logic_id`` (+18) / sprite (+8) overrides (state 3 -> 7/37h, state
    4 -> 8/35h); the second shot's X is the first's + 8.  Returns ``(slot1, slot2)`` or None (gate closed,
    or a full pool -- the 7550 recycle is unmodelled).  The A970 += 2 counter is the fanout caller's, not
    part of the per-shot stamp."""
    st = state & 0xFFFF
    if st not in A41A_PAIR_STATES:
        return None
    if (a3a0 & 0xFFFF) != 0x0000:
        return None  # the A3A0 gate is closed -> no spawn this dispatch
    stamp_logic, stamp_sprite = A41A_PAIR_STATES[st]
    seed = object_spawn_seed_a4ea()
    y = (source_y + A41A_SHOT_Y_BIAS) & 0xFFFF
    alloc1 = object_pool_find_free(pool, cursor)
    if alloc1.offset is None:
        return None  # pool full -> the 7550 recycle path (not modelled)
    slot1 = _player_shot_slot(seed, alloc1, source_x, y, stamp_logic, stamp_sprite)
    index1 = (((alloc1.offset - pool.base) & 0xFFFF) // (pool.stride & 0xFFFF))
    pool1 = pool.with_word(index1, 0x00, seed.active_word)  # the seed marks slot1 active before alloc 2
    alloc2 = object_pool_find_free(pool1, alloc1.cursor)
    if alloc2.offset is None:
        return None
    slot2 = _player_shot_slot(seed, alloc2, (source_x + A41A_PAIR_X_OFFSET) & 0xFFFF, y,
                              stamp_logic, stamp_sprite)
    return (slot1, slot2)


# A378 SI-follow-up: A3FF runs it after each A41A dispatch to spawn two more shots from the same schedule
# entry (the run_a396_body body, called twice with the first slot's logic_id overridden to 6 at A391).
A378_X_BIAS = 0x0004                                    # A378: X = [si+2] + 4
A378_Y_ALIGN = 0xFFFC                                   # A378: Y = ([si+4] + 4) & ~3 (align to 4)
A378_SPRITE = 0x0008                                    # A378: sprite (+8) for both shots
A378_SLOT1_LOGIC = 0x0006                              # first shot logic_id (+18), overridden from 5 at A391
A378_SLOT2_LOGIC = 0x0005                              # second shot logic_id (+18)


def native_a378_followup(pool: ObjectPool, cursor: int, source_x: int, source_y: int,
                         a95e: int, a3a4: int) -> tuple[PlayerShotSpawn, PlayerShotSpawn] | None:
    """Pure WHOLE A378 SI-follow-up player-shot pair (the A3FF post-A41A two-shot spawn).

    Gated by ``DS:A95E != 0`` and ``DS:A3A4 == 0`` (no spawn otherwise; the caller also gates SI != FFFF).
    Allocates two gameplay slots (threading the cursor + the first's active word, like the A41A pair), each
    stamped with the A4EA seed + ``{X = source_x + 4, Y = (source_y + 4) & ~3, sprite 8}``; the first
    shot's ``logic_id`` (+18) is 6, the second's 5.  Returns ``(slot1, slot2)`` or None (gated, or a full
    pool -- the 7550 recycle is unmodelled).  The A976 += 1-per-slot counter and the BEFF stamp are the
    fanout caller's, not part of the per-shot stamp."""
    if (a95e & 0xFFFF) == 0x0000 or (a3a4 & 0xFFFF) != 0x0000:
        return None  # the A95E / A3A4 gates are closed -> no spawn
    seed = object_spawn_seed_a4ea()
    x = (source_x + A378_X_BIAS) & 0xFFFF
    y = ((source_y + A41A_SHOT_Y_BIAS) & A378_Y_ALIGN) & 0xFFFF
    alloc1 = object_pool_find_free(pool, cursor)
    if alloc1.offset is None:
        return None  # pool full -> the 7550 recycle path (not modelled)
    slot1 = _player_shot_slot(seed, alloc1, x, y, A378_SLOT1_LOGIC, A378_SPRITE)
    index1 = (((alloc1.offset - pool.base) & 0xFFFF) // (pool.stride & 0xFFFF))
    pool1 = pool.with_word(index1, 0x00, seed.active_word)  # the seed marks slot1 active before alloc 2
    alloc2 = object_pool_find_free(pool1, alloc1.cursor)
    if alloc2.offset is None:
        return None
    slot2 = _player_shot_slot(seed, alloc2, x, y, A378_SLOT2_LOGIC, A378_SPRITE)
    return (slot1, slot2)


# A584 dual-anchor spawn: two A571-anchored crawler slots (the A378 projectile's FULL-fanout sibling).
A584_ANCHOR_BIAS = 0x000A                              # A571: X = [bp+2] + 0xA, Y = [bp+4] + 0xA
A584_Y_ALIGN = 0xFFFC                                  # then Y &= ~3 (align down to a 4-pixel boundary)
A584_SPRITE = 0x0008                                   # both slots: sprite (+8) = 8
A584_SLOT1_LOGIC = 0x0005                              # first slot logic_id (+18)
A584_SLOT2_LOGIC = 0x0006                              # second slot logic_id (+18)


def native_a584(pool: ObjectPool, cursor: int, source_x: int, source_y: int,
                a95e: int, a3a4: int) -> tuple[PlayerShotSpawn, PlayerShotSpawn] | None:
    """Pure WHOLE A584 dual-anchor player-spawn pair (the A067 FULL-fanout terrain-crawler spawner).

    Gated by ``DS:A95E != 0`` and ``DS:A3A4 == 0`` (A3A4 counts live logic_id 5/6 crawlers, so this only
    re-seeds the pair when none are alive).  Allocates two gameplay slots (threading the cursor + the
    first's active word, like the A41A pair), each A571-anchored at ``{X = source_x + 0xA, Y = (source_y +
    0xA) & ~3}`` with the A4EA seed + sprite 8; the first slot's ``logic_id`` (+18) is 5, the second's 6.
    Returns ``(slot1, slot2)`` or None (gated, or a full pool -- the 7550 recycle is unmodelled).  The
    A976 += 1-per-slot counter and the BEFF stamp are the caller's, not part of the per-slot stamp."""
    if (a95e & 0xFFFF) == 0x0000 or (a3a4 & 0xFFFF) != 0x0000:
        return None  # the A95E / A3A4 gates are closed -> no spawn
    seed = object_spawn_seed_a4ea()
    x = (source_x + A584_ANCHOR_BIAS) & 0xFFFF
    y = ((source_y + A584_ANCHOR_BIAS) & 0xFFFF) & A584_Y_ALIGN
    alloc1 = object_pool_find_free(pool, cursor)
    if alloc1.offset is None:
        return None  # pool full -> the 7550 recycle path (not modelled)
    slot1 = _player_shot_slot(seed, alloc1, x, y, A584_SLOT1_LOGIC, A584_SPRITE)
    index1 = (((alloc1.offset - pool.base) & 0xFFFF) // (pool.stride & 0xFFFF))
    pool1 = pool.with_word(index1, 0x00, seed.active_word)  # the seed marks slot1 active before alloc 2
    alloc2 = object_pool_find_free(pool1, alloc1.cursor)
    if alloc2.offset is None:
        return None
    slot2 = _player_shot_slot(seed, alloc2, x, y, A584_SLOT2_LOGIC, A584_SPRITE)
    return (slot1, slot2)


# A114 three-shot burst (the a96e-schedule weapon; the FULL-fanout be06==8 child).  All three shots share
# the A4EA seed (sprite 32h kept) + logic_id 0Ch + substate 7; each reads the schedule entry [A96E] for
# its X0=[ptr+2]/Y0=[ptr+4] base, then applies a per-shot {dx, dy, direction} (shot 1 keeps the seed dir).
A114_LOGIC = 0x000C
A114_SUBSTATE = 0x0007
A114_SCHEDULE_PTR = 0xA96E
A114_SHOTS = (
    (-0x0006, +0x0004, None),      # shot 1: X0-6, Y0+4, seed direction
    (-0x0002, -0x0004, 0x0007),    # shot 2: X0-2, Y0-4, direction 7
    (-0x0002, +0x000C, 0x0001),    # shot 3: X0-2, Y0+0Ch, direction 1
)


def native_a114(pool: ObjectPool, cursor: int, a3a6: int, read_ds_word) -> tuple[PlayerShotSpawn, ...] | None:
    """Pure WHOLE 1010:A114 three-shot burst (the a96e-schedule / be06==8 fanout child).

    Gated by ``DS:A3A6 == 0``.  Reads the schedule entry pointer ``DS:A96E`` once for the shot base
    ``{X0 = [ptr+2], Y0 = [ptr+4]}``, then spawns three A4EA-seed slots (sprite 32h kept, ``logic_id`` 0Ch,
    ``substate`` 7) at the per-shot ``{X0+dx, Y0+dy}`` with the per-shot direction (shot 1 keeps the seed's
    0), threading the cursor + each slot's active word so the next :func:`object_pool_find_free` skips it.
    Returns the three shots or None (gate closed, or a full pool -- the 7550 recycle is unmodelled).  The
    A974 += 1-per-shot counter and the BEFF stamp are the caller's, not part of the per-shot stamp."""
    if (a3a6 & 0xFFFF) != 0x0000:
        return None  # the A3A6 gate is closed -> no spawn
    schedule = read_ds_word(A114_SCHEDULE_PTR) & 0xFFFF          # si = [A96E]
    x0 = read_ds_word((schedule + 0x02) & 0xFFFF)               # [si+2]
    y0 = read_ds_word((schedule + 0x04) & 0xFFFF)               # [si+4]
    seed = object_spawn_seed_a4ea()
    shots: list[PlayerShotSpawn] = []
    p, cur = pool, cursor
    for dx, dy, direction in A114_SHOTS:
        alloc = object_pool_find_free(p, cur)
        if alloc.offset is None:
            return None  # pool full -> the 7550 recycle path (not modelled)
        shots.append(_player_shot_slot(
            seed, alloc, (x0 + dx) & 0xFFFF, (y0 + dy) & 0xFFFF,
            A114_LOGIC, seed.sprite_or_state, direction=direction, substate=A114_SUBSTATE))
        index = (((alloc.offset - p.base) & 0xFFFF) // (p.stride & 0xFFFF))
        p = p.with_word(index, 0x00, seed.active_word)          # seed marks the slot active before the next alloc
        cur = alloc.cursor
    return tuple(shots)


# A0E8 early-level muzzle-projected pair tails (the early-scroll versions of the A41A 3/4 pair):
# the A958 state dispatches A2F6 (==4) / A337 (==3); each stamps both slots with its (logic_id+18, sprite+08).
A0E8_PAIR_TARGETS = {
    0x0004: (0x0008, 0x0035),   # A2F6: A958 == 4
    0x0003: (0x0007, 0x0037),   # A337: A958 == 3
}
A0E8_PAIR_X_OFFSET = 0x0008     # the second slot's X is the first's + 8 (the A332/A373 post-add)


def native_a0e8_pair(pool: ObjectPool, cursor: int, state: int, source_index: int,
                     source_x: int, source_y: int, a3a0: int, read_ds_word
                     ) -> tuple[PlayerShotSpawn, PlayerShotSpawn] | None:
    """Pure WHOLE A2F6 (A958==4) / A337 (A958==3) early-level two-slot muzzle pair.

    These are the A0E8 (early-scroll) counterparts of the A41A 3/4 pair: gated by ``DS:A3A0 == 0``, they
    spawn two A4EA-seed slots at the A1AE-projected muzzle (:func:`a1ae_project`), each stamped with the
    state's ``logic_id`` (+18) / sprite (+08) override (state 4 -> 8/35h, state 3 -> 7/37h); the second
    slot's X is the first's + 8.  Returns ``(slot1, slot2)`` or None (not a pair state, gate closed, or a
    full pool -- the 7550 recycle is unmodelled).  The A970 += 2 counter is the caller's, not the stamp."""
    st = state & 0xFFFF
    if st not in A0E8_PAIR_TARGETS:
        return None
    if (a3a0 & 0xFFFF) != 0x0000:
        return None  # the A3A0 gate is closed -> no spawn this dispatch
    stamp_logic, stamp_sprite = A0E8_PAIR_TARGETS[st]
    x, y = a1ae_project(read_ds_word, source_index, source_x, source_y)
    seed = object_spawn_seed_a4ea()
    alloc1 = object_pool_find_free(pool, cursor)
    if alloc1.offset is None:
        return None  # pool full -> the 7550 recycle path (not modelled)
    slot1 = _player_shot_slot(seed, alloc1, x, y, stamp_logic, stamp_sprite)
    index1 = (((alloc1.offset - pool.base) & 0xFFFF) // (pool.stride & 0xFFFF))
    pool1 = pool.with_word(index1, 0x00, seed.active_word)  # the seed marks slot1 active before alloc 2
    alloc2 = object_pool_find_free(pool1, alloc1.cursor)
    if alloc2.offset is None:
        return None
    slot2 = _player_shot_slot(seed, alloc2, (x + A0E8_PAIR_X_OFFSET) & 0xFFFF, y, stamp_logic, stamp_sprite)
    return (slot1, slot2)


# A515 linked-anchor spawn (the counter-driven link weapon): partial-stamps a 7547-found free slot, so the
# un-listed words keep the slot's stale prior contents (no A4EA seed).  Gated by A960 != 0 && A97E != 1.
A515_GATE_A97E_BLOCK = 0x0001    # A515 runs only when DS:A97E != 1 (and DS:A960 != 0)
A515_ANCHOR_BIAS = 0x000A        # A571: X/Y = source + 0xA (no Y-align, unlike A584)
A515_ACTIVE = 0x0001             # [bx+00] active_word
A515_SCAN_FLAG = 0x0000          # [bx+14] scan_flag
A515_HAZARD_CLASS = 0x0002       # [bx+16] hazard_class
A515_LOGIC_ID = 0x000A           # [bx+18] logic_id
A515_SUBSTATE = 0x0001           # [bx+1C] substate
A515_SCAN_ENABLE = 0x0001        # [bx+1E] scan_enable_or_solid
# [bx+30] = the B15A-found target offset (acquired_target_ptr)


def native_a515(gameplay_pool: ObjectPool, cursor_95da: int, effect_pool: ObjectPool, cursor_a43a: int,
                source_x: int, source_y: int, a960: int, a97e: int) -> A515LinkSpawn | None:
    """Pure WHOLE 1010:A515 linked-anchor spawn (the counter-driven link weapon).

    Gated by ``DS:A960 != 0`` and ``DS:A97E != 1``.  Allocates a free gameplay slot with the raw 7547
    finder (advancing DS:95DA), anchors it at ``{X = source_x + 0xA, Y = source_y + 0xA}`` (A571, no
    align), then runs the :func:`native_b15a_scan` link scan over the effect pool (advancing DS:A43A).  If
    the scan finds a target the slot is ACTIVATED with A515's 9 word overrides (active 1, scan_flag 0,
    hazard 2, logic_id 0Ah, substate 1, scan_enable 1, the anchored X/Y, and acquired_target_ptr = the
    found offset) over its stale prior contents, and A97E += 1 / A960 -= 1; if it finds nothing the slot
    stays inactive (no spawn) and the counters are unchanged -- but both cursors still advanced.  Returns
    an :class:`A515LinkSpawn`, or None when a gate is closed (immediate ret, no side effects) or the pool
    is full (the 7550 recycle is unmodelled).  The BEFF=11h sound is the caller's, not modelled here."""
    if (a960 & 0xFFFF) == 0x0000 or (a97e & 0xFFFF) == A515_GATE_A97E_BLOCK:
        return None  # gate closed -> A515 rets immediately, no side effects
    alloc = object_pool_find_free(gameplay_pool, cursor_95da)
    if alloc.offset is None:
        return None  # 7547 full-pool recycle (the 7550 path) is unmodelled
    found, new_a43a = native_b15a_scan(effect_pool, cursor_a43a)
    if found is None:
        # B15A found no link target: the 7547 slot stays inactive (no spawn), counters unchanged.
        return A515LinkSpawn(slot_offset=None, slot_words=None, cursor_95da=alloc.cursor,
                             cursor_a43a=new_a43a, a97e=a97e & 0xFFFF, a960=a960 & 0xFFFF)
    index = (((alloc.offset - gameplay_pool.base) & 0xFFFF) // (gameplay_pool.stride & 0xFFFF))
    words = list(gameplay_pool.words(index))   # the slot's stale prior contents (7547 does not seed)
    words[0x00 >> 1] = A515_ACTIVE
    words[0x02 >> 1] = (source_x + A515_ANCHOR_BIAS) & 0xFFFF   # A571 anchor X
    words[0x04 >> 1] = (source_y + A515_ANCHOR_BIAS) & 0xFFFF   # A571 anchor Y
    words[0x14 >> 1] = A515_SCAN_FLAG
    words[0x16 >> 1] = A515_HAZARD_CLASS
    words[0x18 >> 1] = A515_LOGIC_ID
    words[0x1C >> 1] = A515_SUBSTATE
    words[0x1E >> 1] = A515_SCAN_ENABLE
    words[0x30 >> 1] = found & 0xFFFF                           # acquired_target_ptr
    return A515LinkSpawn(slot_offset=alloc.offset, slot_words=tuple(words), cursor_95da=alloc.cursor,
                         cursor_a43a=new_a43a, a97e=(a97e + 1) & 0xFFFF, a960=(a960 - 1) & 0xFFFF)


# --- A067 child schedule walks (A3FF / A3CA) ------------------------------------------------------------
# These drive the A41A per-shot variants over the equipped weapon's shot schedules, threading the
# allocator across spawns, and compose the verified native_a41a_shot/pair (+ native_a378_followup) leaves.
A3CA_SIDE_ANCHOR_A3EC = (0x0007, 0x0001, 0x0007, 0x0001)  # A3CA sets DS:A3EC per source (A966/8/A/C)
A3FF_MIRROR_A3EC = 0xFFFF                                 # A3FF sets DS:A3EC = FFFFh for both sources (A962/A964)
_A41A_SINGLE_STATES = (0x0000, 0x0001, 0x0002)
_A41A_PAIR_STATES = (0x0003, 0x0004)


def _a41a_dispatch(pool: ObjectPool, cursor: int, fire_state: int,
                   source_x: int, source_y: int, a3ec: int, a3a0: int) -> tuple[PlayerShotSpawn, ...]:
    """One A41A jump-table dispatch (by the fire state DS:A958): the 0/1/2 single variant or the 3/4 pair.

    Returns the tuple of shots A41A produced (0 for a full pool / state 5 / the gated pair, 1 single, 2
    pair)."""
    st = fire_state & 0xFFFF
    if st in _A41A_SINGLE_STATES:
        shot = native_a41a_shot(pool, cursor, st, source_x, source_y, a3ec)
        return (shot,) if shot is not None else ()
    if st in _A41A_PAIR_STATES:
        pair = native_a41a_pair(pool, cursor, st, source_x, source_y, a3a0)
        return pair if pair is not None else ()
    return ()  # state 5 (44AF) or an out-of-range table target -> no native shot


def _thread_player_shots(pool: ObjectPool, cursor: int,
                         shots: tuple[PlayerShotSpawn, ...]) -> tuple[ObjectPool, int]:
    """Mark each freshly spawned slot active (so the next object_pool_find_free skips it) and advance the
    allocator cursor, exactly as the VM's per-A4EA seed + DS:95DA park do."""
    stride = pool.stride & 0xFFFF
    base = pool.base & 0xFFFF
    for shot in shots:
        index = (((shot.slot_offset - base) & 0xFFFF) // stride)
        pool = pool.with_word(index, 0x00, shot.active_word)
        cursor = shot.new_cursor
    return pool, cursor


def native_a3ca(pool: ObjectPool, cursor: int, fire_state: int,
                side_schedule: tuple, a3a0: int, read_ds_word) -> PlayerFanoutResult:
    """Pure 1010:A3CA side-anchor walk: four A41A dispatches over the side schedules (DS:A966/A968/A96A/
    A96C), with DS:A3EC alternating 7/1/7/1.  Each present schedule entry (SI != FFFFh) reads its shot
    coordinate {[si+2], [si+4]} and dispatches through :func:`_a41a_dispatch`; the cursor + the spawned
    slots are threaded across the four sources.  ``side_schedule`` is the four SI pointer values; absent
    sources (FFFFh) spawn nothing (the VM's A41A returns early)."""
    spawns: list[PlayerShotSpawn] = []
    for si, a3ec in zip(side_schedule, A3CA_SIDE_ANCHOR_A3EC):
        if (si & 0xFFFF) == 0xFFFF:
            continue
        shots = _a41a_dispatch(pool, cursor, fire_state,
                               read_ds_word((si + 0x02) & 0xFFFF), read_ds_word((si + 0x04) & 0xFFFF),
                               a3ec, a3a0)
        if shots:
            spawns.extend(shots)
            pool, cursor = _thread_player_shots(pool, cursor, shots)
    return PlayerFanoutResult(spawns=tuple(spawns), final_cursor=cursor & 0xFFFF)


def native_a3ff(pool: ObjectPool, cursor: int, fire_state: int, mirror_schedule: tuple,
                a3a0: int, a95e: int, a3a4: int, read_ds_word) -> PlayerFanoutResult:
    """Pure 1010:A3FF mirrored-anchor walk: per source (DS:A962/A964, DS:A3EC = FFFFh) an A41A dispatch
    followed by the A378 SI follow-up.  Each present source (SI != FFFFh) reads {[si+2], [si+4]}, runs
    :func:`_a41a_dispatch` then :func:`native_a378_followup` (which spawns only when its A95E/A3A4 gates
    are open -- usually a no-op in the corpus); the cursor + spawned slots thread across both sources and
    both stages."""
    spawns: list[PlayerShotSpawn] = []
    for si in mirror_schedule:
        if (si & 0xFFFF) == 0xFFFF:
            continue
        src_x, src_y = read_ds_word((si + 0x02) & 0xFFFF), read_ds_word((si + 0x04) & 0xFFFF)
        shots = _a41a_dispatch(pool, cursor, fire_state, src_x, src_y, A3FF_MIRROR_A3EC, a3a0)
        if shots:
            spawns.extend(shots)
            pool, cursor = _thread_player_shots(pool, cursor, shots)
        follow = native_a378_followup(pool, cursor, src_x, src_y, a95e, a3a4)
        if follow is not None:
            spawns.extend(follow)
            pool, cursor = _thread_player_shots(pool, cursor, follow)
    return PlayerFanoutResult(spawns=tuple(spawns), final_cursor=cursor & 0xFFFF)


# --- A067 EARLY-path fire tails (A1C8 / A19F) -- the early-level fire (DS:2350 <= B6h) -------------------
A1AE_OFFSET_TABLE = 0xA3A8     # the A1AE muzzle-offset table, indexed by the source object's +8 field x 4


def a1ae_project(read_ds_word, source_index: int, source_x: int, source_y: int) -> tuple[int, int]:
    """Pure 1010:A1AE muzzle-coordinate projection: the spawned shot's {X, Y} is the A3A8 offset-table
    entry (indexed by the firing object's +8 field) added to the firing object's position {[bp+2],[bp+4]}.
    ``read_ds_word(off)`` reads the DS word at ``off`` (the A3A8 table lives in the data segment)."""
    off = (A1AE_OFFSET_TABLE + ((source_index & 0xFFFF) << 2)) & 0xFFFF
    return ((read_ds_word(off) + source_x) & 0xFFFF,
            (read_ds_word((off + 2) & 0xFFFF) + source_y) & 0xFFFF)


def native_a19f_tail(pool: ObjectPool, cursor: int, source_index: int, source_x: int, source_y: int,
                     read_ds_word) -> PlayerShotSpawn | None:
    """Pure 1010:A19F early-default fire tail: one A4EA-seed shot at the A1AE-projected muzzle position.

    The A067 EARLY path (DS:2350 <= B6h AND BDAC == 0) reaches A19F when the fire state DS:A958 != 2.  It
    allocates one gameplay slot, stamps the A4EA seed (logic_id 2, sprite 32h, direction 0), and sets the
    shot's {X, Y} from :func:`a1ae_project`.  Returns None on a full pool (the 7550 recycle is unmodelled)."""
    alloc = object_pool_find_free(pool, cursor)
    if alloc.offset is None:
        return None
    seed = object_spawn_seed_a4ea()
    x, y = a1ae_project(read_ds_word, source_index, source_x, source_y)
    return _player_shot_slot(seed, alloc, x, y, seed.logic_id, seed.sprite_or_state)


# A1C8 (the A958 == 2 early tail) second-shot direction/sprite, picked from the input DS:98BE.
A1C8_SLOT1_SPRITE = 0x0018
A1C8_INPUT_BIT1, A1C8_INPUT_BIT0 = 0x02, 0x01
A1C8_SECOND_SHOT = {  # input bit -> (direction, sprite)
    A1C8_INPUT_BIT1: (0x0007, 0x001F),
    A1C8_INPUT_BIT0: (0x0001, 0x0019),
    0x00: (0x0000, 0x0018),
}


def native_a1c8_tail(pool: ObjectPool, cursor: int, source_index: int, source_x: int, source_y: int,
                     input_98be: int, read_ds_word) -> tuple[PlayerShotSpawn, PlayerShotSpawn] | None:
    """Pure 1010:A1C8 early fire tail (fire state DS:A958 == 2): two A4EA-seed shots at the same A1AE-
    projected muzzle.  The first shot keeps the seed direction and sprite 18h; the second's direction and
    sprite come from the input DS:98BE -- bit 1 set -> 7/1Fh, else bit 0 set -> 1/19h, else 0/18h.  The
    second slot threads off the first (its active word is set before the second allocation).  Returns None
    on a full pool (the 7550 recycle is unmodelled)."""
    alloc1 = object_pool_find_free(pool, cursor)
    if alloc1.offset is None:
        return None
    seed = object_spawn_seed_a4ea()
    x, y = a1ae_project(read_ds_word, source_index, source_x, source_y)
    slot1 = _player_shot_slot(seed, alloc1, x, y, seed.logic_id, A1C8_SLOT1_SPRITE)
    index1 = (((alloc1.offset - pool.base) & 0xFFFF) // (pool.stride & 0xFFFF))
    pool1 = pool.with_word(index1, 0x00, seed.active_word)
    alloc2 = object_pool_find_free(pool1, alloc1.cursor)
    if alloc2.offset is None:
        return None
    flags = input_98be & 0x00FF
    if flags & A1C8_INPUT_BIT1:
        direction, sprite = A1C8_SECOND_SHOT[A1C8_INPUT_BIT1]
    elif flags & A1C8_INPUT_BIT0:
        direction, sprite = A1C8_SECOND_SHOT[A1C8_INPUT_BIT0]
    else:
        direction, sprite = A1C8_SECOND_SHOT[0x00]
    slot2 = _player_shot_slot(seed, alloc2, x, y, seed.logic_id, sprite, direction=direction)
    return (slot1, slot2)
