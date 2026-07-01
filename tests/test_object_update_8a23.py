"""Unit tests for object_update_8a23 (logic_id 0x39 -- sprite 6Eh; still (X<80h signed) / stepping mover)."""
from __future__ import annotations

from overkill.recovered.systems.objects import OBJECT_8A23_SPRITE, object_update_8a23


def test_still_when_x_below_80():
    # X < 80h -> still: sprite 6Eh, direction/x/y unchanged
    assert object_update_8a23(0x0040, 0x0050, 0x0003) == (OBJECT_8A23_SPRITE, 0x0003, 0x0040, 0x0050)


def test_negative_x_is_still_signed_compare():
    # X = FFF0h (= -16 signed) -> still (the JL is signed); dir/y untouched (the fixed 16-fail case)
    assert object_update_8a23(0xFFF0, 0x0000, 0x0004) == (OBJECT_8A23_SPRITE, 0x0004, 0xFFF0, 0x0000)


def test_moving_steps_direction_2_down():
    # X >= 80h -> face direction 2 and step the AF60 mode-2 move (2px x 2 = y += 4)
    sprite, direction, x, y = object_update_8a23(0x0100, 0x0050, 0x0000)
    assert sprite == OBJECT_8A23_SPRITE and direction == 0x0002
    assert (x, y) == (0x0100, 0x0054)          # x unchanged, y += 4 (down)


def test_moving_y_over_c0_dies():
    # stepped Y > C0h routes to the BFC7 death (None, left to the VM)
    assert object_update_8a23(0x0100, 0x00C0, 0x0000) is None   # 0xC0 + 4 = 0xC4 > 0xC0
    # 0xBA + 4 = 0xBE, not over C0h -> survives
    assert object_update_8a23(0x0100, 0x00BA, 0x0000) == (OBJECT_8A23_SPRITE, 0x0002, 0x0100, 0x00BE)
