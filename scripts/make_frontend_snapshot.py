"""Create a reusable COLD-BOOT-TO-FRONT-END snapshot so front-end probing stops paying the ~10-minute
cold-boot cost on every attempt.

Front-end work (the intro / attract / menu) has no gameplay demo to seed from, so every probe re-ran
the whole cold boot (LZEXE unpack + init = ~10 min) just to reach the front end.  This tool runs that
boot ONCE, replays the cold-start demo to a target present-frame just before the graphics intro, and
writes a loadable snapshot (`memory_1mb.bin` + `state.json`) to `artifacts/frontend_intro_snapshot/`.

Then a front-end probe loads it INSTANTLY and drives it forward:

    from overkill.runtime import load_overkill_snapshot
    rt = load_overkill_snapshot('assets/OVERKILL', 'artifacts/frontend_intro_snapshot', game_root='assets')
    cpu = rt.cpu
    # The intro paces via RETRACE POLLING (in al,0x3DA), NOT the 1010:0679 timer wait -- so
    # advance_frames_fast and the CS:066B flag-poke do NOT work here.  Raw-step instead (dos_re toggles
    # the 0x3DA retrace bit, so the poll loops complete); ~50k steps/s on PyPy.  Sample B800 (CGA mode 4,
    # decode_cga4) periodically to watch the reveal, or trap a present to get frame boundaries.
    for _ in range(900_000):
        cpu.step()   # ~reaches the composed blueprint

The snapshot is a large game-derived binary -- it is gitignored, recreate it with this tool.

Usage:
    pypy scripts/make_frontend_snapshot.py [--frame N] [--demo NAME] [--out DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402
from dos_re.snapshot import write_snapshot  # noqa: E402


def make(demo_name: str, target_frame: int, out_dir: str) -> None:
    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    # THE COMMAND TAIL IS PART OF THE BOOT.  A cold start must replay the demo's recorded tail
    # (it answers the game's startup prompts -- video/sound selection); booting with an empty tail
    # sends the game down a DIFFERENT path (e.g. CGA mode 4 instead of Tandy mode 9) and every
    # capture from such a snapshot is an artifact.  Mirrors run_ref_step_probe_cold_start.
    tail = str(meta.get("command_tail", ""))
    cur = {"f": 0, "rt": None, "saved": False}
    orig = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, tail):
        rt = orig(exe, assets, snap, tail)
        if next(sides) == "ref":
            cur["rt"] = rt
        return rt

    fv._load_runtime = patched

    def pump(ref, cand):
        rt = cur["rt"]
        f = cur["f"]
        if rt is not None and f == target_frame and not cur["saved"]:
            write_snapshot(rt, out_dir, status=f"cold front-end @f{f}", steps=0)
            cur["saved"] = True
            print(f"SNAPSHOT saved @f{f} cs:ip={rt.cpu.s.cs:04X}:{rt.cpu.s.ip:04X} "
                  f"mode={rt.dos.video_mode} -> {out_dir}")
        pump_demo_frame(demo, f, (ref, cand), ref.cpu)
        cur["f"] = f + 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=target_frame + 2,
                            semantic_state_check=False, stop_on_diff=False, log_every=0,
                            frame_budget=200_000_000)
    try:
        run_frame_verifier(exe=str(ROOT / "assets" / "OVERKILL"), assets=str(ROOT / "assets"),
                           snapshot=None, command_tail=tail, config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig
    if not cur["saved"]:
        raise RuntimeError(f"never reached frame {target_frame} (got {cur['f']})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--frame", type=int, default=410,
                    help="present-frame to snapshot at (default 410: late boot, just before the intro)")
    ap.add_argument("--demo", default="demo_cold_start_intro_20260711_203259")
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "frontend_intro_snapshot"))
    args = ap.parse_args(argv)
    make(args.demo, args.frame, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
