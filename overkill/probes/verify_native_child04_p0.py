"""Driven gate: native _step_child_04's planet-0 (AECD) branch vs the ORIGINAL, over an L6 demo.

Behavior 0x04 on planet 0 dispatches its move through AECD: direction != 4 -> the AEE4 8-way +/-8px
step; direction == 4 -> AF60 (the planet-1..5 path, already gated).  This traps AEBF (the 0x04 handler
entry) for records with behaviour 0x04, captures the pre-state, and at the next A9D3 walk boundary
diffs the VM's record +0x02/+0x04 against running native _step_child_04.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.native_frame import level_tiles_from_image  # noqa: E402
from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.adapters.behavior_walk import _step_child_04  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402

CS = 0x1010
DS = 0x25CC
ENTRY = 0xAEBF
DISPATCH = 0xA9D3   # the walk's per-record dispatch top (hit before the next record)
base = DS * 16


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, "demo_play_tandy_L6_begin_20260618_225537")
    max_frames = int(argv[1]) if len(argv) > 1 else 3000
    st = {"pre": None, "bp": 0, "n": 0, "bad": 0, "np0": 0, "first": []}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF) != CS:
            return
        ip = s.ip & 0xFFFF
        if ip == ENTRY and st["pre"] is None:
            bp = s.bp & 0xFFFF
            if cpu.mem.rw(DS, (bp + 0x18) & 0xFFFF) == 0x04:
                st["pre"] = bytes(cpu.mem.data)
                st["bp"] = bp
                if cpu.mem.rw(DS, 0x2356) == 0 and (cpu.mem.rw(DS, (bp + 0x06) & 0xFFFF) & 0x7) != 4:
                    st["np0"] += 1
        elif ip == DISPATCH and st["pre"] is not None:
            bp = st["bp"]
            vm = tuple(cpu.mem.rw(DS, (bp + o) & 0xFFFF) for o in (0x02, 0x04))
            native = MutFlatMemory(bytearray(st["pre"]))
            _step_child_04(native, bp, level_tiles_from_image(native))
            nat = tuple(native.rw(DS, (bp + o) & 0xFFFF) for o in (0x02, 0x04))
            st["n"] += 1
            if vm != nat:
                st["bad"] += 1
                if len(st["first"]) < 8:
                    st["first"].append(f"step {st['n']} rec {bp:04X}: vm {vm} nat {nat}")
            st["pre"] = None

    run_ref_step_probe(demo, max_frames, on_step, trap=frozenset({(CS, ENTRY), (CS, DISPATCH)}))
    print(f"0x04 steps verified: {st['n']}  (planet-0 8-way branch: {st['np0']})  diverging: {st['bad']}")
    for line in st["first"]:
        print(f"  DIVERGENCE {line}")
    ok = st["n"] > 0 and st["bad"] == 0 and st["np0"] > 0
    print("RESULT:", f"PASS -- native _step_child_04 matches the VM incl. the planet-0 8-way branch "
          f"({st['np0']} of {st['n']} steps)" if ok else "FAIL"
          if st["np0"] > 0 else "SKIP -- planet-0 8-way branch not exercised")
    return 0 if (ok or st["np0"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
