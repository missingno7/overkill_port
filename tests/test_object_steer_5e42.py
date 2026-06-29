"""Bucket C: the native delta-steer producer -- object_delta_steer_5e42, the whole runtime-patched
1010:5E42 (the 3rd object-update movement primitive, used by b24d/b86d), VM-free.

It converts signed Y/X deltas into a direction via a Bresenham axis pick against the move_step_error
accumulator + the DS:A348 table, then steps x/y (composing the recovered step_operations_for_direction).
Byte-exactness vs the real VM 5E42 is separately gated by overkill/probes/verify_native_object_steer_5e42.py
(L2 64/64, L6_boss 121/121, 0 divergence); this locks the Bresenham branches, the sign bits, the
blocked sentinel, and the step-mode dispatch in a VM-free unit test."""
from __future__ import annotations

from overkill.recovered.domain.coords import i16, u16
from overkill.recovered.systems.movement import object_delta_steer_5e42, step_operations_for_direction


def _table(**bit_to_dir: int) -> tuple[int, ...]:
    # default every direction-bit entry to FFh (blocked); kwargs like b2=4 set table[2] = 4.
    t = [0xFF] * 16
    for key, value in bit_to_dir.items():
        t[int(key[1:])] = value
    return tuple(t)


def _stepped(x: int, y: int, direction: int, pixels: int) -> tuple[int, int]:
    for op in step_operations_for_direction(direction, pixels):
        d = i16(op.delta_word)
        if op.axis == "x":
            x = u16(x + d)
        else:
            y = u16(y + d)
    return x, y


def test_5e42_y_major_minor_no_step():
    # dy=5 (y_bit 2), dx=3 (x_bit 8); |dy|>|dx| -> err += 3; 3 <= |dy|(5) -> y only -> bits 2.
    res = object_delta_steer_5e42(0x50, 0x50, 0x07, 5, 3, 0, 0, _table(b2=4))
    assert not res.blocked
    assert res.direction_or_step == 4
    assert res.move_step_error == 3  # 0 + |dx|; not > |dy|, so no subtract
    assert (res.x_word, res.y_word) == _stepped(0x50, 0x50, 4, 2)


def test_5e42_y_major_both_step_subtracts():
    # dy=5, dx=3, err_in=4 -> err += 3 = 7; 7 > |dy|(5) -> err -= 5 = 2; both axes -> bits 2|8 = 0xA.
    res = object_delta_steer_5e42(0x50, 0x50, 0x07, 5, 3, 4, 0, _table(b10=6))
    assert res.direction_or_step == 6
    assert res.move_step_error == 2


def test_5e42_equal_magnitudes_step_both_no_accumulator_change():
    # dy=4, dx=4 -> ady==adx -> bits 2|8 = 0xA; accumulator unchanged.
    res = object_delta_steer_5e42(0x50, 0x50, 0x07, 4, 4, 9, 0, _table(b10=1))
    assert res.direction_or_step == 1
    assert res.move_step_error == 9  # unchanged in the equal branch


def test_5e42_negative_deltas_set_neg_bits():
    # dy=-5 (0xFFFB -> y_bit 1, |dy|=5), dx=-3 (0xFFFD -> x_bit 4, |dx|=3); y major, y only -> bits 1.
    res = object_delta_steer_5e42(0x50, 0x50, 0x07, 0xFFFB, 0xFFFD, 0, 0, _table(b1=2))
    assert res.direction_or_step == 2
    assert res.move_step_error == 3


def test_5e42_blocked_leaves_direction_and_xy_but_advances_accumulator():
    # Every direction-bit -> FFh: blocked.  Direction + x/y untouched; accumulator still advanced.
    res = object_delta_steer_5e42(0x50, 0x60, 0x07, 5, 3, 0, 0, tuple([0xFF] * 16))
    assert res.blocked
    assert res.direction_or_step == 0x07          # unchanged
    assert (res.x_word, res.y_word) == (0x50, 0x60)  # unchanged
    assert res.move_step_error == 3                # err += |dx|, still advanced


def test_5e42_fast_step_mode_uses_3px():
    res = object_delta_steer_5e42(0x50, 0x50, 0x07, 5, 3, 0, 3, _table(b2=4))  # DS:2312 == 3 -> 3px
    assert (res.x_word, res.y_word) == _stepped(0x50, 0x50, 4, 3)
