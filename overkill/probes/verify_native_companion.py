"""Driven-oracle: the type-6 companion handler vs the ORIGINAL 1010:AB10.

Drives AB10 with a synthetic companion record across: both hide gates (2384 / A47C), every
divider value 0..7, and several anchor positions/sprites -- comparing the record's +0/+2/+4/+8
against ``systems/companion.step_companion_ab10`` fed by the live A40C/A414 tables.

Usage:
    python -m overkill.probes.verify_native_companion [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
SENTINEL_IP = 0xFFFE
SCRATCH_SP = 0xFF00
RECORD = 0x23EC
ANCHOR = 0x237C
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.companion import step_companion_ab10

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    anim_table = tuple(m.rb(ds, (0xA40C + i) & 0xFFFF) for i in range(8))

    def offset_pair_at(sprite: int):
        base = (0xA414 + sprite * 4) & 0xFFFF
        return m.rw(ds, base), m.rw(ds, (base + 2) & 0xFFFF)

    def run() -> None:
        m.ww(ds, SCRATCH_SP, SENTINEL_IP)
        s.sp = SCRATCH_SP
        s.cs, s.ip, s.bp = CS, 0xAB10, RECORD
        for _ in range(2000):
            if (s.ip & 0xFFFF) == SENTINEL_IP:
                return
            cpu.step()
        raise RuntimeError("AB10 did not return")

    # NOTE: DS:2384 is NOT set separately -- it IS the anchor record's +0x08 sprite field
    # (0x237C + 8 = 0x2384; the first probe version set both and the oracle caught the aliasing)
    fails = cases = 0
    for a47c in (0, 2, 3):
        for div in range(8):
            for ax_pos, ay_pos, aspr in ((0xC0, 0x58, 0), (0x30, 0x90, 1), (0x88, 0x20, 2),
                                         (0x60, 0x40, 3), (0x60, 0x40, 4)):
                cases += 1
                m.ww(ds, RECORD + 0x00, 1)
                m.ww(ds, RECORD + 0x02, 0x1111)
                m.ww(ds, RECORD + 0x04, 0x2222)
                m.ww(ds, RECORD + 0x08, 0x3333)
                m.ww(ds, RECORD + 0x16, 6)
                m.ww(ds, 0xA47C, a47c)
                m.ww(ds, 0x2336, div)
                m.ww(ds, ANCHOR + 0x02, ax_pos)
                m.ww(ds, ANCHOR + 0x04, ay_pos)
                m.ww(ds, ANCHOR + 0x08, aspr)
                run()
                vm = (m.rw(ds, RECORD), m.rw(ds, RECORD + 2), m.rw(ds, RECORD + 4),
                      m.rw(ds, RECORD + 8))
                r = step_companion_ab10(scripted_a47c=a47c, divider_2336=div,
                                        anchor_x=ax_pos, anchor_y=ay_pos, anchor_sprite=aspr,
                                        anim_table=anim_table, offset_pair_at=offset_pair_at)
                mine = (0, 0x1111, 0x2222, 0x3333) if r.deactivate else \
                    (1, r.x_word, r.y_word, r.sprite)
                ok = vm == mine
                fails += not ok
                if not ok and fails <= 10:
                    print(f"  FAIL A47C={a47c} div={div} anchor=({ax_pos:02X},"
                          f"{ay_pos:02X},spr{aspr}): vm={vm} mine={mine}")

    print(f"companion AB10: {cases} cases, fails={fails}")
    print("RESULT:", "PASS -- step_companion_ab10 matches the original AB10"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
