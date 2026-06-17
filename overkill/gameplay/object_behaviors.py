"""Object behaviour families + logic dispatch for the OVERKILL object runtime.

Architecture layer: **lifted**.  The per-family object behaviour bodies
(B73E/B86D/B9F0/AB77/ABA3/AE09/8D4F/AED8/B24D, the ABCA sprite-0F collision, the
AD04 logic branch, the AB10 logic body) and the AA2B/EFAE logic dispatch +
object-logic scan.  Behaviours are reached by *address* through the hook
registry, not by direct Python call, so this module depends on the movement /
postmove / contact / bounds / deactivation seams but nothing depends back on it
except the thin object_runtime dispatch spine.  Conservative names only; bodies
relocated verbatim.
"""
from __future__ import annotations

from dos_re.cpu import CF, DF
from overkill.asm import (
    _add_mem_word, _add_reg16, _and_mem_word, _cmp_byte, _cmp_word,
    _inc_mem_word_preserve_cf, _sub_mem_word,
)
from overkill.gameplay.collision import run_object_slot_scan_guard_ac81, run_tile_collision_probe_ac28
from overkill.gameplay.contact_overlap import run_overlap_contact_selector_b250
from overkill.gameplay.object_bounds import _run_object_bounds_tile_tail_ad60
from overkill.gameplay.object_movement import (
    _run_aee4_step_for_direction, _run_af22_three_pixel_step_for_direction,
    _run_movement_direction_5db2, _run_object_delta_helper_5e1b,
    run_object_target_move_b729, run_runtime_patched_object_steer_5e42,
)
from overkill.gameplay.object_postmove import _run_object_postmove_bc4b
from overkill.gameplay.object_runtime_common import (
    _call_verified_child_near, _no_patch_guard, _object_ptr_from_scan_index,
    _push_loop_count_for_interpreted_tail, _raise_unverified_path,
    _remember_balanced_push_scratch, _run_interpreted_near_call_observed,
)
from overkill.gameplay.object_spawns import _run_formation_spawn_7476_observed
from overkill.gameplay.objects import run_object_motion_table_ab34, run_object_scroll_sprite_ab4f
from overkill.recovered.views.object_slots import (
    OFF_DIRECTION_OR_STEP, OFF_DRAW_LAYER, OFF_LOGIC_ID, OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE, OFF_TARGET_X, OFF_TARGET_Y, OFF_TRANSITION_LATCH, OFF_X, OFF_Y,
)



def _call_ab34(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAB34, lambda c: run_object_motion_table_ab34(c, _no_patch_guard), return_ip)


def _call_ab4f(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAB4F, lambda c: run_object_scroll_sprite_ab4f(c, _no_patch_guard), return_ip)


def _call_ac28(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAC28, lambda c: run_tile_collision_probe_ac28(c, _no_patch_guard), return_ip)


def _call_ac81(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAC81, lambda c: run_object_slot_scan_guard_ac81(c, _no_patch_guard), return_ip)


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
        target_y_local = cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF)
        target_x_local = cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF)
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
        cpu.mem.ww(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF, 0x0004)
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
            cpu.mem.ww(ss, (bp + OFF_TARGET_Y) & 0xFFFF, cpu.s.ax)
        _and_mem_word(cpu, ss, (bp + OFF_TARGET_Y) & 0xFFFF, 0xFFF8)
        cpu.mem.ww(ds, 0x2340, 0x0028)
        cpu.mem.ww(ss, (bp + OFF_SUBSTATE) & 0xFFFF, 0x0000)
        cpu.mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, 0x0078)
        cpu.mem.ww(ss, (bp + OFF_TARGET_X) & 0xFFFF, 0x0020)
        _run_object_postmove_bc4b(
            cpu,
            parent=parent,
            chain=f"{chain} -> B73E -> B7BD -> {branch}",
            cx_value=cx_value,
        )
        cpu.s.ip = cpu.pop()

    substate = cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    _cmp_word(cpu, substate, 0xFFFF)
    if substate != 0xFFFF:
        cpu.s.bx = substate
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
        target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xB74E + cpu.s.bx) & 0xFFFF)
        if target_ip == 0xB754:
            y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
            target_y = cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF)
            cpu.s.ax = y
            _cmp_word(cpu, y, target_y)
            if y != target_y:
                run_b85c_move_to_target()
                return
            x = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
            target_x = cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF)
            cpu.s.ax = x
            _cmp_word(cpu, x, target_x)
            if x != target_x:
                run_b85c_move_to_target()
                return
            _add_mem_word(cpu, ss, (bp + OFF_SUBSTATE) & 0xFFFF, 1)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B754", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        if target_ip == 0xB770:
            cpu.mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, 0x0079)
            _add_mem_word(cpu, ss, (bp + OFF_SUBSTATE) & 0xFFFF, 1)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B770", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        if target_ip == 0xB77B:
            _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0x0004)
            _cmp_word(cpu, cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF), 0x00A0)
            if cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF) >= 0x00A0:
                cpu.mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, 0x0077)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B77B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> B73E[substate]",
            target_ip=target_ip, bp=bp, cx_value=cx_value,
        )

    timer = cpu.mem.rw(ds, 0x2338)
    y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
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
    cpu.mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, cpu.s.ax)

    target_y = cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF)
    cpu.s.ax = y
    _cmp_word(cpu, y, target_y)
    if y != target_y:
        # B85C: move toward the target; shared by Y-mismatch and X-mismatch.
        run_b85c_move_to_target()
        return

    x = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    target_x = cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF)
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
        cpu.mem.ww(ss, (bp + OFF_TARGET_X) & 0xFFFF, cpu.s.ax)
        cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + 2) & 0xFFFF
        cpu.mem.ww(ss, (bp + OFF_TARGET_Y) & 0xFFFF, cpu.s.ax)
        cpu.mem.ww(ds, 0xA842, cpu.s.si)

        x = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
        cpu.s.ax = x
        _cmp_word(cpu, x, cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF))
        if x != cpu.mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF):
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D -> BC4B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
        cpu.s.ax = y
        _cmp_word(cpu, y, cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF))
        if y != cpu.mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF):
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


def _run_b250_overlap_contact_selector(cpu, *, caller: str) -> int:
    """Run the shared B250 overlap/contact selector.

    The selector itself now lives in :mod:`overkill.gameplay.contact_overlap`.
    This thin shim injects the object-runtime near-call helper so the original
    ``9E19`` contact side-effect remains a bounded, verifier-visible boundary,
    and returns the selected original tail IP (AD5A/ADC9) to the caller.
    """
    return run_overlap_contact_selector_b250(
        cpu, caller=caller, near_call=_run_interpreted_near_call_observed
    )


def _run_object_behavior_b24d(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed ``1010:B24D`` object-family behavior prelude.

    B24D is selected by the second-level EFAE object-family dispatcher in the
    active gameplay snapshot.  The hot path calls the runtime-patched 5E42
    steering helper, then runs the shared B250 overlap/contact selector.  This
    hook stops at the selected AD5A/ADC9 frontier; larger parents may compose
    those tails when their own verifier boundary requires a near return.
    """
    # B24D: CALL 5E42.  The live 5E42 body is the runtime-patched gameplay
    # steering helper, not the cold executable bytes at the same address.
    cpu.push(0xB250)
    run_runtime_patched_object_steer_5e42(cpu)
    if (cpu.s.ip & 0xFFFF) != 0xB250:
        raise RuntimeError(f"5E42 returned to unexpected IP {cpu.s.ip:04X} inside B24D")

    cpu.s.ip = _run_b250_overlap_contact_selector(cpu, caller="B24D")


def _run_object_behavior_b86d(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift observed 1010:B86D object-slot behavior branches.

    This is still low-level object-runtime logic: it updates slot coordinates,
    sprite words, movement-target globals, and then joins the shared BC4B
    post-move/collision tail.  The B8F8 edge-steering tail is now covered too;
    less frequent later B90x/B93x/B96x continuations remain separate frontiers.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    def call_7476(return_ip: int) -> None:
        _run_interpreted_near_call_observed(cpu, 0x7476, return_ip & 0xFFFF, max_steps=12000)
        if (cpu.s.ip & 0xFFFF) != (return_ip & 0xFFFF):
            raise RuntimeError(f"7476 returned to unexpected IP {cpu.s.ip:04X} inside B86D")

    def run_b729_target_move(return_ip: int, *, mode: int) -> bool:
        mem.ww(ds, 0x2308, mode & 0xFFFF)
        _call_verified_child_near(
            cpu,
            0xB729,
            lambda c: run_object_target_move_b729(c, _no_patch_guard),
            return_ip & 0xFFFF,
        )
        if (cpu.s.ip & 0xFFFF) != (return_ip & 0xFFFF):
            raise RuntimeError(f"B729 returned to unexpected IP {cpu.s.ip:04X} inside B86D")
        _cmp_word(cpu, mem.rw(ds, 0x230A), 0)
        return mem.rw(ds, 0x230A) == 0

    def run_b8f8_edge_steer() -> None:
        # B8F8: object has crossed the B86D entry guard (early global phase or
        # X > 00C0h).  Steer it back toward the DS:237C reference box, force the
        # outgoing sprite, then join the shared post-move/collision boundary.
        cpu.s.bx = 0x237C
        _run_object_delta_helper_5e1b(cpu)
        cpu.push(0xB901)
        run_runtime_patched_object_steer_5e42(cpu)
        if (cpu.s.ip & 0xFFFF) != 0xB901:
            raise RuntimeError(f"5E42 returned to unexpected IP {cpu.s.ip:04X} inside B86D/B8F8")
        mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, 0x0076)
        cpu.s.ip = 0xBC4B

    _cmp_word(cpu, mem.rw(ds, 0xA47E), 0x0002)
    if mem.rw(ds, 0xA47E) <= 0x0002:
        run_b8f8_edge_steer()
        return

    x = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    _cmp_word(cpu, x, 0x00C0)
    if x > 0x00C0:
        run_b8f8_edge_steer()
        return

    _cmp_word(cpu, mem.rw(ds, 0xA7A0), 0x0028)
    if mem.rw(ds, 0xA7A0) < 0x0028:
        mem.ww(ds, 0x2308, 0x0001)
        mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, 0x0075)
        _and_mem_word(cpu, ss, (bp + OFF_TARGET_Y) & 0xFFFF, 0xFFFE)
        _and_mem_word(cpu, ss, (bp + OFF_Y) & 0xFFFF, 0xFFFE)
        _and_mem_word(cpu, ss, (bp + OFF_TARGET_X) & 0xFFFF, 0xFFFE)
        _and_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0xFFFE)
        if not run_b729_target_move(0xB8A3, mode=1):
            mem.ww(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF, 0x0004)
        cpu.s.ip = 0xBC4B
        return

    game_counter = mem.rw(ds, 0x2340)
    _cmp_word(cpu, game_counter, 0x02EF)
    if game_counter == 0x02EF:
        call_7476(0xB8BB)
    else:
        _cmp_word(cpu, game_counter, 0x0159)
        if game_counter == 0x0159:
            call_7476(0xB8C6)
        else:
            _cmp_word(cpu, game_counter, 0x0079)
            if game_counter == 0x0079:
                call_7476(0xB8D0)

    old_ax = mem.rw(ds, 0x2342)
    cpu.set_sub_flags(0, old_ax, -old_ax, 16)
    cpu.s.ax = (-old_ax) & 0xFFFF
    _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, cpu.s.ax)
    cpu.s.ax = 0x0075
    _cmp_word(cpu, mem.rw(ds, 0x2342), 0xFFFF)
    if mem.rw(ds, 0x2342) != 0xFFFF:
        cpu.s.ax = 0x0076
    mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, cpu.s.ax)
    _cmp_word(cpu, mem.rw(ds, 0x2328), 0x0007)
    if mem.rw(ds, 0x2328) == 0x0007:
        _inc_mem_word_preserve_cf(cpu, ss, (bp + OFF_X) & 0xFFFF)
    cpu.s.ip = 0xBC4B


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
        _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0x0002)

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
        _add_mem_word(cpu, ss, (bp + OFF_TARGET_Y) & 0xFFFF, cpu.s.ax)
        cpu.s.ax = mem.rw(ds, 0x2346)
        _add_mem_word(cpu, ss, (bp + OFF_TARGET_X) & 0xFFFF, cpu.s.ax)

        # BA13..BA1A: wrap target X from >D0h to 20h.
        target_x = mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF)
        _cmp_word(cpu, target_x, 0x00D0)
        if target_x > 0x00D0:
            mem.ww(ss, (bp + OFF_TARGET_X) & 0xFFFF, 0x0020)

        # BA1F..BA31: if current position plus vertical delta reached target,
        # use the direct sprite-refresh/helper branch; otherwise branch to BA99.
        cpu.s.ax = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
        old_ax = cpu.s.ax
        delta_y = mem.rw(ds, 0x2342)
        cpu.s.ax = (cpu.s.ax + delta_y) & 0xFFFF
        cpu.set_add_flags(old_ax, delta_y, old_ax + delta_y, 16)
        target_y = mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF)
        _cmp_word(cpu, cpu.s.ax, target_y)
        reached_target = cpu.s.ax == target_y
        if reached_target:
            cpu.s.ax = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
            target_x = mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF)
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
            cpu.s.ax = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
            target_x = mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF)
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
                _cmp_word(cpu, mem.rw(ss, (bp + OFF_X) & 0xFFFF), 0x00D0)
                if mem.rw(ss, (bp + OFF_X) & 0xFFFF) > 0x00D0:
                    mem.ww(ss, (bp + OFF_X) & 0xFFFF, 0x0010)
                cpu.s.ip = 0xBC4B
                return

            # BA73..BA8D: align target/current coordinates and publish movement
            # target globals.
            cpu.s.ax = mem.rw(ss, (bp + OFF_TARGET_Y) & 0xFFFF)
            cpu.s.ax &= 0xFFFE
            cpu.set_logic_flags(cpu.s.ax, 16)
            _and_mem_word(cpu, ss, (bp + OFF_Y) & 0xFFFF, 0xFFFE)
            mem.ww(ds, 0x2304, cpu.s.ax)
            cpu.s.ax = mem.rw(ss, (bp + OFF_TARGET_X) & 0xFFFF)
            cpu.s.ax &= 0xFFFE
            cpu.set_logic_flags(cpu.s.ax, 16)
            _and_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0xFFFE)
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
    mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, cpu.s.ax)
    cpu.s.ip = 0xBC4B


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

    cpu.s.ax = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    cpu.mem.ww(ds, 0xD1FE, cpu.s.ax)
    cpu.s.ax = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    cpu.mem.ww(ds, 0xD200, cpu.s.ax)

    cpu.s.bx = cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1
    target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xEFC4 + cpu.s.bx) & 0xFFFF)
    cpu.s.ip = target_ip


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

    _call_ab4f(cpu, 0xAB81)
    if cpu.s.ip != 0xAB81:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AB4F", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)

    _call_ac28(cpu, 0xAB84)
    if cpu.s.ip == 0xAA44:
        cpu.set_flag(CF, False)
        cpu.s.ip = cpu.pop()
    if cpu.s.ip != 0xAB84:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AC28", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)
    if cpu.get_flag(CF):
        cpu.s.ip = 0xAB8F
        return

    _call_ac81(cpu, 0xAB89)
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

        mem.ww(ss, (bp + OFF_LOGIC_ID) & 0xFFFF, 0x0001)
        mem.ww(ss, (bp + OFF_DRAW_LAYER) & 0xFFFF, 0x0004)
        mem.ww(ss, (bp + OFF_TRANSITION_LATCH) & 0xFFFF, 0x0000)
        mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, 0x0000)

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
        _call_ab34(cpu, 0xABD7)
        if cpu.s.ip != 0xABD7:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> AB34",
                target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
            )

        _call_ac28(cpu, 0xABDA)
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
            _call_ac81(cpu, 0xABE7)
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

    sprite = mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF)
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
    mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, cpu.s.ax)

    _call_ac81(cpu, 0xABBA)
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

    timer = mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    _cmp_word(cpu, timer, 0x0000)
    if timer != 0:
        _sub_mem_word(cpu, ss, (bp + OFF_SUBSTATE) & 0xFFFF, 1)
        if mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF) == 0:
            mem.ww(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF, 0x0000)
    if timer == 0 or mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF) == 0:
        _sub_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 2)

    cpu.s.ax = mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (old_ax + 0x0028) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0028, old_ax + 0x0028, 16)
    mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, cpu.s.ax)

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


def _run_object_behavior_aed8(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed EFAE logic_id=2 movement/tile-probe branch at AED8."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    _sub_mem_word(cpu, ss, (bp + OFF_SUBSTATE) & 0xFFFF, 1)
    if mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF) == 0:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 timer expired", target_ip=0xADC9, bp=bp, cx_value=cx_value)

    cpu.s.ax = 0xB250
    # AED8 pushes B250 and falls into AEE4.  The return word is later replaced
    # by the nested ADBF call scratch; keep SP unchanged in the lifted form.
    mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xB250)
    _run_aee4_step_for_direction(cpu)

    selected_tail = _run_b250_overlap_contact_selector(cpu, caller="AED8")
    if selected_tail == 0xAD5A:
        _run_object_bounds_tile_tail_ad60(
            cpu,
            parent=parent,
            chain=f"{chain} -> AED8 -> B250 -> AD5A",
            cx_value=cx_value,
            add_a278_to_x=True,
        )
        return
    if selected_tail == 0xADC9:
        # ADC9: MOV SS:[BP+02],FFFFh; JMP AD60.  Unlike AD5A, this tail does
        # not first add DS:A278 to X.
        mem.ww(ss, (bp + OFF_X) & 0xFFFF, 0xFFFF)
        _run_object_bounds_tile_tail_ad60(
            cpu,
            parent=parent,
            chain=f"{chain} -> AED8 -> B250 -> ADC9",
            cx_value=cx_value,
            add_a278_to_x=False,
        )
        return
    raise RuntimeError(f"unexpected B250 selector target 1010:{selected_tail:04X} inside AED8")


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
    mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, cpu.s.ax)

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
    mem.ww(ss, (bp + OFF_X) & 0xFFFF, cpu.s.ax)

    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    old_ax = cpu.s.ax & 0xFFFF
    addend = mem.rw(ds, (cpu.s.bx + 0x04) & 0xFFFF)
    cpu.s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ss, (bp + OFF_Y) & 0xFFFF, cpu.s.ax)
    cpu.s.ip = cpu.pop()


def _run_object_logic_dispatch_aa2b(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run AA2B's first-level dispatch and leave IP at the selected target.

    AA2B dispatches through CS:AA36 using SS:[BP+16].  It is a jump-table stub,
    not a stable gameplay body, so keep the hook at this exact boundary instead
    of executing the selected behavior inline.
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    cpu.s.bx = cpu.mem.rw(ss, (bp + OFF_DRAW_LAYER) & 0xFFFF)
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
