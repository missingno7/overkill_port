"""Unit tests for the A0E8 early-level muzzle pair tails A2F6 (A958==4) / A337 (A958==3)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import (
    A1AE_OFFSET_TABLE,
    A0E8_PAIR_TARGETS,
    a1ae_project,
    native_a0e8_pair,
    object_spawn_seed_a4ea,
)

BASE, STRIDE = 0x2B5C, 0x38
_FREE = (0x0000,) * 0x1C
# index 0 -> the A3A8 table entry at A1AE_OFFSET_TABLE; X offset 8, Y offset 4
_A1AE_TABLE = {A1AE_OFFSET_TABLE & 0xFFFF: 0x0008, (A1AE_OFFSET_TABLE + 2) & 0xFFFF: 0x0004}


def _pool(free_slots: int) -> ObjectPool:
    return ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * free_slots)


def _read(off):
    return _A1AE_TABLE.get(off & 0xFFFF, 0)


def test_native_a0e8_pair_state4_a2f6():
    seed = object_spawn_seed_a4ea()
    x, y = a1ae_project(_read, 0, 0x0050, 0x0060)
    assert (x, y) == (0x0058, 0x0064)
    slot1, slot2 = native_a0e8_pair(_pool(8), BASE, 0x0004, 0, 0x0050, 0x0060, 0, _read)
    # both at the A1AE muzzle, slot2.x = slot1.x + 8
    assert (slot1.x_word, slot1.y_word) == (0x0058, 0x0064)
    assert (slot2.x_word, slot2.y_word) == (0x0060, 0x0064)
    assert slot1.slot_offset == BASE and slot2.slot_offset == BASE + STRIDE
    assert slot2.new_cursor == BASE + STRIDE
    # state 4 stamp: logic_id 8, sprite 35h; both slots; seed direction kept
    assert (slot1.logic_id, slot1.sprite_or_state) == A0E8_PAIR_TARGETS[0x0004]
    assert (slot1.logic_id, slot1.sprite_or_state) == (0x0008, 0x0035)
    assert (slot2.logic_id, slot2.sprite_or_state) == (0x0008, 0x0035)
    assert slot1.direction_or_step == seed.direction_or_step


def test_native_a0e8_pair_state3_a337():
    slot1, slot2 = native_a0e8_pair(_pool(8), BASE, 0x0003, 0, 0x0050, 0x0060, 0, _read)
    assert (slot1.logic_id, slot1.sprite_or_state) == (0x0007, 0x0037)
    assert (slot2.logic_id, slot2.sprite_or_state) == (0x0007, 0x0037)
    assert slot2.x_word == slot1.x_word + 0x0008


def test_native_a0e8_pair_gate_closed_returns_none():
    assert native_a0e8_pair(_pool(8), BASE, 0x0004, 0, 0x0050, 0x0060, 0x0001, _read) is None


def test_native_a0e8_pair_non_pair_state_returns_none():
    for st in (0x0000, 0x0001, 0x0002, 0x0005):
        assert native_a0e8_pair(_pool(8), BASE, st, 0, 0x0050, 0x0060, 0, _read) is None


def test_native_a0e8_pair_full_pool_returns_none():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=((0x0001,) + (0x0000,) * 0x1B,))   # occupied
    assert native_a0e8_pair(pool, BASE, 0x0004, 0, 0x0050, 0x0060, 0, _read) is None


def test_native_a0e8_pair_one_free_slot_emits_committed_shot1():
    # One free slot: shot1 is find_free-allocated (DS:95DA parks at it); shot2 overflows to the 7550
    # recycle (unmodelled) WITHOUT moving the cursor, so the pair emits the committed (slot1,) -- not None.
    result = native_a0e8_pair(_pool(1), BASE, 0x0004, 0, 0x0050, 0x0060, 0, _read)
    assert result is not None and len(result) == 1
    (slot1,) = result
    assert slot1.slot_offset == BASE and slot1.new_cursor == BASE
    assert (slot1.x_word, slot1.y_word) == (0x0058, 0x0064)
    assert (slot1.logic_id, slot1.sprite_or_state) == (0x0008, 0x0035)
