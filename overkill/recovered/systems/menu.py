"""Native front-end (intro/title/menu/map) systems -- the VM-free counterpart of the scenes
shown before/around a level, sequenced the way ``systems/frame_loop.py`` sequences gameplay.
"""
from __future__ import annotations

from overkill.recovered.domain.menu import (
    INTERSTITIAL_TIMEOUT,
    LEVEL_SELECT_CELL_COUNT,
    MENU_ATTRACT_TIMEOUT,
    MENU_TRANSITION_LATCH_SPACE_SCANCODE,
    YES_NO_CHOICE_N_CHAR,
    YES_NO_CHOICE_Y_CHAR,
    InterstitialTickOutcome,
    LevelSelectFireResult,
    LevelSelectStep,
    MenuIdleOutcome,
    MenuTransitionWaitOutcome,
    YesNoChoiceOutcome,
)


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


def step_level_select_page_down_d476(beda: int) -> LevelSelectStep:
    """``1010:D476`` (the level-select screen's bit-0x01 direction handler): ``BEDA += 3``
    (jump to the grid's other row/half), rejected (unchanged) when ``BEDA`` is already >= 3."""
    b = beda & 0xFF
    if b >= 3:
        return LevelSelectStep(beda=beda, accepted=False)
    return LevelSelectStep(beda=(b + 3) & 0xFF, accepted=True)


def step_level_select_page_up_d480(beda: int) -> LevelSelectStep:
    """``1010:D480`` (bit-0x02 direction handler): ``BEDA -= 3``, rejected when ``BEDA`` <= 2."""
    b = beda & 0xFF
    if b <= 2:
        return LevelSelectStep(beda=beda, accepted=False)
    return LevelSelectStep(beda=(b - 3) & 0xFF, accepted=True)


def step_level_select_decrement_d488(beda: int) -> LevelSelectStep:
    """``1010:D488`` (bit-0x08 direction handler): ``BEDA -= 1``, rejected when ``BEDA`` == 0."""
    b = beda & 0xFF
    if b == 0:
        return LevelSelectStep(beda=beda, accepted=False)
    return LevelSelectStep(beda=(b - 1) & 0xFF, accepted=True)


def step_level_select_increment_d490(beda: int) -> LevelSelectStep:
    """``1010:D490`` (bit-0x04 direction handler): ``BEDA += 1``, rejected when ``BEDA`` == 5
    (:data:`~overkill.recovered.domain.menu.LEVEL_SELECT_UNPLAYABLE_CELL`, the grid's max index)."""
    b = beda & 0xFF
    if b == 5:
        return LevelSelectStep(beda=beda, accepted=False)
    return LevelSelectStep(beda=(b + 1) & 0xFF, accepted=True)


def resolve_level_select_fire_d424(beda: int) -> LevelSelectFireResult:
    """``1010:D424``: map the confirmed grid cell (``DS:BEDA``, 0-5) to ``DS:2356`` (the level
    global) -- unchanged for cells 0-4, the ``0xFFFF`` sentinel for cell 5.  The ASM computes
    this as ``ax = BEDA+1; if ax==6: ax=0; ax -= 1`` rather than a plain copy, which is what
    produces the sentinel for BEDA==5 specifically (``6 -> wraps to 0 -> dec -> 0xFFFF``)."""
    ax = ((beda & 0xFF) + 1) & 0xFFFF
    if ax == LEVEL_SELECT_CELL_COUNT:
        ax = 0
    return LevelSelectFireResult(level=(ax - 1) & 0xFFFF)


def advance_level_index_9744(v2356: int) -> int:
    """``1010:9744``: advance the level index ``DS:2356`` to the next of the six planets, wrapping
    after the last.  The ASM is ``inc [2356]; cmp [2356],6; jb keep; mov [2356],0`` -- increment,
    then reset to 0 once the incremented value reaches :data:`LEVEL_SELECT_CELL_COUNT` (6).  So the
    cycle is ``0->1->2->3->4->5->0`` (driven-oracle ``verify_native_level_advance_9744``).  This is
    the level-progression step taken on the scripted level-end transition (``9734``, the SCRIPTED
    exit target of :func:`~overkill.recovered.systems.frame_loop.detect_gameplay_transition`) and by
    the ``971A`` new-game/level-start setup.  Pure; the caller owns the ``DS:2356`` write.
    """
    n = ((v2356 & 0xFFFF) + 1) & 0xFFFF
    return 0 if n >= LEVEL_SELECT_CELL_COUNT else n


def step_interstitial_tick_d318(counter: int, *, fire_pressed: bool) -> InterstitialTickOutcome:
    """Pure model of one ``1010:D318`` interstitial-loop iteration's decision.

    Bumps the loop counter (``DS:BED8``, wraps mod 0x10000 like the real ``INC``) and reports
    which of three continuations fires: the counter exceeding ``INTERSTITIAL_TIMEOUT`` (200,
    checked FIRST, strictly-greater matching the ASM's own ``JA``) exits regardless of input,
    else FIRE (the caller's decoded ``DS:98BE == 0x10``) also exits, else the loop continues.
    Both exits wait for FIRE to be released before the real routine actually returns to its
    caller (``call_input_until_release`` in ``overkill.gameplay.frame_orchestration.run_
    interstitial_timed_input_loop_d318``) -- a timing gate with no further decision content, not
    modelled here.  The chain of graphics/sound/starfield child calls that redraw this screen
    every real iteration are pure presentation glue, also not modelled.
    """
    new_counter = (counter + 1) & 0xFFFF
    if new_counter > INTERSTITIAL_TIMEOUT:
        return InterstitialTickOutcome(counter=new_counter, result="exit_timeout")
    if fire_pressed:
        return InterstitialTickOutcome(counter=new_counter, result="exit_fire")
    return InterstitialTickOutcome(counter=new_counter, result="loop")


def step_menu_transition_wait_ce40(cx: int, latched_key: int, *, fire_pressed: bool) -> MenuTransitionWaitOutcome:
    """Pure model of one ``1010:CE40`` menu-transition-wait iteration.

    Checked FIRST, matching the ASM's own order: if ``latched_key`` (``DS:98C3``) is already
    non-zero at entry -- set by THIS ROUTINE on an earlier iteration, or by an unrelated screen
    sharing the same global -- exits immediately with no poll/wait this iteration.  Otherwise
    polls, latches ``MENU_TRANSITION_LATCH_SPACE_SCANCODE`` into the (still-zero) ``latched_key``
    when FIRE is pressed this iteration (the exit via that new latch happens on the NEXT call,
    not this one -- the real ASM still runs its retrace wait + LOOP decrement before returning),
    decrements ``cx`` (wraps mod 0x10000 like the real ``LOOP``), and exits once it reaches 0,
    else loops.  The VGA-retrace wait (``50C9``) and the keyboard poll (``0162``) are pure
    timing/input plumbing -- ``fire_pressed`` is this function's only input from the poll.
    """
    if latched_key != 0:
        return MenuTransitionWaitOutcome(cx=cx, latched_key=latched_key, result="exit_latched")
    new_latch = MENU_TRANSITION_LATCH_SPACE_SCANCODE if fire_pressed else latched_key
    new_cx = (cx - 1) & 0xFFFF
    if new_cx != 0:
        return MenuTransitionWaitOutcome(cx=new_cx, latched_key=new_latch, result="loop")
    return MenuTransitionWaitOutcome(cx=new_cx, latched_key=new_latch, result="exit_timeout")


def step_yes_no_choice_989e(*, n_pressed: bool, y_pressed: bool) -> YesNoChoiceOutcome:
    """Pure model of one ``1010:989E`` yes/no choice iteration.

    Checks N FIRST, matching the ASM's own order: if pressed, exits immediately (``DS:22B4``
    stays ``'N'``, ``Y`` is never even written or checked this iteration).  Otherwise writes
    ``'Y'`` and checks Y; exits if pressed, else loops (``DS:22B4`` is left showing ``'Y'`` in
    the loop case too, since that write already happened before the idle re-check).  Both exits
    return to the same caller address in the real ASM -- the caller distinguishes them via
    ``result`` (or, in the real ASM, by re-reading ``DS:22B4``/the flag bytes itself)."""
    if n_pressed:
        return YesNoChoiceOutcome(display_char=YES_NO_CHOICE_N_CHAR, result="exit_no")
    if y_pressed:
        return YesNoChoiceOutcome(display_char=YES_NO_CHOICE_Y_CHAR, result="exit_yes")
    return YesNoChoiceOutcome(display_char=YES_NO_CHOICE_Y_CHAR, result="loop")


TANDY_MODE_FLAG = 0x0001  # CS:95BC == 1 -- the same Tandy-mode convention D318 checks


def tandy_status_cache_reset_5145(mode: int) -> bool:
    """Pure ``1010:5145`` GATE ONLY: does the routine skip its whole body via an immediate ``ret``?

    Part of the post-level-confirm new-game HUD/status-bar setup (``971A`` -> ``5C9A`` ->
    ``5BEE`` -> ``5145``). ``False`` (``mode != 1``, the real cold-start session's own observed
    value) means the real ASM takes an immediate ``ret`` -- a true no-op, verified against the
    VM. ``True`` (``mode == 1``, matching D318's own Tandy-mode convention) means the routine
    falls through into MORE than a first read suggested: not just a single status-cache zero,
    but a second write (``CS:95A4 = 0xA000``, likely a VGA segment constant) followed by a
    non-standard jump exit (NOT a plain ``ret`` back to the caller) -- that tail is genuinely
    unverified (no demo observed taking it yet) and is deliberately NOT modelled by any hook or
    further pure function here. Don't compose past this gate until a demo exercises ``True``."""
    return (mode & 0xFFFF) == TANDY_MODE_FLAG
