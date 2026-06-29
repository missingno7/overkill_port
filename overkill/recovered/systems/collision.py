"""Pure recovered collision systems.

No CPU, memory, DOS segment, or hook state is allowed here.  The functions in
this module are the first portable slice that a future native source port can
reuse directly.
"""
from __future__ import annotations

from overkill.recovered.domain.collision import (
    CollisionDamageChainBF25,
    CollisionDeathTransition,
    CollisionVariantDispatchBEC5,
    ObjectOverlapScanDecision,
    PostMoveContactWindow,
    PostMoveYClampResult,
    ProbePoint,
    RectContactResult,
    TileSweepPlan,
    ViewContactCenter,
)
from overkill.recovered.domain.directions import direction8
from overkill.recovered.domain.coords import i16, u16
from overkill.recovered.domain.object_slots import ObjectSlotRecord

CONTACT_HALF_EXTENT = 0x10
PLAYER_HAZARD_SCAN_REQUIRED_GATE = 0x0001
PLAYER_HAZARD_SCAN_REQUIRED_FLAG = 0x0001
PLAYER_HAZARD_SCAN_REQUIRED_CLASS = 0x0004
PLAYER_HAZARD_LOGIC_MIN = 0x0082
PLAYER_HAZARD_LOGIC_MAX = 0x0094

# 1010:AC97 object-overlap scan constants.  This scan uses the same 16-pixel
# centered window as the BDE3 hazard scan, but its candidate/action gates are
# different and should stay named separately.
OBJECT_OVERLAP_SCAN_REQUIRED_FLAG = 0x0001
OBJECT_OVERLAP_INACTIVE_LOGIC_ID = 0x0001
OBJECT_OVERLAP_ACTIONABLE_CLASSES = frozenset((0x0004, 0x0005))

# 1010:AA71 post-move contact-window constants.  This helper shares the wider
# +/- style window shape with other contact tests, but its Y compare is against
# DS:2380 and its X compare uses unsigned bounds against DS:237E.  Final-boss
# mode (DS:A8C2 == 1) narrows only the X span.
POSTMOVE_CONTACT_Y_UPPER_BIAS = 0x0018
POSTMOVE_CONTACT_Y_SPAN = 0x002C
POSTMOVE_CONTACT_X_NORMAL_UPPER_BIAS = 0x0018
POSTMOVE_CONTACT_X_NORMAL_SPAN = 0x002C
POSTMOVE_CONTACT_X_BOSS_UPPER_BIAS = 0x0008
POSTMOVE_CONTACT_X_BOSS_SPAN = 0x000C

# 1010:BCB1 post-move Y clamp constants.
POSTMOVE_Y_MIN = 0x0000
POSTMOVE_Y_MAX = 0x00C0


def clamp_postmove_y_bcb1(y_word: int) -> PostMoveYClampResult:
    """Pure source-like form of the 1010:BCB1 signed Y clamp.

    BCB1 constrains the current object Y coordinate into the signed inclusive
    0..00C0h gameplay window.  The adapter replays the original CMP sequence so
    CPU-visible flags still match the ASM oracle.
    """
    y = i16(y_word)
    if y > POSTMOVE_Y_MAX:
        return PostMoveYClampResult(y_word=POSTMOVE_Y_MAX, changed=True)
    if y < 0:
        return PostMoveYClampResult(y_word=POSTMOVE_Y_MIN, changed=True)
    return PostMoveYClampResult(y_word=u16(y_word), changed=False)


# 1010:BC4B post-move X-bounds death.  After the Y clamp, BC4B deactivates the object (-> BD17,
# active=0) when its post-move X leaves the play box.  The precise lower bound -C0h applies unless the
# global gate DS:A47C is set or the logic id is a wide-box exempt family, which use the tighter -14h;
# the upper bound F0h is shared.  (The collision path that BC4B runs afterwards sets logic_id, not
# active, so ``active == 0`` at BC4B's return is exactly this X-bounds death.)
POSTMOVE_X_BOUND_UPPER = 0x00F0
POSTMOVE_X_BOUND_LOWER_PRECISE = -0x00C0
POSTMOVE_X_BOUND_LOWER_WIDE = -0x0014
POSTMOVE_X_BOUND_WIDE_LOGIC_IDS = frozenset((0x0000, 0x0048, 0x0026, 0x0086, 0x0028, 0x0029, 0x0034))


def object_postmove_x_bounds_deactivates_bc4b(x_word: int, global_disable: int, logic_id: int) -> bool:
    """True iff 1010:BC4B deactivates the object for leaving the X play box (BC52..BC9x -> BD17).

    ``x_word`` is the signed post-move X.  The precise lower bound (-C0h) applies unless the global
    gate ``global_disable`` (DS:A47C) is non-zero or ``logic_id`` is a wide-box exempt family (which
    use -14h); the upper bound (F0h) is shared.  This is the BC4B slot effect on ``active``; the
    collision path that follows it sets ``logic_id`` instead, so it does not affect ``active``."""
    wide = (global_disable & 0xFFFF) != 0 or (logic_id & 0xFFFF) in POSTMOVE_X_BOUND_WIDE_LOGIC_IDS
    lower = POSTMOVE_X_BOUND_LOWER_WIDE if wide else POSTMOVE_X_BOUND_LOWER_PRECISE
    sx = i16(x_word)
    return sx < lower or sx >= POSTMOVE_X_BOUND_UPPER


def word_inside_signed_center_window(
    value_word: int,
    center_word: int,
    *,
    half_extent: int = CONTACT_HALF_EXTENT,
    include_edges: bool,
) -> bool:
    """Return whether ``value_word`` is inside a signed centered word window.

    This is the source-like predicate behind several recovered rectangle tests.
    The exact 8086 flag/register choreography remains in adapters; this pure
    function deliberately returns only the portable gameplay decision.
    """
    upper = u16(center_word + half_extent)
    lower = u16(upper - half_extent * 2)
    value = i16(value_word)
    lower_i = i16(lower)
    upper_i = i16(upper)
    if include_edges:
        return lower_i <= value <= upper_i
    return lower_i < value < upper_i


def slot_contains_probe_point(
    slot: ObjectSlotRecord,
    point: ProbePoint,
    *,
    half_extent: int = CONTACT_HALF_EXTENT,
    include_edges: bool,
) -> bool:
    """Return whether a probe point lies inside an object's centered window."""
    return word_inside_signed_center_window(
        point.x_word,
        slot.x_word,
        half_extent=half_extent,
        include_edges=include_edges,
    ) and word_inside_signed_center_window(
        point.y_word,
        slot.y_word,
        half_extent=half_extent,
        include_edges=include_edges,
    )


def view_contact_rect_test(
    slot: ObjectSlotRecord,
    center: ViewContactCenter,
    *,
    half_extent: int = CONTACT_HALF_EXTENT,
) -> RectContactResult:
    """Pure source-like form of the 1010:8331 signed rectangle test."""
    return RectContactResult(
        slot_contains_probe_point(
            slot,
            ProbePoint(x_word=center.x_word, y_word=center.y_word),
            half_extent=half_extent,
            include_edges=True,
        )
    )



def view_contact_center_from_offsets_aa46(
    *,
    view_x_word: int,
    view_y_word: int,
    offset_x_word: int,
    offset_y_word: int,
) -> ViewContactCenter:
    """Pure AA46 center projection from the view/contact offset table.

    AA46 selects a dx/dy pair from the same DS:214E table family used by
    tile/contact probing, adds it to the live view center globals, stores the
    resulting DS:95F2/95F4 contact center, then runs the shared 8331 rectangle
    test.  This function owns only the portable projection; the adapter owns
    the table read order, flags, and DOS writes.
    """
    return ViewContactCenter(
        x_word=u16(view_x_word + offset_x_word),
        y_word=u16(view_y_word + offset_y_word),
    )


def postmove_contact_window_test_aa71(
    slot: ObjectSlotRecord,
    window: PostMoveContactWindow,
) -> RectContactResult:
    """Pure source-like form of the 1010:AA71 contact-window decision.

    AA71 is used from the BC4B post-move chain.  Negative signed X escapes
    immediately.  Y is tested with signed bounds around the live DS:2380 guard;
    X is then tested with unsigned bounds around DS:237E.  The final-boss mode
    observed via DS:A8C2 narrows only that X window.
    """
    x = u16(slot.x_word)
    if i16(x) < 0:
        return RectContactResult(False)

    upper_y = u16(slot.y_word + POSTMOVE_CONTACT_Y_UPPER_BIAS)
    if i16(upper_y) < i16(window.y_guard_word):
        return RectContactResult(False)
    lower_y = u16(upper_y - POSTMOVE_CONTACT_Y_SPAN)
    if i16(lower_y) > i16(window.y_guard_word):
        return RectContactResult(False)

    if window.final_boss_narrow_x:
        upper_bias = POSTMOVE_CONTACT_X_BOSS_UPPER_BIAS
        span = POSTMOVE_CONTACT_X_BOSS_SPAN
    else:
        upper_bias = POSTMOVE_CONTACT_X_NORMAL_UPPER_BIAS
        span = POSTMOVE_CONTACT_X_NORMAL_SPAN

    upper_x = u16(x + upper_bias)
    view_x = u16(window.view_x_word)
    if upper_x < view_x:
        return RectContactResult(False)
    lower_x = u16(upper_x - span)
    if lower_x > view_x:
        return RectContactResult(False)
    return RectContactResult(True)

def is_player_hazard_scan_candidate(slot: ObjectSlotRecord) -> bool:
    """Pure candidate gate recovered from the 1010:BDE3 hazard scan.

    The name is intentionally narrow: this is not yet a universal "enemy" or
    "damage" classification.  It is exactly the object-record family that BDE3
    considers after the BDD0 guard initializes the player probe point.
    """
    return (
        slot.active_word != 0
        and slot.gate_or_layer != PLAYER_HAZARD_SCAN_REQUIRED_GATE
        and slot.scan_flag == PLAYER_HAZARD_SCAN_REQUIRED_FLAG
        and slot.hazard_class == PLAYER_HAZARD_SCAN_REQUIRED_CLASS
        and PLAYER_HAZARD_LOGIC_MIN <= slot.logic_id <= PLAYER_HAZARD_LOGIC_MAX
    )


def player_hazard_scan_hit(
    current: ObjectSlotRecord,
    slot: ObjectSlotRecord,
    probe: ProbePoint,
    *,
    half_extent: int = CONTACT_HALF_EXTENT,
) -> bool:
    """Pure hit decision recovered from 1010:BDE3.

    BDE3 uses strict signed bounds: the probe must be greater than x/y-16 and
    less than x/y+16.  It also rejects matching link keys so an object does not
    collide with its linked/source record.
    """
    return (
        is_player_hazard_scan_candidate(slot)
        and slot_contains_probe_point(slot, probe, half_extent=half_extent, include_edges=False)
        and current.link_key != slot.link_key
    )


def object_overlap_scan_decision(
    current: ObjectSlotRecord,
    slot: ObjectSlotRecord,
    probe: ProbePoint,
    *,
    half_extent: int = CONTACT_HALF_EXTENT,
) -> ObjectOverlapScanDecision:
    """Pure one-slot decision recovered from the 1010:AC97 overlap scan.

    AC97 scans the same DS:23B4 effect/contact object pool as BDE3, but it is a
    more general object-overlap/reaction path.  A slot is an overlap candidate
    when it is active, not already in logic id ``1``, scan-enabled, contains the
    current probe point in the inclusive signed ±16 window, and has a different
    link key from the current object.  Only hazard/draw class ``4`` or ``5`` is
    actionable at the ACD9 continuation; other overlaps are absorbed by the
    lifted ACD9->ACD2 continue tail.
    """
    overlaps = (
        slot.active_word != 0
        and slot.logic_id != OBJECT_OVERLAP_INACTIVE_LOGIC_ID
        and slot.scan_flag == OBJECT_OVERLAP_SCAN_REQUIRED_FLAG
        and slot_contains_probe_point(slot, probe, half_extent=half_extent, include_edges=True)
        and current.link_key != slot.link_key
    )
    return ObjectOverlapScanDecision(
        overlaps=overlaps,
        actionable=overlaps and slot.hazard_class in OBJECT_OVERLAP_ACTIONABLE_CLASSES,
    )


def tile_sweep_plan_for_direction(direction: int) -> TileSweepPlan:
    """Return the pure component order for B00D's eight direction entries."""
    return TileSweepPlan(direction8(direction).components)


# 1010:B256..B278 overlap/contact box test (the B250 selector's predicate).  The active
# object slot overlaps the reference box anchored at (ref_x, ref_y) when its X lies in the
# signed window [ref_x - 2, ref_x - 2 + 0x14] and its Y in the unsigned window
# [ref_y, ref_y + 0x14].  X uses signed compares, Y unsigned -- exactly as the ASM.
OVERLAP_CONTACT_BOX_X_INSET = 0x0002
OVERLAP_CONTACT_BOX_SPAN = 0x0014


def overlap_contact_box_contains(obj_x: int, obj_y: int, ref_box_x: int, ref_box_y: int) -> bool:
    """Pure B250 overlap predicate: is ``(obj_x, obj_y)`` inside the reference box?

    Recovered from 1010:B256..B278: X is tested with signed bounds in
    ``[ref_box_x - 2, ref_box_x - 2 + 0x14]`` and Y with unsigned bounds in
    ``[ref_box_y, ref_box_y + 0x14]`` (the box is anchored at the view target
    DS:237E/2380, 0x14 wide/high after the -2 X inset).  ``True`` means the slot is
    in the box -- the selector continues to the contact fanout; ``False`` routes to
    the no-contact tail.  The adapter owns the original SUB/ADD/CMP register and flag
    side effects; this owns the portable geometric decision."""
    lo_x = u16(ref_box_x - OVERLAP_CONTACT_BOX_X_INSET)
    if i16(obj_x) < i16(lo_x):
        return False
    hi_x = u16(lo_x + OVERLAP_CONTACT_BOX_SPAN)
    if i16(obj_x) > i16(hi_x):
        return False
    if u16(obj_y) < u16(ref_box_y):
        return False
    if u16(obj_y) > u16(ref_box_y + OVERLAP_CONTACT_BOX_SPAN):
        return False
    return True


# 1010:BFC7 -> C037 collision-death transition.  The dying state is logic id 1, and
# the death sprite is chosen from the object type via the small C037 table.
COLLISION_DEATH_STATE_LOGIC_ID = 0x0001
COLLISION_DEATH_C037_SPRITE_BY_TYPE = {0x0001: 0x0000, 0x0002: 0x0003}


# 1010:62F6 object-vs-object grid overlap test.  The scanning object's 8px-aligned
# cell (x&FFF8, y&FFF8) is tested against a candidate's occupied cell footprint, which
# is widened by the scanning object's size (object_type 2) and Y pixel alignment.
OBJECT_GRID_CELL_MASK = 0xFFF8
OBJECT_GRID_CELL_PIXELS = 0x0008
OBJECT_GRID_WIDE_OBJECT_TYPE = 0x0002
OBJECT_GRID_X_NARROW_LOGIC_IDS = frozenset((0x0078, 0x0079))


def object_grid_overlap_62f6(self_x_cell: int, self_y_cell: int, cand_x: int, cand_y: int,
                             self_object_type: int, self_logic_id: int) -> bool:
    """Pure 1010:62F6 grid overlap predicate: does the scanning object's cell hit the candidate?

    ``self_x_cell``/``self_y_cell`` are the scanning object's 8px-aligned cell
    (``x & FFF8`` / ``y & FFF8``).  The candidate at ``(cand_x, cand_y)`` occupies a
    vertical cell run -- two cells (``aligned+8``, ``aligned``) when ``cand_y`` is not
    8px-aligned, else one (``cand_y``) -- always plus the cell 8px above, and two more
    above that for a wide (object_type 2) scanner.  Its horizontal run is ``cand_x &
    FFF8`` and the cell 8px left, plus two more left for a wide scanner unless its logic
    id is 78h/79h.  Returns whether the scanning cell is inside that footprint (Y first,
    then X) -- the match that the original routes to the BEC5 collision handler."""
    cand_y &= 0xFFFF
    if cand_y & (OBJECT_GRID_CELL_PIXELS - 1):
        aligned = cand_y & OBJECT_GRID_CELL_MASK
        y_cells = [(aligned + OBJECT_GRID_CELL_PIXELS) & 0xFFFF, aligned]
    else:
        y_cells = [cand_y]
    y_cells.append((y_cells[-1] - OBJECT_GRID_CELL_PIXELS) & 0xFFFF)
    if (self_object_type & 0xFFFF) == OBJECT_GRID_WIDE_OBJECT_TYPE:
        y_cells.append((y_cells[-1] - OBJECT_GRID_CELL_PIXELS) & 0xFFFF)
        y_cells.append((y_cells[-1] - OBJECT_GRID_CELL_PIXELS) & 0xFFFF)
    if (self_y_cell & 0xFFFF) not in y_cells:
        return False

    base_x = cand_x & OBJECT_GRID_CELL_MASK
    x_cells = [base_x, (base_x - OBJECT_GRID_CELL_PIXELS) & 0xFFFF]
    if (self_object_type & 0xFFFF) == OBJECT_GRID_WIDE_OBJECT_TYPE and \
            (self_logic_id & 0xFFFF) not in OBJECT_GRID_X_NARROW_LOGIC_IDS:
        x_cells.append((x_cells[-1] - OBJECT_GRID_CELL_PIXELS) & 0xFFFF)
        x_cells.append((x_cells[-1] - OBJECT_GRID_CELL_PIXELS) & 0xFFFF)
    return (self_x_cell & 0xFFFF) in x_cells


# 1010:BEC5 object-vs-object collision variant dispatch (by the collided slot's logic id).
COLLISION_VARIANT_BD0D_A8C2 = frozenset((0x0005, 0x0006, 0x0007, 0x0008, 0x000C))
COLLISION_VARIANT_A8C2_NO_BD0D = 0x0009
COLLISION_VARIANT_SPRITE_2 = 0x0002


def bec5_collision_variant_family(variant: int) -> CollisionVariantDispatchBEC5:
    """Pure source-like 1010:BEC5 collision-reaction family classification.

    Classifies the collided candidate's logic id (``variant``) into the reaction family
    BEC5 routes to -- BD0D-then-A8C2 (05/06/07/08/0C), A8C2 without BD0D (09), the
    sprite-0033 variant-2 path (02), or the owner-linked/no-op fallback (any other id).
    The adapter replays the per-variant BD0D return address and the runtime owner-link
    test; this owns the stable family routing."""
    v = variant & 0xFFFF
    if v in COLLISION_VARIANT_BD0D_A8C2:
        return CollisionVariantDispatchBEC5("bd0d_then_a8c2")
    if v == COLLISION_VARIANT_A8C2_NO_BD0D:
        return CollisionVariantDispatchBEC5("a8c2_no_bd0d")
    if v == COLLISION_VARIANT_SPRITE_2:
        return CollisionVariantDispatchBEC5("sprite_variant_2")
    return CollisionVariantDispatchBEC5("owner_linked_or_noop")


# 1010:BF25 collision-damage counter chain.  Each hit decrements counter_20 a
# difficulty-gated number of times; a decrement reaching zero kills the object.
COLLISION_DAMAGE_BEDC_ONE_EXTRA_DECS = 1   # DS:BEDC == 1 -> one extra decrement
COLLISION_DAMAGE_BEDC_ZERO_EXTRA_DECS = 3  # DS:BEDC == 0 -> three extra decrements


def collision_damage_counter_chain_bf25(counter_20: int, bedc: int, enter_at_bf25: bool) -> CollisionDamageChainBF25:
    """Pure 1010:BF25 collision-damage counter chain.

    Decrements ``counter_20`` once for the BF25 entry (only when ``enter_at_bf25`` --
    the variant-2 sprite path enters at BF2D and skips it), once at BF2D, then one
    more decrement if ``bedc == 1`` or three more if ``bedc == 0`` (other ``bedc``
    values add none).  Each decrement is checked for zero immediately after (matching
    the ASM ``DEC; JZ BFC7`` per step, including the 16-bit wrap of a 0 counter), and
    the object dies the first time a decrement lands on zero.  Returns the post-chain
    counter and whether it died.
    """
    c = counter_20 & 0xFFFF
    decrements = (1 if enter_at_bf25 else 0) + 1
    b = bedc & 0xFFFF
    if b == 0x0001:
        decrements += COLLISION_DAMAGE_BEDC_ONE_EXTRA_DECS
    elif b == 0x0000:
        decrements += COLLISION_DAMAGE_BEDC_ZERO_EXTRA_DECS
    for _ in range(decrements):
        c = (c - 1) & 0xFFFF
        if c == 0:
            return CollisionDamageChainBF25(new_counter_20=0, died=True)
    return CollisionDamageChainBF25(new_counter_20=c, died=False)


def object_collision_death_transition_c037(logic_id: int, object_type: int) -> CollisionDeathTransition:
    """Pure BFC7/C037 collision-death slot transition for a type-1/2 object.

    Records the old ``logic_id`` as ``previous_logic_id``, forces ``logic_id`` to the
    dying-state ``1``, clears the ``transition_latch``, and selects the death
    ``sprite_or_state`` from the object type via the C037 table (type 1 -> 0, type
    2 -> 3).  Raises ``ValueError`` for any other type -- the original dispatches such
    types through a different C037 table entry, which the adapter still handles as an
    unverified path rather than guessing here.
    """
    try:
        sprite = COLLISION_DEATH_C037_SPRITE_BY_TYPE[object_type & 0xFFFF]
    except KeyError:
        raise ValueError(
            f"no C037 collision-death sprite for object type {object_type & 0xFFFF:#06x}"
        ) from None
    return CollisionDeathTransition(
        previous_logic_id=logic_id & 0xFFFF,
        logic_id=COLLISION_DEATH_STATE_LOGIC_ID,
        transition_latch=0x0000,
        sprite_or_state=sprite,
    )
