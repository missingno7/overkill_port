"""Probe: is the [9592] master plane the clean background layer?

The BackgroundLayer model says OVERKILL pre-renders the level into the [9592]
master plane (tiles materialised as it scrolls). If that plane, windowed by the
scroll, is the background WITHOUT sprites, it is the page-baked bg layer the
native renderer can consume (cached) and compose sprites over -- solving the
"no clean plate" problem the painter's-reverse compose created in [9598].

Dumps [9592] windowed by both candidate scroll cells ([234C], [2350]) and the
composed [9598] for reference, at one frame's 5BDC (present) entry.

Usage:
    python -m overkill.probes.witness_master_plane <demo_dir> [frame] [outdir]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"
CS = 0x1010
P_MASTER = 0x9592   # background master plane segment
P_SOURCE = 0x9598   # composited source page segment
CUR_234C = 0x234C   # source-page present cursor
CUR_2350 = 0x2350   # background scroll row


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    target = int(argv[1]) if len(argv) > 1 else 6
    outdir = argv[2] if len(argv) > 2 else str(ROOT / "artifacts" / "master_plane")

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.native_video.page_raster import render_present_page_indices

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    st = {"frame": 0, "shots": None}
    rep = registry.replacements[(CS, 0x5BDC)]
    orig = rep.handler

    def hook(cpu):
        if st["frame"] == target and st["shots"] is None:
            mem = np.frombuffer(cpu.mem.data, dtype=np.uint8)
            ds = cpu.s.ds & 0xFFFF
            master, source = cpu.mem.rw(CS, P_MASTER), cpu.mem.rw(CS, P_SOURCE)
            c234c, c2350 = cpu.mem.rw(ds, CUR_234C), cpu.mem.rw(ds, CUR_2350)
            def raw_linear(seg, stride, rows, off=0):
                base = ((seg & 0xFFFF) << 4) + off
                buf = mem[base:base + stride * rows]
                b = buf.reshape(rows, stride)
                img = np.zeros((rows, stride * 2), dtype=np.uint8)
                img[:, 0::2] = b >> 4
                img[:, 1::2] = b & 0x0F
                return img
            st["shots"] = {
                "master_at_234C": (render_present_page_indices(mem, master, c234c), c234c),
                "master_raw_A0x400": (raw_linear(master, 0xA0, 400), 0),
                "master_raw_68x400": (raw_linear(master, 0x68, 400), 0),
                "source_composed": (render_present_page_indices(mem, source, c234c), c234c),
            }
            print(f"  segments: [9592]={master:04X} [9598]={source:04X}  "
                  f"[234C]={c234c:04X} [2350]={c2350:04X}")
        orig(cpu)
    object.__setattr__(rep, "handler", hook)

    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample):
        st["frame"] += 1

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=target + 2,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        object.__setattr__(rep, "handler", orig)

    from PIL import Image
    from overkill.native_video.page_raster import colorize
    Path(outdir).mkdir(parents=True, exist_ok=True)
    print(f"demo {demo_dir.name}  frame {target}")
    for name, (img, cur) in (st["shots"] or {}).items():
        Image.fromarray(colorize(img)).save(f"{outdir}/{name}.png")
        print(f"  {name}: cursor={cur:04X}  non-zero={int((img != 0).sum())}")
    print(f"  wrote PNGs to {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
