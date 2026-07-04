"""Driven-oracle: the A47C-script ARM gate vs the ORIGINAL 1010:A680.

Drives the original frame block at ``A680`` (which calls the world-scroll ``A6FE`` then a ``C591``
housekeeping call) with synthetic ``(A480, 234E, 2350)`` and observes whether control reaches the
``mov ds:[A47C],1`` arm at ``A6B9`` or bails to ``A6FD`` -- comparing that outcome to
``systems.frame_loop.a47c_script_arms_a680``.  Proves the native ARM (the upstream link that launches
the A47C scripted-input/event script).  NOTE: this arm is scroll-POSITION-gated (234E/2350 are the
scroll cursor); the script it launches is NOT confirmed to be player death -- see the function's
docstring + loop_blockers.md.

Usage:
    python -m overkill.probes.verify_native_a47c_arm_a680 [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xA680
ARM = 0xA6B9      # mov ds:[A47C],1  -- reaching here == the A47C script will arm
NOARM = 0xA6FD    # bail target
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import a47c_script_arms_a680

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(a480, v234e, v2350):
        m.ww(ds, 0xA480, a480 & 0xFFFF)
        m.ww(ds, 0x234E, v234e & 0xFFFF)
        m.ww(ds, 0x2350, v2350 & 0xFFFF)
        m.ww(ds, 0xA47C, 0)
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        for _ in range(20000):
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip in (ARM, NOARM):
                break
            cpu.step()
        return (s.ip & 0xFFFF) == ARM

    combos = []
    for a480 in (0, 1):
        for v234e in (0, 1, 2, 0xFFFF):
            for v2350 in (0x0EA0, 0x0E9F, 0x0EA1, 0x0E52, 0x0000):
                combos.append((a480, v234e, v2350))

    fails = 0
    for a480, v234e, v2350 in combos:
        vm = drive(a480, v234e, v2350)
        mine = a47c_script_arms_a680(a480, v234e, v2350)
        if mine != vm:
            fails += 1
            if fails <= 8:
                print("  FAIL in=", (a480, hex(v234e), hex(v2350)), "mine=", mine, "vm=", vm)

    print(f"A680 A47C-arm gate driven-oracle: combos={len(combos)} fails={fails}")
    print("RESULT:", "PASS -- a47c_script_arms_a680 matches the original A680 arm gate"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
