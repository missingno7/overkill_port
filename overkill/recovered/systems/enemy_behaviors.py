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
from overkill.recovered.systems.movement import (
    object_delta_steer_5e42,
    object_target_seek_step_5db2,
)

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


# behavior 0x30 spawner: a [233C]-clocked sprite animation that periodically spawns a C237 child.
SPAWNER_30_PLANET5 = 0x0005
SPAWNER_30_SPRITE_BIAS = 0x0044      # 887A: sprite = table[233C] + 0x44
SPAWNER_30_FREEZE_DY = 0x000C        # planet-5 anchor-proximity freeze threshold
SPAWNER_30_FREEZE_SPRITE = 0x0046
SPAWNER_30_GATE_2326_PLANET5 = 0x0003   # planet-5 spawn gate on [2326]
SPAWNER_30_GATE_232A = 0x000F           # non-planet-5 spawn gate on [232A]


@dataclass(frozen=True, slots=True)
class Spawner30Step:
    """behavior 0x30 per-frame outcome (caller applies)."""
    early_return: bool   # planet-5 anchor-freeze: skip the anim + spawn
    sprite: int          # the animated sprite to write to +0x08 (when not early_return)
    spawn: bool          # fire the C237 child spawn + sound 0x0E this frame


@recovered_island(
    asm=("1010:8851..88A7",),
    contract="behavior 0x30 (1010:8851): a [233C]-clocked sprite animation (sprite = "
             "table[96D2 + 233C*2] + 0x44) that spawns a C237 child + plays sound 0x0E when its "
             "spawn gate fires (planet5: [2326]==3, else [232A]==0xF); the planet-5 branch also "
             "freezes (skip anim+spawn) when |[2380]-y| >= 0xC and the sprite is already 0x46.",
    status="OBSERVED",
    merge_target="EnemyWaveSystem",
    unknowns="the planet-5 sub-paths ([2356]==5) are modelled from the disasm but NOT exercised by "
             "the L1 demo shadow; the C237 spawn + the BEFF=0x0E sound are applied by the caller.",
)
def step_spawner_anim_30(*, planet_2356: int, anchor_y_2380: int, y_word: int, sprite_08: int,
                         anim_table_value: int, gate_2326: int, gate_232a: int) -> Spawner30Step:
    """One frame of behavior ``0x30`` (``1010:8851``), pure (the C237 spawn excluded).

    ``anim_table_value`` is the word the caller read from ``DS:[96D2 + 233C*2]``.  On planet 5 the
    actor freezes (no anim, no spawn) when it is far enough from the anchor and already showing the
    ``0x46`` sprite.  The spawn gate differs by planet; the caller runs C237 + the sound when
    ``spawn`` is set.
    """
    p5 = (planet_2356 & 0xFFFF) == SPAWNER_30_PLANET5
    if p5:
        raw = (anchor_y_2380 - y_word) & 0xFFFF
        dy = raw if raw < 0x8000 else (0x10000 - raw)
        if dy >= SPAWNER_30_FREEZE_DY and (sprite_08 & 0xFFFF) == SPAWNER_30_FREEZE_SPRITE:
            return Spawner30Step(early_return=True, sprite=sprite_08 & 0xFFFF, spawn=False)
    sprite = (anim_table_value + SPAWNER_30_SPRITE_BIAS) & 0xFFFF
    spawn = ((gate_2326 & 0xFFFF) == SPAWNER_30_GATE_2326_PLANET5 if p5
             else (gate_232a & 0xFFFF) == SPAWNER_30_GATE_232A)
    return Spawner30Step(early_return=False, sprite=sprite, spawn=spawn)


# behaviors 0x90 / 0x91 animated spawners (1010:8282 / 8291): identical but for the base sprite.
# The [2330]>>5 clock indexes the DS:95EA table; the value is BOTH the sprite delta AND the 82CA
# jump-table selector (only values 0/1/2 occur on L1: 95EA[0..3] = {1,0,1,2}).
ANIM_SPAWNER_90_BASE = 0x0088
ANIM_SPAWNER_90_BASE_PLANET4 = 0x016C
ANIM_SPAWNER_91_BASE = 0x008B
ANIM_SPAWNER_91_BASE_PLANET4 = 0x016F
ANIM_SPAWNER_PLANET4 = 0x0004
ANIM_SPAWNER_GATE_232C = 0x001F


@dataclass(frozen=True, slots=True)
class AnimSpawner9091Step:
    """behaviors 0x90/0x91 per-frame outcome (caller applies the sprite + the offset spawn)."""
    sprite: int
    spawn_x_delta: "int | None"   # None = no spawn; -4 / +4 = spawn a C237 child at that X offset


@recovered_island(
    asm=("1010:8282..82E9",),
    contract="behaviors 0x90/0x91 (1010:8282/8291): base sprite (0x88/0x8B, or 0x16C/0x16F on planet "
             "4) + the DS:95EA[[2330]>>5] delta; when [232C]==0x1F the same table value selects the "
             "82CA action -- value 0 spawns a C237 child at X-4, value 2 at X+4, value 1 does nothing "
             "(the ONLY values reachable on L1). The X offset is applied around the C237 call.",
    status="OBSERVED",
    merge_target="EnemyWaveSystem",
    unknowns="the 82CA table entries for values >=3 (targets 4683/0402/... ) are NOT reachable on L1 "
             "(95EA[0..3]={1,0,1,2}) and are left unrecovered (ValueError); the C237 spawn is caller-run.",
)
def step_animated_spawner_90_91(*, base_normal: int, base_planet4: int, planet_2356: int,
                                anim_table_value: int, gate_232c: int) -> AnimSpawner9091Step:
    """One frame of behavior ``0x90``/``0x91`` (``1010:8282``/``8291``), pure (the C237 spawn excluded).

    ``anim_table_value`` is the ``DS:95EA[[2330]>>5]`` word the caller read.  It is added to the
    planet-selected base sprite AND, on the ``[232C]==0x1F`` frame, selects the 82CA action: 0 -> a
    C237 child spawned at ``X-4``, 2 -> at ``X+4``, 1 -> nothing.  The caller applies the sprite write
    and, per ``spawn_x_delta``, the offset-then-C237-then-restore.
    """
    base = base_planet4 if (planet_2356 & 0xFFFF) == ANIM_SPAWNER_PLANET4 else base_normal
    tv = anim_table_value & 0xFFFF
    sprite = (base + tv) & 0xFFFF
    spawn_x_delta = None
    if (gate_232c & 0xFFFF) == ANIM_SPAWNER_GATE_232C:
        if tv == 0:
            spawn_x_delta = -4
        elif tv == 2:
            spawn_x_delta = 4
        elif tv != 1:
            raise ValueError(f"unverified 82CA jump target for 95EA value {tv:#x} (only 0/1/2 on L1)")
    return AnimSpawner9091Step(sprite=sprite, spawn_x_delta=spawn_x_delta)


# behaviors 0x11/0x12 (1010:B2C3/B2CD): the cold A43C waypoint-path follower. 0x11 is a one-shot
# morph (seed the waypoint pointer, retag the record as 0x12) that falls straight into 0x12's body.
WAYPOINT_FOLLOWER_TABLE_SEED = 0xA43C     # 0x11's one-time reset value for the +0x36 pointer field
WAYPOINT_FOLLOWER_X_BIAS = 0x0020         # B2D1: the raw table X gets +0x20 before it's a target
WAYPOINT_FOLLOWER_MAX_RETRIES = 64        # the ASM loops with no explicit bound; this is a fail-loud cap
WAYPOINT_FOLLOWER_MODE_PLANET0 = 0x0002   # planet 0 or BDAC==1 -> 5DB2 mode 2 (AF60 double-step)
WAYPOINT_FOLLOWER_BDAC_SPRITE_BIAS = 0x003B
WAYPOINT_FOLLOWER_BOSS_PLANETS = (0x0000, 0x0005, 0x0006)
WAYPOINT_FOLLOWER_BOSS_GATE_2350 = 0x0E52
WAYPOINT_FOLLOWER_SPRITE_BY_PLANET = {
    0x0001: 0x002A, 0x0002: 0x00D2, 0x0003: 0x00EC, 0x0004: 0x00EC, 0x0007: 0x00EC,
}
WAYPOINT_FOLLOWER_SPRITE_DEFAULT = 0x00EC          # any planet not explicitly listed above
WAYPOINT_FOLLOWER_SPRITE_BOSS_NO_GATE = 0x0115     # planet in (0,5,6), [2350] != the E52 gate
WAYPOINT_FOLLOWER_SPRITE_BOSS_GATED = {0x0000: 0x0105, 0x0006: 0x0105}   # planet 5 falls to DEFAULT


@dataclass(frozen=True, slots=True)
class WaypointFollowerStep:
    """behaviors 0x11/0x12 per-frame outcome: the seek result + the advanced waypoint pointer +
    sprite. Caller applies via BC4B (no A278 drift, unlike the BC45-tail actors).  ``target_x_2306``/
    ``target_y_2304`` are B2D4/B2D8's own global writes (every retry re-writes them; only the FINAL
    -- the successful attempt's -- survives to the frame boundary); ``seek_mode_2308`` is B2DB/B2EF's
    seek-mode global write (1, overwritten to 2 iff planet==0 or BDAC==1 -- same per retry)."""
    x_word: int
    y_word: int
    direction_or_step: int
    waypoint_ptr_after: int
    sprite: int
    target_x_2306: int
    target_y_2304: int
    seek_mode_2308: int


def _waypoint_follower_sprite(direction: int, bdac: int, planet: int, boss_2350: int) -> int:
    if (bdac & 0xFFFF) == 0x0001:
        return (direction + WAYPOINT_FOLLOWER_BDAC_SPRITE_BIAS) & 0xFFFF
    p = planet & 0xFFFF
    if p in WAYPOINT_FOLLOWER_BOSS_PLANETS:
        if (boss_2350 & 0xFFFF) != WAYPOINT_FOLLOWER_BOSS_GATE_2350:
            return (direction + WAYPOINT_FOLLOWER_SPRITE_BOSS_NO_GATE) & 0xFFFF
        return (direction + WAYPOINT_FOLLOWER_SPRITE_BOSS_GATED.get(
            p, WAYPOINT_FOLLOWER_SPRITE_DEFAULT)) & 0xFFFF
    return (direction + WAYPOINT_FOLLOWER_SPRITE_BY_PLANET.get(
        p, WAYPOINT_FOLLOWER_SPRITE_DEFAULT)) & 0xFFFF


@recovered_island(
    asm=("1010:B2C3..B2CD (the 0x11 one-shot morph)", "1010:B2CD..B3BC (the 0x12 waypoint follower)"),
    contract="behaviors 0x11/0x12: 0x11 seeds the +0x36 waypoint pointer to the cold A43C table and "
             "retags the record 0x12, then falls into 0x12's body. 0x12 reads (x+0x20,y) pairs from "
             "the pointer via the 5DB2 seek (mode 2 iff planet==0 or BDAC==1, else mode 1); on a "
             "BLOCKED seek it advances the pointer by 4 and retries with the next pair (until a seek "
             "succeeds); the final direction picks the sprite via a planet/BDAC-keyed bias table "
             "(the full B2C3..B3BC cascade, byte-decoded). Exits via BC4B (no drift).",
    status="OBSERVED",
    merge_target="EnemyWaveSystem",
    unknowns="the cold A43C table's actual length/content is read live via waypoint_at, not modelled "
             "as fixed data here; WAYPOINT_FOLLOWER_MAX_RETRIES is a fail-loud safety cap, not an "
             "ASM-derived bound (the original loop has none).",
)
def step_waypoint_follower_11_12(*, x_word: int, y_word: int, direction: int, waypoint_ptr: int,
                                 waypoint_at, bdac: int, planet_2356: int,
                                 boss_2350: int, direction_table) -> WaypointFollowerStep:
    """One frame of behaviors 0x11/0x12 (``1010:B2C3``/``B2CD``), pure.

    ``waypoint_at(ptr)`` returns the ``(raw_x, y)`` word pair the caller reads from ``DS:[ptr]``/
    ``DS:[ptr+2]`` (the cold A43C table).  Loops the 5DB2 seek across successive pairs (advancing
    ``ptr`` by 4 each time the seek reports blocked) until one succeeds, returning the final
    position/direction, the pointer to persist into ``+0x36``, and the sprite.
    """
    mode = (WAYPOINT_FOLLOWER_MODE_PLANET0
            if (planet_2356 & 0xFFFF) == 0x0000 or (bdac & 0xFFFF) == 0x0001 else 0x0001)
    ptr = waypoint_ptr & 0xFFFF
    x, y, d = x_word & 0xFFFF, y_word & 0xFFFF, direction & 0xFFFF
    target_x = target_y = 0
    for _ in range(WAYPOINT_FOLLOWER_MAX_RETRIES):
        raw_x, raw_y = waypoint_at(ptr)
        target_x = (raw_x + WAYPOINT_FOLLOWER_X_BIAS) & 0xFFFF
        target_y = raw_y & 0xFFFF
        step = object_target_seek_step_5db2(
            x, y, d, MovementTarget(y_word=target_y, x_word=target_x), mode, direction_table)
        if not step.blocked:
            x, y, d = step.x_word, step.y_word, step.direction_or_step
            break
        ptr = (ptr + 4) & 0xFFFF
    else:
        raise ValueError(f"waypoint follower exceeded {WAYPOINT_FOLLOWER_MAX_RETRIES} blocked retries "
                         f"(ptr={ptr:#06x}) -- the A43C table may not terminate as expected")
    sprite = _waypoint_follower_sprite(d, bdac, planet_2356, boss_2350)
    return WaypointFollowerStep(x_word=x, y_word=y, direction_or_step=d,
                                waypoint_ptr_after=ptr, sprite=sprite,
                                target_x_2306=target_x, target_y_2304=target_y,
                                seek_mode_2308=mode)


# 1010:74E2 retarget: refresh a record's steer deltas (+0x2A/+0x2C) toward the CURRENT view/anchor
# position -- the same Y-bias formula formation_spawn_seed_7476 already uses for a fresh spawn.
RETARGET_74E2_VIEW_Y_BIAS = 0x0009


def retarget_delta_toward_anchor_74e2(record_x: int, record_y: int,
                                      anchor_x_237e: int, anchor_y_2380: int) -> "tuple[int, int]":
    """Pure 1010:74E2: ``(move_delta_x, move_delta_y)`` toward the current view/anchor.

    ``move_delta_x = record_x - anchor_x_237e``; ``move_delta_y = record_y - (anchor_y_2380 + 9)``
    (the same ``+9`` Y bias as :func:`formation_spawn_seed_7476`).  Pure arithmetic; the caller
    writes the pair into the record's ``+0x2A``/``+0x2C`` fields.
    """
    move_delta_x = (record_x - anchor_x_237e) & 0xFFFF
    move_delta_y = (record_y - (anchor_y_2380 + RETARGET_74E2_VIEW_Y_BIAS)) & 0xFFFF
    return move_delta_x, move_delta_y


# behavior 0x29 (1010:8721): a sprite ramp-then-retarget, steered by the recovered 5E42 delta-steer,
# with a Y-bounds death check.
RAMP_29_TARGET_SPRITE = 0x00A4
RAMP_29_GATE_2328 = 0x0007
RAMP_29_STEER_MODE_DURING = 0x0002   # [2312] during the 5E42 call (2px step, not the 3px AF22 mode)
RAMP_29_STEER_MODE_AFTER = 0x0003    # [2312] restored after (read by some OTHER caller next time)
RAMP_29_DEATH_Y_MAX = 0x00C0
RAMP_29_DEATH_Y_MIN = 0x0000


@dataclass(frozen=True, slots=True)
class Ramp29Step:
    """behavior 0x29 per-frame outcome (caller applies; the 5E42 steer + Y-bounds death check run
    outside, since they need the steered Y this decision doesn't compute)."""
    fired: bool                 # False = the 2328 gate missed entirely -> BC45 untouched
    sprite: "int | None"
    retarget: bool               # True -> the caller refreshes move_delta_x/y via 74E2 before steering
    steer: bool                  # True -> the caller runs the 5E42 steer (writes direction/x/y/error)


@recovered_island(
    asm=("1010:8721..8766",),
    contract="behavior 0x29 (1010:8721): if sprite != 0xA4, gate on [2328]==7 then ramp sprite += 1 "
             "(else no-op this frame); once the ramp reaches 0xA4, retarget (74E2) and steer (5E42, "
             "[2312]=2 during the call); then a Y-bounds check (y>0xC0 or y<0) runs the BFC7 death; "
             "else BC45.",
    status="OBSERVED",
    merge_target="EnemyWaveSystem",
    unknowns="the steer (5E42) and death (BFC7) actions, plus the Y-bounds check they gate on, are "
             "applied by the caller; this owns the ramp/gate/retarget-trigger decision only.",
)
def step_ramp_steer_29(*, sprite: int, gate_2328: int) -> Ramp29Step:
    """One frame of behavior ``0x29`` (``1010:8721``), pure (the 74E2/5E42/BFC7 actions excluded).

    ``sprite`` is the record's current ``+0x08``.  Returns whether this frame fires at all (the
    ``[2328]==7`` gate, skipped once ``sprite`` already equals the ramp target), the ramped sprite,
    and whether the ramp JUST reached the target (triggering a 74E2 retarget before steering).
    """
    if (sprite & 0xFFFF) == RAMP_29_TARGET_SPRITE:
        return Ramp29Step(fired=True, sprite=None, retarget=False, steer=True)
    if (gate_2328 & 0xFFFF) != RAMP_29_GATE_2328:
        return Ramp29Step(fired=False, sprite=None, retarget=False, steer=False)
    new_sprite = (sprite + 1) & 0xFFFF
    reached = new_sprite == RAMP_29_TARGET_SPRITE
    return Ramp29Step(fired=True, sprite=new_sprite, retarget=reached, steer=reached)


# behavior 0x01's key-1 latch-9 MORPH (1010:BE5A/BE60) and its target, behavior 0x26 (1010:8302).
# When a dying key-1 record's latch counter (+0x22) reaches 9, its PREVIOUS logic id (+0x1A) picks a
# morph: 0x24 -> float UP (direction 6, sprite 0x97, y -= 8); 0x25 -> float DOWN (direction 2, sprite
# 0x91, y += 8); anything else -> the BD17 deactivate.  The morph stamps behavior 0x26, saves the
# (new) position into +0x32 (y) / +0x34 (x), and RETURNS -- skipping the BC45 postmove THIS frame.
# 0x26 then AFD8-floats in that direction each frame; on a blocked step OR y >= 0xC0 the sprite ramps
# +1 (with sound 0x1E) to the FINISHED sprite (0x98/0x92), where it waits for DS:2326 == 3 to reset
# y from +0x32 and drop the sprite back -- a respawn loop.
DYING_LATCH9_MORPHS = {0x24: (0x0006, 0x0097, -8), 0x25: (0x0002, 0x0091, 8)}
MORPH_26_FINISHED_SPRITES = (0x0098, 0x0092)
MORPH_26_RESET_GATE_2326 = 0x0003
MORPH_26_DEATH_Y = 0x00C0
MORPH_26_RAMP_SOUND = 0x001E


@recovered_island(
    asm=("1010:BE5A..BEA3",),
    contract="behavior 0x01 key-1 latch-9 morph (1010:BE60): previous logic id 0x24 -> (direction 6, "
             "sprite 0x97, y-=8); 0x25 -> (direction 2, sprite 0x91, y+=8); else None (-> the BD17 "
             "deactivate). The caller stamps behavior 0x26, writes +0x32=new_y / +0x34=x, and SKIPS "
             "the BC45 postmove this frame (the morph path RETURNS, unlike the BEA4/BEB9 anim paths).",
    status="OBSERVED",
    merge_target="EnemyWaveSystem",
    unknowns="none -- a 3-way constant table, fully decoded",
)
def dying_latch9_morph_be60(prev_logic_id: int) -> "tuple[int, int, int] | None":
    """The (direction, sprite, y_delta) morph for a latch-9 dying record, or ``None`` -> deactivate."""
    return DYING_LATCH9_MORPHS.get(prev_logic_id & 0xFFFF)


@recovered_island(
    asm=("1010:8302..8330 (the float+ramp)", "1010:82EC..8301 (the finished-wait/reset)"),
    contract="behavior 0x26 (1010:8302): if sprite is FINISHED (0x98/0x92), wait for DS:2326==3 then "
             "y = +0x32 and sprite -= 1 (the reset); otherwise AFD8-step in the record's direction -- "
             "a BLOCKED step or y >= 0xC0 ramps the sprite +1 (sound 0x1E via [98C0]); else nothing. "
             "All paths exit jmp BC45 (WITH drift).",
    status="OBSERVED",
    merge_target="EnemyWaveSystem",
    unknowns="the AFD8 step (with the wired BDD0 contact predicate) runs in the adapter; this owns "
             "the finished/reset/ramp decision only.",
)
def morph_26_is_finished(sprite: int) -> bool:
    """Whether the 0x26 float has already ramped to its finished sprite (0x98/0x92)."""
    return (sprite & 0xFFFF) in MORPH_26_FINISHED_SPRITES


def morph_26_should_reset(gate_2326: int) -> bool:
    """Whether a finished 0x26 resets this frame (``DS:2326 == 3``)."""
    return (gate_2326 & 0xFFFF) == MORPH_26_RESET_GATE_2326


def morph_26_should_ramp(blocked: bool, y_word: int) -> bool:
    """Whether the 0x26 float ramps its sprite this frame (a blocked step OR y >= 0xC0)."""
    return blocked or (y_word & 0xFFFF) >= MORPH_26_DEATH_Y


# behaviors 0x28 / 0x2A (1010:8676, an alias group): an animated SPAWNER. The 8654 helper animates
# a sprite from a DS:96AA ramp table indexed by a per-record counter (+0x06) that advances only when
# DS:2332 == 0 (wrapping mod 0x18); once per cycle -- when the counter is exactly 7 AND no enemies
# are active (DS:A47E == 0) -- it fires a child via the 81F4 spawn worker (the recovered
# enemy_spawn_stamp_8209 over a 7524 effect-slot), then bumps the counter past 7.  The child's final
# behavior/sprite are a per-planet override the caller applies (planet 1: behavior 0x29, sprite 0xA1).
SPAWNER_28_SPRITE_BIAS = 0x001C          # 8676: cx = 0x1C (the sprite table's additive bias)
SPAWNER_28_COUNTER_WRAP = 0x0018         # 8654: the +0x06 counter wraps mod 0x18
SPAWNER_28_SPAWN_COUNTER = 0x0007        # 86A0: spawn fires the frame the counter equals 7


@dataclass(frozen=True, slots=True)
class Spawner28Step:
    """behavior 0x28 per-frame outcome (caller applies the record writes + the 81F4 spawn)."""
    counter: int         # the new +0x06 counter (already bumped past 7 on a spawn frame)
    sprite: int          # the animated sprite to write to +0x08
    spawn: bool          # fire the 81F4 child spawn this frame (caller does alloc + stamp + override)


@recovered_island(
    asm=("1010:8654..8675", "1010:8676..86A5"),
    contract="behavior 0x28 (1010:8676 + its 8654 helper), planet-1 path: advance the +0x06 counter "
             "when DS:2332==0 (wrap mod 0x18); sprite = DS:96AA[counter] + 0x1C. Then, iff "
             "DS:A47E==0 AND counter==7, bump the counter (+1) and fire the 81F4 spawn; else no spawn.",
    status="OBSERVED",
    merge_target="EnemyWaveSystem",
    unknowns="the 81F4 spawn (7524 alloc + enemy_spawn_stamp_8209 + the [98C0] sound) and the "
             "per-planet child override (planet 1: +0x18=0x29, +0x08=0xA1, +0x20=4, X/Y += 8) are "
             "applied by the caller; the non-planet-1 child variants (0x2B/0x7A) are not L1-exercised.",
)
def step_spawner_28(*, counter_06: int, gate_2332: int, active_a47e: int,
                    sprite_table: "tuple[int, ...]") -> Spawner28Step:
    """One frame of behavior ``0x28`` (``1010:8676``), pure (the 81F4 spawn excluded).

    ``counter_06`` is the record's current ``+0x06``; ``sprite_table`` is the 0x18-byte ``DS:96AA``
    ramp the caller read live.  The counter advances (wrapping mod 0x18) only on frames where
    ``DS:2332 == 0``; the sprite is always ``table[counter] + 0x1C``.  The spawn gate (``DS:A47E==0``
    and ``counter == 7``) also bumps the counter one past 7 so it fires exactly once per cycle.
    """
    counter = counter_06 & 0xFFFF
    if (gate_2332 & 0xFFFF) == 0:
        counter = (counter + 1) & 0xFFFF
        if counter >= SPAWNER_28_COUNTER_WRAP:
            counter = 0
    sprite = (sprite_table[counter] + SPAWNER_28_SPRITE_BIAS) & 0xFFFF
    spawn = (active_a47e & 0xFFFF) == 0 and counter == SPAWNER_28_SPAWN_COUNTER
    if spawn:
        counter = (counter + 1) & 0xFFFF
    return Spawner28Step(counter=counter, sprite=sprite, spawn=spawn)
