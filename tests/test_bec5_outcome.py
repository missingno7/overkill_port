"""Unit tests for the BEC5 moving-object reaction outcome (bec5_moving_object_outcome)."""
from __future__ import annotations

import pytest

from overkill.recovered.systems.collision import bec5_candidate_deactivated, bec5_moving_object_outcome


def _out(logic_id, *, boss=False, sprite=0):
    return bec5_moving_object_outcome(candidate_logic_id=logic_id, a8c2_boss_mode=boss,
                                      candidate_sprite=sprite)


@pytest.mark.parametrize("logic_id", [0x0005, 0x0006, 0x0007, 0x0008, 0x0009, 0x000C])
def test_enemy_variants_damage_in_boss_mode(logic_id):
    out = _out(logic_id, boss=True)
    assert (out.kind, out.enter_at_bf25) == ("damage", True)


@pytest.mark.parametrize("logic_id", [0x0005, 0x0006, 0x0007, 0x0008, 0x0009, 0x000C])
def test_enemy_variants_instant_death_outside_boss_mode(logic_id):
    assert _out(logic_id, boss=False).kind == "instant_death"


def test_variant2_sprite_33_enters_at_bf25():
    out = _out(0x0002, sprite=0x0033)
    assert (out.kind, out.enter_at_bf25) == ("damage", True)


def test_variant2_other_sprite_enters_at_bf2d():
    out = _out(0x0002, sprite=0x0010)
    assert (out.kind, out.enter_at_bf25) == ("damage", False)


def test_variant2_is_damage_regardless_of_boss_mode():
    # Variant 2 always damages; A8C2 does not gate it.
    assert _out(0x0002, boss=False, sprite=0x0033).kind == "damage"
    assert _out(0x0002, boss=True, sprite=0x0010).kind == "damage"


@pytest.mark.parametrize("logic_id", [0x0000, 0x0001, 0x0003, 0x0004, 0x000A, 0x0042, 0x0078])
def test_other_logic_ids_are_unclassified(logic_id):
    assert _out(logic_id, boss=True).kind == "owner_or_unclassified"


@pytest.mark.parametrize("logic_id", [0x0002, 0x0005, 0x0006, 0x0007, 0x0008, 0x000C])
def test_candidate_deactivated_variants(logic_id):
    assert bec5_candidate_deactivated(logic_id) is True


@pytest.mark.parametrize("logic_id", [0x0009, 0x0000, 0x0001, 0x0042])
def test_candidate_not_deactivated_variants(logic_id):
    # Variant 9 hurts the scanner but leaves the candidate alive; other ids are owner-link/no-op.
    assert bec5_candidate_deactivated(logic_id) is False
