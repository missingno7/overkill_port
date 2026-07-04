"""Structural verify: the C4DB seed's record set == special view-anchor + the effect table.

Reads the real ``DS:0x32CA`` slot-pointer table and proves the C4DB object-pool seed covers exactly the
special view-anchor slot (:data:`POOL_BASE_SPECIAL`, 1) + the effect table (:data:`POOL_BASE_EFFECT`, 35
slots) as one contiguous 0x38-grid block, and that the gameplay/enemy table (:data:`POOL_BASE_GAMEPLAY`)
is NOT seeded and sits exactly one stride past the last seeded record.  Grounds the object-pool layout
the native level-start relies on.

Usage:
    python -m overkill.probes.verify_native_c4db_seed_pool_layout [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import (
        OBJECT_SEED_SLOT_TABLE_32CA, OBJECT_SEED_COUNT, OBJECT_RECORD_STRIDE,
        POOL_BASE_SPECIAL, POOL_BASE_EFFECT, POOL_BASE_GAMEPLAY, POOL_EFFECT_SLOTS,
    )

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    m = rt.cpu.mem
    ds = rt.cpu.s.ds & 0xFFFF

    table = {cx: m.rw(ds, (OBJECT_SEED_SLOT_TABLE_32CA + cx * 2) & 0xFFFF) & 0xFFFF
             for cx in range(1, OBJECT_SEED_COUNT + 1)}
    seeded = sorted(set(table.values()))

    expected = sorted({POOL_BASE_SPECIAL} |
                      {(POOL_BASE_EFFECT + k * OBJECT_RECORD_STRIDE) & 0xFFFF for k in range(POOL_EFFECT_SLOTS)})

    checks = {
        "36 distinct seeded records": len(seeded) == OBJECT_SEED_COUNT == 36,
        "seeded == special + effect table": seeded == expected,
        "contiguous 0x38 grid 0x237C..0x2B24":
            all((seeded[i + 1] - seeded[i]) == OBJECT_RECORD_STRIDE for i in range(len(seeded) - 1))
            and seeded[0] == POOL_BASE_SPECIAL and seeded[-1] == 0x2B24,
        "gameplay table NOT seeded": POOL_BASE_GAMEPLAY not in table.values(),
        "gameplay base == last seeded + stride": (max(seeded) + OBJECT_RECORD_STRIDE) & 0xFFFF == POOL_BASE_GAMEPLAY,
    }
    for name, ok in checks.items():
        print(f"  [{'ok' if ok else 'FAIL'}] {name}")

    ok = all(checks.values())
    print("RESULT:", "PASS -- C4DB seeds exactly {special} + {effect table}; gameplay table is separate"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
