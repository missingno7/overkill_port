"""Whole-walk shadow over a HUMAN-PLAYED cold-start demo: every A9D3..AA25 frame, native vs VM.

The free-run shadow (verify_native_behavior_walk) proves the walk on the L1 attract wave only --
no firing, no kills, no scenery interactions.  This probe replays a recorded COLD-START session
(intro -> menu -> the whole played level) through the frame verifier and, on the pure-ASM ``ref``
side, traps EVERY object-walk frame: snapshot at ``1010:A9D3``, let the VM run to ``1010:AA25``,
run the native walk (``run_behavior_walk_a9d3``) on the pre-state copy, and diff the entire 64K
DGROUP (stack window + documented steer scratch excluded).

Frames where the native walk raises :class:`RecoveryGap` are NOT divergence -- they are the
evidence-driven frontier (unrecovered behaviors the played level actually exercises) and are
reported loudly with counts.  PASS requires zero divergence on every frame the walk CAN run, and
reports how many frames were combat-exposed (a live solid gameplay candidate at entry -- i.e. the
62F6 chain had real player shots to see).

Usage:
    python -m overkill.probes.verify_native_walk_demo [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import (  # noqa: E402
    load_demo, run_ref_step_probe, run_ref_step_probe_cold_start,
)
from overkill.recovered.adapters.behavior_walk import run_behavior_walk_a9d3  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402
from overkill.recovered.domain.tilemap import LevelTileContext  # noqa: E402

CS = 0x1010
WALK_ENTRY = 0xA9D3
WALK_END = 0xAA25
DGROUP = 0x25CC
GAMEPLAY_BASE = 0x2B5C
DEFAULT_DEMO = "demo_cold_start_full_20260705_123645"
# out-of-model steer scratch (documented): the 5DB2/5E42 steer globals live OUTSIDE the pure
# islands.  A954 direction bits; 230A blocked flag; 230C/230E/2310 the 5E42 delta-steer scratch
# triple ("not slot state" per domain/movement.DeltaSteerStep).  The attract-wave free run never
# drives delta-steer so it only needed 230E/2310; a player-driven session also toggles 230C.
#
# DS:215A: traced (scratchpad/trace_215a.py, the 2026-07-05 cold-start demo) -- changes ~400 times
# within a few thousand boundaries, written from dozens of addresses (06AB/4EB3/ECCC/024C/0266/
# 0270/02B0/0D33/44AF/5C33/5C99/CD77/CE07/...) that are IRQ/sound/menu machinery, NOT object-behavior
# code; none of the recovered walk handlers touch it.  It is reused as promiscuous low-memory scratch
# across unrelated subroutines -- the shadow snapshots DGROUP at walk-ENTRY and only re-runs the
# object walk, so it can never reproduce a value an ASYNC interrupt handler wrote between entry and
# AA25; excluding it is a methodology fact, not a walk-correctness weakening.
EXCLUDED_CELLS = {0xA954, 0xA955, 0x230A, 0x230B, 0x230C, 0x230D,
                  0x230E, 0x230F, 0x2310, 0x2311, 0x215A, 0x215B}


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else None

    st = {"pre": None, "sp": 0, "plane_seg": None, "plane": None, "classes": None}
    stats = {"frames": 0, "diverged": 0, "combat_exposed": 0}
    gaps: Counter = Counter()
    first_divs: list[str] = []

    def on_ref_step(cpu) -> None:
        if (cpu.s.cs & 0xFFFF) != CS:
            return
        ip = cpu.s.ip & 0xFFFF
        m = cpu.mem
        ds = cpu.s.ds & 0xFFFF
        if ip == WALK_ENTRY and st["pre"] is None:
            # read the tile plane FRESH every frame: the level scrolls and rewrites the plane
            # in place, so a per-segment cache goes stale and spuriously diverges the AD60 tile probe
            seg = m.rw(CS, 0x9592)
            st["plane"] = bytes(m.data[seg * 16:seg * 16 + 0x4000])
            # the class table is read FRESH per frame too: the 0B3E level-data init REBUILDS it at
            # a level transition (and at the death respawn), so a one-shot cache goes stale on any
            # demo that crosses a level end (e.g. the L2_full playthrough)
            st["classes"] = tuple(m.rb(ds, (0xC3AA + i) & 0xFFFF) for i in range(256))
            st["pre"] = bytes(m.data)
            st["sp"] = cpu.s.sp & 0xFFFF
            for i in range(0x22):
                rec = GAMEPLAY_BASE + i * 0x38
                if m.rw(ds, rec) and m.rw(ds, rec + 0x1E):
                    stats["combat_exposed"] += 1
                    break
            return
        if ip == WALK_END and st["pre"] is not None:
            pre, sp = st["pre"], st["sp"]
            st["pre"] = None
            stats["frames"] += 1
            if stats["frames"] % 500 == 0:
                print(f"  ..walk frame {stats['frames']}: diverged={stats['diverged']} "
                      f"distinct-gaps={len(gaps)} combat-exposed={stats['combat_exposed']}"
                      + (f" gaps={sorted(gaps)}" if gaps else ""), flush=True)
            native = MutFlatMemory(pre)
            tiles = LevelTileContext(origin_x_word=native.rw(ds, 0x234E),
                                     row_base_word=native.rw(ds, 0x2350),
                                     tile_plane=st["plane"], class_table=st["classes"])
            try:
                run_behavior_walk_a9d3(native, tiles)
            except RecoveryGap as gap:
                # normalise away the per-record address so the distinct-gap set is the
                # actual behavior/type frontier, not one key per object instance
                key = str(gap).split(" (record ")[0].split(" (candidate ")[0]
                gaps[key] += 1
                return
            base = DGROUP * 16
            vm = bytes(m.data[base:base + 0x10000])
            nat = bytes(native.data[base:base + 0x10000])
            if vm == nat:
                return
            diffs = [o for o in range(0x10000)
                     if vm[o] != nat[o] and o not in EXCLUDED_CELLS
                     and not (sp - 0x60 <= o < sp)]
            if diffs:
                stats["diverged"] += 1
                if len(first_divs) < 12:
                    line = (f"walk frame {stats['frames']}: {len(diffs)}B at "
                            + ",".join(f"DS:{o:04X}(vm={vm[o]:02X}/nat={nat[o]:02X})"
                                       for o in diffs[:6]))
                    first_divs.append(line)
                    print(f"  DIVERGENCE {line}", flush=True)

    if demo.is_cold_start:
        run_ref_step_probe_cold_start(demo, max_frames, on_ref_step)
    else:
        # a snapshot-based demo (the L2/L3/L4/L6 recordings): same trap, the snapshot harness
        frames = (demo.end_boundary + 5) if max_frames is None else max_frames
        run_ref_step_probe(demo, frames, on_ref_step)

    print(f"walk frames shadowed: {stats['frames']}  diverged: {stats['diverged']}  "
          f"combat-exposed: {stats['combat_exposed']}")
    for line in first_divs:
        print(f"  DIVERGENCE {line}")
    if gaps:
        print(f"recovery gaps hit ({sum(gaps.values())} frames NOT natively walkable yet):")
        for text, n in gaps.most_common():
            print(f"  {n:6d}x {text}")
    verdict = stats["diverged"] == 0 and stats["frames"] > 0
    print("RESULT:", ("PASS -- zero divergence on every natively-walkable frame of the played demo"
                      + (" (with the gap frontier above)" if gaps else ""))
          if verdict else "FAIL")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
