"""Produced-vs-VM verify: the native level-select grid (``1010:D390-D4B0``) direction handlers
+ fire-confirm mapping vs the VM -- the second slice of front-end native recovery (after 558B),
and the first slice of a routine that had ZERO prior hook coverage (pure disassembly-derived).

Like ``verify_native_menu_idle_558b``, this uses a COLD-START demo (``run_ref_step_probe_cold_
start``) since the gameplay-only demo corpus never reaches the level-select screen.

Per real direction-key event, one of 4 handlers is entered with ``AL`` already holding ``DS:BEDA``
(loaded once by the shared prelude at ``1010:D44F``): capture AL, predict via the matching pure
function, then classify the REAL outcome -- reaching the shared accept tail (``1010:D47C``, about
to execute ``mov [BEDA],al``, so AL still holds the predicted post-state at that instant) means
accepted; reaching the idle-loop head (``1010:D445``) directly means rejected (a boundary case,
``BEDA`` never written). Per real fire-confirm, ``1010:D424`` is entered with ``DS:BEDA`` fresh in
memory; captures the return address/SP there (D424 does no pushes -- pure straight-line
arithmetic) and compares ``DS:2356`` at that exit against the predicted ``LevelSelectFireResult``.

Usage:
    python -m overkill.probes.verify_native_level_select_grid [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402
from overkill.recovered.systems.menu import (  # noqa: E402
    resolve_level_select_fire_d424,
    step_level_select_decrement_d488,
    step_level_select_increment_d490,
    step_level_select_page_down_d476,
    step_level_select_page_up_d480,
)

CS = 0x1010
HANDLERS = {
    0xD476: (step_level_select_page_down_d476, "D476_page_down"),
    0xD480: (step_level_select_page_up_d480, "D480_page_up"),
    0xD488: (step_level_select_decrement_d488, "D488_decrement"),
    0xD490: (step_level_select_increment_d490, "D490_increment"),
}
ACCEPT_TAIL_IP = 0xD47C
IDLE_HEAD_IP = 0xD445
FIRE_CONFIRM_IP = 0xD424
BEDA = 0xBEDA
LEVEL_GLOBAL = 0x2356


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
        print(f"ERROR: {demo_name} is not a cold-start demo -- the level-select screen is only "
              f"reached from a fresh boot's menu flow.")
        return 2

    res = {"dir_calls": 0, "dir_ok": 0, "dir_fail": [], "fire_calls": 0, "fire_ok": 0, "fire_fail": []}
    dir_pending: dict[int, dict] = {}
    fire_pending: dict[int, dict] = {}

    def on_ref_step(cpu):
        if (cpu.s.cs & 0xFFFF) != CS:
            return
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        ds = cpu.s.ds & 0xFFFF

        dp = dir_pending.get(key)
        if dp is not None:
            outcome = None
            if dp["accepted"] and ip == ACCEPT_TAIL_IP:
                outcome = cpu.s.ax & 0xFF
            elif not dp["accepted"] and ip == IDLE_HEAD_IP:
                outcome = cpu.mem.rb(ds, BEDA)
            if outcome is not None:
                res["dir_calls"] += 1
                if outcome == dp["predicted"].beda:
                    res["dir_ok"] += 1
                else:
                    res["dir_fail"].append((dp["label"], dp["beda_before"], dp["predicted"], outcome))
                del dir_pending[key]

        if ip in HANDLERS and key not in dir_pending:
            func, label = HANDLERS[ip]
            al = cpu.s.ax & 0xFF
            predicted = func(al)
            dir_pending[key] = dict(predicted=predicted, label=label, beda_before=al, accepted=predicted.accepted)

        fp = fire_pending.get(key)
        if fp is not None and ip == fp["ret_addr"] and (cpu.s.sp & 0xFFFF) == fp["ret_sp"]:
            actual = cpu.mem.rw(ds, LEVEL_GLOBAL)
            res["fire_calls"] += 1
            if actual == fp["predicted"].level:
                res["fire_ok"] += 1
            else:
                res["fire_fail"].append((fp["beda"], fp["predicted"], actual))
            del fire_pending[key]

        if ip == FIRE_CONFIRM_IP and key not in fire_pending:
            beda = cpu.mem.rw(ds, BEDA)
            ss, sp = cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF
            fire_pending[key] = dict(
                predicted=resolve_level_select_fire_d424(beda), beda=beda,
                ret_addr=cpu.mem.rw(ss, sp), ret_sp=(sp + 2) & 0xFFFF)

    run_ref_step_probe_cold_start(demo, max_frames, on_ref_step)

    print(f"demo {demo_name}: native level-select direction handlers vs VM: "
          f"calls={res['dir_calls']} ok={res['dir_ok']} fail={len(res['dir_fail'])}")
    for f in res["dir_fail"][:8]:
        print(f"  FAIL {f}")
    print(f"demo {demo_name}: native level-select fire-confirm (D424) vs VM: "
          f"calls={res['fire_calls']} ok={res['fire_ok']} fail={len(res['fire_fail'])}")
    for f in res["fire_fail"][:8]:
        print(f"  FAIL {f}")
    ok = (res["dir_calls"] > 0 or res["fire_calls"] > 0) and not res["dir_fail"] and not res["fire_fail"]
    print("RESULT:", "PASS -- the native level-select grid reproduces the VM"
          if ok else ("NO-EVENTS -- the level-select screen was not reached"
                      if res["dir_calls"] == 0 and res["fire_calls"] == 0
                      else "FAIL -- the native level-select grid diverged from the VM"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
