"""DOS/ASM adapters for recovered movement systems."""
from __future__ import annotations

from overkill.asm import _add_mem_word, _add_reg16, _and_mem_word, _sub_mem_word
from overkill.recovered.adapters.object_slot_adapter import read_object_slot_record
from overkill.recovered.domain.movement import MovementTarget, TargetSeekDecision
from overkill.recovered.domain.coords import i16
from overkill.recovered.systems.movement import (
    PLAYER_CENTER_TARGET_X_BIAS,
    PLAYER_CENTER_TARGET_Y_BIAS,
    TARGET_GRID_MASK_4PX,
    align_word_to_four,
    choose_target_seek_direction,
    player_center_target_from_view,
    step_operations_for_direction,
)
from overkill.recovered.views.object_slots import OFF_TARGET_X, OFF_TARGET_Y, OFF_X, OFF_Y, ObjectSlotView

MOVEMENT_TARGET_Y = 0x2304
MOVEMENT_TARGET_X = 0x2306
MOVEMENT_MODE = 0x2308
MOVEMENT_BLOCKED_FLAG = 0x230A
MOVEMENT_DIRECTION_BITS = 0xA954
MOVEMENT_DIRECTION_TABLE = 0xA348
VIEW_TARGET_X = 0x237E
VIEW_TARGET_Y = 0x2380


def read_movement_target_globals(cpu) -> MovementTarget:
    """Copy the original 5DB2 target globals into a pure movement record."""
    ds = cpu.s.ds & 0xFFFF
    return MovementTarget(
        y_word=cpu.mem.rw(ds, MOVEMENT_TARGET_Y),
        x_word=cpu.mem.rw(ds, MOVEMENT_TARGET_X),
    )


def read_direction_table(cpu) -> tuple[int, ...]:
    """Copy the 16-byte 5DB2 direction map used by the original XLAT."""
    ds = cpu.s.ds & 0xFFFF
    return tuple(cpu.mem.rb(ds, (MOVEMENT_DIRECTION_TABLE + idx) & 0xFFFF) for idx in range(16))


def decide_target_seek_direction_from_dos(cpu, slot: ObjectSlotView) -> TargetSeekDecision:
    """Run the pure 5DB2 direction decision from DOS-memory inputs."""
    return choose_target_seek_direction(
        read_object_slot_record(slot),
        read_movement_target_globals(cpu),
        read_direction_table(cpu),
    )


def publish_object_slot_target_to_movement_globals(cpu, slot: ObjectSlotView) -> MovementTarget:
    """Recovered B729 target-copy prelude: slot +32/+34 -> DS:2304/2306."""
    ds = cpu.s.ds & 0xFFFF
    target = MovementTarget(y_word=slot.u16(OFF_TARGET_Y), x_word=slot.u16(OFF_TARGET_X))
    cpu.mem.ww(ds, MOVEMENT_TARGET_Y, target.y_word)
    cpu.mem.ww(ds, MOVEMENT_TARGET_X, target.x_word)
    return target


def apply_direction_step_to_current_object(cpu, *, direction: int, pixels: int) -> None:
    """Apply one recovered AEE4/AF22/AF63 movement step to ``SS:BP``.

    The pure system owns the direction -> ordered axis mutation mapping.  This
    adapter performs the original-compatible ADD/SUB memory writes so register
    flags remain byte-for-byte comparable with the ASM oracle.
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    for op in step_operations_for_direction(direction, pixels):
        off = OFF_X if op.axis == "x" else OFF_Y
        delta = i16(op.delta_word)
        if delta >= 0:
            _add_mem_word(cpu, ss, (bp + off) & 0xFFFF, delta)
        else:
            _sub_mem_word(cpu, ss, (bp + off) & 0xFFFF, -delta)


def read_player_center_target_from_dos(cpu) -> MovementTarget:
    """Project B1B0's view/player-center target without mutating DOS state."""
    ds = cpu.s.ds & 0xFFFF
    return player_center_target_from_view(
        cpu.mem.rw(ds, VIEW_TARGET_X),
        cpu.mem.rw(ds, VIEW_TARGET_Y),
    )


def run_player_center_target_setup_b1bf(cpu) -> MovementTarget:
    """Replay B1B0's view-target setup while proving the pure projection.

    This is the exact source-port boundary we want: the pure movement system
    decides the aligned target point, while this adapter performs the original
    MOV/ADD/AND memory sequence so CPU-visible flags and intermediate writes
    stay verifier-compatible.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    target = read_player_center_target_from_dos(cpu)

    cpu.s.ax = cpu.mem.rw(ds, VIEW_TARGET_X)
    _add_reg16(cpu, 0, PLAYER_CENTER_TARGET_X_BIAS)
    cpu.mem.ww(ds, MOVEMENT_TARGET_X, cpu.s.ax)
    cpu.s.ax = cpu.mem.rw(ds, VIEW_TARGET_Y)
    _add_reg16(cpu, 0, PLAYER_CENTER_TARGET_Y_BIAS)
    cpu.mem.ww(ds, MOVEMENT_TARGET_Y, cpu.s.ax)
    cpu.mem.ww(ds, MOVEMENT_MODE, 0x0002)
    _and_mem_word(cpu, ds, MOVEMENT_TARGET_Y, TARGET_GRID_MASK_4PX)
    _and_mem_word(cpu, ds, MOVEMENT_TARGET_X, TARGET_GRID_MASK_4PX)
    _and_mem_word(cpu, ss, (bp + OFF_Y) & 0xFFFF, TARGET_GRID_MASK_4PX)
    _and_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, TARGET_GRID_MASK_4PX)

    if (cpu.mem.rw(ds, MOVEMENT_TARGET_Y), cpu.mem.rw(ds, MOVEMENT_TARGET_X)) != (
        target.y_word,
        target.x_word,
    ):
        raise RuntimeError("B1B0 pure view-target projection disagrees with ASM writes")
    return target
