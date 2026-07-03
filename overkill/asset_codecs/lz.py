"""OVERKILL LZ-style asset decoder routines.

This module holds the ECF2 decompressor and its helper entrypoints ED97, EDE9,
and ED7A.  The code remains OVERKILL-specific: fixed buffer offsets such as
D8B8/DCB8/D666/EDE5 are part of the original loader layout and must not leak into
or depend on the generic VM framework.
"""
from __future__ import annotations

from ._flags import CF, DF
from .asm_adapters import linear_addr, loop_count, near_call_into_hook

INPUT_RING_BASE = 0xD8B8
OUTPUT_DICT_BASE = 0xDCB8
DOS_FILE_HANDLE_OFF = 0xD666
PUSHBACK_FLAG_OFF = 0xEE04
PUSHBACK_BYTE_OFF = 0xEE05
OUTPUT_COUNT_LOW_OFF = 0xEDE5
OUTPUT_COUNT_HIGH_OFF = 0xEDE7
DEST_DI_OFF = 0xECEE
DEST_ES_OFF = 0xECF0


def output_lz_byte(cpu) -> None:
    """Hook body for 1010:EDE9 byte output helper; near-returns to caller."""
    # STOSB
    cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.get_reg8(0))
    cpu.s.di = (cpu.s.di + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF

    # OR DI,DI
    cpu.set_logic_flags(cpu.s.di, 16)
    if cpu.s.di == 0:
        # PUSH AX; MOV AX,ES; ADD AX,1000h; MOV ES,AX; POP AX.
        saved_ax = cpu.s.ax & 0xFFFF
        ax = cpu.s.es & 0xFFFF
        result = ax + 0x1000
        cpu.set_add_flags(ax, 0x1000, result, 16)
        cpu.s.es = result & 0xFFFF
        cpu.s.ax = saved_ax

    # INC word ptr CS:EDE5; if it wrapped, INC word ptr CS:EDE7.
    old = cpu.mem.rw(cpu.s.cs, OUTPUT_COUNT_LOW_OFF)
    old_cf = cpu.get_flag(CF)
    new = (old + 1) & 0xFFFF
    cpu.mem.ww(cpu.s.cs, OUTPUT_COUNT_LOW_OFF, new)
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)
    if new == 0:
        old2 = cpu.mem.rw(cpu.s.cs, OUTPUT_COUNT_HIGH_OFF)
        old_cf = cpu.get_flag(CF)
        cpu.mem.ww(cpu.s.cs, OUTPUT_COUNT_HIGH_OFF, (old2 + 1) & 0xFFFF)
        cpu.set_add_flags(old2, 1, old2 + 1, 16)
        cpu.set_flag(CF, old_cf)

    cpu.s.ip = cpu.pop()


def input_lz_byte(cpu) -> None:
    """Hook body for 1010:ED97 byte input helper; near-returns to caller.

    The helper either consumes a one-byte pushback slot or reads from the 1 KiB
    ring buffer at DS:D8B8+SI.  On ring wrap it performs DOS AH=3Fh through the
    VM interrupt handler and restores the caller-visible register set just like
    the ASM routine.
    """
    cs = cpu.s.cs & 0xFFFF
    # TEST byte ptr CS:EE04,0FFh.  Even the pushback path returns with these
    # TEST flags, so do not treat this as a simple Python boolean check.
    pushback_flag = cpu.mem.rb(cs, PUSHBACK_FLAG_OFF)
    cpu.set_logic_flags(pushback_flag & 0xFF, 8)
    if pushback_flag != 0:
        cpu.set_reg8(0, cpu.mem.rb(cs, PUSHBACK_BYTE_OFF))
        cpu.mem.wb(cs, PUSHBACK_FLAG_OFF, 0)
        cpu.s.ip = cpu.pop()
        return

    old_si = cpu.s.si & 0xFFFF
    added = old_si + INPUT_RING_BASE
    cpu.s.si = added & 0xFFFF
    cpu.set_add_flags(old_si, INPUT_RING_BASE, added, 16)
    cpu.set_reg8(0, cpu.mem.rb(cpu.s.ds, cpu.s.si))
    cpu.s.si = (cpu.s.si + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF

    before_sub = cpu.s.si & 0xFFFF
    sub_result = before_sub - INPUT_RING_BASE
    cpu.s.si = sub_result & 0xFFFF
    cpu.set_sub_flags(before_sub, INPUT_RING_BASE, sub_result, 16)

    and_result = cpu.s.si & 0x03FF
    cpu.s.si = and_result
    cpu.set_logic_flags(and_result, 16)
    saved_flags_after_and = cpu.s.flags & 0xFFFF

    if cpu.s.si == 0:
        saved = (cpu.s.ax, cpu.s.bx, cpu.s.cx, cpu.s.dx, cpu.s.si, cpu.s.di, cpu.s.bp, cpu.s.flags)
        cpu.s.dx = INPUT_RING_BASE
        cpu.s.ax = 0x3F00
        cpu.s.bx = cpu.mem.rw(cs, DOS_FILE_HANDLE_OFF)
        cpu.s.cx = 0x0400
        if cpu.interrupt_handler is None:
            raise RuntimeError("OVERKILL LZ reader needs DOS INT 21h handler")
        cpu.interrupt_handler(cpu, 0x21)
        cpu.s.ax, cpu.s.bx, cpu.s.cx, cpu.s.dx, cpu.s.si, cpu.s.di, cpu.s.bp, _ = saved
        # The original path reaches the return with the ZF/PF-style bits from
        # AND SI,03FF rather than the DOS flags.
        cpu.s.flags = saved_flags_after_and | 0x0002

    cpu.s.ip = cpu.pop()


def copy_lz_back_reference(cpu) -> None:
    """Hook body for 1010:ED7A back-reference copy loop; continues at ED26."""
    count = loop_count(cpu.s.cx)
    cs = cpu.s.cs & 0xFFFF
    for _ in range(count):
        cpu.set_reg8(0, cpu.mem.rb(cs, (cpu.s.bx + OUTPUT_DICT_BASE) & 0xFFFF))
        near_call_into_hook(cpu, output_lz_byte, 0xED82)
        cpu.mem.wb(cs, (cpu.s.bp + OUTPUT_DICT_BASE) & 0xFFFF, cpu.get_reg8(0))

        old_bx = cpu.s.bx & 0xFFFF
        old_cf = cpu.get_flag(CF)
        cpu.s.bx = (old_bx + 1) & 0xFFFF
        cpu.set_add_flags(old_bx, 1, old_bx + 1, 16)
        cpu.set_flag(CF, old_cf)
        cpu.s.bx &= 0x0FFF
        cpu.set_logic_flags(cpu.s.bx, 16)

        old_bp = cpu.s.bp & 0xFFFF
        old_cf = cpu.get_flag(CF)
        cpu.s.bp = (old_bp + 1) & 0xFFFF
        cpu.set_add_flags(old_bp, 1, old_bp + 1, 16)
        cpu.set_flag(CF, old_cf)
        cpu.s.bp &= 0x0FFF
        cpu.set_logic_flags(cpu.s.bp, 16)

        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unaffected.
    cpu.s.ip = 0xED26


def decode_lz_bytes(stream) -> bytes:
    """Pure 1010:ECF2 LZ decode: a compressed byte stream -> the decompressed bytes.

    The VM-free twin of :func:`decode_lz_asset`, with the machine mechanics stripped (the 1 KiB DS:D8B8
    input ring + DOS refill, the ES:DI segment wrap, the CS-relative counters, and the stack scratch).
    What remains is the codec: a 4 KiB sliding-window LZSS.  An 8-bit flag word feeds one control bit per
    item LSB-first (refilled from the stream every 8 items, ``0xFF00`` high marker); a 1 bit is a literal
    byte (emitted and pushed into the window), a 0 bit is a back-reference -- two bytes ``ax`` give a
    12-bit window offset and a length of ``(ax>>12)+3``.  ``ax==0`` reads one more byte: ``0`` terminates,
    otherwise it is pushed back and a 3-byte copy from window offset 0 runs (the ASM resync path).  The
    window starts zeroed with the write cursor at ``0x0FEE``.  Algorithm is the hook's, ASM-verified.
    """
    iterator = iter(stream)
    pushback: list[int] = []

    def read() -> int:
        return pushback.pop() if pushback else (next(iterator) & 0xFF)

    out = bytearray()
    window = bytearray(0x1000)
    write_pos = 0x0FEE
    flags = 0

    while True:
        flags >>= 1
        if (flags & 0x0100) == 0:  # high marker exhausted -> refill 8 control bits
            flags = 0xFF00 | read()
        if flags & 1:  # literal
            byte = read()
            out.append(byte)
            window[write_pos] = byte
            write_pos = (write_pos + 1) & 0x0FFF
            continue
        # back-reference
        low = read()
        high = read()
        word = ((high & 0xFF) << 8) | (low & 0xFF)
        if word == 0:
            extra = read()
            if extra == 0:
                return bytes(out)
            pushback.append(extra)  # ASM resync: push the byte back, copy 3 from offset 0
            word = 0
        length = ((word >> 8) & 0x0F) + 3
        offset = ((((word >> 8) >> 4) << 8) | (word & 0xFF)) & 0x0FFF
        read_pos = offset
        for _ in range(length):
            byte = window[read_pos]
            out.append(byte)
            window[write_pos] = byte
            read_pos = (read_pos + 1) & 0x0FFF
            write_pos = (write_pos + 1) & 0x0FFF


def decode_lz_asset(cpu) -> None:
    """Full verified replacement for OVERKILL's 1010:ECF2 LZ asset decoder.

    Byte input, byte output, and back-reference copying are inlined here rather
    than dispatched through ED97/EDE9/ED7A helpers, so a whole compressed asset
    completes in one hook invocation without nested Python call/flag overhead.
    The externally observable boundary remains the same as ECF2: PUSH ES at
    entry, ED95 POP ES, then RET to the original caller.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    data = mem.data

    def rb(seg: int, off: int) -> int:
        return data[linear_addr(seg, off)]

    def wb(seg: int, off: int, value: int) -> None:
        data[linear_addr(seg, off)] = value & 0xFF

    def ww(seg: int, off: int, value: int) -> None:
        wb(seg, off, value)
        wb(seg, (off + 1) & 0xFFFF, value >> 8)

    def read_input_byte() -> int:
        # Mirrors ED97.  Most flags are not live across the full decoder except
        # for explicit TEST/CMP branches reproduced in the outer logic.
        if rb(cs, PUSHBACK_FLAG_OFF) != 0:
            value = rb(cs, PUSHBACK_BYTE_OFF)
            wb(cs, PUSHBACK_FLAG_OFF, 0)
            cpu.set_reg8(0, value)
            return value

        ds = cpu.s.ds & 0xFFFF
        temp_si = (cpu.s.si + INPUT_RING_BASE) & 0xFFFF
        value = rb(ds, temp_si)
        temp_si = (temp_si + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF
        cpu.s.si = (temp_si - INPUT_RING_BASE) & 0xFFFF
        cpu.s.si &= 0x03FF

        if cpu.s.si == 0:
            # LODSB already set AL to the new byte in the original ASM before
            # the ring-wrap check.  Mirror that so PUSH AX saves the same value.
            cpu.set_reg8(0, value)
            # AND SI,03FF sets ZF=1/PF=1 (SI=0), clears OF/CF.  Update flags so
            # PUSHF captures the same flag word as the oracle.
            cpu.set_logic_flags(cpu.s.si, 16)
            # PUSHF; PUSH AX…BP — matches ASM register-save sequence so the
            # dead-stack slots below SP get the same values as the oracle run.
            cpu.push(cpu.s.flags)
            cpu.push(cpu.s.ax)
            cpu.push(cpu.s.bx)
            cpu.push(cpu.s.cx)
            cpu.push(cpu.s.dx)
            cpu.push(cpu.s.si)
            cpu.push(cpu.s.di)
            cpu.push(cpu.s.bp)
            cpu.s.dx = INPUT_RING_BASE
            cpu.s.ax = 0x3F00
            cpu.s.bx = mem.rw(cs, DOS_FILE_HANDLE_OFF)
            cpu.s.cx = 0x0400
            if cpu.interrupt_handler is None:
                raise RuntimeError("OVERKILL LZ decoder needs DOS INT 21h handler")
            cpu.interrupt_handler(cpu, 0x21)
            # POP BP…AX; POPF — mirrors the ASM pop sequence.
            cpu.s.bp = cpu.pop()
            cpu.s.di = cpu.pop()
            cpu.s.si = cpu.pop()
            cpu.s.dx = cpu.pop()
            cpu.s.cx = cpu.pop()
            cpu.s.bx = cpu.pop()
            cpu.s.ax = cpu.pop()
            cpu.s.flags = cpu.pop()
            return value

        cpu.set_reg8(0, value)
        return value

    def output_byte(value: int) -> None:
        wb(cpu.s.es, cpu.s.di, value)
        cpu.s.di = (cpu.s.di + (-1 if cpu.get_flag(DF) else 1)) & 0xFFFF
        if cpu.s.di == 0:
            cpu.s.es = (cpu.s.es + 0x1000) & 0xFFFF
        counter = (mem.rw(cs, OUTPUT_COUNT_LOW_OFF) + 1) & 0xFFFF
        mem.ww(cs, OUTPUT_COUNT_LOW_OFF, counter)
        if counter == 0:
            mem.ww(cs, OUTPUT_COUNT_HIGH_OFF, (mem.rw(cs, OUTPUT_COUNT_HIGH_OFF) + 1) & 0xFFFF)

    def input_from_call(return_ip: int) -> int:
        # The full decoder inlines ED97 for speed, but the original ECF2 code
        # reaches it through near CALLs.  Keep those call frames live so freed
        # stack scratch, including the final ED5F terminator read, matches ASM.
        cpu.push(return_ip & 0xFFFF)
        value = read_input_byte()
        cpu.s.ip = cpu.pop()
        return value

    def output_from_call(return_ip: int, value: int) -> None:
        cpu.push(return_ip & 0xFFFF)
        output_byte(value)
        cpu.s.ip = cpu.pop()

    # ECF2 PUSH ES / ED95 POP ES; RET.
    cpu.push(cpu.s.es)

    mem.ww(cs, OUTPUT_COUNT_LOW_OFF, 0)
    mem.ww(cs, OUTPUT_COUNT_HIGH_OFF, 0)
    cpu.s.di = mem.rw(cs, DEST_DI_OFF)
    cpu.s.es = mem.rw(cs, DEST_ES_OFF)
    wb(cs, PUSHBACK_FLAG_OFF, 0)
    cpu.s.si = 0
    cpu.s.bp = 0
    cpu.s.cx = 0x07F7

    while cpu.s.cx != 0:
        ww(cs, (OUTPUT_DICT_BASE + cpu.s.bp) & 0xFFFF, 0)
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
            flag_byte = input_from_call(0xED31)
            cpu.s.dx = 0xFF00 | flag_byte  # MOV DL,AL; MOV DH,FFh

        if cpu.s.dx & 1:
            value = input_from_call(0xED3E)
            output_from_call(0xED41, value)
            wb(cs, (OUTPUT_DICT_BASE + cpu.s.bp) & 0xFFFF, value)
            cpu.s.bp = (cpu.s.bp + 1) & 0x0FFF
            cpu.s.cx = 0
            continue

        first = input_from_call(0xED50)
        # MOV AH,AL at ED50: save first byte in AH before second read so that
        # any ring-wrap inside the second CALL ED97 pushes the correct AX word.
        cpu.set_reg8(4, cpu.get_reg8(0))
        second = input_from_call(0xED55)
        cpu.s.ax = ((second & 0xFF) << 8) | first
        cpu.set_sub_flags(cpu.s.ax, 0, cpu.s.ax, 16)
        if cpu.s.ax == 0:
            extra = input_from_call(0xED5F)
            cpu.set_reg8(0, extra)
            cpu.set_sub_flags(extra, 0, extra, 8)
            if extra == 0:
                cpu.s.es = cpu.pop()
                cpu.s.ip = cpu.pop()
                return
            wb(cs, PUSHBACK_FLAG_OFF, 1)
            wb(cs, PUSHBACK_BYTE_OFF, extra)
            cpu.set_reg8(0, 0)
            # AX is now exactly zero, matching MOV AL,0 with AH already zero.
            cpu.s.ax &= 0xFF00

        ah = (cpu.s.ax >> 8) & 0xFF
        length = (ah & 0x0F) + 3
        offset = (((ah >> 4) << 8) | (cpu.s.ax & 0xFF)) & 0x0FFF
        # ASM: MOV CL,AH; SHR AH,1 ×4; MOV BX,AX — AH becomes ah>>4 as a
        # side-effect of the shift sequence before the copy loop.
        cpu.s.ax = ((ah >> 4) << 8) | (cpu.s.ax & 0xFF)
        cpu.s.bx = offset
        cpu.s.cx = length

        while cpu.s.cx != 0:
            value = rb(cs, (OUTPUT_DICT_BASE + cpu.s.bx) & 0xFFFF)
            cpu.set_reg8(0, value)
            output_from_call(0xED82, value)
            wb(cs, (OUTPUT_DICT_BASE + cpu.s.bp) & 0xFFFF, value)
            cpu.s.bx = (cpu.s.bx + 1) & 0x0FFF
            cpu.s.bp = (cpu.s.bp + 1) & 0x0FFF
            cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
