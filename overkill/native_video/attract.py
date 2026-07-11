"""Native ATTRACT scene-cell render -- the VM-free form of the D04D scene draw (front-end slice C).

The cold-boot attract (1010:D007/D04D) is a scene machine (systems/attract.attract_frame_step): the
current scene id `DS:BE06` selects a 6-byte descriptor at `DS:BE18 + scene*6`, whose word0 is a cell id;
`CS:[0BE4 + cellid*2]` is that cell's offset in the shared cell bank `CS:[95B4]`; D04D blits it via the
5A00/5A6C cell copy at cursor (0x1F, 0x18) every frame.  Scenes 0..7 are these cell screens; scenes >= 8
are the auto-fire gameplay demo (handled by the native frame); scene 0x13 is terminal.

This is the same rows/width cell format + blit play_native already renders for the mission plaque and the
level-select cursors, so this module is a thin compose over `native_video.level_select.cell_indices` --
it reads the descriptor -> directory -> bank chain from the image and returns/stamps the scene cell.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.level_select import cell_indices

CS = 0x1010
DS = 0x25CC
SCENE_ID_CELL = 0xBE06            # DS:BE06 -- current attract scene
SCENE_DESC_TABLE = 0xBE18         # DS:BE18 + scene*6 -> 6-byte descriptor (word0 = cell id)
SCENE_DESC_STRIDE = 6
CELL_DIRECTORY = 0x0BE4           # CS:[0BE4 + cellid*2] -> cell offset in the CS:[95B4] bank
CELL_BANK_SEG_CELL = 0x95B4       # CS:[95B4] -> the cell bank segment
SCENE_CELL_XY = (0x1F * 8, 0x18)  # 5A00 (al=0x1F, ah=0x18): the blit cursor -- (x px, y scanline)
FIRST_CELL_SCENE = 0              # scenes 0..7 are cell screens
LAST_CELL_SCENE = 7


def scene_cell_id(mem, scene: int) -> int:
    """The cell id for an attract scene -- word0 of its DS:BE18 descriptor."""
    return mem.rw(DS, (SCENE_DESC_TABLE + scene * SCENE_DESC_STRIDE) & 0xFFFF)


def _cell_offset(mem, cell_id: int) -> int:
    return mem.rw(CS, (CELL_DIRECTORY + cell_id * 2) & 0xFFFF)


def decode_scene_cell(mem, scene: int) -> np.ndarray:
    """Decode an attract scene's graphic cell (a ``(rows, width*8)`` index block) from the image:
    descriptor -> directory -> the ``CS:[95B4]`` bank, via the shared rows/width cell format."""
    offset = _cell_offset(mem, scene_cell_id(mem, scene))
    bank_seg = mem.rw(CS, CELL_BANK_SEG_CELL)
    base = bank_seg * 16
    bank = np.frombuffer(bytes(mem.data[base:base + 0x10000]), dtype=np.uint8)
    return cell_indices(bank, offset)


def compose_scene(frame: np.ndarray, mem, scene: int) -> np.ndarray:
    """Stamp an attract scene's cell onto a COPY of the ``(200,320)`` index ``frame`` at the D04D
    cursor (0x1F, 0x18) -- the 5A6C raw cell copy."""
    out = frame.copy()
    cell = decode_scene_cell(mem, scene)
    x, y = SCENE_CELL_XY
    h, w = cell.shape
    out[y:y + h, x:x + w] = cell[:max(0, 200 - y), :max(0, 320 - x)]
    return out
