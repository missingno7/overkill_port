"""Unit tests for the native frame controller (overkill.recovered.systems.frame_loop)."""
from __future__ import annotations

from overkill.recovered.domain.frame_loop import FrameInput
from overkill.recovered.domain.frame_snapshot import CameraState, HudLayer
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.frame_loop import (
    decode_frame_input,
    native_object_pass,
    native_player_frame_step,
)
from overkill.recovered.systems.input import (
    DEFAULT_CONTROL_MAP,
    INPUT_FIRE,
    INPUT_RIGHT,
    INPUT_UP,
    key_state_from_pressed,
)
from overkill.recovered.systems.object_update import native_object_update_pool

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


# --- native_object_pass (the A9E0 object-scan stage) -------------------------------------------

def _slot(logic_id: int, active: int = 1) -> tuple:
    words = [0] * (STRIDE >> 1)
    words[0x00 >> 1] = active
    words[0x18 >> 1] = logic_id
    return tuple(words)


def _pool(*slots: tuple, base: int) -> ObjectPool:
    return ObjectPool(base=base, stride=STRIDE, slots=slots)


def _state(special, obj, eff) -> NativeGameState:
    return NativeGameState(
        special_pool=special, object_pool=obj, effect_pool=eff,
        camera=CameraState(x=0x11, y=0x22), hud=HudLayer(counters=(1, 2, 3), score_bcd=(0, 0)),
    )


_EMPTY_GLOBALS = ObjectUpdateGlobals(
    ref_box_x=0, ref_box_y=0, a278=0, tile_probe_suppressed=False,
    tiles=LevelTileContext(origin_x_word=0, row_base_word=0, tile_plane=(), class_table=()),
)


def test_object_pass_leaves_view_anchor_camera_hud_untouched():
    # The object scan does not cover the view-anchor (special_pool) or the camera/HUD.
    special = _anchor_pool(0x40, 0x40)
    state = _state(special, _pool(_slot(0x05), base=0x2B5C), _pool(_slot(0x05), base=0x23B4))
    out = native_object_pass(state, _EMPTY_GLOBALS)
    assert out.special_pool is special
    assert out.camera is state.camera and out.hud is state.hud


def test_object_pass_delegates_both_pools_to_the_driver():
    # native_object_pass returns exactly what the driver produces for each scanned pool
    # (non-native logic ids are left to the VM -> the driver is a no-op for them here).
    obj = _pool(_slot(0x05), _slot(0x07, active=0), base=0x2B5C)
    eff = _pool(_slot(0x09), base=0x23B4)
    out = native_object_pass(_state(_anchor_pool(0, 0), obj, eff), _EMPTY_GLOBALS)
    assert out.object_pool == native_object_update_pool(obj, _EMPTY_GLOBALS)
    assert out.effect_pool == native_object_update_pool(eff, _EMPTY_GLOBALS)
