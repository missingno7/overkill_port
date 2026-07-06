"""THE OWNER'S BAR: the native frame compose vs the VM's OWN page, 1:1, across a played demo.

For every cached walk frame (the walk-shadow cache stores the FULL VM machine state), build the
native frame exactly the way ``play_native`` renders -- the starfield plate (from the pre-state's
LIVE star records) + the object sprite layer (from the pre-state's own pools and projection
cells) -- and pixel-diff it against the VM's own present page
(``render_present_page_indices`` of ``CS:[9598]`` at ``DS:[234C]``) over the playfield region
``x in [0,208), y in [4,196)``.

This is a REPORTING probe first: the diff count IS the render TODO list (the missing tile-plane
layer is expected to dominate; then the skipped anim/variant sprite routines).  The goal
criterion is diff -> 0, at which point it flips to a hard gate.

Usage:
    python -m overkill.probes.verify_native_frame_1to1 [demo_name] [stride]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEMO = "demo_cold_start_full_20260705_123645"
DEFAULT_BUDGET = 20000
CS = 0x1010
DS = 0x25CC
PLAYFIELD = np.s_[4:196, 0:208]


def main(argv) -> int:
    import dataclasses

    from overkill.native_game import NativeGame
    from overkill.native_video.frame import SnapshotSprite
    from overkill.native_video.page_raster import render_present_page_indices
    from overkill.native_video.playfield import compose_playfield_indices
    from overkill.native_video.object_sprites import object_sprite_blocks
    from overkill.native_video.starfield_plate import render_starfield_plate
    from overkill.native_walk_frame import project_state
    from overkill.probes._shadow_cache import (cache_path_for, demo_key, iter_cached_frames,
                                               load_cache)
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.adapters.starfield_adapter import load_starfield_state
    import scripts.play_native as pn

    demo_name = argv[0] if argv and argv[0] else DEFAULT_DEMO
    stride = int(argv[1]) if len(argv) > 1 else 250

    class _Demo:
        demo_dir = str(ROOT / "artifacts" / "demos" / demo_name)

    cached = load_cache(cache_path_for(_Demo()), demo_key(_Demo()), DEFAULT_BUDGET)
    if cached is None:
        print(f"RESULT: SKIP -- no walk-shadow cache for {demo_name}")
        return 0

    bundle_data = (ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin").read_bytes()
    container_data = (ROOT / "assets" / "OVERKILL").read_bytes()
    game0 = NativeGame.load_level(bundle_data, container_data, 0,
                                  __import__("overkill.recovered.adapters.cold_level_start",
                                             fromlist=["build_cold_level_start"])
                                  .build_cold_level_start(bundle_data, 0)[0],
                                  origin_x=0, row_base=0x9C)
    del dataclasses

    frames = diff_total = 0
    worst = (0, -1)
    for i, (pre, post, sp) in enumerate(iter_cached_frames(cached)):
        if i % stride:
            continue
        image = MutFlatMemory(pre)
        cursor = image.rw(DS, 0x234C)
        page_seg = image.rw(CS, 0x9598)
        pre_np = np.frombuffer(bytes(image.data), dtype=np.uint8)
        vm = render_present_page_indices(pre_np, page_seg, cursor)

        ctx = pn._build_sprite_context(bundle_data, container_data, game0,
                                       (image.rw(DS, 0x1028) >> 1) & 0xFFFF)
        state = project_state(image)
        plate = render_starfield_plate(load_starfield_state(bytes(image.data)), cursor)
        blocks = []
        for pool in (state.special_pool, state.effect_pool, state.object_pool):
            blocks.extend(object_sprite_blocks(pool, ctx))
        if blocks:
            sprite = SnapshotSprite(identity=0, sprite_id=0, anim_phase=0, screen_di=0,
                                    blocks=tuple(blocks))
            native = compose_playfield_indices(plate, [sprite], cursor)
        else:
            native = plate
        d = int((native[PLAYFIELD] != vm[PLAYFIELD]).sum())
        frames += 1
        diff_total += d
        if d > worst[0]:
            worst = (d, i)
        print(f"  frame {i:5d}: playfield diff px = {d}")
    area = 192 * 208
    print(f"frames sampled: {frames}; mean diff px/frame: {diff_total // max(1, frames)} "
          f"of {area}; worst: {worst[0]} at frame {worst[1]}")
    print("RESULT:", "PASS -- 1:1 with the VM page" if diff_total == 0 else
          "REPORT -- the diff above is the render TODO list (tiles, anim/variant sprites); "
          "the goal criterion is 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
