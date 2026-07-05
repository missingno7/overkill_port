"""Driven-oracle: the 62F6 shot-kills-enemy chain in the walk vs the ORIGINAL, one frame, full diff.

Plants a SOLID player shot (the A4EA seed: +1E=1, logic 2, type 2) in the gameplay pool directly on
a live enemy's 8px cell, then shadows ONE whole walk frame (A9D3..AA25) exactly like
verify_native_behavior_walk: VM runs the original, the native walk runs on the pre-state copy, and
the ENTIRE 64K DGROUP is diffed (stack window + documented steer scratch excluded).  Cases: the shot
ON an enemy (the hit chain: BF25 damage / BFC7 death + the candidate's fate), the shot far away
(no interaction), and repeated hits to drive the enemy's counter to death.

Usage:
    python -m overkill.probes.verify_native_combat [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
WALK_ENTRY = 0xA9D3
WALK_END = 0xAA25
DGROUP = 0x25CC
GAMEPLAY_BASE = 0x2B5C
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"
EXCLUDED_CELLS = {0xA954, 0xA955, 0x230A, 0x230B, 0x230E, 0x230F, 0x2310, 0x2311}
SHOT_SEED = {0x00: 1, 0x1E: 1, 0x06: 0, 0x08: 0x32, 0x14: 0, 0x16: 2, 0x18: 2, 0x1C: 0xFFFF}


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.adapters.behavior_walk import run_behavior_walk_a9d3
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.domain.tilemap import LevelTileContext
    from overkill.sounds.timing import deliver_overkill_timer_irq0

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem
    base = DGROUP * 16
    plane_seg = m.rw(CS, 0x9592)
    class_table = tuple(m.rb(ds, (0xC3AA + i) & 0xFFFF) for i in range(256))
    plane = bytes(m.data[plane_seg * 16:plane_seg * 16 + 0x4000])

    def step_to_walk_entry() -> None:
        budget = 4_000_000
        while budget:
            budget -= 1
            csr, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
            if csr == CS and ip == WALK_ENTRY:
                return
            if csr == CS and ip in (0x0679, 0x067F) and m.rb(CS, 0x066B) == 0:
                deliver_overkill_timer_irq0(cpu)
                continue
            if csr == CS and ip in (0x9921, 0x9926) and m.rb(ds, 0xBEFE) != 0:
                deliver_overkill_timer_irq0(cpu)
                continue
            cpu.step()
        raise RuntimeError("never reached the walk entry")

    def first_walked(behavior: int):
        # the walk visits the effect pool HIGH cx -> LOW, so the FIRST record scanned wins the hit
        for cx in range(0x23, 0, -1):
            rec = m.rw(ds, (0x32CA + cx * 2) & 0xFFFF)
            if rec and m.rw(ds, rec) and m.rw(ds, rec + 0x18) == behavior:
                return rec
        raise RuntimeError(f"no live behavior-{behavior:#x} record")

    def plant_shot(slot_index: int, x: int, y: int) -> None:
        rec = GAMEPLAY_BASE + slot_index * 0x38
        for off in range(0, 0x38, 2):
            m.ww(ds, rec + off, 0)
        for off, val in SHOT_SEED.items():
            m.ww(ds, rec + off, val)
        m.ww(ds, rec + 0x02, x)
        m.ww(ds, rec + 0x04, y)

    fails = 0
    labels = ("shot ON enemy (kill)", "shot far away (no hit)", "shot on controller (survive)")
    for case in range(3):
        step_to_walk_entry()
        if case == 2:
            # the wave controller (hp 14h) SURVIVES one hit -> the BF25 survival tail.  Its cell
            # +8 in x keeps the stacked 0x20 enemies (one cell left) out of the footprint.
            target = first_walked(0x1F)
            tx, ty = m.rw(ds, target + 0x02), m.rw(ds, target + 0x04)
            plant_shot(3, (tx & 0xFFF8) + 8, ty)
        else:
            target = first_walked(0x20)
            tx, ty = m.rw(ds, target + 0x02), m.rw(ds, target + 0x04)
            if case == 0:
                plant_shot(3, tx, ty)
            else:
                plant_shot(3, (tx + 0x60) & 0xFFF0, (ty + 0x40) & 0xFFF0)
        hp_before = m.rw(ds, target + 0x20)
        pre = bytes(m.data)
        sp_entry = s.sp & 0xFFFF
        budget = 3_000_000
        while not ((s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == WALK_END):
            cpu.step()
            budget -= 1
            if budget <= 0:
                raise RuntimeError("walk did not reach AA25")
        native = MutFlatMemory(pre)
        tiles = LevelTileContext(origin_x_word=native.rw(ds, 0x234E),
                                 row_base_word=native.rw(ds, 0x2350),
                                 tile_plane=plane, class_table=class_table)
        run_behavior_walk_a9d3(native, tiles)
        vm_bytes = bytes(m.data[base:base + 0x10000])
        nat_bytes = bytes(native.data[base:base + 0x10000])
        diffs = [o for o in range(0x10000)
                 if vm_bytes[o] != nat_bytes[o] and o not in EXCLUDED_CELLS
                 and not (sp_entry - 0x60 <= o < sp_entry)]
        hp = m.rw(ds, target + 0x20)
        beh = m.rw(ds, target + 0x18)
        hit_react = m.rw(ds, target + 0x24)
        shot_active = m.rw(ds, GAMEPLAY_BASE + 3 * 0x38)
        # the chain must actually FIRE: case 0 kills the target, case 1 leaves it whole,
        # case 2 damages-but-not-kills and stamps the +24h hit-react
        fired_ok = (beh == 1 and hp == 0 and shot_active == 0) if case == 0 else \
                   (hp == hp_before and beh != 1) if case == 1 else \
                   (0 < hp < hp_before and hit_react == 5 and shot_active == 0)
        ok = not diffs and fired_ok
        fails += not ok
        print(f"  {labels[case]:30s} {'ok' if ok else 'FAIL'}"
              f"  [vm after: hp={hp_before}->{hp} beh={beh:#x} react24={hit_react} shot={shot_active}]"
              + ("" if not diffs else f"  {len(diffs)}B first DS:{diffs[0]:04X}"
                                      f" vm={vm_bytes[diffs[0]]:02X} nat={nat_bytes[diffs[0]]:02X}"))

    print(f"combat chain: 3 cases, fails={fails}")
    print("RESULT:", "PASS -- the walk's 62F6/BEC5/BF25/BFC7 combat chain matches the original"
          if fails == 0 else "CHECK")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
