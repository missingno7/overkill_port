"""ASM-compatibility helpers for OVERKILL startup asset codecs.

These helpers are game-specific boundary glue for Python implementations that
replace OVERKILL loader routines.  They intentionally model small 8086 details
(flags, direction flag, DOS side effects) and should not be moved into the
generic VM just because they touch CPU state: the offsets and behavior here are
specific to OVERKILL's loader code.
"""
from __future__ import annotations

from dos_re.cpu import CF, DF
from overkill.asm import loop_count

OVERKILL_LOAD_ERROR_IP = 0x02B2
OVERKILL_LOAD_DISPATCH_CONTINUATION_IP = 0x02A8


def inc_mem_word_preserve_cf(cpu, seg: int, off: int) -> None:
    """Mirror INC word ptr [seg:off], including flags except preserved CF."""
    old = cpu.mem.rw(seg, off)
    old_cf = cpu.get_flag(CF)
    cpu.mem.ww(seg, off, (old + 1) & 0xFFFF)
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)


def dec_reg8_preserve_cf(cpu, reg_idx: int) -> None:
    """Mirror DEC r8, including flags except preserved CF."""
    old = cpu.get_reg8(reg_idx)
    old_cf = cpu.get_flag(CF)
    cpu.set_reg8(reg_idx, (old - 1) & 0xFF)
    cpu.set_sub_flags(old, 1, old - 1, 8)
    cpu.set_flag(CF, old_cf)


def near_call_into_hook(cpu, handler, return_ip: int) -> None:
    """Run a replacement body with the same stack side effect as CALL/RET."""
    cpu.push(return_ip & 0xFFFF)
    handler(cpu)


def stosb(cpu, value: int | None = None) -> None:
    """Store AL or value through ES:DI and advance DI according to DF."""
    if value is None:
        value = cpu.get_reg8(0)
    cpu.mem.wb(cpu.s.es, cpu.s.di, value)
    cpu.s.di = (cpu.s.di + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF


def linear_addr(seg: int, off: int) -> int:
    return (((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF
