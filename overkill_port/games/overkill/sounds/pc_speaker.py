"""OVERKILL PC-speaker and timer-IRQ sound island.

This module contains the game-specific source-code lift of OVERKILL's installed
IRQ0 handler and PC-speaker bytecode sequencer:

* 1010:06E5  fast timer ISR installed by 1010:068A
* 1010:D50E  sound tick / PC-speaker driver
* 1010:D566  sound request and priority gate
* 1010:D5AC  two-channel sound bytecode sequencer
* 1010:D61F+ pitch/frequency helpers

The code is intentionally not part of the generic 8086 VM.  Offsets such as
BEFF/BFAA/BFBA/BFCA and the INT 08h chaining behavior are specific to OVERKILL.
Hook wrappers in :mod:`overkill_port.replacements` keep the original addresses
registered while delegating the lifted implementation here.
"""
from __future__ import annotations

import time

from overkill_port.cpu import CF, IF, TF

# Live-byte signatures used by the hook wrappers in replacements.py.
SIG_FAST_TIMER_ISR_06E5 = bytes.fromhex("50 1e 53 51 52 57 56 55 06 2e 8e 1e 96 95 80 3e")
SIG_PC_SPEAKER_TICK_D50E = bytes.fromhex("fe 06 00 bf 80 26 00 bf 03 a0 ff be 0a c0 74 03")

# PIT divisor programmed by OVERKILL's 1010:068A installer.
OVERKILL_PIT_HZ = 1193182.0 / 0x4000


def _cmp_byte(cpu, a: int, b: int) -> None:
    a &= 0xFF
    b &= 0xFF
    cpu.set_sub_flags(a, b, a - b, 8)


def _inc_reg8_preserve_cf(cpu, idx: int) -> int:
    old = cpu.get_reg8(idx)
    old_cf = cpu.get_flag(CF)
    result = (old + 1) & 0xFF
    cpu.set_reg8(idx, result)
    cpu.set_add_flags(old, 1, old + 1, 8)
    cpu.set_flag(CF, old_cf)
    return result


def _inc_mem_byte_preserve_cf(cpu, seg: int, off: int) -> int:
    old = cpu.mem.rb(seg, off)
    old_cf = cpu.get_flag(CF)
    result = (old + 1) & 0xFF
    cpu.mem.wb(seg, off, result)
    cpu.set_add_flags(old, 1, old + 1, 8)
    cpu.set_flag(CF, old_cf)
    return result


def _dec_mem_byte_preserve_cf(cpu, seg: int, off: int) -> int:
    old = cpu.mem.rb(seg, off)
    old_cf = cpu.get_flag(CF)
    result = (old - 1) & 0xFF
    cpu.mem.wb(seg, off, result)
    cpu.set_sub_flags(old, 1, old - 1, 8)
    cpu.set_flag(CF, old_cf)
    return result


def _and_mem_byte(cpu, seg: int, off: int, value: int) -> int:
    old = cpu.mem.rb(seg, off)
    result = old & (value & 0xFF)
    cpu.mem.wb(seg, off, result)
    cpu.set_logic_flags(result, 8)
    return result


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


def _in_al(cpu, port: int) -> int:
    value = cpu.port_reader(cpu, port & 0xFFFF, 8) if cpu.port_reader else 0
    cpu.set_reg8(0, value & 0xFF)
    return value & 0xFF


def _out_imm_al(cpu, port: int) -> None:
    if cpu.port_writer:
        cpu.port_writer(cpu, port & 0xFFFF, cpu.get_reg8(0), 8)


def run_fast_timer_isr_06e5(cpu) -> None:
    """Lift OVERKILL 1010:06E5 installed IRQ0 handler.

    The interrupted FLAGS/CS/IP frame is already on the stack when this is called
    by the VM's interrupt delivery path.  This routine preserves the original
    save/restore frame and the old-BIOS chaining behavior used every fourth PIT
    sub-tick.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    # 06E5..06ED: save interrupted state.
    cpu.push(cpu.s.ax)
    cpu.push(cpu.s.ds)
    cpu.push(cpu.s.bx)
    cpu.push(cpu.s.cx)
    cpu.push(cpu.s.dx)
    cpu.push(cpu.s.di)
    cpu.push(cpu.s.si)
    cpu.push(cpu.s.bp)
    cpu.push(cpu.s.es)

    game_ds = mem.rw(cs, 0x9596)
    cpu.s.ds = game_ds
    driver_flag = mem.rb(game_ds, 0x0055)
    _cmp_byte(cpu, driver_flag, 1)
    if driver_flag == 1:
        # The captured Tandy/PC-speaker path has this disabled.  The optional far
        # sound-driver branch at 2032:0000 is a different island and should not be
        # silently approximated here.
        raise RuntimeError("1010:06E5 optional far sound-driver branch is not lifted")

    cpu.push(0x0707)
    run_pc_speaker_tick_d50e(cpu)
    if cpu.s.ip != 0x0707:
        raise RuntimeError(f"D50E sound tick returned to unexpected IP {cpu.s.ip:04X}")

    cpu.s.ds = mem.rw(cs, 0x9596)
    test_value = mem.rb(cpu.s.ds, 0x0054) & 0x01
    cpu.set_logic_flags(test_value, 8)  # TEST byte [0054],1
    if test_value == 0:
        cpu.push(0x0716)
        _inc_mem_byte_preserve_cf(cpu, cs, 0x066B)  # 066C INC byte ptr CS:[066B]
        cpu.s.ip = cpu.pop()

    cpu.s.es = cpu.pop()
    cpu.s.bp = cpu.pop()
    cpu.s.si = cpu.pop()
    cpu.s.di = cpu.pop()
    cpu.s.dx = cpu.pop()
    cpu.s.cx = cpu.pop()
    cpu.s.bx = cpu.pop()

    _inc_mem_byte_preserve_cf(cpu, cpu.s.ds, 0x0054)
    tick_mod = _and_mem_byte(cpu, cpu.s.ds, 0x0054, 0x03)
    if tick_mod == 0:
        # 072F chain path.  The VM's IRQ deliverer treats the old BIOS vector as
        # a bounded return to the interrupted code after the game-side work.
        cpu.s.ds = cpu.pop()
        cpu.s.ax = cpu.pop()
        cpu.set_flag(IF, True)  # STI
        if cpu.port_writer:
            cpu.port_writer(cpu, 0x20, 0x20, 8)
        cpu.s.ip = cpu.pop()
        cpu.s.cs = cpu.pop()
        cpu.s.flags = cpu.pop() | 0x0002
        return

    cpu.s.ds = cpu.pop()
    cpu.set_reg8(0, 0x20)
    _out_imm_al(cpu, 0x20)
    cpu.s.ax = cpu.pop()
    cpu.s.ip = cpu.pop()
    cpu.s.cs = cpu.pop()
    cpu.s.flags = cpu.pop() | 0x0002


def _sound_disable_speaker_d62f(cpu, ds: int) -> None:
    # D62F: xor al,al; clear global/channel-active bytes; in 61h; and al,fc; out 61h; ret
    cpu.set_reg8(0, 0)
    cpu.set_logic_flags(0, 8)  # XOR AL,AL
    cpu.mem.wb(ds, 0xBEFE, 0)
    cpu.mem.wb(ds, 0xBFB3, 0)
    cpu.mem.wb(ds, 0xBFC3, 0)
    al = _in_al(cpu, 0x61)
    al &= 0xFC
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)  # AND AL,0FCh
    _out_imm_al(cpu, 0x61)


def _sound_frequency_lookup_d61f(cpu, ds: int, di: int, al: int) -> None:
    # D61F: xor ah,ah; shl al,1; mov si,ax; add si,bf01; mov ax,[si]; mov [di+6],ax; ret
    cpu.set_reg8(4, 0)
    cpu.set_logic_flags(0, 8)  # XOR AH,AH
    al = cpu.shift(4, al & 0xFF, 1, 8)
    cpu.set_reg8(0, al)
    cpu.s.si = cpu.s.ax & 0xFFFF
    _add_reg16(cpu, 6, 0xBF01)
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
    _cmp_byte(cpu, value, 0)
    if value == 0:
        return
    _dec_mem_byte_preserve_cf(cpu, ds, off)
    cpu.s.ax = cpu.mem.rw(ds, (di + 0x0C) & 0xFFFF)
    _add_mem_word(cpu, ds, (di + 0x06) & 0xFFFF, cpu.s.ax)


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
        al = _in_al(cpu, 0x61)
        al &= 0xFC
        cpu.set_reg8(0, al)
        cpu.set_logic_flags(al, 8)  # AND AL,0FCh
        _out_imm_al(cpu, 0x61)
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
    new_delay = _dec_mem_byte_preserve_cf(cpu, ds, (di + 0x08) & 0xFFFF)
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
        _cmp_byte(cpu, al, 0xE0)
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
        _add_reg16(cpu, 6, 0xBEF0)
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
    _cmp_byte(cpu, al, 0x20)
    if al >= 0x20:
        _sound_disable_speaker_d62f(cpu, ds)
        return

    active = cpu.mem.rb(ds, 0xBEFE)
    _cmp_byte(cpu, active, 0)
    if active != 0:
        _cmp_byte(cpu, al, active)
        if al != active and al >= active:
            # JAE D565: rejected lower-priority request, RET with the CMP flags.
            return
    cpu.mem.wb(ds, 0xBEFE, al)
    cpu.set_reg8(4, 0)
    cpu.set_logic_flags(0, 8)       # XOR AH,AH
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.si = 0xBFCA
    _add_reg16(cpu, 6, cpu.s.ax)
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
    _inc_reg8_preserve_cf(cpu, 0)   # INC AL -> 1, flags preserved through following MOVs.
    cpu.mem.wb(ds, 0xBFB2, cpu.get_reg8(0))
    cpu.mem.wb(ds, 0xBFC2, cpu.get_reg8(0))


def run_pc_speaker_tick_d50e(cpu) -> None:
    """Lift OVERKILL 1010:D50E PC-speaker tick routine; near-returns."""
    ds = cpu.s.ds & 0xFFFF

    _inc_mem_byte_preserve_cf(cpu, ds, 0xBF00)
    _and_mem_byte(cpu, ds, 0xBF00, 0x03)
    al = cpu.mem.rb(ds, 0xBEFF)
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)  # OR AL,AL
    if al != 0:
        cpu.push(0xD521)
        _sound_request_d566(cpu, ds)
        cpu.s.ip = cpu.pop()

    active = cpu.mem.rb(ds, 0xBEFE)
    _cmp_byte(cpu, active, 0)
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
        _cmp_byte(cpu, active2, 0)
        if active2 == 0:
            cpu.s.ip = cpu.pop()
            return
        cpu.s.bx = cpu.mem.rw(ds, 0xBFC0)
    else:
        active1 = cpu.mem.rb(ds, 0xBFB3)
        _cmp_byte(cpu, active1, 0)
        if active1 == 0:
            cpu.s.ip = cpu.pop()
            return
        cpu.s.bx = cpu.mem.rw(ds, 0xBFB0)

    cpu.set_reg8(0, 0xB6)
    _out_imm_al(cpu, 0x43)
    cpu.set_reg8(0, cpu.s.bx & 0xFF)
    _out_imm_al(cpu, 0x42)
    cpu.set_reg8(0, (cpu.s.bx >> 8) & 0xFF)
    _out_imm_al(cpu, 0x42)
    al = _in_al(cpu, 0x61)
    al |= 0x03
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)  # OR AL,03h
    _out_imm_al(cpu, 0x61)
    cpu.s.ip = cpu.pop()


def deliver_overkill_timer_irq0(cpu, *, max_steps: int = 200_000) -> bool:
    """Synchronously run OVERKILL's installed INT 08h timer ISR if present.

    The game sound code lives in the real ISR at ``1010:06E5``.  The original
    handler chains the old BIOS timer every fourth tick via ``JMP FAR
    CS:[0738]``; in this VM that saved BIOS vector is often 0000:0000, so stop
    at the known chain point after the game-side work and restore the interrupt
    frame locally.
    """
    mem = cpu.mem
    off = mem.rw(0, 0x20)
    seg = mem.rw(0, 0x22)
    if (seg & 0xFFFF, off & 0xFFFF) != (0x1010, 0x06E5):
        return False

    ret_cs, ret_ip = cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF
    sp0 = cpu.s.sp & 0xFFFF
    cpu.push(cpu.s.flags)
    cpu.push(ret_cs)
    cpu.push(ret_ip)
    cpu.set_flag(IF, False)
    cpu.set_flag(TF, False)
    cpu.s.cs = seg & 0xFFFF
    cpu.s.ip = off & 0xFFFF

    for _ in range(max_steps):
        if cpu.s.sp == sp0 and cpu.addr() == (ret_cs, ret_ip):
            return True
        if cpu.addr() == (0x1010, 0x072F):
            # Chain path after the game work:
            #   POP DS; POP AX; STI; JMP FAR CS:[0738]
            cpu.s.ds = cpu.pop()
            cpu.s.ax = cpu.pop()
            cpu.set_flag(IF, True)
            if cpu.port_writer:
                cpu.port_writer(cpu, 0x20, 0x20, 8)
            cpu.s.ip = cpu.pop()
            cpu.s.cs = cpu.pop()
            cpu.s.flags = cpu.pop()
            return cpu.s.sp == sp0 and cpu.addr() == (ret_cs, ret_ip)
        cpu.step()
    raise RuntimeError(
        f"OVERKILL INT 08h timer ISR did not return "
        f"(cs:ip={cpu.s.cs:04X}:{cpu.s.ip:04X})"
    )


class AsyncTimerIrqDriver:
    """Deliver real OVERKILL INT 08h IRQs during non-frame busy waits.

    The game normally waits at 1010:0679, where the timer hook runs the real
    1010:06E5 ISR.  Some menu/input-release loops spin without touching 0679; on
    the original PC the PIT IRQ continues asynchronously and advances sound there
    too.  This driver is intentionally only a scheduler: each tick still executes
    the actual installed ISR, not a synthetic sound fallback.
    """

    def __init__(self, hz: float = OVERKILL_PIT_HZ) -> None:
        self.period = 1.0 / hz if hz > 0 else 0.0
        self._next: float | None = None

    def reset_after_synchronous_ticks(self, ticks: int = 1) -> None:
        if self.period <= 0:
            return
        now = time.perf_counter()
        self._next = now + self.period * max(1, int(ticks))

    def poll(self, cpu, *, max_catchup: int = 1) -> int:
        if self.period <= 0 or not cpu.get_flag(IF):
            return 0
        now = time.perf_counter()
        if self._next is None:
            self._next = now + self.period
            return 0
        if now < self._next:
            return 0

        # This driver is only meant to keep the original IRQ0 sound ISR alive
        # while the foreground code is in menu/retrace/input waits that do not
        # reach the normal 1010:0679 timer wait.  Do not preserve a large wall-
        # clock backlog here.  Replaying missed PIT ticks later mutates the same
        # CS:066B frame-wait flag that drives gameplay, so after one slow Python
        # burst the game can briefly run too fast while the delayed IRQs are
        # drained.  Hardware IRQs are asynchronous, but our foreground execution
        # is not interruptible in the middle of a long Python hook; the stable
        # interactive compromise is to deliver a small bounded number of real ISR
        # ticks and then re-anchor to wall clock.
        due = int((now - self._next) // self.period) + 1
        due = max(1, min(max_catchup, due))
        delivered = 0
        for _ in range(due):
            if not deliver_overkill_timer_irq0(cpu):
                break
            delivered += 1
        if delivered:
            self._next = time.perf_counter() + self.period
        return delivered
