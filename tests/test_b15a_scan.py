"""Unit tests for the native B15A rotating target-candidate scan (native_b15a_scan)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import native_b15a_scan

BASE, STRIDE, COUNT = 0x23B4, 0x38, 0x23
WRAP = BASE + COUNT * STRIDE          # 0x2B5C: the effect table's end = the adjacent gameplay base


def _slot(*, active=1, x=0x10, hazard=4, logic=2) -> tuple[int, ...]:
    """A 0x38-byte effect slot.  Defaults are a valid chase candidate (active, x<=E0, hazard 4, logic 2)."""
    words = [0] * (STRIDE >> 1)
    words[0x00 >> 1] = active
    words[0x02 >> 1] = x
    words[0x16 >> 1] = hazard
    words[0x18 >> 1] = logic
    return tuple(words)


def _pool(slot_map: dict[int, tuple[int, ...]]) -> ObjectPool:
    """A full COUNT-slot effect pool; unset indices default to an inactive (non-candidate) slot."""
    slots = tuple(slot_map.get(i, _slot(active=0)) for i in range(COUNT))
    return ObjectPool(base=BASE, stride=STRIDE, slots=slots)


def test_b15a_found_at_cursor():
    found, cursor = native_b15a_scan(_pool({0: _slot()}), BASE)
    assert found == BASE                      # slot 0 is the candidate
    assert cursor == BASE + STRIDE            # cursor parks just past it


def test_b15a_skips_non_candidates_until_match():
    found, cursor = native_b15a_scan(_pool({2: _slot()}), BASE)   # slots 0,1 inactive; 2 matches
    assert found == BASE + 2 * STRIDE
    assert cursor == BASE + 3 * STRIDE


def test_b15a_starts_from_mid_cursor():
    found, cursor = native_b15a_scan(_pool({5: _slot()}), BASE + 5 * STRIDE)
    assert found == BASE + 5 * STRIDE
    assert cursor == BASE + 6 * STRIDE


def test_b15a_miss_leaves_cursor_unchanged():
    # no candidate anywhere; a full rotation from BASE never wraps -> cursor unchanged
    found, cursor = native_b15a_scan(_pool({}), BASE)
    assert found is None
    assert cursor == BASE


def test_b15a_wraps_at_table_end_then_finds():
    # cursor on the last slot (non-candidate); the scan wraps to BASE and finds slot 0
    found, cursor = native_b15a_scan(_pool({0: _slot()}), BASE + (COUNT - 1) * STRIDE)
    assert found == BASE
    assert cursor == BASE + STRIDE


def test_b15a_cursor_at_wrap_limit_resets_first():
    # a cursor exactly at the gameplay-table base wraps before the first real check
    found, cursor = native_b15a_scan(_pool({0: _slot()}), WRAP)
    assert found == BASE
    assert cursor == BASE + STRIDE


def test_b15a_candidate_gates_each_rejected():
    # each single-reason non-candidate at slot 0 is skipped; slot 1 is the real match
    for bad in (_slot(active=0), _slot(x=0x00E1), _slot(hazard=3), _slot(logic=0x21)):
        found, _ = native_b15a_scan(_pool({0: bad, 1: _slot()}), BASE)
        assert found == BASE + STRIDE


def test_b15a_x_boundary_inclusive():
    # x == MAX (E0h) is still a candidate; x == E1h is not
    assert native_b15a_scan(_pool({0: _slot(x=0x00E0)}), BASE)[0] == BASE
    assert native_b15a_scan(_pool({0: _slot(x=0x00E1), 1: _slot()}), BASE)[0] == BASE + STRIDE


def test_b15a_wrap_limit_is_table_end():
    # the cursor wrap limit is exactly one slot past the last effect slot (the gameplay table base)
    assert WRAP == BASE + COUNT * STRIDE == 0x2B5C
