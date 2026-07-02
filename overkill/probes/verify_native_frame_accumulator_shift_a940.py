"""Produced-vs-VM verify: the native A940 accumulator-shift (``step_frame_accumulator_shift_a940``)
vs the VM's ``1010:A940`` opening sequence -- the first gameplay-frame-loop slice recovered this
session (as opposed to the front-end slices).

Unlike the front-end probes, A940 runs every real gameplay frame unconditionally (called from
97B2 right before the object scan), so this uses the STANDARD (snapshot-based, non-cold-start)
demo harness and gets far more coverage per demo.

Per real A940 entry: capture DS:A8CE/A8C8/A8CC, then compare against the VM's actual values at
0xA95D -- the instruction right after the shift completes and before A940's own state==5
(attract-mode) check begins.

Usage:
    python -m overkill.probes.verify_native_frame_accumulator_shift_a940 [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.systems.frame_loop import step_frame_accumulator_shift_a940  # noqa: E402

CS = 0x1010
ENTRY_IP = 0xA940
SHIFT_DONE_IP = 0xA95D
A8CE, A8C6, A8C8, A8CA, A8CC = 0xA8CE, 0xA8C6, 0xA8C8, 0xA8CA, 0xA8CC


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1500
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, dict] = {}

    def on_ref_step(cpu):
        if (cpu.s.cs & 0xFFFF) != CS:
            return
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        ds = cpu.s.ds & 0xFFFF

        p = pending.get(key)
        if p is not None and ip == SHIFT_DONE_IP:
            predicted = p["predicted"]
            actual = (cpu.mem.rw(ds, A8CE), cpu.mem.rw(ds, A8C6), cpu.mem.rw(ds, A8CA),
                      cpu.mem.rw(ds, A8C8), cpu.mem.rw(ds, A8CC))
            expected = (predicted.counter_a8ce, predicted.prev_a8c6, predicted.prev_a8ca, 0, 0)
            res["calls"] += 1
            if actual == expected:
                res["ok"] += 1
            else:
                res["fail"].append((p["a8ce_before"], p["a8c8_before"], p["a8cc_before"], expected, actual))
            del pending[key]

        if ip == ENTRY_IP and key not in pending:
            a8ce_before = cpu.mem.rw(ds, A8CE)
            a8c8_before = cpu.mem.rw(ds, A8C8)
            a8cc_before = cpu.mem.rw(ds, A8CC)
            predicted = step_frame_accumulator_shift_a940(a8ce_before, a8c8_before, a8cc_before)
            pending[key] = dict(predicted=predicted, a8ce_before=a8ce_before,
                                a8c8_before=a8c8_before, a8cc_before=a8cc_before)

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native A940 accumulator-shift vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for f in res["fail"][:8]:
        print(f"  FAIL {f}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A940 accumulator-shift reproduces the VM"
          if ok else ("NO-EVENTS -- A940 was not reached" if res["calls"] == 0
                      else "FAIL -- the native A940 accumulator-shift diverged from the VM"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
