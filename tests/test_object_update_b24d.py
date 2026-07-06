"""VM-free unit tests for the pure 1010:B24D whole-slot transform (EFAE logic_id 0x0B).

Pins ``object_update_b24d``: 5E42 delta-steer + B250 contact selection (``overlap_contact_box_contains``
/ +1E skip) + the AD60 bounds tail (AD5A adds DS:A278, ADC9 sets X=FFFFh).  The steer itself is pinned by
the movement tests + the live object-update coverage gate; these use a blocked steer (direction table all
FFh -> x/y/direction untouched) to isolate B24D's contact/bounds composition.
"""
from __future__ import annotations

from overkill.recovered.domain.object_behaviors import B24dSlotUpdate
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.objects import object_update_b24d

_TILES = LevelTileContext(origin_x_word=0, row_base_word=0, tile_plane=bytes(1), class_table=tuple([0] * 256))
_BLOCKED = (0xFF,) * 16  # 5E42 direction table that blocks the steer -> x/y/direction unchanged


def _call(**kw):
    base = dict(
        x_word=0x50, y_word=0x50, direction_or_step=4, active_word=1, substate_1e=0,
        move_delta_x=0, move_delta_y=0, move_step_error=0, step_mode=0, direction_table=_BLOCKED,
        hazard_class=0, logic_id=0x0B, ref_box_x=0x52, ref_box_y=0x50, a278=0x04,
        tile_probe_suppressed=True, tiles=_TILES,
    )
    base.update(kw)
    return object_update_b24d(**base)


def test_contact_sets_x_ffff_and_deactivates():
    # +1E != 1 and the (blocked) pos (0x50,0x50) is inside the ref box -> ADC9 -> X=FFFF, which is out of
    # play bounds -> AD60 deactivates.
    r = _call(substate_1e=0)
    assert r.x_word == 0xFFFF and r.active_word == 0 and r.y_word == 0x50


def test_skip_overlap_adds_a278_and_survives():
    # +1E == 1 skips the overlap test -> AD5A: X = 0x50 + a278(0x04) = 0x54, in bounds, logic 0x0B is not
    # a tile-probe family -> skip -> active unchanged; the blocked steer leaves direction at 4.
    assert _call(substate_1e=0x0001) == B24dSlotUpdate(
        direction_or_step=4, x_word=0x0054, y_word=0x50, active_word=1, move_step_error=0,
        contact=False,
    )


def test_no_contact_when_outside_box():
    # +1E != 1 but the pos is outside the ref box -> no contact -> AD5A (X += a278).
    assert _call(substate_1e=0, ref_box_x=0x00, ref_box_y=0x00).x_word == 0x0054


def test_out_of_bounds_deactivates():
    # X past the play-field max (0xE0) after AD5A -> AD60 deactivates.
    assert _call(substate_1e=1, x_word=0xF0).active_word == 0
