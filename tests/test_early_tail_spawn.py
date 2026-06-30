"""Unit tests for the A067 A19F early fire tail + the A1AE muzzle projection."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import (
    A1AE_OFFSET_TABLE,
    a1ae_project,
    native_a19f_tail,
    object_spawn_seed_a4ea,
)

BASE, STRIDE = 0x2B5C, 0x38


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
