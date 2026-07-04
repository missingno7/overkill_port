"""Driven-oracle: STAGE 1 of death -- the native A95A anchor-loss countdown vs the ORIGINAL 1010:9E69.

The countdown only runs in a specific mode over many frames, so this witnesses it by DRIVING the
original bytes: on a snapshot, clear the hooks, set a synthetic ``(A47C, 2384, A362, A95A)``, run from
``9E69`` and stop at the first ret (``9E70``/``9E78``/``9E97``) or at ``9E9C`` (right after the A95A
decrement, BEFORE the entangled death-path 61DC/511F side effects), and compare the resulting
``(A362, A95A)`` to ``systems.frame_loop.step_death_countdown_9e69``.  Exercises every branch incl. the
``A95A: 0 -> FFFF`` anchor-loss.

Usage:
    python -m overkill.probes.verify_native_death_countdown [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x9E69
STOPS = {0x9E70, 0x9E78, 0x9E97, 0x9E9C}   # rets + the post-decrement point (before the death path)
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"

# (A47C, 2384, A362, A95A) combos exercising every branch.
COMBOS = [
    (0x01, 0x00, 0x00, 0x0003),   # A47C == 1 -> gated off (ret 9E70), no change
    (0x00, 0x03, 0x00, 0x0003),   # 2384 >= 3 -> gated off (ret 9E78)
    (0x00, 0x05, 0x01, 0x0003),   # 2384 >= 3 -> gated off
    (0x00, 0x00, 0x00, 0x0003),   # armed, A362 0 -> toggles to 1, no dec (ret 9E97)
    (0x00, 0x02, 0x01, 0x0003),   # armed, A362 1 -> toggles to 0, DEC A95A (3 -> 2)
    (0x00, 0x00, 0x01, 0x0001),   # dec A95A 1 -> 0
    (0x00, 0x00, 0x01, 0x0000),   # dec A95A 0 -> FFFF (ANCHOR LOST)
    (0x04, 0x01, 0x01, 0x0002),   # A47C != 1, armed, A362 1 -> dec 2 -> 1
]


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import step_death_countdown_9e69

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(a47c, c2384, a362, a95a):
        m.ww(ds, 0xA47C, a47c & 0xFFFF)
        m.ww(ds, 0x2384, c2384 & 0xFFFF)
        m.ww(ds, 0xA362, a362 & 0xFFFF)
        m.ww(ds, 0xA95A, a95a & 0xFFFF)
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        for _ in range(2000):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) in STOPS:
                break
            cpu.step()
        return m.rw(ds, 0xA362) & 0x01, m.rw(ds, 0xA95A) & 0xFFFF

    fails = []
    for combo in COMBOS:
        vm_a362, vm_a95a = drive(*combo)
        mine_a362, mine_a95a, _ = step_death_countdown_9e69(*combo)
        if (mine_a362 & 0x01, mine_a95a) != (vm_a362, vm_a95a):
            fails.append((combo, (mine_a362, mine_a95a), (vm_a362, vm_a95a)))

    print(f"death-countdown (9E69) driven-oracle: combos={len(COMBOS)} fails={len(fails)}")
    for f in fails:
        print("  FAIL in=", f[0], "mine=", tuple(hex(x) for x in f[1]), "vm=", tuple(hex(x) for x in f[2]))
    ok = not fails
    print("RESULT:", "PASS -- step_death_countdown_9e69 matches the original 9E69 on every branch"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
