"""Produced-vs-VM verify: the native object-update driver as a whole GAMEPLAY PASS vs the VM.

The per-slot driver-verify proves each handler byte-exact at its own boundary; this proves the
driver as a *pass* -- one ``native_object_update_pool`` call over the whole gameplay table (DS:2B5C)
reproduces the VM's A9E0 object scan of that table.

The A9E0 scan is two loops: the first (effect table, DS:32CA pointers) increments the tick DS:2340
once per entry, so its per-slot globals evolve and it can't be frozen-projected.  But DS:2346 is
reset at AA07 and the second loop (gameplay table, DS:8D12 pointers) never touches DS:2340 -- so
across the gameplay scan the per-frame globals are constant.  So at AA0D (gameplay-loop setup, after
DS:2346:=0) this projects the gameplay table + the frozen globals, runs the driver once, and at the
scan exit (AA25) compares every slot that was active with a native logic_id at entry.  Non-native
slots (the VM advances, the driver leaves to the VM) and slots that spawned mid-scan are excluded;
a contact-death sprite override (logic_id -> 1) is deferred exactly as the per-slot verify does.

Usage: python -m overkill.probes.verify_native_object_pass [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.object_update import NATIVE_OBJECT_HANDLERS, native_object_update_pool

CS = 0x1010
SETUP_IP = 0xAA0D       # mov cx,0022h -- gameplay-loop setup, after AA07 reset DS:2346:=0
EXIT_IP = 0xAA25        # far call after the gameplay loop -- scan done
GAMEPLAY_BASE = 0x2B5C
GAMEPLAY_COUNT = 0x22
STRIDE = 0x38
STRIDE_WORDS = STRIDE >> 1
SKIP_SPRITE_LOGIC_IDS = frozenset((0x001D, 0x0014))  # B86D, B9F0: contact path may override sprite
COLLISION_DEATH_LOGIC_ID = 0x0001
# slot record field offsets
OFF_ACTIVE, OFF_X, OFF_Y, OFF_DIR, OFF_SPRITE, OFF_LOGIC, OFF_SUBSTATE = 0, 0x02, 0x04, 0x06, 0x08, 0x18, 0x1C
LOGIC_WORD = OFF_LOGIC >> 1
# DS globals (same projection as verify_native_object_update_driver)
REF_BOX_X, REF_BOX_Y, A278, BDAC = 0x237E, 0x2380, 0xA278, 0xBDAC
REF_BOX_SCAN, A47E, A7A0, A47C = 0x2390, 0xA47E, 0xA7A0, 0xA47C
DELTA_2342, PHASE_2328, STEP_MODE, DIR_TABLE = 0x2342, 0x2328, 0x2312, 0xA348
A482, FRAME_233C, DELTA_X_2346, BEDC, TICK_2340 = 0xA482, 0x233C, 0x2346, 0xBEDC, 0x2340
TILE_ORIGIN, TILE_ROW, TILE_CLASS, TILE_PLANE_PTR = 0x234E, 0x2350, 0xC3AA, 0x9592


def _six(words: tuple) -> tuple:
    return (words[OFF_SUBSTATE >> 1], words[OFF_DIR >> 1], words[OFF_SPRITE >> 1],
            words[OFF_X >> 1], words[OFF_Y >> 1], words[OFF_ACTIVE >> 1])


def _six_cpu(cpu, ss: int, base: int) -> tuple:
    return tuple(cpu.mem.rw(ss, (base + off) & 0xFFFF)
                 for off in (OFF_SUBSTATE, OFF_DIR, OFF_SPRITE, OFF_X, OFF_Y, OFF_ACTIVE))


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"frames": 0, "slots": 0, "ok": 0, "skip": 0, "sprite_deferred": 0, "fail": []}
    pending: dict[int, tuple] = {}
    class_cache: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        if cs == CS and ip == SETUP_IP and key not in pending:
            ds = cpu.s.ds & 0xFFFF
            ss = cpu.s.ss & 0xFFFF
            class_table = class_cache.get(ds)
            if class_table is None:
                class_table = tuple(cpu.mem.rb(ds, (TILE_CLASS + k) & 0xFFFF) for k in range(0x100))
                class_cache[ds] = class_table
            g = ObjectUpdateGlobals(
                ref_box_x=cpu.mem.rw(ds, REF_BOX_X), ref_box_y=cpu.mem.rw(ds, REF_BOX_Y),
                a278=cpu.mem.rw(ds, A278), tile_probe_suppressed=cpu.mem.rw(ds, BDAC) == 0x0001,
                tiles=LevelTileContext(
                    origin_x_word=cpu.mem.rw(ds, TILE_ORIGIN), row_base_word=cpu.mem.rw(ds, TILE_ROW),
                    tile_plane=LazyBytes(cpu.mem, cpu.mem.rw(cs, TILE_PLANE_PTR), 0, 0x10000),
                    class_table=class_table),
                ref_box_scan=cpu.mem.rw(ds, REF_BOX_SCAN), a47e=cpu.mem.rw(ds, A47E),
                a7a0=cpu.mem.rw(ds, A7A0), vertical_delta=cpu.mem.rw(ds, DELTA_2342),
                phase_2328=cpu.mem.rw(ds, PHASE_2328), step_mode=cpu.mem.rw(ds, STEP_MODE),
                direction_table=tuple(cpu.mem.rb(ds, (DIR_TABLE + k) & 0xFFFF) for k in range(16)),
                global_disable=cpu.mem.rw(ds, A47C), a482=cpu.mem.rw(ds, A482),
                frame_233c=cpu.mem.rw(ds, FRAME_233C), horizontal_delta=cpu.mem.rw(ds, DELTA_X_2346),
                difficulty=cpu.mem.rw(ds, BEDC), tick=cpu.mem.rw(ds, TICK_2340))
            slots = tuple(
                tuple(cpu.mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF) for j in range(STRIDE_WORDS))
                for i in range(GAMEPLAY_COUNT))
            out = native_object_update_pool(ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=slots), g)
            pending[key] = (ss, ds, slots, out)
        else:
            p = pending.get(key)
            if p is not None and cs == CS and ip == EXIT_IP:
                ss, ds, slots_in, out = pending.pop(key)
                res["frames"] += 1
                for i in range(GAMEPLAY_COUNT):
                    entry = slots_in[i]
                    if entry[OFF_ACTIVE >> 1] == 0 or entry[LOGIC_WORD] not in NATIVE_OBJECT_HANDLERS:
                        res["skip"] += 1
                        continue
                    base = (GAMEPLAY_BASE + i * STRIDE) & 0xFFFF
                    predicted = _six(out.slots[i])
                    actual = _six_cpu(cpu, ds, base)  # gameplay table is DS-relative; SS==DS here
                    if entry[LOGIC_WORD] in SKIP_SPRITE_LOGIC_IDS and \
                            cpu.mem.rw(ds, (base + OFF_LOGIC) & 0xFFFF) == COLLISION_DEATH_LOGIC_ID:
                        res["sprite_deferred"] += 1
                        predicted = predicted[:2] + predicted[3:]
                        actual = actual[:2] + actual[3:]
                    res["slots"] += 1
                    if predicted == actual:
                        res["ok"] += 1
                    else:
                        res["fail"].append((i, predicted, actual))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native object PASS vs VM gameplay scan "
          f"(project DS:2B5C + frozen globals -> drive once -> compare at AA25): "
          f"frames={res['frames']} slots={res['slots']} ok={res['ok']} skip={res['skip']} "
          f"sprite_deferred={res['sprite_deferred']} fail={len(res['fail'])}")
    for i, predicted, actual in res["fail"][:8]:
        print(f"  FAIL slot[{i}] predicted={tuple(hex(v) for v in predicted)} actual={tuple(hex(v) for v in actual)}")
    ok = res["slots"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the driver reproduces the VM's whole gameplay object pass"
          if ok else ("NO-EVENTS -- no native gameplay slot scanned" if res["slots"] == 0 and not res["fail"]
                      else "FAIL -- the pass diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
