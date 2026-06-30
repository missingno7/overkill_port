"""Native object-update **coverage gate** -- the §1.2/§1.3 scaffold.

This generalises the per-routine ``verify_native_*`` probes into the seed of the
VM-free state producer: it walks a real gameplay demo and, at the per-slot
behaviour dispatch (EFAE, ``1010:EFAE`` -> ``CS:[0xEFC4 + logic_id*2]``), classifies
**every** per-slot object update as either

  * **native** -- a recovered pure whole-slot transform is wired for this
    ``logic_id``, and it is checked byte-exact against the VM at the handler's
    return (the produced-vs-VM gate, same mechanism as the AE09 probe), or
  * **fallback** -- no pure transform yet; counted so the report shows the next
    promotion targets (the hottest fallback ``logic_id`` buckets).

So one run yields three things at once: a live zero-divergence **gate** for the
handlers we have made native, a **coverage %** (how much of the object-update we
can already produce VM-free), and a prioritised **backlog** (which ``logic_id`` to
recover next).  Wire a new pure transform = add one entry to ``NATIVE_HANDLERS``.

Scope today: the EFAE family (AA2B draw-layer-2/4 behaviours -- the bulk of
gameplay/effect objects).  AA2B's other first-level branches are a separate,
smaller dispatch to fold in later.  One native handler is wired: AE09
(``logic_id`` 0Ch), the proven complete per-slot transform.

Usage:
    python -m overkill.probes.verify_native_object_update [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.domain.movement import MovementTarget
from overkill.recovered.systems.movement import object_target_seek_step_5db2
from overkill.recovered.systems.objects import (
    object_update_ae09,
    object_update_aed8,
    object_update_b24d,
    object_update_b2cd,
    object_update_b86d,
    object_update_b9f0,
    object_update_be3c,
)
from overkill.recovered.views.object_slots import (
    OFF_ACTIVE_WORD,
    OFF_DIRECTION_OR_STEP,
    OFF_HAZARD_CLASS,
    OFF_LOGIC_ID,
    OFF_MOVE_DELTA_X,
    OFF_MOVE_DELTA_Y,
    OFF_MOVE_STEP_ERROR,
    OFF_SCAN_ENABLE_OR_SOLID,
    OFF_SCAN_FLAG,
    OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE,
    OFF_TARGET_X,
    OFF_TARGET_Y,
    OFF_X,
    OFF_Y,
)

CS = 0x1010
EFAE_IP = 0xEFAE              # per-slot behaviour dispatcher
EFC4_TABLE = 0xEFC4          # CS:[EFC4 + logic_id*2] -> handler entry IP
# AE09 tile-probe inputs (see verify_native_object_update_ae09 for the derivation).
AE09_IP = 0xAE09
RENDER_MODE_BDAC = 0xBDAC
TILE_PROBE_ORIGIN_X = 0x234E
TILE_PROBE_ROW_BASE = 0x2350
TILE_CLASS_TABLE = 0xC3AA
TILE_PLANE_SEGMENT_PTR = 0x9592

# AED8 (logic_id 0x02) inputs.  AED8 RETs via the AD60 tail (like AE09), so its boundary is the
# return address.  Its B250 contact test uses the same DS:237E/2380 view box as B86D's B8F8.
AED8_IP = 0xAED8
AED8_REF_BOX_X = 0x237E           # DS:237E view-target box X (B250 overlap reference)
AED8_REF_BOX_Y = 0x2380          # DS:2380 view-target box Y
AD60_A278 = 0xA278               # DS:A278 added to X on the AD5A (no-contact) tail

# B9F0 (logic_id 0x14) DS-global read offsets (the movement logic + its constants live in the pure
# object_update_b9f0; this adapter only projects these inputs from the VM).  B9F0 tail-jumps to BC4B.
B9F0_IP = 0xB9F0
B9F0_A482 = 0xA482               # DS:A482; == A4E4h enters the movement paths, else sprite-refresh
B9F0_FRAME_233C = 0x233C         # DS:233C global frame -> the BA67 sprite refresh
B9F0_DELTA_Y_2342 = 0x2342       # DS:2342 global Y delta added to target_y (+32)
B9F0_DELTA_X_2346 = 0x2346       # DS:2346 global X delta added to target_x (+34)
B9F0_COUNTER_A47E = 0xA47E       # DS:A47E level counter (< 6 -> BA5A helper fires)
B9F0_DIFFICULTY_BEDC = 0xBEDC    # DS:BEDC difficulty -> periodic-helper tick mask
B9F0_TICK_2340 = 0x2340          # DS:2340 tick counter for the periodic BA5A helper

# B86D (logic_id 0x1D) fall-through inputs.  B86D tail-jumps to the shared BC4B post-move
# stage rather than RETurning, so its slot-write boundary is a fixed IP, not a return address.
B86D_IP = 0xB86D
BC4B_IP = 0xBC4B
B86D_PHASE_A47E = 0xA47E          # DS:A47E early-global guard (<=2 -> B8F8 edge-steer)
B86D_PHASE_A7A0 = 0xA7A0          # DS:A7A0 phase gate (<0x28 -> A7A0 mask/B729 block)
B86D_VERTICAL_DELTA_2342 = 0x2342  # DS:2342 global vertical delta (X += -delta)
B86D_PHASE_2328 = 0x2328          # DS:2328 phase word (==7 -> +1 X nudge)
B86D_REF_BOX = 0x237C            # DS:237C view-anchor box (5E1B target: B86D B8F8 + B9F0 BA5A)
STEP_MODE_2312 = 0x2312          # DS:2312 5E42 step mode (==3 -> 3px else 2px)
DIRECTION_TABLE_A348 = 0xA348    # DS:A348 16-byte direction-bits -> direction map (5E42 + 5DB2)


@dataclass
class _Pending:
    """An armed native prediction awaiting the handler's slot-write boundary.

    ``exit_ip`` is the IP at which the slot is compared: a dynamic return address for a
    RETurning handler (AE09), or a fixed tail-jump target for a handler that hands off to a
    shared post-move stage (B86D -> BC4B).
    """

    ss: int
    bp: int
    exit_ip: int
    predicted: tuple
    read_post: Callable  # (cpu, ss, bp) -> tuple of post-frame fields
    logic_id: int = -1   # filled in at arm time for clean attribution


def _read_slot_6tuple(cpu, ss: int, bp: int) -> tuple:
    """The six post-frame slot fields the gate compares: substate, direction, sprite, x, y, active."""
    return (
        cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF),
    )


@dataclass(frozen=True)
class NativeHandler:
    """A wired pure whole-slot transform for one ``logic_id``.

    ``entry_ip`` is the handler the EFC4 table dispatches to; ``arm`` captures the
    slot pre-state at that IP, predicts the post-state via the pure transform, and
    returns a :class:`_Pending` (or ``None`` to skip an unmodelled sub-path).
    """

    logic_id: int
    label: str
    entry_ip: int
    arm: Callable  # (cpu, class_table_cache) -> _Pending | None


def _read_level_tile_context(cpu, ds: int, class_table_cache: dict) -> LevelTileContext:
    """Project the DS tile-probe inputs into a LevelTileContext (shared by AE09 + AED8)."""
    class_table = class_table_cache.get(ds)
    if class_table is None:
        class_table = tuple(cpu.mem.rb(ds, (TILE_CLASS_TABLE + i) & 0xFFFF) for i in range(0x100))
        class_table_cache[ds] = class_table
    return LevelTileContext(
        origin_x_word=cpu.mem.rw(ds, TILE_PROBE_ORIGIN_X),
        row_base_word=cpu.mem.rw(ds, TILE_PROBE_ROW_BASE),
        tile_plane=LazyBytes(cpu.mem, cpu.mem.rw(cpu.s.cs & 0xFFFF, TILE_PLANE_SEGMENT_PTR), 0, 0x10000),
        class_table=class_table,
    )


def _arm_ae09(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict AE09 (logic_id 0Ch) -- identical to the AE09 probe."""
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    substate = cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    direction = cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
    x = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    active = cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF)
    draw_layer = cpu.mem.rw(ss, (bp + OFF_HAZARD_CLASS) & 0xFFFF)
    logic_id = cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
    bdac = cpu.mem.rw(ds, RENDER_MODE_BDAC)
    tiles = _read_level_tile_context(cpu, ds, class_table_cache)
    p = object_update_ae09(substate, direction, x, y, active, draw_layer, logic_id, bdac == 0x0001, tiles)
    predicted = (p.substate, p.direction_or_step, p.sprite_or_state, p.x_word, p.y_word, p.active_word)
    ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)  # AE09 RETs to its caller
    return _Pending(ss=ss, bp=bp, exit_ip=ret_addr, predicted=predicted, read_post=_read_slot_6tuple)


def _arm_b86d(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict B86D (logic_id 0x1D) -- all three branches via the pure object_update_b86d.

    B86D tail-jumps to BC4B, so compare the movement half at the BC4B handoff.  This adapter only
    projects the slot fields + the B86D DS globals from the VM and calls the canonical pure system; the
    branch logic (B8F8 edge-steer / A7A0 5DB2 seek / fall-through drift) lives in object_update_b86d.
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    table = tuple(cpu.mem.rb(ds, (DIRECTION_TABLE_A348 + i) & 0xFFFF) for i in range(16))
    r = object_update_b86d(
        cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF),
        cpu.mem.rw(ds, B86D_PHASE_A47E),
        cpu.mem.rw(ds, B86D_PHASE_A7A0),
        cpu.mem.rw(ds, (B86D_REF_BOX + OFF_X) & 0xFFFF),
        cpu.mem.rw(ds, (B86D_REF_BOX + OFF_Y) & 0xFFFF),
        cpu.mem.rw(ds, (B86D_REF_BOX + OFF_SCAN_FLAG) & 0xFFFF),
        cpu.mem.rw(ds, B86D_VERTICAL_DELTA_2342),
        cpu.mem.rw(ds, B86D_PHASE_2328),
        cpu.mem.rw(ds, STEP_MODE_2312),
        table,
    )
    predicted = (r.substate, r.direction_or_step, r.sprite_or_state, r.x_word, r.y_word, r.active_word)
    return _Pending(ss=ss, bp=bp, exit_ip=BC4B_IP, predicted=predicted, read_post=_read_slot_6tuple)


def _arm_aed8(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict AED8 (logic_id 0x02): AEE4 step + B250 contact + AD60, compared at AED8's RET.

    AED8 RETs through the AD60 tail (like AE09), so the boundary is the return address.  Returns None
    for the timer-expired death and out-of-range-direction sub-paths object_update_aed8 leaves unmodelled.
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    substate = cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    direction = cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
    x = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    active = cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF)
    sprite = cpu.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF)
    substate_1e = cpu.mem.rw(ss, (bp + OFF_SCAN_ENABLE_OR_SOLID) & 0xFFFF)
    draw_layer = cpu.mem.rw(ss, (bp + OFF_HAZARD_CLASS) & 0xFFFF)
    logic_id = cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
    bdac = cpu.mem.rw(ds, RENDER_MODE_BDAC)
    upd = object_update_aed8(
        substate, direction, x, y, active, substate_1e, draw_layer, logic_id,
        cpu.mem.rw(ds, AED8_REF_BOX_X), cpu.mem.rw(ds, AED8_REF_BOX_Y), cpu.mem.rw(ds, AD60_A278),
        bdac == 0x0001, _read_level_tile_context(cpu, ds, class_table_cache),
    )
    if upd is None:
        return None
    # AED8 leaves sprite + direction untouched.
    predicted = (upd.substate, direction, sprite, upd.x_word, upd.y_word, upd.active_word)
    ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
    return _Pending(ss=ss, bp=bp, exit_ip=ret_addr, predicted=predicted, read_post=_read_slot_6tuple)


def _arm_b24d(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict B24D (logic_id 0x0B): 5E42 steer + B250 contact + AD60, compared at B24D's RET.

    B24D is reached via the EFC4 jump and RETs through the shared AD60 tail (like AED8), so the boundary
    is the return address.  Only the four movement fields change (direction, x, y, active); substate and
    sprite are passed through.  This adapter projects the slot fields + B24D's DS globals and calls the
    canonical pure object_update_b24d.  The contact/out-of-bounds death paths route to BD17 (no RET), so
    the gate naturally only compares the survive path."""
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    substate = cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    sprite = cpu.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF)
    bdac = cpu.mem.rw(ds, RENDER_MODE_BDAC)
    table = tuple(cpu.mem.rb(ds, (DIRECTION_TABLE_A348 + i) & 0xFFFF) for i in range(16))
    upd = object_update_b24d(
        x_word=cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
        y_word=cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
        direction_or_step=cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
        active_word=cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF),
        substate_1e=cpu.mem.rw(ss, (bp + OFF_SCAN_ENABLE_OR_SOLID) & 0xFFFF),
        move_delta_x=cpu.mem.rw(ss, (bp + OFF_MOVE_DELTA_X) & 0xFFFF),
        move_delta_y=cpu.mem.rw(ss, (bp + OFF_MOVE_DELTA_Y) & 0xFFFF),
        move_step_error=cpu.mem.rw(ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF),
        step_mode=cpu.mem.rw(ds, STEP_MODE_2312),
        direction_table=table,
        draw_layer=cpu.mem.rw(ss, (bp + OFF_HAZARD_CLASS) & 0xFFFF),
        logic_id=cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF),
        ref_box_x=cpu.mem.rw(ds, AED8_REF_BOX_X),
        ref_box_y=cpu.mem.rw(ds, AED8_REF_BOX_Y),
        a278=cpu.mem.rw(ds, AD60_A278),
        tile_probe_suppressed=bdac == 0x0001,
        tiles=_read_level_tile_context(cpu, ds, class_table_cache),
    )
    predicted = (substate, upd.direction_or_step, sprite, upd.x_word, upd.y_word, upd.active_word)
    ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
    return _Pending(ss=ss, bp=bp, exit_ip=ret_addr, predicted=predicted, read_post=_read_slot_6tuple)


def _arm_b9f0(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict B9F0 (logic_id 0x14) -- all four paths via the pure object_update_b9f0.

    B9F0 tail-jumps to BC4B; compare the movement half at the handoff.  This adapter only projects the
    slot fields + the B9F0 DS globals and calls the canonical pure system (the Path A sprite-refresh /
    reached-target BA5A helper or plain refresh / overshoot 5E42 / 5DB2 seek branches all live there).
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    r = object_update_b9f0(
        x_word=cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
        y_word=cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
        substate=cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF),
        direction=cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
        active_word=cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF),
        sprite=cpu.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF),
        target_x=cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF),
        target_y=cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF),
        move_step_error=cpu.mem.rw(ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF),
        move_delta_x=cpu.mem.rw(ss, (bp + OFF_MOVE_DELTA_X) & 0xFFFF),
        move_delta_y=cpu.mem.rw(ss, (bp + OFF_MOVE_DELTA_Y) & 0xFFFF),
        a482=cpu.mem.rw(ds, B9F0_A482),
        frame=cpu.mem.rw(ds, B9F0_FRAME_233C),
        vertical_delta=cpu.mem.rw(ds, B9F0_DELTA_Y_2342),
        horizontal_delta=cpu.mem.rw(ds, B9F0_DELTA_X_2346),
        a47e=cpu.mem.rw(ds, B9F0_COUNTER_A47E),
        difficulty=cpu.mem.rw(ds, B9F0_DIFFICULTY_BEDC),
        tick=cpu.mem.rw(ds, B9F0_TICK_2340),
        ref_box_x=cpu.mem.rw(ds, (B86D_REF_BOX + OFF_X) & 0xFFFF),
        ref_box_y=cpu.mem.rw(ds, (B86D_REF_BOX + OFF_Y) & 0xFFFF),
        ref_box_scan=cpu.mem.rw(ds, (B86D_REF_BOX + OFF_SCAN_FLAG) & 0xFFFF),
        step_mode=cpu.mem.rw(ds, STEP_MODE_2312),
        direction_table=tuple(cpu.mem.rb(ds, (DIRECTION_TABLE_A348 + i) & 0xFFFF) for i in range(16)),
    )
    predicted = (r.substate, r.direction_or_step, r.sprite_or_state, r.x_word, r.y_word, r.active_word)
    return _Pending(ss=ss, bp=bp, exit_ip=BC4B_IP, predicted=predicted, read_post=_read_slot_6tuple)


# The registry: one entry per recovered pure whole-slot transform.  Grow this as
# handlers are promoted; everything not here is counted as a fallback.
B24D_IP = 0xB24D  # logic_id 0x0B: 5E42 delta-steer + B250 contact + AD60 (movement half)
B909_IP = 0xB909  # logic_id 0x1E: sets mode 2, B729 (5DB2 seek) -> BC4B; blocked -> 7476 spawn
B909_MOVEMENT_MODE = 0x0002  # B909 stamps DS:2308 = 2 before B729's 5DB2
B2CD_IP = 0xB2CD  # logic_id 0x12: waypoint 5DB2 seek + level sprite -> BC4B (the dominant L6 object)
B2CD_WAYPOINT_PTR_OFF = 0x36
LEVEL_2356 = 0x2356
SCROLL_2350 = 0x2350


def _arm_b2cd(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict B2CD (logic_id 0x12): the waypoint 5DB2 seek + sprite, at the BC4B handoff.

    Reads the slot's current waypoint via the +36 DS pointer ({X, Y}), seeks toward it (object_update_b2cd
    composes the 5DB2 seek + the level/BDAC/scroll sprite table); returns None when 5DB2 is blocked (the
    reached-waypoint advance loop) or for the unmodelled sprite fall-throughs.  substate/active untouched."""
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    substate = cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    active = cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF)
    wp = cpu.mem.rw(ss, (bp + B2CD_WAYPOINT_PTR_OFF) & 0xFFFF)  # DS offset of the current waypoint
    table = tuple(cpu.mem.rb(ds, (DIRECTION_TABLE_A348 + i) & 0xFFFF) for i in range(16))
    upd = object_update_b2cd(
        slot_x=cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
        slot_y=cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
        slot_direction=cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
        waypoint_x=cpu.mem.rw(ds, wp & 0xFFFF),
        waypoint_y=cpu.mem.rw(ds, (wp + 2) & 0xFFFF),
        direction_table=table,
        bdac=cpu.mem.rw(ds, RENDER_MODE_BDAC),
        level=cpu.mem.rw(ds, LEVEL_2356),
        scroll=cpu.mem.rw(ds, SCROLL_2350),
    )
    if upd is None:
        return None
    predicted = (substate, upd.direction_or_step, upd.sprite_or_state, upd.x_word, upd.y_word, active)
    return _Pending(ss=ss, bp=bp, exit_ip=BC4B_IP, predicted=predicted, read_post=_read_slot_6tuple)


BE3C_IP = 0xBE3C  # logic_id 0x01: animation state machine -> BC45 post-move
BC45_IP = 0xBC45  # BE3C's post-move handoff (the sibling of BC4B)
BE3C_GATE_2324 = 0x2324
BE3C_STATE_OFF = 0x14
BE3C_COUNTER_OFF = 0x22


def _arm_be3c(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict BE3C (logic_id 0x01): the animation, compared at the BC45 handoff.

    BE3C only changes the slot sprite (+08) on its modelled paths (gate-off / state 0 -> unchanged;
    state 1 -> sprite = the inc'd frame counter), all of which join the BC45 post-move; the morph (counter
    9) and states 2/3 return None (skipped).  substate/direction/x/y/active are untouched here."""
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    sprite = cpu.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF)
    new_sprite = object_update_be3c(
        cpu.mem.rw(ds, BE3C_GATE_2324),
        cpu.mem.rw(ss, (bp + BE3C_STATE_OFF) & 0xFFFF),
        cpu.mem.rw(ss, (bp + BE3C_COUNTER_OFF) & 0xFFFF),
        sprite,
    )
    if new_sprite is None:
        return None
    predicted = (
        cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
        new_sprite,
        cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF),
    )
    return _Pending(ss=ss, bp=bp, exit_ip=BC45_IP, predicted=predicted, read_post=_read_slot_6tuple)


def _arm_b909(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict B909 (logic_id 0x1E): the B729 5DB2 seek, compared at the BC4B handoff.

    B909 stamps mode 2 (DS:2308) and calls B729, which copies the slot target (+32/+34) into the DS:2304/
    2306 seek globals and runs 5DB2.  Both the moved path and the reached/blocked path (which adds the
    7476 formation spawn + a +32 write -- global/off-tuple side effects) fall into the shared BC4B tail,
    so the slot's 6-tuple at the handoff is exactly the 5DB2 result (substate/sprite/active untouched).
    Compared at BC4B like B86D/B9F0; the BC4B post-move + 7476 spawn are verified/handled separately."""
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    substate = cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    sprite = cpu.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF)
    active = cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF)
    target = MovementTarget(
        y_word=cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF),
        x_word=cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF),
    )
    table = tuple(cpu.mem.rb(ds, (DIRECTION_TABLE_A348 + i) & 0xFFFF) for i in range(16))
    try:
        seek = object_target_seek_step_5db2(
            cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
            cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
            cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
            target, B909_MOVEMENT_MODE, table,
        )
    except ValueError:
        return None  # unverified 5E0C mode (absent from the green demos)
    predicted = (substate, seek.direction_or_step, sprite, seek.x_word, seek.y_word, active)
    return _Pending(ss=ss, bp=bp, exit_ip=BC4B_IP, predicted=predicted, read_post=_read_slot_6tuple)


NATIVE_HANDLERS: tuple[NativeHandler, ...] = (
    NativeHandler(logic_id=0x0C, label="AE09", entry_ip=AE09_IP, arm=_arm_ae09),
    NativeHandler(logic_id=0x1D, label="B86D", entry_ip=B86D_IP, arm=_arm_b86d),
    NativeHandler(logic_id=0x02, label="AED8", entry_ip=AED8_IP, arm=_arm_aed8),
    NativeHandler(logic_id=0x14, label="B9F0", entry_ip=B9F0_IP, arm=_arm_b9f0),
    NativeHandler(logic_id=0x0B, label="B24D", entry_ip=B24D_IP, arm=_arm_b24d),
    NativeHandler(logic_id=0x1E, label="B909", entry_ip=B909_IP, arm=_arm_b909),
    NativeHandler(logic_id=0x01, label="BE3C", entry_ip=BE3C_IP, arm=_arm_be3c),
    NativeHandler(logic_id=0x12, label="B2CD", entry_ip=B2CD_IP, arm=_arm_b2cd),
)
_HANDLER_BY_IP = {(CS, h.entry_ip): h for h in NATIVE_HANDLERS}


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    coverage: dict[int, int] = {}          # logic_id -> per-slot EFAE dispatches
    handler_ip: dict[int, int] = {}        # logic_id -> EFC4 dispatch target IP (the routine to recover)
    native_ok: dict[int, int] = {}         # logic_id -> verified-exact native updates
    native_fail: dict[int, list] = {}      # logic_id -> [(predicted, actual), ...]
    pending: dict[int, _Pending] = {}      # id(cpu) -> armed prediction (no nesting in the walk)
    class_table_cache: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        if cs == CS and ip == EFAE_IP:
            ss = cpu.s.ss & 0xFFFF
            bp = cpu.s.bp & 0xFFFF
            logic_id = cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
            coverage[logic_id] = coverage.get(logic_id, 0) + 1
            if logic_id not in handler_ip:
                handler_ip[logic_id] = cpu.mem.rw(cs, (EFC4_TABLE + ((logic_id << 1) & 0xFFFF)) & 0xFFFF)
        else:
            key = id(cpu)
            handler = _HANDLER_BY_IP.get((cs, ip))
            if handler is not None and key not in pending:
                armed = handler.arm(cpu, class_table_cache)
                if armed is not None:
                    armed.logic_id = handler.logic_id
                    pending[key] = armed
            else:
                armed = pending.get(key)
                if armed is not None and cs == CS and ip == armed.exit_ip:
                    pending.pop(key)
                    actual = armed.read_post(cpu, armed.ss, armed.bp)
                    if actual == armed.predicted:
                        native_ok[armed.logic_id] = native_ok.get(armed.logic_id, 0) + 1
                    else:
                        native_fail.setdefault(armed.logic_id, []).append((armed.predicted, actual))

    run_ref_step_probe(demo, max_frames, on_ref_step)
    return _report(demo_name, max_frames, coverage, native_ok, native_fail, handler_ip)


def _report(demo_name, max_frames, coverage, native_ok, native_fail, handler_ip=None) -> int:
    handler_ip = handler_ip or {}
    total = sum(coverage.values())
    native_total = sum(native_ok.values())
    native_logic_ids = {h.logic_id for h in NATIVE_HANDLERS}
    any_fail = any(native_fail.values())

    print(f"demo {demo_name} ({max_frames} frames): native object-update coverage (EFAE family)")
    print(f"  total per-slot EFAE updates: {total}")
    for lid in sorted(coverage, key=lambda k: -coverage[k]):
        seen = coverage[lid]
        if lid in native_logic_ids:
            ok = native_ok.get(lid, 0)
            fails = native_fail.get(lid, [])
            tag = f"native OK  ok={ok}/{seen} fail={len(fails)}" if not fails else f"native FAIL fail={len(fails)}"
        else:
            tag = "fallback (VM)"
        label = next((h.label for h in NATIVE_HANDLERS if h.logic_id == lid), "----")
        ip = handler_ip.get(lid)
        ip_s = f"->{ip:04X}" if ip is not None else "->????"
        print(f"  logic_id {lid:#06x} {ip_s}  {label:<6} {tag:<28} slots={seen}")
    pct = (100.0 * native_total / total) if total else 0.0
    print(f"  NATIVE COVERAGE: {native_total}/{total} per-slot updates ({pct:.1f}%), "
          f"{len(native_logic_ids)} logic_id(s) wired")
    for lid, fails in native_fail.items():
        for pred, actual in fails[:4]:
            print(f"  FAIL logic_id {lid:#06x} predicted={tuple(hex(v) for v in pred)} "
                  f"actual={tuple(hex(v) for v in actual)}")

    # Gate semantics: only an actual divergence fails.  A demo that never spawns a
    # wired handler is NO-EVENTS (not a failure) -- the rare-event convention used by
    # scripts/verify_native_producers.py -- so this is safe in a cross-demo sweep.
    if any_fail:
        result, code = "FAIL -- a wired native handler diverged from the VM", 1
    elif native_total == 0:
        result, code = "NO-EVENTS -- no wired native handler reached in this demo (not a failure)", 0
    else:
        result, code = "PASS -- wired native handlers byte-exact vs VM; coverage measured", 0
    print("RESULT:", result)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
