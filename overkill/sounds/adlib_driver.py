"""OVERKILL optional AdLib driver bootstrap/runtime helpers.

The optional Sound Images AdLib driver is loaded by the original startup at
``2032:0000``.  Keeping the music driver original is useful, but some helper
routines are dominated by hardware delay / no-op polling work.  This module
lifts those mechanical parts while leaving the actual bytecode/music sequencing
available as the oracle until the whole driver is understood.
"""
from __future__ import annotations

from dos_re.cpu import CF
from ._asm import cmp_byte, dec_mem_byte_preserve_cf, in_al, out_value
from .loaded_driver import OPTIONAL_SOUND_DRIVER_SEGMENT

# 2032:04E9 AdLib/YM3812 probe.  It starts by saving BX/CX/DX/DS and then writes
# timer registers through 0557 before checking the status bits from port 388h.
SIG_ADLIB_DETECT_2032_04E9 = bytes.fromhex(
    "53 51 52 1e 0e 1f 8b 16 0e 00 b8 01 00 e8 5e 00"
)

SIG_ADLIB_FAR_ENTRY_2032_0000 = bytes.fromhex("e8 60 00 cb")

SIG_ADLIB_DRIVER_TICK_2032_0063 = bytes.fromhex(
    "50 53 51 52 57 56 1e 0e 1f be 62 00 80 3c 00 75 51"
)

# 2032:0557 writes AX as YM3812 register/value pair (AL=register, AH=value) via
# ports 388h/389h and calls the 0579 PIT/speaker hardware delay twice.  The delay
# has no game-visible purpose beyond port side effects and final flags.
SIG_ADLIB_WRITE_2032_0557 = bytes.fromhex(
    "53 52 8b 16 0e 00 ee bb fc 1f e8 15 00 8a c4 42 ee"
)

# 2032:02C9 and 2032:02F6 are per-channel modulation helpers.  During the main
# menu music they very often take trivial disabled/no-op exits, which previously
# made RET at 0302 the single hottest interpreted AdLib instruction.
SIG_ADLIB_CHANNEL_TICK_2032_00CD = bytes.fromhex(
    "80 3e 5f 00 00 75 22 8a 45 10 0a c0 74 1b 8b 5d 0c"
)
SIG_ADLIB_PAGE_GATE_2032_0409 = bytes.fromhex(
    "32 e4 3a 26 09 00 75 06 a0 08 00 a2 5f 00"
)
SIG_ADLIB_CHANNEL_HELPER_2032_0244 = bytes.fromhex(
    "8a 45 13 0a c0 74 f8 02 05 88 05"
)
SIG_ADLIB_CHANNEL_HELPER_2032_02AA = bytes.fromhex(
    "80 3f 82 74 19 8b 75 02 8a 44 0e 0a c0 74 0f"
)
SIG_ADLIB_SET_INSTRUMENT_2032_0181 = bytes.fromhex(
    "2c a0 3a 45 04 75 03 e9 6c ff 53 88 45 04"
)
SIG_ADLIB_NOTE_FREQUENCY_2032_024F = bytes.fromhex(
    "53 56 8a 05 02 45 12 32 e4 8b f0 8a 9c 49 07"
)
SIG_ADLIB_CHANNEL_MOD_A_2032_02C9 = bytes.fromhex(
    "32 c0 3a 45 1d 74 32 3a 45 1e 74 2d fe 4d 1e 74 28"
)
SIG_ADLIB_CHANNEL_MOD_B_2032_02F6 = bytes.fromhex(
    "32 c0 3a 45 18 74 06 fe 4d 18 74 01 c3 3a 45 19 74"
)


def _call_adlib_write(cpu, ax: int, return_ip: int) -> None:
    """Call the lifted 2032:0557 helper with the original near-call shape."""
    cpu.s.ax = ax & 0xFFFF
    cpu.push(return_ip & 0xFFFF)
    cpu.s.ip = 0x0557
    run_adlib_write_2032_0557(cpu)
    if cpu.s.ip != (return_ip & 0xFFFF):
        raise RuntimeError(
            f"2032:0557 returned to unexpected IP {cpu.s.ip:04X}, expected {return_ip:04X}"
        )


def _emulate_0579_delay_side_effects(cpu, compare_threshold: int) -> None:
    """Model the port-visible tail of 2032:0579 without the busy wait.

    The original delay temporarily programs PIT channel 2, sets speaker-control
    bits 0+1, then clears bit 0 before returning.  AX is pushed/popped by 0579,
    so only port side effects and the final AND flags are observable by callers.
    """
    ax0 = cpu.s.ax & 0xFFFF
    out_value(cpu, 0x43, 0xB6)
    al = (in_al(cpu, 0x61) | 0x03) & 0xFF
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)
    out_value(cpu, 0x61, al)
    # The delay routine always programs PIT channel 2 with 1FFFh; BX holds only
    # the later comparison threshold (1FFCh or 1FECh).
    _ = compare_threshold
    out_value(cpu, 0x42, 0xFF)
    out_value(cpu, 0x42, 0x1F)
    out_value(cpu, 0x43, 0x86)
    out_value(cpu, 0x43, 0xB6)

    # The real loop samples channel 2 until the counter reaches the requested
    # range.  The VM's port-42 reads are synthetic and not game data, so skip the
    # wait and model the final speaker-control clear.
    al = in_al(cpu, 0x61)
    al &= 0xFE
    cpu.set_reg8(0, al)
    cpu.set_logic_flags(al, 8)
    out_value(cpu, 0x61, al)
    cpu.s.ax = ax0


def _run_original_near(cpu, entry_ip: int, *, max_steps: int = 20_000) -> None:
    """Interpret the original near routine when a lifted fast path does not apply."""
    key = (cpu.s.cs & 0xFFFF, entry_ip & 0xFFFF)
    saved_hook = cpu.replacement_hooks.pop(key, None)
    saved_name = cpu.hook_names.get(key)
    ss = cpu.s.ss & 0xFFFF
    frame_sp = cpu.s.sp & 0xFFFF
    ret_ip = cpu.mem.rw(ss, frame_sp)
    return_sp = (frame_sp + 2) & 0xFFFF
    ret_cs = cpu.s.cs & 0xFFFF
    try:
        for _ in range(max_steps):
            if cpu.s.sp == return_sp and cpu.addr() == (ret_cs, ret_ip):
                return
            cpu.step()
    finally:
        if saved_hook is not None:
            cpu.replacement_hooks[key] = saved_hook
        if saved_name is not None:
            cpu.hook_names[key] = saved_name
    raise RuntimeError(
        f"original 2032:{entry_ip:04X} AdLib helper did not near-return "
        f"(cs:ip={cpu.s.cs:04X}:{cpu.s.ip:04X})"
    )


def run_adlib_far_entry_2032_0000(cpu) -> None:
    """Lift the loaded driver's far-call entry ``2032:0000``.

    The entry is only ``CALL 0063`` followed by ``RETF``.  Hooking it removes
    two interpreted instructions from every optional-driver timer tick and gives
    the lifted ``1010:06E5`` ISR a clean way to preserve the original far-call
    stack shape while still using the already lifted ``0063`` driver tick.
    """
    handler = cpu.replacement_hooks.get((OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0063), run_adlib_driver_tick_2032_0063)
    cpu.push(0x0003)
    cpu.s.ip = 0x0063
    handler(cpu)
    if cpu.s.ip != 0x0003:
        raise RuntimeError(f"2032:0063 returned to unexpected IP {cpu.s.ip:04X} inside 2032:0000")
    cpu.s.ip = cpu.pop()
    cpu.s.cs = cpu.pop()


def run_adlib_detect_2032_04e9(cpu) -> None:
    """Lift the loaded AdLib driver's hardware probe at ``2032:04E9``.

    This probe is still evidence-sensitive enough that the safest behavior is
    to run the interpreted oracle directly.  We keep the hook registered so the
    exact boundary remains documented and regression-tested, but defer the body
    to the original ASM until the remaining stack/branch details are fully
    proven.
    """
    _run_original_near(cpu, 0x04E9, max_steps=120_000)


def run_adlib_write_2032_0557(cpu) -> None:
    """Lift 2032:0557 YM3812 register write plus PIT-delay side effects."""
    s = cpu.s
    ss = s.ss & 0xFFFF
    sp0 = s.sp & 0xFFFF
    bx0 = s.bx & 0xFFFF
    dx0 = s.dx & 0xFFFF
    ax = s.ax & 0xFFFF
    dx = cpu.mem.rw(s.ds & 0xFFFF, 0x000E)

    out_value(cpu, dx, ax & 0xFF)
    _emulate_0579_delay_side_effects(cpu, 0x1FFC)
    out_value(cpu, (dx + 1) & 0xFFFF, (ax >> 8) & 0xFF)
    _emulate_0579_delay_side_effects(cpu, 0x1FEC)

    # Preserve dead stack scratch left by PUSH BX/PUSH DX and the two CALL 0579
    # frames.  This is below the restored SP, but keeping it stable makes
    # full-memory hook verification less noisy.
    cpu.mem.ww(ss, (sp0 - 0x02) & 0xFFFF, bx0)
    cpu.mem.ww(ss, (sp0 - 0x04) & 0xFFFF, dx0)
    cpu.mem.ww(ss, (sp0 - 0x06) & 0xFFFF, 0x056E)
    ax_out = ((ax & 0xFF00) | ((ax >> 8) & 0x00FF)) & 0xFFFF
    cpu.mem.ww(ss, (sp0 - 0x08) & 0xFFFF, ax_out)

    s.ax = ax_out
    s.bx = bx0
    s.dx = dx0
    s.flags = (s.flags | 0x0010) & 0xFFFF
    s.ip = cpu.pop()


def run_adlib_page_gate_2032_0409(cpu) -> None:
    """Fast-path the loaded driver's common page/pause gate at ``2032:0409``.

    In the menu-music hot path byte ``0009h`` is non-zero and ``005Fh`` is
    already zero, so the original routine just clears AH, compares AL/AH, jumps
    to a RET at 04A3 and returns.  Non-trivial pattern/page transitions still
    fall back to the original routine.
    """
    ds = cpu.s.ds & 0xFFFF
    if cpu.mem.rb(ds, 0x0009) != 0 and cpu.mem.rb(ds, 0x005F) == 0:
        cpu.set_reg8(4, 0)  # XOR AH,AH
        cpu.set_reg8(0, 0)  # MOV AL,[005F]
        cmp_byte(cpu, 0, 0)
        cpu.s.ip = cpu.pop()
        return
    _run_original_near(cpu, 0x0409)


def run_adlib_set_instrument_2032_0181(cpu) -> None:
    """Lift the 2032:0181 instrument-select command body.

    The bytecode sequencer jumps here after reading a command in the A0h..DFh
    range.  The routine selects the instrument table, writes the associated
    operator registers, updates channel state, and jumps back to the 00F7 command
    loop.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    di = s.di & 0xFFFF

    al0 = s.ax & 0xFF
    inst = (al0 - 0xA0) & 0xFF
    s.ax = (s.ax & 0xFF00) | inst
    cpu.set_sub_flags(al0, 0xA0, al0 - 0xA0, 8)
    current = mem.rb(ds, (di + 0x04) & 0xFFFF)
    cmp_byte(cpu, inst, current)
    if inst == current:
        s.ip = 0x00F7
        return

    bx0 = s.bx & 0xFFFF
    cpu.push(bx0)
    mem.wb(ds, (di + 0x04) & 0xFFFF, inst)
    cpu.set_reg8(4, 0)
    cpu.set_logic_flags(0, 8)

    ax = inst
    ax = ((ax << 1) & 0x00FF)
    ax = ((ax << 1) & 0x00FF)
    ax = ((ax << 1) & 0xFFFF)
    ax = ((ax << 1) & 0xFFFF)
    s.ax = ax
    si = (0x0869 + ax) & 0xFFFF
    s.si = si
    mem.ww(ds, (di + 0x02) & 0xFFFF, si)

    dx = mem.rw(ds, (di + 0x05) & 0xFFFF)
    s.dx = dx
    dl = dx & 0xFF
    dh = (dx >> 8) & 0xFF
    voice = mem.rb(ds, (di + 0x07) & 0xFFFF)

    for ret, reg_base, value_off in (
        (0x01AD, 0x60 + dl, 0),
        (0x01B7, 0x60 + dh, 1),
        (0x01C1, 0x80 + dl, 2),
        (0x01CB, 0x80 + dh, 3),
        (0x01D5, 0xE0 + dl, 6),
        (0x01DF, 0xE0 + dh, 7),
        (0x01EA, 0xC0 + voice, 9),
        (0x01F4, 0x20 + dl, 4),
        (0x01FE, 0x20 + dh, 5),
    ):
        ax = ((mem.rb(ds, (si + value_off) & 0xFFFF) << 8) | (reg_base & 0xFF)) & 0xFFFF
        _call_adlib_write(cpu, ax, ret)

    bl = mem.rb(ds, (si + 0x0A) & 0xFFFF)
    s.bx = bl
    cpu.set_logic_flags(bl & 0x007F, 16)  # AND BX,007Fh
    bx = bl & 0x007F
    ah = mem.rb(ds, (bx + 0x06C9) & 0xFFFF)
    al = mem.rb(ds, (si + 0x0C) & 0xFFFF)
    al = (al << 1) & 0xFF
    al = (al << 1) & 0xFF
    al &= 0xC0
    ah |= al
    _call_adlib_write(cpu, ((ah << 8) | ((0x40 + dl) & 0xFF)) & 0xFFFF, 0x021A)

    bl = mem.rb(ds, (si + 0x0B) & 0xFFFF)
    mem.wb(ds, (di + 0x0E) & 0xFFFF, bl)
    s.bx = bl
    cpu.set_logic_flags(bl & 0x007F, 16)
    bx = bl & 0x007F
    ah = mem.rb(ds, (bx + 0x06C9) & 0xFFFF)
    al = mem.rb(ds, (si + 0x0C) & 0xFFFF)
    al = ((al >> 1) | ((al & 0x01) << 7)) & 0xFF
    al = ((al >> 1) | ((al & 0x01) << 7)) & 0xFF
    al &= 0xC0
    ah |= al
    _call_adlib_write(cpu, ((ah << 8) | ((0x40 + dh) & 0xFF)) & 0xFFFF, 0x0239)

    al = mem.rb(ds, (si + 0x08) & 0xFFFF)
    s.ax = (s.ax & 0xFF00) | al
    mem.wb(ds, (di + 0x12) & 0xFFFF, al)
    s.bx = cpu.pop()
    s.ip = 0x00F7


def run_adlib_note_frequency_2032_024f(cpu) -> None:
    """Lift 2032:024F note/frequency register update."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    di = s.di & 0xFFFF
    bx0 = s.bx & 0xFFFF
    si0 = s.si & 0xFFFF
    cpu.push(bx0)
    cpu.push(si0)

    al = (mem.rb(ds, di) + mem.rb(ds, (di + 0x12) & 0xFFFF)) & 0xFF
    s.ax = al
    s.si = al
    bl = mem.rb(ds, (s.si + 0x0749) & 0xFFFF)
    # The original MOV BL,[SI+0749] mutates the live register file before the
    # first YM3812 call, so keep BX's high byte and replace BL in place.
    s.bx = (s.bx & 0xFF00) | bl
    al2 = (al << 1) & 0xFF
    si = (0x07A9 + al2) & 0xFFFF
    ax = mem.rw(ds, si)
    ax = (ax + mem.rw(ds, (di + 0x1A) & 0xFFFF)) & 0xFFFF
    mem.ww(ds, (di + 0x14) & 0xFFFF, ax)
    al_freq = ax & 0xFF
    ax = ((((ax >> 8) | bl) & 0xFF) << 8) | al_freq

    # The original pushes the OR'ed frequency word around the first YM3812
    # write so the old value remains visible on the stack scratch below SP.
    cpu.push(ax)
    _call_adlib_write(cpu, ((al_freq << 8) | (mem.rb(ds, (di + 0x07) & 0xFFFF) | 0xA0)) & 0xFFFF, 0x0279)
    ax = cpu.pop()
    s.ax = ax

    ax2 = ((ax & 0xFF00) | (mem.rb(ds, (di + 0x07) & 0xFFFF) | 0xB0)) & 0xFFFF
    mem.ww(ds, (di + 0x08) & 0xFFFF, ax2)
    _call_adlib_write(cpu, ((((ax2 >> 8) | 0x20) << 8) | (ax2 & 0x00FF)) & 0xFFFF, 0x0288)

    al_final = mem.rb(ds, (di + 0x1D) & 0xFFFF)
    s.ax = (s.ax & 0xFF00) | al_final
    mem.wb(ds, (di + 0x1E) & 0xFFFF, al_final)
    s.si = cpu.pop()
    s.bx = cpu.pop()
    s.ip = cpu.pop()


def run_adlib_channel_helper_2032_0244(cpu) -> None:
    """Lift 2032:0244 per-channel accumulator helper."""
    ds = cpu.s.ds & 0xFFFF
    di = cpu.s.di & 0xFFFF
    value = cpu.mem.rb(ds, (di + 0x13) & 0xFFFF)
    cpu.set_reg8(0, value)
    cpu.set_logic_flags(value, 8)
    if value == 0:
        cpu.s.ip = cpu.pop()
        return
    base = cpu.mem.rb(ds, di)
    result = base + value
    cpu.set_reg8(0, result & 0xFF)
    cpu.set_add_flags(value, base, result, 8)
    cpu.mem.wb(ds, di, result & 0xFF)
    cpu.s.ip = cpu.pop()


def run_adlib_channel_helper_2032_02aa(cpu) -> None:
    """Lift 2032:02AA pending-note/key-on helper."""
    ds = cpu.s.ds & 0xFFFF
    di = cpu.s.di & 0xFFFF
    bx = cpu.s.bx & 0xFFFF
    stream_byte = cpu.mem.rb(ds, bx)
    cmp_byte(cpu, stream_byte, 0x82)
    if stream_byte == 0x82:
        cpu.s.ip = cpu.pop()
        return
    si_candidate = cpu.mem.rw(ds, (di + 0x02) & 0xFFFF)
    cpu.s.si = si_candidate
    note_state = cpu.mem.rb(ds, (si_candidate + 0x0E) & 0xFFFF)
    cpu.set_reg8(0, note_state)
    cpu.set_logic_flags(note_state, 8)
    if note_state == 0:
        cpu.s.ip = cpu.pop()
        return
    delay = cpu.mem.rb(ds, (di + 0x01) & 0xFFFF)
    cmp_byte(cpu, note_state, delay)
    if note_state != delay:
        cpu.s.ip = cpu.pop()
        return
    _call_adlib_write(cpu, cpu.mem.rw(ds, (di + 0x08) & 0xFFFF), 0x02C4)
    cpu.mem.wb(ds, (di + 0x13) & 0xFFFF, 0)
    cpu.s.ip = cpu.pop()


def _adlib_apply_frequency_modulation(cpu, *, ax: int, cx: int, delta_off: int, return_ip: int) -> None:
    ds = cpu.s.ds & 0xFFFF
    di = cpu.s.di & 0xFFFF
    ax = (ax + cpu.mem.rw(ds, (di + delta_off) & 0xFFFF)) & 0xFFFF
    ah = (ax >> 8) & 0xFF
    ah &= 0x03
    ax = (ah << 8) | (ax & 0xFF)
    if ax > 0x03EC:
        ax >>= 1
        cx = (cx & 0x00FF) | ((((cx >> 8) + 0x04) & 0xFF) << 8)
    elif ax <= 0x01F6:
        ax = (ax << 1) & 0xFFFF
        cx = (cx & 0x00FF) | ((((cx >> 8) - 0x04) & 0xFF) << 8)
    ah = (ax >> 8) & 0xFF
    ah &= 0x03
    ax = (ah << 8) | (ax & 0xFF)
    cpu.mem.ww(ds, (di + 0x14) & 0xFFFF, ax)

    voice = cpu.mem.rb(ds, (di + 0x07) & 0xFFFF)
    _call_adlib_write(cpu, (((ax & 0xFF) << 8) | ((voice + 0xA0) & 0xFF)) & 0xFFFF, 0x0342)
    ah = (((ax >> 8) & 0xFF) | ((cx >> 8) & 0xFF)) & 0xFF
    ax2 = (ah << 8) | ((voice + 0xB0) & 0xFF)
    cpu.mem.ww(ds, (di + 0x08) & 0xFFFF, ax2)
    _call_adlib_write(cpu, (((ah | 0x20) << 8) | ((voice + 0xB0) & 0xFF)) & 0xFFFF, return_ip)


def run_adlib_channel_mod_a_2032_02c9(cpu) -> None:
    """Lift 2032:02C9 per-channel pitch modulation helper."""
    ds = cpu.s.ds & 0xFFFF
    di = cpu.s.di & 0xFFFF
    cpu.set_reg8(0, 0)
    cpu.set_logic_flags(0, 8)
    value = cpu.mem.rb(ds, (di + 0x1D) & 0xFFFF)
    cmp_byte(cpu, 0, value)
    if value == 0:
        cpu.s.ip = cpu.pop()
        return
    counter = cpu.mem.rb(ds, (di + 0x1E) & 0xFFFF)
    cmp_byte(cpu, 0, counter)
    if counter == 0:
        cpu.s.ip = cpu.pop()
        return
    counter = dec_mem_byte_preserve_cf(cpu, ds, (di + 0x1E) & 0xFFFF)
    if counter == 0:
        cpu.s.ip = cpu.pop()
        return
    cx0 = cpu.s.cx & 0xFFFF
    cpu.push(cx0)
    cx = cpu.mem.rw(ds, (di + 0x08) & 0xFFFF)
    cx = (cx & 0x00FF) | (((cx >> 8) & 0x1C) << 8)
    ax = cpu.mem.rw(ds, (di + 0x14) & 0xFFFF)
    _adlib_apply_frequency_modulation(cpu, ax=ax, cx=cx, delta_off=0x1C, return_ip=0x0353)
    cpu.s.cx = cpu.pop()
    cpu.s.ip = cpu.pop()


def run_adlib_channel_mod_b_2032_02f6(cpu) -> None:
    """Lift 2032:02F6 per-channel secondary pitch modulation helper."""
    ds = cpu.s.ds & 0xFFFF
    di = cpu.s.di & 0xFFFF
    cpu.set_reg8(0, 0)
    cpu.set_logic_flags(0, 8)
    first = cpu.mem.rb(ds, (di + 0x18) & 0xFFFF)
    cmp_byte(cpu, 0, first)
    if first != 0:
        first = dec_mem_byte_preserve_cf(cpu, ds, (di + 0x18) & 0xFFFF)
        if first != 0:
            cpu.s.ip = cpu.pop()
            return
    second = cpu.mem.rb(ds, (di + 0x19) & 0xFFFF)
    cmp_byte(cpu, 0, second)
    if second == 0:
        cpu.s.ip = cpu.pop()
        return
    dec_mem_byte_preserve_cf(cpu, ds, (di + 0x19) & 0xFFFF)
    cx0 = cpu.s.cx & 0xFFFF
    cpu.push(cx0)
    cx = cpu.mem.rw(ds, (di + 0x08) & 0xFFFF)
    cx = (cx & 0x00FF) | (((cx >> 8) & 0x1C) << 8)
    ax = cpu.mem.rw(ds, (di + 0x14) & 0xFFFF)
    _adlib_apply_frequency_modulation(cpu, ax=ax, cx=cx, delta_off=0x16, return_ip=0x0353)
    cpu.s.cx = cpu.pop()
    cpu.s.ip = cpu.pop()


def run_adlib_channel_tick_2032_00cd(cpu) -> None:
    """Fast-path the loaded AdLib driver's common per-channel idle tick.

    2032:00CD is the channel bytecode sequencer.  When the global countdown
    byte at 000Dh is nonzero, most main-menu timer ticks only test whether the
    channel is active and then run the disabled modulation helpers.  Model that
    hot no-op path directly and fall back to the original routine for note/command
    advancement or enabled modulation.
    """
    ds = cpu.s.ds & 0xFFFF
    di = cpu.s.di & 0xFFFF

    pause = cpu.mem.rb(ds, 0x005F)
    cmp_byte(cpu, pause, 0)
    if pause != 0:
        cpu.s.ip = cpu.pop()
        return

    active = cpu.mem.rb(ds, (di + 0x10) & 0xFFFF)
    cpu.set_reg8(0, active)
    cpu.set_logic_flags(active, 8)  # OR AL,AL
    if active == 0:
        cpu.s.ip = cpu.pop()
        return

    cpu.s.bx = cpu.mem.rw(ds, (di + 0x0C) & 0xFFFF)
    gate = cpu.mem.rb(ds, 0x000D)
    cmp_byte(cpu, gate, 0)

    mod_a_delay = cpu.mem.rb(ds, (di + 0x1D) & 0xFFFF)
    mod_b_delay_a = cpu.mem.rb(ds, (di + 0x18) & 0xFFFF)
    mod_b_delay_b = cpu.mem.rb(ds, (di + 0x19) & 0xFFFF)

    if gate != 0:
        if mod_a_delay == 0 and mod_b_delay_a == 0 and mod_b_delay_b == 0:
            # CALL 02C9 takes its disabled exit, then CALL 02F6 takes its
            # disabled exit.  Both leave AL=0; final flags are from CMP AL,[DI+19].
            cpu.set_reg8(0, 0)
            cmp_byte(cpu, 0, mod_a_delay)
            cmp_byte(cpu, 0, mod_b_delay_a)
            cmp_byte(cpu, 0, mod_b_delay_b)
            cpu.mem.ww(cpu.s.ss & 0xFFFF, (cpu.s.sp - 2) & 0xFFFF, 0x00F6)
            cpu.s.ip = cpu.pop()
            return
    else:
        # Hot menu-music countdown path:
        #   DEC [DI+1]; JZ advance-command; CALL 0244; CALL 02AA; CALL 02C9; CALL 02F6; RET
        # When the countdown remains non-zero and all four helpers take their
        # no-op exits, this is pure timer bookkeeping with no YM3812 writes.
        old_delay = cpu.mem.rb(ds, (di + 0x01) & 0xFFFF)
        old_cf = cpu.get_flag(CF)
        new_delay_full = old_delay - 1
        new_delay = new_delay_full & 0xFF
        if new_delay != 0:
            # 0244: MOV AL,[DI+13h]; OR AL,AL; JZ RET.
            helper_0244 = cpu.mem.rb(ds, (di + 0x13) & 0xFFFF)
            # 02AA no-op path: current stream byte is not 82h and the selected
            # instrument/operator state byte at [SI+0Eh] is zero.
            stream_byte = cpu.mem.rb(ds, cpu.s.bx & 0xFFFF)
            si_candidate = cpu.mem.rw(ds, (di + 0x02) & 0xFFFF)
            note_state = cpu.mem.rb(ds, (si_candidate + 0x0E) & 0xFFFF)
            if (
                helper_0244 == 0
                and stream_byte != 0x82
                and note_state == 0
                and mod_a_delay == 0
                and mod_b_delay_a == 0
                and mod_b_delay_b == 0
            ):
                cpu.mem.wb(ds, (di + 0x01) & 0xFFFF, new_delay)
                cpu.set_sub_flags(old_delay, 1, new_delay_full, 8)
                cpu.set_flag(CF, old_cf)
                # CALL 0244 leaves AL=0 and ZF=1.  CALL 02AA then leaves SI at
                # [DI+2], AL=0 and ZF=1 from OR AL,AL.  The two modulation
                # calls finally leave flags from CMP AL,[DI+19].
                cpu.s.si = si_candidate
                cpu.set_reg8(0, 0)
                cmp_byte(cpu, stream_byte, 0x82)
                cpu.set_logic_flags(0, 8)
                cmp_byte(cpu, 0, mod_a_delay)
                cmp_byte(cpu, 0, mod_b_delay_a)
                cmp_byte(cpu, 0, mod_b_delay_b)
                cpu.mem.ww(cpu.s.ss & 0xFFFF, (cpu.s.sp - 2) & 0xFFFF, 0x00F6)
                cpu.s.ip = cpu.pop()
                return

    _run_original_near(cpu, 0x00CD)


def run_adlib_driver_tick_2032_0063(cpu) -> None:
    """Lift the loaded AdLib driver's top-level timer tick at 2032:0063.

    This keeps the bytecode/channel routines as the oracle for non-trivial music
    events, but removes the fixed save/restore scaffolding and batches the nine
    per-channel calls through the lifted 00CD fast path.
    """
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    sp0 = s.sp & 0xFFFF
    ret_ip = mem.rw(ss, sp0)

    ax0, bx0, cx0, dx0 = s.ax & 0xFFFF, s.bx & 0xFFFF, s.cx & 0xFFFF, s.dx & 0xFFFF
    di0, si0, ds0 = s.di & 0xFFFF, s.si & 0xFFFF, s.ds & 0xFFFF

    # Preserve the dead stack shape left by the original PUSH register prologue.
    for index, value in enumerate((ax0, bx0, cx0, dx0, di0, si0, ds0), start=1):
        mem.ww(ss, (sp0 - index * 2) & 0xFFFF, value)

    s.ds = cs  # PUSH CS; POP DS
    s.si = 0x0062
    busy = mem.rb(s.ds, s.si)
    cmp_byte(cpu, busy, 0)
    if busy != 0:
        s.ax, s.bx, s.cx, s.dx = ax0, bx0, cx0, dx0
        s.di, s.si, s.ds = di0, si0, ds0
        s.ip = ret_ip
        s.sp = (sp0 + 2) & 0xFFFF
        return

    # INC byte ptr [0062].
    old = busy
    mem.wb(s.ds, s.si, (old + 1) & 0xFF)
    cpu.set_add_flags(old, 1, old + 1, 8)

    # CALL 0409; use its lifted hot no-op path and keep the original as oracle
    # for actual pattern/page transitions.
    mem.ww(ss, (s.sp - 2) & 0xFFFF, 0x0079)
    cpu.push(0x0079)
    s.ip = 0x0409
    run_adlib_page_gate_2032_0409(cpu)
    if s.ip != 0x0079:
        raise RuntimeError(f"2032:0409 returned to unexpected IP {s.ip:04X}")

    # DEC byte ptr [000D].
    old = mem.rb(s.ds, 0x000D)
    value = (old - 1) & 0xFF
    mem.wb(s.ds, 0x000D, value)
    cpu.set_sub_flags(old, 1, old - 1, 8)

    for ret, di in (
        (0x0083, 0x05A9), (0x0089, 0x05C9), (0x008F, 0x05E9),
        (0x0095, 0x0609), (0x009B, 0x0629), (0x00A1, 0x0649),
        (0x00A7, 0x0669), (0x00AD, 0x0689), (0x00B3, 0x06A9),
    ):
        s.di = di
        mem.ww(ss, (s.sp - 2) & 0xFFFF, ret)
        cpu.push(ret)
        s.ip = 0x00CD
        run_adlib_channel_tick_2032_00cd(cpu)
        if s.ip != ret:
            raise RuntimeError(f"2032:00CD returned to unexpected IP {s.ip:04X}, expected {ret:04X}")

    gate = mem.rb(s.ds, 0x000D)
    cmp_byte(cpu, gate, 0)
    if gate == 0:
        al = mem.rb(s.ds, 0x000C)
        s.ax = (s.ax & 0xFF00) | al
        mem.wb(s.ds, 0x000D, al)
    mem.wb(s.ds, 0x0062, 0)

    s.ax, s.bx, s.cx, s.dx = ax0, bx0, cx0, dx0
    s.di, s.si, s.ds = di0, si0, ds0
    s.ip = ret_ip
    s.sp = (sp0 + 2) & 0xFFFF
