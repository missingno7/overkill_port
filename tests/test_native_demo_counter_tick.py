"""Synthetic ASM-vs-pure verification for the demo/attract-mode counter tick (1F8F:081D).

No recorded demo enters attract-mode playback (A940 only calls this while DS:2356 == 5, a state
none of the corpus reaches), so this is verified directly against the real ASM instead, per the
project's witness-poor-routine convention: inject each entry state by hand into a loaded
snapshot's CPU (the routine is FAR-called, so the stack needs a fake far-return address pushed)
and run the real interpreter to its real exit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dos_re.snapshot import run_until
from overkill.recovered.systems.frame_loop import step_demo_counter_tick_1f8f_081d
from overkill.runtime import load_overkill_snapshot

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets" / "OVERKILL"
SNAPSHOT = ROOT / "artifacts" / "demos" / "demo_play_tandy_L2_full_20260617_180221" / "snapshot"
ENTRY_CS, ENTRY_IP = 0x1F8F, 0x081D
FAKE_RET_CS, FAKE_RET_IP = 0xBEEF, 0xCAFE
COUNTER_98A7, SPEED_A47E, COUNTER_98A6 = 0x98A7, 0xA47E, 0x98A6

# (counter_98a7, speed_bucket_a47e, counter_98a6) -- covers: plain decrement (no reload), the
# byte-DEC-from-0 wrap (still non-zero, so also no reload), and a reload at each threshold bucket.
CASES = [
    (0x05, 0x20, 0x03),  # decrements to 4 (non-zero) -> no reload
    (0x00, 0x20, 0x03),  # DEC from 0 wraps to 0xFF (non-zero) -> no reload, same as above
    (0x01, 0x20, 0x03),  # reaches 0 -> reload; a47e=0x20 > 0x10 -> default bucket 0x78
    (0x01, 0x0C, 0x03),  # reaches 0; a47e=0x0C: <=0x10 but not <=0x08 -> bucket 0x64
    (0x01, 0x06, 0x03),  # reaches 0; a47e=0x06: <=0x08 but not <=0x04 -> bucket 0x50
    (0x01, 0x03, 0x03),  # reaches 0; a47e=0x03: <=0x04 but not <=0x02 -> bucket 0x3C
    (0x01, 0x01, 0x03),  # reaches 0; a47e=0x01: <=0x02 -> deepest bucket 0x28
]


@pytest.mark.skipif(not EXE.exists() or not SNAPSHOT.exists(), reason="needs assets/OVERKILL + a demo snapshot")
@pytest.mark.parametrize("counter_98a7,speed_bucket_a47e,counter_98a6", CASES)
def test_demo_counter_tick_matches_asm(counter_98a7, speed_bucket_a47e, counter_98a6):
    predicted = step_demo_counter_tick_1f8f_081d(counter_98a7, speed_bucket_a47e, counter_98a6)
    rt = load_overkill_snapshot(EXE, SNAPSHOT, game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.trace_enabled = False
    ds = cpu.s.ds & 0xFFFF
    cpu.mem.wb(ds, COUNTER_98A7, counter_98a7)
    cpu.mem.ww(ds, SPEED_A47E, speed_bucket_a47e)
    cpu.mem.wb(ds, COUNTER_98A6, counter_98a6)
    cpu.push(FAKE_RET_CS)
    cpu.push(FAKE_RET_IP)
    cpu.s.cs = ENTRY_CS
    cpu.s.ip = ENTRY_IP

    status, steps, _ = run_until(rt, max_steps=30, stop_at=(FAKE_RET_CS, FAKE_RET_IP))
    assert status.startswith("reached"), (
        f"counter_98a7={counter_98a7:#04x} a47e={speed_bucket_a47e:#06x}: expected to reach the "
        f"far-return within 30 steps, got {status!r} (cs:ip={cpu.s.cs:04X}:{cpu.s.ip:04X})")

    assert cpu.mem.rb(ds, COUNTER_98A7) == predicted.counter_98a7, (
        f"counter_98a7={counter_98a7:#04x} a47e={speed_bucket_a47e:#06x}: "
        f"DS:98A7={cpu.mem.rb(ds, COUNTER_98A7):#04x} != predicted {predicted.counter_98a7:#04x}")
    assert cpu.mem.rb(ds, COUNTER_98A6) == predicted.counter_98a6, (
        f"counter_98a7={counter_98a7:#04x} a47e={speed_bucket_a47e:#06x}: "
        f"DS:98A6={cpu.mem.rb(ds, COUNTER_98A6):#04x} != predicted {predicted.counter_98a6:#04x}")
