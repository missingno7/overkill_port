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
from overkill.recovered.systems.movement import (
    object_delta_5e1b,
    object_delta_steer_5e42,
    object_target_seek_step_5db2,
)
from overkill.recovered.systems.objects import (
    b9f0_low_counter_runs_helper,
    b9f0_periodic_helper_mask,
    b9f0_sprite_from_frame,
    b9f0_wrapped_target_x,
    object_update_ae09,
    object_update_aed8,
    object_update_b86d_drift,
)
from overkill.recovered.views.object_slots import (
    OFF_ACTIVE_WORD,
    OFF_DIRECTION_OR_STEP,
    OFF_HAZARD_CLASS,
    OFF_LOGIC_ID,
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

# B9F0 (logic_id 0x14) tail-jumps to BC4B.  Incremental: only the sprite-refresh path (A482 != A4E4,
# the BA67 tail) is modelled so far; the A482 == A4E4 movement paths (5DB2 seek / 5E42 overshoot /
# BA5A helper) are left as fallback (None) and added next.
B9F0_IP = 0xB9F0
B9F0_A482 = 0xA482               # DS:A482; == A4E4h enters the movement paths, else sprite-refresh
B9F0_A482_MOVEMENT_SENTINEL = 0xA4E4
B9F0_FRAME_233C = 0x233C         # DS:233C global frame -> b9f0_sprite_from_frame on the BA67 tail
B9F0_DELTA_Y_2342 = 0x2342       # DS:2342 global Y delta added to target_y (+32)
B9F0_DELTA_X_2346 = 0x2346       # DS:2346 global X delta added to target_x (+34)
B9F0_COUNTER_A47E = 0xA47E       # DS:A47E level counter (< 6 -> BA5A helper fires)
B9F0_DIFFICULTY_BEDC = 0xBEDC    # DS:BEDC difficulty -> periodic-helper tick mask
B9F0_TICK_2340 = 0x2340          # DS:2340 tick counter for the periodic BA5A helper
B9F0_SEEK_MODE = 0x0001          # DS:2308 mode the Path-D seek sets before 5DB2 (mode 1)

# B86D (logic_id 0x1D) fall-through inputs.  B86D tail-jumps to the shared BC4B post-move
# stage rather than RETurning, so its slot-write boundary is a fixed IP, not a return address.
B86D_IP = 0xB86D
BC4B_IP = 0xBC4B
B86D_PHASE_A47E = 0xA47E          # DS:A47E early-global guard (<=2 -> B8F8 edge-steer)
B86D_PHASE_A7A0 = 0xA7A0          # DS:A7A0 phase gate (<0x28 -> A7A0 mask/B729 block)
B86D_VERTICAL_DELTA_2342 = 0x2342  # DS:2342 global vertical delta (X += -delta)
B86D_PHASE_2328 = 0x2328          # DS:2328 phase word (==7 -> +1 X nudge)
B86D_X_EDGE = 0x00C0              # x > C0h -> B8F8 edge-steer
B86D_REF_BOX = 0x237C            # DS:237C view-anchor box (BX for 5E1B in the B8F8 branch)
B86D_EDGE_STEER_SPRITE = 0x0076  # sprite B86D forces after the B8F8 steer
STEP_MODE_2312 = 0x2312          # DS:2312 5E42 step mode (==3 -> 3px else 2px)
DIRECTION_TABLE_A348 = 0xA348    # DS:A348 16-byte direction-bits -> direction map (5E42 + 5DB2)
B86D_A7A0_SPRITE = 0x0075        # sprite B86D forces in the A7A0 phase block
B86D_A7A0_BLOCKED_DIR = 0x0004   # direction B86D sets when the A7A0 B729/5DB2 seek is blocked
B86D_A7A0_MODE = 0x0001          # DS:2308 mode the A7A0 block sets before B729 (5DB2 mode 1)
LOW_BIT_CLEAR_MASK = 0xFFFE      # the A7A0 block clears the low bit of x/y/target before the seek


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
    """Capture + predict B86D (logic_id 0x1D): the B8F8 edge-steer and the fall-through paths.

    B86D tail-jumps to the shared BC4B post-move stage, so compare at the BC4B handoff.  Two of the
    three branches are pure-composable today: the B8F8 edge-steer (A47E<=2 or x>C0h) computes deltas
    toward the DS:237C box via 5E1B, steers via 5E42, then forces sprite 0x76; the fall-through
    (formation drift) is object_update_b86d_drift.  The A7A0 phase block still needs the cpu-bound
    B729 target move -> fallback (``None``).
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    x = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    substate = cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    direction = cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
    active = cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF)

    if cpu.mem.rw(ds, B86D_PHASE_A47E) <= 0x0002 or x > B86D_X_EDGE:
        # B8F8 edge-steer: 5E1B deltas toward the DS:237C box, then 5E42 steer, then sprite 0x76.
        ref_x = cpu.mem.rw(ds, (B86D_REF_BOX + OFF_X) & 0xFFFF)
        ref_y = cpu.mem.rw(ds, (B86D_REF_BOX + OFF_Y) & 0xFFFF)
        ref_scan = cpu.mem.rw(ds, (B86D_REF_BOX + OFF_SCAN_FLAG) & 0xFFFF)
        deltas = object_delta_5e1b(x, y, ref_x, ref_y, ref_scan)
        err = cpu.mem.rw(ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF)
        step_mode = cpu.mem.rw(ds, STEP_MODE_2312)
        table = tuple(cpu.mem.rb(ds, (DIRECTION_TABLE_A348 + i) & 0xFFFF) for i in range(16))
        steer = object_delta_steer_5e42(
            x, y, direction, deltas.move_delta_y, deltas.move_delta_x, err, step_mode, table
        )
        predicted = (substate, steer.direction_or_step, B86D_EDGE_STEER_SPRITE,
                     steer.x_word, steer.y_word, active)
        return _Pending(ss=ss, bp=bp, exit_ip=BC4B_IP, predicted=predicted, read_post=_read_slot_6tuple)

    if cpu.mem.rw(ds, B86D_PHASE_A7A0) < 0x0028:
        # A7A0 phase block: clear the low bit of x/y/target, then B729 = publish the slot's target
        # to the 5DB2 globals + run the pure 5DB2 target-seek (mode 1), force sprite 0x75, and set
        # direction 4 when the seek reports blocked.  Compared at the BC4B handoff.
        masked_x = x & LOW_BIT_CLEAR_MASK
        masked_y = y & LOW_BIT_CLEAR_MASK
        target = MovementTarget(
            y_word=cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF) & LOW_BIT_CLEAR_MASK,
            x_word=cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF) & LOW_BIT_CLEAR_MASK,
        )
        table = tuple(cpu.mem.rb(ds, (DIRECTION_TABLE_A348 + i) & 0xFFFF) for i in range(16))
        seek = object_target_seek_step_5db2(masked_x, masked_y, direction, target, B86D_A7A0_MODE, table)
        new_dir = B86D_A7A0_BLOCKED_DIR if seek.blocked else seek.direction_or_step
        predicted = (substate, new_dir, B86D_A7A0_SPRITE, seek.x_word, seek.y_word, active)
        return _Pending(ss=ss, bp=bp, exit_ip=BC4B_IP, predicted=predicted, read_post=_read_slot_6tuple)

    # Fall-through (formation drift): changes only sprite and X; the other four are unchanged.
    delta = cpu.mem.rw(ds, B86D_VERTICAL_DELTA_2342)
    pred = object_update_b86d_drift(x, delta, cpu.mem.rw(ds, B86D_PHASE_2328))
    predicted = (substate, direction, pred.sprite_or_state, pred.x_word, y, active)
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


def _arm_b9f0(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict B9F0 (logic_id 0x14), compared at the BC4B handoff.

    Models three of the four paths: the sprite-refresh tail (A482 != A4E4, or the reached-target path
    when its BA5A helper does not fire) and Path D, the 5DB2 seek (A482 == A4E4, not reached, x <= target).
    The two 5E42 paths -- the overshoot branch and the BA5A motion helper -- return None (fallback) for now.
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

    def sprite_refresh() -> _Pending:
        # BA67 tail: sprite = DS:233C frame + 1Ch; nothing else changes.
        refreshed = b9f0_sprite_from_frame(cpu.mem.rw(ds, B9F0_FRAME_233C))
        return _Pending(ss=ss, bp=bp, exit_ip=BC4B_IP,
                        predicted=(substate, direction, refreshed, x, y, active), read_post=_read_slot_6tuple)

    if (cpu.mem.rw(ds, B9F0_A482) & 0xFFFF) != B9F0_A482_MOVEMENT_SENTINEL:
        return sprite_refresh()  # Path A

    # A482 == A4E4: apply the global target deltas into +32/+34, wrap target X (BA07..BA1A).
    delta_y = cpu.mem.rw(ds, B9F0_DELTA_Y_2342)
    target_y = (cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF) + delta_y) & 0xFFFF
    target_x = b9f0_wrapped_target_x(
        (cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF) + cpu.mem.rw(ds, B9F0_DELTA_X_2346)) & 0xFFFF
    )
    # reached-target (mirrors b9f0_reached_target on the updated targets; avoids building a record here).
    reached = ((y + delta_y) & 0xFFFF) == target_y and (x & 0xFFFF) == target_x
    if reached:
        # Path B: the BA5A motion helper fires on a low level counter or a periodic tick -> defer (5E42).
        if b9f0_low_counter_runs_helper(cpu.mem.rw(ds, B9F0_COUNTER_A47E)):
            return None
        mask = b9f0_periodic_helper_mask(cpu.mem.rw(ds, B9F0_DIFFICULTY_BEDC))
        if (cpu.mem.rw(ds, B9F0_TICK_2340) & mask) == mask:
            return None
        return sprite_refresh()  # reached, no helper -> the BA67 sprite-refresh tail

    if (x & 0xFFFF) > target_x:
        return None  # Path C overshoot (5E42) -- deferred

    # Path D: align to even pixels and seek toward the updated target via the pure 5DB2 (mode 1).
    table = tuple(cpu.mem.rb(ds, (DIRECTION_TABLE_A348 + i) & 0xFFFF) for i in range(16))
    target = MovementTarget(y_word=target_y & 0xFFFE, x_word=target_x & 0xFFFE)
    seek = object_target_seek_step_5db2(x & 0xFFFE, y & 0xFFFE, direction, target, B9F0_SEEK_MODE, table)
    predicted = (substate, seek.direction_or_step, sprite, seek.x_word, seek.y_word, active)
    return _Pending(ss=ss, bp=bp, exit_ip=BC4B_IP, predicted=predicted, read_post=_read_slot_6tuple)


# The registry: one entry per recovered pure whole-slot transform.  Grow this as
# handlers are promoted; everything not here is counted as a fallback.
NATIVE_HANDLERS: tuple[NativeHandler, ...] = (
    NativeHandler(logic_id=0x0C, label="AE09", entry_ip=AE09_IP, arm=_arm_ae09),
    NativeHandler(logic_id=0x1D, label="B86D", entry_ip=B86D_IP, arm=_arm_b86d),
    NativeHandler(logic_id=0x02, label="AED8", entry_ip=AED8_IP, arm=_arm_aed8),
    NativeHandler(logic_id=0x14, label="B9F0", entry_ip=B9F0_IP, arm=_arm_b9f0),
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
