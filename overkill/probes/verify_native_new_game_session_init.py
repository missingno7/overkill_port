"""Driven-oracle + completeness: the session-start init vs the ORIGINAL 1010:96EE..9715.

Drives the pure ``mov`` block that starts a fresh game session (planet 0, lives 3, score 0, game-over
flag clear) and asserts ``systems.frame_loop.new_game_session_init_96ee`` is CORRECT (every predicted
cell matches) AND COMPLETE (the block writes no other DGROUP words, excluding stack churn).

Usage:
    python -m overkill.probes.verify_native_new_game_session_init [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x96EE
STOP = 0x971A
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import new_game_session_init_96ee

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    model = new_game_session_init_96ee()
    for off in model:  # sentinel so a missed write shows up
        m.ww(ds, off, 0xDEAD)

    before = bytes(m.rb(ds, o) for o in range(0x10000))
    s.cs, s.ip = CS, ENTRY
    sp0 = s.sp & 0xFFFF
    msp = sp0
    for _ in range(2000):
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

    for o, w, g in wrong:
        print(f"  WRONG {o:04X}: want {w:04X} got {g:04X}")
    for o in unexpected[:8]:
        print(f"  UNEXPECTED write at {o:04X}")

    print(f"96EE session init: model={len(model)} wrong={len(wrong)} unexpected={len(unexpected)} "
          f"reached_stop={reached}")
    ok = reached and not wrong and not unexpected
    print("RESULT:", "PASS -- new_game_session_init_96ee is correct AND complete vs the VM"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
