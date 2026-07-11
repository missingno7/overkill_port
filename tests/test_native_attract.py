"""Native attract scene-cell render (the D04D draw) -- VM-free structural tests (front-end slice C).

Confirms the descriptor -> `CS:0BE4` directory -> `CS:[95B4]` bank -> cell chain decodes for every cell
scene and composes onto a frame at the pinned (0x1F,0x18) cursor -- the render half of the native
cold-boot attract (the sequencer is `systems/attract.attract_frame_step`).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from overkill.native_video.attract import (
    LAST_CELL_SCENE,
    SCENE_CELL_XY,
    compose_scene,
    decode_scene_cell,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


def test_scene_cursor_matches_d04d():
    # D04D: mov al,1Fh ; mov ah,18h -> the 5A00 xy convention (x = al*8, y = ah)
    assert SCENE_CELL_XY == (0x1F * 8, 0x18)


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
@pytest.mark.parametrize("scene", range(LAST_CELL_SCENE + 1))
def test_cell_scene_decodes_and_composes(scene):
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    mem = MutFlatMemory(BUNDLE.read_bytes())

    cell = decode_scene_cell(mem, scene)
    assert cell.ndim == 2 and cell.shape[0] > 0 and cell.shape[1] > 0
    assert cell.max() <= 0x0F                       # 4-bit indices

    frame = np.zeros((200, 320), dtype=np.uint8)
    out = compose_scene(frame, mem, scene)
    assert out.shape == (200, 320)
    assert frame.sum() == 0                          # composed into a copy, not the caller's frame
