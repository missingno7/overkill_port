"""Lifted OVERKILL frame/game-state update helpers.

These routines sit above raw object-slot behaviours but below any semantic game
model.  They update per-frame counters, globals, and scan orchestration state;
they must not classify concrete enemies/projectiles yet.
"""
from __future__ import annotations

from overkill_port.games.overkill.asm import _add_reg16, _and_mem_word, _cmp_word, _dec_mem_word_preserve_cf, _inc_mem_word_preserve_cf, loop_count


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


SIG_GAMEPLAY_COUNTER_TICK_1F8F_0922 = bytes.fromhex(
    "83 3e 5a a9 ff 74 36 ff 06 12 c8 83 26 12 c8 01 75 2b "
    "be c1 c6 b9 14 00 e8 23 00"
)




SIG_DECREMENT_ACTIVE_COUNTER_61C5 = bytes.fromhex(
    "bf 68 23 83 3d 00 74 03 ff 0d c3 83 c7 02 81 ff 74 23 75 ef c3"
)
SIG_DECREMENT_ACTIVE_COUNTER_SCAN_61CA = bytes.fromhex(
    "83 3d 00 74 03 ff 0d c3 83 c7 02 81 ff 74 23 75 ef c3"
)


def run_decrement_first_active_counter_61c5(cpu, self_disable_if_patched) -> None:
    """Lift 1010:61C5, a tiny per-frame countdown helper.

    The routine scans the six word counters at ``DS:2368..2372``.  It decrements
    the first non-zero counter and returns immediately; if all counters are zero
    it returns after the final ``CMP DI,2374h``.  This is game-state/timing glue,
    not object semantics.
    """
    if self_disable_if_patched(
        cpu,
        0x61C5,
        SIG_DECREMENT_ACTIVE_COUNTER_61C5,
        "overkill_decrement_first_active_counter_61c5",
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
