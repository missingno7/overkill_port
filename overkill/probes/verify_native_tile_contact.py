"""Produced-vs-VM verify: the native tile/contact probe vs the VM's 1010:4FF9.

4FF9 is the worker of the 9B2E contact stage (9CB6): a non-destructive tile-contact probe that
returns CF (set = the slot contacts a solid tile).  At each 4FF9 entry on the oracle side this
projects the probed slot (SS:BP +2/+4 position, +8 side index), the DS:214E dx/dy offset table, and
the level tile context (DS:234E/2350 + the CS:[9592] plane + the DS:C3AA class table), runs the pure
``probe_tile_contact_4ff9``, and asserts the predicted contact equals the VM's CF at 4FF9's return.

This grounds the contact composition (gate + DS:214E offset + compute_tile_probe_5073 + the
one/two-column sampling via the class table) end-to-end against the VM.

Usage: python -m overkill.probes.verify_native_tile_contact [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from dos_re.cpu import CF
from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.tilemap import probe_tile_contact_4ff9

CS = 0x1010
CONTACT_ENTRY_IP = 0x4FF9
OFF_X, OFF_Y, OFF_SIDE = 0x02, 0x04, 0x08
OFFSET_TABLE = 0x214E       # three signed dx/dy word pairs (12 bytes)
TILE_ORIGIN, TILE_ROW, TILE_CLASS, TILE_PLANE_PTR = 0x234E, 0x2350, 0xC3AA, 0x9592


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "contact": 0, "fail": []}
    pending: dict[int, tuple] = {}
    class_cache: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        if cs == CS and ip == CONTACT_ENTRY_IP and key not in pending:
            ss = cpu.s.ss & 0xFFFF
            ds = cpu.s.ds & 0xFFFF
            bp = cpu.s.bp & 0xFFFF
            class_table = class_cache.get(ds)
            if class_table is None:
                class_table = tuple(cpu.mem.rb(ds, (TILE_CLASS + k) & 0xFFFF) for k in range(0x100))
                class_cache[ds] = class_table
            tiles = LevelTileContext(
                origin_x_word=cpu.mem.rw(ds, TILE_ORIGIN), row_base_word=cpu.mem.rw(ds, TILE_ROW),
                tile_plane=LazyBytes(cpu.mem, cpu.mem.rw(cs, TILE_PLANE_PTR), 0, 0x10000),
                class_table=class_table)
            predicted = probe_tile_contact_4ff9(
                object_x_word=cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                object_y_word=cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
                side_index_word=cpu.mem.rw(ss, (bp + OFF_SIDE) & 0xFFFF),
                offset_table=tuple(cpu.mem.rb(ds, (OFFSET_TABLE + k) & 0xFFFF) for k in range(12)),
                tiles=tiles)
            ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
            pending[key] = (ret_addr, predicted)
        else:
            p = pending.get(key)
            if p is not None and cs == CS and ip == p[0]:
                _ret, predicted = pending.pop(key)
                actual = cpu.get_flag(CF)
                res["calls"] += 1
                if predicted:
                    res["contact"] += 1
                if predicted == actual:
                    res["ok"] += 1
                else:
                    res["fail"].append((predicted, actual))

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native tile-contact probe vs VM 4FF9 "
          f"(project slot+offset-table+tiles -> probe -> compare CF): "
          f"calls={res['calls']} ok={res['ok']} contact={res['contact']} fail={len(res['fail'])}")
    for predicted, actual in res["fail"][:8]:
        print(f"  FAIL predicted_contact={predicted} vm_CF={actual}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- the native contact probe reproduces the VM's CF"
          if ok else ("NO-EVENTS -- 4FF9 was not reached" if res["calls"] == 0 and not res["fail"]
                      else "FAIL -- the contact probe diverged from the VM"))
    return 0 if (not res["fail"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
