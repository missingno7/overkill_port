"""Bridge: extract a semantic :class:`FrameSnapshot` from live VM memory.

Reads the original object tables + camera globals through memory views and
reconstructs the render-intent snapshot the enhanced renderer/interpolator
consume. This is the one place VM memory meets the render dataclasses.

**Status: ASM_MATCHED (content + order); not yet VERIFIED.** Grounded against the
real present scan via `overkill/probes/inspect_draw_list.py`: the present lists
`DS:8D12` (gameplay) and `DS:32CA` (effect) are **static pointer arrays into the
two object tables** (2B5C / 23B4 + 0x38 stride), and `run_present_object_scan_pair_a90c`
walks `8D12` (gameplay) **first**, then `32CA` (effect), checking each slot's
active flag. So the draw list *is* the active slots of both tables, in
**gameplay-then-effect** order — matched below.

On-screen culling is grounded too: the present pass writes the projected screen
destination to record +0C (the layer scan's `OBJ_DEST_SLOT_0C`), and `0xFFFF`
means off-screen — so the draw list is active AND `+0C != 0xFFFF`, with `+0C`
carried as `screen_di`.

Live-witness findings (`overkill/probes/witness_draw_order.py`, instrumenting the
real 5AC8 draw dispatch over a Tandy demo — these are things static snapshots
could not show):
  1. **Draw order == scan order.** `draw_layer` (values 4/1/6) is NOT the z-sort;
     the draws come out in present/scan order. So no per-layer sort is needed —
     the grounded present order IS the draw order.
  2. **One object is missing from this extractor.** A `sprite=0001 @layer 3`
     object is drawn FIRST (back-most, scrolling with the camera) but is not in
     the effect/gameplay tables this walks — it lives in a separate fixed slot
     (likely the player/a special object). TODO: recover its source and include it.
  3. **screen_di has a one-render phase offset.** The +0C dest captured at the
     present-hook frame boundary is exactly one render step (~104 px scroll) off
     the value the draw actually used (snap[N].dest == drawn[N+2].dest). The
     extraction boundary must align with the draw, or `screen_di` lags by a frame.

Remaining for VERIFIED (enhanced_renderer_plan.md R2): include the missing fixed
slot (#2), align the extraction phase (#3), and the VRAM round-trip (needs the R3
rasterizer). CameraState (VIEW_TARGET) is OBSERVED.
"""
from __future__ import annotations

from overkill.recovered.domain.coords import i16
from overkill.recovered.domain.frame_snapshot import CameraState, FrameSnapshot, SpriteDraw
from overkill.recovered.ds_globals import VIEW_TARGET_X, VIEW_TARGET_Y
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    EFFECT_OBJECT_TABLE_COUNT,
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    OBJECT_SLOT_STRIDE,
    OFF_DRAW_SCRATCH_OR_DI,
    ObjectSlotView,
)

# The present pass writes the projected screen destination (a VRAM di) to the
# object record's +0C dest slot; this sentinel means the object is off-screen and
# the draw pass skips it (layer_sprites.OFFSCREEN_DESTINATION).
OFFSCREEN_DESTINATION = 0xFFFF

# The object tables walked for the draw list, in the present-scan order grounded
# by the probe: A90C scans DS:8D12 (gameplay) first, then DS:32CA (effect).
_OBJECT_TABLES = (
    (GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT),
    (EFFECT_OBJECT_TABLE_BASE, EFFECT_OBJECT_TABLE_COUNT),
)


def extract_frame_snapshot(mem, ds: int) -> FrameSnapshot:
    """Reconstruct the render-intent snapshot from the object tables + camera.

    A slot is on the draw list when it is active (record +00 non-zero) AND
    on-screen (its +0C dest slot != OFFSCREEN_DESTINATION). Coordinates are
    returned signed (world space); ``screen_di`` is the present pass's projected
    destination.
    """
    ds &= 0xFFFF
    sprites: list[SpriteDraw] = []
    for base, count in _OBJECT_TABLES:
        for index in range(count):
            slot = ObjectSlotView(mem, ds, (base + index * OBJECT_SLOT_STRIDE) & 0xFFFF)
            if slot.active_word == 0:
                continue
            screen_di = slot.u16(OFF_DRAW_SCRATCH_OR_DI)
            if screen_di == OFFSCREEN_DESTINATION:
                continue
            sprites.append(
                SpriteDraw(
                    sprite=slot.sprite_or_state,
                    x=i16(slot.x_word),
                    y=i16(slot.y_word),
                    layer=slot.draw_layer,
                    object_type=slot.object_type,
                    screen_di=screen_di,
                )
            )
    camera = CameraState(x=i16(mem.rw(ds, VIEW_TARGET_X)), y=i16(mem.rw(ds, VIEW_TARGET_Y)))
    return FrameSnapshot(camera=camera, sprites=tuple(sprites))
