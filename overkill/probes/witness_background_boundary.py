"""Probe: locate the clean-background boundary in the source page [9598].

FINDING (2026-06-27): there is NO clean background plate. Dumping the present-
decoded [9598] at three points of one frame shows the page is composed in
painter's-REVERSE: it is cleared, then the SPRITES are drawn (before the first
sprite pixel the page is empty, ~40 px), then the background (tiles + starfield)
is drawn around them, then 5BDC presents the fully composed page. So the bg is
drawn AFTER the sprites and there is no captured background behind a sprite -- the
background cannot be plated or sprite-erased, it must be recovered as regenerable
semantic state (the tile-draw + starfield generators), per the recovery-first rule.

Usage:
    python -m overkill.probes.witness_background_boundary <demo_dir> [frame] [outdir]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"
CS = 0x1010
P_SOURCE = 0x9598
P_CURSOR = 0x234C


def _render(cpu, cursor):
    from overkill.native_video.page_raster import render_present_page_indices
    mem = np.frombuffer(cpu.mem.data, dtype=np.uint8)
    src = cpu.mem.rw(CS, P_SOURCE)
    return render_present_page_indices(mem, src, cursor), cursor


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    target = int(argv[1]) if len(argv) > 1 else 4
    outdir = argv[2] if len(argv) > 2 else str(ROOT / "artifacts" / "bg_boundary")

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    st = {"frame": 0, "shots": {}, "cursor": 0}
    wrapped = []

    def grab(label, once_per_frame=False):
        def make(orig):
            def hook(cpu):
                if st["frame"] == target and not (once_per_frame and label in st["shots"]):
                    img, cur = _render(cpu, st["cursor"])
                    st["shots"].setdefault(label, (img, cur, int((img != 0).sum())))
                orig(cpu)
            return hook
        return make

    # A846 runs at the frame top with the game data segment -> capture the cursor there.
    a846 = registry.replacements[(CS, 0xA846)]
    a846_orig = a846.handler

    def a846_hook(cpu):
        st["cursor"] = cpu.mem.rw(cpu.s.ds & 0xFFFF, P_CURSOR)
        a846_orig(cpu)
    object.__setattr__(a846, "handler", a846_hook)
    wrapped.append((a846, a846_orig))

    for ip, label, once in [(0x5BDC, "1_5BDC_entry", True)] + \
            [(c, "2_before_first_sprite_pixel", True) for c in (0x2E6E, 0x2F81, 0x2FB6)] + \
            [(0x3354, "3_present_3354", True)]:
        rep = registry.replacements[(CS, ip)]
        orig = rep.handler
        object.__setattr__(rep, "handler", grab(label, once)(orig))
        wrapped.append((rep, orig))

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
        for rep, orig in wrapped:
            object.__setattr__(rep, "handler", orig)

    from PIL import Image
    from overkill.native_video.page_raster import colorize
    Path(outdir).mkdir(parents=True, exist_ok=True)
    print(f"demo {demo_dir.name}  frame {target}")
    for label in sorted(st["shots"]):
        img, cur, nz = st["shots"][label]
        Image.fromarray(colorize(img)).save(f"{outdir}/{label}.png")
        print(f"  {label}: cursor={cur:04X} non-zero_px={nz}")
    print(f"  wrote PNGs to {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
