"""Fast (VM-free) tests for the special-weapon deploy (native_frame._deploy_weapon_9f1a).

Pins the 9F1A/9F20 tracker selection ([A962] then [A964], no-op when both full) and the 9F41 stamp.
The byte-exact-vs-the-original proof over the demo is overkill.probes.verify_native_special_weapon_apply
(PASS: markers 1=44AF + 2=84C3, 4/4 applies, 0 diverging).
"""
from __future__ import annotations

from overkill.native_frame import (
    _apply_flag_weapon_84d6,
    _deploy_weapon_9d91,
    _deploy_weapon_9f1a,
)
from overkill.recovered.adapters.behavior_walk import EFFECT_POOL_BASE
from overkill.recovered.adapters.flat_memory import MutFlatMemory

DS = 0x25CC
STAMP = {0x00: 1, 0x0A: 1, 0x08: 0x14, 0x14: 1, 0x16: 1, 0x20: 0x50}
STAMP_9D91 = {0x00: 1, 0x08: 0x0F, 0x14: 1, 0x16: 1, 0x20: 0x14}


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


def test_9d91_deploys_into_a96e_and_is_single_instance():
    mem = MutFlatMemory(bytes(0x100000))
    mem.ww(DS, 0xA96E, 0xFFFF)
    mem.ww(DS, 0x95D8, EFFECT_POOL_BASE)
    _deploy_weapon_9d91(mem)
    slot = mem.rw(DS, 0xA96E)
    assert slot == EFFECT_POOL_BASE
    for off, val in STAMP_9D91.items():
        assert mem.rw(DS, (slot + off) & 0xFFFF) == val, hex(off)
    # already deployed -> a second call is a no-op (9D96)
    _deploy_weapon_9d91(mem)
    assert mem.rw(DS, 0xA96E) == slot


def test_flag_weapon_sets_2384_and_the_gated_chirp():
    mem = MutFlatMemory(bytes(0x100000))
    mem.wb(DS, 0x98C0, 1)                     # [98C0] != 0 -> the chirp fires
    _apply_flag_weapon_84d6(mem, 2)
    assert mem.rw(DS, 0x2384) == 2 and mem.rb(DS, 0xBEFE) == 0 and mem.rb(DS, 0xBEFF) == 6

    mem2 = MutFlatMemory(bytes(0x100000))     # [98C0] == 0 -> no chirp
    _apply_flag_weapon_84d6(mem2, 1)
    assert mem2.rw(DS, 0x2384) == 1 and mem2.rb(DS, 0xBEFF) == 0
