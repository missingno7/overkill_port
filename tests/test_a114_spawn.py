"""Unit tests for the A067 A114 three-shot burst (native_a114)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import (
    A114_LOGIC,
    A114_SUBSTATE,
    native_a114,
    object_spawn_seed_a4ea,
)

BASE, STRIDE = 0x2B5C, 0x38
_FREE = (0x0000,) * 0x1C
# [A96E] = the schedule pointer 0x1000; X0 = [0x1002], Y0 = [0x1004]
_SCHED = {0xA96E: 0x1000, 0x1002: 0x0050, 0x1004: 0x0060}


def _pool(free_slots: int) -> ObjectPool:
    return ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * free_slots)


def _read(off):
    return _SCHED.get(off & 0xFFFF, 0)


def test_native_a114_three_threaded_shots():
    seed = object_spawn_seed_a4ea()
    shots = native_a114(_pool(8), BASE, 0, _read)
    assert len(shots) == 3
    # per-shot {X0+dx, Y0+dy}: X0=0x50, Y0=0x60
    assert [(s.x_word, s.y_word) for s in shots] == [(0x004A, 0x0064), (0x004E, 0x005C), (0x004E, 0x006C)]
    # threaded onto distinct slots; the cursor parks on the third
    assert [s.slot_offset for s in shots] == [BASE, BASE + STRIDE, BASE + 2 * STRIDE]
    assert shots[-1].new_cursor == BASE + 2 * STRIDE
    # all three: logic 0Ch, substate 7, seed sprite (32h) kept
    assert all(s.logic_id == A114_LOGIC for s in shots)
    assert all(s.substate == A114_SUBSTATE for s in shots)
    assert all(s.sprite_or_state == seed.sprite_or_state for s in shots)


def test_native_a114_per_shot_directions():
    shots = native_a114(_pool(8), BASE, 0, _read)
    seed = object_spawn_seed_a4ea()
    # shot 1 keeps the seed direction; shot 2 -> 7; shot 3 -> 1
    assert [s.direction_or_step for s in shots] == [seed.direction_or_step, 0x0007, 0x0001]


def test_native_a114_gate_closed_returns_none():
    assert native_a114(_pool(8), BASE, 0x0001, _read) is None


def test_native_a114_full_pool_returns_none():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=((0x0001,) + (0x0000,) * 0x1B,))   # occupied
    assert native_a114(pool, BASE, 0, _read) is None


def test_native_a114_two_free_slots_emits_committed_two():
    # only two free slots: shots 1-2 are find_free-allocated (cursor parks on shot 2); the third overflows
    # to the 7550 recycle (unmodelled) without moving DS:95DA, so native emits the committed two -- not None.
    shots = native_a114(_pool(2), BASE, 0, _read)
    assert shots is not None and len(shots) == 2
    assert [s.slot_offset for s in shots] == [BASE, BASE + STRIDE]
    assert shots[-1].new_cursor == BASE + STRIDE
    assert all(s.logic_id == A114_LOGIC for s in shots)
