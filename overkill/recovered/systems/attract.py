"""Pure attract/story scene-sequencer rules -- the ``1010:D007``/``D04D`` scene machine.

Recovered from the D007..D0EF disassembly (2026-07-04; see ``domain/attract.py`` for the state model
and the cell-by-cell readout).  VERIFICATION STATUS: **demo-witnessed** by
``overkill/probes/verify_native_attract.py`` against the live D04D on two cold-start replays:
``demo_cold_start_attract_interrupt_synthetic`` (399 transitions, scenes 0x0..0x5) and
``demo_cold_start_wait_synthetic`` (1699 transitions, the WHOLE scene range 0x0..0x12 incl. the whole
auto-fire window 0x8..0x12 with 891 auto-fire transitions) -- 0 fails.  Scene-0's D160 branch and the
next-scene entry actions (D0DB tail) remain declared gaps (fail-loud), outside the witnessed rules.

Pure: no VM, no ``cpu``/``mem``.  The caller owns where BE06/BE08/BE0A/98BE live.
"""
from __future__ import annotations

from overkill.recovered.domain.attract import (
    AUTOFIRE_CYCLE,
    AUTOFIRE_MIN_COUNTDOWN,
    AUTOFIRE_MIN_SCENE,
    AUTOFIRE_TICKS,
    SCENE_COUNTDOWN_RELOAD,
    SPECIAL_SCENE_0,
    TERMINAL_SCENE,
    AttractFrameStep,
    AttractSceneState,
)
from overkill.recovered.domain.gaps import RecoveryGap


def attract_autofire_runs(scene: int, countdown: int) -> bool:
    """The ``D080`` gate: the demo auto-fire block runs only for scenes >= 8 with countdown >= 0x14.

    ASM: ``cmp [BE06],8 / jb skip ; cmp [BE08],14h / jb skip``.
    """
    return scene >= AUTOFIRE_MIN_SCENE and countdown >= AUTOFIRE_MIN_COUNTDOWN


def attract_autofire_tick(autofire_tick: int) -> tuple[int, int]:
    """One ``D08E..D0B9`` auto-fire advance: ``(new_tick, injected_98be)``.

    ASM: ``mov [98BE],0 ; inc [BE0A] ; cmp [BE0A],14h / jb + ; mov [BE0A],0`` then FIRE (``98BE=10h``)
    exactly on ticks ``0F/11/13``.  The input byte is *overwritten* every auto-fire frame (real input
    is discarded during the demo), so the return is the whole new ``98BE`` value.
    """
    new_tick = (autofire_tick + 1) & 0xFFFF
    if new_tick >= AUTOFIRE_CYCLE:
        new_tick = 0
    injected = 0x10 if new_tick in AUTOFIRE_TICKS else 0x00
    return new_tick, injected


def attract_scene_countdown(scene: int, countdown: int) -> tuple[int, int, bool]:
    """The ``D0D4..D0E5`` per-frame countdown: ``(new_scene, new_countdown, advanced)``.

    ASM: ``dec [BE08] / jz advance ; ret`` -- and on advance ``mov [BE08],64h ; inc [BE06]``.  The
    original then re-enters the next scene's descriptor setup (``D0DB..`` tail past ``D0EF``); those
    scene-entry actions are a declared gap (the caller must treat ``advanced=True`` accordingly).
    """
    new_countdown = (countdown - 1) & 0xFFFF
    if new_countdown != 0:
        return scene, new_countdown, False
    return (scene + 1) & 0xFFFF, SCENE_COUNTDOWN_RELOAD, True


def attract_frame_step(state: AttractSceneState) -> AttractFrameStep:
    """One whole ``D04D`` per-frame scene-machine advance (state cells only).

    Composes the gate + auto-fire + countdown in the original order.  The scene-cell draw, the
    ``A212`` chain pre-update and the ``A067`` fan-out drive are the caller's (the fan-out runs
    unconditionally inside the auto-fire block -- ``run_fanout``); scene ``0``'s special ``D160``
    branch is NOT recovered and fails loud here.
    """
    if state.scene == SPECIAL_SCENE_0:
        raise RecoveryGap("1010:D0D1 -> D160 (attract scene 0 special branch)",
                          "scene 0 semantics are not recovered; do not guess")
    injected: int | None = None
    run_fanout = False
    tick = state.autofire_tick
    if attract_autofire_runs(state.scene, state.countdown):
        tick, injected = attract_autofire_tick(tick)
        run_fanout = True
    scene, countdown, advanced = attract_scene_countdown(state.scene, state.countdown)
    return AttractFrameStep(
        state=AttractSceneState(scene=scene, countdown=countdown, autofire_tick=tick),
        injected_input=injected,
        run_fanout=run_fanout,
        scene_advanced=advanced,
    )


def attract_loop_exits(scene: int, input_98be: int, any_key_98c3: int) -> bool:
    """Whether the ``D007`` frame loop returns to its caller this frame.

    ASM (``D028..D03E``): scene ``0x13`` skips the input poll and exits unconditionally; otherwise the
    loop exits on FIRE (``98BE & 10h``) or any pressed key (``byte [98C3] != 0``), else repeats.
    """
    if scene == TERMINAL_SCENE:
        return True
    return (input_98be & 0x10) != 0 or (any_key_98c3 & 0xFF) != 0
