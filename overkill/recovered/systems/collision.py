"""Pure recovered collision systems.

No CPU, memory, DOS segment, or hook state is allowed here.  The functions in
this module are the first portable slice that a future native source port can
reuse directly.
"""
from __future__ import annotations

from overkill.recovered.domain.collision import (
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
