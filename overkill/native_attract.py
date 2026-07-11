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

Scene 0's `D160` gameplay-setup is a declared recovery gap, so a native session starts the attract at
scene 1 (the first cell scene); reaching scene 0 raises fail-loud via `attract_frame_step`.
"""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.domain.attract import AttractSceneState
from overkill.recovered.systems.attract import (
    TERMINAL_SCENE,
    attract_frame_step,
    attract_loop_exits,
)

FIRST_CELL_SCENE = 1          # scene 0 (D160 gameplay-setup) is a gap; a native attract starts here
LAST_CELL_SCENE = 7
SCENE_COUNTDOWN_START = 0x64


@dataclass(frozen=True)
class AttractAction:
    """What the caller does THIS frame: ``draw_cell`` (with ``scene``), ``gameplay`` (with
    ``injected_fire`` = the auto-fire beat or None), or ``exit`` (leave the attract, back to the menu)."""
    kind: str                       # "draw_cell" | "gameplay" | "exit"
    scene: int = 0
    injected_fire: "int | None" = None


@dataclass(frozen=True)
class NativeAttract:
    """The D007 attract loop as a steppable state object."""
    state: AttractSceneState

    @classmethod
    def start(cls) -> "NativeAttract":
        """Begin the attract at the first cell scene (scene 0's D160 setup is a declared gap)."""
        return cls(AttractSceneState(scene=FIRST_CELL_SCENE, countdown=SCENE_COUNTDOWN_START,
                                     autofire_tick=0))

    def step(self, *, fire_pressed: bool, any_key: bool) -> "tuple[NativeAttract, AttractAction]":
        """One D007 frame: decide the action for the CURRENT scene, then advance the scene machine.
        Returns ``(next_driver, action)``."""
        scene = self.state.scene
        if attract_loop_exits(scene, 0x10 if fire_pressed else 0, 1 if any_key else 0):
            return self, AttractAction("exit")
        adv = attract_frame_step(self.state)          # advance (fails loud on scene 0's D160 gap)
        nxt = NativeAttract(adv.state)
        if scene >= 8:
            return nxt, AttractAction("gameplay", scene=scene, injected_fire=adv.injected_input)
        return nxt, AttractAction("draw_cell", scene=scene)


__all__ = ["NativeAttract", "AttractAction", "FIRST_CELL_SCENE", "LAST_CELL_SCENE", "TERMINAL_SCENE"]
