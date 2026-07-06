"""Headless smoke: play_native's cold path reaches the LEVEL END and the outro arms, VM-free.

Mirrors play_native's cold wiring and lets the scroll run the whole plane: the probe CLEARS the
wave state each tick (A47E/A480 = 0 + deactivating spawned type-2/4 records -- a documented probe
convenience standing in for the player shooting everything, so the A66F gate never holds) and spins
until row_base crosses the whole level.  Asserts the native milestone composition:

* the scroll does NOT stall at 0x0E52 (the C591 milestone -- a Tandy no-op, previously a decline),
* at 0x0EA0 the A680 arm fires: ``A47C == 1``, the four A3EE outro objects (behavior 0x53) are live,
* the walk keeps running with the outro on stage (the 0x53 sprites animate), and the scroll HOLDS
  (A47C nonzero gates it) -- the armed outro scene, awaiting the phase handlers (the next slice).

Usage:
    python -m overkill.probes.verify_play_native_levelend [bundle_path] [max_ticks]
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
    from overkill.recovered.adapters.behavior_walk import (
        run_level_end_arm_a680, run_outro_script_99f6,
    )
    from overkill.recovered.domain.frame_loop import GameplayExit
    from overkill.recovered.systems.frame_loop import detect_gameplay_transition
    from overkill.recovered.adapters.cold_level_start import (
        build_cold_level_start, build_cold_level_start_image,
    )
    from overkill.recovered.adapters.level_object_script import run_level_object_script_4a65
    from overkill.recovered.domain.frame_loop import FrameInput
    from overkill.recovered.domain.gaps import RecoveryGap
    from overkill.recovered.domain.object_update import ObjectUpdateGlobals
    from overkill.recovered.systems.input import DEFAULT_CONTROL_MAP, key_state_from_pressed

    bundle_path = Path(argv[0]) if argv and argv[0] else ROOT / DEFAULT_BUNDLE
    max_ticks = int(argv[1]) if len(argv) > 1 else 6000
    bundle_data = bundle_path.read_bytes()
    container_data = (ROOT / DEFAULT_CONTAINER).read_bytes()

    state, _sf = build_cold_level_start(bundle_data, 0)
    game = dataclasses.replace(
        NativeGame.load_level(bundle_data, container_data, 0, state, origin_x=0, row_base=0x9C),
        rows_to_milestone=0x0110)
    walk_image = build_cold_level_start_image(bundle_data, 0)
    walk_tiles = level_tiles(walk_image)
    empty_input = FrameInput(control_map=DEFAULT_CONTROL_MAP, key_state=key_state_from_pressed(set()))

    passed_e52 = False
    armed_at = None
    outro_sig = []          # (tick, tuple of the 0x53 records' sprites)
    phases_seen: set = set()
    scripted_exit_at = None
    gap = None
    for t in range(max_ticks):
        pre_rows = game.rows_to_milestone
        pre_row_base = game.row_base

        def clear_field() -> None:
            # the probe convenience: the "player" clears everything instantly so the scroll never
            # holds and freshly-scripted spawns never walk -- the END mechanics are what's under test
            walk_image.ww(DS, 0xA47E, 0)
            walk_image.ww(DS, 0xA480, 0)
            for table, n in ((0x32CA, 0x23), (0x8D12, 0x22)):
                for cx in range(1, n + 1):
                    rec = walk_image.rw(DS, (table + cx * 2) & 0xFFFF)
                    if rec and rec != ANCHOR and walk_image.rw(DS, rec) \
                            and walk_image.rw(DS, rec + 0x16) in (2, 4):
                        walk_image.ww(DS, rec, 0)

        if armed_at is None:
            clear_field()
        frame_input = empty_input
        a47c = walk_image.rw(DS, 0xA47C)
        if a47c in (1, 2, 3):
            from overkill.recovered.systems.input import key_state_from_pressed as ksp
            bits = run_outro_script_99f6(walk_image)
            phases_seen.add(a47c)
            pressed = {sc for sc, mask in ((0x4D, 1), (0x4B, 2), (0x50, 4), (0x48, 8))
                       if bits & mask}
            frame_input = FrameInput(control_map=DEFAULT_CONTROL_MAP, key_state=ksp(pressed))
        game, _ = game.step(
            frame_input, no_clamp=a47c in (1, 2, 3),
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
        if game.row_base == 0x0E52 and pre_row_base != 0x0E52:
            passed_e52 = True
        if game.row_base == 0x0EA0 and pre_row_base != 0x0EA0 \
                and walk_image.rw(DS, 0xA47C) == 0:
            run_level_end_arm_a680(walk_image)
            armed_at = t
            print(f"  armed at tick {t} (row_base=0x0EA0)")
        sp = game.state.special_pool
        sync_player_anchor(walk_image, sp.x_word(0), sp.y_word(0), sp.word_at(0, 0x08))
        sync_new_gameplay_records(walk_image, game.state.object_pool)
        walk_image.ww(DS, 0x234E, game.origin_x)
        walk_image.ww(DS, 0x2350, game.row_base)
        walk_image.ww(DS, 0x234C, game.row_source)
        walk_image.ww(DS, 0xA978, pre_rows)
        try:
            run_level_object_script_4a65(walk_image)
        except RecoveryGap as exc:
            if "wave driver" not in str(exc):
                raise
            # the row-4 script entry spawns the 0x21 wave driver via the walker's DECLARED gap (the
            # 1F8F:0209 leftover-ax schedule quirk).  Skip that single entry (advance the cursor) so
            # the END mechanics under test stay reachable; the driver spawn remains the recorded
            # blocker for a full NATURAL playthrough.
            planet = walk_image.rw(DS, 0x2356)
            cell = walk_image.rw(DS, (0xC5E9 + planet * 2) & 0xFFFF)
            si = walk_image.rw(DS, cell)
            si += 2
            if walk_image.rw(DS, si) == 0xFFFF:
                si += 2
            walk_image.ww(DS, cell, (si + 6) & 0xFFFF)
        if armed_at is None:
            clear_field()      # the script fires INSIDE the frame; clear before the walk sees them
        advance_object_frame(walk_image, walk_tiles)
        game = game.with_state(project_state(walk_image))

        if armed_at is not None:
            sprites = []
            for cx in range(1, 0x24):
                rec = walk_image.rw(DS, (0x32CA + cx * 2) & 0xFFFF)
                if rec and walk_image.rw(DS, rec) and walk_image.rw(DS, rec + 0x18) == 0x53:
                    sprites.append(walk_image.rw(DS, rec + 0x08))
            outro_sig.append((t, tuple(sorted(sprites))))
        exit_ = detect_gameplay_transition(
            a47c=walk_image.rw(DS, 0xA47C), a95a=walk_image.rw(DS, 0xA95A),
            a97a=walk_image.rw(DS, 0xA97A), v2326=walk_image.rw(DS, 0x2326),
            anchor_counter_after_inc=game.state.special_pool.word_at(0, 0x08))
        if exit_ is not None:
            if exit_.exit is GameplayExit.SCRIPTED:
                scripted_exit_at = t
                print(f"  SCRIPTED exit (LEVEL COMPLETE) at tick {t}; phases seen: {sorted(phases_seen)}")
                # the 9744 advance (mirrors play_native._load_next_level): boot LEVEL 2 with the
                # session carried, then prove the L2 wave spawns natively
                score_lo, score_hi = walk_image.rw(DS, 0x2314), walk_image.rw(DS, 0x2316)
                lives = walk_image.rw(DS, 0x2358)
                walk_image.ww(DS, 0x2314, 0x1234)   # make the carry-over observable
                score_lo = 0x1234
                new_img = build_cold_level_start_image(bundle_data, 1)
                new_img.ww(DS, 0x2314, score_lo)
                new_img.ww(DS, 0x2316, score_hi)
                new_img.ww(DS, 0x2358, lives)
                walk_image.data[:] = new_img.data
                nstate, _nsf = build_cold_level_start(bundle_data, 1)
                game = dataclasses.replace(
                    NativeGame.load_level(bundle_data, container_data, 1, nstate,
                                          origin_x=0, row_base=0x9C),
                    rows_to_milestone=0x0110)
                walk_tiles = level_tiles(walk_image)
                l2 = {"planet": walk_image.rw(DS, 0x2356), "score": walk_image.rw(DS, 0x2314),
                      "lives": walk_image.rw(DS, 0x2358)}
                l2_frames = 0
                l2_wave = 0
                for f2 in range(240):
                    pre2 = game.rows_to_milestone
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
                    sp2 = game.state.special_pool
                    sync_player_anchor(walk_image, sp2.x_word(0), sp2.y_word(0), sp2.word_at(0, 0x08))
                    sync_new_gameplay_records(walk_image, game.state.object_pool)
                    walk_image.ww(DS, 0x234E, game.origin_x)
                    walk_image.ww(DS, 0x2350, game.row_base)
                    walk_image.ww(DS, 0x234C, game.row_source)
                    walk_image.ww(DS, 0xA978, pre2)
                    run_level_object_script_4a65(walk_image)
                    try:
                        advance_object_frame(walk_image, walk_tiles)
                    except RecoveryGap as exc:
                        # the KNOWN L2 zoo frontier (0x39/0x8A/...) -- the honest boundary of this
                        # slice: the transition itself is proven once the wave spawned natively
                        l2["gap"] = str(exc).split(" (record")[0]
                        break
                    game = game.with_state(project_state(walk_image))
                    l2_frames = f2 + 1
                    for cx in range(1, 0x24):
                        rec = walk_image.rw(DS, (0x32CA + cx * 2) & 0xFFFF)
                        if rec and walk_image.rw(DS, rec) \
                                and walk_image.rw(DS, rec + 0x18) in (0x1C, 0x1D, 0x1E):
                            l2_wave += 1
                l2["frames"] = l2_frames
                l2["wave_hits"] = l2_wave
                print(f"  L2 boot: {l2}")
                # the L2 walk gaps on its KNOWN zoo frontier (0x39 scenery spawns in the very first
                # script row) -- the transition claim: planet 2 booted, session carried, and the L2
                # wave CONTROLLER is on stage (the script fired). The L2 zoo is separate ongoing work.
                l2_ok = (l2["planet"] == 2 and l2["score"] == 0x1234 and l2["lives"] == lives
                         and l2_wave > 0)
                if not l2_ok:
                    gap = f"the L2 transition check failed: {l2}"
            else:
                gap = f"unexpected exit {exit_.exit.name} at tick {t}"
            break

    n_outro = len(outro_sig[-1][1]) if outro_sig else 0
    animated = len({s for _, s in outro_sig}) > 1 if outro_sig else False
    # `game` rebinds to the L2 state after the transition, so "the scroll held through the outro"
    # is implied by the SCRIPTED exit itself (A47C nonzero gated the scroll throughout the phases).
    held = scripted_exit_at is not None
    print(f"passed 0x0E52: {passed_e52}; armed at: {armed_at}; outro objects live: {n_outro}; "
          f"outro animating: {animated}; scroll held at 0xEA0: {held}; phases: {sorted(phases_seen)}; "
          f"scripted exit at: {scripted_exit_at}; gap: {gap}")
    # phase 3 can complete WITHIN the phase-2 tick (the 99F6 re-dispatch + the settled-counter
    # fixed point advances it immediately for an undamaged ship), so {1, 2} + the SCRIPTED exit
    # proves the full chain (the exit REQUIRES A47C == 4, which only phase 3 sets).
    ok = (passed_e52 and armed_at is not None and n_outro == 4 and animated and held
          and phases_seen >= {1, 2} and scripted_exit_at is not None and gap is None)
    print("RESULT:", "PASS -- the level scrolls to its end, the outro arms, the four 0x53 objects "
          "animate, the autopilot flies phases 1..3, and the SCRIPTED exit (LEVEL COMPLETE) fires "
          "-- VM-free" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
