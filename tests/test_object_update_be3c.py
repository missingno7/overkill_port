"""VM-free unit tests for the pure 1010:BE3C animation handler (EFAE logic_id 0x01).

Pins ``object_update_be3c``: the DS:2324 gate + the CS:BE54 state dispatch.  Full byte-exact
confirmation is the native object-update coverage gate vs the VM (279/296 L2, 0 fail).
"""
from __future__ import annotations

from overkill.recovered.systems.objects import object_update_be3c


def test_gate_off_leaves_sprite_unchanged():
    # DS:2324 != 1 -> straight to BC45, the slot (sprite) is untouched.
    assert object_update_be3c(animate_gate=0, state=1, anim_counter=5, sprite_or_state=0x77) == 0x77


def test_state0_leaves_sprite_unchanged():
    # gate on but state 0 -> the jump table routes to BC45, unchanged.
    assert object_update_be3c(animate_gate=1, state=0, anim_counter=5, sprite_or_state=0x77) == 0x77


def test_state1_sets_sprite_to_inc_counter():
    # state 1 (BE5A): sprite = the inc'd frame counter (5 -> 6).
    assert object_update_be3c(animate_gate=1, state=1, anim_counter=5, sprite_or_state=0x77) == 6


def test_state1_morph_at_counter_9_returns_none():
    # inc'd counter == 9 -> the morph transition (logic-id change), not modelled.
    assert object_update_be3c(animate_gate=1, state=1, anim_counter=8, sprite_or_state=0x77) is None


def test_states_2_and_3_return_none():
    assert object_update_be3c(animate_gate=1, state=2, anim_counter=5, sprite_or_state=0x77) is None
    assert object_update_be3c(animate_gate=1, state=3, anim_counter=5, sprite_or_state=0x77) is None
