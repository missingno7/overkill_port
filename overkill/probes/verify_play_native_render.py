"""Headless PIXEL gate: play_native's cold path actually RENDERS the game -- ship + enemy sprites.

The state-level smokes (verify_play_native_cold/death/respawn) proved the cold wiring produces a
live, moving wave -- but the sprite compositor places objects from the records' ``+0x0C``
screen-projection cells, which only the A90C present scan computes; without it the game played
INVISIBLY (the stars-only bug the owner caught).  This gate mirrors play_native's cold wiring
INCLUDING ``sync_screen_projection`` and asserts the composed frame (the exact ``_render_frame``
play_native blits, numpy, no pygame) shows:

* the PLAYER SHIP from the very first frames (sprite pixels differing from the bare starfield), and
* substantially MORE sprite pixels once the wave is live (enemies visible on screen).

Usage:
    python -m overkill.probes.verify_play_native_render [bundle_path] [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DS = 0x25CC
DEFAULT_BUNDLE = "artifacts/static_runtime_bundle/memory_1mb.bin"
DEFAULT_CONTAINER = "assets/OVERKILL"


def main(argv) -> int:
    import dataclasses

    import numpy as np

    from overkill.native_game import NativeGame
    from overkill.native_walk_frame import (
        advance_object_frame, level_tiles, project_state, sync_new_gameplay_records,
        sync_player_anchor, sync_screen_projection,
    )
    from overkill.recovered.adapters.cold_level_start import (
        build_cold_level_start, build_cold_level_start_image,
    )
    from overkill.recovered.adapters.level_object_script import run_level_object_script_4a65
    from overkill.recovered.domain.frame_loop import FrameInput
    from overkill.recovered.domain.object_update import ObjectUpdateGlobals
    from overkill.recovered.systems.input import DEFAULT_CONTROL_MAP, key_state_from_pressed
    from overkill.native_video.starfield_plate import render_starfield_plate
    import scripts.play_native as pn

    bundle_path = Path(argv[0]) if argv else ROOT / DEFAULT_BUNDLE
    frames = int(argv[1]) if len(argv) > 1 else 150
    bundle_data = bundle_path.read_bytes()
    container_data = (ROOT / DEFAULT_CONTAINER).read_bytes()

    state, starfield = build_cold_level_start(bundle_data, 0)
    game = dataclasses.replace(
        NativeGame.load_level(bundle_data, container_data, 0, state, origin_x=0, row_base=0x9C),
        rows_to_milestone=0x0110)
    walk_image = build_cold_level_start_image(bundle_data, 0)
    walk_tiles = level_tiles(walk_image)
    mem = walk_image  # alias for the half-stride read below
    ctx = pn._build_sprite_context(bundle_data, container_data, game,
                                   (mem.rw(DS, 0x1028) >> 1) & 0xFFFF)
    empty_input = FrameInput(control_map=DEFAULT_CONTROL_MAP, key_state=key_state_from_pressed(set()))

    ship_pixels_early = None
    max_pixels = 0
    for f in range(frames):
        pre_step_rows = game.rows_to_milestone
        game, _ = game.step(
            empty_input, no_clamp=False,
            repeat_9790=0, state_232a=0, scroll_2350=game.row_base,
            bdac=0, a958=0, be06=0,
            source_index=0, source_x=game.state.special_pool.x_word(0),
            source_y=game.state.special_pool.y_word(0),
            read_ds_word=lambda off: 0,
            update_globals=ObjectUpdateGlobals(
                ref_box_x=game.state.special_pool.x_word(0),
                ref_box_y=game.state.special_pool.y_word(0),
                a278=0, tile_probe_suppressed=False, tiles=game.tile_context),
            scroll_gate=(walk_image.rw(DS, 0xA47C), walk_image.rw(DS, 0xA47E),
                         walk_image.rw(DS, 0xA480)),
            run_object_pass=False)
        sp = game.state.special_pool
        sync_player_anchor(walk_image, sp.x_word(0), sp.y_word(0), sp.word_at(0, 0x08))
        sync_new_gameplay_records(walk_image, game.state.object_pool)
        walk_image.ww(DS, 0x234E, game.origin_x)
        walk_image.ww(DS, 0x2350, game.row_base)
        walk_image.ww(DS, 0x234C, game.row_source)
        walk_image.ww(DS, 0xA978, pre_step_rows)
        run_level_object_script_4a65(walk_image)
        advance_object_frame(walk_image, walk_tiles)
        sync_screen_projection(walk_image)
        game = game.with_state(project_state(walk_image))

        frame = np.asarray(pn._render_frame(game, starfield, ctx))
        plate = np.asarray(render_starfield_plate(starfield, game.row_source))
        pixels = int((frame != plate).sum())
        if f == 2:
            ship_pixels_early = pixels
        max_pixels = max(max_pixels, pixels)
        if f in (2, 30, 60, 90, 120) or (f == frames - 1):
            print(f"  frame {f:3d}: sprite pixels on screen = {pixels}")

    # The HUD panel: the byte-exact-gated compose (verify_native_hud_panel) over the walk image's
    # LIVE cells must light the panel region up -- the experience gate for the play_native overlay.
    from overkill.asset_codecs.container import load_container_asset
    from overkill.asset_codecs.planar import deplanarize_tandy
    from overkill.native_video.hud_panel import panel_indices_from_page
    from overkill.recovered.adapters.hud_panel_state import (
        compose_hud_panel_from_image, read_hud_dir_table, read_hud_font)
    panel_source = np.frombuffer(
        deplanarize_tandy(load_container_asset(container_data, "PANEL.ENC"),
                          sprite_mode=False, emit_item_headers=True), dtype=np.uint8)
    panel = panel_indices_from_page(compose_hud_panel_from_image(
        walk_image, panel_source=panel_source,
        dir_table=read_hud_dir_table(walk_image), font=read_hud_font(walk_image)))
    panel_pixels = int((panel > 0).sum())
    print(f"HUD panel pixels lit: {panel_pixels} / {panel.size}")

    print(f"ship pixels at frame 2: {ship_pixels_early}; peak sprite pixels: {max_pixels}")
    ok = (ship_pixels_early or 0) >= 30 and max_pixels >= 300 and panel_pixels >= 5000
    print("RESULT:", "PASS -- the cold-booted game RENDERS: the ship is visible from the first "
          "frames, the wave lights the screen up, and the HUD panel is composed" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
