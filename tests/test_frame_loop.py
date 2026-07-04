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


def test_step_death_tail_9aff_increments_and_fires():
    from overkill.recovered.systems.frame_loop import step_death_tail_9aff
    from overkill.recovered.domain.frame_loop import GameplayExit
    # anchor present -> tail not reached -> counter unchanged, no transition
    r = step_death_tail_9aff(a95a=0x3, a97a=0x57, v2326=3, anchor_counter=0x10)
    assert (r.anchor_counter, r.transition, r.deactivate_anchor) == (0x10, None, False)
    # reached (A95A==FFFF) + dying + below limit -> increments, no fire
    r = step_death_tail_9aff(a95a=0xFFFF, a97a=1, v2326=3, anchor_counter=0x0D)
    assert (r.anchor_counter, r.transition) == (0x0E, None)
    # increments to 0x0F -> DEATH fires + anchor deactivates
    r = step_death_tail_9aff(a95a=0xFFFF, a97a=1, v2326=3, anchor_counter=0x0E)
    assert r.anchor_counter == 0x0F and r.transition.exit is GameplayExit.DEATH and r.deactivate_anchor
    # reached via A97A==0 -> GAME_OVER variant
    assert step_death_tail_9aff(0x3, 0, 3, 0x0E).transition.exit is GameplayExit.GAME_OVER
    # reached but not dying (2326 != 3) -> unchanged
    assert step_death_tail_9aff(0xFFFF, 1, 2, 0x05).anchor_counter == 0x05
    assert step_death_tail_9aff(0xFFFF, 1, 2, 0x05).transition is None


def test_a940_speed_bucket_cascades():
    from overkill.recovered.systems.frame_loop import a940_speed_bucket
    assert a940_speed_bucket(0x40) == 0x0A     # > 0x10
    assert a940_speed_bucket(0x10) == 0x06
    assert a940_speed_bucket(0x08) == 0x04
    assert a940_speed_bucket(0x04) == 0x01


def test_a940_attract_middle_98a5_countdown_and_98a2_negate():
    from overkill.recovered.systems.frame_loop import step_a940_attract_middle
    # 98A2 != 0 -> negate 98AA, clear 98A2, set 98A4 = 1
    assert step_a940_attract_middle(a98a2=1, a98aa=5, a98a5=0, a98a3=0x10, a47e=0x40) == \
        (0, 1, (-5) & 0xFFFF, 0, 0x11)
    # 98A5 == 0 -> stays 0, 98A3 increments
    assert step_a940_attract_middle(0, 0x1234, 0, 0x10, 0x40) == (0, 0, 0x1234, 0, 0x11)
    # 98A5 == 1 -> reload bucket, 98A3 increments
    assert step_a940_attract_middle(0, 0x1234, 1, 0x7F, 0x40) == (0, 0, 0x1234, 0x0A, 0x80)
    # 98A5 > 1 -> decrement, 98A3 RESET to 0 (the A9B3 branch the lifted code misses)
    assert step_a940_attract_middle(0, 0x1234, 5, 0x20, 0x40) == (0, 0, 0x1234, 4, 0)
    assert step_a940_attract_middle(0, 0x1234, 3, 0x99, 0x40) == (0, 0, 0x1234, 2, 0)


def test_step_death_countdown_9e69_arm_gate_and_toggle():
    from overkill.recovered.systems.frame_loop import step_death_countdown_9e69
    # gated off when A47C == 1 or 2384 >= 3 -> no change
    assert step_death_countdown_9e69(a47c=1, counter_2384=0, a362=0, a95a=0x3) == (0, 0x3, False)
    assert step_death_countdown_9e69(a47c=0, counter_2384=3, a362=1, a95a=0x3) == (1, 0x3, False)
    # armed, A362 0 -> toggles to 1, no decrement
    assert step_death_countdown_9e69(a47c=0, counter_2384=0, a362=0, a95a=0x3) == (1, 0x3, False)
    # armed, A362 1 -> toggles to 0, decrements A95A (every-other-frame)
    assert step_death_countdown_9e69(a47c=0, counter_2384=2, a362=1, a95a=0x3) == (0, 0x2, False)
    # A95A 0 -> FFFF = anchor lost (death stage 1 complete)
    assert step_death_countdown_9e69(a47c=0, counter_2384=0, a362=1, a95a=0x0) == (0, 0xFFFF, True)


def test_step_game_over_countdown_9ee4():
    from overkill.recovered.systems.frame_loop import step_game_over_countdown_9ee4
    # A97A == 0 -> no-op ret (game over already settled)
    assert step_game_over_countdown_9ee4(0) == (0, False, True)
    # decrement to non-zero -> still counting (9EF2)
    assert step_game_over_countdown_9ee4(0x57) == (0x56, False, False)
    assert step_game_over_countdown_9ee4(2) == (1, False, False)
    # decrement to zero -> game over reached (9EF5)
    assert step_game_over_countdown_9ee4(1) == (0, True, False)


def test_step_a95c_difficulty_countdown_9e43():
    from overkill.recovered.systems.frame_loop import step_a95c_difficulty_countdown_9e43
    # BEDC decrement scale: 0 -> 1, 1 -> 2, >=2 -> 3
    assert step_a95c_difficulty_countdown_9e43(0, 5) == (4, False)
    assert step_a95c_difficulty_countdown_9e43(1, 5) == (3, False)
    assert step_a95c_difficulty_countdown_9e43(2, 5) == (2, False)
    assert step_a95c_difficulty_countdown_9e43(5, 10) == (7, False)   # BEDC >= 2 -> dec 3
    # reaching 0 (A95C <= count) reloads to 0x18
    assert step_a95c_difficulty_countdown_9e43(0, 1) == (0x18, True)
    assert step_a95c_difficulty_countdown_9e43(1, 2) == (0x18, True)
    assert step_a95c_difficulty_countdown_9e43(2, 3) == (0x18, True)
    assert step_a95c_difficulty_countdown_9e43(2, 1) == (0x18, True)


def test_scripted_input_prologue_99f6():
    from overkill.recovered.systems.frame_loop import scripted_input_prologue_99f6
    # clears bit 0 of 2380, clears 98BE, table byte offset = A47C * 2
    assert scripted_input_prologue_99f6(a47c=0, prev_2380=0xFFFF) == (0xFFFE, 0, 0)
    assert scripted_input_prologue_99f6(a47c=1, prev_2380=0x0001) == (0x0000, 0, 2)
    assert scripted_input_prologue_99f6(a47c=4, prev_2380=0x1235) == (0x1234, 0, 8)
    assert scripted_input_prologue_99f6(a47c=0x10, prev_2380=0x0000) == (0x0000, 0, 0x20)


def test_step_death_seq_9dea():
    from overkill.recovered.systems.frame_loop import step_death_seq_9dea
    # A95C not yet 0x18 -> just increment A95C
    assert step_death_seq_9dea(0x05, 0x03, 0) == (0x06, 0x03, None)
    assert step_death_seq_9dea(0x17, 0x00, 1) == (0x18, 0x00, None)
    # A95C == 0x18 and A95A == 3 -> no-op
    assert step_death_seq_9dea(0x18, 0x03, 1) == (0x18, 0x03, None)
    # A95C == 0x18 and A95A != 3 -> advance (inc A95A, A95C=0); BEFF only when 98C0 != 0
    assert step_death_seq_9dea(0x18, 0x02, 0) == (0x00, 0x03, None)
    assert step_death_seq_9dea(0x18, 0x05, 1) == (0x00, 0x06, 0x1C)


def test_step_game_over_arm_9db9():
    from overkill.recovered.systems.frame_loop import step_game_over_arm_9db9
    # no-op when A97A == 0x58 or A97C == 1 (already armed)
    assert step_game_over_arm_9db9(0x58, 0, 0, 0, 1) == (0, None)
    assert step_game_over_arm_9db9(0x30, 1, 0, 0, 1) == (1, None)
    # A97A != 0x58, A97C == 0, 2384 >= 3 -> stays 0
    assert step_game_over_arm_9db9(0x30, 0, 3, 0, 1) == (0, None)
    # 2384 < 3 -> arm A97C := 1; BEFF = 0x0D only when BDAC != 1 AND 98C0 != 0
    assert step_game_over_arm_9db9(0x30, 0, 0, 0, 1) == (1, 0x0D)
    assert step_game_over_arm_9db9(0x30, 0, 0, 1, 1) == (1, None)   # BDAC == 1 -> no BEFF
    assert step_game_over_arm_9db9(0x30, 0, 0, 0, 0) == (1, None)   # 98C0 == 0 -> no BEFF


def test_step_death_handler_9a16_composition():
    from overkill.recovered.systems.frame_loop import step_death_handler_9a16
    # sets scripted input 98BE := 8 always
    assert step_death_handler_9a16(0x30, 0, 0x02, 0x05, 0, 0, 1)[0] == 0x08
    # A47C advances only when (post sub-steps) A97A == 0x58 AND A95A == 3 AND A95C == 0x18.
    # A95C=0x18 with A95A=3 -> 9DEA no-ops (A95A stays 3, A95C stays 0x18); A97A 0x58 -> advance
    i98be, a97c, a95a, a95c, adv = step_death_handler_9a16(0x58, 0, 0x03, 0x18, 0, 0, 1)
    assert (a95a, a95c, adv) == (0x03, 0x18, True)
    # A97A != 0x58 -> no advance
    assert step_death_handler_9a16(0x30, 0, 0x03, 0x18, 0, 0, 1)[4] is False
    # A95C != 0x18 (9DEA increments it) -> no advance
    assert step_death_handler_9a16(0x58, 0, 0x03, 0x05, 0, 0, 1)[4] is False


def test_step_scripted_move_counters_9a3e():
    from overkill.recovered.systems.frame_loop import step_scripted_move_counters_9a3e
    # 2384 == 0 -> caps A39C 0x08 / A39A 0xFFF8
    assert step_scripted_move_counters_9a3e(0, 0x05, 0xFFFA) == (0x06, 0xFFF9)
    assert step_scripted_move_counters_9a3e(0, 0x08, 0xFFF8) == (0x08, 0xFFF8)   # capped
    # 2384 != 0 -> caps A39C 0x0F / A39A 0xFFF1
    assert step_scripted_move_counters_9a3e(1, 0x05, 0xFFF5) == (0x06, 0xFFF4)
    assert step_scripted_move_counters_9a3e(1, 0x0F, 0xFFF1) == (0x0F, 0xFFF1)   # capped
    assert step_scripted_move_counters_9a3e(3, 0x00, 0xFFFF) == (0x01, 0xFFFE)


def test_a47c_script_arms_a680():
    from overkill.recovered.systems.frame_loop import a47c_script_arms_a680, A47C_ARM_GATE_2350
    assert A47C_ARM_GATE_2350 == 0x0EA0
    # the one arming combination
    assert a47c_script_arms_a680(0, 1, 0x0EA0) is True
    # each guard is necessary
    assert a47c_script_arms_a680(1, 1, 0x0EA0) is False   # A480 must be 0
    assert a47c_script_arms_a680(0, 0, 0x0EA0) is False   # 234E must be exactly 1
    assert a47c_script_arms_a680(0, 2, 0x0EA0) is False   # ...not merely nonzero
    assert a47c_script_arms_a680(0, 1, 0x0E52) is False    # 2350 must match exactly
    assert a47c_script_arms_a680(0, 1, 0x0EA1) is False
