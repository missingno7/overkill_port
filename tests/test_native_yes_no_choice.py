"""Synthetic ASM-vs-pure verification for the yes/no choice gate (1010:989E).

No recorded demo triggers a yes/no confirmation prompt (the user's cold-start recording never
reached one -- confirmed NO-EVENTS via overkill.probes.verify_native_yes_no_choice_989e), so
this is verified directly against the real ASM instead, per the project's witness-poor-routine
convention: inject each (N-flag, Y-flag) combination by hand and run the real interpreter to its
real exit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dos_re.snapshot import run_until
from overkill.recovered.systems.menu import step_yes_no_choice_989e
from overkill.runtime import load_overkill_snapshot

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets" / "OVERKILL"
SNAPSHOT = ROOT / "artifacts" / "demos" / "demo_play_tandy_L2_full_20260617_180221" / "snapshot"
ENTRY_IP = 0x989E
EXIT_IP = 0x98B6
N_FLAG, Y_FLAG, DISPLAY_CHAR = 0x98F5, 0x98D9, 0x22B4

# (n_pressed, y_pressed) -- N is checked first, so (True, True) still resolves to exit_no.
CASES = [(False, False), (True, False), (False, True), (True, True)]


@pytest.mark.skipif(not EXE.exists() or not SNAPSHOT.exists(), reason="needs assets/OVERKILL + a demo snapshot")
@pytest.mark.parametrize("n_pressed,y_pressed", CASES)
def test_yes_no_choice_matches_asm(n_pressed, y_pressed):
    predicted = step_yes_no_choice_989e(n_pressed=n_pressed, y_pressed=y_pressed)
    rt = load_overkill_snapshot(EXE, SNAPSHOT, game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.trace_enabled = False
    ds = cpu.s.ds & 0xFFFF
    cpu.mem.wb(ds, N_FLAG, 1 if n_pressed else 0)
    cpu.mem.wb(ds, Y_FLAG, 1 if y_pressed else 0)
    cpu.s.cs = 0x1010
    cpu.s.ip = ENTRY_IP

    if predicted.result == "loop":
        # The loop case re-enters ENTRY_IP itself, which run_until's stop_at would match
        # immediately (before the body ever runs) -- run a fixed number of raw steps (the whole
        # body is ~6 instructions) instead, then check where it actually landed.
        cpu.run(9)
        assert (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) == (0x1010, ENTRY_IP), (
            f"n={n_pressed} y={y_pressed}: expected to loop back to {ENTRY_IP:04X}, "
            f"landed at {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}")
    else:
        status, steps, _ = run_until(rt, max_steps=10, stop_at=(0x1010, EXIT_IP))
        assert status.startswith("reached"), (
            f"n={n_pressed} y={y_pressed}: expected to reach {EXIT_IP:04X} within 10 steps, "
            f"got {status!r} (ip={cpu.s.ip:04X})")

    assert cpu.mem.rb(ds, DISPLAY_CHAR) == predicted.display_char, (
        f"n={n_pressed} y={y_pressed}: DS:22B4={cpu.mem.rb(ds, DISPLAY_CHAR):02X} "
        f"!= predicted {predicted.display_char:02X}")
