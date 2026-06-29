"""Produced-vs-VM verify: the native object-overlap scan vs the VM's 1010:62F6.

62F6 is the object-vs-object overlap scan: a moving object (the scanner at SS:BP) walks the
gameplay object pool (DS:2B5C) and, on the first overlapping candidate, jumps to the BEC5
collision handler with BX pointing at that slot; if none overlaps it returns without BEC5.

At each 62F6 entry on the oracle side this projects the scanner's fields + the whole gameplay
pool, runs the pure ``object_overlap_scan_62f6``, and asserts its prediction matches the VM:
when it predicts a hit index ``i`` the VM must reach BEC5 with ``BX == 2B5C + i*38h``; when it
predicts ``None`` the VM must return from 62F6 without reaching BEC5.

Usage: python -m overkill.probes.verify_native_overlap_scan_62f6 [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import load_demo, run_ref_step_probe
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.collision import object_overlap_scan_62f6

CS = 0x1010
SCAN_ENTRY_IP = 0x62F6
BEC5_IP = 0xBEC5
GAMEPLAY_BASE = 0x2B5C
GAMEPLAY_COUNT = 0x22
STRIDE = 0x38
STRIDE_WORDS = STRIDE >> 1
OFF_X, OFF_Y, OFF_OBJECT_TYPE, OFF_DRAW_LAYER, OFF_LOGIC_ID = 0x02, 0x04, 0x14, 0x16, 0x18


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "hit": 0, "empty": 0, "fail": []}
    pending: dict[int, dict] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        p = pending.get(key)
        if cs == CS and ip == SCAN_ENTRY_IP and p is None:
            ss = cpu.s.ss & 0xFFFF
            ds = cpu.s.ds & 0xFFFF
            bp = cpu.s.bp & 0xFFFF
            slots = tuple(
                tuple(cpu.mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF) for j in range(STRIDE_WORDS))
                for i in range(GAMEPLAY_COUNT))
            predicted = object_overlap_scan_62f6(
                scanner_active_word=cpu.mem.rw(ss, bp),
                scanner_x_word=cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                scanner_y_word=cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
                scanner_draw_layer=cpu.mem.rw(ss, (bp + OFF_DRAW_LAYER) & 0xFFFF),
                scanner_logic_id=cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF),
                scanner_object_type=cpu.mem.rw(ss, (bp + OFF_OBJECT_TYPE) & 0xFFFF),
                candidates=ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=slots))
            ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
            pending[key] = {"ret": ret_addr, "predicted": predicted, "bec5_bx": None}
        elif p is not None and cs == CS and ip == BEC5_IP and p["bec5_bx"] is None:
            p["bec5_bx"] = cpu.s.bx & 0xFFFF
        elif p is not None and cs == CS and ip == p["ret"]:
            pending.pop(key)
            predicted = p["predicted"]
            expected_bx = None if predicted is None else (GAMEPLAY_BASE + predicted * STRIDE) & 0xFFFF
            res["calls"] += 1
            if predicted is None:
                res["empty"] += 1
            else:
                res["hit"] += 1
            if expected_bx == p["bec5_bx"]:
                res["ok"] += 1
            else:
                res["fail"].append((predicted, expected_bx, p["bec5_bx"]))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native overlap scan vs VM 62F6 "
          f"(project scanner+pool -> scan -> compare BEC5 hit slot): "
          f"calls={res['calls']} ok={res['ok']} hit={res['hit']} empty={res['empty']} fail={len(res['fail'])}")
    for predicted, exp, act in res["fail"][:8]:
        print(f"  FAIL predicted_idx={predicted} expected_bx={exp if exp is None else hex(exp)} "
              f"vm_bec5_bx={act if act is None else hex(act)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the native overlap scan reproduces the VM's hit candidate"
          if ok else ("NO-EVENTS -- 62F6 was not reached" if res["calls"] == 0 and not res["fail"]
                      else "FAIL -- the scan diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
