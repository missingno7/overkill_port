"""Pure collision-domain records for recovered OVERKILL systems."""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.domain.directions import DirectionComponent


@dataclass(frozen=True, slots=True)
class ViewContactCenter:
    """Prepared center words used by the 1010:8331 contact-window test."""

    x_word: int
    y_word: int


@dataclass(frozen=True, slots=True)
class RectContactResult:
    """Pure result of an object-vs-view rectangle/contact test."""

    hit: bool




@dataclass(frozen=True, slots=True)
class PostMoveYClampResult:
    """Pure result for the recovered 1010:BCB1 post-move Y clamp.

    The original clamps the current object Y coordinate into the signed
    inclusive 0..00C0h gameplay window.  The adapter owns the exact CMP/flags
    sequence and optional near-return behavior.
    """

    y_word: int
    changed: bool


@dataclass(frozen=True, slots=True)
class ProbePoint:
    """Pure point/probe words used by object-centered collision scans."""

    x_word: int
    y_word: int


@dataclass(frozen=True, slots=True)
class TileSweepPlan:
    """Pure direction decomposition for the recovered B00D tile-sweep table.

    The original routine dispatches by direction index into four cardinal tile
    response bodies and four diagonal CALL+fallthrough compositions.  This pure
    record names only the gameplay order; ASM return addresses stay in the
    adapter/hook layer.
    """

    components: tuple[DirectionComponent, ...]


@dataclass(frozen=True, slots=True)
class PostMoveContactWindow:
    """Pure AA71/BC4B post-move contact-window inputs.

    The original helper compares the current object slot against the live
    view/contact globals.  ``final_boss_narrow_x`` names the DS:A8C2 == 1
    mode that narrows only the X window; the adapter owns the original globals
    and flags.
    """

    view_x_word: int
    y_guard_word: int
    final_boss_narrow_x: bool


@dataclass(frozen=True, slots=True)
class ObjectOverlapScanDecision:
    """Pure result for one AC97 object-overlap slot candidate.

    ``overlaps`` means the current probe point and link/type gates matched far
    enough that AC97 reaches its ACD9 reaction decision.  ``actionable`` names
    the recovered type-4/type-5 family whose reaction must continue at ACD9;
    non-actionable overlaps are consumed by the lifted loop and scanning
    continues, exactly like the original ACD9 -> ACD2 tail.
    """

    overlaps: bool
    actionable: bool


@dataclass(frozen=True, slots=True)
class CollisionDeathTransition:
    """Pure slot transition stamped by the 1010:BFC7 collision-death tail's C037 end.

    When a type-1/2 object dies by collision, BFC7 finishes by recording the old
    ``logic_id`` as ``previous_logic_id``, forcing ``logic_id`` to the dying-state
    ``1``, clearing the ``transition_latch``, and selecting the death
    ``sprite_or_state`` from the object type via the C037 table (type 1 -> 0, type
    2 -> 3).  The adapter owns the BFC7 orchestration and the unverified-type tail;
    this owns the four transition field values.
    """

    previous_logic_id: int
    logic_id: int
    transition_latch: int
    sprite_or_state: int
