"""Driven-oracle: the A97A game-over countdown vs the ORIGINAL 1010:9EE4 (a death-island leaf).

Drives the original bytes with a synthetic ``DS:A97A`` and stops at the three exits -- ``9EEB`` (the
``A97A == 0`` no-op ret), ``9EF2`` (game over reached -> jmp 77DF), ``9EF5`` (still counting) -- and
compares ``DS:A97A`` + which exit to ``systems.frame_loop.step_game_over_countdown_9ee4``.

Usage:
    python -m overkill.probes.verify_native_a97a_game_over [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x9EE4
# dec-to-0 (game over) takes the 9EF5 final path (2384/BEFF setup); dec-to-nonzero falls to 9EF2.
RET_NOOP, REACHED_ZERO, STILL_COUNTING = 0x9EEB, 0x9EF5, 0x9EF2
STOPS = {RET_NOOP, REACHED_ZERO, STILL_COUNTING}
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"
COMBOS = [0x0000, 0x0001, 0x0002, 0x0057, 0x00FF]


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import step_game_over_countdown_9ee4

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(a97a):
        m.ww(ds, 0xA97A, a97a & 0xFFFF)
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        stop = None
        for _ in range(2000):
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip in STOPS:
                stop = ip
                break
            cpu.step()
        return m.rw(ds, 0xA97A) & 0xFFFF, stop

    fails = []
    for a97a in COMBOS:
        vm_a97a, vm_stop = drive(a97a)
        new_a97a, reached_zero, rets_early = step_game_over_countdown_9ee4(a97a)
        mine_stop = RET_NOOP if rets_early else (REACHED_ZERO if reached_zero else STILL_COUNTING)
        if (new_a97a, mine_stop) != (vm_a97a, vm_stop):
            fails.append((hex(a97a), (hex(new_a97a), hex(mine_stop)),
                          (hex(vm_a97a), hex(vm_stop) if vm_stop else None)))

    print(f"A97A game-over countdown (9EE4) driven-oracle: combos={len(COMBOS)} fails={len(fails)}")
    for f in fails:
        print("  FAIL in=", f[0], "mine=", f[1], "vm=", f[2])
    ok = not fails
    print("RESULT:", "PASS -- step_game_over_countdown_9ee4 matches the original 9EE4 on every branch"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
