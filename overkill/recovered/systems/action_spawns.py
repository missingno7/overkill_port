"""Pure recovered action-spawn fan-out gates.

The per-frame action/spawn fan-out at ``1010:A067`` decides, before any spawn
work, whether this frame's action input is *armed* and whether it may *repeat*
while held.  Those two decisions are ordinary boolean predicates over a handful
of DS words/bytes; the original routine expresses them as a ``TEST``/``CMP``
chain whose head is (from ``SIG_FRAME_ACTION_SPAWN_FANOUT_A067``):

```text
f6 06 be 98 10   test byte [DS:98BE], 10h     ; trigger bit 4 -> action armed
74 f2            jz   ...                      ; not pressed: clear latch, return
83 3e 80 a9 00   cmp  word [DS:A980], 0        ; latch_word == 0  (fresh press)
74 0f            jz   ...
80 3e 90 97 01   cmp  byte [DS:9790], 1        ; repeat_byte_9790 == 1
74 08            jz   ...
83 3e 2a 23 0f   cmp  word [DS:232A], 0Fh      ; state_word_232a == 000Fh
74 01            jz   ...
c3              ret                            ; none held-and-repeatable: return
```

These gates are pure: they own only the comparison logic, not the DS pointer,
the ``TEST``/``CMP`` flag side effects, or the latch write-back.  The lifted A067
adapter (``overkill.gameplay.action_spawns.run_frame_action_spawn_fanout_a067``)
reads ``DS:98BE``/``DS:A980``/``DS:9790``/``DS:232A`` from DOS memory, replays the
original flag-producing instruction order for verifier compatibility, and uses
these predicates as the canonical decision.

Conservative naming: this is the "action" fan-out (the original routine fans the
held-action counters ``A970/A972/A974/A976`` into spawn scratch).  It is not yet
proven to be a specific weapon/projectile/player semantic, so the names stay at
``action`` / ``trigger`` / ``latch`` rather than any gameplay entity.
"""
from __future__ import annotations

from dataclasses import dataclass

# Bit 4 of the DS:98BE input word is the action-trigger latch input (TEST ...,10h).
ACTION_TRIGGER_INPUT_MASK = 0x10
# Once armed, the action may repeat while held when any of these hold:
ACTION_LATCH_FRESH_PRESS = 0x0000  # DS:A980 latch word still zero (first frame of a press)
ACTION_LATCH_REPEAT_BYTE = 0x0001  # DS:9790 repeat-enable byte set
ACTION_LATCH_REPEAT_STATE = 0x000F  # DS:232A state word at the repeatable sentinel


def action_trigger_is_pressed(input_flags: int) -> bool:
    """Pure ``1010:A067`` trigger gate: bit 4 of ``DS:98BE`` is the action input.

    Input: the raw ``DS:98BE`` input byte/word.  Output: whether the action is
    armed this frame.  Mirrors ``test byte [98BE], 10h`` / ``jz``.
    """

    return bool(input_flags & ACTION_TRIGGER_INPUT_MASK)


def action_latch_allows_repeat(*, latch_word: int, repeat_byte_9790: int, state_word_232a: int) -> bool:
    """Pure ``1010:A067`` repeat gate, evaluated after the trigger bit is pressed.

    Inputs are the three DS values the original ``CMP`` chain consults:
    ``latch_word`` (``DS:A980``), ``repeat_byte_9790`` (``DS:9790``) and
    ``state_word_232a`` (``DS:232A``).  The action proceeds to the spawn fan-out
    when it is a fresh press (latch still zero), repeat is enabled, or the state
    word sits at the repeatable sentinel ``000Fh`` -- the three ``jz`` exits in
    the disassembly above.
    """

    return (
        latch_word == ACTION_LATCH_FRESH_PRESS
        or repeat_byte_9790 == ACTION_LATCH_REPEAT_BYTE
        or state_word_232a == ACTION_LATCH_REPEAT_STATE
    )


@dataclass(frozen=True, slots=True)
class ActionFanoutGate:
    """The 1010:A067 entry decision: whether the action/spawn fan-out runs this frame + DS:A980's latch.

    ``runs`` gates everything downstream (the v2350/BDAC path branch and the A515/A584/A3FF/A3CA children);
    ``new_latch_word`` is DS:A980 after A067 -- the only state the entry gate itself writes.
    """

    runs: bool
    new_latch_word: int


def action_fanout_gate(input_flags: int, latch_a980: int, repeat_9790: int, state_232a: int) -> ActionFanoutGate:
    """Pure 1010:A067 entry gate: does the action/spawn fan-out run this frame, and DS:A980's write-back.

    Composes :func:`action_trigger_is_pressed` (DS:98BE bit 4) with :func:`action_latch_allows_repeat`
    (DS:A980/9790/232A): NOT pressed -> the latch clears (A980 = 0) and the fan-out is skipped; pressed and
    repeatable (fresh press / repeat byte / state sentinel) -> the latch arms (A980 = 1) and the fan-out
    runs; pressed but held-non-repeatable -> A980 is left unchanged and the fan-out is skipped.  The
    downstream spawn children own every other write, so DS:A980 after A067 is exactly ``new_latch_word``.
    """
    if not action_trigger_is_pressed(input_flags):
        return ActionFanoutGate(runs=False, new_latch_word=0x0000)
    if action_latch_allows_repeat(latch_word=latch_a980 & 0xFFFF,
                                  repeat_byte_9790=repeat_9790 & 0x00FF,
                                  state_word_232a=state_232a & 0xFFFF):
        return ActionFanoutGate(runs=True, new_latch_word=0x0001)
    return ActionFanoutGate(runs=False, new_latch_word=latch_a980 & 0xFFFF)
