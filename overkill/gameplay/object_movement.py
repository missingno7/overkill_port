"""Object movement primitives for the OVERKILL object runtime.

Architecture layer: **lifted**.  The leaf motion primitives carved out of
``object_runtime.py``: per-direction pixel steps, axis clamps, world-scroll
steps/rows/edge responses, child/linked coordinate updates, the 5DB2 direction
resolver, the 5E42 runtime-patched steer, and the target-seek/candidate-scan
helpers (B729/B15A/D281).  These mutate object-slot coordinates and movement
globals only; the *movement behaviours* that route on into the postmove/contact
tails (drift AE2C/AE7D, player-chase B1B0, tile-sweep B00D) deliberately stay in
``object_runtime.py`` with the dispatch/postmove hub.  Bodies relocated verbatim;
conservative names only.
"""
from __future__ import annotations

from dos_re.cpu import ZF
from overkill.asm import (
    _add_mem_word, _add_reg16, _and_mem_word, _cmp_byte, _cmp_word,
    _dec_mem_word_preserve_cf, _inc_mem_word_preserve_cf, _sub_mem_word,
)
from overkill.gameplay.collision import run_tile_lookup_505b
from overkill.gameplay.object_runtime_common import (
    _call_verified_child_near, _neg_reg16, _no_patch_guard, _or_mem_word,
    _raise_unverified_path, _run_interpreted_near_call_observed,
)
from overkill.recovered.adapters.movement_adapter import (
    MOVEMENT_BLOCKED_FLAG, MOVEMENT_DIRECTION_BITS, MOVEMENT_MODE,
    apply_direction_step_to_current_object, decide_target_seek_direction_from_dos,
    publish_object_slot_target_to_movement_globals,
)
from overkill.recovered.adapters.object_behavior_adapter import run_player_chase_candidate_checks_b15a
from overkill.recovered.domain.movement import VerticalScrollEdgeInput
from overkill.recovered.systems.movement import (
    decay_bottom_scroll_bias_a63c, one_pixel_axis_step, recover_top_scroll_bias_a662,
    top_scroll_edge_response_a648, two_pass_axis_clamp_step, vertical_scroll_edge_response_a616,
)
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_BASE, OBJECT_SLOT_STRIDE,
    OFF_MOVE_STEP_ERROR, OFF_SPRITE_OR_STATE, OFF_X, OFF_Y, ObjectSlotView,
)
from overkill.runtime_code import require_runtime_code_variant



SIG_OBJECT_CHILD_COORD_UPDATE_9FEA = bytes.fromhex(
    "83 fb ff 75 01 c3 8b 46 08 d1 e0 d1 e0 03 f0"
)


SIG_LINKED_OBJECT_COORD_QUAD_UPDATE_9FAF = bytes.fromhex(
    "c6 06 9e a3 00 c6 06 9f a3 00 a1 9a a3 a3 98 a3"
    " be 8c a3 8b 1e 6c a9 e8 21 00 be 74 a3 8b 1e 68"
    " a9 e8 17 00 a1 9c a3 a3 98 a3 be 80 a3 8b 1e 6a"
    " a9 e8 07 00 be 68 a3 8b 1e 66 a9"
)


SIG_OBJECT_X_STEP_LEFT_CLAMP_A5D1 = bytes.fromhex(
    "83 3e 7c a4 00 75 0e e8 00 00 83 7e 02 20 75 01 c3 ff 4e 02 c3 ff 4e 02 c3"
)


SIG_OBJECT_X_STEP_RIGHT_CLAMP_A5EA = bytes.fromhex(
    "e8 00 00 81 7e 02 c0 00 75 01 c3 ff 46 02 c3"
)


SIG_OBJECT_Y_STEP_UP_CLAMP_A5F9 = bytes.fromhex(
    "e8 00 00 83 7e 04 00 75 01 c3 ff 4e 04 c3"
)


SIG_OBJECT_Y_STEP_DOWN_CLAMP_A607 = bytes.fromhex(
    "e8 00 00 81 7e 04 b0 00 72 01 c3 ff 46 04 c3"
)


SIG_OBJECT_VERTICAL_SCROLL_EDGE_RESPONSE_A616 = bytes.fromhex(
    "81 3e 50 23 b6 00 77 01 c3 e8 26 00 81 7e 04 b0"
    " 00 75 13 f6 06 be 98 01 74 0c 83 3e 9c a3 08 74"
    " 04 ff 06 9c a3 c3 83 3e 9c a3 00 74 04 ff 0e 9c"
    " a3 c3 83 7e 04 00 75 14 f6 06 be 98 02 74 0d 83"
    " 3e 9a a3 f8 75 01 c3 ff 0e 9a a3 c3 83 3e 9a a3"
    " 00 75 01 c3 ff 06 9a a3 c3"
)


SIG_OBJECT_BOTTOM_SCROLL_OFFSET_DECAY_A63C = bytes.fromhex(
    "83 3e 9c a3 00 74 04 ff 0e 9c a3 c3"
)


SIG_OBJECT_TOP_SCROLL_EDGE_RESPONSE_A648 = bytes.fromhex(
    "83 7e 04 00 75 14 f6 06 be 98 02 74 0d 83 3e 9a"
    " a3 f8 75 01 c3 ff 0e 9a a3 c3 83 3e 9a a3 00"
    " 75 01 c3 ff 06 9a a3 c3"
)


SIG_OBJECT_TOP_SCROLL_OFFSET_RECOVER_A662 = bytes.fromhex(
    "83 3e 9a a3 00 75 01 c3 ff 06 9a a3 c3"
)


SIG_OBJECT_TARGET_CHASE_D281 = bytes.fromhex(
    "8b 46 32 a3 04 23 8b 46 34 a3 06 23 c7 06 08 23 01 00"
)


SIG_MOVEMENT_DIR_STEP_8PX_AEE4 = bytes.fromhex(
    "8b 5e 06 d1 e3 2e ff a7 ee ae 0b af 10 af 14 af fe ae 02 af 19 af 1d af 07 af "
    "83 46 04 08 83 46 02 08 c3 83 6e 04 08 83 6e 02 08 c3 83 6e 02 08 83 46 04 08 c3 "
    "83 46 02 08 83 6e 04 08 c3"
)


SIG_MOVEMENT_DIR_STEP_3PX_AF22 = bytes.fromhex(
    "8b 5e 06 d1 e3 2e ff a7 2c af 49 af 4e af 52 af 3c af 40 af 57 af 5b af 45 af "
    "83 46 04 03 83 46 02 03 c3 83 6e 04 03 83 6e 02 03 c3 83 6e 02 03 83 46 04 03 c3 "
    "83 46 02 03 83 6e 04 03 c3"
)


SIG_MOVEMENT_DIR_STEP_2PX_AF63 = bytes.fromhex(
    "8b 5e 06 d1 e3 2e ff a7 6e af 90 8b af 90 af 94 af 7e af 82 af 99 af 9d af 87 af "
    "83 46 04 02 83 46 02 02 c3 83 6e 04 02 83 6e 02 02 c3 83 6e 02 02 83 46 04 02 c3 "
    "83 46 02 02 83 6e 04 02 c3"
)


SIG_MOVEMENT_DOUBLE_STEP_2PX_AF60 = b"\xE8\x00\x00" + SIG_MOVEMENT_DIR_STEP_2PX_AF63


SIG_OBJECT_TARGET_MOVE_B729 = bytes.fromhex(
    "8b 46 32 a3 04 23 8b 46 34 a3 06 23 e8 7a a6 83 3e 0a 23 00 c3"
)


SIG_OBJECT_SCROLL_FORWARD_STEP_A6FE = bytes.fromhex(
    "55 83 06 78 a2 01 c7 06 52 23 00 00 83 3e 4e 23 00 75 03 "
    "e8 3a 00 ff 0e 4e 23 83 26 4e 23 0f 75 10 83 3e 54 23 00 "
    "74 09 83 06 50 23 0d ff 0e 78 a9 2e a1 be 95"
)


SIG_OBJECT_SCROLL_BACKWARD_STEP_A781 = bytes.fromhex(
    "55 c7 06 52 23 01 00 83 3e 50 23 00 74 b5 83 06 78 a2 ff "
    "83 3e 4e 23 00 75 03 e8 32 00 ff 06 4e 23 83 26 4e 23 0f "
    "75 10 83 3e 54 23 01"
)


SIG_OBJECT_SCROLL_FORWARD_ROW_A74E = bytes.fromhex(
    "e8 9a 00 81 3e 50 23 b6 00 77 0c 80 3e c0 98 00 74 05 "
    "c6 06 ff be 07 83 06 50 23 0d"
)


SIG_OBJECT_SCROLL_BACKWARD_ROW_A7D0 = bytes.fromhex(
    "e8 18 00 83 2e 50 23 0d ff 06 78 a9 c7 06 54 23 01 00 c3"
)


SIG_OBJECT_SCROLL_ROW_WRAP_A746 = bytes.fromhex("2e a1 c0 95 a3 4c 23 c3")


SIG_OBJECT_SCROLL_ROW_WRAP_A7E3 = bytes.fromhex("2e a1 be 95 a3 4c 23 c3")


SIG_OBJECT_SCROLL_WORLD_PROGRESS_GATE_A66F = bytes.fromhex(
    "83 3e 7c a4 00 74 03 e9 84 00 83 3e 7e a4 00 75 7d "
    "83 3e 80 a4 00 75 76 e8 74 00 83 3e 4e 23 00 75 6c "
    "50 53 51 52 57 56 55 06 1e be 82 a9"
)


SIG_OBJECT_PLAYER_CHASE_CANDIDATE_SCAN_B15A = bytes.fromhex(
    "b9 23 00 8b 1e 3a a4 81 fb 5c 2b 73 33 83 3f 00 "
    "74 25 83 7f 18 01 74 1f 83 7f 18 26 74 19 83 "
    "7f 18 21 74 13 83 7f 18 22 74 0d 81 7f 02 e0 "
    "00 77 06 83 7f 16 04 74 15 83 c3 38 e2 cb bb "
    "ff ff c3 c7 06 3a a4 b4 23 8b 1e 3a a4 eb bb "
    "53 83 c3 38 89 1e 3a a4 5b c3"
)


def _run_object_delta_helper_5e1b(cpu) -> None:
    """Mirror the small 1010:5E1B object delta helper.

    The helper is used by several object-family edge/target steering branches.
    BX points at a target object/box record, BP points at the active object slot.
    It stores signed Y/X deltas into SS:[BP+2C]/SS:[BP+2A] relative to
    DS:[BX+04]/DS:[BX+02], with either a 4px or 12px padding depending on
    DS:[BX+14].  The final live flags are from the X ``SUB AX,CX`` just like
    the original; the trailing MOV/RET do not alter them.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    bx = cpu.s.bx & 0xFFFF
    mem = cpu.mem
    dst = ObjectSlotView(mem, ds, bx)  # the target object's record (DS:BX)

    cpu.s.dx = 0x0004
    _cmp_word(cpu, dst.scan_flag, 0x0001)
    if dst.scan_flag != 0x0001:
        cpu.s.dx = 0x000C

    cpu.s.ax = slot.y_word
    cpu.s.cx = dst.y_word
    old_cx = cpu.s.cx
    cpu.s.cx = (cpu.s.cx + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_cx, cpu.s.dx, old_cx + cpu.s.dx, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    slot.move_delta_y = cpu.s.ax

    cpu.s.ax = slot.x_word
    cpu.s.cx = dst.x_word
    old_cx = cpu.s.cx
    cpu.s.cx = (cpu.s.cx + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_cx, cpu.s.dx, old_cx + cpu.s.dx, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    slot.move_delta_x = cpu.s.ax


def _run_runtime_patched_object_steer_5e42(cpu) -> None:
    """Mirror the hot gameplay-patched 1010:5E42 steering helper.

    The original executable overlays this address with a small helper during
    gameplay.  It converts signed Y/X deltas at ``SS:[BP+2C]/[BP+2A]`` into a
    direction through the ``DS:A348`` table, then tail-jumps to AF22 for a
    3-pixel move when ``DS:2312 == 3`` or AF63 for a 2-pixel move otherwise.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    def call_5eb5() -> None:
        _cmp_word(cpu, mem.rw(ds, 0x230C), 0x0001)
        if mem.rw(ds, 0x230C) == 0x0001:
            _or_mem_word(cpu, ds, 0x2310, 0x0001)
        else:
            _or_mem_word(cpu, ds, 0x2310, 0x0002)

    def call_5ec8() -> None:
        _cmp_word(cpu, mem.rw(ds, 0x230E), 0x0001)
        if mem.rw(ds, 0x230E) == 0x0001:
            _or_mem_word(cpu, ds, 0x2310, 0x0004)
        else:
            _or_mem_word(cpu, ds, 0x2310, 0x0008)

    mem.ww(ds, 0x230C, 0x0000)
    mem.ww(ds, 0x230E, 0x0000)
    mem.ww(ds, 0x2310, 0x0000)

    cpu.s.ax = slot.move_delta_y
    cpu.set_logic_flags(cpu.s.ax, 16)
    if (cpu.s.ax & 0x8000) != 0:
        _neg_reg16(cpu, 0)
        _inc_mem_word_preserve_cf(cpu, ds, 0x230C)

    cpu.s.bx = slot.move_delta_x
    cpu.set_logic_flags(cpu.s.bx, 16)
    if (cpu.s.bx & 0x8000) != 0:
        _neg_reg16(cpu, 3)
        _inc_mem_word_preserve_cf(cpu, ds, 0x230E)

    ax = cpu.s.ax & 0xFFFF
    bx = cpu.s.bx & 0xFFFF
    _cmp_word(cpu, ax, bx)
    if ax == bx:
        call_5eb5()
        call_5ec8()
    elif ax > bx:
        _add_mem_word(cpu, ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF, bx)
        frac = slot.move_step_error
        _cmp_word(cpu, frac, ax)
        if frac <= ax:
            call_5eb5()
        else:
            _sub_mem_word(cpu, ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF, ax)
            call_5eb5()
            call_5ec8()
    else:
        _add_mem_word(cpu, ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF, ax)
        frac = slot.move_step_error
        _cmp_word(cpu, frac, bx)
        if frac <= bx:
            call_5ec8()
        else:
            _sub_mem_word(cpu, ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF, bx)
            call_5eb5()
            call_5ec8()

    cpu.s.bx = 0xA348
    cpu.s.ax = mem.rw(ds, 0x2310)
    cpu.set_reg8(0, mem.rb(ds, (cpu.s.bx + (cpu.s.ax & 0x00FF)) & 0xFFFF))
    _cmp_byte(cpu, cpu.s.ax & 0x00FF, 0xFF)
    if (cpu.s.ax & 0x00FF) == 0xFF:
        cpu.s.ip = cpu.pop()
        return

    slot.direction_or_step = cpu.s.ax
    _cmp_word(cpu, mem.rw(ds, 0x2312), 0x0003)
    if mem.rw(ds, 0x2312) == 0x0003:
        _run_af22_three_pixel_step_for_direction(cpu, parent="1010:5E42 -> AF22")
    else:
        _run_af63_step_for_direction(cpu, parent="1010:5E42 -> AF63")
    cpu.s.ip = cpu.pop()


def run_runtime_patched_object_steer_5e42(cpu) -> None:
    """Hook wrapper body for the gameplay-patched 1010:5E42 variant.

    This address is polyvariant.  The hook is valid only for the known gameplay
    materialized body; known-cold or unknown live bytes fail fast so runtime code
    exhaustion cannot hide behind interpreted fallback.
    """
    require_runtime_code_variant(cpu, (cpu.s.cs & 0xFFFF, 0x5E42), "gameplay_object_steer_5e42")
    _run_runtime_patched_object_steer_5e42(cpu)


def run_object_child_coord_update_9fea(cpu, self_disable_if_patched) -> None:
    """Lift 1010:9FEA, a small object-linked coordinate update helper.

    The caller passes BX as the destination linked object pointer and SI as a
    motion/offset table pointer.  BX==FFFF is the null-link fast return.  The
    active path adds the source object's base X/Y to two table words, applies
    the global vertical scroll offset DS:A398 twice, clamps Y into 0..00C0h,
    and sets DS:A39E/A39F when the lower/upper clamp fired.
    """
    if self_disable_if_patched(
        cpu,
        0x9FEA,
        SIG_OBJECT_CHILD_COORD_UPDATE_9FEA,
        "overkill_object_child_coord_update_9fea",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bx = s.bx & 0xFFFF

    _cmp_word(cpu, bx, 0xFFFF)
    if bx == 0xFFFF:
        s.ip = cpu.pop()
        return

    ax = mem.rw(ss, (s.bp + OFF_SPRITE_OR_STATE) & 0xFFFF)
    ax = cpu.shift(4, ax, 1, 16)
    ax = cpu.shift(4, ax, 1, 16)
    _add_reg16(cpu, 6, ax)

    x_delta = mem.rw(ds, s.si & 0xFFFF)
    s.si = (s.si + 2) & 0xFFFF
    ax = (x_delta + mem.rw(ss, (s.bp + OFF_X) & 0xFFFF)) & 0xFFFF
    # ADD flags are overwritten later by the Y clamps/cmp in all observed active paths.
    s.ax = ax
    dst = ObjectSlotView(mem, ds, bx)  # the spawned/target object's record (DS:BX)
    dst.x_word = ax

    y_delta = mem.rw(ds, s.si & 0xFFFF)
    s.si = (s.si + 2) & 0xFFFF
    ax_full = y_delta + mem.rw(ss, (s.bp + OFF_Y) & 0xFFFF)
    ax_full += mem.rw(ds, 0xA398)
    ax_full += mem.rw(ds, 0xA398)
    ax = ax_full & 0xFFFF
    s.ax = ax
    dst.y_word = ax

    y = dst.y_word
    _cmp_word(cpu, y, 0x0000)
    if y & 0x8000:
        dst.y_word = 0x0000
        mem.wb(ds, 0xA39E, 0x01)
        y = 0

    _cmp_word(cpu, y, 0x00C0)
    # Signed JLE.  Values above 00C0 in the positive signed range trigger the
    # upper clamp.  Negative values have already been clamped to zero above.
    if y <= 0x00C0:
        s.ip = cpu.pop()
        return

    dst.y_word = 0x00C0
    mem.wb(ds, 0xA39F, 0x01)
    s.ip = cpu.pop()


def run_linked_object_coord_quad_update_9faf(cpu, self_disable_if_patched) -> None:
    """Lift 1010:9FAF, the four-linked-object coordinate update parent.

    The frame-controller child calls this block to update four linked object
    pointers from motion/offset tables.  It composes the already verified
    ``9FEA`` child-coordinate helper three times via real CALL scratch and then
    falls through into the fourth ``9FEA`` call, which returns directly to the
    original caller.  This is still raw linked-slot/ring behavior; it does not
    assign a semantic enemy/projectile identity to the four children.
    """
    if self_disable_if_patched(
        cpu,
        0x9FAF,
        SIG_LINKED_OBJECT_COORD_QUAD_UPDATE_9FAF,
        "overkill_linked_object_coord_quad_update_9faf",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    def call_child(si: int, bx_global: int, ret_ip: int) -> None:
        s.si = si & 0xFFFF
        s.bx = mem.rw(ds, bx_global & 0xFFFF)
        cpu.push(ret_ip & 0xFFFF)
        run_object_child_coord_update_9fea(cpu, self_disable_if_patched)
        if (s.ip & 0xFFFF) != (ret_ip & 0xFFFF):
            raise RuntimeError(
                f"9FAF expected 9FEA child to return to 1010:{ret_ip & 0xFFFF:04X}, "
                f"got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    mem.wb(ds, 0xA39E, 0x00)
    mem.wb(ds, 0xA39F, 0x00)

    s.ax = mem.rw(ds, 0xA39A)
    mem.ww(ds, 0xA398, s.ax)
    call_child(0xA38C, 0xA96C, 0x9FC9)
    call_child(0xA374, 0xA968, 0x9FD3)

    s.ax = mem.rw(ds, 0xA39C)
    mem.ww(ds, 0xA398, s.ax)
    call_child(0xA380, 0xA96A, 0x9FE3)

    s.si = 0xA368
    s.bx = mem.rw(ds, 0xA966)
    _cmp_word(cpu, s.bx & 0xFFFF, 0xFFFF)
    if (s.bx & 0xFFFF) == 0xFFFF:
        # The original guards the final fall-through (CMP BX,FFFF / JNZ / RET):
        # when the 4th linked slot is inactive - e.g. a sidearm was lost - it
        # skips the 9FEA child-coord update and returns, consuming 9FAF's caller
        # return word exactly as the fall-through path otherwise would.  Without
        # this guard the lift ran an extra child-coord write, corrupting the
        # DS:A30A coord trail (the mothership sidearm-drag divergence).
        s.ip = cpu.pop()
        return
    # Fall through into 9FEA (BX != FFFF): no new return word is pushed, so the
    # child helper consumes 9FAF's caller return exactly like the original ASM.
    run_object_child_coord_update_9fea(cpu, self_disable_if_patched)


def _run_two_pass_word_clamp_step(cpu, *, field_off: int, limit: int, increment: bool, below_condition: bool = False) -> None:
    """Thin adapter over the pure two-pass clamp-step (MovementSystem).

    The recovered :func:`two_pass_axis_clamp_step` is the live implementation:
    read the field, call it, write the final value, return.  The original
    CALL-next/RET-twice stack scratch lived in the dead-stack window the boundary
    contract already frees, and the body's intermediate 8086 flags are not
    observed at the caller boundary, so neither is reproduced.
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    field_addr = (bp + field_off) & 0xFFFF
    decision = two_pass_axis_clamp_step(
        cpu.mem.rw(ss, field_addr),
        limit_word=limit,
        increment=increment,
        below_condition=below_condition,
    )
    cpu.mem.ww(ss, field_addr, decision.final_word)
    cpu.s.ip = cpu.pop()


def run_object_x_step_left_clamp_a5d1(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A5D1, a raw leftward object X clamp-step helper."""
    if self_disable_if_patched(
        cpu,
        0xA5D1,
        SIG_OBJECT_X_STEP_LEFT_CLAMP_A5D1,
        "overkill_object_x_step_left_clamp_a5d1",
    ):
        return
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    if cpu.mem.rw(cpu.s.ds & 0xFFFF, 0xA47C) != 0:
        # Global no-clamp gate set: one unconditional leftward pixel step.
        slot.x_word = one_pixel_axis_step(slot.x_word, increment=False).final_word
        cpu.s.ip = cpu.pop()
        return
    _run_two_pass_word_clamp_step(cpu, field_off=OFF_X, limit=0x0020, increment=False)


def run_object_x_step_right_clamp_a5ea(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A5EA, a raw rightward object X clamp-step helper."""
    if self_disable_if_patched(
        cpu,
        0xA5EA,
        SIG_OBJECT_X_STEP_RIGHT_CLAMP_A5EA,
        "overkill_object_x_step_right_clamp_a5ea",
    ):
        return
    _run_two_pass_word_clamp_step(cpu, field_off=OFF_X, limit=0x00C0, increment=True)


def run_object_y_step_up_clamp_a5f9(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A5F9, a raw upward object Y clamp-step helper."""
    if self_disable_if_patched(
        cpu,
        0xA5F9,
        SIG_OBJECT_Y_STEP_UP_CLAMP_A5F9,
        "overkill_object_y_step_up_clamp_a5f9",
    ):
        return
    _run_two_pass_word_clamp_step(cpu, field_off=OFF_Y, limit=0x0000, increment=False)


def run_object_y_step_down_clamp_a607(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A607, a raw downward object Y clamp-step helper."""
    if self_disable_if_patched(
        cpu,
        0xA607,
        SIG_OBJECT_Y_STEP_DOWN_CLAMP_A607,
        "overkill_object_y_step_down_clamp_a607",
    ):
        return
    _run_two_pass_word_clamp_step(cpu, field_off=OFF_Y, limit=0x00B0, increment=True, below_condition=True)


def run_object_bottom_scroll_offset_decay_a63c(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A63C, decay the bottom-edge scroll offset toward zero."""
    if self_disable_if_patched(
        cpu,
        0xA63C,
        SIG_OBJECT_BOTTOM_SCROLL_OFFSET_DECAY_A63C,
        "overkill_object_bottom_scroll_offset_decay_a63c",
    ):
        return
    # Thin adapter: the pure decay rule owns the result; the body's CMP/DEC flags
    # are dead at the caller (demo-replay green).
    ds = cpu.s.ds & 0xFFFF
    cpu.mem.ww(ds, 0xA39C, decay_bottom_scroll_bias_a63c(cpu.mem.rw(ds, 0xA39C)))
    cpu.s.ip = cpu.pop()


def run_object_top_scroll_offset_recover_a662(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A662, recover the top-edge scroll offset toward zero."""
    if self_disable_if_patched(
        cpu,
        0xA662,
        SIG_OBJECT_TOP_SCROLL_OFFSET_RECOVER_A662,
        "overkill_object_top_scroll_offset_recover_a662",
    ):
        return
    # Thin adapter: the pure recovery rule owns the result; the body's CMP/INC
    # flags are dead at the caller (demo-replay green).
    ds = cpu.s.ds & 0xFFFF
    cpu.mem.ww(ds, 0xA39A, recover_top_scroll_bias_a662(cpu.mem.rw(ds, 0xA39A)))
    cpu.s.ip = cpu.pop()


def run_object_top_scroll_edge_response_a648(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A648 — thin adapter over the pure top-edge scroll-bias rule."""
    if self_disable_if_patched(
        cpu,
        0xA648,
        SIG_OBJECT_TOP_SCROLL_EDGE_RESPONSE_A648,
        "overkill_object_top_scroll_edge_response_a648",
    ):
        return
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    cpu.mem.ww(ds, 0xA39A, top_scroll_edge_response_a648(
        object_y_word=slot.y_word,
        input_bits=cpu.mem.rb(ds, 0x98BE),
        top_bias_word=cpu.mem.rw(ds, 0xA39A),
    ))
    cpu.s.ip = cpu.pop()


def run_object_vertical_scroll_edge_response_a616(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A616 — thin adapter over the pure vertical scroll-edge rule.

    Frame-controller/object bridge: once the view advances past the gameplay
    threshold it updates the top/bottom scroll-bias globals DS:A39A/A39C from the
    active object's Y and input bits.  The recovered MovementSystem owns the whole
    decision (view gate + top + bottom); this adapter reads state, calls it, and
    writes the two bias globals.  The original nested CALL A648, its dead-stack
    scratch, and the body's intermediate flags are not part of the caller contract
    (demo-replay green).
    """
    if self_disable_if_patched(
        cpu,
        0xA616,
        SIG_OBJECT_VERTICAL_SCROLL_EDGE_RESPONSE_A616,
        "overkill_object_vertical_scroll_edge_response_a616",
    ):
        return
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    decision = vertical_scroll_edge_response_a616(
        VerticalScrollEdgeInput(
            view_y_word=cpu.mem.rw(ds, 0x2350),
            object_y_word=slot.y_word,
            input_bits=cpu.mem.rb(ds, 0x98BE),
            top_bias_word=cpu.mem.rw(ds, 0xA39A),
            bottom_bias_word=cpu.mem.rw(ds, 0xA39C),
        )
    )
    cpu.mem.ww(ds, 0xA39A, decision.top_bias_word)
    cpu.mem.ww(ds, 0xA39C, decision.bottom_bias_word)
    cpu.s.ip = cpu.pop()


def run_object_scroll_world_progress_gate_a66f(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A66F, the vertical-scroll/world-progress gate.

    This parent is the low-level controller around the A6FE scroll tick.  It
    gates on transition globals, advances the scroll row state, optionally
    updates the EGA palette at a milestone, and when the scroll reaches EA0h it
    seeds four compact effect slots from the A3EE descriptor table.  It is still
    raw world-scroll bookkeeping, not a semantic level-completion model.
    """
    if self_disable_if_patched(cpu, 0xA66F, SIG_OBJECT_SCROLL_WORLD_PROGRESS_GATE_A66F, "overkill_object_scroll_world_progress_gate_a66f"):
        return
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    cs = s.cs & 0xFFFF

    value = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, value, 0)
    if value != 0:
        s.ip = cpu.pop()
        return
    value = mem.rw(ds, 0xA47E)
    _cmp_word(cpu, value, 0)
    if value != 0:
        s.ip = cpu.pop()
        return
    value = mem.rw(ds, 0xA480)
    _cmp_word(cpu, value, 0)
    if value != 0:
        s.ip = cpu.pop()
        return

    cpu.push(0xA68A)
    run_object_scroll_forward_step_a6fe(cpu, self_disable_if_patched)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xA68A):
        raise RuntimeError(f"A66F expected A6FE to return to 1010:A68A, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    value = mem.rw(ds, 0x234E)
    _cmp_word(cpu, value, 0)
    if value != 0:
        s.ip = cpu.pop()
        return

    # PUSH AX,BX,CX,DX,DI,SI,BP,ES,DS
    for value in (s.ax, s.bx, s.cx, s.dx, s.di, s.si, s.bp, s.es, s.ds):
        cpu.push(value)
    s.si = 0xA982
    value_2350 = mem.rw(ds, 0x2350)
    _cmp_word(cpu, value_2350, 0x0E52)
    if value_2350 == 0x0E52:
        _run_interpreted_near_call_observed(cpu, 0xC591, 0xA6A8, max_steps=12000)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xA6A8):
            raise RuntimeError(f"A66F expected C591 to return to 1010:A6A8, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
    # POP DS,ES,BP,SI,DI,DX,CX,BX,AX
    s.ds = cpu.pop()
    s.es = cpu.pop()
    s.bp = cpu.pop()
    s.si = cpu.pop()
    s.di = cpu.pop()
    s.dx = cpu.pop()
    s.cx = cpu.pop()
    s.bx = cpu.pop()
    s.ax = cpu.pop()
    ds = s.ds & 0xFFFF

    value_2350 = mem.rw(ds, 0x2350)
    _cmp_word(cpu, value_2350, 0x0EA0)
    if value_2350 != 0x0EA0:
        s.ip = cpu.pop()
        return

    mem.ww(ds, 0xA47C, 0x0001)
    _run_interpreted_near_call_observed(cpu, 0x62AA, 0xA6C2, max_steps=60000)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xA6C2):
        raise RuntimeError(f"A66F expected 62AA to return to 1010:A6C2, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    s.si = 0xA3EE
    s.cx = 0x0004
    while True:
        cpu.push(s.cx)
        cpu.push(s.si)
        _run_interpreted_near_call_observed(cpu, 0x7524, 0xA6CD, max_steps=20000)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xA6CD):
            raise RuntimeError(f"A66F expected 7524 to return to 1010:A6CD, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
        s.si = cpu.pop()
        _cmp_word(cpu, s.bx, 0xFFFF)
        if s.bx != 0xFFFF:
            bx = s.bx & 0xFFFF
            dst = ObjectSlotView(mem, ds, bx)  # the spawned/target object's record (DS:BX)
            dst.active_word = 0x0001
            dst.scan_flag = 0x0002
            dst.hazard_class = 0x0004
            dst.logic_id = 0x0053
            dst.linked_counter_index = 0xFFFF
            s.ax = mem.rw(ds, s.si)
            s.si = (s.si + 2) & 0xFFFF
            dst.x_word = s.ax
            s.ax = mem.rw(ds, s.si)
            s.si = (s.si + 2) & 0xFFFF
            dst.y_word = s.ax
            s.ax = mem.rw(ds, s.si)
            s.si = (s.si + 2) & 0xFFFF
            dst.sprite_or_state = s.ax
            mem.ww(ds, (bx + 0x36) & 0xFFFF, s.ax)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF
        if s.cx == 0:
            s.ip = cpu.pop()
            return


def run_object_scroll_forward_row_a74e(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A74E, the forward map/scroll-row advance side effect.

    The heavy display copy at A7EB remains a bounded original child for now.
    This wrapper names the finite bookkeeping around it: advance DS:2350 by one
    13-byte tile row, decrement the remaining row counter DS:A978, optionally
    notify the sound/transition helper at CB1C, and mark DS:2354 as forward.
    """
    if self_disable_if_patched(cpu, 0xA74E, SIG_OBJECT_SCROLL_FORWARD_ROW_A74E, "overkill_object_scroll_forward_row_a74e"):
        return
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    _run_interpreted_near_call_observed(cpu, 0xA7EB, 0xA751, max_steps=60000)
    if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (0x1010, 0xA751):
        raise RuntimeError(f"A74E expected A7EB to return to 1010:A751, got {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}")

    value_2350 = mem.rw(ds, 0x2350)
    _cmp_word(cpu, value_2350, 0x00B6)
    if value_2350 <= 0x00B6:
        flag = mem.rb(ds, 0x98C0)
        _cmp_byte(cpu, flag, 0)
        if flag != 0:
            mem.wb(ds, 0xBEFF, 0x07)

    _add_mem_word(cpu, ds, 0x2350, 0x000D)
    _dec_mem_word_preserve_cf(cpu, ds, 0xA978)
    cpu.set_reg8(0, 0x05)
    value_a978 = mem.rw(ds, 0xA978)
    _cmp_word(cpu, value_a978, 0x0004)
    if value_a978 == 0x0004:
        _run_interpreted_near_call_observed(cpu, 0xCB1C, 0xA77A, max_steps=20000)
        if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (0x1010, 0xA77A):
            raise RuntimeError(f"A74E expected CB1C to return to 1010:A77A, got {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}")
    mem.ww(ds, 0x2354, 0x0000)
    cpu.s.ip = cpu.pop()


def run_object_scroll_backward_row_a7d0(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A7D0, the backward map/scroll-row bookkeeping side effect."""
    if self_disable_if_patched(cpu, 0xA7D0, SIG_OBJECT_SCROLL_BACKWARD_ROW_A7D0, "overkill_object_scroll_backward_row_a7d0"):
        return
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    _run_interpreted_near_call_observed(cpu, 0xA7EB, 0xA7D3, max_steps=60000)
    if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (0x1010, 0xA7D3):
        raise RuntimeError(f"A7D0 expected A7EB to return to 1010:A7D3, got {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}")
    _sub_mem_word(cpu, ds, 0x2350, 0x000D)
    _inc_mem_word_preserve_cf(cpu, ds, 0xA978)
    mem.ww(ds, 0x2354, 0x0001)
    cpu.s.ip = cpu.pop()


def run_object_scroll_row_wrap_forward_a746(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A746, wrapping the source row pointer to CS:95C0."""
    if self_disable_if_patched(cpu, 0xA746, SIG_OBJECT_SCROLL_ROW_WRAP_A746, "overkill_object_scroll_row_wrap_forward_a746"):
        return
    cs = cpu.s.cs & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    cpu.s.ax = cpu.mem.rw(cs, 0x95C0)
    cpu.mem.ww(ds, 0x234C, cpu.s.ax)
    cpu.s.ip = cpu.pop()


def run_object_scroll_row_wrap_backward_a7e3(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A7E3, wrapping the source row pointer to CS:95BE."""
    if self_disable_if_patched(cpu, 0xA7E3, SIG_OBJECT_SCROLL_ROW_WRAP_A7E3, "overkill_object_scroll_row_wrap_backward_a7e3"):
        return
    cs = cpu.s.cs & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    cpu.s.ax = cpu.mem.rw(cs, 0x95BE)
    cpu.mem.ww(ds, 0x234C, cpu.s.ax)
    cpu.s.ip = cpu.pop()


def run_object_scroll_forward_step_a6fe(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A6FE, one forward vertical-scroll bookkeeping step.

    This is still raw scroll/map bookkeeping, not a semantic camera system: it
    advances the sub-row phase counters, occasionally pulls the next tile row
    through A74E, wraps the source row pointer, and returns.
    """
    if self_disable_if_patched(cpu, 0xA6FE, SIG_OBJECT_SCROLL_FORWARD_STEP_A6FE, "overkill_object_scroll_forward_step_a6fe"):
        return
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    cpu.push(cpu.s.bp)
    _add_mem_word(cpu, ds, 0xA278, 0x0001)
    mem.ww(ds, 0x2352, 0x0000)
    value_234e = mem.rw(ds, 0x234E)
    _cmp_word(cpu, value_234e, 0)
    if value_234e == 0:
        cpu.push(0xA714)
        run_object_scroll_forward_row_a74e(cpu, self_disable_if_patched)
        if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (cs, 0xA714):
            raise RuntimeError(f"A6FE expected A74E to return to 1010:A714, got {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}")
    _dec_mem_word_preserve_cf(cpu, ds, 0x234E)
    _and_mem_word(cpu, ds, 0x234E, 0x000F)
    if mem.rw(ds, 0x234E) == 0:
        value_2354 = mem.rw(ds, 0x2354)
        _cmp_word(cpu, value_2354, 0)
        if value_2354 != 0:
            _add_mem_word(cpu, ds, 0x2350, 0x000D)
            _dec_mem_word_preserve_cf(cpu, ds, 0xA978)
    cpu.s.ax = mem.rw(cs, 0x95BE)
    _cmp_word(cpu, mem.rw(ds, 0x234C), cpu.s.ax)
    if mem.rw(ds, 0x234C) == cpu.s.ax:
        cpu.push(0xA73C)
        run_object_scroll_row_wrap_forward_a746(cpu, self_disable_if_patched)
        if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (cs, 0xA73C):
            raise RuntimeError(f"A6FE expected A746 to return to 1010:A73C, got {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}")
    cpu.s.ax = mem.rw(cs, 0x959E)
    _sub_mem_word(cpu, ds, 0x234C, cpu.s.ax)
    cpu.s.bp = cpu.pop()
    cpu.s.ip = cpu.pop()


def run_object_scroll_backward_step_a781(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A781, one backward vertical-scroll bookkeeping step."""
    if self_disable_if_patched(cpu, 0xA781, SIG_OBJECT_SCROLL_BACKWARD_STEP_A781, "overkill_object_scroll_backward_step_a781"):
        return
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    cpu.push(cpu.s.bp)
    mem.ww(ds, 0x2352, 0x0001)
    value_2350 = mem.rw(ds, 0x2350)
    _cmp_word(cpu, value_2350, 0)
    if value_2350 == 0:
        cpu.s.bp = cpu.pop()
        cpu.s.ip = cpu.pop()
        return
    _add_mem_word(cpu, ds, 0xA278, 0xFFFF)
    value_234e = mem.rw(ds, 0x234E)
    _cmp_word(cpu, value_234e, 0)
    if value_234e == 0:
        cpu.push(0xA79E)
        run_object_scroll_backward_row_a7d0(cpu, self_disable_if_patched)
        if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (cs, 0xA79E):
            raise RuntimeError(f"A781 expected A7D0 to return to 1010:A79E, got {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}")
    _inc_mem_word_preserve_cf(cpu, ds, 0x234E)
    _and_mem_word(cpu, ds, 0x234E, 0x000F)
    if mem.rw(ds, 0x234E) == 0:
        value_2354 = mem.rw(ds, 0x2354)
        _cmp_word(cpu, value_2354, 1)
        if value_2354 != 1:
            _sub_mem_word(cpu, ds, 0x2350, 0x000D)
            _inc_mem_word_preserve_cf(cpu, ds, 0xA978)
    cpu.s.ax = mem.rw(cs, 0x95C0)
    _cmp_word(cpu, mem.rw(ds, 0x234C), cpu.s.ax)
    if mem.rw(ds, 0x234C) == cpu.s.ax:
        cpu.push(0xA7C6)
        run_object_scroll_row_wrap_backward_a7e3(cpu, self_disable_if_patched)
        if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (cs, 0xA7C6):
            raise RuntimeError(f"A781 expected A7E3 to return to 1010:A7C6, got {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}")
    cpu.s.ax = mem.rw(cs, 0x959E)
    _add_mem_word(cpu, ds, 0x234C, cpu.s.ax)
    cpu.s.bp = cpu.pop()
    cpu.s.ip = cpu.pop()


def _run_af22_three_pixel_step_for_direction(cpu, *, parent: str = "1010:AF22") -> None:
    """Mirror 1010:AF22: one 3-pixel diagonal/cardinal step by SS:[BP+06]."""
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    direction = slot.direction_or_step & 0xFFFF
    cpu.s.bx = direction
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
    if direction > 7:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain="AF22 direction table",
            target_ip=cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAF2C + ((direction << 1) & 0xFFFF)) & 0xFFFF),
            bp=bp,
            cx_value=cpu.s.cx & 0xFFFF,
        )
    apply_direction_step_to_current_object(cpu, direction=direction, pixels=3)


def run_object_target_chase_d281(cpu, self_disable_if_patched) -> None:
    """Lift 1010:D281, an observed target-copy + 5DB2 movement helper tail.

    The routine copies target Y/X words from the current object frame
    (SS:[BP+32h]/[BP+34h]) into DS:2304/2306, selects movement mode 1 for the
    first 5DB2 call, then mode 2 for follow-up state.  In the cold-start demo
    path DS:230A remains zero and the routine returns immediately to the object
    scan tail.  If 5DB2 reports the unobserved blocked/no-direction case, keep
    the rest of D2A4+ as bounded original code rather than guessing it.
    """
    if self_disable_if_patched(
        cpu,
        0xD281,
        SIG_OBJECT_TARGET_CHASE_D281,
        "overkill_object_target_chase_d281",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    s.ax = slot.target_y_word
    mem.ww(ds, 0x2304, s.ax)
    s.ax = slot.target_x_word
    mem.ww(ds, 0x2306, s.ax)
    mem.ww(ds, 0x2308, 0x0001)

    cpu.push(0xD296)
    _run_movement_direction_5db2(cpu)
    ret = cpu.pop()
    if ret != 0xD296:
        raise RuntimeError(f"D281 expected 5DB2 return D296, got {ret:04X}")

    mem.ww(ds, 0x2308, 0x0002)
    blocked = mem.rw(ds, 0x230A)
    _cmp_word(cpu, blocked, 0)
    if blocked == 0:
        s.ip = cpu.pop()
        return

    # D2A1 JNZ +1 skips the RET at D2A3 and continues at D2A4.  Preserve the
    # original caller's return word by turning that tail into a bounded near call
    # with the same return IP.
    caller_ret = cpu.pop()
    _run_interpreted_near_call_observed(cpu, 0xD2A4, caller_ret, max_steps=12000)


def _run_af63_step_for_direction(cpu, *, parent: str = "1010:AF63") -> None:
    """Mirror one 1010:AF63 2-pixel direction step.

    AF63 dispatches through the CS:AF6E table using SS:[BP+06].  AF60 is built
    from this same body with a self-call trick, so keeping the one-step body
    separate lets 5DB2 mode 1 (direct AF63) and mode 2 (AF60 double step) share
    exactly the same movement mapping.
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    direction = slot.direction_or_step & 0xFFFF
    cpu.s.bx = direction
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1 before table JMP.
    if direction > 7:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain="AF63 direction table",
            target_ip=cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAF6E + ((direction << 1) & 0xFFFF)) & 0xFFFF),
            bp=bp,
            cx_value=cpu.s.cx & 0xFFFF,
        )
    apply_direction_step_to_current_object(cpu, direction=direction, pixels=2)


def _run_af60_double_step_for_direction(cpu) -> None:
    """Mirror 1010:AF60 for the movement helper's speed-2 mode.

    AF60 is another OVERKILL self-call trick: ``CALL AF63`` pushes AF63, so
    the direction movement body runs once, RET returns to AF63, and the same
    body runs a second time before returning to the original caller.
    """
    _run_af63_step_for_direction(cpu, parent="1010:AF60")
    _run_af63_step_for_direction(cpu, parent="1010:AF60")


def run_movement_dir_double_step_2px_af60(cpu, self_disable_if_patched) -> None:
    """Hook entry for 1010:AF60, the self-call double 2-pixel step.

    The original is ``CALL AF63`` followed by the AF63 body.  The near CALL
    pushes ``AF63`` as scratch, the first AF63 RET returns to the AF63 entry,
    and the second AF63 RET returns to the real caller.  Registering AF60 closes
    the direct-entry blind spot while preserving the scratch word below SP.
    """
    if self_disable_if_patched(
        cpu,
        0xAF60,
        SIG_MOVEMENT_DOUBLE_STEP_2PX_AF60,
        "overkill_movement_dir_double_step_2px_af60",
    ):
        return
    _run_af60_double_step_for_direction(cpu)
    cpu.s.ip = cpu.pop()


def run_movement_dir_step_2px_af63(cpu, self_disable_if_patched) -> None:
    """Hook entry for 1010:AF63, the 2-pixel 8-direction movement step table.

    The body is already lifted as ``_run_af63_step_for_direction`` and shared by
    the 5DB2/5E42/AF60 parents.  This wrapper registers the same body at the
    exact ASM entry so a *direct* ``CALL AF63`` (for example from 1010:89FF/8A1D)
    is hook-covered instead of interpreted.  The routine is a near-return.
    """
    if self_disable_if_patched(
        cpu,
        0xAF63,
        SIG_MOVEMENT_DIR_STEP_2PX_AF63,
        "overkill_movement_dir_step_2px_af63",
    ):
        return
    _run_af63_step_for_direction(cpu)
    cpu.s.ip = cpu.pop()


def run_movement_dir_step_3px_af22(cpu, self_disable_if_patched) -> None:
    """Hook entry for 1010:AF22, the 3-pixel 8-direction movement step table.

    Same dispatch shape as AF63 with a 3-pixel delta; body lifted as
    ``_run_af22_three_pixel_step_for_direction``.  Near-return entry wrapper.
    """
    if self_disable_if_patched(
        cpu,
        0xAF22,
        SIG_MOVEMENT_DIR_STEP_3PX_AF22,
        "overkill_movement_dir_step_3px_af22",
    ):
        return
    _run_af22_three_pixel_step_for_direction(cpu)
    cpu.s.ip = cpu.pop()


def run_movement_dir_step_8px_aee4(cpu, self_disable_if_patched) -> None:
    """Hook entry for 1010:AEE4, the 8-pixel 8-direction movement step table.

    Same dispatch shape as AF63 with an 8-pixel delta; body lifted as
    ``_run_aee4_step_for_direction``.  Near-return entry wrapper.
    """
    if self_disable_if_patched(
        cpu,
        0xAEE4,
        SIG_MOVEMENT_DIR_STEP_8PX_AEE4,
        "overkill_movement_dir_step_8px_aee4",
    ):
        return
    _run_aee4_step_for_direction(cpu)
    cpu.s.ip = cpu.pop()


def _run_aee4_step_for_direction(cpu) -> None:
    """Mirror 1010:AEE4: one 8-pixel direction step via the AEEE table."""
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    direction = slot.direction_or_step & 0xFFFF
    cpu.s.bx = direction
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
    if direction > 7:
        _raise_unverified_path(
            cpu,
            parent="1010:AEE4",
            chain="AEE4 direction table",
            target_ip=cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAEEE + ((direction << 1) & 0xFFFF)) & 0xFFFF),
            bp=bp,
            cx_value=cpu.s.cx & 0xFFFF,
        )
    apply_direction_step_to_current_object(cpu, direction=direction, pixels=8)


def _run_movement_direction_5db2(cpu) -> None:
    """Run the 1010:5DB2 target-seeking movement/direction helper.

    The helper compares object Y/X against DS:2304/2306, encodes the desired
    direction into DS:A954, maps that nibble through DS:A348 into the object's
    animation/direction word at SS:[BP+06], then dispatches through CS:5E0C by
    DS:2308.  For the currently opened object-logic island, the verified mode is
    DS:2308 == 2, which is the AF60 double 2-pixel step.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    slot = ObjectSlotView.from_ss_bp(cpu)
    pure_decision = decide_target_seek_direction_from_dos(cpu, slot)

    cpu.mem.ww(ds, MOVEMENT_DIRECTION_BITS, 0)
    cpu.mem.ww(ds, MOVEMENT_BLOCKED_FLAG, 0)

    y = slot.y_word
    target_y = cpu.mem.rw(ds, 0x2304)
    _cmp_word(cpu, y, target_y)
    if y < target_y:
        cpu.mem.ww(ds, MOVEMENT_DIRECTION_BITS, 1)
    elif y > target_y:
        cpu.mem.ww(ds, MOVEMENT_DIRECTION_BITS, 2)

    x = slot.x_word
    target_x = cpu.mem.rw(ds, 0x2306)
    _cmp_word(cpu, x, target_x)
    # Original uses signed JL/JG for X after CMP AX,DS:[2306].
    sx = x if x < 0x8000 else x - 0x10000
    starget_x = target_x if target_x < 0x8000 else target_x - 0x10000
    direction_bits = cpu.mem.rw(ds, MOVEMENT_DIRECTION_BITS)
    if sx < starget_x:
        direction_bits |= 0x0004
        cpu.mem.ww(ds, MOVEMENT_DIRECTION_BITS, direction_bits)
    elif sx > starget_x:
        direction_bits |= 0x0008
        cpu.mem.ww(ds, MOVEMENT_DIRECTION_BITS, direction_bits)

    if (direction_bits & 0xFFFF) != pure_decision.direction_bits:
        raise AssertionError(
            "pure 5DB2 target-seek direction bits disagree with ASM-compatible compares"
        )

    cpu.s.bx = 0xA348
    cpu.s.ax = cpu.mem.rw(ds, MOVEMENT_DIRECTION_BITS)
    mapped = cpu.mem.rb(ds, (cpu.s.bx + (cpu.s.ax & 0xFF)) & 0xFFFF)
    cpu.set_reg8(0, mapped)  # XLAT updates AL only.
    cpu.set_sub_flags(mapped, 0xFF, mapped - 0xFF, 8)  # CMP AL,FFh.
    if mapped != pure_decision.mapped_direction:
        raise AssertionError("pure 5DB2 direction-table result disagrees with XLAT")
    if mapped == 0xFF:
        if not pure_decision.blocked:
            raise AssertionError("pure 5DB2 blocked flag disagrees with CMP AL,FFh")
        cpu.mem.ww(ds, MOVEMENT_BLOCKED_FLAG, 1)
        # MOV word and RET do not affect flags; leave CMP AL,FFh flags live.
        return
    if pure_decision.blocked:
        raise AssertionError("pure 5DB2 blocked flag disagrees with movement dispatch path")

    slot.direction_or_step = cpu.s.ax
    cpu.s.bx = cpu.mem.rw(ds, MOVEMENT_MODE)
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1 before 5E0C table JMP.
    mode = cpu.mem.rw(ds, MOVEMENT_MODE)
    target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0x5E0C + ((mode << 1) & 0xFFFF)) & 0xFFFF)
    if target_ip == 0xAF63:
        _run_af63_step_for_direction(cpu, parent="1010:5DB2")
        return
    if target_ip == 0xAF60:
        _run_af60_double_step_for_direction(cpu)
        return
    if target_ip == 0xAEE4:
        _run_aee4_step_for_direction(cpu)
        return
    _raise_unverified_path(
        cpu,
        parent="1010:5DB2",
        chain="5DB2 -> 5E0C movement-mode dispatch",
        target_ip=target_ip,
        bp=bp,
        cx_value=cpu.s.cx & 0xFFFF,
    )


def _call_tile_lookup_505b(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0x505B, lambda c: run_tile_lookup_505b(c, _no_patch_guard), return_ip)


def _b00d_tile_is_blocking(cpu, return_ip: int) -> bool:
    _call_tile_lookup_505b(cpu, return_ip)
    return not bool(cpu.get_flag(ZF))


def _call_b00d_component(cpu, component, return_ip: int) -> None:
    """Simulate the internal CALL/RET used by diagonal B00D branches.

    B032 is a shared tail, not a global abort.  When a cardinal component is
    reached via CALL inside a diagonal branch, a JMP B032 returns to that
    component's internal caller, and the second component still runs.
    """
    cpu.push(return_ip & 0xFFFF)
    blocked = component(cpu)
    if not blocked:
        cpu.s.ip = cpu.pop()
    if (cpu.s.ip & 0xFFFF) != (return_ip & 0xFFFF):
        raise RuntimeError(f"B00D internal component expected return {return_ip:04X}, got {cpu.s.ip & 0xFFFF:04X}")


def _run_player_chase_candidate_scan_b15a(cpu) -> None:
    """Mirror B15A, the B1B0 target-acquisition scan over effect/contact slots.

    The pure predicate owns the candidate meaning; this adapter keeps the exact
    loop/cursor/register/flag behavior.  DS:A43A is a rotating cursor through
    the DS:23B4..2B5C pool.  On success the cursor advances to the next slot but
    BX is restored to the found slot, matching the original PUSH/ADD/STORE/POP.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    cpu.s.cx = 0x0023
    cpu.s.bx = mem.rw(ds, 0xA43A)

    while True:
        bx = cpu.s.bx & 0xFFFF
        _cmp_word(cpu, bx, GAMEPLAY_OBJECT_TABLE_BASE)
        if bx >= GAMEPLAY_OBJECT_TABLE_BASE:
            mem.ww(ds, 0xA43A, EFFECT_OBJECT_TABLE_BASE)
            cpu.s.bx = mem.rw(ds, 0xA43A)
            continue

        slot = ObjectSlotView.from_ds(cpu, bx)
        if run_player_chase_candidate_checks_b15a(cpu, slot):
            found_bx = bx
            cpu.push(found_bx)
            _add_reg16(cpu, 3, OBJECT_SLOT_STRIDE)
            mem.ww(ds, 0xA43A, cpu.s.bx & 0xFFFF)
            cpu.s.bx = cpu.pop()
            return

        _add_reg16(cpu, 3, OBJECT_SLOT_STRIDE)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        if cpu.s.cx == 0:
            cpu.s.bx = 0xFFFF
            return


def run_player_chase_candidate_scan_b15a(cpu, self_disable_if_patched) -> None:
    """Lift 1010:B15A as a standalone rotating target-candidate scan.

    This helper is shared by the B1B0 chase-acquisition behavior and by the
    A515 action/spawn link helper.  Keep the loop mechanics raw: DS:A43A is the
    cursor through DS:23B4..2B5C, BX returns either the found slot or FFFFh, and
    the pure object predicate owns only the candidate decision.
    """
    if self_disable_if_patched(
        cpu,
        0xB15A,
        SIG_OBJECT_PLAYER_CHASE_CANDIDATE_SCAN_B15A,
        "overkill_player_chase_candidate_scan_b15a",
    ):
        return

    _run_player_chase_candidate_scan_b15a(cpu)
    cpu.s.ip = cpu.pop()


def run_object_target_move_b729(cpu, self_disable_if_patched) -> None:
    """Lift 1010:B729, the object target-copy + 5DB2 movement prelude.

    B729 is the small source-like wrapper used by several object behaviours:
    copy the slot's observed target pair (``+32h/+34h``) into the shared 5DB2
    target globals, call the recovered target-seeking movement helper, compare
    the blocked flag, and return to the caller.  The nested 5DB2 call is routed
    through its hook boundary so verifier coverage still sees the child routine.
    """
    if self_disable_if_patched(cpu, 0xB729, SIG_OBJECT_TARGET_MOVE_B729, "overkill_object_target_move_b729"):
        return

    publish_object_slot_target_to_movement_globals(cpu, ObjectSlotView.from_ss_bp(cpu))

    def run_5db2(c):
        _run_movement_direction_5db2(c)
        c.s.ip = c.pop()

    _call_verified_child_near(cpu, 0x5DB2, run_5db2, 0xB738)
    if (cpu.s.ip & 0xFFFF) != 0xB738:
        raise RuntimeError(f"B729 expected 5DB2 to return to B738, got {cpu.s.ip:04X}")

    _cmp_word(cpu, cpu.mem.rw(cpu.s.ds & 0xFFFF, MOVEMENT_BLOCKED_FLAG), 0)
    cpu.s.ip = cpu.pop()
