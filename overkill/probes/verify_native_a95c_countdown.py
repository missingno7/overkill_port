"""Driven-oracle: the A95C difficulty countdown vs the ORIGINAL 1010:9E43 (a death-island leaf).

Drives the original bytes with a synthetic ``(BEDC, A95C)`` and stops at ``9E63`` (reload) or ``9EC2``
(continue), comparing ``DS:A95C`` + which exit to ``systems.frame_loop.step_a95c_difficulty_countdown_9e43``.
Exercises each BEDC decrement (1/2/3) and both the continue and the reload-at-0 paths.

Usage:
    python -m overkill.probes.verify_native_a95c_countdown [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x9E43
# the reload path runs `mov A95C,0x18` at 9E63 then falls to 9E69 -- stop AFTER the reload (9E69) so
# the observed A95C is the reloaded value; the continue path stops at its 9EC2 jump.
RELOAD, CONTINUE = 0x9E69, 0x9EC2
STOPS = {RELOAD, CONTINUE}
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"
# (BEDC, A95C): each BEDC decrement + both continue and reload-at-0 paths.
COMBOS = [(0, 5), (0, 1), (1, 5), (1, 2), (1, 1), (2, 5), (2, 3), (3, 4), (5, 10), (2, 1)]


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import step_a95c_difficulty_countdown_9e43

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(bedc, a95c):
        m.ww(ds, 0xBEDC, bedc & 0xFFFF)
        m.ww(ds, 0xA95C, a95c & 0xFFFF)
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        stop = None
        for _ in range(2000):
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip in STOPS:
                stop = ip
                break
            cpu.step()
        return m.rw(ds, 0xA95C) & 0xFFFF, stop

    fails = []
    for bedc, a95c in COMBOS:
        vm_a95c, vm_stop = drive(bedc, a95c)
        new_a95c, reloaded = step_a95c_difficulty_countdown_9e43(bedc, a95c)
        mine_stop = RELOAD if reloaded else CONTINUE
        if (new_a95c, mine_stop) != (vm_a95c, vm_stop):
            fails.append(((bedc, hex(a95c)), (hex(new_a95c), hex(mine_stop)),
                          (hex(vm_a95c), hex(vm_stop) if vm_stop else None)))

    print(f"A95C difficulty countdown (9E43) driven-oracle: combos={len(COMBOS)} fails={len(fails)}")
    for f in fails:
        print("  FAIL in=", f[0], "mine=", f[1], "vm=", f[2])
    ok = not fails
    print("RESULT:", "PASS -- step_a95c_difficulty_countdown_9e43 matches the original 9E43 on every branch"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
