"""Unit tests for the merged per-object collision-hit outcome (resolve_collision_hit).

Merges the two already-verified collision leaves (collision_damage_counter_chain_bf25 +
object_collision_death_transition_c037) the way the ASM chains them at BF25 -> BFC7 -> C037.
"""
from __future__ import annotations

import pytest

from overkill.recovered.systems.collision import resolve_collision_hit

BEDC_OTHER = 0x0002   # any BEDC != 0/1 adds no extra decrements (base count only)
BEDC_ONE = 0x0001     # +1 extra decrement
BEDC_ZERO = 0x0000    # +3 extra decrements
TYPE1, TYPE2 = 0x0001, 0x0002


def _hit(counter, bedc=BEDC_OTHER, object_type=TYPE1, logic_id=0x0042, enter_at_bf25=True):
    return resolve_collision_hit(counter_20=counter, bedc=bedc, object_type=object_type,
                                 logic_id=logic_id, enter_at_bf25=enter_at_bf25)


def test_survive_base_two_decrements():
    # BF25 entry with a neutral BEDC = exactly two decrements.
    out = _hit(10)
    assert (out.died, out.new_counter_20, out.death_transition) == (False, 8, None)


def test_death_on_second_decrement():
    out = _hit(2)
    assert out.died and out.new_counter_20 == 0
    assert out.death_transition is not None


def test_death_on_first_decrement():
    assert _hit(1).died and _hit(1).new_counter_20 == 0


def test_bedc_one_adds_one_decrement():
    assert _hit(4, bedc=BEDC_ONE).new_counter_20 == 1   # 3 decs -> survive
    assert _hit(3, bedc=BEDC_ONE).died                  # 3 decs -> dead


def test_bedc_zero_adds_three_decrements():
    assert _hit(6, bedc=BEDC_ZERO).new_counter_20 == 1  # 5 decs -> survive
    assert _hit(5, bedc=BEDC_ZERO).died                 # 5 decs -> dead


def test_variant2_entry_is_one_fewer_decrement():
    # The BF2D (variant-2 sprite) entry skips BF25's first decrement.
    assert _hit(1, enter_at_bf25=False).died            # 1 dec -> dead
    assert _hit(2, enter_at_bf25=False).new_counter_20 == 1  # 1 dec -> survive


def test_zero_counter_wraps_not_dies():
    # (0 - 1) & FFFF = FFFF, not 0 -- a 0 counter does not die on the decrement.
    out = _hit(0)
    assert out.died is False
    assert out.new_counter_20 == 0xFFFE  # two decrements from 0 -> FFFF -> FFFE


def test_death_transition_fields_and_sprite_by_type():
    out1 = _hit(1, object_type=TYPE1, logic_id=0x0042)
    t1 = out1.death_transition
    assert (t1.logic_id, t1.previous_logic_id, t1.transition_latch, t1.sprite_or_state) == (1, 0x0042, 0, 0)
    out2 = _hit(1, object_type=TYPE2, logic_id=0x0007)
    assert out2.death_transition.sprite_or_state == 3  # type 2 -> sprite 3


def test_survivor_has_no_death_transition_even_for_unverified_type():
    # No death -> the C037 leaf is never called, so an odd type does not raise.
    out = _hit(10, object_type=0x00FF)
    assert out.death_transition is None and out.died is False


def test_unverified_type_on_death_raises():
    # On death the C037 leaf is consulted; a non-1/2 type is the original's unverified path.
    with pytest.raises(ValueError):
        _hit(1, object_type=0x00FF)
