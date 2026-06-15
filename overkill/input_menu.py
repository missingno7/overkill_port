"""OVERKILL input/menu polling helpers lifted from the 1010h code segment.

The routines here are game-specific: they model how OVERKILL packs keyboard or
joystick state into the resident button bitfield at DS:98BE.  Address-facing hook
wrappers stay in ``overkill.hooks``; this module owns the reusable
logic so the outer poller and the inner bit-packer do not duplicate code.
"""
from __future__ import annotations

from dos_re.cpu import CF, DF, IF, ZF
from overkill.asm import (
    _cmp_byte,
    _cmp_word,
    _dec_mem_byte_preserve_cf,
    _inc_mem_byte_preserve_cf,
    _inc_mem_word_preserve_cf,
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




def run_boss_key_f9_release_wait_gate_07c4(cpu) -> None:
    """Lift one poll of the F9 boss-key initial release wait at 1010:07C4.

    The original loop is ``CMP byte [9907],01h; JE 07C4``.  Keep it as a
    one-iteration state-machine hook so the text-mode boss screen remains
    interactive and the outer viewer can publish/pump key-up events between
    polls.
    """
    ds = cpu.s.ds & 0xFFFF
    value = cpu.mem.rb(ds, 0x9907)
    _cmp_byte(cpu, value, 0x01)
    cpu.s.ip = 0x07C4 if value == 0x01 else 0x07CB


def run_boss_key_any_key_wait_gate_07d0(cpu) -> None:
    """Lift one poll of the boss-key any-key wait at 1010:07D0.

    The original loop is ``CMP byte [98C3],00h; JE 07D0``.  ``DS:98C3`` is
    cleared immediately before entering the loop and set by OVERKILL's keyboard
    path when a key should leave the fake DOS text screen.
    """
    ds = cpu.s.ds & 0xFFFF
    value = cpu.mem.rb(ds, 0x98C3)
    _cmp_byte(cpu, value, 0x00)
    cpu.s.ip = 0x07D0 if value == 0x00 else 0x07D7


def run_boss_key_return_key_release_wait_gate_07d7(cpu) -> None:
    """Lift one poll of the boss-key return-key release wait at 1010:07D7.

    This is the final ``CMP byte [9907],01h; JE 07D7`` gate before the original
    routine restores the game's video mode.
    """
    ds = cpu.s.ds & 0xFFFF
    value = cpu.mem.rb(ds, 0x9907)
    _cmp_byte(cpu, value, 0x01)
    cpu.s.ip = 0x07D7 if value == 0x01 else 0x07DE




def run_text_entry_prompt_loop_53c9(cpu, call_text_string, call_prompt_key_read) -> None:
    """Lift one iteration of the 1010:53C9 DOS text-entry prompt loop.

    This is intentionally a one-iteration state-machine hook, not the full
    prompt routine.  The hot path repeatedly redraws the prompt/current buffer,
    reads one DOS key through 5497, accepts printable ASCII into DS:229B..22A4,
    and jumps back to 53C9.  Rare edit/finish tails are left as original branch
    targets so they remain oracle-visible until their surrounding dispatches are
    classified.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    # 53C9: MOV BP,22A9 ; CALL 518C ; 53CF: MOV BP,229B ; CALL 518C
    s.bp = 0x22A9
    call_text_string(0x53CF)
    if (s.ip & 0xFFFF) != 0x53CF:
        raise RuntimeError(f"518C returned to unexpected IP {s.ip:04X} inside 53C9 prompt header draw")
    s.bp = 0x229B
    call_text_string(0x53D5)
    if (s.ip & 0xFFFF) != 0x53D5:
        raise RuntimeError(f"518C returned to unexpected IP {s.ip:04X} inside 53C9 prompt buffer draw")

    # 53D5: CALL 5497.  If DOS input blocks, 5497 leaves the machine at its
    # original INT 21h retry IP and propagates ConsoleInputWouldBlock.
    call_prompt_key_read(0x53D8)
    if (s.ip & 0xFFFF) != 0x53D8:
        raise RuntimeError(f"5497 returned to unexpected IP {s.ip:04X} inside 53C9 prompt loop")

    al = s.ax & 0xFF
    _cmp_byte(cpu, al, 0x08)
    if al == 0x08:
        s.ip = 0x5408
        return
    _cmp_byte(cpu, al, 0x0D)
    if al == 0x0D:
        s.ip = 0x541E
        return

    cursor = mem.rw(ds, 0x22B0)
    _cmp_word(cpu, cursor, 0x22A5)
    if cursor == 0x22A5:
        # Leave the bell helper/tail in original ASM for now.
        s.ip = 0x53FC
        return

    _cmp_byte(cpu, al, 0x20)
    if al < 0x20:
        s.ip = 0x53C9
        return
    _cmp_byte(cpu, al, 0x7A)
    if al > 0x7A:
        s.ip = 0x53C9
        return

    s.di = mem.rw(ds, 0x22B0)
    mem.wb(ds, s.di & 0xFFFF, al)
    _inc_mem_word_preserve_cf(cpu, ds, 0x22B0)
    s.ip = 0x53C9

def run_bios_keyboard_buffer_tail_sync_50ba(cpu) -> None:
    """Lift 1010:50BA, synchronize BIOS keyboard-buffer tail to head.

    OVERKILL uses this after prompt/menu reads to flush pending BIOS keyboard
    characters.  Final flags come from ``XOR AX,AX``; ``STI`` then sets IF.
    """
    from dos_re.cpu import IF

    s = cpu.s
    cpu.set_flag(IF, False)
    s.ax = 0
    cpu.set_logic_flags(0, 16)
    s.es = 0
    al = cpu.mem.rb(0, 0x041A)
    s.ax = (s.ax & 0xFF00) | al
    cpu.mem.wb(0, 0x041C, al)
    cpu.set_flag(IF, True)
    s.ip = cpu.pop()


def run_keyboard_state_clear_and_bios_tail_sync_50ab(cpu) -> None:
    """Lift 1010:50AB, clear OVERKILL key-state table then flush BIOS tail."""
    s = cpu.s
    ds = cpu.mem.rw(s.cs & 0xFFFF, 0x9596)
    s.es = ds & 0xFFFF
    s.di = 0x98C4
    s.ax = (s.ax & 0xFF00)
    cpu.set_logic_flags(0, 8)  # XOR AL,AL
    s.cx = 0x0080
    for _ in range(0x80):
        cpu.mem.wb(s.es & 0xFFFF, s.di & 0xFFFF, 0)
        s.di = (s.di - 1 if cpu.get_flag(DF) else s.di + 1) & 0xFFFF
    s.cx = 0
    run_bios_keyboard_buffer_tail_sync_50ba(cpu)

def _call_dos_int21_at(cpu, after_ip: int) -> None:
    """Run OVERKILL-visible DOS INT 21h from a lifted caller.

    The interpreter fetches ``CD 21`` before invoking the DOS shim, so a blocking
    console read rewinds IP by two bytes to the INT instruction.  Lifted callers
    set IP to the post-INT address before delegating so ``ConsoleInputWouldBlock``
    leaves the VM at the same resumable instruction boundary as interpreted ASM.
    """
    cpu.s.ip = after_ip & 0xFFFF
    if cpu.interrupt_handler is None:
        from dos_re.cpu import UnsupportedInstruction

        raise UnsupportedInstruction(f"INT 21h not hooked at {cpu.s.cs:04X}:{(after_ip - 2) & 0xFFFF:04X}")
    cpu.interrupt_handler(cpu, 0x21)


def run_temp_keyboard_vector_install_4e9f(cpu) -> None:
    """Lift 1010:4E9F, install OVERKILL's temporary INT 9 text-input handler.

    The helper saves the current INT 09h vector in ``DS:213A`` and then points the
    IVT at ``CS:4ED2``.  It is used by the DOS text-entry prompt around 5497; the
    stack push/pop scratch is preserved because full-memory hook verification
    compares the stack bytes too.
    """
    s = cpu.s
    mem = cpu.mem
    entry_ds = s.ds & 0xFFFF
    entry_es = s.es & 0xFFFF

    cpu.push(entry_ds)
    cpu.push(entry_es)

    s.ax = (0x35 << 8) | 0x09
    # DOS AH=35h: get vector AL -> ES:BX.
    s.bx = mem.rw(0, 0x09 * 4)
    s.es = mem.rw(0, 0x09 * 4 + 2)

    s.di = 0x213A
    mem.ww(entry_ds, 0x213A, s.es)
    mem.ww(entry_ds, 0x213C, s.bx)

    s.es = cpu.pop()
    cpu.push(entry_ds)
    cpu.push(s.cs & 0xFFFF)
    s.ds = cpu.pop()

    s.dx = 0x4ED2
    s.ax = (0x25 << 8) | 0x09
    # DOS AH=25h: set vector AL = DS:DX.
    mem.ww(0, 0x09 * 4, s.dx)
    mem.ww(0, 0x09 * 4 + 2, s.ds)

    s.ds = cpu.pop()
    s.ds = cpu.pop()
    s.ip = cpu.pop()


def run_temp_keyboard_vector_restore_4ebf(cpu) -> None:
    """Lift 1010:4EBF, restore the INT 9 vector saved by 4E9F."""
    s = cpu.s
    mem = cpu.mem
    entry_ds = s.ds & 0xFFFF

    cpu.push(entry_ds)
    s.di = 0x213A
    s.dx = mem.rw(entry_ds, 0x213C)
    s.ax = mem.rw(entry_ds, 0x213A)
    s.ds = s.ax & 0xFFFF
    s.ax = (0x25 << 8) | 0x09
    mem.ww(0, 0x09 * 4, s.dx)
    mem.ww(0, 0x09 * 4 + 2, s.ds)
    s.ds = cpu.pop()
    s.ip = cpu.pop()


def run_text_prompt_key_read_5497(cpu) -> None:
    """Lift 1010:5497, the DOS key read used by the text-entry prompt.

    The original temporarily restores the prior INT 9 vector before DOS AH=07h
    reads, then reinstalls OVERKILL's temporary handler before returning the
    character in AL.  Blocking reads remain resumable at the original INT 21h
    instruction IPs (54A7/54AF).
    """
    s = cpu.s
    ds = cpu.mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ds = ds & 0xFFFF

    cpu.push(0x549F)
    run_temp_keyboard_vector_restore_4ebf(cpu)
    if (s.ip & 0xFFFF) != 0x549F:
        raise RuntimeError(f"4EBF returned to unexpected IP {s.ip:04X} inside 5497")

    cpu.mem.ww(s.ds & 0xFFFF, 0x22B2, 0)
    s.ax = (0x07 << 8) | (s.ax & 0x00FF)
    _call_dos_int21_at(cpu, 0x54A9)
    al = s.ax & 0xFF
    _cmp_byte(cpu, al, 0)
    if al == 0:
        s.ax = (0x07 << 8) | al
        _call_dos_int21_at(cpu, 0x54B1)
        cpu.mem.ww(s.ds & 0xFFFF, 0x22B2, 1)
        al = s.ax & 0xFF

    cpu.mem.wb(s.ds & 0xFFFF, 0x22B4, al)
    cpu.push(s.ax & 0xFFFF)
    cpu.push(0x54BE)
    run_temp_keyboard_vector_install_4e9f(cpu)
    if (s.ip & 0xFFFF) != 0x54BE:
        raise RuntimeError(f"4E9F returned to unexpected IP {s.ip:04X} inside 5497")
    s.ax = cpu.pop()
    s.ip = cpu.pop()

def _wait_vga_status_bit3(cpu, *, want_set: bool) -> None:
    """Inline 1010:50C9-compatible VGA status wait used by menu parents.

    The address-facing 50C9 hook normally owns this behavior.  Differential
    verification can run this parent with passthrough/UI hooks removed, so keep a
    tiny local copy rather than falling back to a single original instruction.
    """
    cpu.s.dx = 0x03DA
    for _ in range(100000):
        value = cpu.port_reader(cpu, 0x03DA, 8) if cpu.port_reader else (0x08 if want_set else 0x00)
        cpu.set_reg8(0, value)
        result = value & 0x08
        cpu.set_logic_flags(result, 8)  # TEST AL,08h
        if (result != 0) == want_set:
            return
    raise RuntimeError("VGA status wait did not converge")


def _run_vga_retrace_wait_50c9_inline(cpu) -> None:
    """Run the pure 1010:50C9 retrace wait body to the near return.

    This mirrors ``overkill_wait_vga_retrace_50c9`` without importing from
    ``overkill.hooks`` (which would be circular because hooks import this
    module).
    """
    cs = cpu.s.cs & 0xFFFF
    inverted_order = cpu.mem.rb(cs, 0xCA5A) == 0x01
    _wait_vga_status_bit3(cpu, want_set=not inverted_order)
    _wait_vga_status_bit3(cpu, want_set=inverted_order)
    cpu.mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, 0xC9F0)
    cpu.s.ip = cpu.pop()

def _step_original_once(cpu, addr: tuple[int, int]) -> None:
    """Execute one original instruction at an address that also has a hook.

    Some menu hooks intentionally cover only the hot idle path.  When a real
    key/state branch is active, interpreting the original instruction stream is
    safer than duplicating rarely used transition logic.
    """
    saved_hook = cpu.replacement_hooks.pop(addr, None)
    saved_name = cpu.hook_names.get(addr)
    try:
        cpu.step()
    finally:
        if saved_hook is not None:
            cpu.replacement_hooks[addr] = saved_hook
        if saved_name is not None:
            cpu.hook_names[addr] = saved_name


def run_main_menu_idle_loop_558b(cpu) -> None:
    """Run one hot idle iteration of the main-menu wait loop at ``1010:558B``.

    The observed menu loop is mostly a polling/timing wrapper:

    * test a set of keyboard-state bytes for menu shortcuts;
    * when nothing is pressed, clear three animation deltas;
    * wait for retrace through ``50C9``;
    * increment the attract-mode counter ``DS:22BF``;
    * poll input through ``0162``; and
    * either loop back to ``558B`` or return when FIRE/SPACE is down.

    The non-idle branches are real menu transitions, so this hook optimizes only
    the exact no-key path and falls back to the original instruction stream for
    everything else.  Like the selector hook, it executes one poll iteration
    rather than spinning internally, which keeps the frontend responsive and lets
    asynchronous timer/sound work run between iterations.
    """
    s = cpu.s
    ds = s.ds & 0xFFFF
    mem = cpu.mem

    # Fast-path only the branch pattern observed in the passive main menu.
    for off in (0x98E9, 0x98E8, 0x98E2, 0x98D7, 0x98F6, 0x98DC, 0x98DB, 0x98C5, 0x9907):
        if mem.rb(ds, off) == 0x01:
            _step_original_once(cpu, (s.cs & 0xFFFF, 0x558B))
            return

    # Do not pre-fallback on the attract counter.  The verified boundary for this
    # parent explicitly includes the post-increment expiry continuation at 55FD,
    # so the hook must reproduce the increment/retrace side effects before
    # stopping there.

    retrace = cpu.replacement_hooks.get((0x1010, 0x50C9), _run_vga_retrace_wait_50c9_inline)
    poll_input = cpu.replacement_hooks.get((0x1010, 0x0162), run_input_poll_0162)

    # MOV word [22B9/22BB/22BD],0 does not affect flags.
    mem.ww(ds, 0x22B9, 0)
    mem.ww(ds, 0x22BB, 0)
    mem.ww(ds, 0x22BD, 0)

    cpu.push(0x55F1)
    retrace(cpu)
    if s.ip != 0x55F1:
        raise RuntimeError(f"50C9 returned to unexpected IP {s.ip:04X} inside 558B menu idle loop")

    counter = _inc_mem_word_preserve_cf(cpu, ds, 0x22BF)
    _cmp_word(cpu, counter, 0x02EE)
    if counter >= 0x02EE:
        # Should be prevented by the pre-check above.  If a custom retrace hook
        # mutated the counter, land at the original continuation instead of
        # guessing the transition path.
        s.ip = 0x55FD
        return

    cpu.push(0x5616)
    poll_input(cpu)
    if s.ip != 0x5616:
        raise RuntimeError(f"0162 returned to unexpected IP {s.ip:04X} inside 558B menu idle loop")

    buttons = mem.rb(ds, 0x98BE)
    _cmp_byte(cpu, buttons, 0x10)
    if buttons == 0x10:
        s.ip = cpu.pop()
    else:
        s.ip = 0x558B


def run_menu_fire_release_wait_d390(cpu) -> None:
    """Lift one poll of the 1010:D390 FIRE-release wait gate.

    The original main-menu/planet transition code waits in a tight loop while
    FIRE/SPACE remains held::

        D390 CALL 0162
        D393 TEST byte [98BE],10h
        D398 JNZ D390

    Keep it as a one-iteration state-machine hook so the outer runtime can
    yield/pump input instead of burning interpreted ASM while the key is held.
    """
    poll_input = cpu.replacement_hooks.get((0x1010, 0x0162), run_input_poll_0162)
    cpu.push(0xD393)
    poll_input(cpu)
    if cpu.s.ip != 0xD393:
        raise RuntimeError(f"0162 returned to unexpected IP {cpu.s.ip:04X} inside D390 fire-release wait")
    ds = cpu.s.ds & 0xFFFF
    buttons = cpu.mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(buttons & 0x10, 8)
    cpu.s.ip = 0xD390 if (buttons & 0x10) else 0xD39A


def run_selector_input_release_wait_d434(cpu) -> None:
    """Lift one poll of the 1010:D434 selector input-release wait gate.

    This gate is reached after the level/planet transition visuals.  It waits
    until the current selector/fire input is released before falling into the
    normal D445 selector loop.  The hook intentionally performs only one poll so
    interactive play remains responsive.
    """
    ds = cpu.s.ds & 0xFFFF
    value = cpu.mem.rb(ds, 0x98E4)
    _cmp_byte(cpu, value, 0x01)
    if value == 0x01:
        cpu.s.ip = 0xD434
        return

    poll_input = cpu.replacement_hooks.get((0x1010, 0x0162), run_input_poll_0162)
    cpu.push(0xD43E)
    poll_input(cpu)
    if cpu.s.ip != 0xD43E:
        raise RuntimeError(f"0162 returned to unexpected IP {cpu.s.ip:04X} inside D434 selector-release wait")
    buttons = cpu.mem.rb(ds, 0x98BE)
    _cmp_byte(cpu, buttons, 0x00)
    cpu.s.ip = 0xD43B if buttons != 0 else 0xD445


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
