"""OVERKILL object scan / logic dispatch glue.

Small bounded helpers that are part of object-list traversal but are not the
large object behavior bodies themselves.
"""
from __future__ import annotations

from dos_re.cpu import DF

from overkill.asm import _add_mem_word, loop_count
from overkill.recovered.views.object_slots import ObjectSlotView

SIG_OBJECT_LOGIC_CALL_AA2B_AA01 = bytes.fromhex("e8 27 00 59 e2 d9")
SIG_OBJECT_LOGIC_SCAN_TAIL_AA04 = bytes.fromhex("59 e2 d9")


def dispatch_object_logic_aa2b(cpu) -> None:
    """Lift OVERKILL 1010:AA2B first-level object-logic dispatcher."""
    s = cpu.s
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    s.bx = slot.hazard_class
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ip = cpu.mem.rw(s.cs & 0xFFFF, (0xAA36 + s.bx) & 0xFFFF)


def call_object_logic_from_scan_aa01(cpu, self_disable_if_patched) -> None:
    """Model ``AA01: CALL AA2B`` while preserving the real return frame."""
    if self_disable_if_patched(cpu, 0xAA01, SIG_OBJECT_LOGIC_CALL_AA2B_AA01, "overkill_object_logic_call_aa2b_aa01"):
        return
    cpu.push(0xAA04)
    dispatch_object_logic_aa2b(cpu)


def finish_object_logic_scan_tail_aa04(cpu, self_disable_if_patched) -> None:
    """Model ``AA04: POP CX ; LOOP A9E0``."""
    if self_disable_if_patched(cpu, 0xAA04, SIG_OBJECT_LOGIC_SCAN_TAIL_AA04, "overkill_object_logic_scan_tail_aa04"):
        return
    s = cpu.s
    s.cx = cpu.pop()
    s.cx = (s.cx - 1) & 0xFFFF
    s.ip = 0xA9E0 if s.cx != 0 else 0xAA07


SIG_RESET_EFFECT_SLOT_BLOCK_C3BF = bytes.fromhex(
    "51 8b d9 d1 e3 8b af 12 8d c7 46 00 00 00 c7 46 2e 00 00 "
    "c7 46 18 00 00 2e a1 a2 c3 89 46 0e 2e 83 06 a2 c3 40 "
    "59 e2 d8"
)

SIG_RESET_OBJECT_SLOT_BLOCK_C3F1 = bytes.fromhex(
    "51 8b d9 d1 e3 8b af ca 32 c7 46 0a 01 00 83 7e 16 01 74 "
    "19 c7 46 00 00 00 c7 46 2e 00 00 c7 46 24 00 00 c7 46 "
    "18 00 00 c7 46 06 00 00 2e a1 a2 c3 89 46 0e 2e 81 06 "
    "a2 c3 80 02 59 e2 c2"
)


def run_reset_effect_slot_block_c3bf(cpu, self_disable_if_patched) -> None:
    """Lift the internal 1010:C3BF compact-slot reset loop body.

    The parent setup routine enters here with CX loaded and CS:C3A2 pointing at
    the first compact present-frame cell.  The loop uses the pointer table at
    DS:8D12 + CX*2, clears selected fields through SS:BP, stamps slot +0E from
    CS:C3A2, advances CS:C3A2 by 0040h, and falls through to C3E7.
    """
    if self_disable_if_patched(
        cpu,
        0xC3BF,
        SIG_RESET_EFFECT_SLOT_BLOCK_C3BF,
        "overkill_reset_effect_slot_block_c3bf",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF

    for _ in range(loop_count(s.cx)):
        cpu.push(s.cx & 0xFFFF)
        s.bx = s.cx & 0xFFFF
        s.bx = cpu.shift(4, s.bx, 1, 16)
        s.bp = mem.rw(ds, (0x8D12 + (s.bx & 0xFFFF)) & 0xFFFF)
        bp = s.bp & 0xFFFF
        slot = ObjectSlotView(mem, ss, bp)  # the reset target slot (SS:BP)
        slot.active_word = 0x0000
        slot.move_step_error = 0x0000
        slot.logic_id = 0x0000
        s.ax = mem.rw(cs, 0xC3A2)
        slot.link_key = s.ax
        _add_mem_word(cpu, cs, 0xC3A2, 0x0040)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF
        if s.cx == 0:
            break

    s.ip = 0xC3E7


def run_reset_object_slot_block_c3f1(cpu, self_disable_if_patched) -> None:
    """Lift the internal 1010:C3F1 object-slot reset loop body.

    This is the object-table sibling of C4E5 used by the larger setup routine.
    It always restores layer field +0A to 1, preserves slots whose +16 field is
    already 1, clears selected runtime fields for all others, stamps +0E from
    CS:C3A2, advances CS:C3A2 by 0280h, and falls through to C42F.
    """
    if self_disable_if_patched(
        cpu,
        0xC3F1,
        SIG_RESET_OBJECT_SLOT_BLOCK_C3F1,
        "overkill_reset_object_slot_block_c3f1",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF

    for _ in range(loop_count(s.cx)):
        cpu.push(s.cx & 0xFFFF)
        s.bx = s.cx & 0xFFFF
        s.bx = cpu.shift(4, s.bx, 1, 16)
        s.bp = mem.rw(ds, (0x32CA + (s.bx & 0xFFFF)) & 0xFFFF)
        bp = s.bp & 0xFFFF
        slot = ObjectSlotView(mem, ss, bp)  # the reset target slot (SS:BP)
        slot.gate_or_layer = 0x0001
        keep_slot = slot.hazard_class == 0x0001
        cpu.set_sub_flags(slot.hazard_class, 0x0001, slot.hazard_class - 0x0001, 16)
        if not keep_slot:
            slot.active_word = 0x0000
            slot.move_step_error = 0x0000
            slot.variant = 0x0000
            slot.logic_id = 0x0000
            slot.direction_or_step = 0x0000
        s.ax = mem.rw(cs, 0xC3A2)
        slot.link_key = s.ax
        _add_mem_word(cpu, cs, 0xC3A2, 0x0280)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF
        if s.cx == 0:
            break

    s.ip = 0xC42F


SIG_RESET_OBJECT_SLOT_BLOCK_C4E5 = bytes.fromhex(
    "51 8b d9 d1 e3 8b af ca 32 c7 46 00 00 00 c7 46 2e 00 00 "
    "c7 46 24 00 00 c7 46 18 00 00 c7 46 0a 01 00 c7 46 06 "
    "00 00 2e a1 a2 c3 89 46 0e 2e 81 06 a2 c3 80 02 59 e2 c8"
)


def run_reset_object_slot_block_c4e5(cpu, self_disable_if_patched) -> None:
    """Lift the internal 1010:C4E5 object-slot reset loop body.

    This block is entered from the C4DB transition/setup routine after
    CS:C3A2 has been reset and CX has been loaded with the number of object
    table entries.  It clears selected runtime fields for each object pointer
    from DS:32CA, stamps the per-slot present pointer from CS:C3A2, advances
    CS:C3A2 by 0280h per slot, and falls through to C51D.

    The original loop uses PUSH/POP CX each iteration; this replacement keeps
    that stack scratch visible below SP so full-memory oracle comparisons stay
    stable.
    """
    if self_disable_if_patched(
        cpu,
        0xC4E5,
        SIG_RESET_OBJECT_SLOT_BLOCK_C4E5,
        "overkill_reset_object_slot_block_c4e5",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF

    for _ in range(loop_count(s.cx)):
        cpu.push(s.cx & 0xFFFF)
        s.bx = s.cx & 0xFFFF
        s.bx = cpu.shift(4, s.bx, 1, 16)
        s.bp = mem.rw(ds, (0x32CA + (s.bx & 0xFFFF)) & 0xFFFF)
        bp = s.bp & 0xFFFF
        slot = ObjectSlotView(mem, ss, bp)  # the reset target slot (SS:BP)
        slot.active_word = 0x0000
        slot.move_step_error = 0x0000
        slot.variant = 0x0000
        slot.logic_id = 0x0000
        slot.gate_or_layer = 0x0001
        slot.direction_or_step = 0x0000
        s.ax = mem.rw(cs, 0xC3A2)
        slot.link_key = s.ax
        _add_mem_word(cpu, cs, 0xC3A2, 0x0280)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF
        if s.cx == 0:
            break

    s.ip = 0xC51D


SIG_RESET_OBJECT_SLOT_AND_STATUS_SETUP_C4DB = bytes.fromhex(
    "2e c7 06 a2 c3 14 33 b9 24 00"
)


def run_reset_object_slot_and_status_setup_c4db(
    cpu,
    self_disable_if_patched,
    run_reset_object_slots,
    run_setup_tracked_status_tail,
    run_status_cell_quad_composite,
) -> None:
    """Lift 1010:C4DB, the compact object-reset/status-setup parent.

    C4DB is a short setup parent used by transition/status wait code.  It
    resets the object-present pointer base, enters the already-lifted C4E5
    object-slot reset loop, continues through the C51D tracked/status setup
    tail, and finally falls into the 859E status-cell compositor which returns
    to the original caller.

    The children are deliberately kept as separate proof boundaries; this parent
    only exposes the previously-anonymous composition order.
    """
    if self_disable_if_patched(
        cpu,
        0xC4DB,
        SIG_RESET_OBJECT_SLOT_AND_STATUS_SETUP_C4DB,
        "overkill_reset_object_slot_and_status_setup_c4db",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    mem.ww(cs, 0xC3A2, 0x3314)
    s.cx = 0x0024

    run_reset_object_slots()
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xC51D):
        raise RuntimeError(
            f"C4DB expected C4E5 child to fall through to 1010:C51D, got "
            f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
        )

    run_setup_tracked_status_tail()
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x859E):
        raise RuntimeError(
            f"C4DB expected C51D child to jump to 1010:859E, got "
            f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
        )

    run_status_cell_quad_composite()

SIG_SETUP_TRACKED_STATUS_TAIL_C51D = bytes.fromhex(
    "c7 06 58 a9 00 00 c7 06 5e a9 00 00 c7 06 60 a9 00 00 "
    "c7 06 62 a9 ff ff c7 06 64 a9 ff ff c7 06 66 a9 ff ff "
    "c7 06 68 a9 ff ff c7 06 6a a9 ff ff c7 06 6c a9 ff ff "
    "c7 06 6e a9 ff ff c7 06 84 23 00 00 e8 b5 bf e9 39 c0"
)


def run_setup_tracked_status_tail_c51d(cpu, self_disable_if_patched, call_status_cell_list_seed) -> None:
    """Lift 1010:C51D, the setup tail before the status-cell compositor.

    C4DB/C4E5 reset object slots, then this tail clears the tracked-coordinate
    and status descriptor globals, calls the already-lifted ``8517`` descriptor
    seed, and jumps into ``859E``.  Keeping it explicit makes the setup/status
    boundary visible without pretending to know the higher-level game state yet.
    """
    if self_disable_if_patched(
        cpu,
        0xC51D,
        SIG_SETUP_TRACKED_STATUS_TAIL_C51D,
        "overkill_setup_tracked_status_tail_c51d",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    cs = s.cs & 0xFFFF

    for off, value in (
        (0xA958, 0x0000),
        (0xA95E, 0x0000),
        (0xA960, 0x0000),
        (0xA962, 0xFFFF),
        (0xA964, 0xFFFF),
        (0xA966, 0xFFFF),
        (0xA968, 0xFFFF),
        (0xA96A, 0xFFFF),
        (0xA96C, 0xFFFF),
        (0xA96E, 0xFFFF),
        (0x2384, 0x0000),
    ):
        mem.ww(ds, off, value)

    call_status_cell_list_seed(0xC562)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xC562):
        raise RuntimeError(
            f"C51D expected 8517 to return to C562, got "
            f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
        )
    s.ip = 0x859E

SIG_OBJECT_MOTION_TABLE_AB34 = bytes.fromhex(
    "bb 7c 23 8b 77 08 d1 e6 d1 e6 03 f2 ad 03 47 02 "
    "89 46 02 ad 03 47 04 89 46 04 c3"
)

SIG_OBJECT_SCROLL_SPRITE_AB4F = bytes.fromhex("a1 3c 23 05 18 00 89 46 08 c3")


def _lodsw(cpu) -> int:
    s = cpu.s
    value = cpu.mem.rw(s.ds & 0xFFFF, s.si & 0xFFFF)
    s.ax = value
    s.si = (s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    return value


def run_object_motion_table_ab34(cpu, self_disable_if_patched) -> None:
    """Runtime-patched AB34 helper: derive object X/Y from a motion table.

    The caller supplies ``DX`` as the table base and BP as the destination object
    record.  AB34 uses the player/base object at DS:237C, indexes by its sprite
    id at +08, then stores relative X/Y into SS:[BP+2]/[BP+4].
    """
    if self_disable_if_patched(cpu, 0xAB34, SIG_OBJECT_MOTION_TABLE_AB34, "overkill_object_motion_table_ab34"):
        return
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    slot = ObjectSlotView(mem, ss, bp)  # this object's record (SS:BP)

    s.bx = 0x237C
    s.si = mem.rw(ds, (s.bx + 0x08) & 0xFFFF)
    s.si = cpu.shift(4, s.si, 1, 16)
    s.si = cpu.shift(4, s.si, 1, 16)
    old_si = s.si
    s.si = (old_si + (s.dx & 0xFFFF)) & 0xFFFF
    cpu.set_add_flags(old_si, s.dx & 0xFFFF, old_si + (s.dx & 0xFFFF), 16)
    _lodsw(cpu)
    addend = mem.rw(ds, (s.bx + 0x02) & 0xFFFF)
    old_ax = s.ax
    s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    slot.x_word = s.ax
    _lodsw(cpu)
    addend = mem.rw(ds, (s.bx + 0x04) & 0xFFFF)
    old_ax = s.ax
    s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    slot.y_word = s.ax
    s.ip = cpu.pop()


def run_object_scroll_sprite_ab4f(cpu, self_disable_if_patched) -> None:
    """Runtime-patched AB4F helper: choose sprite from horizontal scroll base."""
    if self_disable_if_patched(cpu, 0xAB4F, SIG_OBJECT_SCROLL_SPRITE_AB4F, "overkill_object_scroll_sprite_ab4f"):
        return
    s = cpu.s
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    s.ax = cpu.mem.rw(ds, 0x233C)
    old_ax = s.ax
    s.ax = (old_ax + 0x0018) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0018, old_ax + 0x0018, 16)
    slot.sprite_or_state = s.ax
    s.ip = cpu.pop()
