"""Native static-HUD-chrome blit -- the VM-free form of the 1010:306F panel-cell copy.

The static HUD/border chrome (the WEAPON/MISSILES/DRONE/GADGETS/UPGRADES panel graphics + icon
caps) is drawn at level start (and, being static, never re-blit during play) by the status-cell
render path ``859E -> 85D5 -> 5A6C``.  In Tandy mode ``5A6C`` dispatches to ``1010:306F``, which
is a raw ``rep movsb`` copy of a decoded PANEL cell into the packed B800 page -- no colour mask,
no transparency (unlike the ``3153`` HUD-text glyph blit).  This module is the pure page-writer
form of that blit, so the eventual cold-boot backend can compose the chrome from the recovered
PANEL asset (``asset_codecs/planar``) instead of capturing the VM page.

``306F`` geometry (confirmed by disassembly, and pinned byte-exact against the original opcodes by
``tests/test_hud_chrome.py``'s synthetic-ASM oracle):

    lodsw -> rows (CX)          ; a {rows, width} 2-word cell header at DS:SI
    lodsw -> width; width<<2    ; -> BP = row stride in bytes (Tandy 4-plane: width*4)
    ES = CS:[95A4]              ; the present page segment (0xB800)
    per row: rep movsb <stride> bytes DS:SI -> ES:DI ; DI += 0x2000 ; if DI&0x8000: DI += 0x80A0

The per-row ``sub di,bp; add di,2000h`` nets to ``DI += 0x2000`` (the rep-movsb advance is
undone), the same four-bank Tandy geometry ``native_video.hud_text`` uses.

WITNESS NOTE: the in-game render path (859E/306F) runs only at cold-boot/level-load, before every
recorded snapshot demo, so there is no gameplay-demo witness (see loop_blockers.md).  This blit is
therefore verified by the synthetic-ASM oracle (original 306F opcodes vs this function on synthetic
cells) -- the same "synthetic fixtures + interpreted ASM" gate the asset codecs use -- pending the
cold-boot frame that will consume it.
"""
from __future__ import annotations

import numpy as np

PAGE_SIZE = 0x10000       # DI is a 16-bit page offset
BANK_ADVANCE = 0x2000     # 306F: DI += 0x2000 per row (next Tandy bank)
BANK_WRAP = 0x80A0        # 306F: DI += 0x80A0 once DI crosses 0x8000
CELL_HEADER_BYTES = 4     # two words: {rows, width}
STRIDE_SHIFT = 2          # row stride bytes = width << 2


def _le_word(source: np.ndarray, off: int) -> int:
    return int(source[off]) | (int(source[off + 1]) << 8)


def paste_panel_cell(page: np.ndarray, source: np.ndarray, src_off: int, di: int) -> int:
    """Blit one PANEL cell into the packed ``page`` at ``ES:DI`` exactly as ``1010:306F`` does.

    ``source`` is a flat ``uint8`` byte array; ``src_off`` is the byte offset of the cell's
    ``{rows, width}`` header, followed by ``rows * width*4`` contiguous pixel bytes.  ``page`` is
    the ``PAGE_SIZE`` packed B800 window (mutated in place); ``di`` is the 16-bit dest cursor.
    Each row copies ``width*4`` bytes, then ``di`` steps one Tandy bank (+0x2000, wrapping +0x80A0
    past 0x8000).  A raw copy -- no colour mask.  Returns the source offset just past the cell.
    """
    rows = _le_word(source, src_off)
    width = _le_word(source, src_off + 2)
    stride = (width << STRIDE_SHIFT) & 0xFFFF
    si = src_off + CELL_HEADER_BYTES
    cur = di & 0xFFFF
    if stride:
        cols = np.arange(stride)
        for _ in range(rows):
            page[(cur + cols) & 0xFFFF] = source[si:si + stride]
            si += stride
            cur = (cur + BANK_ADVANCE) & 0xFFFF
            if cur & 0x8000:
                cur = (cur + BANK_WRAP) & 0xFFFF
    return si
