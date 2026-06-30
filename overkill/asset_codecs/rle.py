"""OVERKILL startup RLE asset decoders.

This module contains the loader/materialization routines at 1010:0324,
1010:03A8, and 1010:0367.  They decode OVERKILL's packed loader streams into
ES:DI targets selected by DS:023A/DS:023C.  The implementations are readable
Python, but the boundary behavior remains ASM-compatible: error jumps, register
shuffles, preserved CF on INC/DEC, and the shared continuation at 1010:02A8 are
intentionally preserved.
"""
from __future__ import annotations

from dos_re.cpu import CF, DF

from .asm_adapters import (
    OVERKILL_LOAD_DISPATCH_CONTINUATION_IP,
    OVERKILL_LOAD_ERROR_IP,
    dec_reg8_preserve_cf,
    inc_mem_word_preserve_cf,
    linear_addr,
)
from .packed_stream import read_packed_byte, read_packed_word_le


def _stosw(cpu, value: int | None = None) -> None:
    if value is None:
        value = cpu.s.ax
    cpu.mem.ww(cpu.s.es, cpu.s.di, value)
    cpu.s.di = (cpu.s.di + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF


def _add_mem_word(cpu, seg: int, off: int, value: int) -> None:
    old = cpu.mem.rw(seg, off)
    result = old + value
    cpu.mem.ww(seg, off, result & 0xFFFF)
    cpu.set_add_flags(old, value, result, 16)


def _add_mem_word_repeated(cpu, seg: int, off: int, value: int, count: int) -> None:
    count &= 0xFFFF
    if count == 0:
        return
    old = cpu.mem.rw(seg, off)
    final_old = (old + value * (count - 1)) & 0xFFFF
    final_result = final_old + value
    cpu.mem.ww(seg, off, (old + value * count) & 0xFFFF)
    cpu.set_add_flags(final_old, value, final_result, 16)


def decode_word_pair_rle_words(words) -> list[int]:
    """Pure 1010:0324 word-pair RLE decode: an input word stream -> the decoded word list.

    The dual-mode form of :func:`decode_word_pair_rle` (the cpu/VM hook), with the VM mechanics
    stripped: it takes the already-unpacked input words (the hook's ``read_packed_word_le`` source) and
    returns the output words (the hook's ``STOSW`` sequence), so the standalone loader can decode an
    asset blob with no VM.  The algorithm is the hook's, verified against the ASM:

    * the first word is the sentinel ``marker``;
    * a word != marker is a literal pair: it and the following word are emitted;
    * the marker introduces a repeat count -- count 0 terminates, else the following two words are the
      pair emitted ``count`` times.
    """
    it = iter(words)
    marker = next(it) & 0xFFFF
    out: list[int] = []
    while True:
        word0 = next(it) & 0xFFFF
        if word0 != marker:
            out.append(word0)
            out.append(next(it) & 0xFFFF)
            continue
        count = next(it) & 0xFFFF
        if count == 0:
            return out
        pair0 = next(it) & 0xFFFF
        pair1 = next(it) & 0xFFFF
        for _ in range(count):
            out.append(pair0)
            out.append(pair1)


def decode_word_pair_rle(cpu) -> None:
    """Hook body for 1010:0324 word-pair RLE decoder.

    The stream starts with a sentinel word.  Non-sentinel words are literal
    first words followed by a second literal word.  A sentinel word introduces a
    repeat count; count zero terminates at the common loader dispatcher, and any
    nonzero count is followed by the two-word pair to repeat.
    """
    ds = cpu.s.ds & 0xFFFF
    cpu.s.es = cpu.mem.rw(ds, 0x023A)
    cpu.s.di = cpu.mem.rw(ds, 0x023C)

    def read_word_from_call(return_ip: int) -> None:
        # return_ip is the original CALL's return word; it ends up as dead stack
        # scratch below SP, which the oracle no longer compares, so we don't
        # model it.  (TODO Phase 3: inline this into read_packed_word_le.)
        read_packed_word_le(cpu)

    read_word_from_call(0x032F)
    if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
        return
    marker = cpu.s.ax & 0xFFFF
    cpu.s.bx = marker

    guard = 0
    while True:
        guard += 1
        if guard > 1_000_000:
            raise RuntimeError("OVERKILL 0324 word-pair RLE did not reach terminator")

        read_word_from_call(0x0334)
        if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
            return
        word0 = cpu.s.ax & 0xFFFF
        cpu.set_sub_flags(word0, cpu.s.bx, word0 - cpu.s.bx, 16)  # CMP AX,BX
        if word0 != cpu.s.bx:
            _stosw(cpu, word0)
            read_word_from_call(0x033C)
            if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
                return
            _stosw(cpu)
            _add_mem_word(cpu, ds, 0x0244, 4)
            continue

        read_word_from_call(0x0347)
        if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
            return
        cpu.s.cx = cpu.s.ax & 0xFFFF
        if cpu.s.cx == 0:
            cpu.s.ip = OVERKILL_LOAD_DISPATCH_CONTINUATION_IP
            return

        read_word_from_call(0x0353)
        if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
            return
        pair0 = cpu.s.ax & 0xFFFF
        cpu.push(pair0)
        read_word_from_call(0x0357)
        if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
            return
        pair1 = cpu.s.ax & 0xFFFF
        cpu.s.dx = pair1
        cpu.s.ax = cpu.pop()

        count = cpu.s.cx & 0xFFFF
        for _ in range(count):
            _stosw(cpu, cpu.s.ax)
            cpu.s.ax, cpu.s.dx = cpu.s.dx, cpu.s.ax
            _stosw(cpu, cpu.s.ax)
            cpu.s.ax, cpu.s.dx = cpu.s.dx, cpu.s.ax
        _add_mem_word_repeated(cpu, ds, 0x0244, 4, count)
        cpu.s.cx = 0


def decode_linear_byte_rle_bytes(stream) -> bytes:
    """Pure 1010:0367 linear byte-RLE decode: an input byte stream -> the decoded bytes.

    The dual-mode form of :func:`decode_linear_byte_rle` (the cpu/VM hook), VM mechanics stripped
    (ES:DI STOSB, the DOS refill, the NEG/XCHG register dance, error-IP).  The control byte selects:

    * ``< 0x80`` -- a literal run of ``control + 1`` bytes (each read from the stream);
    * ``== 0x80`` -- terminator;
    * ``> 0x80`` -- a repeat run of ``((-control) & 0xFF) + 1`` copies of the next byte.

    Algorithm is the hook's, verified against the ASM.
    """
    it = iter(stream)
    out = bytearray()
    while True:
        control = next(it) & 0xFF
        if control == 0x80:
            return bytes(out)
        if control > 0x80:
            count = ((-control) & 0xFF) + 1
            value = next(it) & 0xFF
            out.extend(value for _ in range(count))
        else:  # control < 0x80 -- literal run of control + 1 bytes
            for _ in range(control + 1):
                out.append(next(it) & 0xFF)


def decode_vertical_rle_columns_writes(stream) -> list[tuple[int, int]]:
    """Pure 1010:03A8 vertical byte-RLE decode: an input byte stream -> ``(offset, byte)`` writes.

    The dual-mode form of :func:`decode_vertical_rle_columns` (the cpu/VM hook), VM mechanics stripped
    (ES:DI STOSB at a vertical stride, the DOS refill, the NEG/XCHG dance, error-IP).  The stream is a
    3-word header (read little-endian) followed by per-column control bytes; the second header word is
    the vertical ``stride`` and also the column count.  For each column ``c`` (0..stride-1) the decoder
    fills *down* the column -- byte row ``r`` lands at ``di`` offset ``c + r*stride`` -- via the same RLE
    as the linear byte codec (``< 0x80`` literal run of ``control+1``; ``== 0x80`` ends the column;
    ``> 0x80`` repeat ``((-control) & 0xFF) + 1`` copies of the next byte), then moves to column ``c+1``.

    Returns the writes relative to ``di = 0`` (the caller adds its ES:DI base).  Algorithm is the hook's,
    verified against the ASM.
    """
    it = iter(stream)

    def rb() -> int:
        return next(it) & 0xFF

    def rw() -> int:
        lo = rb()
        return lo | (rb() << 8)

    rw()                 # header word 0 (CS:03A2) -- not used by the decode geometry
    stride = rw()        # header word 1 (DS:03A4) -- vertical stride AND column count
    rw()                 # header word 2 (DS:03A6) -- not used by the decode geometry

    writes: list[tuple[int, int]] = []
    for c in range(stride):
        r = 0
        while True:
            control = rb()
            if control == 0x80:
                break
            if control > 0x80:
                count = ((-control) & 0xFF) + 1
                value = rb()
                for _ in range(count):
                    writes.append((c + r * stride, value))
                    r += 1
            else:
                for _ in range(control + 1):
                    writes.append((c + r * stride, rb()))
                    r += 1
    return writes


def decode_vertical_rle_columns(cpu) -> None:
    """Hook body for 1010:03A8 vertical byte-RLE decoder.

    The routine is not a normal near function.  Successful completion jumps to
    the common loader dispatcher continuation at 1010:02A8.  The header words are
    read through the packed byte reader, because DOS refill side effects are
    observable by the original code.
    """
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF

    cpu.s.es = cpu.mem.rw(ds, 0x023A)
    start_di = cpu.mem.rw(ds, 0x023C)
    cpu.s.di = start_di

    def read_word_from_call(return_ip: int) -> bool:
        # 03A8 is a jump-style loader routine, but its helper reads are normal
        # near CALLs.  Keep those return frames live while running the lifted
        # 0615 body so verifier-visible freed stack scratch matches ASM.
        cpu.push(return_ip & 0xFFFF)
        read_packed_word_le(cpu)
        if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
            return False
        cpu.s.ip = cpu.pop()
        return True

    def read_byte_from_call(return_ip: int) -> bool:
        cpu.push(return_ip & 0xFFFF)
        read_packed_byte(cpu)
        if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
            return False
        cpu.s.ip = cpu.pop()
        return True

    if not read_word_from_call(0x03B3):
        return
    word0 = cpu.s.ax & 0xFFFF
    cpu.mem.ww(cs, 0x03A2, word0)

    if not read_word_from_call(0x03BA):
        return
    word1 = cpu.s.ax & 0xFFFF
    cpu.mem.ww(ds, 0x03A4, word1)

    if not read_word_from_call(0x03C0):
        return
    word2 = cpu.s.ax & 0xFFFF
    cpu.mem.ww(ds, 0x03A6, word2)

    # Original uses CS:03A4 for both outer LOOP count and vertical stride.  In
    # the real runtime DS==CS here, but CS keeps synthetic oracle fixtures
    # bit-faithful.
    stride = cpu.mem.rw(cs, 0x03A4)
    columns = stride
    cpu.s.cx = columns
    outer_di = cpu.s.di & 0xFFFF

    while cpu.s.cx != 0:
        cpu.s.di = outer_di & 0xFFFF
        # Original saves the outer LOOP counter and column DI on the real stack:
        #   PUSH CX; PUSH DI; ... ; POP DI; INC DI; POP CX; LOOP ...
        # The words remain below SP after return and are compared by hook_verify.
        cpu.push(cpu.s.cx & 0xFFFF)
        cpu.push(cpu.s.di & 0xFFFF)

        while True:
            if not read_byte_from_call(0x03CD):
                return
            control = cpu.get_reg8(0)
            cpu.set_sub_flags(control, 0x80, control - 0x80, 8)  # CMP AL,80h

            if control == 0x80:
                break

            if control > 0x80:
                # NEG AL; XCHG AL,AH; XCHG AH,BL; CALL 0624; XCHG AH,BL.
                # The strange register dance is visible at routine boundary
                # when the packed reader refills through DOS.
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

                if not read_byte_from_call(0x03DC):
                    return

                ah = cpu.get_reg8(4)
                bl = cpu.get_reg8(3)
                cpu.set_reg8(4, bl)
                cpu.set_reg8(3, ah)

                while True:
                    cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.get_reg8(0))
                    cpu.s.di = (cpu.s.di + stride) & 0xFFFF
                    # ADD DI,stride flags are overwritten by INC/DEC below.
                    inc_mem_word_preserve_cf(cpu, ds, 0x0244)
                    dec_reg8_preserve_cf(cpu, 4)  # DEC AH
                    if cpu.get_flag(0x0080):      # JNS not taken when SF=1
                        break
                continue

            # Literal run: PUSH AX; CALL 0624; STOSB; INC [0244]; POP AX;
            # DEC AL; JNS.
            while True:
                # PUSH AX; CALL 0624; ... ; POP AX; DEC AL; JNS ...
                cpu.push(cpu.s.ax & 0xFFFF)
                if not read_byte_from_call(0x03F4):
                    return
                cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.get_reg8(0))
                cpu.s.di = (cpu.s.di + stride) & 0xFFFF
                inc_mem_word_preserve_cf(cpu, ds, 0x0244)
                cpu.s.ax = cpu.pop()
                dec_reg8_preserve_cf(cpu, 0)  # DEC AL
                if cpu.get_flag(0x0080):       # JNS not taken when SF=1
                    break

        # POP DI; INC DI; POP CX; LOOP outer.
        cpu.s.di = cpu.pop()
        old_di = cpu.s.di & 0xFFFF
        old_cf = cpu.get_flag(CF)
        cpu.s.di = (old_di + 1) & 0xFFFF
        cpu.set_add_flags(old_di, 1, old_di + 1, 16)
        cpu.set_flag(CF, old_cf)
        outer_di = cpu.s.di

        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        # LOOP does not affect flags.

    cpu.s.ip = OVERKILL_LOAD_DISPATCH_CONTINUATION_IP


def decode_linear_byte_rle(cpu) -> None:
    """Hook body for 1010:0367 linear byte-RLE decoder.

    This fast path intentionally does not call the shared 0624 helper for every
    data byte; the observed final state was oracle-verified and avoids minutes
    of nested Python call overhead on large startup images.  It still uses the
    same DOS AH=3Fh refill contract as 0624.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    data = mem.data

    def rb(seg: int, off: int) -> int:
        return data[linear_addr(seg, off)]

    def wb(seg: int, off: int, value: int) -> None:
        data[linear_addr(seg, off)] = value & 0xFF

    def read_byte_from_0367_stream() -> int | None:
        saved_bx = cpu.s.bx & 0xFFFF
        mem.ww(ds, 0x0612, saved_bx)
        ptr = mem.rw(ds, 0x0610)
        cpu.set_sub_flags(ptr, 0x0610, ptr - 0x0610, 16)
        if ptr >= 0x0610:
            mem.ww(ds, 0x0610, 0x0410)
            saved_cx = cpu.s.cx & 0xFFFF  # PUSH CX -- restored after the INT 21h read
            cpu.set_reg8(4, 0x3F)
            cpu.s.bx = mem.rw(ds, 0x0240)
            cpu.s.cx = 0x0200
            cpu.s.dx = 0x0410
            if cpu.interrupt_handler is None:
                raise RuntimeError("OVERKILL 0367 RLE needs DOS INT 21h handler")
            cpu.interrupt_handler(cpu, 0x21)
            cpu.s.cx = saved_cx
            if cpu.get_flag(CF):
                cpu.s.ip = OVERKILL_LOAD_ERROR_IP
                return None
            ptr = mem.rw(ds, 0x0610)
        value = rb(ds, ptr)
        cpu.set_reg8(0, value)
        old_ptr = mem.rw(ds, 0x0610)
        old_cf = cpu.get_flag(CF)
        mem.ww(ds, 0x0610, (old_ptr + 1) & 0xFFFF)
        cpu.set_add_flags(old_ptr, 1, old_ptr + 1, 16)
        cpu.set_flag(CF, old_cf)
        cpu.s.bx = mem.rw(ds, 0x0612)
        return value

    def read_byte_from_call(return_ip: int) -> int | None:
        cpu.push(return_ip & 0xFFFF)
        value = read_byte_from_0367_stream()
        if value is None:
            return None
        cpu.s.ip = cpu.pop()
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

        control = read_byte_from_call(0x0372)
        if control is None:
            return
        cpu.set_sub_flags(control, 0x80, control - 0x80, 8)
        if control == 0x80:
            cpu.s.ip = OVERKILL_LOAD_DISPATCH_CONTINUATION_IP
            return

        if control > 0x80:
            # Keep the visible register shuffling from NEG/XCHG/CALL/XCHG.
            cpu.set_sub_flags(0, control, -control, 8)
            cpu.set_reg8(0, (-control) & 0xFF)
            al = cpu.get_reg8(0); ah = cpu.get_reg8(4)
            cpu.set_reg8(0, ah); cpu.set_reg8(4, al)
            ah = cpu.get_reg8(4); bl = cpu.get_reg8(3)
            cpu.set_reg8(4, bl); cpu.set_reg8(3, ah)
            value = read_byte_from_call(0x0384)
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
            dec_reg8_preserve_cf(cpu, 4)
            continue

        # Literal run, count = AL + 1.  Data reads do not affect the branch
        # structure; the final DEC AL decides loop exit and defines flags.
        saved_ah = cpu.get_reg8(4)
        count = control + 1
        for _ in range(count):
            cpu.push(cpu.s.ax & 0xFFFF)
            value = read_byte_from_call(0x0395)
            if value is None:
                return
            write_byte(value)
            cpu.s.ax = cpu.pop()
            dec_reg8_preserve_cf(cpu, 0)
        mem.ww(ds, 0x0244, (mem.rw(ds, 0x0244) + count) & 0xFFFF)
        cpu.set_reg8(4, saved_ah)
