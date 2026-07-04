"""Driven-oracle: the C3B5 gameplay object-pool seed vs the ORIGINAL 1010:C3B5..C3E5.

Reads the real ``DS:0x8D12`` slot-pointer table, prefills every seeded field with a sentinel, drives the
gameplay-pool seed loop (C3B5 -> C3E7), and asserts all 34 gameplay records hold exactly what
``systems.frame_loop.object_pool_seed_c3b5`` predicts (34 records x 4 fields).

Usage:
    python -m overkill.probes.verify_native_gameplay_pool_seed [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xC3B5
STOP = 0xC3E7
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"
FIELDS = (0x00, 0x0E, 0x18, 0x2E)


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import (
        GAMEPLAY_SEED_SLOT_TABLE_8D12, GAMEPLAY_SEED_COUNT, object_pool_seed_c3b5,
    )

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    m = cpu.mem

    table = {cx: m.rw(ds, (GAMEPLAY_SEED_SLOT_TABLE_8D12 + cx * 2) & 0xFFFF) & 0xFFFF
             for cx in range(1, GAMEPLAY_SEED_COUNT + 1)}
    expected = object_pool_seed_c3b5(table)

    for off, fields in expected.items():
        for fo in fields:
            m.ww(ss, (off + fo) & 0xFFFF, 0xDEAD)

    s.cs, s.ip = CS, ENTRY
    for _ in range(8000):
        if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == STOP:
            break
        cpu.step()
    reached = (s.ip & 0xFFFF) == STOP

    fails = 0
    checked = 0
    for off, fields in expected.items():
        for fo, want in fields.items():
            got = m.rw(ss, (off + fo) & 0xFFFF) & 0xFFFF
            checked += 1
            if got != want:
                fails += 1
                if fails <= 8:
                    print(f"  FAIL rec {off:04X}+{fo:02X}: want {want:04X} got {got:04X}")

    print(f"C3B5 gameplay-pool seed: records={len(expected)} fields={checked} fails={fails} "
          f"reached_stop={reached}")
    ok = reached and not fails and len(expected) == GAMEPLAY_SEED_COUNT
    print("RESULT:", "PASS -- object_pool_seed_c3b5 matches the original C3B5 gameplay seed"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
