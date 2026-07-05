"""Cold-populate integration smoke: from the COLD bundle (no snapshot), the level object-script
walker + the behavior walk produce a live, MOVING enemy wave.

This is the end-to-end demonstration behind the "cold level has enemies" milestone -- NOT a
byte-exact oracle (that is verify_native_behavior_walk's job), but a coherence smoke over the whole
native pipeline running from cold data alone:

1. load the static runtime bundle into a MutFlatMemory DGROUP image (no VM);
2. set the level: DS:2356 = 1 (planet 1, the cold-boot LEVEL1), cursor at the planet-1 script head;
3. per frame: advance the scroll row DS:A978 (down from 0x110 -- the entry triggers), tick the
   601E per-frame counter bank (A7A0 wave clock etc.), run the level object-script walker
   (adapters/level_object_script) to spawn as triggers fire, then run the whole behavior walk
   (adapters/behavior_walk) over the cold tile context;
4. observe: the wave controller spawns, then bursts behavior-0x20 enemies, and those enemies MOVE
   (their positions change across frames).

STATUS (2026-07-05): this is the COLD-POPULATE MILESTONE GATE.  It already proves the wave
controller spawns from cold data (frame 0), but it currently reports CHECK: as the level scrolls in
from row 0x110 the script spawns GROUND SCENERY (behaviors 0x19/0x1A -> 1010:BAF0/BAD4, 0x8A ->
8C1F) that the behavior walk has no handler for yet (the mid-level L1_start shadow never reached
them).  Recovering those scenery behaviors (their BB03/C237 scroll-follow tail) is the next target;
then this gate goes PASS and the cold level is truly populated + playable.

Usage:
    python -m overkill.probes.verify_cold_populate [bundle_path] [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DS = 0x25CC
CS = 0x1010
DEFAULT_BUNDLE = "artifacts/static_runtime_bundle/memory_1mb.bin"


def _tick_counter_bank(mem) -> None:
    """The 1010:6003..6046 per-frame counter bank (DGROUP half): the dividers + the A7A0 wave
    clock + the 2324 frame parity that gate the enemy behaviors."""
    mem.ww(DS, 0x233A, 0)
    mem.ww(DS, 0x233E, (mem.rw(DS, 0x233E) + 1) % 3)
    mem.ww(DS, 0x233C, (mem.rw(DS, 0x233C) + 1) & 3)
    mem.ww(DS, 0x2336, (mem.rw(DS, 0x2336) + 1) & 7)
    mem.ww(DS, 0xA7A0, (mem.rw(DS, 0xA7A0) + 1) & 0xFFFF)
    mem.ww(DS, 0x2324, mem.rw(DS, 0x2324) ^ 1)
    mem.ww(DS, 0x2326, (mem.rw(DS, 0x2326) + 1) & 3)
    mem.ww(DS, 0x2328, (mem.rw(DS, 0x2328) + 1) & 7)
    mem.ww(DS, 0x2338, (mem.rw(DS, 0x2338) + 1) & 0xFFFF)


def _census(mem):
    controllers = enemies = shots = 0
    sample = None
    for table, n in ((0x32CA, 0x23), (0x8D12, 0x22)):
        for cx in range(1, n + 1):
            rec = mem.rw(DS, table + cx * 2)
            if not rec or mem.rw(DS, rec) == 0:
                continue
            if mem.rw(DS, rec + 0x16) not in (2, 4):
                continue
            beh = mem.rw(DS, rec + 0x18)
            if beh == 0x1F:
                controllers += 1
            elif beh == 0x20:
                enemies += 1
                if sample is None:
                    sample = (rec, mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04))
            elif beh == 0x0B:
                shots += 1
    return controllers, enemies, shots, sample


def main(argv) -> int:
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.adapters.behavior_walk import run_behavior_walk_a9d3
    from overkill.recovered.adapters.level_object_script import run_level_object_script_4a65
    from overkill.recovered.domain.gaps import RecoveryGap
    from overkill.recovered.domain.tilemap import LevelTileContext

    bundle = Path(argv[0]) if argv else ROOT / DEFAULT_BUNDLE
    frames = int(argv[1]) if len(argv) > 1 else 160
    mem = MutFlatMemory(bundle.read_bytes())

    mem.ww(DS, 0x2356, 1)                                    # planet 1 = the cold-boot LEVEL1
    plane_seg = mem.rw(CS, 0x9592)
    tiles = LevelTileContext(
        origin_x_word=mem.rw(DS, 0x234E), row_base_word=mem.rw(DS, 0x2350),
        tile_plane=bytes(mem.data[plane_seg * 16:plane_seg * 16 + 0x4000]),
        class_table=tuple(mem.rb(DS, (0xC3AA + i) & 0xFFFF) for i in range(256)))

    row = 0x0110                                             # the scroll row the first entry triggers on
    ever_enemies = 0
    moved = False
    sample_track = None
    gaps = []
    for f in range(frames):
        mem.ww(DS, 0xA978, row & 0xFFFF)
        try:
            run_level_object_script_4a65(mem)
        except RecoveryGap as g:
            gaps.append((f, "script", str(g.args[0])))
        _tick_counter_bank(mem)
        try:
            run_behavior_walk_a9d3(mem, tiles)
        except RecoveryGap as g:
            gaps.append((f, "walk", str(g.args[0])))
        c, e, s, sample = _census(mem)
        ever_enemies = max(ever_enemies, e)
        if sample is not None:
            if sample_track is not None and sample[0] == sample_track[0] \
                    and (sample[1], sample[2]) != (sample_track[1], sample_track[2]):
                moved = True
            sample_track = sample
        if f < 6 or f % 40 == 0 or (e and f % 8 == 0):
            print(f"  frame {f:3d} row {row:04X}: controllers={c} enemies={e} shots={s} A7A0={mem.rw(DS,0xA7A0):04X}")
        if row > 0:
            row -= 1

    print(f"cold populate: peak enemies={ever_enemies}, a tracked enemy moved={moved}, "
          f"gap-frames={len(gaps)}")
    for f, where, msg in gaps[:4]:
        print(f"    gap @ frame {f} ({where}): {msg}")
    ok = ever_enemies >= 5 and moved and not gaps
    print("RESULT:", "PASS -- the cold level populates with a moving enemy wave, VM-free"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
