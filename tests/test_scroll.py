"""Pure world-scroll gate + forward tick (1010:A66F/A6FE, see overkill.recovered.systems.scroll).

Byte-exact verification against a live VM lives in overkill.probes.verify_native_scroll_forward_a6fe
and verify_native_scroll_gate_a66f (L2/L4/L6 demos, 0 failures across thousands of real calls, plus
one correctly-declined boss-materialize milestone on L6); these are lightweight unit checks of the
wrap/cycle math and gate dispatch in isolation.
"""
from __future__ import annotations

from overkill.recovered.domain.scroll import ScrollState
from overkill.recovered.systems.scroll import (
    BOSS_MATERIALIZE_ROW_BASE,
    FORWARD_ROW_STRIDE,
    ROW_SOURCE_DECREMENT,
    ROW_SOURCE_WRAP_RESET,
    ROW_SOURCE_WRAP_THRESHOLD,
    UNKNOWN_MILESTONE_ROW_BASE,
    step_scroll_forward_a6fe,
    step_scroll_world_progress_gate_a66f,
)


def _state(**overrides) -> ScrollState:
    base = dict(origin_x=5, row_base=0x100, row_source=0x1000,
                rows_to_milestone=10, forward_last=True)
    base.update(overrides)
    return ScrollState(**base)


def test_mid_cycle_tick_only_decrements_origin_x():
    out = step_scroll_forward_a6fe(_state(origin_x=5))
    assert not out.pulled_row
    assert out.state.origin_x == 4
    assert out.state.row_base == 0x100  # unchanged: no row pulled mid-cycle
    assert out.state.rows_to_milestone == 10


def test_origin_x_zero_pulls_a_new_row_and_wraps_to_15():
    out = step_scroll_forward_a6fe(_state(origin_x=0, row_base=0x100, rows_to_milestone=10))
    assert out.pulled_row
    assert out.state.origin_x == 0x0F  # 0 - 1, wrapped mod 16
    assert out.state.row_base == 0x100 + FORWARD_ROW_STRIDE
    assert out.state.rows_to_milestone == 9
    assert out.state.forward_last is True


def test_row_source_decrements_every_tick_regardless_of_row_pull():
    out = step_scroll_forward_a6fe(_state(origin_x=5, row_source=0x2000))
    assert out.state.row_source == (0x2000 - ROW_SOURCE_DECREMENT) & 0xFFFF


def test_row_source_wraps_at_threshold_before_decrementing():
    out = step_scroll_forward_a6fe(_state(origin_x=5, row_source=ROW_SOURCE_WRAP_THRESHOLD))
    assert out.state.row_source == (ROW_SOURCE_WRAP_RESET - ROW_SOURCE_DECREMENT) & 0xFFFF


def test_a_full_16_tick_cycle_pulls_exactly_one_row():
    state = _state(origin_x=15, row_base=0, rows_to_milestone=10)
    pulls = 0
    for _ in range(16):
        out = step_scroll_forward_a6fe(state)
        state = out.state
        pulls += out.pulled_row
    assert pulls == 1
    assert state.row_base == FORWARD_ROW_STRIDE
    assert state.rows_to_milestone == 9
    assert state.origin_x == 15  # back to the same phase after a full cycle


def test_gate_is_a_confirmed_no_op_when_any_gate_global_is_nonzero():
    scroll = _state(origin_x=0)  # would pull a row if the gate let it through
    for kwargs in (dict(a47c=1, a47e=0, a480=0), dict(a47c=0, a47e=1, a480=0), dict(a47c=0, a47e=0, a480=1)):
        out = step_scroll_world_progress_gate_a66f(scroll, **kwargs)
        assert out is not None and out.state == scroll and not out.pulled_row


def test_gate_runs_the_forward_tick_when_all_gate_globals_are_zero():
    scroll = _state(origin_x=0, row_base=0x100)
    out = step_scroll_world_progress_gate_a66f(scroll, a47c=0, a47e=0, a480=0)
    assert out is not None
    assert out.pulled_row  # origin_x==0 at entry pulls a row
    assert out.state.row_base == 0x100 + FORWARD_ROW_STRIDE


def test_gate_declines_on_the_boss_materialize_milestone():
    scroll = _state(origin_x=0, row_base=BOSS_MATERIALIZE_ROW_BASE - FORWARD_ROW_STRIDE)
    assert step_scroll_world_progress_gate_a66f(scroll, a47c=0, a47e=0, a480=0) is None


def test_gate_declines_on_the_unknown_milestone():
    scroll = _state(origin_x=0, row_base=UNKNOWN_MILESTONE_ROW_BASE - FORWARD_ROW_STRIDE)
    assert step_scroll_world_progress_gate_a66f(scroll, a47c=0, a47e=0, a480=0) is None


def test_gate_does_not_decline_when_no_row_is_pulled_this_tick():
    # Even if row_base HAPPENS to already equal a milestone value, only the tick that PULLS a new
    # row into that position should decline (matching the real ASM, which only checks 2350 right
    # after A74E ran).
    scroll = _state(origin_x=5, row_base=BOSS_MATERIALIZE_ROW_BASE)
    out = step_scroll_world_progress_gate_a66f(scroll, a47c=0, a47e=0, a480=0)
    assert out is not None and out.state.row_base == BOSS_MATERIALIZE_ROW_BASE
