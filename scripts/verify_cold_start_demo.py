"""Verify a COLD-START input demo: does the native runtime behave exactly like the real game, from boot?

A cold-start demo (recorded with ``scripts/play.py --record-demo NAME`` on a fresh boot, ideally with
``--no-replacements`` so the captured input is pure-ASM ground truth) has NO start snapshot -- it replays
from power-on.  This harness boots two fresh runtimes and replays the recorded input into both, frame by
frame: the frame verifier's REFERENCE keeps only the env (timer/retrace) hooks, so it is the pure original
ASM (the real game); the CANDIDATE is the full hybrid (every recovered native hook).  Zero divergence means
the native hooks reproduce the real game across the WHOLE recorded session -- intro, menu, and gameplay --
from a cold boot with no snapshot.

    python scripts/verify_cold_start_demo.py <cold-start-demo-dir> [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))  # submodule repo root (no editable install under PyPy)

from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    demo = InputDemoPlayback.load(argv[0])
    max_frames = int(argv[1]) if len(argv) > 1 else 100000

    meta = demo.manifest.get("metadata", {})
    if not demo.is_cold_start:
        print(f"ERROR: {argv[0]} is not a cold-start demo (it has a start snapshot); "
              f"use the normal frame verifier for snapshot demos.")
        return 2
    video = str(meta.get("video", "tandy"))
    command_tail = str(meta.get("command_tail", ""))
    end = demo.end_boundary
    print(f"cold-start demo: {argv[0]}")
    print(f"  video={video} events={len(demo.events)} end_boundary={end} "
          f"recorded_no_replacements={meta.get('no_replacements')}")

    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt) -> None:
        boundary["n"], _ = pump_demo_frame(demo, boundary["n"], (ref_rt, cand_rt), ref_rt.cpu)
        boundary["n"] += 1

    # Frame 1 runs the whole boot: in the pure-ASM reference that is the REAL (slow) LZEXE self-unpack +
    # init, which the hybrid fast-forwards with a boot hook.  Give it a large per-frame budget so the real
    # boot completes; gameplay frames still terminate at their boundary long before this cap.
    cfg = FrameVerifyConfig(video=video, source="candidate",
                            max_frames=end + 5 if end is not None else max_frames,
                            semantic_state_check=False, stop_on_diff=True, log_every=0,
                            frame_budget=120_000_000)
    rc = run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                            snapshot=None, command_tail=command_tail, config=cfg, pump_inputs=pump_inputs)
    if rc == 0:
        print("RESULT: PASS -- the hybrid native runtime matched the pure-ASM real game across the "
              "whole cold-start demo (no divergence)")
    else:
        print("RESULT: DIVERGENCE -- the native runtime diverged from the real game (see the frame report "
              "above for the first diverging frame)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
