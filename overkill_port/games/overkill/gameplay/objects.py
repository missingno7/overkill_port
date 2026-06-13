"""OVERKILL object scan / logic dispatch glue.

Small bounded helpers that are part of object-list traversal but are not the
large object behavior bodies themselves.
"""
from __future__ import annotations

from overkill_port.cpu import DF

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


SIG_OBJECT_MOTION_TABLE_AB34 = bytes.fromhex(
    "bb 7c 23 8b 77 08 d1 e6 d1 e6 03 f2 ad 03 47 02 "
    "89 46 02 ad 03 47 04 89 46 04 c3"
)

SIG_OBJECT_SCROLL_SPRITE_AB4F = bytes.fromhex("a1 3c 23 05 18 00 89 46 08 c3")


def _lodsw(cpu) -> int:
    s = cpu.s
    value = cpu.mem.rw(s.ds & 0xFFFF, s.si & 0xFFFF)
    s.ax = value
    s.si = (s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    return value


def run_object_motion_table_ab34(cpu, self_disable_if_patched) -> None:
    """Runtime-patched AB34 helper: derive object X/Y from a motion table.

    The caller supplies ``DX`` as the table base and BP as the destination object
    record.  AB34 uses the player/base object at DS:237C, indexes by its sprite
    id at +08, then stores relative X/Y into SS:[BP+2]/[BP+4].
    """
    if self_disable_if_patched(cpu, 0xAB34, SIG_OBJECT_MOTION_TABLE_AB34, "overkill_object_motion_table_ab34"):
        return
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    s.bx = 0x237C
    s.si = mem.rw(ds, (s.bx + 0x08) & 0xFFFF)
    s.si = cpu.shift(4, s.si, 1, 16)
    s.si = cpu.shift(4, s.si, 1, 16)
    old_si = s.si
    s.si = (old_si + (s.dx & 0xFFFF)) & 0xFFFF
    cpu.set_add_flags(old_si, s.dx & 0xFFFF, old_si + (s.dx & 0xFFFF), 16)
    _lodsw(cpu)
    addend = mem.rw(ds, (s.bx + 0x02) & 0xFFFF)
    old_ax = s.ax
    s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ss, (bp + 0x02) & 0xFFFF, s.ax)
    _lodsw(cpu)
    addend = mem.rw(ds, (s.bx + 0x04) & 0xFFFF)
    old_ax = s.ax
    s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, s.ax)
    s.ip = cpu.pop()


def run_object_scroll_sprite_ab4f(cpu, self_disable_if_patched) -> None:
    """Runtime-patched AB4F helper: choose sprite from horizontal scroll base."""
    if self_disable_if_patched(cpu, 0xAB4F, SIG_OBJECT_SCROLL_SPRITE_AB4F, "overkill_object_scroll_sprite_ab4f"):
        return
    s = cpu.s
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    s.ax = cpu.mem.rw(ds, 0x233C)
    old_ax = s.ax
    s.ax = (old_ax + 0x0018) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0018, old_ax + 0x0018, 16)
    cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, s.ax)
    s.ip = cpu.pop()
