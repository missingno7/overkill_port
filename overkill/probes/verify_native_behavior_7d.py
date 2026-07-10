"""Driven gate: native `_step_controller_7d` vs the ORIGINAL 1F8F:027A, per 0x7D/0x7E step, over L4.

Behaviour 0x7D/0x7E is the shared 8D4F waypoint body's DEFAULT (02CB) arrival.  It is NOT in the L1
lockstep (planet-4 only), so it was recovered from the lifter-verified transcription (liftverify
1F8F:027A ORACLE_PASSING via a capture_pure_vm_snapshot snapshot).  This gate proves the native handler
byte-exact against the interpreted original: it replays the L4 demo through the pure ref VM, and at
every 8D4F entry whose record carries behaviour 0x7D/0x7E it captures the pre-state, then at the
far-call return 8D54 (i.e. after 1F8F:027A ran) it diffs the VM's DGROUP against running native
`_step_controller_7d` over the same pre-state.  8D4F..8D54 is exactly 1F8F:027A (the postmove BC4B is
separately gated), so this isolates the recovered handler.

Usage:
    python -m overkill.probes.verify_native_behavior_7d [demo] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.probes.verify_native_lockstep import EXCLUDED_CELLS  # noqa: E402
from overkill.recovered.adapters.behavior_walk import _step_controller_7d  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402

CS = 0x1010
DS = 0x25CC
STEP_ENTRY = 0x8D4F
FAR_RET = 0x8D54
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
            if cpu.mem.rw(DS, (bp + 0x18) & 0xFFFF) in (0x7D, 0x7E):
                st["pre"] = bytes(cpu.mem.data)
                st["bp"] = bp
                st["sp"] = s.sp & 0xFFFF
            else:
                st["pre"] = None
        elif ip == FAR_RET and st["pre"] is not None:
            vm_post = bytes(cpu.mem.data[base:base + 0x10000])
            native = MutFlatMemory(bytearray(st["pre"]))
            _step_controller_7d(native, st["bp"])
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

    print(f"behaviour 0x7D/0x7E steps verified: {st['n']}  diverging: {st['bad']}")
    for line in st["first"]:
        print(f"  DIVERGENCE {line}")
    ok = st["n"] > 0 and st["bad"] == 0
    print("RESULT:", "PASS -- native _step_controller_7d reproduces 1F8F:027A byte-exact for every "
          f"0x7D/0x7E step ({st['n']} steps, incl. arrivals)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
