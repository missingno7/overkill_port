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

from overkill.asm import _add_reg16, _and_mem_word, _cmp_byte, _cmp_word, _dec_mem_word_preserve_cf, _inc_mem_word_preserve_cf, _sub_mem_word, _sub_reg16
from dos_re.cpu import ZF
from overkill.gameplay.starfield_bridge import advance_starfield_in_memory
from overkill.sounds.loaded_driver import OPTIONAL_SOUND_DRIVER_SEGMENT


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

    # Each input-bit TEST and the 2350 CMP below have dead flags: the CALL each
    # gates (or the next TEST/CALL) overwrites them before any hook boundary.
    input_flags = mem.rb(ds, 0x98BE)
    if input_flags & 0x08:
        call(0xA5D1, 0x9B79)

    input_flags = mem.rb(ds, 0x98BE)
    if input_flags & 0x04:
        call(0xA5EA, 0x9B83)

    input_flags = mem.rb(ds, 0x98BE)
    if input_flags & 0x01:
        call(0xA607, 0x9B8D)

    input_flags = mem.rb(ds, 0x98BE)
    if input_flags & 0x02:
        call(0xA5F9, 0x9B97)

    v2350 = mem.rw(ds, 0x2350)
    if v2350 > 0x00B6:
        input_flags = mem.rb(ds, 0x98BE)
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
        # ASM 9BCF `jne 9BDF` skips BOTH the 9CB6 call and the 9C01 camera-step
        # when [a47c] != 0, so the [2350] poll-gate and 9C01 must be nested under
        # the [a47c]==0 guard -- not run unconditionally.  Once the mothership
        # trigger (A66F) sets [a47c]=1 the vertical scroll locks; running 9C01
        # anyway advanced the camera anchor (DS:2380) one extra step.
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
    # BP += 0x0A: the ADD's flags are dead (the AH ADD below overwrites them).
    s.bp = (s.bp + 0x000A) & 0xFFFF
    s.ax = cpu.pop()
    old_ah = (s.ax >> 8) & 0xFF
    result_ah = old_ah + 0x10
    cpu.set_reg8(4, result_ah)
    cpu.set_add_flags(old_ah, 0x10, result_ah, 8)  # live: reaches the RET
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
    # 1F8F:0922 = the per-frame parallax starfield move (row=(row+1)%192, 3 layers at 2/4/8 cadence);
    # recovered VM-free via advance_starfield (was run-original).  See recovered/systems/starfield.py.
    advance_starfield_in_memory(cpu)
    s.cs, s.ip = cs, 0xD337
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
    s.bx = OPTIONAL_SOUND_DRIVER_SEGMENT
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
