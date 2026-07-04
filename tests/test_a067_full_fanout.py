"""Unit tests for the A067 FULL fan-out capstone (native_a067_full_fanout) -- structure + threading.

Byte-exact correctness is covered by verify_native_a067_full_fanout (L6 58/58); these lock the
composition wiring: the counter copy (with its crossed last pair), the cross-child threading, and the
a958 >= 5 gap.
"""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import A1AE_OFFSET_TABLE, native_a067_full_fanout

BASE, STRIDE = 0x2B5C, 0x38
EFFECT_BASE = 0x23B4
_FREE = (0x0000,) * 0x1C
_NO_SRC = 0xFFFF
# A1AE table (index 0) for the A0E8 A19F tail; a present A3FF mirror source 0x1000 -> X0=[1002], Y0=[1004].
_TABLE = {A1AE_OFFSET_TABLE & 0xFFFF: 0x0008, (A1AE_OFFSET_TABLE + 2) & 0xFFFF: 0x0004,
          0x1002: 0x0040, 0x1004: 0x0050}


def _read(off):
    return _TABLE.get(off & 0xFFFF, 0)


def _run(*, gp_free=8, **kw):
    defaults = dict(a970=0x0011, a972=0x0022, a976=0x0033, a974=0x0044, a95e=0, a960=0, a97e=0,
                    a958=0, a96e=_NO_SRC, input_98be=0, source_index=0, source_x=0x0050, source_y=0x0060,
                    mirror_schedule=(_NO_SRC, _NO_SRC), side_schedule=(_NO_SRC,) * 4)
    defaults.update(kw)
    gp = ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * gp_free)
    eff = ObjectPool(base=EFFECT_BASE, stride=STRIDE, slots=(_FREE,) * 0x23)
    return native_a067_full_fanout(gp, eff, BASE, EFFECT_BASE, read_ds_word=_read, **defaults)


def test_counter_copy_crossed_last_pair():
    # a3a0<-a970, a3a2<-a972, a3a4<-a976, a3a6<-a974 (the last pair is crossed vs address order)
    r = _run()
    assert (r.a3a0, r.a3a2, r.a3a4, r.a3a6) == (0x0011, 0x0022, 0x0033, 0x0044)


def test_all_gated_off_but_a0e8_tail():
    # A515 (a960==0) + A584 (a95e==0) gated off, both walks empty -> only the A0E8 a958=0 (A19F) tail
    r = _run()
    assert len(r.spawns) == 1 and r.spawns[0].slot_offset == BASE
    assert r.final_cursor == BASE


def test_a3ff_then_a0e8_tail_threaded():
    # one present A3FF mirror source (a958=0 single) THEN the A0E8 a958=0 tail -> 2 threaded shots
    r = _run(mirror_schedule=(0x1000, _NO_SRC))
    assert len(r.spawns) == 2
    assert [s.slot_offset for s in r.spawns] == [BASE, BASE + STRIDE]   # distinct, threaded
    assert r.final_cursor == BASE + STRIDE


def test_a958_dead_state_returns_none():
    assert _run(a958=5) is None
    assert _run(a958=6) is None


def test_a515_state_passthrough_when_gated():
    # A515 gate closed (a960==0) -> its scan state is unchanged (a960/a97e/a43a pass through)
    r = _run(a960=0, a97e=0)
    assert r.a960 == 0 and r.a97e == 0 and r.cursor_a43a == EFFECT_BASE


def test_native_a067_composes_full_fanout_when_threaded():
    # native_a067's FULL path (scroll > 0xB6) delegates to native_a067_full_fanout when the caller threads
    # its state -- the shots + cursor match the capstone directly, and full_result rides back for threading.
    from overkill.recovered.systems.action_spawns import native_a067
    gp = ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * 8)
    eff = ObjectPool(base=EFFECT_BASE, stride=STRIDE, slots=(_FREE,) * 0x23)
    full = dict(effect_pool=eff, cursor_a43a=EFFECT_BASE, a970=0x11, a972=0x22, a976=0x33, a974=0x44,
                a95e=0, a960=0, a97e=0, a96e=_NO_SRC, mirror_schedule=(0x1000, _NO_SRC),
                side_schedule=(_NO_SRC,) * 4)
    # armed fire, FULL path: scroll 0x100 > 0xB6
    res = native_a067(gp, BASE, input_98be=0x10, latch_a980=0, repeat_9790=0, state_232a=0,
                      scroll_2350=0x100, bdac=0, a958=0, be06=0, source_index=0, source_x=0x50,
                      source_y=0x60, read_ds_word=_read, **full)
    ref = native_a067_full_fanout(gp, eff, BASE, EFFECT_BASE, read_ds_word=_read,
                                  a970=0x11, a972=0x22, a976=0x33, a974=0x44, a95e=0, a960=0, a97e=0,
                                  a958=0, a96e=_NO_SRC, input_98be=0x10, source_index=0, source_x=0x50,
                                  source_y=0x60, mirror_schedule=(0x1000, _NO_SRC),
                                  side_schedule=(_NO_SRC,) * 4)
    assert res is not None and res.ran_fanout and res.new_a980 == 1
    assert res.spawns == ref.spawns and res.final_cursor == ref.final_cursor
    assert res.full_result == ref   # the threaded counters + A515 scan state ride back for the caller


def test_native_a067_full_path_declines_when_not_threaded():
    # backward-compatible: without the FULL inputs, the FULL path still returns None (VM owns the frame)
    from overkill.recovered.systems.action_spawns import native_a067
    gp = ObjectPool(base=BASE, stride=STRIDE, slots=(_FREE,) * 8)
    res = native_a067(gp, BASE, input_98be=0x10, latch_a980=0, repeat_9790=0, state_232a=0,
                      scroll_2350=0x100, bdac=0, a958=0, be06=0, source_index=0, source_x=0x50,
                      source_y=0x60, read_ds_word=_read)
    assert res is None
