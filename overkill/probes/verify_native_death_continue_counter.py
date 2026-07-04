"""Driven-oracle: the DS:2358 lives/continue-counter update vs the ORIGINAL 1010:9908 / 1010:9902.

Drives the death handler (9908) and the game-over entry (9902) with a synthetic ``(2358, 978D)``, runs
to ``991A`` (just past the counter update, before the BEFF-driven respawn/game-over branch), and compares
``DS:2358`` to ``systems.frame_loop.death_continue_counter_update``.

Usage:
    python -m overkill.probes.verify_native_death_continue_counter [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
STOP = 0x991A
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import (
        death_continue_counter_update, GAMEPLAY_EXIT_GAME_OVER_9902, GAMEPLAY_EXIT_DEATH_9908,
    )

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    def drive(entry, lives, f978d):
        m.ww(ds, 0x2358, lives & 0xFFFF)
        m.wb(ds, 0x978D, f978d & 0xFF)
        s.cs, s.ip = CS, entry
        for _ in range(80000):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == STOP:
                break
            cpu.step()
        return m.rw(ds, 0x2358) & 0xFFFF

    fails = 0
    for entry, is_go in ((GAMEPLAY_EXIT_DEATH_9908, False), (GAMEPLAY_EXIT_GAME_OVER_9902, True)):
        for lives in (3, 1, 0):
            for f in (0, 1):
                vm = drive(entry, lives, f)
                mine = death_continue_counter_update(is_go, lives, f)
                ok = vm == mine
                fails += not ok
                tag = "game_over" if is_go else "death"
                print(f"  {tag} lives={lives} 978d={f}: vm={vm:04X} mine={mine:04X} {'ok' if ok else 'FAIL'}")

    print(f"death/game-over continue-counter: fails={fails}")
    print("RESULT:", "PASS -- death_continue_counter_update matches the original 9908/9902"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
