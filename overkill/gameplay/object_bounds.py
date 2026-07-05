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
from overkill.recovered.systems.objects import (
    OBJECT_BOUNDS_MAX_X,
    OBJECT_BOUNDS_MAX_Y,
    OBJECT_BOUNDS_MIN_X,
    OBJECT_BOUNDS_TILE_PROBE_HAZARD_CLASS,
    OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS,
    object_bounds_tile_decision_ad60,
)
from overkill.recovered.views.object_slots import OFF_X, ObjectSlotView



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

    # The pure recovered system owns the AD60 branch classification.  This tail
    # keeps the original CMP order so live flags match the oracle at each branch,
    # and asserts the pure decision agrees with the ASM-compatible walk.
    slot = ObjectSlotView.from_ss_bp(cpu)
    x = slot.x_word
    y = slot.y_word
    draw_layer = slot.draw_layer
    logic_id = slot.logic_id
    bdac = mem.rw(ds, 0xBDAC)
    decision = object_bounds_tile_decision_ad60(
        x, y, draw_layer, logic_id, tile_probe_suppressed=bdac == 0x0001
    )

    def _deactivate(chain_suffix: str) -> None:
        if decision.kind != "deactivate":
            raise AssertionError("pure AD60 decision disagrees on out-of-bounds deactivate")
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> {chain_suffix}", cx_value=cx_value, pop_return=False)
        cpu.s.ip = cpu.pop()

    def _skip() -> None:
        if decision.kind != "skip":
            raise AssertionError("pure AD60 decision disagrees on tile-probe skip")
        cpu.s.ip = cpu.pop()

    _cmp_word(cpu, x, OBJECT_BOUNDS_MIN_X)
    if x < OBJECT_BOUNDS_MIN_X:
        _deactivate("AD60")
        return
    _cmp_word(cpu, x, OBJECT_BOUNDS_MAX_X)
    if x > OBJECT_BOUNDS_MAX_X:
        _deactivate("AD60")
        return
    _cmp_word(cpu, y, OBJECT_BOUNDS_MAX_Y)
    if y > OBJECT_BOUNDS_MAX_Y:
        _deactivate("AD60")
        return
    _cmp_word(cpu, draw_layer, OBJECT_BOUNDS_TILE_PROBE_HAZARD_CLASS)
    if draw_layer != OBJECT_BOUNDS_TILE_PROBE_HAZARD_CLASS:
        _skip()
        return
    for good in OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS:
        _cmp_word(cpu, logic_id, good)
        if logic_id == good:
            break
    else:
        _skip()
        return

    _cmp_word(cpu, bdac, 0x0001)
    if bdac == 0x0001:
        _skip()
        return
    if decision.kind != "tile_probe":
        raise AssertionError("pure AD60 decision missed the tile-probe family")
    _run_tile_probe_5073(cpu)
    _add_reg16(cpu, 3, 0x000D)
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
