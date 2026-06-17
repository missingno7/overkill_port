"""Address-bound wrappers for recovered OVERKILL gameplay frontiers.

This module owns small CS:IP registration adapters for gameplay/frontier hooks.
The actual behavior remains in :mod:`overkill.gameplay.*`; wrappers here only
preserve hook names, live-code guards, and ASM-visible call-boundary adapters.
Keeping these out of ``overkill.hooks`` prevents the aggregate registration
surface from mixing recovered gameplay logic with rendering/input glue.
"""

from __future__ import annotations

from dos_re.hooks import registry
from ..gameplay.collision import (
    run_collision_clc_ret_835b,
    run_collision_stc_ret_5059,
    run_object_tile_sweep_blocked_b032,
    run_player_hazard_object_scan_bde3,
    run_player_hazard_scan_guard_bdd0,
    run_tile_contact_probe_4ff9,
    run_tile_lookup_505b,
    run_tile_probe_5073,
    run_view_contact_rect_test_8331,
)
from ..gameplay.action_spawns import (
    run_frame_action_dual_anchor_spawn_a584,
    run_frame_action_linked_anchor_spawn_a515,
    run_frame_action_listed_anchor_spawn_a2a0,
    run_frame_action_mirrored_anchor_spawn_a3ff,
    run_frame_action_pair_spawn_a2f6,
    run_frame_action_pair_spawn_a337,
    run_frame_action_side_anchor_spawn_a3ca,
    run_frame_action_spawn_fanout_a067,
)
from ..gameplay.game_state import (
    run_demo_counter_tick_1f8f_081d,
    run_gameplay_counter_stride_loop_1f8f_0960,
    run_gameplay_counter_tick_1f8f_0922,
)
from ..gameplay.object_runtime import (
    _run_interpreted_near_call_observed,
    run_movement_dir_double_step_2px_af60,
    run_movement_dir_step_2px_af63,
    run_object_bottom_scroll_offset_decay_a63c,
    run_object_scroll_backward_row_a7d0,
    run_object_scroll_backward_step_a781,
    run_object_scroll_forward_row_a74e,
    run_object_scroll_forward_step_a6fe,
    run_object_scroll_row_wrap_backward_a7e3,
    run_object_scroll_row_wrap_forward_a746,
    run_object_scroll_world_progress_gate_a66f,
    run_object_tile_sweep_dispatch_b00d,
    run_object_tile_sweep_probe_afd8,
    run_object_top_scroll_edge_response_a648,
    run_object_top_scroll_offset_recover_a662,
    run_object_vertical_scroll_edge_response_a616,
)
from .common import self_disable_if_patched


@registry.replace(0x1010, 0xB032, "overkill_object_tile_sweep_blocked_b032")
def overkill_object_tile_sweep_blocked_b032(cpu):
    """Hook wrapper for OVERKILL 1010:B032 tile-sweep blocked sentinel."""
    run_object_tile_sweep_blocked_b032(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xBDE3, "overkill_player_hazard_object_scan_bde3")
def overkill_player_hazard_object_scan_bde3(cpu):
    """Hook wrapper for OVERKILL 1010:BDE3 player/hazard scan."""
    run_player_hazard_object_scan_bde3(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xBDD0, "overkill_player_hazard_scan_guard_bdd0")
def overkill_player_hazard_scan_guard_bdd0(cpu):
    """Hook wrapper for OVERKILL 1010:BDD0 player/hazard scan guard."""
    run_player_hazard_scan_guard_bdd0(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0x8331, "overkill_view_contact_rect_test_8331")
def overkill_view_contact_rect_test_8331(cpu):
    """Hook wrapper for OVERKILL 1010:8331 view/contact rectangle test."""
    run_view_contact_rect_test_8331(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0x835B, "overkill_collision_clc_ret_835b")
def overkill_collision_clc_ret_835b(cpu):
    """Hook wrapper for OVERKILL 1010:835B CLC/RET collision miss tail."""
    run_collision_clc_ret_835b(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0x5059, "overkill_collision_stc_ret_5059")
def overkill_collision_stc_ret_5059(cpu):
    """Hook wrapper for OVERKILL 1010:5059 STC/RET collision-hit helper."""
    run_collision_stc_ret_5059(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0x505B, "overkill_tile_lookup_505b")
def overkill_tile_lookup_505b(cpu):
    """Hook wrapper for OVERKILL 1010:505B tile lookup helper."""
    run_tile_lookup_505b(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0x4FF9, "overkill_tile_contact_probe_4ff9")
def overkill_tile_contact_probe_4ff9(cpu):
    """Hook wrapper for OVERKILL 1010:4FF9 tile/contact probe helper."""
    run_tile_contact_probe_4ff9(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0x5073, "overkill_tile_probe_5073")
def overkill_tile_probe_5073(cpu):
    """Hook wrapper for OVERKILL 1010:5073 coordinate-to-tile probe helper."""
    run_tile_probe_5073(cpu, self_disable_if_patched)


@registry.replace(0x1F8F, 0x081D, "overkill_demo_counter_tick_1f8f_081d")
def overkill_demo_counter_tick_1f8f_081d(cpu):
    """Hook wrapper for the far demo/attract counter tick at 1F8F:081D."""
    run_demo_counter_tick_1f8f_081d(cpu, self_disable_if_patched)


@registry.replace(0x1F8F, 0x0922, "overkill_gameplay_counter_tick_1f8f_0922")
def overkill_gameplay_counter_tick_1f8f_0922(cpu):
    """Hook wrapper for the per-frame far counter tick at 1F8F:0922."""
    run_gameplay_counter_tick_1f8f_0922(cpu, self_disable_if_patched)


@registry.replace(0x1F8F, 0x0960, "overkill_gameplay_counter_stride_loop_1f8f_0960")
def overkill_gameplay_counter_stride_loop_1f8f_0960(cpu):
    """Hook wrapper for OVERKILL 1F8F:0960 gameplay counter stride loop."""
    run_gameplay_counter_stride_loop_1f8f_0960(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xAF60, "overkill_movement_dir_double_step_2px_af60")
def overkill_movement_dir_double_step_2px_af60(cpu):
    """Self-call double 2-pixel movement step (entry for direct calls)."""
    run_movement_dir_double_step_2px_af60(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xAF63, "overkill_movement_dir_step_2px_af63")
def overkill_movement_dir_step_2px_af63(cpu):
    """8-direction movement step table, 2-pixel delta (entry for direct calls)."""
    run_movement_dir_step_2px_af63(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA616, "overkill_object_vertical_scroll_edge_response_a616")
def overkill_object_vertical_scroll_edge_response_a616(cpu):
    """Raw vertical edge-scroll response around top/bottom scroll-bias globals."""
    run_object_vertical_scroll_edge_response_a616(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA63C, "overkill_object_bottom_scroll_offset_decay_a63c")
def overkill_object_bottom_scroll_offset_decay_a63c(cpu):
    """Decay DS:A39C bottom-edge scroll bias toward zero."""
    run_object_bottom_scroll_offset_decay_a63c(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA648, "overkill_object_top_scroll_edge_response_a648")
def overkill_object_top_scroll_edge_response_a648(cpu):
    """Top-edge input scroll bias/recovery helper."""
    run_object_top_scroll_edge_response_a648(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA662, "overkill_object_top_scroll_offset_recover_a662")
def overkill_object_top_scroll_offset_recover_a662(cpu):
    """Recover DS:A39A top-edge scroll bias toward zero."""
    run_object_top_scroll_offset_recover_a662(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xB00D, "overkill_object_tile_sweep_dispatch_b00d")
def overkill_object_tile_sweep_dispatch_b00d(cpu):
    """Recovered direction-specific object tile-sweep dispatcher at 1010:B00D."""
    run_object_tile_sweep_dispatch_b00d(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xAFD8, "overkill_object_tile_sweep_probe_afd8")
def overkill_object_tile_sweep_probe_afd8(cpu):
    """Shared object tile-sweep probe wrapper around B00D."""
    run_object_tile_sweep_probe_afd8(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA067, "overkill_frame_action_spawn_fanout_a067")
def overkill_frame_action_spawn_fanout_a067(cpu):
    """Frame input-bit gated action/object-spawn fanout exposed by 9B2E/D04D."""
    run_frame_action_spawn_fanout_a067(cpu, self_disable_if_patched, _run_interpreted_near_call_observed)


@registry.replace(0x1010, 0xA515, "overkill_frame_action_linked_anchor_spawn_a515")
def overkill_frame_action_linked_anchor_spawn_a515(cpu):
    """Gated raw anchored-slot spawn child behind A067."""
    run_frame_action_linked_anchor_spawn_a515(cpu, self_disable_if_patched, _run_interpreted_near_call_observed)


@registry.replace(0x1010, 0xA584, "overkill_frame_action_dual_anchor_spawn_a584")
def overkill_frame_action_dual_anchor_spawn_a584(cpu):
    """Gated two-slot anchored spawn child behind A067."""
    run_frame_action_dual_anchor_spawn_a584(cpu, self_disable_if_patched, _run_interpreted_near_call_observed)


@registry.replace(0x1010, 0xA3CA, "overkill_frame_action_side_anchor_spawn_a3ca")
def overkill_frame_action_side_anchor_spawn_a3ca(cpu):
    """Four-source raw side-anchor spawn dispatcher behind A067."""
    run_frame_action_side_anchor_spawn_a3ca(cpu, self_disable_if_patched, _run_interpreted_near_call_observed)


@registry.replace(0x1010, 0xA3FF, "overkill_frame_action_mirrored_anchor_spawn_a3ff")
def overkill_frame_action_mirrored_anchor_spawn_a3ff(cpu):
    """Two-source mirrored raw anchor spawn dispatcher behind A067."""
    run_frame_action_mirrored_anchor_spawn_a3ff(cpu, self_disable_if_patched, _run_interpreted_near_call_observed)


@registry.replace(0x1010, 0xA2A0, "overkill_frame_action_listed_anchor_spawn_a2a0")
def overkill_frame_action_listed_anchor_spawn_a2a0(cpu):
    """Raw listed two-slot action-spawn child behind A067/A0E8."""
    run_frame_action_listed_anchor_spawn_a2a0(cpu, self_disable_if_patched, _run_interpreted_near_call_observed)


@registry.replace(0x1010, 0xA2F6, "overkill_frame_action_pair_spawn_a2f6")
def overkill_frame_action_pair_spawn_a2f6(cpu):
    """Raw two-slot action-spawn table tail behind A067/A0E8."""
    run_frame_action_pair_spawn_a2f6(cpu, self_disable_if_patched, _run_interpreted_near_call_observed)


@registry.replace(0x1010, 0xA337, "overkill_frame_action_pair_spawn_a337")
def overkill_frame_action_pair_spawn_a337(cpu):
    """Sibling raw two-slot action-spawn table tail behind A067/A0E8."""
    run_frame_action_pair_spawn_a337(cpu, self_disable_if_patched, _run_interpreted_near_call_observed)


@registry.replace(0x1010, 0xA66F, "overkill_object_scroll_world_progress_gate_a66f")
def overkill_object_scroll_world_progress_gate_a66f(cpu):
    """Vertical scroll/world-progress gate around A6FE."""
    run_object_scroll_world_progress_gate_a66f(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA746, "overkill_object_scroll_row_wrap_forward_a746")
def overkill_object_scroll_row_wrap_forward_a746(cpu):
    """Wrap the forward scroll source row pointer."""
    run_object_scroll_row_wrap_forward_a746(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA7E3, "overkill_object_scroll_row_wrap_backward_a7e3")
def overkill_object_scroll_row_wrap_backward_a7e3(cpu):
    """Wrap the backward scroll source row pointer."""
    run_object_scroll_row_wrap_backward_a7e3(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA74E, "overkill_object_scroll_forward_row_a74e")
def overkill_object_scroll_forward_row_a74e(cpu):
    """Forward map/scroll-row advance bookkeeping around A7EB."""
    run_object_scroll_forward_row_a74e(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA7D0, "overkill_object_scroll_backward_row_a7d0")
def overkill_object_scroll_backward_row_a7d0(cpu):
    """Backward map/scroll-row advance bookkeeping around A7EB."""
    run_object_scroll_backward_row_a7d0(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA6FE, "overkill_object_scroll_forward_step_a6fe")
def overkill_object_scroll_forward_step_a6fe(cpu):
    """Forward vertical-scroll bookkeeping step."""
    run_object_scroll_forward_step_a6fe(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0xA781, "overkill_object_scroll_backward_step_a781")
def overkill_object_scroll_backward_step_a781(cpu):
    """Backward vertical-scroll bookkeeping step."""
    run_object_scroll_backward_step_a781(cpu, self_disable_if_patched)

__all__ = [name for name in globals() if name.startswith("overkill_")]
