"""VM-free unit tests for the pure 1010:5E1B object-delta helper.

Pins ``object_delta_5e1b``: per-axis ``delta = slot - (target + pad)`` with pad 4px when the target
is solid (scan flag +14 == 1) else 12px.  These deltas are what ``object_delta_steer_5e42`` consumes;
the demo-level confirmation is the B86D edge-steer composition in the native object-update coverage gate.
"""
from __future__ import annotations

from overkill.recovered.domain.movement import ObjectDelta5e1b
from overkill.recovered.systems.movement import object_delta_5e1b


def test_solid_target_uses_4px_pad():
    # scan_flag == 1 -> pad 4: delta = slot - (target + 4)
    assert object_delta_5e1b(0x0080, 0x0050, 0x0040, 0x0030, 0x0001) == ObjectDelta5e1b(
        move_delta_x=0x003C, move_delta_y=0x001C
    )


def test_nonsolid_target_uses_12px_pad():
    # scan_flag != 1 -> pad 0x0C
    assert object_delta_5e1b(0x0080, 0x0050, 0x0040, 0x0030, 0x0000) == ObjectDelta5e1b(
        move_delta_x=0x0034, move_delta_y=0x0014
    )


def test_negative_delta_wraps_16_bit_signed():
    # slot left/above the padded target -> negative (16-bit two's complement) deltas.
    out = object_delta_5e1b(0x0000, 0x0000, 0x0010, 0x0020, 0x0001)
    assert out.move_delta_x == 0xFFEC  # -(0x10+4) = -0x14
    assert out.move_delta_y == 0xFFDC  # -(0x20+4) = -0x24


def test_same_pad_for_both_axes():
    # The pad is computed once from the target's scan flag and applied to both axes.
    out = object_delta_5e1b(0x0100, 0x0100, 0x0000, 0x0000, 0x0005)  # non-solid -> pad 0x0C
    assert out.move_delta_x == 0x00F4 and out.move_delta_y == 0x00F4
