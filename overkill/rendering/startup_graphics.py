"""OVERKILL startup graphics materialization helpers.

These routines are game-specific asset-loading/render-preparation codecs. They
turn planar/bitpacked startup graphics into the transient work buffers used by
OVERKILL's original renderer.  They are not generic VM services and intentionally
preserve ASM-visible register, flag, memory, stack, and continuation behavior at
the hook boundaries.
"""

from __future__ import annotations

from dos_re.cpu import CF, DF, OF
from overkill.asm import _stosw


def pack_four_pixels_45f6(cpu):
    """Replace the hot pixel/nibble packing helper at 1010:45F6.

    This routine takes bitplanes in AL/AH/DL/DH, rotates bits through CF into
    CL, optionally applies a transparent-nibble mask in CH, then remaps both
    nibbles through the CS:45E6 lookup table.  The caller stores CL/CH into
    temporary CS variables used by the renderer around 4537..45CA.
    """
    # Interleave 8 bits from DH,DL,AH,AL into CL using the same current CPU
    # rotate helper as interpreted D0 /1 and D0 /2 instructions.
    sequence = ["dh", "dl", "ah", "al", "dh", "dl", "ah", "al"]
    for reg in sequence:
        if reg == "dh":
            value = cpu.get_reg8(6)
            cpu.set_reg8(6, cpu.shift(1, value, 1, 8))  # ROR DH,1
        elif reg == "dl":
            value = cpu.get_reg8(2)
            cpu.set_reg8(2, cpu.shift(1, value, 1, 8))  # ROR DL,1
        elif reg == "ah":
            value = cpu.get_reg8(4)
            cpu.set_reg8(4, cpu.shift(1, value, 1, 8))  # ROR AH,1
        else:
            value = cpu.get_reg8(0)
            cpu.set_reg8(0, cpu.shift(1, value, 1, 8))  # ROR AL,1
        cl = cpu.get_reg8(1)
        cpu.set_reg8(1, cpu.shift(2, cl, 1, 8))        # RCL CL,1

    for _ in range(4):
        cl = cpu.get_reg8(1)
        cpu.set_reg8(1, cpu.shift(1, cl, 1, 8))        # ROR CL,1

    original_ax = cpu.s.ax & 0xFFFF
    cl = cpu.get_reg8(1)
    ch = cpu.get_reg8(5)

    transparent_enabled = cpu.mem.rw(cpu.s.cs, 0x0BD6) != 0
    transparent_color = cpu.mem.rb(cpu.s.cs, 0x0000)
    if transparent_enabled:
        ch = 0
        low = cl & 0x0F
        if low == transparent_color:
            ch |= 0x0F
            cl &= 0xF0
        high = (cl >> 4) & 0x0F
        if high == transparent_color:
            ch |= 0xF0
            cl &= 0x0F

    cpu.mem.ww(cpu.s.cs, 0x45E2, original_ax)

    table_base = 0x45E6
    low_mapped = cpu.mem.rb(cpu.s.cs, table_base + (cl & 0x0F))
    high_mapped = cpu.mem.rb(cpu.s.cs, table_base + ((cl >> 4) & 0x0F))
    mapped = ((high_mapped << 4) | low_mapped) & 0xFF
    cpu.set_logic_flags(mapped, 8)  # final OR AL,AH flags

    cpu.s.bx = table_base
    cpu.set_reg8(1, mapped)  # CL
    cpu.set_reg8(5, ch)      # CH
    cpu.s.ax = original_ax
    cpu.s.ip = cpu.pop()

def expand_bits_45cb(cpu):
    """Replace the tiny self-call bit expansion helper at 1010:45CB.

    The original routine is intentionally odd:

        45CB  call 45CE     ; pushes 45CE, jumps to 45CE
        45CE  rol al,1
              rol al,1
              rol al,1
              rcl word ptr cs:[45E4],1
              rol al,1
              rcl word ptr cs:[45E4],1
              ret           ; first ret goes back to 45CE
                            ; second ret returns to the original caller

    Therefore a single CALL 45CB executes the 45CE body twice.  The helper is
    hot while the startup renderer expands bit/nibble graphics into video-ish
    buffers, and replacing it removes thousands of interpreted instructions
    without changing the architectural result.
    """

    def body_once() -> None:
        al = cpu.get_reg8(0)
        for _ in range(3):
            al = cpu.shift(0, al, 1, 8)  # ROL AL,1
        cpu.set_reg8(0, al)

        word = cpu.mem.rw(cpu.s.cs, 0x45E4)
        word = cpu.shift(2, word, 1, 16)  # RCL word ptr CS:[45E4],1
        cpu.mem.ww(cpu.s.cs, 0x45E4, word)

        al = cpu.get_reg8(0)
        al = cpu.shift(0, al, 1, 8)  # ROL AL,1
        cpu.set_reg8(0, al)

        word = cpu.mem.rw(cpu.s.cs, 0x45E4)
        word = cpu.shift(2, word, 1, 16)  # RCL word ptr CS:[45E4],1
        cpu.mem.ww(cpu.s.cs, 0x45E4, word)

    body_once()
    body_once()
    cpu.s.ip = cpu.pop()

def expand_4plane_block_4511(cpu):
    """Replace the hot nested block renderer at 1010:4511.

    Original shape:

        CX = CS:5B9E
      row:
        push CX
        CX = CS:5B9C
      col:
        push CX
        call 4537
        pop CX
        loop col
        add SI,width three times
        pop CX
        loop row
        jmp 450C

    The inner 4537 leaf is already tested independently, so this hook mostly
    preserves the LOOP stack/register side effects while collapsing the Python
    interpreter overhead of the nested control-flow instructions.
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    height = cpu.mem.rw(cs, 0x5B9E)
    width = cpu.mem.rw(cs, 0x5B9C)

    outer = height
    while outer != 0:
        # Original: PUSH CX / MOV CX,width / per-column PUSH CX; CALL 4537;
        # POP CX; LOOP.  The loop counters are carried in Python locals and
        # CX is staged before each row call because the row body reads CH for
        # the non-transparent mask bytes.  Only sub-SP stack scratch is
        # dropped, as the verified 4537 fast hook already does.
        col = width
        while col != 0:
            s.cx = col
            _row_4537_core(cpu)
            col -= 1  # LOOP col, flags unaffected.

        # ADD SI,width three times; the third ADD's flags are the live ones.
        si = (s.si + width + width) & 0xFFFF
        cpu.set_add_flags(si, width, si + width, 16)
        s.si = (si + width) & 0xFFFF

        outer = (outer - 1) & 0xFFFF  # LOOP row, flags unaffected.

    s.cx = 0
    s.ip = 0x450C


# 45CB bit-spread group table.  One 45CB expansion inserts exactly four bits of
# its input byte into CS:[45E4] via the ROL/RCL16 chain, in this order:
# bit5, bit4, bit1, bit0 (ROL x3 carries out bit5, ROL carries bit4, then ROL x3
# from the rotated position carries bit1, ROL carries bit0).  The table maps a
# byte to that 4-bit group so a whole 45CB call becomes one lookup.
_G45CB = tuple(
    ((((b >> 5) & 1) << 3) | (((b >> 4) & 1) << 2) | (((b >> 1) & 1) << 1) | (b & 1))
    for b in range(256)
)

def _row_4537_core(cpu):
    """Fast lifted body of the 1010:4537 row expander (no return-IP pop).

    Computes the same final architectural state as the original 45F6/45CB
    rotate chain (the four 45F6 pack calls and the 45CB bit-spread calls) using
    direct bit arithmetic and the `_G45CB` table:

    - pack call k (k=0..3) gathers bits 2k/2k+1 of the four plane bytes
      (DH,DL,AH,AL) into CL with the nibbles swapped, applies the optional
      transparency test against CS:[0BD6]/CS:[0000], and remaps both nibbles
      through the CS:45E6 colour table;
    - each 45CB expansion contributes `_G45CB[byte]` as the next nibble of the
      output word, first byte highest (mask word from 5B98..5B9B when
      CS:[0BD6] != 0, then the visible word from 5B94..5B97);
    - final flags: ZF/SF/PF/AF are left by the `CMP CS:[0BD6],0` (result =
      CS:[0BD6]); the ROL/RCL16 rotate tail that follows touches only CF and OF.
      CF is the bit rotated out by the last RCL16 (bit15 of its operand, which
      the hook already tracks as `prev45e4_bit0`), and OF is that 1-bit
      left-rotate's overflow = msb(operand) XOR msb(result) = CF XOR bit15(w2)
      (the result word being the final CS:[45E4] == w2).

    Verified bit-identical to the interpreted original ASM by the oracle test
    plus a randomized differential fuzz (registers, flags incl. DF, and all
    written memory).
    """
    s = cpu.s
    mem = cpu.mem
    rb, rw, wb, ww = mem.rb, mem.rw, mem.wb, mem.ww
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    width = rw(cs, 0x5B9C)
    si = s.si & 0xFFFF
    al = rb(ds, si)
    ah = rb(ds, (si + width) & 0xFFFF)
    bx = (width << 1) & 0xFFFF
    dl = rb(ds, (si + bx) & 0xFFFF)
    bx = (bx + width) & 0xFFFF
    dh = rb(ds, (si + bx) & 0xFFFF)

    bd6 = rw(cs, 0x0BD6)
    tcol = rb(cs, 0x0000) if bd6 else 0
    entry_ch = (s.cx >> 8) & 0xFF

    cls = []
    chs = []
    for k in (0, 2, 4, 6):
        b = k + 1
        cl = ((((dh >> b) & 1) << 7) | (((dl >> b) & 1) << 6)
              | (((ah >> b) & 1) << 5) | (((al >> b) & 1) << 4)
              | (((dh >> k) & 1) << 3) | (((dl >> k) & 1) << 2)
              | (((ah >> k) & 1) << 1) | ((al >> k) & 1))
        if bd6:
            ch = 0
            if (cl & 0x0F) == tcol:
                ch = 0x0F
                cl &= 0xF0
            if ((cl >> 4) & 0x0F) == tcol:
                ch |= 0xF0
                cl &= 0x0F
        else:
            ch = entry_ch
        cls.append(((rb(cs, 0x45E6 + ((cl >> 4) & 0x0F)) << 4)
                    | rb(cs, 0x45E6 + (cl & 0x0F))) & 0xFF)
        chs.append(ch)

    c0, c1, c2, c3 = cls
    m0, m1, m2, m3 = chs
    wb(cs, 0x5B95, c0); wb(cs, 0x5B99, m0)
    wb(cs, 0x5B94, c1); wb(cs, 0x5B98, m1)
    wb(cs, 0x5B97, c2); wb(cs, 0x5B9B, m2)
    wb(cs, 0x5B96, c3); wb(cs, 0x5B9A, m3)
    # CS:[45E2] is written once per pack call; the surviving value is the one
    # from the fourth call, where AH:AL have been rotated by a full 8 bits and
    # therefore equal the loaded plane bytes again.
    ww(cs, 0x45E2, ((ah << 8) | al) & 0xFFFF)

    s.si = (si + 1) & 0xFFFF

    g = _G45CB
    step = -2 if s.flags & DF else 2
    di = s.di & 0xFFFF
    es = s.es & 0xFFFF

    if bd6:
        # Mask word from 5B98,5B99,5B9A,5B9B == m1,m0,m3,m2 (insertion order).
        w1 = (g[m1] << 12) | (g[m0] << 8) | (g[m3] << 4) | g[m2]
        ww(es, di, w1)
        di = (di + step) & 0xFFFF
        prev45e4_bit0 = w1 & 1
    else:
        prev45e4_bit0 = rw(cs, 0x45E4) & 1

    # Visible word from 5B94,5B95,5B96,5B97 == c1,c0,c3,c2.
    w2 = (g[c1] << 12) | (g[c0] << 8) | (g[c3] << 4) | g[c2]
    ww(cs, 0x45E4, w2)
    ww(es, di, w2)
    s.di = (di + step) & 0xFFFF

    s.ax = w2
    s.bx = 0x45E6
    s.cx = ((m3 << 8) | c3) & 0xFFFF
    # 45F6 rotates each plane byte by two bits per call. 4537 calls it four
    # times, so the bytes return to their loaded values, not the entry DX.
    s.dx = ((dh << 8) | dl) & 0xFFFF

    # CMP CS:[0BD6],0 sets ZF/SF/PF/AF from its result (= CS:[0BD6]) and clears
    # CF/OF.  The ROL AL / RCL16 CS:[45E4] rotate tail that follows overwrites
    # ONLY CF and OF (rotates never touch ZF/SF/PF/AF), so those four survive
    # exactly as the compare left them.
    cpu.set_sub_flags(bd6, 0, bd6, 16)
    cf = 1 if prev45e4_bit0 else 0               # CF = bit rotated out by the last RCL16
    f = s.flags & ~(CF | OF)
    if cf:
        f |= CF
    # OF of a 1-bit left rotate = msb(operand_before) XOR msb(result).  The
    # result word is the final CS:[45E4] (== w2) and msb(operand_before) == CF.
    if cf ^ ((w2 >> 15) & 1):
        f |= OF
    s.flags = (f | 0x0002) & 0x0FFF

def expand_4plane_row_4537(cpu):
    """Verified replacement for 1010:4537 4-plane row expansion.

    The body lives in `_row_4537_core`, which computes the same observable
    semantics as the original 45F6/45CB rotate chain using direct bit arithmetic
    (the rotate chain would perform ~500 per-bit rotate/flag operations per row).
    Verified bit-identical against the interpreted original ASM by
    ``test_expand_4plane_row_4537_hook_matches_interpreted_asm`` and the
    randomized differential fuzz in ``test_expand_4plane_row_4537_fuzz``.
    """
    _row_4537_core(cpu)
    cpu.s.ip = cpu.pop()

def expand_4plane_list_450c(cpu):
    """Replace the list-driver loop around 1010:450C.

    This is intentionally a narrow control-flow replacement, not a new renderer.
    It only folds the hot outer loop:

        450C call 44D7        ; read one block header / detect terminator
        450F jz   44AA        ; exit list when 44D7 left ZF set
        4511 ...              ; existing verified 4-plane block renderer
        4535 jmp  450C

    Each non-terminal block is still rendered by the already verified 4511 hook.
    This keeps behavior tied to the interpreted routine while removing tens of
    thousands of call/jmp/header instructions during startup asset expansion.
    """
    cs = cpu.s.cs & 0xFFFF
    ds = cpu.s.ds & 0xFFFF

    guard = 0
    while True:
        guard += 1
        if guard > 100_000:
            raise RuntimeError("OVERKILL 450C 4-plane list did not reach terminator")

        # The original enters 44D7 through CALL 44D7, then 44D7 returns to
        # 450F.  SP is restored, but the pushed return word remains below SP and
        # full-memory verification observes that dead-stack scratch byte-for-byte.
        cpu.mem.ww(cpu.s.ss & 0xFFFF, (cpu.s.sp - 2) & 0xFFFF, 0x450F)

        # 44D7: MOV AX,[SI]; OR AX,[SI+2]; JNZ 44DF; RET
        first = cpu.mem.rw(ds, cpu.s.si)
        second = cpu.mem.rw(ds, (cpu.s.si + 2) & 0xFFFF)
        combined = first | second
        cpu.s.ax = combined & 0xFFFF
        cpu.set_logic_flags(cpu.s.ax, 16)
        if combined == 0:
            # The original returns to 450F with ZF=1; JZ then jumps to 44AA.
            cpu.s.ip = 0x44AA
            return

        # 44DF..450A: consume header words and publish dimensions.
        cpu.s.bx = cpu.mem.rw(cs, 0x0BE0)
        old_index = cpu.mem.rw(cs, 0x0BE0)
        cpu.mem.ww(cs, 0x0BE0, (old_index + 2) & 0xFFFF)
        cpu.set_add_flags(old_index, 2, old_index + 2, 16)

        # LODSW -> first word.  Flags are overwritten below by CMP/INC.
        cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF

        bd8 = cpu.mem.rw(cs, 0x0BD8)
        cpu.set_sub_flags(bd8, 0, bd8, 16)
        if bd8 != 0:
            cpu.mem.ww(cs, cpu.s.bx, cpu.s.di)
            _stosw(cpu)
        cpu.mem.ww(cs, 0x5B9E, cpu.s.ax)

        # LODSW -> second word.
        cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF

        bd8 = cpu.mem.rw(cs, 0x0BD8)
        cpu.set_sub_flags(bd8, 0, bd8, 16)
        if bd8 != 0:
            _stosw(cpu)
        cpu.mem.ww(cs, 0x5B9C, cpu.s.ax)

        old_ax = cpu.s.ax & 0xFFFF
        old_cf = cpu.get_flag(CF)
        cpu.s.ax = (old_ax + 1) & 0xFFFF
        cpu.set_add_flags(old_ax, 1, old_ax + 1, 16)  # INC AX flag shape.
        cpu.set_flag(CF, old_cf)                      # INC does not affect CF.

        if cpu.get_flag(0x0040):  # ZF from INC AX; matches JZ 44AA at 450F.
            cpu.s.ip = 0x44AA
            return

        # Fall-through to 4511.  It is a jump target, not a CALL, so invoke the
        # verified 4511 replacement directly without a synthetic return word.
        expand_4plane_block_4511(cpu)
        if cpu.s.ip != 0x450C:
            return
