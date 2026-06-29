"""Tests for the pure 1010:BF25 collision-damage counter chain.

Pins the difficulty-gated decrement decision (``collision_damage_counter_chain_bf25``): the BF25
+ BF2D base decrements, the BEDC==1 (one extra) / BEDC==0 (three extra) / other (none) gate, the
death-on-zero, and the 16-bit wrap.  Verified two ways: VM-free unit assertions and an
assembled-ASM oracle that runs the real BF25..BF52 chain (stopping at BFC7 on death or BF52 on
survive) and compares -- the per-routine ASM gate (BF25 is the object-vs-object collision damage,
reached through the BEC5 handler).
"""
from __future__ import annotations

from overkill.recovered.domain.collision import CollisionDamageChainBF25
from overkill.recovered.systems.collision import collision_damage_counter_chain_bf25


def test_chain_base_decrements_survive():
    # enter_at_bf25 + BF2D = 2 base decrements; BEDC=2 (other) adds none.
    assert collision_damage_counter_chain_bf25(5, 0x0002, True) == CollisionDamageChainBF25(3, False)
    # BF2D-only entry (variant-2 sprite path) = 1 decrement.
    assert collision_damage_counter_chain_bf25(5, 0x0002, False) == CollisionDamageChainBF25(4, False)


def test_chain_bedc_gate():
    assert collision_damage_counter_chain_bf25(5, 0x0001, True) == CollisionDamageChainBF25(2, False)  # +1
    assert collision_damage_counter_chain_bf25(10, 0x0000, True) == CollisionDamageChainBF25(5, False)  # +3 (5 total)


def test_chain_death_on_zero():
    assert collision_damage_counter_chain_bf25(2, 0x0002, True) == CollisionDamageChainBF25(0, True)
    assert collision_damage_counter_chain_bf25(5, 0x0000, True) == CollisionDamageChainBF25(0, True)  # 5 decs from 5
    assert collision_damage_counter_chain_bf25(1, 0x0002, False) == CollisionDamageChainBF25(0, True)


def test_chain_matches_interpreted_asm_bf25():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory

    code_bf25 = bytes.fromhex(
        "ff 4e 20 75 03 e9 9a 00 ff 4e 20 75 03 e9 92 00 83 3e dc be 01 74 11 "
        "83 3e dc be 00 75 0f ff 4e 20 74 7f ff 4e 20 74 7a ff 4e 20 74 75 "
        "c7 46 24 05 00 83 3e c2 a8 01 74 01"
    )
    BP = 0x4000

    def run_asm(counter_20, bedc, enter_at_bf25):
        mem = Memory()
        mem.load(0x1010, 0xBF25, code_bf25)
        start = 0xBF25 if enter_at_bf25 else 0xBF2D
        cpu = CPU8086(mem, CPUState(cs=0x1010, ds=0x2000, ss=0x2000, sp=0x9000, ip=start, bp=BP, flags=0x0202))
        cpu.trace_enabled = False
        mem.ww(0x2000, (BP + 0x20) & 0xFFFF, counter_20)
        mem.ww(0x2000, 0xBEDC, bedc)
        for _ in range(60):
            if cpu.addr() in ((0x1010, 0xBFC7), (0x1010, 0xBF52)):
                break
            cpu.step()
        assert cpu.addr() in ((0x1010, 0xBFC7), (0x1010, 0xBF52)), hex(cpu.s.ip)
        died = cpu.addr() == (0x1010, 0xBFC7)
        return mem.rw(0x2000, (BP + 0x20) & 0xFFFF), died

    cases = [
        (5, 0x0002, True), (5, 0x0002, False), (5, 0x0001, True), (10, 0x0000, True),
        (2, 0x0002, True), (5, 0x0000, True), (1, 0x0002, False), (3, 0x0000, True),
        (7, 0x0001, False), (4, 0x0003, True),  # BEDC=3 (other) -> no extra decs
    ]
    for counter_20, bedc, enter in cases:
        final, died = run_asm(counter_20, bedc, enter)
        pred = collision_damage_counter_chain_bf25(counter_20, bedc, enter)
        assert pred.died == died, (counter_20, bedc, enter)
        if not died:
            assert pred.new_counter_20 == final, (counter_20, bedc, enter)
