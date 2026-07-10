"""FREE-RUN gate: does the native frame stay on the original's trajectory, unaided, for a whole demo?

This answers a question ``verify_native_lockstep`` structurally cannot.  The lockstep gate loads the
VM's recorded pre-state, runs ONE native frame, compares, and then THROWS OUR RESULT AWAY and reloads
the VM's state for the next frame.  It resets us every frame.  So it proves each frame is a correct
*function of the original's state* -- but never that our own state, carried forward by our own frames,
does not drift.

``play_native`` free-runs.  So this gate free-runs:

  * seed the image ONCE, from the demo's frame-0 pre-state;
  * each frame, copy in ONLY the HOST INPUT CHANNEL from the recorded pre-state -- the INT9 key table
    (DS:98C4..99C3) and the last-scancode cell (DS:98C3), i.e. exactly the bytes the keyboard IRQ
    would have written.  Nothing else is ever resynced;
  * run our own frame over our own state;
  * diff the whole DGROUP against the VM's recorded post-state, and report the FIRST frame that drifts.

A divergence here is a state-carry bug -- a seed, an accumulator, an ordering -- of exactly the kind
the lockstep gate is blind to.  The `[234C]` scroll-cursor seed (0x5B00 vs the warm-up's real 0x1A00)
was one of these: lockstep never noticed, because it re-supplied the VM's 234C every single frame.

``cold`` is a SEED AUDIT, not a trajectory gate: it diffs
``build_cold_level_start_image`` (what play_native actually boots) against the demo's real level
start and reports where they differ.  A cold image has rendered no strip rows yet, so the strip
alias dominates and is expected; what matters is the game-state residue.

Usage:
    pypy -m overkill.probes.verify_native_freerun [demo] [max_frames]
    pypy -m overkill.probes.verify_native_freerun [demo] - cold        # the seed audit
"""
from __future__ import annotations

import sys
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
#: the HOST INPUT CHANNEL: the INT9 key-state table + the last-scancode cell.  The only bytes fed in.
INPUT_CHANNEL = (0x98C3,) + tuple(range(0x98C4, 0x99C4))


def _seed_audit(cached) -> int:
    """Diff play_native's cold seed against the demo's REAL level start.  Not a trajectory gate."""
    from collections import Counter

    from overkill.probes.inspect_death_windows import _region
    from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image

    base = DGROUP * 16
    pre_full = next(iter(iter_cached_frames(cached)))[0]
    bundle = (ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin").read_bytes()
    container = (ROOT / "assets" / "OVERKILL").read_bytes()
    img = build_cold_level_start_image(bundle, 0, container)
    vm = pre_full[base:base + 0x10000]
    nat = bytes(img.data[base:base + 0x10000])
    diff = [o for o in range(0x10000) if vm[o] != nat[o] and o not in EXCLUDED_CELLS]
    counts = Counter(_region(o) for o in diff)
    print(f"SEED AUDIT -- build_cold_level_start_image vs the demo's real level start: "
          f"{len(diff)} DGROUP cells")
    for k, v in counts.most_common():
        note = "  (expected: a cold image has rendered no strip rows yet)" if k == "Cxxx+" else ""
        print(f"   {k:24s} {v}{note}")
    state = [o for o in diff if o < 0xD330]
    print(f"\n  non-strip (real game state): {len(state)} cells")
    for o in state[:24]:
        print(f"    DS:{o:04X}  real={vm[o]:02X}  seed={nat[o]:02X}")
    if len(state) > 24:
        print(f"    ... and {len(state) - 24} more")
    print("\nThis is an AUDIT, not a pass/fail gate -- the cold seed is a synthesis of the "
          "level-start writes,\nnot a capture.  Every cell above is a place it does not yet "
          "reproduce the original's level start.")
    return 0


def main(argv) -> int:
    demo = load_demo(argv[0] if argv and argv[0] else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 and argv[1] != "-" else 0
    cold = len(argv) > 2 and argv[2] == "cold"

    cached = load_cache(lockstep_cache_path(demo), demo_key(demo), CACHE_BUDGET)
    if cached is None:
        print(f'cache miss -- record it: pypy -m overkill.probes.verify_native_lockstep "" '
              f'{CACHE_BUDGET}')
        return 1

    if cold:
        return _seed_audit(cached)

    base = DGROUP * 16
    img: MutFlatMemory | None = None
    frames = 0
    first_div: str | None = None
    gap: str | None = None

    for n, (pre_full, post_dgroup, sp, ticks) in enumerate(iter_cached_frames(cached), start=1):
        if max_frames and n > max_frames:
            break
        if img is None:
            img = MutFlatMemory(bytearray(pre_full))       # seed ONCE
        else:
            # the ONLY thing ever fed in: the keyboard IRQ's own writes
            for off in INPUT_CHANNEL:
                img.wb(DGROUP, off, pre_full[base + off])

        try:
            advance_gameplay_frame_97b2(img, isr_ticks=ticks,
                                        level_assets=level_assets_for,
                                        menu_pick=GAME_OVER_MENU_PICK)
        except RecoveryGap as exc:
            gap = f"frame {n}: {exc}"
            break
        frames = n

        nat = bytes(img.data[base:base + 0x10000])
        diffs = [o for o in range(0x10000)
                 if nat[o] != post_dgroup[o] and o not in EXCLUDED_CELLS
                 and not (sp - 0x60 <= o < sp)]
        if diffs and first_div is None:
            cells = ",".join(f"DS:{o:04X}(vm={post_dgroup[o]:02X}/nat={nat[o]:02X})"
                             for o in diffs[:6])
            first_div = f"frame {n}: {len(diffs)}B  {cells}"
            break
        if n % 500 == 0:
            print(f"  ..free-run frame {n}: still byte-exact", flush=True)

    print(f"\nfree-run frames byte-exact: {frames}"
          + (f" (of {cached['frames']})" if not max_frames else ""))
    if gap:
        print(f"GAP  {gap}")
    if first_div:
        print(f"FIRST DRIFT  {first_div}")
    ok = first_div is None and gap is None and frames > 0
    print("RESULT:", "PASS -- the native frame free-runs the whole demo on its own state, byte-exact "
          "against the original every frame" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
