"""Lifted OVERKILL gameplay object behavior and post-move collision chains.

The functions in this module are game-specific source-port logic that used to
live in ``overkill/hooks.py``.  They intentionally keep original addresses in
names/docstrings because their behavior is still verified against the DOS ASM
oracle.  ``overkill/hooks.py`` imports these functions back and remains the exact
CS:IP hook-registration layer.
"""
from __future__ import annotations

from dos_re.cpu import CF, DF, ZF
from dos_re.hooks import call_installed_hook_like_near_call
from overkill.asm import (
    _add_mem_word,
    _add_reg16,
    _and_mem_word,
    _cmp_byte,
    _cmp_word,
    _dec_mem_word_preserve_cf,
    _dec_reg16_preserve_cf,
    _inc_mem_word_preserve_cf,
    _inc_reg16_preserve_cf,
    _sub_mem_word,
    _sub_reg16,
    _test_word,
)
from overkill.gameplay.collision import (
    run_object_deactivate_logic_dispatch_c054,
    run_object_slot_scan_guard_ac81,
    run_object_tile_sweep_blocked_b032,
    run_player_hazard_scan_guard_bdd0,
    run_postmove_contact_window_aa71,
    run_tile_collision_probe_ac28,
    run_tile_lookup_505b,
    run_tile_probe_5073,
)
from overkill.gameplay.contact_overlap import run_overlap_contact_selector_b250
from overkill.gameplay.object_runtime_common import (
    _or_mem_word,
    _neg_reg16,
    _signed16,
    _format_object_context,
    _raise_unverified_path,
    _run_interpreted_near_call_observed,
    _run_original_tail_to_caller,
    _call_verified_child_near,
)
from overkill.gameplay.object_movement import (
    SIG_OBJECT_CHILD_COORD_UPDATE_9FEA,
    SIG_LINKED_OBJECT_COORD_QUAD_UPDATE_9FAF,
    SIG_OBJECT_X_STEP_LEFT_CLAMP_A5D1,
    SIG_OBJECT_X_STEP_RIGHT_CLAMP_A5EA,
    SIG_OBJECT_Y_STEP_UP_CLAMP_A5F9,
    SIG_OBJECT_Y_STEP_DOWN_CLAMP_A607,
    SIG_OBJECT_VERTICAL_SCROLL_EDGE_RESPONSE_A616,
    SIG_OBJECT_BOTTOM_SCROLL_OFFSET_DECAY_A63C,
    SIG_OBJECT_TOP_SCROLL_EDGE_RESPONSE_A648,
    SIG_OBJECT_TOP_SCROLL_OFFSET_RECOVER_A662,
    SIG_OBJECT_TARGET_CHASE_D281,
    SIG_MOVEMENT_DIR_STEP_8PX_AEE4,
    SIG_MOVEMENT_DIR_STEP_3PX_AF22,
    SIG_MOVEMENT_DIR_STEP_2PX_AF63,
    SIG_MOVEMENT_DOUBLE_STEP_2PX_AF60,
    SIG_OBJECT_TARGET_MOVE_B729,
    SIG_OBJECT_SCROLL_FORWARD_STEP_A6FE,
    SIG_OBJECT_SCROLL_BACKWARD_STEP_A781,
    SIG_OBJECT_SCROLL_FORWARD_ROW_A74E,
    SIG_OBJECT_SCROLL_BACKWARD_ROW_A7D0,
    SIG_OBJECT_SCROLL_ROW_WRAP_A746,
    SIG_OBJECT_SCROLL_ROW_WRAP_A7E3,
    SIG_OBJECT_SCROLL_WORLD_PROGRESS_GATE_A66F,
    SIG_OBJECT_PLAYER_CHASE_CANDIDATE_SCAN_B15A,
    _run_object_delta_helper_5e1b,
    _run_runtime_patched_object_steer_5e42,
    run_runtime_patched_object_steer_5e42,
    run_object_child_coord_update_9fea,
    run_linked_object_coord_quad_update_9faf,
    _run_two_pass_word_clamp_step,
    run_object_x_step_left_clamp_a5d1,
    run_object_x_step_right_clamp_a5ea,
    run_object_y_step_up_clamp_a5f9,
    run_object_y_step_down_clamp_a607,
    run_object_bottom_scroll_offset_decay_a63c,
    run_object_top_scroll_offset_recover_a662,
    _assert_vertical_scroll_biases,
    _run_object_top_scroll_edge_response_a648_body,
    run_object_top_scroll_edge_response_a648,
    run_object_vertical_scroll_edge_response_a616,
    run_object_scroll_world_progress_gate_a66f,
    run_object_scroll_forward_row_a74e,
    run_object_scroll_backward_row_a7d0,
    run_object_scroll_row_wrap_forward_a746,
    run_object_scroll_row_wrap_backward_a7e3,
    run_object_scroll_forward_step_a6fe,
    run_object_scroll_backward_step_a781,
    _run_af22_three_pixel_step_for_direction,
    run_object_target_chase_d281,
    _run_af63_step_for_direction,
    _run_af60_double_step_for_direction,
    run_movement_dir_double_step_2px_af60,
    run_movement_dir_step_2px_af63,
    run_movement_dir_step_3px_af22,
    run_movement_dir_step_8px_aee4,
    _run_aee4_step_for_direction,
    _run_movement_direction_5db2,
    _call_tile_lookup_505b,
    _b00d_tile_is_blocking,
    _call_b00d_component,
    _run_player_chase_candidate_scan_b15a,
    run_player_chase_candidate_scan_b15a,
    run_object_target_move_b729,
)
from overkill.gameplay.object_runtime_common import _no_patch_guard
from overkill.gameplay.contact_side_effects import (
    _run_object_overlap_scan_62f6,
    _run_collision_handler_bec5_observed,
    _run_collision_mark_a8c2_tail_bf5f,
    _run_post_contact_9e69_observed,
    _run_post_contact_9e98_tail_observed,
)
from overkill.gameplay.object_postmove import (
    _call_aa71,
    run_object_postmove_prelude_bc45,
    _run_object_postmove_bc4b,
)
from overkill.gameplay.object_runtime_common import _remember_balanced_push_scratch
from overkill.gameplay.object_deactivation import (
    _run_deactivate_bd17_observed,
    _run_collision_death_tail_bfc7,
    _run_collision_cleanup_bd0d_observed,
    _run_score_add_5f0d_observed,
    _run_y_clamp_bcb1,
)
from overkill.gameplay.object_spawns import (
    _find_free_effect_slot_7524,
    _find_free_object_slot_7573,
    _run_c054_c12d_effect_spawn_tail,
    _run_formation_spawn_7476_observed,
    _run_linked_effect_spawn_7420_observed,
    run_object_slot_allocate_or_reclaim_7547,
    run_object_spawn_anchor_offset_a571,
    run_object_spawn_seed_a4ea,
    run_object_spawn_seed_from_source_a4d7,
)
from overkill.gameplay.view_window import _run_view_window_check_aa46
from overkill.gameplay.objects import (
    run_object_motion_table_ab34,
    run_object_scroll_sprite_ab4f,
)
from overkill.recovered.adapters.movement_adapter import (
    MOVEMENT_BLOCKED_FLAG,
    MOVEMENT_DIRECTION_BITS,
    MOVEMENT_MODE,
    decide_target_seek_direction_from_dos,
    publish_object_slot_target_to_movement_globals,
    run_player_center_target_setup_b1bf,
    apply_direction_step_to_current_object,
)
from overkill.recovered.adapters.collision_adapter import (
    run_postmove_y_clamp_bcb1_body,
    run_tile_lookup_505b_body,
    run_tile_probe_5073_body,
)
from overkill.recovered.adapters.object_behavior_adapter import (
    run_player_chase_acquired_target_validity_b1b0,
    run_player_chase_candidate_checks_b15a,
)
from overkill.recovered.domain.movement import VerticalScrollEdgeDecision, VerticalScrollEdgeInput
from overkill.recovered.systems.collision import tile_sweep_plan_for_direction
from overkill.recovered.systems.movement import (
    decay_bottom_scroll_bias_a63c,
    one_pixel_axis_step,
    recover_top_scroll_bias_a662,
    top_scroll_edge_response_a648,
    two_pass_axis_clamp_step,
    vertical_scroll_edge_response_a616,
)
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL,
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_LAST_SLOT_BASE,
    OBJECT_SLOT_STRIDE,
    OFF_ACQUIRED_TARGET_PTR,
    OFF_ACTIVE_WORD,
    OFF_DIRECTION_OR_STEP,
    OFF_DRAW_LAYER,
    OFF_GATE_OR_LAYER,
    OFF_LOGIC_ID,
    OFF_OBJECT_TYPE,
    OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE,
    OFF_TARGET_X,
    OFF_TARGET_Y,
    OFF_TRANSITION_LATCH,
    OFF_X,
    OFF_Y,
    ObjectSlotView,
)
from overkill.runtime_code import require_runtime_code_variant





def _call_ab34(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAB34, lambda c: run_object_motion_table_ab34(c, _no_patch_guard), return_ip)


def _call_ab4f(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAB4F, lambda c: run_object_scroll_sprite_ab4f(c, _no_patch_guard), return_ip)


def _call_ac28(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAC28, lambda c: run_tile_collision_probe_ac28(c, _no_patch_guard), return_ip)


def _call_ac81(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAC81, lambda c: run_object_slot_scan_guard_ac81(c, _no_patch_guard), return_ip)







SIG_OBJECT_BOUNDS_TILE_PRELUDE_AD5A = bytes.fromhex(
    "a1 78 a2 01 46 02 83 7e 02 08 73 03 e9 ae 0f"
)
SIG_OBJECT_DRIFT_DOWNRIGHT_AE2C = bytes.fromhex(
    "81 7e 04 c8 00 74 96 83 6e 02 04 f7 46 04 07 00"
)
SIG_OBJECT_DRIFT_UPRIGHT_AE7D = bytes.fromhex(
    "83 7e 04 00 75 03 e9 43 ff 83 6e 02 04 f7 46 04 0f 00"
)

# 8-direction movement step tables.  Each routine reads the direction index from
# SS:[BP+06], doubles it, and dispatches through a CS jump table to a handler
# that adds/subtracts a fixed delta to SS:[BP+02] (X) and/or SS:[BP+04] (Y).  The
# three siblings differ only in their per-step delta (8px / 3px / 2px).  The full
# routine bytes (entry stub + table + handlers) are pinned so a runtime patch of
# either the dispatch or any handler disables the hook instead of guessing.
SIG_OBJECT_TILE_SWEEP_DISPATCH_B00D = bytes.fromhex(
    "e8 63 a0 83 fb ff 74 1d 8b d3 8b 5e 06 d1 e3 "
    "2e ff a7 22 b0 90 7d b0 c9 b0 cc b0 39 b0 "
    "3c b0 0c b1 0f b1 7a b0"
)
SIG_OBJECT_PLAYER_CHASE_B1B0 = bytes.fromhex(
    "a1 28 23 05 6d 00 89 46 08 83 7e 1c 01 74 68 "
    "a1 7e 23 05 0a 00 a3 06 23 a1 80 23 05 0c 00 "
    "a3 04 23 c7 06 08 23 02 00 83 26 04 23 fc 83 "
    "26 06 23 fc 83 66 04 fc 83 66 02 fc e8 c6 ab "
    "83 3e 0a 23 00 75 03 e9 6a fb"
)









































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






def _present_dispatch_target_5a92(cpu, bp: int) -> int:
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    obj_type = cpu.mem.rw(ss, (bp + OFF_OBJECT_TYPE) & 0xFFFF)
    index = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0x5AB6 + index) & 0xFFFF)


def _draw_dispatch_target_5ac8(cpu, bp: int) -> int:
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    obj_type = cpu.mem.rw(ss, (bp + OFF_OBJECT_TYPE) & 0xFFFF)
    index = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0x5AE2 + index) & 0xFFFF)


def _layer_draw_dispatch_target_7596(cpu, bp: int) -> int:
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    obj_type = cpu.mem.rw(ss, (bp + OFF_OBJECT_TYPE) & 0xFFFF)
    index = (obj_type << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0x75A0 + index) & 0xFFFF)


def _object_logic_target_aa2b(cpu, bp: int) -> int:
    """Predict AA2B's object-logic dispatch target from SS:[BP+16]."""
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    draw_layer = cpu.mem.rw(ss, (bp + OFF_DRAW_LAYER) & 0xFFFF)
    index = (draw_layer << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0xAA36 + index) & 0xFFFF)


def _object_family_target_efae(cpu, bp: int) -> int:
    """Predict EFAE's second-level behavior dispatch target from SS:[BP+18]."""
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    logic_id = cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
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





























SIG_OBJECT_TILE_SWEEP_PROBE_AFD8 = bytes.fromhex(
    "c7 06 30 a4 00 00 8b 46 02 a3 32 a4 a3 38 a4 8b 46 04 "
    "a3 34 a4 a3 36 a4 a1 78 a2 01 46 02 83 6e 02 10"
)


def run_object_tile_sweep_probe_afd8(cpu, self_disable_if_patched) -> None:
    """Lift 1010:AFD8, the object tile-sweep probe pre/post wrapper.

    The detailed direction-specific tile response still lives in the B00D jump
    table, but this wrapper names the shared contract around it: snapshot the
    object coordinate rectangle into A430-era scratch globals, bias X by the
    current scroll offset DS:A278, run the directional tile probe, restore X,
    and return with flags from CMP DS:A430,0.
    """
    if self_disable_if_patched(cpu, 0xAFD8, SIG_OBJECT_TILE_SWEEP_PROBE_AFD8, "overkill_object_tile_sweep_probe_afd8"):
        return
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    mem.ww(ds, 0xA430, 0x0000)
    s.ax = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    mem.ww(ds, 0xA432, s.ax)
    mem.ww(ds, 0xA438, s.ax)
    s.ax = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    mem.ww(ds, 0xA434, s.ax)
    mem.ww(ds, 0xA436, s.ax)
    s.ax = mem.rw(ds, 0xA278)
    _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, s.ax)
    _sub_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0x0010)
    _call_verified_child_near(
        cpu,
        0xB00D,
        lambda c: run_object_tile_sweep_dispatch_b00d(c, _no_patch_guard),
        0xAFFD,
    )
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (0x1010, 0xAFFD):
        raise RuntimeError(f"AFD8 expected B00D to return to 1010:AFFD, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
    _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0x0010)
    s.ax = mem.rw(ds, 0xA278)
    _sub_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, s.ax)
    _cmp_word(cpu, mem.rw(ds, 0xA430), 0)
    s.ip = cpu.pop()


































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





def _run_object_bounds_tile_tail_ad60(cpu, *, parent: str, chain: str, cx_value: int, add_a278_to_x: bool) -> None:
    """Shared AD5A/AD60 bounds + optional tile-probe tail used by object behaviors."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    if add_a278_to_x:
        cpu.s.ax = mem.rw(ds, 0xA278)
        _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, cpu.s.ax)

    x = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
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
    y = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    _cmp_word(cpu, y, 0x00C8)
    if y > 0x00C8:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AD60", cx_value=cx_value, pop_return=False)
        cpu.s.ip = cpu.pop()
        return
    draw_layer = mem.rw(ss, (bp + OFF_DRAW_LAYER) & 0xFFFF)
    _cmp_word(cpu, draw_layer, 0x0002)
    if draw_layer != 0x0002:
        cpu.s.ip = cpu.pop()
        return
    logic_id = mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
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





def _finish_ae2c_common(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    mem.ww(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF, 0x0001)
    _add_mem_word(cpu, ss, (bp + OFF_Y) & 0xFFFF, 4)
    cpu.s.ax = mem.rw(ds, 0x2326)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax &= 0x0008
    cpu.set_logic_flags(cpu.s.ax, 16)
    _add_reg16(cpu, 0, mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF))
    _add_reg16(cpu, 0, 0x0008)
    mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, cpu.s.ax)
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
    y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    _cmp_word(cpu, y, 0x00C8)
    if y == 0x00C8:
        _run_original_tail_to_caller(cpu, 0xADC9)
        return

    _sub_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 4)
    y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
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
    y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    _cmp_word(cpu, y, 0)
    if y == 0:
        _run_original_tail_to_caller(cpu, 0xADC9)
        return

    _sub_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 4)
    y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    _test_word(cpu, y, 0x000F)
    if (y & 0x000F) == 0:
        _run_original_tail_to_caller(cpu, 0xAE91)
        return

    cpu.mem.ww(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF, 0x0007)
    _sub_mem_word(cpu, ss, (bp + OFF_Y) & 0xFFFF, 4)
    cpu.s.ax = cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
    _add_reg16(cpu, 0, 0x0008)
    cpu.mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, cpu.s.ax)
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


def _run_tile_probe_5073(cpu) -> None:
    """Run 1010:5073 without consuming a near-call return word.

    Older lifted parent tails need the body in-place rather than as a hook
    boundary.  Delegate to the same recovered adapter as the public hook so the
    tile-offset formula has one canonical implementation.
    """
    run_tile_probe_5073_body(cpu, pop_return=False)


def _run_tile_lookup_505b(cpu) -> None:
    """Run 1010:505B without consuming a near-call return word.

    Older lifted parent tails need the body in-place rather than as a hook
    boundary.  Delegate to the same recovered adapter as the public hook so the
    raw-tile -> class-byte mapping has one canonical implementation.
    """
    run_tile_lookup_505b_body(cpu, pop_return=False)




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



















def _call_tile_probe_5073(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0x5073, lambda c: run_tile_probe_5073(c, _no_patch_guard), return_ip)




def _call_player_hazard_scan_bdd0(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xBDD0, lambda c: run_player_hazard_scan_guard_bdd0(c, _no_patch_guard), return_ip)


def _jump_object_tile_sweep_blocked_b032(cpu) -> None:
    """Tail-jump into the B032 sentinel without adding a CALL frame.

    B032 is reached by JMP from the B00D table, so the existing top-of-stack
    return word belongs either to B00D's caller or to an internal diagonal
    component CALL.  Route through the verifier if installed, but never push an
    extra near-CALL frame.
    """
    key = (cpu.s.cs & 0xFFFF, 0xB032)
    default_handler = lambda c: run_object_tile_sweep_blocked_b032(c, _no_patch_guard)
    handler = cpu.replacement_hooks.get(key, default_handler)
    name = cpu.hook_names.get(key, getattr(handler, "__name__", "replacement"))
    cpu.s.ip = 0xB032
    verifier = getattr(cpu, "hook_verifier", None)
    if (
        verifier is not None
        and getattr(cpu, "hook_verifier_verify_nested_calls", True)
        and key not in getattr(cpu, "hook_verifier_passthrough", set())
    ):
        verifier(cpu, key, handler, name)
    else:
        handler(cpu)




def _run_b00d_move_right(cpu) -> bool:
    """Run the B03C/B039 right-step tile response body; True means B032 tail used."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    s.bx = s.dx & 0xFFFF
    _sub_reg16(cpu, 3, 0x000D)  # SUB BX,000Dh
    if _b00d_tile_is_blocking(cpu, 0xB044):
        _jump_object_tile_sweep_blocked_b032(cpu)
        return True
    _test_word(cpu, mem.rw(ss, (bp + OFF_Y) & 0xFFFF), 0x000F)
    if not cpu.get_flag(ZF):
        _inc_reg16_preserve_cf(cpu, 3)
        if _b00d_tile_is_blocking(cpu, 0xB051):
            _jump_object_tile_sweep_blocked_b032(cpu)
            return True

    _inc_mem_word_preserve_cf(cpu, ss, (bp + OFF_X) & 0xFFFF)
    _inc_mem_word_preserve_cf(cpu, ds, 0xA438)
    saved_bx = s.bx & 0xFFFF
    cpu.push(saved_bx)
    _call_player_hazard_scan_bdd0(cpu, 0xB05E)
    s.bx = cpu.pop()
    if cpu.get_flag(CF):
        _dec_mem_word_preserve_cf(cpu, ss, (bp + OFF_X) & 0xFFFF)
        _dec_mem_word_preserve_cf(cpu, ds, 0xA438)
        _jump_object_tile_sweep_blocked_b032(cpu)
        return True

    _inc_mem_word_preserve_cf(cpu, ds, 0x215A)
    _and_mem_word(cpu, ds, 0x215A, 0x000F)
    if cpu.get_flag(ZF):
        _sub_reg16(cpu, 2, 0x000D)  # SUB DX,000Dh
    return False


def _run_b00d_move_left(cpu) -> bool:
    """Run the B07D/B07A left-step tile response body; True means B032 tail used."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    s.bx = s.dx & 0xFFFF
    _test_word(cpu, mem.rw(ds, 0x215A), 0x000F)
    if cpu.get_flag(ZF):
        _add_reg16(cpu, 3, 0x000D)
        if _b00d_tile_is_blocking(cpu, 0xB08D):
            _jump_object_tile_sweep_blocked_b032(cpu)
            return True
        _test_word(cpu, mem.rw(ss, (bp + OFF_Y) & 0xFFFF), 0x000F)
        if not cpu.get_flag(ZF):
            _inc_reg16_preserve_cf(cpu, 3)
            if _b00d_tile_is_blocking(cpu, 0xB09A):
                _jump_object_tile_sweep_blocked_b032(cpu)
                return True

    _dec_mem_word_preserve_cf(cpu, ss, (bp + OFF_X) & 0xFFFF)
    _dec_mem_word_preserve_cf(cpu, ds, 0xA438)
    saved_bx = s.bx & 0xFFFF
    cpu.push(saved_bx)
    _call_player_hazard_scan_bdd0(cpu, 0xB0A7)
    s.bx = cpu.pop()
    if cpu.get_flag(CF):
        _inc_mem_word_preserve_cf(cpu, ss, (bp + OFF_X) & 0xFFFF)
        _inc_mem_word_preserve_cf(cpu, ds, 0xA438)
        _jump_object_tile_sweep_blocked_b032(cpu)
        return True

    _dec_mem_word_preserve_cf(cpu, ds, 0x215A)
    _and_mem_word(cpu, ds, 0x215A, 0x000F)
    _cmp_word(cpu, mem.rw(ds, 0x215A), 0x000F)
    if cpu.get_flag(ZF):
        _add_reg16(cpu, 2, 0x000D)  # ADD DX,000Dh
    return False


def _run_b00d_move_down(cpu) -> bool:
    """Run the B0CC downward tile response body; True means B032 tail used."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    s.bx = s.dx & 0xFFFF
    _inc_reg16_preserve_cf(cpu, 3)
    if _b00d_tile_is_blocking(cpu, 0xB0D2):
        _jump_object_tile_sweep_blocked_b032(cpu)
        return True
    _test_word(cpu, mem.rw(ds, 0x215A), 0x000F)
    if not cpu.get_flag(ZF):
        _sub_reg16(cpu, 3, 0x000D)
        if _b00d_tile_is_blocking(cpu, 0xB0E5):
            _jump_object_tile_sweep_blocked_b032(cpu)
            return True

    _inc_mem_word_preserve_cf(cpu, ss, (bp + OFF_Y) & 0xFFFF)
    _inc_mem_word_preserve_cf(cpu, ds, 0xA436)
    saved_bx = s.bx & 0xFFFF
    cpu.push(saved_bx)
    _call_player_hazard_scan_bdd0(cpu, 0xB0F5)
    s.bx = cpu.pop()
    if cpu.get_flag(CF):
        _dec_mem_word_preserve_cf(cpu, ss, (bp + OFF_Y) & 0xFFFF)
        _dec_mem_word_preserve_cf(cpu, ds, 0xA436)
        _jump_object_tile_sweep_blocked_b032(cpu)
        return True

    _test_word(cpu, mem.rw(ss, (bp + OFF_Y) & 0xFFFF), 0x000F)
    if cpu.get_flag(ZF):
        _inc_reg16_preserve_cf(cpu, 2)  # INC DX
    return False


def _run_b00d_move_up(cpu) -> bool:
    """Run the B10F upward tile response body; True means B032 tail used."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    s.bx = s.dx & 0xFFFF
    _test_word(cpu, mem.rw(ss, (bp + OFF_Y) & 0xFFFF), 0x000F)
    if cpu.get_flag(ZF):
        _dec_reg16_preserve_cf(cpu, 3)
        if _b00d_tile_is_blocking(cpu, 0xB11C):
            _jump_object_tile_sweep_blocked_b032(cpu)
            return True
        _test_word(cpu, mem.rw(ds, 0x215A), 0x000F)
        if not cpu.get_flag(ZF):
            _sub_reg16(cpu, 3, 0x000D)
            if _b00d_tile_is_blocking(cpu, 0xB12F):
                _jump_object_tile_sweep_blocked_b032(cpu)
                return True

    _dec_mem_word_preserve_cf(cpu, ss, (bp + OFF_Y) & 0xFFFF)
    _dec_mem_word_preserve_cf(cpu, ds, 0xA436)
    saved_bx = s.bx & 0xFFFF
    cpu.push(saved_bx)
    _call_player_hazard_scan_bdd0(cpu, 0xB13F)
    s.bx = cpu.pop()
    if cpu.get_flag(CF):
        _inc_mem_word_preserve_cf(cpu, ss, (bp + OFF_Y) & 0xFFFF)
        _inc_mem_word_preserve_cf(cpu, ds, 0xA436)
        _jump_object_tile_sweep_blocked_b032(cpu)
        return True

    s.ax = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    s.ax &= 0x000F
    cpu.set_logic_flags(s.ax, 16)  # AND AX,000Fh
    _cmp_word(cpu, s.ax, 0x000F)
    if cpu.get_flag(ZF):
        _dec_reg16_preserve_cf(cpu, 2)  # DEC DX
    return False





def run_object_tile_sweep_dispatch_b00d(cpu, self_disable_if_patched) -> None:
    """Lift 1010:B00D, the direction-specific object tile sweep dispatcher.

    AFD8 prepares the A430/A432/A434/A436/A438 scratch rectangle, then calls
    this routine.  B00D converts the object point to a tile-map index through
    5073, dispatches by ``SS:[BP+06]`` into the eight recovered movement
    directions, probes blocking tiles via 505B, checks object hazards via BDD0,
    and either returns normally or tail-jumps into the B032 blocked sentinel.
    """
    if self_disable_if_patched(cpu, 0xB00D, SIG_OBJECT_TILE_SWEEP_DISPATCH_B00D, "overkill_object_tile_sweep_dispatch_b00d"):
        return

    s = cpu.s
    mem = cpu.mem
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    _call_tile_probe_5073(cpu, 0xB010)
    _cmp_word(cpu, s.bx, 0xFFFF)
    if s.bx == 0xFFFF:
        _jump_object_tile_sweep_blocked_b032(cpu)
        return

    s.dx = s.bx & 0xFFFF
    direction = mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF) & 0xFFFF
    if direction > 7:
        _raise_unverified_path(
            cpu,
            parent="1010:B00D",
            chain=f"B00D direction dispatch direction={direction:04X}",
            bp=bp,
        )

    component_handlers = {
        "left": _run_b00d_move_left,
        "down": _run_b00d_move_down,
        "right": _run_b00d_move_right,
        "up": _run_b00d_move_up,
    }
    component_entries = {
        "left": 0xB07D,
        "down": 0xB0CC,
        "right": 0xB03C,
        "up": 0xB10F,
    }
    plan = tile_sweep_plan_for_direction(direction)
    blocked = False
    for idx, component in enumerate(plan.components):
        handler = component_handlers[component]
        if idx + 1 < len(plan.components):
            next_component = plan.components[idx + 1]
            _call_b00d_component(cpu, handler, component_entries[next_component])
        else:
            blocked = handler(cpu)

    if not blocked:
        s.ip = cpu.pop()








def run_object_player_chase_b1b0(cpu, self_disable_if_patched) -> None:
    """Lift B1B0, a player/view-centered chase + target-acquisition behavior.

    This closes the hot B1B0-B1F3 interpreted cluster from the gameplay demo.
    The behavior has two phases: while unacquired it snaps itself and the
    view-centered target to a 4px grid, runs the recovered 5DB2 seeker, and only
    scans for a chase target when movement reports blocked.  Once acquired it
    steers toward the stored target slot through the existing 5E1B/5E42 helpers.
    """
    if self_disable_if_patched(cpu, 0xB1B0, SIG_OBJECT_PLAYER_CHASE_B1B0, "overkill_object_player_chase_b1b0"):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    def jump_ad60() -> None:
        _run_object_bounds_tile_tail_ad60(
            cpu,
            parent="1010:B1B0",
            chain="B1B0 -> AD60",
            cx_value=s.cx & 0xFFFF,
            add_a278_to_x=False,
        )

    def jump_ad5a() -> None:
        _run_object_bounds_tile_tail_ad60(
            cpu,
            parent="1010:B1B0",
            chain="B1B0 -> AD5A",
            cx_value=s.cx & 0xFFFF,
            add_a278_to_x=True,
        )

    s.ax = mem.rw(ds, 0x2328)
    _add_reg16(cpu, 0, 0x006D)
    mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, s.ax)

    acquired = mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    _cmp_word(cpu, acquired, 0x0001)
    if acquired != 0x0001:
        # B1BF: view/player center target -> 5DB2 globals, all aligned to 4px.
        run_player_center_target_setup_b1bf(cpu)

        def run_5db2(c):
            _run_movement_direction_5db2(c)
            c.s.ip = c.pop()

        _call_verified_child_near(cpu, 0x5DB2, run_5db2, 0xB1EC)
        if (s.ip & 0xFFFF) != 0xB1EC:
            raise RuntimeError(f"B1B0 expected 5DB2 to return to B1EC, got {s.ip:04X}")
        _cmp_word(cpu, mem.rw(ds, MOVEMENT_BLOCKED_FLAG), 0)
        if mem.rw(ds, MOVEMENT_BLOCKED_FLAG) == 0:
            jump_ad60()
            return

        _cmp_word(cpu, mem.rw(ds, 0xA97E), 0)
        if mem.rw(ds, 0xA97E) != 0:
            _dec_mem_word_preserve_cf(cpu, ds, 0xA97E)
        # CALL B15A leaves B204 as freed stack scratch; route it through the
        # real hook boundary so the shared scan stays independently verifiable.
        _call_verified_child_near(
            cpu,
            0xB15A,
            lambda c: run_player_chase_candidate_scan_b15a(c, _no_patch_guard),
            0xB204,
        )
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (0x1010, 0xB204):
            raise RuntimeError(
                f"B1B0 expected B15A to return to B204, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )
        _cmp_word(cpu, s.bx & 0xFFFF, 0xFFFF)
        if (s.bx & 0xFFFF) == 0xFFFF:
            _run_original_tail_to_caller(cpu, 0xADC9)
            return
        mem.ww(ss, (bp + 0x30) & 0xFFFF, s.bx & 0xFFFF)
        mem.ww(ss, (bp + OFF_SUBSTATE) & 0xFFFF, 0x0001)
        _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
        if mem.rb(ds, 0x98C0) != 0:
            mem.wb(ds, 0xBEFF, 0x11)
        _inc_mem_word_preserve_cf(cpu, ds, 0xA97E)
        jump_ad60()
        return

    # B227: already acquired; validate stored target slot and steer toward it.
    s.bx = mem.rw(ss, (bp + 0x30) & 0xFFFF)
    target_bx = s.bx & 0xFFFF
    target_slot = ObjectSlotView.from_ds(cpu, target_bx)
    if not run_player_chase_acquired_target_validity_b1b0(cpu, target_slot):
        mem.ww(ss, (bp + OFF_SUBSTATE) & 0xFFFF, 0x0000)
        jump_ad5a()
        return

    mem.ww(ss, (s.sp - 2) & 0xFFFF, 0xB23F)
    _run_object_delta_helper_5e1b(cpu)
    cpu.push(0xB242)
    run_runtime_patched_object_steer_5e42(cpu)
    if (s.ip & 0xFFFF) != 0xB242:
        raise RuntimeError(f"B1B0 expected 5E42 to return to B242, got {s.ip:04X}")
    jump_ad5a()


