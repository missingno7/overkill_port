"""OVERKILL input/menu polling helpers lifted from the 1010h code segment.

The routines here are game-specific: they model how OVERKILL packs keyboard or
joystick state into the resident button bitfield at DS:98BE.  Address-facing hook
wrappers stay in ``overkill_port.replacements``; this module owns the reusable
logic so the outer poller and the inner bit-packer do not duplicate code.
"""
from __future__ import annotations

from overkill_port.cpu import CF, IF, ZF
from overkill_port.games.overkill.asm import (
    _cmp_byte,
    _cmp_word,
    _dec_mem_byte_preserve_cf,
    _inc_mem_byte_preserve_cf,
)


def _or_mem_byte(cpu, seg: int, off: int, value: int) -> int:
    """8086 ``OR byte ptr [seg:off], imm8`` helper."""
    result = cpu.mem.rb(seg, off) | (value & 0xFF)
    cpu.mem.wb(seg, off, result)
    cpu.set_logic_flags(result, 8)
    return result


def pack_keyboard_poll_bits_017e(cpu) -> None:
    """Run the hot 1010:017E keyboard bit-packer up to 1010:018B.

    The caller must set ``CX`` to the number of scan-code entries, ``SI`` to the
    active control-map table, and ``DI`` to the keyboard state table base
    (normally DS:98C4).  The routine reads each scancode, fetches the associated
    key-state byte, shifts bit 0 into CF, and ``RCL``-packs it into DS:98BE.
    """
    s = cpu.s
    ds = s.ds & 0xFFFF
    data = cpu.mem.data
    base = ds << 4
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    cx = s.cx & 0xFFFF
    if cx == 0:
        cx = 0x10000

    bh = s.bx & 0xFF00
    al = s.ax & 0xFF
    bl = s.bx & 0xFF
    scratch_off = 0x98BE

    while cx:
        bl = data[(base + si) & 0xFFFFF]
        bx = bh | bl
        al = data[(base + ((bx + di) & 0xFFFF)) & 0xFFFFF]
        al = cpu.shift(5, al, 1, 8)  # SHR AL,1; CF becomes the key-state bit.
        scratch_addr = (base + scratch_off) & 0xFFFFF
        data[scratch_addr] = cpu.shift(2, data[scratch_addr], 1, 8)  # RCL byte [98BE],1.

        old_cf = cpu.get_flag(CF)
        old_si = si
        si = (si + 1) & 0xFFFF
        cpu.set_add_flags(old_si, 1, old_si + 1, 16)  # INC SI flags...
        cpu.set_flag(CF, old_cf)                      # ...but INC preserves CF.
        cx -= 1

    s.ax = (s.ax & 0xFF00) | (al & 0xFF)
    s.bx = bh | bl
    s.si = si
    s.cx = 0
    s.ip = 0x018B


def _joystick_axis_sample_00e8(cpu) -> None:
    """Model the observed 1010:00E8 joystick timing helper.

    This is only used by the 1010:0162 joystick branch.  It mirrors the narrow
    hardware model already used by the interpreter: write AL to port 201h, then
    poll port 201h until the low two bits clear or SI wraps.  In the default DOS
    shim port 201h reads as zero, so the loop normally exits immediately, but the
    helper remains exact enough for custom port readers.
    """
    s = cpu.s
    s.bx = 0
    s.cx = 0
    s.si = 0xC350
    s.dx = 0x0201
    cpu.set_flag(IF, False)  # CLI
    if cpu.port_writer:
        cpu.port_writer(cpu, 0x0201, s.ax & 0xFF, 8)
    while True:
        value = cpu.port_reader(cpu, 0x0201, 8) if cpu.port_reader else 0
        cpu.set_reg8(0, value)
        s.ax &= 0x0003
        cpu.set_logic_flags(s.ax, 16)  # AND AX,0003h
        if cpu.get_flag(ZF):
            break
        # RCR AX,1 then ADC BX,0.
        old_cf = 1 if cpu.get_flag(CF) else 0
        new_cf = bool(s.ax & 0x0001)
        s.ax = ((old_cf << 15) | ((s.ax >> 1) & 0x7FFF)) & 0xFFFF
        cpu.set_flag(CF, new_cf)
        addend = 1 if cpu.get_flag(CF) else 0
        old_bx = s.bx & 0xFFFF
        result = old_bx + addend
        s.bx = result & 0xFFFF
        cpu.set_add_flags(old_bx, addend, result, 16)
        result = (s.cx & 0xFFFF) + (s.ax & 0xFFFF)
        cpu.set_add_flags(s.cx & 0xFFFF, s.ax & 0xFFFF, result, 16)
        s.cx = result & 0xFFFF
        old_si = s.si & 0xFFFF
        s.si = (old_si + 1) & 0xFFFF
        old_cf_after_inc = cpu.get_flag(CF)
        cpu.set_add_flags(old_si, 1, old_si + 1, 16)
        cpu.set_flag(CF, old_cf_after_inc)
        if s.si == 0:
            break
    cpu.set_flag(IF, True)  # STI


def run_input_poll_0162(cpu) -> None:
    """Run OVERKILL 1010:0162 input poller to its near return.

    ``DS:[0010]`` selects the input device/mapping:
    * value 1: joystick path, switches to the resident input-data segment 15BCh;
    * value 2: alternate keyboard control-map table DS:2146;
    * anything else: default keyboard control-map table DS:213E.
    """
    s = cpu.s
    ds = s.ds & 0xFFFF

    _cmp_word(cpu, cpu.mem.rw(ds, 0x0010), 0x0001)
    if cpu.get_flag(ZF):
        # 01CE joystick branch.
        s.ax = 0x15BC
        s.ds = s.ax
        ds = s.ds & 0xFFFF
        cpu.mem.wb(ds, 0x98BE, 0)
        cpu.mem.ww(ds, 0x0012, 1)
        _joystick_axis_sample_00e8(cpu)
        s.si = s.bx & 0xFFFF
        _cmp_word(cpu, s.si, cpu.mem.rw(ds, 0x003E))
        if cpu.get_flag(CF):  # JAE skips the OR; OR only when SI < lower bound.
            _or_mem_byte(cpu, ds, 0x98BE, 0x02)
        _cmp_word(cpu, s.si, cpu.mem.rw(ds, 0x0040))
        if not (cpu.get_flag(CF) or cpu.get_flag(ZF)):  # JA sets right bit.
            _or_mem_byte(cpu, ds, 0x98BE, 0x01)
        _joystick_axis_sample_00e8(cpu)
        s.si = s.cx & 0xFFFF
        _cmp_word(cpu, s.si, cpu.mem.rw(ds, 0x0042))
        if cpu.get_flag(CF):
            _or_mem_byte(cpu, ds, 0x98BE, 0x08)
        _cmp_word(cpu, s.si, cpu.mem.rw(ds, 0x0044))
        if not (cpu.get_flag(CF) or cpu.get_flag(ZF)):
            _or_mem_byte(cpu, ds, 0x98BE, 0x04)
        s.dx = 0x0201
        value = cpu.port_reader(cpu, 0x0201, 8) if cpu.port_reader else 0
        cpu.set_reg8(0, value)
        _cmp_word(cpu, cpu.mem.rw(ds, 0x0012), 0x0001)
        s.cx = (s.cx & 0xFF00) | 0x20
        s.cx = (s.cx & 0x00FF) | 0x1000
        if not cpu.get_flag(ZF):
            s.cx = (s.cx & 0xFF00) | 0x80
            s.cx = (s.cx & 0x00FF) | 0x4000
        cpu.set_logic_flags((s.cx & 0x00FF) & (s.ax & 0x00FF), 8)  # TEST CL,AL
        if cpu.get_flag(ZF):
            _or_mem_byte(cpu, ds, 0x98BE, 0x20)
        cpu.set_logic_flags(((s.cx >> 8) & 0xFF) & (s.ax & 0x00FF), 8)  # TEST CH,AL
        if cpu.get_flag(ZF):
            _or_mem_byte(cpu, ds, 0x98BE, 0x10)
        s.ip = cpu.pop()
        return

    # 0169 keyboard branch.
    s.cx = 0x0008
    s.bx = 0
    cpu.set_logic_flags(0, 16)  # XOR BX,BX
    s.si = 0x213E
    _cmp_word(cpu, cpu.mem.rw(ds, 0x0010), 0x0002)
    if cpu.get_flag(ZF):
        s.si = 0x2146
    s.di = 0x98C4
    pack_keyboard_poll_bits_017e(cpu)

    for off, mask in (
        (0x000F, 0x20),
        (0x0039, 0x10),
        (0x0048, 0x08),
        (0x0050, 0x04),
        (0x004B, 0x02),
        (0x004D, 0x01),
    ):
        _cmp_byte(cpu, cpu.mem.rb(ds, (s.di + off) & 0xFFFF), 0)
        if not cpu.get_flag(ZF):
            _or_mem_byte(cpu, ds, 0x98BE, mask)
    s.ip = cpu.pop()


def run_input_selector_loop_d445(cpu) -> None:
    """Run one observed 1010:D445 input/selector loop iteration.

    The loop has two distinct observed modes:

    * when ``DS:[98E4] == 1``, it increments ``DS:[BEDC]`` and wraps that
      counter back to zero after the third tick; and
    * otherwise it polls input through ``1010:0162`` and adjusts ``DS:[BEDA]``
      as a small 2x3 selector grid driven by the direction bits in
      ``DS:[98BE]``.

    The fire bit ``10h`` exits immediately for every selector value, including
    ``DS:[BEDA] == 0``.  That zero slot is the first planet (Edrax), so adding a
    Python-side nonzero guard would make Edrax impossible to select.

    Important: this is an interactive busy-wait loop when no usable key is
    pressed.  The hook must not spin in Python until input changes, because that
    starves the UI thread and prevents queued snapshot requests from being
    serviced.  For idle/waiting cases it executes exactly one poll iteration and
    lands back on ``D445h`` with the same observable flags the final branch would
    have produced.  The outer player can then yield, pump key events, and call the
    hook again on the next VM slice.
    """

    def _write_beda_add(delta: int) -> int:
        old = cpu.s.ax & 0xFF
        result_full = old + (delta & 0xFF)
        result = result_full & 0xFF
        cpu.mem.wb(ds, 0xBEDA, result)
        cpu.set_reg8(0, result)
        cpu.set_add_flags(old, delta & 0xFF, result_full, 8)
        return result

    def _write_beda_sub(delta: int) -> int:
        old = cpu.s.ax & 0xFF
        result_full = old - (delta & 0xFF)
        result = result_full & 0xFF
        cpu.mem.wb(ds, 0xBEDA, result)
        cpu.set_reg8(0, result)
        cpu.set_sub_flags(old, delta & 0xFF, result_full, 8)
        return result

    s = cpu.s
    ds = s.ds & 0xFFFF
    mem = cpu.mem

    while True:
        _cmp_byte(cpu, mem.rb(ds, 0x98E4), 0x01)
        if cpu.get_flag(ZF):
            _inc_mem_byte_preserve_cf(cpu, ds, 0xBEDC)
            bedc = mem.rb(ds, 0xBEDC)
            _cmp_byte(cpu, bedc, 0x03)
            if bedc >= 0x03:
                mem.wb(ds, 0xBEDC, 0x00)
            s.ip = cpu.pop()
            return

        cpu.push(0xD44F)
        poll_input = cpu.replacement_hooks.get((0x1010, 0x0162), run_input_poll_0162)
        poll_input(cpu)
        if s.ip != 0xD44F:
            raise RuntimeError(f"0162 returned to unexpected IP {s.ip:04X} inside D445 selector loop")

        beda = mem.rb(ds, 0xBEDA)
        cpu.set_reg8(0, beda)
        buttons = mem.rb(ds, 0x98BE)

        if buttons & 0x01:
            _cmp_byte(cpu, beda, 0x03)
            if beda < 0x03:
                _write_beda_add(0x03)
            s.ip = cpu.pop()
            return

        if buttons & 0x02:
            _cmp_byte(cpu, beda, 0x02)
            if beda > 0x02:
                _write_beda_sub(0x03)
            s.ip = cpu.pop()
            return

        if buttons & 0x08:
            cpu.set_logic_flags(beda, 8)
            if beda == 0:
                s.ip = 0xD445
                return
            old_cf = cpu.get_flag(CF)
            result = _dec_mem_byte_preserve_cf(cpu, ds, 0xBEDA)
            cpu.set_reg8(0, result)
            cpu.set_flag(CF, old_cf)
            s.ip = cpu.pop()
            return

        if buttons & 0x04:
            _cmp_byte(cpu, beda, 0x05)
            if beda != 0x05:
                old_cf = cpu.get_flag(CF)
                _write_beda_add(0x01)
                cpu.set_flag(CF, old_cf)
            s.ip = cpu.pop()
            return

        if buttons & 0x10:
            # Original code at 1010:D46F is simply:
            #   TEST byte [98BE],10h
            #   JZ D445
            #   RET
            # There is no BEDA/nonzero guard.  BEDA==0 is the Edrax slot.
            cpu.set_logic_flags(buttons & 0x10, 8)
            s.ip = cpu.pop()
            return

        # Original idle tail is a TEST/JZ back to D445.  Preserve the final
        # TEST flags instead of looping internally.
        cpu.set_logic_flags(buttons & 0x10, 8)
        s.ip = 0xD445
        return


def run_input_release_wait_gate_986e(cpu) -> None:
    """Lift the tiny 1010:986E key-release wait gate.

    The original block is an interactive busy wait:

    ``CMP byte [98C5],01h; JE 986E``

    Keep it as a one-iteration state-machine hook instead of spinning in Python
    so the outer runtime can still yield between CPU chunks while a key remains
    held.  The hook preserves the original CMP flags and lands either back on
    the same gate or at the finite continuation 9875h.
    """
    ds = cpu.s.ds & 0xFFFF
    value = cpu.mem.rb(ds, 0x98C5)
    _cmp_byte(cpu, value, 0x01)
    cpu.s.ip = 0x986E if value == 0x01 else 0x9875


def run_yes_no_choice_wait_gate_989e(cpu) -> None:
    """Lift one poll of the 1010:989E yes/no choice wait gate.

    The original code continuously rewrites ``DS:22B4`` to ``'N'`` or ``'Y'``
    while waiting for either the N-key flag ``DS:98F5`` or Y-key flag
    ``DS:98D9``.  This function intentionally executes only one poll iteration:
    if no accepted key is down it returns to 989Eh, preserving the original
    opportunity for the frontend/input layer to update memory between chunks.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    mem.wb(ds, 0x22B4, 0x4E)  # 'N'
    n_flag = mem.rb(ds, 0x98F5)
    _cmp_byte(cpu, n_flag, 0x01)
    if n_flag == 0x01:
        cpu.s.ip = 0x98B6
        return

    mem.wb(ds, 0x22B4, 0x59)  # 'Y'
    y_flag = mem.rb(ds, 0x98D9)
    _cmp_byte(cpu, y_flag, 0x01)
    cpu.s.ip = 0x98B6 if y_flag == 0x01 else 0x989E


def run_sound_effect_completion_wait_gate_98d8(cpu) -> None:
    """Lift one poll of the 1010:98D8 sound/effect completion wait gate.

    The original branch waits while ``DS:BEFE`` is non-zero.  Keep it as a
    one-iteration same-IP gate so it removes interpreted hot-loop noise without
    swallowing runtime yields.
    """
    ds = cpu.s.ds & 0xFFFF
    value = cpu.mem.rb(ds, 0xBEFE)
    _cmp_byte(cpu, value, 0x00)
    cpu.s.ip = 0x98D8 if value != 0x00 else 0x98DF


def run_intro_retrace_delay_loop_96c5(cpu, call_retrace_wait) -> None:
    """Run the 1010:96C5 intro/menu retrace-delay loop to 1010:96CA.

    The original parent initializes ``CX`` before entering this loop and then
    performs ``CALL 50C9`` followed by ``LOOP 96C5``.  Interactive play wraps
    the installed 50C9 hook as a video publish/yield boundary, so this helper
    receives a callback instead of calling the base retrace hook directly.

    ``LOOP`` does not alter flags; the final flags/AL/DX side effects therefore
    remain those produced by the last 50C9 call.
    """
    while True:
        call_retrace_wait(0x96C8)
        if cpu.s.ip != 0x96C8:
            raise RuntimeError(f"50C9 returned to unexpected IP {cpu.s.ip:04X} inside 96C5 delay loop")
        cx = ((cpu.s.cx & 0xFFFF) - 1) & 0xFFFF
        cpu.s.cx = cx
        if cx != 0:
            continue
        cpu.s.ip = 0x96CA
        return


def run_intro_retrace_delay_loop_tail_96c8(cpu) -> None:
    """Resume the 1010:96C5 delay loop at the post-50C9 LOOP instruction.

    This is needed only when the interactive 50C9 wrapper publishes a frame and
    stops the CPU burst with IP at the original 96C8 continuation.
    """
    cx = ((cpu.s.cx & 0xFFFF) - 1) & 0xFFFF
    cpu.s.cx = cx
    cpu.s.ip = 0x96C5 if cx != 0 else 0x96CA
