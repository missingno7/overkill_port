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
  2. **The missing object is now included (RESOLVED).** A `sprite=0001 @layer 3`
     object is drawn FIRST (back-most) from the special slot one stride before the
     effect table (DS:237C, its x/y == the VIEW_TARGET globals). Added as the
     leading slot. The draw-list **content is now witnessed-exact**: the sprite
     multiset matches the real 5AC8 draws 6/6 render frames on the L5 demo.
  3. **screen_di phase = a boundary choice (RESOLVED).** Extracted at the present-
     hook boundary, +0C is one render step (~104 px) ahead of the draw. Extracted
     at the **draw boundary** (the first 5AC8 of a render burst), the snapshot's
     `(sprite, screen_di)` matches the witnessed draws EXACTLY (6/6 frames). So the
     runtime must extract at the draw-scan boundary (A846/A858), not the present
     hook; the extractor itself is correct.

Status: the draw list (**content + screen positions**) is **VERIFIED witnessed-
exact** against the live 5AC8 draws when extracted at the draw boundary. Remaining:
the VRAM round-trip (needs the R3 rasterizer) and CameraState/projection grounding
(for interpolation — the special slot's x/y already capture the view anchor).
"""
from __future__ import annotations

from overkill.recovered.domain.coords import i16
from overkill.recovered.domain.frame_snapshot import (
    BackgroundLayer,
    CameraState,
    FrameSnapshot,
    HudLayer,
    PlayfieldLayer,
    SpriteDraw,
)

# Background scroll globals (the 4E2F tile draw reads these).
BG_SCROLL_ROW = 0x2350     # vertical scroll into the level map
BG_COLUMN_INDEX = 0x2356   # starting map column (index into the DS:20D6 row table)
from overkill.recovered.ds_globals import VIEW_TARGET_X, VIEW_TARGET_Y
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    EFFECT_OBJECT_TABLE_COUNT,
    FRAME_TIMER_COUNT,
    FRAME_TIMER_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_BASE,
    SCORE_BCD_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    OBJECT_SLOT_STRIDE,
    OFF_DRAW_SCRATCH_OR_DI,
    ObjectSlotView,
)

# The present pass writes the projected screen destination (a VRAM di) to the
# object record's +0C dest slot; this sentinel means the object is off-screen and
# the draw pass skips it (layer_sprites.OFFSCREEN_DESTINATION).
OFFSCREEN_DESTINATION = 0xFFFF

# A single special object slot sits one stride before the effect table; the live
# witness (witness_draw_order) shows it drawn FIRST (back-most). Its x/y fields
# (+02/+04) are the VIEW_TARGET globals (237E/2380), so it is the view/camera
# anchor object (sprite 1, layer 3).
SPECIAL_DRAW_SLOT_BASE = (EFFECT_OBJECT_TABLE_BASE - OBJECT_SLOT_STRIDE) & 0xFFFF  # 0x237C

# The object tables walked for the draw list, in the witnessed draw order: the
# special slot first, then the present-scan order (DS:8D12 gameplay, DS:32CA effect).
_OBJECT_TABLES = (
    (SPECIAL_DRAW_SLOT_BASE, 1),
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
    playfield = PlayfieldLayer(camera=camera, sprites=tuple(sprites))

    # HUD: the six status-counter cells the 61DC status display draws (DS:2368..2372)
    # plus the packed-decimal score (DS:2314 low, DS:2316 high).
    hud = HudLayer(
        counters=tuple(
            mem.rw(ds, (FRAME_TIMER_TABLE_BASE + 2 * i) & 0xFFFF) for i in range(FRAME_TIMER_COUNT)
        ),
        score_bcd=(mem.rw(ds, SCORE_BCD_BASE), mem.rw(ds, (SCORE_BCD_BASE + 2) & 0xFFFF)),
    )
    # Background: the scrolling level tilemap's camera position.
    background = BackgroundLayer(
        scroll_row=mem.rw(ds, BG_SCROLL_ROW),
        column_index=mem.rw(ds, BG_COLUMN_INDEX),
    )
    return FrameSnapshot(background=background, playfield=playfield, hud=hud)
