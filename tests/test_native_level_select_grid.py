"""Synthetic ASM-vs-pure verification for the level-select grid (1010:D390-D4B0).

No recorded demo navigates this screen's direction keys (the user's cold-start recording
confirmed the fire-confirm mapping but never pressed a direction), so the 4 direction handlers'
accept AND reject (boundary) branches are verified here directly against the real ASM instead --
setting up each entry state by hand and running the real interpreter to its real exit, per the
project's witness-poor-routine convention (build a targeted/synthetic probe, mark clearly).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dos_re.snapshot import run_until
from overkill.recovered.systems.menu import (
    step_level_select_decrement_d488,
    step_level_select_increment_d490,
    step_level_select_page_down_d476,
    step_level_select_page_up_d480,
)
from overkill.runtime import load_overkill_snapshot

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets" / "OVERKILL"
SNAPSHOT = ROOT / "artifacts" / "demos" / "demo_play_tandy_L2_full_20260617_180221" / "snapshot"
ACCEPT_TAIL_IP = 0xD47C
IDLE_HEAD_IP = 0xD445
BEDA = 0xBEDA

# (handler ASM entry addr, pure function, beda values to try -- a mix of accept + boundary-reject)
CASES = [
    (0xD476, step_level_select_page_down_d476, (0, 1, 2, 3, 4, 5)),
    (0xD480, step_level_select_page_up_d480, (0, 1, 2, 3, 4, 5)),
    (0xD488, step_level_select_decrement_d488, (0, 1, 2, 3, 4, 5)),
    (0xD490, step_level_select_increment_d490, (0, 1, 2, 3, 4, 5)),
]


@pytest.mark.skipif(not EXE.exists() or not SNAPSHOT.exists(), reason="needs assets/OVERKILL + a demo snapshot")
@pytest.mark.parametrize("handler_ip,pure_fn,beda_values", CASES)
def test_level_select_direction_handler_matches_asm(handler_ip, pure_fn, beda_values):
    for beda_before in beda_values:
        predicted = pure_fn(beda_before)
        rt = load_overkill_snapshot(EXE, SNAPSHOT, game_root=ROOT / "assets")
        cpu = rt.cpu
        cpu.trace_enabled = False
        ds = cpu.s.ds & 0xFFFF
        cpu.mem.wb(ds, BEDA, beda_before)
        cpu.s.cs = 0x1010
        cpu.s.ip = handler_ip
        cpu.s.ax = (cpu.s.ax & 0xFF00) | beda_before  # AL = BEDA, matching the real D44F prelude

        target = ACCEPT_TAIL_IP if predicted.accepted else IDLE_HEAD_IP
        status, steps, _ = run_until(rt, max_steps=10, stop_at=(0x1010, target))
        assert status.startswith("reached"), (
            f"handler {handler_ip:04X} beda={beda_before}: expected to reach "
            f"{target:04X} within 10 steps, got {status!r} (ip={cpu.s.ip:04X})")

        if predicted.accepted:
            # Stopped BEFORE D47C's own `mov [BEDA],al` executes -- AL already holds the
            # post-transform value (the preceding add/sub/inc/dec already ran).
            assert (cpu.s.ax & 0xFF) == predicted.beda, (
                f"handler {handler_ip:04X} beda={beda_before}: AL={cpu.s.ax & 0xFF:02X} "
                f"!= predicted {predicted.beda:02X} at the D47C accept tail")
        else:
            actual = cpu.mem.rb(ds, BEDA)
            assert actual == beda_before == predicted.beda, (
                f"handler {handler_ip:04X} beda={beda_before}: DS:BEDA={actual:02X} changed "
                f"on a predicted-reject path (should be untouched)")
