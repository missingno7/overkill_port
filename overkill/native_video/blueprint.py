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

DATA_SEGMENT = 0x25CC            # DGROUP: the recipe table lives here
#: The blueprint's cell OVERLAY is not a hardcoded list -- the game reads it from a RECIPE TABLE.
#: CC22 sets ``[BD98] = BD54`` and CE5F walks it: 5 entries per call x 3 calls = 15 cells, each a
#: 3-byte ``(row, col, cell_id)`` triple, blit at ``x = col*8, y = row`` over the grid.  The 15 cells
#: (0x00..0x0E) are the 3 ship schematics + the briefing text, revealed 5 per beat (the animation).
#: (An earlier hardcoded 10-cell guess was MISSING beat 3 -- cells 0x02/0x05/0x08/0x0B/0x0E; reading
#: the real table fixes it.  With the grid, grid + all 15 == the VM's blueprint, 0 under-draw.)
BLUEPRINT_RECIPE_PTR = 0xBD54
BLUEPRINT_RECIPE_ENTRIES = 15
BLUEPRINT_REVEAL_PER_BEAT = 5    # CE5F draws 5 cells per call (3 beats -> 5,10,15 revealed)


def read_blueprint_recipe(mem) -> "list[tuple[int, int, int]]":
    """The 15-cell blueprint overlay recipe, read from the game's own table at ``DS:BD54`` (the source
    CE5F walks) -- ``(cell_id, col, row)`` in draw/reveal order."""
    out = []
    p = BLUEPRINT_RECIPE_PTR
    for _ in range(BLUEPRINT_RECIPE_ENTRIES):
        row = mem.rb(DATA_SEGMENT, p & 0xFFFF)
        col = mem.rb(DATA_SEGMENT, (p + 1) & 0xFFFF)
        cell_id = mem.rb(DATA_SEGMENT, (p + 2) & 0xFFFF)
        out.append((cell_id, col, row))
        p += 3
    return out


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


def compose_blueprint(mem, cells_revealed: "int | None" = None) -> np.ndarray:
    """The cold-boot blueprint screen -> a ``(200,320)`` 4-bit index frame (TANDY 16-colour).  The CE97
    GRID (`compose_ce97_grid`, byte-exact vs the VM), then the first ``cells_revealed`` overlay cells
    from the game's own recipe (`read_blueprint_recipe`, at DS:BD54) transparent-blit over it.

    ``cells_revealed`` drives the ANIMATION exactly as the original does: the reveal builds 5 cells per
    beat (`BLUEPRINT_REVEAL_PER_BEAT`), so 5 -> 10 -> 15 are the three reveal steps; ``None`` = all 15
    (the final frame).  Grid + all 15 == the VM's composed blueprint with ZERO under-draw (verified);
    the per-frame reveal is what `_run_blueprint_intro` replays for the faithful intro."""
    n = BLUEPRINT_RECIPE_ENTRIES if cells_revealed is None else max(0, min(cells_revealed,
                                                                           BLUEPRINT_RECIPE_ENTRIES))
    bank_seg = mem.rw(CS, BLUEBITS_BANK_PTR)
    base = bank_seg * 16
    bank = np.frombuffer(bytes(mem.data[base:base + 0x10000]), dtype=np.uint8)
    out = compose_ce97_grid(mem)                                 # the grid LAYER first (byte-exact)
    for cell_id, col, row in read_blueprint_recipe(mem)[:n]:     # then the revealed overlay cells
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


__all__ = ["compose_ce97_grid", "compose_blueprint", "read_blueprint_recipe",
           "BLUEPRINT_REVEAL_PER_BEAT", "BLUEPRINT_RECIPE_ENTRIES"]
