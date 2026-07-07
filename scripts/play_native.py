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
  ``advance_starfield`` move, PLUS the full object SPRITE layer -- the player ship (with exhaust
  flames), enemies and effects -- through the recovered object-record -> sprite-pixel bridge
  (``native_video.object_sprites.object_sprite_blocks``), proven byte-exact vs the VM's 7596
  draw-type dispatch. On the L3 capture the whole composed frame matches the VM present page
  0-for-0. Objects mid-animation-phase or using the OR-inverted variant are not drawn yet (documented
  gaps) -- they are SKIPPED, never faked.
* There is NO placeholder starting state: the DEFAULT (no ``--snapshot``) cold-boots the level-start
  state entirely from the recovered seeds (``overkill.recovered.adapters.cold_level_start``) -- no VM,
  no capture. This includes the enemy wave: the level-object-script walker (``4A65``) and the whole
  object behaviour walk run over a DGROUP image seeded identically to the projected game state, so a
  cold ``--level 0`` spawns/moves real enemies (``overkill.probes.verify_play_native_cold``, PASS for
  planet 1). ``--snapshot`` remains a debug override to seed from a captured VM state instead.
* GAMEPLAY-EXIT BOUNDARY: each frame the loop runs the recovered, demo-witnessed
  ``detect_gameplay_transition`` (death / game-over / scripted level-end, the 1010:97B2 flags) and
  STOPS fail-loud if one fires -- the native runtime cannot follow the unrecovered 9734/9902/9908
  continuations, so it reports the exit instead of running blindly past it. (The anchor death counter
  is live; the other trigger cells are seeded-static until the native loop runs the stages that mutate
  them, so on a normal mid-level capture no exit fires -- a fail-loud guard, never a fake.)
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
import dataclasses
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.native_app import GameplayFrameSkeleton  # noqa: E402
from overkill.native_game import NativeGame  # noqa: E402
from overkill.recovered.adapters.flat_memory import FlatMemory  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402
from overkill.recovered.systems.frame_loop import (  # noqa: E402
    death_tail_reached_9aff,
    detect_gameplay_transition,
    step_death_tail_9aff,
)
from overkill.recovered.domain.frame_loop import FrameInput, GameplayExit  # noqa: E402
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
from overkill.native_video.object_sprites import (  # noqa: E402
    SpriteDrawContext,
    object_sprite_blocks,
)

DEFAULT_BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
DEFAULT_CONTAINER = ROOT / "assets" / "OVERKILL"

# The three sprite-frame tables + the draw-type dispatch live in the game code segment (CS:1010) --
# constants materialized in the static bundle (identical there and in every snapshot).
_CS = 0x1010
_TABLE_75A6, _TABLE_768E, _TABLE_7746 = 0x9392, 0x9192, 0x8F92
_SPRITE_CELL_STRIDE_OFF = 0x1028   # ds:[1028] -- 75A6's source advance to the +10 second slot is >>1
_ANCHOR_RECORD = 0x237C            # the player view-anchor record (special_pool slot 0)
_COLD_ROW_SOURCE = 0x5B00          # DS:234C -- the fixed row-source start (NativeGame's level-post-load default)
_COLD_ROW_BASE = 0x009C            # DS:2350 -- level-load leaves the view row base here: 60C5 sets 0xEA0,
#                                    then the 16x A781 warm-up scroll settles it to 0x9C (60D5 cmp); this
#                                    is the frame-0 level-start scroll (row_base=0 underflows the tile probe)
_PLANET = (1, 2, 3, 4, 5, 0)      # == cold_level_start.LEVEL_INDEX_TO_PLANET: LEV{n} assets are
#                                    PLANET-keyed; every load below maps the 0-based level index
_COLD_ROWS_TO_MILESTONE = 0x0110   # DS:A978 at level-start: confirmed empirically for ALL SIX planets --
#                                    each planet's level-object script's own FIRST entry trigger_row is
#                                    0x110 (read directly from the cold data: DS:[C5E9+p*2] -> the cursor
#                                    cell -> the script head -> its first trigger_row word, for p in 0..5)


def _read_starfield(mem: "FlatMemory", ds: int) -> StarfieldState:
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


@dataclass(frozen=True)
class _SeededStart:
    """A REAL starting point read from a captured snapshot: the game+starfield state, the sprite
    half-stride, and the live scroll cursor trio (DS:234C/234E/2350) so the first native frame lands
    the world + sprites exactly where the VM had them.  (The gameplay-exit detector inputs are NOT
    carried here anymore -- they are read LIVE from the walk image each tick, ADR-1.)"""

    state: NativeGameState
    starfield: StarfieldState
    half_stride: int
    origin_x: int    # DS:234E
    row_base: int    # DS:2350
    row_source: int  # DS:234C
    rows_to_milestone: int  # DS:A978 -- the level-script scroll-trigger counter


def _seed_state_from_snapshot(snapshot_dir: Path) -> "_SeededStart":
    """Seed a REAL starting state from a captured VM memory dump (a static file read) -- the game
    state, the starfield state, the 75A6 sprite half-stride (``ds:[1028] >> 1``) and the live scroll
    cursor, all projected from the same captured data segment.

    The cold level-start state (player spawn + object-table seed + the starfield init) is NOT yet a
    recovered pure system (Bucket F "level loader" is still open), so there is no VM-free way to
    produce it from the raw files today; rather than fake one, this program requires a captured
    ``--snapshot`` to obtain a REAL starting state, and fails loud without it (see ``main``). Reading
    is over :class:`FlatMemory` (no ``dos_re`` import) -- just parsing bytes a previous run captured.
    """
    from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state

    mem = FlatMemory((snapshot_dir / "memory_1mb.bin").read_bytes())
    cpu_line = json.loads((snapshot_dir / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu_line).group(1), 16)
    return _SeededStart(
        state=read_native_game_state(mem, ds),
        starfield=_read_starfield(mem, ds),
        half_stride=(mem.rw(ds, _SPRITE_CELL_STRIDE_OFF) >> 1) & 0xFFFF,
        origin_x=mem.rw(ds, 0x234E),
        row_base=mem.rw(ds, 0x2350),
        row_source=mem.rw(ds, 0x234C),
        rows_to_milestone=mem.rw(ds, 0xA978),
    )


def _cold_seeded_start(bundle_data: bytes, level_index: int = 0) -> "_SeededStart":
    """Assemble a REAL cold level-start :class:`_SeededStart` -- no VM, no gameplay snapshot.

    The game + starfield STATE is built entirely from the recovered level-start seeds
    (:func:`overkill.recovered.adapters.cold_level_start.build_cold_level_start` -- session init + C4DB
    setup + gameplay-pool seed + control reset + player spawn + cold starfield + the post-intro health
    bar, seeded with the chosen PLANET via ``level_index``).  The render params the loop also needs --
    the scroll cursor (DS:234C/234E/2350) and the sprite half-stride (``ds:[1028]>>1``) -- are read
    from the SAME cold runtime data image (byte-array read, no VM).

    The scroll cursor is the LEVEL-POST-LOAD origin (``origin_x = 0``, ``row_base = _COLD_ROW_BASE``,
    ``row_source = _COLD_ROW_SOURCE``) -- the values the level-load leaves in DS:234E/2350/234C (NOT the
    cold image's live cursor, which is mid-scroll and would wrap the starfield page).  ``row_base = 0x9C``
    (not 0) matters: the object-pass tile probe subtracts against ``row_base``, so ``row_base = 0`` would
    UNDERFLOW for any object below the top row (crash).  The sprite half-stride is read from the cold image.
    ``rows_to_milestone = _COLD_ROWS_TO_MILESTONE`` (DS:A978) is likewise a level-load constant, not read
    from the raw cold image (confirmed empirically identical -- 0x110 -- for all six planets' level
    scripts' own first trigger row).
    """
    from overkill.recovered.adapters.cold_level_start import build_cold_level_start
    from overkill.recovered.adapters.starfield_adapter import DATA_SEGMENT

    state, starfield = build_cold_level_start(bundle_data, level_index)
    mem = FlatMemory(bundle_data)
    ds = DATA_SEGMENT
    return _SeededStart(
        state=state,
        starfield=starfield,
        half_stride=(mem.rw(ds, _SPRITE_CELL_STRIDE_OFF) >> 1) & 0xFFFF,
        origin_x=0x0000,               # level-post-load view origin (DS:234E)
        row_base=_COLD_ROW_BASE,       # level-post-load view row base (DS:2350) -- 0x9C, see the constant
        row_source=_COLD_ROW_SOURCE,   # DS:234C -- the fixed row-source start
        rows_to_milestone=_COLD_ROWS_TO_MILESTONE,  # DS:A978 -- 0x110, see the constant
    )


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


def _build_sprite_context(bundle_data: bytes, container_data: bytes, game: NativeGame,
                          half_stride: int) -> SpriteDrawContext:
    """Assemble the VM-free object->sprite draw context from the game's own data.

    The five sprite banks are the recovered de-planarized buffers (the four global startup banks from
    ``load_shared_startup_assets`` -- MANEXPL/2X2/2X2C/1X1 -- plus this level's own sprite bank), and
    the three frame tables are the ``CS:9392/9192/8F92`` word tables read from the static bundle (game
    code constants). This is exactly the input ``object_sprite_blocks`` maps each object slot through,
    proven byte-exact vs the VM's 7596 dispatch by ``verify_native_object_sprites``.
    """
    from overkill.asset_codecs.shared_assets import load_shared_startup_assets

    shared = load_shared_startup_assets(container_data)

    def cs_word(off: int) -> int:
        p = (_CS * 16 + (off & 0xFFFF)) & 0xFFFFF
        return bundle_data[p] | (bundle_data[(p + 1) & 0xFFFFF] << 8)

    return SpriteDrawContext(
        common_bank=shared["MANEXPL.BIC"],
        level_bank=game.level.graphics,
        wide_bank=shared["2X2.BIC"],
        wide_bank_hi=shared["2X2C.BIC"],
        compact_bank=shared["1X1.BIC"],
        table_75a6=[cs_word(_TABLE_75A6 + 2 * k) for k in range(0x400)],
        table_768e=[cs_word(_TABLE_768E + 2 * k) for k in range(0x100)],
        table_7746=[cs_word(_TABLE_7746 + 2 * k) for k in range(0x100)],
        half_stride=half_stride,
    )


def _render_frame(game: NativeGame, starfield: StarfieldState, ctx: SpriteDrawContext,
                  tile_base=None):
    """Render the real recovered playfield: terrain + the starfield plate + the sprite layer.

    ``tile_base`` (optional) is the composed terrain window (``compose_tile_window``,
    pixel-exact on the pure-VM 1:1 instrument): the page BASE -- stars fill only unlit pixels
    (the 4D15 rule), sprites composite on top.  The background is the byte-exact recovered
    starfield (``render_starfield_plate``, proven vs the VM) at the game's live present cursor
    (DS:234C = ``game.row_source``). Over it, the recovered object->sprite bridge
    (``object_sprite_blocks``) draws every active object, proven byte-exact vs the VM's 7596
    draw-type dispatch. (Objects mid-animation-phase or using the OR-inverted variant are not
    drawn yet -- documented gaps -- skipped, never faked.)
    """
    import numpy as np

    from overkill.native_video.frame import SnapshotSprite
    from overkill.native_video.playfield import compose_playfield_indices
    from overkill.native_video.starfield_plate import render_starfield_plate

    from overkill.native_video.object_sprites import object_sprite_blocks_a846
    plate = render_starfield_plate(starfield, game.row_source)
    if tile_base is not None:
        plate = np.where(tile_base > 0, tile_base, plate)
    blocks = object_sprite_blocks_a846(game.state.special_pool, game.state.effect_pool,
                                       game.state.object_pool, ctx)
    if not blocks:
        return plate
    sprite = SnapshotSprite(identity=0, sprite_id=0, anim_phase=0, screen_di=0, blocks=tuple(blocks))
    return compose_playfield_indices(plate, [sprite], game.row_source)


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


def _run_level_select(display, pygame, container_data, image, start_beda: int = 0) -> "int | None":
    """The REAL level-select screen (the D3F0 loop), VM-free: LEVSCR.ENC + the two D4AA cursors
    (cells from CHOOSE.ENC, xy/pointer tables read from the machine image), driven by the
    RECOVERED grid handlers (D476/D480/D488/D490) and the D424 fire resolve.

    Returns ``(level_index, difficulty)`` or None if the user quit.  The level index == the grid
    cell (D424 writes ``2356 = cell``; the 971A start advance makes it planet ``cell+1`` --
    exactly ``LEVEL_INDEX_TO_PLANET[cell]``).  ``difficulty`` is the second (BEDC) cursor, 0..2
    (EASIER/NORMAL/HOLY COW!) -- ``DS:BEDC`` is the difficulty global the gameplay's C237 spawn
    throttle reads; the on-screen "[D]ifficulty" key cycles it.  Movement keys wait for release
    between steps, like D43B."""
    import numpy as np

    from overkill.asset_codecs.container import load_container_asset
    from overkill.asset_codecs.planar import deplanarize_tandy
    from overkill.native_video.level_select import compose_level_select
    from overkill.recovered.adapters.level_select_state import read_level_select_tables
    from overkill.recovered.systems.menu import (
        resolve_level_select_fire_d424, step_level_select_decrement_d488,
        step_level_select_increment_d490, step_level_select_page_down_d476,
        step_level_select_page_up_d480,
    )

    levscr = decode_fullscreen_image(container_data, "LEVSCR.ENC")
    choose = np.frombuffer(deplanarize_tandy(load_container_asset(container_data, "CHOOSE.ENC"),
                                             sprite_mode=False, emit_item_headers=True),
                           dtype=np.uint8)
    level_xy, option_xy, _ = read_level_select_tables(image)
    beda, bedc = start_beda % 6, 0
    display.set_title("OVERKILL - native (VM-less)  [level select -- arrows = move, "
                      "Space = start, Esc = back]")
    clock = pygame.time.Clock()
    # the D434 dispatch: bit1(Right)->D476 +3, bit2(Left)->D480 -3, bit8(Up)->D488 -1,
    # bit4(Down)->D490 +1 -- keydown events give the release-wait (D43B) step semantics.
    steps = {pygame.K_RIGHT: step_level_select_page_down_d476,
             pygame.K_LEFT: step_level_select_page_up_d480,
             pygame.K_UP: step_level_select_decrement_d488,
             pygame.K_DOWN: step_level_select_increment_d490}
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return None
            if ev.type == pygame.KEYDOWN and ev.key in steps:
                beda = steps[ev.key](beda).beda
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_d:
                bedc = (bedc + 1) % 3        # the "[D]ifficulty" key cycles the BEDC cursor
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                planet_2356 = resolve_level_select_fire_d424(beda).level
                # 971A/9744 then advances 2356 by one planet: FFFF->0 (the mothership),
                # k->k+1 -- which is LEVEL_INDEX_TO_PLANET[cell], so the cell IS the level index.
                del planet_2356
                return beda, bedc
        display.draw(compose_level_select(levscr, choose, level_xy, option_xy, beda, bedc))
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
        # scale to the CURRENT window size -- the window is RESIZABLE, so self.size may be stale
        self.pygame.transform.scale(self._surf, self.screen.get_size(), self.screen)
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
                    help="OPTIONAL debug override: seed the starting game+starfield state from a captured "
                         "VM snapshot directory instead of the cold level-start seeds. Reads bytes only, "
                         "no VM. Omit it to cold-start the level from the recovered seeds (the default).")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--no-title", action="store_true", help="skip the title/options screen, go straight to gameplay")
    args = ap.parse_args(argv)

    bundle_path, container_path = Path(args.bundle), Path(args.container)
    if not bundle_path.is_file():
        raise SystemExit(f"--bundle {bundle_path}: not found (build it via overkill/static_runtime_bundle.py)")
    if not container_path.is_file():
        raise SystemExit(f"--container {container_path}: not found -- point it at the OVERKILL game data")
    container_data = container_path.read_bytes()
    bundle_data = bundle_path.read_bytes()
    # Front-end FIRST (like the original 96E0 flow): title -> level select -> the game build for
    # the PICKED level.  --no-title (and the probes) skip straight to args.level.
    display = PygameDisplay(scale=args.scale)
    pygame = display.pygame
    if not args.no_title:
        if not _run_title_screen(display, pygame, container_data):
            display.close()
            return 0
        from overkill.recovered.adapters.flat_memory import MutFlatMemory as _MFM
        picked = _run_level_select(display, pygame, container_data, _MFM(bundle_data),
                                   start_beda=args.level)
        if picked is None:
            display.close()
            return 0
        args.level, menu_difficulty = picked
    else:
        menu_difficulty = None

    # DEFAULT: cold-start the level from the recovered level-start seeds (VM-free, no capture). The
    # --snapshot path stays as a debug override that seeds from a captured VM state instead.
    if args.snapshot:
        seed = _seed_state_from_snapshot(Path(args.snapshot))
    else:
        seed = _cold_seeded_start(bundle_data, args.level)
    starfield = seed.starfield
    # Cold-load the level, then plant the captured live scroll cursor (DS:234C/234E/2350) so the first
    # native frame renders the world + sprites exactly where the VM had them.
    game = dataclasses.replace(
        NativeGame.load_level(bundle_data, container_data, _PLANET[args.level % 6], seed.state,
                              origin_x=seed.origin_x, row_base=seed.row_base),
        row_source=seed.row_source,
        rows_to_milestone=seed.rows_to_milestone,
    )
    sprite_ctx = _build_sprite_context(bundle_data, container_data, game, seed.half_stride)
    print(f"cold-loaded LEVEL{args.level + 1}: tile_plane={len(game.level.tile_plane)}B "
          f"blocks={len(game.level.blocks)}B graphics={len(game.level.graphics)}B (VM-free)")

    clock = pygame.time.Clock()
    # The frame runs through the skeleton (overkill.native_app) in the ORIGINAL 97B2 stage order:
    # present the state 9B2E produced last tick, THEN advance -- the 9B2E-family step polls its own
    # input, exactly like the original's input-poll-first controller.  The mutable cell carries the
    # carried state between the two closures.
    #
    # OBJECT-FRAME OWNERSHIP: the enemy wave (the whole A9D3..AA25 behaviour walk) runs over a
    # MutFlatMemory DGROUP image via overkill.native_walk_frame -- the shadow-proven registry of
    # recovered systems -- so play_native SHOWS the real enemies (controller/wave/shots/companion).
    # NativeGame still owns the player anchor + scroll; each tick syncs the anchor into the image,
    # advances the object frame, and projects the pools back out for the renderer.  On the cold path
    # the image is seeded identically to `seed.state` (build_cold_level_start_image -- the SAME
    # session/C4DB/gameplay-pool/control-reset/player-spawn writes), so the level-object-script
    # walker (4A65) fires from the SAME planet's spawn script the projected NativeGame is playing.
    from overkill.native_walk_frame import (  # noqa: E402
        advance_object_frame, level_tiles, project_state, sync_new_gameplay_records,
        sync_player_anchor, sync_screen_projection,
    )
    from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402
    from overkill.recovered.adapters.level_object_script import run_level_object_script_4a65  # noqa: E402
    from overkill.recovered.adapters.behavior_walk import (  # noqa: E402
        run_level_end_arm_a680, run_outro_script_99f6,
    )
    from overkill.recovered.adapters.cold_level_start import (  # noqa: E402
        apply_respawn_seeds, build_cold_level_start, build_cold_level_start_image,
    )

    if args.snapshot:
        walk_image = MutFlatMemory((Path(args.snapshot) / "memory_1mb.bin").read_bytes())
    else:
        walk_image = build_cold_level_start_image(bundle_data, args.level, container_data)
    if menu_difficulty is not None:
        walk_image.ww(0x25CC, 0xBEDC, menu_difficulty)   # the menu's difficulty pick (DS:BEDC)

    # The HUD panel: composed per frame from the walk image's LIVE state cells through the
    # byte-exact-gated compose (verify_native_hud_panel) -- backdrop, chrome, counters, lives,
    # energy bar, score digits, planet digit.  Static inputs (the natively-decoded PANEL.ENC cell
    # library, the CS:0BE4 directory, the DGROUP glyph font) are read once.
    import numpy as _np  # noqa: E402
    from overkill.asset_codecs.container import load_container_asset  # noqa: E402
    from overkill.asset_codecs.planar import deplanarize_tandy  # noqa: E402
    from overkill.native_video.hud_panel import PANEL_LEFT_PX, panel_indices_from_page  # noqa: E402
    from overkill.recovered.adapters.hud_panel_state import (  # noqa: E402
        compose_hud_panel_from_image, read_hud_dir_table, read_hud_font,
    )
    hud_ctx = {
        "panel_source": _np.frombuffer(
            deplanarize_tandy(load_container_asset(container_data, "PANEL.ENC"),
                              sprite_mode=False, emit_item_headers=True), dtype=_np.uint8),
        "dir_table": read_hud_dir_table(walk_image),
        "font": read_hud_font(walk_image),
    }

    def _hud_panel_indices():
        return panel_indices_from_page(compose_hud_panel_from_image(walk_image, **hud_ctx))

    # The TERRAIN: the oracle-proven tile window composed from the walk image's LIVE plane +
    # the planet's LEV{n}BLX bank (both refreshed by the level-data unification) + the static
    # CS:8D92 table.  [959C] (rows >= 0xE5F, the level-end strip) still holds the bundle's
    # capture -- its asset identity is an open journal item.
    from overkill.native_video.tile_row import BANK2_ROW_BASE, compose_tile_window  # noqa: E402
    _tile_table = [walk_image.rw(0x1010, (0x8D92 + 2 * k) & 0xFFFF) for k in range(0x100)]

    def _tile_base():
        g = cell["game"]
        buf = _np.frombuffer(walk_image.data, dtype=_np.uint8)
        plane = buf[walk_image.rw(0x1010, 0x9592) * 16:
                    walk_image.rw(0x1010, 0x9592) * 16 + 0x10000]
        bank_ptr = 0x959C if g.row_base >= BANK2_ROW_BASE else 0x959A
        bank = buf[walk_image.rw(0x1010, bank_ptr) * 16:
                   walk_image.rw(0x1010, bank_ptr) * 16 + 0x10000]
        tiles = _np.zeros((200, 320), dtype=_np.uint8)
        compose_tile_window(tiles, plane, g.row_base, _tile_table, bank,
                            phase_234e=g.origin_x)
        return tiles

    # The 98EB game-over banner: THEND.BIC (byte-matched to the VM's CS:[95B2] segment) -- one
    # {rows,width} cell, drawn by 5C35 at (0, 0x4E) over the playfield.  Decoded once, VM-free.
    _banner_dec = _np.frombuffer(
        deplanarize_tandy(load_container_asset(container_data, "THEND.BIC"),
                          sprite_mode=False, emit_item_headers=True), dtype=_np.uint8)
    _banner_rows = int(_banner_dec[0]) | (int(_banner_dec[1]) << 8)
    _banner_stride = ((int(_banner_dec[2]) | (int(_banner_dec[3]) << 8)) << 2)
    _b = _banner_dec[4: 4 + _banner_rows * _banner_stride].reshape(_banner_rows, _banner_stride)
    _banner_idx = _np.empty((_banner_rows, _banner_stride * 2), dtype=_np.uint8)
    _banner_idx[:, 0::2] = (_b >> 4) & 0x0F
    _banner_idx[:, 1::2] = _b & 0x0F
    _GAME_OVER_BANNER_Y = 0x4E     # 5C35: 5A00(x=0, y=0x4E)
    _GAME_OVER_HOLD_TICKS = 0x96   # 98F4: the 150-frame 50C9 hold

    cell = {"game": game, "starfield": starfield, "tick": 0, "walk_gap": None,
            "level": args.level, "sprite_ctx": sprite_ctx, "game_over": None}

    def _load_next_level() -> None:
        """The 9744 LEVEL-ADVANCE continuation, natively: the SAME cold-boot machinery reloads the
        NEXT level (the real 9744 -> 9755 tail does the full reload) with the SESSION persisting --
        score (2314/2316) and lives (2358) carry over (96EE, which would reset them, is a fresh-
        session-only step and is overwritten here).  The walk image's BUFFER is replaced in place so
        every closure keeps its reference."""
        nxt = (cell["level"] + 1) % 6
        score_lo = walk_image.rw(0x25CC, 0x2314)
        score_hi = walk_image.rw(0x25CC, 0x2316)
        lives = walk_image.rw(0x25CC, 0x2358)
        new_img = build_cold_level_start_image(bundle_data, nxt, container_data)
        new_img.ww(0x25CC, 0x2314, score_lo)
        new_img.ww(0x25CC, 0x2316, score_hi)
        new_img.ww(0x25CC, 0x2358, lives)
        walk_image.data[:] = new_img.data
        nstate, nstarfield = build_cold_level_start(bundle_data, nxt)
        cell["game"] = dataclasses.replace(
            NativeGame.load_level(bundle_data, container_data, _PLANET[nxt % 6], nstate,
                                  origin_x=0, row_base=_COLD_ROW_BASE),
            row_source=_COLD_ROW_SOURCE, rows_to_milestone=_COLD_ROWS_TO_MILESTONE)
        cell["starfield"] = nstarfield
        cell["sprite_ctx"] = _build_sprite_context(bundle_data, container_data, cell["game"],
                                                   seed.half_stride)
        cell["level"] = nxt
        print(f"LEVEL COMPLETE -> level {nxt + 1} (score/lives carried, lives={lives})")

    def _restart_session(lvl: int) -> None:
        """The 96E0 continuation after game over: a FRESH session on the picked level -- the
        SAME cold-boot machinery, whose 96EE fresh-session init resets score and lives."""
        new_img = build_cold_level_start_image(bundle_data, lvl, container_data)
        walk_image.data[:] = new_img.data
        nstate, nstarfield = build_cold_level_start(bundle_data, lvl)
        cell["game"] = dataclasses.replace(
            NativeGame.load_level(bundle_data, container_data, _PLANET[lvl % 6], nstate,
                                  origin_x=0, row_base=_COLD_ROW_BASE),
            row_source=_COLD_ROW_SOURCE, rows_to_milestone=_COLD_ROWS_TO_MILESTONE)
        cell["starfield"] = nstarfield
        cell["sprite_ctx"] = _build_sprite_context(bundle_data, container_data, cell["game"],
                                                   seed.half_stride)
        cell["level"] = lvl
        cell["game_over"] = None
        print(f"fresh session: LEVEL{lvl + 1} (score/lives reset by 96EE)")

    def _advance() -> None:
        keys = pygame.key.get_pressed()
        pressed = _pressed_scancodes(pygame, keys)
        frame_input = FrameInput(control_map=DEFAULT_CONTROL_MAP,
                                 key_state=key_state_from_pressed(pressed))
        g = cell["game"]
        # The level-object-script trigger check (4A65, called from the DRAW/PRESENT half of the
        # original loop -- "present last tick's state, then advance") compares against the
        # rows_to_milestone value AS IT STOOD before this tick's scroll step, not after: a cold-start
        # origin_x of 0 pulls a row (and decrements rows_to_milestone) on frame 0's OWN scroll tick,
        # so checking the post-step value would skip the very entry the cold seed was built to match
        # (confirmed empirically: rows_to_milestone's cold value equals the first trigger_row exactly).
        pre_step_rows_to_milestone = g.rows_to_milestone
        pre_step_row_base = g.row_base
        # The 9B61 death branch: when the tracked anchor state is absent (A95A == FFFF after the
        # native 9E69/9EA3 death chain, or the A97A bar empty), the original SKIPS the whole
        # player-move/scroll/fan-out flow and runs the 9AFF death tail instead -- the anchor's +08
        # cell becomes the explosion-animation counter (incremented on 2326==3 phases; the renderer
        # draws those frames as the anchor sprite), firing the exit at 0x0F.  The object WALK still
        # runs during the death animation (proven: the demo shadow stayed byte-exact through the
        # demo's 5 real death beats).  The post-fire 4DBF call (the death jingle/text) is a declared
        # host boundary -- the loop stops fail-loud at the exit before any continuation anyway.
        dying = death_tail_reached_9aff(walk_image.rw(0x25CC, 0xA95A), walk_image.rw(0x25CC, 0xA97A))
        # The LEVEL-END OUTRO script (A47C phases 1..3): the recovered autopilot's synthetic input
        # bits REPLACE the keyboard, exactly as the original's scripted input overrides the poll --
        # the script flies the ship through the outro, then phase 3 raises A47C=4 -> the SCRIPTED
        # exit (A344) fires below.
        if not dying and walk_image.rw(0x25CC, 0xA47C) in (1, 2, 3):
            outro_bits = run_outro_script_99f6(walk_image)
            pressed = {sc for sc, mask in ((0x4D, 0x01), (0x4B, 0x02), (0x50, 0x04), (0x48, 0x08))
                       if outro_bits & mask}
            frame_input = FrameInput(control_map=DEFAULT_CONTROL_MAP,
                                     key_state=key_state_from_pressed(pressed))
        if dying:
            tail = step_death_tail_9aff(
                walk_image.rw(0x25CC, 0xA95A), walk_image.rw(0x25CC, 0xA97A),
                walk_image.rw(0x25CC, 0x2326), walk_image.rw(0x25CC, _ANCHOR_RECORD + 0x08))
            walk_image.ww(0x25CC, _ANCHOR_RECORD + 0x08, tail.anchor_counter)
            if tail.deactivate_anchor:
                walk_image.ww(0x25CC, _ANCHOR_RECORD + 0x00, 0)   # 9B11: the anchor slot deactivates
        else:
            g, _player_step = g.step(
                frame_input,
                no_clamp=False,
                repeat_9790=0, state_232a=0, scroll_2350=g.row_base,
                bdac=0, a958=0, be06=0,
                # the fire fan-out spawns from the firing object -- the player view-anchor (special_pool
                # slot 0) at its live position, so shots leave the ship's muzzle.
                source_index=0,
                source_x=g.state.special_pool.x_word(0), source_y=g.state.special_pool.y_word(0),
                read_ds_word=lambda off: 0,
                update_globals=_object_update_globals(g),
                # the REAL A66F gate inputs, live from the image (ADR-1): A47E is the walk-owned
                # active-enemy count, so the world scroll PAUSES while a wave is alive -- the real
                # game's pacing (the scroll resumes when the wave is cleared). A47C/A480 join in the
                # moment their stages (the boss script arm / the A480 countdown) go native.
                scroll_gate=(walk_image.rw(0x25CC, 0xA47C), walk_image.rw(0x25CC, 0xA47E),
                             walk_image.rw(0x25CC, 0xA480)),
                # the object pass is run over the DGROUP image below (the full behaviour walk), so skip
                # NativeGame's dataclass object pass when the image owns the pools -- no double-step.
                run_object_pass=walk_image is None,
            )
        # The 0xEA0 LEVEL-END milestone (the native scroll now APPLIES the milestone ticks and the
        # runtime owns the A680 arm's memory actions, live-traced): the moment row_base lands on the
        # plane end, arm the outro -- A47C=1 (the scroll gate then holds), the 62AA sweep kills every
        # remaining enemy (score and all), and the four A3EE outro objects (behavior 0x53) spawn.
        # The A47C outro PHASES (the autopilot fly-off -> A344 -> the next level) are the next slice;
        # until then the game holds on the armed outro scene fail-loud-visibly rather than stalling.
        if not dying and g.row_base == 0x0EA0 and pre_step_row_base != 0x0EA0 \
                and walk_image.rw(0x25CC, 0xA47C) == 0:
            run_level_end_arm_a680(walk_image)
            print(f"level-end arm at tick {cell['tick']}: the outro is on stage (A47C=1)")
        # THE TILE CUES (A81B -> 7948): each pulled row spawns its terrain actors -- crawlers,
        # turrets, the deployer.  Runs at the pull's PRE-decrement row (A7D0 pulls THEN subs),
        # gated like A831 (rows > 0xE52 skip).  Planet 1's handler is driven-oracle-proven
        # (verify_native_tile_cues); other planets skip with a note until theirs are decoded.
        # The 8209 +32/+34 caller-frame leak cells get 0 (an open sub-item; none of planet 1's
        # spawned behaviors read them).
        if not dying and g.row_base != pre_step_row_base and pre_step_row_base <= 0x0E52:
            if walk_image.rw(0x25CC, 0x2356) == 1:
                from overkill.recovered.adapters.tile_cues import run_tile_cue_row_7948
                spawned = run_tile_cue_row_7948(walk_image, pre_step_row_base)
                if spawned:
                    print(f"tile cues at row {pre_step_row_base:#06x}: spawned "
                          f"{[f'{r:04X}' for r in spawned]}")
        # The native OBJECT FRAME over the image: sync the player anchor + scroll, advance the whole
        # behaviour walk, and project the enemy/effect/shot pools back into g for rendering. Fail-loud
        # on an unrecovered object (holds the last good frame, like a gameplay-stage exception).
        if walk_image is not None and cell["walk_gap"] is None:
            sp = g.state.special_pool
            if not dying:
                # during the death anim the anchor is image-owned (the +08 explosion counter) -- the
                # dataclass side didn't step, so syncing would clobber the counter with a stale sprite.
                sync_player_anchor(walk_image, sp.x_word(0), sp.y_word(0), sp.word_at(0, 0x08))
            # ADR-1: anything the dataclass side created this tick flows into the image BEFORE the
            # walk -- otherwise fired shots would be destroyed by the projection below.
            sync_new_gameplay_records(walk_image, g.state.object_pool)
            walk_image.ww(0x25CC, 0x234E, g.origin_x)
            walk_image.ww(0x25CC, 0x2350, g.row_base)
            walk_image.ww(0x25CC, 0x234C, g.row_source)
            walk_image.ww(0x25CC, 0xA978, pre_step_rows_to_milestone)
            try:
                run_level_object_script_4a65(walk_image)
                advance_object_frame(walk_image, level_tiles(walk_image))
                # the A90C present-scan's projection: every record's +0x0C screen-di (the sprite
                # compositor's placement input) -- without it a cold image renders NOTHING.
                sync_screen_projection(walk_image)
                g = g.with_state(project_state(walk_image))
            except RecoveryGap as exc:
                cell["walk_gap"] = f"{type(exc).__name__}: {exc}"
                print(f"object-walk gap at tick {cell['tick']}: {cell['walk_gap']}")
        cell["game"] = g
        cell["starfield"] = advance_starfield(cell["starfield"])  # the recovered parallax move
        cell["tick"] += 1
        # The 97B2 gameplay-exit boundary: end this level fail-loud if a death / game-over / scripted
        # transition is detected (recovered + demo-witnessed as detect_gameplay_transition). The
        # trigger cells are read LIVE from the walk image (ADR-1: the image is the state) -- the
        # 9E69/9EA3 death chain natively writes A95A (FFFF on life exhaustion) and 2384, so a real
        # in-game death now reaches "anchor state absent" for real. A47C/A97A/2326 are still only
        # ever written by their VM-owned stages (the A47C script arm, the dying-mode 9B2E flow), so
        # today they hold their cold values -- live reads make them take effect the moment those
        # stages go native, with no further wiring. The anchor +08 counter is live (slot 0).
        exit_ = detect_gameplay_transition(
            a47c=walk_image.rw(0x25CC, 0xA47C), a95a=walk_image.rw(0x25CC, 0xA95A),
            a97a=walk_image.rw(0x25CC, 0xA97A), v2326=walk_image.rw(0x25CC, 0x2326),
            anchor_counter_after_inc=g.state.special_pool.word_at(0, 0x08),
        )
        if exit_ is not None:
            if exit_.exit is GameplayExit.DEATH:
                # The 9908 death CONTINUATION, natively: dec the lives (990B; the [978D] cheat
                # re-incs), queue the respawn jingle (BEFF=2), then the 9773 re-entry -- which is
                # the SAME level-start seed sequence the cold boot runs (C4DB + C3A6/C42F/C461 +
                # the post-intro bar), shared as apply_respawn_seeds -- plus the B5A9 formation-
                # cursor reset and the A8C2/20A6 re-inits. Score/planet/scroll persist (no 96EE,
                # no scroll writes -- the level continues from where it was). Audio (5F43 music)
                # and presentation (6176 HUD / C57C palette / D305 intro) stay host boundaries.
                lives = (walk_image.rw(0x25CC, 0x2358) - 1) & 0xFFFF
                if walk_image.rb(0x25CC, 0x978D):
                    lives = (lives + 1) & 0xFFFF
                walk_image.ww(0x25CC, 0x2358, lives)
                if lives == 0xFFFF:                   # 9773: lives exhausted -> the 98EB game-over flow
                    # 98EB natively: the THEND.BIC banner (5C35's [95B2] cell, target (0, 0x4E))
                    # holds ~0x96 frames, then jmp 96E0 -- the title flow (a fresh session on
                    # restart).  The 5283 high-score entry (far 1F8F:0000/0076) is NOT recovered:
                    # logged and SKIPPED, never faked.
                    cell["game_over"] = _GAME_OVER_HOLD_TICKS
                    print(f"GAME OVER at tick {cell['tick']}: the 98EB banner holds "
                          f"{_GAME_OVER_HOLD_TICKS} ticks, then the title screen "
                          "(the 5283 high-score entry is not recovered -- skipped)")
                    return
                if walk_image.rb(0x25CC, 0x98C0):
                    walk_image.wb(0x25CC, 0xBEFF, 0x02)
                apply_respawn_seeds(walk_image)
                walk_image.ww(0x25CC, 0xA8D0, 0xA8D2)  # B5A9: the formation-schedule cursor reset
                walk_image.ww(0x25CC, 0xA8C8, 0)
                walk_image.ww(0x25CC, 0xA8CC, 0)
                walk_image.ww(0x25CC, 0xA8C2, 0)
                walk_image.ww(0x25CC, 0x20A6, 0x20A8)  # the canned-random ring cursor reset (9792)
                # The death moment's 4DBF -> 0B3E runs the LEVEL-DATA re-init: traced live, the
                # demo's respawns land with the scroll back at the LEVEL START -- death restarts
                # the level (score/lives persist; the script cursors were rewound by the seeds).
                cell["game"] = dataclasses.replace(
                    g.with_state(project_state(walk_image)),
                    origin_x=0x0000, row_base=_COLD_ROW_BASE, row_source=_COLD_ROW_SOURCE,
                    rows_to_milestone=_COLD_ROWS_TO_MILESTONE)
                print(f"respawn at tick {cell['tick']}: lives={lives} (level restarts)")
                return
            if exit_.exit is GameplayExit.SCRIPTED:
                _load_next_level()          # the 9744 advance: the next level boots, session carried
                return
            raise RecoveryGap(
                f"gameplay exit {exit_.exit.name} (1010:97B2 -> {exit_.jump_target:#06x})",
                "the native loop detected a game-over/scripted transition; that target is not "
                "recovered yet (the native runtime cannot continue past it)")

    def _render_with_hud():
        frame = _render_frame(cell["game"], cell["starfield"], cell["sprite_ctx"],
                              tile_base=_tile_base())
        frame[:, PANEL_LEFT_PX:] = _hud_panel_indices()
        return frame

    skeleton = GameplayFrameSkeleton(
        render=_render_with_hud,
        advance=_advance,
    )

    gap: str | None = None
    running = True
    last_frame = _render_with_hud()
    try:
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                    running = False
            if cell["game_over"] is not None:
                # The 98EB hold: the frozen playfield + the THEND banner, then the title flow.
                frame = _render_with_hud()
                frame[_GAME_OVER_BANNER_Y:_GAME_OVER_BANNER_Y + _banner_rows,
                      :_banner_idx.shape[1]] = _banner_idx
                last_frame = frame
                display.set_title("OVERKILL - native (VM-less)  GAME OVER")
                cell["game_over"] -= 1
                if cell["game_over"] <= 0:
                    # the 96E0 flow: title -> level select -> a fresh session on the pick
                    if not _run_title_screen(display, pygame, container_data):
                        running = False
                    else:
                        picked = _run_level_select(display, pygame, container_data, walk_image,
                                                   start_beda=cell["level"])
                        if picked is None:
                            running = False
                        else:
                            lvl, diff = picked
                            _restart_session(lvl)
                            walk_image.ww(0x25CC, 0xBEDC, diff)
            elif gap is None:
                try:
                    last_frame = skeleton.tick()
                except Exception as exc:  # noqa: BLE001 -- a real unrecovered gap, report + hold
                    gap = f"{type(exc).__name__}: {exc}"
                    print(f"gameplay gap at tick {cell['tick']}: {gap}")
                g = cell["game"]
                display.set_title(f"OVERKILL - native (VM-less)  tick={cell['tick']}  "
                                  f"xy=({g.state.special_pool.x_word(0)},{g.state.special_pool.y_word(0)})")
            else:
                display.set_title(f"OVERKILL - native (VM-less)  HELD on gap: {gap[:70]}")
            display.draw(last_frame)
            clock.tick(args.fps)
    finally:
        display.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
