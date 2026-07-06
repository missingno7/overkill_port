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
    bb03_bounce_boundary,
    ground_crawler_should_spawn,
    ground_crawler_sprite_8b_8c,
    scenery_19_should_emit,
    scenery_89_should_emit,
    step_scenery_emitter_sprite_19,
    step_scenery_emitter_sprite_89,
    step_scenery_sprite_ramp_1a,
)
from overkill.recovered.systems.tilemap import compute_tile_probe_5073
from overkill.recovered.domain.tilemap import TileProbeInput
from overkill.recovered.systems.frame_loop import (
    canned_random_next_4d95,
    enemy_shot_stamp_7476,
    enemy_spawn_stamp_8209,
    pickup_heal_9d67,
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
    object_delta_steer_5e42,
    object_target_seek_step_5db2,
)
from overkill.recovered.systems.objects import (
    child_spawn_seed_c237,
    child_spawn_sound_c237,
    child_spawn_throttle_c237,
    object_update_aed8,
    object_update_af60,
    object_update_b24d,
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
    direction = mem.rw(DS, rec + 0x06)
    y = mem.rw(DS, rec + 0x04)
    flip = bb03_bounce_boundary(direction, y)
    if flip is not None:
        mem.ww(DS, rec + 0x06, flip)
        return
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


def _step_scenery_89(mem, rec: int, tiles: LevelTileContext) -> None:
    mem.ww(DS, rec + 0x08, step_scenery_emitter_sprite_89(mem.rw(DS, 0x233C)))
    if scenery_89_should_emit(mem.rw(DS, 0x232C)):
        # the SAME BAE1 dir=4 emit as 0x19 (B2B6 call BAE1); parent behavior 0x89 (& 0xF == 9).
        saved_dir = mem.rw(DS, rec + 0x06)
        mem.ww(DS, rec + 0x06, SCENERY_19_EMIT_DIRECTION)
        _spawn_child_c237(mem, rec, 0x89)
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


def _step_child_04(mem, rec: int, tiles: LevelTileContext) -> None:
    """Behavior 0x04 (``1010:AEBF``, EFAE logic_id 4) -- the C237-spawned child. On the ``planet !=
    0`` path (DS:2356 != 0, always true on L1: 2356==1) AEBF falls straight into AF60 with B250
    pushed as the return -- a thin adapter around the whole-AF60 update (double 2px step + the
    shared B250 contact + AD5A/ADC9 -> AD60 tail).  Contact triggers the single 9E19 fan-out
    (logic_id 4 != 3, so exactly one call per contact_fanout_count) exactly like behavior 0x0B's
    shot-hit beat."""
    if mem.rw(DS, 0x2356) == 0:
        raise RecoveryGap("behavior 0x04 planet-0 direction dispatch (1010:AECD)",
                          "the AEE4 8px-step / direction==4 special case is not recovered "
                          "(only the AF60 double-step path used on planets 1-5)")
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


def _pickup_collect_aad3(mem, rec: int) -> None:
    """``1010:AAD3``: the type-5 pickup COLLECT -- pose gate, sound 7, score +0x20 (5F0D), the
    ``+0x26``-keyed AB00 kind dispatch (kind 2 = the 9D67 shield/HP heal -- the only demo-witnessed
    kind), then the BD17 deactivate of the pickup record (the AB0C tail)."""
    if mem.rw(DS, 0x2384) >= 3:             # AAD3's own pose gate (dying pose -> no collect)
        return
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x07)            # AAE2: sound 7 (kind 2 then overwrites with 0x1C)
    _score_add_5f0d(mem, 0x20)
    kind = mem.rw(DS, rec + 0x26)
    if kind != 2:
        raise RecoveryGap(f"pickup kind {kind} collect (the AB00 index-{kind} entry, record {rec:04X})",
                          "only kind 2 (1010:9D67, the shield/HP heal) is demo-witnessed + recovered;"
                          " kinds 0/1/3/4 (AF44/9D4D/62AA/9DB9) are not")
    # 9D67: sound 0x1C + the A95A/A95C heal + ONE 9EC2 HUD-energy beat.
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x1C)
    a95a, a95c = pickup_heal_9d67(mem.rw(DS, 0xA95A), mem.rw(DS, 0xA95C))
    mem.ww(DS, 0xA95A, a95a)
    mem.ww(DS, 0xA95C, a95c)
    _hud_energy_beat_9ec2(mem)
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
    """``1010:7420``: alloc an effect slot and stamp the pickup at (``2378``, ``2376``), kind
    ``237A`` (the f86 write-trace pinned every field)."""
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
    if slot == 0xFFFF:
        return
    for off, val in ((0x00, 1), (0x02, mem.rw(DS, 0x2378)), (0x04, mem.rw(DS, 0x2376)),
                     (0x22, 0), (0x14, 1), (0x16, 5), (0x18, 0), (0x28, 0xFFFF),
                     (0x24, 0), (0x26, mem.rw(DS, 0x237A)), (0x08, 0x48), (0x0A, 0)):
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
    if beh in (0x05, 0x07, 0x08, 0x0A, 0x0C):
        raise RecoveryGap(f"BD17 logic-keyed decay beat (behavior {beh:#x})",
                          "the BDAC/BDB8/BDC4/BD9E A970-family decays are not composed here")


def _player_hit_9e69(mem) -> None:
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
        raise RecoveryGap("player health exhausted (the 9EA3 death-flag chain)",
                          "A95C=0 + [9791] gate + 2384=3 ship-death path not composed yet")
    _energy_redraw_61dc(mem)


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
    hit = object_overlap_scan_62f6(
        scanner_active_word=mem.rw(DS, rec + 0x00),
        scanner_x_word=mem.rw(DS, rec + 0x02), scanner_y_word=mem.rw(DS, rec + 0x04),
        scanner_draw_layer=mem.rw(DS, rec + 0x0A),
        scanner_logic_id=mem.rw(DS, rec + 0x18), scanner_object_type=mem.rw(DS, rec + 0x16),
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
        raise RecoveryGap(f"BEC5 owner-link/unclassified collision (record {rec:04X}, "
                          f"candidate logic {cand_logic:#x})",
                          "the +0x30 owner-pointer reaction is not recovered")
    # the struck candidate's fate (BEC5): variant 2 clears active directly; 5/6/7/8/C run BD0D
    if bec5_candidate_deactivated(cand_logic):
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
        elif beh == 0x02:
            _step_shot_02(mem, rec, tiles)                      # player shots (AED8's AD60 internal)
        elif beh == 0x04:
            _step_child_04(mem, rec, tiles)                     # C237 children (AF60's AD60 internal)
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
        elif beh == 0x11:
            _step_waypoint_11(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B2C3->B2CD exits jmp BC4B
        elif beh == 0x12:
            _step_waypoint_12(mem, rec)
            _postmove_bc45(mem, rec, tiles, with_drift=False)   # B2CD exits jmp BC4B
        elif beh == 0x1A:
            _step_scenery_1a(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # BAD4->BB03 exits jmp BC45 (WITH drift)
        elif beh == 0x19:
            _step_scenery_19(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # BAF0->BB03 exits jmp BC45 (WITH drift)
        elif beh == 0x89:
            _step_scenery_89(mem, rec, tiles)
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # B2A6->BB03 exits jmp BC45 (WITH drift)
        elif beh == 0x8C:
            _step_ground_crawler(mem, rec, tiles, 0xFFFF)       # BB80: A952 = -1
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # BB8E body exits jmp BC45 (WITH drift)
        elif beh == 0x8B:
            _step_ground_crawler(mem, rec, tiles, 0x0001)       # BB88: A952 = +1
            _postmove_bc45(mem, rec, tiles, with_drift=True)    # BB8E body exits jmp BC45 (WITH drift)
        else:
            raise RecoveryGap(f"behavior {beh:#04x} (record {rec:04X})",
                              "no native handler registered -- recover it before walking")
        return
    raise RecoveryGap(f"object type {rtype} (record {rec:04X})",
                      "no native type handler registered -- recover it before walking")


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
