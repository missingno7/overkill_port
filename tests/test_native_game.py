"""The native game core (overkill.game_core.NativeGame) -- run frames over a cold-loaded level.

Proves the two halves meet: a level loaded entirely from the original files (EXE image + container) is
stepped by the recovered frame systems with no VM.  The tile context the object scan samples is the
cold-loaded tile plane (byte-identical to the VM's, proven elsewhere), so the recovered systems run on
cold data exactly as on the VM.
"""
from __future__ import annotations

import pathlib

import pytest

from overkill.native_game import NativeGame
from overkill.recovered.domain.frame_loop import FireControlState, FrameInput
from overkill.recovered.domain.frame_snapshot import CameraState, HudLayer
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.input import DEFAULT_CONTROL_MAP, INPUT_FIRE, INPUT_RIGHT, key_state_from_pressed

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"

STRIDE = 0x38
RIGHT_ARROW = 0x4D


def _anchor_pool(x: int, y: int) -> ObjectPool:
    words = [0] * (STRIDE >> 1)
    words[0x02 >> 1] = x
    words[0x04 >> 1] = y
    return ObjectPool(base=0x237C, stride=STRIDE, slots=(tuple(words),))


def _empty_pool(base: int) -> ObjectPool:
    return ObjectPool(base=base, stride=STRIDE, slots=())


def _starting_state() -> NativeGameState:
    # Level-start gameplay state: a player view anchor + empty object/effect pools (enemies spawn later).
    return NativeGameState(
        special_pool=_anchor_pool(0x50, 0x60),
        object_pool=_empty_pool(0x2B5C),
        effect_pool=_empty_pool(0x23B4),
        camera=CameraState(x=0, y=0),
        hud=HudLayer(counters=(0, 0, 0), score_bcd=(0, 0)),
    )


def _input(*pressed: int) -> FrameInput:
    return FrameInput(control_map=DEFAULT_CONTROL_MAP, key_state=key_state_from_pressed(pressed))


@pytest.mark.skipif(not OVERKILL.is_file() or not BUNDLE.is_file(), reason="game data not present")
def test_native_game_runs_frames_over_a_cold_loaded_level():
    game = NativeGame.load_level(BUNDLE.read_bytes(), OVERKILL.read_bytes(), 0, _starting_state())

    # The tile context the recovered systems sample comes straight from the cold-loaded level.
    assert game.tile_context.tile_plane is game.level.tile_plane
    assert len(game.level.tile_plane) == 3744 and len(game.level.class_table) == 256
    assert len(game.level.blocks) > 0 and len(game.level.graphics) > 0

    # Player stage: moving right advances the view-anchor Y (the recovered 9B2E movement bits).
    moved, step = game.step_player(_input(RIGHT_ARROW))
    assert step.input_flags == INPUT_RIGHT and step.moved
    assert moved.state.special_pool.y_word(0) == 0x62
    assert moved.state.special_pool.x_word(0) == 0x50

    # Object stage runs over the cold tile context (empty pools at level start -> state carries through).
    globals_ = ObjectUpdateGlobals(
        ref_box_x=0, ref_box_y=0, a278=0, tile_probe_suppressed=False,
        tiles=LevelTileContext(origin_x_word=0, row_base_word=0, tile_plane=(), class_table=()),
    )
    advanced = moved.step_objects(globals_)
    assert advanced.state.object_pool.slots == ()
    assert advanced.state.special_pool is moved.state.special_pool  # object scan leaves the anchor alone


def test_native_game_with_state_is_functional():
    # with_state swaps the gameplay state, leaving the cold level + scroll intact (pure/functional).
    from overkill.asset_codecs.native_level import NativeLevel

    lvl = NativeLevel(level=0, tile_plane=b"\x00" * 3744, class_table=b"\x01" * 256, blocks=b"", graphics=b"")
    game = NativeGame(lvl, _starting_state(), origin_x=0x10, row_base=0x20)
    other = game.with_state(_starting_state())
    assert other.level is game.level and other.origin_x == 0x10 and other.row_base == 0x20
    assert game.tile_context.origin_x_word == 0x10 and game.tile_context.row_base_word == 0x20


def test_native_game_step_action_fanout_composes_and_wires_fire_state():
    # step_action_fanout wires native_action_fanout_step: folds a spawn into state.object_pool and
    # advances the carried FireControlState -- no game data needed (a hand-built pool with free slots).
    from overkill.asset_codecs.native_level import NativeLevel

    lvl = NativeLevel(level=0, tile_plane=b"\x00" * 3744, class_table=b"\x01" * 256, blocks=b"", graphics=b"")
    free_slot = tuple([0] * (STRIDE >> 1))
    state = NativeGameState(
        special_pool=_anchor_pool(0x50, 0x60),
        object_pool=ObjectPool(base=0x2B5C, stride=STRIDE, slots=(free_slot,) * 4),
        effect_pool=_empty_pool(0x23B4),
        camera=CameraState(x=0, y=0), hud=HudLayer(counters=(0, 0, 0), score_bcd=(0, 0)),
    )
    game = NativeGame(lvl, state)
    assert game.fire == FireControlState()  # default: latch 0, cursor parked at the gameplay base

    out = game.step_action_fanout(
        input_flags=INPUT_FIRE, repeat_9790=0, state_232a=0, scroll_2350=0, bdac=0, a958=0, be06=0,
        source_index=0, source_x=0x50, source_y=0x60, read_ds_word=lambda off: 0,
    )
    assert out is not game  # a new NativeGame, not mutated in place
    assert out.fire.latch_a980 == 1
    assert out.state.object_pool.active_word(0) == 1
    assert (out.state.object_pool.x_word(0), out.state.object_pool.y_word(0)) == (0x50, 0x60)


def _scroll_game(origin_x: int, row_base: int, **extra) -> NativeGame:
    from overkill.asset_codecs.native_level import NativeLevel

    lvl = NativeLevel(level=0, tile_plane=b"\x00" * 3744, class_table=b"\x01" * 256, blocks=b"", graphics=b"")
    return NativeGame(lvl, _starting_state(), origin_x=origin_x, row_base=row_base, **extra)


def test_native_game_step_scroll_advances_origin_and_row_base():
    # origin_x==0 at entry -> this tick pulls a tile row (row_base += 13) and origin_x wraps to 15.
    game = _scroll_game(origin_x=0, row_base=0x100, rows_to_milestone=10)
    out, outcome = game.step_scroll(a47c=0, a47e=0, a480=0)
    assert outcome is not None and outcome.pulled_row
    assert out is not game  # functional: a new NativeGame
    assert out.origin_x == 0x0F
    assert out.row_base == 0x100 + 0x0D
    assert out.rows_to_milestone == 9
    # The evolved bookkeeping round-trips through the .scroll view.
    assert out.scroll.origin_x == 0x0F and out.scroll.row_base == 0x100 + 0x0D


def test_native_game_step_scroll_is_a_noop_when_gate_globals_are_set():
    game = _scroll_game(origin_x=0, row_base=0x100)
    out, outcome = game.step_scroll(a47c=1, a47e=0, a480=0)
    assert outcome is not None and not outcome.pulled_row
    assert out.origin_x == game.origin_x and out.row_base == game.row_base


def test_native_game_step_scroll_declines_on_milestone_and_leaves_game_unchanged():
    from overkill.recovered.systems.scroll import BOSS_MATERIALIZE_ROW_BASE, FORWARD_ROW_STRIDE

    game = _scroll_game(origin_x=0, row_base=BOSS_MATERIALIZE_ROW_BASE - FORWARD_ROW_STRIDE, rows_to_milestone=1)
    out, outcome = game.step_scroll(a47c=0, a47e=0, a480=0)
    assert outcome is None  # A66F's boss-materialize branch -- caller stays VM-owned this tick
    assert out is game  # unchanged


def test_native_game_step_composes_all_stages_in_order_incl_native_scroll():
    # step() is composition glue: it must produce EXACTLY what hand-chaining step_player ->
    # step_scroll -> step_action_fanout -> step_objects (threading input_flags + the native row_base
    # by hand) produces, in the real 9B2E -> A66F -> A067 -> AA0D order.
    from overkill.asset_codecs.native_level import NativeLevel

    lvl = NativeLevel(level=0, tile_plane=b"\x00" * 3744, class_table=b"\x01" * 256, blocks=b"", graphics=b"")
    free_slot = tuple([0] * (STRIDE >> 1))
    state = NativeGameState(
        special_pool=_anchor_pool(0x50, 0x60),
        object_pool=ObjectPool(base=0x2B5C, stride=STRIDE, slots=(free_slot,) * 4),
        effect_pool=_empty_pool(0x23B4),
        camera=CameraState(x=0, y=0), hud=HudLayer(counters=(0, 0, 0), score_bcd=(0, 0)),
    )
    # origin_x=5 so this tick does NOT pull a row (keeps the compare simple); scroll still advances
    # origin_x, proving step() runs the scroll stage.
    game = NativeGame(lvl, state, origin_x=5, row_base=0x40)
    globals_ = ObjectUpdateGlobals(
        ref_box_x=0, ref_box_y=0, a278=0, tile_probe_suppressed=False,
        tiles=LevelTileContext(origin_x_word=0, row_base_word=0, tile_plane=(), class_table=()),
    )
    fanout_kwargs = dict(
        repeat_9790=0, state_232a=0, scroll_2350=0, bdac=0, a958=0, be06=0,
        source_index=0, source_x=0x50, source_y=0x60, read_ds_word=lambda off: 0,
    )
    frame_input = _input(RIGHT_ARROW)

    chained, player_step = game.step_player(frame_input)
    chained, scroll_outcome = chained.step_scroll(a47c=0, a47e=0, a480=0)
    chained = chained.step_action_fanout(
        input_flags=player_step.input_flags, **{**fanout_kwargs, "scroll_2350": chained.row_base})
    chained = chained.step_objects(globals_)

    composed, composed_step = game.step(
        frame_input, update_globals=globals_, scroll_gate=(0, 0, 0), **fanout_kwargs,
    )

    assert composed_step == player_step
    assert scroll_outcome is not None and composed.origin_x == 4  # scroll ran (origin_x 5 -> 4)
    assert composed.state == chained.state
    assert composed.fire == chained.fire
    assert (composed.origin_x, composed.row_base) == (chained.origin_x, chained.row_base)
