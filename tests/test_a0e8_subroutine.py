"""Unit tests for the A0E8 subroutine composition (native_a0e8_subroutine)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import (
    A1AE_OFFSET_TABLE,
    native_a0e8_subroutine,
)

BASE, STRIDE = 0x2B5C, 0x38
_FREE = (0x0000,) * 0x1C
_NO_A114 = 0xFFFF   # DS:A96E == FFFFh -> no A114 pre-call
# A1AE table (index 0): X off 8, Y off 4.  A114 schedule ptr 0x1000 -> X0=[1002], Y0=[1004].
_TABLE = {A1AE_OFFSET_TABLE & 0xFFFF: 0x0008, (A1AE_OFFSET_TABLE + 2) & 0xFFFF: 0x0004,
          0xA96E: 0x1000, 0x1002: 0x0040, 0x1004: 0x0050}


def _pool(free_slots: int) -> ObjectPool:
    return ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * free_slots)


def _read(off):
    return _TABLE.get(off & 0xFFFF, 0)


def _run(pool, *, a958, a96e=_NO_A114, a3a6=0, a3a0=0, input_98be=0):
    return native_a0e8_subroutine(pool, BASE, a958=a958, a96e=a96e, a3a6=a3a6, a3a0=a3a0,
                                  source_index=0, source_x=0x0050, source_y=0x0060,
                                  input_98be=input_98be, read_ds_word=_read)


def test_a0e8_state0_a19f_single():
    r = _run(_pool(8), a958=0)
    assert len(r.spawns) == 1 and r.spawns[0].sprite_or_state == 0x0032   # A19F keeps the seed sprite
    assert r.final_cursor == BASE


def test_a0e8_state1_a18a_single():
    r = _run(_pool(8), a958=1)
    assert len(r.spawns) == 1 and r.spawns[0].sprite_or_state == 0x0033   # A18A sprite 33h


def test_a0e8_state2_a1c8_pair():
    r = _run(_pool(8), a958=2)
    assert len(r.spawns) == 2 and r.final_cursor == BASE + STRIDE


def test_a0e8_state3_a337_pair():
    r = _run(_pool(8), a958=3)
    assert len(r.spawns) == 2
    assert all(s.logic_id == 0x0007 and s.sprite_or_state == 0x0037 for s in r.spawns)


def test_a0e8_state4_a2f6_pair():
    r = _run(_pool(8), a958=4)
    assert all(s.logic_id == 0x0008 and s.sprite_or_state == 0x0035 for s in r.spawns)


def test_a0e8_pair_gated_off_when_a3a0_nonzero():
    # the a958 3/4 muzzle pair is gated by A3A0 == 0; nonzero -> no tail spawn
    assert _run(_pool(8), a958=3, a3a0=1).spawns == ()


def test_a0e8_state5_is_dead_returns_none():
    assert _run(_pool(8), a958=5) is None
    assert _run(_pool(8), a958=6) is None


def test_a0e8_a114_precall_then_tail():
    # A96E present + A3A6 gate open -> the A114 three-shot burst THEN the a958=0 tail = 4 shots, threaded
    r = _run(_pool(8), a958=0, a96e=0x1000, a3a6=0)
    assert len(r.spawns) == 4
    assert [s.slot_offset for s in r.spawns] == [BASE + i * STRIDE for i in range(4)]
    assert r.final_cursor == BASE + 3 * STRIDE
    assert all(s.logic_id == 0x000C for s in r.spawns[:3])       # the 3 A114 burst shots (logic 0Ch)


def test_a0e8_a114_gated_off_leaves_only_tail():
    # A96E present but A3A6 != 0 -> A114 does not spawn; only the a958=0 tail
    r = _run(_pool(8), a958=0, a96e=0x1000, a3a6=1)
    assert len(r.spawns) == 1
