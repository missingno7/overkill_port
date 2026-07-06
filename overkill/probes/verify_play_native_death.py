"""Headless smoke: play_native's native DEATH TAIL -- explosion anim, frozen ship, live walk, exit.

Mirrors ``scripts/play_native.py``'s cold wiring (no pygame) exactly like ``verify_play_native_cold``,
runs until the wave is live, then forces the post-9EA3 death state (``DS:A95A = 0xFFFF`` -- the value
the native death chain itself writes on life exhaustion; the chain's own byte-exactness is already
demo-proven) and asserts the 9B61/9AFF composition:

* the player/scroll/fan-out stage is SKIPPED while dying (the ship + scroll freeze),
* the anchor's ``+08`` cell counts the explosion animation, advancing ONLY on ``DS:2326 == 3``
  phases (the mod-4 frame counter),
* the object WALK keeps running (enemies still move during the death animation),
* at counter ``0x0F`` the anchor slot deactivates and ``detect_gameplay_transition`` fires DEATH
  (the A97A bar is at its seeded post-intro 0x58, so not GAME_OVER).

Also asserts the cold start itself is NOT dying (the new ``A97A = 0x58`` post-intro seed -- an empty
bar IS the 9B61 death condition, so the old unseeded 0 would have started the level dying).

Usage:
    python -m overkill.probes.verify_play_native_death [bundle_path] [frames]
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
        build_cold_level_start, build_cold_level_start_image,
    )
    from overkill.recovered.adapters.level_object_script import run_level_object_script_4a65
    from overkill.recovered.domain.frame_loop import FrameInput
    from overkill.recovered.domain.object_update import ObjectUpdateGlobals
    from overkill.recovered.systems.frame_loop import (
        death_tail_reached_9aff, detect_gameplay_transition, step_death_tail_9aff,
    )
    from overkill.recovered.systems.input import DEFAULT_CONTROL_MAP, key_state_from_pressed

    bundle_path = Path(argv[0]) if argv else ROOT / DEFAULT_BUNDLE
    frames = int(argv[1]) if len(argv) > 1 else 400
    bundle_data = bundle_path.read_bytes()
    container_data = (ROOT / DEFAULT_CONTAINER).read_bytes()

    state, _starfield = build_cold_level_start(bundle_data, 0)
    game = dataclasses.replace(
        NativeGame.load_level(bundle_data, container_data, 0, state, origin_x=0, row_base=0x9C),
        rows_to_milestone=0x0110)
    walk_image = build_cold_level_start_image(bundle_data, 0)
    walk_tiles = level_tiles(walk_image)
    empty_input = FrameInput(control_map=DEFAULT_CONTROL_MAP, key_state=key_state_from_pressed(set()))

    assert not death_tail_reached_9aff(walk_image.rw(DS, 0xA95A), walk_image.rw(DS, 0xA97A)), \
        "cold start must NOT be dying (the A97A=0x58 post-intro seed)"

    death_forced_at = None
    counter_advances = []          # (frame, 2326 phase) for each +08 advance while dying
    ship_x_frozen = None
    enemy_moved_while_dying = False
    enemy_track = None
    exit_fired = None
    for f in range(frames):
        pre_step_rows = game.rows_to_milestone
        dying = death_tail_reached_9aff(walk_image.rw(DS, 0xA95A), walk_image.rw(DS, 0xA97A))
        if dying:
            before = walk_image.rw(DS, ANCHOR + 0x08)
            phase = walk_image.rw(DS, 0x2326)
            tail = step_death_tail_9aff(
                walk_image.rw(DS, 0xA95A), walk_image.rw(DS, 0xA97A),
                phase, before)
            walk_image.ww(DS, ANCHOR + 0x08, tail.anchor_counter)
            if tail.anchor_counter != before:
                counter_advances.append((f, phase))
            if tail.deactivate_anchor:
                walk_image.ww(DS, ANCHOR + 0x00, 0)
            assert walk_image.rw(DS, ANCHOR + 0x02) == ship_x_frozen, \
                "the ship must FREEZE during the death anim (no player step)"
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

        # prove the walk keeps running during the death anim: any enemy record's state changes
        # (formation enemies can HOLD position, so hash every 0x20 record's full x/y/sprite triple)
        sample = None
        wave_sig = []
        for pool_name in ("special_pool", "effect_pool", "object_pool"):
            pool = getattr(game.state, pool_name)
            for i in range(len(pool)):
                if pool.active_word(i) and pool.word_at(i, 0x18) == 0x20:
                    wave_sig.append((pool_name, i, pool.x_word(i), pool.y_word(i),
                                     pool.word_at(i, 0x08), pool.word_at(i, 0x1C)))
                    if sample is None:
                        sample = wave_sig[-1]
        if dying and wave_sig and enemy_track and tuple(wave_sig) != enemy_track:
            enemy_moved_while_dying = True
        enemy_track = tuple(wave_sig)

        exit_ = detect_gameplay_transition(
            a47c=walk_image.rw(DS, 0xA47C), a95a=walk_image.rw(DS, 0xA95A),
            a97a=walk_image.rw(DS, 0xA97A), v2326=walk_image.rw(DS, 0x2326),
            anchor_counter_after_inc=game.state.special_pool.word_at(0, 0x08))
        if exit_ is not None:
            exit_fired = (f, exit_.exit.name)
            break

        # once the wave is live, force the post-9EA3 death state (what the native chain writes)
        if death_forced_at is None and f >= 120 and sample is not None:
            walk_image.ww(DS, 0xA95A, 0xFFFF)
            walk_image.ww(DS, 0xA95C, 0x0000)
            walk_image.ww(DS, 0x2384, 0x0003)
            ship_x_frozen = walk_image.rw(DS, ANCHOR + 0x02)
            death_forced_at = f

    phases = {p for _, p in counter_advances}
    print(f"death forced at frame {death_forced_at}; +08 advances: {len(counter_advances)} "
          f"(phases seen: {sorted(phases)}); wave changed while dying: {enemy_moved_while_dying}; "
          f"exit: {exit_fired}")
    # DS:2384 IS the anchor's +08 cell (0x237C + 8): the 9EA3 chain's `[2384] = 3` seeds the
    # explosion counter at 3, so the 9AFF anim runs 3 -> 0x0F = 12 phase-3 advances exactly.
    ok = (death_forced_at is not None
          and exit_fired is not None and exit_fired[1] == "DEATH"
          and len(counter_advances) == 0x0F - 3
          and phases == {3}
          and enemy_moved_while_dying
          and walk_image.rw(DS, ANCHOR + 0x00) == 0)
    print("RESULT:", "PASS -- the native death tail plays the explosion (phase-3 clocked, sprites "
          "3..0xF), freezes the ship, keeps the wave live, and fires the DEATH exit at 0x0F"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
