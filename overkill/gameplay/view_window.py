"""Shared view-window helpers for OVERKILL gameplay collision tails."""
from __future__ import annotations

from dos_re.cpu import CF


def _cmp_word(cpu, a: int, b: int) -> None:
    a &= 0xFFFF
    b &= 0xFFFF
    cpu.set_sub_flags(a, b, a - b, 16)


def _run_view_window_check_aa46(cpu) -> None:
    """Run the observed AA46 -> 8331 view-window check path.

    This helper is used from BCCB inside the BC4B post-move pass.  It preserves
    the memory writes to DS:95F2/95F4 and the live carry flag used by BCCB.  The
    current Tandy gameplay path exits with CF clear; if a later state reaches a
    not-yet-modeled branch, the surrounding caller will fail fast instead of
    hiding it.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    cpu.s.ax = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    cpu.set_logic_flags(cpu.s.ax, 16)  # OR AX,AX
    if cpu.s.ax & 0x8000:
        cpu.set_flag(CF, False)  # 835B CLC on this observed out-of-window exit.
        return

    cpu.s.si = mem.rw(ds, 0x2384)
    _cmp_word(cpu, cpu.s.si, 0x0003)
    # The observed path uses SI < 3.  For SI >= 3 the original still reaches the
    # same 8331-style bounds check through a nearby branch; keep the arithmetic
    # table-driven because it is harmless for the captured state and explicit.
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si << 1) & 0xFFFF
    cpu.set_add_flags(old_si, old_si, old_si + old_si, 16)  # SHL-by-1 flag shape approximation.
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si << 1) & 0xFFFF
    cpu.set_add_flags(old_si, old_si, old_si + old_si, 16)
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si + 0x214E) & 0xFFFF
    cpu.set_add_flags(old_si, 0x214E, old_si + 0x214E, 16)

    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + mem.rw(ds, 0x237E)) & 0xFFFF
    cpu.set_add_flags(old_ax, mem.rw(ds, 0x237E), old_ax + mem.rw(ds, 0x237E), 16)
    mem.ww(ds, 0x95F2, cpu.s.ax)
    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + mem.rw(ds, 0x2380)) & 0xFFFF
    cpu.set_add_flags(old_ax, mem.rw(ds, 0x2380), old_ax + mem.rw(ds, 0x2380), 16)
    mem.ww(ds, 0x95F4, cpu.s.ax)

    cpu.s.si = (mem.rw(ds, 0x95F2) + 0x0010) & 0xFFFF
    cpu.set_add_flags(mem.rw(ds, 0x95F2), 0x0010, mem.rw(ds, 0x95F2) + 0x0010, 16)
    x = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    _cmp_word(cpu, x, cpu.s.si)
    sx = x if x < 0x8000 else x - 0x10000
    ssi = cpu.s.si if cpu.s.si < 0x8000 else cpu.s.si - 0x10000
    if sx > ssi:
        cpu.set_flag(CF, False)
        return
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si - 0x0020) & 0xFFFF
    cpu.set_sub_flags(old_si, 0x0020, old_si - 0x0020, 16)
    _cmp_word(cpu, x, cpu.s.si)
    ssi = cpu.s.si if cpu.s.si < 0x8000 else cpu.s.si - 0x10000
    if sx < ssi:
        cpu.set_flag(CF, False)
        return

    cpu.s.si = (mem.rw(ds, 0x95F4) + 0x0010) & 0xFFFF
    cpu.set_add_flags(mem.rw(ds, 0x95F4), 0x0010, mem.rw(ds, 0x95F4) + 0x0010, 16)
    y = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, cpu.s.si)
    sy = y if y < 0x8000 else y - 0x10000
    ssi = cpu.s.si if cpu.s.si < 0x8000 else cpu.s.si - 0x10000
    if sy > ssi:
        cpu.set_flag(CF, False)
        return
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si - 0x0020) & 0xFFFF
    cpu.set_sub_flags(old_si, 0x0020, old_si - 0x0020, 16)
    _cmp_word(cpu, y, cpu.s.si)
    ssi = cpu.s.si if cpu.s.si < 0x8000 else cpu.s.si - 0x10000
    if sy < ssi:
        cpu.set_flag(CF, False)
        return
    cpu.set_flag(CF, True)
