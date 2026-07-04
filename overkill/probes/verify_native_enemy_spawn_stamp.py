"""Driven-oracle: the enemy spawn stamp vs the ORIGINAL 1010:81E9..8247 (the level-wave enemy spawner).

Seeds a schedule frame (``ss:[bp+2]``=x, ``ss:[bp+4]``=y), drives the enemy spawner (``81E9`` calls the
``7524`` allocator then stamps), and asserts the freshly-allocated object record holds exactly what
``systems.frame_loop.enemy_spawn_stamp_8209`` predicts.

Usage:
    python -m overkill.probes.verify_native_enemy_spawn_stamp [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x81E9        # call 7524 (allocate the enemy) then stamp
ALLOC_RET = 0x81EC    # after 7524 returns -- BX = the allocated record
STOP = 0x8247         # the ret -- right after the stamp
BP_FRAME = 0x7000     # a safe synthetic stack frame for the x/y schedule entry
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import enemy_spawn_stamp_8209

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    m = cpu.mem

    def drive(x, y):
        s.bp = BP_FRAME
        m.ww(ss, (BP_FRAME + 2) & 0xFFFF, x & 0xFFFF)
        m.ww(ss, (BP_FRAME + 4) & 0xFFFF, y & 0xFFFF)
        s.cs, s.ip = CS, ENTRY
        bx = None
        for _ in range(40000):
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip == ALLOC_RET and bx is None:
                bx = s.bx & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip == STOP:
                break
            cpu.step()
        return bx

    fails = 0
    for x, y in ((0x0140, 0x0050), (0x0080, 0x0030), (0x00C0, 0x0058)):
        bx = drive(x, y)
        model = enemy_spawn_stamp_8209(x, y)
        if bx in (None, 0xFFFF):
            print(f"  x={x:#06x} y={y:#06x}: allocator returned no slot")
            fails += 1
            continue
        bad = [(fo, model[fo], m.rw(ds, (bx + fo) & 0xFFFF) & 0xFFFF)
               for fo in model if (m.rw(ds, (bx + fo) & 0xFFFF) & 0xFFFF) != model[fo]]
        fails += bool(bad)
        tag = "ok" if not bad else "FAIL"
        print(f"  x={x:#06x} y={y:#06x} bx={bx:#06x}: {tag}")
        for fo, want, got in bad:
            print(f"     +{fo:02X}: want {want:04X} got {got:04X}")

    print(f"enemy spawn stamp: fails={fails}")
    print("RESULT:", "PASS -- enemy_spawn_stamp_8209 matches the original 81E9 spawner"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
