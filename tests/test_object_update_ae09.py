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
from overkill.recovered.systems.movement import step_operations_for_direction
from overkill.recovered.systems.objects import AE09_SPRITE_OFFSET, object_movement_step_ae09


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
