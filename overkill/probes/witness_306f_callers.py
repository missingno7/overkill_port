"""Find who calls `1010:306F` during the STEADY per-frame reveal (f478..570), to check whether it's
really the CC4F/CC7F chain (which `witness_cc4f_caller.py` showed fires ONLY ONCE, processing 19 rows
in one shot -- the f477 burst) or a SEPARATE, still-unidentified per-frame driver.

Traps every entry to 1010:306F over a present-frame window and logs the caller's return address (off
SS:SP at entry) plus a present-frame boundary count (reusing the reliable `pump_demo_frame` boundary,
not an approximation).

Usage:
    pypy -m overkill.probes.witness_306f_callers [demo_name] [--frames N] [--from F]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from dos_re.step_probe import install_step_observer  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"
TARGET = (0x1010, 0x306F)


def witness(demo_name: str, max_frames: int, from_frame: int):
    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    tail = str(meta.get("command_tail", ""))

    state = {"f": 0, "ref": None}
    events: list[dict] = []

    def on_ref(cpu):
        f = state["f"]
        if from_frame <= f < from_frame + max_frames:
            cs = cpu.s.cs & 0xFFFF
            ss = cpu.s.ss & 0xFFFF
            ret = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
            events.append({"f": f, "caller": f"{cs:04X}:{ret:04X}"})

    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            state["ref"] = rt
            install_step_observer(rt.cpu, on_ref, trap=frozenset((TARGET,)))
        return rt

    fv._load_runtime = patched

    def pump(ref, cand):
        pump_demo_frame(demo, state["f"], (ref, cand), ref.cpu)
        state["f"] += 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=from_frame + max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0,
                            frame_budget=120_000_000)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=None, command_tail=tail, config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig_load
    return events


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", nargs="?", default=DEFAULT_DEMO)
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--from-frame", type=int, default=440, dest="from_frame")
    args = ap.parse_args(argv)
    events = witness(args.demo, args.frames, args.from_frame)
    print(f"{len(events)} calls to 306F in boundaries [{args.from_frame}, {args.from_frame + args.frames})")
    callers = Counter(e["caller"] for e in events)
    print(f"callers: {callers.most_common(10)}")
    for e in events[:30]:
        print(f"  f={e['f']:4d}  caller={e['caller']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
