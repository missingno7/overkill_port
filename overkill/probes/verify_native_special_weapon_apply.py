"""Driven-oracle gate for 8546's SPECIAL-WEAPON apply families (44AF no-op + 84C3 module deploy).

The [A958] gun-level stubs are covered by ``verify_native_apply_upgrade_8546``; this covers the two
NON-gun handlers reachable in the different-weapons demo: marker 2 -> ``84C3`` (``call 9F1A; jmp
8430`` -- deploy a weapon module into [A962]/[A964] via the 7524 allocator) and marker 1 -> ``44AF``
(a bare ``ret`` -- the apply is a no-op, the marker persists, no sound).

Like the gun gate it SYNTHESISES the coverage the corpus lacks: it replays the demo, writes the held
marker + the TAB scancode into the pure VM's own INT9 key table at a 9B2E boundary, lets the game's
0162 decode it, traps 8546 entry + its 859D ret, runs the native ``_apply_upgrade_8546`` over the
entry image, and diffs DGROUP.  Injecting input creates an oracle for a path the demo never drives;
every cell the handler writes is still compared byte for byte.

Usage:
    pypy -m overkill.probes.verify_native_special_weapon_apply [demo]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402

CS = 0x1010
DS = 0x25CC
FRAME_TOP = 0x9B2E
HANDLER_ENTRY = 0x8546
HANDLER_RET = 0x859D
TAB_SCANCODE = 0x0F
DEFAULT_DEMO = "demo_play_tandy_L6_different_weapons_20260618_225615"
INJECT_AT_FRAME = 6
STACK_SLACK = 0x100
#: (held marker, forced weapon level [desc+8]) -> the handler it dispatches to.  Forcing the level in
#: the pure VM's own descriptor is the same kind of synthetic-coverage injection as the held marker:
#: the game's 8546 dispatch (bx = [desc+8]*6; call [bx+si+4]) then executes the real handler.
CASES = [
    (2, 1, "8463 (deploy 9D91 -> [A96E])"),
    (2, 3, "84C3 (deploy 9F1A -> [A962]/[A964])"),
    (2, 6, "84D6 (flag weapon, [2384]=1)"),
    (2, 7, "84FD (flag weapon, [2384]=2)"),
    (1, 0, "44AF (no-op ret)"),
]


class _Done(Exception):
    pass


def _capture(demo, marker, level, base):
    st = {"frame": 0, "pre": None, "sp": 0, "calls": []}

    def on_step(cpu):
        s = cpu.s
        cs, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if cs != CS:
            return
        if ip == FRAME_TOP:
            st["frame"] += 1
            if st["frame"] >= INJECT_AT_FRAME:
                cpu.mem.wb(DS, (0x98C4 + TAB_SCANCODE) & 0xFFFF, 1)
                cpu.mem.ww(DS, 0x95FA, marker)
                desc = cpu.mem.rw(DS, (0x95FC + marker * 2) & 0xFFFF)
                cpu.mem.ww(DS, (desc + 8) & 0xFFFF, level)   # force the weapon level -> target handler
            if st["frame"] > INJECT_AT_FRAME + 30:
                raise _Done
        elif ip == HANDLER_ENTRY:
            st["pre"] = bytes(cpu.mem.data)
            st["sp"] = s.sp & 0xFFFF
        elif ip == HANDLER_RET and st["pre"] is not None:
            st["calls"].append((st["pre"], bytes(cpu.mem.data[base:base + 0x10000]), st["sp"]))
            st["pre"] = None
            if len(st["calls"]) >= 2:
                raise _Done

    try:
        run_ref_step_probe(demo, 300, on_step,
                           trap=frozenset({(CS, FRAME_TOP), (CS, HANDLER_ENTRY), (CS, HANDLER_RET)}))
    except _Done:
        pass
    return st["calls"]


def main(argv) -> int:
    from overkill.native_frame import _apply_upgrade_8546
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    demo_name = argv[0] if argv else DEFAULT_DEMO
    base = DS * 16
    total, bad, verified = 0, 0, 0

    for marker, level, label in CASES:
        calls = _capture(load_demo(demo_name, DEFAULT_DEMO), marker, level, base)
        if not calls:
            print(f"  {label}: 8546 never ran -- skipped (marker {marker} not held in this demo?)")
            continue
        for i, (pre_full, post, sp) in enumerate(calls, 1):
            total += 1
            native = MutFlatMemory(bytearray(pre_full))
            try:
                _apply_upgrade_8546(native)
            except Exception as exc:  # noqa: BLE001
                print(f"  {label} apply #{i}: native REFUSED: {exc}")
                bad += 1
                continue
            nat = bytes(native.data[base:base + 0x10000])
            lo = (sp - STACK_SLACK) & 0xFFFF
            diff = [o for o in range(0x10000) if nat[o] != post[o] and not (lo <= o < sp)]
            verified += 1
            status = "OK" if not diff else f"DIFF ({len(diff)})"
            print(f"  {label} apply #{i}: {status}")
            for o in diff[:8]:
                print(f"       DS:{o:04X} vm={post[o]:02X} nat={nat[o]:02X}")
            bad += bool(diff)

    print(f"\nspecial-weapon applies verified: {verified}/{total}  diverging: {bad}")
    ok = bad == 0 and verified >= 8
    print("RESULT:", "PASS -- the native apply reproduces the 8463/84C3/84D6/84FD/44AF weapon "
          "families byte-exact" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
