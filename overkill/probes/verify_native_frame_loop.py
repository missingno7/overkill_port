"""Produced-vs-VM verify: the native frame controller's player sub-step vs the VM's 9B2E.

This grounds the *composition* in overkill.recovered.systems.frame_loop, not just the two
stages separately: at each 9B2E movement-bits entry (1010:9B6F) on the oracle side it builds
the native FrameInput from the raw key state (DS:98C4) + the control map (DS:213E/2146) and
projects the view-anchor slot (DS:237C, SS:BP) into a one-slot ObjectPool, runs
``native_player_frame_step`` (decode the button byte itself, then apply the movement bits),
and asserts BOTH that the decoded flags equal the VM's DS:98BE and that the stepped anchor X/Y
equal the VM's at the stage exit (1010:9B97).  So the native input decode and the movement
bits are proven to chain through their real data flow, with no VM in the path.

The joystick device (DS:[0010]==1) decodes from hardware ports, not the key table, so it is
skipped (the controller's input source is the keyboard path).  Frames in the scripted-input
mode (DS:A47C != 0) are also skipped: there 9B2E first runs 1010:99F6, which overrides DS:98BE
with a scripted value (boss/cutscene auto-movement) instead of the keyboard decode -- a 9B2E
stage that is not native yet.  The separate movement-bits probe still covers those frames via
the VM's actual DS:98BE.

Usage: python -m overkill.probes.verify_native_frame_loop [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe
from overkill.recovered.domain.frame_loop import FrameInput
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.frame_loop import native_player_frame_step

CS = 0x1010
STAGE_ENTRY_IP = 0x9B6F
STAGE_EXIT_IP = 0x9B97
STRIDE = 0x38
STRIDE_WORDS = STRIDE >> 1
SPECIAL_BASE = 0x237C
OFF_X, OFF_Y = 0x02, 0x04
INPUT_FLAGS = 0x98BE
KEY_STATE_BASE = 0x98C4
NO_CLAMP_GATE = 0xA47C
DEVICE_WORD = 0x0010
CONTROL_MAP_DEFAULT, CONTROL_MAP_ALT = 0x213E, 0x2146
JOYSTICK_DEVICE, ALT_KEYBOARD_DEVICE = 0x0001, 0x0002


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "moved": 0, "joystick": 0, "scripted": 0, "fail": []}
    pending: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        if cs == CS and ip == STAGE_ENTRY_IP and key not in pending:
            ds = cpu.s.ds & 0xFFFF
            device = cpu.mem.rw(ds, DEVICE_WORD)
            if device == JOYSTICK_DEVICE:
                res["joystick"] += 1
                return
            no_clamp = cpu.mem.rw(ds, NO_CLAMP_GATE) != 0
            if no_clamp:
                # DS:A47C != 0: 9B2E ran 99F6 first, overriding DS:98BE with scripted input
                # (boss/cutscene auto-movement) -- a stage the native controller does not model yet.
                res["scripted"] += 1
                return
            ss = cpu.s.ss & 0xFFFF
            bp = cpu.s.bp & 0xFFFF
            table = CONTROL_MAP_ALT if device == ALT_KEYBOARD_DEVICE else CONTROL_MAP_DEFAULT
            frame_input = FrameInput(
                control_map=tuple(cpu.mem.rb(ds, (table + k) & 0xFFFF) for k in range(8)),
                key_state=LazyBytes(cpu.mem, ds, KEY_STATE_BASE, 0x100),
            )
            words = tuple(cpu.mem.rw(ss, (bp + 2 * j) & 0xFFFF) for j in range(STRIDE_WORDS))
            special_pool = ObjectPool(base=SPECIAL_BASE, stride=STRIDE, slots=(words,))
            out = native_player_frame_step(special_pool, frame_input, no_clamp=no_clamp)
            vm_flags = cpu.mem.rb(ds, INPUT_FLAGS)
            pending[key] = (ss, bp, out, vm_flags)
        else:
            p = pending.get(key)
            if p is not None and cs == CS and ip == STAGE_EXIT_IP:
                ss, bp, out, vm_flags = pending.pop(key)
                actual_xy = (cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                             cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF))
                predicted_xy = (out.special_pool.x_word(0), out.special_pool.y_word(0))
                res["calls"] += 1
                if out.moved:
                    res["moved"] += 1
                if out.input_flags == vm_flags and predicted_xy == actual_xy:
                    res["ok"] += 1
                else:
                    res["fail"].append((out.input_flags, vm_flags, predicted_xy, actual_xy))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native frame-controller player step vs VM 9B2E "
          f"(raw key-state -> decode -> movement, compare flags + anchor): "
          f"calls={res['calls']} ok={res['ok']} moved={res['moved']} joystick_skipped={res['joystick']} "
          f"scripted_skipped={res['scripted']} fail={len(res['fail'])}")
    for pf, vf, pxy, axy in res["fail"][:8]:
        print(f"  FAIL flags pred={hex(pf)} vm={hex(vf)}  anchor pred={tuple(hex(v) for v in pxy)} "
              f"vm={tuple(hex(v) for v in axy)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the native controller reproduces the VM from raw key state (decode + movement chained)"
          if ok else ("NO-EVENTS -- the 9B2E player stage was not reached"
                      if res["calls"] == 0 and not res["fail"]
                      else "FAIL -- the native controller diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
