"""VM-free unit tests for the pure 1010:D0D4 scroll-script interpreter step.

Pins the script-state transition (``scroll_script_step``): the per-command delay countdown, the
index advance + entry read on expiry, the FFFFh end marker, and the dec-from-zero wrap -- the
synthetic oracle behind the demo-level ``overkill.probes.verify_native_scroll_script_step``.
"""
from __future__ import annotations

from overkill.recovered.domain.level_script import ScrollScriptStep
from overkill.recovered.systems.level_script import scroll_script_step


def test_timer_running_just_decrements():
    step = scroll_script_step(delay=5, index=3, next_entry_w0=0x1234, next_entry_w1=0x5678)
    assert step == ScrollScriptStep(new_delay=4, new_index=3, entry_updated=False,
                                    command_w0=0, command_w1=0)


def test_timer_expiry_advances_and_reads_entry():
    step = scroll_script_step(delay=1, index=3, next_entry_w0=0x1234, next_entry_w1=0x5678)
    assert step == ScrollScriptStep(new_delay=0x64, new_index=4, entry_updated=True,
                                    command_w0=0x1234, command_w1=0x5678)


def test_end_marker_advances_without_publishing_entry():
    step = scroll_script_step(delay=1, index=7, next_entry_w0=0xFFFF, next_entry_w1=0x0000)
    assert step.new_delay == 0x64 and step.new_index == 8
    assert step.entry_updated is False  # 95FA/BE16 keep their previous values at the FFFFh marker


def test_delay_decrement_wraps_from_zero():
    # dec of 0 -> FFFFh (non-zero), so the timer keeps running rather than firing.
    step = scroll_script_step(delay=0, index=2, next_entry_w0=0x1111, next_entry_w1=0x2222)
    assert step == ScrollScriptStep(new_delay=0xFFFF, new_index=2, entry_updated=False,
                                    command_w0=0, command_w1=0)


def test_scroll_script_step_matches_interpreted_asm_d0d4():
    """Assembled-ASM oracle (D0D4 is a level-intro/scripted-event interpreter, not demo-reached,
    so this per-routine ASM gate stands in for the produced-vs-VM demo gate).

    Run the real 1010:D0D4 timer + index-advance + entry-read up to either D0DA (the timer-not-
    expired RET) or D104 (the 859E call on the expiry path -- stop before it), and assert the
    DS:BE08/BE06/95FA/BE16 it leaves equal ``scroll_script_step``.  The FFFFh end path jumps to
    D107 (the command dispatch, past this slice) and is covered by the unit tests above.
    """
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory

    # exact D0D4..D106 bytes (timer dec, reload+advance, entry read, up to the 859E call):
    code_d0d4 = bytes.fromhex(
        "ff 0e 08 be 74 01 c3 c7 06 08 be 64 00 ff 06 06 be 8b 1e 06 be d1 e3 8b c3 "
        "d1 e3 03 d8 8b 87 1a be 3d ff ff 74 0d a3 fa 95 8b 87 1c be a3 16 be e8 97 b4"
    )
    SENTINEL = 0x9999
    STRIDE = 6

    def run_asm(delay, index, w0, w1):
        mem = Memory()
        mem.load(0x1010, 0xD0D4, code_d0d4)
        cpu = CPU8086(mem, CPUState(cs=0x1010, ds=0x2000, ss=0x2000, sp=0x9000, ip=0xD0D4, flags=0x0202))
        cpu.trace_enabled = False
        mem.ww(0x2000, 0xBE08, delay)
        mem.ww(0x2000, 0xBE06, index)
        mem.ww(0x2000, 0x95FA, SENTINEL)
        mem.ww(0x2000, 0xBE16, SENTINEL)
        entry = (0xBE1A + ((index + 1) & 0xFFFF) * STRIDE) & 0xFFFF
        mem.ww(0x2000, entry, w0)
        mem.ww(0x2000, (entry + 2) & 0xFFFF, w1)
        cpu.push(0xBEEF)
        for _ in range(80):
            if cpu.addr() in ((0x1010, 0xD0DA), (0x1010, 0xD104)):
                break
            cpu.step()
        assert cpu.addr() in ((0x1010, 0xD0DA), (0x1010, 0xD104)), hex(cpu.s.ip)
        return (mem.rw(0x2000, 0xBE08), mem.rw(0x2000, 0xBE06),
                mem.rw(0x2000, 0x95FA), mem.rw(0x2000, 0xBE16))

    # (delay, index, next-entry w0, w1); avoid FFFFh w0 (the end path leaves this slice at D107).
    for delay, index, w0, w1 in [
        (5, 3, 0x1234, 0x5678),    # timer still running
        (1, 3, 0x1234, 0x5678),    # expiry: advance + read entry
        (1, 0, 0xABCD, 0x0001),    # expiry from index 0
        (2, 9, 0x4444, 0x5555),    # timer still running, higher index
    ]:
        be08, be06, w95fa, wbe16 = run_asm(delay, index, w0, w1)
        pred = scroll_script_step(delay, index, w0, w1)
        assert be08 == pred.new_delay and be06 == pred.new_index, (delay, index)
        if pred.entry_updated:
            assert (w95fa, wbe16) == (pred.command_w0, pred.command_w1), (delay, index)
        else:
            assert (w95fa, wbe16) == (SENTINEL, SENTINEL), (delay, index)
