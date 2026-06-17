"""OVERKILL PC-speaker sound-effect engine.

The game plays all of its **sound effects** through the PC speaker.  This module
is the platform-independent source-code lift of that engine:

* 1010:D50E  sound tick / PC-speaker driver (near-return; called from the IRQ0
             conductor in :mod:`overkill.sounds.timing`)
* 1010:D566  sound request and priority gate
* 1010:D5AC  two-channel sound bytecode sequencer
* 1010:D5D6/D5CC/D61F/D612/D602/D62F  channel finish / frequency / pitch helpers

Music is a separate concern handled by the AdLib driver
(:mod:`overkill.sounds.adlib_driver`); the only thing the two share is the timer
tick that drives them, which lives in :mod:`overkill.sounds.timing`.

The offsets BEFF/BFAA/BFBA/BFCA and the PIT/speaker port (42h/43h/61h) accesses
are specific to OVERKILL.  The hook wrappers in
:mod:`overkill.hook_wrappers.sounds` keep the original address registered while
delegating the lifted implementation here.
"""
from __future__ import annotations

from dos_re.cpu import CF
from ._asm import (
    add_mem_word,
    add_reg16,
    and_mem_byte,
    cmp_byte,
    dec_mem_byte_preserve_cf,
    in_al,
    inc_mem_byte_preserve_cf,
    inc_reg8_preserve_cf,
    out_imm_al,
)

# Live-byte signature used by the hook wrapper in overkill/hook_wrappers/sounds.py.
SIG_PC_SPEAKER_TICK_D50E = bytes.fromhex("fe 06 00 bf 80 26 00 bf 03 a0 ff be 0a c0 74 03")


def _sound_disable_speaker_d62f(cpu, ds: int) -> None:
    # D62F: xor al,al; clear global/channel-active bytes; in 61h; and al,fc; out 61h; ret
    cpu.set_reg8(0, 0)
    cpu.set_logic_flags(0, 8)  # XOR AL,AL
    cpu.mem.wb(ds, 0xBEFE, 0)
    cpu.mem.wb(ds, 0xBFB3, 0)
    cpu.mem.wb(ds, 0xBFC3, 0)
    al = in_al(cpu, 0x61)
    al &= 0xFC
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)  # AND AL,0FCh
    out_imm_al(cpu, 0x61)


def _sound_frequency_lookup_d61f(cpu, ds: int, di: int, al: int) -> None:
    # D61F: xor ah,ah; shl al,1; mov si,ax; add si,bf01; mov ax,[si]; mov [di+6],ax; ret
    cpu.set_reg8(4, 0)
    cpu.set_logic_flags(0, 8)  # XOR AH,AH
    al = cpu.shift(4, al & 0xFF, 1, 8)
    cpu.set_reg8(0, al)
    cpu.s.si = cpu.s.ax & 0xFFFF
    add_reg16(cpu, 6, 0xBF01)
    cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
    cpu.mem.ww(ds, (di + 0x06) & 0xFFFF, cpu.s.ax)


def _sound_apply_pitch_delta_d612(cpu, ds: int, di: int) -> None:
    # D612: al=[di+b]; or al,al; jz ret; add al,[di+4]; [di+4]=al; fall into D61F.
    al = cpu.mem.rb(ds, (di + 0x0B) & 0xFFFF)
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)  # OR AL,AL
    if al == 0:
        return
    old = al
    value = cpu.mem.rb(ds, (di + 0x04) & 0xFFFF)
    result = (old + value) & 0xFF
    cpu.set_reg8(0, result)
    cpu.set_add_flags(old, value, old + value, 8)
    cpu.mem.wb(ds, (di + 0x04) & 0xFFFF, result)
    _sound_frequency_lookup_d61f(cpu, ds, di, result)


def _sound_apply_slide_d602(cpu, ds: int, di: int) -> None:
    # D602: if [di+e] != 0, decrement it and add [di+c] into [di+6].
    off = (di + 0x0E) & 0xFFFF
    value = cpu.mem.rb(ds, off)
    cmp_byte(cpu, value, 0)
    if value == 0:
        return
    dec_mem_byte_preserve_cf(cpu, ds, off)
    cpu.s.ax = cpu.mem.rw(ds, (di + 0x0C) & 0xFFFF)
    add_mem_word(cpu, ds, (di + 0x06) & 0xFFFF, cpu.s.ax)


def _sound_finish_channel_d5d6(cpu, ds: int, di: int, bx: int) -> tuple[bool, int]:
    # Returns (finished, bx).  D5D6 can fall through to the common D5CC tail.
    cpu.mem.wb(ds, (di + 0x09) & 0xFFFF, 0)
    al = cpu.mem.rb(ds, 0xBFB3)
    cpu.set_reg8(0, al)
    rhs = cpu.mem.rb(ds, 0xBFC3)
    al = (al | rhs) & 0xFF
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)  # OR AL,[BFC3]
    if al == 0:
        al = in_al(cpu, 0x61)
        al &= 0xFC
        cpu.set_reg8(0, al)
        cpu.set_logic_flags(al, 8)  # AND AL,0FCh
        out_imm_al(cpu, 0x61)
    return True, bx


def _sound_store_pointer_delay_tail_d5cc(cpu, ds: int, di: int, bx: int) -> None:
    cpu.mem.ww(ds, (di + 0x02) & 0xFFFF, bx & 0xFFFF)
    al = cpu.mem.rb(ds, (di + 0x05) & 0xFFFF)
    cpu.set_reg8(0, al)
    cpu.mem.wb(ds, (di + 0x08) & 0xFFFF, al)


def _sound_step_channel_d5ac(cpu, ds: int, di: int) -> None:
    """Lift OVERKILL 1010:D5AC PC-speaker channel sequencer.

    DI points at one of the two 16-byte channel records (BFAA or BFBA).  The
    original helper returns via several tails; this routine preserves the same
    registers/flags observable by D50E, including the command interpreter loops
    and PIT/speaker port writes.
    """
    di &= 0xFFFF
    cpu.s.bx = cpu.mem.rw(ds, (di + 0x02) & 0xFFFF)
    new_delay = dec_mem_byte_preserve_cf(cpu, ds, (di + 0x08) & 0xFFFF)
    if new_delay != 0:
        # CALL D612; CALL D602; RET.  Their return words are verifier-visible
        # below SP while the outer D50E hook is verified, so model the frames.
        cpu.push(0xD5B7)
        _sound_apply_pitch_delta_d612(cpu, ds, di)
        cpu.s.ip = cpu.pop()
        cpu.push(0xD5BA)
        _sound_apply_slide_d602(cpu, ds, di)
        cpu.s.ip = cpu.pop()
        return

    bx = cpu.s.bx & 0xFFFF
    while True:
        al = cpu.mem.rb(ds, bx)
        cpu.set_reg8(0, al)
        bx = (bx + 1) & 0xFFFF
        cpu.set_logic_flags(al, 8)  # OR AL,AL
        if al < 0x80:
            cpu.mem.wb(ds, (di + 0x04) & 0xFFFF, al)
            cpu.push(0xD5C8)
            _sound_frequency_lookup_d61f(cpu, ds, di, al)
            cpu.s.ip = cpu.pop()
            cpu.mem.wb(ds, (di + 0x09) & 0xFFFF, 0x02)
            _sound_store_pointer_delay_tail_d5cc(cpu, ds, di, bx)
            return

        # D5EB: negative command byte.
        cmp_byte(cpu, al, 0xE0)
        if al >= 0xE0:
            old = al
            al = (al - 0xDF) & 0xFF
            cpu.set_reg8(0, al)
            cpu.set_sub_flags(old, 0xDF, old - 0xDF, 8)  # SUB AL,0DFh
            cpu.mem.wb(ds, (di + 0x05) & 0xFFFF, al)
            continue

        # JMP word ptr [BEF0 + AL*2].  Model the flag-affecting SHL/XOR/ADD
        # before dispatch because D5CC and D5D6 may preserve those flags.
        al2 = cpu.shift(4, al, 1, 8)
        cpu.set_reg8(0, al2)
        cpu.set_reg8(4, 0)
        cpu.set_logic_flags(0, 8)  # XOR AH,AH
        cpu.s.si = cpu.s.ax & 0xFFFF
        add_reg16(cpu, 6, 0xBEF0)
        target = cpu.mem.rw(ds, cpu.s.si)
        if target == 0xD62F:
            _sound_disable_speaker_d62f(cpu, ds)
            return
        if target == 0xD5D6:
            _sound_finish_channel_d5d6(cpu, ds, di, bx)
            _sound_store_pointer_delay_tail_d5cc(cpu, ds, di, bx)
            return
        if target == 0xD641:
            cpu.mem.wb(ds, (di + 0x0B) & 0xFFFF, 0xFF)
            continue
        if target == 0xD648:
            cpu.mem.wb(ds, (di + 0x0B) & 0xFFFF, 0x01)
            continue
        if target == 0xD64F:
            cpu.s.ax = cpu.mem.rw(ds, bx)
            bx = (bx + 2) & 0xFFFF
            cpu.mem.ww(ds, (di + 0x0C) & 0xFFFF, cpu.s.ax)
            al = cpu.mem.rb(ds, bx)
            cpu.set_reg8(0, al)
            bx = (bx + 1) & 0xFFFF
            cpu.mem.wb(ds, (di + 0x0E) & 0xFFFF, al)
            continue
        if target == 0xD5CC:
            _sound_store_pointer_delay_tail_d5cc(cpu, ds, di, bx)
            return
        raise RuntimeError(f"unknown OVERKILL sound command target {target:04X} from {ds:04X}:{cpu.s.si:04X}")


def _sound_request_d566(cpu, ds: int) -> None:
    al = cpu.get_reg8(0)
    cmp_byte(cpu, al, 0x20)
    if al >= 0x20:
        _sound_disable_speaker_d62f(cpu, ds)
        return

    active = cpu.mem.rb(ds, 0xBEFE)
    cmp_byte(cpu, active, 0)
    if active != 0:
        cmp_byte(cpu, al, active)
        if al != active and al >= active:
            # JAE D565: rejected lower-priority request, RET with the CMP flags.
            return
    cpu.mem.wb(ds, 0xBEFE, al)
    cpu.set_reg8(4, 0)
    cpu.set_logic_flags(0, 8)       # XOR AH,AH
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.si = 0xBFCA
    add_reg16(cpu, 6, cpu.s.ax)
    cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    cpu.mem.ww(ds, 0xBFAC, cpu.s.ax)
    cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    cpu.mem.ww(ds, 0xBFBC, cpu.s.ax)
    cpu.set_reg8(0, 0)
    cpu.set_logic_flags(0, 8)       # XOR AL,AL
    cpu.mem.wb(ds, 0xBFB5, 0)
    cpu.mem.wb(ds, 0xBFC5, 0)
    cpu.mem.wb(ds, 0xBFB8, 0)
    cpu.mem.wb(ds, 0xBFC8, 0)
    cpu.mem.wb(ds, 0xBEFF, 0)
    inc_reg8_preserve_cf(cpu, 0)    # INC AL -> 1, flags preserved through following MOVs.
    cpu.mem.wb(ds, 0xBFB2, cpu.get_reg8(0))
    cpu.mem.wb(ds, 0xBFC2, cpu.get_reg8(0))


def run_pc_speaker_tick_d50e(cpu) -> None:
    """Lift OVERKILL 1010:D50E PC-speaker tick routine; near-returns."""
    ds = cpu.s.ds & 0xFFFF

    inc_mem_byte_preserve_cf(cpu, ds, 0xBF00)
    and_mem_byte(cpu, ds, 0xBF00, 0x03)
    al = cpu.mem.rb(ds, 0xBEFF)
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)  # OR AL,AL
    if al != 0:
        cpu.push(0xD521)
        _sound_request_d566(cpu, ds)
        cpu.s.ip = cpu.pop()

    active = cpu.mem.rb(ds, 0xBEFE)
    cmp_byte(cpu, active, 0)
    if active == 0:
        cpu.s.ip = cpu.pop()
        return

    cpu.s.di = 0xBFAA
    cpu.push(0xD52E)
    _sound_step_channel_d5ac(cpu, ds, cpu.s.di)
    cpu.s.ip = cpu.pop()
    cpu.s.di = 0xBFBA
    cpu.push(0xD534)
    _sound_step_channel_d5ac(cpu, ds, cpu.s.di)
    cpu.s.ip = cpu.pop()

    al = cpu.mem.rb(ds, 0xBF00)
    cpu.set_reg8(0, al)
    al = cpu.shift(5, al, 1, 8)  # SHR AL,1
    cpu.set_reg8(0, al)
    if cpu.get_flag(CF):
        active2 = cpu.mem.rb(ds, 0xBFC3)
        cmp_byte(cpu, active2, 0)
        if active2 == 0:
            cpu.s.ip = cpu.pop()
            return
        cpu.s.bx = cpu.mem.rw(ds, 0xBFC0)
    else:
        active1 = cpu.mem.rb(ds, 0xBFB3)
        cmp_byte(cpu, active1, 0)
        if active1 == 0:
            cpu.s.ip = cpu.pop()
            return
        cpu.s.bx = cpu.mem.rw(ds, 0xBFB0)

    cpu.set_reg8(0, 0xB6)
    out_imm_al(cpu, 0x43)
    cpu.set_reg8(0, cpu.s.bx & 0xFF)
    out_imm_al(cpu, 0x42)
    cpu.set_reg8(0, (cpu.s.bx >> 8) & 0xFF)
    out_imm_al(cpu, 0x42)
    al = in_al(cpu, 0x61)
    al |= 0x03
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)  # OR AL,03h
    out_imm_al(cpu, 0x61)
    cpu.s.ip = cpu.pop()
