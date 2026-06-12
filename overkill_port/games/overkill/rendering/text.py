"""OVERKILL text and HUD glyph rendering island.

This module owns the lifted source-code counterparts of OVERKILL's text drawing
path:

* 1010:519A  generic text-character dispatcher
* 1010:5F06  score/BCD nibble-to-text helper
* 1010:3153  Tandy/PCjr glyph renderer

The code is game-specific rather than VM-generic: it knows OVERKILL's text state
variables (DS:215C, DS:215E, DS:2160), the original font/mask tables, and the
Tandy video-work-buffer layout.  Hook registration stays in
``overkill_port.replacements``; the wrappers delegate here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from overkill_port.cpu import CF

Cpu = object
SelfDisableIfPatched = Callable[[Cpu, int, bytes, str], bool]

SIG_TANDY_TEXT_GLYPH_3153 = bytes.fromhex(
    "3c 10 75 03 e9 e3 01 3c 11 75 03 e9 c1 01 32 e4"
)
SIG_TEXT_DISPATCH_519A = bytes.fromhex(
    "2e 8e 06 96 95 83 3e a2 21 00 74 12 2e 8b 1e bc 95 d1 e3 2e ff a7 b2 51"
)
SIG_SCORE_NIBBLE_TEXT_5F06 = bytes.fromhex("24 0f 04 30 e9 8d f2")


@dataclass(frozen=True)
class TextRenderRuntime:
    """Boundary services supplied by the hook wrappers.

    The runtime-patched-code guard is still centralized in replacements.py, but
    the live-byte signatures and lifted behavior live with the text island.
    """

    self_disable_if_patched: SelfDisableIfPatched


def _cmp_byte(cpu, a: int, b: int) -> None:
    a &= 0xFF
    b &= 0xFF
    cpu.set_sub_flags(a, b, a - b, 8)


def _cmp_word(cpu, a: int, b: int) -> None:
    a &= 0xFFFF
    b &= 0xFFFF
    cpu.set_sub_flags(a, b, a - b, 16)


def _add_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    addend = value & 0xFFFF
    result = old + addend
    cpu.set_reg16(reg_idx, result)
    cpu.set_add_flags(old, addend, result, 16)


def _add_mem_word(cpu, seg: int, off: int, value: int) -> None:
    old = cpu.mem.rw(seg, off)
    addend = value & 0xFFFF
    result = old + addend
    cpu.mem.ww(seg, off, result)
    cpu.set_add_flags(old, addend, result, 16)


def run_text_dispatch_519a(cpu, runtime: TextRenderRuntime) -> None:
    """Lift the OVERKILL generic text-character dispatcher at 1010:519A.

    In Tandy mode this hot wrapper sets ES to the game data segment, checks the
    active text backend flag, dispatches through the video-mode text table, and
    jumps to the Tandy glyph renderer.  The direct text-buffer path used when
    DS:21A2 == 0 is also modeled because startup/status code can temporarily
    disable backend dispatch.
    """
    if runtime.self_disable_if_patched(cpu, 0x519A, SIG_TEXT_DISPATCH_519A, "overkill_text_dispatch_519a"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    s.es = mem.rw(cs, 0x9596)
    text_backend = mem.rw(ds, 0x21A2)
    _cmp_word(cpu, text_backend, 0)
    if text_backend != 0:
        mode = mem.rw(cs, 0x95BC)
        s.bx = mode
        s.bx = cpu.shift(4, s.bx, 1, 16)
        target = mem.rw(cs, (0x51B2 + s.bx) & 0xFFFF)
        if target == 0x3153:
            run_tandy_text_glyph_3153(cpu, runtime)
            return
        # Keep original JMP semantics for unlifted non-Tandy text backends.
        s.ip = target & 0xFFFF
        return

    al = s.ax & 0xFF
    _cmp_byte(cpu, al, 0x10)
    if al == 0x10:
        old_bp = bp
        bp = (bp + 1) & 0xFFFF
        s.bp = bp
        old_cf = cpu.get_flag(CF)
        cpu.set_add_flags(old_bp, 1, old_bp + 1, 16)
        cpu.set_flag(CF, old_cf)
        value = mem.rb(ss, bp)
        s.ax = (s.ax & 0xFF00) | value
        mem.wb(ds, 0x215C, value)
        s.ip = cpu.pop()
        return

    _cmp_byte(cpu, al, 0x11)
    if al == 0x11:
        value = mem.rb(ss, (bp + 1) & 0xFFFF)
        s.ax = (s.ax & 0xFF00) | value
        s.cx = 0x0050
        s.ax = value & 0xFF
        cpu.set_logic_flags(0, 8)  # XOR AH,AH
        product = (s.ax * s.cx) & 0xFFFFFFFF
        s.dx = (product >> 16) & 0xFFFF
        s.ax = product & 0xFFFF
        s.bx = s.ax
        value = mem.rb(ss, (bp + 2) & 0xFFFF)
        s.ax = (s.ax & 0xFF00) | value
        s.ax &= 0x00FF
        s.ax = cpu.shift(4, s.ax, 1, 16)
        old_bx = s.bx
        s.bx = (s.bx + s.ax) & 0xFFFF
        cpu.set_add_flags(old_bx, s.ax, old_bx + s.ax, 16)
        mem.ww(ds, 0x2160, s.bx)
        _add_reg16(cpu, 5, 2)
        s.ip = cpu.pop()
        return

    s.es = mem.rw(cs, 0x9594)
    s.di = mem.rw(ds, 0x2160)
    ah = mem.rb(ds, 0x215C)
    s.ax = ((ah << 8) | (s.ax & 0x00FF)) & 0xFFFF
    mem.ww(s.es, s.di, s.ax)
    _add_mem_word(cpu, ds, 0x2160, 2)
    s.ip = cpu.pop()


def run_score_nibble_text_5f06(cpu, runtime: TextRenderRuntime) -> None:
    """Lift the tiny BCD/score nibble printer at 1010:5F06.

    Original code masks AL to a nibble, converts it to ASCII '0'..'?' and jumps
    to the 519A text dispatcher.  Because it is a JMP, the dispatcher returns
    directly to the original caller's return address already on the stack.
    """
    if runtime.self_disable_if_patched(cpu, 0x5F06, SIG_SCORE_NIBBLE_TEXT_5F06, "overkill_score_nibble_text_5f06"):
        return

    al = cpu.get_reg8(0) & 0x0F
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)
    old = al
    result = old + 0x30
    cpu.set_reg8(0, result & 0xFF)
    cpu.set_add_flags(old, 0x30, result, 8)
    run_text_dispatch_519a(cpu, runtime)


def run_tandy_text_glyph_3153(cpu, runtime: TextRenderRuntime) -> None:
    """Lift OVERKILL Tandy text/glyph routine 1010:3153.

    It handles inline control bytes (10h = set colour, 11h = set cursor) and
    otherwise draws one 8-row glyph into the Tandy work/video buffer using the
    original font and nibble-mask tables.
    """
    if runtime.self_disable_if_patched(cpu, 0x3153, SIG_TANDY_TEXT_GLYPH_3153, "overkill_tandy_text_glyph_3153"):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    cs = s.cs & 0xFFFF
    bp = s.bp & 0xFFFF
    al = s.ax & 0x00FF

    if al == 0x10:
        old_bp = bp
        bp = (bp + 1) & 0xFFFF
        s.bp = bp
        # INC preserves CF; following MOVs do not change FLAGS.
        old_cf = cpu.get_flag(CF)
        cpu.set_add_flags(old_bp, 1, old_bp + 1, 16)
        cpu.set_flag(CF, old_cf)
        value = mem.rb(ss, bp)
        s.ax = (s.ax & 0xFF00) | value
        mem.wb(ds, 0x215C, value)
        s.ip = cpu.pop()
        return

    if al == 0x11:
        row = mem.rb(ss, (bp + 1) & 0xFFFF)
        product = row * 0x0140
        s.dx = (product >> 16) & 0xFFFF
        ax = product & 0xFFFF
        mem.ww(ds, 0x2160, ax)
        col = mem.rb(ss, (bp + 2) & 0xFFFF)
        # The Tandy control path shifts AL only, preserving AH from row*0140.
        ax = (ax & 0xFF00) | col
        ax = (ax & 0xFF00) | ((ax << 1) & 0x00FF)
        ax = (ax & 0xFF00) | ((ax << 1) & 0x00FF)
        mem.wb(ds, 0x215E, ax & 0x00FF)
        old_bp = bp
        bp = (bp + 2) & 0xFFFF
        s.ax = ax & 0xFFFF
        s.cx = 0x0140
        s.bp = bp
        cpu.set_add_flags(old_bp, 2, old_bp + 2, 16)
        s.ip = cpu.pop()
        return

    # Normal glyph path.  The original zeroes AH, multiplies the character by
    # eight via three SHL AX, and reads eight source bytes from DS:1816+char*8.
    ax = (al << 3) & 0xFFFF
    si = (ax + 0x1816) & 0xFFFF
    es = mem.rw(cs, 0x95A4)
    dx = mem.rb(ds, 0x215E)
    dx = (dx + mem.rw(ds, 0x2160)) & 0xFFFF
    di = dx
    colour = mem.rb(ds, 0x215C)
    dl = (((colour << 4) & 0xFF) | colour) & 0xFF
    dx = (dl << 8) | dl

    bx = s.bx & 0xFFFF
    cx = s.cx & 0xFFFF
    last_ax = ax
    for _ in range(8):
        glyph_byte = mem.rb(ds, si)
        si = (si + 1) & 0xFFFF
        ax = glyph_byte
        bx = ((ax << 2) + 0x1514) & 0xFFFF
        last_ax = mem.rw(ds, bx)
        cx = last_ax & dx
        mem.ww(es, di, cx)
        last_ax = mem.rw(ds, (bx + 2) & 0xFFFF)
        cx = last_ax & dx
        mem.ww(es, (di + 2) & 0xFFFF, cx)
        before_di = di
        di = (di + 0x2000) & 0xFFFF
        cpu.set_add_flags(before_di, 0x2000, before_di + 0x2000, 16)
        cpu.set_logic_flags(di & 0x8000, 16)
        if di & 0x8000:
            before_di = di
            di = (di + 0x80A0) & 0xFFFF
            cpu.set_add_flags(before_di, 0x80A0, before_di + 0x80A0, 16)

    old_cursor_x = mem.rb(ds, 0x215E)
    new_cursor_x = (old_cursor_x + 4) & 0xFF
    mem.wb(ds, 0x215E, new_cursor_x)
    cpu.set_add_flags(old_cursor_x, 4, old_cursor_x + 4, 8)
    cpu.set_sub_flags(new_cursor_x, 0xA0, new_cursor_x - 0xA0, 8)
    if new_cursor_x >= 0xA0:
        mem.wb(ds, 0x215E, 0)
        old_y = mem.rw(ds, 0x2160)
        mem.ww(ds, 0x2160, (old_y + 0x0140) & 0xFFFF)
        cpu.set_add_flags(old_y, 0x0140, old_y + 0x0140, 16)

    s.ax = last_ax & 0xFFFF
    s.bx = bx & 0xFFFF
    s.cx = cx & 0xFFFF
    s.dx = dx & 0xFFFF
    s.si = si & 0xFFFF
    s.di = di & 0xFFFF
    s.es = es & 0xFFFF
    s.ip = cpu.pop()
