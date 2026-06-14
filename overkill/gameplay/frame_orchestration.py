"""Lifted OVERKILL frame orchestration / glue helpers.

This module is for finite glue that is neither a renderer primitive, nor an
object behaviour, nor an asset codec.  These routines preserve the original
frame-ordering contract by composing lower proof-boundaries in the same order as
ASM.  Timing waits stay in ``sounds``/``input_menu``; concrete object behaviour
stays in ``object_runtime``; this layer owns only the per-frame bookkeeping and
script/list orchestration that binds them together.
"""
from __future__ import annotations

from collections.abc import Callable

from overkill.asm import (
    _add_reg16,
    _and_mem_word,
    _cmp_byte,
    _cmp_word,
    _dec_mem_word_preserve_cf,
    _inc_mem_word_preserve_cf,
    _sub_mem_word,
    _sub_reg16,
)
from dos_re.cpu import ZF


RunOriginalNearCall = Callable[[object, int, int], None]



SIG_MAIN_FRAME_LOOP_D007 = bytes.fromhex(
    "e8 68 36 e8 12 81 e8 36 d8 e8 c9 8b e8 f6 d8 e8 "
    "34 00 e8 24 d9 e8 42 8f e8 1a 37 e8 3b 81 e8 51 "
    "36 83 3e 06 be 13 74 11 e8 30 31 f6 06 be 98 10 "
    "75 07 80 3e c3 98 00 74 c7"
)


def run_main_frame_loop_d007(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift one iteration of the 1010:D007 main gameplay frame loop.

    D007 is the top-level frame orchestrator, not an object or renderer leaf.
    The hook deliberately performs exactly one ASM frame-loop iteration and then
    either returns to D007 for the next frame or stops at D040, the original exit
    tail used when input/script state breaks out of the attract/gameplay loop.

    Child islands remain separate proof boundaries: this function composes their
    existing hooks in the same CALL order as the original code.  The verifier
    metadata for this routine requires the ASM oracle to execute at least one
    step before accepting D007 as a target, otherwise a same-IP loop would verify
    against a zero-step oracle.
    """
    if self_disable_if_patched(
        cpu,
        0xD007,
        SIG_MAIN_FRAME_LOOP_D007,
        "overkill_main_frame_loop_d007",
    ):
        return

    s = cpu.s
    mem = cpu.mem

    def call(ip: int, ret: int) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret & 0xFFFF)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (0x1010, ret & 0xFFFF):
            raise RuntimeError(
                f"D007 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret & 0xFFFF:04X}, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    call(0x0672, 0xD00A)
    call(0x511F, 0xD00D)
    call(0xA846, 0xD010)
    call(0x5BDC, 0xD013)
    call(0xA90C, 0xD016)
    call(0xD04D, 0xD019)
    call(0xA940, 0xD01C)
    call(0x5F61, 0xD01F)
    call(0x073C, 0xD022)
    call(0x5160, 0xD025)
    call(0x0679, 0xD028)

    ds = s.ds & 0xFFFF
    be06 = mem.rw(ds, 0xBE06)
    _cmp_word(cpu, be06, 0x0013)
    if be06 == 0x0013:
        s.ip = 0xD040
        return

    call(0x0162, 0xD032)

    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x10, 8)
    if input_flags & 0x10:
        s.ip = 0xD040
        return

    state98c3 = mem.rb(ds, 0x98C3)
    _cmp_byte(cpu, state98c3, 0x00)
    s.ip = 0xD007 if state98c3 == 0 else 0xD040

SIG_FRAME_STATUS_COUNTER_UPDATE_5F61 = bytes.fromhex(
    "83 3e 7e a4 00 75 21 83 3e 80 a4 00 74 1a ff 0e"
)
SIG_DEMO_OBJECT_LIST_MAINTENANCE_A212 = bytes.fromhex(
    "83 3e 72 a9 00 75 01 c3 83 3e 24 23 01 75 37 81"
)
SIG_FRAME_SERVICE_GATE_073C = bytes.fromhex(
    "80 3e 07 99 01 74 01 c3 e8 18 00 e8 a5 00 83 3e"
)
SIG_FRAME_UI_STATE_UPDATE_D04D = bytes.fromhex(
    "c7 06 78 a2 00 00 b0 1f b4 18 e8 a6 89 8b 1e 06 be"
)


def _run_sound_state_select_cb1c(cpu) -> None:
    """Mirror the tiny 1010:CB1C sound-state selector used by 5F61.

    This is deliberately local to frame orchestration because 5F61 only needs
    this small leaf to preserve byte/flag effects when a status countdown reaches
    zero.  It is not the AdLib path; it writes the same PC-speaker/shared sound
    request bytes as the original leaf.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    al = cpu.get_reg8(0)
    mem.wb(ds, 0x98C2, al)
    v98c1 = mem.rb(ds, 0x98C1)
    _cmp_byte(cpu, v98c1, 0)
    if v98c1 == 0:
        return

    cpu.set_reg8(4, 0)  # XOR AH,AH
    cpu.set_logic_flags(0, 8)
    s.bx = 0x2032
    s.es = s.bx
    es_value = mem.rb(s.es & 0xFFFF, 0x0009)
    _cmp_byte(cpu, al, es_value)
    if al == es_value:
        return
    mem.ww(s.es & 0xFFFF, 0x0008, s.ax)
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)


def _xlat_state_byte(cpu) -> int:
    ds = cpu.s.ds & 0xFFFF
    al = cpu.mem.rb(ds, 0x2356)
    cpu.set_reg8(0, al)
    cpu.s.bx = 0x231E
    value = cpu.mem.rb(ds, (cpu.s.bx + al) & 0xFFFF)
    cpu.set_reg8(0, value)
    return value


def _call_frame_effect_tick_606f(cpu, run_original_near_call: RunOriginalNearCall) -> None:
    """Mirror the 606F helper called by 5F61, including call-frame scratch.

    The only not-yet-lifted tail is 9EE4/77DF, which is an effect/rendering
    island.  When that rare branch is reached we run it as a bounded original
    near call so 5F61 can still be a complete near-return proof boundary while
    the remaining effect island stays explicitly identified.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    ss = cpu.s.ss & 0xFFFF
    sp_at_call = cpu.s.sp & 0xFFFF

    def finish_606f_ret() -> None:
        # 5F61 reaches 606F via CALL 606F, so even when Python inlines the body,
        # the full-memory verifier can see the balanced return word below SP.
        mem.ww(ss, (sp_at_call - 2) & 0xFFFF, 0x606E)

    bedc = mem.rw(ds, 0xBEDC)
    _cmp_word(cpu, bedc, 1)
    if bedc > 1:
        v232e = mem.rw(ds, 0x232E)
        _cmp_word(cpu, v232e, 0x003F)
    else:
        v2330 = mem.rw(ds, 0x2330)
        _cmp_word(cpu, v2330, 0x007F)

    if cpu.get_flag(ZF):
        # 6084 CALL 9EE4; continue at 6087, then run the rest of 606F.
        cpu.push(0x606E)
        run_original_near_call(cpu, 0x9EE4, 0x6087)
        # We are now logically at 6087 with the 606E frame still on the stack.
        if (cpu.s.sp & 0xFFFF) != ((sp_at_call - 2) & 0xFFFF):
            raise RuntimeError(
                f"9EE4 did not preserve 606F stack frame; SP={cpu.s.sp:04X} expected {(sp_at_call - 2) & 0xFFFF:04X}"
            )
        # Simulate the eventual RET from 606F back to 606E, but keep the scratch.
        ret = cpu.pop()
        if ret != 0x606E:
            raise RuntimeError(f"606F expected return word 606E after 9EE4, got {ret:04X}")

    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, 2)
    if v2384 != 2:
        finish_606f_ret()
        return

    v232c = mem.rw(ds, 0x232C)
    _cmp_word(cpu, v232c, 0x001F)
    if v232c != 0x001F:
        finish_606f_ret()
        return

    old = mem.rw(ds, 0x234A)
    result = old ^ 0x0001
    mem.ww(ds, 0x234A, result)
    cpu.set_logic_flags(result, 16)
    if result != 0:
        finish_606f_ret()
        return

    # 609F JMP 9EE4.  Because 606F was itself called, 9EE4's RET lands at 606E.
    run_original_near_call(cpu, 0x9EE4, 0x606E)


def run_frame_status_counter_update_5f61(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift the finite 1010:5F61 per-frame status/counter update.

    This is frame orchestration glue: it advances global animation/status
    counters, requests an occasional sound-state change through CB1C, and calls
    the separate 606F effect tick.  It does not own the effect renderer itself;
    9EE4/77DF remains a named bounded effect island until lifted separately.
    """
    if self_disable_if_patched(
        cpu,
        0x5F61,
        SIG_FRAME_STATUS_COUNTER_UPDATE_5F61,
        "overkill_frame_status_counter_update_5f61",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    v_a47e = mem.rw(ds, 0xA47E)
    _cmp_word(cpu, v_a47e, 0)
    if v_a47e == 0:
        v_a480 = mem.rw(ds, 0xA480)
        _cmp_word(cpu, v_a480, 0)
        if v_a480 != 0:
            dec = _dec_mem_word_preserve_cf(cpu, ds, 0xA480)
            if dec == 0:
                al = _xlat_state_byte(cpu)
                v2350 = mem.rw(ds, 0x2350)
                _cmp_word(cpu, v2350, 0x0750)
                if v2350 >= 0x0750:
                    al = 0x06
                    cpu.set_reg8(0, al)
                _run_sound_state_select_cb1c(cpu)
                # CB1C may restore DS from the game's data-segment cell.
                ds = s.ds & 0xFFFF

    v2328 = mem.rw(ds, 0x2328)
    _cmp_word(cpu, v2328, 7)
    if v2328 == 7:
        v2342 = mem.rw(ds, 0x2342)
        _cmp_word(cpu, v2342, 0xFFFF)
        if v2342 != 0xFFFF:
            inc = _inc_mem_word_preserve_cf(cpu, ds, 0x2344)
            _cmp_word(cpu, inc, 2)
            if inc == 2:
                old = mem.rw(ds, 0x2342)
                mem.ww(ds, 0x2342, (-old) & 0xFFFF)
                cpu.set_sub_flags(0, old, -old, 16)
                _inc_mem_word_preserve_cf(cpu, ds, 0x2348)
        else:
            dec = _dec_mem_word_preserve_cf(cpu, ds, 0x2344)
            if dec == 0:
                old = mem.rw(ds, 0x2342)
                mem.ww(ds, 0x2342, (-old) & 0xFFFF)
                cpu.set_sub_flags(0, old, -old, 16)
                _inc_mem_word_preserve_cf(cpu, ds, 0x2348)

    _and_mem_word(cpu, ds, 0x2348, 0x000F)
    if mem.rw(ds, 0x2348) == 0:
        mem.ww(ds, 0x2346, 0x0008)
        _inc_mem_word_preserve_cf(cpu, ds, 0x2348)

    _inc_mem_word_preserve_cf(cpu, ds, 0x2332)
    _and_mem_word(cpu, ds, 0x2332, 0x0003)
    if mem.rw(ds, 0x2332) == 0:
        _inc_mem_word_preserve_cf(cpu, ds, 0x2334)
        v2334 = mem.rw(ds, 0x2334)
        _cmp_word(cpu, v2334, 0x000A)
        if v2334 >= 0x000A:
            mem.ww(ds, 0x2334, 0)

        _inc_mem_word_preserve_cf(cpu, ds, 0x2338)
        v2338 = mem.rw(ds, 0x2338)
        _cmp_word(cpu, v2338, 0x0006)
        if v2338 >= 0x0006:
            mem.ww(ds, 0x2338, 0)

        _inc_mem_word_preserve_cf(cpu, ds, 0x233A)
        v233a = mem.rw(ds, 0x233A)
        _cmp_word(cpu, v233a, 0x0005)
        if v233a >= 0x0005:
            mem.ww(ds, 0x233A, 0)

        _inc_mem_word_preserve_cf(cpu, ds, 0x233E)
        v233e = mem.rw(ds, 0x233E)
        _cmp_word(cpu, v233e, 0x0003)
        if v233e >= 0x0003:
            mem.ww(ds, 0x233E, 0)

        _inc_mem_word_preserve_cf(cpu, ds, 0x233C)
        _and_mem_word(cpu, ds, 0x233C, 0x0003)
        _inc_mem_word_preserve_cf(cpu, ds, 0x2336)
        _and_mem_word(cpu, ds, 0x2336, 0x0007)
        _inc_mem_word_preserve_cf(cpu, ds, 0xA7A0)

    old2324 = mem.rw(ds, 0x2324)
    result2324 = old2324 ^ 0x0001
    mem.ww(ds, 0x2324, result2324)
    cpu.set_logic_flags(result2324, 16)

    _inc_mem_word_preserve_cf(cpu, ds, 0x2326)
    _and_mem_word(cpu, ds, 0x2326, 0x0003)
    _inc_mem_word_preserve_cf(cpu, ds, 0x2328)
    _and_mem_word(cpu, ds, 0x2328, 0x0007)
    _inc_mem_word_preserve_cf(cpu, ds, 0x232A)
    _and_mem_word(cpu, ds, 0x232A, 0x000F)
    _inc_mem_word_preserve_cf(cpu, ds, 0x232C)
    _and_mem_word(cpu, ds, 0x232C, 0x001F)
    _inc_mem_word_preserve_cf(cpu, ds, 0x232E)
    _and_mem_word(cpu, ds, 0x232E, 0x003F)
    _inc_mem_word_preserve_cf(cpu, ds, 0x2330)
    _and_mem_word(cpu, ds, 0x2330, 0x007F)

    _call_frame_effect_tick_606f(cpu, run_original_near_call)
    s.ip = cpu.pop()



def run_frame_service_gate_073c(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:073C, the tiny per-frame service/platform gate.

    In the normal cold-start/attract frame path DS:9907 is not 1, so this
    routine is a three-instruction gate returning immediately to D022 while
    preserving the CMP flags.  The rare enabled path is explicit platform/UI
    glue, not gameplay logic; keep it bounded-original for now so the hook can
    safely own the hot gate without pretending to understand the longer service
    tail.
    """
    if self_disable_if_patched(
        cpu,
        0x073C,
        SIG_FRAME_SERVICE_GATE_073C,
        "overkill_frame_service_gate_073c",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    v9907 = mem.rb(ds, 0x9907)
    _cmp_byte(cpu, v9907, 0x01)
    if v9907 != 0x01:
        s.ip = cpu.pop()
        return

    # 0744+ is a longer platform/UI service path reached only when the gate is
    # armed.  It contains several separate calls and a BDAC guard; keep it as a
    # bounded original continuation until a real trace exercises it enough to
    # split into smaller named children.
    s.ip = 0x0744
    run_original_near_call(cpu, 0x0744, cpu.pop())



def run_frame_ui_state_update_d04d(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:D04D, the finite per-frame UI/demo-state update block.

    This is frame orchestration, not gameplay object logic.  It draws the small
    status/menu cell selected by the current BE06 script state, runs the A212
    demo-object list maintenance helper, advances the BE08/BE0A timers, and
    either returns to the main frame loop or hands off to the original jump-table
    script continuation when a state transition is due.
    """
    if self_disable_if_patched(
        cpu,
        0xD04D,
        SIG_FRAME_UI_STATE_UPDATE_D04D,
        "overkill_frame_ui_state_update_d04d",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds0 = s.ds & 0xFFFF

    mem.ww(ds0, 0xA278, 0x0000)
    cpu.set_reg8(0, 0x1F)
    cpu.set_reg8(4, 0x18)
    run_original_near_call(cpu, 0x5A00, 0xD05A)
    if s.ip != 0xD05A:
        raise RuntimeError(f"D04D expected 5A00 return D05A, got {s.ip:04X}")

    s.bx = mem.rw(ds0, 0xBE06)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ax = s.bx
    s.bx = cpu.shift(4, s.bx, 1, 16)
    _add_reg16(cpu, 3, s.ax)
    s.si = mem.rw(ds0, (s.bx - 0x41E8) & 0xFFFF)
    s.si = cpu.shift(4, s.si, 1, 16)
    _add_reg16(cpu, 6, 0x0BE4)
    s.si = mem.rw(cs, s.si & 0xFFFF)

    saved_ds = s.ds & 0xFFFF
    cpu.push(saved_ds)
    s.ds = mem.rw(cs, 0x95B4)
    run_original_near_call(cpu, 0x5A6C, 0xD07C)
    if s.ip != 0xD07C:
        raise RuntimeError(f"D04D expected 5A6C return D07C, got {s.ip:04X}")
    s.ds = cpu.pop()
    ds = s.ds & 0xFFFF

    run_original_near_call(cpu, 0xA212, 0xD080)
    if s.ip != 0xD080:
        raise RuntimeError(f"D04D expected A212 return D080, got {s.ip:04X}")

    v_be06 = mem.rw(ds, 0xBE06)
    _cmp_word(cpu, v_be06, 0x0008)
    if v_be06 >= 0x0008:
        v_be08 = mem.rw(ds, 0xBE08)
        _cmp_word(cpu, v_be08, 0x0014)
        if v_be08 >= 0x0014:
            mem.wb(ds, 0x98BE, 0x00)
            _inc_mem_word_preserve_cf(cpu, ds, 0xBE0A)
            v_be0a = mem.rw(ds, 0xBE0A)
            _cmp_word(cpu, v_be0a, 0x0014)
            if v_be0a >= 0x0014:
                mem.ww(ds, 0xBE0A, 0x0000)
            v_be0a = mem.rw(ds, 0xBE0A)
            _cmp_word(cpu, v_be0a, 0x000F)
            if v_be0a == 0x000F:
                mem.wb(ds, 0x98BE, 0x10)
            else:
                _cmp_word(cpu, v_be0a, 0x0011)
                if v_be0a == 0x0011:
                    mem.wb(ds, 0x98BE, 0x10)
                else:
                    _cmp_word(cpu, v_be0a, 0x0013)
                    if v_be0a == 0x0013:
                        mem.wb(ds, 0x98BE, 0x10)
            s.bp = 0x237C
            mem.ww(ds, 0xA980, 0x0000)
            run_original_near_call(cpu, 0xA067, 0xD0CA)
            if s.ip != 0xD0CA:
                raise RuntimeError(f"D04D expected A067 return D0CA, got {s.ip:04X}")

    v_be06 = mem.rw(ds, 0xBE06)
    _cmp_word(cpu, v_be06, 0x0000)
    if v_be06 == 0:
        s.ip = 0xD160
        return

    dec = _dec_mem_word_preserve_cf(cpu, ds, 0xBE08)
    if dec != 0:
        s.ip = cpu.pop()
        return

    mem.ww(ds, 0xBE08, 0x0064)
    _inc_mem_word_preserve_cf(cpu, ds, 0xBE06)
    s.bx = mem.rw(ds, 0xBE06)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ax = s.bx
    s.bx = cpu.shift(4, s.bx, 1, 16)
    _add_reg16(cpu, 3, s.ax)
    s.ax = mem.rw(ds, (s.bx - 0x41E6) & 0xFFFF)
    _cmp_word(cpu, s.ax, 0xFFFF)
    if s.ax != 0xFFFF:
        mem.ww(ds, 0x95FA, s.ax)
        s.ax = mem.rw(ds, (s.bx - 0x41E4) & 0xFFFF)
        mem.ww(ds, 0xBE16, s.ax)
        run_original_near_call(cpu, 0x859E, 0xD107)
        if s.ip != 0xD107:
            raise RuntimeError(f"D04D expected 859E return D107, got {s.ip:04X}")

    s.bx = mem.rw(ds, 0xBE06)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ip = mem.rw(cs, (s.bx - 0x2EEE) & 0xFFFF)

def run_demo_object_list_maintenance_a212(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A212, the scripted demo object-list maintenance helper.

    The common cold-start/attract path returns immediately while DS:A972 is
    zero.  The non-zero path maintains a small pointer list at A3B4 and uses
    A2D6 as a separate object-spawn helper; that spawn helper remains bounded
    original until its allocator island is lifted.
    """
    if self_disable_if_patched(
        cpu,
        0xA212,
        SIG_DEMO_OBJECT_LIST_MAINTENANCE_A212,
        "overkill_demo_object_list_maintenance_a212",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    v_a972 = mem.rw(ds, 0xA972)
    _cmp_word(cpu, v_a972, 0)
    if v_a972 == 0:
        s.ip = cpu.pop()
        return

    v2324 = mem.rw(ds, 0x2324)
    _cmp_word(cpu, v2324, 1)
    if v2324 == 1:
        v_a3ea = mem.rw(ds, 0xA3EA)
        _cmp_word(cpu, v_a3ea, 0xA3E8)
        if v_a3ea == 0xA3E8:
            s.ip = cpu.pop()
            return

        s.bx = mem.rw(ds, 0xA3B4)
        _cmp_word(cpu, s.bx, 0xFFFF)
        if s.bx == 0xFFFF:
            s.ip = cpu.pop()
            return

        first_y = mem.rw(ds, (s.bx + 0x04) & 0xFFFF)
        _cmp_word(cpu, first_y, 0)
        if first_y != 0:
            run_original_near_call(cpu, 0xA2D6, 0xA23D)
            s.bx = mem.rw(ds, 0xA3B4)
            _sub_mem_word(cpu, ds, (s.bx + 0x04) & 0xFFFF, 8)
            s.bx = mem.rw(ds, 0xA3EA)
            _sub_reg16(cpu, 3, 4)
            # SUB BX,4 flags are overwritten by the following CMP in observed code.
            s.bx = mem.rw(ds, s.bx)
            tail_y = mem.rw(ds, (s.bx + 0x04) & 0xFFFF)
            _cmp_word(cpu, tail_y, 0x00C8)
            if tail_y != 0x00C8:
                run_original_near_call(cpu, 0xA2D6, 0xA258)
        else:
            run_original_near_call(cpu, 0xA2D6, 0xA258)

    s.si = 0xA3B4
    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + 2) & 0xFFFF
    _cmp_word(cpu, s.ax, 0xFFFF)
    if s.ax == 0xFFFF:
        s.ip = cpu.pop()
        return

    s.bx = s.ax
    _sub_mem_word(cpu, ds, (s.bx + 0x02) & 0xFFFF, 4)
    s.cx = mem.rw(ds, (s.bx + 0x04) & 0xFFFF)
    _add_reg16(cpu, 1, 8)
    s.di = mem.rw(ds, (s.bx + 0x02) & 0xFFFF)

    while True:
        s.ax = mem.rw(ds, s.si)
        s.si = (s.si + 2) & 0xFFFF
        _cmp_word(cpu, s.ax, 0xFFFF)
        if s.ax == 0xFFFF:
            break
        s.bx = s.ax
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.cx)
        _add_reg16(cpu, 1, 8)
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.di)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x006B)

    _sub_reg16(cpu, 6, 4)
    s.bx = mem.rw(ds, s.si)
    mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x006C)
    s.ip = cpu.pop()
