"""Native tile-row renderer -- the VM-free form of the ``1010:36A2`` Tandy tile-row blit.

The scroll's row pull (``A781 -> A7EB -> A81B -> jmp 5A7E -> mode-2 body 36A2``) draws ONE
13-tile row of the level's terrain into the work page:

* per tile: ``id = plane[row_base + k]`` (the tile PLANE, seg ``[9592]``); a zero id still
  indexes the table (``id - 1`` wraps) exactly as the ASM's ``dec bl`` does;
* ``src = graphics[CS:[8D92 + (id-1)*2] ...]`` -- the tile-graphics OFFSET TABLE; the source
  segment is ``[959A]`` (the level graphics) or ``[959C]`` when ``row_base >= 0xE5F`` (the
  second bank);
* 16 rows x 8 bytes (16 px, 2px/byte) per tile, the dest advancing ``di += 0x60`` between rows
  (the 0x68 page stride minus the 8 written bytes).

This module owns only the PURE pixel form: one row of 13 tiles as ``(16, 208)`` colour indices.
``verify_native_tile_row`` drives the ORIGINAL 36A2 on a snapshot (hooks cleared) and asserts
byte-equality against this function -- the same synthetic-ASM oracle gate the HUD chrome uses.
"""
from __future__ import annotations

import numpy as np

TILES_PER_ROW = 13
TILE_W_BYTES = 8      # 16 px, 2 px/byte
TILE_ROWS = 16
BANK2_ROW_BASE = 0x0E5F   # 36AB: row_base >= 0xE5F reads the [959C] bank


#: the visible window: 12 16-row bands from screen y=4; band b's plane row = row_base - (b+1)*0xD
WINDOW_BANDS = 12
WINDOW_TOP_Y = 4
PLANE_ROW_STRIDE = 0x0D


def compose_tile_window(frame: np.ndarray, plane, row_base: int, table_8d92, graphics,
                        phase_234e: int = 0) -> None:
    """Compose the visible terrain window onto a ``(200, 320)`` index ``frame`` (in place).

    Band ``b`` (screen rows ``4 + b*16 ..``) carries the tile row at plane index
    ``row_base - (b+1)*0x0D`` -- oracle-fit to 2 px (the residue is sprites) on the pure-VM
    present-500 fixture with ``[234E] == 0``.  A nonzero ``phase_234e`` (the mid-strip scroll
    step) is NOT modelled yet: a first ``16-k`` slice guess made phased frames WORSE (measured),
    so this fails loud rather than draw a misaligned field -- fit the phase against captured
    phased fixtures before wiring it."""
    if phase_234e:
        raise ValueError(f"[234E] phase {phase_234e:#x} not modelled -- strip-aligned scroll "
                         "only (fit the sub-strip offset against a phased pure-VM fixture)")
    for band in range(WINDOW_BANDS):
        rb = (row_base - (band + 1) * PLANE_ROW_STRIDE) & 0xFFFF
        strip = render_tile_row(plane, rb, table_8d92, graphics)
        y0 = WINDOW_TOP_Y + band * TILE_ROWS
        frame[y0: y0 + TILE_ROWS, 0: strip.shape[1]] = strip


def render_tile_row(plane: "bytes | np.ndarray", row_base: int,
                    table_8d92, graphics: "bytes | np.ndarray") -> np.ndarray:
    """One 13-tile terrain row as ``(16, 208)`` colour indices.

    ``plane`` is the tile plane (seg ``[9592]``'s bytes); ``row_base`` the DS:2350 cursor (the
    plane index of the row's FIRST tile); ``table_8d92`` the 256-entry tile-graphics offset
    table (``CS:8D92``, indexed ``(id - 1) & 0xFF``); ``graphics`` the SOURCE bank's bytes
    (the caller picks ``[959A]`` vs ``[959C]`` per :data:`BANK2_ROW_BASE`)."""
    out = np.empty((TILE_ROWS, TILES_PER_ROW * TILE_W_BYTES * 2), dtype=np.uint8)
    g = np.asarray(graphics if isinstance(graphics, np.ndarray) else
                   np.frombuffer(graphics, dtype=np.uint8))
    p = plane
    for k in range(TILES_PER_ROW):
        tile_id = p[(row_base + k) & 0xFFFF]
        src = table_8d92[(tile_id - 1) & 0xFF]
        cell = g[src: src + TILE_ROWS * TILE_W_BYTES].reshape(TILE_ROWS, TILE_W_BYTES)
        x0 = k * TILE_W_BYTES * 2
        out[:, x0 + 0::2][:, :TILE_W_BYTES] = (cell >> 4) & 0x0F
        out[:, x0 + 1::2][:, :TILE_W_BYTES] = cell & 0x0F
    return out
