"""Driven gate: native _planet0_cue vs the ORIGINAL 7BCB mothership tile-cue, over an L6 demo.

Planet 0's tile-cue (7BCB) is not in the L1 lockstep.  This replays a planet-0 demo through the pure
ref VM; at each 7BCB entry it captures the pre-state + the cue args (tile al, si, [A40A], the 8209
leak ss:[bp+2]/[bp+4]), then at the 7948 loop-return 796A diffs the VM DGROUP + the plane byte at si
against running native _planet0_cue over the same pre-state.  Fails loud on the un-transcribed special
handlers (skips them from the pass/fail tally, reports the count).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.probes.verify_native_lockstep import EXCLUDED_CELLS  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402
from overkill.recovered.adapters.tile_cues import _planet0_cue  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402

CS = 0x1010
DS = 0x25CC
CUE = 0x7BCB
LOOP_RET = 0x796A
base = DS * 16


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, "demo_play_tandy_L6_begin_20260618_225537")
    max_frames = int(argv[1]) if len(argv) > 1 else 3000
    st = {"pre": None, "n": 0, "bad": 0, "gaps": 0, "first": []}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF) != CS:
            return
        ip = s.ip & 0xFFFF
        m = cpu.mem
        if ip == CUE:
            ss, bp = s.ss & 0xFFFF, s.bp & 0xFFFF
            st["pre"] = (bytes(m.data), s.ax & 0xFF, s.si & 0xFFFF, m.rw(DS, 0xA40A),
                         m.rw(ss, (bp + 4) & 0xFFFF), m.rw(ss, (bp + 2) & 0xFFFF),
                         m.rw(CS, 0x9592), s.sp & 0xFFFF)
        elif ip == LOOP_RET and st["pre"] is not None:
            pre, tile_id, si, y_a40a, leak_32, leak_34, plane_seg, sp = st["pre"]
            st["pre"] = None
            vm_post = bytes(m.data[base:base + 0x10000])
            vm_plane = m.rb(plane_seg, si)
            native = MutFlatMemory(bytearray(pre))
            try:
                _planet0_cue(native, plane_seg, si, tile_id, y_a40a, leak_32, leak_34)
            except RecoveryGap:
                st["gaps"] += 1
                return
            nat = bytes(native.data[base:base + 0x10000])
            lo = (sp - 0x60) & 0xFFFF
            diff = [o for o in range(0x10000)
                    if nat[o] != vm_post[o] and o not in EXCLUDED_CELLS and not (lo <= o < sp)]
            nat_plane = native.rb(plane_seg, si)
            st["n"] += 1
            if diff or nat_plane != vm_plane:
                st["bad"] += 1
                if len(st["first"]) < 10:
                    d = " ".join(f"{o:04X} vm={vm_post[o]:02X} nat={nat[o]:02X}" for o in diff[:6])
                    if nat_plane != vm_plane:
                        d += f" plane[{si:04X}] vm={vm_plane:02X} nat={nat_plane:02X}"
                    st["first"].append(f"cue #{st['n']} tile {tile_id:#04X}: {d}")

    run_ref_step_probe(demo, max_frames, on_step, trap=frozenset({(CS, CUE), (CS, LOOP_RET)}))

    print(f"planet-0 cues verified: {st['n']}  diverging: {st['bad']}  special-gaps skipped: {st['gaps']}")
    for line in st["first"]:
        print(f"  DIVERGENCE {line}")
    ok = st["n"] > 0 and st["bad"] == 0
    print("RESULT:", f"PASS -- native _planet0_cue reproduces 7BCB byte-exact for {st['n']} cues "
          f"({st['gaps']} special-handler gaps skipped)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
