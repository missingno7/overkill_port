"""Aggregate hook-registration surface for OVERKILL replacements.

Importing this module registers every known hook.  Address-bound wrapper modules
should live under ``overkill.hook_wrappers`` when they are stable enough to
leave this staging file.  Keep actual game logic in the domain modules
(``asset_codecs``, ``rendering``, ``gameplay``, ``sounds``).
"""

from __future__ import annotations

import os

from dos_re.cpu import CF, DF, PF, SF, ZF, _PARITY
from dos_re.hooks import registry
from .hook_wrappers.common import (
    call_hook_like_near_call as _call_hook_like_near_call,
    call_installed_hook_like_near_call as _call_installed_hook_like_near_call,
    code_matches as _code_matches,
    interpret_current_instruction_without_hook as _interpret_current_instruction_without_hook,
    jump_installed_hook_boundary as _jump_installed_hook_boundary,
    self_disable_if_patched as _self_disable_if_patched,
)
from .hook_wrappers.asset_codecs import *  # noqa: F401,F403 - register/re-export address wrappers
from .hook_wrappers.text import *  # noqa: F401,F403 - register/re-export address wrappers
from .bootstrap_lzexe import (
    SIG_LZEXE_MAIN_LOOP_0069,
    run_lzexe_bootstrap_main_loop_0069,
)
from .hook_wrappers.sounds import *  # noqa: F401,F403 - register/re-export address wrappers
from .hook_wrappers.gameplay_frontiers import *  # noqa: F401,F403 - register/re-export address wrappers
from .hook_wrappers.object_runtime_frontiers import *  # noqa: F401,F403 - register/re-export address wrappers
from .rendering.ega import (
    run_ega_compact_byte_masked_composite_2193,
    run_ega_compact_byte_spread_composite_21d6,
    run_ega_compact_byte_spread_composite_2223,
    run_ega_compact_byte_spread_composite_2285,
    run_ega_compact_byte_spread_composite_22fc,
    run_ega_compact_byte_spread_left_composite_238d,
    run_ega_compact_byte_spread_left_composite_2410,
    run_ega_compact_byte_spread_left_composite_247e,
    run_ega_compact_spread_composite_409d,
    run_ega_compact_spread_composite_40d7,
    run_ega_compact_spread_composite_412b,
    run_ega_display_start_wait_5160,
    run_ega_expand_temp_rows_2824,
    run_ega_layer_masked_composite_103c,
    run_ega_layer_or_inverted_composite_10b7,
    run_ega_load_temp_rows_280d,
    run_ega_planar_to_linear_copy_5827,
    run_ega_row_driver_27eb,
    run_ega_source_spaced_copy_2ab9,
    run_ega_spaced_copy_29c6,
    run_ega_spaced_word_composite_1aeb,
    run_ega_spread_masked_composite_1d1b,
    run_ega_spread_masked_composite_wide_13e7,
    run_ega_temp_row_copy_291c,
    run_ega_transparency_mask_2932,
    run_present_ega_frame_2750,
)


from dos_re.memory import EGA_CPU_APERTURE, EGA_APERTURE, EGA_PLANE_STRIDE, EGA_PLANE_WINDOW
from .input_menu import (
    pack_keyboard_poll_bits_017e,
    run_input_selector_loop_d445,
    run_menu_fire_release_wait_d390,
    run_selector_input_release_wait_d434,
    run_main_menu_idle_loop_558b,
    run_input_poll_0162,
    run_input_release_wait_gate_986e,
    run_yes_no_choice_wait_gate_989e,
    run_sound_effect_completion_wait_gate_98d8,
    run_boss_key_f9_release_wait_gate_07c4,
    run_boss_key_any_key_wait_gate_07d0,
    run_boss_key_return_key_release_wait_gate_07d7,
    run_keyboard_state_clear_and_bios_tail_sync_50ab,
    run_bios_keyboard_buffer_tail_sync_50ba,
    run_temp_keyboard_vector_install_4e9f,
    run_temp_keyboard_vector_restore_4ebf,
    run_text_prompt_key_read_5497,
    run_text_entry_prompt_loop_53c9,
    run_intro_retrace_delay_loop_96c5,
    run_intro_retrace_delay_loop_tail_96c8,
)

from .rendering.coordinates import (
    coordinate_ax_to_di_5a00,
    coordinate_ax_to_di_5a24,
    object_row_address_from_mode_dispatch_5a36,
    object_row_address_mode1_2580,
)
from .rendering.layer_sprites import (
    LayerSpriteRuntime,
    call_draw_dispatch_from_scan_a858,
    call_layer0_draw_type_from_scan_a8be,
    call_layer1_draw_type_from_scan_a8f1,
    call_present_dispatch_from_scan_a936,
    call_clear_presence_list_parent_a93c,
    dispatch_draw_object_5ac8,
    dispatch_layer_draw_type_7596,
    dispatch_menu_cell_source_blit_5a6c,
    dispatch_present_object_5a92,
    run_clear_presence_list_parent_4d64,
    run_presence_stamp_triplet_4ced,
    run_present_object_scan_pair_a90c,
    run_video_page_toggle_511f,
    draw_compact_layer_sprite_7746,
    finish_draw_scan_tail_a85b,
    finish_layer0_scan_tail_a8c1,
    finish_layer1_scan_tail_a8f4,
    finish_present_scan_tail_a939,
    draw_layer_sprite_75a6,
    draw_layer_sprite_768e,
)

from .rendering.tandy import (
    build_startup_coordinate_tables_0f0b as run_tandy_startup_coordinate_tables_0f0b,
    build_video_offset_tables_0fa3 as run_tandy_video_offset_tables_0fa3,
    clear_tandy_interlaced_buffer_30b0 as run_tandy_interlaced_clear_30b0,
    clear_tandy_interlaced_buffer_3389 as run_tandy_interlaced_clear_3389,
    patched_strided_row_copy_30ba as run_tandy_patched_strided_row_copy_30ba,
    build_pixel_pair_lookup_table_0fe4 as run_tandy_pixel_pair_table_0fe4,
    expand_tandy_cell_33dd as run_expand_tandy_cell_33dd,
    expand_tandy_block_33b2 as run_expand_tandy_block_33b2,
    expand_tandy_list_33af as run_expand_tandy_list_33af,
    TandyRenderRuntime,
    draw_object_block_35cc as run_tandy_draw_object_block_35cc,
    draw_split_object_356c as run_tandy_draw_split_object_356c,
    draw_tiny_object_3657 as run_tandy_draw_tiny_object_3657,
    masked_compact_2fb6 as run_tandy_masked_compact_2fb6,
    masked_sprite_composite_2e6e as run_tandy_masked_sprite_composite_2e6e,
    masked_sprite_composite_2f81 as run_tandy_masked_sprite_composite_2f81,
    or_inverted_mask_2ecb as run_tandy_or_inverted_mask_2ecb,
    or_inverted_mask_2f40 as run_tandy_or_inverted_mask_2f40,
    loading_scroll_sequence_60c5 as run_tandy_loading_scroll_sequence_60c5,
    loading_scroll_until_4e0d as run_tandy_loading_scroll_until_4e0d,
    loading_tile_remap_scan_4e26 as run_tandy_loading_tile_remap_scan_4e26,
    loading_tile_column_copy_36a2 as run_tandy_loading_tile_column_copy_36a2,
    postcopy_scaled_blit_375b as run_tandy_postcopy_scaled_blit_375b,
    full_width_panel_copy_3824 as run_tandy_full_width_panel_copy_3824,
    present_tandy_frame_3354 as run_present_tandy_frame_3354,
    changed_dword_present_8rows_cdaa as run_tandy_changed_dword_present_cdaa,
    copy_rect_to_tandy_video_306f as run_tandy_rect_copy_306f,
    small_strided_copy_34d8 as run_tandy_small_strided_copy_34d8,
    source_strided_copy_35aa as run_tandy_source_strided_copy_35aa,
    split_present_copy_34ad as run_tandy_split_present_copy_34ad,
    sprite_blit_9x16_477e as run_tandy_sprite_blit_9x16_477e,
    linear_rows_to_work_buffer_41da as run_tandy_linear_rows_to_work_buffer_41da,
    strided_copy_34c5 as run_tandy_strided_copy_34c5,
    tiny_strided_copy_3542 as run_tandy_tiny_strided_copy_3542,
)

from .rendering.effects import (
    SIG_FRAME_EFFECT_SLASH_77F6,
    SIG_FRAME_EFFECT_GATE_77C5,
    run_frame_effect_gate_77c5,
    run_frame_effect_slash_77f6,
)

from .gameplay.collision import (
    run_object_deactivate_logic_dispatch_c054,
    run_object_slot_scan_ac97,
    run_object_slot_scan_guard_ac81,
    run_postmove_y_clamp_bcb1,
    run_postmove_contact_window_aa71,
    run_tile_collision_probe_ac28,
    run_frame_contact_probe_fanout_9cb6,
    run_post_contact_status_helper_9e19,
)
from .gameplay.game_state import (
    run_decrement_first_active_counter_61c7,
    run_decrement_first_active_counter_scan_61ca,
    run_decrement_first_active_counter_loop_61f7,
    run_status_display_parent_61dc,
    run_status_counter_cell_blit_6296,
    run_status_cursor_advance_613e,
    run_status_cursor_retreat_615a,
    run_status_row_repeat_6120,
    run_status_cell_quad_composite_859e,
    run_status_cell_composite_85d5,
    run_status_coord_list_fill_99cd,
    run_frame_tracked_coord_store_9cd9,
    run_frame_coord_ring_advance_9cf1,
    run_tracked_object_coord_pull_a031,
    run_frame_axis_count_inc_ah_9bfb,
    run_frame_axis_count_inc_al_9bfe,
    run_frame_axis_condition_dispatch_9c01,
    run_frame_game_state_update_a940,
    run_gameplay_counter_tick_1f8f_0922,
)
from .gameplay.frame_orchestration import (
    run_demo_object_list_maintenance_a212,
    SIG_FRAME_EFFECT_STATUS_TEXT_60A2,
    SIG_FRAME_LOOP_97B2,
    SIG_FRAME_UI_STATE_UPDATE_D04D,
    run_interstitial_status_cell_d367,
    run_interstitial_timed_input_loop_d318,
    run_status_cell_list_seed_8517,
    run_status_cell_seed_852b,
    run_frame_effect_status_text_60a2,
    run_frame_controller_9b2e,
    run_frame_loop_97b2,
    run_transition_status_wait_9908,
    run_transition_input_release_tail_9928,
    run_main_frame_loop_d007,
    run_frame_service_gate_073c,
    run_frame_status_counter_update_5f61,
    run_frame_ui_state_update_d04d,
)
from .gameplay.objects import (
    call_object_logic_from_scan_aa01,
    finish_object_logic_scan_tail_aa04,
    run_object_motion_table_ab34,
    run_object_scroll_sprite_ab4f,
    run_reset_effect_slot_block_c3bf,
    run_reset_object_slot_block_c3f1,
    run_reset_object_slot_block_c4e5,
    run_reset_object_slot_and_status_setup_c4db,
    run_setup_tracked_status_tail_c51d,
)

from .asm import (
    _add_mem_byte,
    _add_mem_word,
    _add_reg16,
    _and_mem_byte,
    _and_mem_word,
    _cmp_byte,
    _cmp_word,
    _dec_mem_byte_preserve_cf,
    _dec_reg16_preserve_cf,
    _inc_reg8_preserve_cf,
    _out_dx_al,
    _out_dx_ax,
    _rep_movsw,
    _ega_aperture_overlap,
    _ega_next_scanline_di,
    _inc_mem_byte_preserve_cf,
    _inc_reg16_preserve_cf,
    _rep_movsb,
    _rep_stosb,
    _sub_mem_word,
    _sub_reg16,
    _test_word,
    _xor_al_al,
)
from .gameplay.object_runtime import (
    _draw_dispatch_target_5ac8,
    _find_free_effect_slot_7524,
    _find_free_object_slot_7573,
    run_object_slot_allocate_or_reclaim_7547,
    run_object_spawn_seed_8209,
    run_object_spawn_seed_a4ea,
    run_object_spawn_seed_from_source_a4d7,
    run_object_spawn_anchor_offset_a571,
    _format_object_context,
    _layer_draw_dispatch_target_7596,
    _object_family_target_efae,
    _object_logic_target_aa2b,
    _object_ptr_from_scan_index,
    _present_dispatch_target_5a92,
    _push_loop_count_for_interpreted_tail,
    _raise_unverified_path,
    _run_object_behavior_aba3,
    _run_aee4_step_for_direction,
    _run_af60_double_step_for_direction,
    _run_af63_step_for_direction,
    run_movement_dir_step_3px_af22,
    run_movement_dir_step_8px_aee4,
    _run_collision_death_tail_bfc7,
    _run_collision_handler_bec5_observed,
    _run_deactivate_bd17_observed,
    _run_formation_spawn_7476_observed,
    _run_interpreted_near_call_observed,
    _run_linked_effect_spawn_7420_observed,
    _run_movement_direction_5db2,
    run_object_target_move_b729,
    run_object_player_chase_b1b0,
    run_player_chase_candidate_scan_b15a,
    SIG_OBJECT_PLAYER_CHASE_B1B0,
    _run_object_bounds_tile_tail_ad60,
    run_object_bounds_tile_prelude_ad5a,
    run_object_target_chase_d281,
    run_object_drift_downright_ae2c,
    run_object_drift_upright_ae7d,
    _run_object_behavior_8d4f,
    _run_object_behavior_ab77,
    _run_object_sprite0f_collision_abca,
    _run_object_behavior_ae09,
    _run_object_behavior_aed8,
    _run_object_behavior_b86d,
    _run_object_behavior_b24d,
    _run_object_behavior_b73e,
    _run_object_behavior_b9f0,
    _run_object_family_dispatch_efae,
    _run_object_logic_ab10,
    _run_object_logic_branch_ad04,
    _run_tracked_object_selector_to_ab77,
    _run_object_logic_dispatch_aa2b,
    _run_object_overlap_scan_62f6,
    _run_object_postmove_bc4b,
    run_linked_object_coord_quad_update_9faf,
    run_object_child_coord_update_9fea,
    run_object_x_step_left_clamp_a5d1,
    run_object_x_step_right_clamp_a5ea,
    run_object_y_step_up_clamp_a5f9,
    run_object_y_step_down_clamp_a607,
    run_runtime_patched_object_steer_5e42,
    run_object_postmove_prelude_bc45,
    _run_post_contact_9e69_observed,
    _run_post_contact_9e98_tail_observed,
    _run_tile_lookup_505b,
    _run_tile_probe_5073,
    _run_view_window_check_aa46,
    _run_y_clamp_bcb1,
    _scan_active_object_call,
    _scan_layered_object_call,
    _scan_loop_until_callable,
    _scan_object_logic_via_aa2b,
)

from .hook_wrappers.runtime_signatures import *  # noqa: F403 - intentional private signature re-export


def _run_bootstrap_lzexe_loop_0069_if_matching(cpu) -> None:
    if not _code_matches(cpu, 0x0069, SIG_LZEXE_MAIN_LOOP_0069):
        _interpret_current_instruction_without_hook(cpu)
        return
    run_lzexe_bootstrap_main_loop_0069(cpu)


@registry.replace(0x1B65, 0x0069, "overkill_bootstrap_lzexe_main_loop_1b65_0069")
def overkill_bootstrap_lzexe_main_loop_1b65_0069(cpu):
    """Lift hot LZEXE bootstrap bitstream loop in temporary segment 1B65."""
    _run_bootstrap_lzexe_loop_0069_if_matching(cpu)


@registry.replace(0x1C43, 0x0069, "overkill_bootstrap_lzexe_main_loop_1c43_0069")
def overkill_bootstrap_lzexe_main_loop_1c43_0069(cpu):
    """Lift hot LZEXE bootstrap bitstream loop in temporary segment 1C43."""
    _run_bootstrap_lzexe_loop_0069_if_matching(cpu)


@registry.replace(0x23AD, 0x0069, "overkill_bootstrap_lzexe_main_loop_23ad_0069")
def overkill_bootstrap_lzexe_main_loop_23ad_0069(cpu):
    """Lift hot LZEXE bootstrap bitstream loop in temporary segment 23AD."""
    _run_bootstrap_lzexe_loop_0069_if_matching(cpu)














@registry.replace(0x1010, 0x33DD, "overkill_expand_tandy_cell_33dd")
def overkill_expand_tandy_cell_33dd(cpu):
    """Hook wrapper for OVERKILL 1010:33DD Tandy startup cell expander."""
    run_expand_tandy_cell_33dd(cpu)


@registry.replace(0x1010, 0x33B2, "overkill_expand_tandy_block_33b2")
def overkill_expand_tandy_block_33b2(cpu):
    """Hook wrapper for OVERKILL 1010:33B2 Tandy startup block expander."""
    run_expand_tandy_block_33b2(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x33AF, "overkill_expand_tandy_list_33af")
def overkill_expand_tandy_list_33af(cpu):
    """Hook wrapper for OVERKILL 1010:33AF Tandy startup list expander."""
    run_expand_tandy_list_33af(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x0FE4, "overkill_tandy_pixel_pair_table_0fe4")
def overkill_tandy_pixel_pair_table_0fe4(cpu):
    """Hook wrapper for OVERKILL 1010:0FE4 Tandy pixel-pair lookup table init."""
    run_tandy_pixel_pair_table_0fe4(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x0F0B, "overkill_startup_coordinate_tables_0f0b")
def overkill_startup_coordinate_tables_0f0b(cpu):
    """Hook wrapper for OVERKILL 1010:0F0B startup coordinate/video tables."""
    run_tandy_startup_coordinate_tables_0f0b(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x0FA3, "overkill_tandy_video_offset_tables_0fa3")
def overkill_tandy_video_offset_tables_0fa3(cpu):
    """Hook wrapper for OVERKILL 1010:0FA3 Tandy/CGA video offset table init."""
    run_tandy_video_offset_tables_0fa3(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x30B0, "overkill_tandy_interlaced_clear_30b0")
def overkill_tandy_interlaced_clear_30b0(cpu):
    """Hook wrapper for OVERKILL 1010:30B0 Tandy interlaced buffer clear."""
    run_tandy_interlaced_clear_30b0(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x3389, "overkill_tandy_interlaced_clear_3389")
def overkill_tandy_interlaced_clear_3389(cpu):
    """Hook wrapper for OVERKILL 1010:3389 Tandy interlaced clear from current DI."""
    if _self_disable_if_patched(cpu, 0x3389, _SIG_3389, "overkill_tandy_interlaced_clear_3389"):
        return
    run_tandy_interlaced_clear_3389(cpu)


@registry.replace(0x1010, 0x30BA, "overkill_tandy_patched_row_copy_30ba")
def overkill_tandy_patched_row_copy_30ba(cpu):
    """Hook wrapper for runtime-patched OVERKILL 1010:30BA Tandy row copier."""
    if not _code_matches(cpu, 0x30BA, _SIG_30BA_PATCHED_ROW_COPY):
        _interpret_current_instruction_without_hook(cpu)
        return
    run_tandy_patched_strided_row_copy_30ba(cpu)













@registry.replace(0x1010, 0x2E6E, "overkill_tandy_masked_sprite_composite_2e6e")
def overkill_tandy_masked_sprite_composite_2e6e(cpu):
    """Hook wrapper for OVERKILL 1010:2E6E Tandy masked compositor."""
    run_tandy_masked_sprite_composite_2e6e(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x2F40, "overkill_tandy_or_inverted_mask_2f40")
def overkill_tandy_or_inverted_mask_2f40(cpu):
    """Hook wrapper for OVERKILL 1010:2F40 Tandy inverted-mask OR compositor."""
    run_tandy_or_inverted_mask_2f40(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x2ECB, "overkill_tandy_or_inverted_mask_2ecb")
def overkill_tandy_or_inverted_mask_2ecb(cpu):
    """Hook wrapper for OVERKILL 1010:2ECB Tandy inverted-mask OR compositor."""
    run_tandy_or_inverted_mask_2ecb(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x2F81, "overkill_tandy_masked_sprite_composite_2f81")
def overkill_tandy_masked_sprite_composite_2f81(cpu):
    """Hook wrapper for OVERKILL 1010:2F81 Tandy masked compositor."""
    run_tandy_masked_sprite_composite_2f81(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x35AA, "overkill_tandy_source_strided_copy_35aa")
def overkill_tandy_source_strided_copy_35aa(cpu):
    """Hook wrapper for OVERKILL 1010:35AA Tandy source-strided copy."""
    run_tandy_source_strided_copy_35aa(cpu, _tandy_render_runtime())




@registry.replace(0x1010, 0x34AD, "overkill_tandy_split_present_copy_34ad")
def overkill_tandy_split_present_copy_34ad(cpu):
    """Hook wrapper for OVERKILL 1010:34AD Tandy split present copy."""
    run_tandy_split_present_copy_34ad(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x34C5, "overkill_tandy_strided_copy_34c5")
def overkill_tandy_strided_copy_34c5(cpu):
    """Hook wrapper for OVERKILL 1010:34C5 Tandy strided copy helper."""
    run_tandy_strided_copy_34c5(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x34D8, "overkill_tandy_small_strided_copy_34d8")
def overkill_tandy_small_strided_copy_34d8(cpu):
    """Hook wrapper for OVERKILL 1010:34D8 Tandy small strided copy."""
    run_tandy_small_strided_copy_34d8(cpu, _tandy_render_runtime())




@registry.replace(0x1010, 0x3542, "overkill_tandy_tiny_strided_copy_3542")
def overkill_tandy_tiny_strided_copy_3542(cpu):
    """Hook wrapper for OVERKILL 1010:3542 Tandy tiny strided copy."""
    run_tandy_tiny_strided_copy_3542(cpu, _tandy_render_runtime())





@registry.replace(0x1010, 0x3657, "overkill_tandy_draw_tiny_object_3657")
def overkill_tandy_draw_tiny_object_3657(cpu):
    """Hook wrapper for OVERKILL 1010:3657 Tandy tiny-object draw."""
    run_tandy_draw_tiny_object_3657(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x356C, "overkill_tandy_draw_split_object_356c")
def overkill_tandy_draw_split_object_356c(cpu):
    """Hook wrapper for OVERKILL 1010:356C Tandy split-object draw."""
    run_tandy_draw_split_object_356c(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x35CC, "overkill_tandy_draw_object_block_35cc")
def overkill_tandy_draw_object_block_35cc(cpu):
    """Hook wrapper for OVERKILL 1010:35CC Tandy object-block draw."""
    run_tandy_draw_object_block_35cc(cpu, _tandy_render_runtime())





























































@registry.replace(0x1010, 0x7596, "overkill_layer_draw_type_dispatch_7596")
def overkill_layer_draw_type_dispatch_7596(cpu):
    """Hook wrapper for OVERKILL 1010:7596 layer draw type jump-table dispatch."""
    dispatch_layer_draw_type_7596(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xA8BE, "overkill_layer0_call_7596_a8be")
def overkill_layer0_call_7596_a8be(cpu):
    """Hook wrapper for A894 active-entry CALL 7596 glue."""
    call_layer0_draw_type_from_scan_a8be(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xA8C1, "overkill_layer0_scan_tail_a8c1")
def overkill_layer0_scan_tail_a8c1(cpu):
    """Hook wrapper for A894 post-draw POP/LOOP glue."""
    finish_layer0_scan_tail_a8c1(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xA8F1, "overkill_layer1_call_7596_a8f1")
def overkill_layer1_call_7596_a8f1(cpu):
    """Hook wrapper for A8C7 active-entry CALL 7596 glue."""
    call_layer1_draw_type_from_scan_a8f1(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xA8F4, "overkill_layer1_scan_tail_a8f4")
def overkill_layer1_scan_tail_a8f4(cpu):
    """Hook wrapper for A8C7 post-draw POP/LOOP glue."""
    finish_layer1_scan_tail_a8f4(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xA858, "overkill_scan_draw_call_5ac8_a858")
def overkill_scan_draw_call_5ac8_a858(cpu):
    """Hook wrapper for A849 active-entry CALL 5AC8 glue."""
    call_draw_dispatch_from_scan_a858(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xA85B, "overkill_scan_draw_tail_a85b")
def overkill_scan_draw_tail_a85b(cpu):
    """Hook wrapper for A849 post-draw POP/LOOP glue."""
    finish_draw_scan_tail_a85b(cpu, _layer_sprite_runtime())



@registry.replace(0x1010, 0xA846, "overkill_scan_draw_setup_32ca_a846")
def overkill_scan_draw_setup_32ca_a846(cpu):
    """Set up the 32CA draw scan: MOV CX,24h; fall through to A849."""
    if _self_disable_if_patched(cpu, 0xA846, _SIG_A846, "overkill_scan_draw_setup_32ca_a846"):
        return
    cpu.s.cx = 0x0024
    cpu.s.ip = 0xA849


@registry.replace(0x1010, 0xA876, "overkill_presence_stamp_call_a876")
def overkill_presence_stamp_call_a876(cpu):
    """Model A876: CALL 4CED and continue at A879."""
    if _self_disable_if_patched(cpu, 0xA876, _SIG_A876, "overkill_presence_stamp_call_a876"):
        return
    _call_installed_hook_like_near_call(cpu, (0x1010, 0x4CED), overkill_presence_stamp_triplet_4ced, 0xA879)


@registry.replace(0x1010, 0xA85E, "overkill_scan_draw_setup_8d12_a85e")
def overkill_scan_draw_setup_8d12_a85e(cpu):
    """Set up the second draw scan: MOV CX,22h; fall through to A861."""
    if _self_disable_if_patched(cpu, 0xA85E, _SIG_A85E, "overkill_scan_draw_setup_8d12_a85e"):
        return
    cpu.s.cx = 0x0022
    cpu.s.ip = 0xA861


@registry.replace(0x1010, 0xA870, "overkill_scan_draw_call_5ac8_a870")
def overkill_scan_draw_call_5ac8_a870(cpu):
    """Hook wrapper for A861 active-entry CALL 5AC8 glue."""
    if _self_disable_if_patched(cpu, 0xA870, _SIG_A870, "overkill_scan_draw_call_5ac8_a870"):
        return
    _call_installed_hook_like_near_call(cpu, (0x1010, 0x5AC8), overkill_dispatch_draw_object_5ac8, 0xA873)


@registry.replace(0x1010, 0xA873, "overkill_scan_draw_tail_a873")
def overkill_scan_draw_tail_a873(cpu):
    """Model A873: POP CX ; LOOP A861 for the 8D12 draw scan."""
    if _self_disable_if_patched(cpu, 0xA873, _SIG_A873, "overkill_scan_draw_tail_a873"):
        return
    cpu.s.cx = cpu.pop()
    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xA861 if cpu.s.cx != 0 else 0xA876


@registry.replace(0x1010, 0xA879, "overkill_compact_layer_scan_setup_a879")
def overkill_compact_layer_scan_setup_a879(cpu):
    """Set up the compact layer scan: MOV CX,22h; fall through to A87C."""
    if _self_disable_if_patched(cpu, 0xA879, _SIG_A879, "overkill_compact_layer_scan_setup_a879"):
        return
    cpu.s.cx = 0x0022
    cpu.s.ip = 0xA87C


@registry.replace(0x1010, 0xA88B, "overkill_compact_layer_call_7746_a88b")
def overkill_compact_layer_call_7746_a88b(cpu):
    """Hook wrapper for A87C active-entry CALL 7746 glue."""
    if _self_disable_if_patched(cpu, 0xA88B, _SIG_A88B, "overkill_compact_layer_call_7746_a88b"):
        return
    cpu.push(0xA88E)
    draw_compact_layer_sprite_7746(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xA88E, "overkill_compact_layer_scan_tail_a88e")
def overkill_compact_layer_scan_tail_a88e(cpu):
    """Model A88E: POP CX ; LOOP A87C for the compact layer scan."""
    if _self_disable_if_patched(cpu, 0xA88E, _SIG_A88E, "overkill_compact_layer_scan_tail_a88e"):
        return
    cpu.s.cx = cpu.pop()
    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xA87C if cpu.s.cx != 0 else 0xA891


@registry.replace(0x1010, 0xA891, "overkill_layer0_scan_setup_a891")
def overkill_layer0_scan_setup_a891(cpu):
    """Set up the layer-0 draw scan: MOV CX,23h; fall through to A894."""
    if _self_disable_if_patched(cpu, 0xA891, _SIG_A891, "overkill_layer0_scan_setup_a891"):
        return
    cpu.s.cx = 0x0023
    cpu.s.ip = 0xA894


@registry.replace(0x1010, 0xA8C4, "overkill_layer1_scan_setup_a8c4")
def overkill_layer1_scan_setup_a8c4(cpu):
    """Set up the layer-1 draw scan: MOV CX,24h; fall through to A8C7."""
    if _self_disable_if_patched(cpu, 0xA8C4, _SIG_A8C4, "overkill_layer1_scan_setup_a8c4"):
        return
    cpu.s.cx = 0x0024
    cpu.s.ip = 0xA8C7


@registry.replace(0x1010, 0xA8F7, "overkill_optional_layer_draw_tail_a8f7")
def overkill_optional_layer_draw_tail_a8f7(cpu):
    """Model A8F7: optional extra layer draw gate; common path returns immediately."""
    if _self_disable_if_patched(cpu, 0xA8F7, _SIG_A8F7, "overkill_optional_layer_draw_tail_a8f7"):
        return
    value = cpu.mem.rw(cpu.s.ds & 0xFFFF, 0xA47C)
    _cmp_word(cpu, value, 0)
    if value == 0:
        cpu.s.ip = cpu.pop()
    else:
        cpu.s.ip = 0xA8FF


@registry.replace(0x1010, 0xA936, "overkill_scan_present_call_5a92_a936")
def overkill_scan_present_call_5a92_a936(cpu):
    """Hook wrapper for A927 active-entry CALL 5A92 glue."""
    call_present_dispatch_from_scan_a936(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xA939, "overkill_scan_present_tail_a939")
def overkill_scan_present_tail_a939(cpu):
    """Hook wrapper for A927 post-present POP/LOOP glue."""
    finish_present_scan_tail_a939(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xA91E, "overkill_scan_present_call_5a92_a91e")
def overkill_scan_present_call_5a92_a91e(cpu):
    """Hook wrapper for A90F active-entry CALL 5A92 glue."""
    if _self_disable_if_patched(cpu, 0xA91E, _SIG_A91E, "overkill_scan_present_call_5a92_a91e"):
        return
    _call_installed_hook_like_near_call(cpu, (0x1010, 0x5A92), overkill_dispatch_present_object_5a92, 0xA921)


@registry.replace(0x1010, 0xA921, "overkill_scan_present_tail_a921")
def overkill_scan_present_tail_a921(cpu):
    """Model A921: POP CX ; LOOP A90F for the 8D12 present scan."""
    if _self_disable_if_patched(cpu, 0xA921, _SIG_A921, "overkill_scan_present_tail_a921"):
        return
    cpu.s.cx = cpu.pop()
    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xA90F if cpu.s.cx != 0 else 0xA924


@registry.replace(0x1010, 0xA924, "overkill_scan_present_setup_32ca_a924")
def overkill_scan_present_setup_32ca_a924(cpu):
    """Set up the 32CA present scan: MOV CX,24h; fall through to A927."""
    if _self_disable_if_patched(cpu, 0xA924, _SIG_A924, "overkill_scan_present_setup_32ca_a924"):
        return
    cpu.s.cx = 0x0024
    cpu.s.ip = 0xA927


@registry.replace(0x1010, 0x768E, "overkill_layer_sprite_draw_768e")
def overkill_layer_sprite_draw_768e(cpu):
    """Hook wrapper for OVERKILL 1010:768E shared layer-sprite draw helper."""
    draw_layer_sprite_768e(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0x77C5, "overkill_frame_effect_gate_77c5")
def overkill_frame_effect_gate_77c5(cpu):
    """Frame-effect state gate around the 77F6 slash/column renderer."""

    def call_slash(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x77F6),
            overkill_frame_effect_slash_77f6,
            return_ip,
        )

    def call_page_toggle(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x511F),
            overkill_video_page_toggle_511f,
            return_ip,
        )

    run_frame_effect_gate_77c5(cpu, _self_disable_if_patched, call_slash, call_page_toggle)


@registry.replace(0x1010, 0x77F6, "overkill_frame_effect_slash_77f6")
def overkill_frame_effect_slash_77f6(cpu):
    """Frame-effect draw/clear column helper used by 77DF/9EE4."""
    run_frame_effect_slash_77f6(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0x75A6, "overkill_layer_sprite_draw_75a6")
def overkill_layer_sprite_draw_75a6(cpu):
    """Hook wrapper for OVERKILL 1010:75A6 shared double-slot layer draw."""
    draw_layer_sprite_75a6(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0x2FB6, "overkill_tandy_masked_compact_2fb6")
def overkill_tandy_masked_compact_2fb6(cpu):
    """Hook wrapper for OVERKILL 1010:2FB6 Tandy compact masked compositor."""
    run_tandy_masked_compact_2fb6(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x306F, "overkill_tandy_rect_copy_306f")
def overkill_tandy_rect_copy_306f(cpu):
    """Hook wrapper for OVERKILL 1010:306F Tandy raw rectangular copy."""
    run_tandy_rect_copy_306f(cpu, _tandy_render_runtime())








@registry.replace(0x1010, 0x4E0D, "overkill_tandy_loading_scroll_until_4e0d")
def overkill_tandy_loading_scroll_until_4e0d(cpu):
    """Replace 4E0D parent loop around the A781 loading-scroll step."""
    if _self_disable_if_patched(cpu, 0x4E0D, _SIG_4E0D, "overkill_tandy_loading_scroll_until_4e0d"):
        return
    run_tandy_loading_scroll_until_4e0d(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x4E26, "overkill_tandy_loading_tile_remap_scan_4e26")
def overkill_tandy_loading_tile_remap_scan_4e26(cpu):
    """Replace loading/menu work-buffer tile-id remap scan at 1010:4E26."""
    if _self_disable_if_patched(cpu, 0x4E26, _SIG_4E26, "overkill_tandy_loading_tile_remap_scan_4e26"):
        return
    run_tandy_loading_tile_remap_scan_4e26(cpu)

@registry.replace(0x1010, 0x60C5, "overkill_tandy_loading_scroll_sequence_60c5")
def overkill_tandy_loading_scroll_sequence_60c5(cpu):
    """Hook wrapper for OVERKILL 1010:60C5 Tandy loading scroll sequence."""
    run_tandy_loading_scroll_sequence_60c5(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x36A2, "overkill_tandy_loading_tile_column_copy_36a2")
def overkill_tandy_loading_tile_column_copy_36a2(cpu):
    """Hook wrapper for OVERKILL 1010:36A2 Tandy loading tile-column copy."""
    run_tandy_loading_tile_column_copy_36a2(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x7746, "overkill_compact_layer_sprite_draw_7746")
def overkill_compact_layer_sprite_draw_7746(cpu):
    """Hook wrapper for OVERKILL 1010:7746 shared compact layer draw."""
    draw_compact_layer_sprite_7746(cpu, _layer_sprite_runtime())






































@registry.replace(0x1010, 0x375B, "overkill_tandy_postcopy_scaled_blit_375b")
def overkill_tandy_postcopy_scaled_blit_375b(cpu):
    """Hook wrapper for OVERKILL 1010:375B Tandy post-copy scaled blitter."""
    if _self_disable_if_patched(cpu, 0x375B, _SIG_375B, "overkill_tandy_postcopy_scaled_blit_375b"):
        return
    run_tandy_postcopy_scaled_blit_375b(cpu)


@registry.replace(0x1010, 0x3824, "overkill_tandy_full_width_panel_copy_3824")
def overkill_tandy_full_width_panel_copy_3824(cpu):
    """Replace the 1010:3824 full-width Tandy menu/panel copy loop."""
    if _self_disable_if_patched(cpu, 0x3824, _SIG_3824, "overkill_tandy_full_width_panel_copy_3824"):
        return
    run_tandy_full_width_panel_copy_3824(cpu)


@registry.replace(0x1010, 0x497A, "overkill_blit_scaled_column_block_497a")
def overkill_blit_scaled_column_block_497a(cpu):
    """Replace the hot display blit/clear routine at 1010:497A.

    Evidence: reached from the renderer dispatcher at 1010:58EC through a
    function-pointer table selected by CS:95BC.  The routine copies rows from
    DS:SI to ES:DI (usually decoded asset buffer -> B800 planar video memory),
    optionally skipping/duplicating source rows according to CS:5901/5903/5905,
    and uses the same planar address step as the original inner loops.

    This is deliberately a direct transliteration of 497A..4A40, not a guessed
    high-level renderer.  It preserves the observed register/flag/stack state
    by using the same arithmetic flag helpers as the interpreter.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    # 497A: mov cs:[5903],0000h
    mem.ww(cs, 0x5903, 0)
    # 4981..4995: load local state and double BP (source bytes per row)
    cpu.s.di = mem.rw(cs, 0x58F9)
    cpu.s.si = mem.rw(cs, 0x58FB)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    cpu.s.bp = mem.rw(cs, 0x58FF)
    cpu.s.bp = cpu.shift(4, cpu.s.bp, 1, 16)  # SHL BP,1

    # Optional bottom-up source positioning.
    _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
    if not cpu.get_flag(ZF):
        cpu.s.ax = cpu.s.bp & 0xFFFF
        _dec_reg16_preserve_cf(cpu, 1)  # DEC CX
        # MUL CX, matching CPU8086 group-F7 behavior: AX*CX -> DX:AX, CF/OF only.
        result = (cpu.s.ax & 0xFFFF) * (cpu.s.cx & 0xFFFF)
        cpu.s.ax = result & 0xFFFF
        cpu.s.dx = (result >> 16) & 0xFFFF
        carry = cpu.s.dx != 0
        cpu.set_flag(CF, carry)
        cpu.set_flag(0x0800, carry)  # OF
        _inc_reg16_preserve_cf(cpu, 1)  # INC CX
        _add_reg16(cpu, 6, cpu.s.ax)    # ADD SI,AX

    # Initial clear/skip region before the first copied row.
    cpu.push(cpu.s.cx)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    _sub_reg16(cpu, 1, mem.rw(cs, 0x5901))
    _test_word(cpu, cpu.s.cx, cpu.s.cx)  # OR CX,CX
    if not cpu.get_flag(SF):
        cpu.s.cx = cpu.shift(5, cpu.s.cx, 1, 16)  # SHR CX,1
        if cpu.s.cx != 0:
            _dec_reg16_preserve_cf(cpu, 1)
            if cpu.s.cx != 0:
                # 49BD..49CB: advance DI by CX-1 planar rows.
                while cpu.s.cx != 0:
                    _ega_next_scanline_di(cpu)
                    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, no flags
            # 49CD..49E3: clear one row and advance to next row.
            _xor_al_al(cpu)
            cpu.s.cx = cpu.s.bp & 0xFFFF
            _rep_stosb(cpu, cpu.s.cx)
            _sub_reg16(cpu, 7, cpu.s.bp)
            _ega_next_scanline_di(cpu)
    cpu.s.cx = cpu.pop()

    # 49E4..4A38: copy/skip rows according to CS:5901 accumulator.
    while True:
        cpu.s.ax = mem.rw(cs, 0x5901)
        _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x58FD))
        if cpu.get_flag(ZF):
            copy_this_row = True
        else:
            _add_mem_word(cpu, cs, 0x5903, cpu.s.ax)
            cpu.s.ax = mem.rw(cs, 0x58FD)
            _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x5903))
            # JA 4A11: jump if AX > CS:5903, unsigned.
            if (not cpu.get_flag(CF)) and (not cpu.get_flag(ZF)):
                _sub_mem_word(cpu, cs, 0x5903, cpu.s.ax)
                copy_this_row = True
            else:
                _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
                if cpu.get_flag(ZF):
                    _add_reg16(cpu, 6, cpu.s.bp)
                else:
                    _sub_reg16(cpu, 6, cpu.s.bp)
                cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP 49E4, no flags
                if cpu.s.cx != 0:
                    continue
                break

        # 4A16..4A38: copy one BP-byte row, advance planar DI, optionally step SI back.
        cpu.push(cpu.s.cx)
        cpu.s.cx = cpu.s.bp & 0xFFFF
        _rep_movsb(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, cpu.s.bp)
        _ega_next_scanline_di(cpu)
        _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
        if not cpu.get_flag(ZF):
            _sub_reg16(cpu, 6, cpu.s.bp)
            _sub_reg16(cpu, 6, cpu.s.bp)
        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP 49E4, no flags
        if cpu.s.cx != 0:
            continue
        break

    # 4A3A..4A40: final clear row and RET.
    _xor_al_al(cpu)
    cpu.s.cx = cpu.s.bp & 0xFFFF
    _rep_stosb(cpu, cpu.s.cx)
    cpu.s.ip = cpu.pop()

@registry.replace(0x1010, 0x41DA, "overkill_linear_rows_to_work_buffer_41da")
def overkill_linear_rows_to_work_buffer_41da(cpu):
    """Replace 1010:41DA row-copy routine selected by the 5A5A table.

    Thin boundary wrapper; the body lives in
    :func:`overkill.rendering.tandy.linear_rows_to_work_buffer_41da`.
    """
    run_tandy_linear_rows_to_work_buffer_41da(cpu)


@registry.replace(0x1010, 0x477E, "overkill_sprite_blit_9x16_477e")
def overkill_sprite_blit_9x16_477e(cpu):
    """Replace the fully-unrolled fixed-geometry sprite blit at 1010:477E.

    Thin boundary wrapper; the Tandy sprite-blit body lives in
    :func:`overkill.rendering.tandy.sprite_blit_9x16_477e`.
    """
    run_tandy_sprite_blit_9x16_477e(cpu)


@registry.replace(0x1010, 0x38B7, "overkill_masked_sprite_composite_38b7")
def overkill_masked_sprite_composite_38b7(cpu):
    """Replace the masked 2-column sprite-composite loop at 1010:38B7..38CF.

    Profiling after the 477E lift showed this is the hottest remaining
    interpreted routine during sprite-heavy frames.  It is a tight LOOP that
    composites a sprite over the destination with the classic AND-mask / OR-data
    operation, two 16-bit columns per row:

        38B7  lodsw                ; mask = DS:[SI], SI += 2
        38B8  and ax, es:[di]      ; AX = mask AND dest word (keep background)
        38BB  or  ax, ds:[si]      ; AX |= data word = DS:[SI] (paint sprite)
        38BD  add si, 2            ; step past the data word
        38C0  stosw                ; ES:[DI] = AX, DI += 2
        38C1..38CA  (identical second column)
        38CB  add di, 0030h        ; next visible row (net DI stride 0034h)
        38CE  loop 38B7            ; CX rows (CX==0 -> 65536, 8086 rule)
        38D0  (fall-through)

    Per row the source is [mask0, data0, mask1, data1] so SI advances 8; the
    destination advances 0034h (two words written + 30h).  The destination is a
    read-modify-write (the AND reads ES:[DI] before STOSW overwrites it).  Only
    the final `add di,0030h` leaves live FLAGS; AX holds the last composited
    word; CX exits 0; control falls through to 38D0.  LODSW/STOSW honour DF; the
    immediate `add si,2`/`add di,30h` do not.  Verified bit-identical to the
    interpreted loop over 2000 randomised states.
    """
    s = cpu.s
    mem = cpu.mem
    df = cpu.get_flag(DF)
    rows = s.cx if s.cx != 0 else 0x10000
    es = s.es & 0xFFFF
    ds = s.ds & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    sd = -2 if df else 2
    old_di = di
    for _ in range(rows):
        for _col in range(2):
            mask = mem.rw(ds, si)            # lodsw
            si = (si + sd) & 0xFFFF
            ax = mask & mem.rw(es, di)       # and ax, es:[di]
            ax = ax | mem.rw(ds, si)         # or  ax, ds:[si]
            si = (si + 2) & 0xFFFF           # add si, 2
            mem.ww(es, di, ax)               # stosw
            di = (di + sd) & 0xFFFF
        old_di = di
        di = (di + 0x30) & 0xFFFF            # add di, 0030h
    cpu.set_add_flags(old_di, 0x30, old_di + 0x30, 16)
    s.si = si
    s.di = di
    s.ax = ax
    s.cx = 0
    # The original 38B7 loop falls into the shared 38D0 tail
    # (MOV DS,CS:[9596]; RET).  Earlier versions stopped at 38D0 and used a
    # private helper when 38B7 was reached as a compositor jump target; that made
    # the registered 38B7 boundary partial.  Keep the hook complete so any
    # parent that jumps here can route through the hook verifier.
    s.ds = cpu.mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x3849, "overkill_masked_sprite_composite_3849")
def overkill_masked_sprite_composite_3849(cpu):
    """Replace the 4-column masked sprite composite loop at 1010:3849.

    This is the wider sibling of the verified 38B7 hook.  Each row composites
    four destination words using source pairs [mask,data] and then advances the
    destination by 0x2C, for a net visible stride of 0x34 bytes.  The helper
    finally restores DS from CS:[9596] and returns near.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -2 if cpu.get_flag(DF) else 2
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        for _col in range(4):
            mask = mem.rw(ds, si)
            si = (si + sd) & 0xFFFF
            ax = mask & mem.rw(es, di)
            ax = ax | mem.rw(ds, si)
            si = (si + 2) & 0xFFFF
            mem.ww(es, di, ax)
            di = (di + sd) & 0xFFFF
        old_di = di
        di = (di + 0x2C) & 0xFFFF

    cpu.set_add_flags(old_di, 0x2C, old_di + 0x2C, 16)
    s.ax = ax
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()












@registry.replace(0x1010, 0x40D7, "overkill_ega_compact_spread_composite_40d7")
def overkill_ega_compact_spread_composite_40d7(cpu):
    run_ega_compact_spread_composite_40d7(cpu)


@registry.replace(0x1010, 0x412B, "overkill_ega_compact_spread_composite_412b")
def overkill_ega_compact_spread_composite_412b(cpu):
    run_ega_compact_spread_composite_412b(cpu)


@registry.replace(0x1010, 0x409D, "overkill_ega_compact_spread_composite_409d")
def overkill_ega_compact_spread_composite_409d(cpu):
    run_ega_compact_spread_composite_409d(cpu)


def _cga_or_inverted_composite_rows(cpu, *, words_per_row: int, row_add: int) -> None:
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -2 if cpu.get_flag(DF) else 2
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        for _col in range(words_per_row):
            ax = mem.rw(ds, si)              # LODSW
            si = (si + sd) & 0xFFFF
            ax = (~ax) & 0xFFFF              # NOT AX
            value = mem.rw(es, di) | ax      # OR ES:[DI],AX
            mem.ww(es, di, value & 0xFFFF)
            cpu.set_logic_flags(value, 16)
            old_si = si
            si = (si + 0x0002) & 0xFFFF      # ADD SI,2
            cpu.set_add_flags(old_si, 0x0002, old_si + 0x0002, 16)
            old_di_col = di
            di = (di + 0x0002) & 0xFFFF      # ADD DI,2
            cpu.set_add_flags(old_di_col, 0x0002, old_di_col + 0x0002, 16)
        old_di = di
        di = (di + row_add) & 0xFFFF
        cpu.set_add_flags(old_di, row_add, old_di + row_add, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x387C, "overkill_or_inverted_sprite_composite_387c")
def overkill_or_inverted_sprite_composite_387c(cpu):
    """Replace the 4-column CGA inverted-mask OR compositor at 1010:387C."""
    _cga_or_inverted_composite_rows(cpu, words_per_row=4, row_add=0x002C)


@registry.replace(0x1010, 0x38D6, "overkill_or_inverted_sprite_composite_38d6")
def overkill_or_inverted_sprite_composite_38d6(cpu):
    """Replace the 2-column CGA inverted-mask OR compositor at 1010:38D6."""
    _cga_or_inverted_composite_rows(cpu, words_per_row=2, row_add=0x0030)


@registry.replace(0x1010, 0x390E, "overkill_or_inverted_sprite_composite_390e")
def overkill_or_inverted_sprite_composite_390e(cpu):
    """Replace the 1-column CGA inverted-mask OR compositor at 1010:390E."""
    _cga_or_inverted_composite_rows(cpu, words_per_row=1, row_add=0x0032)








@registry.replace(0x1010, 0x2193, "overkill_ega_compact_byte_masked_composite_2193")
def overkill_ega_compact_byte_masked_composite_2193(cpu):
    run_ega_compact_byte_masked_composite_2193(cpu)








@registry.replace(0x1010, 0x238D, "overkill_ega_compact_byte_spread_left_composite_238d")
def overkill_ega_compact_byte_spread_left_composite_238d(cpu):
    run_ega_compact_byte_spread_left_composite_238d(cpu)


@registry.replace(0x1010, 0x2410, "overkill_ega_compact_byte_spread_left_composite_2410")
def overkill_ega_compact_byte_spread_left_composite_2410(cpu):
    run_ega_compact_byte_spread_left_composite_2410(cpu)


@registry.replace(0x1010, 0x247E, "overkill_ega_compact_byte_spread_left_composite_247e")
def overkill_ega_compact_byte_spread_left_composite_247e(cpu):
    run_ega_compact_byte_spread_left_composite_247e(cpu)


@registry.replace(0x1010, 0x21D6, "overkill_ega_compact_byte_spread_composite_21d6")
def overkill_ega_compact_byte_spread_composite_21d6(cpu):
    run_ega_compact_byte_spread_composite_21d6(cpu)


@registry.replace(0x1010, 0x2223, "overkill_ega_compact_byte_spread_composite_2223")
def overkill_ega_compact_byte_spread_composite_2223(cpu):
    run_ega_compact_byte_spread_composite_2223(cpu)


@registry.replace(0x1010, 0x2285, "overkill_ega_compact_byte_spread_composite_2285")
def overkill_ega_compact_byte_spread_composite_2285(cpu):
    run_ega_compact_byte_spread_composite_2285(cpu)


@registry.replace(0x1010, 0x22FC, "overkill_ega_compact_byte_spread_composite_22fc")
def overkill_ega_compact_byte_spread_composite_22fc(cpu):
    run_ega_compact_byte_spread_composite_22fc(cpu)


@registry.replace(0x1010, 0x38F9, "overkill_masked_sprite_composite_38f9")
def overkill_masked_sprite_composite_38f9(cpu):
    """Replace the compact 1-column CGA masked compositor at 1010:38F9.

    Reached from the compact layer helper 7746 in mode 0.  Each row consumes one
    source mask/data word pair, composites one destination word, then advances DI
    by 32h after STOSW for the same net 34h row stride as the wider CGA sprite
    compositors.  The original restores DS from CS:[9596] and returns near.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -2 if cpu.get_flag(DF) else 2
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        mask = mem.rw(ds, si)                 # LODSW
        si = (si + sd) & 0xFFFF
        ax = mask & mem.rw(es, di)            # AND AX,ES:[DI]
        ax = ax | mem.rw(ds, si)              # OR AX,DS:[SI]
        si = (si + 2) & 0xFFFF                # ADD SI,2
        mem.ww(es, di, ax & 0xFFFF)           # STOSW
        di = (di + sd) & 0xFFFF
        old_di = di
        di = (di + 0x32) & 0xFFFF             # ADD DI,32h

    cpu.set_add_flags(old_di, 0x32, old_di + 0x32, 16)
    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x10B7, "overkill_ega_layer_or_inverted_composite_10b7")
def overkill_ega_layer_or_inverted_composite_10b7(cpu):
    run_ega_layer_or_inverted_composite_10b7(cpu)


@registry.replace(0x1010, 0x103C, "overkill_ega_layer_masked_composite_103c")
def overkill_ega_layer_masked_composite_103c(cpu):
    run_ega_layer_masked_composite_103c(cpu)


@registry.replace(0x1010, 0x1AEB, "overkill_ega_spaced_word_composite_1aeb")
def overkill_ega_spaced_word_composite_1aeb(cpu):
    run_ega_spaced_word_composite_1aeb(cpu)


@registry.replace(0x1010, 0x1D1B, "overkill_ega_spread_masked_composite_1d1b")
def overkill_ega_spread_masked_composite_1d1b(cpu):
    run_ega_spread_masked_composite_1d1b(cpu)


@registry.replace(0x1010, 0x13E7, "overkill_ega_spread_masked_composite_wide_13e7")
def overkill_ega_spread_masked_composite_wide_13e7(cpu):
    run_ega_spread_masked_composite_wide_13e7(cpu)


@registry.replace(0x1010, 0x29C6, "overkill_ega_spaced_copy_29c6")
def overkill_ega_spaced_copy_29c6(cpu):
    run_ega_spaced_copy_29c6(cpu)


@registry.replace(0x1010, 0x2AB9, "overkill_ega_source_spaced_copy_2ab9")
def overkill_ega_source_spaced_copy_2ab9(cpu):
    run_ega_source_spaced_copy_2ab9(cpu)


@registry.replace(0x1010, 0x469F, "overkill_sprite_copy_9x16_469f")
def overkill_sprite_copy_9x16_469f(cpu):
    """Replace the hot 9-byte-wide by 16-row plain sprite copy at 1010:469F."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    old_di = di

    if not cpu.get_flag(DF):
        data = mem.data
        src_base = ds << 4
        dst_base = es << 4
        for _ in range(16):
            data[((dst_base + di) & 0xFFFFF):((dst_base + di) & 0xFFFFF) + 9] =                 data[((src_base + si) & 0xFFFFF):((src_base + si) & 0xFFFFF) + 9]
            si = (si + 9) & 0xFFFF
            old_di = (di + 9) & 0xFFFF
            di = (old_di + 0x2B) & 0xFFFF
    else:
        for _ in range(16):
            for _word in range(4):
                mem.ww(es, di, mem.rw(ds, si))
                si = (si - 2) & 0xFFFF
                di = (di - 2) & 0xFFFF
            mem.wb(es, di, mem.rb(ds, si))
            si = (si - 1) & 0xFFFF
            di = (di - 1) & 0xFFFF
            old_di = di
            di = (di + 0x2B) & 0xFFFF

    cpu.set_add_flags(old_di, 0x2B, old_di + 0x2B, 16)
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = cpu.pop()

@registry.replace(0x1010, 0x4D15, "overkill_presence_stamp_list_4d15")
def overkill_presence_stamp_list_4d15(cpu):
    """Replace the hot 1010:4D15 presence/stamp list helper.

    The caller feeds a compact list of triples.  Each iteration maps the first
    word through DS:[9A08 + word*2], adds DS:[234C] and the second word to get
    an ES-relative cell address, then uses the low byte of the third word as a
    marker.  Empty cells are stamped into ES and the cell address is appended to
    DS:DI; occupied cells are skipped.  In mode 1 it checks/stamps a small stack
    of vertically separated cells at +1Ah/+34h/+4Eh; BP selects whether the +4Eh
    layer is included.

    This screen is especially expensive when the live player disables the older
    interactive-risk render hooks: the planet/difficulty screen executes this
    loop tens of thousands of times.  Keep the loop in Python locals and only set
    FLAGS for the final original instruction that can survive the LOOP/RET.
    """
    s = cpu.s
    count = s.cx & 0xFFFF
    if count == 0:
        count = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    ds_base = ds << 4
    es_base = es << 4
    cs_base = cs << 4
    data = cpu.mem.data
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    delta = -2 if cpu.get_flag(DF) else 2
    table_base = 0x9A08
    scroll_base = data[((ds_base + 0x234C) & 0xFFFFF)] | (data[((ds_base + 0x234D) & 0xFFFFF)] << 8)
    mode = data[((cs_base + 0x95BC) & 0xFFFFF)] | (data[((cs_base + 0x95BD) & 0xFFFFF)] << 8)
    bx = s.bx & 0xFFFF
    ax = s.ax & 0xFFFF
    last_flag_kind = "none"
    last_flag_a = 0
    last_flag_b = 0
    last_flag_result = 0
    last_flag_bits = 8

    def read_word(seg_base: int, off: int) -> int:
        a = (seg_base + (off & 0xFFFF)) & 0xFFFFF
        if a == 0xFFFFF:
            return data[a] | (data[0] << 8)
        return data[a] | (data[a + 1] << 8)

    def write_word(seg_base: int, off: int, value: int) -> None:
        # DS:DI never targets EGA planar memory on this path, so direct writes are
        # safe and avoid the Memory.ww helper overhead inside the hot loop.
        a = (seg_base + (off & 0xFFFF)) & 0xFFFFF
        data[a] = value & 0xFF
        if a == 0xFFFFF:
            data[0] = (value >> 8) & 0xFF
        else:
            data[a + 1] = (value >> 8) & 0xFF

    def write_byte(seg_base: int, off: int, value: int) -> None:
        # ES is the presence/cell buffer in this routine, not the EGA A000h
        # aperture, so direct byte writes match Memory.wb without planar routing.
        data[(seg_base + (off & 0xFFFF)) & 0xFFFFF] = value & 0xFF

    for _ in range(count):
        # LODSW #1: compact table index.
        ax = read_word(ds_base, si)
        si = (si + delta) & 0xFFFF
        bx = ((ax << 1) + table_base) & 0xFFFF
        bx = read_word(ds_base, bx)
        bx = (bx + scroll_base) & 0xFFFF

        # LODSW #2: cell-relative offset.
        ax = read_word(ds_base, si)
        si = (si + delta) & 0xFFFF
        bx = (bx + ax) & 0xFFFF

        # LODSW #3: marker byte in AL.
        ax = read_word(ds_base, si)
        si = (si + delta) & 0xFFFF
        marker = ax & 0xFF

        cell = data[(es_base + bx) & 0xFFFFF]
        if cell != 0:
            last_flag_kind = "sub"
            last_flag_a = cell
            last_flag_b = 0
            last_flag_result = cell
            last_flag_bits = 8
            s.cx = (s.cx - 1) & 0xFFFF
            continue

        should_store = False
        store_1a = False
        store_34 = False
        store_4e = False
        if mode != 1:
            # JNE 4D59: non-mode-1 callers only stamp the base cell and append
            # the address to DS:DI.  The stacked +1A/+34/+4E stores are reached
            # only through the mode-1 JMP BP path.
            should_store = True
        else:
            blocked = False
            for off in (0x1A, 0x34, 0x4E):
                value = data[(es_base + ((bx + off) & 0xFFFF)) & 0xFFFFF]
                if value != 0:
                    last_flag_kind = "sub"
                    last_flag_a = value
                    last_flag_b = 0
                    last_flag_result = value
                    last_flag_bits = 8
                    blocked = True
                    break
            if not blocked:
                if bp not in (0x4D4D, 0x4D51):
                    s.ax = ax
                    s.bx = bx
                    s.si = si
                    s.di = di
                    s.ip = bp
                    return
                should_store = True
                store_1a = True
                store_34 = True
                store_4e = bp == 0x4D4D

        if should_store:
            if store_4e:
                write_byte(es_base, (bx + 0x4E) & 0xFFFF, marker)
            if store_34:
                write_byte(es_base, (bx + 0x34) & 0xFFFF, marker)
            if store_1a:
                write_byte(es_base, (bx + 0x1A) & 0xFFFF, marker)
            write_byte(es_base, bx, marker)
            write_word(ds_base, di, bx)
            old_di = di
            di = (di + 2) & 0xFFFF
            last_flag_kind = "add"
            last_flag_a = old_di
            last_flag_b = 2
            last_flag_result = old_di + 2
            last_flag_bits = 16

        s.cx = (s.cx - 1) & 0xFFFF

    s.ax = ax & 0xFFFF
    s.bx = bx & 0xFFFF
    s.si = si & 0xFFFF
    s.di = di & 0xFFFF
    s.cx = 0
    if last_flag_kind == "add":
        cpu.set_add_flags(last_flag_a, last_flag_b, last_flag_result, last_flag_bits)
    elif last_flag_kind == "sub":
        cpu.set_sub_flags(last_flag_a, last_flag_b, last_flag_result, last_flag_bits)
    s.ip = cpu.pop()


























def _tandy_render_runtime() -> TandyRenderRuntime:
    """Build VM callbacks/signatures for Tandy-specific rendering primitives."""
    return TandyRenderRuntime(
        self_disable_if_patched=_self_disable_if_patched,
        object_row_address_from_mode_dispatch_5a36=overkill_object_row_addr_5a36,
        signature_2e6e=_SIG_2E6E,
        signature_2ecb=_SIG_2ECB,
        signature_2f40=_SIG_2F40,
        signature_2f81=_SIG_2F81,
        signature_2fb6=_SIG_2FB6,
        signature_306f=_SIG_306F,
        signature_33af=_SIG_33AF,
        signature_33b2=_SIG_33B2,
        signature_34ad=_SIG_34AD,
        signature_34c5=_SIG_34C5,
        signature_34d8=_SIG_34D8,
        signature_3542=_SIG_3542,
        signature_35aa=_SIG_35AA,
        signature_36a2=_SIG_36A2,
        signature_60c5=_SIG_60C5,
        signature_35cc=_SIG_35CC,
        signature_356c=_SIG_356C,
        signature_3657=_SIG_3657,
        signature_0f0b=_SIG_0F0B,
        signature_0fa3=_SIG_0FA3,
        signature_0fe4=_SIG_0FE4,
        signature_30b0=_SIG_30B0,
    )


def _layer_sprite_runtime() -> LayerSpriteRuntime:
    """Build the callback table used by the shared layer-sprite module.

    The renderer setup logic now lives outside this large hook-registration file,
    but the concrete compositor hook functions remain here for now.  Creating the
    table lazily keeps import order simple while avoiding a circular import from
    ``overkill.rendering.layer_sprites`` back into this module.
    """
    return LayerSpriteRuntime(
        self_disable_if_patched=_self_disable_if_patched,
        fail_unverified=_raise_unverified_path,
        signature_75a6=_SIG_75A6,
        signature_768e=_SIG_768E,
        signature_7746=_SIG_7746,
        compositor_handlers={
            # EGA compact/spread compositor leaves.
            0x2193: overkill_ega_compact_byte_masked_composite_2193,
            0x238D: overkill_ega_compact_byte_spread_left_composite_238d,
            0x2410: overkill_ega_compact_byte_spread_left_composite_2410,
            0x247E: overkill_ega_compact_byte_spread_left_composite_247e,
            0x21D6: overkill_ega_compact_byte_spread_composite_21d6,
            0x2223: overkill_ega_compact_byte_spread_composite_2223,
            0x2285: overkill_ega_compact_byte_spread_composite_2285,
            0x22FC: overkill_ega_compact_byte_spread_composite_22fc,
            0x409D: overkill_ega_compact_spread_composite_409d,
            0x40D7: overkill_ega_compact_spread_composite_40d7,
            0x412B: overkill_ega_compact_spread_composite_412b,
            # CGA compositor leaves.
            0x387C: overkill_or_inverted_sprite_composite_387c,
            0x38D6: overkill_or_inverted_sprite_composite_38d6,
            0x390E: overkill_or_inverted_sprite_composite_390e,
            0x3849: overkill_masked_sprite_composite_3849,
            0x38B7: overkill_masked_sprite_composite_38b7,
            0x38F9: overkill_masked_sprite_composite_38f9,
            # EGA full-width layer compositor leaves.
            0x10B7: overkill_ega_layer_or_inverted_composite_10b7,
            0x103C: overkill_ega_layer_masked_composite_103c,
            0x1AEB: overkill_ega_spaced_word_composite_1aeb,
            0x1D1B: overkill_ega_spread_masked_composite_1d1b,
            # Tandy compositor leaves.
            0x2F81: overkill_tandy_masked_sprite_composite_2f81,
            0x2F40: overkill_tandy_or_inverted_mask_2f40,
            0x2ECB: overkill_tandy_or_inverted_mask_2ecb,
            0x2E6E: overkill_tandy_masked_sprite_composite_2e6e,
            0x2FB6: overkill_tandy_masked_compact_2fb6,
        },
    )

















































@registry.replace(0x1010, 0xA849, "overkill_scan_objects_call_5ac8_a849")
def overkill_scan_objects_call_5ac8_a849(cpu):
    """Skip inactive 32CA draw entries up to the real ``CALL 5AC8``.

    A849 is only the descending scan wrapper.  Earlier versions tried to run the
    child 5AC8 draw dispatch inline for some known targets, but that crosses the
    verifier boundary: the original ASM stops at A858 before the CALL, while the
    composed hook may have already returned to A85E.  Keep this hook narrow and
    let the real CALL enter the independently verified 5AC8/target hooks.
    """
    if _self_disable_if_patched(cpu, 0xA849, _SIG_A849, "overkill_scan_objects_call_5ac8_a849"):
        return

    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ss = cpu.s.ss & 0xFFFF

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, 0x32CA, cx_value)
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)

        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = 0xA858
            return

        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = 0xA85E
            return

    cpu.s.ip = 0xA85E


@registry.replace(0x1010, 0xA861, "overkill_scan_objects_call_5ac8_a861")
def overkill_scan_objects_call_5ac8_a861(cpu):
    """Skip inactive 8D12 draw entries up to the real ``CALL 5AC8``.

    Hook verification for this wrapper is intentionally narrow: active entries
    continue at A870, and the separate 5AC8/target hooks own the draw dispatch.
    """
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ss = cpu.s.ss & 0xFFFF

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, 0x8D12, cx_value)
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = 0xA870
            return

        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = 0xA876
            return
    cpu.s.ip = 0xA876


@registry.replace(0x1010, 0xA87C, "overkill_scan_objects_call_7746_a87c")
def overkill_scan_objects_call_7746_a87c(cpu):
    """Skip inactive compact-layer entries up to the real ``CALL 7746``."""
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ss = cpu.s.ss & 0xFFFF
    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, 0x8D12, cx_value)
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = 0xA88B
            return
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = 0xA891
            return
    cpu.s.ip = 0xA891


@registry.replace(0x1010, 0xA894, "overkill_scan_layer0_draw_a894")
def overkill_scan_layer0_draw_a894(cpu):
    """Skip non-drawing entries in the overlaid layer-0 draw scan before CALL 7596."""
    _scan_layered_object_call(cpu, 0, 0xA8BE, 0xA8C4)


@registry.replace(0x1010, 0xA8C7, "overkill_scan_layer1_draw_a8c7")
def overkill_scan_layer1_draw_a8c7(cpu):
    """Skip non-drawing entries in the layer-1 scan before ``CALL 7596``."""
    if _self_disable_if_patched(cpu, 0xA8C7, _SIG_A8C7, "overkill_scan_layer1_draw_a8c7"):
        return

    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF

    def should_call() -> bool:
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active == 0:
            return False

        mode = cpu.mem.rw(ds, 0xBDAC)
        _cmp_word(cpu, mode, 1)
        if mode != 1:
            camera = cpu.mem.rw(ds, 0x2350)
            _cmp_word(cpu, camera, 0x00B6)
            if camera <= 0x00B6:
                layer = cpu.mem.rw(ss, (cpu.s.bp + 0x16) & 0xFFFF)
                _cmp_word(cpu, layer, 1)
                if layer == 1:
                    return False

        obj_layer = cpu.mem.rw(ss, (cpu.s.bp + 0x0A) & 0xFFFF)
        _cmp_word(cpu, obj_layer, 1)
        return obj_layer == 1

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, 0x32CA, cx_value)
        if should_call():
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = 0xA8F1
            return

        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = 0xA8F7
            return

    cpu.s.ip = 0xA8F7


def _scan_present_objects_via_5a92(
    cpu,
    *,
    table_base: int,
    done_ip: int,
    return_ip: int,
    parent: str,
    chain: str,
) -> None:
    """Skip inactive present entries up to the real ``CALL 5A92``."""
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ss = cpu.s.ss & 0xFFFF
    call_ip = (return_ip - 3) & 0xFFFF

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, table_base, cx_value)
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)

        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = call_ip
            return

        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = done_ip & 0xFFFF
            return

    cpu.s.ip = done_ip & 0xFFFF




@registry.replace(0x1010, 0x4CED, "overkill_presence_stamp_triplet_4ced")
def overkill_presence_stamp_triplet_4ced(cpu):
    """Compose the 4CED parent from three existing 4D15 presence-stamp calls."""
    if _self_disable_if_patched(cpu, 0x4CED, _SIG_4CED, "overkill_presence_stamp_triplet_4ced"):
        return
    run_presence_stamp_triplet_4ced(cpu, overkill_presence_stamp_list_4d15)


@registry.replace(0x1010, 0x4D64, "overkill_clear_presence_list_parent_4d64")
def overkill_clear_presence_list_parent_4d64(cpu):
    """Set up and tail into the shared 4D6F presence-list clear hook."""
    if _self_disable_if_patched(cpu, 0x4D64, _SIG_4D64, "overkill_clear_presence_list_parent_4d64"):
        return
    run_clear_presence_list_parent_4d64(cpu, overkill_clear_presence_list_4d6f)


@registry.replace(0x1010, 0xA93C, "overkill_present_scan_clear_presence_a93c")
def overkill_present_scan_clear_presence_a93c(cpu):
    """Model A93C: CALL 4D64 ; RET using the shared 4D64/4D6F hooks."""
    if _self_disable_if_patched(cpu, 0xA93C, _SIG_A93C, "overkill_present_scan_clear_presence_a93c"):
        return
    call_clear_presence_list_parent_a93c(cpu, overkill_clear_presence_list_parent_4d64)


@registry.replace(0x1010, 0xA90C, "overkill_present_object_scan_pair_a90c")
def overkill_present_object_scan_pair_a90c(cpu):
    """Compose the two present scans and presence-list clear without duplicating leaves."""
    if _self_disable_if_patched(cpu, 0xA90C, _SIG_A90C, "overkill_present_object_scan_pair_a90c"):
        return
    run_present_object_scan_pair_a90c(
        cpu,
        overkill_scan_objects_call_5a92_a90f,
        overkill_scan_objects_call_5a92_a927,
        overkill_clear_presence_list_parent_4d64,
    )


@registry.replace(0x1010, 0xA90F, "overkill_scan_objects_call_5a92_a90f")
def overkill_scan_objects_call_5a92_a90f(cpu):
    """Present active 8D12 objects when their Tandy targets are verified."""
    if _self_disable_if_patched(cpu, 0xA90F, _SIG_A90F, "overkill_scan_objects_call_5a92_a90f"):
        return
    _scan_present_objects_via_5a92(
        cpu,
        table_base=0x8D12,
        done_ip=0xA924,
        return_ip=0xA921,
        parent="1010:A90F",
        chain="A90F -> 5A92",
    )


@registry.replace(0x1010, 0xA927, "overkill_scan_objects_call_5a92_a927")
def overkill_scan_objects_call_5a92_a927(cpu):
    """Present active 32CA objects when their Tandy targets are verified."""
    if _self_disable_if_patched(cpu, 0xA927, _SIG_A927, "overkill_scan_objects_call_5a92_a927"):
        return
    _scan_present_objects_via_5a92(
        cpu,
        table_base=0x32CA,
        done_ip=0xA93C,
        return_ip=0xA939,
        parent="1010:A927",
        chain="A927 -> 5A92",
    )













































@registry.replace(0x1010, 0x61C7, "overkill_decrement_first_active_counter_61c7")
def overkill_decrement_first_active_counter_61c7(cpu):
    """Replace the small DS:2368..2372 countdown scan at real entry 1010:61C7."""
    run_decrement_first_active_counter_61c7(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0x61F7, "overkill_decrement_first_active_counter_loop_61f7")
def overkill_decrement_first_active_counter_loop_61f7(cpu):
    """Replace the hot CALL-61C7/LOOP glue at 1010:61F7."""
    run_decrement_first_active_counter_loop_61f7(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0x61CA, "overkill_decrement_first_active_counter_scan_61ca")
def overkill_decrement_first_active_counter_scan_61ca(cpu):
    """Replace the inner countdown scan body at 1010:61CA."""
    run_decrement_first_active_counter_scan_61ca(cpu, _self_disable_if_patched)
























































def _run_installed_tail_hook(cpu, key: tuple[int, int], fallback) -> None:
    """Run an installed hook at its natural entry without pushing a return word."""
    handler = cpu.replacement_hooks.get(key, fallback)
    name = cpu.hook_names.get(key, getattr(handler, "__name__", "replacement"))
    cpu.s.cs = key[0] & 0xFFFF
    cpu.s.ip = key[1] & 0xFFFF
    verifier = getattr(cpu, "hook_verifier", None)
    if (
        verifier is not None
        and getattr(cpu, "hook_verifier_verify_nested_calls", True)
        and key not in getattr(cpu, "hook_verifier_passthrough", set())
    ):
        verifier(cpu, key, handler, name)
    else:
        handler(cpu)

@registry.replace(0x1010, 0x6296, "overkill_status_counter_cell_blit_6296")
def overkill_status_counter_cell_blit_6296(cpu):
    """Composed status/counter cell blit helper used by the 61DC display parent."""
    def call_menu_cell_source_blit(return_ip: int) -> None:
        cs = cpu.s.cs & 0xFFFF
        mode = cpu.mem.rw(cs, 0x95BC)
        cpu.s.bx = mode & 0xFFFF
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
        if mode == 2:
            _call_installed_hook_like_near_call(cpu, (0x1010, 0x306F), overkill_tandy_rect_copy_306f, return_ip)
            return
        # 6296 has only been proven on the Tandy-first source-port path.  Other
        # video modes should be lifted explicitly rather than silently routed
        # through original-mode dispatch.
        raise RuntimeError(f"unverified 6296 source-cell blit video mode {mode:04X}")

    run_status_counter_cell_blit_6296(cpu, _self_disable_if_patched, call_menu_cell_source_blit)




@registry.replace(0x1010, 0x613E, "overkill_status_cursor_advance_613e")
def overkill_status_cursor_advance_613e(cpu):
    """Mode-dependent status/HUD cursor advance helper."""
    run_status_cursor_advance_613e(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0x615A, "overkill_status_cursor_retreat_615a")
def overkill_status_cursor_retreat_615a(cpu):
    """Mode-dependent status/HUD cursor retreat helper."""
    run_status_cursor_retreat_615a(cpu, _self_disable_if_patched)






@registry.replace(0x1010, 0xC4DB, "overkill_reset_object_slot_and_status_setup_c4db")
def overkill_reset_object_slot_and_status_setup_c4db(cpu):
    """Transition/setup parent: C4E5 object reset, C51D status setup, 859E compositor."""

    def run_c4e5_tail() -> None:
        _run_installed_tail_hook(cpu, (0x1010, 0xC4E5), overkill_reset_object_slot_block_c4e5)

    def run_c51d_tail() -> None:
        _run_installed_tail_hook(cpu, (0x1010, 0xC51D), overkill_setup_tracked_status_tail_c51d)

    def run_859e_tail() -> None:
        _run_installed_tail_hook(cpu, (0x1010, 0x859E), overkill_status_cell_quad_composite_859e)

    run_reset_object_slot_and_status_setup_c4db(
        cpu,
        _self_disable_if_patched,
        run_c4e5_tail,
        run_c51d_tail,
        run_859e_tail,
    )


@registry.replace(0x1010, 0x9908, "overkill_transition_status_wait_9908")
def overkill_transition_status_wait_9908(cpu):
    """Frame-controller transition/status reset and optional input-release wait."""

    def call_c4db(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0xC4DB),
            overkill_reset_object_slot_and_status_setup_c4db,
            return_ip,
        )

    run_transition_status_wait_9908(cpu, _self_disable_if_patched, call_c4db)



@registry.replace(0x1010, 0x9928, "overkill_transition_input_release_tail_9928")
def overkill_transition_input_release_tail_9928(cpu):
    """Post-9921 transition tail that stores BEFF and jumps back to 9773."""
    run_transition_input_release_tail_9928(cpu, _self_disable_if_patched)

@registry.replace(0x1010, 0xC51D, "overkill_setup_tracked_status_tail_c51d")
def overkill_setup_tracked_status_tail_c51d(cpu):
    """Setup tail clearing tracked/status globals before jumping to 859E."""

    def call_8517(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x8517),
            overkill_status_cell_list_seed_8517,
            return_ip,
        )

    run_setup_tracked_status_tail_c51d(cpu, _self_disable_if_patched, call_8517)

@registry.replace(0x1010, 0xC3BF, "overkill_reset_effect_slot_block_c3bf")
def overkill_reset_effect_slot_block_c3bf(cpu):
    """Internal compact/effect-slot reset loop reached by setup code."""
    run_reset_effect_slot_block_c3bf(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xC3F1, "overkill_reset_object_slot_block_c3f1")
def overkill_reset_object_slot_block_c3f1(cpu):
    """Internal object-slot reset loop reached by setup code."""
    run_reset_object_slot_block_c3f1(cpu, _self_disable_if_patched)

@registry.replace(0x1010, 0xC4E5, "overkill_reset_object_slot_block_c4e5")
def overkill_reset_object_slot_block_c4e5(cpu):
    """Internal object-slot reset loop reached by the C4DB setup routine."""
    run_reset_object_slot_block_c4e5(cpu, _self_disable_if_patched)

@registry.replace(0x1010, 0x60A2, "overkill_frame_effect_status_text_60a2")
def overkill_frame_effect_status_text_60a2(cpu):
    """Per-frame glue: 77C5 effect gate, 5F61 counters, then 5EDB text."""

    def call_effect_gate(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x77C5),
            overkill_frame_effect_gate_77c5,
            return_ip,
        )

    def call_status_counter(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x5F61),
            overkill_frame_status_counter_update_5f61,
            return_ip,
        )

    def call_status_text(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x5EDB),
            overkill_score_status_text_block_5edb,
            return_ip,
        )

    run_frame_effect_status_text_60a2(
        cpu,
        _self_disable_if_patched,
        call_effect_gate,
        call_status_counter,
        call_status_text,
    )


@registry.replace(0x1010, 0x97B2, "overkill_frame_loop_97b2")
def overkill_frame_loop_97b2(cpu):
    """One iteration of the 97B2 gameplay/attract frame controller."""
    run_frame_loop_97b2(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )


def _run_interpreted_far_call_observed(cpu, target_cs: int, target_ip: int, return_ip: int, *, max_steps: int = 20000) -> None:
    """Run a bounded original FAR CALL from inside a lifted frame parent.

    Keep nested hook verification active by default, matching the near-call
    helper.  If the far helper reaches an installed child hook, that child is
    verified at the state produced by the original bounded code instead of being
    silently shared by both sides of the parent transaction.
    """
    return_cs = cpu.s.cs & 0xFFFF
    target = (return_cs, return_ip & 0xFFFF)
    saved_verifier = cpu.hook_verifier
    if not getattr(cpu, "hook_verifier_verify_nested_calls", True):
        cpu.hook_verifier = None
    cpu.push(return_cs)
    cpu.push(return_ip & 0xFFFF)
    cpu.s.cs = target_cs & 0xFFFF
    cpu.s.ip = target_ip & 0xFFFF
    try:
        ctx = (
            cpu.coverage_telemetry.bounded_original((target_cs & 0xFFFF, target_ip & 0xFFFF), "bounded original far call")
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
        f"interpreted far helper {target_cs & 0xFFFF:04X}:{target_ip & 0xFFFF:04X} did not return to "
        f"{return_cs:04X}:{return_ip & 0xFFFF:04X}; now at {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}"
    )


@registry.replace(0x1010, 0xD367, "overkill_interstitial_status_cell_d367")
def overkill_interstitial_status_cell_d367(cpu):
    """Small interstitial/status cell source blit helper."""
    run_interstitial_status_cell_d367(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )


@registry.replace(0x1010, 0x852B, "overkill_status_cell_seed_852b")
def overkill_status_cell_seed_852b(cpu):
    """One raw status/list cell descriptor seed."""
    run_status_cell_seed_852b(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )


@registry.replace(0x1010, 0x8517, "overkill_status_cell_list_seed_8517")
def overkill_status_cell_list_seed_8517(cpu):
    """Four-entry raw status/list descriptor builder."""
    run_status_cell_list_seed_8517(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )


@registry.replace(0x1010, 0xD318, "overkill_interstitial_timed_input_loop_d318")
def overkill_interstitial_timed_input_loop_d318(cpu):
    """One ASM-shaped iteration of the D318 timed interstitial/input loop."""
    run_interstitial_timed_input_loop_d318(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
        _run_interpreted_far_call_observed,
    )


@registry.replace(0x1010, 0xD007, "overkill_main_frame_loop_d007")
def overkill_main_frame_loop_d007(cpu):
    """One original gameplay/attract frame iteration, composed from child hooks."""
    run_main_frame_loop_d007(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )

@registry.replace(0x1010, 0x073C, "overkill_frame_service_gate_073c")
def overkill_frame_service_gate_073c(cpu):
    """Tiny per-frame platform/service gate called from the D007 loop."""
    if cpu.mem.rb(cpu.s.ds & 0xFFFF, 0x9907) == 0x01:
        key = (0x1010, 0x073C)
        cpu.replacement_hooks.pop(key, None)
        cpu.hook_names.pop(key, None)
        cpu.s.ip = 0x073C
        return
    run_frame_service_gate_073c(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )


@registry.replace(0x1010, 0xD04D, "overkill_frame_ui_state_update_d04d")
def overkill_frame_ui_state_update_d04d(cpu):
    """Finite per-frame UI/demo-state update block called from D007."""
    run_frame_ui_state_update_d04d(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )


@registry.replace(0x1010, 0xA212, "overkill_demo_object_list_maintenance_a212")
def overkill_demo_object_list_maintenance_a212(cpu):
    """Hook wrapper for the cold-start/attract demo object-list maintenance glue."""
    run_demo_object_list_maintenance_a212(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )


@registry.replace(0x1010, 0x5F61, "overkill_frame_status_counter_update_5f61")
def overkill_frame_status_counter_update_5f61(cpu):
    """Hook wrapper for finite per-frame status/counter orchestration glue."""
    run_frame_status_counter_update_5f61(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )





@registry.replace(0x1010, 0x61DC, "overkill_status_display_parent_61dc")
def overkill_status_display_parent_61dc(cpu):
    """Raw status/counter display parent around 61F7, 5A00, 6296, and 5A6C."""

    def call_5a00(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x5A00),
            overkill_xy_to_di_5a00,
            return_ip,
        )

    def call_6296(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x6296),
            overkill_status_counter_cell_blit_6296,
            return_ip,
        )

    def call_5a6c(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x5A6C),
            overkill_menu_cell_source_blit_dispatch_5a6c,
            return_ip,
        )
        if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (0x1010, return_ip & 0xFFFF):
            # 5A6C is a dispatch stub whose JMP target owns the RET that consumes
            # the original 5A6C CALL frame.  Run that installed target without
            # adding another synthetic CALL word.
            handler = cpu.replacement_hooks.get((cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF))
            if handler is not None:
                handler(cpu)

    run_status_display_parent_61dc(
        cpu,
        _self_disable_if_patched,
        call_5a00,
        call_6296,
        call_5a6c,
    )


@registry.replace(0x1010, 0x6120, "overkill_status_row_repeat_6120")
def overkill_status_row_repeat_6120(cpu):
    """Repeated raw status/HUD row compositor around 5A6C and 613E."""

    def call_5a6c(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x5A6C),
            overkill_menu_cell_source_blit_dispatch_5a6c,
            return_ip,
        )
        if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (0x1010, return_ip & 0xFFFF):
            # 5A6C dispatches by JMP to the mode-specific renderer.  Run the
            # installed target without another CALL push so its RET consumes the
            # original 5A6C call frame.
            handler = cpu.replacement_hooks.get((cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF))
            if handler is not None:
                handler(cpu)

    def call_613e(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x613E),
            overkill_status_cursor_advance_613e,
            return_ip,
        )

    run_status_row_repeat_6120(cpu, _self_disable_if_patched, call_5a6c, call_613e)


@registry.replace(0x1010, 0x859E, "overkill_status_cell_quad_composite_859e")
def overkill_status_cell_quad_composite_859e(cpu):
    """Four-cell status/HUD compositor parent around 85D5 and optional 511F."""

    def call_85d5(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x85D5),
            overkill_status_cell_composite_85d5,
            return_ip,
        )

    def tail_85d5() -> None:
        key = (0x1010, 0x85D5)
        handler = cpu.replacement_hooks.get(key, overkill_status_cell_composite_85d5)
        name = cpu.hook_names.get(key, getattr(handler, "__name__", "replacement"))
        cpu.s.cs = key[0]
        cpu.s.ip = key[1]
        verifier = getattr(cpu, "hook_verifier", None)
        if (
            verifier is not None
            and getattr(cpu, "hook_verifier_verify_nested_calls", True)
            and key not in getattr(cpu, "hook_verifier_passthrough", set())
        ):
            verifier(cpu, key, handler, name)
        else:
            handler(cpu)

    def call_511f(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x511F),
            overkill_video_page_toggle_511f,
            return_ip,
        )

    run_status_cell_quad_composite_859e(cpu, _self_disable_if_patched, call_85d5, tail_85d5, call_511f)

@registry.replace(0x1010, 0x85D5, "overkill_status_cell_composite_85d5")
def overkill_status_cell_composite_85d5(cpu):
    """Low-level status/HUD cell compositor around 613E/615A and 5A6C."""

    def call_613e(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x613E),
            overkill_status_cursor_advance_613e,
            return_ip,
        )

    def call_615a(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x615A),
            overkill_status_cursor_retreat_615a,
            return_ip,
        )

    def call_5a6c(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x5A6C),
            overkill_menu_cell_source_blit_dispatch_5a6c,
            return_ip,
        )
        if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (0x1010, return_ip & 0xFFFF):
            # 5A6C is a dispatch stub: the original CALL pushes return_ip,
            # then 5A6C JMPs to the mode-specific renderer body (for Tandy,
            # usually 306F).  Execute that installed target hook without an
            # extra CALL push so the child RET consumes the original return.
            handler = cpu.replacement_hooks.get((cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF))
            if handler is None:
                return
            handler(cpu)

    run_status_cell_composite_85d5(cpu, _self_disable_if_patched, call_613e, call_615a, call_5a6c)


@registry.replace(0x1010, 0x99CD, "overkill_status_coord_list_fill_99cd")
def overkill_status_coord_list_fill_99cd(cpu):
    """Raw coordinate-list fill loop used by the 97B2/9B2E frame controller."""
    run_status_coord_list_fill_99cd(cpu, _self_disable_if_patched)




@registry.replace(0x1010, 0x9B2E, "overkill_frame_controller_9b2e")
def overkill_frame_controller_9b2e(cpu):
    """Frame-controller child around input, movement, A067, contacts, and coord rings."""
    run_frame_controller_9b2e(cpu, _self_disable_if_patched, _run_interpreted_near_call_observed)


@registry.replace(0x1010, 0x9CB6, "overkill_frame_contact_probe_fanout_9cb6")
def overkill_frame_contact_probe_fanout_9cb6(cpu):
    """Frame contact-probe fanout around 4FF9 and BEDC-gated 9E19 calls."""
    run_frame_contact_probe_fanout_9cb6(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )


@registry.replace(0x1010, 0x9E19, "overkill_post_contact_status_helper_9e19")
def overkill_post_contact_status_helper_9e19(cpu):
    """Post-contact/status counter helper reached by 9CB6 and B24D."""
    run_post_contact_status_helper_9e19(
        cpu,
        _self_disable_if_patched,
        _run_interpreted_near_call_observed,
    )


@registry.replace(0x1010, 0x9CD9, "overkill_frame_tracked_coord_store_9cd9")
def overkill_frame_tracked_coord_store_9cd9(cpu):
    """Store current object center into the frame coordinate ring."""
    run_frame_tracked_coord_store_9cd9(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0x9CF1, "overkill_frame_coord_ring_advance_9cf1")
def overkill_frame_coord_ring_advance_9cf1(cpu):
    """Advance the delayed frame coordinate-ring cursors."""
    run_frame_coord_ring_advance_9cf1(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xA031, "overkill_tracked_object_coord_pull_a031")
def overkill_tracked_object_coord_pull_a031(cpu):
    """Pull delayed coordinate-ring entries into tracked object slots."""
    run_tracked_object_coord_pull_a031(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0x9BFB, "overkill_frame_axis_count_inc_ah_9bfb")
def overkill_frame_axis_count_inc_ah_9bfb(cpu):
    """Tiny 9C01 frame-controller leaf: INC AH; RET."""
    run_frame_axis_count_inc_ah_9bfb(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0x9BFE, "overkill_frame_axis_count_inc_al_9bfe")
def overkill_frame_axis_count_inc_al_9bfe(cpu):
    """Tiny 9C01 frame-controller leaf: INC AL; RET."""
    run_frame_axis_count_inc_al_9bfe(cpu, _self_disable_if_patched)



@registry.replace(0x1010, 0x9C01, "overkill_frame_axis_condition_dispatch_9c01")
def overkill_frame_axis_condition_dispatch_9c01(cpu):
    """Frame-controller axis condition counter and jump-table child of 9B2E."""

    def call_a607(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0xA607),
            overkill_object_y_step_down_clamp_a607,
            return_ip,
        )

    def call_a5f9(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0xA5F9),
            overkill_object_y_step_up_clamp_a5f9,
            return_ip,
        )

    run_frame_axis_condition_dispatch_9c01(
        cpu,
        _self_disable_if_patched,
        call_a607,
        call_a5f9,
    )


@registry.replace(0x1010, 0x9FAF, "overkill_linked_object_coord_quad_update_9faf")
def overkill_linked_object_coord_quad_update_9faf(cpu):
    """Frame-controller linked child-coordinate parent around four 9FEA updates."""
    run_linked_object_coord_quad_update_9faf(cpu, _self_disable_if_patched)

@registry.replace(0x1010, 0xA940, "overkill_frame_game_state_update_a940")
def overkill_frame_game_state_update_a940(cpu):
    """Hook wrapper for the finite A940 per-frame game-state prelude."""
    run_frame_game_state_update_a940(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0x9FEA, "overkill_object_child_coord_update_9fea")
def overkill_object_child_coord_update_9fea(cpu):
    """Linked-object coordinate update/clamp helper."""
    run_object_child_coord_update_9fea(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xA9E0, "overkill_scan_objects_call_aa2b_a9e0")
def overkill_scan_objects_call_aa2b_a9e0(cpu):
    """Run the 32CA object-logic scan until the next unlifted concrete behavior."""
    if _self_disable_if_patched(cpu, 0xA9E0, _SIG_A9E0, "overkill_scan_objects_call_aa2b_a9e0"):
        return
    _scan_object_logic_via_aa2b(
        cpu,
        table_base=0x32CA,
        done_ip=0xAA07,
        call_ip=0xAA01,
        advance_global_counter=True,
    )


@registry.replace(0x1010, 0xAA10, "overkill_scan_objects_call_aa2b_aa10")
def overkill_scan_objects_call_aa2b_aa10(cpu):
    """Run the 8D12 object-logic scan until the next unlifted concrete behavior."""
    if _self_disable_if_patched(cpu, 0xAA10, _SIG_AA10, "overkill_scan_objects_call_aa2b_aa10"):
        return
    _scan_object_logic_via_aa2b(
        cpu,
        table_base=0x8D12,
        done_ip=0xAA25,
        call_ip=0xAA1F,
        advance_global_counter=False,
    )






@registry.replace(0x1010, 0xAA07, "overkill_second_object_scan_setup_aa07")
def overkill_second_object_scan_setup_aa07(cpu):
    """Model AA07: clear DS:2346 and set up the 8D12 AA10 object scan."""
    if _self_disable_if_patched(cpu, 0xAA07, _SIG_AA07, "overkill_second_object_scan_setup_aa07"):
        return
    cpu.mem.ww(cpu.s.ds & 0xFFFF, 0x2346, 0)
    cpu.s.cx = 0x0022
    cpu.s.ip = 0xAA10


@registry.replace(0x1010, 0xAA1F, "overkill_object_logic_call_aa2b_aa1f")
def overkill_object_logic_call_aa2b_aa1f(cpu):
    """Hook wrapper for AA10 active-entry CALL AA2B glue."""
    if _self_disable_if_patched(cpu, 0xAA1F, _SIG_AA1F, "overkill_object_logic_call_aa2b_aa1f"):
        return
    cpu.push(0xAA22)
    _run_object_logic_dispatch_aa2b(
        cpu,
        parent="1010:AA1F",
        chain="AA1F -> AA2B",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xAA22, "overkill_object_logic_scan_tail_aa22")
def overkill_object_logic_scan_tail_aa22(cpu):
    """Model AA22: POP CX ; LOOP AA10 for the 8D12 object-logic scan."""
    if _self_disable_if_patched(cpu, 0xAA22, _SIG_AA22, "overkill_object_logic_scan_tail_aa22"):
        return
    cpu.s.cx = cpu.pop()
    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xAA10 if cpu.s.cx != 0 else 0xAA25


@registry.replace(0x1010, 0xAA25, "overkill_gameplay_counter_tick_tail_aa25")
def overkill_gameplay_counter_tick_tail_aa25(cpu):
    """Model AA25: FAR CALL 1F8F:0922 ; RET using the lifted counter hook."""
    if _self_disable_if_patched(cpu, 0xAA25, _SIG_AA25, "overkill_gameplay_counter_tick_tail_aa25"):
        return
    caller_cs = cpu.s.cs & 0xFFFF
    cpu.push(caller_cs)
    cpu.push(0xAA2A)
    cpu.s.cs = 0x1F8F
    cpu.s.ip = 0x0922
    run_gameplay_counter_tick_1f8f_0922(cpu, _self_disable_if_patched)
    if (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) != (caller_cs, 0xAA2A):
        raise RuntimeError(
            f"1F8F:0922 returned to unexpected IP {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X} inside AA25 tail"
        )
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x4D6F, "overkill_clear_presence_list_4d6f")
def overkill_clear_presence_list_4d6f(cpu):
    """Replace the hot list clear at 1010:4D6F.

    It walks up to CX word entries from DS:SI, stops on FFFF, and clears the
    corresponding occupancy byte(s) in ES.  Mode CS:[95BC] == 1 clears the
    stacked +1A/+34/+4E cells as well.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    si = s.si & 0xFFFF
    count = s.cx & 0xFFFF
    if count == 0:
        count = 0x10000
    step = -2 if cpu.get_flag(DF) else 2

    while count:
        ax = mem.rw(ds, si)
        si = (si + step) & 0xFFFF
        s.ax = ax
        _cmp_word(cpu, ax, 0xFFFF)
        if ax == 0xFFFF:
            s.si = si
            s.ip = cpu.pop()
            return

        s.di = ax & 0xFFFF
        mode = mem.rw(cs, 0x95BC)
        _cmp_word(cpu, mode, 1)
        if mode == 1:
            mem.wb(es, (s.di + 0x4E) & 0xFFFF, 0)
            mem.wb(es, (s.di + 0x34) & 0xFFFF, 0)
            mem.wb(es, (s.di + 0x1A) & 0xFFFF, 0)
        mem.wb(es, s.di, 0)
        s.cx = (s.cx - 1) & 0xFFFF
        count -= 1
        if s.cx == 0:
            s.si = si
            s.ip = cpu.pop()
            return

    s.si = si
    s.ip = cpu.pop()

@registry.replace(0x1010, 0x41A6, "overkill_variable_width_interlaced_blit_41a6")
def overkill_variable_width_interlaced_blit_41a6(cpu):
    """Replace the hot variable-width interlaced row blit at 1010:41A6.

    Entry state is set up by the immediately preceding interpreted code:

        ES = CS:[9598]
        CX = row count
        BP = source bytes per row (source width word * 2)
        DS:SI = source
        ES:DI = destination

    Original loop:

        push cx
        mov  cx,bp
        rep  movsb
        sub  di,bp
        add  di,2000h
        test di,4000h
        jz   +
        add  di,C050h
        pop  cx
        loop ...
        ret

    It is the same EGA/CGA interlaced-addressing family as the already lifted
    447B and 41DA routines, but with a variable row width.
    """
    rows = cpu.s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    while rows:
        # Preserve the PUSH/POP scratch write because some oracle tests compare
        # the full 1 MiB memory image, including the word below SP.
        cpu.push(cpu.s.cx)
        cpu.s.cx = cpu.s.bp & 0xFFFF
        _rep_movsb(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, cpu.s.bp)
        _add_reg16(cpu, 7, 0x2000)
        _test_word(cpu, cpu.s.di, 0x4000)
        if not cpu.get_flag(ZF):
            _add_reg16(cpu, 7, 0xC050)
        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unaffected.
        rows -= 1

    cpu.s.ip = cpu.pop()









@registry.replace(0x1010, 0x27EB, "overkill_ega_row_driver_27eb")
def overkill_ega_row_driver_27eb(cpu):
    run_ega_row_driver_27eb(cpu)


@registry.replace(0x1010, 0x280D, "overkill_ega_load_temp_rows_280d")
def overkill_ega_load_temp_rows_280d(cpu):
    run_ega_load_temp_rows_280d(cpu)


@registry.replace(0x1010, 0x2824, "overkill_ega_expand_temp_rows_2824")
def overkill_ega_expand_temp_rows_2824(cpu):
    run_ega_expand_temp_rows_2824(cpu)


@registry.replace(0x1010, 0x291C, "overkill_ega_temp_row_copy_291c")
def overkill_ega_temp_row_copy_291c(cpu):
    run_ega_temp_row_copy_291c(cpu)


@registry.replace(0x1010, 0x2932, "overkill_ega_transparency_mask_2932")
def overkill_ega_transparency_mask_2932(cpu):
    run_ega_transparency_mask_2932(cpu)


@registry.replace(0x1010, 0x5827, "overkill_ega_planar_to_linear_copy_5827")
def overkill_ega_planar_to_linear_copy_5827(cpu):
    run_ega_planar_to_linear_copy_5827(cpu)














def _inc_mem_byte_preserve_cf(cpu, seg: int, off: int) -> None:
    old = cpu.mem.rb(seg, off)
    old_cf = cpu.get_flag(CF)
    result = old + 1
    cpu.mem.wb(seg, off, result)
    cpu.set_add_flags(old, 1, result, 8)
    cpu.set_flag(CF, old_cf)


def _run_menu_cell_source_blit_5a6c_from_cd4f(cpu) -> bool:
    """Run the 1010:CD4F -> 5A6C source blit part of the dirty-cell presenter.

    Returns True when the blit was fully lifted and execution reached CD52.
    Returns False after preparing a faithful partial continuation for an
    unlifted video-mode target (currently EGA 24D7).
    """
    cs = cpu.s.cs & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    cpu.s.bx = mode & 0xFFFF
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)

    if mode == 0:
        # 5A6C dispatches mode 0 to 4199.  4199 reads height/width, selects the
        # visible video segment, doubles the byte width into BP, then falls into
        # the already lifted 41A6 variable-width interlaced blit and RETs to CD52.
        delta = -2 if cpu.get_flag(DF) else 2
        cpu.s.ax = cpu.mem.rw(cpu.s.ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + delta) & 0xFFFF
        cpu.s.cx = cpu.s.ax & 0xFFFF
        cpu.s.ax = cpu.mem.rw(cpu.s.ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + delta) & 0xFFFF
        cpu.s.es = cpu.mem.rw(cs, 0x95A4)
        cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
        cpu.s.bp = cpu.s.ax & 0xFFFF
        _call_installed_hook_like_near_call(cpu, (0x1010, 0x41A6), overkill_variable_width_interlaced_blit_41a6, 0xCD52)
        if cpu.s.ip != 0xCD52:
            raise RuntimeError(f"41A6 returned to unexpected IP {cpu.s.ip:04X} inside CC7F presenter")
        return True

    if mode == 2:
        # 5A6C dispatches mode 2 to 306F, the lifted Tandy raw-rectangle copy.
        _call_installed_hook_like_near_call(cpu, (0x1010, 0x306F), overkill_tandy_rect_copy_306f, 0xCD52)
        if cpu.s.ip != 0xCD52:
            raise RuntimeError(f"306F returned to unexpected IP {cpu.s.ip:04X} inside CC7F presenter")
        return True

    if mode == 1:
        # EGA target 24D7 is not part of this narrow pass.  Preserve CALL 5A6C
        # semantics exactly so the original target can continue from there.
        cpu.push(0xCD52)
        cpu.s.ip = 0x24D7
        return False

    raise RuntimeError(f"unverified original-code path reached in 1010:CC7F: unknown video mode {mode:04X}")


def _run_changed_cell_present_dispatch_cd7e(cpu) -> bool:
    """Run the 1010:CD77/7E changed-cell present dispatch when lifted.

    Returns False after preparing a faithful continuation for an unlifted EGA
    presenter target.
    """
    cs = cpu.s.cs & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    cpu.s.bx = mode & 0xFFFF
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)

    if mode == 0:
        cpu.s.cx = 0x0008
        _jump_installed_hook_boundary(cpu, (0x1010, 0xCD8D), overkill_changed_word_present_8rows_cd8d)
        if cpu.s.ip != 0xCE02:
            raise RuntimeError(f"CD8D returned to unexpected IP {cpu.s.ip:04X} inside CC7F presenter")
        return True

    if mode == 2:
        cpu.s.cx = 0x0008
        _jump_installed_hook_boundary(cpu, (0x1010, 0xCDAA), overkill_tandy_changed_dword_present_8rows_cdaa)
        if cpu.s.ip != 0xCE02:
            raise RuntimeError(f"CDAA returned to unexpected IP {cpu.s.ip:04X} inside CC7F presenter")
        return True

    if mode == 1:
        cpu.s.ip = 0xCDCC
        return False

    raise RuntimeError(f"unverified original-code path reached in 1010:CC7F: unknown changed-present mode {mode:04X}")


def _finish_dirty_cell_presenter_row_loop_ce07(cpu) -> None:
    ds = cpu.s.ds & 0xFFFF
    _inc_mem_byte_preserve_cf(cpu, ds, 0xBD95)
    cpu.s.cx = cpu.pop()
    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP does not alter flags.
    cpu.s.ip = 0xCC7F if cpu.s.cx != 0 else 0xCE13


def _run_dirty_cell_presenter_row_cc7f_once(cpu) -> None:
    if _self_disable_if_patched(cpu, 0xCC7F, _SIG_CC7F, "overkill_dirty_cell_presenter_row_cc7f"):
        return
    """Fuse one row iteration of the CC4F/CC58 dirty-cell presenter.

    The surrounding routine pushes an outer rectangle count and jumps back to
    CC7F once per dirty-cell row.  This hook owns the hot row body:

      CC7F..CC9E  compute work-buffer source/destination and dispatch dirty copy
      CCAA/CCF0/CCC4 compare/copy back-buffer cells, setting DL when changed
      CD08..CD7E  if changed, draw the source cell and present it to video
      CE02..CE10  restore DS, increment row coordinate, LOOP to CC7F or CE13

    EGA's source/presenter leaves are still not part of this pass; when mode 1
    reaches an unlifted target the hook leaves a faithful partial continuation
    at the original target with the expected return word on the stack.
    """
    cs = cpu.s.cs & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    # CC7F push cx; mov ax,[BD95]; call 5A24
    cpu.push(cpu.s.cx)
    cpu.s.ax = mem.rw(ds, 0xBD95)
    _call_installed_hook_like_near_call(cpu, (0x1010, 0x5A24), overkill_xy_to_di_5a24, 0xCC86)
    if cpu.s.ip != 0xCC86:
        raise RuntimeError(f"5A24 returned to unexpected IP {cpu.s.ip:04X} inside CC7F presenter")

    # CC86..CC9E prepare dirty-copy dispatch.
    ds = cpu.s.ds & 0xFFFF
    mem.ww(ds, 0xBD9E, cpu.s.di)
    cpu.s.si = cpu.s.di & 0xFFFF
    _add_reg16(cpu, 6, 0x7D00)
    cpu.set_reg8(2, 0)            # XOR DL,DL
    cpu.set_logic_flags(0, 8)
    cpu.s.es = mem.rw(cs, 0x9598)
    mode = mem.rw(cs, 0x95BC)
    cpu.s.bx = mode & 0xFFFF
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)

    if mode == 0:
        _jump_installed_hook_boundary(cpu, (0x1010, 0xCCAA), overkill_dirty_copy_mode1_ccaa)
    elif mode == 1:
        _jump_installed_hook_boundary(cpu, (0x1010, 0xCCF0), overkill_dirty_copy_mode2_ccf0)
    elif mode == 2:
        _jump_installed_hook_boundary(cpu, (0x1010, 0xCCC4), overkill_dirty_copy_mode3_ccc4)
    else:
        raise RuntimeError(f"unverified original-code path reached in 1010:CC7F: unknown dirty-copy mode {mode:04X}")
    if cpu.s.ip != 0xCD08:
        raise RuntimeError(f"dirty-copy target returned to unexpected IP {cpu.s.ip:04X} inside CC7F presenter")

    # CD08 OR DL,DL; unchanged cells skip the expensive source draw/present.
    dl = cpu.s.dx & 0x00FF
    cpu.set_logic_flags(dl, 8)
    if dl != 0:
        # CD0F..CD37 optional cursor/status byte selected by row group and flag.
        ds = cpu.s.ds & 0xFFFF
        bda0 = mem.rw(ds, 0xBDA0)
        _cmp_word(cpu, bda0, 0x0004)
        status_enabled = mem.rb(ds, 0x98C0)
        if bda0 == 0x0004:
            _cmp_byte(cpu, status_enabled, 0)
            if status_enabled != 0:
                mem.wb(ds, 0xBEFF, 0x0A)
        else:
            _cmp_byte(cpu, status_enabled, 0)
            if status_enabled != 0:
                _cmp_byte(cpu, status_enabled, 0)  # The original repeats this CMP before the MOV.
                mem.wb(ds, 0xBEFF, 0x0E)

        # CD37..CD52 draw the changed source cell to the visible video segment.
        cpu.s.ax = mem.rw(ds, 0xBD95)
        _call_installed_hook_like_near_call(cpu, (0x1010, 0x5A00), overkill_xy_to_di_5a00, 0xCD3D)
        if cpu.s.ip != 0xCD3D:
            raise RuntimeError(f"5A00 returned to unexpected IP {cpu.s.ip:04X} inside CC7F presenter")
        cpu.push(cpu.s.di)
        cpu.s.si = 0x0012
        cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)
        _add_reg16(cpu, 6, 0x0C92)
        cpu.s.si = mem.rw(cs, cpu.s.si)
        cpu.s.ds = mem.rw(cs, 0x95B8)
        if not _run_menu_cell_source_blit_5a6c_from_cd4f(cpu):
            return

        # CD52..CD68 optional retrace wait before presenting the changed cell.
        cpu.s.ds = mem.rw(cs, 0x9596)
        ds = cpu.s.ds & 0xFFFF
        bda0 = mem.rw(ds, 0xBDA0)
        _cmp_word(cpu, bda0, 0x0005)
        if bda0 != 0x0005:
            flag = mem.rb(ds, 0x98C3)
            _cmp_byte(cpu, flag, 0)
            if flag == 0:
                # ip is 0xCD52 here (the CALL site in original ASM); preserve it so
                # play.py's pacing wrapper can detect this specific call context.
                _call_installed_hook_like_near_call(
                    cpu,
                    (0x1010, 0x50C9),
                    overkill_wait_vga_retrace_50c9,
                    0xCD68,
                )
                if cpu.s.ip != 0xCD68:
                    raise RuntimeError(f"50C9 returned to unexpected IP {cpu.s.ip:04X} inside CC7F presenter")

        # CD68..CE02 present the dirty cell from the work/front buffer.
        cpu.s.di = cpu.pop()
        cpu.s.si = mem.rw(ds, 0xBD9E)
        cpu.s.es = mem.rw(cs, 0x95A4)
        cpu.s.ds = mem.rw(cs, 0x9598)
        if not _run_changed_cell_present_dispatch_cd7e(cpu):
            return
        cpu.s.ds = mem.rw(cs, 0x9596)

    _finish_dirty_cell_presenter_row_loop_ce07(cpu)


def _run_dirty_cell_presenter_resume_cd68(cpu) -> None:
    """Resume the CC7F dirty-cell presenter after the pacing wait at CD68.

    The full CC7F hook intentionally calls the installed 50C9 wait hook on the
    nested ``CD52 -> 50C9 -> CD68`` path.  In interactive play that wrapper may
    publish/yield the frame and leave IP at CD68.  This helper owns the remaining
    original tail so the UI pacing boundary stays visible while the hot
    ``CD68..CE10`` presenter code is still lifted and classified.
    """
    if _self_disable_if_patched(cpu, 0xCD68, _SIG_CD68, "overkill_dirty_cell_presenter_resume_cd68"):
        return
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    ds = cpu.s.ds & 0xFFFF

    # CD68..CD7E: restore the changed cell destination and dispatch the
    # mode-specific presenter.  This is the same tail used by the fused CC7F
    # path after the optional retrace wait returns normally.
    cpu.s.di = cpu.pop()
    cpu.s.si = mem.rw(ds, 0xBD9E)
    cpu.s.es = mem.rw(cs, 0x95A4)
    cpu.s.ds = mem.rw(cs, 0x9598)
    if not _run_changed_cell_present_dispatch_cd7e(cpu):
        return

    # CE02..CE10: restore display DS, increment the row cursor, pop the saved
    # row counter and loop back to CC7F or exit at CE13.  LOOP does not alter
    # flags; the byte INC preserves CF.
    cpu.s.ds = mem.rw(cs, 0x9596)
    _finish_dirty_cell_presenter_row_loop_ce07(cpu)


@registry.replace(0x1010, 0xCD68, "overkill_dirty_cell_presenter_resume_cd68")
def overkill_dirty_cell_presenter_resume_cd68(cpu):
    """Replace the post-retrace dirty-cell presenter tail at 1010:CD68."""
    _run_dirty_cell_presenter_resume_cd68(cpu)


def _run_menu_transition_input_wait_ce40(cpu) -> None:
    """Run the CE40 menu/transition input-poll + retrace wait subroutine.

    This routine is reached after a dirty-cell panel has finished presenting.
    It polls the input bitfield through the already lifted 0162 input poller,
    optionally latches the Space/fire scancode into DS:98C3, and waits on the
    installed 50C9 retrace boundary up to CX times.  The installed 50C9 hook is
    used intentionally so interactive play can still publish/yield at each
    original wait; if that happens, execution resumes at the CE5C LOOP tail.
    """
    if _self_disable_if_patched(cpu, 0xCE40, _SIG_CE40, "overkill_menu_transition_input_wait_ce40"):
        return
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    while True:
        key = mem.rb(ds, 0x98C3)
        _cmp_byte(cpu, key, 0)
        if key != 0:
            cpu.s.ip = cpu.pop()
            return

        cpu.push(cpu.s.cx)
        _call_installed_hook_like_near_call(cpu, (0x1010, 0x0162), overkill_input_poll_0162, 0xCE4C)
        if cpu.s.ip != 0xCE4C:
            raise RuntimeError(f"0162 returned to unexpected IP {cpu.s.ip:04X} inside CE40 input wait")
        cpu.s.cx = cpu.pop()

        buttons = mem.rb(ds, 0x98BE)
        cpu.set_logic_flags(buttons & 0x10, 8)  # TEST byte [98BE],10h
        if buttons & 0x10:
            mem.wb(ds, 0x98C3, 0x39)

        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x50C9),
            overkill_wait_vga_retrace_50c9,
            0xCE5C,
        )
        if cpu.s.ip != 0xCE5C:
            raise RuntimeError(f"50C9 returned to unexpected IP {cpu.s.ip:04X} inside CE40 input wait")

        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP preserves flags.
        if cpu.s.cx != 0:
            continue
        cpu.s.ip = cpu.pop()
        return


def _run_menu_transition_input_wait_loop_ce5c(cpu) -> None:
    """Resume CE40 after an interactive 50C9 pacing boundary returned at CE5C."""
    if _self_disable_if_patched(cpu, 0xCE5C, _SIG_CE5C, "overkill_menu_transition_input_wait_loop_ce5c"):
        return
    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP does not alter flags.
    cpu.s.ip = 0xCE40 if cpu.s.cx != 0 else cpu.pop()


def _run_menu_script_input_wait_cf78(cpu) -> None:
    """Run the CF78 retrace/input wait loop to its in-procedure continuation.

    CF78 is not a normal near subroutine entry; it is a loop body inside the
    menu/script presenter.  It waits up to CX retraces, polling input once per
    retrace.  Space/fire in DS:98BE or the latched DS:98C3 byte exits early at
    CF97; loop exhaustion falls through to CF90.
    """
    if _self_disable_if_patched(cpu, 0xCF78, _SIG_CF78, "overkill_menu_script_input_wait_cf78"):
        return

    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    while True:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x50C9),
            overkill_wait_vga_retrace_50c9,
            0xCF7B,
        )
        if cpu.s.ip != 0xCF7B:
            raise RuntimeError(f"50C9 returned to unexpected IP {cpu.s.ip:04X} inside CF78 input wait")

        cpu.push(cpu.s.cx)
        _call_installed_hook_like_near_call(cpu, (0x1010, 0x0162), overkill_input_poll_0162, 0xCF7F)
        if cpu.s.ip != 0xCF7F:
            raise RuntimeError(f"0162 returned to unexpected IP {cpu.s.ip:04X} inside CF78 input wait")
        cpu.s.cx = cpu.pop()

        buttons = mem.rb(ds, 0x98BE)
        cpu.set_logic_flags(buttons & 0x10, 8)
        if buttons & 0x10:
            cpu.s.ip = 0xCF97
            return

        latched = mem.rb(ds, 0x98C3)
        _cmp_byte(cpu, latched, 0)
        if latched != 0:
            cpu.s.ip = 0xCF97
            return

        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP preserves flags.
        if cpu.s.cx != 0:
            continue
        cpu.s.ip = 0xCF90
        return


@registry.replace(0x1010, 0xCF78, "overkill_menu_script_input_wait_cf78")
def overkill_menu_script_input_wait_cf78(cpu):
    """Replace the CF78 retrace/input wait loop body."""
    _run_menu_script_input_wait_cf78(cpu)


@registry.replace(0x1010, 0xCE40, "overkill_menu_transition_input_wait_ce40")
def overkill_menu_transition_input_wait_ce40(cpu):
    """Replace the CE40 input-poll/retrace wait subroutine."""
    _run_menu_transition_input_wait_ce40(cpu)


@registry.replace(0x1010, 0xCE5C, "overkill_menu_transition_input_wait_loop_ce5c")
def overkill_menu_transition_input_wait_loop_ce5c(cpu):
    """Replace the CE5C LOOP/RET tail used when 50C9 pacing yields."""
    _run_menu_transition_input_wait_loop_ce5c(cpu)



@registry.replace(0x1010, 0xCC7F, "overkill_dirty_cell_presenter_row_cc7f")
def overkill_dirty_cell_presenter_row_cc7f(cpu):
    """Run CC7F row iterations until the original inner LOOP exits.

    A verifier target cannot be the hook entry itself, so this wrapper consumes
    the CC7F -> ... -> CE10 -> CC7F loop internally and stops only when the
    original reaches CE13, or at an explicitly preserved unlifted EGA target.
    """
    while True:
        _run_dirty_cell_presenter_row_cc7f_once(cpu)
        if cpu.s.ip == 0xCC7F:
            continue
        return

@registry.replace(0x1010, 0xCCAA, "overkill_dirty_copy_mode1_ccaa")
def overkill_dirty_copy_mode1_ccaa(cpu):
    if _self_disable_if_patched(cpu, 0xCCAA, _SIG_CCAA, "overkill_dirty_copy_mode1_ccaa"):
        return
    """Replace dirty detect/copy mode 1 at 1010:CCAA.

    Compares eight ES:SI words against ES:DI with an 80-byte stride.  Changed
    words are copied and DL is set to 1.  The surrounding dispatcher at CC90
    sets ES and clears DL before jumping here; the continuation at CD08 tests DL.
    """
    cpu.s.cx = 0x0008
    while cpu.s.cx != 0:
        src = cpu.mem.rw(cpu.s.es, cpu.s.si)
        dst = cpu.mem.rw(cpu.s.es, cpu.s.di)
        cpu.s.ax = src
        _cmp_word(cpu, src, dst)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.ww(cpu.s.es, cpu.s.di, src)
        _add_reg16(cpu, 7, 0x0050)
        _add_reg16(cpu, 6, 0x0050)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xCD08


@registry.replace(0x1010, 0xCCC4, "overkill_dirty_copy_mode3_ccc4")
def overkill_dirty_copy_mode3_ccc4(cpu):
    if _self_disable_if_patched(cpu, 0xCCC4, _SIG_CCC4, "overkill_dirty_copy_mode3_ccc4"):
        return
    """Replace dirty detect/copy mode 3 at 1010:CCC4.

    Eight iterations, comparing/copying two adjacent words per row, then
    stepping source/destination by 160 bytes.
    """
    cpu.s.cx = 0x0008
    while cpu.s.cx != 0:
        src0 = cpu.mem.rw(cpu.s.es, cpu.s.si)
        dst0 = cpu.mem.rw(cpu.s.es, cpu.s.di)
        cpu.s.ax = src0
        _cmp_word(cpu, src0, dst0)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.ww(cpu.s.es, cpu.s.di, src0)

        src1 = cpu.mem.rw(cpu.s.es, (cpu.s.si + 2) & 0xFFFF)
        dst1 = cpu.mem.rw(cpu.s.es, (cpu.s.di + 2) & 0xFFFF)
        cpu.s.ax = src1
        _cmp_word(cpu, src1, dst1)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.ww(cpu.s.es, (cpu.s.di + 2) & 0xFFFF, src1)

        _add_reg16(cpu, 7, 0x00A0)
        _add_reg16(cpu, 6, 0x00A0)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xCD08


@registry.replace(0x1010, 0xCCF0, "overkill_dirty_copy_mode2_ccf0")
def overkill_dirty_copy_mode2_ccf0(cpu):
    if _self_disable_if_patched(cpu, 0xCCF0, _SIG_CCF0, "overkill_dirty_copy_mode2_ccf0"):
        return
    """Replace dirty detect/copy mode 2 at 1010:CCF0.

    Compares 32 ES:SI bytes against ES:DI with a 40-byte stride.
    """
    cpu.s.cx = 0x0020
    while cpu.s.cx != 0:
        src = cpu.mem.rb(cpu.s.es, cpu.s.si)
        dst = cpu.mem.rb(cpu.s.es, cpu.s.di)
        cpu.set_reg8(0, src)
        _cmp_byte(cpu, src, dst)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.wb(cpu.s.es, cpu.s.di, src)
        _add_reg16(cpu, 7, 0x0028)
        _add_reg16(cpu, 6, 0x0028)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xCD08


@registry.replace(0x1010, 0x2750, "overkill_present_ega_frame_2750")
def overkill_present_ega_frame_2750(cpu):
    run_present_ega_frame_2750(cpu)


@registry.replace(0x1010, 0x50C9, "overkill_wait_vga_retrace_50c9")
def overkill_wait_vga_retrace_50c9(cpu):
    """Replace the C9EA VGA retrace wait wrapper reached through 50C9.

    The original code is not a high-level timer; it performs two busy-waits on
    port 03DAh, with the order controlled by CS:CA5A.  The hook still reads the
    port through the DOS/video IO layer so vga_status_reads and final AL/flags
    remain oracle-relative.
    """
    cs = cpu.s.cs & 0xFFFF
    inverted_order = cpu.mem.rb(cs, 0xCA5A) == 0x01
    _wait_vga_status_bit3(cpu, want_set=not inverted_order)
    _wait_vga_status_bit3(cpu, want_set=inverted_order)
    cpu.s.ip = cpu.pop()


def _wait_vga_status_bit3(cpu, *, want_set: bool) -> None:
    cpu.s.dx = 0x03DA
    # Keep a guard for testability if a runtime accidentally has no IO layer.
    for _ in range(100000):
        value = cpu.port_reader(cpu, 0x03DA, 8) if cpu.port_reader else (0x08 if want_set else 0x00)
        cpu.set_reg8(0, value)
        result = value & 0x08
        cpu.set_logic_flags(result, 8)  # TEST AL,08h
        if (result != 0) == want_set:
            return
    raise RuntimeError("VGA status wait did not converge")

@registry.replace(0x1010, 0x58DF, "overkill_postcopy_blit_wait_loop_58df")
def overkill_postcopy_blit_wait_loop_58df(cpu):
    if _self_disable_if_patched(cpu, 0x58DF, _SIG_58DF, "overkill_postcopy_blit_wait_loop_58df"):
        return
    """Replace the narrow 58DF..58F8 post-copy blit/wait loop.

    This is still a control-flow hook, not a new renderer: for the captured
    mode-0 path it repeatedly invokes the already verified 497A blitter and the
    verified 50C9 VGA wait hook, preserving the PUSH/CALL/POP stack scratches
    and the unusual DEC CX + LOOP CX double-decrement.
    """
    cs = cpu.s.cs & 0xFFFF
    if cpu.mem.rw(cs, 0x95BC) != 0:
        # This lift is only proven for the mode-0 blitter.  Disable before any
        # setup side effects so the original mode-1/2 code resumes at the exact
        # entry state.
        cpu.replacement_hooks.pop((cs, 0x58DF), None)
        cpu.hook_names.pop((cs, 0x58DF), None)
        cpu.s.ip = 0x58DF
        return

    while True:
        cpu.push(cpu.s.cx)                         # 58DF PUSH CX
        cpu.mem.ww(cs, 0x5901, cpu.s.cx)           # 58E0 MOV CS:[5901],CX
        mode = cpu.mem.rw(cs, 0x95BC)
        cpu.s.bx = mode & 0xFFFF
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)   # 58E5..58EA
        _call_installed_hook_like_near_call(cpu, (0x1010, 0x497A), overkill_blit_scaled_column_block_497a, 0x58F1)
        if cpu.s.ip != 0x58F1:
            raise RuntimeError(f"497A replacement returned to unexpected IP {cpu.s.ip:04X}")
        _call_installed_hook_like_near_call(cpu, (0x1010, 0x50C9), overkill_wait_vga_retrace_50c9, 0x58F4)
        if cpu.s.ip != 0x58F4:
            raise RuntimeError(f"50C9 replacement returned to unexpected IP {cpu.s.ip:04X}")
        cpu.s.cx = cpu.pop()                       # 58F4 POP CX
        _dec_reg16_preserve_cf(cpu, 1)             # 58F5 DEC CX
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF         # 58F6 LOOP, no flags
        if cpu.s.cx == 0:
            cpu.s.ip = 0x58F8
            return




@registry.replace(0x1010, 0x511F, "overkill_video_page_toggle_511f")
def overkill_video_page_toggle_511f(cpu):
    run_video_page_toggle_511f(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0x5BDC, "overkill_present_frame_dispatch_5bdc")
def overkill_present_frame_dispatch_5bdc(cpu):
    """Lift the per-frame video-mode dispatch stub before the mode presenter."""
    if _self_disable_if_patched(cpu, 0x5BDC, _SIG_5BDC, "overkill_present_frame_dispatch_5bdc"):
        return
    cs = cpu.s.cs & 0xFFFF
    cpu.s.bx = cpu.mem.rw(cs, 0x95BC)
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
    cpu.s.ip = cpu.mem.rw(cs, (0x5BE8 + cpu.s.bx) & 0xFFFF)


@registry.replace(0x1010, 0x5C74, "overkill_tandy_postcopy_mode_sweep_5c74")
def overkill_tandy_postcopy_mode_sweep_5c74(cpu):
    """Absorb the Tandy postcopy dispatch/wait loop that feeds the 375B leaf."""
    if _self_disable_if_patched(cpu, 0x5C74, _SIG_5C74, "overkill_tandy_postcopy_mode_sweep_5c74"):
        return

    cs = cpu.s.cs & 0xFFFF
    while True:
        mode = cpu.mem.rw(cs, 0x95BC) & 0xFFFF
        cpu.s.bx = mode & 0xFFFF
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
        target = cpu.mem.rw(cs, (0x595A + ((mode & 0xFFFF) << 1)) & 0xFFFF) & 0xFFFF
        if target == 0x497A:
            _call_installed_hook_like_near_call(
                cpu,
                (0x1010, 0x497A),
                overkill_blit_scaled_column_block_497a,
                0x5C80,
            )
        elif target == 0x375B:
            _call_installed_hook_like_near_call(
                cpu,
                (0x1010, 0x375B),
                overkill_tandy_postcopy_scaled_blit_375b,
                0x5C80,
            )
        else:
            cpu.push(0x5C80)
            cpu.s.ip = target
            return
        if cpu.s.ip != 0x5C80:
            raise RuntimeError(f"5C74 mode sweep target returned to unexpected IP {cpu.s.ip:04X}")

        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x50C9),
            overkill_wait_vga_retrace_50c9,
            0x5C83,
        )
        if cpu.s.ip != 0x5C83:
            raise RuntimeError(f"5C74 wait hook returned to unexpected IP {cpu.s.ip:04X}")

        _add_mem_word(cpu, cs, 0x5901, 0x0002)
        cpu.s.ax = cpu.mem.rw(cs, 0x5901)
        _cmp_word(cpu, cpu.s.ax, cpu.mem.rw(cs, 0x58FD))
        if cpu.s.ax != cpu.mem.rw(cs, 0x58FD):
            continue
        cpu.s.ds = cpu.mem.rw(cs, 0x9596)
        cpu.s.ip = cpu.pop()
        return


@registry.replace(0x1010, 0x5160, "overkill_ega_display_start_wait_5160")
def overkill_ega_display_start_wait_5160(cpu):
    run_ega_display_start_wait_5160(cpu)


@registry.replace(0x1010, 0x3354, "overkill_present_tandy_frame_3354")
def overkill_present_tandy_frame_3354(cpu):
    """Hook wrapper for OVERKILL 1010:3354 Tandy frame-present blit."""
    run_present_tandy_frame_3354(cpu)


@registry.replace(0x1010, 0x447B, "overkill_present_frame_blit_447b")
def overkill_present_frame_blit_447b(cpu):
    """Replace the mode-0 frame-present blit reached via the 5BDC video jump table.

    The per-frame presenter ``1010:5BDC`` reads the mode selector ``CS:[95BC]``,
    shifts it left and ``jmp cs:[bx+5BE8]``.  For mode 0 the table entry is
    ``1010:447B``:

        447B  mov si, ds:[234C]      ; source cursor (work-buffer offset)
        447F  mov es, cs:[95A4]      ; destination segment (B800 video memory)
        4484  mov ds, cs:[9598]      ; source segment (decoded work buffer)
        4489  mov bx,1Ah / di,A0h / bp,C0h
        4492  mov cx,bx
              rep movsw              ; copy 1Ah (26) words = 52 bytes
              sub di,34h             ; rewind to row start
              add di,2000h           ; next interlaced scanline bank
              test di,4000h
              jz  44A7
              add di,C050h           ; wrap to next char row on bank crossing
        44A7  dec bp
              jnz 4492               ; C0h (192) rows
        44AA  mov ds, cs:[9596]      ; restore the game data segment
        44AF  ret

    Confirmed selectors in the live run: dest ``CS:[95A4]=B800h`` (CGA/EGA video
    memory), source ``CS:[9598]`` = the decoded work buffer, restore
    ``CS:[9596]`` = the game data segment.  This is the actual screen present and,
    once the main loop runs, the single hottest interpreted routine.

    The hook mirrors the interpreter's own helpers in the exact instruction order
    so registers, flags and memory match the oracle; it only collapses the Python
    per-iteration overhead of the 192-row interlaced copy.
    """
    cs = cpu.s.cs & 0xFFFF
    # 447B MOV SI, DS:[234C] (uses the entry DS before it is reloaded below).
    cpu.s.si = cpu.mem.rw(cpu.s.ds, 0x234C)
    # 447F/4484 load the destination and source segments from the resident selectors.
    cpu.s.es = cpu.mem.rw(cs, 0x95A4)
    cpu.s.ds = cpu.mem.rw(cs, 0x9598)
    # 4489..448F constants.
    cpu.s.bx = 0x001A
    cpu.s.di = 0x00A0
    cpu.s.bp = 0x00C0
    while True:
        cpu.s.cx = cpu.s.bx & 0xFFFF       # 4492 MOV CX,BX
        _rep_movsw(cpu, cpu.s.cx)          # 4494 REP MOVSW (sets CX=0, advances SI/DI)
        _sub_reg16(cpu, 7, 0x0034)         # 4496 SUB DI,34h
        _add_reg16(cpu, 7, 0x2000)         # 4499 ADD DI,2000h
        _test_word(cpu, cpu.s.di, 0x4000)  # 449D TEST DI,4000h
        if not cpu.get_flag(ZF):           # 44A1 JZ 44A7
            _add_reg16(cpu, 7, 0xC050)     # 44A3 ADD DI,C050h
        _dec_reg16_preserve_cf(cpu, 5)     # 44A7 DEC BP (CF unaffected on 8086)
        if cpu.get_flag(ZF):               # 44A8 JNZ 4492
            break
    cpu.s.ds = cpu.mem.rw(cs, 0x9596)      # 44AA MOV DS,CS:[9596]
    cpu.s.ip = cpu.pop()                   # 44AF RET



@registry.replace(0x1010, 0x986E, "overkill_input_release_wait_gate_986e")
def overkill_input_release_wait_gate_986e(cpu):
    """One-iteration state-machine hook for the 986E input-release wait."""
    if _self_disable_if_patched(cpu, 0x986E, _SIG_986E, "overkill_input_release_wait_gate_986e"):
        return
    run_input_release_wait_gate_986e(cpu)


@registry.replace(0x1010, 0x989E, "overkill_yes_no_choice_wait_gate_989e")
def overkill_yes_no_choice_wait_gate_989e(cpu):
    """One-iteration state-machine hook for the 989E Y/N choice wait."""
    if _self_disable_if_patched(cpu, 0x989E, _SIG_989E, "overkill_yes_no_choice_wait_gate_989e"):
        return
    run_yes_no_choice_wait_gate_989e(cpu)


@registry.replace(0x1010, 0x98D8, "overkill_sound_effect_completion_wait_gate_98d8")
def overkill_sound_effect_completion_wait_gate_98d8(cpu):
    """One-iteration state-machine hook for the 98D8 completion wait."""
    if _self_disable_if_patched(cpu, 0x98D8, _SIG_98D8, "overkill_sound_effect_completion_wait_gate_98d8"):
        return
    run_sound_effect_completion_wait_gate_98d8(cpu)


@registry.replace(0x1010, 0x07C4, "overkill_boss_key_f9_release_wait_gate_07c4")
def overkill_boss_key_f9_release_wait_gate_07c4(cpu):
    """One-iteration state-machine hook for the boss-key F9-release wait."""
    if _self_disable_if_patched(cpu, 0x07C4, _SIG_07C4, "overkill_boss_key_f9_release_wait_gate_07c4"):
        return
    run_boss_key_f9_release_wait_gate_07c4(cpu)


@registry.replace(0x1010, 0x07D0, "overkill_boss_key_any_key_wait_gate_07d0")
def overkill_boss_key_any_key_wait_gate_07d0(cpu):
    """One-iteration state-machine hook for the boss-key any-key wait."""
    if _self_disable_if_patched(cpu, 0x07D0, _SIG_07D0, "overkill_boss_key_any_key_wait_gate_07d0"):
        return
    run_boss_key_any_key_wait_gate_07d0(cpu)


@registry.replace(0x1010, 0x07D7, "overkill_boss_key_return_key_release_wait_gate_07d7")
def overkill_boss_key_return_key_release_wait_gate_07d7(cpu):
    """One-iteration state-machine hook for the boss-key return-key-release wait."""
    if _self_disable_if_patched(cpu, 0x07D7, _SIG_07D7, "overkill_boss_key_return_key_release_wait_gate_07d7"):
        return
    run_boss_key_return_key_release_wait_gate_07d7(cpu)


@registry.replace(0x1010, 0x53C9, "overkill_text_entry_prompt_loop_53c9")
def overkill_text_entry_prompt_loop_53c9(cpu):
    """Run one interactive DOS text-entry prompt iteration."""
    if _self_disable_if_patched(cpu, 0x53C9, _SIG_53C9, "overkill_text_entry_prompt_loop_53c9"):
        return

    def call_text_string(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x518C),
            overkill_text_string_loop_518c,
            return_ip,
        )

    def call_prompt_key_read(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x5497),
            overkill_text_prompt_key_read_5497,
            return_ip,
        )

    run_text_entry_prompt_loop_53c9(cpu, call_text_string, call_prompt_key_read)


@registry.replace(0x1010, 0x50AB, "overkill_keyboard_state_clear_and_bios_tail_sync_50ab")
def overkill_keyboard_state_clear_and_bios_tail_sync_50ab(cpu):
    """Clear OVERKILL key-state bytes and flush the BIOS keyboard buffer tail."""
    if _self_disable_if_patched(cpu, 0x50AB, _SIG_50AB, "overkill_keyboard_state_clear_and_bios_tail_sync_50ab"):
        return
    run_keyboard_state_clear_and_bios_tail_sync_50ab(cpu)


@registry.replace(0x1010, 0x50BA, "overkill_bios_keyboard_buffer_tail_sync_50ba")
def overkill_bios_keyboard_buffer_tail_sync_50ba(cpu):
    """Flush BIOS keyboard buffer tail to head after menu/prompt input."""
    if _self_disable_if_patched(cpu, 0x50BA, _SIG_50BA, "overkill_bios_keyboard_buffer_tail_sync_50ba"):
        return
    run_bios_keyboard_buffer_tail_sync_50ba(cpu)


@registry.replace(0x1010, 0x4E9F, "overkill_temp_keyboard_vector_install_4e9f")
def overkill_temp_keyboard_vector_install_4e9f(cpu):
    """Install OVERKILL's temporary INT 9 handler for DOS text input."""
    if _self_disable_if_patched(cpu, 0x4E9F, _SIG_4E9F, "overkill_temp_keyboard_vector_install_4e9f"):
        return
    run_temp_keyboard_vector_install_4e9f(cpu)


@registry.replace(0x1010, 0x4EBF, "overkill_temp_keyboard_vector_restore_4ebf")
def overkill_temp_keyboard_vector_restore_4ebf(cpu):
    """Restore the INT 9 vector saved by the temporary text-input handler."""
    if _self_disable_if_patched(cpu, 0x4EBF, _SIG_4EBF, "overkill_temp_keyboard_vector_restore_4ebf"):
        return
    run_temp_keyboard_vector_restore_4ebf(cpu)


@registry.replace(0x1010, 0x5497, "overkill_text_prompt_key_read_5497")
def overkill_text_prompt_key_read_5497(cpu):
    """Read one DOS key for the text-entry prompt with temporary INT 9 restore/install."""
    if _self_disable_if_patched(cpu, 0x5497, _SIG_5497, "overkill_text_prompt_key_read_5497"):
        return
    run_text_prompt_key_read_5497(cpu)


@registry.replace(0x1010, 0x96C5, "overkill_intro_retrace_delay_loop_96c5")
def overkill_intro_retrace_delay_loop_96c5(cpu):
    """Replace the intro/menu CALL 50C9 + LOOP delay body at 1010:96C5."""
    if _self_disable_if_patched(cpu, 0x96C5, _SIG_96C5, "overkill_intro_retrace_delay_loop_96c5"):
        return

    def call_retrace_wait(return_ip: int) -> None:
        _call_installed_hook_like_near_call(
            cpu,
            (0x1010, 0x50C9),
            overkill_wait_vga_retrace_50c9,
            return_ip,
        )

    run_intro_retrace_delay_loop_96c5(cpu, call_retrace_wait)


@registry.replace(0x1010, 0x96C8, "overkill_intro_retrace_delay_loop_tail_96c8")
def overkill_intro_retrace_delay_loop_tail_96c8(cpu):
    """Replace the 1010:96C8 LOOP tail used after an interactive 50C9 yield."""
    if _self_disable_if_patched(cpu, 0x96C8, _SIG_96C8, "overkill_intro_retrace_delay_loop_tail_96c8"):
        return
    run_intro_retrace_delay_loop_tail_96c8(cpu)

@registry.replace(0x1010, 0x0162, "overkill_input_poll_0162")
def overkill_input_poll_0162(cpu):
    """Replace the full keyboard/joystick input poller at 1010:0162."""
    run_input_poll_0162(cpu)


@registry.replace(0x1010, 0x558B, "overkill_main_menu_idle_loop_558b")
def overkill_main_menu_idle_loop_558b(cpu):
    """Replace one hot no-key iteration of the main-menu idle loop."""
    if _self_disable_if_patched(cpu, 0x558B, _SIG_558B, "overkill_main_menu_idle_loop_558b"):
        return
    run_main_menu_idle_loop_558b(cpu)


_SIG_D390 = bytes.fromhex("e8 cf 2d f6 06 be 98 10 75 f6")


@registry.replace(0x1010, 0xD390, "overkill_menu_fire_release_wait_d390")
def overkill_menu_fire_release_wait_d390(cpu):
    """One poll of the menu FIRE/SPACE release wait before transition setup."""
    if not _code_matches(cpu, 0xD390, _SIG_D390):
        _interpret_current_instruction_without_hook(cpu)
        return
    run_menu_fire_release_wait_d390(cpu)


_SIG_D434 = bytes.fromhex("80 3e e4 98 01 74 f9 e8 24 2d 80 3e be 98 00 75 f6")


@registry.replace(0x1010, 0xD434, "overkill_selector_input_release_wait_d434")
def overkill_selector_input_release_wait_d434(cpu):
    """One poll of the selector input-release wait before entering D445."""
    if not _code_matches(cpu, 0xD434, _SIG_D434):
        _interpret_current_instruction_without_hook(cpu)
        return
    run_selector_input_release_wait_d434(cpu)


@registry.replace(0x1010, 0xD445, "overkill_input_selector_loop_d445")
def overkill_input_selector_loop_d445(cpu):
    """Replace the observed D445 input/selector loop and BEDC counter path."""
    run_input_selector_loop_d445(cpu)


@registry.replace(0x1010, 0x017E, "overkill_keyboard_poll_bits_017e")
def overkill_keyboard_poll_bits_017e(cpu):
    """Replace the hot eight-key poll bit-packer at 1010:017E."""
    pack_keyboard_poll_bits_017e(cpu)


@registry.replace(0x1010, 0xCD8D, "overkill_changed_word_present_8rows_cd8d")
def overkill_changed_word_present_8rows_cd8d(cpu):
    """Replace the changed-word CGA presenter loop at 1010:CD8D.

    After the dirty-copy detector marks a block as changed, this loop copies one
    word from the work buffer to the visible CGA aperture across eight interlaced
    scanlines.  It appears prominently on the planet/difficulty menu because the
    screen is redrawn in many small dirty cells when the selection changes.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    cx = s.cx & 0xFFFF
    if cx == 0:
        cx = 0x10000

    ax = s.ax & 0xFFFF
    while cx:
        ax = mem.rw(ds, si)
        mem.ww(es, di, ax)

        old_si = si
        si = (si + 0x50) & 0xFFFF
        # ADD SI flags are overwritten before the LOOP unless this is somehow
        # not followed by the DI/test path, so keep only the architectural result.
        old_di = di
        di = (di + 0x2000) & 0xFFFF
        cpu.set_add_flags(old_di, 0x2000, old_di + 0x2000, 16)
        cpu.s.di = di
        _test_word(cpu, di, 0x4000)
        if not cpu.get_flag(ZF):
            old_di = di
            di = (di + 0xC050) & 0xFFFF
            cpu.set_add_flags(old_di, 0xC050, old_di + 0xC050, 16)
            cpu.s.di = di
        cx -= 1

    s.ax = ax
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = 0xCE02


@registry.replace(0x1010, 0xCDAA, "overkill_tandy_changed_dword_present_8rows_cdaa")
def overkill_tandy_changed_dword_present_8rows_cdaa(cpu):
    """Replace the Tandy changed-cell presenter loop at 1010:CDAA."""
    run_tandy_changed_dword_present_cdaa(cpu)






def _overkill_strided_row_copy(cpu, *, row_advance: int) -> None:
    """Shared replacement for OVERKILL's LODSW/REP-MOVSB strided row copier."""
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    s.es = mem.rw(cs, 0x9598)

    df = cpu.get_flag(DF)
    lod_delta = -2 if df else 2
    si = s.si & 0xFFFF
    ax = mem.rw(s.ds, si)
    si = (si + lod_delta) & 0xFFFF
    s.cx = ax & 0xFFFF
    ax = mem.rw(s.ds, si)
    si = (si + lod_delta) & 0xFFFF
    s.si = si
    s.ax = ax & 0xFFFF
    s.ax = cpu.shift(4, s.ax, 1, 16)  # SHL AX,1
    s.bp = s.ax & 0xFFFF

    outer = s.cx if s.cx != 0 else 0x10000
    width = s.bp & 0xFFFF
    row_advance &= 0xFFFF
    for _ in range(outer):
        # PUSH CX / MOV CX,BP / REP MOVSB / SUB DI,BP / ADD DI,row_advance /
        # POP CX / LOOP.  Keep using the project's optimized REP helper so DF
        # and 16-bit wrapping semantics stay centralized.
        saved_cx = s.cx & 0xFFFF
        cpu.push(saved_cx)
        s.cx = width
        _rep_movsb(cpu, width)
        _sub_reg16(cpu, 7, width)
        _add_reg16(cpu, 7, row_advance)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF  # LOOP does not change flags.

    s.ip = cpu.pop()


_STRIDED_ROW_COPY_34_SIG = bytes.fromhex("2e 8e 06 98 95 ad 8b c8 ad d1 e0 8b e8 51 8b cd f3 a4 2b fd 83 c7 34 59 e2 f3 c3")
_STRIDED_ROW_COPY_50_SIG = bytes.fromhex("2e 8e 06 98 95 ad 8b c8 ad d1 e0 8b e8 51 8b cd f3 a4 2b fd 83 c7 50 59 e2 f3 c3")


@registry.replace(0x1010, 0x3EE1, "overkill_strided_row_copy_3ee1")
def overkill_strided_row_copy_3ee1(cpu):
    """Replace row copier 1010:3EE1, which advances destination rows by 34h.

    This address is overlaid/reused by later sprite code, so the hook only
    applies while the exact row-copy bytes are resident.
    """
    if not _code_matches(cpu, 0x3EE1, _STRIDED_ROW_COPY_34_SIG):
        _interpret_current_instruction_without_hook(cpu)
        return
    _overkill_strided_row_copy(cpu, row_advance=0x34)


@registry.replace(0x1010, 0x3EFC, "overkill_strided_row_copy_3efc")
def overkill_strided_row_copy_3efc(cpu):
    """Replace row copier 1010:3EFC, which advances destination rows by 50h.

    This address is overlaid/reused by later sprite code, so the hook only
    applies while the exact row-copy bytes are resident.
    """
    if not _code_matches(cpu, 0x3EFC, _STRIDED_ROW_COPY_50_SIG):
        _interpret_current_instruction_without_hook(cpu)
        return
    _overkill_strided_row_copy(cpu, row_advance=0x50)




def _rcr_stc_chain_5bytes(bl: int, bh: int, al: int, ah: int, dl: int, passes: int) -> tuple[int, int, int, int, int]:
    """Return the 5-byte result of repeated STC; RCR BL,BH,AL,AH,DL groups.

    Used by the CGA masked-sprite compositors.  The interpreted version updated
    CPU flags on every single rotate, but those flags are overwritten by the
    row-step ADD/DEC before control leaves the hook.
    """
    bl &= 0xFF; bh &= 0xFF; al &= 0xFF; ah &= 0xFF; dl &= 0xFF
    for _ in range(passes):
        cf = 1
        old = bl; bl = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = bh; bh = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = al; al = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = ah; ah = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = dl; dl = ((cf << 7) | (old >> 1)) & 0xFF
    return bl, bh, al, ah, dl


def _shr_rcr_chain_5bytes(bl: int, bh: int, al: int, ah: int, dl: int, passes: int) -> tuple[int, int, int, int, int]:
    """Return the 5-byte result of repeated SHR BL; RCR BH,AL,AH,DL groups."""
    bl &= 0xFF; bh &= 0xFF; al &= 0xFF; ah &= 0xFF; dl &= 0xFF
    for _ in range(passes):
        cf = bl & 1
        bl = (bl >> 1) & 0xFF
        old = bh; bh = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = al; al = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = ah; ah = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = dl; dl = ((cf << 7) | (old >> 1)) & 0xFF
    return bl, bh, al, ah, dl


_MASKED_SPRITE_COMPOSITE_3EFB_SIG = bytes.fromhex(
    "8b 1c 8b 44 04 b2 ff f9 d0 db d0 df d0 d8 d0 dc d0 da"
)


@registry.replace(0x1010, 0x3EFB, "overkill_masked_sprite_composite_3efb")
def overkill_masked_sprite_composite_3efb(cpu):
    """Replace the overlaid 6-shift masked sprite loop at 1010:3EFB.

    This is the dominant interpreted loop on the planet/difficulty selection
    redraw path after the 3E12 two-shift compositor is hooked.  The address is
    overlay-reused, so only apply while the observed masked-compositor bytes are
    resident.
    """
    if not _code_matches(cpu, 0x3EFB, _MASKED_SPRITE_COMPOSITE_3EFB_SIG):
        _interpret_current_instruction_without_hook(cpu)
        return

    s = cpu.s
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    rows = bp if bp != 0 else 0x10000
    initial_dh = s.dx & 0xFF00
    final_dl = s.dx & 0x00FF
    mem = cpu.mem

    for _ in range(rows):
        mask_bx = mem.rw(ds, si)
        mask_ax = mem.rw(ds, (si + 4) & 0xFFFF)
        bl = mask_bx & 0xFF
        bh = (mask_bx >> 8) & 0xFF
        al = mask_ax & 0xFF
        ah = (mask_ax >> 8) & 0xFF
        dl = 0xFF
        bl, bh, al, ah, dl = _rcr_stc_chain_5bytes(bl, bh, al, ah, dl, 6)
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) & mask_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) & mask_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) & dl)

        data_bx = mem.rw(ds, (si + 2) & 0xFFFF)
        data_ax = mem.rw(ds, (si + 6) & 0xFFFF)
        bl = data_bx & 0xFF
        bh = (data_bx >> 8) & 0xFF
        al = data_ax & 0xFF
        ah = (data_ax >> 8) & 0xFF
        dl = 0x00
        cpu.set_logic_flags(0, 8)        # XOR DL,DL
        bl, bh, al, ah, dl = _shr_rcr_chain_5bytes(bl, bh, al, ah, dl, 6)
        data_bx = ((bh << 8) | bl) & 0xFFFF
        data_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) | data_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) | data_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) | dl)
        final_dl = dl

        si = (si + 8) & 0xFFFF
        old_di = di
        di_sum = old_di + 0x34
        di = di_sum & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, di_sum, 16)
        old_cf = cpu.get_flag(CF)
        old_bp = bp
        bp = (bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)
        cpu.set_flag(CF, old_cf)         # DEC preserves CF.

    s.si = si
    s.di = di
    s.bp = bp
    s.dx = initial_dh | final_dl
    s.bx = data_bx
    s.ax = data_ax
    s.ds = mem.rw(cs, 0x9596)            # MOV DS,CS:[9596] before RET.
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x3E12, "overkill_masked_sprite_composite_3e12")
def overkill_masked_sprite_composite_3e12(cpu):
    """Replace the hot masked CGA sprite/composite row loop at 1010:3E12.

    The original loop consumes eight source bytes per row, shifts mask and data
    bits through carry twice, then AND/OR-composites three destination bytes.
    It is hit heavily by the planet/difficulty selection screen when the menu
    redraws its sprites and highlight frame.
    """
    s = cpu.s
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    rows = bp if bp != 0 else 0x10000
    initial_dh = s.dx & 0xFF00
    final_dl = s.dx & 0x00FF

    mem = cpu.mem
    for _ in range(rows):
        # Mask phase:
        #   mov bx,[si]; mov ax,[si+4]; mov dl,ff; stc;
        #   rcr bl,bh,al,ah,dl twice; and destination bytes.
        mask_bx = mem.rw(ds, si)
        mask_ax = mem.rw(ds, (si + 4) & 0xFFFF)
        bl = mask_bx & 0xFF
        bh = (mask_bx >> 8) & 0xFF
        al = mask_ax & 0xFF
        ah = (mask_ax >> 8) & 0xFF
        dl = 0xFF
        bl, bh, al, ah, dl = _rcr_stc_chain_5bytes(bl, bh, al, ah, dl, 2)
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) & mask_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) & mask_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) & dl)

        # Data phase:
        #   mov bx,[si+2]; mov ax,[si+6]; xor dl,dl;
        #   shr bl; rcr bh,al,ah,dl; repeat; or destination bytes.
        data_bx = mem.rw(ds, (si + 2) & 0xFFFF)
        data_ax = mem.rw(ds, (si + 6) & 0xFFFF)
        bl = data_bx & 0xFF
        bh = (data_bx >> 8) & 0xFF
        al = data_ax & 0xFF
        ah = (data_ax >> 8) & 0xFF
        dl = 0x00
        cpu.set_logic_flags(0, 8)        # XOR DL,DL clears CF/OF and sets ZF/PF.
        bl, bh, al, ah, dl = _shr_rcr_chain_5bytes(bl, bh, al, ah, dl, 2)
        data_bx = ((bh << 8) | bl) & 0xFFFF
        data_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) | data_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) | data_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) | dl)
        final_dl = dl

        # ADD SI,8; ADD DI,34h; DEC BP; JNZ 3E12.  Only the final DEC flags are
        # externally visible, with CF preserved from the immediately preceding
        # ADD DI because DEC does not modify CF.
        si = (si + 8) & 0xFFFF
        old_di = di
        di_sum = old_di + 0x34
        di = di_sum & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, di_sum, 16)
        old_cf = cpu.get_flag(CF)
        old_bp = bp
        bp = (bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)
        cpu.set_flag(CF, old_cf)

    s.si = si
    s.di = di
    s.bp = bp
    s.dx = initial_dh | final_dl
    # BX and AX are left containing the last shifted data words; DL is already
    # reflected in DX, while DH is untouched by the ASM loop.
    s.bx = data_bx
    s.ax = data_ax
    s.ip = 0x3E6A



@registry.replace(0x1010, 0x5A36, "overkill_object_row_addr_5a36")
def overkill_object_row_addr_5a36(cpu):
    """Hook wrapper for OVERKILL 1010:5A36 object-row address dispatch.

    The original address is a video-mode dispatch helper, not a CGA-only
    routine.  It reaches CGA, EGA, or Tandy row-address targets through
    CS:[95BC], so the neutral name avoids making Tandy coverage look like it is
    accidentally using the CGA renderer.
    """
    object_row_address_from_mode_dispatch_5a36(cpu)


@registry.replace(0x1010, 0x5A00, "overkill_xy_to_di_5a00")
def overkill_xy_to_di_5a00(cpu):
    """Hook wrapper for OVERKILL 1010:5A00 shared coordinate-to-DI helper."""
    coordinate_ax_to_di_5a00(cpu)


@registry.replace(0x1010, 0x5A24, "overkill_xy_to_di_5a24")
def overkill_xy_to_di_5a24(cpu):
    """Hook wrapper for OVERKILL 1010:5A24 shared coordinate-to-DI helper."""
    coordinate_ax_to_di_5a24(cpu)




@registry.replace(0x1010, 0x5A6C, "overkill_menu_cell_source_blit_dispatch_5a6c")
def overkill_menu_cell_source_blit_dispatch_5a6c(cpu):
    """Hook wrapper for OVERKILL 1010:5A6C source-cell mode dispatch."""
    if not _code_matches(cpu, 0x5A6C, _SIG_5A6C):
        _interpret_current_instruction_without_hook(cpu)
        return
    dispatch_menu_cell_source_blit_5a6c(cpu)

@registry.replace(0x1010, 0x5AC8, "overkill_dispatch_draw_object_5ac8")
def overkill_dispatch_draw_object_5ac8(cpu):
    """Hook wrapper for OVERKILL 1010:5AC8 draw-object dispatcher."""
    dispatch_draw_object_5ac8(cpu)


@registry.replace(0x1010, 0x5A92, "overkill_dispatch_present_object_5a92")
def overkill_dispatch_present_object_5a92(cpu):
    """Hook wrapper for OVERKILL 1010:5A92 present-object dispatcher."""
    dispatch_present_object_5a92(cpu)


@registry.replace(0x1010, 0xAA44, "overkill_clc_ret_aa44")
def overkill_clc_ret_aa44(cpu):
    """Replace the tiny hot CLC/RET success helper at 1010:AA44."""
    cpu.set_flag(CF, False)
    cpu.s.ip = cpu.pop()
