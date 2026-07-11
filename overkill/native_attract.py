"""Native ATTRACT driver -- the steppable D007 loop that ties the recovered pieces together.

Front-end slice C.  The cold-boot attract (1010:D007) loops: draw the current scene, advance the scene
machine, exit on FIRE / any key / the terminal scene.  This composes the already-recovered parts into
one steppable object (the front-end counterpart of the gameplay `NativeGame`):

* the SEQUENCER -- `systems.attract.attract_frame_step` (scene id / countdown / auto-fire) + the
  `attract_loop_exits` exit test;
* the per-frame ACTION each scene needs, which the CALLER performs:
  - scenes 1..7  -> ``draw_cell`` (the `native_video.attract` scene-cell render),
  - scenes >= 8  -> ``gameplay`` (run the native frame; ``injected_fire`` carries the auto-fire beat),
  - scene 0x13   -> ``exit``.

Scene 0's `D160` is the scroll-in gameplay-SETUP (recovered as
`native_frame.attract_scene0_setup_d160`): while it runs, the driver emits a ``scene0_setup`` action and
the caller runs the setup until it reports done, then the machine advances to scene 1.
"""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.domain.attract import AttractSceneState
from overkill.recovered.systems.attract import (
    TERMINAL_SCENE,
    attract_frame_step,
    attract_loop_exits,
)

SETUP_SCENE = 0              # scene 0 (D160): the scroll-in gameplay-setup
FIRST_CELL_SCENE = 1
LAST_CELL_SCENE = 7
SCENE_COUNTDOWN_START = 0x64


@dataclass(frozen=True)
class AttractAction:
    """What the caller does THIS frame: ``scene0_setup`` (run the D160 scroll-in), ``draw_cell`` (with
    ``scene``), ``gameplay`` (with ``injected_fire`` = the auto-fire beat or None), or ``exit`` (leave
    the attract, back to the menu)."""
    kind: str                       # "scene0_setup" | "draw_cell" | "gameplay" | "exit"
    scene: int = 0
    injected_fire: "int | None" = None


@dataclass(frozen=True)
class NativeAttract:
    """The D007 attract loop as a steppable state object."""
    state: AttractSceneState

    @classmethod
    def start(cls) -> "NativeAttract":
        """Begin the attract at scene 0 (the D160 scroll-in setup)."""
        return cls(AttractSceneState(scene=SETUP_SCENE, countdown=SCENE_COUNTDOWN_START,
                                     autofire_tick=0))

    def step(self, *, fire_pressed: bool, any_key: bool,
             setup_done: bool = False) -> "tuple[NativeAttract, AttractAction]":
        """One D007 frame: decide the action for the CURRENT scene, then advance the scene machine.
        ``setup_done`` is the caller's report from the scene-0 setup.  Returns ``(next_driver, action)``."""
        scene = self.state.scene
        if attract_loop_exits(scene, 0x10 if fire_pressed else 0, 1 if any_key else 0):
            return self, AttractAction("exit")
        if scene == SETUP_SCENE:                      # D160 scroll-in: stay until the caller says done
            if not setup_done:
                return self, AttractAction("scene0_setup", scene=scene)
            nxt = NativeAttract(AttractSceneState(scene=FIRST_CELL_SCENE,
                                                  countdown=SCENE_COUNTDOWN_START, autofire_tick=0))
            return nxt, AttractAction("draw_cell", scene=FIRST_CELL_SCENE)
        adv = attract_frame_step(self.state)          # advance the recovered scene machine
        nxt = NativeAttract(adv.state)
        if scene >= 8:
            return nxt, AttractAction("gameplay", scene=scene, injected_fire=adv.injected_input)
        return nxt, AttractAction("draw_cell", scene=scene)


__all__ = ["NativeAttract", "AttractAction", "FIRST_CELL_SCENE", "LAST_CELL_SCENE", "TERMINAL_SCENE"]
