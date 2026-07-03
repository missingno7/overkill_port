"""Attract/story scene-sequencer state -- the ``1010:D007`` loop's scene machine (domain form).

OVERKILL's intro/attract flow is a small scene machine driven by three DS cells (grounded by the
D007/D04D/D080..D0EF disassembly, 2026-07-04 -- see ``systems/attract.py`` for the rules):

* ``DS:BE06`` -- the current **scene id**.  Indexes a 6-byte descriptor table at ``DS:BE18`` (whose
  word links into the ``CS:0BE4`` panel-cell directory -- each scene has a graphic cell drawn every
  frame at cell cursor (0x1F, 0x18)).  Scene ``0`` takes a special branch (``D160``, not recovered);
  scene ``0x13`` is terminal (the frame loop returns to its caller instead of polling input).
* ``DS:BE08`` -- the per-scene **countdown**: decremented once per frame; at zero it reloads to
  ``0x64`` (100 ticks) and ``BE06`` advances to the next scene (auto-advance).
* ``DS:BE0A`` -- the **demo auto-fire cycle**: a mod-``0x14`` counter; on ticks ``0x0F/0x11/0x13`` the
  sequencer injects a synthetic FIRE (``DS:98BE = 0x10``) and drives the action fan-out (``A067`` with
  ``BP = 237C``) -- the attract mode literally plays the game with scripted fire presses.  Active only
  for scenes ``>= 8`` while the countdown is ``>= 0x14``.

The loop exits to its caller on a real FIRE press, any key, or the terminal scene.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Countdown reload when a scene's timer expires (100 frames per scene).
SCENE_COUNTDOWN_RELOAD = 0x64
#: The demo auto-fire cycle length (BE0A wraps to 0 at this value).
AUTOFIRE_CYCLE = 0x14
#: The BE0A ticks that inject a synthetic FIRE press.
AUTOFIRE_TICKS = frozenset((0x0F, 0x11, 0x13))
#: Scenes below this id never run the demo auto-fire.
AUTOFIRE_MIN_SCENE = 0x08
#: The countdown floor below which the auto-fire stops (scene about to change).
AUTOFIRE_MIN_COUNTDOWN = 0x14
#: The terminal scene id: the D007 frame loop returns to its caller instead of polling input.
TERMINAL_SCENE = 0x13
#: Scene 0 takes the special D160 branch (not recovered yet).
SPECIAL_SCENE_0 = 0x00


@dataclass(frozen=True)
class AttractSceneState:
    """The scene machine's three DS cells (BE06/BE08/BE0A)."""

    scene: int        # DS:BE06
    countdown: int    # DS:BE08
    autofire_tick: int  # DS:BE0A


@dataclass(frozen=True)
class AttractFrameStep:
    """One D04D per-frame advance of the scene machine.

    ``injected_input`` is the synthetic ``DS:98BE`` value the demo auto-fire produced this frame
    (``None`` when the auto-fire block did not run at all; ``0`` when it ran and cleared the input
    without firing).  ``run_fanout`` mirrors the unconditional ``A067`` drive inside the auto-fire
    block.  ``scene_advanced`` is True when the countdown expired (the original then re-enters the
    scene-descriptor setup at ``D0DB..``, whose entry actions are a declared gap).
    """

    state: AttractSceneState
    injected_input: int | None
    run_fanout: bool
    scene_advanced: bool
