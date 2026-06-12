"""Tandy/PCjr-specific OVERKILL rendering primitives.

This module contains the low-level mode-2 rendering primitives that were lifted
from ``overkill_port.replacements``.  They are game-specific source-code
counterparts of OVERKILL's original routines, not generic VM services.

The shared layer-sprite setup and dispatch code lives in
``rendering.layer_sprites``.  This module only owns Tandy-specific compositor,
copy, draw, and frame-present leaves such as 1010:2E6E, 1010:356C, and
1010:3354.

The implementation deliberately keeps odd ASM boundary behavior visible:
segment reloads, balanced-CALL stack scratch, offscreen FFFF returns, and exact
near-return handling are part of the contract verified against the original
interpreter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from overkill_port.cpu import CF, DF, ZF
from overkill_port.memory import EGA_CPU_APERTURE, EGA_PLANE_WINDOW

Cpu = object
SelfDisableIfPatched = Callable[[Cpu, int, bytes, str], bool]
HookHandler = Callable[[Cpu], None]

TANDY_DISPLAY_SEGMENT_OFF = 0x9596
TANDY_SOURCE_SEGMENT_OFF = 0x9598
TANDY_VIDEO_SEGMENT_OFF = 0x95A4
WORK_BUFFER_CURSOR_OFF = 0x234C
OFFSCREEN_DESTINATION = 0xFFFF


@dataclass(frozen=True)
class TandyRenderRuntime:
    """VM-bound services needed by the Tandy rendering primitives.

    The game-specific code remains outside the hook-registration module, but it
    still needs the runtime-patched code guard and the object row-address helper
    used by the original draw leaves.  Hook wrappers provide these callbacks so
    the generic VM does not depend on OVERKILL-specific rendering formats.
    """

    self_disable_if_patched: SelfDisableIfPatched
    object_row_address_from_mode_dispatch_5a36: HookHandler
    signature_2e6e: bytes
    signature_2ecb: bytes
    signature_2f40: bytes
    signature_2f81: bytes
    signature_2fb6: bytes
    signature_33b2: bytes
    signature_34ad: bytes
    signature_34c5: bytes
    signature_34d8: bytes
    signature_3542: bytes
    signature_35aa: bytes
    signature_35cc: bytes
    signature_356c: bytes
    signature_3657: bytes


def _call_hook_like_near_call(cpu, handler: HookHandler, return_ip: int) -> None:
    """Run a lifted helper with the same stack side effect as CALL/RET."""
    cpu.push(return_ip & 0xFFFF)
    handler(cpu)


def _cmp_word(cpu, a: int, b: int) -> None:
    cpu.set_sub_flags(a & 0xFFFF, b & 0xFFFF, (a & 0xFFFF) - (b & 0xFFFF), 16)


def _test_word(cpu, a: int, b: int) -> None:
    cpu.set_logic_flags((a & 0xFFFF) & (b & 0xFFFF), 16)


def _stosw(cpu) -> None:
    """Store AX to ES:DI and advance DI exactly like STOSW."""
    cpu.mem.ww(cpu.s.es, cpu.s.di, cpu.s.ax)
    cpu.s.di = (cpu.s.di + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF


def _add_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    addend = value & 0xFFFF
    result = old + addend
    cpu.set_reg16(reg_idx, result)
    cpu.set_add_flags(old, addend, result, 16)


def _sub_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    subtrahend = value & 0xFFFF
    result = old - subtrahend
    cpu.set_reg16(reg_idx, result)
    cpu.set_sub_flags(old, subtrahend, result, 16)


def _add_mem_word(cpu, seg: int, off: int, value: int) -> None:
    old = cpu.mem.rw(seg, off)
    addend = value & 0xFFFF
    result = old + addend
    cpu.mem.ww(seg, off, result)
    cpu.set_add_flags(old, addend, result, 16)


def _sub_mem_word(cpu, seg: int, off: int, value: int) -> None:
    old = cpu.mem.rw(seg, off)
    subtrahend = value & 0xFFFF
    result = old - subtrahend
    cpu.mem.ww(seg, off, result)
    cpu.set_sub_flags(old, subtrahend, result, 16)


def _dec_reg16_preserve_cf(cpu, reg_idx: int) -> None:
    old = cpu.get_reg16(reg_idx)
    old_cf = cpu.get_flag(CF)
    cpu.set_reg16(reg_idx, (old - 1) & 0xFFFF)
    cpu.set_sub_flags(old, 1, old - 1, 16)
    cpu.set_flag(CF, old_cf)


def _ega_aperture_overlap(seg: int, off: int, count: int) -> bool:
    """Return True when a flat transfer touches the emulated EGA aperture.

    The Tandy presenter normally does not hit EGA planar memory, but this helper
    mirrors the existing replacement fast path so the refactor does not change
    behavior for synthetic tests or unusual states.
    """
    if count <= 0:
        return False
    start = (((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF
    end = start + count
    ega_start = EGA_CPU_APERTURE
    ega_end = EGA_CPU_APERTURE + EGA_PLANE_WINDOW
    return start < ega_end and end > ega_start


def _rep_movsw(cpu, count: int) -> None:
    """ASM-compatible REP MOVSW helper used by the 1010:3354 presenter."""
    count &= 0xFFFF
    if count == 0:
        cpu.s.cx = 0
        return

    byte_count = count * 2
    if not cpu.get_flag(DF):
        si = cpu.s.si & 0xFFFF
        di = cpu.s.di & 0xFFFF
        if si + byte_count <= 0x10000 and di + byte_count <= 0x10000 \
                and not (cpu.mem.ega_planar and (
                    _ega_aperture_overlap(cpu.s.ds, si, byte_count)
                    or _ega_aperture_overlap(cpu.s.es, di, byte_count)
                )):
            src = (((cpu.s.ds & 0xFFFF) << 4) + si) & 0xFFFFF
            dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
            if src + byte_count <= len(cpu.mem.data) and dst + byte_count <= len(cpu.mem.data):
                cpu.mem.data[dst:dst + byte_count] = cpu.mem.data[src:src + byte_count]
                cpu.s.si = (si + byte_count) & 0xFFFF
                cpu.s.di = (di + byte_count) & 0xFFFF
                cpu.s.cx = 0
                return

    delta = -2 if cpu.get_flag(DF) else 2
    for _ in range(count):
        cpu.mem.ww(cpu.s.es, cpu.s.di, cpu.mem.rw(cpu.s.ds, cpu.s.si))
        cpu.s.si = (cpu.s.si + delta) & 0xFFFF
        cpu.s.di = (cpu.s.di + delta) & 0xFFFF
    cpu.s.cx = 0



def _rep_movsb(cpu, count: int) -> None:
    """ASM-compatible REP MOVSB helper used by the 1010:375B Tandy blitter."""
    count &= 0xFFFF
    if count == 0:
        cpu.s.cx = 0
        return

    if not cpu.get_flag(DF):
        si = cpu.s.si & 0xFFFF
        di = cpu.s.di & 0xFFFF
        if si + count <= 0x10000 and di + count <= 0x10000 \
                and not (cpu.mem.ega_planar and (
                    _ega_aperture_overlap(cpu.s.ds, si, count)
                    or _ega_aperture_overlap(cpu.s.es, di, count)
                )):
            src = (((cpu.s.ds & 0xFFFF) << 4) + si) & 0xFFFFF
            dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
            if src + count <= len(cpu.mem.data) and dst + count <= len(cpu.mem.data):
                cpu.mem.data[dst:dst + count] = cpu.mem.data[src:src + count]
                cpu.s.si = (si + count) & 0xFFFF
                cpu.s.di = (di + count) & 0xFFFF
                cpu.s.cx = 0
                return

    delta = -1 if cpu.get_flag(DF) else 1
    for _ in range(count):
        cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.mem.rb(cpu.s.ds, cpu.s.si))
        cpu.s.si = (cpu.s.si + delta) & 0xFFFF
        cpu.s.di = (cpu.s.di + delta) & 0xFFFF
    cpu.s.cx = 0


def _rep_stosb(cpu, count: int) -> None:
    """ASM-compatible REP STOSB helper used by the 1010:375B Tandy blitter."""
    count &= 0xFFFF
    if count == 0:
        cpu.s.cx = 0
        return

    value = cpu.s.ax & 0xFF
    if not cpu.get_flag(DF):
        di = cpu.s.di & 0xFFFF
        if di + count <= 0x10000 and not (
                cpu.mem.ega_planar and _ega_aperture_overlap(cpu.s.es, di, count)
        ):
            dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
            if dst + count <= len(cpu.mem.data):
                cpu.mem.data[dst:dst + count] = bytes([value]) * count
                cpu.s.di = (di + count) & 0xFFFF
                cpu.s.cx = 0
                return

    delta = -1 if cpu.get_flag(DF) else 1
    for _ in range(count):
        cpu.mem.wb(cpu.s.es, cpu.s.di, value)
        cpu.s.di = (cpu.s.di + delta) & 0xFFFF
    cpu.s.cx = 0


def _xor_al_al(cpu) -> None:
    cpu.set_reg8(0, 0)
    cpu.set_logic_flags(0, 8)


def _tandy_next_scanline_di(cpu) -> None:
    """Mirror OVERKILL's packed Tandy/PCjr B800 row advance used by 1010:375B."""
    _add_reg16(cpu, 7, 0x2000)
    _test_word(cpu, cpu.s.di, 0x8000)
    if not cpu.get_flag(ZF):
        _add_reg16(cpu, 7, 0x80A0)

def _masked_word_composite_rows(cpu, *, words_per_row: int, row_add: int) -> None:
    """Composite Tandy masked words exactly like 1010:2E6E/2F81/2FB6 leaves."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    step = -2 if s.flags & DF else 2
    bx = row_add & 0xFFFF
    ax = s.ax & 0xFFFF

    for _ in range(rows):
        for _col in range(words_per_row):
            ax = mem.rw(ds, si)              # LODSW
            si = (si + step) & 0xFFFF
            ax = (ax & mem.rw(es, di)) & 0xFFFF
            ax = (ax | mem.rw(ds, si)) & 0xFFFF
            si_sum = si + 2                  # ADD SI,2
            si = si_sum & 0xFFFF
            mem.ww(es, di, ax)               # STOSW
            di = (di + step) & 0xFFFF

        di_sum = di + bx                     # ADD DI,BX; LOOP preserves flags.
        cpu.set_add_flags(di, bx, di_sum, 16)
        di = di_sum & 0xFFFF

    s.ax = ax
    s.bx = bx
    s.cx = 0
    s.si = si
    s.di = di


def _or_inverted_source_words_rows(cpu, *, words_per_row: int, row_add: int) -> None:
    """OR inverted source-mask words into ES:DI for Tandy layer/object leaves."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bx = row_add & 0xFFFF
    ax = s.ax & 0xFFFF

    for _ in range(rows):
        bx = row_add & 0xFFFF
        for _col in range(words_per_row):
            ax = mem.rw(ds, si)
            ax = (~ax) & 0xFFFF              # NOT AX, flags unaffected.
            value = (mem.rw(es, di) | ax) & 0xFFFF
            mem.ww(es, di, value)            # OR ES:[DI],AX
            cpu.set_logic_flags(value, 16)

            si_sum = si + 4
            si = si_sum & 0xFFFF
            cpu.set_add_flags((si - 4) & 0xFFFF, 4, si_sum, 16)

            di_sum = di + 2
            di = di_sum & 0xFFFF
            cpu.set_add_flags((di - 2) & 0xFFFF, 2, di_sum, 16)

        di_sum = di + bx
        cpu.set_add_flags(di, bx, di_sum, 16)
        di = di_sum & 0xFFFF

    s.ax = ax
    s.bx = bx
    s.cx = 0
    s.si = si
    s.di = di


def _strided_movsw_rows(cpu, *, words_per_row: int, row_add: int) -> None:
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    step = -2 if s.flags & DF else 2
    bx = row_add & 0xFFFF
    for _ in range(rows):
        for _col in range(words_per_row):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + step) & 0xFFFF
            di = (di + step) & 0xFFFF
        di_sum = di + bx
        cpu.set_add_flags(di, bx, di_sum, 16)
        di = di_sum & 0xFFFF
    s.bx = bx
    s.cx = 0
    s.si = si
    s.di = di


def _source_strided_movsw_rows(cpu, *, words_per_row: int, row_add: int) -> None:
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    step = -2 if s.flags & DF else 2
    bx = row_add & 0xFFFF
    for _ in range(rows):
        for _col in range(words_per_row):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + step) & 0xFFFF
            di = (di + step) & 0xFFFF
        si_sum = si + bx
        cpu.set_add_flags(si, bx, si_sum, 16)
        si = si_sum & 0xFFFF
    s.bx = bx
    s.cx = 0
    s.si = si
    s.di = di


def _fixed_di_strided_movsw_rows(cpu, *, words_per_row: int, row_add: int, rows: int) -> None:
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    step = -2 if s.flags & DF else 2
    bx = row_add & 0xFFFF

    for _row in range(rows):
        for _col in range(words_per_row):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + step) & 0xFFFF
            di = (di + step) & 0xFFFF
        di_sum = di + bx
        cpu.set_add_flags(di, bx, di_sum, 16)
        di = di_sum & 0xFFFF

    s.bx = bx
    s.si = si
    s.di = di


def _fixed_si_strided_movsw_rows(cpu, *, words_per_row: int, row_add: int, rows: int) -> None:
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    step = -2 if s.flags & DF else 2
    bx = row_add & 0xFFFF

    for _row in range(rows):
        for _col in range(words_per_row):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + step) & 0xFFFF
            di = (di + step) & 0xFFFF
        si_sum = si + bx
        cpu.set_add_flags(si, bx, si_sum, 16)
        si = si_sum & 0xFFFF

    s.bx = bx
    s.si = si
    s.di = di


def _restore_tandy_display_ds(cpu) -> None:
    cpu.s.ds = cpu.mem.rw(cpu.s.cs & 0xFFFF, TANDY_DISPLAY_SEGMENT_OFF)


def masked_sprite_composite_2e6e(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:2E6E, mode-2 eight-word masked sprite compositor."""
    if runtime.self_disable_if_patched(cpu, 0x2E6E, runtime.signature_2e6e, "overkill_tandy_masked_sprite_composite_2e6e"):
        return
    _masked_word_composite_rows(cpu, words_per_row=8, row_add=0x0058)
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()


def or_inverted_mask_2f40(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:2F40, mode-2 four-word inverted-mask OR compositor."""
    if runtime.self_disable_if_patched(cpu, 0x2F40, runtime.signature_2f40, "overkill_tandy_or_inverted_mask_2f40"):
        return
    _or_inverted_source_words_rows(cpu, words_per_row=4, row_add=0x0060)
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()


def or_inverted_mask_2ecb(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:2ECB, mode-2 eight-word inverted-mask OR compositor."""
    if runtime.self_disable_if_patched(cpu, 0x2ECB, runtime.signature_2ecb, "overkill_tandy_or_inverted_mask_2ecb"):
        return
    _or_inverted_source_words_rows(cpu, words_per_row=8, row_add=0x0058)
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()


def masked_sprite_composite_2f81(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:2F81, mode-2 four-word masked sprite compositor."""
    if runtime.self_disable_if_patched(cpu, 0x2F81, runtime.signature_2f81, "overkill_tandy_masked_sprite_composite_2f81"):
        return
    _masked_word_composite_rows(cpu, words_per_row=4, row_add=0x0060)
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()


def masked_compact_2fb6(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:2FB6, mode-2 compact two-word masked compositor."""
    if runtime.self_disable_if_patched(cpu, 0x2FB6, runtime.signature_2fb6, "overkill_tandy_masked_compact_2fb6"):
        return
    _masked_word_composite_rows(cpu, words_per_row=2, row_add=0x0064)
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()


def source_strided_copy_35aa(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:35AA, mode-2 source-strided object copy."""
    if runtime.self_disable_if_patched(cpu, 0x35AA, runtime.signature_35aa, "overkill_tandy_source_strided_copy_35aa"):
        return
    cs = cpu.s.cs & 0xFFFF
    cpu.s.es = cpu.mem.rw(cs, TANDY_DISPLAY_SEGMENT_OFF)
    cpu.s.ds = cpu.mem.rw(cs, TANDY_SOURCE_SEGMENT_OFF)
    cpu.s.bx = 0x0058
    cpu.s.cx = 0x0010
    _source_strided_movsw_rows(cpu, words_per_row=8, row_add=0x0058)
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()


def split_present_copy_34ad(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:34AD, mode-2 split object-present copy.

    The original optionally calls 34C5 for the first visible half, then reloads
    DI/SI from the object stack frame and tail-falls into 34C5 for the second
    half.  The synthetic CALL return word must remain exact.
    """
    if runtime.self_disable_if_patched(cpu, 0x34AD, runtime.signature_34ad, "overkill_tandy_split_present_copy_34ad"):
        return

    _cmp_word(cpu, cpu.s.di & 0xFFFF, OFFSCREEN_DESTINATION)
    if (cpu.s.di & 0xFFFF) != OFFSCREEN_DESTINATION:
        _call_hook_like_near_call(cpu, lambda c: strided_copy_34c5(c, runtime), 0x34B5)
        if cpu.s.ip != 0x34B5:
            raise RuntimeError(f"34C5 first half returned to unexpected IP {cpu.s.ip:04X}")

    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    cpu.s.di = cpu.mem.rw(ss, (bp + 0x10) & 0xFFFF)
    cpu.s.si = cpu.mem.rw(ss, (bp + 0x0E) & 0xFFFF)
    _add_reg16(cpu, 6, 0x0140)
    _cmp_word(cpu, cpu.s.di & 0xFFFF, OFFSCREEN_DESTINATION)
    if (cpu.s.di & 0xFFFF) == OFFSCREEN_DESTINATION:
        cpu.s.ip = cpu.pop()
        return
    strided_copy_34c5(cpu, runtime)


def strided_copy_34c5(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:34C5, 16-row eight-word strided copy helper."""
    if runtime.self_disable_if_patched(cpu, 0x34C5, runtime.signature_34c5, "overkill_tandy_strided_copy_34c5"):
        return
    cpu.s.bx = 0x0058
    cpu.s.cx = 0x0010
    _strided_movsw_rows(cpu, words_per_row=8, row_add=0x0058)
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()


def small_strided_copy_34d8(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:34D8, mode-2 16-row four-word object-present copy."""
    if runtime.self_disable_if_patched(cpu, 0x34D8, runtime.signature_34d8, "overkill_tandy_small_strided_copy_34d8"):
        return
    _cmp_word(cpu, cpu.s.di & 0xFFFF, OFFSCREEN_DESTINATION)
    if (cpu.s.di & 0xFFFF) == OFFSCREEN_DESTINATION:
        cpu.s.ip = cpu.pop()
        return
    cpu.s.bx = 0x0060
    _fixed_di_strided_movsw_rows(cpu, words_per_row=4, row_add=0x0060, rows=16)
    cpu.s.ip = cpu.pop()


def tiny_strided_copy_3542(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:3542, mode-2 8-row two-word object-present copy."""
    if runtime.self_disable_if_patched(cpu, 0x3542, runtime.signature_3542, "overkill_tandy_tiny_strided_copy_3542"):
        return
    _cmp_word(cpu, cpu.s.di & 0xFFFF, OFFSCREEN_DESTINATION)
    if (cpu.s.di & 0xFFFF) == OFFSCREEN_DESTINATION:
        cpu.s.ip = cpu.pop()
        return
    cpu.s.bx = 0x0064
    _fixed_di_strided_movsw_rows(cpu, words_per_row=2, row_add=0x0064, rows=8)
    cpu.s.ip = cpu.pop()


def _draw_source_copy_body(cpu, *, si: int, di: int) -> None:
    cs = cpu.s.cs & 0xFFFF
    cpu.s.es = cpu.mem.rw(cs, TANDY_DISPLAY_SEGMENT_OFF)
    cpu.s.ds = cpu.mem.rw(cs, TANDY_SOURCE_SEGMENT_OFF)
    cpu.s.si = si & 0xFFFF
    cpu.s.di = di & 0xFFFF
    cpu.s.bx = 0x0058
    cpu.s.cx = 0x0010
    _source_strided_movsw_rows(cpu, words_per_row=8, row_add=0x0058)
    _restore_tandy_display_ds(cpu)


def draw_tiny_object_3657(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:3657, mode-2 small draw target."""
    if runtime.self_disable_if_patched(cpu, 0x3657, runtime.signature_3657, "overkill_tandy_draw_tiny_object_3657"):
        return
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    _call_hook_like_near_call(cpu, runtime.object_row_address_from_mode_dispatch_5a36, 0x365A)
    if cpu.s.ip != 0x365A:
        raise RuntimeError(f"5A36 replacement returned to unexpected IP {cpu.s.ip:04X}")
    ax = cpu.s.ax & 0xFFFF
    mem.ww(ss, (bp + 0x0C) & 0xFFFF, ax)
    _cmp_word(cpu, ax, OFFSCREEN_DESTINATION)
    if ax == OFFSCREEN_DESTINATION:
        cpu.s.ip = cpu.pop()
        return
    row_sum = ax + mem.rw(ds, WORK_BUFFER_CURSOR_OFF)
    cpu.s.ax = row_sum & 0xFFFF
    cpu.set_add_flags(ax, mem.rw(ds, WORK_BUFFER_CURSOR_OFF), row_sum, 16)
    mem.ww(ss, (bp + 0x0C) & 0xFFFF, cpu.s.ax)
    cs = cpu.s.cs & 0xFFFF
    cpu.s.es = mem.rw(cs, TANDY_DISPLAY_SEGMENT_OFF)
    cpu.s.ds = mem.rw(cs, TANDY_SOURCE_SEGMENT_OFF)
    cpu.s.si = cpu.s.ax
    cpu.s.di = mem.rw(ss, (bp + 0x0E) & 0xFFFF)
    cpu.s.bx = 0x0064
    _fixed_si_strided_movsw_rows(cpu, words_per_row=2, row_add=0x0064, rows=8)
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()


def draw_split_object_356c(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:356C, mode-2 split draw target.

    This is the draw-side sibling of 1010:34AD.  It row-addresses the first
    half, nudges X by 10h, row-addresses the second half, then draws both visible
    halves into the Tandy work buffer.  The second synthetic CALL returns to
    358D, not the later branch target, because stack scratch below SP is visible
    to hook verification.
    """
    if runtime.self_disable_if_patched(cpu, 0x356C, runtime.signature_356c, "overkill_tandy_draw_split_object_356c"):
        return

    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    _call_hook_like_near_call(cpu, runtime.object_row_address_from_mode_dispatch_5a36, 0x356F)
    if cpu.s.ip != 0x356F:
        raise RuntimeError(f"5A36 replacement returned to unexpected IP {cpu.s.ip:04X}")
    ax = cpu.s.ax & 0xFFFF
    mem.ww(ss, (bp + 0x0C) & 0xFFFF, ax)
    _cmp_word(cpu, ax, OFFSCREEN_DESTINATION)
    if ax != OFFSCREEN_DESTINATION:
        row_sum = ax + mem.rw(ds, WORK_BUFFER_CURSOR_OFF)
        cpu.s.ax = row_sum & 0xFFFF
        cpu.set_add_flags(ax, mem.rw(ds, WORK_BUFFER_CURSOR_OFF), row_sum, 16)
        mem.ww(ss, (bp + 0x0C) & 0xFFFF, cpu.s.ax)
        _draw_source_copy_body(cpu, si=cpu.s.ax, di=mem.rw(ss, (bp + 0x0E) & 0xFFFF))
        ds = cpu.s.ds & 0xFFFF

    _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 0x0010)
    _call_hook_like_near_call(cpu, runtime.object_row_address_from_mode_dispatch_5a36, 0x358D)
    if cpu.s.ip != 0x358D:
        raise RuntimeError(f"5A36 replacement returned to unexpected IP {cpu.s.ip:04X}")
    ax = cpu.s.ax & 0xFFFF
    mem.ww(ss, (bp + 0x10) & 0xFFFF, ax)
    _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 0x0010)
    _cmp_word(cpu, ax, OFFSCREEN_DESTINATION)
    if ax != OFFSCREEN_DESTINATION:
        ds = cpu.s.ds & 0xFFFF
        row_sum = ax + mem.rw(ds, WORK_BUFFER_CURSOR_OFF)
        cpu.s.ax = row_sum & 0xFFFF
        cpu.set_add_flags(ax, mem.rw(ds, WORK_BUFFER_CURSOR_OFF), row_sum, 16)
        mem.ww(ss, (bp + 0x10) & 0xFFFF, cpu.s.ax)
        di = (mem.rw(ss, (bp + 0x0E) & 0xFFFF) + 0x0140) & 0xFFFF
        _draw_source_copy_body(cpu, si=cpu.s.ax, di=di)
    cpu.s.ip = cpu.pop()


def draw_object_block_35cc(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:35CC, row-address plus source-strided copy draw target."""
    if runtime.self_disable_if_patched(cpu, 0x35CC, runtime.signature_35cc, "overkill_tandy_draw_object_block_35cc"):
        return

    _call_hook_like_near_call(cpu, runtime.object_row_address_from_mode_dispatch_5a36, 0x35CF)
    if cpu.s.ip != 0x35CF:
        raise RuntimeError(f"5A36 replacement returned to unexpected IP {cpu.s.ip:04X}")

    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    ax = cpu.s.ax & 0xFFFF

    cpu.mem.ww(ss, (bp + 0x0C) & 0xFFFF, ax)
    _cmp_word(cpu, ax, OFFSCREEN_DESTINATION)
    if ax == OFFSCREEN_DESTINATION:
        cpu.s.ip = cpu.pop()
        return

    row_sum = ax + cpu.mem.rw(ds, WORK_BUFFER_CURSOR_OFF)
    cpu.s.ax = row_sum & 0xFFFF
    cpu.set_add_flags(ax, cpu.mem.rw(ds, WORK_BUFFER_CURSOR_OFF), row_sum, 16)
    cpu.mem.ww(ss, (bp + 0x0C) & 0xFFFF, cpu.s.ax)
    cpu.s.si = cpu.s.ax
    cpu.s.di = cpu.mem.rw(ss, (bp + 0x0E) & 0xFFFF)
    cpu.s.es = cpu.mem.rw(cs, TANDY_DISPLAY_SEGMENT_OFF)
    cpu.s.ds = cpu.mem.rw(cs, TANDY_SOURCE_SEGMENT_OFF)
    cpu.s.bx = 0x0060
    _fixed_si_strided_movsw_rows(cpu, words_per_row=4, row_add=0x0060, rows=16)
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()



def postcopy_scaled_blit_375b(cpu) -> None:
    """OVERKILL 1010:375B Tandy post-copy scaled blitter.

    This runtime-patched leaf is reached from the shared 1010:58DF post-copy
    wait loop through the CS:95BC video-mode dispatch table when the game is in
    mode 2 (Tandy/PCjr). It copies rows from the work buffer at DS:SI to the
    B800 display segment at ES:DI, using the same vertical accumulator fields as
    the mode-0 1010:497A blitter but the Tandy row stride and X scaling.

    The routine is a normal near-return target. It deliberately preserves the
    original scratch stack writes from PUSH/POP CX, the accumulator fields
    CS:5901/5903/5905, and the final flags from the last clear-row STOSB setup.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    mem.ww(cs, 0x5903, 0)
    cpu.s.di = mem.rw(cs, 0x58F9)
    cpu.s.si = mem.rw(cs, 0x58FB)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    cpu.s.bp = mem.rw(cs, 0x58FF)
    cpu.s.bp = cpu.shift(4, cpu.s.bp, 1, 16)
    cpu.s.bp = cpu.shift(4, cpu.s.bp, 1, 16)

    _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
    if not cpu.get_flag(ZF):
        cpu.s.ax = cpu.s.bp & 0xFFFF
        _dec_reg16_preserve_cf(cpu, 1)
        result = (cpu.s.ax & 0xFFFF) * (cpu.s.cx & 0xFFFF)
        cpu.s.ax = result & 0xFFFF
        cpu.s.dx = (result >> 16) & 0xFFFF
        carry = cpu.s.dx != 0
        cpu.set_flag(CF, carry)
        cpu.set_flag(0x0800, carry)
        _inc_reg16_preserve_cf(cpu, 1)
        _add_reg16(cpu, 6, cpu.s.ax)

    cpu.push(cpu.s.cx)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    _sub_reg16(cpu, 1, mem.rw(cs, 0x5901))
    _test_word(cpu, cpu.s.cx, cpu.s.cx)
    if not cpu.get_flag(0x0080):
        cpu.s.cx = cpu.shift(5, cpu.s.cx, 1, 16)
        if cpu.s.cx != 0:
            _dec_reg16_preserve_cf(cpu, 1)
            if cpu.s.cx != 0:
                while cpu.s.cx != 0:
                    _tandy_next_scanline_di(cpu)
                    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
            _xor_al_al(cpu)
            cpu.s.cx = cpu.s.bp & 0xFFFF
            _rep_stosb(cpu, cpu.s.cx)
            _sub_reg16(cpu, 7, cpu.s.bp)
            _tandy_next_scanline_di(cpu)
    cpu.s.cx = cpu.pop()

    while True:
        cpu.s.ax = mem.rw(cs, 0x5901)
        _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x58FD))
        if cpu.get_flag(ZF):
            copy_this_row = True
        else:
            _add_mem_word(cpu, cs, 0x5903, cpu.s.ax)
            cpu.s.ax = mem.rw(cs, 0x58FD)
            _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x5903))
            copy_this_row = (not cpu.get_flag(CF)) and (not cpu.get_flag(ZF))
            if not copy_this_row:
                _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
                if cpu.get_flag(ZF):
                    _add_reg16(cpu, 6, cpu.s.bp)
                else:
                    _sub_reg16(cpu, 6, cpu.s.bp)
                cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
                if cpu.s.cx != 0:
                    continue
                break

        if copy_this_row:
            _sub_mem_word(cpu, cs, 0x5903, cpu.s.ax)
            cpu.push(cpu.s.cx)
            cpu.s.cx = cpu.s.bp & 0xFFFF
            _rep_movsb(cpu, cpu.s.cx)
            _sub_reg16(cpu, 7, cpu.s.bp)
            _tandy_next_scanline_di(cpu)
            _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
            if not cpu.get_flag(ZF):
                _sub_reg16(cpu, 6, cpu.s.bp)
                _sub_reg16(cpu, 6, cpu.s.bp)
            cpu.s.cx = cpu.pop()
            cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
            if cpu.s.cx != 0:
                continue
            break

    _xor_al_al(cpu)
    cpu.s.cx = cpu.s.bp & 0xFFFF
    _rep_stosb(cpu, cpu.s.cx)
    cpu.s.ip = cpu.pop()

def present_tandy_frame_3354(cpu) -> None:
    """OVERKILL 1010:3354, mode-2 Tandy frame-present blit.

    The Tandy/PCjr presenter copies the game's 208-pixel-wide work buffer into
    the 320x200x16 packed Tandy aperture using the four-bank address pattern:

        screen offset = (y & 3) * 2000h + (y >> 2) * 00A0h + x_byte

    It copies 52 words for each of 192 rows, starting at destination 00A0h, then
    restores DS from CS:[9596] and returns near.
    """
    cs = cpu.s.cs & 0xFFFF
    cpu.s.si = cpu.mem.rw(cpu.s.ds, WORK_BUFFER_CURSOR_OFF)
    cpu.s.es = cpu.mem.rw(cs, TANDY_VIDEO_SEGMENT_OFF)
    cpu.s.ds = cpu.mem.rw(cs, TANDY_SOURCE_SEGMENT_OFF)
    cpu.s.bx = 0x0034
    cpu.s.di = 0x00A0
    cpu.s.bp = 0x00C0
    while True:
        cpu.s.cx = cpu.s.bx & 0xFFFF
        _rep_movsw(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, 0x0068)
        _add_reg16(cpu, 7, 0x2000)
        _test_word(cpu, cpu.s.di, 0x8000)
        if not cpu.get_flag(ZF):
            _add_reg16(cpu, 7, 0x80A0)
        _dec_reg16_preserve_cf(cpu, 5)
        if cpu.get_flag(ZF):
            break
    _restore_tandy_display_ds(cpu)
    cpu.s.ip = cpu.pop()


# Startup Tandy packed-pixel asset expansion ---------------------------------
#
# These routines run while OVERKILL materializes graphics assets into the
# mode-2/Tandy-packed buffers consumed later by the runtime draw primitives
# above.  They belong with the Tandy renderer because the output format is
# Tandy-specific, but they remain separate from shared layer-sprite dispatch.

def _tandy_cell_33dd_core(cpu) -> None:
    """Fast lifted body of one 1010:33DD Tandy source cell expansion.

    The original calls 344B four times.  Each call rotates two bits from
    DH/DL/AH/AL into CL, optionally masks transparent nibbles into CH, and then
    33DD stores the four CL/CH pairs as two Tandy packed words.  At the 33DD
    boundary all rotate/transparency-test flags have been overwritten by the
    final ``CMP CS:[0BD6],0``, so this can use direct bit arithmetic while still
    matching interpreted ASM at the hook continuation.
    """
    s = cpu.s
    mem = cpu.mem
    rb, rw, wb = mem.rb, mem.rw, mem.wb
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    width = rw(cs, 0x5B9C)
    si = s.si & 0xFFFF

    s.bx = width
    al = rb(ds, si)
    ah = rb(ds, (si + s.bx) & 0xFFFF)
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1
    dl = rb(ds, (si + s.bx) & 0xFFFF)
    old_bx = s.bx
    s.bx = (s.bx + width) & 0xFFFF
    cpu.set_add_flags(old_bx, width, old_bx + width, 16)
    dh = rb(ds, (si + s.bx) & 0xFFFF)

    bd6 = rw(cs, 0x0BD6)
    transparent_color = rb(cs, 0x0000) if bd6 else 0
    entry_ch = (s.cx >> 8) & 0xFF

    cls = []
    chs = []
    for k in (0, 2, 4, 6):
        b = k + 1
        cl = ((((dh >> b) & 1) << 7) | (((dl >> b) & 1) << 6)
              | (((ah >> b) & 1) << 5) | (((al >> b) & 1) << 4)
              | (((dh >> k) & 1) << 3) | (((dl >> k) & 1) << 2)
              | (((ah >> k) & 1) << 1) | ((al >> k) & 1))
        if bd6:
            ch = 0
            if (cl & 0x0F) == transparent_color:
                ch |= 0x0F
                cl &= 0xF0
            if ((cl >> 4) & 0x0F) == transparent_color:
                ch |= 0xF0
                cl &= 0x0F
        else:
            ch = entry_ch
        cls.append(cl & 0xFF)
        chs.append(ch & 0xFF)

    c0, c1, c2, c3 = cls
    m0, m1, m2, m3 = chs
    wb(cs, 0x5B95, c0); wb(cs, 0x5B99, m0)
    wb(cs, 0x5B94, c1); wb(cs, 0x5B98, m1)
    wb(cs, 0x5B97, c2); wb(cs, 0x5B9B, m2)
    wb(cs, 0x5B96, c3); wb(cs, 0x5B9A, m3)

    old_si = s.si & 0xFFFF
    s.si = (old_si + 1) & 0xFFFF
    old_cf = cpu.get_flag(CF)
    cpu.set_add_flags(old_si, 1, old_si + 1, 16)  # INC SI, preserving CF.
    cpu.set_flag(CF, old_cf)

    cpu.set_sub_flags(bd6, 0, bd6, 16)
    if bd6 != 0:
        s.ax = rw(cs, 0x5B9A)
        _stosw(cpu)
    s.ax = rw(cs, 0x5B96)
    _stosw(cpu)

    cpu.set_sub_flags(bd6, 0, bd6, 16)
    if bd6 != 0:
        s.ax = rw(cs, 0x5B98)
        _stosw(cpu)
    s.ax = rw(cs, 0x5B94)
    _stosw(cpu)

    s.bx = ((ah << 8) | al) if bd6 else (width * 3) & 0xFFFF
    s.cx = (((m3 if bd6 else entry_ch) << 8) | c3) & 0xFFFF
    s.dx = ((dh << 8) | dl) & 0xFFFF

def expand_tandy_cell_33dd(cpu):
    """OVERKILL 1010:33DD Tandy packed-pixel cell expander."""
    _tandy_cell_33dd_core(cpu)
    cpu.s.ip = cpu.pop()

def expand_tandy_block_33b2(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:33B2 hot Tandy startup block/list expansion."""
    if runtime.self_disable_if_patched(cpu, 0x33B2, runtime.signature_33b2, "overkill_expand_tandy_block_33b2"):
        return

    s = cpu.s
    if s.flags & ZF:
        s.ip = 0x44AA
        return

    cs = s.cs & 0xFFFF
    height = cpu.mem.rw(cs, 0x5B9E)
    width = cpu.mem.rw(cs, 0x5B9C)
    entry_sp = s.sp & 0xFFFF
    wrote_call_scratch = False

    outer = height
    while outer != 0:
        col = width
        while col != 0:
            wrote_call_scratch = True
            s.cx = col
            _tandy_cell_33dd_core(cpu)
            col = (col - 1) & 0xFFFF  # LOOP column, flags unaffected.

        si = (s.si + width + width) & 0xFFFF
        cpu.set_add_flags(si, width, si + width, 16)
        s.si = (si + width) & 0xFFFF
        outer = (outer - 1) & 0xFFFF  # LOOP row, flags unaffected.

    if wrote_call_scratch:
        ss = s.ss & 0xFFFF
        cpu.mem.ww(ss, (entry_sp - 6) & 0xFFFF, 0x33C6)
        cpu.mem.ww(ss, (entry_sp - 4) & 0xFFFF, 0x0001)
        cpu.mem.ww(ss, (entry_sp - 2) & 0xFFFF, 0x0001)

    s.cx = 0
    s.ip = 0x33AF
