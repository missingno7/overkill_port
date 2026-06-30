"""Cold-load the starfield initial state from the runtime data image (starfield_adapter)."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.starfield_adapter import load_starfield_state
from overkill.recovered.domain.starfield import STAR_COUNT, Star
from overkill.recovered.systems.starfield import advance_starfield

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_cold_starfield_matches_known_data():
    state = load_starfield_state(BUNDLE.read_bytes())
    assert len(state.stars) == STAR_COUNT
    # The fixed per-star pattern (verified against the live runtime: dx/color are constant game data).
    assert state.stars[0] == Star(0x07, 0x0E, 0xF00F)
    assert state.stars[1] == Star(0x21, 0x1F, 0xF00F)
    assert state.stars[2] == Star(0x32, 0x02, 0x90F0)
    assert all(s.row < 0xC0 for s in state.stars)   # rows are valid scanlines
    assert state.enabled                              # gate A95A != 0xFFFF


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_cold_starfield_advances_cleanly():
    # The cold state drives the recovered move without error and keeps 40 valid stars.
    state = load_starfield_state(BUNDLE.read_bytes())
    for _ in range(20):
        state = advance_starfield(state)
    assert len(state.stars) == STAR_COUNT
    assert all(0 <= s.row < 0xC0 for s in state.stars)
