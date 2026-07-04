"""Driven-oracle: the composed 99F6 A47C handler 9A16 vs the ORIGINAL 1010:9A16 (A47C==3 script step).

Drives the original handler (which itself calls 9DB9 + 9DEA) with a synthetic state, seeds ``A47C = 3``,
runs to its ret, and compares the handler's script state -- ``98BE`` (scripted input), ``A97C``,
``A95A``, ``A95C``, and whether ``A47C`` advanced (3 -> 4) -- to
``systems.frame_loop.step_a47c_handler_9a16``.  Proves the native COMPOSITION of the recovered
sub-steps + the A47C-advance gate.

Usage:
    python -m overkill.probes.verify_native_a47c_handler_9a16 [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x9A16
RETS = {0x9A28, 0x9A30, 0x9A38, 0x9A3D}
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import step_a47c_handler_9a16

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(a97a, a97c, a95a, a95c, c2384, bdac, c0):
        for off, v in ((0xA97A, a97a), (0xA97C, a97c), (0xA95A, a95a), (0xA95C, a95c),
                       (0x2384, c2384), (0xBDAC, bdac), (0x98C0, c0), (0xA47C, 3), (0x98BE, 0)):
            m.ww(ds, off, v & 0xFFFF)
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        for _ in range(4000):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) in RETS:
                break
            cpu.step()
        return (m.rb(ds, 0x98BE), m.rw(ds, 0xA97C) & 0xFFFF, m.rw(ds, 0xA95A) & 0xFFFF,
                m.rw(ds, 0xA95C) & 0xFFFF, (m.rw(ds, 0xA47C) & 0xFFFF) == 4)

    # combos: vary the fields the handler's gate + sub-steps depend on
    combos = []
    for a97a in (0x58, 0x30):
        for a95a in (0x03, 0x02):
            for a95c in (0x18, 0x17, 0x05):
                for a97c in (0, 1):
                    combos.append((a97a, a97c, a95a, a95c, 0, 0, 1))

    fails = 0
    for c in combos:
        vm = drive(*c)
        mine = step_a47c_handler_9a16(*c)
        if tuple(mine) != tuple(vm):
            fails += 1
            if fails <= 8:
                print("  FAIL in=", (hex(c[0]), c[1], hex(c[2]), hex(c[3])),
                      "mine=", tuple(hex(x) if isinstance(x, int) else x for x in mine),
                      "vm=", tuple(hex(x) if isinstance(x, int) else x for x in vm))

    print(f"9A16 death handler driven-oracle: combos={len(combos)} fails={fails}")
    print("RESULT:", "PASS -- step_a47c_handler_9a16 matches the original 9A16 composition"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
