"""§1.2 'across every demo' gate for the recovered native producers.

Runs each native producer verify probe (score / allocator -- byte-exact produced-vs-VM) across the
gameplay demo corpus and reports, per (demo, producer): PASS (events, zero divergence), NO-EVENTS
(that producer is not exercised in the demo), or DIVERGENCE (a real failure). Zero DIVERGENCE on
every demo is the §1.2 invariant for the producers recovered so far; this gate GROWS as more
producers land (add their probe to PROBES). Slow (full demos x step-hook) -- a standalone /
overnight gate, not the fast pytest suite.

Usage:
    python scripts/verify_native_producers.py [max_frames] [demo_glob]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBES = (
    "verify_native_score",
    "verify_native_allocator",
    "verify_native_spawn_seed",
    "verify_native_spawn_seed_a4ea",
    "verify_native_frame_timer",
    "verify_native_projection",
    "verify_native_screen_di",
    "verify_native_sprite_draws",
    "verify_native_object_update_ae09",
    "verify_native_object_seek_step_5db2",
    "verify_native_object_steer_5e42",
    "verify_native_object_postmove_bounds_bc4b",
    "verify_native_hud_text",
    "verify_native_object_spawn_seed_7420",
    "verify_native_object_logic_dispatch_aa2b",
    "verify_native_overlap_contact_box_b250",
    "verify_native_starfield",
    "verify_native_player_shot_spawn",
    "verify_native_a067_fire_gate",
    "verify_native_a067_fire_path",
    "verify_native_player_fanout_walk",
    "verify_native_early_tail_spawn",
    "verify_native_a584_spawn",
    "verify_native_a0e8_pair_spawn",
    "verify_native_b15a_scan",
    "verify_native_a515_spawn",
)
_RESULT_LINE = re.compile(r"calls=(\d+) ok=(\d+) fail=(\d+)")


def _run_probe(probe: str, demo: str, frames: str) -> tuple[int, int, int] | None:
    out = subprocess.run(
        [sys.executable, "-m", f"overkill.probes.{probe}", demo, frames],
        cwd=ROOT, capture_output=True, text=True,
    )
    m = _RESULT_LINE.search(out.stdout)
    return tuple(int(x) for x in m.groups()) if m else None


def main(argv) -> int:
    frames = argv[0] if argv else "1500"
    demo_glob = argv[1] if len(argv) > 1 else "demo_play_tandy_*"
    demos = sorted(p.name for p in (ROOT / "artifacts" / "demos").glob(demo_glob) if p.is_dir())
    diverged: list[tuple[str, str, str]] = []
    for demo in demos:
        for probe in PROBES:
            r = _run_probe(probe, demo, frames)
            if r is None:
                status, detail = "ERROR", "no result line"
            else:
                calls, ok, fail = r
                detail = f"calls={calls} ok={ok} fail={fail}"
                status = "PASS" if (calls > 0 and fail == 0) else ("NO-EVENTS" if calls == 0 else "DIVERGENCE")
            if status in ("DIVERGENCE", "ERROR"):
                diverged.append((demo, probe, detail))
            print(f"  {status:10s} {demo} [{probe.replace('verify_native_', '')}] {detail}")
    print(f"\n=== cross-demo native-producer verify: {len(demos)} demos x {len(PROBES)} producers; "
          f"divergences={len(diverged)} ===")
    for demo, probe, detail in diverged:
        print(f"  FAIL {demo} [{probe}] {detail}")
    print("RESULT:", "PASS -- producers byte-exact vs the VM across the corpus"
          if not diverged else "DIVERGENCE")
    return 1 if diverged else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
