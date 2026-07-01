"""Produced-vs-VM verify: the native menu-transition wait (``step_menu_transition_wait_ce40``)
vs the VM's ``1010:CE40`` -- the fourth slice of front-end native recovery.

Uses a COLD-START demo (``run_ref_step_probe_cold_start``): CE40 is reached after a dirty-cell
panel finishes presenting, part of the front-end flow never exercised by the gameplay-only demo
corpus.

Per real CE40 iteration: capture ``DS:98C3`` (the shared latch) at entry -- if already non-zero,
the routine exits IMMEDIATELY with no poll/wait, so the outcome is unambiguous.  Otherwise capture
``CX``, watch the poll-return IP (``0xCE4C``) for a fresh ``fire_pressed`` read, then classify the
real outcome from the observed ``CX`` after (0 -> exit_timeout, else -> loop) or an immediate exit.
Both exit reasons reach the SAME (return address, SP), so -- like D318 -- they are disambiguated
from what was OBSERVED (the entry latch / the post-decrement CX), never guessed.

Usage:
    python -m overkill.probes.verify_native_menu_transition_wait_ce40 [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402
from overkill.recovered.systems.menu import step_menu_transition_wait_ce40  # noqa: E402

CS = 0x1010
ENTRY_IP = 0xCE40
POLL_RETURN_IP = 0xCE4C
LATCH = 0x98C3
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
        print(f"ERROR: {demo_name} is not a cold-start demo -- CE40 is only reached via the "
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
            if ip == POLL_RETURN_IP and not p["immediate"]:
                p["fire_pressed"] = bool(cpu.mem.rb(ds, INPUT_FLAGS) & FIRE_MASK)
            outcome = None
            if ip == p["ret_addr"] and sp == p["ret_sp"]:
                outcome = "exit"
            elif ip == ENTRY_IP and sp == p["entry_sp"]:
                outcome = "loop"
            if outcome is not None:
                cx_after = cpu.s.cx & 0xFFFF
                latch_after = cpu.mem.rb(ds, LATCH)
                if p["immediate"]:
                    actual_result = "exit_latched"
                elif outcome == "exit":
                    actual_result = "exit_timeout"
                else:
                    actual_result = "loop"
                predicted = step_menu_transition_wait_ce40(
                    p["cx_before"], p["key_before"], fire_pressed=p.get("fire_pressed", False))
                res["calls"] += 1
                if (predicted.cx == cx_after and predicted.latched_key == latch_after
                        and predicted.result == actual_result):
                    res["ok"] += 1
                else:
                    res["fail"].append((p["cx_before"], p["key_before"], p.get("fire_pressed"),
                                        predicted, (cx_after, latch_after, actual_result)))
                del pending[key]

        if ip == ENTRY_IP and key not in pending:
            key_before = cpu.mem.rb(ds, LATCH)
            ss, sp2 = cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF
            pending[key] = dict(
                cx_before=cpu.s.cx & 0xFFFF, key_before=key_before, immediate=(key_before != 0),
                ret_addr=cpu.mem.rw(ss, sp2), ret_sp=(sp2 + 2) & 0xFFFF, entry_sp=sp2)

    run_ref_step_probe_cold_start(demo, max_frames, on_ref_step)

    print(f"demo {demo_name}: native menu transition wait (CE40) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for f in res["fail"][:8]:
        print(f"  FAIL {f}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native menu transition wait reproduces the VM's CE40"
          if ok else ("NO-EVENTS -- CE40 was not reached"
                      if res["calls"] == 0 else "FAIL -- the native menu transition wait diverged from the VM"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
