"""Headless smoke: ``play_native``'s COLD path (no --snapshot) shows a live, MOVING enemy wave.

Mirrors ``scripts/play_native.py``'s exact wiring (no pygame -- the window can't be observed here):
cold-seed ``NativeGame`` (:func:`overkill.recovered.adapters.cold_level_start.build_cold_level_start`),
build the object-walk DGROUP image identically
(:func:`overkill.recovered.adapters.cold_level_start.build_cold_level_start_image`), then tick both in
lockstep exactly like ``play_native._advance`` does: ``NativeGame.step`` (player + scroll), sync the
player anchor / origin / row_base / ``rows_to_milestone`` into the image, run the level-object-script
walker (``4A65``) so scroll-triggered spawns fire, run the whole behaviour walk, and project the pools
back.  This is the loop-closer for the cold-boot wiring itself (verify_cold_populate proves the
walker+walk compose from a hand-driven row counter; this proves play_native's actual glue -- the
NativeGame-owned scroll feeding the image's ``A978`` -- produces the same live wave).

Usage:
    python -m overkill.probes.verify_play_native_cold [bundle_path] [level_index] [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

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
    from overkill.recovered.domain.gaps import RecoveryGap
    from overkill.recovered.domain.object_update import ObjectUpdateGlobals
    from overkill.recovered.systems.input import DEFAULT_CONTROL_MAP, key_state_from_pressed

    bundle_path = Path(argv[0]) if argv else ROOT / DEFAULT_BUNDLE
    level_index = int(argv[1]) if len(argv) > 1 else 0
    frames = int(argv[2]) if len(argv) > 2 else 200
    bundle_data = bundle_path.read_bytes()
    container_data = (ROOT / DEFAULT_CONTAINER).read_bytes()

    state, _starfield = build_cold_level_start(bundle_data, level_index)
    _COLD_ROW_BASE = 0x9C
    _COLD_ROWS_TO_MILESTONE = 0x0110
    game = NativeGame.load_level(bundle_data, container_data, level_index, state,
                                  origin_x=0, row_base=_COLD_ROW_BASE)
    game = dataclasses.replace(game, rows_to_milestone=_COLD_ROWS_TO_MILESTONE)

    walk_image = build_cold_level_start_image(bundle_data, level_index)
    walk_tiles = level_tiles(walk_image)

    ever_enemies = 0
    moved = False
    track = None
    gaps = []
    empty_input = FrameInput(control_map=DEFAULT_CONTROL_MAP, key_state=key_state_from_pressed(set()))
    for f in range(frames):
        pre_step_rows_to_milestone = game.rows_to_milestone
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
                a278=0, tile_probe_suppressed=False, tiles=game.tile_context,
            ),
            scroll_gate=(0, 0, 0),
            run_object_pass=False,
        )
        sp = game.state.special_pool
        sync_player_anchor(walk_image, sp.x_word(0), sp.y_word(0), sp.word_at(0, 0x08))
        sync_new_gameplay_records(walk_image, game.state.object_pool)
        walk_image.ww(0x25CC, 0x234E, game.origin_x)
        walk_image.ww(0x25CC, 0x2350, game.row_base)
        walk_image.ww(0x25CC, 0xA978, pre_step_rows_to_milestone)
        try:
            run_level_object_script_4a65(walk_image)
            advance_object_frame(walk_image, walk_tiles)
            game = game.with_state(project_state(walk_image))
        except RecoveryGap as exc:
            gaps.append((f, str(exc)))
            break

        e = c = 0
        sample = None
        for pool_name in ("special_pool", "effect_pool", "object_pool"):
            pool = getattr(game.state, pool_name)
            for i in range(len(pool)):
                if not pool.active_word(i):
                    continue
                beh = pool.word_at(i, 0x18)
                if beh == 0x20:
                    e += 1
                    if sample is None:
                        sample = (pool_name, i, pool.x_word(i), pool.y_word(i))
                elif beh == 0x1F:
                    c += 1
        ever_enemies = max(ever_enemies, e)
        if sample is not None:
            if track is not None and track[0] == sample[0] and track[1] == sample[1] \
                    and (track[2], track[3]) != (sample[2], sample[3]):
                moved = True
            track = sample
        if f < 6 or f % 40 == 0 or (e and f % 8 == 0):
            print(f"  frame {f:3d} A978(checked)={pre_step_rows_to_milestone:04X}: "
                  f"controllers={c} enemies={e}")

    print(f"play_native cold: peak enemies={ever_enemies}, tracked enemy moved={moved}, "
          f"gap-frames={len(gaps)}")
    for f, msg in gaps[:4]:
        print(f"    gap @ frame {f}: {msg}")
    ok = ever_enemies >= 1 and moved and not gaps
    print("RESULT:", "PASS -- play_native's cold wiring produces a live, moving enemy wave, VM-free"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
