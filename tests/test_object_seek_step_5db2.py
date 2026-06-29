"""Bucket C: the SHARED native object-update movement producer -- object_target_seek_step_5db2, the
whole 1010:5DB2 target-seek (direction toward target + the 5E0C mode-dispatched step), VM-free.

It composes two already-VERIFIED recovered systems -- the 5DB2 direction decision
(``choose_target_seek_direction``) and the 8-way step (``step_operations_for_direction``) -- with the
recovered 5E0C mode table.  Byte-exactness vs the real VM 5DB2 is separately gated by
overkill/probes/verify_native_object_seek_step_5db2.py (L2 1257/1257, L6_boss 1957/1957,
player_death 1721/1721, 0 divergence); this locks the mode dispatch + blocked branch + step
composition in a VM-free unit test."""
from __future__ import annotations

import pytest

from overkill.recovered.domain.coords import i16, u16
from overkill.recovered.domain.movement import MovementTarget
from overkill.recovered.systems.movement import (
    MOVEMENT_MODE_STEP_5E0C,
    object_target_seek_step_5db2,
    step_operations_for_direction,
)

# slot (0x50, 0x50) vs target (y=0x40, x=0x60): the 5DB2 direction bits are 6
# (y > target_y -> 2, signed x < target_x -> +4); table[6] picks the direction.
_TARGET = MovementTarget(y_word=0x0040, x_word=0x0060)


def _table_to(direction_at_6: int) -> tuple[int, ...]:
    return tuple(direction_at_6 if i == 6 else 0 for i in range(16))


def _stepped(x: int, y: int, direction: int, pixels: int, repeat: int) -> tuple[int, int]:
    for _ in range(repeat):
        for op in step_operations_for_direction(direction, pixels):
            d = i16(op.delta_word)
            if op.axis == "x":
                x = u16(x + d)
            else:
                y = u16(y + d)
    return x, y


def test_5e0c_mode_step_table_recovered():
    # mode 1 -> AF63 (one 2px step), 2 -> AF60 (two 2px steps), 3 -> AEE4 (one 8px step).
    assert MOVEMENT_MODE_STEP_5E0C == {1: (2, 1), 2: (2, 2), 3: (8, 1)}


def test_5db2_seek_mode1_one_2px_step():
    res = object_target_seek_step_5db2(0x50, 0x50, 0x0007, _TARGET, 1, _table_to(3))
    assert not res.blocked
    assert res.direction_or_step == 3  # table[6]
    assert (res.x_word, res.y_word) == _stepped(0x50, 0x50, 3, 2, 1)


def test_5db2_seek_mode2_double_2px_step():
    res = object_target_seek_step_5db2(0x50, 0x50, 0x0007, _TARGET, 2, _table_to(3))
    assert res.direction_or_step == 3
    assert (res.x_word, res.y_word) == _stepped(0x50, 0x50, 3, 2, 2)  # AF60 self-call double


def test_5db2_seek_mode3_one_8px_step():
    res = object_target_seek_step_5db2(0x50, 0x50, 0x0007, _TARGET, 3, _table_to(5))
    assert res.direction_or_step == 5
    assert (res.x_word, res.y_word) == _stepped(0x50, 0x50, 5, 8, 1)


def test_5db2_blocked_leaves_slot_untouched():
    # table[6] == FFh -> the seek is blocked; 5DB2 returns before touching the slot.
    res = object_target_seek_step_5db2(0x50, 0x50, 0x0007, _TARGET, 2, _table_to(0xFF))
    assert res.blocked
    assert (res.direction_or_step, res.x_word, res.y_word) == (0x0007, 0x50, 0x50)


def test_5db2_unverified_mode_raises():
    # mode 0 (AFA2) and modes >= 4 are outside the verified 5E0C set -> fail loud.
    with pytest.raises(ValueError):
        object_target_seek_step_5db2(0x50, 0x50, 0x0007, _TARGET, 0, _table_to(3))
