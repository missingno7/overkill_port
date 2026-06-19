"""Object deactivation / death / post-contact side-effect tails.

Architecture layer: **lifted**.  Carved out of ``object_runtime.py``: the tails
that run when an object slot is removed or scores — out-of-bounds deactivation
(``BD17``), the collision/death tail (``BFC7`` -> the ``C054`` deactivate
selector), cleanup (``BD0D``), the packed-decimal score add (``5F0D``), and the
post-move Y clamp (``BCB1``).  This is the "slot mutation -> postmove/death
tail" end of the contact pipeline.  It depends on the spawn/common/collision
modules but on nothing that stays in object_runtime, so the cut is one-way.
Conservative names only; bodies relocated verbatim.
"""
from __future__ import annotations

from overkill.asm import _add_reg16, _cmp_byte, _cmp_word, _dec_mem_word_preserve_cf, _sub_mem_word
from overkill.gameplay.collision import run_object_deactivate_logic_dispatch_c054
from overkill.gameplay.object_runtime_common import (
    _raise_unverified_path,
    _run_original_tail_to_caller,
)
from overkill.gameplay.object_spawns import (
    _run_c054_c12d_effect_spawn_tail,
    _run_linked_effect_spawn_7420_observed,
)
from overkill.recovered.adapters.collision_adapter import run_postmove_y_clamp_bcb1_body
from overkill.recovered.views.object_slots import (
    OFF_ACTIVE_WORD,
    OFF_DRAW_LAYER,
    OFF_LINKED_COUNTER_INDEX,
    OFF_LOGIC_ID,
    OFF_OBJECT_TYPE,
    OFF_PREVIOUS_LOGIC_ID,
    OFF_SPRITE_OR_STATE,
    OFF_TRANSITION_LATCH,
    OFF_X,
    OFF_Y,
)



def _run_deactivate_bd17_observed(cpu, *, parent: str, chain: str, cx_value: int, pop_return: bool = True) -> None:
    """Run observed 1010:BD17 object deactivation tail.

    BD17 is reached from BC4B when an object leaves the allowed X bounds.  The
    currently observed gameplay case is the B73E formation/attack object with
    draw layer 4.  One observed selector result takes the longer BD5F tail that
    publishes DS:A482, seeds the 7420 linked-effect spawn helper, and then
    unwinds back to BC4B.  Other draw-layer/logic-id combinations still fall
    through to the smaller cleanup branches that were already modeled.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    mem.ww(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF, 0x0000)

    draw_layer = mem.rw(ss, (bp + OFF_DRAW_LAYER) & 0xFFFF)
    _cmp_word(cpu, draw_layer, 0x0004)
    if draw_layer == 0x0004:
        logic_id = mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
        # BD5C is a real CALL C054.  Even after the call returns, the BD5F
        # return word remains in freed stack space and is visible to full-stack
        # verifier comparisons.  Keep the frame live while modelling the C054
        # selector tail so nested CALL scratch lands at the original offsets.
        c054_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xBD5F)
        run_object_deactivate_logic_dispatch_c054(cpu)
        selector_ax = cpu.s.ax & 0xFFFF
        # C054 has two families that can leave the selector chain with one of
        # these AX table values.  The 76h..79h family jumps to the live-counter
        # cleanup tail, but the 7Eh/7Dh/1Fh/1Ch/15h/13h family falls through to
        # C12D and runs the linked-effect spawn helper before returning to BD5F.
        # Keying only on AX missed the observed logic_id=13h case because A4E4h
        # was not in the earlier whitelist; keying on the actual logic id keeps
        # the overlap with 76h/77h unambiguous as well.
        if logic_id in (0x007E, 0x007D, 0x001F, 0x001C, 0x0015, 0x0013):
            _run_c054_c12d_effect_spawn_tail(cpu, object_bp=bp, selector_ax=selector_ax)

        # Simulate C054's RET back to BD5F.  The return word remains below SP.
        cpu.s.sp = c054_sp

        _cmp_word(cpu, logic_id, 0x0001)
        if logic_id == 0x0001:
            return
        slot = mem.rw(ss, (bp + OFF_LINKED_COUNTER_INDEX) & 0xFFFF)
        _cmp_word(cpu, slot, 0xFFFF)
        if slot == 0xFFFF:
            return
        cpu.s.si = slot
        cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)  # SHL SI,1
        _add_reg16(cpu, 6, 0x2078)                # ADD SI,2078h
        mem.wb(ds, cpu.s.si & 0xFFFF, 0x00)
        return

    _cmp_word(cpu, draw_layer, 0x0001)
    if draw_layer == 0x0001:
        mem.ww(ss, (bp + OFF_DRAW_LAYER) & 0xFFFF, 0x0002)
        return

    logic_id = mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
    for target, counter in (
        (0x0007, 0xA970),
        (0x0008, 0xA970),
        (0x0009, 0xA972),
        (0x0006, 0xA976),
        (0x0005, 0xA976),
        (0x000C, 0xA974),
    ):
        _cmp_word(cpu, logic_id, target)
        if logic_id == target:
            if target == 0x0009:
                # logic_id 9 is NOT a single-counter decrement like its siblings:
                # BD17 jumps to BD7A, which clears the WHOLE projectile list.  It
                # walks the FFFF-terminated DS:A3B4 pointer list, deactivates each
                # listed object (DS:[slot]=0), and drains DS:A972 to zero.  This
                # is the ringlas (last weapon) controller leaving bounds: the
                # original removes its entire projectile column at once, where the
                # earlier single-decrement model left them active forever (their
                # stale slots then corrupted state and crashed in heavy L5 play).
                a972 = mem.rw(ds, 0xA972)
                _cmp_word(cpu, a972, 0x0000)  # BD7A: CMP DS:[A972],0
                if a972 != 0:                 # BD7F: JNZ BD82
                    cpu.s.cx = 0x001A         # BD82: MOV CX,1Ah
                    cpu.s.si = 0xA3B4         # BD85: MOV SI,A3B4h
                    for _ in range(0x100):    # FFFF-terminated; bounded for safety
                        ax = mem.rw(ds, cpu.s.si & 0xFFFF)  # BD88: LODSW
                        cpu.s.si = (cpu.s.si + 2) & 0xFFFF
                        cpu.s.ax = ax
                        _cmp_word(cpu, ax, 0xFFFF)          # BD89
                        if ax == 0xFFFF:                    # BD8C/BD8E: end of list
                            break
                        mem.ww(ds, (cpu.s.si - 2) & 0xFFFF, ax)  # BD8F: MOV [SI-2],AX
                        cpu.s.bx = ax                       # BD92
                        mem.ww(ds, ax & 0xFFFF, 0x0000)     # BD94: MOV [BX],0
                        _dec_mem_word_preserve_cf(cpu, ds, 0xA972)  # BD98: DEC [A972]
                return
            if mem.rw(ds, counter) != 0:
                _sub_mem_word(cpu, ds, counter, 0x0001)
            return

    # Logic id 000Ah is not the same small counter-only tail as 0009h.
    # Original BD17 branches to BD9E: it optionally decrements DS:A97E and
    # then jumps into the AC19 transition/status helper chain.  That chain is
    # rare, but it has visible register, ES and below-SP scratch side effects;
    # modelling it as a simple DS:A972 decrement caused AD60 hook divergence
    # once the attract/demo object left bounds.
    _cmp_word(cpu, logic_id, 0x000A)
    if logic_id == 0x000A:
        _run_original_tail_to_caller(cpu, 0xBD9E, max_steps=20000)
        if not pop_return:
            # AD60 reaches BD17 by a direct JMP and its lifted caller still owns
            # the final caller RET pop.  The bounded original BD9E/AC19 tail has
            # already executed that RET to reproduce register and below-SP side
            # effects, so push the same continuation back for the AD60 wrapper.
            cpu.push(cpu.s.ip & 0xFFFF)
        return

    # BD17 is usually called as a standalone helper in tests/older lifted paths,
    # but BC4B reaches it by a direct branch and its wrapper owns the final RET
    # pop.  Preserve both boundary shapes explicitly.
    if pop_return:
        cpu.s.ip = cpu.pop()
    return


def _run_collision_death_tail_bfc7(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the observed BFC7 object death/transition tail for type-1 objects."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    logic_id = mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
    _cmp_word(cpu, logic_id, 0x0021)
    if logic_id == 0x0021:
        _cmp_word(cpu, mem.rw(ds, 0x2356), 0x0004)
        if mem.rw(ds, 0x2356) != 0x0004:
            cpu.s.ip = cpu.pop()
            return
        # BFCF: CMP DS:[2356],0004 / BFD4: JE BFD7.  When the
        # global gate is exactly 4, logic 0021 does *not* branch to a
        # special body; it merely joins the ordinary BFD7 death/transition
        # path below.

    obj_type = mem.rw(ss, (bp + OFF_OBJECT_TYPE) & 0xFFFF)
    _cmp_word(cpu, obj_type, 0x0001)
    score_amount = 0x0030 if obj_type == 0x0001 else 0x0060
    # BFC7 materializes the score value in BX (MOV BX,0030h/0060h) before
    # calling the score-add helper.  Later nested selector/effect helpers may
    # push BX as freed stack scratch, so full-memory verification observes this
    # even though the live gameplay transition overwrites BX before returning.
    cpu.s.bx = score_amount
    if obj_type not in (0x0001, 0x0002):
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> BFC7 type {obj_type:04X}",
            target_ip=0xBFE1, bp=bp, cx_value=cx_value,
        )

    score_ax = cpu.s.ax
    score_dx = cpu.s.dx
    score_bp = cpu.s.bp
    _run_score_add_5f0d_observed(cpu, score_amount)
    stack_base = cpu.s.sp & 0xFFFF
    mem.ww(ss, (stack_base - 8) & 0xFFFF, score_dx)
    mem.ww(ss, (stack_base - 6) & 0xFFFF, score_ax)
    mem.ww(ss, (stack_base - 4) & 0xFFFF, score_bp)
    _run_y_clamp_bcb1(cpu)

    saved_bp = bp
    cpu.push(saved_bp)
    linked_slot = mem.rw(ss, (bp + OFF_LINKED_COUNTER_INDEX) & 0xFFFF)
    _cmp_word(cpu, linked_slot, 0xFFFF)
    if linked_slot != 0xFFFF:
        cpu.s.si = linked_slot
        cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)
        _add_reg16(cpu, 6, 0x2078)
        linked_counter = mem.rb(ds, cpu.s.si & 0xFFFF)
        _cmp_byte(cpu, linked_counter, 0)
        if linked_counter != 0:
            old_counter = linked_counter
            new_counter = (old_counter - 1) & 0xFF
            mem.wb(ds, cpu.s.si & 0xFFFF, new_counter)
            cpu.set_sub_flags(old_counter, 1, old_counter - 1, 8)
            if new_counter == 0:
                mem.ww(ds, 0x2376, mem.rw(ss, (bp + OFF_Y) & 0xFFFF))
                mem.ww(ds, 0x2378, mem.rw(ss, (bp + OFF_X) & 0xFFFF))
                cpu.s.ax = mem.rb(ds, (cpu.s.si + 1) & 0xFFFF)
                cpu.set_logic_flags(cpu.s.ax, 16)
                mem.ww(ds, 0x237A, cpu.s.ax)
                _run_linked_effect_spawn_7420_observed(cpu)
    cpu.s.bp = cpu.pop()

    # BFC7 always CALLs the shared C054 selector before the state transition.
    # Earlier revisions whitelisted only a few observed logic ids here, but the
    # real helper is just the same compare chain used by BD17: some ids decrement
    # DS:A47E, while all other ids fall through to the default AX selector.
    # The following C01B compare overwrites C054's flags and C027 overwrites AX
    # with the original logic id, so the important observable effects are the
    # optional counter drop and call-frame scratch.
    c054_sp = cpu.s.sp & 0xFFFF
    cpu.push(0xC01B)
    run_object_deactivate_logic_dispatch_c054(cpu)
    selector_ax = cpu.s.ax & 0xFFFF
    # C054 has two selector families.  The 76h..79h family only selects AX;
    # the 7Eh/7Dh/1Fh/1Ch/15h/13h family falls through to C12D, publishes the
    # selected effect script in DS:A482, spawns a compact linked effect through
    # 7420, and decrements the live-effect counter before returning to C01B.
    # BFC7 reaches the same C054 helper as BD17, so keep the real C01B call
    # frame live while modelling the nested PUSH/CALL scratch.
    if logic_id in (0x007E, 0x007D, 0x001F, 0x001C, 0x0015, 0x0013):
        _run_c054_c12d_effect_spawn_tail(cpu, object_bp=bp, selector_ax=selector_ax)
    cpu.s.sp = c054_sp
    _cmp_word(cpu, mem.rb(ds, 0x98C0), 0)
    if mem.rb(ds, 0x98C0) != 0:
        mem.wb(ds, 0xBEFF, 0x19)

    cpu.s.ax = logic_id
    mem.ww(ss, (bp + OFF_PREVIOUS_LOGIC_ID) & 0xFFFF, cpu.s.ax)
    mem.ww(ss, (bp + OFF_LOGIC_ID) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + OFF_TRANSITION_LATCH) & 0xFFFF, 0x0000)
    # C037 dispatches through a tiny table keyed by the object type at +14h.
    # Earlier lifts hard-coded the type-1 C048 tail (BX=0002, +08=0000), but
    # multi-part/final-boss objects use type 2 and the original takes C04E
    # instead (BX=0004, +08=0003).  Keep this as a source-like type dispatch
    # rather than a per-snapshot special case.
    obj_type = mem.rw(ss, (bp + OFF_OBJECT_TYPE) & 0xFFFF)
    cpu.s.bx = obj_type & 0xFFFF
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
    if obj_type == 0x0001:
        mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, 0x0000)
    elif obj_type == 0x0002:
        mem.ww(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF, 0x0003)
    else:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain=f"{chain} -> BFC7 C037 type dispatch {obj_type:04X}",
            target_ip=cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xC042 + cpu.s.bx) & 0xFFFF),
            bp=bp,
            cx_value=cx_value,
        )
    cpu.s.ip = cpu.pop()


def _run_collision_cleanup_bd0d_observed(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the small BEC5 cleanup call at BD0D for the collided object in BX.

    BD0D is a wrapper around BD17: PUSH BP; BP=BX; CALL BD17; BX=BP;
    POP BP; RET.  Keep the nested return-address scratch visible while leaving
    the caller's live frame balanced.
    """
    saved_bp = cpu.s.bp & 0xFFFF
    cpu.push(saved_bp)
    bd17_return_sp = cpu.s.sp & 0xFFFF
    cpu.push(0xBD13)
    cpu.s.bp = cpu.s.bx & 0xFFFF
    _run_deactivate_bd17_observed(
        cpu,
        parent=parent,
        chain=f"{chain} -> BD0D",
        cx_value=cx_value,
        pop_return=False,
    )
    # Simulate BD17's RET to BD13; the return word remains below SP as in ASM.
    cpu.s.sp = bd17_return_sp
    cpu.s.bx = cpu.s.bp & 0xFFFF
    cpu.s.bp = cpu.pop()


def _run_score_add_5f0d_observed(cpu, amount: int) -> None:
    """Observed score add helper reached from BFC7.

    The original is a packed decimal add starting at 1010:5F0D.  The death-tail
    paths seen so far add 0030h or 0060h into DS:2314..2318 and preserve AX, DX,
    and BP.  Later code in the tail overwrites flags, so this helper only needs
    the memory effect for the verified branch.
    """
    ss = cpu.s.ss & 0xFFFF
    carry = amount & 0xFFFF
    off = 0x2314
    for _ in range(5):
        value = cpu.mem.rb(ss, off)
        addend = carry & 0xFF
        total = (value & 0x0F) + (addend & 0x0F)
        high = (value >> 4) + (addend >> 4)
        if total > 9:
            total -= 10
            high += 1
        carry = 0
        if high > 9:
            high -= 10
            carry = 1
        cpu.mem.wb(ss, off, ((high << 4) | total) & 0xFF)
        off = (off + 1) & 0xFFFF


def _run_y_clamp_bcb1(cpu) -> None:
    """Run BCB1's shared post-move Y clamp without consuming a return word."""
    run_postmove_y_clamp_bcb1_body(cpu, pop_return=False)
