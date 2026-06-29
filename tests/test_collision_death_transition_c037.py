"""VM-free unit tests for the pure BFC7/C037 collision-death slot transition.

Pins the four field values the 1010:BFC7 death tail stamps when a type-1/2 object dies by
collision (``object_collision_death_transition_c037``): the old logic id saved as
``previous_logic_id``, the forced dying state ``logic_id=1``, the cleared ``transition_latch``,
and the C037 death sprite by type (1 -> 0, 2 -> 3).  Other types are an unverified C037 table
entry and must fail loud.
"""
from __future__ import annotations

import pytest

from overkill.recovered.domain.collision import CollisionDeathTransition
from overkill.recovered.systems.collision import object_collision_death_transition_c037


def test_c037_transition_type_1():
    assert object_collision_death_transition_c037(0x0082, 0x0001) == CollisionDeathTransition(
        previous_logic_id=0x0082, logic_id=0x0001, transition_latch=0x0000, sprite_or_state=0x0000,
    )


def test_c037_transition_type_2():
    assert object_collision_death_transition_c037(0x0048, 0x0002) == CollisionDeathTransition(
        previous_logic_id=0x0048, logic_id=0x0001, transition_latch=0x0000, sprite_or_state=0x0003,
    )


def test_c037_transition_preserves_old_logic_id():
    # previous_logic_id is exactly the incoming logic id (masked to 16 bits).
    assert object_collision_death_transition_c037(0x1234, 0x0001).previous_logic_id == 0x1234
    assert object_collision_death_transition_c037(0x1_0086, 0x0002).previous_logic_id == 0x0086


def test_c037_transition_unknown_type_fails_loud():
    with pytest.raises(ValueError):
        object_collision_death_transition_c037(0x0010, 0x0003)
