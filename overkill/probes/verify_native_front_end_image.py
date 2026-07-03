"""Byte-exact gate: the native title/options render vs the VM's cold-boot title screen.

The front-end screens are never in the gameplay demos, and the title render runs only at cold boot, so
this drives a fresh hooks-ON boot (with the checksum accelerator, Tandy command tail) to the title
screen, decodes the VM's visible B800 page to (200,320) indices, and asserts it equals
``native_video.front_end.decode_fullscreen_image(container, "OKMENU.ENC")`` -- the pure, VM-free decode.
Zero diff means the standalone draws the real title screen byte-for-byte, from the game data alone.

Usage:
    python -m overkill.probes.verify_native_front_end_image [steps]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CS = 0x1010
C916 = 0xC916
C91F = 0xC91F
PAGE_SEG_PTR = 0x95A4


def _accel_checksum(cpu):
    from overkill.asset_codecs.boot_selfcheck import boot_selfcheck_checksum
    cx = (cpu.s.cx & 0xFFFF) or 0x10000
    ds, si = cpu.s.ds & 0xFFFF, cpu.s.si & 0xFFFF
    base = ((ds << 4) + si) & 0xFFFFF
    cpu.s.ax = boot_selfcheck_checksum(cpu.s.ax & 0xFFFF, bytes(cpu.mem.data[base:base + cx]))
    cpu.s.si = (si + cx) & 0xFFFF
    cpu.s.cx = 0
    cpu.s.ip = C91F


def main(argv) -> int:
    steps = int(argv[0]) if argv else 90000
    from overkill.runtime import create_overkill_runtime
    from overkill.launch import build_command_tail
    from overkill.native_video.front_end import TITLE_OPTIONS, decode_fullscreen_image
    from overkill.native_video.page_raster import decode_tandy_b800_indices

    container = (ROOT / "assets" / "OVERKILL").read_bytes()
    native = decode_fullscreen_image(container, TITLE_OPTIONS)

    rt = create_overkill_runtime(ROOT / "assets" / "OVERKILL", game_root=ROOT / "assets",
                                 command_tail=build_command_tail("tandy", "pc"), install_replacements=True)
    cpu = rt.cpu
    for _ in range(steps):
        if (cpu.s.cs & 0xFFFF) == CS and (cpu.s.ip & 0xFFFF) == C916:
            _accel_checksum(cpu)
            continue
        cpu.step()

    mem = np.frombuffer(cpu.mem.data, np.uint8)
    page_seg = cpu.mem.rw(CS, PAGE_SEG_PTR) & 0xFFFF
    vm = decode_tandy_b800_indices(mem, (page_seg << 4) & 0xFFFFF)
    diff = int(np.count_nonzero(native != vm))
    print(f"native title vs VM (steps={steps}, page_seg={page_seg:#06x}): B800 diff={diff}px")
    if diff:
        ys, xs = np.where(native != vm)
        print(f"  diff bbox: y[{ys.min()}..{ys.max()}] x[{xs.min()}..{xs.max()}]  "
              f"sample native={[int(native[y, x]) for y, x in zip(ys[:8], xs[:8])]} "
              f"vm={[int(vm[y, x]) for y, x in zip(ys[:8], xs[:8])]} "
              f"at={[(int(y), int(x)) for y, x in zip(ys[:8], xs[:8])]}")
        # per-row diff histogram (which screen bands differ)
        rows_with_diff = sorted(set(int(y) for y in ys))
        print(f"  {len(rows_with_diff)} rows differ; first/last: {rows_with_diff[:4]} ... {rows_with_diff[-4:]}")
    ok = diff == 0
    print("RESULT:", "PASS -- native title/options render byte-exact vs the VM" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
