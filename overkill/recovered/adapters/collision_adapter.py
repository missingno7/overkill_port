"""DOS/ASM adapters for recovered collision systems."""
from __future__ import annotations

from overkill.recovered.adapters.asm_flags import (
    add_word_to_si,
    cmp_word,
    set_carry_and_return,
    sub_word_from_si,
)
from overkill.recovered.adapters.object_slot_adapter import read_object_slot_record
from overkill.recovered.domain.collision import ProbePoint, ViewContactCenter
from overkill.recovered.domain.coords import i16
from overkill.recovered.systems.collision import player_hazard_scan_hit, view_contact_rect_test
from overkill.recovered.views.object_slots import ObjectSlotView

VIEW_CONTACT_CENTER_X = 0x95F2
VIEW_CONTACT_CENTER_Y = 0x95F4
TILE_SWEEP_BLOCKED_FLAG = 0xA430


def mark_tile_sweep_blocked(cpu) -> None:
    """Recovered from 1010:B032: set the raw B00D tile-sweep blocked flag."""
    cpu.mem.ww(cpu.s.ds & 0xFFFF, TILE_SWEEP_BLOCKED_FLAG, 0x0001)


def view_contact_centers(cpu) -> tuple[int, int]:
    """Return the prepared DS:95F2/95F4 rectangle center words."""
    ds = cpu.s.ds & 0xFFFF
    return cpu.mem.rw(ds, VIEW_CONTACT_CENTER_X), cpu.mem.rw(ds, VIEW_CONTACT_CENTER_Y)


def read_view_contact_center(cpu) -> ViewContactCenter:
    """Copy the DOS contact center globals into a pure domain record."""
    x_word, y_word = view_contact_centers(cpu)
    return ViewContactCenter(x_word=x_word, y_word=y_word)


def run_signed_center_rect_test_8331(
    cpu,
    slot: ObjectSlotView,
    *,
    center_x: int,
    center_y: int,
    half_extent: int = 0x10,
) -> bool:
    """Run 1010:8331 with exact SI/FLAGS while validating the pure system.

    The pure recovered system computes the portable gameplay result from copied
    domain records.  This adapter then performs the original instruction-shaped
    compare sequence so hook verification still sees the exact flags and SI at
    the return tail.
    """
    pure = view_contact_rect_test(
        read_object_slot_record(slot),
        ViewContactCenter(center_x & 0xFFFF, center_y & 0xFFFF),
        half_extent=half_extent,
    ).hit

    cpu.s.si = center_x & 0xFFFF
    add_word_to_si(cpu, half_extent)
    x = slot.x_word
    cmp_word(cpu, x, cpu.s.si)
    if i16(x) > i16(cpu.s.si):
        if pure:
            raise AssertionError("pure 8331 result disagrees with ASM-compatible X upper branch")
        return False

    sub_word_from_si(cpu, half_extent * 2)
    cmp_word(cpu, x, cpu.s.si)
    if i16(x) < i16(cpu.s.si):
        if pure:
            raise AssertionError("pure 8331 result disagrees with ASM-compatible X lower branch")
        return False

    cpu.s.si = center_y & 0xFFFF
    add_word_to_si(cpu, half_extent)
    y = slot.y_word
    cmp_word(cpu, y, cpu.s.si)
    if i16(y) > i16(cpu.s.si):
        if pure:
            raise AssertionError("pure 8331 result disagrees with ASM-compatible Y upper branch")
        return False

    sub_word_from_si(cpu, half_extent * 2)
    cmp_word(cpu, y, cpu.s.si)
    if i16(y) < i16(cpu.s.si):
        if pure:
            raise AssertionError("pure 8331 result disagrees with ASM-compatible Y lower branch")
        return False

    if not pure:
        raise AssertionError("pure 8331 result disagrees with ASM-compatible hit path")
    return True



def run_player_hazard_candidate_checks_bde3(
    cpu,
    *,
    current_record,
    slot,
    probe_x: int,
    probe_y: int,
    half_extent: int = 0x10,
) -> bool:
    """Run one BDE3 object candidate check with exact ASM flags.

    The portable decision is computed by
    ``systems.collision.player_hazard_scan_hit``.  This adapter then performs
    the original compare sequence so hook verification still observes the same
    flags/SI at every skip or hit boundary.  The caller owns BX/CX advancement
    and the final jump/RET continuation.
    """
    slot_record = read_object_slot_record(slot)
    pure_hit = player_hazard_scan_hit(
        current_record,
        slot_record,
        ProbePoint(x_word=probe_x & 0xFFFF, y_word=probe_y & 0xFFFF),
        half_extent=half_extent,
    )

    value = slot.active_word
    cmp_word(cpu, value, 0)
    if value == 0:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on active-word gate")
        return False

    value = slot.gate_or_layer
    cmp_word(cpu, value, 1)
    if value == 1:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on gate/layer rejection")
        return False

    value = slot.scan_flag
    cmp_word(cpu, value, 1)
    if value != 1:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on scan-flag gate")
        return False

    value = slot.hazard_class
    cmp_word(cpu, value, 4)
    if value != 4:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on hazard-class gate")
        return False

    obj_id = slot.logic_id
    cmp_word(cpu, obj_id, 0x0082)
    if obj_id < 0x0082:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on logic-id lower gate")
        return False

    cmp_word(cpu, obj_id, 0x0094)
    if obj_id > 0x0094:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on logic-id upper gate")
        return False

    si0 = slot.x_word
    si = (si0 + half_extent) & 0xFFFF
    cpu.s.si = si
    cpu.set_add_flags(si0, half_extent, si0 + half_extent, 16)
    cmp_word(cpu, probe_x, si)
    if i16(probe_x) >= i16(si):
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on X upper bound")
        return False

    si_before = si
    si = (si - half_extent * 2) & 0xFFFF
    cpu.s.si = si
    cpu.set_sub_flags(si_before, half_extent * 2, si_before - half_extent * 2, 16)
    cmp_word(cpu, probe_x, si)
    if i16(probe_x) <= i16(si):
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on X lower bound")
        return False

    si0 = slot.y_word
    si = (si0 + half_extent) & 0xFFFF
    cpu.s.si = si
    cpu.set_add_flags(si0, half_extent, si0 + half_extent, 16)
    cmp_word(cpu, probe_y, si)
    if i16(probe_y) >= i16(si):
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on Y upper bound")
        return False

    si_before = si
    si = (si - half_extent * 2) & 0xFFFF
    cpu.s.si = si
    cpu.set_sub_flags(si_before, half_extent * 2, si_before - half_extent * 2, 16)
    cmp_word(cpu, probe_y, si)
    if i16(probe_y) <= i16(si):
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on Y lower bound")
        return False

    si = current_record.link_key
    cpu.s.si = si
    other = slot.link_key
    cmp_word(cpu, si, other)
    hit = si != other
    if pure_hit != hit:
        raise AssertionError("pure BDE3 hazard result disagrees on link-key gate")
    return hit
