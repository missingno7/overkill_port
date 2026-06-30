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
class PostmoveBc4bResult:
    """Pure result of the shared 1010:BC4B post-move stage's deterministic ``y``/``active`` effect.

    Every object passes through BC4B after moving.  Its effect on these two slot fields is fully
    determined: ``y`` is the BCB1 clamp, and ``active`` becomes 0 exactly when the post-move X leaves
    the play box (the X-bounds death).  Per the verified BC4B invariant, the collision/contact path
    that runs afterwards sets ``logic_id`` (and the death sprite), NOT ``active`` or ``y`` -- so those
    two fields are complete here; ``contact_path_runs`` flags the slots that still enter that
    (separately-recovered) contact path, where the sprite/logic_id may yet change."""

    y_word: int
    active_word: int
    contact_path_runs: bool


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
class CollisionVariantDispatchBEC5:
    """Pure family classification for the 1010:BEC5 object-vs-object collision handler.

    BEC5 routes by the collided candidate's logic id (``variant``) to a reaction family,
    address-rooted like the C054 classifier: ``bd0d_then_a8c2`` (variants 05/06/07/08/0C
    -- deactivate the collided slot via BD0D, then A8C2 gates the BF25 counter chain vs
    the BFC7 death), ``a8c2_no_bd0d`` (variant 09 -- the same A8C2 gate without the BD0D
    prep), ``sprite_variant_2`` (variant 02 -- clear the collided slot and run BF25 with
    the entry chosen by its sprite==0033h), or ``owner_linked_or_noop`` (any other variant
    -- a runtime check of whether the collided slot is linked back to the mover).  The
    adapter owns the per-variant BD0D return address and the runtime owner-link test.
    """

    kind: str


@dataclass(frozen=True, slots=True)
class CollisionDamageChainBF25:
    """Pure result of the 1010:BF25 collision-damage counter chain.

    When a counter-variant object is hit, BF25 decrements its ``counter_20`` hit
    counter a difficulty-gated number of times (one for the BF25 entry, one at BF2D,
    then one more if DS:BEDC==1 or three more if DS:BEDC==0; other BEDC values add
    none) and dies the instant a decrement reaches zero (-> the recovered BFC7 death
    tail).  ``died`` is that zero-crossing; ``new_counter_20`` is the post-chain
    counter (0 on death, else the survivor's remaining count).  The adapter owns the
    BFC7 death dispatch and the survivor's variant/A8C2-mark tail.
    """

    new_counter_20: int
    died: bool


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


@dataclass(frozen=True, slots=True)
class CollisionHitOutcome:
    """The per-object outcome of one collision hit: the BF25 damage chain + the BFC7 death.

    Merges the two recovered collision leaves into the single result a hit produces on the
    struck object: ``new_counter_20`` (post-chain hit counter), ``died`` (a decrement reached
    zero), and ``death_transition`` -- the BFC7/C037 dying-state stamp (logic_id -> 1 + death
    sprite) when it died, else ``None``.  Survival's hit-react state (``bp+36 = 5``) and the
    A8C2 boss-group fan-out are pool/adapter side effects, not part of this per-object outcome.
    """

    new_counter_20: int
    died: bool
    death_transition: "CollisionDeathTransition | None"


@dataclass(frozen=True, slots=True)
class Bec5MovingObjectOutcome:
    """The moving object's fate when its 62F6 scan hits a candidate -- the BEC5 reaction outcome.

    This is the bridge from object_overlap_scan_62f6 (which candidate) to resolve_collision_hit
    (the damage/death) for the scanning object at SS:BP.  ``kind`` is ``"damage"`` (the BF25 hit
    chain runs on the moving object), ``"instant_death"`` (its counter_20 is zeroed and it goes
    straight to the BFC7 death), or ``"owner_or_unclassified"`` (the owner-link / no-op fallback
    this classifier does not own).  ``enter_at_bf25`` is meaningful only for ``"damage"``: the
    chain enters at BF25 (two base decrements) vs BF2D (one) -- the variant-2 sprite path.
    """

    kind: str
    enter_at_bf25: bool
