"""Probe whether OVERKILL's EGA render hooks are bypassing patched code.

This is a diagnostic for the EGA menu/transition mixing bug.  The unpacked EXE
still rewrites large parts of CS=1010h during its bootstrap, so comparing against
on-disk bytes is misleading.  This tool instead captures a *post-bootstrap* code
baseline at the first timed/video boundary, then watches the EGA presenter,
row-expansion pipeline, dirty-copy cluster, and transition blitters for later
runtime patches while the intro/menu continue running.

Usage:
    python scripts/probe_ega_self_mod.py --boundaries 1200
    OVERKILL_TRACE_CODE_PATCHES=1 python scripts/play.py --video ega
"""
from __future__ import annotations

import argparse
import zlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.runtime import create_overkill_runtime  # noqa: E402

VIDEO_TAIL_EGA = bytes((0x0D, 0x01))
BOUNDARY_HOOKS = {
    "present": (0x1010, 0x2750),
    "retrace": (0x1010, 0x50C9),
    "timer": (0x1010, 0x0679),
}
NON_CGA_DISABLE = {
    (0x1010, 0x58DF),
}
WATCH_RANGES = [
    ("present_2750", 0x2750, 0x27A2),
    ("ega_row_pipeline_27d9", 0x27D9, 0x2990),
    ("mode1_blitter_2d2d", 0x2D2D, 0x2E40),
    ("transition_5c00", 0x5C00, 0x5D20),
    ("postcopy_58df", 0x58DF, 0x5905),
    ("dirty_dispatch_cc90", 0xCC90, 0xCD20),
    ("dispatch_cd40", 0xCD40, 0xCE80),
]


class Boundary(Exception):
    pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--boundaries", type=int, default=1200)
    p.add_argument("--report-at", default="1,2,10,120,500,800,1200",
                   help="comma-separated boundary numbers to print")
    p.add_argument("--keep-non-cga-hooks", action="store_true",
                   help="do not disable 58DF/CCAA/CCC4/CCF0 like play.py does for EGA")
    args = p.parse_args(argv)

    rt = create_overkill_runtime(ROOT / "assets" / "OVERKILL",
                        game_root=ROOT / "assets", command_tail=VIDEO_TAIL_EGA)
    cpu = rt.cpu
    cpu.trace_enabled = False
    if not args.keep_non_cga_hooks:
        for key in NON_CGA_DISABLE:
            cpu.replacement_hooks.pop(key, None)
            cpu.hook_names.pop(key, None)

    counts: dict[str, int] = {name: 0 for name in BOUNDARY_HOOKS}
    for name, addr in BOUNDARY_HOOKS.items():
        base = cpu.replacement_hooks.get(addr)

        def make_boundary_hook(name=name, base=base):
            def hook(c):
                if base is not None:
                    base(c)
                counts[name] += 1
                raise Boundary()
            return hook

        cpu.replacement_hooks[addr] = make_boundary_hook()

    watch_base = 0x1010 << 4
    baseline: dict[str, bytes] | None = None
    report_at = {int(x) for x in args.report_at.split(",") if x.strip()}

    def capture() -> dict[str, bytes]:
        return {
            name: bytes(cpu.mem.data[watch_base + lo:watch_base + hi])
            for name, lo, hi in WATCH_RANGES
        }

    def report(boundary: int) -> None:
        assert baseline is not None
        print(f"\n== boundary {boundary} @ {cpu.s.cs:04X}:{cpu.s.ip:04X} "
              f"steps={cpu.instruction_count} counts={counts} ==")
        any_changed = False
        for name, lo, hi in WATCH_RANGES:
            cur = bytes(cpu.mem.data[watch_base + lo:watch_base + hi])
            diffs = [(lo + i, a, b) for i, (a, b) in enumerate(zip(baseline[name], cur)) if a != b]
            if not diffs:
                continue
            any_changed = True
            first = " ".join(f"{off:04X}:{a:02X}->{b:02X}" for off, a, b in diffs[:8])
            print(f"{name}: changed={len(diffs)} crc={zlib.crc32(cur) & 0xFFFFFFFF:08x} {first}")
        if not any_changed:
            print("watched code ranges unchanged since post-bootstrap baseline")

    for boundary in range(1, args.boundaries + 1):
        while True:
            try:
                cpu.run(10000)
            except Boundary:
                break
        if boundary == 1:
            baseline = capture()
            print(f"captured post-bootstrap baseline at {cpu.s.cs:04X}:{cpu.s.ip:04X}")
        if boundary in report_at:
            report(boundary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
