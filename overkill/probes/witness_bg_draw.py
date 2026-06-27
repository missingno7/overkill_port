"""Probe: identify the routines that paint the background into [9598].

The background (tiles + starfield) is drawn after the sprites (painter's-reverse;
see witness_background_boundary). This wraps the candidate Tandy fill/copy/clear
leaves + the present, and for one frame reports each call's change to the page
non-zero pixel count (decoded with the game cursor). The big positive deltas are
the background draws to recover; dumps the page after the largest-delta call.

Usage:
    python -m overkill.probes.witness_bg_draw <demo_dir> [frame] [outdir]
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

# Bracket the top-level D007 per-frame calls to find which contains the bg draw.
CANDIDATES = {
    0xA846: "A846_scan_setup", 0x5BDC: "5BDC_present", 0xA90C: "A90C_obj_scan",
    0xD04D: "D04D_ui_state", 0xA940: "A940_game_state", 0x5F61: "5F61_status",
    0x981F: "981F", 0x60A2: "60A2_fx_text",
}


def _nonzero(cpu, cursor):
    from overkill.native_video.page_raster import render_present_page_indices
    mem = np.frombuffer(cpu.mem.data, dtype=np.uint8)
    img = render_present_page_indices(mem, cpu.mem.rw(CS, P_SOURCE), cursor)
    return img, int((img != 0).sum())


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    target = int(argv[1]) if len(argv) > 1 else 6
    outdir = argv[2] if len(argv) > 2 else str(ROOT / "artifacts" / "bg_draw")

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    st = {"frame": 0, "cursor": 0, "trace": [], "best": (0, None)}
    wrapped = []

    a846 = registry.replacements[(CS, 0xA846)]
    a846_orig = a846.handler

    def a846_hook(cpu):
        st["cursor"] = cpu.mem.rw(cpu.s.ds & 0xFFFF, P_CURSOR)
        a846_orig(cpu)
    object.__setattr__(a846, "handler", a846_hook)
    wrapped.append((a846, a846_orig))

    def make(ip, label):
        try:
            rep = registry.replacements[(CS, ip)]
        except KeyError:
            return
        orig = rep.handler

        def hook(cpu, _orig=orig, _label=label):
            if st["frame"] == target and _label not in {t[0] for t in st["trace"]}:
                _, before = _nonzero(cpu, st["cursor"])
                _orig(cpu)
                img, after = _nonzero(cpu, st["cursor"])
                st["trace"].append((_label, before, after, after - before))
                if (after - before) > st["best"][0]:
                    st["best"] = (after - before, img.copy())
            else:
                _orig(cpu)
        object.__setattr__(rep, "handler", hook)
        wrapped.append((rep, orig))

    for ip, label in CANDIDATES.items():
        make(ip, label)

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

    print(f"demo {demo_dir.name}  frame {target}  (page non-zero deltas, in order):")
    for label, b, a, d in st["trace"]:
        print(f"  {label:20s} {b:5d} -> {a:5d}   delta {d:+5d}")
    if st["best"][1] is not None:
        from PIL import Image
        from overkill.native_video.page_raster import colorize
        Path(outdir).mkdir(parents=True, exist_ok=True)
        Image.fromarray(colorize(st["best"][1])).save(f"{outdir}/after_largest_delta.png")
        print(f"  wrote page-after-largest-delta to {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
