"""Driven-oracle: the 4D95 canned-random step + the 7476 enemy-shot spawn vs the original bytes.

1. ``4D95``: drive it 40 times from the live cursor (more than one full wrap of the 16-word ring),
   comparing every returned value + cursor against ``canned_random_next_4d95`` over the cold-loaded
   ring (``load_canned_random_ring``).
2. ``7476``: with a synthetic shooter record and a cleared gameplay pool (deterministic ``7573``
   alloc), drive the spawn for both muzzle variants (``DS:A8C2`` 0/1) and several shooter/player
   positions; compare the allocated record's full stamp (incl. the ``74E2`` aim deltas) against
   ``enemy_shot_stamp_7476``, plus the ``DS:BEFF`` sound queue under both ``DS:98C0`` gate states.

Usage:
    python -m overkill.probes.verify_native_enemy_shot [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
SENTINEL_IP = 0xFFFE
SCRATCH_SP = 0xFE40
SHOOTER_RECORD = 0x23EC          # effect slot 1 -- bp for the drive
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"
STAMP_OFFSETS = (0x00, 0x02, 0x04, 0x06, 0x08, 0x0A, 0x14, 0x16, 0x18, 0x1C, 0x1E, 0x2A, 0x2C)


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.adapters.canned_random_adapter import load_canned_random_ring
    from overkill.recovered.systems.frame_loop import (
        canned_random_next_4d95,
        enemy_shot_stamp_7476,
    )

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem
    fails = 0

    def run_to_sentinel(entry: int, max_steps: int = 5000) -> None:
        m.ww(ds, SCRATCH_SP, SENTINEL_IP)
        s.sp = SCRATCH_SP
        s.cs, s.ip, s.bp = CS, entry, SHOOTER_RECORD
        for _ in range(max_steps):
            if (s.ip & 0xFFFF) == SENTINEL_IP:
                return
            cpu.step()
        raise RuntimeError(f"drive of {entry:04X} did not return")

    # -- gate 1: 4D95 across a full ring wrap ----------------------------------------------------
    ring = load_canned_random_ring(bytes(m.data))
    cursor = m.rw(ds, 0x20A6)
    bad = 0
    for _ in range(40):
        run_to_sentinel(0x4D95)
        vm_val, vm_cursor = s.bx & 0xFFFF, m.rw(ds, 0x20A6)
        my_val, cursor = canned_random_next_4d95(cursor, ring)
        bad += (vm_val, vm_cursor) != (my_val, cursor)
    fails += bad
    print(f"  4D95 canned random: 40 steps (full wrap), mismatches={bad}")

    # -- gate 2: the 7476 enemy-shot spawn --------------------------------------------------------
    # clear the gameplay pool so 7573 allocates slot 1 deterministically each time
    def clear_gameplay_pool():
        for cx in range(1, 0x23):
            rec = m.rw(ds, (0x8D12 + cx * 2) & 0xFFFF)
            if rec:
                m.ww(ds, rec, 0)

    shot_cases = 0
    for sx, sy in ((0x40, 0x30), (0x88, 0x77)):
        for a8c2 in (0, 1):
            for gate_98c0 in (0, 1):
                shot_cases += 1
                clear_gameplay_pool()
                m.ww(ds, SHOOTER_RECORD + 0x02, sx)
                m.ww(ds, SHOOTER_RECORD + 0x04, sy)
                m.ww(ds, 0xA8C2, a8c2)
                m.wb(ds, 0x98C0, gate_98c0)
                m.wb(ds, 0xBEFF, 0)
                px, py = m.rw(ds, 0x237E), m.rw(ds, 0x2380)
                run_to_sentinel(0x7476)
                slot = next((m.rw(ds, (0x8D12 + cx * 2) & 0xFFFF) for cx in range(1, 0x23)
                             if m.rw(ds, m.rw(ds, (0x8D12 + cx * 2) & 0xFFFF)) != 0), None)
                if slot is None:
                    fails += 1
                    print(f"  7476 FAIL: no shot allocated (sx={sx:02X} a8c2={a8c2})")
                    continue
                stamp = enemy_shot_stamp_7476(sx, sy, bool(a8c2), px, py)
                got = {off: m.rw(ds, (slot + off) & 0xFFFF) for off in STAMP_OFFSETS}
                want = {off: stamp[off] & 0xFFFF for off in STAMP_OFFSETS}
                sound_ok = m.rb(ds, 0xBEFF) == (0x1A if gate_98c0 else 0)
                ok = got == want and sound_ok
                fails += not ok
                if not ok:
                    diff = {o: (got[o], want[o]) for o in STAMP_OFFSETS if got[o] != want[o]}
                    print(f"  7476 FAIL sx={sx:02X} sy={sy:02X} a8c2={a8c2} 98c0={gate_98c0}: "
                          f"diff={diff} sound_ok={sound_ok}")
    print(f"  7476 enemy shot: {shot_cases} cases")

    print(f"enemy shot leaves: fails={fails}")
    print("RESULT:", "PASS -- 4D95 + 7476 match the original bytes"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
