"""Runtime bootstrap unpacker helpers for OVERKILL's nested LZEXE stubs.

The packed original executable enters several temporary, self-relocated 16-bit
unpack stubs before the stable inner game is materialized.  Those stubs are not
part of the target source port, but during faithful cold-start runs they can
consume hundreds of thousands of interpreted instructions.  This module lifts the
hot LZEXE-style bitstream loop used by those temporary stubs while keeping it in
the explicit bootstrap island.
"""
from __future__ import annotations

from dos_re.cpu import AF, CF, ZF

# Entry at stub offset 0069 after the relocation prelude has prepared:
#   DS:SI = compressed stream, ES:DI = output stream, BP = bit buffer, DX = bits left.
SIG_LZEXE_MAIN_LOOP_0069 = bytes.fromhex(
    "d1 ed 4a 75 05 ad 89 c5 b2 10 73 03 a4 eb f1 31 c9"
)


def _lodsb(cpu, ds: int, si: int) -> tuple[int, int]:
    value = cpu.mem.rb(ds, si)
    return value, (si + 1) & 0xFFFF


def _lodsw(cpu, ds: int, si: int) -> tuple[int, int]:
    value = cpu.mem.rw(ds, si)
    return value, (si + 2) & 0xFFFF


def _next_bit(cpu, *, ds: int, si: int, bp: int, dx: int, af: bool) -> tuple[int, int, int, int, bool]:
    """Return the next LSB-first bit and updated SI/BP/DX.

    This mirrors the repeated instruction group used by the unpacker::

        shr bp,1
        dec dx
        jnz have_bit
        lodsw
        mov bp,ax
        mov dl,10h

    ``DEC`` does not modify CF, so the consumer branch still sees the carry from
    ``SHR BP,1``.
    """
    bit = bp & 0x0001
    bp = (bp >> 1) & 0xFFFF
    af = (dx & 0x000F) == 0
    dx = (dx - 1) & 0xFFFF
    if dx == 0:
        bp, si = _lodsw(cpu, ds, si)
        dx = (dx & 0xFF00) | 0x10
    return bit, si, bp, dx, af


def run_lzexe_bootstrap_main_loop_0069(cpu, *, max_ops: int = 8_000_000) -> None:
    """Lift the hot LZEXE bitstream loop at temporary stub offset ``0069``.

    The loop ends by branching to offset ``00FC`` where the original relocation
    fixup and final far jump continue.  We intentionally stop there rather than
    swallowing the whole bootstrap: the relocation tail is short and keeping it
    interpreted gives us a clean, observable boundary between the accelerated
    codec and the dynamic transfer into the next packed layer.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    dx = s.dx & 0xFFFF
    bx = s.bx & 0xFFFF
    cx = s.cx & 0xFFFF
    al = s.ax & 0x00FF
    af = bool(s.flags & AF)

    ops = 0
    while True:
        ops += 1
        if ops > max_ops:
            raise RuntimeError(
                f"bootstrap LZEXE loop at {s.cs:04X}:0069 did not finish "
                f"within {max_ops} operations"
            )

        bit, si, bp, dx, af = _next_bit(cpu, ds=ds, si=si, bp=bp, dx=dx, af=af)
        if bit:
            # 0075: MOVSB; 0076: JMP 0069
            al = mem.rb(ds, si)
            mem.wb(es, di, al)
            si = (si + 1) & 0xFFFF
            di = (di + 1) & 0xFFFF
            continue

        cx = 0
        bit, si, bp, dx, af = _next_bit(cpu, ds=ds, si=si, bp=bp, dx=dx, af=af)
        if bit:
            # 00A8 long copy token.
            ax, si = _lodsw(cpu, ds, si)
            bx = ax & 0xFFFF
            bh = (bx >> 8) & 0xFF
            ah = (ax >> 8) & 0xFF
            bh = ((bh >> 3) | 0xE0) & 0xFF
            bx = ((bh << 8) | (bx & 0x00FF)) & 0xFFFF
            ah &= 0x07
            if ah:
                cx = (ah + 2) & 0xFFFF
            else:
                al, si = _lodsb(cpu, ds, si)
                if al == 0:
                    # 00C3..00C6: LODSB; OR AL,AL; JE 00FC.
                    #
                    # The oracle continuation keeps the long-token CL seed
                    # visible here and clears AX before transferring to the
                    # relocation tail.
                    s.ds = ds
                    s.es = es
                    s.si = si
                    s.di = di
                    s.bp = bp
                    s.dx = dx
                    s.bx = bx
                    s.cx = 0x0003
                    s.ax = 0x0000
                    cpu.set_logic_flags(0, 8)
                    if af:
                        s.flags |= AF
                    else:
                        s.flags &= ~AF
                    s.ip = 0x00FC
                    return
                if al == 1:
                    # 00D1 segment-renormalization escape.  The stream can cross
                    # paragraph windows; the original adjusts both source and
                    # destination segments then resumes the same bit loop.
                    bx = di
                    di = ((di & 0x000F) + 0x2000) & 0xFFFF
                    es = (es + (bx >> 4) - 0x0200) & 0xFFFF
                    bx = si
                    si &= 0x000F
                    ds = (ds + (bx >> 4)) & 0xFFFF
                    continue
                cx = (al + 1) & 0xFFFF
        else:
            # 0078 short copy token: two literal bits encode length 2..5 and the
            # following byte is an 8-bit negative back-reference.
            bit, si, bp, dx, af = _next_bit(cpu, ds=ds, si=si, bp=bp, dx=dx, af=af)
            cx = ((cx << 1) | bit) & 0xFFFF
            bit, si, bp, dx, af = _next_bit(cpu, ds=ds, si=si, bp=bp, dx=dx, af=af)
            cx = ((cx << 1) | bit) & 0xFFFF
            cx = (cx + 2) & 0xFFFF
            al, si = _lodsb(cpu, ds, si)
            bx = (0xFF00 | al) & 0xFFFF

        # 00BB copy loop: AL = ES:[BX+DI]; STOSB; LOOP.
        for _ in range(cx):
            al = mem.rb(es, (bx + di) & 0xFFFF)
            mem.wb(es, di, al)
            di = (di + 1) & 0xFFFF
        cx = 0
