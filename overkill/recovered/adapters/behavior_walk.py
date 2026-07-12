"""The NATIVE object behavior walk (``1010:A9D3..AA25``) -- the registry stage, memory-shaped.

Composes the recovered pure systems into the VM's per-frame object walk, over any ``rw``/``ww``
memory-shaped state (``MutFlatMemory`` in the shadow probe; the NativeGame projections later):

* the ``A8C2 == 1`` leader-tick gate (``F797`` unrecovered -> fail-loud),
* the EFFECT pool loop (``cx = 0x23..1`` via the ``DS:32CA`` table -- HIGH record to LOW; the
  ``DS:2340`` tick incs per entry BEFORE the active check, wrapping at ``0x5DC``),
* ``DS:2346 = 0`` between pools, then the GAMEPLAY pool loop (``cx = 0x22..1`` via ``DS:8D12``),
* per active record the TYPE dispatch (``+0x16``): 0 -> nop, 6 -> the companion
  (``step_companion_ab10``), 2/4 -> the EFAE position mirror (``D1FE``/``D200``) then the BEHAVIOR
  registry (``+0x18``): 0x1F -> ``step_wave_controller_1f`` (+ the arrival burst through the native
  ``7524`` allocator), 0x20 -> ``step_enemy_behavior_20`` (+ the seek/shot application through the
  native ``7573`` allocator), 0x0B -> ``object_update_b24d``.  ANY other active type/behavior
  raises :class:`RecoveryGap` -- the registry is fail-loud, never silently partial,
* the BC45/BC4B postmove tail per walked record: drift, Y clamp, X-bounds death, the BCCB
  anchor-touch, and the 62F6 object-vs-object COMBAT chain (62F6 overlap -> BEC5 reaction ->
  BF25 damage -> the full BFC7 death; player shots are the solid candidates).

The trailing far call ``1F8F:0922`` is OUTSIDE this stage (the shadow probe compares at ``AA25``).
Verified by ``probes/verify_native_behavior_walk`` (the whole-walk shadow over fast-forwarded
frames from L1_start) and ``probes/verify_native_combat`` (the kill / no-hit / survive combat
driven oracle, full-DGROUP zero diff).
"""
from __future__ import annotations

from types import SimpleNamespace

from overkill.recovered.domain.coords import i16
from overkill.recovered.domain.gaps import RecoveryGap
from overkill.recovered.domain.movement import MovementTarget
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.collision import (
    view_contact_center_from_offsets_aa46,
    view_contact_rect_test,
)
from overkill.recovered.systems.companion import step_companion_ab10
from overkill.recovered.systems.contact_step import contact_probe_afd8
from overkill.recovered.systems.enemy_behaviors import (
    RAMP_29_DEATH_Y_MAX,
    RAMP_29_DEATH_Y_MIN,
    RAMP_29_STEER_MODE_AFTER,
    RAMP_29_STEER_MODE_DURING,
    MORPH_26_RAMP_SOUND,
    WAYPOINT_FOLLOWER_MAX_RETRIES,
    WAYPOINT_FOLLOWER_TABLE_SEED,
    dying_latch9_morph_be60,
    morph_26_is_finished,
    morph_26_should_ramp,
    morph_26_should_reset,
    retarget_delta_toward_anchor_74e2,
    step_animated_spawner_90_91,
    step_bounce_scanner_2f,
    step_enemy_behavior_20,
    step_ramp_steer_29,
    step_spawner_28,
    step_spawner_anim_30,
    step_sprite_scroller_27_835d,
    step_wave_controller_1f,
    step_waypoint_follower_11_12,
)
from overkill.recovered.systems.scenery_behaviors import (
    GROUND_CRAWLER_CHILD_SPRITE,
    GROUND_CRAWLER_CHILD_XY_BIAS,
    GROUND_CRAWLER_LEFT_DIRECTION,
    GROUND_CRAWLER_LEFT_ROW_BIAS,
    GROUND_CRAWLER_PROBE_X_BIAS,
    GROUND_CRAWLER_RIGHT_DIRECTION,
    SCENERY_19_EMIT_DIRECTION,
    bb03_bounce_after_step,
    ground_crawler_should_spawn,
    ground_crawler_sprite_8b_8c,
    scenery_19_should_emit,
    scenery_89_should_emit,
    step_scenery_emitter_sprite_19,
    step_scenery_emitter_sprite_89,
    step_scenery_sprite_ramp_1a,
)
from overkill.recovered.systems.tilemap import compute_tile_probe_5073, lookup_tile_class_byte
from overkill.recovered.domain.tilemap import TileProbeInput
from overkill.recovered.systems.frame_loop import (
    canned_random_next_4d95,
    enemy_shot_stamp_7476,
    enemy_spawn_stamp_8209,
    outro_autopilot_bits_9ad1,
    pickup_heal_9d67,
    step_a47c_handler_9a16,
    step_scripted_move_counters_9a3e,
)
from overkill.recovered.systems.collision import (
    PLAYER_HAZARD_SCAN_REQUIRED_GATE,
    bec5_candidate_deactivated,
    bec5_moving_object_outcome,
    clamp_postmove_y_bcb1,
    collision_damage_counter_chain_bf25,
    object_overlap_scan_62f6,
    object_postmove_x_bounds_deactivates_bc4b,
    player_hazard_scan_hit,
    postmove_contact_window_test_aa71,
)
from overkill.recovered.domain.object_slots import ObjectSlotRecord
from overkill.recovered.domain.collision import ProbePoint
from overkill.recovered.views.object_slots import (
    GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL,
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    read_object_pool,
)
from overkill.recovered.domain.collision import PostMoveContactWindow
from overkill.recovered.systems.movement import (
    object_delta_5e1b,
    object_delta_steer_5e42,
    object_target_seek_step_5db2,
    step_operations_for_direction,
)
from overkill.recovered.systems.objects import (
    child_spawn_seed_c237,
    AED8_CONTACT_DEATH_X,
    AED8_SUBSTATE_SKIP_OVERLAP,
    child_spawn_sound_c237,
    child_spawn_throttle_c237,
    object_update_ae2c,
    object_bounds_tile_decision_ad60,
    overlap_contact_box_contains,
    object_tile_probe_deactivates_ad60,
    object_update_ae7d,
    object_update_aed8,
    object_update_af60,
    object_update_b24d,
    object_update_b86d,
)
from overkill.recovered.systems.score import bcd_add_score

# the C054 death-beat schedule re-arm: dying CONTROLLER behaviors chain the NEXT wave schedule
_DEATH_NEXT_SCHEDULE = {0x7E: 0xA79C, 0x7D: 0xA6F0, 0x1F: 0xA83E, 0x1C: 0xA82A,
                        0x15: 0xA5C0, 0x13: 0xA4E4}
_DEATH_DEC_ONLY = frozenset((0x16, 0x17, 0x18, 0x7F, 0x80, 0x81, 0x1D, 0x1E, 0x20, 0x21, 0x22,
                             0x61, 0x62, 0x65, 0x14))

DS = 0x25CC
CODE_SEG = 0x1010
TILE_PLANE_SEG_CELL = 0x9592       # CS:[9592] -- the level tile-plane segment (read live like 4B4A)
TILE_CLASS_TABLE_C3AA = 0xC3AA     # DS:C3AA -- the 256-entry raw-tile -> class map (505B)
EFFECT_TABLE_32CA = 0x32CA
GAMEPLAY_TABLE_8D12 = 0x8D12
EFFECT_SLOTS = 0x23
GAMEPLAY_SLOTS = 0x22
TICK_2340_PERIOD = 0x05DC
EFFECT_POOL_BASE, EFFECT_POOL_WRAP = 0x23B4, 0x2B5C          # the 7524 allocator scan bounds
# the 7573 twin: was 0x2CA4 (a stray, NOT slot-aligned value -- (0x2CA4-0x2B5C)/0x38 = 5.857, so the
# `cur == wrap` check could never trigger, letting the cursor drift past the pool into adjacent
# memory whenever a scan needed more than ~5 slots).  The canonical, slot-aligned sentinel already
# exists in views/object_slots.py; reuse it instead of a second, drifted copy.
GAMEPLAY_POOL_BASE, GAMEPLAY_POOL_WRAP = GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL


def _alloc(mem, cursor_cell: int, base: int, wrap: int, slots: int) -> int:
    """The 7524/7573 allocator: scan from the cursor for an inactive slot; cursor sticks to it."""
    cur = mem.rw(DS, cursor_cell)
    for _ in range(slots):
        if mem.rw(DS, cur) == 0:
            mem.ww(DS, cursor_cell, cur)
            return cur
        cur = cur + 0x38
        if cur == wrap:
            cur = base
    return 0xFFFF


def _apply_seek(mem, rec: int, target_y: int, target_x: int, mode: int) -> bool:
    """The B729/B85C move tail: target globals, the 5DB2 seek, then the +0x06 = 4 override."""
    mem.ww(DS, 0x2304, target_y)
    mem.ww(DS, 0x2306, target_x)
    mem.ww(DS, 0x2308, mode)
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))
    seek = object_target_seek_step_5db2(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x06),
        MovementTarget(y_word=target_y, x_word=target_x), mode, table)
    mem.ww(DS, rec + 0x02, seek.x_word)
    mem.ww(DS, rec + 0x04, seek.y_word)
    mem.ww(DS, rec + 0x06, seek.direction_or_step)
    # B729 exposes the seek's blocked state as `cmp [230A],0`; 230A is excluded shadow scratch, so a
    # caller that branches on it (behavior 0x2f) reads the pure result rather than the global.
    return seek.blocked


def _step_controller_1f(mem, rec: int) -> None:
    a482 = mem.rw(DS, 0xA482)
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))
    r = step_wave_controller_1f(
        x_word=mem.rw(DS, rec + 0x02), y_word=mem.rw(DS, rec + 0x04),
        direction=mem.rw(DS, rec + 0x06),
        schedule_x_raw=mem.rw(DS, a482), schedule_y=mem.rw(DS, (a482 + 2) & 0xFFFF),
        ring_cursor_a842=mem.rw(DS, 0xA842),
        ring_slot_at=lambda cur: (mem.rw(DS, cur & 0xFFFF), mem.rw(DS, (cur + 2) & 0xFFFF)),
        direction_table=table)
    for off, val in r.seek_globals.items():
        mem.ww(DS, off, val)
    mem.ww(DS, rec + 0x02, r.x_word)
    mem.ww(DS, rec + 0x04, r.y_word)
    mem.ww(DS, rec + 0x06, r.direction)
    mem.ww(DS, rec + 0x08, r.sprite)
    mem.ww(DS, 0xA482, (a482 + r.schedule_advance) & 0xFFFF)
    mem.ww(DS, 0xA842, r.ring_cursor_after)
    for stamp in r.spawn_stamps:
        slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
        if slot == 0xFFFF:
            continue
        mem.wb(DS, 0xBEFF, 0x0B)     # 8209's own (ungated) spawn-sound queue
        for off, val in stamp.items():
            mem.ww(DS, slot + off, val)
        mem.ww(DS, 0xA47E, (mem.rw(DS, 0xA47E) + 1) & 0xFFFF)


def _step_enemy_20(mem, rec: int) -> None:
    ring = tuple((mem.rw(DS, 0xA844 + i * 4), mem.rw(DS, 0xA844 + i * 4 + 2)) for i in range(20))
    rand_ring = tuple(mem.rw(DS, 0x20A8 + i * 2) for i in range(16))
    rand_val, rand_next = canned_random_next_4d95(mem.rw(DS, 0x20A6), rand_ring)
    r = step_enemy_behavior_20(
        x_word=mem.rw(DS, rec + 0x02), y_word=mem.rw(DS, rec + 0x04),
        substate_1c=mem.rw(DS, rec + 0x1C),
        target_x_34=mem.rw(DS, rec + 0x34), target_y_32=mem.rw(DS, rec + 0x32),
        a7a0=mem.rw(DS, 0xA7A0), clock_2338=mem.rw(DS, 0x2338), clock_2340=mem.rw(DS, 0x2340),
        clock_232e=mem.rw(DS, 0x232E), parity_2324=mem.rw(DS, 0x2324),
        active_enemies_a47e=mem.rw(DS, 0xA47E), anchor_y_2380=mem.rw(DS, 0x2380),
        ring_cursor_a842=mem.rw(DS, 0xA842),
        slot_ring=ring, random_value=rand_val)
    if r.shoot:
        # the B7F3 shoot runs BEFORE the dive/re-shuffle writes; shooter pos is the current record
        sx, sy = mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04)
        slot = _alloc(mem, 0x95DA, GAMEPLAY_POOL_BASE, GAMEPLAY_POOL_WRAP, GAMEPLAY_SLOTS)
        if slot != 0xFFFF:
            stamp = enemy_shot_stamp_7476(sx, sy, mem.rw(DS, 0xA8C2) == 1,
                                          mem.rw(DS, 0x237E), mem.rw(DS, 0x2380))
            for off, val in stamp.items():
                mem.ww(DS, slot + off, val)
            if mem.rb(DS, 0x98C0):
                mem.wb(DS, 0xBEFF, 0x1A)
    if r.random_stepped:
        mem.ww(DS, 0x20A6, rand_next)
    if r.move_to_target:
        _apply_seek(mem, rec, mem.rw(DS, rec + 0x32), mem.rw(DS, rec + 0x34), 2)
    for off, val in r.record_writes.items():
        mem.ww(DS, rec + off, val)
    for off, val in r.global_writes.items():
        mem.ww(DS, off, val)


def _read_slot_record(mem, rec: int) -> ObjectSlotRecord:
    """The 8-field ObjectSlotRecord the BDD0/BDE3 hazard scan reads (from a raw DGROUP slot)."""
    return ObjectSlotRecord(
        active_word=mem.rw(DS, rec + 0x00), x_word=mem.rw(DS, rec + 0x02),
        y_word=mem.rw(DS, rec + 0x04), gate_or_layer=mem.rw(DS, rec + 0x0A),
        link_key=mem.rw(DS, rec + 0x0E), scan_flag=mem.rw(DS, rec + 0x14),
        hazard_class=mem.rw(DS, rec + 0x16), logic_id=mem.rw(DS, rec + 0x18))


def _bdd0_contact_at(mem, rec: int):
    """1010:BDD0: the AFD8 contact predicate. Returns a ``contact_at(mirror_dx_x, mirror_dx_y) -> bool``
    closure the B022 step calls after each 1px move -- the deltas form the ``A438``/``A436`` probe
    point (this record's own X/Y plus the accumulated step).  If contact, the step is undone.

    BDD0 first guards on the PROBING record's own ``+0x0A`` (``== 1`` -> never contacts), then scans
    the WHOLE effect pool for an active type-4 hazard record (behavior 0x82..0x94) whose 0x20 box
    strictly contains the probe point and whose group (``+0x0E``) differs -- the already-recovered
    ``collision.player_hazard_scan_hit`` predicate, one candidate at a time."""
    current = _read_slot_record(mem, rec)
    orig_x, orig_y = current.x_word, current.y_word
    guarded = current.gate_or_layer == PLAYER_HAZARD_SCAN_REQUIRED_GATE   # BDD0/BDD4: [bp+0A]==1 -> no contact

    def contact_at(mirror_dx_x: int, mirror_dx_y: int) -> bool:
        if guarded:
            return False
        probe = ProbePoint(x_word=(orig_x + mirror_dx_x) & 0xFFFF,
                           y_word=(orig_y + mirror_dx_y) & 0xFFFF)
        for i in range(EFFECT_SLOTS):                    # the 0x23 effect-pool records, linearly (BDD9)
            cand = _read_slot_record(mem, EFFECT_POOL_BASE + i * 0x38)
            if player_hazard_scan_hit(current, cand, probe):
                return True
        return False

    return contact_at


def _bb03_bounce(mem, rec: int, tiles: LevelTileContext) -> None:
    """``1010:BB03`` -- the vertical bounce.  Direction 6 is the UP phase; ANY other direction is
    COERCED to 2 (BB24 stamps +06 = 2 BEFORE the boundary check and the step -- oracle: the L3
    frame-475 dir-4-stamped 0x19 record steps DOWN, not +X; L1/L2 never spawned a non-2/6 bouncer
    so the raw-direction shortcut never showed).  At the boundary (up: y == 0; down: y == 0xC0)
    flip with NO step; else ONE AFD8 contact-step; a blocked step flips to the opposite phase."""
    if mem.rw(DS, rec + 0x06) == 6:
        if mem.rw(DS, rec + 0x04) == 0:                 # BB0E: at the top -> flip down, no step
            mem.ww(DS, rec + 0x06, 2)
            return
        direction = 6
    else:
        mem.ww(DS, rec + 0x06, 2)                       # BB24: the down-phase coercion write
        if mem.rw(DS, rec + 0x04) == 0x00C0:            # BB29: at the bottom -> flip up, no step
            mem.ww(DS, rec + 0x06, 6)
            return
        direction = 2
    y = mem.rw(DS, rec + 0x04)
    result = contact_probe_afd8(mem.rw(DS, rec + 0x02), y, direction, mem.rw(DS, 0xA278),
                                tiles, _bdd0_contact_at(mem, rec))
    mem.ww(DS, rec + 0x02, result.x_word)
    mem.ww(DS, rec + 0x04, result.y_word)
    # AFD8's own observable DGROUP writes (the "scratch" cells the ASM itself writes every call,
    # not just internal working state) -- A430 the blocked flag, A432/A434 the pre-step snapshot,
    # A436/A438 the post-step mirror. 215A is excluded shadow scratch (written for fidelity anyway).
    mem.ww(DS, 0xA430, 1 if result.blocked else 0)
    mem.ww(DS, 0xA432, result.snap_x)
    mem.ww(DS, 0xA434, result.snap_y)
    mem.ww(DS, 0xA436, result.mirror_y)
    mem.ww(DS, 0xA438, result.mirror_x)
    mem.ww(DS, 0x215A, result.sample_215a)
    flip = bb03_bounce_after_step(direction, result.blocked)
    if flip is not None:
        mem.ww(DS, rec + 0x06, flip)


def _step_scenery_1a(mem, rec: int, tiles: LevelTileContext) -> None:
    mem.ww(DS, rec + 0x08, step_scenery_sprite_ramp_1a(mem.rw(DS, 0x2338)))
    _bb03_bounce(mem, rec, tiles)


def _step_scenery_19(mem, rec: int, tiles: LevelTileContext) -> None:
    mem.ww(DS, rec + 0x08, step_scenery_emitter_sprite_19(mem.rw(DS, 0x233A)))
    if scenery_19_should_emit(mem.rw(DS, 0x232E)):
        # 1010:BAE1: force direction=4 for the spawn, then restore this record's own direction.
        saved_dir = mem.rw(DS, rec + 0x06)
        mem.ww(DS, rec + 0x06, SCENERY_19_EMIT_DIRECTION)
        _spawn_child_c237(mem, rec, 0x19)
        mem.ww(DS, rec + 0x06, saved_dir)
    _bb03_bounce(mem, rec, tiles)


def _step_scenery_83(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x83 (``1010:89E9``): sprite = ``[233C] + 0x10``, the SAME ``[232E] == 0x3F``
    BAE1 dir-4 emit gate as 0x19, then the shared BB03 bounce."""
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x233C) + 0x0010) & 0xFFFF)
    if scenery_19_should_emit(mem.rw(DS, 0x232E)):
        saved_dir = mem.rw(DS, rec + 0x06)
        mem.ww(DS, rec + 0x06, SCENERY_19_EMIT_DIRECTION)
        _spawn_child_c237(mem, rec, 0x83)
        mem.ww(DS, rec + 0x06, saved_dir)
    _bb03_bounce(mem, rec, tiles)


def _step_scenery_89(mem, rec: int, tiles: LevelTileContext) -> None:
    mem.ww(DS, rec + 0x08, step_scenery_emitter_sprite_89(mem.rw(DS, 0x233C)))
    if scenery_89_should_emit(mem.rw(DS, 0x232C)):
        # the SAME BAE1 dir=4 emit as 0x19 (B2B6 call BAE1); parent behavior 0x89 (& 0xF == 9).
        saved_dir = mem.rw(DS, rec + 0x06)
        mem.ww(DS, rec + 0x06, SCENERY_19_EMIT_DIRECTION)
        _spawn_child_c237(mem, rec, 0x89)
        mem.ww(DS, rec + 0x06, saved_dir)
    _bb03_bounce(mem, rec, tiles)


def _b729_seek(mem, rec: int) -> bool:
    """``1010:B729``: copy the record's own +0x32/+0x34 targets into 2304/2306 and run the 5DB2
    seek with the LIVE ``[2308]`` mode (B729 does NOT set the mode); returns the blocked state
    (the ASM exposes it to the caller as ZF from ``cmp [230A],0``)."""
    return _apply_seek(mem, rec, mem.rw(DS, rec + 0x32), mem.rw(DS, rec + 0x34),
                       mem.rw(DS, 0x2308))


def _step_drift_seeker_2e(mem, rec: int) -> bool:
    """Behavior 0x2E (``1010:87DA``): the target-x cell rides the scroll (``+0x34 += [A278]``),
    sprite = (4D95 canned random & 3) + 0xAD (the RING advances); WAITING while signed x < 0x80
    (that path exits jmp BC45 -- WITH drift); at x == 0x80 EXACTLY the 8802 one-shot (sound 0x0B,
    target_y = ``([2380]+8) & ~1``, target_x = 0x7530), then every frame from x >= 0x80 the B729
    seek toward the record's own targets (live [2308] mode), exiting jmp BC4B -- WITHOUT drift.
    Returns the postmove's ``with_drift``."""
    mem.ww(DS, rec + 0x34, (mem.rw(DS, rec + 0x34) + mem.rw(DS, 0xA278)) & 0xFFFF)
    ring = tuple(mem.rw(DS, 0x20A8 + i * 2) for i in range(16))
    rand, nxt = canned_random_next_4d95(mem.rw(DS, 0x20A6), ring)
    mem.ww(DS, 0x20A6, nxt)
    mem.ww(DS, rec + 0x08, ((rand & 3) + 0x00AD) & 0xFFFF)
    x = mem.rw(DS, rec + 0x02)
    if i16(x) < 0x0080:
        return True
    if x == 0x0080:
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, 0x0B)
        mem.ww(DS, rec + 0x32, (mem.rw(DS, 0x2380) + 8) & 0xFFFE)
        mem.ww(DS, rec + 0x34, 0x7530)
    _b729_seek(mem, rec)
    return False


def _step_beacon_46(mem, rec: int) -> None:
    """Behavior 0x46 (``1010:8C28``): sprite = ``[2338] + 0x4B``, then the shared ``87B5`` tail --
    x > 0x60 (unsigned) drifts right 4px; x <= 0x60 WAITS for ``[2330] == 0x7F``, then dir = 4 and
    ONE C237 child (the child's sprite is left as C237 seeded it)."""
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x2338) + 0x004B) & 0xFFFF)
    x = mem.rw(DS, rec + 0x02)
    if x > 0x0060:
        mem.ww(DS, rec + 0x02, (x + 4) & 0xFFFF)
        return
    if mem.rw(DS, 0x2330) != 0x007F:
        return
    mem.ww(DS, rec + 0x06, 0x0004)
    _spawn_child_c237(mem, rec, 0x46)


def _step_bounce_emitter_47(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x47 (``1010:8C31``) -- NOT 0x46's beacon twin (the old decode misread the jmp
    target; oracle: the L2 walk frame 1389 AFD8 y-step): sprite = ``[2338] + 0x51``, then the
    shared ``B2AC`` scenery-emitter body -- the ``[232C] == 0x1F`` BAE1 dir-4 C237 emit and the
    BB03 bounce (the same tail behavior 0x89 enters with its own sprite)."""
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x2338) + 0x0051) & 0xFFFF)
    if scenery_89_should_emit(mem.rw(DS, 0x232C)):
        saved_dir = mem.rw(DS, rec + 0x06)
        mem.ww(DS, rec + 0x06, SCENERY_19_EMIT_DIRECTION)
        _spawn_child_c237(mem, rec, 0x47)
        mem.ww(DS, rec + 0x06, saved_dir)
    _bb03_bounce(mem, rec, tiles)


def _step_pulser_8f(mem, rec: int) -> None:
    """Behavior 0x8F (``1010:8769``): sprite = ``[96C2 + ([232E]>>3)*2] + 0xBF`` (+3 when
    y <= 0x60 -- the ja skips the add above it); when the clock phase ``[232E]>>3 == 3``,
    ONE C237 child whose sprite is stamped 0x44."""
    phase = (mem.rw(DS, 0x232E) >> 3) & 0xFFFF
    base = (mem.rw(DS, (0x96C2 + ((phase << 1) & 0xFFFF)) & 0xFFFF) + 0x00BF) & 0xFFFF
    sprite = base
    if mem.rw(DS, rec + 0x04) <= 0x0060:
        sprite = (sprite + 3) & 0xFFFF   # 8788 adds to [bp+8] in memory -- bx keeps the base
    mem.ww(DS, rec + 0x08, sprite)
    if phase != 3:
        return
    slot = _spawn_child_c237(mem, rec, 0x8F)
    if slot is None:
        # throttled: `cmp bx,FFFF; mov [bx+8],44h` runs with the STALE bx = the sprite BASE
        # (877B's anim+0xBF -- the 8788 +3 went to memory, not bx), the 8248-shape artifact.
        mem.ww(DS, (base + 8) & 0xFFFF, 0x0044)
    elif slot != 0xFFFF:
        mem.ww(DS, slot + 0x08, 0x0044)


def _step_scenery_8a(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x8A (``1010:8C1F``): sprite = ``[233C] + 0x9D``, then jmp B2AC -- the SAME tail
    as 0x89 (the 232C==0x1F BAE1 dir=4 emit + the shared BB03 bounce)."""
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x233C) + 0x009D) & 0xFFFF)
    if scenery_89_should_emit(mem.rw(DS, 0x232C)):
        saved_dir = mem.rw(DS, rec + 0x06)
        mem.ww(DS, rec + 0x06, SCENERY_19_EMIT_DIRECTION)
        _spawn_child_c237(mem, rec, 0x8A)
        mem.ww(DS, rec + 0x06, saved_dir)
    _bb03_bounce(mem, rec, tiles)


def _ground_follow_move_bbed(mem, rec: int, tiles: LevelTileContext, sign: int) -> bool:
    """1010:BBED: walk the ground crawler one step along the terrain surface. Returns whether it
    MOVED (DS:A430 == 0 on return -- the body gates the animation term on this).

    Sets DS:A430 (blocked flag), stamps the chosen step direction into rec+0x06 (0 when X >= the view
    anchor, 4 when X < it), and -- when the tile ahead is solid -- steps via the recovered AFD8 with
    the real BDD0 contact predicate (persisting its position + the A430/A432.. scratch).  The terrain
    PRE-PROBE: 5073 over (X + A278 - 0x10) -> base tile offset, then +A952 (and -0xD on the X<anchor
    path) selects the tile whose class (505B/C3AA) gates the step -- a class-0 (open) tile means 'no
    ground there', so the crawler is BLOCKED (no AFD8 step)."""
    mem.ww(DS, 0xA430, 0)
    mem.ww(DS, rec + 0x06, GROUND_CRAWLER_RIGHT_DIRECTION)

    x = mem.rw(DS, rec + 0x02)
    y = mem.rw(DS, rec + 0x04)
    probe_x = (x + mem.rw(DS, 0xA278) + GROUND_CRAWLER_PROBE_X_BIAS) & 0xFFFF
    probe = compute_tile_probe_5073(TileProbeInput(
        origin_x_word=mem.rw(DS, 0x234E), row_base_word=mem.rw(DS, 0x2350),
        object_x_word=probe_x, object_y_word=y))
    mem.ww(DS, 0x215A, probe.adjusted_x_word)   # 5073 writes DS:215A = origin_x + probe_x
    if probe.negative_adjusted_x:               # BC0E: bx == FFFF -> blocked, no step
        mem.ww(DS, 0xA430, 1)
        return False

    bx = probe.tile_offset_word
    if x < mem.rw(DS, 0x237E):                   # BC17: X < anchor -> the left (direction 4) path
        mem.ww(DS, rec + 0x06, GROUND_CRAWLER_LEFT_DIRECTION)
        bx = (bx + sign + GROUND_CRAWLER_LEFT_ROW_BIAS) & 0xFFFF
    else:                                        # X >= anchor -> the right (direction 0) path
        bx = (bx + sign) & 0xFFFF

    plane_seg = mem.rw(CODE_SEG, TILE_PLANE_SEG_CELL)
    tile = mem.rb(plane_seg, bx)
    if mem.rb(DS, (TILE_CLASS_TABLE_C3AA + tile) & 0xFFFF) == 0:  # BC20/BC3A: class 0 -> blocked
        mem.ww(DS, 0xA430, 1)
        return False

    direction = mem.rw(DS, rec + 0x06)
    result = contact_probe_afd8(x, y, direction, mem.rw(DS, 0xA278), tiles, _bdd0_contact_at(mem, rec))
    mem.ww(DS, rec + 0x02, result.x_word)
    mem.ww(DS, rec + 0x04, result.y_word)
    mem.ww(DS, 0xA430, 1 if result.blocked else 0)
    mem.ww(DS, 0xA432, result.snap_x)
    mem.ww(DS, 0xA434, result.snap_y)
    mem.ww(DS, 0xA436, result.mirror_y)
    mem.ww(DS, 0xA438, result.mirror_x)
    mem.ww(DS, 0x215A, result.sample_215a)
    return not result.blocked


def _spawn_ground_crawler_shot(mem, rec: int) -> None:
    """1010:BBCA: fire a 7476 shot from the crawler, then override its sprite (0x03) and nudge its X/Y
    by -8 (BBD2/BBD7/BBDB) -- otherwise a standard 7476 enemy-shot (behavior 0x0B) child."""
    slot = _alloc(mem, 0x95DA, GAMEPLAY_POOL_BASE, GAMEPLAY_POOL_WRAP, GAMEPLAY_SLOTS)
    if slot == 0xFFFF:
        return
    stamp = enemy_shot_stamp_7476(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
                                  mem.rw(DS, 0xA8C2) == 1, mem.rw(DS, 0x237E), mem.rw(DS, 0x2380))
    for off, val in stamp.items():
        mem.ww(DS, slot + off, val)
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x1A)
    mem.ww(DS, slot + 0x08, GROUND_CRAWLER_CHILD_SPRITE)
    mem.ww(DS, slot + 0x04, (mem.rw(DS, slot + 0x04) + GROUND_CRAWLER_CHILD_XY_BIAS) & 0xFFFF)
    mem.ww(DS, slot + 0x02, (mem.rw(DS, slot + 0x02) + GROUND_CRAWLER_CHILD_XY_BIAS) & 0xFFFF)


def _step_ground_crawler(mem, rec: int, tiles: LevelTileContext, sign: int) -> None:
    """behaviors 0x8C (sign 0xFFFF) / 0x8B (sign 0x0001): the shared ground-crawler body (1010:BB8E)."""
    mem.ww(DS, 0xA952, sign)
    moved = _ground_follow_move_bbed(mem, rec, tiles, sign)
    mem.ww(DS, rec + 0x08, ground_crawler_sprite_8b_8c(
        sign, mem.rw(DS, 0x233C), moved, mem.rw(DS, rec + 0x06)))
    if ground_crawler_should_spawn(mem.rw(DS, 0x2330)):
        _spawn_ground_crawler_shot(mem, rec)


def _step_burster_49(mem, rec: int) -> None:
    """Behavior 0x49 (``1010:8C3A``): sprite 0x1D, x += 2; on the ``[232A] == 0xF`` clock beat,
    an 8-shot RADIAL BURST -- eight 7476 spawns re-stamped to behavior 4 with directions 7..0
    (a full pool aborts the rest of the burst, the ASM's bx == FFFF early-out)."""
    mem.ww(DS, rec + 0x08, 0x001D)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 2) & 0xFFFF)
    if mem.rw(DS, 0x232A) != 0x000F:
        return
    for cx in range(8, 0, -1):                      # 8C4E: cx = 8 .. 1
        slot = _spawn_enemy_shot_7476(mem, rec)
        if slot == 0xFFFF:
            return
        mem.ww(DS, slot + 0x18, 0x0004)             # 8C5E
        mem.ww(DS, slot + 0x06, cx - 1)             # 8C63/8C64: direction 7..0
    return


def _step_climber_morph_4e(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x4E (``1010:8CF6``): sprite = ``[96D2 + [233C]*2] + 0xCF`` (the 96D2 anim ring),
    then the ``88BB`` tail: nothing until x == 0x90 exactly; there it MORPHS to behavior 0x33,
    aims dir 7 (up-left) and runs up to THREE AFD8 1px contact-steps -- the first BLOCKED step
    flips the direction with ``dir ^= 2`` (7 -> 5, up-right) and stops."""
    anim = mem.rw(DS, (0x96D2 + ((mem.rw(DS, 0x233C) << 1) & 0xFFFF)) & 0xFFFF)
    mem.ww(DS, rec + 0x08, (anim + 0x00CF) & 0xFFFF)
    if mem.rw(DS, rec + 0x02) != 0x0090:
        return
    mem.ww(DS, rec + 0x18, 0x0033)                  # 88C5: the morph
    mem.ww(DS, rec + 0x06, 0x0007)
    for _ in range(3):                              # 88CF/88D4/88D9
        result = contact_probe_afd8(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
                                    mem.rw(DS, rec + 0x06), mem.rw(DS, 0xA278),
                                    tiles, _bdd0_contact_at(mem, rec))
        mem.ww(DS, rec + 0x02, result.x_word)
        mem.ww(DS, rec + 0x04, result.y_word)
        mem.ww(DS, 0xA430, 1 if result.blocked else 0)
        mem.ww(DS, 0xA432, result.snap_x)
        mem.ww(DS, 0xA434, result.snap_y)
        mem.ww(DS, 0xA436, result.mirror_y)
        mem.ww(DS, 0xA438, result.mirror_x)
        mem.ww(DS, 0x215A, result.sample_215a)
        if result.blocked:
            mem.ww(DS, rec + 0x06, mem.rw(DS, rec + 0x06) ^ 2)   # 88E1
            return
    return


def _step_strober_4f(mem, rec: int) -> None:
    """Behavior 0x4F (``1010:8D0A``): sprite = ``(([2328] + rec + [2340]) & 7) + 0x80`` -- the
    record ADDRESS itself salts the strobe phase -- then x += 4."""
    spr = ((mem.rw(DS, 0x2328) + rec + mem.rw(DS, 0x2340)) & 7) + 0x0080
    mem.ww(DS, rec + 0x08, spr)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 4) & 0xFFFF)


def _step_shooter_48(mem, rec: int) -> None:
    """Behavior 0x48 (``1010:8D3C``): the far ``1F8F:01C2`` body -- planet 5: a 1px unsigned
    y-seek toward the player row ``[2380]`` + sprite ``[96D2 + ([2336] & ~1)] + 0x26``; planet 3:
    sprite 0x1C; else sprite ``([2328] >> 1) + 0x22`` -- then x += 1 and a 7476 enemy shot every
    frame."""
    planet = mem.rw(DS, 0x2356)
    if planet == 5:
        y = mem.rw(DS, rec + 0x04)
        py = mem.rw(DS, 0x2380)
        step = 1 if y < py else (0 if y == py else 0xFFFF)
        mem.ww(DS, rec + 0x04, (y + step) & 0xFFFF)
        spr = (mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x2336) & 0xFFFE)) & 0xFFFF) + 0x0026) & 0xFFFF
    elif planet == 3:
        spr = 0x001C
    else:
        spr = ((mem.rw(DS, 0x2328) >> 1) + 0x0022) & 0xFFFF
    mem.ww(DS, rec + 0x08, spr)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 1) & 0xFFFF)
    _spawn_enemy_shot_7476(mem, rec)                # 8D41


def _spawn_enemy_shot_7476(mem, rec: int) -> int:
    """``1010:7476`` from a live record: alloc + the recovered shot stamp + the [98C0] sound.
    Returns the spawned slot, or 0xFFFF when the pool is full (the ASM's bx)."""
    slot = _alloc(mem, 0x95DA, GAMEPLAY_POOL_BASE, GAMEPLAY_POOL_WRAP, GAMEPLAY_SLOTS)
    if slot == 0xFFFF:
        return 0xFFFF
    stamp = enemy_shot_stamp_7476(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
                                  mem.rw(DS, 0xA8C2) == 1, mem.rw(DS, 0x237E), mem.rw(DS, 0x2380))
    for off, val in stamp.items():
        mem.ww(DS, slot + off, val)
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x1A)
    return slot


def _step_controller_13(mem, rec: int) -> None:
    """Behavior 0x13 (the 8D4F far ``1F8F:027A`` body, the 0x13 arrival at 1F8F:0432): seek the
    A482-schedule waypoint (x+0x20/y, 5DB2 mode 3); ON ARRIVAL advance the schedule +4 and 81F4-
    spawn ONE default child (the plain 8209 stamp -- behavior 0x14) at the controller's position,
    then A47E++.  ALL paths end in the 0448 tail: sprite = direction + 0x3B."""
    a482 = mem.rw(DS, 0xA482)
    target_x = (mem.rw(DS, a482) + 0x20) & 0xFFFF
    target_y = mem.rw(DS, (a482 + 2) & 0xFFFF)
    blocked = _apply_seek(mem, rec, target_y, target_x, 3)
    if blocked:                                     # 02A7 -> 0432: the 0x13 arrival
        mem.ww(DS, 0xA482, (a482 + 4) & 0xFFFF)
        slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)  # 81F4
        if slot != 0xFFFF:
            if mem.rb(DS, 0x98C0):
                mem.wb(DS, 0xBEFF, 0x0B)
            for off, val in enemy_spawn_stamp_8209(mem.rw(DS, rec + 0x02),
                                                   mem.rw(DS, rec + 0x04)).items():
                mem.ww(DS, slot + off, val)
            mem.ww(DS, 0xA47E, (mem.rw(DS, 0xA47E) + 1) & 0xFFFF)
    mem.ww(DS, rec + 0x08, (mem.rw(DS, rec + 0x06) + 0x3B) & 0xFFFF)   # 1F8F:0448


def _step_morpher_81(mem, rec: int) -> None:
    """Behavior 0x81 (8D57 -> 1F8F:0452; the child 0x7D spawns): sprite = 0x16A, seek MODE 1 toward the
    record's OWN +0x32/+0x34 target (B729); ON BLOCKED (arrival) morph to behavior 0x93.  jmp BC4B tail.
    Lifter-verified (liftverify 1F8F:0452 ORACLE_PASSING); gated by verify_native_behavior_81."""
    mem.ww(DS, rec + 0x08, 0x016A)                # 0452
    mem.ww(DS, 0x2308, 0x0001)                    # 0457: seek mode 1
    saved_dir = mem.rw(DS, rec + 0x06)            # 045D: push [bp+6]
    blocked = _b729_seek(mem, rec)                 # 0460..0466: B729 seek (writes +0x06)
    mem.ww(DS, rec + 0x06, saved_dir)             # 0468: pop [bp+6] -- restore the direction
    if blocked:                                    # 046B: on blocked ->
        mem.ww(DS, rec + 0x18, 0x93)              # 046D: morph to behavior 0x93


def _step_riser_70(mem, rec: int) -> None:
    """Behavior 0x70 (1010:F5BF; also 0x6F's fall-through tail): sprite = ([232A]>>2) + 0x133, ONE 2px
    8-way step (AF63 = step_operations_for_direction(dir, 2)), then a [2328]==7-gated C237 spawn.
    jmp BC45 tail."""
    mem.ww(DS, rec + 0x08, ((mem.rw(DS, 0x232A) >> 2) + 0x0133) & 0xFFFF)   # F5BF
    x, y = mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04)                   # F5CC: AF63 2px step
    for op in step_operations_for_direction(mem.rw(DS, rec + 0x06) & 0x7, 2):
        delta = i16(op.delta_word)
        if op.axis == "x":
            x = (x + delta) & 0xFFFF
        else:
            y = (y + delta) & 0xFFFF
    mem.ww(DS, rec + 0x02, x)
    mem.ww(DS, rec + 0x04, y)
    if mem.rw(DS, 0x2328) == 0x0007:                                        # F5CF
        _spawn_child_c237(mem, rec, mem.rw(DS, rec + 0x18))


def _step_riser_6f(mem, rec: int) -> None:
    """Behavior 0x6F (1010:F5A3; planet-0 cue spawn): drift while +0x02 < 0x50 OR ([237E]-+0x02) < 0x20;
    otherwise MORPH to behavior 0x70 (+0x18 = 0x70) and fall through into its body (F5BF)."""
    if mem.rw(DS, rec + 0x02) < 0x50:                                       # F5A3
        return
    if ((mem.rw(DS, 0x237E) - mem.rw(DS, rec + 0x02)) & 0xFFFF) < 0x20:     # F5B5
        return
    mem.ww(DS, rec + 0x18, 0x70)                                            # F5BA: morph
    _step_riser_70(mem, rec)                                                # F5BF fall-through


def _step_yseeker_6b6c6d(mem, rec: int, y_target: int, sprite_add: "int | None") -> None:
    """Behaviors 0x6B/0x6C/0x6D (F52A/F554/F53F -> the shared F55A body; planet-0 cue spawns): set the
    shared Y target DS:[D2C2] (0x50/0x60/0x70), 0x6B/0x6D also set sprite = ([232A]>>2) + add; then
    (once +0x02 >= 0x40) seek +0x04 toward [D2C2] by +/-2 and inc +0x02.  ONLY the 0x6C record (+0x18 ==
    0x6C, F57A) spawns a C237 child -- gated on [2326]==3 at Y==0x60, else on [232A]==0xF.  Tail: jmp
    BC45.  (F57A reads +0x18, which lindis prints as 'bp+24' in DECIMAL = offset 0x18, not 0x24.)"""
    mem.ww(DS, 0xD2C2, y_target)                          # F52A/F554/F53F
    if sprite_add is not None:                            # 6B/6D sprite
        mem.ww(DS, rec + 0x08, ((mem.rw(DS, 0x232A) >> 2) + sprite_add) & 0xFFFF)
    if mem.rw(DS, rec + 0x02) < 0x40:                     # F55A: still drifting in
        return
    y = mem.rw(DS, rec + 0x04)                            # F563: seek Y toward [D2C2] +/-2
    if y < y_target:
        mem.ww(DS, rec + 0x04, (y + 2) & 0xFFFF)
    elif y > y_target:
        mem.ww(DS, rec + 0x04, (y - 2) & 0xFFFF)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 1) & 0xFFFF)   # F577
    if mem.rw(DS, rec + 0x18) != 0x6C:                    # F57A: only the 0x6C record spawns
        return
    if mem.rw(DS, rec + 0x04) == 0x60:                    # F583
        if mem.rw(DS, 0x2326) == 3:                       # F596
            _spawn_child_c237(mem, rec, mem.rw(DS, rec + 0x18))
    elif mem.rw(DS, 0x232A) == 0x0F:                      # F589
        _spawn_child_c237(mem, rec, mem.rw(DS, rec + 0x18))


def _step_shooter_88(mem, rec: int) -> None:
    """Behavior 0x88 (1010:F13C; planet-0 cue spawn): once +0x02 >= 0x80, sprite = a word from the
    DS:D212 (dir==6) / DS:D21A table indexed by ([232E]>>4)*2; when that index == 4, spawn a C237
    child.  jmp BC45 tail.  ('bp+24' at F13C's index is DECIMAL -- but here the fields are +0x02/+0x06/
    +0x08, all single-digit, so no decimal/hex ambiguity.)"""
    if mem.rw(DS, rec + 0x02) < 0x80:                     # F13C
        return
    idx = ((mem.rw(DS, 0x232E) >> 4) << 1) & 0xFFFF       # F146..F152
    table = 0xD212 if mem.rw(DS, rec + 0x06) == 6 else 0xD21A   # F154/F15D
    mem.ww(DS, rec + 0x08, mem.rw(DS, (table + idx) & 0xFFFF))  # F162/F164
    if idx == 0x04:                                       # F167
        _spawn_child_c237(mem, rec, mem.rw(DS, rec + 0x18))     # F16F


def _step_crawler_8e(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x8E (1010:BB48; a planet-0 ground-crawler variant): [A952]=1, the BBED terrain-follow
    move, sprite = 0x13A + 3*[A952] + (moved ? [96D2 + [233C]*2] : 0) + (3 if +0x06 != 0), then the
    shared BBB2 tail -- the [2330] in {7F,6B,57}-gated 7476 shot spawn (offset -8,-8, sprite 3)."""
    mem.ww(DS, 0xA952, 0x0001)                            # BB48
    moved = _ground_follow_move_bbed(mem, rec, tiles, 0x0001)   # BBED
    anim = mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x233C) << 1)) & 0xFFFF) if moved else 0
    sprite = (0x013A + 3 * mem.rw(DS, 0xA952) + anim
              + (3 if mem.rw(DS, rec + 0x06) != 0 else 0)) & 0xFFFF   # BB60..BB7E
    mem.ww(DS, rec + 0x08, sprite)                        # BBB2
    if ground_crawler_should_spawn(mem.rw(DS, 0x2330)):   # BBB5
        _spawn_ground_crawler_shot(mem, rec)              # BBCA


def _reflect_0686(mem, rec: int) -> None:
    """1F8F:0686: the blocked-step reaction -- inc the +0x36 death counter, set direction 7 (or 1 when
    the record's Y (+0x04) is <= 0x60)."""
    mem.ww(DS, rec + 0x36, (mem.rw(DS, rec + 0x36) + 1) & 0xFFFF)   # 0686
    mem.ww(DS, rec + 0x06, 7 if mem.rw(DS, rec + 0x04) > 0x60 else 1)   # 068B/0694


def _step_stepper_93(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x93 (8D5F -> 1F8F:0473; the morph target of 0x81): a multi-directional AFD8 stepper
    gated on the A6F0 schedule, with a +0x1C substate, per-direction step sequences, the 0686 blocked
    reaction, a [232A]-clocked sprite + [2340]-clocked BAE1 emit / 7476 shot (path C), and a +0x36
    death counter (the caller kills at >= 0x64).  Faithful transcription of the lifter-verified
    1F8F:0473 (liftverify ORACLE_PASSING); gated by verify_native_behavior_93 over the L4 demo."""
    def rw(o):
        return mem.rw(DS, (rec + o) & 0xFFFF)

    def ww(o, v):
        mem.ww(DS, (rec + o) & 0xFFFF, v)

    def afd8():
        return _afd8_step(mem, rec, tiles)

    def emit_bae1():                                    # 1010:BAE1: dir-4 C237 child spawn
        saved = rw(0x06)
        ww(0x06, 0x04)
        _spawn_child_c237(mem, rec, 0x93)
        ww(0x06, saved)

    bb = 0
    while True:
        if bb == 0:                                    # 0473
            bb = 2 if mem.rw(DS, 0xA482) == 0xA6F0 else 1
        elif bb in (1, 4):                             # 047B / 0489
            bb = 51
        elif bb == 2:                                  # 047E
            bb = 5 if rw(0x1C) == 0 else 3
        elif bb == 3:                                  # 0484: dec the substate
            ww(0x1C, (rw(0x1C) - 1) & 0xFFFF)
            bb = 5 if rw(0x1C) == 0 else 4
        elif bb == 5:                                  # 048C: direction dispatch
            bb = 13 if rw(0x06) == 0 else 6
        elif bb == 6:                                  # 0492
            bb = 13 if rw(0x06) == 1 else 7
        elif bb == 7:                                  # 0498
            bb = 13 if rw(0x06) == 7 else 8
        elif bb == 8:                                  # 049E
            bb = 9 if rw(0x06) == 4 else 25
        elif bb == 9:                                  # 04A4: dir 4 -> 4x AFD8
            afd8(); afd8(); afd8()
            bb = 12 if afd8() else 10
        elif bb == 10:                                 # 04C6
            bb = 12 if rw(0x02) >= 0x00D0 else 11
        elif bb == 11:                                 # 04CD
            bb = 53
        elif bb == 12:                                 # 04D0
            ww(0x06, 0)
            bb = 13
        elif bb == 13:                                 # 04D5: AFD8 + 0686 on blocked
            if afd8():
                _reflect_0686(mem, rec)                # 04DF: block 14
            bb = 15
        elif bb == 15:                                 # 04E2
            if afd8():
                _reflect_0686(mem, rec)                # 04EC: block 16
            bb = 17
        elif bb == 17:                                 # 04EF
            last = afd8()
            if last:
                _reflect_0686(mem, rec)                # 04F9: block 18
            bb = 21 if last else 20                    # 04FC
        elif bb == 20:                                 # 04FE
            ww(0x36, 0)
            ww(0x06, 0)
            bb = 21
        elif bb == 21:                                 # 0508
            bb = 23 if rw(0x02) <= 0x0020 else 22
        elif bb == 22:                                 # 050E
            bb = 53
        elif bb == 23:                                 # 0511
            ww(0x06, 0x06)
            bb = 25 if (rw(0x04) & 0x02) == 0 else 24  # 0516 test [bp+4],2
        elif bb == 24:                                 # 051D
            ww(0x06, 0x02)
            bb = 25
        elif bb == 25:                                 # 0522: sprite + [98A9] gate
            ww(0x08, ((mem.rw(DS, 0x232A) >> 3) + 0x016A) & 0xFFFF)
            bb = 27 if mem.rb(DS, 0x98A9) == 0 else 26
        elif bb == 26:                                 # 0538: push dir, dir 4, 5x AFD8, pop dir
            saved = rw(0x06)
            ww(0x06, 0x04)
            for _ in range(5):
                afd8()
            ww(0x06, saved)
            bb = 27
        elif bb == 27:                                 # 056B: [2340] & 0xFF == 0xFF ?
            bb = 29 if (mem.rw(DS, 0x2340) & 0xFF) != 0xFF else 28
        elif bb == 28:                                 # 0576: BAE1 emit + inc [2340]
            emit_bae1()
            mem.ww(DS, 0x2340, (mem.rw(DS, 0x2340) + 1) & 0xFFFF)
            bb = 29
        elif bb == 29:                                 # 0582
            bb = 31 if mem.rw(DS, 0x2340) == 0 else 30
        elif bb == 30:                                 # 0589
            bb = 32 if mem.rw(DS, 0x2340) != 0x02BD else 31
        elif bb == 31:                                 # 0591: 7476 shot + inc [2340]
            _spawn_enemy_shot_7476(mem, rec)
            mem.ww(DS, 0x2340, (mem.rw(DS, 0x2340) + 1) & 0xFFFF)
            bb = 32
        elif bb == 32:                                 # 059D
            bb = 44 if rw(0x04) == 0 else 33
        elif bb == 33:                                 # 05A3
            bb = 37 if rw(0x04) == 0x00C0 else 34
        elif bb == 34:                                 # 05AA: cmp [bp+6], 6
            bb = 36 if rw(0x06) == 6 else 35
        elif bb == 35:                                 # 05B0
            bb = 45
        elif bb == 36:                                 # 05B3
            bb = 38
        elif bb == 37:                                 # 05B5: dir 4, 5x AFD8
            ww(0x06, 0x04)
            for _ in range(5):
                afd8()
            bb = 38
        elif bb == 38:                                 # 05E2: dir 6, AFD8 chain until blocked
            ww(0x06, 0x06)
            bb = 43 if afd8() else 39
        elif bb == 39:                                 # 05F1
            bb = 43 if afd8() else 40
        elif bb == 40:                                 # 05FB
            bb = 43 if afd8() else 41
        elif bb == 41:                                 # 0605
            bb = 43 if afd8() else 42
        elif bb == 42:                                 # 060F
            bb = 51
        elif bb == 43:                                 # 0611
            ww(0x06, 0x02)
            bb = 51
        elif bb == 44:                                 # 0618: dir 4, 5x AFD8
            ww(0x06, 0x04)
            for _ in range(5):
                afd8()
            bb = 45
        elif bb == 45:                                 # 0645: dir 2, AFD8 chain until blocked
            ww(0x06, 0x02)
            bb = 50 if afd8() else 46
        elif bb == 46:                                 # 0654
            bb = 50 if afd8() else 47
        elif bb == 47:                                 # 065E
            bb = 50 if afd8() else 48
        elif bb == 48:                                 # 0668
            bb = 50 if afd8() else 49
        elif bb == 49:                                 # 0672
            bb = 51
        elif bb == 50:                                 # 0674
            ww(0x06, 0x06)
            bb = 51
        elif bb == 51:                                 # 0679: final X-direction
            if rw(0x02) >= 0x0080:
                ww(0x06, 0x04)                         # 0680: block 52
            return                                     # 0685: retf
        elif bb == 53:                                 # 0685
            return


def _step_controller_1c(mem, rec: int) -> None:
    """Behavior 0x1C (the planet-2 WAVE CONTROLLER; the shared 8D4F/1F8F:027A body + the 03A6
    arrival): seek the A482-schedule waypoint (x+0x20/y, 5DB2 mode 3); ON ARRIVAL advance the
    schedule +8 (its entries are waypoint pair + target pair) and 81F4-spawn ONE child at the
    controller's position -- behavior 0x1D (or 0x1E with sprite 0x43 when the controller's y == 0)
    with the entry's target pair in +0x34/+0x32 and +0x1C = 0x14 -- then A47E++.  ALL paths end in
    the 0448 tail: sprite = direction + 0x3B."""
    a482 = mem.rw(DS, 0xA482)
    target_x = (mem.rw(DS, a482) + 0x20) & 0xFFFF
    target_y = mem.rw(DS, (a482 + 2) & 0xFFFF)
    blocked = _apply_seek(mem, rec, target_y, target_x, 3)
    if blocked:                                     # 02B3 -> 03A6: the 0x1C arrival body
        mem.ww(DS, 0xA482, (a482 + 8) & 0xFFFF)
        slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)  # 81F4 -> 7524
        if slot != 0xFFFF:
            if mem.rb(DS, 0x98C0):
                mem.wb(DS, 0xBEFF, 0x0B)            # 81F4's own sound
            for off, val in enemy_spawn_stamp_8209(mem.rw(DS, rec + 0x02),
                                                   mem.rw(DS, rec + 0x04)).items():
                mem.ww(DS, slot + off, val)
            mem.ww(DS, slot + 0x34, (mem.rw(DS, (a482 + 4) & 0xFFFF) + 0x20) & 0xFFFF)
            mem.ww(DS, slot + 0x32, mem.rw(DS, (a482 + 6) & 0xFFFF))
            if mem.rw(DS, rec + 0x04) == 0:         # 03CB: the y==0 controller variant
                mem.ww(DS, slot + 0x18, 0x001E)
                mem.ww(DS, slot + 0x08, 0x0043)
            else:
                mem.ww(DS, slot + 0x18, 0x001D)
            mem.ww(DS, slot + 0x1C, 0x0014)
            mem.ww(DS, 0xA47E, (mem.rw(DS, 0xA47E) + 1) & 0xFFFF)
    # 1F8F:0448: the shared en-route/arrival sprite tail
    mem.ww(DS, rec + 0x08, (mem.rw(DS, rec + 0x06) + 0x3B) & 0xFFFF)


def _step_waypoint_18(mem, rec: int) -> None:
    """Behavior 0x18 (1010:B98C; the mothership WAVE ENEMY 0x16/0x17 morph into): a retry-loop waypoint
    follower over the +0x36 schedule.  Each pass: a [2340]&0x3FF==0x0C-gated 7476 shot (+ inc [2340]);
    read the next waypoint at +0x36 (FFFF -> reset +0x36 to the word after and loop); else seek toward
    (x+0x20, y) mode 3, sprite = dir + 0x10D; if NOT blocked -> done; else advance +0x36, a 4D95&7==2
    -gated C237 child (dir 4), and LOOP.  Fail-loud retry cap (the ASM loops unbounded)."""
    ring = tuple(mem.rw(DS, (0x20A8 + i * 2) & 0xFFFF) for i in range(16))
    for _ in range(WAYPOINT_FOLLOWER_MAX_RETRIES):
        if (mem.rw(DS, 0x2340) & 0x03FF) == 0x000C:                     # B98C/B995: only on the shot beat
            _spawn_enemy_shot_7476(mem, rec)                            # B997
            mem.ww(DS, 0x2340, (mem.rw(DS, 0x2340) + 1) & 0xFFFF)      # B99A (skipped when no shot)
        si = mem.rw(DS, rec + 0x36)                                     # B99E
        pt0 = mem.rw(DS, si)
        if pt0 == 0xFFFF:                                              # B9A2 -> B9EA: reset the schedule
            mem.ww(DS, rec + 0x36, mem.rw(DS, (si + 2) & 0xFFFF))
            continue
        blocked = _apply_seek(mem, rec, mem.rw(DS, (si + 2) & 0xFFFF),   # B9A7..B9B7 (5DB2 mode 3)
                              (pt0 + 0x20) & 0xFFFF, 3)
        mem.ww(DS, rec + 0x08, (mem.rw(DS, rec + 0x06) + 0x010D) & 0xFFFF)   # B9BA
        if not blocked:                                                # B9C3
            return
        mem.ww(DS, rec + 0x36, (si + 4) & 0xFFFF)                       # B9CD: past the consumed pair
        rand, nxt = canned_random_next_4d95(mem.rw(DS, 0x20A6), ring)   # B9D0
        mem.ww(DS, 0x20A6, nxt)
        if (rand & 0x07) == 0x02:                                      # B9D6
            slot = _spawn_child_c237(mem, rec, mem.rw(DS, rec + 0x18))  # B9DB
            if slot is None:                                           # throttled: bx stays 2 (the RNG
                mem.ww(DS, 0x0008, 0x0004)                             # value) -> B9E3 [bx+6]=[0008]=4
            elif slot != 0xFFFF:
                mem.ww(DS, slot + 0x06, 0x0004)                        # B9E3: the spawned child
            # slot == FFFF (pool full): B9E1 jz B98C -- loop with no write
    raise RecoveryGap(f"behavior 0x18 waypoint retry loop exceeded {WAYPOINT_FOLLOWER_MAX_RETRIES} "
                      f"(record {rec:04X})", "the schedule never yielded an unblocked seek")


def _step_diver_16_17(mem, rec: int) -> None:
    """Behaviors 0x16/0x17 (1010:B930; 0x15's spawned children): seek MODE 2 on planet 0 (else 1) via
    B729 toward the record's own +0x32/+0x34 target; sprite = +0x06 (dir) + 0x10D; on arrival (blocked)
    a +0x1C substate: at 0 -> if [A7A0]==0x31 morph +0x18 to 0x18; else dec +0x1C, and when it reaches 0
    set +0x34 = 0x20 (or 0x40 for the 0x17 variant).  jmp BC4B tail (no drift)."""
    mem.ww(DS, 0x2308, 0x0002 if mem.rw(DS, 0x2356) == 0 else 0x0001)   # B930/B93D
    blocked = _b729_seek(mem, rec)                                       # B729
    mem.ww(DS, rec + 0x08, (mem.rw(DS, rec + 0x06) + 0x010D) & 0xFFFF)   # B947
    if not blocked:                                                     # B951
        return
    if mem.rw(DS, rec + 0x1C) == 0:                                     # B956
        if mem.rw(DS, 0xA7A0) == 0x31:                                  # B97A
            mem.ww(DS, rec + 0x18, 0x18)                                # B984: morph to 0x18
    else:
        mem.ww(DS, rec + 0x1C, (mem.rw(DS, rec + 0x1C) - 1) & 0xFFFF)   # B95C
        if mem.rw(DS, rec + 0x1C) == 0:                                 # B95F
            mem.ww(DS, rec + 0x34, 0x0020)                             # B964
            if mem.rw(DS, rec + 0x18) != 0x16:                         # B969: the 0x17 variant
                mem.ww(DS, rec + 0x34, 0x0040)                        # B972


def _step_controller_15(mem, rec: int) -> None:
    """Behavior 0x15 (the shared 8D4F/1F8F:027A body + the 03E6 arrival; a planet-0 wave controller):
    seek the A482 schedule (x+0x20/y, mode 3); ON ARRIVAL advance the schedule +8 and, unless the next
    entry is FFFF, 81F4-spawn ONE child with the entry's target pair in +0x34/+0x32, behaviour 0x16 &
    +0x36 = A5D4 (or 0x17 & A5C4 when the controller's +0x02 != 0x40), +0x1C = 0x14, +0x20 = 3; A47E++.
    ALL paths end in the 0448 sprite tail."""
    a482 = mem.rw(DS, 0xA482)
    target_x = (mem.rw(DS, a482) + 0x20) & 0xFFFF
    target_y = mem.rw(DS, (a482 + 2) & 0xFFFF)
    blocked = _apply_seek(mem, rec, target_y, target_x, 3)
    if blocked:                                          # 03E6
        mem.ww(DS, 0xA482, (a482 + 8) & 0xFFFF)
        if mem.rw(DS, (a482 + 4) & 0xFFFF) != 0xFFFF:    # 03EB: schedule not FFFF-ended
            slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)  # 81F4
            if slot != 0xFFFF:
                if mem.rb(DS, 0x98C0):
                    mem.wb(DS, 0xBEFF, 0x0B)
                for off, val in enemy_spawn_stamp_8209(mem.rw(DS, rec + 0x02),
                                                       mem.rw(DS, rec + 0x04)).items():
                    mem.ww(DS, slot + off, val)
                mem.ww(DS, slot + 0x34, (mem.rw(DS, (a482 + 4) & 0xFFFF) + 0x20) & 0xFFFF)  # 03FD
                mem.ww(DS, slot + 0x32, mem.rw(DS, (a482 + 6) & 0xFFFF))                    # 0404
                if mem.rw(DS, rec + 0x02) == 0x40:       # 0412
                    mem.ww(DS, slot + 0x18, 0x0016)
                    mem.ww(DS, slot + 0x36, 0xA5D4)
                else:
                    mem.ww(DS, slot + 0x18, 0x0017)
                    mem.ww(DS, slot + 0x36, 0xA5C4)
                mem.ww(DS, slot + 0x1C, 0x0014)          # 0422
                mem.ww(DS, slot + 0x20, 0x0003)          # 0427
                mem.ww(DS, 0xA47E, (mem.rw(DS, 0xA47E) + 1) & 0xFFFF)
    mem.ww(DS, rec + 0x08, (mem.rw(DS, rec + 0x06) + 0x3B) & 0xFFFF)   # 1F8F:0448


def _step_controller_7d(mem, rec: int) -> None:
    """Behavior 0x7D / 0x7E (the shared 8D4F/1F8F:027A body; these ids carry `+0x24` mode 0x7D, so 027A
    takes the ``0309`` arrival branch): seek the A482 schedule (x+0x20/y, 5DB2 mode 3); ON ARRIVAL
    advance the schedule +8 and 81F4-spawn ONE child -- behavior 0x81, +0x1C = 0x19, +0x20 = 5,
    +0x0A = 0, +0x36 = 0, direction (+0x06) = 6 if the target-Y bit 4 is set else 2 -- with the entry's
    target pair in +0x34/+0x32, then A47E++.  ALL paths end in the 0448 tail (sprite = dir + 0x3B).
    Transcription authoritative from the lifter (liftverify 1F8F:027A ORACLE_PASSING via the
    capture_pure_vm_snapshot pipeline); gated by verify_native_behavior_7d over the L4 demo."""
    a482 = mem.rw(DS, 0xA482)
    target_x = (mem.rw(DS, a482) + 0x20) & 0xFFFF
    target_y = mem.rw(DS, (a482 + 2) & 0xFFFF)
    blocked = _apply_seek(mem, rec, target_y, target_x, 3)
    if blocked:                                                # 0309: advance the schedule always
        mem.ww(DS, 0xA482, (a482 + 8) & 0xFFFF)
        child_y = mem.rw(DS, (a482 + 6) & 0xFFFF)
        if mem.rw(DS, (a482 + 4) & 0xFFFF) != 0xFFFF:          # 030E: not FFFF-ended
            slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)  # 81F4
            if slot != 0xFFFF:
                if mem.rb(DS, 0x98C0):
                    mem.wb(DS, 0xBEFF, 0x0B)                    # 81F4's own sound
                for off, val in enemy_spawn_stamp_8209(mem.rw(DS, rec + 0x02),
                                                       mem.rw(DS, rec + 0x04)).items():
                    mem.ww(DS, slot + off, val)
                mem.ww(DS, slot + 0x34, (mem.rw(DS, (a482 + 4) & 0xFFFF) + 0x20) & 0xFFFF)  # 0326
                mem.ww(DS, slot + 0x32, child_y)                              # 032D
                mem.ww(DS, slot + 0x06, 6 if (child_y >> 4) & 1 else 2)       # 0331/0343
                mem.ww(DS, slot + 0x18, 0x81)                                 # 0348: child behaviour
                mem.ww(DS, slot + 0x1C, 0x19)                                 # 034D
                mem.ww(DS, slot + 0x20, 0x05)                                 # 0352
                mem.ww(DS, slot + 0x0A, 0x00)                                 # 0357
                mem.ww(DS, slot + 0x36, 0x00)                                 # 035C
                mem.ww(DS, 0xA47E, (mem.rw(DS, 0xA47E) + 1) & 0xFFFF)         # 0361
    mem.ww(DS, rec + 0x08, (mem.rw(DS, rec + 0x06) + 0x3B) & 0xFFFF)   # 1F8F:0448


def _step_formation_1d(mem, rec: int) -> None:
    """Behavior 0x1D (``1010:B86D``) -- the planet-2 formation enemy, via the ALREADY-RECOVERED
    (BC4B-handoff-verified) ``object_update_b86d``.  Caller-owned extras per the ASM: the A7A0 seek
    block's global writes ([2308]=1 + the record's low-bit-cleared x/y/target cells + B729's
    2304/2306 targets), and the drift path's 7476 formation shots on the DS:2340 schedule ticks
    (0x2EF/0x159/0x79)."""
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))
    x, y = mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04)
    a47e, a7a0 = mem.rw(DS, 0xA47E), mem.rw(DS, 0xA7A0)
    r = object_update_b86d(
        x, y, mem.rw(DS, rec + 0x1C), mem.rw(DS, rec + 0x06), mem.rw(DS, rec + 0x00),
        mem.rw(DS, rec + 0x34), mem.rw(DS, rec + 0x32), mem.rw(DS, rec + 0x2E),
        a47e, a7a0, mem.rw(DS, 0x237E), mem.rw(DS, 0x2380), mem.rw(DS, 0x237C + 0x14),
        mem.rw(DS, 0x2342), mem.rw(DS, 0x2328), mem.rw(DS, 0x2312), table)
    on_edge_path = a47e <= 2 or x > 0x00C0
    if on_edge_path:
        # 5E1B WRITES the record's +0x2C/+0x2A delta cells (5E31/5E3E -- real record state, not
        # scratch); the pure b86d consumes them internally, so persist them here.
        deltas = object_delta_5e1b(x, y, mem.rw(DS, 0x237E), mem.rw(DS, 0x2380),
                                   mem.rw(DS, 0x237C + 0x14))
        mem.ww(DS, rec + 0x2C, deltas.move_delta_y)
        mem.ww(DS, rec + 0x2A, deltas.move_delta_x)
    if not on_edge_path and a7a0 < 0x0028:
        # B885..B89C: the A7A0 seek block's own writes -- [2308]=1, the record's target/x/y cells
        # low-bit-cleared IN PLACE, and B729's 2304/2306 target globals (from the masked target).
        mem.ww(DS, 0x2308, 0x0001)
        ty, tx = mem.rw(DS, rec + 0x32) & 0xFFFE, mem.rw(DS, rec + 0x34) & 0xFFFE
        mem.ww(DS, rec + 0x32, ty)
        mem.ww(DS, rec + 0x34, tx)
        mem.ww(DS, 0x2304, ty)
        mem.ww(DS, 0x2306, tx)
    elif not on_edge_path:
        # the fall-through drift path: the 7476 formation shots on the exact 2340 ticks (B8B0..)
        if mem.rw(DS, 0x2340) in (0x02EF, 0x0159, 0x0079):
            _spawn_enemy_shot_7476(mem, rec)
    mem.ww(DS, rec + 0x1C, r.substate)
    mem.ww(DS, rec + 0x06, r.direction_or_step)
    mem.ww(DS, rec + 0x08, r.sprite_or_state)
    mem.ww(DS, rec + 0x02, r.x_word)
    mem.ww(DS, rec + 0x04, r.y_word)
    mem.ww(DS, rec + 0x2E, r.move_step_error)


def _step_patrol_1e(mem, rec: int) -> None:
    """Behavior 0x1E (``1010:B909``) -- the planet-2 vertical PATROL: seek toward the record's own
    +0x32/+0x34 target (5DB2 mode 2 via the B729 tail); on a BLOCKED seek (arrival) fire a 7476 shot
    and toggle the Y target between 0 and 0xC0."""
    blocked = _apply_seek(mem, rec, mem.rw(DS, rec + 0x32), mem.rw(DS, rec + 0x34), 2)
    if not blocked:
        return
    _spawn_enemy_shot_7476(mem, rec)
    mem.ww(DS, rec + 0x32, 0x0000 if mem.rw(DS, rec + 0x32) != 0 else 0x00C0)


def _step_hover_3a(mem, rec: int) -> None:
    """Behavior 0x3A (``1010:8A55``): sprite = ``[96D2 + [233C]*2] + 0xCC``; while signed
    x >= 0x80, HOME on the player anchor -- 5E1B deltas (PERSISTED to +0x2A/+0x2C, real record
    state) then the 5E42 steer with the CURRENT ``[2312]`` mode (8A72..8A7B leaves 2312 alone)."""
    anim = mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x233C) & 0xFFFF) * 2) & 0xFFFF)
    mem.ww(DS, rec + 0x08, (anim + 0x00CC) & 0xFFFF)
    x = mem.rw(DS, rec + 0x02)
    if i16(x) < 0x0080:
        return
    deltas = object_delta_5e1b(x, mem.rw(DS, rec + 0x04), mem.rw(DS, 0x237E),
                               mem.rw(DS, 0x2380), mem.rw(DS, 0x237C + 0x14))
    mem.ww(DS, rec + 0x2C, deltas.move_delta_y)
    mem.ww(DS, rec + 0x2A, deltas.move_delta_x)
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))
    steer = object_delta_steer_5e42(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x06),
        mem.rw(DS, rec + 0x2C), mem.rw(DS, rec + 0x2A), mem.rw(DS, rec + 0x2E),
        mem.rw(DS, 0x2312), table)
    mem.ww(DS, rec + 0x06, steer.direction_or_step)
    mem.ww(DS, rec + 0x02, steer.x_word)
    mem.ww(DS, rec + 0x04, steer.y_word)
    mem.ww(DS, rec + 0x2E, steer.move_step_error)


def _step_glitter_3b(mem, rec: int) -> None:
    """Behavior 0x3B (``1010:8A7E``): sprite = (4D95 canned random & 3) + a planet-keyed base
    (0x152 on planets 0/6-sentinel, else 0xA9); x += 2.  The random RING advances (20A6)."""
    ring = tuple(mem.rw(DS, 0x20A8 + i * 2) for i in range(16))
    rand, nxt = canned_random_next_4d95(mem.rw(DS, 0x20A6), ring)
    mem.ww(DS, 0x20A6, nxt)
    base = 0x0152 if mem.rw(DS, 0x2356) in (0x0000, 0x0006) else 0x00A9
    mem.ww(DS, rec + 0x08, ((rand & 3) + base) & 0xFFFF)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 2) & 0xFFFF)


#: the AF22 8-way move dispatch (CS:AF2C jump table): direction -> (dx, dy), +/-3px steps.
_AF22_MOVE_BY_DIRECTION = (
    (-3, 0),    # 0 -> AF49
    (-3, +3),   # 1 -> AF4E
    (0, +3),    # 2 -> AF52
    (+3, +3),   # 3 -> AF3C
    (+3, 0),    # 4 -> AF40
    (+3, -3),   # 5 -> AF57
    (0, -3),    # 6 -> AF5B
    (-3, -3),   # 7 -> AF45
)


def _rotating_pool_scan_b15a(mem) -> int:
    """``1010:B15A`` -- the ROTATING victim scan: from the persistent [A43A] cursor over the
    23B4 pool (wrapping at 2B5C), the first active record with behavior not in {1, 0x26, 0x21,
    0x22}, x <= 0xE0 (unsigned) and type 4; the cursor advances PAST the hit (or FFFF after 0x23
    probes)."""
    bx = mem.rw(DS, 0xA43A)
    for _ in range(0x23):
        if bx >= 0x2B5C:
            mem.ww(DS, 0xA43A, 0x23B4)
            bx = 0x23B4
        if (mem.rw(DS, bx) != 0
                and mem.rw(DS, bx + 0x18) not in (0x01, 0x26, 0x21, 0x22)
                and mem.rw(DS, bx + 0x02) <= 0x00E0
                and mem.rw(DS, bx + 0x16) == 4):
            mem.ww(DS, 0xA43A, (bx + 0x38) & 0xFFFF)
            return bx
        bx += 0x38
    return 0xFFFF


def _ad60_tail(mem, rec: int, tiles: LevelTileContext, logic_id: int, *, drift: bool) -> None:
    """The shared AD5A/AD60 exit: optional A278 drift, then the bounds/tile decision with the
    BD17 deactivate on either kill path."""
    if drift:
        mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + mem.rw(DS, 0xA278)) & 0xFFFF)
    x = mem.rw(DS, rec + 0x02)
    y = mem.rw(DS, rec + 0x04)
    decision = object_bounds_tile_decision_ad60(
        x, y, mem.rw(DS, rec + 0x16), logic_id,
        tile_probe_suppressed=mem.rw(DS, 0xBDAC) == 0x0001)
    if decision.kind == "deactivate":
        _bd17_deactivate(mem, rec)
    elif decision.kind == "tile_probe":
        if object_tile_probe_deactivates_ad60(x, y, tiles):
            _bd17_deactivate(mem, rec)


def _steer_5e42_inplace(mem, rec: int) -> None:
    """One 5E42 delta-steer over the record's own +0x2A/+0x2C deltas, written back in place."""
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))
    steer = object_delta_steer_5e42(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x06),
        mem.rw(DS, rec + 0x2C), mem.rw(DS, rec + 0x2A), mem.rw(DS, rec + 0x2E),
        mem.rw(DS, 0x2312), table)
    mem.ww(DS, rec + 0x06, steer.direction_or_step)
    mem.ww(DS, rec + 0x02, steer.x_word)
    mem.ww(DS, rec + 0x04, steer.y_word)
    mem.ww(DS, rec + 0x2E, steer.move_step_error)


def _step_diver_7a(mem, rec: int) -> None:
    """Behavior 0x7A (``1010:870C``): sprite = ``0x20 + [2326]`` (the mod-4 clock animation); set the
    steer mode ``[2312] = 2``, run ONE 5E42 delta-steer over the record's own +0x2A/+0x2C deltas, then
    leave ``[2312] = 3``.  DIES (the BFC7 touch-death) if it has left the play area vertically -- y (as
    SIGNED) > 0xC0 or < 0 -- otherwise it drifts (BC45)."""
    mem.ww(DS, rec + 0x08, (0x0020 + mem.rw(DS, 0x2326)) & 0xFFFF)   # 870C: animated sprite
    mem.ww(DS, 0x2312, 0x0002)                                       # 8744
    _steer_5e42_inplace(mem, rec)                                    # 874A: call 5E42 (mode 2)
    mem.ww(DS, 0x2312, 0x0003)                                       # 874D
    y = mem.rw(DS, rec + 0x04)
    if i16(y) > 0x00C0 or i16(y) < 0:                                # 8753 jg / 875A jl (both SIGNED)
        _bfc7_touch_death(mem, rec)                                  # 8763


def _afd8_step(mem, rec: int, tiles: LevelTileContext) -> bool:
    """ONE AFD8 contact-step in the record's own direction (position + the A430.. scratch written
    back); returns the blocked flag (the ASM's ZF convention: NZ = blocked)."""
    result = contact_probe_afd8(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
                                mem.rw(DS, rec + 0x06), mem.rw(DS, 0xA278),
                                tiles, _bdd0_contact_at(mem, rec))
    mem.ww(DS, rec + 0x02, result.x_word)
    mem.ww(DS, rec + 0x04, result.y_word)
    mem.ww(DS, 0xA430, 1 if result.blocked else 0)
    mem.ww(DS, 0xA432, result.snap_x)
    mem.ww(DS, 0xA434, result.snap_y)
    mem.ww(DS, 0xA436, result.mirror_y)
    mem.ww(DS, 0xA438, result.mirror_x)
    mem.ww(DS, 0x215A, result.sample_215a)
    return result.blocked


def _triple_afd8_or_die_f194(mem, rec: int, tiles: LevelTileContext) -> bool:
    """``1010:F194`` (= behavior 0x56's whole body): up to THREE AFD8 1px contact-steps in the
    record's OWN direction; the first BLOCKED step is the full BFC7 death.  UNLIKE the F2BA/
    F308/F381 ``jmp BFC7`` exits, F1A6 is ``call BFC7`` + ``jmp BC45`` -- the postmove drift
    still applies after this death (oracle: the L3 frame-2091 0x54 record).  Always returns
    False (the caller runs the postmove)."""
    for _ in range(3):
        if _afd8_step(mem, rec, tiles):
            _bfc7_touch_death(mem, rec)                 # F1A6: call BFC7, then jmp BC45
            return False
    return False


def _step_riser_57(mem, rec: int, tiles: LevelTileContext) -> bool:
    """Behaviors 0x57/0x58 (``1010:F201``, one shared entry): nothing until x >= 0x80; at
    x == 0x80 EXACTLY the sprite ticks +1 (F221); then TWO AFD8 steps -- only the SECOND'S
    blocked flag matters (the first's is overwritten): blocked -> the BFC7 death."""
    x = mem.rw(DS, rec + 0x02)
    if x < 0x0080:
        return False
    if x == 0x0080:
        mem.ww(DS, rec + 0x08, (mem.rw(DS, rec + 0x08) + 1) & 0xFFFF)
    _afd8_step(mem, rec, tiles)
    if _afd8_step(mem, rec, tiles):
        _bfc7_touch_death(mem, rec)                     # F21B: jmp BFC7 -- no postmove
        return True
    return False


def _planet_sprite_f225(mem) -> int:
    """The F225/F268 planet-keyed sprite base: 0x148 (planets 0/6), 0x174 (planet 4), 0xE3."""
    planet = mem.rw(DS, 0x2356)
    if planet in (0, 6):
        return 0x0148
    if planet == 4:
        return 0x0174
    return 0x00E3


def _step_glider_5a(mem, rec: int, tiles: LevelTileContext) -> bool:
    """Behavior 0x5A (``1010:F268``): the planet-keyed sprite + [2326]; THREE AFD8 steps; a block
    (or leaving 0 < y < 0xC0, signed) flips dir ^= 6 and takes ONE more step -- blocked again is
    the BFC7 death."""
    mem.ww(DS, rec + 0x08, (_planet_sprite_f225(mem) + mem.rw(DS, 0x2326)) & 0xFFFF)
    flip = False
    for _ in range(3):
        if _afd8_step(mem, rec, tiles):
            flip = True
            break
    if not flip:
        y = _s16(mem.rw(DS, rec + 0x04))
        if 0 < y < 0x00C0:
            return False
    mem.ww(DS, rec + 0x06, mem.rw(DS, rec + 0x06) ^ 6)  # F2B1
    if _afd8_step(mem, rec, tiles):
        _bfc7_touch_death(mem, rec)                     # F2BA: jmp BFC7 -- no postmove
        return True
    return False


def _step_glide_arm_59(mem, rec: int, tiles: LevelTileContext) -> bool:
    """Behavior 0x59 (``1010:F225``): the planet-keyed sprite; x <= 0x80 (signed) waits; past it
    the sprite animates (+[2326]); x > 0xC0 MORPHS to 0x5A and runs its body same-frame."""
    mem.ww(DS, rec + 0x08, _planet_sprite_f225(mem))
    if _s16(mem.rw(DS, rec + 0x02)) <= 0x0080:
        return False
    mem.ww(DS, rec + 0x08, (_planet_sprite_f225(mem) + mem.rw(DS, 0x2326)) & 0xFFFF)
    if _s16(mem.rw(DS, rec + 0x02)) <= 0x00C0:
        return False
    mem.ww(DS, rec + 0x18, 0x005A)                      # F263: the morph
    return _step_glider_5a(mem, rec, tiles)


def _step_turner_5e(mem, rec: int, tiles: LevelTileContext) -> bool:
    """Behavior 0x5E (``1010:F2EB``): FOUR AFD8 steps (only the last's blocked flag matters);
    blocked: dir 4 -> 5, dir 5 -> 6, anything else -> the BFC7 death."""
    for _ in range(3):
        _afd8_step(mem, rec, tiles)
    if not _afd8_step(mem, rec, tiles):
        return False
    d = mem.rw(DS, rec + 0x06)
    if d == 4:
        mem.ww(DS, rec + 0x06, 0x0005)
    elif d == 5:
        mem.ww(DS, rec + 0x06, 0x0006)
    else:
        _bfc7_touch_death(mem, rec)                     # F308: jmp BFC7 -- no postmove
        return True
    return False


def _step_turner_5f(mem, rec: int, tiles: LevelTileContext) -> bool:
    """Behavior 0x5F (``1010:F34D``): sprite = [2326] + 0xF6; waits while x + y < 0x60; then FOUR
    AFD8 steps (only the last's flag); blocked: dir 6 -> 3, dir 2 -> 5, else the BFC7 death."""
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x2326) + 0x00F6) & 0xFFFF)
    if ((mem.rw(DS, rec + 0x02) + mem.rw(DS, rec + 0x04)) & 0xFFFF) < 0x0060:
        return False
    for _ in range(3):
        _afd8_step(mem, rec, tiles)
    if not _afd8_step(mem, rec, tiles):
        return False
    d = mem.rw(DS, rec + 0x06)
    if d == 6:
        mem.ww(DS, rec + 0x06, 0x0003)
    elif d == 2:
        mem.ww(DS, rec + 0x06, 0x0005)
    else:
        _bfc7_touch_death(mem, rec)                     # F381: jmp BFC7 -- no postmove
        return True
    return False





def _step_hatcher_63(mem, rec: int) -> None:
    """Behavior 0x63 (``1010:F4B3``): waits left of x 0x50; then a SPRITE-KEYED hatch machine --
    sprites E7/E8/EA advance +1 on the [2326] == 3 beat; E9 descends 2px/frame to y == 0x60 then
    advances; any other sprite flies right x += 4."""
    if mem.rw(DS, rec + 0x02) < 0x0050:
        return
    spr = mem.rw(DS, rec + 0x08)
    if spr in (0x00E7, 0x00E8, 0x00EA):
        if mem.rw(DS, 0x2326) == 3:
            mem.ww(DS, rec + 0x08, (spr + 1) & 0xFFFF)
        return
    if spr == 0x00E9:
        y = (mem.rw(DS, rec + 0x04) + 2) & 0xFFFF
        mem.ww(DS, rec + 0x04, y)
        if y == 0x0060:
            mem.ww(DS, rec + 0x08, (spr + 1) & 0xFFFF)
        return
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 4) & 0xFFFF)


def _step_snake_head_54(mem, rec: int, tiles: LevelTileContext) -> bool:
    """Behavior 0x54 (``1010:F185``): wait until x == 0xB0 exactly, then MORPH to 0x56 and fall
    straight into the F194 triple-AFD8 body this same frame.  Returns died (skip the postmove)."""
    if mem.rw(DS, rec + 0x02) != 0x00B0:
        return False
    mem.ww(DS, rec + 0x18, 0x0056)
    return _triple_afd8_or_die_f194(mem, rec, tiles)


def _step_waiter_55(mem, rec: int) -> bool:
    """Behavior 0x55 (``1010:F1D7``): waiting (dir != 4): sprite 0x73 until x == 0xB0, then
    dir = 4; flying (dir == 4): sprite = [2328] + 0x77, x += 4.  Returns True on the flying
    path (the BC4B no-drift exit)."""
    if mem.rw(DS, rec + 0x06) != 4:
        mem.ww(DS, rec + 0x08, 0x0073)
        if mem.rw(DS, rec + 0x02) != 0x00B0:
            return False
        mem.ww(DS, rec + 0x06, 0x0004)
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x2328) + 0x0077) & 0xFFFF)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 4) & 0xFFFF)
    return True


def _step_launcher_86(mem, rec: int) -> None:
    """Behavior 0x86 (``1010:F0EE``): sprite from the D202 (dir 6) / D20A (else) anim ring at
    word index ([232E] >> 4) * 2; on the exact ``[232E] == 0x26`` beat (index 2), an 81F4 spawn
    at a stamp position, aimed at the player via the 74E2 deltas, sprite 0xCB, behavior 0x60
    (the 8744 delta steer)."""
    idx = ((mem.rw(DS, 0x232E) >> 4) << 1) & 0xFFFF
    si = 0xD202 if mem.rw(DS, rec + 0x06) == 6 else 0xD20A
    mem.ww(DS, rec + 0x08, mem.rw(DS, (si + idx) & 0xFFFF))
    if idx != 4 or mem.rw(DS, 0x232E) != 0x0026:
        return
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)    # 81F4
    if slot == 0xFFFF:
        return
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x0B)                        # 81F4's own sound
    for off, val in enemy_spawn_stamp_8209(mem.rw(DS, rec + 0x02),
                                           mem.rw(DS, rec + 0x04)).items():
        mem.ww(DS, slot + off, val)
    dx, dy = retarget_delta_toward_anchor_74e2(
        mem.rw(DS, slot + 0x02), mem.rw(DS, slot + 0x04),
        mem.rw(DS, 0x237E), mem.rw(DS, 0x2380))
    mem.ww(DS, slot + 0x2A, dx)
    mem.ww(DS, slot + 0x2C, dy)
    mem.ww(DS, slot + 0x08, 0x00CB)                     # F12F
    mem.ww(DS, slot + 0x18, 0x0060)                     # F134: the 8744 steer child


def _step_pulser_87(mem, rec: int) -> None:
    """Behavior 0x87 (``1010:F1AC``): sprite = ``[96C2 + ([232E]>>3)*2] + 0xDD`` (+3 when
    y >= 0x60), then the shared ``878C`` emit: clock phase ([232E]>>3) == 3 -> ONE C237 child
    with sprite 0x44 (the pulser-8F tail; the throttled stale-bx artifact writes sprite-base+8)."""
    phase = (mem.rw(DS, 0x232E) >> 3) & 0xFFFF
    base = (mem.rw(DS, (0x96C2 + ((phase << 1) & 0xFFFF)) & 0xFFFF) + 0x00DD) & 0xFFFF
    sprite = base
    if mem.rw(DS, rec + 0x04) >= 0x0060:
        sprite = (sprite + 3) & 0xFFFF                  # F1D0 adds in memory -- bx keeps the base
    mem.ww(DS, rec + 0x08, sprite)
    if phase != 3:
        return
    slot = _spawn_child_c237(mem, rec, 0x87)
    if slot is None:
        # throttled: `cmp bx,FFFF; mov [bx+8],44h` runs with the STALE bx = the sprite BASE
        mem.ww(DS, (base + 8) & 0xFFFF, 0x0044)
    elif slot != 0xFFFF:
        mem.ww(DS, slot + 0x08, 0x0044)


def _step_formation_14(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x14 (``1010:B9F0``) -- the FORMATION FLYER, fully inline (the pure
    ``object_update_b9f0`` omits the caller-owned globals: the [2340]==0x2EF 7476 beat + tick
    incs, the +0x32/+0x34 in-place target drift, the 5E1B +0x2A/+0x2C persist, and the seek
    path's 2304/2306/2308 writes).

    [A482] != A4E4 -> just the [233C]+0x1C sprite refresh.  Else: the 2EF spawn beat; targets
    drift by [2342]/[2346] (target x wraps 0xD0 -> 0x20); REACHED (y+[2342]==ty and x==tx) ->
    the BA5A player-homing helper (5E1B persist + 5E42 + x += 2) -- throttled by the
    [2340]&mask==mask tick gate when [A47E] >= 6 (mask 0x7F on difficulty 2, else 0xFF; a match
    also incs [2340]) -- then the sprite refresh; NOT reached: x <= tx -> the BA73 seek (2px-
    aligned targets to 2304/2306, own x/y aligned in place, mode 1, 5DB2); x > tx -> one 5E42
    overshoot step + the [A47E]<6 [232E]==0x3F 7476 beat + the x>0xD0 -> 0x10 wrap."""
    if mem.rw(DS, 0xA482) != 0xA4E4:
        mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x233C) + 0x001C) & 0xFFFF)
        return
    if mem.rw(DS, 0x2340) == 0x02EF:
        _spawn_enemy_shot_7476(mem, rec)
        mem.ww(DS, 0x2340, (mem.rw(DS, 0x2340) + 1) & 0xFFFF)
    ty = (mem.rw(DS, rec + 0x32) + mem.rw(DS, 0x2342)) & 0xFFFF
    tx = (mem.rw(DS, rec + 0x34) + mem.rw(DS, 0x2346)) & 0xFFFF
    if tx > 0x00D0:
        tx = 0x0020
    mem.ww(DS, rec + 0x32, ty)
    mem.ww(DS, rec + 0x34, tx)
    x = mem.rw(DS, rec + 0x02)
    y = mem.rw(DS, rec + 0x04)
    if ((y + mem.rw(DS, 0x2342)) & 0xFFFF) == ty and x == tx:
        run_helper = True
        if mem.rw(DS, 0xA47E) >= 6:                     # BA33: the throttle gate
            mask = 0x7F if mem.rw(DS, 0xBEDC) == 2 else 0xFF
            if (mem.rw(DS, 0x2340) & mask) == mask:
                mem.ww(DS, 0x2340, (mem.rw(DS, 0x2340) + 1) & 0xFFFF)
            else:
                run_helper = False
        if run_helper:                                  # BA5A: the player-homing helper
            deltas = object_delta_5e1b(x, y, mem.rw(DS, 0x237E), mem.rw(DS, 0x2380),
                                       mem.rw(DS, 0x237C + 0x14))
            mem.ww(DS, rec + 0x2C, deltas.move_delta_y)
            mem.ww(DS, rec + 0x2A, deltas.move_delta_x)
            _steer_5e42_inplace(mem, rec)
            mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 2) & 0xFFFF)
        mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x233C) + 0x001C) & 0xFFFF)   # BA67
        return
    if x <= tx:                                         # BA73: the aligned seek (no sprite)
        mem.ww(DS, rec + 0x04, y & 0xFFFE)
        mem.ww(DS, rec + 0x02, x & 0xFFFE)
        _apply_seek(mem, rec, ty & 0xFFFE, tx & 0xFFFE, 1)
        return
    _steer_5e42_inplace(mem, rec)                       # BAA1: the overshoot step (no sprite)
    if mem.rw(DS, 0xA47E) < 6 and mem.rw(DS, 0x232E) == 0x003F:
        _spawn_enemy_shot_7476(mem, rec)                # BAB2
    if mem.rw(DS, rec + 0x02) > 0x00D0:
        mem.ww(DS, rec + 0x02, 0x0010)                  # BABF: the right-edge wrap
    return


def _step_tractor_0a(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x0A (``1010:B1B0``) -- the TRACTOR: sprite = [2328] + 0x6D.  Phase 0 (+0x1C != 1):
    a 4px-aligned 5DB2 mode-2 seek toward (player x + 0xA, player y + 0xC); while moving, the AD60
    tail; on arrival ([230A] blocked), dec [A97E], the B15A rotating scan LINKS a victim into
    +0x30 (FFFF -> the ADC9 death), +0x1C = 1, sound 0x11, [A97E]++.  Phase 1: victim inactive /
    x > 0xDC / dying -> unlatch (+0x1C = 0); else the 5E1B victim deltas (persisted to +0x2A/+0x2C)
    + the 5E42 steer; phase-1 exits take the AD5A drift."""
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x2328) + 0x006D) & 0xFFFF)
    if mem.rw(DS, rec + 0x1C) != 1:
        tx = (mem.rw(DS, 0x237E) + 0x000A) & 0xFFFC     # B1BF..B1DC: masked targets
        ty = (mem.rw(DS, 0x2380) + 0x000C) & 0xFFFC
        mem.ww(DS, rec + 0x04, mem.rw(DS, rec + 0x04) & 0xFFFC)
        mem.ww(DS, rec + 0x02, mem.rw(DS, rec + 0x02) & 0xFFFC)
        blocked = _apply_seek(mem, rec, ty, tx, 2)
        if not blocked:
            _ad60_tail(mem, rec, tiles, 0x000A, drift=False)
            return
        if mem.rw(DS, 0xA97E):
            mem.ww(DS, 0xA97E, mem.rw(DS, 0xA97E) - 1)
        victim = _rotating_pool_scan_b15a(mem)
        if victim == 0xFFFF:
            mem.ww(DS, rec + 0x02, 0xFFFF)              # B209 -> ADC9
            _bd17_deactivate(mem, rec)
            return
        mem.ww(DS, rec + 0x30, victim)
        mem.ww(DS, rec + 0x1C, 0x0001)
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, 0x11)
        mem.ww(DS, 0xA97E, (mem.rw(DS, 0xA97E) + 1) & 0xFFFF)
        _ad60_tail(mem, rec, tiles, 0x000A, drift=False)
        return
    victim = mem.rw(DS, rec + 0x30)
    if (mem.rw(DS, victim) == 0 or mem.rw(DS, victim + 0x02) > 0x00DC
            or mem.rw(DS, victim + 0x18) == 1):
        mem.ww(DS, rec + 0x1C, 0x0000)                  # B245: unlatch
        _ad60_tail(mem, rec, tiles, 0x000A, drift=True)
        return
    deltas = object_delta_5e1b(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
                               mem.rw(DS, victim + 0x02), mem.rw(DS, victim + 0x04),
                               mem.rw(DS, victim + 0x14))
    mem.ww(DS, rec + 0x2C, deltas.move_delta_y)
    mem.ww(DS, rec + 0x2A, deltas.move_delta_x)
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))
    steer = object_delta_steer_5e42(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x06),
        mem.rw(DS, rec + 0x2C), mem.rw(DS, rec + 0x2A), mem.rw(DS, rec + 0x2E),
        mem.rw(DS, 0x2312), table)
    mem.ww(DS, rec + 0x06, steer.direction_or_step)
    mem.ww(DS, rec + 0x02, steer.x_word)
    mem.ww(DS, rec + 0x04, steer.y_word)
    mem.ww(DS, rec + 0x2E, steer.move_step_error)
    _ad60_tail(mem, rec, tiles, 0x000A, drift=True)


def _step_marcher_0c(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x0C (``1010:AE09``, EFAE logic_id 0xC) -- the 8-way MARCHER: while the +0x1C
    countdown runs it only ticks (the tick reaching 0 re-aims dir = 0 and resumes); at 0 the body
    drifts x -= 2 every frame.  sprite = dir + 0x28, then the AF22 8-way +/-3px move over the
    CS:AF2C table and the shared AD60 bounds/tile tail (NO A278 drift -- AE29 jumps to AD60, not
    AD5A)."""
    sub = mem.rw(DS, rec + 0x1C)
    step_x2 = sub == 0
    if sub != 0:
        sub = (sub - 1) & 0xFFFF
        mem.ww(DS, rec + 0x1C, sub)
        if sub == 0:                    # AE14: the countdown expiring re-aims left...
            mem.ww(DS, rec + 0x06, 0)
            step_x2 = True              # ...and falls into the AE19 x -= 2
    if step_x2:
        mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) - 2) & 0xFFFF)
    direction = mem.rw(DS, rec + 0x06)
    mem.ww(DS, rec + 0x08, (direction + 0x0028) & 0xFFFF)
    if direction > 7:
        raise RecoveryGap(f"behavior 0x0C direction {direction:#x} (record {rec:04X})",
                          "AF22's jump table has 8 entries; an out-of-range direction would "
                          "jump through arbitrary code")
    dx, dy = _AF22_MOVE_BY_DIRECTION[direction]
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + dx) & 0xFFFF)
    mem.ww(DS, rec + 0x04, (mem.rw(DS, rec + 0x04) + dy) & 0xFFFF)
    # the AD60 tail (no drift)
    x = mem.rw(DS, rec + 0x02)
    y = mem.rw(DS, rec + 0x04)
    decision = object_bounds_tile_decision_ad60(
        x, y, mem.rw(DS, rec + 0x16), 0x000C,
        tile_probe_suppressed=mem.rw(DS, 0xBDAC) == 0x0001)
    if decision.kind == "deactivate":
        _bd17_deactivate(mem, rec)
    elif decision.kind == "tile_probe":
        if object_tile_probe_deactivates_ad60(x, y, tiles):
            _bd17_deactivate(mem, rec)


def _step_mover_06(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x06 (``1010:AE2C``, EFAE logic_id 6) -- the recovered whole-slot scroll-left mover
    with the tile-gated down-step (``object_update_ae2c``, produced-vs-VM verified)."""
    u = object_update_ae2c(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x00),
        mem.rw(DS, rec + 0x16), mem.rw(DS, 0xA278), mem.rw(DS, 0x2326), False, tiles)
    if u is None:
        mem.ww(DS, rec + 0x02, 0xFFFF)   # ADC9 -> AD60's x < 8 bound -> BD17
        _bd17_deactivate(mem, rec)       # the 0x06 decay (A976) is composed in BD17 now
        return
    mem.ww(DS, rec + 0x06, u.direction_or_step)
    mem.ww(DS, rec + 0x08, u.sprite_or_state)
    mem.ww(DS, rec + 0x02, u.x_word)
    mem.ww(DS, rec + 0x04, u.y_word)
    if u.active_word == 0:
        _bd17_deactivate(mem, rec)   # BD17: clear active + the hazard_class-keyed death side effects


def _step_bouncer_33(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x33 (``1010:88CF``): THREE chained AFD8 contact-steps in the record's direction
    (each with the wired BDD0 predicate); the FIRST blocked step stops the chain and flips the
    vertical phase (``direction ^= 2``)."""
    for _ in range(3):
        result = contact_probe_afd8(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
                                    mem.rw(DS, rec + 0x06), mem.rw(DS, 0xA278),
                                    tiles, _bdd0_contact_at(mem, rec))
        mem.ww(DS, rec + 0x02, result.x_word)
        mem.ww(DS, rec + 0x04, result.y_word)
        mem.ww(DS, 0xA430, 1 if result.blocked else 0)
        mem.ww(DS, 0xA432, result.snap_x)
        mem.ww(DS, 0xA434, result.snap_y)
        mem.ww(DS, 0xA436, result.mirror_y)
        mem.ww(DS, 0xA438, result.mirror_x)
        mem.ww(DS, 0x215A, result.sample_215a)
        if result.blocked:
            mem.ww(DS, rec + 0x06, mem.rw(DS, rec + 0x06) ^ 0x0002)   # 88E1: flip the vertical phase
            return


def _step_bouncer_32(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x32 (``1010:88B6``): sprite 0x24, DRIFTING (jmp BC45) until ``x == 0x90`` EXACTLY;
    there it latches ``+0x24 = 0x33`` and ``dir = 7`` and runs the ``88CF`` triple-AFD8 bounce body
    (the same one 0x33 uses).  All paths exit through the BC45 postmove."""
    mem.ww(DS, rec + 0x08, 0x0024)                     # 88B6
    if mem.rw(DS, rec + 0x02) != 0x0090:               # 88BB: not at x == 0x90 yet -> just drift
        return
    mem.ww(DS, rec + 0x24, 0x0033)                     # 88C5
    mem.ww(DS, rec + 0x06, 0x0007)                     # 88CA: dir = 7
    _step_bouncer_33(mem, rec, tiles)                  # 88CF: the triple-AFD8 bounce


def _step_bounce_sprite_3d(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x3D (``1010:8AC7``): sprite = ``[96D2 + [233C]*2] + 0xC5``, then jmp 88CF --
    the SAME triple-AFD8 bounce body 0x33 uses."""
    anim = mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x233C) & 0xFFFF) * 2) & 0xFFFF)
    mem.ww(DS, rec + 0x08, (anim + 0x00C5) & 0xFFFF)
    _step_bouncer_33(mem, rec, tiles)


def _step_lurker_3c(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x3C (``1010:8AA4``): sprite 0xC5 WAITING for x == 0xB0 exactly; there -- sound
    0x1D (98C0-gated BEFF write), MORPH ``+0x18 += 1`` (-> 0x3D), dir = 7, and falls straight into
    the 0x3D body the SAME frame (8AC2 -> 8AC7)."""
    mem.ww(DS, rec + 0x08, 0x00C5)
    if mem.rw(DS, rec + 0x02) != 0x00B0:
        return
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x1D)
    mem.ww(DS, rec + 0x18, (mem.rw(DS, rec + 0x18) + 1) & 0xFFFF)
    mem.ww(DS, rec + 0x06, 0x0007)
    _step_bounce_sprite_3d(mem, rec, tiles)


def _step_riser_35(mem, rec: int) -> None:
    """Behaviors 0x35/0x22 (``1010:B3DF``): sprite = ((DS:2342 + 1) >> 1) + 0x71 (the B3BF worker),
    x += 1 (again on planet 0); at x >= 0xA0 the record dies (the full BFC7 beat) and BURSTS eight
    radial behavior-3 children (the B402 spawner: directions 7..0, sprites 0x0F..0x08, spawned at
    (x+d, y+d) with d = 0xC when +0x14 == 2 else 4 -- behavior 3 is the recovered AED8 alias)."""
    # B3BF: inc ax is 16-BIT -- [2342]==0xFFFF wraps to 0 BEFORE the shift (caught at L2 frame 4024)
    mem.ww(DS, rec + 0x08, ((((mem.rw(DS, 0x2342) + 1) & 0xFFFF) >> 1) + 0x0071) & 0xFFFF)
    x = (mem.rw(DS, rec + 0x02) + 1) & 0xFFFF
    if mem.rw(DS, 0x2356) == 0:
        x = (x + 1) & 0xFFFF
    mem.ww(DS, rec + 0x02, x)
    if x < 0x00A0:
        return
    _riser_death_burst_b3f9(mem, rec)


def _riser_death_burst_b3f9(mem, rec: int) -> None:
    """B3F9: the shared riser TERMINAL beat -- the full BFC7 touch-death, then the B402 8-way radial
    burst of behavior-3 children (directions 7..0, sprites 0x0F..0x08, spawned at (x+d, y+d) with
    d = 0xC when +0x14 == 2 else 4).  Shared by 0x35/0x22 (B3DF) and 0x36 (B3CC)."""
    _bfc7_touch_death(mem, rec)
    # B402: the 8-way radial burst
    d = 0x000C if mem.rw(DS, rec + 0x14) == 2 else 0x0004
    burst_y = (mem.rw(DS, rec + 0x04) + d) & 0xFFFF
    burst_x = (mem.rw(DS, rec + 0x02) + d) & 0xFFFF
    mem.ww(DS, 0xA8B2, burst_y)
    mem.ww(DS, 0xA8B4, burst_x)
    for cx in range(8, 0, -1):
        slot = _alloc(mem, 0x95DA, GAMEPLAY_POOL_BASE, GAMEPLAY_POOL_WRAP, GAMEPLAY_SLOTS)
        if slot == 0xFFFF:
            return
        mem.ww(DS, slot + 0x06, cx - 1)
        mem.ww(DS, slot + 0x08, (cx - 1 + 8) & 0xFFFF)
        mem.ww(DS, slot + 0x04, burst_y)
        mem.ww(DS, slot + 0x02, burst_x)
        mem.ww(DS, slot + 0x00, 1)
        mem.ww(DS, slot + 0x1E, 0)
        mem.ww(DS, slot + 0x0A, 1)
        mem.ww(DS, slot + 0x14, 0)
        mem.ww(DS, slot + 0x16, 2)
        mem.ww(DS, slot + 0x18, 3)
        mem.ww(DS, slot + 0x1C, 0xFFFF)


def _step_riser_36(mem, rec: int) -> None:
    """Behavior 0x36 (``1010:B3CC``): sprite = the B3BF worker, then x += 2 (a FIXED step -- no
    planet-0 extra, unlike 0x35); at x >= 0xA0 the SAME B3F9 death + 8-way radial burst as 0x35."""
    mem.ww(DS, rec + 0x08, ((((mem.rw(DS, 0x2342) + 1) & 0xFFFF) >> 1) + 0x0071) & 0xFFFF)  # B3CC->B3BF
    x = (mem.rw(DS, rec + 0x02) + 2) & 0xFFFF                                                # B3CF
    mem.ww(DS, rec + 0x02, x)
    if x < 0x00A0:                                                                           # B3D3
        return
    _riser_death_burst_b3f9(mem, rec)                                                        # B3DD->B3F9


def _step_patroller_37(mem, rec: int) -> None:
    """Behavior 0x37 (``1010:8982``): a horizontal patroller.  Sprite = [233C] + 0xB5.  Speed ([96EA])
    ramps by row: 1 at y == 0x60, 3 at y == 0x50 / 0x70, else 5.  dir 4 moves right (x += speed; at
    x >= 0x90 a C237 child spawns THEN dir flips to 0); any other dir moves left (dir flips to 4 FIRST,
    THEN x <= 8 spawns a C237 child).  Both bounce compares are UNSIGNED word compares, and the child
    seed reads +0x06 -- so the set/spawn order matters (both paths seed the child with dir 4)."""
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x233C) + 0x00B5) & 0xFFFF)      # 8982: sprite
    y = mem.rw(DS, rec + 0x04)
    speed = 1 if y == 0x0060 else (3 if y in (0x0050, 0x0070) else 5)   # 898B/8997/89A9 -> [96EA]
    mem.ww(DS, 0x96EA, speed)
    if mem.rw(DS, rec + 0x06) == 0x0004:                                # 89B2: dir 4 -> moving right
        x = (mem.rw(DS, rec + 0x02) + speed) & 0xFFFF                   # 89D1
        mem.ww(DS, rec + 0x02, x)
        if x < 0x0090:                                                  # 89D4 (jnb -> bounce)
            return
        _spawn_child_c237(mem, rec, 0x37)                              # 89DE: spawn (child sees dir 4)
        mem.ww(DS, rec + 0x06, 0x0000)                                 # 89E1: then dir -> 0
    else:                                                              # moving left
        x = (mem.rw(DS, rec + 0x02) - speed) & 0xFFFF                  # 89B8/89BA: neg + add
        mem.ww(DS, rec + 0x02, x)
        if x > 0x0008:                                                 # 89BD (jbe -> bounce)
            return
        mem.ww(DS, rec + 0x06, 0x0004)                                # 89C6: dir -> 4 FIRST
        _spawn_child_c237(mem, rec, 0x37)                             # 89CB: then spawn (child sees dir 4)


def _step_edge_runner_38(mem, rec: int) -> None:
    """Behavior 0x38 (``1010:89FF``): direction snaps to 3 at y == 0 / 5 at y == 0xC0 (else keeps),
    sprite = 0x6E, then ONE 2px 8-way step (the AF63 single-step -- half of the recovered AF60
    double-step, same direction table)."""
    y = mem.rw(DS, rec + 0x04)
    if y == 0:
        mem.ww(DS, rec + 0x06, 0x0003)
    elif y == 0x00C0:
        mem.ww(DS, rec + 0x06, 0x0005)
    mem.ww(DS, rec + 0x08, 0x006E)
    x, yv = mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04)
    for op in step_operations_for_direction(mem.rw(DS, rec + 0x06) & 0x7, 2):
        delta = i16(op.delta_word)
        if op.axis == "x":
            x = (x + delta) & 0xFFFF
        else:
            yv = (yv + delta) & 0xFFFF
    mem.ww(DS, rec + 0x02, x)
    mem.ww(DS, rec + 0x04, yv)


def _step_faller_39(mem, rec: int) -> None:
    """Behavior 0x39 (``1010:8A23``): sprite 0x6E WAITING for signed x >= 0x80; there -- at
    x == 0x80 EXACTLY a one-shot sound 0x0B (98C0-gated BEFF), dir = 2, the AF60 DOUBLE 2px step
    (twice the 0x38 single-step, same direction table), then the y > 0xC0 (unsigned) BFC7 kill."""
    mem.ww(DS, rec + 0x08, 0x006E)
    x = mem.rw(DS, rec + 0x02)
    if i16(x) < 0x0080:
        return
    if x == 0x0080 and mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x0B)
    mem.ww(DS, rec + 0x06, 0x0002)
    xv, yv = mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04)
    for _ in range(2):
        for op in step_operations_for_direction(0x2, 2):
            delta = i16(op.delta_word)
            if op.axis == "x":
                xv = (xv + delta) & 0xFFFF
            else:
                yv = (yv + delta) & 0xFFFF
    mem.ww(DS, rec + 0x02, xv)
    mem.ww(DS, rec + 0x04, yv)
    if yv > 0x00C0:
        _bfc7_touch_death(mem, rec)


def _step_scroller_27(mem, rec: int) -> None:
    r = step_sprite_scroller_27_835d(
        clock_2338=mem.rw(DS, 0x2338), planet_2356=mem.rw(DS, 0x2356),
        x_word=mem.rw(DS, rec + 0x02))
    for off, val in r.record_writes.items():
        mem.ww(DS, rec + off, val)


def _spawn_child_c237(mem, rec: int, parent_beh: int) -> "int | None":
    """1010:C237: the difficulty-throttled child spawn. Returns the child slot offset (spawned),
    0xFFFF (pool full), or None (throttled -- no allocation)."""
    bedc = mem.rw(DS, 0xBEDC)
    # DS:A956 is a BYTE counter (`inc`/`and` at C245/C253 are the FE 06 / 80 26 byte-width opcodes) --
    # a word rw/ww here would clobber the adjacent DS:A957 byte (a real bug the demo shadow caught).
    allow, a956 = child_spawn_throttle_c237(bedc, mem.rb(DS, 0xA956))
    if bedc != 0x0002:
        mem.wb(DS, 0xA956, a956)          # A956 is ticked on the BEDC 0/1 paths, spawn or not
    if not allow:
        return None
    slot = _alloc(mem, 0x95DA, GAMEPLAY_POOL_BASE, GAMEPLAY_POOL_WRAP, GAMEPLAY_SLOTS)
    if slot == 0xFFFF:
        return 0xFFFF
    for off, val in child_spawn_seed_c237(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
                                          mem.rw(DS, rec + 0x06)).items():
        mem.ww(DS, slot + off, val)
    sound = child_spawn_sound_c237(parent_beh, mem.rw(DS, slot + 0x02), mem.rw(DS, rec + 0x02))
    if sound is not None and mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, sound)
    return slot


def _step_spawn_child_sprite(mem, rec: int, parent_beh: int, sprite: int) -> None:
    # the 8248/8265 shape (behaviors 0x24/0x25 -- byte-identical apart from the sprite constant):
    # only spawn when the 232C clock hits 0x1F; then C237, and stamp the child's sprite.
    if mem.rw(DS, 0x232C) != 0x001F:
        return
    result = _spawn_child_c237(mem, rec, parent_beh)
    if result is None:
        # throttled: `cmp bx,FFFF; mov [bx+8],sprite` runs with the STALE dispatch bx = parent_beh<<1,
        # so it writes DS:[(parent_beh<<1)+8] -- an artifact (oracle-traced for 0x25: bx=0x4A -> 0x52).
        mem.ww(DS, ((parent_beh << 1) + 8) & 0xFFFF, sprite)
    elif result != 0xFFFF:
        mem.ww(DS, result + 0x08, sprite)


_ANIM_SPAWNER_BASES = {0x90: (0x0088, 0x016C), 0x91: (0x008B, 0x016F)}


def _step_anim_spawner_90_91(mem, rec: int, beh: int) -> None:
    anim = mem.rw(DS, (0x95EA + ((mem.rw(DS, 0x2330) >> 5) & 0xFFFF) * 2) & 0xFFFF)
    base_normal, base_planet4 = _ANIM_SPAWNER_BASES[beh]
    r = step_animated_spawner_90_91(
        base_normal=base_normal, base_planet4=base_planet4,
        planet_2356=mem.rw(DS, 0x2356), anim_table_value=anim, gate_232c=mem.rw(DS, 0x232C))
    mem.ww(DS, rec + 0x08, r.sprite)
    if r.spawn_x_delta is not None:
        # 82D0/82DE: offset X, spawn a C237 child at the offset, restore X
        mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + r.spawn_x_delta) & 0xFFFF)
        _spawn_child_c237(mem, rec, beh)
        mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) - r.spawn_x_delta) & 0xFFFF)


def _step_waypoint_12(mem, rec: int) -> None:
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))

    def waypoint_at(ptr: int) -> "tuple[int, int]":
        return mem.rw(DS, ptr & 0xFFFF), mem.rw(DS, (ptr + 2) & 0xFFFF)

    r = step_waypoint_follower_11_12(
        x_word=mem.rw(DS, rec + 0x02), y_word=mem.rw(DS, rec + 0x04),
        direction=mem.rw(DS, rec + 0x06), waypoint_ptr=mem.rw(DS, rec + 0x36),
        waypoint_at=waypoint_at, bdac=mem.rw(DS, 0xBDAC), planet_2356=mem.rw(DS, 0x2356),
        boss_2350=mem.rw(DS, 0x2350), direction_table=table)
    mem.ww(DS, rec + 0x02, r.x_word)
    mem.ww(DS, rec + 0x04, r.y_word)
    mem.ww(DS, rec + 0x06, r.direction_or_step)
    mem.ww(DS, rec + 0x36, r.waypoint_ptr_after)
    mem.ww(DS, rec + 0x08, r.sprite)
    mem.ww(DS, 0x2306, r.target_x_2306)   # B2D4: the seek target globals (every retry rewrites them)
    mem.ww(DS, 0x2304, r.target_y_2304)   # B2D8
    mem.ww(DS, 0x2308, r.seek_mode_2308)  # B2DB/B2EF: the seek-mode global (1, or 2 on planet0/BDAC)


def _step_waypoint_11(mem, rec: int) -> None:
    mem.ww(DS, rec + 0x36, WAYPOINT_FOLLOWER_TABLE_SEED)   # B2C3: seed the waypoint pointer
    mem.ww(DS, rec + 0x18, 0x0012)                          # B2C8: retag the record as 0x12
    _step_waypoint_12(mem, rec)                             # falls straight into 0x12's body


#: behavior 0x10's own waypoint schedule (B2BC seeds A45C; 0x11 seeds A43C, one entry earlier)
WAYPOINT_FOLLOWER_TABLE_SEED_10 = 0xA45C


def _step_waypoint_10(mem, rec: int) -> None:
    mem.ww(DS, rec + 0x36, WAYPOINT_FOLLOWER_TABLE_SEED_10)  # B2BC: seed 0x10's waypoint schedule
    mem.ww(DS, rec + 0x18, 0x0012)                          # B2C8: retag the record as 0x12
    _step_waypoint_12(mem, rec)                             # the shared follower body


#: the 8BC8..8BF5 waypoint-seed stubs (byte-identical apart from the table pointer): each seeds
#: its own +0x36 waypoint TABLE and jumps to B2C8 -- the retag-as-0x12 + follower body 0x11 uses.
_WAYPOINT_SEED_BY_BEHAVIOR = {0x41: 0x96F0, 0x43: 0x970C, 0x44: 0x9724,
                              0x45: 0x973C, 0x4A: 0x975C, 0x51: 0x9764}


def _step_waypoint_seed(mem, rec: int, beh: int) -> None:
    mem.ww(DS, rec + 0x36, _WAYPOINT_SEED_BY_BEHAVIOR[beh])
    mem.ww(DS, rec + 0x18, 0x0012)                          # B2C8: retag the record as 0x12
    _step_waypoint_12(mem, rec)


def _step_ramp_steer_29(mem, rec: int) -> None:
    r = step_ramp_steer_29(sprite=mem.rw(DS, rec + 0x08), gate_2328=mem.rw(DS, 0x2328))
    if not r.fired:
        return
    if r.sprite is not None:
        mem.ww(DS, rec + 0x08, r.sprite)
    if r.retarget:
        dx, dy = retarget_delta_toward_anchor_74e2(
            mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
            mem.rw(DS, 0x237E), mem.rw(DS, 0x2380))
        mem.ww(DS, rec + 0x2A, dx)
        mem.ww(DS, rec + 0x2C, dy)
    if not r.steer:
        return
    _steer_missile_tail_8744(mem, rec)


def _steer_missile_tail_8744(mem, rec: int) -> None:
    """The shared ``1010:8744`` steer tail (behavior 0x3F's whole body; 0x29 and 0x3E jump here):
    ``[2312] = 2``, the 5E42 delta steer (the record's own +0x2C/+0x2A deltas), write-backs,
    ``[2312] = 3``, then the signed-Y bounds kill (y > 0xC0 or y < 0 -> BFC7)."""
    mem.ww(DS, 0x2312, RAMP_29_STEER_MODE_DURING)
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))
    steer = object_delta_steer_5e42(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x06),
        mem.rw(DS, rec + 0x2C), mem.rw(DS, rec + 0x2A), mem.rw(DS, rec + 0x2E),
        RAMP_29_STEER_MODE_DURING, table)
    mem.ww(DS, rec + 0x06, steer.direction_or_step)
    mem.ww(DS, rec + 0x02, steer.x_word)
    mem.ww(DS, rec + 0x04, steer.y_word)
    mem.ww(DS, rec + 0x2E, steer.move_step_error)
    mem.ww(DS, 0x2312, RAMP_29_STEER_MODE_AFTER)
    y_signed = i16(steer.y_word)
    if y_signed > RAMP_29_DEATH_Y_MAX or y_signed < RAMP_29_DEATH_Y_MIN:
        _bfc7_touch_death(mem, rec)


def _step_latch_bouncer_4b(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x4B (``1010:8C6D``): sprite = ``[96D2 + [233C]*2] + 0xCF`` WAITING for x == 0x40
    EXACTLY; there -- MORPH ``+0x18 = 0x33``, dir = 1, and jmp 88CF (the 0x33 triple-AFD8 bounce
    body) the SAME frame."""
    anim = mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x233C) & 0xFFFF) * 2) & 0xFFFF)
    mem.ww(DS, rec + 0x08, (anim + 0x00CF) & 0xFFFF)
    if mem.rw(DS, rec + 0x02) != 0x0040:
        return
    mem.ww(DS, rec + 0x18, 0x0033)
    mem.ww(DS, rec + 0x06, 0x0001)
    _step_bouncer_33(mem, rec, tiles)


def _step_glide_4c(mem, rec: int) -> bool:
    """Behavior 0x4C (``1010:8C94``): while dir != 0 -- sprite 0x74 WAITING for x == 0xB0 EXACTLY
    (that path exits BC45, WITH drift), arrival sets dir = 0; then sprite = ``([2328]>>2) + 0x73``
    and x -= 4, exiting BC4B (no drift).  Returns the postmove's ``with_drift``."""
    if mem.rw(DS, rec + 0x06) != 0:
        mem.ww(DS, rec + 0x08, 0x0074)
        if mem.rw(DS, rec + 0x02) != 0x00B0:
            return True
        mem.ww(DS, rec + 0x06, 0x0000)
    mem.ww(DS, rec + 0x08, ((mem.rw(DS, 0x2328) >> 2) + 0x0073) & 0xFFFF)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) - 4) & 0xFFFF)
    return False


def _step_glide_morph_4d(mem, rec: int) -> bool:
    """Behavior 0x4D (``1010:8CC2``): sprite 0x6E; while dir == 4 WAIT for x == 0x80 EXACTLY
    (that path exits BC45, WITH drift), arrival sets dir = 0; then x -= 4 (BC4B, no drift) until
    x == 0x60 EXACTLY -- there dir = 2, MORPH ``+0x18 = 0x39``, and jmp 8A23 (the 0x39 faller
    body) the SAME frame (BC45).  Returns the postmove's ``with_drift``."""
    mem.ww(DS, rec + 0x08, 0x006E)
    if mem.rw(DS, rec + 0x06) == 0x0004:
        if mem.rw(DS, rec + 0x02) != 0x0080:
            return True
        mem.ww(DS, rec + 0x06, 0x0000)
    x = (mem.rw(DS, rec + 0x02) - 4) & 0xFFFF
    mem.ww(DS, rec + 0x02, x)
    if x != 0x0060:
        return False
    mem.ww(DS, rec + 0x06, 0x0002)
    mem.ww(DS, rec + 0x18, 0x0039)
    _step_faller_39(mem, rec)
    return True


def _step_bobber_42(mem, rec: int) -> None:
    """Behavior 0x42 (``1010:8BF8``): sprite = ``[96D2 + [233C]*2] + 0xCF``, x += 1, and a
    ``[232E]``-clocked vertical bob -- y -= 1 while the clock is <= 0x1F, y += 1 above."""
    anim = mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x233C) & 0xFFFF) * 2) & 0xFFFF)
    mem.ww(DS, rec + 0x08, (anim + 0x00CF) & 0xFFFF)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 1) & 0xFFFF)
    dy = 1 if mem.rw(DS, 0x232E) > 0x001F else -1
    mem.ww(DS, rec + 0x04, (mem.rw(DS, rec + 0x04) + dy) & 0xFFFF)


def _step_jitter_40(mem, rec: int) -> None:
    """Behavior 0x40 (``1010:8B3B``): sprite = ``[96D2 + [233C]*2] + 0xCF``; jitter ONE random
    axis -- the 4D95 draw's low bit picks a cell offset from the ``[96EC]`` pair {+0x04, +0x02} --
    by ``([232E] & 1)*2 - 1`` (+/-1px); then while signed x >= 0x80, a C237 child on the
    ``[232C] == 0x1F`` tick and x += 2."""
    anim = mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x233C) & 0xFFFF) * 2) & 0xFFFF)
    mem.ww(DS, rec + 0x08, (anim + 0x00CF) & 0xFFFF)
    ring = tuple(mem.rw(DS, 0x20A8 + i * 2) for i in range(16))
    rand, nxt = canned_random_next_4d95(mem.rw(DS, 0x20A6), ring)
    mem.ww(DS, 0x20A6, nxt)
    cell = mem.rw(DS, (0x96EC + ((rand & 1) << 1)) & 0xFFFF)
    delta = ((mem.rw(DS, 0x232E) & 1) << 1) - 1
    mem.ww(DS, (rec + cell) & 0xFFFF, (mem.rw(DS, (rec + cell) & 0xFFFF) + delta) & 0xFFFF)
    if i16(mem.rw(DS, rec + 0x02)) < 0x0080:
        return
    if mem.rw(DS, 0x232C) == 0x001F:
        _spawn_child_c237(mem, rec, 0x40)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 2) & 0xFFFF)


def _jitter_axis_96ec(mem, rec: int, delta: int) -> None:
    """The shared 4D95-picked axis jitter: the draw's low bit picks a cell offset from the
    ``[96EC]`` pair, and ``delta`` is added to that record cell."""
    ring = tuple(mem.rw(DS, 0x20A8 + i * 2) for i in range(16))
    rand, nxt = canned_random_next_4d95(mem.rw(DS, 0x20A6), ring)
    mem.ww(DS, 0x20A6, nxt)
    cell = mem.rw(DS, (0x96EC + ((rand & 1) << 1)) & 0xFFFF)
    mem.ww(DS, (rec + cell) & 0xFFFF, (mem.rw(DS, (rec + cell) & 0xFFFF) + delta) & 0xFFFF)


def _step_jitter_emitter_68(mem, rec: int) -> None:
    """Behavior 0x68 (``1010:8AF9``): the 0x40-family jitter with a planet-keyed anim sprite --
    ``[96D2 + [233C]*2]`` + 0x24 (planet 4) / 0xA1 (planet 5) / 0x100 (else); the +/-1px 96EC
    axis jitter; then while signed x >= 0x80, a C237 child on the [232C] == 0x1F tick and
    x += 2."""
    anim = mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x233C) & 0xFFFF) * 2) & 0xFFFF)
    planet = mem.rw(DS, 0x2356)
    bias = 0x0024 if planet == 4 else (0x00A1 if planet == 5 else 0x0100)
    mem.ww(DS, rec + 0x08, (anim + bias) & 0xFFFF)
    _jitter_axis_96ec(mem, rec, ((mem.rw(DS, 0x232E) & 1) << 1) - 1)
    if i16(mem.rw(DS, rec + 0x02)) < 0x0080:
        return
    if mem.rw(DS, 0x232C) == 0x001F:
        _spawn_child_c237(mem, rec, 0x68)
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 2) & 0xFFFF)


def _step_jitter_creeper_69(mem, rec: int) -> None:
    """Behavior 0x69 (``1010:8B80``): sprite = ([232A] >> 3) + 0x178 (planet 4) / 0x103 (else);
    the SAME 96EC axis jitter at +/-4px (the +/-1 shifted left twice); then while signed
    x <= 0x18, x += 8."""
    base = 0x0178 if mem.rw(DS, 0x2356) == 4 else 0x0103
    mem.ww(DS, rec + 0x08, ((mem.rw(DS, 0x232A) >> 3) + base) & 0xFFFF)
    _jitter_axis_96ec(mem, rec, ((((mem.rw(DS, 0x232E) & 1) << 1) - 1) << 2) & 0xFFFF)
    if i16(mem.rw(DS, rec + 0x02)) > 0x0018:
        return
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 8) & 0xFFFF)


def _step_beacon_2d(mem, rec: int) -> None:
    """Behavior 0x2D (``1010:87AF``): sprite = ``[233C] + 0x93``, then the shared 87B5 beacon
    tail (x > 0x60 drifts right 4px; else wait for [2330] == 0x7F, dir = 4, ONE C237 child)."""
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x233C) + 0x0093) & 0xFFFF)
    x = mem.rw(DS, rec + 0x02)
    if x > 0x0060:
        mem.ww(DS, rec + 0x02, (x + 4) & 0xFFFF)
        return
    if mem.rw(DS, 0x2330) != 0x007F:
        return
    mem.ww(DS, rec + 0x06, 0x0004)
    _spawn_child_c237(mem, rec, 0x2D)


def _step_strider_64(mem, rec: int) -> None:
    """Behavior 0x64 (``1010:F4FE``): x += 2 on planet 4, else x += 4."""
    step = 2 if mem.rw(DS, 0x2356) == 4 else 4
    mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + step) & 0xFFFF)


def _step_dropper_34(mem, rec: int) -> None:
    """Behavior 0x34 (``1010:88E8``): planet-keyed sprite (``[96DA + [2356]*2]``, minus 1 on the
    upper half y < 0x60); on planets 0/6 only, WAIT for x >= 0x50; then every frame the ``[232E]``
    clock is >= 0x32 -- sound 0x13 and a C237 child aimed down-ish on the upper half (dir 2, or 3
    when ``[2324] != 1``) / up-ish on the lower half (dir 6, or 5 when ``[2324] != 1``)."""
    planet = mem.rw(DS, 0x2356)
    sprite = mem.rw(DS, (0x96DA + ((planet << 1) & 0xFFFF)) & 0xFFFF)
    upper = mem.rw(DS, rec + 0x04) < 0x0060
    if upper:
        sprite = (sprite - 1) & 0xFFFF
    mem.ww(DS, rec + 0x08, sprite)
    if planet in (0x0006, 0x0000) and mem.rw(DS, rec + 0x02) < 0x0050:
        return
    if mem.rw(DS, 0x232E) < 0x0032:
        return
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x13)
    if upper:
        d = 0x0002 if mem.rw(DS, 0x2324) == 1 else 0x0003
    else:
        d = 0x0006 if mem.rw(DS, 0x2324) == 1 else 0x0005
    mem.ww(DS, rec + 0x06, d)
    _spawn_child_c237(mem, rec, 0x34)


def _step_wave_diver_2c(mem, rec: int) -> None:
    """Behavior 0x2C (``1010:B70E``) -- the planet-2 wave enemy's MORPH target: sprite =
    ``[233C] + 0xB9``, then the 5E42 delta steer over the record's own +0x2A/+0x2C deltas
    (set by the 0x23 arrival's 74E2), ``[2312]`` 2 -> 3 -- the 8744 steer WITHOUT the
    Y-bounds kill."""
    mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x233C) + 0x00B9) & 0xFFFF)
    mem.ww(DS, 0x2312, RAMP_29_STEER_MODE_DURING)
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))
    steer = object_delta_steer_5e42(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x06),
        mem.rw(DS, rec + 0x2C), mem.rw(DS, rec + 0x2A), mem.rw(DS, rec + 0x2E),
        RAMP_29_STEER_MODE_DURING, table)
    mem.ww(DS, rec + 0x06, steer.direction_or_step)
    mem.ww(DS, rec + 0x02, steer.x_word)
    mem.ww(DS, rec + 0x04, steer.y_word)
    mem.ww(DS, rec + 0x2E, steer.move_step_error)
    mem.ww(DS, 0x2312, RAMP_29_STEER_MODE_AFTER)


def _step_wave_enemy_23(mem, rec: int) -> None:
    """Behavior 0x23 (``1010:B690``) -- the B615-spawned WAVE ENEMY: while its y/x differ from
    the ``+0x32``/``+0x34`` targets, the B85C tail ([2308]=2, the B729 seek toward its own
    targets, dir=4).  ARRIVED: the ``0x1C <= x <= 0x20`` sound-0x1D beat; planet 2 -- a 74E2
    self-retarget + MORPH to 0x2C; other planets -- the sub-phase (+0x1C) entry of the
    A932 (or A942 on planets 3/5) table: {cell-ptr, advance} -> sprite = ``[[ptr]]>>1 + 0x80``
    (0x6D on 3/5), then x and target-x advance together."""
    if (mem.rw(DS, rec + 0x04) != mem.rw(DS, rec + 0x32)
            or mem.rw(DS, rec + 0x02) != mem.rw(DS, rec + 0x34)):
        mem.ww(DS, 0x2308, 0x0002)          # B85C: the mode-2 seek tail
        _b729_seek(mem, rec)
        mem.ww(DS, rec + 0x06, 0x0004)
        return
    x = mem.rw(DS, rec + 0x02)
    if 0x001C <= x <= 0x0020 and mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x1D)
    planet = mem.rw(DS, 0x2356)
    if planet == 2:
        dx, dy = retarget_delta_toward_anchor_74e2(
            x, mem.rw(DS, rec + 0x04), mem.rw(DS, 0x237E), mem.rw(DS, 0x2380))
        mem.ww(DS, rec + 0x2A, dx)
        mem.ww(DS, rec + 0x2C, dy)
        mem.ww(DS, rec + 0x18, 0x002C)      # B706: the morph into 0x2C
        return
    base, spr_add = (0xA942, 0x006D) if planet in (3, 5) else (0xA932, 0x0080)
    si = (base + (mem.rw(DS, rec + 0x1C) * 4)) & 0xFFFF
    ptr = mem.rw(DS, si)
    mem.ww(DS, rec + 0x08, ((mem.rw(DS, ptr) >> 1) + spr_add) & 0xFFFF)
    adv = mem.rw(DS, (si + 2) & 0xFFFF)
    mem.ww(DS, rec + 0x02, (x + adv) & 0xFFFF)
    mem.ww(DS, rec + 0x34, (mem.rw(DS, rec + 0x34) + adv) & 0xFFFF)


def _step_wave_driver_21(mem, rec: int) -> None:
    """Behavior 0x21 (``1010:B556``) -- THE WAVE DRIVER, the A7A0-phased family (planets other
    than 0/3/4; the recovered ``wave_driver_dispatch_b556`` names the branch):

    * ``per_planet`` (A7A0 < 0xC8): the **B615** spawn -- on the ``[2328] == 7`` cadence tick,
      an 81E9 alloc (the 8209 stamp with the DRIVER's own x/y as the frame values -- here the
      "leak" is the intended position inherit), the ``A894`` Y-schedule ring (A896..A8B0, wraps)
      into ``+0x32``, ``+0x34 = 0x10``, behavior ``0x23``; planet 2 adds ``+0x20 = 1``; planets
      1/3/5 add ``+0x20 = FFFF`` + the ``[2340]++ & 3`` sub-phase into ``+0x1C``;
    * ``none`` (A7A0 < 0xF0): a pause -- nothing;
    * ``boss_transform``: the recovered ``boss_transform_stamp_b58a`` record overwrite.

    The planet-0 leader group / planet-3 phase machine / planet-4 family fail loud until their
    bodies are recovered."""
    from overkill.recovered.systems.frame_loop import (boss_transform_stamp_b58a,
                                                       wave_driver_dispatch_b556)
    from overkill.recovered.adapters.tile_cues import _stamp_8209

    kind = wave_driver_dispatch_b556(mem.rw(DS, 0x2356), mem.rw(DS, 0xA7A0))
    if kind == "none":
        return
    if kind == "boss_transform":
        for off, val in boss_transform_stamp_b58a(mem.rw(DS, 0x2356)).items():
            mem.ww(DS, rec + off, val)
        return
    if kind != "per_planet":
        raise RecoveryGap(f"wave-driver branch {kind!r} (behavior 0x21, 1010:B556)",
                          "the planet-0 leader group / planet-3 phase machine / planet-4 family "
                          "bodies are not recovered")
    # B615
    if mem.rw(DS, 0x2328) != 0x0007:
        return
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
    if slot == 0xFFFF:
        return
    _stamp_8209(mem, slot, mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x02))
    # B673: the Y-schedule ring
    si = mem.rw(DS, 0xA894)
    if si >= 0xA8B2:
        mem.ww(DS, 0xA894, 0xA896)
        si = 0xA896
    mem.ww(DS, slot + 0x32, mem.rw(DS, si))
    mem.ww(DS, 0xA894, (si + 2) & 0xFFFF)
    mem.ww(DS, slot + 0x34, 0x0010)
    mem.ww(DS, slot + 0x18, 0x0023)
    planet = mem.rw(DS, 0x2356)
    if planet == 2:
        mem.ww(DS, slot + 0x20, 0x0001)
    elif planet in (1, 3, 5):
        mem.ww(DS, slot + 0x20, 0xFFFF)
        ax = mem.rw(DS, 0x2340)
        mem.ww(DS, 0x2340, (ax + 1) & 0xFFFF)
        mem.ww(DS, slot + 0x1C, ax & 3)


def _step_missile_2b(mem, rec: int) -> None:
    """Behavior 0x2B (``1010:8715``): sprite = ``0xA5 + [233C]``, then jmp 8744 -- the shared
    steer tail (0x28's planet-2 child; the sprite base matches the 8676 spawner's 0xA5 stamp)."""
    mem.ww(DS, rec + 0x08, (0x00A5 + mem.rw(DS, 0x233C)) & 0xFFFF)
    _steer_missile_tail_8744(mem, rec)


def _step_arm_missile_3e(mem, rec: int) -> None:
    """Behavior 0x3E (``1010:8ADD``): sprite 0x0E WAITING for signed x >= 0xA0; there -- MORPH
    ``+0x18 = 0x3F``, the 74E2 self-retarget (deltas toward the anchor PERSISTED to +0x2A/+0x2C),
    and the shared 8744 steer tail the SAME frame."""
    mem.ww(DS, rec + 0x08, 0x000E)
    if i16(mem.rw(DS, rec + 0x02)) < 0x00A0:
        return
    mem.ww(DS, rec + 0x18, 0x003F)
    dx, dy = retarget_delta_toward_anchor_74e2(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
        mem.rw(DS, 0x237E), mem.rw(DS, 0x2380))
    mem.ww(DS, rec + 0x2A, dx)
    mem.ww(DS, rec + 0x2C, dy)
    _steer_missile_tail_8744(mem, rec)


def _step_spawner_30(mem, rec: int) -> None:
    anim = mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x233C) & 0xFFFF) * 2) & 0xFFFF)
    r = step_spawner_anim_30(
        planet_2356=mem.rw(DS, 0x2356), anchor_y_2380=mem.rw(DS, 0x2380),
        y_word=mem.rw(DS, rec + 0x04), sprite_08=mem.rw(DS, rec + 0x08),
        anim_table_value=anim, gate_2326=mem.rw(DS, 0x2326), gate_232a=mem.rw(DS, 0x232A))
    if r.early_return:
        return
    mem.ww(DS, rec + 0x08, r.sprite)
    if r.spawn:
        _spawn_child_c237(mem, rec, 0x30)     # 0x30 ignores the return (uses the spawn side effect)
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, 0x0E)          # 0x30's own sound override (post-C237)


#: 0x28's per-planet child override (86BB..8704): (behavior +0x18, sprite +0x08, retarget-via-74E2).
#: Planets NOT in this map fall through to BC45 leaving the 81F4 default behavior (0x14) -- but only
#: planets 1/4 (0x29) are exercised by the L1 demo shadow; 2 (0x2B) and 5 (0x7A) are decoded-not-tested.
_SPAWNER_28_CHILD_BY_PLANET = {0x01: (0x29, 0xA1, False), 0x04: (0x29, 0xA1, False),
                               0x02: (0x2B, 0xA5, True), 0x05: (0x7A, 0x20, True)}


def _step_spawner_28(mem, rec: int) -> None:
    table = tuple(mem.rb(DS, (0x96AA + i) & 0xFFFF) for i in range(0x18))
    r = step_spawner_28(counter_06=mem.rw(DS, rec + 0x06), gate_2332=mem.rw(DS, 0x2332),
                        active_a47e=mem.rw(DS, 0xA47E), sprite_table=table)
    mem.ww(DS, rec + 0x06, r.counter)
    mem.ww(DS, rec + 0x08, r.sprite)
    if not r.spawn:
        return
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)   # 81F4 -> 7524
    if slot == 0xFFFF:
        return
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x0B)             # 81F4's own sound (pre-stamp, gated on [98C0])
    for off, val in enemy_spawn_stamp_8209(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04)).items():
        mem.ww(DS, slot + off, val)
    mem.ww(DS, slot + 0x20, 0x0004)          # 86AE (redundant with the 8209 stamp, but the ASM re-writes it)
    mem.ww(DS, slot + 0x02, (mem.rw(DS, slot + 0x02) + 0x08) & 0xFFFF)   # 86B3: child X += 8
    mem.ww(DS, slot + 0x04, (mem.rw(DS, slot + 0x04) + 0x08) & 0xFFFF)   # 86B7: child Y += 8
    override = _SPAWNER_28_CHILD_BY_PLANET.get(mem.rw(DS, 0x2356))
    if override is None:
        return                                # other planets: child stays the 0x14 default
    behavior, sprite, retarget = override
    mem.ww(DS, slot + 0x18, behavior)
    mem.ww(DS, slot + 0x08, sprite)
    if retarget:                              # 86F1/8701: planets 2/5 aim the child at the anchor
        dx, dy = retarget_delta_toward_anchor_74e2(
            mem.rw(DS, slot + 0x02), mem.rw(DS, slot + 0x04),
            mem.rw(DS, 0x237E), mem.rw(DS, 0x2380))
        mem.ww(DS, slot + 0x2A, dx)
        mem.ww(DS, slot + 0x2C, dy)


def _step_bounce_2f(mem, rec: int) -> None:
    # 8825 sets the seek mode [2308]=2 then calls B729; the seek reads the PRE-drift target (+0x32/34)
    blocked = _apply_seek(mem, rec, mem.rw(DS, rec + 0x32), mem.rw(DS, rec + 0x34), 2)
    r = step_bounce_scanner_2f(
        blocked=blocked, target_y_32=mem.rw(DS, rec + 0x32),
        target_x_34=mem.rw(DS, rec + 0x34), a278=mem.rw(DS, 0xA278))
    for off, val in r.record_writes.items():
        mem.ww(DS, rec + off, val)


def _step_scroller_05(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x05 (``1010:AE7D``, EFAE logic_id 5) -- the scroll-left GROUND CRAWLER: a thin
    memory-shaped adapter around the already-VERIFIED whole-AE7D update (``object_update_ae7d``:
    X -= 4; on a 16px-aligned Y with the render gate clear, the 5073 tile probe (+0xC) class-1
    check parks it (direction 0), else it climbs (direction 7, Y -= 4); sprite = direction + 8;
    then the shared AD5A drift + AD60 bounds/tile tail owns active).  ``y == 0`` is the ADC9
    death (x = FFFF -> the AD60 x<8 bound -> BD17)."""
    u = object_update_ae7d(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x00),
        mem.rw(DS, rec + 0x16), mem.rw(DS, 0xA278),
        mem.rw(DS, 0xBDAC) == 0x0001, tiles)
    if u is None:
        mem.ww(DS, rec + 0x02, 0xFFFF)   # ADC9
        _bd17_deactivate(mem, rec)       # -> AD60 x<8 -> BD17
        return
    mem.ww(DS, rec + 0x06, u.direction_or_step)
    mem.ww(DS, rec + 0x08, u.sprite_or_state)
    mem.ww(DS, rec + 0x02, u.x_word)
    mem.ww(DS, rec + 0x04, u.y_word)
    if u.active_word == 0:
        _bd17_deactivate(mem, rec)   # BD17: clear active + the hazard_class-keyed death side effects


def _step_shot_0b(mem, rec: int, tiles: LevelTileContext) -> None:
    table = tuple(mem.rb(DS, (0xA348 + i) & 0xFFFF) for i in range(16))
    u = object_update_b24d(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x06),
        mem.rw(DS, rec + 0x00), mem.rw(DS, rec + 0x1E),
        mem.rw(DS, rec + 0x2A), mem.rw(DS, rec + 0x2C), mem.rw(DS, rec + 0x2E),
        mem.rw(DS, 0x2312), table, mem.rw(DS, rec + 0x16), mem.rw(DS, rec + 0x18),
        mem.rw(DS, 0x237E), mem.rw(DS, 0x2380), mem.rw(DS, 0xA278),
        False, tiles)
    if u is None:
        raise RecoveryGap("behavior 0x0B in-box contact death",
                          "object_update_b24d's contact-death sub-path is not modeled natively")
    mem.ww(DS, rec + 0x06, u.direction_or_step)
    mem.ww(DS, rec + 0x02, u.x_word)
    mem.ww(DS, rec + 0x04, u.y_word)
    mem.ww(DS, rec + 0x2E, u.move_step_error)
    if u.active_word == 0:
        _bd17_deactivate(mem, rec)   # BD17: clear active + the hazard_class-keyed death side effects
    if u.contact:
        _shot_hit_9e19(mem)   # the ADC9 in-box contact marker; the 9E19 fan-out is the VM's
        #                       "separate global side effect" the pure island leaves caller-owned


def _step_shot_02(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x02 (``1010:AED8``, EFAE logic_id 2) -- the PLAYER SHOT (the A4EA fanout seed
    stamps logic_id 2).  A thin memory-shaped adapter around the already-VERIFIED whole-AED8 update
    (``object_update_aed8``: the timer dec + the AEE4 8px step + the B250 contact + the AD60 bounds
    tail).  The timer-death / odd-direction sub-paths return None (an unmodeled fallback) -> fail
    loud."""
    u = object_update_aed8(
        mem.rw(DS, rec + 0x1C), mem.rw(DS, rec + 0x06), mem.rw(DS, rec + 0x02),
        mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x00), mem.rw(DS, rec + 0x1E),
        mem.rw(DS, rec + 0x16), mem.rw(DS, rec + 0x18),
        mem.rw(DS, 0x237E), mem.rw(DS, 0x2380), mem.rw(DS, 0xA278), False, tiles)
    if u is None:
        raise RecoveryGap(f"behavior 0x02 timer-death / odd-direction (record {rec:04X})",
                          "object_update_aed8's unmodeled ADC9 fallback")
    mem.ww(DS, rec + 0x1C, u.substate)
    mem.ww(DS, rec + 0x02, u.x_word)
    mem.ww(DS, rec + 0x04, u.y_word)
    if u.active_word == 0:
        _bd17_deactivate(mem, rec)   # BD17: clear active + the hazard_class-keyed death side effects


#: the AEEE 8-way +/-8px move table (behavior 0x04 on planet 0, direction != 4): dir -> (dx on +0x02,
#: dy on +0x04).  Decoded from the AF0B/AF10/AF14/AEFE/AF02/AF19/AF1D/AF07 fall-through handlers.
_AECD_8WAY_STEP_8PX = ((-8, 0), (-8, 8), (0, 8), (8, 8), (8, 0), (8, -8), (0, -8), (-8, -8))


def _step_child_04(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x04 (``1010:AEBF``, EFAE logic_id 4) -- the C237-spawned child. On the ``planet !=
    0`` path (DS:2356 != 0, always true on L1: 2356==1) AEBF falls straight into AF60 with B250
    pushed as the return -- a thin adapter around the whole-AF60 update (double 2px step + the
    shared B250 contact + AD5A/ADC9 -> AD60 tail).  Contact triggers the single 9E19 fan-out
    (logic_id 4 != 3, so exactly one call per contact_fanout_count) exactly like behavior 0x0B's
    shot-hit beat."""
    if mem.rw(DS, 0x2356) == 0 and (mem.rw(DS, rec + 0x06) & 0x7) != 4:
        # AECD planet-0 dispatch: direction != 4 takes the AEE4 8-way jump table -- a single +/-8px
        # step per direction, then AEBF's pushed B250 return runs the SAME contact + AD5A drift + AD60
        # tail the AF60 path uses (direction == 4 falls into AF60 below like planets 1-5).
        dx, dy = _AECD_8WAY_STEP_8PX[mem.rw(DS, rec + 0x06) & 0x7]
        x = (mem.rw(DS, rec + 0x02) + dx) & 0xFFFF
        y = (mem.rw(DS, rec + 0x04) + dy) & 0xFFFF
        contact = (mem.rw(DS, rec + 0x1E) != AED8_SUBSTATE_SKIP_OVERLAP
                   and overlap_contact_box_contains(x, y, mem.rw(DS, 0x237E), mem.rw(DS, 0x2380)))
        final_x = AED8_CONTACT_DEATH_X if contact else (x + mem.rw(DS, 0xA278)) & 0xFFFF   # ADC9/AD5A
        mem.ww(DS, rec + 0x02, final_x)
        mem.ww(DS, rec + 0x04, y)
        decision = object_bounds_tile_decision_ad60(final_x, y, mem.rw(DS, rec + 0x16),
                                                    mem.rw(DS, rec + 0x18), tile_probe_suppressed=False)
        if decision.kind == "deactivate" or (decision.kind != "skip"
                                             and object_tile_probe_deactivates_ad60(final_x, y, tiles)):
            _bd17_deactivate(mem, rec)
        if contact:
            _shot_hit_9e19(mem)
        return
    u = object_update_af60(
        mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04), mem.rw(DS, rec + 0x06),
        mem.rw(DS, rec + 0x00), mem.rw(DS, rec + 0x1E),
        mem.rw(DS, rec + 0x16), mem.rw(DS, rec + 0x18),
        mem.rw(DS, 0x237E), mem.rw(DS, 0x2380), mem.rw(DS, 0xA278), False, tiles)
    mem.ww(DS, rec + 0x02, u.x_word)
    mem.ww(DS, rec + 0x04, u.y_word)
    if u.active_word == 0:
        _bd17_deactivate(mem, rec)   # BD17: clear active + the hazard_class-keyed death side effects
    if u.contact:
        _shot_hit_9e19(mem)


def _shot_hit_9e19(mem) -> None:
    """``1010:9E19`` -- the shot-hit player-damage beat: hit-flash timer, sound 0x0F, 1..3 energy
    decs by the DS:BEDC shield level; exhaustion refills A95C to 0x18 and falls into the 9E69
    life beat (then the 61DC energy redraw either way)."""
    if mem.rw(DS, 0xA47C) == 1 or mem.rw(DS, 0x2384) >= 3 or mem.rw(DS, 0xA95A) == 0xFFFF:
        return
    mem.ww(DS, 0x23A0, 0x0008)
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x0F)
    bedc = mem.rw(DS, 0xBEDC)
    decs = 1 + (1 if bedc != 0 else 0) + (1 if bedc not in (0, 1) else 0)
    exhausted = False
    for _ in range(decs):
        v = (mem.rw(DS, 0xA95C) - 1) & 0xFFFF
        mem.ww(DS, 0xA95C, v)
        if v == 0:
            exhausted = True
            break
    if exhausted:
        mem.ww(DS, 0xA95C, 0x0018)
        _player_hit_9e69(mem)
        return
    _energy_redraw_61dc(mem)


def _energy_redraw_61dc(mem) -> None:
    """The 61DC HUD-energy beat's DGROUP half: reset the six 2368..2372 slot words to 4, then
    drain the first nonzero slot once per A95C unit (61C7); the blits after are presentation."""
    for i in range(6):
        mem.ww(DS, 0x2368 + i * 2, 4)
    count = mem.rw(DS, 0xA95C)
    for _ in range(count if count < 0x8000 else 0):
        for i in range(6):
            v = mem.rw(DS, 0x2368 + i * 2)
            if v:
                mem.ww(DS, 0x2368 + i * 2, v - 1)
                break


def _hud_energy_beat_9ec2(mem) -> None:
    """``1010:9EC2``: the HUD-energy beat -- the 61DC redraw, plus (mode-1 dual-page video ONLY,
    ``cs:[95BC]==1``) a 511F/61DC/511F page pair.  Tandy is mode 2, so the 511F half never runs on
    this port's path; fail loud rather than fake it if a mode-1 image ever reaches here."""
    _energy_redraw_61dc(mem)
    if mem.rw(CODE_SEG, 0x95BC) == 1:
        raise RecoveryGap("the 9EC2 dual-page energy beat (1010:511F)",
                          "cs:[95BC]==1 (mode-1 dual-page video) -- 511F is not recovered; the Tandy"
                          " path (mode 2) never takes this branch")


#: the 837A weapon-script PREDICATES (1010 addresses -> latch decision).  Each script entry is
#: {state word, predicate fn, action fn}; 837A calls the predicate and LATCHES the state into the
#: record's +0 on NZ.  Predicates are read-only: flag helpers (83D7 Z / 83DA NZ), the A958 weapon
#: mode compares (83DE..83FC, k=0..5), the A95E/A960 one-shot flags, and the pod-registry
#: free-slot checks (8456/8468/84A2 -- with [2384] pose gates ordered exactly as the ASM
#: short-circuits them).
_WEAPON_SCRIPT_PREDICATES = {
    0x83D7: lambda mem: False,
    0x83DA: lambda mem: True,
    0x83DE: lambda mem: mem.rw(DS, 0xA958) != 0,
    0x83E4: lambda mem: mem.rw(DS, 0xA958) != 1,
    0x83EA: lambda mem: mem.rw(DS, 0xA958) != 2,
    0x83F0: lambda mem: mem.rw(DS, 0xA958) != 3,
    0x83F6: lambda mem: mem.rw(DS, 0xA958) != 4,
    0x83FC: lambda mem: mem.rw(DS, 0xA958) != 5,
    0x8437: lambda mem: mem.rw(DS, 0xA95E) != 1,
    0x8445: lambda mem: mem.rw(DS, 0xA960) == 0,
    0x8456: lambda mem: mem.rw(DS, 0xA96E) == 0xFFFF,
    0x8468: lambda mem: (mem.rw(DS, 0xA966) == 0xFFFF or mem.rw(DS, 0xA968) == 0xFFFF
                         or (mem.rw(DS, 0x2384) != 0
                             and (mem.rw(DS, 0xA96A) == 0xFFFF or mem.rw(DS, 0xA96C) == 0xFFFF))),
    0x84A2: lambda mem: (mem.rw(DS, 0x2384) == 2
                         and (mem.rw(DS, 0xA962) == 0xFFFF or mem.rw(DS, 0xA964) == 0xFFFF)),
    0x84C9: lambda mem: mem.rw(DS, 0x2384) == 0,
    0x84F0: lambda mem: mem.rw(DS, 0x2384) != 2,
}


def _weapon_script_tick_837a(mem) -> None:
    """``1010:837A`` -- the weapon-upgrade SCRIPT SCHEDULER (the first half of the AC19 beat; the
    859E second half is a pure-video chrome redraw, DGROUP-silent).  While an upgrade is pending
    ([95FA] != FFFF), walk that level's script record ([95FC + lvl*2]): probe entries from the
    record's +8 cursor; the first predicate returning NZ LATCHES its state word into +0 (the HUD's
    offered-upgrade icon) without advancing; a Z advances the cursor (FFFF wraps it); ten probes
    without a latch ([95F8]) reset the cursor and park the icon at 0x24."""
    lvl = mem.rw(DS, 0x95FA)
    if lvl == 0xFFFF:
        return
    rec = mem.rw(DS, (0x95FC + ((lvl * 2) & 0xFFFF)) & 0xFFFF)
    script = mem.rw(DS, rec + 6)
    mem.ww(DS, 0x95F8, 0)
    while True:
        idx = mem.rw(DS, rec + 8)
        ent = (script + idx * 6) & 0xFFFF
        fn = mem.rw(DS, (ent + 2) & 0xFFFF)
        if fn == 0xFFFF:
            mem.ww(DS, rec + 8, 0)                      # 83D0: wrap
            continue
        predicate = _WEAPON_SCRIPT_PREDICATES.get(fn)
        if predicate is None:
            raise RecoveryGap(f"837A weapon-script predicate 1010:{fn:04X}",
                              "an unmapped script fn -- decode it before walking")
        if predicate(mem):
            mem.ww(DS, rec + 0, mem.rw(DS, ent))        # 83CA: latch, cursor stays
            return
        mem.ww(DS, rec + 8, (idx + 1) & 0xFFFF)
        scanned = (mem.rw(DS, 0x95F8) + 1) & 0xFFFF
        mem.ww(DS, 0x95F8, scanned)
        if scanned >= 0x000A:                           # 83B8
            mem.ww(DS, rec + 8, 0)
            mem.ww(DS, rec + 0, 0x0024)
            return


def _pod_damage_ac56(mem, rec: int) -> bool:
    """``1010:AC56`` -- the pod HIT beat shared by the tile crash and the collision sweep: sound
    0x0E, the +0x24 = 5 hit-flash variant, then damage only when difficulty (DS:BEDC) != 0 or the
    DS:2324 gate is 1: dec the +0x20 counter; at 0 the flash clears and the pod DIES (returns
    True = the ASM's stc)."""
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x0E)
    mem.ww(DS, rec + 0x24, 0x0005)
    if mem.rw(DS, 0xBEDC) == 0 and mem.rw(DS, 0x2324) != 1:
        return False
    counter = (mem.rw(DS, rec + 0x20) - 1) & 0xFFFF
    mem.ww(DS, rec + 0x20, counter)
    if counter != 0:
        return False
    mem.ww(DS, rec + 0x24, 0x0000)
    return True


def _pod_tile_crash_ac28(mem, rec: int, tiles: LevelTileContext) -> bool:
    """``1010:AC28`` -- the pod TILE-CRASH probe: no-op under the DS:A47C script gate or the BDAC
    render mode; else the 5073 probe at the pod's x/y, class of plane[probe+0xD] != 0 crashes (and
    on a 16px-UNaligned Y the second row plane[probe+0xE] too).  A crash runs the AC56 damage beat;
    returns True only when that beat KILLED the pod."""
    if mem.rw(DS, 0xA47C) != 0 or mem.rw(DS, 0xBDAC) == 1:
        return False
    probe = compute_tile_probe_5073(TileProbeInput(
        origin_x_word=tiles.origin_x_word, row_base_word=tiles.row_base_word,
        object_x_word=mem.rw(DS, rec + 0x02), object_y_word=mem.rw(DS, rec + 0x04)))
    raw = tiles.tile_plane[(probe.tile_offset_word + 0x0D) & 0xFFFF]
    if lookup_tile_class_byte(raw, tiles.class_table) != 0:
        return _pod_damage_ac56(mem, rec)
    if mem.rw(DS, rec + 0x04) & 0x000F:
        raw = tiles.tile_plane[(probe.tile_offset_word + 0x0E) & 0xFFFF]
        if lookup_tile_class_byte(raw, tiles.class_table) != 0:
            return _pod_damage_ac56(mem, rec)
    return False


def _s16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def _pod_collision_sweep_ac81(mem, rec: int) -> tuple[int | None, bool]:
    """``1010:AC81`` -- the pod-vs-pool collision sweep: over the 0x23 records at DS:23B4 (stride
    0x38; the player record 237C sits BELOW the base and is excluded), active + behavior != 1 +
    the +0x14 scan flag == 1, a SIGNED +/-16px box on both axes, and a +0x0E owner-id mismatch.
    The FIRST hit ends the sweep: type 5 -> the AAD3 pickup collect; type 4 -> the BFC7 touch
    death on the victim + the AC56 damage beat on the pod.  Returns (the type-4 victim record or
    None, pod-died)."""
    if mem.rw(DS, 0xBDAC) == 1:
        return None, False
    y = _s16(mem.rw(DS, rec + 0x04))
    x = _s16(mem.rw(DS, rec + 0x02))
    bx = 0x23B4
    for _ in range(0x23):
        if (mem.rw(DS, bx) != 0 and mem.rw(DS, bx + 0x18) != 1
                and mem.rw(DS, bx + 0x14) == 1):
            tx = mem.rw(DS, bx + 0x02)
            ty = mem.rw(DS, bx + 0x04)
            if (x <= _s16((tx + 0x10) & 0xFFFF) and x >= _s16((tx - 0x10) & 0xFFFF)
                    and y <= _s16((ty + 0x10) & 0xFFFF) and y >= _s16((ty - 0x10) & 0xFFFF)
                    and mem.rw(DS, rec + 0x0E) != mem.rw(DS, bx + 0x0E)):
                if mem.rw(DS, bx + 0x16) == 5:
                    _pickup_collect_aad3(mem, bx)   # ACF9: push bp; bp = the pickup; AAD3
                    return None, False
                if mem.rw(DS, bx + 0x16) == 4:      # ACE8
                    _bfc7_touch_death(mem, bx)      # ACEE -> AB99: the victim dies
                    return bx, _pod_damage_ac56(mem, rec)
                # a type that is neither 4 nor 5 keeps sweeping (ACD2)
        bx += 0x38
    return None, False


def _pod_death_abf3(mem, rec: int) -> None:
    """``1010:ABF3`` -- the pod DYING transform: sound 0x19, behavior := 1 (the dying-anim state),
    type := 4, +0x22 := 0, sprite := 0, then the AC19 beat (the 837A weapon-script tick +
    the video-only 859E chrome redraw)."""
    if rec == 0xFFFF:
        return
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x19)
    mem.ww(DS, rec + 0x18, 0x0001)
    mem.ww(DS, rec + 0x16, 0x0004)
    mem.ww(DS, rec + 0x22, 0x0000)
    mem.ww(DS, rec + 0x08, 0x0000)
    _weapon_script_tick_837a(mem)                       # AC19


#: the AD1D pod registry: DS slot address -> jumps into the shared AB77 body (order-faithful)
_POD_SLOTS_AB77 = (0xA966, 0xA968, 0xA96A, 0xA96C)


def _step_special_pod_1(mem, rec: int, tiles: LevelTileContext) -> None:
    """Object type 1 (``1010:AD04`` via AA36[1]) -- the player's POD/ESCORT records, tracked by the
    DS:A962..A96E slot registry.  Gate: skipped until the scroll progress DS:2350 > 0xB6 (unless
    the BDAC render mode).  Three families:

    * sprite 0xF (ABCA, slot A96E): repositioned every frame from the A420 per-player-sprite
      offset table + the player record 237C, then the AC28 tile crash + the AC81 sweep;
    * slots A966/A968/A96A/A96C (AB77): sprite = [233C]+0x18, the AC28 tile crash + the AC81
      sweep ([A42C] latches the slot address);
    * slots A962/A964 (ABA3): sprite = [233C]+0x14, the AC81 sweep only ([A42E] latches).

    Any death clears the registry slot to FFFF and runs the ABF3 dying transform; a player in the
    dying pose ([2384] >= 3) kills the pod outright."""
    if mem.rw(DS, 0xBDAC) != 1 and mem.rw(DS, 0x2350) <= 0x00B6:
        return
    if mem.rw(DS, rec + 0x08) == 0x000F:                        # ABCA: the A96E tracker pod
        if mem.rw(DS, 0x2384) >= 3:
            mem.ww(DS, 0xA96E, 0xFFFF)
            _pod_death_abf3(mem, rec)
            return
        si = ((mem.rw(DS, 0x2384) * 4) + 0xA420) & 0xFFFF       # AB34 (dx=A420)
        mem.ww(DS, rec + 0x02, (mem.rw(DS, si) + mem.rw(DS, 0x237E)) & 0xFFFF)
        mem.ww(DS, rec + 0x04, (mem.rw(DS, (si + 2) & 0xFFFF) + mem.rw(DS, 0x2380)) & 0xFFFF)
        if _pod_tile_crash_ac28(mem, rec, tiles):
            mem.ww(DS, 0xA96E, 0xFFFF)
            _pod_death_abf3(mem, rec)
            return
        victim, died = _pod_collision_sweep_ac81(mem, rec)
        if died:
            mem.ww(DS, 0xA96E, 0xFFFF)                          # ABEA order: clear, AB99, ABF3
            _bfc7_touch_death(mem, victim)                      # the ABF0 second AB99 beat
            _pod_death_abf3(mem, rec)
        return
    for slot in _POD_SLOTS_AB77:                                # AD1D..AD3E -> AB77
        if rec == mem.rw(DS, slot):
            mem.ww(DS, 0xA42C, slot)
            if mem.rw(DS, 0x2384) >= 3:
                mem.ww(DS, slot, 0xFFFF)
                _pod_death_abf3(mem, rec)
                return
            mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x233C) + 0x0018) & 0xFFFF)   # AB4F
            if _pod_tile_crash_ac28(mem, rec, tiles):
                mem.ww(DS, slot, 0xFFFF)                        # AB8F (tile death skips AB99)
                _pod_death_abf3(mem, rec)
                return
            victim, died = _pod_collision_sweep_ac81(mem, rec)
            if died:
                _bfc7_touch_death(mem, victim)                  # AB8C: the second AB99 beat
                mem.ww(DS, slot, 0xFFFF)
                _pod_death_abf3(mem, rec)
            return
    for slot in (0xA962, 0xA964):                               # AD41..AD56 -> ABA3
        if rec == mem.rw(DS, slot):
            mem.ww(DS, 0xA42E, slot)
            if mem.rw(DS, 0x2384) >= 3:
                mem.ww(DS, slot, 0xFFFF)
                _pod_death_abf3(mem, rec)
                return
            mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x233C) + 0x0014) & 0xFFFF)   # ABAE
            victim, died = _pod_collision_sweep_ac81(mem, rec)
            if died:
                _bfc7_touch_death(mem, victim)                  # ABBD: the second AB99 beat
                mem.ww(DS, slot, 0xFFFF)
                _pod_death_abf3(mem, rec)
            return
    return                                                      # AD59: an unregistered type-1 record


def _pickup_collect_aad3(mem, rec: int) -> None:
    """``1010:AAD3``: the type-5 pickup COLLECT -- pose gate, sound 7, score +0x20 (5F0D), the
    ``+0x26``-keyed AB00 kind dispatch (1 = the 9D4D weapon-level upgrade, 2 = the 9D67 shield/HP
    heal, 3 = the 62AA smart bomb, 4 = the 9DB9 one-shot A97C flag), then the BD17 deactivate of
    the pickup record (the AB0C tail).  Kind 0 (44AF) stays a loud gap."""
    if mem.rw(DS, 0x2384) >= 3:             # AAD3's own pose gate (dying pose -> no collect)
        return
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x07)            # AAE2: sound 7 (kind 2 then overwrites with 0x1C)
    _score_add_5f0d(mem, 0x20)
    kind = mem.rw(DS, rec + 0x26)
    if kind == 2:
        # 9D67: sound 0x1C + the A95A/A95C heal + ONE 9EC2 HUD-energy beat.
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, 0x1C)
        a95a, a95c = pickup_heal_9d67(mem.rw(DS, 0xA95A), mem.rw(DS, 0xA95C))
        mem.ww(DS, 0xA95A, a95a)
        mem.ww(DS, 0xA95C, a95c)
        _hud_energy_beat_9ec2(mem)
    elif kind == 1:
        # 9D4D: the WEAPON-LEVEL upgrade -- inc [95FA] mod 4, then the AC19 HUD-chrome redraw
        # (pure video; the native HUD compose redraws every frame).  The 9D54 spin waits for the
        # sound IRQ to clear [98C8] -- an async flag the synchronous walk cannot model.
        if mem.rb(DS, 0x978E) and mem.rb(DS, 0x98C8) == 1:
            raise RecoveryGap("pickup kind 1's 9D54 sound-flag spin ([978E]!=0 with [98C8]==1)",
                              "waits on the sound IRQ clearing [98C8] -- not representable in the walk")
        mem.ww(DS, 0x95FA, (mem.rw(DS, 0x95FA) + 1) & 0x0003)
        _weapon_script_tick_837a(mem)                   # AC19: 837A + the video-only 859E
    elif kind == 3:
        # 62AA: the SMART BOMB -- sound 8, then every active 32CA-table record with x <= 0xE0,
        # type 4 and behavior not 0/1 dies the FULL BFC7 death (counter := 0 first), in the same
        # descending table order as the walk itself.
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, 0x08)
        for cx in range(EFFECT_SLOTS, 0, -1):
            victim = mem.rw(DS, (EFFECT_TABLE_32CA + cx * 2) & 0xFFFF)
            if (mem.rw(DS, victim) != 0 and mem.rw(DS, victim + 0x02) <= 0x00E0
                    and mem.rw(DS, victim + 0x16) == 4
                    and mem.rw(DS, victim + 0x18) not in (0, 1)):
                mem.ww(DS, victim + 0x20, 0)            # 62EE
                _bfc7_touch_death(mem, victim)
    elif kind == 4:
        # 9DB9: the one-shot companion/flag pickup -- inert while [A97A] == 0x58 or already owned
        # ([A97C] == 1); else (alive pose) set [A97C] = 1 + sound 0x0D (render gate BDAC != 1).
        if mem.rw(DS, 0xA97A) != 0x0058 and mem.rw(DS, 0xA97C) != 1 and mem.rw(DS, 0x2384) < 3:
            mem.ww(DS, 0xA97C, 0x0001)
            if mem.rw(DS, 0xBDAC) != 1 and mem.rb(DS, 0x98C0):
                mem.wb(DS, 0xBEFF, 0x0D)
    else:
        raise RecoveryGap(f"pickup kind {kind} collect -- the AB00 index-{kind} entry (record {rec:04X})",
                          "kind 0 (1010:44AF) is not recovered")
    _bd17_deactivate(mem, rec)              # AB0C: pop bp; jmp BD17 -- the pickup deactivates


def _step_pickup_5(mem, rec: int) -> None:
    """The type-5 PICKUP handler (``1010:AAC2``): drift +X, then the recovered AA46/8331 player-
    overlap test (the DS:214E pose-offset projection into 95F2/95F4); a hit runs the AAD3 COLLECT
    (sound 7 + the 5F0D score + the +0x26-keyed AB00 dispatch + the BD17 deactivate)."""
    x = (mem.rw(DS, rec + 0x02) + 1) & 0xFFFF
    mem.ww(DS, rec + 0x02, x)
    if x & 0x8000:                          # AA46: negative X -> no test
        return
    pose = mem.rw(DS, 0x2384)               # the anchor sprite (the 2384 aliasing)
    if pose >= 3:
        return
    off = (0x214E + pose * 4) & 0xFFFF
    center = view_contact_center_from_offsets_aa46(
        view_x_word=mem.rw(DS, 0x237E), view_y_word=mem.rw(DS, 0x2380),
        offset_x_word=mem.rw(DS, off), offset_y_word=mem.rw(DS, (off + 2) & 0xFFFF))
    mem.ww(DS, 0x95F2, center.x_word)
    mem.ww(DS, 0x95F4, center.y_word)
    slot = SimpleNamespace(x_word=x, y_word=mem.rw(DS, rec + 0x04))
    if view_contact_rect_test(slot, center).hit:
        _pickup_collect_aad3(mem, rec)


def _step_dying_01(mem, rec: int) -> bool:
    """Behavior 0x01 (``1010:BE3C``) -- the death/explosion transition (entered via the recovered
    C037 collision-death stamp: logic_id 1, latch 0, prev id kept).  Parity-gated (odd ``2324``
    frames only): latch++, then the ``+0x14``-keyed anim: key 1 -> sprite = latch until the latch-9
    MORPH (BE60: prev 0x24/0x25 respawn as behavior 0x26, direction/sprite/y-delta per the morph
    table, +0x32=new_y / +0x34=x -- and RETURN, skipping BC45 this frame); key 2 -> sprite = latch+3
    until the latch-0xC BD17 deactivate; key 0 -> no-op.  Returns whether the BC45 postmove runs
    (False only on the morph path's early ``ret``)."""
    if mem.rw(DS, 0x2324) != 1:
        return True
    latch = (mem.rw(DS, rec + 0x22) + 1) & 0xFFFF
    mem.ww(DS, rec + 0x22, latch)
    key = mem.rw(DS, rec + 0x14)
    if key == 0:
        return True
    if key == 1:
        if latch != 9:
            mem.ww(DS, rec + 0x08, latch)
            return True
        morph = dying_latch9_morph_be60(mem.rw(DS, rec + 0x1A))
        if morph is None:
            _bd17_deactivate(mem, rec)   # BE6C: jmp BD17 -- BD17's paths ret (no BC45)
            return False
        direction, sprite, y_delta = morph
        mem.ww(DS, rec + 0x06, direction)
        mem.ww(DS, rec + 0x18, 0x0026)
        mem.ww(DS, rec + 0x08, sprite)
        new_y = (mem.rw(DS, rec + 0x04) + y_delta) & 0xFFFF
        mem.ww(DS, rec + 0x04, new_y)
        mem.ww(DS, rec + 0x32, new_y)                     # BE97/BE9A: +0x32 = the NEW y
        mem.ww(DS, rec + 0x34, mem.rw(DS, rec + 0x02))    # BE9D/BEA0: +0x34 = x
        return False                                      # BEA3: ret -- SKIP the BC45 postmove
    if key == 2:
        if latch != 0x0C:
            mem.ww(DS, rec + 0x08, (latch + 3) & 0xFFFF)
            return True
        _bd17_deactivate(mem, rec)       # BEB6: jmp BD17 -- BD17's paths ret (no BC45)
        return False
    raise RecoveryGap(f"behavior 0x01 key {key} latch {latch:#x} (record {rec:04X})",
                      "an unobserved +0x14 anim key -- only keys 0/1/2 are in the BE54 table")


def _step_morph_26(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x26 (``1010:8302``) -- the latch-9 morph target's float-away/respawn loop.

    FINISHED sprite (0x98/0x92): wait for ``DS:2326 == 3``, then reset y from +0x32 and drop the
    sprite back (the respawn).  Otherwise one AFD8 step in the record's direction (with the wired
    BDD0 contact predicate); a BLOCKED step or ``y >= 0xC0`` ramps the sprite +1 with sound 0x1E."""
    sprite = mem.rw(DS, rec + 0x08)
    if morph_26_is_finished(sprite):
        if morph_26_should_reset(mem.rw(DS, 0x2326)):     # 82EC: [2326]==3 -> the reset
            mem.ww(DS, rec + 0x04, mem.rw(DS, rec + 0x32))
            mem.ww(DS, rec + 0x08, (sprite - 1) & 0xFFFF)
        return
    result = contact_probe_afd8(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
                                mem.rw(DS, rec + 0x06), mem.rw(DS, 0xA278),
                                tiles, _bdd0_contact_at(mem, rec))
    mem.ww(DS, rec + 0x02, result.x_word)
    mem.ww(DS, rec + 0x04, result.y_word)
    # AFD8's own observable scratch (same cells every AFD8 site persists).
    mem.ww(DS, 0xA430, 1 if result.blocked else 0)
    mem.ww(DS, 0xA432, result.snap_x)
    mem.ww(DS, 0xA434, result.snap_y)
    mem.ww(DS, 0xA436, result.mirror_y)
    mem.ww(DS, 0xA438, result.mirror_x)
    mem.ww(DS, 0x215A, result.sample_215a)
    if morph_26_should_ramp(result.blocked, mem.rw(DS, rec + 0x04)):
        mem.ww(DS, rec + 0x08, (mem.rw(DS, rec + 0x08) + 1) & 0xFFFF)
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, MORPH_26_RAMP_SOUND)


def _score_add_5f0d(mem, delta: int) -> None:
    old = tuple(mem.rb(DS, 0x2314 + i) for i in range(4))
    for i, b in enumerate(bcd_add_score(old, delta)):
        mem.wb(DS, 0x2314 + i, b)


def _pickup_spawn_7420(mem) -> None:
    """``1010:7420``: alloc an effect slot and stamp the pickup -- ``x = [2378] + [A278]`` (the
    drift IS added at spawn, 7430), ``y = min([2376], 0xC0)`` (the 743A clamp), kind ``[237A]`` into
    ``+0x26``, and ``sprite = [237A] + 0x46`` (KIND-KEYED, 746A -- the old fixed ``0x48`` was
    L1-blind: L1 only ever drops kind 2, and the L2_full shadow caught kind 1 -> 0x47)."""
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
    if slot == 0xFFFF:
        return
    kind = mem.rw(DS, 0x237A)
    y = mem.rw(DS, 0x2376)
    if y > 0x00C0:
        y = 0x00C0
    for off, val in ((0x00, 1), (0x02, (mem.rw(DS, 0x2378) + mem.rw(DS, 0xA278)) & 0xFFFF),
                     (0x04, y), (0x22, 0), (0x14, 1), (0x16, 5), (0x18, 0), (0x28, 0xFFFF),
                     (0x24, 0), (0x26, kind), (0x08, (kind + 0x46) & 0xFFFF), (0x0A, 0)):
        mem.ww(DS, slot + off, val)


def _death_beat_c054(mem, rec: int) -> None:
    beh = mem.rw(DS, rec + 0x18)
    if beh in _DEATH_NEXT_SCHEDULE:
        mem.ww(DS, 0xA482, _DEATH_NEXT_SCHEDULE[beh])
        mem.ww(DS, 0xA842, 0xA844)
        mem.ww(DS, 0x2376, mem.rw(DS, rec + 0x04))
        mem.ww(DS, 0x2378, mem.rw(DS, rec + 0x02))
        mem.ww(DS, 0x237A, 2)
        _pickup_spawn_7420(mem)
        mem.ww(DS, 0xA47E, (mem.rw(DS, 0xA47E) - 1) & 0xFFFF)
        return
    if beh == 0x93:
        mem.wb(DS, 0x98A8, 1)
        mem.ww(DS, 0xA47E, (mem.rw(DS, 0xA47E) - 1) & 0xFFFF)
        return
    if beh in _DEATH_DEC_ONLY:
        mem.ww(DS, 0xA47E, (mem.rw(DS, 0xA47E) - 1) & 0xFFFF)
        return
    if beh in (0x76, 0x77, 0x78, 0x79):
        raise RecoveryGap(f"C054 leader-group death beat (behavior {beh:#x})",
                          "the C15B escort chain is not recovered")
    return  # C12C: unknown behaviors fall out with no beat


def _bd17_deactivate(mem, rec: int) -> None:
    """``1010:BD17``: deactivate + the per-type/behavior death chain."""
    mem.ww(DS, rec + 0x00, 0)
    rtype = mem.rw(DS, rec + 0x16)
    beh = mem.rw(DS, rec + 0x18)
    if rtype == 4:
        _death_beat_c054(mem, rec)     # BD5C: call C054 ...
        if beh != 0x01:                # ... skip the counter clear for dying-state records
            idx = mem.rw(DS, rec + 0x28)
            if idx != 0xFFFF:
                mem.wb(DS, (0x2078 + idx * 2) & 0xFFFF, 0)
        return
    if rtype == 1:
        mem.ww(DS, rec + 0x16, 2)      # BD56
        return
    if beh in (0x07, 0x08):
        if mem.rw(DS, 0xA970):                     # BDAC: the saturating family-counter decay
            mem.ww(DS, 0xA970, mem.rw(DS, 0xA970) - 1)
        return
    if beh in (0x05, 0x06):
        if mem.rw(DS, 0xA976):                     # BDC4
            mem.ww(DS, 0xA976, mem.rw(DS, 0xA976) - 1)
        return
    if beh == 0x0C:
        if mem.rw(DS, 0xA974):                     # BDB8
            mem.ww(DS, 0xA974, mem.rw(DS, 0xA974) - 1)
        return
    if beh == 0x09:
        # BD7A: while [A972] != 0, sweep the A3B4 sibling list (max 0x1A words, FFFF ends):
        # deactivate every listed record and decrement [A972] per entry.
        if mem.rw(DS, 0xA972) == 0:
            return
        si = 0xA3B4
        for _ in range(0x1A):
            ptr = mem.rw(DS, si)
            si = (si + 2) & 0xFFFF
            if ptr == 0xFFFF:
                return
            mem.ww(DS, ptr, 0)
            mem.ww(DS, 0xA972, (mem.rw(DS, 0xA972) - 1) & 0xFFFF)
        return
    if beh == 0x0A:
        if mem.rw(DS, 0xA97E):                     # BD9E
            mem.ww(DS, 0xA97E, mem.rw(DS, 0xA97E) - 1)
        _weapon_script_tick_837a(mem)              # BDA9 -> AC19 (859E is video-only)
        return


def _player_hit_9e69(mem) -> None:
    """``1010:9E69`` -- the player LIFE beat: gates, sound 3, the BEDC parity throttle, then
    ``A95A -= 1``.  UNDERFLOW (the 9EA3 death-flag chain): ``A95C = 0``; if the ``DS:[9791]`` byte
    is 1 (an invulnerability/refill flag), A95A/A95C refill to 3/0x18 and RETURN (no energy beat);
    otherwise ``DS:2384 = 3`` (the ship-death pose -- the >=3 dying state every pose gate tests) +
    sound 0x19, then the 9EC2 energy beat as on the normal path."""
    if mem.rw(DS, 0xA47C) == 1 or mem.rw(DS, 0x2384) >= 3:
        return
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x03)
    if mem.rw(DS, 0xBEDC) == 0:
        parity = (mem.rb(DS, 0xA362) + 1) & 0x01
        mem.wb(DS, 0xA362, parity)
        if parity != 0:
            return
    hp = (mem.rw(DS, 0xA95A) - 1) & 0xFFFF
    mem.ww(DS, 0xA95A, hp)
    if hp == 0xFFFF:
        # 9EA3: the death-flag chain.
        mem.ww(DS, 0xA95C, 0x0000)
        if mem.rb(DS, 0x9791) == 1:          # 9EA9: the refill flag -> 9ED7 (no death, no beat)
            mem.ww(DS, 0xA95A, 0x0003)
            mem.ww(DS, 0xA95C, 0x0018)
            return
        mem.ww(DS, 0x2384, 0x0003)           # 9EB0: the ship-death pose
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, 0x19)         # 9EBD: the death sound
    _hud_energy_beat_9ec2(mem)               # 9EC2: 61DC (+ the mode-1 511F pair, Tandy-unreachable)


def _bfc7_touch_death(mem, rec: int) -> None:
    """``1010:BFC7``: the touched object's own death -- score, linked-counter completion, the
    C054 beat, sound 0x19, and the exact recovered C037 transition."""
    beh = mem.rw(DS, rec + 0x18)
    if beh == 0x21 and mem.rw(DS, 0x2356) != 4:
        return
    _score_add_5f0d(mem, 0x30 if mem.rw(DS, rec + 0x14) == 1 else 0x60)
    mem.ww(DS, rec + 0x04, clamp_postmove_y_bcb1(mem.rw(DS, rec + 0x04)).y_word)
    idx = mem.rw(DS, rec + 0x28)
    if idx != 0xFFFF:
        cell = (0x2078 + idx * 2) & 0xFFFF
        count = mem.rb(DS, cell)
        if count:
            count -= 1
            mem.wb(DS, cell, count)
            if count == 0:
                mem.ww(DS, 0x2376, mem.rw(DS, rec + 0x04))
                mem.ww(DS, 0x2378, mem.rw(DS, rec + 0x02))
                mem.ww(DS, 0x237A, mem.rb(DS, cell + 1))
                _pickup_spawn_7420(mem)
    _death_beat_c054(mem, rec)
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x19)
    mem.ww(DS, rec + 0x1A, beh)
    mem.ww(DS, rec + 0x18, 0x0001)
    mem.ww(DS, rec + 0x22, 0x0000)
    key = mem.rw(DS, rec + 0x14)
    if key == 1:
        mem.ww(DS, rec + 0x08, 0x0000)
    elif key == 2:
        mem.ww(DS, rec + 0x08, 0x0003)
    else:
        raise RecoveryGap(f"BFC7 death sprite for scan key {key}", "only keys 1/2 in the C042 table")


def _anchor_touch_aa46(mem, rec: int) -> bool:
    x = mem.rw(DS, rec + 0x02)
    if x & 0x8000:
        return False
    pose = mem.rw(DS, 0x2384)
    if pose >= 3:
        return False
    off = (0x214E + pose * 4) & 0xFFFF
    center = view_contact_center_from_offsets_aa46(
        view_x_word=mem.rw(DS, 0x237E), view_y_word=mem.rw(DS, 0x2380),
        offset_x_word=mem.rw(DS, off), offset_y_word=mem.rw(DS, (off + 2) & 0xFFFF))
    mem.ww(DS, 0x95F2, center.x_word)
    mem.ww(DS, 0x95F4, center.y_word)
    return view_contact_rect_test(SimpleNamespace(x_word=x, y_word=mem.rw(DS, rec + 0x04)),
                                  center).hit


def _postmove_bc45(mem, rec: int, tiles: LevelTileContext, *, with_drift: bool) -> None:
    """The shared BC45/BC4B post-move tail every jmp-exiting handler falls into."""
    if with_drift:
        mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + mem.rw(DS, 0xA278)) & 0xFFFF)
    mem.ww(DS, rec + 0x04, clamp_postmove_y_bcb1(mem.rw(DS, rec + 0x04)).y_word)
    a47c = mem.rw(DS, 0xA47C)
    if object_postmove_x_bounds_deactivates_bc4b(mem.rw(DS, rec + 0x02), a47c,
                                                 mem.rw(DS, rec + 0x18)):
        _bd17_deactivate(mem, rec)
        return
    if a47c != 0:
        return
    # BCCB: the anchor-touch scan
    beh = mem.rw(DS, rec + 0x18)
    if mem.rw(DS, rec) != 0 and mem.rw(DS, rec + 0x16) != 5 and beh not in (0, 1):
        key = mem.rw(DS, rec + 0x14)
        touched = False
        if key == 1:
            touched = _anchor_touch_aa46(mem, rec)
        elif key == 2:
            touched = postmove_contact_window_test_aa71(
                SimpleNamespace(x_word=mem.rw(DS, rec + 0x02), y_word=mem.rw(DS, rec + 0x04)),
                PostMoveContactWindow(y_guard_word=mem.rw(DS, 0x2380),
                                      view_x_word=mem.rw(DS, 0x237E),
                                      final_boss_narrow_x=mem.rw(DS, 0xA8C2) == 1)).hit
        if touched:
            if mem.rw(DS, 0xA8C2) != 1:
                _bfc7_touch_death(mem, rec)
            _player_hit_9e69(mem)
    # the 62F6 object-vs-object scan: the walked (moving) record vs the LIVE gameplay pool (player
    # shots are the solid candidates -- the A4EA seed stamps +1E=1; enemy shots are +1E=0 and thus
    # invisible to the scan).  Chains the recovered collision leaves the way BC4B does:
    # 62F6 (who overlaps) -> BEC5 (the reaction family) -> BF25 (damage) -> BFC7 (the FULL death).
    if mem.rw(DS, rec) == 0:
        return                          # died in the BCCB touch above -- nothing left to scan
    # FIELD BINDING (disasm 62F6, caught by the L2 0x8A scanner with +0x0A==0): the pre-gate reads
    # [bp+22] = +0x16 (OFF_DRAW_LAYER == OFF_HAZARD_CLASS) and the wide-window key reads
    # [bp+20] = +0x14 (OFF_OBJECT_TYPE == OFF_SCAN_FLAG) -- NOT +0x0A, which 62F6 never tests.
    hit = object_overlap_scan_62f6(
        scanner_active_word=mem.rw(DS, rec + 0x00),
        scanner_x_word=mem.rw(DS, rec + 0x02), scanner_y_word=mem.rw(DS, rec + 0x04),
        scanner_draw_layer=mem.rw(DS, rec + 0x16),
        scanner_logic_id=mem.rw(DS, rec + 0x18), scanner_object_type=mem.rw(DS, rec + 0x14),
        candidates=read_object_pool(mem, DS, GAMEPLAY_OBJECT_TABLE_BASE,
                                    GAMEPLAY_OBJECT_TABLE_COUNT))
    if hit is None:
        return
    cand = GAMEPLAY_OBJECT_TABLE_BASE + hit * 0x38
    cand_logic = mem.rw(DS, cand + 0x18)
    outcome = bec5_moving_object_outcome(
        candidate_logic_id=cand_logic, a8c2_boss_mode=mem.rw(DS, 0xA8C2) == 1,
        candidate_sprite=mem.rw(DS, cand + 0x08))
    if outcome.kind == "owner_or_unclassified":
        # BF01: the OWNER-LINK reaction -- a candidate whose +0x30 owner pointer is NOT the
        # scanner is ignored entirely; the scanner hitting its OWN linked candidate clears the
        # candidate's +0x1C, then boss mode -> the BF25 damage chain, else the scanner dies the
        # counter:=0 BFC7 death (the same BFB9-normal shape).
        if mem.rw(DS, cand + 0x30) != rec:
            return                                  # BF06: not ours -> no reaction at all
        mem.ww(DS, cand + 0x1C, 0)                  # BF07
        if mem.rw(DS, 0xA8C2) != 1:
            mem.ww(DS, rec + 0x20, 0)               # BF13
            _bfc7_touch_death(mem, rec)
            return
        chain = collision_damage_counter_chain_bf25(mem.rw(DS, rec + 0x20), mem.rw(DS, 0xBEDC),
                                                    True)
        mem.ww(DS, rec + 0x20, chain.new_counter_20)
        if chain.died:
            _bfc7_touch_death(mem, rec)
        else:
            mem.ww(DS, rec + 0x24, 0x0005)          # BF52: the survival hit-react variant
        return
    # the struck candidate's fate (BEC5): variant 2 clears active directly; 5/6 always run BD0D;
    # 7/8/C run BD0D only in A8C2 final-boss mode (else the candidate SURVIVES the hit)
    if bec5_candidate_deactivated(cand_logic, mem.rw(DS, 0xA8C2) == 1):
        if cand_logic == 0x0002:
            mem.ww(DS, cand + 0x00, 0)
        else:
            _bd17_deactivate(mem, cand)
    # the scanner's fate: instant death (counter := 0) or the BF25 damage chain; either death
    # runs the FULL BFC7 beat (score, completion drops, C054, sound 0x19, the dying stamp)
    if outcome.kind == "instant_death":
        mem.ww(DS, rec + 0x20, 0)
        _bfc7_touch_death(mem, rec)
        return
    chain = collision_damage_counter_chain_bf25(mem.rw(DS, rec + 0x20), mem.rw(DS, 0xBEDC),
                                                outcome.enter_at_bf25)
    mem.ww(DS, rec + 0x20, chain.new_counter_20)
    if chain.died:
        _bfc7_touch_death(mem, rec)
    else:
        # survival's hit-react state: BF25's [bp+36] = 5 tail -- DECIMAL 36 = +24h (the variant
        # word), oracle-pinned by the controller-survives case
        mem.ww(DS, rec + 0x24, 0x0005)


def _dispatch(mem, rec: int, tiles: LevelTileContext) -> None:
    rtype = mem.rw(DS, rec + 0x16)
    if rtype == 0:
        return
    if rtype == 1:
        _step_special_pod_1(mem, rec, tiles)   # AD04: the pod step is the whole walk (no BC45)
        return
    if rtype == 5:
        _step_pickup_5(mem, rec)
        _postmove_bc45(mem, rec, tiles, with_drift=True)   # AAC2 exits via BC45
        return
    if rtype == 6:
        r = step_companion_ab10(
            scripted_a47c=mem.rw(DS, 0xA47C), divider_2336=mem.rw(DS, 0x2336),
            anchor_x=mem.rw(DS, 0x237E), anchor_y=mem.rw(DS, 0x2380),
            anchor_sprite=mem.rw(DS, 0x2384),
            anim_table=tuple(mem.rb(DS, 0xA40C + i) for i in range(8)),
            offset_pair_at=lambda spr: (mem.rw(DS, (0xA414 + spr * 4) & 0xFFFF),
                                        mem.rw(DS, (0xA414 + spr * 4 + 2) & 0xFFFF)))
        if r.deactivate:
            mem.ww(DS, rec + 0x00, 0)
        else:
            mem.ww(DS, rec + 0x08, r.sprite)
            mem.ww(DS, rec + 0x02, r.x_word)
            mem.ww(DS, rec + 0x04, r.y_word)
        return
    if rtype in (2, 4):
        # the EFAE prologue mirrors the record position
        mem.ww(DS, 0xD1FE, mem.rw(DS, rec + 0x04))
        mem.ww(DS, 0xD200, mem.rw(DS, rec + 0x02))
        beh = mem.rw(DS, rec + 0x18)
        if beh == 0x1F:
            _step_controller_1f(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # the 8D4F stub exits jmp BC4B
        elif beh == 0x20:
            _step_enemy_20(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # every B73E exit is jmp BC4B
        elif beh == 0x0B:
            _step_shot_0b(mem, rec, tiles)                      # B24D's AD5A/AD60 tail is internal
        elif beh in (0x02, 0x03):
            _step_shot_02(mem, rec, tiles)                      # player shots (AED8's AD60 internal;
            #                                                     EFC4[0x03] aliases the same body)
        elif beh == 0x04:
            _step_child_04(mem, rec, tiles)                     # C237 children (AF60's AD60 internal)
        elif beh == 0x05:
            _step_scroller_05(mem, rec, tiles)                  # AE7D crawler (AD5A/AD60 internal)
        elif beh == 0x01:
            if _step_dying_01(mem, rec):                        # False: the latch-9 morph / BD17 ret
                _postmove_bc45(mem, rec, tiles, with_drift=True)  # BE43/BEAD/BEC2 exit jmp BC45
        elif beh == 0x26:
            _step_morph_26(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 831C/832E/82F3/82FF exit jmp BC45
        elif beh == 0x27:
            _step_scroller_27(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 835D exits jmp BC45
        elif beh == 0x2F:
            _step_bounce_2f(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8820 exits jmp BC45
        elif beh == 0x24:
            _step_spawn_child_sprite(mem, rec, 0x24, 0x001E)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8248 exits jmp BC45
        elif beh == 0x25:
            _step_spawn_child_sprite(mem, rec, 0x25, 0x001A)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8265 exits jmp BC45
        elif beh == 0x29:
            _step_ramp_steer_29(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8721 exits jmp BC45
        elif beh == 0x30:
            _step_spawner_30(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8851 exits jmp BC45
        elif beh in (0x28, 0x2A):
            _step_spawner_28(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8676 exits jmp BC45
        elif beh in (0x90, 0x91):
            _step_anim_spawner_90_91(mem, rec, beh)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8282/8291 exit jmp BC45
        elif beh == 0x10:
            _step_waypoint_10(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B2BC->B2CD exits jmp BC4B
        elif beh == 0x11:
            _step_waypoint_11(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B2C3->B2CD exits jmp BC4B
        elif beh == 0x12:
            _step_waypoint_12(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B2CD exits jmp BC4B
        elif beh in _WAYPOINT_SEED_BY_BEHAVIOR:
            _step_waypoint_seed(mem, rec, beh)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # 8BC8.. -> B2C8 exits jmp BC4B
        elif beh == 0x1A:
            _step_scenery_1a(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # BAD4->BB03 exits jmp BC45 (WITH drift)
        elif beh == 0x19:
            _step_scenery_19(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # BAF0->BB03 exits jmp BC45 (WITH drift)
        elif beh == 0x83:
            _step_scenery_83(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 89FC->BB03 exits jmp BC45
        elif beh == 0x89:
            _step_scenery_89(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # B2A6->BB03 exits jmp BC45 (WITH drift)
        elif beh == 0x8A:
            _step_scenery_8a(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8C1F->B2AC->BB03 exits jmp BC45
        elif beh == 0x2E:
            drift = _step_drift_seeker_2e(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=drift)   # waiting: BC45; seeking: BC4B
        elif beh == 0x46:
            _step_beacon_46(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 87B5 exits jmp BC45 (all paths)
        elif beh == 0x47:
            _step_bounce_emitter_47(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8C37->B2AC->BB03 exits jmp BC45
        elif beh == 0x4E:
            _step_climber_morph_4e(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 88BB's paths all exit jmp BC45
        elif beh == 0x4F:
            _step_strober_4f(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8D20 exits jmp BC45
        elif beh == 0x48:
            _step_shooter_48(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8D44 exits jmp BC45
        elif beh == 0x49:
            _step_burster_49(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8C6A exits jmp BC45
        elif beh == 0x8F:
            _step_pulser_8f(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8769 exits jmp BC45 (all paths)
        elif beh == 0x8C:
            _step_ground_crawler(mem, rec, tiles, 0xFFFF)       # BB80: A952 = -1
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # BB8E body exits jmp BC45 (WITH drift)
        elif beh == 0x8B:
            _step_ground_crawler(mem, rec, tiles, 0x0001)       # BB88: A952 = +1
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # BB8E body exits jmp BC45 (WITH drift)
        elif beh == 0x06:
            _step_mover_06(mem, rec, tiles)                     # AE2C (recovered whole-slot update)
        elif beh == 0x0C:
            _step_marcher_0c(mem, rec, tiles)                   # AE09 (the AD60 tail is internal)
        elif beh == 0x0A:
            _step_tractor_0a(mem, rec, tiles)                   # B1B0 (the AD5A/AD60 tail internal)
        elif beh == 0x14:
            _step_formation_14(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # every B9F0 exit is jmp BC4B
        elif beh == 0x54:
            if not _step_snake_head_54(mem, rec, tiles):        # the BFC7 exit skips BC45
                _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh in (0x57, 0x58):
            if not _step_riser_57(mem, rec, tiles):             # the BFC7 exit skips BC45
                _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x59:
            if not _step_glide_arm_59(mem, rec, tiles):         # the BFC7 exit skips BC45
                _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x5A:
            if not _step_glider_5a(mem, rec, tiles):            # the BFC7 exit skips BC45
                _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x5B:
            # 1010:F2C0: x > 0xB0 (signed) MORPHS to 0x5C and runs its body same-frame
            if _s16(mem.rw(DS, rec + 0x02)) > 0x00B0:
                mem.ww(DS, rec + 0x18, 0x005C)
                mem.ww(DS, rec + 0x08, 0x0073)              # F2CF
                mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) - 4) & 0xFFFF)
            _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x5C:
            # 1010:F2CF: sprite 0x73, x -= 4
            mem.ww(DS, rec + 0x08, 0x0073)
            mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) - 4) & 0xFFFF)
            _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x5D:
            # 1010:F2DB: sprite [2336] + 0x77, x += 8
            mem.ww(DS, rec + 0x08, (mem.rw(DS, 0x2336) + 0x0077) & 0xFFFF)
            mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 8) & 0xFFFF)
            _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x5E:
            if not _step_turner_5e(mem, rec, tiles):            # the BFC7 exit skips BC45
                _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x63:
            _step_hatcher_63(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # F4B3's exits are jmp BC45
        elif beh == 0x5F:
            if not _step_turner_5f(mem, rec, tiles):            # the BFC7 exit skips BC45
                _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x55:
            flying = _step_waiter_55(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=not flying)  # wait: BC45; fly: BC4B
        elif beh == 0x56:
            if not _triple_afd8_or_die_f194(mem, rec, tiles):   # the BFC7 exit skips BC45
                _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x86:
            _step_launcher_86(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # F0EE's exits are jmp BC45
        elif beh == 0x87:
            _step_pulser_87(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 878C's exits are jmp BC45
        elif beh == 0x13:
            _step_controller_13(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # 8D54 exits jmp BC4B
        elif beh == 0x1C:
            _step_controller_1c(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # the 8D4F stub exits jmp BC4B
        elif beh == 0x15:
            _step_controller_15(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # the 8D4F stub exits jmp BC4B
        elif beh in (0x16, 0x17):
            _step_diver_16_17(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B930 exits jmp BC4B
        elif beh == 0x18:
            _step_waypoint_18(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B9CA/B9EE loop to BC4B
        elif beh == 0x1D:
            _step_formation_1d(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B86D exits jmp BC4B
        elif beh == 0x1E:
            _step_patrol_1e(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B909 exits jmp BC4B
        elif beh == 0x31:
            # 1010:88AA: sprite = 0x2E, x += 3, jmp BC45 -- a plain right-scroller
            mem.ww(DS, rec + 0x08, 0x002E)
            mem.ww(DS, rec + 0x02, (mem.rw(DS, rec + 0x02) + 3) & 0xFFFF)
            _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x32:
            _step_bouncer_32(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 88B6's paths all exit jmp BC45
        elif beh == 0x33:
            _step_bouncer_33(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 88CF exits jmp BC45
        elif beh in (0x35, 0x22):
            # the EFC4 table aliases 0x22 (the planet BOSS the 0x21 transform creates) and 0x35
            # to the SAME B3DF body (zoo-xref-confirmed; the riser docstring names both)
            _step_riser_35(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # B3DF exits jmp BC45 (both paths)
        elif beh == 0x36:
            _step_riser_36(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # B3CC exits jmp BC45 (both paths)
        elif beh == 0x37:
            _step_patroller_37(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8982 exits jmp BC45 (all paths)
        elif beh == 0x38:
            _step_edge_runner_38(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 89FF exits jmp BC45
        elif beh == 0x34:
            _step_dropper_34(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 88E8 exits jmp BC45 (all paths)
        elif beh == 0x39:
            _step_faller_39(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8A23 exits jmp BC45 (all paths)
        elif beh == 0x3A:
            _step_hover_3a(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8A55 exits jmp BC45 (both paths)
        elif beh == 0x3B:
            _step_glitter_3b(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8A7E exits jmp BC45
        elif beh == 0x3C:
            _step_lurker_3c(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8AA4 exits jmp BC45 (both paths)
        elif beh == 0x3D:
            _step_bounce_sprite_3d(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8AC7 -> 88CF exits jmp BC45
        elif beh == 0x21:
            _step_wave_driver_21(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B556's phased paths exit BC4B
        elif beh == 0x23:
            _step_wave_enemy_23(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B690's paths exit BC4B
        elif beh == 0x2C:
            _step_wave_diver_2c(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B556's phased paths exit BC4B
        elif beh == 0x2B:
            _step_missile_2b(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8715->8744 exits jmp BC45
        elif beh == 0x40:
            _step_jitter_40(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8B3B exits jmp BC45 (all paths)
        elif beh == 0x68:
            _step_jitter_emitter_68(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8AF9's exits are jmp BC45
        elif beh == 0x69:
            _step_jitter_creeper_69(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8B80's exits are jmp BC45
        elif beh == 0x2D:
            _step_beacon_2d(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 87AF->87B5 exits jmp BC45
        elif beh == 0x64:
            _step_strider_64(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # F4FE exits jmp BC45
        elif beh == 0x42:
            _step_bobber_42(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8BF8 exits jmp BC45 (both paths)
        elif beh == 0x4B:
            _step_latch_bouncer_4b(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8C6D / 88CF exit jmp BC45
        elif beh == 0x4C:
            drift = _step_glide_4c(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=drift)   # waiting: BC45; gliding: BC4B
        elif beh == 0x4D:
            drift = _step_glide_morph_4d(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=drift)   # wait/morph: BC45; gliding: BC4B
        elif beh == 0x3E:
            _step_arm_missile_3e(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8ADD exits jmp BC45 (all paths)
        elif beh in (0x3F, 0x60):
            # 1010:8AF6: jmp 8744 -- the whole body IS the shared steer tail; EFC4[0x60] points
            # STRAIGHT at 8744 (the L3 zoo aliases the same body)
            _steer_missile_tail_8744(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8744 exits jmp BC45 (both paths)
        elif beh == 0x52:
            # 1010:8D23: the phase-1 outro object -- a NO-OP body (jmp BC45; the postmove drifts it)
            _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x53:
            # 1010:8D26: the A3EE level-end outro objects -- sprite = [96D2 + (2328 & ~1)] + rec[+0x36]
            # (the same 96D2 anim table 0x30 uses, clocked by 2328 word-aligned), then jmp BC45.
            anim = mem.rw(DS, (0x96D2 + (mem.rw(DS, 0x2328) & 0xFFFE)) & 0xFFFF)
            mem.ww(DS, rec + 0x08, (anim + mem.rw(DS, rec + 0x36)) & 0xFFFF)
            _postmove_bc45(mem, rec, tiles, with_drift=True)
        elif beh == 0x7A:
            _step_diver_7a(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # 8760/8766 exit jmp BC45
        elif beh in (0x7D, 0x7E):
            _step_controller_7d(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # the 8D4F stub exits jmp BC4B
        elif beh == 0x81:
            _step_morpher_81(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # the 8D57 stub exits jmp BC4B
        elif beh == 0x93:
            _step_stepper_93(mem, rec, tiles)
            if mem.rw(DS, rec + 0x36) >= 0x64:                  # 8D64: the +0x36 death counter
                _bfc7_touch_death(mem, rec)                     # 8D6D
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # 8D6A/8D70: jmp BC4B
        elif beh in (0x6B, 0x6C, 0x6D):
            _step_yseeker_6b6c6d(mem, rec,
                                 {0x6B: 0x50, 0x6C: 0x60, 0x6D: 0x70}[beh],
                                 {0x6B: 0x011F, 0x6D: 0x0124}.get(beh))
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # all paths exit jmp BC45
        elif beh == 0x8E:
            _step_crawler_8e(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # BBB2 tail exits jmp BC45
        elif beh == 0x88:
            _step_shooter_88(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # F16A/F172 exit jmp BC45
        elif beh == 0x6F:
            _step_riser_6f(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # F5A9/F5D9 exit jmp BC45
        elif beh == 0x70:
            _step_riser_70(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # F5D9 exits jmp BC45
        elif beh in (0x00, 0x0D, 0x0E, 0x82):
            # the EFC4 table points these straight at BC45 -- there is NO per-behavior body, the
            # handler IS the drift postmove.  Dispatching them = the plain drift (with_drift=True).
            _postmove_bc45(mem, rec, tiles, with_drift=True)
        else:
            raise RecoveryGap(f"behavior {beh:#04x} (record {rec:04X})",
                              "no native handler registered -- recover it before walking")
        return
    raise RecoveryGap(f"object type {rtype} (record {rec:04X})",
                      "no native type handler registered -- recover it before walking")


#: the A3EE level-end outro spawn table (4 entries x (x, y, sprite) -- the sprite also seeds +0x36,
#: the base the 0x53 handler animates from).  Static data, read from the image at arm time.
LEVEL_END_OUTRO_TABLE_A3EE = 0xA3EE


def run_level_end_arm_a680(mem) -> None:
    """The ``1010:A680`` LEVEL-END ARM (the 0xEA0 scroll milestone's memory actions, live-traced):
    ``A47C = 1`` (the outro script arms -- the scroll gate then holds), the ``62AA`` sweep (sound 8;
    every remaining live on-screen enemy -- x <= 0xE0, type 4, logic not 0/1 -- has its HP zeroed
    and dies the full BFC7 death, score and all), then the FOUR A3EE outro objects spawn via 7524
    (behavior 0x53, +0x14=2/+0x16=4/+0x28=FFFF, position + sprite/+0x36 from the table)."""
    mem.ww(DS, 0xA47C, 0x0001)                              # A6B9
    # 62AA: the field sweep
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x08)
    for cx in range(EFFECT_SLOTS, 0, -1):
        rec = mem.rw(DS, (EFFECT_TABLE_32CA + cx * 2) & 0xFFFF)
        if not rec or mem.rw(DS, rec) == 0:
            continue
        if mem.rw(DS, rec + 0x02) > 0x00E0:
            continue
        if mem.rw(DS, rec + 0x16) != 4:
            continue
        if mem.rw(DS, rec + 0x18) in (0x0000, 0x0001):
            continue
        mem.ww(DS, rec + 0x20, 0x0000)                      # 62EE: HP = 0
        _bfc7_touch_death(mem, rec)                         # 62F3: jmp BFC7
    # A6C2..A6F8: the four outro spawns
    si = LEVEL_END_OUTRO_TABLE_A3EE
    for _ in range(4):
        slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
        if slot != 0xFFFF:
            mem.ww(DS, slot + 0x00, 1)
            mem.ww(DS, slot + 0x14, 0x0002)
            mem.ww(DS, slot + 0x16, 0x0004)
            mem.ww(DS, slot + 0x18, 0x0053)
            mem.ww(DS, slot + 0x28, 0xFFFF)
            mem.ww(DS, slot + 0x02, mem.rw(DS, si))
            mem.ww(DS, slot + 0x04, mem.rw(DS, (si + 2) & 0xFFFF))
            spr = mem.rw(DS, (si + 4) & 0xFFFF)
            mem.ww(DS, slot + 0x08, spr)
            mem.ww(DS, slot + 0x36, spr)
        si = (si + 6) & 0xFFFF


#: the two outro autopilot target pairs (x, y): phase 1 flies to A358, phase 2 to A35C.
OUTRO_TARGET_A358, OUTRO_TARGET_A35C = 0xA358, 0xA35C


def run_outro_script_99f6(mem) -> int:
    """The ``99F6`` A47C-script dispatch for the LEVEL-END OUTRO phases (1..3), one frame.

    Returns this frame's synthetic 98BE input bits (0 when the script isn't steering) -- the caller
    feeds them to the player stage IN PLACE of the keyboard, exactly as the original's scripted
    input overrides the poll.  Phase 1 (``9A78``): autopilot to the A358 target; on arrival
    ``A47C = 2`` + the A39A/A39C reset + the 0x52 outro-object spawn ([9788] = its slot) and the
    script RE-DISPATCHES the same frame (the ``jmp 99F6`` tail).  Phase 2 (``9A3E``): the recovered
    scripted-move counters step, then autopilot to the A35C target; arrival -> ``A47C = 3``, same
    re-dispatch.  Phase 3 (``9A16``, the recovered pure handler): input := 8 (the fly-off) while the
    A97C/A95A/A95C counters settle; at the settled state ``A47C = 4`` -- the 9B47 check then raises
    ``A344`` (the SCRIPTED transition the exit detector already fires on)."""
    while True:
        a47c = mem.rw(DS, 0xA47C)
        if a47c in (1, 2):
            if a47c == 2:
                new_c, new_a = step_scripted_move_counters_9a3e(
                    mem.rw(DS, 0x2384), mem.rw(DS, 0xA39C), mem.rw(DS, 0xA39A))
                mem.ww(DS, 0xA39C, new_c)
                mem.ww(DS, 0xA39A, new_a)
                si = OUTRO_TARGET_A35C
            else:
                si = OUTRO_TARGET_A358
            bits = outro_autopilot_bits_9ad1(
                mem.rw(DS, 0x237E), mem.rw(DS, 0x2380),
                mem.rw(DS, si), mem.rw(DS, (si + 2) & 0xFFFF))
            mem.ww(DS, 0x98BE, bits)
            if bits:
                return bits
            mem.ww(DS, 0xA47C, a47c + 1)                    # 9A86: inc [A47C]
            if a47c + 1 == 2:                               # 9A8A/9A94: the phase-1 arrival extras
                mem.ww(DS, 0xA39A, 0)
                mem.ww(DS, 0xA39C, 0)
                slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
                if slot != 0xFFFF:                          # the 0x52 outro object at (0x20, 0x58)
                    for off, val in ((0x00, 1), (0x16, 4), (0x18, 0x52), (0x14, 2),
                                     (0x28, 0xFFFF), (0x08, 0x0F), (0x02, 0x20), (0x04, 0x58)):
                        mem.ww(DS, slot + off, val)
                    mem.ww(DS, 0x9788, slot)
            continue                                        # 9ACE/9A91: jmp 99F6 -- re-dispatch
        if a47c == 3:
            bits, new_a97c, new_a95a, new_a95c, advanced = step_a47c_handler_9a16(
                mem.rw(DS, 0xA97A), mem.rw(DS, 0xA97C), mem.rw(DS, 0xA95A), mem.rw(DS, 0xA95C),
                mem.rw(DS, 0x2384), mem.rw(DS, 0xBDAC), mem.rb(DS, 0x98C0))
            mem.ww(DS, 0xA97C, new_a97c)
            mem.ww(DS, 0xA95A, new_a95a)
            mem.ww(DS, 0xA95C, new_a95c)
            mem.ww(DS, 0x98BE, bits)
            if advanced:
                mem.ww(DS, 0xA47C, 0x0004)                  # -> the 9B47 A344 raise next check
            return bits
        return 0


def run_behavior_walk_a9d3(mem, tiles: LevelTileContext) -> None:
    """Run the whole ``A9D3..AA25`` object behavior walk natively over ``mem`` (in place)."""
    if mem.rw(DS, 0xA8C2) == 1:
        raise RecoveryGap("the A8C2 leader-group per-frame tick (1010:F797)",
                          "not recovered; only the leader-group planet sets A8C2")
    for cx in range(EFFECT_SLOTS, 0, -1):
        tick = (mem.rw(DS, 0x2340) + 1) & 0xFFFF
        mem.ww(DS, 0x2340, 0 if tick >= TICK_2340_PERIOD else tick)
        rec = mem.rw(DS, (EFFECT_TABLE_32CA + cx * 2) & 0xFFFF)
        if mem.rw(DS, rec) != 0:
            _dispatch(mem, rec, tiles)
    mem.ww(DS, 0x2346, 0)
    for cx in range(GAMEPLAY_SLOTS, 0, -1):
        rec = mem.rw(DS, (GAMEPLAY_TABLE_8D12 + cx * 2) & 0xFFFF)
        if mem.rw(DS, rec) != 0:
            _dispatch(mem, rec, tiles)
