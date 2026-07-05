"""The enemy BEHAVIOR handlers (the EFC4 zoo) as pure per-frame decision functions.

Each behavior handler runs once per frame per active record (the ``A9DD..AA2A`` walk -> the ``AA36``
type dispatch -> the ``EFC4`` behavior dispatch, ``+0x18`` keyed).  This module recovers them as
PURE DECISION functions: inputs are the record fields + the DGROUP clocks/globals; the output is a
:class:`EnemyBehaviorStep` naming the record/global writes and the ACTIONS (move / shoot) whose
implementations are the already-recovered systems (``object_target_seek_step_5db2`` via the
``B85C``/``B729`` tail, ``enemy_shot_stamp_7476``, ``canned_random_next_4d95``).  The caller (the
future NativeGame behavior-registry stage) owns applying writes and running actions.

First resident: behavior ``0x20`` (``1010:B73E``) -- the planet-1 wave enemy.  Its life:
APPROACH the formation slot (``+0x1C == FFFF``: sprite animated from the ``DS:2338`` clock, the
``B85C`` seek toward ``+0x34``/``+0x32``), then HOLD (once ``A7A0 >= 0x23``): shoot in the
``DS:2340`` walk-clock window (gated by the ``4D95`` canned random's low bit), DIVE-retarget at the
player when few enemies remain (``A47E <= 3`` -> ``B7C7``: target y = anchor ``[2380]+8 & ~7``,
parity-gated; also the ``[2340] < 5`` variant), or RE-SHUFFLE to a fresh slot from the second ring
``DS:A844..A894`` when ``[232E] == 0x3F``; the dive runs the SUBSTATE chain ``+0x1C`` = 0 (re-
approach) -> 1 (sprite 0x79) -> 2 (fly +X 4px/frame, sprite 0x77 past x >= 0xA0 -- the exit path,
despawned by the postmove bounds check).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from overkill.recovered.domain.movement import MovementTarget
from overkill.recovered.islands import recovered_island
from overkill.recovered.systems.frame_loop import enemy_spawn_stamp_8209
from overkill.recovered.systems.movement import object_target_seek_step_5db2

BEHAVIOR_20_HOLD_A7A0 = 0x0023          # arrival idles until the wave clock reaches this
BEHAVIOR_20_SHOOT_WINDOW = (0x02BC, 0x02D0)   # the DS:2340 walk-clock shoot window (inclusive)
BEHAVIOR_20_DIVE_MAX_ENEMIES = 3        # A47E <= this -> the dive retarget path
BEHAVIOR_20_RESHUFFLE_232E = 0x003F     # the re-shuffle gate on DS:232E
SLOT_RING_BASE_A844 = 0xA844            # the second formation ring (cursor DS:A842)
SLOT_RING_END_A894 = 0xA894
SLOT_RING_X_BIAS = 0x20                 # ring x values are stored -0x20 (lodsw; add ax,0x20)


@dataclass(frozen=True)
class EnemyBehaviorStep:
    """One behavior handler's per-frame outcome: writes + actions, caller-applied."""

    record_writes: dict = field(default_factory=dict)   # {record field offset: value}
    global_writes: dict = field(default_factory=dict)   # {DGROUP offset: value}
    move_to_target: bool = False   # run the B85C tail: [2308]=2, the 5DB2 seek, then +0x06 = 4
    shoot: bool = False            # spawn the 7476 enemy shot
    random_stepped: bool = False   # the 4D95 cursor was consumed this frame


@recovered_island(
    asm=("1010:B73E..B7BC", "1010:B7BD..B85B", "1010:B74E"),
    contract="behavior 0x20 (the planet-1 wave enemy) as a pure per-frame decision: approach the "
             "formation slot / hold+shoot in the 2340 window (4D95 low-bit gate) / dive-retarget "
             "at the player (A47E<=3 or 2340<5, parity-gated) / re-shuffle from the A844 ring at "
             "232E==0x3F / the +0x1C substate exit chain",
    status="VERIFIED",
    merge_target="EnemyWaveSystem",
    unknowns="the seek path's player-touch death (C037 family) fires OUTSIDE this decision fn "
             "(the walk's collision stage owns it); DS:A954/230A stay separate per the 5DB2 island",
)
def step_enemy_behavior_20(*, x_word: int, y_word: int, substate_1c: int,
                           target_x_34: int, target_y_32: int,
                           a7a0: int, clock_2338: int, clock_2340: int, clock_232e: int,
                           parity_2324: int, active_enemies_a47e: int, anchor_y_2380: int,
                           ring_cursor_a842: int, slot_ring, random_value: int) -> EnemyBehaviorStep:
    """One frame of behavior ``0x20`` (``1010:B73E``), pure.

    ``slot_ring`` is the cold ``A844..A894`` list of ``(x_raw, y)`` word pairs (x stored without the
    ``+0x20`` bias); ``random_value`` is the NEXT ``4D95`` ring word -- consumed (and thus the
    cursor advanced by the caller) only when ``random_stepped`` is set in the result.
    """
    su = substate_1c & 0xFFFF
    if su != 0xFFFF:
        if su == 0:      # B754: re-approach until back at the target, then advance the substate
            if y_word != target_y_32 or x_word != target_x_34:
                return EnemyBehaviorStep(move_to_target=True,
                                         record_writes={0x06: 0x0004})
            return EnemyBehaviorStep(record_writes={0x1C: 0x0001})
        if su == 1:      # B770: flash sprite 0x79, advance
            return EnemyBehaviorStep(record_writes={0x08: 0x0079, 0x1C: 0x0002})
        # su == 2 -- B77B: fly +X 4px/frame; sprite 0x77 once past the right edge
        new_x = (x_word + 4) & 0xFFFF
        writes = {0x02: new_x}
        if new_x >= 0x00A0:
            writes[0x08] = 0x0077
        return EnemyBehaviorStep(record_writes=writes)

    # the FFFF APPROACH/HOLD phase (B791)
    clock = clock_2338 & 0xFFFF
    sprite = ((0x7F - clock) if (y_word & 0xFFFF) < 0x60 else (0x7A + clock)) & 0xFFFF
    writes = {0x08: sprite}
    if y_word != target_y_32 or x_word != target_x_34:
        writes[0x06] = 0x0004
        return EnemyBehaviorStep(record_writes=writes, move_to_target=True)
    if (a7a0 & 0xFFFF) < BEHAVIOR_20_HOLD_A7A0:
        return EnemyBehaviorStep(record_writes=writes)

    # holding at the slot past the wave-clock gate (B7F3)
    shoot = False
    random_stepped = False
    lo, hi = BEHAVIOR_20_SHOOT_WINDOW
    if lo <= (clock_2340 & 0xFFFF) <= hi:
        random_stepped = True
        shoot = (random_value & 1) == 0
    if (active_enemies_a47e & 0xFFFF) <= BEHAVIOR_20_DIVE_MAX_ENEMIES \
            or (clock_2340 & 0xFFFF) < 5:
        # the DIVE retarget (B7C7; the 2340 < 5 entry at B7CE skips the parity gate)
        parity_gated = (active_enemies_a47e & 0xFFFF) <= BEHAVIOR_20_DIVE_MAX_ENEMIES \
            and (parity_2324 & 0xFFFF) == 1
        target_y = target_y_32
        if not parity_gated:
            target_y = ((anchor_y_2380 + 8) & 0xFFFF)
        writes.update({0x32: target_y & 0xFFF8, 0x1C: 0x0000, 0x08: 0x0078, 0x34: 0x0020})
        return EnemyBehaviorStep(record_writes=writes, global_writes={0x2340: 0x0028},
                                 shoot=shoot, random_stepped=random_stepped)
    if (clock_232e & 0xFFFF) != BEHAVIOR_20_RESHUFFLE_232E:
        return EnemyBehaviorStep(record_writes=writes, shoot=shoot,
                                 random_stepped=random_stepped)

    # the RE-SHUFFLE pick from the A844 ring (B826)
    cursor = ring_cursor_a842 & 0xFFFF
    for _ in range(len(slot_ring) + 1):
        if cursor >= SLOT_RING_END_A894:
            cursor = SLOT_RING_BASE_A844
        idx = (cursor - SLOT_RING_BASE_A844) // 4
        raw_x, ring_y = slot_ring[idx]
        new_tx = (raw_x + SLOT_RING_X_BIAS) & 0xFFFF
        cursor = (cursor + 4) & 0xFFFF
        writes.update({0x34: new_tx, 0x32: ring_y & 0xFFFF})
        if x_word != new_tx or y_word != ring_y:
            break
    else:
        raise ValueError("A844 slot ring: every entry equals the current position (impossible ring)")
    return EnemyBehaviorStep(record_writes=writes, global_writes={0xA842: cursor},
                             shoot=shoot, random_stepped=random_stepped)

WAVE_CONTROLLER_SPRITE_BIAS = 0x3B     # the 0448 exit: sprite = direction (+0x06) + 0x3B, every frame
WAVE_CONTROLLER_SEEK_MODE = 3          # [2308] = 3 -- the 8px 5DB2 step
WAVE_CONTROLLER_BURST = 5              # five 81F4 spawns per waypoint arrival
WAVE_CONTROLLER_SCHEDULE_X_BIAS = 0x20  # schedule/ring x words are stored -0x20


@dataclass(frozen=True)
class WaveControllerStep:
    """One frame of the 0x1F wave controller: the seek movement, the every-frame sprite write,
    and (on waypoint arrival) the schedule advance + the five-enemy spawn burst."""

    x_word: int
    y_word: int
    direction: int               # +0x06 after the frame (the seek's write; unchanged when arrived)
    sprite: int                  # +0x08 = direction + 0x3B (written every frame at the 0448 exit)
    arrived: bool                # the seek's blocked branch == at the waypoint
    schedule_advance: int        # bytes to add to DS:A482 (4 on arrival, else 0)
    ring_cursor_after: int       # DS:A842 after the burst (+4 per spawn attempt, NO wrap in 0368)
    spawn_stamps: tuple          # 5 enemy stamps on arrival (caller drops one per failed alloc,
    #                              but the ring cursor advance above stays -- exactly the original)
    seek_globals: dict           # the every-frame B729-shape target setup: 2304/2306/2308


@recovered_island(
    asm=("1F8F:027A..02A0", "1F8F:0368..03A5", "1F8F:0448..0451", "1010:8D8B"),
    contract="behavior 0x1F (the planet-1 WAVE CONTROLLER, via the 8D4F stub + the 8D8B trampoline):"
             " seek the A482-schedule waypoint (x+0x20/y, 5DB2 mode 3); on arrival advance the"
             " schedule +4 and burst FIVE 81F4 spawns (leader-context = the controller's position,"
             " formation slots from the A844 ring cursor +4 each NO wrap, behavior 0x20, substate"
             " FFFF); sprite = direction + 0x3B every frame",
    status="VERIFIED",
    merge_target="EnemyWaveSystem",
    unknowns="the sibling family tails (0x13/0x15/0x1C/0x7D/0x7E) are separate recoveries; the"
             " burst's past-A894 ring reads are caller-owned (no wrap in 0368)",
)
def step_wave_controller_1f(*, x_word: int, y_word: int, direction: int,
                            schedule_x_raw: int, schedule_y: int,
                            ring_cursor_a842: int, ring_slot_at,
                            direction_table) -> WaveControllerStep:
    """One frame of behavior ``0x1F`` (``1F8F:027A``, the 0x1F tail), pure.

    ``schedule_x_raw``/``schedule_y`` are the CURRENT ``[A482]`` schedule pair (x without the +0x20
    bias); ``ring_slot_at(cursor_word) -> (x_raw, y)`` serves the ``A844`` ring reads (the burst
    does NOT wrap -- past-the-end reads are the caller's fail-loud concern).
    """
    target = MovementTarget(y_word=schedule_y & 0xFFFF,
                            x_word=(schedule_x_raw + WAVE_CONTROLLER_SCHEDULE_X_BIAS) & 0xFFFF)
    seek_globals = {0x2304: target.y_word, 0x2306: target.x_word,
                    0x2308: WAVE_CONTROLLER_SEEK_MODE}
    seek = object_target_seek_step_5db2(x_word, y_word, direction, target,
                                        WAVE_CONTROLLER_SEEK_MODE, direction_table)
    if not seek.blocked:
        return WaveControllerStep(
            x_word=seek.x_word, y_word=seek.y_word, direction=seek.direction_or_step,
            sprite=(seek.direction_or_step + WAVE_CONTROLLER_SPRITE_BIAS) & 0xFFFF,
            arrived=False, schedule_advance=0, ring_cursor_after=ring_cursor_a842 & 0xFFFF,
            spawn_stamps=(), seek_globals=seek_globals)

    # arrived at the waypoint: the 0368 burst
    stamps = []
    cursor = ring_cursor_a842 & 0xFFFF
    for _ in range(WAVE_CONTROLLER_BURST):
        ring_x_raw, ring_y = ring_slot_at(cursor)
        cursor = (cursor + 4) & 0xFFFF
        stamp = enemy_spawn_stamp_8209(x_word, y_word)
        stamp[0x34] = (ring_x_raw + WAVE_CONTROLLER_SCHEDULE_X_BIAS) & 0xFFFF
        stamp[0x32] = ring_y & 0xFFFF
        stamp[0x18] = 0x0020
        stamp[0x1C] = 0xFFFF
        stamps.append(stamp)
    return WaveControllerStep(
        x_word=x_word, y_word=y_word, direction=direction,
        sprite=(direction + WAVE_CONTROLLER_SPRITE_BIAS) & 0xFFFF,
        arrived=True, schedule_advance=4, ring_cursor_after=cursor,
        spawn_stamps=tuple(stamps), seek_globals=seek_globals)


# behavior 0x27 sprite scroller: the base sprite is planet-selected, animated on the DS:2338 clock.
SCROLLER_27_SPRITE_BASE = 0x0027           # 835D: default base sprite
SCROLLER_27_SPRITE_BASE_PLANET5 = 0x0024   # 8365: base on planet 5 (DS:2356 == 5)
SCROLLER_27_PLANET5 = 0x0005


@recovered_island(
    asm=("1010:835D..8377",),
    contract="behavior 0x27 (1010:835D): a pure sprite scroller -- sprite = base + (DS:2338 >> 1) "
             "with base 0x24 on planet 5 (DS:2356==5) else 0x27, then x += 1; the handler then "
             "falls into the shared BC45 postmove tail (drift/clamp/bounds/contact, caller-owned).",
    status="OBSERVED",
    merge_target="EnemyWaveSystem",
    unknowns="the +0x08 sprite is written raw; the BC45 tail (A278 drift, Y clamp, X-bounds death, "
             "BCCB contact, 62F6 scan) is applied by the caller, not here.",
)
def step_sprite_scroller_27_835d(*, clock_2338: int, planet_2356: int, x_word: int) -> EnemyBehaviorStep:
    """One frame of behavior ``0x27`` (``1010:835D``), pure.

    ``clock_2338`` is the DS:2338 sub-bank counter (mod 6); the ``>> 1`` gives a 3-phase sprite
    cycle over the animated base.  ``x_word`` is the record's +0x02 X, stepped +1 (the ``inc [bp+2]``
    before the ``jmp BC45``); the BC45 drift/clamp/collision tail runs afterwards in the caller.
    """
    base = (SCROLLER_27_SPRITE_BASE_PLANET5 if (planet_2356 & 0xFFFF) == SCROLLER_27_PLANET5
            else SCROLLER_27_SPRITE_BASE)
    sprite = (base + ((clock_2338 & 0xFFFF) >> 1)) & 0xFFFF
    return EnemyBehaviorStep(record_writes={0x08: sprite, 0x02: (x_word + 1) & 0xFFFF})


# behavior 0x2f patrol-bounce: static sprite, seek (caller), then drift the target and bounce target-y.
BOUNCE_2F_SPRITE = 0x0043           # 8820: fixed sprite
BOUNCE_2F_TARGET_Y_HI = 0x00C0      # 8849: the far bounce endpoint
BOUNCE_2F_TARGET_Y_LO = 0x0000      # 8841: the near bounce endpoint


@recovered_island(
    asm=("1010:8820..8851",),
    contract="behavior 0x2f (1010:8820): sprite=0x43, then the B729 seek (mode 2, caller-applied via "
             "5DB2); the target X (+0x34) drifts by DS:A278 every frame, and WHEN THE SEEK IS BLOCKED "
             "the target Y (+0x32) toggles between 0 and 0xC0 (a vertical patrol bounce); then BC45.",
    status="OBSERVED",
    merge_target="EnemyWaveSystem",
    unknowns="the seek itself (+0x02/+0x04/+0x06) is applied by the caller's _apply_seek; 'blocked' is "
             "the 5DB2 result (B729's `cmp [230A],0`), 230A being excluded shadow scratch.",
)
def step_bounce_scanner_2f(*, blocked: bool, target_y_32: int, target_x_34: int,
                           a278: int) -> EnemyBehaviorStep:
    """One frame of behavior ``0x2f`` (``1010:8820``), pure (the seek excluded).

    The caller runs the B729 seek first and passes its ``blocked`` flag.  This owns the non-seek
    writes: the fixed sprite, the target-X drift by ``a278``, and -- only when the seek was blocked --
    the target-Y bounce toggle (``0`` <-> ``0xC0``).
    """
    writes = {0x08: BOUNCE_2F_SPRITE, 0x34: (target_x_34 + a278) & 0xFFFF}
    if blocked:
        writes[0x32] = (BOUNCE_2F_TARGET_Y_HI if (target_y_32 & 0xFFFF) == 0
                        else BOUNCE_2F_TARGET_Y_LO)
    return EnemyBehaviorStep(record_writes=writes)
