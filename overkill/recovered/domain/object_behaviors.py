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
class B9f0MovementResult:
    """Pure result of the 1010:B9F0 movement half -- the slot at the BC4B handoff (logic_id 0x14).

    B9F0's four paths (Path A sprite-refresh; the reached-target BA5A helper or plain sprite-refresh;
    the overshoot 5E42 step; the 5DB2 target seek) all tail-jump to BC4B.  Records the six handoff
    fields; ``substate``/``active`` are unchanged by the movement half (BC4B owns the post-move
    y/active).  Compose with ``object_postmove_bc4b`` for the slot's post-move y/active.
    ``move_step_error`` is the 5E42 Bresenham accumulator (record byte +2E) -- only the BA5A helper
    and the overshoot-step paths advance it (each makes its own 5E42 call); the other paths leave it
    unwritten in the real ASM, so this carries the ORIGINAL input value through unchanged for them."""

    substate: int
    direction_or_step: int
    sprite_or_state: int
    x_word: int
    y_word: int
    active_word: int
    move_step_error: int


@dataclass(frozen=True, slots=True)
class B86dMovementResult:
    """Pure result of the 1010:B86D movement half -- the slot at the BC4B handoff (logic_id 0x1D).

    B86D's three branches (B8F8 edge-steer via 5E1B->5E42; the A7A0 phase block via the 5DB2 target
    seek; the fall-through formation drift) all tail-jump to the shared BC4B post-move stage.  This
    records the six fields the movement half leaves at that handoff; ``substate`` and ``active`` are
    unchanged by the movement half (BC4B then owns the y clamp / X-bounds death).  Compose with
    ``object_postmove_bc4b`` for the slot's post-move y/active.  ``move_step_error`` is the 5E42
    Bresenham accumulator (record byte +2E) -- only the edge-steer branch advances it (its own 5E42
    call computes a new value); the other two branches leave it unwritten in the real ASM, so this
    carries the ORIGINAL input value through unchanged for them, not a guessed/zeroed one."""

    substate: int
    direction_or_step: int
    sprite_or_state: int
    x_word: int
    y_word: int
    active_word: int
    move_step_error: int


@dataclass(frozen=True, slots=True)
class Aed8SlotUpdate:
    """Pure WHOLE per-slot result of the 1010:AED8 behavior (EFAE logic_id 2): step + contact + active.

    AED8 decrements the slot's substate timer, steps it 8px in its direction (AEE4), runs the B250
    overlap-contact selector against the DS:237E/2380 view box, then joins the AD60 bounds/tile tail:
    no contact -> AD5A (x += DS:A278) then AD60; contact -> ADC9 (x = FFFFh) then AD60.  AD60 sets the
    slot ``active`` word (out-of-bounds, or the tile one row below has class 1).  AEE4/AD60 do not touch
    the sprite or direction, so this records only the four fields AED8 changes.  The B250 fan-out 9E19
    status side effects and the timer-expired (substate->0) death are out of this transform's scope."""

    substate: int
    x_word: int
    y_word: int
    active_word: int


@dataclass(frozen=True, slots=True)
class B24dSlotUpdate:
    """Pure WHOLE per-slot result of the 1010:B24D behavior (EFAE logic_id 0x0B): steer + contact + active.

    B24D calls the 5E42 delta-steer (updates direction +06, move_step_error +2E, x +02, y +04), then runs
    the same B250 overlap-contact selector against the DS:237E/2380 view box and joins the shared AD5A/
    ADC9 -> AD60 tail: no contact -> AD5A (x += DS:A278) then AD60; contact -> ADC9 (x = FFFFh) then AD60.
    AD60 sets the slot ``active`` word (out of bounds; logic_id 0x0B is not a tile-probe family).  The
    substate and sprite are untouched.  The in-box contact's 9E19 fan-out (x1/3/5 by difficulty) is a
    separate global side effect, out of this slot transform's scope."""

    direction_or_step: int
    x_word: int
    y_word: int
    active_word: int
    move_step_error: int


@dataclass(frozen=True, slots=True)
class B2cdSlotUpdate:
    """Pure WHOLE per-slot result of the 1010:B2CD behavior (EFAE logic_id 0x12): waypoint seek + sprite.

    B2CD reads the slot's current waypoint (the +36 pointer -> {X, Y} in DS), seeks toward it with 5DB2
    (target X offset by +0x20, mode 2 when level 0 / BDAC==1 else 1), then sets the sprite from the seek
    direction plus a level/BDAC/scroll-dependent constant (B304..B3B0), and joins the BC4B post-move.
    Only direction/sprite/x/y change here; substate/active are untouched (BC4B owns the post-move).  The
    reached-waypoint advance loop (B2FF: 5DB2 blocked -> advance the +36 pointer by 4 and re-seek toward
    the next waypoint) IS modelled -- ``waypoint_ptr`` is the (possibly advanced) +36 pointer to write
    back.  Only the messy scroll==0xE52/unknown-level sprite fall-throughs stay out of scope (-> None)."""

    direction_or_step: int
    sprite_or_state: int
    x_word: int
    y_word: int
    waypoint_ptr: int       # the +0x36 waypoint pointer after the advance loop (B2FF write-back)


@dataclass(frozen=True, slots=True)
class B1b0Update:
    """Pure WHOLE per-slot result of the 1010:B1B0 behavior (EFAE logic_id 0x0A): the two-state seeker.

    B1B0 always sets the slot sprite to ``DS:2328 + 6Dh``, then branches on the slot state (+1C):
    STATE 0 (acquire) 4px-aligns X/Y and seeks the view-centre (5DB2 mode 2); if it moved it joins the
    AD60 bounds tail, else (reached) it decrements DS:A97E and runs the B15A target scan -- no candidate
    -> ADC9 deactivate; found -> stores the target pointer (+30), flips to state 1, DS:A97E += 1, AD60.
    STATE 1 (follow) validates the acquired target (active, X <= DCh, logic != 1); valid -> 5E1B delta +
    5E42 steer toward it (AD5A compact); invalid -> back to state 0 (no move, AD5A).  ``state`` is the
    slot +1C word (the coverage 6-tuple's ``substate``); ``acquired_target_ptr`` is the +30 word;
    ``a97e``/``cursor_a43a`` are the DS:A97E counter + DS:A43A scan cursor after (the global side effects,
    unchanged in state 1 and on the moved path); ``tail`` names which post-move tail B1B0 jmps to (a code,
    not a VM address).  move_step_error (+2E, updated by 5E42) is out of scope, like B24D/B86D."""

    state: int
    direction_or_step: int
    sprite_or_state: int
    x_word: int
    y_word: int
    active_word: int
    acquired_target_ptr: int
    a97e: int
    cursor_a43a: int
    tail: str


@dataclass(frozen=True, slots=True)
class Ae7dSlotUpdate:
    """Pure WHOLE per-slot result of the 1010:AE7D behavior (EFAE logic_id 0x05): a scroll-left mover.

    AE7D dies at y==0 (ADC9); else moves X left 4px and, unless the slot is 16px-aligned in Y with a
    clear render mode (BDAC) and the tile one probe-row below has class 1, also steers up (direction 7,
    Y -= 4).  The sprite is direction + 8; then AD5A (X += DS:A278) and the AD60 bounds/tile tail set
    ``active`` (0x05 is a tile-probe family).  substate is untouched."""

    direction_or_step: int
    sprite_or_state: int
    x_word: int
    y_word: int
    active_word: int


@dataclass(frozen=True, slots=True)
class Ae2cSlotUpdate:
    """Pure WHOLE per-slot result of the 1010:AE2C behavior (EFAE logic_id 0x06): a scroll-left mover.

    The sibling of AE7D: dies at y==0xC8 (ADC9); else moves X left 4px and, unless the slot sits at Y
    mod 16 == 8 with a clear render mode (BDAC) and the tile at the 5073 probe + 0xE has class 1
    (-> direction 0, no Y move), it steers down (direction 1, Y += 4).  The sprite is
    ``((DS:2326 << 2) & 8) + direction + 8``; then AD5A (X += DS:A278) and the AD60 bounds/tile tail
    (0x06 is a tile-probe family) set ``active``.  substate is untouched."""

    direction_or_step: int
    sprite_or_state: int
    x_word: int
    y_word: int
    active_word: int


@dataclass(frozen=True, slots=True)
class B86dDriftUpdate:
    """Pure result of the 1010:B86D *fall-through* (formation-drift) path's slot writes.

    The common B86D path (not the B8F8 edge-steer, not the A7A0 phase block) moves the slot
    horizontally by the negated global vertical delta (DS:2342), nudges +1 when the DS:2328
    phase word is ``0007h``, and sets the outgoing sprite from the delta's sign.  Only these two
    slot fields change; the formation-spawn (CALL 7476) is a separate global side effect, and the
    shared BC4B post-move tail is the next stage (verified separately).  ``x_word`` is the slot's
    X after the drift; ``sprite_or_state`` the outgoing sprite."""

    x_word: int
    sprite_or_state: int


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

