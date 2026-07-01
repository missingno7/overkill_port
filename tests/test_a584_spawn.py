"""Unit tests for the A067 A584 dual-anchor spawn (the terrain-crawler pair, native_a584)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import (
    A584_SLOT1_LOGIC,
    A584_SLOT2_LOGIC,
    A584_SPRITE,
    native_a584,
    object_spawn_seed_a4ea,
)

BASE, STRIDE = 0x2B5C, 0x38
_FREE = (0x0000,) * 0x1C


def _pool(free_slots: int) -> ObjectPool:
    return ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * free_slots)


def test_native_a584_two_threaded_anchored_slots():
    seed = object_spawn_seed_a4ea()
    slot1, slot2 = native_a584(_pool(8), BASE, 0x0050, 0x0060, a95e=1, a3a4=0)
    # A571 anchor: X = src + 0xA on both axes, then Y &= ~3 (0x6A -> 0x68)
    assert (slot1.x_word, slot1.y_word) == (0x005A, 0x0068)
    assert (slot2.x_word, slot2.y_word) == (0x005A, 0x0068)
    # threaded onto distinct slots; the cursor parks on the second
    assert slot1.slot_offset == BASE and slot2.slot_offset == BASE + STRIDE
    assert slot2.new_cursor == BASE + STRIDE
    # both sprite 8; logic_id 5 (slot1) / 6 (slot2); direction the seed's
    assert slot1.sprite_or_state == A584_SPRITE and slot2.sprite_or_state == A584_SPRITE
    assert slot1.logic_id == A584_SLOT1_LOGIC and slot2.logic_id == A584_SLOT2_LOGIC
    assert (A584_SLOT1_LOGIC, A584_SLOT2_LOGIC) == (0x0005, 0x0006)
    assert slot1.direction_or_step == seed.direction_or_step


def test_native_a584_y_aligned_down_to_four():
    # source Y already 4-aligned -> +0xA stays unaligned (0x44 -> 0x4E -> 0x4C)
    slot1, _ = native_a584(_pool(8), BASE, 0x0000, 0x0044, a95e=1, a3a4=0)
    assert slot1.y_word == 0x004C            # (0x44 + 0xA) & ~3
    slot2_pool = native_a584(_pool(8), BASE, 0x0000, 0x0042, a95e=1, a3a4=0)
    assert slot2_pool[0].y_word == 0x004C    # (0x42 + 0xA = 0x4C) already aligned


def test_native_a584_gate_a95e_zero_returns_none():
    assert native_a584(_pool(8), BASE, 0x0050, 0x0060, a95e=0, a3a4=0) is None


def test_native_a584_gate_a3a4_nonzero_returns_none():
    # A3A4 != 0 -> a crawler pair is already alive -> no re-seed
    assert native_a584(_pool(8), BASE, 0x0050, 0x0060, a95e=1, a3a4=1) is None


def test_native_a584_full_pool_returns_none():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=((0x0001,) + (0x0000,) * 0x1B,))   # occupied
    assert native_a584(pool, BASE, 0x0050, 0x0060, a95e=1, a3a4=0) is None


def test_native_a584_one_free_slot_emits_committed_shot1():
    # the first shot takes the only slot (cursor parks there); the second overflows to the 7550 recycle
    # (unmodelled) without moving DS:95DA, so native emits the committed (slot1,) -- not None.
    result = native_a584(_pool(1), BASE, 0x0050, 0x0060, a95e=1, a3a4=0)
    assert result is not None and len(result) == 1
    (slot1,) = result
    assert slot1.slot_offset == BASE and slot1.new_cursor == BASE
    assert (slot1.x_word, slot1.y_word) == (0x005A, 0x0068)
    assert slot1.logic_id == A584_SLOT1_LOGIC and slot1.sprite_or_state == A584_SPRITE
