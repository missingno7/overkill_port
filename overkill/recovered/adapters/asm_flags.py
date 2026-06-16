"""ASM-compatible flag/register adapters for recovered hook wrappers."""
from __future__ import annotations

from dos_re.cpu import CF


def cmp_word(cpu, a: int, b: int) -> None:
    """Apply 8086 ``CMP word a,b`` flags without changing either operand."""
    a &= 0xFFFF
    b &= 0xFFFF
    cpu.set_sub_flags(a, b, a - b, 16)


def add_word_to_si(cpu, value: int) -> int:
    """Model ``ADD SI,imm`` and return the wrapped result."""
    old = cpu.s.si & 0xFFFF
    value &= 0xFFFF
    result_full = old + value
    cpu.s.si = result_full & 0xFFFF
    cpu.set_add_flags(old, value, result_full, 16)
    return cpu.s.si


def sub_word_from_si(cpu, value: int) -> int:
    """Model ``SUB SI,imm`` and return the wrapped result."""
    old = cpu.s.si & 0xFFFF
    value &= 0xFFFF
    result_full = old - value
    cpu.s.si = result_full & 0xFFFF
    cpu.set_sub_flags(old, value, result_full, 16)
    return cpu.s.si


def set_carry_and_return(cpu, carry: bool) -> None:
    """Model the common ``STC/CLC ; RET`` tails used by collision helpers."""
    cpu.set_flag(CF, carry)
    cpu.s.ip = cpu.pop()
