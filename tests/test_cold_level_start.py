"""The frame-0 level-start state assembled from the recovered cold seeds -- no VM, no snapshot."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.cold_level_start import build_cold_level_start

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_cold_level_start_is_a_coherent_frame_zero():
    state, starfield = build_cold_level_start(BUNDLE.read_bytes())

    # the player view-anchor is spawned: record 0x237C active at (0xC0, 0x58)
    assert state.special_pool.active_word(0) == 1
    assert state.special_pool.x_word(0) == 0xC0
    assert state.special_pool.y_word(0) == 0x58

    # a fresh level starts with NO live enemies / effects -- every gameplay + effect slot is free
    assert len(state.object_pool) == 34
    assert all(state.object_pool.active_word(i) == 0 for i in range(len(state.object_pool)))
    assert len(state.effect_pool) == 35
    assert all(state.effect_pool.active_word(i) == 0 for i in range(len(state.effect_pool)))

    # the cold starfield is present + enabled (its own byte-exactness is proven in test_starfield_cold)
    assert len(starfield.stars) == 40
    assert starfield.enabled
