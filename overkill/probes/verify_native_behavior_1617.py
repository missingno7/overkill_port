"""Driven gate: native _step_shooter_88 vs the ORIGINAL F52A/F554/F53F/F55A, over an L6 demo.

Behaviors 0x16/0x17 are planet-0 (mothership) cue spawns -- three thin wrappers over the shared
F55A body (vertical seek toward DS:[D2C2] + a gated C237 spawn), each ending `jmp BC45`.  Not in the L1
lockstep.  Replays a planet-0 demo through the pure ref VM; at each handler entry whose record carries
0x16/0x17, diffs the VM DGROUP at the following BC45 (body done, postmove not yet) against running
native _step_shooter_88 over the same pre-state.

Usage:
    python -m overkill.probes.verify_native_behavior_1617 [demo] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.probes.verify_native_lockstep import EXCLUDED_CELLS  # noqa: E402
from overkill.recovered.adapters.behavior_walk import _step_diver_16_17  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402

CS = 0x1010
DS = 0x25CC
ENTRIES = {0xB930: 0x16}
BC45 = 0xBC4B
PARAMS = {0x16: None, 0x17: None}
DEFAULT_DEMO = "demo_play_tandy_L6_begin_20260618_225537"
base = DS * 16


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else 3000
    st = {"pre": None, "bp": 0, "beh": 0, "sp": 0, "n": 0, "bad": 0, "first": []}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF) != CS:
            return
        ip = s.ip & 0xFFFF
        if ip in ENTRIES:
            bp = s.bp & 0xFFFF
            beh = cpu.mem.rw(DS, (bp + 0x18) & 0xFFFF)
            if beh in PARAMS:
                st["pre"] = bytes(cpu.mem.data)
                st["bp"] = bp
                st["beh"] = beh
                st["sp"] = s.sp & 0xFFFF
            else:
                st["pre"] = None
        elif ip == BC45 and st["pre"] is not None:
            vm_post = bytes(cpu.mem.data[base:base + 0x10000])
            native = MutFlatMemory(bytearray(st["pre"]))
            _step_diver_16_17(native, st["bp"])
            nat = bytes(native.data[base:base + 0x10000])
            lo = (st["sp"] - 0x100) & 0xFFFF
            diff = [o for o in range(0x10000)
                    if nat[o] != vm_post[o] and not (lo <= o < st["sp"]) and o not in EXCLUDED_CELLS]
            st["n"] += 1
            if diff:
                st["bad"] += 1
                if len(st["first"]) < 10:
                    st["first"].append(
                        f"step {st['n']} beh {st['beh']:#04x} rec {st['bp']:04X}: " +
                        " ".join(f"{o:04X} vm={vm_post[o]:02X} nat={nat[o]:02X}" for o in diff[:6]))
            st["pre"] = None

    run_ref_step_probe(demo, max_frames, on_step, trap=frozenset(
        {(CS, ip) for ip in ENTRIES} | {(CS, BC45)}))

    print(f"behaviour 0x16/0x17 steps verified: {st['n']}  diverging: {st['bad']}")
    for line in st["first"]:
        print(f"  DIVERGENCE {line}")
    ok = st["n"] > 0 and st["bad"] == 0
    print("RESULT:", "PASS -- native _step_diver_16_17 reproduces B930 byte-exact for every "
          f"0x16/0x17 step ({st['n']} steps)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
