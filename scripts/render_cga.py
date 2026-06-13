"""Render the emulator's CGA video memory (B800) to a PNG.

OVERKILL's unpacked executable runs in CGA mode (the resident video-mode
selector ``CS:[95BC]`` is 0).  Its frame-present blit at ``1010:447B`` copies the
decoded work buffer into segment ``CS:[95A4] = B800h`` using the standard CGA
320x200 4-colour interlaced layout:

    line y  ->  offset = (y & 1) * 0x2000 + (y >> 1) * 80
    each byte  ->  4 pixels, 2 bits each, most-significant pixel first.

Dumping that region as text mode (80x25 character cells) produces meaningless
CP437 glyphs, which is what a naive screen grab shows.  This tool decodes it as
CGA graphics instead so a frame can actually be inspected.

Dependency-free: PNG is written with the standard-library ``zlib`` only.

Usage:
    python scripts/render_cga.py <snapshot_dir> [--seg B800] [--palette 1h]
                                 [--scale 2] [--out frame.png]
    python scripts/render_cga.py --steps 2000000 [...]   # run fresh, then dump
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# CGA palettes.  The background colour (index 0) is programmable on real CGA via
# port 03D9h; the other three come from the selected palette/intensity.
CGA_PALETTES = {
    "1h": [(0, 0, 0), (0x55, 0xFF, 0xFF), (0xFF, 0x55, 0xFF), (0xFF, 0xFF, 0xFF)],  # cyan/magenta/white
    "1l": [(0, 0, 0), (0x00, 0xAA, 0xAA), (0xAA, 0x00, 0xAA), (0xAA, 0xAA, 0xAA)],
    "0h": [(0, 0, 0), (0x55, 0xFF, 0x55), (0xFF, 0x55, 0x55), (0xFF, 0xFF, 0x55)],  # green/red/yellow
    "0l": [(0, 0, 0), (0x00, 0xAA, 0x00), (0xAA, 0x55, 0x00), (0xAA, 0xAA, 0xAA)],
}

# Standard 16-colour RGBI/EGA palette used by the live EGA viewer.
EGA_PALETTE = [
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xAA), (0x00, 0xAA, 0x00), (0x00, 0xAA, 0xAA),
    (0xAA, 0x00, 0x00), (0xAA, 0x00, 0xAA), (0xAA, 0x55, 0x00), (0xAA, 0xAA, 0xAA),
    (0x55, 0x55, 0x55), (0x55, 0x55, 0xFF), (0x55, 0xFF, 0x55), (0x55, 0xFF, 0xFF),
    (0xFF, 0x55, 0x55), (0xFF, 0x55, 0xFF), (0xFF, 0xFF, 0x55), (0xFF, 0xFF, 0xFF),
]


@lru_cache(maxsize=65536)
def _ega_quad_pixels(p0: int, p1: int, p2: int, p3: int, scale: int) -> bytes:
    px = bytearray()
    for bit in range(7, -1, -1):
        colour = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1) | (((p2 >> bit) & 1) << 2) | (((p3 >> bit) & 1) << 3)
        r, g, b = EGA_PALETTE[colour]
        px += bytes((r, g, b)) * scale
    return bytes(px)

EGA_SHADOW_BASE = 0x100000
EGA_PLANE_STRIDE = 0x10000
EGA_LEGACY_PLANE_STRIDE = 0x2000
EGA_BYTES_PER_ROW = 40
TANDY_BANK_STRIDE = 0x2000
TANDY_BYTES_PER_ROW = 160



def write_png(path: Path, width: int, height: int, rows: list[bytearray]) -> None:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + typ
            + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for row in rows:
        raw.append(0)  # filter type 0 (none)
        raw.extend(row)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def _byte_table(palette: str, scale: int) -> list[bytes]:
    """Precompute the scaled RGB bytes for every possible CGA byte (4 pixels)."""
    pal = CGA_PALETTES[palette]
    table: list[bytes] = [b""] * 256
    for value in range(256):
        px = bytearray()
        for p in range(4):
            r, g, b = pal[(value >> (6 - 2 * p)) & 3]
            px += bytes((r, g, b)) * scale
        table[value] = bytes(px)
    return table


def render_ppm(mem: bytes, seg: int, palette: str = "1h", scale: int = 2) -> tuple[int, int, bytes]:
    """Fast path used by the live viewer: decode B800 straight to binary PPM (P6).

    Uses a 256-entry byte lookup so each scanline is 80 dict lookups + a join
    instead of a per-pixel inner loop, which keeps the viewer interactive.
    """
    base = (seg & 0xFFFF) * 16
    table = _byte_table(palette, scale)
    width, height = 320, 200
    out = bytearray(f"P6\n{width * scale} {height * scale}\n255\n".encode("ascii"))
    for y in range(height):
        off = (y & 1) * 0x2000 + (y >> 1) * 80
        line = b"".join([table[mem[base + off + xb]] for xb in range(80)])
        out += line * scale  # vertical scale: repeat each source scanline
    return width * scale, height * scale, bytes(out)



def render_ega_ppm(mem: bytes, seg: int = 0xA000, scale: int = 2, start_offset: int = 0) -> tuple[int, int, bytes]:
    """Decode the live EGA shadow planes to binary PPM (P6).

    The real EGA mode uses four hardware bitplanes selected through the
    sequencer map-mask register.  The source-port runtime stores the currently
    presented frame in an explicit shadow layout at ``seg``:

        plane 0: seg:0000..1F3F
        plane 1: seg:2000..3F3F
        plane 2: seg:4000..5F3F
        plane 3: seg:6000..7F3F

    Each byte represents eight horizontal pixels; colour index bits come from
    the four planes in the usual EGA order.  ``start_offset`` is the CRTC display
    start address tracked from ports 03D4h/03D5h; old snapshots default to zero.
    """
    # Three accepted plane layouts, distinguished by buffer length:
    #   * a tight view of exactly the four shadow planes (the live viewer slices
    #     these out of runtime memory) -> planes start at offset 0;
    #   * full runtime memory, where newer builds store the planes outside the
    #     CPU-visible A000h aperture so real offsets/pages such as A000:2000
    #     cannot corrupt the displayed shadows -> planes start at EGA_SHADOW_BASE;
    #   * older saved byte snapshots using the legacy in-aperture layout.
    if len(mem) == EGA_PLANE_STRIDE * 4:
        base = 0
        plane_stride = EGA_PLANE_STRIDE
    elif len(mem) >= EGA_SHADOW_BASE + EGA_PLANE_STRIDE * 4:
        base = EGA_SHADOW_BASE
        plane_stride = EGA_PLANE_STRIDE
    else:
        base = (seg & 0xFFFF) * 16
        plane_stride = EGA_LEGACY_PLANE_STRIDE
    width, height = 320, 200
    out = bytearray(f"P6\n{width * scale} {height * scale}\n255\n".encode("ascii"))
    data = mem
    start_offset &= 0xFFFF
    for y in range(height):
        row = (start_offset + y * EGA_BYTES_PER_ROW) & 0xFFFF
        line = bytearray()
        for xb in range(EGA_BYTES_PER_ROW):
            off = (row + xb) & 0xFFFF
            line += _ega_quad_pixels(
                data[base + off],
                data[base + plane_stride + off],
                data[base + plane_stride * 2 + off],
                data[base + plane_stride * 3 + off],
                scale,
            )
        out += line * scale
    return width * scale, height * scale, bytes(out)


def render_tandy_ppm(mem: bytes, seg: int = 0xB800, scale: int = 2) -> tuple[int, int, bytes]:
    """Decode Tandy/PCjr 320x200x16 packed graphics to binary PPM (P6).

    OVERKILL's mode-2 presenter uses the Tandy 16-colour packed layout: one byte
    contains two horizontal pixels, high nibble first, and scanlines are split
    across four 8 KiB banks:

        offset(y, x_byte) = (y & 3) * 0x2000 + (y >> 2) * 160 + x_byte

    The game only presents a 208-pixel-wide active work-buffer rectangle, starting
    at byte offset 00A0h (screen row 4 in this layout); the rest of the aperture
    remains whatever the original code drew/cleared there.  The renderer decodes
    the whole 320x200 aperture so direct VRAM effects and borders stay visible.
    """
    base = (seg & 0xFFFF) * 16
    width, height = 320, 200
    out = bytearray(f"P6\n{width * scale} {height * scale}\n255\n".encode("ascii"))
    data = mem
    for y in range(height):
        row = (y & 3) * TANDY_BANK_STRIDE + (y >> 2) * TANDY_BYTES_PER_ROW
        line = bytearray()
        for xb in range(TANDY_BYTES_PER_ROW):
            value = data[base + row + xb]
            for colour in ((value >> 4) & 0x0F, value & 0x0F):
                r, g, b = EGA_PALETTE[colour]
                line += bytes((r, g, b)) * scale
        out += line * scale
    return width * scale, height * scale, bytes(out)

def render_cga(mem: bytes, seg: int, palette: str, scale: int) -> tuple[int, int, list[bytearray]]:
    base = (seg & 0xFFFF) * 16
    pal = CGA_PALETTES[palette]
    width, height = 320, 200
    rows: list[bytearray] = []
    for y in range(height):
        off = (y & 1) * 0x2000 + (y >> 1) * 80
        line = bytearray()
        for xb in range(80):
            byte = mem[base + off + xb]
            for p in range(4):
                r, g, b = pal[(byte >> (6 - 2 * p)) & 3]
                line += bytes((r, g, b)) * scale
        for _ in range(scale):
            rows.append(bytearray(line))
    return width * scale, height * scale, rows


def load_memory(args: argparse.Namespace) -> bytes:
    if args.steps is not None:
        from overkill_port.runtime import create_runtime

        rt = create_runtime(ROOT / "assets" / "OVERKILL", game_root=ROOT / "assets")
        rt.cpu.trace_enabled = False
        rt.cpu.run(args.steps)
        return bytes(rt.program.memory.data)
    snap = Path(args.snapshot_dir)
    return (snap / "memory_1mb.bin").read_bytes()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render emulator CGA video memory to PNG")
    p.add_argument("snapshot_dir", nargs="?", help="snapshot directory containing memory_1mb.bin")
    p.add_argument("--steps", type=int, default=None, help="run a fresh runtime this many steps instead")
    p.add_argument("--seg", default=None, help="video segment in hex (default B800 for CGA, A000 for EGA)")
    p.add_argument("--video", default="cga", choices=("cga", "ega", "tandy"), help="decode CGA packed, EGA shadow-planar, or Tandy packed video")
    p.add_argument("--palette", default="1h", choices=sorted(CGA_PALETTES), help="CGA palette")
    p.add_argument("--scale", type=int, default=2)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    if args.snapshot_dir is None and args.steps is None:
        p.error("provide a snapshot_dir or --steps")

    mem = load_memory(args)
    seg = int(args.seg, 16) if args.seg is not None else (0xA000 if args.video == "ega" else 0xB800)
    out = Path(args.out) if args.out else (
        (Path(args.snapshot_dir) / "frame.png") if args.snapshot_dir else ROOT / "frame.png"
    )
    if args.video in {"ega", "tandy"}:
        # Keep the CLI PNG writer dependency-free by converting the PPM rows back
        # to RGB rows; the live Tk viewer uses the PPM helpers directly.
        if args.video == "ega":
            width, height, ppm = render_ega_ppm(mem, seg, args.scale)
            label = "EGA shadow"
        else:
            width, height, ppm = render_tandy_ppm(mem, seg, args.scale)
            label = "Tandy"
        header_end = ppm.find(b"\n255\n") + len(b"\n255\n")
        raw = ppm[header_end:]
        row_bytes = width * 3
        rows = [bytearray(raw[y * row_bytes:(y + 1) * row_bytes]) for y in range(height)]
        write_png(out, width, height, rows)
        print(f"wrote {out} ({width}x{height}, {label} seg {seg:04X})")
    else:
        width, height, rows = render_cga(mem, seg, args.palette, args.scale)
        write_png(out, width, height, rows)
        print(f"wrote {out} ({width}x{height}, seg {seg:04X}, palette {args.palette})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
