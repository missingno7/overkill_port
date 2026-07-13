"""Gate: `1010:CC4F` (`overkill_dirty_cell_presenter_scene_setup_cc4f`) byte-exact vs the pure VM.

Replays a cold-start demo through the frame verifier with the CC4F hook installed on the candidate
side only (the ref side runs hooks-stripped, per the standard `run_frame_verifier` split) and asserts
zero DGROUP divergence -- the hook is either byte-exact or this fails loud at the first differing
present-frame, per the demo-lockstep discipline (never fake a gap).

Usage:
    pypy -m overkill.probes.verify_native_cc4f_scene_setup [demo_name] [--frames N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.hooks  # noqa: F401,E402 -- registers overkill_dirty_cell_presenter_scene_setup_cc4f
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"


def verify(demo_name: str, max_frames: "int | None") -> None:
    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    tail = str(meta.get("command_tail", "")) if demo.is_cold_start else b""
    frames = (demo.end_boundary + 5) if max_frames is None else max_frames

    state = {"f": 0}

    def pump(ref, cand):
        pump_demo_frame(demo, state["f"], (ref, cand), ref.cpu)
        state["f"] += 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=frames,
                            semantic_state_check=False, stop_on_diff=True, log_every=0,
                            frame_budget=120_000_000)
    run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                       snapshot=None, command_tail=tail, config=cfg, pump_inputs=pump)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", nargs="?", default=DEFAULT_DEMO)
    ap.add_argument("--frames", type=int, default=None)
    args = ap.parse_args(argv)
    verify(args.demo, args.frames)
    print("CC4F scene setup: PASS (0 divergence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
