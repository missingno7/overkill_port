"""Produced-vs-VM verify: the native interstitial-loop decision (``step_interstitial_tick_d318``)
vs the VM's ``1010:D318`` -- the third slice of front-end native recovery.

Uses a COLD-START demo (``run_ref_step_probe_cold_start``): D318 is a Tandy-only interstitial
screen reached after the 97B2 frame path, never exercised by the gameplay-only demo corpus.

Per real D318 iteration: capture the counter (DS:BED8) and the return address/SP at entry (D318
does no pushes of its own before this decision -- the ``ret``/loop-back happen at the SAME depth
the routine was entered at). Classify the real outcome by which of two conditions is next true:
reaching the caller's return address (a genuine exit -- either timeout or fire; disambiguated by
the counter itself, since only the timeout path can leave it > INTERSTITIAL_TIMEOUT) or looping
back to 0xD318 at the same stack depth (no CALL happened).

Usage:
    python -m overkill.probes.verify_native_interstitial_tick_d318 [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402
from overkill.recovered.domain.menu import INTERSTITIAL_TIMEOUT  # noqa: E402
from overkill.recovered.systems.menu import step_interstitial_tick_d318  # noqa: E402

CS = 0x1010
ENTRY_IP = 0xD318
POLL_RETURN_IP = 0xD355  # right after `call 0162` inside D318's own counter<=timeout branch
COUNTER = 0xBED8
INPUT_FLAGS = 0x98BE
FIRE_MASK = 0x10


def main(argv) -> int:
    demo_name = argv[0] if argv else None
    if demo_name is None:
        candidates = sorted((ROOT / "artifacts" / "demos").glob("demo_*"))
        found = next((d.name for d in reversed(candidates)
                     if (d / "input_demo.json").is_file() and load_demo(d.name, d.name).is_cold_start), None)
        if found is None:
            print("RESULT: NO-EVENTS -- no cold-start demo found under artifacts/demos/")
            return 0
        demo_name = found
    max_frames = int(argv[1]) if len(argv) > 1 else None
    demo = load_demo(demo_name, demo_name)
    if not demo.is_cold_start:
        print(f"ERROR: {demo_name} is not a cold-start demo -- D318 is only reached via the "
              f"front-end flow, never mid-level.")
        return 2

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, dict] = {}

    def on_ref_step(cpu):
        if (cpu.s.cs & 0xFFFF) != CS:
            return
        ip = cpu.s.ip & 0xFFFF
        sp = cpu.s.sp & 0xFFFF
        key = id(cpu)
        ds = cpu.s.ds & 0xFFFF

        p = pending.get(key)
        if p is not None:
            # Capture fire_pressed right after D318's own poll (0162) returns -- BEFORE the
            # exit path's call_input_until_release loop re-polls until fire is RELEASED,
            # which would otherwise clobber DS:98BE back to 0 by the time we observe the exit.
            if ip == POLL_RETURN_IP:
                p["fire_pressed"] = bool(cpu.mem.rb(ds, INPUT_FLAGS) & FIRE_MASK)
            outcome = None
            if ip == p["ret_addr"] and sp == p["ret_sp"]:
                outcome = "exit"
            elif ip == ENTRY_IP and sp == p["entry_sp"]:
                outcome = "loop"
            if outcome is not None:
                counter_after = cpu.mem.rw(ds, COUNTER)
                if outcome == "exit":
                    actual_result = "exit_timeout" if counter_after > INTERSTITIAL_TIMEOUT else "exit_fire"
                else:
                    actual_result = "loop"
                # The timeout path never reaches POLL_RETURN_IP; fire_pressed is irrelevant
                # there (step_interstitial_tick_d318 checks the timeout first), so False is safe.
                fire_pressed = p.get("fire_pressed", False)
                predicted = step_interstitial_tick_d318(p["counter_before"], fire_pressed=fire_pressed)
                res["calls"] += 1
                if predicted.counter == counter_after and predicted.result == actual_result:
                    res["ok"] += 1
                else:
                    res["fail"].append((p["counter_before"], fire_pressed, predicted, (counter_after, actual_result)))
                del pending[key]

        if ip == ENTRY_IP and key not in pending:
            ss, sp2 = cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF
            pending[key] = dict(
                counter_before=cpu.mem.rw(ds, COUNTER),
                ret_addr=cpu.mem.rw(ss, sp2), ret_sp=(sp2 + 2) & 0xFFFF, entry_sp=sp2)

    run_ref_step_probe_cold_start(demo, max_frames, on_ref_step)

    print(f"demo {demo_name}: native interstitial tick (D318) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for f in res["fail"][:8]:
        print(f"  FAIL {f}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native interstitial tick reproduces the VM's D318"
          if ok else ("NO-EVENTS -- D318 was not reached (Tandy-only screen -- does the demo touch it?)"
                      if res["calls"] == 0 else "FAIL -- the native interstitial tick diverged from the VM"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
