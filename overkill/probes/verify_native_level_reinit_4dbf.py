"""Driven-oracle gate for ``1010:4DBF`` -- the LEVEL RE-INIT the death tail calls at ``9B16``.

The lockstep gate's whole residue is 7 death/respawn windows, and 4DBF is the first unmodelled thing
in them.  Rather than wait for a whole window to go byte-exact (which also needs 9908, the 978F
prologue, and six more routines), this gate isolates 4DBF: trap its entry and its ``4E0C`` return on
the pure-VM side, snapshot DGROUP at both, run the native ``_level_reinit_4dbf`` over the entry
image, and diff.

WHAT IS COMPARED.  The whole 64K DGROUP, minus two things that are provably not state and that an
earlier probe of this very routine mistook for recovered structure:

  * ``EXCLUDED_CELLS`` (the lockstep gate's own list).  Without it, 0B3E's ``rep stosb`` clear of the
    INT9 key table at 98C4..9943 (from 1010:50AB) shows up as four mysterious "flags" at
    990C/990F/9911/9914.
  * the STACK below ``sp`` at the 4DBF call.  Without it, the pushes at ``254A:04D7`` inside the DOS
    open call show up as a 22-byte far-pointer struct at A256..A26B.  ``sp`` there is A26C.

WHAT IS SUPPLIED.  0B3E loads the level FILE (``C679``: DOS 3Dh open on the ``[14C0+planet*2]``
filename, read, close; ``[21A8]`` = the byte count).  That is a host boundary, like the key table and
the INT8 tick count, so the native side is handed the same bytes rather than emulating INT 21h.

Usage:
    pypy -m overkill.probes.verify_native_level_reinit_4dbf [demo]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402
from overkill.probes.verify_native_lockstep import DGROUP, EXCLUDED_CELLS  # noqa: E402

CS = 0x1010
FRAME_TOP = 0x9B2E
REINIT_ENTRY = 0x4DBF
REINIT_RET = 0x4E0C          # the `ret` of 4DBF
VERIFIER_FRAMES = 20000
DEFAULT_DEMO = "demo_cold_start_full_20260705_123645"
#: The stack window to ignore, measured, not guessed: sp at the 4DBF call sits just above A26C, and
#: the deepest push inside (the DOS open wrapper at 254A:04D7) reaches A256 -- 0x16 below.  0x100 is
#: comfortable slack that still leaves the nearest real cell, DS:A278 (which A781 decrements), ABOVE
#: sp and therefore compared.  This is a window, NOT "everything below sp": DGROUP's real data lives
#: at low offsets and must not be masked out.
STACK_SLACK = 0x100


def _diff(post: bytes, native: bytes, sp: int) -> "list[int]":
    lo = (sp - STACK_SLACK) & 0xFFFF
    return [o for o in range(0x10000)
            if native[o] != post[o] and o not in EXCLUDED_CELLS and not (lo <= o < sp)]


def main(argv) -> int:
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    try:
        from overkill.native_frame import _level_reinit_4dbf
    except ImportError:
        print("RESULT: SKIP -- native_frame._level_reinit_4dbf is not implemented yet.")
        print("  (This gate is deliberately written BEFORE the code; see "
              "docs/overkill/campaigns/demo_lockstep.md.)")
        return 0

    # The LEVEL FILE is the host input C679 fetches with INT 21h.  Supply it from the container,
    # which is where the native port reads its assets -- do not emulate DOS.
    from overkill.probes.verify_native_lockstep import level_assets_for

    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    base = DGROUP * 16
    st: dict = {"frame": 0, "pend": None}
    res = {"calls": 0, "bad": 0}
    lines: list[str] = []

    def on_ref_step(cpu) -> None:
        s = cpu.s
        cs, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if ip == FRAME_TOP and cs == CS:
            st["frame"] += 1
            return
        if cs != CS:
            return
        if ip == REINIT_ENTRY:
            st["pend"] = (st["frame"], bytes(cpu.mem.data), s.sp & 0xFFFF)
        elif ip == REINIT_RET and st["pend"] is not None:
            frame, pre_full, sp = st["pend"]
            st["pend"] = None
            res["calls"] += 1
            post = bytes(cpu.mem.data[base:base + 0x10000])
            native = MutFlatMemory(bytearray(pre_full))
            _level_reinit_4dbf(native, level_assets_for)
            nat = bytes(native.data[base:base + 0x10000])
            diffs = _diff(post, nat, sp)
            if diffs:
                res["bad"] += 1
                if len(lines) < 6:
                    cells = ",".join(
                        f"DS:{o:04X}(vm={post[o]:02X}/nat={nat[o]:02X})" for o in diffs[:6])
                    lines.append(f"  frame {frame}: {len(diffs)}B (sp={sp:04X}) {cells}")

    trap = frozenset({(CS, FRAME_TOP), (CS, REINIT_ENTRY), (CS, REINIT_RET)})
    run_ref_step_probe_cold_start(demo, VERIFIER_FRAMES, on_ref_step, trap=trap)

    print(f"4DBF calls driven: {res['calls']}  diverging: {res['bad']}")
    for line in lines:
        print(line)
    ok = res["calls"] > 0 and res["bad"] == 0
    print("RESULT:", "PASS -- the native level re-init reproduces 4DBF's DGROUP effect on every "
          "death of the demo" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
