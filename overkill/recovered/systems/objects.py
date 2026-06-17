"""Pure recovered object-system predicates.

No CPU, memory, DOS segment, hook state, or original continuation is allowed in
this module.  These predicates name gameplay decisions once multiple hooks or
traces have constrained their object-slot fields.
"""
from __future__ import annotations

from overkill.recovered.domain.object_behaviors import BossGroupSlotTransition, ObjectDeactivateDispatchDecision
from overkill.recovered.domain.object_slots import ObjectSlotRecord

PLAYER_CHASE_EXCLUDED_LOGIC_IDS = frozenset({0x0001, 0x0021, 0x0022, 0x0026})
PLAYER_CHASE_CANDIDATE_MAX_X = 0x00E0
PLAYER_CHASE_REQUIRED_HAZARD_CLASS = 0x0004
PLAYER_CHASE_ACQUIRED_MAX_X = 0x00DC
PLAYER_CHASE_INACTIVE_LOGIC_ID = 0x0001


def is_player_chase_target_candidate(slot: ObjectSlotRecord) -> bool:
    """Pure candidate gate recovered from the B15A scan used by B1B0.

    This does not mean "enemy" globally.  It is exactly the object-record family
    that the B1B0 behavior may acquire as its chase/focus target.
    """
    return (
        slot.active_word != 0
        and slot.logic_id not in PLAYER_CHASE_EXCLUDED_LOGIC_IDS
        and (slot.x_word & 0xFFFF) <= PLAYER_CHASE_CANDIDATE_MAX_X
        and slot.hazard_class == PLAYER_CHASE_REQUIRED_HAZARD_CLASS
    )


def is_player_chase_acquired_target_valid(slot: ObjectSlotRecord) -> bool:
    """Pure validity gate for B1B0's already-acquired chase target.

    B1B0 stores the acquired target slot pointer at current-object ``+30h``.
    On later frames it keeps chasing that slot only while the target remains
    active, stays inside the recovered right-side boundary, and has not become
    logic id ``0001h``.  This is still a narrow B1B0 predicate, not a global
    object-life classification.
    """
    return slot.active_word != 0 and (slot.x_word & 0xFFFF) <= PLAYER_CHASE_ACQUIRED_MAX_X and slot.logic_id != PLAYER_CHASE_INACTIVE_LOGIC_ID


# 1010:C054 deactivate dispatcher families.  These names are still
# dispatcher/source-level, not final gameplay archetype names.
OBJECT_DEACTIVATE_BOSS_GROUP_LOGIC_IDS = (0x0076, 0x0077, 0x0078, 0x0079)
OBJECT_DEACTIVATE_COUNTER_DROP_LOGIC_IDS = (
    0x0061, 0x0062, 0x0065,
    0x0014, 0x0016, 0x0017, 0x0018,
    0x007F, 0x0080, 0x0081,
    0x0093,
    0x001D, 0x001E, 0x0020, 0x0021, 0x0022,
)
OBJECT_DEACTIVATE_DEBUG_BYTE_LOGIC_ID = 0x0093
OBJECT_DEACTIVATE_SCRIPT_AX_BY_LOGIC_ID = {
    0x007E: 0xA79C,
    0x007D: 0xA6F0,
    0x001F: 0xA83E,
    0x001C: 0xA82A,
    0x0015: 0xA5C0,
    0x0013: 0xA4E4,
}



# C054 -> C15B/C194 multi-part boss group transition facts.
# These are source-level state values, not stack/debug glue.
BOSS_GROUP_DEACTIVATED_LOGIC_ID = 0x0001
BOSS_GROUP_TRANSITION_LATCH_CLEAR = 0x0000
BOSS_GROUP_SPRITE_OR_STATE_DEATH = 0x0003


def boss_group_transition_targets(current_slot_base: int, group_pointer_words: tuple[int, ...]) -> tuple[int, ...]:
    """Return sibling boss-part slots transitioned by C15B.

    The original C15B walks four DS:A8BA..A8C0 pointers and skips the pointer
    equal to the current object BP.  Keep this pure so the adapter owns only the
    DOS reads, CALL scratch return words, and C194 side effects.
    """
    current = current_slot_base & 0xFFFF
    return tuple(ptr & 0xFFFF for ptr in group_pointer_words if (ptr & 0xFFFF) != current)


def boss_group_slot_transition_c194(previous_logic_id: int) -> BossGroupSlotTransition:
    """Pure C194 state assignment for one sibling boss part."""
    return BossGroupSlotTransition(
        previous_logic_id=previous_logic_id & 0xFFFF,
        logic_id=BOSS_GROUP_DEACTIVATED_LOGIC_ID,
        transition_latch=BOSS_GROUP_TRANSITION_LATCH_CLEAR,
        sprite_or_state=BOSS_GROUP_SPRITE_OR_STATE_DEATH,
    )

def object_deactivate_dispatch_decision_c054(logic_id: int) -> ObjectDeactivateDispatchDecision:
    """Pure source-like classification recovered from 1010:C054.

    The hook/adapter layer still replays the original CMP order so flags stay
    oracle-compatible.  This pure function owns the stable gameplay dispatcher
    classification: multi-part boss group transition, global counter drop, AX
    script selection, or no observed C054 action.
    """
    selector = logic_id & 0xFFFF
    if selector in OBJECT_DEACTIVATE_BOSS_GROUP_LOGIC_IDS:
        return ObjectDeactivateDispatchDecision("boss_group_transition")
    if selector in OBJECT_DEACTIVATE_COUNTER_DROP_LOGIC_IDS:
        return ObjectDeactivateDispatchDecision("counter_drop")
    ax_script = OBJECT_DEACTIVATE_SCRIPT_AX_BY_LOGIC_ID.get(selector)
    if ax_script is not None:
        return ObjectDeactivateDispatchDecision("script_select", ax_script=ax_script)
    return ObjectDeactivateDispatchDecision("none")
