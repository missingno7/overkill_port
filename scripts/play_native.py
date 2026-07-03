#!/usr/bin/env python
"""OVERKILL -- the VM-less native standalone entrypoint.

Cold-loads a level from the game's own data files (``assets/OVERKILL`` + the materialized static
runtime bundle) and runs the recovered gameplay frame systems with **NO VM, no ``dos_re`` import
anywhere on this default run path** -- a genuinely standalone game, separable from the whole RE
workbench.

    python scripts/play_native.py                              # title/options screen (VM-free); Space starts
    python scripts/play_native.py --snapshot DIR               # + gameplay from a REAL captured state
    python scripts/play_native.py --no-title --snapshot DIR    # straight into gameplay

Controls: title -> Space starts; in game: arrow keys = move, Space = fire, ESC/close = quit.

STATUS -- every layer here is REAL recovered code (no placeholders, fail loud on gaps):

* FRONT-END: the title/options screen is the real ``OKMENU.ENC`` decoded VM-free through the
  recovered codecs (``native_video.front_end.decode_fullscreen_image``), byte-exact vs the VM apart
  from the red key-letter overlay the menu draws (a next front-end slice). Not a screenshot -- a
  live decode from the game data.
* Level data (tile plane, tile classes, block graphics, sprite bank) loads byte-exact from the
  original files, no VM (``overkill.asset_codecs.native_level.load_native_level``).
* Gameplay ticks (input decode, view-anchor movement, world-scroll, the object-update pass) run
  through the recovered pure systems (``overkill.native_game.NativeGame``), no VM. A handful of
  per-frame globals are still-open Bucket-C gaps (``99F6`` scripted input, the FULL ``A067`` fan-out,
  the ``9CB6`` contact probe, the coordinate rings); this runner passes the systems' own documented
  "normal tick" defaults, and ``ref_box_x``/``ref_box_y`` are DERIVED for real (see
  :func:`_object_update_globals`).
* RENDERING: the real recovered parallax STARFIELD background (``native_video.starfield_plate
  .render_starfield_plate``, proven byte-exact vs the VM), advanced each frame by the recovered
  ``advance_starfield`` move. The SPRITE layer (player + enemies) is the next piece to wire -- the
  object-record -> sprite-pixel bridge -- so today the standalone draws the real background but not
  yet the ships; it does NOT fake a ship in the meantime.
* There is NO placeholder starting state: the cold level-start state is not a recovered VM-free
  system yet (Bucket F level loader), so gameplay REQUIRES ``--snapshot`` (a real captured state) and
  fails loud without it, rather than invent a spawn.
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
from overkill.recovered.domain.native_game_state import NativeGameState  # noqa: E402
from overkill.recovered.domain.object_update import ObjectUpdateGlobals  # noqa: E402
from overkill.recovered.domain.starfield import STAR_COUNT, Star, StarfieldState  # noqa: E402
from overkill.recovered.systems.input import (  # noqa: E402
    DEFAULT_CONTROL_MAP,
    FIXED_DIRECTION_KEYS,
    key_state_from_pressed,
)
from overkill.recovered.systems.starfield import advance_starfield  # noqa: E402
from overkill.recovered.systems.tandy_screen import (  # noqa: E402
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TANDY_PALETTE_RGB,
)
from overkill.native_video.front_end import TITLE_OPTIONS, decode_fullscreen_image  # noqa: E402

DEFAULT_BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
DEFAULT_CONTAINER = ROOT / "assets" / "OVERKILL"


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


def _read_starfield(mem: "_FlatMemory", ds: int) -> StarfieldState:
    """Read the recovered starfield state (40 stars + the 3 layer counters + the enable gate) from a
    captured game data segment -- the same fields ``overkill.probes.verify_native_starfield`` proves
    reproduce the VM's parallax move byte-exact. Plain byte reads, no VM."""
    stars = tuple(
        Star(mem.rw(ds, (0xC6C1 + i * 6) & 0xFFFF),
             mem.rw(ds, (0xC6C3 + i * 6) & 0xFFFF),
             mem.rw(ds, (0xC6C5 + i * 6) & 0xFFFF))
        for i in range(STAR_COUNT)
    )
    counters = (mem.rw(ds, 0xC812), mem.rw(ds, 0xC814), mem.rw(ds, 0xC816))
    enabled = mem.rw(ds, 0xA95A) != 0xFFFF
    return StarfieldState(stars, counters, enabled)


def _seed_state_from_snapshot(snapshot_dir: Path) -> tuple[NativeGameState, StarfieldState]:
    """Seed a REAL starting state from a captured VM memory dump (a static file read) -- the game
    state AND the starfield state, both projected from the same captured data segment.

    The cold level-start state (player spawn + object-table seed + the starfield init) is NOT yet a
    recovered pure system (Bucket F "level loader" is still open), so there is no VM-free way to
    produce it from the raw files today; rather than fake one, this program requires a captured
    ``--snapshot`` to obtain a REAL starting state, and fails loud without it (see ``main``). Reading
    is over :class:`_FlatMemory` (no ``dos_re`` import) -- just parsing bytes a previous run captured.
    """
    from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state

    mem = _FlatMemory((snapshot_dir / "memory_1mb.bin").read_bytes())
    cpu_line = json.loads((snapshot_dir / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu_line).group(1), 16)
    return read_native_game_state(mem, ds), _read_starfield(mem, ds)


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


def _render_frame(game: NativeGame, starfield: StarfieldState):
    """Render the real recovered playfield background: the parallax starfield plate.

    This is the byte-exact recovered starfield (``native_video.starfield_plate.render_starfield_plate``,
    proven vs the VM), plotted at the game's live present cursor (DS:234C = ``game.row_source``). It is
    the BACKGROUND layer only; the sprite layer (player/enemies) is the next recovered piece to wire --
    the object-record -> sprite-pixel bridge -- and until it lands this draws the real background, not a
    fake ship. No placeholder: every pixel here is the recovered starfield.
    """
    from overkill.native_video.starfield_plate import render_starfield_plate

    return render_starfield_plate(starfield, game.row_source)


def _run_title_screen(display, pygame, container_data) -> bool:
    """Show the REAL title/options screen (OKMENU.ENC), VM-free, until FIRE (Space) or quit.

    This is the recovered front-end render: the whole title/options screen decodes from one container
    asset through the pure codecs (``native_video.front_end.decode_fullscreen_image``) -- no VM, no
    placeholder.  Returns True to advance into the game, False if the user quit.
    """
    title = decode_fullscreen_image(container_data, TITLE_OPTIONS)
    display.set_title("OVERKILL - native (VM-less)  [title screen -- Space = start, Esc = quit]")
    clock = pygame.time.Clock()
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return False
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                return True
        display.draw(title)
        clock.tick(30)


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
                    help="REQUIRED for gameplay: a captured VM snapshot directory to seed the REAL "
                         "starting game+starfield state (the cold level-start state is not a recovered "
                         "system yet -- Bucket F level loader). Reads bytes only, no VM.")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--no-title", action="store_true", help="skip the title/options screen, go straight to gameplay")
    args = ap.parse_args(argv)

    bundle_path, container_path = Path(args.bundle), Path(args.container)
    if not bundle_path.is_file():
        raise SystemExit(f"--bundle {bundle_path}: not found (build it via overkill/static_runtime_bundle.py)")
    if not container_path.is_file():
        raise SystemExit(f"--container {container_path}: not found -- point it at the OVERKILL game data")
    # No placeholder spawn: the cold level-start state is not recovered yet, so fail loud rather than
    # fake one. A real starting state comes only from a captured snapshot until the level loader lands.
    if not args.snapshot:
        raise SystemExit(
            "gameplay needs a real starting state: pass --snapshot DIR (a captured VM snapshot).\n"
            "The cold level-start state (player spawn + object seed + starfield init) is not yet a "
            "recovered VM-free system (Bucket F level loader is still open) -- there is no honest way "
            "to cold-start gameplay without the VM today, and this program will not fake one.")

    container_data = container_path.read_bytes()
    state, starfield = _seed_state_from_snapshot(Path(args.snapshot))
    game = NativeGame.load_level(bundle_path.read_bytes(), container_data, args.level, state)
    print(f"cold-loaded LEVEL{args.level + 1}: tile_plane={len(game.level.tile_plane)}B "
          f"blocks={len(game.level.blocks)}B graphics={len(game.level.graphics)}B (VM-free)")

    display = PygameDisplay(scale=args.scale)
    pygame = display.pygame

    # Front-end: open on the REAL title/options screen (VM-free), like the actual game. Space starts.
    if not args.no_title:
        if not _run_title_screen(display, pygame, container_data):
            display.close()
            return 0

    clock = pygame.time.Clock()
    tick = 0
    gap: str | None = None
    running = True
    last_frame = _render_frame(game, starfield)
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
                    starfield = advance_starfield(starfield)  # the recovered parallax move, one frame
                    tick += 1
                    last_frame = _render_frame(game, starfield)
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
