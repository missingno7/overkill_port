"""Native LEVEL-START mission PLAQUE compositor -- the VM-free form of the D367 briefing blit.

Between level-select and the first gameplay frame, the original shows a mission briefing: a placed
``plaq{level}.enc`` cell (planet name + number + icon + a one-line description) overlaid on the
level's initial screen (animated starfield + the HUD panel), held by the ``1010:D305`` "get ready"
wait until the player presses FIRE.

``1010:D367`` is the blit::

    D367  mov ah,47h ; mov al,03h ; call 5A00     ; select the blit target (the 5A00 xy convention:
                                                    AL = x cell-col -> pixel x*8, AH = y scanline)
    D36E  xor si,si ; ds = cs:[95B6] ; call 5A6C  ; raw cell copy from the loaded plaque, offset 0

so the plaque lands at pixel ``(24, 0x47)`` and its bytes are the same ``rows,width`` cell the
level-select CHOOSE cells use (:func:`overkill.native_video.level_select.cell_indices`).  The plaque
file is ``plaq{level_index}.enc`` (0-based: level 1 -> plaq0), ``PLAQUE_RAW_LEN`` (0x1778) raw bytes.
"""
from __future__ import annotations

import numpy as np

from overkill.asset_codecs.container import load_container_asset
from overkill.asset_codecs.planar import deplanarize_tandy
from overkill.native_video.level_select import cell_indices

#: D367's 5A00 target: al=03 -> x = 3*8 = 24 px; ah=0x47 -> y = 71 scanlines.
PLAQUE_X_PX = 0x03 * 8
PLAQUE_Y = 0x47


def decode_plaque_cell(container_data, level_index: int) -> np.ndarray:
    """Decode ``plaq{level_index}.enc`` to a ``(rows, width*8)`` index cell (the D367 source)."""
    name = f"plaq{level_index % 6}.enc"
    dec = np.frombuffer(
        deplanarize_tandy(load_container_asset(container_data, name),
                          sprite_mode=False, emit_item_headers=True),
        dtype=np.uint8)
    return cell_indices(dec, 0)


def compose_plaque(frame: np.ndarray, plaque_cell: np.ndarray) -> np.ndarray:
    """Overlay the plaque cell onto a COPY of the ``(200, 320)`` index ``frame`` at the D367 position
    (the 5A6C raw copy: no transparency, a straight cell stamp)."""
    out = frame.copy()
    h, w = plaque_cell.shape
    y, x = PLAQUE_Y, PLAQUE_X_PX
    out[y: y + h, x: x + w] = plaque_cell[: max(0, 200 - y), : max(0, 320 - x)]
    return out
