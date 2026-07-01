"""Produced-vs-VM verify: the native yes/no choice gate (``step_yes_no_choice_989e``) vs the
VM's ``1010:989E`` -- the fifth slice of front-end native recovery.

Uses a COLD-START demo (``run_ref_step_probe_cold_start``): 989E is a confirmation-style prompt
(e.g. restart/quit), not necessarily reached by every session -- NO-EVENTS is an expected, honest
outcome if the demo never triggers one.

Per real 989E iteration: capture the N-flag (DS:98F5) and Y-flag (DS:98D9) at entry, plus the
return address/SP (both real exits return to the SAME caller address, ``0x98B6``, so -- like
D318/CE40 -- the outcome is disambiguated from OBSERVED state, never guessed: DS:22B4 stays 'N'
only on the exit_no path, since the 'Y' write never runs there).

Usage:
    python -m overkill.probes.verify_native_yes_no_choice_989e [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402
from overkill.recovered.domain.menu import YES_NO_CHOICE_N_CHAR  # noqa: E402
from overkill.recovered.systems.menu import step_yes_no_choice_989e  # noqa: E402

CS = 0x1010
ENTRY_IP = 0x989E
N_FLAG, Y_FLAG = 0x98F5, 0x98D9
DISPLAY_CHAR = 0x22B4


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
        print(f"ERROR: {demo_name} is not a cold-start demo.")
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
            outcome = None
            if ip == p["ret_addr"] and sp == p["ret_sp"]:
                outcome = "exit"
            elif ip == ENTRY_IP and sp == p["entry_sp"]:
                outcome = "loop"
            if outcome is not None:
                display_after = cpu.mem.rb(ds, DISPLAY_CHAR)
                if outcome == "loop":
                    actual_result = "loop"
                else:
                    actual_result = "exit_no" if display_after == YES_NO_CHOICE_N_CHAR else "exit_yes"
                predicted = step_yes_no_choice_989e(n_pressed=p["n_pressed"], y_pressed=p["y_pressed"])
                res["calls"] += 1
                if predicted.display_char == display_after and predicted.result == actual_result:
                    res["ok"] += 1
                else:
                    res["fail"].append((p["n_pressed"], p["y_pressed"], predicted, (display_after, actual_result)))
                del pending[key]

        if ip == ENTRY_IP and key not in pending:
            ss, sp2 = cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF
            pending[key] = dict(
                n_pressed=cpu.mem.rb(ds, N_FLAG) == 0x01, y_pressed=cpu.mem.rb(ds, Y_FLAG) == 0x01,
                ret_addr=cpu.mem.rw(ss, sp2), ret_sp=(sp2 + 2) & 0xFFFF, entry_sp=sp2)

    run_ref_step_probe_cold_start(demo, max_frames, on_ref_step)

    print(f"demo {demo_name}: native yes/no choice (989E) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for f in res["fail"][:8]:
        print(f"  FAIL {f}")
    ok = not res["fail"]
    if res["calls"] == 0:
        print("RESULT: NO-EVENTS -- 989E was not reached (this demo never triggered a yes/no prompt)")
    else:
        print("RESULT:", "PASS -- native yes/no choice reproduces the VM's 989E"
              if ok else "FAIL -- the native yes/no choice diverged from the VM")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
