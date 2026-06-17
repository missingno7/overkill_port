"""Lifted OVERKILL frame orchestration / glue helpers.

This module is for finite glue that is neither a renderer primitive, nor an
object behaviour, nor an asset codec.  These routines preserve the original
frame-ordering contract by composing lower proof-boundaries in the same order as
ASM.  Timing waits stay in ``sounds``/``input_menu``; concrete object behaviour
stays in ``object_runtime``; this layer owns only the per-frame bookkeeping and
script/list orchestration that binds them together.
"""
from __future__ import annotations

from collections.abc import Callable

from overkill.asm import (
    _add_mem_word,
    _add_reg16,
    _and_mem_word,
    _cmp_byte,
    _cmp_word,
    _dec_mem_word_preserve_cf,
    _inc_mem_word_preserve_cf,
    _rep_stosw_preserve_flags,
    _sub_mem_word,
    _sub_reg16,
)
from dos_re.cpu import ZF


RunOriginalNearCall = Callable[[object, int, int], None]
RunOriginalFarCall = Callable[[object, int, int, int], None]



SIG_MAIN_FRAME_LOOP_D007 = bytes.fromhex(
    "e8 68 36 e8 12 81 e8 36 d8 e8 c9 8b e8 f6 d8 e8 "
    "34 00 e8 24 d9 e8 42 8f e8 1a 37 e8 3b 81 e8 51 "
    "36 83 3e 06 be 13 74 11 e8 30 31 f6 06 be 98 10 "
    "75 07 80 3e c3 98 00 74 c7"
)


def run_main_frame_loop_d007(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift one iteration of the 1010:D007 main gameplay frame loop.

    D007 is the top-level frame orchestrator, not an object or renderer leaf.
    The hook deliberately performs exactly one ASM frame-loop iteration and then
    either returns to D007 for the next frame or stops at D040, the original exit
    tail used when input/script state breaks out of the attract/gameplay loop.

    Child islands remain separate proof boundaries: this function composes their
    existing hooks in the same CALL order as the original code.  The verifier
    metadata for this routine requires the ASM oracle to execute at least one
    step before accepting D007 as a target, otherwise a same-IP loop would verify
    against a zero-step oracle.
    """
    if self_disable_if_patched(
        cpu,
        0xD007,
        SIG_MAIN_FRAME_LOOP_D007,
        "overkill_main_frame_loop_d007",
    ):
        return

    s = cpu.s
    mem = cpu.mem

    def call(ip: int, ret: int) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret & 0xFFFF)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (0x1010, ret & 0xFFFF):
            raise RuntimeError(
                f"D007 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret & 0xFFFF:04X}, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    call(0x0672, 0xD00A)
    call(0x511F, 0xD00D)
    call(0xA846, 0xD010)
    call(0x5BDC, 0xD013)
    call(0xA90C, 0xD016)
    call(0xD04D, 0xD019)
    call(0xA940, 0xD01C)
    call(0x5F61, 0xD01F)
    call(0x073C, 0xD022)
    call(0x5160, 0xD025)
    call(0x0679, 0xD028)

    ds = s.ds & 0xFFFF
    be06 = mem.rw(ds, 0xBE06)
    _cmp_word(cpu, be06, 0x0013)
    if be06 == 0x0013:
        s.ip = 0xD040
        return

    call(0x0162, 0xD032)

    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x10, 8)
    if input_flags & 0x10:
        s.ip = 0xD040
        return

    state98c3 = mem.rb(ds, 0x98C3)
    _cmp_byte(cpu, state98c3, 0x00)
    s.ip = 0xD007 if state98c3 == 0 else 0xD040

SIG_FRAME_STATUS_COUNTER_UPDATE_5F61 = bytes.fromhex(
    "83 3e 7e a4 00 75 21 83 3e 80 a4 00 74 1a ff 0e"
)
SIG_DEMO_OBJECT_LIST_MAINTENANCE_A212 = bytes.fromhex(
    "83 3e 72 a9 00 75 01 c3 83 3e 24 23 01 75 37 81"
)
SIG_FRAME_SERVICE_GATE_073C = bytes.fromhex(
    "80 3e 07 99 01 74 01 c3 e8 18 00 e8 a5 00 83 3e"
)
SIG_FRAME_UI_STATE_UPDATE_D04D = bytes.fromhex(
    "c7 06 78 a2 00 00 b0 1f b4 18 e8 a6 89 8b 1e 06 be"
)
SIG_FRAME_EFFECT_STATUS_TEXT_60A2 = bytes.fromhex("e8 20 17 e8 b9 fe e8 30 fe c3")
SIG_FRAME_LOOP_97B2 = bytes.fromhex(
    "e8 bd 6e e8 67 b9 e8 8b 10 83 3e 7a a9 00 75 03 e8 5a 00 "
    "e8 14 c4 e8 41 11 e8 60 03 83 3e 44 a3 01 75 03 e9 5c ff "
    "83 3e 42 a3 01 75 03 e9 20 01 83 3e 46 a3 01 75 03 e9 1c 01 "
    "e8 51 11 e8 4a 6f e8 ad c8 80 3e 8f 97 00 74 0a 80 3e 02 99 01 "
    "75 03 e9 2e ff 80 3e 08 99 01 75 03 e8 27 01 80 3e c5 98 01 "
    "74 4b e8 46 b9 e8 5c 6e eb 93"
)

SIG_FRAME_CONTROLLER_9B2E = bytes.fromhex(
    "c7 06 46 a3 00 00 c7 06 44 a3 00 00 e8 25 66 83 "
    "3e 7c a4 00 74 03 e8 af fe 83 3e 7c a4 04 75 07 "
    "c7 06 44 a3 01 00 c3 c7 06 78 a2 00 00 bd 7c 23 "
    "e8 b1 06 83 3e 5a a9 ff 74 97 83 3e 7a a9 00 74 "
    "90 f6 06 be 98 08 74 03 e8 58 0a f6 06 be 98 04 "
    "74 03 e8 67 0a f6 06 be 98 01 74 03 e8 7a 0a "
    "f6 06 be 98 02 74 03 e8 62 0a"
)

SIG_FRAME_ACTION_SPAWN_FANOUT_A067 = bytes.fromhex(
    "f6 06 be 98 10 74 f2 83 3e 80 a9 00 74 0f 80 "
    "3e 90 97 01 74 08 83 3e 2a 23 0f 74 01 c3 "
    "c7 06 80 a9 01 00 81 3e 50 23 b6 00 77 14 "
    "83 3e ac bd 00 75 0d 83 3e 58 a9 02 75 03 "
    "e9 25 01 e9 f9 00"
)

SIG_FRAME_ACTION_LINKED_ANCHOR_SPAWN_A515 = bytes.fromhex(
    "83 3e 60 a9 00 75 01 c3 83 3e 7e a9 01 75 01 c3 "
    "e8 1f d0 e8 46 00 55 8b eb e8 29 0c 8b c3 8b dd "
    "5d 3d ff ff 75 01 c3 89 47 30 c7 07 01 00 c7 47 "
    "1e 01 00 c7 47 14 00 00 c7 47 16 02 00 c7 47 "
    "18 0a 00 c7 47 1c 01 00 80 3e c0 98 00 74 05 "
    "c6 06 ff be 11 ff 06 7e a9 ff 0e 60 a9 c3"
)

SIG_FRAME_ACTION_DUAL_ANCHOR_SPAWN_A584 = bytes.fromhex(
    "83 3e 5e a9 00 75 01 c3 83 3e a4 a3 00 74 01 c3 "
    "ff 06 76 a9 80 3e c0 98 00 74 05 c6 06 ff be 12 "
    "e8 43 ff e8 c7 ff 83 67 04 fc c7 47 08 08 00 c7 "
    "47 18 05 00 ff 06 76 a9 e8 2b ff e8 af ff 83 67 "
    "04 fc c7 47 08 08 00 c7 47 18 06 00 c3"
)


SIG_FRAME_ACTION_SIDE_ANCHOR_SPAWN_A3CA = bytes.fromhex(
    "c7 06 ec a3 07 00 8b 36 66 a9 e8 43 00 c7 06 ec a3 "
    "01 00 8b 36 68 a9 e8 36 00 c7 06 ec a3 07 00 8b "
    "36 6a a9 e8 29 00 c7 06 ec a3 01 00 8b 36 6c a9 "
    "e8 1c 00 c3"
)

SIG_FRAME_ACTION_MIRRORED_ANCHOR_SPAWN_A3FF = bytes.fromhex(
    "c7 06 ec a3 ff ff 8b 36 62 a9 e8 0e 00 e8 69 ff "
    "8b 36 64 a9 e8 04 00 e8 5f ff c3"
)

SIG_FRAME_ACTION_LISTED_ANCHOR_SPAWN_A2A0 = bytes.fromhex(
    "83 3e a2 a3 00 74 01 c3 80 3e c0 98 00 74 05 c6 06 ff be 11 "
    "2e 8e 06 96 95 c7 06 ea a3 b4 a3 bf b4 a3 b8 ff ff b9 1a 00 "
    "f3 ab e8 09 00 c7 47 08 6a 00 83 6f 04 08 ff 06 72 a9 e8 0d 02 "
    "e8 b4 ff c7 47 18 09 00 e8 c6 fe 83 67 04 f8 83 47 04 08 c7 47 "
    "08 6c 00 c3"
)

SIG_FRAME_ACTION_PAIR_SPAWN_A2F6 = bytes.fromhex(
    "83 3e a0 a3 00 74 01 c3 80 3e c0 98 00 74 05 c6 06 ff be 17 "
    "ff 06 70 a9 e8 d9 01 c7 47 18 08 00 c7 47 08 35 00 e8 90 fe "
    "ff 06 70 a9 e8 c5 01 c7 47 18 08 00 c7 47 08 35 00 e8 7c fe "
    "83 47 02 08 c3"
)

SIG_FRAME_ACTION_PAIR_SPAWN_A337 = bytes.fromhex(
    "83 3e a0 a3 00 74 01 c3 80 3e c0 98 00 74 05 c6 06 ff be 16 "
    "ff 06 70 a9 e8 98 01 c7 47 18 07 00 c7 47 08 37 00 e8 4f fe "
    "ff 06 70 a9 e8 84 01 c7 47 18 07 00 c7 47 08 37 00 e8 3b fe "
    "83 47 02 08 c3"
)



def _set_beff_when_98c0_nonzero(cpu, value: int) -> None:
    ds = cpu.s.ds & 0xFFFF
    v98c0 = cpu.mem.rb(ds, 0x98C0)
    _cmp_byte(cpu, v98c0, 0x00)
    if v98c0 != 0:
        cpu.mem.wb(ds, 0xBEFF, value & 0xFF)


def _run_frame_action_coordinate_projection_body_a1ae(cpu) -> None:
    """Run the local A1AE BP-relative coordinate projection body."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    s.si = mem.rw(ss, (s.bp + 0x08) & 0xFFFF)
    s.si = cpu.shift(4, s.si, 1, 16)
    s.si = cpu.shift(4, s.si, 1, 16)
    _add_reg16(cpu, 6, 0xA3A8)
    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + 2) & 0xFFFF
    _add_reg16(cpu, 0, mem.rw(ss, (s.bp + 0x02) & 0xFFFF))
    mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.ax)
    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + 2) & 0xFFFF
    _add_reg16(cpu, 0, mem.rw(ss, (s.bp + 0x04) & 0xFFFF))
    mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.ax)


def _run_frame_action_coordinate_projection_a1ae(cpu) -> None:
    _run_frame_action_coordinate_projection_body_a1ae(cpu)
    cpu.s.ip = cpu.pop()


def _run_frame_action_list_append_a294(cpu) -> None:
    """Run local A294: append BX to the raw DS:A3EA word list."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    s.di = mem.rw(ds, 0xA3EA)
    mem.ww(ds, s.di & 0xFFFF, s.bx & 0xFFFF)
    _add_mem_word(cpu, ds, 0xA3EA, 0x0002)
    s.ip = cpu.pop()


def _run_frame_action_a2d6_spawn_body(
    cpu,
    run_original_near_call: RunOriginalNearCall,
    *,
    caller_name: str,
) -> None:
    """Run local A2D6 body used by A2A0's call/fallthrough pair."""
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def call_original(ip: int, ret_ip: int, *, max_steps: int = 80000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"{caller_name} expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    def internal_call(ret_ip: int, body) -> None:
        saved_sp = s.sp
        cpu.push(ret_ip & 0xFFFF)
        body()
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(f"{caller_name} internal call returned to unexpected IP {s.ip:04X}")
        if s.sp != saved_sp:
            raise RuntimeError(f"{caller_name} internal call stack mismatch")

    _inc_mem_word_preserve_cf(cpu, ds, 0xA972)
    call_original(0xA4EA, 0xA2DD, max_steps=80000)
    internal_call(0xA2E0, lambda: _run_frame_action_list_append_a294(cpu))
    mem.ww(ds, (s.bx + 0x18) & 0xFFFF, 0x0009)
    internal_call(0xA2E8, lambda: _run_frame_action_coordinate_projection_a1ae(cpu))
    _and_mem_word(cpu, ds, (s.bx + 0x04) & 0xFFFF, 0xFFF8)
    _add_mem_word(cpu, ds, (s.bx + 0x04) & 0xFFFF, 0x0008)
    mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x006C)
    s.ip = cpu.pop()


def _run_frame_action_pair_spawn_tail(
    cpu,
    run_original_near_call: RunOriginalNearCall,
    *,
    gate_addr: int,
    beff_value: int,
    slot_18: int,
    slot_08: int,
    first_ret: int,
    second_ret: int,
    first_a1ae_ret: int,
    second_a1ae_ret: int,
    caller_name: str,
) -> None:
    """Shared body for the A2F6/A337 two-slot raw action tails."""
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def call_original(ip: int, ret_ip: int, *, max_steps: int = 80000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"{caller_name} expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    def internal_call(ret_ip: int, body) -> None:
        saved_sp = s.sp
        cpu.push(ret_ip & 0xFFFF)
        body()
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(f"{caller_name} internal call returned to unexpected IP {s.ip:04X}")
        if s.sp != saved_sp:
            raise RuntimeError(f"{caller_name} internal call stack mismatch")

    v_gate = mem.rw(ds, gate_addr & 0xFFFF)
    _cmp_word(cpu, v_gate, 0x0000)
    if v_gate != 0x0000:
        ret()
        return

    _set_beff_when_98c0_nonzero(cpu, beff_value)

    def spawn_one(ret_ip: int, a1ae_ret: int) -> None:
        _inc_mem_word_preserve_cf(cpu, ds, 0xA970)
        call_original(0xA4EA, ret_ip, max_steps=80000)
        mem.ww(ds, (s.bx + 0x18) & 0xFFFF, slot_18 & 0xFFFF)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, slot_08 & 0xFFFF)
        internal_call(a1ae_ret, lambda: _run_frame_action_coordinate_projection_a1ae(cpu))

    spawn_one(first_ret, first_a1ae_ret)
    spawn_one(second_ret, second_a1ae_ret)
    _add_mem_word(cpu, ds, (s.bx + 0x02) & 0xFFFF, 0x0008)
    ret()



def run_frame_action_listed_anchor_spawn_a2a0(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A2A0, a raw listed two-slot action-spawn helper.

    The routine is reached from ``A067/A0E8`` when raw action index ``A958`` is
    5.  It is deliberately kept structural: it clears a 26-word list in the
    segment at ``CS:9596``, seeds ``DS:A3EA`` with ``A3B4``, then runs the local
    ``A2D6`` spawn body once through CALL and once through fall-through.  The
    first spawned slot is post-stamped with ``+8=006A`` and ``Y-=8`` before the
    second ``A2D6`` body runs.
    """
    if self_disable_if_patched(
        cpu,
        0xA2A0,
        SIG_FRAME_ACTION_LISTED_ANCHOR_SPAWN_A2A0,
        "overkill_frame_action_listed_anchor_spawn_a2a0",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def internal_call(ret_ip: int, body) -> None:
        saved_sp = s.sp
        cpu.push(ret_ip & 0xFFFF)
        body()
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(f"A2A0 internal call returned to unexpected IP {s.ip:04X}")
        if s.sp != saved_sp:
            raise RuntimeError("A2A0 internal call stack mismatch")

    v_a3a2 = mem.rw(ds, 0xA3A2)
    _cmp_word(cpu, v_a3a2, 0x0000)
    if v_a3a2 != 0x0000:
        ret()
        return

    _set_beff_when_98c0_nonzero(cpu, 0x11)
    s.es = mem.rw(cs, 0x9596)
    mem.ww(ds, 0xA3EA, 0xA3B4)
    s.di = 0xA3B4
    s.ax = 0xFFFF
    s.cx = 0x001A
    _rep_stosw_preserve_flags(cpu, s.cx)

    internal_call(
        0xA2CD,
        lambda: _run_frame_action_a2d6_spawn_body(
            cpu,
            run_original_near_call,
            caller_name="A2A0/A2D6",
        ),
    )
    mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x006A)
    _sub_mem_word(cpu, ds, (s.bx + 0x04) & 0xFFFF, 0x0008)

    # Original control flow falls through into A2D6 here, so this RET returns
    # to A2A0's caller rather than to an internal A2xx continuation.
    _run_frame_action_a2d6_spawn_body(
        cpu,
        run_original_near_call,
        caller_name="A2A0/A2D6-fallthrough",
    )


def run_frame_action_pair_spawn_a2f6(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A2F6, the A958==4 two-slot raw action tail."""
    if self_disable_if_patched(
        cpu,
        0xA2F6,
        SIG_FRAME_ACTION_PAIR_SPAWN_A2F6,
        "overkill_frame_action_pair_spawn_a2f6",
    ):
        return
    _run_frame_action_pair_spawn_tail(
        cpu,
        run_original_near_call,
        gate_addr=0xA3A0,
        beff_value=0x17,
        slot_18=0x0008,
        slot_08=0x0035,
        first_ret=0xA311,
        second_ret=0xA325,
        first_a1ae_ret=0xA31E,
        second_a1ae_ret=0xA332,
        caller_name="A2F6",
    )


def run_frame_action_pair_spawn_a337(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A337, the sibling A958==3 two-slot raw action tail."""
    if self_disable_if_patched(
        cpu,
        0xA337,
        SIG_FRAME_ACTION_PAIR_SPAWN_A337,
        "overkill_frame_action_pair_spawn_a337",
    ):
        return
    _run_frame_action_pair_spawn_tail(
        cpu,
        run_original_near_call,
        gate_addr=0xA3A0,
        beff_value=0x16,
        slot_18=0x0007,
        slot_08=0x0037,
        first_ret=0xA352,
        second_ret=0xA366,
        first_a1ae_ret=0xA35F,
        second_a1ae_ret=0xA373,
        caller_name="A337",
    )


def run_frame_action_linked_anchor_spawn_a515(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A515, a gated raw anchored-slot spawn helper.

    This is one child frontier behind ``A067``.  The routine is still described
    only structurally: it gates on raw counters ``A960``/``A97E``, allocates one
    destination slot, anchors it from the current ``BP`` slot through ``A571``,
    probes a linked/reference slot through ``B15A``, and stamps the destination
    slot fields.  Do not promote it to a named gameplay entity yet.
    """
    if self_disable_if_patched(
        cpu,
        0xA515,
        SIG_FRAME_ACTION_LINKED_ANCHOR_SPAWN_A515,
        "overkill_frame_action_linked_anchor_spawn_a515",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    def ret() -> None:
        s.ip = cpu.pop()

    def call(ip: int, ret_ip: int, *, max_steps: int = 120000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"A515 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    v_a960 = mem.rw(ds, 0xA960)
    _cmp_word(cpu, v_a960, 0x0000)
    if v_a960 == 0x0000:
        ret()
        return

    v_a97e = mem.rw(ds, 0xA97E)
    _cmp_word(cpu, v_a97e, 0x0001)
    if v_a97e == 0x0001:
        ret()
        return

    call(0x7547, 0xA528, max_steps=120000)
    call(0xA571, 0xA52B, max_steps=80000)

    cpu.push(s.bp & 0xFFFF)
    s.bp = s.bx & 0xFFFF
    call(0xB15A, 0xA531, max_steps=120000)
    s.ax = s.bx & 0xFFFF
    s.bx = s.bp & 0xFFFF
    s.bp = cpu.pop()

    _cmp_word(cpu, s.ax, 0xFFFF)
    if s.ax == 0xFFFF:
        ret()
        return

    bx = s.bx & 0xFFFF
    mem.ww(ds, (bx + 0x30) & 0xFFFF, s.ax)
    mem.ww(ds, bx, 0x0001)
    mem.ww(ds, (bx + 0x1E) & 0xFFFF, 0x0001)
    mem.ww(ds, (bx + 0x14) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x16) & 0xFFFF, 0x0002)
    mem.ww(ds, (bx + 0x18) & 0xFFFF, 0x000A)
    mem.ww(ds, (bx + 0x1C) & 0xFFFF, 0x0001)

    v98c0 = mem.rb(ds, 0x98C0)
    _cmp_byte(cpu, v98c0, 0x00)
    if v98c0 != 0:
        mem.wb(ds, 0xBEFF, 0x11)

    _inc_mem_word_preserve_cf(cpu, ds, 0xA97E)
    _dec_mem_word_preserve_cf(cpu, ds, 0xA960)
    ret()


def run_frame_action_dual_anchor_spawn_a584(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A584, a gated two-slot anchored spawn helper behind A067.

    The verified structure is a raw two-spawn helper gated by ``A95E`` and the
    copied ``A3A4`` counter.  It increments ``A976`` before each allocation,
    anchors both slots through ``A571``, aligns the destination Y field down to
    a 4-pixel boundary, and stamps two nearby slot-state fields.
    """
    if self_disable_if_patched(
        cpu,
        0xA584,
        SIG_FRAME_ACTION_DUAL_ANCHOR_SPAWN_A584,
        "overkill_frame_action_dual_anchor_spawn_a584",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def call(ip: int, ret_ip: int, *, max_steps: int = 120000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"A584 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    v_a95e = mem.rw(ds, 0xA95E)
    _cmp_word(cpu, v_a95e, 0x0000)
    if v_a95e == 0x0000:
        ret()
        return

    v_a3a4 = mem.rw(ds, 0xA3A4)
    _cmp_word(cpu, v_a3a4, 0x0000)
    if v_a3a4 != 0x0000:
        ret()
        return

    def finish_spawn(ret_seed: int, ret_anchor: int, stamp_18: int) -> None:
        call(0xA4EA, ret_seed, max_steps=80000)
        call(0xA571, ret_anchor, max_steps=80000)
        _and_mem_word(cpu, ds, (s.bx + 0x04) & 0xFFFF, 0xFFFC)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x0008)
        mem.ww(ds, (s.bx + 0x18) & 0xFFFF, stamp_18 & 0xFFFF)

    _inc_mem_word_preserve_cf(cpu, ds, 0xA976)
    v98c0 = mem.rb(ds, 0x98C0)
    _cmp_byte(cpu, v98c0, 0x00)
    if v98c0 != 0:
        mem.wb(ds, 0xBEFF, 0x12)
    finish_spawn(0xA5A7, 0xA5AA, 0x0005)

    _inc_mem_word_preserve_cf(cpu, ds, 0xA976)
    finish_spawn(0xA5BF, 0xA5C2, 0x0006)
    ret()


def _run_frame_action_table_body_a41a(
    cpu,
    run_original_near_call: RunOriginalNearCall,
    *,
    caller_name: str,
) -> None:
    """Run the local A41A raw action-slot dispatch body.

    ``A41A`` is not registered as a public hook because it is only a tiny local
    jump-table body used by the structural ``A3CA``/``A3FF`` spawn helpers.  It
    gates on ``SI != FFFFh`` and dispatches through the raw ``DS:A958`` table:
    ``A4D7, A490, A499, A464, A438``.  The targets are still structural slot
    side effects only; no semantic weapon/entity name is implied here.
    """
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def call_original(ip: int, ret_ip: int, *, max_steps: int = 80000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"{caller_name} expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    def internal_call(ret_ip: int, body) -> None:
        saved_sp = s.sp
        cpu.push(ret_ip & 0xFFFF)
        body()
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"{caller_name} internal call expected 1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )
        if s.sp != saved_sp:
            raise RuntimeError(f"{caller_name} internal call stack mismatch")

    def tail_original(ip: int, *, max_steps: int = 120000) -> None:
        target = (cs, mem.rw(s.ss & 0xFFFF, s.sp & 0xFFFF))
        saved_verifier = cpu.hook_verifier
        if not getattr(cpu, "hook_verifier_verify_nested_calls", True):
            cpu.hook_verifier = None
        s.ip = ip & 0xFFFF
        try:
            ctx = (
                cpu.coverage_telemetry.bounded_original((cs, ip & 0xFFFF), "bounded A41A table tail")
                if cpu.coverage_telemetry is not None
                else None
            )
            if ctx is not None:
                ctx.__enter__()
            try:
                for _ in range(max_steps):
                    if cpu.addr() == target:
                        return
                    cpu.step()
            finally:
                if ctx is not None:
                    ctx.__exit__(None, None, None)
        finally:
            cpu.hook_verifier = saved_verifier
        raise RuntimeError(
            f"{caller_name} interpreted A41A tail 1010:{ip & 0xFFFF:04X} did not reach "
            f"1010:{target[1] & 0xFFFF:04X}; now at "
            f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
        )

    def call_a4ea(ret_ip: int) -> None:
        call_original(0xA4EA, ret_ip, max_steps=80000)

    def run_a4d7_body() -> None:
        call_a4ea(0xA4DA)
        s.ax = mem.rw(ds, (s.si + 0x02) & 0xFFFF)
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.ax)
        s.ax = mem.rw(ds, (s.si + 0x04) & 0xFFFF)
        _add_reg16(cpu, 0, 0x0004)
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.ax)
        ret()

    def run_a438_pair(stamp_18: int, stamp_08: int) -> None:
        v_a3a0 = mem.rw(ds, 0xA3A0)
        _cmp_word(cpu, v_a3a0, 0x0000)
        if v_a3a0 != 0x0000:
            ret()
            return
        _add_mem_word(cpu, ds, 0xA970, 0x0002)
        internal_call(0xA448 if stamp_18 == 0x0008 else 0xA474, run_a4d7_body)
        mem.ww(ds, (s.bx + 0x18) & 0xFFFF, stamp_18 & 0xFFFF)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, stamp_08 & 0xFFFF)
        internal_call(0xA455 if stamp_18 == 0x0008 else 0xA481, run_a4d7_body)
        mem.ww(ds, (s.bx + 0x18) & 0xFFFF, stamp_18 & 0xFFFF)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, stamp_08 & 0xFFFF)
        _add_mem_word(cpu, ds, (s.bx + 0x02) & 0xFFFF, 0x0008)
        ret()

    def run_a490_body() -> None:
        internal_call(0xA493, run_a4d7_body)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x0033)
        ret()

    def run_a499_body() -> None:
        call_a4ea(0xA49C)
        s.ax = mem.rw(ds, (s.si + 0x02) & 0xFFFF)
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.ax)
        s.ax = mem.rw(ds, (s.si + 0x04) & 0xFFFF)
        _add_reg16(cpu, 0, 0x0004)
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.ax)
        s.ax = mem.rw(ds, 0xA3EC)
        mem.ww(ds, (s.bx + 0x06) & 0xFFFF, s.ax)
        _cmp_word(cpu, s.ax, 0xFFFF)
        if s.ax == 0xFFFF:
            mem.ww(ds, (s.bx + 0x06) & 0xFFFF, 0x0007)
            si_y = mem.rw(ds, (s.si + 0x04) & 0xFFFF)
            _cmp_word(cpu, si_y, 0x0058)
            if si_y > 0x0058:
                mem.ww(ds, (s.bx + 0x06) & 0xFFFF, 0x0001)
        current_dir = mem.rw(ds, (s.bx + 0x06) & 0xFFFF)
        _cmp_word(cpu, current_dir, 0x0001)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x0019)
        if current_dir != 0x0001:
            mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x001F)
        ret()

    si = s.si & 0xFFFF
    _cmp_word(cpu, si, 0xFFFF)
    if si == 0xFFFF:
        ret()
        return

    s.bx = mem.rw(ds, 0xA958)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    target = mem.rw(cs, (s.bx + 0xA42C) & 0xFFFF)
    if target == 0xA4D7:
        run_a4d7_body()
    elif target == 0xA490:
        run_a490_body()
    elif target == 0xA499:
        run_a499_body()
    elif target == 0xA464:
        run_a438_pair(0x0007, 0x0037)
    elif target == 0xA438:
        run_a438_pair(0x0008, 0x0035)
    else:
        tail_original(target, max_steps=160000)


def _run_frame_action_si_followup_a378(
    cpu,
    run_original_near_call: RunOriginalNearCall,
    *,
    caller_name: str,
) -> None:
    """Run the local A378 SI-relative follow-up spawn helper.

    ``A378`` is used by ``A3FF`` after each mirrored A41A table dispatch.  It is
    gated by ``SI != FFFFh``, raw ``A95E`` availability, and copied counter
    ``A3A4 == 0``.  On the open path it performs one ``A4EA`` allocation using
    SI-relative coordinates, aligns Y to a four-pixel boundary, stamps +8/+18,
    then overwrites the first slot's +18 to ``6`` and falls through into the
    same spawn body a second time.  This odd call/fallthrough shape is
    intentional original control flow: an open A378 path creates two slots.
    """
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def call_original(ip: int, ret_ip: int, *, max_steps: int = 80000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"{caller_name} expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    si = s.si & 0xFFFF
    _cmp_word(cpu, si, 0xFFFF)
    if si == 0xFFFF:
        ret()
        return

    v_a95e = mem.rw(ds, 0xA95E)
    _cmp_word(cpu, v_a95e, 0x0000)
    if v_a95e == 0x0000:
        ret()
        return

    v_a3a4 = mem.rw(ds, 0xA3A4)
    _cmp_word(cpu, v_a3a4, 0x0000)
    if v_a3a4 != 0x0000:
        ret()
        return

    def run_a396_body() -> None:
        _inc_mem_word_preserve_cf(cpu, ds, 0xA976)
        v98c0 = mem.rb(ds, 0x98C0)
        _cmp_byte(cpu, v98c0, 0x00)
        if v98c0 != 0:
            mem.wb(ds, 0xBEFF, 0x12)
        call_original(0xA4EA, 0xA3A9, max_steps=80000)
        s.ax = mem.rw(ds, (s.si + 0x04) & 0xFFFF)
        _add_reg16(cpu, 0, 0x0004)
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.ax)
        s.ax = mem.rw(ds, (s.si + 0x02) & 0xFFFF)
        _add_reg16(cpu, 0, 0x0004)
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.ax)
        _and_mem_word(cpu, ds, (s.bx + 0x04) & 0xFFFF, 0xFFFC)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x0008)
        mem.ww(ds, (s.bx + 0x18) & 0xFFFF, 0x0005)
        ret()

    # A378 calls A396 once, overwrites that first slot's +18 stamp to 6 at
    # A391, and then deliberately falls through into A396 a second time.
    # This produces two SI-relative spawns, not one.
    saved_sp = s.sp
    cpu.push(0xA391)
    run_a396_body()
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xA391):
        raise RuntimeError(f"{caller_name} A396 subcall returned to unexpected IP {s.ip:04X}")
    if s.sp != saved_sp:
        raise RuntimeError(f"{caller_name} A396 subcall stack mismatch")
    mem.ww(ds, (s.bx + 0x18) & 0xFFFF, 0x0006)
    run_a396_body()


def run_frame_action_side_anchor_spawn_a3ca(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A3CA, a four-source raw side-anchor spawn dispatcher.

    This is a structural child behind ``A067``.  It alternates raw direction
    stamp ``A3EC`` between ``7`` and ``1`` while dispatching the four SI sources
    ``A966/A968/A96A/A96C`` through local table body ``A41A``.  Keep it as slot
    spawn glue, not a named gameplay weapon/entity.
    """
    if self_disable_if_patched(
        cpu,
        0xA3CA,
        SIG_FRAME_ACTION_SIDE_ANCHOR_SPAWN_A3CA,
        "overkill_frame_action_side_anchor_spawn_a3ca",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def internal_a41a(ret_ip: int) -> None:
        saved_sp = s.sp
        cpu.push(ret_ip & 0xFFFF)
        _run_frame_action_table_body_a41a(
            cpu,
            run_original_near_call,
            caller_name="A3CA",
        )
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (0x1010, ret_ip & 0xFFFF):
            raise RuntimeError(f"A3CA A41A returned to unexpected IP {s.ip:04X}")
        if s.sp != saved_sp:
            raise RuntimeError("A3CA A41A stack mismatch")

    mem.ww(ds, 0xA3EC, 0x0007)
    s.si = mem.rw(ds, 0xA966)
    internal_a41a(0xA3D7)
    mem.ww(ds, 0xA3EC, 0x0001)
    s.si = mem.rw(ds, 0xA968)
    internal_a41a(0xA3E4)
    mem.ww(ds, 0xA3EC, 0x0007)
    s.si = mem.rw(ds, 0xA96A)
    internal_a41a(0xA3F1)
    mem.ww(ds, 0xA3EC, 0x0001)
    s.si = mem.rw(ds, 0xA96C)
    internal_a41a(0xA3FE)
    ret()


def run_frame_action_mirrored_anchor_spawn_a3ff(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A3FF, a two-source mirrored raw anchor spawn dispatcher.

    ``A3FF`` is another structural child behind ``A067``.  It sets ``A3EC`` to
    ``FFFFh``, dispatches ``A962`` and ``A964`` through the local ``A41A`` table,
    and after each source runs the SI-relative ``A378`` follow-up helper.  The
    ``FFFFh`` direction stamp is later converted by the ``A499`` table target
    into raw direction/state fields based on the source Y coordinate.
    """
    if self_disable_if_patched(
        cpu,
        0xA3FF,
        SIG_FRAME_ACTION_MIRRORED_ANCHOR_SPAWN_A3FF,
        "overkill_frame_action_mirrored_anchor_spawn_a3ff",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def internal_call(ret_ip: int, body) -> None:
        saved_sp = s.sp
        cpu.push(ret_ip & 0xFFFF)
        body()
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (0x1010, ret_ip & 0xFFFF):
            raise RuntimeError(f"A3FF internal call returned to unexpected IP {s.ip:04X}")
        if s.sp != saved_sp:
            raise RuntimeError("A3FF internal call stack mismatch")

    mem.ww(ds, 0xA3EC, 0xFFFF)
    s.si = mem.rw(ds, 0xA962)
    internal_call(
        0xA40C,
        lambda: _run_frame_action_table_body_a41a(
            cpu,
            run_original_near_call,
            caller_name="A3FF/A41A",
        ),
    )
    internal_call(
        0xA40F,
        lambda: _run_frame_action_si_followup_a378(
            cpu,
            run_original_near_call,
            caller_name="A3FF/A378",
        ),
    )
    s.si = mem.rw(ds, 0xA964)
    internal_call(
        0xA416,
        lambda: _run_frame_action_table_body_a41a(
            cpu,
            run_original_near_call,
            caller_name="A3FF/A41A",
        ),
    )
    internal_call(
        0xA419,
        lambda: _run_frame_action_si_followup_a378(
            cpu,
            run_original_near_call,
            caller_name="A3FF/A378",
        ),
    )
    ret()


def run_frame_action_spawn_fanout_a067(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A067, the frame action/object-spawn fanout.

    The evidence so far proves this as an input-bit-gated frame helper, not as a
    named weapon/player semantic.  It gates on ``DS:98BE & 10h``, latches
    ``DS:A980``, copies action counters from ``A970/A972/A974/A976`` into the
    ``A3A0..A3A6`` scratch quartet, and fans out through the raw ``DS:A958``
    action table.  Object-slot allocation/setup remains behind the existing
    ``A4EA`` and larger ``A515/A584/A3FF/A3CA/A2A0`` child frontiers.
    """
    if self_disable_if_patched(
        cpu,
        0xA067,
        SIG_FRAME_ACTION_SPAWN_FANOUT_A067,
        "overkill_frame_action_spawn_fanout_a067",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def caller_return_ip() -> int:
        return mem.rw(s.ss & 0xFFFF, s.sp & 0xFFFF)

    def ret() -> None:
        s.ip = cpu.pop()

    def call(ip: int, ret_ip: int, *, max_steps: int = 120000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"A067 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    def tail_original(ip: int, *, max_steps: int = 160000) -> None:
        target = (cs, caller_return_ip())
        saved_verifier = cpu.hook_verifier
        if not getattr(cpu, "hook_verifier_verify_nested_calls", True):
            cpu.hook_verifier = None
        s.ip = ip & 0xFFFF
        try:
            ctx = (
                cpu.coverage_telemetry.bounded_original((cs, ip & 0xFFFF), "bounded original tail jump")
                if cpu.coverage_telemetry is not None
                else None
            )
            if ctx is not None:
                ctx.__enter__()
            try:
                for _ in range(max_steps):
                    if cpu.addr() == target:
                        return
                    cpu.step()
            finally:
                if ctx is not None:
                    ctx.__exit__(None, None, None)
        finally:
            cpu.hook_verifier = saved_verifier
        raise RuntimeError(
            f"A067 interpreted tail 1010:{ip & 0xFFFF:04X} did not reach "
            f"1010:{target[1] & 0xFFFF:04X}; now at "
            f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
        )

    def set_beff_when_98c0_nonzero(value: int) -> None:
        v98c0 = mem.rb(ds, 0x98C0)
        _cmp_byte(cpu, v98c0, 0x00)
        if v98c0 != 0:
            mem.wb(ds, 0xBEFF, value & 0xFF)

    def call_a4ea(ret_ip: int) -> None:
        call(0xA4EA, ret_ip, max_steps=80000)

    def internal_call(ret_ip: int, body) -> None:
        saved_sp = s.sp
        cpu.push(ret_ip & 0xFFFF)
        body()
        s.ip = cpu.pop()
        if s.sp != saved_sp:
            raise RuntimeError("A067 internal call stack mismatch")

    def run_a1ae_coordinate_body() -> None:
        _run_frame_action_coordinate_projection_body_a1ae(cpu)

    def run_a1ab_body() -> None:
        call_a4ea(0xA1AE)
        run_a1ae_coordinate_body()

    def run_a175_body() -> None:
        call_a4ea(0xA178)
        mem.ww(ds, (s.bx + 0x18) & 0xFFFF, 0x000C)
        mem.ww(ds, (s.bx + 0x1C) & 0xFFFF, 0x0007)
        s.si = mem.rw(ds, 0xA96E)
        s.ax = mem.rw(ds, (s.si + 0x02) & 0xFFFF)

    def run_a114_tail_or_body() -> None:
        v_a3a6 = mem.rw(ds, 0xA3A6)
        _cmp_word(cpu, v_a3a6, 0x0000)
        if v_a3a6 != 0:
            ret()
            return

        set_beff_when_98c0_nonzero(0x18)
        _inc_mem_word_preserve_cf(cpu, ds, 0xA974)
        internal_call(0xA12F, run_a175_body)
        _sub_reg16(cpu, 0, 0x0006)
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.ax)
        s.ax = mem.rw(ds, (s.si + 0x04) & 0xFFFF)
        _add_reg16(cpu, 0, 0x0004)
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.ax)

        _inc_mem_word_preserve_cf(cpu, ds, 0xA974)
        internal_call(0xA145, run_a175_body)
        _sub_reg16(cpu, 0, 0x0002)
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.ax)
        s.ax = mem.rw(ds, (s.si + 0x04) & 0xFFFF)
        _sub_reg16(cpu, 0, 0x0004)
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.ax)
        mem.ww(ds, (s.bx + 0x06) & 0xFFFF, 0x0007)

        _inc_mem_word_preserve_cf(cpu, ds, 0xA974)
        internal_call(0xA160, run_a175_body)
        _sub_reg16(cpu, 0, 0x0002)
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.ax)
        s.ax = mem.rw(ds, (s.si + 0x04) & 0xFFFF)
        _add_reg16(cpu, 0, 0x000C)
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.ax)
        mem.ww(ds, (s.bx + 0x06) & 0xFFFF, 0x0001)
        ret()

    def run_a18a_tail() -> None:
        internal_call(0xA18D, run_a1ab_body)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x0033)
        set_beff_when_98c0_nonzero(0x14)
        ret()

    def run_a19f_tail() -> None:
        set_beff_when_98c0_nonzero(0x13)
        run_a1ab_body()
        ret()

    def run_a1c8_tail() -> None:
        set_beff_when_98c0_nonzero(0x15)
        call_a4ea(0xA1D7)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x0018)
        internal_call(0xA1DF, run_a1ae_coordinate_body)
        call_a4ea(0xA1E2)
        internal_call(0xA1E5, run_a1ae_coordinate_body)
        mem.ww(ds, (s.bx + 0x06) & 0xFFFF, 0x0007)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x001F)
        input_flags = mem.rb(ds, 0x98BE)
        cpu.set_logic_flags(input_flags & 0x02, 8)
        if input_flags & 0x02:
            ret()
            return
        mem.ww(ds, (s.bx + 0x06) & 0xFFFF, 0x0001)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x0019)
        input_flags = mem.rb(ds, 0x98BE)
        cpu.set_logic_flags(input_flags & 0x01, 8)
        if input_flags & 0x01:
            ret()
            return
        mem.ww(ds, (s.bx + 0x06) & 0xFFFF, 0x0000)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x0018)
        ret()

    def run_a0e8_subroutine() -> None:
        v_a958 = mem.rw(ds, 0xA958)
        _cmp_word(cpu, v_a958, 0x0005)
        if v_a958 == 0x0005:
            call(0xA2A0, 0xA0F2, max_steps=120000)

        v_a96e = mem.rw(ds, 0xA96E)
        _cmp_word(cpu, v_a96e, 0xFFFF)
        if v_a96e != 0xFFFF:
            # A114 is called as a child here, so its RET returns to A0FC.
            saved_sp = s.sp
            cpu.push(0xA0FC)
            run_a114_tail_or_body()
            if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xA0FC):
                raise RuntimeError(
                    f"A067 expected internal A114 call to return A0FC, got "
                    f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
                )
            if s.sp != saved_sp:
                raise RuntimeError("A067 internal A114 stack mismatch")

        s.bx = mem.rw(ds, 0xA958)
        s.bx = cpu.shift(4, s.bx, 1, 16)
        target = mem.rw(cs, (s.bx - 0x5EF8) & 0xFFFF)
        if target == 0xA19F:
            run_a19f_tail()
        elif target == 0xA18A:
            run_a18a_tail()
        elif target == 0xA1C8:
            run_a1c8_tail()
        else:
            tail_original(target, max_steps=180000)

    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x10, 8)
    if not (input_flags & 0x10):
        mem.ww(ds, 0xA980, 0x0000)
        ret()
        return

    v_a980 = mem.rw(ds, 0xA980)
    _cmp_word(cpu, v_a980, 0x0000)
    if v_a980 != 0:
        v9790 = mem.rb(ds, 0x9790)
        _cmp_byte(cpu, v9790, 0x01)
        if v9790 != 0x01:
            v232a = mem.rw(ds, 0x232A)
            _cmp_word(cpu, v232a, 0x000F)
            if v232a != 0x000F:
                ret()
                return

    mem.ww(ds, 0xA980, 0x0001)
    v2350 = mem.rw(ds, 0x2350)
    _cmp_word(cpu, v2350, 0x00B6)
    if v2350 <= 0x00B6:
        v_bdac = mem.rw(ds, 0xBDAC)
        _cmp_word(cpu, v_bdac, 0x0000)
        if v_bdac == 0:
            v_a958 = mem.rw(ds, 0xA958)
            _cmp_word(cpu, v_a958, 0x0002)
            if v_a958 == 0x0002:
                run_a1c8_tail()
            else:
                run_a19f_tail()
            return

    s.ax = mem.rw(ds, 0xA970)
    mem.ww(ds, 0xA3A0, s.ax)
    s.ax = mem.rw(ds, 0xA972)
    mem.ww(ds, 0xA3A2, s.ax)
    s.ax = mem.rw(ds, 0xA976)
    mem.ww(ds, 0xA3A4, s.ax)
    s.ax = mem.rw(ds, 0xA974)
    mem.ww(ds, 0xA3A6, s.ax)

    v_bdac = mem.rw(ds, 0xBDAC)
    _cmp_word(cpu, v_bdac, 0x0001)
    if v_bdac == 1:
        v_be06 = mem.rw(ds, 0xBE06)
        _cmp_word(cpu, v_be06, 0x0008)
        if v_be06 == 0x0008:
            run_a114_tail_or_body()
            return
        v_be06 = mem.rw(ds, 0xBE06)
        _cmp_word(cpu, v_be06, 0x000F)
        if v_be06 > 0x000F:
            tail_original(0xA515, max_steps=180000)
            return

    call(0xA515, 0xA0DB, max_steps=120000)
    call(0xA584, 0xA0DE, max_steps=120000)
    call(0xA3FF, 0xA0E1, max_steps=120000)
    call(0xA3CA, 0xA0E4, max_steps=120000)
    saved_sp = s.sp
    cpu.push(0xA0E7)
    run_a0e8_subroutine()
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xA0E7):
        raise RuntimeError(
            f"A067 expected internal A0E8 call to return A0E7, got "
            f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
        )
    if s.sp != saved_sp:
        raise RuntimeError("A067 internal A0E8 stack mismatch")
    ret()



def run_frame_controller_9b2e(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift the 1010:9B2E frame-controller child of the 97B2 loop.

    This routine is still raw frame/controller logic, not a semantic player or
    enemy update.  It owns the original ordering between the input poll, the
    current BP object slot, four direct movement bits, the A067 action/helper
    frontier, optional contact probing, coordinate-ring maintenance, and linked
    child-coordinate propagation.

    Larger children such as ``A067`` and ``9CB6`` deliberately remain separate
    boundaries: this parent composes them in ASM order instead of duplicating
    their internal logic.
    """
    if self_disable_if_patched(
        cpu,
        0x9B2E,
        SIG_FRAME_CONTROLLER_9B2E,
        "overkill_frame_controller_9b2e",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def call(ip: int, ret_ip: int, *, max_steps: int = 20000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"9B2E expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    def run_9aff_tail() -> None:
        # 9AFF is the early/transition tail reached when the active tracked
        # object/list state is absent.  Keep it inside this parent because both
        # 9B61 and 9B68 branch here instead of returning through a child.
        v2326 = mem.rw(ds, 0x2326)
        _cmp_word(cpu, v2326, 0x0003)
        if v2326 != 0x0003:
            ret()
            return

        _inc_mem_word_preserve_cf(cpu, s.ss & 0xFFFF, (s.bp + 0x08) & 0xFFFF)
        bp8 = mem.rw(s.ss & 0xFFFF, (s.bp + 0x08) & 0xFFFF)
        _cmp_word(cpu, bp8, 0x000F)
        if bp8 != 0x000F:
            ret()
            return

        mem.ww(s.ss & 0xFFFF, (s.bp + 0x00) & 0xFFFF, 0x0000)
        call(0x4DBF, 0x9B19)
        mem.ww(ds, 0xA346, 0x0001)
        v_a97a_tail = mem.rw(ds, 0xA97A)
        _cmp_word(cpu, v_a97a_tail, 0x0000)
        if v_a97a_tail != 0x0000:
            ret()
            return
        mem.ww(ds, 0xA342, 0x0001)
        ret()

    mem.ww(ds, 0xA346, 0x0000)
    mem.ww(ds, 0xA344, 0x0000)
    call(0x0162, 0x9B3D)

    v_a47c = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, v_a47c, 0x0000)
    if v_a47c != 0x0000:
        call(0x99F6, 0x9B47)

    v_a47c = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, v_a47c, 0x0004)
    if v_a47c == 0x0004:
        mem.ww(ds, 0xA344, 0x0001)
        ret()
        return

    mem.ww(ds, 0xA278, 0x0000)
    s.bp = 0x237C
    call(0xA212, 0x9B61, max_steps=60000)

    v_a95a = mem.rw(ds, 0xA95A)
    _cmp_word(cpu, v_a95a, 0xFFFF)
    if v_a95a == 0xFFFF:
        run_9aff_tail()
        return

    v_a97a = mem.rw(ds, 0xA97A)
    _cmp_word(cpu, v_a97a, 0x0000)
    if v_a97a == 0x0000:
        run_9aff_tail()
        return

    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x08, 8)
    if input_flags & 0x08:
        call(0xA5D1, 0x9B79)

    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x04, 8)
    if input_flags & 0x04:
        call(0xA5EA, 0x9B83)

    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x01, 8)
    if input_flags & 0x01:
        call(0xA607, 0x9B8D)

    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x02, 8)
    if input_flags & 0x02:
        call(0xA5F9, 0x9B97)

    v2350 = mem.rw(ds, 0x2350)
    _cmp_word(cpu, v2350, 0x00B6)
    if v2350 > 0x00B6:
        input_flags = mem.rb(ds, 0x98BE)
        cpu.set_logic_flags(input_flags & 0x20, 8)
        if input_flags & 0x20:
            call(0x8546, 0x9BA9, max_steps=60000)

    call(0xA66F, 0x9BAC, max_steps=120000)
    call(0xA067, 0x9BAF, max_steps=160000)

    v978e = mem.rb(ds, 0x978E)
    _cmp_byte(cpu, v978e, 0x00)
    if v978e != 0x00:
        v98c8 = mem.rb(ds, 0x98C8)
        _cmp_byte(cpu, v98c8, 0x01)
        if v98c8 == 0x01:
            call(0x9D4D, 0x9BC0, max_steps=60000)

    v_a47c = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, v_a47c, 0x0001)
    if v_a47c <= 0x0001:
        call(0xA616, 0x9BCA)

    v_a47c = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, v_a47c, 0x0000)
    if v_a47c == 0x0000:
        call(0x9CB6, 0x9BD4, max_steps=120000)

    v2350 = mem.rw(ds, 0x2350)
    _cmp_word(cpu, v2350, 0x00B6)
    if v2350 > 0x00B6:
        call(0x9C01, 0x9BDF, max_steps=120000)

    call(0x9CF1, 0x9BE2)
    call(0x9CD9, 0x9BE5)
    call(0xA031, 0x9BE8)

    v_bdac = mem.rw(ds, 0xBDAC)
    _cmp_word(cpu, v_bdac, 0x0000)
    if v_bdac == 0x0000:
        v2350 = mem.rw(ds, 0x2350)
        _cmp_word(cpu, v2350, 0x00B6)
        if v2350 <= 0x00B6:
            ret()
            return

    call(0x9FAF, 0x9BFA, max_steps=120000)
    ret()


SIG_INTERSTITIAL_STATUS_CELL_D367 = bytes.fromhex(
    "b4 47 b0 03 e8 92 86 33 f6 2e 8e 1e b6 95 e8 f4 86 "
    "2e 8e 1e 96 95 c3"
)
SIG_INTERSTITIAL_TIMED_INPUT_LOOP_D318 = bytes.fromhex(
    "e8 57 33 e8 01 7e e8 cc 79 2e 83 3e bc 95 01 75 03 "
    "e8 b0 88 e8 38 00 e8 32 7a 9a 22 09 8f 1f e8 02 34 "
    "e8 65 8d e8 20 7e e8 36 33 e8 83 7d ff 06 d8 be 81 "
    "3e d8 be c8 00 77 0a e8 0d 2e f6 06 be 98 10 74 bc "
    "e8 03 2e f6 06 be 98 10 75 f6 c3"
)
SIG_STATUS_CELL_SEED_852B = bytes.fromhex(
    "b0 1c 50 e8 cf d4 c7 46 00 24 00 89 7e 02 c7 46 08 "
    "00 00 83 c5 0a 58 80 c4 10 c3"
)
SIG_STATUS_CELL_LIST_SEED_8517 = bytes.fromhex(
    "c7 06 fa 95 ff ff bd 82 96 b4 87 e8 06 00 e8 03 00 e8 00 00"
)


def run_status_cell_seed_852b(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:852B, one raw status/list cell descriptor seed.

    The routine converts ``AX`` through the existing ``5A00`` coordinate helper,
    stores a compact 10-byte descriptor at ``SS:BP``, advances ``BP`` by one
    descriptor, restores the saved AX, increments AH by 10h, and returns.
    """
    if self_disable_if_patched(cpu, 0x852B, SIG_STATUS_CELL_SEED_852B, "overkill_status_cell_seed_852b"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF

    s.ax = (s.ax & 0xFF00) | 0x001C
    cpu.push(s.ax)
    run_original_near_call(cpu, 0x5A00, 0x8531)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x8531):
        raise RuntimeError(
            f"852B expected 1010:5A00 to return 1010:8531, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
        )
    bp = s.bp & 0xFFFF
    mem.ww(ss, bp + 0x00, 0x0024)
    mem.ww(ss, bp + 0x02, s.di & 0xFFFF)
    mem.ww(ss, bp + 0x08, 0x0000)
    old_bp = s.bp & 0xFFFF
    result_bp = old_bp + 0x000A
    s.bp = result_bp & 0xFFFF
    cpu.set_add_flags(old_bp, 0x000A, result_bp, 16)
    s.ax = cpu.pop()
    old_ah = (s.ax >> 8) & 0xFF
    result_ah = old_ah + 0x10
    cpu.set_reg8(4, result_ah)
    cpu.set_add_flags(old_ah, 0x10, result_ah, 8)
    s.ip = cpu.pop()


def run_status_cell_list_seed_8517(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:8517, a four-entry raw status/list descriptor builder.

    Original ASM deliberately uses three CALLs into 852B and then falls through
    into 852B for the fourth descriptor.  The hook preserves that call/stack
    shape so this remains an exact low-level list seed, not a semantic HUD model.
    """
    if self_disable_if_patched(cpu, 0x8517, SIG_STATUS_CELL_LIST_SEED_8517, "overkill_status_cell_list_seed_8517"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def call_852b(ret: int) -> None:
        # The third original CALL returns to 852B itself, so the generic bounded
        # CALL helper would accept the target before executing any instruction.
        # Run the lifted 852B body with explicit CALL stack semantics instead.
        cpu.push(ret & 0xFFFF)
        run_status_cell_seed_852b(cpu, self_disable_if_patched, run_original_near_call)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret & 0xFFFF):
            raise RuntimeError(
                f"8517 expected 852B to return 1010:{ret & 0xFFFF:04X}, "
                f"got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    mem.ww(ds, 0x95FA, 0xFFFF)
    s.bp = 0x9682
    s.ax = (0x87 << 8) | (s.ax & 0x00FF)
    call_852b(0x8525)
    call_852b(0x8528)
    call_852b(0x852B)
    # The fourth descriptor is the original fall-through into 852B.  Do not push
    # a synthetic return word; 852B must consume the caller's return address.
    run_status_cell_seed_852b(cpu, self_disable_if_patched, run_original_near_call)


def run_interstitial_status_cell_d367(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:D367, a small interstitial/status cell blit helper.

    The helper prepares AX for ``5A00`` coordinate conversion, switches DS to
    the cell-source segment at ``CS:95B6``, dispatches ``5A6C`` to the current
    video-mode blitter, then restores DS from ``CS:9596``.  It is still raw
    frame/HUD glue: no semantic screen or menu model is introduced here.
    """
    if self_disable_if_patched(
        cpu,
        0xD367,
        SIG_INTERSTITIAL_STATUS_CELL_D367,
        "overkill_interstitial_status_cell_d367",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF

    def call(ip: int, ret: int, *, max_steps: int = 20000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret & 0xFFFF):
            raise RuntimeError(
                f"D367 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret & 0xFFFF:04X}, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    s.ax = (0x47 << 8) | 0x03
    call(0x5A00, 0xD36E)
    s.si = 0
    cpu.set_logic_flags(0, 16)  # XOR SI,SI
    s.ds = mem.rw(cs, 0x95B6)
    call(0x5A6C, 0xD378)
    s.ds = mem.rw(cs, 0x9596)
    s.ip = cpu.pop()


def run_interstitial_timed_input_loop_d318(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
    run_original_far_call: RunOriginalFarCall,
) -> None:
    """Lift one iteration of 1010:D318 timed interstitial/input-wait loop.

    This loop is a frame-script controller used after the 97B2 path in observed
    Tandy runs.  Each iteration services graphics/sound/status children, bumps
    ``DS:BED8``, then either loops back to D318 while the timeout is active or
    waits for the input-release bit to clear before returning to its caller.

    Keeping this as an ASM-shaped frame glue routine removes repeated anonymous
    ``D318`` interpreted noise and exposes the higher-level direction without
    inventing a semantic screen/menu state yet.
    """
    if self_disable_if_patched(
        cpu,
        0xD318,
        SIG_INTERSTITIAL_TIMED_INPUT_LOOP_D318,
        "overkill_interstitial_timed_input_loop_d318",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def call(ip: int, ret: int, *, max_steps: int = 20000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret & 0xFFFF):
            raise RuntimeError(
                f"D318 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret & 0xFFFF:04X}, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    def call_input_until_release(return_ip: int) -> None:
        while True:
            call(0x0162, return_ip)
            input_flags = mem.rb(ds, 0x98BE)
            cpu.set_logic_flags(input_flags & 0x10, 8)
            if not (input_flags & 0x10):
                return

    call(0x0672, 0xD31B)
    call(0x511F, 0xD31E)
    call(0x4CED, 0xD321)

    mode = mem.rw(cs, 0x95BC)
    _cmp_word(cpu, mode, 0x0001)
    if mode == 0x0001:
        call(0x5BDC, 0xD32C)

    call(0xD367, 0xD32F)
    call(0x4D64, 0xD332)
    run_original_far_call(cpu, 0x1F8F, 0x0922, 0xD337)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0xD337):
        raise RuntimeError(
            f"D318 expected 1F8F:0922 to return to 1010:D337, "
            f"got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
        )
    call(0x073C, 0xD33A)
    call(0x60A2, 0xD33D)
    call(0x5160, 0xD340)
    call(0x0679, 0xD343)
    call(0x50C9, 0xD346)

    counter = _inc_mem_word_preserve_cf(cpu, ds, 0xBED8)
    _cmp_word(cpu, counter, 0x00C8)
    if counter > 0x00C8:
        call_input_until_release(0xD35F)
        s.ip = cpu.pop()
        return

    call(0x0162, 0xD355)
    input_flags = mem.rb(ds, 0x98BE)
    cpu.set_logic_flags(input_flags & 0x10, 8)
    if not (input_flags & 0x10):
        s.ip = 0xD318
        return

    call_input_until_release(0xD35F)
    s.ip = cpu.pop()




def run_frame_loop_97b2(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift one iteration of the 1010:97B2 gameplay/attract frame loop.

    This is the frame controller that surrounds the large 9B2E input/game-state
    controller.  9B2E is now a separate verifier-visible parent hook, so this
    wrapper still owns only the finite call/branch glue around it.
    """
    if self_disable_if_patched(cpu, 0x97B2, SIG_FRAME_LOOP_97B2, "overkill_frame_loop_97b2"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def call(ip: int, ret: int, *, max_steps: int = 20000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret & 0xFFFF):
            raise RuntimeError(
                f"97B2 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret & 0xFFFF:04X}, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    call(0x0672, 0x97B5)
    call(0x511F, 0x97B8)
    call(0xA846, 0x97BB)

    v_a97a = mem.rw(ds, 0xA97A)
    _cmp_word(cpu, v_a97a, 0x0000)
    if v_a97a == 0x0000:
        call(0x981F, 0x97C5)

    call(0x5BDC, 0x97C8)
    call(0xA90C, 0x97CB)
    call(0x9B2E, 0x97CE, max_steps=120000)

    v_a344 = mem.rw(ds, 0xA344)
    _cmp_word(cpu, v_a344, 0x0001)
    if v_a344 == 0x0001:
        s.ip = 0x9734
        return

    v_a342 = mem.rw(ds, 0xA342)
    _cmp_word(cpu, v_a342, 0x0001)
    if v_a342 == 0x0001:
        s.ip = 0x9902
        return

    v_a346 = mem.rw(ds, 0xA346)
    _cmp_word(cpu, v_a346, 0x0001)
    if v_a346 == 0x0001:
        s.ip = 0x9908
        return

    call(0xA940, 0x97EF)
    call(0x073C, 0x97F2)
    call(0x60A2, 0x97F5)

    v978f = mem.rb(ds, 0x978F)
    _cmp_byte(cpu, v978f, 0x00)
    if v978f != 0:
        v9902 = mem.rb(ds, 0x9902)
        _cmp_byte(cpu, v9902, 0x01)
        if v9902 == 0x01:
            s.ip = 0x9734
            return

    v9908 = mem.rb(ds, 0x9908)
    _cmp_byte(cpu, v9908, 0x01)
    if v9908 == 0x01:
        call(0x9937, 0x9810)

    v98c5 = mem.rb(ds, 0x98C5)
    _cmp_byte(cpu, v98c5, 0x01)
    if v98c5 == 0x01:
        s.ip = 0x9862
        return

    call(0x5160, 0x981A)
    call(0x0679, 0x981D)
    s.ip = 0x97B2



SIG_TRANSITION_STATUS_WAIT_9908 = bytes.fromhex(
    "e8 d0 2b ff 0e 58 23 80 3e 8d 97 00 74 04 ff 06 58 23 "
    "80 3e c0 98 00 74 07"
)
SIG_TRANSITION_INPUT_RELEASE_WAIT_9921 = bytes.fromhex(
    "80 3e fe be 00 75 f9"
)


def run_transition_status_wait_9908(
    cpu,
    self_disable_if_patched,
    call_reset_object_slot_and_status_setup,
) -> None:
    """Lift 1010:9908, a transition/status reset plus optional input wait.

    This parent is reached when the 97B2 frame controller observes the A346
    transition flag.  It resets object/status state via C4DB, adjusts the
    transition countdown at DS:2358, optionally waits for the BEFE input latch
    to clear, then jumps back to the 9773 setup/frame-controller prelude.
    """
    if self_disable_if_patched(cpu, 0x9908, SIG_TRANSITION_STATUS_WAIT_9908, "overkill_transition_status_wait_9908"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    call_reset_object_slot_and_status_setup(0x990B)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x990B):
        raise RuntimeError(
            f"9908 expected C4DB to return to 1010:990B, got "
            f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
        )

    _dec_mem_word_preserve_cf(cpu, ds, 0x2358)

    v978d = mem.rb(ds, 0x978D)
    _cmp_byte(cpu, v978d, 0x00)
    if v978d != 0:
        _inc_mem_word_preserve_cf(cpu, ds, 0x2358)

    v98c0 = mem.rb(ds, 0x98C0)
    _cmp_byte(cpu, v98c0, 0x00)
    if v98c0 != 0:
        # Preserve the original boundary: the tight 9921 wait loop is already a
        # shared hook (``overkill_sound_active_wait_9921``) and is a useful
        # checkpoint on its own.  Do not consume it inside the 9908 parent.
        s.ip = 0x9921
        return

    s.ip = 0x9773



SIG_TRANSITION_INPUT_RELEASE_TAIL_9928 = bytes.fromhex(
    "80 3e c0 98 00 74 05 c6 06 ff be 02 e9 3c fe"
)


def run_transition_input_release_tail_9928(cpu, self_disable_if_patched) -> None:
    """Lift 1010:9928, the post-wait transition input/sound latch tail."""
    if self_disable_if_patched(
        cpu,
        0x9928,
        SIG_TRANSITION_INPUT_RELEASE_TAIL_9928,
        "overkill_transition_input_release_tail_9928",
    ):
        return

    s = cpu.s
    ds = s.ds & 0xFFFF
    v98c0 = cpu.mem.rb(ds, 0x98C0)
    _cmp_byte(cpu, v98c0, 0x00)
    if v98c0 != 0:
        cpu.mem.wb(ds, 0xBEFF, 0x02)
    s.ip = 0x9773

def run_transition_input_release_wait_9921(cpu, self_disable_if_patched) -> None:
    """Lift the tight 1010:9921 wait for the BEFE input latch to clear."""
    if self_disable_if_patched(
        cpu,
        0x9921,
        SIG_TRANSITION_INPUT_RELEASE_WAIT_9921,
        "overkill_transition_input_release_wait_9921",
    ):
        return

    s = cpu.s
    ds = s.ds & 0xFFFF
    v_befe = cpu.mem.rb(ds, 0xBEFE)
    _cmp_byte(cpu, v_befe, 0x00)
    s.ip = 0x9921 if v_befe != 0 else 0x9928

def run_frame_effect_status_text_60a2(
    cpu,
    self_disable_if_patched,
    call_effect_gate_77c5,
    call_status_counter_5f61,
    call_status_text_5edb,
) -> None:
    """Lift 1010:60A2, the per-frame effect/status/text glue block.

    The routine is only a three-call near helper: 77C5 effect gate, 5F61 global
    status counters, 5EDB HUD/status text.  It is frame orchestration glue, not
    standalone gameplay behavior, so child ownership remains with the existing
    effect/text/game-state hooks.
    """
    if self_disable_if_patched(cpu, 0x60A2, SIG_FRAME_EFFECT_STATUS_TEXT_60A2, "overkill_frame_effect_status_text_60a2"):
        return

    s = cpu.s
    cs = s.cs & 0xFFFF

    call_effect_gate_77c5(0x60A5)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x60A5):
        raise RuntimeError(f"60A2 expected 77C5 to return to 60A5, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    call_status_counter_5f61(0x60A8)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x60A8):
        raise RuntimeError(f"60A2 expected 5F61 to return to 60A8, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    call_status_text_5edb(0x60AB)
    if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, 0x60AB):
        raise RuntimeError(f"60A2 expected 5EDB to return to 60AB, got {s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}")

    s.ip = cpu.pop()

def _run_sound_state_select_cb1c(cpu) -> None:
    """Mirror the tiny 1010:CB1C sound-state selector used by 5F61.

    This is deliberately local to frame orchestration because 5F61 only needs
    this small leaf to preserve byte/flag effects when a status countdown reaches
    zero.  It is not the AdLib path; it writes the same PC-speaker/shared sound
    request bytes as the original leaf.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    al = cpu.get_reg8(0)
    mem.wb(ds, 0x98C2, al)
    v98c1 = mem.rb(ds, 0x98C1)
    _cmp_byte(cpu, v98c1, 0)
    if v98c1 == 0:
        return

    cpu.set_reg8(4, 0)  # XOR AH,AH
    cpu.set_logic_flags(0, 8)
    s.bx = 0x2032
    s.es = s.bx
    es_value = mem.rb(s.es & 0xFFFF, 0x0009)
    _cmp_byte(cpu, al, es_value)
    if al == es_value:
        return
    mem.ww(s.es & 0xFFFF, 0x0008, s.ax)
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)


def _xlat_state_byte(cpu) -> int:
    ds = cpu.s.ds & 0xFFFF
    al = cpu.mem.rb(ds, 0x2356)
    cpu.set_reg8(0, al)
    cpu.s.bx = 0x231E
    value = cpu.mem.rb(ds, (cpu.s.bx + al) & 0xFFFF)
    cpu.set_reg8(0, value)
    return value


def _call_frame_effect_tick_606f(cpu, run_original_near_call: RunOriginalNearCall) -> None:
    """Mirror the 606F helper called by 5F61, including call-frame scratch.

    The only not-yet-lifted tail is 9EE4/77DF, which is an effect/rendering
    island.  When that rare branch is reached we run it as a bounded original
    near call so 5F61 can still be a complete near-return proof boundary while
    the remaining effect island stays explicitly identified.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    ss = cpu.s.ss & 0xFFFF
    sp_at_call = cpu.s.sp & 0xFFFF

    def finish_606f_ret() -> None:
        # 5F61 reaches 606F via CALL 606F, so even when Python inlines the body,
        # the full-memory verifier can see the balanced return word below SP.
        mem.ww(ss, (sp_at_call - 2) & 0xFFFF, 0x606E)

    bedc = mem.rw(ds, 0xBEDC)
    _cmp_word(cpu, bedc, 1)
    if bedc > 1:
        v232e = mem.rw(ds, 0x232E)
        _cmp_word(cpu, v232e, 0x003F)
    else:
        v2330 = mem.rw(ds, 0x2330)
        _cmp_word(cpu, v2330, 0x007F)

    if cpu.get_flag(ZF):
        # 6084 CALL 9EE4; continue at 6087, then run the rest of 606F.
        cpu.push(0x606E)
        run_original_near_call(cpu, 0x9EE4, 0x6087)
        # We are now logically at 6087 with the 606E frame still on the stack.
        if (cpu.s.sp & 0xFFFF) != ((sp_at_call - 2) & 0xFFFF):
            raise RuntimeError(
                f"9EE4 did not preserve 606F stack frame; SP={cpu.s.sp:04X} expected {(sp_at_call - 2) & 0xFFFF:04X}"
            )
        # Simulate the eventual RET from 606F back to 606E, but keep the scratch.
        ret = cpu.pop()
        if ret != 0x606E:
            raise RuntimeError(f"606F expected return word 606E after 9EE4, got {ret:04X}")

    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, 2)
    if v2384 != 2:
        finish_606f_ret()
        return

    v232c = mem.rw(ds, 0x232C)
    _cmp_word(cpu, v232c, 0x001F)
    if v232c != 0x001F:
        finish_606f_ret()
        return

    old = mem.rw(ds, 0x234A)
    result = old ^ 0x0001
    mem.ww(ds, 0x234A, result)
    cpu.set_logic_flags(result, 16)
    if result != 0:
        finish_606f_ret()
        return

    # 609F JMP 9EE4.  Because 606F was itself called, 9EE4's RET lands at 606E.
    run_original_near_call(cpu, 0x9EE4, 0x606E)


def run_frame_status_counter_update_5f61(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift the finite 1010:5F61 per-frame status/counter update.

    This is frame orchestration glue: it advances global animation/status
    counters, requests an occasional sound-state change through CB1C, and calls
    the separate 606F effect tick.  It does not own the effect renderer itself;
    9EE4/77DF remains a named bounded effect island until lifted separately.
    """
    if self_disable_if_patched(
        cpu,
        0x5F61,
        SIG_FRAME_STATUS_COUNTER_UPDATE_5F61,
        "overkill_frame_status_counter_update_5f61",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    v_a47e = mem.rw(ds, 0xA47E)
    _cmp_word(cpu, v_a47e, 0)
    if v_a47e == 0:
        v_a480 = mem.rw(ds, 0xA480)
        _cmp_word(cpu, v_a480, 0)
        if v_a480 != 0:
            dec = _dec_mem_word_preserve_cf(cpu, ds, 0xA480)
            if dec == 0:
                al = _xlat_state_byte(cpu)
                v2350 = mem.rw(ds, 0x2350)
                _cmp_word(cpu, v2350, 0x0750)
                if v2350 >= 0x0750:
                    al = 0x06
                    cpu.set_reg8(0, al)
                _run_sound_state_select_cb1c(cpu)
                # CB1C may restore DS from the game's data-segment cell.
                ds = s.ds & 0xFFFF

    v2328 = mem.rw(ds, 0x2328)
    _cmp_word(cpu, v2328, 7)
    if v2328 == 7:
        v2342 = mem.rw(ds, 0x2342)
        _cmp_word(cpu, v2342, 0xFFFF)
        if v2342 != 0xFFFF:
            inc = _inc_mem_word_preserve_cf(cpu, ds, 0x2344)
            _cmp_word(cpu, inc, 2)
            if inc == 2:
                old = mem.rw(ds, 0x2342)
                mem.ww(ds, 0x2342, (-old) & 0xFFFF)
                cpu.set_sub_flags(0, old, -old, 16)
                _inc_mem_word_preserve_cf(cpu, ds, 0x2348)
        else:
            dec = _dec_mem_word_preserve_cf(cpu, ds, 0x2344)
            if dec == 0:
                old = mem.rw(ds, 0x2342)
                mem.ww(ds, 0x2342, (-old) & 0xFFFF)
                cpu.set_sub_flags(0, old, -old, 16)
                _inc_mem_word_preserve_cf(cpu, ds, 0x2348)

    _and_mem_word(cpu, ds, 0x2348, 0x000F)
    if mem.rw(ds, 0x2348) == 0:
        mem.ww(ds, 0x2346, 0x0008)
        _inc_mem_word_preserve_cf(cpu, ds, 0x2348)

    _inc_mem_word_preserve_cf(cpu, ds, 0x2332)
    _and_mem_word(cpu, ds, 0x2332, 0x0003)
    if mem.rw(ds, 0x2332) == 0:
        _inc_mem_word_preserve_cf(cpu, ds, 0x2334)
        v2334 = mem.rw(ds, 0x2334)
        _cmp_word(cpu, v2334, 0x000A)
        if v2334 >= 0x000A:
            mem.ww(ds, 0x2334, 0)

        _inc_mem_word_preserve_cf(cpu, ds, 0x2338)
        v2338 = mem.rw(ds, 0x2338)
        _cmp_word(cpu, v2338, 0x0006)
        if v2338 >= 0x0006:
            mem.ww(ds, 0x2338, 0)

        _inc_mem_word_preserve_cf(cpu, ds, 0x233A)
        v233a = mem.rw(ds, 0x233A)
        _cmp_word(cpu, v233a, 0x0005)
        if v233a >= 0x0005:
            mem.ww(ds, 0x233A, 0)

        _inc_mem_word_preserve_cf(cpu, ds, 0x233E)
        v233e = mem.rw(ds, 0x233E)
        _cmp_word(cpu, v233e, 0x0003)
        if v233e >= 0x0003:
            mem.ww(ds, 0x233E, 0)

        _inc_mem_word_preserve_cf(cpu, ds, 0x233C)
        _and_mem_word(cpu, ds, 0x233C, 0x0003)
        _inc_mem_word_preserve_cf(cpu, ds, 0x2336)
        _and_mem_word(cpu, ds, 0x2336, 0x0007)
        _inc_mem_word_preserve_cf(cpu, ds, 0xA7A0)

    old2324 = mem.rw(ds, 0x2324)
    result2324 = old2324 ^ 0x0001
    mem.ww(ds, 0x2324, result2324)
    cpu.set_logic_flags(result2324, 16)

    _inc_mem_word_preserve_cf(cpu, ds, 0x2326)
    _and_mem_word(cpu, ds, 0x2326, 0x0003)
    _inc_mem_word_preserve_cf(cpu, ds, 0x2328)
    _and_mem_word(cpu, ds, 0x2328, 0x0007)
    _inc_mem_word_preserve_cf(cpu, ds, 0x232A)
    _and_mem_word(cpu, ds, 0x232A, 0x000F)
    _inc_mem_word_preserve_cf(cpu, ds, 0x232C)
    _and_mem_word(cpu, ds, 0x232C, 0x001F)
    _inc_mem_word_preserve_cf(cpu, ds, 0x232E)
    _and_mem_word(cpu, ds, 0x232E, 0x003F)
    _inc_mem_word_preserve_cf(cpu, ds, 0x2330)
    _and_mem_word(cpu, ds, 0x2330, 0x007F)

    _call_frame_effect_tick_606f(cpu, run_original_near_call)
    s.ip = cpu.pop()



def run_frame_service_gate_073c(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:073C, the tiny per-frame service/platform gate.

    In the normal cold-start/attract frame path DS:9907 is not 1, so this
    routine is a three-instruction gate returning immediately to D022 while
    preserving the CMP flags.  The rare enabled path is explicit platform/UI
    glue, not gameplay logic; keep it bounded-original for now so the hook can
    safely own the hot gate without pretending to understand the longer service
    tail.
    """
    if self_disable_if_patched(
        cpu,
        0x073C,
        SIG_FRAME_SERVICE_GATE_073C,
        "overkill_frame_service_gate_073c",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    v9907 = mem.rb(ds, 0x9907)
    _cmp_byte(cpu, v9907, 0x01)
    if v9907 != 0x01:
        s.ip = cpu.pop()
        return

    # 0744+ is a longer platform/UI service path reached only when the gate is
    # armed.  It contains several separate calls and a BDAC guard; keep it as a
    # bounded original continuation until a real trace exercises it enough to
    # split into smaller named children.
    s.ip = 0x0744
    run_original_near_call(cpu, 0x0744, cpu.pop())



def run_frame_ui_state_update_d04d(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:D04D, the finite per-frame UI/demo-state update block.

    This is frame orchestration, not gameplay object logic.  It draws the small
    status/menu cell selected by the current BE06 script state, runs the A212
    demo-object list maintenance helper, advances the BE08/BE0A timers, and
    either returns to the main frame loop or hands off to the original jump-table
    script continuation when a state transition is due.
    """
    if self_disable_if_patched(
        cpu,
        0xD04D,
        SIG_FRAME_UI_STATE_UPDATE_D04D,
        "overkill_frame_ui_state_update_d04d",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds0 = s.ds & 0xFFFF

    mem.ww(ds0, 0xA278, 0x0000)
    cpu.set_reg8(0, 0x1F)
    cpu.set_reg8(4, 0x18)
    run_original_near_call(cpu, 0x5A00, 0xD05A)
    if s.ip != 0xD05A:
        raise RuntimeError(f"D04D expected 5A00 return D05A, got {s.ip:04X}")

    s.bx = mem.rw(ds0, 0xBE06)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ax = s.bx
    s.bx = cpu.shift(4, s.bx, 1, 16)
    _add_reg16(cpu, 3, s.ax)
    s.si = mem.rw(ds0, (s.bx - 0x41E8) & 0xFFFF)
    s.si = cpu.shift(4, s.si, 1, 16)
    _add_reg16(cpu, 6, 0x0BE4)
    s.si = mem.rw(cs, s.si & 0xFFFF)

    saved_ds = s.ds & 0xFFFF
    cpu.push(saved_ds)
    s.ds = mem.rw(cs, 0x95B4)
    run_original_near_call(cpu, 0x5A6C, 0xD07C)
    if s.ip != 0xD07C:
        raise RuntimeError(f"D04D expected 5A6C return D07C, got {s.ip:04X}")
    s.ds = cpu.pop()
    ds = s.ds & 0xFFFF

    run_original_near_call(cpu, 0xA212, 0xD080)
    if s.ip != 0xD080:
        raise RuntimeError(f"D04D expected A212 return D080, got {s.ip:04X}")

    v_be06 = mem.rw(ds, 0xBE06)
    _cmp_word(cpu, v_be06, 0x0008)
    if v_be06 >= 0x0008:
        v_be08 = mem.rw(ds, 0xBE08)
        _cmp_word(cpu, v_be08, 0x0014)
        if v_be08 >= 0x0014:
            mem.wb(ds, 0x98BE, 0x00)
            _inc_mem_word_preserve_cf(cpu, ds, 0xBE0A)
            v_be0a = mem.rw(ds, 0xBE0A)
            _cmp_word(cpu, v_be0a, 0x0014)
            if v_be0a >= 0x0014:
                mem.ww(ds, 0xBE0A, 0x0000)
            v_be0a = mem.rw(ds, 0xBE0A)
            _cmp_word(cpu, v_be0a, 0x000F)
            if v_be0a == 0x000F:
                mem.wb(ds, 0x98BE, 0x10)
            else:
                _cmp_word(cpu, v_be0a, 0x0011)
                if v_be0a == 0x0011:
                    mem.wb(ds, 0x98BE, 0x10)
                else:
                    _cmp_word(cpu, v_be0a, 0x0013)
                    if v_be0a == 0x0013:
                        mem.wb(ds, 0x98BE, 0x10)
            s.bp = 0x237C
            mem.ww(ds, 0xA980, 0x0000)
            run_original_near_call(cpu, 0xA067, 0xD0CA)
            if s.ip != 0xD0CA:
                raise RuntimeError(f"D04D expected A067 return D0CA, got {s.ip:04X}")

    v_be06 = mem.rw(ds, 0xBE06)
    _cmp_word(cpu, v_be06, 0x0000)
    if v_be06 == 0:
        s.ip = 0xD160
        return

    dec = _dec_mem_word_preserve_cf(cpu, ds, 0xBE08)
    if dec != 0:
        s.ip = cpu.pop()
        return

    mem.ww(ds, 0xBE08, 0x0064)
    _inc_mem_word_preserve_cf(cpu, ds, 0xBE06)
    s.bx = mem.rw(ds, 0xBE06)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ax = s.bx
    s.bx = cpu.shift(4, s.bx, 1, 16)
    _add_reg16(cpu, 3, s.ax)
    s.ax = mem.rw(ds, (s.bx - 0x41E6) & 0xFFFF)
    _cmp_word(cpu, s.ax, 0xFFFF)
    if s.ax != 0xFFFF:
        mem.ww(ds, 0x95FA, s.ax)
        s.ax = mem.rw(ds, (s.bx - 0x41E4) & 0xFFFF)
        mem.ww(ds, 0xBE16, s.ax)
        run_original_near_call(cpu, 0x859E, 0xD107)
        if s.ip != 0xD107:
            raise RuntimeError(f"D04D expected 859E return D107, got {s.ip:04X}")

    s.bx = mem.rw(ds, 0xBE06)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ip = mem.rw(cs, (s.bx - 0x2EEE) & 0xFFFF)

def run_demo_object_list_maintenance_a212(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:A212, the scripted demo object-list maintenance helper.

    The common cold-start/attract path returns immediately while DS:A972 is
    zero.  The non-zero path maintains a small pointer list at A3B4 and uses
    A2D6 as a separate object-spawn helper; that spawn helper remains bounded
    original until its allocator island is lifted.
    """
    if self_disable_if_patched(
        cpu,
        0xA212,
        SIG_DEMO_OBJECT_LIST_MAINTENANCE_A212,
        "overkill_demo_object_list_maintenance_a212",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF

    v_a972 = mem.rw(ds, 0xA972)
    _cmp_word(cpu, v_a972, 0)
    if v_a972 == 0:
        s.ip = cpu.pop()
        return

    v2324 = mem.rw(ds, 0x2324)
    _cmp_word(cpu, v2324, 1)
    if v2324 == 1:
        v_a3ea = mem.rw(ds, 0xA3EA)
        _cmp_word(cpu, v_a3ea, 0xA3E8)
        if v_a3ea == 0xA3E8:
            s.ip = cpu.pop()
            return

        s.bx = mem.rw(ds, 0xA3B4)
        _cmp_word(cpu, s.bx, 0xFFFF)
        if s.bx == 0xFFFF:
            s.ip = cpu.pop()
            return

        first_y = mem.rw(ds, (s.bx + 0x04) & 0xFFFF)
        _cmp_word(cpu, first_y, 0)
        if first_y != 0:
            run_original_near_call(cpu, 0xA2D6, 0xA23D)
            s.bx = mem.rw(ds, 0xA3B4)
            _sub_mem_word(cpu, ds, (s.bx + 0x04) & 0xFFFF, 8)
            s.bx = mem.rw(ds, 0xA3EA)
            _sub_reg16(cpu, 3, 4)
            # SUB BX,4 flags are overwritten by the following CMP in observed code.
            s.bx = mem.rw(ds, s.bx)
            tail_y = mem.rw(ds, (s.bx + 0x04) & 0xFFFF)
            _cmp_word(cpu, tail_y, 0x00C8)
            if tail_y != 0x00C8:
                run_original_near_call(cpu, 0xA2D6, 0xA258)
        else:
            run_original_near_call(cpu, 0xA2D6, 0xA258)

    s.si = 0xA3B4
    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + 2) & 0xFFFF
    _cmp_word(cpu, s.ax, 0xFFFF)
    if s.ax == 0xFFFF:
        s.ip = cpu.pop()
        return

    s.bx = s.ax
    _sub_mem_word(cpu, ds, (s.bx + 0x02) & 0xFFFF, 4)
    s.cx = mem.rw(ds, (s.bx + 0x04) & 0xFFFF)
    _add_reg16(cpu, 1, 8)
    s.di = mem.rw(ds, (s.bx + 0x02) & 0xFFFF)

    while True:
        s.ax = mem.rw(ds, s.si)
        s.si = (s.si + 2) & 0xFFFF
        _cmp_word(cpu, s.ax, 0xFFFF)
        if s.ax == 0xFFFF:
            break
        s.bx = s.ax
        mem.ww(ds, (s.bx + 0x04) & 0xFFFF, s.cx)
        _add_reg16(cpu, 1, 8)
        mem.ww(ds, (s.bx + 0x02) & 0xFFFF, s.di)
        mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x006B)

    _sub_reg16(cpu, 6, 4)
    s.bx = mem.rw(ds, s.si)
    mem.ww(ds, (s.bx + 0x08) & 0xFFFF, 0x006C)
    s.ip = cpu.pop()
