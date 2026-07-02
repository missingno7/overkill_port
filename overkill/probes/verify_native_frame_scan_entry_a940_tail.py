"""Produced-vs-VM verify: the native A940 tail (``step_frame_scan_entry_a940_tail``) vs the VM's
``1010:A9BD`` -- the second gameplay-frame slice this session, completing the A940 pieces that
don't need the (deferred) DS:2356==5 attract-mode cluster.

Uses a STANDARD gameplay demo (not cold-start): this tail runs every real frame, reached either
by falling through the DS:2356==5 attract-mode branch or by a direct jump when DS:2356 != 5 (both
converge at 1010:A9BD, confirmed by disassembly).

Per real A9BD entry: capture DS:98A8 and DS:A8C2, predict, then classify the real outcome by
which of two IPs is reached next -- 0xA9DA (the boss fork, "call near F797" -- deliberately not
modelled past this point, matching the existing hook's own "leave the rare path as original code"
design) or 0xA9DD (the normal scan entry, about to set CX=0x23).

Usage:
    python -m overkill.probes.verify_native_frame_scan_entry_a940_tail [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.systems.frame_loop import step_frame_scan_entry_a940_tail  # noqa: E402

CS = 0x1010
ENTRY_IP = 0xA9BD
BOSS_IP = 0xA9DA
NORMAL_IP = 0xA9DD
FLAG_98A8, FLAG_98A9, BOSS_LATCH = 0x98A8, 0x98A9, 0xA8C2


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1500
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "fail": [], "boss": 0, "normal": 0}
    pending: dict[int, dict] = {}

    def on_ref_step(cpu):
        if (cpu.s.cs & 0xFFFF) != CS:
            return
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        ds = cpu.s.ds & 0xFFFF

        p = pending.get(key)
        if p is not None and ip in (BOSS_IP, NORMAL_IP):
            actual_target = "boss" if ip == BOSS_IP else "normal"
            actual = (cpu.mem.rb(ds, FLAG_98A8), cpu.mem.rb(ds, FLAG_98A9), actual_target)
            predicted = p["predicted"]
            expected = (predicted.flag_98a8, predicted.flag_98a9, predicted.scan_target)
            res["calls"] += 1
            res[actual_target] += 1
            if actual == expected:
                res["ok"] += 1
            else:
                res["fail"].append((p["flag_98a8_before"], p["boss_pending"], expected, actual))
            del pending[key]

        if ip == ENTRY_IP and key not in pending:
            flag_98a8_before = cpu.mem.rb(ds, FLAG_98A8)
            boss_pending = cpu.mem.rw(ds, BOSS_LATCH)
            predicted = step_frame_scan_entry_a940_tail(flag_98a8_before, boss_pending)
            pending[key] = dict(predicted=predicted, flag_98a8_before=flag_98a8_before, boss_pending=boss_pending)

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native A940 tail (98A8/98A9 + boss fork) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} "
          f"(boss={res['boss']} normal={res['normal']})")
    for f in res["fail"][:8]:
        print(f"  FAIL {f}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A940 tail reproduces the VM"
          if ok else ("NO-EVENTS -- A9BD was not reached" if res["calls"] == 0
                      else "FAIL -- the native A940 tail diverged from the VM"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
