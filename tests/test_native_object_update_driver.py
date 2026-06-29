"""VM-free unit tests for the native object-update driver (pillar 2 skeleton).

Pins ``native_object_update_pool``: it advances active slots whose logic_id has a native handler
(via the verified pure systems) and leaves every other slot untouched -- the VM-free pool walk the
native runtime uses.  The handlers themselves are proven byte-exact vs the VM by the coverage gate;
this pins the driver's walk/dispatch/write-back wiring.
"""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.object_update import native_object_update_pool
from overkill.recovered.systems.objects import object_update_aed8

_STRIDE_WORDS = 0x38 >> 1


def _slot(**fields: int) -> tuple:
    """Build a stride-0x38 slot record (28 words) with the named fields at their record offsets."""
    words = [0] * _STRIDE_WORDS
    for name, offset in (
        ("active", 0x00), ("x", 0x02), ("y", 0x04), ("direction", 0x06), ("sprite", 0x08),
        ("draw_layer", 0x16), ("logic_id", 0x18), ("substate", 0x1C), ("substate_1e", 0x1E),
    ):
        if name in fields:
            words[offset >> 1] = fields[name] & 0xFFFF
    return tuple(words)


def _globals() -> ObjectUpdateGlobals:
    tiles = LevelTileContext(origin_x_word=0, row_base_word=0, tile_plane=bytes(1), class_table=tuple([0] * 256))
    return ObjectUpdateGlobals(ref_box_x=0x58, ref_box_y=0x50, a278=0x04, tile_probe_suppressed=True, tiles=tiles)


def test_advances_native_slot_leaves_others_and_inactive():
    g = _globals()
    aed8 = _slot(active=1, logic_id=0x02, substate=5, direction=4, x=0x50, y=0x50, substate_1e=1, draw_layer=0)
    other = _slot(active=1, logic_id=0x0099, x=0x30, y=0x30)       # no native handler -> untouched
    inactive = _slot(active=0, logic_id=0x02, x=0x70)              # inactive -> skipped
    pool = ObjectPool(base=0x2B5C, stride=0x38, slots=(aed8, other, inactive))

    out = native_object_update_pool(pool, g)

    # The AED8 slot advanced exactly as its pure system says (driver wires it correctly).
    exp = object_update_aed8(5, 4, 0x50, 0x50, 1, 1, 0, 0x02, 0x58, 0x50, 0x04, True, g.tiles)
    assert (out.substate(0), out.x_word(0), out.y_word(0), out.active_word(0)) == (
        exp.substate, exp.x_word, exp.y_word, exp.active_word
    )
    assert out.direction_word(0) == 4 and out.sprite_word(0) == 0  # AED8 leaves direction + sprite
    # Non-native and inactive slots are untouched.
    assert out.logic_id(1) == 0x0099 and out.x_word(1) == 0x30
    assert out.active_word(2) == 0 and out.x_word(2) == 0x70


def test_empty_dispatch_is_identity():
    g = _globals()
    pool = ObjectPool(base=0x2B5C, stride=0x38, slots=(_slot(active=1, logic_id=0x02, x=0x40),))
    out = native_object_update_pool(pool, g, handlers={})
    assert out.x_word(0) == 0x40  # no handlers -> nothing advances
