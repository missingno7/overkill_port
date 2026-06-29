"""Bucket C: the first native OBJECT-UPDATE producer -- object_movement_step_ae09, the per-slot
movement half of the 1010:AE09 behavior (logic_id 0Ch), VM-free.

It composes two already-VERIFIED recovered systems -- the AE09 timer/step decision
(``object_logic_ae09``) and the AF22 3-pixel direction step (``step_operations_for_direction``) --
in the order the lifted behavior applies them.  Byte-exactness vs the real VM AE09 is separately
gated by overkill/probes/verify_native_object_update_ae09.py (L5_continue 777/777, L5_short 638/638,
0 divergence); this locks the composition (timer/direction/sprite + the optional x-=2 + the step
order) in a VM-free unit test."""
from __future__ import annotations

from overkill.recovered.domain.coords import i16, u16
from overkill.recovered.domain.tilemap import LevelTileContext, TileProbeInput
from overkill.recovered.systems.movement import step_operations_for_direction
from overkill.recovered.systems.objects import (
    AE09_SPRITE_OFFSET,
    object_bounds_tile_decision_ad60,
    object_movement_step_ae09,
    object_tile_probe_deactivates_ad60,
    object_update_ae09,
)
from overkill.recovered.systems.tilemap import compute_tile_probe_5073


def _stepped(x: int, y: int, direction: int) -> tuple[int, int]:
    for op in step_operations_for_direction(direction, 3):
        d = i16(op.delta_word)
        if op.axis == "x":
            x = u16(x + d)
        else:
            y = u16(y + d)
    return x, y


def test_ae09_timer_running_keeps_direction_no_pre_decrement():
    # substate 5 (running): decs to 4, direction kept (3), sprite = dir + 0x28, no x-=2, then steps.
    res = object_movement_step_ae09(5, 3, 0x0050, 0x0060)
    assert res.substate == 4
    assert res.direction_or_step == 3
    assert res.sprite_or_state == (3 + AE09_SPRITE_OFFSET)
    assert (res.x_word, res.y_word) == _stepped(0x0050, 0x0060, 3)


def test_ae09_timer_expiry_clears_direction_and_steps_left():
    # substate 1: decs to 0 -> direction cleared to 0, x -= 2 (decrement_x), then steps dir 0.
    res = object_movement_step_ae09(1, 3, 0x0050, 0x0060)
    assert res.substate == 0
    assert res.direction_or_step == 0
    assert res.sprite_or_state == (0 + AE09_SPRITE_OFFSET)
    assert (res.x_word, res.y_word) == _stepped(u16(0x0050 - 2), 0x0060, 0)


def test_ae09_timer_already_zero_keeps_direction_steps_left():
    # substate 0: no dec, direction kept (5), x -= 2 (decrement_x), then steps dir 5.
    res = object_movement_step_ae09(0, 5, 0x0050, 0x0060)
    assert res.substate == 0
    assert res.direction_or_step == 5
    assert res.sprite_or_state == (5 + AE09_SPRITE_OFFSET)
    assert (res.x_word, res.y_word) == _stepped(u16(0x0050 - 2), 0x0060, 5)


def test_ae09_x_wraps_16_bit_on_step():
    # A leftward step from a tiny X wraps mod 0x10000 (matches the 8086 word arithmetic).
    res = object_movement_step_ae09(5, 4, 0x0001, 0x0001)
    assert (res.x_word, res.y_word) == _stepped(0x0001, 0x0001, 4)
    assert 0 <= res.x_word <= 0xFFFF and 0 <= res.y_word <= 0xFFFF


# --- The WHOLE AE09 slot transform: movement + the AD60 bounds/tile -> active -----------------------
# Byte-exactness vs the VM is gated by verify_native_object_update_ae09.py (L5_continue 353/353,
# L5_short 342/342, 0 div, no skips -- the tile-probe path included).  These lock the active mapping.

def _empty_tiles(origin_x=0, row_base=0x0100, tile_plane=None, class_table=None) -> LevelTileContext:
    return LevelTileContext(
        origin_x_word=origin_x,
        row_base_word=row_base,
        tile_plane=tile_plane if tile_plane is not None else [0] * 0x10000,
        class_table=class_table if class_table is not None else tuple([0] * 256),
    )


def test_object_tile_probe_deactivates_ad60_class1_only():
    # 5073(origin=0,row=0x100, x=0x20,y=0x10) -> tile_offset 0xE7; +13 row stride -> 0xF4.
    tile_plane = [0] * 0x10000
    tile_plane[0xF4] = 0x42
    assert object_tile_probe_deactivates_ad60(
        0x20, 0x10, _empty_tiles(tile_plane=tile_plane, class_table=tuple(1 if i == 0x42 else 0 for i in range(256)))
    ) is True   # class 1 -> deactivate
    assert object_tile_probe_deactivates_ad60(
        0x20, 0x10, _empty_tiles(tile_plane=tile_plane, class_table=tuple(2 if i == 0x42 else 0 for i in range(256)))
    ) is False  # class 2 -> survive
    assert object_tile_probe_deactivates_ad60(
        0x20, 0x10, _empty_tiles(tile_plane=tile_plane)  # class table all 0
    ) is False  # class 0 -> survive


def test_object_update_ae09_skip_keeps_active():
    # draw_layer != 2 + in-bounds post-move -> AD60 "skip" -> active unchanged; movement == the step.
    move = object_movement_step_ae09(5, 3, 0x50, 0x50)
    assert object_bounds_tile_decision_ad60(move.x_word, move.y_word, 0x4, 0xC, tile_probe_suppressed=False).kind == "skip"
    res = object_update_ae09(5, 3, 0x50, 0x50, 0x0001, 0x4, 0xC, False, _empty_tiles())
    assert (res.substate, res.direction_or_step, res.sprite_or_state, res.x_word, res.y_word) == (
        move.substate, move.direction_or_step, move.sprite_or_state, move.x_word, move.y_word)
    assert res.active_word == 0x0001  # skip -> unchanged


def test_object_update_ae09_out_of_bounds_deactivates():
    # A post-move far past the right edge -> AD60 "deactivate" -> active = 0.
    move = object_movement_step_ae09(5, 3, 0x0200, 0x50)
    assert object_bounds_tile_decision_ad60(move.x_word, move.y_word, 0x4, 0xC, tile_probe_suppressed=False).kind == "deactivate"
    res = object_update_ae09(5, 3, 0x0200, 0x50, 0x0001, 0x4, 0xC, False, _empty_tiles())
    assert res.active_word == 0x0000  # deactivated
    assert (res.x_word, res.y_word) == (move.x_word, move.y_word)  # movement fields still set


def test_object_update_ae09_tile_probe_class1_deactivates():
    # draw_layer == 2 + tile-probe logic id + class-1 tile under the post-move -> active = 0.
    move = object_movement_step_ae09(5, 3, 0x50, 0x50)
    assert object_bounds_tile_decision_ad60(move.x_word, move.y_word, 0x2, 0xC, tile_probe_suppressed=False).kind == "tile_probe"
    probe = compute_tile_probe_5073(TileProbeInput(0, 0x100, move.x_word, move.y_word))
    offset = (probe.tile_offset_word + 13) & 0xFFFF
    tile_plane = [0] * 0x10000
    tile_plane[offset] = 0x55
    res = object_update_ae09(5, 3, 0x50, 0x50, 0x0001, 0x2, 0xC, False,
                             _empty_tiles(tile_plane=tile_plane, class_table=tuple(1 if i == 0x55 else 0 for i in range(256))))
    assert res.active_word == 0x0000  # tile class 1 -> deactivate
    res2 = object_update_ae09(5, 3, 0x50, 0x50, 0x0001, 0x2, 0xC, False,
                              _empty_tiles(tile_plane=tile_plane, class_table=tuple(2 if i == 0x55 else 0 for i in range(256))))
    assert res2.active_word == 0x0001  # tile class 2 -> survive
