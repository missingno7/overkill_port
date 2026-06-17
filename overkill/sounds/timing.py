"""OVERKILL frame-timer / IRQ0 infrastructure.

This is the shared *tick source* for the whole sound island, and it is neither
sound-effect nor music logic itself: it is the reprogrammed PIT / INT 08h
handler that, on every tick, drives both the optional AdLib/Roland **music**
driver (``2032:0000``) and the PC-speaker **sound-effect** engine
(``1010:D50E``), and advances the frame-wait flag the gameplay loop spins on.

Concretely it lifts:

* 1010:06E5  installed IRQ0 handler (conductor: music tick + SFX tick + frame flag)
* 1010:0672  clear the frame-timer flag
* 1010:0679  wait for the next timer tick
* 1010:9921  wait for the active PC-speaker sound to finish

plus the VM-side delivery shims (:func:`deliver_overkill_timer_irq0`,
:class:`AsyncTimerIrqDriver`) that synchronously run the real installed ISR,
because the Python VM is not asynchronously interruptible.  Keeping these out of
``pc_speaker`` leaves that module as a pure sound-effect engine.
"""
from __future__ import annotations

import time

from dos_re.cpu import IF, TF, ZF
from ._asm import and_mem_byte, cmp_byte, inc_mem_byte_preserve_cf, out_imm_al
from .adlib_driver import run_adlib_far_entry_2032_0000
from .loaded_driver import OPTIONAL_SOUND_DRIVER_SEGMENT
from .pc_speaker import run_pc_speaker_tick_d50e

# Live-byte signatures used by the hook wrappers in overkill/hook_wrappers.
SIG_FAST_TIMER_ISR_06E5 = bytes.fromhex("50 1e 53 51 52 57 56 55 06 2e 8e 1e 96 95 80 3e")
SIG_TIMER_CLEAR_0672 = bytes.fromhex("2e c6 06 6b 06 00 c3")
SIG_TIMER_WAIT_0679 = bytes.fromhex("2e 80 3e 6b 06 00 74 f8 c3")
SIG_SOUND_ACTIVE_WAIT_9921 = bytes.fromhex("80 3e fe be 00 75 f9")

# PIT divisor programmed by OVERKILL's 1010:068A installer.
OVERKILL_PIT_HZ = 1193182.0 / 0x4000


def run_clear_timer_tick_flag_0672(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:0672: clear the frame timer flag and RET.

    This is the small companion to the 1010:0679 wait loop.  Main/gameplay loops
    call 0672 before doing a frame worth of work, then call 0679 to wait until
    the installed IRQ0 handler advances CS:066B.
    """
    if self_disable_if_patched(cpu, 0x0672, SIG_TIMER_CLEAR_0672, "overkill_clear_timer_tick_flag_0672"):
        return
    cs = cpu.s.cs & 0xFFFF
    cpu.mem.wb(cs, 0x066B, 0)
    cpu.s.ip = cpu.pop()


def run_wait_timer_tick_0679(cpu) -> None:
    """Lift OVERKILL 1010:0679 timer-tick busy wait.

    Original routine::

        0679  cmp byte ptr cs:[066B],0
        067F  jz   0679
        0681  ret

    The flag at CS:066B is normally incremented by the installed IRQ0 handler
    (1010:06E5).  Since the Python VM does not receive asynchronous hardware
    IRQs, this hook explicitly delivers the game's timer ISR at the same
    instruction boundaries used by the verifier's ASM oracle, then models the
    tiny CMP/JZ/RET loop.  Preserving the delivery point matters: when multiple
    ticks are needed, the asm oracle delivers the ISR before each cpu.step()
    call, so the CMP at 0679 never executes between retries and every stale
    interrupt frame has IP=0679.  Mirror that here.
    """
    cs = cpu.s.cs & 0xFFFF
    delivered = 0
    cpu.timer_ticks_elapsed = 0
    cpu.s.ip = 0x0679

    for _ in range(32):
        flag = cpu.mem.rb(cs, 0x066B)
        if cpu.s.ip in (0x0679, 0x067F) and flag == 0:
            if not deliver_overkill_timer_irq0(cpu):
                raise RuntimeError(
                    "1010:0679 timer wait needs OVERKILL INT 08h at 1010:06E5; "
                    "no synthetic timer fallback is allowed"
                )
            delivered += 1
            flag = cpu.mem.rb(cs, 0x066B)
            if flag == 0 and cpu.s.ip == 0x0679:
                # ISR fired at 0679 but didn't advance the flag; the asm oracle
                # would fire again at 0679 before the next CMP, so skip the CMP
                # step and retry delivery at ip=0679.
                continue

        if cpu.s.ip == 0x0679:
            cmp_byte(cpu, flag, 0)
            cpu.s.ip = 0x067F
            continue

        if cpu.s.ip == 0x067F:
            cpu.s.ip = 0x0679 if cpu.get_flag(ZF) else 0x0681
            continue

        if cpu.s.ip == 0x0681:
            cpu.timer_ticks_elapsed = delivered
            cpu.s.ip = cpu.pop()
            if cpu.timer_pacer is not None:
                cpu.timer_pacer()
            return

        raise RuntimeError(f"1010:0679 timer wait reached unexpected IP {cpu.s.ip:04X}")

    raise RuntimeError("1010:06E5 timer ISR did not advance CS:066B within 32 wait-loop iterations")


def run_sound_active_wait_9921(cpu) -> None:
    """Lift OVERKILL 1010:9921 sound-active busy wait.

    Original inline loop::

        9921  cmp byte ptr ds:[BEFE],0
        9926  jnz 9921

    This loop appears in foreground/menu code after sound requests.  On real
    hardware the reprogrammed PIT/IRQ0 keeps executing 1010:06E5 asynchronously
    while the foreground code spins.  The Python VM is not asynchronously
    interruptible, so the hook delivers the real installed OVERKILL IRQ0 ISR
    until the global sound-active byte clears, then models the final exiting
    CMP/JNZ iteration and continues at 9928.
    """
    ds = cpu.s.ds & 0xFFFF
    active = cpu.mem.rb(ds, 0xBEFE)
    delivered = 0
    while active != 0 and delivered < 8192:
        if not deliver_overkill_timer_irq0(cpu):
            raise RuntimeError(
                "1010:9921 sound-active wait needs OVERKILL INT 08h at 1010:06E5; "
                "no synthetic sound fallback is allowed"
            )
        delivered += 1
        active = cpu.mem.rb(ds, 0xBEFE)
    if active != 0:
        raise RuntimeError("1010:06E5 timer ISR did not clear DS:BEFE within 8192 ticks")

    cmp_byte(cpu, active, 0)
    cpu.s.ip = 0x9928


def run_fast_timer_isr_06e5(cpu) -> None:
    """Lift OVERKILL 1010:06E5 installed IRQ0 handler.

    On each tick the handler (a) optionally enters the loaded AdLib/Roland music
    driver at 2032:0000, (b) runs the PC-speaker sound-effect tick at D50E, and
    (c) advances the frame-wait counter CS:066B every fourth sub-tick.  The
    interrupted FLAGS/CS/IP frame is already on the stack when this is called by
    the VM's interrupt delivery path; this routine preserves the original
    save/restore frame and the old-BIOS chaining behavior.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    game_ds = mem.rw(cs, 0x9596)
    if mem.rb(game_ds, 0x0055) == 1:
        # Once the optional AdLib/Roland driver is active, the ISR enters a
        # loaded far driver at 2032:0000.  The exact stack scratch left by that
        # path is part of strict full-memory verification, so keep this rare path
        # bounded-original until the driver ISR is fully lifted with byte-exact
        # scratch semantics.
        run_original_fast_timer_isr_06e5(cpu)
        return

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

    cpu.s.ds = game_ds
    driver_flag = mem.rb(game_ds, 0x0055)
    cmp_byte(cpu, driver_flag, 1)
    if driver_flag == 1:
        # 06FA: CALL FAR 2032:0000.  Preserve the original far-return words so
        # the loaded driver's RETF lands at the same 1010:06FF continuation.
        cpu.push(0x1010)
        cpu.push(0x06FF)
        cpu.s.cs = OPTIONAL_SOUND_DRIVER_SEGMENT
        cpu.s.ip = 0x0000
        handler = cpu.replacement_hooks.get((OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0000), run_adlib_far_entry_2032_0000)
        handler(cpu)
        if cpu.addr() != (0x1010, 0x06FF):
            raise RuntimeError(
                f"2032:0000 AdLib far entry returned to unexpected address "
                f"{cpu.s.cs:04X}:{cpu.s.ip:04X}"
            )
        cpu.s.ds = mem.rw(cs, 0x9596)

    cpu.push(0x0707)
    run_pc_speaker_tick_d50e(cpu)
    if cpu.s.ip != 0x0707:
        raise RuntimeError(f"D50E sound tick returned to unexpected IP {cpu.s.ip:04X}")

    cpu.s.ds = mem.rw(cs, 0x9596)
    test_value = mem.rb(cpu.s.ds, 0x0054) & 0x01
    cpu.set_logic_flags(test_value, 8)  # TEST byte [0054],1
    if test_value == 0:
        cpu.push(0x0716)
        inc_mem_byte_preserve_cf(cpu, cs, 0x066B)  # 066C INC byte ptr CS:[066B]
        cpu.s.ip = cpu.pop()

    cpu.s.es = cpu.pop()
    cpu.s.bp = cpu.pop()
    cpu.s.si = cpu.pop()
    cpu.s.di = cpu.pop()
    cpu.s.dx = cpu.pop()
    cpu.s.cx = cpu.pop()
    cpu.s.bx = cpu.pop()

    inc_mem_byte_preserve_cf(cpu, cpu.s.ds, 0x0054)
    tick_mod = and_mem_byte(cpu, cpu.s.ds, 0x0054, 0x03)
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
    out_imm_al(cpu, 0x20)
    cpu.s.ax = cpu.pop()
    cpu.s.ip = cpu.pop()
    cpu.s.cs = cpu.pop()
    cpu.s.flags = cpu.pop() | 0x0002


def run_original_fast_timer_isr_06e5(cpu, *, max_steps: int = 200_000) -> None:
    """Run the original 1010:06E5 ISR body when the optional far driver is active.

    The lifted PC-speaker path intentionally covers the common ``DS:0055 == 0``
    case.  When the AdLib/Roland driver initializes successfully, the real ISR
    performs an additional far call through ``2032:0000`` before the shared sound
    tick.  Keep that path faithful by temporarily disabling replacement hooks and
    interpreting the original ISR until it IRETs back to the interrupted code.
    """
    saved_hooks = dict(cpu.replacement_hooks)
    saved_names = dict(cpu.hook_names)
    cpu.replacement_hooks.clear()
    cpu.hook_names.clear()
    ss = cpu.s.ss & 0xFFFF
    frame_sp = cpu.s.sp & 0xFFFF
    ret_ip = cpu.mem.rw(ss, frame_sp)
    ret_cs = cpu.mem.rw(ss, (frame_sp + 2) & 0xFFFF)
    return_sp = (frame_sp + 6) & 0xFFFF
    try:
        for _ in range(max_steps):
            if cpu.s.sp == return_sp and cpu.addr() == (ret_cs, ret_ip):
                return
            if cpu.addr() == (0x1010, 0x072F):
                # Same old-BIOS chain boundary used by deliver_overkill_timer_irq0:
                # POP DS; POP AX; STI; JMP FAR CS:[0738].  The VM does not run a
                # real BIOS timer, so complete the interrupt frame locally after
                # the game-side work has finished.
                cpu.s.ds = cpu.pop()
                cpu.s.ax = cpu.pop()
                cpu.set_flag(IF, True)
                if cpu.port_writer:
                    cpu.port_writer(cpu, 0x20, 0x20, 8)
                cpu.s.ip = cpu.pop()
                cpu.s.cs = cpu.pop()
                cpu.s.flags = cpu.pop() | 0x0002
                return
            cpu.step()
    finally:
        cpu.replacement_hooks.clear()
        cpu.replacement_hooks.update(saved_hooks)
        cpu.hook_names.clear()
        cpu.hook_names.update(saved_names)
    raise RuntimeError(
        f"original 1010:06E5 optional-driver ISR did not return "
        f"(cs:ip={cpu.s.cs:04X}:{cpu.s.ip:04X})"
    )


def deliver_overkill_timer_irq0(cpu, *, max_steps: int = 200_000) -> bool:
    """Synchronously run OVERKILL's installed INT 08h timer ISR if present.

    The game sound code lives in the real ISR at ``1010:06E5``.  The original
    handler chains the old BIOS timer every fourth tick via ``JMP FAR
    CS:[0738]``; in this VM that saved BIOS vector is often 0000:0000, so stop at
    the known chain point after the game-side work and restore the interrupt
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
        # drained.  The stable interactive compromise is to deliver a small
        # bounded number of real ISR ticks and then re-anchor to wall clock.
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
