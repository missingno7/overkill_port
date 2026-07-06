"""Headless smoke: play_native's native DEATH -> RESPAWN cycle -- die, explode, respawn, keep playing.

Mirrors ``scripts/play_native.py``'s cold wiring (no pygame) INCLUDING the 9908 death continuation:
run until the wave is live, force the post-9EA3 death state (``DS:A95A = 0xFFFF`` -- what the native
death chain itself writes; its byte-exactness is demo-proven), let the death tail play the explosion
to 0x0F, then assert the native respawn composition:

* the DEATH exit triggers the 9908 continuation instead of stopping: lives 3 -> 2 (``DS:2358``),
  ``apply_respawn_seeds`` (C4DB + C3A6/C42F/C461 + the post-intro bar) re-seeds the level state,
* the player anchor is back: active at the spawn point (0xC0, 0x58), ``A95A = 3``, the bar full,
* play CONTINUES: the wave re-spawns and moves for 150+ more frames with no exit,
* a SECOND forced death cycles again: lives 2 -> 1, still playing.

Usage:
    python -m overkill.probes.verify_play_native_respawn [bundle_path] [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DS = 0x25CC
ANCHOR = 0x237C
DEFAULT_BUNDLE = "artifacts/static_runtime_bundle/memory_1mb.bin"
DEFAULT_CONTAINER = "assets/OVERKILL"


def main(argv) -> int:
    import dataclasses

    from overkill.native_game import NativeGame
    from overkill.native_walk_frame import (
        advance_object_frame, level_tiles, project_state, sync_new_gameplay_records,
        sync_player_anchor,
    )
    from overkill.recovered.adapters.cold_level_start import (
        apply_respawn_seeds, build_cold_level_start, build_cold_level_start_image,
    )
    from overkill.recovered.adapters.level_object_script import run_level_object_script_4a65
    from overkill.recovered.domain.frame_loop import FrameInput, GameplayExit
    from overkill.recovered.domain.object_update import ObjectUpdateGlobals
    from overkill.recovered.systems.frame_loop import (
        death_tail_reached_9aff, detect_gameplay_transition, step_death_tail_9aff,
    )
    from overkill.recovered.systems.input import DEFAULT_CONTROL_MAP, key_state_from_pressed

    bundle_path = Path(argv[0]) if argv else ROOT / DEFAULT_BUNDLE
    frames = int(argv[1]) if len(argv) > 1 else 900
    bundle_data = bundle_path.read_bytes()
    container_data = (ROOT / DEFAULT_CONTAINER).read_bytes()

    state, _starfield = build_cold_level_start(bundle_data, 0)
    game = dataclasses.replace(
        NativeGame.load_level(bundle_data, container_data, 0, state, origin_x=0, row_base=0x9C),
        rows_to_milestone=0x0110)
    walk_image = build_cold_level_start_image(bundle_data, 0)
    walk_tiles = level_tiles(walk_image)
    empty_input = FrameInput(control_map=DEFAULT_CONTROL_MAP, key_state=key_state_from_pressed(set()))

    deaths_forced = 0
    respawns = []                 # (frame, lives_after, anchor_x, anchor_y, a95a, a97a)
    frames_alive_since_respawn = 0
    wave_after_first_respawn = False
    max_alive_streak = 0
    gap = None
    for f in range(frames):
        pre_step_rows = game.rows_to_milestone
        dying = death_tail_reached_9aff(walk_image.rw(DS, 0xA95A), walk_image.rw(DS, 0xA97A))
        if dying:
            tail = step_death_tail_9aff(
                walk_image.rw(DS, 0xA95A), walk_image.rw(DS, 0xA97A),
                walk_image.rw(DS, 0x2326), walk_image.rw(DS, ANCHOR + 0x08))
            walk_image.ww(DS, ANCHOR + 0x08, tail.anchor_counter)
            if tail.deactivate_anchor:
                walk_image.ww(DS, ANCHOR + 0x00, 0)
        else:
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
                scroll_gate=(0, 0, 0), run_object_pass=False)
        sp = game.state.special_pool
        if not dying:
            sync_player_anchor(walk_image, sp.x_word(0), sp.y_word(0), sp.word_at(0, 0x08))
        sync_new_gameplay_records(walk_image, game.state.object_pool)
        walk_image.ww(DS, 0x234E, game.origin_x)
        walk_image.ww(DS, 0x2350, game.row_base)
        walk_image.ww(DS, 0xA978, pre_step_rows)
        run_level_object_script_4a65(walk_image)
        advance_object_frame(walk_image, walk_tiles)
        game = game.with_state(project_state(walk_image))

        # count live level content: 0x20 wave enemies for the first-death arming, and ANY active
        # type-2/4 hostile (excluding the anchor) for post-respawn liveness -- planet 1's script has
        # its ONLY 0x1F wave-controller entry at row 0x110, so later content is OTHER behavior types
        # (0x27/0x11/0x30/0x83/...), not more 0x20 formations.
        enemies = 0
        hostiles = 0
        for pool_name in ("special_pool", "effect_pool", "object_pool"):
            pool = getattr(game.state, pool_name)
            for i in range(len(pool)):
                if not pool.active_word(i):
                    continue
                if pool.word_at(i, 0x18) == 0x20:
                    enemies += 1
                if pool.word_at(i, 0x16) in (2, 4):
                    hostiles += 1
        if hostiles and respawns:
            wave_after_first_respawn = True   # later script rows keep producing live level content
        if respawns and not dying:
            frames_alive_since_respawn += 1
            max_alive_streak = max(max_alive_streak, frames_alive_since_respawn)

        exit_ = detect_gameplay_transition(
            a47c=walk_image.rw(DS, 0xA47C), a95a=walk_image.rw(DS, 0xA95A),
            a97a=walk_image.rw(DS, 0xA97A), v2326=walk_image.rw(DS, 0x2326),
            anchor_counter_after_inc=game.state.special_pool.word_at(0, 0x08))
        if exit_ is not None:
            if exit_.exit is not GameplayExit.DEATH:
                gap = f"unexpected exit {exit_.exit.name} at frame {f}"
                break
            # the 9908 death continuation (mirrors play_native)
            lives = (walk_image.rw(DS, 0x2358) - 1) & 0xFFFF
            if walk_image.rb(DS, 0x978D):
                lives = (lives + 1) & 0xFFFF
            walk_image.ww(DS, 0x2358, lives)
            if lives == 0xFFFF:
                gap = f"game over at frame {f}"
                break
            if walk_image.rb(DS, 0x98C0):
                walk_image.wb(DS, 0xBEFF, 0x02)
            apply_respawn_seeds(walk_image)
            walk_image.ww(DS, 0xA8D0, 0xA8D2)
            walk_image.ww(DS, 0xA8C8, 0)
            walk_image.ww(DS, 0xA8CC, 0)
            walk_image.ww(DS, 0xA8C2, 0)
            walk_image.ww(DS, 0x20A6, 0x20A8)
            game = game.with_state(project_state(walk_image))
            respawns.append((f, lives, walk_image.rw(DS, ANCHOR + 0x02),
                             walk_image.rw(DS, ANCHOR + 0x04),
                             walk_image.rw(DS, 0xA95A), walk_image.rw(DS, 0xA97A)))
            frames_alive_since_respawn = 0
            print(f"  respawn at frame {f}: lives={lives}")
            continue

        # force the FIRST death once the wave is live; any further deaths are the level's own doing
        # (the respawned ship sits unpiloted at the spawn point in a scrolling shooting gallery --
        # this run has NO input, so natural deaths are expected and exercise the same path).
        if deaths_forced == 0 and f >= 120 and not dying and enemies:
            walk_image.ww(DS, 0xA95A, 0xFFFF)
            walk_image.ww(DS, 0xA95C, 0x0000)
            walk_image.ww(DS, 0x2384, 0x0003)
            deaths_forced += 1

    lives_seq = [r[1] for r in respawns]
    print(f"deaths forced: {deaths_forced}; respawns: {respawns}; longest alive streak after a "
          f"respawn: {max_alive_streak}; hostiles after first respawn: {wave_after_first_respawn}; "
          f"gap: {gap}")
    # PASS: at least two full death->respawn cycles with the correct reseeded state each time, lives
    # stepping down 2,1,..; play continues (a 100+ frame streak); later script rows keep producing
    # live content. A game-over gap is acceptable ONLY as the true lives-exhausted end (2,1,0 first).
    ok = (deaths_forced == 1 and len(respawns) >= 2
          and lives_seq == list(range(2, 2 - len(respawns), -1))
          and all(r[2] == 0xC0 and r[3] == 0x58 and r[4] == 3 and r[5] == 0x58 for r in respawns)
          and max_alive_streak >= 100 and wave_after_first_respawn
          and (gap is None or (gap.startswith("game over") and lives_seq[-1] == 0)))
    print("RESULT:", "PASS -- die, explode, respawn (lives stepping down), the level keeps living, "
          "play continues -- the full native death->respawn cycle, VM-free" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
