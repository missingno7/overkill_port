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


A95C_RELOAD = 0x0018   # DS:A95C reloads to 0x18 when the difficulty countdown reaches 0 (9E63)
SCRIPTED_INPUT_TABLE_9A0C = 0x9A0C   # the CS jump table 99F6 dispatches through, indexed by A47C*2

A47C_ARM_GATE_2350 = 0x0EA0   # DS:2350 must equal this for the A680 A47C-script arm to fire


def a47c_script_arms_a680(a480: int, gate_234e: int, gate_2350: int) -> bool:
    """The ``1010:A680`` scripted-input ARM gate: does this frame set ``DS:A47C = 1`` (launch the
    A47C-indexed scripted-input/event script)?

    This is the *upstream trigger* for the A47C scripted-input system -- 99F6 then dispatches on A47C
    to its per-mode handlers (1=9A78, 2=9A3E, 3=9A16) and the script self-advances via ``inc [A47C]``.
    Recovered end-to-end by ``verify_native_a47c_arm_a680.py`` driving ``A680`` (which first calls the
    world-scroll ``A6FE``, then a ``C591`` housekeeping call) and observing whether control reaches the
    ``mov ds:[A47C],1`` at ``A6B9`` vs the bail at ``A6FD``.

    The disassembler *displays* the three guards as ``[A480]==0`` / ``[234E]==0`` / ``[2350]==0x0EA0``
    ``jnz``-bails, but the live oracle is ground truth (lindis mis-renders these jz/jnz targets): the
    arm fires **iff** ``A480 == 0`` **and** ``234E == 1`` **and** ``2350 == 0x0EA0`` -- the ``234E``
    guard reads as ``== 1``, not ``!= 0`` (A6FE decrements it before the compare), and ``2350`` must
    match exactly.  Values are read as 16-bit words.

    WHAT THIS SCRIPT ACTUALLY IS -- UNVERIFIED.  ``234E``/``2350`` are the world-SCROLL cursor
    (origin_x / row_base, per play_native), so this arm fires at a specific scroll POSITION, and it
    spawns an entity (``62AA`` + ``7524`` at A6BF, si=A3EE) -- the shape of a scripted level/boss
    event, NOT collision-death.  Evidence: ``A47C == 0`` at EVERY demo seed incl. player_death and
    L6_boss, and the "death countdown" cells ``A95A``/``A97A`` hold normal-play resting values in
    ordinary L1/L2 gameplay.  The GROUNDED (demo-witnessed) player-death path is the SEPARATE ``9AFF``
    ``+08`` anchor counter (:func:`step_death_tail_9aff` / :func:`detect_gameplay_transition`), which
    does not touch A47C.  The A47C-script functions here are byte-exact but their "death"/"game-over"
    naming is a provisional label pending a trace that actually drives A47C nonzero (see
    loop_blockers.md).  Pure predicate; the caller owns the A47C write + the spawn tail.
    """
    return (a480 & 0xFFFF) == 0 and (gate_234e & 0xFFFF) == 1 and (gate_2350 & 0xFFFF) == A47C_ARM_GATE_2350


def scripted_input_prologue_99f6(a47c: int, prev_2380: int):
    """The ``1010:99F6`` scripted-input dispatch prologue (the entry to the A47C-driven script system).

    99F6 runs each frame the scripted-input mode is active (``DS:A47C != 0`` -- boss/cutscene
    auto-movement, and the death/end-of-life sequence): it clears bit 0 of ``DS:2380`` and the input
    byte ``DS:98BE``, then jumps through ``jmp cs:[A47C*2 + 9A0C]`` to the per-mode handler.  Returns
    ``(new_2380, new_98be, table_byte_offset)`` -- the handler IP is
    ``cs:[SCRIPTED_INPUT_TABLE_9A0C + table_byte_offset]`` (a code-table constant the caller reads).
    Pure: the caller owns the DS writes + the table read.
    """
    return prev_2380 & 0xFFFE, 0x00, (a47c << 1) & 0xFFFF


def step_scripted_move_counters_9a3e(counter_2384: int, a39c: int, a39a: int):
    """The ``1010:9A3E`` scripted-move coordinate-counter update (the A47C==2 script step's head).

    Recovered from ``9A3E..9A73``, confirmed by ``verify_native_scripted_move_counters_9a3e.py``: it
    increments ``DS:A39C`` (capped) and decrements ``DS:A39A`` (capped) with the caps chosen by the
    A47C-script counter ``DS:2384`` -- ``2384 == 0`` caps at ``A39C 0x08`` / ``A39A 0xFFF8``, else
    ``0x0F`` / ``0xFFF1``.  (The tail past ``9A73`` -- the entity spawn via 7524 + the coordinate-table
    movement -- is a spawner island, NOT part of this counter leaf.)  Returns ``(new_a39c, new_a39a)``.
    (A47C is the scripted-input/event script, NOT player death -- see :func:`a47c_script_arms_a680`.)
    """
    if (counter_2384 & 0xFFFF) == 0:
        cap_c, cap_a = 0x0008, 0xFFF8
    else:
        cap_c, cap_a = 0x000F, 0xFFF1
    a39c, a39a = a39c & 0xFFFF, a39a & 0xFFFF
    new_a39c = a39c if a39c == cap_c else (a39c + 1) & 0xFFFF
    new_a39a = a39a if a39a == cap_a else (a39a - 1) & 0xFFFF
    return new_a39c, new_a39a


def step_a47c_handler_9a16(a97a: int, a97c: int, a95a: int, a95c: int,
                            counter_2384: int, bdac: int, flag_98c0: int):
    """The whole ``1010:9A16`` scripted-input handler (the ``A47C == 3`` step of the 99F6 script).

    NOTE: previously named ``step_death_handler_9a16``; the "death" label is UNVERIFIED and contradicted
    by evidence -- A47C is dormant (``==0``) across the ENTIRE player-death demo and its arm (A680) is
    scroll-POSITION gated -- so this is the scripted-input/event script, NOT player death (see
    :func:`a47c_script_arms_a680` + loop_blockers.md).  ``A95A``/``A95C``/``A97A`` are this script's
    counters, not death counters (they hold the same resting values in ordinary L1/L2 play).

    COMPOSES the recovered sub-steps -- no VM/render calls, fully native: set the scripted input
    ``DS:98BE := 8`` (down), run :func:`step_a47c_arm_9db9` then :func:`step_a47c_seq_9dea`, then ADVANCE
    the script step ``inc DS:A47C`` only when (after those sub-steps) ``A97A == 0x58`` AND ``A95A == 3``
    AND ``A95C == 0x18`` (all three -- confirmed by ``verify_native_a47c_handler_9a16.py``).

    Returns ``(input_98be, new_a97c, new_a95a, new_a95c, a47c_advanced)``.  Pure.
    """
    new_a97c, _ = step_a47c_arm_9db9(a97a, a97c, counter_2384, bdac, flag_98c0)
    new_a95c, new_a95a, _ = step_a47c_seq_9dea(a95c, a95a, flag_98c0)
    a47c_advanced = (a97a & 0xFFFF) == 0x0058 and new_a95a == 0x0003 and new_a95c == 0x0018
    return 0x08, new_a97c, new_a95a, new_a95c, a47c_advanced


def step_a47c_arm_9db9(a97a: int, a97c: int, counter_2384: int, bdac: int, flag_98c0: int):
    """The ``1010:9DB9`` A47C-script ARM sub-step (of the ``A47C==3`` handler; sets the ``A97C`` flag).

    NOTE: previously ``step_game_over_arm_9db9``; the "game-over" label is UNVERIFIED (see
    :func:`step_a47c_handler_9a16`) -- ``A97A``/``A97C`` are A47C-script cells, not confirmed game-over.
    Recovered from ``9DB9..9DE9``, confirmed by ``verify_native_a47c_arm_9db9.py`` (32 combos):
    no-op when ``DS:A97A == 0x58`` or ``DS:A97C == 1`` (already armed); otherwise, only while the counter
    ``DS:2384 < 3``, it ARMS ``A97C := 1`` and (only when ``DS:BDAC != 1`` AND ``DS:98C0 != 0``)
    writes ``DS:BEFF := 0x0D``.  When ``2384 >= 3`` it leaves ``A97C`` at 0.

    Returns ``(new_a97c, beff)`` where ``beff`` is ``0x0D`` or ``None``.  Pure.
    """
    if (a97a & 0xFFFF) == 0x0058 or (a97c & 0xFFFF) == 1:
        return a97c & 0xFFFF, None
    if (counter_2384 & 0xFFFF) >= 3:
        return 0, None
    beff = 0x0D if (bdac & 0xFFFF) != 1 and (flag_98c0 & 0xFFFF) != 0 else None
    return 1, beff


def step_a47c_seq_9dea(a95c: int, a95a: int, flag_98c0: int):
    """The ``1010:9DEA`` A47C-script A95A/A95C advance (a sub-step of the ``A47C==3`` handler).

    NOTE: previously ``step_death_seq_9dea``; the "death" label is UNVERIFIED (see
    :func:`step_a47c_handler_9a16`).
    Recovered from ``9DEA..9E16``, confirmed by ``verify_native_a47c_seq_9dea.py``: while ``DS:A95C``
    hasn't reached ``0x18`` it just increments ``A95C`` (``9E12``); once ``A95C == 0x18`` AND
    ``DS:A95A != 3`` it advances the anchor (``inc A95A``), resets ``A95C = 0``, and (only when
    ``DS:98C0 != 0``) writes ``DS:BEFF = 0x1C``; if ``A95C == 0x18`` and ``A95A == 3`` it no-ops
    (``9DF8 ret``).

    Returns ``(new_a95c, new_a95a, beff)`` where ``beff`` is ``0x1C`` or ``None``.  Pure.
    """
    a95c, a95a = a95c & 0xFFFF, a95a & 0xFFFF
    if a95c != 0x0018:
        return (a95c + 1) & 0xFFFF, a95a, None
    if a95a == 0x0003:
        return a95c, a95a, None
    beff = 0x1C if (flag_98c0 & 0xFFFF) != 0 else None
    return 0x0000, (a95a + 1) & 0xFFFF, beff


def step_a95c_difficulty_countdown_9e43(bedc: int, a95c: int):
    """The ``1010:9E43`` difficulty-scaled ``A95C`` countdown (a death-island leaf).

    Recovered from the ``9E43..9E63`` disassembly, confirmed by ``verify_native_a95c_countdown.py``:
    ``A95C`` is decremented by ``1`` / ``2`` / ``3`` per frame for ``DS:BEDC`` == 0 / == 1 / >= 2
    (three sequential ``dec`` sites gated by the BEDC compares), and when the countdown reaches 0 it
    reloads to :data:`A95C_RELOAD` (``9E63``); otherwise it continues (``9E61 jnz 9EC2``).

    Returns ``(new_a95c, reloaded)``.  Pure: the caller owns the DS read/write.
    """
    bedc &= 0xFFFF
    count = 1 if bedc == 0 else (2 if bedc == 1 else 3)
    a95c &= 0xFFFF
    if a95c > count:
        return (a95c - count) & 0xFFFF, False
    return A95C_RELOAD, True


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


def step_game_over_countdown_9ee4(a97a: int):
    """The ``1010:9EE4`` game-over animation countdown (a death-island leaf; sets ``A97A -> 0``).

    Recovered from the ``9EE4..9EF5`` disassembly, confirmed by ``verify_native_a97a_game_over.py``:
    when ``DS:A97A == 0`` the routine no-ops and returns (game over already settled); otherwise it
    decrements ``A97A`` and, when that reaches 0, the game-over-final branch fires (``9EF5``: sets
    2384/BEFF, then ``jmp 77DF``) -- ``A97A == 0`` is what the gameplay-exit GAME_OVER verdict keys on
    (:func:`death_tail_transition_9aff`).  While still counting (``A97A > 0`` after the decrement) it
    takes the plain ``9EF2 -> jmp 77DF`` path.  (The 2384/BEFF writes on the reached-zero path are not
    part of this countdown leaf.)

    Returns ``(new_a97a, reached_zero, rets_early)``: ``rets_early`` marks the no-op ``A97A == 0``
    entry.  Pure: the caller owns the DS read/write.
    """
    a97a &= 0xFFFF
    if a97a == 0:
        return 0, False, True
    new_a97a = (a97a - 1) & 0xFFFF
    return new_a97a, new_a97a == 0, False


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


OBJECT_SEED_SLOT_TABLE_32CA = 0x32CA   # layout-justified: DS word table cx(1..0x24) -> object-record offset
OBJECT_SEED_FB_BASE_C3A2 = 0x3314      # first per-slot framebuffer back-buffer pointer (CS:C3A2 init)
OBJECT_SEED_FB_STEP = 0x0280           # per-slot framebuffer pointer stride
OBJECT_SEED_COUNT = 0x24               # 36 object slots seeded
OBJECT_RECORD_STRIDE = 0x38            # layout-justified: object-record size
#: The pool bases the C4DB seed covers, all on the object-record grid (base + i*0x38):
POOL_BASE_SPECIAL = 0x237C     # layout-justified: the view-anchor / player slot (record 0), 1 slot
POOL_BASE_EFFECT = 0x23B4      # layout-justified: the effect table (records 1..35), 35 slots
POOL_BASE_GAMEPLAY = 0x2B5C    # layout-justified: the gameplay/enemy table (record 36+) -- NOT C4DB-seeded
POOL_EFFECT_SLOTS = 35         # effect-table slot count (records 1..35, up to 0x2B24)


GAMEPLAY_SEED_SLOT_TABLE_8D12 = 0x8D12   # layout-justified: DS word table cx(1..0x22) -> gameplay record
GAMEPLAY_SEED_FB_BASE = 0x8D58           # first per-slot back-buffer pointer (CS:C3A2 init in C3A6)
GAMEPLAY_SEED_FB_STEP = 0x0040           # per-slot back-buffer pointer stride
GAMEPLAY_SEED_COUNT = 0x22               # 34 gameplay/enemy slots seeded


def object_pool_seed_c3b5(slot_ptr_table) -> dict:
    """The ``1010:C3B5`` GAMEPLAY object-pool seed loop (``C3BF..C3E5``; the first pool re-init in the
    respawn/level-start routine ``C3A6``).

    This is the seed for the GAMEPLAY/enemy pool (:data:`POOL_BASE_GAMEPLAY` = ``0x2B5C``) -- the one the
    C4DB new-game seed does NOT cover (see :func:`object_pool_seed_c4db`); it resolves the earlier open
    question of where the gameplay table is initialised.  For each of the 34 slots ``cx = 0x22..1`` it
    reads the record offset from the ``DS:0x8D12`` word table and stamps ``+0x00 = 0`` (inactive) /
    ``+0x18 = 0`` / ``+0x2E = 0`` plus a per-slot back-buffer pointer at ``+0x0E`` that steps ``0x8D58,
    +0x40, ...``.  Byte-exact vs the VM (34 records x 4 fields) in ``verify_native_gameplay_pool_seed``.

    ``slot_ptr_table`` maps ``cx (1..0x22) -> record offset`` (read from ``DS:0x8D12``; resolves to
    ``0x2B5C`` + stride ``0x38`` on this build).  Returns ``{record_offset: {field: value}}`` -- the pure
    LOGIC; the caller owns the table read + the writes.
    """
    seed: dict = {}
    render = GAMEPLAY_SEED_FB_BASE
    for cx in range(GAMEPLAY_SEED_COUNT, 0, -1):   # 0x22 down to 1, matching the ASM loop
        off = slot_ptr_table[cx] & 0xFFFF
        seed[off] = {0x00: 0, 0x0E: render & 0xFFFF, 0x18: 0, 0x2E: 0}
        render = (render + GAMEPLAY_SEED_FB_STEP) & 0xFFFF
    return seed


def object_pool_seed_c4db(slot_ptr_table) -> dict:
    """The ``1010:C4DB`` object-pool SEED loop (``C4E5..C51B``; the head of the C4DB new-game setup,
    Bucket-F level-start object state).

    For each of the 36 slots ``cx = 0x24 .. 1`` (descending, as the ASM ``loop`` runs it) it reads the
    slot's object-record offset from the ``DS:0x32CA`` word table and stamps a fixed template plus a
    per-slot framebuffer back-buffer pointer at ``+0x0E`` that steps ``0x3314, +0x280, +0x280, ...`` in
    that processing order (``CS:C3A2`` accumulator).  The template zeroes ``+0x00`` (inactive) / ``+0x06``
    / ``+0x18`` / ``+0x24`` / ``+0x2E`` and sets ``+0x0A = 1``.  Byte-exact vs the VM (36 records x 7
    fields) in ``verify_native_object_pool_seed_c4db``.

    POOL LAYOUT (verified in ``verify_native_c4db_seed_pool_layout``): the 36 seeded records are exactly
    the special view-anchor (:data:`POOL_BASE_SPECIAL`, record 0, 1 slot) + the effect table
    (:data:`POOL_BASE_EFFECT`, records 1..35, :data:`POOL_EFFECT_SLOTS` slots) -- one contiguous
    ``0x237C..0x2B24`` block on the ``0x38`` grid.  The gameplay/enemy table (:data:`POOL_BASE_GAMEPLAY`)
    is seeded separately by :func:`object_pool_seed_c3b5` (in the respawn/level-start C3A6).

    ``slot_ptr_table`` is a mapping ``cx (1..0x24) -> record offset`` (the caller reads the real table
    from ``DS:0x32CA``; on this build it resolves to base ``0x237C`` + stride ``0x38``).  Returns
    ``{record_offset: {field_offset: value}}`` -- the pure LOGIC (order/template/pointer stepping); the
    caller owns the table read and the DS/SS writes.
    """
    seed: dict = {}
    render = OBJECT_SEED_FB_BASE_C3A2
    for cx in range(OBJECT_SEED_COUNT, 0, -1):   # 0x24 down to 1, matching the ASM loop
        off = slot_ptr_table[cx] & 0xFFFF
        seed[off] = {0x00: 0, 0x06: 0, 0x0A: 1, 0x0E: render & 0xFFFF, 0x18: 0, 0x24: 0, 0x2E: 0}
        render = (render + OBJECT_SEED_FB_STEP) & 0xFFFF
    return seed


def level_start_control_reset_c51d() -> dict:
    """The ``1010:C51D..C559`` level-start reset of the frame-control cells (part of the C4DB
    new-game setup; Bucket-F level-start state).  Returns the exact ``{DS offset: value}`` map the
    setup writes, driven-oracle byte-exact (``verify_native_level_start_control_reset_c51d``):

    * the four delayed-coordinate slots :func:`frame_axis_dispatch_offset` consumes (``A966``/``A96A``
      feed AH, ``A968``/``A96C`` feed AL) plus their neighbours ``A962``/``A964``/``A96E`` -> ``0xFFFF``
      (the empty-slot sentinel: 9C01 then counts none present);
    * ``A958`` / ``A95E`` / ``A960`` -> 0 (fire-latch + related control words);
    * ``A47C``-script counter ``2384`` -> 0.

    Pure data (a memset, not a decision); the caller owns the DS writes.  The rest of C4DB -- the
    36-slot object-record seed loop (``C4E5..C51B``, per-slot framebuffer pointer stepping by 0x280
    via the DS:3002 pointer table) -- is the object-pool seed, a separate Bucket-F integration.
    """
    reset = {0xA958: 0x0000, 0xA95E: 0x0000, 0xA960: 0x0000, 0x2384: 0x0000}
    for off in (0xA962, 0xA964, 0xA966, 0xA968, 0xA96A, 0xA96C, 0xA96E):
        reset[off] = 0xFFFF
    return reset


def apply_new_game_setup_c4db(slot_ptr_table) -> dict:
    """The WHOLE ``1010:C4DB`` new-game setup as one flat ``{DGROUP offset: value}`` write-map --
    COMPOSES :func:`object_pool_seed_c4db` (the C4E5..C51B object-record seed) with
    :func:`level_start_control_reset_c51d` (the C51D..C559 control-cell reset).

    ``SS == DS`` (both the DGROUP data segment) on this build, so the object records and the control
    cells live in one segment and merge into a single write-map.  Proven byte-exact AND COMPLETE
    (a full-segment before/after diff shows C4DB writes exactly these DGROUP cells -- its only other
    write is the ``CS:C3A2`` framebuffer accumulator, outside DGROUP) by
    ``verify_native_new_game_setup_c4db``.  This is the native entry point a cold level-start calls to
    seed the object pool + reset the frame-control cells.  ``slot_ptr_table`` is the ``DS:0x32CA``
    ``cx (1..0x24) -> record offset`` map; the caller owns the writes.
    """
    writes: dict = {}
    for rec_off, fields in object_pool_seed_c4db(slot_ptr_table).items():
        for fo, val in fields.items():
            writes[(rec_off + fo) & 0xFFFF] = val
    writes.update(level_start_control_reset_c51d())
    return writes


#: The render-glue cells the 6176 panel-draw writes inside the 9720..9748 new-game setup range -- NOT
#: part of the data model (they belong to the HUD/panel presentation layer, verified as the documented
#: completeness boundary in verify_native_new_game_data_setup).
NEW_GAME_SETUP_RENDER_CELLS = (0x215E, 0x2160, 0x2370, 0x2372, 0x9682, 0x968A, 0x9696, 0x969E)


def native_new_game_data_setup(new_level_index: int, slot_ptr_table) -> dict:
    """The DATA half of the new-game / level-start setup (``1010:9720..9748``), composed native.

    Composes the verified data-setup pieces into one ``{DGROUP offset: value}`` cell-map:
    :func:`apply_new_game_setup_c4db` (the C4DB object-pool seed + frame-control reset) + the ``9723``
    counter init (``DS:A95A := 3``, ``DS:A95C := 0x18``) + the advanced level index (``DS:2356``; the
    caller advances it via :func:`overkill.recovered.systems.menu.advance_level_index_9744`).

    This is the DATA model ONLY.  The setup range also runs the ``5C9A`` full-screen blit and the
    ``6176`` panel draw -- host PRESENTATION whose render-bookkeeping cell writes
    (:data:`NEW_GAME_SETUP_RENDER_CELLS`) are deliberately NOT modelled here.
    ``verify_native_new_game_data_setup`` proves this map matches the VM for every data cell AND that the
    only other DGROUP writes are exactly those render cells (a documented completeness boundary).  This
    is the native entry point a cold level-start calls to build its initial game-data state.
    """
    cells = dict(apply_new_game_setup_c4db(slot_ptr_table))
    cells[0xA95A] = 0x0003
    cells[0xA95C] = 0x0018
    cells[0x2356] = new_level_index & 0xFFFF
    return cells


NEW_GAME_SESSION_START_LIVES = 0x0003   # DS:2358 lives/continue counter at a fresh game session

PLAYER_SPAWN_RECORD = 0x237C   # layout-justified: the player view-anchor object record (special pool)
PLAYER_SPAWN_X = 0x00C0        # DS:237C+02 spawn x
PLAYER_SPAWN_Y = 0x0058        # DS:237C+04 spawn y


def player_spawn_record_c42f() -> dict:
    """The player view-anchor record (``DS:237C``) SPAWN stamp at ``1010:C42F..C44B`` -- the Bucket-F
    player-spawn state, inside the level/respawn re-init ``C3A6``.

    Activates and positions the player object: ``+0x00 = 1`` (active), ``+0x02 = 0xC0`` (spawn x),
    ``+0x04 = 0x58`` (spawn y), ``+0x0A = 1``, ``+0x14 = 2``, ``+0x16 = 3``.  Byte-exact vs the VM
    (``verify_native_player_spawn``).  Returns ``{field offset: value}`` for the ``DS:237C`` record.

    The steps that FOLLOW the stamp -- the ``7524`` companion-object spawn
    (:func:`player_companion_spawn_c453`), the ``A3B4`` coordinate-ring clear (26 words -> 0xFFFF), and
    the ``A95A``/``A95C``/``A970``.. counter re-init -- are separate; this leaf is just the player
    record's initial fields.
    """
    return {0x00: 1, 0x02: PLAYER_SPAWN_X, 0x04: PLAYER_SPAWN_Y, 0x0A: 1, 0x14: 2, 0x16: 3}


def player_companion_spawn_c453() -> dict:
    """The player COMPANION object stamp at ``1010:C453..C45F`` -- the object spawned alongside the player
    at spawn (its flame/exhaust anchor), right after the ``7524`` allocation at ``C450``.

    The freshly-allocated object record gets ``+0x00 = 1`` (active), ``+0x14 = 1``, ``+0x16 = 6`` (its
    logic/sprite type).  Byte-exact vs the VM (``verify_native_player_companion_spawn``).  Returns the
    ``{field offset: value}`` stamp template; WHICH slot ``7524`` returns is the allocator's concern (on
    the death snapshot it lands in the effect table), so this leaf models only the template.
    """
    return {0x00: 1, 0x14: 1, 0x16: 6}


def respawn_control_reset_c461() -> dict:
    """The ``1010:C461..C4AD`` respawn / level-start control re-init (the C3A6 tail, after the player +
    companion spawn).  Returns the exact ``{DGROUP offset: value}`` map it writes:

    * the ``A3B4`` coordinate ring -- 26 words -> ``0xFFFF`` (the empty-slot sentinel);
    * ``A95A = 3`` / ``A95C = 0x18`` -- the death/difficulty countdown counters (as at session start);
    * ``A970``/``A972``/``A974``/``A976``/``A97A``/``A97E`` -> 0 -- the A970-family counters + the
      game-over/HUD cell ``A97A``;
    * ``A39A``/``A39C`` -> 0 -- the scripted-move coordinate counters (see
      :func:`step_scripted_move_counters_9a3e`);
    * ``9788 = 0xFFFF``.

    Pure data (a memset of the per-life control state; ``SS==DS`` so the ``A3B4`` ring's ES write lands
    in DGROUP too).  The ``9DB9`` game-over-arm call + ``A980``/``20A6`` writes that FOLLOW at ``C4B3+``
    are separate.  Byte-exact + complete vs the VM (``verify_native_respawn_control_reset``).
    """
    reset: dict = {}
    for i in range(26):
        reset[(0xA3B4 + i * 2) & 0xFFFF] = 0xFFFF
    reset[0xA95A] = 0x0003
    reset[0xA95C] = 0x0018
    for off in (0xA970, 0xA972, 0xA974, 0xA976, 0xA97A, 0xA97E, 0xA39A, 0xA39C):
        reset[off] = 0x0000
    reset[0x9788] = 0xFFFF
    return reset


def new_game_session_init_96ee() -> dict:
    """The session-start (new-game) DATA init at ``1010:96EE..9715`` -- the TOP of the mode machine's
    game session.

    Returns the exact ``{DGROUP offset: word value}`` map the init writes: ``DS:2356 = 0`` (planet index
    -> planet 0), ``DS:2358 = 3`` (the lives/continue counter -- :data:`NEW_GAME_SESSION_START_LIVES`),
    ``DS:235A = 0``, ``DS:A342 = 0`` (clears the game-over flag), and the score ``DS:2314..2317 = 0`` --
    a 32-bit little-endian value (NOT BCD digits: ``532D`` ranks it against the high-score table with a
    4-byte ``sub``/``sbb``), modelled here as the two words ``2314``/``2316``.  Reached from the
    title/menu on "start" and from the game-over tail (``98EB -> jmp 96E0``) to restart; flows into the
    ``971A`` new-game setup.  Byte-exact AND complete vs the VM (``verify_native_new_game_session_init``).

    The preceding ``96E0..96EB`` video/palette init (``CB1C``/``4FC3``/``5145``/``5559``) is host
    presentation, not modelled here.  Pure data (a memset of the session globals); the caller owns the
    DS writes.
    """
    return {0x2356: 0x0000, 0x2358: NEW_GAME_SESSION_START_LIVES, 0x235A: 0x0000,
            0xA342: 0x0000, 0x2314: 0x0000, 0x2316: 0x0000}


GAMEPLAY_EXIT_GAME_OVER_9902 = 0x9902   # the A342 gameplay-exit target
GAMEPLAY_EXIT_DEATH_9908 = 0x9908       # the A346 gameplay-exit target


def death_continue_counter_update(is_game_over: bool, lives_2358: int, flag_978d: int) -> int:
    """The ``DS:2358`` lives / continue-counter update at the two death-family gameplay-exit targets:
    the death handler (``1010:9908``, flag A346) and the game-over entry (``1010:9902``, flag A342).

    Game-over (``9902``) forces the counter to 0 first, then falls into the death handler; the death
    handler re-seeds the object pool (``C4DB``) and DECREMENTS the counter, with the "no-death" flag
    ``DS:978D`` (``!= 0``) cancelling the decrement (net-zero -- a practice/invuln branch).  A counter
    that underflows to ``0xFFFF`` is the game-over sentinel.  Byte-exact 12/12 vs the VM
    (``verify_native_death_continue_counter``).

    Pure; the caller owns the DS reads/writes, the ``C4DB`` re-seed, and the deeper respawn-vs-game-over
    branch past ``991A`` (the ``BEFF`` mode codes + ``jmp 9773`` -- still a GAP).
    """
    lives = 0 if is_game_over else (lives_2358 & 0xFFFF)
    lives = (lives - 1) & 0xFFFF
    if (flag_978d & 0xFF) != 0:
        lives = (lives + 1) & 0xFFFF
    return lives


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
