"""Driven gate: native `_step_stepper_93` vs the ORIGINAL 1F8F:0473, per 0x93 step, over the L4 demo.

Behaviour 0x93 is the child behaviour 0x7D spawns (8D5F -> 1F8F:0473, jmp BC4B).  Not in the L1
lockstep; recovered from the lifter-verified transcription (liftverify 1F8F:0473 ORACLE_PASSING via a
capture_pure_vm_snapshot snapshot).  This proves the native handler byte-exact: it replays the L4 demo
through the pure ref VM, and at every 8D5F entry whose record carries behaviour 0x93 it diffs the VM's
DGROUP after the far-call return 8D64 (i.e. after 1F8F:0473 ran) against running native
`_step_stepper_93` over the same pre-state (the A954/230A seek scratch is excluded per the walk shadow).

Usage:
    python -m overkill.probes.verify_native_behavior_93 [demo] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.probes.verify_native_lockstep import EXCLUDED_CELLS  # noqa: E402
from overkill.native_frame import level_tiles_from_image  # noqa: E402
from overkill.recovered.adapters.behavior_walk import _step_stepper_93  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402

CS = 0x1010
DS = 0x25CC
STEP_ENTRY = 0x8D5F
FAR_RET = 0x8D64
DEFAULT_DEMO = "demo_play_tandy_L4_full_20260618_185155"
base = DS * 16


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else 4000
    st = {"pre": None, "bp": 0, "sp": 0, "n": 0, "bad": 0, "first": []}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF) != CS:
            return
        ip = s.ip & 0xFFFF
        if ip == STEP_ENTRY:
            bp = s.bp & 0xFFFF
            if cpu.mem.rw(DS, (bp + 0x18) & 0xFFFF) == 0x93:
                st["pre"] = bytes(cpu.mem.data)
                st["bp"] = bp
                st["sp"] = s.sp & 0xFFFF
            else:
                st["pre"] = None
        elif ip == FAR_RET and st["pre"] is not None:
            vm_post = bytes(cpu.mem.data[base:base + 0x10000])
            native = MutFlatMemory(bytearray(st["pre"]))
            _step_stepper_93(native, st["bp"], level_tiles_from_image(native))
            nat = bytes(native.data[base:base + 0x10000])
            lo = (st["sp"] - 0x100) & 0xFFFF
            diff = [o for o in range(0x10000)
                    if nat[o] != vm_post[o] and not (lo <= o < st["sp"]) and o not in EXCLUDED_CELLS]
            st["n"] += 1
            if diff:
                st["bad"] += 1
                if len(st["first"]) < 10:
                    st["first"].append(
                        f"step {st['n']} rec {st['bp']:04X}: " +
                        " ".join(f"{o:04X} vm={vm_post[o]:02X} nat={nat[o]:02X}" for o in diff[:6]))
            st["pre"] = None

    run_ref_step_probe(demo, max_frames, on_step,
                       trap=frozenset({(CS, STEP_ENTRY), (CS, FAR_RET)}))

    print(f"behaviour 0x93 steps verified: {st['n']}  diverging: {st['bad']}")
    for line in st["first"]:
        print(f"  DIVERGENCE {line}")
    ok = st["n"] > 0 and st["bad"] == 0
    print("RESULT:", "PASS -- native _step_stepper_93 reproduces 1F8F:0473 byte-exact for every "
          f"0x93 step ({st['n']} steps)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
