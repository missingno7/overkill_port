"""OVERKILL overlay/file-block XOR decoder.

This corresponds to 254A:05BF in the overlay segment.  It decodes a DOS-read
block in place and continues at 254A:05C6.  The address is intentionally kept in
this game-specific module because it is tied to OVERKILL's PSP/load layout.
"""
from __future__ import annotations

from overkill_port.cpu import CF

from .asm_adapters import linear_addr, loop_count


def decode_overlay_xor(cpu) -> None:
    """Mirror the 254A:05BF XOR/add loop and continue at 05C6."""
    count = loop_count(cpu.s.cx)
    al = cpu.get_reg8(0)
    ah = cpu.get_reg8(4)
    di = cpu.s.di & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    data = cpu.mem.data
    last_add_a = al
    last_add_result = al
    for _ in range(count):
        data[linear_addr(ds, di)] ^= al
        di = (di + 1) & 0xFFFF
        last_add_a = al
        last_add_result = al + ah
        al = last_add_result & 0xFF
    cpu.set_reg8(0, al)
    cpu.s.di = di
    cpu.s.cx = 0
    cpu.set_add_flags(last_add_a, ah, last_add_result, 8)
    cpu.s.ip = 0x05C6


def compare_overlay_signature_0582(cpu) -> None:
    """Mirror OVERKILL overlay 254A:0582 six-byte signature compare loop.

    The parent loader reads a twelve-byte header into CS:074A.  When the header
    looks like an MZ-style overlay record, this loop compares six bytes at
    DS:SI (normally 074E) against the signature table at DS:DI (normally 0756).

    Continuations:
        * 254A:058D when all compared bytes match.
        * 254A:0640 when the first mismatch is found.
    """
    ds = cpu.s.ds & 0xFFFF
    si = cpu.s.si & 0xFFFF
    di = cpu.s.di & 0xFFFF
    count = loop_count(cpu.s.cx)

    for index in range(count):
        al = cpu.mem.rb(ds, si)
        si = (si + 1) & 0xFFFF
        cpu.set_reg8(0, al)
        rhs = cpu.mem.rb(ds, di)
        cpu.set_sub_flags(al, rhs, al - rhs, 8)
        if al != rhs:
            cpu.s.si = si
            cpu.s.di = di
            cpu.s.cx = (count - index) & 0xFFFF
            cpu.s.ip = 0x0640
            return

        old_di = di
        old_cf = cpu.get_flag(CF)
        di = (di + 1) & 0xFFFF
        cpu.set_add_flags(old_di, 1, old_di + 1, 16)
        cpu.set_flag(CF, old_cf)

    cpu.s.si = si
    cpu.s.di = di
    cpu.s.cx = 0
    cpu.s.ip = 0x058D


def compare_overlay_entry_name_05d9(cpu) -> None:
    """Mirror OVERKILL overlay 254A:05D9 filename-entry comparison loop.

    The overlay loader reads and XOR-decodes a small directory entry at
    CS:075C, then compares the desired name at ES:DI with the decoded entry
    name at DS:SI.  The original loop intentionally ignores spaces on both
    sides and uppercases lowercase ASCII letters from the requested name before
    comparison.

    Continuations:
        * 254A:0607 when the names match and both reach NUL.
        * 254A:0637 when this directory entry does not match.

    This is an OVERKILL overlay-loader detail, not a generic DOS API helper.
    """
    ds = cpu.s.ds & 0xFFFF
    es = cpu.s.es & 0xFFFF
    si = cpu.s.si & 0xFFFF
    di = cpu.s.di & 0xFFFF
    data = cpu.mem.data

    def rb(seg: int, off: int) -> int:
        return data[linear_addr(seg, off)]

    while True:
        while rb(es, di) == 0x20:  # skip spaces in requested name
            di = (di + 1) & 0xFFFF
        while rb(ds, si) == 0x20:  # skip spaces in decoded entry name
            si = (si + 1) & 0xFFFF

        al = rb(es, di)
        di = (di + 1) & 0xFFFF
        ah = rb(ds, si)
        si = (si + 1) & 0xFFFF

        # The original uppercases only AL using ``AND AL,5Fh`` for 'a'..'z'.
        if 0x61 <= al <= 0x7A:
            al &= 0x5F

        cpu.set_reg8(0, al)
        cpu.set_reg8(4, ah)
        cpu.s.si = si
        cpu.s.di = di

        cmp_result = al - ah
        cpu.set_sub_flags(al, ah, cmp_result, 8)
        if (cmp_result & 0xFF) != 0:
            cpu.s.ip = 0x0637
            return

        # CMP matched.  The ASM then executes OR AL,AL; if non-zero it loops.
        cpu.set_logic_flags(al, 8)
        if al != 0:
            continue

        # End of both strings.  The live flags at 0607 are from OR AH,AH.
        cpu.set_logic_flags(ah, 8)
        if ah != 0:
            cpu.s.ip = 0x0637
        else:
            cpu.s.ip = 0x0607
        return

def strip_overlay_path_components_0701(cpu) -> None:
    """Mirror OVERKILL overlay 254A:0701 path-component normalizer.

    The overlay loader calls this helper as ``PUSH CS; CALL 0701`` and the
    helper exits with ``RETF``.  In practice it behaves like a near helper that
    can trim DS:SI and/or ES:DI to the component after the final backslash.

    Control bits:
        * CS:073A bit 1 gates the whole helper.
        * AH bit 0 enables DS:SI trimming.
        * AH bit 1 enables ES:DI trimming.

    The unusual far-return stack shape is part of OVERKILL's overlay loader and
    is intentionally reproduced here instead of generalized into the VM.
    """
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    gate = mem.rw(cs, 0x073A) & 0x0002
    cpu.set_logic_flags(gate, 16)
    if gate == 0:
        s.ip = cpu.pop()
        s.cs = cpu.pop()
        return

    ah = cpu.get_reg8(4)
    cpu.set_logic_flags(ah & 0x01, 8)
    if ah & 0x01:
        ds = s.ds & 0xFFFF
        si = s.si & 0xFFFF
        bp = si
        while True:
            al = mem.rb(ds, si)
            si = (si + 1) & 0xFFFF
            cpu.set_reg8(0, al)
            cpu.set_logic_flags(al, 8)
            if al == 0:
                break
            cpu.set_sub_flags(al, 0x5C, al - 0x5C, 8)
            if al == 0x5C:  # '\\' path separator; BP points after it because LODSB incremented SI.
                bp = si
        s.si = bp & 0xFFFF
        s.bp = bp & 0xFFFF

    # TEST AH,2 is the live flag producer when the DI branch is skipped.
    ah = cpu.get_reg8(4)
    cpu.set_logic_flags(ah & 0x02, 8)
    if not (ah & 0x02):
        s.ip = cpu.pop()
        s.cs = cpu.pop()
        return

    es = s.es & 0xFFFF
    di = s.di & 0xFFFF
    bp = di
    while True:
        al = mem.rb(es, di)
        di = (di + 1) & 0xFFFF
        cpu.set_reg8(0, al)
        cpu.set_logic_flags(al, 8)
        if al == 0:
            break
        cpu.set_sub_flags(al, 0x5C, al - 0x5C, 8)
        if al == 0x5C:
            bp = di
    s.di = bp & 0xFFFF
    s.bp = bp & 0xFFFF
    s.ip = cpu.pop()
    s.cs = cpu.pop()

def find_overlay_directory_entry_05a1(cpu) -> None:
    """Run the OVERKILL overlay directory-entry search loop at 254A:05A1.

    This is the loader loop that repeatedly reads a small encrypted directory
    entry from the currently open overlay file, XOR-decodes it, normalizes the
    requested path via 254A:0701 semantics, and compares the requested name with
    the entry name via 254A:05D9 semantics.

    The hook intentionally keeps DOS I/O at the VM boundary: each entry is read
    through INT 21h AH=3Fh so AX/flags and file-handle state remain observable.

    Continuations:
        * 254A:0607 when a matching entry is found.
        * 254A:0640 when the read fails or the directory scan is exhausted.
    """
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    while True:
        s.dx = 0x075C
        s.cx = mem.rw(cs, 0x0754)
        s.bx = mem.rw(cs, 0x0744)
        cpu.set_reg8(4, 0x3F)
        if cpu.interrupt_handler is None:
            raise RuntimeError("OVERKILL overlay entry scan needs DOS INT 21h handler")
        cpu.interrupt_handler(cpu, 0x21)
        if cpu.get_flag(CF):
            s.ip = 0x0640
            return

        s.di = 0x075C
        s.cx = mem.rw(cs, 0x0754)
        s.ax = mem.rw(cs, 0x074C)
        decode_overlay_xor(cpu)
        mem.ww(cs, 0x074C, s.ax & 0xFFFF)

        s.si = 0x075C
        s.si = (s.si + 0x000D) & 0xFFFF
        s.di = mem.rw(cs, 0x0746)
        s.es = mem.rw(cs, 0x0748)
        cpu.set_reg8(4, 0x03)
        # Original shape: PUSH CS; CALL 0701; ... and 0701 exits with RETF.
        cpu.push(cs)
        cpu.push(0x05D9)
        strip_overlay_path_components_0701(cpu)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x05D9):
            raise RuntimeError(f"overlay 0701 returned to unexpected {s.cs:04X}:{s.ip:04X}")

        compare_overlay_entry_name_05d9(cpu)
        if (s.ip & 0xFFFF) == 0x0607:
            return
        if (s.ip & 0xFFFF) != 0x0637:
            raise RuntimeError(f"overlay 05D9 comparison returned to unexpected IP {s.ip:04X}")

        counter = mem.rw(cs, 0x074A)
        new_counter = (counter - 1) & 0xFFFF
        old_cf = cpu.get_flag(CF)
        mem.ww(cs, 0x074A, new_counter)
        cpu.set_sub_flags(counter, 1, counter - 1, 16)
        cpu.set_flag(CF, old_cf)
        if new_counter == 0:
            s.ip = 0x0640
            return
        # JMP 05A1; continue the Python loop.

SIG_OVERLAY_COUNTER_STRIDE_LOOP_1F8F_0960 = bytes.fromhex(
    "ff 04 81 3c c0 00 75 04 c7 04 00 00 83 c6 06 e2 ef c3"
)


def run_overlay_counter_stride_loop_1f8f_0960(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL overlay routine 1F8F:0960.

    This tiny near helper is hot during Tandy gameplay.  It walks ``CX`` words
    spaced six bytes apart, increments each counter, wraps counters that reach
    ``00C0h`` back to zero, then returns.  The final FLAGS are those of the
    last ``ADD SI,0006h``; the following ``LOOP``/``RET`` do not affect them.
    """
    if self_disable_if_patched(
        cpu,
        0x0960,
        SIG_OVERLAY_COUNTER_STRIDE_LOOP_1F8F_0960,
        "overkill_overlay_counter_stride_loop_1f8f_0960",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    count = loop_count(s.cx)
    si = s.si & 0xFFFF

    last_si = si
    for _ in range(count):
        value = (mem.rw(ds, si) + 1) & 0xFFFF
        mem.ww(ds, si, 0 if value == 0x00C0 else value)
        last_si = si
        si = (si + 0x0006) & 0xFFFF

    s.si = si
    s.cx = 0
    cpu.set_add_flags(last_si, 0x0006, last_si + 0x0006, 16)
    s.ip = cpu.pop()
