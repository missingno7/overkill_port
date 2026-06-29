"""Whole-driver verify: the VM-free native object-update driver vs the VM, per native slot.

Upgrades the driver (overkill.recovered.systems.object_update) from unit-tested wiring to a VM-verified
runtime piece.  At each AE09/AED8 handler entry on the oracle side it projects the slot's full record
(SS:BP) into a 1-slot ``ObjectPool`` + the per-frame ``ObjectUpdateGlobals`` (DS), runs the driver
(``native_object_update_pool``), and asserts the driven slot's post-frame fields equal the VM's at the
handler's return.  This grounds the cpu->ObjectPool projection, the pool field accessors, and the
driver's write-back against the VM end-to-end (the handlers' arithmetic is already gate-proven, and both
AE09 and AED8 produce the complete slot at their RET, so the handler boundary is the slot's final state).

Driver slots the handler leaves unchanged (AED8's timer-death / out-of-range-direction fallback) are
reported as skips, not compared.

Usage: python -m overkill.probes.verify_native_object_update_driver [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.object_update import native_object_update_pool
from overkill.recovered.views.object_slots import (
    OFF_ACTIVE_WORD,
    OFF_DIRECTION_OR_STEP,
    OFF_LOGIC_ID,
    OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE,
    OFF_X,
    OFF_Y,
)

CS = 0x1010
STRIDE = 0x38
STRIDE_WORDS = STRIDE >> 1
HANDLER_ENTRY_IPS = (0xAE09, 0xAED8, 0xB86D, 0xB9F0)  # AE09/AED8 RET; B86D/B9F0 tail-jump to BC4B, chains RET here
SKIP_SPRITE_LOGIC_IDS = frozenset((0x001D, 0x0014))  # B86D, B9F0: the deferred contact path may override sprite
COLLISION_DEATH_LOGIC_ID = 0x0001  # BFC7 -> C037 sets logic_id 1; the only contact-path sprite change
LOGIC_ID_WORD = 0x18 >> 1
REF_BOX_X, REF_BOX_Y, A278, BDAC = 0x237E, 0x2380, 0xA278, 0xBDAC
REF_BOX_SCAN, A47E, A7A0, A47C = 0x2390, 0xA47E, 0xA7A0, 0xA47C  # B86D/B9F0 + BC4B globals
DELTA_2342, PHASE_2328, STEP_MODE, DIR_TABLE = 0x2342, 0x2328, 0x2312, 0xA348
A482, FRAME_233C, DELTA_X_2346, BEDC, TICK_2340 = 0xA482, 0x233C, 0x2346, 0xBEDC, 0x2340  # B9F0
TILE_ORIGIN, TILE_ROW, TILE_CLASS, TILE_PLANE_PTR = 0x234E, 0x2350, 0xC3AA, 0x9592


def _six_from_cpu(cpu, ss: int, bp: int) -> tuple:
    return (
        cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
        cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF),
    )


def _six_from_pool(pool: ObjectPool) -> tuple:
    return (pool.substate(0), pool.direction_word(0), pool.sprite_word(0),
            pool.x_word(0), pool.y_word(0), pool.active_word(0))


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "skip": 0, "sprite_deferred": 0, "fail": []}
    pending: dict[int, tuple] = {}
    class_cache: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        if cs == CS and ip in HANDLER_ENTRY_IPS and key not in pending:
            ss = cpu.s.ss & 0xFFFF
            ds = cpu.s.ds & 0xFFFF
            bp = cpu.s.bp & 0xFFFF
            words = tuple(cpu.mem.rw(ss, (bp + 2 * j) & 0xFFFF) for j in range(STRIDE_WORDS))
            class_table = class_cache.get(ds)
            if class_table is None:
                class_table = tuple(cpu.mem.rb(ds, (TILE_CLASS + k) & 0xFFFF) for k in range(0x100))
                class_cache[ds] = class_table
            g = ObjectUpdateGlobals(
                ref_box_x=cpu.mem.rw(ds, REF_BOX_X),
                ref_box_y=cpu.mem.rw(ds, REF_BOX_Y),
                a278=cpu.mem.rw(ds, A278),
                tile_probe_suppressed=cpu.mem.rw(ds, BDAC) == 0x0001,
                tiles=LevelTileContext(
                    origin_x_word=cpu.mem.rw(ds, TILE_ORIGIN),
                    row_base_word=cpu.mem.rw(ds, TILE_ROW),
                    tile_plane=LazyBytes(cpu.mem, cpu.mem.rw(cs, TILE_PLANE_PTR), 0, 0x10000),
                    class_table=class_table,
                ),
                ref_box_scan=cpu.mem.rw(ds, REF_BOX_SCAN),
                a47e=cpu.mem.rw(ds, A47E),
                a7a0=cpu.mem.rw(ds, A7A0),
                vertical_delta=cpu.mem.rw(ds, DELTA_2342),
                phase_2328=cpu.mem.rw(ds, PHASE_2328),
                step_mode=cpu.mem.rw(ds, STEP_MODE),
                direction_table=tuple(cpu.mem.rb(ds, (DIR_TABLE + k) & 0xFFFF) for k in range(16)),
                global_disable=cpu.mem.rw(ds, A47C),
                a482=cpu.mem.rw(ds, A482),
                frame_233c=cpu.mem.rw(ds, FRAME_233C),
                horizontal_delta=cpu.mem.rw(ds, DELTA_X_2346),
                difficulty=cpu.mem.rw(ds, BEDC),
                tick=cpu.mem.rw(ds, TICK_2340),
            )
            out = native_object_update_pool(ObjectPool(base=0, stride=STRIDE, slots=(words,)), g)
            advanced = out.slots[0] != words
            ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
            pending[key] = (ss, bp, ret_addr, out, advanced, words[LOGIC_ID_WORD])
        else:
            p = pending.get(key)
            if p is not None and cs == CS and ip == p[2]:
                ss, bp, _ret, out, advanced, logic_id = pending.pop(key)
                if not advanced:
                    res["skip"] += 1  # handler returned None (death/oob) -> driver leaves it to the VM
                    return
                predicted = _six_from_pool(out)
                actual = _six_from_cpu(cpu, ss, bp)
                if logic_id in SKIP_SPRITE_LOGIC_IDS and \
                        cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF) == COLLISION_DEATH_LOGIC_ID:
                    # Only a contact-path collision death (BFC7 -> logic_id 1) overrides the sprite, and
                    # that path is deferred -- compare the five fields the driver owns.  Every non-death
                    # slot compares all six (the movement sprite is the final sprite).
                    res["sprite_deferred"] += 1
                    predicted = predicted[:2] + predicted[3:]
                    actual = actual[:2] + actual[3:]
                res["calls"] += 1
                if predicted == actual:
                    res["ok"] += 1
                else:
                    res["fail"].append((predicted, actual))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native object-update DRIVER vs VM (project -> drive "
          f"-> compare): calls={res['calls']} ok={res['ok']} skip={res['skip']} "
          f"sprite_deferred={res['sprite_deferred']} fail={len(res['fail'])}")
    for predicted, actual in res["fail"][:8]:
        print(f"  FAIL predicted={tuple(hex(v) for v in predicted)} actual={tuple(hex(v) for v in actual)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the VM-free driver reproduces the VM per native slot (projection + drive + write-back)"
          if ok else ("NO-EVENTS -- no native slot reached" if res["calls"] == 0 and not res["fail"]
                      else "FAIL -- driver diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
