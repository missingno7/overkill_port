"""THE DEMO-LOCKSTEP GATE: every 97B2 gameplay frame, the native frame vs the VM, whole-DGROUP.

The campaign instrument (campaigns/demo_lockstep.md): replay a recorded demo through the frame
verifier's PURE reference VM; at every ``1010:97B2`` frame top, snapshot the machine; when the VM
next returns to 97B2 (one full frame ran), run the NATIVE frame (``native_frame.
advance_gameplay_frame_97b2``) over the pre-state copy and diff the ENTIRE 64K DGROUP.

Frames where the native frame raises :class:`RecoveryGap` are the FRONTIER (reported with counts,
newest recovery target first); PASS requires zero divergence on every frame the native frame CAN
run.  The owner's bar: the whole demo, zero gaps, zero divergence -- then play_native runs this
same frame function with the keyboard.

The per-frame VM states record into a shadow cache on the first run (the walk-cache machinery,
a separate ``.lockstepcache`` file) and replay in seconds afterwards; pass ``vm`` to force the
live oracle.

Usage:
    python -m overkill.probes.verify_native_lockstep [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import (  # noqa: E402
    load_demo, run_ref_step_probe, run_ref_step_probe_cold_start,
)
from overkill.probes._shadow_cache import (  # noqa: E402
    CACHE_DIR, WalkShadowRecorder, demo_key, iter_cached_frames, load_cache,
)
from overkill.native_frame import advance_gameplay_frame_97b2  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402

CS = 0x1010
FRAME_TOP = 0x97B2
DGROUP = 0x25CC
DEFAULT_DEMO = "demo_cold_start_full_20260705_123645"

# The compare exclusions, inherited from the walk gate with the same justifications
# (probes/verify_native_walk_demo.py): the 5DB2/5E42 steer scratch outside the pure islands and
# the DS:215A promiscuous IRQ/menu scratch.  The frame boundary sees MORE machinery than the walk
# boundary; any additional exclusion must be added HERE with a traced justification, never
# silently.
EXCLUDED_CELLS = {0xA954, 0xA955, 0x230A, 0x230B, 0x230C, 0x230D,
                  0x230E, 0x230F, 0x2310, 0x2311, 0x215A, 0x215B}


def lockstep_cache_path(demo) -> Path:
    return CACHE_DIR / (Path(demo.demo_dir).name + ".lockstepcache")


def _check_frame(pre_full, post_dgroup: bytes, sp: int, stats, gaps: Counter,
                 first_divs: list) -> None:
    """Run the native frame over one VM pre-state and diff DGROUP against the VM post-state."""
    base = DGROUP * 16
    native = MutFlatMemory(pre_full)
    stats["frames"] += 1
    if stats["frames"] % 500 == 0:
        print(f"  ..lockstep frame {stats['frames']}: diverged={stats['diverged']} "
              f"distinct-gaps={len(gaps)}", flush=True)
    try:
        advance_gameplay_frame_97b2(native)
    except RecoveryGap as gap:
        key = str(gap).split(" (record ")[0]
        gaps[key] += 1
        return
    nat = bytes(native.data[base:base + 0x10000])
    if post_dgroup == nat:
        return
    diffs = [o for o in range(0x10000)
             if post_dgroup[o] != nat[o] and o not in EXCLUDED_CELLS
             and not (sp - 0x60 <= o < sp)]
    if diffs:
        stats["diverged"] += 1
        if len(first_divs) < 12:
            line = (f"lockstep frame {stats['frames']}: {len(diffs)}B at "
                    + ",".join(f"DS:{o:04X}(vm={post_dgroup[o]:02X}/nat={nat[o]:02X})"
                               for o in diffs[:6]))
            first_divs.append(line)
            print(f"  DIVERGENCE {line}", flush=True)


def main(argv) -> int:
    force_vm = any(a in ("vm", "--vm") for a in argv)
    argv = [a for a in argv if a not in ("vm", "--vm")]
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else None

    stats = {"frames": 0, "diverged": 0}
    gaps: Counter = Counter()
    first_divs: list[str] = []

    key = demo_key(demo)
    cache_file = lockstep_cache_path(demo)
    cached = None if force_vm else load_cache(cache_file, key, max_frames)
    if cached is not None:
        print(f"  (replaying {cached['frames']} recorded 97B2 frames from {cache_file.name} -- "
              f"same states, same comparison, no VM)", flush=True)
        for pre_full, post_dgroup, sp in iter_cached_frames(cached):
            _check_frame(pre_full, post_dgroup, sp, stats, gaps, first_divs)
    else:
        recorder = WalkShadowRecorder(key, max_frames)
        base = DGROUP * 16
        st = {"pre": None, "sp": 0}

        def on_ref_step(cpu) -> None:
            if (cpu.s.cs & 0xFFFF) != CS or (cpu.s.ip & 0xFFFF) != FRAME_TOP:
                return
            m = cpu.mem
            if st["pre"] is not None:
                # one full 97B2 frame ran between the previous hit and this one
                pre, sp = st["pre"], st["sp"]
                post_dgroup = bytes(m.data[base:base + 0x10000])
                recorder.add_frame(pre, post_dgroup, sp)
                _check_frame(pre, post_dgroup, sp, stats, gaps, first_divs)
            st["pre"] = bytes(m.data)
            st["sp"] = cpu.s.sp & 0xFFFF

        if demo.is_cold_start:
            run_ref_step_probe_cold_start(demo, max_frames, on_ref_step)
        else:
            frames = (demo.end_boundary + 5) if max_frames is None else max_frames
            run_ref_step_probe(demo, frames, on_ref_step)
        if stats["frames"]:
            recorder.save(cache_file)
            print(f"  (recorded {stats['frames']} 97B2 frames -> {cache_file.name})", flush=True)

    print(f"97B2 frames lockstepped: {stats['frames']}  diverged: {stats['diverged']}")
    for line in first_divs:
        print(f"  DIVERGENCE {line}")
    if gaps:
        print(f"recovery gaps ({sum(gaps.values())} frames NOT natively runnable yet):")
        for text, n in gaps.most_common():
            print(f"  {n:6d}x {text}")
    verdict = stats["diverged"] == 0 and stats["frames"] > 0
    print("RESULT:", ("PASS -- zero divergence on every natively-runnable 97B2 frame"
                      + (" (with the gap frontier above)" if gaps else ""))
          if verdict else "FAIL")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
