"""Driven-oracle: the 9A3E scripted-move counter update vs the ORIGINAL 1010:9A3E (A47C==2 head).

Drives the original bytes with a synthetic ``(2384, A39C, A39A)`` and stops at ``9A73`` (the end of the
counter update, before the spawn/movement tail), comparing ``(A39C, A39A)`` to
``systems.frame_loop.step_scripted_move_counters_9a3e``.

Usage:
    python -m overkill.probes.verify_native_scripted_move_counters_9a3e [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x9A3E
STOP = 0x9A73
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"
COMBOS = [
    (0, 0x05, 0xFFFA), (0, 0x08, 0xFFF8), (0, 0x07, 0xFFF9),
    (1, 0x05, 0xFFF5), (1, 0x0F, 0xFFF1), (1, 0x0E, 0xFFF2), (3, 0x00, 0xFFFF),
]


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import step_scripted_move_counters_9a3e

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(c2384, a39c, a39a):
        m.ww(ds, 0x2384, c2384 & 0xFFFF)
        m.ww(ds, 0xA39C, a39c & 0xFFFF)
        m.ww(ds, 0xA39A, a39a & 0xFFFF)
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        for _ in range(2000):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == STOP:
                break
            cpu.step()
        return m.rw(ds, 0xA39C) & 0xFFFF, m.rw(ds, 0xA39A) & 0xFFFF

    fails = []
    for c2384, a39c, a39a in COMBOS:
        vm = drive(c2384, a39c, a39a)
        mine = step_scripted_move_counters_9a3e(c2384, a39c, a39a)
        if tuple(mine) != tuple(vm):
            fails.append(((c2384, hex(a39c), hex(a39a)), tuple(hex(x) for x in mine), tuple(hex(x) for x in vm)))

    print(f"9A3E scripted-move counters driven-oracle: combos={len(COMBOS)} fails={len(fails)}")
    for f in fails:
        print("  FAIL in=", f[0], "mine=", f[1], "vm=", f[2])
    ok = not fails
    print("RESULT:", "PASS -- step_scripted_move_counters_9a3e matches the original 9A3E"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
