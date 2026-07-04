"""Tests for the native application skeleton (overkill.native_app).

The skeleton is structure, not behaviour: these pin the recovered 97B2 stage ORDER, the
machine-readable gap boundary, and the fail-loud rules (no silent fallback ever hides a gap).
"""
from __future__ import annotations

import pytest

from overkill.native_app import (
    GAP,
    GAMEPLAY_FRAME_STAGES,
    HOST,
    NATIVE,
    NEW_GAME_SETUP_STAGES,
    UNMONITORED,
    AttractSequencer,
    GameplayFrameSkeleton,
    describe_gaps,
)
from overkill.recovered.domain.attract import AttractSceneState
from overkill.recovered.domain.gaps import RecoveryGap


def test_stage_map_matches_the_97b2_call_order():
    # the original 1010:97B2 loop order, one entry per call site
    assert [s.name for s in GAMEPLAY_FRAME_STAGES] == [
        "timer_tick_clear", "video_page_toggle", "sprite_draw_scan", "conditional_hud_cell",
        "present_blit", "present_object_scan", "game_state_controller", "transition_flags",
        "frame_state_update", "service_gate", "status_text", "frame_wait",
    ]
    assert all(s.status in (NATIVE, HOST, GAP, UNMONITORED) for s in GAMEPLAY_FRAME_STAGES)
    assert all(s.asm.startswith("1010:") for s in GAMEPLAY_FRAME_STAGES)


def test_new_game_setup_bridge_map_is_declared_and_honest():
    # the 971A/9734 -> 9744 -> 97B2 new-game/level-start bridge, in flow order
    assert [s.name for s in NEW_GAME_SETUP_STAGES] == [
        "level_select", "screen_load", "new_game_setup", "countdown_init", "panel_draw",
        "level0_intro", "level_advance", "setup_tail",
    ]
    assert all(s.status in (NATIVE, HOST, GAP, UNMONITORED) for s in NEW_GAME_SETUP_STAGES)
    assert all(s.asm.startswith("1010:") for s in NEW_GAME_SETUP_STAGES)
    by_name = {s.name: s for s in NEW_GAME_SETUP_STAGES}
    assert by_name["new_game_setup"].status == NATIVE     # C4DB composed + proven complete
    assert by_name["level_advance"].status == NATIVE       # 9744 six-planet advance recovered
    assert by_name["screen_load"].status == HOST           # 5C9A VGA blit is presentation
    assert by_name["setup_tail"].status == GAP             # the unrecovered per-level setup remainder
    # the newly-declared bridge gaps surface in the honest gap report
    report = "\n".join(describe_gaps())
    assert "new_game_setup.setup_tail" in report and "new_game_setup.level0_intro" in report


def test_planet_video_dispatch_is_six_planets_three_configs():
    from overkill.native_app import PLANET_VIDEO_DISPATCH, PLANET_VIDEO_HANDLERS
    # exactly the six planets (2356 = 0..5)
    assert sorted(PLANET_VIDEO_DISPATCH) == list(range(6))
    # three distinct handlers in the A,B,C,B,A,C pattern
    assert set(PLANET_VIDEO_DISPATCH.values()) == set(PLANET_VIDEO_HANDLERS) == {0x4F37, 0x4FC3, 0x4F57}
    assert [PLANET_VIDEO_DISPATCH[i] for i in range(6)] == [0x4F37, 0x4FC3, 0x4F57, 0x4FC3, 0x4F37, 0x4F57]


def test_gap_boundary_is_declared_and_reported():
    # the known-unrecovered pieces must stay visible: the transition flags + the frame-state update
    by_name = {s.name: s for s in GAMEPLAY_FRAME_STAGES}
    assert by_name["transition_flags"].status == GAP        # decision recovered + wired fail-loud
    assert by_name["service_gate"].status == GAP             # 073C sound/timer -- not recovered
    assert by_name["frame_state_update"].status == NATIVE    # A940 gameplay path composed + verified
    assert by_name["conditional_hud_cell"].status == UNMONITORED  # still a truly-unmonitored stage
    report = "\n".join(describe_gaps())
    for expected in ("transition_flags", "Bucket F", "D160", "menu logic"):
        assert expected in report, expected


def test_skeleton_tick_presents_current_state_then_advances():
    calls = []
    sk = GameplayFrameSkeleton(render=lambda: calls.append("render") or "frame",
                               advance=lambda: calls.append("advance"))
    assert sk.tick() == "frame"
    assert calls == ["render", "advance"]     # the original order: present BEFORE 9B2E


def test_skeleton_tick_propagates_recovery_gaps():
    def _advance():
        raise RecoveryGap("1010:99F6 (scripted input)", "DS:A47C went non-zero")
    sk = GameplayFrameSkeleton(render=lambda: "frame", advance=_advance)
    with pytest.raises(RecoveryGap):
        sk.tick()


def test_attract_sequencer_autofire_never_exits_the_loop():
    # D007 polls the REAL input (0162) AFTER the scene step, overwriting the injected auto-fire --
    # so a demo fire is consumed by the fan-out but never trips the exit test.
    seq = AttractSequencer(AttractSceneState(scene=9, countdown=0x40, autofire_tick=0x0E))
    assert seq.frame(real_input_98be=0x00, any_key_98c3=0) == 0x10   # fan-out consumed the demo FIRE
    assert seq.state.autofire_tick == 0x0F


def test_attract_sequencer_exits_only_on_real_input():
    seq = AttractSequencer(AttractSceneState(scene=9, countdown=0x40, autofire_tick=0x00))
    assert seq.frame(real_input_98be=0x10, any_key_98c3=0) is None   # real FIRE exits
    seq = AttractSequencer(AttractSceneState(scene=9, countdown=0x40, autofire_tick=0x00))
    assert seq.frame(real_input_98be=0x00, any_key_98c3=0x1C) is None  # any real key exits
    seq = AttractSequencer(AttractSceneState(scene=9, countdown=0x40, autofire_tick=0x0F))
    # a quiet frame inside the auto-fire window: input cleared (0), loop continues
    assert seq.frame(real_input_98be=0x00, any_key_98c3=0) == 0
    assert seq.state.autofire_tick == 0x10


def test_attract_sequencer_scene_advance_fails_loud():
    seq = AttractSequencer(AttractSceneState(scene=9, countdown=1, autofire_tick=0))
    with pytest.raises(RecoveryGap):
        seq.frame(real_input_98be=0, any_key_98c3=0)
