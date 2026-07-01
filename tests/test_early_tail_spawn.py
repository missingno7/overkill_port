"""Unit tests for the A067 early fire tails (A19F single / A1C8 pair) + the A1AE muzzle projection."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import (
    A1AE_OFFSET_TABLE,
    A18A_SPRITE,
    A1C8_SECOND_SHOT,
    A1C8_SLOT1_SPRITE,
    a1ae_project,
    native_a18a,
    native_a19f_tail,
    native_a1c8_tail,
    object_spawn_seed_a4ea,
)

BASE, STRIDE = 0x2B5C, 0x38
_FREE = (0x0000,) * 0x1C


def _pool(free_slots: int) -> ObjectPool:
    return ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * free_slots)


# index 0 -> the A3A8 table entry at A1AE_OFFSET_TABLE; X offset 8, Y offset 4
_A1AE_TABLE = {A1AE_OFFSET_TABLE & 0xFFFF: 0x0008, (A1AE_OFFSET_TABLE + 2) & 0xFFFF: 0x0004}


def _read(off):
    return _A1AE_TABLE.get(off & 0xFFFF, 0)


def test_a1ae_project_is_table_offset_plus_source():
    off = (A1AE_OFFSET_TABLE + (3 << 2)) & 0xFFFF      # index 3 -> table entry at A3A8 + 12
    table = {off: 0x0010, (off + 2) & 0xFFFF: 0x0020}
    x, y = a1ae_project(lambda o: table.get(o & 0xFFFF, 0), source_index=3, source_x=0x0100, source_y=0x0080)
    assert (x, y) == (0x0110, 0x00A0)                  # (0x10 + 0x100, 0x20 + 0x80)


def test_native_a19f_seed_plus_projected_coords():
    seed = object_spawn_seed_a4ea()
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=((0x0000,) * 0x1C,))  # one free slot
    table = {A1AE_OFFSET_TABLE & 0xFFFF: 0x0008, (A1AE_OFFSET_TABLE + 2) & 0xFFFF: 0x0004}  # index 0
    shot = native_a19f_tail(pool, BASE, 0, 0x0050, 0x0060, lambda o: table.get(o & 0xFFFF, 0))
    assert shot is not None
    assert (shot.x_word, shot.y_word) == (0x0058, 0x0064)            # source + the A3A8 offset
    assert shot.sprite_or_state == seed.sprite_or_state             # A19F applies no sprite override
    assert (shot.logic_id, shot.direction_or_step) == (seed.logic_id, seed.direction_or_step)
    assert shot.slot_offset == BASE and shot.new_cursor == BASE


def test_native_a19f_full_pool_returns_none():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=((0x0001,) + (0x0000,) * 0x1B,))   # occupied
    assert native_a19f_tail(pool, BASE, 0, 0x0050, 0x0060, lambda o: 0) is None


# --- A18A (the a958==1 A0E8-table tail): A19F with sprite 33h ---

def test_native_a18a_seed_shot_with_sprite_33():
    seed = object_spawn_seed_a4ea()
    shot = native_a18a(_pool(1), BASE, 0, 0x0050, 0x0060, _read)   # index 0 -> +8/+4 offsets
    assert shot is not None
    assert (shot.x_word, shot.y_word) == (0x0058, 0x0064)          # same A1AE muzzle as A19F
    assert shot.sprite_or_state == A18A_SPRITE == 0x0033           # the only difference from A19F
    assert (shot.logic_id, shot.direction_or_step) == (seed.logic_id, seed.direction_or_step)
    assert shot.slot_offset == BASE and shot.new_cursor == BASE


def test_native_a18a_full_pool_returns_none():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=((0x0001,) + (0x0000,) * 0x1B,))   # occupied
    assert native_a18a(pool, BASE, 0, 0x0050, 0x0060, _read) is None


# --- A1C8 (the A958 == 2 early tail): two threaded shots at the same A1AE muzzle ---

def test_native_a1c8_two_threaded_slots_same_coords():
    seed = object_spawn_seed_a4ea()
    slot1, slot2 = native_a1c8_tail(_pool(8), BASE, 0, 0x0050, 0x0060, 0x00, _read)
    # both placed at the SAME A1AE-projected muzzle (source + the index-0 A3A8 offset)
    assert (slot1.x_word, slot1.y_word) == (0x0058, 0x0064)
    assert (slot2.x_word, slot2.y_word) == (0x0058, 0x0064)
    # threaded onto distinct slots; the cursor parks on the second
    assert slot1.slot_offset == BASE and slot2.slot_offset == BASE + STRIDE
    assert slot2.new_cursor == BASE + STRIDE
    # slot1 keeps the seed direction; sprite forced to 18h; logic_id the seed's
    assert slot1.sprite_or_state == A1C8_SLOT1_SPRITE
    assert slot1.direction_or_step == seed.direction_or_step
    assert slot1.logic_id == seed.logic_id and slot2.logic_id == seed.logic_id


def test_native_a1c8_second_shot_bit1():
    _, slot2 = native_a1c8_tail(_pool(8), BASE, 0, 0x0050, 0x0060, 0x02, _read)
    assert (slot2.direction_or_step, slot2.sprite_or_state) == A1C8_SECOND_SHOT[0x02]
    assert (slot2.direction_or_step, slot2.sprite_or_state) == (0x0007, 0x001F)


def test_native_a1c8_second_shot_bit0():
    _, slot2 = native_a1c8_tail(_pool(8), BASE, 0, 0x0050, 0x0060, 0x01, _read)
    assert (slot2.direction_or_step, slot2.sprite_or_state) == (0x0001, 0x0019)


def test_native_a1c8_second_shot_neither_bit():
    _, slot2 = native_a1c8_tail(_pool(8), BASE, 0, 0x0050, 0x0060, 0x00, _read)
    assert (slot2.direction_or_step, slot2.sprite_or_state) == (0x0000, A1C8_SLOT1_SPRITE)


def test_native_a1c8_bit1_takes_priority_over_bit0():
    # both input bits set -> bit1 (test ds:[98BE],2 first) wins -> 7/1Fh
    _, slot2 = native_a1c8_tail(_pool(8), BASE, 0, 0x0050, 0x0060, 0x03, _read)
    assert (slot2.direction_or_step, slot2.sprite_or_state) == (0x0007, 0x001F)


def test_native_a1c8_high_byte_of_input_ignored():
    # only the low byte of DS:98BE is tested (test ds:[98BE],imm8) -> 0x0200 reads as no bits
    _, slot2 = native_a1c8_tail(_pool(8), BASE, 0, 0x0050, 0x0060, 0x0200, _read)
    assert (slot2.direction_or_step, slot2.sprite_or_state) == (0x0000, A1C8_SLOT1_SPRITE)


def test_native_a1c8_full_pool_returns_none():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=((0x0001,) + (0x0000,) * 0x1B,))   # occupied
    assert native_a1c8_tail(pool, BASE, 0, 0x0050, 0x0060, 0x00, _read) is None


def test_native_a1c8_one_free_slot_returns_none():
    # only one free slot -> the first shot takes it, the second allocation fails -> None
    assert native_a1c8_tail(_pool(1), BASE, 0, 0x0050, 0x0060, 0x00, _read) is None
