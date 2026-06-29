"""Unit tests for the pure input decode (overkill.recovered.systems.input)."""
from __future__ import annotations

from overkill.recovered.systems.input import (
    DEFAULT_CONTROL_MAP,
    INPUT_DOWN,
    INPUT_FIRE,
    INPUT_LEFT,
    INPUT_RIGHT,
    INPUT_SECONDARY,
    INPUT_UP,
    decode_keyboard_input_flags,
    key_state_from_pressed,
    pack_control_map_bits,
)


def _state(*pressed: int):
    return key_state_from_pressed(pressed)


def test_pack_is_msb_first():
    # First map entry -> bit 7, last -> bit 0.  A one-hot map proves the bit position.
    for i, scancode in enumerate((0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17)):
        cmap = (0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17)
        flags = pack_control_map_bits(cmap, _state(scancode))
        assert flags == (1 << (7 - i)), (i, hex(flags))


def test_pack_uses_bit0_only():
    # key_state value 2 has bit 0 clear -> not packed; value 3 has bit 0 set -> packed.
    cmap = (0x20, 0x21)
    ks = [0] * 0x100
    ks[0x20] = 2  # bit0 clear
    ks[0x21] = 3  # bit0 set
    assert pack_control_map_bits(cmap, ks) == 0b01  # only the second entry (bit 0)


def test_default_map_move_and_fire_bits():
    # The shipped map: Q/A/O/P -> up/down/left/right bits, Z/Space -> secondary/fire.
    Q, A, O, P, Z, SPACE = 0x10, 0x1E, 0x18, 0x19, 0x2C, 0x39
    assert decode_keyboard_input_flags(DEFAULT_CONTROL_MAP, _state(P)) & INPUT_RIGHT
    assert decode_keyboard_input_flags(DEFAULT_CONTROL_MAP, _state(O)) & INPUT_LEFT
    assert decode_keyboard_input_flags(DEFAULT_CONTROL_MAP, _state(A)) & INPUT_DOWN
    assert decode_keyboard_input_flags(DEFAULT_CONTROL_MAP, _state(Q)) & INPUT_UP
    assert decode_keyboard_input_flags(DEFAULT_CONTROL_MAP, _state(SPACE)) & INPUT_FIRE
    assert decode_keyboard_input_flags(DEFAULT_CONTROL_MAP, _state(Z)) & INPUT_SECONDARY


def test_fixed_arrow_keys_always_work():
    # Even with an empty control map, the hardwired arrows/Space/Tab set their bits.
    empty = (0, 0, 0, 0, 0, 0, 0, 0)
    UP, DOWN, LEFT, RIGHT, SPACE, TAB = 0x48, 0x50, 0x4B, 0x4D, 0x39, 0x0F
    assert decode_keyboard_input_flags(empty, _state(UP)) == INPUT_UP
    assert decode_keyboard_input_flags(empty, _state(DOWN)) == INPUT_DOWN
    assert decode_keyboard_input_flags(empty, _state(LEFT)) == INPUT_LEFT
    assert decode_keyboard_input_flags(empty, _state(RIGHT)) == INPUT_RIGHT
    assert decode_keyboard_input_flags(empty, _state(SPACE)) == INPUT_FIRE
    assert decode_keyboard_input_flags(empty, _state(TAB)) == INPUT_SECONDARY


def test_fixed_and_control_combine_with_or():
    # Space (fire) appears in both the default map (entry 3) and the fixed keys; the
    # decode is the OR, so pressing it sets exactly the fire bit and nothing spurious.
    SPACE = 0x39
    assert decode_keyboard_input_flags(DEFAULT_CONTROL_MAP, _state(SPACE)) == INPUT_FIRE


def test_no_keys_no_flags():
    assert decode_keyboard_input_flags(DEFAULT_CONTROL_MAP, _state()) == 0


def test_diagonal_plus_fire():
    # Native source: hold Up+Right+Fire -> the three bits, OR-combined.
    UP, RIGHT, SPACE = 0x48, 0x4D, 0x39
    flags = decode_keyboard_input_flags(DEFAULT_CONTROL_MAP, _state(UP, RIGHT, SPACE))
    assert flags == (INPUT_UP | INPUT_RIGHT | INPUT_FIRE)
