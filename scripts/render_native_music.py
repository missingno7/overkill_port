"""Render the VM-FREE AdLib driver's music to a WAV -- the native counterpart of render_demo_music.py.

render_demo_music.py captures the *VM's* OPL register stream (the audio ORACLE).  This tool instead
runs the recovered VM-free driver (`overkill.native_audio.adlib.AdlibDriver`) over an AdLib snapshot's
segment-2032 state and synthesizes ITS register stream through the same Nuked-OPL3 path -- so the
recovered driver can be listened to end-to-end (perceptual validation ahead of the byte-exact oracle
gate).  The driver's own bytecode loop keeps the loaded music page playing (and looping), so no game
input is needed for a continuous render.

Usage:
    python scripts/render_native_music.py [--snapshot DIR] [--seconds S] [--ticks-per-frame N]
                                          [--out PATH] [--rate HZ] [--fps HZ]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.native_audio.adlib import AdlibDriver  # noqa: E402
from scripts.render_demo_music import render_wav      # noqa: E402

DEFAULT_SNAPSHOT = ROOT / "artifacts" / "demos" / "demo_play_tandy_20260711_120636" / "snapshot"
SEG_2032 = 0x2032 * 16


def render(snapshot: Path, frames: int, ticks_per_frame: int) -> "list[list[tuple[int, int]]]":
    """Run the VM-free driver `frames` present-frames (each `ticks_per_frame` driver ticks); return the
    per-frame (reg, val) OPL writes."""
    seg = bytearray((snapshot / "memory_1mb.bin").read_bytes()[SEG_2032:SEG_2032 + 0x10000])
    driver = AdlibDriver(seg)
    per_frame: "list[list[tuple[int, int]]]" = []
    for _ in range(frames):
        for _ in range(ticks_per_frame):
            driver.tick_2032_0063()
        per_frame.append(driver.drain())
    return per_frame


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT, help="an AdLib-booted snapshot dir")
    ap.add_argument("--seconds", type=float, default=10.0, help="seconds of music to render")
    ap.add_argument("--ticks-per-frame", type=int, default=1,
                    help="driver ISR ticks per present-frame (the music tempo). The audio oracle gate "
                         "(overkill.probes.verify_native_audio) fixed this at 1/present-frame == 2 per "
                         "30fps gameplay-frame, byte-exact vs the VM; the default 60fps here wants 1.")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--rate", type=int, default=44100)
    ap.add_argument("--fps", type=int, default=60)
    args = ap.parse_args(argv)

    frames = int(args.seconds * args.fps)
    writes = render(args.snapshot, frames, args.ticks_per_frame)
    total = sum(len(w) for w in writes)
    out = args.out or (ROOT / "artifacts" / "music_native_vmfree.wav")
    secs = render_wav(writes, out, args.rate, args.fps)
    print(f"VM-free driver: {total} OPL writes over {frames} frames "
          f"({args.ticks_per_frame} tick/frame)")
    print(f"wrote {out} ({secs:.1f}s @ {args.rate} Hz)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
