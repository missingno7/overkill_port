"""Witness EVERY registered VM hook that fires inside a present-frame boundary window of a cold-start
demo -- a broad net for locating an unidentified per-frame routine (e.g. the cold-boot blueprint
char-writer) when the specific candidates already tried (519A/3153 text path, etc) show zero hits.

Wraps every ``dos_re.hooks.registry`` replacement for CS=0x1010 with a counting/logging shim, replays
the demo through the window, and reports which hook names fired and how many times, broken out by
present-frame boundary so a routine that fires ~once per frame (matching a ~12px/frame reveal rate)
stands out from setup-only or once-total routines.

Usage:
    pypy -m overkill.probes.witness_all_hooks_window [demo_name] [--frames N] [--from F]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"


def witness(demo_name: str, max_frames: int, from_frame: int):
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry

    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    tail = str(meta.get("command_tail", "")) if demo.is_cold_start else b""

    state = {"f": 0, "ref": None}
    hits: Counter = Counter()
    per_frame_hits: "dict[int, Counter]" = defaultdict(Counter)

    originals = {}
    for key, rep in list(registry.replacements.items()):
        cs, ip = key
        if cs != 0x1010:
            continue
        originals[key] = rep.handler

        def make_wrapped(rep=rep, key=key, orig=rep.handler):
            def wrapped(cpu):
                f = state["f"]
                if from_frame <= f < from_frame + max_frames:
                    hits[key] += 1
                    per_frame_hits[f][key] += 1
                orig(cpu)
            return wrapped

        object.__setattr__(rep, "handler", make_wrapped())

    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            state["ref"] = rt
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
        for key, rep in registry.replacements.items():
            if key in originals:
                object.__setattr__(rep, "handler", originals[key])
    return hits, per_frame_hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", nargs="?", default=DEFAULT_DEMO)
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--from-frame", type=int, default=440, dest="from_frame")
    args = ap.parse_args(argv)
    hits, per_frame_hits = witness(args.demo, args.frames, args.from_frame)
    print(f"hooks fired in boundaries [{args.from_frame}, {args.from_frame + args.frames}):")
    for (cs, ip), n in hits.most_common(40):
        frames_hit = sum(1 for f, c in per_frame_hits.items() if (cs, ip) in c)
        print(f"  {cs:04X}:{ip:04X}  hits={n:6d}  in {frames_hit} distinct frames "
              f"(avg {n / max(frames_hit, 1):.2f}/frame)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
