"""Unit tests for overkill.native_front_end.NativeFrontEnd -- the reusable front-end flow state.

The underlying decisions (step_menu_idle_558b, the 4 level-select direction handlers,
resolve_level_select_fire_d424) are already proven byte-exact against real ASM elsewhere
(overkill.probes.verify_native_menu_idle_558b, verify_native_level_select_grid,
tests/test_native_level_select_grid.py); these tests only need to confirm the WIRING -- phase
transitions, delegation, and phase-guard errors -- is correct, not re-verify the ASM.
"""
from __future__ import annotations

import pytest

from overkill.native_front_end import NativeFrontEnd


def test_new_session_starts_at_menu_idle():
    fe = NativeFrontEnd.new_session()
    assert fe.phase == "menu_idle"
    assert fe.attract_counter == 0


def test_menu_idle_loops_while_no_fire():
    fe = NativeFrontEnd.new_session()
    for i in range(1, 5):
        fe = fe.step_menu_idle(shortcut_active=False, fire_pressed=False)
        assert fe.phase == "menu_idle"
        assert fe.attract_counter == i


def test_menu_idle_declines_on_shortcut():
    fe = NativeFrontEnd.new_session()
    fe2 = fe.step_menu_idle(shortcut_active=True, fire_pressed=False)
    assert fe2 == fe  # unchanged -- matches the hook's own fallback scope


def test_menu_idle_exits_to_level_select_on_fire():
    fe = NativeFrontEnd.new_session().step_menu_idle(shortcut_active=False, fire_pressed=False)
    fe = fe.step_menu_idle(shortcut_active=False, fire_pressed=True)
    assert fe.phase == "level_select"
    assert fe.beda == 0


def test_menu_idle_stays_put_at_attract_timeout():
    fe = NativeFrontEnd.new_session()
    for _ in range(800):  # past MENU_ATTRACT_TIMEOUT (0x2EE = 750)
        fe = fe.step_menu_idle(shortcut_active=False, fire_pressed=False)
    assert fe.phase == "menu_idle"  # declined, not modelled -- see the module docstring


def test_level_select_direction_and_confirm_matches_the_real_session():
    """The user's real cold-start session never touched a direction key and confirmed level 0 --
    the exact scenario overkill.probes.verify_native_front_end_forward proved against the VM."""
    fe = NativeFrontEnd.new_session().step_menu_idle(shortcut_active=False, fire_pressed=True)
    fe = fe.step_level_select_confirm()
    assert fe.phase == "confirmed"
    assert fe.confirmed_level == 0


def test_level_select_direction_navigates_and_rejects_at_boundaries():
    fe = NativeFrontEnd.new_session().step_menu_idle(shortcut_active=False, fire_pressed=True)
    assert fe.beda == 0
    fe = fe.step_level_select_direction("increment")
    assert fe.beda == 1
    fe = fe.step_level_select_direction("page_down")
    assert fe.beda == 4  # 1 + 3
    fe = fe.step_level_select_direction("increment")
    assert fe.beda == 5  # 4 + 1
    fe = fe.step_level_select_direction("increment")
    assert fe.beda == 5  # rejected at the boundary (max index), unchanged
    fe = fe.step_level_select_confirm()
    assert fe.confirmed_level == 0xFFFF  # cell 5's sentinel, not a playable level


def test_level_select_direction_rejects_unknown_direction():
    fe = NativeFrontEnd.new_session().step_menu_idle(shortcut_active=False, fire_pressed=True)
    with pytest.raises(ValueError):
        fe.step_level_select_direction("sideways")


@pytest.mark.parametrize("method,kwargs", [
    ("step_level_select_direction", {"direction": "increment"}),
    ("step_level_select_confirm", {}),
])
def test_level_select_methods_reject_wrong_phase(method, kwargs):
    fe = NativeFrontEnd.new_session()  # still in menu_idle
    with pytest.raises(ValueError):
        getattr(fe, method)(**kwargs)


def test_menu_idle_rejects_wrong_phase():
    fe = NativeFrontEnd.new_session().step_menu_idle(shortcut_active=False, fire_pressed=True)  # -> level_select
    with pytest.raises(ValueError):
        fe.step_menu_idle(shortcut_active=False, fire_pressed=False)
