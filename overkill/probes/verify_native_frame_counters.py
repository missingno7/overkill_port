"""Driven-oracle: the per-frame counter cascade vs the ORIGINAL 1010:5F61.

From the L1_start snapshot (A47E != 0, so the routine skips its A480/CB1C video branch -- the pure
counter case), drive 5F61 to its RET once per frame for many frames, capturing the FRAME_COUNTER_CELLS
before + after, and compare the after-values to ``advance_frame_counters_5f61`` fed the before-values.
Enough frames to exercise all the gates: the /4 A7A0 sub-bank (2332), the /8 wave oscillator (2328).

Usage:
    python -m overkill.probes.verify_native_frame_counters [snapshot_dir] [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x5F61
SENTINEL_IP = 0xFFFE
SCRATCH_SP = 0xFF60
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import (
        FRAME_COUNTER_CELLS,
        advance_frame_counters_5f61,
    )

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    want = int(argv[1]) if len(argv) > 1 else 64
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    def run_frame() -> None:
        m.ww(ds, SCRATCH_SP, SENTINEL_IP)
        s.sp = SCRATCH_SP
        s.cs, s.ip = CS, ENTRY
        for _ in range(200_000):
            if (s.ip & 0xFFFF) == SENTINEL_IP:
                return
            cpu.step()
        raise RuntimeError("5F61 did not return")

    assert m.rw(ds, 0xA47E) != 0, "the snapshot must have live enemies (A47E != 0) for the pure case"
    fails = 0
    a7a0_ticks = osc_steps = 0
    for f in range(want):
        before = {off: m.rw(ds, off) for off in FRAME_COUNTER_CELLS}
        run_frame()
        after = {off: m.rw(ds, off) for off in FRAME_COUNTER_CELLS}
        mine = advance_frame_counters_5f61(before)
        a7a0_ticks += after[0xA7A0] != before[0xA7A0]
        osc_steps += after[0x2348] != before[0x2348]
        diffs = {off: (after[off], mine[off]) for off in FRAME_COUNTER_CELLS if after[off] != mine[off]}
        if diffs:
            fails += 1
            if fails <= 6:
                pretty = ", ".join(f"{o:04X}:vm={v[0]:04X}/mine={v[1]:04X}" for o, v in diffs.items())
                print(f"  frame {f}: FAIL {pretty}")

    print(f"frame counters: {want} frames, fails={fails} "
          f"(A7A0 ticked {a7a0_ticks}x ~ every {want/max(a7a0_ticks,1):.1f}, "
          f"oscillator stepped {osc_steps}x)")
    coverage = a7a0_ticks and want >= 8
    print("RESULT:", "PASS -- advance_frame_counters_5f61 matches the original 5F61 cascade"
          if fails == 0 and coverage else "CHECK")
    return 0 if fails == 0 and coverage else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
