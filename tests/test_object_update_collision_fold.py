"""Unit tests for the BC4B collision fold in the object-update driver (_fold_bc4b_collision)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.object_update import (
    _OFF_ACTIVE,
    _OFF_COUNTER_20,
    _OFF_LOGIC_ID,
    _OFF_SPRITE,
    _OFF_X,
    _OFF_Y,
    _collide_post_move,
    _fold_bc4b_collision,
)

STRIDE = 0x38
_EMPTY_TILES = LevelTileContext(origin_x_word=0, row_base_word=0, tile_plane=(), class_table=())


def _scanner_pool(*, object_type=1, logic_id=0x1D, draw_layer=1, counter_20=10) -> ObjectPool:
    w = [0] * (STRIDE >> 1)
    w[0x14 >> 1] = object_type
    w[0x16 >> 1] = draw_layer
    w[0x18 >> 1] = logic_id
    w[0x20 >> 1] = counter_20
    return ObjectPool(base=0, stride=STRIDE, slots=(tuple(w),))


def _enemy_pool(logic_id, *, x=0x40, y=0x40, solid=1) -> ObjectPool:
    w = [0] * (STRIDE >> 1)
    w[0x00 >> 1] = 1          # active
    w[0x02 >> 1] = x
    w[0x04 >> 1] = y
    w[0x18 >> 1] = logic_id
    w[0x1E >> 1] = solid      # scan_enable_or_solid
    return ObjectPool(base=0x2B5C, stride=STRIDE, slots=(tuple(w),))


def _globals(candidate_pool, *, boss=False, global_disable=0, bedc=0x0002):
    return ObjectUpdateGlobals(ref_box_x=0, ref_box_y=0, a278=0, tile_probe_suppressed=False,
                               tiles=_EMPTY_TILES, candidate_pool=candidate_pool,
                               a8c2_boss_mode=boss, bedc=bedc, global_disable=global_disable)


_POST_MOVE = {_OFF_ACTIVE: 1, _OFF_X: 0x40, _OFF_Y: 0x40, _OFF_SPRITE: 0x99}


def test_no_candidate_pool_leaves_updates_unchanged():
    out = _fold_bc4b_collision(_scanner_pool(), 0, _globals(None), dict(_POST_MOVE))
    assert out == _POST_MOVE


def test_global_disable_skips_the_contact_scan():
    # DS:A47C != 0 -> BC4B skips the 62F6 scan entirely.
    g = _globals(_enemy_pool(5), global_disable=1)
    assert _fold_bc4b_collision(_scanner_pool(), 0, g, dict(_POST_MOVE)) == _POST_MOVE


def test_no_overlap_leaves_updates_unchanged():
    g = _globals(_enemy_pool(5, x=0x200, y=0x200))
    assert _fold_bc4b_collision(_scanner_pool(), 0, g, dict(_POST_MOVE)) == _POST_MOVE


def test_instant_death_folds_death_sprite_and_logic_id():
    g = _globals(_enemy_pool(5), boss=False)  # enemy variant 5, non-boss -> instant death
    out = _fold_bc4b_collision(_scanner_pool(object_type=1), 0, g, dict(_POST_MOVE))
    assert out[_OFF_LOGIC_ID] == 1
    assert out[_OFF_SPRITE] == 0          # object_type 1 -> C037 death sprite 0
    assert out[_OFF_COUNTER_20] == 0
    assert out[_OFF_X] == 0x40            # movement fields preserved


def test_damage_survive_folds_only_the_counter():
    g = _globals(_enemy_pool(5), boss=True)  # boss mode -> BF25 damage chain
    out = _fold_bc4b_collision(_scanner_pool(counter_20=10), 0, g, dict(_POST_MOVE))
    assert out[_OFF_COUNTER_20] == 8      # two decrements (bedc=2)
    assert _OFF_LOGIC_ID not in out       # not a death -> logic_id/sprite untouched
    assert out[_OFF_SPRITE] == 0x99


def test_dead_post_move_slot_is_not_scanned():
    dead = {**_POST_MOVE, _OFF_ACTIVE: 0}
    assert _fold_bc4b_collision(_scanner_pool(), 0, _globals(_enemy_pool(5)), dead) == dead


def test_collide_post_move_returns_the_candidate_effect():
    # _collide_post_move (the in-place pass's entry) returns the full result so the pass can clear
    # the killed candidate, while folding the scanner death into the updates.
    g = _globals(_enemy_pool(5), boss=False)  # variant 5, non-boss -> scanner instant death
    updates, result = _collide_post_move(_scanner_pool(object_type=1), 0, g, dict(_POST_MOVE))
    assert result is not None and result.died and result.candidate_deactivated and result.hit_index == 0
    assert updates[_OFF_LOGIC_ID] == 1 and updates[_OFF_SPRITE] == 0


def test_collide_post_move_none_without_candidates():
    updates, result = _collide_post_move(_scanner_pool(), 0, _globals(None), dict(_POST_MOVE))
    assert result is None and updates == _POST_MOVE
