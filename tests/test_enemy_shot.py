"""The 4D95 canned-random step + the 7476 enemy-shot stamp (frame_loop) + the ring adapter."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.systems.frame_loop import (
    CANNED_RANDOM_RING_BASE_20A8,
    canned_random_next_4d95,
    enemy_shot_stamp_7476,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
LIVE = ROOT / "artifacts" / "demos" / "demo_play_tandy_L1_start_20260618_143947" / "snapshot" / "memory_1mb.bin"


def test_canned_random_walks_and_wraps_the_ring():
    ring = tuple(range(100, 116))
    cursor = CANNED_RANDOM_RING_BASE_20A8
    seen = []
    for _ in range(16):
        value, cursor = canned_random_next_4d95(cursor, ring)
        seen.append(value)
    # +2 first, so the walk starts at ring[1] and wraps back through ring[0]
    assert seen == list(range(101, 116)) + [100]
    assert cursor == CANNED_RANDOM_RING_BASE_20A8


@pytest.mark.skipif(not (BUNDLE.is_file() and LIVE.is_file()), reason="artifacts not present")
def test_canned_random_ring_is_static_cold_equals_live():
    from overkill.recovered.adapters.canned_random_adapter import load_canned_random_ring

    cold = load_canned_random_ring(BUNDLE.read_bytes())
    assert len(cold) == 16
    assert cold == load_canned_random_ring(LIVE.read_bytes())


def test_enemy_shot_stamp_muzzle_variants_and_aim_deltas():
    normal = enemy_shot_stamp_7476(0x40, 0x30, False, player_x_237e=0x50, player_y_2380=0x60)
    assert (normal[0x02], normal[0x04]) == (0x4C, 0x3C)          # +0x0C / +0x0C
    assert (normal[0x16], normal[0x18], normal[0x08]) == (2, 0x0B, 0x31)
    assert normal[0x2A] == (0x4C - 0x50) & 0xFFFF                 # signed delta to player X
    assert normal[0x2C] == (0x3C - (0x60 + 9)) & 0xFFFF           # signed delta to player Y + 9
    leader = enemy_shot_stamp_7476(0x40, 0x30, True, player_x_237e=0x50, player_y_2380=0x60)
    assert (leader[0x02], leader[0x04]) == (0x48, 0x4C)          # +0x08 / +0x1C
