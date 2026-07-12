"""GROUND TRUTH: capture the cold-start demo's FRONT-END timeline from the pure reference VM.

play_native's front end (intro / menu / attract) is currently host-loop code that GUESSES the flow --
it is verified against nothing, so it drifts from the game.  This probe records what the ORIGINAL
actually does at every present-frame boundary of a cold-start demo: the attract scene id [BE06], its
countdown [BE08], the front-end START flag [98C3], and the CPU location (which distinguishes the
front-end loop from the 97B2 gameplay frame).  It is the reference the native front-end must reproduce
byte-for-byte -- the data that replaces guessing.

Usage:
    python scripts/probe_coldstart_frontend.py <demo_name> [--frames N]
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
from overkill.probes._harness import load_demo  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402


def capture(demo_name: str, max_frames: int) -> "list[dict]":
    """Replay the cold-start demo through the ref VM; per present-frame record the front-end state."""
    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    is_cold = demo.is_cold_start
    tail = str(meta.get("command_tail", "")) if is_cold else b""

    rows: "list[dict]" = []
    cur = {"f": 0, "ref": None}
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            cur["ref"] = rt
        return rt

    fv._load_runtime = patched

    def pump(ref, cand):
        rt = cur["ref"]
        if rt is not None:
            ds = rt.cpu.s.ds & 0xFFFF
            def rb(o):
                return rt.cpu.mem.rb(ds, o & 0xFFFF)
            rows.append({
                "f": cur["f"],
                "cs_ip": f"{rt.cpu.s.cs:04X}:{rt.cpu.s.ip:04X}",
                "ds": f"{ds:04X}",
                "scene_BE06": rb(0xBE06),
                "count_BE08": rb(0xBE08),
                "start_98C3": rb(0x98C3),
            })
        pump_demo_frame(demo, cur["f"], (ref, cand), ref.cpu)
        cur["f"] += 1

    budget = {"frame_budget": 120_000_000} if is_cold else {}
    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0, **budget)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=(None if is_cold else demo.snapshot_path()),
                           command_tail=tail, config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig_load
    return rows


def _phase(row) -> str:
    cs = row["cs_ip"].split(":")[0]
    return "gameplay(97B2)" if cs == "1010" and 0x9000 <= int(row["cs_ip"].split(":")[1], 16) <= 0x9FFF \
        else "front-end"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo")
    ap.add_argument("--frames", type=int, default=400)
    ap.add_argument("--raw", type=int, default=0, metavar="START",
                    help="print EVERY frame in [START, START+40) raw (to see the exact countdown)")
    args = ap.parse_args(argv)
    rows = capture(args.demo, args.frames)
    if args.raw:
        print(f"raw frames {args.raw}..{args.raw + 40}:")
        for r in rows:
            if args.raw <= r["f"] < args.raw + 40:
                print(f"  f={r['f']:5d}  scene={r['scene_BE06']:#04x}  count={r['count_BE08']:3d}  @ {r['cs_ip']}")
        return 0
    # compress into runs of (scene, start-flag) so the timeline is readable
    print(f"captured {len(rows)} present-frames")
    prev = None
    for r in rows:
        key = (r["scene_BE06"], r["start_98C3"])
        if key != prev:
            print(f"  f={r['f']:5d}  scene[BE06]={r['scene_BE06']:#04x}  count[BE08]={r['count_BE08']:3d}  "
                  f"start[98C3]={r['start_98C3']:#04x}  @ {r['cs_ip']}")
            prev = key
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
