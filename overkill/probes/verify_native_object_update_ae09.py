"""Verify the native AE09 WHOLE slot transform (object_update_ae09) is byte-exact vs the VM's
1010:AE09 behavior across a gameplay demo -- the §1.2 produced-vs-VM gate for a COMPLETE per-slot
object-update (movement + the AD60 bounds/tile -> active), including the tile-collision path.

AE09 (the EFAE logic_id=0Ch behavior) decrements the slot's substate timer, steps it 3px in its
direction (AF22), then tails into AD60: out of play bounds -> deactivate (BD17 -> active=0); else for
the tile-probe family (draw_layer 2) it samples the tile one map row below (5073 +13 -> 505B) and
deactivates when that tile has class 1; else it survives.  ``object_update_ae09`` composes the recovered
movement (``object_movement_step_ae09``), the AD60 bounds decision, and the tile-probe deactivation
(``object_tile_probe_deactivates_ad60`` over a :class:`LevelTileContext`), predicting the slot's six
post-frame fields: substate +1C, direction +06, sprite +08, x +02, y +04, active +00.  (The BD17 global
counter/spawn writes are separate state, out of scope.)

Step-hook AE09 on the pure-VM (oracle) side: at entry capture the slot fields + draw_layer/logic_id/
DS:BDAC + the level tile context (DS:234E origin, DS:2350 row base, the CS:[9592] tile plane, the
DS:C3AA class table) + the return address; predict; when control returns (the AD60 tail RETs to AE09's
caller) read the slot's six post fields and assert they equal the prediction -- for every AE09 object.

Shares the verify scaffolding in ``overkill.probes._harness``; generalised by
``overkill.probes.verify_native_object_update`` (the per-logic coverage gate).

Usage:
    python -m overkill.probes.verify_native_object_update_ae09 [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.objects import object_update_ae09
from overkill.recovered.views.object_slots import (
    OFF_ACTIVE_WORD,
    OFF_DIRECTION_OR_STEP,
    OFF_HAZARD_CLASS,
    OFF_LOGIC_ID,
    OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE,
    OFF_X,
    OFF_Y,
)

CS = 0x1010
AE09_IP = 0xAE09
RENDER_MODE_BDAC = 0xBDAC       # DS:BDAC; AD60 suppresses the tile-probe when this == 1
TILE_PROBE_ORIGIN_X = 0x234E    # DS:234E
TILE_PROBE_ROW_BASE = 0x2350    # DS:2350
TILE_CLASS_TABLE = 0xC3AA       # DS:C3AA, 256 entries
TILE_PLANE_SEGMENT_PTR = 0x9592  # CS:[9592] -> the raw tile-plane segment


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, tuple] = {}
    class_table_cache: dict[int, tuple] = {}  # DS:C3AA is static; snapshot once (avoid 256 reads/call)

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        if cs == CS and ip == AE09_IP and key not in pending:
            ss = cpu.s.ss & 0xFFFF
            ds = cpu.s.ds & 0xFFFF
            bp = cpu.s.bp & 0xFFFF
            substate = cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
            direction = cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
            x = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
            y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
            active = cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF)
            draw_layer = cpu.mem.rw(ss, (bp + OFF_HAZARD_CLASS) & 0xFFFF)
            logic_id = cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
            bdac = cpu.mem.rw(ds, RENDER_MODE_BDAC)
            class_table = class_table_cache.get(ds)
            if class_table is None:
                class_table = tuple(cpu.mem.rb(ds, (TILE_CLASS_TABLE + i) & 0xFFFF) for i in range(0x100))
                class_table_cache[ds] = class_table
            tiles = LevelTileContext(
                origin_x_word=cpu.mem.rw(ds, TILE_PROBE_ORIGIN_X),
                row_base_word=cpu.mem.rw(ds, TILE_PROBE_ROW_BASE),
                tile_plane=LazyBytes(cpu.mem, cpu.mem.rw(cs, TILE_PLANE_SEGMENT_PTR), 0, 0x10000),
                class_table=class_table,
            )
            predicted = object_update_ae09(
                substate, direction, x, y, active, draw_layer, logic_id, bdac == 0x0001, tiles
            )
            ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
            pending[key] = (ss, bp, ret_addr, predicted)
        elif key in pending and cs == CS and ip == pending[key][2]:
            ss, bp, _ret, predicted = pending.pop(key)
            post = (
                cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF),
                cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
                cpu.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF),
                cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
                cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF),
            )
            pred = (predicted.substate, predicted.direction_or_step, predicted.sprite_or_state,
                    predicted.x_word, predicted.y_word, predicted.active_word)
            res["calls"] += 1
            if pred == post:
                res["ok"] += 1
            else:
                res["fail"].append((pred, post))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native object_update_ae09 vs VM AE09 (movement+active): "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for pred, post in res["fail"][:8]:
        print(f"  FAIL predicted={tuple(hex(v) for v in pred)} actual={tuple(hex(v) for v in post)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native AE09 whole slot transform byte-exact vs the VM across the demo"
          if ok else "CHECK -- no AE09 reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
