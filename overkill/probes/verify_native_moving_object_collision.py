"""Produced-vs-VM verify: the whole moving-object collision (scan + BEC5 + hit) vs the VM.

This grounds the collision-island capstone (``resolve_moving_object_collision``) end-to-end: at each
BC4B contact scan (1010:62F6 entry) on the oracle side it projects the scanning object (SS:BP) + the
gameplay candidate pool (DS:2B5C) + the per-frame globals (DS:A8C2 boss flag, DS:BEDC difficulty),
runs the composed system, and asserts the scanner's post-collision state at the scan's return matches
the VM:

* not collided -> the scanner's counter_20 / logic_id / sprite are unchanged;
* died        -> counter_20 == result, logic_id == 1, sprite == the C037 death sprite;
* survived    -> counter_20 == result (the BF25 chain), logic_id / sprite unchanged.

The owner-link / no-op BEC5 fallback (``unclassified``) and the C037 unverified object-type path are
reported and skipped.

Usage: python -m overkill.probes.verify_native_moving_object_collision [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import load_demo, run_ref_step_probe
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.collision import resolve_moving_object_collision

CS = 0x1010
SCAN_ENTRY_IP = 0x62F6
GAMEPLAY_BASE, GAMEPLAY_COUNT, STRIDE = 0x2B5C, 0x22, 0x38
STRIDE_WORDS = STRIDE >> 1
OFF_X, OFF_Y, OFF_SPRITE, OFF_OBJECT_TYPE, OFF_DRAW_LAYER, OFF_LOGIC_ID, OFF_COUNTER_20 = \
    0x02, 0x04, 0x08, 0x14, 0x16, 0x18, 0x20
A8C2, BEDC = 0xA8C2, 0xBEDC
DEATH_LOGIC_ID = 0x0001


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "died": 0, "survived": 0, "no_collision": 0,
           "unclassified": 0, "bad_type": 0, "cand_calls": 0, "cand_ok": 0, "cand_deact": 0, "fail": []}
    pending: dict[int, dict] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        p = pending.get(key)
        if cs == CS and ip == SCAN_ENTRY_IP and p is None:
            ds = cpu.s.ds & 0xFFFF
            ss = cpu.s.ss & 0xFFFF
            bp = cpu.s.bp & 0xFFFF
            slots = tuple(
                tuple(cpu.mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF) for j in range(STRIDE_WORDS))
                for i in range(GAMEPLAY_COUNT))
            pre = (cpu.mem.rw(ss, (bp + OFF_COUNTER_20) & 0xFFFF),
                   cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF),
                   cpu.mem.rw(ss, (bp + OFF_SPRITE) & 0xFFFF))
            try:
                predicted = resolve_moving_object_collision(
                    scanner_active_word=cpu.mem.rw(ss, bp),
                    scanner_x_word=cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                    scanner_y_word=cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
                    scanner_draw_layer=cpu.mem.rw(ss, (bp + OFF_DRAW_LAYER) & 0xFFFF),
                    scanner_logic_id=pre[1],
                    scanner_object_type=cpu.mem.rw(ss, (bp + OFF_OBJECT_TYPE) & 0xFFFF),
                    scanner_counter_20=pre[0],
                    candidates=ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=slots),
                    a8c2_boss_mode=cpu.mem.rw(ds, A8C2) == 0x0001,
                    bedc=cpu.mem.rw(ds, BEDC))
            except ValueError:
                res["bad_type"] += 1  # C037 unverified object-type death path
                pending[key] = {"ret": cpu.mem.rw(ss, cpu.s.sp & 0xFFFF), "skip": True}
                return
            cand_pre_active = slots[predicted.hit_index][0] if predicted.hit_index is not None else None
            pending[key] = {"ret": cpu.mem.rw(ss, cpu.s.sp & 0xFFFF), "skip": False,
                            "bp": bp, "pre": pre, "predicted": predicted, "cand_pre_active": cand_pre_active}
        elif p is not None and cs == CS and ip == p["ret"]:
            pending.pop(key)
            if p["skip"]:
                return
            predicted, pre, bp = p["predicted"], p["pre"], p["bp"]
            ss = cpu.s.ss & 0xFFFF
            post = (cpu.mem.rw(ss, (bp + OFF_COUNTER_20) & 0xFFFF),
                    cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF),
                    cpu.mem.rw(ss, (bp + OFF_SPRITE) & 0xFFFF))
            if predicted.unclassified:
                res["unclassified"] += 1
                return
            if not predicted.collided:
                expected = pre  # unchanged
                res["no_collision"] += 1
            elif predicted.died:
                expected = (predicted.new_counter_20, DEATH_LOGIC_ID, predicted.death_transition.sprite_or_state)
                res["died"] += 1
            else:
                expected = (predicted.new_counter_20, pre[1], pre[2])  # counter changes; logic_id/sprite unchanged
                res["survived"] += 1
            res["calls"] += 1
            if expected == post:
                res["ok"] += 1
            else:
                res["fail"].append((expected, post))
            # Also verify the struck candidate's active word: deactivated -> 0, else unchanged.
            if predicted.hit_index is not None:
                res["cand_calls"] += 1
                cand_active = cpu.mem.rw(cpu.s.ds & 0xFFFF,
                                         (GAMEPLAY_BASE + predicted.hit_index * STRIDE) & 0xFFFF)
                expected_cand = 0 if predicted.candidate_deactivated else p["cand_pre_active"]
                if predicted.candidate_deactivated:
                    res["cand_deact"] += 1
                if cand_active == expected_cand:
                    res["cand_ok"] += 1
                else:
                    res["fail"].append(((expected_cand,), (cand_active,)))  # candidate active mismatch

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native moving-object collision vs VM "
          f"(scan+BEC5+hit -> compare scanner post-state): calls={res['calls']} ok={res['ok']} "
          f"died={res['died']} survived={res['survived']} no_collision={res['no_collision']} "
          f"unclassified={res['unclassified']} bad_type={res['bad_type']} "
          f"cand={res['cand_ok']}/{res['cand_calls']}(deact={res['cand_deact']}) fail={len(res['fail'])}")
    for exp, act in res["fail"][:8]:
        print(f"  FAIL expected(counter,logic,sprite)={tuple(hex(v) for v in exp)} "
              f"actual={tuple(hex(v) for v in act)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the composed moving-object collision reproduces the VM scanner post-state"
          if ok else ("NO-EVENTS -- no classified collision reached"
                      if res["calls"] == 0 and not res["fail"]
                      else "FAIL -- the composed collision diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
