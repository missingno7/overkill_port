"""Diagnose EGA / Tandy / CGA video output by inspecting the presented aperture.

The EGA mode currently renders geometry-correct but mostly black/blue output.
The working hypothesis is that only colour indices 0 and 1 are produced, i.e.
only one bitplane (plane 0) ends up populated or rendered.  This tool answers
that directly: it runs the original code to the first frame-present in the
requested video mode and reports

  * EGA: nonzero-byte count for each of the four shadow planes (0..3), and the
    full 16-entry colour-index histogram of the decoded frame;
  * Tandy: nonzero-byte count of the packed aperture and the 16-entry nibble
    (colour) histogram;
  * CGA: nonzero-byte count and the 4-entry 2bpp colour histogram.

If the EGA histogram only has counts in indices 0 and 1 while planes 1..3 are
all zero, the problem is upstream of the renderer (the planes are never filled);
if planes 1..3 have data but the histogram is still 0/1 only, the bug is in how
the planes are combined.

Usage:
    python scripts/diag_video.py --video ega [--max-steps 6000000]
    python scripts/diag_video.py --video tandy
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill_port.runtime import create_runtime  # noqa: E402

VIDEO_TAIL = {
    "cga": b"",
    "ega": bytes((0x0D, 0x01)),
    "tandy": bytes((0x0D, 0x02)),
}
PRESENT_HOOK = {
    "cga": (0x1010, 0x447B),
    "ega": (0x1010, 0x2750),
    "tandy": (0x1010, 0x3354),
}
# Hooks play.py disables for the interactive non-CGA modes: they are only
# verified for mode 0, so let interpreted ASM handle them in EGA/Tandy.
NON_CGA_DISABLE = {
    (0x1010, 0x41A6), (0x1010, 0x4D15), (0x1010, 0x58DF),
    (0x1010, 0xCCAA), (0x1010, 0xCCC4), (0x1010, 0xCCF0),
}
EGA_PLANE_STRIDE = 0x2000
EGA_BYTES_PER_ROW = 40
TANDY_BANK_STRIDE = 0x2000
TANDY_BYTES_PER_ROW = 160


def run_to_present(video: str, max_steps: int):
    rt = create_runtime(
        ROOT / "assets" / "OVERKILL.UNLZEXE.EXE",
        game_root=ROOT / "assets",
        command_tail=VIDEO_TAIL[video],
    )
    cpu = rt.cpu
    cpu.trace_enabled = False
    if video != "cga":
        for key in NON_CGA_DISABLE:
            cpu.replacement_hooks.pop(key, None)
            cpu.hook_names.pop(key, None)
    target = PRESENT_HOOK[video]

    # Count EGA sequencer map-mask writes (03C4/03C5) and attribute-controller
    # palette writes (03C0).  These distinguish a plane-fill problem from a
    # palette-remap problem: if the game programs the AC palette (03C0) the fixed
    # render palette would be wrong; if it only toggles the map mask the planes
    # are written directly and the question is whether all four get filled.
    counters = {"map_mask": Counter(), "palette_writes": 0}
    orig_pw = cpu.port_writer

    def counting_pw(c, port, val, bits):
        p = port & 0xFFFF
        if p in (0x3C4, 0x3C5):
            counters["map_mask"][(p, val & 0xFF)] += 1
        elif p == 0x3C0:
            counters["palette_writes"] += 1
        if orig_pw is not None:
            return orig_pw(c, port, val, bits)
        return None

    cpu.port_writer = counting_pw

    # Wrap the present hook so we can let it run (fill the aperture) and stop
    # right after the first frame is presented.
    base = cpu.replacement_hooks.get(target)
    fired = {"n": 0}

    def stop_after_present(c):
        if base is not None:
            base(c)
        fired["n"] += 1

    cpu.replacement_hooks[target] = stop_after_present

    for i in range(max_steps):
        if fired["n"] > 0:
            break
        cpu.step()
    return rt, fired["n"], counters


def diag_ega(mem: bytes) -> None:
    base = 0xA000 * 16
    print("EGA shadow-plane occupancy (A000 aperture):")
    plane_nonzero = []
    for p in range(4):
        start = base + p * EGA_PLANE_STRIDE
        chunk = mem[start:start + 200 * EGA_BYTES_PER_ROW]
        nz = sum(1 for b in chunk if b)
        plane_nonzero.append(nz)
        print(f"  plane {p}: {nz:6d} / {len(chunk)} nonzero bytes")

    hist = Counter()
    for y in range(200):
        row = y * EGA_BYTES_PER_ROW
        for xb in range(EGA_BYTES_PER_ROW):
            off = row + xb
            p0 = mem[base + off]
            p1 = mem[base + EGA_PLANE_STRIDE + off]
            p2 = mem[base + EGA_PLANE_STRIDE * 2 + off]
            p3 = mem[base + EGA_PLANE_STRIDE * 3 + off]
            for bit in range(7, -1, -1):
                idx = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1) \
                    | (((p2 >> bit) & 1) << 2) | (((p3 >> bit) & 1) << 3)
                hist[idx] += 1
    _print_hist("EGA 16-colour index histogram", hist, 16)

    used = [i for i in range(16) if hist.get(i, 0)]
    print(f"  colour indices actually used: {used}")
    if plane_nonzero[1] == plane_nonzero[2] == plane_nonzero[3] == 0 and plane_nonzero[0]:
        print("  => DIAGNOSIS: only plane 0 is populated; planes 1..3 are empty.")
        print("     The black/blue output is upstream of the renderer (planes never filled).")
    elif used and max(used) <= 1:
        print("  => DIAGNOSIS: planes carry data but only indices 0/1 appear.")
        print("     The bug is in how the four planes are combined into colour indices.")


def diag_tandy(mem: bytes) -> None:
    base = 0xB800 * 16
    chunk = mem[base:base + 0x8000]
    nz = sum(1 for b in chunk if b)
    print(f"Tandy aperture (B800): {nz} / {len(chunk)} nonzero bytes")
    hist = Counter()
    for y in range(200):
        row = (y & 3) * TANDY_BANK_STRIDE + (y >> 2) * TANDY_BYTES_PER_ROW
        for xb in range(TANDY_BYTES_PER_ROW):
            value = mem[base + row + xb]
            hist[(value >> 4) & 0x0F] += 1
            hist[value & 0x0F] += 1
    _print_hist("Tandy 16-colour nibble histogram", hist, 16)
    print(f"  colour indices actually used: {[i for i in range(16) if hist.get(i, 0)]}")


def diag_cga(mem: bytes) -> None:
    base = 0xB800 * 16
    chunk = mem[base:base + 0x4000]
    nz = sum(1 for b in chunk if b)
    print(f"CGA aperture (B800): {nz} / {len(chunk)} nonzero bytes")
    hist = Counter()
    for y in range(200):
        off = (y & 1) * 0x2000 + (y >> 1) * 80
        for xb in range(80):
            byte = mem[base + off + xb]
            for sh in (6, 4, 2, 0):
                hist[(byte >> sh) & 3] += 1
    _print_hist("CGA 4-colour index histogram", hist, 4)


def _print_hist(title: str, hist: Counter, n: int) -> None:
    total = sum(hist.values()) or 1
    print(f"{title}:")
    for i in range(n):
        c = hist.get(i, 0)
        bar = "#" * int(40 * c / total)
        print(f"  idx {i:2d}: {c:8d}  {100*c/total:5.1f}%  {bar}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", choices=("cga", "ega", "tandy"), default="ega")
    p.add_argument("--max-steps", type=int, default=6_000_000)
    args = p.parse_args(argv)

    rt, fired, counters = run_to_present(args.video, args.max_steps)
    cs, ip = rt.cpu.addr()
    print("=" * 60)
    print(f"video={args.video}  present-fired={fired}  stopped@{cs:04X}:{ip:04X}")
    print("=" * 60)
    if fired == 0:
        print("WARNING: no frame was presented within the step budget; the aperture")
        print("below may be empty.  Increase --max-steps.")
    mem = bytes(rt.program.memory.data)
    if args.video == "ega":
        diag_ega(mem)
    elif args.video == "tandy":
        diag_tandy(mem)
    else:
        diag_cga(mem)

    if args.video == "ega":
        print("-" * 60)
        mm = counters["map_mask"]
        print("EGA register activity up to first present:")
        for (port, val), c in sorted(mm.items()):
            print(f"  OUT {port:04X}h, {val:02X}h : {c}")
        print(f"  attribute-controller (03C0h) palette writes: {counters['palette_writes']}")
        if counters["palette_writes"] == 0:
            print("  => palette is the fixed default (no AC remap); colour mapping is not")
            print("     the cause.  Combined with sparse planes 2/3 above, the issue is")
            print("     that the EGA decode/work-buffer under-fills the high planes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
