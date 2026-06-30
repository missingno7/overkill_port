"""VM-free unit tests for the pure 1010:AE2C handler (EFAE logic_id 0x06) -- AE7D's sibling mover.

Pins ``object_update_ae2c``: y==0xC8 death, X-=4, the tile-gated down-step (direction 1 / Y+=4 unless the
Y mod 16 == 8 probe tile has class 1), and sprite = ((DS:2326<<2)&8) + direction + 8.  Full byte-exact
confirmation is the coverage gate vs the VM (134/140 on L6_boss, 0 fail).
"""
from __future__ import annotations

from overkill.recovered.domain.object_behaviors import Ae2cSlotUpdate
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.objects import object_update_ae2c


def _tiles(class1_at_67: bool) -> LevelTileContext:
    plane = bytearray(0x10000)
    if class1_at_67:
        plane[67] = 5
    class_table = [0] * 256
    class_table[5] = 1
    # 5073(origin 0, row_base 100, x 0x4C, y 0x58) -> offset 53; +0xE -> 67.
    return LevelTileContext(origin_x_word=0, row_base_word=100,
                            tile_plane=bytes(plane), class_table=tuple(class_table))


def test_death_at_y_c8():
    assert object_update_ae2c(0x50, 0xC8, 1, 0, 4, 0, True, _tiles(False)) is None


def test_suppressed_down_step():
    # BDAC suppressed -> no probe -> down-step (dir 1, Y+=4), sprite 9; draw_layer 0 -> active kept.
    assert object_update_ae2c(0x50, 0x58, 1, 0, 4, 0, True, _tiles(False)) == Ae2cSlotUpdate(1, 9, 0x50, 0x5C, 1)


def test_tile_gated_direction_zero():
    # Y mod 16 == 8, not suppressed, probe tile class 1 -> direction 0, no Y move, sprite 8.
    assert object_update_ae2c(0x50, 0x58, 1, 0, 4, 0, False, _tiles(True)) == Ae2cSlotUpdate(0, 8, 0x50, 0x58, 1)


def test_anim_bit_in_sprite():
    # DS:2326 bit 1 -> ((2<<2)&8)=8 added: sprite = 8 + direction(1) + 8 = 0x11.
    assert object_update_ae2c(0x50, 0x50, 1, 0, 4, 2, True, _tiles(False)) == Ae2cSlotUpdate(1, 0x11, 0x50, 0x54, 1)
