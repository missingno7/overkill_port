"""Bucket C: the NativeGameState aggregate + the pure verify-mode comparison core.

``native_game_state_mismatches`` is the §1.2 verify gate: it compares the standalone
runtime's state against a VM-projected reference, VM-free.  ``read_native_game_state``
builds that reference from VM memory by composing the recovered per-state readers.
"""
from __future__ import annotations

from dos_re.memory import Memory

from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state
from overkill.recovered.domain.frame_snapshot import CameraState, HudLayer
from overkill.recovered.domain.native_game_state import (
    NativeGameState,
    native_game_state_mismatches,
)
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.ds_globals import VIEW_TARGET_X, VIEW_TARGET_Y
from overkill.recovered.systems.score import advance_hud_score
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    FRAME_TIMER_COUNT,
    FRAME_TIMER_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_BASE,
    SCORE_BCD_BASE,
)

DS = 0x1A0F


def _state(camera_xy=(0x10, 0x20), score=(0x0990, 0x0003), pool_slot0_word0=0x0001,
           effect_slot0_word0=0x0010) -> NativeGameState:
    pool = ObjectPool(
        base=GAMEPLAY_OBJECT_TABLE_BASE,
        stride=4,
        slots=((pool_slot0_word0, 0x0000), (0x0000, 0x0000)),
    )
    effect = ObjectPool(
        base=EFFECT_OBJECT_TABLE_BASE,
        stride=4,
        slots=((effect_slot0_word0, 0x0000),),
    )
    return NativeGameState(
        object_pool=pool,
        effect_pool=effect,
        camera=CameraState(x=camera_xy[0], y=camera_xy[1]),
        hud=HudLayer(counters=(0, 0, 0, 0, 0, 0), score_bcd=score),
    )


def test_native_game_state_mismatches_empty_when_equal():
    assert native_game_state_mismatches(_state(), _state()) == ()


def test_native_game_state_mismatches_reports_each_substate():
    base = _state()
    # camera drift
    assert native_game_state_mismatches(_state(camera_xy=(0x11, 0x20)), base) == (
        ("camera", "x", 0x11, 0x10),
    )
    # score (ScoreState) drift
    assert native_game_state_mismatches(_state(score=(0x0990, 0x0004)), base) == (
        ("hud", "score_bcd[1]", 0x0004, 0x0003),
    )
    # object-pool slot drift (byte-faithful per word)
    assert native_game_state_mismatches(_state(pool_slot0_word0=0x0002), base) == (
        ("object_pool", "slot[0].word[0x0]", 0x0002, 0x0001),
    )
    # effect-pool slot drift (the second object table)
    assert native_game_state_mismatches(_state(effect_slot0_word0=0x0011), base) == (
        ("effect_pool", "slot[0].word[0x0]", 0x0011, 0x0010),
    )


def test_native_game_state_mismatches_reports_pool_layout_change():
    a = _state()
    b = NativeGameState(
        object_pool=ObjectPool(base=a.object_pool.base, stride=8, slots=a.object_pool.slots),
        effect_pool=a.effect_pool,
        camera=a.camera,
        hud=a.hud,
    )
    assert native_game_state_mismatches(a, b) == (
        ("object_pool", "layout", (GAMEPLAY_OBJECT_TABLE_BASE, 4), (GAMEPLAY_OBJECT_TABLE_BASE, 8)),
    )


def _planted_vm() -> Memory:
    mem = Memory()
    mem.ww(DS, VIEW_TARGET_X, 0x0050)
    mem.ww(DS, VIEW_TARGET_Y, 0xFFF0)  # signed -16
    mem.ww(DS, SCORE_BCD_BASE, 0x0990)
    mem.ww(DS, SCORE_BCD_BASE + 2, 0x0003)
    for i in range(FRAME_TIMER_COUNT):
        mem.ww(DS, FRAME_TIMER_TABLE_BASE + 2 * i, i)
    mem.ww(DS, GAMEPLAY_OBJECT_TABLE_BASE, 0x0001)  # one active gameplay slot
    return mem


def test_read_native_game_state_round_trips_to_zero_mismatches():
    mem = _planted_vm()
    state = read_native_game_state(mem, DS)
    # A state read from the VM mirrors that same VM with zero divergence (§1.2).
    assert native_game_state_mismatches(state, read_native_game_state(mem, DS)) == ()
    assert state.camera == CameraState(x=0x50, y=-16)
    assert state.hud.score_bcd == (0x0990, 0x0003)


def test_read_native_game_state_detects_vm_drift_after_capture():
    mem = _planted_vm()
    captured = read_native_game_state(mem, DS)
    # The VM then advances (camera moves); the captured native state no longer mirrors it.
    mem.ww(DS, VIEW_TARGET_X, 0x0058)
    assert native_game_state_mismatches(captured, read_native_game_state(mem, DS)) == (
        ("camera", "x", 0x50, 0x58),
    )


def test_advance_hud_score_is_the_native_score_producer():
    hud = HudLayer(counters=(1, 2, 3, 4, 5, 6), score_bcd=(0x0990, 0x0003))  # 30990
    advanced = advance_hud_score(hud, 0x0010)  # + 10 (BCD)
    assert advanced.score_bcd == (0x1000, 0x0003)  # 31000
    assert advanced.counters == (1, 2, 3, 4, 5, 6)  # counters untouched
    # Carry across the word boundary (byte1 -> byte2): 9990 + 10 = 10000.
    rolled = advance_hud_score(HudLayer(counters=(), score_bcd=(0x9990, 0x0000)), 0x0010)
    assert rolled.score_bcd == (0x0000, 0x0001)

