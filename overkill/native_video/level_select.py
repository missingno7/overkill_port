"""Native LEVEL-SELECT screen composer -- the VM-free form of the D3F0 menu page.

The screen is ``LEVSCR.ENC`` (fullscreen) with two cell-blit cursors drawn per frame by
``1010:D4AA``:

* the LEVEL cursor -- grid cell ``BEDA`` (0..5; two columns of three, +/-3 = column, +/-1 = row),
  xy from the six-entry word table ``DS:BEDE`` (``AL`` = x cell-col, ``AH`` = y scanline, the 5A00
  convention), cell pointer from ``CS:D37E[BEDA]``;
* the second cursor -- ``BEDC`` (0..2), xy from ``DS:BEEA``, cells ``CS:D37E[BEDC + 6]``.

The cells live in ``CHOOSE.ENC``: six 33x136px level-cell frames + three 27x40px option cells,
concatenated in D37E order; the pointers assume the decoded asset sits at segment offset
``0x4000`` (:data:`CHOOSE_SEGMENT_BASE`), so ``cell_offset = D37E[k] - 0x4000``.  The blit is the
``5A6C -> 306F`` raw cell copy (no transparency), here applied directly in index space.
"""
from __future__ import annotations

import numpy as np

#: the D37E cell pointers are segment offsets with the decoded CHOOSE.ENC loaded at 0x4000.
CHOOSE_SEGMENT_BASE = 0x4000
LEVEL_CELLS = 6
OPTION_CELLS = 3


def walk_choose_cells(choose_dec: np.ndarray) -> "list[int]":
    """The nine cell offsets inside the decoded CHOOSE.ENC, walked header-by-header -- the same
    layout the runtime loader records in ``CS:D37E`` (as ``offset + 0x4000``; pinned against a
    live snapshot's table by ``verify_native_level_select``)."""
    offs = []
    off = 0
    for _ in range(LEVEL_CELLS + OPTION_CELLS):
        offs.append(off)
        rows = int(choose_dec[off]) | (int(choose_dec[off + 1]) << 8)
        width = int(choose_dec[off + 2]) | (int(choose_dec[off + 3]) << 8)
        off += 4 + rows * width * 4
    return offs


def cell_indices(choose_dec: np.ndarray, cell_off: int) -> np.ndarray:
    """One CHOOSE cell as ``(rows, width*8)`` colour indices (packed 2px/byte, high nibble left)."""
    rows = int(choose_dec[cell_off]) | (int(choose_dec[cell_off + 1]) << 8)
    width = int(choose_dec[cell_off + 2]) | (int(choose_dec[cell_off + 3]) << 8)
    stride = width * 4
    body = choose_dec[cell_off + 4: cell_off + 4 + rows * stride].reshape(rows, stride)
    out = np.empty((rows, stride * 2), dtype=np.uint8)
    out[:, 0::2] = (body >> 4) & 0x0F
    out[:, 1::2] = body & 0x0F
    return out


def stamp_cursor(frame: np.ndarray, cell: np.ndarray, xy_word: int) -> None:
    """Blit one cursor cell onto the ``(200, 320)`` index ``frame`` at a 5A00 xy word
    (``AL`` = x cell-col -> pixel ``x*8``, ``AH`` = y scanline) -- the 306F raw copy."""
    x_px = (xy_word & 0xFF) * 8
    y = (xy_word >> 8) & 0xFF
    h, w = cell.shape
    frame[y: y + h, x_px: x_px + w] = cell[: max(0, 200 - y), : max(0, 320 - x_px)]


def compose_level_select(levscr_indices: np.ndarray, choose_dec: np.ndarray,
                         level_xy, option_xy,
                         beda: int, bedc: int) -> np.ndarray:
    """The full level-select frame: LEVSCR + the BEDA level cursor + the BEDC option cursor.

    ``level_xy``/``option_xy`` are the DS:BEDE/BEEA word tables (from the image); the cell
    offsets come from walking the decoded CHOOSE.ENC (:func:`walk_choose_cells`).  Returns a
    fresh ``(200, 320)`` index frame."""
    frame = np.array(levscr_indices, dtype=np.uint8, copy=True)
    offs = walk_choose_cells(choose_dec)
    stamp_cursor(frame, cell_indices(choose_dec, offs[beda % LEVEL_CELLS]),
                 level_xy[beda % LEVEL_CELLS])
    stamp_cursor(frame, cell_indices(choose_dec, offs[LEVEL_CELLS + (bedc % OPTION_CELLS)]),
                 option_xy[bedc % OPTION_CELLS])
    return frame
