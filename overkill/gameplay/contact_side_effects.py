"""Contact side-effects for the OVERKILL object runtime.

Architecture layer: **lifted**.  The "fanout -> side effect -> slot mutation"
middle of the contact pipeline, carved out of ``object_runtime.py``: the 62F6
overlap scan, the BEC5 collision handler and its A8C2/BF5F mark tail, and the
9E69/9E98 post-contact status tails.  These are reached only from the postmove
hub (``object_postmove.py``); they route on into the death/deactivation tails
in ``object_deactivation.py``.  Bodies relocated verbatim; conservative names.
"""
from __future__ import annotations

from overkill.asm import _add_reg16, _cmp_byte, _cmp_word, _sub_mem_word, _test_word
from overkill.gameplay.object_deactivation import (
    _run_collision_cleanup_bd0d_observed,
    _run_collision_death_tail_bfc7,
)
from overkill.gameplay.object_runtime_common import _run_interpreted_near_call_observed
from overkill.recovered.views.object_slots import (
    ObjectSlotView,
    GAMEPLAY_OBJECT_LAST_SLOT_BASE, GAMEPLAY_OBJECT_TABLE_BASE, OBJECT_SLOT_STRIDE,
    OFF_ACQUIRED_TARGET_PTR, OFF_COUNTER_20, OFF_DRAW_LAYER, OFF_GATE_OR_LAYER,
    OFF_LOGIC_ID, OFF_OBJECT_TYPE, OFF_SCAN_ENABLE_OR_SOLID, OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE, OFF_VARIANT, OFF_X, OFF_Y,
)



def _run_collision_mark_a8c2_tail_bf5f(cpu) -> None:
    """Run BEC5:BF5F's observed A8C2 linked-object mark tail and return."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mem = cpu.mem

    saved_bp = cpu.s.bp & 0xFFFF
    cpu.push(saved_bp)
    for ptr_off in (0xA8BA, 0xA8BC, 0xA8BE, 0xA8C0):
        cpu.s.bp = mem.rw(ds, ptr_off)
        mem.ww(ss, (cpu.s.bp + 0x24) & 0xFFFF, 0x0005)
    _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
    if mem.rb(ds, 0x98C0) != 0x00:
        mem.wb(ds, 0xBEFF, 0x0E)
    cpu.s.bp = cpu.pop()
    cpu.s.ip = cpu.pop()


def _run_collision_handler_bec5_observed(cpu, *, collided_bx: int, parent: str, chain: str, cx_value: int) -> None:
    """Run the currently verified BEC5 collision branches.

    BEC5 is jumped to from the unrolled 62F6 overlap scan rather than called as
    a separate subroutine.  Its RET returns to 62F6's caller, so every lifted RET
    path consumes the caller's return word exactly like the original ASM.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    bx = collided_bx & 0xFFFF
    mem = cpu.mem

    def run_bfc7(label: str) -> None:
        _run_collision_death_tail_bfc7(
            cpu,
            parent=parent,
            chain=f"{chain} -> BEC5 {label}".rstrip(),
            cx_value=cx_value,
        )

    def call_bd0d(return_ip: int, label: str) -> None:
        # BEC5 reaches BD0D by real CALLs at BF92/BF97.  Preserve their
        # return-address scratch even though the lifted code invokes the helper
        # directly.
        call_sp = cpu.s.sp & 0xFFFF
        cpu.push(return_ip & 0xFFFF)
        _run_collision_cleanup_bd0d_observed(
            cpu,
            parent=parent,
            chain=f"{chain} -> BEC5 {label}",
            cx_value=cx_value,
        )
        cpu.s.sp = call_sp

    def run_bf25_counter_chain(*, enter_at_bf25: bool, label: str) -> None:
        # BF25 is reached only by sprite-0033 variant-2 collisions and by the
        # A8C2-gated variant 5/6 and 7/8/0C continuations.  The usual variant-2
        # sprite path starts at BF2D and therefore skips this first decrement.
        if enter_at_bf25:
            _sub_mem_word(cpu, ss, (bp + OFF_COUNTER_20) & 0xFFFF, 1)
            if slot.counter_20 == 0:
                run_bfc7(f"{label} BF25 counter zero")
                return

        # BF2D
        _sub_mem_word(cpu, ss, (bp + OFF_COUNTER_20) & 0xFFFF, 1)
        if slot.counter_20 == 0:
            run_bfc7(f"{label} BF2D counter zero")
            return

        bedc = mem.rw(ds, 0xBEDC)
        _cmp_word(cpu, bedc, 0x0001)
        if bedc == 0x0001:
            _sub_mem_word(cpu, ss, (bp + OFF_COUNTER_20) & 0xFFFF, 1)
            if slot.counter_20 == 0:
                run_bfc7(f"{label} BEDC=0001 counter zero")
                return
        else:
            _cmp_word(cpu, bedc, 0x0000)
            if bedc == 0x0000:
                for tail in ("BF46", "BF4B", "BF50"):
                    _sub_mem_word(cpu, ss, (bp + OFF_COUNTER_20) & 0xFFFF, 1)
                    if slot.counter_20 == 0:
                        run_bfc7(f"{label} {tail} counter zero")
                        return
            # BEDC values other than 0/1 fall through to BF52 in the original.

        slot.variant = 0x0005
        a8c2 = mem.rw(ds, 0xA8C2)
        _cmp_word(cpu, a8c2, 0x0001)
        if a8c2 == 0x0001:
            _run_collision_mark_a8c2_tail_bf5f(cpu)
            return
        cpu.s.ip = cpu.pop()

    variant = mem.rw(ds, (bx + OFF_LOGIC_ID) & 0xFFFF)

    for target in (0x0007, 0x0008, 0x000C):
        _cmp_word(cpu, variant, target)
        if variant == target:
            # BFB9: A8C2 gates whether the collided slot is cleaned up and then
            # joins BF25, or whether the moving object is forced into BFC7.
            _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
            if mem.rw(ds, 0xA8C2) == 0x0001:
                cpu.s.bx = bx
                call_bd0d(0xBF95, f"variant {variant:04X}")
                run_bf25_counter_chain(enter_at_bf25=True, label=f"variant {variant:04X}")
                return
            slot.counter_20 = 0x0000
            run_bfc7(f"variant {variant:04X}")
            return

    _cmp_word(cpu, variant, 0x0009)
    if variant == 0x0009:
        # BFA8: variant 9 uses the same A8C2 gate but does not call BD0D first.
        _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
        if mem.rw(ds, 0xA8C2) == 0x0001:
            run_bf25_counter_chain(enter_at_bf25=True, label="variant 0009")
            return
        slot.counter_20 = 0x0000
        run_bfc7("variant 0009")
        return

    _cmp_word(cpu, variant, 0x0002)
    if variant == 0x0002:
        cpu.s.bx = bx
        mem.ww(ds, bx, 0)
        sprite = mem.rw(ds, (bx + OFF_SPRITE_OR_STATE) & 0xFFFF)
        _cmp_word(cpu, sprite, 0x0033)
        run_bf25_counter_chain(enter_at_bf25=(sprite == 0x0033), label="variant 0002")
        return

    for target in (0x0006, 0x0005):
        _cmp_word(cpu, variant, target)
        if variant == target:
            # BF97: BD0D/BD17 deactivate the collided object and maintain the
            # family live counters; the following A8C2 test chooses between the
            # BF25 shared counter path and the BFC7 death/transition tail.
            cpu.s.bx = bx
            call_bd0d(0xBF9A, f"variant {variant:04X}")
            _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
            if mem.rw(ds, 0xA8C2) == 0x0001:
                run_bf25_counter_chain(enter_at_bf25=True, label=f"variant {variant:04X}")
                return
            slot.counter_20 = 0x0000
            run_bfc7(f"variant {variant:04X}")
            return

    # Remaining family: BEC5 finally checks whether the collided slot is linked
    # back to the moving object through +30h.  Linked contacts run the observed
    # counter/death transition below; non-linked contacts are a deliberate no-op
    # in the original ASM and just RET with the CMP flags live.
    owner_bp = mem.rw(ds, (bx + OFF_ACQUIRED_TARGET_PTR) & 0xFFFF)
    _cmp_word(cpu, bp, owner_bp)
    if bp == owner_bp:
        mem.ww(ds, (bx + OFF_SUBSTATE) & 0xFFFF, 0x0000)
        _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
        if mem.rw(ds, 0xA8C2) == 0x0001:
            run_bf25_counter_chain(enter_at_bf25=True, label=f"owner-linked variant {variant:04X}")
            return
        slot.counter_20 = 0x0000
        run_bfc7(f"owner-linked variant {variant:04X}")
        return

    cpu.s.ip = cpu.pop()


def _run_post_contact_9e69_observed(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the observed 1010:9E69 post-contact bookkeeping path."""
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    _cmp_word(cpu, mem.rw(ds, 0xA47C), 0x0001)
    if mem.rw(ds, 0xA47C) == 0x0001:
        return
    _cmp_word(cpu, mem.rw(ds, 0x2384), 0x0003)
    if mem.rw(ds, 0x2384) >= 0x0003:
        return
    _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
    if mem.rb(ds, 0x98C0) != 0:
        mem.wb(ds, 0xBEFF, 0x03)
    _cmp_word(cpu, mem.rw(ds, 0xBEDC), 0x0000)
    if mem.rw(ds, 0xBEDC) != 0:
        # JNE 9E98: skip the A362 every-other-call toggle and run the same tail
        # immediately while BEDC is active.
        _run_post_contact_9e98_tail_observed(cpu)
        return
    old = mem.rb(ds, 0xA362)
    new = (old + 1) & 0xFF
    mem.wb(ds, 0xA362, new)
    cpu.set_add_flags(old, 1, old + 1, 8)
    new &= 0x01
    mem.wb(ds, 0xA362, new)
    cpu.set_logic_flags(new, 8)
    if new == 0:
        _run_post_contact_9e98_tail_observed(cpu)


def _run_post_contact_9e98_tail_observed(cpu) -> None:
    """Run the observed 1010:9E98 tail of post-contact bookkeeping.

    9E69 toggles DS:A362 and returns immediately on odd toggles.  On even
    toggles it falls into 9E98, which advances global counters and redraws the
    associated status/formation strip through 61DC.  The gameplay-relevant
    branches are lifted here; the rare display helper 61DC is still executed by
    bounded original interpretation so the visible frame and scratch registers
    stay faithful until that helper is lifted separately.
    """
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    resume_ip = cpu.s.ip & 0xFFFF
    mem = cpu.mem

    old_counter = mem.rw(ds, 0xA95A)
    new_counter = (old_counter - 1) & 0xFFFF
    mem.ww(ds, 0xA95A, new_counter)
    cpu.set_sub_flags(old_counter, 1, old_counter - 1, 16)
    _cmp_word(cpu, new_counter, 0xFFFF)
    if new_counter == 0xFFFF:
        mem.ww(ds, 0xA95C, 0x0000)
        _cmp_byte(cpu, mem.rb(ds, 0x9791), 0x01)
        if mem.rb(ds, 0x9791) == 0x01:
            mem.ww(ds, 0xA95A, 0x0003)
            mem.ww(ds, 0xA95C, 0x0018)
            return
        mem.ww(ds, 0x2384, 0x0003)
        _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
        if mem.rb(ds, 0x98C0) != 0:
            mem.wb(ds, 0xBEFF, 0x19)

    _run_interpreted_near_call_observed(cpu, 0x61DC, 0x9EC5)
    _cmp_word(cpu, mem.rw(cs, 0x95BC), 0x0001)
    if mem.rw(cs, 0x95BC) == 0x0001:
        _run_interpreted_near_call_observed(cpu, 0x511F, 0x9ED0)
        _run_interpreted_near_call_observed(cpu, 0x61DC, 0x9ED3)
        _run_interpreted_near_call_observed(cpu, 0x511F, 0x9ED6)
    cpu.s.ip = resume_ip


def _run_object_overlap_scan_62f6(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the no-collision path of the 1010:62F6 object-overlap scan.

    The original is a large unrolled scan over 32CA-era object slots.  This
    compact loop preserves the observed no-collision semantics and fail-fasts if
    a candidate would jump to the unlifted collision handler at BEC5.
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    def finish_empty_scan() -> None:
        # 741C: ADD BX,0038 ; 741F: RET in the unrolled original.
        _add_reg16(cpu, 3, OBJECT_SLOT_STRIDE)  # BX

    _cmp_word(cpu, mem.rw(ss, bp), 0)
    if mem.rw(ss, bp) == 0:
        # 62FA: an inactive object slot ([bp+00]==0) jumps straight to the shared
        # RET at 741F, bypassing the 741C "ADD BX,38h" tail.  So BX and the
        # zero-compare flags from this 62F6 CMP are preserved unchanged -- it is
        # NOT the empty-scan sentinel exit (which does run the 741C add and lands
        # at BX=32CC).  Conflating the two left BX=32CC / ZF=0 instead of the
        # original's incoming BX / ZF=1.
        return

    slot = ObjectSlotView(mem, ss, bp)  # this object's record (SS:BP)
    _cmp_word(cpu, slot.x_word, 0x0020)
    if slot.x < 0x20:
        # The original bails out before the slot scan here, so keep BX and the
        # compare flags from 62FE intact instead of forcing the empty-scan tail.
        return

    for off, bad in ((0x16, 0), (0x18, 0)):
        _cmp_word(cpu, mem.rw(ss, (bp + off) & 0xFFFF), bad)
        if mem.rw(ss, (bp + off) & 0xFFFF) == bad:
            # 6308/6311: zero draw-layer/logic-id does not enter the slot scan.
            # The original falls through/jumps directly to the shared RET at
            # 741F, preserving the incoming BX and the zero-compare flags.  Do
            # not force the empty-scan sentinel tail here.
            return
    _cmp_word(cpu, slot.logic_id, 0x0001)
    if slot.logic_id == 0x0001:
        return
    _cmp_word(cpu, slot.logic_id, 0x0026)
    if slot.logic_id == 0x0026:
        # 6323/6329: logic-id 26h is another pre-scan exemption.  The ASM
        # falls through into ``JMP 741F`` and returns immediately, so BX remains
        # the caller's BX and the zero flags from ``CMP [BP+18],26h`` stay live.
        # Do not run the empty-scan sentinel tail (741C ADD BX,38h).
        return

    cpu.s.si = slot.draw_layer
    cpu.s.di = slot.gate_or_layer
    cpu.s.dx = slot.y_word & 0xFFF8
    cpu.set_logic_flags(cpu.s.dx, 16)
    cpu.s.cx = slot.x_word & 0xFFF8
    cpu.set_logic_flags(cpu.s.cx, 16)

    obj_type = slot.object_type
    logic_id = slot.logic_id
    bx = GAMEPLAY_OBJECT_TABLE_BASE
    while True:
        cpu.s.bx = bx
        _cmp_word(cpu, mem.rw(ds, bx), 0)
        if mem.rw(ds, bx) != 0:
            _cmp_word(cpu, mem.rw(ds, (bx + OFF_SCAN_ENABLE_OR_SOLID) & 0xFFFF), 0)
            if mem.rw(ds, (bx + OFF_SCAN_ENABLE_OR_SOLID) & 0xFFFF) != 0:
                ax = mem.rw(ds, (bx + OFF_Y) & 0xFFFF)
                _test_word(cpu, ax, 0x0007)
                y_candidates = []
                if ax & 0x0007:
                    aligned = (ax & 0xFFF8)
                    y_candidates.append((aligned + 8) & 0xFFFF)
                    y_candidates.append(aligned)
                else:
                    y_candidates.append(ax)
                y_candidates.append((y_candidates[-1] - 8) & 0xFFFF)
                if obj_type == 2:
                    y_candidates.append((y_candidates[-1] - 8) & 0xFFFF)
                    y_candidates.append((y_candidates[-1] - 8) & 0xFFFF)
                if cpu.s.dx in y_candidates:
                    used_x_branch = False
                    ax = mem.rw(ds, (bx + OFF_X) & 0xFFFF) & 0xFFF8
                    x_candidates = [ax, (ax - 8) & 0xFFFF]
                    if obj_type == 2 and logic_id not in (0x78, 0x79):
                        x_candidates.append((x_candidates[-1] - 8) & 0xFFFF)
                        x_candidates.append((x_candidates[-1] - 8) & 0xFFFF)
                    used_x_branch = True
                    if cpu.s.cx in x_candidates:
                        # The original arrives at BEC5 with AX holding the
                        # matched tile X and BX pointing at the collided slot.
                        cpu.s.ax = cpu.s.cx & 0xFFFF
                        _run_collision_handler_bec5_observed(
                            cpu,
                            collided_bx=bx,
                            parent=parent,
                            chain=f"{chain} -> 62F6",
                            cx_value=cx_value,
                        )
                        return
                    # The original leaves AX at the last X candidate once the
                    # X branch has been entered, even on a miss.
                    cpu.s.ax = x_candidates[-1]
                else:
                    # Leave AX at the last tested Y coordinate when the Y
                    # branch misses entirely.
                    cpu.s.ax = y_candidates[-1]
        if bx == GAMEPLAY_OBJECT_LAST_SLOT_BASE:
            cpu.s.bx = bx
            finish_empty_scan()
            return
        old_bx = bx
        bx = (bx + OBJECT_SLOT_STRIDE) & 0xFFFF
        cpu.set_add_flags(old_bx, OBJECT_SLOT_STRIDE, old_bx + OBJECT_SLOT_STRIDE, 16)
