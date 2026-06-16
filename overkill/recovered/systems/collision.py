"""Pure recovered collision systems.

No CPU, memory, DOS segment, or hook state is allowed here.  The functions in
this module are the first portable slice that a future native source port can
reuse directly.
"""
from __future__ import annotations

from overkill.recovered.domain.collision import ProbePoint, RectContactResult, ViewContactCenter
from overkill.recovered.domain.coords import i16, u16
from overkill.recovered.domain.object_slots import ObjectSlotRecord


def word_inside_signed_center_window(
    value_word: int,
    center_word: int,
    *,
    half_extent: int = 0x10,
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
    half_extent: int = 0x10,
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
    half_extent: int = 0x10,
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


def is_player_hazard_scan_candidate(slot: ObjectSlotRecord) -> bool:
    """Pure candidate gate recovered from the 1010:BDE3 hazard scan.

    The name is intentionally narrow: this is not yet a universal "enemy" or
    "damage" classification.  It is exactly the object-record family that BDE3
    considers after the BDD0 guard initializes the player probe point.
    """
    return (
        slot.active_word != 0
        and slot.gate_or_layer != 1
        and slot.scan_flag == 1
        and slot.hazard_class == 4
        and 0x0082 <= slot.logic_id <= 0x0094
    )


def player_hazard_scan_hit(
    current: ObjectSlotRecord,
    slot: ObjectSlotRecord,
    probe: ProbePoint,
    *,
    half_extent: int = 0x10,
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
