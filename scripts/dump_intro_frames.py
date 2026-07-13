"""Dump multiple demo-paced cold-boot-intro present-frames to PNG for visual inspection.

Snapshots the ref VM's B800 aperture at several present-frame boundaries during a real cold-start
demo replay (real command tail, real timing) and renders each to a PNG via scripts/render_frame.py's
Tandy decoder -- so the blueprint char-writer reveal can be SEEN, not inferred from register dumps.

Usage:
    pypy scripts/dump_intro_frames.py [demo_name] --frames 446,460,477,480,500,520,550 --out DIR
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
from scripts.render_frame import render_tandy_ppm, write_png  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"


def dump(demo_name: str, frames: "list[int]", out_dir: Path, seg: int = 0xB800) -> None:
    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    tail = str(meta.get("command_tail", ""))
    targets = set(frames)
    max_frame = max(frames)

    state = {"f": 0, "ref": None}
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            state["ref"] = rt
        return rt

    fv._load_runtime = patched
    out_dir.mkdir(parents=True, exist_ok=True)

    def pump(ref, cand):
        f = state["f"]
        rt = state["ref"]
        if rt is not None and f in targets:
            mem = bytes(rt.cpu.mem.data)
            width, height, ppm = render_tandy_ppm(mem, seg, scale=2)
            header_end = ppm.find(b"\n255\n") + len(b"\n255\n")
            raw = ppm[header_end:]
            row_bytes = width * 3
            rows = [bytearray(raw[y * row_bytes:(y + 1) * row_bytes]) for y in range(height)]
            path = out_dir / f"f{f:04d}_seg{seg:04X}.png"
            write_png(path, width, height, rows)
            print(f"wrote {path}")
        pump_demo_frame(demo, f, (ref, cand), ref.cpu)
        state["f"] = f + 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=max_frame + 2,
                            semantic_state_check=False, stop_on_diff=False, log_every=0,
                            frame_budget=120_000_000)
    try:
        run_frame_verifier(exe=str(ROOT / "assets" / "OVERKILL"), assets=str(ROOT / "assets"),
                           snapshot=None, command_tail=tail, config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig_load


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", nargs="?", default=DEFAULT_DEMO)
    ap.add_argument("--frames", default="446,460,477,480,500,520,550")
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "intro_frame_dump"))
    ap.add_argument("--seg", default="B800", help="video segment in hex to decode (default B800)")
    args = ap.parse_args(argv)
    frames = [int(x) for x in args.frames.split(",")]
    dump(args.demo, frames, Path(args.out), seg=int(args.seg, 16))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
