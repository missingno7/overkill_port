"""Native front-end (intro/title/menu/map) systems -- the VM-free counterpart of the scenes
shown before/around a level, sequenced the way ``systems/frame_loop.py`` sequences gameplay.
"""
from __future__ import annotations

from overkill.recovered.domain.menu import MENU_ATTRACT_TIMEOUT, MenuIdleOutcome


def step_menu_idle_558b(attract_counter: int, *, shortcut_active: bool, fire_pressed: bool) -> MenuIdleOutcome | None:
    """Pure model of one ``1010:558B`` main-menu idle-loop iteration.

    Returns ``None`` when a shortcut flag is active (the hook's own decline: ``558B`` checks
    a fixed set of DS:98xx key-state bytes first and falls back to interpreted ASM for the real
    menu-transition branches that iteration -- see ``overkill.input_menu.run_main_menu_idle_
    loop_558b``, whose docstring states it "optimizes only the exact no-key path").  Otherwise
    mirrors the hot idle path: increment the attract-mode counter (``DS:22BF``, wraps mod
    0x10000 like the real ``INC``), and report which of the three modelled continuations fires --
    fire/space (the caller's decoded ``DS:98BE == 0x10``) exits the idle loop (into whatever
    screen follows, e.g. a difficulty/level selector -- not modelled here), the counter reaching
    ``MENU_ATTRACT_TIMEOUT`` (750) reaches the attract-mode demo playback (``0x55FD``), otherwise
    the loop continues.  The three per-frame animation deltas (``DS:22B9/22BB/22BD``) are
    unconditionally cleared to 0 every idle tick and carry no state across iterations, so they
    are not modelled as inputs/outputs.  The VGA-retrace wait (``50C9``) and the keyboard poll
    (``0162``, whose decode is ``systems.input.decode_keyboard_input_flags``) are pure timing/
    input plumbing with no menu-state consequence of their own -- their DECODED RESULT
    (``fire_pressed``) is this function's only input from them.
    """
    if shortcut_active:
        return None
    new_counter = (attract_counter + 1) & 0xFFFF
    if new_counter >= MENU_ATTRACT_TIMEOUT:
        return MenuIdleOutcome(attract_counter=new_counter, result="attract_timeout")
    if fire_pressed:
        return MenuIdleOutcome(attract_counter=new_counter, result="exit")
    return MenuIdleOutcome(attract_counter=new_counter, result="loop")
