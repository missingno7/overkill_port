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
from enum import Enum

from overkill.recovered.domain.object_slots import A067Result, ObjectPool
from overkill.recovered.systems.objects import native_a1c8_tail, native_a19f_tail

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


class A067FirePath(Enum):
    """Which spawn fan-out path 1010:A067 takes once the entry gate (action_fanout_gate) has armed."""

    EARLY_STATE2 = "early_state2"        # v2350<=B6 & BDAC==0 & A958==2  -> the A1C8 early tail
    EARLY_DEFAULT = "early_default"      # v2350<=B6 & BDAC==0 & A958!=2  -> the A19F early tail
    FULL_BDAC_A114 = "full_bdac_a114"    # full, BDAC==1, BE06==8         -> the A114 path
    FULL_BDAC_A515 = "full_bdac_a515"    # full, BDAC==1, BE06>0Fh        -> the A515-only tail
    FULL_FANOUT = "full_fanout"          # full                          -> A515/A584/A3FF/A3CA/A0E8


# A067 path-branch thresholds (evaluated after the gate writes DS:A980 = 1).
A067_EARLY_SCROLL_MAX = 0x00B6       # DS:2350 <= B6h (with BDAC==0) takes the early-level tails
A067_FIRE_STATE_A1C8 = 0x0002        # DS:A958 == 2 -> the A1C8 early tail, else A19F
A067_BDAC_ENABLED = 0x0001
A067_BE06_A114 = 0x0008              # full + BDAC==1: DS:BE06 == 8   -> A114
A067_BE06_A515_ONLY_OVER = 0x000F    # full + BDAC==1: DS:BE06 > 0Fh  -> A515-only tail


def a067_fire_path(scroll_2350: int, bdac: int, fire_state_a958: int, be06: int) -> A067FirePath:
    """Pure 1010:A067 path branch (after the entry gate arms): which spawn fan-out runs this frame.

    EARLY (DS:2350 <= B6h AND DS:BDAC == 0): the early-level tails -- A1C8 when the fire state DS:A958 == 2
    else A19F; these spawn WITHOUT copying the held-action counters.  Otherwise FULL (which first copies
    A970..976 -> A3A0..6): with BDAC == 1, BE06 == 8 takes the A114 path and BE06 > 0Fh the A515-only tail;
    every other full case is the A515/A584/A3FF/A3CA/A0E8 fan-out."""
    if (scroll_2350 & 0xFFFF) <= A067_EARLY_SCROLL_MAX and (bdac & 0xFFFF) == 0x0000:
        if (fire_state_a958 & 0xFFFF) == A067_FIRE_STATE_A1C8:
            return A067FirePath.EARLY_STATE2
        return A067FirePath.EARLY_DEFAULT
    if (bdac & 0xFFFF) == A067_BDAC_ENABLED:
        if (be06 & 0xFFFF) == A067_BE06_A114:
            return A067FirePath.FULL_BDAC_A114
        if (be06 & 0xFFFF) > A067_BE06_A515_ONLY_OVER:
            return A067FirePath.FULL_BDAC_A515
    return A067FirePath.FULL_FANOUT


_A067_FULL_PATHS = frozenset(
    (A067FirePath.FULL_BDAC_A114, A067FirePath.FULL_BDAC_A515, A067FirePath.FULL_FANOUT)
)


def a067_path_copies_counters(path: A067FirePath) -> bool:
    """True for the FULL paths (which copy A970..976 -> A3A0..6 before spawning); False for the EARLY tails.

    That counter copy -- a DS:A3A0 write -- is the clean produced-vs-VM witness separating EARLY from FULL.
    """
    return path in _A067_FULL_PATHS


def native_a067(pool: ObjectPool, cursor: int, *, input_98be: int, latch_a980: int, repeat_9790: int,
                state_232a: int, scroll_2350: int, bdac: int, a958: int, be06: int,
                source_index: int, source_x: int, source_y: int, read_ds_word,
                effect_pool: "ObjectPool | None" = None, cursor_a43a: int = 0,
                a970: int = 0, a972: int = 0, a976: int = 0, a974: int = 0,
                a95e: int = 0, a960: int = 0, a97e: int = 0, a96e: int = 0,
                mirror_schedule: tuple = (), side_schedule: tuple = ()) -> A067Result | None:
    """Pure WHOLE 1010:A067 entry gate + spawn dispatch -- the composed A067 fire.

    Chains the verified pieces end-to-end: the entry gate (:func:`action_fanout_gate`) decides whether the
    fire runs this frame and writes DS:A980; when armed, the path branch (:func:`a067_fire_path`) selects the
    spawn.  The EARLY tails (scroll DS:2350 <= B6h & BDAC == 0): A958 == 2 -> the A1C8 pair, else the A19F
    single, each at the A1AE muzzle from the firing object ``{source_index, source_x, source_y}``.

    The FULL fan-out (A515/A584/A3FF/A3CA/A0E8) is now COMPOSED too, via
    :func:`~overkill.recovered.systems.objects.native_a067_full_fanout` -- but ONLY when the caller supplies
    its extra inputs (``effect_pool`` + the ``a970``-family held-action counters + the A515 scan state
    ``cursor_a43a``/``a960``/``a97e`` + ``a95e``/``a96e`` + the ``mirror_schedule``/``side_schedule``).
    The FULL result rides back on :attr:`A067Result.full_result` so the caller can thread its counters
    frame-to-frame.  When those inputs are NOT supplied (``effect_pool is None``) the FULL path still
    returns ``None`` (the VM owns the frame) -- backward-compatible with callers that don't thread the
    full state yet.

    Returns an :class:`A067Result` for gate-only / EARLY / composed-FULL frames; ``None`` for an
    un-threaded FULL path, the ``a958 >= 5`` dead tail, a saturated pool, or a full pool at the first
    shot (the 7550 recycle is unmodelled) -- the caller leaves those frames to the VM."""
    gate = action_fanout_gate(input_98be, latch_a980, repeat_9790, state_232a)
    if not gate.runs:
        # not firing / held-non-repeatable: only DS:A980 is written, nothing spawns, the cursor is untouched
        return A067Result(new_a980=gate.new_latch_word, spawns=(), final_cursor=cursor & 0xFFFF,
                          ran_fanout=False)
    path = a067_fire_path(scroll_2350, bdac, a958, be06)
    if path is A067FirePath.EARLY_STATE2:
        shots = native_a1c8_tail(pool, cursor, source_index, source_x, source_y, input_98be, read_ds_word)
    elif path is A067FirePath.EARLY_DEFAULT:
        shot = native_a19f_tail(pool, cursor, source_index, source_x, source_y, read_ds_word)
        shots = (shot,) if shot is not None else None
    elif path is A067FirePath.FULL_FANOUT and effect_pool is not None:
        # the composed FULL fan-out -- only the plain FULL_FANOUT path (the FULL_BDAC_A114/A515 paths have
        # no native composition yet), and only when the caller threads its state
        from overkill.recovered.systems.objects import native_a067_full_fanout
        full = native_a067_full_fanout(
            pool, effect_pool, cursor, cursor_a43a, a970=a970, a972=a972, a976=a976, a974=a974,
            a95e=a95e, a960=a960, a97e=a97e, a958=a958, a96e=a96e, input_98be=input_98be,
            source_index=source_index, source_x=source_x, source_y=source_y,
            mirror_schedule=mirror_schedule, side_schedule=side_schedule, read_ds_word=read_ds_word)
        if full is None:
            return None  # a958 >= 5 dead tail or a saturated pool -> the VM owns this frame
        return A067Result(new_a980=gate.new_latch_word, spawns=full.spawns,
                          final_cursor=full.final_cursor, ran_fanout=True, full_result=full)
    else:
        # an un-threaded FULL_FANOUT, or a FULL_BDAC_A114/A515 path (no native composition) -> VM-owned
        return None
    if shots is None:
        return None  # full pool (the 7550 recycle path) is unmodelled -> the VM owns this frame
    shots = tuple(shots)
    return A067Result(new_a980=gate.new_latch_word, spawns=shots,
                      final_cursor=shots[-1].new_cursor, ran_fanout=True)
