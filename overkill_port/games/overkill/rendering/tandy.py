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
    signature_306f: bytes
    signature_33af: bytes
    signature_33b2: bytes
    signature_34ad: bytes
    signature_34c5: bytes
    signature_34d8: bytes
    signature_3542: bytes
    signature_35aa: bytes
    signature_36a2: bytes
    signature_60c5: bytes
    signature_35cc: bytes
    signature_356c: bytes
    signature_3657: bytes
    signature_0f0b: bytes
    signature_0fa3: bytes
    signature_0fe4: bytes
    signature_30b0: bytes


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


def _inc_mem_word_preserve_cf(cpu, seg: int, off: int) -> None:
    old = cpu.mem.rw(seg, off)
    old_cf = cpu.get_flag(CF)
    result = old + 1
    cpu.mem.ww(seg, off, result)
    cpu.set_add_flags(old, 1, result, 16)
    cpu.set_flag(CF, old_cf)


def _and_mem_word(cpu, seg: int, off: int, value: int) -> None:
    result = cpu.mem.rw(seg, off) & (value & 0xFFFF)
    cpu.mem.ww(seg, off, result)
    cpu.set_logic_flags(result, 16)


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


def build_pixel_pair_lookup_table_0fe4(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:0FE4 Tandy startup pixel-pair table builder.

    The original routine is a one-shot startup helper called immediately after
    the unpacked program resizes its DOS memory block.  It expands every byte
    value 00h..FFh into four bytes at ``DS:1514..1913``.  Each source bit-pair
    becomes one mask-ish byte: low bit -> ``0Fh`` and high bit -> ``F0h``.  The
    code uses ``RCR DL,1`` rather than ``SHR`` so the exact final ``DL`` and
    flags are part of the verified boundary state.

    This is rendering startup data, not file/overlay asset decoding: it is the
    small table later used by Tandy/PCjr pixel expansion paths.
    """
    if runtime.self_disable_if_patched(cpu, 0x0FE4, runtime.signature_0fe4, "overkill_tandy_pixel_pair_table_0fe4"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    # MOV ES,CS:[9596]; MOV DI,1517h; XOR DH,DH.
    s.es = mem.rw(cs, TANDY_DISPLAY_SEGMENT_OFF)
    s.di = 0x1517
    s.dx &= 0x00FF
    cpu.set_logic_flags(0, 8)

    while True:
        dh = (s.dx >> 8) & 0xFF
        dl = dh
        s.dx = (s.dx & 0xFF00) | dl

        for _ in range(4):
            # XOR AL,AL.
            s.ax &= 0xFF00
            cpu.set_logic_flags(0, 8)

            # RCR DL,1; JNB skip; MOV AL,0Fh.
            dl = cpu.shift(3, dl, 1, 8)
            if cpu.get_flag(CF):
                s.ax = (s.ax & 0xFF00) | 0x0F

            # RCR DL,1; JNB skip; ADD AL,F0h.
            dl = cpu.shift(3, dl, 1, 8)
            if cpu.get_flag(CF):
                al = s.ax & 0xFF
                result = al + 0xF0
                s.ax = (s.ax & 0xFF00) | (result & 0xFF)
                cpu.set_add_flags(al, 0xF0, result, 8)

            # MOV [DI],AL; DEC DI.
            mem.wb(s.ds, s.di, s.ax & 0xFF)
            old_cf = cpu.get_flag(CF)
            old_di = s.di & 0xFFFF
            s.di = (old_di - 1) & 0xFFFF
            cpu.set_sub_flags(old_di, 1, old_di - 1, 16)
            cpu.set_flag(CF, old_cf)
            s.dx = (s.dx & 0xFF00) | dl

        # ADD DI,8; INC DH; JNZ 0FEE.
        old_di = s.di & 0xFFFF
        result_di = old_di + 8
        s.di = result_di & 0xFFFF
        cpu.set_add_flags(old_di, 8, result_di, 16)

        old_cf = cpu.get_flag(CF)
        old_dh = (s.dx >> 8) & 0xFF
        new_dh = (old_dh + 1) & 0xFF
        s.dx = (new_dh << 8) | (s.dx & 0x00FF)
        cpu.set_add_flags(old_dh, 1, old_dh + 1, 8)
        cpu.set_flag(CF, old_cf)  # INC preserves carry.
        if new_dh == 0:
            break

    s.ip = cpu.pop()




def patched_strided_row_copy_30ba(cpu) -> None:
    """OVERKILL runtime-patched 1010:30BA strided row copier.

    Live startup/menu code patches 30BA from the earlier clear-loop body into a
    compact row copier:

        mov cx,ax; lodsw; shl ax,1; shl ax,1; mov bp,ax
        push cx; mov cx,bp; rep movsb; sub di,bp; add di,00A0h; pop cx; loop

    This is mode-2/Tandy rendering glue, not asset decoding.
    """
    s = cpu.s
    mem = cpu.mem
    s.cx = s.ax & 0xFFFF
    delta = -2 if cpu.get_flag(DF) else 2
    s.ax = mem.rw(s.ds & 0xFFFF, s.si & 0xFFFF)
    s.si = (s.si + delta) & 0xFFFF
    s.ax = cpu.shift(4, s.ax, 1, 16)
    s.ax = cpu.shift(4, s.ax, 1, 16)
    s.bp = s.ax & 0xFFFF

    outer = s.cx if s.cx != 0 else 0x10000
    width = s.bp & 0xFFFF
    for _ in range(outer):
        saved_cx = s.cx & 0xFFFF
        cpu.push(saved_cx)
        s.cx = width
        _rep_movsb(cpu, width)
        _sub_reg16(cpu, 7, width)
        _add_reg16(cpu, 7, 0x00A0)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF

    s.ip = cpu.pop()

def _clear_tandy_interlaced_rows_from_current_state(cpu) -> None:
    s = cpu.s
    while True:
        s.cx = 0x0034
        s.ax = 0
        cpu.set_logic_flags(0, 16)
        for _ in range(0x34):
            _stosw(cpu)
        _sub_reg16(cpu, 7, 0x0068)
        _add_reg16(cpu, 7, 0x2000)
        _test_word(cpu, s.di, 0x8000)
        if not cpu.get_flag(ZF):
            _add_reg16(cpu, 7, 0x80A0)
        _dec_reg16_preserve_cf(cpu, 5)
        if s.bp == 0:
            break
    s.ip = cpu.pop()


def clear_tandy_interlaced_buffer_30b0(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:30B0 Tandy interlaced-buffer clear loop.

    The original clears 200 interlaced rows in the Tandy video/work segment
    selected by ``CS:[95A4]``.  Each row stores 0x34 words, rewinds DI by the
    row width, advances through the 2000h/80A0h interlaced address pattern, and
    loops on BP.  The final live FLAGS are from the last ``DEC BP`` with CF
    preserved from the preceding TEST/ADD path.
    """
    if runtime.self_disable_if_patched(cpu, 0x30B0, runtime.signature_30b0, "overkill_tandy_interlaced_clear_30b0"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    s.es = mem.rw(cs, TANDY_VIDEO_SEGMENT_OFF)
    s.di = 0
    s.bp = 0x00C8

    _clear_tandy_interlaced_rows_from_current_state(cpu)


def build_video_offset_tables_0fa3(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:0FA3 Tandy/CGA video-offset lookup table builder.

    The startup code materializes four 256-word tables in the code segment at
    8D92h, 8F92h, 9192h, and 9392h.  Each table is a simple cumulative sequence
    using mode-dependent strides stored in the data segment.  The original ends
    with ``JMP 526A`` rather than returning, so the lifted hook has a fixed-IP
    continuation.
    """
    if runtime.self_disable_if_patched(cpu, 0x0FA3, runtime.signature_0fa3, "overkill_tandy_video_offset_tables_0fa3"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    # PUSH CS; POP ES.  The net SP is unchanged, but the transient push leaves
    # a scratch word below SP that full-memory verifier snapshots can observe.
    mem.ww(s.ss, (s.sp - 2) & 0xFFFF, cs)
    s.es = cs

    for base, stride_off in (
        (0x8D92, 0x1070),
        (0x8F92, 0x1024),
        (0x9192, 0x1026),
        (0x9392, 0x1028),
    ):
        s.di = base
        s.cx = 0x0100
        s.ax = 0
        cpu.set_logic_flags(0, 16)  # XOR AX,AX.
        stride = mem.rw(ds, stride_off)
        while True:
            # STOSW; ADD AX,DS:[stride_off]; LOOP.
            _stosw(cpu)
            old_ax = s.ax & 0xFFFF
            result = old_ax + stride
            s.ax = result & 0xFFFF
            cpu.set_add_flags(old_ax, stride, result, 16)
            s.cx = (s.cx - 1) & 0xFFFF
            if s.cx == 0:
                break

    s.ip = 0x526A


def build_startup_coordinate_tables_0f0b(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:0F0B startup coordinate/video lookup table builder.

    This parent setup block materializes the coordinate helper tables in the
    active renderer data segment, then falls through into the already-lifted
    ``0FA3`` code-segment video-offset table builder.  It is renderer setup
    glue, not asset decoding: the generated tables are consumed later by the
    coordinate and dirty-cell presenter paths.

    Original shape:

    * clear ``DS:99C8..99E7`` to ``FFFF``;
    * build a signed X/window table at ``99E8`` using stride ``CS:[959E]``;
    * add a second ``FFFF`` guard band;
    * build two linear tables at ``9BC8`` and ``9D58`` using ``CS:[959E]`` and
      ``CS:[95A0]``;
    * build a mode-dispatched physical row-address table at ``9EE8``;
    * fall through to ``0FA3``.

    The mode-dispatch logic is shared by CGA/EGA/Tandy startup.  The observed
    Tandy cold-start path currently uses mode index 0, but the helper implements
    all three dispatch-table entries from the original bytes so synthetic and
    alternate-video verification do not need a second copy of the routine.
    """
    if runtime.self_disable_if_patched(cpu, 0x0F0B, runtime.signature_0f0b, "overkill_startup_coordinate_tables_0f0b"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    # MOV DS,CS:[9596]; MOV ES,CS:[9596].
    table_seg = mem.rw(cs, TANDY_DISPLAY_SEGMENT_OFF)
    s.ds = table_seg
    s.es = table_seg

    # DI=99C8; CX=10; AX=FFFF; REP STOSW.
    s.di = 0x99C8
    s.cx = 0x0010
    s.ax = 0xFFFF
    for _ in range(0x0010):
        _stosw(cpu)
    s.cx = 0

    # AX = -(CS:[959E] << 4); CX=D0; table += CS:[959E].
    s.ax = mem.rw(cs, 0x959E)
    for _ in range(4):
        s.ax = cpu.shift(4, s.ax, 1, 16)  # SHL AX,1
    old_ax = s.ax & 0xFFFF
    s.ax = (-old_ax) & 0xFFFF
    cpu.set_sub_flags(0, old_ax, -old_ax, 16)  # NEG AX.
    s.cx = 0x00D0
    stride = mem.rw(cs, 0x959E)
    for _ in range(0x00D0):
        _stosw(cpu)
        old_ax = s.ax & 0xFFFF
        result = old_ax + stride
        s.ax = result & 0xFFFF
        cpu.set_add_flags(old_ax, stride, result, 16)
        s.cx = (s.cx - 1) & 0xFFFF

    # Guard band: AX=FFFF; CX=20; REP STOSW.
    s.ax = 0xFFFF
    s.cx = 0x0020
    for _ in range(0x0020):
        _stosw(cpu)
    s.cx = 0

    def build_linear_table(base: int, stride_off: int) -> None:
        s.di = base & 0xFFFF
        s.ax = 0
        cpu.set_logic_flags(0, 16)  # XOR AX,AX.
        s.cx = 0x00C8
        stride_value = mem.rw(cs, stride_off)
        for _ in range(0x00C8):
            _stosw(cpu)
            old = s.ax & 0xFFFF
            result = old + stride_value
            s.ax = result & 0xFFFF
            cpu.set_add_flags(old, stride_value, result, 16)
            s.cx = (s.cx - 1) & 0xFFFF

    build_linear_table(0x9BC8, 0x959E)
    build_linear_table(0x9D58, 0x95A0)

    # DI=9EE8; CX=C8; AX=0; row-address table with mode-dispatched advance.
    s.di = 0x9EE8
    s.cx = 0x00C8
    s.ax = 0
    cpu.set_logic_flags(0, 16)
    mode = mem.rw(cs, 0x95BC) & 0xFFFF
    while s.cx != 0:
        _stosw(cpu)
        # XCHG AX,DI; the original then dispatches on CS:[95BC].
        s.ax, s.di = s.di & 0xFFFF, s.ax & 0xFFFF
        if mode == 0:
            _add_reg16(cpu, 7, 0x2000)
            _test_word(cpu, s.di, 0x4000)
            if not cpu.get_flag(ZF):
                _add_reg16(cpu, 7, 0xC050)
        elif mode == 1:
            _add_reg16(cpu, 7, 0x0028)
        elif mode == 2:
            _add_reg16(cpu, 7, 0x2000)
            _test_word(cpu, s.di, 0x8000)
            if not cpu.get_flag(ZF):
                _add_reg16(cpu, 7, 0x80A0)
        else:
            raise RuntimeError(f"1010:0F0B startup coordinate hook reached unknown video mode index {mode:04X}")
        # XCHG AX,DI; LOOP.
        s.ax, s.di = s.di & 0xFFFF, s.ax & 0xFFFF
        s.cx = (s.cx - 1) & 0xFFFF

    # The original dispatch sequence leaves BX holding CS:[95BC] << 1 from
    # the final iteration before falling through into 0FA3.  Preserve that
    # register side effect even though the Python dispatch above keeps mode as
    # a local for clarity.
    s.bx = ((mode & 0xFFFF) << 1) & 0xFFFF

    # The original falls through into 0FA3 (not CALL).  Reuse the existing
    # lifted helper so we do not keep a second implementation of those tables.
    build_video_offset_tables_0fa3(cpu, runtime)


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


def copy_rect_to_tandy_video_306f(cpu, runtime: TandyRenderRuntime) -> None:
    """Copy a raw rectangle to Tandy B800h interlaced video memory.

    Original routine ``1010:306F`` reads ``height`` and ``width`` words from
    ``DS:SI``.  Each row copies ``width * 4`` bytes, then rewinds to the row
    start and advances through Tandy's ``+2000h`` interlace layout with the
    original ``+80A0h`` wrap correction.
    """
    if runtime.self_disable_if_patched(cpu, 0x306F, runtime.signature_306f, "overkill_tandy_rect_copy_306f"):
        return

    mem = cpu.mem
    s = cpu.s

    lodsw_delta = -2 if cpu.get_flag(DF) else 2

    s.ax = mem.rw(s.ds, s.si)
    s.si = (s.si + lodsw_delta) & 0xFFFF
    height = s.ax & 0xFFFF
    s.cx = height

    s.ax = mem.rw(s.ds, s.si)
    s.si = (s.si + lodsw_delta) & 0xFFFF
    s.es = mem.rw(s.cs, TANDY_VIDEO_SEGMENT_OFF)
    s.ax = (s.ax << 1) & 0xFFFF
    s.ax = (s.ax << 1) & 0xFFFF
    s.bp = s.ax

    rows_left = height
    while rows_left:
        mem.ww(s.ss, (s.sp - 2) & 0xFFFF, rows_left)
        s.cx = s.bp
        _rep_movsb(cpu, s.cx)

        old_di = s.di & 0xFFFF
        result = old_di - (s.bp & 0xFFFF)
        s.di = result & 0xFFFF
        cpu.set_sub_flags(old_di, s.bp & 0xFFFF, result, 16)

        old_di = s.di & 0xFFFF
        result = old_di + 0x2000
        s.di = result & 0xFFFF
        cpu.set_add_flags(old_di, 0x2000, result, 16)

        cpu.set_logic_flags(s.di & 0x8000, 16)
        if s.di & 0x8000:
            old_di = s.di & 0xFFFF
            result = old_di + 0x80A0
            s.di = result & 0xFFFF
            cpu.set_add_flags(old_di, 0x80A0, result, 16)

        rows_left = (rows_left - 1) & 0xFFFF

    s.cx = 0
    s.ip = cpu.pop()


def changed_dword_present_8rows_cdaa(cpu) -> None:
    """Copy one changed 4-byte Tandy cell to visible B800h for eight rows."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    cx = s.cx & 0xFFFF
    if cx == 0:
        cx = 0x10000

    ax = s.ax & 0xFFFF
    while cx:
        ax = mem.rw(ds, si)
        mem.ww(es, di, ax)
        ax = mem.rw(ds, (si + 2) & 0xFFFF)
        mem.ww(es, (di + 2) & 0xFFFF, ax)

        si = (si + 0x00A0) & 0xFFFF

        old_di = di
        result = old_di + 0x2000
        di = result & 0xFFFF
        cpu.set_add_flags(old_di, 0x2000, result, 16)

        cpu.set_logic_flags(di & 0x8000, 16)
        if di & 0x8000:
            old_di = di
            result = old_di + 0x80A0
            di = result & 0xFFFF
            cpu.set_add_flags(old_di, 0x80A0, result, 16)

        cx -= 1

    s.ax = ax
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = 0xCE02


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



def _loading_scroll_a7e3_reset_cursor(cpu) -> None:
    """Lift 1010:A7E3, reset the loading work-buffer cursor."""
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    cpu.s.ax = cpu.mem.rw(cs, 0x95BE)
    cpu.mem.ww(ds, 0x234C, cpu.s.ax)
    cpu.s.ip = cpu.pop()


def _loading_scroll_a81b_dispatch(cpu, runtime: TandyRenderRuntime) -> None:
    """Lift the A81B path reached from A781 with DS:[2352] == 1."""
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    cpu.s.bx = cpu.mem.rw(ds, 0x2350)
    _cmp_word(cpu, cpu.mem.rw(ds, 0x2352), 1)
    if cpu.mem.rw(ds, 0x2352) != 1:
        raise RuntimeError("1010:A81B loading-scroll hook reached unverified DS:[2352] != 1 path")
    _sub_reg16(cpu, 3, 0x00A9)  # BX -= 00A9h

    # 5A7E dispatch prologue: MOV DX,BX; MOV BX,CS:[95BC]; SHL BX,1;
    # JMP CS:[5A8C+BX].  36A2 then immediately reloads BX from DX, but DX
    # and the pushed BX scratch are visible at the wider 60C5 boundary.
    cpu.s.dx = cpu.s.bx & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    cpu.s.bx = mode & 0xFFFF
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
    if mode != 2:
        raise RuntimeError(f"1010:A81B loading-scroll hook only covers Tandy mode, got mode {mode}")
    loading_tile_column_copy_36a2(cpu, runtime)


def _loading_scroll_a7eb_build_and_shift(cpu, runtime: TandyRenderRuntime) -> None:
    """Lift 1010:A7EB, build one Tandy strip then shift the work buffer."""
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF

    cpu.s.di = cpu.mem.rw(ds, 0x234C)
    _sub_reg16(cpu, 7, cpu.mem.rw(cs, 0x95BE))

    cpu.push(0xA7F7)
    _loading_scroll_a81b_dispatch(cpu, runtime)
    if cpu.s.ip != 0xA7F7:
        raise RuntimeError(f"1010:A81B returned to unexpected IP {cpu.s.ip:04X}")

    ds = cpu.s.ds & 0xFFFF
    cpu.s.si = cpu.mem.rw(ds, 0x234C)
    _sub_reg16(cpu, 6, cpu.mem.rw(cs, 0x95BE))
    cpu.s.ds = cpu.mem.rw(cs, 0x9598)
    cpu.s.di = cpu.s.si & 0xFFFF
    _add_reg16(cpu, 7, cpu.mem.rw(cs, 0x95C2))
    cpu.s.cx = cpu.mem.rw(cs, 0x95BE)
    cpu.s.cx = cpu.shift(5, cpu.s.cx, 1, 16)  # SHR CX,1
    _rep_movsw(cpu, cpu.s.cx)
    cpu.s.ds = cpu.mem.rw(cs, TANDY_DISPLAY_SEGMENT_OFF)
    cpu.s.ip = cpu.pop()


def _loading_scroll_a7d0_advance_source(cpu, runtime: TandyRenderRuntime) -> None:
    """Lift 1010:A7D0, the source-strip advance helper called by A781."""
    cpu.push(0xA7D3)
    _loading_scroll_a7eb_build_and_shift(cpu, runtime)
    if cpu.s.ip != 0xA7D3:
        raise RuntimeError(f"1010:A7EB returned to unexpected IP {cpu.s.ip:04X}")

    ds = cpu.s.ds & 0xFFFF
    _sub_mem_word(cpu, ds, 0x2350, 0x000D)
    _inc_mem_word_preserve_cf(cpu, ds, 0xA978)
    cpu.mem.ww(ds, 0x2354, 1)
    cpu.s.ip = cpu.pop()


def _loading_scroll_step_a781(cpu, runtime: TandyRenderRuntime) -> None:
    """Lift observed 1010:A781 loading-scroll step used by the 60C5 loop."""
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF

    cpu.push(cpu.s.bp)
    cpu.mem.ww(ds, 0x2352, 1)
    _cmp_word(cpu, cpu.mem.rw(ds, 0x2350), 0)
    if cpu.mem.rw(ds, 0x2350) == 0:
        raise RuntimeError("1010:A781 loading-scroll hook reached unverified zero-cursor path")

    _add_mem_word(cpu, ds, 0xA278, 0xFFFF)
    _cmp_word(cpu, cpu.mem.rw(ds, 0x234E), 0)
    if cpu.mem.rw(ds, 0x234E) == 0:
        cpu.push(0xA79E)
        _loading_scroll_a7d0_advance_source(cpu, runtime)
        if cpu.s.ip != 0xA79E:
            raise RuntimeError(f"1010:A7D0 returned to unexpected IP {cpu.s.ip:04X}")

    _inc_mem_word_preserve_cf(cpu, ds, 0x234E)
    _and_mem_word(cpu, ds, 0x234E, 0x000F)
    if cpu.mem.rw(ds, 0x234E) == 0:
        _cmp_word(cpu, cpu.mem.rw(ds, 0x2354), 1)
        if cpu.mem.rw(ds, 0x2354) != 1:
            _sub_mem_word(cpu, ds, 0x2350, 0x000D)
            _inc_mem_word_preserve_cf(cpu, ds, 0xA978)

    cpu.s.ax = cpu.mem.rw(cs, 0x95C0)
    _cmp_word(cpu, cpu.mem.rw(ds, 0x234C), cpu.s.ax)
    if cpu.mem.rw(ds, 0x234C) == cpu.s.ax:
        cpu.push(0xA7C6)
        _loading_scroll_a7e3_reset_cursor(cpu)
        if cpu.s.ip != 0xA7C6:
            raise RuntimeError(f"1010:A7E3 returned to unexpected IP {cpu.s.ip:04X}")

    cpu.s.ax = cpu.mem.rw(cs, 0x959E)
    _add_mem_word(cpu, ds, 0x234C, cpu.s.ax)
    cpu.s.bp = cpu.pop()
    cpu.s.ip = cpu.pop()




def loading_scroll_until_4e0d(cpu, runtime: TandyRenderRuntime) -> None:
    """Lift 1010:4E0D, a parent loop around the A781 loading-scroll step.

    The routine preserves ``DI``/``SI`` around each A781 call, then keeps
    stepping until the work-buffer cursor ``DS:[2350]`` is no longer above the
    caller's ``DI`` and the phase counter ``DS:[234E]`` has wrapped to zero.
    It finally stores the caller's ``SI`` into ``DS:A978`` and returns.
    """
    ds = cpu.s.ds & 0xFFFF
    while True:
        cpu.push(cpu.s.di)
        cpu.push(cpu.s.si)
        cpu.push(0x4E12)
        _loading_scroll_step_a781(cpu, runtime)
        if cpu.s.ip != 0x4E12:
            raise RuntimeError(f"1010:A781 returned to unexpected IP {cpu.s.ip:04X} inside 4E0D")
        cpu.s.si = cpu.pop()
        cpu.s.di = cpu.pop()

        cursor = cpu.mem.rw(ds, 0x2350)
        _cmp_word(cpu, cursor, cpu.s.di & 0xFFFF)
        if (not cpu.get_flag(CF)) and (not cpu.get_flag(ZF)):
            continue

        phase = cpu.mem.rw(ds, 0x234E)
        _cmp_word(cpu, phase, 0)
        if phase != 0:
            continue

        cpu.mem.ww(ds, 0xA978, cpu.s.si & 0xFFFF)
        cpu.s.ip = cpu.pop()
        return

def loading_scroll_sequence_60c5(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:60C5 Tandy loading scroll/materialization loop.

    The snapshot spends thousands of interpreted instructions in the nested
    ``60C5 -> A781 -> A7EB -> A81B -> 36A2`` loading path.  ``36A2`` owns the
    Tandy tile materialization, while this wrapper preserves the original outer
    loop/call structure and cursor bookkeeping.
    """
    if runtime.self_disable_if_patched(cpu, 0x60C5, runtime.signature_60c5, "overkill_tandy_loading_scroll_sequence_60c5"):
        return
    if cpu.mem.rw(cpu.s.cs & 0xFFFF, 0x95BC) != 2:
        raise RuntimeError("1010:60C5 loading-scroll hook only covers verified Tandy mode")

    ds = cpu.s.ds & 0xFFFF
    cpu.mem.ww(ds, 0x2350, 0x0EA0)
    while True:
        cpu.s.cx = 0x0010
        while True:
            cpu.push(cpu.s.cx)
            cpu.push(0x60D2)
            _loading_scroll_step_a781(cpu, runtime)
            if cpu.s.ip != 0x60D2:
                raise RuntimeError(f"1010:A781 returned to unexpected IP {cpu.s.ip:04X}")
            cpu.s.cx = cpu.pop()
            cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unaffected.
            if cpu.s.cx != 0:
                continue
            break

        _cmp_word(cpu, cpu.mem.rw(ds, 0x2350), 0x009C)
        if cpu.mem.rw(ds, 0x2350) != 0x009C:
            continue
        break

    _sub_mem_word(cpu, ds, 0xA978, 0x0003)
    cpu.s.ip = cpu.pop()


def loading_tile_column_copy_36a2(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:36A2 Tandy loading/menu tile-column materializer.

    This is reached from the shared ``5A7E`` video-mode dispatch while the game
    loads transition/menu graphics.  It expands a 13-column strip of 16x8-byte
    Tandy tile cells from the selected source segment into the decoded work
    buffer at ``CS:[9598]``.  The body is mostly a long unrolled MOVSW sequence;
    keeping it as one hook avoids thousands of interpreter steps during loading
    without changing the surrounding loading state machine.
    """
    if runtime.self_disable_if_patched(cpu, 0x36A2, runtime.signature_36a2, "overkill_tandy_loading_tile_column_copy_36a2"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    display_ds = s.ds & 0xFFFF

    # 36A2..36B7: select the source segment based on the current loading cursor.
    s.bx = s.dx & 0xFFFF
    s.cx = 0x000D
    s.ax = mem.rw(cs, 0x959A)
    cursor = mem.rw(display_ds, 0x2350)
    cpu.set_sub_flags(cursor, 0x0E5F, cursor - 0x0E5F, 16)
    if cursor >= 0x0E5F:
        s.ax = mem.rw(cs, 0x959C)
    s.ds = s.ax & 0xFFFF

    while True:
        # The original loop pushes CX then BX every column and pops them back
        # after the copy.  Use real push/pop so freed stack scratch remains
        # byte-identical for hook verification.
        cpu.push(s.cx)
        cpu.push(s.bx)

        s.es = mem.rw(cs, 0x9592)
        tile_index = mem.rb(s.es, s.bx)

        # DEC BL preserves CF; XOR BH,BH then clears CF/OF and sets ZF/PF.
        old_bl = tile_index & 0xFF
        old_cf = cpu.get_flag(CF)
        new_bl = (old_bl - 1) & 0xFF
        cpu.set_sub_flags(old_bl, 1, old_bl - 1, 8)
        cpu.set_flag(CF, old_cf)
        s.bx = (s.bx & 0xFF00) | new_bl
        s.bx &= 0x00FF
        cpu.set_logic_flags(0, 8)

        s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1
        old_bx = s.bx & 0xFFFF
        s.bx = (old_bx + 0x8D92) & 0xFFFF
        cpu.set_add_flags(old_bx, 0x8D92, old_bx + 0x8D92, 16)
        s.si = mem.rw(cs, s.bx)
        s.es = mem.rw(cs, 0x9598)

        # Sixteen rows, four MOVSW per row, then ADD DI,60h.  MOVSW does not
        # affect flags; the row add does.  The original code is fully unrolled.
        for _row in range(16):
            for _ in range(4):
                mem.ww(s.es, s.di, mem.rw(s.ds, s.si))
                delta = -2 if s.flags & DF else 2
                s.si = (s.si + delta) & 0xFFFF
                s.di = (s.di + delta) & 0xFFFF
            old_di = s.di & 0xFFFF
            s.di = (old_di + 0x0060) & 0xFFFF
            cpu.set_add_flags(old_di, 0x0060, old_di + 0x0060, 16)

        old_di = s.di & 0xFFFF
        s.di = (old_di - 0x0678) & 0xFFFF
        cpu.set_sub_flags(old_di, 0x0678, old_di - 0x0678, 16)

        s.bx = cpu.pop()
        old_bx = s.bx & 0xFFFF
        s.bx = (old_bx + 1) & 0xFFFF
        cpu.set_add_flags(old_bx, 1, old_bx + 1, 16)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF  # LOOP does not modify FLAGS.
        if s.cx == 0:
            break

    s.ds = mem.rw(cs, TANDY_DISPLAY_SEGMENT_OFF)
    s.ip = cpu.pop()


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


def _inc_ax_preserve_cf(cpu) -> None:
    old = cpu.s.ax & 0xFFFF
    old_cf = cpu.get_flag(CF)
    cpu.s.ax = (old + 1) & 0xFFFF
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)


def _tandy_block_header_44d7(cpu) -> bool:
    """Lift the 1010:44D7 header reader used by the Tandy list driver."""
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    s.ax = mem.rw(ds, s.si)
    value = s.ax | mem.rw(ds, (s.si + 2) & 0xFFFF)
    cpu.set_logic_flags(value, 16)
    if value == 0:
        return False

    s.bx = mem.rw(cs, 0x0BE0)
    _add_mem_word(cpu, cs, 0x0BE0, 2)

    lodsw_delta = -2 if cpu.get_flag(DF) else 2
    mirror_headers = mem.rw(cs, 0x0BD8) != 0

    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + lodsw_delta) & 0xFFFF
    if mirror_headers:
        mem.ww(cs, s.bx, s.di)
        _stosw(cpu)
    mem.ww(cs, 0x5B9E, s.ax)

    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + lodsw_delta) & 0xFFFF
    if mirror_headers:
        _stosw(cpu)
    mem.ww(cs, 0x5B9C, s.ax)
    _inc_ax_preserve_cf(cpu)
    return True


def expand_tandy_list_33af(cpu, runtime: TandyRenderRuntime) -> None:
    """OVERKILL 1010:33AF Tandy startup list driver.

    This composes the small original header reader at ``44D7`` with the already
    verified ``33B2`` block expander, removing hundreds of interpreted
    call/return/header iterations during Tandy startup materialization.
    """
    if runtime.self_disable_if_patched(cpu, 0x33AF, runtime.signature_33af, "overkill_expand_tandy_list_33af"):
        return

    s = cpu.s
    ss = s.ss & 0xFFFF
    while True:
        # CALL 44D7 writes return IP 33B2 below SP, then RET restores SP.  Keep
        # the scratch word because full-memory oracles can observe it.
        cpu.mem.ww(ss, (s.sp - 2) & 0xFFFF, 0x33B2)
        if not _tandy_block_header_44d7(cpu):
            s.ip = 0x44AA
            return
        expand_tandy_block_33b2(cpu, runtime)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (s.cs & 0xFFFF, 0x33AF):
            return


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
        cpu.mem.ww(ss, (entry_sp - 8) & 0xFFFF, 0x341B)
        cpu.mem.ww(ss, (entry_sp - 6) & 0xFFFF, 0x33C6)
        cpu.mem.ww(ss, (entry_sp - 4) & 0xFFFF, 0x0001)
        cpu.mem.ww(ss, (entry_sp - 2) & 0xFFFF, 0x0001)

    s.cx = 0
    s.ip = 0x33AF
