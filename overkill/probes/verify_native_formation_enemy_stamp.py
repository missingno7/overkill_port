"""Driven-oracle: the B5E6 formation-enemy stamp vs the ORIGINAL 1010:B5E6 (the wave iterator step).

Points the schedule cursor ``DS:A8D0`` at a synthetic ``(x, y)`` entry, drives the formation iterator
``B5E6`` (which calls the ``81F4`` spawn then applies the schedule position + overrides), and asserts the
spawned enemy's SCHEDULE-driven fields match ``systems.frame_loop.formation_enemy_stamp_b5e6`` (``+0x02``/
``+0x04`` are leader-context and deliberately not checked).

Usage:
    python -m overkill.probes.verify_native_formation_enemy_stamp [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xB5E6
ALLOC_RET = 0xB5EE   # after 81F4 returns -- BX = the allocated enemy
STOP = 0xB612        # jmp BC4B -- right after the stamp + cursor advance
SCRATCH = 0x7100     # a scratch DS area for the synthetic (x,y) schedule entry
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import formation_enemy_stamp_b5e6

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    def drive(x, y):
        m.ww(ds, SCRATCH, x & 0xFFFF)
        m.ww(ds, (SCRATCH + 2) & 0xFFFF, y & 0xFFFF)
        m.ww(ds, 0xA8D0, SCRATCH)
        s.cs, s.ip = CS, ENTRY
        bx = None
        for _ in range(40000):
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip == ALLOC_RET and bx is None:
                bx = s.bx & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip == STOP:
                break
            cpu.step()
        return bx, (m.rw(ds, 0xA8D0) & 0xFFFF)

    fails = 0
    for x, y in ((0x0050, 0x00A8), (0x0038, 0x0018), (0x0020, 0x0060)):
        bx, cursor_after = drive(x, y)
        model = formation_enemy_stamp_b5e6(x, y)
        if bx in (None, 0xFFFF):
            print(f"  x={x:#06x} y={y:#06x}: no slot"); fails += 1; continue
        bad = [(fo, model[fo], m.rw(ds, (bx + fo) & 0xFFFF) & 0xFFFF)
               for fo in model if (m.rw(ds, (bx + fo) & 0xFFFF) & 0xFFFF) != model[fo]]
        advanced = cursor_after == ((SCRATCH + 4) & 0xFFFF)   # cursor += 4 (one x,y pair)
        ok = not bad and advanced
        fails += not ok
        print(f"  x={x:#06x} y={y:#06x} bx={bx:#06x} cursor+4={advanced}: {'ok' if ok else 'FAIL'}")
        for fo, want, got in bad:
            print(f"     +{fo:02X}: want {want:04X} got {got:04X}")

    print(f"formation-enemy stamp: fails={fails}")
    print("RESULT:", "PASS -- formation_enemy_stamp_b5e6 matches the original B5E6 iterator step"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
