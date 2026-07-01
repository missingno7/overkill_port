"""Structural unit tests for object_update_b1b0 (the two-state seeker, logic_id 0x0A).

Byte-exact correctness is covered by verify_native_object_update (L6_boss 386/386); these lock the
state-machine wiring (sprite, the two-state branches, the A97E/A43A globals, the tail selection).  An
all-blocked direction table (0xFF) makes 5DB2/5E42 deterministic (no move), isolating the control flow.
"""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import (
    B1B0_SPRITE_BIAS,
    B1B0_TAIL_BOUNDS,
    B1B0_TAIL_COMPACT,
    B1B0_TAIL_DEACTIVATE,
    object_update_b1b0,
)

EFFECT_BASE, STRIDE = 0x23B4, 0x38
_BLOCKED = (0xFF,) * 16          # every A348 entry FFh -> 5DB2/5E42 blocked (no move)


def _slot(*, active=1, x=0x10, logic=2, hazard=4, y=0x20, scan=0) -> tuple[int, ...]:
    w = [0] * (STRIDE >> 1)
    w[0x00 >> 1] = active
    w[0x02 >> 1] = x
    w[0x04 >> 1] = y
    w[0x14 >> 1] = scan
    w[0x16 >> 1] = hazard
    w[0x18 >> 1] = logic
    return tuple(w)


def _effect(slot_map: dict[int, tuple[int, ...]]) -> ObjectPool:
    inactive = (0x0000,) * (STRIDE >> 1)
    return ObjectPool(base=EFFECT_BASE, stride=STRIDE, slots=tuple(slot_map.get(i, inactive) for i in range(0x23)))


def _run(**kw):
    d = dict(state=1, x_word=0x0080, y_word=0x0080, direction=0, active_word=1,
             acquired_target_ptr=EFFECT_BASE, move_step_error=0, phase_2328=0x0010,
             view_x=0x0100, view_y=0x0100, a97e=5, cursor_a43a=EFFECT_BASE, step_mode=0,
             direction_table=_BLOCKED, effect_pool=_effect({}))
    d.update(kw)
    return object_update_b1b0(**d)


def test_sprite_is_phase_2328_plus_6d():
    r = _run(state=1, effect_pool=_effect({0: _slot(active=0)}))
    assert r.sprite_or_state == (0x0010 + B1B0_SPRITE_BIAS)


def test_state1_inactive_target_reacquires_no_move():
    # target slot 0 inactive -> invalid -> drop to state 0, no movement, DS:A97E untouched, tail AD5A
    r = _run(state=1, x_word=0x0088, y_word=0x0090, a97e=5, effect_pool=_effect({0: _slot(active=0)}))
    assert r.state == 0 and r.tail == B1B0_TAIL_COMPACT
    assert (r.x_word, r.y_word) == (0x0088, 0x0090) and r.a97e == 5


def test_state1_far_target_reacquires():
    # target X > DCh -> invalid -> state 0
    assert _run(state=1, effect_pool=_effect({0: _slot(x=0x00E0)})).state == 0    # E0 > DC
    assert _run(state=1, effect_pool=_effect({0: _slot(x=0x00D0)})).state == 1    # D0 <= DC valid


def test_state1_valid_target_follows_tail_compact():
    # valid target (active, x<=DCh, logic!=1) -> stays state 1, steers (blocked table -> no move), tail AD5A
    r = _run(state=1, x_word=0x0088, y_word=0x0090, effect_pool=_effect({0: _slot(x=0x0050, logic=2)}))
    assert r.state == 1 and r.tail == B1B0_TAIL_COMPACT
    assert (r.x_word, r.y_word) == (0x0088, 0x0090)   # all-blocked steer -> no move


def test_state0_reached_no_candidate_deactivates():
    # state 0, blocked seek (reached) + empty effect pool -> B15A finds nothing -> tail ADC9, A97E -= 1
    r = _run(state=0, a97e=5, effect_pool=_effect({}))
    assert r.state == 0 and r.tail == B1B0_TAIL_DEACTIVATE and r.a97e == 4


def test_state0_reached_found_flips_to_follow():
    # state 0, blocked seek + a candidate at effect slot 0 -> acquire it, flip to state 1, tail AD60
    r = _run(state=0, a97e=5, cursor_a43a=EFFECT_BASE, effect_pool=_effect({0: _slot(active=1, logic=2, hazard=4, x=0x10)}))
    assert r.state == 1 and r.tail == B1B0_TAIL_BOUNDS
    assert r.acquired_target_ptr == EFFECT_BASE           # slot 0's DS offset
    assert r.a97e == 5                                    # dec then inc -> net unchanged (was != 0)


def test_state0_a97e_zero_dec_then_inc_on_found():
    # A97E == 0: the dec is skipped, so a found target leaves A97E == 1
    r = _run(state=0, a97e=0, effect_pool=_effect({0: _slot(active=1, logic=2, hazard=4, x=0x10)}))
    assert r.a97e == 1
