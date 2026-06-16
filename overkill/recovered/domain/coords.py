"""Pure coordinate and word helpers for recovered OVERKILL systems."""
from __future__ import annotations


def u16(value: int) -> int:
    """Return ``value`` wrapped to an unsigned 16-bit word."""
    return value & 0xFFFF


def i16(value: int) -> int:
    """Interpret ``value`` as a signed 16-bit word."""
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def signed_gt_word(a: int, b: int) -> bool:
    """Signed 16-bit comparison matching 8086 JG after ``CMP a,b``."""
    return i16(a) > i16(b)


def signed_lt_word(a: int, b: int) -> bool:
    """Signed 16-bit comparison matching 8086 JL after ``CMP a,b``."""
    return i16(a) < i16(b)
