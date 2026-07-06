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
from overkill.recovered.domain.frame_loop import FireControlState, FrameInput, PlayerFrameStep
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.domain.scroll import ScrollState, ScrollTickOutcome
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.frame_loop import (
    native_action_fanout_step,
    native_object_pass,
    native_player_frame_step,
)
from overkill.recovered.systems.scroll import step_scroll_with_milestones


@dataclass(frozen=True)
class NativeGame:
    """A cold-loaded level + its gameplay state, advanced by the recovered frame systems with no VM."""

    level: NativeLevel
    state: NativeGameState
    origin_x: int = 0  # DS:234E scroll (the tile-probe origin)
    row_base: int = 0  # DS:2350 scroll (the tile-probe row base)
    # The rest of A6FE/A74E's forward-scroll bookkeeping, carried between ticks so step_scroll can run
    # the pure A66F gate natively (see overkill.recovered.systems.scroll).  Not tile-probe-consumed;
    # defaults match a level's post-load state (DS:234C = the fixed row-source start, forward flag set).
    row_source: int = 0x5B00  # DS:234C
    rows_to_milestone: int = 0  # DS:A978
    forward_last: bool = True  # DS:2354 == 0
    fire: FireControlState = dataclasses.field(default_factory=FireControlState)

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

    def step_action_fanout(
        self,
        *,
        input_flags: int,
        repeat_9790: int,
        state_232a: int,
        scroll_2350: int,
        bdac: int,
        a958: int,
        be06: int,
        source_index: int,
        source_x: int,
        source_y: int,
        read_ds_word,
    ) -> "NativeGame":
        """Run the action/fire fan-out's EARLY-only slice over the current state + carried fire control.

        ``input_flags`` is normally the player stage's decoded button byte
        (:attr:`~overkill.recovered.domain.frame_loop.PlayerFrameStep.input_flags`); the rest are the
        still-VM-owned per-frame inputs :class:`~overkill.recovered.domain.frame_loop.FireControlState`
        documents, until A66F (scroll) and the weapon-equip subsystem are native too.  See
        :func:`~overkill.recovered.systems.frame_loop.native_action_fanout_step` for which frames this
        declines (leaves VM-owned).
        """
        new_state, new_fire = native_action_fanout_step(
            self.state, self.fire, input_flags=input_flags, repeat_9790=repeat_9790, state_232a=state_232a,
            scroll_2350=scroll_2350, bdac=bdac, a958=a958, be06=be06, source_index=source_index,
            source_x=source_x, source_y=source_y, read_ds_word=read_ds_word,
        )
        return dataclasses.replace(self, state=new_state, fire=new_fire)

    @property
    def scroll(self) -> ScrollState:
        """This game's forward-scroll bookkeeping as one value object (the A66F/A6FE fields)."""
        return ScrollState(
            origin_x=self.origin_x, row_base=self.row_base, row_source=self.row_source,
            rows_to_milestone=self.rows_to_milestone, forward_last=self.forward_last,
        )

    def step_scroll(self, *, a47c: int, a47e: int, a480: int) -> tuple["NativeGame", ScrollTickOutcome | None]:
        """Run the native forward world-scroll tick (A66F gate -> A6FE), advancing origin_x/row_base.

        This runs in the real frame order right BEFORE the action fan-out (A66F at 9BAC precedes A067
        at 9BAF), so the row_base it produces is the DS:2350 the fan-out and object stages then read.
        The gate globals DS:A47C/A47E/A480 are per-frame inputs (like the other ``step_*`` methods'
        kwargs).  The once-per-level A66F milestones are composed natively
        (:func:`~overkill.recovered.systems.scroll.step_scroll_with_milestones`): the tick APPLIES at
        the milestone rows (live-traced) and ``outcome.milestone`` reports which fired -- 0x0E52 is a
        Tandy no-op; 0x0EA0 is the level-end arm whose memory actions the runtime (play_native) owns.
        """
        outcome = step_scroll_with_milestones(self.scroll, a47c=a47c, a47e=a47e, a480=a480)
        s = outcome.state
        game = dataclasses.replace(
            self, origin_x=s.origin_x, row_base=s.row_base, row_source=s.row_source,
            rows_to_milestone=s.rows_to_milestone, forward_last=s.forward_last,
        )
        return game, outcome

    def step_objects(self, update_globals: ObjectUpdateGlobals) -> "NativeGame":
        """Run the object-update pass over both pools, using this level's cold tile context.

        The caller supplies the per-frame gameplay globals (deltas, difficulty, tick, ...); this swaps in
        the level's cold :attr:`tile_context` so the object scan samples the cold-loaded terrain.
        """
        g = dataclasses.replace(update_globals, tiles=self.tile_context)
        return self.with_state(native_object_pass(self.state, g))

    def step(
        self,
        frame_input: FrameInput,
        *,
        no_clamp: bool = False,
        repeat_9790: int,
        state_232a: int,
        scroll_2350: int,
        bdac: int,
        a958: int,
        be06: int,
        source_index: int,
        source_x: int,
        source_y: int,
        read_ds_word,
        update_globals: ObjectUpdateGlobals,
        scroll_gate: tuple[int, int, int] = (0, 0, 0),
        run_object_pass: bool = True,
    ) -> tuple["NativeGame", PlayerFrameStep]:
        """Run one whole native game tick: player -> scroll -> action fan-out -> object scan, in the
        real 9B2E -> A66F -> A067 -> AA0D order (confirmed always in that order -- see
        ``overkill.probes.verify_native_forward_frames``), threading the player stage's own decoded
        ``input_flags`` into the fan-out automatically instead of making the caller chain the stages
        and thread that value by hand.

        Scroll (A66F) is run NATIVELY: ``scroll_gate`` is (DS:A47C, A47E, A480), and the native
        row_base it produces becomes the DS:2350 fed to the fan-out + the object scan's tile context
        (which reads this game's own origin_x/row_base).  ``scroll_2350`` is now only a FALLBACK, used
        for the one tick A66F declines (a rare boss/milestone branch -- see
        :meth:`step_scroll`); on a normal tick the native row_base overrides it.

        The remaining keyword arguments are ``step_action_fanout``'s / ``step_objects``' own
        still-VM-owned inputs (see their docstrings) -- this method is composition, not new coverage;
        it does not decide what those values are for a given tick.
        """
        game, player_step = self.step_player(frame_input, no_clamp=no_clamp)
        a47c, a47e, a480 = scroll_gate
        game, scroll_outcome = game.step_scroll(a47c=a47c, a47e=a47e, a480=a480)
        # Normal tick: the native row_base is the DS:2350 downstream reads.  Declined tick (outcome
        # None, scroll left VM-owned): fall back to the caller-supplied VM scroll_2350.
        fanout_scroll = scroll_2350 if scroll_outcome is None else game.row_base
        game = game.step_action_fanout(
            input_flags=player_step.input_flags, repeat_9790=repeat_9790, state_232a=state_232a,
            scroll_2350=fanout_scroll, bdac=bdac, a958=a958, be06=be06,
            source_index=source_index, source_x=source_x, source_y=source_y, read_ds_word=read_ds_word,
        )
        # run_object_pass=False lets a caller that owns the FULL A9D3..AA25 behavior walk (the
        # image-backed adapters/behavior_walk registry, shadow-proven) replace this dataclass
        # object pass instead of double-stepping the shared logic ids.
        if run_object_pass:
            game = game.step_objects(update_globals)
        return game, player_step
