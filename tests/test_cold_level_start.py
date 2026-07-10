"""The frame-0 level-start state assembled from the recovered cold seeds -- no VM, no snapshot."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.cold_level_start import (
    build_cold_level_start, build_cold_level_start_image,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_cold_level_start_image_matches_the_projection():
    """build_cold_level_start_image is the SAME seeded write sequence build_cold_level_start projects
    -- play_native's object-walk DGROUP (built via the image function) must agree with the NativeGame
    state (built via the projecting function) byte-for-byte on every field either one reads."""
    from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state
    from overkill.recovered.adapters.starfield_adapter import DATA_SEGMENT

    bundle = BUNDLE.read_bytes()
    state, _starfield = build_cold_level_start(bundle, level_index=2)
    image = build_cold_level_start_image(bundle, level_index=2)
    reprojected = read_native_game_state(image, DATA_SEGMENT)

    assert reprojected.special_pool.x_word(0) == state.special_pool.x_word(0)
    assert reprojected.special_pool.y_word(0) == state.special_pool.y_word(0)
    assert image.rw(DATA_SEGMENT, 0x2356) == 3  # level_index=2 -> planet 3 (LEVEL_INDEX_TO_PLANET)


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_cold_level_start_is_a_coherent_frame_zero():
    state, starfield = build_cold_level_start(BUNDLE.read_bytes())

    # the player view-anchor is spawned: record 0x237C active at (0xC0, 0x58)
    assert state.special_pool.active_word(0) == 1
    assert state.special_pool.x_word(0) == 0xC0
    assert state.special_pool.y_word(0) == 0x58

    # a fresh level starts with NO live enemies -- every gameplay slot is free
    assert len(state.object_pool) == 34
    assert all(state.object_pool.active_word(i) == 0 for i in range(len(state.object_pool)))

    # ...but exactly ONE effect slot is live: the C450/7524 COMPANION, the ship's flame/exhaust
    # anchor.  This assertion used to read "every effect slot is free", which was simply wrong --
    # the ORIGINAL's own level start (the cold-start demo's frame-0 pre-state) holds
    # slot 0x23B4 with +00=1, +14=1, +16=6, byte-identical to what the seed now writes.
    # Omitting the companion is why a cold-started level had no thrusters while a snapshot did.
    assert len(state.effect_pool) == 35
    live = [i for i in range(len(state.effect_pool)) if state.effect_pool.active_word(i) != 0]
    assert live == [0], f"expected only the companion in effect slot 0, got {live}"
    assert state.effect_pool.word_at(0, 0x14) == 1
    assert state.effect_pool.word_at(0, 0x16) == 6

    # the cold starfield is present + enabled (its own byte-exactness is proven in test_starfield_cold)
    assert len(starfield.stars) == 40
    assert starfield.enabled


CONTAINER = ROOT / "assets" / "OVERKILL"
COLD_ROW_BASE = 0x009C   # level-load leaves DS:2350 here (60C5 sets 0xEA0, the 16x A781 warm-up -> 0x9C)


@pytest.mark.skipif(not (BUNDLE.is_file() and CONTAINER.is_file()),
                    reason="static runtime bundle or OVERKILL container not present")
def test_cold_start_fires_a_persisting_shot():
    """The cold-started level FIRES: with the level-load scroll origin (row_base 0x9C, not 0 -- which
    underflows the tile probe) and the player anchor as the fan-out source, holding fire spawns player
    shots into the gameplay pool that persist + move across frames.  End-to-end proof that play_native's
    cold start produces live gameplay, VM-free.
    """
    import dataclasses
    from overkill.native_game import NativeGame
    from overkill.recovered.domain.frame_loop import FrameInput
    from overkill.recovered.domain.object_update import ObjectUpdateGlobals
    from overkill.recovered.systems.input import DEFAULT_CONTROL_MAP, key_state_from_pressed

    state, _ = build_cold_level_start(BUNDLE.read_bytes())
    game = dataclasses.replace(
        NativeGame.load_level(BUNDLE.read_bytes(), CONTAINER.read_bytes(), 0, state, origin_x=0,
                              row_base=COLD_ROW_BASE),
        row_source=0x5B00)
    FIRE = 0x39

    def tick(g, fire):
        fi = FrameInput(control_map=DEFAULT_CONTROL_MAP,
                        key_state=key_state_from_pressed({FIRE} if fire else set()))
        glob = ObjectUpdateGlobals(ref_box_x=g.state.special_pool.x_word(0),
                                   ref_box_y=g.state.special_pool.y_word(0), a278=0,
                                   tile_probe_suppressed=False, tiles=g.tile_context)
        g, _ = g.step(fi, no_clamp=False, repeat_9790=0, state_232a=0, scroll_2350=g.row_base, bdac=0,
                      a958=0, be06=0, source_index=0, source_x=g.state.special_pool.x_word(0),
                      source_y=g.state.special_pool.y_word(0), read_ds_word=lambda o: 0,
                      update_globals=glob, scroll_gate=(0, 0, 0))
        return g

    def n_active(g):
        return sum(1 for i in range(len(g.state.object_pool)) if g.state.object_pool.active_word(i) != 0)

    g = game
    assert n_active(g) == 0                     # fresh level: no shots yet
    g = tick(g, fire=True)
    assert n_active(g) == 1                      # a shot spawned at the player
    for t in range(1, 4):                        # tap-fire: alternate so the latch re-arms
        g = tick(g, fire=(t % 2 == 0))
    assert n_active(g) >= 2                       # earlier shots persisted + new ones added
