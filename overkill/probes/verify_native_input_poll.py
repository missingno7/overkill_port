"""Produced-vs-VM verify: the pure keyboard input decode vs the VM's 1010:0162.

At every ``1010:0162`` keyboard-path entry on the oracle (pure-VM) side this projects
the two decode inputs -- the eight-scancode control map (DS:213E, or DS:2146 when
DS:[0010]==2) and the 256-byte INT 9 key-state table (DS:98C4) -- runs the pure
``decode_keyboard_input_flags``, and asserts the predicted button byte equals the VM's
DS:98BE at 0162's return.  This grounds the canonical input rule
(overkill.recovered.systems.input) against the VM end-to-end, exactly as the object
handlers are grounded by their per-slot gate.

The joystick path (DS:[0010]==1) reads hardware ports, not game data, so it is a host
concern and is skipped here.

Usage: python -m overkill.probes.verify_native_input_poll [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe
from overkill.recovered.systems.input import decode_keyboard_input_flags

CS = 0x1010
POLL_ENTRY_IP = 0x0162
DEVICE_WORD = 0x0010          # DS:[0010] selects keyboard(0)/alt-keyboard(2)/joystick(1)
CONTROL_MAP_DEFAULT = 0x213E  # eight control scancodes
CONTROL_MAP_ALT = 0x2146
KEY_STATE_BASE = 0x98C4       # 256-byte INT 9 scancode->pressed table
INPUT_FLAGS = 0x98BE          # output button byte
JOYSTICK_DEVICE = 0x0001
ALT_KEYBOARD_DEVICE = 0x0002


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "joystick": 0, "fail": []}
    pending: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        if cs == CS and ip == POLL_ENTRY_IP and key not in pending:
            ds = cpu.s.ds & 0xFFFF
            device = cpu.mem.rw(ds, DEVICE_WORD)
            if device == JOYSTICK_DEVICE:
                res["joystick"] += 1
                return
            table = CONTROL_MAP_ALT if device == ALT_KEYBOARD_DEVICE else CONTROL_MAP_DEFAULT
            control_map = tuple(cpu.mem.rb(ds, (table + k) & 0xFFFF) for k in range(8))
            key_state = LazyBytes(cpu.mem, ds, KEY_STATE_BASE, 0x100)
            predicted = decode_keyboard_input_flags(control_map, key_state)
            ss = cpu.s.ss & 0xFFFF
            ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
            pending[key] = (ret_addr, predicted)
        else:
            p = pending.get(key)
            if p is not None and cs == CS and ip == p[0]:
                _ret, predicted = pending.pop(key)
                ds = cpu.s.ds & 0xFFFF
                actual = cpu.mem.rb(ds, INPUT_FLAGS)
                res["calls"] += 1
                if predicted == actual:
                    res["ok"] += 1
                else:
                    res["fail"].append((predicted, actual))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native input decode vs VM 0162 "
          f"(project control-map+key-state -> decode -> compare DS:98BE): "
          f"calls={res['calls']} ok={res['ok']} joystick_skipped={res['joystick']} fail={len(res['fail'])}")
    for predicted, actual in res["fail"][:8]:
        print(f"  FAIL predicted={hex(predicted)} actual={hex(actual)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the pure decode reproduces the VM's button byte"
          if ok else ("NO-EVENTS -- 0162 keyboard path not reached" if res["calls"] == 0 and not res["fail"]
                      else "FAIL -- decode diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
