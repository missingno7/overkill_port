"""VM-free unit tests for the pure 1010:B2CD handler (EFAE logic_id 0x12) -- the dominant boss object.

Pins ``b2cd_sprite_offset`` (the level/BDAC/scroll sprite table) and ``object_update_b2cd``'s waypoint
advance-loop cap -> None path.  Full byte-exact confirmation (incl. the reached-waypoint advance loop and
the BC4B contact death) is the coverage gate + in-place pass vs the VM (1410/1410 on L6_boss, 0 fail).
"""
from __future__ import annotations

from overkill.recovered.systems.objects import b2cd_sprite_offset, object_update_b2cd

_BLOCKED = (0xFF,) * 16  # 5DB2 direction table that blocks the seek


def test_sprite_offset_bdac_override():
    assert b2cd_sprite_offset(direction=4, bdac=1, level=5, scroll=0) == 4 + 0x3B


def test_sprite_offset_by_level():
    assert b2cd_sprite_offset(4, 0, 5, 0) == 4 + 0x115   # level 5 (L6)
    assert b2cd_sprite_offset(4, 0, 0, 0) == 4 + 0x115
    assert b2cd_sprite_offset(4, 0, 1, 0) == 4 + 0x2A    # level 1 (L2)
    assert b2cd_sprite_offset(4, 0, 2, 0) == 4 + 0xD2    # level 2 (L3)
    assert b2cd_sprite_offset(4, 0, 3, 0) == 4 + 0xEC
    assert b2cd_sprite_offset(4, 0, 4, 0) == 4 + 0xEC


def test_sprite_offset_scroll_special():
    assert b2cd_sprite_offset(4, 0, 0, 0xE52) == 4 + 0x105   # levels 0/6 + scroll 0xE52
    assert b2cd_sprite_offset(4, 0, 6, 0xE52) == 4 + 0x105
    assert b2cd_sprite_offset(4, 0, 5, 0xE52) is None        # level 5 + 0xE52 -> unmapped fall-through


def test_all_blocked_seek_walks_to_cap_returns_none():
    # An all-FFh direction table blocks every seek, so the reached-waypoint advance loop walks every
    # waypoint and reaches its safety cap -> None (the VM relies on an eventually-unreached waypoint; a
    # degenerate all-blocked list has none).  ``read_waypoint_word`` returns a constant waypoint here.
    assert object_update_b2cd(
        slot_x=0x50, slot_y=0x50, slot_direction=4,
        waypoint_ptr=0x1000, read_waypoint_word=lambda off: 0x50,
        direction_table=_BLOCKED, bdac=0, level=5, scroll=0,
    ) is None
