"""Produced-vs-VM verify: the BEC5 moving-object reaction outcome vs the VM.

When the 62F6 scan finds an overlap it enters the BEC5 collision handler, which decides the
*scanning* object's fate by the collided candidate's logic id: take the BF25 damage chain, or die
instantly (counter_20:=0 -> BFC7).  At each BEC5 entry on the oracle side this projects the candidate
(logic id + sprite) and the DS:A8C2 final-boss flag, runs the pure ``bec5_moving_object_outcome``,
and checks the VM:

* predicted ``"damage"``        -> the VM reaches the damage chain (BF25 or the variant-2 BF2D entry),
  and ``enter_at_bf25`` matches which of the two it enters at;
* predicted ``"instant_death"`` -> the VM reaches BFC7 *without* the damage chain;
* predicted ``"owner_or_unclassified"`` -> the owner-link / no-op fallback this classifier does not
  own, reported and skipped.

Usage: python -m overkill.probes.verify_native_bec5_outcome [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import load_demo, run_ref_step_probe
from overkill.recovered.systems.collision import bec5_moving_object_outcome

CS = 0x1010
BEC5_IP = 0xBEC5
BF25_IP, BF2D_IP, BFC7_IP = 0xBF25, 0xBF2D, 0xBFC7
OFF_CAND_SPRITE, OFF_CAND_LOGIC_ID = 0x08, 0x18
A8C2 = 0xA8C2


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "damage": 0, "instant": 0, "unclassified": 0, "fail": []}
    pending: dict[int, dict] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        p = pending.get(key)
        if cs == CS and ip == BEC5_IP and p is None:
            ds = cpu.s.ds & 0xFFFF
            ss = cpu.s.ss & 0xFFFF
            bx = cpu.s.bx & 0xFFFF
            predicted = bec5_moving_object_outcome(
                candidate_logic_id=cpu.mem.rw(ds, (bx + OFF_CAND_LOGIC_ID) & 0xFFFF),
                a8c2_boss_mode=cpu.mem.rw(ds, A8C2) == 0x0001,
                candidate_sprite=cpu.mem.rw(ds, (bx + OFF_CAND_SPRITE) & 0xFFFF))
            ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
            pending[key] = {"ret": ret_addr, "predicted": predicted, "first_damage_ip": None, "saw_bfc7": False}
        elif p is not None and cs == CS:
            if ip in (BF25_IP, BF2D_IP) and p["first_damage_ip"] is None:
                p["first_damage_ip"] = ip
            elif ip == BFC7_IP:
                p["saw_bfc7"] = True
            elif ip == p["ret"]:
                pending.pop(key)
                predicted = p["predicted"]
                if p["first_damage_ip"] is not None:
                    vm_kind, vm_enter = "damage", p["first_damage_ip"] == BF25_IP
                elif p["saw_bfc7"]:
                    vm_kind, vm_enter = "instant_death", False
                else:
                    vm_kind, vm_enter = "owner_noop", False
                if predicted.kind == "owner_or_unclassified":
                    res["unclassified"] += 1
                    return
                res["calls"] += 1
                res["damage" if predicted.kind == "damage" else "instant"] += 1
                ok = predicted.kind == vm_kind and (predicted.kind != "damage" or predicted.enter_at_bf25 == vm_enter)
                if ok:
                    res["ok"] += 1
                else:
                    res["fail"].append((predicted.kind, predicted.enter_at_bf25, vm_kind, vm_enter))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native BEC5 moving-object outcome vs VM "
          f"(project candidate+A8C2 -> classify -> compare damage/instant path): "
          f"calls={res['calls']} ok={res['ok']} damage={res['damage']} instant={res['instant']} "
          f"unclassified={res['unclassified']} fail={len(res['fail'])}")
    for pk, pe, vk, ve in res["fail"][:8]:
        print(f"  FAIL predicted={pk}(enter_bf25={pe}) vm={vk}(enter_bf25={ve})")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the native BEC5 outcome reproduces the VM's scanner fate"
          if ok else ("NO-EVENTS -- no classified BEC5 reaction reached"
                      if res["calls"] == 0 and not res["fail"]
                      else "FAIL -- the BEC5 outcome diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
