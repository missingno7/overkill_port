"""Address-bound wrappers for OVERKILL object-runtime frontiers.

This module keeps object-slot allocation, spawn seeding, movement, and observed
object-family behavior wrappers out of the aggregate ``overkill.hooks`` staging
file.  The routines here are still CS:IP-facing glue: behavior lives in
``overkill.gameplay.object_runtime`` / ``overkill.gameplay.collision`` and this
module only preserves names, signatures, and exact hook-boundary side effects.
"""

from __future__ import annotations

from dos_re.hooks import registry

from ..gameplay.collision import (
    run_object_slot_scan_ac97,
    run_object_slot_scan_guard_ac81,
    run_postmove_contact_window_aa71,
    run_postmove_y_clamp_bcb1,
    run_tile_collision_probe_ac28,
)
from ..gameplay.objects import (
    call_object_logic_from_scan_aa01,
    finish_object_logic_scan_tail_aa04,
    run_object_motion_table_ab34,
    run_object_scroll_sprite_ab4f,
)
from ..gameplay.object_runtime import (
    _find_free_effect_slot_7524,
    _find_free_object_slot_7573,
    _run_interpreted_near_call_observed,
    _run_movement_direction_5db2,
    _run_object_behavior_aba3,
    _run_object_behavior_ab77,
    _run_object_behavior_ae09,
    _run_object_behavior_aed8,
    _run_object_behavior_b24d,
    _run_object_behavior_b73e,
    _run_object_behavior_b86d,
    _run_object_behavior_b9f0,
    _run_object_bounds_tile_tail_ad60,
    _run_object_family_dispatch_efae,
    _run_object_logic_ab10,
    _run_object_logic_branch_ad04,
    _run_object_logic_dispatch_aa2b,
    _run_object_postmove_bc4b,
    _run_object_sprite0f_collision_abca,
    _run_tracked_object_selector_to_ab77,
    run_movement_dir_step_3px_af22,
    run_movement_dir_step_8px_aee4,
    run_object_bounds_tile_prelude_ad5a,
    run_object_drift_downright_ae2c,
    run_object_drift_upright_ae7d,
    run_object_player_chase_b1b0,
    run_object_postmove_prelude_bc45,
    run_object_slot_allocate_or_reclaim_7547,
    run_object_spawn_anchor_offset_a571,
    run_object_spawn_seed_8209,
    run_object_spawn_seed_a4ea,
    run_object_spawn_seed_from_source_a4d7,
    run_object_target_chase_d281,
    run_object_target_move_b729,
    run_object_x_step_left_clamp_a5d1,
    run_object_x_step_right_clamp_a5ea,
    run_object_y_step_down_clamp_a607,
    run_object_y_step_up_clamp_a5f9,
    run_player_chase_candidate_scan_b15a,
    run_runtime_patched_object_steer_5e42,
)
from .common import (
    code_matches as _code_matches,
    interpret_current_instruction_without_hook as _interpret_current_instruction_without_hook,
    self_disable_if_patched as _self_disable_if_patched,
)
from .runtime_signatures import *  # noqa: F403 - address signatures are hook data

_SIG_FIND_FREE_EFFECT_SLOT_7524 = bytes.fromhex(
    "b9 23 00 8b 1e d8 95 83 3f 00 74 12 83 c3 38 81"
    " fb 5c 2b 75 03 bb b4 23 e2 ed bb ff ff c3 89 1e"
    " d8 95 c3"
)

_SIG_FIND_FREE_OBJECT_SLOT_7573 = bytes.fromhex(
    "b9 22 00 8b 1e da 95 81 fb cc 32 75 03 bb 5c 2b"
    " 83 3f 00 74 09 83 c3 38 e2 ed bb ff ff c3 89 1e"
    " da 95 c3"
)

_SIG_OBJECT_ALLOC_OR_RECLAIM_7547 = bytes.fromhex(
    "e8 29 00 83 fb ff 74 01 c3 b9 22 00 bb 5c 2b 83"
    " 7f 18 09 74 0c 83 7f 18 0a 74 06 83 7f 16 01 75 08"
    " 83 c3 38 e2 e9 bb 5c 2b e9 9a 47"
)

_SIG_OBJECT_SPAWN_SEED_A4EA = bytes.fromhex(
    "e8 5a d0 c7 07 01 00 c7 47 1e 01 00 c7 47 06 00"
    " 00 c7 47 08 32 00 c7 47 14 00 00 c7 47 16 02 00"
    " c7 47 18 02 00 c7 47 1c ff ff c3"
)

_SIG_OBJECT_SPAWN_SEED_FROM_SOURCE_A4D7 = (
    bytes.fromhex("e8 10 00 8b 44 02 89 47 02 8b 44 04 83 c0 04 89 47 04 c3"),
    bytes.fromhex("e8 10 00 8b 44 02 89 47 02 8b 44 04 05 04 00 89 47 04 c3"),
)

_SIG_OBJECT_SPAWN_ANCHOR_OFFSET_A571 = (
    # install-time/static runtime form: ADD AX, imm8
    bytes.fromhex("8b 46 04 83 c0 0a 89 47 04 8b 46 02 83 c0 0a 89 47 02 c3"),
    # live/runtime-loaded form seen in demo snapshots: ADD AX, imm16
    bytes.fromhex("8b 46 04 05 0a 00 89 47 04 8b 46 02 05 0a 00 89 47 02 c3"),
)


@registry.replace(0x1010, 0x7524, "overkill_find_free_effect_slot_7524")
def overkill_find_free_effect_slot_7524(cpu):
    """Replace compact effect-slot allocator 1010:7524."""
    if not _code_matches(cpu, 0x7524, _SIG_FIND_FREE_EFFECT_SLOT_7524):
        _interpret_current_instruction_without_hook(cpu)
        return
    _find_free_effect_slot_7524(cpu)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x7573, "overkill_find_free_object_slot_7573")
def overkill_find_free_object_slot_7573(cpu):
    """Replace main gameplay object-slot allocator 1010:7573."""
    if not _code_matches(cpu, 0x7573, _SIG_FIND_FREE_OBJECT_SLOT_7573):
        _interpret_current_instruction_without_hook(cpu)
        return
    _find_free_object_slot_7573(cpu)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x7547, "overkill_object_slot_allocate_or_reclaim_7547")
def overkill_object_slot_allocate_or_reclaim_7547(cpu):
    """Hot object-slot allocation gate with rare original reclaim fallback."""
    if not _code_matches(cpu, 0x7547, _SIG_OBJECT_ALLOC_OR_RECLAIM_7547):
        _interpret_current_instruction_without_hook(cpu)
        return
    run_object_slot_allocate_or_reclaim_7547(cpu)


@registry.replace(0x1010, 0xA4EA, "overkill_object_spawn_seed_a4ea")
def overkill_object_spawn_seed_a4ea(cpu):
    """Common raw object-slot seed template reached by several object families."""
    if not _code_matches(cpu, 0xA4EA, _SIG_OBJECT_SPAWN_SEED_A4EA):
        _interpret_current_instruction_without_hook(cpu)
        return
    run_object_spawn_seed_a4ea(cpu)


@registry.replace(0x1010, 0xA4D7, "overkill_object_spawn_seed_from_source_a4d7")
def overkill_object_spawn_seed_from_source_a4d7(cpu):
    """A4EA seed plus source-coordinate copy into the spawned object slot."""
    if not _code_matches(cpu, 0xA4D7, _SIG_OBJECT_SPAWN_SEED_FROM_SOURCE_A4D7):
        _interpret_current_instruction_without_hook(cpu)
        return
    run_object_spawn_seed_from_source_a4d7(cpu)


@registry.replace(0x1010, 0xA571, "overkill_object_spawn_anchor_offset_a571")
def overkill_object_spawn_anchor_offset_a571(cpu):
    """Copy source object coordinates plus +10/+10 into a spawned object slot."""
    if not _code_matches(cpu, 0xA571, _SIG_OBJECT_SPAWN_ANCHOR_OFFSET_A571):
        _interpret_current_instruction_without_hook(cpu)
        return
    run_object_spawn_anchor_offset_a571(cpu)


_SIG_OBJECT_SPAWN_SEED_8209 = bytes.fromhex(
    "c7 47 28 ff ff c7 07 01 00 c7 47 0a 01 00 8b 46"
    " 02 89 47 02 89 47 34 8b 46 04 89 47 04 89 47 32"
    " c7 47 06 04 00 c7 47 14 01 00 c7 47 16 04 00 c7"
    " 47 18 14 00 c7 47 20 04 00 c7 47 24 00 00 c3"
)


@registry.replace(0x1010, 0x8209, "overkill_object_spawn_seed_8209")
def overkill_object_spawn_seed_8209(cpu):
    """Shared object-slot spawn-stamp template reached from 81E9/81F4."""
    if not _code_matches(cpu, 0x8209, _SIG_OBJECT_SPAWN_SEED_8209):
        _interpret_current_instruction_without_hook(cpu)
        return
    run_object_spawn_seed_8209(cpu)


@registry.replace(0x1010, 0xA5D1, "overkill_object_x_step_left_clamp_a5d1")
def overkill_object_x_step_left_clamp_a5d1(cpu):
    """Raw object X decrement helper with the original two-pass clamp idiom."""
    run_object_x_step_left_clamp_a5d1(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xA5EA, "overkill_object_x_step_right_clamp_a5ea")
def overkill_object_x_step_right_clamp_a5ea(cpu):
    """Raw object X increment helper with the original two-pass clamp idiom."""
    run_object_x_step_right_clamp_a5ea(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xA5F9, "overkill_object_y_step_up_clamp_a5f9")
def overkill_object_y_step_up_clamp_a5f9(cpu):
    """Raw object Y decrement helper with the original two-pass clamp idiom."""
    run_object_y_step_up_clamp_a5f9(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xA607, "overkill_object_y_step_down_clamp_a607")
def overkill_object_y_step_down_clamp_a607(cpu):
    """Raw object Y increment helper with the original two-pass clamp idiom."""
    run_object_y_step_down_clamp_a607(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAEE4, "overkill_movement_dir_step_8px_aee4")
def overkill_movement_dir_step_8px_aee4(cpu):
    """8-direction movement step table, 8-pixel delta (entry for direct calls)."""
    run_movement_dir_step_8px_aee4(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAF22, "overkill_movement_dir_step_3px_af22")
def overkill_movement_dir_step_3px_af22(cpu):
    """8-direction movement step table, 3-pixel delta (entry for direct calls)."""
    run_movement_dir_step_3px_af22(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xB9F0, "overkill_object_behavior_b9f0")
def overkill_object_behavior_b9f0(cpu):
    """Observed object-family behavior B9F0 lifted up to the shared BC4B tail."""
    if _self_disable_if_patched(cpu, 0xB9F0, _SIG_B9F0, "overkill_object_behavior_b9f0"):
        return
    _run_object_behavior_b9f0(
        cpu,
        parent="1010:B9F0",
        chain="B9F0",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xB73E, "overkill_object_behavior_b73e")
def overkill_object_behavior_b73e(cpu):
    """Fail-fast lifted branch of object behavior B73E."""
    if _self_disable_if_patched(cpu, 0xB73E, _SIG_B73E, "overkill_object_behavior_b73e"):
        return
    _run_object_behavior_b73e(
        cpu,
        parent="1010:B73E",
        chain="B73E",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xB24D, "overkill_object_behavior_b24d")
def overkill_object_behavior_b24d(cpu):
    """Lift the observed B24D object-family steering/overlap behavior."""
    if _self_disable_if_patched(cpu, 0xB24D, _SIG_B24D, "overkill_object_behavior_b24d"):
        return
    _run_object_behavior_b24d(
        cpu,
        parent="1010:B24D",
        chain="B24D",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xB15A, "overkill_player_chase_candidate_scan_b15a")
def overkill_player_chase_candidate_scan_b15a(cpu):
    """Shared rotating object-slot candidate scan used by B1B0 and A515."""
    run_player_chase_candidate_scan_b15a(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xB1B0, "overkill_object_player_chase_b1b0")
def overkill_object_player_chase_b1b0(cpu):
    """Recovered player/view-centered chase behavior at 1010:B1B0."""
    run_object_player_chase_b1b0(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xB86D, "overkill_object_behavior_b86d")
def overkill_object_behavior_b86d(cpu):
    """Observed object-family behavior B86D lifted up to the shared BC4B tail."""
    if _self_disable_if_patched(cpu, 0xB86D, _SIG_B86D, "overkill_object_behavior_b86d"):
        return
    _run_object_behavior_b86d(
        cpu,
        parent="1010:B86D",
        chain="B86D",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0x5E42, "overkill_runtime_patched_object_steer_5e42")
def overkill_runtime_patched_object_steer_5e42(cpu):
    """Lift the gameplay-patched object steering helper at 1010:5E42."""
    run_runtime_patched_object_steer_5e42(cpu)


@registry.replace(0x1010, 0x5DB2, "overkill_movement_direction_helper_5db2")
def overkill_movement_direction_helper_5db2(cpu):
    """Verified target-seeking movement helper at 1010:5DB2."""
    if _self_disable_if_patched(cpu, 0x5DB2, _SIG_5DB2, "overkill_movement_direction_helper_5db2"):
        return
    _run_movement_direction_5db2(cpu)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0xB729, "overkill_object_target_move_b729")
def overkill_object_target_move_b729(cpu):
    """Recovered object target-copy + 5DB2 movement wrapper at 1010:B729."""
    run_object_target_move_b729(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAA01, "overkill_object_logic_call_aa2b_aa01")
def overkill_object_logic_call_aa2b_aa01(cpu):
    """Hook wrapper for A9E0 active-entry CALL AA2B glue."""
    call_object_logic_from_scan_aa01(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAA04, "overkill_object_logic_scan_tail_aa04")
def overkill_object_logic_scan_tail_aa04(cpu):
    """Hook wrapper for A9E0 post-logic POP/LOOP glue."""
    finish_object_logic_scan_tail_aa04(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAC97, "overkill_object_slot_scan_ac97")
def overkill_object_slot_scan_ac97(cpu):
    """Lift the hot 35-slot object-record scan at 1010:AC97."""
    run_object_slot_scan_ac97(cpu)


@registry.replace(0x1010, 0xBCB1, "overkill_postmove_y_clamp_bcb1")
def overkill_postmove_y_clamp_bcb1(cpu):
    """Lift the hot BC4B Y-clamp leaf at 1010:BCB1."""
    run_postmove_y_clamp_bcb1(cpu)


@registry.replace(0x1010, 0xAA71, "overkill_postmove_contact_window_aa71")
def overkill_postmove_contact_window_aa71(cpu):
    """Lift the object/player contact-window helper at 1010:AA71."""
    run_postmove_contact_window_aa71(cpu)


@registry.replace(0x1010, 0xBC45, "overkill_object_postmove_prelude_bc45")
def overkill_object_postmove_prelude_bc45(cpu):
    """Replace BC45 prelude and reuse the shared BC4B postmove implementation."""
    if _self_disable_if_patched(cpu, 0xBC45, _SIG_BC45, "overkill_object_postmove_prelude_bc45"):
        return
    run_object_postmove_prelude_bc45(cpu, cx_value=cpu.s.cx & 0xFFFF)


@registry.replace(0x1010, 0xBC4B, "overkill_object_postmove_bc4b")
def overkill_object_postmove_bc4b(cpu):
    """Lift the hot BC4B post-move helper call-site at 1010:BC4B."""
    _run_object_postmove_bc4b(cpu, parent="1010:BC4B", chain="BC4B", cx_value=cpu.s.cx & 0xFFFF)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0xAA2B, "overkill_object_logic_dispatch_aa2b")
def overkill_object_logic_dispatch_aa2b(cpu):
    """Fail-fast first-level object logic dispatcher indexed by SS:[BP+16]."""
    if _self_disable_if_patched(cpu, 0xAA2B, _SIG_AA2B, "overkill_object_logic_dispatch_aa2b"):
        return
    _run_object_logic_dispatch_aa2b(
        cpu,
        parent="1010:AA2B",
        chain="AA2B",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xEFAE, "overkill_object_family_dispatch_efae")
def overkill_object_family_dispatch_efae(cpu):
    """Fail-fast second-level object-family dispatcher indexed by SS:[BP+18]."""
    if _self_disable_if_patched(cpu, 0xEFAE, _SIG_EFAE, "overkill_object_family_dispatch_efae"):
        return
    _run_object_family_dispatch_efae(
        cpu,
        parent="1010:EFAE",
        chain="EFAE",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xAE09, "overkill_object_behavior_ae09")
def overkill_object_behavior_ae09(cpu):
    """Observed logic-id 0Ch timer/3-pixel-step behavior."""
    if _self_disable_if_patched(cpu, 0xAE09, _SIG_AE09, "overkill_object_behavior_ae09"):
        return
    _run_object_behavior_ae09(
        cpu,
        parent="1010:AE09",
        chain="AE09",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xAED8, "overkill_object_behavior_aed8")
def overkill_object_behavior_aed8(cpu):
    """Observed logic-id 2/3 object behavior: countdown, movement, and postmove tail."""
    if _self_disable_if_patched(cpu, 0xAED8, _SIG_AED8, "overkill_object_behavior_aed8"):
        return
    _run_object_behavior_aed8(
        cpu,
        parent="1010:AED8",
        chain="AED8",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xAB10, "overkill_object_logic_ab10")
def overkill_object_logic_ab10(cpu):
    """Observed AA2B target AB10 position/sprite update helper."""
    if _self_disable_if_patched(cpu, 0xAB10, _SIG_AB10, "overkill_object_logic_ab10"):
        return
    _run_object_logic_ab10(
        cpu,
        parent="1010:AB10",
        chain="AB10",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xAD04, "overkill_object_logic_branch_ad04")
def overkill_object_logic_branch_ad04(cpu):
    """Small object-logic selector that jumps to ABxx tails or returns."""
    if _self_disable_if_patched(cpu, 0xAD04, _SIG_AD04, "overkill_object_logic_branch_ad04"):
        return
    _run_object_logic_branch_ad04(
        cpu,
        parent="1010:AD04",
        chain="AD04",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xAD60, "overkill_object_bounds_tile_tail_ad60")
def overkill_object_bounds_tile_tail_ad60(cpu):
    """Shared object bounds/tile tail reached by several ADxx behaviours."""
    if _self_disable_if_patched(cpu, 0xAD60, _SIG_AD60, "overkill_object_bounds_tile_tail_ad60"):
        return
    _run_object_bounds_tile_tail_ad60(
        cpu,
        parent="1010:AD60",
        chain="AD60",
        cx_value=cpu.s.cx & 0xFFFF,
        add_a278_to_x=False,
    )


@registry.replace(0x1010, 0xAE2C, "overkill_object_drift_downright_ae2c")
def overkill_object_drift_downright_ae2c(cpu):
    """Observed drift-down/right object tail that joins AD5A/AD60."""
    run_object_drift_downright_ae2c(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAE7D, "overkill_object_drift_upright_ae7d")
def overkill_object_drift_upright_ae7d(cpu):
    """Observed drift-up/right object tail that joins AD5A/AD60."""
    run_object_drift_upright_ae7d(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAD5A, "overkill_object_bounds_tile_prelude_ad5a")
def overkill_object_bounds_tile_prelude_ad5a(cpu):
    """Object bounds/tile tail prelude that applies DS:A278 to object X."""
    run_object_bounds_tile_prelude_ad5a(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xD281, "overkill_object_target_chase_d281")
def overkill_object_target_chase_d281(cpu):
    """Observed object target-copy + 5DB2 chase helper tail."""
    run_object_target_chase_d281(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xABA3, "overkill_object_behavior_aba3")
def overkill_object_behavior_aba3(cpu):
    """Observed ABA3 tracked-object follower/probe behaviour."""
    if _self_disable_if_patched(cpu, 0xABA3, _SIG_ABA3, "overkill_object_behavior_aba3"):
        return
    _run_object_behavior_aba3(
        cpu,
        parent="1010:ABA3",
        chain="ABA3",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xAB59, "overkill_tracked_object_selector_a96c_ab59")
def overkill_tracked_object_selector_a96c_ab59(cpu):
    """Tiny AD04 branch glue: DS:A42C=A96C then jump to AB77."""
    if _self_disable_if_patched(cpu, 0xAB59, _SIG_AB59, "overkill_tracked_object_selector_a96c_ab59"):
        return
    _run_tracked_object_selector_to_ab77(cpu, selector_addr=0xA96C)


@registry.replace(0x1010, 0xAB61, "overkill_tracked_object_selector_a96a_ab61")
def overkill_tracked_object_selector_a96a_ab61(cpu):
    """Tiny AD04 branch glue: DS:A42C=A96A then jump to AB77."""
    if _self_disable_if_patched(cpu, 0xAB61, _SIG_AB61, "overkill_tracked_object_selector_a96a_ab61"):
        return
    _run_tracked_object_selector_to_ab77(cpu, selector_addr=0xA96A)


@registry.replace(0x1010, 0xAB69, "overkill_tracked_object_selector_a968_ab69")
def overkill_tracked_object_selector_a968_ab69(cpu):
    """Tiny AD04 branch glue: DS:A42C=A968 then jump to AB77."""
    if _self_disable_if_patched(cpu, 0xAB69, _SIG_AB69, "overkill_tracked_object_selector_a968_ab69"):
        return
    _run_tracked_object_selector_to_ab77(cpu, selector_addr=0xA968)


@registry.replace(0x1010, 0xAB71, "overkill_tracked_object_selector_a966_ab71")
def overkill_tracked_object_selector_a966_ab71(cpu):
    """Tiny AD04 branch glue: DS:A42C=A966 then jump to AB77."""
    if _self_disable_if_patched(cpu, 0xAB71, _SIG_AB71, "overkill_tracked_object_selector_a966_ab71"):
        return
    _run_tracked_object_selector_to_ab77(cpu, selector_addr=0xA966)


@registry.replace(0x1010, 0xABCA, "overkill_object_sprite0f_collision_abca")
def overkill_object_sprite0f_collision_abca(cpu):
    """Observed AD04 sprite-000F object collision/deactivation path."""
    if _self_disable_if_patched(cpu, 0xABCA, _SIG_ABCA, "overkill_object_sprite0f_collision_abca"):
        return
    _run_object_sprite0f_collision_abca(
        cpu,
        parent="1010:ABCA",
        chain="ABCA",
        cx_value=cpu.s.cx & 0xFFFF,
        run_original_near_call=_run_interpreted_near_call_observed,
    )


@registry.replace(0x1010, 0xAB77, "overkill_object_behavior_ab77")
def overkill_object_behavior_ab77(cpu):
    """Observed AB77 tracked-object behaviour driver."""
    if _self_disable_if_patched(cpu, 0xAB77, _SIG_AB77, "overkill_object_behavior_ab77"):
        return
    _run_object_behavior_ab77(
        cpu,
        parent="1010:AB77",
        chain="AB77",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xAB34, "overkill_object_motion_table_ab34")
def overkill_object_motion_table_ab34(cpu):
    """Runtime-patched object motion table helper."""
    run_object_motion_table_ab34(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAB4F, "overkill_object_scroll_sprite_ab4f")
def overkill_object_scroll_sprite_ab4f(cpu):
    """Runtime-patched object scroll/sprite helper."""
    run_object_scroll_sprite_ab4f(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAC28, "overkill_tile_collision_probe_ac28")
def overkill_tile_collision_probe_ac28(cpu):
    """Runtime-patched tile-collision probe used by ABxx object behaviours."""
    run_tile_collision_probe_ac28(cpu, _self_disable_if_patched)


@registry.replace(0x1010, 0xAC81, "overkill_object_slot_scan_guard_ac81")
def overkill_object_slot_scan_guard_ac81(cpu):
    """Guard/setup wrapper around the shared AC97 object-slot overlap scan."""
    run_object_slot_scan_guard_ac81(cpu, _self_disable_if_patched)

__all__ = [name for name in globals() if name.startswith("overkill_")]
