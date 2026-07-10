"""Driven-oracle gate: ``DS:98BE`` -- 0162's decoded input word -- is DEAD at the 9B2E boundary.

The lockstep gate diffs the whole DGROUP, so a cell whose RESIDUAL value differs is reported even
when nothing ever reads that residue.  ``215A`` and ``215E``/``2160`` are already excluded on exactly
that ground; this proves the same for the input word, which is the last cell separating the L1 demo
from zero divergence.

WHY IT COMES UP.  ``D305`` (the post-respawn wait, run at the top-of-level checkpoint) polls ``0162``
0xC9 times inside ONE 9B2E window, and the demo pump rewrites the INT9 key table between INT8 frames.
So the final poll reads a key table that exists only inside the VM and never in the pre-state image
the native frame is handed.  The input channel is being sampled 201 times in one window; no routine
is missing.

WHY THE RESIDUE IS DEAD.  ``0162`` rebuilds the byte from nothing: eight ``rcl byte [98BE],1`` shift
all eight old bits out through CF (each one immediately overwritten by the next ``shr al,1``), then
``or byte [98BE],imm`` adds the flag bits.  The prior value cannot survive a poll, and every 9B2E
frame polls before it reads.  This probe asserts precisely that, driving the ORIGINAL.

A NOTE ON HOW THIS WAS NEARLY GOT WRONG.  A first version of this proof derived the writer addresses
from a static opcode scan and reported ``writes 0`` over 8291 frames -- impossible, since the poll
plainly writes the cell.  The stores are ``rcl`` (opcode D0), which the scan never classified as a
write.  A zero write-count is a broken instrument, not a discovery: the writer addresses below were
found by DRIVING the original and watching the byte change.

Usage:
    pypy -m overkill.probes.verify_input_word_dead [demo]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402

CS = 0x1010
FRAME_TOP = 0x9B2E
DEFAULT_DEMO = "demo_cold_start_full_20260705_123645"
VERIFIER_FRAMES = 20000

#: every instruction that STORES to 98BE: 0162's eight `rcl byte [98BE],1` and its `or ...,imm`
#: flag merges, plus the menu/front-end stores.  Found by driving, not by scanning.
WRITE_IPS = frozenset({
    0x0181, 0x0184, 0x0191, 0x019C, 0x01A7, 0x01B2, 0x01BD, 0x01C8, 0x01D3,
    0x01E9, 0x01F4, 0x0204, 0x020F, 0x022B, 0x0234,
    0x99FB, 0x9A16, 0x9AD8, 0x9ADF, 0x9AEC, 0x9AF9,
    0xD08E, 0xD0B9,
})
#: every instruction that CONSUMES it
READ_IPS = frozenset({
    0x4E88, 0x4E92, 0x50D5, 0x50E7, 0x5616, 0x56A8, 0x598A, 0x59D2, 0x985A, 0x999D,
    0x9A7E, 0x9AF4, 0x9B6F, 0x9B79, 0x9B83, 0x9B8D, 0x9B9F, 0x9C07, 0x9C1E, 0x9CF1,
    0xA067, 0xA1EF, 0xA200, 0xA629, 0xA64E, 0xCE4D, 0xCF80, 0xD032, 0xD308, 0xD355,
    0xD35F, 0xD393, 0xD418, 0xD43E, 0xD452, 0xD459, 0xD460, 0xD467, 0xD46E,
})


class _Done(Exception):
    pass


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    st = {"frame": 0, "written": False, "w": 0, "r": 0}
    bad: list[str] = []

    def on_step(cpu) -> None:
        s = cpu.s
        cs, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if cs != CS:
            return
        if ip == FRAME_TOP:
            st["frame"] += 1
            st["written"] = False
            if st["frame"] > 8290:
                raise _Done
            return
        if ip in WRITE_IPS:
            st["written"] = True
            st["w"] += 1
        elif ip in READ_IPS:
            st["r"] += 1
            # frame 0 is the pre-gameplay boot/menu, before any 9B2E boundary exists
            if st["frame"] >= 1 and not st["written"] and len(bad) < 8:
                bad.append(f"  frame {st['frame']}: 1010:{ip:04X} reads 98BE before any poll")

    trap = frozenset([(CS, FRAME_TOP)] + [(CS, a) for a in WRITE_IPS | READ_IPS])
    try:
        run_ref_step_probe_cold_start(demo, VERIFIER_FRAMES, on_step, trap=trap)
    except _Done:
        pass

    print(f"9B2E frames: {st['frame']}  stores: {st['w']}  consumers: {st['r']}")
    for line in bad:
        print(line)
    # A zero store count means the trap addresses are wrong, not that the cell is never written.
    ok = st["frame"] > 0 and st["w"] > 0 and st["r"] > 0 and not bad
    print("RESULT:", "PASS -- every consumer of 98BE runs after that frame's own 0162 poll; the "
          "residue at the 9B2E boundary is dead" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
