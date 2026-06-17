"""Shared 8086 byte/port/ALU helpers for the OVERKILL sound + music island.

These tiny primitives model individual original instructions (flag-accurate
byte compares, port in/out, carry-preserving inc/dec, etc.).  They were
previously duplicated across ``pc_speaker``, ``timing`` and ``adlib_driver``;
keeping a single copy here removes that ballast and guarantees the timer,
sound-effect and music paths share identical flag semantics.
"""
from __future__ import annotations

from dos_re.cpu import CF


def cmp_byte(cpu, a: int, b: int) -> None:
    a &= 0xFF
    b &= 0xFF
    cpu.set_sub_flags(a, b, a - b, 8)


def in_al(cpu, port: int) -> int:
    value = cpu.port_reader(cpu, port & 0xFFFF, 8) if cpu.port_reader else 0
    cpu.set_reg8(0, value & 0xFF)
    return value & 0xFF


def out_imm_al(cpu, port: int) -> None:
    """OUT port, AL -- emit the current AL register."""
    if cpu.port_writer:
        cpu.port_writer(cpu, port & 0xFFFF, cpu.get_reg8(0), 8)


def out_value(cpu, port: int, value: int) -> None:
    """OUT port, value -- emit an explicit byte (used by the YM3812 writer)."""
    if cpu.port_writer:
        cpu.port_writer(cpu, port & 0xFFFF, value & 0xFF, 8)


def write_ym3812(cpu, dx: int, ax: int) -> None:
    """Mirror the YM3812 register/value pair write (AL=register, AH=value)."""
    out_value(cpu, dx, ax & 0xFF)
    out_value(cpu, (dx + 1) & 0xFFFF, (ax >> 8) & 0xFF)


def inc_reg8_preserve_cf(cpu, idx: int) -> int:
    old = cpu.get_reg8(idx)
    old_cf = cpu.get_flag(CF)
    result = (old + 1) & 0xFF
    cpu.set_reg8(idx, result)
    cpu.set_add_flags(old, 1, old + 1, 8)
    cpu.set_flag(CF, old_cf)
    return result


def inc_mem_byte_preserve_cf(cpu, seg: int, off: int) -> int:
    old = cpu.mem.rb(seg, off)
    old_cf = cpu.get_flag(CF)
    result = (old + 1) & 0xFF
    cpu.mem.wb(seg, off, result)
    cpu.set_add_flags(old, 1, old + 1, 8)
    cpu.set_flag(CF, old_cf)
    return result


def dec_mem_byte_preserve_cf(cpu, seg: int, off: int) -> int:
    old = cpu.mem.rb(seg, off)
    old_cf = cpu.get_flag(CF)
    result = (old - 1) & 0xFF
    cpu.mem.wb(seg, off, result)
    cpu.set_sub_flags(old, 1, old - 1, 8)
    cpu.set_flag(CF, old_cf)
    return result


def and_mem_byte(cpu, seg: int, off: int, value: int) -> int:
    old = cpu.mem.rb(seg, off)
    result = old & (value & 0xFF)
    cpu.mem.wb(seg, off, result)
    cpu.set_logic_flags(result, 8)
    return result


def add_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    addend = value & 0xFFFF
    result = old + addend
    cpu.set_reg16(reg_idx, result)
    cpu.set_add_flags(old, addend, result, 16)


def add_mem_word(cpu, seg: int, off: int, value: int) -> None:
    old = cpu.mem.rw(seg, off)
    addend = value & 0xFFFF
    result = old + addend
    cpu.mem.ww(seg, off, result)
    cpu.set_add_flags(old, addend, result, 16)
