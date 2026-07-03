#!/usr/bin/env python
"""OVERKILL -- the VM-less native standalone entrypoint.

Cold-loads a level from the game's own data files (``assets/OVERKILL`` + the materialized static
runtime bundle) and runs the recovered gameplay frame systems with **NO VM, no ``dos_re`` import
anywhere on this default run path** -- a genuinely standalone game, separable from the whole RE
workbench.

    python scripts/play_native.py --level 0                    # play LEVEL1 (0-based), VM-free
    python scripts/play_native.py --level 0 --snapshot DIR     # DEBUG: seed a REAL, verified
                                                                 # starting NativeGameState from a
                                                                 # captured VM memory dump instead
                                                                 # of the placeholder spawn (this
                                                                 # is the ONLY flag that touches
                                                                 # dos_re, and only lazily -- the
                                                                 # default path never does)

Controls: arrow keys = move, Space = fire, Tab = secondary fire, ESC/close window = quit.

STATUS -- what is real vs. still a placeholder here (be honest, never fake a gap):

* Level data (tile plane, tile classes, block graphics, sprite bank) loads byte-exact from the
  original files, no VM (``overkill.asset_codecs.native_level.load_native_level``).
* Gameplay ticks (input decode, view-anchor movement, world-scroll, the object-update pass) run
  through the recovered pure systems (``overkill.native_game.NativeGame``), no VM. A handful of
  per-frame globals the object-update pass and action fan-out consume are not yet derivable
  VM-free (open Bucket-C gaps: ``99F6`` scripted input, the FULL ``A067`` fan-out paths, the
  ``9CB6`` contact probe, the coordinate rings). This runner supplies the same documented,
  default-safe values those systems' own dataclasses already default to for the "normal tick"
  case (0 / False) -- it does not invent new behaviour, it just doesn't yet model every rare
  special-mode branch. ``ref_box_x``/``ref_box_y`` (the view-anchor box the object pass reads)
  ARE derived for real, from the tracked view-anchor position -- see :func:`_object_update_globals`.
* RENDERING is currently a DEBUG PLACEHOLDER: a black background + a marker block at the player's
  tracked position. The real recovered visuals (the byte-exact starfield background, HUD chrome,
  and the sprite draw list) are each proven correct in isolation (``overkill/native_video/*``) but
  not yet WIRED into this standalone loop -- the fresh-level starfield INIT state and the
  object-pool -> sprite-pixel bridge are still-open integration gaps (see
  ``docs/overkill/overnight_endgame_execution.md`` Buckets B/C). When those land, :func:`_render_indices`
  is where they plug in.
* On any exception from a gameplay stage (a real unrecovered gap) the runner stops the tick loop,
  prints the gap, and holds the last frame -- it never silently fakes forward past a divergence.

This replaces ``scripts/native_play.py``, which was NOT a standalone game: its default mode only
presented one captured VM snapshot, and its ``--backend native`` mode (in ``scripts/play.py``)
spawned a full VM child process to actually run the game -- a hybrid presenter, not VM-less. That
VM-child machinery has been removed from ``play.py`` entirely; this file is the one true
VM-less standalone.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.native_game import NativeGame  # noqa: E402
from overkill.recovered.domain.frame_loop import FrameInput  # noqa: E402
from overkill.recovered.domain.frame_snapshot import CameraState, HudLayer  # noqa: E402
from overkill.recovered.domain.native_game_state import NativeGameState  # noqa: E402
from overkill.recovered.domain.object_slots import ObjectPool  # noqa: E402
from overkill.recovered.domain.object_update import ObjectUpdateGlobals  # noqa: E402
from overkill.recovered.systems.input import (  # noqa: E402
    DEFAULT_CONTROL_MAP,
    FIXED_DIRECTION_KEYS,
    key_state_from_pressed,
)
from overkill.recovered.systems.tandy_screen import (  # noqa: E402
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TANDY_PALETTE_RGB,
)

DEFAULT_BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
DEFAULT_CONTAINER = ROOT / "assets" / "OVERKILL"

_ANCHOR_STRIDE = 0x38          # the object-slot record size every pool uses
_ANCHOR_BASE = 0x237C          # DS:237C -- the special/view-anchor slot's own base
_GAMEPLAY_BASE = 0x2B5C        # DS:2B5C -- the gameplay object table
_EFFECT_BASE = 0x23B4          # DS:23B4 -- the effect object table
_OFF_X, _OFF_Y = 0x02, 0x04     # record byte offsets for X/Y (shared by every pool)


class _FlatMemory:
    """A read-only flat 1 MiB buffer with dos_re.memory.Memory's ``rb``/``rw`` shape.

    Used ONLY by :func:`_seed_state_from_snapshot` (the optional ``--snapshot`` debug path) so a
    captured VM memory dump can be read with the existing recovered ``read_native_game_state``
    projection WITHOUT importing ``dos_re`` -- this is a plain byte-array reader, not an emulator.
    """

    def __init__(self, data: bytes) -> None:
        self.data = data

    def _phys(self, seg: int, off: int) -> int:
        return ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF

    def rb(self, seg: int, off: int) -> int:
        return self.data[self._phys(seg, off)]

    def rw(self, seg: int, off: int) -> int:
        p = self._phys(seg, off)
        return self.data[p] | (self.data[(p + 1) & 0xFFFFF] << 8)


def _anchor_pool(x: int, y: int) -> ObjectPool:
    """The single-slot view-anchor pool (DS:237C) at a given tracked position."""
    words = [0] * (_ANCHOR_STRIDE >> 1)
    words[_OFF_X >> 1] = x & 0xFFFF
    words[_OFF_Y >> 1] = y & 0xFFFF
    words[0] = 1  # active
    return ObjectPool(base=_ANCHOR_BASE, stride=_ANCHOR_STRIDE, slots=(tuple(words),))


def _placeholder_starting_state() -> NativeGameState:
    """A PLACEHOLDER cold-start state: the real level-init gameplay state (player spawn point,
    initial object-table seed) is not yet a recovered pure system (Bucket F "level loader" is
    still open) -- this is a reasonable default spawn for exercising the loop, not a verified
    reproduction of the real game's level-start state. Use ``--snapshot`` for a real one."""
    return NativeGameState(
        special_pool=_anchor_pool(0x64, 0x80),
        object_pool=ObjectPool(base=_GAMEPLAY_BASE, stride=_ANCHOR_STRIDE, slots=()),
        effect_pool=ObjectPool(base=_EFFECT_BASE, stride=_ANCHOR_STRIDE, slots=()),
        camera=CameraState(x=0, y=0),
        hud=HudLayer(counters=(0, 0, 0), score_bcd=(0, 0)),
    )


def _seed_state_from_snapshot(snapshot_dir: Path) -> NativeGameState:
    """DEBUG: seed a REAL starting state from a captured VM memory dump (a static file read).

    Only this function ever touches recovered-adapter code that expects VM-shaped memory, and it
    does so over :class:`_FlatMemory` (no ``dos_re`` import) -- so passing ``--snapshot`` is the
    only way this program ever gets near workbench-only conventions, and even then it is just
    parsing bytes a previous (separate) run captured.
    """
    from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state

    mem = _FlatMemory((snapshot_dir / "memory_1mb.bin").read_bytes())
    cpu_line = json.loads((snapshot_dir / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu_line).group(1), 16)
    return read_native_game_state(mem, ds)


# Host key -> the recovered FIXED_DIRECTION_KEYS scancode it corresponds to (single source of
# truth: recovered.systems.input owns which scancodes the game actually reacts to).
_HOST_KEY_BY_SCANCODE = {0x48: "K_UP", 0x50: "K_DOWN", 0x4B: "K_LEFT", 0x4D: "K_RIGHT",
                         0x39: "K_SPACE", 0x0F: "K_TAB"}


def _pressed_scancodes(pygame, keys) -> set[int]:
    """Host key state -> the XT scancode set ``key_state_from_pressed`` expects."""
    out: set[int] = set()
    for scancode, _mask in FIXED_DIRECTION_KEYS:
        key_name = _HOST_KEY_BY_SCANCODE.get(scancode)
        if key_name is not None and keys[getattr(pygame, key_name)]:
            out.add(scancode)
    return out


def _object_update_globals(game: NativeGame) -> ObjectUpdateGlobals:
    """Build this tick's :class:`ObjectUpdateGlobals`.

    ``ref_box_x``/``ref_box_y`` are DERIVED for real: they are the DS:237E/2380 view-anchor box,
    which IS the tracked view-anchor slot's own X/Y fields (DS:237C+02/+04) -- the same slot
    ``game.state.special_pool`` already carries, just after this tick's player-movement step.
    Every other field is the documented default-safe "normal tick" value the dataclass itself
    already defaults to (see ``overkill.recovered.domain.object_update.ObjectUpdateGlobals``).
    """
    return ObjectUpdateGlobals(
        ref_box_x=game.state.special_pool.x_word(0),
        ref_box_y=game.state.special_pool.y_word(0),
        a278=0,
        tile_probe_suppressed=False,
        tiles=game.tile_context,
    )


def _render_indices(game: NativeGame):
    """DEBUG placeholder render: black background + a marker at the tracked player position.

    See the module docstring's STATUS section -- the real recovered background/HUD/sprite
    rendering is not yet wired into the standalone loop; this proves the loop and lets you SEE the
    player move, nothing more.
    """
    import numpy as np

    frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH), dtype=np.uint8)
    x = game.state.special_pool.x_word(0) % SCREEN_WIDTH
    y = game.state.special_pool.y_word(0) % SCREEN_HEIGHT
    y0, y1 = max(0, y - 2), min(SCREEN_HEIGHT, y + 3)
    x0, x1 = max(0, x - 2), min(SCREEN_WIDTH, x + 3)
    frame[y0:y1, x0:x1] = 15  # bright marker (Tandy palette index 15 = white)
    return frame


class PygameDisplay:
    """An SDL window blitting scaled (200,320) indexed frames through the Tandy palette."""

    def __init__(self, *, scale: int = 3, title: str = "OVERKILL - native (VM-less)") -> None:
        import pygame

        self.pygame = pygame
        import numpy as np

        self._np = np
        pygame.init()
        pygame.font.init()
        self.scale = scale
        self.size = (SCREEN_WIDTH * scale, SCREEN_HEIGHT * scale)
        self.screen = pygame.display.set_mode(self.size, pygame.RESIZABLE)
        pygame.display.set_caption(title)
        self._surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self._palette = self._np.array(TANDY_PALETTE_RGB, dtype=self._np.uint8)

    def draw(self, indices) -> None:
        rgb = self._palette[indices]
        self.pygame.surfarray.blit_array(self._surf, self._np.transpose(rgb, (1, 0, 2)))
        self.pygame.transform.scale(self._surf, self.size, self.screen)
        self.pygame.display.flip()

    def set_title(self, text: str) -> None:
        self.pygame.display.set_caption(text)

    def close(self) -> None:
        self.pygame.quit()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--level", type=int, default=0, help="0-based level to cold-load and play")
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE),
                    help="materialized static runtime bundle (memory_1mb.bin); build once via "
                         "overkill/static_runtime_bundle.py")
    ap.add_argument("--container", default=str(DEFAULT_CONTAINER), help="the OVERKILL asset container file")
    ap.add_argument("--snapshot", default=None,
                    help="DEBUG: seed a real starting NativeGameState from a captured VM snapshot "
                         "directory instead of the placeholder spawn (lazily touches dos_re; the "
                         "default path never does)")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args(argv)

    bundle_path, container_path = Path(args.bundle), Path(args.container)
    if not bundle_path.is_file():
        raise SystemExit(f"--bundle {bundle_path}: not found (build it via overkill/static_runtime_bundle.py)")
    if not container_path.is_file():
        raise SystemExit(f"--container {container_path}: not found -- point it at the OVERKILL game data")

    state = (_seed_state_from_snapshot(Path(args.snapshot)) if args.snapshot
             else _placeholder_starting_state())
    game = NativeGame.load_level(bundle_path.read_bytes(), container_path.read_bytes(), args.level, state)
    print(f"cold-loaded LEVEL{args.level + 1}: tile_plane={len(game.level.tile_plane)}B "
          f"blocks={len(game.level.blocks)}B graphics={len(game.level.graphics)}B (VM-free)")

    display = PygameDisplay(scale=args.scale)
    pygame = display.pygame
    clock = pygame.time.Clock()
    tick = 0
    gap: str | None = None
    running = True
    last_frame = _render_indices(game)
    try:
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                    running = False
            if gap is None:
                keys = pygame.key.get_pressed()
                pressed = _pressed_scancodes(pygame, keys)
                frame_input = FrameInput(control_map=DEFAULT_CONTROL_MAP,
                                         key_state=key_state_from_pressed(pressed))
                try:
                    game, _player_step = game.step(
                        frame_input,
                        no_clamp=False,
                        repeat_9790=0, state_232a=0, scroll_2350=game.row_base,
                        bdac=0, a958=0, be06=0,
                        source_index=0, source_x=0, source_y=0,
                        read_ds_word=lambda off: 0,
                        update_globals=_object_update_globals(game),
                        scroll_gate=(0, 0, 0),
                    )
                    tick += 1
                    last_frame = _render_indices(game)
                except Exception as exc:  # noqa: BLE001 -- a real unrecovered gap, report + hold
                    gap = f"{type(exc).__name__}: {exc}"
                    print(f"gameplay gap at tick {tick}: {gap}")
                display.set_title(f"OVERKILL - native (VM-less)  tick={tick}  "
                                  f"xy=({game.state.special_pool.x_word(0)},{game.state.special_pool.y_word(0)})")
            else:
                display.set_title(f"OVERKILL - native (VM-less)  HELD on gap: {gap[:70]}")
            display.draw(last_frame)
            clock.tick(args.fps)
    finally:
        display.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
