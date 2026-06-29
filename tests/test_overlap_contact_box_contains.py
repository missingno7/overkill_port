"""VM-free unit tests for the pure B250 overlap/contact box predicate.

Pins the recovered 1010:B256..B278 box test (``overlap_contact_box_contains``): the signed-X
window ``[ref_x - 2, ref_x - 2 + 0x14]``, the unsigned-Y window ``[ref_y, ref_y + 0x14]``, and
the edges -- the synthetic oracle behind the demo-level
``overkill.probes.verify_native_overlap_contact_box_b250`` produced-vs-VM witness.
"""
from __future__ import annotations

from overkill.recovered.systems.collision import overlap_contact_box_contains


def test_box_center_is_inside():
    assert overlap_contact_box_contains(0x100, 0x88, 0x100, 0x80) is True


def test_x_edges_signed():
    # X window: [ref_x-2, ref_x-2+0x14] = [0xFE, 0x112] for ref_x=0x100.
    assert overlap_contact_box_contains(0x0FE, 0x88, 0x100, 0x80) is True
    assert overlap_contact_box_contains(0x112, 0x88, 0x100, 0x80) is True
    assert overlap_contact_box_contains(0x0FD, 0x88, 0x100, 0x80) is False
    assert overlap_contact_box_contains(0x113, 0x88, 0x100, 0x80) is False


def test_y_edges_unsigned():
    # Y window: [ref_y, ref_y+0x14] = [0x80, 0x94] for ref_y=0x80.
    assert overlap_contact_box_contains(0x100, 0x80, 0x100, 0x80) is True
    assert overlap_contact_box_contains(0x100, 0x94, 0x100, 0x80) is True
    assert overlap_contact_box_contains(0x100, 0x7F, 0x100, 0x80) is False
    assert overlap_contact_box_contains(0x100, 0x95, 0x100, 0x80) is False


def test_x_uses_signed_compare():
    # ref_x=1 -> lo_x = -1 (0xFFFF), hi_x = 0x13.  A signed obj_x = -1 (0xFFFF) is INSIDE;
    # an unsigned reading (0xFFFF >> 0x13) would wrongly reject it.
    assert overlap_contact_box_contains(0xFFFF, 0x88, 0x0001, 0x80) is True
    assert overlap_contact_box_contains(0x0014, 0x88, 0x0001, 0x80) is False  # 0x14 > hi 0x13
