"""Verify the native HUD glyph blit is byte-exact vs the VM's 1010:3153, from the game's
own tables (no position/timing assumption).

`3153` renders a glyph as, per row byte: ``DS:1514[byte*4]`` (the bit->4bpp expand) ANDed
with the colour mask from ``DS:215C``, written to the B800 page. This witness proves the
native `hud_glyph.draw_glyph` (over the recovered `DS:1816` font) reproduces those exact
pixels, two ways:

  1. the VM's actual ``DS:1514`` expand table equals ``draw_glyph``'s bit->0xF-nibble
     spread, for all 256 byte values; and
  2. for every char, ``draw_glyph(font[char], colour)`` equals the VM cell built from the
     real tables (``expand[font_byte]`` decoded, ANDed with the colour).

Both holding means the native glyph rendering is byte-identical to `3153`'s output. (The
score-digit *placement* is the separate score-display layer; this proves the glyph leaf.)

Usage:
    python -m overkill.probes.verify_hud_glyph <snapshot_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.native_video.hud_glyph import (  # noqa: E402
    HUD_COLOR_OFF,
    draw_glyph,
    read_glyph_font,
)
from overkill.runtime import load_overkill_snapshot  # noqa: E402

EXPAND_OFF = 0x1514


def _bit_spread(b: int):
    nib = [0xF if (b >> (7 - j)) & 1 else 0 for j in range(8)]
    return [(nib[2 * k] << 4) | nib[2 * k + 1] for k in range(4)]


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    snap = Path(argv[0])
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", snap, game_root=ROOT / "assets")
    cpu = rt.cpu
    ds = cpu.s.ds & 0xFFFF
    rb = cpu.mem.rb
    mem = np.frombuffer(cpu.mem.data, dtype=np.uint8)
    color = rb(ds, HUD_COLOR_OFF) & 0xFF
    font = read_glyph_font(mem, ds)

    # (1) the VM's expand table == the native bit-spread, all 256 bytes.
    expand_bad = sum(
        1 for b in range(256)
        if [rb(ds, (EXPAND_OFF + b * 4 + i) & 0xFFFF) for i in range(4)] != _bit_spread(b)
    )

    # (2) per-char: draw_glyph == the VM cell from the real font/expand/colour tables.
    char_bad = 0
    for ch in range(256):
        native = draw_glyph(np.zeros((8, 8), dtype=np.uint8), 0, 0, font[ch], color)
        vm = np.zeros((8, 8), dtype=np.uint8)
        for r in range(8):
            gb = int(font[ch][r])
            e4 = [rb(ds, (EXPAND_OFF + gb * 4 + i) & 0xFFFF) for i in range(4)]
            for i in range(8):
                nib = (e4[i // 2] >> 4) if i % 2 == 0 else (e4[i // 2] & 0xF)
                vm[r, i] = nib & color          # F&colour = colour, 0&colour = 0
        if not np.array_equal(native, vm):
            char_bad += 1

    print(f"colour DS:215C = {color:#x}; DS:1816 font + DS:1514 expand read from snapshot")
    print(f"(1) expand table all-256 vs native bit-spread: {256 - expand_bad}/256 match")
    print(f"(2) per-char draw_glyph == VM cell: {256 - char_bad}/256 match")
    ok = expand_bad == 0 and char_bad == 0
    print("RESULT:", "PASS — native HUD glyph rendering is byte-exact vs 1010:3153" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
