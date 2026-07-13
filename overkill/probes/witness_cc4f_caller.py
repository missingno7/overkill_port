"""Find CC4F's own caller + how BD81 (its parameter mailbox) gets populated between calls.

The landed `1010:CC4F` hook is byte-exact-verified regardless of *why* it does what it does, but its
own caller is still unrecovered (`grep -n "0xCC4F" overkill/hooks.py` finds only the hook itself) -- and
CC4F unconditionally resets `DS:[BD9A]=BD81h` on every call, which only makes sense if BD81 is a
REUSABLE parameter mailbox the caller refills before each call, not an advancing multi-entry table.
This traps every entry to 1010:CC4F over a cold-start demo and logs the caller's return address (read
directly off SS:SP at entry, since CC4F's own first instruction doesn't push anything) plus the live
BD81 bytes at that moment, to find the caller and see BD81 actually changing between calls.

Usage:
    pypy -m overkill.probes.witness_cc4f_caller [demo_name] [--frames N]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"
TARGET = (0x1010, 0xCC4F)


def witness(demo_name: str, max_frames: "int | None"):
    demo = load_demo(demo_name, demo_name)
    events: list[dict] = []

    def on_ref(cpu):
        cs = cpu.s.cs & 0xFFFF
        ss = cpu.s.ss & 0xFFFF
        ds = cpu.s.ds & 0xFFFF
        ret = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
        bd81 = bytes(cpu.mem.rb(ds, (0xBD81 + i) & 0xFFFF) for i in range(4))
        events.append({"caller": f"{cs:04X}:{ret:04X}", "bd81": bd81.hex()})

    run_ref_step_probe_cold_start(demo, max_frames, on_ref, trap=frozenset((TARGET,)))
    return events


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", nargs="?", default=DEFAULT_DEMO)
    ap.add_argument("--frames", type=int, default=None)
    args = ap.parse_args(argv)
    events = witness(args.demo, args.frames)
    print(f"{len(events)} calls to 1010:CC4F")
    callers = Counter(e["caller"] for e in events)
    print(f"callers: {callers.most_common(10)}")
    for e in events[:60]:
        print(f"  caller={e['caller']}  bd81={e['bd81']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
