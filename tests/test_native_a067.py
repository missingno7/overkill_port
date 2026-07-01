"""Unit tests for the composed A067 entry gate + EARLY spawn dispatch (native_a067)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.action_spawns import native_a067
from overkill.recovered.systems.objects import A1AE_OFFSET_TABLE

BASE, STRIDE = 0x2B5C, 0x38
_FREE = (0x0000,) * 0x1C
# index 0 -> the A3A8 table entry: X offset 8, Y offset 4
_A1AE_TABLE = {A1AE_OFFSET_TABLE & 0xFFFF: 0x0008, (A1AE_OFFSET_TABLE + 2) & 0xFFFF: 0x0004}


def _read(off):
    return _A1AE_TABLE.get(off & 0xFFFF, 0)


def _pool(free_slots: int) -> ObjectPool:
    return ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * free_slots)


def _call(pool, cursor=BASE, *, input_98be=0x10, latch_a980=0, repeat_9790=0, state_232a=0,
          scroll_2350=0x50, bdac=0, a958=0, be06=0, source_x=0x50, source_y=0x60):
    return native_a067(pool, cursor, input_98be=input_98be, latch_a980=latch_a980, repeat_9790=repeat_9790,
                       state_232a=state_232a, scroll_2350=scroll_2350, bdac=bdac, a958=a958, be06=be06,
                       source_index=0, source_x=source_x, source_y=source_y, read_ds_word=_read)


def test_native_a067_not_firing_clears_latch_no_spawn():
    r = _call(_pool(8), input_98be=0x00)     # trigger bit 4 clear
    assert r is not None
    assert r.new_a980 == 0 and r.spawns == () and r.ran_fanout is False
    assert r.final_cursor == BASE            # cursor untouched


def test_native_a067_held_non_repeatable_no_spawn():
    # pressed, but latch already armed + not repeatable (9790 != 1, 232A != 0Fh) -> gate does not run
    r = _call(_pool(8), input_98be=0x10, latch_a980=1, repeat_9790=0, state_232a=0)
    assert r.new_a980 == 1 and r.spawns == () and r.ran_fanout is False
    assert r.final_cursor == BASE


def test_native_a067_early_default_a19f_single():
    r = _call(_pool(8), a958=0)              # fresh press, EARLY, A958 != 2 -> A19F single
    assert r.new_a980 == 1 and r.ran_fanout is True
    assert len(r.spawns) == 1
    assert (r.spawns[0].x_word, r.spawns[0].y_word) == (0x0058, 0x0064)   # the A1AE muzzle
    assert r.final_cursor == BASE            # one allocation parks the cursor at the slot


def test_native_a067_early_state2_a1c8_pair():
    r = _call(_pool(8), a958=2)              # EARLY, A958 == 2 -> A1C8 pair
    assert r.new_a980 == 1 and r.ran_fanout is True
    assert len(r.spawns) == 2
    assert r.final_cursor == BASE + STRIDE   # two allocations


def test_native_a067_full_path_returns_none():
    # scroll > B6h -> the FULL fan-out, which native_a067 does not compose yet
    assert _call(_pool(8), scroll_2350=0x0100) is None


def test_native_a067_early_full_pool_returns_none():
    pool = ObjectPool(base=BASE, stride=STRIDE, slots=((0x0001,) + (0x0000,) * 0x1B,))   # occupied
    assert _call(pool) is None


def test_native_a067_repeat_byte_allows_rearm():
    # pressed + already-armed latch but repeat byte 9790 == 1 -> re-arms and fires
    r = _call(_pool(8), input_98be=0x10, latch_a980=1, repeat_9790=1)
    assert r.new_a980 == 1 and r.ran_fanout is True and len(r.spawns) == 1
