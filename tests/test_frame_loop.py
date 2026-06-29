"""Unit tests for the native frame controller (overkill.recovered.systems.frame_loop)."""
from __future__ import annotations

from overkill.recovered.domain.frame_loop import FrameInput
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.frame_loop import (
    decode_frame_input,
    native_player_frame_step,
)
from overkill.recovered.systems.input import (
    DEFAULT_CONTROL_MAP,
    INPUT_FIRE,
    INPUT_RIGHT,
    INPUT_UP,
    key_state_from_pressed,
)

STRIDE = 0x38
UP_ARROW, DOWN_ARROW, LEFT_ARROW, RIGHT_ARROW, SPACE = 0x48, 0x50, 0x4B, 0x4D, 0x39


def _anchor_pool(x: int, y: int, *, marker_word=(0x10, 0xABCD)) -> ObjectPool:
    words = [0] * (STRIDE >> 1)
    words[0x02 >> 1] = x
    words[0x04 >> 1] = y
    words[marker_word[0] >> 1] = marker_word[1]  # an unrelated word, must survive a step
    return ObjectPool(base=0x237C, stride=STRIDE, slots=(tuple(words),))


def _input(*pressed: int) -> FrameInput:
    return FrameInput(control_map=DEFAULT_CONTROL_MAP, key_state=key_state_from_pressed(pressed))


def test_decode_frame_input_delegates_to_input_system():
    assert decode_frame_input(_input(SPACE)) == INPUT_FIRE
    assert decode_frame_input(_input()) == 0


def test_no_input_leaves_pool_unchanged():
    pool = _anchor_pool(0x50, 0x60)
    out = native_player_frame_step(pool, _input(), no_clamp=False)
    assert out.moved is False
    assert out.input_flags == 0
    assert out.special_pool is pool  # untouched -> same object


def test_right_steps_anchor_y_and_reports_flags():
    pool = _anchor_pool(0x50, 0x60)
    out = native_player_frame_step(pool, _input(RIGHT_ARROW), no_clamp=False)
    assert out.input_flags == INPUT_RIGHT
    assert out.moved is True
    assert (out.special_pool.x_word(0), out.special_pool.y_word(0)) == (0x50, 0x62)


def test_up_steps_anchor_x_two_pass():
    out = native_player_frame_step(_anchor_pool(0x50, 0x60), _input(UP_ARROW), no_clamp=False)
    assert out.input_flags == INPUT_UP
    assert (out.special_pool.x_word(0), out.special_pool.y_word(0)) == (0x4E, 0x60)


def test_up_no_clamp_steps_one_pixel():
    out = native_player_frame_step(_anchor_pool(0x50, 0x60), _input(UP_ARROW), no_clamp=True)
    assert out.special_pool.x_word(0) == 0x4F


def test_step_preserves_other_slot_words():
    pool = _anchor_pool(0x50, 0x60, marker_word=(0x10, 0xBEEF))
    out = native_player_frame_step(pool, _input(RIGHT_ARROW), no_clamp=False)
    # Only X/Y change; the unrelated word at +0x10 is carried through untouched.
    assert out.special_pool.word_at(0, 0x10) == 0xBEEF
    assert out.special_pool.x_word(0) == 0x50  # right moves Y, not X
