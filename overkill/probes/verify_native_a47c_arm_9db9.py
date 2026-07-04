"""Driven-oracle: the 9DB9 A47C-script ARM vs the ORIGINAL 1010:9DB9.

Drives the original bytes across every ``(A97A, A97C, 2384, BDAC, 98C0)`` branch combo (stops at the
rets 9DC0/9DC8/9DE9) and compares ``(A97C, BEFF)`` to ``systems.frame_loop.step_a47c_arm_9db9``.

Usage:
    python -m overkill.probes.verify_native_a47c_arm_9db9 [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x9DB9
STOPS = {0x9DC0, 0x9DC8, 0x9DE9}
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import step_a47c_arm_9db9

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(a97a, a97c, c2384, bdac, c0):
        m.ww(ds, 0xA97A, a97a); m.ww(ds, 0xA97C, a97c); m.ww(ds, 0x2384, c2384)
        m.ww(ds, 0xBDAC, bdac); m.ww(ds, 0x98C0, c0); m.ww(ds, 0xBEFF, 0)
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        for _ in range(2000):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) in STOPS:
                break
            cpu.step()
        return m.rw(ds, 0xA97C) & 0xFFFF, m.rw(ds, 0xBEFF) & 0xFFFF

    fails = 0
    n = 0
    for a97a in (0x58, 0x30):
        for a97c in (1, 0):
            for c2384 in (0, 3):
                for bdac in (1, 0):
                    for c0 in (0, 1):
                        n += 1
                        vm_a97c, vm_beff = drive(a97a, a97c, c2384, bdac, c0)
                        new_a97c, beff = step_a47c_arm_9db9(a97a, a97c, c2384, bdac, c0)
                        mine = (new_a97c, beff if beff is not None else 0)
                        if mine != (vm_a97c, vm_beff):
                            fails += 1
                            print("  FAIL in=", (hex(a97a), a97c, c2384, bdac, c0),
                                  "mine=", tuple(hex(x) for x in mine),
                                  "vm=", (hex(vm_a97c), hex(vm_beff)))

    print(f"9DB9 game-over arm driven-oracle: combos={n} fails={fails}")
    print("RESULT:", "PASS -- step_a47c_arm_9db9 matches the original 9DB9 on every branch"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
