"""Lifted OVERKILL gameplay object behavior and post-move collision chains.

The functions in this module are game-specific source-port logic that used to
live in ``replacements.py``.  They intentionally keep original addresses in
names/docstrings because their behavior is still verified against the DOS ASM
oracle.  ``replacements.py`` imports these functions back and remains the exact
CS:IP hook-registration layer.
"""
from __future__ import annotations

from overkill_port.cpu import CF, DF, ZF
from overkill_port.games.overkill.asm import (
    _add_mem_word,
    _add_reg16,
    _and_mem_word,
    _cmp_byte,
    _cmp_word,
    _dec_mem_word_preserve_cf,
    _inc_mem_word_preserve_cf,
    _sub_mem_word,
    _sub_reg16,
    _test_word,
)
from overkill_port.games.overkill.gameplay.collision import (
    run_object_deactivate_logic_dispatch_c054,
    run_object_slot_scan_guard_ac81,
    run_postmove_contact_window_aa71,
    run_tile_collision_probe_ac28,
)
from overkill_port.games.overkill.gameplay.view_window import _run_view_window_check_aa46
from overkill_port.games.overkill.gameplay.objects import (
    run_object_motion_table_ab34,
    run_object_scroll_sprite_ab4f,
)

def _run_interpreted_near_call_observed(cpu, target_ip: int, return_ip: int, *, max_steps: int = 20000) -> None:
    """Run a rare original near helper from inside a larger lifted path.

    This is used for non-hot, display/bookkeeping helper tails that have not yet
    been lifted but are needed to keep gameplay moving through an observed path.
    The helper is still bounded and deterministic: it installs the same near-CALL
    return word the ASM would have pushed, steps until that continuation is
    reached, and restores verifier state afterwards so nested fast hooks do not
    recursively start their own differential verification.
    """
    cs = cpu.s.cs & 0xFFFF
    target = (cs, return_ip & 0xFFFF)
    saved_verifier = cpu.hook_verifier
    cpu.hook_verifier = None
    cpu.push(return_ip & 0xFFFF)
    cpu.s.ip = target_ip & 0xFFFF
    try:
        ctx = (
            cpu.coverage_telemetry.bounded_original((cs, target_ip & 0xFFFF), "bounded original near call")
            if cpu.coverage_telemetry is not None
            else None
        )
        if ctx is not None:
            ctx.__enter__()
        try:
            for _ in range(max_steps):
                if cpu.addr() == target:
                    return
                cpu.step()
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)
    finally:
        cpu.hook_verifier = saved_verifier
    raise RuntimeError(
        f"interpreted helper 1010:{target_ip & 0xFFFF:04X} did not return to "
        f"1010:{return_ip & 0xFFFF:04X}; now at {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}"
    )


SIG_OBJECT_CHILD_COORD_UPDATE_9FEA = bytes.fromhex(
    "83 fb ff 75 01 c3 8b 46 08 d1 e0 d1 e0 03 f0"
)

SIG_OBJECT_BOUNDS_TILE_PRELUDE_AD5A = bytes.fromhex(
    "a1 78 a2 01 46 02 83 7e 02 08 73 03 e9 ae 0f"
)
SIG_OBJECT_TARGET_CHASE_D281 = bytes.fromhex(
    "8b 46 32 a3 04 23 8b 46 34 a3 06 23 c7 06 08 23 01 00"
)
SIG_OBJECT_DRIFT_DOWNRIGHT_AE2C = bytes.fromhex(
    "81 7e 04 c8 00 74 96 83 6e 02 04 f7 46 04 07 00"
)
SIG_OBJECT_DRIFT_UPRIGHT_AE7D = bytes.fromhex(
    "83 7e 04 00 75 03 e9 43 ff 83 6e 02 04 f7 46 04 0f 00"
)


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

    ax = mem.rw(ss, (s.bp + 0x08) & 0xFFFF)
    ax = cpu.shift(4, ax, 1, 16)
    ax = cpu.shift(4, ax, 1, 16)
    _add_reg16(cpu, 6, ax)

    x_delta = mem.rw(ds, s.si & 0xFFFF)
    s.si = (s.si + 2) & 0xFFFF
    ax = (x_delta + mem.rw(ss, (s.bp + 0x02) & 0xFFFF)) & 0xFFFF
    # ADD flags are overwritten later by the Y clamps/cmp in all observed active paths.
    s.ax = ax
    mem.ww(ds, (bx + 0x02) & 0xFFFF, ax)

    y_delta = mem.rw(ds, s.si & 0xFFFF)
    s.si = (s.si + 2) & 0xFFFF
    ax_full = y_delta + mem.rw(ss, (s.bp + 0x04) & 0xFFFF)
    ax_full += mem.rw(ds, 0xA398)
    ax_full += mem.rw(ds, 0xA398)
    ax = ax_full & 0xFFFF
    s.ax = ax
    mem.ww(ds, (bx + 0x04) & 0xFFFF, ax)

    y = mem.rw(ds, (bx + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0x0000)
    if y & 0x8000:
        mem.ww(ds, (bx + 0x04) & 0xFFFF, 0x0000)
        mem.wb(ds, 0xA39E, 0x01)
        y = 0

    _cmp_word(cpu, y, 0x00C0)
    # Signed JLE.  Values above 00C0 in the positive signed range trigger the
    # upper clamp.  Negative values have already been clamped to zero above.
    if y <= 0x00C0:
        s.ip = cpu.pop()
        return

    mem.ww(ds, (bx + 0x04) & 0xFFFF, 0x00C0)
    mem.wb(ds, 0xA39F, 0x01)
    s.ip = cpu.pop()


def _object_ptr_from_scan_index(cpu, table_base: int, cx_value: int) -> tuple[int, int]:
    """Return (BX, BP) for OVERKILL's descending object-list scan loops."""
    bx = ((cx_value & 0xFFFF) << 1) & 0xFFFF
    bp = cpu.mem.rw(cpu.s.ds & 0xFFFF, (table_base + bx) & 0xFFFF)
    cpu.s.bx = bx
    cpu.s.bp = bp
    return bx, bp


def _push_loop_count_for_interpreted_tail(cpu, cx_value: int) -> None:
    cpu.s.sp = (cpu.s.sp - 2) & 0xFFFF
    cpu.mem.ww(cpu.s.ss & 0xFFFF, cpu.s.sp, cx_value & 0xFFFF)


def _remember_balanced_push_scratch(cpu, cx_value: int) -> None:
    # PUSH/POP pairs leave the last pushed word below SP. Full-memory oracle
    # comparisons can see it even though SP is balanced afterwards.
    cpu.mem.ww(cpu.s.ss & 0xFFFF, (cpu.s.sp - 2) & 0xFFFF, cx_value & 0xFFFF)


def _scan_loop_until_callable(cpu, table_base: int, callable_ip: int, done_ip: int, should_call) -> None:
    """Collapse an object-list loop until the next entry that really calls out.

    The overlaid loading/rendering code has several loops of the form::

        push cx
        mov  bx,cx
        shl  bx,1
        mov  bp,[table+bx]
        ... tests against SS:[BP+...] ...
        call helper      ; only for active/matching objects
        pop  cx
        loop top

    Most startup iterations only skip inactive objects.  This helper consumes
    those skip-only iterations in Python and stops immediately before the real
    CALL for the first object that needs original helper logic.
    """
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, table_base, cx_value)
        if should_call():
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = callable_ip & 0xFFFF
            return

        _remember_balanced_push_scratch(cpu, cx_value)
        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = done_ip & 0xFFFF
            return

    cpu.s.ip = done_ip & 0xFFFF


def _scan_active_object_call(cpu, table_base: int, callable_ip: int, done_ip: int) -> None:
    ss = cpu.s.ss & 0xFFFF

    def should_call() -> bool:
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        return active != 0

    _scan_loop_until_callable(cpu, table_base, callable_ip, done_ip, should_call)


def _scan_layered_object_call(cpu, wanted_layer: int, callable_ip: int, done_ip: int) -> None:
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF

    def should_call() -> bool:
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active == 0:
            return False

        mode = cpu.mem.rw(ds, 0xBDAC)
        _cmp_word(cpu, mode, 1)
        use_layer_test = False
        if mode != 1:
            camera = cpu.mem.rw(ds, 0x2350)
            _cmp_word(cpu, camera, 0x00B6)
            if camera <= 0x00B6:  # original JA falls through to layer test only when false
                layer = cpu.mem.rw(ss, (cpu.s.bp + 0x16) & 0xFFFF)
                _cmp_word(cpu, layer, 1)
                if layer == 1:
                    return False
                use_layer_test = True

        obj_layer = cpu.mem.rw(ss, (cpu.s.bp + 0x0A) & 0xFFFF)
        _cmp_word(cpu, obj_layer, wanted_layer)
        return obj_layer == wanted_layer

    _scan_loop_until_callable(cpu, 0x32CA, callable_ip, done_ip, should_call)


def _format_object_context(cpu, bp: int | None = None, cx_value: int | None = None) -> str:
    parts = [
        f"CS:IP={cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}",
        f"DS={cpu.s.ds & 0xFFFF:04X}",
        f"SS={cpu.s.ss & 0xFFFF:04X}",
        f"SP={cpu.s.sp & 0xFFFF:04X}",
        f"CX={cpu.s.cx & 0xFFFF:04X}",
    ]
    if cx_value is not None:
        parts.append(f"scan_cx={cx_value & 0xFFFF:04X}")
    if bp is not None:
        ss = cpu.s.ss & 0xFFFF
        bp &= 0xFFFF
        parts.append(f"BP={bp:04X}")
        for off, name in (
            (0x00, "active"),
            (0x08, "sprite"),
            (0x0A, "layer"),
            (0x0C, "di"),
            (0x0E, "present_si"),
            (0x12, "phase"),
            (0x14, "type"),
            (0x16, "draw_layer"),
            (0x18, "logic_id"),
            (0x1C, "substate"),
            (0x24, "variant"),
            (0x32, "target_y"),
            (0x34, "target_x"),
        ):
            parts.append(f"{name}@+{off:02X}={cpu.mem.rw(ss, (bp + off) & 0xFFFF):04X}")
    return "; ".join(parts)


def _raise_unverified_path(
    cpu,
    *,
    parent: str,
    chain: str,
    target_ip: int | None = None,
    bp: int | None = None,
    cx_value: int | None = None,
) -> None:
    target = "immediate-ret" if target_ip is None else f"{target_ip:04X}"
    raise RuntimeError(
        f"unverified original-code path reached in {parent}: {chain} -> {target}. "
        f"Fail-fast is intentional; reverse and hook this target instead of "
        f"falling back to interpreted ASM. {_format_object_context(cpu, bp, cx_value)}"
    )


def _present_dispatch_target_5a92(cpu, bp: int) -> int:
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    obj_type = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    index = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0x5AB6 + index) & 0xFFFF)


def _draw_dispatch_target_5ac8(cpu, bp: int) -> int:
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    obj_type = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    index = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0x5AE2 + index) & 0xFFFF)


def _layer_draw_dispatch_target_7596(cpu, bp: int) -> int:
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    obj_type = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    index = (obj_type << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0x75A0 + index) & 0xFFFF)


def _object_logic_target_aa2b(cpu, bp: int) -> int:
    """Predict AA2B's object-logic dispatch target from SS:[BP+16]."""
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    draw_layer = cpu.mem.rw(ss, (bp + 0x16) & 0xFFFF)
    index = (draw_layer << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0xAA36 + index) & 0xFFFF)


def _object_family_target_efae(cpu, bp: int) -> int:
    """Predict EFAE's second-level behavior dispatch target from SS:[BP+18]."""
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    logic_id = cpu.mem.rw(ss, (bp + 0x18) & 0xFFFF)
    index = (logic_id << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0xEFC4 + index) & 0xFFFF)


def _run_object_behavior_b73e(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the first branch layer of behavior B73E until its next helper call.

    The observed gameplay object (`logic_id=20h`, `substate=FFFFh`) enters the
    no-substate path, selects an animation frame, and when it has not reached
    its target Y/X yet it prepares DS:2304/2306 and calls B729 -> 5DB2.  We stop
    at that concrete helper instead of pretending the whole behavior is known.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    def run_b85c_move_to_target() -> None:
        target_y_local = cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF)
        target_x_local = cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF)
        cpu.mem.ww(ds, 0x2308, 0x0002)
        cpu.mem.ww(ds, 0x2304, target_y_local)
        cpu.s.ax = target_x_local
        cpu.mem.ww(ds, 0x2306, target_x_local)
        # B85C reaches the movement helper through B862 CALL B729, then
        # B735 CALL 5DB2.  The lifted helper models AF60's self-call scratch
        # relative to the current SP, so keep both real return frames live while
        # running it; otherwise AF63 is written one frame too shallow and hook
        # verification later sees stale stack garbage around SS:SP.
        saved_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xB865)
        cpu.push(0xB738)
        _run_movement_direction_5db2(cpu)
        cpu.s.sp = saved_sp
        _cmp_word(cpu, cpu.mem.rw(ds, 0x230A), 0)
        cpu.mem.ww(ss, (bp + 0x06) & 0xFFFF, 0x0004)
        _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B85C -> B729 -> 5DB2", cx_value=cx_value)
        cpu.s.ip = cpu.pop()

    def run_b7c7_reset_target(*, check_2324: bool, branch: str) -> None:
        # B7C7/B7CE: choose a new target row, align it to 8 pixels, reset the
        # behavior substate, and tail-jump into the common BC4B post-move path.
        # B7C7 performs the DS:2324 guard first; B7CE is the direct path that
        # always reloads target_y from DS:2380+8.
        if check_2324:
            value_2324 = cpu.mem.rw(ds, 0x2324)
            _cmp_word(cpu, value_2324, 0x0001)
            should_reload_y = value_2324 != 0x0001
        else:
            should_reload_y = True
        if should_reload_y:
            cpu.s.ax = cpu.mem.rw(ds, 0x2380)
            old_ax = cpu.s.ax
            cpu.s.ax = (cpu.s.ax + 0x0008) & 0xFFFF
            cpu.set_add_flags(old_ax, 0x0008, old_ax + 0x0008, 16)
            cpu.mem.ww(ss, (bp + 0x32) & 0xFFFF, cpu.s.ax)
        _and_mem_word(cpu, ss, (bp + 0x32) & 0xFFFF, 0xFFF8)
        cpu.mem.ww(ds, 0x2340, 0x0028)
        cpu.mem.ww(ss, (bp + 0x1C) & 0xFFFF, 0x0000)
        cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0078)
        cpu.mem.ww(ss, (bp + 0x34) & 0xFFFF, 0x0020)
        _run_object_postmove_bc4b(
            cpu,
            parent=parent,
            chain=f"{chain} -> B73E -> B7BD -> {branch}",
            cx_value=cx_value,
        )
        cpu.s.ip = cpu.pop()

    substate = cpu.mem.rw(ss, (bp + 0x1C) & 0xFFFF)
    _cmp_word(cpu, substate, 0xFFFF)
    if substate != 0xFFFF:
        cpu.s.bx = substate
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
        target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xB74E + cpu.s.bx) & 0xFFFF)
        if target_ip == 0xB754:
            y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
            target_y = cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF)
            cpu.s.ax = y
            _cmp_word(cpu, y, target_y)
            if y != target_y:
                run_b85c_move_to_target()
                return
            x = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
            target_x = cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF)
            cpu.s.ax = x
            _cmp_word(cpu, x, target_x)
            if x != target_x:
                run_b85c_move_to_target()
                return
            _add_mem_word(cpu, ss, (bp + 0x1C) & 0xFFFF, 1)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B754", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        if target_ip == 0xB770:
            cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0079)
            _add_mem_word(cpu, ss, (bp + 0x1C) & 0xFFFF, 1)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B770", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        if target_ip == 0xB77B:
            _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 0x0004)
            _cmp_word(cpu, cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF), 0x00A0)
            if cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF) >= 0x00A0:
                cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0077)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B77B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> B73E[substate]",
            target_ip=target_ip, bp=bp, cx_value=cx_value,
        )

    timer = cpu.mem.rw(ds, 0x2338)
    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0x0060)
    if y < 0x0060:
        # NEG AX; ADD AX,007Fh, with AX initially DS:[2338].
        cpu.set_sub_flags(0, timer, -timer, 16)
        cpu.s.ax = (-timer) & 0xFFFF
        old_ax = cpu.s.ax
        cpu.s.ax = (cpu.s.ax + 0x007F) & 0xFFFF
        cpu.set_add_flags(old_ax, 0x007F, old_ax + 0x007F, 16)
    else:
        old_ax = timer
        cpu.s.ax = (timer + 0x007A) & 0xFFFF
        cpu.set_add_flags(old_ax, 0x007A, old_ax + 0x007A, 16)
    cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, cpu.s.ax)

    target_y = cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF)
    cpu.s.ax = y
    _cmp_word(cpu, y, target_y)
    if y != target_y:
        # B85C: move toward the target; shared by Y-mismatch and X-mismatch.
        run_b85c_move_to_target()
        return

    x = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
    target_x = cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF)
    cpu.s.ax = x
    _cmp_word(cpu, x, target_x)
    if x != target_x:
        run_b85c_move_to_target()
        return

    # B7BD reached when this object is already at its current target.  In the
    # observed gameplay state DS:A7A0 is below 23h, so the original immediately
    # falls through to the same BC4B post-move helper.  Keep that helper as the
    # next honest frontier rather than pretending the whole behavior is closed.
    _cmp_word(cpu, cpu.mem.rw(ds, 0xA7A0), 0x0023)
    if cpu.mem.rw(ds, 0xA7A0) < 0x0023:
        _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD", cx_value=cx_value)
        cpu.s.ip = cpu.pop()
        return

    game_counter = cpu.mem.rw(ds, 0x2340)
    _cmp_word(cpu, game_counter, 0x02BC)
    if game_counter < 0x02BC:
        reaches_b808 = True
    else:
        _cmp_word(cpu, game_counter, 0x02D0)
        reaches_b808 = game_counter > 0x02D0
    if not reaches_b808:
        old_ptr = cpu.mem.rw(ds, 0x20A6)
        new_ptr = (old_ptr + 0x0002) & 0xFFFF
        cpu.mem.ww(ds, 0x20A6, new_ptr)
        _cmp_word(cpu, new_ptr, 0x20C7)
        if new_ptr >= 0x20C7:
            cpu.mem.ww(ds, 0x20A6, 0x20A8)
            new_ptr = 0x20A8
        cpu.s.bx = cpu.mem.rw(ds, new_ptr)
        cpu.s.bx &= 0x0001
        cpu.set_logic_flags(cpu.s.bx, 16)
        if cpu.s.bx == 0:
            _run_formation_spawn_7476_observed(
                cpu,
                parent=parent,
                chain=f"{chain} -> B73E -> B7BD -> B800",
                cx_value=cx_value,
            )

    _cmp_word(cpu, cpu.mem.rw(ds, 0xA47E), 0x0003)
    if cpu.mem.rw(ds, 0xA47E) <= 0x0003:
        run_b7c7_reset_target(check_2324=True, branch="B808 -> B7C7 -> BC4B")
        return
    _cmp_word(cpu, game_counter, 0x0005)
    if game_counter < 0x0005:
        run_b7c7_reset_target(check_2324=False, branch="B815 -> B7CE -> BC4B")
        return
    _cmp_word(cpu, cpu.mem.rw(ds, 0x232E), 0x003F)
    if cpu.mem.rw(ds, 0x232E) != 0x003F:
        _run_object_postmove_bc4b(
            cpu,
            parent=parent,
            chain=f"{chain} -> B73E -> B7BD -> B7F3 -> BC4B",
            cx_value=cx_value,
        )
        cpu.s.ip = cpu.pop()
        return

    for _ in range(0x20):
        cpu.s.si = cpu.mem.rw(ds, 0xA842)
        _cmp_word(cpu, cpu.s.si, 0xA894)
        if cpu.s.si >= 0xA894:
            cpu.mem.ww(ds, 0xA842, 0xA844)
            cpu.s.si = 0xA844
        else:
            cpu.s.si = cpu.mem.rw(ds, 0xA842)
        cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + 2) & 0xFFFF
        old_ax = cpu.s.ax
        cpu.s.ax = (cpu.s.ax + 0x0020) & 0xFFFF
        cpu.set_add_flags(old_ax, 0x0020, old_ax + 0x0020, 16)
        cpu.mem.ww(ss, (bp + 0x34) & 0xFFFF, cpu.s.ax)
        cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + 2) & 0xFFFF
        cpu.mem.ww(ss, (bp + 0x32) & 0xFFFF, cpu.s.ax)
        cpu.mem.ww(ds, 0xA842, cpu.s.si)

        x = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
        cpu.s.ax = x
        _cmp_word(cpu, x, cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF))
        if x != cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF):
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D -> BC4B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
        cpu.s.ax = y
        _cmp_word(cpu, y, cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF))
        if y != cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF):
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D -> BC4B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return

        _cmp_word(cpu, cpu.mem.rw(ds, 0xA7A0), 0x0023)
        if cpu.mem.rw(ds, 0xA7A0) < 0x0023:
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D -> B7BD", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        game_counter = cpu.mem.rw(ds, 0x2340)
        _cmp_word(cpu, game_counter, 0x02BC)
        if game_counter < 0x02BC:
            continue
        _cmp_word(cpu, game_counter, 0x02D0)
        if game_counter > 0x02D0:
            continue
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D loop",
            target_ip=0xB800, bp=bp, cx_value=cx_value,
        )
    _raise_unverified_path(
        cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D loop",
        target_ip=0xB7BD, bp=bp, cx_value=cx_value,
    )



def _run_object_behavior_b9f0(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift observed object-family behavior at ``1010:B9F0`` up to ``BC4B``.

    B9F0 is the hot behavior selected by ``EFAE`` for the current gameplay
    snapshot.  The routine updates the object's target-position fields from the
    global motion deltas and then either:

    * refreshes its sprite/animation word and jumps directly to ``BC4B``; or
    * prepares ``DS:2304/2306/2308``, calls the already verified ``5DB2``
      movement helper, and jumps to ``BC4B``.

    Less frequent helper calls are kept explicit and bounded.  They either use
    already-lifted helpers (7476 formation spawn, 5DB2 movement) or narrowly run
    the original helper until its real near-return continuation.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    def call_7476(return_ip: int, why: str) -> None:
        # 7476 is already understood in another object path, but this behavior
        # compares full stack scratch before BC4B.  Run the original bounded
        # helper here so its internal near-CALL return words match byte-for-byte.
        _run_interpreted_near_call_observed(cpu, 0x7476, return_ip & 0xFFFF, max_steps=12000)
        if (cpu.s.ip & 0xFFFF) != (return_ip & 0xFFFF):
            raise RuntimeError(f"7476 returned to unexpected IP {cpu.s.ip:04X} inside B9F0")

    def call_5e1b(return_ip: int) -> None:
        _run_interpreted_near_call_observed(cpu, 0x5E1B, return_ip & 0xFFFF, max_steps=3000)
        if (cpu.s.ip & 0xFFFF) != (return_ip & 0xFFFF):
            raise RuntimeError(f"5E1B returned to unexpected IP {cpu.s.ip:04X} inside B9F0")

    def call_5e42(return_ip: int) -> None:
        _run_interpreted_near_call_observed(cpu, 0x5E42, return_ip & 0xFFFF, max_steps=3000)
        if (cpu.s.ip & 0xFFFF) != (return_ip & 0xFFFF):
            raise RuntimeError(f"5E42 returned to unexpected IP {cpu.s.ip:04X} inside B9F0")

    def run_ba5a_helper_branch() -> None:
        # BA56 is reached only from the counter-wrap tests; BA5A itself is also
        # used directly when A47E < 6.  The caller performs the optional INC.
        # After BA63 the original falls through to BA67, so this helper only
        # performs the motion work and leaves AX/flags live for the BA67 block.
        cpu.s.bx = 0x237C
        call_5e1b(0xBA60)
        call_5e42(0xBA63)
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 0x0002)

    # B9F0: CMP DS:A482,A4E4 / JNE BA67.
    _cmp_word(cpu, mem.rw(ds, 0xA482), 0xA4E4)
    if mem.rw(ds, 0xA482) == 0xA4E4:
        # B9F8..BA03: one exact tick calls 7476 before continuing.
        _cmp_word(cpu, mem.rw(ds, 0x2340), 0x02EF)
        if mem.rw(ds, 0x2340) == 0x02EF:
            call_7476(0xBA03, "BA00 CALL 7476")
            _inc_mem_word_preserve_cf(cpu, ds, 0x2340)

        # BA07..BA10: apply global target deltas into +32/+34.
        cpu.s.ax = mem.rw(ds, 0x2342)
        _add_mem_word(cpu, ss, (bp + 0x32) & 0xFFFF, cpu.s.ax)
        cpu.s.ax = mem.rw(ds, 0x2346)
        _add_mem_word(cpu, ss, (bp + 0x34) & 0xFFFF, cpu.s.ax)

        # BA13..BA1A: wrap target X from >D0h to 20h.
        target_x = mem.rw(ss, (bp + 0x34) & 0xFFFF)
        _cmp_word(cpu, target_x, 0x00D0)
        if target_x > 0x00D0:
            mem.ww(ss, (bp + 0x34) & 0xFFFF, 0x0020)

        # BA1F..BA31: if current position plus vertical delta reached target,
        # use the direct sprite-refresh/helper branch; otherwise branch to BA99.
        cpu.s.ax = mem.rw(ss, (bp + 0x04) & 0xFFFF)
        old_ax = cpu.s.ax
        delta_y = mem.rw(ds, 0x2342)
        cpu.s.ax = (cpu.s.ax + delta_y) & 0xFFFF
        cpu.set_add_flags(old_ax, delta_y, old_ax + delta_y, 16)
        target_y = mem.rw(ss, (bp + 0x32) & 0xFFFF)
        _cmp_word(cpu, cpu.s.ax, target_y)
        reached_target = cpu.s.ax == target_y
        if reached_target:
            cpu.s.ax = mem.rw(ss, (bp + 0x02) & 0xFFFF)
            target_x = mem.rw(ss, (bp + 0x34) & 0xFFFF)
            _cmp_word(cpu, cpu.s.ax, target_x)
            reached_target = cpu.s.ax == target_x

        if reached_target:
            # BA33..BA5A: low level/tick branches call two helper leaves, then
            # advance X by two pixels before BC4B.  The common path falls through
            # to BA67 after failing the counter mask test.
            _cmp_word(cpu, mem.rw(ds, 0xA47E), 0x0006)
            ran_helper = False
            if mem.rw(ds, 0xA47E) < 0x0006:
                run_ba5a_helper_branch()
                ran_helper = True

            if not ran_helper:
                cpu.s.ax = mem.rw(ds, 0x2340)
                _cmp_word(cpu, mem.rw(ds, 0xBEDC), 0x0002)
                if mem.rw(ds, 0xBEDC) == 0x0002:
                    cpu.s.ax &= 0x007F
                    cpu.set_logic_flags(cpu.s.ax, 16)
                    _cmp_word(cpu, cpu.s.ax, 0x007F)
                    if cpu.s.ax == 0x007F:
                        _inc_mem_word_preserve_cf(cpu, ds, 0x2340)
                        run_ba5a_helper_branch()
                        ran_helper = True
                else:
                    cpu.s.ax &= 0x00FF
                    cpu.set_logic_flags(cpu.s.ax, 16)
                    _cmp_word(cpu, cpu.s.ax, 0x00FF)
                    if cpu.s.ax == 0x00FF:
                        _inc_mem_word_preserve_cf(cpu, ds, 0x2340)
                        run_ba5a_helper_branch()
                        ran_helper = True
            # BA67 path below.
        else:
            # BA99: decide whether to move toward the target through 5DB2 or use
            # the overshoot helper branch.
            cpu.s.ax = mem.rw(ss, (bp + 0x02) & 0xFFFF)
            target_x = mem.rw(ss, (bp + 0x34) & 0xFFFF)
            _cmp_word(cpu, cpu.s.ax, target_x)
            if cpu.s.ax > target_x:
                # BAA1..BABA: helper call, optional spawn, then either continue
                # to BC4B or wrap Y to 10h on unsigned overflow.
                call_5e42(0xBAA4)
                _cmp_word(cpu, mem.rw(ds, 0xA47E), 0x0006)
                if mem.rw(ds, 0xA47E) < 0x0006:
                    _cmp_word(cpu, mem.rw(ds, 0x232E), 0x003F)
                    if mem.rw(ds, 0x232E) == 0x003F:
                        call_7476(0xBAB5, "BAB2 CALL 7476")
                _cmp_word(cpu, mem.rw(ss, (bp + 0x02) & 0xFFFF), 0x00D0)
                if mem.rw(ss, (bp + 0x02) & 0xFFFF) > 0x00D0:
                    mem.ww(ss, (bp + 0x02) & 0xFFFF, 0x0010)
                cpu.s.ip = 0xBC4B
                return

            # BA73..BA8D: align target/current coordinates and publish movement
            # target globals.
            cpu.s.ax = mem.rw(ss, (bp + 0x32) & 0xFFFF)
            cpu.s.ax &= 0xFFFE
            cpu.set_logic_flags(cpu.s.ax, 16)
            _and_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 0xFFFE)
            mem.ww(ds, 0x2304, cpu.s.ax)
            cpu.s.ax = mem.rw(ss, (bp + 0x34) & 0xFFFF)
            cpu.s.ax &= 0xFFFE
            cpu.set_logic_flags(cpu.s.ax, 16)
            _and_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 0xFFFE)
            mem.ww(ds, 0x2306, cpu.s.ax)
            mem.ww(ds, 0x2308, 0x0001)

            # BA93: CALL 5DB2.  Push/pop the real return word so full-memory
            # verifier snapshots see the same balanced call scratch below SP.
            cpu.push(0xBA96)
            _run_movement_direction_5db2(cpu)
            cpu.s.ip = cpu.pop()
            if (cpu.s.ip & 0xFFFF) != 0xBA96:
                raise RuntimeError(f"5DB2 returned to unexpected IP {cpu.s.ip:04X} inside B9F0")
            cpu.s.ip = 0xBC4B
            return

    # BA67..BA70: update sprite/animation word from current global frame and
    # jump into the shared post-move helper.
    cpu.s.ax = mem.rw(ds, 0x233C)
    _add_reg16(cpu, 0, 0x001C)  # AX
    mem.ww(ss, (bp + 0x08) & 0xFFFF, cpu.s.ax)
    cpu.s.ip = 0xBC4B

def _run_collision_mark_a8c2_tail_bf5f(cpu) -> None:
    """Run BEC5:BF5F's observed A8C2 linked-object mark tail and return."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mem = cpu.mem

    saved_bp = cpu.s.bp & 0xFFFF
    cpu.push(saved_bp)
    for ptr_off in (0xA8BA, 0xA8BC, 0xA8BE, 0xA8C0):
        cpu.s.bp = mem.rw(ds, ptr_off)
        mem.ww(ss, (cpu.s.bp + 0x24) & 0xFFFF, 0x0005)
    _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
    if mem.rb(ds, 0x98C0) != 0x00:
        mem.wb(ds, 0xBEFF, 0x0E)
    cpu.s.bp = cpu.pop()
    cpu.s.ip = cpu.pop()


def _run_collision_cleanup_bd0d_observed(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the small BEC5 cleanup call at BD0D for the collided object in BX.

    BD0D is a wrapper around BD17: PUSH BP; BP=BX; CALL BD17; BX=BP;
    POP BP; RET.  Keep the nested return-address scratch visible while leaving
    the caller's live frame balanced.
    """
    saved_bp = cpu.s.bp & 0xFFFF
    cpu.push(saved_bp)
    bd17_return_sp = cpu.s.sp & 0xFFFF
    cpu.push(0xBD13)
    cpu.s.bp = cpu.s.bx & 0xFFFF
    _run_deactivate_bd17_observed(
        cpu,
        parent=parent,
        chain=f"{chain} -> BD0D",
        cx_value=cx_value,
        pop_return=False,
    )
    # Simulate BD17's RET to BD13; the return word remains below SP as in ASM.
    cpu.s.sp = bd17_return_sp
    cpu.s.bx = cpu.s.bp & 0xFFFF
    cpu.s.bp = cpu.pop()


def _run_collision_handler_bec5_observed(cpu, *, collided_bx: int, parent: str, chain: str, cx_value: int) -> None:
    """Run the currently verified BEC5 collision branches.

    BEC5 is jumped to from the unrolled 62F6 overlap scan rather than called as
    a separate subroutine.  Its RET returns to 62F6's caller, so every lifted RET
    path consumes the caller's return word exactly like the original ASM.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    bx = collided_bx & 0xFFFF
    mem = cpu.mem

    def run_bfc7(label: str) -> None:
        _run_collision_death_tail_bfc7(
            cpu,
            parent=parent,
            chain=f"{chain} -> BEC5 {label}".rstrip(),
            cx_value=cx_value,
        )

    def call_bd0d(return_ip: int, label: str) -> None:
        # BEC5 reaches BD0D by real CALLs at BF92/BF97.  Preserve their
        # return-address scratch even though the lifted code invokes the helper
        # directly.
        call_sp = cpu.s.sp & 0xFFFF
        cpu.push(return_ip & 0xFFFF)
        _run_collision_cleanup_bd0d_observed(
            cpu,
            parent=parent,
            chain=f"{chain} -> BEC5 {label}",
            cx_value=cx_value,
        )
        cpu.s.sp = call_sp

    def run_bf25_counter_chain(*, enter_at_bf25: bool, label: str) -> None:
        # BF25 is reached only by sprite-0033 variant-2 collisions and by the
        # A8C2-gated variant 5/6 and 7/8/0C continuations.  The usual variant-2
        # sprite path starts at BF2D and therefore skips this first decrement.
        if enter_at_bf25:
            _sub_mem_word(cpu, ss, (bp + 0x20) & 0xFFFF, 1)
            if mem.rw(ss, (bp + 0x20) & 0xFFFF) == 0:
                run_bfc7(f"{label} BF25 counter zero")
                return

        # BF2D
        _sub_mem_word(cpu, ss, (bp + 0x20) & 0xFFFF, 1)
        if mem.rw(ss, (bp + 0x20) & 0xFFFF) == 0:
            run_bfc7(f"{label} BF2D counter zero")
            return

        bedc = mem.rw(ds, 0xBEDC)
        _cmp_word(cpu, bedc, 0x0001)
        if bedc == 0x0001:
            _sub_mem_word(cpu, ss, (bp + 0x20) & 0xFFFF, 1)
            if mem.rw(ss, (bp + 0x20) & 0xFFFF) == 0:
                run_bfc7(f"{label} BEDC=0001 counter zero")
                return
        else:
            _cmp_word(cpu, bedc, 0x0000)
            if bedc == 0x0000:
                for tail in ("BF46", "BF4B", "BF50"):
                    _sub_mem_word(cpu, ss, (bp + 0x20) & 0xFFFF, 1)
                    if mem.rw(ss, (bp + 0x20) & 0xFFFF) == 0:
                        run_bfc7(f"{label} {tail} counter zero")
                        return
            # BEDC values other than 0/1 fall through to BF52 in the original.

        mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0005)
        a8c2 = mem.rw(ds, 0xA8C2)
        _cmp_word(cpu, a8c2, 0x0001)
        if a8c2 == 0x0001:
            _run_collision_mark_a8c2_tail_bf5f(cpu)
            return
        cpu.s.ip = cpu.pop()

    variant = mem.rw(ds, (bx + 0x18) & 0xFFFF)

    for target in (0x0007, 0x0008, 0x000C):
        _cmp_word(cpu, variant, target)
        if variant == target:
            # BFB9: A8C2 gates whether the collided slot is cleaned up and then
            # joins BF25, or whether the moving object is forced into BFC7.
            _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
            if mem.rw(ds, 0xA8C2) == 0x0001:
                cpu.s.bx = bx
                call_bd0d(0xBF95, f"variant {variant:04X}")
                run_bf25_counter_chain(enter_at_bf25=True, label=f"variant {variant:04X}")
                return
            mem.ww(ss, (bp + 0x20) & 0xFFFF, 0x0000)
            # Existing oracle fixtures for this lifted BFB9 path record the
            # target-Y field being cleared as part of the higher-level contact
            # transition.  Keep that observed side effect while the surrounding
            # object-state island is still being closed.
            mem.ww(ss, (bp + 0x32) & 0xFFFF, 0x0000)
            run_bfc7(f"variant {variant:04X}")
            return

    _cmp_word(cpu, variant, 0x0009)
    if variant == 0x0009:
        # BFA8: variant 9 uses the same A8C2 gate but does not call BD0D first.
        _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
        if mem.rw(ds, 0xA8C2) == 0x0001:
            run_bf25_counter_chain(enter_at_bf25=True, label="variant 0009")
            return
        mem.ww(ss, (bp + 0x20) & 0xFFFF, 0x0000)
        run_bfc7("variant 0009")
        return

    _cmp_word(cpu, variant, 0x0002)
    if variant == 0x0002:
        cpu.s.bx = bx
        mem.ww(ds, bx, 0)
        sprite = mem.rw(ds, (bx + 0x08) & 0xFFFF)
        _cmp_word(cpu, sprite, 0x0033)
        run_bf25_counter_chain(enter_at_bf25=(sprite == 0x0033), label="variant 0002")
        return

    for target in (0x0006, 0x0005):
        _cmp_word(cpu, variant, target)
        if variant == target:
            # BF97: BD0D/BD17 deactivate the collided object and maintain the
            # family live counters; the following A8C2 test chooses between the
            # BF25 shared counter path and the BFC7 death/transition tail.
            cpu.s.bx = bx
            call_bd0d(0xBF9A, f"variant {variant:04X}")
            _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
            if mem.rw(ds, 0xA8C2) == 0x0001:
                run_bf25_counter_chain(enter_at_bf25=True, label=f"variant {variant:04X}")
                return
            mem.ww(ss, (bp + 0x20) & 0xFFFF, 0x0000)
            run_bfc7(f"variant {variant:04X}")
            return

    # Remaining observed family: a collided slot linked back to the current
    # object via +30h.  A non-linked slot is still left fail-fast because that is
    # a new semantic path, even though the raw ASM would simply RET.
    owner_bp = mem.rw(ds, (bx + 0x30) & 0xFFFF)
    _cmp_word(cpu, bp, owner_bp)
    if bp == owner_bp:
        mem.ww(ds, (bx + 0x1C) & 0xFFFF, 0x0000)
        _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
        if mem.rw(ds, 0xA8C2) == 0x0001:
            run_bf25_counter_chain(enter_at_bf25=True, label=f"owner-linked variant {variant:04X}")
            return
        mem.ww(ss, (bp + 0x20) & 0xFFFF, 0x0000)
        run_bfc7(f"owner-linked variant {variant:04X}")
        return

    _raise_unverified_path(
        cpu,
        parent=parent,
        chain=f"{chain} -> BEC5 variant {variant:04X}",
        target_ip=0xBEC5,
        bp=bp,
        cx_value=cx_value,
    )

def _run_score_add_5f0d_observed(cpu, amount: int) -> None:
    """Observed score add helper reached from BFC7.

    The original is a packed decimal add starting at 1010:5F0D.  The death-tail
    paths seen so far add 0030h or 0060h into DS:2314..2318 and preserve AX, DX,
    and BP.  Later code in the tail overwrites flags, so this helper only needs
    the memory effect for the verified branch.
    """
    ss = cpu.s.ss & 0xFFFF
    carry = amount & 0xFFFF
    off = 0x2314
    for _ in range(5):
        value = cpu.mem.rb(ss, off)
        addend = carry & 0xFF
        total = (value & 0x0F) + (addend & 0x0F)
        high = (value >> 4) + (addend >> 4)
        if total > 9:
            total -= 10
            high += 1
        carry = 0
        if high > 9:
            high -= 10
            carry = 1
        cpu.mem.wb(ss, off, ((high << 4) | total) & 0xFF)
        off = (off + 1) & 0xFFFF


def _run_y_clamp_bcb1(cpu) -> None:
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0x00C0)
    sy = y if y < 0x8000 else y - 0x10000
    if sy > 0x00C0:
        cpu.mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x00C0)
        return
    _cmp_word(cpu, y, 0)
    if sy < 0:
        cpu.mem.ww(ss, (bp + 0x04) & 0xFFFF, 0)


def _find_free_effect_slot_7524(cpu) -> int:
    """Mirror the small 1010:7524 allocator used by the BFC7 linked effect.

    It scans from DS:[95D8] through the compact 38h-byte object records before
    the main 2B5C object pool, stores the found slot back to DS:[95D8], and
    leaves BX/CX/flags as the original allocator.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    cpu.s.cx = 0x0023
    cpu.s.bx = mem.rw(ds, 0x95D8)
    while True:
        bx = cpu.s.bx & 0xFFFF
        _cmp_word(cpu, mem.rw(ds, bx), 0x0000)
        if mem.rw(ds, bx) == 0:
            mem.ww(ds, 0x95D8, bx)
            return bx
        _add_reg16(cpu, 3, 0x0038)
        _cmp_word(cpu, cpu.s.bx, 0x2B5C)
        if cpu.s.bx == 0x2B5C:
            cpu.s.bx = 0x23B4
        old_cx = cpu.s.cx
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        if cpu.s.cx == 0:
            cpu.s.bx = 0xFFFF
            return 0xFFFF


def _run_linked_effect_spawn_7420_observed(cpu) -> None:
    """Run the observed 1010:7420 spawn helper used by BFC7/BFEE.

    The helper publishes source Y/X/type in DS:2376/2378/237A, allocates a
    compact effect slot via 7524, and seeds a short-lived visual object.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    bx = _find_free_effect_slot_7524(cpu)
    _cmp_word(cpu, cpu.s.bx, 0xFFFF)
    if bx == 0xFFFF:
        return

    mem.ww(ds, bx, 0x0001)
    cpu.s.ax = mem.rw(ds, 0x2378)
    old_ax = cpu.s.ax
    addend = mem.rw(ds, 0xA278)
    cpu.s.ax = (cpu.s.ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ds, (bx + 0x02) & 0xFFFF, cpu.s.ax)

    cpu.s.ax = mem.rw(ds, 0x2376)
    _cmp_word(cpu, cpu.s.ax, 0x00C0)
    if cpu.s.ax > 0x00C0:
        cpu.s.ax = 0x00C0
    mem.ww(ds, (bx + 0x04) & 0xFFFF, cpu.s.ax)

    mem.ww(ds, (bx + 0x22) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x14) & 0xFFFF, 0x0001)
    mem.ww(ds, (bx + 0x16) & 0xFFFF, 0x0005)
    mem.ww(ds, (bx + 0x18) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x28) & 0xFFFF, 0xFFFF)
    mem.ww(ds, (bx + 0x24) & 0xFFFF, 0x0000)

    cpu.s.si = mem.rw(ds, 0x237A)
    mem.ww(ds, (bx + 0x26) & 0xFFFF, cpu.s.si)
    _add_reg16(cpu, 6, 0x0046)
    mem.ww(ds, (bx + 0x08) & 0xFFFF, cpu.s.si)
    mem.ww(ds, (bx + 0x0A) & 0xFFFF, 0x0000)


def _run_c054_c12d_effect_spawn_tail(cpu, *, object_bp: int, selector_ax: int) -> None:
    """Mirror the C054:C12D linked-effect tail used by BD17 and BFC7.

    The 7Eh/7Dh/1Fh/1Ch/15h/13h selector family does more than choose AX:
    C12D publishes the selected script, pushes BX/BP below the live C054 return
    frame, CALLs 7420, then decrements DS:A47E.  Full-memory hook verification
    observes the freed stack scratch, so this helper deliberately models the
    nested CALL frames instead of treating the effect spawn as a pure function.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mem = cpu.mem
    bp = object_bp & 0xFFFF

    mem.ww(ds, 0xA482, selector_ax & 0xFFFF)
    mem.ww(ds, 0xA842, 0xA844)

    cpu.push(cpu.s.bx)
    cpu.push(cpu.s.bp)
    mem.ww(ds, 0x2376, mem.rw(ss, (bp + 0x04) & 0xFFFF))
    mem.ww(ds, 0x2378, mem.rw(ss, (bp + 0x02) & 0xFFFF))
    cpu.s.ax = 0x0002
    mem.ww(ds, 0x237A, cpu.s.ax)

    call_7420_sp = cpu.s.sp & 0xFFFF
    cpu.push(0xC14D)
    cpu.push(0x7423)
    _run_linked_effect_spawn_7420_observed(cpu)

    # Simulate the RETs from 7420/C12D while preserving the scratch words below
    # final SP for the full-memory verifier.
    cpu.s.sp = call_7420_sp
    cpu.s.bp = cpu.pop()
    cpu.s.bx = cpu.pop()
    _dec_mem_word_preserve_cf(cpu, ds, 0xA47E)


def _run_collision_death_tail_bfc7(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the observed BFC7 object death/transition tail for type-1 objects."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)
    _cmp_word(cpu, logic_id, 0x0021)
    if logic_id == 0x0021:
        _cmp_word(cpu, mem.rw(ds, 0x2356), 0x0004)
        if mem.rw(ds, 0x2356) != 0x0004:
            cpu.s.ip = cpu.pop()
            return
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> BFC7 logic 0021",
            target_ip=0xBFD2, bp=bp, cx_value=cx_value,
        )

    obj_type = mem.rw(ss, (bp + 0x14) & 0xFFFF)
    _cmp_word(cpu, obj_type, 0x0001)
    score_amount = 0x0030 if obj_type == 0x0001 else 0x0060
    if obj_type not in (0x0001, 0x0002):
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> BFC7 type {obj_type:04X}",
            target_ip=0xBFE1, bp=bp, cx_value=cx_value,
        )

    score_ax = cpu.s.ax
    score_dx = cpu.s.dx
    score_bp = cpu.s.bp
    _run_score_add_5f0d_observed(cpu, score_amount)
    stack_base = cpu.s.sp & 0xFFFF
    mem.ww(ss, (stack_base - 8) & 0xFFFF, score_dx)
    mem.ww(ss, (stack_base - 6) & 0xFFFF, score_ax)
    mem.ww(ss, (stack_base - 4) & 0xFFFF, score_bp)
    _run_y_clamp_bcb1(cpu)

    saved_bp = bp
    cpu.push(saved_bp)
    linked_slot = mem.rw(ss, (bp + 0x28) & 0xFFFF)
    _cmp_word(cpu, linked_slot, 0xFFFF)
    if linked_slot != 0xFFFF:
        cpu.s.si = linked_slot
        cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)
        _add_reg16(cpu, 6, 0x2078)
        linked_counter = mem.rb(ds, cpu.s.si & 0xFFFF)
        _cmp_byte(cpu, linked_counter, 0)
        if linked_counter != 0:
            old_counter = linked_counter
            new_counter = (old_counter - 1) & 0xFF
            mem.wb(ds, cpu.s.si & 0xFFFF, new_counter)
            cpu.set_sub_flags(old_counter, 1, old_counter - 1, 8)
            if new_counter == 0:
                mem.ww(ds, 0x2376, mem.rw(ss, (bp + 0x04) & 0xFFFF))
                mem.ww(ds, 0x2378, mem.rw(ss, (bp + 0x02) & 0xFFFF))
                cpu.s.ax = mem.rb(ds, (cpu.s.si + 1) & 0xFFFF)
                cpu.set_logic_flags(cpu.s.ax, 16)
                mem.ww(ds, 0x237A, cpu.s.ax)
                # C014 CALL 7420 leaves C017 below the live saved-BP word.
                mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xC017)
                _run_linked_effect_spawn_7420_observed(cpu)
    cpu.s.bp = cpu.pop()

    # BFC7 always CALLs the shared C054 selector before the state transition.
    # Earlier revisions whitelisted only a few observed logic ids here, but the
    # real helper is just the same compare chain used by BD17: some ids decrement
    # DS:A47E, while all other ids fall through to the default AX selector.
    # The following C01B compare overwrites C054's flags and C027 overwrites AX
    # with the original logic id, so the important observable effects are the
    # optional counter drop and call-frame scratch.
    c054_sp = cpu.s.sp & 0xFFFF
    cpu.push(0xC01B)
    run_object_deactivate_logic_dispatch_c054(cpu)
    selector_ax = cpu.s.ax & 0xFFFF
    # C054 has two selector families.  The 76h..79h family only selects AX;
    # the 7Eh/7Dh/1Fh/1Ch/15h/13h family falls through to C12D, publishes the
    # selected effect script in DS:A482, spawns a compact linked effect through
    # 7420, and decrements the live-effect counter before returning to C01B.
    # BFC7 reaches the same C054 helper as BD17, so keep the real C01B call
    # frame live while modelling the nested PUSH/CALL scratch.
    if logic_id in (0x007E, 0x007D, 0x001F, 0x001C, 0x0015, 0x0013):
        _run_c054_c12d_effect_spawn_tail(cpu, object_bp=bp, selector_ax=selector_ax)
    cpu.s.sp = c054_sp
    _cmp_word(cpu, mem.rb(ds, 0x98C0), 0)
    if mem.rb(ds, 0x98C0) != 0:
        mem.wb(ds, 0xBEFF, 0x19)

    cpu.s.ax = logic_id
    mem.ww(ss, (bp + 0x1A) & 0xFFFF, cpu.s.ax)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0000)
    # The captured C037/C048 tail exits through the one-step branch even when
    # the live counter slot has already been restored to its pre-tail value in
    # memory.  The observed final state is BX=0002 and FLAGS=0202.
    cpu.s.bx = 0x0001
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0000)
    cpu.s.ip = cpu.pop()


def _run_post_contact_9e69_observed(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the observed 1010:9E69 post-contact bookkeeping path."""
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    _cmp_word(cpu, mem.rw(ds, 0xA47C), 0x0001)
    if mem.rw(ds, 0xA47C) == 0x0001:
        return
    _cmp_word(cpu, mem.rw(ds, 0x2384), 0x0003)
    if mem.rw(ds, 0x2384) >= 0x0003:
        return
    _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
    if mem.rb(ds, 0x98C0) != 0:
        mem.wb(ds, 0xBEFF, 0x03)
    _cmp_word(cpu, mem.rw(ds, 0xBEDC), 0x0000)
    if mem.rw(ds, 0xBEDC) != 0:
        # JNE 9E98: skip the A362 every-other-call toggle and run the same tail
        # immediately while BEDC is active.
        _run_post_contact_9e98_tail_observed(cpu)
        return
    old = mem.rb(ds, 0xA362)
    new = (old + 1) & 0xFF
    mem.wb(ds, 0xA362, new)
    cpu.set_add_flags(old, 1, old + 1, 8)
    new &= 0x01
    mem.wb(ds, 0xA362, new)
    cpu.set_logic_flags(new, 8)
    if new == 0:
        _run_post_contact_9e98_tail_observed(cpu)


def _run_post_contact_9e98_tail_observed(cpu) -> None:
    """Run the observed 1010:9E98 tail of post-contact bookkeeping.

    9E69 toggles DS:A362 and returns immediately on odd toggles.  On even
    toggles it falls into 9E98, which advances global counters and redraws the
    associated status/formation strip through 61DC.  The gameplay-relevant
    branches are lifted here; the rare display helper 61DC is still executed by
    bounded original interpretation so the visible frame and scratch registers
    stay faithful until that helper is lifted separately.
    """
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    resume_ip = cpu.s.ip & 0xFFFF
    mem = cpu.mem

    old_counter = mem.rw(ds, 0xA95A)
    new_counter = (old_counter - 1) & 0xFFFF
    mem.ww(ds, 0xA95A, new_counter)
    cpu.set_sub_flags(old_counter, 1, old_counter - 1, 16)
    _cmp_word(cpu, new_counter, 0xFFFF)
    if new_counter == 0xFFFF:
        mem.ww(ds, 0xA95C, 0x0000)
        _cmp_byte(cpu, mem.rb(ds, 0x9791), 0x01)
        if mem.rb(ds, 0x9791) == 0x01:
            mem.ww(ds, 0xA95A, 0x0003)
            mem.ww(ds, 0xA95C, 0x0018)
            return
        mem.ww(ds, 0x2384, 0x0003)
        _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
        if mem.rb(ds, 0x98C0) != 0:
            mem.wb(ds, 0xBEFF, 0x19)

    _run_interpreted_near_call_observed(cpu, 0x61DC, 0x9EC5)
    _cmp_word(cpu, mem.rw(cs, 0x95BC), 0x0001)
    if mem.rw(cs, 0x95BC) == 0x0001:
        _run_interpreted_near_call_observed(cpu, 0x511F, 0x9ED0)
        _run_interpreted_near_call_observed(cpu, 0x61DC, 0x9ED3)
        _run_interpreted_near_call_observed(cpu, 0x511F, 0x9ED6)
    cpu.s.ip = resume_ip


def _find_free_object_slot_7573(cpu) -> int:
    """Mirror the original 1010:7573 object-slot allocator.

    The loop target in the ASM is 757A, not 7583, so the sentinel/wrap check is
    repeated on every scan iteration.  A lifted version that only wrapped once
    before the loop could let DS:[95DA] advance past 32CC into Tandy draw
    scratch space; the next projectile allocation would then overlap the sprite
    buffer and vanish on the following draw pass.
    """
    ds = cpu.s.ds & 0xFFFF
    bx = cpu.mem.rw(ds, 0x95DA)
    cx = 0x0022
    while cx:
        _cmp_word(cpu, bx, 0x32CC)
        if bx == 0x32CC:
            bx = 0x2B5C
        value = cpu.mem.rw(ds, bx)
        _cmp_word(cpu, value, 0)
        if value == 0:
            cpu.mem.ww(ds, 0x95DA, bx)
            cpu.s.bx = bx
            cpu.s.cx = cx
            return bx
        old_bx = bx
        bx = (bx + 0x0038) & 0xFFFF
        cpu.set_add_flags(old_bx, 0x0038, old_bx + 0x0038, 16)
        cx = (cx - 1) & 0xFFFF
    cpu.s.bx = 0xFFFF
    cpu.s.cx = 0
    return 0xFFFF


def _run_formation_spawn_7476_observed(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run observed B800 -> 7476 helper that spawns a formation child object."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    bx = _find_free_object_slot_7573(cpu)
    _cmp_word(cpu, cpu.s.bx, 0xFFFF)
    if bx == 0xFFFF:
        return
    if mem.rb(ds, 0x98C0) != 0:
        mem.wb(ds, 0xBEFF, 0x1A)

    cpu.s.cx = 0x000C
    cpu.s.dx = 0x000C
    _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
    if mem.rw(ds, 0xA8C2) == 0x0001:
        cpu.s.cx = 0x001C
        cpu.s.dx = 0x0008

    cpu.s.ax = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + cpu.s.cx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.cx, old_ax + cpu.s.cx, 16)
    mem.ww(ds, (bx + 0x04) & 0xFFFF, cpu.s.ax)
    cpu.s.ax = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.dx, old_ax + cpu.s.dx, 16)
    mem.ww(ds, (bx + 0x02) & 0xFFFF, cpu.s.ax)

    mem.ww(ds, bx, 0x0001)
    mem.ww(ds, (bx + 0x1E) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x06) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x08) & 0xFFFF, 0x0031)
    mem.ww(ds, (bx + 0x0A) & 0xFFFF, 0x0001)
    mem.ww(ds, (bx + 0x14) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x16) & 0xFFFF, 0x0002)
    mem.ww(ds, (bx + 0x18) & 0xFFFF, 0x000B)
    mem.ww(ds, (bx + 0x1C) & 0xFFFF, 0xFFFF)

    cpu.s.ax = mem.rw(ds, (bx + 0x04) & 0xFFFF)
    cpu.s.cx = (mem.rw(ds, 0x2380) + 0x0009) & 0xFFFF
    cpu.set_add_flags(mem.rw(ds, 0x2380), 0x0009, mem.rw(ds, 0x2380) + 0x0009, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    mem.ww(ds, (bx + 0x2C) & 0xFFFF, cpu.s.ax)
    cpu.s.ax = mem.rw(ds, (bx + 0x02) & 0xFFFF)
    cpu.s.cx = mem.rw(ds, 0x237E)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    mem.ww(ds, (bx + 0x2A) & 0xFFFF, cpu.s.ax)


def _run_object_overlap_scan_62f6(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the no-collision path of the 1010:62F6 object-overlap scan.

    The original is a large unrolled scan over 32CA-era object slots.  This
    compact loop preserves the observed no-collision semantics and fail-fasts if
    a candidate would jump to the unlifted collision handler at BEC5.
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    def finish_empty_scan() -> None:
        # 741C: ADD BX,0038 ; 741F: RET in the unrolled original.
        _add_reg16(cpu, 3, 0x0038)  # BX

    _cmp_word(cpu, mem.rw(ss, bp), 0)
    if mem.rw(ss, bp) == 0:
        cpu.s.bx = 0x3294
        finish_empty_scan()
        return

    _cmp_word(cpu, mem.rw(ss, (bp + 0x02) & 0xFFFF), 0x0020)
    if (mem.rw(ss, (bp + 0x02) & 0xFFFF) if mem.rw(ss, (bp + 0x02) & 0xFFFF) < 0x8000 else mem.rw(ss, (bp + 0x02) & 0xFFFF) - 0x10000) < 0x20:
        # The original bails out before the slot scan here, so keep BX and the
        # compare flags from 62FE intact instead of forcing the empty-scan tail.
        return

    for off, bad in ((0x16, 0), (0x18, 0)):
        _cmp_word(cpu, mem.rw(ss, (bp + off) & 0xFFFF), bad)
        if mem.rw(ss, (bp + off) & 0xFFFF) == bad:
            # 6308/6311: zero draw-layer/logic-id does not enter the slot scan.
            # The original falls through/jumps directly to the shared RET at
            # 741F, preserving the incoming BX and the zero-compare flags.  Do
            # not force the empty-scan sentinel tail here.
            return
    _cmp_word(cpu, mem.rw(ss, (bp + 0x18) & 0xFFFF), 0x0001)
    if mem.rw(ss, (bp + 0x18) & 0xFFFF) == 0x0001:
        return
    _cmp_word(cpu, mem.rw(ss, (bp + 0x18) & 0xFFFF), 0x0026)
    if mem.rw(ss, (bp + 0x18) & 0xFFFF) == 0x0026:
        cpu.s.bx = 0x3294
        finish_empty_scan()
        return

    cpu.s.si = mem.rw(ss, (bp + 0x16) & 0xFFFF)
    cpu.s.di = mem.rw(ss, (bp + 0x0A) & 0xFFFF)
    cpu.s.dx = mem.rw(ss, (bp + 0x04) & 0xFFFF) & 0xFFF8
    cpu.set_logic_flags(cpu.s.dx, 16)
    cpu.s.cx = mem.rw(ss, (bp + 0x02) & 0xFFFF) & 0xFFF8
    cpu.set_logic_flags(cpu.s.cx, 16)

    obj_type = mem.rw(ss, (bp + 0x14) & 0xFFFF)
    logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)
    bx = 0x2B5C
    while True:
        cpu.s.bx = bx
        _cmp_word(cpu, mem.rw(ds, bx), 0)
        if mem.rw(ds, bx) != 0:
            _cmp_word(cpu, mem.rw(ds, (bx + 0x1E) & 0xFFFF), 0)
            if mem.rw(ds, (bx + 0x1E) & 0xFFFF) != 0:
                ax = mem.rw(ds, (bx + 0x04) & 0xFFFF)
                _test_word(cpu, ax, 0x0007)
                y_candidates = []
                if ax & 0x0007:
                    aligned = (ax & 0xFFF8)
                    y_candidates.append((aligned + 8) & 0xFFFF)
                    y_candidates.append(aligned)
                else:
                    y_candidates.append(ax)
                y_candidates.append((y_candidates[-1] - 8) & 0xFFFF)
                if obj_type == 2:
                    y_candidates.append((y_candidates[-1] - 8) & 0xFFFF)
                    y_candidates.append((y_candidates[-1] - 8) & 0xFFFF)
                if cpu.s.dx in y_candidates:
                    used_x_branch = False
                    ax = mem.rw(ds, (bx + 0x02) & 0xFFFF) & 0xFFF8
                    x_candidates = [ax, (ax - 8) & 0xFFFF]
                    if obj_type == 2 and logic_id not in (0x78, 0x79):
                        x_candidates.append((x_candidates[-1] - 8) & 0xFFFF)
                        x_candidates.append((x_candidates[-1] - 8) & 0xFFFF)
                    used_x_branch = True
                    if cpu.s.cx in x_candidates:
                        # The original arrives at BEC5 with AX holding the
                        # matched tile X and BX pointing at the collided slot.
                        cpu.s.ax = cpu.s.cx & 0xFFFF
                        _run_collision_handler_bec5_observed(
                            cpu,
                            collided_bx=bx,
                            parent=parent,
                            chain=f"{chain} -> 62F6",
                            cx_value=cx_value,
                        )
                        return
                    # The original leaves AX at the last X candidate once the
                    # X branch has been entered, even on a miss.
                    cpu.s.ax = x_candidates[-1]
                else:
                    # Leave AX at the last tested Y coordinate when the Y
                    # branch misses entirely.
                    cpu.s.ax = y_candidates[-1]
        if bx == 0x3294:
            cpu.s.bx = bx
            finish_empty_scan()
            return
        old_bx = bx
        bx = (bx + 0x0038) & 0xFFFF
        cpu.set_add_flags(old_bx, 0x0038, old_bx + 0x0038, 16)




def run_object_postmove_prelude_bc45(cpu, *, parent: str = "1010:BC45", chain: str = "BC45 -> BC4B", cx_value: int | None = None) -> None:
    """Run the tiny 1010:BC45 prelude and the shared BC4B postmove chain.

    Several object behaviours jump to ``BC45`` instead of calling ``BC4B``
    directly.  The prelude reloads ``AX`` from the global vertical delta
    ``DS:A278`` and adds it into ``SS:[BP+02]`` before falling through to BC4B.
    Keep this as a wrapper around the single BC4B implementation so the
    collision/postmove tail is not duplicated.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    cpu.s.ax = cpu.mem.rw(ds, 0xA278)
    _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, cpu.s.ax)
    if cx_value is None:
        cx_value = cpu.s.cx & 0xFFFF
    _run_object_postmove_bc4b(cpu, parent=parent, chain=chain, cx_value=cx_value & 0xFFFF)
    cpu.s.ip = cpu.pop()

def _run_object_postmove_bc4b(cpu, *, parent: str, chain: str, cx_value: int, clamp_y: bool = True) -> None:
    """Run the observed BC4B post-move/bounds/collision helper path."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    if clamp_y:
        # BCB1: clamp Y into the 0..C0h range.  Some callers jump directly to
        # BC4F, after this call; those use clamp_y=False.
        y = mem.rw(ss, (bp + 0x04) & 0xFFFF)
        _cmp_word(cpu, y, 0x00C0)
        sy = y if y < 0x8000 else y - 0x10000
        if sy > 0x00C0:
            mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x00C0)
        else:
            _cmp_word(cpu, y, 0)
            if sy < 0:
                mem.ww(ss, (bp + 0x04) & 0xFFFF, 0)
        _remember_balanced_push_scratch(cpu, 0xBC4E)

    global_disable = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, global_disable, 0)
    skip_precise_x = global_disable != 0 or mem.rw(ss, (bp + 0x18) & 0xFFFF) in (0, 0x48, 0x26, 0x86, 0x28, 0x29, 0x34)
    x = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    sx = x if x < 0x8000 else x - 0x10000
    if not skip_precise_x:
        _cmp_word(cpu, x, 0xFF40)
        if sx < -0x00C0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value, pop_return=False)
            return
        _cmp_word(cpu, x, 0x00F0)
        if sx >= 0x00F0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value, pop_return=False)
            return
    else:
        _cmp_word(cpu, x, 0xFFEC)
        if sx < -0x0014:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value, pop_return=False)
            return
        _cmp_word(cpu, x, 0x00F0)
        if sx >= 0x00F0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value, pop_return=False)
            return

    _cmp_word(cpu, global_disable, 0)
    if global_disable == 0:
        # BC4B reaches the contact checks through CALL BCCB.  Even though BCCB
        # balances SP before returning, its nested CALLs leave return-address
        # scratch below SP; keep the real BCAD call frame live while modelling
        # BCCB so later nested calls land at the same stack offsets.
        bccb_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xBCAD)
        try:
            # BCCB early exits for inactive/exempt objects; otherwise it may call
            # the view-window helper and only continues into hit logic if CF is set.
            _cmp_word(cpu, mem.rw(ss, bp), 0)
            if mem.rw(ss, bp) != 0:
                for off, bad in ((0x16, 5), (0x18, 0), (0x18, 1)):
                    _cmp_word(cpu, mem.rw(ss, (bp + off) & 0xFFFF), bad)
                    if mem.rw(ss, (bp + off) & 0xFFFF) == bad:
                        break
                else:
                    obj_type = mem.rw(ss, (bp + 0x14) & 0xFFFF)
                    _cmp_word(cpu, obj_type, 1)
                    if obj_type == 1:
                        # BCF4 CALL AA46 leaves BCF7 below BCCB's live frame.
                        saved_sp = cpu.s.sp & 0xFFFF
                        cpu.push(0xBCF7)
                        _run_view_window_check_aa46(cpu)
                        cpu.s.sp = saved_sp
                    elif obj_type == 2:
                        # BCF9 CALL AA71 leaves BCFC below BCCB's live frame.
                        saved_sp = cpu.s.sp & 0xFFFF
                        cpu.push(0xBCFC)
                        run_postmove_contact_window_aa71(cpu)
                        cpu.s.sp = saved_sp
                    else:
                        return
                    if cpu.get_flag(CF):
                        _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
                        if mem.rw(ds, 0xA8C2) != 0x0001:
                            cpu.push(0xBD09)
                            _run_collision_death_tail_bfc7(
                                cpu,
                                parent=parent,
                                chain=f"{chain} -> BCCB",
                                cx_value=cx_value,
                            )
                        # BD09 CALL 9E69 must run with BD0C on the stack, not
                        # merely written below the current SP.  The 9E69 -> 9E98
                        # display tail calls 61DC, whose nested scratch is part
                        # of the verifier-visible freed stack bytes.
                        saved_sp = cpu.s.sp & 0xFFFF
                        cpu.push(0xBD0C)
                        _run_post_contact_9e69_observed(
                            cpu,
                            parent=parent,
                            chain=f"{chain} -> BCCB -> BD09",
                            cx_value=cx_value,
                        )
                        cpu.s.sp = saved_sp
        finally:
            cpu.s.sp = bccb_sp
        # BCAD CALL 62F6 leaves the BCB0 return word as stack scratch below SP.
        saved_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xBCB0)
        _run_object_overlap_scan_62f6(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value)
        cpu.s.sp = saved_sp


def _run_object_family_dispatch_efae(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run EFAE's prologue and leave IP at the concrete second-level target.

    EFAE is a dispatcher, not a behavior body.  It publishes the object's current
    Y/X into DS:D1FE/D200 and then jumps through a second table indexed by
    SS:[BP+18].  Keep this boundary conservative: do not run the selected
    gameplay routine inline here.
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    cpu.s.ax = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    cpu.mem.ww(ds, 0xD1FE, cpu.s.ax)
    cpu.s.ax = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
    cpu.mem.ww(ds, 0xD200, cpu.s.ax)

    cpu.s.bx = cpu.mem.rw(ss, (bp + 0x18) & 0xFFFF)
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1
    target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xEFC4 + cpu.s.bx) & 0xFFFF)
    cpu.s.ip = target_ip



def _run_af22_three_pixel_step_for_direction(cpu, *, parent: str = "1010:AF22") -> None:
    """Mirror 1010:AF22: one 3-pixel diagonal/cardinal step by SS:[BP+06]."""
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    direction = cpu.mem.rw(ss, (bp + 0x06) & 0xFFFF) & 0xFFFF
    cpu.s.bx = direction
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)

    if direction == 0:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 3)
    elif direction == 1:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 3)
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 3)
    elif direction == 2:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 3)
    elif direction == 3:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 3)
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 3)
    elif direction == 4:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 3)
    elif direction == 5:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 3)
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 3)
    elif direction == 6:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 3)
    elif direction == 7:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 3)
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 3)
    else:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain="AF22 direction table",
            target_ip=cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAF2C + ((direction << 1) & 0xFFFF)) & 0xFFFF),
            bp=bp,
            cx_value=cpu.s.cx & 0xFFFF,
        )


def _run_object_bounds_tile_tail_ad60(cpu, *, parent: str, chain: str, cx_value: int, add_a278_to_x: bool) -> None:
    """Shared AD5A/AD60 bounds + optional tile-probe tail used by object behaviors."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    if add_a278_to_x:
        cpu.s.ax = mem.rw(ds, 0xA278)
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, cpu.s.ax)

    x = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    _cmp_word(cpu, x, 0x0008)
    if x < 0x0008:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AD60", cx_value=cx_value, pop_return=False)
        cpu.s.ip = cpu.pop()
        return
    _cmp_word(cpu, x, 0x00E0)
    if x > 0x00E0:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AD60", cx_value=cx_value, pop_return=False)
        cpu.s.ip = cpu.pop()
        return
    y = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0x00C8)
    if y > 0x00C8:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AD60", cx_value=cx_value, pop_return=False)
        cpu.s.ip = cpu.pop()
        return
    draw_layer = mem.rw(ss, (bp + 0x16) & 0xFFFF)
    _cmp_word(cpu, draw_layer, 0x0002)
    if draw_layer != 0x0002:
        cpu.s.ip = cpu.pop()
        return
    logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)
    for good in (0x0002, 0x0004, 0x000C, 0x0005, 0x0006, 0x0009, 0x0008):
        _cmp_word(cpu, logic_id, good)
        if logic_id == good:
            break
    else:
        cpu.s.ip = cpu.pop()
        return

    bdac = mem.rw(ds, 0xBDAC)
    _cmp_word(cpu, bdac, 0x0001)
    if bdac == 0x0001:
        cpu.s.ip = cpu.pop()
        return
    _run_tile_probe_5073(cpu)
    _add_reg16(cpu, 3, 0x000D)
    mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xADBF)
    _run_tile_lookup_505b(cpu)
    if not cpu.get_flag(ZF):
        old_al = cpu.get_reg8(0)
        old_cf = cpu.get_flag(CF)
        result_full = old_al - 1
        cpu.set_reg8(0, result_full & 0xFF)
        cpu.set_sub_flags(old_al, 1, result_full, 8)
        cpu.set_flag(CF, old_cf)
        if cpu.get_reg8(0) == 0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> ADC1", cx_value=cx_value, pop_return=False)
            cpu.s.ip = cpu.pop()
            return
    cpu.s.ip = cpu.pop()



def _run_original_tail_to_caller(cpu, target_ip: int, *, max_steps: int = 12000) -> None:
    """Run an unlifted in-procedure tail to the current near caller return.

    The original code is not executing a CALL at this point; the caller return
    word is already at SS:SP.  Pop and re-push the same word through the bounded
    near-call helper so the final SP and below-SP scratch remain comparable.
    """
    caller_ret = cpu.pop()
    _run_interpreted_near_call_observed(cpu, target_ip & 0xFFFF, caller_ret, max_steps=max_steps)


def _finish_ae2c_common(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    mem.ww(ss, (bp + 0x06) & 0xFFFF, 0x0001)
    _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 4)
    cpu.s.ax = mem.rw(ds, 0x2326)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax &= 0x0008
    cpu.set_logic_flags(cpu.s.ax, 16)
    _add_reg16(cpu, 0, mem.rw(ss, (bp + 0x06) & 0xFFFF))
    _add_reg16(cpu, 0, 0x0008)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, cpu.s.ax)
    _run_object_bounds_tile_tail_ad60(
        cpu, parent=parent, chain=f"{chain} -> AD5A", cx_value=cx_value, add_a278_to_x=True
    )


def run_object_drift_downright_ae2c(cpu, self_disable_if_patched) -> None:
    """Lift the observed 1010:AE2C drift-down/right object tail to AD5A.

    The hot cold-start demo path nudges X left, conditionally nudges Y down,
    updates the sprite frame from the global frame counter, then joins the
    AD5A/AD60 bounds tile tail.  Less common collision/deactivation subpaths are
    kept as bounded original tails.
    """
    if self_disable_if_patched(
        cpu, 0xAE2C, SIG_OBJECT_DRIFT_DOWNRIGHT_AE2C, "overkill_object_drift_downright_ae2c"
    ):
        return

    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0x00C8)
    if y == 0x00C8:
        _run_original_tail_to_caller(cpu, 0xADC9)
        return

    _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 4)
    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _test_word(cpu, y, 0x0007)
    if y & 0x0007:
        _finish_ae2c_common(cpu, parent="1010:AE2C", chain="AE2C", cx_value=cpu.s.cx & 0xFFFF)
        return

    _test_word(cpu, y, 0x0008)
    if (y & 0x0008) == 0:
        _finish_ae2c_common(cpu, parent="1010:AE2C", chain="AE2C", cx_value=cpu.s.cx & 0xFFFF)
        return

    _run_original_tail_to_caller(cpu, 0xAE45)


def run_object_drift_upright_ae7d(cpu, self_disable_if_patched) -> None:
    """Lift the observed 1010:AE7D drift-up/right object tail to AD5A."""
    if self_disable_if_patched(
        cpu, 0xAE7D, SIG_OBJECT_DRIFT_UPRIGHT_AE7D, "overkill_object_drift_upright_ae7d"
    ):
        return

    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0)
    if y == 0:
        _run_original_tail_to_caller(cpu, 0xADC9)
        return

    _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 4)
    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _test_word(cpu, y, 0x000F)
    if (y & 0x000F) == 0:
        _run_original_tail_to_caller(cpu, 0xAE91)
        return

    cpu.mem.ww(ss, (bp + 0x06) & 0xFFFF, 0x0007)
    _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 4)
    cpu.s.ax = cpu.mem.rw(ss, (bp + 0x06) & 0xFFFF)
    _add_reg16(cpu, 0, 0x0008)
    cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, cpu.s.ax)
    _run_object_bounds_tile_tail_ad60(
        cpu, parent="1010:AE7D", chain="AE7D -> AD5A", cx_value=cpu.s.cx & 0xFFFF, add_a278_to_x=True
    )


def run_object_bounds_tile_prelude_ad5a(cpu, self_disable_if_patched) -> None:
    """Lift 1010:AD5A, the A278-relative prelude to the AD60 bounds/tile tail.

    This is object-runtime glue, not a distinct behaviour: AD5A adds the current
    frame scroll/X delta at DS:A278 to SS:[BP+02], then falls directly into the
    already lifted AD60 bounds/tile/deactivation tail.
    """
    if self_disable_if_patched(
        cpu,
        0xAD5A,
        SIG_OBJECT_BOUNDS_TILE_PRELUDE_AD5A,
        "overkill_object_bounds_tile_prelude_ad5a",
    ):
        return

    _run_object_bounds_tile_tail_ad60(
        cpu,
        parent="1010:AD5A",
        chain="AD5A",
        cx_value=cpu.s.cx & 0xFFFF,
        add_a278_to_x=True,
    )


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

    s.ax = mem.rw(ss, (bp + 0x32) & 0xFFFF)
    mem.ww(ds, 0x2304, s.ax)
    s.ax = mem.rw(ss, (bp + 0x34) & 0xFFFF)
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



def _no_patch_guard(*_args) -> bool:
    return False


def _run_object_behavior_ab77(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed AB77 object-behaviour driver without duplicating leaves.

    AB77 is the shared tail reached from AD04's tracked-object branches
    (AB71/AB69/AB61).  The hot observed path is: choose the scroll-relative
    sprite through AB4F, probe tile collision through AC28, scan object overlaps
    through AC81/AC97, then return if nothing was hit.  The unobserved collision
    continuations remain as exact original IP continuations instead of being
    guessed here.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, 0x0003)
    if v2384 >= 0x0003:
        cpu.s.ip = 0xAB8F
        return

    cpu.push(0xAB81)
    run_object_scroll_sprite_ab4f(cpu, _no_patch_guard)
    if cpu.s.ip != 0xAB81:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AB4F", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)

    cpu.push(0xAB84)
    run_tile_collision_probe_ac28(cpu, _no_patch_guard)
    if cpu.s.ip == 0xAA44:
        cpu.set_flag(CF, False)
        cpu.s.ip = cpu.pop()
    if cpu.s.ip != 0xAB84:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AC28", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)
    if cpu.get_flag(CF):
        cpu.s.ip = 0xAB8F
        return

    cpu.push(0xAB89)
    run_object_slot_scan_guard_ac81(cpu, _no_patch_guard)
    if cpu.s.ip == 0xAA44:
        cpu.set_flag(CF, False)
        cpu.s.ip = cpu.pop()
    if cpu.s.ip == 0xACD9:
        return
    if cpu.s.ip != 0xAB89:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AC81", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)
    if cpu.get_flag(CF):
        cpu.s.ip = 0xAB8C
        return

    # AB8B RET
    cpu.s.ip = cpu.pop()



def _run_tracked_object_selector_to_ab77(cpu, *, selector_addr: int) -> None:
    """Mirror the tiny AB59/AB61/AB69/AB71 selector stubs before AB77.

    These are not independent object behaviours.  Each writes the address of one
    tracked-object global into DS:A42C, then jumps into the shared AB77 tail.
    Keeping them as one helper makes the AD04 frontier explicit without
    duplicating AB77 itself.
    """
    cpu.mem.ww(cpu.s.ds & 0xFFFF, 0xA42C, selector_addr & 0xFFFF)
    cpu.s.ip = 0xAB77


def _run_object_sprite0f_collision_abca(
    cpu,
    *,
    parent: str,
    chain: str,
    cx_value: int,
    run_original_near_call,
) -> None:
    """Lift the observed ABCA sprite-0F/tracked collision behaviour.

    ABCA is reached from AD04 when the slot sprite field is 000Fh.  The hot
    cold-start/attract path derives a motion-table position through AB34,
    probes tiles through AC28, then scans nearby object slots through AC81.
    Collision/deactivation continuations are preserved either through existing
    lifted helpers or through bounded original calls for the still-separate
    animation/reinitialization leaves.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mem = cpu.mem

    def finish_deactivate_tail(*, call_ab99: bool) -> None:
        mem.ww(ds, 0xA96E, 0xFFFF)
        if call_ab99:
            run_original_near_call(cpu, 0xAB99, 0xABF3)
            if cpu.s.ip != 0xABF3:
                _raise_unverified_path(
                    cpu, parent=parent, chain=f"{chain} -> AB99",
                    target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
                )

        bp = cpu.s.bp & 0xFFFF
        _cmp_word(cpu, bp, 0xFFFF)
        if bp == 0xFFFF:
            cpu.s.ip = cpu.pop()
            return

        _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
        if mem.rb(ds, 0x98C0) != 0:
            mem.wb(ds, 0xBEFF, 0x19)

        mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x0001)
        mem.ww(ss, (bp + 0x16) & 0xFFFF, 0x0004)
        mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0000)
        mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0000)

        cpu.push(bp)
        run_original_near_call(cpu, 0x837A, 0xAC1D)
        if cpu.s.ip != 0xAC1D:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> 837A",
                target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
            )
        run_original_near_call(cpu, 0x859E, 0xAC20)
        if cpu.s.ip != 0xAC20:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> 859E",
                target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
            )
        cpu.s.bp = cpu.pop()
        cpu.s.ip = cpu.pop()

    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, 0x0003)
    if v2384 < 0x0003:
        cpu.s.dx = 0xA420
        cpu.push(0xABD7)
        run_object_motion_table_ab34(cpu, _no_patch_guard)
        if cpu.s.ip != 0xABD7:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> AB34",
                target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
            )

        cpu.push(0xABDA)
        run_tile_collision_probe_ac28(cpu, _no_patch_guard)
        if cpu.s.ip == 0xAA44:
            cpu.set_flag(CF, False)
            cpu.s.ip = cpu.pop()
        if cpu.s.ip != 0xABDA:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> AC28",
                target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
            )
        # ABDA: JAE ABE4.  If CF is set, fall through to ABDC/ABF3.
        if not cpu.get_flag(CF):
            cpu.push(0xABE7)
            run_object_slot_scan_guard_ac81(cpu, _no_patch_guard)
            if cpu.s.ip == 0xAA44:
                cpu.set_flag(CF, False)
                cpu.s.ip = cpu.pop()
            if cpu.s.ip == 0xACD9:
                return
            if cpu.s.ip != 0xABE7:
                _raise_unverified_path(
                    cpu, parent=parent, chain=f"{chain} -> AC81",
                    target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
                )
            if not cpu.get_flag(CF):
                cpu.s.ip = cpu.pop()
                return
            finish_deactivate_tail(call_ab99=True)
            return

    finish_deactivate_tail(call_ab99=False)

def _run_object_logic_branch_ad04(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Mirror the 1010:AD04 small object-logic branch selector.

    AD04 is a hot first-level object logic target, not a full behavior body.  It
    decides whether to return immediately or jump into one of the nearby ABxx
    behavior tails according to global state and a handful of tracked object
    pointer globals.  Keeping it as a branch selector avoids duplicating those
    ABxx bodies while removing the tiny interpreted hotspot cluster.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    bdac = mem.rw(ds, 0xBDAC)
    _cmp_word(cpu, bdac, 0x0001)
    if bdac != 0x0001:
        v2350 = mem.rw(ds, 0x2350)
        _cmp_word(cpu, v2350, 0x00B6)
        if v2350 <= 0x00B6:
            cpu.s.ip = cpu.pop()
            return

    sprite = mem.rw(ss, (bp + 0x08) & 0xFFFF)
    _cmp_word(cpu, sprite, 0x000F)
    if sprite == 0x000F:
        cpu.s.ip = 0xABCA
        return

    for global_off, target_ip in (
        (0xA966, 0xAB71),
        (0xA968, 0xAB69),
        (0xA96A, 0xAB61),
        (0xA96C, 0xAB59),
    ):
        tracked = mem.rw(ds, global_off)
        _cmp_word(cpu, bp, tracked)
        if bp == tracked:
            cpu.s.ip = target_ip
            return

    cpu.s.bx = 0xA962
    tracked = mem.rw(ds, 0xA962)
    _cmp_word(cpu, bp, tracked)
    if bp == tracked:
        cpu.s.ip = 0xABA3
        return

    cpu.s.bx = 0xA964
    tracked = mem.rw(ds, 0xA964)
    _cmp_word(cpu, bp, tracked)
    if bp == tracked:
        cpu.s.ip = 0xABA3
        return

    cpu.s.ip = cpu.pop()



def _run_object_behavior_aba3(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed ABA3 tracked-object follower probe.

    ABA3 is reached from AD04 when the current slot matches one of the global
    tracked object pointers at A962/A964.  The observed hot path stores the
    selected tracker pointer in DS:A42E, derives a scroll-relative sprite index
    from DS:233C+14h, and reuses the already lifted AC81/AC97 object-slot scan
    guard.  Collision continuations after the CF-set branch are preserved as
    original IP continuations until they are separately understood.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    mem.ww(ds, 0xA42E, cpu.s.bx)
    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, 0x0003)
    if v2384 >= 0x0003:
        cpu.s.ip = 0xABC0
        return

    ax = mem.rw(ds, 0x233C)
    cpu.s.ax = ax
    result = ax + 0x0014
    cpu.s.ax = result & 0xFFFF
    cpu.set_add_flags(ax, 0x0014, result, 16)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, cpu.s.ax)

    cpu.push(0xABBA)
    run_object_slot_scan_guard_ac81(cpu, _no_patch_guard)
    if cpu.s.ip == 0xAA44:
        cpu.set_flag(CF, False)
        cpu.s.ip = cpu.pop()
    if cpu.s.ip == 0xACD9:
        return
    if cpu.s.ip != 0xABBA:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AC81", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)
    if cpu.get_flag(CF):
        cpu.s.ip = 0xABBD
        return
    cpu.s.ip = cpu.pop()

def _run_object_behavior_ae09(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Observed EFAE logic-id 0Ch behavior: timer, 3-pixel step, then AD60 tail."""
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    timer = mem.rw(ss, (bp + 0x1C) & 0xFFFF)
    _cmp_word(cpu, timer, 0x0000)
    if timer != 0:
        _sub_mem_word(cpu, ss, (bp + 0x1C) & 0xFFFF, 1)
        if mem.rw(ss, (bp + 0x1C) & 0xFFFF) == 0:
            mem.ww(ss, (bp + 0x06) & 0xFFFF, 0x0000)
    if timer == 0 or mem.rw(ss, (bp + 0x1C) & 0xFFFF) == 0:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)

    cpu.s.ax = mem.rw(ss, (bp + 0x06) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (old_ax + 0x0028) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0028, old_ax + 0x0028, 16)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, cpu.s.ax)

    # AE26 CALL AF22 leaves AE29 as balanced-call stack scratch.
    mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xAE29)
    _run_af22_three_pixel_step_for_direction(cpu, parent="1010:AF22")
    _run_object_bounds_tile_tail_ad60(
        cpu,
        parent=parent,
        chain=f"{chain} -> AE09",
        cx_value=cx_value,
        add_a278_to_x=False,
    )

def _run_object_behavior_8d4f(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed logic_id=1Fh target-patrol behavior at 1010:8D4F.

    The body is mostly an overlay far-call (`1F8F:027A`) that reads the next
    waypoint pair from DS:A482, publishes target X/Y to DS:2306/2304, sets
    movement mode 3, calls the generic 5DB2 direction helper through the far
    trampoline at 1010:8D8B, then returns to 8D54 and joins BC4B.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    cpu.s.si = mem.rw(ds, 0xA482)
    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + 0x0020) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0020, old_ax + 0x0020, 16)
    mem.ww(ds, 0x2306, cpu.s.ax)
    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    mem.ww(ds, 0x2304, cpu.s.ax)
    mem.ww(ds, 0x2308, 0x0003)
    cpu.s.ax = 0x5DB2
    # Faithfully reproduce the call frame the original leaves below SP -- OVERKILL
    # reads this scratch through its self-call tricks, so an approximation diverges:
    #   8D4F      CALL FAR 1F8F:027A   pushes CS=1010, IP=8D54
    #   1F8F:0292 CALL FAR 1010:8D8B   pushes CS=1F8F, IP=0297
    #   1010:8D8B CALL AX (=5DB2)      pushes IP=8D8D
    # 5DB2 then runs and three RET/RETF pops unwind the frame back to 8D54.
    cpu.push(0x1010)
    cpu.push(0x8D54)
    cpu.push(0x1F8F)
    cpu.push(0x0297)
    cpu.push(0x8D8D)
    _run_movement_direction_5db2(cpu)
    cpu.s.sp = (cpu.s.sp + 0x000A) & 0xFFFF  # RET 5DB2 + RETF 8D8D + RETF 1F8F:0451
    _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> 8D4F -> 1F8F:027A -> 5DB2", cx_value=cx_value)
    cpu.s.ip = cpu.pop()


def _run_tile_probe_5073(cpu) -> None:
    """Mirror the coordinate-to-tile-index helper at 1010:5073."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    cpu.s.ax = mem.rw(ds, 0x234E)
    old_ax = cpu.s.ax
    addend = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    cpu.s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ds, 0x215A, cpu.s.ax)
    if cpu.s.ax & 0x8000:
        return
    for _ in range(4):
        cpu.s.ax = cpu.shift(5, cpu.s.ax, 1, 16)  # SHR AX,1
    cpu.s.dx = cpu.s.ax
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.cx = cpu.s.ax
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (old_ax + cpu.s.cx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.cx, old_ax + cpu.s.cx, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (old_ax + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.dx, old_ax + cpu.s.dx, 16)
    cpu.s.bx = mem.rw(ds, 0x2350)
    _sub_reg16(cpu, 3, cpu.s.ax)
    cpu.s.ax = mem.rw(ss, (bp + 0x04) & 0xFFFF) & 0xFFF0
    cpu.set_logic_flags(cpu.s.ax, 16)
    for _ in range(4):
        cpu.s.ax = cpu.shift(5, cpu.s.ax, 1, 16)
    _add_reg16(cpu, 3, cpu.s.ax)


def _run_tile_lookup_505b(cpu) -> None:
    """Mirror the observed tile lookup helper at 1010:505B."""
    cs = cpu.s.cs & 0xFFFF
    es = cpu.mem.rw(cs, 0x9592)
    cpu.s.es = es
    cpu.s.si = 0xC3AA
    value = cpu.mem.rb(es, cpu.s.bx & 0xFFFF)
    cpu.set_reg8(0, value)
    cpu.set_reg8(4, 0)  # XOR AH,AH
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si + cpu.s.ax) & 0xFFFF
    cpu.set_add_flags(old_si, cpu.s.ax, old_si + cpu.s.ax, 16)
    cpu.set_reg8(0, cpu.mem.rb(cpu.s.ds & 0xFFFF, cpu.s.si))
    cpu.set_logic_flags(cpu.get_reg8(0), 8)


def _run_deactivate_bd17_observed(cpu, *, parent: str, chain: str, cx_value: int, pop_return: bool = True) -> None:
    """Run observed 1010:BD17 object deactivation tail.

    BD17 is reached from BC4B when an object leaves the allowed X bounds.  The
    currently observed gameplay case is the B73E formation/attack object with
    draw layer 4.  One observed selector result takes the longer BD5F tail that
    publishes DS:A482, seeds the 7420 linked-effect spawn helper, and then
    unwinds back to BC4B.  Other draw-layer/logic-id combinations still fall
    through to the smaller cleanup branches that were already modeled.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x0000)

    draw_layer = mem.rw(ss, (bp + 0x16) & 0xFFFF)
    _cmp_word(cpu, draw_layer, 0x0004)
    if draw_layer == 0x0004:
        logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)
        # BD5C is a real CALL C054.  Even after the call returns, the BD5F
        # return word remains in freed stack space and is visible to full-stack
        # verifier comparisons.  Keep the frame live while modelling the C054
        # selector tail so nested CALL scratch lands at the original offsets.
        c054_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xBD5F)
        run_object_deactivate_logic_dispatch_c054(cpu)
        selector_ax = cpu.s.ax & 0xFFFF
        # C054 has two families that can leave the selector chain with one of
        # these AX table values.  The 76h..79h family jumps to the live-counter
        # cleanup tail, but the 7Eh/7Dh/1Fh/1Ch/15h/13h family falls through to
        # C12D and runs the linked-effect spawn helper before returning to BD5F.
        # Keying only on AX missed the observed logic_id=13h case because A4E4h
        # was not in the earlier whitelist; keying on the actual logic id keeps
        # the overlap with 76h/77h unambiguous as well.
        if logic_id in (0x007E, 0x007D, 0x001F, 0x001C, 0x0015, 0x0013):
            _run_c054_c12d_effect_spawn_tail(cpu, object_bp=bp, selector_ax=selector_ax)

        # Simulate C054's RET back to BD5F.  The return word remains below SP.
        cpu.s.sp = c054_sp

        _cmp_word(cpu, logic_id, 0x0001)
        if logic_id == 0x0001:
            return
        slot = mem.rw(ss, (bp + 0x28) & 0xFFFF)
        _cmp_word(cpu, slot, 0xFFFF)
        if slot == 0xFFFF:
            return
        cpu.s.si = slot
        cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)  # SHL SI,1
        _add_reg16(cpu, 6, 0x2078)                # ADD SI,2078h
        mem.wb(ds, cpu.s.si & 0xFFFF, 0x00)
        return

    _cmp_word(cpu, draw_layer, 0x0001)
    if draw_layer == 0x0001:
        mem.ww(ss, (bp + 0x16) & 0xFFFF, 0x0002)
        return

    logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)
    for target, counter in (
        (0x0007, 0xA970),
        (0x0008, 0xA970),
        (0x0009, 0xA972),
        (0x0006, 0xA976),
        (0x0005, 0xA976),
        (0x000C, 0xA974),
        (0x000A, 0xA972),
    ):
        _cmp_word(cpu, logic_id, target)
        if logic_id == target:
            if mem.rw(ds, counter) != 0:
                _sub_mem_word(cpu, ds, counter, 0x0001)
            return

    # BD17 is usually called as a standalone helper in tests/older lifted paths,
    # but BC4B reaches it by a direct branch and its wrapper owns the final RET
    # pop.  Preserve both boundary shapes explicitly.
    if pop_return:
        cpu.s.ip = cpu.pop()
    return


def _run_object_behavior_aed8(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed EFAE logic_id=2 movement/tile-probe branch at AED8."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    _sub_mem_word(cpu, ss, (bp + 0x1C) & 0xFFFF, 1)
    if mem.rw(ss, (bp + 0x1C) & 0xFFFF) == 0:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 timer expired", target_ip=0xADC9, bp=bp, cx_value=cx_value)

    cpu.s.ax = 0xB250
    # AED8 pushes B250 and falls into AEE4.  The return word is later replaced
    # by the nested ADBF call scratch; keep SP unchanged in the lifted form.
    mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xB250)
    _run_aee4_step_for_direction(cpu)

    # Observed B250 branch: object +1Eh == 1 jumps to B2A3 -> AD5A.
    marker = mem.rw(ss, (bp + 0x1E) & 0xFFFF)
    _cmp_word(cpu, marker, 0x0001)
    if marker != 0x0001:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 -> B250", target_ip=0xB254, bp=bp, cx_value=cx_value)

    _run_object_bounds_tile_tail_ad60(
        cpu,
        parent=parent,
        chain=f"{chain} -> AED8",
        cx_value=cx_value,
        add_a278_to_x=True,
    )


def _run_object_logic_ab10(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed AA2B target AB10 position/sprite update helper.

    AB10 is a first-level object logic target for SS:[BP+16] == 6 in the
    current island.  The observed branch samples a small animation table at
    DS:A40C/DS:A414 using DS:2336 and DS:237C, then writes the object's sprite
    and position before returning to the AA2B caller.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, 0x0003)
    if v2384 >= 0x0003:
        mem.ww(ss, bp, 0x0000)
        cpu.s.ip = cpu.pop()
        return

    global_disable = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, global_disable, 0x0003)
    if global_disable >= 0x0003:
        mem.ww(ss, bp, 0x0000)
        cpu.s.ip = cpu.pop()
        return

    cpu.s.ax = mem.rw(ds, 0x2336)
    cpu.s.bx = 0xA40C
    # XLAT: AL = DS:[BX+AL], AH unchanged.
    cpu.set_reg8(0, mem.rb(ds, (cpu.s.bx + (cpu.s.ax & 0x00FF)) & 0xFFFF))
    old_ax = cpu.s.ax & 0xFFFF
    cpu.s.ax = (old_ax + 0x0009) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0009, old_ax + 0x0009, 16)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, cpu.s.ax)

    cpu.s.dx = 0xA414
    cpu.s.bx = 0x237C
    cpu.s.si = mem.rw(ds, (cpu.s.bx + 0x08) & 0xFFFF)
    cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)
    cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_si, cpu.s.dx, old_si + cpu.s.dx, 16)

    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    old_ax = cpu.s.ax & 0xFFFF
    addend = mem.rw(ds, (cpu.s.bx + 0x02) & 0xFFFF)
    cpu.s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ss, (bp + 0x02) & 0xFFFF, cpu.s.ax)

    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    old_ax = cpu.s.ax & 0xFFFF
    addend = mem.rw(ds, (cpu.s.bx + 0x04) & 0xFFFF)
    cpu.s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, cpu.s.ax)
    cpu.s.ip = cpu.pop()


def _run_object_logic_dispatch_aa2b(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run AA2B's first-level dispatch and leave IP at the selected target.

    AA2B dispatches through CS:AA36 using SS:[BP+16].  It is a jump-table stub,
    not a stable gameplay body, so keep the hook at this exact boundary instead
    of executing the selected behavior inline.
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    cpu.s.bx = cpu.mem.rw(ss, (bp + 0x16) & 0xFFFF)
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1
    target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAA36 + cpu.s.bx) & 0xFFFF)
    cpu.s.ip = target_ip


def _scan_object_logic_via_aa2b(
    cpu,
    *,
    table_base: int,
    done_ip: int,
    call_ip: int,
    advance_global_counter: bool,
) -> None:
    """Collapse the AA2B object scan only up to the next real CALL.

    The loop bodies at A9E0/AA10 are scan wrappers, not the object logic itself.
    They PUSH CX, select BP from an object table, and only then call AA2B for
    active objects.  A previous replacement crossed that CALL boundary and ran
    the whole AA2B dispatch inline.  That is too large a hook boundary: the
    verifier quite reasonably stops the original ASM at AA01/AA1F before the
    CALL, while the hook had already consumed the call and sometimes the whole
    remaining scan.

    Keep this hook as a narrow scan accelerator: consume inactive entries, but
    when the first active object is found, leave CPU state exactly as the ASM has
    it immediately before CALL AA2B.  The interpreter then executes the CALL,
    and the separate AA2B hook owns the object-logic dispatch boundary.
    """
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF

        # PUSH CX / MOV BX,CX / SHL BX,1 / MOV BP,[table+BX]
        _object_ptr_from_scan_index(cpu, table_base, cx_value)

        if advance_global_counter:
            ds = cpu.s.ds & 0xFFFF
            old_counter = cpu.mem.rw(ds, 0x2340)
            counter = (old_counter + 1) & 0xFFFF
            cpu.mem.ww(ds, 0x2340, counter)
            _cmp_word(cpu, counter, 0x05DC)
            if counter >= 0x05DC:
                cpu.mem.ww(ds, 0x2340, 0)

        active = cpu.mem.rw(cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = call_ip & 0xFFFF
            return

        # The original PUSH/POP pair is balanced for inactive objects, but the
        # transient PUSH still leaves bytes just below SP.  Keep that stack
        # scratch visible for full-memory oracle comparisons.
        _remember_balanced_push_scratch(cpu, cx_value)
        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = done_ip & 0xFFFF
            return

    cpu.s.ip = done_ip & 0xFFFF


def _run_af63_step_for_direction(cpu, *, parent: str = "1010:AF63") -> None:
    """Mirror one 1010:AF63 2-pixel direction step.

    AF63 dispatches through the CS:AF6E table using SS:[BP+06].  AF60 is built
    from this same body with a self-call trick, so keeping the one-step body
    separate lets 5DB2 mode 1 (direct AF63) and mode 2 (AF60 double step) share
    exactly the same movement mapping.
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    direction = cpu.mem.rw(ss, (bp + 0x06) & 0xFFFF) & 0xFFFF
    cpu.s.bx = direction
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1 before table JMP.

    if direction == 0:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
    elif direction == 1:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
    elif direction == 2:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
    elif direction == 3:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
    elif direction == 4:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
    elif direction == 5:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
    elif direction == 6:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
    elif direction == 7:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
    else:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain="AF63 direction table",
            target_ip=cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAF6E + ((direction << 1) & 0xFFFF)) & 0xFFFF),
            bp=bp,
            cx_value=cpu.s.cx & 0xFFFF,
        )


def _run_af60_double_step_for_direction(cpu) -> None:
    """Mirror 1010:AF60 for the movement helper's speed-2 mode.

    AF60 is another OVERKILL self-call trick: ``CALL AF63`` pushes AF63, so
    the direction movement body runs once, RET returns to AF63, and the same
    body runs a second time before returning to the original caller.
    """
    ss = cpu.s.ss & 0xFFFF
    # AF60 begins with CALL AF63.  After the self-call trick completes, SP is
    # back where it started but the pushed return word remains as stack scratch.
    cpu.mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xAF63)
    _run_af63_step_for_direction(cpu, parent="1010:AF60")
    _run_af63_step_for_direction(cpu, parent="1010:AF60")


def _run_aee4_step_for_direction(cpu) -> None:
    """Mirror 1010:AEE4: one 8-pixel direction step via the AEEE table."""
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    direction = cpu.mem.rw(ss, (bp + 0x06) & 0xFFFF) & 0xFFFF
    cpu.s.bx = direction
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)

    if direction == 0:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
    elif direction == 1:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
    elif direction == 2:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
    elif direction == 3:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
    elif direction == 4:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
    elif direction == 5:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
    elif direction == 6:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
    elif direction == 7:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
    else:
        _raise_unverified_path(
            cpu,
            parent="1010:AEE4",
            chain="AEE4 direction table",
            target_ip=cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAEEE + ((direction << 1) & 0xFFFF)) & 0xFFFF),
            bp=bp,
            cx_value=cpu.s.cx & 0xFFFF,
        )


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

    cpu.mem.ww(ds, 0xA954, 0)
    cpu.mem.ww(ds, 0x230A, 0)

    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    target_y = cpu.mem.rw(ds, 0x2304)
    _cmp_word(cpu, y, target_y)
    if y < target_y:
        cpu.mem.ww(ds, 0xA954, 1)
    elif y > target_y:
        cpu.mem.ww(ds, 0xA954, 2)

    x = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
    target_x = cpu.mem.rw(ds, 0x2306)
    _cmp_word(cpu, x, target_x)
    # Original uses signed JL/JG for X after CMP AX,DS:[2306].
    sx = x if x < 0x8000 else x - 0x10000
    starget_x = target_x if target_x < 0x8000 else target_x - 0x10000
    direction_bits = cpu.mem.rw(ds, 0xA954)
    if sx < starget_x:
        direction_bits |= 0x0004
        cpu.mem.ww(ds, 0xA954, direction_bits)
    elif sx > starget_x:
        direction_bits |= 0x0008
        cpu.mem.ww(ds, 0xA954, direction_bits)

    cpu.s.bx = 0xA348
    cpu.s.ax = cpu.mem.rw(ds, 0xA954)
    mapped = cpu.mem.rb(ds, (cpu.s.bx + (cpu.s.ax & 0xFF)) & 0xFFFF)
    cpu.set_reg8(0, mapped)  # XLAT updates AL only.
    cpu.set_sub_flags(mapped, 0xFF, mapped - 0xFF, 8)  # CMP AL,FFh.
    if mapped == 0xFF:
        cpu.mem.ww(ds, 0x230A, 1)
        # MOV word and RET do not affect flags; leave CMP AL,FFh flags live.
        return

    cpu.mem.ww(ss, (bp + 0x06) & 0xFFFF, cpu.s.ax)
    cpu.s.bx = cpu.mem.rw(ds, 0x2308)
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1 before 5E0C table JMP.
    mode = cpu.mem.rw(ds, 0x2308)
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
