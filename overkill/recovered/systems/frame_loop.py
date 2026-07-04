"""The native frame controller -- the VM-free per-frame sequence (pillar 3 skeleton).

``1010:9B2E`` is the game-state controller: each frame it polls input, updates the player
view-anchor from that input, runs the object-update pass, fans out actions, resolves
contacts, and maintains the coordinate rings -- all over VM memory.  This module is the
VM-free counterpart: it sequences the *recovered systems* over a :class:`NativeGameState`,
the same order, with no VM.

It grows one stage at a time as each 9B2E stage becomes a pure system.  Today it covers the
two stages that are native and share a data flow -- the input decode and the movement bits --
composed end-to-end (raw key state -> decoded button byte -> view-anchor step), proven equal
to the VM by ``overkill.probes.verify_native_frame_loop``.  Stages still owned by the VM
(the A212 anchor pre-update, the 8546 secondary fire, the A067 action fan-out, the 9CB6
contact probe, the coordinate rings) are noted at their call sites and join as they land.

The input stage here models the *keyboard* path.  When the scripted-input mode is active
(DS:A47C != 0, boss/cutscene auto-movement) 9B2E first runs 1010:99F6, which overwrites the
button byte with a scripted value instead of decoding the keyboard; that scripted-input stage
is not native yet, so ``native_player_frame_step`` applies to the normal-gameplay frames
(no_clamp == False).  The no-clamp movement path itself is still exercised by the standalone
movement-bits verify, which reads the VM's actual button byte.
"""
from __future__ import annotations

import dataclasses

from overkill.recovered.domain.frame_loop import (
    DEMO_TICK_DEFAULT_RELOAD,
    DemoCounterTickOutcome,
    FireControlState,
    FrameAccumulatorShiftOutcome,
    FrameInput,
    FrameScanEntryOutcome,
    PlayerFrameStep,
)
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.systems.action_spawns import native_a067
from overkill.recovered.systems.input import decode_keyboard_input_flags
from overkill.recovered.systems.movement import step_view_anchor_by_input
from overkill.recovered.systems.object_update import native_object_pass_in_place, native_object_update_pool
from overkill.recovered.systems.objects import apply_player_shot_to_pool

# View-anchor record field offsets the controller writes (cf. recovered.views.object_slots);
# the pure systems layer names the small set it touches rather than importing the bridge views.
_OFF_X = 0x02
_OFF_Y = 0x04
_VIEW_ANCHOR_SLOT = 0  # special_pool holds the single DS:237C view-anchor slot


def decode_frame_input(frame_input: FrameInput) -> int:
    """Frame stage 1 (9B2E:9B3A): decode the per-frame input source to the button byte.

    The native controller decodes from the raw key state itself, so the rest of the frame
    consumes the same DS:98BE the VM would -- without the VM's INT 9 path.
    """
    return decode_keyboard_input_flags(frame_input.control_map, frame_input.key_state)


def native_player_frame_step(
    special_pool: ObjectPool, frame_input: FrameInput, *, no_clamp: bool
) -> PlayerFrameStep:
    """Frame stages 1->2 composed: decode input, then apply the movement bits to the anchor.

    Mirrors 9B2E from the input poll through the four direction bits (9B6F..9B94): decode the
    button byte, then step the view-anchor slot (DS:237C, ``special_pool`` slot 0) via the
    recovered :func:`step_view_anchor_by_input`.  ``no_clamp`` is the DS:A47C movement-mode
    gate the up-step consults.  Returns the updated pool plus the decoded flags the later
    action/fire stages will consume.
    """
    input_flags = decode_frame_input(frame_input)
    move = step_view_anchor_by_input(
        special_pool.x_word(_VIEW_ANCHOR_SLOT),
        special_pool.y_word(_VIEW_ANCHOR_SLOT),
        input_flags,
        no_clamp=no_clamp,
    )
    new_pool = special_pool
    if move.stepped:
        new_pool = (new_pool
                    .with_word(_VIEW_ANCHOR_SLOT, _OFF_X, move.x_word)
                    .with_word(_VIEW_ANCHOR_SLOT, _OFF_Y, move.y_word))
    return PlayerFrameStep(special_pool=new_pool, input_flags=input_flags, moved=move.stepped)


def native_object_pass(state: NativeGameState, update_globals: ObjectUpdateGlobals) -> NativeGameState:
    """Frame stage (A940 -> A9E0 object scan): advance the gameplay + effect pools VM-free.

    The VM's object scan walks the effect table (DS:32CA pointers) then the gameplay table
    (DS:8D12 pointers), dispatching each active slot to its behaviour; this is the VM-free
    counterpart -- run the object-update driver over the two scanned pools.  The view-anchor
    (``special_pool``) is *not* part of this scan (it is the player stage's, updated in 9B2E),
    so it is left untouched here.

    The effect walk runs FIRST, order-dependently (:func:`native_object_pass_in_place`): each
    effect-pool scanner's own 62F6 contact scan reads the GAMEPLAY pool as its candidates (always
    the gameplay pool, never the effect pool itself, regardless of which pool the scanner lives in
    -- see :func:`object_overlap_scan_62f6`), so an effect object can deactivate a gameplay candidate
    mid-scan; the gameplay walk that follows must see that death (a killed candidate is skipped by
    the whole-pool "inactive -> skip" gate, exactly like the VM).  Composing the two SEPARATELY
    (each from the same frozen entry snapshot, as this function used to) drops that cross-pool kill
    entirely -- a real, confirmed forward-carry-harness divergence (a candidate slot the VM
    deactivates stays "alive" in the snapshot composition; see verify_native_forward_frames' L2/L1/
    L3/L4/L5 walls, root-caused via a live write-watcher on the killed slot's active word landing at
    1010:BF1B, an effect-pool scanner's own collision tail). The gameplay walk's own movement stays
    the existing, whole-pool-verified snapshot pass (:func:`native_object_update_pool`) -- a
    gameplay-pool object scanning OTHER gameplay-pool objects for contact (enemy-vs-enemy) is a
    separate, not-yet-modelled case and stays VM-owned exactly as before.

    Verified against the VM at the gameplay-scan boundary (overkill.probes.verify_native_object_pass):
    one driver call over DS:2B5C reproduces the VM's whole gameplay pass byte-for-byte (every active
    native-logic slot) for the movement-only half this composes with. The effect walk's own in-place
    pass is separately verified by overkill.probes.verify_native_object_pass_in_place.
    """
    effect_pool_out, gameplay_after_effect_kills = native_object_pass_in_place(
        state.effect_pool, state.object_pool, update_globals, entry_tick=update_globals.tick,
    )
    return dataclasses.replace(
        state,
        object_pool=native_object_update_pool(gameplay_after_effect_kills, update_globals),
        effect_pool=effect_pool_out,
    )


def native_action_fanout_step(
    state: NativeGameState,
    fire: FireControlState,
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
) -> tuple[NativeGameState, FireControlState]:
    """Frame stage (9B2E's A067 child, EARLY-only slice): the action-trigger gate + early-level fire tails.

    Composes the WHOLE-native ``native_a067`` (the entry gate + the A19F/A1C8 early tails) over the
    current gameplay pool + the carried :class:`FireControlState`, folding any spawned shots into
    ``state.object_pool`` (:func:`~overkill.recovered.systems.objects.apply_player_shot_to_pool`) and
    advancing the cursor/latch.  ``input_flags`` is the decoded DS:98BE button byte (the player stage's
    output, :attr:`~overkill.recovered.domain.frame_loop.PlayerFrameStep.input_flags`); the rest are the
    still-VM-owned per-frame inputs :class:`FireControlState` documents.

    Declines the SPAWN (``state.object_pool``/``fire.cursor_95da`` unchanged) for frames ``native_a067``
    itself declines: the FULL fan-out paths -- ``FULL_FANOUT`` needs the still-unrecovered A970-family
    held-action counters kept correct frame to frame (their per-child increment amount is not modelled;
    see the "the caller's, not part of the per-shot stamp" notes throughout ``systems/objects.py``),
    ``FULL_BDAC_A114``/``FULL_BDAC_A515`` have no native composition at all yet -- and a full pool at the
    very first shot.  Those frames leave the pool VM-owned, the same stance :func:`native_object_pass`
    takes for non-native logic ids: leave what is not yet recovered to the VM rather than guess.  The
    ``DS:A980`` latch write is NOT part of that decline -- it happens unconditionally before the path
    branch, so ``fire.latch_a980`` still advances correctly even on a declined-spawn frame.

    Verified against the VM at A067's own boundary (overkill.probes.verify_native_action_fanout_step):
    the special/effect pools + camera + hud (never touched by A067, in any path) and the latch always
    match a fresh VM projection; the gameplay pool + cursor are checked only on frames that actually ran
    a spawn, since a decline is a deliberate "not modelled yet", not a claim to reproduce the VM's FULL
    fan-out spawns without running them.
    """
    result = native_a067(
        state.object_pool, fire.cursor_95da,
        input_98be=input_flags, latch_a980=fire.latch_a980, repeat_9790=repeat_9790, state_232a=state_232a,
        scroll_2350=scroll_2350, bdac=bdac, a958=a958, be06=be06,
        source_index=source_index, source_x=source_x, source_y=source_y, read_ds_word=read_ds_word,
    )
    if result is None:
        # native_a067 only returns None PAST its "if not gate.runs: return A067Result(...)" early exit --
        # i.e. the entry gate DID arm (action_fanout_gate's only runs=True branch always writes
        # new_latch_word = 1) but the spawn path is FULL (not composed) or a full pool blocked the first
        # shot.  The gameplay pool + cursor stay VM-owned (we don't know what it spawned), but the A980
        # latch write happens unconditionally BEFORE the path branch, so it is still knowable -- applying
        # it here is not a guess, it's the one part of this frame native_a067's contract already proves.
        return state, dataclasses.replace(fire, latch_a980=0x0001)
    if not result.ran_fanout:
        return state, dataclasses.replace(fire, latch_a980=result.new_a980)  # only the latch changed
    new_pool = state.object_pool
    for shot in result.spawns:
        new_pool = apply_player_shot_to_pool(new_pool, shot)
    return (
        dataclasses.replace(state, object_pool=new_pool),
        FireControlState(latch_a980=result.new_a980, cursor_95da=result.final_cursor),
    )


SCRIPTED_TRANSITION_A47C = 0x0004   # DS:A47C == 4 -> the scripted "end/transition" command
DEATH_TAIL_MODE_2326 = 0x0003       # DS:2326 == 3 -> the 9AFF death tail is armed
DEATH_COUNTDOWN_LIMIT = 0x000F      # the anchor slot's +08 counter value that fires the transition
ANCHOR_STATE_ABSENT_A95A = 0xFFFF   # DS:A95A == FFFF (or A97A == 0) -> 9B2E reaches the 9AFF tail


def scripted_transition_fires_9b2e(a47c: int) -> bool:
    """The 9B2E scripted-transition gate: ``A344 = 1`` (and the frame ends) iff ``DS:A47C == 4``.

    9B2E clears ``A346``/``A344`` at entry each frame, runs the input poll (and ``99F6`` when the
    scripted-input mode ``A47C`` is non-zero), then checks ``A47C == 4`` -- the script's own
    "end/transition" command.  When it fires, 97B2 exits the gameplay loop via ``A344 -> jmp 9734``.
    """
    return (a47c & 0xFFFF) == SCRIPTED_TRANSITION_A47C


def death_tail_transition_9aff(v2326: int, anchor_counter_after_inc: int, a97a: int
                               ) -> tuple[bool, bool, bool]:
    """The 9AFF death-tail decision: ``(deactivate_and_a346, a342, counter_matters)``.

    9B2E reaches the ``9AFF`` tail when the tracked-anchor state is absent (``A95A == FFFF`` or
    ``A97A == 0``).  There: nothing happens unless ``DS:2326 == 3`` (the dying mode); then the anchor
    slot's ``+08`` counter (already incremented by the caller this frame) must reach ``0x0F`` -- at
    which point the slot deactivates, ``4DBF`` runs, and ``A346 = 1`` (97B2 exits via ``jmp 9908``);
    ``A342 = 1`` additionally iff ``A97A == 0`` (the game-over variant, ``jmp 9902``).

    Returns ``(transition, game_over_variant, counted)``: ``counted`` is True when the tail is in the
    counting mode (``2326 == 3``) at all -- the caller owns the actual ``+08`` increment.
    """
    if (v2326 & 0xFFFF) != DEATH_TAIL_MODE_2326:
        return False, False, False
    if (anchor_counter_after_inc & 0xFFFF) != DEATH_COUNTDOWN_LIMIT:
        return False, False, True
    return True, (a97a & 0xFFFF) == 0, True


def step_death_countdown_9e69(a47c: int, counter_2384: int, a362: int, a95a: int):
    """STAGE 1 of the death sequence: the ``1010:9E69`` per-frame ``A95A`` anchor-loss countdown.

    Recovered from the ``9E69..9E9C`` disassembly, confirmed by the driven oracle
    ``verify_native_death_countdown.py`` (the branch polarity was pinned there, not by eye).  The
    countdown is gated off (``A95A``/``A362`` unchanged) when ``DS:A47C == 1`` (``9E69``) or the death
    counter ``DS:2384 >= 3`` (``9E71``).  Otherwise it toggles ``DS:A362`` (``inc; and 1``) and, only
    on the ``A362 == 0`` frames (``9E95``), decrements ``DS:A95A`` (``9E98``).  When A95A wraps
    ``0 -> FFFF`` the anchor is lost and the 9AFF death tail (:func:`step_death_tail_9aff`) becomes
    reachable.

    Returns ``(new_a362, new_a95a, anchor_lost)``.  Pure: the caller owns the DS reads/writes and the
    block's other side effects (BEFF/A95C/etc., not part of this countdown).
    """
    a362, a95a = a362 & 0xFFFF, a95a & 0xFFFF
    if (a47c & 0xFFFF) == 1 or (counter_2384 & 0xFFFF) >= 3:
        return a362, a95a, False
    new_a362 = (a362 + 1) & 0x01
    if new_a362 != 0:
        return new_a362, a95a, False
    new_a95a = (a95a - 1) & 0xFFFF
    return new_a362, new_a95a, new_a95a == 0xFFFF


def death_tail_reached_9aff(a95a: int, a97a: int) -> bool:
    """Whether 9B2E branches into the ``9AFF`` death tail: the tracked anchor state is absent."""
    return (a95a & 0xFFFF) == ANCHOR_STATE_ABSENT_A95A or (a97a & 0xFFFF) == 0


def step_death_tail_9aff(a95a: int, a97a: int, v2326: int, anchor_counter: int):
    """One ``1010:9AFF`` death-tail stage: advance the death counter + maybe fire the exit.

    The STATEFUL half of the death exit (:func:`detect_gameplay_transition` is the stateless verdict
    given the already-incremented counter; this OWNS the increment).  Reached only when
    :func:`death_tail_reached_9aff`; then, in the dying mode (``DS:2326 == 3``), the anchor slot's
    ``+08`` counter is incremented and the exit fires at ``0x0F`` (deactivating the anchor).  When the
    tail isn't reached or isn't dying, the counter is returned UNCHANGED.  Pure: the caller owns the
    DS reads and the ``+08`` write-back.
    """
    from overkill.recovered.domain.frame_loop import DeathTailStep, GameplayExit, GameplayTransition

    counter = anchor_counter & 0xFFFF
    if not death_tail_reached_9aff(a95a, a97a) or (v2326 & 0xFFFF) != DEATH_TAIL_MODE_2326:
        return DeathTailStep(counter, None, False)
    new_counter = (counter + 1) & 0xFFFF
    fires, game_over, _ = death_tail_transition_9aff(v2326, new_counter, a97a)
    if not fires:
        return DeathTailStep(new_counter, None, False)
    exit_ = GameplayExit.GAME_OVER if game_over else GameplayExit.DEATH
    return DeathTailStep(new_counter, GameplayTransition(exit_), True)


def detect_gameplay_transition(a47c: int, a95a: int, a97a: int, v2326: int,
                               anchor_counter_after_inc: int):
    """The whole-frame gameplay-exit decision the ``1010:9B2E`` controller reaches (or ``None``).

    Composes the two recovered 9B2E exit rules in the original order + the ``97B2`` flag priority
    (``A344`` > ``A342`` > ``A346``):

    1. ``A344`` scripted transition fires first -- iff ``DS:A47C == 4`` (:func:`scripted_transition_fires_9b2e`).
    2. otherwise the ``9AFF`` death tail is reached only when the tracked anchor state is absent
       (``DS:A95A == FFFF`` or ``DS:A97A == 0``); there :func:`death_tail_transition_9aff` fires when
       the dying mode ``DS:2326 == 3`` and the anchor slot's ``+08`` counter (already incremented this
       frame) reaches ``0x0F`` -- ``A342``/game-over when ``A97A == 0``, else ``A346``/death.

    Returns a :class:`GameplayTransition` for the exit, or ``None`` on a normal gameplay frame.  Pure:
    the caller owns the DS reads (and the ``+08`` increment, matching
    :func:`death_tail_transition_9aff`'s ``anchor_counter_after_inc`` contract).
    """
    from overkill.recovered.domain.frame_loop import GameplayExit, GameplayTransition

    if scripted_transition_fires_9b2e(a47c):
        return GameplayTransition(GameplayExit.SCRIPTED)
    if (a95a & 0xFFFF) == ANCHOR_STATE_ABSENT_A95A or (a97a & 0xFFFF) == 0:
        fires, game_over, _ = death_tail_transition_9aff(v2326, anchor_counter_after_inc, a97a)
        if fires:
            return GameplayTransition(GameplayExit.GAME_OVER if game_over else GameplayExit.DEATH)
    return None


ATTRACT_MODE_2356 = 0x0005   # DS:2356 == 5 -> A940 runs its attract-mode counter/demo-tick middle


def a940_speed_bucket(a47e: int) -> int:
    """A940's attract reload from the ``DS:A47E`` speed bucket: 0x0A default, tightening as A47E drops.

    ``CL = 0x0A; if A47E <= 0x10: 0x06; if <= 0x08: 0x04; if <= 0x04: 0x01`` (1010:A98F..A9A7).
    """
    a47e &= 0xFFFF
    bucket = 0x0A
    if a47e <= 0x10:
        bucket = 0x06
        if a47e <= 0x08:
            bucket = 0x04
            if a47e <= 0x04:
                bucket = 0x01
    return bucket


def step_a940_attract_middle(a98a2: int, a98aa: int, a98a5: int, a98a3: int, a47e: int):
    """A940's ``DS:2356 == 5`` attract-mode counter block (1010:A970..A9AD, game_state.py's 118-154).

    Returns ``(new_98a2, new_98a4, new_98aa, new_98a5, new_98a3)`` (recovered from the A970..A9AD
    disassembly + confirmed against the original by ``verify_native_a940_attract.py`` -- NB the driven
    oracle caught that the lifted ``game_state`` attract branch mis-handles the ``98A5 > 1`` path, which
    no gameplay demo exercises):
    * ``98A2 != 0`` -> negate ``98AA``, clear ``98A2``, set ``98A4 = 1``; else ``98A4 = 0`` (98A2/98AA
      unchanged);
    * the ``98A5`` countdown (``A982..A9B3``): ``98A5 == 0`` -> stays 0 and ``98A3`` increments;
      ``98A5 == 1`` -> reloads :func:`a940_speed_bucket` and ``98A3`` increments; ``98A5 > 1`` ->
      decrements to ``98A5-1`` and ``98A3`` is RESET to 0 (the ``A9B3`` branch).
    (The 1F8F:081D demo tick is separate -- :func:`step_demo_counter_tick_1f8f_081d`.)  Pure.
    """
    a98a2 &= 0xFF
    if a98a2 != 0:
        new_98aa = (-(a98aa & 0xFFFF)) & 0xFFFF
        new_98a2, new_98a4 = 0, 1
    else:
        new_98aa, new_98a2, new_98a4 = a98aa & 0xFFFF, 0, 0
    a98a5 &= 0xFF
    if a98a5 == 0:
        new_98a5, new_98a3 = 0, (a98a3 + 1) & 0xFF
    else:
        dec = (a98a5 - 1) & 0xFF
        if dec != 0:
            new_98a5, new_98a3 = dec, 0
        else:
            new_98a5, new_98a3 = a940_speed_bucket(a47e), (a98a3 + 1) & 0xFF
    return new_98a2, new_98a4, new_98aa, new_98a5, new_98a3


def frame_state_update_a940(counter_a8ce: int, a8c8: int, a8cc: int, mode_2356: int,
                            flag_98a8: int, boss_pending_a8c2: int):
    """The whole ``1010:A940`` game-state update for a GAMEPLAY frame (``DS:2356 != 5``).

    Composes the two already-pure A940 halves -- :func:`step_frame_accumulator_shift_a940` (the
    unconditional saturating counter + the A8C8/A8CC->A8C6/A8CA shift, A8CC reset) and
    :func:`step_frame_scan_entry_a940_tail` (the 98A8/98A9 edge + the A8C2 boss-scan fork) -- into the
    whole native stage.  The ``DS:2356 == 5`` attract-mode middle (the 98A2/98A4/98A5 counters + the
    1F8F:081D demo tick) is a declared sub-gap: it FAILS LOUD here rather than run un-modeled.
    Verified produced-vs-VM by ``overkill/probes/verify_native_a940.py``.
    """
    from overkill.recovered.domain.frame_loop import FrameStateUpdateA940
    from overkill.recovered.domain.gaps import RecoveryGap

    if (mode_2356 & 0xFFFF) == ATTRACT_MODE_2356:
        raise RecoveryGap("1010:A940 attract-mode middle (DS:2356 == 5)",
                          "recovered as step_a940_attract_middle + step_demo_counter_tick_1f8f_081d, "
                          "but this gameplay-path signature doesn't carry the attract inputs -- a "
                          "caller in attract mode composes those two directly")
    accum = step_frame_accumulator_shift_a940(counter_a8ce, a8c8, a8cc)
    scan = step_frame_scan_entry_a940_tail(flag_98a8, boss_pending_a8c2)
    return FrameStateUpdateA940(
        counter_a8ce=accum.counter_a8ce, prev_a8c6=accum.prev_a8c6, prev_a8ca=accum.prev_a8ca,
        a8cc_reset=0, flag_98a8=scan.flag_98a8, flag_98a9=scan.flag_98a9, scan_target=scan.scan_target,
    )


def frame_axis_dispatch_offset(ah_count: int, al_count: int) -> int:
    """The ``1010:9C01`` axis jump-table byte offset from the two present-slot counts.

    9C01 counts how many of its four delayed-coordinate slots are live: two feed ``AH``
    (``DS:A966``/``A96A``) and two feed ``AL`` (``DS:A968``/``A96C``), so ``ah_count`` and
    ``al_count`` are each ``0..2``.  It then forms ``BL = al + 3*ah`` (an 8-bit value ``0..8``) and
    shifts left once to index the word jump table at ``CS:9C70`` -- i.e. the byte offset
    ``((al + 3*ah) & 0xFF) << 1`` (``0..16``).  Pure: the caller owns the slot reads and the table.
    """
    return (((al_count + 3 * ah_count) & 0xFF) << 1) & 0xFFFF


def step_frame_accumulator_shift_a940(counter_a8ce: int, a8c8: int, a8cc: int) -> FrameAccumulatorShiftOutcome:
    """Pure model of ``1010:A940``'s own opening accumulator-shift (unconditional, every frame,
    before A940's later attract-mode/boss-scan-fork decisions -- see the frame-controller memory
    for why those are NOT modelled here yet).  ``counter_a8ce`` saturates at ``0xFFFF`` rather
    than wrapping (matches the ASM's own ``cmp ...,0xFFFF; jz skip`` guard before the ``inc``).
    ``a8c8``/``a8cc`` shift into the returned ``prev_a8c6``/``prev_a8ca``; the real ``DS:A8C8``/
    ``DS:A8CC`` cells are then always reset to 0, so callers don't need to thread them forward."""
    new_counter = counter_a8ce if counter_a8ce == 0xFFFF else (counter_a8ce + 1) & 0xFFFF
    return FrameAccumulatorShiftOutcome(counter_a8ce=new_counter, prev_a8c6=a8c8, prev_a8ca=a8cc)


def step_demo_counter_tick_1f8f_081d(counter_98a7: int, speed_bucket_a47e: int, counter_98a6: int) -> DemoCounterTickOutcome:
    """Pure model of one ``1F8F:081D`` demo/attract-mode counter tick.

    Decrements ``counter_98a7`` (wraps mod 0x100 like the real byte ``DEC``); if it is still
    non-zero, ``counter_98a6`` resets to 0 and nothing else happens this tick.  Once it reaches
    0, reloads it from a difficulty/speed-bucket table keyed on ``speed_bucket_a47e`` (the SAME
    cascading nested-threshold shape as the ASM: default 0x78, tightening to 0x64/0x50/0x3C/0x28
    as ``speed_bucket_a47e`` drops through 0x10/0x08/0x04/0x02 -- smaller = faster reload) and
    increments ``counter_98a6``.
    """
    new_counter_98a7 = (counter_98a7 - 1) & 0xFF
    if new_counter_98a7 != 0:
        return DemoCounterTickOutcome(counter_98a7=new_counter_98a7, counter_98a6=0)
    reload = DEMO_TICK_DEFAULT_RELOAD
    if speed_bucket_a47e <= 0x10:
        reload = 0x64
        if speed_bucket_a47e <= 0x08:
            reload = 0x50
            if speed_bucket_a47e <= 0x04:
                reload = 0x3C
                if speed_bucket_a47e <= 0x02:
                    reload = 0x28
    return DemoCounterTickOutcome(counter_98a7=reload, counter_98a6=(counter_98a6 + 1) & 0xFF)


def step_frame_scan_entry_a940_tail(flag_98a8_before: int, boss_pending_a8c2: int) -> FrameScanEntryOutcome:
    """Pure model of ``1010:A940``'s tail: the ``98A8``/``98A9`` edge-detect + the ``A8C2``
    boss-scan fork.  Runs unconditionally every frame, after A940's ``DS:2356==5`` attract-mode
    branch (not modelled here) whether or not that branch ran."""
    new_98a9 = 1 if flag_98a8_before != 0 else 0
    scan_target = "boss" if boss_pending_a8c2 == 1 else "normal"
    return FrameScanEntryOutcome(flag_98a8=0, flag_98a9=new_98a9, scan_target=scan_target)
