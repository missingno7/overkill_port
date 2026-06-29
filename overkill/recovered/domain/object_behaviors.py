"""Pure object-behavior domain records recovered from dispatcher hooks."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObjectDeactivateDispatchDecision:
    """Pure classification for the recovered 1010:C054 deactivate dispatcher.

    ``kind`` is intentionally narrow and address-rooted.  It names the observed
    dispatcher families without claiming a complete enemy/boss archetype model.
    ``ax_script`` is populated only for the family where C054 selects an AX
    script address for the caller's follow-up tail.
    """

    kind: str
    ax_script: int | None = None


@dataclass(frozen=True, slots=True)
class ObjectLogicDispatchAA2B:
    """Pure first-level object-logic dispatch recovered from 1010:AA2B.

    AA2B selects the per-frame object handler from the slot's ``draw_layer``
    (SS:[BP+16]) through the CS:AA36 jump table.  ``kind`` is the address-rooted
    handler name for the eight draw layers (0-7); draw layers 2 and 4 share the
    EFAE second-level family dispatcher.  Like the C054 classifier this names the
    routing without claiming a complete handler model; the adapter owns the CS:AA36
    table read, the ``BX = layer*2`` index, and the IP jump.
    """

    kind: str


@dataclass(frozen=True, slots=True)
class Ab10Update:
    """Pure result of the 1010:AB10 per-frame object update (logic_id=6 path).

    The object deactivates when the level frame phase (DS:2384) or the global
    disable counter (DS:A47C) has advanced to ``0003h``; otherwise it samples its
    animation frame and view-relative position. ``deactivate`` true means the slot
    is cleared (active=0) and the other fields are unused. The adapter owns the DOS
    reads + the original CMP/ADD flag replay; this owns the gameplay decision."""

    deactivate: bool
    sprite: int = 0
    x: int = 0
    y: int = 0


@dataclass(frozen=True, slots=True)
class Ae09Update:
    """Pure result of the 1010:AE09 per-frame object update (EFAE logic_id 0Ch path).

    A countdown timer (slot ``substate``) decrements while non-zero, clearing the
    ``direction_or_step`` word on the frame it reaches zero. The object steps left
    (``decrement_x`` -> ``x -= 2``) on the frame the timer is zero or has just
    expired, and its outgoing sprite is ``direction_or_step + 28h``. The adapter owns
    the slot reads/writes and the AF22 + AD60 tail (whose first ops overwrite this
    routine's now-dead flags); this owns the timer/step/sprite decision."""

    substate: int
    direction_or_step: int
    decrement_x: bool
    sprite: int


@dataclass(frozen=True, slots=True)
class Ae09MovementStep:
    """Pure per-slot movement result of the whole 1010:AE09 behavior (logic_id 0Ch).

    Composes the :class:`Ae09Update` timer/step decision with the AF22 3-pixel direction
    step that AE09 tails into, giving the slot's post-frame movement fields: the decremented
    ``substate`` timer, the ``direction_or_step`` (cleared on expiry), the outgoing
    ``sprite_or_state``, and the stepped ``x_word`` / ``y_word``.  The AD60 bounds tail and
    the BD17 deactivation / global side-effects do NOT touch these five fields (AD60 only
    sets the slot ``active`` word and global counters), so this is a clean native producer
    for the movement half of the object update, verifiable produced-vs-VM at AE09's return."""

    substate: int
    direction_or_step: int
    sprite_or_state: int
    x_word: int
    y_word: int


@dataclass(frozen=True, slots=True)
class Ae09SlotUpdate:
    """Pure WHOLE per-slot result of the 1010:AE09 behavior (logic_id 0Ch): movement + active.

    Extends :class:`Ae09MovementStep` (timer/step + AF22 move) with the slot's ``active_word`` after
    the AD60 bounds/tile tail: AD60 deactivates the slot (BD17 -> ``active = 0``) when the moved object
    leaves the play bounds, OR -- for the tile-probe family -- when the tile one map row below has
    class 1; otherwise it survives (``active`` unchanged).  This is the complete native slot transform
    for an AE09 object EXCEPT the BD17 global counter/spawn writes (separate state, not slot fields).
    The template for the per-logic-id native dispatch: movement primitive + bounds/tile -> next slot."""

    substate: int
    direction_or_step: int
    sprite_or_state: int
    x_word: int
    y_word: int
    active_word: int


@dataclass(frozen=True, slots=True)
class Aba3Update:
    """Pure result of the 1010:ABA3 tracked-object follower probe (reached from AD04).

    When the level frame phase (DS:2384) has advanced to ``0003h`` the follower takes
    the ABC0 branch (the adapter routes control there); otherwise its outgoing sprite
    is the scroll frame (DS:233C) + ``14h`` and the adapter runs the AC81 collision
    tail. The adapter owns the A42E tracker-pointer store and the AC81 CF/IP
    continuations; this owns the phase-gate decision and the sprite formula."""

    branch_abc0: bool
    sprite: int = 0


@dataclass(frozen=True, slots=True)
class B73ETargetReachedResolution:
    """Pure 4-way dispatch for B73E once an object is already at its target.

    Recovered from the B7BD/B808 tail.  After the object reaches its waypoint and
    the optional B800 formation spawn, B73E chooses how to continue from three
    globals.  ``kind`` is one of:

    - ``"reset_target_check_2324"``: low ``DS:A47E`` -> reset the target row with
      the B7C7 ``DS:2324`` guard.
    - ``"reset_target_direct"``: low ``DS:2340`` counter -> reset the target row
      directly through B7CE.
    - ``"postmove"``: ``DS:232E`` is not the ``003Fh`` sentinel -> join the shared
      BC4B post-move tail.
    - ``"waypoint_loop"``: otherwise -> enter the B82D waypoint-table loop.

    Names the branch decision without owning the reset side effects, the BC4B
    tail, or the waypoint loop body.
    """

    kind: str

@dataclass(frozen=True, slots=True)
class ObjectBoundsTileDecision:
    """Pure classification for the recovered 1010:AD60 bounds/tile tail.

    AD60 first tests the moved object against the play-field bounds, then decides
    whether the object is eligible for the under-object tile probe.  ``kind`` is
    one of:

    - ``"deactivate"``: the object left the play-field box and AD60 routes it to
      the BD17 deactivate tail.
    - ``"skip"``: the object stayed in bounds but is not a tile-probing family
      (wrong draw layer, non-probing logic id, or the BDAC probe-suppress flag),
      so AD60 just returns.
    - ``"tile_probe"``: an in-bounds probing family with BDAC clear, so AD60 runs
      the 5073/505B tile probe tail.

    This names the AD60 branch decision without owning the deactivate side
    effects, the tile-probe sampling, or any DOS memory.
    """

    kind: str

@dataclass(frozen=True, slots=True)
class BossGroupSlotTransition:
    """Pure state update performed by the recovered C194 boss-part helper.

    C194 stores the previous logic id before switching a sibling boss part into
    the shared death/transition state.  This record names those final field
    values without knowing DOS memory, stack scratch, or debug globals.
    """

    previous_logic_id: int
    logic_id: int
    transition_latch: int
    sprite_or_state: int

