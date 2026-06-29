"""Produced-vs-VM verify: the native movement-bits stage vs the VM's 9B2E (9B6F..9B94).

The game-state controller's second stage (after the input poll) applies the four held
direction bits of DS:98BE to the player-controlled view-anchor slot (DS:237C, addressed
SS:BP) through the A5D1/A5EA/A5F9/A607 axis clamp-steps.  At each 9B6F entry on the oracle
side this projects the slot's X/Y, the input byte, and the no-clamp gate (DS:A47C), runs
the pure ``step_view_anchor_by_input``, and asserts the predicted X/Y equal the VM's at the
stage's convergence point (1010:9B97, just past the four bits and before the secondary-fire
check).  This grounds the composed stage end-to-end against the VM.

Usage: python -m overkill.probes.verify_native_movement_bits [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import load_demo, run_ref_step_probe
from overkill.recovered.systems.movement import step_view_anchor_by_input

CS = 0x1010
STAGE_ENTRY_IP = 0x9B6F     # first direction-bit test (UP)
STAGE_EXIT_IP = 0x9B97      # convergence after all four bits (cmp [2350],B6)
OFF_X = 0x02                # SS:BP+2 view-anchor X word
OFF_Y = 0x04                # SS:BP+4 view-anchor Y word
INPUT_FLAGS = 0x98BE
NO_CLAMP_GATE = 0xA47C      # A5D1 takes the one-pixel path when this is non-zero


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "moved": 0, "fail": []}
    pending: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        if cs == CS and ip == STAGE_ENTRY_IP and key not in pending:
            ss = cpu.s.ss & 0xFFFF
            ds = cpu.s.ds & 0xFFFF
            bp = cpu.s.bp & 0xFFFF
            x = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
            y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
            input_flags = cpu.mem.rb(ds, INPUT_FLAGS)
            no_clamp = cpu.mem.rw(ds, NO_CLAMP_GATE) != 0
            predicted = step_view_anchor_by_input(x, y, input_flags, no_clamp=no_clamp)
            pending[key] = (ss, bp, predicted)
        else:
            p = pending.get(key)
            if p is not None and cs == CS and ip == STAGE_EXIT_IP:
                ss, bp, predicted = pending.pop(key)
                actual = (cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                          cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF))
                res["calls"] += 1
                if predicted.stepped:
                    res["moved"] += 1
                if (predicted.x_word, predicted.y_word) == actual:
                    res["ok"] += 1
                else:
                    res["fail"].append(((predicted.x_word, predicted.y_word), actual))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native movement-bits stage vs VM 9B2E "
          f"(project slot+input -> step -> compare SS:BP X/Y at 9B97): "
          f"calls={res['calls']} ok={res['ok']} moved={res['moved']} fail={len(res['fail'])}")
    for predicted, actual in res["fail"][:8]:
        print(f"  FAIL predicted={tuple(hex(v) for v in predicted)} actual={tuple(hex(v) for v in actual)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the native movement-bits stage reproduces the VM's view-anchor position"
          if ok else ("NO-EVENTS -- the 9B2E movement-bits stage was not reached"
                      if res["calls"] == 0 and not res["fail"]
                      else "FAIL -- the stage diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
