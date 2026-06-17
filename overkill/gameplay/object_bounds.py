"""Object bounds / tile-probe tail for the OVERKILL object runtime.

Architecture layer: **lifted**.  The AD60 bounds-tile tail (and its AD5A
prelude hook) plus the 5073/505B tile probe/lookup helpers.  Shared by both the
object behaviours and the movement behaviours (drift/chase) that test the tile
under an object after it moves, so it sits in its own module below both.  Bodies
relocated verbatim; conservative names.
"""
from __future__ import annotations

from dos_re.cpu import CF, ZF
from overkill.asm import _add_mem_word, _add_reg16, _cmp_word
from overkill.gameplay.object_deactivation import _run_deactivate_bd17_observed
from overkill.recovered.adapters.collision_adapter import (
    run_tile_lookup_505b_body, run_tile_probe_5073_body,
)
from overkill.recovered.views.object_slots import OFF_DRAW_LAYER, OFF_LOGIC_ID, OFF_X, OFF_Y



SIG_OBJECT_BOUNDS_TILE_PRELUDE_AD5A = bytes.fromhex(
    "a1 78 a2 01 46 02 83 7e 02 08 73 03 e9 ae 0f"
)


def _run_object_bounds_tile_tail_ad60(cpu, *, parent: str, chain: str, cx_value: int, add_a278_to_x: bool) -> None:
    """Shared AD5A/AD60 bounds + optional tile-probe tail used by object behaviors."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    if add_a278_to_x:
        cpu.s.ax = mem.rw(ds, 0xA278)
        _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, cpu.s.ax)

    x = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    _cmp_word(cpu, x, 0x0008)
    if x < 0x0008:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AD60", cx_value=cx_value, pop_return=False)
        cpu.s.ip = cpu.pop()
        return
    _cmp_word(cpu, x, 0x00E0)
    if x > 0x00E0:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AD60", cx_value=cx_value, pop_return=False)
        cpu.s.ip = cpu.pop()
        return
    y = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    _cmp_word(cpu, y, 0x00C8)
    if y > 0x00C8:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AD60", cx_value=cx_value, pop_return=False)
        cpu.s.ip = cpu.pop()
        return
    draw_layer = mem.rw(ss, (bp + OFF_DRAW_LAYER) & 0xFFFF)
    _cmp_word(cpu, draw_layer, 0x0002)
    if draw_layer != 0x0002:
        cpu.s.ip = cpu.pop()
        return
    logic_id = mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
    for good in (0x0002, 0x0004, 0x000C, 0x0005, 0x0006, 0x0009, 0x0008):
        _cmp_word(cpu, logic_id, good)
        if logic_id == good:
            break
    else:
        cpu.s.ip = cpu.pop()
        return

    bdac = mem.rw(ds, 0xBDAC)
    _cmp_word(cpu, bdac, 0x0001)
    if bdac == 0x0001:
        cpu.s.ip = cpu.pop()
        return
    _run_tile_probe_5073(cpu)
    _add_reg16(cpu, 3, 0x000D)
    mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xADBF)
    _run_tile_lookup_505b(cpu)
    if not cpu.get_flag(ZF):
        old_al = cpu.get_reg8(0)
        old_cf = cpu.get_flag(CF)
        result_full = old_al - 1
        cpu.set_reg8(0, result_full & 0xFF)
        cpu.set_sub_flags(old_al, 1, result_full, 8)
        cpu.set_flag(CF, old_cf)
        if cpu.get_reg8(0) == 0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> ADC1", cx_value=cx_value, pop_return=False)
            cpu.s.ip = cpu.pop()
            return
    cpu.s.ip = cpu.pop()


def run_object_bounds_tile_prelude_ad5a(cpu, self_disable_if_patched) -> None:
    """Lift 1010:AD5A, the A278-relative prelude to the AD60 bounds/tile tail.

    This is object-runtime glue, not a distinct behaviour: AD5A adds the current
    frame scroll/X delta at DS:A278 to SS:[BP+02], then falls directly into the
    already lifted AD60 bounds/tile/deactivation tail.
    """
    if self_disable_if_patched(
        cpu,
        0xAD5A,
        SIG_OBJECT_BOUNDS_TILE_PRELUDE_AD5A,
        "overkill_object_bounds_tile_prelude_ad5a",
    ):
        return

    _run_object_bounds_tile_tail_ad60(
        cpu,
        parent="1010:AD5A",
        chain="AD5A",
        cx_value=cpu.s.cx & 0xFFFF,
        add_a278_to_x=True,
    )


def _run_tile_probe_5073(cpu) -> None:
    """Run 1010:5073 without consuming a near-call return word.

    Older lifted parent tails need the body in-place rather than as a hook
    boundary.  Delegate to the same recovered adapter as the public hook so the
    tile-offset formula has one canonical implementation.
    """
    run_tile_probe_5073_body(cpu, pop_return=False)


def _run_tile_lookup_505b(cpu) -> None:
    """Run 1010:505B without consuming a near-call return word.

    Older lifted parent tails need the body in-place rather than as a hook
    boundary.  Delegate to the same recovered adapter as the public hook so the
    raw-tile -> class-byte mapping has one canonical implementation.
    """
    run_tile_lookup_505b_body(cpu, pop_return=False)
