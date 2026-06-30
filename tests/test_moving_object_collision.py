"""Unit tests for the composed moving-object collision (resolve_moving_object_collision)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.collision import resolve_moving_object_collision

STRIDE = 0x38


def _cand(logic_id, *, x=0x40, y=0x40, sprite=0, active=1, solid=1) -> tuple:
    w = [0] * (STRIDE >> 1)
    w[0x00 >> 1] = active
    w[0x02 >> 1] = x
    w[0x04 >> 1] = y
    w[0x08 >> 1] = sprite
    w[0x18 >> 1] = logic_id
    w[0x1E >> 1] = solid
    return tuple(w)


def _pool(*cands) -> ObjectPool:
    return ObjectPool(base=0x2B5C, stride=STRIDE, slots=cands)


def _collide(pool, *, boss=False, counter=2, object_type=1, logic_id=0x10):
    return resolve_moving_object_collision(
        scanner_active_word=1, scanner_x_word=0x40, scanner_y_word=0x40,
        scanner_draw_layer=1, scanner_logic_id=logic_id, scanner_object_type=object_type,
        scanner_counter_20=counter, candidates=pool, a8c2_boss_mode=boss, bedc=0x0002)


def test_no_overlap_is_no_collision():
    r = _collide(_pool(_cand(5, x=0x200, y=0x200)), counter=7)
    assert (r.collided, r.died, r.new_counter_20) == (False, False, 7)


def test_enemy_variant_instant_death_outside_boss():
    r = _collide(_pool(_cand(5)), boss=False, object_type=1)
    assert r.collided and r.died and r.new_counter_20 == 0
    assert (r.death_transition.logic_id, r.death_transition.sprite_or_state) == (1, 0)  # type 1 -> sprite 0


def test_enemy_variant_damage_survives_in_boss():
    r = _collide(_pool(_cand(5)), boss=True, counter=10)  # 2 decs (bedc=2) -> 8
    assert r.collided and not r.died and r.new_counter_20 == 8


def test_enemy_variant_damage_kills_in_boss():
    r = _collide(_pool(_cand(6)), boss=True, counter=2, object_type=2)
    assert r.collided and r.died and r.new_counter_20 == 0
    assert r.death_transition.sprite_or_state == 3  # type 2 -> sprite 3


def test_variant2_always_damages():
    r = _collide(_pool(_cand(2, sprite=0x33)), boss=False, counter=10)  # enter_at_bf25 -> 2 decs
    assert r.collided and not r.died and r.new_counter_20 == 8


def test_owner_link_variant_is_unclassified():
    r = _collide(_pool(_cand(0x42)))
    assert r.collided and r.unclassified and not r.died


def test_first_overlapping_candidate_decides():
    # A non-overlapping enemy then an overlapping instant-death enemy -> the hit is the latter.
    r = _collide(_pool(_cand(5, x=0x200, y=0x200), _cand(5)), boss=False)
    assert r.died and r.new_counter_20 == 0
