"""Capture the cold-boot BLUEPRINT INTRO frame-by-frame from the reference VM -- the ORACLE for
proving play_native's intro animation faithful.

The intro is the animated blueprint-drafting screen: the grid + title bar appear, then the spec text,
then the ship schematics -- a progressive reveal that ends at the full `native_video.blueprint`
compose.  This port runs `video=tandy`, so the intro renders in **TANDY 16-colour**; test against
Tandy, not CGA.

CAVEAT (see run_status 2026-07-13): the `dos.video_mode` reads 4 during the intro, but a raw-B800
Tandy decode of those frames GARBLES (the intro's live B800 is not in the mode-9 bank layout), and the
CGA-4 branch below is a DEAD END for this port (it renders the wrong-colour, wrong-content screen).
The correct oracle is the byte-exact-vs-VM COMPOSE-PAGE (16-colour) comparison used to verify the grid
(`tests/test_blueprint_grid` / the campaign doc), NOT this raw-B800 capture.  This tool is kept for the
per-frame nz TIMELINE (which shows the reveal building up) but its pixels are only reliable for
mode-9 (Tandy) screens.

Usage:
    python scripts/capture_intro_frames.py [LO] [HI] [--demo NAME] [--out DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402

import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.native_video.page_raster import decode_tandy_b800_indices  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402


def decode_cga4_indices(buf: "np.ndarray", base: int = 0xB8000) -> "np.ndarray":
    """Decode a CGA mode-4 (320x200x2bpp) B800 aperture to ``(200,320)`` colour indices 0..3.
    Two interlaced 8 KiB banks: ``off = (y&1)*0x2000 + (y>>1)*80``; 4 pixels/byte, high bits left."""
    y = np.arange(200)
    off = base + (y & 1) * 0x2000 + (y >> 1) * 80
    cols = buf[off[:, None] + np.arange(80)[None, :]]           # (200,80)
    idx = np.empty((200, 320), np.uint8)
    for p in range(4):
        idx[:, p::4] = (cols >> (6 - 2 * p)) & 3
    return idx


def decode_frame_indices(buf: "np.ndarray", video_mode: int) -> "np.ndarray":
    """Decode the current B800 framebuffer to ``(200,320)`` indices using the decoder that matches the
    ACTIVE video mode -- CGA (mode 4) vs Tandy (mode 9).  This is the key to a correct front-end
    capture: the front end switches modes mid-sequence, so a fixed decoder mis-reads half the frames."""
    if (video_mode & 0x7F) == 4:
        return decode_cga4_indices(buf)
    return decode_tandy_b800_indices(buf, 0xB8000)


def capture(demo_name: str, lo: int, hi: int):
    """Replay the cold-start demo; per present-frame in ``[lo,hi]`` yield ``(f, video_mode, indices)``
    decoded with the mode-correct decoder.  Returns the list of frame records."""
    demo = load_demo(demo_name, demo_name)
    cur = {"f": 0, "rt": None}
    frames: "list[tuple[int, int, np.ndarray]]" = []
    orig = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(e, a, s, t):
        rt = orig(e, a, s, t)
        if next(sides) == "ref":
            cur["rt"] = rt
        return rt

    fv._load_runtime = patched

    def pump(ref, cand):
        rt = cur["rt"]
        f = cur["f"]
        if rt is not None and lo <= f <= hi:
            buf = np.frombuffer(bytes(rt.cpu.mem.data), np.uint8)
            frames.append((f, rt.dos.video_mode, decode_frame_indices(buf, rt.dos.video_mode)))
        pump_demo_frame(demo, f, (ref, cand), ref.cpu)
        cur["f"] = f + 1

    cfg = FrameVerifyConfig(video="tandy", source="candidate", max_frames=hi + 1,
                            semantic_state_check=False, stop_on_diff=False, log_every=0,
                            frame_budget=200_000_000)
    try:
        run_frame_verifier(exe=str(ROOT / "assets" / "OVERKILL"), assets=str(ROOT / "assets"),
                           snapshot=None, command_tail=b"", config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig
    return frames


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("lo", type=int, nargs="?", default=440)
    ap.add_argument("hi", type=int, nargs="?", default=760)
    ap.add_argument("--demo", default="demo_cold_start_intro_20260711_203259")
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "_intro"))
    args = ap.parse_args(argv)

    from render_frame import CGA_PALETTES, EGA_PALETTE
    from PIL import Image
    cga = np.array(CGA_PALETTES["1h"], np.uint8)
    ega = np.array(EGA_PALETTE, np.uint8)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    frames = capture(args.demo, args.lo, args.hi)
    prev_mode, prev_nz = -1, -1
    for f, mode, idx in frames:
        nz = int(np.count_nonzero(idx))
        if mode != prev_mode or abs(nz - prev_nz) > 250:
            pal = cga if (mode & 0x7F) == 4 else ega
            Image.fromarray(pal[idx]).resize((640, 400), Image.NEAREST).save(out / f"f{f:04d}_m{mode}.png")
            print(f"f={f:4d} mode={mode} nz={nz} (saved)")
            prev_mode, prev_nz = mode, nz
    print(f"captured {len(frames)} frames [{args.lo},{args.hi}] from {args.demo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
