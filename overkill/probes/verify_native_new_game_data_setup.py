"""Driven-oracle + boundary: the composed new-game DATA setup vs the ORIGINAL 1010:9720..9748.

Drives the whole new-game/level-start data range (C4DB seed -> A95A/A95C init -> 6176 panel draw ->
level advance) and proves ``systems.frame_loop.native_new_game_data_setup``:
  1. CORRECT -- every data cell it predicts holds the right value after the drive.
  2. BOUNDED  -- the only DGROUP words the range changes that are NOT in the data model are exactly the
     documented render-glue cells (NEW_GAME_SETUP_RENDER_CELLS, written by the 6176 panel draw) plus
     stack churn -- so the data model misses no game-data write.

Usage:
    python -m overkill.probes.verify_native_new_game_data_setup [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x9720   # the C4DB call site (start of the new-game data setup)
STOP = 0x9748    # just after the level-advance wrap check
SEED_LEVEL = 0x0002
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import (
        OBJECT_SEED_SLOT_TABLE_32CA, OBJECT_SEED_COUNT, NEW_GAME_SETUP_RENDER_CELLS,
        native_new_game_data_setup,
    )
    from overkill.recovered.systems.menu import advance_level_index_9744

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    m.ww(ds, 0x2356, SEED_LEVEL)
    table = {cx: m.rw(ds, (OBJECT_SEED_SLOT_TABLE_32CA + cx * 2) & 0xFFFF) & 0xFFFF
             for cx in range(1, OBJECT_SEED_COUNT + 1)}
    model = native_new_game_data_setup(advance_level_index_9744(SEED_LEVEL), table)

    before = bytes(m.rb(ds, off) for off in range(0x10000))
    s.cs, s.ip = CS, ENTRY
    sp_entry = s.sp & 0xFFFF
    min_sp = sp_entry
    for _ in range(4_000_000):
        if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == STOP:
            break
        cpu.step()
        if (s.sp & 0xFFFF) < min_sp:
            min_sp = s.sp & 0xFFFF
    reached = (s.ip & 0xFFFF) == STOP
    after = bytes(m.rb(ds, off) for off in range(0x10000))

    def in_stack(off):
        return (min_sp - 2) <= off < sp_entry

    changed = {}
    for off in range(0, 0x10000, 2):
        b = before[off] | before[off + 1] << 8
        a = after[off] | after[off + 1] << 8
        if b != a and not in_stack(off):
            changed[off] = a

    # 1. correctness: every data-model cell holds its predicted value
    wrong = [(o, v, m.rw(ds, o) & 0xFFFF) for o, v in model.items() if (m.rw(ds, o) & 0xFFFF) != v]
    # 2. boundary: changed words not in the model must be exactly the documented render cells
    render = set(NEW_GAME_SETUP_RENDER_CELLS)
    unexpected = sorted(o for o in changed if o not in model and o not in render)
    # render cells the probe expected to see change but didn't (keep the boundary list honest/tight)
    render_not_seen = sorted(o for o in render if o not in changed)

    for o, w, g in wrong[:8]:
        print(f"  WRONG {o:04X}: model {w:04X} got {g:04X}")
    for o in unexpected[:8]:
        print(f"  UNEXPECTED (unmodelled) {o:04X} -> {changed[o]:04X}")
    for o in render_not_seen:
        print(f"  render cell {o:04X} declared but did not change (tighten the boundary list)")

    print(f"9720..9748 new-game data setup: model={len(model)} wrong={len(wrong)} "
          f"unexpected={len(unexpected)} render_not_seen={len(render_not_seen)} reached_stop={reached}")
    ok = reached and not wrong and not unexpected and not render_not_seen
    print("RESULT:", "PASS -- native_new_game_data_setup matches the VM (data exact; render-glue boundary tight)"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
