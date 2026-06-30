"""Unit tests for the A378 player-shot follow-up fail-loud tripwire."""
from __future__ import annotations

import pytest

from overkill.gameplay.player_shot_spawn_gap import (
    PlayerShotSpawnGap,
    set_raise_on_encounter,
    witness_a378_spawn_gap,
)


def test_tripwire_raises_by_default():
    set_raise_on_encounter(True)
    try:
        with pytest.raises(PlayerShotSpawnGap):
            witness_a378_spawn_gap(0x0050, 0x0060)
    finally:
        set_raise_on_encounter(True)


def test_tripwire_silent_when_disabled():
    set_raise_on_encounter(False)
    try:
        witness_a378_spawn_gap(0x0050, 0x0060)  # must not raise (the verify probe replays witnesses)
    finally:
        set_raise_on_encounter(True)  # restore the default-armed tripwire for other tests
