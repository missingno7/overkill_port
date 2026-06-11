from __future__ import annotations

import os

from .cpu import CF, DF, ZF, SF, PF, _PARITY
from .hooks import registry
from .memory import EGA_CPU_APERTURE, EGA_APERTURE, EGA_PLANE_STRIDE, EGA_PLANE_WINDOW


# Runtime-patched code guard -------------------------------------------------
#
# OVERKILL's unpacked EXE still patches/relocates large parts of the 1010h code
# segment during startup.  A Python replacement bypasses whatever bytes are live
# at CS:IP, so render hooks that assume one fixed instruction stream should be
# conservative: if the game later changes the entry bytes, remove the hook and
# let the interpreter execute the patched original.  Synthetic oracle tests often
# do not populate the routine bytes at all, so an all-zero signature is treated as
# "test fixture / no live code available" and the hook remains enabled.

def _self_disable_if_patched(cpu, ip: int, expected: bytes, name: str) -> bool:
    cs = cpu.s.cs & 0xFFFF
    start = ((cs << 4) + (ip & 0xFFFF)) & 0xFFFFF
    live = bytes(cpu.mem.data[start:start + len(expected)])
    if live == expected or all(b == 0 for b in live):
        return False
    if os.environ.get("OVERKILL_TRACE_CODE_PATCHES"):
        print(
            f"[overkill] disabling hook {name} at {cs:04X}:{ip:04X}: "
            f"live bytes {live.hex(' ')} != expected {expected.hex(' ')}"
        )
    cpu.replacement_hooks.pop((cs, ip & 0xFFFF), None)
    cpu.hook_names.pop((cs, ip & 0xFFFF), None)
    cpu.s.ip = ip & 0xFFFF
    return True


_SIG_2750 = bytes.fromhex("8b 36 4c 23 2e 8e 06 a4 95 2e 8e 1e 98 95 bb 0d")
_SIG_27EB = bytes.fromhex("51 2e 83 3e d6 0b 00 74 0e 56 2e 8b 0e 9c 5b 51")
_SIG_280D = bytes.fromhex("2e 8b 0e 9c 5b ac 2e 88 05 47 e2 f9 2e 2b 3e 9c")
_SIG_2824 = bytes.fromhex("bf f4 5a 2e 8b 0e 9c 5b 51 2e 8a 05 2e 8a 65 28")
_SIG_291C = bytes.fromhex("51 2e 8a 05 47 57 2e 8b 3e a6 5b aa 2e 89 3e a6")
_SIG_2932 = bytes.fromhex("2e c6 06 a0 5b 00 2e 8b 1e 9c 5b 8a 04 8a 20 d1")
_SIG_33B2 = bytes.fromhex("75 03 e9 f3 10 2e 8b 0e 9e 5b 51 2e 8b 0e 9c")
_SIG_58DF = bytes.fromhex("51 2e 89 0e 01 59 2e 8b 1e bc 95 d1 e3 2e ff 97")
_SIG_CCAA = bytes.fromhex("b9 08 00 26 8b 04 26 3b 05 74 05 b2 01 26 89 05")
_SIG_CCC4 = bytes.fromhex("b9 08 00 26 8b 04 26 3b 05 74 05 b2 01 26 89 05")
_SIG_CCF0 = bytes.fromhex("b9 20 00 26 8a 04 26 3a 05 74 05 b2 01 26 88 05")



@registry.replace(0x1010, 0xC916, "overkill_file_checksum_loop")
def overkill_file_checksum_loop(cpu):
    """Replace the tight OVERKILL data-file checksum loop.

    Original code at 1010:C916:

        mov dl, [si]
        add ax, dx
        add ah, al
        inc si
        loop C916

    This optimized version keeps all per-byte state in Python locals.  The
    first checkpoint implementation used CPU helper calls inside the loop,
    which was correct but still very slow when startup invokes this with
    CX=0000 (8086 LOOP count = 65536) many times while validating OVERKILL.
    """
    count = cpu.s.cx & 0xFFFF
    if count == 0:
        count = 0x10000

    ax = cpu.s.ax & 0xFFFF
    dh_part = cpu.s.dx & 0xFF00
    ds_base = (cpu.s.ds & 0xFFFF) << 4
    off = cpu.s.si & 0xFFFF
    remaining = count
    data = cpu.mem.data
    last_b = cpu.s.dx & 0xFF
    carry_after_ah_add = cpu.get_flag(CF)

    while remaining:
        chunk = min(remaining, 0x10000 - off)
        start = (ds_base + off) & 0xFFFFF
        for b in data[start:start + chunk]:
            last_b = b
            ax = (ax + (dh_part | b)) & 0xFFFF
            al = ax & 0xFF
            ah = (ax >> 8) & 0xFF
            sum8 = ah + al
            carry_after_ah_add = sum8 > 0xFF
            ax = ((sum8 & 0xFF) << 8) | al
        off = (off + chunk) & 0xFFFF
        remaining -= chunk

    old_si = (cpu.s.si + count - 1) & 0xFFFF
    final_si = (cpu.s.si + count) & 0xFFFF
    cpu.s.ax = ax & 0xFFFF
    cpu.s.dx = dh_part | last_b
    cpu.s.si = final_si
    cpu.s.cx = 0

    cpu.set_add_flags(old_si, 1, old_si + 1, 16)
    cpu.set_flag(CF, carry_after_ah_add)
    cpu.s.ip = 0xC91F


@registry.replace(0x1010, 0x45F6, "overkill_pack_four_pixels_45f6")
def overkill_pack_four_pixels_45f6(cpu):
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


def _overkill_read_packed_byte(cpu) -> None:
    """Shared implementation for OVERKILL's 512-byte packed-data reader.

    Mirrors 1010:0624. Result byte is returned in AL.  On refill the original
    routine calls DOS AH=3Fh and leaves AH as the high byte of the byte-count
    returned by DOS; this matters, so the hook calls the configured interrupt
    handler rather than reading Python files directly.
    """
    ds = cpu.s.ds & 0xFFFF
    saved_bx = cpu.s.bx & 0xFFFF
    cpu.mem.ww(ds, 0x0612, saved_bx)
    ptr = cpu.mem.rw(ds, 0x0610)

    if ptr >= 0x0610:
        cpu.mem.ww(ds, 0x0610, 0x0410)
        saved_cx = cpu.s.cx & 0xFFFF
        cpu.set_reg8(4, 0x3F)  # AH=3Fh read file/device
        cpu.s.bx = cpu.mem.rw(ds, 0x0240)
        cpu.s.cx = 0x0200
        cpu.s.dx = 0x0410
        if cpu.interrupt_handler is None:
            raise RuntimeError("OVERKILL packed reader needs DOS INT 21h handler")
        cpu.interrupt_handler(cpu, 0x21)
        cpu.s.cx = saved_cx
        if cpu.get_flag(CF):
            cpu.s.ip = 0x02B2
            return
        ptr = cpu.mem.rw(ds, 0x0610)

    byte = cpu.mem.rb(ds, ptr)
    cpu.set_reg8(0, byte)

    old_ptr = cpu.mem.rw(ds, 0x0610)
    new_ptr = (old_ptr + 1) & 0xFFFF
    old_cf = cpu.get_flag(CF)
    cpu.set_add_flags(old_ptr, 1, old_ptr + 1, 16)
    cpu.set_flag(CF, old_cf)
    cpu.mem.ww(ds, 0x0610, new_ptr)

    cpu.s.bx = cpu.mem.rw(ds, 0x0612)


@registry.replace(0x1010, 0x0624, "overkill_packed_read_byte")
def overkill_packed_read_byte(cpu):
    """Replace hot byte reader at 1010:0624 used by startup RLE/asset decoders."""
    _overkill_read_packed_byte(cpu)
    if cpu.s.ip != 0x02B2:
        cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x0615, "overkill_packed_read_word")
def overkill_packed_read_word(cpu):
    """Replace 1010:0615 little-endian word reader built from two byte reads."""
    _overkill_read_packed_byte(cpu)
    if cpu.s.ip == 0x02B2:
        return
    low = cpu.get_reg8(0)
    cpu.mem.wb(cpu.s.ds, 0x0614, low)
    _overkill_read_packed_byte(cpu)
    if cpu.s.ip == 0x02B2:
        return
    high = cpu.get_reg8(0)
    cpu.set_reg8(4, high)  # AH
    cpu.set_reg8(0, cpu.mem.rb(cpu.s.ds, 0x0614))
    cpu.s.ip = cpu.pop()

@registry.replace(0x1010, 0x45CB, "overkill_expand_bits_45cb")
def overkill_expand_bits_45cb(cpu):
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


def _inc_mem_word_preserve_cf(cpu, seg: int, off: int) -> None:
    old = cpu.mem.rw(seg, off)
    old_cf = cpu.get_flag(CF)
    cpu.mem.ww(seg, off, (old + 1) & 0xFFFF)
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)


def _dec_reg8_preserve_cf(cpu, reg_idx: int) -> None:
    old = cpu.get_reg8(reg_idx)
    old_cf = cpu.get_flag(CF)
    cpu.set_reg8(reg_idx, (old - 1) & 0xFF)
    cpu.set_sub_flags(old, 1, old - 1, 8)
    cpu.set_flag(CF, old_cf)


@registry.replace(0x1010, 0x03A8, "overkill_vertical_rle_decoder_03a8")
def overkill_vertical_rle_decoder_03a8(cpu):
    """Replace the vertical byte RLE startup decoder at 1010:03A8.

    The original routine is not a normal near function: when the image is
    complete it jumps to the common dispatcher continuation at 1010:02A8.

    Header words are read through the original packed stream reader:

        word0 -> CS:03A2
        word1 -> DS:03A4   ; also read back through CS:03A4 as column count/stride
        word2 -> DS:03A6

    Then it decodes one vertical RLE stream per column.  Byte 0x80 ends the
    current column.  Bytes 00..7F copy N+1 following literal bytes downward by
    the stride.  Bytes 81..FF repeat the following byte (-N)+1 times downward.

    This hook intentionally preserves the odd AX/AH/BL side effects of the ASM
    around the packed byte reader, because those registers carry across RLE
    commands and can differ when a DOS refill changes AH to the high byte of the
    byte count returned by INT 21h AH=3Fh.
    """
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF

    cpu.s.es = cpu.mem.rw(ds, 0x023A)
    start_di = cpu.mem.rw(ds, 0x023C)
    cpu.s.di = start_di

    _overkill_read_packed_byte(cpu)
    if cpu.s.ip == 0x02B2:
        return
    lo = cpu.get_reg8(0)
    _overkill_read_packed_byte(cpu)
    if cpu.s.ip == 0x02B2:
        return
    word0 = lo | (cpu.get_reg8(0) << 8)
    cpu.s.ax = word0
    cpu.mem.ww(cs, 0x03A2, word0)

    _overkill_read_packed_byte(cpu)
    if cpu.s.ip == 0x02B2:
        return
    lo = cpu.get_reg8(0)
    _overkill_read_packed_byte(cpu)
    if cpu.s.ip == 0x02B2:
        return
    word1 = lo | (cpu.get_reg8(0) << 8)
    cpu.s.ax = word1
    cpu.mem.ww(ds, 0x03A4, word1)

    _overkill_read_packed_byte(cpu)
    if cpu.s.ip == 0x02B2:
        return
    lo = cpu.get_reg8(0)
    _overkill_read_packed_byte(cpu)
    if cpu.s.ip == 0x02B2:
        return
    word2 = lo | (cpu.get_reg8(0) << 8)
    cpu.s.ax = word2
    cpu.mem.ww(ds, 0x03A6, word2)

    # Original uses CS:03A4 for both outer LOOP count and vertical stride.
    # In the real runtime DS==CS here, but using CS keeps the hook bit-faithful.
    stride = cpu.mem.rw(cs, 0x03A4)
    columns = stride
    cpu.s.cx = columns
    outer_di = cpu.s.di & 0xFFFF

    while cpu.s.cx != 0:
        saved_outer_cx = cpu.s.cx & 0xFFFF
        saved_outer_di = outer_di & 0xFFFF
        cpu.s.di = saved_outer_di

        while True:
            _overkill_read_packed_byte(cpu)
            if cpu.s.ip == 0x02B2:
                return
            control = cpu.get_reg8(0)
            cpu.set_sub_flags(control, 0x80, control - 0x80, 8)  # CMP AL,80h

            if control == 0x80:
                break

            if control > 0x80:
                # NEG AL; XCHG AL,AH; XCHG AH,BL; CALL 0624; XCHG AH,BL
                cpu.set_sub_flags(0, control, -control, 8)
                cpu.set_reg8(0, (-control) & 0xFF)

                al = cpu.get_reg8(0)
                ah = cpu.get_reg8(4)
                cpu.set_reg8(0, ah)
                cpu.set_reg8(4, al)

                ah = cpu.get_reg8(4)
                bl = cpu.get_reg8(3)
                cpu.set_reg8(4, bl)
                cpu.set_reg8(3, ah)

                _overkill_read_packed_byte(cpu)
                if cpu.s.ip == 0x02B2:
                    return

                ah = cpu.get_reg8(4)
                bl = cpu.get_reg8(3)
                cpu.set_reg8(4, bl)
                cpu.set_reg8(3, ah)

                while True:
                    cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.get_reg8(0))
                    cpu.s.di = (cpu.s.di + stride) & 0xFFFF
                    # ADD DI,stride flags are overwritten by the following INC/DEC in this loop.
                    _inc_mem_word_preserve_cf(cpu, ds, 0x0244)
                    _dec_reg8_preserve_cf(cpu, 4)  # DEC AH
                    if cpu.get_flag(0x0080):      # JNS not taken when SF=1
                        break
                continue

            # Literal run: PUSH AX; CALL 0624; STOSB; INC [0244]; POP AX; DEC AL; JNS
            while True:
                saved_ax = cpu.s.ax & 0xFFFF
                _overkill_read_packed_byte(cpu)
                if cpu.s.ip == 0x02B2:
                    return
                cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.get_reg8(0))
                cpu.s.di = (cpu.s.di + stride) & 0xFFFF
                _inc_mem_word_preserve_cf(cpu, ds, 0x0244)
                cpu.s.ax = saved_ax
                _dec_reg8_preserve_cf(cpu, 0)  # DEC AL
                if cpu.get_flag(0x0080):       # JNS not taken when SF=1
                    break

        # POP DI; INC DI; POP CX; LOOP outer
        cpu.s.di = saved_outer_di
        old_di = cpu.s.di & 0xFFFF
        old_cf = cpu.get_flag(CF)
        cpu.s.di = (cpu.s.di + 1) & 0xFFFF
        cpu.set_add_flags(old_di, 1, old_di + 1, 16)  # INC DI
        cpu.set_flag(CF, old_cf)
        outer_di = cpu.s.di

        cpu.s.cx = saved_outer_cx
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        # LOOP does not affect flags.

    cpu.s.ip = 0x02A8


def _call_hook_like_near_call(cpu, handler, return_ip: int) -> None:
    """Run a replacement body with the same stack side effect as CALL/RET."""
    cpu.push(return_ip & 0xFFFF)
    handler(cpu)


def _stosw(cpu) -> None:
    cpu.mem.ww(cpu.s.es, cpu.s.di, cpu.s.ax)
    cpu.s.di = (cpu.s.di + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF


@registry.replace(0x1010, 0x4511, "overkill_expand_4plane_block_4511")
def overkill_expand_4plane_block_4511(cpu):
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


def _tandy_cell_33dd_core(cpu) -> None:
    """Fast lifted body of one 1010:33DD Tandy source cell expansion.

    The original calls 344B four times.  Each call rotates two bits from
    DH/DL/AH/AL into CL, optionally masks transparent nibbles into CH, and then
    33DD stores the four CL/CH pairs as two Tandy packed words.  At the 33DD
    boundary all rotate/transparency-test flags have been overwritten by the
    final ``CMP CS:[0BD6],0``, so this can use direct bit arithmetic while still
    matching interpreted ASM at the hook continuation.
    """
    s = cpu.s
    mem = cpu.mem
    rb, rw, wb = mem.rb, mem.rw, mem.wb
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    width = rw(cs, 0x5B9C)
    si = s.si & 0xFFFF

    s.bx = width
    al = rb(ds, si)
    ah = rb(ds, (si + s.bx) & 0xFFFF)
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1
    dl = rb(ds, (si + s.bx) & 0xFFFF)
    old_bx = s.bx
    s.bx = (s.bx + width) & 0xFFFF
    cpu.set_add_flags(old_bx, width, old_bx + width, 16)
    dh = rb(ds, (si + s.bx) & 0xFFFF)

    bd6 = rw(cs, 0x0BD6)
    transparent_color = rb(cs, 0x0000) if bd6 else 0
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
            if (cl & 0x0F) == transparent_color:
                ch |= 0x0F
                cl &= 0xF0
            if ((cl >> 4) & 0x0F) == transparent_color:
                ch |= 0xF0
                cl &= 0x0F
        else:
            ch = entry_ch
        cls.append(cl & 0xFF)
        chs.append(ch & 0xFF)

    c0, c1, c2, c3 = cls
    m0, m1, m2, m3 = chs
    wb(cs, 0x5B95, c0); wb(cs, 0x5B99, m0)
    wb(cs, 0x5B94, c1); wb(cs, 0x5B98, m1)
    wb(cs, 0x5B97, c2); wb(cs, 0x5B9B, m2)
    wb(cs, 0x5B96, c3); wb(cs, 0x5B9A, m3)

    old_si = s.si & 0xFFFF
    s.si = (old_si + 1) & 0xFFFF
    old_cf = cpu.get_flag(CF)
    cpu.set_add_flags(old_si, 1, old_si + 1, 16)  # INC SI, preserving CF.
    cpu.set_flag(CF, old_cf)

    cpu.set_sub_flags(bd6, 0, bd6, 16)
    if bd6 != 0:
        s.ax = rw(cs, 0x5B9A)
        _stosw(cpu)
    s.ax = rw(cs, 0x5B96)
    _stosw(cpu)

    cpu.set_sub_flags(bd6, 0, bd6, 16)
    if bd6 != 0:
        s.ax = rw(cs, 0x5B98)
        _stosw(cpu)
    s.ax = rw(cs, 0x5B94)
    _stosw(cpu)

    s.bx = ((ah << 8) | al) if bd6 else (width * 3) & 0xFFFF
    s.cx = (((m3 if bd6 else entry_ch) << 8) | c3) & 0xFFFF
    s.dx = ((dh << 8) | dl) & 0xFFFF


@registry.replace(0x1010, 0x33DD, "overkill_expand_tandy_cell_33dd")
def overkill_expand_tandy_cell_33dd(cpu):
    """Verified replacement for the Tandy packed-pixel cell expander at 1010:33DD."""
    _tandy_cell_33dd_core(cpu)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x33B2, "overkill_expand_tandy_block_33b2")
def overkill_expand_tandy_block_33b2(cpu):
    """Replace the hot Tandy startup block renderer/list continuation at 1010:33B2."""
    if _self_disable_if_patched(cpu, 0x33B2, _SIG_33B2, "overkill_expand_tandy_block_33b2"):
        return

    s = cpu.s
    if s.flags & ZF:
        s.ip = 0x44AA
        return

    cs = s.cs & 0xFFFF
    height = cpu.mem.rw(cs, 0x5B9E)
    width = cpu.mem.rw(cs, 0x5B9C)
    entry_sp = s.sp & 0xFFFF
    wrote_call_scratch = False

    outer = height
    while outer != 0:
        col = width
        while col != 0:
            wrote_call_scratch = True
            s.cx = col
            _tandy_cell_33dd_core(cpu)
            col = (col - 1) & 0xFFFF  # LOOP column, flags unaffected.

        si = (s.si + width + width) & 0xFFFF
        cpu.set_add_flags(si, width, si + width, 16)
        s.si = (si + width) & 0xFFFF
        outer = (outer - 1) & 0xFFFF  # LOOP row, flags unaffected.

    if wrote_call_scratch:
        ss = s.ss & 0xFFFF
        cpu.mem.ww(ss, (entry_sp - 6) & 0xFFFF, 0x33C6)
        cpu.mem.ww(ss, (entry_sp - 4) & 0xFFFF, 0x0001)
        cpu.mem.ww(ss, (entry_sp - 2) & 0xFFFF, 0x0001)

    s.cx = 0
    s.ip = 0x33AF


@registry.replace(0x1010, 0xEDE9, "overkill_lz_output_byte_ede9")
def overkill_lz_output_byte_ede9(cpu):
    """Replace byte-output helper at 1010:EDE9 used by the LZ-style decoder."""
    # STOSB
    cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.get_reg8(0))
    cpu.s.di = (cpu.s.di + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF

    # OR DI,DI
    cpu.set_logic_flags(cpu.s.di, 16)
    if cpu.s.di == 0:
        # PUSH AX; MOV AX,ES; ADD AX,1000h; MOV ES,AX; POP AX
        saved_ax = cpu.s.ax & 0xFFFF
        ax = cpu.s.es & 0xFFFF
        result = ax + 0x1000
        cpu.set_add_flags(ax, 0x1000, result, 16)
        cpu.s.es = result & 0xFFFF
        cpu.s.ax = saved_ax

    # INC word ptr CS:EDE5; if it wrapped, INC word ptr CS:EDE7.
    old = cpu.mem.rw(cpu.s.cs, 0xEDE5)
    old_cf = cpu.get_flag(CF)
    new = (old + 1) & 0xFFFF
    cpu.mem.ww(cpu.s.cs, 0xEDE5, new)
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)
    if new == 0:
        old2 = cpu.mem.rw(cpu.s.cs, 0xEDE7)
        old_cf = cpu.get_flag(CF)
        cpu.mem.ww(cpu.s.cs, 0xEDE7, (old2 + 1) & 0xFFFF)
        cpu.set_add_flags(old2, 1, old2 + 1, 16)
        cpu.set_flag(CF, old_cf)

    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0xED97, "overkill_lz_input_byte_ed97")
def overkill_lz_input_byte_ed97(cpu):
    """Replace byte-input helper at 1010:ED97 used by the LZ-style decoder.

    The routine reads from a 1 KiB buffer at DS:D8B8+SI.  When SI wraps to zero
    it refills that buffer from DOS handle CS:D666.  It also has a one-byte
    pushback slot at CS:EE04/EE05 used by the decoder around ED5C..EDDA.
    """
    cs = cpu.s.cs & 0xFFFF
    # TEST byte ptr CS:EE04,0FFh
    pushback_flag = cpu.mem.rb(cs, 0xEE04)
    cpu.set_logic_flags(pushback_flag & 0xFF, 8)
    if pushback_flag != 0:
        cpu.set_reg8(0, cpu.mem.rb(cs, 0xEE05))
        cpu.mem.wb(cs, 0xEE04, 0)
        cpu.s.ip = cpu.pop()
        return

    # ADD SI,D8B8h; LODSB; SUB SI,D8B8h; AND SI,03FFh
    old_si = cpu.s.si & 0xFFFF
    added = old_si + 0xD8B8
    cpu.s.si = added & 0xFFFF
    cpu.set_add_flags(old_si, 0xD8B8, added, 16)

    cpu.set_reg8(0, cpu.mem.rb(cpu.s.ds, cpu.s.si))
    cpu.s.si = (cpu.s.si + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF

    before_sub = cpu.s.si & 0xFFFF
    sub_result = before_sub - 0xD8B8
    cpu.s.si = sub_result & 0xFFFF
    cpu.set_sub_flags(before_sub, 0xD8B8, sub_result, 16)

    and_result = cpu.s.si & 0x03FF
    cpu.s.si = and_result
    cpu.set_logic_flags(and_result, 16)
    saved_flags_after_and = cpu.s.flags & 0xFFFF

    if cpu.s.si == 0:
        saved = (cpu.s.ax, cpu.s.bx, cpu.s.cx, cpu.s.dx, cpu.s.si, cpu.s.di, cpu.s.bp, cpu.s.flags)
        cpu.s.dx = 0xD8B8
        cpu.s.ax = 0x3F00
        cpu.s.bx = cpu.mem.rw(cs, 0xD666)
        cpu.s.cx = 0x0400
        if cpu.interrupt_handler is None:
            raise RuntimeError("OVERKILL LZ reader needs DOS INT 21h handler")
        cpu.interrupt_handler(cpu, 0x21)
        cpu.s.ax, cpu.s.bx, cpu.s.cx, cpu.s.dx, cpu.s.si, cpu.s.di, cpu.s.bp, _ = saved
        cpu.s.flags = saved_flags_after_and | 0x0002

    cpu.s.ip = cpu.pop()


@registry.replace(0x254A, 0x05BF, "overkill_overlay_xor_decode_254a_05bf")
def overkill_overlay_xor_decode_254a_05bf(cpu):
    """Replace the small overlay/file-block XOR decode loop at 254A:05BF.

    Original loop:

        xor [di],al
        inc di
        add al,ah
        loop 05BF

    It is reached after an INT 21h read into DS:075C and is stable for the
    default PSP/load layout used by this project.
    """
    count = cpu.s.cx & 0xFFFF
    if count == 0:
        count = 0x10000
    al = cpu.get_reg8(0)
    ah = cpu.get_reg8(4)
    di = cpu.s.di & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    data = cpu.mem.data
    base = (ds << 4) & 0xFFFFF
    last_add_a = al
    last_add_result = al
    for _ in range(count):
        addr = (base + di) & 0xFFFFF
        data[addr] ^= al
        di = (di + 1) & 0xFFFF
        last_add_a = al
        last_add_result = al + ah
        al = last_add_result & 0xFF
    cpu.set_reg8(0, al)
    cpu.s.di = di
    cpu.s.cx = 0
    cpu.set_add_flags(last_add_a, ah, last_add_result, 8)
    cpu.s.ip = 0x05C6


@registry.replace(0x1010, 0xED7A, "overkill_lz_backref_copy_ed7a")
def overkill_lz_backref_copy_ed7a(cpu):
    """Replace the LZ back-reference copy loop at 1010:ED7A."""
    count = cpu.s.cx & 0xFFFF
    if count == 0:
        count = 0x10000
    cs = cpu.s.cs & 0xFFFF
    for _ in range(count):
        cpu.set_reg8(0, cpu.mem.rb(cs, (cpu.s.bx + 0xDCB8) & 0xFFFF))
        _call_hook_like_near_call(cpu, overkill_lz_output_byte_ede9, 0xED82)
        cpu.mem.wb(cs, (cpu.s.bp + 0xDCB8) & 0xFFFF, cpu.get_reg8(0))

        old_bx = cpu.s.bx & 0xFFFF
        old_cf = cpu.get_flag(CF)
        cpu.s.bx = (cpu.s.bx + 1) & 0xFFFF
        cpu.set_add_flags(old_bx, 1, old_bx + 1, 16)
        cpu.set_flag(CF, old_cf)
        cpu.s.bx &= 0x0FFF
        cpu.set_logic_flags(cpu.s.bx, 16)

        old_bp = cpu.s.bp & 0xFFFF
        old_cf = cpu.get_flag(CF)
        cpu.s.bp = (cpu.s.bp + 1) & 0xFFFF
        cpu.set_add_flags(old_bp, 1, old_bp + 1, 16)
        cpu.set_flag(CF, old_cf)
        cpu.s.bp &= 0x0FFF
        cpu.set_logic_flags(cpu.s.bp, 16)

        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unaffected.
    cpu.s.ip = 0xED26

@registry.replace(0x1010, 0xECF2, "overkill_lz_decoder_ecf2")
def overkill_lz_decoder_ecf2(cpu):
    """Full verified replacement for OVERKILL's 1010:ECF2 LZ asset decoder.

    Byte input, byte output, and back-reference copying are inlined here (rather
    than dispatched through the ED97/EDE9/ED7A helper hooks) so a whole
    compressed asset completes in one hook invocation without spending minutes in
    nested Python call/flag overhead.  The observable result is verified against
    the interpreted ASM by the ECF2 oracle test.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    data = mem.data

    def rb(seg: int, off: int) -> int:
        return data[(((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF]

    def wb(seg: int, off: int, value: int) -> None:
        data[(((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF] = value & 0xFF

    def ww(seg: int, off: int, value: int) -> None:
        wb(seg, off, value)
        wb(seg, (off + 1) & 0xFFFF, value >> 8)

    def read_input_byte() -> int:
        # Mirrors ED97.  Most flags are not live across the full decoder except
        # for the explicit TEST/CMP branches reproduced in the outer logic.
        if rb(cs, 0xEE04) != 0:
            value = rb(cs, 0xEE05)
            wb(cs, 0xEE04, 0)
            cpu.set_reg8(0, value)
            return value

        ds = cpu.s.ds & 0xFFFF
        temp_si = (cpu.s.si + 0xD8B8) & 0xFFFF
        value = rb(ds, temp_si)
        temp_si = (temp_si + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF
        cpu.s.si = (temp_si - 0xD8B8) & 0xFFFF
        cpu.s.si &= 0x03FF

        if cpu.s.si == 0:
            saved = (cpu.s.ax, cpu.s.bx, cpu.s.cx, cpu.s.dx, cpu.s.si, cpu.s.di, cpu.s.bp, cpu.s.flags)
            cpu.s.dx = 0xD8B8
            cpu.s.ax = 0x3F00
            cpu.s.bx = mem.rw(cs, 0xD666)
            cpu.s.cx = 0x0400
            if cpu.interrupt_handler is None:
                raise RuntimeError("OVERKILL LZ decoder needs DOS INT 21h handler")
            cpu.interrupt_handler(cpu, 0x21)
            cpu.s.ax, cpu.s.bx, cpu.s.cx, cpu.s.dx, cpu.s.si, cpu.s.di, cpu.s.bp, cpu.s.flags = saved

        cpu.set_reg8(0, value)
        return value

    def output_byte(value: int) -> None:
        wb(cpu.s.es, cpu.s.di, value)
        cpu.s.di = (cpu.s.di + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF
        if cpu.s.di == 0:
            cpu.s.es = (cpu.s.es + 0x1000) & 0xFFFF
        counter = (mem.rw(cs, 0xEDE5) + 1) & 0xFFFF
        mem.ww(cs, 0xEDE5, counter)
        if counter == 0:
            mem.ww(cs, 0xEDE7, (mem.rw(cs, 0xEDE7) + 1) & 0xFFFF)

    # ECF2 PUSH ES / ED95 POP ES; RET.
    cpu.push(cpu.s.es)

    mem.ww(cs, 0xEDE5, 0)
    mem.ww(cs, 0xEDE7, 0)
    cpu.s.di = mem.rw(cs, 0xECEE)
    cpu.s.es = mem.rw(cs, 0xECF0)
    wb(cs, 0xEE04, 0)
    cpu.s.si = 0
    cpu.s.bp = 0
    cpu.s.cx = 0x07F7

    while cpu.s.cx != 0:
        ww(cs, (0xDCB8 + cpu.s.bp) & 0xFFFF, 0)
        cpu.s.bp = (cpu.s.bp + 2) & 0xFFFF
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF

    cpu.s.bp = 0x0FEE
    cpu.s.dx = 0
    cpu.s.cx = 0

    guard = 0
    while True:
        guard += 1
        if guard > 200_000:
            raise RuntimeError("OVERKILL LZ decoder did not reach terminator")

        cpu.s.dx = (cpu.s.dx >> 1) & 0xFFFF
        if (cpu.s.dx & 0x0100) == 0:
            flag_byte = read_input_byte()
            cpu.s.dx = 0xFF00 | flag_byte

        if cpu.s.dx & 1:
            value = read_input_byte()
            output_byte(value)
            wb(cs, (0xDCB8 + cpu.s.bp) & 0xFFFF, value)
            cpu.s.bp = (cpu.s.bp + 1) & 0x0FFF
            cpu.s.cx = 0
            continue

        first = read_input_byte()
        second = read_input_byte()
        cpu.s.ax = ((second & 0xFF) << 8) | first
        cpu.set_sub_flags(cpu.s.ax, 0, cpu.s.ax, 16)
        if cpu.s.ax == 0:
            extra = read_input_byte()
            cpu.set_reg8(0, extra)
            cpu.set_sub_flags(extra, 0, extra, 8)
            if extra == 0:
                cpu.s.es = cpu.pop()
                cpu.s.ip = cpu.pop()
                return
            wb(cs, 0xEE04, 1)
            wb(cs, 0xEE05, extra)
            cpu.set_reg8(0, 0)
            # AX is now exactly zero, matching MOV AL,0 with AH already zero.
            cpu.s.ax &= 0xFF00

        ah = (cpu.s.ax >> 8) & 0xFF
        length = (ah & 0x0F) + 3
        offset = (((ah >> 4) << 8) | (cpu.s.ax & 0xFF)) & 0x0FFF
        cpu.s.bx = offset
        cpu.s.cx = length

        while cpu.s.cx != 0:
            value = rb(cs, (0xDCB8 + cpu.s.bx) & 0xFFFF)
            cpu.set_reg8(0, value)
            output_byte(value)
            wb(cs, (0xDCB8 + cpu.s.bp) & 0xFFFF, value)
            cpu.s.bx = (cpu.s.bx + 1) & 0x0FFF
            cpu.s.bp = (cpu.s.bp + 1) & 0x0FFF
            cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF

@registry.replace(0x1010, 0x0367, "overkill_linear_byte_rle_decoder_0367_fast")
def overkill_linear_byte_rle_decoder_0367(cpu):
    """Verified replacement for 1010:0367 linear byte-RLE decoder.

    Each literal/repeat run is collapsed into a small Python loop instead of
    invoking the packed byte-reader hook and recomputing flags per output byte,
    which matters because the real startup stream can contain very large images.
    The externally observed state matches the interpreted ASM (oracle test).
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    data = mem.data

    def rb(seg: int, off: int) -> int:
        return data[(((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF]

    def wb(seg: int, off: int, value: int) -> None:
        data[(((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF] = value & 0xFF

    def read_packed_byte() -> int | None:
        saved_bx = cpu.s.bx & 0xFFFF
        mem.ww(ds, 0x0612, saved_bx)
        ptr = mem.rw(ds, 0x0610)
        if ptr >= 0x0610:
            mem.ww(ds, 0x0610, 0x0410)
            saved_cx = cpu.s.cx & 0xFFFF
            cpu.set_reg8(4, 0x3F)
            cpu.s.bx = mem.rw(ds, 0x0240)
            cpu.s.cx = 0x0200
            cpu.s.dx = 0x0410
            if cpu.interrupt_handler is None:
                raise RuntimeError("OVERKILL 0367 RLE needs DOS INT 21h handler")
            cpu.interrupt_handler(cpu, 0x21)
            cpu.s.cx = saved_cx
            if cpu.get_flag(CF):
                cpu.s.ip = 0x02B2
                return None
            ptr = mem.rw(ds, 0x0610)
        value = rb(ds, ptr)
        cpu.set_reg8(0, value)
        mem.ww(ds, 0x0610, (ptr + 1) & 0xFFFF)
        cpu.s.bx = mem.rw(ds, 0x0612)
        return value

    def write_byte(value: int) -> None:
        wb(cpu.s.es, cpu.s.di, value)
        cpu.s.di = (cpu.s.di + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF

    cpu.s.es = mem.rw(ds, 0x023A)
    cpu.s.di = mem.rw(ds, 0x023C)

    guard = 0
    while True:
        guard += 1
        if guard > 1_000_000:
            raise RuntimeError("OVERKILL 0367 byte RLE did not reach terminator")

        control = read_packed_byte()
        if control is None:
            return
        cpu.set_sub_flags(control, 0x80, control - 0x80, 8)
        if control == 0x80:
            cpu.s.ip = 0x02A8
            return

        if control > 0x80:
            # Keep the visible register shuffling from NEG/XCHG/CALL/XCHG.
            cpu.set_sub_flags(0, control, -control, 8)
            cpu.set_reg8(0, (-control) & 0xFF)
            al = cpu.get_reg8(0); ah = cpu.get_reg8(4)
            cpu.set_reg8(0, ah); cpu.set_reg8(4, al)
            ah = cpu.get_reg8(4); bl = cpu.get_reg8(3)
            cpu.set_reg8(4, bl); cpu.set_reg8(3, ah)
            value = read_packed_byte()
            if value is None:
                return
            ah = cpu.get_reg8(4); bl = cpu.get_reg8(3)
            cpu.set_reg8(4, bl); cpu.set_reg8(3, ah)
            count = (cpu.get_reg8(4) + 1) & 0x1FF
            for _ in range(count):
                write_byte(value)
            mem.ww(ds, 0x0244, (mem.rw(ds, 0x0244) + count) & 0xFFFF)
            # Final DEC AH when AH was 00h exits the JNS loop.
            cpu.set_reg8(4, 0)
            _dec_reg8_preserve_cf(cpu, 4)
            continue

        # Literal run, count = AL + 1.  Data reads do not affect the branch
        # structure; the final DEC AL decides loop exit and defines flags.
        saved_ah = cpu.get_reg8(4)
        count = control + 1
        for _ in range(count):
            value = read_packed_byte()
            if value is None:
                return
            write_byte(value)
        mem.ww(ds, 0x0244, (mem.rw(ds, 0x0244) + count) & 0xFFFF)
        cpu.set_reg8(4, saved_ah)
        cpu.set_reg8(0, 0)
        _dec_reg8_preserve_cf(cpu, 0)


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
    - final flags: AF/OF (and base word) from `CMP CS:[0BD6],0`, then CF from
      bit15 of CS:[45E4] before the last RCL16 (= bit0 of the word's previous
      content) and ZF/SF/PF from the final word, exactly as the RCL16 chain
      leaves them.

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

    cpu.set_sub_flags(bd6, 0, bd6, 16)          # CMP CS:[0BD6],0 -> AF/OF base
    f = s.flags & ~0x00C5                        # clear CF, PF, ZF, SF
    if prev45e4_bit0:
        f |= CF
    if w2 == 0:
        f |= ZF
    if w2 & 0x8000:
        f |= SF
    if _PARITY[w2 & 0xFF]:
        f |= PF
    s.flags = (f | 0x0002) & 0x0FFF


@registry.replace(0x1010, 0x4537, "overkill_expand_4plane_row_4537_fast")
def overkill_expand_4plane_row_4537(cpu):
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

@registry.replace(0x1010, 0x450C, "overkill_expand_4plane_list_450c")
def overkill_expand_4plane_list_450c(cpu):
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
        overkill_expand_4plane_block_4511(cpu)
        if cpu.s.ip != 0x450C:
            return


def _inc_reg16_preserve_cf(cpu, reg_idx: int) -> None:
    old = cpu.get_reg16(reg_idx)
    old_cf = cpu.get_flag(CF)
    cpu.set_reg16(reg_idx, (old + 1) & 0xFFFF)
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)


def _dec_reg16_preserve_cf(cpu, reg_idx: int) -> None:
    old = cpu.get_reg16(reg_idx)
    old_cf = cpu.get_flag(CF)
    cpu.set_reg16(reg_idx, (old - 1) & 0xFFFF)
    cpu.set_sub_flags(old, 1, old - 1, 16)
    cpu.set_flag(CF, old_cf)


def _add_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    result = old + (value & 0xFFFF)
    cpu.set_reg16(reg_idx, result)
    cpu.set_add_flags(old, value & 0xFFFF, result, 16)


def _sub_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    result = old - (value & 0xFFFF)
    cpu.set_reg16(reg_idx, result)
    cpu.set_sub_flags(old, value & 0xFFFF, result, 16)


def _add_mem_word(cpu, seg: int, off: int, value: int) -> None:
    old = cpu.mem.rw(seg, off)
    result = old + (value & 0xFFFF)
    cpu.mem.ww(seg, off, result)
    cpu.set_add_flags(old, value & 0xFFFF, result, 16)


def _sub_mem_word(cpu, seg: int, off: int, value: int) -> None:
    old = cpu.mem.rw(seg, off)
    result = old - (value & 0xFFFF)
    cpu.mem.ww(seg, off, result)
    cpu.set_sub_flags(old, value & 0xFFFF, result, 16)




def _ega_aperture_overlap(seg: int, off: int, count: int) -> bool:
    """Return True when a flat byte transfer touches the emulated EGA aperture.

    Real EGA memory is not a linear bytearray: reads come from the selected read
    plane and writes land in the planes selected by the sequencer map mask.
    Slice-copy fast paths must therefore avoid this range, otherwise only one
    shadow plane is updated/read and moving EGA sprites leave coloured ghosts.
    The fast callers already restrict transfers to non-wrapping 16-bit offsets,
    so a simple physical interval check is enough here.
    """
    if count <= 0:
        return False
    start = (((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF
    end = start + count
    ega_start = EGA_CPU_APERTURE
    ega_end = EGA_CPU_APERTURE + EGA_PLANE_WINDOW
    return start < ega_end and end > ega_start

def _cmp_word(cpu, a: int, b: int) -> None:
    cpu.set_sub_flags(a & 0xFFFF, b & 0xFFFF, (a & 0xFFFF) - (b & 0xFFFF), 16)


def _test_word(cpu, a: int, b: int) -> None:
    cpu.set_logic_flags((a & 0xFFFF) & (b & 0xFFFF), 16)


def _xor_al_al(cpu) -> None:
    cpu.set_reg8(0, 0)
    cpu.set_logic_flags(0, 8)


def _rep_movsb(cpu, count: int) -> None:
    count &= 0xFFFF
    if count == 0:
        cpu.s.cx = 0
        return

    # Fast path for the normal forward, non-wrapping case used by the render
    # blitters.  REP MOVSB does not alter FLAGS, so a bytearray slice copy is
    # behavior-equivalent as long as the 16-bit source/destination offsets and
    # 20-bit physical addresses do not wrap inside the transfer.
    if not cpu.get_flag(DF):
        si = cpu.s.si & 0xFFFF
        di = cpu.s.di & 0xFFFF
        if si + count <= 0x10000 and di + count <= 0x10000 \
                and not (cpu.mem.ega_planar and (
                    _ega_aperture_overlap(cpu.s.ds, si, count)
                    or _ega_aperture_overlap(cpu.s.es, di, count)
                )):
            src = (((cpu.s.ds & 0xFFFF) << 4) + si) & 0xFFFFF
            dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
            if src + count <= len(cpu.mem.data) and dst + count <= len(cpu.mem.data):
                cpu.mem.data[dst:dst + count] = cpu.mem.data[src:src + count]
                cpu.s.si = (si + count) & 0xFFFF
                cpu.s.di = (di + count) & 0xFFFF
                cpu.s.cx = 0
                return

    delta = -1 if cpu.get_flag(DF) else 1
    for _ in range(count):
        cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.mem.rb(cpu.s.ds, cpu.s.si))
        cpu.s.si = (cpu.s.si + delta) & 0xFFFF
        cpu.s.di = (cpu.s.di + delta) & 0xFFFF
    cpu.s.cx = 0


def _rep_stosb(cpu, count: int) -> None:
    count &= 0xFFFF
    if count == 0:
        cpu.s.cx = 0
        return
    value = cpu.get_reg8(0)
    if not cpu.get_flag(DF):
        di = cpu.s.di & 0xFFFF
        if di + count <= 0x10000 \
                and not (cpu.mem.ega_planar and _ega_aperture_overlap(cpu.s.es, di, count)):
            dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
            if dst + count <= len(cpu.mem.data):
                cpu.mem.data[dst:dst + count] = bytes([value]) * count
                cpu.s.di = (di + count) & 0xFFFF
                cpu.s.cx = 0
                return
    delta = -1 if cpu.get_flag(DF) else 1
    for _ in range(count):
        cpu.mem.wb(cpu.s.es, cpu.s.di, value)
        cpu.s.di = (cpu.s.di + delta) & 0xFFFF
    cpu.s.cx = 0


def _ega_next_scanline_di(cpu) -> None:
    """Mirror OVERKILL's planar 80-byte EGA/VGA row address advance."""
    _add_reg16(cpu, 7, 0x2000)  # ADD DI,2000h
    _test_word(cpu, cpu.s.di, 0x4000)
    if not cpu.get_flag(ZF):
        _add_reg16(cpu, 7, 0xC050)


@registry.replace(0x1010, 0x497A, "overkill_blit_scaled_column_block_497a")
def overkill_blit_scaled_column_block_497a(cpu):
    """Replace the hot display blit/clear routine at 1010:497A.

    Evidence: reached from the renderer dispatcher at 1010:58EC through a
    function-pointer table selected by CS:95BC.  The routine copies rows from
    DS:SI to ES:DI (usually decoded asset buffer -> B800 planar video memory),
    optionally skipping/duplicating source rows according to CS:5901/5903/5905,
    and uses the same planar address step as the original inner loops.

    This is deliberately a direct transliteration of 497A..4A40, not a guessed
    high-level renderer.  It preserves the observed register/flag/stack state
    by using the same arithmetic flag helpers as the interpreter.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    # 497A: mov cs:[5903],0000h
    mem.ww(cs, 0x5903, 0)
    # 4981..4995: load local state and double BP (source bytes per row)
    cpu.s.di = mem.rw(cs, 0x58F9)
    cpu.s.si = mem.rw(cs, 0x58FB)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    cpu.s.bp = mem.rw(cs, 0x58FF)
    cpu.s.bp = cpu.shift(4, cpu.s.bp, 1, 16)  # SHL BP,1

    # Optional bottom-up source positioning.
    _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
    if not cpu.get_flag(ZF):
        cpu.s.ax = cpu.s.bp & 0xFFFF
        _dec_reg16_preserve_cf(cpu, 1)  # DEC CX
        # MUL CX, matching CPU8086 group-F7 behavior: AX*CX -> DX:AX, CF/OF only.
        result = (cpu.s.ax & 0xFFFF) * (cpu.s.cx & 0xFFFF)
        cpu.s.ax = result & 0xFFFF
        cpu.s.dx = (result >> 16) & 0xFFFF
        carry = cpu.s.dx != 0
        cpu.set_flag(CF, carry)
        cpu.set_flag(0x0800, carry)  # OF
        _inc_reg16_preserve_cf(cpu, 1)  # INC CX
        _add_reg16(cpu, 6, cpu.s.ax)    # ADD SI,AX

    # Initial clear/skip region before the first copied row.
    cpu.push(cpu.s.cx)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    _sub_reg16(cpu, 1, mem.rw(cs, 0x5901))
    _test_word(cpu, cpu.s.cx, cpu.s.cx)  # OR CX,CX
    if not cpu.get_flag(SF):
        cpu.s.cx = cpu.shift(5, cpu.s.cx, 1, 16)  # SHR CX,1
        if cpu.s.cx != 0:
            _dec_reg16_preserve_cf(cpu, 1)
            if cpu.s.cx != 0:
                # 49BD..49CB: advance DI by CX-1 planar rows.
                while cpu.s.cx != 0:
                    _ega_next_scanline_di(cpu)
                    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, no flags
            # 49CD..49E3: clear one row and advance to next row.
            _xor_al_al(cpu)
            cpu.s.cx = cpu.s.bp & 0xFFFF
            _rep_stosb(cpu, cpu.s.cx)
            _sub_reg16(cpu, 7, cpu.s.bp)
            _ega_next_scanline_di(cpu)
    cpu.s.cx = cpu.pop()

    # 49E4..4A38: copy/skip rows according to CS:5901 accumulator.
    while True:
        cpu.s.ax = mem.rw(cs, 0x5901)
        _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x58FD))
        if cpu.get_flag(ZF):
            copy_this_row = True
        else:
            _add_mem_word(cpu, cs, 0x5903, cpu.s.ax)
            cpu.s.ax = mem.rw(cs, 0x58FD)
            _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x5903))
            # JA 4A11: jump if AX > CS:5903, unsigned.
            if (not cpu.get_flag(CF)) and (not cpu.get_flag(ZF)):
                _sub_mem_word(cpu, cs, 0x5903, cpu.s.ax)
                copy_this_row = True
            else:
                _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
                if cpu.get_flag(ZF):
                    _add_reg16(cpu, 6, cpu.s.bp)
                else:
                    _sub_reg16(cpu, 6, cpu.s.bp)
                cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP 49E4, no flags
                if cpu.s.cx != 0:
                    continue
                break

        # 4A16..4A38: copy one BP-byte row, advance planar DI, optionally step SI back.
        cpu.push(cpu.s.cx)
        cpu.s.cx = cpu.s.bp & 0xFFFF
        _rep_movsb(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, cpu.s.bp)
        _ega_next_scanline_di(cpu)
        _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
        if not cpu.get_flag(ZF):
            _sub_reg16(cpu, 6, cpu.s.bp)
            _sub_reg16(cpu, 6, cpu.s.bp)
        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP 49E4, no flags
        if cpu.s.cx != 0:
            continue
        break

    # 4A3A..4A40: final clear row and RET.
    _xor_al_al(cpu)
    cpu.s.cx = cpu.s.bp & 0xFFFF
    _rep_stosb(cpu, cpu.s.cx)
    cpu.s.ip = cpu.pop()

@registry.replace(0x1010, 0x41DA, "overkill_linear_rows_to_work_buffer_41da")
def overkill_linear_rows_to_work_buffer_41da(cpu):
    """Replace 1010:41DA row-copy routine selected by the 5A5A table.

    Direct transliteration of 41DA..41F4.  The current captured startup call has
    both header words zero, which is exactly the kind of 8086 edge case that is
    slow in the interpreter: LOOP with CX=0000 performs 65,536 iterations.  The
    hook preserves that behavior instead of treating zero as zero iterations.
    """
    cs = cpu.s.cs & 0xFFFF
    cpu.s.es = cpu.mem.rw(cs, 0x9598)
    # LODSW; MOV CX,AX
    cpu.s.ax = cpu.mem.rw(cpu.s.ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    cpu.s.cx = cpu.s.ax & 0xFFFF
    # LODSW; SHL AX,1; MOV BP,AX
    cpu.s.ax = cpu.mem.rw(cpu.s.ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.bp = cpu.s.ax & 0xFFFF

    # LOOP executes 65,536 times when the input count word is zero.
    iterations = cpu.s.cx if cpu.s.cx != 0 else 0x10000

    if cpu.s.bp != 0 and iterations * (cpu.s.bp & 0xFFFF) > 10_000_000:
        raise RuntimeError(
            f"suspicious 41DA row copy header: rows={iterations} width_bytes={cpu.s.bp:04X} "
            f"DS:SI={cpu.s.ds:04X}:{(cpu.s.si - 4) & 0xFFFF:04X} DI={cpu.s.di:04X}"
        )

    if cpu.s.bp == 0:
        # Hot startup edge case: zero-width rows.  The original still performs
        # every LOOP iteration, but each row only does SUB DI,0 and ADD DI,50h.
        # Collapse it while preserving the final ADD flags from the last row.
        start_di = cpu.s.di & 0xFFFF
        if iterations:
            last_old_di = (start_di + (0x50 * (iterations - 1))) & 0xFFFF
            final_di_full = last_old_di + 0x50
            cpu.s.di = final_di_full & 0xFFFF
            cpu.set_add_flags(last_old_di, 0x50, final_di_full, 16)
            # The collapsed loop still has one observable memory side-effect:
            # PUSH CX writes to SS:SP-2 every row and POP restores SP.  The
            # last iteration always pushes 0001h before LOOP consumes it.
            cpu.mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, 0x0001)
        cpu.s.cx = 0
        cpu.s.ip = cpu.pop()
        return

    for _ in range(iterations):
        cpu.push(cpu.s.cx)
        cpu.s.cx = cpu.s.bp & 0xFFFF
        _rep_movsb(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, cpu.s.bp)
        _add_reg16(cpu, 7, 0x0050)
        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, no flags
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x477E, "overkill_sprite_blit_9x16_477e")
def overkill_sprite_blit_9x16_477e(cpu):
    """Replace the fully-unrolled fixed-geometry sprite blit at 1010:477E.

    Evidence: profiling the asset-heavy loading path shows this is the single
    dominant routine (hundreds of thousands of interpreted MOVSW per load,
    clustered around 1010:477E..480D and reached from the 5A36/4740 table
    dispatcher).  The original code is straight-line, not a loop: it copies a
    fixed 9-byte-wide by 16-row sprite from DS:SI into a packed ES:DI buffer.
    Disassembly of 477E..480D:

        477E  mov es, cs:[9596]          ; dest segment
        4783  mov ds, cs:[9598]          ; source segment
        per row (x16):
            movsw; movsw; movsw; movsw; movsb   ; copy 9 bytes, SI+=9, DI+=9
            add si, 002Bh                       ; skip 43 -> source row stride 52
        4808  mov ds, cs:[9596]          ; restore DS = dest segment
        480D  ret near

    Side effects preserved exactly (verified against interpreted ASM on
    artifacts/snapshot_stop_477e_probe, exit state SI+=0x340, DI+=0x90,
    DS=ES=cs:[9596], FLAGS=0212):
      * ES = cs:[9596], DS = cs:[9596] on exit
      * SI += 16*0x34 = 0x340, DI += 16*0x09 = 0x90
      * 144 bytes copied (16 rows x 9 bytes), source stride 52, dest packed
      * FLAGS = result of the final `add si,0x2B` (the only flag-affecting op;
        MOVS leaves FLAGS untouched)
      * near RET to the caller

    MOVS honours DF; the unrolled body only ever runs forward (DF=0) in the
    captured oracle.  DF=1 takes a faithful per-instruction fallback so the hook
    can never silently diverge from the original word/byte ordering.  Source and
    destination always live in distinct segments (e.g. 35FF vs 25CC), so the
    forward slice copy can never alias the destination it is reading from.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    es_seg = mem.rw(cs, 0x9596)   # 477E: mov es, cs:[9596]
    ds_seg = mem.rw(cs, 0x9598)   # 4783: mov ds, cs:[9598]
    cpu.s.es = es_seg
    cpu.s.ds = ds_seg

    si = cpu.s.si & 0xFFFF
    di = cpu.s.di & 0xFFFF
    data = mem.data
    mlen = len(data)
    old_si = si

    if not cpu.get_flag(DF):
        for _row in range(16):
            # movsw x4 + movsb == 9 forward byte copies; SI+=9, DI+=9.
            if si + 9 <= 0x10000 and di + 9 <= 0x10000:
                src = ((ds_seg << 4) + si) & 0xFFFFF
                dst = ((es_seg << 4) + di) & 0xFFFFF
                if src + 9 <= mlen and dst + 9 <= mlen:
                    data[dst:dst + 9] = data[src:src + 9]
                    si = (si + 9) & 0xFFFF
                    di = (di + 9) & 0xFFFF
                else:  # physical-edge wrap: stay byte-exact
                    for _ in range(9):
                        mem.wb(es_seg, di, mem.rb(ds_seg, si))
                        si = (si + 1) & 0xFFFF
                        di = (di + 1) & 0xFFFF
            else:  # 16-bit offset wrap inside the row: stay byte-exact
                for _ in range(9):
                    mem.wb(es_seg, di, mem.rb(ds_seg, si))
                    si = (si + 1) & 0xFFFF
                    di = (di + 1) & 0xFFFF
            old_si = si
            si = (si + 0x2B) & 0xFFFF   # add si,002Bh
    else:
        # DF=1 fallback: reproduce the exact MOVSW/MOVSB word/byte ordering.
        for _row in range(16):
            for _ in range(4):  # movsw x4
                mem.ww(es_seg, di, mem.rw(ds_seg, si))
                si = (si - 2) & 0xFFFF
                di = (di - 2) & 0xFFFF
            mem.wb(es_seg, di, mem.rb(ds_seg, si))  # movsb
            si = (si - 1) & 0xFFFF
            di = (di - 1) & 0xFFFF
            old_si = si
            si = (si + 0x2B) & 0xFFFF   # add si,002Bh (unaffected by DF)

    cpu.set_add_flags(old_si, 0x2B, old_si + 0x2B, 16)
    cpu.s.si = si
    cpu.s.di = di
    cpu.s.ds = es_seg   # 4808: mov ds, cs:[9596]
    cpu.s.ip = cpu.pop()  # 480D: ret near


@registry.replace(0x1010, 0x38B7, "overkill_masked_sprite_composite_38b7")
def overkill_masked_sprite_composite_38b7(cpu):
    """Replace the masked 2-column sprite-composite loop at 1010:38B7..38CF.

    Profiling after the 477E lift showed this is the hottest remaining
    interpreted routine during sprite-heavy frames.  It is a tight LOOP that
    composites a sprite over the destination with the classic AND-mask / OR-data
    operation, two 16-bit columns per row:

        38B7  lodsw                ; mask = DS:[SI], SI += 2
        38B8  and ax, es:[di]      ; AX = mask AND dest word (keep background)
        38BB  or  ax, ds:[si]      ; AX |= data word = DS:[SI] (paint sprite)
        38BD  add si, 2            ; step past the data word
        38C0  stosw                ; ES:[DI] = AX, DI += 2
        38C1..38CA  (identical second column)
        38CB  add di, 0030h        ; next visible row (net DI stride 0034h)
        38CE  loop 38B7            ; CX rows (CX==0 -> 65536, 8086 rule)
        38D0  (fall-through)

    Per row the source is [mask0, data0, mask1, data1] so SI advances 8; the
    destination advances 0034h (two words written + 30h).  The destination is a
    read-modify-write (the AND reads ES:[DI] before STOSW overwrites it).  Only
    the final `add di,0030h` leaves live FLAGS; AX holds the last composited
    word; CX exits 0; control falls through to 38D0.  LODSW/STOSW honour DF; the
    immediate `add si,2`/`add di,30h` do not.  Verified bit-identical to the
    interpreted loop over 2000 randomised states.
    """
    s = cpu.s
    mem = cpu.mem
    df = cpu.get_flag(DF)
    rows = s.cx if s.cx != 0 else 0x10000
    es = s.es & 0xFFFF
    ds = s.ds & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    sd = -2 if df else 2
    old_di = di
    for _ in range(rows):
        for _col in range(2):
            mask = mem.rw(ds, si)            # lodsw
            si = (si + sd) & 0xFFFF
            ax = mask & mem.rw(es, di)       # and ax, es:[di]
            ax = ax | mem.rw(ds, si)         # or  ax, ds:[si]
            si = (si + 2) & 0xFFFF           # add si, 2
            mem.ww(es, di, ax)               # stosw
            di = (di + sd) & 0xFFFF
        old_di = di
        di = (di + 0x30) & 0xFFFF            # add di, 0030h
    cpu.set_add_flags(old_di, 0x30, old_di + 0x30, 16)
    s.si = si
    s.di = di
    s.ax = ax
    s.cx = 0
    s.ip = 0x38D0                            # fall through past LOOP



@registry.replace(0x1010, 0x3849, "overkill_masked_sprite_composite_3849")
def overkill_masked_sprite_composite_3849(cpu):
    """Replace the 4-column masked sprite composite loop at 1010:3849.

    This is the wider sibling of the verified 38B7 hook.  Each row composites
    four destination words using source pairs [mask,data] and then advances the
    destination by 0x2C, for a net visible stride of 0x34 bytes.  The helper
    finally restores DS from CS:[9596] and returns near.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -2 if cpu.get_flag(DF) else 2
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        for _col in range(4):
            mask = mem.rw(ds, si)
            si = (si + sd) & 0xFFFF
            ax = mask & mem.rw(es, di)
            ax = ax | mem.rw(ds, si)
            si = (si + 2) & 0xFFFF
            mem.ww(es, di, ax)
            di = (di + sd) & 0xFFFF
        old_di = di
        di = (di + 0x2C) & 0xFFFF

    cpu.set_add_flags(old_di, 0x2C, old_di + 0x2C, 16)
    s.ax = ax
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x1AEB, "overkill_ega_spaced_word_composite_1aeb")
def overkill_ega_spaced_word_composite_1aeb(cpu):
    """Replace the hot EGA spaced-word composite loop at 1010:1AEB.

    Each row updates four words separated by 1Ah bytes in ES.  Source words are
    laid out as one mask word followed by four data words.  The original
    restores DS from CS:[9596] and returns near after the loop.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    old_si = si

    for _ in range(rows):
        row_si = si
        mask = mem.rw(ds, row_si)
        for data_off in (2, 4, 6, 8):
            ax = (mem.rw(es, di) & mask) | mem.rw(ds, (row_si + data_off) & 0xFFFF)
            mem.ww(es, di, ax)
            di = (di + 0x1A) & 0xFFFF
        old_si = si
        si = (si + 0x0A) & 0xFFFF

    cpu.set_add_flags(old_si, 0x0A, old_si + 0x0A, 16)
    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x1D1B, "overkill_ega_spread_masked_composite_1d1b")
def overkill_ega_spread_masked_composite_1d1b(cpu):
    """Replace the hot EGA bit-spread masked composite loop at 1010:1D1B.

    This is the sibling of the 1AEB jump-table sprite variant (both are reached
    through the ``jmp cs:[bx]`` dispatcher at 1010:76E2 and return near to the
    object-scan caller after restoring DS from CS:[9596]).  Per row it writes
    four 3-byte chunks (a word at DI plus a byte at DI+2) spaced 1Ah bytes apart,
    advancing DI by 68h between rows.

    The source layout is one mask word followed by four data words (SI += 0Ah per
    row).  Unlike 1AEB, each word is first spread through the original RCR/SHR bit
    chains before it is combined with the destination:

      * mask word: ``DL=FF`` then 4x {STC; RCR AL; RCR AH; RCR DL}; the resulting
        AX (word) and DL (byte) are AND-ed into all four chunks of the row,
        clearing the pixels the sprite will overwrite;
      * each of the four data words: ``DL=0`` then 4x {SHR AL; RCR AH; RCR DL};
        the resulting AX/DL are OR-ed into that chunk, painting the pixels.

    The chains are replicated exactly (same primitives, same order) so registers,
    flags and written memory match the interpreted ASM; only the per-instruction
    fetch/decode/dispatch overhead is removed.  Verified bit-identical at runtime
    by the differential hook verifier (see ``DEFAULT_STOPS`` 1D1B near_ret) and by
    ``test_ega_spread_masked_composite_1d1b_hook_matches_interpreted_asm``.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF

    rw, ww, rb, wb = mem.rw, mem.ww, mem.rb, mem.wb

    ax = s.ax & 0xFFFF
    dl = 0
    old_di = di
    # Destination chunk offsets within a row: word at +k, byte at +k+2.
    chunk = (0x00, 0x1A, 0x34, 0x4E)

    for _ in range(rows):
        # Mask word: STC-seeded RCR chain, then AND into all four chunks.
        al = rw(ds, si) & 0xFF
        ah = (rw(ds, si) >> 8) & 0xFF
        si = (si + 2) & 0xFFFF
        dl = 0xFF
        for _ in range(4):
            cf = 1
            nal = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = nal
            nah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = nah
            ndl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = ndl
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mask_dl = dl
        for k in chunk:
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) & mask_ax)
            wb(es, (di + k + 2) & 0xFFFF, rb(es, (di + k + 2) & 0xFFFF) & mask_dl)

        # Four data words: SHR-seeded RCR chain, then OR into the matching chunk.
        for k in chunk:
            al = rw(ds, si) & 0xFF
            ah = (rw(ds, si) >> 8) & 0xFF
            si = (si + 2) & 0xFFFF
            dl = 0
            for _ in range(4):
                cf = al & 1; al = (al >> 1) & 0xFF
                nah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = nah
                ndl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = ndl
            ax = ((ah << 8) | al) & 0xFFFF
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) | ax)
            wb(es, (di + k + 2) & 0xFFFF, rb(es, (di + k + 2) & 0xFFFF) | dl)

        old_di = di
        di = (di + 0x68) & 0xFFFF

    # Live flags at the near return come from the final ADD DI,68h.
    cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)
    s.ax = ax & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x13E7, "overkill_ega_spread_masked_composite_wide_13e7")
def overkill_ega_spread_masked_composite_wide_13e7(cpu):
    """Replace the hot wide EGA bit-spread masked composite loop at 1010:13E7.

    This is the five-byte-wide sibling of the 1D1B variant: another target of the
    ``jmp cs:[bx]`` sprite dispatcher (here at 1010:7620) that returns near to the
    object-scan caller after restoring DS from CS:[9596].  Where 1D1B writes a
    word+byte (3-byte) chunk, 1D1B's wide sibling writes a word+word+byte (5-byte)
    chunk: a word at DI, a word at DI+2, and a byte at DI+4.  Four chunks per row
    are spaced 1Ah bytes apart (DI += 68h between rows).

    Per row the source is read with explicit ``MOV r,DS:[SI+disp]`` (not LODSW), as
    one mask pair followed by four data pairs, so SI advances by 14h per row:

      * mask: AX=[SI], BX=[SI+2], ``DL=FF`` then 4x {STC; RCR AL; RCR AH; RCR BL;
        RCR BH; RCR DL}; AX/BX/DL are AND-ed into all four chunks of the row;
      * data k (k=0..3): AX=[SI+4+4k], BX=[SI+6+4k], ``DL=0`` then 4x {SHR AL;
        RCR AH; RCR BL; RCR BH; RCR DL}; AX/BX/DL are OR-ed into chunk k.

    The RCR/SHR chains are replicated exactly (same primitives/order over the
    AL/AH/BL/BH/DL register chain) so registers, flags and written memory match the
    interpreted ASM; only the per-instruction fetch/decode/dispatch overhead is
    removed.  The live flags at the near return come from the final ``ADD SI,14h``
    (textually the last arithmetic before LOOP).  Verified bit-identical by the
    differential hook verifier (``DEFAULT_STOPS`` 13E7 near_ret) and by
    ``test_ega_spread_masked_composite_wide_13e7_hook_matches_interpreted_asm``.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF

    rw, ww, rb, wb = mem.rw, mem.ww, mem.rb, mem.wb

    ax = s.ax & 0xFFFF
    bx = s.bx & 0xFFFF
    dl = 0
    old_si = si
    # Destination chunk offsets within a row: word at +k, word at +k+2, byte +k+4.
    chunk = (0x00, 0x1A, 0x34, 0x4E)

    for _ in range(rows):
        # Mask pair: STC-seeded RCR chain over AL/AH/BL/BH/DL, AND into all chunks.
        word = rw(ds, si)
        al = word & 0xFF; ah = (word >> 8) & 0xFF
        word = rw(ds, (si + 2) & 0xFFFF)
        bl = word & 0xFF; bh = (word >> 8) & 0xFF
        dl = 0xFF
        for _ in range(4):
            cf = 1
            n = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = n
            n = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = n
            n = ((cf << 7) | (bl >> 1)) & 0xFF; cf = bl & 1; bl = n
            n = ((cf << 7) | (bh >> 1)) & 0xFF; cf = bh & 1; bh = n
            n = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = n
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_dl = dl
        for k in chunk:
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) & mask_ax)
            ww(es, (di + k + 2) & 0xFFFF, rw(es, (di + k + 2) & 0xFFFF) & mask_bx)
            wb(es, (di + k + 4) & 0xFFFF, rb(es, (di + k + 4) & 0xFFFF) & mask_dl)

        # Four data pairs: SHR-seeded RCR chain, then OR into the matching chunk.
        for j, k in enumerate(chunk):
            so = 4 + j * 4
            word = rw(ds, (si + so) & 0xFFFF)
            al = word & 0xFF; ah = (word >> 8) & 0xFF
            word = rw(ds, (si + so + 2) & 0xFFFF)
            bl = word & 0xFF; bh = (word >> 8) & 0xFF
            dl = 0
            for _ in range(4):
                cf = al & 1; al = (al >> 1) & 0xFF
                n = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = n
                n = ((cf << 7) | (bl >> 1)) & 0xFF; cf = bl & 1; bl = n
                n = ((cf << 7) | (bh >> 1)) & 0xFF; cf = bh & 1; bh = n
                n = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = n
            ax = ((ah << 8) | al) & 0xFFFF
            bx = ((bh << 8) | bl) & 0xFFFF
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) | ax)
            ww(es, (di + k + 2) & 0xFFFF, rw(es, (di + k + 2) & 0xFFFF) | bx)
            wb(es, (di + k + 4) & 0xFFFF, rb(es, (di + k + 4) & 0xFFFF) | dl)

        di = (di + 0x68) & 0xFFFF
        old_si = si
        si = (si + 0x14) & 0xFFFF

    # Live flags at the near return come from the final ADD SI,14h.
    cpu.set_add_flags(old_si, 0x14, old_si + 0x14, 16)
    s.ax = ax & 0xFFFF
    s.bx = bx & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x29C6, "overkill_ega_spaced_copy_29c6")
def overkill_ega_spaced_copy_29c6(cpu):
    """Replace the hot EGA 16-row spaced copy routine at 1010:29C6.

    If DI is FFFFh the original returns immediately.  Otherwise it copies four
    3-byte chunks per row for 16 rows, spacing destination chunks by 1Ah bytes.
    """
    s = cpu.s
    mem = cpu.mem
    _cmp_word(cpu, s.di & 0xFFFF, 0xFFFF)
    if (s.di & 0xFFFF) == 0xFFFF:
        s.ip = cpu.pop()
        return

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    s.bx = 0x0017
    old_di = di

    for _row in range(16):
        for _col in range(4):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + 2) & 0xFFFF
            di = (di + 2) & 0xFFFF
            mem.wb(es, di, mem.rb(ds, si))
            si = (si + 1) & 0xFFFF
            di = (di + 1) & 0xFFFF
            old_di = di
            di = (di + 0x0017) & 0xFFFF

    cpu.set_add_flags(old_di, 0x0017, old_di + 0x0017, 16)
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x2AB9, "overkill_ega_source_spaced_copy_2ab9")
def overkill_ega_source_spaced_copy_2ab9(cpu):
    """Replace EGA object draw copy routine at 1010:2AB9.

    The original calls the mode-specific 5A36 row-address helper, then copies
    four 3-byte chunks per row for 16 rows, spacing source chunks by 1Ah bytes.
    """
    s = cpu.s
    mem = cpu.mem
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    cs = s.cs & 0xFFFF

    _call_hook_like_near_call(cpu, _object_row_addr_mode1_2580, 0x2ABC)
    if s.ip != 0x2ABC:
        return
    # The near-call push already left 0x2ABC in the scratch slot below SP, so the
    # stack image matches a real CALL/RET without an extra fixup write here.

    mem.ww(ss, (bp + 0x0C) & 0xFFFF, s.ax)
    _cmp_word(cpu, s.ax, 0xFFFF)
    if (s.ax & 0xFFFF) == 0xFFFF:
        s.ip = cpu.pop()
        return

    _add_reg16(cpu, 0, mem.rw(s.ds & 0xFFFF, 0x234C))
    mem.ww(ss, (bp + 0x0C) & 0xFFFF, s.ax)
    s.si = s.ax & 0xFFFF
    s.di = mem.rw(ss, (bp + 0x0E) & 0xFFFF)
    s.es = mem.rw(cs, 0x9596)
    s.ds = mem.rw(cs, 0x9598)
    s.bx = 0x0017

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    old_si = si

    for _row in range(16):
        for _col in range(4):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + 2) & 0xFFFF
            di = (di + 2) & 0xFFFF
            mem.wb(es, di, mem.rb(ds, si))
            si = (si + 1) & 0xFFFF
            di = (di + 1) & 0xFFFF
            old_si = si
            si = (si + 0x0017) & 0xFFFF

    cpu.set_add_flags(old_si, 0x0017, old_si + 0x0017, 16)
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(cs, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x469F, "overkill_sprite_copy_9x16_469f")
def overkill_sprite_copy_9x16_469f(cpu):
    """Replace the hot 9-byte-wide by 16-row plain sprite copy at 1010:469F."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    old_di = di

    if not cpu.get_flag(DF):
        data = mem.data
        src_base = ds << 4
        dst_base = es << 4
        for _ in range(16):
            data[((dst_base + di) & 0xFFFFF):((dst_base + di) & 0xFFFFF) + 9] =                 data[((src_base + si) & 0xFFFFF):((src_base + si) & 0xFFFFF) + 9]
            si = (si + 9) & 0xFFFF
            old_di = (di + 9) & 0xFFFF
            di = (old_di + 0x2B) & 0xFFFF
    else:
        for _ in range(16):
            for _word in range(4):
                mem.ww(es, di, mem.rw(ds, si))
                si = (si - 2) & 0xFFFF
                di = (di - 2) & 0xFFFF
            mem.wb(es, di, mem.rb(ds, si))
            si = (si - 1) & 0xFFFF
            di = (di - 1) & 0xFFFF
            old_di = di
            di = (di + 0x2B) & 0xFFFF

    cpu.set_add_flags(old_di, 0x2B, old_di + 0x2B, 16)
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = cpu.pop()

@registry.replace(0x1010, 0x4D15, "overkill_presence_stamp_list_4d15")
def overkill_presence_stamp_list_4d15(cpu):
    """Replace the hot 1010:4D15 presence/stamp list helper.

    The caller feeds a compact list of triples.  Each iteration maps the first
    word through DS:[9A08 + word*2], adds DS:[234C] and the second word to get
    an ES-relative cell address, then uses the low byte of the third word as a
    marker.  Empty cells are stamped into ES and the cell address is appended to
    DS:DI; occupied cells are skipped.  In mode 1 it checks/stamps a small stack
    of vertically separated cells at +1Ah/+34h/+4Eh; BP selects whether the +4Eh
    layer is included.

    This screen is especially expensive when the live player disables the older
    interactive-risk render hooks: the planet/difficulty screen executes this
    loop tens of thousands of times.  Keep the loop in Python locals and only set
    FLAGS for the final original instruction that can survive the LOOP/RET.
    """
    s = cpu.s
    count = s.cx & 0xFFFF
    if count == 0:
        count = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    ds_base = ds << 4
    es_base = es << 4
    cs_base = cs << 4
    data = cpu.mem.data
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    delta = -2 if cpu.get_flag(DF) else 2
    table_base = 0x9A08
    scroll_base = data[((ds_base + 0x234C) & 0xFFFFF)] | (data[((ds_base + 0x234D) & 0xFFFFF)] << 8)
    mode = data[((cs_base + 0x95BC) & 0xFFFFF)] | (data[((cs_base + 0x95BD) & 0xFFFFF)] << 8)
    bx = s.bx & 0xFFFF
    ax = s.ax & 0xFFFF
    last_flag_kind = "none"
    last_flag_a = 0
    last_flag_b = 0
    last_flag_result = 0
    last_flag_bits = 8

    def read_word(seg_base: int, off: int) -> int:
        a = (seg_base + (off & 0xFFFF)) & 0xFFFFF
        if a == 0xFFFFF:
            return data[a] | (data[0] << 8)
        return data[a] | (data[a + 1] << 8)

    def write_word(seg_base: int, off: int, value: int) -> None:
        # DS:DI never targets EGA planar memory on this path, so direct writes are
        # safe and avoid the Memory.ww helper overhead inside the hot loop.
        a = (seg_base + (off & 0xFFFF)) & 0xFFFFF
        data[a] = value & 0xFF
        if a == 0xFFFFF:
            data[0] = (value >> 8) & 0xFF
        else:
            data[a + 1] = (value >> 8) & 0xFF

    def write_byte(seg_base: int, off: int, value: int) -> None:
        # ES is the presence/cell buffer in this routine, not the EGA A000h
        # aperture, so direct byte writes match Memory.wb without planar routing.
        data[(seg_base + (off & 0xFFFF)) & 0xFFFFF] = value & 0xFF

    for _ in range(count):
        # LODSW #1: compact table index.
        ax = read_word(ds_base, si)
        si = (si + delta) & 0xFFFF
        bx = ((ax << 1) + table_base) & 0xFFFF
        bx = read_word(ds_base, bx)
        bx = (bx + scroll_base) & 0xFFFF

        # LODSW #2: cell-relative offset.
        ax = read_word(ds_base, si)
        si = (si + delta) & 0xFFFF
        bx = (bx + ax) & 0xFFFF

        # LODSW #3: marker byte in AL.
        ax = read_word(ds_base, si)
        si = (si + delta) & 0xFFFF
        marker = ax & 0xFF

        cell = data[(es_base + bx) & 0xFFFFF]
        if cell != 0:
            last_flag_kind = "sub"
            last_flag_a = cell
            last_flag_b = 0
            last_flag_result = cell
            last_flag_bits = 8
            s.cx = (s.cx - 1) & 0xFFFF
            continue

        should_store = False
        store_1a = False
        store_34 = False
        store_4e = False
        if mode != 1:
            # JNE 4D59: non-mode-1 callers only stamp the base cell and append
            # the address to DS:DI.  The stacked +1A/+34/+4E stores are reached
            # only through the mode-1 JMP BP path.
            should_store = True
        else:
            blocked = False
            for off in (0x1A, 0x34, 0x4E):
                value = data[(es_base + ((bx + off) & 0xFFFF)) & 0xFFFFF]
                if value != 0:
                    last_flag_kind = "sub"
                    last_flag_a = value
                    last_flag_b = 0
                    last_flag_result = value
                    last_flag_bits = 8
                    blocked = True
                    break
            if not blocked:
                if bp not in (0x4D4D, 0x4D51):
                    s.ax = ax
                    s.bx = bx
                    s.si = si
                    s.di = di
                    s.ip = bp
                    return
                should_store = True
                store_1a = True
                store_34 = True
                store_4e = bp == 0x4D4D

        if should_store:
            if store_4e:
                write_byte(es_base, (bx + 0x4E) & 0xFFFF, marker)
            if store_34:
                write_byte(es_base, (bx + 0x34) & 0xFFFF, marker)
            if store_1a:
                write_byte(es_base, (bx + 0x1A) & 0xFFFF, marker)
            write_byte(es_base, bx, marker)
            write_word(ds_base, di, bx)
            old_di = di
            di = (di + 2) & 0xFFFF
            last_flag_kind = "add"
            last_flag_a = old_di
            last_flag_b = 2
            last_flag_result = old_di + 2
            last_flag_bits = 16

        s.cx = (s.cx - 1) & 0xFFFF

    s.ax = ax & 0xFFFF
    s.bx = bx & 0xFFFF
    s.si = si & 0xFFFF
    s.di = di & 0xFFFF
    s.cx = 0
    if last_flag_kind == "add":
        cpu.set_add_flags(last_flag_a, last_flag_b, last_flag_result, last_flag_bits)
    elif last_flag_kind == "sub":
        cpu.set_sub_flags(last_flag_a, last_flag_b, last_flag_result, last_flag_bits)
    s.ip = cpu.pop()


def _object_ptr_from_scan_index(cpu, table_base: int, cx_value: int) -> tuple[int, int]:
    """Return (BX, BP) for OVERKILL's descending object-list scan loops."""
    bx = ((cx_value & 0xFFFF) << 1) & 0xFFFF
    bp = cpu.mem.rw(cpu.s.ds & 0xFFFF, (table_base + bx) & 0xFFFF)
    cpu.s.bx = bx
    cpu.s.bp = bp
    return bx, bp


def _push_loop_count_for_interpreted_tail(cpu, cx_value: int) -> None:
    cpu.s.sp = (cpu.s.sp - 2) & 0xFFFF
    cpu.mem.ww(cpu.s.ss & 0xFFFF, cpu.s.sp, cx_value & 0xFFFF)


def _remember_balanced_push_scratch(cpu, cx_value: int) -> None:
    # PUSH/POP pairs leave the last pushed word below SP. Full-memory oracle
    # comparisons can see it even though SP is balanced afterwards.
    cpu.mem.ww(cpu.s.ss & 0xFFFF, (cpu.s.sp - 2) & 0xFFFF, cx_value & 0xFFFF)


def _scan_loop_until_callable(cpu, table_base: int, callable_ip: int, done_ip: int, should_call) -> None:
    """Collapse an object-list loop until the next entry that really calls out.

    The overlaid loading/rendering code has several loops of the form::

        push cx
        mov  bx,cx
        shl  bx,1
        mov  bp,[table+bx]
        ... tests against SS:[BP+...] ...
        call helper      ; only for active/matching objects
        pop  cx
        loop top

    Most startup iterations only skip inactive objects.  This helper consumes
    those skip-only iterations in Python and stops immediately before the real
    CALL for the first object that needs original helper logic.
    """
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, table_base, cx_value)
        if should_call():
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = callable_ip & 0xFFFF
            return

        _remember_balanced_push_scratch(cpu, cx_value)
        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = done_ip & 0xFFFF
            return

    cpu.s.ip = done_ip & 0xFFFF


def _scan_active_object_call(cpu, table_base: int, callable_ip: int, done_ip: int) -> None:
    ss = cpu.s.ss & 0xFFFF

    def should_call() -> bool:
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        return active != 0

    _scan_loop_until_callable(cpu, table_base, callable_ip, done_ip, should_call)


def _scan_layered_object_call(cpu, wanted_layer: int, callable_ip: int, done_ip: int) -> None:
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF

    def should_call() -> bool:
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active == 0:
            return False

        mode = cpu.mem.rw(ds, 0xBDAC)
        _cmp_word(cpu, mode, 1)
        use_layer_test = False
        if mode != 1:
            camera = cpu.mem.rw(ds, 0x2350)
            _cmp_word(cpu, camera, 0x00B6)
            if camera <= 0x00B6:  # original JA falls through to layer test only when false
                layer = cpu.mem.rw(ss, (cpu.s.bp + 0x16) & 0xFFFF)
                _cmp_word(cpu, layer, 1)
                if layer == 1:
                    return False
                use_layer_test = True

        obj_layer = cpu.mem.rw(ss, (cpu.s.bp + 0x0A) & 0xFFFF)
        _cmp_word(cpu, obj_layer, wanted_layer)
        return obj_layer == wanted_layer

    _scan_loop_until_callable(cpu, 0x32CA, callable_ip, done_ip, should_call)


@registry.replace(0x1010, 0xA849, "overkill_scan_objects_call_5ac8_a849")
def overkill_scan_objects_call_5ac8_a849(cpu):
    """Skip inactive entries in the overlaid 32CA object scan before CALL 5AC8."""
    _scan_active_object_call(cpu, 0x32CA, 0xA858, 0xA85E)


@registry.replace(0x1010, 0xA861, "overkill_scan_objects_call_5ac8_a861")
def overkill_scan_objects_call_5ac8_a861(cpu):
    """Skip inactive entries in the overlaid 8D12 object scan before CALL 5AC8."""
    _scan_active_object_call(cpu, 0x8D12, 0xA870, 0xA876)


@registry.replace(0x1010, 0xA87C, "overkill_scan_objects_call_7746_a87c")
def overkill_scan_objects_call_7746_a87c(cpu):
    """Skip inactive entries in the overlaid 8D12 object scan before CALL 7746."""
    _scan_active_object_call(cpu, 0x8D12, 0xA88B, 0xA891)


@registry.replace(0x1010, 0xA894, "overkill_scan_layer0_draw_a894")
def overkill_scan_layer0_draw_a894(cpu):
    """Skip non-drawing entries in the overlaid layer-0 draw scan before CALL 7596."""
    _scan_layered_object_call(cpu, 0, 0xA8BE, 0xA8C4)


@registry.replace(0x1010, 0xA8C7, "overkill_scan_layer1_draw_a8c7")
def overkill_scan_layer1_draw_a8c7(cpu):
    """Skip non-drawing entries in the overlaid layer-1 draw scan before CALL 7596."""
    _scan_layered_object_call(cpu, 1, 0xA8F1, 0xA8F7)


@registry.replace(0x1010, 0xA90F, "overkill_scan_objects_call_5a92_a90f")
def overkill_scan_objects_call_5a92_a90f(cpu):
    """Skip inactive entries in the overlaid 8D12 object scan before CALL 5A92."""
    _scan_active_object_call(cpu, 0x8D12, 0xA91E, 0xA924)


@registry.replace(0x1010, 0xA927, "overkill_scan_objects_call_5a92_a927")
def overkill_scan_objects_call_5a92_a927(cpu):
    """Skip inactive entries in the overlaid 32CA object scan before CALL 5A92."""
    _scan_active_object_call(cpu, 0x32CA, 0xA936, 0xA93C)


@registry.replace(0x1010, 0xA9E0, "overkill_scan_objects_call_aa2b_a9e0")
def overkill_scan_objects_call_aa2b_a9e0(cpu):
    """Skip inactive entries in the overlaid timed object scan before CALL AA2B."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF

    def should_call() -> bool:
        counter = (cpu.mem.rw(ds, 0x2340) + 1) & 0xFFFF
        cpu.mem.ww(ds, 0x2340, counter)
        if counter >= 0x05DC:
            cpu.mem.ww(ds, 0x2340, 0)
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        return active != 0

    _scan_loop_until_callable(cpu, 0x32CA, 0xAA01, 0xAA07, should_call)


@registry.replace(0x1010, 0xAA10, "overkill_scan_objects_call_aa2b_aa10")
def overkill_scan_objects_call_aa2b_aa10(cpu):
    """Skip inactive entries in the overlaid 8D12 object scan before CALL AA2B."""
    _scan_active_object_call(cpu, 0x8D12, 0xAA1F, 0xAA25)


@registry.replace(0x1010, 0x4D6F, "overkill_clear_presence_list_4d6f")
def overkill_clear_presence_list_4d6f(cpu):
    """Replace the hot list clear at 1010:4D6F.

    It walks up to CX word entries from DS:SI, stops on FFFF, and clears the
    corresponding occupancy byte(s) in ES.  Mode CS:[95BC] == 1 clears the
    stacked +1A/+34/+4E cells as well.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    si = s.si & 0xFFFF
    count = s.cx & 0xFFFF
    if count == 0:
        count = 0x10000
    step = -2 if cpu.get_flag(DF) else 2

    while count:
        ax = mem.rw(ds, si)
        si = (si + step) & 0xFFFF
        s.ax = ax
        _cmp_word(cpu, ax, 0xFFFF)
        if ax == 0xFFFF:
            s.si = si
            s.ip = cpu.pop()
            return

        s.di = ax & 0xFFFF
        mode = mem.rw(cs, 0x95BC)
        _cmp_word(cpu, mode, 1)
        if mode == 1:
            mem.wb(es, (s.di + 0x4E) & 0xFFFF, 0)
            mem.wb(es, (s.di + 0x34) & 0xFFFF, 0)
            mem.wb(es, (s.di + 0x1A) & 0xFFFF, 0)
        mem.wb(es, s.di, 0)
        s.cx = (s.cx - 1) & 0xFFFF
        count -= 1
        if s.cx == 0:
            s.si = si
            s.ip = cpu.pop()
            return

    s.si = si
    s.ip = cpu.pop()

@registry.replace(0x1010, 0x41A6, "overkill_variable_width_interlaced_blit_41a6")
def overkill_variable_width_interlaced_blit_41a6(cpu):
    """Replace the hot variable-width interlaced row blit at 1010:41A6.

    Entry state is set up by the immediately preceding interpreted code:

        ES = CS:[9598]
        CX = row count
        BP = source bytes per row (source width word * 2)
        DS:SI = source
        ES:DI = destination

    Original loop:

        push cx
        mov  cx,bp
        rep  movsb
        sub  di,bp
        add  di,2000h
        test di,4000h
        jz   +
        add  di,C050h
        pop  cx
        loop ...
        ret

    It is the same EGA/CGA interlaced-addressing family as the already lifted
    447B and 41DA routines, but with a variable row width.
    """
    rows = cpu.s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    while rows:
        # Preserve the PUSH/POP scratch write because some oracle tests compare
        # the full 1 MiB memory image, including the word below SP.
        cpu.push(cpu.s.cx)
        cpu.s.cx = cpu.s.bp & 0xFFFF
        _rep_movsb(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, cpu.s.bp)
        _add_reg16(cpu, 7, 0x2000)
        _test_word(cpu, cpu.s.di, 0x4000)
        if not cpu.get_flag(ZF):
            _add_reg16(cpu, 7, 0xC050)
        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unaffected.
        rows -= 1

    cpu.s.ip = cpu.pop()









@registry.replace(0x1010, 0x27EB, "overkill_ega_row_driver_27eb")
def overkill_ega_row_driver_27eb(cpu):
    if _self_disable_if_patched(cpu, 0x27EB, _SIG_27EB, "overkill_ega_row_driver_27eb"):
        return
    """Fuse the hot EGA mode-1 row driver at 1010:27EB.

    This is the interpreted outer loop that used to call the already-hooked
    helpers thousands of times during EGA startup/menu asset expansion:

        27EB  push cx                  ; remaining source rows
        27EC  cmp  cs:[0BD6],0
        27F4  push si / call 2932 ...  ; optional transparency-mask row
        2802  mov  cs:[5BA6],di
        2807  mov  di,5AF4h
        280A  mov  bp,0004h
        280D  ... temp-row load
        2824  ... temp expansion/copy, LOOP back to 27EB or JMP 27D9

    The narrow 280D/2824/2932 hooks are still the source of truth.  This driver
    removes the repeated interpreter dispatch and hook-boundary crossings around
    them without inventing new renderer semantics.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    while True:
        outer_cx = cpu.s.cx & 0xFFFF
        # 27EB PUSH CX.  The 2824 block consumes this with its final POP CX.
        cpu.push(outer_cx)

        _cmp_word(cpu, mem.rw(cs, 0x0BD6), 0)
        if not cpu.get_flag(ZF):
            # 27F4 PUSH SI; 27F5 MOV CX,CS:[5B9C]
            saved_si = cpu.s.si & 0xFFFF
            cpu.push(saved_si)
            width = mem.rw(cs, 0x5B9C)
            loop_count = width if width != 0 else 0x10000
            cpu.s.cx = width & 0xFFFF

            while loop_count:
                # 27FA PUSH CX; 27FB CALL 2932; 27FE POP CX; 27FF LOOP 27FA.
                cpu.push(cpu.s.cx)
                cpu.push(0x27FE)
                overkill_ega_transparency_mask_2932(cpu)
                cpu.s.cx = cpu.pop()
                cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
                loop_count -= 1

            cpu.s.si = cpu.pop()

        # 2802 MOV CS:[5BA6],DI; 2807 MOV DI,5AF4h; 280A MOV BP,4.
        mem.ww(cs, 0x5BA6, cpu.s.di & 0xFFFF)
        cpu.s.di = 0x5AF4
        cpu.s.bp = 0x0004

        overkill_ega_load_temp_rows_280d(cpu)
        overkill_ega_expand_temp_rows_2824(cpu)
        if cpu.s.ip != 0x27EB:
            return


@registry.replace(0x1010, 0x280D, "overkill_ega_load_temp_rows_280d")
def overkill_ega_load_temp_rows_280d(cpu):
    if _self_disable_if_patched(cpu, 0x280D, _SIG_280D, "overkill_ega_load_temp_rows_280d"):
        return
    """Replace the hot four-row temp loader at 1010:280D.

    The block copies four ``CS:5B9C``-byte rows from DS:SI into the temporary
    EGA row buffer starting at CS:5AF4, with a fixed 40-byte stride between
    rows.  It is the setup immediately before the 2824 expansion block.
    """
    cs = cpu.s.cs & 0xFFFF
    width = cpu.mem.rw(cs, 0x5B9C)
    if width == 0:
        width = 0x10000
    data = cpu.mem.data
    src_base = (cpu.s.ds & 0xFFFF) << 4
    dst_base = cs << 4
    di = cpu.s.di & 0xFFFF
    si = cpu.s.si & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    while bp != 0:
        # Final PUSH-less LOOP leaves flags from DEC BP / the last arithmetic
        # instruction that matters.  We still use the helper flag operations for
        # the row-step instructions so oracle tests can compare exact FLAGS.
        row_di = di
        for _ in range(width):
            cpu.set_reg8(0, data[(src_base + si) & 0xFFFFF])  # LODSB
            si = (si + 1) & 0xFFFF
            data[(dst_base + row_di) & 0xFFFFF] = cpu.get_reg8(0)
            row_di = (row_di + 1) & 0xFFFF
        cpu.s.di = row_di
        _sub_reg16(cpu, 7, width)
        _add_reg16(cpu, 7, 0x0028)
        di = cpu.s.di & 0xFFFF
        cpu.s.bp = bp
        _dec_reg16_preserve_cf(cpu, 5)
        bp = cpu.s.bp & 0xFFFF

    cpu.s.si = si
    cpu.s.cx = 0
    cpu.s.ip = 0x2824


@registry.replace(0x1010, 0x2824, "overkill_ega_expand_temp_rows_2824")
def overkill_ega_expand_temp_rows_2824(cpu):
    if _self_disable_if_patched(cpu, 0x2824, _SIG_2824, "overkill_ega_expand_temp_rows_2824"):
        return
    """Replace the hot EGA temp-row expansion/copy block at 1010:2824.

    This block converts four temporary 1bpp-ish rows at CS:5AF4/5B1C/5B44/5B6C
    into four EGA output-plane rows, applies OVERKILL's transparent-colour rule,
    then copies the four rows to the destination cursor tracked in CS:5BA6.  It
    is an internal block of the mode-1 renderer, not a subroutine: the hook ends
    at the same control-flow targets as the original ``LOOP/JMP`` tail
    (``27EB`` for another source row, ``27D9`` for the next object/list entry).

    The first lift mirrored the rotate/shift chain through ``CPU.shift``.  This
    version keeps the same byte/flag/stack results but performs the per-pixel
    plane packing as integer bit operations, which matters when the new 27EB
    driver fuses hundreds of rows into one hook call.
    """
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    es = cpu.s.es & 0xFFFF
    mem = cpu.mem
    data = mem.data
    cs_base = cs << 4
    es_base = es << 4
    width_word = mem.rw(cs, 0x5B9C)
    width = width_word if width_word != 0 else 0x10000

    di = 0x5AF4
    transparent_enabled = mem.rw(cs, 0x0BD6) != 0
    transparent_colour = mem.rb(cs, 0x0000) & 0xFF
    marker_enabled = mem.rb(cs, 0xC5B0) == 1
    marker_base = mem.rw(cs, 0x5BAA)
    marker_add = mem.rw(cs, 0x5BA8)

    for col in range(width):
        # Final column PUSH CX scratch.  The column loop's push/pop pair leaves
        # the last pushed count in the word below SP.
        mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, (width - col) & 0xFFFF)

        al = data[(cs_base + di) & 0xFFFFF]
        ah = data[(cs_base + ((di + 0x28) & 0xFFFF)) & 0xFFFFF]
        dl = data[(cs_base + ((di + 0x50) & 0xFFFF)) & 0xFFFFF]
        dh = data[(cs_base + ((di + 0x78) & 0xFFFF)) & 0xFFFFF]
        p0 = mem.rb(cs, 0x5BA2)
        p1 = mem.rb(cs, 0x5BA3)
        p2 = mem.rb(cs, 0x5BA4)
        p3 = mem.rb(cs, 0x5BA5)
        bl = cpu.get_reg8(3)
        final_rcl_value = p3

        for _ in range(8):
            # ROL DH/DL/AH/AL + RCL BL gathers one 4-bit pixel.  The carry
            # emitted by RCL BL is overwritten by the next ROL, so only the
            # incoming plane bit matters for the low nibble that survives AND.
            bit = (dh >> 7) & 1; dh = ((dh << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bit = (dl >> 7) & 1; dl = ((dl << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bit = (ah >> 7) & 1; ah = ((ah << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bit = (al >> 7) & 1; al = ((al << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bl &= 0x0F

            if transparent_enabled and bl == transparent_colour:
                bl = 0

            if marker_enabled:
                cpu.s.bp = marker_base
                if cpu.s.bp != 0xFFFF:
                    cpu.s.bp = (cpu.s.bp + marker_add) & 0xFFFF
                    marker = mem.rb(ss, cpu.s.bp)
                    # The ASM branches are slightly counter-intuitive here:
                    # marker == 1 enters the 06h/0Ch swap block, while
                    # marker == 2 (and all other values) skip it.
                    if marker == 1:
                        if bl == 0x06:
                            bl = 0x0C
                        elif bl == 0x0C:
                            bl = 0x06

            cf = bl & 1; bl >>= 1
            old = p0; p0 = ((p0 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            cf = bl & 1; bl >>= 1
            old = p1; p1 = ((p1 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            cf = bl & 1; bl >>= 1
            old = p2; p2 = ((p2 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            cf = bl & 1; bl >>= 1
            old = p3; p3 = ((p3 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            final_rcl_value = p3

        data[(cs_base + di) & 0xFFFFF] = p0
        data[(cs_base + ((di + 0x28) & 0xFFFF)) & 0xFFFFF] = p1
        data[(cs_base + ((di + 0x50) & 0xFFFF)) & 0xFFFFF] = p2
        data[(cs_base + ((di + 0x78) & 0xFFFF)) & 0xFFFFF] = p3
        mem.wb(cs, 0x5BA2, p0)
        mem.wb(cs, 0x5BA3, p1)
        mem.wb(cs, 0x5BA4, p2)
        mem.wb(cs, 0x5BA5, p3)
        di = (di + 1) & 0xFFFF
        bl = 0

    cpu.set_reg8(0, al if width else cpu.get_reg8(0))
    cpu.set_reg8(4, ah if width else cpu.get_reg8(4))
    cpu.set_reg8(2, dl if width else cpu.get_reg8(2))
    cpu.set_reg8(6, dh if width else cpu.get_reg8(6))
    cpu.set_reg8(3, bl)
    cpu.s.di = di
    cpu.s.cx = 0
    # These flags are normally overwritten by the row-copy INC below; keep the
    # RCL result here for completeness before the copy phase runs.
    cpu.set_logic_flags(final_rcl_value, 8)
    cpu.set_flag(CF, bool(cf))

    def copy_temp_row(start: int, return_ip: int) -> None:
        count_word = mem.rw(cs, 0x5B9C)
        count = count_word if count_word != 0 else 0x10000
        src_di = start & 0xFFFF
        out_di = mem.rw(cs, 0x5BA6)

        # Mirror CALL 291C plus the helper's final PUSH CX/PUSH DI scratches.
        mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, return_ip & 0xFFFF)
        mem.ww(ss, (cpu.s.sp - 4) & 0xFFFF, 0x0001)
        mem.ww(ss, (cpu.s.sp - 6) & 0xFFFF, (src_di + count) & 0xFFFF)

        if count and src_di + count <= 0x10000 and out_di + count <= 0x10000 \
                and not (mem.ega_planar and _ega_aperture_overlap(es, out_di, count)):
            src = (cs_base + src_di) & 0xFFFFF
            dst = (es_base + out_di) & 0xFFFFF
            data[dst:dst + count] = data[src:src + count]
            al_last = data[src + count - 1]
            src_di = (src_di + count) & 0xFFFF
            out_di = (out_di + count) & 0xFFFF
        else:
            al_last = cpu.get_reg8(0)
            for _ in range(count):
                al_last = mem.rb(cs, src_di)
                src_di = (src_di + 1) & 0xFFFF
                mem.wb(es, out_di, al_last)
                out_di = (out_di + 1) & 0xFFFF

        mem.ww(cs, 0x5BA6, out_di)
        cpu.s.di = src_di
        cpu.s.cx = 0
        cpu.set_reg8(0, al_last)
        old_cf = cpu.get_flag(CF)
        old = (src_di - 1) & 0xFFFF
        cpu.set_add_flags(old, 1, old + 1, 16)
        cpu.set_flag(CF, old_cf)

    copy_temp_row(0x5AF4, 0x28EB)
    copy_temp_row(0x5B1C, 0x28F6)
    copy_temp_row(0x5B44, 0x2901)
    copy_temp_row(0x5B6C, 0x290C)

    cpu.s.di = mem.rw(cs, 0x5BA6)
    outer = cpu.pop()
    cpu.s.cx = (outer - 1) & 0xFFFF
    cpu.s.ip = 0x27EB if cpu.s.cx != 0 else 0x27D9


@registry.replace(0x1010, 0x291C, "overkill_ega_temp_row_copy_291c")
def overkill_ega_temp_row_copy_291c(cpu):
    if _self_disable_if_patched(cpu, 0x291C, _SIG_291C, "overkill_ega_temp_row_copy_291c"):
        return
    """Replace the hot EGA temp-row copy helper at 1010:291C.

    Original shape::

        push cx
    loop:
        mov  al,cs:[di]
        inc  di
        push di
        mov  di,cs:[5BA6]
        stosb
        mov  cs:[5BA6],di
        pop  di
        pop  cx
        loop loop
        ret

    It copies ``CX`` bytes from a temporary CS row to the current ES output
    cursor stored at ``CS:5BA6``.  The helper is called four times for each EGA
    converted row, so collapsing the interpreted push/pop/stos loop noticeably
    speeds up EGA startup and menu rendering without changing renderer logic.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    count = cpu.s.cx & 0xFFFF
    if count == 0:
        count = 0x10000

    source_di = cpu.s.di & 0xFFFF
    out_di = mem.rw(cs, 0x5BA6)
    ah = cpu.get_reg8(4)
    last_source_di = source_di

    # Preserve the stack scratch left by the final PUSH CX / PUSH DI pair.  The
    # words are popped again, but full-memory oracle tests can still observe the
    # overwritten stack slots.
    final_pushed_cx = 1
    final_pushed_di = (source_di + count) & 0xFFFF
    mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, final_pushed_cx)
    mem.ww(cpu.s.ss, (cpu.s.sp - 4) & 0xFFFF, final_pushed_di)

    src_base = (cs << 4)
    es = cpu.s.es & 0xFFFF
    dst_base = es << 4
    data = mem.data
    planar_destination = mem.ega_planar and _ega_aperture_overlap(es, out_di, count)
    for i in range(count):
        al = data[(src_base + source_di) & 0xFFFFF]
        source_di = (source_di + 1) & 0xFFFF
        last_source_di = source_di
        if planar_destination:
            # STOSB into A000h must go through the EGA map-mask router.  The
            # previous lift wrote the flat A000 byte directly, which only changed
            # shadow plane 0 and could leave stale bits in the other planes.
            mem.wb(es, out_di, al)
        else:
            data[(dst_base + out_di) & 0xFFFFF] = al
        out_di = (out_di + 1) & 0xFFFF
        cpu.set_reg8(0, al)

    mem.ww(cs, 0x5BA6, out_di)
    cpu.s.di = last_source_di
    cpu.s.cx = 0
    # Final flags are from the last INC DI.  INC preserves CF.
    old_cf = cpu.get_flag(CF)
    old = (last_source_di - 1) & 0xFFFF
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)
    cpu.set_reg8(4, ah)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x2932, "overkill_ega_transparency_mask_2932")
def overkill_ega_transparency_mask_2932(cpu):
    if _self_disable_if_patched(cpu, 0x2932, _SIG_2932, "overkill_ega_transparency_mask_2932"):
        return
    """Replace the hot EGA transparency-mask builder at 1010:2932.

    This is the same routine as the previous transliterated hook, but it now
    computes the eight transparency bits directly instead of executing the
    original RCL chain through CPU.shift for every bit of every plane byte.
    The helper is called thousands of times by the EGA startup/menu asset path,
    so avoiding per-bit flag/register helper traffic is much more valuable than
    adding another tiny leaf hook.
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    mem = cpu.mem

    width = mem.rw(cs, 0x5B9C)
    si = s.si & 0xFFFF
    bx = (width * 3) & 0xFFFF

    al_src = mem.rb(ds, si)
    ah_src = mem.rb(ds, (si + width) & 0xFFFF)
    dl_src = mem.rb(ds, (si + ((width << 1) & 0xFFFF)) & 0xFFFF)
    dh_src = mem.rb(ds, (si + bx) & 0xFFFF)
    transparent = mem.rb(cs, 0x0000) & 0x0F

    def rcl8(value: int, carry: int) -> tuple[int, int]:
        value &= 0xFF
        return (((value << 1) | carry) & 0xFF), ((value >> 7) & 1)

    # Keep the exact carry interactions through CS:[5BA1] and CS:[5BA0], but
    # run them as simple integer operations rather than CPU.shift calls.
    al = al_src
    ah = ah_src
    dl = dl_src
    dh = dh_src
    scratch = mem.rb(cs, 0x5BA1)
    mask = 0
    # The loop's incoming CF is not the caller's CF: the original setup
    # executes SHL BX,1 and then ADD BX,CS:[5B9C], so the first RCL sees the
    # carry produced by that ADD.
    bx2 = (width << 1) & 0xFFFF
    cf = 1 if (bx2 + width) > 0xFFFF else 0
    for _ in range(8):
        dh, cf = rcl8(dh, cf)
        scratch, cf = rcl8(scratch, cf)
        dl, cf = rcl8(dl, cf)
        scratch, cf = rcl8(scratch, cf)
        ah, cf = rcl8(ah, cf)
        scratch, cf = rcl8(scratch, cf)
        al, cf = rcl8(al, cf)
        scratch, cf = rcl8(scratch, cf)
        scratch &= 0x0F
        cf = 1 if scratch == transparent else 0
        mask, cf = rcl8(mask, cf)

    mem.wb(cs, 0x5BA0, mask)
    mem.wb(cs, 0x5BA1, scratch)
    mem.ww(s.ss & 0xFFFF, (s.sp - 2) & 0xFFFF, 0x0001)  # final PUSH CX scratch

    s.bx = bx
    s.cx = 0
    s.ax = ((ah & 0xFF) << 8) | (mask & 0xFF)  # MOV AL,[5BA0] after the loop.
    s.dx = ((dh & 0xFF) << 8) | (dl & 0xFF)

    mem.wb(s.es & 0xFFFF, s.di & 0xFFFF, mask)
    s.di = (s.di + ( -1 if cpu.get_flag(DF) else 1)) & 0xFFFF

    old_cf = bool(cf)
    old_si = s.si & 0xFFFF
    s.si = (old_si + 1) & 0xFFFF
    cpu.set_add_flags(old_si, 1, old_si + 1, 16)
    cpu.set_flag(CF, old_cf)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x5827, "overkill_ega_planar_to_linear_copy_5827")
def overkill_ega_planar_to_linear_copy_5827(cpu):
    """Replace the hot 1010:5827 EGA row-copy loop only.

    This deliberately stops at 58A4 and lets the original setup/render driver run
    after the copied 200-row screen/work-buffer transfer.  It is a narrow hook:
    it collapses the repeated row copy selected by CS:95BCh, but does not infer
    higher-level video semantics.
    """
    cs = cpu.s.cs & 0xFFFF
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000

    for _ in range(iterations):
        cpu.push(cpu.s.cx)

        # 5828..582F: BX = CS:[95BC] << 1; JMP CS:[5834+BX]
        mode_word = cpu.mem.rw(cs, 0x95BC)
        cpu.s.bx = mode_word & 0xFFFF
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
        mode = (cpu.s.bx >> 1) & 0xFFFF

        if mode == 0:
            # 583A: packed/linear 80-byte row, planar source stride.
            cpu.s.cx = 0x0050
            _rep_movsb(cpu, cpu.s.cx)
            _sub_reg16(cpu, 6, 0x0050)   # SI -= 80
            _add_reg16(cpu, 6, 0x2000)   # next EGA plane/scanline block
            _test_word(cpu, cpu.s.si, 0x4000)
            if not cpu.get_flag(ZF):
                _add_reg16(cpu, 6, 0xC050)
        elif mode == 1:
            # 5852: four 40-byte plane reads selected through GC index writes.
            # A real EGA returns bytes from the GC read-map-selected plane while
            # SI stays at the same CPU offset.  Copy directly from our shadow
            # plane when the geometry is simple; otherwise fall back through
            # mem.rb/mem.wb so the selected-read-plane emulation still applies.
            cpu.s.ax = 0x0004
            _out_dx_ax(cpu)
            for plane in range(4):
                count = 0x0028
                si = cpu.s.si & 0xFFFF
                di = cpu.s.di & 0xFFFF
                if (cpu.mem.ega_planar
                        and (cpu.s.ds & 0xFFFF) == 0xA000
                        and si + count <= EGA_PLANE_WINDOW
                        and di + count <= 0x10000
                        and not _ega_aperture_overlap(cpu.s.es, di, count)):
                    read_plane = cpu.mem.ega_read_plane & 0x03
                    src = EGA_APERTURE + read_plane * EGA_PLANE_STRIDE + si
                    dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
                    cpu.mem.data[dst:dst + count] = cpu.mem.data[src:src + count]
                    cpu.s.si = (si + count) & 0xFFFF
                    cpu.s.di = (di + count) & 0xFFFF
                    cpu.s.cx = 0
                else:
                    cpu.s.cx = count
                    _rep_movsb(cpu, cpu.s.cx)
                if plane != 3:
                    _sub_reg16(cpu, 6, count)
                    _inc_reg8_preserve_cf(cpu, 4)  # INC AH
                    _out_dx_ax(cpu)
        elif mode == 2:
            # 587E: 80 word copies (=160 bytes), different EGA row wrap rule.
            cpu.s.cx = 0x0050
            _rep_movsw(cpu, cpu.s.cx)
            _sub_reg16(cpu, 6, 0x00A0)
            _add_reg16(cpu, 6, 0x2000)
            _test_word(cpu, cpu.s.si, 0x8000)
            if not cpu.get_flag(ZF):
                _add_reg16(cpu, 6, 0x80A0)
        else:
            raise RuntimeError(f"unsupported OVERKILL 5827 video mode selector {mode_word:04X}")

        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unchanged

    # 5898..58A3: optional final graphics-controller write for mode 1.
    _cmp_word(cpu, cpu.mem.rw(cs, 0x95BC), 0x0001)
    if cpu.get_flag(ZF):
        cpu.s.ax = 0x0004
        _out_dx_ax(cpu)
    cpu.s.ip = 0x58A4


def _rep_movsw(cpu, count: int) -> None:
    count &= 0xFFFF
    if count == 0:
        cpu.s.cx = 0
        return

    byte_count = count * 2
    if not cpu.get_flag(DF):
        si = cpu.s.si & 0xFFFF
        di = cpu.s.di & 0xFFFF
        if si + byte_count <= 0x10000 and di + byte_count <= 0x10000 \
                and not (cpu.mem.ega_planar and (
                    _ega_aperture_overlap(cpu.s.ds, si, byte_count)
                    or _ega_aperture_overlap(cpu.s.es, di, byte_count)
                )):
            src = (((cpu.s.ds & 0xFFFF) << 4) + si) & 0xFFFFF
            dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
            if src + byte_count <= len(cpu.mem.data) and dst + byte_count <= len(cpu.mem.data):
                cpu.mem.data[dst:dst + byte_count] = cpu.mem.data[src:src + byte_count]
                cpu.s.si = (si + byte_count) & 0xFFFF
                cpu.s.di = (di + byte_count) & 0xFFFF
                cpu.s.cx = 0
                return

    delta = -2 if cpu.get_flag(DF) else 2
    for _ in range(count):
        cpu.mem.ww(cpu.s.es, cpu.s.di, cpu.mem.rw(cpu.s.ds, cpu.s.si))
        cpu.s.si = (cpu.s.si + delta) & 0xFFFF
        cpu.s.di = (cpu.s.di + delta) & 0xFFFF
    cpu.s.cx = 0


def _inc_reg8_preserve_cf(cpu, idx: int) -> None:
    old_cf = cpu.get_flag(CF)
    old = cpu.get_reg8(idx)
    result = old + 1
    cpu.set_reg8(idx, result)
    cpu.set_add_flags(old, 1, result, 8)
    cpu.set_flag(CF, old_cf)


def _out_dx_ax(cpu) -> None:
    if cpu.port_writer:
        cpu.port_writer(cpu, cpu.s.dx & 0xFFFF, cpu.s.ax & 0xFFFF, 16)


def _out_dx_al(cpu) -> None:
    if cpu.port_writer:
        cpu.port_writer(cpu, cpu.s.dx & 0xFFFF, cpu.get_reg8(0), 8)


def _cmp_byte(cpu, a: int, b: int) -> None:
    cpu.set_sub_flags(a & 0xFF, b & 0xFF, (a & 0xFF) - (b & 0xFF), 8)


@registry.replace(0x1010, 0xCCAA, "overkill_dirty_copy_mode1_ccaa")
def overkill_dirty_copy_mode1_ccaa(cpu):
    if _self_disable_if_patched(cpu, 0xCCAA, _SIG_CCAA, "overkill_dirty_copy_mode1_ccaa"):
        return
    """Replace dirty detect/copy mode 1 at 1010:CCAA.

    Compares eight ES:SI words against ES:DI with an 80-byte stride.  Changed
    words are copied and DL is set to 1.  The surrounding dispatcher at CC90
    sets ES and clears DL before jumping here; the continuation at CD08 tests DL.
    """
    cpu.s.cx = 0x0008
    while cpu.s.cx != 0:
        src = cpu.mem.rw(cpu.s.es, cpu.s.si)
        dst = cpu.mem.rw(cpu.s.es, cpu.s.di)
        cpu.s.ax = src
        _cmp_word(cpu, src, dst)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.ww(cpu.s.es, cpu.s.di, src)
        _add_reg16(cpu, 7, 0x0050)
        _add_reg16(cpu, 6, 0x0050)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xCD08


@registry.replace(0x1010, 0xCCC4, "overkill_dirty_copy_mode3_ccc4")
def overkill_dirty_copy_mode3_ccc4(cpu):
    if _self_disable_if_patched(cpu, 0xCCC4, _SIG_CCC4, "overkill_dirty_copy_mode3_ccc4"):
        return
    """Replace dirty detect/copy mode 3 at 1010:CCC4.

    Eight iterations, comparing/copying two adjacent words per row, then
    stepping source/destination by 160 bytes.
    """
    cpu.s.cx = 0x0008
    while cpu.s.cx != 0:
        src0 = cpu.mem.rw(cpu.s.es, cpu.s.si)
        dst0 = cpu.mem.rw(cpu.s.es, cpu.s.di)
        cpu.s.ax = src0
        _cmp_word(cpu, src0, dst0)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.ww(cpu.s.es, cpu.s.di, src0)

        src1 = cpu.mem.rw(cpu.s.es, (cpu.s.si + 2) & 0xFFFF)
        dst1 = cpu.mem.rw(cpu.s.es, (cpu.s.di + 2) & 0xFFFF)
        cpu.s.ax = src1
        _cmp_word(cpu, src1, dst1)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.ww(cpu.s.es, (cpu.s.di + 2) & 0xFFFF, src1)

        _add_reg16(cpu, 7, 0x00A0)
        _add_reg16(cpu, 6, 0x00A0)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xCD08


@registry.replace(0x1010, 0xCCF0, "overkill_dirty_copy_mode2_ccf0")
def overkill_dirty_copy_mode2_ccf0(cpu):
    if _self_disable_if_patched(cpu, 0xCCF0, _SIG_CCF0, "overkill_dirty_copy_mode2_ccf0"):
        return
    """Replace dirty detect/copy mode 2 at 1010:CCF0.

    Compares 32 ES:SI bytes against ES:DI with a 40-byte stride.
    """
    cpu.s.cx = 0x0020
    while cpu.s.cx != 0:
        src = cpu.mem.rb(cpu.s.es, cpu.s.si)
        dst = cpu.mem.rb(cpu.s.es, cpu.s.di)
        cpu.set_reg8(0, src)
        _cmp_byte(cpu, src, dst)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.wb(cpu.s.es, cpu.s.di, src)
        _add_reg16(cpu, 7, 0x0028)
        _add_reg16(cpu, 6, 0x0028)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xCD08


@registry.replace(0x1010, 0x2750, "overkill_present_ega_frame_2750")
def overkill_present_ega_frame_2750(cpu):
    if _self_disable_if_patched(cpu, 0x2750, _SIG_2750, "overkill_present_ega_frame_2750"):
        return
    """Replace the EGA mode-1 frame-present blit at 1010:2750.

    The real routine writes the same A000h offsets four times while changing the
    EGA sequencer map-mask register (03C4h index 02h / 03C5h data 1,2,4,8).
    The memory model routes those CPU-visible A000h writes into the selected
    shadow plane.  The common A000 case copies directly into that selected
    shadow plane; unusual geometry falls back through ``Memory.ww``.  The copied
    source bytes and register flow mirror the original routine; this is
    deliberately only the final presenter, not a broad VGA/EGA hardware
    emulator.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    # 2750..275D setup.
    cpu.s.si = mem.rw(cpu.s.ds, 0x234C)
    cpu.s.es = mem.rw(cs, 0x95A4)
    cpu.s.ds = mem.rw(cs, 0x9598)
    cpu.s.bx = 0x000D
    cpu.s.di = 0x00A0
    cpu.s.dx = 0x03C4
    cpu.set_reg8(0, 0x02)
    _out_dx_al(cpu)                 # OUT 03C4h,02h: sequencer map mask index.
    _inc_reg16_preserve_cf(cpu, 2)  # INC DX -> 03C5h.
    cpu.s.bp = 0x00C0

    es_seg = cpu.s.es & 0xFFFF
    width = 0x001A
    words = width // 2
    data = mem.data

    def set_present_map_mask() -> None:
        # Runtime executions update this via DOSMachine.port_write.  Synthetic
        # hook tests often have no port writer attached, so mirror this routine's
        # known 03C5h map-mask writes locally too.
        mem.ega_planar = True
        mem.ega_map_mask = cpu.get_reg8(0) & 0x0F

    def fast_copy_selected_plane(src: int, dst: int) -> bool:
        mask = cpu.get_reg8(0) & 0x0F
        if (not mem.ega_planar
                or es_seg != 0xA000
                or mask not in (0x01, 0x02, 0x04, 0x08)
                or src + width > 0x10000
                or dst + width > EGA_PLANE_WINDOW
                or _ega_aperture_overlap(cpu.s.ds, src, width)):
            return False
        plane = (mask.bit_length() - 1) & 0x03
        src_base = (((cpu.s.ds & 0xFFFF) << 4) + src) & 0xFFFFF
        dst_base = EGA_APERTURE + plane * EGA_PLANE_STRIDE + dst
        data[dst_base:dst_base + width] = data[src_base:src_base + width]
        return True

    while True:
        cpu.set_reg8(0, 0x01)
        _out_dx_al(cpu)
        set_present_map_mask()
        for plane in range(4):
            # Original plane copy is REP MOVSW with BX=000Dh: 26 bytes.
            # MOVS changes SI/DI/CX but not flags.
            src = cpu.s.si & 0xFFFF
            dst = cpu.s.di & 0xFFFF
            if fast_copy_selected_plane(src, dst):
                src = (src + width) & 0xFFFF
                dst = (dst + width) & 0xFFFF
            else:
                for _ in range(words):
                    mem.ww(es_seg, dst, mem.rw(cpu.s.ds, src))
                    src = (src + 2) & 0xFFFF
                    dst = (dst + 2) & 0xFFFF
            cpu.s.si = src
            cpu.s.di = dst
            cpu.s.cx = 0
            if plane != 3:
                _sub_reg16(cpu, 7, width)
                cpu.set_reg8(0, cpu.shift(4, cpu.get_reg8(0), 1, 8))
                _out_dx_al(cpu)
                set_present_map_mask()
        _add_reg16(cpu, 7, 0x000E)  # Net row stride: 26 copied bytes + 14 = 40.
        _dec_reg16_preserve_cf(cpu, 5)
        if cpu.get_flag(ZF):
            break

    cpu.set_reg8(0, 0x0F)
    _out_dx_al(cpu)
    set_present_map_mask()
    cpu.s.ds = mem.rw(cs, 0x9596)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x50C9, "overkill_wait_vga_retrace_50c9")
def overkill_wait_vga_retrace_50c9(cpu):
    """Replace the C9EA VGA retrace wait wrapper reached through 50C9.

    The original code is not a high-level timer; it performs two busy-waits on
    port 03DAh, with the order controlled by CS:CA5A.  The hook still reads the
    port through the DOS/video IO layer so vga_status_reads and final AL/flags
    remain oracle-relative.
    """
    cs = cpu.s.cs & 0xFFFF
    inverted_order = cpu.mem.rb(cs, 0xCA5A) == 0x01
    _wait_vga_status_bit3(cpu, want_set=not inverted_order)
    _wait_vga_status_bit3(cpu, want_set=inverted_order)
    # Original path is 50C9 -> JMP C9EA; C9EA performs CALL C9F1 and CALL
    # CA02 before RET.  Those internal near calls leave their last return word
    # (C9F0) in the scratch stack slot at the original SS:SP-2.
    cpu.mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, 0xC9F0)
    cpu.s.ip = cpu.pop()


def _wait_vga_status_bit3(cpu, *, want_set: bool) -> None:
    cpu.s.dx = 0x03DA
    # Keep a guard for testability if a runtime accidentally has no IO layer.
    for _ in range(100000):
        value = cpu.port_reader(cpu, 0x03DA, 8) if cpu.port_reader else (0x08 if want_set else 0x00)
        cpu.set_reg8(0, value)
        result = value & 0x08
        cpu.set_logic_flags(result, 8)  # TEST AL,08h
        if (result != 0) == want_set:
            return
    raise RuntimeError("VGA status wait did not converge")

@registry.replace(0x1010, 0x58DF, "overkill_postcopy_blit_wait_loop_58df")
def overkill_postcopy_blit_wait_loop_58df(cpu):
    if _self_disable_if_patched(cpu, 0x58DF, _SIG_58DF, "overkill_postcopy_blit_wait_loop_58df"):
        return
    """Replace the narrow 58DF..58F8 post-copy blit/wait loop.

    This is still a control-flow hook, not a new renderer: for the captured
    mode-0 path it repeatedly invokes the already verified 497A blitter and the
    verified 50C9 VGA wait hook, preserving the PUSH/CALL/POP stack scratches
    and the unusual DEC CX + LOOP CX double-decrement.
    """
    cs = cpu.s.cs & 0xFFFF
    while True:
        cpu.push(cpu.s.cx)                         # 58DF PUSH CX
        cpu.mem.ww(cs, 0x5901, cpu.s.cx)           # 58E0 MOV CS:[5901],CX
        mode = cpu.mem.rw(cs, 0x95BC)
        cpu.s.bx = mode & 0xFFFF
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)   # 58E5..58EA
        if mode != 0:
            # The mode-1/2 callees are different planar/Tandy blitters and have
            # not been lifted as part of this narrow mode-0 hook.  Do not crash
            # EGA/Tandy profiling: make this address self-disabling and let the
            # original interpreted code run from 58DF on the next CPU step.
            cpu.replacement_hooks.pop((cs, 0x58DF), None)
            cpu.hook_names.pop((cs, 0x58DF), None)
            cpu.s.ip = 0x58DF
            return
        _call_hook_like_near_call(cpu, overkill_blit_scaled_column_block_497a, 0x58F1)
        if cpu.s.ip != 0x58F1:
            raise RuntimeError(f"497A replacement returned to unexpected IP {cpu.s.ip:04X}")
        _call_hook_like_near_call(cpu, overkill_wait_vga_retrace_50c9, 0x58F4)
        if cpu.s.ip != 0x58F4:
            raise RuntimeError(f"50C9 replacement returned to unexpected IP {cpu.s.ip:04X}")
        cpu.s.cx = cpu.pop()                       # 58F4 POP CX
        _dec_reg16_preserve_cf(cpu, 1)             # 58F5 DEC CX
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF         # 58F6 LOOP, no flags
        if cpu.s.cx == 0:
            cpu.s.ip = 0x58F8
            return


@registry.replace(0x1010, 0x0679, "overkill_wait_timer_tick_0679")
def overkill_wait_timer_tick_0679(cpu):
    """Replace the timer-tick busy-wait at 1010:0679.

    Original routine:

        0679  cmp byte ptr cs:[066B],0
        067F  jz   0679
        0681  ret

    It spins until the byte flag at ``CS:066B`` becomes non-zero.  That flag is
    only ever touched by three tiny resident routines:

        1010:066C  inc byte ptr cs:[066B] ; ret   (tick increment helper)
        1010:0672  mov byte ptr cs:[066B],0 ; ret (clear before waiting)
        1010:0679  this wait loop

    ``066C`` is reached from the game's own reprogrammed IRQ0 handler installed
    at ``1010:068A``: that installer saves the old INT 08h vector to ``CS:0738``,
    reprograms the 8253 PIT (``out 43h,36h`` then divisor ``0x4000`` ≈ 72.8 Hz),
    and points INT 08h at the ISR ``1010:06E5``.  The ISR drives sound/per-tick
    logic, calls ``066C`` to bump ``066B`` on alternating sub-ticks, and chains
    the original BIOS handler every fourth tick.

    This interpreter delivers no asynchronous hardware interrupts, so that ISR
    never runs and ``066B`` stays 0 forever — the runtime spins here indefinitely
    once it reaches the main per-frame timing loop (callers at 981A/D025/D340/
    D41F, each paired with a ``066C`` clear at 97B2/D007/D318/D406).

    Mirroring the existing narrow VGA-retrace model (``50C9`` / port ``03DAh``),
    this hook models exactly one elapsed timer tick: if the flag is still 0 it
    bumps it to 1 (one ISR ``inc``), then reproduces the final, exiting loop
    iteration (``cmp`` against 0, ``jz`` not taken, ``ret``).  ``066B`` has no
    other consumer, so this is sufficient to satisfy the wait faithfully without
    speculatively emulating the whole IRQ0/sound ISR chain.
    """
    cs = cpu.s.cs & 0xFFFF
    flag = cpu.mem.rb(cs, 0x066B)
    if flag == 0:
        flag = 1  # model a single elapsed reprogrammed-IRQ0 tick
        cpu.mem.wb(cs, 0x066B, flag)
    # Final loop iteration: CMP byte ptr CS:[066B],0 (now non-zero); JZ not taken; RET.
    cpu.set_sub_flags(flag, 0, flag, 8)
    cpu.s.ip = cpu.pop()
    # There is exactly one of these waits per rendered frame, so it is the natural
    # place to throttle the game to real time when an interactive front-end asks.
    if cpu.timer_pacer is not None:
        cpu.timer_pacer()



@registry.replace(0x1010, 0x3354, "overkill_present_tandy_frame_3354")
def overkill_present_tandy_frame_3354(cpu):
    """Replace the mode-2 Tandy frame-present blit at 1010:3354.

    The Tandy/PCjr presenter is selected by the same 5BDC video-mode jump table
    as the CGA and EGA presenters, but it copies to a 320x200x16 packed Tandy
    aperture instead of CGA 2bpp or EGA hardware planes.  Its address progression
    is the classic four-bank Tandy layout:

        screen offset = (y & 3) * 2000h + (y >> 2) * 00A0h + x_byte

    One byte contains two 4-bit pixels.  The source work buffer is still only the
    game's active 208-pixel-wide rectangle, so the presenter copies 52 words
    (104 bytes) for each of 192 rows, starting at screen offset 00A0h.
    """
    cs = cpu.s.cs & 0xFFFF
    # 3354 MOV SI,DS:[234C] (uses entry DS before DS is reloaded below).
    cpu.s.si = cpu.mem.rw(cpu.s.ds, 0x234C)
    # 3358/335D load destination/source selectors from the resident video state.
    cpu.s.es = cpu.mem.rw(cs, 0x95A4)
    cpu.s.ds = cpu.mem.rw(cs, 0x9598)
    # 3362..3368 constants: 52 words = 104 bytes per row, row 4 start, 192 rows.
    cpu.s.bx = 0x0034
    cpu.s.di = 0x00A0
    cpu.s.bp = 0x00C0
    while True:
        cpu.s.cx = cpu.s.bx & 0xFFFF       # 336B MOV CX,BX
        _rep_movsw(cpu, cpu.s.cx)          # 336D REP MOVSW
        _sub_reg16(cpu, 7, 0x0068)         # 336F SUB DI,68h
        _add_reg16(cpu, 7, 0x2000)         # 3372 ADD DI,2000h
        _test_word(cpu, cpu.s.di, 0x8000)  # 3376 TEST DI,8000h
        if not cpu.get_flag(ZF):           # 337A JZ 3380
            _add_reg16(cpu, 7, 0x80A0)     # 337C ADD DI,80A0h
        _dec_reg16_preserve_cf(cpu, 5)     # 3380 DEC BP
        if cpu.get_flag(ZF):               # 3381 JNZ 336B
            break
    cpu.s.ds = cpu.mem.rw(cs, 0x9596)      # 3383 MOV DS,CS:[9596]
    cpu.s.ip = cpu.pop()                   # 3388 RET


@registry.replace(0x1010, 0x447B, "overkill_present_frame_blit_447b")
def overkill_present_frame_blit_447b(cpu):
    """Replace the mode-0 frame-present blit reached via the 5BDC video jump table.

    The per-frame presenter ``1010:5BDC`` reads the mode selector ``CS:[95BC]``,
    shifts it left and ``jmp cs:[bx+5BE8]``.  For mode 0 the table entry is
    ``1010:447B``:

        447B  mov si, ds:[234C]      ; source cursor (work-buffer offset)
        447F  mov es, cs:[95A4]      ; destination segment (B800 video memory)
        4484  mov ds, cs:[9598]      ; source segment (decoded work buffer)
        4489  mov bx,1Ah / di,A0h / bp,C0h
        4492  mov cx,bx
              rep movsw              ; copy 1Ah (26) words = 52 bytes
              sub di,34h             ; rewind to row start
              add di,2000h           ; next interlaced scanline bank
              test di,4000h
              jz  44A7
              add di,C050h           ; wrap to next char row on bank crossing
        44A7  dec bp
              jnz 4492               ; C0h (192) rows
        44AA  mov ds, cs:[9596]      ; restore the game data segment
        44AF  ret

    Confirmed selectors in the live run: dest ``CS:[95A4]=B800h`` (CGA/EGA video
    memory), source ``CS:[9598]`` = the decoded work buffer, restore
    ``CS:[9596]`` = the game data segment.  This is the actual screen present and,
    once the main loop runs, the single hottest interpreted routine.

    The hook mirrors the interpreter's own helpers in the exact instruction order
    so registers, flags and memory match the oracle; it only collapses the Python
    per-iteration overhead of the 192-row interlaced copy.
    """
    cs = cpu.s.cs & 0xFFFF
    # 447B MOV SI, DS:[234C] (uses the entry DS before it is reloaded below).
    cpu.s.si = cpu.mem.rw(cpu.s.ds, 0x234C)
    # 447F/4484 load the destination and source segments from the resident selectors.
    cpu.s.es = cpu.mem.rw(cs, 0x95A4)
    cpu.s.ds = cpu.mem.rw(cs, 0x9598)
    # 4489..448F constants.
    cpu.s.bx = 0x001A
    cpu.s.di = 0x00A0
    cpu.s.bp = 0x00C0
    while True:
        cpu.s.cx = cpu.s.bx & 0xFFFF       # 4492 MOV CX,BX
        _rep_movsw(cpu, cpu.s.cx)          # 4494 REP MOVSW (sets CX=0, advances SI/DI)
        _sub_reg16(cpu, 7, 0x0034)         # 4496 SUB DI,34h
        _add_reg16(cpu, 7, 0x2000)         # 4499 ADD DI,2000h
        _test_word(cpu, cpu.s.di, 0x4000)  # 449D TEST DI,4000h
        if not cpu.get_flag(ZF):           # 44A1 JZ 44A7
            _add_reg16(cpu, 7, 0xC050)     # 44A3 ADD DI,C050h
        _dec_reg16_preserve_cf(cpu, 5)     # 44A7 DEC BP (CF unaffected on 8086)
        if cpu.get_flag(ZF):               # 44A8 JNZ 4492
            break
    cpu.s.ds = cpu.mem.rw(cs, 0x9596)      # 44AA MOV DS,CS:[9596]
    cpu.s.ip = cpu.pop()                   # 44AF RET

@registry.replace(0x1010, 0x017E, "overkill_keyboard_poll_bits_017e")
def overkill_keyboard_poll_bits_017e(cpu):
    """Replace the hot eight-key poll bit-packer at 1010:017E.

    The menu/gameplay input path repeatedly scans a small table of XT scan codes
    at DS:SI, reads the corresponding key-state byte from DS:DI+scan, shifts its
    low bit into DS:98BE, and advances SI.  It is small but very hot on static
    menu screens because the game polls it every frame.
    """
    s = cpu.s
    ds = s.ds & 0xFFFF
    data = cpu.mem.data
    base = ds << 4
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    cx = s.cx & 0xFFFF
    if cx == 0:
        cx = 0x10000

    bh = s.bx & 0xFF00
    al = s.ax & 0xFF
    bl = s.bx & 0xFF
    scratch_off = 0x98BE

    while cx:
        bl = data[(base + si) & 0xFFFFF]
        bx = bh | bl
        al = data[(base + ((bx + di) & 0xFFFF)) & 0xFFFFF]
        al = cpu.shift(5, al, 1, 8)  # SHR AL,1; CF becomes the key-state bit.
        scratch_addr = (base + scratch_off) & 0xFFFFF
        data[scratch_addr] = cpu.shift(2, data[scratch_addr], 1, 8)  # RCL byte [98BE],1.

        old_cf = cpu.get_flag(CF)
        old_si = si
        si = (si + 1) & 0xFFFF
        cpu.set_add_flags(old_si, 1, old_si + 1, 16)  # INC SI flags...
        cpu.set_flag(CF, old_cf)                      # ...but INC preserves CF.
        cx -= 1

    s.ax = (s.ax & 0xFF00) | (al & 0xFF)
    s.bx = bh | bl
    s.si = si
    s.cx = 0
    s.ip = 0x018B


@registry.replace(0x1010, 0xCD8D, "overkill_changed_word_present_8rows_cd8d")
def overkill_changed_word_present_8rows_cd8d(cpu):
    """Replace the changed-word CGA presenter loop at 1010:CD8D.

    After the dirty-copy detector marks a block as changed, this loop copies one
    word from the work buffer to the visible CGA aperture across eight interlaced
    scanlines.  It appears prominently on the planet/difficulty menu because the
    screen is redrawn in many small dirty cells when the selection changes.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    cx = s.cx & 0xFFFF
    if cx == 0:
        cx = 0x10000

    ax = s.ax & 0xFFFF
    while cx:
        ax = mem.rw(ds, si)
        mem.ww(es, di, ax)

        old_si = si
        si = (si + 0x50) & 0xFFFF
        # ADD SI flags are overwritten before the LOOP unless this is somehow
        # not followed by the DI/test path, so keep only the architectural result.
        old_di = di
        di = (di + 0x2000) & 0xFFFF
        cpu.set_add_flags(old_di, 0x2000, old_di + 0x2000, 16)
        cpu.s.di = di
        _test_word(cpu, di, 0x4000)
        if not cpu.get_flag(ZF):
            old_di = di
            di = (di + 0xC050) & 0xFFFF
            cpu.set_add_flags(old_di, 0xC050, old_di + 0xC050, 16)
            cpu.s.di = di
        cx -= 1

    s.ax = ax
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = 0xCE02


def _interpret_current_instruction_without_hook(cpu) -> None:
    """Interpret the current instruction when an overlaid address no longer matches a hook signature."""
    key = cpu.addr()
    fn = cpu.replacement_hooks.pop(key, None)
    try:
        cpu.step()
    finally:
        if fn is not None:
            cpu.replacement_hooks[key] = fn


def _code_matches(cpu, off: int, expected: bytes) -> bool:
    cs = cpu.s.cs & 0xFFFF
    return all(cpu.mem.rb(cs, (off + i) & 0xFFFF) == b for i, b in enumerate(expected))


def _overkill_strided_row_copy(cpu, *, row_advance: int) -> None:
    """Shared replacement for OVERKILL's LODSW/REP-MOVSB strided row copier."""
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    s.es = mem.rw(cs, 0x9598)

    df = cpu.get_flag(DF)
    lod_delta = -2 if df else 2
    si = s.si & 0xFFFF
    ax = mem.rw(s.ds, si)
    si = (si + lod_delta) & 0xFFFF
    s.cx = ax & 0xFFFF
    ax = mem.rw(s.ds, si)
    si = (si + lod_delta) & 0xFFFF
    s.si = si
    s.ax = ax & 0xFFFF
    s.ax = cpu.shift(4, s.ax, 1, 16)  # SHL AX,1
    s.bp = s.ax & 0xFFFF

    outer = s.cx if s.cx != 0 else 0x10000
    width = s.bp & 0xFFFF
    row_advance &= 0xFFFF
    for _ in range(outer):
        # PUSH CX / MOV CX,BP / REP MOVSB / SUB DI,BP / ADD DI,row_advance /
        # POP CX / LOOP.  Keep using the project's optimized REP helper so DF
        # and 16-bit wrapping semantics stay centralized.
        saved_cx = s.cx & 0xFFFF
        cpu.push(saved_cx)
        s.cx = width
        _rep_movsb(cpu, width)
        _sub_reg16(cpu, 7, width)
        _add_reg16(cpu, 7, row_advance)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF  # LOOP does not change flags.

    s.ip = cpu.pop()


_STRIDED_ROW_COPY_34_SIG = bytes.fromhex("2e 8e 06 98 95 ad 8b c8 ad d1 e0 8b e8 51 8b cd f3 a4 2b fd 83 c7 34 59 e2 f3 c3")
_STRIDED_ROW_COPY_50_SIG = bytes.fromhex("2e 8e 06 98 95 ad 8b c8 ad d1 e0 8b e8 51 8b cd f3 a4 2b fd 83 c7 50 59 e2 f3 c3")


@registry.replace(0x1010, 0x3EE1, "overkill_strided_row_copy_3ee1")
def overkill_strided_row_copy_3ee1(cpu):
    """Replace row copier 1010:3EE1, which advances destination rows by 34h.

    This address is overlaid/reused by later sprite code, so the hook only
    applies while the exact row-copy bytes are resident.
    """
    if not _code_matches(cpu, 0x3EE1, _STRIDED_ROW_COPY_34_SIG):
        _interpret_current_instruction_without_hook(cpu)
        return
    _overkill_strided_row_copy(cpu, row_advance=0x34)


@registry.replace(0x1010, 0x3EFC, "overkill_strided_row_copy_3efc")
def overkill_strided_row_copy_3efc(cpu):
    """Replace row copier 1010:3EFC, which advances destination rows by 50h.

    This address is overlaid/reused by later sprite code, so the hook only
    applies while the exact row-copy bytes are resident.
    """
    if not _code_matches(cpu, 0x3EFC, _STRIDED_ROW_COPY_50_SIG):
        _interpret_current_instruction_without_hook(cpu)
        return
    _overkill_strided_row_copy(cpu, row_advance=0x50)




def _rcr_stc_chain_5bytes(bl: int, bh: int, al: int, ah: int, dl: int, passes: int) -> tuple[int, int, int, int, int]:
    """Return the 5-byte result of repeated STC; RCR BL,BH,AL,AH,DL groups.

    Used by the CGA masked-sprite compositors.  The interpreted version updated
    CPU flags on every single rotate, but those flags are overwritten by the
    row-step ADD/DEC before control leaves the hook.
    """
    bl &= 0xFF; bh &= 0xFF; al &= 0xFF; ah &= 0xFF; dl &= 0xFF
    for _ in range(passes):
        cf = 1
        old = bl; bl = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = bh; bh = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = al; al = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = ah; ah = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = dl; dl = ((cf << 7) | (old >> 1)) & 0xFF
    return bl, bh, al, ah, dl


def _shr_rcr_chain_5bytes(bl: int, bh: int, al: int, ah: int, dl: int, passes: int) -> tuple[int, int, int, int, int]:
    """Return the 5-byte result of repeated SHR BL; RCR BH,AL,AH,DL groups."""
    bl &= 0xFF; bh &= 0xFF; al &= 0xFF; ah &= 0xFF; dl &= 0xFF
    for _ in range(passes):
        cf = bl & 1
        bl = (bl >> 1) & 0xFF
        old = bh; bh = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = al; al = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = ah; ah = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = dl; dl = ((cf << 7) | (old >> 1)) & 0xFF
    return bl, bh, al, ah, dl


_MASKED_SPRITE_COMPOSITE_3EFB_SIG = bytes.fromhex(
    "8b 1c 8b 44 04 b2 ff f9 d0 db d0 df d0 d8 d0 dc d0 da"
)


@registry.replace(0x1010, 0x3EFB, "overkill_masked_sprite_composite_3efb")
def overkill_masked_sprite_composite_3efb(cpu):
    """Replace the overlaid 6-shift masked sprite loop at 1010:3EFB.

    This is the dominant interpreted loop on the planet/difficulty selection
    redraw path after the 3E12 two-shift compositor is hooked.  The address is
    overlay-reused, so only apply while the observed masked-compositor bytes are
    resident.
    """
    if not _code_matches(cpu, 0x3EFB, _MASKED_SPRITE_COMPOSITE_3EFB_SIG):
        _interpret_current_instruction_without_hook(cpu)
        return

    s = cpu.s
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    rows = bp if bp != 0 else 0x10000
    initial_dh = s.dx & 0xFF00
    final_dl = s.dx & 0x00FF
    mem = cpu.mem

    for _ in range(rows):
        mask_bx = mem.rw(ds, si)
        mask_ax = mem.rw(ds, (si + 4) & 0xFFFF)
        bl = mask_bx & 0xFF
        bh = (mask_bx >> 8) & 0xFF
        al = mask_ax & 0xFF
        ah = (mask_ax >> 8) & 0xFF
        dl = 0xFF
        bl, bh, al, ah, dl = _rcr_stc_chain_5bytes(bl, bh, al, ah, dl, 6)
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) & mask_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) & mask_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) & dl)

        data_bx = mem.rw(ds, (si + 2) & 0xFFFF)
        data_ax = mem.rw(ds, (si + 6) & 0xFFFF)
        bl = data_bx & 0xFF
        bh = (data_bx >> 8) & 0xFF
        al = data_ax & 0xFF
        ah = (data_ax >> 8) & 0xFF
        dl = 0x00
        cpu.set_logic_flags(0, 8)        # XOR DL,DL
        bl, bh, al, ah, dl = _shr_rcr_chain_5bytes(bl, bh, al, ah, dl, 6)
        data_bx = ((bh << 8) | bl) & 0xFFFF
        data_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) | data_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) | data_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) | dl)
        final_dl = dl

        si = (si + 8) & 0xFFFF
        old_di = di
        di_sum = old_di + 0x34
        di = di_sum & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, di_sum, 16)
        old_cf = cpu.get_flag(CF)
        old_bp = bp
        bp = (bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)
        cpu.set_flag(CF, old_cf)         # DEC preserves CF.

    s.si = si
    s.di = di
    s.bp = bp
    s.dx = initial_dh | final_dl
    s.bx = data_bx
    s.ax = data_ax
    s.ds = mem.rw(cs, 0x9596)            # MOV DS,CS:[9596] before RET.
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x3E12, "overkill_masked_sprite_composite_3e12")
def overkill_masked_sprite_composite_3e12(cpu):
    """Replace the hot masked CGA sprite/composite row loop at 1010:3E12.

    The original loop consumes eight source bytes per row, shifts mask and data
    bits through carry twice, then AND/OR-composites three destination bytes.
    It is hit heavily by the planet/difficulty selection screen when the menu
    redraws its sprites and highlight frame.
    """
    s = cpu.s
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    rows = bp if bp != 0 else 0x10000
    initial_dh = s.dx & 0xFF00
    final_dl = s.dx & 0x00FF

    mem = cpu.mem
    for _ in range(rows):
        # Mask phase:
        #   mov bx,[si]; mov ax,[si+4]; mov dl,ff; stc;
        #   rcr bl,bh,al,ah,dl twice; and destination bytes.
        mask_bx = mem.rw(ds, si)
        mask_ax = mem.rw(ds, (si + 4) & 0xFFFF)
        bl = mask_bx & 0xFF
        bh = (mask_bx >> 8) & 0xFF
        al = mask_ax & 0xFF
        ah = (mask_ax >> 8) & 0xFF
        dl = 0xFF
        bl, bh, al, ah, dl = _rcr_stc_chain_5bytes(bl, bh, al, ah, dl, 2)
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) & mask_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) & mask_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) & dl)

        # Data phase:
        #   mov bx,[si+2]; mov ax,[si+6]; xor dl,dl;
        #   shr bl; rcr bh,al,ah,dl; repeat; or destination bytes.
        data_bx = mem.rw(ds, (si + 2) & 0xFFFF)
        data_ax = mem.rw(ds, (si + 6) & 0xFFFF)
        bl = data_bx & 0xFF
        bh = (data_bx >> 8) & 0xFF
        al = data_ax & 0xFF
        ah = (data_ax >> 8) & 0xFF
        dl = 0x00
        cpu.set_logic_flags(0, 8)        # XOR DL,DL clears CF/OF and sets ZF/PF.
        bl, bh, al, ah, dl = _shr_rcr_chain_5bytes(bl, bh, al, ah, dl, 2)
        data_bx = ((bh << 8) | bl) & 0xFFFF
        data_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) | data_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) | data_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) | dl)
        final_dl = dl

        # ADD SI,8; ADD DI,34h; DEC BP; JNZ 3E12.  Only the final DEC flags are
        # externally visible, with CF preserved from the immediately preceding
        # ADD DI because DEC does not modify CF.
        si = (si + 8) & 0xFFFF
        old_di = di
        di_sum = old_di + 0x34
        di = di_sum & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, di_sum, 16)
        old_cf = cpu.get_flag(CF)
        old_bp = bp
        bp = (bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)
        cpu.set_flag(CF, old_cf)

    s.si = si
    s.di = di
    s.bp = bp
    s.dx = initial_dh | final_dl
    # BX and AX are left containing the last shifted data words; DL is already
    # reflected in DX, while DH is untouched by the ASM loop.
    s.bx = data_bx
    s.ax = data_ax
    s.ip = 0x3E6A



@registry.replace(0x1010, 0x5A36, "overkill_cga_object_row_addr_5a36")
def overkill_cga_object_row_addr_5a36(cpu):
    """Replace the hot CGA object/sprite row-address helper at 1010:5A36.

    In mode 0 the dispatch target at 41F5 maps an object's Y coordinate
    (SS:BP+2) and X coordinate (SS:BP+4) to a work-buffer row address, stores the
    sub-byte X phase at SS:BP+12h, and optionally decrements SS:BP+24h.  This is
    called many times while rendering the planet-selection menu cursor/sprites.
    Non-CGA modes are dispatched back to the original target so EGA/Tandy remain
    conservative.
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    s.bx = mode & 0xFFFF
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1 from the dispatch stub.
    if mode == 1:
        _object_row_addr_mode1_2580(cpu)
        return
    if mode != 0:
        s.ip = cpu.mem.rw(cs, (0x5A42 + s.bx) & 0xFFFF)
        return

    ss = s.ss & 0xFFFF
    ds = s.ds & 0xFFFF
    bp = s.bp & 0xFFFF

    y = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
    s.bx = y
    _cmp_word(cpu, y, 0x00E0)
    if y >= 0x00E0:
        s.ax = 0xFFFF
        s.ip = cpu.pop()
        return

    s.bx = cpu.shift(4, y, 1, 16)  # SHL BX,1
    row_base = cpu.mem.rw(ds, (s.bx + 0x99C8) & 0xFFFF)
    s.bx = row_base
    _cmp_word(cpu, row_base, 0xFFFF)
    if row_base == 0xFFFF:
        s.ax = 0xFFFF
        s.ip = cpu.pop()
        return

    x = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    s.ax = x
    s.cx = x
    s.cx &= 0x0003
    cpu.set_logic_flags(s.cx, 16)       # AND CX,0003h
    cpu.mem.ww(ss, (bp + 0x12) & 0xFFFF, s.cx)
    s.ax = cpu.shift(5, s.ax, 1, 16)    # SHR AX,1
    s.ax = cpu.shift(5, s.ax, 1, 16)    # SHR AX,1
    _add_reg16(cpu, 0, row_base)        # ADD AX,BX

    countdown = cpu.mem.rw(ss, (bp + 0x24) & 0xFFFF)
    _cmp_word(cpu, countdown, 0)
    if countdown != 0:
        old_cf = cpu.get_flag(CF)
        result = (countdown - 1) & 0xFFFF
        cpu.mem.ww(ss, (bp + 0x24) & 0xFFFF, result)
        cpu.set_sub_flags(countdown, 1, countdown - 1, 16)
        cpu.set_flag(CF, old_cf)        # DEC preserves CF.
    s.ip = cpu.pop()


def _object_row_addr_mode1_2580(cpu) -> None:
    """Mode-1 row-address target reached through 1010:5A36 -> 1010:2580."""
    s = cpu.s
    ss = s.ss & 0xFFFF
    ds = s.ds & 0xFFFF
    bp = s.bp & 0xFFFF

    y = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
    s.bx = y
    _cmp_word(cpu, y, 0x00E0)
    if y >= 0x00E0:
        s.ax = 0xFFFF
        s.ip = cpu.pop()
        return

    s.bx = cpu.shift(4, y, 1, 16)  # SHL BX,1
    row_base = cpu.mem.rw(ds, (s.bx + 0x99C8) & 0xFFFF)
    s.bx = row_base
    _cmp_word(cpu, row_base, 0xFFFF)
    if row_base == 0xFFFF:
        s.ax = 0xFFFF
        s.ip = cpu.pop()
        return

    x = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    s.ax = x
    s.cx = x
    s.cx &= 0x0007
    cpu.set_logic_flags(s.cx, 16)       # AND CX,0007h
    cpu.mem.ww(ss, (bp + 0x12) & 0xFFFF, s.cx)
    s.ax = cpu.shift(5, s.ax, 1, 16)    # SHR AX,1
    s.ax = cpu.shift(5, s.ax, 1, 16)    # SHR AX,1
    s.ax = cpu.shift(5, s.ax, 1, 16)    # SHR AX,1
    _add_reg16(cpu, 0, row_base)        # ADD AX,BX

    countdown = cpu.mem.rw(ss, (bp + 0x24) & 0xFFFF)
    _cmp_word(cpu, countdown, 0)
    if countdown != 0:
        old_cf = cpu.get_flag(CF)
        result = (countdown - 1) & 0xFFFF
        cpu.mem.ww(ss, (bp + 0x24) & 0xFFFF, result)
        cpu.set_sub_flags(countdown, 1, countdown - 1, 16)
        cpu.set_flag(CF, old_cf)        # DEC preserves CF.
    s.ip = cpu.pop()


def _cga_xy_to_di_common(cpu, *, dispatch_table: int, row_table: int) -> None:
    s = cpu.s
    cs = s.cs & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    s.bx = mode & 0xFFFF
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1 from the dispatch stub.
    if mode != 0:
        s.ip = cpu.mem.rw(cs, (dispatch_table + s.bx) & 0xFFFF)
        return

    ds = s.ds & 0xFFFF
    y = (s.ax >> 8) & 0xFF
    x = s.ax & 0xFF
    # The target zeroes BH, shifts the y index to word addressing, loads the row
    # base, zeroes AH, doubles X in AX, then adds the row base.
    s.bx = (y << 1) & 0xFFFF
    row_base = cpu.mem.rw(ds, (row_table + s.bx) & 0xFFFF)
    s.bx = row_base
    s.ax = (x << 1) & 0xFFFF
    _add_reg16(cpu, 0, row_base)
    s.di = s.ax & 0xFFFF
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x5A00, "overkill_cga_xy_to_di_5a00")
def overkill_cga_xy_to_di_5a00(cpu):
    """Replace CGA coordinate-to-DI helper 1010:5A00 / target 422B."""
    _cga_xy_to_di_common(cpu, dispatch_table=0x5A0C, row_table=0x9EE8)


@registry.replace(0x1010, 0x5A24, "overkill_cga_xy_to_di_5a24")
def overkill_cga_xy_to_di_5a24(cpu):
    """Replace CGA coordinate-to-DI helper 1010:5A24 / target 4251."""
    _cga_xy_to_di_common(cpu, dispatch_table=0x5A30, row_table=0x9D58)

@registry.replace(0x1010, 0x5AC8, "overkill_dispatch_draw_object_5ac8")
def overkill_dispatch_draw_object_5ac8(cpu):
    """Collapse the hot CGA object draw dispatcher at 1010:5AC8."""
    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    bx = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    bx = (bx + mode + mode + mode) & 0xFFFF
    s.bx = bx
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1; final flags before JMP.
    s.ip = cpu.mem.rw(cs, (0x5AE2 + s.bx) & 0xFFFF)


@registry.replace(0x1010, 0x5A92, "overkill_dispatch_present_object_5a92")
def overkill_dispatch_present_object_5a92(cpu):
    """Collapse the hot object-present dispatcher at 1010:5A92."""
    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    s.es = cpu.mem.rw(cs, 0x9598)
    s.di = cpu.mem.rw(ss, (bp + 0x0C) & 0xFFFF)
    s.si = cpu.mem.rw(ss, (bp + 0x0E) & 0xFFFF)
    mode = cpu.mem.rw(cs, 0x95BC)
    bx = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    bx = (bx + mode + mode + mode) & 0xFFFF
    s.bx = bx
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1; final flags before JMP.
    s.ip = cpu.mem.rw(cs, (0x5AB6 + s.bx) & 0xFFFF)


@registry.replace(0x1010, 0xAA44, "overkill_clc_ret_aa44")
def overkill_clc_ret_aa44(cpu):
    """Replace the tiny hot CLC/RET success helper at 1010:AA44."""
    cpu.set_flag(CF, False)
    cpu.s.ip = cpu.pop()
