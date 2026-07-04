"""Driven-oracle: the player companion-object stamp vs the ORIGINAL 1010:C453..C45F.

Drives the player spawn's companion allocation (``C450`` calls the ``7524`` allocator) and asserts the
freshly-allocated object record holds exactly what ``systems.frame_loop.player_companion_spawn_c453``
predicts (active + logic/type fields), on whatever slot the allocator returned.

Usage:
    python -m overkill.probes.verify_native_player_companion_spawn [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xC450   # call 7524 (allocate the companion)
ALLOC_RET = 0xC453   # the instruction after 7524 returns -- BX = the allocated record
STOP = 0xC461    # just after the companion stamp
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import player_companion_spawn_c453

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    model = player_companion_spawn_c453()
    s.cs, s.ip = CS, ENTRY
    bx_alloc = None
    for _ in range(40000):
        ip = s.ip & 0xFFFF
        if (s.cs & 0xFFFF) == CS and ip == ALLOC_RET and bx_alloc is None:
            bx_alloc = s.bx & 0xFFFF
        if (s.cs & 0xFFFF) == CS and ip == STOP:
            break
        cpu.step()
    reached = (s.ip & 0xFFFF) == STOP

    fails = 0
    if bx_alloc is None:
        print("  did not observe the allocator return")
        fails = 1
    else:
        for fo, want in model.items():
            got = m.rw(ds, (bx_alloc + fo) & 0xFFFF) & 0xFFFF
            ok = got == want
            fails += not ok
            print(f"  companion[{bx_alloc:04X}+{fo:02X}] = {got:04X}  want {want:04X}  {'ok' if ok else 'FAIL'}")

    print(f"player companion spawn: fields={len(model)} fails={fails} reached_stop={reached}")
    ok = reached and not fails
    print("RESULT:", "PASS -- player_companion_spawn_c453 matches the original C453 stamp"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
