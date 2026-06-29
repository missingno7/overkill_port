"""Unit tests for the 9B2E movement-bits stage (step_view_anchor_by_input)."""
from __future__ import annotations

from overkill.recovered.systems.input import (
    INPUT_DOWN,
    INPUT_LEFT,
    INPUT_RIGHT,
    INPUT_UP,
)
from overkill.recovered.systems.movement import (
    OBJECT_CLAMP_X_MAX,
    OBJECT_CLAMP_X_MIN,
    OBJECT_CLAMP_Y_MAX,
    OBJECT_CLAMP_Y_MIN,
    step_view_anchor_by_input,
)


def test_no_input_does_not_move():
    r = step_view_anchor_by_input(0x50, 0x60, 0, no_clamp=False)
    assert (r.x_word, r.y_word, r.stepped) == (0x50, 0x60, False)


def test_up_steps_x_down_twice():
    # Up (A5D1) is a two-pass step of X toward X_MIN -> two pixels per frame.
    r = step_view_anchor_by_input(0x50, 0x60, INPUT_UP, no_clamp=False)
    assert (r.x_word, r.y_word, r.stepped) == (0x4E, 0x60, True)


def test_up_no_clamp_steps_x_one_pixel():
    # With the no-clamp gate set, A5D1 takes the single unclamped pixel path.
    r = step_view_anchor_by_input(0x50, 0x60, INPUT_UP, no_clamp=True)
    assert (r.x_word, r.y_word) == (0x4F, 0x60)


def test_down_steps_x_up_twice():
    r = step_view_anchor_by_input(0x50, 0x60, INPUT_DOWN, no_clamp=False)
    assert (r.x_word, r.y_word) == (0x52, 0x60)


def test_left_steps_y_down_twice():
    r = step_view_anchor_by_input(0x50, 0x60, INPUT_LEFT, no_clamp=False)
    assert (r.x_word, r.y_word) == (0x50, 0x5E)


def test_right_steps_y_up_twice():
    r = step_view_anchor_by_input(0x50, 0x60, INPUT_RIGHT, no_clamp=False)
    assert (r.x_word, r.y_word) == (0x50, 0x62)


def test_opposed_x_bits_cancel_in_order():
    # Up then down (9B2E order): -2 then +2 on X -> back to start, still flagged moved.
    r = step_view_anchor_by_input(0x50, 0x60, INPUT_UP | INPUT_DOWN, no_clamp=False)
    assert (r.x_word, r.y_word, r.stepped) == (0x50, 0x60, True)


def test_x_clamps_at_min():
    assert step_view_anchor_by_input(OBJECT_CLAMP_X_MIN, 0x60, INPUT_UP, no_clamp=False).x_word == OBJECT_CLAMP_X_MIN
    # One pixel above the floor: first pass reaches it, second pass holds.
    assert step_view_anchor_by_input(OBJECT_CLAMP_X_MIN + 1, 0x60, INPUT_UP, no_clamp=False).x_word == OBJECT_CLAMP_X_MIN


def test_x_clamps_at_max():
    assert step_view_anchor_by_input(OBJECT_CLAMP_X_MAX, 0x60, INPUT_DOWN, no_clamp=False).x_word == OBJECT_CLAMP_X_MAX


def test_y_clamps_at_min():
    assert step_view_anchor_by_input(0x50, OBJECT_CLAMP_Y_MIN, INPUT_LEFT, no_clamp=False).y_word == OBJECT_CLAMP_Y_MIN


def test_y_right_uses_below_condition_at_max():
    # A607's unsigned `below` test stops exactly at Y_MAX (0xB0).
    assert step_view_anchor_by_input(0x50, OBJECT_CLAMP_Y_MAX - 1, INPUT_RIGHT, no_clamp=False).y_word == OBJECT_CLAMP_Y_MAX
    assert step_view_anchor_by_input(0x50, OBJECT_CLAMP_Y_MAX, INPUT_RIGHT, no_clamp=False).y_word == OBJECT_CLAMP_Y_MAX


def test_diagonal_moves_both_axes():
    # Up + right -> X toward min, Y toward max, independently.
    r = step_view_anchor_by_input(0x50, 0x60, INPUT_UP | INPUT_RIGHT, no_clamp=False)
    assert (r.x_word, r.y_word) == (0x4E, 0x62)
