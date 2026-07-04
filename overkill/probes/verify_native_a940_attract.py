"""Driven-oracle: the native A940 attract-mode counter block vs the ORIGINAL 1010:A940 (DS:2356 == 5).

No gameplay demo runs 97B2/A940 with ``DS:2356 == 5`` (that's the in-game demo-playback mode), so this
witnesses the attract middle by DRIVING the original bytes: on a snapshot, clear the hooks, force
``DS:2356 = 5`` + a synthetic ``(98A2, 98AA, 98A5, 98A3, A47E)``, run A940 from entry to its ``A9E0``
exit, and compare the five attract cells the original wrote to
``systems.frame_loop.step_a940_attract_middle``.  Exercises every branch (98A2 zero/non-zero; 98A5
0 / 1 / >1; each A47E speed bucket).

Usage:
    python -m overkill.probes.verify_native_a940_attract [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
A940 = 0xA940
A940_DONE = 0xA9E0
RET = 0xFFFF
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L3_full_20260617_202520/snapshot"

# (98A2, 98AA, 98A5, 98A3, A47E) input combos exercising every branch.
COMBOS = [
    (0x00, 0x0005, 0x00, 0x10, 0x40),   # 98A2==0, 98A5==0
    (0x01, 0x0005, 0x00, 0x10, 0x40),   # 98A2!=0 -> negate 98AA, 98A4=1
    (0x00, 0x1234, 0x01, 0x7F, 0x40),   # 98A5==1 -> reload bucket 0x0A (A47E>0x10)
    (0x00, 0x1234, 0x01, 0xFF, 0x10),   # 98A5==1 -> bucket 0x06 (A47E<=0x10); 98A3 wraps
    (0x00, 0x1234, 0x01, 0x00, 0x08),   # bucket 0x04
    (0x00, 0x1234, 0x01, 0x00, 0x04),   # bucket 0x01
    (0x00, 0x1234, 0x05, 0x00, 0x40),   # 98A5>1 -> 0
    (0x02, 0x8000, 0x03, 0x20, 0x02),   # 98A2!=0 + 98A5>1
]


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import step_a940_attract_middle

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(a98a2, a98aa, a98a5, a98a3, a47e):
        m.wb(ds, 0x98A2, a98a2 & 0xFF)
        m.ww(ds, 0x98AA, a98aa & 0xFFFF)
        m.wb(ds, 0x98A5, a98a5 & 0xFF)
        m.wb(ds, 0x98A3, a98a3 & 0xFF)
        m.ww(ds, 0xA47E, a47e & 0xFFFF)
        m.ww(ds, 0x2356, 0x0005)
        s = cpu.s
        s.cs = CS
        sp = (s.sp - 2) & 0xFFFF
        m.ww(s.ss & 0xFFFF, sp, RET)
        s.sp = sp
        s.ip = A940
        for _ in range(200000):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == A940_DONE:
                break
            cpu.step()
        return (m.rb(ds, 0x98A2), m.rb(ds, 0x98A4), m.rw(ds, 0x98AA), m.rb(ds, 0x98A5), m.rb(ds, 0x98A3))

    fails = []
    for combo in COMBOS:
        vm = drive(*combo)
        mine = step_a940_attract_middle(*combo)
        if tuple(mine) != tuple(vm):
            fails.append((combo, mine, vm))

    print(f"A940 attract-middle driven-oracle: combos={len(COMBOS)} fails={len(fails)}")
    for f in fails:
        print("  FAIL in=", f[0], "mine=", tuple(hex(x) for x in f[1]), "vm=", tuple(hex(x) for x in f[2]))
    ok = not fails
    print("RESULT:", "PASS -- step_a940_attract_middle matches the original A940 (2356==5) on every branch"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
