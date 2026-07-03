"""Unit tests for the pure attract/story scene-sequencer rules (systems/attract).

These pin the D007/D04D disassembly transcription (2026-07-04); the demo witness is the follow-up
gate before an attract mode ships on them.
"""
from __future__ import annotations

import pytest

from overkill.recovered.domain.attract import (
    AUTOFIRE_CYCLE,
    AUTOFIRE_TICKS,
    SCENE_COUNTDOWN_RELOAD,
    TERMINAL_SCENE,
    AttractSceneState,
)
from overkill.recovered.domain.gaps import RecoveryGap
from overkill.recovered.systems.attract import (
    attract_autofire_runs,
    attract_autofire_tick,
    attract_frame_step,
    attract_loop_exits,
    attract_scene_countdown,
)


def test_autofire_gate_boundaries():
    # cmp [BE06],8 / jb skip ; cmp [BE08],14h / jb skip
    assert attract_autofire_runs(8, 0x14) is True
    assert attract_autofire_runs(7, 0x14) is False     # scene below 8
    assert attract_autofire_runs(8, 0x13) is False     # countdown below 0x14
    assert attract_autofire_runs(0x12, 0x64) is True


def test_autofire_tick_wraps_and_fires_on_the_three_ticks():
    # inc; wrap at 0x14 -> 0; FIRE (0x10) exactly on new ticks {0x0F, 0x11, 0x13}
    assert attract_autofire_tick(0x13) == (0x00, 0x00)          # 0x13+1 = 0x14 -> wraps to 0
    assert attract_autofire_tick(0x0E) == (0x0F, 0x10)          # fire tick
    assert attract_autofire_tick(0x10) == (0x11, 0x10)          # fire tick
    assert attract_autofire_tick(0x12) == (0x13, 0x10)          # fire tick
    assert attract_autofire_tick(0x0F) == (0x10, 0x00)          # in between -> input cleared
    fired = [new for t in range(AUTOFIRE_CYCLE)
             for new, inj in (attract_autofire_tick(t),) if inj]
    assert sorted(fired) == sorted(AUTOFIRE_TICKS)              # exactly three fire ticks per cycle


def test_scene_countdown_decrements_then_advances():
    assert attract_scene_countdown(9, 5) == (9, 4, False)
    assert attract_scene_countdown(9, 1) == (10, SCENE_COUNTDOWN_RELOAD, True)   # expiry -> next scene


def test_frame_step_composes_autofire_and_countdown():
    step = attract_frame_step(AttractSceneState(scene=9, countdown=0x40, autofire_tick=0x0E))
    assert step.state == AttractSceneState(scene=9, countdown=0x3F, autofire_tick=0x0F)
    assert step.injected_input == 0x10 and step.run_fanout is True
    assert step.scene_advanced is False


def test_frame_step_low_scene_skips_autofire():
    step = attract_frame_step(AttractSceneState(scene=3, countdown=0x40, autofire_tick=0x0E))
    assert step.injected_input is None and step.run_fanout is False
    assert step.state.autofire_tick == 0x0E                     # untouched outside the gate


def test_frame_step_scene0_fails_loud():
    with pytest.raises(RecoveryGap):
        attract_frame_step(AttractSceneState(scene=0, countdown=0x40, autofire_tick=0))


def test_loop_exit_rules():
    # terminal scene exits unconditionally; otherwise FIRE (0x10) or any key byte exits
    assert attract_loop_exits(TERMINAL_SCENE, 0x00, 0x00) is True
    assert attract_loop_exits(9, 0x10, 0x00) is True            # fire
    assert attract_loop_exits(9, 0x00, 0x01) is True            # any key
    assert attract_loop_exits(9, 0x0F, 0x00) is False           # directions alone do not exit
    assert attract_loop_exits(9, 0x00, 0x00) is False
