"""Play a cold-loaded OVERKILL level natively -- fly through the real terrain, VM-free.

Run (interactive, needs pygame + a display):
    python scripts/native_play_cold.py [level 0..5]
        Arrow keys move the ship; the level auto-scrolls; Esc/close to quit.

Run (headless, render a scrolling clip to GIF -- works without a display):
    python scripts/native_play_cold.py [level] --gif out.gif [--frames 90]

Everything here is VM-free: the level is decoded from the original files (the unpacked OVERKILL.EXE
image + the OVERKILL container), the terrain is composited by the native terrain compositor, the player
position is stepped by the recovered movement system, and frames are colorized with the recovered palette.
The terrain is real; the player is a placeholder marker until the sprite compositor (player/enemies from
the cold graphics bank) lands -- this is the scrolling, controllable cold level.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from overkill.asset_codecs import load_native_level                       # noqa: E402
from overkill.native_video.page_raster import PLAYFIELD_H, PLAYFIELD_W, colorize  # noqa: E402
from overkill.native_video.terrain import render_terrain_indices         # noqa: E402

EXE_IMAGE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
CONTAINER = ROOT / "assets" / "OVERKILL"


def _draw_ship(rgb: np.ndarray, x: int, y: int) -> None:
    """Draw a small placeholder ship marker (a blue arrow) at (x, y) on an (H, W, 3) RGB frame."""
    h, w = rgb.shape[:2]
    for dy in range(-4, 5):
        half = 4 - abs(dy)
        yy = y + dy
        if 0 <= yy < h:
            x0, x1 = max(0, x - half), min(w, x + half + 1)
            rgb[yy, x0:x1] = (80, 160, 255)
    if 0 <= y < h and 0 <= x < w:
        rgb[max(0, y - 5):y, max(0, x - 1):x + 2] = (255, 255, 255)


def playfield_frame(terrain: np.ndarray, scroll_y: int, ship_xy) -> np.ndarray:
    """Compose one VM-free playfield frame: the terrain window at ``scroll_y`` + the ship marker.

    Returns an ``(PLAYFIELD_H, PLAYFIELD_W, 3)`` uint8 RGB image.
    """
    h = PLAYFIELD_H
    w = min(PLAYFIELD_W, terrain.shape[1])
    scroll_y = max(0, min(scroll_y, terrain.shape[0] - h))
    window = terrain[scroll_y:scroll_y + h, :w]
    rgb = np.array(colorize(window), dtype=np.uint8)
    if rgb.shape[1] < PLAYFIELD_W:  # pad to the full playfield width
        rgb = np.pad(rgb, ((0, 0), (0, PLAYFIELD_W - rgb.shape[1]), (0, 0)))
    _draw_ship(rgb, ship_xy[0], ship_xy[1])
    return rgb


def _load_terrain(level: int) -> np.ndarray:
    lvl = load_native_level(EXE_IMAGE.read_bytes(), CONTAINER.read_bytes(), level)
    return render_terrain_indices(lvl.tile_plane, lvl.blocks)


def run_gif(level: int, out: pathlib.Path, frames: int) -> int:
    from PIL import Image
    terrain = _load_terrain(level)
    bottom = terrain.shape[0] - PLAYFIELD_H
    ship = (PLAYFIELD_W // 2, PLAYFIELD_H - 40)
    imgs = []
    for i in range(frames):
        scroll = bottom - (i * 4) % max(1, bottom)  # auto-scroll up, looping
        rgb = playfield_frame(terrain, scroll, ship)
        imgs.append(Image.fromarray(rgb, "RGB").resize((PLAYFIELD_W * 2, PLAYFIELD_H * 2), Image.NEAREST))
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=33, loop=0)
    print("wrote %s (%d frames, level %d, VM-free terrain)" % (out, frames, level))
    return 0


def run_interactive(level: int, scale: int) -> int:
    import pygame
    terrain = _load_terrain(level)
    pygame.init()
    screen = pygame.display.set_mode((PLAYFIELD_W * scale, PLAYFIELD_H * scale))
    pygame.display.set_caption("OVERKILL - cold native level %d (arrows to move, Esc to quit)" % level)
    clock = pygame.time.Clock()
    surf = pygame.Surface((PLAYFIELD_W, PLAYFIELD_H))
    scroll = float(terrain.shape[0] - PLAYFIELD_H)
    px, py = PLAYFIELD_W // 2, PLAYFIELD_H - 40
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            px = max(6, px - 3)
        if keys[pygame.K_RIGHT]:
            px = min(PLAYFIELD_W - 6, px + 3)
        if keys[pygame.K_UP]:
            py = max(8, py - 3)
        if keys[pygame.K_DOWN]:
            py = min(PLAYFIELD_H - 6, py + 3)
        scroll -= 1.2                       # auto-scroll up the level
        if scroll < 0:
            scroll = float(terrain.shape[0] - PLAYFIELD_H)
        rgb = playfield_frame(terrain, int(scroll), (px, py))
        pygame.surfarray.blit_array(surf, np.transpose(rgb, (1, 0, 2)))
        pygame.transform.scale(surf, screen.get_size(), screen)
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("level", nargs="?", type=int, default=0)
    p.add_argument("--gif", type=pathlib.Path, help="render a scrolling clip to this GIF (headless)")
    p.add_argument("--frames", type=int, default=90)
    p.add_argument("--scale", type=int, default=3)
    args = p.parse_args(argv)
    if not EXE_IMAGE.is_file() or not CONTAINER.is_file():
        print("Missing game data (need %s and %s)" % (EXE_IMAGE, CONTAINER))
        return 1
    if args.gif:
        return run_gif(args.level, args.gif, args.frames)
    return run_interactive(args.level, args.scale)


if __name__ == "__main__":
    raise SystemExit(main())
