"""OVERKILL, native and VM-less: THE gate-verified frame function over the DGROUP image.

THE GAME IS ``overkill.native_frame.advance_gameplay_frame_97b2`` -- the one frame implementation
the demo-lockstep gate proves byte-exact against the original (8291/8292 frames of the L1 cold-start
demo, zero divergence, the whole 64K DGROUP compared).  The DGROUP image IS the game state (ADR-1);
this script owns NOTHING gameplay-shaped.

What this shell does, and it is all host boundary:
  * a window (pygame) and the Tandy palette blit;
  * the keyboard: the WHOLE host keyboard is written into the image's own INT9 key-state table
    (DS:98C4..), exactly as the IRQ writes it -- the game's 0162 poll then decodes DS:98BE through
    its OWN configurable control map (DS:213E/2146).  The shell never decides which keys mean what,
    and never synthesises the decoded word.  Default scheme: Q/A/O/P move, Space fires, Z (or TAB)
    applies a collected upgrade;
  * frame pacing, and the two host inputs the frame declares: ``isr_ticks`` (2 in steady state --
    the 0679 frame-wait's pair) and ``level_bytes`` (the LEV{n}MAP.BIC file C679 re-reads on death);
  * RENDERING, read back from the image: the tile window from the plane, the starfield plate from
    the DS:C6C1 ring, the sprite layer from the pools via ``project_state`` (a render projection,
    per ADR-1), and the HUD panel from the live state cells.  Every composer is byte-/pixel-gated
    against the VM (verify_native_frame_1to1, verify_native_hud_panel, verify_native_object_sprites).

DECLARED GAPS (fail loud, held visibly, never faked):
  * 98EB -- game over (out of lives): the front-end sequence is unrecovered;
  * 9734 -- level-complete -> next level (the A344 exit's continuation);
  * the real title-menu LOGIC (key redefine etc.): only the screen composes are recovered, so the
    title screen here is the real OKMENU image with a host "Space = start" wait, and the level
    select is the real LEVSCR/CHOOSE compose driven by the RECOVERED grid handlers.

An earlier version of this script kept a dataclass game (``NativeGame``) as the authority and
mirrored fragments into the image; that hybrid was inaccurate in exactly the ways the owner's
playtests kept finding (no thrusters, wrong fire origin, dead waves).  It was deleted, not
repaired -- see docs/overkill/deprecated_or_quarantined.md.

``--snapshot DIR`` starts from a captured memory image.  That image IS the state -- its planet,
difficulty, score, lives and scroll position all come from it -- so the title/level-select are
skipped entirely and nothing is written over it.  ``--level`` is ignored in that mode.

On a RecoveryGap (an unrecovered path reached during play) the app dumps a --snapshot-loadable image
of the pre-frame state to artifacts/gap_snapshots/, so the exact gap can be reproduced and filled.

Usage:
    python scripts/play_native.py [--level N] [--no-title] [--frames N] [--snapshot DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.native_frame import (  # noqa: E402
    advance_gameplay_frame_97b2, GameOverReached, TheEndReached,
)
from overkill.native_walk_frame import project_state  # noqa: E402
from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402
from overkill.recovered.domain.starfield import STAR_COUNT, Star, StarfieldState  # noqa: E402
from overkill.recovered.systems.tandy_screen import (  # noqa: E402
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TANDY_PALETTE_RGB,
)
from overkill.native_video.front_end import (TITLE_OPTIONS, apply_menu_selection_highlights,  # noqa: E402
                                              decode_fullscreen_image)
from overkill.native_video.object_sprites import (  # noqa: E402
    SpriteDrawContext,
    object_sprite_blocks_a846,
)

DEFAULT_BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
DEFAULT_CONTAINER = ROOT / "assets" / "OVERKILL"

_CS = 0x1010
_DS = 0x25CC
#: the three sprite-frame tables in the game code segment (bundle == every snapshot; constants)
_TABLE_75A6, _TABLE_768E, _TABLE_7746 = 0x9392, 0x9192, 0x8F92
_SPRITE_CELL_STRIDE_OFF = 0x1028   # ds:[1028] -- 75A6's +10-slot source advance is this >> 1

def _build_scan_map(pygame) -> dict:
    """Host key -> XT scancode, the FULL keyboard, shared with the VM viewer (scripts/sdl_view).

    THE SHELL MUST NOT DECIDE WHICH KEYS THE GAME READS.  OVERKILL's control map is CONFIGURABLE and
    lives in the image (``DS:213E``, or ``DS:2146`` when ``[0010] == 2``); ``0162`` packs those eight
    scancodes MSB-first and ORs in a fixed set.  In this corpus the map is
    ``[--, --, 2C(Z), 39(Space), 10(Q), 1E(A), 18(O), 19(P)]`` -- so Z is APPLY-UPGRADE (bit 0x20)
    and Q/A/O/P are the movement keys, none of which a fixed six-key list contains.

    An earlier version of this file wrote only ``FIXED_DIRECTION_KEYS``, so Z, Q, A, O and P were
    never written into the key table at all: the owner found Z dead and had to press TAB (the fixed
    alias for the same bit).  Writing the whole keyboard is both simpler and correct -- and it makes
    an in-game key REDEFINE work the day that screen lands, with no change here.
    """
    name_scan = {
        "escape": 0x01, "-": 0x0C, "=": 0x0D, "backspace": 0x0E, "tab": 0x0F,
        "[": 0x1A, "]": 0x1B, "return": 0x1C, "enter": 0x1C,
        "left ctrl": 0x1D, "right ctrl": 0x1D, ";": 0x27, "'": 0x28,
        "`": 0x29, "left shift": 0x2A, "\\": 0x2B, ",": 0x33, ".": 0x34,
        "/": 0x35, "right shift": 0x36, "left alt": 0x38, "right alt": 0x38,
        "space": 0x39, "caps lock": 0x3A,
        "up": 0x48, "down": 0x50, "left": 0x4B, "right": 0x4D,
    }
    for i, ch in enumerate("1234567890"):
        name_scan[ch] = 0x02 + i
    for i, ch in enumerate("qwertyuiop"):
        name_scan[ch] = 0x10 + i
    for i, ch in enumerate("asdfghjkl"):
        name_scan[ch] = 0x1E + i
    for i, ch in enumerate("zxcvbnm"):
        name_scan[ch] = 0x2C + i
    out = {}
    for name, code in name_scan.items():
        try:
            out[pygame.key.key_code(name)] = code
        except (ValueError, AttributeError):
            continue        # name unknown to this SDL build
    return out


def _pressed_scancodes(pygame, keys, scan_map) -> set[int]:
    """Every host key currently down, as XT scancodes.  The game decides what they mean."""
    return {sc for key, sc in scan_map.items() if keys[key]}


def make_level_assets(container_data: bytes, bundle_data: bytes):
    """A planet -> LevelAssets loader: the files 0B3E / 0E9C read with INT 21h.

    A HOST INPUT, supplied from the container exactly as the lockstep gate supplies it.  The frame
    reads it on a death re-init, a game-over and a level advance -- it never emulates DOS."""
    from overkill.asset_codecs.level_assets import (decode_level_blocks, decode_level_graphics,
                                                    decode_level_tile_map)
    from overkill.asset_codecs.native_level import (_read_class_override_pairs,
                                                    build_level_class_table)
    from overkill.native_frame import LevelAssets

    cache: dict = {}

    def loader(planet: int) -> LevelAssets:
        if planet not in cache:
            cache[planet] = LevelAssets(
                map_bytes=bytes(decode_level_tile_map(container_data, planet)),
                class_table=bytes(build_level_class_table(
                    _read_class_override_pairs(bundle_data, planet))),
                blocks=bytes(decode_level_blocks(container_data, planet)),
                graphics=bytes(decode_level_graphics(container_data, planet)),
            )
        return cache[planet]

    return loader


def read_starfield(img) -> StarfieldState:
    """The DS:C6C1 star ring + layer counters, read straight from the image.

    The frame function ticks this ring natively (the far 1F8F:0922, lockstep-verified), so the
    render side only ever READS it -- there is no separate starfield simulation."""
    stars = tuple(
        Star(img.rw(_DS, (0xC6C1 + i * 6) & 0xFFFF),
             img.rw(_DS, (0xC6C3 + i * 6) & 0xFFFF),
             img.rw(_DS, (0xC6C5 + i * 6) & 0xFFFF))
        for i in range(STAR_COUNT)
    )
    counters = (img.rw(_DS, 0xC812), img.rw(_DS, 0xC814), img.rw(_DS, 0xC816))
    return StarfieldState(stars, counters, img.rw(_DS, 0xA95A) != 0xFFFF)


def build_sprite_context(bundle_data: bytes, container_data: bytes, img) -> SpriteDrawContext:
    """The VM-free object->sprite draw context, from the image + the container.

    The level sprite bank is read from the image's own CS:[959A] segment (the level load put the
    decoded LEV{n}BLX there, byte-equal to the VM's runtime bank); the four shared banks decode from
    the container; the frame tables are CS constants from the bundle.  This is exactly the input
    ``object_sprite_blocks_a846`` maps each slot through, proven byte-exact vs the VM's 7596
    dispatch by ``verify_native_object_sprites``."""
    from overkill.asset_codecs.shared_assets import load_shared_startup_assets

    shared = load_shared_startup_assets(container_data)

    def cs_word(off: int) -> int:
        p = (_CS * 16 + (off & 0xFFFF)) & 0xFFFFF
        return bundle_data[p] | (bundle_data[(p + 1) & 0xFFFFF] << 8)

    # the level SPRITE bank is G{n}.BIC at CS:[95AE] -- NOT the tile-block bank at CS:[959A].
    # 0E9C loads both; object_sprite_blocks_a846 indexes the sprite one.
    bank_seg = img.rw(_CS, 0x95AE)
    level_bank = bytes(img.data[bank_seg * 16: bank_seg * 16 + 0x10000])
    return SpriteDrawContext(
        common_bank=shared["MANEXPL.BIC"],
        level_bank=level_bank,
        wide_bank=shared["2X2.BIC"],
        wide_bank_hi=shared["2X2C.BIC"],
        compact_bank=shared["1X1.BIC"],
        table_75a6=[cs_word(_TABLE_75A6 + 2 * k) for k in range(0x400)],
        table_768e=[cs_word(_TABLE_768E + 2 * k) for k in range(0x100)],
        table_7746=[cs_word(_TABLE_7746 + 2 * k) for k in range(0x100)],
        half_stride=img.rw(_DS, _SPRITE_CELL_STRIDE_OFF) >> 1,
    )


class ImageRenderer:
    """Compose the full screen from the IMAGE alone (plus static assets): tiles, stars, sprites, HUD.

    Every layer is a read-back of state the lockstep gate compares, through composers that are
    themselves gated against the VM's real pages.  Nothing here advances anything."""

    def __init__(self, bundle_data: bytes, container_data: bytes, img) -> None:
        import numpy as np

        from overkill.native_video.hud_panel import PANEL_LEFT_PX, panel_indices_from_page
        from overkill.recovered.adapters.hud_panel_state import (
            compose_hud_panel_from_image, read_hud_dir_table, read_hud_font,
        )

        self._np = np
        self._img = img
        self._ctx = build_sprite_context(bundle_data, container_data, img)
        self._panel_left = PANEL_LEFT_PX
        self._panel_indices_from_page = panel_indices_from_page
        from overkill.asset_codecs.container import load_container_asset
        from overkill.asset_codecs.planar import deplanarize_tandy

        # PANEL.ENC natively decoded -- proven byte-equal to the VM's decoded panel segment
        # (CS:[95B4]); verify_native_hud_panel gates the whole composer on it.
        panel_source = np.frombuffer(
            deplanarize_tandy(load_container_asset(container_data, "PANEL.ENC"),
                              sprite_mode=False, emit_item_headers=True), dtype=np.uint8)
        self._compose_hud = compose_hud_panel_from_image
        self._hud_ctx = {"panel_source": panel_source,
                         "dir_table": read_hud_dir_table(img), "font": read_hud_font(img)}
        self._tile_table = [img.rw(_CS, (0x8D92 + 2 * k) & 0xFFFF) for k in range(0x100)]

    def _tile_base(self):
        from overkill.native_video.tile_row import BANK2_ROW_BASE, compose_tile_window

        img, np = self._img, self._np
        row_base = img.rw(_DS, 0x2350)
        buf = np.frombuffer(img.data, dtype=np.uint8)
        plane = buf[img.rw(_CS, 0x9592) * 16: img.rw(_CS, 0x9592) * 16 + 0x10000]
        bank_ptr = 0x959C if row_base >= BANK2_ROW_BASE else 0x959A
        bank = buf[img.rw(_CS, bank_ptr) * 16: img.rw(_CS, bank_ptr) * 16 + 0x10000]
        tiles = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH), dtype=np.uint8)
        compose_tile_window(tiles, plane, row_base, self._tile_table, bank,
                            phase_234e=img.rw(_DS, 0x234E))
        return tiles

    def frame(self, *, stars: bool = True):
        """One composed (200, 320) indexed frame: terrain -> stars in unlit pixels -> sprites -> HUD.

        ``stars=False`` starts from a black playfield (no starfield) -- the level-start unsqueeze blits
        the static page, which has no per-frame starfield yet, so the transition shows no stars."""
        from overkill.native_video.frame import SnapshotSprite
        from overkill.native_video.playfield import compose_playfield_indices
        from overkill.native_video.starfield_plate import render_starfield_plate

        img, np = self._img, self._np
        row_source = img.rw(_DS, 0x234C)
        plate = (render_starfield_plate(read_starfield(img), row_source) if stars
                 else np.zeros((200, 320), dtype=np.uint8))
        tiles = self._tile_base()
        plate = np.where(tiles > 0, tiles, plate)
        state = project_state(img)     # ADR-1: a render projection of the image's pools
        blocks = object_sprite_blocks_a846(state.special_pool, state.effect_pool,
                                           state.object_pool, self._ctx)
        if blocks:
            sprite = SnapshotSprite(identity=0, sprite_id=0, anim_phase=0, screen_di=0,
                                    blocks=tuple(blocks))
            plate = compose_playfield_indices(plate, [sprite], row_source)
        plate[:, self._panel_left:] = self._panel_indices_from_page(
            self._compose_hud(img, **self._hud_ctx))
        return plate


#: the high-score TABLE layout (index space), drawn with the game's own DS:1816 glyph font.
_HISCORE_TABLE_XY = (0x2C, 0x10)         # (sy, sx): under the "High Scores" title, left column
_HISCORE_TABLE_COLOR = 0x0E             # yellow, matching the title
_HISCORE_ROW_H = 0x0E                    # px per table row
_HISCORE_NAME_MAX = 10


def _run_highscore_entry(display, pygame, container_data, img) -> "str | None":
    """The game-over HIGH-SCORE screen (``532D`` -> ``5497``): the real table + interactive NAME ENTRY.

    The original reads the name through **DOS ``INT 21h AH=07``** (console STDIN) -- an input path
    neither the VM-less frame nor the scancode key table feeds, which is why the screen ignored every
    key and the game hung there.  play_native owns it: it reads the 8-entry table at ``DS:21D8``,
    finds the player's rank from their score (``DS:2314``), and draws the whole table with the player's
    new entry inserted at its rank -- the name typed live (letters, Backspace) in the game's own
    recovered glyph font (the ``3153`` index-space path).  Enter accepts, Esc quits.  Returns the name,
    or None to quit.  (If the score does not make the table, the table is shown and Enter/Esc dismiss.)"""
    import numpy as np

    from overkill.native_video.highscore import (
        PLAYER_SCORE_CELL, compose_table, player_rank, read_table,
    )
    from overkill.native_video.hud_glyph import read_glyph_font

    mem = np.frombuffer(img.data, dtype=np.uint8)
    bg = decode_fullscreen_image(container_data, "HISCORE.ENC")
    font = read_glyph_font(mem, _DS)
    table = read_table(mem, _DS)
    player_score = bytes(mem[_DS * 16 + PLAYER_SCORE_CELL:_DS * 16 + PLAYER_SCORE_CELL + 4])
    rank = player_rank(table, player_score)
    made_table = rank < len(table)
    clock = pygame.time.Clock()
    display.set_title("OVERKILL - GAME OVER / HIGH SCORE  "
                      + ("[type your name, Enter = accept, Esc = quit]" if made_table
                         else "[Enter / Esc to continue]"))
    name = ""
    blink = 0
    sy, sx = _HISCORE_TABLE_XY
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return None
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):     # 5497: al==0Dh -> accept
                    return name
                if not made_table:
                    continue
                if ev.key == pygame.K_BACKSPACE:                       # 5497: al==08h -> delete
                    name = name[:-1]
                elif ev.unicode and ev.unicode.isprintable() and len(name) < _HISCORE_NAME_MAX:
                    name += ev.unicode.upper()
        frame = compose_table(bg, font, table, sy=sy, sx=sx, color=_HISCORE_TABLE_COLOR,
                              row_h=_HISCORE_ROW_H,
                              editing_rank=rank if made_table else None,
                              editing_name=name, editing_score=player_score,
                              caret=(blink // 15) % 2 == 0)
        display.draw(frame)
        blink += 1
        clock.tick(30)


def _run_game_over(display, pygame, bundle_data, container_data, img, speaker) -> "int | None":
    """Game-over screen chain: the high-score NAME ENTRY, then restart.  Returns the level pick for
    the 98EB restart (0 -> level 1), or None to quit."""
    if _run_highscore_entry(display, pygame, container_data, img) is None:
        return None
    return 0        # the fresh game restarts at level 1 (98EB does [2356] = pick + 1)


def _run_hiscore_screen(display, pygame, container_data, seconds: float) -> "bool | None":
    """Show HISCORE.ENC (natively decoded) for `seconds`.  Returns True on Space (start), False on
    quit, None on timeout (advance the attract cycle)."""
    img = decode_fullscreen_image(container_data, "HISCORE.ENC")
    display.set_title("OVERKILL - native (VM-less)  [high scores -- Space = start]")
    clock = pygame.time.Clock()
    frames = int(seconds * 30)
    for _ in range(frames):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return False
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                return True
        display.draw(img)
        clock.tick(30)
    return None


#: The menu's INSTRUCTIONS screen (558B 'I' -> BE92): five IPAGE pages.  These are NOT a story intro
#: -- 1F8F:0980 pages through the descriptor at DS:BE92, whose entries are the DS:1323 filename
#: pointers IPAGE1..IPAGE5.ENC (D2B8 just loads + blits each ENC, no glyph renderer).  Each decodes to
#: a full-screen (200,320) page through the same native codec as the title screen.
_INSTRUCTIONS_PAGES = ("IPAGE1.ENC", "IPAGE2.ENC", "IPAGE3.ENC", "IPAGE4.ENC", "IPAGE5.ENC")


#: The menu's ORDERING screen (558B 'O' -> BEA0): ten OPAGE pages (this is shareware -- how to order
#: the full game).  These are NOT the victory ending; the win screen is WINSCR.ENC (see _run_the_end).
_ORDERING_PAGES = tuple(f"OPAGE{i}.ENC" for i in range(1, 11))


def _run_story_pages(display, pygame, container_data, names, label: str,
                     per_page_seconds: float = 8.0) -> bool:
    """Page through a sequence of full-screen ENC pages (the 1F8F:0980 viewer: each page is loaded +
    blitted by D2B8), each advanced by Space or a timeout.  Esc/quit exits.  Returns False on
    window-close (so the caller can exit), else True."""
    display.set_title(f"OVERKILL - native (VM-less)  [{label} -- Space = next page, Esc = back]")
    clock = pygame.time.Clock()
    for name in names:
        img = decode_fullscreen_image(container_data, name)
        for _ in range(int(per_page_seconds * 30)):
            advance = False
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    return False
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    return True
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                    advance = True
            if advance:
                break
            display.draw(img)
            clock.tick(30)
    return True


def _run_instructions(display, pygame, container_data, per_page_seconds: float = 8.0) -> bool:
    """The menu 'I' INSTRUCTIONS screen (IPAGE1..5)."""
    return _run_story_pages(display, pygame, container_data, _INSTRUCTIONS_PAGES, "instructions",
                            per_page_seconds)


def _run_ordering(display, pygame, container_data, per_page_seconds: float = 8.0) -> bool:
    """The menu 'O' ORDERING screen (OPAGE1..10 -- shareware order info, not the victory ending)."""
    return _run_story_pages(display, pygame, container_data, _ORDERING_PAGES, "ordering",
                            per_page_seconds)


#: THE END splash asset -- the full-screen win image 1010:9844 loads (name @ DS:1440, len 0x7D04)
#: and shows when the mothership (planet 0) is beaten, before the arcade loop restarts at planet 1.
_THE_END_PAGE = "winscr.enc"


def _run_the_end(display, pygame, container_data) -> bool:
    """Present THE END (``1010:9844``): show the full-screen ``WINSCR.ENC`` win image and wait for FIRE.

    The mothership-beaten splash of the original.  Space/fire (or Esc/quit) dismisses it; then the caller
    resumes the arcade loop at planet 1.  Returns False on window-close so the caller can exit."""
    img = decode_fullscreen_image(container_data, _THE_END_PAGE)
    display.set_title("OVERKILL - native (VM-less)  [THE END -- mothership destroyed! Space continues]")
    clock = pygame.time.Clock()
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE, pygame.K_RETURN,
                                                        pygame.K_ESCAPE):
                return True
        display.draw(img)
        clock.tick(30)


def _replay_demo(display, pygame, bundle_data, container_data, demo_dir: Path,
                 seconds: float) -> "bool | None":
    """The ATTRACT DEMO: replay a recorded gameplay demo through the SAME verified frame + renderer.

    Seeds the image from the demo's own frame-0 snapshot, then each frame writes the demo's recorded
    INT9 scancodes into the image's key table and runs advance_gameplay_frame_97b2 -- so what plays is
    the byte-exact native frame driven by the original's recorded input.  (This is charter step 2's
    --demo replay, reused as the attract sequence's third element.)  Returns True on Space, False on
    quit, None on timeout / demo end / an unrecovered gap.
    """
    import json

    snap = demo_dir / "snapshot" / "memory_1mb.bin"
    if not snap.is_file():
        return None
    img = MutFlatMemory(snap.read_bytes())
    events = json.loads((demo_dir / "input_demo.json").read_text()).get("events", [])
    by_boundary: dict[int, list] = {}
    for e in events:
        if e.get("kind") == "scan":
            by_boundary.setdefault(int(e["boundary"]), []).append(int(e["value"]))
    planet = img.rw(_DS, 0x2356)
    renderer = ImageRenderer(bundle_data, container_data, img)
    level_assets = make_level_assets(container_data, bundle_data)
    display.set_title("OVERKILL - native (VM-less)  [attract demo -- Space = start]")
    clock = pygame.time.Clock()
    from overkill.recovered.domain.gaps import RecoveryGap
    for f in range(int(seconds * 30)):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return False
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                return True
        for sc in by_boundary.get(f, ()):        # make/break codes -> the INT9 table
            img.wb(_DS, (0x98C4 + (sc & 0x7F)) & 0xFFFF, 0 if (sc & 0x80) else 1)
        try:
            advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets, menu_pick=0)
        except RecoveryGap:
            return None                          # the demo reached an unrecovered edge -- next scene
        display.draw(renderer.frame())
        clock.tick(30)
    return None


#: the menu's state cells the original's 558B dispatch writes (see docs/overkill/campaigns/frontend.md):
_MENU_CONTROL_CELL = 0x0010     # [0010]: control method -- K -> 0 (keyboard), J -> 1, A -> 2 (amstrad)
_MENU_SOUND_MODE_CELL = 0x22B5  # [22B5]: sound mode 0..3 (Music/fx/both/none), M cycles it (inc & 3)
#: 558B idles ~750 of its own ticks before rolling the attract; ~10 s at the app's 30 fps.
_MENU_ATTRACT_IDLE_FRAMES = 300


#: 558B 'r' REDEFINE KEYS -- the six remappable actions in the original's capture order (5732: the
#: prompts si=0x50..0x55 store into di=2142,2143,2144,2145,2141,2140), with the control-map cell each
#: writes.  The map is DS:213E..2145; 0162 packs it MSB-first (Q/A/O/P movement, Space fire, Z special
#: -- see overkill.recovered.systems.input.DEFAULT_CONTROL_MAP).
_REDEFINE_SLOTS = (("UP", 0x2142), ("DOWN", 0x2143), ("LEFT", 0x2144),
                   ("RIGHT", 0x2145), ("FIRE", 0x2141), ("SPECIAL (apply upgrade)", 0x2140))


def _draw_menu_text_overlay(display, pygame, base_frame, lines, anchor: str = "center") -> None:
    """Draw ``base_frame`` (the title) then blit centered text ``lines`` (``(text, rgb)``) over it.
    ``anchor`` = "center" (default) or "bottom" (a settings row that doesn't cover the menu art)."""
    display.draw(base_frame)
    font = pygame.font.SysFont("monospace", 18, bold=True)
    w, h = display.screen.get_width(), display.screen.get_height()
    y = (h - int(h * 0.16)) if anchor == "bottom" else (h // 2 - len(lines) * 18)
    for text, color in lines:
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(w // 2, y))
        display.screen.fill((0, 0, 0), rect.inflate(16, 8))     # a readable backdrop
        display.screen.blit(surf, rect)
        y += 30
    pygame.display.flip()


def _run_redefine_keys(display, pygame, container_data, scan_map) -> "dict | bool | None":
    """558B 'r' -- REDEFINE KEYS.  Capture a new key for each of the six game actions and return
    ``{cell_offset: scancode}`` for DS:[2140-2145].  The original shows the BEC4 controls page through
    ``1F8F:0980`` and captures via ``5797`` (skipping F9/F10/Esc, beeping on each); here we prompt over
    the title and map each host key to its XT scancode via ``scan_map`` (a key absent from the XT map is
    skipped, mirroring the original's ignore-list).  Returns the map on success, ``None`` on Esc-cancel
    (keep the current bindings), or ``False`` on window-close."""
    title = decode_fullscreen_image(container_data, TITLE_OPTIONS)
    clock = pygame.time.Clock()
    result: dict = {}
    for label, cell in _REDEFINE_SLOTS:
        _draw_menu_text_overlay(display, pygame, title, [
            ("REDEFINE KEYS", (255, 220, 0)),
            (f"press a key for  {label}", (255, 255, 255)),
            ("(Esc cancels)", (150, 150, 150)),
        ])
        captured = None
        while captured is None:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    return False
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        return None                       # cancel -> keep the current map
                    sc = scan_map.get(ev.key)
                    if sc is not None:                    # ignore keys with no XT scancode
                        captured = sc
            clock.tick(60)
        result[cell] = captured
    return result


def _run_boss_key(display, pygame, bundle_data) -> bool:
    """F9 BOSS KEY (``1010:075F``): paint the fake "SNAFU V4.2" file-manager decoy screen (read straight
    from the image's text segment) and freeze until any key -- the original's hide-the-game panic
    button.  Returns ``False`` on window-close, ``True`` to resume."""
    from overkill.native_video.boss_key import read_boss_screen, cell_colors, COLS, ROWS
    cells = read_boss_screen(bundle_data)
    screen = display.screen
    w, h = screen.get_size()
    cw, chh = max(1, w // COLS), max(1, h // ROWS)
    font = pygame.font.SysFont("monospace", chh)
    screen.fill((0, 0, 0))
    for i, (ch, attr) in enumerate(cells):
        fg, bg = cell_colors(attr)
        r, c = divmod(i, COLS)
        x, y = c * cw, r * chh
        if bg != (0, 0, 0):
            screen.fill(bg, (x, y, cw, chh))
        if ch not in (0, 32):
            screen.blit(font.render(bytes([ch]).decode("cp437", errors="replace"), True, fg, bg), (x, y))
    pygame.display.flip()
    clock = pygame.time.Clock()
    while True:                              # 075F waits for a keypress before restoring
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN:
                return True
        clock.tick(30)


def _run_title_menu(display, pygame, bundle_data, container_data,
                    scan_map, music=None) -> "tuple[int, int, dict] | None":
    """The faithful cold-start MENU -- the original's ``1010:558B`` option dispatch over ``OKMENU.ENC``.

    Recovered from 558B: **M** cycles the sound mode (``[22B5]`` inc & 3 -- Music/fx/both/none),
    **K/A** pick the control method (``[0010]`` = 0 keyboard / 2 amstrad -- both are keyboard maps
    0162 decodes, 213E vs the alternate 2146), an idle timeout rolls the **attract** (high scores +
    a byte-exact gameplay demo, the "demo after intro"), and **FIRE/Space** starts.  Returns
    ``(sound_mode, control)`` to start, or ``None`` to quit.

    **J** (joystick, ``[0010] == 1``) is offered by the original but play_native is keyboard-only and
    0162 fail-louds on that mode, so J is declined here rather than starting an unplayable session.
    558B's **I**/**O** instructions/ordering screens render text through the far renderer
    ``1F8F:0980``, which is not recovered yet, so they are omitted rather than faked -- see
    docs/overkill/campaigns/frontend.md.
    """
    title = decode_fullscreen_image(container_data, TITLE_OPTIONS)
    clock = pygame.time.Clock()
    sound_mode, control = 2, 0        # the boot defaults the VM shows highlighted: keyboard + both
    composed = apply_menu_selection_highlights(title, control=control, sound_mode=sound_mode)
    key_overrides: dict = {}          # 'r' REDEFINE KEYS: control-map cell -> scancode
    idle = 0
    display.set_title("OVERKILL - native (VM-less)  "
                      "[menu -- M sound, K/A control, R redefine, Space = start, Esc = quit]")
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return None
            if ev.type == pygame.KEYDOWN:
                idle = 0
                if ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                    return sound_mode, control, key_overrides
                if ev.key == pygame.K_m:                       # 56E1: inc [22B5] ; and 3
                    sound_mode = (sound_mode + 1) & 3
                    composed = apply_menu_selection_highlights(title, control=control,
                                                               sound_mode=sound_mode)
                elif ev.key == pygame.K_k:                     # 563D: [0010] = 0 (keyboard, map 213E)
                    control = 0
                    composed = apply_menu_selection_highlights(title, control=control,
                                                               sound_mode=sound_mode)
                elif ev.key == pygame.K_a:                     # 56B2: [0010] = 2 (amstrad, map 2146)
                    control = 2
                    composed = apply_menu_selection_highlights(title, control=control,
                                                               sound_mode=sound_mode)
                elif ev.key == pygame.K_F9:                    # 075F: the boss key (also polled here)
                    if not _run_boss_key(display, pygame, bundle_data):
                        return None
                elif ev.key == pygame.K_r:                     # 5732: R -> redefine the six game keys
                    ov = _run_redefine_keys(display, pygame, container_data, scan_map)
                    if ov is False:
                        return None                            # window-close during capture
                    if ov:                                     # None = Esc-cancel (keep current map)
                        key_overrides.update(ov)
                        control = 0                            # 578E: R forces keyboard mode ([0010]=0)
                        composed = apply_menu_selection_highlights(title, control=control,
                                                                   sound_mode=sound_mode)
                elif ev.key == pygame.K_i:                     # 55C4: I -> BE92, the INSTRUCTIONS pages
                    if not _run_instructions(display, pygame, container_data):
                        return None
                elif ev.key == pygame.K_o:                     # 55BD: O -> BEA0, the ORDERING pages
                    if not _run_ordering(display, pygame, container_data):
                        return None
                # J (joystick, [0010]==1) is declined: play_native is keyboard-only (0162 fail-louds)
        idle += 1
        if idle >= _MENU_ATTRACT_IDLE_FRAMES:                  # 558B idle timeout -> the attract (5604)
            r = _run_native_attract(display, pygame, bundle_data, container_data, music)
            if r is False:
                return None
            if r is True:
                return sound_mode, control, key_overrides
            idle = 0
        # the VM's own selection-highlight mechanism (measured: the selected words' white text
        # recolors 15->12, byte-exact 276/276 for the boot default) -- see native_video.front_end.
        display.draw(composed)
        if music is not None:
            music.pump()                                       # the menu tune (page 2) plays here
        clock.tick(30)


#: the FIRE scancode (space) the attract's auto-fire injects into the image's INT9 key table.
_ATTRACT_FIRE_SCANCODE = 0x39


def _run_blueprint_intro(display, pygame, bundle_data, container_data,
                         max_frames: int = 300) -> bool:
    """The cold-boot BLUEPRINT / intro screen -- the REAL first screen the original shows (NOT OKMENU).

    `1010:CE97` composes the grid background and the boot overlays the ship-schematic + briefing-text
    cells, all from the BLUEBITS bank (`native_video.blueprint.compose_blueprint`, grounded against the
    VM).  Held until FIRE/Space/any-key (or `max_frames` at 30fps).  Returns False on window-close/Esc."""
    from overkill.native_video.blueprint import compose_blueprint

    img = build_cold_level_start_image(bundle_data, 0, container_data)
    frame = compose_blueprint(img)
    clock = pygame.time.Clock()
    display.set_title("OVERKILL - native (VM-less)  [intro -- Space/any key to continue]")
    for _ in range(max_frames):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return False
            if ev.type == pygame.KEYDOWN:
                return True                       # any key advances to the menu/attract
        display.draw(frame)
        clock.tick(30)
    return True


def _run_native_attract(display, pygame, bundle_data, container_data, music=None) -> "bool | None":
    """The cold-boot ATTRACT (1010:D007), driven by the recovered scene machine -- the game plays
    ITSELF.  `NativeAttract` sequences the scenes; each frame the caller runs the recovered action:
    scene 0 the D160 scroll-in setup, scenes 1..7 draw the scene cell over the live frame, scenes >= 8
    run the native frame with the scripted auto-fire.  Returns True on Space (start a game), False on
    quit, None when the attract ends (back to the menu)."""
    from overkill.native_attract import NativeAttract
    from overkill.native_frame import attract_scene0_setup_d160
    from overkill.native_video.attract import compose_scene

    img = build_cold_level_start_image(bundle_data, 0, container_data)
    renderer = ImageRenderer(bundle_data, container_data, img)
    level_assets = make_level_assets(container_data, bundle_data)
    driver = NativeAttract.start()
    setup_done = False
    clock = pygame.time.Clock()
    display.set_title("OVERKILL - native (VM-less)  [attract -- Space = start, Esc = quit]")
    while True:
        fire = anykey = False
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN:
                anykey = True
                if ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                    fire = True
                elif ev.key == pygame.K_ESCAPE:
                    return None
        driver, action = driver.step(fire_pressed=fire, any_key=anykey, setup_done=setup_done)
        setup_done = False
        if action.kind == "exit":
            return True if fire else None
        try:
            if action.kind == "scene0_setup":
                setup_done = attract_scene0_setup_d160(img)          # the D160 scroll-in
                frame = renderer.frame()
            elif action.kind == "gameplay":                          # scenes >= 8: the game plays itself
                img.wb(_DS, (0x98C4 + _ATTRACT_FIRE_SCANCODE) & 0xFFFF, 1 if action.injected_fire else 0)
                advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets, menu_pick=0)
                frame = renderer.frame()
            else:                                                    # draw_cell (scenes 1..7)
                advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets, menu_pick=0)
                frame = compose_scene(renderer.frame(), img, action.scene)
        except RecoveryGap:
            return None                                              # an unrecovered attract edge -> menu
        display.draw(frame)
        if music is not None:
            music.pump()                                            # keep the tune playing in the attract
        clock.tick(30)


def _run_screen_squeeze(display, pygame, frame, *, opening: bool) -> bool:
    """Play the original's vertical screen SQUEEZE (1010:5C46 opening / 5960 closing): the ``(200,320)``
    index ``frame`` scaled from a thin centre band to full height (opening) or full to a band (closing),
    stepped at the retrace cadence.  Returns False on window-close."""
    from overkill.native_video.transition import squeeze_heights, vertical_squeeze_frame

    clock = pygame.time.Clock()
    for h in squeeze_heights(opening=opening):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
        display.draw(vertical_squeeze_frame(frame, h))
        clock.tick(60)                    # 5C46 steps [5901] += 2 per retrace (~60 Hz)
    return True


def _run_level_start_plaque(display, pygame, container_data, img, renderer, level_index: int,
                            speaker=None) -> bool:
    """The level-start MISSION PLAQUE (``1010:D305``/``D367``): the ``plaq{level}.enc`` briefing cell
    overlaid on the level's initial screen (animated starfield + HUD), held until FIRE -- what the
    original shows between level-select and the first gameplay frame.  Space/fire starts the level;
    Esc/quit aborts (returns False so the caller exits).

    The background animates exactly as D305's wait does: it ticks the starfield (0922) + star list
    (4CED) + clock (5F61) each frame, AND runs the REFUEL -- the 77C5 energy-bar charge (``[A97A]``
    0 -> 0x58, one step per frame while ``[A97C] == 1``, with the queued sound played through the ISR
    effects), which is the fuel indicator rising on the HUD that the original shows here.  The
    cold-start image hands over with the bar already full (``[A97A] = 0x58``); to replay the animation
    we reset it to empty + re-arm the charge (exactly C4DB's ``[A97A] = 0`` + the A47C-script arm that
    sets ``[A97C] = 1`` and queues sound 0x0D), then let 77C5 fill it.  Gameplay continues from the
    advanced state (no lockstep involved -- this is the front-end interlude); if fire is pressed before
    the bar is full, the frame's own 77C5 finishes it in-game."""
    from overkill.native_frame import (
        _clock_tick_5f61, _isr_effects_ticks, _shield_charge_77c5, _star_list_4ced,
        _starfield_tick_0922,
    )
    from overkill.native_video.plaque import compose_plaque, decode_plaque_cell

    plaque = decode_plaque_cell(container_data, level_index)
    img.ww(_DS, 0xA97A, 0x0000)      # C4DB/C495: the bar starts EMPTY
    img.ww(_DS, 0xA97C, 0x0001)      # 9DD0: the charge is armed (77C5 will fill it)
    # 5C46: the level screen UNSQUEEZES in (a thin centre band -> full) before the briefing.  The
    # blitted page has no per-frame starfield yet, so the transition shows NO stars (stars=False).
    if not _run_screen_squeeze(display, pygame, renderer.frame(stars=False), opening=True):
        return False
    img.wb(_DS, 0xBEFF, 0x04)        # 9755: the level-start JINGLE plays right after the unsqueeze
    display.set_title("OVERKILL - native (VM-less)  [mission briefing -- Space = launch, Esc = quit]")
    clock = pygame.time.Clock()
    frame_n = 0
    refuel_started = False
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return False
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                return True
        _star_list_4ced(img)
        _starfield_tick_0922(img)
        # once the jingle has played, the refuel glissando (0x0D, 9DB9) sounds as the bar fills
        if not refuel_started and frame_n >= 40 and img.rw(_DS, 0xA97A) < 0x58:
            img.wb(_DS, 0xBEFF, 0x0D)
            refuel_started = True
        _shield_charge_77c5(img)     # 77C5: the fuel/energy bar refuel (A97A 0 -> 0x58, 0x0C at full)
        _clock_tick_5f61(img)
        _isr_effects_ticks(img, 2)   # advance the sound engine on the queued sounds
        if speaker is not None:
            speaker.update(img)      # play them to the host (jingle, then the refuel, as the bar fills)
        display.draw(compose_plaque(renderer.frame(), plaque))
        clock.tick(30)
        frame_n += 1


def _run_level_select(display, pygame, container_data, image, start_beda: int = 0):
    """The REAL level-select screen: LEVSCR/CHOOSE composes + the RECOVERED grid handlers
    (D476/D480/D488/D490) and the D424 fire resolve.  Returns ``(level_index, difficulty)`` or
    None on quit.  The screen LOOP (D3F0's own wait/present) is host here."""
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
    display.set_title("OVERKILL - native (VM-less)  [level select -- arrows, Space, Esc]")
    clock = pygame.time.Clock()
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
                bedc = (bedc + 1) % 3
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                resolve_level_select_fire_d424(beda)
                return beda, bedc
        display.draw(compose_level_select(levscr, choose, level_xy, option_xy, beda, bedc))
        clock.tick(30)


#: the sound engine's live output, exactly as the ISR at D530..D563 selects it:
#:   [BFB3] (channel 0 status) != 0 -> program its period [BFB0];  else [BFC3] -> [BFC0];  else off.
#: freq = the PIT input clock / period.  A pure READ of the D50E engine's verified DGROUP state.
_PIT_HZ = 1193182.0
_SND_CH0_STATUS, _SND_CH0_PERIOD = 0xBFB3, 0xBFB0
_SND_CH1_STATUS, _SND_CH1_PERIOD = 0xBFC3, 0xBFC0


def read_speaker(img) -> "tuple[bool, float]":
    """(enabled, freq) for the host PC-speaker sink, derived from the image's sound-engine cells."""
    if img.rb(_DS, _SND_CH0_STATUS):
        period = img.rw(_DS, _SND_CH0_PERIOD)
    elif img.rb(_DS, _SND_CH1_STATUS):
        period = img.rw(_DS, _SND_CH1_PERIOD)
    else:
        return False, 0.0
    if period == 0:
        return False, 0.0
    return True, _PIT_HZ / period


class SpeakerSink:
    """Drive scripts/sdl_view.PcSpeakerAudio from the image each frame.  Silently no-ops if pygame
    audio is unavailable (headless, no device) -- audio is never allowed to break gameplay."""

    def __init__(self, pygame) -> None:
        self._speaker = None
        try:
            from sdl_view import PcSpeakerAudio
            self._speaker = PcSpeakerAudio(pygame)
        except Exception as exc:  # noqa: BLE001 -- headless / no audio device: run silent
            print(f"(audio disabled: {type(exc).__name__}: {exc})")

    def update(self, img) -> None:
        if self._speaker is None:
            return
        enabled, freq = read_speaker(img)
        self._speaker.set(enabled, freq)

    def close(self) -> None:
        if self._speaker is not None:
            self._speaker.close()


def _music_page_for(img) -> int:
    """The current music page = ``DS:[98C2]``, the song the native frame's ``1010:5F61``
    (``native_frame._clock_tick_5f61``) has ALREADY selected -- read it, do NOT recompute.

    5F61 re-selects the song ONLY on the gated A480 beat (``[A47E]==0`` and ``[A480]`` decrementing to
    0), then stamps ``[98C2]`` (CB1C's first store).  It IS where the per-planet table
    (``[0x231E + [2356]]``) and the ``[2350] >= 0x0750`` boss-page-6 override live -- but gated.  The
    old version here recomputed that override EVERY frame, so it forced the boss/end tune (page 6) the
    instant the world scroll passed 0x0750 -- e.g. mid-planet-1 -- even though the real 5F61 had not
    re-selected (A480 not on its beat) and ``[98C2]`` still held the planet song.  Following ``[98C2]``
    is the gated truth the driver's own CB1C would request."""
    return img.rb(_DS, 0x98C2)


class AdlibMusicSink:
    """Live OPL3 MUSIC from the recovered VM-free AdLib driver.  Each present-frame it ticks the
    segment-2032 ``AdlibDriver`` (``ticks_per_frame`` = the timer-ISR ticks the driver runs per frame)
    and synthesizes the emitted YM3812 register stream through Nuked-OPL3 into a pygame mixer channel --
    the native counterpart of dos_re's ``AdlibSpeakerSink``, driven by the port's own driver, no VM.
    Silently no-ops if the mixer or ``pynuked_opl3`` is unavailable (audio never breaks gameplay)."""

    def __init__(self, pygame, seg2032_image, *, present_hz: int, ticks_per_frame: int = 2) -> None:
        self._pygame = pygame
        self.available = False
        self._ticks = ticks_per_frame
        try:
            import numpy as np
            from overkill.native_audio.adlib import AdlibDriver
            from pynuked_opl3 import OPL3
        except Exception as exc:  # noqa: BLE001
            print(f"(music disabled: {type(exc).__name__}: {exc})")
            return
        self._np = np
        self.driver = AdlibDriver(seg2032_image)
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            except Exception as exc:  # noqa: BLE001 -- headless / no device
                print(f"(music disabled: no mixer: {exc})")
                return
        rate, _size, channels = pygame.mixer.get_init()
        self._rate, self._channels = int(rate), int(channels)
        self._present_hz = max(1, present_hz)
        # the driver's ISR tick rate: ticks/frame * frames/sec.  Music tempo + audio are advanced by
        # REAL elapsed time (below), so a slow frame (many enemies) catches up instead of dragging.
        self._isr_hz = self._present_hz * max(1, ticks_per_frame)
        self._last_ms = None
        self._tick_accum = 0.0
        self._samp_accum = 0.0
        self._chunk = max(256, self._rate // 20)         # ~50ms chunks: play+queue = ~100ms of slack
        self._lead = int(self._rate * 0.12)              # build ~120ms before starting playback
        self._buf = np.zeros((0, self._channels), dtype=np.int16)
        self._started = False
        if pygame.mixer.get_num_channels() < 3:
            pygame.mixer.set_num_channels(3)
        self._channel = pygame.mixer.Channel(2)          # ch 2: the PC-speaker sink keeps its own
        self._opl = OPL3(sample_rate=self._rate)
        self.available = True

    def request_page(self, page: int) -> None:
        """Queue a music-page (re)load -- the game->driver ``[0008]`` request the tune plays from."""
        if self.available:
            self._song = page & 0xFF
            self.driver.ram[0x0008] = page & 0xFF

    def set_song(self, page: int) -> None:
        """Switch music to ``page`` (the 5F61 per-level selection).  Unlike :meth:`request_page` this
        FORCES the page gate to pick it up by clearing the active-page latch ``[0009]`` -- the game
        changes songs by stopping first, so a mid-song request otherwise no-ops (0409 only reloads
        ``[0008]`` when ``[0009] == 0``).  A no-op when the song is already selected."""
        if not self.available or page == getattr(self, "_song", None):
            return
        self._song = page & 0xFF
        self.driver.ram[0x0009] = 0                  # clear the latch so 0409 reloads the new page
        self.driver.ram[0x0008] = page & 0xFF

    def pump(self) -> None:
        """Advance the driver + feed its audio to the mixer, paced by REAL elapsed time so the tempo and
        the audio stay real-time no matter how slow the frame rendered.  Call once per frame."""
        if not self.available:
            return
        np = self._np
        now = self._pygame.time.get_ticks()
        if self._last_ms is None:
            elapsed = 1000.0 / self._present_hz          # first frame: one nominal period
        else:
            elapsed = min(now - self._last_ms, 100)      # cap a catch-up burst (a long stall) at 100ms
        self._last_ms = now
        # tick the driver + generate samples proportional to elapsed wall-clock time (fractions carried)
        self._tick_accum += self._isr_hz * elapsed / 1000.0
        ticks = int(self._tick_accum); self._tick_accum -= ticks
        self._samp_accum += self._rate * elapsed / 1000.0
        nsamp = int(self._samp_accum); self._samp_accum -= nsamp
        for _ in range(ticks):
            self.driver.tick_2032_0063()
        for reg, val in self.driver.drain():
            self._opl.write(reg, val)
        if nsamp > 0:
            pcm = np.frombuffer(self._opl.generate_stereo(nsamp), dtype="<i2").reshape(-1, 2)
            out = pcm if self._channels > 1 else pcm[:, :1]
            self._buf = np.concatenate([self._buf, out])
        if not self._started:
            if len(self._buf) >= self._lead:
                self._channel.play(self._next_sound())
                self._started = True
            return
        if not self._channel.get_busy():
            self._started = False
            return
        if self._channel.get_queue() is None and len(self._buf) >= self._chunk:
            self._channel.queue(self._next_sound())

    def _next_sound(self):
        chunk, self._buf = self._buf[:self._chunk], self._buf[self._chunk:]
        arr = chunk if self._channels > 1 else chunk.reshape(-1)
        return self._pygame.sndarray.make_sound(self._np.ascontiguousarray(arr))

    def close(self) -> None:
        pass


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


def dump_gap_snapshot(pre_frame: bytes, img, exc: RecoveryGap, tick: int) -> Path:
    """On a RecoveryGap, write a ``--snapshot``-loadable image + gap metadata so the exact state that
    hit the gap can be reproduced and the gap filled.

    ``pre_frame`` is the image BEFORE the frame that raised (the host input already written into the
    INT9 table), so re-running one frame over it re-raises the same gap deterministically -- the seed
    a recovery probe drives.  Named by the gap address + planet + tick so repeated hits don't clobber
    each other."""
    import json
    import re

    msg = str(exc)
    # prefer an explicit CS:/1010: routine address; else the first bare 4-hex token the message names
    # (gap messages lead with the routine, e.g. "the 98EB game-over ...", "... CS:8463", "(1010:7BCB)")
    m = re.search(r"(?:CS:|1010:)([0-9A-Fa-f]{3,4})", msg) or re.search(r"\b([0-9A-Fa-f]{4})\b", msg)
    addr = m.group(1).upper() if m else "unknown"
    planet = img.rw(_DS, 0x2356)
    out = ROOT / "artifacts" / "gap_snapshots" / f"gap_{addr}_p{planet}_t{tick}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "memory_1mb.bin").write_bytes(pre_frame)
    (out / "gap_info.json").write_text(json.dumps({
        "gap": msg,
        "address": addr,
        "tick": tick,
        "planet": planet,
        "difficulty": img.rw(_DS, 0xBEDC),
        "lives": img.rw(_DS, 0x2358),
        "reproduce": "python scripts/play_native.py --snapshot "
                     f"artifacts/gap_snapshots/{out.name}",
    }, indent=2), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--level", type=int, default=0, help="0-based level to cold-load and play")
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE),
                    help="the static runtime bundle (memory_1mb.bin)")
    ap.add_argument("--container", default=str(DEFAULT_CONTAINER), help="the OVERKILL asset container")
    ap.add_argument("--snapshot", default=None,
                    help="start from a captured snapshot dir's memory_1mb.bin (it IS the state: its "
                         "own planet/difficulty/lives are used; the front end is skipped and "
                         "--level is ignored)")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--no-title", action="store_true", help="skip the title + level select")
    ap.add_argument("--no-intro", action="store_true",
                    help="(deprecated no-op: the IPAGE pages are the menu's INSTRUCTIONS, not an intro)")
    ap.add_argument("--frames", type=int, default=0,
                    help="headless self-test: run N gameplay frames then exit (SDL_VIDEODRIVER=dummy)")
    ap.add_argument("--no-sound", action="store_true", help="disable the PC-speaker + music audio")
    ap.add_argument("--music-page", type=int, default=2,
                    help="the AdLib music page to play (the game->driver [0008] request; 2 = the "
                         "gameplay tune observed in the demo corpus)")
    ap.add_argument("--demo", default=None,
                    help="replay a recorded demo through the verified frame + renderer, then exit "
                         "(charter step 2 -- the attract sequence's demo element, standalone)")
    ap.add_argument("--instructions", dest="instructions", action="store_true",
                    help="the menu 'I' INSTRUCTIONS screen (IPAGE1..5 story/help pages), then exit")
    ap.add_argument("--ordering", dest="ordering", action="store_true",
                    help="the menu 'O' ORDERING screen (OPAGE1..10, shareware order info), then exit")
    ap.add_argument("--ending", dest="ending", action="store_true",
                    help="THE END victory screen (WINSCR.ENC, shown when the mothership is beaten), then exit")
    ap.add_argument("--intro", dest="intro", action="store_true",
                    help="the cold-boot INTRO/ATTRACT sequence (there is no separate intro asset -- the "
                         "original's cold-boot intro IS the attract), then exit")
    args = ap.parse_args(argv)

    bundle_data = Path(args.bundle).read_bytes()
    container_data = Path(args.container).read_bytes()

    display = PygameDisplay(scale=args.scale)
    pygame = display.pygame
    scan_map = _build_scan_map(pygame)

    if args.instructions or args.ordering:
        run = _run_ordering if args.ordering else _run_instructions
        run(display, pygame, container_data)
        display.close()
        return 0

    if args.ending:                       # THE END (WINSCR.ENC) -- the victory screen, NOT the OPAGE ordering
        _run_the_end(display, pygame, container_data)
        display.close()
        return 0

    if args.intro:                        # the cold-boot INTRO == the attract (title + scenes + demo)
        music = None
        if not args.no_sound:
            music = AdlibMusicSink(pygame, bytearray(bundle_data[0x2032 * 16:0x2032 * 16 + 0x10000]),
                                   present_hz=args.fps)
            music.request_page(args.music_page)
        _run_native_attract(display, pygame, bundle_data, container_data, music)
        display.close()
        return 0

    if args.demo:
        demo_dir = ROOT / "artifacts" / "demos" / args.demo
        print(f"replaying demo {args.demo} through the verified frame (Space/Esc to stop)")
        _replay_demo(display, pygame, bundle_data, container_data, demo_dir, seconds=10_000.0)
        display.close()
        return 0

    # Live OPL3 MUSIC via the recovered VM-free AdLib driver -- created BEFORE the front end so the
    # MENU + ATTRACT play the tune too (the VM loads page 2 for the menu/attract AND planet-1 gameplay;
    # the boot/intro is silent, page 0).  The sink runs over its own copy of segment 2032, independent
    # of the game image, so one sink plays continuously across menu -> level select -> gameplay.
    music = None
    if not args.frames and not args.no_sound:
        music = AdlibMusicSink(pygame, bytearray(bundle_data[0x2032 * 16:0x2032 * 16 + 0x10000]),
                               present_hz=args.fps)
        music.request_page(args.music_page)     # the game->driver [0008] page request

    plaque_level: "int | None" = None    # the level whose mission plaque to show at start (cold play only)
    if args.snapshot:
        # A SNAPSHOT IS THE STATE.  It already carries its own planet (DS:2356), difficulty
        # (DS:BEDC), score, lives and scroll position -- so the front end must not run before it and
        # must not write over it.  Neither --level nor the level-select pick means anything here.
        img = MutFlatMemory((Path(args.snapshot) / "memory_1mb.bin").read_bytes())
        origin = f"snapshot {Path(args.snapshot).name}"
    else:
        level = args.level
        difficulty = 0
        menu_choice: "tuple[int, int, dict] | None" = None
        if not args.no_title and not args.frames:
            # The real cold boot opens on the BLUEPRINT/intro screen (CE97 grid + BLUEBITS ship
            # schematics + text), NOT OKMENU -- show it first, as the original does.
            if not _run_blueprint_intro(display, pygame, bundle_data, container_data):
                display.close()
                return 0
            menu_choice = _run_title_menu(display, pygame, bundle_data, container_data, scan_map, music)
            if menu_choice is None:
                display.close()
                return 0
            # 558B FIRE goes straight to the level-select (971A -> D390); the IPAGE story intro is NOT
            # on the start path (it never loads there -- confirmed by the cold-start asset trace), it is
            # part of the ATTRACT (menu idle), so play_native shows it there, not before level-select.
            probe_img = build_cold_level_start_image(bundle_data, level, container_data)
            picked = _run_level_select(display, pygame, container_data, probe_img, start_beda=level)
            if picked is None:
                display.close()
                return 0
            level, difficulty = picked
            plaque_level = level          # went through the front end -> show the mission plaque
        img = build_cold_level_start_image(bundle_data, level, container_data)
        img.ww(_DS, 0xBEDC, difficulty)   # the difficulty global (the C237 spawn throttle reads it)
        if menu_choice is not None:       # apply the 558B menu selections onto the game image
            img.ww(_DS, _MENU_SOUND_MODE_CELL, menu_choice[0])
            img.ww(_DS, _MENU_CONTROL_CELL, menu_choice[1])
            for cell, scancode in menu_choice[2].items():   # 'r' REDEFINE KEYS -> the control map
                img.wb(_DS, cell, scancode)
        origin = f"cold level {level + 1}"

    planet = img.rw(_DS, 0x2356)

    level_assets = make_level_assets(container_data, bundle_data)
    renderer = ImageRenderer(bundle_data, container_data, img)
    speaker = SpeakerSink(pygame) if not args.frames and not args.no_sound else None
    if plaque_level is not None:
        # 1010:D305/D367: the level-start "get ready" screen -- the mission briefing plaque over the
        # animated starfield + HUD, held until FIRE, exactly as the original shows between level-select
        # and the first gameplay frame.  The speaker plays the refuel sound as the fuel bar fills.
        if not _run_level_start_plaque(display, pygame, container_data, img, renderer, plaque_level,
                                       speaker):
            display.close()
            return 0
    clock = pygame.time.Clock()
    tick = 0          # gameplay frames advanced (frozen once HELD)
    drawn = 0         # display frames drawn (always advances -- the --frames self-test counts these)
    hold: str | None = None
    pre_frame = bytearray(len(img.data))   # reused each tick: the clean seed dumped on a gap
    running = True
    print(f"native: {origin} -- planet {planet}, difficulty {img.rw(_DS, 0xBEDC)}, "
          f"lives {img.rw(_DS, 0x2358)}, row {img.rw(_DS, 0x2350):#06x}; "
          "the gate-verified frame over the image -- no VM, no dataclass game")
    try:
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN
                                              and ev.key == pygame.K_ESCAPE):
                    running = False
                elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_F9:   # 075F: the boss key
                    if not _run_boss_key(display, pygame, bundle_data):
                        running = False

            if hold is None:
                # keyboard -> the image's own INT9 key table; 0162 decodes it inside the frame,
                # through the game's OWN (configurable) control map.  We write the raw keyboard.
                pressed = _pressed_scancodes(pygame, pygame.key.get_pressed(), scan_map)
                for sc in scan_map.values():
                    img.wb(_DS, (0x98C4 + sc) & 0xFFFF, 1 if sc in pressed else 0)
                # a clean seed of THIS frame's pre-state (input already applied) so a gap can be
                # reproduced by re-running one frame over it; reused each tick, no per-frame alloc.
                pre_frame[:] = img.data
                try:
                    # menu_pick=None makes out-of-lives raise GameOverReached instead of restarting
                    # silently, so the app can present the (real, input-driven) high-score entry +
                    # new-game level-select -- the frame reads DOS INT 21h for the name, which nothing
                    # feeds VM-less, so play_native owns that screen.  (--frames self-test auto-restarts.)
                    advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets,
                                                menu_pick=(0 if args.frames else None))
                except GameOverReached as over:
                    print(f"GAME OVER at tick {tick}: high-score entry, then restart")
                    pick = _run_game_over(display, pygame, bundle_data, container_data, img, speaker)
                    if pick is None:
                        running = False
                    else:
                        over.resume(pick)
                        plaque_level = pick
                        if not _run_level_start_plaque(display, pygame, container_data, img, renderer,
                                                       pick, speaker):
                            running = False
                    tick += 1
                    continue
                except TheEndReached as end:
                    # The mothership was beaten: present THE END (WINSCR.ENC), then -- on fire -- run
                    # the recovered 9744 continuation to load planet 1 and loop, exactly like the original.
                    print(f"THE END at tick {tick}: mothership destroyed -- showing WINSCR, then looping")
                    if not args.frames:
                        if not _run_the_end(display, pygame, container_data):
                            running = False
                    end.resume()
                    planet = img.rw(_DS, 0x2356)
                    print(f"  arcade loop -> planet {planet}, lives {img.rw(_DS, 0x2358)}")
                    tick += 1
                    continue
                except RecoveryGap as exc:
                    hold = f"{type(exc).__name__}: {exc}"
                    print(f"HELD at tick {tick}: {hold}")
                    if not args.frames:
                        snap = dump_gap_snapshot(bytes(pre_frame), img, exc, tick)
                        print(f"  gap snapshot written -> {snap}")
                        print(f"  reproduce: python scripts/play_native.py --snapshot "
                              f"artifacts/gap_snapshots/{snap.name}")
                tick += 1
                # The frame OWNS the three exits internally: it sets and consumes A344/A346 within the
                # same call (9B2E clears them at entry, the loop body re-raises the taken one, and the
                # 97CE/97E2 tail runs the recovered 9734 level-advance / 9908 death-respawn -> 98EB
                # game-over before returning).  So after a normal frame these flags are already 0; the
                # only thing the frame leaves for the caller is a RecoveryGap (the mothership's 9844
                # story intro), handled above.  A342 (game over reached as a *standalone* flag, i.e. NOT
                # via the death path) has no recovered continuation yet -- keep it as a fail-loud net so
                # play can never silently freeze on it rather than misreport it as a normal exit.
                if hold is None and img.rw(_DS, 0xA342) == 1:
                    hold = "standalone game-over flag (A342) with no recovered continuation"
                    print(f"HELD at tick {tick}: {hold}")

            frame = renderer.frame()
            if hold is None:
                display.set_title(f"OVERKILL - native (VM-less)  tick={tick}  "
                                  f"xy=({img.rw(_DS, 0x237E):#05x},{img.rw(_DS, 0x2380):#05x})  "
                                  f"lives={img.rw(_DS, 0x2358)}")
            else:
                display.set_title(f"OVERKILL - native (VM-less)  HELD: {hold[:70]}")
            if speaker is not None:
                speaker.update(img)
            if music is not None:
                if hold is None:
                    music.set_song(_music_page_for(img))   # 5F61: follow the per-level song selection
                music.pump()             # advance + play one frame of the VM-free AdLib music
            display.draw(frame)
            drawn += 1

            # count DRAWN frames, not gameplay ticks: a HELD frame stops advancing `tick`, and an
            # earlier version looped forever waiting for a counter that could never move.
            if args.frames and drawn >= args.frames:
                lit = int((frame > 0).sum())
                print(f"--frames self-test: {tick} gameplay frames, {drawn} drawn, "
                      f"last frame {lit} lit px, hold={hold!r}")
                running = False
            clock.tick(args.fps)
    finally:
        if speaker is not None:
            speaker.close()
        if music is not None:
            music.close()
        display.close()
    return 1 if (hold and args.frames) else 0   # a held gap is a self-test failure


if __name__ == "__main__":
    raise SystemExit(main())
