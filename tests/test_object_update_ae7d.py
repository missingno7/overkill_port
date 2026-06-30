"""VM-free unit tests for the pure 1010:AE7D handler (EFAE logic_id 0x05) -- a scroll-left mover.

Pins ``object_update_ae7d``: y==0 death, the X-=4 move, the tile-gated up-step (direction 7 / Y-=4 unless
the probe tile has class 1), and the sprite = direction + 8.  Full byte-exact confirmation is the coverage
gate vs the VM (129/132 on L6_boss, 0 fail).
"""
from __future__ import annotations

from overkill.recovered.domain.object_behaviors import Ae7dSlotUpdate
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.objects import object_update_ae7d


def _tiles(class1_at_65: bool) -> LevelTileContext:
    plane = bytearray(0x10000)
    if class1_at_65:
        plane[65] = 5
    class_table = [0] * 256
    class_table[5] = 1
    # 5073(origin 0, row_base 100, x 0x4C, y 0x50) -> offset 53; +0xC -> 65.
    return LevelTileContext(origin_x_word=0, row_base_word=100,
                            tile_plane=bytes(plane), class_table=tuple(class_table))


def test_death_at_y_zero():
    assert object_update_ae7d(0x50, 0, 1, 0, 4, True, _tiles(False)) is None


def test_suppressed_up_step():
    # BDAC suppressed -> no direction probe -> up-step (dir 7, Y-=4), sprite 15; draw_layer 0 -> active kept.
    assert object_update_ae7d(0x50, 0x50, 1, 0, 4, True, _tiles(False)) == Ae7dSlotUpdate(7, 15, 0x50, 0x4C, 1)


def test_not_aligned_up_step():
    # Y not 16px-aligned -> no probe -> up-step.
    r = object_update_ae7d(0x50, 0x51, 1, 0, 4, False, _tiles(True))
    assert r.direction_or_step == 7 and r.y_word == 0x4D


def test_tile_gated_direction_zero():
    # Aligned + not suppressed + the probed tile has class 1 -> direction 0, no Y move, sprite 8.
    assert object_update_ae7d(0x50, 0x50, 1, 0, 4, False, _tiles(True)) == Ae7dSlotUpdate(0, 8, 0x50, 0x50, 1)
