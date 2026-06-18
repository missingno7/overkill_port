"""Lifted OVERKILL frame/game-state update helpers.

These routines sit above raw object-slot behaviours but below any semantic game
model.  They update per-frame counters, globals, and scan orchestration state;
they must not classify concrete enemies/projectiles yet.
"""
from __future__ import annotations

from overkill.asm import (
    _add_reg16,
    _and_mem_word,
    _cmp_byte,
    _cmp_word,
    _dec_mem_byte_preserve_cf,
    _dec_mem_word_preserve_cf,
    _dec_reg16_preserve_cf,
    _sub_reg16,
    _inc_mem_byte_preserve_cf,
    _inc_mem_word_preserve_cf,
    _rep_stosw_preserve_flags,
    _inc_reg16_preserve_cf,
    loop_count,
)
from dos_re.cpu import CF
from overkill.recovered.systems.frame_timers import step_first_active_timer
from overkill.recovered.systems.status_display import status_cursor_stride
from overkill.recovered.views.object_slots import (
    FRAME_TIMER_COUNT,
    FRAME_TIMER_TABLE_BASE,
    FRAME_TIMER_TABLE_END,
)


SIG_GAMEPLAY_COUNTER_STRIDE_LOOP_1F8F_0960 = bytes.fromhex(
    "ff 04 81 3c c0 00 75 04 c7 04 00 00 83 c6 06 e2 ef c3"
)


def run_gameplay_counter_stride_loop_1f8f_0960(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1F8F:0960 gameplay counter stride loop.

    The routine lives in an overlay segment, but the behavior is per-frame
    gameplay state: it walks ``CX`` words spaced six bytes apart, increments
    each counter, wraps counters that reach ``00C0h`` back to zero, and returns.
    It is intentionally kept with ``game_state`` instead of ``asset_codecs`` so
    overlay segment residence does not imply asset-loader ownership.
    """
    if self_disable_if_patched(
        cpu,
        0x0960,
        SIG_GAMEPLAY_COUNTER_STRIDE_LOOP_1F8F_0960,
        "overkill_gameplay_counter_stride_loop_1f8f_0960",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    count = loop_count(s.cx)
    si = s.si & 0xFFFF

    last_si = si
    for _ in range(count):
        value = (mem.rw(ds, si) + 1) & 0xFFFF
        mem.ww(ds, si, 0 if value == 0x00C0 else value)
        last_si = si
        si = (si + 0x0006) & 0xFFFF

    s.si = si
    s.cx = 0
    cpu.set_add_flags(last_si, 0x0006, last_si + 0x0006, 16)
    s.ip = cpu.pop()


SIG_FRAME_GAME_STATE_UPDATE_A940 = bytes.fromhex(
    "83 3e ce a8 ff 74 04 ff 06 ce a8 a1 c8 a8 a3 c6 "
    "a8 a1 cc a8 a3 ca a8 c7 06 cc a8 00 00 83 3e 56"
)


def run_frame_game_state_update_a940(cpu, self_disable_if_patched) -> None:
    """Lift the finite A940 per-frame game-state prelude up to the A9E0 scan.

    This hook owns only the deterministic counter/global updates before object
    scanning.  It deliberately stops at A9E0 so the existing object-scan and
    object-behavior hooks remain the proof boundary.  The rare F797 path is left
    as original code by returning at A9DA before the call.
    """
    if self_disable_if_patched(
        cpu,
        0xA940,
        SIG_FRAME_GAME_STATE_UPDATE_A940,
        "overkill_frame_game_state_update_a940",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    value = mem.rw(ds, 0xA8CE)
    _cmp_word(cpu, value, 0xFFFF)
    if value != 0xFFFF:
        _inc_mem_word_preserve_cf(cpu, ds, 0xA8CE)

    s.ax = mem.rw(ds, 0xA8C8)
    mem.ww(ds, 0xA8C6, s.ax)
    s.ax = mem.rw(ds, 0xA8CC)
    mem.ww(ds, 0xA8CA, s.ax)
    mem.ww(ds, 0xA8CC, 0)

    state = mem.rw(ds, 0x2356)
    _cmp_word(cpu, state, 5)
    if state == 5:
        flag98a2 = mem.rb(ds, 0x98A2)
        _cmp_byte(cpu, flag98a2, 0)
        if flag98a2 != 0:
            old = mem.rw(ds, 0x98AA)
            mem.ww(ds, 0x98AA, (-old) & 0xFFFF)
            cpu.set_sub_flags(0, old, -old, 16)
            mem.wb(ds, 0x98A2, 0)
            mem.wb(ds, 0x98A4, 1)
        else:
            mem.wb(ds, 0x98A4, 0)

        cpu.set_reg8(1, 0)  # XOR CL,CL
        cpu.set_logic_flags(0, 8)

        flag98a5 = mem.rb(ds, 0x98A5)
        _cmp_byte(cpu, flag98a5, 0)
        if flag98a5 != 0:
            dec_value = _dec_mem_byte_preserve_cf(cpu, ds, 0x98A5)
            if dec_value == 0:
                s.ax = mem.rw(ds, 0xA47E)
                cpu.set_reg8(1, 0x0A)
                _cmp_word(cpu, s.ax, 0x0010)
                if s.ax <= 0x0010:
                    cpu.set_reg8(1, 0x06)
                    _cmp_word(cpu, s.ax, 0x0008)
                    if s.ax <= 0x0008:
                        cpu.set_reg8(1, 0x04)
                        _cmp_word(cpu, s.ax, 0x0004)
                        if s.ax <= 0x0004:
                            cpu.set_reg8(1, 0x01)

            mem.wb(ds, 0x98A5, s.cx & 0x00FF)
            _inc_mem_byte_preserve_cf(cpu, ds, 0x98A3)
        else:
            mem.wb(ds, 0x98A5, s.cx & 0x00FF)
            _inc_mem_byte_preserve_cf(cpu, ds, 0x98A3)

        # A9B8 far-call 1F8F:081D, then continuation at A9BD.
        caller_cs = s.cs & 0xFFFF
        cpu.push(caller_cs)
        cpu.push(0xA9BD)
        s.cs = 0x1F8F
        s.ip = 0x081D
        run_demo_counter_tick_1f8f_081d(cpu, self_disable_if_patched)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (caller_cs, 0xA9BD):
            raise RuntimeError(
                f"1F8F:081D returned to unexpected IP {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X} inside A940"
            )

    mem.wb(ds, 0x98A9, 0)
    flag98a8 = mem.rb(ds, 0x98A8)
    _cmp_byte(cpu, flag98a8, 0)
    if flag98a8 != 0:
        mem.wb(ds, 0x98A8, 0)
        mem.wb(ds, 0x98A9, 1)

    pending = mem.rw(ds, 0xA8C2)
    _cmp_word(cpu, pending, 1)
    if pending == 1:
        s.ip = 0xA9DA
        return

    s.cx = 0x0023
    s.ip = 0xA9E0


SIG_DEMO_COUNTER_TICK_1F8F_081D_COMPACT_CMP = bytes.fromhex(
    "fe 0e a7 98 75 2b a1 7e a4 b1 78 83 f8 10 77 17 "
    "b1 64 83 f8 08 77 0f b1 50 83 f8 04 77 07 b1 3c "
    "83 f8 02 77 02 b1 28"
)
SIG_DEMO_COUNTER_TICK_1F8F_081D_WIDE_CMP = bytes.fromhex(
    "fe 0e a7 98 75 2b a1 7e a4 b1 78 3d 10 00 77 17 "
    "b1 64 3d 08 00 77 10 b1 50 3d 04 00 77 09 b1 3c "
    "3d 02 00 77 02 b1 28"
)
SIG_DEMO_COUNTER_TICK_1F8F_081D = (
    SIG_DEMO_COUNTER_TICK_1F8F_081D_COMPACT_CMP,
    SIG_DEMO_COUNTER_TICK_1F8F_081D_WIDE_CMP,
)


def run_demo_counter_tick_1f8f_081d(cpu, self_disable_if_patched) -> None:
    """Lift the small far-call demo/attract counter tick at 1F8F:081D.

    A940 calls this once per frame only while DS:2356 == 5.  It decrements
    DS:98A7; when the byte reaches zero it reloads it from the current speed
    bucket DS:A47E and increments DS:98A6.  Otherwise it clears DS:98A6.
    The routine returns with RETF.
    """
    if self_disable_if_patched(
        cpu,
        0x081D,
        SIG_DEMO_COUNTER_TICK_1F8F_081D,
        "overkill_demo_counter_tick_1f8f_081d",
    ):
        return

    s = cpu.s
    ds = s.ds & 0xFFFF
    mem = cpu.mem

    result = _dec_mem_byte_preserve_cf(cpu, ds, 0x98A7)
    if result != 0:
        mem.wb(ds, 0x98A6, 0)
        s.ip = cpu.pop()
        s.cs = cpu.pop()
        return

    s.ax = mem.rw(ds, 0xA47E)
    s.cx = (s.cx & 0xFF00) | 0x78
    _cmp_word(cpu, s.ax, 0x0010)
    if s.ax <= 0x0010:
        s.cx = (s.cx & 0xFF00) | 0x64
        _cmp_word(cpu, s.ax, 0x0008)
        if s.ax <= 0x0008:
            s.cx = (s.cx & 0xFF00) | 0x50
            _cmp_word(cpu, s.ax, 0x0004)
            if s.ax <= 0x0004:
                s.cx = (s.cx & 0xFF00) | 0x3C
                _cmp_word(cpu, s.ax, 0x0002)
                if s.ax <= 0x0002:
                    s.cx = (s.cx & 0xFF00) | 0x28

    mem.wb(ds, 0x98A7, s.cx & 0xFF)
    _inc_mem_byte_preserve_cf(cpu, ds, 0x98A6)
    s.ip = cpu.pop()
    s.cs = cpu.pop()


SIG_GAMEPLAY_COUNTER_TICK_1F8F_0922 = bytes.fromhex(
    "83 3e 5a a9 ff 74 36 ff 06 12 c8 83 26 12 c8 01 75 2b "
    "be c1 c6 b9 14 00 e8 23 00"
)




SIG_DECREMENT_ACTIVE_COUNTER_61C7 = bytes.fromhex(
    "bf 68 23 83 3d 00 74 03 ff 0d c3 83 c7 02 81 ff 74 23 75 ef c3"
)
SIG_DECREMENT_ACTIVE_COUNTER_SCAN_61CA = bytes.fromhex(
    "83 3d 00 74 03 ff 0d c3 83 c7 02 81 ff 74 23 75 ef c3"
)
SIG_DECREMENT_ACTIVE_COUNTER_LOOP_61F7 = bytes.fromhex(
    "e8 cd ff e2 fb"
)


def run_decrement_first_active_counter_61c7(cpu, self_disable_if_patched) -> None:
    """Lift 1010:61C7, a tiny per-frame countdown helper.

    The routine scans the six word counters at ``DS:2368..2372``.  It decrements
    the first non-zero counter and returns immediately; if all counters are zero
    it returns after the final ``CMP DI,2374h``.  This is game-state/timing glue,
    not object semantics.

    Historical note: an older hook was registered at ``61C5``, but that address
    is the middle of the preceding CALL immediate in the materialized runtime
    body.  ``61C7`` is the real instruction boundary (``MOV DI,2368h``).
    """
    if self_disable_if_patched(
        cpu,
        0x61C7,
        SIG_DECREMENT_ACTIVE_COUNTER_61C7,
        "overkill_decrement_first_active_counter_61c7",
    ):
        return

    cpu.s.di = 0x2368
    _run_decrement_first_active_counter_scan(cpu)


def run_decrement_first_active_counter_scan_61ca(cpu, self_disable_if_patched) -> None:
    """Lift the 1010:61CA scan body when callers provide the starting DI."""
    if self_disable_if_patched(
        cpu,
        0x61CA,
        SIG_DECREMENT_ACTIVE_COUNTER_SCAN_61CA,
        "overkill_decrement_first_active_counter_scan_61ca",
    ):
        return
    _run_decrement_first_active_counter_scan(cpu)



def run_decrement_first_active_counter_loop_61f7(cpu, self_disable_if_patched) -> None:
    """Lift the hot ``CALL 61C7; LOOP 61F7`` status-counter loop.

    The parent display/status routine at 61DC executes a small loop whose whole
    body is a CALL to the 61C7 countdown scan.  Hooking this glue removes a large
    misleading unknown region while preserving the original CALL stack scratch:
    each virtual CALL writes return IP 61FA below SP before the scan RET pops it.
    LOOP does not modify FLAGS, so the final flags are those left by the last
    61C7 scan, just like the original ASM.
    """
    if self_disable_if_patched(
        cpu,
        0x61F7,
        SIG_DECREMENT_ACTIVE_COUNTER_LOOP_61F7,
        "overkill_decrement_first_active_counter_loop_61f7",
    ):
        return

    count = loop_count(cpu.s.cx)
    for index in range(count):
        cpu.push(0x61FA)
        cpu.s.di = 0x2368
        _run_decrement_first_active_counter_scan(cpu)
        if (cpu.s.ip & 0xFFFF) != 0x61FA:
            raise RuntimeError(
                f"61F7 nested 61C7 scan returned to unexpected IP {cpu.s.ip & 0xFFFF:04X}"
            )
        cpu.s.cx = ((cpu.s.cx & 0xFFFF) - 1) & 0xFFFF
        if cpu.s.cx == 0:
            break
        if index == 0xFFFF:
            # loop_count() caps the CX=0 case at the exact 8086 65536
            # iterations, so this should be unreachable unless CX is mutated by
            # a future change inside the nested helper.
            raise RuntimeError("61F7 LOOP failed to terminate after 65536 iterations")

    cpu.s.ip = 0x61FC


def _run_decrement_first_active_counter_scan(cpu) -> None:
    """Thin VM boundary adapter over the recovered frame-timer rule.

    Decodes the countdown table from DS, runs the source-like
    :func:`~overkill.recovered.systems.frame_timers.step_first_active_timer`, and
    writes only the decremented slot back -- then reproduces exactly the original
    61C7 CPU-boundary contract (final DI, the dec/compare flags, and the near
    return) so the live hook stays byte/register/flag identical to the ASM oracle.
    """
    ds = cpu.s.ds & 0xFFFF
    di = cpu.s.di & 0xFFFF
    if di & 1 or not (FRAME_TIMER_TABLE_BASE <= di <= FRAME_TIMER_TABLE_END):
        raise RuntimeError(f"61C7 frame-timer scan reached unexpected DI {di:04X}")
    start_index = (di - FRAME_TIMER_TABLE_BASE) // 2

    counters = tuple(
        cpu.mem.rw(ds, (FRAME_TIMER_TABLE_BASE + i * 2) & 0xFFFF) for i in range(FRAME_TIMER_COUNT)
    )
    step = step_first_active_timer(counters, start_index)

    if step.decremented_index is not None:
        k = step.decremented_index
        addr = (FRAME_TIMER_TABLE_BASE + k * 2) & 0xFFFF
        cpu.mem.ww(ds, addr, step.counters[k])
        cpu.s.di = addr
        # Loop exit after DEC mem,1 on a non-zero value: CF was cleared by the
        # preceding CMP value,0 and the DEC preserves it.
        old = counters[k] & 0xFFFF
        cpu.set_sub_flags(old, 1, old - 1, 16)
        cpu.set_flag(CF, False)
    else:
        cpu.s.di = FRAME_TIMER_TABLE_END & 0xFFFF
        # Loop exit after CMP DI,2374h with DI == 2374h: ZF set, CF clear.
        cpu.set_sub_flags(FRAME_TIMER_TABLE_END, FRAME_TIMER_TABLE_END, 0, 16)

    cpu.s.ip = cpu.pop()



SIG_STATUS_DISPLAY_PARENT_61DC = bytes.fromhex(
    "55 2e 8e 06 96 95 bf 68 23 b9 06 00 b8 04 00 f3 ab "
    "8b 0e 5c a9 e3 09 0b c9 78 05 e8 cd ff e2 fb b4 40 "
    "b0 1f e8 fd f7 2e 8e 1e b4 95 36 8b 36 68 23 e8 86 "
    "00 36 8b 36 6a 23 e8 7e 00 36 8b 36 6c 23 e8 76 00 "
    "36 8b 36 6e 23 e8 6e 00 36 8b 36 70 23 e8 66 00 36 "
    "8b 36 72 23 e8 5e 00 2e 8e 1e 96 95 a1 5a a9 3b 06 "
    "74 23 74 4e b0 1f b4 0c e8 b3 f7 be 00 00 83 3e 5a "
    "a9 ff 74 04 8b 36 5a a9 83 c6 20 d1 e6 81 c6 e4 0b "
    "2e 8b 34 2e 8e 1e b4 95 e8 fd f7 2e 8e 1e 96 95 b0 "
    "21 b4 18 e8 85 f7 be 1e 00 d1 e6 81 c6 e4 0b 2e 8b "
    "34 2e 8e 1e b4 95 e8 dd f7 2e 8e 1e 96 95 5d c3"
)



def run_status_display_parent_61dc(
    cpu,
    self_disable_if_patched,
    call_xy_to_di,
    call_status_counter_cell_blit,
    call_menu_cell_source_blit,
) -> None:
    """Lift 1010:61DC, the raw status/counter display parent.

    This parent clears the six status counter words at ``SS:2368..2372``, runs
    the already-lifted ``61C7`` countdown scan while ``DS:A95C`` is positive,
    draws those six cells through ``6296``, and optionally draws two trailing
    marker cells based on ``DS:A95A``.  It remains a low-level display/status
    compositor: no semantic HUD widget names are introduced here.
    """
    if self_disable_if_patched(
        cpu,
        0x61DC,
        SIG_STATUS_DISPLAY_PARENT_61DC,
        "overkill_status_display_parent_61dc",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF

    cpu.push(s.bp & 0xFFFF)

    s.es = mem.rw(cs, 0x9596)
    s.di = 0x2368
    s.cx = 0x0006
    s.ax = 0x0004
    _rep_stosw_preserve_flags(cpu, 6)

    s.cx = mem.rw(ds, 0xA95C)
    if s.cx != 0:
        cpu.set_logic_flags(s.cx & 0xFFFF, 16)
        if (s.cx & 0x8000) == 0:
            run_decrement_first_active_counter_loop_61f7(cpu, self_disable_if_patched)
            if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x61FC):
                raise RuntimeError(
                    f"61DC expected 61F7 loop to finish at 61FC, got "
                    f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
                )
    else:
        # JCXZ does not affect FLAGS; keep the incoming status flags.
        pass

    s.ax = (0x40 << 8) | 0x1F
    call_xy_to_di(0x6203)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x6203):
        raise RuntimeError(f"61DC expected 5A00 return 6203, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    s.ds = mem.rw(cs, 0x95B4)
    for offset, return_ip in (
        (0x2368, 0x6210),
        (0x236A, 0x6218),
        (0x236C, 0x6220),
        (0x236E, 0x6228),
        (0x2370, 0x6230),
        (0x2372, 0x6238),
    ):
        s.si = mem.rw(ss, offset)
        call_status_counter_cell_blit(return_ip)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, return_ip):
            raise RuntimeError(
                f"61DC expected 6296 return {return_ip:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    s.ds = mem.rw(cs, 0x9596)
    ds = s.ds & 0xFFFF
    s.ax = mem.rw(ds, 0xA95A)
    _cmp_word(cpu, s.ax & 0xFFFF, mem.rw(ds, 0x2374))
    if (s.ax & 0xFFFF) != mem.rw(ds, 0x2374):
        s.ax = (0x0C << 8) | 0x1F
        call_xy_to_di(0x624D)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x624D):
            raise RuntimeError(f"61DC expected 5A00 return 624D, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

        s.si = 0x0000
        _cmp_word(cpu, mem.rw(ds, 0xA95A), 0xFFFF)
        if mem.rw(ds, 0xA95A) != 0xFFFF:
            s.si = mem.rw(ds, 0xA95A)
        _add_reg16(cpu, 6, 0x0020)
        s.si = cpu.shift(4, s.si & 0xFFFF, 1, 16)
        _add_reg16(cpu, 6, 0x0BE4)
        s.si = mem.rw(cs, s.si & 0xFFFF)
        s.ds = mem.rw(cs, 0x95B4)
        call_menu_cell_source_blit(0x626F)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x626F):
            raise RuntimeError(f"61DC expected first 5A6C return 626F, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

        s.ds = mem.rw(cs, 0x9596)
        ds = s.ds & 0xFFFF
        s.ax = (0x18 << 8) | 0x21
        call_xy_to_di(0x627B)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x627B):
            raise RuntimeError(f"61DC expected 5A00 return 627B, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

        s.si = 0x001E
        s.si = cpu.shift(4, s.si & 0xFFFF, 1, 16)
        _add_reg16(cpu, 6, 0x0BE4)
        s.si = mem.rw(cs, s.si & 0xFFFF)
        s.ds = mem.rw(cs, 0x95B4)
        call_menu_cell_source_blit(0x628F)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x628F):
            raise RuntimeError(f"61DC expected second 5A6C return 628F, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

        s.ds = mem.rw(cs, 0x9596)

    s.bp = cpu.pop()
    s.ip = cpu.pop()


SIG_STATUS_COUNTER_CELL_BLIT_6296 = bytes.fromhex(
    "83 c6 19 d1 e6 81 c6 e4 0b 2e 8b 34 57 e8 c6 f7 5f e9 94 fe"
)


def run_status_counter_cell_blit_6296(cpu, self_disable_if_patched, call_menu_cell_source_blit) -> None:
    """Lift the 1010:6296 status-counter cell blit helper.

    61DC calls this helper six times to draw the small status/counter cells.
    The routine selects a cell sprite from the CS:0BE4 table, calls the already
    verified 5A6C menu-cell blitter, restores DI, then tail-jumps to the tiny
    613E video-mode cursor advance dispatch.

    Keeping this as a composed helper removes the remaining hot interpreted
    6296/613E glue without lifting the whole 61DC display parent yet.
    """
    if self_disable_if_patched(
        cpu,
        0x6296,
        SIG_STATUS_COUNTER_CELL_BLIT_6296,
        "overkill_status_counter_cell_blit_6296",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    _add_reg16(cpu, 6, 0x0019)
    s.si = cpu.shift(4, s.si & 0xFFFF, 1, 16)
    _add_reg16(cpu, 6, 0x0BE4)
    s.si = mem.rw(cs, s.si & 0xFFFF)

    cpu.push(s.di & 0xFFFF)
    call_menu_cell_source_blit(0x62A6)
    if (s.ip & 0xFFFF) != 0x62A6:
        raise RuntimeError(f"5A6C returned to unexpected IP {s.ip:04X} inside 6296 status cell blit")
    s.di = cpu.pop()

    _run_status_cursor_advance_613e(cpu)


SIG_STATUS_CURSOR_ADVANCE_613E = bytes.fromhex(
    "2e 8b 1e bc 95 d1 e3 2e ff a7 4a 61 50 61 54 61 56 61 "
    "83 c7 02 c3 47 c3 83 c7 04 c3"
)

SIG_STATUS_CURSOR_RETREAT_615A = bytes.fromhex(
    "2e 8b 1e bc 95 d1 e3 2e ff a7 66 61 6c 61 70 61 72 61 "
    "83 ef 02 c3 4f c3 83 ef 04 c3"
)


def run_status_cursor_advance_613e(cpu, self_disable_if_patched) -> None:
    """Lift the tiny 1010:613E video-mode text/status cursor advance helper.

    The helper is a CS:95BC jump-table dispatch used by status/HUD drawing
    glue.  Mode 0 advances DI by 2, mode 1 by 1, and mode 2 by 4.  It is a
    rendering/status cursor stride leaf, not a high-level HUD model.
    """
    if self_disable_if_patched(
        cpu,
        0x613E,
        SIG_STATUS_CURSOR_ADVANCE_613E,
        "overkill_status_cursor_advance_613e",
    ):
        return
    _run_status_cursor_advance_613e(cpu)


def _run_status_cursor_advance_613e(cpu) -> None:
    """Advance the status/HUD cursor by one cell (the lifted 613E rule).

    The game logic -- how far one status cell advances the video cursor in the
    active mode -- now lives in :func:`status_cursor_stride`.  This adapter keeps
    only the VM-boundary ceremony: it reproduces the BX=mode<<1 / SHL-flags
    register effect, applies the stride with the original DI op (INC when the
    stride is one byte, ADD otherwise, which differ in their carry behaviour),
    and near-returns.
    """
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    s.bx = mem.rw(cs, 0x95BC)
    s.bx = cpu.shift(4, s.bx & 0xFFFF, 1, 16)  # BX = video_mode << 1, SHL flags
    stride = status_cursor_stride((s.bx >> 1) & 0xFFFF)
    if stride == 1:
        _inc_reg16_preserve_cf(cpu, 7)  # INC DI keeps CF (the SHL result)
    else:
        _add_reg16(cpu, 7, stride)
    s.ip = cpu.pop()


def run_status_cursor_retreat_615a(cpu, self_disable_if_patched) -> None:
    """Retreat the status/HUD cursor by one cell (the lifted 615A rule).

    The inverse of 613E and the same lifted rule: one status cell is
    :func:`status_cursor_stride` bytes wide in the active mode.  This adapter
    keeps only the VM-boundary ceremony, applying the stride with the original
    backward DI op (DEC for a one-byte stride, SUB otherwise).
    """
    if self_disable_if_patched(
        cpu,
        0x615A,
        SIG_STATUS_CURSOR_RETREAT_615A,
        "overkill_status_cursor_retreat_615a",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    s.bx = mem.rw(cs, 0x95BC)
    s.bx = cpu.shift(4, s.bx & 0xFFFF, 1, 16)  # BX = video_mode << 1, SHL flags
    stride = status_cursor_stride((s.bx >> 1) & 0xFFFF)
    if stride == 1:
        _dec_reg16_preserve_cf(cpu, 7)  # DEC DI keeps CF (the SHL result)
    else:
        _sub_reg16(cpu, 7, stride)
    s.ip = cpu.pop()



SIG_STATUS_ROW_REPEAT_6120 = bytes.fromhex(
    "e3 16 56 57 51 2e 8e 1e b4 95 e8 3f f9 59 5f 5e "
    "e8 0b 00 e8 08 00 e2 e8 2e 8e 1e 96 95 c3"
)


def run_status_row_repeat_6120(cpu, self_disable_if_patched, call_cell_blit, call_cursor_advance) -> None:
    """Lift 1010:6120, a raw repeated status/HUD cell row compositor.

    The routine draws ``CX`` adjacent cells using the mode-specific ``5A6C``
    source blitter, then advances the text/status cursor twice through ``613E``
    between cells.  It is deliberately kept below semantic HUD naming: this is a
    row-repeat primitive over existing blit/cursor leaves.
    """
    if self_disable_if_patched(cpu, 0x6120, SIG_STATUS_ROW_REPEAT_6120, "overkill_status_row_repeat_6120"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    if (s.cx & 0xFFFF) != 0:
        while True:
            # PUSH SI; PUSH DI; PUSH CX
            cpu.push(s.si & 0xFFFF)
            cpu.push(s.di & 0xFFFF)
            cpu.push(s.cx & 0xFFFF)

            s.ds = mem.rw(cs, 0x95B4)
            call_cell_blit(0x612D)
            if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x612D):
                raise RuntimeError(
                    f"6120 expected 5A6C to return to 612D, got "
                    f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
                )

            s.cx = cpu.pop()
            s.di = cpu.pop()
            s.si = cpu.pop()

            call_cursor_advance(0x6133)
            if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x6133):
                raise RuntimeError(
                    f"6120 expected first 613E to return to 6133, got "
                    f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
                )
            call_cursor_advance(0x6136)
            if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x6136):
                raise RuntimeError(
                    f"6120 expected second 613E to return to 6136, got "
                    f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
                )

            s.cx = (s.cx - 1) & 0xFFFF
            if s.cx == 0:
                break

    s.ds = mem.rw(cs, 0x9596)
    s.ip = cpu.pop()


SIG_STATUS_CELL_QUAD_COMPOSITE_859E = bytes.fromhex(
    "55 e8 13 00 2e 83 3e bc 95 01 75 09 e8 72 cb e8 05 00 "
    "e8 6c cb 5d c3 bd 82 96 33 ff e8 18 00 bd 8c 96 bf 01 "
    "00 e8 0f 00 bd 96 96 bf 02 00 e8 06 00 bd a0 96 bf 03 00"
)


def run_status_cell_quad_composite_859e(
    cpu,
    self_disable_if_patched,
    call_cell_composite,
    tail_cell_composite,
    call_video_page_toggle,
) -> None:
    """Lift 1010:859E, the four-cell status/HUD descriptor compositor parent.

    ``859E`` preserves the caller's BP, calls the tiny ``85B5`` descriptor
    sequence, and in video mode 1 toggles the active page around a second pass.
    The internal ``85B5`` is unusual: its fourth cell falls through into
    ``85D5`` so that ``85D5`` returns directly to the caller of ``85B5``.  The
    helper below preserves that stack shape instead of inventing a cleaner
    subroutine boundary.
    """
    if self_disable_if_patched(cpu, 0x859E, SIG_STATUS_CELL_QUAD_COMPOSITE_859E, "overkill_status_cell_quad_composite_859e"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    def run_85b5_sequence(return_ip: int) -> None:
        # Model CALL 85B5.  The fourth/fallthrough 85D5 consumes this return.
        cpu.push(return_ip & 0xFFFF)

        s.bp = 0x9682
        s.di = 0x0000
        cpu.set_logic_flags(0, 16)  # XOR DI,DI
        call_cell_composite(0x85BD)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x85BD):
            raise RuntimeError(f"859E expected first 85D5 return to 85BD, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

        s.bp = 0x968C
        s.di = 0x0001
        call_cell_composite(0x85C6)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x85C6):
            raise RuntimeError(f"859E expected second 85D5 return to 85C6, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

        s.bp = 0x9696
        s.di = 0x0002
        call_cell_composite(0x85CF)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x85CF):
            raise RuntimeError(f"859E expected third 85D5 return to 85CF, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

        s.bp = 0x96A0
        s.di = 0x0003
        tail_cell_composite()
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, return_ip & 0xFFFF):
            raise RuntimeError(
                f"859E expected fallthrough 85D5 to return to {return_ip:04X}, "
                f"got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    cpu.push(s.bp & 0xFFFF)
    run_85b5_sequence(0x85A2)

    mode = mem.rw(cs, 0x95BC)
    _cmp_word(cpu, mode, 0x0001)
    if mode == 0x0001:
        call_video_page_toggle(0x85AD)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x85AD):
            raise RuntimeError(f"859E expected first 511F return to 85AD, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
        run_85b5_sequence(0x85B0)
        call_video_page_toggle(0x85B3)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x85B3):
            raise RuntimeError(f"859E expected second 511F return to 85B3, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    s.bp = cpu.pop()
    s.ip = cpu.pop()

SIG_STATUS_CELL_COMPOSITE_85D5 = bytes.fromhex(
    "83 3e fa 95 ff 74 11 8b 36 fa 95 d1 e6 81 c6 fc 95 "
    "3b 2c b8 01 00 74 02 33 c0 83 3e ac bd 01 75 0c "
    "3b 3e fa 95 75 06 ff 36 16 be eb 03 ff 76 00 50 "
    "8b 76 04 03 f0 d1 e6 81 c6 e4 0b 2e 8b 34 8b 7e "
    "02 57 b9 05 00 e8 20 db e2 fb 2e 8e 1e b4 95 e8 "
    "44 d4 5f e8 2e db 5e 83 c6 17 d1 e6 81 c6 e4 0b "
    "2e 8b 34 57 e8 2f d4 5f e8 fd da 5e d1 e6 81 c6 "
    "e4 0b 2e 8b 34 e8 1e d4 2e 8e 1e 96 95 c3"
)

SIG_STATUS_COORD_LIST_FILL_99CD = bytes.fromhex(
    "8b 46 02 05 08 00 ab 8b 46 04 05 09 00 ab e2 f0"
)

SIG_FRAME_AXIS_COUNT_INC_AH_9BFB = bytes.fromhex("fe c4 c3")
SIG_FRAME_AXIS_COUNT_INC_AL_9BFE = bytes.fromhex("fe c0 c3")

SIG_FRAME_AXIS_CONDITION_DISPATCH_9C01 = bytes.fromhex(
    "c7 06 60 a3 00 00 f6 06 be 98 02 75 10 80 3e 9e a3 "
    "01 75 09 e8 ef 09 c7 06 60 a3 01 00 f6 06 be 98 01 "
    "75 10 80 3e 9f a3 01 75 09 e8 ca 09 c7 06 60 a3 01 "
    "00 33 c0 83 3e 66 a9 ff 74 03 e8 ba ff 83 3e 68 a9 "
    "ff 74 03 e8 b3 ff 83 3e 6a a9 ff 74 03 e8 a6 ff 83 "
    "3e 6c a9 ff 74 03 e8 9f ff 8a d8 32 ff 02 dc 02 dc "
    "02 dc d1 e3 2e ff a7 70 9c af 44 9c 9c ad 9c 82 9c "
    "af 44 9c 9c 93 9c 82 9c af 44 83 3e 24 23 01 75 01 "
    "c3 c7 06 60 a3 01 00 e9 77 09 c7 06 60 a3 01 00 e9 "
    "6e 09 83 3e 24 23 01 75 01 c3 c7 06 60 a3 01 00 e9 "
    "4f 09 c7 06 60 a3 01 00 e9 46 09"
)


def _run_object_y_step_down_one_pass_a60a(cpu) -> None:
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    value = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, value, 0x00B0)
    if value < 0x00B0:
        _inc_mem_word_preserve_cf(cpu, ss, (bp + 0x04) & 0xFFFF)
    cpu.s.ip = cpu.pop()


def _run_object_y_step_up_one_pass_a5fc(cpu) -> None:
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    value = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, value, 0x0000)
    if value != 0:
        _dec_mem_word_preserve_cf(cpu, ss, (bp + 0x04) & 0xFFFF)
    cpu.s.ip = cpu.pop()


def _add_bl_ah(cpu) -> None:
    old = cpu.s.bx & 0x00FF
    addend = (cpu.s.ax >> 8) & 0x00FF
    result = old + addend
    cpu.s.bx = (cpu.s.bx & 0xFF00) | (result & 0x00FF)
    cpu.set_add_flags(old, addend, result, 8)


def run_frame_axis_condition_dispatch_9c01(
    cpu,
    self_disable_if_patched,
    call_y_step_down,
    call_y_step_up,
) -> None:
    """Lift the 1010:9C01 axis-condition counter and jump-table dispatch.

    This child of the larger ``9B2E`` frame controller combines current input
    bits, four delayed coordinate slots, and a small jump table.  It is still a
    runtime frame/controller primitive, not semantic movement intent.
    """
    if self_disable_if_patched(
        cpu,
        0x9C01,
        SIG_FRAME_AXIS_CONDITION_DISPATCH_9C01,
        "overkill_frame_axis_condition_dispatch_9c01",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    mem.ww(ds, 0xA360, 0x0000)

    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x02, 8)
    if (input_flags & 0x02) == 0:
        marker = mem.rb(ds, 0xA39E)
        _cmp_byte(cpu, marker, 0x01)
        if marker == 0x01:
            call_y_step_down(0x9C18)
            if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x9C18):
                raise RuntimeError(f"9C01 expected A607 return 9C18, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
            mem.ww(ds, 0xA360, 0x0001)

    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x01, 8)
    if (input_flags & 0x01) == 0:
        marker = mem.rb(ds, 0xA39F)
        _cmp_byte(cpu, marker, 0x01)
        if marker == 0x01:
            call_y_step_up(0x9C2F)
            if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x9C2F):
                raise RuntimeError(f"9C01 expected A5F9 return 9C2F, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
            mem.ww(ds, 0xA360, 0x0001)

    s.ax = 0x0000
    cpu.set_logic_flags(0, 16)

    for off, return_ip, which in (
        (0xA966, 0x9C41, "ah"),
        (0xA968, 0x9C4B, "al"),
        (0xA96A, 0x9C55, "ah"),
        (0xA96C, 0x9C5F, "al"),
    ):
        value = mem.rw(ds, off)
        _cmp_word(cpu, value, 0xFFFF)
        if value != 0xFFFF:
            if which == "ah":
                cpu.push(return_ip)
                run_frame_axis_count_inc_ah_9bfb(cpu, self_disable_if_patched)
            else:
                cpu.push(return_ip)
                run_frame_axis_count_inc_al_9bfe(cpu, self_disable_if_patched)
            if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, return_ip):
                raise RuntimeError(f"9C01 expected {which.upper()} counter return {return_ip:04X}, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    s.bx = (s.bx & 0xFF00) | (s.ax & 0x00FF)
    s.bx &= 0x00FF
    cpu.set_logic_flags(0, 8)  # XOR BH,BH
    _add_bl_ah(cpu)
    _add_bl_ah(cpu)
    _add_bl_ah(cpu)
    s.bx = cpu.shift(4, s.bx & 0xFFFF, 1, 16)

    target = mem.rw(cs, (0x9C70 + (s.bx & 0xFFFF)) & 0xFFFF)
    if target == 0x44AF:
        s.ip = cpu.pop()
        return
    if target in (0x9C82, 0x9C9C):
        current = mem.rw(ds, 0x2324)
        _cmp_word(cpu, current, 0x0001)
        if current == 0x0001:
            s.ip = cpu.pop()
            return
        mem.ww(ds, 0xA360, 0x0001)
        if target == 0x9C82:
            _run_object_y_step_down_one_pass_a60a(cpu)
        else:
            _run_object_y_step_up_one_pass_a5fc(cpu)
        return
    if target == 0x9C93:
        mem.ww(ds, 0xA360, 0x0001)
        _run_object_y_step_down_one_pass_a60a(cpu)
        return
    if target == 0x9CAD:
        mem.ww(ds, 0xA360, 0x0001)
        _run_object_y_step_up_one_pass_a5fc(cpu)
        return
    raise RuntimeError(f"unverified 9C01 jump-table target {target:04X}")



SIG_FRAME_TRACKED_COORD_STORE_9CD9 = (
    bytes.fromhex("2e 8e 06 96 95 8b 3e 3a a3 8b 46 02 83 c0 08 ab 8b 46 04 83 c0 08 ab c3"),
    bytes.fromhex("2e 8e 06 96 95 8b 3e 3a a3 8b 46 02 05 08 00 ab 8b 46 04 05 08 00 ab c3"),
)
SIG_FRAME_COORD_RING_ADVANCE_9CF1 = bytes.fromhex("f6 06 be 98 0f 75 08 83 3e 60 a3 00 75 01 c3 83 06 3a a3 04")
SIG_TRACKED_OBJECT_COORD_PULL_A031 = bytes.fromhex("83 3e 62 a9 ff 74 10 8b 1e 62 a9 8b 36 3c a3 ad 89 47 02 ad 89 47 04 83 3e 64 a9 ff 74 10")


def run_status_cell_composite_85d5(
    cpu,
    self_disable_if_patched,
    call_cursor_advance,
    call_cursor_retreat,
    call_cell_blit,
) -> None:
    """Lift 1010:85D5, a low-level status/HUD cell composition parent.

    This block decides which of two small status-cell glyph sources to use,
    advances/retreats the mode-dependent cursor through the already-lifted
    ``613E``/``615A`` leaves, and calls the existing ``5A6C`` cell blitter three
    times.  It is intentionally still a raw compositor, not a semantic HUD
    widget.
    """
    if self_disable_if_patched(cpu, 0x85D5, SIG_STATUS_CELL_COMPOSITE_85D5, "overkill_status_cell_composite_85d5"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF

    marker = mem.rw(ds, 0x95FA)
    _cmp_word(cpu, marker, 0xFFFF)
    if marker == 0xFFFF:
        s.ax = 0x0000
        cpu.set_logic_flags(0, 16)
    else:
        s.si = marker
        s.si = cpu.shift(4, s.si & 0xFFFF, 1, 16)
        _add_reg16(cpu, 6, 0x95FC)
        _cmp_word(cpu, s.bp & 0xFFFF, mem.rw(ds, s.si & 0xFFFF))
        s.ax = 0x0001
        if (s.bp & 0xFFFF) != mem.rw(ds, s.si & 0xFFFF):
            s.ax = 0x0000
            cpu.set_logic_flags(0, 16)

    bdac = mem.rw(ds, 0xBDAC)
    _cmp_word(cpu, bdac, 0x0001)
    if bdac == 0x0001:
        marker = mem.rw(ds, 0x95FA)
        _cmp_word(cpu, s.di & 0xFFFF, marker)
        if (s.di & 0xFFFF) == marker:
            cpu.push(mem.rw(ds, 0xBE16))
        else:
            cpu.push(mem.rw(ss, (s.bp + 0x00) & 0xFFFF))
    else:
        cpu.push(mem.rw(ss, (s.bp + 0x00) & 0xFFFF))

    cpu.push(s.ax & 0xFFFF)
    s.si = mem.rw(ss, (s.bp + 0x04) & 0xFFFF)
    _add_reg16(cpu, 6, s.ax & 0xFFFF)
    s.si = cpu.shift(4, s.si & 0xFFFF, 1, 16)
    _add_reg16(cpu, 6, 0x0BE4)
    s.si = mem.rw(cs, s.si & 0xFFFF)
    s.di = mem.rw(ss, (s.bp + 0x02) & 0xFFFF)
    cpu.push(s.di & 0xFFFF)
    s.cx = 0x0005
    while True:
        call_cursor_advance(0x861E)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x861E):
            raise RuntimeError(f"85D5 expected 613E to return to 861E, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
        s.cx = (s.cx - 1) & 0xFFFF
        if s.cx == 0:
            break

    s.ds = mem.rw(cs, 0x95B4)
    call_cell_blit(0x8628)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x8628):
        raise RuntimeError(f"85D5 expected 5A6C to return to 8628, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
    s.di = cpu.pop()
    call_cursor_retreat(0x862C)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x862C):
        raise RuntimeError(f"85D5 expected 615A to return to 862C, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    s.si = cpu.pop()
    _add_reg16(cpu, 6, 0x0017)
    s.si = cpu.shift(4, s.si & 0xFFFF, 1, 16)
    _add_reg16(cpu, 6, 0x0BE4)
    s.si = mem.rw(cs, s.si & 0xFFFF)
    cpu.push(s.di & 0xFFFF)
    call_cell_blit(0x863D)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x863D):
        raise RuntimeError(f"85D5 expected 5A6C to return to 863D, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
    s.di = cpu.pop()
    call_cursor_advance(0x8641)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x8641):
        raise RuntimeError(f"85D5 expected 613E to return to 8641, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    s.si = cpu.pop()
    s.si = cpu.shift(4, s.si & 0xFFFF, 1, 16)
    _add_reg16(cpu, 6, 0x0BE4)
    s.si = mem.rw(cs, s.si & 0xFFFF)
    call_cell_blit(0x864E)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x864E):
        raise RuntimeError(f"85D5 expected 5A6C to return to 864E, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
    s.ds = mem.rw(cs, 0x9596)
    s.ip = cpu.pop()




def run_frame_tracked_coord_store_9cd9(cpu, self_disable_if_patched) -> None:
    """Lift 1010:9CD9, storing the current object center into the coord ring.

    This is still raw frame-controller data prep: BP points at an object slot,
    DS:A33A names the current coordinate-ring write cursor, and the routine
    writes X+8/Y+8 into ES:DI.
    """
    if self_disable_if_patched(cpu, 0x9CD9, SIG_FRAME_TRACKED_COORD_STORE_9CD9, "overkill_frame_tracked_coord_store_9cd9"):
        return
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    s.es = mem.rw(cs, 0x9596)
    s.di = mem.rw(s.ds & 0xFFFF, 0xA33A)
    old_ax = mem.rw(ss, (s.bp + 0x02) & 0xFFFF)
    s.ax = (old_ax + 0x0008) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0008, old_ax + 0x0008, 16)
    mem.ww(s.es & 0xFFFF, s.di & 0xFFFF, s.ax)
    s.di = (s.di + 2) & 0xFFFF
    old_ax = mem.rw(ss, (s.bp + 0x04) & 0xFFFF)
    s.ax = (old_ax + 0x0008) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0008, old_ax + 0x0008, 16)
    mem.ww(s.es & 0xFFFF, s.di & 0xFFFF, s.ax)
    s.di = (s.di + 2) & 0xFFFF
    s.ip = cpu.pop()


def _advance_coord_ring_ptr(cpu, ds: int, off: int) -> None:
    mem = cpu.mem
    old = mem.rw(ds, off)
    new = (old + 0x0004) & 0xFFFF
    mem.ww(ds, off, new)
    cpu.set_add_flags(old, 0x0004, old + 0x0004, 16)
    _cmp_word(cpu, new, 0xA33A)
    if new == 0xA33A:
        mem.ww(ds, off, 0xA27A)


def run_frame_coord_ring_advance_9cf1(cpu, self_disable_if_patched) -> None:
    """Lift 1010:9CF1, advancing the four-frame coordinate-ring cursors."""
    if self_disable_if_patched(cpu, 0x9CF1, SIG_FRAME_COORD_RING_ADVANCE_9CF1, "overkill_frame_coord_ring_advance_9cf1"):
        return
    s = cpu.s
    ds = s.ds & 0xFFFF
    mem = cpu.mem
    _test = mem.rb(ds, 0x98BE) & 0x0F
    cpu.set_logic_flags(_test, 8)
    if _test == 0:
        _cmp_word(cpu, mem.rw(ds, 0xA360), 0x0000)
        if mem.rw(ds, 0xA360) == 0x0000:
            s.ip = cpu.pop()
            return
    for off in (0xA33A, 0xA33C, 0xA33E, 0xA340):
        _advance_coord_ring_ptr(cpu, ds, off)
    s.ip = cpu.pop()


def run_tracked_object_coord_pull_a031(cpu, self_disable_if_patched) -> None:
    """Lift 1010:A031, pulling delayed ring coordinates into tracked slots."""
    if self_disable_if_patched(cpu, 0xA031, SIG_TRACKED_OBJECT_COORD_PULL_A031, "overkill_tracked_object_coord_pull_a031"):
        return
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    _cmp_word(cpu, mem.rw(ds, 0xA962), 0xFFFF)
    if mem.rw(ds, 0xA962) != 0xFFFF:
        s.bx = mem.rw(ds, 0xA962)
        s.si = mem.rw(ds, 0xA33C)
        s.ax = mem.rw(ds, s.si & 0xFFFF)
        s.si = (s.si + 2) & 0xFFFF
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.ax)
        s.ax = mem.rw(ds, s.si & 0xFFFF)
        s.si = (s.si + 2) & 0xFFFF
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.ax)
    _cmp_word(cpu, mem.rw(ds, 0xA964), 0xFFFF)
    if mem.rw(ds, 0xA964) != 0xFFFF:
        s.bx = mem.rw(ds, 0xA964)
        s.si = mem.rw(ds, 0xA33E)
        s.ax = mem.rw(ds, s.si & 0xFFFF)
        s.si = (s.si + 2) & 0xFFFF
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.ax)
        s.ax = mem.rw(ds, s.si & 0xFFFF)
        s.si = (s.si + 2) & 0xFFFF
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.ax)
    s.ip = cpu.pop()


def run_status_coord_list_fill_99cd(cpu, self_disable_if_patched) -> None:
    """Lift the compact 1010:99CD coordinate-list fill loop.

    The loop writes ``([BP+2]+8, [BP+4]+9)`` pairs into ``ES:DI`` for ``CX``
    entries.  It is a raw status/frame data-preparation loop exposed by the
    post-97B2 profiles, not a semantic object list yet.
    """
    if self_disable_if_patched(cpu, 0x99CD, SIG_STATUS_COORD_LIST_FILL_99CD, "overkill_status_coord_list_fill_99cd"):
        return

    s = cpu.s
    mem = cpu.mem
    ss = s.ss & 0xFFFF
    es = s.es & 0xFFFF
    count = loop_count(s.cx)
    di = s.di & 0xFFFF
    ax = 0
    for _ in range(count):
        ax = mem.rw(ss, (s.bp + 0x02) & 0xFFFF)
        result = ax + 0x0008
        s.ax = result & 0xFFFF
        cpu.set_add_flags(ax, 0x0008, result, 16)
        mem.ww(es, di, s.ax)
        di = (di + 2) & 0xFFFF

        ax = mem.rw(ss, (s.bp + 0x04) & 0xFFFF)
        result = ax + 0x0009
        s.ax = result & 0xFFFF
        cpu.set_add_flags(ax, 0x0009, result, 16)
        mem.ww(es, di, s.ax)
        di = (di + 2) & 0xFFFF
    s.di = di
    s.cx = 0
    s.ip = 0x99DD


def _inc_reg8_preserve_cf(cpu, reg_idx: int) -> None:
    old = cpu.get_reg8(reg_idx)
    old_cf = cpu.get_flag(0x0001)
    result = (old + 1) & 0xFF
    cpu.set_reg8(reg_idx, result)
    cpu.set_add_flags(old, 1, old + 1, 8)
    cpu.set_flag(0x0001, old_cf)


def run_frame_axis_count_inc_ah_9bfb(cpu, self_disable_if_patched) -> None:
    """Lift 1010:9BFB, the tiny ``INC AH; RET`` frame-controller leaf."""
    if self_disable_if_patched(cpu, 0x9BFB, SIG_FRAME_AXIS_COUNT_INC_AH_9BFB, "overkill_frame_axis_count_inc_ah_9bfb"):
        return
    _inc_reg8_preserve_cf(cpu, 4)
    cpu.s.ip = cpu.pop()


def run_frame_axis_count_inc_al_9bfe(cpu, self_disable_if_patched) -> None:
    """Lift 1010:9BFE, the tiny ``INC AL; RET`` frame-controller leaf."""
    if self_disable_if_patched(cpu, 0x9BFE, SIG_FRAME_AXIS_COUNT_INC_AL_9BFE, "overkill_frame_axis_count_inc_al_9bfe"):
        return
    _inc_reg8_preserve_cf(cpu, 0)
    cpu.s.ip = cpu.pop()


def _call_counter_stride_0960(cpu, self_disable_if_patched, return_ip: int) -> None:
    cpu.push(return_ip & 0xFFFF)
    run_gameplay_counter_stride_loop_1f8f_0960(cpu, self_disable_if_patched)
    if (cpu.s.ip & 0xFFFF) != (return_ip & 0xFFFF):
        raise RuntimeError(
            f"1F8F:0922 expected nested 0960 return to {return_ip:04X}, "
            f"got {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}"
        )


def run_gameplay_counter_tick_1f8f_0922(cpu, self_disable_if_patched) -> None:
    """Lift the small far-call counter tick at 1F8F:0922.

    A940 calls this overlay helper once per frame/update.  It is not an asset
    decoder despite living in the overlay segment: it advances gameplay/animation
    counters and reuses the already verified 0960 stride loop for three optional
    counter bands.  The routine returns with RETF.
    """
    if self_disable_if_patched(
        cpu,
        0x0922,
        SIG_GAMEPLAY_COUNTER_TICK_1F8F_0922,
        "overkill_gameplay_counter_tick_1f8f_0922",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    marker = mem.rw(ds, 0xA95A)
    _cmp_word(cpu, marker, 0xFFFF)
    if marker != 0xFFFF:
        _inc_mem_word_preserve_cf(cpu, ds, 0xC812)
        _and_mem_word(cpu, ds, 0xC812, 0x0001)
        if mem.rw(ds, 0xC812) == 0:
            s.si = 0xC6C1
            s.cx = 0x0014
            _call_counter_stride_0960(cpu, self_disable_if_patched, 0x093D)

            _inc_mem_word_preserve_cf(cpu, ds, 0xC814)
            _and_mem_word(cpu, ds, 0xC814, 0x0001)
            if mem.rw(ds, 0xC814) == 0:
                s.cx = 0x000A
                _call_counter_stride_0960(cpu, self_disable_if_patched, 0x094E)

                _inc_mem_word_preserve_cf(cpu, ds, 0xC816)
                _and_mem_word(cpu, ds, 0xC816, 0x0001)
                if mem.rw(ds, 0xC816) == 0:
                    s.cx = 0x000A
                    _call_counter_stride_0960(cpu, self_disable_if_patched, 0x095F)

    s.ip = cpu.pop()
    s.cs = cpu.pop()
