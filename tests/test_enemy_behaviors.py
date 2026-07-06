"""Behavior 0x20 (the planet-1 wave enemy) as a pure decision fn (systems/enemy_behaviors)."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.systems.enemy_behaviors import step_enemy_behavior_20

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
LIVE = ROOT / "artifacts" / "demos" / "demo_play_tandy_L1_start_20260618_143947" / "snapshot" / "memory_1mb.bin"

RING = tuple((0x10 * i, 0x20 + i) for i in range(20))


def _step(**over):
    base = dict(x_word=0x60, y_word=0x50, substate_1c=0xFFFF,
                target_x_34=0x60, target_y_32=0x50,
                a7a0=0x30, clock_2338=2, clock_2340=0x100, clock_232e=0,
                parity_2324=0, active_enemies_a47e=10, anchor_y_2380=0x58,
                ring_cursor_a842=0xA844, slot_ring=RING, random_value=1)
    base.update(over)
    return step_enemy_behavior_20(**base)


def test_approach_moves_toward_the_slot_with_the_clock_sprite():
    r = _step(x_word=0x40, a7a0=0x00, y_word=0x50)
    assert r.move_to_target and r.record_writes[0x06] == 4
    assert r.record_writes[0x08] == 0x7F - 2          # y < 0x60 -> descending sprite ramp
    r2 = _step(x_word=0x40, y_word=0x70, target_y_32=0x70)
    assert r2.record_writes[0x08] == 0x7A + 2         # y >= 0x60 -> ascending ramp


def test_arrival_idles_until_the_wave_clock_gate():
    r = _step(a7a0=0x22)
    assert not r.move_to_target and not r.shoot and 0x1C not in r.record_writes


def test_shoot_window_consumes_the_random_and_gates_on_its_low_bit():
    r = _step(clock_2340=0x2C0, random_value=2)
    assert r.random_stepped and r.shoot
    r2 = _step(clock_2340=0x2C0, random_value=3)
    assert r2.random_stepped and not r2.shoot
    r3 = _step(clock_2340=0x2D1, random_value=2)
    assert not r3.random_stepped and not r3.shoot


def test_dive_retarget_at_the_player_with_the_parity_gate():
    r = _step(active_enemies_a47e=3, parity_2324=0)
    assert r.record_writes[0x32] == (0x58 + 8) & 0xFFF8   # the anchor Y + 8, snapped
    assert r.record_writes[0x1C] == 0 and r.record_writes[0x08] == 0x78
    assert r.record_writes[0x34] == 0x20 and r.global_writes[0x2340] == 0x28
    # parity 1 keeps the OLD target y (still snapped)
    r2 = _step(active_enemies_a47e=3, parity_2324=1, target_y_32=0x53, y_word=0x53)
    assert r2.record_writes[0x32] == 0x53 & 0xFFF8
    # the 2340 < 5 variant dives regardless of enemy count, WITHOUT the parity gate
    r3 = _step(clock_2340=4, parity_2324=1)
    assert r3.record_writes[0x32] == (0x58 + 8) & 0xFFF8


def test_reshuffle_picks_the_next_ring_slot_skipping_the_current_position():
    r = _step(clock_232e=0x3F)
    assert r.record_writes[0x34] == RING[0][0] + 0x20 and r.record_writes[0x32] == RING[0][1]
    assert r.global_writes[0xA842] == 0xA848
    # already exactly at ring[0]'s slot -> the pick advances to ring[1]
    r2 = _step(clock_232e=0x3F, x_word=RING[0][0] + 0x20, y_word=RING[0][1],
               target_x_34=RING[0][0] + 0x20, target_y_32=RING[0][1])
    assert r2.record_writes[0x34] == RING[1][0] + 0x20
    assert r2.global_writes[0xA842] == 0xA84C
    # cursor at the end wraps to the base before reading
    r3 = _step(clock_232e=0x3F, ring_cursor_a842=0xA894)
    assert r3.record_writes[0x34] == RING[0][0] + 0x20


def test_substate_chain_reapproach_flash_and_exit():
    assert step_enemy_behavior_20 is not None
    r0 = _step(substate_1c=0, x_word=0x10)
    assert r0.move_to_target and r0.record_writes == {0x06: 4}
    r0b = _step(substate_1c=0)
    assert r0b.record_writes == {0x1C: 1}
    r1 = _step(substate_1c=1)
    assert r1.record_writes == {0x08: 0x79, 0x1C: 2}
    r2 = _step(substate_1c=2, x_word=0x98)
    assert r2.record_writes == {0x02: 0x9C}
    r2b = _step(substate_1c=2, x_word=0x9C)
    assert r2b.record_writes == {0x02: 0xA0, 0x08: 0x77}


@pytest.mark.skipif(not (BUNDLE.is_file() and LIVE.is_file()), reason="artifacts not present")
def test_slot_ring_is_static_cold_equals_live():
    from overkill.recovered.adapters.enemy_slot_ring_adapter import load_enemy_slot_ring

    cold = load_enemy_slot_ring(BUNDLE.read_bytes())
    assert len(cold) == 20
    assert cold == load_enemy_slot_ring(LIVE.read_bytes())


# behavior 0x28 (step_spawner_28): a 96AA-ramp anim spawner gated on [2332]/[A47E]/counter.
_SPAWNER_28_TABLE = tuple([0, 0, 1, 2, 3, 4] + [5] * 12 + [4, 3, 2, 1, 0, 0])  # the real DS:96AA ramp


def test_spawner_28_counter_advances_only_when_2332_zero_and_wraps():
    from overkill.recovered.systems.enemy_behaviors import step_spawner_28

    # [2332] != 0 -> counter frozen, sprite = table[counter] + 0x1C, no spawn
    r = step_spawner_28(counter_06=3, gate_2332=1, active_a47e=5, sprite_table=_SPAWNER_28_TABLE)
    assert r.counter == 3 and r.sprite == _SPAWNER_28_TABLE[3] + 0x1C and not r.spawn
    # [2332] == 0 -> counter advances; sprite reads the ADVANCED counter
    r = step_spawner_28(counter_06=3, gate_2332=0, active_a47e=5, sprite_table=_SPAWNER_28_TABLE)
    assert r.counter == 4 and r.sprite == _SPAWNER_28_TABLE[4] + 0x1C
    # wrap: counter 0x17 + 1 == 0x18 -> 0
    r = step_spawner_28(counter_06=0x17, gate_2332=0, active_a47e=5, sprite_table=_SPAWNER_28_TABLE)
    assert r.counter == 0


def test_spawner_28_spawn_gate_needs_no_enemies_and_counter_7_then_bumps():
    from overkill.recovered.systems.enemy_behaviors import step_spawner_28

    # counter reaches 7 (from 6, [2332]==0) with A47E==0 -> spawn, and the counter is bumped past 7
    r = step_spawner_28(counter_06=6, gate_2332=0, active_a47e=0, sprite_table=_SPAWNER_28_TABLE)
    assert r.spawn and r.counter == 8
    # same counter but enemies active -> no spawn, counter stays at 7
    r = step_spawner_28(counter_06=6, gate_2332=0, active_a47e=1, sprite_table=_SPAWNER_28_TABLE)
    assert not r.spawn and r.counter == 7
