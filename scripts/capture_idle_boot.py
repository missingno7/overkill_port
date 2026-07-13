"""Headless capture of play_native's cold boot with ZERO input -- exactly "launch the game and wait",
the same way the real DOS game's whole intro/menu/attract sequence is naturally reachable.  Runs under
SDL_VIDEODRIVER=dummy (no real window/input backend, so pygame.event.get() naturally returns nothing --
literally simulating doing nothing) and saves a screenshot every N presented frames so the sequence can
be inspected without a live display.

Usage:
    python scripts/capture_idle_boot.py [--seconds N] [--every N] [--out DIR]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.play_native as pn  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, default=25.0, help="wall-clock seconds of idle play to capture")
    ap.add_argument("--every", type=int, default=15, help="save a screenshot every N presented frames")
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "idle_boot_capture"))
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle_data = Path(pn.DEFAULT_BUNDLE).read_bytes()
    container_data = Path(pn.DEFAULT_CONTAINER).read_bytes()

    display = pn.PygameDisplay(scale=1)
    pygame = display.pygame
    scan_map = pn._build_scan_map(pygame)

    state = {"n": 0, "saved": 0}
    orig_draw = display.draw

    max_frames = int(args.seconds * 30)

    def capturing_draw(indices):
        orig_draw(indices)
        state["n"] += 1
        if state["n"] % args.every == 0:
            path = out_dir / f"f{state['n']:05d}.png"
            pygame.image.save(display.screen, str(path))
            state["saved"] += 1
            print(f"  saved {path.name}  (title={pygame.display.get_caption()[0]})")
        if state["n"] >= max_frames:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    display.draw = capturing_draw

    print(f"capturing ~{args.seconds}s of idle boot (no input) to {out_dir}")
    try:
        if not pn._run_blueprint_intro(display, pygame, bundle_data, container_data):
            print("blueprint intro exited (QUIT) early")
            return 0
        result = pn._run_title_menu(display, pygame, bundle_data, container_data, scan_map, music=None)
        print(f"title menu returned: {result}")
    finally:
        display.close()

    print(f"done: {state['saved']} screenshots saved, {state['n']} frames presented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
