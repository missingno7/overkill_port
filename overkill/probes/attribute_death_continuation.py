"""Attribute the death continuation's DGROUP effect to each routine along it.

Snapshot DGROUP at consecutive checkpoints on 9908 -> 9773 -> 978F -> 97B2 and diff neighbours, over
every death window.  A step that changes ZERO bytes in all of them is a no-op for the lockstep gate
and does not need recovering at all -- which is how C57C and B5A9 were struck off the work list
without decoding a single instruction of either.

Run it before implementing any part of a continuation: it tells you which routines carry state and
roughly how much, so effort goes where the bytes are.  Diffs exclude EXCLUDED_CELLS and a 0x100
stack window below sp, exactly as verify_native_level_reinit_4dbf does; without both, dead stack and
the excluded key table masquerade as recovered state.

Usage:
    pypy -m overkill.probes.attribute_death_continuation
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start
from overkill.probes.verify_native_lockstep import EXCLUDED_CELLS

CS, DS = 0x1010, 0x25CC
FRAME = 0x9B2E
DEATH = {4636, 4821, 5018, 5379, 6495, 7143, 7595}

# (ip, label) in execution order along the continuation
POINTS = [
    (0x9908, "enter 9908"),
    (0x990B, "after C4DB"),
    (0x977D, "at 9773 tail (pre C3A6)"),
    (0x9780, "after C3A6"),
    (0x9783, "after 77C5"),
    (0x9786, "after 99BF"),
    (0x9789, "after 6176"),
    (0x978F, "after 9BE2"),
    (0x9792, "after A940(+walk+starfield)"),
    (0x9798, "after [20A6]=20A8"),
    (0x979B, "after C57C"),
    (0x979E, "after B5A9"),
    (0x97A4, "after [A8C2]=0"),
    (0x97A7, "after 5F43"),
    (0x97B2, "at 97B2 loop head"),
]
IPS = {ip: lbl for ip, lbl in POINTS}
ORDER = [lbl for _, lbl in POINTS]

def main() -> int:
    demo = load_demo("", "demo_cold_start_full_20260705_123645")
    base = DS * 16
    st = {"f": 0}
    snaps: dict = {}
    union: dict = {}


    class Done(Exception):
        pass



    def on_step(cpu):
        s = cpu.s
        cs, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if ip == FRAME and cs == CS:
            st["f"] += 1
            if st["f"] > 7600:
                raise Done
            snaps.clear()
            return
        if cs != CS or st["f"] not in DEATH or ip not in IPS:
            return
        lbl = IPS[ip]
        if lbl in snaps:
            return                       # only the first visit (the 97B2 head repeats)
        snaps[lbl] = bytes(cpu.mem.data[base:base + 0x10000])
        sp = s.sp & 0xFFFF
        idx = ORDER.index(lbl)
        if idx == 0:
            return
        prev = ORDER[idx - 1]
        if prev not in snaps:
            return
        a, b = snaps[prev], snaps[lbl]
        lo = (sp - 0x100) & 0xFFFF
        n = sum(1 for o in range(0x10000)
                if a[o] != b[o] and o not in EXCLUDED_CELLS and not (lo <= o < sp))
        key = f"{prev} -> {lbl}"
        union.setdefault(key, []).append((st["f"], n))


    try:
        run_ref_step_probe_cold_start(demo, 20000, on_step,
                                      trap=frozenset([(CS, FRAME)] + [(CS, ip) for ip in IPS]))
    except Done:
        pass

    print("DGROUP bytes changed by each step of the continuation (per death window):\n")
    for i in range(1, len(ORDER)):
        key = f"{ORDER[i - 1]} -> {ORDER[i]}"
        ev = union.get(key)
        if not ev:
            print(f"  {key:48s}  (never reached)")
            continue
        counts = [n for _, n in ev]
        tag = "NO-OP" if all(c == 0 for c in counts) else ""
        print(f"  {key:48s}  {counts}  {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
