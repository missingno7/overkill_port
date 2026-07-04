"""Driven-oracle + COMPLETENESS: the composed C4DB new-game setup vs the ORIGINAL 1010:C4DB..C559.

Proves two things about ``systems.frame_loop.apply_new_game_setup_c4db``:
  1. CORRECT -- every cell it predicts holds the right value after driving the whole C4DB routine.
  2. COMPLETE -- a full DGROUP before/after diff shows C4DB writes *exactly* the predicted set of DGROUP
     cells and no others (its only other write is the CS:C3A2 framebuffer accumulator, outside DGROUP),
     so the composition of the two recovered halves misses nothing.

Usage:
    python -m overkill.probes.verify_native_new_game_setup_c4db [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xC4DB
STOP = 0xC55F
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import (
        OBJECT_SEED_SLOT_TABLE_32CA, OBJECT_SEED_COUNT, apply_new_game_setup_c4db,
    )

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    table = {cx: m.rw(ds, (OBJECT_SEED_SLOT_TABLE_32CA + cx * 2) & 0xFFFF) & 0xFFFF
             for cx in range(1, OBJECT_SEED_COUNT + 1)}
    predicted = apply_new_game_setup_c4db(table)

    # snapshot the whole DGROUP before, drive the routine, snapshot after -> diff.
    # NOTE: SS == DS here, so the STACK lives in DGROUP too; the routine's push/pop/call churn stack
    # memory in [min_sp, sp_entry). That is not game state, so exclude that window from the diff.
    before = bytes(m.rb(ds, off) for off in range(0x10000))
    s.cs, s.ip = CS, ENTRY
    sp_entry = s.sp & 0xFFFF
    min_sp = sp_entry
    for _ in range(8000):
        if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == STOP:
            break
        cpu.step()
        if (s.sp & 0xFFFF) < min_sp:
            min_sp = s.sp & 0xFFFF
    reached = (s.ip & 0xFFFF) == STOP
    after = bytes(m.rb(ds, off) for off in range(0x10000))

    def in_stack(off: int) -> bool:
        # the stack grew down to min_sp; treat [min_sp - 2, sp_entry) as churn (a pushed word sits at sp)
        return (min_sp - 2) <= off < sp_entry

    # the set of WORD offsets that actually changed (collapse byte diffs to their word base)
    changed_words = set()
    for off in range(0x10000):
        if before[off] != after[off]:
            w = off if off % 2 == 0 else off - 1
            if not in_stack(w):
                changed_words.add(w)

    # 1. correctness: predicted cells hold predicted values
    wrong = [(o, v, m.rw(ds, o) & 0xFFFF) for o, v in predicted.items() if (m.rw(ds, o) & 0xFFFF) != v]
    # 2. completeness: every changed word is predicted (no missed writes)
    unexpected = sorted(w for w in changed_words if w not in predicted)

    for o, want, got in wrong[:8]:
        print(f"  WRONG {o:04X}: want {want:04X} got {got:04X}")
    for w in unexpected[:8]:
        print(f"  UNPREDICTED write at {w:04X} -> {m.rw(ds, w) & 0xFFFF:04X} (was {before[w] | before[w+1] << 8:04X})")

    print(f"C4DB new-game setup: predicted={len(predicted)} wrong={len(wrong)} "
          f"unpredicted_changes={len(unexpected)} reached_stop={reached}")
    ok = reached and not wrong and not unexpected
    print("RESULT:", "PASS -- apply_new_game_setup_c4db is correct AND complete vs the original C4DB"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
