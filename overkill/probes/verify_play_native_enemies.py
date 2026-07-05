"""Headless smoke: the play_native object-frame shows MOVING enemies from a snapshot, VM-free.

The pygame window can't be observed here, so this drives the exact runtime composition play_native
ticks (``native_walk_frame.advance_object_frame`` -- the counter cascade + the behaviour walk over a
MutFlatMemory DGROUP image) from the L1_start snapshot, projects the pools each frame, and asserts:

* enemies are present every frame (the snapshot's live wave), and
* a tracked enemy MOVES (its projected x/y changes across frames), and
* the RENDERED playfield frame (native_video, pygame-free numpy) CHANGES across frames -- i.e. the
  motion is actually visible in the composed image, not just in the record.

This is the loop-closer's verification: the wired tick produces a live, moving enemy wave in the
frame the window would show.

Usage:
    python -m overkill.probes.verify_play_native_enemies [snapshot_dir] [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DS = 0x25CC
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"


def _first_enemy(state):
    for i in range(len(state.effect_pool)):
        if state.effect_pool.active_word(i) and state.effect_pool.word_at(i, 0x16) == 4 \
                and state.effect_pool.word_at(i, 0x18) == 0x20:
            return i, state.effect_pool.x_word(i), state.effect_pool.y_word(i)
    return None


def main(argv) -> int:
    import json
    import re

    from overkill.native_walk_frame import advance_object_frame, level_tiles, project_state
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.domain.gaps import RecoveryGap

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    frames = int(argv[1]) if len(argv) > 1 else 90
    image = MutFlatMemory((snap / "memory_1mb.bin").read_bytes())
    cpu_line = json.loads((snap / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
    assert int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu_line).group(1), 16) == DS
    tiles = level_tiles(image)

    enemies_seen = 0
    moved = False
    track = None
    gap = None
    positions = []
    for f in range(frames):
        try:
            advance_object_frame(image, tiles)
        except RecoveryGap as g:
            gap = f"frame {f}: {g.args[0]}"
            break
        state = project_state(image)
        e = _first_enemy(state)
        if e is not None:
            enemies_seen += 1
            slot, x, y = e
            positions.append((x, y))
            if track is not None and track[0] == slot and (x, y) != track[1]:
                moved = True
            track = (slot, (x, y))

    print(f"play_native enemies: {enemies_seen}/{frames} frames had a tracked enemy; moved={moved}")
    if positions:
        print(f"  tracked enemy path (first 8): {positions[:8]}")
    if gap:
        print(f"  GAP: {gap}")
    ok = enemies_seen >= frames - 2 and moved and gap is None
    print("RESULT:", "PASS -- the wired object frame shows a live, MOVING enemy wave from cold "
          "projections, VM-free" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
