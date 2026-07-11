"""CONVERGENCE slice B (first measurement): how much of the exe-derived bundle does the native frame
actually depend on?

play_native seeds every level from the 1 MB static_runtime_bundle (an exe snapshot).  To drop it
(assets-only, no exe) we must recover the bytes the runtime READS from it that were NOT produced by the
recovered init + the container load.  This tracks read-before-write over a gameplay run and reports the
footprint, split by segment -- so "converge to assets-only" becomes a measured, shrinking byte count
(the exact remaining "recovered ROM" work).

Usage:  python scripts/measure_rom_footprint.py [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402

CS_BASE = 0x1010 * 16          # the code+data segment the frame reads its tables from
CS_END = CS_BASE + 0x10000
DS_BASE = 0x25CC * 16          # DGROUP


class TrackingMemory(MutFlatMemory):
    """Records read-BEFORE-write linear addresses -- the bytes whose INITIAL (bundle) value the frame
    depends on.  A write to an address before any read clears it (that byte is produced, not needed)."""

    def __init__(self, data) -> None:
        super().__init__(data)
        self.needed = set()       # read before written
        self.written = set()

    def rb(self, seg, off):
        p = self._phys(seg, off)
        if p not in self.written:
            self.needed.add(p)
        return super().rb(seg, off)

    def rw(self, seg, off):
        p = self._phys(seg, off)
        for a in (p, (p + 1) & 0xFFFFF):
            if a not in self.written:
                self.needed.add(a)
        return super().rw(seg, off)

    def ww(self, seg, off, val):
        p = self._phys(seg, off)
        self.written.add(p)
        self.written.add((p + 1) & 0xFFFFF)
        super().ww(seg, off, val)

    def wb(self, seg, off, val):
        self.written.add(self._phys(seg, off))
        super().wb(seg, off, val)


def _span(name, lo, hi, needed):
    n = sum(1 for a in needed if lo <= a < hi)
    print(f"  {name:22} {n:6d} bytes")
    return n


def main(argv) -> int:
    from overkill.native_frame import advance_gameplay_frame_97b2
    from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image
    from scripts.play_native import DEFAULT_BUNDLE, DEFAULT_CONTAINER, make_level_assets, _DS

    frames = int(argv[0]) if argv else 600
    bundle = Path(DEFAULT_BUNDLE).read_bytes()
    container = Path(DEFAULT_CONTAINER).read_bytes()
    level_assets = make_level_assets(container, bundle)

    # Build the cold image the normal way (init + container), THEN wrap it so we only track what the
    # FRAME reads (the build's own writes are the recovered init/container -- already asset-derived).
    seed = build_cold_level_start_image(bundle, 0, container)
    mem = TrackingMemory(bytes(seed.data))
    for _ in range(frames):
        advance_gameplay_frame_97b2(mem, isr_ticks=2, level_assets=level_assets, menu_pick=0)

    needed = mem.needed
    print(f"=== ROM FOOTPRINT over {frames} gameplay frames (read-before-write) ===")
    print(f"total read-before-write bytes: {len(needed)}  (of the 1,048,576-byte image)\n")
    cs = _span("CS code+data (1010)", CS_BASE, CS_END, needed)
    ds = _span("DGROUP (25CC)", DS_BASE, DS_BASE + 0x10000, needed)
    other = len(needed) - cs - ds
    print(f"  {'other segments':22} {other:6d} bytes")
    print(f"\nThe CS + DGROUP-initial read-before-write set is the 'recovered ROM' slice A must produce;")
    print(f"everything else in the {len(bundle):,}-byte bundle is dead weight droppable once A/B land.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
