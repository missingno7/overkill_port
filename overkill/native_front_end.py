"""Native front-end flow -- run the pre-gameplay menu sequence VM-free (the standalone backbone,
the front-end counterpart of :mod:`overkill.native_game`).

This packages the composition already PROVEN byte-exact against a real cold-start session
(``overkill.probes.verify_native_front_end_forward``) as a reusable, steppable state object,
instead of a one-shot verify probe. It covers ONLY: the ``558B`` main-menu idle loop, the ``D390``
level-select grid's 4 direction handlers, and the ``D424`` fire-confirm mapping.

**What this does NOT cover, and why** (see ``overkill-front-end-recovery`` / ``overkill-native-
frame-controller`` memory for the full caller-graph reconnaissance this is built on):

* Everything BEFORE ``558B`` -- the intro (``96C5``), and the ``CE40`` title->menu transition
  (found to be a generic multi-caller utility, not owned by any one screen) -- is not modelled.
  A session starts already IN the menu-idle phase; getting there from a cold boot is still VM-only.
* The menu's ``attract_timeout`` outcome is DECLINED (the state stays in ``menu_idle`` rather than
  advancing) -- not because it is rare, but because what follows it turned out to be a genuinely
  deep, only-partially-understood thread: attract-mode plays REAL gameplay (confirmed via runtime
  instrumentation: ``DS:2356`` becomes a real level index and ``A940`` starts running >1000 times),
  not a simple title-screen loop. Modelling that composition wrong would be worse than declining it.
* Everything AFTER a level is confirmed -- the ``971A`` "new game setup" routine (score-digit
  reset, ``C4DB``, ``5C9A``, ``6176``, and a level-0-specific ``9844``/``5BEE`` branch) -- is not
  modelled. The caller graph from there into actual gameplay (``9B2E``/``A940``) has real,
  documented gaps.

This is the BEGINNING of the native front-end driver, not a complete one. It grows the same way
``NativeGame`` does: one verified stage at a time, composed only where the caller graph is proven.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from overkill.recovered.systems.menu import (
    resolve_level_select_fire_d424,
    step_level_select_decrement_d488,
    step_level_select_increment_d490,
    step_level_select_page_down_d476,
    step_level_select_page_up_d480,
    step_menu_idle_558b,
)

_DIRECTION_HANDLERS = {
    "page_down": step_level_select_page_down_d476,
    "page_up": step_level_select_page_up_d480,
    "decrement": step_level_select_decrement_d488,
    "increment": step_level_select_increment_d490,
}


@dataclass(frozen=True, slots=True)
class NativeFrontEnd:
    """State for the covered slice of the native front-end flow. ``phase`` is one of
    ``"menu_idle"`` (558B) or ``"level_select"`` (the D390 grid, entered on 558B's FIRE exit)."""

    phase: str
    attract_counter: int = 0
    beda: int = 0
    confirmed_level: int | None = None

    @classmethod
    def new_session(cls) -> "NativeFrontEnd":
        """A session already at the menu-idle phase -- see the module docstring for what getting
        here from a cold boot still needs (VM-owned intro/title transition)."""
        return cls(phase="menu_idle")

    def step_menu_idle(self, *, shortcut_active: bool, fire_pressed: bool) -> "NativeFrontEnd":
        """Run one ``558B`` idle-loop iteration. Only valid in the ``menu_idle`` phase."""
        if self.phase != "menu_idle":
            raise ValueError(f"step_menu_idle called outside the menu_idle phase (phase={self.phase!r})")
        outcome = step_menu_idle_558b(self.attract_counter, shortcut_active=shortcut_active, fire_pressed=fire_pressed)
        if outcome is None:
            return self  # declined (a shortcut key is active) -- matches the hook's own fallback scope
        if outcome.result == "exit":
            return dataclasses.replace(self, phase="level_select", attract_counter=outcome.attract_counter, beda=0)
        # "loop" and "attract_timeout" both stay in menu_idle -- see the module docstring for why
        # attract_timeout is deliberately declined rather than modelled as a transition.
        return dataclasses.replace(self, attract_counter=outcome.attract_counter)

    def step_level_select_direction(self, direction: str) -> "NativeFrontEnd":
        """Run one direction-key event at the level-select grid.

        ``direction`` is one of ``"page_down"``/``"page_up"``/``"decrement"``/``"increment"``
        (the D476/D480/D488/D490 handlers). Only valid in the ``level_select`` phase; a rejected
        (boundary) direction leaves ``beda`` unchanged, matching the ASM's own behaviour.
        """
        if self.phase != "level_select":
            raise ValueError(f"step_level_select_direction called outside the level_select phase (phase={self.phase!r})")
        try:
            handler = _DIRECTION_HANDLERS[direction]
        except KeyError as exc:
            raise ValueError(f"unknown level-select direction {direction!r}") from exc
        step = handler(self.beda)
        return dataclasses.replace(self, beda=step.beda)

    def step_level_select_confirm(self) -> "NativeFrontEnd":
        """Run the ``D424`` fire-confirm: map the selected grid cell to a level index (or the
        unplayable-cell sentinel, ``LevelSelectFireResult.level == 0xFFFF``). Only valid in the
        ``level_select`` phase; the result is terminal for this flow (see the module docstring for
        what comes after a level is confirmed -- not modelled here)."""
        if self.phase != "level_select":
            raise ValueError(f"step_level_select_confirm called outside the level_select phase (phase={self.phase!r})")
        result = resolve_level_select_fire_d424(self.beda)
        return dataclasses.replace(self, phase="confirmed", confirmed_level=result.level)
