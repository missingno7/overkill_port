"""Unit tests for the A067 A958==5 listed two-slot spawn (native_a2a0)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import (
    A1AE_OFFSET_TABLE,
    A2A0_LOGIC,
    A2A0_SLOT1_SPRITE,
    A2A0_SLOT2_SPRITE,
    native_a2a0,
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


def test_native_a2a0_two_slots_aligned_and_stamped():
    seed = object_spawn_seed_a4ea()
    # a1ae: x = 0x50+8 = 0x58, y = 0x63+4 = 0x67 -> y_base = 0x67 & ~7 = 0x60
    r = native_a2a0(_pool(8), BASE, 0, 0x0050, 0x0063, 0, _read)
    assert r is not None
    slot1, slot2 = r.spawns
    assert (slot1.x_word, slot1.y_word) == (0x0058, 0x0060)     # slot1 Y = y_base
    assert (slot2.x_word, slot2.y_word) == (0x0058, 0x0068)     # slot2 Y = y_base + 8
    assert slot1.sprite_or_state == A2A0_SLOT1_SPRITE and slot2.sprite_or_state == A2A0_SLOT2_SPRITE
    assert (A2A0_SLOT1_SPRITE, A2A0_SLOT2_SPRITE) == (0x006A, 0x006C)
    assert slot1.logic_id == A2A0_LOGIC and slot2.logic_id == A2A0_LOGIC
    assert slot1.direction_or_step == seed.direction_or_step     # A2D6/A2A0 do not touch direction
    assert slot1.slot_offset == BASE and slot2.slot_offset == BASE + STRIDE


def test_native_a2a0_list_words_and_advance():
    r = native_a2a0(_pool(8), BASE, 0, 0x0050, 0x0063, 0, _read)
    # word 0 = slot1 offset, word 1 = slot2 offset, the remaining 24 = the FFFFh sentinel
    assert r.list_words[0] == BASE and r.list_words[1] == BASE + STRIDE
    assert set(r.list_words[2:]) == {0xFFFF}
    assert len(r.list_words) == 26
    assert r.list_advance == 4                                   # two 2-byte appends
    assert r.final_cursor == BASE + STRIDE


def test_native_a2a0_gate_closed_returns_none():
    assert native_a2a0(_pool(8), BASE, 0, 0x0050, 0x0063, 0x0001, _read) is None


def test_native_a2a0_full_pool_returns_none():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=((0x0001,) + (0x0000,) * 0x1B,))   # occupied
    assert native_a2a0(pool, BASE, 0, 0x0050, 0x0063, 0, _read) is None


def test_native_a2a0_one_free_slot_returns_none():
    assert native_a2a0(_pool(1), BASE, 0, 0x0050, 0x0063, 0, _read) is None
