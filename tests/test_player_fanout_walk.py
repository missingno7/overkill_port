"""Unit tests for the A067 child schedule walks native_a3ca / native_a3ff (the threading + dispatch)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import native_a3ca, native_a3ff

BASE, STRIDE = 0x2B5C, 0x38
_FREE = (0x0000,) * 0x1C   # active_word 0 -> free


def _pool(free_slots: int) -> ObjectPool:
    return ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * free_slots)


def _coords(*schedules) -> dict:
    c = {}
    for k, si in enumerate(schedules):
        c[(si + 2) & 0xFFFF] = 0x40 + k * 4   # [si+2] = X
        c[(si + 4) & 0xFFFF] = 0x50 + k * 4   # [si+4] = Y (the variant adds +4)
    return c


def test_a3ca_walks_four_sources_threaded():
    sched = (0x1000, 0x1010, 0x1020, 0x1030)
    coords = _coords(*sched)
    result = native_a3ca(_pool(8), BASE, 0, sched, 0, lambda off: coords.get(off & 0xFFFF, 0))
    assert len(result.spawns) == 4
    assert [s.slot_offset for s in result.spawns] == [BASE + i * STRIDE for i in range(4)]  # threaded, distinct
    assert result.final_cursor == BASE + 3 * STRIDE
    assert [s.x_word for s in result.spawns] == [0x40, 0x44, 0x48, 0x4C]   # each X = its [si+2]


def test_a3ca_skips_absent_sources():
    sched = (0x1000, 0xFFFF, 0x1020, 0xFFFF)   # two present, two empty
    coords = {0x1002: 0x40, 0x1004: 0x50, 0x1022: 0x60, 0x1024: 0x70}
    result = native_a3ca(_pool(8), BASE, 0, sched, 0, lambda off: coords.get(off & 0xFFFF, 0))
    assert len(result.spawns) == 2


def test_a3ca_state5_spawns_nothing():
    sched = (0x1000, 0x1010, 0x1020, 0x1030)
    result = native_a3ca(_pool(8), BASE, 5, sched, 0, lambda off: 0)
    assert result.spawns == () and result.final_cursor == BASE


def test_a3ca_pair_state_two_slots_per_source():
    # state 3 (A464 pair) -> each present source spawns two slots
    sched = (0x1000, 0x1010)
    coords = _coords(*sched)
    result = native_a3ca(_pool(8), BASE, 3, sched, 0, lambda off: coords.get(off & 0xFFFF, 0))
    assert len(result.spawns) == 4   # two sources x two slots
    assert all(s.logic_id == 0x0007 for s in result.spawns)   # A464 logic override


def test_a3ff_two_sources_a378_gated_off():
    sched = (0x1000, 0x1010)
    coords = _coords(*sched)
    # A95E == 0 -> the A378 follow-up is gated off -> only the two A41A shots
    result = native_a3ff(_pool(8), BASE, 0, sched, 0, 0, 0, lambda off: coords.get(off & 0xFFFF, 0))
    assert len(result.spawns) == 2


def test_a3ff_a378_fires_when_gates_open():
    sched = (0x1000,)
    coords = _coords(*sched)
    # A95E != 0 and A3A4 == 0 -> the A378 follow-up fires (two slots) after the one A41A shot
    result = native_a3ff(_pool(8), BASE, 0, sched, 0, 1, 0, lambda off: coords.get(off & 0xFFFF, 0))
    assert len(result.spawns) == 3   # 1 A41A + 2 A378 follow-ups, all threaded
    assert len({s.slot_offset for s in result.spawns}) == 3
