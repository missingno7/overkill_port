"""Forward-carry composition proof for the front-end: does chaining the 4 recovered leaf
decisions (558B menu idle -> D390 level-select entry -> D424 fire-confirm), predicting purely
from the FIRST 558B exit onward with NO intervening VM state reads, correctly predict the FINAL
selected level (DS:2356) the user's real cold-start session reached?

This is the front-end counterpart of overkill.probes.verify_native_forward_frames: every other
front-end probe resets from a fresh VM projection on every call (proving each screen's decision
in isolation), never that CHAINING them (558B's exit state feeding D390's entry, D390's BEDA
carried across however many direction/confirm events happen, feeding D424's fire-confirm) stays
correct end to end.  Uses a COLD-START demo (this whole chain is front-end-only).

Design: on the FIRST 558B exit (fire pressed), seed BEDA=0 (the level-select screen's own static
initial value -- DS:BEDA is a fixed data location, never written before the screen's first
entry) and start tracking.  From then on, ignore 558B entirely (the menu is behind us) and
predict purely from the 4 direction handlers + D424 as they fire for real, carrying BEDA forward
between them (never re-reading DS:BEDA from the VM once tracking starts).  At D424's real exit,
compare the carried prediction's final level against the VM's actual DS:2356.

Usage:
    python -m overkill.probes.verify_native_front_end_forward [demo_name] [max_frames]
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
    step_menu_idle_558b,
)

CS = 0x1010
MENU_IDLE_IP = 0x558B
ATTRACT_TIMEOUT_IP = 0x55FD
DIR_HANDLERS = {
    0xD476: step_level_select_page_down_d476,
    0xD480: step_level_select_page_up_d480,
    0xD488: step_level_select_decrement_d488,
    0xD490: step_level_select_increment_d490,
}
ACCEPT_TAIL_IP = 0xD47C
IDLE_HEAD_IP = 0xD445
FIRE_CONFIRM_IP = 0xD424
LEVEL_GLOBAL = 0x2356
DEVICE_WORD, JOYSTICK_DEVICE = 0x0010, 0x0001
SHORTCUT_FLAG_OFFSETS = (0x98E9, 0x98E8, 0x98E2, 0x98D7, 0x98F6, 0x98DC, 0x98DB, 0x98C5, 0x9907)
INPUT_FLAGS, FIRE_MASK = 0x98BE, 0x10


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

    state = {"phase": "waiting_for_menu_exit", "beda": None, "menu_pending": {}, "dir_pending": {}}
    fire_pending: dict[int, dict] = {}
    result = {}

    def on_ref_step(cpu):
        if (cpu.s.cs & 0xFFFF) != CS or state["phase"] == "done":
            return
        ip = cpu.s.ip & 0xFFFF
        sp = cpu.s.sp & 0xFFFF
        key = id(cpu)
        ds = cpu.s.ds & 0xFFFF

        if state["phase"] == "waiting_for_menu_exit":
            mp = state["menu_pending"].get(key)
            if mp is not None:
                outcome = None
                if ip == mp["ret_addr"] and sp == mp["ret_sp"]:
                    outcome = "exit"
                elif ip == ATTRACT_TIMEOUT_IP:
                    outcome = "attract_timeout"
                elif ip == MENU_IDLE_IP and sp == mp["entry_sp"]:
                    outcome = "loop"
                if outcome == "exit":
                    print("558B exited (FIRE) -- switching to level-select tracking, BEDA seeded at 0")
                    state["phase"] = "tracking"
                    state["beda"] = 0
                    del state["menu_pending"][key]
                elif outcome is not None:
                    del state["menu_pending"][key]
            if ip == MENU_IDLE_IP and key not in state["menu_pending"]:
                if cpu.mem.rw(ds, DEVICE_WORD) == JOYSTICK_DEVICE:
                    return
                if any(cpu.mem.rb(ds, off) == 0x01 for off in SHORTCUT_FLAG_OFFSETS):
                    return
                ss, sp2 = cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF
                state["menu_pending"][key] = dict(
                    ret_addr=cpu.mem.rw(ss, sp2), ret_sp=(sp2 + 2) & 0xFFFF, entry_sp=sp2)
            return

        # phase == "tracking": chase the 4 direction handlers + D424, carrying BEDA purely.
        dp = state["dir_pending"].get(key)
        if dp is not None:
            outcome_beda = None
            if dp["accepted"] and ip == ACCEPT_TAIL_IP:
                outcome_beda = state["beda"]  # already updated at handler-entry time below
            elif not dp["accepted"] and ip == IDLE_HEAD_IP:
                outcome_beda = state["beda"]
            if outcome_beda is not None:
                del state["dir_pending"][key]

        if ip in DIR_HANDLERS and key not in state["dir_pending"]:
            step = DIR_HANDLERS[ip](state["beda"])
            state["beda"] = step.beda
            state["dir_pending"][key] = dict(accepted=step.accepted)

        fp = fire_pending.get(key)
        if fp is not None and ip == fp["ret_addr"] and sp == fp["ret_sp"]:
            actual_level = cpu.mem.rw(ds, LEVEL_GLOBAL)
            predicted_level = fp["predicted"].level
            result["match"] = predicted_level == actual_level
            result["predicted"] = predicted_level
            result["actual"] = actual_level
            result["beda_at_confirm"] = fp["beda"]
            state["phase"] = "done"
            del fire_pending[key]

        if ip == FIRE_CONFIRM_IP and key not in fire_pending:
            ss, sp2 = cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF
            fire_pending[key] = dict(
                predicted=resolve_level_select_fire_d424(state["beda"]), beda=state["beda"],
                ret_addr=cpu.mem.rw(ss, sp2), ret_sp=(sp2 + 2) & 0xFFFF)

    run_ref_step_probe_cold_start(demo, max_frames, on_ref_step)

    if state["phase"] != "done":
        print(f"RESULT: NO-EVENTS -- never reached D424 confirm (final phase: {state['phase']})")
        return 0
    print(f"demo {demo_name}: front-end forward-carry (558B exit -> D390 grid -> D424 confirm), "
          f"NO intervening VM reads: beda_at_confirm={result['beda_at_confirm']} "
          f"predicted_level={result['predicted']:#06x} actual_level={result['actual']:#06x}")
    print("RESULT:", "PASS -- the composed front-end chain predicts the real selected level"
          if result["match"] else "FAIL -- the composed chain diverged from the VM's real selection")
    return 0 if result["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
