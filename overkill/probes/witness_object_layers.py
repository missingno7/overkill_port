"""Probe: separate the moving OBJECTS from the rest of the per-frame draw.

For native object interpolation we need, per source frame: a clean background to
draw objects over, and each object's pixels + screen box. This probe samples the
composited source page `[9598]` at two instants over a real demo:

  * at `A846` (the draw-scan setup, BEFORE the object scan) -> the *clean* page;
  * at `3354` (the present blit)                            -> the *composed* page.

It decodes both via the present geometry (same window) and reports where they
differ, split into pixels INSIDE the witnessed object boxes (screen_di) vs
OUTSIDE them. A large OUTSIDE share means a separate layer (e.g. the starfield)
is drawn after A846 and must be modelled, not just the table objects.

Usage:
    python -m overkill.probes.witness_object_layers <demo_dir> [frames] [box]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"

CS = 0x1010
P_SOURCE = 0x9598   # CS:[9598] -> composited source page segment
P_CURSOR = 0x234C   # DS:[234C] -> present blit start (scroll)


def _np_mem(cpu):
    return np.frombuffer(cpu.mem.data, dtype=np.uint8)


def _decode_page(cpu):
    from overkill.native_video.page_raster import render_present_page_indices
    src = cpu.mem.rw(CS, P_SOURCE)
    cur = cpu.mem.rw(cpu.s.ds & 0xFFFF, P_CURSOR)
    return render_present_page_indices(_np_mem(cpu), src, cur)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    frames_wanted = int(argv[1]) if len(argv) > 1 else 20
    box = int(argv[2]) if len(argv) > 2 else 20
    dump_frame = int(argv[3]) if len(argv) > 3 else 1
    outdir = argv[4] if len(argv) > 4 else str(ROOT / "artifacts" / "object_layers")

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401 - registers the hooks
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.recovered.adapters.frame_snapshot_adapter import extract_frame_snapshot
    from overkill.recovered.systems.tandy_screen import di_to_screen, on_screen

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    # per-frame scratch the hooks fill
    cur = {"clean": None, "composed": None, "snap": None, "seen_a846": False}

    a846 = registry.replacements[(CS, 0xA846)]
    present = registry.replacements[(CS, 0x3354)]
    orig_a846, orig_present = a846.handler, present.handler

    def hook_a846(cpu):
        if not cur["seen_a846"]:                      # first scan-setup of the frame = clean
            cur["clean"] = _decode_page(cpu)
            cur["snap"] = extract_frame_snapshot(cpu.mem, cpu.s.ds & 0xFFFF)
            cur["cur_a"] = cpu.mem.rw(cpu.s.ds & 0xFFFF, P_CURSOR)
            cur["seen_a846"] = True
        orig_a846(cpu)

    def hook_present(cpu):
        cur["composed"] = _decode_page(cpu)
        cur["cur_p"] = cpu.mem.rw(cpu.s.ds & 0xFFFF, P_CURSOR)
        orig_present(cpu)

    object.__setattr__(a846, "handler", hook_a846)
    object.__setattr__(present, "handler", hook_present)

    records = []
    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample):
        if len(records) < frames_wanted and cur["clean"] is not None and cur["composed"] is not None:
            records.append((cur["clean"], cur["composed"], cur["snap"],
                            cur.get("cur_a"), cur.get("cur_p")))
        cur["clean"] = cur["composed"] = cur["snap"] = None
        cur["seen_a846"] = False

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=frames_wanted + 2,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        object.__setattr__(a846, "handler", orig_a846)
        object.__setattr__(present, "handler", orig_present)

    print(f"demo {demo_dir.name}  frames={len(records)}  box={box}px (top-left anchored)")
    H, W = 200, 320
    for i, (clean, composed, snap, cur_a, cur_p) in enumerate(records):
        diff = clean != composed
        ndiff = int(diff.sum())
        # mark the witnessed object boxes (sprite anchors top-left, extends down-right)
        objmask = np.zeros((H, W), dtype=bool)
        boxes = []
        for sd in snap.playfield.sprites:
            if not on_screen(sd.screen_di):
                continue
            ox, oy = di_to_screen(sd.screen_di)
            x0, x1 = max(0, ox - 4), min(W, ox + box)
            y0, y1 = max(0, oy - 4), min(H, oy + box)
            objmask[y0:y1, x0:x1] = True
            boxes.append((sd.sprite, ox, oy))
        inbox = int((diff & objmask).sum())
        outbox = ndiff - inbox
        scroll = "SAME" if cur_a == cur_p else f"A={cur_a:04X} P={cur_p:04X} d={(cur_a - cur_p) & 0xFFFF:+d}"
        print(f"frame {i:2d}: diff={ndiff:5d}px  in-boxes={inbox:5d}  outside={outbox:5d}  "
              f"objs={len(boxes):2d}  cursor:{scroll}")
        if i < 3:
            print("   objs:", " ".join(f"{s:04X}@({x},{y})" for s, x, y in boxes[:12]))
        if i == dump_frame:
            _dump_pngs(clean, composed, diff, objmask, outdir)
    return 0


def _dump_pngs(clean, composed, diff, objmask, outdir):
    from PIL import Image
    from overkill.native_video.page_raster import colorize
    Path(outdir).mkdir(parents=True, exist_ok=True)
    Image.fromarray(colorize(clean)).save(f"{outdir}/clean_a846.png")
    Image.fromarray(colorize(composed)).save(f"{outdir}/composed_3354.png")
    # diff highlight: green = diff outside object boxes (stars?), red = diff in boxes (objects)
    H, W = diff.shape
    hi = np.zeros((H, W, 3), dtype=np.uint8)
    hi[diff & ~objmask] = (0, 255, 0)
    hi[diff & objmask] = (255, 0, 0)
    Image.fromarray(hi).save(f"{outdir}/diff_red=obj_green=else.png")
    print(f"   wrote PNGs to {outdir}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
