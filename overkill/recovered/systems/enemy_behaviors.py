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

from overkill.recovered.islands import recovered_island

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