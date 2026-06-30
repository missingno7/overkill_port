"""VM-free unit tests for native_a41a_shot -- the A41A single-slot player-shot spawn (A958 state 0/1/2).

Pins the A4D7/A490/A499 field stamps (A4EA seed + schedule coords + per-state sprite/direction) and the
None paths (multi-slot states, full pool).  Byte-exact confirmation vs the VM is verify_native_player_shot_spawn.
"""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import native_a41a_pair, native_a41a_shot, object_spawn_seed_a4ea

BASE, STRIDE = 0x2B5C, 0x38
_FREE = (0x0000,) + (0x0000,) * 0x1B   # active_word 0 -> free
_OCC = (0x0001,) + (0x0000,) * 0x1B    # active_word 1 -> occupied


def _pool_free_slot0() -> ObjectPool:
    return ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE, _OCC, _OCC, _OCC))


def _pool_free_slots01() -> ObjectPool:
    return ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE, _FREE, _OCC, _OCC))


def test_state0_a4d7_is_seed_plus_coords():
    seed = object_spawn_seed_a4ea()
    s = native_a41a_shot(_pool_free_slot0(), BASE, 0, 0x0050, 0x0060, 0xFFFF)
    assert s is not None
    assert s.slot_offset == BASE and s.new_cursor == BASE
    assert (s.x_word, s.y_word) == (0x0050, 0x0064)            # X = [si+2], Y = [si+4] + 4
    assert s.direction_or_step == seed.direction_or_step
    assert s.sprite_or_state == seed.sprite_or_state
    assert (s.logic_id, s.hazard_class, s.substate) == (seed.logic_id, seed.hazard_class, seed.substate)


def test_state1_a490_overrides_sprite():
    s = native_a41a_shot(_pool_free_slot0(), BASE, 1, 0x0050, 0x0060, 0xFFFF)
    assert s.sprite_or_state == 0x0033
    assert s.y_word == 0x0064


def test_state2_a499_direction_from_a3ec():
    s = native_a41a_shot(_pool_free_slot0(), BASE, 2, 0x0050, 0x0060, 0x0005)
    assert s.direction_or_step == 0x0005      # a3ec != FFFF -> used directly
    assert s.sprite_or_state == 0x001F        # direction != 1 -> 1Fh


def test_state2_a499_default_direction_low_y():
    s = native_a41a_shot(_pool_free_slot0(), BASE, 2, 0x0050, 0x0040, 0xFFFF)
    assert s.direction_or_step == 0x0007      # a3ec FFFF, source Y <= 58h -> 7
    assert s.sprite_or_state == 0x001F


def test_state2_a499_high_y_direction_one():
    s = native_a41a_shot(_pool_free_slot0(), BASE, 2, 0x0050, 0x0060, 0xFFFF)
    assert s.direction_or_step == 0x0001      # a3ec FFFF, source Y 60h > 58h -> 1
    assert s.sprite_or_state == 0x0019        # direction == 1 -> 19h


def test_multislot_and_tail_states_return_none():
    pool = _pool_free_slot0()
    assert native_a41a_shot(pool, BASE, 3, 0x50, 0x60, 0xFFFF) is None   # A464 pair
    assert native_a41a_shot(pool, BASE, 4, 0x50, 0x60, 0xFFFF) is None   # A438 pair
    assert native_a41a_shot(pool, BASE, 5, 0x50, 0x60, 0xFFFF) is None   # 44AF tail


def test_full_pool_returns_none():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=(_OCC, _OCC, _OCC, _OCC))
    assert native_a41a_shot(pool, BASE, 0, 0x50, 0x60, 0xFFFF) is None   # 7550 recycle not modelled


def test_state3_a464_pair_two_slots():
    seed = object_spawn_seed_a4ea()
    pair = native_a41a_pair(_pool_free_slots01(), BASE, 3, 0x0050, 0x0060, 0x0000)
    assert pair is not None
    s1, s2 = pair
    assert (s1.slot_offset, s2.slot_offset) == (BASE, BASE + STRIDE)   # second skips the first (now active)
    assert (s1.x_word, s2.x_word) == (0x0050, 0x0058)                  # second X = first + 8
    assert s1.y_word == 0x0064 and s2.y_word == 0x0064
    assert s1.logic_id == 0x0007 and s2.logic_id == 0x0007            # +18 override (A464)
    assert s1.sprite_or_state == 0x0037 and s2.sprite_or_state == 0x0037
    assert s1.active_word == seed.active_word and s1.hazard_class == seed.hazard_class


def test_state4_a438_pair_overrides():
    s1, s2 = native_a41a_pair(_pool_free_slots01(), BASE, 4, 0x0050, 0x0060, 0x0000)
    assert s1.logic_id == 0x0008 and s2.logic_id == 0x0008            # A438
    assert s1.sprite_or_state == 0x0035 and s2.sprite_or_state == 0x0035


def test_pair_gated_by_a3a0():
    assert native_a41a_pair(_pool_free_slots01(), BASE, 3, 0x50, 0x60, 0x0001) is None   # gate closed


def test_pair_needs_two_free_slots():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE, _OCC, _OCC, _OCC))
    assert native_a41a_pair(pool, BASE, 3, 0x50, 0x60, 0x0000) is None   # second alloc fails -> None


def test_pair_rejects_single_and_tail_states():
    pool = _pool_free_slots01()
    assert native_a41a_pair(pool, BASE, 0, 0x50, 0x60, 0x0000) is None   # single state
    assert native_a41a_pair(pool, BASE, 5, 0x50, 0x60, 0x0000) is None   # 44AF tail
