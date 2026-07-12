"""GROUND TRUTH #2: the per-frame DGROUP WRITE-SET of the cold-start front end.

A native front-end frame (the thing the front-end lockstep will run at each 50C9 retrace boundary)
must reproduce exactly the DGROUP cells the VM changes between two boundaries.  This probe replays a
cold-start demo through the pure ref VM, snapshots the whole 64K DGROUP at every front-end boundary,
and reports which cells change and HOW OFTEN -- separating the small per-frame STATE (counters /
scene machine, changed almost every frame) from the bursty rendering / page loads (changed rarely).
That per-frame state set is the concrete spec for the native front-end frame -- no guessing.

Usage:
    python scripts/probe_frontend_writeset.py <demo_name> [--frames N] [--skip N]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402


def capture_writeset(demo_name: str, max_frames: int, skip: int):
    """Replay the cold demo; return (changed_counts, n_pairs, scene_at, cs_at) over the boundaries in
    [skip, skip+max_frames).  ``changed_counts[cell]`` = how many frame-pairs changed that DGROUP cell."""
    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    tail = str(meta.get("command_tail", "")) if demo.is_cold_start else b""

    changed: Counter = Counter()
    state = {"f": 0, "ref": None, "prev": None, "pairs": 0, "scene": {}, "cs": {}}
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            state["ref"] = rt
        return rt

    fv._load_runtime = patched

    def pump(ref, cand):
        f = state["f"]
        rt = state["ref"]
        if rt is not None and skip <= f < skip + max_frames:
            ds = rt.cpu.s.ds & 0xFFFF
            cur = bytes(rt.cpu.mem.block(ds, 0, 0x10000))
            prev = state["prev"]
            if prev is not None and len(prev) == len(cur):
                for i in range(0x10000):
                    if cur[i] != prev[i]:
                        changed[i] += 1
                state["pairs"] += 1
            state["prev"] = cur
            state["scene"][f] = rt.cpu.mem.rb(ds, 0xBE06)
            state["cs"][f] = f"{rt.cpu.s.cs:04X}:{rt.cpu.s.ip:04X}"
        pump_demo_frame(demo, f, (ref, cand), ref.cpu)
        state["f"] = f + 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=skip + max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0,
                            frame_budget=120_000_000)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=None, command_tail=tail, config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig_load
    return changed, state["pairs"], state["scene"], state["cs"]


def _ranges(cells):
    cells = sorted(cells)
    out, start, prev = [], None, None
    for c in cells:
        if start is None:
            start = prev = c
        elif c == prev + 1:
            prev = c
        else:
            out.append((start, prev)); start = prev = c
    if start is not None:
        out.append((start, prev))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--skip", type=int, default=0, help="skip this many boundaries first (reach a phase)")
    args = ap.parse_args(argv)
    changed, pairs, scene, cs = capture_writeset(args.demo, args.frames, args.skip)
    print(f"boundaries {args.skip}..{args.skip + args.frames}: {pairs} frame-pairs diffed")
    print(f"scene[BE06] seen: {sorted(set(scene.values()))}  sample CS:IP: "
          f"{sorted(set(cs.values()))[:6]}")
    per_frame = sorted(c for c, n in changed.items() if n >= pairs * 0.9)
    occasional = sorted(c for c, n in changed.items() if n < pairs * 0.9)
    print(f"\nPER-FRAME state cells (changed in >=90% of frames) -- {len(per_frame)} cells:")
    for lo, hi in _ranges(per_frame):
        print(f"  {lo:04X}" + (f"..{hi:04X}" if hi != lo else ""))
    print(f"\nOCCASIONAL cells (transitions / rendering) -- {len(occasional)} cells in "
          f"{len(_ranges(occasional))} ranges (not listed; the bursty page/render writes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
