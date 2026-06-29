"""Pure recovered input decode -- the canonical keyboard -> button-flags rule.

The per-frame input poller ``1010:0162`` turns the raw keyboard state into the
button bitfield ``DS:98BE`` that the rest of the game reads (the A067 action gate,
the menu selectors, the player FSM).  Its keyboard path is a pure decode of two
inputs:

* the *control map* -- eight scancodes the game stores at ``DS:213E`` (default) or
  ``DS:2146`` (alternate, ``DS:[0010]==2``).  The shipped default map is
  ``[00,00,Z(2C),Space(39),Q(10),A(1E),O(18),P(19)]`` -- OVERKILL moves with
  Q/A/O/P and fires with Z/Space.
* the *key-state table* -- the 256-byte INT 9 scancode->pressed table at ``DS:98C4``
  (byte non-zero / bit 0 set means the key is down).

``1010:017E`` packs the eight control keys into the byte MSB-first (the first map
entry lands in bit 7, the eighth in bit 0) via its ``SHR``/``RCL`` loop; ``0162``
then ORs in the six hardwired direction/fire keys (arrows + Space + Tab).  The
resulting bits are, low to high: right, left, down, up, fire, secondary-fire.

This module is the single definition of that rule.  The lifted VM hooks
(``overkill.input_menu.run_input_poll_0162`` / ``pack_keyboard_poll_bits_017e``)
compute the same bits through these functions while replaying the original
register/flag epilogue for verifier compatibility, and the native runtime builds
its button flags straight from a host key-state table -- no VM, one rule.
"""
from __future__ import annotations

from typing import Iterable, Sequence

# DS:98BE button bits (low -> high).  Bits 0..3 are the four directions, bit 4 the
# primary fire/action (the A067 trigger gate tests this), bit 5 the secondary fire.
INPUT_RIGHT = 0x01
INPUT_LEFT = 0x02
INPUT_DOWN = 0x04
INPUT_UP = 0x08
INPUT_FIRE = 0x10
INPUT_SECONDARY = 0x20

# The six hardwired keys 0162 ORs in after the configurable pack: (scancode, bit).
# These are the IBM PC arrow cluster plus Space (fire) and Tab (secondary), and they
# always work regardless of the control map.
FIXED_DIRECTION_KEYS: tuple[tuple[int, int], ...] = (
    (0x0F, INPUT_SECONDARY),  # Tab    -> secondary fire
    (0x39, INPUT_FIRE),       # Space  -> fire
    (0x48, INPUT_UP),         # Up
    (0x50, INPUT_DOWN),       # Down
    (0x4B, INPUT_LEFT),       # Left
    (0x4D, INPUT_RIGHT),      # Right
)

# The shipped default control map (DS:213E): the eight scancodes 017E packs MSB-first.
# Entries 0/1 are unused (scancode 0 is never pressed), so only the lower six bits of
# the pack are live; the alternate map (DS:2146) has the same shape.
DEFAULT_CONTROL_MAP: tuple[int, ...] = (0x00, 0x00, 0x2C, 0x39, 0x10, 0x1E, 0x18, 0x19)

CONTROL_MAP_KEYS = 8  # 0162 always packs eight control entries (CX=8)


def pack_control_map_bits(control_map: Sequence[int], key_state: Sequence[int]) -> int:
    """Pack a control map's down-bits MSB-first, the pure core of ``1010:017E``.

    For each scancode in ``control_map`` (first entry -> highest bit) shift the key's
    pressed bit (``key_state[scancode] & 1``) into the accumulator, mirroring the
    ``SHR AL,1`` / ``RCL [98BE],1`` loop.  The result is an 8-bit byte; an
    eight-entry map fills it exactly (and 017E's eight ``RCL``s rotate out whatever
    was in the byte before, so the prior value never leaks).
    """
    flags = 0
    for scancode in control_map:
        flags = ((flags << 1) | (key_state[scancode] & 1)) & 0xFF
    return flags


def decode_keyboard_input_flags(control_map: Sequence[int], key_state: Sequence[int]) -> int:
    """The full ``1010:0162`` keyboard decode: control-map pack OR the six fixed keys.

    Returns the ``DS:98BE`` button byte the game consumes.  ``control_map`` is the
    eight-scancode map at DS:213E/2146; ``key_state`` is the 256-byte DS:98C4 INT 9
    table indexed by scancode.  The fixed keys use a whole-byte non-zero test (as the
    original ``CMP byte,0`` does), the pack uses bit 0 -- both kept faithful.
    """
    flags = pack_control_map_bits(control_map, key_state)
    for scancode, mask in FIXED_DIRECTION_KEYS:
        if key_state[scancode] != 0:
            flags |= mask
    return flags


def key_state_from_pressed(pressed: Iterable[int], size: int = 0x100) -> tuple[int, ...]:
    """Build a native key-state table from a set of pressed scancodes.

    The native input source replaces the INT 9 keyboard ISR: instead of the VM's
    DS:98C4 table it produces this ``size``-entry table (1 = down, 0 = up) from the
    host's set of pressed scancodes, which ``decode_keyboard_input_flags`` then turns
    into the same button byte the VM would compute.
    """
    state = [0] * size
    for scancode in pressed:
        if 0 <= scancode < size:
            state[scancode] = 1
    return tuple(state)
