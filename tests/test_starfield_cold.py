"""Cold-load the starfield initial state from the runtime data image (starfield_adapter)."""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.recovered.adapters.starfield_adapter import DATA_SEGMENT, STREAM_OFFSET, load_starfield_state
from overkill.recovered.domain.starfield import STAR_COUNT, Star
from overkill.recovered.systems.starfield import advance_starfield

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
L1_START = ROOT / "artifacts" / "demos" / "demo_play_tandy_L1_start_20260618_143947" / "snapshot" / "memory_1mb.bin"


def _read_star_stream(image: bytes) -> tuple[Star, ...]:
    """Read the 40-star {row, dx, color} stream straight from a memory image at DS:C6C1."""
    base = DATA_SEGMENT * 16

    def rw(off: int) -> int:
        return struct.unpack_from("<H", image, base + (off & 0xFFFF))[0]

    return tuple(Star(rw(STREAM_OFFSET + i * 6), rw(STREAM_OFFSET + i * 6 + 2), rw(STREAM_OFFSET + i * 6 + 4))
                for i in range(STAR_COUNT))


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


@pytest.mark.skipif(not (BUNDLE.is_file() and L1_START.is_file()),
                    reason="static runtime bundle or L1-start capture not present")
def test_cold_starfield_advances_to_a_real_level_start():
    """The starfield is NOT re-seeded per level: the level-1 START starfield is exactly the cold
    starfield ADVANCED by the recovered move (here 71 frames of pre-level screens).  Proves the cold
    load + advance_starfield reproduce a real level start with NO snapshot/capture -- so the "starfield
    init" is load_starfield_state + advance, not an unrecovered per-level seed.
    """
    level_start = _read_star_stream(L1_START.read_bytes())
    # dx/color are fixed game data; a fresh level start shares them with the cold pattern
    cold = load_starfield_state(BUNDLE.read_bytes())
    assert all((cold.stars[i].dx, cold.stars[i].color) == (level_start[i].dx, level_start[i].color)
               for i in range(STAR_COUNT))
    # advancing the cold field reproduces the full 40-star level-start state exactly
    state = load_starfield_state(BUNDLE.read_bytes())
    for frame in range(600):
        if state.stars == level_start:
            break
        state = advance_starfield(state)
    assert state.stars == level_start   # reached the exact level-1 start by cold-load + advance
