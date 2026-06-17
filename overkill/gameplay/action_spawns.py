"""Recovered action-spawn frontier logic behind the frame controller.

This module is the emerging high-level gameplay layer for the raw A067 action
fanout family.  It still preserves original ASM-visible ordering at the public
CS:IP boundaries, but the code is separated from frame orchestration so the
project can grow a source-like gameplay model instead of one huge hook glue
module.

Naming rule: routine names remain structural until the evidence proves a
concrete gameplay entity.  For example, A067 is an action-spawn fanout, not yet
"player shooting".
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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

RunOriginalNearCall = Callable[[object, int, int], None]


@dataclass(frozen=True, slots=True)
class PairSpawnTailPlan:
    """Source-like description of the two-slot A2F6/A337 action tails."""

    entry_ip: int
    gate_addr: int
    beff_value: int
    slot_18: int
    slot_08: int
    first_ret: int
    second_ret: int
    first_a1ae_ret: int
    second_a1ae_ret: int
    name: str


PAIR_SPAWN_A2F6 = PairSpawnTailPlan(
    entry_ip=0xA2F6,
    gate_addr=0xA3A0,
    beff_value=0x17,
    slot_18=0x0008,
    slot_08=0x0035,
    first_ret=0xA311,
    second_ret=0xA325,
    first_a1ae_ret=0xA31E,
    second_a1ae_ret=0xA332,
    name="A2F6",
)
PAIR_SPAWN_A337 = PairSpawnTailPlan(
    entry_ip=0xA337,
    gate_addr=0xA3A0,
    beff_value=0x16,
    slot_18=0x0007,
    slot_08=0x0037,
    first_ret=0xA352,
    second_ret=0xA366,
    first_a1ae_ret=0xA35F,
    second_a1ae_ret=0xA373,
    name="A337",
)


@dataclass(frozen=True, slots=True)
class ActionCounterSnapshot:
    """A067's copied action counters before it calls the child spawn family."""

    pair_counter: int
    listed_counter: int
    dual_anchor_counter: int
    triple_anchor_counter: int


ACTION_COUNTER_SOURCE_TO_SCRATCH: tuple[tuple[int, int], ...] = (
    (0xA970, 0xA3A0),
    (0xA972, 0xA3A2),
    (0xA976, 0xA3A4),
    (0xA974, 0xA3A6),
)


def action_trigger_is_pressed(input_flags: int) -> bool:
    """Pure A067 trigger gate: bit 4 of DS:98BE is the action latch input."""

    return bool(input_flags & 0x10)


def action_latch_allows_repeat(*, latch_word: int, repeat_byte_9790: int, state_word_232a: int) -> bool:
    """Pure A067 repeat gate after the initial trigger bit is pressed."""

    return latch_word == 0 or repeat_byte_9790 == 0x01 or state_word_232a == 0x000F


def read_action_counter_snapshot(cpu, ds: int) -> ActionCounterSnapshot:
    """Project A067's raw action counters into a small source-like record."""

    mem = cpu.mem
    return ActionCounterSnapshot(
        pair_counter=mem.rw(ds, 0xA970),
        listed_counter=mem.rw(ds, 0xA972),
        dual_anchor_counter=mem.rw(ds, 0xA976),
        triple_anchor_counter=mem.rw(ds, 0xA974),
    )


def publish_action_counter_snapshot(cpu, ds: int, snapshot: ActionCounterSnapshot) -> None:
    """Mirror A067's A970/A972/A976/A974 -> A3A0/A3A2/A3A4/A3A6 copy."""

    mem = cpu.mem
    mem.ww(ds, 0xA3A0, snapshot.pair_counter)
    mem.ww(ds, 0xA3A2, snapshot.listed_counter)
    mem.ww(ds, 0xA3A4, snapshot.dual_anchor_counter)
    mem.ww(ds, 0xA3A6, snapshot.triple_anchor_counter)
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
    plan: PairSpawnTailPlan,
) -> None:
    """Shared body for the A2F6/A337 two-slot raw action tails."""
    gate_addr = plan.gate_addr
    beff_value = plan.beff_value
    slot_18 = plan.slot_18
    slot_08 = plan.slot_08
    first_ret = plan.first_ret
    second_ret = plan.second_ret
    first_a1ae_ret = plan.first_a1ae_ret
    second_a1ae_ret = plan.second_a1ae_ret
    caller_name = plan.name
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
        plan=PAIR_SPAWN_A2F6,
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
        plan=PAIR_SPAWN_A337,
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
    if not action_trigger_is_pressed(input_flags):
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
            if not action_latch_allows_repeat(
                latch_word=v_a980,
                repeat_byte_9790=v9790,
                state_word_232a=v232a,
            ):
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

    action_counters = read_action_counter_snapshot(cpu, ds)
    publish_action_counter_snapshot(cpu, ds, action_counters)
    s.ax = action_counters.triple_anchor_counter

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


