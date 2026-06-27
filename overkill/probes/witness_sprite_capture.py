"""Probe: capture each object's sprite + the background behind it, at the draw.

Since OVERKILL has no clean object-free plate (see witness_object_layers), object
interpolation must capture each object AT its draw. This probe wraps the per-object
draw dispatch 5AC8 and, for one frame, decodes the composited source page `[9598]`
immediately BEFORE and AFTER each object's draw. The changed pixels are that
object's footprint: AFTER = the sprite (over its background), BEFORE = the clean
background behind it (what we erase to when we move the object). Keyed by the
object record (slot identity + sprite id + screen_di), this is exactly the data a
native interpolator needs to redraw objects at interpolated positions.

Dumps a montage of the captured sprites + their backgrounds to verify the lift.

Usage:
    python -m overkill.probes.witness_sprite_capture <demo_dir> [frame] [outdir]
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
OFF_SPRITE, OFF_DEST, OFF_LAYER, OFF_TYPE = 0x08, 0x0C, 0x16, 0x14


def _decode(cpu, seg):
    from overkill.native_video.page_raster import render_present_page_indices
    mem = np.frombuffer(cpu.mem.data, dtype=np.uint8)
    cur = cpu.mem.rw(cpu.s.ds & 0xFFFF, P_CURSOR)
    return render_present_page_indices(mem, seg, cur)


def _raw(cpu, seg):
    base = (seg << 4) & 0xFFFFF
    return np.frombuffer(cpu.mem.data, dtype=np.uint8)[base:base + 0x10000].copy()


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    target_frame = int(argv[1]) if len(argv) > 1 else 3
    outdir = argv[2] if len(argv) > 2 else str(ROOT / "artifacts" / "sprite_capture")

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    state = {"frame": 0}
    captures: list[dict] = []                      # filled only on target_frame
    per_frame = {}                                 # state.frame -> 5AC8 call count

    draw = registry.replacements[(CS, 0x5AC8)]
    orig_draw = draw.handler

    def hook_draw(cpu):
        per_frame[state["frame"]] = per_frame.get(state["frame"], 0) + 1
        if state["frame"] == target_frame:
            ss, bp = cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF
            segs = {p: cpu.mem.rw(CS, p) for p in (0x9592, 0x9596, 0x9598, 0x95A4)}
            segs["ES"] = cpu.s.es & 0xFFFF
            raw_before = {name: _raw(cpu, seg) for name, seg in segs.items()}
            orig_draw(cpu)
            changed = {}
            for name, seg in segs.items():
                d = int((raw_before[name] != _raw(cpu, seg)).sum())
                if d:
                    changed[name] = (seg, d)
            captures.append({
                "sprite": cpu.mem.rw(ss, (bp + OFF_SPRITE) & 0xFFFF),
                "dest": cpu.mem.rw(ss, (bp + OFF_DEST) & 0xFFFF),
                "segs": segs, "changed": changed,
            })
        else:
            orig_draw(cpu)

    object.__setattr__(draw, "handler", hook_draw)

    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample):
        state["frame"] += 1

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=target_frame + 3,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        object.__setattr__(draw, "handler", orig_draw)

    print(f"demo {demo_dir.name}  5AC8 draws per frame: "
          + " ".join(f"f{k}={v}" for k, v in sorted(per_frame.items())))
    print(f"frame={target_frame}  objects captured={len(captures)}")
    if captures:
        s = captures[0]["segs"]
        print("  segs: " + " ".join(f"{k}={v:04X}" for k, v in s.items()))
    for i, c in enumerate(captures):
        if not c["changed"]:
            print(f"  draw {i:2d}: sprite={c['sprite']:04X} dest={c['dest']:04X}  -> NOTHING WRITTEN")
            continue
        ch = " ".join(f"{name}({seg:04X}):{d}B" for name, (seg, d) in c["changed"].items())
        print(f"  draw {i:2d}: sprite={c['sprite']:04X} dest={c['dest']:04X}  -> wrote {ch}")
    return 0


def _dump_montage(rows, outdir):
    from PIL import Image
    from overkill.native_video.page_raster import colorize
    Path(outdir).mkdir(parents=True, exist_ok=True)
    cell, pad = 48, 4
    cols = min(8, len(rows))
    n = len(rows)
    rows_n = (n + cols - 1) // cols
    # two strips: AFTER (sprite over bg) on top, BEFORE (bg behind) below
    sheet = np.zeros((rows_n * (cell * 2 + pad * 3), cols * (cell + pad), 3), dtype=np.uint8)
    for k, (c, (y0, y1, x0, x1)) in enumerate(rows):
        r, col = divmod(k, cols)
        spr = colorize(c["after"][y0:y1, x0:x1])
        bg = colorize(c["before"][y0:y1, x0:x1])
        oy = r * (cell * 2 + pad * 3) + pad
        ox = col * (cell + pad)
        for img, yo in ((spr, oy), (bg, oy + cell + pad)):
            h, w = min(cell, img.shape[0]), min(cell, img.shape[1])
            sheet[yo:yo + h, ox:ox + w] = img[:h, :w]
    Image.fromarray(sheet).save(f"{outdir}/sprites_top=after_bottom=bg.png")
    print(f"  wrote montage to {outdir}/sprites_top=after_bottom=bg.png")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
