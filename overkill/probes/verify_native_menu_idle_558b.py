"""Produced-vs-VM verify: the native main-menu idle loop (``step_menu_idle_558b``) vs the VM's
``1010:558B`` -- the first slice of the front-end (intro/title/menu/map) native recovery.

Front-end routines are never exercised by the recorded gameplay demos (they all start mid-level),
so this uses a COLD-START demo (recorded via ``scripts/play.py --record-demo`` from a fresh boot,
covering the real intro->menu->gameplay session a human played) via
``overkill.probes._harness.run_ref_step_probe_cold_start``.

Per real ``558B`` iteration: capture the attract counter (DS:22BF) and the 9 shortcut-flag bytes
at entry (the ret address + SP too, for the "exit" outcome).  Then watch for one of three real
outcomes: reaching the caller's return address (exit -- FIRE pressed), reaching 0x55FD (the
attract-mode timeout continuation), or looping back to 0x558B at the same stack depth (no CALL
happened).  A shortcut-active entry is a decline (matches ``step_menu_idle_558b`` returning
``None`` -- the hook's own documented fallback-to-ASM scope) and is not compared.

Usage:
    python -m overkill.probes.verify_native_menu_idle_558b [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402
from overkill.recovered.systems.menu import step_menu_idle_558b  # noqa: E402

CS = 0x1010
ENTRY_IP = 0x558B
ATTRACT_TIMEOUT_IP = 0x55FD
ATTRACT_COUNTER = 0x22BF
INPUT_FLAGS = 0x98BE
FIRE_MASK = 0x10
SHORTCUT_FLAG_OFFSETS = (0x98E9, 0x98E8, 0x98E2, 0x98D7, 0x98F6, 0x98DC, 0x98DB, 0x98C5, 0x9907)


def main(argv) -> int:
    demo_name = argv[0] if argv else None
    demo_path = ROOT / "artifacts" / "demos" / demo_name if demo_name else None
    if demo_path is None:
        # Fall back to the newest cold-start demo under artifacts/demos, if any.
        candidates = sorted((ROOT / "artifacts" / "demos").glob("demo_*"))
        demo_path = next((d for d in reversed(candidates)
                          if (d / "input_demo.json").is_file()
                          and load_demo(d.name, d.name).is_cold_start), None)
        if demo_path is None:
            print("RESULT: NO-EVENTS -- no cold-start demo found under artifacts/demos/")
            return 0
        demo_name = demo_path.name
    max_frames = int(argv[1]) if len(argv) > 1 else None
    demo = load_demo(demo_name, demo_name)
    if not demo.is_cold_start:
        print(f"ERROR: {demo_name} is not a cold-start demo (has a start snapshot); "
              f"558B is never reached mid-level -- use a cold-start demo.")
        return 2

    res = {"calls": 0, "ok": 0, "declined": 0, "fail": []}
    pending: dict[int, dict] = {}

    def capture(cpu, key: int) -> None:
        ds = cpu.s.ds & 0xFFFF
        ss = cpu.s.ss & 0xFFFF
        sp = cpu.s.sp & 0xFFFF
        pending[key] = dict(
            attract_before=cpu.mem.rw(ds, ATTRACT_COUNTER),
            shortcut_active=any(cpu.mem.rb(ds, off) == 0x01 for off in SHORTCUT_FLAG_OFFSETS),
            ret_addr=cpu.mem.rw(ss, sp), ret_sp=(sp + 2) & 0xFFFF, entry_sp=sp,
        )

    def on_ref_step(cpu):
        if (cpu.s.cs & 0xFFFF) != CS:
            return
        ip = cpu.s.ip & 0xFFFF
        sp = cpu.s.sp & 0xFFFF
        key = id(cpu)
        p = pending.get(key)
        outcome = None
        if p is not None:
            if ip == p["ret_addr"] and sp == p["ret_sp"]:
                outcome = "exit"
            elif ip == ATTRACT_TIMEOUT_IP:
                outcome = "attract_timeout"
            elif ip == ENTRY_IP and sp == p["entry_sp"]:
                outcome = "loop"
        if outcome is not None:
            ds = cpu.s.ds & 0xFFFF
            actual_attract = cpu.mem.rw(ds, ATTRACT_COUNTER)
            fire_pressed = cpu.mem.rb(ds, INPUT_FLAGS) == FIRE_MASK
            res["calls"] += 1
            if p["shortcut_active"]:
                res["declined"] += 1
            else:
                predicted = step_menu_idle_558b(
                    p["attract_before"], shortcut_active=False, fire_pressed=fire_pressed)
                if predicted is not None and predicted.attract_counter == actual_attract and predicted.result == outcome:
                    res["ok"] += 1
                else:
                    res["fail"].append((p["attract_before"], fire_pressed, predicted, (actual_attract, outcome)))
            del pending[key]
        if ip == ENTRY_IP and key not in pending:
            capture(cpu, key)

    run_ref_step_probe_cold_start(demo, max_frames, on_ref_step)

    print(f"demo {demo_name}: native menu idle loop (558B) vs VM: "
          f"calls={res['calls']} ok={res['ok']} declined={res['declined']} fail={len(res['fail'])}")
    for f in res["fail"][:8]:
        print(f"  FAIL attract_before={f[0]} fire_pressed={f[1]} predicted={f[2]} actual={f[3]}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native menu idle loop reproduces the VM's 558B"
          if ok else ("NO-EVENTS -- 558B was not reached (does the demo touch the main menu?)"
                      if res["calls"] == 0 else "FAIL -- the native menu idle loop diverged from the VM"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
