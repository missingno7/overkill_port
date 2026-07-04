"""Driven-oracle: the 9DEA A47C-script A95A/A95C advance vs the ORIGINAL 1010:9DEA.

Drives the original bytes with a synthetic ``(A95C, A95A, 98C0)``, stops at ``9DF8`` (no-op ret) or
``9EC2`` (the jmp target both active paths reach), and compares ``(A95C, A95A, BEFF)`` to
``systems.frame_loop.step_a47c_seq_9dea``.

Usage:
    python -m overkill.probes.verify_native_a47c_seq_9dea [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x9DEA
STOPS = {0x9DF8, 0x9EC2}
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"
# (A95C, A95A, 98C0): not-0x18 inc; 0x18 & A95A==3 advance (98C0 on/off); 0x18 & A95A!=3 no-op.
COMBOS = [(0x05, 0x03, 0), (0x17, 0x00, 1), (0x18, 0x03, 1), (0x18, 0x03, 0), (0x18, 0x02, 0), (0x18, 0x05, 1)]


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import step_a47c_seq_9dea

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(a95c, a95a, c0):
        m.ww(ds, 0xA95C, a95c & 0xFFFF)
        m.ww(ds, 0xA95A, a95a & 0xFFFF)
        m.ww(ds, 0x98C0, c0 & 0xFFFF)
        m.ww(ds, 0xBEFF, 0x0000)   # clear so a BEFF write is observable
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        for _ in range(2000):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) in STOPS:
                break
            cpu.step()
        return m.rw(ds, 0xA95C) & 0xFFFF, m.rw(ds, 0xA95A) & 0xFFFF, m.rw(ds, 0xBEFF) & 0xFFFF

    fails = []
    for a95c, a95a, c0 in COMBOS:
        vm = drive(a95c, a95a, c0)
        new_a95c, new_a95a, beff = step_a47c_seq_9dea(a95c, a95a, c0)
        mine = (new_a95c, new_a95a, beff if beff is not None else 0x0000)
        if mine != vm:
            fails.append(((a95c, a95a, c0), tuple(hex(x) for x in mine), tuple(hex(x) for x in vm)))

    print(f"9DEA death-seq advance driven-oracle: combos={len(COMBOS)} fails={len(fails)}")
    for f in fails:
        print("  FAIL in=", f[0], "mine=", f[1], "vm=", f[2])
    ok = not fails
    print("RESULT:", "PASS -- step_a47c_seq_9dea matches the original 9DEA on every branch"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
