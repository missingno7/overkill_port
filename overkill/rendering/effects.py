"""OVERKILL small frame-effect rendering helpers.

These routines are neither gameplay object behaviour nor low-level sprite
compositors.  They draw short screen-space effects driven by frame state.  Hook
wrappers in ``overkill/hooks.py`` keep the original CS:IP boundary visible.
"""
from __future__ import annotations

from overkill.asm import (
    _add_reg16,
    _cmp_byte,
    _cmp_word,
    _inc_mem_word_preserve_cf,
    _inc_reg16_preserve_cf,
    _sub_reg16,
    _test_word,
)
from overkill.rendering.coordinates import coordinate_ax_to_di_5a00
from dos_re.cpu import ZF

SIG_FRAME_EFFECT_SLASH_77F6 = bytes.fromhex(
    "b0 1d b4 5f e8 03 e2 89 3e dc 95 8b 0e 7a a9 d1 e9 e3 02 eb 03"
)
SIG_FRAME_EFFECT_GATE_77C5 = bytes.fromhex(
    "83 3e 7c a9 01 74 01 c3 83 3e 84 23 03 73 ea "
    "83 3e 7a a9 58 74 d7 ff 06 7a a9 55 e8 13 00 "
    "2e 83 3e bc 95 01 75 09 e8 31 d9 e8 05 00 e8 2b d9 5d c3"
)


def _out_al(cpu) -> None:
    if cpu.port_writer:
        cpu.port_writer(cpu, cpu.s.dx & 0xFFFF, cpu.get_reg8(0), 8)


def _mode2_tandy_advance_two_rows(cpu, *, value0: int, value1: int) -> None:
    es = cpu.s.es & 0xFFFF
    di = cpu.s.di & 0xFFFF
    cpu.mem.ww(es, di, value0 & 0xFFFF)
    cpu.mem.ww(es, (di + 2) & 0xFFFF, value1 & 0xFFFF)
    _test_word(cpu, cpu.s.di, 0x6000)
    if cpu.get_flag(ZF):
        _add_reg16(cpu, 7, 0x7F60)
    _sub_reg16(cpu, 7, 0x2000)
    _test_word(cpu, cpu.s.di, 0x6000)
    if cpu.get_flag(ZF):
        _add_reg16(cpu, 7, 0x7F60)
    _sub_reg16(cpu, 7, 0x2000)


def _mode0_cga_advance_two_rows(cpu, *, value: int) -> None:
    cpu.mem.ww(cpu.s.es & 0xFFFF, cpu.s.di & 0xFFFF, value & 0xFFFF)
    cpu.s.ax = 0x2000
    _test_word(cpu, cpu.s.ax, cpu.s.di)
    if not cpu.get_flag(ZF):
        cpu.s.ax = 0xE050
    _sub_reg16(cpu, 7, cpu.s.ax)
    cpu.s.ax = 0x2000
    _test_word(cpu, cpu.s.ax, cpu.s.di)
    if not cpu.get_flag(ZF):
        cpu.s.ax = 0xE050
    _sub_reg16(cpu, 7, cpu.s.ax)


def _mode1_ega_draw(cpu, *, fill: bool) -> None:
    cpu.s.dx = 0x03C4
    cpu.set_reg8(0, 0x02)
    _out_al(cpu)
    _inc_reg16_preserve_cf(cpu, 2)  # INC DX
    if fill:
        for mask, value in ((0x01, 0x30), (0x02, 0x7C), (0x04, 0xFF), (0x08, 0xFE)):
            cpu.set_reg8(0, mask)
            _out_al(cpu)
            cpu.mem.wb(cpu.s.es & 0xFFFF, cpu.s.di & 0xFFFF, value)
    else:
        cpu.set_reg8(0, 0x0F)
        _out_al(cpu)
        cpu.mem.wb(cpu.s.es & 0xFFFF, cpu.s.di & 0xFFFF, 0x00)
    _sub_reg16(cpu, 7, 0x0028)
    _sub_reg16(cpu, 7, 0x0028)


def _restore_ega_map_mask(cpu) -> None:
    cpu.s.dx = 0x03C4
    cpu.set_reg8(0, 0x02)
    _out_al(cpu)
    _inc_reg16_preserve_cf(cpu, 2)
    cpu.set_reg8(0, 0x0F)
    _out_al(cpu)



def run_frame_effect_gate_77c5(
    cpu,
    self_disable_if_patched,
    call_slash_77f6,
    call_page_toggle_511f,
) -> None:
    """Lift 1010:77C5, the finite per-frame slash/effect gate.

    This helper owns the effect state at DS:A97A/A97C and composes the already
    lifted 77F6 column renderer.  In normal Tandy gameplay CS:95BC is 2, so the
    path is a single 77F6 draw after DS:A97A increments; the EGA-only page-toggle
    branch remains represented by explicit 511F calls rather than by a semantic
    renderer model.
    """
    if self_disable_if_patched(cpu, 0x77C5, SIG_FRAME_EFFECT_GATE_77C5, "overkill_frame_effect_gate_77c5"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    v_a97c = mem.rw(ds, 0xA97C)
    _cmp_word(cpu, v_a97c, 0x0001)
    if v_a97c != 0x0001:
        s.ip = cpu.pop()
        return

    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, 0x0003)
    if v2384 >= 0x0003:
        mem.ww(ds, 0xA97C, 0x0000)
        s.ip = cpu.pop()
        return

    v_a97a = mem.rw(ds, 0xA97A)
    _cmp_word(cpu, v_a97a, 0x0058)
    if v_a97a == 0x0058:
        v98c0 = mem.rb(ds, 0x98C0)
        _cmp_byte(cpu, v98c0, 0x00)
        if v98c0 != 0:
            mem.wb(ds, 0xBEFF, 0x0C)
        mem.ww(ds, 0xA97C, 0x0000)
        s.ip = cpu.pop()
        return

    _inc_mem_word_preserve_cf(cpu, ds, 0xA97A)
    saved_bp = s.bp & 0xFFFF
    cpu.push(saved_bp)
    call_slash_77f6(0x77E3)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x77E3):
        raise RuntimeError(f"77C5 expected 77F6 to return to 77E3, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    mode = mem.rw(cs, 0x95BC)
    _cmp_word(cpu, mode, 0x0001)
    if mode == 0x0001:
        call_page_toggle_511f(0x77EE)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x77EE):
            raise RuntimeError(f"77C5 expected 511F to return to 77EE, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
        call_slash_77f6(0x77F1)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x77F1):
            raise RuntimeError(f"77C5 expected 77F6 to return to 77F1, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")
        call_page_toggle_511f(0x77F4)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x77F4):
            raise RuntimeError(f"77C5 expected 511F to return to 77F4, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    s.bp = cpu.pop()
    if (s.bp & 0xFFFF) != saved_bp:
        raise RuntimeError(f"77C5 BP stack imbalance: restored {s.bp & 0xFFFF:04X}, expected {saved_bp:04X}")
    s.ip = cpu.pop()

def run_frame_effect_slash_77f6(cpu, self_disable_if_patched) -> None:
    """Lift 1010:77F6, the short vertical frame-effect clear/draw loop.

    The caller owns the effect state (77C5/77DF).  This helper draws the current
    slash/curtain column from DS:A97A into the active video work segment, then
    clears the rest of the column.  It supports the same CGA/EGA/Tandy mode
    branches as the original code; cold-start attract coverage currently uses
    the Tandy branch.
    """
    if self_disable_if_patched(cpu, 0x77F6, SIG_FRAME_EFFECT_SLASH_77F6, "overkill_frame_effect_slash_77f6"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    cpu.set_reg8(0, 0x1D)
    cpu.set_reg8(4, 0x5F)
    cpu.push(0x77FD)
    coordinate_ax_to_di_5a00(cpu)
    if s.ip != 0x77FD:
        raise RuntimeError(f"77F6 coordinate helper returned to {s.ip:04X}, expected 77FD")

    mem.ww(ds, 0x95DC, s.di & 0xFFFF)
    s.cx = mem.rw(ds, 0xA97A)
    s.cx = cpu.shift(5, s.cx, 1, 16)  # SHR CX,1

    mode = mem.rw(cs, 0x95BC) & 0xFFFF

    while s.cx != 0:
        cx_saved = s.cx & 0xFFFF
        cpu.push(cx_saved)
        s.es = mem.rw(cs, 0x95A4)
        _cmp_word(cpu, mode, 0)
        if mode == 0:
            _mode0_cga_advance_two_rows(cpu, value=0xA02F)
        else:
            _cmp_word(cpu, mode, 1)
            if mode == 1:
                _mode1_ega_draw(cpu, fill=True)
            else:
                _mode2_tandy_advance_two_rows(cpu, value0=0xFFCE, value1=0xC4EE)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF

    s.cx = 0x002C
    s.ax = mem.rw(ds, 0xA97A)
    s.ax = cpu.shift(5, s.ax, 1, 16)  # SHR AX,1
    _sub_reg16(cpu, 1, s.ax)

    while s.cx != 0:
        cx_saved = s.cx & 0xFFFF
        cpu.push(cx_saved)
        s.es = mem.rw(cs, 0x95A4)
        _cmp_word(cpu, mode, 0)
        if mode == 0:
            _mode0_cga_advance_two_rows(cpu, value=0x0000)
        else:
            _cmp_word(cpu, mode, 1)
            if mode == 1:
                _mode1_ega_draw(cpu, fill=False)
            else:
                _mode2_tandy_advance_two_rows(cpu, value0=0x0000, value1=0x0000)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF

    _cmp_word(cpu, mode, 1)
    if mode == 1:
        _restore_ega_map_mask(cpu)

    v_a97a = mem.rw(ds, 0xA97A)
    _cmp_word(cpu, v_a97a, 0x0010)
    if v_a97a < 0x0010:
        v_a97c = mem.rw(ds, 0xA97C)
        _cmp_word(cpu, v_a97c, 0x0001)
        if v_a97c != 0x0001:
            _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
            if mem.rb(ds, 0x98C0) != 0:
                mem.wb(ds, 0xBEFF, 0x0A)

    s.ip = cpu.pop()
