"""Unit tests for a067_fire_path -- the 1010:A067 spawn-path branch (after the entry gate arms)."""
from __future__ import annotations

from overkill.recovered.systems.action_spawns import (
    A067FirePath,
    a067_fire_path,
    a067_path_copies_counters,
)


def test_early_state2_tail():
    assert a067_fire_path(scroll_2350=0x50, bdac=0, fire_state_a958=2, be06=0) == A067FirePath.EARLY_STATE2


def test_early_default_tail():
    assert a067_fire_path(scroll_2350=0x50, bdac=0, fire_state_a958=0, be06=0) == A067FirePath.EARLY_DEFAULT


def test_early_requires_bdac_zero():
    # v2350 <= B6 but BDAC != 0 -> not early -> full
    assert a067_fire_path(scroll_2350=0x50, bdac=1, fire_state_a958=2, be06=0x05) == A067FirePath.FULL_FANOUT


def test_full_when_scrolled_past_threshold():
    assert a067_fire_path(scroll_2350=0xC0, bdac=0, fire_state_a958=2, be06=0) == A067FirePath.FULL_FANOUT


def test_full_bdac_a114():
    assert a067_fire_path(scroll_2350=0xC0, bdac=1, fire_state_a958=0, be06=0x08) == A067FirePath.FULL_BDAC_A114


def test_full_bdac_a515_only_over_0f():
    assert a067_fire_path(scroll_2350=0xC0, bdac=1, fire_state_a958=0, be06=0x10) == A067FirePath.FULL_BDAC_A515


def test_full_fanout_bdac_be06_between():
    # BDAC == 1 but BE06 is neither 8 nor > 0Fh -> the full fan-out
    assert a067_fire_path(scroll_2350=0xC0, bdac=1, fire_state_a958=0, be06=0x0A) == A067FirePath.FULL_FANOUT
    assert a067_fire_path(scroll_2350=0xC0, bdac=1, fire_state_a958=0, be06=0x0F) == A067FirePath.FULL_FANOUT


def test_copies_counters_full_vs_early():
    for full in (A067FirePath.FULL_FANOUT, A067FirePath.FULL_BDAC_A114, A067FirePath.FULL_BDAC_A515):
        assert a067_path_copies_counters(full) is True
    for early in (A067FirePath.EARLY_STATE2, A067FirePath.EARLY_DEFAULT):
        assert a067_path_copies_counters(early) is False
