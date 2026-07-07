"""Verify ``run_tile_cue_row_7948`` against the ORIGINAL 7948, driven on the planet-1 snapshot.

For every plane row containing a planet-1 cue id, drive the REAL ``1010:7948`` (hooks cleared,
``DS:A408 = row``) and run the native fn on an identical image copy; compare the WHOLE DGROUP
plus the tile plane afterward.  Any stamp byte, consume write, allocator-cursor move, or
caller-frame leak the native form gets wrong shows as a byte diff.

Usage:
    python -m overkill.probes.verify_native_tile_cues [max_rows]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CS = 0x1010
DS = 0x25CC
RET = 0xFFFF
SNAP = ROOT / "artifacts" / "demos" / "demo_play_tandy_L1_start_20260618_143947" / "snapshot"
CUE_IDS = (0x04, 0x07, 0x6C, 0x6D, 0xAC, 0xB1, 0xC9)


def _drive(cpu, entry: int) -> bool:
    ss = cpu.s.ss & 0xFFFF
    sp = (cpu.s.sp - 2) & 0xFFFF
    cpu.mem.ww(ss, sp, RET)
    cpu.s.sp = sp
    cpu.s.cs = CS
    cpu.s.ip = entry
    for _ in range(3_000_000):
        if (cpu.s.cs & 0xFFFF) == CS and (cpu.s.ip & 0xFFFF) == RET:
            return True
        cpu.step()
    return False


def main(argv) -> int:
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.adapters.tile_cues import run_tile_cue_row_7948
    from overkill.runtime import load_overkill_snapshot

    max_rows = int(argv[0]) if argv else 12
    base_state = (SNAP / "memory_1mb.bin").read_bytes()
    img0 = MutFlatMemory(base_state)
    assert img0.rw(DS, 0x2356) == 1, "the L1 snapshot must be planet 1"
    plane_seg = img0.rw(CS, 0x9592)
    plane = bytes(img0.data[plane_seg * 16: plane_seg * 16 + 3744])
    rows = sorted({(i // 13) * 13 for i, b in enumerate(plane) if b in CUE_IDS})[:max_rows]
    if not rows:
        print("RESULT: SKIP -- no cue ids in the plane (unexpected)")
        return 1

    ok = True
    for row in rows:
        rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(SNAP),
                                    game_root=ROOT / "assets")
        cpu = rt.cpu
        cpu.replacement_hooks.clear()
        cpu.hook_verifier = None
        cpu.mem.ww(DS, 0xA408, row)
        # the 8209 stamp's +32/+34 leak the CALLER frame ([bp+4]/[bp+2]) -- read the drive's
        # live frame so the native form reproduces the same bytes
        bp = cpu.s.bp & 0xFFFF
        ss_ = cpu.s.ss & 0xFFFF
        leak_32 = cpu.mem.rw(ss_, (bp + 4) & 0xFFFF)
        leak_34 = cpu.mem.rw(ss_, (bp + 2) & 0xFFFF)
        if not _drive(cpu, 0x7948):
            print(f"row {row:04X}: the drive did not return")
            ok = False
            continue
        vm = np.frombuffer(cpu.mem.data, dtype=np.uint8)

        nat = MutFlatMemory(base_state)
        run_tile_cue_row_7948(nat, row, leak_32, leak_34)
        nb = np.frombuffer(bytes(nat.data), dtype=np.uint8)

        dg = np.s_[DS * 16: DS * 16 + 0x10000]
        pl = np.s_[plane_seg * 16: plane_seg * 16 + 3744]
        dg_diff = np.flatnonzero(vm[dg] != nb[dg])
        # DS:A26E..A277 is the 7948 family's hand-rolled return-address scratch (the drive
        # observed 81EC/81CF/7AF3/796A/FFFF frames there) -- no game-state meaning, excluded
        dg_diff = dg_diff[(dg_diff < 0xA26E) | (dg_diff > 0xA277)]
        pl_diff = np.flatnonzero(vm[pl] != nb[pl])
        ids = sorted({plane[row + k] for k in range(13)} & set(CUE_IDS))
        if dg_diff.size or pl_diff.size:
            ok = False
            print(f"row {row:04X} (ids {['%02X' % i for i in ids]}): DIFF -- "
                  f"dgroup {dg_diff.size}B at {[f'{d:04X}' for d in dg_diff[:6]]}, "
                  f"plane {pl_diff.size}B at {[f'{d:04X}' for d in pl_diff[:6]]}")
        else:
            print(f"row {row:04X} (ids {['%02X' % i for i in ids]}): BYTE-EXACT")
    print("RESULT:", "PASS -- run_tile_cue_row_7948 is byte-exact vs the driven 7948"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
