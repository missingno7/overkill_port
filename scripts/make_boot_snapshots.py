"""Regenerate the boot-phase snapshots the LZEXE/init lift campaign verifies against.

The cold-boot chain is a lifter campaign (docs/overkill/loop_blockers.md 2026-07-10): the game's
init reaches the 1010:D007 frontier in ~18770 instructions across 72 routines, 74% of them liftable.
liftverify replays FORWARD from a snapshot, so to cover boot routines you snapshot early and run to
D007 with the hooks installed.  This writes two useful start points:

  boot_entry_snapshot : the MZ image at entry (1C32:000E), before any init -- for the phase-1
                        (segment-setup) routines that BUILD the 1010 code segment.
  boot_1010_entry     : the first instruction executed IN the 1010 segment (~8134 instr in) -- for
                        the phase-2 table-building init routines.

Then, e.g.:
    python dos_re/tools/liftverify.py --exe assets/OVERKILL --snapshot artifacts/boot_1010_entry \
        --entries-file <boot entries> --steps 900000 --emit-dir lifted_boot
Proven working: 6 ORACLE_PASSING, 0 DIVERGED on the first pass (the loop is correct on boot code;
full coverage needs snapshots at each routine's own entry, or a cold-boot harness).

Usage:
    python scripts/make_boot_snapshots.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

FRONTIER = (0x1010, 0xD007)
CODE_SEG = 0x1010


def main() -> int:
    from dos_re.snapshot import write_snapshot

    from overkill.launch import build_command_tail
    from overkill.runtime import create_overkill_runtime

    tail = build_command_tail("tandy", "pc")

    rt = create_overkill_runtime(str(ROOT / "assets" / "OVERKILL"), command_tail=tail)
    write_snapshot(rt, ROOT / "artifacts" / "boot_entry_snapshot",
                   status="boot entry (MZ loaded, pre-init)", steps=0, trace_tail=())
    print(f"boot_entry_snapshot at {rt.cpu.s.cs:04X}:{rt.cpu.s.ip:04X}")

    rt = create_overkill_runtime(str(ROOT / "assets" / "OVERKILL"), command_tail=tail)
    cpu = rt.cpu
    orig = cpu.__class__.step
    n = [0]

    def step(_c=cpu):
        n[0] += 1
        if (_c.s.cs & 0xFFFF) == CODE_SEG and n[0] > 1:
            raise StopIteration
        if n[0] > 3_000_000:
            raise StopIteration
        return orig(_c)

    cpu.step = step
    try:
        while True:
            cpu.step(cpu)
    except StopIteration:
        pass
    write_snapshot(rt, ROOT / "artifacts" / "boot_1010_entry",
                   status="first 1010 execution (mid-init)", steps=n[0], trace_tail=())
    print(f"boot_1010_entry at {cpu.s.cs:04X}:{cpu.s.ip:04X} after {n[0]} instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
