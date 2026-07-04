"""Driven-oracle: the six-planet level-index advance vs the ORIGINAL 1010:9744.

Drives the original ``inc [2356] / wrap-at-6`` block with a synthetic ``DS:2356`` and stops at ``9755``,
comparing the resulting ``DS:2356`` to ``systems.menu.advance_level_index_9744``.

Usage:
    python -m overkill.probes.verify_native_level_advance_9744 [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x9744
STOP = 0x9755
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.menu import advance_level_index_9744

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(v2356):
        m.ww(ds, 0x2356, v2356 & 0xFFFF)
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        for _ in range(50):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == STOP:
                break
            cpu.step()
        return m.rw(ds, 0x2356) & 0xFFFF

    fails = 0
    for v in range(0, 9):
        vm = drive(v)
        mine = advance_level_index_9744(v)
        if mine != vm:
            fails += 1
            print("  FAIL 2356=", v, "mine=", mine, "vm=", vm)

    print(f"9744 level-index advance driven-oracle: cases=9 fails={fails}")
    print("RESULT:", "PASS -- advance_level_index_9744 matches the original 9744"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
