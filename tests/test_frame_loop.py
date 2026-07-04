"""Unit tests for the native frame controller (overkill.recovered.systems.frame_loop)."""
from __future__ import annotations

from overkill.recovered.domain.frame_loop import FireControlState, FrameInput
from overkill.recovered.domain.frame_snapshot import CameraState, HudLayer
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.object_slots import ObjectPool, PlayerShotSpawn
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.frame_loop import (
    decode_frame_input,
    frame_axis_dispatch_offset,
    native_action_fanout_step,
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
from overkill.recovered.systems.objects import apply_player_shot_to_pool

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


# --- apply_player_shot_to_pool (the spawn write side native_action_fanout_step folds in) -------

GAMEPLAY_BASE = 0x2B5C
_FREE_WORDS = tuple([0] * (STRIDE >> 1))


def _gameplay_pool(free_slots: int) -> ObjectPool:
    return ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=(_FREE_WORDS,) * free_slots)


def _shot(offset: int, *, x=0x50, y=0x60, logic=0x0C, sprite=0x32) -> PlayerShotSpawn:
    return PlayerShotSpawn(
        slot_offset=offset, new_cursor=offset, active_word=1, scan_enable_or_solid=1,
        direction_or_step=0, sprite_or_state=sprite, scan_flag=0, hazard_class=2,
        logic_id=logic, substate=0xFFFF, x_word=x, y_word=y,
    )


def test_apply_player_shot_writes_all_ten_stamped_fields():
    out = apply_player_shot_to_pool(_gameplay_pool(1), _shot(GAMEPLAY_BASE, x=0x99, y=0x77, logic=0x0B, sprite=0x40))
    assert (out.active_word(0), out.x_word(0), out.y_word(0)) == (1, 0x99, 0x77)
    assert (out.logic_id(0), out.sprite_word(0)) == (0x0B, 0x40)


def test_apply_player_shot_preserves_unrelated_words():
    words = list(_FREE_WORDS)
    words[0x10 >> 1] = 0xBEEF
    pool = ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=(tuple(words),))
    out = apply_player_shot_to_pool(pool, _shot(GAMEPLAY_BASE))
    assert out.word_at(0, 0x10) == 0xBEEF


def test_apply_player_shot_targets_slot_by_offset():
    out = apply_player_shot_to_pool(_gameplay_pool(2), _shot(GAMEPLAY_BASE + STRIDE, x=0x77))
    assert out.x_word(0) == 0 and out.x_word(1) == 0x77


# --- native_action_fanout_step (the A067 EARLY-only frame stage) -------------------------------

def _no_muzzle_table(off):
    return 0  # a1ae_project falls back to the firing object's own position


def _fanout_state(pool: ObjectPool) -> NativeGameState:
    return _state(_anchor_pool(0, 0), pool, _pool(base=0x23B4))


def test_fanout_not_pressed_clears_latch_leaves_pool_untouched():
    pool = _gameplay_pool(8)
    out_state, out_fire = native_action_fanout_step(
        _fanout_state(pool), FireControlState(latch_a980=1, cursor_95da=GAMEPLAY_BASE),
        input_flags=0, repeat_9790=0, state_232a=0, scroll_2350=0, bdac=0, a958=0, be06=0,
        source_index=0, source_x=0x50, source_y=0x60, read_ds_word=_no_muzzle_table,
    )
    assert out_state.object_pool is pool  # untouched -> same object
    assert out_fire.latch_a980 == 0  # not pressed -> the latch clears


def test_fanout_fresh_press_early_default_spawns_one_shot():
    pool = _gameplay_pool(8)
    out_state, out_fire = native_action_fanout_step(
        _fanout_state(pool), FireControlState(),  # latch 0 (fresh press), cursor at the pool base
        input_flags=INPUT_FIRE, repeat_9790=0, state_232a=0, scroll_2350=0, bdac=0,
        a958=0, be06=0,  # a958 != 2 -> EARLY_DEFAULT (the A19F single tail)
        source_index=0, source_x=0x50, source_y=0x60, read_ds_word=_no_muzzle_table,
    )
    assert out_fire.latch_a980 == 1
    assert out_fire.cursor_95da == GAMEPLAY_BASE  # A19F allocates exactly the first slot
    assert out_state.object_pool.active_word(0) == 1
    assert (out_state.object_pool.x_word(0), out_state.object_pool.y_word(0)) == (0x50, 0x60)


def test_fanout_a958_2_early_state2_spawns_pair():
    pool = _gameplay_pool(8)
    out_state, out_fire = native_action_fanout_step(
        _fanout_state(pool), FireControlState(), input_flags=INPUT_FIRE, repeat_9790=0, state_232a=0,
        scroll_2350=0, bdac=0, a958=2, be06=0,  # a958 == 2 -> EARLY_STATE2 (the A1C8 pair)
        source_index=0, source_x=0x50, source_y=0x60, read_ds_word=_no_muzzle_table,
    )
    assert out_fire.latch_a980 == 1
    assert out_fire.cursor_95da == GAMEPLAY_BASE + STRIDE  # A1C8 allocates 2 slots, parks on the 2nd
    assert out_state.object_pool.active_word(0) == 1 and out_state.object_pool.active_word(1) == 1


def test_fanout_held_non_repeatable_no_spawn_latch_unchanged():
    pool = _gameplay_pool(8)
    out_state, out_fire = native_action_fanout_step(
        _fanout_state(pool), FireControlState(latch_a980=1, cursor_95da=GAMEPLAY_BASE),
        input_flags=INPUT_FIRE, repeat_9790=0, state_232a=0,  # held (latch!=0), not repeat-enabled, not sentinel
        scroll_2350=0, bdac=0, a958=0, be06=0,
        source_index=0, source_x=0x50, source_y=0x60, read_ds_word=_no_muzzle_table,
    )
    assert out_state.object_pool is pool  # untouched
    assert (out_fire.latch_a980, out_fire.cursor_95da) == (1, GAMEPLAY_BASE)  # unchanged


def test_fanout_full_path_declines_pool_but_still_arms_latch():
    state = _fanout_state(_gameplay_pool(8))
    fire = FireControlState()  # latch 0 -> a fresh press, so the entry gate arms (new_a980 = 1)
    out_state, out_fire = native_action_fanout_step(
        state, fire, input_flags=INPUT_FIRE, repeat_9790=0, state_232a=0,
        scroll_2350=0x00B7, bdac=0,  # scroll > B6h -> the FULL path -> FULL_FANOUT -> native_a067 declines
        a958=0, be06=0, source_index=0, source_x=0x50, source_y=0x60, read_ds_word=_no_muzzle_table,
    )
    # The spawn is declined (pool untouched -- the same object), but the A980 latch write happens
    # unconditionally BEFORE the path branch, so it still applies even though the spawn does not.
    assert out_state.object_pool is state.object_pool
    assert out_fire.latch_a980 == 1
    assert out_fire.cursor_95da == fire.cursor_95da  # the allocator cursor stays VM-owned on a decline


def test_fanout_full_pool_at_first_shot_declines_pool_but_still_arms_latch():
    occupied = (1,) + (0,) * ((STRIDE >> 1) - 1)
    state = _fanout_state(ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=(occupied,)))
    fire = FireControlState()  # latch 0 -> a fresh press, so the entry gate arms (new_a980 = 1)
    out_state, out_fire = native_action_fanout_step(
        state, fire, input_flags=INPUT_FIRE, repeat_9790=0, state_232a=0, scroll_2350=0, bdac=0,
        a958=0, be06=0, source_index=0, source_x=0x50, source_y=0x60, read_ds_word=_no_muzzle_table,
    )
    assert out_state.object_pool is state.object_pool  # the full pool blocked the spawn -> untouched
    assert out_fire.latch_a980 == 1
    assert out_fire.cursor_95da == fire.cursor_95da


def test_frame_axis_dispatch_offset_is_al_plus_3ah_times_2():
    # ah/al are each 0..2 (present-slot counts); offset = ((al + 3*ah) & 0xFF) << 1.
    expected = {
        (0, 0): 0, (0, 1): 2, (0, 2): 4,
        (1, 0): 6, (1, 1): 8, (1, 2): 10,
        (2, 0): 12, (2, 1): 14, (2, 2): 16,
    }
    for (ah, al), off in expected.items():
        assert frame_axis_dispatch_offset(ah, al) == off, (ah, al)
    # every offset is even (word table) and within the 0..16 span
    assert all(frame_axis_dispatch_offset(ah, al) % 2 == 0 for ah in range(3) for al in range(3))
    assert max(frame_axis_dispatch_offset(ah, al) for ah in range(3) for al in range(3)) == 16


def test_scripted_transition_fires_only_on_a47c_4():
    from overkill.recovered.systems.frame_loop import scripted_transition_fires_9b2e
    assert scripted_transition_fires_9b2e(4) is True
    for v in (0, 1, 2, 3, 5, 0x10):
        assert scripted_transition_fires_9b2e(v) is False, v


def test_death_tail_transition_9aff():
    from overkill.recovered.systems.frame_loop import death_tail_transition_9aff
    # 2326 != 3 -> nothing counts, nothing fires
    assert death_tail_transition_9aff(0, 0x0F, 0) == (False, False, False)
    assert death_tail_transition_9aff(2, 0x0F, 0) == (False, False, False)
    # dying mode: counts every frame, fires only when the anchor +08 counter hits 0x0F
    assert death_tail_transition_9aff(3, 0x0E, 1) == (False, False, True)
    assert death_tail_transition_9aff(3, 0x0F, 1) == (True, False, True)    # death transition (A346)
    assert death_tail_transition_9aff(3, 0x0F, 0) == (True, True, True)     # + game-over (A342)
    assert death_tail_transition_9aff(3, 0x10, 0) == (False, False, True)   # past 0x0F: exact match only


def test_detect_gameplay_transition_composes_the_exit_rules():
    from overkill.recovered.systems.frame_loop import detect_gameplay_transition
    from overkill.recovered.domain.frame_loop import GameplayExit
    # normal gameplay frame: anchor present (A95A != FFFF, A97A != 0) -> no exit regardless of counter
    assert detect_gameplay_transition(0, 0x1234, 5, 3, 0x0F) is None
    # scripted transition takes priority even if a death tail would also fire
    t = detect_gameplay_transition(4, 0xFFFF, 0, 3, 0x0F)
    assert t.exit is GameplayExit.SCRIPTED and t.jump_target == 0x9734
    # death tail reached via A95A == FFFF, A97A != 0 -> DEATH (jmp 9908)
    assert detect_gameplay_transition(0, 0xFFFF, 1, 3, 0x0F).exit is GameplayExit.DEATH
    # reached via A97A == 0 -> GAME_OVER (jmp 9902), and A342 beats A346
    go = detect_gameplay_transition(0, 0x1234, 0, 3, 0x0F)
    assert go.exit is GameplayExit.GAME_OVER and go.jump_target == 0x9902
    # tail reached but countdown not at 0x0F, or wrong mode -> no exit
    assert detect_gameplay_transition(0, 0xFFFF, 1, 3, 0x0E) is None
    assert detect_gameplay_transition(0, 0xFFFF, 1, 2, 0x0F) is None


def test_frame_state_update_a940_gameplay_path_composes_the_two_halves():
    from overkill.recovered.systems.frame_loop import frame_state_update_a940
    r = frame_state_update_a940(counter_a8ce=0x10, a8c8=0x22, a8cc=0x33, mode_2356=0,
                                flag_98a8=1, boss_pending_a8c2=0)
    # accumulator: A8CE++, A8C6 <- entry A8C8, A8CA <- entry A8CC, A8CC := 0
    assert (r.counter_a8ce, r.prev_a8c6, r.prev_a8ca, r.a8cc_reset) == (0x11, 0x22, 0x33, 0)
    # scan-entry tail: 98A8 := 0, 98A9 := edge(entry 98A8 != 0), scan fork on A8C2
    assert (r.flag_98a8, r.flag_98a9, r.scan_target) == (0, 1, "normal")
    assert frame_state_update_a940(0xFFFF, 0, 0, 0, 0, 0).counter_a8ce == 0xFFFF   # saturates
    assert frame_state_update_a940(0, 0, 0, 0, 0, 1).scan_target == "boss"          # A8C2 == 1
    assert frame_state_update_a940(0, 0, 0, 0, 0, 0).flag_98a9 == 0                 # 98A8 was 0


def test_frame_state_update_a940_attract_path_fails_loud():
    import pytest
    from overkill.recovered.systems.frame_loop import frame_state_update_a940
    from overkill.recovered.domain.gaps import RecoveryGap
    with pytest.raises(RecoveryGap):
        frame_state_update_a940(0, 0, 0, 5, 0, 0)   # DS:2356 == 5 attract middle not modelled
