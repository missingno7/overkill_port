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
    run_collision_stc_ret_5059,
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
from overkill.gameplay.object_bounds import (
    SIG_OBJECT_BOUNDS_TILE_PRELUDE_AD5A,
    _run_object_bounds_tile_tail_ad60,
    run_object_bounds_tile_prelude_ad5a,
    _run_tile_probe_5073,
    _run_tile_lookup_505b,
)
from overkill.gameplay.object_behaviors import (
    _call_ab34,
    _call_ab4f,
    _call_ac28,
    _call_ac81,
    _run_object_behavior_b73e,
    _run_b250_overlap_contact_selector,
    _run_object_behavior_b24d,
    _run_object_behavior_b86d,
    _run_object_behavior_b9f0,
    _run_object_family_dispatch_efae,
    _run_object_behavior_ab77,
    _run_tracked_object_selector_to_ab77,
    _run_object_sprite0f_collision_abca,
    _run_object_logic_branch_ad04,
    _run_object_behavior_aba3,
    _run_object_behavior_ae09,
    _run_object_behavior_8d4f,
    _run_object_behavior_aed8,
    _run_object_logic_ab10,
    _run_object_logic_dispatch_aa2b,
    _scan_object_logic_via_aa2b,
)
from overkill.gameplay.object_runtime_common import (
    _object_ptr_from_scan_index,
    _push_loop_count_for_interpreted_tail,
)
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
    run_object_spawn_seed_8209,
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
    OFF_X,
    OFF_Y,
    ObjectSlotView,
)
from overkill.runtime_code import require_runtime_code_variant


















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
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    mem.ww(ds, 0xA430, 0x0000)
    s.ax = slot.x_word
    mem.ww(ds, 0xA432, s.ax)
    mem.ww(ds, 0xA438, s.ax)
    s.ax = slot.y_word
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












































def _finish_ae2c_common(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem
    slot = ObjectSlotView(mem, ss, bp)  # this object's record (SS:BP)

    slot.direction_or_step = 0x0001
    _add_mem_word(cpu, ss, (bp + OFF_Y) & 0xFFFF, 4)
    cpu.s.ax = mem.rw(ds, 0x2326)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax &= 0x0008
    cpu.set_logic_flags(cpu.s.ax, 16)
    _add_reg16(cpu, 0, slot.direction_or_step)
    _add_reg16(cpu, 0, 0x0008)
    slot.sprite_or_state = cpu.s.ax
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
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    y = slot.y_word
    _cmp_word(cpu, y, 0x00C8)
    if y == 0x00C8:
        _run_original_tail_to_caller(cpu, 0xADC9)
        return

    _sub_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 4)
    y = slot.y_word
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
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    y = slot.y_word
    _cmp_word(cpu, y, 0)
    if y == 0:
        _run_original_tail_to_caller(cpu, 0xADC9)
        return

    _sub_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 4)
    y = slot.y_word
    _test_word(cpu, y, 0x000F)
    if (y & 0x000F) == 0:
        _run_original_tail_to_caller(cpu, 0xAE91)
        return

    slot.direction_or_step = 0x0007
    _sub_mem_word(cpu, ss, (bp + OFF_Y) & 0xFFFF, 4)
    cpu.s.ax = slot.direction_or_step
    _add_reg16(cpu, 0, 0x0008)
    slot.sprite_or_state = cpu.s.ax
    _run_object_bounds_tile_tail_ad60(
        cpu, parent="1010:AE7D", chain="AE7D -> AD5A", cx_value=cpu.s.cx & 0xFFFF, add_a278_to_x=True
    )





















































def _call_tile_probe_5073(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0x5073, lambda c: run_tile_probe_5073(c, _no_patch_guard), return_ip)




def _call_player_hazard_scan_bdd0(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xBDD0, lambda c: run_player_hazard_scan_guard_bdd0(c, _no_patch_guard), return_ip)
    # On a hazard hit, BDD0 lands on the 1010:5059 STC;RET stub (the original
    # JMP 5059) instead of collapsing it, so the near-CALL frame this wrapper
    # pushed is still on the stack.  Run that stub here to set carry and pop back
    # to return_ip, exactly as the VM would when 5059 is reached at top level.
    if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) == (0x1010, 0x5059):
        run_collision_stc_ret_5059(cpu, _no_patch_guard)


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
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    s.bx = s.dx & 0xFFFF
    _sub_reg16(cpu, 3, 0x000D)  # SUB BX,000Dh
    if _b00d_tile_is_blocking(cpu, 0xB044):
        _jump_object_tile_sweep_blocked_b032(cpu)
        return True
    _test_word(cpu, slot.y_word, 0x000F)
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
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    s.bx = s.dx & 0xFFFF
    _test_word(cpu, mem.rw(ds, 0x215A), 0x000F)
    if cpu.get_flag(ZF):
        _add_reg16(cpu, 3, 0x000D)
        if _b00d_tile_is_blocking(cpu, 0xB08D):
            _jump_object_tile_sweep_blocked_b032(cpu)
            return True
        _test_word(cpu, slot.y_word, 0x000F)
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
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

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

    _test_word(cpu, slot.y_word, 0x000F)
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
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    s.bx = s.dx & 0xFFFF
    _test_word(cpu, slot.y_word, 0x000F)
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

    s.ax = slot.y_word
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
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    _call_tile_probe_5073(cpu, 0xB010)
    _cmp_word(cpu, s.bx, 0xFFFF)
    if s.bx == 0xFFFF:
        _jump_object_tile_sweep_blocked_b032(cpu)
        return

    s.dx = s.bx & 0xFFFF
    direction = slot.direction_or_step & 0xFFFF
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

    slot = ObjectSlotView(mem, ss, bp)  # this object's record (SS:BP)
    s.ax = mem.rw(ds, 0x2328)
    _add_reg16(cpu, 0, 0x006D)
    slot.sprite_or_state = s.ax

    acquired = slot.substate
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
        slot.acquired_target_ptr = s.bx & 0xFFFF
        slot.substate = 0x0001
        _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
        if mem.rb(ds, 0x98C0) != 0:
            mem.wb(ds, 0xBEFF, 0x11)
        _inc_mem_word_preserve_cf(cpu, ds, 0xA97E)
        jump_ad60()
        return

    # B227: already acquired; validate stored target slot and steer toward it.
    s.bx = slot.acquired_target_ptr
    target_bx = s.bx & 0xFFFF
    target_slot = ObjectSlotView.from_ds(cpu, target_bx)
    if not run_player_chase_acquired_target_validity_b1b0(cpu, target_slot):
        slot.substate = 0x0000
        jump_ad5a()
        return

    _run_object_delta_helper_5e1b(cpu)
    cpu.push(0xB242)
    run_runtime_patched_object_steer_5e42(cpu)
    if (s.ip & 0xFFFF) != 0xB242:
        raise RuntimeError(f"B1B0 expected 5E42 to return to B242, got {s.ip:04X}")
    jump_ad5a()


