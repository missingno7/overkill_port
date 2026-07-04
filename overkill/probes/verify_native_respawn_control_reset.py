"""Driven-oracle + completeness: the respawn control re-init vs the ORIGINAL 1010:C461..C4AD.

Drives the respawn / level-start control reset (the C3A6 tail) and asserts
``systems.frame_loop.respawn_control_reset_c461`` is CORRECT (every predicted cell matches) AND COMPLETE
(the block writes no other DGROUP words, excluding stack churn).

Usage:
    python -m overkill.probes.verify_native_respawn_control_reset [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xC461
STOP = 0xC4B3   # the call 9DB9 -- right after the control reset
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import respawn_control_reset_c461

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    model = respawn_control_reset_c461()
    for off in model:  # sentinel so a missed write shows
        m.ww(ds, off, 0xDEAD if model[off] != 0xDEAD else 0x1234)

    before = bytes(m.rb(ds, o) for o in range(0x10000))
    s.cs, s.ip = CS, ENTRY
    sp0 = s.sp & 0xFFFF
    msp = sp0
    for _ in range(20000):
        if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == STOP:
            break
        cpu.step()
        if (s.sp & 0xFFFF) < msp:
            msp = s.sp & 0xFFFF
    reached = (s.ip & 0xFFFF) == STOP
    after = bytes(m.rb(ds, o) for o in range(0x10000))

    wrong = [(o, v, m.rw(ds, o) & 0xFFFF) for o, v in model.items() if (m.rw(ds, o) & 0xFFFF) != v]
    modeled = set()
    for o in model:
        modeled |= {o, o + 1}
    unexpected = sorted(o for o in range(0, 0x10000)
                        if before[o] != after[o] and o not in modeled and not (msp - 2 <= o < sp0))

    for o, w, g in wrong[:8]:
        print(f"  WRONG {o:04X}: want {w:04X} got {g:04X}")
    for o in unexpected[:8]:
        print(f"  UNEXPECTED write at {o:04X} -> {m.rw(ds, o) & 0xFFFF:04X}")

    print(f"C461 respawn control reset: model={len(model)} wrong={len(wrong)} "
          f"unexpected={len(unexpected)} reached_stop={reached}")
    ok = reached and not wrong and not unexpected
    print("RESULT:", "PASS -- respawn_control_reset_c461 is correct AND complete vs the VM"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
