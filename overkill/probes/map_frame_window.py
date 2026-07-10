"""COVERAGE MAP of one 9B2E frame window: every call edge the VM takes, nested by depth.

The general instrument for "what does the original actually DO in this frame?".  It exists because
reasoning from the disassembly listing has been wrong nearly every time in this port, while driving
the original has been right the first time -- a listing shows what CAN run, this shows what DID.

At the Nth 9B2E boundary it swaps the cheap trap observer for a full per-instruction logger, records
every CALL (near, far, and indirect resolved by watching the next instruction), and stops at the
N+1th boundary.  A call is attributed at its TARGET, so an indirect call through a jump table names
the routine that really ran.

It found the death continuation: the native frame returns at the 97CE exit, but frame 5018 of the
cold-start demo runs 418626 more instructions --

    9B16 -> 4DBF  -> 4DAF, 0B3E (level-data init; C679, the far 254A:04D7 asset decode, 0248),
                     4E26, 4E0D -> A781 (row pull) -> A7EB -> A81B
    9908 -> C4DB  -> 8517 -> 5A00, 85B5 -> 85D5 -> 613E/5A6C     (the respawn seed)
    978F -> A940 (+ object walk + 1F8F:0922), 9798 -> C57C, 979B -> B5A9, 97A4 -> 5F43
    then the ordinary present half, up to the next 9B2E.

-- disproving the note that had stood in native_frame.py calling 4DBF "the death jingle".

Usage:
    pypy -m overkill.probes.map_frame_window [frame_number]     (default: 5018, a death frame)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start

CS, DS = 0x1010, 0x25CC
FRAME = 0x9B2E
DEFAULT_DEMO = "demo_cold_start_full_20260705_123645"
#: the recorded cold-start demo's max_frames -- must match the lockstep cache's budget
VERIFIER_FRAMES = 20000
#: 5018 is a death frame: the window the native frame returns before
DEFAULT_TARGET = 5018


class _Done(Exception):
    """Raised at the closing 9B2E boundary to unwind out of the verifier."""


def map_window(target: int, demo_name: str | None = None) -> "tuple[int, list]":
    """Drive the demo and return ``(instructions, [(depth, from, to), ...])`` for window ``target``."""
    demo = load_demo(demo_name, DEFAULT_DEMO)
    st = {"f": 0, "n": 0, "pending": None, "depth": 0}
    calls: list = []
    seen: set = set()

    def full_step(cpu) -> None:
        s = cpu.s
        cs, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if cs == CS and ip == FRAME:
            raise _Done
        st["n"] += 1
        op = cpu.mem.rb(cs, ip)
        is_call = op in (0xE8, 0x9A) or (
            op == 0xFF and ((cpu.mem.rb(cs, (ip + 1) & 0xFFFF) >> 3) & 7) in (2, 3))
        if is_call:
            st["pending"] = (cs, ip, st["depth"])
            st["depth"] += 1
            return
        if op in (0xC3, 0xCB, 0xC2, 0xCA):
            st["depth"] = max(0, st["depth"] - 1)
            return
        p = st["pending"]
        if p is not None:
            st["pending"] = None
            fcs, fip, d = p
            key = (fcs, fip, cs, ip)
            if key not in seen:
                seen.add(key)
                calls.append((d, f"{fcs:04X}:{fip:04X}", f"{cs:04X}:{ip:04X}"))

    def on_step(cpu) -> None:
        s = cpu.s
        if (s.ip & 0xFFFF) == FRAME and (s.cs & 0xFFFF) == CS:
            st["f"] += 1
            if st["f"] == target:
                orig = cpu.__class__.step

                def step(_c=cpu):
                    full_step(_c)
                    return orig(_c)

                cpu.step = step

    try:
        run_ref_step_probe_cold_start(demo, VERIFIER_FRAMES, on_step,
                                      trap=frozenset({(CS, FRAME)}))
    except _Done:
        pass
    return st["n"], calls


def main(argv) -> int:
    target = int(argv[0]) if argv else DEFAULT_TARGET
    demo_name = argv[1] if len(argv) > 1 else None
    n, calls = map_window(target, demo_name)
    print(f"frame {target}: {n} instructions in the window, {len(calls)} distinct call edges")
    print("(the native frame returns at the 97CE exit when A344/A342/A346 == 1)\n")
    for d, frm, to in calls:
        print(f"  {'  ' * min(d, 8)}{frm} -> {to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
