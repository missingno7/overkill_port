"""Fast (VM-free) tests for the special-weapon deploy (native_frame._deploy_weapon_9f1a).

Pins the 9F1A/9F20 tracker selection ([A962] then [A964], no-op when both full) and the 9F41 stamp.
The byte-exact-vs-the-original proof over the demo is overkill.probes.verify_native_special_weapon_apply
(PASS: markers 1=44AF + 2=84C3, 4/4 applies, 0 diverging).
"""
from __future__ import annotations

from overkill.native_frame import _deploy_weapon_9f1a
from overkill.recovered.adapters.behavior_walk import EFFECT_POOL_BASE
from overkill.recovered.adapters.flat_memory import MutFlatMemory

DS = 0x25CC
STAMP = {0x00: 1, 0x0A: 1, 0x08: 0x14, 0x14: 1, 0x16: 1, 0x20: 0x50}


def _fresh():
    mem = MutFlatMemory(bytes(0x100000))
    mem.ww(DS, 0xA962, 0xFFFF)
    mem.ww(DS, 0xA964, 0xFFFF)
    mem.ww(DS, 0x95D8, EFFECT_POOL_BASE)     # alloc cursor at the pool head
    return mem


def _assert_stamp(mem, slot):
    for off, val in STAMP.items():
        assert mem.rw(DS, (slot + off) & 0xFFFF) == val, hex(off)


def test_first_deploy_fills_a962_and_stamps():
    mem = _fresh()
    _deploy_weapon_9f1a(mem)
    slot = mem.rw(DS, 0xA962)
    assert slot == EFFECT_POOL_BASE          # first free effect slot
    assert mem.rw(DS, 0xA964) == 0xFFFF       # second tracker untouched
    _assert_stamp(mem, slot)


def test_second_deploy_fills_a964():
    mem = _fresh()
    _deploy_weapon_9f1a(mem)
    _deploy_weapon_9f1a(mem)
    s1, s2 = mem.rw(DS, 0xA962), mem.rw(DS, 0xA964)
    assert s1 != 0xFFFF and s2 != 0xFFFF and s1 != s2
    _assert_stamp(mem, s2)


def test_third_deploy_is_a_noop_when_both_trackers_full():
    mem = _fresh()
    _deploy_weapon_9f1a(mem)
    _deploy_weapon_9f1a(mem)
    before = (mem.rw(DS, 0xA962), mem.rw(DS, 0xA964))
    _deploy_weapon_9f1a(mem)                  # 9F40: both occupied -> ret
    assert (mem.rw(DS, 0xA962), mem.rw(DS, 0xA964)) == before
