"""Verify the cold image's PLANET-KEYED level data against fresh level-load snapshots.

``build_cold_level_start_image(bundle, level_index, container)`` must place the SAME bytes the
VM's own loader placed: the tile-map body at ``CS:[9592]``, the LEV{planet}BLX bank at
``CS:[959A]``, and the class table at ``DS:C3AA`` -- compared per level against the fresh-load
snapshot for that PLANET (the same fixtures tests/test_level_map_placement.py pins, which assert
``DS:2356 == planet``).  This is the gate for the level-data UNIFICATION (the play_native
wrong-planet bug: LEV{n} names are planet-keyed; the walk image previously kept the static
bundle's stale capture).

Usage:
    python -m overkill.probes.verify_native_cold_level_data
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CS = 0x1010
DS = 0x25CC
BODY = (12, 3682)
FRESH_SNAPSHOTS = {
    1: "demo_play_tandy_L1_start_20260618_143947",
    2: "demo_play_tandy_L2_full_20260617_180221",
    3: "demo_play_tandy_L3_full_20260617_202520",
    4: "demo_play_tandy_L4_full_20260618_185155",
    5: "demo_play_tandy_L5_start_20260618_185923",
    0: "demo_play_tandy_L6_begin_20260618_225537",
}


def main(argv) -> int:
    from overkill.asset_codecs.level_assets import decode_level_blocks
    from overkill.recovered.adapters.cold_level_start import (LEVEL_INDEX_TO_PLANET,
                                                              build_cold_level_start_image)

    bundle = (ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin").read_bytes()
    container = (ROOT / "assets" / "OVERKILL").read_bytes()
    ok = True
    checked = 0
    for idx in range(6):
        planet = LEVEL_INDEX_TO_PLANET[idx]
        snap = ROOT / "artifacts" / "demos" / FRESH_SNAPSHOTS[planet] / "snapshot" / "memory_1mb.bin"
        if not snap.is_file():
            print(f"level {idx} (planet {planet}): no snapshot -- skipped")
            continue
        vm = snap.read_bytes()
        assert struct.unpack_from("<H", vm, DS * 16 + 0x2356)[0] == planet
        img = build_cold_level_start_image(bundle, idx, container)

        def rw(off):
            a = CS * 16 + off
            return vm[a] | (vm[a + 1] << 8)

        plane_ok = (bytes(img.data[img.rw(CS, 0x9592) * 16 + BODY[0]:
                                   img.rw(CS, 0x9592) * 16 + BODY[1]])
                    == vm[rw(0x9592) * 16 + BODY[0]: rw(0x9592) * 16 + BODY[1]])
        blocks = decode_level_blocks(container, planet)
        bank_ok = (bytes(img.data[img.rw(CS, 0x959A) * 16:
                                  img.rw(CS, 0x959A) * 16 + len(blocks)])
                   == vm[rw(0x959A) * 16: rw(0x959A) * 16 + len(blocks)])
        cls_ok = (bytes(img.data[DS * 16 + 0xC3AA: DS * 16 + 0xC3AA + 256])
                  == vm[DS * 16 + 0xC3AA: DS * 16 + 0xC3AA + 256])
        print(f"level {idx} (planet {planet}): plane-body={'OK' if plane_ok else 'DIFF'} "
              f"bank={'OK' if bank_ok else 'DIFF'} classes={'OK' if cls_ok else 'DIFF'}")
        ok &= plane_ok and bank_ok and cls_ok
        checked += 1
    print("RESULT:", f"PASS -- the cold image carries the PLANET's own level data ({checked} levels)"
          if ok and checked else "FAIL")
    return 0 if ok and checked else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
