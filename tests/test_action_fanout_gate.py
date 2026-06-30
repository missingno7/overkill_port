"""Unit tests for action_fanout_gate -- the 1010:A067 entry trigger + latch decision."""
from __future__ import annotations

from overkill.recovered.systems.action_spawns import action_fanout_gate

PRESSED = 0x10  # DS:98BE bit 4 (the action trigger)


def test_not_pressed_clears_latch_and_skips():
    g = action_fanout_gate(input_flags=0x00, latch_a980=0x0001, repeat_9790=0x00, state_232a=0x0000)
    assert g.runs is False and g.new_latch_word == 0x0000


def test_trigger_is_only_bit4():
    g = action_fanout_gate(input_flags=0xEF, latch_a980=0x0000, repeat_9790=0x00, state_232a=0x0000)
    assert g.runs is False and g.new_latch_word == 0x0000   # 0xEF has bit 4 clear -> not pressed


def test_fresh_press_arms_and_runs():
    g = action_fanout_gate(input_flags=PRESSED, latch_a980=0x0000, repeat_9790=0x00, state_232a=0x0000)
    assert g.runs is True and g.new_latch_word == 0x0001


def test_held_with_repeat_byte_runs():
    g = action_fanout_gate(input_flags=PRESSED, latch_a980=0x0001, repeat_9790=0x01, state_232a=0x0000)
    assert g.runs is True and g.new_latch_word == 0x0001


def test_held_with_state_sentinel_runs():
    g = action_fanout_gate(input_flags=PRESSED, latch_a980=0x0001, repeat_9790=0x00, state_232a=0x000F)
    assert g.runs is True and g.new_latch_word == 0x0001


def test_held_non_repeatable_is_latched_unchanged():
    g = action_fanout_gate(input_flags=PRESSED, latch_a980=0x0007, repeat_9790=0x00, state_232a=0x0000)
    assert g.runs is False and g.new_latch_word == 0x0007   # A980 left exactly as-is (latched, no repeat)
