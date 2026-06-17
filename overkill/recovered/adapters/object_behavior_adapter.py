"""DOS/ASM adapters for recovered object-behavior predicates."""
from __future__ import annotations

from overkill.recovered.adapters.asm_flags import cmp_byte, cmp_word
from overkill.recovered.adapters.object_slot_adapter import read_object_slot_record
from overkill.recovered.systems.objects import (
    OBJECT_DEACTIVATE_BOSS_GROUP_LOGIC_IDS,
    OBJECT_DEACTIVATE_COUNTER_DROP_LOGIC_IDS,
    OBJECT_DEACTIVATE_DEBUG_BYTE_LOGIC_ID,
    OBJECT_DEACTIVATE_SCRIPT_AX_BY_LOGIC_ID,
    PLAYER_CHASE_ACQUIRED_MAX_X,
    PLAYER_CHASE_CANDIDATE_MAX_X,
    PLAYER_CHASE_EXCLUDED_LOGIC_IDS,
    PLAYER_CHASE_INACTIVE_LOGIC_ID,
    PLAYER_CHASE_REQUIRED_HAZARD_CLASS,
    boss_group_slot_transition_c194,
    boss_group_transition_targets,
    is_player_chase_acquired_target_valid,
    is_player_chase_target_candidate,
    object_deactivate_dispatch_decision_c054,
)
from overkill.recovered.views.object_slots import ObjectSlotView


def run_player_chase_candidate_checks_b15a(cpu, slot: ObjectSlotView) -> bool:
    """Replay B15A's candidate gate with a pure source-layer predicate.

    B15A is the target-acquisition scan used by B1B0.  Keep the loop/cursor
    mechanics in the lifted routine, but make the candidate decision canonical
    here so it is not duplicated between hook code and pure recovered systems.
    """
    pure_candidate = is_player_chase_target_candidate(read_object_slot_record(slot))

    active = slot.active_word
    cmp_word(cpu, active, 0)
    if active == 0:
        if pure_candidate:
            raise AssertionError("pure B15A candidate predicate disagrees on active-word gate")
        return False

    logic_id = slot.logic_id
    asm_excluded_logic_ids = (0x0001, 0x0026, 0x0021, 0x0022)
    if set(asm_excluded_logic_ids) != PLAYER_CHASE_EXCLUDED_LOGIC_IDS:
        raise AssertionError("B15A ASM exclusion order no longer matches pure predicate set")
    for excluded in asm_excluded_logic_ids:
        cmp_word(cpu, logic_id, excluded)
        if logic_id == excluded:
            if pure_candidate:
                raise AssertionError("pure B15A candidate predicate disagrees on logic-id exclusion")
            return False

    x_word = slot.x_word
    cmp_word(cpu, x_word, PLAYER_CHASE_CANDIDATE_MAX_X)
    if x_word > PLAYER_CHASE_CANDIDATE_MAX_X:
        if pure_candidate:
            raise AssertionError("pure B15A candidate predicate disagrees on X boundary")
        return False

    hazard_class = slot.hazard_class
    cmp_word(cpu, hazard_class, PLAYER_CHASE_REQUIRED_HAZARD_CLASS)
    candidate = hazard_class == PLAYER_CHASE_REQUIRED_HAZARD_CLASS
    if pure_candidate != candidate:
        raise AssertionError("pure B15A candidate predicate disagrees on hazard-class gate")
    return candidate


def run_player_chase_acquired_target_validity_b1b0(cpu, target_slot: ObjectSlotView) -> bool:
    """Replay B1B0's acquired-target validity checks with pure-system proof.

    The pure system owns the source-port decision.  This adapter keeps the exact
    original compare order so the live 8086 flags at each rejection/acceptance
    boundary still match the ASM oracle.
    """
    pure_valid = is_player_chase_acquired_target_valid(read_object_slot_record(target_slot))

    active = target_slot.active_word
    cmp_word(cpu, active, 0)
    if active == 0:
        if pure_valid:
            raise AssertionError("pure B1B0 acquired-target predicate disagrees on active-word gate")
        return False

    x_word = target_slot.x_word
    cmp_word(cpu, x_word, PLAYER_CHASE_ACQUIRED_MAX_X)
    if x_word > PLAYER_CHASE_ACQUIRED_MAX_X:
        if pure_valid:
            raise AssertionError("pure B1B0 acquired-target predicate disagrees on X boundary")
        return False

    logic_id = target_slot.logic_id
    cmp_word(cpu, logic_id, PLAYER_CHASE_INACTIVE_LOGIC_ID)
    valid = logic_id != PLAYER_CHASE_INACTIVE_LOGIC_ID
    if pure_valid != valid:
        raise AssertionError("pure B1B0 acquired-target predicate disagrees on logic-id gate")
    return valid

# C054 -> C15B/C194 final-boss/multipart transition DOS glue.
# Keep the source-level values in recovered.systems.objects; these constants are
# addresses, debug globals, and CALL scratch words that belong to the adapter.
BOSS_GROUP_POINTER_OFFSETS_AND_RETURN_IPS = (
    (0xA8BA, 0xC166),
    (0xA8BC, 0xC171),
    (0xA8BE, 0xC17C),
    (0xA8C0, 0xC187),
)
BOSS_GROUP_COUNTER_GLOBAL = 0xA47E
BOSS_GROUP_LATCH_GLOBAL = 0xA8C2
BOSS_GROUP_DEBUG_FLAG = 0x98C0
BOSS_GROUP_DEBUG_CODE_ADDR = 0xBEFF
BOSS_GROUP_DEBUG_CODE = 0x19
OBJECT_DEACTIVATE_DEBUG_BYTE = 0x98A8


def run_boss_group_slot_transition_c194(cpu, slot_bx: int) -> None:
    """Replay C194 for one sibling boss part while proving pure state values.

    The pure recovered system owns the final field values.  This adapter owns
    the debug byte, AX side effect, and direct DOS-memory writes used by the ASM
    oracle.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    slot = ObjectSlotView.from_ds(cpu, slot_bx)

    cmp_byte(cpu, mem.rb(ds, BOSS_GROUP_DEBUG_FLAG), 0x00)
    if mem.rb(ds, BOSS_GROUP_DEBUG_FLAG) != 0:
        mem.wb(ds, BOSS_GROUP_DEBUG_CODE_ADDR, BOSS_GROUP_DEBUG_CODE)

    previous_logic = slot.logic_id
    transition = boss_group_slot_transition_c194(previous_logic)
    s.ax = previous_logic & 0xFFFF
    slot.previous_logic_id = transition.previous_logic_id
    slot.logic_id = transition.logic_id
    slot.transition_latch = transition.transition_latch
    slot.sprite_or_state = transition.sprite_or_state


def run_boss_group_transition_c15b(cpu) -> None:
    """Replay C054 -> C15B, the final-boss/multipart group transition.

    C15B reads four boss-part pointers from DS:A8BA..A8C0, skips the current
    BP, CALLs C194 for sibling slots, then clears the global group counters.
    The pure layer chooses the sibling target set; this adapter preserves the
    CMP order, CALL return scratch words, and global DOS writes.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    pointer_words = tuple(mem.rw(ds, ptr_off) for ptr_off, _return_ip in BOSS_GROUP_POINTER_OFFSETS_AND_RETURN_IPS)
    pure_targets = boss_group_transition_targets(bp, pointer_words)
    asm_targets: list[int] = []

    for ptr_off, return_ip in BOSS_GROUP_POINTER_OFFSETS_AND_RETURN_IPS:
        s.bx = mem.rw(ds, ptr_off)
        cmp_word(cpu, s.bx, bp)
        if (s.bx & 0xFFFF) != bp:
            asm_targets.append(s.bx & 0xFFFF)
            # C194 RET leaves this word below SP as freed stack scratch.
            mem.ww(ss, (s.sp - 2) & 0xFFFF, return_ip)
            run_boss_group_slot_transition_c194(cpu, s.bx)

    if tuple(asm_targets) != pure_targets:
        raise AssertionError("pure C15B boss-group target set disagrees with ASM-compatible walk")

    mem.ww(ds, BOSS_GROUP_COUNTER_GLOBAL, 0x0000)
    mem.ww(ds, BOSS_GROUP_LATCH_GLOBAL, 0x0000)


def run_object_deactivate_logic_dispatch_c054_body(cpu) -> None:
    """Replay the observed BD17/BFC7 -> C054 variant dispatcher.

    The pure system owns the stable dispatch classification.  This adapter keeps
    the original CMP order, AX script side effect, DS:A47E/98A8 writes, and the
    C15B boss group transition.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    selector = ObjectSlotView.from_ss_bp(cpu).logic_id
    decision = object_deactivate_dispatch_decision_c054(selector)

    for value in OBJECT_DEACTIVATE_BOSS_GROUP_LOGIC_IDS:
        cmp_word(cpu, selector, value)
        if selector == value:
            if decision.kind != "boss_group_transition":
                raise AssertionError("pure C054 decision disagrees on boss-group selector")
            run_boss_group_transition_c15b(cpu)
            return

    for value in OBJECT_DEACTIVATE_COUNTER_DROP_LOGIC_IDS:
        cmp_word(cpu, selector, value)
        if selector == value:
            if decision.kind != "counter_drop":
                raise AssertionError("pure C054 decision disagrees on counter-drop selector")
            if selector == OBJECT_DEACTIVATE_DEBUG_BYTE_LOGIC_ID:
                mem.wb(ds, OBJECT_DEACTIVATE_DEBUG_BYTE, 0x01)
            old = mem.rw(ds, BOSS_GROUP_COUNTER_GLOBAL)
            result = (old - 1) & 0xFFFF
            mem.ww(ds, BOSS_GROUP_COUNTER_GLOBAL, result)
            cpu.set_sub_flags(old, 1, old - 1, 16)
            return

    for value, ax in OBJECT_DEACTIVATE_SCRIPT_AX_BY_LOGIC_ID.items():
        cmp_word(cpu, selector, value)
        s.ax = ax
        if selector == value:
            if decision.kind != "script_select" or decision.ax_script != ax:
                raise AssertionError("pure C054 decision disagrees on script selector")
            return

    if decision.kind != "none":
        raise AssertionError("pure C054 decision found an action missed by ASM-compatible dispatcher")

