"""Driven-oracle gate: ``DS:215E`` / ``DS:2160`` are DEAD SCRATCH across a 9B2E frame boundary.

The lockstep gate diffs the whole DGROUP, so a cell whose *residual* value differs between the VM
and the native frame is reported even when nothing ever reads that residue.  ``215A`` is already
excluded on exactly that ground (5073 writes it, 4FF9 reads it, both inside one present half).
This probe proves the same for its neighbours, which are the last 'state' residue in the gate.

WHAT THEY ARE.  Three mode-variant copies of one coordinate decoder (``2718`` x1, ``3322`` x4,
``4445`` x2) read a 2-byte pair off a ``bp`` data pointer::

    mov al,[bp+1] ; mul 320 ; mov [2160],ax      ; y * 320
    mov al,[bp+2] ; (scale) ; mov [215E],al      ; x
    add bp,2 ; ret

and the drawer (``3170``: ``mov dl,[215E]`` / ``add dx,[2160]``) turns them back into an offset.
The caller at ``1010:5194`` runs this EVERY frame -- twice per drawn item, with ``bp`` pointing at
the ``231A`` and ``235E`` coordinate blocks -- so the value standing at the frame boundary is just
whichever item was drawn last.  That count varies (an item may be culled), which is why the residue
flips on a handful of frames and why it is not state.

WHAT THIS PROBE ASSERTS.  For every 9B2E frame of a demo, the FIRST access to each cell is an
absolute write.  Any read -- or any ``add [2160],imm16`` read-modify-write -- reaching a cell before
that frame's first absolute write would mean the residue carries information, and the probe FAILS.
Excluding these cells from the lockstep diff is sound only while this passes.

Usage:
    python -m overkill.probes.verify_draw_scratch_dead [demo] [max_frames]
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

#: ``mov [cell],reg`` / ``mov byte [cell],imm`` -- the value written does not depend on the old one
ABS_WRITES = {
    0x2160: {0x2722, 0x332C, 0x444F, 0x51EB},
    0x215E: {0x2728, 0x3336, 0x4457, 0x270C, 0x3316, 0x4439},
}
#: reads, and ``add [cell],imm16`` read-modify-writes -- these CONSUME the standing value
CONSUMERS = {
    0x2160: {0x2711, 0x331B, 0x443E, 0x262A, 0x317A, 0x42A4, 0x51C5, 0x51D0},
    0x215E: {0x2627, 0x3176, 0x42A0},
}


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else 0

    abs_ip = {ip: cell for cell, ips in ABS_WRITES.items() for ip in ips}
    con_ip = {ip: cell for cell, ips in CONSUMERS.items() for ip in ips}

    st = {"frame": 0, "writes": 0, "reads": 0}
    written: set[int] = set()          # cells absolutely written so far THIS frame
    bad: list[str] = []

    class Done(Exception):
        pass

    def on_step(cpu) -> None:
        ip = cpu.s.ip & 0xFFFF
        if ip == FRAME_TOP:
            st["frame"] += 1
            written.clear()
            if max_frames and st["frame"] > max_frames:
                raise Done
            return
        cell = abs_ip.get(ip)
        if cell is not None:
            written.add(cell)
            st["writes"] += 1
            return
        cell = con_ip.get(ip)
        if cell is not None:
            st["reads"] += 1
            if cell not in written and len(bad) < 8:
                bad.append(f"  frame {st['frame']}: 1010:{ip:04X} consumes {cell:04X} "
                           f"before any absolute write this frame")

    trap = frozenset([(CS, FRAME_TOP)] + [(CS, ip) for ip in abs_ip] + [(CS, ip) for ip in con_ip])
    try:
        run_ref_step_probe_cold_start(demo, None, on_step, trap=trap)
    except Done:
        pass

    print(f"9B2E frames: {st['frame']}  absolute writes: {st['writes']}  consumers: {st['reads']}")
    for line in bad:
        print(line)
    ok = st["frame"] > 0 and st["writes"] > 0 and st["reads"] > 0 and not bad
    print("RESULT:", "PASS -- every consumer of 215E/2160 runs after that frame's own absolute "
          "write; the residue at the 9B2E boundary is dead" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
