"""Verify the native LEVEL-SELECT screen pieces against the live snapshot's own tables.

1. **the cell layout**: walking the natively-decoded CHOOSE.ENC headers reproduces the runtime
   loader's ``CS:D37E`` pointer table exactly (as ``offset + 0x4000``) -- the snapshot is the
   oracle for the loader's segment layout;
2. **the xy tables**: the static bundle's ``DS:BEDE``/``BEEA`` words equal the live snapshot's
   (they are static DGROUP data, safe to read from a cold image);
3. **the compose**: the two cursor cells land at their exact 5A00 pixel positions on a LEVSCR
   frame (content check at the stamp rectangles);
4. **the flow mapping**: the D424 fire resolve + the 9744/971A advance send grid cell k to
   planet ``LEVEL_INDEX_TO_PLANET[k]`` -- i.e. the cell IS the 0-based level index.

Usage:
    python -m overkill.probes.verify_native_level_select
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SNAP = ROOT / "artifacts" / "demos" / "demo_play_tandy_L2_full_20260617_180221" / "snapshot"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


def main(argv) -> int:
    from overkill.asset_codecs.container import load_container_asset
    from overkill.asset_codecs.planar import deplanarize_tandy
    from overkill.native_video.front_end import decode_fullscreen_image
    from overkill.native_video.level_select import (CHOOSE_SEGMENT_BASE, cell_indices,
                                                    compose_level_select, walk_choose_cells)
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.adapters.level_select_state import read_level_select_tables
    from overkill.recovered.adapters.cold_level_start import LEVEL_INDEX_TO_PLANET
    from overkill.recovered.systems.menu import (advance_level_index_9744,
                                                 resolve_level_select_fire_d424)

    container = (ROOT / "assets" / "OVERKILL").read_bytes()
    choose = np.frombuffer(deplanarize_tandy(load_container_asset(container, "CHOOSE.ENC"),
                                             sprite_mode=False, emit_item_headers=True),
                           dtype=np.uint8)
    ok = True

    # 1) walked offsets vs the live loader table
    live = MutFlatMemory((SNAP / "memory_1mb.bin").read_bytes())
    _, _, live_ptrs = read_level_select_tables(live)
    walked = [o + CHOOSE_SEGMENT_BASE for o in walk_choose_cells(choose)]
    ptr_ok = walked == live_ptrs
    print(f"D37E pointers: walked={['%04X' % w for w in walked]}\n"
          f"               live  ={['%04X' % p for p in live_ptrs]} -> match={ptr_ok}")
    ok &= ptr_ok

    # 2) the xy tables: static bundle == live snapshot
    cold = MutFlatMemory(BUNDLE.read_bytes())
    cold_lx, cold_ox, _ = read_level_select_tables(cold)
    live_lx, live_ox, _ = read_level_select_tables(live)
    xy_ok = cold_lx == live_lx and cold_ox == live_ox
    print(f"xy tables static==live: {xy_ok}  level_xy={['%04X' % v for v in cold_lx]}")
    ok &= xy_ok

    # 3) the compose stamps at the exact 5A00 positions
    levscr = decode_fullscreen_image(container, "LEVSCR.ENC")
    offs = walk_choose_cells(choose)
    for beda in (0, 5):
        frame = compose_level_select(levscr, choose, cold_lx, cold_ox, beda, 0)
        cellpx = cell_indices(choose, offs[beda])
        x = (cold_lx[beda] & 0xFF) * 8
        y = (cold_lx[beda] >> 8) & 0xFF
        h, w = cellpx.shape
        stamp_ok = np.array_equal(frame[y:y + h, x:x + w], cellpx)
        print(f"cursor cell {beda} stamped at ({x},{y}) {w}x{h}: {stamp_ok}")
        ok &= stamp_ok

    # 4) cell k -> planet LEVEL_INDEX_TO_PLANET[k]
    for k in range(6):
        planet = advance_level_index_9744(resolve_level_select_fire_d424(k).level)
        expect = LEVEL_INDEX_TO_PLANET[k]
        if planet != expect:
            print(f"cell {k}: planet {planet} != LEVEL_INDEX_TO_PLANET[{k}]={expect}")
            ok = False
    print("cell->planet mapping (D424 + 9744 advance == LEVEL_INDEX_TO_PLANET):",
          all(advance_level_index_9744(resolve_level_select_fire_d424(k).level)
              == LEVEL_INDEX_TO_PLANET[k] for k in range(6)))

    print("RESULT:", "PASS -- the native level-select: CHOOSE cells match the loader table, the "
          "xy tables are static, the cursors stamp exactly, and cell k boots level k"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
