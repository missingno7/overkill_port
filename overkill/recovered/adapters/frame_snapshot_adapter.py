"""Bridge: extract a semantic :class:`FrameSnapshot` from live VM memory.

Reads the original object tables + camera globals through memory views and
reconstructs the render-intent snapshot the enhanced renderer/interpolator
consume. This is the one place VM memory meets the render dataclasses.

**Status: OBSERVED hypothesis — known to need correction.** The draw list here is
"every active object slot" in the effect + gameplay tables. The *faithful* render
list is NOT that: `run_present_object_scan_pair_a90c` (layer_sprites.py) shows the
present scan walks two **presence lists** — `DS:8D12` (34 entries, scanned by the
A90F hook) and `DS:32CA` (36 entries, scanned by A927) — populated by the 4CED
presence-stamp and dispatched per-object via 5A92. So the grounded draw list must
read those presence lists (entry format TBD: object pointer + screen position),
not iterate the object tables.

Grounding step (enhanced_renderer_plan.md R2): recover the 8D12/32CA presence-list
entry format and the A90F/A927 scan, then prove the snapshot's draw list matches
the present scan + a VRAM round-trip over the demo corpus. Until then this
extractor is a scaffold, not the render contract.
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
    ObjectSlotView,
)

# The object tables walked for the draw list (effect slots first, then gameplay).
_OBJECT_TABLES = (
    (EFFECT_OBJECT_TABLE_BASE, EFFECT_OBJECT_TABLE_COUNT),
    (GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT),
)


def extract_frame_snapshot(mem, ds: int) -> FrameSnapshot:
    """Reconstruct the render-intent snapshot from the object tables + camera.

    A slot is on the draw list when its ``active_word`` (record +00) is non-zero.
    Coordinates are returned signed (world space).
    """
    ds &= 0xFFFF
    sprites: list[SpriteDraw] = []
    for base, count in _OBJECT_TABLES:
        for index in range(count):
            slot = ObjectSlotView(mem, ds, (base + index * OBJECT_SLOT_STRIDE) & 0xFFFF)
            if slot.active_word == 0:
                continue
            sprites.append(
                SpriteDraw(
                    sprite=slot.sprite_or_state,
                    x=i16(slot.x_word),
                    y=i16(slot.y_word),
                    layer=slot.draw_layer,
                    object_type=slot.object_type,
                )
            )
    camera = CameraState(x=i16(mem.rw(ds, VIEW_TARGET_X)), y=i16(mem.rw(ds, VIEW_TARGET_Y)))
    return FrameSnapshot(camera=camera, sprites=tuple(sprites))
