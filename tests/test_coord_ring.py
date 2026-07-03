"""Unit tests for the pure delayed-coordinate ring geometry (systems/coord_ring).

Pins the 9CF1 cursor-advance wrap rule the lifted game_state adapter delegates to.
"""
from __future__ import annotations

from overkill.recovered.systems.coord_ring import (
    COORD_RING_BASE,
    COORD_RING_CURSOR_COUNT,
    COORD_RING_SLOTS,
    COORD_RING_STEP,
    COORD_RING_WRAP_AT,
    advance_coord_ring_cursors,
    advance_coord_ring_ptr,
    coord_ring_advance_gate,
)


def test_geometry_constants():
    assert COORD_RING_BASE == 0xA27A
    assert COORD_RING_WRAP_AT == 0xA33A
    assert COORD_RING_STEP == 4
    assert COORD_RING_SLOTS == 48
    assert COORD_RING_BASE + COORD_RING_SLOTS * COORD_RING_STEP == COORD_RING_WRAP_AT


def test_plain_advance_steps_by_four():
    assert advance_coord_ring_ptr(COORD_RING_BASE) == COORD_RING_BASE + 4
    assert advance_coord_ring_ptr(0xA300) == 0xA304


def test_last_slot_wraps_to_base():
    last = COORD_RING_WRAP_AT - COORD_RING_STEP  # 0xA336, the final valid slot
    assert advance_coord_ring_ptr(last) == COORD_RING_BASE
    # one before the last does NOT wrap
    assert advance_coord_ring_ptr(last - COORD_RING_STEP) == last


def test_walking_the_whole_ring_returns_to_base():
    ptr = COORD_RING_BASE
    seen = []
    for _ in range(COORD_RING_SLOTS):
        seen.append(ptr)
        ptr = advance_coord_ring_ptr(ptr)
    assert ptr == COORD_RING_BASE                 # full loop
    assert len(set(seen)) == COORD_RING_SLOTS     # every slot visited exactly once
    assert min(seen) == COORD_RING_BASE and max(seen) == COORD_RING_WRAP_AT - COORD_RING_STEP


def test_result_masked_to_16_bits():
    assert 0 <= advance_coord_ring_ptr(0xFFFE) <= 0xFFFF


def test_advance_gate_skips_only_on_no_input_and_clear_a360():
    # 9CF1 advances unless (low input nibble == 0 AND a360 == 0).
    assert coord_ring_advance_gate(0x00, 0x0000) is False   # no input, clear -> skip
    assert coord_ring_advance_gate(0x01, 0x0000) is True     # directional input -> advance
    assert coord_ring_advance_gate(0x00, 0x0001) is True     # axis-response flag set -> advance
    assert coord_ring_advance_gate(0x10, 0x0000) is False    # only high nibble bits -> still skip
    assert coord_ring_advance_gate(0x1F, 0x0000) is True     # low nibble non-zero -> advance


def test_advance_all_cursors_steps_each_and_wraps():
    last = COORD_RING_WRAP_AT - COORD_RING_STEP
    cursors = (COORD_RING_BASE, COORD_RING_BASE + 4, 0xA300, last)
    out = advance_coord_ring_cursors(cursors)
    assert len(out) == COORD_RING_CURSOR_COUNT == 4
    assert out == (COORD_RING_BASE + 4, COORD_RING_BASE + 8, 0xA304, COORD_RING_BASE)
