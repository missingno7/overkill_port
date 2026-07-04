"""Driven-oracle: the level-start control-cell reset vs the ORIGINAL 1010:C51D..C559.

Prefills the target cells with a sentinel, drives the original constant-store block (C51D) to C55F,
and asserts every cell holds exactly what ``systems.frame_loop.level_start_control_reset_c51d`` says.

Usage:
    python -m overkill.probes.verify_native_level_start_control_reset_c51d [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xC51D
STOP = 0xC55F
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import level_start_control_reset_c51d

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    expected = level_start_control_reset_c51d()
    for off in expected:
        m.ww(ds, off, 0xDEAD)  # sentinel so we prove each cell is actually written
    s = cpu.s
    s.cs, s.ip = CS, ENTRY
    for _ in range(80):
        if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == STOP:
            break
        cpu.step()

    fails = 0
    for off, want in expected.items():
        got = m.rw(ds, off) & 0xFFFF
        if got != want:
            fails += 1
            print(f"  FAIL {off:04X}: want {want:04X} got {got:04X}")

    reached = (s.ip & 0xFFFF) == STOP
    print(f"C51D level-start control reset: cells={len(expected)} fails={fails} reached_stop={reached}")
    ok = reached and not fails
    print("RESULT:", "PASS -- level_start_control_reset_c51d matches the original C51D block"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
