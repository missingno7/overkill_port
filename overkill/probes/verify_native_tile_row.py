"""Verify ``render_tile_row`` byte-exact against the ORIGINAL 36A2 blit, driven on a snapshot.

Loads the L2 snapshot, clears the hooks, points CS:IP at ``5A7E`` (bx = a chosen row_base,
di = a scratch page-relative dest) and steps to the return -- the REAL ASM draws one tile row
into the work page.  The native ``render_tile_row`` is then compared against those exact bytes
for several row_base values (both graphics banks).

Usage:
    python -m overkill.probes.verify_native_tile_row [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CS = 0x1010
RET = 0xFFFF
ROW_STRIDE = 0x68
TILE_BYTES = 8


def _drive(cpu, entry: int, bx: int, di: int) -> bool:
    ss = cpu.s.ss & 0xFFFF
    sp = (cpu.s.sp - 2) & 0xFFFF
    cpu.mem.ww(ss, sp, RET)
    cpu.s.sp = sp
    cpu.s.cs = CS
    cpu.s.ip = entry
    cpu.s.bx = bx
    cpu.s.di = di
    for _ in range(3_000_000):
        if (cpu.s.cs & 0xFFFF) == CS and (cpu.s.ip & 0xFFFF) == RET:
            return True
        cpu.step()
    return False


def main(argv) -> int:
    from overkill.native_video.tile_row import (BANK2_ROW_BASE, TILE_ROWS, TILES_PER_ROW,
                                                render_tile_row)
    from overkill.runtime import load_overkill_snapshot

    snap = Path(argv[0]) if argv else (
        ROOT / "artifacts" / "demos" / "demo_play_tandy_L2_full_20260617_180221" / "snapshot")
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    mem_np = np.frombuffer(cpu.mem.data, dtype=np.uint8)

    def seg(ptr):
        return cpu.mem.rw(CS, ptr) & 0xFFFF

    plane = mem_np[seg(0x9592) * 16: seg(0x9592) * 16 + 0x10000]
    table = [cpu.mem.rw(CS, (0x8D92 + 2 * k) & 0xFFFF) for k in range(0x100)]
    bank1 = mem_np[seg(0x959A) * 16: seg(0x959A) * 16 + 0x10000]
    bank2 = mem_np[seg(0x959C) * 16: seg(0x959C) * 16 + 0x10000]
    page_base = seg(0x9598) * 16

    ok = True
    for row_base in (0x009C, 0x0400, 0x0B00, 0x0E52, 0x0E5F, 0x0EA0):
        dest_di = 0x0000
        # scrub the dest strip so only the blit's own writes show
        for r in range(TILE_ROWS):
            off = page_base + dest_di + r * ROW_STRIDE
            mem_np[off: off + TILES_PER_ROW * TILE_BYTES] = 0xEE
        # 36AB picks the bank from the GLOBAL DS:[2350] (in the real caller bx == [2350])
        cpu.mem.ww(0x25CC, 0x2350, row_base)
        if not _drive(cpu, 0x5A7E, row_base, dest_di):
            print(f"row_base {row_base:04X}: did not return")
            ok = False
            continue
        vm_rows = np.stack([
            mem_np[page_base + dest_di + r * ROW_STRIDE:
                   page_base + dest_di + r * ROW_STRIDE + TILES_PER_ROW * TILE_BYTES]
            for r in range(TILE_ROWS)])
        graphics = bank2 if row_base >= BANK2_ROW_BASE else bank1
        nat = render_tile_row(plane, row_base, table, graphics)
        # repack the native indices (2px/byte) for the byte compare
        packed = ((nat[:, 0::2] << 4) | nat[:, 1::2]).astype(np.uint8)
        match = np.array_equal(packed, vm_rows)
        print(f"row_base {row_base:04X} (bank {'2' if row_base >= BANK2_ROW_BASE else '1'}): "
              f"{'BYTE-EXACT' if match else f'DIFF {int((packed != vm_rows).sum())} bytes'}")
        ok &= match
    print("RESULT:", "PASS -- render_tile_row is byte-exact vs the driven 36A2 blit"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
