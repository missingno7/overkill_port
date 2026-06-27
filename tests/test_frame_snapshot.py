"""The FrameSnapshot extractor reconstructs the render intent from object slots.

This verifies the *extraction* reads the right record fields/offsets. Grounding
the draw list against the real A846/A90C present scan + the VRAM round-trip is a
later step (enhanced_renderer_plan.md R2).
"""
from __future__ import annotations

from dos_re.memory import Memory

from overkill.recovered.adapters.frame_snapshot_adapter import extract_frame_snapshot
from overkill.recovered.domain.frame_snapshot import CameraState, SpriteDraw
from overkill.recovered.ds_globals import VIEW_TARGET_X, VIEW_TARGET_Y
from overkill.recovered.views.object_slots import (
    GAMEPLAY_OBJECT_TABLE_BASE,
    OBJECT_SLOT_STRIDE,
    ObjectSlotView,
)


def _slot(mem, ds, base, index):
    return ObjectSlotView(mem, ds, base + index * OBJECT_SLOT_STRIDE)


def test_extract_frame_snapshot_reads_active_object_slots():
    mem = Memory()
    ds = 0x1A0F

    mem.ww(ds, VIEW_TARGET_X, 0x0050)
    mem.ww(ds, VIEW_TARGET_Y, 0xFFF0)  # signed -16

    s0 = _slot(mem, ds, GAMEPLAY_OBJECT_TABLE_BASE, 0)
    s0.active_word = 1
    s0.x_word = 0x0010
    s0.y_word = 0x0020
    s0.sprite_or_state = 0x0031
    s0.hazard_class = 0x0004  # writable base of the draw_layer read alias
    s0.scan_flag = 0x0002     # writable base of the object_type read alias

    # index 1 left inactive (active_word == 0) -> excluded.

    s2 = _slot(mem, ds, GAMEPLAY_OBJECT_TABLE_BASE, 2)
    s2.active_word = 1
    s2.x_word = 0xFFFE        # signed -2
    s2.y_word = 0x0005
    s2.sprite_or_state = 0x0076
    s2.hazard_class = 0x0001
    s2.scan_flag = 0x0000

    snap = extract_frame_snapshot(mem, ds)

    assert snap.camera == CameraState(x=0x50, y=-16)
    assert snap.sprites == (
        SpriteDraw(sprite=0x0031, x=0x10, y=0x20, layer=0x04, object_type=0x02),
        SpriteDraw(sprite=0x0076, x=-2, y=0x05, layer=0x01, object_type=0x00),
    )
