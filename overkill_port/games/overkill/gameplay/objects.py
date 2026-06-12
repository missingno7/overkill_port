"""OVERKILL object scan / logic dispatch glue.

Small bounded helpers that are part of object-list traversal but are not the
large object behavior bodies themselves.
"""
from __future__ import annotations

SIG_OBJECT_LOGIC_CALL_AA2B_AA01 = bytes.fromhex("e8 27 00 59 e2 d9")
SIG_OBJECT_LOGIC_SCAN_TAIL_AA04 = bytes.fromhex("59 e2 d9")


def dispatch_object_logic_aa2b(cpu) -> None:
    """Lift OVERKILL 1010:AA2B first-level object-logic dispatcher."""
    s = cpu.s
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    s.bx = cpu.mem.rw(ss, (bp + 0x16) & 0xFFFF)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ip = cpu.mem.rw(s.cs & 0xFFFF, (0xAA36 + s.bx) & 0xFFFF)


def call_object_logic_from_scan_aa01(cpu, self_disable_if_patched) -> None:
    """Model ``AA01: CALL AA2B`` while preserving the real return frame."""
    if self_disable_if_patched(cpu, 0xAA01, SIG_OBJECT_LOGIC_CALL_AA2B_AA01, "overkill_object_logic_call_aa2b_aa01"):
        return
    cpu.push(0xAA04)
    dispatch_object_logic_aa2b(cpu)


def finish_object_logic_scan_tail_aa04(cpu, self_disable_if_patched) -> None:
    """Model ``AA04: POP CX ; LOOP A9E0``."""
    if self_disable_if_patched(cpu, 0xAA04, SIG_OBJECT_LOGIC_SCAN_TAIL_AA04, "overkill_object_logic_scan_tail_aa04"):
        return
    s = cpu.s
    s.cx = cpu.pop()
    s.cx = (s.cx - 1) & 0xFFFF
    s.ip = 0xA9E0 if s.cx != 0 else 0xAA07
