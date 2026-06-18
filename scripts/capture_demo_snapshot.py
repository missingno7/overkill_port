#!/usr/bin/env python
"""Capture an oracle snapshot at a target CS:IP during input-demo replay.

Reusable enabler for behavior-queue lifts.  It replays a recorded demo through a
single hooked runtime (driven by the same boundary clock the demo was recorded
against) and writes a standard ``memory_1mb.bin`` + ``state.json`` snapshot the
first time execution reaches a target address at or after ``--min-boundary``.
The result loads with ``overkill.runtime.load_overkill_snapshot`` exactly like the
existing ``artifacts/evidence/snapshot_stop_*`` behavior oracles, so a new object
behavior can be lifted and verified against a real captured state.

Example:
    python scripts/capture_demo_snapshot.py \
        --demo artifacts/demos/demo_play_tandy_L3_full_20260617_202520 \
        --stop-at 1010:BB80 --min-boundary 500 \
        --out artifacts/evidence/snapshot_stop_1010_bb80_behavior
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import overkill.hooks  # noqa: F401 - registers all replacement hooks
from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from dos_re.snapshot import write_snapshot  # noqa: E402
from overkill.runtime import load_overkill_snapshot  # noqa: E402

# Frame-boundary hooks per video mode (mirrors overkill.frame_verify).
PRESENT_IP_BY_VIDEO = {"cga": 0x447B, "ega": 0x2750, "tandy": 0x3354}
TIMER_WAIT_IP = 0x0679
RETRACE_WAIT_IP = 0x50C9


def _parse_addr(text: str) -> tuple[int, int]:
    cs_s, ip_s = text.split(":")
    return int(cs_s, 16) & 0xFFFF, int(ip_s, 16) & 0xFFFF


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--demo", required=True, help="input demo directory/json")
    p.add_argument("--stop-at", required=True, help="target CS:IP, e.g. 1010:BB80")
    p.add_argument("--out", required=True, help="snapshot output directory")
    p.add_argument("--exe", default=str(ROOT / "assets" / "OVERKILL"))
    p.add_argument("--game-root", default=str(ROOT / "assets"))
    p.add_argument("--video", default="tandy", choices=sorted(PRESENT_IP_BY_VIDEO))
    p.add_argument("--min-boundary", type=int, default=0,
                   help="only capture once this many frame boundaries have elapsed")
    p.add_argument("--max-steps", type=int, default=300_000_000)
    args = p.parse_args(argv)

    target = _parse_addr(args.stop_at)
    demo = InputDemoPlayback.load(args.demo)
    rt = load_overkill_snapshot(args.exe, demo.snapshot_path(), game_root=args.game_root)
    rt.cpu.trace_enabled = False
    rt.cpu.coverage_telemetry = None

    boundary_hooks = {
        (0x1010, PRESENT_IP_BY_VIDEO[args.video]),
        (0x1010, TIMER_WAIT_IP),
        (0x1010, RETRACE_WAIT_IP),
    }

    boundary = 0
    demo_boundary = 0
    demo.apply_to_runtime(0, rt)

    # Hot loop: keep local references and use plain int compares (avoid building a
    # (cs, ip) tuple every instruction) so deep demo replays finish in time.
    s = rt.cpu.s
    step_fn = rt.cpu.step
    target_cs, target_ip = target
    boundary_ips = {ip for (cs, ip) in boundary_hooks}
    min_boundary = args.min_boundary

    for step in range(1, args.max_steps + 1):
        ip = s.ip
        cs = s.cs
        if ip == target_ip and cs == target_cs and boundary >= min_boundary:
            write_snapshot(rt, args.out, status=f"stop_at_{target_cs:04X}_{target_ip:04X}", steps=step)
            print(f"OK captured {target_cs:04X}:{target_ip:04X} at step={step} boundary={boundary} -> {args.out}")
            print(rt.cpu.s.snapshot())
            return 0
        if cs == 0x1010 and ip in boundary_ips:
            boundary += 1
            if boundary > demo_boundary:
                demo_boundary = boundary
                if demo.finished(demo_boundary):
                    print(f"FAIL demo finished at boundary={demo_boundary} without reaching {args.stop_at}")
                    return 1
                demo.apply_to_runtime(demo_boundary, rt)
        step_fn()

    print(f"FAIL reached --max-steps without hitting {args.stop_at}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
