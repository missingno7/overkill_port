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
from overkill.recovered.domain.frame_loop import FrameInput
from overkill.recovered.domain.frame_snapshot import CameraState, HudLayer
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.input import DEFAULT_CONTROL_MAP, INPUT_RIGHT, key_state_from_pressed

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
