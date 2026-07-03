"""Verify the native HUD status-cell composer (hud_chrome.compose_status_cells_859e) is byte-exact
vs the VM's 1010:859E render, driven on a snapshot.

The 859E cell render runs only at cold-boot/level-load (no gameplay-demo witness), so this drives it
directly on a snapshot: load the snapshot, clear the CPU hook dispatch (so ORIGINAL 859E->85D5->5A6C
->306F bytes run), redirect CS:IP to 859E and step to its ret -- the VM oracle output in B800.  Then
run compose_status_cells_859e over the same descriptors (SS:9682/968C/9696/96A0), the CS:0BE4 cell
directory, and the decoded PANEL (CS:[95B4]) onto a copy of the pre-render B800, and assert the two
B800 pages are byte-identical.

Usage:
    python -m overkill.probes.verify_native_hud_chrome [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CS = 0x1010
E859 = 0x859E
B800 = 0xB8000
RET = 0xFFFF
PANEL_SEG_PTR = 0x95B4
DIR_OFF = 0x0BE4
DESCRIPTORS = (0x9682, 0x968C, 0x9696, 0x96A0)


def main(argv) -> int:
    snap = Path(argv[0]) if argv else (
        ROOT / "artifacts" / "demos" / "demo_play_tandy_L2_full_20260617_180221" / "snapshot")
    from overkill.runtime import load_overkill_snapshot
    from overkill.native_video.hud_chrome import PAGE_SIZE, compose_status_cells_859e

    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()   # run ORIGINAL bytes (the lindis trick)
    cpu.hook_verifier = None
    mem = cpu.mem
    ds = cpu.s.ds & 0xFFFF
    mem_np = np.frombuffer(mem.data, np.uint8)

    # --- gather the composer inputs from the snapshot ---
    panel_seg = mem.rw(CS, PANEL_SEG_PTR) & 0xFFFF
    panel_base = (panel_seg << 4) & 0xFFFFF
    panel_source = mem_np[panel_base:panel_base + PAGE_SIZE]
    dir_table = [mem.rw(CS, (DIR_OFF + 2 * k) & 0xFFFF) for k in range(0x100)]
    marker = mem.rw(ds, 0x95FA)
    bdac = mem.rw(ds, 0xBDAC)
    be16 = mem.rw(ds, 0xBE16)

    def match_for(bp: int) -> int:
        if marker == 0xFFFF:
            return 0
        return 1 if bp == mem.rw(ds, ((marker << 1) + 0x95FC) & 0xFFFF) else 0

    cells = []
    for idx, bp in enumerate(DESCRIPTORS):
        color0 = mem.rw(ds, (bp + 0x00) & 0xFFFF)
        di_base = mem.rw(ds, (bp + 0x02) & 0xFFFF)
        src_idx = mem.rw(ds, (bp + 0x04) & 0xFFFF)
        color_idx = be16 if (bdac == 1 and idx == marker) else color0
        cells.append((di_base, src_idx, color_idx, match_for(bp)))

    before = mem_np[B800:B800 + PAGE_SIZE].copy()

    # --- native composer onto a copy of the pre-render page ---
    native = before.copy()
    compose_status_cells_859e(native, panel_source, dir_table, cells)

    # --- VM oracle: drive original 859E to its ret ---
    ss = cpu.s.ss & 0xFFFF
    sp = (cpu.s.sp - 2) & 0xFFFF
    mem.ww(ss, sp, RET)
    cpu.s.sp = sp
    cpu.s.cs = CS
    cpu.s.ip = E859
    for _ in range(3_000_000):
        if (cpu.s.cs & 0xFFFF) == CS and (cpu.s.ip & 0xFFFF) == RET:
            break
        cpu.step()
    else:
        print("CHECK -- 859E did not return")
        return 1
    vm = mem_np[B800:B800 + PAGE_SIZE]

    ok = np.array_equal(native, vm)
    diff = int(np.count_nonzero(native != vm))
    print(f"snapshot {snap.parent.name}: native HUD-cell composer vs VM 859E: "
          f"marker={marker:#06x} B800 diff={diff}")
    if not ok:
        d = np.flatnonzero(native != vm)
        print(f"  first diff offsets B800+{d[0]:#06x}..{d[-1]:#06x} (n={len(d)})")
    print("RESULT:", "PASS -- native status-cell composer byte-exact vs VM 859E" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
