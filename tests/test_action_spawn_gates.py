"""VM-free unit tests for the pure 1010:A067 action-spawn fan-out gates.

Pins the two predicates promoted out of the lifted A067 adapter into the pure
layer (``overkill.recovered.systems.action_spawns``):

- ``action_trigger_is_pressed`` -- ``test byte [98BE], 10h`` (bit 4 = armed),
- ``action_latch_allows_repeat`` -- the ``CMP [A980],0`` / ``CMP [9790],1`` /
  ``CMP [232A],0Fh`` repeat chain.

The demo-level confirmation is the A067 hook replaying the instruction-shaped
flag sequence alongside these predicates, exercised by the demo-replay suite.
"""
from __future__ import annotations

from overkill.recovered.systems.action_spawns import (
    ACTION_LATCH_FRESH_PRESS,
    ACTION_LATCH_REPEAT_BYTE,
    ACTION_LATCH_REPEAT_STATE,
    ACTION_TRIGGER_INPUT_MASK,
    action_latch_allows_repeat,
    action_trigger_is_pressed,
)


def test_trigger_gate_is_input_bit_4():
    assert ACTION_TRIGGER_INPUT_MASK == 0x10
    assert action_trigger_is_pressed(0x10) is True
    assert action_trigger_is_pressed(0x00) is False
    # Other input bits never arm the action on their own.
    for other in (0x01, 0x02, 0x04, 0x08, 0x20, 0x40, 0x80):
        assert action_trigger_is_pressed(other) is False
    # Bit 4 set among other bits still arms it.
    assert action_trigger_is_pressed(0xFF) is True
    assert action_trigger_is_pressed(0xEF) is False  # every bit but 4


def test_repeat_gate_each_disjunct_opens_alone():
    # Fresh press: latch word still zero.
    assert action_latch_allows_repeat(
        latch_word=ACTION_LATCH_FRESH_PRESS, repeat_byte_9790=0x99, state_word_232a=0x1234
    ) is True
    # Repeat-enable byte set.
    assert action_latch_allows_repeat(
        latch_word=0x0001, repeat_byte_9790=ACTION_LATCH_REPEAT_BYTE, state_word_232a=0x1234
    ) is True
    # State word at the repeatable sentinel.
    assert action_latch_allows_repeat(
        latch_word=0x0001, repeat_byte_9790=0x99, state_word_232a=ACTION_LATCH_REPEAT_STATE
    ) is True


def test_repeat_gate_closed_when_no_disjunct_holds():
    assert action_latch_allows_repeat(
        latch_word=0x0001, repeat_byte_9790=0x00, state_word_232a=0x000E
    ) is False
    assert action_latch_allows_repeat(
        latch_word=0xFFFF, repeat_byte_9790=0x02, state_word_232a=0x0010
    ) is False
