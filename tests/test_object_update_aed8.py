"""VM-free unit tests for the pure 1010:AED8 whole-slot transform (EFAE logic_id 2).

Pins ``object_update_aed8``: substate timer + AEE4 8px step + B250 contact selection
(``overlap_contact_box_contains`` / +1E skip) + the AD60 bounds tail (AD5A adds DS:A278, ADC9 sets
X=FFFFh).  Full byte-exact confirmation is the native object-update coverage gate vs the VM.
"""
from __future__ import annotations

from overkill.recovered.domain.object_behaviors import Aed8SlotUpdate
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.objects import object_update_aed8

# A dummy tile context: the bounds/skip branches below never sample it.
_TILES = LevelTileContext(origin_x_word=0, row_base_word=0, tile_plane=bytes(1), class_table=tuple([0] * 256))


def _call(**kw):
    base = dict(
        substate=5, direction_or_step=4, x_word=0x50, y_word=0x50, active_word=1,
        substate_1e=0, draw_layer=0, logic_id=0, ref_box_x=0x58, ref_box_y=0x50, a278=0x04,
        tile_probe_suppressed=True, tiles=_TILES,
    )
    base.update(kw)
    return object_update_aed8(**base)


def test_timer_expired_returns_none():
    assert _call(substate=1) is None  # decrements to 0 -> unverified ADC9 death path


def test_out_of_range_direction_returns_none():
    assert _call(direction_or_step=8) is None  # AEE4 table is 0..7


def test_contact_path_sets_x_ffff_and_deactivates():
    # substate_1e != 1 and the dir-4 stepped pos (0x58,0x50) is inside the ref box -> ADC9 -> X=FFFF,
    # which is out of play bounds -> AD60 deactivates.
    assert _call(substate_1e=0) == Aed8SlotUpdate(substate=4, x_word=0xFFFF, y_word=0x50, active_word=0)


def test_no_contact_skip_overlap_adds_a278_and_survives():
    # +1E == 1 skips the overlap test -> AD5A: X = stepped(0x58) + a278(0x04) = 0x5C, in bounds,
    # draw_layer 0 is not the tile-probe family -> skip -> active unchanged.
    assert _call(substate_1e=0x0001) == Aed8SlotUpdate(substate=4, x_word=0x005C, y_word=0x50, active_word=1)


def test_no_contact_when_outside_box_even_if_not_skipped():
    # +1E != 1 but the stepped pos is outside the ref box -> no contact -> AD5A (X += a278).
    assert _call(substate_1e=0, ref_box_x=0x00, ref_box_y=0x00).x_word == 0x005C
