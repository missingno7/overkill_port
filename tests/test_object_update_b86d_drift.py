"""VM-free unit tests for the pure 1010:B86D fall-through (formation-drift) slot transform.

Pins ``object_update_b86d_drift``: X += -(vertical_delta), +1 more when DS:2328 == 0007h, and the
outgoing sprite from the delta sign.  The demo-level confirmation is the native object-update
coverage gate (``verify_native_object_update``) checking it byte-exact vs the VM at the BC4B handoff.
"""
from __future__ import annotations

from overkill.recovered.domain.object_behaviors import B86dDriftUpdate
from overkill.recovered.systems.objects import object_update_b86d_drift


def test_falling_delta_moves_left_and_uses_falling_sprite():
    # delta != FFFFh -> falling sprite 0076h; X += -delta.
    assert object_update_b86d_drift(0x0080, 0x0002, 0x0000) == B86dDriftUpdate(x_word=0x007E, sprite_or_state=0x0076)


def test_rising_delta_moves_right_one_and_uses_rising_sprite():
    # delta == FFFFh (one pixel up) -> rising sprite 0075h; X += -(-1) = +1.
    assert object_update_b86d_drift(0x0080, 0xFFFF, 0x0000) == B86dDriftUpdate(x_word=0x0081, sprite_or_state=0x0075)


def test_phase_word_0007_nudges_one_more_pixel():
    assert object_update_b86d_drift(0x0080, 0x0002, 0x0007).x_word == 0x007F  # 0x7E then +1
    # Any other phase value does not nudge.
    assert object_update_b86d_drift(0x0080, 0x0002, 0x0006).x_word == 0x007E


def test_x_wraps_16_bit():
    assert object_update_b86d_drift(0x0000, 0x0002, 0x0000).x_word == 0xFFFE
    assert object_update_b86d_drift(0xFFFF, 0xFFFF, 0x0007).x_word == 0x0001  # FFFF +1 = 0x10000 -> 0, +1 = 1
