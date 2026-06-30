"""Produced-vs-VM verify: the ORDER-DEPENDENT in-place object pass vs the VM's A9E0 effect scan.

The snapshot pass (verify_native_object_pass) is order-independent and carries movement only.  This
verifies the in-place pass that carries collision: at the effect scan's first A9E0 it captures the
DS:32CA walk order (the slots the loop visits, cx=entry_CX down to 1), the entry tick (DS:2340), the
live gameplay candidate pool (DS:2B5C) and the per-frame globals, runs ``native_object_pass_in_place``
(walk in order, advance each slot with its per-entry tick, run the 62F6 collision against the live
candidates, and clear a killed candidate so later scanners skip it), and at the scan exit (AA07)
compares every visited active native slot's post-state -- the 6-tuple + logic_id -- against the VM.

Usage: python -m overkill.probes.verify_native_object_pass_in_place [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.object_update import NATIVE_OBJECT_HANDLERS, native_object_pass_in_place

CS = 0x1010
SCAN_BODY_IP = 0xA9E0          # effect-loop body (cx-down LOOP)
SCAN_EXIT_IP = 0xAA07          # mov [2346],0 -- after the effect loop, before the gameplay loop
TABLE_32CA = 0x32CA
GAMEPLAY_BASE, GAMEPLAY_COUNT = 0x2B5C, 0x22
STRIDE = 0x38
STRIDE_WORDS = STRIDE >> 1
OFF_SUBSTATE, OFF_DIR, OFF_SPRITE, OFF_X, OFF_Y, OFF_ACTIVE, OFF_LOGIC = 0x1C, 0x06, 0x08, 0x02, 0x04, 0x00, 0x18
MAX_WALK = 0x40                # sanity cap on the captured loop count
# per-frame globals (same projection as verify_native_object_update_driver)
REF_BOX_X, REF_BOX_Y, A278, BDAC = 0x237E, 0x2380, 0xA278, 0xBDAC
REF_BOX_SCAN, A47E, A7A0, A47C = 0x2390, 0xA47E, 0xA7A0, 0xA47C
DELTA_2342, PHASE_2328, STEP_MODE, DIR_TABLE = 0x2342, 0x2328, 0x2312, 0xA348
A482, FRAME_233C, DELTA_X_2346, BEDC, TICK_2340 = 0xA482, 0x233C, 0x2346, 0xBEDC, 0x2340
TILE_ORIGIN, TILE_ROW, TILE_CLASS, TILE_PLANE_PTR = 0x234E, 0x2350, 0xC3AA, 0x9592
A8C2_ADDR = 0xA8C2


def _six_logic(words: tuple) -> tuple:
    return (words[OFF_SUBSTATE >> 1], words[OFF_DIR >> 1], words[OFF_SPRITE >> 1],
            words[OFF_X >> 1], words[OFF_Y >> 1], words[OFF_ACTIVE >> 1], words[OFF_LOGIC >> 1])


def _six_logic_cpu(cpu, ds: int, base: int) -> tuple:
    return tuple(cpu.mem.rw(ds, (base + off) & 0xFFFF)
                 for off in (OFF_SUBSTATE, OFF_DIR, OFF_SPRITE, OFF_X, OFF_Y, OFF_ACTIVE, OFF_LOGIC))


def _globals(cpu, ds, cs_seg, class_cache):
    class_table = class_cache.get(ds)
    if class_table is None:
        class_table = tuple(cpu.mem.rb(ds, (TILE_CLASS + k) & 0xFFFF) for k in range(0x100))
        class_cache[ds] = class_table
    return ObjectUpdateGlobals(
        ref_box_x=cpu.mem.rw(ds, REF_BOX_X), ref_box_y=cpu.mem.rw(ds, REF_BOX_Y),
        a278=cpu.mem.rw(ds, A278), tile_probe_suppressed=cpu.mem.rw(ds, BDAC) == 0x0001,
        tiles=LevelTileContext(origin_x_word=cpu.mem.rw(ds, TILE_ORIGIN), row_base_word=cpu.mem.rw(ds, TILE_ROW),
                               tile_plane=LazyBytes(cpu.mem, cpu.mem.rw(cs_seg, TILE_PLANE_PTR), 0, 0x10000),
                               class_table=class_table),
        ref_box_scan=cpu.mem.rw(ds, REF_BOX_SCAN), a47e=cpu.mem.rw(ds, A47E), a7a0=cpu.mem.rw(ds, A7A0),
        vertical_delta=cpu.mem.rw(ds, DELTA_2342), phase_2328=cpu.mem.rw(ds, PHASE_2328),
        step_mode=cpu.mem.rw(ds, STEP_MODE),
        direction_table=tuple(cpu.mem.rb(ds, (DIR_TABLE + k) & 0xFFFF) for k in range(16)),
        global_disable=cpu.mem.rw(ds, A47C), a482=cpu.mem.rw(ds, A482), frame_233c=cpu.mem.rw(ds, FRAME_233C),
        horizontal_delta=cpu.mem.rw(ds, DELTA_X_2346), difficulty=cpu.mem.rw(ds, BEDC),
        a8c2_boss_mode=cpu.mem.rw(ds, A8C2_ADDR) == 0x0001, bedc=cpu.mem.rw(ds, BEDC))


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"frames": 0, "slots": 0, "ok": 0, "skip": 0, "fail": []}
    pending: dict[int, dict] = {}
    in_scan: dict[int, bool] = {}
    class_cache: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        if cs == CS and ip == SCAN_BODY_IP and not in_scan.get(key):
            in_scan[key] = True
            ds = cpu.s.ds & 0xFFFF
            entry_tick = cpu.mem.rw(ds, TICK_2340)
            entry_cx = cpu.s.cx & 0xFFFF
            if not (1 <= entry_cx <= MAX_WALK):
                pending[key] = None
                return
            offsets, words = [], []
            for j in range(entry_cx):
                off = cpu.mem.rw(ds, (TABLE_32CA + (entry_cx - j) * 2) & 0xFFFF)
                offsets.append(off)
                words.append(tuple(cpu.mem.rw(ds, (off + 2 * w) & 0xFFFF) for w in range(STRIDE_WORDS)))
            walk_pool = ObjectPool(base=0, stride=STRIDE, slots=tuple(words))
            gameplay = ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=tuple(
                tuple(cpu.mem.rw(ds, (GAMEPLAY_BASE + s * STRIDE + 2 * w) & 0xFFFF) for w in range(STRIDE_WORDS))
                for s in range(GAMEPLAY_COUNT)))
            out_walk, _ = native_object_pass_in_place(walk_pool, gameplay, _globals(cpu, ds, cs, class_cache),
                                                      entry_tick=entry_tick)
            # Only the LAST visit decides a slot's final state, so map offset -> last walk index.
            last = {off: j for j, off in enumerate(offsets)}
            pending[key] = {"offsets": offsets, "out": out_walk, "entry": walk_pool, "last": last}
        elif cs == CS and ip == SCAN_EXIT_IP and in_scan.get(key):
            in_scan[key] = False
            p = pending.pop(key, None)
            if not p:
                return
            res["frames"] += 1
            ds = cpu.s.ds & 0xFFFF
            entry, out, offsets, last = p["entry"], p["out"], p["offsets"], p["last"]
            for j in range(len(offsets)):
                if last[offsets[j]] != j:
                    continue  # a slot visited again later -> compare only at its last visit
                if entry.active_word(j) == 0 or entry.logic_id(j) not in NATIVE_OBJECT_HANDLERS:
                    res["skip"] += 1
                    continue
                predicted = _six_logic(out.slots[j])
                actual = _six_logic_cpu(cpu, ds, offsets[j])
                res["slots"] += 1
                if predicted == actual:
                    res["ok"] += 1
                else:
                    res["fail"].append((offsets[j], predicted, actual))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native IN-PLACE object pass vs VM A9E0 effect scan "
          f"(walk order + per-entry tick + in-place collision): frames={res['frames']} slots={res['slots']} "
          f"ok={res['ok']} skip={res['skip']} fail={len(res['fail'])}")
    for off, predicted, actual in res["fail"][:8]:
        print(f"  FAIL slot@{off:#06x} predicted={tuple(hex(v) for v in predicted)} "
              f"actual={tuple(hex(v) for v in actual)}")
    ok = res["slots"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the in-place pass reproduces the VM's effect scan (order + tick + collision)"
          if ok else ("NO-EVENTS -- the effect scan was not reached" if res["slots"] == 0 and not res["fail"]
                      else "FAIL -- the in-place pass diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
