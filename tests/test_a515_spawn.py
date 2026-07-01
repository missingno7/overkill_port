"""Unit tests for the A067 A515 linked-anchor spawn (the counter-driven link weapon, native_a515)."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.objects import (
    A515_HAZARD_CLASS,
    A515_LOGIC_ID,
    A515_SUBSTATE,
    native_a515,
    object_pool_find_free,
)

GP_BASE, EFF_BASE, STRIDE = 0x2B5C, 0x23B4, 0x38
STRIDE_WORDS = STRIDE >> 1
OFF_DIRECTION, OFF_SPRITE, OFF_ACQUIRED = 0x06, 0x08, 0x30


def _gp_slot(*, active=0, direction=0xAAAA, sprite=0xBBBB) -> tuple[int, ...]:
    """A gameplay slot with distinctive stale fields (7547 does not seed, so they must survive)."""
    words = [0] * STRIDE_WORDS
    words[0x00 >> 1] = active
    words[OFF_DIRECTION >> 1] = direction
    words[OFF_SPRITE >> 1] = sprite
    return tuple(words)


def _eff_candidate(*, active=1, x=0x10, hazard=4, logic=2) -> tuple[int, ...]:
    words = [0] * STRIDE_WORDS
    words[0x00 >> 1] = active
    words[0x02 >> 1] = x
    words[0x16 >> 1] = hazard
    words[0x18 >> 1] = logic
    return tuple(words)


def _gp_pool(slot_map: dict[int, tuple[int, ...]], count=4) -> ObjectPool:
    return ObjectPool(base=GP_BASE, stride=STRIDE, slots=tuple(
        slot_map.get(i, _gp_slot()) for i in range(count)))


def _eff_pool(slot_map: dict[int, tuple[int, ...]], count=0x23) -> ObjectPool:
    inactive = tuple([0] * STRIDE_WORDS)
    return ObjectPool(base=EFF_BASE, stride=STRIDE, slots=tuple(
        slot_map.get(i, inactive) for i in range(count)))


def test_a515_gate_a960_zero_returns_none():
    assert native_a515(_gp_pool({}), GP_BASE, _eff_pool({0: _eff_candidate()}), EFF_BASE,
                        0x0050, 0x0060, a960=0, a97e=0) is None


def test_a515_gate_a97e_one_returns_none():
    assert native_a515(_gp_pool({}), GP_BASE, _eff_pool({0: _eff_candidate()}), EFF_BASE,
                        0x0050, 0x0060, a960=1, a97e=1) is None


def test_a515_found_partial_stamp_over_stale_slot():
    gp = _gp_pool({})
    r = native_a515(gp, GP_BASE, _eff_pool({0: _eff_candidate()}), EFF_BASE, 0x0050, 0x0060, a960=3, a97e=0)
    assert r is not None and r.slot_offset == GP_BASE and r.slot_words is not None
    w = r.slot_words
    # the 9 A515 overrides
    assert w[0x00 >> 1] == 0x0001                         # active
    assert w[0x02 >> 1] == 0x005A and w[0x04 >> 1] == 0x006A   # anchor src + 0xA (no align)
    assert w[0x14 >> 1] == 0x0000                         # scan_flag
    assert w[0x16 >> 1] == A515_HAZARD_CLASS == 0x0002
    assert w[0x18 >> 1] == A515_LOGIC_ID == 0x000A
    assert w[0x1C >> 1] == A515_SUBSTATE == 0x0001
    assert w[0x1E >> 1] == 0x0001                         # scan_enable
    assert w[OFF_ACQUIRED >> 1] == EFF_BASE               # acquired_target_ptr = the B15A-found slot
    # the un-set words keep the slot's stale prior contents (7547 does not seed)
    assert w[OFF_DIRECTION >> 1] == 0xAAAA and w[OFF_SPRITE >> 1] == 0xBBBB


def test_a515_found_advances_cursors_and_counters():
    gp = _gp_pool({})
    r = native_a515(gp, GP_BASE, _eff_pool({0: _eff_candidate()}), EFF_BASE, 0x0050, 0x0060, a960=3, a97e=0)
    assert r.cursor_95da == object_pool_find_free(gp, GP_BASE).cursor
    assert r.cursor_a43a == EFF_BASE + STRIDE             # B15A parked past the found effect slot
    assert r.a97e == 1 and r.a960 == 2                    # A97E += 1, A960 -= 1


def test_a515_no_target_leaves_slot_inactive_counters_unchanged():
    gp = _gp_pool({})
    # effect pool has no candidate -> B15A returns FFFF -> the slot is not activated
    r = native_a515(gp, GP_BASE, _eff_pool({}), EFF_BASE, 0x0050, 0x0060, a960=3, a97e=0)
    assert r is not None
    assert r.slot_offset is None and r.slot_words is None     # no spawn
    assert r.a97e == 0 and r.a960 == 3                        # counters unchanged
    assert r.cursor_95da == object_pool_find_free(gp, GP_BASE).cursor   # but 95DA still advanced
    assert r.cursor_a43a == EFF_BASE                          # a full miss with no wrap leaves A43A


def test_a515_full_gameplay_pool_returns_none():
    full = ObjectPool(base=GP_BASE, stride=STRIDE, slots=(_gp_slot(active=1),) * 4)
    assert native_a515(full, GP_BASE, _eff_pool({0: _eff_candidate()}), EFF_BASE,
                       0x0050, 0x0060, a960=3, a97e=0) is None
