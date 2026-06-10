from __future__ import annotations

from .cpu import CF, DF, ZF, SF, PF
from .hooks import registry


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


@registry.replace(0x1010, 0x4537, "overkill_expand_4plane_row_4537")
def overkill_expand_4plane_row_4537(cpu):
    """Replace the hot 4-plane-to-packed-pixels row helper at 1010:4537.

    This is the leaf helper called thousands of times by the startup renderer
    around 1010:4516.  It reads four source bitplanes separated by CS:5B9C,
    runs the exact already-verified 45F6 packer four times, optionally builds a
    transparency mask through the already-verified 45CB bit expander, then builds
    the visible pixel word through the same 45CB expander.

    The implementation deliberately invokes the smaller verified hooks with the
    same near-call stack write/pop pattern, instead of reimplementing their
    internals here.  That keeps this larger replacement easier to audit.
    """
    cs = cpu.s.cs & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    width = cpu.mem.rw(cs, 0x5B9C)

    cpu.s.bx = width
    cpu.set_reg8(0, cpu.mem.rb(ds, cpu.s.si))
    cpu.set_reg8(4, cpu.mem.rb(ds, (cpu.s.si + cpu.s.bx) & 0xFFFF))
    cpu.s.bx = (cpu.s.bx << 1) & 0xFFFF
    cpu.set_reg8(2, cpu.mem.rb(ds, (cpu.s.si + cpu.s.bx) & 0xFFFF))
    cpu.s.bx = (cpu.s.bx + width) & 0xFFFF
    cpu.set_reg8(6, cpu.mem.rb(ds, (cpu.s.si + cpu.s.bx) & 0xFFFF))

    _call_hook_like_near_call(cpu, overkill_pack_four_pixels_45f6, 0x454E)
    cpu.mem.wb(cs, 0x5B95, cpu.get_reg8(1))
    cpu.mem.wb(cs, 0x5B99, cpu.get_reg8(5))

    _call_hook_like_near_call(cpu, overkill_pack_four_pixels_45f6, 0x455B)
    cpu.mem.wb(cs, 0x5B94, cpu.get_reg8(1))
    cpu.mem.wb(cs, 0x5B98, cpu.get_reg8(5))

    _call_hook_like_near_call(cpu, overkill_pack_four_pixels_45f6, 0x4568)
    cpu.mem.wb(cs, 0x5B97, cpu.get_reg8(1))
    cpu.mem.wb(cs, 0x5B9B, cpu.get_reg8(5))

    _call_hook_like_near_call(cpu, overkill_pack_four_pixels_45f6, 0x4575)
    cpu.mem.wb(cs, 0x5B96, cpu.get_reg8(1))
    cpu.mem.wb(cs, 0x5B9A, cpu.get_reg8(5))

    # INC SI. Its flags are overwritten by the following CMP or by the 45CB calls.
    old_si = cpu.s.si & 0xFFFF
    old_cf = cpu.get_flag(CF)
    cpu.s.si = (cpu.s.si + 1) & 0xFFFF
    cpu.set_add_flags(old_si, 1, old_si + 1, 16)
    cpu.set_flag(CF, old_cf)

    # CMP word ptr CS:[0BD6],0; JE 45A9
    transparent_enabled = cpu.mem.rw(cs, 0x0BD6) != 0
    cpu.set_sub_flags(cpu.mem.rw(cs, 0x0BD6), 0, cpu.mem.rw(cs, 0x0BD6), 16)

    if transparent_enabled:
        for addr, ret in ((0x5B98, 0x458F), (0x5B99, 0x4596), (0x5B9A, 0x459D), (0x5B9B, 0x45A4)):
            cpu.set_reg8(0, cpu.mem.rb(cs, addr))
            _call_hook_like_near_call(cpu, overkill_expand_bits_45cb, ret)
        cpu.s.ax = cpu.mem.rw(cs, 0x45E4)
        _stosw(cpu)

    for addr, ret in ((0x5B94, 0x45B0), (0x5B95, 0x45B7), (0x5B96, 0x45BE), (0x5B97, 0x45C5)):
        cpu.set_reg8(0, cpu.mem.rb(cs, addr))
        _call_hook_like_near_call(cpu, overkill_expand_bits_45cb, ret)
    cpu.s.ax = cpu.mem.rw(cs, 0x45E4)
    _stosw(cpu)

    cpu.s.ip = cpu.pop()


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
    cs = cpu.s.cs & 0xFFFF
    height = cpu.mem.rw(cs, 0x5B9E)
    width = cpu.mem.rw(cs, 0x5B9C)
    cpu.s.cx = height

    while cpu.s.cx != 0:
        outer_cx = cpu.s.cx & 0xFFFF
        cpu.push(outer_cx)
        cpu.s.cx = width

        while cpu.s.cx != 0:
            inner_cx = cpu.s.cx & 0xFFFF
            cpu.push(inner_cx)
            _call_hook_like_near_call(cpu, overkill_expand_4plane_row_4537, 0x4520)
            cpu.s.cx = cpu.pop()
            cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP col, flags unaffected.

        for _ in range(3):
            old_si = cpu.s.si & 0xFFFF
            cpu.s.si = (cpu.s.si + width) & 0xFFFF
            cpu.set_add_flags(old_si, width, old_si + width, 16)

        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP row, flags unaffected.

    cpu.s.ip = 0x450C


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
    """Replace the complete OVERKILL LZ-style asset decoder at 1010:ECF2.

    This is deliberately a conservative replacement of exactly the observed
    runtime routine, not a generic decompressor.  The code shape in the
    self-modified runtime is:

        ECF2  push es
        ECF3  zero CS:EDE5/EDE7 output counters
        ED01  les di, cs:[ECEE]
        ED06  clear one-byte pushback slot
        ED0C  si = 0; bp = 0
        ED12  clear dictionary words at CS:DCB8
        ED20  bp = 0FEE; dx = 0
        ED26  bitstream loop, literals/backrefs until 00 00 00 terminator
        ED95  pop es; ret

    The hook calls the already-verified ED97 input and EDE9 output helpers with
    synthetic near-call stack side effects.  It keeps the original ring buffer,
    output counters, segment wrapping, one-byte pushback escape, and termination
    flags.  It intentionally does not try to understand higher-level asset
    semantics yet.
    """
    cs = cpu.s.cs & 0xFFFF

    # ECF2: PUSH ES.  The original later restores ES at ED95 before RET.
    cpu.push(cpu.s.es)

    # ECF3..ED00: reset output byte counter dword.
    cpu.mem.ww(cs, 0xEDE5, 0)
    cpu.mem.ww(cs, 0xEDE7, 0)

    # ED01: LES DI, CS:[ECEE]
    cpu.s.di = cpu.mem.rw(cs, 0xECEE)
    cpu.s.es = cpu.mem.rw(cs, 0xECF0)

    # ED06..ED1E: reset pushback, input pointer, and most of the 4 KiB ring.
    cpu.mem.wb(cs, 0xEE04, 0)
    cpu.s.si = 0
    cpu.s.bp = 0
    cpu.s.cx = 0x07F7
    while cpu.s.cx != 0:
        cpu.mem.ww(cs, (0xDCB8 + cpu.s.bp) & 0xFFFF, 0)
        old_cf = cpu.get_flag(CF)
        old_bp = cpu.s.bp & 0xFFFF
        cpu.s.bp = (cpu.s.bp + 1) & 0xFFFF
        cpu.set_add_flags(old_bp, 1, old_bp + 1, 16)
        cpu.set_flag(CF, old_cf)
        old_cf = cpu.get_flag(CF)
        old_bp = cpu.s.bp & 0xFFFF
        cpu.s.bp = (cpu.s.bp + 1) & 0xFFFF
        cpu.set_add_flags(old_bp, 1, old_bp + 1, 16)
        cpu.set_flag(CF, old_cf)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unchanged.

    cpu.s.bp = 0x0FEE
    cpu.s.dx = 0

    # Hard safety guard: the original should terminate from the compressed
    # stream.  Hitting this indicates either bad test data or a wrong hook.
    guard = 0
    while True:
        guard += 1
        if guard > 1_000_000:
            raise RuntimeError("OVERKILL LZ decoder did not reach terminator")

        # ED26: SHR DX,1
        cpu.s.dx = cpu.shift(5, cpu.s.dx, 1, 16)

        # ED28: TEST DX,0100h; if zero, fetch a fresh flag byte into DL and set DH=FF.
        cpu.set_logic_flags(cpu.s.dx & 0x0100, 16)
        if (cpu.s.dx & 0x0100) == 0:
            _call_hook_like_near_call(cpu, overkill_lz_input_byte_ed97, 0xED31)
            cpu.set_reg8(2, cpu.get_reg8(0))  # DL = AL
            cpu.set_reg8(6, 0xFF)             # DH = FF

        # ED35: TEST DX,0001h
        cpu.set_logic_flags(cpu.s.dx & 0x0001, 16)
        if (cpu.s.dx & 0x0001) != 0:
            # Literal path ED3B..ED4B.
            _call_hook_like_near_call(cpu, overkill_lz_input_byte_ed97, 0xED3E)
            _call_hook_like_near_call(cpu, overkill_lz_output_byte_ede9, 0xED41)
            cpu.mem.wb(cs, (0xDCB8 + cpu.s.bp) & 0xFFFF, cpu.get_reg8(0))

            old_cf = cpu.get_flag(CF)
            old_bp = cpu.s.bp & 0xFFFF
            cpu.s.bp = (cpu.s.bp + 1) & 0xFFFF
            cpu.set_add_flags(old_bp, 1, old_bp + 1, 16)  # INC BP
            cpu.set_flag(CF, old_cf)
            cpu.s.bp &= 0x0FFF
            cpu.set_logic_flags(cpu.s.bp, 16)             # AND BP,0FFFh
            continue

        # Back-reference / terminator path ED4D..ED93.
        _call_hook_like_near_call(cpu, overkill_lz_input_byte_ed97, 0xED50)
        cpu.set_reg8(4, cpu.get_reg8(0))  # AH = AL
        _call_hook_like_near_call(cpu, overkill_lz_input_byte_ed97, 0xED55)
        al = cpu.get_reg8(0)
        ah = cpu.get_reg8(4)
        cpu.set_reg8(0, ah)               # XCHG AL,AH
        cpu.set_reg8(4, al)

        cpu.set_sub_flags(cpu.s.ax, 0, cpu.s.ax, 16)      # CMP AX,0
        if cpu.s.ax == 0:
            _call_hook_like_near_call(cpu, overkill_lz_input_byte_ed97, 0xED5F)
            cpu.set_sub_flags(cpu.get_reg8(0), 0, cpu.get_reg8(0), 8)  # CMP AL,0
            if cpu.get_reg8(0) == 0:
                # ED95: POP ES; RET.  Flags intentionally remain from CMP AL,0.
                cpu.s.es = cpu.pop()
                cpu.s.ip = cpu.pop()
                return
            # ED63 CALL EDDA; ED66 MOV AL,0.  EDDA changes no flags.
            cpu.mem.wb(cs, 0xEE04, 1)
            cpu.mem.wb(cs, 0xEE05, cpu.get_reg8(0))
            cpu.set_reg8(0, 0)

        # ED68..ED77: derive length and dictionary offset from AX.
        cpu.set_reg8(1, cpu.get_reg8(4))  # CL = AH
        for _ in range(4):
            cpu.set_reg8(4, cpu.shift(5, cpu.get_reg8(4), 1, 8))  # SHR AH,1
        cl = cpu.get_reg8(1) & 0x0F
        cpu.set_reg8(1, cl)
        cpu.set_logic_flags(cl, 8)        # AND CL,0Fh
        cpu.s.bx = cpu.s.ax & 0xFFFF
        old_cl = cpu.get_reg8(1)
        new_cl = old_cl + 3
        cpu.set_reg8(1, new_cl)
        cpu.set_add_flags(old_cl, 3, new_cl, 8)  # ADD CL,3

        # ED7A is a loop body ending in JMP ED26, not a RETing helper.
        # Call it directly so it does not leave a synthetic return word on the stack.
        overkill_lz_backref_copy_ed7a(cpu)

@registry.replace(0x1010, 0xECF2, "overkill_lz_decoder_ecf2")
def overkill_lz_decoder_ecf2(cpu):
    """Optimized full replacement for OVERKILL's 1010:ECF2 LZ asset decoder.

    This supersedes the first conservative version above.  It keeps the same
    externally verified behavior, but inlines byte input, byte output, and
    back-reference copying so a whole compressed asset can complete in one hook
    invocation without spending minutes in nested Python call/flag overhead.
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

@registry.replace(0x1010, 0x0367, "overkill_linear_byte_rle_decoder_0367")
def overkill_linear_byte_rle_decoder_0367(cpu):
    """Replace the linear byte-RLE startup decoder at 1010:0367.

    This is the horizontal/linear sibling of the already-verified 03A8 vertical
    decoder.  It writes bytes to ES:DI with normal STOSB advancement until a
    control byte of 80h jumps to the shared continuation at 1010:02A8.
    """
    ds = cpu.s.ds & 0xFFFF
    cpu.s.es = cpu.mem.rw(ds, 0x023A)
    cpu.s.di = cpu.mem.rw(ds, 0x023C)

    guard = 0
    while True:
        guard += 1
        if guard > 1_000_000:
            raise RuntimeError("OVERKILL 0367 byte RLE did not reach terminator")

        _overkill_read_packed_byte(cpu)
        if cpu.s.ip == 0x02B2:
            return
        control = cpu.get_reg8(0)
        cpu.set_sub_flags(control, 0x80, control - 0x80, 8)  # CMP AL,80h

        if control == 0x80:
            cpu.s.ip = 0x02A8
            return

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
                cpu.s.di = (cpu.s.di + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF
                _inc_mem_word_preserve_cf(cpu, ds, 0x0244)
                _dec_reg8_preserve_cf(cpu, 4)  # DEC AH
                if cpu.get_flag(0x0080):       # JNS not taken when SF=1
                    break
            continue

        # Literal run: PUSH AX; CALL 0624; STOSB; INC [0244]; POP AX; DEC AL; JNS
        while True:
            saved_ax = cpu.s.ax & 0xFFFF
            _overkill_read_packed_byte(cpu)
            if cpu.s.ip == 0x02B2:
                return
            cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.get_reg8(0))
            cpu.s.di = (cpu.s.di + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF
            _inc_mem_word_preserve_cf(cpu, ds, 0x0244)
            cpu.s.ax = saved_ax
            _dec_reg8_preserve_cf(cpu, 0)  # DEC AL
            if cpu.get_flag(0x0080):       # JNS not taken when SF=1
                break

@registry.replace(0x1010, 0x0367, "overkill_linear_byte_rle_decoder_0367_fast")
def overkill_linear_byte_rle_decoder_0367(cpu):
    """Optimized verified replacement for 1010:0367 linear byte-RLE decoder.

    The earlier implementation was a direct translation that called the packed
    byte-reader hook for every byte and updated flags for every output byte.
    This version preserves the same externally observed state but collapses each
    literal/repeat run into a small Python loop, which matters because the real
    startup stream can contain very large images.
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

def _r_rol8(cpu, v: int) -> int:
    old = v & 0xFF
    res = ((old << 1) | (old >> 7)) & 0xFF
    cpu.set_flag(CF, bool(old & 0x80))
    cpu.set_flag(ZF, res == 0); cpu.set_flag(SF, bool(res & 0x80)); cpu.set_flag(PF, cpu.parity(res))
    return res


def _r_ror8(cpu, v: int) -> int:
    old = v & 0xFF
    res = ((old >> 1) | ((old & 1) << 7)) & 0xFF
    cpu.set_flag(CF, bool(old & 1))
    cpu.set_flag(ZF, res == 0); cpu.set_flag(SF, bool(res & 0x80)); cpu.set_flag(PF, cpu.parity(res))
    return res


def _r_rcl8(cpu, v: int) -> int:
    old = v & 0xFF
    old_cf = 1 if cpu.get_flag(CF) else 0
    res = ((old << 1) | old_cf) & 0xFF
    cpu.set_flag(CF, bool(old & 0x80))
    cpu.set_flag(ZF, res == 0); cpu.set_flag(SF, bool(res & 0x80)); cpu.set_flag(PF, cpu.parity(res))
    return res


def _r_rcl16_mem(cpu, cs: int, off: int) -> None:
    mem = cpu.mem
    old = mem.rw(cs, off)
    old_cf = 1 if cpu.get_flag(CF) else 0
    res = ((old << 1) | old_cf) & 0xFFFF
    mem.ww(cs, off, res)
    cpu.set_flag(CF, bool(old & 0x8000))
    cpu.set_flag(ZF, res == 0); cpu.set_flag(SF, bool(res & 0x8000)); cpu.set_flag(PF, cpu.parity(res))


def _r_pack_four_pixels(cpu, cs: int) -> None:
    """Module-level lift of 4537's per-row pack helper (45F6 family).

    Gathers the low bits of the four plane bytes (DH,DL,AH,AL) into CL via the
    ROR/RCL bit chain, applies the optional transparency test against CS:[0BD6]/
    CS:[0000], then remaps the nibbles through the CS:45E6 colour table.  Lifted
    out of the hook body so it is defined once instead of as a per-call closure.
    """
    mem = cpu.mem
    for reg in (6, 2, 4, 0, 6, 2, 4, 0):
        cpu.set_reg8(reg, _r_ror8(cpu, cpu.get_reg8(reg)))
        cpu.set_reg8(1, _r_rcl8(cpu, cpu.get_reg8(1)))
    for _ in range(4):
        cpu.set_reg8(1, _r_ror8(cpu, cpu.get_reg8(1)))

    original_ax = cpu.s.ax & 0xFFFF
    cl = cpu.get_reg8(1)
    ch = cpu.get_reg8(5)
    if mem.rw(cs, 0x0BD6) != 0:
        ch = 0
        transparent_color = mem.rb(cs, 0x0000)
        low = cl & 0x0F
        if low == transparent_color:
            ch |= 0x0F
            cl &= 0xF0
        high = (cl >> 4) & 0x0F
        if high == transparent_color:
            ch |= 0xF0
            cl &= 0x0F

    mem.ww(cs, 0x45E2, original_ax)
    table = 0x45E6
    low_mapped = mem.rb(cs, table + (cl & 0x0F))
    high_mapped = mem.rb(cs, table + ((cl >> 4) & 0x0F))
    mapped = ((high_mapped << 4) | low_mapped) & 0xFF
    cpu.set_logic_flags(mapped, 8)
    cpu.s.bx = table
    cpu.set_reg8(1, mapped)
    cpu.set_reg8(5, ch)
    cpu.s.ax = original_ax


def _r_expand_bits(cpu, cs: int, value: int) -> None:
    """Module-level lift of 4537's per-byte bit-spread helper (45CB family)."""
    al = value & 0xFF
    for _ in range(2):
        for _ in range(3):
            al = _r_rol8(cpu, al)
        cpu.set_reg8(0, al)
        _r_rcl16_mem(cpu, cs, 0x45E4)
        al = _r_rol8(cpu, al)
        cpu.set_reg8(0, al)
        _r_rcl16_mem(cpu, cs, 0x45E4)
    cpu.set_reg8(0, al)


@registry.replace(0x1010, 0x4537, "overkill_expand_4plane_row_4537_fast")
def overkill_expand_4plane_row_4537(cpu):
    """Optimized verified replacement for 1010:4537 4-plane row expansion.

    Keeps the exact row semantics of the earlier hook and removes the synthetic
    CALL/RET overhead of repeatedly invoking the 45F6 and 45CB helpers.  The
    per-bit rotate / pack / expand helpers are now module-level functions
    (``_r_*``) rather than closures rebuilt on every call, which makes the lifted
    source clearer and lets them be reused/tested independently.  Registers,
    flags and memory are unchanged; re-verified bit-identical against the prior
    implementation by a 3000-state differential fuzz and the existing oracle test
    ``test_expand_4plane_row_4537_hook_matches_interpreted_asm``.
    """
    cs = cpu.s.cs & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    width = mem.rw(cs, 0x5B9C)
    cpu.s.bx = width
    cpu.set_reg8(0, mem.rb(ds, cpu.s.si))
    cpu.set_reg8(4, mem.rb(ds, (cpu.s.si + cpu.s.bx) & 0xFFFF))
    cpu.s.bx = (cpu.s.bx << 1) & 0xFFFF
    cpu.set_reg8(2, mem.rb(ds, (cpu.s.si + cpu.s.bx) & 0xFFFF))
    cpu.s.bx = (cpu.s.bx + width) & 0xFFFF
    cpu.set_reg8(6, mem.rb(ds, (cpu.s.si + cpu.s.bx) & 0xFFFF))

    _r_pack_four_pixels(cpu, cs)
    mem.wb(cs, 0x5B95, cpu.get_reg8(1)); mem.wb(cs, 0x5B99, cpu.get_reg8(5))
    _r_pack_four_pixels(cpu, cs)
    mem.wb(cs, 0x5B94, cpu.get_reg8(1)); mem.wb(cs, 0x5B98, cpu.get_reg8(5))
    _r_pack_four_pixels(cpu, cs)
    mem.wb(cs, 0x5B97, cpu.get_reg8(1)); mem.wb(cs, 0x5B9B, cpu.get_reg8(5))
    _r_pack_four_pixels(cpu, cs)
    mem.wb(cs, 0x5B96, cpu.get_reg8(1)); mem.wb(cs, 0x5B9A, cpu.get_reg8(5))

    old_si = cpu.s.si & 0xFFFF
    old_cf = cpu.get_flag(CF)
    cpu.s.si = (cpu.s.si + 1) & 0xFFFF
    cpu.set_add_flags(old_si, 1, old_si + 1, 16)
    cpu.set_flag(CF, old_cf)

    bd6 = mem.rw(cs, 0x0BD6)
    cpu.set_sub_flags(bd6, 0, bd6, 16)
    if bd6 != 0:
        for addr in (0x5B98, 0x5B99, 0x5B9A, 0x5B9B):
            _r_expand_bits(cpu, cs, mem.rb(cs, addr))
        cpu.s.ax = mem.rw(cs, 0x45E4)
        _stosw(cpu)

    for addr in (0x5B94, 0x5B95, 0x5B96, 0x5B97):
        _r_expand_bits(cpu, cs, mem.rb(cs, addr))
    cpu.s.ax = mem.rw(cs, 0x45E4)
    _stosw(cpu)
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
        cpu.s.ax = (old_ax + 1) & 0xFFFF
        cpu.set_add_flags(old_ax, 1, old_ax + 1, 16)  # INC AX; CF preserved by helper? set_add sets CF, so fix below.
        # INC does not affect CF on 8086.  set_add_flags updated it, so restore the
        # CF from the previous CMP path.  ZF/SF/PF/AF/OF are the live bits here.
        # The old CF after CMP bd8,0 is false when bd8==0 and also false for bd8>0
        # in normal startup, but preserve it explicitly for tests/future cases.
        # Recompute INC flags with preserved CF by applying add flags then restoring.
        # (See the helper below for a clearer version used in future hooks.)

        # Correct CF preservation for INC AX.
        prev_cf = bd8 < 0  # placeholder overwritten immediately below
        # The CF before INC is the CF left by CMP CS:0BD8,0.
        prev_cf = cpu.mem.rw(cs, 0x0BD8) < 0  # always false for unsigned word, kept explicit.
        cpu.set_flag(CF, prev_cf)

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
        if si + count <= 0x10000 and di + count <= 0x10000:
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
        if di + count <= 0x10000:
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
    """
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    delta = -2 if cpu.get_flag(DF) else 2
    cs = cpu.s.cs & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    es = cpu.s.es & 0xFFFF

    def lodsw() -> int:
        value = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + delta) & 0xFFFF
        cpu.s.ax = value
        return value

    while iterations:
        word0 = lodsw()
        cpu.s.bx = word0 & 0xFFFF
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1
        _add_reg16(cpu, 3, 0x9A08)                # ADD BX,9A08h
        cpu.s.bx = cpu.mem.rw(ds, cpu.s.bx)
        _add_reg16(cpu, 3, cpu.mem.rw(ds, 0x234C))
        word1 = lodsw()
        _add_reg16(cpu, 3, word1)
        marker_word = lodsw()
        marker = marker_word & 0xFF

        cell = cpu.mem.rb(es, cpu.s.bx)
        _cmp_byte(cpu, cell, 0)
        should_store = False
        include_4e = False
        if cpu.get_flag(ZF):
            mode = cpu.mem.rw(cs, 0x95BC)
            _cmp_word(cpu, mode, 1)
            if not cpu.get_flag(ZF):
                should_store = True
            else:
                for off in (0x1A, 0x34, 0x4E):
                    value = cpu.mem.rb(es, (cpu.s.bx + off) & 0xFFFF)
                    _cmp_byte(cpu, value, 0)
                    if not cpu.get_flag(ZF):
                        break
                else:
                    should_store = True
                    include_4e = (cpu.s.bp & 0xFFFF) == 0x4D4D

        if should_store:
            if include_4e:
                cpu.mem.wb(es, (cpu.s.bx + 0x4E) & 0xFFFF, marker)
            # BP=4D4D jumps to 4D4D; BP=4D51 jumps to 4D51.  Both paths fall
            # through these lower-layer stores.  For any future BP value outside
            # the known caller pattern, return to the original dynamic target.
            if (cpu.s.bp & 0xFFFF) not in (0x4D4D, 0x4D51):
                cpu.s.ip = cpu.s.bp & 0xFFFF
                return
            cpu.mem.wb(es, (cpu.s.bx + 0x34) & 0xFFFF, marker)
            cpu.mem.wb(es, (cpu.s.bx + 0x1A) & 0xFFFF, marker)
            cpu.mem.wb(es, cpu.s.bx, marker)
            cpu.mem.ww(ds, cpu.s.di, cpu.s.bx)
            _add_reg16(cpu, 7, 2)

        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        iterations -= 1

    cpu.s.ip = cpu.pop()

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







@registry.replace(0x1010, 0x280D, "overkill_ega_load_temp_rows_280d")
def overkill_ega_load_temp_rows_280d(cpu):
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
    """Replace the hot EGA temp-row expansion/copy block at 1010:2824.

    This block converts four temporary 1bpp-ish rows at CS:5AF4/5B1C/5B44/5B6C
    into four EGA output-plane rows, applies OVERKILL's transparent-colour rule,
    then copies the four rows to the destination cursor tracked in CS:5BA6.  It
    is an internal block of the mode-1 renderer, not a subroutine: the hook ends
    at the same control-flow targets as the original ``LOOP/JMP`` tail
    (``27EB`` for another source row, ``27D9`` for the next object/list entry).
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    width = mem.rw(cs, 0x5B9C)
    if width == 0:
        width = 0x10000

    cpu.s.di = 0x5AF4
    base_di = cpu.s.di & 0xFFFF
    data = mem.data
    cs_base = cs << 4

    for col in range(width):
        # Final column PUSH CX scratch.  The column loop's push/pop pair leaves
        # the last pushed count in the word below SP.
        mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, (width - col) & 0xFFFF)

        cpu.set_reg8(0, data[(cs_base + cpu.s.di) & 0xFFFFF])                         # AL
        cpu.set_reg8(4, data[(cs_base + ((cpu.s.di + 0x28) & 0xFFFF)) & 0xFFFFF])      # AH
        cpu.set_reg8(2, data[(cs_base + ((cpu.s.di + 0x50) & 0xFFFF)) & 0xFFFFF])      # DL
        cpu.set_reg8(6, data[(cs_base + ((cpu.s.di + 0x78) & 0xFFFF)) & 0xFFFFF])      # DH
        cpu.s.cx = 8

        while cpu.s.cx != 0:
            cpu.set_reg8(6, cpu.shift(0, cpu.get_reg8(6), 1, 8))       # ROL DH,1
            cpu.set_reg8(3, cpu.shift(2, cpu.get_reg8(3), 1, 8))       # RCL BL,1
            cpu.set_reg8(2, cpu.shift(0, cpu.get_reg8(2), 1, 8))       # ROL DL,1
            cpu.set_reg8(3, cpu.shift(2, cpu.get_reg8(3), 1, 8))       # RCL BL,1
            cpu.set_reg8(4, cpu.shift(0, cpu.get_reg8(4), 1, 8))       # ROL AH,1
            cpu.set_reg8(3, cpu.shift(2, cpu.get_reg8(3), 1, 8))       # RCL BL,1
            cpu.set_reg8(0, cpu.shift(0, cpu.get_reg8(0), 1, 8))       # ROL AL,1
            cpu.set_reg8(3, cpu.shift(2, cpu.get_reg8(3), 1, 8))       # RCL BL,1

            bl = cpu.get_reg8(3) & 0x0F
            cpu.set_reg8(3, bl)
            cpu.set_logic_flags(bl, 8)                                # AND BL,0Fh

            _cmp_word(cpu, mem.rw(cs, 0x0BD6), 0)
            if not cpu.get_flag(ZF):
                _cmp_byte(cpu, cpu.get_reg8(3), mem.rb(cs, 0x0000))
                if cpu.get_flag(ZF):
                    cpu.set_reg8(3, 0)
                    cpu.set_logic_flags(0, 8)                          # XOR BL,BL

            _cmp_byte(cpu, mem.rb(cs, 0xC5B0), 1)
            if cpu.get_flag(ZF):
                cpu.s.bp = mem.rw(cs, 0x5BAA)
                _cmp_word(cpu, cpu.s.bp, 0xFFFF)
                if not cpu.get_flag(ZF):
                    _add_reg16(cpu, 5, mem.rw(cs, 0x5BA8))
                    marker = mem.rb(cpu.s.ss, cpu.s.bp)
                    _cmp_byte(cpu, marker, 1)
                    if cpu.get_flag(ZF):
                        if cpu.get_reg8(3) == 0x06:
                            _cmp_byte(cpu, cpu.get_reg8(3), 0x06)
                            cpu.set_reg8(3, 0x06)
                        elif cpu.get_reg8(3) == 0x0C:
                            _cmp_byte(cpu, cpu.get_reg8(3), 0x0C)
                            cpu.set_reg8(3, 0x0C)
                    else:
                        _cmp_byte(cpu, marker, 2)
                        if cpu.get_flag(ZF):
                            if cpu.get_reg8(3) == 0x06:
                                _cmp_byte(cpu, cpu.get_reg8(3), 0x06)
                                cpu.set_reg8(3, 0x0C)
                            elif cpu.get_reg8(3) == 0x0C:
                                _cmp_byte(cpu, cpu.get_reg8(3), 0x0C)
                                cpu.set_reg8(3, 0x06)

            cpu.set_reg8(3, cpu.shift(5, cpu.get_reg8(3), 1, 8))
            mem.wb(cs, 0x5BA2, cpu.shift(2, mem.rb(cs, 0x5BA2), 1, 8))
            cpu.set_reg8(3, cpu.shift(5, cpu.get_reg8(3), 1, 8))
            mem.wb(cs, 0x5BA3, cpu.shift(2, mem.rb(cs, 0x5BA3), 1, 8))
            cpu.set_reg8(3, cpu.shift(5, cpu.get_reg8(3), 1, 8))
            mem.wb(cs, 0x5BA4, cpu.shift(2, mem.rb(cs, 0x5BA4), 1, 8))
            cpu.set_reg8(3, cpu.shift(5, cpu.get_reg8(3), 1, 8))
            mem.wb(cs, 0x5BA5, cpu.shift(2, mem.rb(cs, 0x5BA5), 1, 8))

            cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF                         # LOOP, no flags

        data[(cs_base + cpu.s.di) & 0xFFFFF] = mem.rb(cs, 0x5BA2)
        data[(cs_base + ((cpu.s.di + 0x28) & 0xFFFF)) & 0xFFFFF] = mem.rb(cs, 0x5BA3)
        data[(cs_base + ((cpu.s.di + 0x50) & 0xFFFF)) & 0xFFFFF] = mem.rb(cs, 0x5BA4)
        data[(cs_base + ((cpu.s.di + 0x78) & 0xFFFF)) & 0xFFFFF] = mem.rb(cs, 0x5BA5)
        _inc_reg16_preserve_cf(cpu, 7)                                  # INC DI

    # Copy the four converted temporary rows to ES:[CS:5BA6].  This inlines the
    # verified 291C helper without manufacturing CALL/RET stack effects.
    def copy_temp_row(start: int, return_ip: int) -> None:
        count = mem.rw(cs, 0x5B9C)
        if count == 0:
            count = 0x10000
        src_di = start & 0xFFFF
        out_di = mem.rw(cs, 0x5BA6)
        cpu.s.di = src_di
        # Mirror CALL 291C plus the helper's final PUSH CX/PUSH DI scratches.
        mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, return_ip & 0xFFFF)
        mem.ww(cpu.s.ss, (cpu.s.sp - 4) & 0xFFFF, 0x0001)
        mem.ww(cpu.s.ss, (cpu.s.sp - 6) & 0xFFFF, (src_di + count) & 0xFFFF)
        for _ in range(count):
            cpu.set_reg8(0, mem.rb(cs, cpu.s.di))
            _inc_reg16_preserve_cf(cpu, 7)  # mirror INC DI flags on the source pointer
            src_di = cpu.s.di & 0xFFFF
            mem.wb(cpu.s.es, out_di, cpu.get_reg8(0))
            out_di = (out_di + 1) & 0xFFFF
        mem.ww(cs, 0x5BA6, out_di)
        cpu.s.di = src_di
        cpu.s.cx = 0

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
    dst_base = (cpu.s.es & 0xFFFF) << 4
    data = mem.data
    for i in range(count):
        al = data[(src_base + source_di) & 0xFFFFF]
        source_di = (source_di + 1) & 0xFFFF
        last_source_di = source_di
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
    """Replace the hot EGA transparency-mask builder at 1010:2932.

    The routine reads four source plane bytes for one 8-pixel group, reconstructs
    each 4-bit colour index through the same RCL chain as the original ASM, and
    emits one mask byte to ES:DI.  A mask bit is 1 when the reconstructed colour
    equals OVERKILL's transparent colour at ``CS:0000``.

    This is intentionally still a narrow renderer hook.  It does not invent any
    high-level sprite semantics; it only collapses the exact 2932..2990 bit loop
    that dominates EGA startup profiles.
    """
    cs = cpu.s.cs & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    mem.wb(cs, 0x5BA0, 0x00)
    width = mem.rw(cs, 0x5B9C)
    si = cpu.s.si & 0xFFFF

    cpu.s.bx = width & 0xFFFF
    cpu.set_reg8(0, mem.rb(ds, si))                               # AL
    cpu.set_reg8(4, mem.rb(ds, (si + cpu.s.bx) & 0xFFFF))          # AH
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)                       # SHL BX,1
    cpu.set_reg8(2, mem.rb(ds, (si + cpu.s.bx) & 0xFFFF))          # DL
    _add_reg16(cpu, 3, width)                                      # ADD BX,CS:[5B9C]
    cpu.set_reg8(6, mem.rb(ds, (si + cpu.s.bx) & 0xFFFF))          # DH

    # The original uses PUSH CX inside the eight-iteration loop.  After the
    # final POP, the scratch word below SP still contains 0001h.
    mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, 0x0001)

    for _ in range(8):
        cpu.set_reg8(6, cpu.shift(2, cpu.get_reg8(6), 1, 8))        # RCL DH,1
        mem.wb(cs, 0x5BA1, cpu.shift(2, mem.rb(cs, 0x5BA1), 1, 8))
        cpu.set_reg8(2, cpu.shift(2, cpu.get_reg8(2), 1, 8))        # RCL DL,1
        mem.wb(cs, 0x5BA1, cpu.shift(2, mem.rb(cs, 0x5BA1), 1, 8))
        cpu.set_reg8(4, cpu.shift(2, cpu.get_reg8(4), 1, 8))        # RCL AH,1
        mem.wb(cs, 0x5BA1, cpu.shift(2, mem.rb(cs, 0x5BA1), 1, 8))
        cpu.set_reg8(0, cpu.shift(2, cpu.get_reg8(0), 1, 8))        # RCL AL,1
        mem.wb(cs, 0x5BA1, cpu.shift(2, mem.rb(cs, 0x5BA1), 1, 8))

        masked = mem.rb(cs, 0x5BA1) & 0x0F
        mem.wb(cs, 0x5BA1, masked)
        cpu.set_logic_flags(masked, 8)                             # AND flags
        transparent = mem.rb(cs, 0x0000)
        cpu.set_reg8(1, transparent)                                # MOV CL,CS:[0000]
        _cmp_byte(cpu, mem.rb(cs, 0x5BA1), transparent)
        cpu.set_flag(CF, mem.rb(cs, 0x5BA1) == transparent)         # STC when transparent, CLC otherwise
        mem.wb(cs, 0x5BA0, cpu.shift(2, mem.rb(cs, 0x5BA0), 1, 8))

    cpu.set_reg8(0, mem.rb(cs, 0x5BA0))                             # MOV AL,[5BA0]
    mem.wb(cpu.s.es, cpu.s.di, cpu.get_reg8(0))                     # STOSB
    cpu.s.di = (cpu.s.di + 1) & 0xFFFF
    cpu.s.cx = 0
    _inc_reg16_preserve_cf(cpu, 6)                                  # INC SI
    cpu.s.ip = cpu.pop()


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
            cpu.s.ax = 0x0004
            _out_dx_ax(cpu)
            for plane in range(4):
                cpu.s.cx = 0x0028
                _rep_movsb(cpu, cpu.s.cx)
                if plane != 3:
                    _sub_reg16(cpu, 6, 0x0028)
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
        if si + byte_count <= 0x10000 and di + byte_count <= 0x10000:
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
    """Replace the EGA mode-1 frame-present blit at 1010:2750.

    The real routine writes the same A000h offsets four times while changing the
    EGA sequencer map-mask register (03C4h index 02h / 03C5h data 1,2,4,8).
    A plain bytearray cannot represent those hardware bitplanes, so this hook
    stores the currently presented frame in an explicit shadow layout inside the
    A000h aperture:

        A000:0000  plane 0, 40 bytes * 200 rows
        A000:2000  plane 1
        A000:4000  plane 2
        A000:6000  plane 3

    ``scripts/render_cga.py`` / ``scripts/play.py`` decode that shadow layout as
    320x200 16-colour EGA.  The copied source bytes and the register flow mirror
    the original routine; this is deliberately only the final presenter, not a
    broad VGA/EGA hardware emulator.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    data = mem.data

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

    src_base = (cpu.s.ds & 0xFFFF) << 4
    dst_base = (cpu.s.es & 0xFFFF) << 4
    plane_stride = 0x2000
    width = 0x001A

    while True:
        cpu.set_reg8(0, 0x01)
        _out_dx_al(cpu)
        row_di = cpu.s.di & 0xFFFF
        for plane in range(4):
            src = (src_base + (cpu.s.si & 0xFFFF)) & 0xFFFFF
            dst = (dst_base + plane * plane_stride + row_di) & 0xFFFFF
            # Original plane copy is REP MOVSW with BX=000Dh: 26 bytes.
            # MOVS changes SI/DI/CX but not flags.
            data[dst:dst + width] = data[src:src + width]
            cpu.s.si = (cpu.s.si + width) & 0xFFFF
            cpu.s.di = (cpu.s.di + width) & 0xFFFF
            cpu.s.cx = 0
            if plane != 3:
                _sub_reg16(cpu, 7, width)
                cpu.set_reg8(0, cpu.shift(4, cpu.get_reg8(0), 1, 8))
                _out_dx_al(cpu)
        _add_reg16(cpu, 7, 0x000E)  # Net row stride: 26 copied bytes + 14 = 40.
        _dec_reg16_preserve_cf(cpu, 5)
        if cpu.get_flag(ZF):
            break

    cpu.set_reg8(0, 0x0F)
    _out_dx_al(cpu)
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
            raise RuntimeError(f"58DF hook currently verified only for mode 0, got {mode:04X}")
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
