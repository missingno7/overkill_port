"""Fast iteration loop over the 7 death/respawn windows -- the lockstep gate's whole residue.

The full gate replays 8292 frames (~1 min cached, ~8 min recording).  While building the death
continuation only 7 windows can change, so this replays just those and prints the diverging-byte
count per window with a region breakdown: a ~16-second edit/measure cycle.

It is a DIAGNOSTIC, not a gate -- a byte count going down is evidence, not proof.  The proof is
`verify_native_lockstep` reporting those frames byte-exact.  Land nothing on this probe alone.

Baseline when the death continuation is unimplemented (the native frame returns at the 97CE exit):

    frame  4636 (  7 ticks):  5337 B      frame  5379 (402 ticks):  3717 B
    frame  4821 (  0 ticks):  3506 B      frame  6495 (402 ticks):   426 B
    frame  5018 (  0 ticks):  4048 B      frame  7143 (402 ticks):   417 B
                                          frame  7595 (402 ticks):   388 B
    TOTAL: 17839 B

The 402-tick windows are the ones that spin at 9921 (`cmp byte [BEFE],0 / jnz`) waiting for the
death jingle to drain -- hundreds of timer interrupts land inside the frame.

Usage:
    pypy -m overkill.probes.inspect_death_windows [frame_to_dump_cells_for]
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.native_frame import advance_gameplay_frame_97b2  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402
from overkill.probes._shadow_cache import demo_key, iter_cached_frames, load_cache  # noqa: E402
from overkill.probes.verify_native_lockstep import (  # noqa: E402
    DGROUP, EXCLUDED_CELLS, GAME_OVER_MENU_PICK, level_assets_for, lockstep_cache_path,
)
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_full_20260705_123645"
CACHE_BUDGET = 20000
#: the 9B2E windows in which the player dies and the level re-inits (cold-start demo)
DEATH_WINDOWS = (4636, 4821, 5018, 5379, 6495, 7143, 7595)

REGIONS = (
    (0x0000, 0x0100, "zero page/[0054]"), (0x2060, 0x2100, "script scratch"),
    (0x2100, 0x2300, "21xx-22xx"), (0x2300, 0x2360, "scroll/clock 23xx"),
    (0x2360, 0x2400, "player+pool head"), (0x2400, 0x3300, "object pools"),
    (0x3300, 0x9600, "save buffers/tables"), (0x9600, 0xA300, "98xx counters"),
    (0xA300, 0xA400, "A3xx flags"), (0xA400, 0xA900, "wave/controller"),
    (0xA900, 0xBE00, "A9xx-BDxx"), (0xBE00, 0xC000, "sound BExx/BFxx"),
    (0xC000, 0x10000, "Cxxx+"),
)


def _region(off: int) -> str:
    for lo, hi, name in REGIONS:
        if lo <= off < hi:
            return name
    return "?"


def main(argv) -> int:
    dump = int(argv[0]) if argv else 0
    demo = load_demo(None, DEFAULT_DEMO)
    cached = load_cache(lockstep_cache_path(demo), demo_key(demo), CACHE_BUDGET)
    if cached is None:
        print(f'cache miss -- record it: pypy -m overkill.probes.verify_native_lockstep "" '
              f'{CACHE_BUDGET}')
        return 1
    base = DGROUP * 16
    total = 0
    for n, (pre, post, sp, ticks) in enumerate(iter_cached_frames(cached), start=1):
        if n not in DEATH_WINDOWS:
            continue
        native = MutFlatMemory(pre)
        try:
            advance_gameplay_frame_97b2(native, isr_ticks=ticks,
                                        level_assets=level_assets_for,
                                        menu_pick=GAME_OVER_MENU_PICK)
        except RecoveryGap as gap:
            print(f"frame {n:5d}: GAP {gap}")
            continue
        nat = bytes(native.data[base:base + 0x10000])
        diffs = [o for o in range(0x10000)
                 if nat[o] != post[o] and o not in EXCLUDED_CELLS and not (sp - 0x60 <= o < sp)]
        total += len(diffs)
        counts = Counter(_region(o) for o in diffs)
        summary = ", ".join(f"{k}={v}" for k, v in counts.most_common(5))
        print(f"frame {n:5d} ({ticks:3d} ticks): {len(diffs):5d} B  {summary}")
        if n == dump:
            for off in diffs[:60]:
                print(f"    DS:{off:04X} pre={pre[base + off]:02X} vm={post[off]:02X} "
                      f"nat={nat[off]:02X}")
    print(f"\nTOTAL diverging bytes across the {len(DEATH_WINDOWS)} death windows: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
