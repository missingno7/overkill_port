"""Lifted OVERKILL frame/game-state update helpers.

These routines sit above raw object-slot behaviours but below any semantic game
model.  They update per-frame counters, globals, and scan orchestration state;
they must not classify concrete enemies/projectiles yet.
"""
from __future__ import annotations

from overkill_port.games.overkill.asm import _add_reg16, _and_mem_word, _cmp_byte, _cmp_word, _dec_mem_byte_preserve_cf, _dec_mem_word_preserve_cf, _inc_mem_byte_preserve_cf, _inc_mem_word_preserve_cf, _inc_reg16_preserve_cf, loop_count


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


SIG_DEMO_COUNTER_TICK_1F8F_081D = bytes.fromhex(
    "fe 0e a7 98 75 2b a1 7e a4 b1 78 83 f8 10 77 17 "
    "b1 64 83 f8 08 77 0f b1 50 83 f8 04 77 07 b1 3c "
    "83 f8 02 77 02 b1 28"
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


def run_decrement_first_active_counter_61c5(cpu, self_disable_if_patched) -> None:
    """Compatibility alias for the old off-by-two helper name.

    This is intentionally not registered at 61C5 anymore; callers/tests that
    imported the Python helper can still exercise the real 61C7 body.
    """
    return run_decrement_first_active_counter_61c7(cpu, self_disable_if_patched)


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
    ds = cpu.s.ds & 0xFFFF
    while True:
        value = cpu.mem.rw(ds, cpu.s.di & 0xFFFF)
        _cmp_word(cpu, value, 0)
        if value != 0:
            _dec_mem_word_preserve_cf(cpu, ds, cpu.s.di & 0xFFFF)
            cpu.s.ip = cpu.pop()
            return
        _add_reg16(cpu, 7, 0x0002)
        _cmp_word(cpu, cpu.s.di & 0xFFFF, 0x2374)
        if cpu.s.di != 0x2374:
            continue
        cpu.s.ip = cpu.pop()
        return



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


def _run_status_cursor_advance_613e(cpu) -> None:
    """Mirror the 613E video-mode text/status cursor advance tail."""
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    s.bx = mem.rw(cs, 0x95BC)
    s.bx = cpu.shift(4, s.bx & 0xFFFF, 1, 16)
    target = mem.rw(cs, (0x614A + s.bx) & 0xFFFF)
    if target == 0x6150:
        _add_reg16(cpu, 7, 0x0002)
    elif target == 0x6154:
        _inc_reg16_preserve_cf(cpu, 7)
    elif target == 0x6156:
        _add_reg16(cpu, 7, 0x0004)
    else:
        raise RuntimeError(f"unverified 613E status cursor advance target {target:04X}")
    s.ip = cpu.pop()


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
