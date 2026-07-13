"""Native (VM-less) render of the cold-boot BLUEPRINT/INTRO screen -- the CE97 compose.

The original's cold boot opens on a blueprint/schematic screen (ship line-art on a grid with briefing
text), NOT the OKMENU title -- established 2026-07-13 by capturing the real B800 aperture at scene 0 of
`demo_cold_start_intro` (see docs/overkill/campaigns/frontend.md).  `1010:CE97` -- long mislabelled the
"menu compose" -- actually composes this screen's **GRID background** from the BLUEBITS cell bank.

`compose_ce97_grid` reproduces that compose exactly (verified byte-exact vs the VM's own CE97 output,
diff 0/64000): the grid is 20 stacked 10-row cell strips from the `CS:[95B8]` (BLUEBITS) bank, looked up
through the `CS:[0C92]` cell directory in the shared rows/width cell format (`level_select.cell_indices`):

  * cell 0x0F  -> rows   0..9   (the top border, 5A24 ax=0),
  * cell 0x10  -> rows  10..189 (a grid row, blitted 18x at rows 10,20,..,180: 5A24 ah=10*cl, cl=18..1),
  * cell 0x11  -> rows 190..199 (the bottom border, 5A24 ah=0xBE).

CE97 draws the grid LAYER only; the boot then overlays the ship schematics + text (all also BLUEBITS
cells) -- :func:`compose_blueprint` draws the WHOLE screen.  The blit position math is the tandy `5A24`
handler `1010:312D`: ``di = row_table[row] + col*4`` over a 2px/byte page, so a cell lands at pixel
``x = col*8, y = row`` (the grid confirms it byte-exact; :func:`compose_ce97_grid`).
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.level_select import cell_indices

CS = 0x1010
BLUEBITS_BANK_PTR = 0x95B8       # CS:[95B8] -> the BLUEBITS cell bank segment
CELL_DIRECTORY = 0x0C92          # CS:[0C92 + cellid*2] -> a cell's offset in the bank
SCREEN_H, SCREEN_W = 200, 320
GRID_ROW_CELL = 0x10             # the repeated grid-row cell
TOP_CELL = 0x0F                  # top border cell (row 0)
BOTTOM_CELL = 0x11               # bottom border cell (row 190)
CELL_ROWS = 10                   # each CE97 cell is a 10-row strip

#: The full cold-boot blueprint compose, ``(cell_id, col, row)`` in blit order -- traced from the VM's
#: 5A24/5A5A cell blits over boot->scene-1 (`trace_frontend_flow` + a 5A5A trap).  The CE97 grid, then
#: the boot's ship-SCHEMATIC + briefing-TEXT overlay (each ship is a 2-colour-pass pair; the text lines
#: 0x0C/0x0D are pre-rendered cells, not live font).  ``col`` is the 5A24 column (pixel x = col*8).
BLUEPRINT_RECIPE: tuple[tuple[int, int, int], ...] = (
    (TOP_CELL, 0, 0),
    *tuple((GRID_ROW_CELL, 0, r) for r in range(180, 0, -10)),
    (BOTTOM_CELL, 0, 190),
    (0x00, 7, 31), (0x03, 23, 57), (0x06, 7, 137), (0x09, 21, 141), (0x0C, 1, 182),
    (0x01, 4, 24), (0x04, 23, 53), (0x07, 4, 133), (0x0A, 21, 141), (0x0D, 1, 182),
)


def compose_ce97_grid(mem) -> np.ndarray:
    """The ``1010:CE97`` blueprint-grid compose -> a ``(200,320)`` 4-bit index frame, byte-exact vs the
    VM.  ``mem`` is the game image (MutFlatMemory) with BLUEBITS loaded at ``CS:[95B8]`` (the cold image
    the bundle/`build_cold_level_start_image` provides)."""
    bank_seg = mem.rw(CS, BLUEBITS_BANK_PTR)
    base = bank_seg * 16
    bank = np.frombuffer(bytes(mem.data[base:base + 0x10000]), dtype=np.uint8)

    def cell(cell_id: int) -> np.ndarray:
        off = mem.rw(CS, (CELL_DIRECTORY + cell_id * 2) & 0xFFFF)
        return cell_indices(bank, off)

    out = np.zeros((SCREEN_H, SCREEN_W), dtype=np.uint8)
    out[0:CELL_ROWS] = cell(TOP_CELL)[:CELL_ROWS]                 # CE97: cell 0x0F at row 0
    grid_row = cell(GRID_ROW_CELL)[:CELL_ROWS]
    for cl in range(18, 0, -1):                                   # 18x at rows 180..10 (5A24 ah=10*cl)
        r = 10 * cl
        out[r:r + CELL_ROWS] = grid_row
    out[190:190 + CELL_ROWS] = cell(BOTTOM_CELL)[:CELL_ROWS]      # cell 0x11 at row 190
    return out


def compose_blueprint(mem) -> np.ndarray:
    """The FINAL FRAME of the cold-boot blueprint screen (all 30 cells at once) -> a ``(200,320)`` 4-bit
    index frame.  **NOT the faithful intro:** the original ANIMATES this -- CE97 draws the grid, then the
    ``CE5F`` loop draws the ships/text from the ``[BD98]`` table (``row,col,cell_id`` x10) in TWO passes
    of 5 cells with a ~20-front-end-frame delay between the layers, plus sounds.  This function draws the
    whole thing in one shot (the end state), which is why it looks static.  Recovering the animation
    (per-frame timing + the delay gate + the sound triggers) and proving it frame-by-frame against
    ``demo_cold_start_intro`` is the open work (see docs/overkill/campaigns/frontend.md).

    Composed from the BLUEBITS cells per :data:`BLUEPRINT_RECIPE` at ``x=col*8, y=row``, transparent-
    blitted; visually/structurally exact vs the VM's composed page with a ~7% byte residual (blit
    opacity where ship cells cross the grid).  ``mem`` is the cold image with BLUEBITS at ``CS:[95B8]``."""
    bank_seg = mem.rw(CS, BLUEBITS_BANK_PTR)
    base = bank_seg * 16
    bank = np.frombuffer(bytes(mem.data[base:base + 0x10000]), dtype=np.uint8)
    out = np.zeros((SCREEN_H, SCREEN_W), dtype=np.uint8)
    for cell_id, col, row in BLUEPRINT_RECIPE:
        c = cell_indices(bank, mem.rw(CS, (CELL_DIRECTORY + cell_id * 2) & 0xFFFF))
        h, w = c.shape
        x = col * 8
        y_end, x_end = min(SCREEN_H, row + h), min(SCREEN_W, x + w)
        if y_end <= row or x_end <= x:
            continue
        sub = c[:y_end - row, :x_end - x]
        m = sub != 0
        out[row:y_end, x:x_end][m] = sub[m]
    return out


__all__ = ["compose_ce97_grid", "compose_blueprint", "BLUEPRINT_RECIPE"]
