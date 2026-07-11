"""Level-start mission PLAQUE compositor (the D367 briefing blit) -- VM-free unit tests.

The plaque is the "missing screen between level-select and the level" the standalone used to skip:
``plaq{level}.enc`` overlaid at the D367 position (24, 0x47) over the level's initial frame, held by
the D305 wait until fire.  These tests confirm every level's plaque decodes to a placed cell and
composes at the pinned position; the visual placement is proven by artifacts/plaque_placement_proof.png
and the D367 disasm (al=03 -> x=24, ah=0x47 -> y=71).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from overkill.native_video.plaque import (
    PLAQUE_X_PX,
    PLAQUE_Y,
    compose_plaque,
    decode_plaque_cell,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTAINER = ROOT / "assets" / "OVERKILL"


def test_plaque_placement_matches_d367():
    # D367: mov ah,47h ; mov al,03h -> the 5A00 xy convention (x = al*8, y = ah)
    assert (PLAQUE_X_PX, PLAQUE_Y) == (0x03 * 8, 0x47)


@pytest.mark.skipif(not CONTAINER.exists(), reason="OVERKILL container not present")
@pytest.mark.parametrize("level_index", range(6))
def test_every_level_plaque_decodes_and_composes(level_index):
    container = CONTAINER.read_bytes()
    cell = decode_plaque_cell(container, level_index)
    assert cell.ndim == 2 and cell.shape[0] > 0 and cell.shape[1] > 0
    assert cell.max() <= 0x0F                       # 4-bit indices
    frame = np.zeros((200, 320), dtype=np.uint8)
    out = compose_plaque(frame, cell)
    assert out.shape == (200, 320)
    # the plaque region is stamped (non-destructive to the input frame; overlaid at the D367 xy)
    h, w = cell.shape
    assert np.array_equal(out[PLAQUE_Y:PLAQUE_Y + h, PLAQUE_X_PX:PLAQUE_X_PX + w],
                          cell[:max(0, 200 - PLAQUE_Y), :max(0, 320 - PLAQUE_X_PX)])
    assert frame.sum() == 0                          # compose_plaque did not mutate the caller's frame
