"""OVERKILL overlay/container file-open helper.

This module lifts the parent file-I/O routine at ``254A:04D7``.  It is not a
codec: it opens the OVERKILL container file, reads small headers/directory
records, seeks to the selected entry, and returns an open DOS handle plus the
entry length.  The deterministic subloops it uses (signature compare, XOR
entry decode, path normalization, and entry-name compare) live in
``asset_codecs.overlay`` and are called here so the parent loader can be kept as
one coherent file-I/O island.
"""
from __future__ import annotations

from dos_re.cpu import CF

from overkill.asset_codecs.overlay import (
    compare_overlay_signature_0582,
    find_overlay_directory_entry_05a1,
    strip_overlay_path_components_0701,
)


def _int21(cpu) -> None:
    if cpu.interrupt_handler is None:
        raise RuntimeError("OVERKILL overlay file-I/O helper needs DOS INT 21h handler")
    cpu.interrupt_handler(cpu, 0x21)


def _overlay_loader_finish(cpu, *, carry: bool, ax: int | None = None) -> None:
    """Restore the 04D7 save frame and far-return to the original caller."""
    if ax is not None:
        cpu.s.ax = ax & 0xFFFF
    cpu.set_flag(CF, carry)
    cpu.s.es = cpu.pop()
    cpu.s.ds = cpu.pop()
    cpu.s.di = cpu.pop()
    cpu.s.si = cpu.pop()
    cpu.s.ip = cpu.pop()
    cpu.s.cs = cpu.pop()


def _close_current_handle(cpu, cs: int) -> None:
    bx = cpu.mem.rw(cs, 0x0744)
    cpu.s.bx = bx
    cpu.set_logic_flags(bx, 16)
    if bx == 0:
        return
    cpu.set_reg8(4, 0x3E)
    _int21(cpu)


def _open_container_at_0740(cpu, cs: int) -> bool:
    """Open the current container path from CS:[0740]."""
    s = cpu.s
    mem = cpu.mem
    mem.ww(cs, 0x0744, 0)
    s.dx = mem.rw(cs, 0x0740)
    s.ax = 0x3D02
    _int21(cpu)
    if cpu.get_flag(CF):
        return False
    mem.ww(cs, 0x0744, s.ax & 0xFFFF)
    return True


def _read_container_header(cpu, cs: int, *, offset: int | None = None) -> bool:
    """Read the 12-byte overlay/container header into CS:074A."""
    s = cpu.s
    mem = cpu.mem
    if offset is not None:
        s.cx = (offset >> 16) & 0xFFFF
        s.dx = offset & 0xFFFF
        s.ax = 0x4200
        s.bx = mem.rw(cs, 0x0744)
        _int21(cpu)
        if cpu.get_flag(CF):
            return False
    s.dx = 0x074A
    s.cx = 0x000C
    s.bx = mem.rw(cs, 0x0744)
    cpu.set_reg8(4, 0x3F)
    _int21(cpu)
    return not cpu.get_flag(CF)


def _compute_mz_overlay_directory_offset(cpu, cs: int) -> int:
    """Mirror 053C..0554: [074C] + (([074E] - 1) << 9), stored at 07AA:07AC."""
    mem = cpu.mem
    pages_minus_one = (mem.rw(cs, 0x074E) - 1) & 0xFFFF
    offset = (mem.rw(cs, 0x074C) + ((pages_minus_one << 9) & 0xFFFFFFFF)) & 0xFFFFFFFF
    mem.ww(cs, 0x07AA, offset & 0xFFFF)
    mem.ww(cs, 0x07AC, (offset >> 16) & 0xFFFF)
    return offset


def _advance_to_next_container_path(cpu, cs: int) -> bool:
    """Mirror 064E..0669 and return True when another path should be tried."""
    mem = cpu.mem
    si = mem.rw(cs, 0x0740)
    while True:
        al = mem.rb(cs, si)
        si = (si + 1) & 0xFFFF
        cpu.set_reg8(0, al)
        cpu.set_logic_flags(al, 8)
        if al == 0:
            break
    cpu.set_sub_flags(mem.rb(cs, si), 0xFF, mem.rb(cs, si) - 0xFF, 8)
    if mem.rb(cs, si) == 0xFF:
        si = 0x07AE
    mem.ww(cs, 0x0740, si)
    cpu.set_sub_flags(si, mem.rw(cs, 0x0742), si - mem.rw(cs, 0x0742), 16)
    return si != mem.rw(cs, 0x0742)


def _fail_or_try_next_container(cpu, cs: int) -> bool:
    """Mirror 0640..0669. Return True when the caller should retry 0504."""
    mem = cpu.mem
    bx = mem.rw(cs, 0x0744)
    cpu.s.bx = bx
    cpu.set_logic_flags(bx, 16)
    if bx != 0:
        cpu.set_reg8(4, 0x3E)
        _int21(cpu)
        if cpu.get_flag(CF):
            return False
    return _advance_to_next_container_path(cpu, cs)


def _success_from_directory_entry(cpu, cs: int) -> bool:
    """Mirror 0607..0631. Return True on successful seek to the entry payload."""
    s = cpu.s
    mem = cpu.mem
    si = 0x075C
    s.si = si
    dx0 = mem.rw(cs, si + 5)
    cx0 = mem.rw(cs, si + 7)
    add_low = mem.rw(cs, 0x07AA)
    low_sum = dx0 + add_low
    dx = low_sum & 0xFFFF
    carry = 1 if low_sum > 0xFFFF else 0
    add_high = (mem.rw(cs, 0x07AC) + carry) & 0xFFFF
    high_sum = cx0 + add_high
    cx = high_sum & 0xFFFF
    # The live flags at the DOS seek are produced by the original ADC CX,[07AC].
    cpu.set_add_flags(cx0, add_high, high_sum, 16)
    s.dx = dx
    s.cx = cx
    s.ax = 0x4200
    s.bx = mem.rw(cs, 0x0744)
    _int21(cpu)
    if cpu.get_flag(CF):
        return False

    s.si = 0x075C
    s.cx = mem.rw(cs, 0x075C + 9)
    s.dx = mem.rw(cs, 0x075C + 0x0B)
    s.ax = mem.rw(cs, 0x0744)
    s.bx = s.ax
    cpu.set_flag(CF, False)
    return True


def _open_direct_file_entry(cpu, cs: int) -> None:
    """Mirror the 0681 direct-file branch used when CS:[073A] bit 0 is set."""
    s = cpu.s
    mem = cpu.mem
    mem.ww(cs, 0x0744, 0)

    # LES DI, CS:[0746]
    s.di = mem.rw(cs, 0x0746)
    s.es = mem.rw(cs, 0x0748)
    cpu.set_reg8(4, 0x02)
    cpu.push(cs)
    cpu.push(0x0691)
    strip_overlay_path_components_0701(cpu)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x0691):
        raise RuntimeError(f"overlay 0701 returned to unexpected {s.cs:04X}:{s.ip:04X}")

    s.dx = s.di & 0xFFFF
    cpu.push(s.ds)
    cpu.push(s.es)
    s.ds = cpu.pop()
    s.ax = 0x3D02
    _int21(cpu)
    s.ds = cpu.pop()
    if cpu.get_flag(CF):
        _close_current_handle(cpu, cs)
        _overlay_loader_finish(cpu, carry=True, ax=0x0002)
        return

    mem.ww(cs, 0x0744, s.ax & 0xFFFF)
    s.cx = 0
    s.dx = 0
    s.bx = s.ax & 0xFFFF
    s.ax = 0x4202
    _int21(cpu)
    if cpu.get_flag(CF):
        _close_current_handle(cpu, cs)
        _overlay_loader_finish(cpu, carry=True, ax=0x0002)
        return

    file_len_low = s.ax & 0xFFFF
    file_len_high = s.dx & 0xFFFF

    s.cx = 0
    s.dx = 0
    s.bx = mem.rw(cs, 0x0744)
    s.ax = 0x4200
    _int21(cpu)
    if cpu.get_flag(CF):
        _close_current_handle(cpu, cs)
        _overlay_loader_finish(cpu, carry=True, ax=0x0002)
        return

    s.dx = file_len_high
    s.cx = file_len_low
    s.ax = mem.rw(cs, 0x0744)
    s.bx = s.ax
    _overlay_loader_finish(cpu, carry=False)


def open_overlay_container_entry_254a_04d7(cpu) -> None:
    """Lift OVERKILL's parent overlay/container file helper at 254A:04D7.

    Entry is a far call.  The helper preserves the original save frame
    (SI/DI/DS/ES), opens either a direct file or a named entry inside one of the
    container paths starting at ``CS:07AE``, and returns with:

    * CF=0, AX=BX=open handle, CX:DX=entry length on success.
    * CF=1, AX=0002h on failure.
    """
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    # 04D7..04E6 prologue.
    cpu.push(s.si)
    cpu.push(s.di)
    mem.ww(cs, 0x0746, s.dx)
    mem.ww(cs, 0x0748, s.ds)
    cpu.push(s.ds)
    cpu.push(s.es)
    s.ds = cs

    if mem.rw(cs, 0x073A) & 0x0001:
        cpu.set_logic_flags(mem.rw(cs, 0x073A) & 0x0001, 16)
        _open_direct_file_entry(cpu, cs)
        return
    cpu.set_logic_flags(mem.rw(cs, 0x073A) & 0x0001, 16)

    mem.ww(cs, 0x0744, 0)
    ax = mem.rw(cs, 0x0740)
    s.ax = ax
    mem.ww(cs, 0x0742, ax)

    while True:
        if not _open_container_at_0740(cpu, cs):
            if not _fail_or_try_next_container(cpu, cs):
                _close_current_handle(cpu, cs)
                _overlay_loader_finish(cpu, carry=True, ax=0x0002)
                return
            continue

        mem.ww(cs, 0x07AA, 0)
        mem.ww(cs, 0x07AC, 0)
        if not _read_container_header(cpu, cs):
            if not _fail_or_try_next_container(cpu, cs):
                _close_current_handle(cpu, cs)
                _overlay_loader_finish(cpu, carry=True, ax=0x0002)
                return
            continue

        if mem.rw(cs, 0x074A) == 0x5A4D:
            offset = _compute_mz_overlay_directory_offset(cpu, cs)
            if not _read_container_header(cpu, cs, offset=offset):
                if not _fail_or_try_next_container(cpu, cs):
                    _close_current_handle(cpu, cs)
                    _overlay_loader_finish(cpu, carry=True, ax=0x0002)
                    return
                continue

        s.si = 0x074E
        s.di = 0x0756
        s.cx = 0x0006
        compare_overlay_signature_0582(cpu)
        if (s.ip & 0xFFFF) != 0x058D:
            if not _fail_or_try_next_container(cpu, cs):
                _close_current_handle(cpu, cs)
                _overlay_loader_finish(cpu, carry=True, ax=0x0002)
                return
            continue

        s.cx = mem.rw(cs, 0x074A)
        cpu.set_logic_flags(s.cx, 16)
        if s.cx == 0:
            if not _fail_or_try_next_container(cpu, cs):
                _close_current_handle(cpu, cs)
                _overlay_loader_finish(cpu, carry=True, ax=0x0002)
                return
            continue
        cpu.set_sub_flags(s.cx, 0x0320, s.cx - 0x0320, 16)
        if s.cx >= 0x0320:
            if not _fail_or_try_next_container(cpu, cs):
                _close_current_handle(cpu, cs)
                _overlay_loader_finish(cpu, carry=True, ax=0x0002)
                return
            continue

        s.ip = 0x05A1
        find_overlay_directory_entry_05a1(cpu)
        if (s.ip & 0xFFFF) == 0x0607 and _success_from_directory_entry(cpu, cs):
            _overlay_loader_finish(cpu, carry=False)
            return

        if not _fail_or_try_next_container(cpu, cs):
            _close_current_handle(cpu, cs)
            _overlay_loader_finish(cpu, carry=True, ax=0x0002)
            return
