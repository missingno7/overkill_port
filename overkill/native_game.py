"""Native game runner -- run a level's frames VM-free over cold-loaded data (the standalone backbone).

This is where the two halves meet: the cold-loaded level data (``asset_codecs.load_native_level``) and
the recovered per-frame systems (``recovered.systems.frame_loop``).  A :class:`NativeGame` pairs a
cold-loaded :class:`NativeLevel` with the evolving :class:`NativeGameState`, and advances it each frame by
running the recovered 9B2E stages -- with no VM, over level data decoded entirely from the original files
(the ``OVERKILL.EXE`` image + the ``OVERKILL`` container).

It is the standalone half of the hybrid->native model.  Today it runs the stages that are recovered and
verified -- the player stage (input decode + view-anchor movement) and the object-update pass over the
cold tile context.  Stages still owned by the VM (scripted input 99F6, the A067 action fan-out, the 9CB6
contact probe, the coordinate rings) are not run here; they join as each becomes a pure system.

(Distinct from :mod:`overkill.game_core`, which is the backend-protocol seam -- video/input/audio ports;
this module is the game-state runner those backends will eventually drive.)
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from overkill.asset_codecs.native_level import NativeLevel, load_native_level
from overkill.recovered.adapters.cold_level_adapter import level_tile_context_from_native
from overkill.recovered.domain.frame_loop import FrameInput, PlayerFrameStep
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.frame_loop import native_object_pass, native_player_frame_step


@dataclass(frozen=True)
class NativeGame:
    """A cold-loaded level + its gameplay state, advanced by the recovered frame systems with no VM."""

    level: NativeLevel
    state: NativeGameState
    origin_x: int = 0  # DS:234E scroll (the tile-probe origin)
    row_base: int = 0  # DS:2350 scroll (the tile-probe row base)

    @classmethod
    def load_level(
        cls,
        exe_image,
        container,
        level_num: int,
        state: NativeGameState,
        *,
        origin_x: int = 0,
        row_base: int = 0,
    ) -> "NativeGame":
        """Cold-load level ``level_num`` from the EXE image + container, paired with a starting state."""
        return cls(load_native_level(exe_image, container, level_num), state, origin_x, row_base)

    @property
    def tile_context(self) -> LevelTileContext:
        """The recovered tile-probe context over this level's cold-loaded tile plane + class table."""
        return level_tile_context_from_native(self.level, self.origin_x, self.row_base)

    def with_state(self, state: NativeGameState) -> "NativeGame":
        return dataclasses.replace(self, state=state)

    def step_player(self, frame_input: FrameInput, *, no_clamp: bool = False) -> tuple["NativeGame", PlayerFrameStep]:
        """Run the player stage (input decode + view-anchor movement) over the current state."""
        step = native_player_frame_step(self.state.special_pool, frame_input, no_clamp=no_clamp)
        return self.with_state(dataclasses.replace(self.state, special_pool=step.special_pool)), step

    def step_objects(self, update_globals: ObjectUpdateGlobals) -> "NativeGame":
        """Run the object-update pass over both pools, using this level's cold tile context.

        The caller supplies the per-frame gameplay globals (deltas, difficulty, tick, ...); this swaps in
        the level's cold :attr:`tile_context` so the object scan samples the cold-loaded terrain.
        """
        g = dataclasses.replace(update_globals, tiles=self.tile_context)
        return self.with_state(native_object_pass(self.state, g))
