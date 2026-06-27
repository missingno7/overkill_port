"""The FrameSnapshot extractor reconstructs the render intent from object slots.

This verifies the *extraction* reads the right record fields/offsets. Grounding
the draw list against the real A846/A90C present scan + the VRAM round-trip is a
later step (enhanced_renderer_plan.md R2).
"""
from __future__ import annotations

from dos_re.memory import Memory

from overkill.recovered.adapters.frame_snapshot_adapter import extract_frame_snapshot
from overkill.recovered.adapters.frame_snapshot_adapter import (
    BG_COLUMN_INDEX,
    BG_SCROLL_ROW,
    PRESENT_SOURCE_CURSOR,
    PRESENT_SOURCE_PAGE_PTR,
    PRESENT_VIDEO_PAGE_PTR,
)
from overkill.recovered.domain.frame_snapshot import (
    BackgroundLayer,
    CameraState,
    PresentComposition,
    SpriteDraw,
)
from overkill.recovered.ds_globals import VIEW_TARGET_X, VIEW_TARGET_Y
from overkill.recovered.views.object_slots import (
    FRAME_TIMER_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_BASE,
    OBJECT_SLOT_STRIDE,
    OFF_DRAW_SCRATCH_OR_DI,
    ObjectSlotView,
)


def _slot(mem, ds, base, index):
    return ObjectSlotView(mem, ds, base + index * OBJECT_SLOT_STRIDE)


def test_extract_frame_snapshot_reads_active_onscreen_slots():
    mem = Memory()
    ds = 0x1A0F

    mem.ww(ds, VIEW_TARGET_X, 0x0050)
    mem.ww(ds, VIEW_TARGET_Y, 0xFFF0)  # signed -16

    # HUD layer: the six status-counter cells.
    mem.ww(ds, FRAME_TIMER_TABLE_BASE, 0x0003)
    mem.ww(ds, FRAME_TIMER_TABLE_BASE + 2, 0x0001)

    # HUD score (BCD: low @2314, high @2316).
    mem.ww(ds, 0x2314, 0x0990)
    mem.ww(ds, 0x2316, 0x0003)

    # Background layer: the level-map scroll position + master-plane segment.
    mem.ww(ds, BG_SCROLL_ROW, 0x0042)
    mem.ww(ds, BG_COLUMN_INDEX, 0x0007)
    mem.ww(0x1010, 0x9592, 0x245A)  # CS:[9592] -> background master plane

    # Present composition: the composited source page the 3354 presenter blits.
    mem.ww(0x1010, PRESENT_SOURCE_PAGE_PTR, 0x35FF)  # CS:[9598] -> source page
    mem.ww(0x1010, PRESENT_VIDEO_PAGE_PTR, 0xB800)   # CS:[95A4] -> visible aperture
    mem.ww(ds, PRESENT_SOURCE_CURSOR, 0x3810)        # DS:[234C] -> source cursor

    s0 = _slot(mem, ds, GAMEPLAY_OBJECT_TABLE_BASE, 0)
    s0.active_word = 1
    s0.x_word = 0x0010
    s0.y_word = 0x0020
    s0.sprite_or_state = 0x0031
    s0.hazard_class = 0x0004  # writable base of the draw_layer read alias
    s0.scan_flag = 0x0002     # writable base of the object_type read alias
    s0.set_u16(OFF_DRAW_SCRATCH_OR_DI, 0x1234)  # on-screen dest

    # index 1: active but OFF-SCREEN (+0C == FFFF) -> culled, not on the draw list.
    s1 = _slot(mem, ds, GAMEPLAY_OBJECT_TABLE_BASE, 1)
    s1.active_word = 1
    s1.sprite_or_state = 0x0099
    s1.set_u16(OFF_DRAW_SCRATCH_OR_DI, 0xFFFF)

    s2 = _slot(mem, ds, GAMEPLAY_OBJECT_TABLE_BASE, 2)
    s2.active_word = 1
    s2.x_word = 0xFFFE        # signed -2
    s2.y_word = 0x0005
    s2.sprite_or_state = 0x0076
    s2.hazard_class = 0x0001
    s2.scan_flag = 0x0000
    s2.set_u16(OFF_DRAW_SCRATCH_OR_DI, 0x5678)

    snap = extract_frame_snapshot(mem, ds)

    assert snap.playfield.camera == CameraState(x=0x50, y=-16)
    assert snap.playfield.sprites == (
        SpriteDraw(sprite=0x0031, x=0x10, y=0x20, layer=0x04, object_type=0x02, screen_di=0x1234),
        SpriteDraw(sprite=0x0076, x=-2, y=0x05, layer=0x01, object_type=0x00, screen_di=0x5678),
    )
    assert snap.hud.counters == (0x0003, 0x0001, 0, 0, 0, 0)
    assert snap.hud.score_bcd == (0x0990, 0x0003)
    assert snap.background == BackgroundLayer(
        scroll_row=0x0042, column_index=0x0007, plane_segment=0x245A
    )
    assert snap.present == PresentComposition(
        source_page=0x35FF, source_cursor=0x3810, video_page=0xB800
    )
