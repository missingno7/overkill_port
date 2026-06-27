"""VM-independent Tandy page rasterizer — the native backend's visual source.

This turns the recovered semantic page into RGB *without* reading the VM
framebuffer, by replaying the present blit (1010:3354) from the composited source
page ``[9598]`` at the scroll cursor ``[234C]`` and decoding through the recovered
Tandy geometry + palette (``recovered/systems/tandy_screen``).

The present copies a 0x34-word (0x68-byte = 208 px) by 0xC0-row (192) window of the
source page into the visible aperture starting at dest byte 0xA0 (screen x=0,y=4),
advancing through the four interlaced banks. So the **playfield** occupies
``x in [0, 208), y in [4, 196)``; the surrounding HUD/border (top strip, right
112 px panel, bottom strip) is drawn separately and persisted in the page — it is
not produced by this blit (see ``render_present_page_rgb`` notes).

Grounded against the live framebuffer: on corpus snapshots the playfield region of
``render_present_page_rgb`` matches the decoded on-screen B800 exactly when the
saved page and framebuffer are in phase (a ~1 % residue otherwise is the known
one-present skew between the saved ``[9598]`` and B800). Pure NumPy; no VM.
"""
from __future__ import annotations

import numpy as np

from overkill.recovered.systems.tandy_screen import (
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TANDY_BANK_STRIDE,
    TANDY_BYTES_PER_ROW,
    TANDY_PALETTE_RGB,
)

_PALETTE = np.array(TANDY_PALETTE_RGB, dtype=np.uint8)  # (16, 3)

# Present blit (1010:3354) constants.
PRESENT_WORDS_PER_ROW = 0x34          # BX: words copied per row
PRESENT_ROW_BYTES = PRESENT_WORDS_PER_ROW * 2  # 0x68 bytes (208 px)
PRESENT_ROWS = 0xC0                    # BP: rows copied (192)
PRESENT_DEST_START = 0x00A0           # DI: first dest byte (screen x=0, y=4)
PRESENT_BANK_ADVANCE = 0x2000
PRESENT_BANK_WRAP = 0x80A0

# The playfield rectangle the present blit fills (screen space).
PLAYFIELD_X0 = 0
PLAYFIELD_W = PRESENT_ROW_BYTES * 2    # 208 px
PLAYFIELD_Y0 = 4
PLAYFIELD_H = PRESENT_ROWS             # 192 rows


def decode_tandy_b800_rgb(buf: np.ndarray, base: int = 0) -> np.ndarray:
    """Decode a Tandy mode-2 packed aperture to an ``(H, W, 3)`` RGB array.

    ``buf`` is a flat ``uint8`` view of memory; ``base`` is the byte offset of the
    aperture. Mirrors the verified framebuffer decode: four 8 KiB banks,
    ``off = (y&3)*0x2000 + (y>>2)*160 + x_byte``, high nibble = left pixel.
    """
    y = np.arange(SCREEN_HEIGHT)
    rowbase = base + (y & 3) * TANDY_BANK_STRIDE + (y >> 2) * TANDY_BYTES_PER_ROW
    cols = buf[(rowbase[:, None] + np.arange(TANDY_BYTES_PER_ROW)[None, :])]  # (200,160)
    idx = np.stack([(cols >> 4) & 0x0F, cols & 0x0F], axis=2)                 # (200,160,2)
    return _PALETTE[idx.reshape(SCREEN_HEIGHT, SCREEN_WIDTH)]


def replay_present_blit(mem: np.ndarray, source_page: int, source_cursor: int):
    """Replay 1010:3354 from ``[source_page:source_cursor]`` into a B800 scratch.

    Returns ``(scratch, written)`` where ``scratch`` is a 0x10000 ``uint8`` aperture
    holding the blitted playfield (HUD region left zero) and ``written`` is a bool
    mask of the bytes the blit wrote.
    """
    src_base = ((source_page & 0xFFFF) << 4) & 0xFFFFF
    scratch = np.zeros(0x10000, dtype=np.uint8)
    written = np.zeros(0x10000, dtype=bool)
    di = PRESENT_DEST_START
    width = PRESENT_ROW_BYTES
    cursor = source_cursor & 0xFFFF
    for r in range(PRESENT_ROWS):
        soff = (src_base + cursor + r * width) & 0xFFFFF
        scratch[di:di + width] = mem[soff:soff + width]
        written[di:di + width] = True
        di = (di + PRESENT_BANK_ADVANCE) & 0xFFFF
        if di & 0x8000:
            di = (di + PRESENT_BANK_WRAP) & 0xFFFF
    return scratch, written


def playfield_pixel_mask(written: np.ndarray) -> np.ndarray:
    """Map a written-byte mask (from :func:`replay_present_blit`) to an
    ``(H, W)`` bool mask of the screen pixels the present blit covers."""
    y = np.arange(SCREEN_HEIGHT)
    rowbase = (y & 3) * TANDY_BANK_STRIDE + (y >> 2) * TANDY_BYTES_PER_ROW
    off = rowbase[:, None] + np.arange(TANDY_BYTES_PER_ROW)[None, :]
    bytemask = written[off]                       # (200,160)
    return np.repeat(bytemask, 2, axis=1)         # (200,320)


def render_present_page_rgb(mem: np.ndarray, source_page: int, source_cursor: int) -> np.ndarray:
    """Render the playfield to RGB from the semantic page (VM-framebuffer-free).

    Replays the present blit from ``[source_page:source_cursor]`` and decodes it.
    The returned ``(H, W, 3)`` array holds the scrolling playfield in
    ``x in [0, 208), y in [4, 196)``; pixels outside that (the HUD/border) are
    black here — they come from the persisted HUD layer, modelled separately.
    """
    scratch, _ = replay_present_blit(mem, source_page, source_cursor)
    return decode_tandy_b800_rgb(scratch, 0)
