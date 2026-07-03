"""OVERKILL text and HUD glyph rendering island.

This module owns the lifted source-code counterparts of OVERKILL's text drawing
path:

* 1010:519A  generic text-character dispatcher
* 1010:5F06  score/BCD nibble-to-text helper
* 1010:3153  Tandy/PCjr glyph renderer

The code is game-specific rather than VM-generic: it knows OVERKILL's text state
variables (DS:215C, DS:215E, DS:2160), the original font/mask tables, and the
Tandy video-work-buffer layout.  Hook registration stays in
``overkill.hooks``; the wrappers delegate here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from dos_re.cpu import CF
from overkill.asm import _add_mem_word, _add_reg16, _cmp_byte, _cmp_word

Cpu = object
SelfDisableIfPatched = Callable[[Cpu, int, bytes, str], bool]

SIG_TANDY_TEXT_GLYPH_3153 = bytes.fromhex(
    "3c 10 75 03 e9 e3 01 3c 11 75 03 e9 c1 01 32 e4"
)
SIG_TEXT_DISPATCH_519A = bytes.fromhex(
    "2e 8e 06 96 95 83 3e a2 21 00 74 12 2e 8b 1e bc 95 d1 e3 2e ff a7 b2 51"
)
SIG_TEXT_STRING_LOOP_518C = bytes.fromhex("8a 46 00 0a c0 75 01 c3 e8 03 00 45 eb f2")
SIG_SCORE_NIBBLE_TEXT_5F06 = bytes.fromhex("24 0f 04 30 e9 8d f2")
SIG_SCORE_BYTE_TEXT_5EF9 = bytes.fromhex("50 d0 e8 d0 e8 d0 e8 d0 e8 e8 01 00 58")
SIG_SCORE_STATUS_TEXT_BLOCK_5EDB = bytes.fromhex(
    "bd 18 23 e8 ab f2 bd 14 23 8a 46 03 e8 0f 00 8a "
    "46 02 e8 09 00 8a 46 01 e8 03 00 8a 46 00"
)


@dataclass(frozen=True)
class TextRenderRuntime:
    """Boundary services supplied by the hook wrappers.

    The runtime-patched-code guard is still centralized in overkill/hooks.py, but
    the live-byte signatures and lifted behavior live with the text island.
    """

    self_disable_if_patched: SelfDisableIfPatched







def run_text_string_loop_518c(cpu, runtime: TextRenderRuntime) -> None:
    """Lift OVERKILL 1010:518C NUL-terminated text loop.

    Original body::

        518C  mov al,[bp+0]
        518F  or  al,al
        5191  jnz 5194
        5193  ret
        5194  call 519A
        5197  inc bp
        5198  jmp 518C

    The helper prints the inline string at SS:BP through the already lifted
    519A character dispatcher.  Control bytes 10h/11h deliberately let 519A
    adjust BP first; the parent INC BP below then matches the original skip over
    the control payload.
    """
    if runtime.self_disable_if_patched(cpu, 0x518C, SIG_TEXT_STRING_LOOP_518C, "overkill_text_string_loop_518c"):
        return

    s = cpu.s
    ss = s.ss & 0xFFFF
    mem = cpu.mem
    while True:
        al = mem.rb(ss, s.bp & 0xFFFF)
        s.ax = (s.ax & 0xFF00) | al
        cpu.set_logic_flags(al, 8)  # OR AL,AL
        if al == 0:
            s.ip = cpu.pop()
            return

        cpu.push(0x5197)
        run_text_dispatch_519a(cpu, runtime)
        # 519A always returns to the pushed 5197: the Tandy-3153 glyph path, the 10h/11h control
        # paths, and (cold-boot) the unlifted non-Tandy text backend, which 519A now runs to its RET.
        if (s.ip & 0xFFFF) != 0x5197:
            raise RuntimeError(f"519A returned to unexpected IP {s.ip & 0xFFFF:04X} inside 518C text loop")
        old_bp = s.bp & 0xFFFF
        old_cf = cpu.get_flag(CF)
        result = (old_bp + 1) & 0xFFFF
        s.bp = result
        cpu.set_add_flags(old_bp, 1, old_bp + 1, 16)
        cpu.set_flag(CF, old_cf)


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
        # Unlifted non-Tandy text backend (e.g. the cold-boot intro/title text mode). The original
        # 519A JMPs to it and the backend RETs to the caller's return already on SS:SP -- but the
        # lifted callers (518C/5F06/5EF9) invoke 519A as a Python call and can't host that JMP, so
        # run the backend's original bytes here until it RETs to that return, then return to the
        # lifted caller.  Never reached in Tandy gameplay (that takes the 3153 branch above), so this
        # changes no gameplay behaviour; equivalent to the original JMP for any VM-driven caller.
        return_addr = mem.rw(ss, s.sp & 0xFFFF)
        entry_sp = s.sp & 0xFFFF
        s.ip = target & 0xFFFF
        for _ in range(20000):
            cpu.step()
            if ((s.cs & 0xFFFF) == cs and (s.ip & 0xFFFF) == (return_addr & 0xFFFF)
                    and (s.sp & 0xFFFF) == ((entry_sp + 2) & 0xFFFF)):
                return
        raise RuntimeError(
            f"519A unlifted text backend {target:04X} did not return to {return_addr:04X} "
            f"(ip={s.ip & 0xFFFF:04X})")

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



def run_score_status_text_block_5edb(cpu, runtime: TextRenderRuntime) -> None:
    """Lift the HUD/status text glue at 1010:5EDB.

    The original body prints a string at ``SS:2318`` through ``518C``, then prints
    four bytes from ``SS:2314..2317`` through the already verified ``5EF9``
    byte-as-two-nibbles helper.  The final byte falls through into 5EF9, so the
    caller's original return address remains on the stack for that last helper.
    Intermediate CALL scratch return words are preserved for full-memory oracle
    comparisons.
    """
    if runtime.self_disable_if_patched(cpu, 0x5EDB, SIG_SCORE_STATUS_TEXT_BLOCK_5EDB, "overkill_score_status_text_block_5edb"):
        return

    ss = cpu.s.ss & 0xFFFF

    cpu.s.bp = 0x2318
    cpu.push(0x5EE1)
    run_text_string_loop_518c(cpu, runtime)
    if (cpu.s.ip & 0xFFFF) != 0x5EE1:
        raise RuntimeError(f"518C returned to unexpected IP {cpu.s.ip:04X} inside 5EDB status text block")

    cpu.s.bp = 0x2314
    for index, return_ip in ((3, 0x5EEA), (2, 0x5EF0), (1, 0x5EF6)):
        cpu.set_reg8(0, cpu.mem.rb(ss, (cpu.s.bp + index) & 0xFFFF))
        cpu.push(return_ip)
        run_score_byte_text_5ef9(cpu, runtime)
        if (cpu.s.ip & 0xFFFF) != return_ip:
            raise RuntimeError(
                f"5EF9 returned to unexpected IP {cpu.s.ip:04X} inside 5EDB status text block"
            )

    cpu.set_reg8(0, cpu.mem.rb(ss, cpu.s.bp & 0xFFFF))
    run_score_byte_text_5ef9(cpu, runtime)


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


def run_score_byte_text_5ef9(cpu, runtime: TextRenderRuntime) -> None:
    """Lift ``1010:5EF9`` as high-nibble then low-nibble text output.

    The original body is small glue around the already verified ``5F06`` helper:
    it saves AX, shifts AL right four times, calls ``5F06`` for the high nibble,
    restores AX, then falls through into ``5F06`` for the low nibble.  Keeping the
    real push/call scratch words preserves full-memory verifier comparisons.
    """
    if runtime.self_disable_if_patched(cpu, 0x5EF9, SIG_SCORE_BYTE_TEXT_5EF9, "overkill_score_byte_text_5ef9"):
        return

    original_ax = cpu.s.ax & 0xFFFF
    cpu.push(original_ax)
    cpu.set_reg8(0, (original_ax >> 4) & 0x0F)
    cpu.push(0x5F05)
    run_score_nibble_text_5f06(cpu, runtime)
    if (cpu.s.ip & 0xFFFF) != 0x5F05:
        raise RuntimeError(f"5F06 returned to unexpected IP {cpu.s.ip:04X} inside 5EF9 score-byte helper")

    cpu.s.ax = cpu.pop()
    run_score_nibble_text_5f06(cpu, runtime)


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
