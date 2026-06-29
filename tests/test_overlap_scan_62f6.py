"""Unit tests for the 62F6 object-vs-object overlap scan (object_overlap_scan_62f6)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.collision import object_overlap_scan_62f6

STRIDE = 0x38


def _slot(*, active=1, x=0, y=0, solid=1) -> tuple:
    w = [0] * (STRIDE >> 1)
    w[0x00 >> 1] = active
    w[0x02 >> 1] = x
    w[0x04 >> 1] = y
    w[0x1E >> 1] = solid  # scan_enable_or_solid
    return tuple(w)


def _pool(*slots) -> ObjectPool:
    return ObjectPool(base=0x2B5C, stride=STRIDE, slots=slots)


def _scan(candidates, *, active=1, x=0x40, y=0x40, draw_layer=1, logic_id=0x10, object_type=1):
    return object_overlap_scan_62f6(
        scanner_active_word=active, scanner_x_word=x, scanner_y_word=y,
        scanner_draw_layer=draw_layer, scanner_logic_id=logic_id, scanner_object_type=object_type,
        candidates=candidates)


_OVERLAP = _pool(_slot(x=0x40, y=0x40))  # a candidate sharing the scanner's (0x40,0x40) cell


def test_inactive_scanner_does_not_scan():
    assert _scan(_OVERLAP, active=0) is None


def test_scanner_left_of_min_x_does_not_scan():
    assert _scan(_OVERLAP, x=0x10) is None


def test_zero_draw_layer_or_logic_id_does_not_scan():
    assert _scan(_OVERLAP, draw_layer=0) is None
    assert _scan(_OVERLAP, logic_id=0) is None


def test_dying_and_exempt_logic_ids_do_not_scan():
    assert _scan(_OVERLAP, logic_id=0x0001) is None  # dying
    assert _scan(_OVERLAP, logic_id=0x0026) is None  # 26h exemption


def test_overlapping_candidate_is_the_hit():
    assert _scan(_OVERLAP) == 0


def test_no_overlap_returns_none():
    assert _scan(_pool(_slot(x=0x200, y=0x200))) is None


def test_inactive_candidate_is_skipped():
    assert _scan(_pool(_slot(active=0, x=0x40, y=0x40))) is None


def test_non_solid_candidate_is_skipped():
    # scan_enable_or_solid (+1E) == 0 -> the candidate is not scanned.
    assert _scan(_pool(_slot(x=0x40, y=0x40, solid=0))) is None


def test_first_overlapping_candidate_wins():
    pool = _pool(
        _slot(x=0x200, y=0x200),  # 0: no overlap
        _slot(x=0x40, y=0x40),    # 1: overlap
        _slot(x=0x40, y=0x40),    # 2: overlap (later, ignored)
    )
    assert _scan(pool) == 1


def test_empty_pool_returns_none():
    assert _scan(_pool()) is None
