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

Usage:
    python scripts/play_native.py [--level N] [--no-title] [--frames N] [--snapshot DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.native_frame import advance_gameplay_frame_97b2  # noqa: E402
from overkill.native_walk_frame import project_state  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402
from overkill.recovered.domain.starfield import STAR_COUNT, Star, StarfieldState  # noqa: E402
from overkill.recovered.systems.tandy_screen import (  # noqa: E402
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TANDY_PALETTE_RGB,
)
from overkill.native_video.front_end import TITLE_OPTIONS, decode_fullscreen_image  # noqa: E402
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

    def frame(self):
        """One composed (200, 320) indexed frame: terrain -> stars in unlit pixels -> sprites -> HUD."""
        from overkill.native_video.frame import SnapshotSprite
        from overkill.native_video.playfield import compose_playfield_indices
        from overkill.native_video.starfield_plate import render_starfield_plate

        img, np = self._img, self._np
        row_source = img.rw(_DS, 0x234C)
        plate = render_starfield_plate(read_starfield(img), row_source)
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


def _run_attract(display, pygame, bundle_data, container_data) -> "bool | None":
    """The cold-boot ATTRACT loop: title -> high scores -> a gameplay demo, cycling on idle, until the
    player presses Space (start a game) or quits.  Mirrors the original's D007 attract sequence with
    the recovered screens + the byte-exact frame; the exact per-scene timings are host-side."""
    title = decode_fullscreen_image(container_data, TITLE_OPTIONS)
    demo_dir = ROOT / "artifacts" / "demos" / "demo_play_tandy_L2_full_20260617_180221"
    clock = pygame.time.Clock()
    while True:
        display.set_title("OVERKILL - native (VM-less)  [title -- Space = start, Esc = quit]")
        for _ in range(6 * 30):                  # ~6s on the title
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN
                                              and ev.key == pygame.K_ESCAPE):
                    return False
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                    return True
            display.draw(title)
            clock.tick(30)
        for scene in (lambda: _run_hiscore_screen(display, pygame, container_data, 5.0),
                      lambda: _replay_demo(display, pygame, bundle_data, container_data,
                                           demo_dir, 15.0)):
            r = scene()
            if r is not None:
                return r


def _run_title_screen(display, pygame, container_data) -> bool:
    """The REAL title/options image (OKMENU.ENC, natively decoded) with a HOST fire-wait.

    The original's menu LOGIC (key redefine, joystick, options) is a declared gap -- this shows the
    recovered screen and waits for Space/Esc, nothing more.  Returns True to start a game."""
    title = decode_fullscreen_image(container_data, TITLE_OPTIONS)
    display.set_title("OVERKILL - native (VM-less)  [title -- Space = start, Esc = quit]")
    clock = pygame.time.Clock()
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return False
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                return True
        display.draw(title)
        clock.tick(30)


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
                    help="the static runtime bundle (memory_1mb.bin)")
    ap.add_argument("--container", default=str(DEFAULT_CONTAINER), help="the OVERKILL asset container")
    ap.add_argument("--snapshot", default=None,
                    help="start from a captured snapshot dir's memory_1mb.bin (it IS the state: its "
                         "own planet/difficulty/lives are used; the front end is skipped and "
                         "--level is ignored)")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--no-title", action="store_true", help="skip the title + level select")
    ap.add_argument("--frames", type=int, default=0,
                    help="headless self-test: run N gameplay frames then exit (SDL_VIDEODRIVER=dummy)")
    ap.add_argument("--no-sound", action="store_true", help="disable the PC-speaker audio sink")
    ap.add_argument("--demo", default=None,
                    help="replay a recorded demo through the verified frame + renderer, then exit "
                         "(charter step 2 -- the attract sequence's demo element, standalone)")
    args = ap.parse_args(argv)

    from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image

    bundle_data = Path(args.bundle).read_bytes()
    container_data = Path(args.container).read_bytes()

    display = PygameDisplay(scale=args.scale)
    pygame = display.pygame
    scan_map = _build_scan_map(pygame)

    if args.demo:
        demo_dir = ROOT / "artifacts" / "demos" / args.demo
        print(f"replaying demo {args.demo} through the verified frame (Space/Esc to stop)")
        _replay_demo(display, pygame, bundle_data, container_data, demo_dir, seconds=10_000.0)
        display.close()
        return 0

    if args.snapshot:
        # A SNAPSHOT IS THE STATE.  It already carries its own planet (DS:2356), difficulty
        # (DS:BEDC), score, lives and scroll position -- so the front end must not run before it and
        # must not write over it.  Neither --level nor the level-select pick means anything here.
        img = MutFlatMemory((Path(args.snapshot) / "memory_1mb.bin").read_bytes())
        origin = f"snapshot {Path(args.snapshot).name}"
    else:
        level = args.level
        difficulty = 0
        if not args.no_title and not args.frames:
            if not _run_attract(display, pygame, bundle_data, container_data):
                display.close()
                return 0
            probe_img = build_cold_level_start_image(bundle_data, level, container_data)
            picked = _run_level_select(display, pygame, container_data, probe_img, start_beda=level)
            if picked is None:
                display.close()
                return 0
            level, difficulty = picked
        img = build_cold_level_start_image(bundle_data, level, container_data)
        img.ww(_DS, 0xBEDC, difficulty)   # the difficulty global (the C237 spawn throttle reads it)
        origin = f"cold level {level + 1}"

    planet = img.rw(_DS, 0x2356)

    level_assets = make_level_assets(container_data, bundle_data)
    renderer = ImageRenderer(bundle_data, container_data, img)
    speaker = SpeakerSink(pygame) if not args.frames and not args.no_sound else None
    clock = pygame.time.Clock()
    tick = 0          # gameplay frames advanced (frozen once HELD)
    drawn = 0         # display frames drawn (always advances -- the --frames self-test counts these)
    hold: str | None = None
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

            if hold is None:
                # keyboard -> the image's own INT9 key table; 0162 decodes it inside the frame,
                # through the game's OWN (configurable) control map.  We write the raw keyboard.
                pressed = _pressed_scancodes(pygame, pygame.key.get_pressed(), scan_map)
                for sc in scan_map.values():
                    img.wb(_DS, (0x98C4 + sc) & 0xFFFF, 1 if sc in pressed else 0)
                try:
                    advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets)
                except RecoveryGap as exc:
                    hold = f"{type(exc).__name__}: {exc}"
                    print(f"HELD at tick {tick}: {hold}")
                tick += 1
                # the two exits whose continuations are declared gaps (the frame consumed A346 --
                # death/respawn -- natively; A344 = level complete -> 9734, A342 = game over -> 9902)
                if hold is None and img.rw(_DS, 0xA344) == 1:
                    hold = "level complete: the 9734 next-level continuation is a declared gap"
                    print(f"HELD at tick {tick}: {hold}")
                if hold is None and img.rw(_DS, 0xA342) == 1:
                    hold = "game over: the 9902/98EB continuation is a declared gap"
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
        display.close()
    return 1 if (hold and args.frames) else 0   # a held gap is a self-test failure


if __name__ == "__main__":
    raise SystemExit(main())
