"""Verify the native HUD-chrome composers (hud_chrome.compose_status_cells_859e /
compose_status_counters_61dc) are byte-exact vs the VM's 1010:859E / 1010:61DC render, driven on a
snapshot.

Those cell renders run only at cold-boot/level-load (no gameplay-demo witness), so this drives them
directly on a snapshot: load it, clear the CPU hook dispatch (so ORIGINAL bytes run: 859E/61DC ->
85D5/6296 -> 5A6C -> 306F), redirect CS:IP to the routine and step to its ret -- the VM oracle B800.
Then run the native composer over the same descriptors / counters + the CS:0BE4 directory + the
decoded PANEL (CS:[95B4]) onto a copy of the pre-render B800, and assert the two pages are identical.

Usage:
    python -m overkill.probes.verify_native_hud_chrome [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CS = 0x1010
B800 = 0xB8000
RET = 0xFFFF
PANEL_SEG_PTR = 0x95B4
DIR_OFF = 0x0BE4
DESCRIPTORS = (0x9682, 0x968C, 0x9696, 0x96A0)


def _load(snap):
    from overkill.runtime import load_overkill_snapshot
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()   # run ORIGINAL bytes (the lindis trick)
    cpu.hook_verifier = None
    return cpu


def _dir_and_panel(cpu):
    from overkill.native_video.hud_chrome import PAGE_SIZE
    mem_np = np.frombuffer(cpu.mem.data, np.uint8)
    panel_base = ((cpu.mem.rw(CS, PANEL_SEG_PTR) & 0xFFFF) << 4) & 0xFFFFF
    panel_source = mem_np[panel_base:panel_base + PAGE_SIZE]
    dir_table = [cpu.mem.rw(CS, (DIR_OFF + 2 * k) & 0xFFFF) for k in range(0x100)]
    return mem_np, panel_source, dir_table


def _drive(cpu, entry):
    """Redirect the CPU to run ORIGINAL bytes from ``entry`` to its near ret."""
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


def _verify_859e(snap) -> bool:
    from overkill.native_video.hud_chrome import PAGE_SIZE, compose_status_cells_859e
    cpu = _load(snap)
    ds = cpu.s.ds & 0xFFFF
    mem_np, panel_source, dir_table = _dir_and_panel(cpu)
    marker = cpu.mem.rw(ds, 0x95FA)
    bdac = cpu.mem.rw(ds, 0xBDAC)
    be16 = cpu.mem.rw(ds, 0xBE16)

    def match_for(bp):
        if marker == 0xFFFF:
            return 0
        return 1 if bp == cpu.mem.rw(ds, ((marker << 1) + 0x95FC) & 0xFFFF) else 0

    cells = []
    for idx, bp in enumerate(DESCRIPTORS):
        color0 = cpu.mem.rw(ds, (bp + 0x00) & 0xFFFF)
        di_base = cpu.mem.rw(ds, (bp + 0x02) & 0xFFFF)
        src_idx = cpu.mem.rw(ds, (bp + 0x04) & 0xFFFF)
        color_idx = be16 if (bdac == 1 and idx == marker) else color0
        cells.append((di_base, src_idx, color_idx, match_for(bp)))

    native = mem_np[B800:B800 + PAGE_SIZE].copy()
    compose_status_cells_859e(native, panel_source, dir_table, cells)
    if not _drive(cpu, 0x859E):
        print("  859E: CHECK -- did not return")
        return False
    vm = mem_np[B800:B800 + PAGE_SIZE]
    diff = int(np.count_nonzero(native != vm))
    print(f"  859E status cells: marker={marker:#06x} diff={diff} -> {'PASS' if diff == 0 else 'CHECK'}")
    return diff == 0


def _verify_61dc(snap) -> bool:
    from overkill.native_video.hud_chrome import PAGE_SIZE, compose_status_counters_61dc
    cpu = _load(snap)
    ds = cpu.s.ds & 0xFFFF
    mem_np, panel_source, dir_table = _dir_and_panel(cpu)
    before = mem_np[B800:B800 + PAGE_SIZE].copy()
    if not _drive(cpu, 0x61DC):
        print("  61DC: CHECK -- did not return")
        return False
    vm = mem_np[B800:B800 + PAGE_SIZE].copy()
    # post-countdown counter values + the trailing gate, read after the drive (what 61DC drew with)
    counters = [cpu.mem.rw(ds, (0x2368 + 2 * k) & 0xFFFF) for k in range(6)]
    a95a = cpu.mem.rw(ds, 0xA95A)
    draw_trailing = a95a != cpu.mem.rw(ds, 0x2374)
    native = before
    compose_status_counters_61dc(native, panel_source, dir_table, counters,
                                 a95a=a95a, draw_trailing=draw_trailing)
    diff = int(np.count_nonzero(native != vm))
    print(f"  61DC counters: a95a={a95a:#06x} trailing={draw_trailing} counters={counters} "
          f"diff={diff} -> {'PASS' if diff == 0 else 'CHECK'}")
    return diff == 0


def main(argv) -> int:
    snap = Path(argv[0]) if argv else (
        ROOT / "artifacts" / "demos" / "demo_play_tandy_L2_full_20260617_180221" / "snapshot")
    print(f"snapshot {snap.parent.name}: native HUD-chrome composers vs VM render")
    ok = _verify_859e(snap) & _verify_61dc(snap)
    print("RESULT:", "PASS -- native HUD-chrome composers byte-exact vs VM" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
