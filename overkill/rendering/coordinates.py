"""OVERKILL coordinate and object-row address helpers.

The routines in this module are lifted from the startup/runtime rendering helper
cluster around 1010:5A00, 1010:5A24, and 1010:5A36.  They are shared by CGA,
EGA, and Tandy draw/present paths.

The implementation is intentionally OverKill-specific: it knows the game's row
base tables, object stack-frame layout, mode selector at CS:95BC, and the exact
ASM continuation behavior.  The generic CPU/VM should not know any of this.

Human-readable implementation lives here; the @registry.replace hook wrappers in
``overkill.hooks`` keep the original ASM addresses visible.
"""

from __future__ import annotations

from dos_re.cpu import CF

from overkill.recovered.ds_globals import VIDEO_MODE_SELECTOR_OFF

MODE_CGA = 0
MODE_EGA = 1
MODE_TANDY = 2

VIDEO_MODE_NAME = {
    MODE_CGA: "CGA",
    MODE_EGA: "EGA",
    MODE_TANDY: "Tandy",
}

# Original OVERKILL data tables used by the lifted helpers.
# VIDEO_MODE_SELECTOR_OFF imported from recovered.ds_globals (shared cell).
OBJECT_ROW_TABLE_OFF = 0x99C8
OBJECT_FRAME_Y_OFF = 0x02
OBJECT_FRAME_X_OFF = 0x04
OBJECT_FRAME_PHASE_OFF = 0x12
OBJECT_FRAME_COUNTDOWN_OFF = 0x24
SCREEN_HEIGHT_LIMIT = 0x00E0
OFFSCREEN_ROW = 0xFFFF


def _add_reg16(cpu, reg_idx: int, value: int) -> None:
    """Mirror ``ADD r16,imm/r16`` on the VM register file."""
    old = cpu.get_reg16(reg_idx)
    addend = value & 0xFFFF
    result = old + addend
    cpu.set_reg16(reg_idx, result)
    cpu.set_add_flags(old, addend, result, 16)


def _cmp_word(cpu, a: int, b: int) -> None:
    """Mirror ``CMP word,word`` flag side effects."""
    left = a & 0xFFFF
    right = b & 0xFFFF
    cpu.set_sub_flags(left, right, left - right, 16)


def _dec_object_countdown_preserve_cf(cpu, ss: int, bp: int) -> None:
    """Decrement SS:[BP+24h] exactly like the original DEC instruction.

    The row-address helper compares the countdown against zero before DEC.  DEC
    updates arithmetic flags but preserves CF, so the hook has to restore the CF
    produced by the preceding CMP.
    """
    off = (bp + OBJECT_FRAME_COUNTDOWN_OFF) & 0xFFFF
    countdown = cpu.mem.rw(ss, off)
    _cmp_word(cpu, countdown, 0)
    if countdown == 0:
        return

    old_cf = cpu.get_flag(CF)
    result = (countdown - 1) & 0xFFFF
    cpu.mem.ww(ss, off, result)
    cpu.set_sub_flags(countdown, 1, countdown - 1, 16)
    cpu.set_flag(CF, old_cf)


def _format_object_context(cpu, bp: int | None = None) -> str:
    """Small local fail-fast context for coordinate helper dispatch errors."""
    s = cpu.s
    parts = [
        f"CS:IP={s.cs:04X}:{s.ip:04X}",
        f"DS={s.ds:04X}",
        f"SS={s.ss:04X}",
        f"SP={s.sp:04X}",
        f"AX={s.ax:04X}",
        f"BX={s.bx:04X}",
        f"CX={s.cx:04X}",
    ]
    if bp is not None:
        parts.append(f"BP={bp:04X}")
    return "; ".join(parts)


def _raise_unknown_mode(cpu, *, parent: str, dispatch_table: int, mode: int) -> None:
    cs = cpu.s.cs & 0xFFFF
    target_ip = cpu.mem.rw(cs, (dispatch_table + cpu.s.bx) & 0xFFFF)
    raise RuntimeError(
        f"unverified original-code path reached in {parent}: "
        f"coordinate helper mode dispatch mode={mode & 0xFFFF:04X} -> {target_ip:04X}. "
        f"Fail-fast is intentional; reverse and hook this target instead of "
        f"falling back to interpreted ASM. {_format_object_context(cpu, cpu.s.bp & 0xFFFF)}"
    )


def _finish_offscreen_object_row(cpu) -> None:
    cpu.s.ax = OFFSCREEN_ROW
    cpu.s.ip = cpu.pop()


def _object_row_address_for_mode(cpu, *, phase_mask: int | None, x_shift_count: int) -> None:
    """Shared body for 1010:5A36 mode targets.

    Original targets:
      * mode 0 CGA   -> 1010:41F5, phase = X & 3, X byte address = X >> 2
      * mode 1 EGA   -> 1010:2580, phase = X & 7, X byte address = X >> 3
      * mode 2 Tandy -> 1010:30D2, phase = 0,     X word address = X >> 1

    All three targets return near to the caller of 5A36, either with AX=FFFFh
    for an offscreen row or AX=row_base+scaled_x for a visible row.
    """
    s = cpu.s
    ss = s.ss & 0xFFFF
    ds = s.ds & 0xFFFF
    bp = s.bp & 0xFFFF
    mem = cpu.mem

    y = mem.rw(ss, (bp + OBJECT_FRAME_Y_OFF) & 0xFFFF)
    s.bx = y
    _cmp_word(cpu, y, SCREEN_HEIGHT_LIMIT)
    if y >= SCREEN_HEIGHT_LIMIT:
        _finish_offscreen_object_row(cpu)
        return

    s.bx = cpu.shift(4, y, 1, 16)  # SHL BX,1: row table is word indexed.
    row_base = mem.rw(ds, (s.bx + OBJECT_ROW_TABLE_OFF) & 0xFFFF)
    s.bx = row_base
    _cmp_word(cpu, row_base, OFFSCREEN_ROW)
    if row_base == OFFSCREEN_ROW:
        _finish_offscreen_object_row(cpu)
        return

    x = mem.rw(ss, (bp + OBJECT_FRAME_X_OFF) & 0xFFFF)
    s.ax = x
    if phase_mask is None:
        # Tandy target stores zero directly.  Unlike the CGA/EGA AND path this
        # does not produce logic flags before the later SHR/ADD sequence.
        mem.ww(ss, (bp + OBJECT_FRAME_PHASE_OFF) & 0xFFFF, 0)
    else:
        s.cx = x
        s.cx &= phase_mask & 0xFFFF
        cpu.set_logic_flags(s.cx, 16)  # AND CX,mask
        mem.ww(ss, (bp + OBJECT_FRAME_PHASE_OFF) & 0xFFFF, s.cx)

    for _ in range(x_shift_count):
        s.ax = cpu.shift(5, s.ax, 1, 16)  # SHR AX,1
    _add_reg16(cpu, 0, row_base)          # ADD AX,BX

    _dec_object_countdown_preserve_cf(cpu, ss, bp)
    s.ip = cpu.pop()



def object_row_address_mode1_2580(cpu) -> None:
    """Hook-callable body for OVERKILL 1010:2580 EGA row-address target.

    Some existing lifted EGA routines call the target directly with synthetic
    CALL/RET stack behavior instead of going through 5A36.  Keep this named
    target available so those wrappers remain readable and address-faithful.
    """
    _object_row_address_for_mode(cpu, phase_mask=0x0007, x_shift_count=3)

def object_row_address_from_mode_dispatch_5a36(cpu) -> None:
    """Hook body for OVERKILL 1010:5A36 object-row address helper.

    5A36 is a video-mode dispatch stub.  It loads CS:95BC, shifts it as a word
    table index, and jumps to a mode-specific target.  This lifted body keeps the
    dispatch side effect on BX, then executes the verified target shape for CGA,
    EGA, or Tandy.
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    mode = cpu.mem.rw(cs, VIDEO_MODE_SELECTOR_OFF)
    s.bx = mode & 0xFFFF
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1 from the dispatch stub.

    if mode == MODE_CGA:
        _object_row_address_for_mode(cpu, phase_mask=0x0003, x_shift_count=2)
        return
    if mode == MODE_EGA:
        _object_row_address_for_mode(cpu, phase_mask=0x0007, x_shift_count=3)
        return
    if mode == MODE_TANDY:
        _object_row_address_for_mode(cpu, phase_mask=None, x_shift_count=1)
        return

    _raise_unknown_mode(cpu, parent="1010:5A36", dispatch_table=0x5A42, mode=mode)


def coordinate_ax_to_di_from_mode_dispatch(cpu, *, dispatch_table: int, row_table: int) -> None:
    """Shared hook body for OVERKILL 1010:5A00 and 1010:5A24.

    Input contract is AX=(Y byte in AH, X byte in AL).  The original dispatch
    selects a mode-specific target through CS:95BC.  All known targets share the
    same shape: load the row base from a DS table indexed by Y, zero AH so AX is
    only X, scale X for the video memory layout, add the row base, copy AX to DI,
    and return near.

    Horizontal scaling by mode:
      * mode 0 CGA   -> X << 1, targets 422B/4251
      * mode 1 EGA   -> X,      targets 25B6/25D8
      * mode 2 Tandy -> X << 2, targets 3103/312D
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    mode = cpu.mem.rw(cs, VIDEO_MODE_SELECTOR_OFF)
    s.bx = mode & 0xFFFF
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1 from the dispatch stub.
    if mode not in (MODE_CGA, MODE_EGA, MODE_TANDY):
        _raise_unknown_mode(cpu, parent="1010:5A00/5A24", dispatch_table=dispatch_table, mode=mode)

    ds = s.ds & 0xFFFF
    y = (s.ax >> 8) & 0xFF
    x = s.ax & 0xFF
    s.bx = (y << 1) & 0xFFFF
    row_base = cpu.mem.rw(ds, (row_table + s.bx) & 0xFFFF)
    s.bx = row_base

    x_shift = {
        MODE_CGA: 1,
        MODE_EGA: 0,
        MODE_TANDY: 2,
    }[mode & 0xFFFF]
    s.ax = (x << x_shift) & 0xFFFF
    _add_reg16(cpu, 0, row_base)
    s.di = s.ax & 0xFFFF
    s.ip = cpu.pop()


def coordinate_ax_to_di_5a00(cpu) -> None:
    """Hook body for OVERKILL 1010:5A00 coordinate helper."""
    coordinate_ax_to_di_from_mode_dispatch(cpu, dispatch_table=0x5A0C, row_table=0x9EE8)


def coordinate_ax_to_di_5a24(cpu) -> None:
    """Hook body for OVERKILL 1010:5A24 coordinate helper."""
    coordinate_ax_to_di_from_mode_dispatch(cpu, dispatch_table=0x5A30, row_table=0x9D58)
