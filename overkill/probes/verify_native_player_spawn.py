"""Driven-oracle: the player spawn stamp vs the ORIGINAL 1010:C42F..C44B (Bucket-F player spawn).

Drives the player-record stamp inside the level/respawn re-init (C3A6) and asserts the DS:237C record
holds exactly what ``systems.frame_loop.player_spawn_record_c42f`` predicts (active + spawn position +
type fields).

Usage:
    python -m overkill.probes.verify_native_player_spawn [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xC42F   # mov bp,237C
STOP = 0xC450    # call 7524 -- right after the record stamp
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import player_spawn_record_c42f, PLAYER_SPAWN_RECORD

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ss = s.ss & 0xFFFF
    m = cpu.mem

    model = player_spawn_record_c42f()
    for fo in model:  # sentinel so a missed write shows
        m.ww(ss, (PLAYER_SPAWN_RECORD + fo) & 0xFFFF, 0xDEAD)

    s.cs, s.ip = CS, ENTRY
    for _ in range(400):
        if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == STOP:
            break
        cpu.step()
    reached = (s.ip & 0xFFFF) == STOP

    fails = 0
    for fo, want in model.items():
        got = m.rw(ss, (PLAYER_SPAWN_RECORD + fo) & 0xFFFF) & 0xFFFF
        ok = got == want
        fails += not ok
        print(f"  237C+{fo:02X} = {got:04X}  want {want:04X}  {'ok' if ok else 'FAIL'}")

    print(f"player spawn stamp: fields={len(model)} fails={fails} reached_stop={reached}")
    ok = reached and not fails
    print("RESULT:", "PASS -- player_spawn_record_c42f matches the original C42F spawn stamp"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
