"""Driven-oracle: the planet-keyed WAVE-DRIVER dispatch vs the ORIGINAL 1010:B556 (+ its leaves).

Four gates, all driven on the original bytes (hooks cleared):

1. ``B556`` dispatch matrix: drive with synthetic ``DS:2356`` (planet) x ``DS:A7A0`` (wave clock),
   observe which family entry is reached -- 8D83 (planet 4), B48B (planet 3 phase machine), B4A2
   (planet 0 leader group), B615 (per-planet), BC4B (pause), B58A (boss transform) -- and compare to
   ``systems.frame_loop.wave_driver_dispatch_b556``.
2. ``B58A`` boss transform: run it to the BC4B exit and compare the record's stamped fields to
   ``boss_transform_stamp_b58a``.
3. ``B468`` active-enemy count: run it on the PRISTINE snapshot pool and compare ``ax`` to
   ``count_active_enemies_b468`` over the same records (and to the live ``DS:A47E``).
4. The TYPE -> BEHAVIOR dispatch chain: drive ``AA2B`` with a synthetic record (``+0x16 = 4``,
   ``+0x18 = 0x21``) and check it lands at B556 via EFAE (pinning the ``shl 1`` + table-base
   semantics of both the AA36 and EFC4 tables), with the EFAE position mirror written.

Usage:
    python -m overkill.probes.verify_native_wave_driver_dispatch [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY_B556 = 0xB556
ENTRY_B468 = 0xB468
RET_B468 = 0xB48A
ENTRY_AA2B = 0xAA2B
TARGETS = {0x8D83: "planet4_family", 0xB48B: "phase_machine", 0xB4A2: "leader_group",
           0xB615: "per_planet", 0xBC4B: "none", 0xB58A: "boss_transform"}
SCRATCH_RECORD = 0x23EC  # effect-pool slot 1 -- a real record the driven bp can point at
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import (
        boss_transform_stamp_b58a,
        count_active_enemies_b468,
        wave_driver_dispatch_b556,
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

    # -- gate 3 FIRST: B468 on the PRISTINE pool (before any synthetic writes) --------------------
    records = []
    for i in range(35):
        rec = m.rw(ds, (0x32CA + (i + 1) * 2) & 0xFFFF)  # slot pointers 1..35 (index 0 unused)
        if rec:
            records.append((m.rw(ds, rec), m.rw(ds, (rec + 0x16) & 0xFFFF)))
    live_a47e = m.rw(ds, 0xA47E)
    s.cs, s.ip, s.bp = CS, ENTRY_B468, SCRATCH_RECORD
    for _ in range(3000):
        if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == RET_B468:
            break
        cpu.step()
    vm_count, mine_count = s.ax & 0xFFFF, count_active_enemies_b468(records)
    ok = vm_count == mine_count == live_a47e
    fails += not ok
    print(f"  B468 count: vm={vm_count} mine={mine_count} live_A47E={live_a47e} {'ok' if ok else 'FAIL'}")

    # -- gate 1: the B556 dispatch matrix ---------------------------------------------------------
    def drive(planet, a7a0, entry=ENTRY_B556):
        m.ww(ds, 0x2356, planet & 0xFFFF)
        m.ww(ds, 0xA7A0, a7a0 & 0xFFFF)
        s.cs, s.ip, s.bp = CS, entry, SCRATCH_RECORD
        for _ in range(300):
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip in TARGETS:
                return TARGETS[ip]
            cpu.step()
        return "?"

    for planet, a7a0 in ((4, 0x00), (3, 0x00), (3, 0x80), (0, 0x00), (0, 0xF0),
                         (1, 0x00), (1, 0xC7), (1, 0xC8), (1, 0xEF), (1, 0xF0),
                         (2, 0x40), (5, 0xFF)):
        vm = drive(planet, a7a0)
        mine = wave_driver_dispatch_b556(planet, a7a0)
        ok = vm == mine
        fails += not ok
        print(f"  B556 2356={planet} A7A0={a7a0:#04x}: vm={vm} mine={mine} {'ok' if ok else 'FAIL'}")

    # -- gate 2: the B58A boss-transform stamp ----------------------------------------------------
    planet = 1
    assert drive(planet, 0xF0) == "boss_transform"
    for _ in range(300):  # run the transform through to the BC4B exit
        if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == 0xBC4B:
            break
        cpu.step()
    stamp = boss_transform_stamp_b58a(planet)
    for off, want in sorted(stamp.items()):
        got = m.rw(ds, (SCRATCH_RECORD + off) & 0xFFFF)
        ok = got == want
        fails += not ok
        print(f"  B58A stamp +{off:02X}: vm={got:#06x} mine={want:#06x} {'ok' if ok else 'FAIL'}")

    # -- gate 4: the AA2B type -> EFAE behavior dispatch chain ------------------------------------
    m.ww(ds, (SCRATCH_RECORD + 0x16) & 0xFFFF, 0x0004)   # type 4 (enemy) -> EFAE
    m.ww(ds, (SCRATCH_RECORD + 0x18) & 0xFFFF, 0x0021)   # behavior 0x21 -> B556
    m.ww(ds, (SCRATCH_RECORD + 0x02) & 0xFFFF, 0x1234)
    m.ww(ds, (SCRATCH_RECORD + 0x04) & 0xFFFF, 0x5678)
    s.cs, s.ip, s.bp = CS, ENTRY_AA2B, SCRATCH_RECORD
    landed = "?"
    for _ in range(300):
        ip = s.ip & 0xFFFF
        if (s.cs & 0xFFFF) == CS and ip == ENTRY_B556:
            landed = "B556"
            break
        cpu.step()
    mirror_ok = m.rw(ds, 0xD1FE) == 0x5678 and m.rw(ds, 0xD200) == 0x1234
    ok = landed == "B556" and mirror_ok
    fails += not ok
    print(f"  AA2B type4/beh21 -> {landed}, EFAE mirror D1FE/D200 {'ok' if mirror_ok else 'FAIL'}"
          f" {'ok' if ok else 'FAIL'}")

    print(f"wave-driver dispatch: fails={fails}")
    print("RESULT:", "PASS -- wave_driver_dispatch_b556 + leaves match the original B556/B468/B58A/AA2B"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
