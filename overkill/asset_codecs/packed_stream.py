"""OVERKILL packed 512-byte loader stream.

The routines here mirror 1010:0624 and 1010:0615.  They are not direct host file
readers.  The original byte reader refills a 512-byte buffer using DOS
INT 21h AH=3Fh, and callers can observe the DOS-updated registers/flags.  The
Python replacement must therefore call the VM's configured interrupt handler
instead of reading Python files directly.
"""
from __future__ import annotations

from dos_re.cpu import CF

from .asm_adapters import OVERKILL_LOAD_ERROR_IP

BUFFER_START = 0x0410
BUFFER_END = 0x0610
SAVED_BX_OFF = 0x0612
STREAM_PTR_OFF = 0x0610
TEMP_LOW_BYTE_OFF = 0x0614
DOS_FILE_HANDLE_OFF = 0x0240


def read_packed_byte(cpu) -> None:
    """Mirror 1010:0624; result byte is returned in AL.

    On DOS read failure CF remains set and IP jumps to 1010:02B2.  Otherwise BX
    is restored from DS:0612 and the stream pointer is advanced exactly like the
    ASM routine, including the final INC-style flags with CF preserved.
    """
    ds = cpu.s.ds & 0xFFFF
    saved_bx = cpu.s.bx & 0xFFFF
    cpu.mem.ww(ds, SAVED_BX_OFF, saved_bx)
    ptr = cpu.mem.rw(ds, STREAM_PTR_OFF)

    cpu.set_sub_flags(ptr, BUFFER_END, ptr - BUFFER_END, 16)  # CMP BX,0610h
    if ptr >= BUFFER_END:
        cpu.mem.ww(ds, STREAM_PTR_OFF, BUFFER_START)
        saved_cx = cpu.s.cx & 0xFFFF  # PUSH CX -- restored after the INT 21h read
        cpu.set_reg8(4, 0x3F)  # AH=3Fh read file/device
        cpu.s.bx = cpu.mem.rw(ds, DOS_FILE_HANDLE_OFF)
        cpu.s.cx = 0x0200
        cpu.s.dx = BUFFER_START
        if cpu.interrupt_handler is None:
            raise RuntimeError("OVERKILL packed reader needs DOS INT 21h handler")
        cpu.interrupt_handler(cpu, 0x21)
        cpu.s.cx = saved_cx
        if cpu.get_flag(CF):
            cpu.s.ip = OVERKILL_LOAD_ERROR_IP
            return
        ptr = cpu.mem.rw(ds, STREAM_PTR_OFF)

    byte = cpu.mem.rb(ds, ptr)
    cpu.set_reg8(0, byte)

    old_ptr = cpu.mem.rw(ds, STREAM_PTR_OFF)
    new_ptr = (old_ptr + 1) & 0xFFFF
    old_cf = cpu.get_flag(CF)
    cpu.set_add_flags(old_ptr, 1, old_ptr + 1, 16)
    cpu.set_flag(CF, old_cf)
    cpu.mem.ww(ds, STREAM_PTR_OFF, new_ptr)

    cpu.s.bx = cpu.mem.rw(ds, SAVED_BX_OFF)


def read_packed_byte_hook(cpu) -> None:
    """Hook boundary for 1010:0624; near-return unless DOS error jumped away."""
    read_packed_byte(cpu)
    if cpu.s.ip != OVERKILL_LOAD_ERROR_IP:
        cpu.s.ip = cpu.pop()


def read_packed_word_le(cpu) -> None:
    """Mirror 1010:0615; result word is returned in AX.

    This is the body form for callers that inline the original CALL/RET effect.
    It preserves the visible DS:0614 scratch byte and all flags left by the
    second 0624 byte read.
    """
    cpu.push(0x0618)
    read_packed_byte(cpu)
    if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
        return
    cpu.s.ip = cpu.pop()
    low = cpu.get_reg8(0)
    cpu.mem.wb(cpu.s.ds, TEMP_LOW_BYTE_OFF, low)
    cpu.push(0x061E)
    read_packed_byte(cpu)
    if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
        return
    cpu.s.ip = cpu.pop()
    high = cpu.get_reg8(0)
    cpu.set_reg8(4, high)  # AH
    cpu.set_reg8(0, cpu.mem.rb(cpu.s.ds, TEMP_LOW_BYTE_OFF))


def read_packed_word_le_hook(cpu) -> None:
    """Hook boundary for 1010:0615 little-endian word reader."""
    read_packed_word_le(cpu)
    if cpu.s.ip == OVERKILL_LOAD_ERROR_IP:
        return
    cpu.s.ip = cpu.pop()
