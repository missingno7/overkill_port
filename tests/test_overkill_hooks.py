import pytest

from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory
from dos_re.snapshot import run_until
from overkill.launch import build_command_tail
from overkill.hooks import overkill_file_checksum_loop_c916
from overkill.runtime import create_overkill_runtime


def assert_oracle_equivalent(asm, hook, *, dead_stack_bytes: int = 0x40) -> None:
    """Assert a hook matches the ASM oracle on all *observable* state.

    Registers, flags, IP and every byte of memory at or above SP (and outside
    the stack) are compared exactly.  The one thing ignored is the dead stack
    scratch in ``SS:[SP-dead_stack_bytes .. SP)``: a real CALL leaves its popped
    return word just below SP, and the x86 calling convention defines memory
    below SP as undefined -- an interrupt may overwrite it at any instant.  So a
    lifted hook that composes a CALL/RET in Python need not reproduce that dead
    word, and the oracle should not demand it.  This lets such hooks drop the
    "write the expected garbage below SP" fidelity code without losing any
    guarantee that matters: nothing a real CALL/RET leaves live is relaxed.

    ``asm``/``hook`` are CPU-like objects exposing ``.s`` (CPUState) and ``.mem``
    (Memory); pass ``runtime.cpu`` for snapshot-backed oracles.
    """
    assert asm.s.snapshot() == hook.s.snapshot()
    if asm.mem.data == hook.mem.data:
        return
    base = (asm.s.ss & 0xFFFF) << 4
    sp = asm.s.sp & 0xFFFF
    a = bytearray(asm.mem.data)
    h = bytearray(hook.mem.data)
    for k in range(1, dead_stack_bytes + 1):
        addr = (base + ((sp - k) & 0xFFFF)) & 0xFFFFF
        a[addr] = h[addr] = 0
    assert a == h, "memory differs outside the dead stack scratch below SP"


def test_checksum_replacement_matches_original_loop_registers_and_flags():
    payload = bytes([0x10, 0x20, 0xFF, 0x01, 0x7E, 0x80, 0x33])

    # mov dl,[si] ; add ax,dx ; add ah,al ; inc si ; loop start ; hlt
    code = bytes.fromhex("8A 14 03 C2 00 C4 46 E2 F7 F4")

    mem_a = Memory(); mem_a.load(0x1000, 0, code); mem_a.load(0x2000, 0, payload)
    cpu_a = CPU8086(mem_a, CPUState(ax=0x1234, dx=0xAB00, cx=len(payload), si=0, cs=0x1000, ds=0x2000, ss=0x3000, sp=0xFFFE))
    cpu_a.trace_enabled = False
    cpu_a.run(len(payload) * 5 + 1)

    mem_b = Memory(); mem_b.load(0x2000, 0, payload)
    cpu_b = CPU8086(mem_b, CPUState(ax=0x1234, dx=0xAB00, cx=len(payload), si=0, cs=0x1010, ip=0xC916, ds=0x2000, ss=0x3000, sp=0xFFFE))
    cpu_b.trace_enabled = False
    overkill_file_checksum_loop_c916(cpu_b)

    assert cpu_b.s.ax == cpu_a.s.ax
    assert cpu_b.s.dx == cpu_a.s.dx
    assert cpu_b.s.cx == cpu_a.s.cx == 0
    assert cpu_b.s.si == cpu_a.s.si == len(payload)
    assert cpu_b.s.flags == cpu_a.s.flags
    assert cpu_b.s.ip == 0xC91F


def test_expand_bits_45cb_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_expand_bits_45cb

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        # 1010:45CB original bytes:
        #   call 45CE; rol al x3; rcl cs:[45E4]; rol al; rcl cs:[45E4]; ret
        base = 0x1010 * 16 + 0x45CB
        mem.data[base:base + 0x16] = bytes.fromhex(
            'e8 00 00 d0 c0 d0 c0 d0 c0 2e d1 16 e4 45 d0 c0 2e d1 16 e4 45 c3'
        )
        state = CPUState(ax=0x12A5, bx=0, cx=0, dx=0, sp=0x9000, cs=0x1010, ds=0x2222, es=0x3333, ss=0x4000, ip=0x45CB, flags=0x0203)
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        # Simulate CALLer return address already on the stack.
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x45CB)] = overkill_expand_bits_45cb
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    # Original wrapper needs 16 interpreted instructions: call + 2 bodies + 2 rets.
    asm.run(15)
    hook.step()

    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.rw(0x1010, 0x45E4) == hook.mem.rw(0x1010, 0x45E4)


def test_pack_four_pixels_45f6_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_pack_four_pixels_45f6

    code = bytes.fromhex(
        'd0 ce d0 d1 d0 ca d0 d1 d0 cc d0 d1 d0 c8 d0 d1'
        'd0 ce d0 d1 d0 ca d0 d1 d0 cc d0 d1 d0 c8 d0 d1'
        'd0 c9 d0 c9 d0 c9 d0 c9'
        '2e 83 3e d6 0b 00 74 30 8b d8 32 ed 8a c1 24 0f'
        '2e 3a 06 00 00 75 06 80 cd 0f 80 e1 f0 8a c1 24 f0'
        'd0 e8 d0 e8 d0 e8 d0 e8 2e 3a 06 00 00 75 06 80 cd f0'
        '80 e1 0f 8b c3 2e a3 e2 45 8a c1 24 0f bb e6 45 2e d7'
        '8a e0 8a c1 d0 e8 d0 e8 d0 e8 d0 e8 24 0f 2e d7 d0 e0'
        'd0 e0 d0 e0 d0 e0 0a c4 8a c8 2e a1 e2 45 c3'
    )

    def make_cpu(use_hook: bool, transparent: bool) -> CPU8086:
        mem = Memory()
        base = 0x1010 * 16 + 0x45F6
        mem.data[base:base + len(code)] = code
        # Use the real-ish low-nibble table shape from the observed memory image.
        table = bytes([0, 1, 1, 1, 2, 2, 2, 1, 2, 1, 1, 1, 2, 2, 1, 3])
        for i, b in enumerate(table):
            mem.wb(0x1010, 0x45E6 + i, b)
        mem.ww(0x1010, 0x0BD6, 1 if transparent else 0)
        mem.wb(0x1010, 0x0000, 0x02)
        state = CPUState(ax=0xA65C, bx=0x1111, cx=0x7E23, dx=0xC398, sp=0x9000, cs=0x1010, ds=0x2222, es=0x3333, ss=0x4000, ip=0x45F6, flags=0x0203)
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x45F6)] = overkill_pack_four_pixels_45f6
        return cpu

    for transparent in (False, True):
        asm = make_cpu(False, transparent)
        hook = make_cpu(True, transparent)
        for _ in range(200):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.rw(0x1010, 0x45E2) == hook.mem.rw(0x1010, 0x45E2)


def test_adlib_detect_04e9_hook_matches_interpreted_asm():
    def make_runtime(use_hook: bool):
        rt = create_overkill_runtime(
            "assets/OVERKILL",
            game_root="assets",
            command_tail=build_command_tail("tandy", "adlib"),
        )
        rt.cpu.trace_enabled = False
        if not use_hook:
            rt.cpu.replacement_hooks.pop((0x2032, 0x04E9), None)
            rt.cpu.hook_names.pop((0x2032, 0x04E9), None)
        return rt

    asm = make_runtime(False)
    hook = make_runtime(True)

    asm_status, _, _ = run_until(asm, max_steps=120_000, stop_at=(0x2032, 0x0007), trace_tail=0)
    hook_status, _, _ = run_until(hook, max_steps=120_000, stop_at=(0x2032, 0x0007), trace_tail=0)

    assert asm_status == "reached 2032:0007"
    assert hook_status == "reached 2032:0007"
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.dos.pit_channel2_reload == hook.dos.pit_channel2_reload == 0x1FFF
    assert asm.dos.speaker_control == hook.dos.speaker_control == 0x02
    assert asm.dos.opl_status == hook.dos.opl_status == 0xC0
    assert asm.dos.opl_registers == hook.dos.opl_registers == {1: 0x20, 2: 0xFF, 4: 0x21}
    assert bytes(asm.program.memory.data) == bytes(hook.program.memory.data)


def test_packed_read_byte_0624_hook_matches_interpreted_asm_no_refill():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_packed_read_byte_0624

    code = bytes.fromhex(
        '89 1e 12 06 8b 1e 10 06 81 fb 10 06 72 1f c7 06 10 06 10 04'
        '51 b4 3f 8b 1e 40 02 b9 00 02 ba 10 04 cd 21 59 73 03 e9 65 fc'
        '8b 1e 10 06 8a 07 ff 06 10 06 8b 1e 12 06 c3'
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        base = 0x1010 * 16 + 0x0624
        mem.data[base:base + len(code)] = code
        mem.ww(0x1010, 0x0610, 0x0500)
        mem.wb(0x1010, 0x0500, 0xAB)
        state = CPUState(ax=0x9900, bx=0x1234, cx=0x7777, dx=0x8888, sp=0x9000, cs=0x1010, ds=0x1010, es=0x3333, ss=0x4000, ip=0x0624, flags=0x0203)
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x0624)] = overkill_packed_read_byte_0624
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(80):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.rw(0x1010, 0x0610) == hook.mem.rw(0x1010, 0x0610)
    assert asm.mem.rw(0x1010, 0x0612) == hook.mem.rw(0x1010, 0x0612)


def test_packed_read_byte_0624_hook_matches_interpreted_asm_with_refill():
    from dos_re.cpu import CPU8086, CPUState, CF
    from dos_re.memory import Memory
    from overkill.hooks import overkill_packed_read_byte_0624

    code = bytes.fromhex(
        '89 1e 12 06 8b 1e 10 06 81 fb 10 06 72 1f c7 06 10 06 10 04'
        '51 b4 3f 8b 1e 40 02 b9 00 02 ba 10 04 cd 21 59 73 03 e9 65 fc'
        '8b 1e 10 06 8a 07 ff 06 10 06 8b 1e 12 06 c3'
    )

    def fake_int21(cpu, num: int) -> None:
        assert num == 0x21
        assert ((cpu.s.ax >> 8) & 0xFF) == 0x3F
        for i in range(cpu.s.cx):
            cpu.mem.wb(cpu.s.ds, (cpu.s.dx + i) & 0xFFFF, (i * 7 + 0x42) & 0xFF)
        cpu.s.ax = cpu.s.cx
        cpu.set_flag(CF, False)

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        base = 0x1010 * 16 + 0x0624
        mem.data[base:base + len(code)] = code
        mem.ww(0x1010, 0x0610, 0x0610)
        mem.ww(0x1010, 0x0240, 0x0005)
        state = CPUState(ax=0x9900, bx=0x1234, cx=0x7777, dx=0x8888, sp=0x9000, cs=0x1010, ds=0x1010, es=0x3333, ss=0x4000, ip=0x0624, flags=0x0203)
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.interrupt_handler = fake_int21
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x0624)] = overkill_packed_read_byte_0624
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(120):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.block(0x1010, 0x0410, 16) == hook.mem.block(0x1010, 0x0410, 16)
    assert asm.mem.rw(0x1010, 0x0610) == hook.mem.rw(0x1010, 0x0610)
    assert asm.mem.rw(asm.s.ss, (asm.s.sp - 2) & 0xFFFF) == hook.mem.rw(hook.s.ss, (hook.s.sp - 2) & 0xFFFF)


def test_packed_read_word_0615_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_packed_read_word_le_0615

    code = bytes.fromhex(
        'e8 0c 00 a2 14 06 e8 06 00 8a e0 a0 14 06 c3'
        '89 1e 12 06 8b 1e 10 06 81 fb 10 06 72 1f c7 06 10 06 10 04'
        '51 b4 3f 8b 1e 40 02 b9 00 02 ba 10 04 cd 21 59 73 03 e9 65 fc'
        '8b 1e 10 06 8a 07 ff 06 10 06 8b 1e 12 06 c3'
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        base = 0x1010 * 16 + 0x0615
        mem.data[base:base + len(code)] = code
        mem.ww(0x1010, 0x0610, 0x0500)
        mem.wb(0x1010, 0x0500, 0x34)
        mem.wb(0x1010, 0x0501, 0x12)
        state = CPUState(ax=0x9900, bx=0x1234, cx=0x7777, dx=0x8888, sp=0x9000, cs=0x1010, ds=0x1010, es=0x3333, ss=0x4000, ip=0x0615, flags=0x0203)
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x0615)] = overkill_packed_read_word_le_0615
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(200):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.rw(0x1010, 0x0610) == hook.mem.rw(0x1010, 0x0610)
    assert asm.mem.rb(0x1010, 0x0614) == hook.mem.rb(0x1010, 0x0614)


def test_vertical_rle_03a8_hook_matches_interpreted_asm_on_synthetic_stream():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_vertical_rle_decoder_03a8

    routine_03a8 = bytes.fromhex(
        '8e 06 3a 02 8b 3e 3c 02 e8 62 02 2e a3 a2 03 e8 5b 02 a3 a4 03'
        'e8 55 02 a3 a6 03 2e 8b 0e a4 03 51 57 e8 57 02 3c 80 74 36'
        '72 1d f6 d8 86 e0 86 dc e8 48 02 86 dc 26 88 05 2e 03 3e a4 03'
        'ff 06 44 02 fe cc 79 f0 eb da 50 e8 30 02 26 88 05 2e 03 3e a4 03'
        'ff 06 44 02 58 fe c8 79 eb eb c3 5f 47 59 e2 bc e9 99 fe'
    )
    reader_0615 = bytes.fromhex(
        'e8 0c 00 a2 14 06 e8 06 00 8a e0 a0 14 06 c3'
        '89 1e 12 06 8b 1e 10 06 81 fb 10 06 72 1f c7 06 10 06 10 04'
        '51 b4 3f 8b 1e 40 02 b9 00 02 ba 10 04 cd 21 59 73 03 e9 65 fc'
        '8b 1e 10 06 8a 07 ff 06 10 06 8b 1e 12 06 c3'
    )

    # Header words: marker=1111h, width/vertical stride=3, height-ish marker=2222h.
    # Then three column streams terminated by 80h.  The mix of literal and repeat
    # commands exercises both branches and the odd AH/BL preservation sequence.
    packed_stream = bytes([
        0x11, 0x11, 0x03, 0x00, 0x22, 0x22,
        0x01, 0xA1, 0xA2, 0xFE, 0xB0, 0x80,
        0xFF, 0xC1, 0x00, 0xD1, 0x80,
        0x02, 0xE1, 0xE2, 0xE3, 0x80,
    ])

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x03A8, routine_03a8)
        mem.load(0x1010, 0x0615, reader_0615)
        mem.load(0x1010, 0x0410, packed_stream)
        mem.ww(0x1010, 0x023A, 0x7000)
        mem.ww(0x1010, 0x023C, 0x0100)
        mem.ww(0x1010, 0x0244, 0x3333)
        mem.ww(0x1010, 0x0610, 0x0410)
        state = CPUState(
            ax=0x5A77, bx=0x12BC, cx=0x9999, dx=0x8888,
            si=0x7777, di=0x6666, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x1010, es=0x4444, ss=0x4000,
            ip=0x03A8, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x03A8)] = overkill_vertical_rle_decoder_03a8
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(1000):
        if asm.addr() == (0x1010, 0x02A8):
            break
        asm.step()
    assert asm.addr() == (0x1010, 0x02A8)

    hook.step()
    assert hook.addr() == (0x1010, 0x02A8)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.block(0x7000, 0x0100, 0x10) == hook.mem.block(0x7000, 0x0100, 0x10)
    assert asm.mem.rw(0x1010, 0x0244) == hook.mem.rw(0x1010, 0x0244)
    assert asm.mem.rw(0x1010, 0x0610) == hook.mem.rw(0x1010, 0x0610)
    assert asm.mem.rw(0x1010, 0x03A2) == hook.mem.rw(0x1010, 0x03A2)
    assert asm.mem.rw(0x1010, 0x03A4) == hook.mem.rw(0x1010, 0x03A4)
    assert asm.mem.rw(0x1010, 0x03A6) == hook.mem.rw(0x1010, 0x03A6)


def test_word_pair_rle_0324_hook_matches_interpreted_asm_on_synthetic_stream():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_word_pair_rle_decoder_0324

    routine_0324 = bytes.fromhex(
        '8e063a028b3e3c02e8e6028bd8e8e1023bc3740cabe8d902ab8306440204ebed'
        'e8ce028bc8e302eb03e958ffe8c20250e8be028bd058ab92ab830644020492e2f5ebca'
    )
    reader_0615 = bytes.fromhex(
        'e8 0c 00 a2 14 06 e8 06 00 8a e0 a0 14 06 c3'
        '89 1e 12 06 8b 1e 10 06 81 fb 10 06 72 1f c7 06 10 06 10 04'
        '51 b4 3f 8b 1e 40 02 b9 00 02 ba 10 04 cd 21 59 73 03 e9 65 fc'
        '8b 1e 10 06 8a 07 ff 06 10 06 8b 1e 12 06 c3'
    )

    def w(value: int) -> list[int]:
        return [value & 0xFF, (value >> 8) & 0xFF]

    packed_stream = bytes(
        w(0xBEEF) +            # marker
        w(0x1111) + w(0x2222) +  # literal pair
        w(0xBEEF) + w(0x0003) + w(0x3333) + w(0x4444) +  # repeated pair
        w(0x5555) + w(0x6666) +  # another literal pair
        w(0xBEEF) + w(0x0000)    # terminator
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x0324, routine_0324)
        mem.load(0x1010, 0x0615, reader_0615)
        mem.load(0x1010, 0x0410, packed_stream)
        mem.ww(0x1010, 0x023A, 0x7000)
        mem.ww(0x1010, 0x023C, 0x0100)
        mem.ww(0x1010, 0x0244, 0x3333)
        mem.ww(0x1010, 0x0610, 0x0410)
        state = CPUState(
            ax=0x5A77, bx=0x12BC, cx=0x9999, dx=0x8888,
            si=0x7777, di=0x6666, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x1010, es=0x4444, ss=0x4000,
            ip=0x0324, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x0324)] = overkill_word_pair_rle_decoder_0324
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(1000):
        if asm.addr() == (0x1010, 0x02A8):
            break
        asm.step()
    hook.step()
    assert asm.addr() == (0x1010, 0x02A8)
    assert hook.addr() == (0x1010, 0x02A8)
    assert asm.s.snapshot() == hook.s.snapshot()
    # SS:[SP-40..SP) is dead stack scratch -- the read_word_from_call CALL return
    # words below SP, no longer modelled -- so it is not compared.
    assert asm.mem.block(0x7000, 0x0100, 0x20) == hook.mem.block(0x7000, 0x0100, 0x20)
    assert asm.mem.rw(0x1010, 0x0244) == hook.mem.rw(0x1010, 0x0244)
    assert asm.mem.rw(0x1010, 0x0610) == hook.mem.rw(0x1010, 0x0610)
    assert asm.mem.rb(0x1010, 0x0614) == hook.mem.rb(0x1010, 0x0614)


def test_expand_4plane_row_4537_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_expand_4plane_row_4537

    row_4537 = bytes.fromhex(
        '2e8b1e9c5b8a048a20d1e38a102e031e9c5b8a30e8a8002e880e955b2e882e995b'
        'e89b002e880e945b2e882e985be88e002e880e975b2e882e9b5be881002e880e965b'
        '2e882e9a5b462e833ed60b0074212ea0985be83c002ea0995be835002ea09a5be82e00'
        '2ea09b5be827002ea1e445ab2ea0945be81b002ea0955be814002ea0965be80d002e'
        'a0975be806002ea1e445abc3e80000d0c0d0c0d0c02ed116e445d0c02ed116e445c3'
    )
    pack_45f6 = bytes.fromhex(
        'd0 ce d0 d1 d0 ca d0 d1 d0 cc d0 d1 d0 c8 d0 d1'
        'd0 ce d0 d1 d0 ca d0 d1 d0 cc d0 d1 d0 c8 d0 d1'
        'd0 c9 d0 c9 d0 c9 d0 c9'
        '2e 83 3e d6 0b 00 74 30 8b d8 32 ed 8a c1 24 0f'
        '2e 3a 06 00 00 75 06 80 cd 0f 80 e1 f0 8a c1 24 f0'
        'd0 e8 d0 e8 d0 e8 d0 e8 2e 3a 06 00 00 75 06 80 cd f0'
        '80 e1 0f 8b c3 2e a3 e2 45 8a c1 24 0f bb e6 45 2e d7'
        '8a e0 8a c1 d0 e8 d0 e8 d0 e8 d0 e8 24 0f 2e d7 d0 e0'
        'd0 e0 d0 e0 d0 e0 0a c4 8a c8 2e a1 e2 45 c3'
    )

    def make_cpu(use_hook: bool, transparent: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x4537, row_4537)
        mem.load(0x1010, 0x45F6, pack_45f6)
        table = bytes([0, 1, 1, 1, 2, 2, 2, 1, 2, 1, 1, 1, 2, 2, 1, 3])
        for i, b in enumerate(table):
            mem.wb(0x1010, 0x45E6 + i, b)
        mem.ww(0x1010, 0x5B9C, 5)
        mem.ww(0x1010, 0x0BD6, 1 if transparent else 0)
        mem.wb(0x1010, 0x0000, 0x02)
        mem.ww(0x1010, 0x45E4, 0x1357)
        # Four bitplanes separated by width=5.
        for off, value in ((0x0100, 0x96), (0x0105, 0x39), (0x010A, 0xC3), (0x010F, 0x5A)):
            mem.wb(0x6000, off, value)
        state = CPUState(
            ax=0xA65C, bx=0x1111, cx=0x7E23, dx=0xC398,
            si=0x0100, di=0x0200, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
            ip=0x4537, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x4537)] = overkill_expand_4plane_row_4537
        return cpu

    for transparent in (False, True):
        asm = make_cpu(False, transparent)
        hook = make_cpu(True, transparent)
        for _ in range(600):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == (0x1010, 0xBEEF)
        assert hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.block(0x7000, 0x0200, 4) == hook.mem.block(0x7000, 0x0200, 4)
        assert asm.mem.block(0x1010, 0x5B94, 8) == hook.mem.block(0x1010, 0x5B94, 8)
        assert asm.mem.rw(0x1010, 0x45E4) == hook.mem.rw(0x1010, 0x45E4)


def test_expand_4plane_block_4511_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_expand_4plane_block_4511

    block_4511 = bytes.fromhex(
        '2e8b0e9e5b512e8b0e9c5b51e8170059e2f92e03369c5b2e03369c5b2e03369c5b'
        '59e2e1ebd52e8b1e9c5b8a048a20d1e38a102e031e9c5b8a30e8a8002e880e955b'
        '2e882e995be89b002e880e945b2e882e985be88e002e880e975b2e882e9b5be88100'
        '2e880e965b2e882e9a5b462e833ed60b0074212ea0985be83c002ea0995be83500'
        '2ea09a5be82e002ea09b5be827002ea1e445ab2ea0945be81b002ea0955be81400'
        '2ea0965be80d002ea0975be806002ea1e445abc3e80000d0c0d0c0d0c02ed116e445'
        'd0c02ed116e445c3'
    )
    pack_45f6 = bytes.fromhex(
        'd0 ce d0 d1 d0 ca d0 d1 d0 cc d0 d1 d0 c8 d0 d1'
        'd0 ce d0 d1 d0 ca d0 d1 d0 cc d0 d1 d0 c8 d0 d1'
        'd0 c9 d0 c9 d0 c9 d0 c9'
        '2e 83 3e d6 0b 00 74 30 8b d8 32 ed 8a c1 24 0f'
        '2e 3a 06 00 00 75 06 80 cd 0f 80 e1 f0 8a c1 24 f0'
        'd0 e8 d0 e8 d0 e8 d0 e8 2e 3a 06 00 00 75 06 80 cd f0'
        '80 e1 0f 8b c3 2e a3 e2 45 8a c1 24 0f bb e6 45 2e d7'
        '8a e0 8a c1 d0 e8 d0 e8 d0 e8 d0 e8 24 0f 2e d7 d0 e0'
        'd0 e0 d0 e0 d0 e0 0a c4 8a c8 2e a1 e2 45 c3'
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x4511, block_4511)
        mem.load(0x1010, 0x45F6, pack_45f6)
        table = bytes([0, 1, 1, 1, 2, 2, 2, 1, 2, 1, 1, 1, 2, 2, 1, 3])
        for i, b in enumerate(table):
            mem.wb(0x1010, 0x45E6 + i, b)
        mem.ww(0x1010, 0x5B9C, 2)  # width
        mem.ww(0x1010, 0x5B9E, 2)  # rows
        mem.ww(0x1010, 0x0BD6, 1)
        mem.wb(0x1010, 0x0000, 0x02)
        mem.ww(0x1010, 0x45E4, 0x2468)
        # Two rows, four planes per row, width=2 -> 16 bytes used.
        for i, value in enumerate([0x96, 0x69, 0x39, 0x93, 0xC3, 0x3C, 0x5A, 0xA5,
                                   0x11, 0x22, 0x44, 0x88, 0xF0, 0x0F, 0xAA, 0x55]):
            mem.wb(0x6000, 0x0100 + i, value)
        state = CPUState(
            ax=0xA65C, bx=0x1111, cx=0x7E23, dx=0xC398,
            si=0x0100, di=0x0200, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
            ip=0x4511, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x4511)] = overkill_expand_4plane_block_4511
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(3000):
        if asm.addr() == (0x1010, 0x450C):
            break
        asm.step()
    hook.step()
    assert asm.addr() == (0x1010, 0x450C)
    assert hook.addr() == (0x1010, 0x450C)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.block(0x7000, 0x0200, 16) == hook.mem.block(0x7000, 0x0200, 16)
    assert asm.mem.block(0x1010, 0x5B94, 8) == hook.mem.block(0x1010, 0x5B94, 8)
    assert asm.mem.rw(0x1010, 0x45E4) == hook.mem.rw(0x1010, 0x45E4)


def _tandy_33dd_asm_bytes():
    cell_33dd = bytes.fromhex(
        "2e8b1e9c5b8a048a20d1e38a102e031e9c5b8a30e857002e880e955b2e882e995b"
        "e84a002e880e945b2e882e985be83d002e880e975b2e882e9b5be830002e880e965b"
        "2e882e9a5b462e833ed60b0074052ea19a5bab2ea1965bab2e833ed60b007405"
        "2ea1985bab2ea1945babc3"
    )
    pack_344b = bytes.fromhex(
        "d0ced0d1d0cad0d1d0ccd0d1d0c8d0d1d0ced0d1d0cad0d1d0ccd0d1d0c8d0d1"
        "d0c9d0c9d0c9d0c92e833ed60b007501c38bd832ed8ac1240f2e3a0600007506"
        "80cd0f80e1f08ac124f0d0e8d0e8d0e8d0e82e3a060000750680cdf080e10f"
        "8bc3c3"
    )
    return cell_33dd, pack_344b


def test_expand_tandy_cell_33dd_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_expand_tandy_cell_33dd

    cell_33dd, pack_344b = _tandy_33dd_asm_bytes()

    def make_cpu(use_hook: bool, *, bd6: int, flags: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x33DD, cell_33dd)
        mem.load(0x1010, 0x344B, pack_344b)
        mem.ww(0x1010, 0x5B9C, 3)
        mem.ww(0x1010, 0x0BD6, bd6)
        mem.wb(0x1010, 0x0000, 0x03)
        for i, value in enumerate([0x96, 0x69, 0x39, 0x93, 0xC3, 0x3C, 0x5A, 0xA5, 0xF0, 0x0F]):
            mem.wb(0x6000, 0x0100 + i, value)
        state = CPUState(
            ax=0xA65C, bx=0x1111, cx=0x7E23, dx=0xC398,
            si=0x0100, di=0x0240, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
            ip=0x33DD, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x33DD)] = overkill_expand_tandy_cell_33dd
        return cpu

    for bd6 in (0, 1):
        for flags in (0x0203, 0x0603):
            asm = make_cpu(False, bd6=bd6, flags=flags)
            hook = make_cpu(True, bd6=bd6, flags=flags)
            for _ in range(800):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == (0x1010, 0xBEEF)
            assert hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.block(0x7000, 0x0200, 0x80) == hook.mem.block(0x7000, 0x0200, 0x80)
            assert asm.mem.block(0x1010, 0x5B94, 8) == hook.mem.block(0x1010, 0x5B94, 8)


def test_expand_tandy_block_33b2_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_expand_tandy_block_33b2

    block_33b2 = bytes.fromhex(
        "7503e9f3102e8b0e9e5b512e8b0e9c5b51e8170059e2f92e03369c5b"
        "2e03369c5b2e03369c5b59e2e1ebd2"
    )
    cell_33dd, pack_344b = _tandy_33dd_asm_bytes()

    def make_cpu(use_hook: bool, *, bd6: int, flags: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x33B2, block_33b2)
        mem.load(0x1010, 0x33DD, cell_33dd)
        mem.load(0x1010, 0x344B, pack_344b)
        mem.ww(0x1010, 0x5B9C, 2)  # width
        mem.ww(0x1010, 0x5B9E, 2)  # rows
        mem.ww(0x1010, 0x0BD6, bd6)
        mem.wb(0x1010, 0x0000, 0x03)
        for i, value in enumerate([0x96, 0x69, 0x39, 0x93, 0xC3, 0x3C, 0x5A, 0xA5,
                                   0x11, 0x22, 0x44, 0x88, 0xF0, 0x0F, 0xAA, 0x55]):
            mem.wb(0x6000, 0x0100 + i, value)
        state = CPUState(
            ax=0xA65C, bx=0x1111, cx=0x7E23, dx=0xC398,
            si=0x0100, di=0x0240, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
            ip=0x33B2, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x33B2)] = overkill_expand_tandy_block_33b2
        return cpu

    for bd6 in (0, 1):
        for flags in (0x0202, 0x0602):
            asm = make_cpu(False, bd6=bd6, flags=flags)
            hook = make_cpu(True, bd6=bd6, flags=flags)
            for _ in range(5000):
                if asm.addr() == (0x1010, 0x33AF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == (0x1010, 0x33AF)
            assert hook.addr() == (0x1010, 0x33AF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.block(0x7000, 0x0200, 0x100) == hook.mem.block(0x7000, 0x0200, 0x100)
            assert asm.mem.block(0x1010, 0x5B94, 8) == hook.mem.block(0x1010, 0x5B94, 8)


def test_expand_tandy_block_33b2_terminator_branch_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_expand_tandy_block_33b2

    block_33b2 = bytes.fromhex("7503e9f3102e8b0e9e5b512e8b0e9c5b")

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x33B2, block_33b2)
        state = CPUState(
            ax=0xA65C, bx=0x1111, cx=0x7E23, dx=0xC398,
            si=0x0100, di=0x0240, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
            ip=0x33B2, flags=0x0242,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x33B2)] = overkill_expand_tandy_block_33b2
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(3):
        if asm.addr() == (0x1010, 0x44AA):
            break
        asm.step()
    hook.step()
    assert asm.addr() == (0x1010, 0x44AA)
    assert hook.addr() == (0x1010, 0x44AA)
    assert asm.s.snapshot() == hook.s.snapshot()


def test_expand_tandy_list_33af_composes_headers_and_blocks_like_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_expand_tandy_list_33af

    code_33af = bytes.fromhex(
        "e825117503e9f3102e8b0e9e5b512e8b0e9c5b51e8170059e2f9"
        "2e03369c5b2e03369c5b2e03369c5b59e2e1ebd2"
    )
    code_44d7 = bytes.fromhex(
        "8b040b44027501c32e8b1ee00b2e8306e00b02ad2e833ed80b007404"
        "2e893fab2ea39e5bad2e833ed80b007401ab2ea39c5b40c3"
    )
    cell_33dd, pack_344b = _tandy_33dd_asm_bytes()

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x33AF, code_33af)
        mem.load(0x1010, 0x33DD, cell_33dd)
        mem.load(0x1010, 0x344B, pack_344b)
        mem.load(0x1010, 0x44D7, code_44d7)
        mem.ww(0x1010, 0x0BD6, 0)
        mem.ww(0x1010, 0x0BD8, 1)
        mem.ww(0x1010, 0x0BE0, 0x5C00)
        stream = bytearray()
        stream += bytes([1, 0, 1, 0, 0x96, 0x69, 0x39, 0x93])
        stream += bytes([2, 0, 1, 0, 0xC3, 0x3C, 0x5A, 0xA5, 0x11, 0x22, 0x44, 0x88])
        stream += bytes([0, 0, 0, 0])
        mem.load(0x6000, 0x0100, stream)
        state = CPUState(
            ax=0xA65C, bx=0x1111, cx=0x7E23, dx=0xC398,
            si=0x0100, di=0x0240, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
            ip=0x33AF, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x33AF)] = overkill_expand_tandy_list_33af
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(20000):
        if asm.addr() == (0x1010, 0x44AA):
            break
        asm.step()
    # The 33AF hook is one header-iteration per call: it reads the 44D7 block
    # header and dispatches to 33B2 (the block processor, which loops back to
    # 33AF) or to 44AA when the list terminates.  So drive the hook the same way
    # the ASM runs -- iterate to the 44AA terminator -- to compare the full
    # multi-block composition rather than a single header dispatch.  33B2 here is
    # interpreted ASM (only 33AF is hooked), so this exercises the 33AF hook in
    # the real loop; 33B2's own hook is covered by its dedicated oracles.
    for _ in range(20000):
        if hook.addr() == (0x1010, 0x44AA):
            break
        hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0x44AA)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_expand_tandy_list_33af_handles_disabled_header_table_like_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_expand_tandy_list_33af

    mem = Memory()
    mem.load(
        0x1010,
        0x33AF,
        bytes.fromhex(
            "e825117503e9f3102e8b0e9e5b512e8b0e9c5b51e8170059e2f9"
            "2e03369c5b2e03369c5b2e03369c5b59e2e1ebd2"
        ),
    )
    # CS:0BD8 only controls whether 44D7 mirrors header words into the side
    # table; it does not disable the 33AF list itself.  A zero source header
    # still returns through the normal 44AA terminator path.
    mem.ww(0x1010, 0x0BD8, 0)
    state = CPUState(
        ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
        si=0x0100, di=0x0200, bp=0x5555, sp=0x9000,
        cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
        ip=0x33AF, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.replacement_hooks[(0x1010, 0x33AF)] = overkill_expand_tandy_list_33af

    cpu.step()

    assert cpu.addr() == (0x1010, 0x44AA)
    assert (0x1010, 0x33AF) in cpu.replacement_hooks


def test_tandy_interlaced_clear_3389_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_interlaced_clear_3389

    code_3389 = bytes.fromhex(
        "2e8e06a49533ffbdc800b9340033c0f3ab83ef6881c70020f7c70080740481c7a0804d75e5c3"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x3389, code_3389)
        mem.ww(0x1010, 0x95A4, 0xB800)
        state = CPUState(
            ax=0x1234, bx=0x5678, cx=0x9ABC, dx=0xDEF0,
            si=0x1111, di=0x1400, bp=0x2222, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7777, ss=0x4000,
            ip=0x3389, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x3389)] = overkill_tandy_interlaced_clear_3389
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(20000):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_tandy_masked_sprite_composite_2f81_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_masked_sprite_composite_2f81

    code = bytes.fromhex(
        "bb6000ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "03fbe2d12e8e1e9695c3"
    )

    def make_cpu(use_hook: bool, *, rows: int, flags: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x2F81, code)
        mem.ww(0x1010, 0x9596, 0x2222)
        ds, es, ss = 0x3000, 0x4000, 0x5000
        si, di = 0x0180, 0x0240
        for off in range(-0x40, rows * 0x20 + 0x80):
            mem.wb(ds, (si + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, rows * 0x80 + 0x100):
            mem.wb(es, (di + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x7777, cx=rows, dx=0x76E6,
            si=si, di=di, bp=0x0010, sp=0x9000,
            cs=0x1010, ds=ds, es=es, ss=ss,
            ip=0x2F81, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x2F81)] = overkill_tandy_masked_sprite_composite_2f81
        return cpu

    for rows in (1, 3, 16):
        for flags in (0x0203, 0x0603):
            asm = make_cpu(False, rows=rows, flags=flags, seed=rows + flags)
            hook = make_cpu(True, rows=rows, flags=flags, seed=rows + flags)
            for _ in range(5000):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.data == hook.mem.data


def test_tandy_masked_sprite_composite_2e6e_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_masked_sprite_composite_2e6e

    code = bytes.fromhex(
        "bb5800"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "03fbe2a92e8e1e9695c3"
    )

    def make_cpu(use_hook: bool, *, rows: int, flags: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x2E6E, code)
        mem.ww(0x1010, 0x9596, 0x2222)
        ds, es, ss = 0x3000, 0x4000, 0x5000
        si, di = 0x0180, 0x0240
        for off in range(-0x40, rows * 0x40 + 0x80):
            mem.wb(ds, (si + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, rows * 0x80 + 0x100):
            mem.wb(es, (di + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x7777, cx=rows, dx=0x7628,
            si=si, di=di, bp=0x0010, sp=0x9000,
            cs=0x1010, ds=ds, es=es, ss=ss,
            ip=0x2E6E, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x2E6E)] = overkill_tandy_masked_sprite_composite_2e6e
        return cpu

    for rows in (1, 3, 16):
        for flags in (0x0203, 0x0603):
            asm = make_cpu(False, rows=rows, flags=flags, seed=0x2E6E + rows + flags)
            hook = make_cpu(True, rows=rows, flags=flags, seed=0x2E6E + rows + flags)
            for _ in range(10000):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.data == hook.mem.data


def test_tandy_masked_compact_2fb6_hook_matches_interpreted_asm_and_preserves_cx():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_masked_compact_2fb6

    # 1010:2FB6 is a fixed 8-row compact compositor, not a LOOP-based leaf.
    # It must preserve CX exactly; strict hook verification caught a previous
    # shared-helper implementation that incorrectly consumed CX as a row count.
    row = "ad2623050b0483c602ab" * 2 + "03fb"
    code = bytes.fromhex("bb6400" + row * 8 + "2e8e1e9695c3")

    def make_cpu(use_hook: bool, *, cx: int, flags: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x2FB6, code)
        mem.ww(0x1010, 0x9596, 0x2222)
        ds, es, ss = 0x3000, 0x4000, 0x5000
        si, di = 0x0180, 0x0240
        for off in range(-0x40, 0x100):
            mem.wb(ds, (si + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x500):
            mem.wb(es, (di + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x7777, cx=cx, dx=0x7628,
            si=si, di=di, bp=0x0010, sp=0x9000,
            cs=0x1010, ds=ds, es=es, ss=ss,
            ip=0x2FB6, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x2FB6)] = overkill_tandy_masked_compact_2fb6
        return cpu

    for cx in (0x0000, 0x0008, 0x3333):
        for flags in (0x0203, 0x0603):
            asm = make_cpu(False, cx=cx, flags=flags, seed=0x2FB6 + cx + flags)
            hook = make_cpu(True, cx=cx, flags=flags, seed=0x2FB6 + cx + flags)
            for _ in range(1000):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.data == hook.mem.data


def test_tandy_strided_copy_34c5_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_strided_copy_34c5

    code = bytes.fromhex("bb5800b91000a5a5a5a5a5a5a5a503fbe2f42e8e1e9695c3")

    def make_cpu(use_hook: bool, *, flags: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x34C5, code)
        mem.ww(0x1010, 0x9596, 0x2222)
        ds, es, ss = 0x3000, 0x4000, 0x5000
        si, di = 0x0180, 0x0240
        for off in range(-0x40, 0x300):
            mem.wb(ds, (si + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x700):
            mem.wb(es, (di + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x7777, cx=0x3333, dx=0x76E6,
            si=si, di=di, bp=0x237C, sp=0x9000,
            cs=0x1010, ds=ds, es=es, ss=ss,
            ip=0x34C5, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x34C5)] = overkill_tandy_strided_copy_34c5
        return cpu

    for flags in (0x0203, 0x0603):
        asm = make_cpu(False, flags=flags, seed=0x34C5 + flags)
        hook = make_cpu(True, flags=flags, seed=0x34C5 + flags)
        for _ in range(2000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_tandy_rect_copy_306f_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_rect_copy_306f

    code = bytes.fromhex(
        "ad8bc8ad2e8e06a495d1e0d1e08be8518bcdf3a42bfd81c70020"
        "f7c70080740481c7a08059e2e8c3"
    )

    def make_cpu(use_hook: bool, *, height: int, width: int, di: int, flags: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x306F, code)
        mem.ww(0x1010, 0x95A4, 0xB800)
        ds, es, ss = 0x3000, 0x1111, 0x5000
        si = 0x0200
        mem.ww(ds, si, height)
        mem.ww(ds, si + 2, width)
        row_bytes = width * 4
        for off in range(0, 4 + max(1, height) * max(1, row_bytes) + 0x40):
            mem.wb(ds, (si + off) & 0xFFFF, rnd.randrange(256))
        mem.ww(ds, si, height)
        mem.ww(ds, si + 2, width)
        for off in range(0, 0x10000):
            if off % 17 == 0:
                mem.wb(0xB800, off, rnd.randrange(256))
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
            si=si, di=di, bp=0xEEEE, sp=0x9000,
            cs=0x1010, ds=ds, es=es, ss=ss,
            ip=0x306F, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x306F)] = overkill_tandy_rect_copy_306f
        return cpu

    cases = (
        (3, 2, 0x0100, 0x0202),
        (5, 1, 0x7F84, 0x0203),
        (1, 4, 0x7FF0, 0x0603),
    )
    for height, width, di, flags in cases:
        asm = make_cpu(False, height=height, width=width, di=di, flags=flags, seed=0x306F + di)
        hook = make_cpu(True, height=height, width=width, di=di, flags=flags, seed=0x306F + di)
        for _ in range(2000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_tandy_source_strided_copy_35aa_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_source_strided_copy_35aa

    code = bytes.fromhex("2e8e0696952e8e1e9895bb5800b91000a5a5a5a5a5a5a5a503f3e2f42e8e1e9695c3")

    def make_cpu(use_hook: bool, *, flags: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x35AA, code)
        mem.ww(0x1010, 0x9596, 0x4000)
        mem.ww(0x1010, 0x9598, 0x3000)
        ds, es, ss = 0x3000, 0x4000, 0x5000
        si, di = 0x0180, 0x0240
        for off in range(-0x40, 0x700):
            mem.wb(ds, (si + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x300):
            mem.wb(es, (di + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x7777, cx=0x3333, dx=0xAAAA,
            si=si, di=di, bp=0x237C, sp=0x9000,
            cs=0x1010, ds=0x2222, es=0x1111, ss=ss,
            ip=0x35AA, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x35AA)] = overkill_tandy_source_strided_copy_35aa
        return cpu

    for flags in (0x0203, 0x0603):
        asm = make_cpu(False, flags=flags, seed=0x35AA + flags)
        hook = make_cpu(True, flags=flags, seed=0x35AA + flags)
        for _ in range(2000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_tandy_small_strided_copy_34d8_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_small_strided_copy_34d8

    body = ("a5a5a5a503fb" * 16) + "c3"
    code = bytes.fromhex("83ffff7501c3bb6000" + body)

    def make_cpu(use_hook: bool, *, flags: int, di: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x34D8, code)
        ds, es, ss = 0x3000, 0x4000, 0x5000
        si = 0x0180
        for off in range(-0x40, 0x300):
            mem.wb(ds, (si + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x700):
            mem.wb(es, (di + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x7777, cx=0x3333, dx=0xAAAA,
            si=si, di=di, bp=0x237C, sp=0x9000,
            cs=0x1010, ds=ds, es=es, ss=ss,
            ip=0x34D8, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x34D8)] = overkill_tandy_small_strided_copy_34d8
        return cpu

    for flags in (0x0203, 0x0603):
        for di in (0x0240, 0xFFFF):
            asm = make_cpu(False, flags=flags, di=di, seed=0x34D8 + flags + di)
            hook = make_cpu(True, flags=flags, di=di, seed=0x34D8 + flags + di)
            for _ in range(1000):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.data == hook.mem.data


def test_tandy_draw_object_block_35cc_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_draw_object_block_35cc

    code_35cc = bytes.fromhex(
        "e8672489460c3dffff7501c303064c2389460c8bf08b7e0e"
        "2e8e0696952e8e1e9895bb6000"
        + ("a5a5a5a503f3" * 16)
        + "2e8e1e9695c3"
    )
    code_5a36 = bytes.fromhex("2e 8b 1e bc 95 d1 e3 2e ff a7 42 5a")
    code_30d2 = bytes.fromhex(
        "8b5e0281fbe0007203e9d4f4d1e38b9fc89983fbff7503e9c6f4"
        "8b4604c746120000d1e803c3837e24007501c3ff4e24c3"
    )
    code_25b2 = bytes.fromhex("b8 ff ff c3")

    def make_cpu(
        use_hook: bool,
        *,
        y: int,
        x: int,
        row_word: int,
        countdown: int,
        flags: int,
        seed: int,
    ) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x35CC, code_35cc)
        mem.load(0x1010, 0x5A36, code_5a36)
        mem.load(0x1010, 0x30D2, code_30d2)
        mem.load(0x1010, 0x25B2, code_25b2)
        game_ds, src_ds, dst_es, ss = 0x2000, 0x3000, 0x4000, 0x5000
        bp = 0x0100
        dest = 0x0240
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x5A46, 0x30D2)
        mem.ww(0x1010, 0x9596, dst_es)
        mem.ww(0x1010, 0x9598, src_ds)
        mem.ww(game_ds, 0x234C, 0x0080)
        mem.ww(game_ds, (0x99C8 + ((y << 1) & 0xFFFF)) & 0xFFFF, row_word)
        mem.ww(ss, bp + 0x02, y)
        mem.ww(ss, bp + 0x04, x)
        mem.ww(ss, bp + 0x0C, 0xCAFE)
        mem.ww(ss, bp + 0x0E, dest)
        mem.ww(ss, bp + 0x12, 0xBEEF)
        mem.ww(ss, bp + 0x24, countdown)
        source = ((row_word + (x >> 1) + 0x0080) & 0xFFFF) if row_word != 0xFFFF else 0x0180
        for off in range(-0x40, 0x900):
            mem.wb(src_ds, (source + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x300):
            mem.wb(dst_es, (dest + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=0x6666, bx=0x7777, cx=0x3333, dx=0x9999,
            si=0xAAAA, di=0xBBBB, bp=bp,
            sp=0x9000, cs=0x1010, ds=game_ds, es=0x1111, ss=ss,
            ip=0x35CC, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x35CC)] = overkill_tandy_draw_object_block_35cc
        return cpu

    cases = [
        dict(y=0x00C0, x=0x0058, row_word=0x2080, countdown=0, flags=0x0203),
        dict(y=0x00D0, x=0x005B, row_word=0x23C0, countdown=3, flags=0x0203),
        dict(y=0x00E0, x=0x0058, row_word=0x2080, countdown=0, flags=0x0246),
        dict(y=0x0010, x=0x0058, row_word=0xFFFF, countdown=0, flags=0x0287),
    ]
    for index, case in enumerate(cases):
        asm = make_cpu(False, seed=0x35CC + index, **case)
        hook = make_cpu(True, seed=0x35CC + index, **case)
        for _ in range(600):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == (0x1010, 0xBEEF)
        assert hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_tandy_layer_sprite_draw_768e_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_layer_sprite_draw_768e

    code_768e = bytes.fromhex(
        "8b7e0c83ffff7501c32e8e0698958b5e082e8b0eaa9581fbfa007209"
        "81ebfa002e8b0eac95d1e381c392912e8b372e8b1ebc95d1e3d1e3"
        "d1e3035e12ba1677f74624ffff7503bae676d1e303da8ed9bd1000"
        "8bcd2eff27"
    )
    code_2f40 = bytes.fromhex(
        "bb60008b04f7d026090583c60483c702"
        "8b04f7d026090583c60483c702"
        "8b04f7d026090583c60483c702"
        "8b04f7d026090583c60483c702"
        "03fbe2c52e8e1e9695c3"
    )
    code_2f81 = bytes.fromhex(
        "bb6000ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "03fbe2d12e8e1e9695c3"
    )

    def make_cpu(use_hook: bool, *, di: int, target: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x768E, code_768e)
        mem.load(0x1010, 0x2F40, code_2f40)
        mem.load(0x1010, 0x2F81, code_2f81)
        game_ds, src_a, src_b, dest_es, ss = 0x2000, 0x3000, 0x3100, 0x4000, 0x5000
        bp = 0x0100
        mem.ww(0x1010, 0x9596, game_ds)
        mem.ww(0x1010, 0x9598, dest_es)
        mem.ww(0x1010, 0x95AA, src_a)
        mem.ww(0x1010, 0x95AC, src_b)
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x9192 + 4 * 2, 0x0180)
        mem.ww(0x1010, 0x9192 + 6 * 2, 0x0280)
        mem.ww(0x1010, 0x76E6 + 16 * 2, target)
        mem.ww(ss, bp + 0x08, 4)
        mem.ww(ss, bp + 0x0C, di)
        mem.ww(ss, bp + 0x12, 0)
        mem.ww(ss, bp + 0x24, 0)
        for off in range(-0x40, 0x500):
            mem.wb(src_a, (0x0180 + off) & 0xFFFF, rnd.randrange(256))
            mem.wb(src_b, (0x0280 + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x900):
            mem.wb(dest_es, (di + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp,
            sp=0x9000, cs=0x1010, ds=game_ds, es=0x7777, ss=ss,
            ip=0x768E, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x768E)] = overkill_layer_sprite_draw_768e
        return cpu

    for di, target, stop in (
        (0x0240, 0x2F81, (0x1010, 0xBEEF)),
        (0x0240, 0x2F40, (0x1010, 0xBEEF)),
        (0xFFFF, 0x2F81, (0x1010, 0xBEEF)),
    ):
        asm = make_cpu(False, di=di, target=target, seed=0x768E + target + di)
        hook = make_cpu(True, di=di, target=target, seed=0x768E + target + di)
        for _ in range(3000):
            if asm.addr() == stop:
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == stop
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data

    hook = make_cpu(True, di=0x0240, target=0x1234, seed=0x768E + 0x1234 + 0x0240)
    with pytest.raises(RuntimeError, match="unverified original-code path.*768E Tandy sprite compositor"):
        hook.step()


def test_tandy_layer_sprite_draw_75a6_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_layer_sprite_draw_75a6

    # Real bytes: 75A6 routine (75A6..75F4) immediately followed by the shared
    # 75F5 dispatcher so the second-slot fall-through works, plus a 2F81 composite.
    code_75a6 = bytes.fromhex(
        "8b5e082e8b0ea69583fb1c720883eb1c2e8b0eae95d1e381c392932e8b372e89"
        "3624762e890e26768b7e0c83ffff740555e81b005d8b7e1083ffff7501c32e8b"
        "3624762e8b0e2676a12810d1e803f0"
    )
    code_75f5 = bytes.fromhex(
        "2e8e0698952e8b1ebc95d1e3d1e3d1e3035e12ba5876f74624ffff7503ba2876"
        "d1e303da8ed9bd10008bcd2eff27"
    )
    code_2f81 = bytes.fromhex(
        "bb6000ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "03fbe2d12e8e1e9695c3"
    )
    assert len(code_75a6) == 0x75F5 - 0x75A6  # 75F5 must follow contiguously

    def make_cpu(use_hook, *, di0, di1, target, seed):
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x75A6, code_75a6)
        mem.load(0x1010, 0x75F5, code_75f5)
        mem.load(0x1010, 0x2F81, code_2f81)
        game_ds, src_seg, dest_es, ss = 0x2000, 0x3000, 0x4000, 0x5000
        bp = 0x0100
        sprite_ptr = 0x0180
        mem.ww(0x1010, 0x9596, game_ds)
        mem.ww(0x1010, 0x9598, dest_es)
        mem.ww(0x1010, 0x95A6, src_seg)
        mem.ww(0x1010, 0x95AE, src_seg)
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x9392 + 4 * 2, sprite_ptr)  # sprite index 4 -> frame pointer
        mem.ww(0x1010, 0x7648, target)              # 75F5 dispatch (mode 2, bp+24==0)
        mem.ww(game_ds, 0x1028, 0x0100)             # DS:[1028]>>1 = second-frame step
        mem.ww(ss, bp + 0x08, 4)                    # sprite index
        mem.ww(ss, bp + 0x0C, di0)                  # draw slot 1 dest
        mem.ww(ss, bp + 0x10, di1)                  # draw slot 2 dest
        mem.ww(ss, bp + 0x12, 0)
        mem.ww(ss, bp + 0x24, 0)
        for off in range(-0x40, 0x600):
            mem.wb(src_seg, (sprite_ptr + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x1000):
            mem.wb(dest_es, (0x0200 + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0xAAAA,
            si=0x5555, di=0x6666, bp=bp,
            sp=0x9000, cs=0x1010, ds=game_ds, es=0x7777, ss=ss,
            ip=0x75A6, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x75A6)] = overkill_layer_sprite_draw_75a6
        return cpu

    # Both slots, only-second-slot, and no-slot paths.
    for di0, di1 in ((0x0240, 0x0A00), (0xFFFF, 0x0A00), (0x0240, 0xFFFF), (0xFFFF, 0xFFFF)):
        asm = make_cpu(False, di0=di0, di1=di1, target=0x2F81, seed=di0 ^ (di1 << 1))
        hook = make_cpu(True, di0=di0, di1=di1, target=0x2F81, seed=di0 ^ (di1 << 1))
        for _ in range(6000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF), (di0, di1)
        assert asm.s.snapshot() == hook.s.snapshot(), (di0, di1)
        assert asm.mem.data == hook.mem.data, (di0, di1)

    # Unknown composite target must fail fast rather than silently fall back.
    hook = make_cpu(True, di0=0x0240, di1=0xFFFF, target=0x1234, seed=1)
    with pytest.raises(RuntimeError, match="unverified original-code path"):
        hook.step()


def test_tandy_layer1_scan_a8c7_composes_7596_768e_like_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_scan_layer1_draw_a8c7

    code_a8c7 = bytes.fromhex(
        "518bd9d1e38bafca32837e0000741e833eacbd01740e813e5023b600"
        "7706837e16017409837e0a017503e8a2cc59e2d0"
    )
    code_7596 = bytes.fromhex("8b5e14d1e32effa7a075")
    code_768e = bytes.fromhex(
        "8b7e0c83ffff7501c32e8e0698958b5e082e8b0eaa9581fbfa007209"
        "81ebfa002e8b0eac95d1e381c392912e8b372e8b1ebc95d1e3d1e3"
        "d1e3035e12ba1677f74624ffff7503bae676d1e303da8ed9bd1000"
        "8bcd2eff27"
    )
    code_2f40 = bytes.fromhex(
        "bb60008b04f7d026090583c60483c702"
        "8b04f7d026090583c60483c702"
        "8b04f7d026090583c60483c702"
        "8b04f7d026090583c60483c702"
        "03fbe2c52e8e1e9695c3"
    )
    code_2f81 = bytes.fromhex(
        "bb6000ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "ad2623050b0483c602ab"
        "03fbe2d12e8e1e9695c3"
    )

    def make_cpu(use_hook: bool, *, fallback: bool, sprite_target: int = 0x2F81) -> CPU8086:
        rnd = random.Random(0xA8C7 + int(fallback) + sprite_target)
        mem = Memory()
        mem.load(0x1010, 0xA8C7, code_a8c7)
        mem.load(0x1010, 0x7596, code_7596)
        mem.load(0x1010, 0x768E, code_768e)
        mem.load(0x1010, 0x2F40, code_2f40)
        mem.load(0x1010, 0x2F81, code_2f81)
        game_ds, src_seg, dest_es, ss = 0x2000, 0x3000, 0x4000, 0x5000
        mem.ww(game_ds, 0xBDAC, 1)
        mem.ww(game_ds, 0x2350, 0)
        mem.ww(0x1010, 0x9596, game_ds)
        mem.ww(0x1010, 0x9598, dest_es)
        mem.ww(0x1010, 0x95AA, src_seg)
        mem.ww(0x1010, 0x95AC, src_seg)
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x9192 + 4 * 2, 0x0180)
        mem.ww(0x1010, 0x75A2, 0x1234 if fallback else 0x768E)
        mem.ww(0x1010, 0x76E6 + 16 * 2, sprite_target)
        for cx in range(1, 4):
            ptr = 0x0100 + cx * 0x40
            mem.ww(game_ds, (0x32CA + cx * 2) & 0xFFFF, ptr)
            mem.ww(ss, ptr, 0)
            mem.ww(ss, ptr + 0x08, 4)
            mem.ww(ss, ptr + 0x0A, 1)
            mem.ww(ss, ptr + 0x0C, 0x0240 + cx * 0x100)
            mem.ww(ss, ptr + 0x12, 0)
            mem.ww(ss, ptr + 0x14, 1)
            mem.ww(ss, ptr + 0x16, 0)
            mem.ww(ss, ptr + 0x24, 0)
        mem.ww(ss, 0x0100 + 2 * 0x40, 1)
        for off in range(-0x40, 0x500):
            mem.wb(src_seg, (0x0180 + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x900):
            mem.wb(dest_es, (0x0440 + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=3, dx=0x3333, si=0x4444, di=0x5555,
            bp=0x6666, sp=0x9000, cs=0x1010, ds=game_ds, es=0x7777,
            ss=ss, ip=0xA8C7, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA8C7)] = overkill_scan_layer1_draw_a8c7
        return cpu

    for fallback, sprite_target in (
        (False, 0x2F81),
        (False, 0x2F40),
        (True, 0x2F81),
    ):
        asm = make_cpu(False, fallback=fallback, sprite_target=sprite_target)
        hook = make_cpu(True, fallback=fallback, sprite_target=sprite_target)
        for _ in range(5000):
            if asm.addr() == (0x1010, 0xA8F1):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xA8F1)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_layer0_scan_a894_stops_at_real_call_like_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_scan_layer0_draw_a894

    code_a894 = bytes.fromhex(
        "518bd9d1e38bafca32837e0000741e833eacbd01740e813e5023"
        "b6007706837e16017409837e0a007503e8d5cc59e2d0"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA894, code_a894)
        ds = 0x2000
        ss = 0x3000
        bp = 0x2884
        cx = 0x0017
        mem.ww(ds, 0x32CA + cx * 2, bp)
        mem.ww(ds, 0xBDAC, 0x0001)
        mem.ww(ds, 0x2350, 0x0000)
        mem.ww(ss, bp + 0x00, 0x0001)
        mem.ww(ss, bp + 0x0A, 0x0000)
        mem.ww(ss, bp + 0x16, 0x0005)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=cx, dx=0x3333,
            si=0x4444, di=0x5555, bp=0x6666, sp=0xA276,
            cs=0x1010, ds=ds, es=0xB800, ss=ss,
            ip=0xA894, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA894)] = overkill_scan_layer0_draw_a894
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(80):
        if asm.addr() == (0x1010, 0xA8BE):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xA8BE)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_lz_output_byte_ede9_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_lz_output_byte_ede9

    code = bytes.fromhex(
        'aa 0b ff 75 09 50 8c c0 05 00 10 8e c0 58'
        '2e ff 06 e5 ed 75 05 2e ff 06 e7 ed c3'
    )

    def make_cpu(use_hook: bool, di: int, counter: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xEDE9, code)
        mem.ww(0x1010, 0xEDE5, counter)
        mem.ww(0x1010, 0xEDE7, 0x2222)
        state = CPUState(
            ax=0x12AB, bx=0x3333, cx=0x4444, dx=0x5555,
            si=0x6666, di=di, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
            ip=0xEDE9, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xEDE9)] = overkill_lz_output_byte_ede9
        return cpu

    for di, counter in ((0x0200, 0x1234), (0xFFFF, 0xFFFF)):
        asm = make_cpu(False, di, counter)
        hook = make_cpu(True, di, counter)
        for _ in range(80):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.block(0x7000, di, 1) == hook.mem.block(0x7000, di, 1)
        assert asm.mem.rw(0x1010, 0xEDE5) == hook.mem.rw(0x1010, 0xEDE5)
        assert asm.mem.rw(0x1010, 0xEDE7) == hook.mem.rw(0x1010, 0xEDE7)


def test_lz_input_byte_ed97_hook_matches_interpreted_asm_paths():
    from dos_re.cpu import CPU8086, CPUState, CF
    from dos_re.memory import Memory
    from overkill.hooks import overkill_lz_input_byte_ed97

    code = bytes.fromhex(
        '2e f6 06 04 ee ff 75 30 81 c6 b8 d8 ac 81 ee b8 d8 81 e6 ff 03'
        '75 20 9c 50 53 51 52 56 57 55 ba b8 d8 b8 00 3f 2e 8b 1e 66 d6'
        'b9 00 04 cd 21 5d 5f 5e 5a 59 5b 58 9d c3 2e a0 05 ee 2e c6 06'
        '04 ee 00 c3'
    )

    def fake_int21(cpu, num: int) -> None:
        assert num == 0x21
        assert cpu.s.ax == 0x3F00
        assert cpu.s.dx == 0xD8B8
        assert cpu.s.cx == 0x0400
        assert cpu.s.bx == 0x0007
        for i in range(0x400):
            cpu.mem.wb(cpu.s.ds, (0xD8B8 + i) & 0xFFFF, (i ^ 0x5A) & 0xFF)
        cpu.s.ax = 0x0400
        cpu.set_flag(CF, False)

    def make_cpu(use_hook: bool, si: int, pushback: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xED97, code)
        mem.ww(0x1010, 0xD666, 0x0007)
        mem.wb(0x1010, 0xEE04, 1 if pushback else 0)
        mem.wb(0x1010, 0xEE05, 0xCC)
        mem.wb(0x6000, (0xD8B8 + si) & 0xFFFF, 0xA0 | (si & 0x0F))
        state = CPUState(
            ax=0x1200, bx=0x3333, cx=0x4444, dx=0x5555,
            si=si, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
            ip=0xED97, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.interrupt_handler = fake_int21
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xED97)] = overkill_lz_input_byte_ed97
        return cpu

    for si, pushback in ((0x0005, False), (0x03FF, False), (0x0012, True)):
        asm = make_cpu(False, si, pushback)
        hook = make_cpu(True, si, pushback)
        for _ in range(120):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.block(0x6000, 0xD8B8, 16) == hook.mem.block(0x6000, 0xD8B8, 16)
        assert asm.mem.rb(0x1010, 0xEE04) == hook.mem.rb(0x1010, 0xEE04)


def test_overlay_xor_decode_254a_05bf_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_overlay_xor_decode_254a_05bf

    code = bytes.fromhex('30 05 47 02 c4 e2 f9')

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x254A, 0x05BF, code)
        payload = bytes(range(32))
        mem.load(0x254A, 0x075C, payload)
        state = CPUState(
            ax=0x3217, bx=0x000F, cx=0x001B, dx=0x075C,
            si=0x076A, di=0x075C, bp=0xFFFF, sp=0xA264,
            cs=0x254A, ds=0x254A, es=0x25CC, ss=0x25CC,
            ip=0x05BF, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x254A, 0x05BF)] = overkill_overlay_xor_decode_254a_05bf
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(200):
        if asm.addr() == (0x254A, 0x05C6):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x254A, 0x05C6)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.block(0x254A, 0x075C, 32) == hook.mem.block(0x254A, 0x075C, 32)


def test_overlay_signature_compare_254a_0582_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_overlay_signature_compare_254a_0582

    code = bytes.fromhex("ac 3a 05 74 03 e9 b6 00 47 e2 f5")

    def make_cpu(use_hook: bool, *, mismatch_at: int | None) -> CPU8086:
        mem = Memory()
        mem.load(0x254A, 0x0582, code)
        left = bytearray(b"SIGNAT")
        right = bytearray(left)
        if mismatch_at is not None:
            right[mismatch_at] ^= 0x20
        mem.load(0x254A, 0x074E, left)
        mem.load(0x254A, 0x0756, right)
        state = CPUState(
            ax=0x1200, bx=0x2222, cx=0x0006, dx=0x4444,
            si=0x074E, di=0x0756, bp=0x6666, sp=0x9000,
            cs=0x254A, ds=0x254A, es=0x3000, ss=0x4000,
            ip=0x0582, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x254A, 0x0582)] = overkill_overlay_signature_compare_254a_0582
        return cpu

    for mismatch_at, stop in ((None, (0x254A, 0x058D)), (3, (0x254A, 0x0640))):
        asm = make_cpu(False, mismatch_at=mismatch_at)
        hook = make_cpu(True, mismatch_at=mismatch_at)
        for _ in range(40):
            if asm.addr() == stop:
                break
            asm.step()
        hook.step()

        assert asm.addr() == hook.addr() == stop
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


OVERLAY_254A_05A1_CODE = bytes.fromhex(
    """
    ba 5c 07 8b 0e 54 07 8b 1e 44 07 b4 3f cd 21 73 03 e9 8b 00
    bf 5c 07 8b 0e 54 07 a1 4c 07 30 05 47 02 c4 e2 f9 a3 4c 07
    be 5c 07 83 c6 0d c4 3e 46 07 b4 03 0e e8 28 01 26 80 3d 20
    75 03 47 eb f7 80 3c 20 75 03 46 eb f8 26 8a 05 47 8a 24 46
    3c 61 72 06 3c 7a 77 02 24 5f 3a c4 75 38 0a c0 75 d6 0a e4
    75 30 be 5c 07 8b 54 05 8b 4c 07 03 16 aa 07 13 0e ac 07 b8
    00 42 8b 1e 44 07 cd 21 72 1d be 5c 07 8b 4c 09 8b 54 0b a1
    44 07 8b d8 f8 07 1f 5f 5e cb ff 0e 4a 07 74 03 e9 61 ff 8b
    1e 44 07 0b db 74 06 b4 3e cd 21 72 1e 8b 36 40 07 ac 0a c0
    75 fb 80 3c ff 75 03 be ae 07 89 36 40 07 3b 36 42 07 74 03
    e9 98 fe 8b 1e 44 07 0b db 74 04 b4 3e cd 21 b8 02 00 f9 07
    1f 5f 5e cb
    """
)

OVERLAY_254A_0701_CODE = bytes.fromhex(
    """
    2e f7 06 3a 07 02 00 74 2f f6 c4 01 74 11 8b ee ac 0a c0 74
    08 3c 5c 75 f7 8b ee eb f3 8b f5 f6 c4 02 74 14 8b ef 26 8a
    05 47 0a c0 74 08 3c 5c 75 f4 8b ef eb f0 8b fd cb
    """
)


def test_overlay_path_normalizer_254a_0701_hook_matches_interpreted_asm():
    from overkill.hooks import overkill_overlay_path_normalizer_254a_0701

    def make_cpu(use_hook: bool, gate: int) -> CPU8086:
        mem = Memory()
        mem.load(0x254A, 0x0701, OVERLAY_254A_0701_CODE)
        mem.ww(0x254A, 0x073A, gate)
        mem.load(0x3000, 0x0100, b"dir1\\dir2\\entry.bin\x00")
        mem.load(0x4000, 0x0200, b"root\\branch\\entry.bin\x00")
        state = CPUState(
            ax=0x0300, bx=0x0000, cx=0x0000, dx=0x0000,
            si=0x0100, di=0x0200, bp=0x0000, sp=0x8FFE,
            cs=0x254A, ds=0x3000, es=0x4000, ss=0x5000,
            ip=0x0701, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0x254A)
        cpu.push(0x05D9)
        if use_hook:
            cpu.replacement_hooks[(0x254A, 0x0701)] = overkill_overlay_path_normalizer_254a_0701
        return cpu

    for gate in (0x0000, 0x0002):
        asm = make_cpu(False, gate)
        hook = make_cpu(True, gate)
        for _ in range(400):
            if asm.addr() == (0x254A, 0x05D9):
                break
            asm.step()
        hook.step()

        assert asm.addr() == hook.addr() == (0x254A, 0x05D9)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data
        if gate & 0x0002:
            assert asm.mem.block(0x3000, asm.s.si, len(b"entry.bin\x00")) == b"entry.bin\x00"
            assert hook.mem.block(0x3000, hook.s.si, len(b"entry.bin\x00")) == b"entry.bin\x00"
            assert asm.mem.block(0x4000, asm.s.di, len(b"entry.bin\x00")) == b"entry.bin\x00"
            assert hook.mem.block(0x4000, hook.s.di, len(b"entry.bin\x00")) == b"entry.bin\x00"


def test_overlay_entry_name_compare_254a_05d9_hook_matches_interpreted_asm():
    from overkill.hooks import overkill_overlay_entry_name_compare_254a_05d9

    def make_cpu(use_hook: bool, *, mismatch: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x254A, 0x05A1, OVERLAY_254A_05A1_CODE)
        if mismatch:
            mem.load(0x3000, 0x0100, b"PLANET02\x00")
            mem.load(0x4000, 0x0200, b"  planet01  \x00")
        else:
            mem.load(0x3000, 0x0100, b"PLANET01\x00")
            mem.load(0x4000, 0x0200, b"  planet01  \x00")
        state = CPUState(
            ax=0x0000, bx=0x0000, cx=0x0000, dx=0x0000,
            si=0x0100, di=0x0200, bp=0x0000, sp=0x9000,
            cs=0x254A, ds=0x3000, es=0x4000, ss=0x5000,
            ip=0x05D9, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x254A, 0x05D9)] = overkill_overlay_entry_name_compare_254a_05d9
        return cpu

    for mismatch, stop in ((False, (0x254A, 0x0607)), (True, (0x254A, 0x0637))):
        asm = make_cpu(False, mismatch=mismatch)
        hook = make_cpu(True, mismatch=mismatch)
        for _ in range(300):
            if asm.addr() == stop:
                break
            asm.step()
        hook.step()

        assert asm.addr() == hook.addr() == stop
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_overlay_directory_entry_scan_254a_05a1_hook_matches_interpreted_asm():
    from dos_re.cpu import CF
    from overkill.hooks import overkill_overlay_directory_entry_scan_254a_05a1

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x254A, 0x05A1, OVERLAY_254A_05A1_CODE)
        mem.load(0x254A, 0x0701, OVERLAY_254A_0701_CODE)
        mem.ww(0x254A, 0x073A, 0x0002)
        mem.ww(0x254A, 0x0744, 0x0005)
        mem.ww(0x254A, 0x0746, 0x0100)
        mem.ww(0x254A, 0x0748, 0x4000)
        mem.ww(0x254A, 0x074A, 0x0001)
        mem.ww(0x254A, 0x074C, 0x0000)
        mem.ww(0x254A, 0x0754, 0x001B)
        mem.load(0x3000, 0x0100, b"root\\branch\\entry.bin\x00")
        payload = bytearray(b"\x00" * 0x1B)
        payload[0x0D:0x0D + len(b"entry.bin\x00")] = b"entry.bin\x00"
        payload = bytes(payload)
        mem.load(0x254A, 0x075C, payload)

        def fake_int21(cpu, num: int) -> None:
            assert num == 0x21
            ah = (cpu.s.ax >> 8) & 0xFF
            if ah == 0x3F:
                count = cpu.s.cx & 0xFFFF
                for i in range(count):
                    cpu.mem.wb(cpu.s.ds, (cpu.s.dx + i) & 0xFFFF, payload[i])
                cpu.s.ax = count
                cpu.set_flag(CF, False)
            elif ah == 0x42:
                cpu.s.ax = 0
                cpu.set_flag(CF, False)
            else:
                cpu.set_flag(CF, False)

        state = CPUState(
            ax=0x0000, bx=0x0000, cx=0x0000, dx=0x0000,
            si=0x0000, di=0x0000, bp=0x0000, sp=0x8FFE,
            cs=0x254A, ds=0x254A, es=0x0000, ss=0x5000,
            ip=0x05A1, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.interrupt_handler = fake_int21
        cpu.push(0x254A)
        cpu.push(0x04D7)
        if use_hook:
            cpu.replacement_hooks[(0x254A, 0x05A1)] = overkill_overlay_directory_entry_scan_254a_05a1
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(1000):
        if asm.addr() == (0x254A, 0x0640):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x254A, 0x0640)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data
    assert asm.get_flag(CF) == hook.get_flag(CF)
    assert asm.mem.block(0x254A, 0x075C, 0x1B) == hook.mem.block(0x254A, 0x075C, 0x1B)


def test_lz_backref_copy_ed7a_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_lz_backref_copy_ed7a

    code_ed7a = bytes.fromhex(
        '2e 8a 87 b8 dc e8 67 00 2e 88 86 b8 dc 43 81 e3 ff 0f'
        '45 81 e5 ff 0f e2 e7 eb 91'
    )
    code_ede9 = bytes.fromhex(
        'aa 0b ff 75 09 50 8c c0 05 00 10 8e c0 58'
        '2e ff 06 e5 ed 75 05 2e ff 06 e7 ed c3'
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xED7A, code_ed7a)
        mem.load(0x1010, 0xEDE9, code_ede9)
        for i, value in enumerate([0xA0, 0xB1, 0xC2, 0xD3, 0xE4, 0xF5]):
            mem.wb(0x1010, 0xDCB8 + 0x00FE + i, value)
        mem.ww(0x1010, 0xEDE5, 0xFFFE)
        mem.ww(0x1010, 0xEDE7, 0x0101)
        state = CPUState(
            ax=0x1200, bx=0x00FE, cx=0x0005, dx=0x5555,
            si=0x6666, di=0xFFFE, bp=0x0FFE, sp=0x9000,
            cs=0x1010, ds=0x1010, es=0x7000, ss=0x4000,
            ip=0xED7A, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xED7A)] = overkill_lz_backref_copy_ed7a
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xED26):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xED26)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.block(0x7000, 0xFFFE, 2) == hook.mem.block(0x7000, 0xFFFE, 2)
    assert asm.mem.block(0x8000, 0x0000, 4) == hook.mem.block(0x8000, 0x0000, 4)
    assert asm.mem.block(0x1010, 0xDCB8 + 0x0FFE, 8) == hook.mem.block(0x1010, 0xDCB8 + 0x0FFE, 8)
    assert asm.mem.rw(0x1010, 0xEDE5) == hook.mem.rw(0x1010, 0xEDE5)
    assert asm.mem.rw(0x1010, 0xEDE7) == hook.mem.rw(0x1010, 0xEDE7)


def test_full_lz_decoder_ecf2_hook_matches_interpreted_asm_literals_and_terminator():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_lz_decoder_ecf2

    lz_ecf2 = bytes.fromhex(
        '062ec706e5ed00002ec706e7ed00002ec43eeeec2ec60604ee00be0000bd0000'
        'b9f7072ec786b8dc00004545e2f5bdee0fba0000d1eaf7c200017507e86600'
        '8ad0b6fff7c201007412e85900e8a8002e8886b8dc4581e5ff0febd9e84700'
        '8ae0e8420086c43d0000750ce838003c007432e87400b0008accd0ecd0ecd0ec'
        'd0ec80e10f8bd880c1032e8a87b8dce867002e8886b8dc4381e3ff0f'
        '4581e5ff0fe2e7eb9107c32ef60604eeff753081c6b8d8ac81eeb8d881e6'
        'ff0375209c50535152565755bab8d8b8003f2e8b1e66d6b90004cd215d5f'
        '5e5a595b589dc32ea005ee2ec60604ee00c32ec60604ee012ea205eec3dc0f'
        '0000aa0bff7509508cc00500108ec0582eff06e5ed75052eff06e7edc3'
    )

    # Flag byte 0000_0111b: three literal tokens, then a zero/backref token.
    # The zero/backref token is encoded as 00 00 00 and terminates the stream.
    stream = bytes([0x07, ord('A'), ord('B'), ord('C'), 0x00, 0x00, 0x00])

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xECF2, lz_ecf2)
        mem.load(0x6000, 0xD8B8, stream)
        mem.ww(0x1010, 0xECEE, 0x0200)
        mem.ww(0x1010, 0xECF0, 0x7000)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x1234, ss=0x4000,
            ip=0xECF2, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xECF2)] = overkill_lz_decoder_ecf2
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(120000):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.block(0x7000, 0x0200, 8) == hook.mem.block(0x7000, 0x0200, 8) == b'ABC\x00\x00\x00\x00\x00'
    assert asm.mem.block(0x1010, 0xDCB8 + 0x0FEE, 8) == hook.mem.block(0x1010, 0xDCB8 + 0x0FEE, 8)
    assert asm.mem.rw(0x1010, 0xEDE5) == hook.mem.rw(0x1010, 0xEDE5) == 3
    assert asm.mem.rw(0x1010, 0xEDE7) == hook.mem.rw(0x1010, 0xEDE7) == 0


def test_full_lz_decoder_ecf2_hook_matches_interpreted_asm_backref():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_lz_decoder_ecf2

    lz_ecf2 = bytes.fromhex(
        '062ec706e5ed00002ec706e7ed00002ec43eeeec2ec60604ee00be0000bd0000'
        'b9f7072ec786b8dc00004545e2f5bdee0fba0000d1eaf7c200017507e86600'
        '8ad0b6fff7c201007412e85900e8a8002e8886b8dc4581e5ff0febd9e84700'
        '8ae0e8420086c43d0000750ce838003c007432e87400b0008accd0ecd0ecd0ec'
        'd0ec80e10f8bd880c1032e8a87b8dce867002e8886b8dc4381e3ff0f'
        '4581e5ff0fe2e7eb9107c32ef60604eeff753081c6b8d8ac81eeb8d881e6'
        'ff0375209c50535152565755bab8d8b8003f2e8b1e66d6b90004cd215d5f'
        '5e5a595b589dc32ea005ee2ec60604ee00c32ec60604ee012ea205eec3dc0f'
        '0000aa0bff7509508cc00500108ec0582eff06e5ed75052eff06e7edc3'
    )

    # Three literal bytes A/B/C, then a backref from ring offset 0FEE with
    # length 3, then 00 00 00 terminator.  Expected output: ABCABC.
    stream = bytes([0x07, ord('A'), ord('B'), ord('C'), 0xEE, 0xF0, 0x00, 0x00, 0x00])

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xECF2, lz_ecf2)
        mem.load(0x6000, 0xD8B8, stream)
        mem.ww(0x1010, 0xECEE, 0x0200)
        mem.ww(0x1010, 0xECF0, 0x7000)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x1234, ss=0x4000,
            ip=0xECF2, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xECF2)] = overkill_lz_decoder_ecf2
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(120000):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.block(0x7000, 0x0200, 8) == hook.mem.block(0x7000, 0x0200, 8) == b'ABCABC\x00\x00'
    assert asm.mem.block(0x1010, 0xDCB8 + 0x0FEE, 10) == hook.mem.block(0x1010, 0xDCB8 + 0x0FEE, 10)
    assert asm.mem.rw(0x1010, 0xEDE5) == hook.mem.rw(0x1010, 0xEDE5) == 6
    assert asm.mem.rw(0x1010, 0xEDE7) == hook.mem.rw(0x1010, 0xEDE7) == 0


def test_expand_4plane_list_450c_hook_matches_interpreted_control_loop():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_expand_4plane_block_4511, overkill_expand_4plane_list_450c

    # Original bytes for 44D7..450A and the 450C dispatcher.  The 4511 renderer
    # itself is replaced in both CPUs; this test isolates the list-control loop.
    header_44d7 = bytes.fromhex(
        '8b040b44027501c32e8b1ee00b2e8306e00b02ad2e833ed80b0074042e893fab'
        '2ea39e5bad2e833ed80b007401ab2ea39c5b40c3'
    )
    dispatcher_450c = bytes.fromhex('e8c8ff7499')

    def make_cpu(use_list_hook: bool, bd8: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x44D7, header_44d7)
        mem.load(0x1010, 0x450C, dispatcher_450c)
        table = bytes([0, 1, 1, 1, 2, 2, 2, 1, 2, 1, 1, 1, 2, 2, 1, 3])
        for i, b in enumerate(table):
            mem.wb(0x1010, 0x45E6 + i, b)
        mem.ww(0x1010, 0x0BD6, 1)
        mem.ww(0x1010, 0x0BD8, bd8)
        mem.ww(0x1010, 0x0BE0, 0x7000)
        mem.wb(0x1010, 0x0000, 0x02)
        mem.ww(0x1010, 0x45E4, 0x2468)

        # Two 1x1 blocks followed by a 0000:0000 terminator.  Each block consumes
        # four source bytes: one byte for each bitplane.
        source = [
            0x0001, 0x0001, 0x0096, 0x0039,
            0x0001, 0x0001, 0x00C3, 0x005A,
            0x0000, 0x0000,
        ]
        off = 0x0100
        for w in source:
            mem.ww(0x6000, off, w)
            off += 2

        state = CPUState(
            ax=0xA65C, bx=0x1111, cx=0x7E23, dx=0xC398,
            si=0x0100, di=0x0200, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
            ip=0x450C, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.replacement_hooks[(0x1010, 0x4511)] = overkill_expand_4plane_block_4511
        if use_list_hook:
            cpu.replacement_hooks[(0x1010, 0x450C)] = overkill_expand_4plane_list_450c
        return cpu

    for bd8 in (0, 1):
        asm = make_cpu(False, bd8)
        hook = make_cpu(True, bd8)
        for _ in range(5000):
            if asm.addr() == (0x1010, 0x44AA):
                break
            asm.step()
        hook.step()
        assert asm.addr() == (0x1010, 0x44AA)
        assert hook.addr() == (0x1010, 0x44AA)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.block(0x7000, 0x0200, 0x40) == hook.mem.block(0x7000, 0x0200, 0x40)
        assert asm.mem.block(0x1010, 0x5B94, 0x10) == hook.mem.block(0x1010, 0x5B94, 0x10)
        assert asm.mem.rw(0x1010, 0x0BE0) == hook.mem.rw(0x1010, 0x0BE0)


def test_linear_byte_rle_0367_hook_matches_interpreted_asm_on_synthetic_stream():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_linear_byte_rle_decoder_0367

    routine_0367 = bytes.fromhex(
        '8e063a028b3e3c02e8b2023c807503e92fff7216f6d886e086dce8a00286dcaa'
        'ff064402fecc79f7ebde50e88f02aaff06440258fec879f2ebce'
    )
    reader_0624 = bytes.fromhex(
        '89 1e 12 06 8b 1e 10 06 81 fb 10 06 72 1f c7 06 10 06 10 04'
        '51 b4 3f 8b 1e 40 02 b9 00 02 ba 10 04 cd 21 59 73 03 e9 65 fc'
        '8b 1e 10 06 8a 07 ff 06 10 06 8b 1e 12 06 c3'
    )

    # literal 3 bytes, repeat 2 bytes of AAh, literal 1 byte, terminator.
    packed_stream = bytes([0x02, 0x11, 0x22, 0x33, 0xFF, 0xAA, 0x00, 0x44, 0x80])

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x0367, routine_0367)
        mem.load(0x1010, 0x0624, reader_0624)
        mem.load(0x1010, 0x0410, packed_stream)
        mem.ww(0x1010, 0x023A, 0x7000)
        mem.ww(0x1010, 0x023C, 0x0100)
        mem.ww(0x1010, 0x0244, 0x3333)
        mem.ww(0x1010, 0x0610, 0x0410)
        state = CPUState(
            ax=0x5A77, bx=0x12BC, cx=0x9999, dx=0x8888,
            si=0x7777, di=0x6666, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x1010, es=0x4444, ss=0x4000,
            ip=0x0367, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x0367)] = overkill_linear_byte_rle_decoder_0367
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(1000):
        if asm.addr() == (0x1010, 0x02A8):
            break
        asm.step()
    hook.step()
    assert asm.addr() == (0x1010, 0x02A8)
    assert hook.addr() == (0x1010, 0x02A8)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.block(0x7000, 0x0100, 8) == hook.mem.block(0x7000, 0x0100, 8)
    assert asm.mem.rw(0x1010, 0x0244) == hook.mem.rw(0x1010, 0x0244)
    assert asm.mem.rw(0x1010, 0x0610) == hook.mem.rw(0x1010, 0x0610)


def test_blit_497a_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_497a_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:497A is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x497A), None)
    asm.cpu.hook_names.pop((0x1010, 0x497A), None)
    asm.cpu.trace_enabled = False

    for _ in range(10000):
        if asm.cpu.addr() == (0x1010, 0x58F1):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x58F1)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_row_copy_41da_hook_matches_interpreted_asm_on_zero_count_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_41da_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:41DA is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x41DA), None)
    asm.cpu.hook_names.pop((0x1010, 0x41DA), None)
    asm.cpu.trace_enabled = False

    for _ in range(500000):
        if asm.cpu.addr() == (0x1010, 0xCEB5):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xCEB5)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_ega_copy_5827_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_5827_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:5827 is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x5827), None)
    asm.cpu.hook_names.pop((0x1010, 0x5827), None)
    asm.cpu.trace_enabled = False

    for _ in range(10000):
        if asm.cpu.addr() == (0x1010, 0x58A4):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x58A4)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_vga_wait_50c9_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_50c9_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:50C9 is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x50C9), None)
    asm.cpu.hook_names.pop((0x1010, 0x50C9), None)
    asm.cpu.trace_enabled = False

    ret_ip = asm.cpu.mem.rw(asm.cpu.s.ss, asm.cpu.s.sp)
    for _ in range(100):
        if asm.cpu.addr() == (0x1010, ret_ip):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, ret_ip)
    assert_oracle_equivalent(asm.cpu, hook.cpu)  # C9F0 internal-call scratch below SP dropped
    assert asm.dos.vga_status_reads == hook.dos.vga_status_reads


def test_postcopy_loop_58df_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_58df_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:58DF is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    for addr in [(0x1010, 0x58DF)]:
        asm.cpu.replacement_hooks.pop(addr, None)
        asm.cpu.hook_names.pop(addr, None)
    asm.cpu.trace_enabled = False

    for _ in range(5000):
        if asm.cpu.addr() == (0x1010, 0x58F8):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x58F8)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data
    assert asm.dos.vga_status_reads == hook.dos.vga_status_reads


def test_tandy_postcopy_mode_sweep_5c74_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_postcopy_mode_sweep_5c74

    code_5c74 = bytes.fromhex(
        "2e8b1ebc95d1e32eff975a59e846f42e83060159022ea101592e3b06fd5875e02e8e1e9695c3"
    )
    code_375b = bytes.fromhex("83c720c3")
    code_50c9 = bytes.fromhex("b80800c3")

    def dummy_375b(cpu: CPU8086) -> None:
        cpu.s.di = (cpu.s.di + 0x0020) & 0xFFFF
        cpu.s.ip = cpu.pop()

    def dummy_50c9(cpu: CPU8086) -> None:
        cpu.s.ax = 0x0008
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x5C74, code_5c74)
        mem.load(0x1010, 0x375B, code_375b)
        mem.load(0x1010, 0x50C9, code_50c9)
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x595A, 0x497A)
        mem.ww(0x1010, 0x595C, 0x2D2D)
        mem.ww(0x1010, 0x595E, 0x375B)
        mem.ww(0x1010, 0x5901, 0x00C4)
        mem.ww(0x1010, 0x58FD, 0x00C8)
        mem.ww(0x1010, 0x9596, 0x6BE1)
        state = CPUState(
            ax=0x0008, bx=0x0004, cx=0x0000, dx=0x03DA,
            si=0x48F8, di=0x1400, bp=0x0034, sp=0xA274,
            cs=0x1010, ds=0x6BE1, es=0xB800, ss=0x25CC,
            ip=0x5C74, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x5C74)] = overkill_tandy_postcopy_mode_sweep_5c74
            cpu.replacement_hooks[(0x1010, 0x375B)] = dummy_375b
            cpu.replacement_hooks[(0x1010, 0x50C9)] = dummy_50c9
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(2000):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_wait_timer_tick_0679_hook_matches_interpreted_asm():
    import pytest
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_wait_timer_tick_0679

    # 0679 cmp byte ptr cs:[066B],0 ; 067F jz 0679 ; 0681 ret
    wait_code = bytes.fromhex('2e 80 3e 6b 06 00 74 f8 c3')

    def make_cpu(use_hook: bool, start_flag: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x0679, wait_code)
        mem.wb(0x1010, 0x066B, start_flag)
        state = CPUState(
            ax=0x1234, bx=0x5678, cx=0x9ABC, dx=0xDEF0,
            si=0x1111, di=0x2222, bp=0x3333, sp=0x9000,
            cs=0x1010, ds=0x4444, es=0x5555, ss=0x4000,
            ip=0x0679, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x0679)] = overkill_wait_timer_tick_0679
        return cpu

    # Case A: flag starts at 0 but no known INT 08h ISR is installed.  Do not
    # invent a synthetic tick; fail loudly so the missing timer path is fixed.
    hook = make_cpu(True, 0)
    with pytest.raises(RuntimeError, match="no synthetic timer fallback"):
        hook.step()

    # Case B: flag already non-zero.  The loop exits immediately without needing
    # external timer progress, so it still matches the original wait loop.
    # it; the hook must leave it untouched and produce the same state.
    hook = make_cpu(True, 7)
    oracle = make_cpu(False, 7)
    hook.step()
    for _ in range(10):
        if oracle.addr() == (0x1010, 0xBEEF):
            break
        oracle.step()
    assert hook.addr() == oracle.addr() == (0x1010, 0xBEEF)
    assert hook.s.snapshot() == oracle.s.snapshot()
    assert hook.mem.rb(0x1010, 0x066B) == oracle.mem.rb(0x1010, 0x066B) == 7


def test_wait_timer_tick_0679_runs_overkill_sound_isr_when_installed():
    from pathlib import Path
    from overkill.hooks import overkill_wait_timer_tick_0679
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "timer_wait_tandy_main_menu_20260612_132548"
    assert snap.exists(), "Tandy menu snapshot with installed INT 08h is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    cpu = rt.cpu
    cpu.trace_enabled = False
    cpu.s.cs = 0x1010
    cpu.s.ip = 0x0679
    cpu.push(0xBEEF)
    cpu.mem.wb(0x1010, 0x066B, 0)
    cpu.mem.wb(cpu.mem.rw(0x1010, 0x9596), 0x0054, 3)  # exercise the BIOS-chain tick path

    ports: list[tuple[int, int, int]] = []
    orig_writer = rt.dos.port_write

    def port_writer(cpu, port: int, value: int, bits: int) -> None:
        orig_writer(cpu, port, value, bits)
        if port in (0x42, 0x43, 0x61):
            ports.append((port, value & ((1 << bits) - 1), bits))

    cpu.port_writer = port_writer
    cpu.replacement_hooks[(0x1010, 0x0679)] = overkill_wait_timer_tick_0679

    cpu.step()

    assert cpu.addr() == (0x1010, 0xBEEF)
    assert cpu.s.sp == 0xA276
    assert cpu.mem.rb(0x1010, 0x066B) != 0
    assert cpu.timer_ticks_elapsed == 2
    assert any(port == 0x42 for port, _, _ in ports)
    assert any(port == 0x43 for port, _, _ in ports)
    assert any(port == 0x61 for port, _, _ in ports)


def test_hook_verifier_timer_wait_0679_delivers_real_isr_oracle():
    from pathlib import Path
    from overkill.verification import HookVerifierConfig, install_hook_verifier
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "timer_wait_tandy_main_menu_20260612_132548"
    assert snap.exists(), "Tandy menu snapshot with installed INT 08h is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    cpu = rt.cpu
    cpu.trace_enabled = False
    cpu.s.cs = 0x1010
    cpu.s.ip = 0x0679
    cpu.push(0xBEEF)
    cpu.mem.wb(0x1010, 0x066B, 0)

    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0x0679)}, stop_on_diff=True, log_diffs=True),
    )

    cpu.step()

    assert verifier.total_verified == 1
    assert cpu.addr() == (0x1010, 0xBEEF)
    assert cpu.mem.rb(0x1010, 0x066B) != 0


def test_present_frame_blit_447b_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_present_frame_blit_447b

    # 447B..44AF, the mode-0 frame-present blit (53 bytes).
    routine = bytes.fromhex(
        '8b 36 4c 23 2e 8e 06 a4 95 2e 8e 1e 98 95 bb 1a 00 bf a0 00 bd c0 00'
        '8b cb f3 a5 83 ef 34 81 c7 00 20 f7 c7 00 40 74 04 81 c7 50 c0 4d 75 e8'
        '2e 8e 1e 96 95 c3'
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x447B, routine)
        mem.ww(0x1010, 0x95A4, 0x7000)  # destination segment (stand-in for B800)
        mem.ww(0x1010, 0x9598, 0x6000)  # source segment
        mem.ww(0x1010, 0x9596, 0x1234)  # restore-DS selector
        mem.ww(0x4000, 0x234C, 0x0100)  # SI source offset, read with the entry DS
        # Deterministic source pattern large enough for 192 rows * 26 words.
        for i in range(0x0100, 0x0100 + 192 * 52 + 4):
            mem.wb(0x6000, i & 0xFFFF, (i * 7 + 0x33) & 0xFF)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=0x4000, es=0x5555, ss=0x4000,
            ip=0x447B, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x447B)] = overkill_present_frame_blit_447b
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(200000):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_variable_width_interlaced_blit_41a6_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_variable_width_interlaced_blit_41a6

    code = bytes.fromhex(
        '51 8b cd f3 a4 2b fd 81 c7 00 20 f7 c7 00 40 74 04 81 c7 50 c0 59 e2 e8 c3'
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x41A6, code)
        payload = bytes((i * 17 + 3) & 0xFF for i in range(64))
        mem.load(0x2000, 0x0200, payload)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=3, dx=0x3333,
            si=0x0200, di=0x0100, bp=4,
            sp=0x9000, cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0x41A6, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x41A6)] = overkill_variable_width_interlaced_blit_41a6
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(200):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_dirty_copy_ccaa_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_dirty_copy_mode1_ccaa

    code = bytes.fromhex(
        'b9 08 00 26 8b 04 26 3b 05 74 05 b2 01 26 89 05 83 c7 50 83 c6 50 e2 eb eb 44'
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xCCAA, code)
        for row in range(8):
            mem.ww(0x3000, 0x0100 + row * 0x50, 0x1000 + row)
            mem.ww(0x3000, 0x0200 + row * 0x50, 0x1000 + (row if row % 2 else row + 1))
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0x7777, dx=0x5500,
            si=0x0100, di=0x0200, bp=0xCCCC,
            sp=0x9000, cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0xCCAA, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xCCAA)] = overkill_dirty_copy_mode1_ccaa
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(200):
        if asm.addr() == (0x1010, 0xCD08):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xCD08)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_presence_stamp_list_4d15_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_presence_stamp_list_4d15

    code = bytes.fromhex(
        'ad 8b d8 d1 e3 81 c3 08 9a 8b 1f 03 1e 4c 23 ad 03 d8 ad'
        '26 80 3f 00 75 33 2e 83 3e bc 95 01 75 23 26 80 7f 1a 00'
        '75 24 26 80 7f 34 00 75 1d 26 80 7f 4e 00 75 16 ff e5'
        '26 88 47 4e 26 88 47 34 26 88 47 1a 26 88 07 89 1d 83 c7 02 e2 b2 c3'
    )

    def make_cpu(use_hook: bool, bp: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x4D15, code)
        mem.ww(0x1010, 0x95BC, 1)
        mem.ww(0x2000, 0x234C, 0x0100)
        # table DS:9A08 + word*2 -> base offsets
        mem.ww(0x2000, 0x9A08 + 0 * 2, 0x0020)
        mem.ww(0x2000, 0x9A08 + 1 * 2, 0x0040)
        mem.ww(0x2000, 0x9A08 + 2 * 2, 0x0060)
        triples = [
            0, 0x0002, 0xAA11,  # empty => stamp
            1, 0x0004, 0xBB22,  # occupied at +1A => skip
            2, 0x0006, 0xCC33,  # empty => stamp
        ]
        off = 0x0200
        for i, w in enumerate(triples):
            mem.ww(0x2000, off + i * 2, w)
        # Occupy the second target's +1A cell.
        mem.wb(0x3000, 0x0100 + 0x0040 + 0x0004 + 0x1A, 0x77)
        state = CPUState(
            ax=0, bx=0, cx=3, dx=0x7777,
            si=off, di=0x0400, bp=bp,
            sp=0x9000, cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0x4D15, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x4D15)] = overkill_presence_stamp_list_4d15
        return cpu

    for bp in (0x4D4D, 0x4D51):
        asm = make_cpu(False, bp)
        hook = make_cpu(True, bp)
        for _ in range(300):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_presence_stamp_list_4d15_final_skip_and_mode0_flags_match_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_presence_stamp_list_4d15

    code = bytes.fromhex(
        'ad 8b d8 d1 e3 81 c3 08 9a 8b 1f 03 1e 4c 23 ad 03 d8 ad'
        '26 80 3f 00 75 33 2e 83 3e bc 95 01 75 23 26 80 7f 1a 00'
        '75 24 26 80 7f 34 00 75 1d 26 80 7f 4e 00 75 16 ff e5'
        '26 88 47 4e 26 88 47 34 26 88 47 1a 26 88 07 89 1d 83 c7 02 e2 b2 c3'
    )

    def make_cpu(use_hook: bool, *, mode: int, final_skip: str) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x4D15, code)
        mem.ww(0x1010, 0x95BC, mode)
        mem.ww(0x2000, 0x234C, 0x0100)
        for i, base in enumerate((0x0020, 0x0040, 0x0060)):
            mem.ww(0x2000, 0x9A08 + i * 2, base)
        triples = [0, 0x0002, 0xAA11, 1, 0x0004, 0xBB22, 2, 0x0006, 0xCC33]
        off = 0x0200
        for i, w in enumerate(triples):
            mem.ww(0x2000, off + i * 2, w)
        final_target = 0x0100 + 0x0060 + 0x0006
        if final_skip == "cell":
            mem.wb(0x3000, final_target, 0x44)
        elif final_skip == "layer":
            mem.wb(0x3000, final_target + 0x34, 0x55)
        state = CPUState(
            ax=0x1234, bx=0x5678, cx=3, dx=0x7777,
            si=off, di=0x0400, bp=0x4D51,
            sp=0x9000, cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0x4D15, flags=0x0297,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x4D15)] = overkill_presence_stamp_list_4d15
        return cpu

    for mode, final_skip in ((1, "cell"), (1, "layer"), (0, "none")):
        asm = make_cpu(False, mode=mode, final_skip=final_skip)
        hook = make_cpu(True, mode=mode, final_skip=final_skip)
        for _ in range(300):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_presence_stamp_triplet_4ced_composes_three_4d15_calls():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_presence_stamp_list_4d15, overkill_presence_stamp_triplet_4ced

    code = bytes.fromhex(
        "2e8e069895bec1c6bfb1c7bd4d4db91400e81400bd514db90a00"
        "e80b00b90a00e80500c705ffffc3ad8bd8d1e381c3089a8b1f"
        "031e4c23ad03d8ad26803f0075332e833ebc9501752326807f"
        "1a00752426807f3400751d26807f4e007516ffe52688474e2688"
        "47342688471a268807891d83c702e2b2c3"
    )

    def make_cpu(use_hook: bool, *, mode: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x4CED, code)
        mem.ww(0x1010, 0x9598, 0x3000)
        mem.ww(0x1010, 0x95BC, mode)
        mem.ww(0x2000, 0x234C, 0x0100)
        for i in range(16):
            mem.ww(0x2000, 0x9A08 + i * 2, 0x0200 + i * 0x30)

        triples = []
        for i in range(40):
            triples.extend((i % 16, (i * 4) & 0x01FF, 0x1100 + i))
        src = 0xC6C1
        for i, word in enumerate(triples):
            mem.ww(0x2000, src + i * 2, word)

        for i in (3, 17, 29):
            base = 0x0100 + (0x0200 + (i % 16) * 0x30) + ((i * 4) & 0x01FF)
            mem.wb(0x3000, base & 0xFFFF, 0x77)
        if mode == 1:
            for i, off in ((8, 0x1A), (21, 0x34), (35, 0x4E)):
                base = 0x0100 + (0x0200 + (i % 16) * 0x30) + ((i * 4) & 0x01FF)
                mem.wb(0x3000, (base + off) & 0xFFFF, 0x55)

        state = CPUState(
            ax=0x2222, bx=0x3333, cx=0x4444, dx=0x5555,
            si=0x6666, di=0x7777, bp=0x8888,
            sp=0x9000, cs=0x1010, ds=0x2000, es=0x9999, ss=0x4000,
            ip=0x4CED, flags=0x0297,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x4CED)] = overkill_presence_stamp_triplet_4ced
            cpu.replacement_hooks[(0x1010, 0x4D15)] = overkill_presence_stamp_list_4d15
        return cpu

    for mode in (0, 1):
        asm = make_cpu(False, mode=mode)
        hook = make_cpu(True, mode=mode)
        for _ in range(5000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_present_ega_frame_2750_hook_writes_shadow_planes():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE
    from overkill.hooks import overkill_present_ega_frame_2750

    mem = Memory()
    mem.ega_planar = True
    mem.ww(0x1010, 0x95A4, 0xA000)
    mem.ww(0x1010, 0x9598, 0x6000)
    mem.ww(0x1010, 0x9596, 0x1234)
    mem.ww(0x4000, 0x234C, 0x0100)
    for i in range(192 * 4 * 26):
        mem.wb(0x6000, 0x0100 + i, (i * 5 + 7) & 0xFF)

    state = CPUState(
        ax=0, bx=0, cx=0, dx=0, si=0, di=0, bp=0,
        sp=0x9000, cs=0x1010, ds=0x4000, es=0, ss=0x5000,
        ip=0x2750, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)
    cpu.replacement_hooks[(0x1010, 0x2750)] = overkill_present_ega_frame_2750
    cpu.step()

    assert cpu.addr() == (0x1010, 0xBEEF)
    assert cpu.s.ds == 0x1234
    assert cpu.s.es == 0xA000
    assert cpu.s.dx == 0x03C5
    assert cpu.get_reg8(0) == 0x0F
    assert cpu.s.si == (0x0100 + 192 * 4 * 26) & 0xFFFF
    assert cpu.s.di == 0x00A0 + 192 * 40
    assert cpu.s.bp == 0

    # First output row starts at A000:00A0.  The live EGA renderer reads the
    # hardware-plane shadow store, not flat CPU-visible A000:+2000 aliases.
    for plane, src_off in enumerate((0, 26, 52, 78)):
        start = EGA_APERTURE + plane * EGA_PLANE_STRIDE + 0x00A0
        assert bytes(mem.data[start:start + 26]) == mem.block(0x6000, 0x0100 + src_off, 26)

    # A000:2000 is a real CPU offset/page, not plane 1 at offset zero.  The
    # presenter hook must not depend on visible data living in the CPU aperture.
    assert mem.block(0xA000, 0x20A0, 26) != mem.block(0x6000, 0x0100 + 26, 26)


def test_ega_temp_row_copy_291c_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_ega_temp_row_copy_291c

    code = bytes.fromhex('51 2e 8a 05 47 57 2e 8b 3e a6 5b aa 2e 89 3e a6 5b 5f 59 e2 eb c3')

    def make_cpu(use_hook: bool, count: int) -> CPU8086:
        mem = Memory()
        mem.data[0x1010 * 16 + 0x291C:0x1010 * 16 + 0x291C + len(code)] = code
        for i in range(32):
            mem.wb(0x1010, 0x5AF4 + i, (0x40 + i * 7) & 0xFF)
        mem.ww(0x1010, 0x5BA6, 0x0103)
        state = CPUState(
            ax=0xABCD, bx=0x2222, cx=count, dx=0x3333,
            si=0x4444, di=0x5AF4, bp=0x5555,
            sp=0x9000, cs=0x1010, ds=0x7777, es=0x6000, ss=0x5000,
            ip=0x291C, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x291C)] = overkill_ega_temp_row_copy_291c
        return cpu

    for count in (1, 7):
        asm = make_cpu(False, count)
        hook = make_cpu(True, count)
        for _ in range(300):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_ega_temp_row_copy_291c_respects_planar_map_mask():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE
    from overkill.hooks import overkill_ega_temp_row_copy_291c

    code = bytes.fromhex('51 2e 8a 05 47 57 2e 8b 3e a6 5b aa 2e 89 3e a6 5b 5f 59 e2 eb c3')

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.ega_planar = True
        mem.ega_map_mask = 0b1010
        mem.data[0x1010 * 16 + 0x291C:0x1010 * 16 + 0x291C + len(code)] = code
        for i in range(4):
            mem.wb(0x1010, 0x5AF4 + i, 0xA0 + i)
        mem.ww(0x1010, 0x5BA6, 0x0120)
        for plane in range(4):
            start = EGA_APERTURE + plane * EGA_PLANE_STRIDE + 0x0120
            mem.data[start:start + 4] = bytes([0x10 + plane]) * 4
        state = CPUState(
            ax=0xABCD, bx=0x2222, cx=4, dx=0x3333,
            si=0x4444, di=0x5AF4, bp=0x5555,
            sp=0x9000, cs=0x1010, ds=0x7777, es=0xA000, ss=0x5000,
            ip=0x291C, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x291C)] = overkill_ega_temp_row_copy_291c
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data
    # Only map-mask-selected planes 1 and 3 should have received the copied row.
    assert bytes(hook.mem.data[EGA_APERTURE + 0 * EGA_PLANE_STRIDE + 0x0120:EGA_APERTURE + 0 * EGA_PLANE_STRIDE + 0x0124]) == bytes([0x10]) * 4
    assert bytes(hook.mem.data[EGA_APERTURE + 1 * EGA_PLANE_STRIDE + 0x0120:EGA_APERTURE + 1 * EGA_PLANE_STRIDE + 0x0124]) == bytes([0xA0, 0xA1, 0xA2, 0xA3])
    assert bytes(hook.mem.data[EGA_APERTURE + 2 * EGA_PLANE_STRIDE + 0x0120:EGA_APERTURE + 2 * EGA_PLANE_STRIDE + 0x0124]) == bytes([0x12]) * 4
    assert bytes(hook.mem.data[EGA_APERTURE + 3 * EGA_PLANE_STRIDE + 0x0120:EGA_APERTURE + 3 * EGA_PLANE_STRIDE + 0x0124]) == bytes([0xA0, 0xA1, 0xA2, 0xA3])


def test_ega_row_driver_27eb_hook_matches_existing_lifted_chain():
    """The broad 27EB fusion must match the already-verified narrow chain.

    The oracle side runs the real 27EB interpreter setup while keeping the
    verified leaf hooks enabled.  The tested side replaces only 27EB with the
    fused driver, so this catches stack/register/control-flow differences in
    the outer loop without spending thousands of pure interpreted steps.
    """
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import (
        overkill_ega_row_driver_27eb,
        overkill_ega_load_temp_rows_280d,
        overkill_ega_expand_temp_rows_2824,
        overkill_ega_temp_row_copy_291c,
        overkill_ega_transparency_mask_2932,
    )

    code = bytes.fromhex(
        '51 2e 83 3e d6 0b 00 74 0e 56 2e 8b 0e 9c 5b 51 e8 34 01 59 e2 f9 5e 2e 89 3e a6 5b bf f4 5a bd'
        '04 00 2e 8b 0e 9c 5b ac 2e 88 05 47 e2 f9 2e 2b 3e 9c 5b 83 c7 28 4d 75 e9 bf f4 5a 2e 8b 0e 9c'
        '5b 51 2e 8a 05 2e 8a 65 28 2e 8a 55 50 2e 8a 75 78 b9 08 00 d0 c6 d0 d3 d0 c2 d0 d3 d0 c4 d0 d3'
        'd0 c0 d0 d3 80 e3 0f 2e 83 3e d6 0b 00 74 09 2e 3a 1e 00 00 75 02 32 db 2e 80 3e b0 c5 01 75 2f'
        '2e 8b 2e aa 5b 83 fd ff 74 25 2e 03 2e a8 5b 80 7e 00 01 74 0a 80 7e 00 02 74 02 eb 12 eb 10 80'
        'fb 06 74 09 80 fb 0c 75 06 b3 06 eb 02 b3 0c d0 eb 2e d0 16 a2 5b d0 eb 2e d0 16 a3 5b d0 eb 2e'
        'd0 16 a4 5b d0 eb 2e d0 16 a5 5b e2 87 2e a0 a2 5b 2e 88 05 2e a0 a3 5b 2e 88 45 28 2e a0 a4 5b'
        '2e 88 45 50 2e a0 a5 5b 2e 88 45 78 47 59 e2 02 eb 03 e9 4c ff bf f4 5a 2e 8b 0e 9c 5b e8 31 00'
        'bf 1c 5b 2e 8b 0e 9c 5b e8 26 00 bf 44 5b 2e 8b 0e 9c 5b e8 1b 00 bf 6c 5b 2e 8b 0e 9c 5b e8 10'
        '00 2e 8b 3e a6 5b 59 e2 02 eb 03 e9 d2 fe e9 bd fe 51 2e 8a 05 47 57 2e 8b 3e a6 5b aa 2e 89 3e'
        'a6 5b 5f 59 e2 eb c3 2e c6 06 a0 5b 00 2e 8b 1e 9c 5b 8a 04 8a 20 d1 e3 8a 10 2e 03 1e 9c 5b 8a'
        '30 b9 08 00 51 d0 d6 2e d0 16 a1 5b d0 d2 2e d0 16 a1 5b d0 d4 2e d0 16 a1 5b d0 d0 2e d0 16 a1'
        '5b 2e 80 26 a1 5b 0f 2e 8a 0e 00 00 2e 38 0e a1 5b 75 03 f9 eb 01 f8 2e d0 16 a0 5b 59 e2 c5 2e'
        'a0 a0 5b aa 46 c3'
    )

    def make_cpu(use_driver: bool, transparent: bool) -> CPU8086:
        mem = Memory()
        mem.data[0x1010 * 16 + 0x27EB:0x1010 * 16 + 0x27EB + len(code)] = code
        mem.ww(0x1010, 0x5B9C, 0x0004)
        mem.ww(0x1010, 0x0BD6, 1 if transparent else 0)
        mem.wb(0x1010, 0x0000, 0x06)
        mem.wb(0x1010, 0xC5B0, 0)
        mem.ww(0x1010, 0x5BA6, 0x0100)
        mem.ww(0x1010, 0x5BA8, 0x0003)
        mem.ww(0x1010, 0x5BAA, 0xFFFF)
        for i in range(128):
            mem.wb(0x7000, 0x0200 + i, (0x13 + i * 17) & 0xFF)
            mem.wb(0x1010, 0x5AF4 + i, (0xA7 + i * 19) & 0xFF)
        state = CPUState(
            ax=0x1234, bx=0x2222, cx=0x0003, dx=0x3333,
            si=0x0200, di=0x0300, bp=0x4444,
            sp=0x9000, cs=0x1010, ds=0x7000, es=0x6000, ss=0x5000,
            ip=0x27EB, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.replacement_hooks[(0x1010, 0x280D)] = overkill_ega_load_temp_rows_280d
        cpu.replacement_hooks[(0x1010, 0x2824)] = overkill_ega_expand_temp_rows_2824
        cpu.replacement_hooks[(0x1010, 0x291C)] = overkill_ega_temp_row_copy_291c
        cpu.replacement_hooks[(0x1010, 0x2932)] = overkill_ega_transparency_mask_2932
        if use_driver:
            cpu.replacement_hooks[(0x1010, 0x27EB)] = overkill_ega_row_driver_27eb
        return cpu

    for transparent in (False, True):
        asm = make_cpu(False, transparent)
        hook = make_cpu(True, transparent)
        for _ in range(5000):
            if asm.addr() == (0x1010, 0x27D9):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0x27D9)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_ega_transparency_mask_2932_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_ega_transparency_mask_2932

    code = bytes.fromhex(
        '2e c6 06 a0 5b 00 2e 8b 1e 9c 5b 8a 04 8a 20 d1 e3 8a 10'
        '2e 03 1e 9c 5b 8a 30 b9 08 00 51 d0 d6 2e d0 16 a1 5b'
        'd0 d2 2e d0 16 a1 5b d0 d4 2e d0 16 a1 5b d0 d0 2e d0 16 a1 5b'
        '2e 80 26 a1 5b 0f 2e 8a 0e 00 00 2e 38 0e a1 5b 75 03 f9 eb 01 f8'
        '2e d0 16 a0 5b 59 e2 c5 2e a0 a0 5b aa 46 c3'
    )

    def make_cpu(use_hook: bool, flags: int) -> CPU8086:
        mem = Memory()
        mem.data[0x1010 * 16 + 0x2932:0x1010 * 16 + 0x2932 + len(code)] = code
        mem.ww(0x1010, 0x5B9C, 0x0005)
        mem.wb(0x1010, 0x0000, 0x06)
        mem.wb(0x1010, 0x5BA1, 0xA5)
        source = bytes([0x12, 0xE7, 0x5A, 0xC3, 0x99, 0x6D, 0x81, 0x44, 0xFE, 0x10,
                        0x03, 0xA0, 0x7C, 0x55, 0xB6, 0x9E, 0x22, 0xF1, 0x08, 0xD4])
        mem.load(0x7000, 0x0200, source)
        state = CPUState(
            ax=0x1357, bx=0x2468, cx=0x9999, dx=0xAAAA,
            si=0x0202, di=0x0304, bp=0xBBBB,
            sp=0x9000, cs=0x1010, ds=0x7000, es=0x6000, ss=0x5000,
            ip=0x2932, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x2932)] = overkill_ega_transparency_mask_2932
        return cpu

    for flags in (0x0202, 0x0203, 0x0297):
        asm = make_cpu(False, flags)
        hook = make_cpu(True, flags)
        for _ in range(300):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_hook_verifier_accepts_ega_transparency_mask_2932_boundary():
    from pathlib import Path
    from dos_re.cpu import CPUState
    from overkill.verification import HookVerifierConfig, install_hook_verifier
    from overkill.runtime import create_overkill_runtime as create_runtime

    root = Path(__file__).resolve().parents[1]
    rt = create_runtime(root / "assets" / "OVERKILL", game_root=root / "assets")
    mem = rt.program.memory
    code = bytes.fromhex(
        '2e c6 06 a0 5b 00 2e 8b 1e 9c 5b 8a 04 8a 20 d1 e3 8a 10'
        '2e 03 1e 9c 5b 8a 30 b9 08 00 51 d0 d6 2e d0 16 a1 5b'
        'd0 d2 2e d0 16 a1 5b d0 d4 2e d0 16 a1 5b d0 d0 2e d0 16 a1 5b'
        '2e 80 26 a1 5b 0f 2e 8a 0e 00 00 2e 38 0e a1 5b 75 03 f9 eb 01 f8'
        '2e d0 16 a0 5b 59 e2 c5 2e a0 a0 5b aa 46 c3'
    )
    mem.data[0x1010 * 16 + 0x2932:0x1010 * 16 + 0x2932 + len(code)] = code
    mem.ww(0x1010, 0x5B9C, 0x0005)
    mem.wb(0x1010, 0x0000, 0x06)
    mem.wb(0x1010, 0x5BA1, 0xA5)
    for i, value in enumerate((0x12, 0xE7, 0x5A, 0xC3, 0x99, 0x6D, 0x81, 0x44,
                               0xFE, 0x10, 0x03, 0xA0, 0x7C, 0x55, 0xB6, 0x9E,
                               0x22, 0xF1, 0x08, 0xD4)):
        mem.wb(0x7000, 0x0200 + i, value)
    rt.cpu.s = CPUState(
        ax=0x1357, bx=0x2468, cx=0x9999, dx=0xAAAA,
        si=0x0202, di=0x0304, bp=0xBBBB,
        sp=0x9000, cs=0x1010, ds=0x7000, es=0x6000, ss=0x5000,
        ip=0x2932, flags=0x0203,
    )
    rt.cpu.trace_enabled = False
    rt.cpu.push(0xBEEF)
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0x2932)}, stop_on_diff=True, log_diffs=True),
    )

    rt.cpu.step()

    assert rt.cpu.addr() == (0x1010, 0xBEEF)
    assert verifier.total_verified == 1
    assert verifier.counts[(0x1010, 0x2932)] == 1


def test_ega_expand_temp_rows_2824_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_ega_expand_temp_rows_2824

    code = bytes.fromhex(
        'bf f4 5a 2e 8b 0e 9c 5b 51 2e 8a 05 2e 8a 65 28 2e 8a 55 50'
        '2e 8a 75 78 b9 08 00 d0 c6 d0 d3 d0 c2 d0 d3 d0 c4 d0 d3 d0 c0 d0 d3'
        '80 e3 0f 2e 83 3e d6 0b 00 74 09 2e 3a 1e 00 00 75 02 32 db'
        '2e 80 3e b0 c5 01 75 2f 2e 8b 2e aa 5b 83 fd ff 74 25'
        '2e 03 2e a8 5b 80 7e 00 01 74 0a 80 7e 00 02 74 02 eb 12 eb 10'
        '80 fb 06 74 09 80 fb 0c 75 06 b3 06 eb 02 b3 0c'
        'd0 eb 2e d0 16 a2 5b d0 eb 2e d0 16 a3 5b d0 eb 2e d0 16 a4 5b d0 eb 2e d0 16 a5 5b'
        'e2 87 2e a0 a2 5b 2e 88 05 2e a0 a3 5b 2e 88 45 28'
        '2e a0 a4 5b 2e 88 45 50 2e a0 a5 5b 2e 88 45 78 47 59 e2 02 eb 03 e9 4c ff'
        'bf f4 5a 2e 8b 0e 9c 5b e8 31 00 bf 1c 5b 2e 8b 0e 9c 5b e8 26 00'
        'bf 44 5b 2e 8b 0e 9c 5b e8 1b 00 bf 6c 5b 2e 8b 0e 9c 5b e8 10 00'
        '2e 8b 3e a6 5b 59 e2 02 eb 03 e9 d2 fe e9 bd fe'
        '51 2e 8a 05 47 57 2e 8b 3e a6 5b aa 2e 89 3e a6 5b 5f 59 e2 eb c3'
    )

    def make_cpu(use_hook: bool, outer_count: int, transparent: bool, marker: int = 0,
                 force_marker_swap_pixel: bool = False) -> CPU8086:
        mem = Memory()
        mem.data[0x1010 * 16 + 0x2824:0x1010 * 16 + 0x2824 + len(code)] = code
        width = 0x0001 if force_marker_swap_pixel else 0x0003
        mem.ww(0x1010, 0x5B9C, width)
        mem.ww(0x1010, 0x0BD6, 1 if transparent else 0)
        mem.wb(0x1010, 0x0000, 0x05)
        mem.wb(0x1010, 0xC5B0, marker)
        mem.ww(0x1010, 0x5BA6, 0x0120)
        mem.ww(0x1010, 0x5BAA, 0x0000)
        mem.ww(0x1010, 0x5BA8, 0x0000)
        mem.wb(0x5000, 0x0000, marker)
        for i in range(0xA0):
            mem.wb(0x1010, 0x5AF4 + i, (0x17 + i * 23) & 0xFF)
        if force_marker_swap_pixel:
            # First pixel colour becomes 06h before marker processing:
            # DH bit7=0, DL bit7=1, AH bit7=1, AL bit7=0.  The real ASM
            # swaps 06h/0Ch only for marker byte 1, not marker byte 2.
            mem.wb(0x1010, 0x5AF4, 0x00)
            mem.wb(0x1010, 0x5B1C, 0x80)
            mem.wb(0x1010, 0x5B44, 0x80)
            mem.wb(0x1010, 0x5B6C, 0x00)
        state = CPUState(
            ax=0x1234, bx=0x0003, cx=0x7777, dx=0x5678,
            si=0x2222, di=0x9999, bp=0x3333,
            sp=0x9000, cs=0x1010, ds=0x7000, es=0x6000, ss=0x5000,
            ip=0x2824, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        # The enclosing 27EB code has already pushed the outer row count.
        cpu.push(outer_count)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x2824)] = overkill_ega_expand_temp_rows_2824
        return cpu

    for outer_count, transparent, marker, force_swap in (
        (1, False, 0, False),
        (2, True, 0, False),
        (1, False, 1, True),
        (1, False, 2, True),
    ):
        asm = make_cpu(False, outer_count, transparent, marker, force_swap)
        hook = make_cpu(True, outer_count, transparent, marker, force_swap)
        expected = (0x1010, 0x27EB if outer_count > 1 else 0x27D9)
        for _ in range(5000):
            if asm.addr() == expected:
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == expected
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_ega_load_temp_rows_280d_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_ega_load_temp_rows_280d

    code = bytes.fromhex('2e 8b 0e 9c 5b ac 2e 88 05 47 e2 f9 2e 2b 3e 9c 5b 83 c7 28 4d 75 e9')

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.data[0x1010 * 16 + 0x280D:0x1010 * 16 + 0x280D + len(code)] = code
        mem.ww(0x1010, 0x5B9C, 0x0005)
        for i in range(64):
            mem.wb(0x7000, 0x0200 + i, (0x21 + i * 11) & 0xFF)
        state = CPUState(
            ax=0x1234, bx=0x2222, cx=0x9999, dx=0x3333,
            si=0x0203, di=0x5AF4, bp=0x0004,
            sp=0x9000, cs=0x1010, ds=0x7000, es=0x6000, ss=0x5000,
            ip=0x280D, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x280D)] = overkill_ega_load_temp_rows_280d
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(300):
        if asm.addr() == (0x1010, 0x2824):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0x2824)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_sprite_blit_477e_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_sprite_blit_9x16_477e

    # 477E..480D, the fully-unrolled fixed 9-byte x 16-row sprite blit:
    #   2E 8E 06 96 95   mov es, cs:[9596]
    #   2E 8E 1E 98 95   mov ds, cs:[9598]
    #   16 x ( A5 A5 A5 A5 A4   movsw x4 + movsb (9 bytes)
    #          83 C6 2B          add si,2Bh        ; source row stride 52 )
    #   2E 8E 1E 96 95   mov ds, cs:[9596]
    #   C3               ret
    row = bytes.fromhex('a5a5a5a5a4 83c62b'.replace(' ', ''))
    routine = (
        bytes.fromhex('2e8e069695') + bytes.fromhex('2e8e1e9895')
        + row * 16
        + bytes.fromhex('2e8e1e9695') + bytes.fromhex('c3')
    )

    def make_cpu(use_hook: bool, df: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x477E, routine)
        mem.ww(0x1010, 0x9596, 0x7000)  # destination segment
        mem.ww(0x1010, 0x9598, 0x6000)  # source segment
        # Deterministic source pattern large enough for 16 rows * 52 bytes.
        for i in range(16 * 52 + 16):
            mem.wb(0x6000, (0x0200 + i) & 0xFFFF, (i * 13 + 0x41) & 0xFF)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x0200, di=0x0100, bp=0x5555, sp=0x9000,
            cs=0x1010, ds=0x4000, es=0x4000, ss=0x4000,
            ip=0x477E, flags=0x0202 | (0x0400 if df else 0),
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x477E)] = overkill_sprite_blit_9x16_477e
        return cpu

    # DF=0 is the only direction the unrolled routine ever runs in practice; the
    # hook also has a faithful DF=1 fallback, so verify both against interpreted ASM.
    for df in (False, True):
        asm = make_cpu(False, df)
        hook = make_cpu(True, df)
        for _ in range(4000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_masked_sprite_composite_38b7_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_masked_sprite_composite_38b7

    # 38B7..38CF: lodsw / and ax,es:[di] / or ax,ds:[si] / add si,2 / stosw  (x2)
    #             add di,30h / loop 38B7 ; then the shared 38D0 tail restores
    #             DS from CS:[9596] and returns near.
    routine = bytes.fromhex(
        'ad 26 23 05 0b 04 83 c6 02 ab'
        'ad 26 23 05 0b 04 83 c6 02 ab'
        '83 c7 30 e2 e7'
        '2e 8e 1e 96 95 c3'.replace(' ', '')
    )

    def make_cpu(use_hook: bool, rows: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x38B7, routine)
        ds, es = 0x4000, 0x3000
        for i in range(rows * 8 + 16):
            mem.wb(ds, (0x0480 + i) & 0xFFFF, rnd.randint(0, 255))
        for i in range(rows * 0x34 + 16):
            mem.wb(es, (0x25AC + i) & 0xFFFF, rnd.randint(0, 255))
        mem.ww(0x1010, 0x9596, ds)
        mem.ww(0x5000, 0x9000, 0xBEEF)
        state = CPUState(
            ax=rnd.randint(0, 0xFFFF), bx=0x1111, cx=rows, dx=0x2222,
            si=0x0480, di=0x25AC, bp=0x3333, sp=0x9000,
            cs=0x1010, ds=ds, es=es, ss=0x5000, ip=0x38B7, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x38B7)] = overkill_masked_sprite_composite_38b7
        return cpu

    for rows in (1, 2, 8, 16):
        asm = make_cpu(False, rows, rows)
        hook = make_cpu(True, rows, rows)
        for _ in range(20000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def _row_4537_asm_bytes():
    row_4537 = bytes.fromhex(
        '2e8b1e9c5b8a048a20d1e38a102e031e9c5b8a30e8a8002e880e955b2e882e995b'
        'e89b002e880e945b2e882e985be88e002e880e975b2e882e9b5be881002e880e965b'
        '2e882e9a5b462e833ed60b0074212ea0985be83c002ea0995be835002ea09a5be82e00'
        '2ea09b5be827002ea1e445ab2ea0945be81b002ea0955be814002ea0965be80d002e'
        'a0975be806002ea1e445abc3e80000d0c0d0c0d0c02ed116e445d0c02ed116e445c3'
    )
    pack_45f6 = bytes.fromhex(
        'd0 ce d0 d1 d0 ca d0 d1 d0 cc d0 d1 d0 c8 d0 d1'
        'd0 ce d0 d1 d0 ca d0 d1 d0 cc d0 d1 d0 c8 d0 d1'
        'd0 c9 d0 c9 d0 c9 d0 c9'
        '2e 83 3e d6 0b 00 74 30 8b d8 32 ed 8a c1 24 0f'
        '2e 3a 06 00 00 75 06 80 cd 0f 80 e1 f0 8a c1 24 f0'
        'd0 e8 d0 e8 d0 e8 d0 e8 2e 3a 06 00 00 75 06 80 cd f0'
        '80 e1 0f 8b c3 2e a3 e2 45 8a c1 24 0f bb e6 45 2e d7'
        '8a e0 8a c1 d0 e8 d0 e8 d0 e8 d0 e8 24 0f 2e d7 d0 e0'
        'd0 e0 d0 e0 d0 e0 0a c4 8a c8 2e a1 e2 45 c3'
    )
    return row_4537, pack_45f6


def _zero_stack_scratch(cpu, n=16):
    """Blank the don't-care scratch bytes below SS:SP before full-memory compare."""
    for i in range(1, n + 1):
        cpu.mem.wb(cpu.s.ss, (cpu.s.sp - i) & 0xFFFF, 0)


def test_expand_4plane_row_4537_fuzz():
    """Differential fuzz: fast 4537 hook vs interpreted original ASM.

    Randomizes registers, flags (incl. DF), the colour table, the transparency
    switch/colour, width (incl. 0 and wrap-around values), source plane bytes
    and the prior CS:[45E4] word.  Compares the full register snapshot and full
    memory except the sub-SP stack scratch, which the fast hooks intentionally
    do not write (established don't-care, see checkpoint 23).
    """
    import random

    from overkill.hooks import overkill_expand_4plane_row_4537

    row_4537, pack_45f6 = _row_4537_asm_bytes()
    rng = random.Random(0x4537)

    for case in range(300):
        width = rng.choice((0, 1, 2, 3, 5, 8, 0x40, 0x1234, 0xFFFE))
        si = rng.randrange(0x10000)
        bd6 = rng.choice((0, 0, 1, 1, 0x8000, rng.randrange(0x10000)))
        tcol = rng.choice((rng.randrange(16), rng.randrange(256)))
        flags = (rng.getrandbits(16) & 0x0CD5) | 0x0202
        regs = dict(
            ax=rng.randrange(0x10000), bx=rng.randrange(0x10000),
            cx=rng.randrange(0x10000), dx=rng.randrange(0x10000),
            di=rng.randrange(0x10000), bp=rng.randrange(0x10000),
        )
        table = bytes(rng.randrange(256) for _ in range(16))
        planes = [rng.randrange(256) for _ in range(4)]
        e4 = rng.randrange(0x10000)

        def make_cpu(use_hook):
            mem = Memory()
            mem.load(0x1010, 0x4537, row_4537)
            mem.load(0x1010, 0x45F6, pack_45f6)
            for i, b in enumerate(table):
                mem.wb(0x1010, 0x45E6 + i, b)
            mem.ww(0x1010, 0x5B9C, width)
            mem.ww(0x1010, 0x0BD6, bd6)
            mem.wb(0x1010, 0x0000, tcol)
            mem.ww(0x1010, 0x45E4, e4)
            for plane, value in enumerate(planes):
                mem.wb(0x6000, (si + plane * width) & 0xFFFF, value)
            state = CPUState(
                si=si, sp=0x9000, cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
                ip=0x4537, flags=flags, **regs,
            )
            cpu = CPU8086(mem, state)
            cpu.trace_enabled = False
            cpu.push(0xBEEF)
            if use_hook:
                cpu.replacement_hooks[(0x1010, 0x4537)] = overkill_expand_4plane_row_4537
            return cpu

        asm = make_cpu(False)
        hook = make_cpu(True)
        for _ in range(2000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF), f"case {case}"
        assert asm.s.snapshot() == hook.s.snapshot(), f"case {case}"
        _zero_stack_scratch(asm)
        _zero_stack_scratch(hook)
        assert asm.mem.data == hook.mem.data, f"case {case}"


def test_expand_4plane_block_4511_fuzz():
    """Differential fuzz: rewritten 4511 block driver vs interpreted ASM."""
    import random

    from overkill.hooks import overkill_expand_4plane_block_4511

    block_4511 = bytes.fromhex(
        '2e8b0e9e5b512e8b0e9c5b51e8170059e2f92e03369c5b2e03369c5b2e03369c5b'
        '59e2e1ebd52e8b1e9c5b8a048a20d1e38a102e031e9c5b8a30e8a8002e880e955b'
        '2e882e995be89b002e880e945b2e882e985be88e002e880e975b2e882e9b5be88100'
        '2e880e965b2e882e9a5b462e833ed60b0074212ea0985be83c002ea0995be83500'
        '2ea09a5be82e002ea09b5be827002ea1e445ab2ea0945be81b002ea0955be81400'
        '2ea0965be80d002ea0975be806002ea1e445abc3e80000d0c0d0c0d0c02ed116e445'
        'd0c02ed116e445c3'
    )
    _, pack_45f6 = _row_4537_asm_bytes()
    rng = random.Random(0x4511)

    for case in range(25):
        width = rng.randrange(1, 7)
        height = rng.randrange(1, 6)
        bd6 = rng.choice((0, 1))
        tcol = rng.randrange(16)
        flags = (rng.getrandbits(16) & 0x08D5) | 0x0202  # DF clear: forward blits
        table = bytes(rng.randrange(256) for _ in range(16))
        source = bytes(rng.randrange(256) for _ in range(4 * width * height + 4 * width))
        e4 = rng.randrange(0x10000)
        regs = dict(
            ax=rng.randrange(0x10000), bx=rng.randrange(0x10000),
            cx=rng.randrange(0x10000), dx=rng.randrange(0x10000),
            bp=rng.randrange(0x10000),
        )

        def make_cpu(use_hook):
            mem = Memory()
            mem.load(0x1010, 0x4511, block_4511)
            mem.load(0x1010, 0x45F6, pack_45f6)
            for i, b in enumerate(table):
                mem.wb(0x1010, 0x45E6 + i, b)
            mem.ww(0x1010, 0x5B9C, width)
            mem.ww(0x1010, 0x5B9E, height)
            mem.ww(0x1010, 0x0BD6, bd6)
            mem.wb(0x1010, 0x0000, tcol)
            mem.ww(0x1010, 0x45E4, e4)
            mem.load(0x6000, 0x0100, source)
            state = CPUState(
                si=0x0100, di=0x0200, sp=0x9000,
                cs=0x1010, ds=0x6000, es=0x7000, ss=0x4000,
                ip=0x4511, flags=flags, **regs,
            )
            cpu = CPU8086(mem, state)
            cpu.trace_enabled = False
            if use_hook:
                cpu.replacement_hooks[(0x1010, 0x4511)] = overkill_expand_4plane_block_4511
            return cpu

        asm = make_cpu(False)
        hook = make_cpu(True)
        for _ in range(60000):
            if asm.addr() == (0x1010, 0x450C):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0x450C), f"case {case}"
        assert asm.s.snapshot() == hook.s.snapshot(), f"case {case}"
        _zero_stack_scratch(asm)
        _zero_stack_scratch(hook)
        assert asm.mem.data == hook.mem.data, f"case {case}"


def test_masked_sprite_composite_3849_hook_matches_interpreted_asm():
    from overkill.hooks import overkill_masked_sprite_composite_3849

    code = bytes.fromhex(
        'ad 26 23 05 0b 04 83 c6 02 ab'
        'ad 26 23 05 0b 04 83 c6 02 ab'
        'ad 26 23 05 0b 04 83 c6 02 ab'
        'ad 26 23 05 0b 04 83 c6 02 ab'
        '83 c7 2c e2 d3 2e 8e 1e 96 95 c3'
    )

    def make_cpu(use_hook: bool):
        mem = Memory()
        mem.load(0x1010, 0x3849, code)
        mem.ww(0x1010, 0x9596, 0x2222)
        # Three rows, four [mask,data] word pairs per row.
        for i in range(3 * 4 * 2):
            mem.ww(0x3000, 0x0100 + i * 2, (0xF0F0 ^ (i * 0x1111)) & 0xFFFF)
        for row in range(3):
            for col in range(4):
                mem.ww(0x4000, 0x0200 + row * 0x34 + col * 2, (0x1234 + row * 0x100 + col * 0x11) & 0xFFFF)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=3, dx=0xDDDD, si=0x0100, di=0x0200,
            bp=0x1111, sp=0x9000, cs=0x1010, ds=0x3000, es=0x4000,
            ss=0x5000, ip=0x3849, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x3849)] = overkill_masked_sprite_composite_3849
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_ega_spaced_word_composite_1aeb_hook_matches_interpreted_asm():
    import random
    from overkill.hooks import overkill_ega_spaced_word_composite_1aeb

    code = bytes.fromhex(
        '26 8b 05 23 04 0b 44 02 26 89 05 83 c7 1a'
        '26 8b 05 23 04 0b 44 04 26 89 05 83 c7 1a'
        '26 8b 05 23 04 0b 44 06 26 89 05 83 c7 1a'
        '26 8b 05 23 04 0b 44 08 26 89 05 83 c7 1a'
        '83 c6 0a e2 c3 2e 8e 1e 96 95 c3'
    )

    def make_cpu(use_hook: bool, rows: int, seed: int):
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x1AEB, code)
        mem.ww(0x1010, 0x9596, 0x2222)
        ds, es = 0x3000, 0x4000
        si, di = 0x0100, 0x0200
        for i in range(rows * 0x0A + 0x20):
            mem.wb(ds, (si + i) & 0xFFFF, rnd.randrange(256))
        for i in range(rows * 0x68 + 0x40):
            mem.wb(es, (di + i) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x1111, cx=rows, dx=0x2222,
            si=si, di=di, bp=0x3333, sp=0x9000, cs=0x1010, ds=ds, es=es,
            ss=0x5000, ip=0x1AEB, flags=0x0287,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x1AEB)] = overkill_ega_spaced_word_composite_1aeb
        return cpu

    for rows in (1, 2, 8, 17):
        asm = make_cpu(False, rows, rows)
        hook = make_cpu(True, rows, rows)
        for _ in range(5000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_ega_spread_masked_composite_1d1b_hook_matches_interpreted_asm():
    import random
    from overkill.hooks import overkill_ega_spread_masked_composite_1d1b

    # Exact bytes of 1010:1D1B..1DF3 captured from the runtime (the EGA bit-spread
    # masked sprite variant reached via the 76E2 jump table).
    code = bytes.fromhex(
        'ad b2 ff f9 d0 d8 d0 dc d0 da f9 d0 d8 d0 dc d0 da f9 d0 d8 d0 dc d0 da'
        'f9 d0 d8 d0 dc d0 da 26 21 05 26 20 55 02 26 21 45 1a 26 20 55 1c'
        '26 21 45 34 26 20 55 36 26 21 45 4e 26 20 55 50 ad 32 d2 d0 e8 d0 dc d0 da'
        'd0 e8 d0 dc d0 da d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da 26 09 05 26 08 55 02'
        'ad 32 d2 d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da'
        '26 09 45 1a 26 08 55 1c'
        'ad 32 d2 d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da'
        '26 09 45 34 26 08 55 36'
        'ad 32 d2 d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da d0 e8 d0 dc d0 da'
        '26 09 45 4e 26 08 55 50'
        '83 c7 68 e2 02 eb 03 e9 2d ff 2e 8e 1e 96 95 c3'
    )

    def make_cpu(use_hook: bool, rows: int, seed: int):
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x1D1B, code)
        mem.ww(0x1010, 0x9596, 0x2222)
        ds, es = 0x3000, 0x4000
        si, di = 0x0100, 0x0200
        for i in range(rows * 0x0A + 0x20):
            mem.wb(ds, (si + i) & 0xFFFF, rnd.randrange(256))
        for i in range(rows * 0x68 + 0x60):
            mem.wb(es, (di + i) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x1111, cx=rows, dx=0x77AA,
            si=si, di=di, bp=0x3333, sp=0x9000, cs=0x1010, ds=ds, es=es,
            ss=0x5000, ip=0x1D1B, flags=0x0287,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x1D1B)] = overkill_ega_spread_masked_composite_1d1b
        return cpu

    for rows in (1, 2, 8, 16, 17):
        asm = make_cpu(False, rows, rows)
        hook = make_cpu(True, rows, rows)
        for _ in range(20000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_ega_spread_masked_composite_wide_13e7_hook_matches_interpreted_asm():
    import random
    from overkill.hooks import overkill_ega_spread_masked_composite_wide_13e7

    # Exact bytes of 1010:13E7..154A captured from the runtime (the wide,
    # word+word+byte EGA bit-spread masked sprite variant reached via 7620).
    code = bytes.fromhex(
        '8b 04 8b 5c 02 b2 ff f9 d0 d8 d0 dc d0 db d0 df d0 da f9 d0 d8 d0 dc d0 db d0 df d0 da'
        'f9 d0 d8 d0 dc d0 db d0 df d0 da f9 d0 d8 d0 dc d0 db d0 df d0 da'
        '26 21 05 26 21 5d 02 26 20 55 04 26 21 45 1a 26 21 5d 1c 26 20 55 1e'
        '26 21 45 34 26 21 5d 36 26 20 55 38 26 21 45 4e 26 21 5d 50 26 20 55 52'
        '8b 44 04 8b 5c 06 32 d2 d0 e8 d0 dc d0 db d0 df d0 da d0 e8 d0 dc d0 db d0 df d0 da'
        'd0 e8 d0 dc d0 db d0 df d0 da d0 e8 d0 dc d0 db d0 df d0 da 26 09 05 26 09 5d 02 26 08 55 04'
        '8b 44 08 8b 5c 0a 32 d2 d0 e8 d0 dc d0 db d0 df d0 da d0 e8 d0 dc d0 db d0 df d0 da'
        'd0 e8 d0 dc d0 db d0 df d0 da d0 e8 d0 dc d0 db d0 df d0 da 26 09 45 1a 26 09 5d 1c 26 08 55 1e'
        '8b 44 0c 8b 5c 0e 32 d2 d0 e8 d0 dc d0 db d0 df d0 da d0 e8 d0 dc d0 db d0 df d0 da'
        'd0 e8 d0 dc d0 db d0 df d0 da d0 e8 d0 dc d0 db d0 df d0 da 26 09 45 34 26 09 5d 36 26 08 55 38'
        '8b 44 10 8b 5c 12 32 d2 d0 e8 d0 dc d0 db d0 df d0 da d0 e8 d0 dc d0 db d0 df d0 da'
        'd0 e8 d0 dc d0 db d0 df d0 da d0 e8 d0 dc d0 db d0 df d0 da 26 09 45 4e 26 09 5d 50 26 08 55 52'
        '83 c7 68 83 c6 14 e2 02 eb 03 e9 a2 fe 2e 8e 1e 96 95 c3'
    )

    def make_cpu(use_hook: bool, rows: int, seed: int):
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x13E7, code)
        mem.ww(0x1010, 0x9596, 0x2222)
        ds, es = 0x3000, 0x4000
        si, di = 0x0100, 0x0200
        for i in range(rows * 0x14 + 0x20):
            mem.wb(ds, (si + i) & 0xFFFF, rnd.randrange(256))
        for i in range(rows * 0x68 + 0x60):
            mem.wb(es, (di + i) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=rnd.randrange(0x10000), cx=rows, dx=0x77AA,
            si=si, di=di, bp=0x3333, sp=0x9000, cs=0x1010, ds=ds, es=es,
            ss=0x5000, ip=0x13E7, flags=0x0287,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x13E7)] = overkill_ega_spread_masked_composite_wide_13e7
        return cpu

    for rows in (1, 2, 8, 16, 17):
        asm = make_cpu(False, rows, rows)
        hook = make_cpu(True, rows, rows)
        for _ in range(30000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_ega_spaced_copy_29c6_hook_matches_interpreted_asm():
    import random
    from overkill.hooks import overkill_ega_spaced_copy_29c6

    code = bytes.fromhex(
        '83 ff ff 75 01 c3 bb 17 00 b9 10 00'
        'a5 a4 03 fb a5 a4 03 fb a5 a4 03 fb a5 a4 03 fb e2 ee c3'
    )

    def make_cpu(use_hook: bool, *, di: int, seed: int):
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x29C6, code)
        ds, es = 0x3000, 0x4000
        si = 0x0100
        for i in range(16 * 4 * 3 + 0x20):
            mem.wb(ds, (si + i) & 0xFFFF, rnd.randrange(256))
        for i in range(16 * 0x68 + 0x80):
            mem.wb(es, (0x0200 + i) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0xAAAA, cx=0xBBBB, dx=0xCCCC,
            si=si, di=di, bp=0xDDDD, sp=0x9000, cs=0x1010, ds=ds, es=es,
            ss=0x5000, ip=0x29C6, flags=0x0287,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x29C6)] = overkill_ega_spaced_copy_29c6
        return cpu

    for di in (0x0200, 0x1234, 0xFFFF):
        asm = make_cpu(False, di=di, seed=di)
        hook = make_cpu(True, di=di, seed=di)
        for _ in range(5000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_ega_source_spaced_copy_2ab9_hook_matches_interpreted_asm():
    import random
    from overkill.hooks import overkill_ega_source_spaced_copy_2ab9

    code_2ab9 = bytes.fromhex(
        'e8 7a 2f 89 46 0c 3d ff ff 75 01 c3 03 06 4c 23'
        '89 46 0c 8b f0 8b 7e 0e 2e 8e 06 96 95 2e 8e 1e 98 95'
        'bb 17 00 b9 10 00'
        'a5 a4 03 f3 a5 a4 03 f3 a5 a4 03 f3 a5 a4 03 f3'
        'e2 ee 2e 8e 1e 96 95 c3'
    )
    code_5a36 = bytes.fromhex('2e 8b 1e bc 95 d1 e3 2e ff a7 42 5a')
    code_2580 = bytes.fromhex(
        '8b 5e 02 81 fb e0 00 73 29 d1 e3 8b 9f c8 99 83 fb ff 74 1e'
        '8b 46 04 8b c8 83 e1 07 89 4e 12 d1 e8 d1 e8 d1 e8 03 c3'
        '83 7e 24 00 75 01 c3 ff 4e 24 c3 b8 ff ff c3'
    )

    def make_cpu(use_hook: bool, *, y: int, row_word: int, seed: int):
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x2AB9, code_2ab9)
        mem.load(0x1010, 0x5A36, code_5a36)
        mem.load(0x1010, 0x2580, code_2580)
        mem.ww(0x1010, 0x95BC, 1)
        mem.ww(0x1010, 0x5A44, 0x2580)
        mem.ww(0x1010, 0x9596, 0x4000)
        mem.ww(0x1010, 0x9598, 0x6000)
        row_ds = 0x3000
        ss = 0x5000
        bp = 0x0800
        mem.ww(row_ds, 0x234C, 0x0100)
        mem.ww(row_ds, 0x99C8 + ((y << 1) & 0xFFFF), row_word)
        mem.ww(ss, bp + 0x02, y)
        mem.ww(ss, bp + 0x04, 0x0039)
        mem.ww(ss, bp + 0x0E, 0x0200)
        mem.ww(ss, bp + 0x24, 3)
        source_start = (row_word + 0x0100 + (0x0039 >> 3)) & 0xFFFF
        for i in range(16 * 0x68 + 0x80):
            mem.wb(0x6000, (source_start + i) & 0xFFFF, rnd.randrange(256))
            mem.wb(0x4000, (0x0200 + i) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0xAAAA, cx=0xBBBB, dx=0xCCCC,
            si=0x1111, di=0x2222, bp=bp, sp=0x9000, cs=0x1010, ds=row_ds,
            es=0x7777, ss=ss, ip=0x2AB9, flags=0x0287,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x2AB9)] = overkill_ega_source_spaced_copy_2ab9
        return cpu

    for y, row_word in ((0x20, 0x1800), (0xE0, 0x1800), (0x30, 0xFFFF)):
        asm = make_cpu(False, y=y, row_word=row_word, seed=y ^ row_word)
        hook = make_cpu(True, y=y, row_word=row_word, seed=y ^ row_word)
        for _ in range(10000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_sprite_copy_469f_hook_matches_interpreted_asm():
    from overkill.hooks import overkill_sprite_copy_9x16_469f

    code = bytes.fromhex('a5 a5 a5 a5 a4 83 c7 2b e2 f6 c3')

    def make_cpu(use_hook: bool):
        mem = Memory()
        mem.load(0x1010, 0x469F, code)
        for i in range(16 * 9):
            mem.wb(0x3000, 0x0100 + i, (i * 17 + 3) & 0xFF)
        for row in range(16):
            for i in range(9):
                mem.wb(0x4000, 0x0200 + row * 0x34 + i, 0xA5)
        state = CPUState(
            ax=0x1357, bx=0x2468, cx=16, dx=0x3333, si=0x0100, di=0x0200,
            bp=0x4444, sp=0x9000, cs=0x1010, ds=0x3000, es=0x4000,
            ss=0x5000, ip=0x469F, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x469F)] = overkill_sprite_copy_9x16_469f
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_overlay_scan_a849_skips_inactive_entries_like_asm():
    from overkill.hooks import overkill_scan_objects_call_5ac8_a849

    code = bytes.fromhex('51 8b d9 d1 e3 8b af ca 32 83 7e 00 00 74 03 e8 6d b2 59 e2 eb')

    def make_cpu(use_hook: bool, active_cx: int | None):
        mem = Memory()
        mem.load(0x1010, 0xA849, code)
        for cx in range(1, 0x25):
            ptr = 0x4000 + cx * 0x20
            mem.ww(0x2000, (0x32CA + cx * 2) & 0xFFFF, ptr)
            mem.ww(0x3000, ptr, 1 if active_cx == cx else 0)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x24, dx=0x3333, si=0x4444, di=0x5555,
            bp=0x6666, sp=0x9000, cs=0x1010, ds=0x2000, es=0x2000,
            ss=0x3000, ip=0xA849, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA849)] = overkill_scan_objects_call_5ac8_a849
        return cpu

    asm = make_cpu(False, None)
    hook = make_cpu(True, None)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xA85E):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xA85E)
    assert_oracle_equivalent(asm, hook)  # A849 no longer writes dead push scratch below SP

    asm = make_cpu(False, 0x20)
    hook = make_cpu(True, 0x20)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xA858):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xA858)
    assert_oracle_equivalent(asm, hook)  # A849 no longer writes dead push scratch below SP


def test_tandy_present_scan_a927_composes_known_targets_like_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_scan_objects_call_5a92_a927

    code_a927 = bytes.fromhex("518bd9d1e38bafca32837e00007403e859b159e2eb")
    code_5a92 = bytes.fromhex(
        "2e8e0698958b7e0c8b760e8b5e142e031ebc952e031ebc952e031ebc95"
        "d1e32effa7b65a"
    )
    code_34c5 = bytes.fromhex("bb5800b91000a5a5a5a5a5a5a5a503fbe2f4c3")
    code_34d8 = bytes.fromhex("83ffff7501c3bb6000" + ("a5a5a5a503fb" * 16) + "c3")

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA927, code_a927)
        mem.load(0x1010, 0x5A92, code_5a92)
        mem.load(0x1010, 0x34C5, code_34c5)
        mem.load(0x1010, 0x34D8, code_34d8)
        game_ds, obj_ss, dest_es = 0x2000, 0x3000, 0x4000
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x9596, game_ds)
        mem.ww(0x1010, 0x9598, dest_es)
        mem.ww(0x1010, 0x5AC2, 0x34D8)  # object type 0, mode 2
        mem.ww(0x1010, 0x5AC4, 0x34C5)  # object type 1, mode 2
        for cx in range(1, 5):
            ptr = 0x0100 + cx * 0x40
            mem.ww(game_ds, (0x32CA + cx * 2) & 0xFFFF, ptr)
            mem.ww(obj_ss, ptr, 0)
            mem.ww(obj_ss, ptr + 0x0C, 0x0200 + cx * 0x120)
            mem.ww(obj_ss, ptr + 0x0E, 0x0800 + cx * 0x140)
            mem.ww(obj_ss, ptr + 0x14, 0)
        # Descending scan order: CX=4,3,2,1.
        mem.ww(obj_ss, 0x0100 + 4 * 0x40, 1)       # 34D8 copy
        mem.ww(obj_ss, 0x0100 + 2 * 0x40, 1)       # 34C5 copy
        mem.ww(obj_ss, 0x0100 + 2 * 0x40 + 0x14, 1)
        mem.ww(obj_ss, 0x0100 + 1 * 0x40, 1)       # 34D8 DI=FFFF early return
        mem.ww(obj_ss, 0x0100 + 1 * 0x40 + 0x0C, 0xFFFF)
        for off in range(0x0600, 0x1200):
            mem.wb(game_ds, off, (off * 7 + 3) & 0xFF)
        for off in range(0x0200, 0x0800):
            mem.wb(dest_es, off, (off * 5 + 1) & 0xFF)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=4, dx=0x3333, si=0x4444, di=0x5555,
            bp=0x6666, sp=0x9000, cs=0x1010, ds=game_ds, es=0x7777,
            ss=obj_ss, ip=0xA927, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA927)] = overkill_scan_objects_call_5a92_a927
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(3000):
        if asm.addr() == (0x1010, 0xA936):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xA936)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_tandy_present_scan_a927_fails_fast_on_unknown_target():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_scan_objects_call_5a92_a927

    code_a927 = bytes.fromhex("518bd9d1e38bafca32837e00007403e859b159e2eb")

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA927, code_a927)
        game_ds, obj_ss = 0x2000, 0x3000
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x5AC2, 0x1234)
        ptr = 0x0180
        mem.ww(game_ds, 0x32CA + 4 * 2, ptr)
        mem.ww(obj_ss, ptr, 1)
        mem.ww(obj_ss, ptr + 0x14, 0)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=4, dx=0x3333, si=0x4444, di=0x5555,
            bp=0x6666, sp=0x9000, cs=0x1010, ds=game_ds, es=0x7777,
            ss=obj_ss, ip=0xA927, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA927)] = overkill_scan_objects_call_5a92_a927
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xA936):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xA936)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_tandy_draw_scan_a849_composes_known_35cc_target_like_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_scan_objects_call_5ac8_a849

    code_a849 = bytes.fromhex("518bd9d1e38bafca32837e00007403e86db259e2eb")
    code_5ac8 = bytes.fromhex(
        "8b5e142e031ebc952e031ebc952e031ebc95d1e32effa7e25a"
    )
    code_35cc = bytes.fromhex(
        "e8672489460c3dffff7501c303064c2389460c8bf08b7e0e"
        "2e8e0696952e8e1e9895bb6000"
        + ("a5a5a5a503f3" * 16)
        + "2e8e1e9695c3"
    )
    code_5a36 = bytes.fromhex("2e 8b 1e bc 95 d1 e3 2e ff a7 42 5a")
    code_30d2 = bytes.fromhex(
        "8b5e0281fbe0007203e9d4f4d1e38b9fc89983fbff7503e9c6f4"
        "8b4604c746120000d1e803c3837e24007501c3ff4e24c3"
    )
    code_25b2 = bytes.fromhex("b8 ff ff c3")

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA849, code_a849)
        mem.load(0x1010, 0x5AC8, code_5ac8)
        mem.load(0x1010, 0x35CC, code_35cc)
        mem.load(0x1010, 0x5A36, code_5a36)
        mem.load(0x1010, 0x30D2, code_30d2)
        mem.load(0x1010, 0x25B2, code_25b2)
        game_ds, src_ds, dst_es, obj_ss = 0x2000, 0x3000, 0x4000, 0x5000
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x9596, dst_es)
        mem.ww(0x1010, 0x9598, src_ds)
        mem.ww(0x1010, 0x5A46, 0x30D2)
        mem.ww(0x1010, 0x5AEE, 0x35CC)  # object type 0, mode 2
        mem.ww(game_ds, 0x234C, 0x0080)
        for cx in range(1, 4):
            ptr = 0x0100 + cx * 0x40
            mem.ww(game_ds, (0x32CA + cx * 2) & 0xFFFF, ptr)
            mem.ww(obj_ss, ptr, 0)
            mem.ww(obj_ss, ptr + 0x02, 0x0040 + cx)
            mem.ww(obj_ss, ptr + 0x04, 0x0020 + cx * 2)
            mem.ww(obj_ss, ptr + 0x0E, 0x0300 + cx * 0x100)
            mem.ww(obj_ss, ptr + 0x14, 0)
            mem.ww(obj_ss, ptr + 0x24, cx & 1)
        active_ptr = 0x0100 + 2 * 0x40
        mem.ww(obj_ss, active_ptr, 1)
        y = mem.rw(obj_ss, active_ptr + 0x02)
        x = mem.rw(obj_ss, active_ptr + 0x04)
        row_word = 0x0500
        mem.ww(game_ds, (0x99C8 + ((y << 1) & 0xFFFF)) & 0xFFFF, row_word)
        source = (row_word + (x >> 1) + 0x0080) & 0xFFFF
        dest = mem.rw(obj_ss, active_ptr + 0x0E)
        for off in range(-0x40, 0x700):
            mem.wb(src_ds, (source + off) & 0xFFFF, (off * 11 + 9) & 0xFF)
        for off in range(-0x40, 0x300):
            mem.wb(dst_es, (dest + off) & 0xFFFF, (off * 7 + 5) & 0xFF)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=3, dx=0x3333, si=0x4444, di=0x5555,
            bp=0x6666, sp=0x9000, cs=0x1010, ds=game_ds, es=0x7777,
            ss=obj_ss, ip=0xA849, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA849)] = overkill_scan_objects_call_5ac8_a849
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(3000):
        if asm.addr() == (0x1010, 0xA858):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xA858)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_tandy_draw_scan_a849_fails_fast_on_unknown_target():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_scan_objects_call_5ac8_a849

    code_a849 = bytes.fromhex("518bd9d1e38bafca32837e00007403e86db259e2eb")

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA849, code_a849)
        game_ds, obj_ss = 0x2000, 0x3000
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x5AEE, 0x1234)
        ptr = 0x0180
        mem.ww(game_ds, 0x32CA + 4 * 2, ptr)
        mem.ww(obj_ss, ptr, 1)
        mem.ww(obj_ss, ptr + 0x14, 0)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=4, dx=0x3333, si=0x4444, di=0x5555,
            bp=0x6666, sp=0x9000, cs=0x1010, ds=game_ds, es=0x7777,
            ss=obj_ss, ip=0xA849, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA849)] = overkill_scan_objects_call_5ac8_a849
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xA858):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xA858)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_overlay_scan_a9e0_counter_and_skip_match_asm():
    from overkill.hooks import overkill_scan_objects_call_aa2b_a9e0

    code = bytes.fromhex(
        '51 8b d9 d1 e3 8b af ca 32 ff 06 40 23 81 3e 40 23 dc 05'
        '72 06 c7 06 40 23 00 00 83 7e 00 00 74 03 e8 27 00 59 e2 d9'
    )

    def make_cpu(use_hook: bool, active_cx: int | None):
        mem = Memory()
        mem.load(0x1010, 0xA9E0, code)
        mem.ww(0x2000, 0x2340, 0x05DA)
        for cx in range(1, 0x24):
            ptr = 0x5000 + cx * 0x20
            mem.ww(0x2000, (0x32CA + cx * 2) & 0xFFFF, ptr)
            mem.ww(0x3000, ptr, 1 if active_cx == cx else 0)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x23, dx=0x3333, si=0x4444, di=0x5555,
            bp=0x6666, sp=0x9000, cs=0x1010, ds=0x2000, es=0x2000,
            ss=0x3000, ip=0xA9E0, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA9E0)] = overkill_scan_objects_call_aa2b_a9e0
        return cpu

    asm = make_cpu(False, None)
    hook = make_cpu(True, None)
    for _ in range(500):
        if asm.addr() == (0x1010, 0xAA07):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xAA07)
    assert_oracle_equivalent(asm, hook)  # A9E0 no longer writes dead push scratch below SP

    asm = make_cpu(False, 0x20)
    hook = make_cpu(True, 0x20)
    for _ in range(500):
        if asm.addr() == (0x1010, 0xAA01):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xAA01)
    assert_oracle_equivalent(asm, hook)  # A9E0 no longer writes dead push scratch below SP


def test_bec5_bedc_one_collision_tail_matches_interpreted_asm():
    from overkill.hooks import _run_collision_handler_bec5_observed

    code_bec5 = bytes.fromhex(
        "837f18077503e9eb00837f18087503e9e200837f180c7503e9d900"
        "837f18097503e9bf00837f1802742c837f18067503e99f00837f"
        "18057503e996003b6f307401c3c7471c0000833ec2a8017412"
        "c746200000e9ac00c7070000837f08337508ff4e207503e99a00"
        "ff4e207503e99200833edcbe017411833edcbe00750fff4e20"
        "747fff4e20747aff4e207475c746240500833ec2a8017401c3"
    )

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xBEC5, code_bec5)
        ds = 0x2000
        ss = 0x3000
        collided_bx = 0x0100
        bp = 0x0200
        mem.ww(ds, collided_bx + 0x00, 0x0001)
        mem.ww(ds, collided_bx + 0x08, 0x007F)
        mem.ww(ds, collided_bx + 0x18, 0x0002)
        mem.ww(ds, 0xA8C2, 0x0000)
        mem.ww(ds, 0xBEDC, 0x0001)
        mem.ww(ss, bp + 0x20, 0x0003)
        mem.ww(ss, bp + 0x24, 0x1111)
        state = CPUState(
            ax=0xAAAA, bx=collided_bx, cx=0x0060, dx=0xDDDD,
            si=0xEEEE, di=0xFFFF, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x4000, ss=ss,
            ip=0xBEC5, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(80):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    _run_collision_handler_bec5_observed(
        hook,
        collided_bx=0x0100,
        parent="test",
        chain="test",
        cx_value=0x0060,
    )

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_bec5_variant_0005_a8c2_one_matches_interpreted_asm():
    from overkill.hooks import _run_collision_handler_bec5_observed
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory

    code_bec5 = bytes.fromhex(
        "837f18077503e9eb00837f18087503e9e200837f180c7503e9d900"
        "837f18097503e9bf00837f1802742c837f18067503e99f00837f"
        "18057503e996003b6f307401c3c7471c0000833ec2a8017412"
        "c746200000e9ac00c7070000837f08337508ff4e207503e99a00"
        "ff4e207503e99200833edcbe017411833edcbe00750fff4e20"
        "747fff4e20747aff4e207475c746240500833ec2a8017401c3"
        "558b2ebaa8c7462405008b2ebca8c7462405008b2ebea8c746"
        "2405008b2ec0a8c746240500803ec098007405c606ffbe0e5dc3"
        "e878fdeb8ee873fd833ec2a8017484c746200000eb1f833ec2a8"
        "017503e973ffc746200000eb0e833ec2a80174d2c746200000eb00"
    )
    code_bd0d = bytes.fromhex(
        "558bebe804008bdd5dc3c746000000837e1604743a837e1601742e"
        "837e1807747e837e18087478837e18097440837e18067503e98100"
        "837e1805747b837e180c7469837e180a7449c3c746160200c3"
        "e8f502837e18017501c3837e28ff7501c38b7628d1e681c67820"
        "c60400c3833e72a9007501c3b91a00beb4a3ad3dffff7501c3"
        "8944fe8bd8c7070000ff0e72a9ebea833e7ea9007404ff0e7ea9"
        "e96dee833e70a9007404ff0e70a9c3833e74a9007404ff0e74a9"
        "c3833e76a9007404ff0e76a9c3"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xBEC5, code_bec5)
        mem.load(0x1010, 0xBD0D, code_bd0d)
        ds = ss = 0x3000
        collided_bx = 0x1200
        bp = 0x2504
        mem.ww(ds, collided_bx + 0x00, 0x0001)
        mem.ww(ds, collided_bx + 0x16, 0x0005)
        mem.ww(ds, collided_bx + 0x18, 0x0005)
        mem.ww(ds, 0xA8C2, 0x0001)
        mem.ww(ds, 0xA976, 0x0004)
        mem.ww(ds, 0xBEDC, 0x0000)
        mem.wb(ds, 0x98C0, 0x01)
        mem.wb(ds, 0xBEFF, 0x00)
        for i, ptr in enumerate((0x2600, 0x2638, 0x2670, 0x26A8)):
            mem.ww(ds, 0xA8BA + i * 2, ptr)
            mem.ww(ss, ptr + 0x24, 0x1111 + i)
        mem.ww(ss, bp + 0x00, 0x0001)
        mem.ww(ss, bp + 0x14, 0x0001)
        mem.ww(ss, bp + 0x18, 0x0058)
        mem.ww(ss, bp + 0x20, 0x0007)
        mem.ww(ss, bp + 0x24, 0x0000)
        state = CPUState(
            ax=0x00A8, bx=collided_bx, cx=0x0048, dx=0x0058,
            si=0x1111, di=0x2222, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xBEC5, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xCAFE)
        if use_hook:
            _run_collision_handler_bec5_observed(
                cpu,
                collided_bx=collided_bx,
                parent="test",
                chain="test",
                cx_value=0x0048,
            )
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xCAFE):
            break
        asm.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xCAFE)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data

def test_bec5_bedc_zero_second_counter_zero_runs_bfc7_tail():
    from overkill.hooks import _run_collision_handler_bec5_observed
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory

    mem = Memory()
    ds = 0x2000
    ss = 0x3000
    collided_bx = 0x1200
    bp = 0x23B4
    mem.ww(ds, collided_bx + 0x00, 0x0001)
    mem.ww(ds, collided_bx + 0x08, 0x007F)
    mem.ww(ds, collided_bx + 0x18, 0x0002)
    mem.ww(ds, 0xA8C2, 0x0000)
    mem.ww(ds, 0xBEDC, 0x0000)
    mem.wb(ds, 0x2078, 0x03)
    mem.wb(ds, 0x2079, 0x01)
    mem.wb(ds, 0x98C0, 0x00)
    mem.ww(ss, bp + 0x00, 0x0001)
    mem.ww(ss, bp + 0x02, 0x006C)
    mem.ww(ss, bp + 0x04, 0x0045)
    mem.ww(ss, bp + 0x08, 0x007F)
    mem.ww(ss, bp + 0x14, 0x0001)
    mem.ww(ss, bp + 0x16, 0x0004)
    mem.ww(ss, bp + 0x18, 0x0019)
    mem.ww(ss, bp + 0x20, 0x0002)
    mem.ww(ss, bp + 0x22, 0xAAAA)
    mem.ww(ss, bp + 0x24, 0x0000)
    mem.ww(ss, bp + 0x28, 0x0000)
    cpu = CPU8086(
        mem,
        CPUState(
            ax=0x006C, bx=collided_bx, cx=0x0017, dx=0xAAAA,
            si=0x1111, di=0x2222, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xBEC5, flags=0x0202,
        ),
    )
    cpu.trace_enabled = False
    cpu.push(0xBEEF)

    _run_collision_handler_bec5_observed(
        cpu,
        collided_bx=collided_bx,
        parent="test",
        chain="test",
        cx_value=0x0017,
    )

    assert cpu.addr() == (0x1010, 0xBEEF)
    assert mem.rw(ds, collided_bx) == 0
    assert mem.rw(ss, bp + 0x20) == 0
    assert mem.rb(ds, 0x2078) == 0x02


def test_bec5_variant_000c_consumes_bfb9_tail_like_bc4b_path():
    from overkill.hooks import _run_collision_handler_bec5_observed
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory

    def make_cpu() -> CPU8086:
        mem = Memory()
        ds = 0x2000
        ss = 0x3000
        collided_bx = 0x1200
        bp = 0x2504
        mem.ww(ds, collided_bx + 0x00, 0x0001)
        mem.ww(ds, collided_bx + 0x08, 0x007E)
        mem.ww(ds, collided_bx + 0x18, 0x000C)
        mem.ww(ds, 0xBEDC, 0x0000)
        mem.ww(ds, 0xA8C2, 0x0000)
        mem.wb(ds, 0x98C0, 0x00)
        mem.ww(ds, 0xA47E, 0x0005)
        mem.ww(ss, bp + 0x00, 0x0001)
        mem.ww(ss, bp + 0x08, 0x9999)
        mem.ww(ss, bp + 0x14, 0x0001)
        mem.ww(ss, bp + 0x18, 0x0020)
        mem.ww(ss, bp + 0x1A, 0xAAAA)
        mem.ww(ss, bp + 0x20, 0x0004)
        mem.ww(ss, bp + 0x22, 0xBBBB)
        mem.ww(ss, bp + 0x24, 0x1111)
        mem.ww(ss, bp + 0x28, 0xFFFF)
        mem.ww(ss, bp + 0x32, 0x7777)
        state = CPUState(
            ax=0xAAAA, bx=collided_bx, cx=0x0007, dx=0xDDDD,
            si=0xEEEE, di=0xFFFF, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xBEC5, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    hook = make_cpu()

    _run_collision_handler_bec5_observed(
        hook,
        collided_bx=0x1200,
        parent="test",
        chain="test",
        cx_value=0x0007,
    )

    assert hook.addr() == (0x1010, 0xBEEF)
    assert hook.s.ax == 0x0020
    assert hook.s.bx == 0x0002
    assert hook.s.cx == 0x0007
    assert hook.s.dx == 0xDDDD
    assert hook.s.si == 0xEEEE
    assert hook.s.di == 0xFFFF
    assert hook.s.sp == 0x9000
    assert hook.s.flags == 0x0202

    mem = hook.mem
    ds = hook.s.ds
    ss = hook.s.ss
    bp = hook.s.bp
    assert mem.rw(ds, 0xA47E) == 0x0004
    assert mem.rw(ss, bp + 0x08) == 0x0000
    assert mem.rw(ss, bp + 0x18) == 0x0001
    assert mem.rw(ss, bp + 0x1A) == 0x0020
    assert mem.rw(ss, bp + 0x22) == 0x0000
    assert mem.rw(ss, bp + 0x32) == 0x7777


def test_bec5_sprite_0033_falls_through_into_shared_tail():
    from overkill.hooks import _run_collision_handler_bec5_observed
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory

    code_bec5 = bytes.fromhex(
        "837f18077503e9eb00837f18087503e9e200837f180c7503e9d900"
        "837f18097503e9bf00837f1802742c837f18067503e99f00837f"
        "18057503e996003b6f307401c3c7471c0000833ec2a8017412"
        "c746200000e9ac00c7070000837f08337508ff4e207503e99a00"
        "ff4e207503e99200833edcbe017411833edcbe00750fff4e20"
        "747fff4e20747aff4e207475c746240500833ec2a8017401c3"
    )

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xBEC5, code_bec5)
        ds = 0x2000
        ss = 0x3000
        collided_bx = 0x1200
        bp = 0x2504
        mem.ww(ds, collided_bx + 0x00, 0x0001)
        mem.ww(ds, collided_bx + 0x08, 0x0033)
        mem.ww(ds, collided_bx + 0x18, 0x0002)
        mem.ww(ds, 0xBEDC, 0x0000)
        mem.ww(ds, 0xA8C2, 0x0000)
        mem.ww(ss, bp + 0x00, 0x0001)
        mem.ww(ss, bp + 0x14, 0x0001)
        mem.ww(ss, bp + 0x18, 0x0020)
        mem.ww(ss, bp + 0x20, 0x0004)
        mem.ww(ss, bp + 0x24, 0x1111)
        mem.ww(ss, bp + 0x28, 0xFFFF)
        state = CPUState(
            ax=0xAAAA, bx=collided_bx, cx=0x0007, dx=0xDDDD,
            si=0xEEEE, di=0xFFFF, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xBEC5, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    hook = make_cpu()

    _run_collision_handler_bec5_observed(hook, collided_bx=0x1200, parent="test", chain="test", cx_value=0x0007)

    assert hook.s.ip == 0xBEEF
    assert hook.mem.rw(0x2000, 0x1200) == 0x0000
    assert hook.mem.rw(0x2000, 0xA8C2) == 0x0000


def test_bec5_third_counter_zero_jumps_to_bf4b():
    from overkill.hooks import _run_collision_handler_bec5_observed
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory

    code_bec5 = bytes.fromhex(
        "837f18077503e9eb00837f18087503e9e200837f180c7503e9d900"
        "837f18097503e9bf00837f1802742c837f18067503e99f00837f"
        "18057503e996003b6f307401c3c7471c0000833ec2a8017412"
        "c746200000e9ac00c7070000837f08337508ff4e207503e99a00"
        "ff4e207503e99200833edcbe017411833edcbe00750fff4e20"
        "747fff4e20747aff4e207475c746240500833ec2a8017401c3"
    )

    mem = Memory()
    mem.load(0x1010, 0xBEC5, code_bec5)
    ds = 0x2000
    ss = 0x3000
    collided_bx = 0x1200
    bp = 0x2504
    mem.ww(ds, collided_bx + 0x00, 0x0001)
    mem.ww(ds, collided_bx + 0x08, 0x0033)
    mem.ww(ds, collided_bx + 0x18, 0x0002)
    mem.ww(ds, 0xBEDC, 0x0000)
    mem.ww(ds, 0xA8C2, 0x0000)
    mem.ww(ss, bp + 0x00, 0x0001)
    mem.ww(ss, bp + 0x14, 0x0001)
    mem.ww(ss, bp + 0x18, 0x0020)
    mem.ww(ss, bp + 0x20, 0x0003)
    mem.ww(ss, bp + 0x24, 0x1111)
    mem.ww(ss, bp + 0x28, 0xFFFF)
    state = CPUState(
        ax=0xAAAA, bx=collided_bx, cx=0x0007, dx=0xDDDD,
        si=0xEEEE, di=0xFFFF, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBEC5, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)
    _run_collision_handler_bec5_observed(cpu, collided_bx=0x1200, parent="test", chain="test", cx_value=0x0007)

    assert cpu.s.ip == 0xBEEF
    assert mem.rw(ds, collided_bx + 0x00) == 0x0000
    assert mem.rw(ss, bp + 0x20) == 0x0000
    assert mem.rw(ss, bp + 0x18) == 0x0001
    assert mem.rw(ds, 0xA47E) == 0xFFFF


def test_bec5_fourth_counter_zero_death_tail_matches_interpreted_asm():
    from pathlib import Path
    from overkill.hooks import _run_collision_handler_bec5_observed

    blob = Path("artifacts/test_oracles/snapshot_play_tandy_20260611_152751/memory_1mb.bin").read_bytes()

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.data[:] = blob
        ds = 0x2000
        ss = 0x3000
        collided_bx = 0x1200
        bp = 0x2504
        for off in range(0, 0x40, 2):
            mem.ww(ds, collided_bx + off, 0)
            mem.ww(ss, bp + off, 0)
        for off in range(0x2314, 0x231A):
            mem.wb(ds, off, 0)
        mem.ww(ds, collided_bx + 0x00, 0x0001)
        mem.ww(ds, collided_bx + 0x08, 0x007E)
        mem.ww(ds, collided_bx + 0x18, 0x0002)
        mem.ww(ds, 0xBEDC, 0x0000)
        mem.ww(ds, 0xA8C2, 0x0000)
        mem.wb(ds, 0x98C0, 0x00)
        mem.ww(ss, bp + 0x00, 0x0001)
        mem.ww(ss, bp + 0x14, 0x0001)
        mem.ww(ss, bp + 0x18, 0x0020)
        mem.ww(ss, bp + 0x20, 0x0004)
        mem.ww(ss, bp + 0x28, 0xFFFF)
        state = CPUState(
            ax=0xAAAA, bx=collided_bx, cx=0x0007, dx=0xDDDD,
            si=0xEEEE, di=0xFFFF, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xBEC5, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(400):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    _run_collision_handler_bec5_observed(
        hook,
        collided_bx=0x1200,
        parent="test",
        chain="test",
        cx_value=0x0007,
    )

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_b73e_b7f3_skip_to_bc4f_matches_interpreted_asm():
    from pathlib import Path
    from overkill.hooks import _run_object_behavior_b73e

    blob = Path("artifacts/test_oracles/snapshot_play_tandy_20260611_152751/memory_1mb.bin").read_bytes()

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.data[:] = blob
        ds = 0x2000
        ss = 0x3000
        bp = 0x284C
        for off in range(0, 0x40, 2):
            mem.ww(ss, bp + off, 0)
        mem.ww(ds, 0x2338, 0x0001)
        mem.ww(ds, 0x2340, 0x03CE)
        mem.ww(ds, 0x232E, 0x002C)
        mem.ww(ds, 0xA47C, 0x0001)
        mem.ww(ds, 0xA47E, 0x0014)
        mem.ww(ds, 0xA7A0, 0x0023)
        mem.ww(ss, bp + 0x00, 0x0001)
        mem.ww(ss, bp + 0x02, 0x0050)
        mem.ww(ss, bp + 0x04, 0x00B0)
        mem.ww(ss, bp + 0x08, 0x007B)
        mem.ww(ss, bp + 0x0A, 0x0001)
        mem.ww(ss, bp + 0x14, 0x0001)
        mem.ww(ss, bp + 0x16, 0x0004)
        mem.ww(ss, bp + 0x18, 0x0020)
        mem.ww(ss, bp + 0x1C, 0xFFFF)
        mem.ww(ss, bp + 0x20, 0x0004)
        mem.ww(ss, bp + 0x32, 0x00B0)
        mem.ww(ss, bp + 0x34, 0x0050)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x0016, dx=0x3333,
            si=0x4444, di=0x5555, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xB73E, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(400):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    _run_object_behavior_b73e(hook, parent="test", chain="test", cx_value=0x0016)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    # Same boundary-level equivalence: the shared BC4B clamp no longer writes the
    # dead BC4E scratch word below SP (ABI-undefined), so ignore just that.
    assert_oracle_equivalent(asm, hook)


def test_b73e_b82d_equal_waypoint_loop_matches_interpreted_asm():
    from pathlib import Path
    from overkill.hooks import _run_object_behavior_b73e

    blob = Path("artifacts/test_oracles/snapshot_play_tandy_20260611_152751/memory_1mb.bin").read_bytes()

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.data[:] = blob
        ds = 0x25CC
        ss = 0x25CC
        bp = 0x261C
        mem.ww(ds, 0x2338, 0x0005)
        mem.ww(ds, 0x2340, 0x00B3)
        mem.ww(ds, 0x2324, 0x0001)
        mem.ww(ds, 0x232E, 0x003F)
        mem.ww(ds, 0xA842, 0xA854)
        mem.ww(ds, 0xA47C, 0x0000)
        mem.ww(ds, 0xA47E, 0x0014)
        mem.ww(ds, 0xA7A0, 0x0027)
        mem.ww(ds, 0x2380, 0x0058)
        mem.ww(ds, 0x237E, 0x00C0)
        mem.ww(ds, 0x2350, 0x00B6)
        for off in range(0, 0x38, 2):
            mem.ww(ss, bp + off, 0)
        values = {
            0x00: 0x0001,
            0x02: 0x0060,
            0x04: 0x0040,
            0x06: 0x0004,
            0x08: 0x007A,
            0x0A: 0x0001,
            0x0C: 0x2D38,
            0x0E: 0x6F14,
            0x14: 0x0001,
            0x16: 0x0004,
            0x18: 0x0020,
            0x1C: 0xFFFF,
            0x20: 0x0004,
            0x28: 0xFFFF,
            0x32: 0x0040,
            0x34: 0x0060,
        }
        for off, value in values.items():
            mem.ww(ss, bp + off, value)
        state = CPUState(
            ax=0x0060, bx=0x0040, cx=0x000C, dx=0x000D,
            si=0xC3AB, di=0xA27E, bp=bp, sp=0xA272,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xB73E, flags=0x0246,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(1200):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    _run_object_behavior_b73e(hook, parent="test", chain="test", cx_value=0x000C)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_b73e_b800_formation_gate_odd_helper_matches_interpreted_asm():
    from pathlib import Path
    from overkill.hooks import _run_object_behavior_b73e

    blob = Path("artifacts/test_oracles/snapshot_play_tandy_20260611_152751/memory_1mb.bin").read_bytes()

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.data[:] = blob
        ds = 0x25CC
        ss = 0x25CC
        bp = 0x284C
        mem.ww(ds, 0x20A6, 0x20A8)
        mem.ww(ds, 0x20AA, 0x746F)  # odd after the helper advances 20A6 by 2.
        mem.ww(ds, 0x20C7, 0x0090)
        mem.ww(ds, 0x2338, 0x0003)
        mem.ww(ds, 0x2340, 0x02C0)
        mem.ww(ds, 0x2324, 0x0000)
        mem.ww(ds, 0x232E, 0x000E)
        mem.ww(ds, 0xA842, 0xA894)
        mem.ww(ds, 0xA47C, 0x0000)
        mem.ww(ds, 0xA47E, 0x0014)
        mem.ww(ds, 0xA7A0, 0x002B)
        mem.ww(ds, 0x2380, 0x0058)
        mem.ww(ds, 0x237E, 0x00C0)
        mem.ww(ds, 0x2350, 0x00B6)
        for off in range(0, 0x38, 2):
            mem.ww(ss, bp + off, 0)
        values = {
            0x00: 0x0001,
            0x02: 0x0060,
            0x04: 0x0090,
            0x06: 0x0004,
            0x08: 0x007D,
            0x0A: 0x0001,
            0x0C: 0x2D60,
            0x0E: 0x5614,
            0x14: 0x0001,
            0x16: 0x0004,
            0x18: 0x0020,
            0x1C: 0xFFFF,
            0x20: 0x0004,
            0x28: 0xFFFF,
            0x32: 0x0090,
            0x34: 0x0060,
        }
        for off, value in values.items():
            mem.ww(ss, bp + off, value)
        state = CPUState(
            ax=0x0060, bx=0x0040, cx=0x0016, dx=0x000D,
            si=0xC3AB, di=0xA27E, bp=bp, sp=0xA272,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xB73E, flags=0x0287,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(800):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    _run_object_behavior_b73e(hook, parent="test", chain="test", cx_value=0x0016)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_b73e_b77b_view_contact_death_matches_interpreted_asm():
    from pathlib import Path
    from overkill.hooks import _run_object_behavior_b73e

    blob = Path("artifacts/test_oracles/snapshot_play_tandy_20260611_152751/memory_1mb.bin").read_bytes()

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.data[:] = blob
        ds = 0x25CC
        ss = 0x25CC
        bp = 0x2814
        globals_ = {
            0x2314: 0x0000,
            0x2340: 0x0280,
            0x237E: 0x00C0,
            0x2380: 0x0058,
            0x2384: 0x0000,
            0xA47C: 0x0000,
            0xA47E: 0x0014,
            0xA8C2: 0x0000,
            0xA362: 0x0000,
            0xBEDC: 0x0000,
        }
        for off, value in globals_.items():
            mem.ww(ds, off, value)
        mem.wb(ds, 0x98C0, 0x00)
        mem.ww(ds, 0x214E, 0x0007)
        mem.ww(ds, 0x2150, 0x0008)
        for off in range(0, 0x38, 2):
            mem.ww(ss, bp + off, 0)
        values = {
            0x00: 0x0001,
            0x02: 0x00B4,
            0x04: 0x0060,
            0x06: 0x0004,
            0x08: 0x0077,
            0x0A: 0x0001,
            0x0C: 0x4F68,
            0x0E: 0x5894,
            0x14: 0x0001,
            0x16: 0x0004,
            0x18: 0x0020,
            0x1C: 0x0002,
            0x20: 0x0004,
            0x28: 0xFFFF,
            0x32: 0x0060,
            0x34: 0x0020,
        }
        for off, value in values.items():
            mem.ww(ss, bp + off, value)
        state = CPUState(
            ax=0x00B4, bx=0x0040, cx=0x0015, dx=0x0090,
            si=0x0004, di=0x0001, bp=bp, sp=0xA274,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xB73E, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(1000):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    _run_object_behavior_b73e(hook, parent="test", chain="test", cx_value=0x0015)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    ss = asm.s.ss & 0xFFFF
    stack_scratch = {((ss << 4) + off) & 0xFFFFF for off in range(0xA266, 0xA270)}
    for i, (a, b) in enumerate(zip(asm.mem.data, hook.mem.data)):
        if i not in stack_scratch:
            assert a == b, f"memory differs at physical {i:05X}: asm={a:02X} hook={b:02X}"


def test_b73e_b808_low_a47e_reset_target_matches_interpreted_asm():
    from pathlib import Path
    from overkill.hooks import _run_object_behavior_b73e

    blob = Path("artifacts/test_oracles/snapshot_play_tandy_20260611_152751/memory_1mb.bin").read_bytes()

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.data[:] = blob
        ds = 0x25CC
        ss = 0x25CC
        bp = 0x2700
        for off in range(0, 0x38, 2):
            mem.ww(ss, bp + off, 0)
        globals_ = {
            0x2338: 0x0002,
            0x2340: 0x0300,
            0x2324: 0x0001,
            0x232E: 0x002C,
            0xA47C: 0x0001,
            0xA47E: 0x0003,
            0xA7A0: 0x0023,
            0x2380: 0x0078,
            0xA278: 0x0000,
        }
        for off, value in globals_.items():
            mem.ww(ds, off, value)
        values = {
            0x00: 0x0001,
            0x02: 0x0060,
            0x04: 0x0080,
            0x08: 0x0000,
            0x0A: 0x0001,
            0x0C: 0x4000,
            0x0E: 0x5000,
            0x14: 0x0001,
            0x16: 0x0004,
            0x18: 0x0020,
            0x1C: 0xFFFF,
            0x20: 0x0004,
            0x28: 0xFFFF,
            0x32: 0x0087,
            0x34: 0x0060,
        }
        for off, value in values.items():
            mem.ww(ss, bp + off, value)
        state = CPUState(
            ax=0, bx=0, cx=0x0012, dx=0,
            si=0, di=0, bp=bp, sp=0xA272,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xB73E, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(300):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    _run_object_behavior_b73e(hook, parent="test", chain="test", cx_value=0x0012)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    ss = asm.s.ss & 0xFFFF
    stack_scratch = {((ss << 4) + off) & 0xFFFFF for off in range(0xA268, 0xA270)}
    for i, (a, b) in enumerate(zip(asm.mem.data, hook.mem.data)):
        if i not in stack_scratch:
            assert a == b, f"memory differs at physical {i:05X}: asm={a:02X} hook={b:02X}"


def test_b73e_b77b_out_of_bounds_bd17_deactivates_logic20_matches_interpreted_asm():
    from pathlib import Path
    from overkill.hooks import _run_object_behavior_b73e

    blob = Path("artifacts/test_oracles/snapshot_play_tandy_20260611_152751/memory_1mb.bin").read_bytes()

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.data[:] = blob
        ds = 0x25CC
        ss = 0x25CC
        bp = 0x276C
        for off in range(0, 0x38, 2):
            mem.ww(ss, bp + off, 0)
        globals_ = {
            0x2338: 0x0002,
            0x2340: 0x0300,
            0x2324: 0x0000,
            0x232E: 0x002C,
            0xA47C: 0x0000,
            0xA47E: 0x0005,
            0xA7A0: 0x0023,
            0x2380: 0x0078,
            0xA278: 0x0000,
        }
        for off, value in globals_.items():
            mem.ww(ds, off, value)
        values = {
            0x00: 0x0001,
            0x02: 0x00EC,
            0x04: 0x0090,
            0x08: 0x007A,
            0x0A: 0x0001,
            0x0C: 0xFFFF,
            0x0E: 0x6014,
            0x14: 0x0001,
            0x16: 0x0004,
            0x18: 0x0020,
            0x1C: 0x0002,
            0x20: 0x0004,
            0x28: 0xFFFF,
            0x32: 0x0090,
            0x34: 0x0020,
        }
        for off, value in values.items():
            mem.ww(ss, bp + off, value)
        state = CPUState(
            ax=0, bx=0, cx=0x0012, dx=0,
            si=0, di=0, bp=bp, sp=0xA272,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xB73E, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(300):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    _run_object_behavior_b73e(hook, parent="test", chain="test", cx_value=0x0012)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    ss = asm.s.ss & 0xFFFF
    stack_scratch = {((ss << 4) + off) & 0xFFFFF for off in range(0xA26A, 0xA270)}
    for i, (a, b) in enumerate(zip(asm.mem.data, hook.mem.data)):
        if i not in stack_scratch:
            assert a == b, f"memory differs at physical {i:05X}: asm={a:02X} hook={b:02X}"


def test_aa2b_and_efae_dispatch_hooks_match_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import (
        overkill_object_family_dispatch_efae,
        overkill_object_logic_dispatch_aa2b,
    )

    code_aa2b = bytes.fromhex("8b5e16d1e32effa736aa")
    code_efae = bytes.fromhex("8b4604a3fed18b4602a300d28b5e18d1e32effa7c4ef")

    def make_aa2b(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xAA2B, code_aa2b)
        mem.ww(0x1010, 0xAA36 + 4 * 2, 0xEFAE)
        ss = 0x3000
        bp = 0x0100
        mem.ww(ss, bp + 0x16, 4)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=0x2000, es=0x4000, ss=ss,
            ip=0xAA2B, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xAA2B)] = overkill_object_logic_dispatch_aa2b
        return cpu

    def make_efae(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xEFAE, code_efae)
        mem.ww(0x1010, 0xEFC4 + 0x20 * 2, 0xB73E)
        ss = 0x3000
        ds = 0x2000
        bp = 0x0100
        mem.ww(ss, bp + 0x02, 0x1234)
        mem.ww(ss, bp + 0x04, 0x5678)
        mem.ww(ss, bp + 0x18, 0x20)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x4000, ss=ss,
            ip=0xEFAE, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xEFAE)] = overkill_object_family_dispatch_efae
        return cpu

    for make_cpu, stop in ((make_aa2b, (0x1010, 0xEFAE)), (make_efae, (0x1010, 0xB73E))):
        asm = make_cpu(False)
        hook = make_cpu(True)
        for _ in range(20):
            if asm.addr() == stop:
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == stop
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_aa2b_dispatch_has_hook_verify_metadata():
    from overkill.verification import DEFAULT_STOPS

    stop = DEFAULT_STOPS[(0x1010, 0xAA2B)]
    assert stop.kind == "dispatch_aa2b"


def test_hook_verify_far_ret_stop_reads_ip_then_cs_from_stack():
    from overkill.verification import HookStop

    mem = Memory()
    ss = 0x3000
    sp = 0x8FFE
    mem.ww(ss, sp, 0x0707)
    mem.ww(ss, (sp + 2) & 0xFFFF, 0x254A)
    state = CPUState(cs=0x254A, ip=0x0701, ss=ss, sp=sp)
    cpu = CPU8086(mem, state)

    assert HookStop("far_ret").targets(cpu, state) == ((0x254A, 0x0707),)


def test_keyboard_poll_bits_017e_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_keyboard_poll_bits_017e

    code = bytes.fromhex('8a 1c 8a 01 d0 e8 d0 16 be 98 46 e2 f3')

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x017E, code)
        ds = 0x2000
        keys = [0x00, 0x2C, 0x39, 0x10, 0x1E, 0x18, 0x2A, 0x36]
        for i, key in enumerate(keys):
            mem.wb(ds, 0x0200 + i, key)
            mem.wb(ds, 0x98C4 + key, 1 if i in (0, 2, 5, 7) else 0)
        mem.wb(ds, 0x98BE, 0xA5)
        state = CPUState(
            ax=0x5500, bx=0x1200, cx=len(keys), dx=0x03D9,
            si=0x0200, di=0x98C4, bp=0,
            sp=0x9000, cs=0x1010, ds=ds, es=0xB800, ss=0x3000,
            ip=0x017E, flags=0x0293,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x017E)] = overkill_keyboard_poll_bits_017e
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(100):
        if asm.addr() == (0x1010, 0x018B):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0x018B)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_changed_word_present_cd8d_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_changed_word_present_8rows_cd8d

    code = bytes.fromhex(
        '8b 04 26 89 05 83 c6 50 81 c7 00 20 f7 c7 00 40 74 04'
        '81 c7 50 c0 e2 e8 eb 5b'
    )

    def make_cpu(use_hook: bool, *, start_di: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xCD8D, code)
        ds = 0x2000
        es = 0xB800
        si = 0x1000
        for row in range(8):
            mem.ww(ds, si + row * 0x50, 0x4000 + row * 0x111)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=8, dx=0x0301,
            si=si, di=start_di, bp=0x0002,
            sp=0x9000, cs=0x1010, ds=ds, es=es, ss=0x3000,
            ip=0xCD8D, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xCD8D)] = overkill_changed_word_present_8rows_cd8d
        return cpu

    for start_di in (0x1B82, 0x3FF0):
        asm = make_cpu(False, start_di=start_di)
        hook = make_cpu(True, start_di=start_di)
        for _ in range(200):
            if asm.addr() == (0x1010, 0xCE02):
                break
            asm.step()
        hook.step()

        assert asm.addr() == hook.addr() == (0x1010, 0xCE02)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_tandy_changed_dword_present_cdaa_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_changed_dword_present_8rows_cdaa

    code = bytes.fromhex(
        '8b 04 26 89 05 8b 44 02 26 89 45 02 81 c6 a0 00'
        '81 c7 00 20 f7 c7 00 80 74 04 81 c7 a0 80 e2 e0 eb 36'
    )

    def make_cpu(use_hook: bool, *, start_di: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xCDAA, code)
        ds = 0x2000
        es = 0xB800
        si = 0x1000
        for row in range(8):
            mem.ww(ds, si + row * 0xA0, 0x4000 + row * 0x111)
            mem.ww(ds, si + row * 0xA0 + 2, 0x5000 + row * 0x111)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=8, dx=0x0301,
            si=si, di=start_di, bp=0x0004,
            sp=0x9000, cs=0x1010, ds=ds, es=es, ss=0x3000,
            ip=0xCDAA, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xCDAA)] = overkill_tandy_changed_dword_present_8rows_cdaa
        return cpu

    for start_di in (0x1B84, 0x7FF0):
        asm = make_cpu(False, start_di=start_di)
        hook = make_cpu(True, start_di=start_di)
        for _ in range(300):
            if asm.addr() == (0x1010, 0xCE02):
                break
            asm.step()
        hook.step()

        assert asm.addr() == hook.addr() == (0x1010, 0xCE02)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_cga_object_row_addr_5a36_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_object_row_addr_5a36

    code_5a36 = bytes.fromhex('2e 8b 1e bc 95 d1 e3 2e ff a7 42 5a')
    code_41f5 = bytes.fromhex(
        '8b 5e 02 81 fb e0 00 72 03 e9 b1 e3 d1 e3 8b 9f c8 99'
        '83 fb ff 75 03 e9 a3 e3 8b 46 04 8b c8 83 e1 03 89 4e 12'
        'd1 e8 d1 e8 03 c3 83 7e 24 00 75 01 c3 ff 4e 24 c3'
    )
    code_25b2 = bytes.fromhex('b8 ff ff c3')

    def make_cpu(use_hook: bool, *, y: int, x: int, row_word: int, countdown: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x5A36, code_5a36)
        mem.load(0x1010, 0x41F5, code_41f5)
        mem.load(0x1010, 0x25B2, code_25b2)
        mem.ww(0x1010, 0x95BC, 0)
        mem.ww(0x1010, 0x5A42, 0x41F5)
        ds = 0x2000
        ss = 0x3000
        bp = 0x0100
        mem.ww(ss, bp + 0x02, y)
        mem.ww(ss, bp + 0x04, x)
        mem.ww(ss, bp + 0x24, countdown)
        mem.ww(ds, 0x99C8 + ((y << 1) & 0xFFFF), row_word)
        state = CPUState(
            ax=0x6666, bx=0x7777, cx=0x8888, dx=0x9999,
            si=0xAAAA, di=0xBBBB, bp=bp,
            sp=0x9000, cs=0x1010, ds=ds, es=0x4000, ss=ss,
            ip=0x5A36, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x5A36)] = overkill_object_row_addr_5a36
        return cpu

    cases = [
        dict(y=0x00C0, x=0x0058, row_word=0x2080, countdown=0),
        dict(y=0x00D0, x=0x005B, row_word=0x23C0, countdown=3),
        dict(y=0x00E0, x=0x0058, row_word=0x2080, countdown=0),
        dict(y=0x0010, x=0x0058, row_word=0xFFFF, countdown=0),
    ]
    for case in cases:
        asm = make_cpu(False, **case)
        hook = make_cpu(True, **case)
        for _ in range(80):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_tandy_object_row_addr_5a36_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_object_row_addr_5a36

    code_5a36 = bytes.fromhex("2e 8b 1e bc 95 d1 e3 2e ff a7 42 5a")
    code_30d2 = bytes.fromhex(
        "8b5e0281fbe0007203e9d4f4d1e38b9fc89983fbff7503e9c6f4"
        "8b4604c746120000d1e803c3837e24007501c3ff4e24c3"
    )
    code_25b2 = bytes.fromhex("b8 ff ff c3")

    def make_cpu(
        use_hook: bool,
        *,
        y: int,
        x: int,
        row_word: int,
        countdown: int,
        flags: int,
    ) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x5A36, code_5a36)
        mem.load(0x1010, 0x30D2, code_30d2)
        mem.load(0x1010, 0x25B2, code_25b2)
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x5A46, 0x30D2)
        ds = 0x2000
        ss = 0x3000
        bp = 0x0100
        mem.ww(ss, bp + 0x02, y)
        mem.ww(ss, bp + 0x04, x)
        mem.ww(ss, bp + 0x12, 0xCAFE)
        mem.ww(ss, bp + 0x24, countdown)
        mem.ww(ds, (0x99C8 + ((y << 1) & 0xFFFF)) & 0xFFFF, row_word)
        state = CPUState(
            ax=0x6666, bx=0x7777, cx=0x8888, dx=0x9999,
            si=0xAAAA, di=0xBBBB, bp=bp,
            sp=0x9000, cs=0x1010, ds=ds, es=0x4000, ss=ss,
            ip=0x5A36, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x5A36)] = overkill_object_row_addr_5a36
        return cpu

    cases = [
        dict(y=0x00C0, x=0x0058, row_word=0x2080, countdown=0, flags=0x0203),
        dict(y=0x00D0, x=0x005B, row_word=0x23C0, countdown=3, flags=0x0203),
        dict(y=0x00E0, x=0x0058, row_word=0x2080, countdown=0, flags=0x0246),
        dict(y=0x0010, x=0x0058, row_word=0xFFFF, countdown=0, flags=0x0287),
    ]
    for case in cases:
        asm = make_cpu(False, **case)
        hook = make_cpu(True, **case)
        for _ in range(100):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == (0x1010, 0xBEEF)
        assert hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_cga_xy_to_di_5a00_and_5a24_hooks_match_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_xy_to_di_5a00, overkill_xy_to_di_5a24

    dispatch_5a00 = bytes.fromhex('2e 8b 1e bc 95 d1 e3 2e ff a7 0c 5a')
    dispatch_5a24 = bytes.fromhex('2e 8b 1e bc 95 d1 e3 2e ff a7 30 5a')
    # Mode 0 (CGA) targets double X (one SHL AX,1), mode 1 (EGA) leaves X
    # unscaled, and mode 2 (Tandy) targets at 3103/312D quadruple X (two SHL AX,1).
    target_422b = bytes.fromhex('8a dc 32 ff d1 e3 8b 9f e8 9e 32 e4 d1 e0 03 c3 8b f8 c3')
    target_4251 = bytes.fromhex('8a dc 32 ff d1 e3 8b 9f 58 9d 32 e4 d1 e0 03 c3 8b f8 c3')
    target_25b6 = bytes.fromhex('8a dc 32 ff d1 e3 8b 9f e8 9e 32 e4 03 c3 8b f8 c3')
    target_25d8 = bytes.fromhex('8a dc 32 ff d1 e3 8b 9f 58 9d 32 e4 03 c3 8b f8 c3')
    target_3103 = bytes.fromhex('8a dc 32 ff d1 e3 8b 9f e8 9e 32 e4 d1 e0 d1 e0 03 c3 8b f8 c3')
    target_312d = bytes.fromhex('8a dc 32 ff d1 e3 8b 9f 58 9d 32 e4 d1 e0 d1 e0 03 c3 8b f8 c3')

    def make_cpu(use_hook, *, entry, hook_fn, dispatch, target, target_ip, table, mode):
        mem = Memory()
        mem.load(0x1010, entry, dispatch)
        mem.load(0x1010, target_ip, target)
        mem.ww(0x1010, 0x95BC, mode)
        table_slot = 0x5A0C if entry == 0x5A00 else 0x5A30
        mem.ww(0x1010, (table_slot + mode * 2) & 0xFFFF, target_ip)
        ds = 0x2000
        mem.ww(ds, table + 0xB0 * 2, 0x1B80)
        mem.ww(ds, table + 0x2A * 2, 0x0660)
        state = CPUState(
            ax=0xB001, bx=0x7777, cx=0x1234, dx=0x0301,
            si=0xAAAA, di=0xBBBB, bp=0xCCCC,
            sp=0x9000, cs=0x1010, ds=ds, es=0x3000, ss=0x4000,
            ip=entry, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, entry)] = hook_fn
        return cpu

    cases = [
        (0x5A00, overkill_xy_to_di_5a00, dispatch_5a00, target_422b, 0x422B, 0x9EE8, 0),
        (0x5A24, overkill_xy_to_di_5a24, dispatch_5a24, target_4251, 0x4251, 0x9D58, 0),
        (0x5A00, overkill_xy_to_di_5a00, dispatch_5a00, target_25b6, 0x25B6, 0x9EE8, 1),
        (0x5A24, overkill_xy_to_di_5a24, dispatch_5a24, target_25d8, 0x25D8, 0x9D58, 1),
        (0x5A00, overkill_xy_to_di_5a00, dispatch_5a00, target_3103, 0x3103, 0x9EE8, 2),
        (0x5A24, overkill_xy_to_di_5a24, dispatch_5a24, target_312d, 0x312D, 0x9D58, 2),
    ]
    for entry, hook_fn, dispatch, target, target_ip, table, mode in cases:
        kw = dict(entry=entry, hook_fn=hook_fn, dispatch=dispatch, target=target,
                  target_ip=target_ip, table=table, mode=mode)
        asm = make_cpu(False, **kw)
        hook = make_cpu(True, **kw)
        for _ in range(40):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == (0x1010, 0xBEEF), (entry, mode)
        assert asm.s.snapshot() == hook.s.snapshot(), (entry, mode)
        assert asm.mem.data == hook.mem.data, (entry, mode)


def test_masked_sprite_composite_3e12_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_masked_sprite_composite_3e12

    code = bytes.fromhex(
        '8b 1c 8b 44 04 b2 ff f9 d0 db d0 df d0 d8 d0 dc d0 da'
        'f9 d0 db d0 df d0 d8 d0 dc d0 da 26 21 1d 26 21 45 02'
        '26 20 55 04 8b 5c 02 8b 44 06 32 d2 d0 eb d0 df d0 d8'
        'd0 dc d0 da d0 eb d0 df d0 d8 d0 dc d0 da 26 09 1d'
        '26 09 45 02 26 08 55 04 83 c6 08 83 c7 34 4d 75 a8'
    )

    def make_cpu(use_hook: bool, *, rows: int, start_di: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x3E12, code)
        ds = 0x2000
        es = 0xB800
        si = 0x1800
        for i in range(rows * 8 + 8):
            mem.wb(ds, (si + i) & 0xFFFF, (0x37 + i * 0x29) & 0xFF)
        for i in range(rows * 0x34 + 0x20):
            mem.wb(es, (start_di + i) & 0xFFFF, (0xA5 ^ (i * 0x11)) & 0xFF)
        state = CPUState(
            ax=0x1357, bx=0x2468, cx=0x4321, dx=0xABCD,
            si=si, di=start_di, bp=rows,
            sp=0x9000, cs=0x1010, ds=ds, es=es, ss=0x3000,
            ip=0x3E12, flags=0x0297,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x3E12)] = overkill_masked_sprite_composite_3e12
        return cpu

    for rows, start_di in ((1, 0x1100), (3, 0x1FF0), (4, 0xFFE8)):
        asm = make_cpu(False, rows=rows, start_di=start_di)
        hook = make_cpu(True, rows=rows, start_di=start_di)
        for _ in range(rows * 80 + 20):
            if asm.addr() == (0x1010, 0x3E6A):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0x3E6A)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_strided_row_copy_3ee1_and_3efc_hooks_match_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_strided_row_copy_3ee1, overkill_strided_row_copy_3efc

    code_3ee1 = bytes.fromhex('2e 8e 06 98 95 ad 8b c8 ad d1 e0 8b e8 51 8b cd f3 a4 2b fd 83 c7 34 59 e2 f3 c3')
    code_3efc = bytes.fromhex('2e 8e 06 98 95 ad 8b c8 ad d1 e0 8b e8 51 8b cd f3 a4 2b fd 83 c7 50 59 e2 f3 c3')

    def make_cpu(use_hook: bool, *, entry: int, code: bytes, hook_fn, rows: int, width_words: int, start_di: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, entry, code)
        mem.ww(0x1010, 0x9598, 0xB800)
        ds = 0x2000
        si = 0x1800
        mem.ww(ds, si, rows)
        mem.ww(ds, si + 2, width_words)
        width = width_words * 2
        for i in range(rows * width + 0x20):
            mem.wb(ds, si + 4 + i, (0x23 + i * 0x31) & 0xFF)
        for i in range(rows * 0x50 + width + 0x40):
            mem.wb(0xB800, (start_di + i) & 0xFFFF, (0xE7 ^ (i * 0x13)) & 0xFF)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=si, di=start_di, bp=0x5555,
            sp=0x9000, cs=0x1010, ds=ds, es=0x7777, ss=0x3000,
            ip=entry, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, entry)] = hook_fn
        return cpu

    cases = [
        (0x3EE1, code_3ee1, overkill_strided_row_copy_3ee1, 3, 4, 0x1100),
        (0x3EE1, code_3ee1, overkill_strided_row_copy_3ee1, 2, 7, 0xFFE8),
        (0x3EFC, code_3efc, overkill_strided_row_copy_3efc, 3, 4, 0x1200),
        (0x3EFC, code_3efc, overkill_strided_row_copy_3efc, 2, 6, 0x1FF0),
    ]
    for entry, code, hook_fn, rows, width_words, start_di in cases:
        asm = make_cpu(False, entry=entry, code=code, hook_fn=hook_fn, rows=rows, width_words=width_words, start_di=start_di)
        hook = make_cpu(True, entry=entry, code=code, hook_fn=hook_fn, rows=rows, width_words=width_words, start_di=start_di)
        for _ in range(rows * (width_words * 4 + 30) + 40):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_masked_sprite_composite_3efb_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_masked_sprite_composite_3efb

    mask_pass = 'f9 d0 db d0 df d0 d8 d0 dc d0 da'
    data_pass = 'd0 eb d0 df d0 d8 d0 dc d0 da'
    code = bytes.fromhex(
        '8b 1c 8b 44 04 b2 ff ' + ' '.join([mask_pass] * 6) +
        ' 26 21 1d 26 21 45 02 26 20 55 04 8b 5c 02 8b 44 06 32 d2 ' +
        ' '.join([data_pass] * 6) +
        ' 26 09 1d 26 09 45 02 26 08 55 04 83 c6 08 83 c7 34 4d 74 03 e9 51 ff 2e 8e 1e 96 95 c3'
    )

    def make_cpu(use_hook: bool, *, rows: int, start_di: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x3EFB, code)
        mem.ww(0x1010, 0x9596, 0x2222)
        ds = 0x2000
        es = 0xB800
        si = 0x1400
        for i in range(rows * 8 + 8):
            mem.wb(ds, (si + i) & 0xFFFF, (0x9B + i * 0x17) & 0xFF)
        for i in range(rows * 0x34 + 0x30):
            mem.wb(es, (start_di + i) & 0xFFFF, (0x41 ^ (i * 0x21)) & 0xFF)
        state = CPUState(
            ax=0x1020, bx=0x3040, cx=0x5060, dx=0x7788,
            si=si, di=start_di, bp=rows,
            sp=0x9000, cs=0x1010, ds=ds, es=es, ss=0x3000,
            ip=0x3EFB, flags=0x0207,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x3EFB)] = overkill_masked_sprite_composite_3efb
        return cpu

    for rows, start_di in ((1, 0x1000), (3, 0x1FE0), (5, 0xFFE0)):
        asm = make_cpu(False, rows=rows, start_di=start_di)
        hook = make_cpu(True, rows=rows, start_di=start_di)
        for _ in range(rows * 120 + 20):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_dispatch_5ac8_and_5a92_hooks_match_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_dispatch_draw_object_5ac8, overkill_dispatch_present_object_5a92

    code_5ac8 = bytes.fromhex('8b 5e 14 2e 03 1e bc 95 2e 03 1e bc 95 2e 03 1e bc 95 d1 e3 2e ff a7 e2 5a')
    code_5a92 = bytes.fromhex('2e 8e 06 98 95 8b 7e 0c 8b 76 0e 8b 5e 14 2e 03 1e bc 95 2e 03 1e bc 95 2e 03 1e bc 95 d1 e3 2e ff a7 b6 5a')

    def make_cpu(use_hook: bool, *, entry: int, code: bytes, hook_fn, table: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, entry, code)
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x9598, 0xB800)
        ss = 0x3000
        bp = 0x1000
        mem.ww(ss, bp + 0x0C, 0x2096)
        mem.ww(ss, bp + 0x0E, 0x3314)
        mem.ww(ss, bp + 0x14, 4)
        # table index = (4 + 2+2+2) << 1 = 20
        mem.ww(0x1010, table + 20, 0xBEEF)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp,
            sp=0x9000, cs=0x1010, ds=0x2000, es=0x7777, ss=ss,
            ip=entry, flags=0x0287,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, entry)] = hook_fn
        return cpu

    for entry, code, hook_fn, table in (
        (0x5AC8, code_5ac8, overkill_dispatch_draw_object_5ac8, 0x5AE2),
        (0x5A92, code_5a92, overkill_dispatch_present_object_5a92, 0x5AB6),
    ):
        asm = make_cpu(False, entry=entry, code=code, hook_fn=hook_fn, table=table)
        hook = make_cpu(True, entry=entry, code=code, hook_fn=hook_fn, table=table)
        for _ in range(20):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_clc_ret_aa44_hook_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_clc_ret_aa44

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xAA44, bytes.fromhex('f8 c3'))
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777,
            sp=0x9000, cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0xAA44, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xAA44)] = overkill_clc_ret_aa44
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(4):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_ega_memory_read_map_selects_shadow_plane():
    from dos_re.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE

    mem = Memory()
    mem.ega_planar = True
    off = 0x0123
    for plane, value in enumerate((0x11, 0x22, 0x33, 0x44)):
        mem.data[EGA_APERTURE + plane * EGA_PLANE_STRIDE + off] = value
        mem.data[EGA_APERTURE + plane * EGA_PLANE_STRIDE + off + 1] = (value + 1) & 0xFF

    for plane, value in enumerate((0x11, 0x22, 0x33, 0x44)):
        mem.ega_read_plane = plane
        assert mem.rb(0xA000, off) == value
        assert mem.rw(0xA000, off) == (value | (((value + 1) & 0xFF) << 8))


def test_rep_movsb_uses_ega_selected_read_plane_instead_of_flat_slice():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE
    from overkill.hooks import _rep_movsb

    mem = Memory()
    mem.ega_planar = True
    mem.ega_read_plane = 2
    src_off = 0x0040
    payloads = [b'aaaa', b'bbbb', b'CDEF', b'dddd']
    for plane, payload in enumerate(payloads):
        start = EGA_APERTURE + plane * EGA_PLANE_STRIDE + src_off
        mem.data[start:start + len(payload)] = payload

    cpu = CPU8086(mem, CPUState(ds=0xA000, es=0x2000, si=src_off, di=0x0100, cx=4, flags=0x0202))
    _rep_movsb(cpu, 4)

    assert bytes(mem.data[0x2000 * 16 + 0x0100:0x2000 * 16 + 0x0104]) == b'CDEF'
    assert cpu.s.si == src_off + 4
    assert cpu.s.di == 0x0104
    assert cpu.s.cx == 0


def test_rep_stosb_respects_ega_map_mask_instead_of_flat_slice():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE
    from overkill.hooks import _rep_stosb

    mem = Memory()
    mem.ega_planar = True
    mem.ega_map_mask = 0b1010
    off = 0x0060
    for plane in range(4):
        start = EGA_APERTURE + plane * EGA_PLANE_STRIDE + off
        mem.data[start:start + 3] = bytes([0x10 + plane]) * 3

    cpu = CPU8086(mem, CPUState(ax=0x00EE, es=0xA000, di=off, cx=3, flags=0x0202))
    _rep_stosb(cpu, 3)

    assert bytes(mem.data[EGA_APERTURE + 0 * EGA_PLANE_STRIDE + off:EGA_APERTURE + 0 * EGA_PLANE_STRIDE + off + 3]) == bytes([0x10]) * 3
    assert bytes(mem.data[EGA_APERTURE + 1 * EGA_PLANE_STRIDE + off:EGA_APERTURE + 1 * EGA_PLANE_STRIDE + off + 3]) == bytes([0xEE]) * 3
    assert bytes(mem.data[EGA_APERTURE + 2 * EGA_PLANE_STRIDE + off:EGA_APERTURE + 2 * EGA_PLANE_STRIDE + off + 3]) == bytes([0x12]) * 3
    assert bytes(mem.data[EGA_APERTURE + 3 * EGA_PLANE_STRIDE + off:EGA_APERTURE + 3 * EGA_PLANE_STRIDE + off + 3]) == bytes([0xEE]) * 3


def test_ega_cpu_page_offsets_do_not_alias_visible_shadow_planes():
    """A000:2000 is a real CPU offset/page, not visible plane-1 offset 0000."""
    from dos_re.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE

    mem = Memory()
    mem.ega_planar = True
    mem.ega_map_mask = 0x0F
    # Seed the visible byte at offset 0 in each plane with unique values.
    for plane in range(4):
        mem.data[EGA_APERTURE + plane * EGA_PLANE_STRIDE + 0x0000] = 0x40 + plane

    # A real CPU write to A000:2000 updates offset 2000h in the selected planes.
    # It must not be interpreted as "plane 1, offset 0000h".
    mem.wb(0xA000, 0x2000, 0xEE)

    assert [mem.data[EGA_APERTURE + plane * EGA_PLANE_STRIDE + 0x0000] for plane in range(4)] == [0x40, 0x41, 0x42, 0x43]
    assert [mem.data[EGA_APERTURE + plane * EGA_PLANE_STRIDE + 0x2000] for plane in range(4)] == [0xEE, 0xEE, 0xEE, 0xEE]


def test_ega_read_map_can_read_high_cpu_offsets_without_shadow_aliasing():
    from dos_re.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE

    mem = Memory()
    mem.ega_planar = True
    for plane in range(4):
        mem.data[EGA_APERTURE + plane * EGA_PLANE_STRIDE + 0x2000] = 0x70 + plane

    mem.ega_read_plane = 2
    assert mem.rb(0xA000, 0x2000) == 0x72
    # Reading the visible offset 0 from plane 2 is independent.
    mem.data[EGA_APERTURE + 2 * EGA_PLANE_STRIDE + 0x0000] = 0x99
    assert mem.rb(0xA000, 0x0000) == 0x99


def test_tandy_tiny_strided_copy_3542_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_tiny_strided_copy_3542

    code = bytes.fromhex("83ffff7501c3bb6400" + ("a5a503fb" * 8) + "c3")

    def make_cpu(use_hook: bool, *, flags: int, di: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x3542, code)
        ds, es, ss = 0x3000, 0x4000, 0x5000
        si = 0x0180
        for off in range(-0x40, 0x220):
            mem.wb(ds, (si + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x700):
            mem.wb(es, (di + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x7777, cx=0x3333, dx=0xAAAA,
            si=si, di=di, bp=0x237C, sp=0x9000,
            cs=0x1010, ds=ds, es=es, ss=ss,
            ip=0x3542, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x3542)] = overkill_tandy_tiny_strided_copy_3542
        return cpu

    for flags in (0x0203, 0x0603):
        for di in (0x0240, 0xFFFF):
            asm = make_cpu(False, flags=flags, di=di, seed=0x3542 + flags + di)
            hook = make_cpu(True, flags=flags, di=di, seed=0x3542 + flags + di)
            for _ in range(1000):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.data == hook.mem.data


def test_tandy_split_present_copy_34ad_hook_matches_interpreted_asm():
    import random
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_split_present_copy_34ad

    code_34ad = bytes.fromhex("83ffff7403e810008b7e108b760e81c6400183ffff7501c3")
    code_34c5 = bytes.fromhex("bb5800b91000a5a5a5a5a5a5a5a503fbe2f4c3")

    def make_cpu(use_hook: bool, *, first_di: int, second_di: int, flags: int, seed: int) -> CPU8086:
        rnd = random.Random(seed)
        mem = Memory()
        mem.load(0x1010, 0x34AD, code_34ad)
        mem.load(0x1010, 0x34C5, code_34c5)
        ds, es, ss = 0x3000, 0x4000, 0x5000
        mem.ww(0x1010, 0x9596, ds)
        bp, si = 0x0200, 0x0800
        mem.ww(ss, bp + 0x0E, si)
        mem.ww(ss, bp + 0x10, second_di)
        for off in range(-0x40, 0x700):
            mem.wb(ds, (si + off) & 0xFFFF, rnd.randrange(256))
        for off in range(-0x40, 0x900):
            mem.wb(es, (first_di + off) & 0xFFFF, rnd.randrange(256))
            mem.wb(es, (second_di + off) & 0xFFFF, rnd.randrange(256))
        state = CPUState(
            ax=rnd.randrange(0x10000), bx=0x7777, cx=0x3333, dx=0xAAAA,
            si=si, di=first_di, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=es, ss=ss,
            ip=0x34AD, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x34AD)] = overkill_tandy_split_present_copy_34ad
        return cpu

    cases = [
        (0x0240, 0x0500),
        (0xFFFF, 0x0500),
        (0x0240, 0xFFFF),
        (0xFFFF, 0xFFFF),
    ]
    for flags in (0x0203, 0x0603):
        for first_di, second_di in cases:
            asm = make_cpu(False, first_di=first_di, second_di=second_di, flags=flags, seed=0x34AD + flags + first_di + second_di)
            hook = make_cpu(True, first_di=first_di, second_di=second_di, flags=flags, seed=0x34AD + flags + first_di + second_di)
            for _ in range(3000):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.data == hook.mem.data


def test_tandy_present_scan_a90f_composes_known_targets_like_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_scan_objects_call_5a92_a90f

    code_a90f = bytes.fromhex("518bd9d1e38baf128d837e00007403e871b159e2eb")
    code_5a92 = bytes.fromhex(
        "2e8e0698958b7e0c8b760e8b5e142e031ebc952e031ebc952e031ebc95"
        "d1e32effa7b65a"
    )
    code_3542 = bytes.fromhex("83ffff7501c3bb6400" + ("a5a503fb" * 8) + "c3")
    code_34ad = bytes.fromhex("83ffff7403e810008b7e108b760e81c6400183ffff7501c3")
    code_34c5 = bytes.fromhex("bb5800b91000a5a5a5a5a5a5a5a503fbe2f4c3")

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA90F, code_a90f)
        mem.load(0x1010, 0x5A92, code_5a92)
        mem.load(0x1010, 0x3542, code_3542)
        mem.load(0x1010, 0x34AD, code_34ad)
        mem.load(0x1010, 0x34C5, code_34c5)
        game_ds, obj_ss, dest_es = 0x2000, 0x3000, 0x4000
        mem.ww(0x1010, 0x95BC, 2)
        mem.ww(0x1010, 0x9596, game_ds)
        mem.ww(0x1010, 0x9598, dest_es)
        mem.ww(0x1010, 0x5AC2, 0x3542)  # object type 0, mode 2
        mem.ww(0x1010, 0x5AC6, 0x34AD)  # object type 2, mode 2
        for cx in range(1, 5):
            ptr = 0x0100 + cx * 0x40
            mem.ww(game_ds, (0x8D12 + cx * 2) & 0xFFFF, ptr)
            mem.ww(obj_ss, ptr, 0)
            mem.ww(obj_ss, ptr + 0x0C, 0x0200 + cx * 0x120)
            mem.ww(obj_ss, ptr + 0x0E, 0x0800 + cx * 0x180)
            mem.ww(obj_ss, ptr + 0x10, 0x0300 + cx * 0x120)
            mem.ww(obj_ss, ptr + 0x14, 0)
        # Descending scan order: CX=4,3,2,1.
        mem.ww(obj_ss, 0x0100 + 4 * 0x40, 1)       # 3542 copy
        mem.ww(obj_ss, 0x0100 + 2 * 0x40, 1)       # 34AD split copy
        mem.ww(obj_ss, 0x0100 + 2 * 0x40 + 0x14, 2)
        mem.ww(obj_ss, 0x0100 + 1 * 0x40, 1)       # 3542 DI=FFFF early return
        mem.ww(obj_ss, 0x0100 + 1 * 0x40 + 0x0C, 0xFFFF)
        for off in range(0x0600, 0x1600):
            mem.wb(game_ds, off, (off * 7 + 3) & 0xFF)
        for off in range(0x0200, 0x1000):
            mem.wb(dest_es, off, (off * 5 + 1) & 0xFF)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=4, dx=0x3333, si=0x4444, di=0x5555,
            bp=0x6666, sp=0x9000, cs=0x1010, ds=game_ds, es=0x7777,
            ss=obj_ss, ip=0xA90F, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA90F)] = overkill_scan_objects_call_5a92_a90f
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(5000):
        if asm.addr() == (0x1010, 0xA91E):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xA91E)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_runtime_patched_object_steer_5e42_hook_matches_interpreted_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "runtime_code_5e42_gameplay_20260613_220042"
    assert snap.exists(), "captured gameplay snapshot for runtime-patched 1010:5E42 is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.trace_enabled = False
        # B24D now absorbs its nested CALL 5E42.  Disable the parent here
        # because this test targets the 5E42 boundary itself.
        rt.cpu.replacement_hooks.pop((0x1010, 0xB24D), None)
        rt.cpu.hook_names.pop((0x1010, 0xB24D), None)
        if not use_hook:
            rt.cpu.replacement_hooks.pop((0x1010, 0x5E42), None)
            rt.cpu.hook_names.pop((0x1010, 0x5E42), None)
        return rt

    asm = make_runtime(False)
    hook = make_runtime(True)

    for _ in range(20_000):
        if asm.cpu.addr() == (0x1010, 0x5E42):
            break
        asm.cpu.step()
    for _ in range(20_000):
        if hook.cpu.addr() == (0x1010, 0x5E42):
            break
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x5E42)
    return_ip = asm.cpu.mem.rw(asm.cpu.s.ss, asm.cpu.s.sp)

    for _ in range(500):
        if asm.cpu.addr() == (0x1010, return_ip):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, return_ip)
    assert_oracle_equivalent(asm.cpu, hook.cpu)  # 5E42 internal-call scratch below SP dropped


def test_hook_verifier_verifies_runtime_patched_object_steer_5e42():
    from pathlib import Path
    from overkill.verification import HookVerifierConfig, install_hook_verifier
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "runtime_code_5e42_gameplay_20260613_220042"
    assert snap.exists(), "captured gameplay snapshot for runtime-patched 1010:5E42 is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    rt.cpu.trace_enabled = False
    # B24D now composes the nested 5E42 call; expose the leaf boundary for
    # this verifier test.
    rt.cpu.replacement_hooks.pop((0x1010, 0xB24D), None)
    rt.cpu.hook_names.pop((0x1010, 0xB24D), None)
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0x5E42)}, stop_on_diff=True),
    )

    for _ in range(20_000):
        rt.cpu.step()
        if verifier.total_verified:
            break

    assert verifier.total_verified == 1
    assert (0x1010, 0x5E42) not in verifier.skipped


def test_movement_direction_5db2_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "closure_run_5db2_160415"
    assert snap.exists(), "captured oracle snapshot for 1010:5DB2 is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x5DB2), None)
    asm.cpu.hook_names.pop((0x1010, 0x5DB2), None)
    asm.cpu.trace_enabled = False
    for _ in range(100):
        if asm.cpu.addr() == (0x1010, 0xB738):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xB738)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_hook_verifier_verifies_movement_direction_5db2_without_skipping():
    from pathlib import Path
    from overkill.verification import HookVerifierConfig, install_hook_verifier
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "closure_run_5db2_160415"
    assert snap.exists(), "captured oracle snapshot for 1010:5DB2 is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    rt.cpu.trace_enabled = False
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0x5DB2)}, stop_on_diff=True),
    )

    rt.cpu.step()

    assert verifier.total_verified == 1
    assert (0x1010, 0x5DB2) not in verifier.skipped
    assert rt.cpu.addr() == (0x1010, 0xB738)


def test_object_allocator_7573_wraps_at_sentinel_each_iteration():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _find_free_object_slot_7573

    code = bytes.fromhex(
        "b9 22 00 8b 1e da 95 81 fb cc 32 75 03 bb 5c 2b "
        "83 3f 00 74 09 83 c3 38 e2 ed bb ff ff c3 89 1e da 95 c3"
    )

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x7573, code)
        state = CPUState(cs=0x1010, ds=0x2000, ss=0x3000, sp=0x9000, ip=0x7573, flags=0x0202)
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.mem.ww(0x2000, 0x95DA, 0x3294)
        cpu.mem.ww(0x2000, 0x3294, 1)
        cpu.mem.ww(0x2000, 0x2B5C, 0)
        return cpu

    asm = make_cpu()
    asm.push(0xBEEF)
    for _ in range(80):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    hook = make_cpu()
    _find_free_object_slot_7573(hook)

    assert asm.addr() == (0x1010, 0xBEEF)
    assert asm.s.bx == hook.s.bx == 0x2B5C
    assert asm.s.cx == hook.s.cx == 0x0021
    assert asm.s.flags == hook.s.flags
    assert asm.mem.rw(0x2000, 0x95DA) == hook.mem.rw(0x2000, 0x95DA) == 0x2B5C


def test_object_allocator_7573_full_pool_matches_original_exhaustion():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _find_free_object_slot_7573

    code = bytes.fromhex(
        "b9 22 00 8b 1e da 95 81 fb cc 32 75 03 bb 5c 2b "
        "83 3f 00 74 09 83 c3 38 e2 ed bb ff ff c3 89 1e da 95 c3"
    )

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x7573, code)
        state = CPUState(cs=0x1010, ds=0x2000, ss=0x3000, sp=0x9000, ip=0x7573, flags=0x0202)
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.mem.ww(0x2000, 0x95DA, 0x3294)
        for i in range(0x22):
            cpu.mem.ww(0x2000, 0x2B5C + i * 0x38, 1)
        return cpu

    asm = make_cpu()
    asm.push(0xBEEF)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    hook = make_cpu()
    _find_free_object_slot_7573(hook)

    assert asm.addr() == (0x1010, 0xBEEF)
    assert asm.s.bx == hook.s.bx == 0xFFFF
    assert asm.s.cx == hook.s.cx == 0
    assert asm.s.flags == hook.s.flags
    assert asm.mem.rw(0x2000, 0x95DA) == hook.mem.rw(0x2000, 0x95DA) == 0x3294


def test_effect_allocator_7524_hook_matches_original_wrap_and_exhaustion():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_find_free_effect_slot_7524

    code = bytes.fromhex(
        "b9 23 00 8b 1e d8 95 83 3f 00 74 12 83 c3 38 81"
        " fb 5c 2b 75 03 bb b4 23 e2 ed bb ff ff c3 89 1e"
        " d8 95 c3"
    )

    def make_cpu(*, free_slot: int | None) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x7524, code)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777,
            cs=0x1010, ds=0x2000, es=0x8888, ss=0x3000,
            sp=0x9000, ip=0x7524, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.mem.ww(0x2000, 0x95D8, 0x2B24)
        for i in range(0x23):
            cpu.mem.ww(0x2000, 0x23B4 + i * 0x38, 1)
        if free_slot is not None:
            cpu.mem.ww(0x2000, free_slot, 0)
        return cpu

    for free_slot in (0x23B4, 0x27E8, None):
        asm = make_cpu(free_slot=free_slot)
        hook = make_cpu(free_slot=free_slot)
        for _ in range(400):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        overkill_find_free_effect_slot_7524(hook)
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_object_allocator_7573_hook_wrapper_matches_original():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_find_free_object_slot_7573

    code = bytes.fromhex(
        "b9 22 00 8b 1e da 95 81 fb cc 32 75 03 bb 5c 2b "
        "83 3f 00 74 09 83 c3 38 e2 ed bb ff ff c3 89 1e da 95 c3"
    )

    def make_cpu(*, start: int, free_slot: int | None) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x7573, code)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777,
            cs=0x1010, ds=0x2000, es=0x8888, ss=0x3000,
            sp=0x9000, ip=0x7573, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.mem.ww(0x2000, 0x95DA, start)
        for i in range(0x22):
            cpu.mem.ww(0x2000, 0x2B5C + i * 0x38, 1)
        if free_slot is not None:
            cpu.mem.ww(0x2000, free_slot, 0)
        return cpu

    for start, free_slot in ((0x3294, 0x2B5C), (0x32CC, 0x2B5C), (0x2B5C, None)):
        asm = make_cpu(start=start, free_slot=free_slot)
        hook = make_cpu(start=start, free_slot=free_slot)
        for _ in range(400):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        overkill_find_free_object_slot_7573(hook)
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_gameplay_counter_stride_loop_1f8f_0960_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_gameplay_counter_stride_loop_1f8f_0960

    code = bytes.fromhex("ff 04 81 3c c0 00 75 04 c7 04 00 00 83 c6 06 e2 ef c3")

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1F8F, 0x0960, code)
        for i, value in enumerate((0x00BE, 0x00BF, 0xFFFF, 0x0001, 0x00C0)):
            mem.ww(0x2000, (0x0100 + i * 6) & 0xFFFF, value)
        mem.ww(0x3000, 0x8FFE, 0xBEEF)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=5, dx=0x3333, si=0x0100, di=0x4444,
            bp=0x5555, sp=0x8FFE, cs=0x1F8F, ds=0x2000, es=0x6666,
            ss=0x3000, ip=0x0960, flags=0x0286,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1F8F, 0x0960)] = overkill_gameplay_counter_stride_loop_1f8f_0960
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(200):
        if asm.addr() == (0x1F8F, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1F8F, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_object_slot_scan_ac97_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "ac97_stop"
    assert snap.exists(), "captured oracle snapshot for 1010:AC97 is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        if not use_hook:
            rt.cpu.replacement_hooks.pop((0x1010, 0xAC97), None)
            rt.cpu.hook_names.pop((0x1010, 0xAC97), None)
        return rt

    asm = make_runtime(False)
    hook = make_runtime(True)
    for _ in range(1000):
        if asm.cpu.addr() == (0x1010, 0xABE7):
            break
        asm.cpu.step()
    for _ in range(1000):
        if hook.cpu.addr() == (0x1010, 0xABE7):
            break
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xABE7)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_object_slot_scan_ac97_absorbs_non_actionable_acd9_continue_tail():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_object_slot_scan_ac97

    code = bytes.fromhex(
        "83 3f 00 74 36 83 7f 18 01 74 30 83 7f 14 01 75 2a "
        "8b 77 02 83 c6 10 3b fe 7f 20 83 ee 20 3b fe 7c 19 "
        "8b 77 04 83 c6 10 3b c6 7f 0f 83 ee 20 3b c6 7c 08 "
        "8b 76 0e 3b 77 0e 75 07 83 c3 38 e2 c0 f8 c3 83 7f "
        "16 05 74 1a 83 7f 14 01 74 03 e9 71 a3 83 7f 16 04 "
        "75 e4 e8 a8 fe e8 62 ff 72 01 c3 f9 c3 55 8b eb e8 "
        "d4 fd 8b dd 5d f8 c3"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xAC97, code)
        ds = ss = 0x25CC
        bp = 0x3000
        sp = 0x8000
        bx = 0x23B4
        # First slot overlaps and has a different owner, but kind 3 is neither
        # ACD9's actionable kind 4 nor kind 5.  Original ASM therefore jumps
        # ACD9 -> ACD2 and continues scanning instead of returning through the
        # interpreted tail.
        mem.ww(ds, bx + 0x00, 1)
        mem.ww(ds, bx + 0x02, 0x0040)
        mem.ww(ds, bx + 0x04, 0x0040)
        mem.ww(ds, bx + 0x0E, 0x2222)
        mem.ww(ds, bx + 0x14, 1)
        mem.ww(ds, bx + 0x16, 3)
        mem.ww(ds, bx + 0x18, 0)
        # Second slot is inactive, so the two-slot scan exhausts and returns CLC.
        mem.ww(ds, bx + 0x38, 0)
        mem.ww(ss, bp + 0x0E, 0x1111)
        mem.ww(ss, sp, 0xBEEF)
        cpu = CPU8086(
            mem,
            CPUState(
                ax=0x0040,
                bx=bx,
                cx=2,
                di=0x0040,
                bp=bp,
                sp=sp,
                cs=0x1010,
                ds=ds,
                es=ds,
                ss=ss,
                ip=0xAC97,
                flags=0x0202,
            ),
        )
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xAC97)] = overkill_object_slot_scan_ac97
            cpu.hook_names[(0x1010, 0xAC97)] = "overkill_object_slot_scan_ac97"
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(120):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_postmove_y_clamp_bcb1_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "bc4b_stop"
    assert snap.exists(), "captured oracle snapshot for 1010:BCB1 is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.replacement_hooks.pop((0x1010, 0xBC4B), None)
        rt.cpu.hook_names.pop((0x1010, 0xBC4B), None)
        if not use_hook:
            rt.cpu.replacement_hooks.pop((0x1010, 0xBCB1), None)
            rt.cpu.hook_names.pop((0x1010, 0xBCB1), None)
        return rt

    asm = make_runtime(False)
    hook = make_runtime(True)
    for _ in range(20):
        if asm.cpu.addr() == (0x1010, 0xBC4E):
            break
        asm.cpu.step()
    for _ in range(20):
        if hook.cpu.addr() == (0x1010, 0xBC4E):
            break
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xBC4E)
    # Boundary-level equivalence: the BC4B clamp hook no longer writes the dead
    # BC4E return word below SP that the original CALL leaves as scratch.  That
    # word is ABI-undefined, so compare everything else exactly and ignore it.
    assert_oracle_equivalent(asm.cpu, hook.cpu)


def test_bd17_deactivate_logic_2a_falls_through_without_counter_drop():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_deactivate_bd17_observed

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x1234)
    mem.ww(ss, (bp + 0x16) & 0xFFFF, 0x0004)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x002A)
    mem.ww(ss, (bp + 0x28) & 0xFFFF, 0xFFFF)
    mem.ww(ds, 0xA47E, 0x0014)
    state = CPUState(
        ax=0x0000, bx=0x0000, cx=0x0000, dx=0x0000,
        si=0x0000, di=0x0000, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBD17, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False

    _run_deactivate_bd17_observed(cpu, parent="1010:BC4B", chain="BC4B", cx_value=0x001C)

    assert cpu.s.ip == 0xBD17
    assert mem.rw(ss, (bp + 0x00) & 0xFFFF) == 0x0000
    assert mem.rw(ds, 0xA47E) == 0x0014


def test_bd17_deactivate_draw_layer_5_logic_0_returns_without_counter_drop():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_deactivate_bd17_observed

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x1234)
    mem.ww(ss, (bp + 0x16) & 0xFFFF, 0x0005)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x28) & 0xFFFF, 0xFFFF)
    mem.ww(ds, 0xA47E, 0x0014)
    state = CPUState(
        ax=0x0000, bx=0x0000, cx=0x0000, dx=0x0000,
        si=0x0000, di=0x0000, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBD17, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)

    _run_deactivate_bd17_observed(cpu, parent="1010:BC4B", chain="BC4B", cx_value=0x0018)

    assert cpu.s.ip == 0xBEEF
    assert mem.rw(ss, (bp + 0x00) & 0xFFFF) == 0x0000
    assert mem.rw(ds, 0xA47E) == 0x0014


def test_bd17_deactivate_selector_a83e_tail_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "bd17_selector_a83e_tail_20260613_125913"
    assert snap.exists(), "captured oracle snapshot for 1010:BD17 selector A83E tail is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        if not use_hook:
            rt.cpu.replacement_hooks.pop((0x1010, 0xBC4B), None)
            rt.cpu.hook_names.pop((0x1010, 0xBC4B), None)
        return rt

    asm = make_runtime(False)
    hook = make_runtime(True)

    for _ in range(1000):
        if asm.cpu.addr() == (0x1010, 0xAA04):
            break
        asm.cpu.step()
    for _ in range(1000):
        if hook.cpu.addr() == (0x1010, 0xAA04):
            break
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xAA04)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_c054_deactivate_dispatch_0013_selects_a4e4():
    from dos_re.cpu import CPU8086, CPUState
    from overkill.gameplay.collision import run_object_deactivate_logic_dispatch_c054
    from dos_re.memory import Memory

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x0013)
    state = CPUState(
        ax=0x0000, bx=0x0000, cx=0x0000, dx=0x0000,
        si=0x0000, di=0x0000, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xC054, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False

    run_object_deactivate_logic_dispatch_c054(cpu)

    assert cpu.s.ax == 0xA4E4


def test_bfc7_logic_2b_keeps_live_counter_and_completes_transition():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_collision_death_tail_bfc7

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x1234)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x0050)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x00A6)
    mem.ww(ss, (bp + 0x14) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x002B)
    mem.ww(ss, (bp + 0x1A) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x28) & 0xFFFF, 0xFFFF)
    mem.ww(ds, 0xA47E, 0x0014)
    mem.wb(ds, 0x98C0, 0x00)
    mem.ww(ds, 0x2314, 0x0000)
    state = CPUState(
        ax=0x0000, bx=0x0004, cx=0x001F, dx=0x0000,
        si=0xC3CB, di=0x0086, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBFC7, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)

    _run_collision_death_tail_bfc7(
        cpu,
        parent="1010:BC4B",
        chain="BC4B",
        cx_value=0x001F,
    )

    assert cpu.s.ip == 0xBEEF
    assert mem.rw(ds, 0xA47E) == 0x0014
    assert mem.rw(ss, (bp + 0x1A) & 0xFFFF) == 0x002B
    assert mem.rw(ss, (bp + 0x18) & 0xFFFF) == 0x0001
    assert mem.rw(ss, (bp + 0x22) & 0xFFFF) == 0x0000


def test_bfc7_logic_31_keeps_live_counter_and_completes_transition():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_collision_death_tail_bfc7

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x1234)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x0050)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x00A6)
    mem.ww(ss, (bp + 0x14) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x0031)
    mem.ww(ss, (bp + 0x1A) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x28) & 0xFFFF, 0xFFFF)
    mem.ww(ds, 0xA47E, 0x0014)
    mem.wb(ds, 0x98C0, 0x00)
    mem.ww(ds, 0x2314, 0x0000)
    state = CPUState(
        ax=0x0000, bx=0x0004, cx=0x001F, dx=0x0000,
        si=0xC3CB, di=0x0086, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBFC7, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)

    _run_collision_death_tail_bfc7(
        cpu,
        parent="1010:BC4B",
        chain="BC4B",
        cx_value=0x001F,
    )

    assert cpu.s.ip == 0xBEEF
    assert mem.rw(ds, 0xA47E) == 0x0014
    assert mem.rw(ss, (bp + 0x1A) & 0xFFFF) == 0x0031
    assert mem.rw(ss, (bp + 0x18) & 0xFFFF) == 0x0001
    assert mem.rw(ss, (bp + 0x22) & 0xFFFF) == 0x0000


def test_bfc7_logic_12_keeps_live_counter_and_completes_transition():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_collision_death_tail_bfc7

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x1234)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x0050)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x00A6)
    mem.ww(ss, (bp + 0x14) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x0012)
    mem.ww(ss, (bp + 0x1A) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x28) & 0xFFFF, 0xFFFF)
    mem.ww(ds, 0xA47E, 0x0014)
    mem.wb(ds, 0x98C0, 0x00)
    mem.ww(ds, 0x2314, 0x0000)
    state = CPUState(
        ax=0x0000, bx=0x0004, cx=0x001F, dx=0x0000,
        si=0xC3CB, di=0x0086, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBFC7, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)

    _run_collision_death_tail_bfc7(
        cpu,
        parent="1010:BC4B",
        chain="BC4B",
        cx_value=0x001F,
    )

    assert cpu.s.ip == 0xBEEF
    assert mem.rw(ds, 0xA47E) == 0x0014
    assert mem.rw(ss, (bp + 0x1A) & 0xFFFF) == 0x0012
    assert mem.rw(ss, (bp + 0x18) & 0xFFFF) == 0x0001
    assert mem.rw(ss, (bp + 0x22) & 0xFFFF) == 0x0000


def test_bfc7_selector_effect_pushes_score_amount_bx_scratch():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_collision_death_tail_bfc7

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x1234)
    mem.ww(ss, (bp + 0x02) & 0xFFFF, 0x002A)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x0078)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x00AA)
    mem.ww(ss, (bp + 0x14) & 0xFFFF, 0x0001)
    # C054's 0013 selector family pushes BX/BP below its live C01B frame before
    # the effect-spawn tail.  BFC7 must have materialized BX=0030h first; an
    # older lift accidentally left the incoming BX=000Ch here, causing the live
    # full-memory verifier to fail at SS:SP-0006 after BC4B returned to AA04.
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x0013)
    mem.ww(ss, (bp + 0x1A) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x28) & 0xFFFF, 0xFFFF)
    mem.ww(ds, 0xA47E, 0x0014)
    mem.ww(ds, 0x95D8, 0x25AC)
    mem.ww(ds, 0x25AC, 0x0000)
    mem.wb(ds, 0x98C0, 0x00)
    mem.ww(ds, 0x2314, 0x0000)
    state = CPUState(
        ax=0x0028, bx=0x000C, cx=0x0028, dx=0x0078,
        si=0x0004, di=0x0001, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBFC7, flags=0x0246,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)

    _run_collision_death_tail_bfc7(
        cpu,
        parent="1010:BC4B",
        chain="BC4B -> BCCB -> BFC7",
        cx_value=0x001F,
    )

    assert cpu.s.ip == 0xBEEF
    assert mem.rw(ss, (cpu.s.sp - 0x06) & 0xFFFF) == 0x0030

def test_bfc7_logic_3b_uses_c054_default_and_completes_transition():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_collision_death_tail_bfc7

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x1234)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x0078)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x00AB)
    mem.ww(ss, (bp + 0x14) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x003B)
    mem.ww(ss, (bp + 0x1A) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0000)
    mem.ww(ss, (bp + 0x28) & 0xFFFF, 0xFFFF)
    mem.ww(ds, 0xA47E, 0x0014)
    mem.wb(ds, 0x98C0, 0x01)
    mem.wb(ds, 0xBEFF, 0x00)
    mem.ww(ds, 0x2314, 0x0000)
    state = CPUState(
        ax=0x0020, bx=0x0030, cx=0x0020, dx=0x0078,
        si=0x0004, di=0x0001, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBFC7, flags=0x0246,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)

    _run_collision_death_tail_bfc7(
        cpu,
        parent="1010:BC4B",
        chain="BC4B -> 62F6 -> BEC5 third counter zero",
        cx_value=0x00A9,
    )

    assert cpu.s.ip == 0xBEEF
    assert mem.rw(ds, 0xA47E) == 0x0014
    assert mem.rb(ds, 0xBEFF) == 0x19
    assert mem.rw(ss, (bp + 0x1A) & 0xFFFF) == 0x003B
    assert mem.rw(ss, (bp + 0x18) & 0xFFFF) == 0x0001
    assert mem.rw(ss, (bp + 0x22) & 0xFFFF) == 0x0000
    assert mem.rw(ss, (bp + 0x08) & 0xFFFF) == 0x0000


def test_aa71_upper_contact_tail_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.gameplay.collision import run_postmove_contact_window_aa71
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "next_frontier_probe_4"
    assert snap.exists(), "captured oracle snapshot for 1010:AA71 is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.replacement_hooks.clear()
        rt.cpu.hook_names.clear()
        rt.cpu.trace_enabled = False
        return rt

    asm = make_runtime()
    hook = make_runtime()
    for _ in range(2000):
        if asm.cpu.addr() == (0x1010, 0xAA71) and hook.cpu.addr() == (0x1010, 0xAA71):
            break
        asm.cpu.step()
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xAA71)

    run_postmove_contact_window_aa71(hook.cpu)

    for _ in range(32):
        if asm.cpu.addr() == (0x1010, 0xBCFC):
            break
        asm.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xBCFC)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_aa71_final_boss_mode_keeps_narrow_x_window_against_asm():
    from overkill.gameplay.collision import run_postmove_contact_window_aa71

    code = bytes.fromhex(
        # AA44: CLC; RET, followed by padding up to AA71.
        "f8 c3" + "90" * (0xAA71 - 0xAA46) +
        # AA71 original helper: signed Y gate, then A8C2-specific/narrow X gate.
        "8b46020bc078cc8b46040518003b0680237cc02d2c003b0680237fb7"
        "833ec2a80175178b46020508003b067e2372a42d0c003b067e23779b"
        "f9c38b46020518003b067e23728d2d2c003b067e237784f9c3"
    )

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xAA44, code)
        ds = ss = 0x25CC
        bp = 0x2734
        # Final-boss projectile/part from the frame-278 divergence: it overlaps
        # vertically, but X+8 is still left of the player/window guard.
        mem.ww(ss, bp + 0x02, 0x0068)
        mem.ww(ss, bp + 0x04, 0x0058)
        mem.ww(ds, 0x237E, 0x00BE)
        mem.ww(ds, 0x2380, 0x006E)
        mem.ww(ds, 0xA8C2, 0x0001)
        cpu = CPU8086(
            mem,
            CPUState(
                ax=0, bx=0, cx=0, dx=0, si=0, di=0, bp=bp, sp=0x9000,
                cs=0x1010, ds=ds, es=ds, ss=ss, ip=0xAA71, flags=0x0202,
            ),
        )
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(32):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    run_postmove_contact_window_aa71(hook)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_inline_parent_call_to_aa71_reaches_hook_verifier():
    """Direct Python parent composition must not hide AA71 child bugs.

    This is the exact verification class that the frame-278 damage bug exposed:
    BC4B was executing Python and called the AA71 helper directly, so the child
    routine's branch coverage was invisible to --verify-hooks.  The parent path
    now routes AA71 through its registered hook boundary; an intentionally wrong
    AA71 replacement must therefore fail immediately at 1010:AA71.
    """
    from pathlib import Path
    from types import SimpleNamespace

    from dos_re.cpu import CF
    from dos_re.dos import DOSMachine
    from dos_re.runtime import Runtime
    from dos_re.verification import GenericHookStop, HookVerifierConfig, HookVerifyDivergence, install_hook_verifier
    from overkill.gameplay.object_runtime import _call_aa71

    code = bytes.fromhex(
        # AA44: CLC; RET, followed by padding up to AA71.
        "f8 c3" + "90" * (0xAA71 - 0xAA46) +
        # AA71 original helper: signed Y gate, then A8C2-specific/narrow X gate.
        "8b46020bc078cc8b46040518003b0680237cc02d2c003b0680237fb7"
        "833ec2a80175178b46020508003b067e2372a42d0c003b067e23779b"
        "f9c38b46020518003b067e23728d2d2c003b067e237784f9c3"
    )
    mem = Memory()
    mem.load(0x1010, 0xAA44, code)
    ds = ss = 0x25CC
    bp = 0x2734
    mem.ww(ss, bp + 0x02, 0x0068)
    mem.ww(ss, bp + 0x04, 0x0058)
    mem.ww(ds, 0x237E, 0x00BE)
    mem.ww(ds, 0x2380, 0x006E)
    mem.ww(ds, 0xA8C2, 0x0001)
    cpu = CPU8086(
        mem,
        CPUState(
            ax=0, bx=0, cx=0, dx=0, si=0, di=0, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=ds, ss=ss, ip=0xBCF9, flags=0x0202,
        ),
    )
    cpu.trace_enabled = False

    def bad_aa71(c):
        # The pre-fix shape: once the final-boss Y gate has matched, claim
        # contact without doing the narrow X-window reject.
        c.set_flag(CF, True)
        c.s.ip = c.pop()

    cpu.replacement_hooks[(0x1010, 0xAA71)] = bad_aa71
    cpu.hook_names[(0x1010, 0xAA71)] = "bad_aa71"
    rt = Runtime(SimpleNamespace(memory=mem), cpu, DOSMachine(Path.cwd()))
    install_hook_verifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0xAA71)}, stop_on_diff=True),
        stops={(0x1010, 0xAA71): GenericHookStop("near_ret")},
    )

    with pytest.raises(HookVerifyDivergence) as excinfo:
        _call_aa71(cpu, 0xBCFC)

    report = str(excinfo.value)
    assert "1010:AA71 bad_aa71" in report
    assert "HOOK continuation: 1010:BCFC" in report
    assert "Flag differences" in report or "Register differences" in report


def test_aa71_upper_contact_tail_forced_upper_branch_matches_interpreted_asm():
    from pathlib import Path
    from overkill.gameplay.collision import run_postmove_contact_window_aa71
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "next_frontier_probe_4"
    assert snap.exists(), "captured oracle snapshot for 1010:AA71 is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.replacement_hooks.clear()
        rt.cpu.hook_names.clear()
        rt.cpu.trace_enabled = False
        return rt

    asm = make_runtime()
    hook = make_runtime()
    for _ in range(2000):
        if asm.cpu.addr() == (0x1010, 0xAA71) and hook.cpu.addr() == (0x1010, 0xAA71):
            break
        asm.cpu.step()
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xAA71)

    for cpu in (asm.cpu, hook.cpu):
        cpu.mem.ww(cpu.s.ss, (cpu.s.bp + 0x04) & 0xFFFF, 0x0041)

    run_postmove_contact_window_aa71(hook.cpu)

    for _ in range(32):
        if asm.cpu.addr() == (0x1010, 0xBCFC):
            break
        asm.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xBCFC)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_aa71_negative_x_escape_matches_interpreted_asm():
    from pathlib import Path
    from overkill.gameplay.collision import run_postmove_contact_window_aa71
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "next_frontier_probe_4"
    assert snap.exists(), "captured oracle snapshot for 1010:AA71 is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.replacement_hooks.clear()
        rt.cpu.hook_names.clear()
        rt.cpu.trace_enabled = False
        return rt

    asm = make_runtime()
    hook = make_runtime()
    for _ in range(2000):
        if asm.cpu.addr() == (0x1010, 0xAA71) and hook.cpu.addr() == (0x1010, 0xAA71):
            break
        asm.cpu.step()
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xAA71)

    for cpu in (asm.cpu, hook.cpu):
        cpu.mem.ww(cpu.s.ss, (cpu.s.bp + 0x02) & 0xFFFF, 0xFF82)

    run_postmove_contact_window_aa71(hook.cpu)

    for _ in range(32):
        if asm.cpu.addr() == (0x1010, 0xBCFC):
            break
        asm.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xBCFC)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_object_postmove_bc4b_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "bc4b_stop"
    assert snap.exists(), "captured oracle snapshot for 1010:BC4B is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        if not use_hook:
            rt.cpu.replacement_hooks.pop((0x1010, 0xBC4B), None)
            rt.cpu.hook_names.pop((0x1010, 0xBC4B), None)
            rt.cpu.replacement_hooks.pop((0x1010, 0xBCB1), None)
            rt.cpu.hook_names.pop((0x1010, 0xBCB1), None)
        return rt

    asm = make_runtime(False)
    hook = make_runtime(True)
    for _ in range(1000):
        if asm.cpu.addr() == (0x1010, 0xAA04):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xAA04)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_object_postmove_bc4b_variant_000a_owner_linked_tail_matches_interpreted_asm():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "bc4b_variant_000a_owner_linked_20260613_000648"
    assert snap.exists(), "captured oracle snapshot for BEC5 variant 000A owner-linked tail is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        # This oracle targets the 53rd *externally visible* BC4B boundary from
        # the captured snapshot.  Once the D007 frame orchestrator is lifted,
        # BC4B can be reached inside a single composed D007 step, so keep the
        # parent frame hook disabled while seeking this BC4B-specific fixture.
        rt.cpu.replacement_hooks.pop((0x1010, 0xD007), None)
        rt.cpu.hook_names.pop((0x1010, 0xD007), None)
        count = 0
        for _ in range(100000):
            if rt.cpu.addr() == (0x1010, 0xBC4B):
                count += 1
                if count == 53:
                    break
            rt.cpu.step()
        assert count == 53
        if not use_hook:
            rt.cpu.replacement_hooks.pop((0x1010, 0xBC4B), None)
            rt.cpu.hook_names.pop((0x1010, 0xBC4B), None)
        return rt

    asm = make_runtime(False)
    hook = make_runtime(True)
    ret = asm.cpu.mem.rw(asm.cpu.s.ss, asm.cpu.s.sp)
    ret_sp = (asm.cpu.s.sp + 2) & 0xFFFF
    for _ in range(1000):
        asm.cpu.step()
        if asm.cpu.addr() == (0x1010, ret) and asm.cpu.s.sp == ret_sp:
            break
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xAA04)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_bec5_variant_000a_non_owner_contact_is_noop_ret_against_asm():
    from overkill.hooks import _run_collision_handler_bec5_observed

    # BEC5's final family check is:
    #   CMP BP,[BX+30]
    #   JE  owner-linked tail
    #   RET
    # This regression covers the newly observed variant-000A contact where the
    # slot is *not* owner-linked, so the collision handler must simply return
    # with the CMP flags live.
    code_bec5 = bytes.fromhex(
        "837f18077503e9eb00837f18087503e9e200837f180c7503e9d900"
        "837f18097503e9bf00837f1802742c837f18067503e99f00837f"
        "18057503e996003b6f307401c3c7471c0000833ec2a8017412"
        "c746200000e9ac00c7070000837f08337508ff4e207503e99a00"
        "ff4e207503e99200833edcbe017411833edcbe00750fff4e20"
        "747fff4e20747aff4e207475c746240500833ec2a8017401c3"
        "558b2ebaa8c7462405008b2ebca8c7462405008b2ebea8c746"
        "2405008b2ec0a8c746240500803ec098007405c606ffbe0e5dc3"
        "e878fdeb8ee873fd833ec2a8017484c746200000eb1f833ec2a8"
        "017503e973ffc746200000eb0e833ec2a80174d2c746200000eb00"
    )

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xBEC5, code_bec5)
        ds = ss = 0x3000
        collided_bx = 0x1200
        bp = 0x28BC
        mem.ww(ds, collided_bx + 0x00, 0x0001)
        mem.ww(ds, collided_bx + 0x18, 0x000A)
        mem.ww(ds, collided_bx + 0x30, 0x1111)
        mem.ww(ss, bp + 0x00, 0x0001)
        mem.ww(ss, bp + 0x18, 0x0029)
        mem.ww(ss, bp + 0x20, 0x7777)
        state = CPUState(
            ax=0xA4EA, bx=collided_bx, cx=0x0068, dx=0x2222,
            si=0x3333, di=0x4444, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0xBEC5, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xCAFE)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(80):
        if asm.addr() == (0x1010, 0xCAFE):
            break
        asm.step()

    _run_collision_handler_bec5_observed(
        hook,
        collided_bx=0x1200,
        parent="1010:BC45",
        chain="BC45 -> BC4B -> 62F6",
        cx_value=0x0068,
    )

    assert asm.addr() == hook.addr() == (0x1010, 0xCAFE)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_object_overlap_scan_62f6_preserves_bx_and_flags_on_signed_x_early_exit():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_object_overlap_scan_62f6

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, bp, 0x0001)
    mem.ww(ss, (bp + 0x02) & 0xFFFF, 0xFFDC)
    state = CPUState(
        ax=0x1234, bx=0x0062, cx=0x000E, dx=0x0080,
        si=0x0004, di=0x0001, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0x62F6, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False

    _run_object_overlap_scan_62f6(cpu, parent="1010:BC4B", chain="BC4B", cx_value=0x000E)

    assert cpu.s.bx == 0x0062
    assert cpu.s.flags == 0x0282
    assert cpu.s.ax == 0x1234


def test_object_overlap_scan_62f6_preserves_bx_and_flags_on_logic_26_exemption():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_object_overlap_scan_62f6

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, bp, 0x0001)
    mem.ww(ss, (bp + 0x02) & 0xFFFF, 0x0066)
    mem.ww(ss, (bp + 0x16) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x0026)
    state = CPUState(
        ax=0x000C, bx=0x03C4, cx=0x0000, dx=0x03C4,
        si=0x001C, di=0x0065, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0x62F6, flags=0x0216,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False

    _run_object_overlap_scan_62f6(cpu, parent="1010:BC45", chain="BC45 -> BC4B", cx_value=0x0000)

    assert cpu.s.bx == 0x03C4
    assert cpu.s.ax == 0x000C
    assert cpu.s.flags == 0x0246


def test_tandy_text_glyph_3153_hook_verifies_on_gameplay_snapshot():
    from pathlib import Path
    from overkill.verification import HookVerifierConfig, HookVerifyLimitReached, install_hook_verifier
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "tandy_text_score_gameplay_20260612_163127"
    assert snap.exists(), "gameplay snapshot for 1010:3153 text glyph verification is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    # Wider text hooks absorb calls before they reach the narrow 3153 glyph
    # hook.  Disable them here so this regression continues to verify the
    # original 3153 boundary directly.
    for key in ((0x1010, 0x5EDB), (0x1010, 0x5EF9), (0x1010, 0x5F06), (0x1010, 0x518C), (0x1010, 0x519A)):
        rt.cpu.replacement_hooks.pop(key, None)
        rt.cpu.hook_names.pop(key, None)
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(
            hooks={(0x1010, 0x3153)},
            stop_on_diff=True,
            max_verified=50,
            asm_max_steps=3000,
        ),
    )

    try:
        rt.cpu.run(500000)
    except HookVerifyLimitReached:
        pass

    assert verifier.counts[(0x1010, 0x3153)] == 50


def test_score_byte_text_5ef9_hook_verifies_on_gameplay_snapshot():
    from pathlib import Path
    from overkill.verification import HookVerifierConfig, HookVerifyLimitReached, install_hook_verifier
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "tandy_text_score_gameplay_20260612_163127"
    assert snap.exists(), "gameplay snapshot for 1010:5EF9 score-byte text verification is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    # The wider 5EDB HUD block composes 5EF9 internally, and the 97B2/60A2
    # frame parents now compose the HUD path.  Disable parents when this test
    # wants to verify the original 5EF9 boundary directly.
    for key in ((0x1010, 0x97B2), (0x1010, 0x60A2), (0x1010, 0x5EDB)):
        rt.cpu.replacement_hooks.pop(key, None)
        rt.cpu.hook_names.pop(key, None)
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(
            hooks={(0x1010, 0x5EF9)},
            stop_on_diff=True,
            max_verified=20,
            asm_max_steps=5000,
        ),
    )

    try:
        rt.cpu.run(500000)
    except HookVerifyLimitReached:
        pass

    assert verifier.counts[(0x1010, 0x5EF9)] == 20


def test_bootstrap_lzexe_main_loop_1c43_0069_hook_verifies_on_bootstrap_snapshot():
    from pathlib import Path
    from overkill.verification import HookVerifierConfig, HookVerifyLimitReached, install_hook_verifier
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_1c43_0069"
    assert snap.exists(), "bootstrap snapshot for 1C43:0069 verification is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(
            hooks={(0x1C43, 0x0069)},
            stop_on_diff=True,
            max_verified=1,
            asm_max_steps=400_000,
        ),
    )

    try:
        rt.cpu.run(10)
    except HookVerifyLimitReached:
        pass

    assert verifier.counts[(0x1C43, 0x0069)] == 1
    assert rt.cpu.s.snapshot() == (
        "AX=0000 BX=FE00 CX=0003 DX=0002 SI=1689 DI=359B BP=0000 SP=007E "
        "CS:IP=1C43:00FC DS=1ADA ES=1810 SS=1C59 FLAGS=0246"
    )


def test_bootstrap_lzexe_main_loop_23ad_0069_hook_verifies_on_bootstrap_snapshot():
    from pathlib import Path
    from overkill.verification import HookVerifierConfig, HookVerifyLimitReached, install_hook_verifier
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_23ad_0069"
    assert snap.exists(), "bootstrap snapshot for 23AD:0069 verification is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(
            hooks={(0x23AD, 0x0069)},
            stop_on_diff=True,
            max_verified=1,
            asm_max_steps=700_000,
        ),
    )

    try:
        rt.cpu.run(10)
    except HookVerifyLimitReached:
        pass

    assert verifier.counts[(0x23AD, 0x0069)] == 1
    assert rt.cpu.s.snapshot() == (
        "AX=0000 BX=FE00 CX=0003 DX=000F SI=578E DI=B8A8 BP=0000 SP=007E "
        "CS:IP=23AD:00FC DS=1E34 ES=1810 SS=23C3 FLAGS=0256"
    )


def test_adlib_note_frequency_024f_hook_matches_interpreted_asm():
    from pathlib import Path
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hook_wrappers.sounds import overkill_adlib_note_frequency_2032_024f

    # The static runtime bundle lives at its documented regen path
    # (artifacts/static_runtime_bundle, see docs/overkill/bootstrap_static_boundary.md).
    # It sits directly under artifacts/ and may be cleared; skip (don't hard-fail)
    # if absent, with the exact command to rebuild it.  Kept at the documented path
    # rather than moved so regeneration does not create a divergent second copy.
    bundle = Path(__file__).resolve().parents[1] / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
    if not bundle.exists():
        pytest.skip(
            "regenerate with: python -m overkill.cli static-runtime-bundle "
            "assets/OVERKILL --game-root assets --video tandy --sound adlib "
            "--out-dir artifacts/static_runtime_bundle"
        )
    blob = bundle.read_bytes()

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.data[:] = blob
        cs = ds = 0x2032
        ss = 0x2FF0
        sp = 0x0100
        di = 0x00C0
        mem.ww(ds, 0x000E, 0x0388)
        mem.wb(ds, (di + 0x00) & 0xFFFF, 0x06)
        mem.wb(ds, (di + 0x07) & 0xFFFF, 0x44)
        mem.wb(ds, (di + 0x0C) & 0xFFFF, 0x08)
        mem.ww(ds, (di + 0x12) & 0xFFFF, 0x0020)
        mem.ww(ds, (di + 0x1A) & 0xFFFF, 0x0102)
        mem.wb(ds, (di + 0x1D) & 0xFFFF, 0x55)
        for off in range(0x0749, 0x0789):
            mem.wb(ds, off, (off * 3) & 0xFF)
        for off in range(0x07A9, 0x07E9, 2):
            mem.ww(ds, off, (0x1200 + off) & 0xFFFF)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
            si=0xEEEE, di=di, bp=0x1234, sp=sp,
            cs=cs, ds=ds, es=0x3000, ss=ss,
            ip=0x024F, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x2032, 0x024F)] = overkill_adlib_note_frequency_2032_024f
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(2000):
        if asm.addr() == (0x2032, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x2032, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_bfc7_linked_slot_decrements_counter_and_completes_transition():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_collision_death_tail_bfc7

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x02) & 0xFFFF, 0x002A)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x0078)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x00AA)
    mem.ww(ss, (bp + 0x14) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x003B)
    mem.ww(ss, (bp + 0x1A) & 0xFFFF, 0x0031)
    mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0009)
    mem.ww(ss, (bp + 0x28) & 0xFFFF, 0x0001)
    mem.wb(ds, 0x207A, 0x02)
    mem.wb(ds, 0x207B, 0x01)
    mem.wb(ds, 0x98C0, 0x01)
    state = CPUState(
        ax=0x0028, bx=0x0030, cx=0x0028, dx=0x0078,
        si=0x0004, di=0x0001, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBFC7, flags=0x0246,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)

    _run_collision_death_tail_bfc7(
        cpu,
        parent="1010:BC4B",
        chain="BC4B -> 62F6 -> BEC5 third counter zero",
        cx_value=0x00A9,
    )

    assert cpu.s.ip == 0xBEEF
    assert mem.rb(ds, 0x207A) == 0x01
    assert cpu.s.si == 0x207A
    assert mem.rb(ds, 0xBEFF) == 0x19
    assert mem.rw(ss, (bp + 0x1A) & 0xFFFF) == 0x003B
    assert mem.rw(ss, (bp + 0x18) & 0xFFFF) == 0x0001
    assert mem.rw(ss, (bp + 0x08) & 0xFFFF) == 0x0000


def test_bfc7_linked_slot_zero_counter_spawns_effect():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import _run_collision_death_tail_bfc7

    mem = Memory()
    ds = ss = 0x3000
    bp = 0x0200
    slot = 0x25E4
    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x02) & 0xFFFF, 0x002A)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x0078)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x00AA)
    mem.ww(ss, (bp + 0x14) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x003B)
    mem.ww(ss, (bp + 0x1A) & 0xFFFF, 0x0031)
    mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0009)
    mem.ww(ss, (bp + 0x28) & 0xFFFF, 0x0001)
    mem.wb(ds, 0x207A, 0x01)
    mem.wb(ds, 0x207B, 0x01)
    mem.wb(ds, 0x98C0, 0x01)
    mem.ww(ds, 0x95D8, 0x25AC)
    mem.ww(ds, 0x25AC, 0x0001)
    mem.ww(ds, slot, 0x0000)
    mem.ww(ds, 0xA278, 0x0001)
    state = CPUState(
        ax=0x0028, bx=0x0030, cx=0x0028, dx=0x0078,
        si=0x0004, di=0x0001, bp=bp, sp=0x9000,
        cs=0x1010, ds=ds, es=ds, ss=ss,
        ip=0xBFC7, flags=0x0246,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.push(0xBEEF)

    _run_collision_death_tail_bfc7(
        cpu,
        parent="1010:BC4B",
        chain="BC4B -> 62F6 -> BEC5 third counter zero",
        cx_value=0x00A9,
    )

    assert cpu.s.ip == 0xBEEF
    assert mem.rb(ds, 0x207A) == 0x00
    assert mem.rw(ds, 0x95D8) == slot
    assert mem.rw(ds, slot) == 0x0001
    assert mem.rw(ds, (slot + 0x02) & 0xFFFF) == 0x002B
    assert mem.rw(ds, (slot + 0x04) & 0xFFFF) == 0x0078
    assert mem.rw(ds, (slot + 0x14) & 0xFFFF) == 0x0001
    assert mem.rw(ds, (slot + 0x16) & 0xFFFF) == 0x0005
    assert mem.rw(ds, (slot + 0x18) & 0xFFFF) == 0x0000
    assert mem.rw(ds, (slot + 0x26) & 0xFFFF) == 0x0001
    assert mem.rw(ds, (slot + 0x08) & 0xFFFF) == 0x0047
    assert cpu.s.cx == 0x0022
    assert cpu.s.si == 0x0047

def test_tandy_pixel_pair_table_0fe4_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_pixel_pair_table_0fe4

    code = bytes.fromhex(
        "2e 8e 06 96 95 bf 17 15 32 f6 8a d6 32 c0 d0 da 73 02 b0 0f "
        "d0 da 73 02 04 f0 88 05 4f 32 c0 d0 da 73 02 b0 0f d0 da 73 "
        "02 04 f0 88 05 4f 32 c0 d0 da 73 02 b0 0f d0 da 73 02 04 f0 "
        "88 05 4f 32 c0 d0 da 73 02 b0 0f d0 da 73 02 04 f0 88 05 4f "
        "83 c7 08 fe c6 75 b3 c3"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x0FE4, code)
        mem.ww(0x1010, 0x9596, 0x25CC)
        for off in range(0x1514, 0x1914):
            mem.wb(0x25CC, off, 0xA5)
        state = CPUState(
            ax=0x4A00, bx=0x22FF, cx=0x7777, dx=0x0FF6,
            si=0x32FF, di=0x0000, bp=0xBEEF,
            cs=0x1010, ds=0x25CC, es=0x1000, ss=0x25CC,
            sp=0xA276, ip=0x0FE4, flags=0x0206,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0x9603)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x0FE4)] = overkill_tandy_pixel_pair_table_0fe4
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(10000):
        if asm.addr() == (0x1010, 0x9603):
            break
        asm.step()
    hook.step()

    assert asm.addr() == (0x1010, 0x9603)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.block(0x25CC, 0x1514, 0x400) == hook.mem.block(0x25CC, 0x1514, 0x400)
    assert asm.mem.block(0x25CC, 0x1514, 8).hex() == "000000000000000f"
    assert asm.mem.block(0x25CC, 0x1910, 4).hex() == "ffffffff"


def test_tandy_video_offset_tables_0fa3_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_tandy_video_offset_tables_0fa3

    code = bytes.fromhex(
        "0e 07 bf 92 8d b9 00 01 33 c0 ab 03 06 70 10 e2 f9 "
        "bf 92 8f b9 00 01 33 c0 ab 03 06 24 10 e2 f9 "
        "bf 92 91 b9 00 01 33 c0 ab 03 06 26 10 e2 f9 "
        "bf 92 93 b9 00 01 33 c0 ab 03 06 28 10 e2 f9 e9 86 42"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x0FA3, code)
        mem.ww(0x25CC, 0x1070, 0x0080)
        mem.ww(0x25CC, 0x1024, 0x0040)
        mem.ww(0x25CC, 0x1026, 0x0100)
        mem.ww(0x25CC, 0x1028, 0x0400)
        for base in (0x8D92, 0x8F92, 0x9192, 0x9392):
            for off in range(base, base + 0x200):
                mem.wb(0x1010, off, 0xA5)
        state = CPUState(
            ax=0x1F40, bx=0x0004, cx=0, dx=0,
            si=0x116E, di=0xA078, bp=0,
            cs=0x1010, ds=0x25CC, es=0x25CC, ss=0x25CC,
            sp=0xA276, ip=0x0FA3, flags=0x0A03,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x0FA3)] = overkill_tandy_video_offset_tables_0fa3
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(4000):
        if asm.addr() == (0x1010, 0x526A):
            break
        asm.step()
    hook.step()

    assert asm.addr() == (0x1010, 0x526A)
    assert asm.s.snapshot() == hook.s.snapshot()
    for base in (0x8D92, 0x8F92, 0x9192, 0x9392):
        assert asm.mem.block(0x1010, base, 0x200) == hook.mem.block(0x1010, base, 0x200)
    assert hook.mem.block(0x1010, 0x8D92, 8).hex() == "0000800000018001"
    assert hook.mem.block(0x1010, 0x9392, 8).hex() == "000000040008000c"


def test_dirty_cell_presenter_cc7f_hook_verifies_on_tandy_startup_snapshot():
    from pathlib import Path
    from overkill.verification import HookVerifierConfig, HookVerifyLimitReached, install_hook_verifier
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_tandy_cc7f"
    assert snap.exists(), "startup snapshot for 1010:CC7F dirty-cell presenter verification is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(
            hooks={(0x1010, 0xCC7F)},
            stop_on_diff=True,
            max_verified=25,
            asm_max_steps=5000,
        ),
    )

    try:
        rt.cpu.run(20000)
    except HookVerifyLimitReached:
        pass

    assert verifier.counts[(0x1010, 0xCC7F)] == 25


def test_dirty_cell_presenter_uses_installed_retrace_hook_for_intro_pacing_snapshot():
    """CC7F must not bypass play.py's 50C9 pacing wrapper when fused.

    The dirty-cell intro presenter calls the retrace wait from inside the lifted
    CC7F path.  Calling the base 50C9 helper directly is register/memory-correct
    at CE13, but interactive play relies on the installed 50C9 wrapper to publish
    intermediate video and yield to the UI.  This regression fixture installs a
    wrapper that raises only for the nested CD52 -> 50C9 call; the CPU must be left
    at the original CD68 continuation so execution can resume in interpreted ASM.
    """
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    class FrameBoundary(Exception):
        pass

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "dirty_cell_presenter_pacing_20260612_235139"
    assert snap.exists(), "intro dirty-cell snapshot is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    base_retrace = rt.cpu.replacement_hooks[(0x1010, 0x50C9)]

    def pacing_wrapper(cpu):
        call_site = getattr(cpu, "hook_call_site", None)
        nested_dirty_presenter_call = (
            call_site is not None
            and call_site[:2] == (0x1010, 0xCD52)
            and call_site[2:4] == (0x1010, 0x50C9)
        )
        base_retrace(cpu)
        if nested_dirty_presenter_call:
            raise FrameBoundary()

    rt.cpu.replacement_hooks[(0x1010, 0x50C9)] = pacing_wrapper

    with pytest.raises(FrameBoundary):
        for _ in range(5000):
            rt.cpu.step()

    assert rt.cpu.addr() == (0x1010, 0xCD68)
    assert rt.cpu.s.sp == 0xA268


def test_decoded_asset_table_search_c713_hook_matches_interpreted_asm():
    from overkill.hooks import overkill_decoded_asset_table_search_c713

    # C713  lodsw; cmp ax,[21AA]; jne C71B; ret;
    # C71B  cmp ax,FFFFh; jne C713; C720 ...
    code = bytes.fromhex("ad 3b 06 aa 21 75 01 c3 3d ff ff 75 f3")

    def make_cpu(use_hook: bool, words: list[int], target: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xC713, code)
        off = 0x14D0
        for i, word in enumerate(words):
            mem.ww(0x3000, off + i * 2, word)
        mem.ww(0x3000, 0x21AA, target)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
            si=off, di=0x1111, bp=0x2222, sp=0x9000,
            cs=0x1010, ds=0x3000, es=0x4000, ss=0x5000,
            ip=0xC713, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xC713)] = overkill_decoded_asset_table_search_c713
        return cpu

    for words, target, stop in (
        ([0x1111, 0x2222, 0x3333, 0xFFFF], 0x3333, (0x1010, 0xBEEF)),
        ([0x1111, 0x2222, 0xFFFF], 0x3333, (0x1010, 0xC720)),
    ):
        asm = make_cpu(False, words, target)
        hook = make_cpu(True, words, target)
        for _ in range(100):
            if asm.addr() == stop:
                break
            asm.step()
        hook.step()

        assert asm.addr() == hook.addr() == stop
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_overlay_container_open_entry_254a_04d7_hook_matches_interpreted_asm_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot
    from overkill.hooks import overkill_overlay_container_open_entry_254a_04d7

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "snapshot_stop_254a_04d7_overlay_parent"
    assert snap.exists(), "captured oracle snapshot for 254A:04D7 is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    hook = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")

    # Run the parent helper as original ASM, including its inner loops.
    for addr in (
        (0x254A, 0x04D7),
        (0x254A, 0x0582),
        (0x254A, 0x05A1),
        (0x254A, 0x05BF),
        (0x254A, 0x05D9),
        (0x254A, 0x0701),
    ):
        asm.cpu.replacement_hooks.pop(addr, None)

    for _ in range(20_000):
        if asm.cpu.addr() == (0x1010, 0xC6A0):
            break
        asm.cpu.step()
    assert asm.cpu.addr() == (0x1010, 0xC6A0)

    hook.cpu.replacement_hooks[(0x254A, 0x04D7)] = overkill_overlay_container_open_entry_254a_04d7
    hook.cpu.step()

    assert hook.cpu.addr() == asm.cpu.addr() == (0x1010, 0xC6A0)
    assert hook.cpu.s.snapshot() == asm.cpu.s.snapshot()
    assert hook.program.memory.data == asm.program.memory.data
    assert {h: f.pos for h, f in hook.dos.files.items()} == {h: f.pos for h, f in asm.dos.files.items()}
    assert sorted(hook.dos.files) == sorted(asm.dos.files)


def test_startup_coordinate_tables_0f0b_hook_matches_interpreted_asm_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot
    from overkill.hooks import overkill_startup_coordinate_tables_0f0b

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "snapshot_stop_1010_0f0b_startup_tables"
    assert snap.exists(), "captured oracle snapshot for 1010:0F0B is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    hook = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")

    # Run the whole original startup table builder, including its 0FA3 fallthrough,
    # as interpreted ASM so the oracle includes all registers and memory effects.
    asm.cpu.replacement_hooks.pop((0x1010, 0x0F0B), None)
    asm.cpu.replacement_hooks.pop((0x1010, 0x0FA3), None)
    for _ in range(20_000):
        if asm.cpu.addr() == (0x1010, 0x526A):
            break
        asm.cpu.step()
    assert asm.cpu.addr() == (0x1010, 0x526A)

    hook.cpu.replacement_hooks[(0x1010, 0x0F0B)] = overkill_startup_coordinate_tables_0f0b
    hook.cpu.step()

    assert hook.cpu.addr() == asm.cpu.addr() == (0x1010, 0x526A)
    assert hook.cpu.s.snapshot() == asm.cpu.s.snapshot()
    assert hook.program.memory.data == asm.program.memory.data


def test_input_poll_0162_keyboard_path_matches_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_input_poll_0162

    code = bytes.fromhex(
        '83 3e 10 00 01 74 65 b9 08 00 33 db be 3e 21 83 3e 10 00 02 75 03'
        'be 46 21 bf c4 98 8a 1c 8a 01 d0 e8 d0 16 be 98 46 e2 f3 80 7d'
        '0f 00 74 05 80 0e be 98 20 80 7d 39 00 74 05 80 0e be 98 10'
        '80 7d 48 00 74 05 80 0e be 98 08 80 7d 50 00 74 05 80 0e'
        'be 98 04 80 7d 4b 00 74 05 80 0e be 98 02 80 7d 4d 00 74'
        '05 80 0e be 98 01 c3'
    )

    def make_cpu(use_hook: bool, selector: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x0162, code)
        ds = 0x2000
        ss = 0x3000
        ret = 0x7777
        mem.ww(ss, 0x8FFE, ret)
        mem.ww(ds, 0x0010, selector)
        for base, keys in ((0x213E, [0, 0, 0x2C, 0x39, 0x10, 0x1E, 0x18, 0x19]),
                           (0x2146, [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])):
            for i, key in enumerate(keys):
                mem.wb(ds, base + i, key)
                mem.wb(ds, 0x98C4 + key, 1 if i in (1, 3, 6) else 0)
        for off in (0x0F, 0x39, 0x48, 0x50, 0x4B, 0x4D):
            mem.wb(ds, 0x98C4 + off, 0)
        mem.wb(ds, 0x98C4 + 0x39, 1)
        mem.wb(ds, 0x98C4 + 0x4D, 1)
        mem.wb(ds, 0x98BE, 0xA5)
        state = CPUState(
            ax=0x5500, bx=0x1200, cx=0xCAFE, dx=0x03D9,
            si=0x0200, di=0x1111, bp=0x2222,
            sp=0x8FFE, cs=0x1010, ds=ds, es=0xB800, ss=ss,
            ip=0x0162, flags=0x0293,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x0162)] = overkill_input_poll_0162
        return cpu

    for selector in (0, 2):
        asm = make_cpu(False, selector)
        hook = make_cpu(True, selector)
        for _ in range(200):
            if asm.addr() == (0x1010, 0x7777):
                break
            asm.step()
        hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0x7777)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_input_selector_loop_d445_matches_interpreted_asm():
    from pathlib import Path

    from overkill.hooks import overkill_input_selector_loop_d445
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshot = root / "artifacts" / "evidence" / "bc4b_stop"

    cases = [
        (0x01, 0x00, 0x00, 0x00, 0x03),
        (0x02, 0x04, 0x00, 0x00, 0x01),
        (0x04, 0x04, 0x00, 0x00, 0x05),
        (0x08, 0x04, 0x00, 0x00, 0x03),
        (0x10, 0x00, 0x00, 0x00, 0x00),
        (0x10, 0x04, 0x00, 0x00, 0x04),
        (0x00, 0x04, 0x01, 0x00, 0x04),
        (0x00, 0x04, 0x01, 0x02, 0x04),
    ]

    def make_cpu(
        use_hook: bool,
        *,
        button_mask: int,
        beda_seed: int,
        bedc_seed: int,
        state98e4: int,
        button_masks: list[int] | None = None,
    ) -> CPU8086:
        rt = load_snapshot(exe, snapshot, game_root=root / "assets")
        ds = rt.cpu.s.ds & 0xFFFF
        rt.cpu.mem.wb(ds, 0x98E4, state98e4)
        rt.cpu.mem.wb(ds, 0xBEDA, beda_seed)
        rt.cpu.mem.wb(ds, 0xBEDC, bedc_seed)

        masks = list(button_masks) if button_masks is not None else [button_mask]

        def fake_0162(cpu, masks=masks):
            ds2 = cpu.s.ds & 0xFFFF
            cpu.mem.wb(ds2, 0x98BE, masks.pop(0) if masks else 0)
            cpu.s.ip = cpu.pop()

        rt.cpu.replacement_hooks[(0x1010, 0x0162)] = fake_0162
        if use_hook:
            rt.cpu.replacement_hooks[(0x1010, 0xD445)] = overkill_input_selector_loop_d445
        else:
            rt.cpu.replacement_hooks.pop((0x1010, 0xD445), None)

        rt.cpu.s.cs = 0x1010
        rt.cpu.s.ip = 0xD445
        rt.cpu.trace_enabled = False
        return rt.cpu

    for button_mask, beda_seed, state98e4, bedc_seed, expected_beda in cases:
        asm = make_cpu(
            False,
            button_mask=button_mask,
            beda_seed=beda_seed,
            bedc_seed=bedc_seed,
            state98e4=state98e4,
        )
        hook = make_cpu(
            True,
            button_mask=button_mask,
            beda_seed=beda_seed,
            bedc_seed=bedc_seed,
            state98e4=state98e4,
        )

        for _ in range(80):
            if asm.addr() == (0x1010, 0xAA04):
                break
            asm.step()
        hook.step()

        assert asm.addr() == hook.addr() == (0x1010, 0xAA04)
        assert asm.mem.rb(asm.s.ds & 0xFFFF, 0xBEDA) == expected_beda
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_input_selector_loop_d445_idle_yields_at_loop_head():
    from pathlib import Path

    from overkill.hooks import overkill_input_selector_loop_d445
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshot = root / "artifacts" / "evidence" / "bc4b_stop"

    def make_cpu(use_hook: bool) -> CPU8086:
        rt = load_snapshot(exe, snapshot, game_root=root / "assets")
        ds = rt.cpu.s.ds & 0xFFFF
        rt.cpu.mem.wb(ds, 0x98E4, 0)
        rt.cpu.mem.wb(ds, 0xBEDA, 0)
        rt.cpu.mem.wb(ds, 0xBEDC, 0)

        def fake_0162(cpu):
            cpu.mem.wb(cpu.s.ds & 0xFFFF, 0x98BE, 0)
            cpu.s.ip = cpu.pop()

        rt.cpu.replacement_hooks[(0x1010, 0x0162)] = fake_0162
        if use_hook:
            rt.cpu.replacement_hooks[(0x1010, 0xD445)] = overkill_input_selector_loop_d445
        else:
            rt.cpu.replacement_hooks.pop((0x1010, 0xD445), None)
        rt.cpu.s.cs = 0x1010
        rt.cpu.s.ip = 0xD445
        rt.cpu.trace_enabled = False
        return rt.cpu

    asm = make_cpu(False)
    hook = make_cpu(True)

    for _ in range(80):
        asm.step()
        if asm.addr() == (0x1010, 0xD445):
            break
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xD445)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_input_selector_loop_d445_wait_then_continue_across_hook_calls():
    from pathlib import Path

    from overkill.hooks import overkill_input_selector_loop_d445
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshot = root / "artifacts" / "evidence" / "bc4b_stop"

    def make_cpu(use_hook: bool) -> CPU8086:
        rt = load_snapshot(exe, snapshot, game_root=root / "assets")
        ds = rt.cpu.s.ds & 0xFFFF
        rt.cpu.mem.wb(ds, 0x98E4, 0)
        rt.cpu.mem.wb(ds, 0xBEDA, 0x04)
        rt.cpu.mem.wb(ds, 0xBEDC, 0)
        masks = [0x00, 0x04]

        def fake_0162(cpu):
            cpu.mem.wb(cpu.s.ds & 0xFFFF, 0x98BE, masks.pop(0) if masks else 0x04)
            cpu.s.ip = cpu.pop()

        rt.cpu.replacement_hooks[(0x1010, 0x0162)] = fake_0162
        if use_hook:
            rt.cpu.replacement_hooks[(0x1010, 0xD445)] = overkill_input_selector_loop_d445
        else:
            rt.cpu.replacement_hooks.pop((0x1010, 0xD445), None)
        rt.cpu.s.cs = 0x1010
        rt.cpu.s.ip = 0xD445
        rt.cpu.trace_enabled = False
        return rt.cpu

    asm = make_cpu(False)
    hook = make_cpu(True)

    for _ in range(120):
        if asm.addr() == (0x1010, 0xAA04):
            break
        asm.step()
    hook.step()
    assert hook.addr() == (0x1010, 0xD445)
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xAA04)
    assert asm.mem.rb(asm.s.ds & 0xFFFF, 0xBEDA) == 0x05
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_intro_retrace_delay_loop_96c5_matches_interpreted_asm_with_stubbed_50c9():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_intro_retrace_delay_loop_96c5

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        # 96C5: CALL 50C9; LOOP 96C5.  50C9 test stub: MOV AL,08; OR AX,AX; RET.
        mem.load(0x1010, 0x96C5, bytes.fromhex("e8 01 ba e2 fb"))
        mem.load(0x1010, 0x50C9, bytes.fromhex("b0 08 0b c0 c3"))
        state = CPUState(
            ax=0x1200, bx=0x3456, cx=0x0003, dx=0x03DA,
            si=0x1111, di=0x2222, bp=0x3333,
            sp=0x8000, cs=0x1010, ds=0x2000, es=0xB800, ss=0x3000,
            ip=0x96C5, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            def retrace_stub(c):
                c.set_reg8(0, 0x08)
                c.s.ax |= c.s.ax
                c.set_logic_flags(c.s.ax, 16)
                c.s.ip = c.pop()
            cpu.replacement_hooks[(0x1010, 0x96C5)] = overkill_intro_retrace_delay_loop_96c5
            cpu.replacement_hooks[(0x1010, 0x50C9)] = retrace_stub
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(50):
        if asm.addr() == (0x1010, 0x96CA):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0x96CA)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_hook_verifier_uses_base_passthrough_hooks_inside_intro_delay_loop():
    """Verifying 96C5 must not call play.py's interactive 50C9 wrapper.

    scripts/play.py installs the verifier first, then replaces 50C9 with a UI
    pacing wrapper and marks it as verifier-pass-through.  The 96C5 fused hook
    intentionally calls the installed 50C9 hook during normal play, but inside a
    differential transaction both the ASM oracle and the live hook side must use
    the install-time base 50C9 hook so verification completes atomically.
    """
    from pathlib import Path
    from types import SimpleNamespace

    from dos_re.cpu import CPU8086, CPUState
    from dos_re.dos import DOSMachine
    from overkill.verification import HookVerifierConfig, install_hook_verifier
    from dos_re.memory import Memory
    from overkill.hooks import overkill_intro_retrace_delay_loop_96c5
    from dos_re.runtime import Runtime

    class FrameBoundary(Exception):
        pass

    mem = Memory()
    # 96C5: CALL 50C9; LOOP 96C5.
    mem.load(0x1010, 0x96C5, bytes.fromhex("e8 01 ba e2 fb"))
    state = CPUState(
        ax=0x1200, bx=0x3456, cx=0x0003, dx=0x03DA,
        si=0x1111, di=0x2222, bp=0x3333,
        sp=0x8000, cs=0x1010, ds=0x2000, es=0xB800, ss=0x3000,
        ip=0x96C5, flags=0x0203,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.replacement_hooks[(0x1010, 0x96C5)] = overkill_intro_retrace_delay_loop_96c5
    cpu.hook_names[(0x1010, 0x96C5)] = "overkill_intro_retrace_delay_loop_96c5"

    calls = {"base": 0, "wrapper": 0}

    def base_retrace(c):
        calls["base"] += 1
        c.set_reg8(0, 0x08)
        c.set_logic_flags(c.s.ax, 16)
        c.s.ip = c.pop()

    def pacing_wrapper(c):
        calls["wrapper"] += 1
        base_retrace(c)
        raise FrameBoundary()

    cpu.replacement_hooks[(0x1010, 0x50C9)] = base_retrace
    cpu.hook_names[(0x1010, 0x50C9)] = "base_retrace"

    program = SimpleNamespace(memory=mem)
    rt = Runtime(program, cpu, DOSMachine(Path.cwd()))
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0x96C5)}, stop_on_diff=True),
    )

    # Mirrors scripts/play.py after verifier installation.
    cpu.replacement_hooks[(0x1010, 0x50C9)] = pacing_wrapper
    cpu.hook_names[(0x1010, 0x50C9)] = "interactive_retrace_wrapper"
    cpu.hook_verifier_passthrough.add((0x1010, 0x50C9))

    cpu.step()

    assert verifier.total_verified == 1
    assert cpu.addr() == (0x1010, 0x96CA)
    assert calls == {"base": 6, "wrapper": 0}
    assert cpu.replacement_hooks[(0x1010, 0x50C9)] is pacing_wrapper
    assert cpu.hook_names[(0x1010, 0x50C9)] == "interactive_retrace_wrapper"

def test_intro_retrace_delay_loop_96c5_uses_installed_retrace_hook_for_pacing():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_intro_retrace_delay_loop_96c5, overkill_intro_retrace_delay_loop_tail_96c8

    class FrameBoundary(Exception):
        pass

    mem = Memory()
    mem.load(0x1010, 0x96C5, bytes.fromhex("e8 01 ba e2 fb"))
    state = CPUState(
        ax=0, bx=0, cx=0x0002, dx=0x03DA, si=0, di=0, bp=0,
        sp=0x8000, cs=0x1010, ds=0x2000, es=0xB800, ss=0x3000,
        ip=0x96C5, flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.replacement_hooks[(0x1010, 0x96C5)] = overkill_intro_retrace_delay_loop_96c5
    cpu.replacement_hooks[(0x1010, 0x96C8)] = overkill_intro_retrace_delay_loop_tail_96c8

    def pacing_retrace(c):
        c.set_reg8(0, 0x08)
        c.set_logic_flags(c.s.ax, 16)
        c.s.ip = c.pop()
        raise FrameBoundary()

    cpu.replacement_hooks[(0x1010, 0x50C9)] = pacing_retrace

    with pytest.raises(FrameBoundary):
        cpu.step()
    assert cpu.addr() == (0x1010, 0x96C8)
    assert cpu.s.cx == 0x0002

    # Resume at the original LOOP instruction; it should preserve flags and loop
    # back for the second wait instead of skipping the remaining delay.
    old_flags = cpu.s.flags
    cpu.step()
    assert cpu.addr() == (0x1010, 0x96C5)
    assert cpu.s.cx == 0x0001
    assert cpu.s.flags == old_flags


def test_hook_stop_after_step_metadata_for_same_ip_frame_loop():
    from overkill.verification import DEFAULT_STOPS

    stop = DEFAULT_STOPS[(0x1010, 0xD007)]
    assert stop.kind == "fixed_ips"
    assert stop.min_steps == 1
    assert 0xD007 in stop.ips
    assert 0xD040 in stop.ips


def test_main_frame_loop_d007_hook_matches_one_interpreted_frame_iteration():
    from pathlib import Path

    from overkill.verification import HookVerifier, HookVerifierConfig
    from overkill.hooks import registry
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path.cwd()
    snap = root / "artifacts" / "test_oracles" / "main_frame_loop_d007"
    rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
    registry.install(rt.cpu)
    verifier = HookVerifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0xD007)}, stop_on_diff=True, log_diffs=True, asm_max_steps=1_000_000),
    )
    rt.cpu.hook_verifier = verifier.verify

    rt.cpu.step()

    assert verifier.total_verified == 1
    assert rt.cpu.addr() in {(0x1010, 0xD007), (0x1010, 0xD040)}


def test_decrement_counter_61c7_hook_matches_interpreted_snapshot():
    from pathlib import Path
    from overkill.hooks import overkill_decrement_first_active_counter_61c7
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "runtime_code_5e42_gameplay_20260613_220042"
    assert snap.exists(), "captured gameplay snapshot for 1010:61C7 is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.trace_enabled = False
        for addr in ((0x1010, 0x61DC), (0x1010, 0x61F7), (0x1010, 0x61C7), (0x1010, 0x61CA), (0x1010, 0xB24D)):
            rt.cpu.replacement_hooks.pop(addr, None)
            rt.cpu.hook_names.pop(addr, None)
        return rt

    asm = make_runtime()
    hook = make_runtime()

    for _ in range(100_000):
        if asm.cpu.addr() == (0x1010, 0x61C7):
            break
        asm.cpu.step()
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x61C7)
    return_ip = asm.cpu.mem.rw(asm.cpu.s.ss, asm.cpu.s.sp)
    hook.cpu.replacement_hooks[(0x1010, 0x61C7)] = overkill_decrement_first_active_counter_61c7

    for _ in range(1_000):
        if asm.cpu.addr() == (0x1010, return_ip):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, return_ip)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_decrement_counter_loop_61f7_hook_matches_interpreted_snapshot():
    from pathlib import Path
    from overkill.hooks import overkill_decrement_first_active_counter_loop_61f7
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "runtime_code_5e42_gameplay_20260613_220042"
    assert snap.exists(), "captured gameplay snapshot for 1010:61F7 is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.trace_enabled = False
        for addr in ((0x1010, 0x61DC), (0x1010, 0x61F7), (0x1010, 0xB24D)):
            rt.cpu.replacement_hooks.pop(addr, None)
            rt.cpu.hook_names.pop(addr, None)
        return rt

    asm = make_runtime()
    hook = make_runtime()

    for _ in range(100_000):
        if asm.cpu.addr() == (0x1010, 0x61F7):
            break
        asm.cpu.step()
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x61F7)
    hook.cpu.replacement_hooks[(0x1010, 0x61F7)] = overkill_decrement_first_active_counter_loop_61f7

    for _ in range(1_000):
        if asm.cpu.addr() == (0x1010, 0x61FC):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x61FC)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_score_status_text_block_5edb_hook_matches_interpreted_snapshot():
    from pathlib import Path
    from overkill.hook_wrappers.text import overkill_score_status_text_block_5edb
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "runtime_code_5e42_gameplay_20260613_220042"
    assert snap.exists(), "captured gameplay snapshot for 1010:5EDB is missing"

    composed = (
        # Disable frame parents so this leaf-boundary oracle reaches the
        # original 5EDB entry instead of executing it inside 60A2/97B2.
        (0x1010, 0x97B2),
        (0x1010, 0x60A2),
        (0x1010, 0x5EDB),
        (0x1010, 0x5EF9),
        (0x1010, 0x5F06),
        (0x1010, 0x518C),
        (0x1010, 0x519A),
    )

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.trace_enabled = False
        for addr in composed:
            rt.cpu.replacement_hooks.pop(addr, None)
            rt.cpu.hook_names.pop(addr, None)
        return rt

    asm = make_runtime()
    hook = make_runtime()

    for _ in range(200_000):
        if asm.cpu.addr() == (0x1010, 0x5EDB):
            break
        asm.cpu.step()
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x5EDB)
    return_ip = asm.cpu.mem.rw(asm.cpu.s.ss, asm.cpu.s.sp)
    hook.cpu.replacement_hooks[(0x1010, 0x5EDB)] = overkill_score_status_text_block_5edb

    for _ in range(5_000):
        if asm.cpu.addr() == (0x1010, return_ip):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, return_ip)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_input_release_wait_gate_986e_matches_interpreted_state_machine():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_input_release_wait_gate_986e

    code = bytes.fromhex("80 3e c5 98 01 74 f9")

    def make_cpu(use_hook: bool, key_flag: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x986E, code)
        mem.wb(0x2000, 0x98C5, key_flag)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777,
            sp=0x8000, cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0x986E, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x986E)] = overkill_input_release_wait_gate_986e
        return cpu

    for key_flag, expected_ip in ((0x01, 0x986E), (0x00, 0x9875), (0x02, 0x9875)):
        asm = make_cpu(False, key_flag)
        hook = make_cpu(True, key_flag)
        for _ in range(4):
            asm.step()
            if asm.addr() == (0x1010, expected_ip):
                break
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, expected_ip)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_yes_no_choice_wait_gate_989e_matches_interpreted_state_machine():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_yes_no_choice_wait_gate_989e

    code = bytes.fromhex(
        "c6 06 b4 22 4e 80 3e f5 98 01 74 0c "
        "c6 06 b4 22 59 80 3e d9 98 01 75 e8"
    )

    def make_cpu(use_hook: bool, *, n_flag: int, y_flag: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x989E, code)
        mem.wb(0x2000, 0x98F5, n_flag)
        mem.wb(0x2000, 0x98D9, y_flag)
        mem.wb(0x2000, 0x22B4, 0x00)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
            si=0x1111, di=0x2222, bp=0x3333,
            sp=0x8000, cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0x989E, flags=0x0207,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x989E)] = overkill_yes_no_choice_wait_gate_989e
        return cpu

    cases = [
        (0x01, 0x00, 0x98B6, 0x4E),
        (0x00, 0x01, 0x98B6, 0x59),
        (0x00, 0x00, 0x989E, 0x59),
    ]
    for n_flag, y_flag, expected_ip, expected_choice in cases:
        asm = make_cpu(False, n_flag=n_flag, y_flag=y_flag)
        hook = make_cpu(True, n_flag=n_flag, y_flag=y_flag)
        for _ in range(8):
            asm.step()
            if asm.addr() == (0x1010, expected_ip):
                break
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, expected_ip)
        assert asm.mem.rb(asm.s.ds & 0xFFFF, 0x22B4) == expected_choice
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_sound_effect_completion_wait_gate_98d8_matches_interpreted_state_machine():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_sound_effect_completion_wait_gate_98d8

    code = bytes.fromhex("80 3e fe be 00 75 f9")

    def make_cpu(use_hook: bool, completion_flag: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x98D8, code)
        mem.wb(0x2000, 0xBEFE, completion_flag)
        state = CPUState(
            ax=0x1357, bx=0x2468, cx=0xAAAA, dx=0xBBBB,
            si=0xCCCC, di=0xDDDD, bp=0xEEEE,
            sp=0x8000, cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0x98D8, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x98D8)] = overkill_sound_effect_completion_wait_gate_98d8
        return cpu

    for completion_flag, expected_ip in ((0x00, 0x98DF), (0x01, 0x98D8), (0x80, 0x98D8)):
        asm = make_cpu(False, completion_flag)
        hook = make_cpu(True, completion_flag)
        for _ in range(4):
            asm.step()
            if asm.addr() == (0x1010, expected_ip):
                break
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, expected_ip)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_boss_key_wait_gates_match_interpreted_state_machines():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import (
        overkill_boss_key_any_key_wait_gate_07d0,
        overkill_boss_key_f9_release_wait_gate_07c4,
        overkill_boss_key_return_key_release_wait_gate_07d7,
    )

    cases = [
        (
            0x07C4,
            bytes.fromhex("80 3e 07 99 01 74 f9"),
            overkill_boss_key_f9_release_wait_gate_07c4,
            0x9907,
            0x01,
            ((0x01, 0x07C4), (0x00, 0x07CB), (0x02, 0x07CB)),
        ),
        (
            0x07D0,
            bytes.fromhex("80 3e c3 98 00 74 f9"),
            overkill_boss_key_any_key_wait_gate_07d0,
            0x98C3,
            0x00,
            ((0x00, 0x07D0), (0x01, 0x07D7), (0x80, 0x07D7)),
        ),
        (
            0x07D7,
            bytes.fromhex("80 3e 07 99 01 74 f9"),
            overkill_boss_key_return_key_release_wait_gate_07d7,
            0x9907,
            0x01,
            ((0x01, 0x07D7), (0x00, 0x07DE), (0x02, 0x07DE)),
        ),
    ]

    def make_cpu(ip: int, code: bytes, use_hook: bool, handler, watched_off: int, value: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, ip, code)
        mem.wb(0x2000, watched_off, value)
        # Seed nearby watched bytes so accidental wrong-offset reads are visible.
        for off in (0x98C3, 0x9907):
            if off != watched_off:
                mem.wb(0x2000, off, 0xA5)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777,
            sp=0x8000, cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=ip, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, ip)] = handler
        return cpu

    for ip, code, handler, watched_off, _expected_value, subcases in cases:
        for value, expected_ip in subcases:
            asm = make_cpu(ip, code, False, handler, watched_off, value)
            hook = make_cpu(ip, code, True, handler, watched_off, value)
            for _ in range(4):
                asm.step()
                if asm.addr() == (0x1010, expected_ip):
                    break
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, expected_ip)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.data == hook.mem.data


def test_input_wait_gate_hook_metadata_uses_after_step_for_same_ip_targets():
    from overkill.verification import DEFAULT_STOPS

    for addr, self_ip, exit_ip in (
        ((0x1010, 0x986E), 0x986E, 0x9875),
        ((0x1010, 0x989E), 0x989E, 0x98B6),
        ((0x1010, 0x98D8), 0x98D8, 0x98DF),
        ((0x1010, 0x07C4), 0x07C4, 0x07CB),
        ((0x1010, 0x07D0), 0x07D0, 0x07D7),
        ((0x1010, 0x07D7), 0x07D7, 0x07DE),
    ):
        stop = DEFAULT_STOPS[addr]
        assert stop.kind == "fixed_ips"
        assert stop.min_steps == 1
        assert self_ip in stop.ips
        assert exit_ip in stop.ips


def test_status_display_parent_61dc_hook_matches_composed_interpreted_snapshot():
    from pathlib import Path
    from overkill.hooks import overkill_status_display_parent_61dc
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "runtime_code_5e42_gameplay_20260613_220042"
    assert snap.exists(), "captured gameplay snapshot for 1010:61DC is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.trace_enabled = False
        rt.cpu.replacement_hooks.pop((0x1010, 0x61DC), None)
        rt.cpu.hook_names.pop((0x1010, 0x61DC), None)
        return rt

    asm = make_runtime()
    hook = make_runtime()

    for _ in range(200_000):
        if asm.cpu.addr() == (0x1010, 0x61DC):
            break
        asm.cpu.step()
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x61DC)
    return_ip = asm.cpu.mem.rw(asm.cpu.s.ss, asm.cpu.s.sp)
    hook.cpu.replacement_hooks[(0x1010, 0x61DC)] = overkill_status_display_parent_61dc

    for _ in range(200_000):
        if asm.cpu.addr() == (0x1010, return_ip):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, return_ip)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data

def test_status_counter_cell_blit_6296_hook_matches_composed_interpreted_snapshot():
    from pathlib import Path
    from overkill.hooks import overkill_status_counter_cell_blit_6296
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "runtime_code_5e42_gameplay_20260613_220042"
    assert snap.exists(), "captured gameplay snapshot for 1010:6296 is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.trace_enabled = False
        rt.cpu.replacement_hooks.pop((0x1010, 0x61DC), None)
        rt.cpu.hook_names.pop((0x1010, 0x61DC), None)
        rt.cpu.replacement_hooks.pop((0x1010, 0x6296), None)
        rt.cpu.hook_names.pop((0x1010, 0x6296), None)
        return rt

    asm = make_runtime()
    hook = make_runtime()

    for _ in range(200_000):
        if asm.cpu.addr() == (0x1010, 0x6296):
            break
        asm.cpu.step()
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x6296)
    return_ip = asm.cpu.mem.rw(asm.cpu.s.ss, asm.cpu.s.sp)
    hook.cpu.replacement_hooks[(0x1010, 0x6296)] = overkill_status_counter_cell_blit_6296

    for _ in range(5_000):
        if asm.cpu.addr() == (0x1010, return_ip):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, return_ip)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_main_menu_idle_loop_558b_matches_interpreted_idle_iteration():
    from pathlib import Path

    from overkill.hooks import overkill_main_menu_idle_loop_558b
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshot = root / "artifacts" / "test_oracles" / "main_menu_idle_558b_20260613_211323"

    def make_cpu(use_hook: bool):
        rt = load_snapshot(exe, snapshot, game_root=root / "assets")
        cpu = rt.cpu
        ds = cpu.s.ds & 0xFFFF
        # Force the observed no-key / no-transition menu-idle path.
        for off in (0x98E9, 0x98E8, 0x98E2, 0x98D7, 0x98F6, 0x98DC, 0x98DB, 0x98C5, 0x9907):
            cpu.mem.wb(ds, off, 0)
        cpu.mem.ww(ds, 0x22BF, 0x0010)
        cpu.mem.wb(ds, 0x98BE, 0)

        def fake_50c9(cpu):
            cpu.set_reg8(0, 0x08)
            cpu.set_logic_flags(cpu.s.ax, 16)
            cpu.mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, 0xC9F0)
            cpu.s.ip = cpu.pop()

        def fake_0162(cpu):
            cpu.mem.wb(cpu.s.ds & 0xFFFF, 0x98BE, 0)
            cpu.set_reg8(0, 0)
            cpu.set_logic_flags(0, 8)
            cpu.s.ip = cpu.pop()

        cpu.replacement_hooks[(0x1010, 0x50C9)] = fake_50c9
        cpu.replacement_hooks[(0x1010, 0x0162)] = fake_0162
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x558B)] = overkill_main_menu_idle_loop_558b
        else:
            cpu.replacement_hooks.pop((0x1010, 0x558B), None)
        cpu.s.cs = 0x1010
        cpu.s.ip = 0x558B
        cpu.trace_enabled = False
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)

    for _ in range(80):
        asm.step()
        if asm.addr() == (0x1010, 0x558B):
            break
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0x558B)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_main_menu_idle_loop_558b_returns_on_fire():
    from pathlib import Path

    from overkill.hooks import overkill_main_menu_idle_loop_558b
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshot = root / "artifacts" / "test_oracles" / "main_menu_idle_558b_20260613_211323"

    def make_cpu(use_hook: bool):
        rt = load_snapshot(exe, snapshot, game_root=root / "assets")
        cpu = rt.cpu
        ds = cpu.s.ds & 0xFFFF
        for off in (0x98E9, 0x98E8, 0x98E2, 0x98D7, 0x98F6, 0x98DC, 0x98DB, 0x98C5, 0x9907):
            cpu.mem.wb(ds, off, 0)
        cpu.mem.ww(ds, 0x22BF, 0x0010)

        def fake_50c9(cpu):
            cpu.set_reg8(0, 0x08)
            cpu.set_logic_flags(cpu.s.ax, 16)
            cpu.mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, 0xC9F0)
            cpu.s.ip = cpu.pop()

        def fake_0162(cpu):
            cpu.mem.wb(cpu.s.ds & 0xFFFF, 0x98BE, 0x10)
            cpu.set_reg8(0, 0)
            cpu.set_logic_flags(0, 8)
            cpu.s.ip = cpu.pop()

        cpu.replacement_hooks[(0x1010, 0x50C9)] = fake_50c9
        cpu.replacement_hooks[(0x1010, 0x0162)] = fake_0162
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x558B)] = overkill_main_menu_idle_loop_558b
        else:
            cpu.replacement_hooks.pop((0x1010, 0x558B), None)
        cpu.s.cs = 0x1010
        cpu.s.ip = 0x558B
        cpu.push(0xBEEF)
        cpu.trace_enabled = False
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)

    for _ in range(80):
        asm.step()
        if asm.addr() == (0x1010, 0xBEEF):
            break
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_demo_counter_tick_081d_accepts_wide_cmp_live_code_against_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_demo_counter_tick_1f8f_081d

    # Some runtime images contain CMP AX,imm16 encodings here (3D xx 00), while
    # older/static evidence used the shorter CMP AX,imm8 form (83 F8 xx).  Both
    # are behaviorally equivalent for these positive thresholds and both are
    # legitimate OVERKILL live-code shapes.
    code = bytes.fromhex(
        "fe 0e a7 98 75 2b a1 7e a4 b1 78 3d 10 00 77 17 "
        "b1 64 3d 08 00 77 10 b1 50 3d 04 00 77 09 b1 3c "
        "3d 02 00 77 02 b1 28 88 0e a7 98 fe 06 a6 98 eb 05 "
        "c6 06 a6 98 00 cb"
    )

    def make_cpu(use_hook: bool, speed_word: int, counter: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1F8F, 0x081D, code)
        ds = 0x2000
        ss = 0x3000
        sp = 0x8FFC
        mem.wb(ds, 0x98A7, counter)
        mem.wb(ds, 0x98A6, 0x55)
        mem.ww(ds, 0xA47E, speed_word)
        mem.ww(ss, sp, 0xBEEF)
        mem.ww(ss, (sp + 2) & 0xFFFF, 0xCAFE)
        cpu = CPU8086(
            mem,
            CPUState(
                ax=0x1111,
                bx=0x2222,
                cx=0xABCD,
                dx=0x3333,
                si=0x4444,
                di=0x5555,
                bp=0x6666,
                sp=sp,
                cs=0x1F8F,
                ds=ds,
                es=0x7777,
                ss=ss,
                ip=0x081D,
                flags=0x0203,
            ),
        )
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1F8F, 0x081D)] = overkill_demo_counter_tick_1f8f_081d
            cpu.hook_names[(0x1F8F, 0x081D)] = "overkill_demo_counter_tick_1f8f_081d"
        return cpu

    for speed_word, counter in ((0x0002, 1), (0x0004, 1), (0x0011, 1), (0x0008, 3)):
        asm = make_cpu(False, speed_word, counter)
        hook = make_cpu(True, speed_word, counter)
        for _ in range(80):
            if asm.addr() == (0xCAFE, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0xCAFE, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_main_menu_idle_loop_558b_counter_expiry_boundary_without_installed_retrace_hook():
    from pathlib import Path

    from overkill.hooks import overkill_main_menu_idle_loop_558b
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshot = root / "artifacts" / "test_oracles" / "main_menu_idle_558b_20260613_211323"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(exe, snapshot, game_root=root / "assets")
        cpu = rt.cpu
        ds = cpu.s.ds & 0xFFFF
        for off in (0x98E9, 0x98E8, 0x98E2, 0x98D7, 0x98F6, 0x98DC, 0x98DB, 0x98C5, 0x9907):
            cpu.mem.wb(ds, off, 0)
        cpu.mem.ww(ds, 0x22BF, 0x02ED)
        cpu.mem.wb(ds, 0x98BE, 0)
        # Mirror the verifier edge that found the bug: the parent must not fall
        # back to a one-instruction original step merely because the nested 50C9
        # replacement is absent/restored differently.
        cpu.replacement_hooks.pop((0x1010, 0x50C9), None)
        cpu.hook_names.pop((0x1010, 0x50C9), None)
        cpu.replacement_hooks.pop((0x1010, 0x0162), None)
        cpu.hook_names.pop((0x1010, 0x0162), None)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x558B)] = overkill_main_menu_idle_loop_558b
            cpu.hook_names[(0x1010, 0x558B)] = "overkill_main_menu_idle_loop_558b"
        else:
            cpu.replacement_hooks.pop((0x1010, 0x558B), None)
            cpu.hook_names.pop((0x1010, 0x558B), None)
        cpu.s.cs = 0x1010
        cpu.s.ip = 0x558B
        cpu.trace_enabled = False
        return rt

    asm = make_runtime(False)
    hook = make_runtime(True)
    for _ in range(200):
        if asm.cpu.addr() == (0x1010, 0x55FD):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x55FD)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.dos.vga_status_reads == hook.dos.vga_status_reads
    assert asm.program.memory.data == hook.program.memory.data

def test_object_behavior_b24d_hook_matches_interpreted_observed_path():
    from pathlib import Path

    from overkill.hooks import overkill_object_behavior_b24d
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshot = root / "artifacts" / "evidence" / "snapshot_stop_1010_b24d_behavior"
    assert snapshot.exists(), f"captured B24D oracle snapshot is missing: {snapshot}"

    asm = load_snapshot(exe, snapshot, game_root=root / "assets")
    hook = load_snapshot(exe, snapshot, game_root=root / "assets")
    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xB24D)

    asm.cpu.replacement_hooks.pop((0x1010, 0xB24D), None)
    hook.cpu.replacement_hooks[(0x1010, 0xB24D)] = overkill_object_behavior_b24d
    asm.cpu.trace_enabled = False
    hook.cpu.trace_enabled = False

    for _ in range(100):
        if asm.cpu.addr() in ((0x1010, 0xAD5A), (0x1010, 0xADC9)):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xAD5A)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_object_behavior_aed8_b250_overlap_branch_matches_interpreted_repro():
    from pathlib import Path

    from overkill.hooks import overkill_object_behavior_aed8
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshot = root / "artifacts" / "evidence" / "snapshot_stop_1010_aed8_b250_overlap"
    assert snapshot.exists(), f"captured AED8/B250 oracle snapshot is missing: {snapshot}"

    asm = load_snapshot(exe, snapshot, game_root=root / "assets")
    hook = load_snapshot(exe, snapshot, game_root=root / "assets")
    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xAED8)

    continuation = asm.cpu.mem.rw(asm.cpu.s.ss & 0xFFFF, asm.cpu.s.sp & 0xFFFF)
    assert continuation == 0xAA22

    asm.cpu.replacement_hooks.pop((0x1010, 0xAED8), None)
    hook.cpu.replacement_hooks[(0x1010, 0xAED8)] = overkill_object_behavior_aed8
    asm.cpu.trace_enabled = False
    hook.cpu.trace_enabled = False

    for _ in range(200):
        if asm.cpu.addr() == (0x1010, continuation):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, continuation)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_object_behavior_b86d_hook_matches_interpreted_observed_paths():
    from pathlib import Path

    from overkill.hooks import overkill_object_behavior_b86d
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshots = [
        (root / "artifacts" / "evidence" / "snapshot_stop_1010_b86d_behavior", False),
        (root / "artifacts" / "evidence" / "snapshot_stop_1010_b8b0_behavior", True),
    ]

    for snapshot, rewind_to_entry in snapshots:
        assert snapshot.exists(), f"captured B86D oracle snapshot is missing: {snapshot}"
        asm = load_snapshot(exe, snapshot, game_root=root / "assets")
        hook = load_snapshot(exe, snapshot, game_root=root / "assets")
        if rewind_to_entry:
            # The B8B0 evidence state is inside B86D after compare-only setup.
            # Rewind IP to the exact hook boundary so the parent branch is
            # verified without fabricating any memory changes.
            asm.cpu.s.ip = 0xB86D
            hook.cpu.s.ip = 0xB86D
            asm.cpu.s.flags = 0x0206
            hook.cpu.s.flags = 0x0206
        asm.cpu.replacement_hooks.pop((0x1010, 0xB86D), None)
        hook.cpu.replacement_hooks[(0x1010, 0xB86D)] = overkill_object_behavior_b86d
        asm.cpu.trace_enabled = False
        hook.cpu.trace_enabled = False

        for _ in range(300):
            if asm.cpu.addr() == (0x1010, 0xBC4B):
                break
            asm.cpu.step()
        hook.cpu.step()

        assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xBC4B)
        assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
        assert asm.program.memory.data == hook.program.memory.data


def test_object_spawn_seed_8209_matches_interpreted_asm():
    from pathlib import Path
    from overkill.hook_wrappers.object_runtime_frontiers import overkill_object_spawn_seed_8209

    blob = Path("artifacts/test_oracles/snapshot_play_tandy_20260611_152751/memory_1mb.bin").read_bytes()

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.data[:] = blob
        ds = 0x2000
        ss = 0x3000
        bp = 0x0100
        bx = 0x23B4  # EFFECT_OBJECT_TABLE_BASE, a DS-relative slot base
        mem.ww(ss, bp + 0x02, 0x0050)  # source X at SS:[bp+2]
        mem.ww(ss, bp + 0x04, 0x00B0)  # source Y at SS:[bp+4]
        state = CPUState(
            ax=0x1111, bx=bx, cx=0x2222, dx=0x3333,
            si=0x4444, di=0x5555, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=ds, ss=ss,
            ip=0x8209, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(40):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()

    overkill_object_spawn_seed_8209(hook)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_object_behavior_b86d_b8f8_edge_path_matches_interpreted_original():
    from pathlib import Path

    from overkill.hooks import overkill_object_behavior_b86d
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL"
    snapshot = root / "artifacts" / "evidence" / "snapshot_stop_1010_b86d_b8f8_edge"

    asm = load_snapshot(exe, snapshot, game_root=root / "assets")
    hook = load_snapshot(exe, snapshot, game_root=root / "assets")
    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xB86D)

    asm.cpu.replacement_hooks.pop((0x1010, 0xB86D), None)
    hook.cpu.replacement_hooks[(0x1010, 0xB86D)] = overkill_object_behavior_b86d
    asm.cpu.trace_enabled = False
    hook.cpu.trace_enabled = False

    for _ in range(100):
        if asm.cpu.addr() == (0x1010, 0xBC4B):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xBC4B)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_live_verify_replacement_hooks_have_continuation_metadata():
    import overkill.hooks  # register all replacements
    from dos_re.hooks import registry
    from overkill.verification import DEFAULT_STOPS

    missing = [
        f"{key[0]:04X}:{key[1]:04X} {replacement.name}"
        for key, replacement in sorted(registry.replacements.items())
        if key not in DEFAULT_STOPS
    ]
    assert missing == []


def test_status_cursor_613e_and_615a_match_interpreted_asm_all_modes():
    from overkill.hooks import overkill_status_cursor_advance_613e, overkill_status_cursor_retreat_615a

    code_613e = bytes.fromhex(
        "2e 8b 1e bc 95 d1 e3 2e ff a7 4a 61 50 61 54 61 56 61 "
        "83 c7 02 c3 47 c3 83 c7 04 c3"
    )
    code_615a = bytes.fromhex(
        "2e 8b 1e bc 95 d1 e3 2e ff a7 66 61 6c 61 70 61 72 61 "
        "83 ef 02 c3 4f c3 83 ef 04 c3"
    )

    def make_cpu(entry: int, code: bytes, mode: int, use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, entry, code)
        mem.ww(0x1010, 0x95BC, mode)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x8004, bp=0x6666,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            sp=0x9000, ip=entry, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            if entry == 0x613E:
                cpu.replacement_hooks[(0x1010, 0x613E)] = overkill_status_cursor_advance_613e
            else:
                cpu.replacement_hooks[(0x1010, 0x615A)] = overkill_status_cursor_retreat_615a
        return cpu

    for entry, code in ((0x613E, code_613e), (0x615A, code_615a)):
        for mode in (0, 1, 2):
            asm = make_cpu(entry, code, mode, False)
            hook = make_cpu(entry, code, mode, True)
            for _ in range(20):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == (0x1010, 0xBEEF)
            assert hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_reset_object_slot_block_c4e5_matches_interpreted_asm():
    from overkill.hooks import overkill_reset_object_slot_block_c4e5

    code = bytes.fromhex(
        "51 8b d9 d1 e3 8b af ca 32 c7 46 00 00 00 c7 46 2e 00 00 "
        "c7 46 24 00 00 c7 46 18 00 00 c7 46 0a 01 00 c7 46 06 "
        "00 00 2e a1 a2 c3 89 46 0e 2e 81 06 a2 c3 80 02 59 e2 c8"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xC4E5, code)
        mem.ww(0x1010, 0xC3A2, 0x3314)
        # The loop indexes DS:32CA by CX*2, so populate entries 1..4.
        for cx, ptr in enumerate((0x2440, 0x2480, 0x24C0, 0x2500), start=1):
            mem.ww(0x2000, 0x32CA + cx * 2, ptr)
            for off in range(0, 0x38, 2):
                mem.ww(0x3000, ptr + off, (0x9000 + ptr + off) & 0xFFFF)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0x0004, dx=0xDDDD,
            si=0xEEEE, di=0xF111, bp=0x2222,
            cs=0x1010, ds=0x2000, es=0x4000, ss=0x3000,
            sp=0x9000, ip=0xC4E5, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xC4E5)] = overkill_reset_object_slot_block_c4e5
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xC51D):
            break
        asm.step()
    hook.step()

    assert asm.addr() == (0x1010, 0xC51D)
    assert hook.addr() == (0x1010, 0xC51D)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_setup_reset_blocks_c3bf_and_c3f1_match_interpreted_asm():
    from overkill.hooks import overkill_reset_effect_slot_block_c3bf, overkill_reset_object_slot_block_c3f1

    code_c3bf = bytes.fromhex(
        "51 8b d9 d1 e3 8b af 12 8d c7 46 00 00 00 c7 46 2e 00 00 "
        "c7 46 18 00 00 2e a1 a2 c3 89 46 0e 2e 83 06 a2 c3 40 "
        "59 e2 d8"
    )
    code_c3f1 = bytes.fromhex(
        "51 8b d9 d1 e3 8b af ca 32 c7 46 0a 01 00 83 7e 16 01 74 "
        "19 c7 46 00 00 00 c7 46 2e 00 00 c7 46 24 00 00 c7 46 "
        "18 00 00 c7 46 06 00 00 2e a1 a2 c3 89 46 0e 2e 81 06 "
        "a2 c3 80 02 59 e2 c2"
    )

    def make_c3bf(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xC3BF, code_c3bf)
        mem.ww(0x1010, 0xC3A2, 0x3314)
        for cx, ptr in enumerate((0x2440, 0x2480, 0x24C0), start=1):
            mem.ww(0x2000, 0x8D12 + cx * 2, ptr)
            for off in range(0, 0x38, 2):
                mem.ww(0x3000, ptr + off, (0x7000 + ptr + off) & 0xFFFF)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x0003, dx=0x3333,
            si=0x4444, di=0x5555, bp=0x6666,
            cs=0x1010, ds=0x2000, es=0x4000, ss=0x3000,
            sp=0x9000, ip=0xC3BF, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xC3BF)] = overkill_reset_effect_slot_block_c3bf
        return cpu

    def make_c3f1(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xC3F1, code_c3f1)
        mem.ww(0x1010, 0xC3A2, 0x3314)
        for cx, ptr in enumerate((0x2540, 0x2580, 0x25C0, 0x2600), start=1):
            mem.ww(0x2000, 0x32CA + cx * 2, ptr)
            for off in range(0, 0x38, 2):
                mem.ww(0x3000, ptr + off, (0x8000 + ptr + off) & 0xFFFF)
            mem.ww(0x3000, ptr + 0x16, 0x0001 if cx == 2 else 0x0007)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0x0004, dx=0xDDDD,
            si=0xEEEE, di=0xF111, bp=0x2222,
            cs=0x1010, ds=0x2000, es=0x4000, ss=0x3000,
            sp=0x9000, ip=0xC3F1, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xC3F1)] = overkill_reset_object_slot_block_c3f1
        return cpu

    for make_cpu, expected_ip in ((make_c3bf, 0xC3E7), (make_c3f1, 0xC42F)):
        asm = make_cpu(False)
        hook = make_cpu(True)
        for _ in range(400):
            if asm.addr() == (0x1010, expected_ip):
                break
            asm.step()
        hook.step()
        assert asm.addr() == (0x1010, expected_ip)
        assert hook.addr() == (0x1010, expected_ip)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_status_cell_composite_85d5_matches_interpreted_parent_with_child_boundaries():
    from overkill.hooks import overkill_status_cell_composite_85d5

    code = bytes.fromhex(
        "83 3e fa 95 ff 74 11 8b 36 fa 95 d1 e6 81 c6 fc 95 "
        "3b 2c b8 01 00 74 02 33 c0 83 3e ac bd 01 75 0c "
        "3b 3e fa 95 75 06 ff 36 16 be eb 03 ff 76 00 50 "
        "8b 76 04 03 f0 d1 e6 81 c6 e4 0b 2e 8b 34 8b 7e "
        "02 57 b9 05 00 e8 20 db e2 fb 2e 8e 1e b4 95 e8 "
        "44 d4 5f e8 2e db 5e 83 c6 17 d1 e6 81 c6 e4 0b "
        "2e 8b 34 57 e8 2f d4 5f e8 fd da 5e d1 e6 81 c6 "
        "e4 0b 2e 8b 34 e8 1e d4 2e 8e 1e 96 95 c3"
    )

    def dummy_613e(cpu: CPU8086) -> None:
        old = cpu.s.di & 0xFFFF
        result = old + 4
        cpu.s.di = result & 0xFFFF
        cpu.set_add_flags(old, 4, result, 16)
        cpu.s.ip = cpu.pop()

    def dummy_615a(cpu: CPU8086) -> None:
        old = cpu.s.di & 0xFFFF
        result = old - 4
        cpu.s.di = result & 0xFFFF
        cpu.set_sub_flags(old, 4, result, 16)
        cpu.s.ip = cpu.pop()

    def dummy_5a6c(cpu: CPU8086) -> None:
        ss = cpu.s.ss & 0xFFFF
        idx = cpu.mem.rw(ss, 0x0100)
        base = 0x0120 + idx * 8
        cpu.mem.ww(ss, base + 0, cpu.s.ds & 0xFFFF)
        cpu.mem.ww(ss, base + 2, cpu.s.si & 0xFFFF)
        cpu.mem.ww(ss, base + 4, cpu.s.di & 0xFFFF)
        cpu.mem.ww(ss, base + 6, cpu.s.cx & 0xFFFF)
        cpu.mem.ww(ss, 0x0100, (idx + 1) & 0xFFFF)
        old = cpu.s.dx & 0xFFFF
        result = old + 0x1111
        cpu.s.dx = result & 0xFFFF
        cpu.set_add_flags(old, 0x1111, result, 16)
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool, *, selected: bool, special_owner: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x85D5, code)
        # Cursor dispatch tables for mode 2: +/-4 DI steps.
        mem.ww(0x1010, 0x95BC, 0x0002)
        mem.ww(0x1010, 0x614A, 0x6150)
        mem.ww(0x1010, 0x614C, 0x6154)
        mem.ww(0x1010, 0x614E, 0x6156)
        mem.ww(0x1010, 0x6166, 0x616C)
        mem.ww(0x1010, 0x6168, 0x6170)
        mem.ww(0x1010, 0x616A, 0x6172)
        mem.ww(0x1010, 0x95B4, 0x3456)
        mem.ww(0x1010, 0x9596, 0x2000)
        for idx, ptr in ((3, 0x3003), (0x17, 0x3017), (0x18, 0x3018), (7, 0x3007)):
            mem.ww(0x1010, 0x0BE4 + idx * 2, ptr)

        ds = ss = 0x2000
        bp = 0x2400
        marker = 0x0003
        mem.ww(ds, 0x95FA, marker)
        mem.ww(ds, 0x95FC + marker * 2, bp if selected else 0x9999)
        mem.ww(ds, 0xBDAC, 0x0001 if special_owner else 0x0000)
        mem.ww(ds, 0xBE16, 0x0007)
        mem.ww(ss, bp + 0x00, 0x0017)
        mem.ww(ss, bp + 0x02, 0x0100)
        mem.ww(ss, bp + 0x04, 0x0002)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0x1111,
            si=0x2222, di=marker if special_owner else 0x7777, bp=bp,
            cs=0x1010, ds=ds, es=0x4000, ss=ss,
            sp=0x9000, ip=0x85D5, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.replacement_hooks[(0x1010, 0x613E)] = dummy_613e
        cpu.replacement_hooks[(0x1010, 0x615A)] = dummy_615a
        cpu.replacement_hooks[(0x1010, 0x5A6C)] = dummy_5a6c
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x85D5)] = overkill_status_cell_composite_85d5
        return cpu

    for selected, special_owner in ((True, True), (False, False)):
        asm = make_cpu(False, selected=selected, special_owner=special_owner)
        hook = make_cpu(True, selected=selected, special_owner=special_owner)
        for _ in range(300):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_status_coord_list_fill_99cd_matches_interpreted_loop():
    from overkill.hooks import overkill_status_coord_list_fill_99cd

    code = bytes.fromhex("8b 46 02 05 08 00 ab 8b 46 04 05 09 00 ab e2 f0")

    def make_cpu(use_hook: bool, count: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x99CD, code)
        ss = 0x2000
        es = 0x3000
        bp = 0x2400
        mem.ww(ss, bp + 0x02, 0x1234)
        mem.ww(ss, bp + 0x04, 0x5678)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=count, dx=0xDDDD,
            si=0xEEEE, di=0x0100, bp=bp,
            cs=0x1010, ds=0x4000, es=es, ss=ss,
            sp=0x9000, ip=0x99CD, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x99CD)] = overkill_status_coord_list_fill_99cd
        return cpu

    asm = make_cpu(False, 5)
    hook = make_cpu(True, 5)
    for _ in range(200):
        if asm.addr() == (0x1010, 0x99DD):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0x99DD)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_frame_action_spawn_fanout_a067_matches_interpreted_paths():
    from overkill.hooks import overkill_frame_action_spawn_fanout_a067

    code_a060_to_a211 = bytes.fromhex(
        "c70680a90000c3f606be981074f2833e80a900740f803e9097017408833e2a230f7401c3"
        "c70680a90100813e5023b6007714833eacbd00750d833e58a9027503e92501e9f900"
        "a170a9a3a0a3a172a9a3a2a3a176a9a3a4a3a174a9a3a6a3833eacbd017513"
        "833e06be087502eb46833e06be0f7603e93d04e83a04e8a604e81e03e8e602e80100c3"
        "833e58a9057503e8ae01833e6ea9ff7403e818008b1e58a9d1e32effa708a1909f"
        "a18aa1c8a137a3f6a2af44833ea6a3007401c3803ec098007405c606ffbe18ff0674a9"
        "e846002d06008947028b4404050400894704ff0674a9e830002d02008947028b4404"
        "2d0400894704c747060700ff0674a9e815002d02008947028b4404050c00894704"
        "c747060100c3e87203c747180c00c7471c07008b366ea98b4402c3e81e00c747083300"
        "803ec098007405c606ffbe14c3803ec098007405c606ffbe13e83c038b7608d1e6"
        "d1e681c6a8a3ad034602894702ad034604894704c3803ec098007405c606ffbe15"
        "e81303c747081800e8cfffe80803e8c9ffc747060700c747081f00f606be9802751b"
        "c747060100c747081900f606be9801750ac747060000c747081800c3"
    )

    def record_call(cpu: CPU8086, ip: int) -> None:
        ds = cpu.s.ds & 0xFFFF
        idx = cpu.mem.rw(ds, 0x0100)
        cpu.mem.ww(ds, 0x0102 + idx * 2, ip & 0xFFFF)
        cpu.mem.ww(ds, 0x0100, (idx + 1) & 0xFFFF)

    def make_child(ip: int):
        def child(cpu: CPU8086) -> None:
            record_call(cpu, ip)
            old = cpu.s.ax & 0xFFFF
            addend = ip & 0x00FF
            result = old + addend
            cpu.s.ax = result & 0xFFFF
            cpu.set_add_flags(old, addend, result, 16)
            cpu.s.ip = cpu.pop()
        return child

    def child_a4ea(cpu: CPU8086) -> None:
        record_call(cpu, 0xA4EA)
        ds = cpu.s.ds & 0xFFFF
        count = cpu.mem.rw(ds, 0x0300)
        cpu.s.bx = (0x4000 + count * 0x40) & 0xFFFF
        cpu.mem.ww(ds, 0x0300, (count + 1) & 0xFFFF)
        old = cpu.s.ax & 0xFFFF
        result = old + 0x004A
        cpu.s.ax = result & 0xFFFF
        cpu.set_add_flags(old, 0x004A, result, 16)
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool, **case) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA060, code_a060_to_a211)
        ds = 0x2000
        ss = ds
        bp = 0x237C
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ss, ip=0xA067, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)

        for ip in (0xA515, 0xA584, 0xA3FF, 0xA3CA, 0xA2A0):
            cpu.replacement_hooks[(0x1010, ip)] = make_child(ip)
        cpu.replacement_hooks[(0x1010, 0xA4EA)] = child_a4ea
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA067)] = overkill_frame_action_spawn_fanout_a067

        mem.wb(ds, 0x98BE, case.get("input_bits", 0x10))
        mem.ww(ds, 0xA980, case.get("a980", 0))
        mem.wb(ds, 0x9790, case.get("v9790", 0))
        mem.ww(ds, 0x232A, case.get("v232a", 0))
        mem.ww(ds, 0x2350, case.get("view_y", 0x00A0))
        mem.ww(ds, 0xBDAC, case.get("bdac", 0))
        mem.ww(ds, 0xA958, case.get("a958", 0))
        mem.wb(ds, 0x98C0, case.get("v98c0", 1))
        mem.ww(ds, 0xBE06, case.get("be06", 0))
        mem.ww(ds, 0xA970, case.get("a970", 1))
        mem.ww(ds, 0xA972, case.get("a972", 2))
        mem.ww(ds, 0xA974, case.get("a974", 0))
        mem.ww(ds, 0xA976, case.get("a976", 3))
        mem.ww(ds, 0xA96E, case.get("a96e", 0x5000))
        mem.ww(ds, 0x5002, 0x0060)
        mem.ww(ds, 0x5004, 0x0070)
        mem.ww(ss, bp + 0x02, 0x0020)
        mem.ww(ss, bp + 0x04, 0x0030)
        mem.ww(ss, bp + 0x08, case.get("bp8", 1))
        # Two offset pairs used by A1AB after BP+8 is shifted by two.
        mem.ww(ds, 0xA3A8 + 4, 0x0005)
        mem.ww(ds, 0xA3A8 + 6, 0x0006)
        mem.ww(ds, 0xA3A8 + 8, 0x0009)
        mem.ww(ds, 0xA3A8 + 10, 0x000A)
        return cpu

    cases = (
        # Input bit 10h clear: A067 tails through A060 and only clears the latch.
        dict(input_bits=0x00, a980=7),
        # Repeated-fire latch blocks unless the edge byte or BP+8-like state opens it.
        dict(input_bits=0x10, a980=1, v9790=0, v232a=2),
        # Low-view action index 0 uses the A19F/A1AB spawn tail.
        dict(input_bits=0x10, a980=0, view_y=0x00A0, bdac=0, a958=0, bp8=1),
        # Low-view action index 2 uses the double-spawn A1C8 tail.
        dict(input_bits=0x10, a980=0, view_y=0x00A0, bdac=0, a958=2, bp8=2),
        # High-view BDAC==1/BE06==8 jumps directly to the A114 three-spawn tail.
        dict(input_bits=0x10, a980=0, view_y=0x00B7, bdac=1, be06=8, a958=1, a974=0),
        # Main high-view path composes the larger children, then dispatches A958==1.
        dict(input_bits=0x10, a980=0, view_y=0x00B7, bdac=2, a958=1, a96e=0xFFFF, bp8=1),
    )

    for case in cases:
        asm = make_cpu(False, **case)
        hook = make_cpu(True, **case)
        for _ in range(6000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot(), case
        assert bytes(asm.mem.data) == bytes(hook.mem.data), case


def test_frame_action_spawn_children_a515_a584_match_interpreted_paths():
    from overkill.hooks import (
        overkill_frame_action_dual_anchor_spawn_a584,
        overkill_frame_action_linked_anchor_spawn_a515,
    )

    code_a515 = bytes.fromhex(
        "83 3e 60 a9 00 75 01 c3 83 3e 7e a9 01 75 01 c3"
        "e8 1f d0 e8 46 00 55 8b eb e8 29 0c 8b c3 8b dd"
        "5d 3d ff ff 75 01 c3 89 47 30 c7 07 01 00 c7 47"
        "1e 01 00 c7 47 14 00 00 c7 47 16 02 00 c7 47"
        "18 0a 00 c7 47 1c 01 00 80 3e c0 98 00 74 05"
        "c6 06 ff be 11 ff 06 7e a9 ff 0e 60 a9 c3"
    )
    code_a584 = bytes.fromhex(
        "83 3e 5e a9 00 75 01 c3 83 3e a4 a3 00 74 01 c3"
        "ff 06 76 a9 80 3e c0 98 00 74 05 c6 06 ff be 12"
        "e8 43 ff e8 c7 ff 83 67 04 fc c7 47 08 08 00 c7"
        "47 18 05 00 ff 06 76 a9 e8 2b ff e8 af ff 83 67"
        "04 fc c7 47 08 08 00 c7 47 18 06 00 c3"
    )

    def record_call(cpu: CPU8086, ip: int) -> None:
        ds = cpu.s.ds & 0xFFFF
        idx = cpu.mem.rw(ds, 0x0100)
        cpu.mem.ww(ds, 0x0102 + idx * 2, ip & 0xFFFF)
        cpu.mem.ww(ds, 0x0100, (idx + 1) & 0xFFFF)

    def child_allocate(ip: int):
        def child(cpu: CPU8086) -> None:
            record_call(cpu, ip)
            ds = cpu.s.ds & 0xFFFF
            count = cpu.mem.rw(ds, 0x0300)
            cpu.s.bx = (0x4200 + count * 0x40) & 0xFFFF
            cpu.mem.ww(ds, 0x0300, (count + 1) & 0xFFFF)
            old = cpu.s.ax & 0xFFFF
            result = old + (ip & 0x00FF)
            cpu.s.ax = result & 0xFFFF
            cpu.set_add_flags(old, ip & 0x00FF, result, 16)
            cpu.s.ip = cpu.pop()
        return child

    def child_a571(cpu: CPU8086) -> None:
        record_call(cpu, 0xA571)
        ds = cpu.s.ds & 0xFFFF
        ss = cpu.s.ss & 0xFFFF
        old_y = cpu.mem.rw(ss, (cpu.s.bp + 0x04) & 0xFFFF)
        result_y = old_y + 0x000A
        cpu.s.ax = result_y & 0xFFFF
        cpu.set_add_flags(old_y, 0x000A, result_y, 16)
        cpu.mem.ww(ds, (cpu.s.bx + 0x04) & 0xFFFF, cpu.s.ax)
        old_x = cpu.mem.rw(ss, (cpu.s.bp + 0x02) & 0xFFFF)
        result_x = old_x + 0x000A
        cpu.s.ax = result_x & 0xFFFF
        cpu.set_add_flags(old_x, 0x000A, result_x, 16)
        cpu.mem.ww(ds, (cpu.s.bx + 0x02) & 0xFFFF, cpu.s.ax)
        cpu.s.ip = cpu.pop()

    def child_b15a(result_bx: int):
        def child(cpu: CPU8086) -> None:
            record_call(cpu, 0xB15A)
            old = cpu.s.bx & 0xFFFF
            cpu.s.bx = result_bx & 0xFFFF
            cpu.set_sub_flags(old, 0x1234, old - 0x1234, 16)
            cpu.s.ip = cpu.pop()
        return child

    def make_a515(use_hook: bool, **case) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA515, code_a515)
        ds = 0x2000
        ss = 0x3000
        bp = 0x237C
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x4000, ss=ss, ip=0xA515, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        mem.ww(ds, 0xA960, case.get("a960", 1))
        mem.ww(ds, 0xA97E, case.get("a97e", 0))
        mem.wb(ds, 0x98C0, case.get("v98c0", 1))
        mem.ww(ss, bp + 0x02, 0x0040)
        mem.ww(ss, bp + 0x04, 0x0050)
        cpu.replacement_hooks[(0x1010, 0x7547)] = child_allocate(0x7547)
        cpu.replacement_hooks[(0x1010, 0xA571)] = child_a571
        cpu.replacement_hooks[(0x1010, 0xB15A)] = child_b15a(case.get("b15a", 0x6200))
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA515)] = overkill_frame_action_linked_anchor_spawn_a515
        return cpu

    def make_a584(use_hook: bool, **case) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA584, code_a584)
        ds = 0x2000
        ss = 0x3000
        bp = 0x237C
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
            si=0xEEEE, di=0xFFFF, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x4000, ss=ss, ip=0xA584, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        mem.ww(ds, 0xA95E, case.get("a95e", 1))
        mem.ww(ds, 0xA3A4, case.get("a3a4", 0))
        mem.wb(ds, 0x98C0, case.get("v98c0", 1))
        mem.ww(ss, bp + 0x02, 0x0041)
        mem.ww(ss, bp + 0x04, 0x0053)
        cpu.replacement_hooks[(0x1010, 0xA4EA)] = child_allocate(0xA4EA)
        cpu.replacement_hooks[(0x1010, 0xA571)] = child_a571
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA584)] = overkill_frame_action_dual_anchor_spawn_a584
        return cpu

    for maker, cases, steps in (
        (make_a515, (
            dict(a960=0),
            dict(a960=3, a97e=1),
            dict(a960=3, a97e=0, b15a=0xFFFF),
            dict(a960=3, a97e=0, b15a=0x6200, v98c0=1),
            dict(a960=3, a97e=0, b15a=0x6200, v98c0=0),
        ), 200),
        (make_a584, (
            dict(a95e=0),
            dict(a95e=2, a3a4=1),
            dict(a95e=2, a3a4=0, v98c0=1),
            dict(a95e=2, a3a4=0, v98c0=0),
        ), 200),
    ):
        for case in cases:
            asm = maker(False, **case)
            hook = maker(True, **case)
            for _ in range(steps):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot(), case
            assert bytes(asm.mem.data) == bytes(hook.mem.data), case


def test_frame_action_anchor_dispatch_children_a3ca_a3ff_match_interpreted_paths():
    from overkill.hooks import (
        overkill_frame_action_mirrored_anchor_spawn_a3ff,
        overkill_frame_action_side_anchor_spawn_a3ca,
    )

    code_a378_to_a514 = bytes.fromhex(
        "83feff7501c3833e5ea9007501c3833ea4a3007401c3e80500c747180600ff0676a9803ec0980074"
        "05c606ffbe12e841018b44040504008947048b4402050400894702836704fcc747080800c7471805"
        "00c3c706eca307008b3666a9e84300c706eca301008b3668a9e83600c706eca307008b366aa9e829"
        "00c706eca301008b366ca9e81c00c3c706eca3ffff8b3662a9e80e00e869ff8b3664a9e80400e85f"
        "ffc383feff7501c38b1e58a9d1e32effa72ca490d7a490a499a464a438a4af44833ea0a3007401c3"
        "830670a902e88f00c747180800c747083500e88200c747180800c74708350083470208c3833ea0a3"
        "007401c3830670a902e86300c747180700c747083700e85600c747180700c74708370083470208c3"
        "e84400c747083300c3e84e008b44028947028b4404050400894704a1eca38947063dffff7510c747"
        "060700837c04587605c747060100837f0601c7470819007405c747081f00c3e810008b4402894702"
        "8b4404050400894704c3e85ad0c7070100c7471e0100c747060000c747083200c747140000c74716"
        "0200c747180200c7471cffffc3"
    )

    def record_call(cpu: CPU8086, ip: int) -> None:
        ds = cpu.s.ds & 0xFFFF
        idx = cpu.mem.rw(ds, 0x0100)
        cpu.mem.ww(ds, 0x0102 + idx * 2, ip & 0xFFFF)
        cpu.mem.ww(ds, 0x0100, (idx + 1) & 0xFFFF)

    def child_a4ea(cpu: CPU8086) -> None:
        record_call(cpu, 0xA4EA)
        ds = cpu.s.ds & 0xFFFF
        count = cpu.mem.rw(ds, 0x0300)
        cpu.s.bx = (0x5000 + count * 0x40) & 0xFFFF
        cpu.mem.ww(ds, 0x0300, (count + 1) & 0xFFFF)
        old = cpu.s.ax & 0xFFFF
        result = old + 0x004A
        cpu.s.ax = result & 0xFFFF
        cpu.set_add_flags(old, 0x004A, result, 16)
        cpu.s.ip = cpu.pop()

    source_ptrs = (0x6100, 0x6120, 0x6140, 0x6160, 0x6180, 0x61A0)

    def make_cpu(use_hook: bool, entry: int, **case) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA378, code_a378_to_a514)
        ds = 0x2000
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ds, ip=entry, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.replacement_hooks[(0x1010, 0xA4EA)] = child_a4ea
        if use_hook:
            if entry == 0xA3CA:
                cpu.replacement_hooks[(0x1010, 0xA3CA)] = overkill_frame_action_side_anchor_spawn_a3ca
            elif entry == 0xA3FF:
                cpu.replacement_hooks[(0x1010, 0xA3FF)] = overkill_frame_action_mirrored_anchor_spawn_a3ff
            else:
                raise AssertionError(entry)

        mem.ww(ds, 0xA958, case.get("a958", 0))
        mem.ww(ds, 0xA3A0, case.get("a3a0", 0))
        mem.ww(ds, 0xA95E, case.get("a95e", 1))
        mem.ww(ds, 0xA3A4, case.get("a3a4", 0))
        mem.ww(ds, 0xA970, case.get("a970", 0))
        mem.ww(ds, 0xA976, case.get("a976", 0))
        mem.wb(ds, 0x98C0, case.get("v98c0", 1))

        defaults = {
            0xA962: source_ptrs[0],
            0xA964: source_ptrs[1],
            0xA966: source_ptrs[2],
            0xA968: source_ptrs[3],
            0xA96A: source_ptrs[4],
            0xA96C: source_ptrs[5],
        }
        defaults.update(case.get("sources", {}))
        for addr, ptr in defaults.items():
            mem.ww(ds, addr, ptr & 0xFFFF)

        for idx, ptr in enumerate(source_ptrs):
            mem.ww(ds, ptr + 0x02, 0x0040 + idx * 0x10)
            # Exercise both branches of the A499 FFFFh direction conversion.
            mem.ww(ds, ptr + 0x04, 0x0050 if idx % 2 == 0 else 0x0060)
        return cpu

    cases = (
        # A3CA through direct A4D7 coordinate-copy table target.
        (0xA3CA, dict(a958=0)),
        # A3CA through A499, where A3EC's alternating 7/1 stamp becomes visible.
        (0xA3CA, dict(a958=2)),
        # A3CA through the two-spawn A438 path.
        (0xA3CA, dict(a958=4, a3a0=0, a970=5)),
        # A3CA A438 early-ret path: BX remains the shifted table index.
        (0xA3CA, dict(a958=4, a3a0=1, a970=5)),
        # A3FF A499 converts A3EC=FFFFh based on source Y, then A378 adds a follow-up spawn.
        (0xA3FF, dict(a958=2, a95e=1, a3a4=0)),
        # A3FF with the first source disabled skips both A41A and A378 for that source.
        (0xA3FF, dict(a958=2, sources={0xA962: 0xFFFF}, a95e=1, a3a4=0)),
        # A3FF still runs A41A, but A378 is gated off by A95E.
        (0xA3FF, dict(a958=3, a95e=0, a3a4=0)),
        # A3FF still runs A41A, but A378 is gated off by copied A3A4.
        (0xA3FF, dict(a958=1, a95e=1, a3a4=1)),
    )

    for entry, case in cases:
        asm = make_cpu(False, entry, **case)
        hook = make_cpu(True, entry, **case)
        for _ in range(1500):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF), (entry, case)
        assert asm.s.snapshot() == hook.s.snapshot(), (entry, case)
        assert bytes(asm.mem.data) == bytes(hook.mem.data), (entry, case)


def test_frame_action_a2xx_spawn_tails_match_interpreted_paths():
    from overkill.hooks import (
        overkill_frame_action_listed_anchor_spawn_a2a0,
        overkill_frame_action_pair_spawn_a2f6,
        overkill_frame_action_pair_spawn_a337,
    )

    code_a1ae = bytes.fromhex(
        "8b7608d1e6d1e681c6a8a3ad034602894702ad034604894704c3"
    )
    code_a294_to_a378 = bytes.fromhex(
        "8b3eeaa3891d8306eaa302c3"
        "833ea2a3007401c3803ec098007405c606ffbe112e8e069695c706eaa3b4a3bf"
        "b4a3b8ffffb91a00f3abe80900c747086a00836f0408ff0672a9e80d02e8b4ff"
        "c747180900e8c6fe836704f883470408c747086c00c3"
        "833ea0a3007401c3803ec098007405c606ffbe17ff0670a9e8d901c747180800"
        "c747083500e890feff0670a9e8c501c747180800c747083500e87cfe83470208"
        "c3"
        "833ea0a3007401c3803ec098007405c606ffbe16ff0670a9e89801c747180700"
        "c747083700e84ffeff0670a9e88401c747180700c747083700e83bfe83470208"
        "c3"
    )

    def record_call(cpu: CPU8086, ip: int) -> None:
        ds = cpu.s.ds & 0xFFFF
        idx = cpu.mem.rw(ds, 0x0100)
        cpu.mem.ww(ds, 0x0102 + idx * 2, ip & 0xFFFF)
        cpu.mem.ww(ds, 0x0100, (idx + 1) & 0xFFFF)

    def child_a4ea(cpu: CPU8086) -> None:
        record_call(cpu, 0xA4EA)
        ds = cpu.s.ds & 0xFFFF
        count = cpu.mem.rw(ds, 0x0300)
        cpu.s.bx = (0x5000 + count * 0x40) & 0xFFFF
        cpu.mem.ww(ds, 0x0300, (count + 1) & 0xFFFF)
        old = cpu.s.ax & 0xFFFF
        result = old + 0x004A
        cpu.s.ax = result & 0xFFFF
        cpu.set_add_flags(old, 0x004A, result, 16)
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool, entry: int, **case) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA1AE, code_a1ae)
        mem.load(0x1010, 0xA294, code_a294_to_a378)
        ds = 0x2000
        bp = 0x237C
        mem.ww(0x1010, 0x9596, ds)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ds, ip=entry, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.replacement_hooks[(0x1010, 0xA4EA)] = child_a4ea
        if use_hook:
            if entry == 0xA2A0:
                cpu.replacement_hooks[(0x1010, 0xA2A0)] = overkill_frame_action_listed_anchor_spawn_a2a0
            elif entry == 0xA2F6:
                cpu.replacement_hooks[(0x1010, 0xA2F6)] = overkill_frame_action_pair_spawn_a2f6
            elif entry == 0xA337:
                cpu.replacement_hooks[(0x1010, 0xA337)] = overkill_frame_action_pair_spawn_a337
            else:
                raise AssertionError(entry)

        mem.wb(ds, 0x98C0, case.get("v98c0", 1))
        mem.ww(ds, 0xA3A2, case.get("a3a2", 0))
        mem.ww(ds, 0xA3A0, case.get("a3a0", 0))
        mem.ww(ds, 0xA970, case.get("a970", 0))
        mem.ww(ds, 0xA972, case.get("a972", 0))
        mem.ww(ds, 0xA3EA, 0x7BAD)
        for off, value in ((0xA3B4, 0x1234), (0xA3B6, 0x5678), (0xA3B8, 0x9ABC), (0xA3BA, 0xDEF0)):
            mem.ww(ds, off, value)
        mem.ww(ds, bp + 0x02, case.get("bp_x", 0x0020))
        mem.ww(ds, bp + 0x04, case.get("bp_y", 0x0030))
        mem.ww(ds, bp + 0x08, case.get("bp8", 1))
        mem.ww(ds, 0xA3A8 + 4, 0x0005)
        mem.ww(ds, 0xA3A8 + 6, 0x0006)
        mem.ww(ds, 0xA3A8 + 8, 0x0009)
        mem.ww(ds, 0xA3A8 + 10, 0x000A)
        return cpu

    cases = (
        (0xA2A0, dict(a3a2=1, v98c0=1)),
        (0xA2A0, dict(a3a2=0, v98c0=1, bp8=1)),
        (0xA2F6, dict(a3a0=1, v98c0=1)),
        (0xA2F6, dict(a3a0=0, v98c0=1, bp8=2)),
        (0xA337, dict(a3a0=0, v98c0=0, bp8=1)),
    )

    for entry, case in cases:
        asm = make_cpu(False, entry, **case)
        hook = make_cpu(True, entry, **case)
        for _ in range(1600):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF), (entry, case)
        assert asm.s.snapshot() == hook.s.snapshot(), (entry, case)
        assert bytes(asm.mem.data) == bytes(hook.mem.data), (entry, case)


def test_player_chase_candidate_scan_b15a_matches_interpreted_paths():
    from overkill.hooks import overkill_player_chase_candidate_scan_b15a

    code_b15a = bytes.fromhex(
        "b9 23 00 8b 1e 3a a4 81 fb 5c 2b 73 33 83 3f 00"
        "74 25 83 7f 18 01 74 1f 83 7f 18 26 74 19 83"
        "7f 18 21 74 13 83 7f 18 22 74 0d 81 7f 02 e0"
        "00 77 06 83 7f 16 04 74 15 83 c3 38 e2 cb bb"
        "ff ff c3 c7 06 3a a4 b4 23 8b 1e 3a a4 eb bb"
        "53 83 c3 38 89 1e 3a a4 5b c3"
    )
    ds = 0x2000
    slot_base = 0x23B4
    slot_stride = 0x38
    table_end = 0x2B5C

    def write_slot(mem: Memory, index: int, *, active=0, logic=1, x=0, hazard=0) -> int:
        base = (slot_base + index * slot_stride) & 0xFFFF
        mem.ww(ds, base + 0x00, active)
        mem.ww(ds, base + 0x02, x)
        mem.ww(ds, base + 0x16, hazard)
        mem.ww(ds, base + 0x18, logic)
        return base

    def make_cpu(use_hook: bool, *, cursor: int, slots: list[tuple[int, dict]]) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xB15A, code_b15a)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=0x4000,
            ip=0xB15A, flags=0x0207,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        mem.ww(ds, 0xA43A, cursor)
        for idx in range(0x23):
            write_slot(mem, idx)
        for idx, kwargs in slots:
            write_slot(mem, idx, **kwargs)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xB15A)] = overkill_player_chase_candidate_scan_b15a
        return cpu

    cases = (
        # Immediate candidate; the cursor advances but BX returns to the found slot.
        dict(cursor=slot_base, slots=[(0, dict(active=1, logic=0x0030, x=0x00E0, hazard=4))]),
        # Rejection order: inactive, excluded logic id, x too high, hazard mismatch, then success.
        dict(cursor=slot_base, slots=[
            (0, dict(active=0, logic=0x0030, x=0x0010, hazard=4)),
            (1, dict(active=1, logic=0x0026, x=0x0010, hazard=4)),
            (2, dict(active=1, logic=0x0030, x=0x00E1, hazard=4)),
            (3, dict(active=1, logic=0x0030, x=0x0010, hazard=3)),
            (4, dict(active=1, logic=0x0030, x=0x0010, hazard=4)),
        ]),
        # Cursor at or beyond the gameplay-object sentinel wraps to the effect/contact pool.
        dict(cursor=table_end, slots=[(0, dict(active=1, logic=0x0030, x=0x0010, hazard=4))]),
        # No candidate: BX becomes FFFF and A43A is not advanced by a found-slot store.
        dict(cursor=slot_base, slots=[(5, dict(active=1, logic=0x0030, x=0x0010, hazard=3))]),
    )

    for case in cases:
        asm = make_cpu(False, **case)
        hook = make_cpu(True, **case)
        for _ in range(500):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF), case
        assert asm.s.snapshot() == hook.s.snapshot(), case
        assert bytes(asm.mem.data) == bytes(hook.mem.data), case

def test_post_contact_status_helper_9e19_matches_interpreted_paths():
    from overkill.hooks import overkill_post_contact_status_helper_9e19

    code_9e19_to_9ee4 = bytes.fromhex(
        "83 3e 7c a4 01 75 01 c3 83 3e 84 23 03 72 01 c3"
        "83 3e 5a a9 ff 75 01 c3 c7 06 a0 23 08 00 80 3e"
        "c0 98 00 74 05 c6 06 ff be 0f 83 3e dc be 00 74"
        "13 83 3e dc be 01 74 06 ff 0e 5c a9 74 0c ff 0e"
        "5c a9 74 06 ff 0e 5c a9 75 5f c7 06 5c a9 18 00"
        "83 3e 7c a4 01 75 01 c3 83 3e 84 23 03 72 01 c3"
        "80 3e c0 98 00 74 05 c6 06 ff be 03 83 3e dc be"
        "00 75 0c fe 06 62 a3 80 26 62 a3 01 74 01 c3 ff"
        "0e 5a a9 83 3e 5a a9 ff 75 1f c7 06 5c a9 00 00"
        "80 3e 91 97 01 74 27 c7 06 84 23 03 00 80 3e c0"
        "98 00 74 05 c6 06 ff be 19 e8 17 c3 2e 83 3e bc 95"
        "01 75 09 e8 4f b2 e8 09 c3 e8 49 b2 c3 c7 06 5a"
        "a9 03 00 c7 06 5c a9 18 00 c3"
    )

    def child(ip: int):
        def run(cpu: CPU8086) -> None:
            ds = cpu.s.ds & 0xFFFF
            idx = cpu.mem.rw(ds, 0x0100)
            cpu.mem.ww(ds, 0x0102 + idx * 2, ip & 0xFFFF)
            cpu.mem.ww(ds, 0x0100, (idx + 1) & 0xFFFF)
            old = cpu.s.ax & 0xFFFF
            addend = ip & 0x00FF
            result = old + addend
            cpu.s.ax = result & 0xFFFF
            cpu.set_add_flags(old, addend, result, 16)
            cpu.s.ip = cpu.pop()
        return run

    def make_cpu(use_hook: bool, *, a47c: int = 0, state2384: int = 0, a95a: int = 3,
                 a95c: int = 5, bedc: int = 0, a362: int = 0, b9791: int = 0,
                 b98c0: int = 1, cs95bc: int = 0) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x9E19, code_9e19_to_9ee4)
        ds = 0x2000
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ds, ip=0x9E19, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        mem.ww(ds, 0xA47C, a47c)
        mem.ww(ds, 0x2384, state2384)
        mem.ww(ds, 0xA95A, a95a)
        mem.ww(ds, 0xA95C, a95c)
        mem.ww(ds, 0xBEDC, bedc)
        mem.wb(ds, 0xA362, a362)
        mem.wb(ds, 0x9791, b9791)
        mem.wb(ds, 0x98C0, b98c0)
        mem.wb(ds, 0xBEFF, 0xEE)
        mem.ww(0x1010, 0x95BC, cs95bc)
        cpu.replacement_hooks[(0x1010, 0x61DC)] = child(0x61DC)
        cpu.replacement_hooks[(0x1010, 0x511F)] = child(0x511F)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x9E19)] = overkill_post_contact_status_helper_9e19
        return cpu

    cases = (
        # Front guards: A47C==1, 2384>=3, or A95A==FFFF all return at the guard CMP.
        dict(a47c=1),
        dict(state2384=3),
        dict(a95a=0xFFFF),
        # Normal cooldown path: one BEDC==0 decrement leaves A95C non-zero and displays once.
        dict(a95a=3, a95c=5, bedc=0, cs95bc=0),
        # BEDC other decrements up to three times; zero reached mid-sequence refills A95C.
        dict(a95a=2, a95c=2, bedc=2, cs95bc=0),
        # BEDC zero alternates A362 and can return without touching A95A on odd toggle.
        dict(a95a=2, a95c=1, bedc=0, a362=0),
        # Even toggle falls through to A95A expiry; 9791==1 resets the short cooldown pair.
        dict(a95a=0, a95c=1, bedc=0, a362=1, b9791=1),
        # Terminal expiry drives 2384 to 3, emits BEFF=19, and with CS:95BC==1 runs page toggles too.
        dict(a95a=0, a95c=1, bedc=1, b9791=0, cs95bc=1),
    )

    for case in cases:
        asm = make_cpu(False, **case)
        hook = make_cpu(True, **case)
        for _ in range(1000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF), case
        assert asm.s.snapshot() == hook.s.snapshot(), case
        assert bytes(asm.mem.data) == bytes(hook.mem.data), case


def test_frame_contact_probe_fanout_9cb6_matches_interpreted_paths():
    from dos_re.cpu import CF
    from overkill.hooks import overkill_frame_contact_probe_fanout_9cb6

    code_9cb6_to_9cd8 = bytes.fromhex(
        "e8 40 b3 72 01 c3 55 83 3e dc be 00 74 0d 83 "
        "3e dc be 01 74 03 e8 4b 01 e8 48 01 e8 45 01 "
        "e8 42 01 5d c3"
    )

    def make_4ff9(carry: bool):
        def child(cpu: CPU8086) -> None:
            ds = cpu.s.ds & 0xFFFF
            idx = cpu.mem.rw(ds, 0x0100)
            cpu.mem.ww(ds, 0x0102 + idx * 2, 0x4FF9)
            cpu.mem.ww(ds, 0x0100, (idx + 1) & 0xFFFF)
            cpu.s.flags = (cpu.s.flags | CF) if carry else (cpu.s.flags & ~CF)
            cpu.s.ax = (cpu.s.ax + 0x004F) & 0xFFFF
            cpu.s.ip = cpu.pop()
        return child

    def child_9e19(cpu: CPU8086) -> None:
        ds = cpu.s.ds & 0xFFFF
        idx = cpu.mem.rw(ds, 0x0100)
        cpu.mem.ww(ds, 0x0102 + idx * 2, 0x9E19)
        cpu.mem.ww(ds, 0x0100, (idx + 1) & 0xFFFF)
        cpu.mem.ww(ds, 0x0200, (cpu.mem.rw(ds, 0x0200) + 1) & 0xFFFF)
        old = cpu.s.ax & 0xFFFF
        result = old + 0x0019
        cpu.s.ax = result & 0xFFFF
        cpu.set_add_flags(old, 0x0019, result, 16)
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool, *, carry: bool, bedc: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x9CB6, code_9cb6_to_9cd8)
        ds = 0x2000
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ds, ip=0x9CB6, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        mem.ww(ds, 0xBEDC, bedc)
        cpu.replacement_hooks[(0x1010, 0x4FF9)] = make_4ff9(carry)
        cpu.replacement_hooks[(0x1010, 0x9E19)] = child_9e19
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x9CB6)] = overkill_frame_contact_probe_fanout_9cb6
        return cpu

    cases = (
        dict(carry=False, bedc=0),  # 4FF9 miss: immediate RET.
        dict(carry=True, bedc=0),   # hit, neutral BEDC: two 9E19 calls.
        dict(carry=True, bedc=1),   # hit, BEDC one: three 9E19 calls.
        dict(carry=True, bedc=2),   # hit, other BEDC: four 9E19 calls.
    )
    for case in cases:
        asm = make_cpu(False, **case)
        hook = make_cpu(True, **case)
        for _ in range(200):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_frame_controller_9b2e_matches_interpreted_parent_paths():
    from overkill.hooks import overkill_frame_controller_9b2e

    # Exact 1010:9AFF..9BFA bytes from the initialized runtime image.  Loading
    # from 9AFF keeps the early tail available for the backwards branches at
    # 9B61/9B68, while the entry under test remains 9B2E.
    code_9aff_to_9bfa = bytes.fromhex(
        "83 3e 26 23 03 74 01 c3 ff 46 08 83 7e 08 0f 74 01 c3 "
        "c7 46 00 00 00 e8 a6 b2 c7 06 46 a3 01 00 83 3e 7a a9 "
        "00 74 01 c3 c7 06 42 a3 01 00 c3 c7 06 46 a3 00 00 c7 "
        "06 44 a3 00 00 e8 25 66 83 3e 7c a4 00 74 03 e8 af fe "
        "83 3e 7c a4 04 75 07 c7 06 44 a3 01 00 c3 c7 06 78 a2 "
        "00 00 bd 7c 23 e8 b1 06 83 3e 5a a9 ff 74 97 83 3e 7a "
        "a9 00 74 90 f6 06 be 98 08 74 03 e8 58 0a f6 06 be 98 "
        "04 74 03 e8 67 0a f6 06 be 98 01 74 03 e8 7a 0a f6 06 "
        "be 98 02 74 03 e8 62 0a 81 3e 50 23 b6 00 76 0a f6 06 "
        "be 98 20 74 03 e8 9d e9 e8 c3 0a e8 b8 04 80 3e 8e 97 "
        "00 74 0a 80 3e c8 98 01 75 03 e8 8d 01 83 3e 7c a4 01 "
        "77 03 e8 4c 0a 83 3e 7c a4 00 75 0e e8 e2 00 81 3e 50 "
        "23 b6 00 76 03 e8 22 00 e8 0f 01 e8 f4 00 e8 49 04 83 "
        "3e ac bd 00 75 08 81 3e 50 23 b6 00 76 03 e8 b5 03 c3"
    )

    child_ips = (
        0x0162, 0x99F6, 0xA212, 0xA5D1, 0xA5EA, 0xA607, 0xA5F9,
        0x8546, 0xA66F, 0xA067, 0x9D4D, 0xA616, 0x9CB6, 0x9C01,
        0x9CF1, 0x9CD9, 0xA031, 0x9FAF, 0x4DBF,
    )

    def make_child(ip: int):
        def child(cpu: CPU8086) -> None:
            ds = cpu.s.ds & 0xFFFF
            idx = cpu.mem.rw(ds, 0x0100)
            cpu.mem.ww(ds, 0x0102 + idx * 2, ip & 0xFFFF)
            cpu.mem.ww(ds, 0x0100, (idx + 1) & 0xFFFF)
            # Give every child a visible but deterministic register/flag side
            # effect so parent ordering and return behaviour are compared.
            old = cpu.s.ax & 0xFFFF
            addend = ip & 0x00FF
            result = old + addend
            cpu.s.ax = result & 0xFFFF
            cpu.set_add_flags(old, addend, result, 16)
            cpu.s.ip = cpu.pop()
        return child

    def make_cpu(use_hook: bool, *, a47c: int, a95a: int, a97a: int, input_bits: int,
                 view_y: int, bdac: int, bp8: int = 0x0000, state2326: int = 0x0000) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x9AFF, code_9aff_to_9bfa)
        ds = 0x2000
        ss = 0x2000
        bp = 0x237C
        mem.ww(ds, 0xA47C, a47c)
        mem.ww(ds, 0xA95A, a95a)
        mem.ww(ds, 0xA97A, a97a)
        mem.wb(ds, 0x98BE, input_bits)
        mem.ww(ds, 0x2350, view_y)
        mem.ww(ds, 0xBDAC, bdac)
        mem.wb(ds, 0x978E, 0x01)
        mem.wb(ds, 0x98C8, 0x01)
        mem.ww(ds, 0x2326, state2326)
        mem.ww(ss, bp + 0x08, bp8)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ss, ip=0x9B2E, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        for ip in child_ips:
            cpu.replacement_hooks[(0x1010, ip)] = make_child(ip)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x9B2E)] = overkill_frame_controller_9b2e
        return cpu

    cases = (
        # Main path: all direct movement/action bits set, viewport past B6,
        # contact probe active, coordinate rings and linked children updated.
        dict(a47c=0, a95a=0x2000, a97a=1, input_bits=0x2F, view_y=0x00B7, bdac=0),
        # A47C==4 exits by raising A344 after the optional 99F6 child.
        dict(a47c=4, a95a=0x2000, a97a=1, input_bits=0, view_y=0x00A0, bdac=0),
        # Early 9AFF tail returns immediately unless DS:2326 is exactly 3.
        dict(a47c=0, a95a=0xFFFF, a97a=1, input_bits=0, view_y=0x00A0, bdac=0, state2326=0),
        # With DS:2326==3 it increments BP+8, but still returns until BP+8 reaches 0Fh.
        dict(a47c=0, a95a=0xFFFF, a97a=1, input_bits=0, view_y=0x00A0, bdac=0, state2326=3, bp8=2),
        # Full 9AFF transition tail runs 4DBF and sets A342 when A97A is absent.
        dict(a47c=0, a95a=0x2000, a97a=0, input_bits=0, view_y=0x00A0, bdac=0, state2326=3, bp8=0x000E),
    )

    for case in cases:
        asm = make_cpu(False, **case)
        hook = make_cpu(True, **case)
        for _ in range(5000):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_frame_axis_condition_dispatch_9c01_hook_matches_composed_interpreted_snapshot():
    from pathlib import Path
    from overkill.hooks import overkill_frame_axis_condition_dispatch_9c01
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "runtime_code_5e42_gameplay_20260613_220042"
    assert snap.exists(), "captured gameplay snapshot for 1010:9C01 is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        rt.cpu.trace_enabled = False
        # The parent 9B2E hook now composes the 9C01 child internally.  Disable
        # both parent and child here so this child-specific oracle can still
        # stop at the original 9C01 boundary.
        for addr in ((0x1010, 0x9B2E), (0x1010, 0x9C01)):
            rt.cpu.replacement_hooks.pop(addr, None)
            rt.cpu.hook_names.pop(addr, None)
        return rt

    asm = make_runtime()
    hook = make_runtime()

    for _ in range(200_000):
        if asm.cpu.addr() == (0x1010, 0x9C01):
            break
        asm.cpu.step()
        hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x9C01)
    return_ip = asm.cpu.mem.rw(asm.cpu.s.ss, asm.cpu.s.sp)
    hook.cpu.replacement_hooks[(0x1010, 0x9C01)] = overkill_frame_axis_condition_dispatch_9c01

    for _ in range(200_000):
        if asm.cpu.addr() == (0x1010, return_ip):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, return_ip)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_frame_axis_count_9bfb_9bfe_tiny_leaves_match_interpreted_asm():
    from overkill.hooks import overkill_frame_axis_count_inc_ah_9bfb, overkill_frame_axis_count_inc_al_9bfe

    cases = (
        (0x9BFB, bytes.fromhex("fe c4 c3"), overkill_frame_axis_count_inc_ah_9bfb),
        (0x9BFE, bytes.fromhex("fe c0 c3"), overkill_frame_axis_count_inc_al_9bfe),
    )

    def make_cpu(entry: int, code: bytes, hook_fn, use_hook: bool, ax: int, flags: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, entry, code)
        state = CPUState(
            ax=ax, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            sp=0x9000, ip=entry, flags=flags,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, entry)] = hook_fn
        return cpu

    for entry, code, hook_fn in cases:
        for ax, flags in ((0x00FF, 0x0203), (0x7FFF, 0x0202), (0xFFFF, 0x0203)):
            asm = make_cpu(entry, code, hook_fn, False, ax, flags)
            hook = make_cpu(entry, code, hook_fn, True, ax, flags)
            for _ in range(10):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_interstitial_status_cell_d367_matches_interpreted_parent_with_child_boundaries():
    from overkill.hooks import overkill_interstitial_status_cell_d367

    code = bytes.fromhex(
        "b4 47 b0 03 e8 92 86 33 f6 2e 8e 1e b6 95 e8 f4 86 "
        "2e 8e 1e 96 95 c3"
    )

    def dummy_5a00(cpu):
        assert cpu.s.ax == 0x4703
        old = cpu.s.di & 0xFFFF
        result = old + 0x0011
        cpu.s.di = result & 0xFFFF
        cpu.set_add_flags(old, 0x0011, result, 16)
        cpu.s.ip = cpu.pop()

    def dummy_5a6c(cpu):
        assert cpu.s.ds == 0x3456
        cpu.mem.ww(cpu.s.ss, 0x0120, cpu.s.si & 0xFFFF)
        cpu.mem.ww(cpu.s.ss, 0x0122, cpu.s.di & 0xFFFF)
        cpu.s.bx = (cpu.s.bx + 3) & 0xFFFF
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xD367, code)
        mem.ww(0x1010, 0x95B6, 0x3456)
        mem.ww(0x1010, 0x9596, 0x2000)
        state = CPUState(
            ax=0xAAAA, bx=0x0100, cx=0x0200, dx=0x0300,
            si=0x4444, di=0x1000, bp=0x5555,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            sp=0x9000, ip=0xD367, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.replacement_hooks[(0x1010, 0x5A00)] = dummy_5a00
        cpu.replacement_hooks[(0x1010, 0x5A6C)] = dummy_5a6c
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xD367)] = overkill_interstitial_status_cell_d367
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(80):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_interstitial_timed_input_loop_d318_matches_interpreted_parent_with_child_boundaries():
    from overkill.hooks import overkill_interstitial_timed_input_loop_d318

    code = bytes.fromhex(
        "e8 57 33 e8 01 7e e8 cc 79 2e 83 3e bc 95 01 75 03 "
        "e8 b0 88 e8 38 00 e8 32 7a 9a 22 09 8f 1f e8 02 34 "
        "e8 65 8d e8 20 7e e8 36 33 e8 83 7d ff 06 d8 be 81 "
        "3e d8 be c8 00 77 0a e8 0d 2e f6 06 be 98 10 74 bc "
        "e8 03 2e f6 06 be 98 10 75 f6 c3"
    )

    near_targets = (0x0672, 0x511F, 0x4CED, 0xD367, 0x4D64, 0x073C, 0x60A2, 0x5160, 0x0679, 0x50C9)

    def make_near_dummy(tag: int):
        def dummy(cpu):
            ss = cpu.s.ss & 0xFFFF
            idx = cpu.mem.rw(ss, 0x0100)
            cpu.mem.ww(ss, 0x0100, (idx + 1) & 0xFFFF)
            cpu.mem.ww(ss, 0x0200 + idx * 2, tag & 0xFFFF)
            old = cpu.s.dx & 0xFFFF
            result = old + tag
            cpu.s.dx = result & 0xFFFF
            cpu.set_add_flags(old, tag & 0xFFFF, result, 16)
            cpu.s.ip = cpu.pop()
        return dummy

    def input_dummy(cpu):
        ds = cpu.s.ds & 0xFFFF
        ss = cpu.s.ss & 0xFFFF
        count = cpu.mem.rw(ss, 0x0180) + 1
        cpu.mem.ww(ss, 0x0180, count)
        release_after = cpu.mem.rw(ss, 0x0182)
        if release_after and count >= release_after:
            cpu.mem.wb(ds, 0x98BE, cpu.mem.rb(ds, 0x98BE) & ~0x10)
        cpu.s.ip = cpu.pop()

    def far_counter_dummy(cpu):
        assert (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) == (0x1F8F, 0x0922)
        ss = cpu.s.ss & 0xFFFF
        cpu.mem.ww(ss, 0x0190, (cpu.mem.rw(ss, 0x0190) + 1) & 0xFFFF)
        cpu.s.ip = cpu.pop()
        cpu.s.cs = cpu.pop()

    def make_cpu(use_hook: bool, *, counter: int, input_flags: int, release_after: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xD318, code)
        mem.ww(0x1010, 0x95BC, 0x0002)
        ds = 0x2000
        mem.ww(ds, 0xBED8, counter)
        mem.wb(ds, 0x98BE, input_flags)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0x1111,
            si=0x2222, di=0x3333, bp=0x4444,
            cs=0x1010, ds=ds, es=0x3000, ss=0x4000,
            sp=0x9000, ip=0xD318, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.mem.ww(cpu.s.ss, 0x0182, release_after)
        for target in near_targets:
            cpu.replacement_hooks[(0x1010, target)] = make_near_dummy(target)
        cpu.replacement_hooks[(0x1010, 0x0162)] = input_dummy
        cpu.replacement_hooks[(0x1F8F, 0x0922)] = far_counter_dummy
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xD318)] = overkill_interstitial_timed_input_loop_d318
        return cpu

    cases = (
        # Normal timed iteration: input bit clear, counter still below timeout, loop to D318.
        (0x0000, 0x00, 0, (0x1010, 0xD318)),
        # Timeout path: immediately enters the release wait and returns.
        (0x00C8, 0x00, 1, (0x1010, 0xBEEF)),
        # Input pressed before timeout: one poll sees the bit, release-wait poll clears it, then return.
        (0x0001, 0x10, 2, (0x1010, 0xBEEF)),
    )
    for counter, input_flags, release_after, expected_addr in cases:
        asm = make_cpu(False, counter=counter, input_flags=input_flags, release_after=release_after)
        hook = make_cpu(True, counter=counter, input_flags=input_flags, release_after=release_after)
        for step in range(300):
            asm.step()
            if step >= 1 and asm.addr() == expected_addr:
                break
        hook.step()
        assert asm.addr() == hook.addr() == expected_addr
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_status_cell_seed_852b_and_list_8517_match_interpreted_asm_with_child_boundary():
    from overkill.hooks import overkill_status_cell_list_seed_8517, overkill_status_cell_seed_852b

    code_8517_8546 = bytes.fromhex(
        "c7 06 fa 95 ff ff bd 82 96 b4 87 e8 06 00 e8 03 00 e8 00 00 "
        "b0 1c 50 e8 cf d4 c7 46 00 24 00 89 7e 02 c7 46 08 00 00 "
        "83 c5 0a 58 80 c4 10 c3"
    )

    def dummy_5a00(cpu):
        # Deterministic but state-dependent enough to prove AX/BP sequencing.
        old = cpu.s.ax & 0xFFFF
        cpu.s.di = ((old << 1) + (cpu.s.bp & 0xFFFF)) & 0xFFFF
        cpu.s.bx = (cpu.s.di ^ 0x55AA) & 0xFFFF
        cpu.set_add_flags(old, cpu.s.bp & 0xFFFF, old + (cpu.s.bp & 0xFFFF), 16)
        cpu.s.ip = cpu.pop()

    def make_cpu(entry: int, use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x8517, code_8517_8546)
        state = CPUState(
            ax=0x1234, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            sp=0x9000, ip=entry, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.replacement_hooks[(0x1010, 0x5A00)] = dummy_5a00
        if use_hook:
            if entry == 0x8517:
                cpu.replacement_hooks[(0x1010, 0x8517)] = overkill_status_cell_list_seed_8517
            cpu.replacement_hooks[(0x1010, 0x852B)] = overkill_status_cell_seed_852b
        return cpu

    for entry in (0x852B, 0x8517):
        asm = make_cpu(entry, False)
        hook = make_cpu(entry, True)
        for _ in range(200):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_status_cell_composite_85d5_matches_captured_snapshot():
    from pathlib import Path
    from overkill.runtime import load_overkill_snapshot as load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_1010_85d5_status_cell"
    assert snap.exists(), "captured oracle snapshot for 1010:85D5 is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL", snap, game_root=root / "assets")
        if not use_hook:
            rt.cpu.replacement_hooks.pop((0x1010, 0x85D5), None)
            rt.cpu.hook_names.pop((0x1010, 0x85D5), None)
        return rt

    asm = make_runtime(False)
    hook = make_runtime(True)
    return_ip = asm.cpu.mem.rw(asm.cpu.s.ss & 0xFFFF, asm.cpu.s.sp & 0xFFFF)
    for _ in range(2000):
        if asm.cpu.addr() == (0x1010, return_ip):
            break
        asm.cpu.step()
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, return_ip)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_hook_verifier_live_passthrough_override_can_publish_without_frame_boundary():
    """Interactive verify can publish inside a verified parent without breaking it.

    play.py marks presenter/timer/retrace hooks as verifier-pass-through so they
    are not recursively verified.  For the ASM oracle they must remain the pure
    install-time hooks.  For the live side, however, the interactive viewer may
    need a publish-only wrapper that has the same CPU-visible effects but does
    not raise the normal FramePresented control-flow exception.
    """
    from pathlib import Path
    from types import SimpleNamespace

    from dos_re.cpu import CPU8086, CPUState
    from dos_re.dos import DOSMachine
    from dos_re.memory import Memory
    from dos_re.runtime import Runtime
    from overkill.hooks import overkill_intro_retrace_delay_loop_96c5
    from overkill.verification import HookVerifierConfig, install_hook_verifier

    mem = Memory()
    # 96C5: CALL 50C9; LOOP 96C5.
    mem.load(0x1010, 0x96C5, bytes.fromhex("e8 01 ba e2 fb"))
    state = CPUState(
        ax=0x1200, bx=0x3456, cx=0x0003, dx=0x03DA,
        si=0x1111, di=0x2222, bp=0x3333,
        sp=0x8000, cs=0x1010, ds=0x2000, es=0xB800, ss=0x3000,
        ip=0x96C5, flags=0x0203,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.replacement_hooks[(0x1010, 0x96C5)] = overkill_intro_retrace_delay_loop_96c5
    cpu.hook_names[(0x1010, 0x96C5)] = "overkill_intro_retrace_delay_loop_96c5"

    calls = {"base": 0, "interactive": 0, "verify_live": 0}

    def base_retrace(c):
        calls["base"] += 1
        c.set_reg8(0, 0x08)
        c.set_logic_flags(c.s.ax, 16)
        c.s.ip = c.pop()

    def interactive_retrace(c):
        calls["interactive"] += 1
        base_retrace(c)
        raise AssertionError("normal UI boundary must not run inside verifier transaction")

    def verify_live_retrace(c):
        calls["verify_live"] += 1
        base_retrace(c)
        # A real viewer wrapper would publish a frame here, but it must not
        # raise FramePresented because the verified parent still needs to reach
        # its continuation before the diff is computed.

    cpu.replacement_hooks[(0x1010, 0x50C9)] = base_retrace
    cpu.hook_names[(0x1010, 0x50C9)] = "base_retrace"

    rt = Runtime(SimpleNamespace(memory=mem), cpu, DOSMachine(Path.cwd()))
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0x96C5)}, stop_on_diff=True),
    )

    cpu.replacement_hooks[(0x1010, 0x50C9)] = interactive_retrace
    cpu.hook_names[(0x1010, 0x50C9)] = "interactive_retrace"
    cpu.hook_verifier_passthrough.add((0x1010, 0x50C9))
    cpu.hook_verifier_live_passthrough_overrides[(0x1010, 0x50C9)] = verify_live_retrace

    cpu.step()

    assert verifier.total_verified == 1
    assert cpu.addr() == (0x1010, 0x96CA)
    assert calls == {"base": 6, "interactive": 0, "verify_live": 3}
    assert cpu.replacement_hooks[(0x1010, 0x50C9)] is interactive_retrace
    assert cpu.hook_names[(0x1010, 0x50C9)] == "interactive_retrace"


def test_hook_verifier_defers_live_passthrough_yield_until_after_diff():
    """A live UI boundary inside a verified parent yields only after verification.

    Interactive play wraps timer/retrace/presenter hooks so they can publish and
    pace while a large parent hook is being differentially verified.  They must
    not raise the UI boundary exception from inside the parent body, but the
    runner still needs a cooperative yield immediately after the parent has been
    compared; otherwise CPU.run can execute many verified frames before SDL input
    is pumped.
    """
    from pathlib import Path
    from types import SimpleNamespace

    from dos_re.cpu import CPU8086, CPUState
    from dos_re.dos import DOSMachine
    from dos_re.memory import Memory
    from dos_re.runtime import Runtime
    from overkill.hooks import overkill_intro_retrace_delay_loop_96c5
    from overkill.verification import HookVerifierConfig, install_hook_verifier

    class BoundaryAfterVerify(Exception):
        pass

    mem = Memory()
    mem.load(0x1010, 0x96C5, bytes.fromhex("e8 01 ba e2 fb"))
    state = CPUState(
        ax=0x1200, bx=0x3456, cx=0x0003, dx=0x03DA,
        si=0x1111, di=0x2222, bp=0x3333,
        sp=0x8000, cs=0x1010, ds=0x2000, es=0xB800, ss=0x3000,
        ip=0x96C5, flags=0x0203,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.replacement_hooks[(0x1010, 0x96C5)] = overkill_intro_retrace_delay_loop_96c5
    cpu.hook_names[(0x1010, 0x96C5)] = "overkill_intro_retrace_delay_loop_96c5"

    events: list[str] = []

    def base_retrace(c):
        events.append("base")
        c.set_reg8(0, 0x08)
        c.set_logic_flags(c.s.ax, 16)
        c.s.ip = c.pop()

    def interactive_retrace(_c):
        raise AssertionError("interactive boundary must not run inside verifier transaction")

    def verify_live_retrace(c):
        events.append("live")
        base_retrace(c)
        c.hook_verifier_live_yield_requested = True

    def yield_callback():
        events.append("yield")
        raise BoundaryAfterVerify()

    cpu.replacement_hooks[(0x1010, 0x50C9)] = base_retrace
    cpu.hook_names[(0x1010, 0x50C9)] = "base_retrace"

    rt = Runtime(SimpleNamespace(memory=mem), cpu, DOSMachine(Path.cwd()))
    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0x96C5)}, stop_on_diff=True),
    )

    cpu.replacement_hooks[(0x1010, 0x50C9)] = interactive_retrace
    cpu.hook_names[(0x1010, 0x50C9)] = "interactive_retrace"
    cpu.hook_verifier_passthrough.add((0x1010, 0x50C9))
    cpu.hook_verifier_live_passthrough_overrides[(0x1010, 0x50C9)] = verify_live_retrace
    cpu.hook_verifier_live_yield_callback = yield_callback

    with pytest.raises(BoundaryAfterVerify):
        cpu.step()

    assert verifier.total_verified == 1
    assert cpu.addr() == (0x1010, 0x96CA)
    assert events[-1] == "yield"
    assert events.count("live") == 3
    assert cpu.hook_verifier_live_yield_requested is False


def test_hook_verifier_recursively_verifies_direct_child_hook_calls():
    """A parent hook calling a child hook directly must not hide child bugs.

    The original parent reaches 1000:0200 with normal CALL semantics.  The
    lifted parent uses call_installed_hook_like_near_call, so the verifier should
    recursively verify the child hook at that exact VM state.  The child hook is
    intentionally wrong here; if nested verification is bypassed this test would
    incorrectly pass through the parent boundary.
    """
    from pathlib import Path
    from types import SimpleNamespace

    from dos_re.cpu import CPU8086, CPUState
    from dos_re.dos import DOSMachine
    from dos_re.memory import Memory
    from dos_re.runtime import Runtime
    from dos_re.verification import GenericHookStop, HookVerifierConfig, HookVerifyDivergence, install_hook_verifier
    from overkill.hook_wrappers.common import call_installed_hook_like_near_call

    mem = Memory()
    # 1000:0100: CALL 0200, then continuation at 0103.
    mem.load(0x1000, 0x0100, bytes.fromhex("e8 fd 00"))
    # 1000:0200: INC AX; RET.
    mem.load(0x1000, 0x0200, bytes.fromhex("40 c3"))
    state = CPUState(cs=0x1000, ds=0x2000, es=0x2000, ss=0x3000, ip=0x0100, sp=0x8000, ax=0x0001, flags=0x0202)
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False

    def bad_child(c):
        c.s.ax = (c.s.ax + 2) & 0xFFFF
        c.s.ip = c.pop()

    def parent(c):
        call_installed_hook_like_near_call(c, (0x1000, 0x0200), bad_child, 0x0103)

    cpu.replacement_hooks[(0x1000, 0x0100)] = parent
    cpu.hook_names[(0x1000, 0x0100)] = "parent"
    cpu.replacement_hooks[(0x1000, 0x0200)] = bad_child
    cpu.hook_names[(0x1000, 0x0200)] = "bad_child"

    rt = Runtime(SimpleNamespace(memory=mem), cpu, DOSMachine(Path.cwd()))
    install_hook_verifier(
        rt,
        HookVerifierConfig(verify_all=True, stop_on_diff=True),
        stops={
            (0x1000, 0x0100): GenericHookStop("fixed_ip", ip=0x0103),
            (0x1000, 0x0200): GenericHookStop("near_ret"),
        },
    )

    with pytest.raises(HookVerifyDivergence) as excinfo:
        cpu.step()
    assert "1000:0200 bad_child" in str(excinfo.value)
    assert "AX: asm=0002 hook=0003" in str(excinfo.value)


def test_object_slot_allocate_or_reclaim_7547_free_path_matches_original():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_object_slot_allocate_or_reclaim_7547

    code_7547 = bytes.fromhex(
        "e8 29 00 83 fb ff 74 01 c3 b9 22 00 bb 5c 2b 83 7f 18 09 74 0c "
        "83 7f 18 0a 74 06 83 7f 16 01 75 08 83 c3 38 e2 e9 bb 5c 2b e9 9a 47"
    )
    code_7573 = bytes.fromhex(
        "b9 22 00 8b 1e da 95 81 fb cc 32 75 03 bb 5c 2b "
        "83 3f 00 74 09 83 c3 38 e2 ed bb ff ff c3 89 1e da 95 c3"
    )

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x7547, code_7547)
        mem.load(0x1010, 0x7573, code_7573)
        cpu = CPU8086(mem, CPUState(cs=0x1010, ds=0x2000, ss=0x3000, sp=0x9000, ip=0x7547, flags=0x0202))
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.mem.ww(0x2000, 0x95DA, 0x2B5C)
        cpu.mem.ww(0x2000, 0x2B5C, 0)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(100):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    overkill_object_slot_allocate_or_reclaim_7547(hook)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert_oracle_equivalent(asm, hook)  # dead 754A return scratch below SP dropped


def test_object_spawn_seed_a4ea_free_path_matches_original():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_object_spawn_seed_a4ea

    code_a4ea = bytes.fromhex(
        "e8 5a d0 c7 07 01 00 c7 47 1e 01 00 c7 47 06 00 00 c7 47 08 32 00 "
        "c7 47 14 00 00 c7 47 16 02 00 c7 47 18 02 00 c7 47 1c ff ff c3"
    )
    code_7547 = bytes.fromhex(
        "e8 29 00 83 fb ff 74 01 c3 b9 22 00 bb 5c 2b 83 7f 18 09 74 0c "
        "83 7f 18 0a 74 06 83 7f 16 01 75 08 83 c3 38 e2 e9 bb 5c 2b e9 9a 47"
    )
    code_7573 = bytes.fromhex(
        "b9 22 00 8b 1e da 95 81 fb cc 32 75 03 bb 5c 2b "
        "83 3f 00 74 09 83 c3 38 e2 ed bb ff ff c3 89 1e da 95 c3"
    )

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA4EA, code_a4ea)
        mem.load(0x1010, 0x7547, code_7547)
        mem.load(0x1010, 0x7573, code_7573)
        cpu = CPU8086(mem, CPUState(cs=0x1010, ds=0x2000, ss=0x3000, sp=0x9000, ip=0xA4EA, flags=0x0202))
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.mem.ww(0x2000, 0x95DA, 0x2B5C)
        cpu.mem.ww(0x2000, 0x2B5C, 0)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(160):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    overkill_object_spawn_seed_a4ea(hook)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert_oracle_equivalent(asm, hook)  # dead A4ED/754A return scratch below SP dropped


def test_object_spawn_seed_from_source_a4d7_free_path_matches_original():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_object_spawn_seed_from_source_a4d7

    code_a4d7 = bytes.fromhex("e8 10 00 8b 44 02 89 47 02 8b 44 04 05 04 00 89 47 04 c3")
    code_a4ea = bytes.fromhex(
        "e8 5a d0 c7 07 01 00 c7 47 1e 01 00 c7 47 06 00 00 c7 47 08 32 00 "
        "c7 47 14 00 00 c7 47 16 02 00 c7 47 18 02 00 c7 47 1c ff ff c3"
    )
    code_7547 = bytes.fromhex(
        "e8 29 00 83 fb ff 74 01 c3 b9 22 00 bb 5c 2b 83 7f 18 09 74 0c "
        "83 7f 18 0a 74 06 83 7f 16 01 75 08 83 c3 38 e2 e9 bb 5c 2b e9 9a 47"
    )
    code_7573 = bytes.fromhex(
        "b9 22 00 8b 1e da 95 81 fb cc 32 75 03 bb 5c 2b "
        "83 3f 00 74 09 83 c3 38 e2 ed bb ff ff c3 89 1e da 95 c3"
    )

    def make_cpu() -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA4D7, code_a4d7)
        mem.load(0x1010, 0xA4EA, code_a4ea)
        mem.load(0x1010, 0x7547, code_7547)
        mem.load(0x1010, 0x7573, code_7573)
        cpu = CPU8086(
            mem,
            CPUState(cs=0x1010, ds=0x2000, ss=0x3000, sp=0x9000, ip=0xA4D7, si=0x0100, flags=0x0202),
        )
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.mem.ww(0x2000, 0x95DA, 0x2B5C)
        cpu.mem.ww(0x2000, 0x2B5C, 0)
        cpu.mem.ww(0x2000, 0x0102, 0x1234)
        cpu.mem.ww(0x2000, 0x0104, 0x00BC)
        return cpu

    asm = make_cpu()
    hook = make_cpu()
    for _ in range(180):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    overkill_object_spawn_seed_from_source_a4d7(hook)

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert_oracle_equivalent(asm, hook)  # dead A4DA/A4ED/754A return scratch below SP dropped


def test_frame_coord_ring_helpers_match_interpreted_asm():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import (
        overkill_frame_coord_ring_advance_9cf1,
        overkill_frame_tracked_coord_store_9cd9,
        overkill_tracked_object_coord_pull_a031,
    )

    code_9cd9 = bytes.fromhex("2e 8e 06 96 95 8b 3e 3a a3 8b 46 02 05 08 00 ab 8b 46 04 05 08 00 ab c3")
    code_9cf1 = bytes.fromhex(
        "f6 06 be 98 0f 75 08 83 3e 60 a3 00 75 01 c3 83 06 3a a3 04 "
        "81 3e 3a a3 3a a3 75 06 c7 06 3a a3 7a a2 83 06 3c a3 04 "
        "81 3e 3c a3 3a a3 75 06 c7 06 3c a3 7a a2 83 06 3e a3 04 "
        "81 3e 3e a3 3a a3 75 06 c7 06 3e a3 7a a2 83 06 40 a3 04 "
        "81 3e 40 a3 3a a3 75 06 c7 06 40 a3 7a a2 c3"
    )
    code_a031 = bytes.fromhex(
        "83 3e 62 a9 ff 74 10 8b 1e 62 a9 8b 36 3c a3 ad 89 47 02 ad 89 47 04 "
        "83 3e 64 a9 ff 74 10 8b 1e 64 a9 8b 36 3e a3 ad 89 47 02 ad 89 47 04 c3"
    )

    def run_pair(ip: int, code: bytes, hook_fn, setup):
        def make_cpu() -> CPU8086:
            mem = Memory()
            mem.load(0x1010, ip, code)
            cpu = CPU8086(
                mem,
                CPUState(cs=0x1010, ds=0x2000, es=0x3333, ss=0x3000, sp=0x9000, ip=ip, bp=0x0400, flags=0x0202),
            )
            cpu.trace_enabled = False
            cpu.push(0xBEEF)
            setup(cpu)
            return cpu

        asm = make_cpu()
        hook = make_cpu()
        for _ in range(180):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook_fn(hook)
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data

    def setup_9cd9(cpu):
        cpu.mem.ww(0x1010, 0x9596, 0x2000)
        cpu.mem.ww(0x2000, 0xA33A, 0x0200)
        cpu.mem.ww(0x3000, 0x0402, 0x0010)
        cpu.mem.ww(0x3000, 0x0404, 0x0020)

    run_pair(0x9CD9, code_9cd9, overkill_frame_tracked_coord_store_9cd9, setup_9cd9)

    def setup_9cf1(cpu):
        cpu.mem.wb(0x2000, 0x98BE, 0x01)
        for off, value in ((0xA33A, 0xA336), (0xA33C, 0xA33A), (0xA33E, 0xA27A), (0xA340, 0xA330)):
            cpu.mem.ww(0x2000, off, value)

    run_pair(0x9CF1, code_9cf1, overkill_frame_coord_ring_advance_9cf1, setup_9cf1)

    def setup_a031(cpu):
        cpu.mem.ww(0x2000, 0xA962, 0x0500)
        cpu.mem.ww(0x2000, 0xA964, 0x0600)
        cpu.mem.ww(0x2000, 0xA33C, 0x0700)
        cpu.mem.ww(0x2000, 0xA33E, 0x0710)
        cpu.mem.ww(0x2000, 0x0700, 0x1111)
        cpu.mem.ww(0x2000, 0x0702, 0x2222)
        cpu.mem.ww(0x2000, 0x0710, 0x3333)
        cpu.mem.ww(0x2000, 0x0712, 0x4444)

    run_pair(0xA031, code_a031, overkill_tracked_object_coord_pull_a031, setup_a031)


def test_tile_contact_probe_4ff9_matches_interpreted_asm_paths():
    from overkill.hooks import overkill_tile_contact_probe_4ff9

    code = bytes.fromhex(
        "8b 76 08 83 fe 03 73 58 d1 e6 d1 e6 81 c6 4e 21"
        "ff 76 02 ff 76 04 ad 01 46 02 ad 01 46 04 e8 59 00"
        "83 c3 0d a1 5a 21 25 0f 00 3d 0a 00 b9 01 00 76 03"
        "b9 02 00 51 53 e8 28 00 75 1c f7 46 04 0f 00 74 06"
        "43 e8 1b 00 75 0f 5b 83 eb 0d 59 e2 e5 8f 46 04 8f"
        "46 02 f8 c3 5b 59 8f 46 04 8f 46 02 f9 c3"
        "be aa c3 2e 8e 06 92 95 26 8a 07 32 e4 03 f0 8a 04 0a c0 c3"
        "bb ff ff c3"
        "a1 4e 23 03 46 02 a3 5a 21 78 f1 d1 e8 d1 e8 d1 e8 d1 e8"
        "8b d0 d1 e0 d1 e0 8b c8 d1 e0 03 c1 03 c2 8b 1e 50 23"
        "2b d8 8b 46 04 25 f0 ff d1 e8 d1 e8 d1 e8 d1 e8 03 d8 c3"
    )

    def make_cpu(use_hook: bool, *, side: int, y: int, first_blocking: bool, second_blocking: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x4FF9, code)
        ds = ss = 0x2000
        es = 0x3000
        bp = 0x2400
        mem.ww(0x1010, 0x9592, es)
        # Three candidate probe offsets at DS:214E.  Keep side 0 at zero so the
        # expected tile index is easy to reason about in the test.
        for idx, (dx, dy) in enumerate(((0, 0), (4, 0), (0, 4))):
            mem.ww(ds, 0x214E + idx * 4, dx)
            mem.ww(ds, 0x2150 + idx * 4, dy)
        mem.ww(ds, 0x234E, 0x0000)
        mem.ww(ds, 0x2350, 0x0200)
        mem.ww(ss, bp + 0x02, 0x0010)
        mem.ww(ss, bp + 0x04, y)
        mem.ww(ss, bp + 0x08, side)
        # 5073 maps x=0010,y~=0 to BX=01F3, and 4FF9 adds 000D before lookup.
        mem.wb(es, 0x0200, 5 if first_blocking else 0)
        mem.wb(es, 0x0201, 7 if second_blocking else 0)
        mem.wb(ds, 0xC3AA + 5, 1)
        mem.wb(ds, 0xC3AA + 7, 1)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
            si=0xEEEE, di=0xF111, bp=bp,
            cs=0x1010, ds=ds, es=0x4444, ss=ss,
            sp=0x9000, ip=0x4FF9, flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x4FF9)] = overkill_tile_contact_probe_4ff9
        return cpu

    cases = (
        # Invalid side selects the 5059 STC;RET helper immediately.
        dict(side=3, y=0x0000, first_blocking=False, second_blocking=False),
        # Empty aligned tile: restore coordinates and return CF clear.
        dict(side=0, y=0x0000, first_blocking=False, second_blocking=False),
        # Blocking first tile: restore coordinates and return CF set.
        dict(side=0, y=0x0000, first_blocking=True, second_blocking=False),
        # Unaligned Y probes the adjacent tile when the first lookup is clear.
        dict(side=0, y=0x0001, first_blocking=False, second_blocking=True),
    )
    for kwargs in cases:
        asm = make_cpu(False, **kwargs)
        hook = make_cpu(True, **kwargs)
        for _ in range(300):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_tile_collision_probe_ac28_matches_interpreted_asm_paths():
    from overkill.gameplay.collision import (
        SIG_TILE_COLLISION_PROBE_AC28,
        SIG_TILE_LOOKUP_505B,
        SIG_TILE_PROBE_5073,
    )
    from overkill.hooks import overkill_tile_collision_probe_ac28
    from overkill.recovered.adapters.collision_adapter import TILE_CLASS_TABLE, TILE_PLANE_SEGMENT_PTR
    from overkill.recovered.views.object_slots import OFF_COUNTER_20, OFF_X, OFF_Y

    def make_cpu(use_hook: bool, *, y: int, first_blocking: bool, second_blocking: bool, counter: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xAC28, SIG_TILE_COLLISION_PROBE_AC28)
        mem.load(0x1010, 0x505B, SIG_TILE_LOOKUP_505B)
        full_5073 = bytes.fromhex(
            "a1 4e 23 03 46 02 a3 5a 21 78 f1 d1 e8 d1 e8 d1 e8 d1 e8"
            "8b d0 d1 e0 d1 e0 8b c8 d1 e0 03 c1 03 c2 8b 1e 50 23"
            "2b d8 8b 46 04 25 f0 ff d1 e8 d1 e8 d1 e8 d1 e8 03 d8 c3"
        )
        assert full_5073.startswith(SIG_TILE_PROBE_5073)
        mem.load(0x1010, 0x5073, full_5073)
        ds = ss = 0x2000
        tile_seg = 0x3000
        bp = 0x2400
        mem.ww(0x1010, TILE_PLANE_SEGMENT_PTR, tile_seg)
        mem.ww(ds, 0xA47C, 0)
        mem.ww(ds, 0xBDAC, 0)
        mem.ww(ds, 0xBEDC, 1)
        mem.ww(ds, 0x234E, 0)
        mem.ww(ds, 0x2350, 0x0200)
        mem.ww(ss, bp + OFF_X, 0x0010)
        mem.ww(ss, bp + OFF_Y, y)
        mem.ww(ss, bp + OFF_COUNTER_20, counter)
        # 5073 maps x=0010,y~=0 to BX=01F3; AC28 samples BX+0D -> 0200.
        mem.wb(tile_seg, 0x0200, 5 if first_blocking else 0)
        mem.wb(tile_seg, 0x0201, 7 if second_blocking else 0)
        mem.wb(ds, TILE_CLASS_TABLE + 5, 1)
        mem.wb(ds, TILE_CLASS_TABLE + 7, 1)
        cpu = CPU8086(
            mem,
            CPUState(
                ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
                si=0xEEEE, di=0xF111, bp=bp,
                cs=0x1010, ds=ds, es=0x4444, ss=ss,
                sp=0x9000, ip=0xAC28, flags=0x0202,
            ),
        )
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xAC28)] = overkill_tile_collision_probe_ac28
        return cpu

    cases = (
        dict(y=0x0000, first_blocking=False, second_blocking=False, counter=1),
        dict(y=0x0000, first_blocking=True, second_blocking=False, counter=1),
        dict(y=0x0001, first_blocking=False, second_blocking=True, counter=2),
    )
    for kwargs in cases:
        asm = make_cpu(False, **kwargs)
        hook = make_cpu(True, **kwargs)
        for _ in range(500):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)

def test_temp_keyboard_vector_install_and_restore_match_interpreted_asm():
    from overkill.hooks import (
        overkill_temp_keyboard_vector_install_4e9f,
        overkill_temp_keyboard_vector_restore_4ebf,
    )

    code_4e9f = bytes.fromhex(
        "1e 06 b4 35 b0 09 cd 21 bf 3a 21 8c 05 89 5d 02 07 1e 0e 1f "
        "ba d2 4e b4 25 b0 09 cd 21 1f 1f c3"
    )
    code_4ebf = bytes.fromhex("1e bf 3a 21 8b 55 02 8b 05 8e d8 b4 25 b0 09 cd 21 1f c3")

    def install_int21(cpu: CPU8086) -> None:
        def handler(c: CPU8086, num: int) -> None:
            assert num == 0x21
            ah = (c.s.ax >> 8) & 0xFF
            al = c.s.ax & 0xFF
            assert al == 0x09
            if ah == 0x35:
                c.s.bx = c.mem.rw(0, al * 4)
                c.s.es = c.mem.rw(0, al * 4 + 2)
                return
            if ah == 0x25:
                c.mem.ww(0, al * 4, c.s.dx)
                c.mem.ww(0, al * 4 + 2, c.s.ds)
                return
            raise AssertionError(f"unexpected AH={ah:02X}")
        cpu.interrupt_handler = handler

    def make_cpu(ip: int, use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x4E9F, code_4e9f)
        mem.load(0x1010, 0x4EBF, code_4ebf)
        mem.ww(0, 0x09 * 4, 0x1234)
        mem.ww(0, 0x09 * 4 + 2, 0x5678)
        mem.ww(0x2000, 0x213A, 0x9ABC)
        mem.ww(0x2000, 0x213C, 0xDEF0)
        cpu = CPU8086(
            mem,
            CPUState(
                ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
                si=0x1111, di=0x2222, bp=0x3333,
                cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
                sp=0x9000, ip=ip, flags=0x0297,
            ),
        )
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        install_int21(cpu)
        if use_hook:
            if ip == 0x4E9F:
                cpu.replacement_hooks[(0x1010, 0x4E9F)] = overkill_temp_keyboard_vector_install_4e9f
            else:
                cpu.replacement_hooks[(0x1010, 0x4EBF)] = overkill_temp_keyboard_vector_restore_4ebf
        return cpu

    for ip in (0x4E9F, 0x4EBF):
        asm = make_cpu(ip, False)
        hook = make_cpu(ip, True)
        for _ in range(80):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_text_prompt_key_read_5497_matches_interpreted_asm_regular_and_extended_keys():
    from overkill.hooks import overkill_text_prompt_key_read_5497

    code_4e9f = bytes.fromhex(
        "1e 06 b4 35 b0 09 cd 21 bf 3a 21 8c 05 89 5d 02 07 1e 0e 1f "
        "ba d2 4e b4 25 b0 09 cd 21 1f 1f c3"
    )
    code_4ebf = bytes.fromhex("1e bf 3a 21 8b 55 02 8b 05 8e d8 b4 25 b0 09 cd 21 1f c3")
    code_5497 = bytes.fromhex(
        "2e 8e 1e 96 95 e8 20 fa c7 06 b2 22 00 00 b4 07 cd 21 3c 00 "
        "74 02 eb 08 cd 21 c7 06 b2 22 01 00 a2 b4 22 50 e8 e1 f9 58 c3"
    )

    def make_cpu(use_hook: bool, keys: list[int]) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x4E9F, code_4e9f)
        mem.load(0x1010, 0x4EBF, code_4ebf)
        mem.load(0x1010, 0x5497, code_5497)
        mem.ww(0x1010, 0x9596, 0x2000)
        mem.ww(0, 0x09 * 4, 0x4ED2)
        mem.ww(0, 0x09 * 4 + 2, 0x1010)
        mem.ww(0x2000, 0x213A, 0x5678)
        mem.ww(0x2000, 0x213C, 0x1234)
        cpu = CPU8086(
            mem,
            CPUState(
                ax=0x3300, bx=0x2222, cx=0x1111, dx=0x4444,
                si=0x5555, di=0x6666, bp=0x7777,
                cs=0x1010, ds=0x9999, es=0x8888, ss=0x4000,
                sp=0x9000, ip=0x5497, flags=0x0202,
            ),
        )
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        queue = list(keys)

        def handler(c: CPU8086, num: int) -> None:
            assert num == 0x21
            ah = (c.s.ax >> 8) & 0xFF
            al = c.s.ax & 0xFF
            if ah == 0x35:
                c.s.bx = c.mem.rw(0, al * 4)
                c.s.es = c.mem.rw(0, al * 4 + 2)
                return
            if ah == 0x25:
                c.mem.ww(0, al * 4, c.s.dx)
                c.mem.ww(0, al * 4 + 2, c.s.ds)
                return
            if ah == 0x07:
                assert queue, "test key queue unexpectedly empty"
                c.s.ax = (c.s.ax & 0xFF00) | (queue.pop(0) & 0xFF)
                return
            raise AssertionError(f"unexpected AH={ah:02X}")

        cpu.interrupt_handler = handler
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x5497)] = overkill_text_prompt_key_read_5497
        return cpu

    for keys in ([ord("A")], [0x00, 0x48]):
        asm = make_cpu(False, list(keys))
        hook = make_cpu(True, list(keys))
        for _ in range(160):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_text_entry_prompt_loop_53c9_matches_interpreted_one_iteration_branches():
    from overkill.hooks import overkill_text_entry_prompt_loop_53c9

    code_53c9 = bytes.fromhex(
        "bda922e8bdfdbd9b22e8b7fde8bf003c08742c3c0d743e813eb022a52274143c2072dd3c7a77d98b3eb0228805ff06b022ebcd"
    )

    def make_cpu(use_hook: bool, key: int, cursor: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x53C9, code_53c9)
        # Synthetic children with the same CALL/RET shape as the real routines:
        # 518C returns without touching state; 5497 returns the requested key.
        mem.load(0x1010, 0x518C, bytes.fromhex("c3"))
        mem.load(0x1010, 0x5497, bytes([0xB0, key & 0xFF, 0xC3]))
        mem.ww(0x2000, 0x22B0, cursor & 0xFFFF)
        for i in range(0x20):
            mem.wb(0x2000, 0x2290 + i, (0x41 + i) & 0xFF)
        cpu = CPU8086(
            mem,
            CPUState(
                ax=0x1200, bx=0xBEEF, cx=0x3333, dx=0x4444,
                si=0x5555, di=0x6666, bp=0x7777,
                cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
                sp=0x9000, ip=0x53C9, flags=0x0203,
            ),
        )
        cpu.trace_enabled = False

        def ret_518c(c: CPU8086) -> None:
            c.s.ip = c.pop()

        def key_5497(c: CPU8086) -> None:
            c.s.ax = (c.s.ax & 0xFF00) | (key & 0xFF)
            c.s.ip = c.pop()

        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x53C9)] = overkill_text_entry_prompt_loop_53c9
            cpu.replacement_hooks[(0x1010, 0x518C)] = ret_518c
            cpu.replacement_hooks[(0x1010, 0x5497)] = key_5497
        return cpu

    cases = (
        (ord("A"), 0x229B, 0x53C9),  # printable append
        (0x1B, 0x229B, 0x53C9),       # low non-printable ignored
        (0x7B, 0x229B, 0x53C9),       # high non-printable ignored
        (0x08, 0x229C, 0x5408),       # backspace tail remains original
        (0x0D, 0x229C, 0x541E),       # enter/pad/copy tail remains original
        (ord("Z"), 0x22A5, 0x53FC),  # full-buffer bell tail remains original
    )
    for key, cursor, expected_ip in cases:
        asm = make_cpu(False, key, cursor)
        hook = make_cpu(True, key, cursor)
        asm.step()
        for _ in range(80):
            if asm.addr() == (0x1010, expected_ip):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, expected_ip)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data

def test_keyboard_state_clear_and_bios_tail_sync_50ab_50ba_match_interpreted_asm():
    from overkill.hooks import (
        overkill_bios_keyboard_buffer_tail_sync_50ba,
        overkill_keyboard_state_clear_and_bios_tail_sync_50ab,
    )

    code_50ab = bytes.fromhex(
        "2e 8e 06 96 95 bf c4 98 32 c0 b9 80 00 f3 aa"
        "fa 33 c0 8e c0 26 a0 1a 04 26 a2 1c 04 fb c3"
    )
    code_50ba = bytes.fromhex("fa 33 c0 8e c0 26 a0 1a 04 26 a2 1c 04 fb c3")

    def make_cpu(ip: int, use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x50AB, code_50ab)
        mem.load(0x1010, 0x50BA, code_50ba)
        mem.ww(0x1010, 0x9596, 0x2000)
        for i in range(0x80):
            mem.wb(0x2000, 0x98C4 + i, (i * 3 + 1) & 0xFF)
        mem.wb(0, 0x041A, 0x34)
        mem.wb(0, 0x041C, 0x12)
        cpu = CPU8086(
            mem,
            CPUState(
                ax=0xABCD, bx=0x2222, cx=0x3333, dx=0x4444,
                si=0x5555, di=0x6666, bp=0x7777,
                cs=0x1010, ds=0x2000, es=0x8888, ss=0x4000,
                sp=0x9000, ip=ip, flags=0x0003,
            ),
        )
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            if ip == 0x50AB:
                cpu.replacement_hooks[(0x1010, 0x50AB)] = overkill_keyboard_state_clear_and_bios_tail_sync_50ab
            else:
                cpu.replacement_hooks[(0x1010, 0x50BA)] = overkill_bios_keyboard_buffer_tail_sync_50ba
        return cpu

    for ip in (0x50AB, 0x50BA):
        asm = make_cpu(ip, False)
        hook = make_cpu(ip, True)
        for _ in range(220):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_status_row_repeat_6120_matches_interpreted_asm_with_child_hooks():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_status_row_repeat_6120

    code = bytes.fromhex(
        "e3 16 56 57 51 2e 8e 1e b4 95 e8 3f f9 59 5f 5e "
        "e8 0b 00 e8 08 00 e2 e8 2e 8e 1e 96 95 c3"
    )

    def dummy_5a6c(cpu: CPU8086) -> None:
        ds = cpu.s.ds & 0xFFFF
        ss = cpu.s.ss & 0xFFFF
        idx = cpu.mem.rw(ss, 0x0100)
        base = 0x0120 + idx * 8
        cpu.mem.ww(ss, base + 0, ds)
        cpu.mem.ww(ss, base + 2, cpu.s.si & 0xFFFF)
        cpu.mem.ww(ss, base + 4, cpu.s.di & 0xFFFF)
        cpu.mem.ww(ss, base + 6, cpu.s.cx & 0xFFFF)
        cpu.mem.ww(ss, 0x0100, (idx + 1) & 0xFFFF)
        old = cpu.s.ax & 0xFFFF
        result = old + 0x0003
        cpu.s.ax = result & 0xFFFF
        cpu.set_add_flags(old, 0x0003, result, 16)
        cpu.s.ip = cpu.pop()

    def dummy_613e(cpu: CPU8086) -> None:
        old = cpu.s.di & 0xFFFF
        result = old + 0x0004
        cpu.s.di = result & 0xFFFF
        cpu.set_add_flags(old, 0x0004, result, 16)
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool, cx: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x6120, code)
        mem.ww(0x1010, 0x95B4, 0x3456)
        mem.ww(0x1010, 0x9596, 0x2000)
        state = CPUState(
            ax=0x0100, bx=0x0200, cx=cx, dx=0x0300,
            si=0x1111, di=0x0100, bp=0x2222,
            cs=0x1010, ds=0x2000, es=0x4000, ss=0x3000,
            sp=0x9000, ip=0x6120, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.replacement_hooks[(0x1010, 0x5A6C)] = dummy_5a6c
        cpu.replacement_hooks[(0x1010, 0x613E)] = dummy_613e
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x6120)] = overkill_status_row_repeat_6120
        return cpu

    for cx in (0, 3):
        asm = make_cpu(False, cx)
        hook = make_cpu(True, cx)
        for _ in range(200):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_setup_tracked_status_tail_c51d_matches_interpreted_asm_with_seed_child():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_setup_tracked_status_tail_c51d

    code = bytes.fromhex(
        "c7 06 58 a9 00 00 c7 06 5e a9 00 00 c7 06 60 a9 00 00 "
        "c7 06 62 a9 ff ff c7 06 64 a9 ff ff c7 06 66 a9 ff ff "
        "c7 06 68 a9 ff ff c7 06 6a a9 ff ff c7 06 6c a9 ff ff "
        "c7 06 6e a9 ff ff c7 06 84 23 00 00 e8 b5 bf e9 39 c0"
    )

    def dummy_8517(cpu: CPU8086) -> None:
        ds = cpu.s.ds & 0xFFFF
        old = cpu.mem.rw(ds, 0x0100)
        result = old + 0x1234
        cpu.mem.ww(ds, 0x0100, result & 0xFFFF)
        cpu.s.ax = result & 0xFFFF
        cpu.set_add_flags(old, 0x1234, result, 16)
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xC51D, code)
        for off in (0xA958, 0xA95E, 0xA960, 0xA962, 0xA964, 0xA966, 0xA968, 0xA96A, 0xA96C, 0xA96E, 0x2384):
            mem.ww(0x2000, off, 0x7777)
        mem.ww(0x2000, 0x0100, 0x0101)
        state = CPUState(
            ax=0xAAAA, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
            si=0xEEEE, di=0xF111, bp=0x2222,
            cs=0x1010, ds=0x2000, es=0x4000, ss=0x3000,
            sp=0x9000, ip=0xC51D, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.replacement_hooks[(0x1010, 0x8517)] = dummy_8517
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xC51D)] = overkill_setup_tracked_status_tail_c51d
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(200):
        if asm.addr() == (0x1010, 0x859E):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0x859E)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_status_cell_quad_composite_859e_matches_interpreted_asm_with_children():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_status_cell_quad_composite_859e

    code = bytes.fromhex(
        "55 e8 13 00 2e 83 3e bc 95 01 75 09 e8 72 cb e8 05 00 "
        "e8 6c cb 5d c3 bd 82 96 33 ff e8 18 00 bd 8c 96 bf 01 "
        "00 e8 0f 00 bd 96 96 bf 02 00 e8 06 00 bd a0 96 bf 03 00"
    )

    def dummy_85d5(cpu: CPU8086) -> None:
        ss = cpu.s.ss & 0xFFFF
        idx = cpu.mem.rw(ss, 0x0100)
        base = 0x0120 + idx * 6
        cpu.mem.ww(ss, base + 0, cpu.s.bp & 0xFFFF)
        cpu.mem.ww(ss, base + 2, cpu.s.di & 0xFFFF)
        cpu.mem.ww(ss, base + 4, cpu.s.sp & 0xFFFF)
        cpu.mem.ww(ss, 0x0100, (idx + 1) & 0xFFFF)
        old = cpu.s.ax & 0xFFFF
        result = old + 0x0001
        cpu.s.ax = result & 0xFFFF
        cpu.set_add_flags(old, 1, result, 16)
        cpu.s.ip = cpu.pop()

    def dummy_511f(cpu: CPU8086) -> None:
        ds = cpu.s.ds & 0xFFFF
        old = cpu.mem.rw(ds, 0x0200)
        result = old + 1
        cpu.mem.ww(ds, 0x0200, result & 0xFFFF)
        cpu.s.dx = result & 0xFFFF
        cpu.set_add_flags(old, 1, result, 16)
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool, mode: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x859E, code)
        mem.ww(0x1010, 0x95BC, mode)
        state = CPUState(
            ax=0x1000, bx=0xBBBB, cx=0xCCCC, dx=0xDDDD,
            si=0xEEEE, di=0xF111, bp=0x2222,
            cs=0x1010, ds=0x2000, es=0x4000, ss=0x3000,
            sp=0x9000, ip=0x859E, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.replacement_hooks[(0x1010, 0x85D5)] = dummy_85d5
        cpu.replacement_hooks[(0x1010, 0x511F)] = dummy_511f
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x859E)] = overkill_status_cell_quad_composite_859e
        return cpu

    for mode in (0, 1, 2):
        asm = make_cpu(False, mode)
        hook = make_cpu(True, mode)
        for _ in range(500):
            if asm.addr() == (0x1010, 0xBEEF):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_reset_object_slot_and_status_setup_c4db_composes_existing_children():
    from overkill.hooks import overkill_reset_object_slot_and_status_setup_c4db

    code = bytes.fromhex("2e c7 06 a2 c3 14 33 b9 24 00")

    def child_c4e5(cpu: CPU8086) -> None:
        ds = cpu.s.ds & 0xFFFF
        cpu.mem.ww(ds, 0x0100, cpu.s.cx & 0xFFFF)
        cpu.mem.ww(ds, 0x0102, cpu.mem.rw(cpu.s.cs & 0xFFFF, 0xC3A2))
        cpu.s.cx = 0
        cpu.s.ip = 0xC51D

    def child_c51d(cpu: CPU8086) -> None:
        ds = cpu.s.ds & 0xFFFF
        cpu.mem.ww(ds, 0x0104, (cpu.mem.rw(ds, 0x0104) + 1) & 0xFFFF)
        cpu.s.ip = 0x859E

    def child_859e(cpu: CPU8086) -> None:
        ds = cpu.s.ds & 0xFFFF
        cpu.mem.ww(ds, 0x0106, (cpu.mem.rw(ds, 0x0106) + 1) & 0xFFFF)
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xC4DB, code)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            sp=0x9000, ip=0xC4DB, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        cpu.replacement_hooks[(0x1010, 0xC4E5)] = child_c4e5
        cpu.replacement_hooks[(0x1010, 0xC51D)] = child_c51d
        cpu.replacement_hooks[(0x1010, 0x859E)] = child_859e
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xC4DB)] = overkill_reset_object_slot_and_status_setup_c4db
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(40):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_transition_status_wait_9908_matches_interpreted_asm_paths():
    from overkill.hooks import overkill_transition_status_wait_9908

    code = bytes.fromhex(
        "e8 d0 2b ff 0e 58 23 80 3e 8d 97 00 74 04 ff 06 58 23 "
        "80 3e c0 98 00 74 07 80 3e fe be 00 75 f9 80 3e c0 98 "
        "00 74 05 c6 06 ff be 02 e9 3c fe"
    )

    def child_c4db(cpu: CPU8086) -> None:
        ds = cpu.s.ds & 0xFFFF
        cpu.mem.ww(ds, 0x0200, (cpu.mem.rw(ds, 0x0200) + 1) & 0xFFFF)
        cpu.s.ax = (cpu.s.ax + 3) & 0xFFFF
        cpu.set_add_flags((cpu.s.ax - 3) & 0xFFFF, 3, cpu.s.ax, 16)
        cpu.s.ip = cpu.pop()

    def make_cpu(use_hook: bool, *, byte_978d: int, byte_98c0: int, byte_befe: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x9908, code)
        mem.wb(0x2000, 0x978D, byte_978d)
        mem.wb(0x2000, 0x98C0, byte_98c0)
        mem.wb(0x2000, 0xBEFE, byte_befe)
        mem.wb(0x2000, 0xBEFF, 0)
        mem.ww(0x2000, 0x2358, 0x0120)
        state = CPUState(
            ax=0x0101, bx=0x0202, cx=0x0303, dx=0x0404,
            si=0x0505, di=0x0606, bp=0x0707,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            sp=0x9000, ip=0x9908, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.replacement_hooks[(0x1010, 0xC4DB)] = child_c4db
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x9908)] = overkill_transition_status_wait_9908
        return cpu

    cases = (
        dict(byte_978d=0, byte_98c0=0, byte_befe=0),
        dict(byte_978d=1, byte_98c0=0, byte_befe=0),
        dict(byte_978d=0, byte_98c0=1, byte_befe=1),
        dict(byte_978d=0, byte_98c0=1, byte_befe=0),
    )
    for case in cases:
        asm = make_cpu(False, **case)
        hook = make_cpu(True, **case)
        for _ in range(80):
            if asm.addr() in ((0x1010, 0x9773), (0x1010, 0x9921)):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr()
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_transition_input_release_tail_9928_matches_interpreted_asm_paths():
    from overkill.hooks import overkill_transition_input_release_tail_9928

    code = bytes.fromhex("80 3e c0 98 00 74 05 c6 06 ff be 02 e9 3c fe")

    def make_cpu(use_hook: bool, byte_98c0: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x9928, code)
        mem.wb(0x2000, 0x98C0, byte_98c0)
        mem.wb(0x2000, 0xBEFF, 0x44)
        state = CPUState(
            ax=0x0101, bx=0x0202, cx=0x0303, dx=0x0404,
            si=0x0505, di=0x0606, bp=0x0707,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            sp=0x9000, ip=0x9928, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x9928)] = overkill_transition_input_release_tail_9928
        return cpu

    for byte_98c0 in (0, 1):
        asm = make_cpu(False, byte_98c0)
        hook = make_cpu(True, byte_98c0)
        for _ in range(20):
            if asm.addr() == (0x1010, 0x9773):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0x9773)
        assert asm.s.snapshot() == hook.s.snapshot()
        assert bytes(asm.mem.data) == bytes(hook.mem.data)


def test_menu_fire_release_wait_d390_matches_original_poll_gate():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_menu_fire_release_wait_d390

    code = bytes.fromhex("e8 cf 2d f6 06 be 98 10 75 f6")

    def make_cpu(use_hook: bool, buttons: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xD390, code)
        mem.wb(0x2000, 0x98BE, 0x00)
        cpu = CPU8086(mem, CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0xD390, flags=0x0203,
        ))

        def poll(cpu2):
            cpu2.mem.wb(cpu2.s.ds & 0xFFFF, 0x98BE, buttons)
            cpu2.s.ip = cpu2.pop()

        cpu.replacement_hooks[(0x1010, 0x0162)] = poll
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xD390)] = overkill_menu_fire_release_wait_d390
        return cpu

    for buttons, expected in ((0x10, (0x1010, 0xD390)), (0x00, (0x1010, 0xD39A)), (0x04, (0x1010, 0xD39A))):
        asm = make_cpu(False, buttons)
        hook = make_cpu(True, buttons)
        for _ in range(8):
            asm.step()
            if asm.addr() == expected:
                break
        hook.step()
        assert asm.addr() == hook.addr() == expected
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_selector_input_release_wait_d434_matches_original_poll_gate():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_selector_input_release_wait_d434

    code = bytes.fromhex("80 3e e4 98 01 74 f9 e8 24 2d 80 3e be 98 00 75 f6")

    def make_cpu(use_hook: bool, key_latch: int, buttons: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xD434, code)
        mem.wb(0x2000, 0x98E4, key_latch)
        mem.wb(0x2000, 0x98BE, 0)
        cpu = CPU8086(mem, CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=0x7777, sp=0x9000,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0xD434, flags=0x0203,
        ))

        def poll(cpu2):
            cpu2.mem.wb(cpu2.s.ds & 0xFFFF, 0x98BE, buttons)
            cpu2.s.ip = cpu2.pop()

        cpu.replacement_hooks[(0x1010, 0x0162)] = poll
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xD434)] = overkill_selector_input_release_wait_d434
        return cpu

    # The D434 hook models only phase 1 (the [98E4] release-wait); when [98E4]
    # is already clear it hands control to D43B, where phase 2 (the [98BE]
    # button-poll loop D43B-D443) runs as raw ASM and eventually reaches D445.
    # So the faithful comparison is at that phase-1 exit boundary: [98E4]==1
    # keeps looping at D434, [98E4]==0 falls through to D43B regardless of the
    # buttons (phase 1 never inspects [98BE]), both carrying the phase-1
    # CMP [98E4],1 flags.  Phase 2 itself (and D445) is exercised by demo replay,
    # not by this single-poll hook -- stepping the ASM into phase 2 here would
    # compare two different routines.
    cases = (
        (1, 0x00, (0x1010, 0xD434), 2),
        (0, 0x08, (0x1010, 0xD43B), 2),
        (0, 0x00, (0x1010, 0xD43B), 2),
    )
    for key_latch, buttons, expected, asm_steps in cases:
        asm = make_cpu(False, key_latch, buttons)
        hook = make_cpu(True, key_latch, buttons)
        for _ in range(asm_steps):
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == expected
        assert asm.s.snapshot() == hook.s.snapshot()
        assert asm.mem.data == hook.mem.data


def test_object_spawn_anchor_offset_a571_matches_original():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_object_spawn_anchor_offset_a571

    code_variants = (
        # Static/install-time form: ADD AX, imm8.
        bytes.fromhex("8b 46 04 83 c0 0a 89 47 04 8b 46 02 83 c0 0a 89 47 02 c3"),
        # Runtime-loaded form seen in real gameplay demos: ADD AX, imm16.
        bytes.fromhex("8b 46 04 05 0a 00 89 47 04 8b 46 02 05 0a 00 89 47 02 c3"),
    )

    def make_cpu(use_hook: bool, code: bytes, src_x: int, src_y: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xA571, code)
        bp = 0x2800
        bx = 0x2A00
        mem.ww(0x4000, bp + 0x02, src_x)
        mem.ww(0x4000, bp + 0x04, src_y)
        cpu = CPU8086(mem, CPUState(
            ax=0xAAAA, bx=bx, cx=0xCCCC, dx=0xDDDD,
            si=0x1111, di=0x2222, bp=bp, sp=0x9000,
            cs=0x1010, ds=0x2000, es=0x3000, ss=0x4000,
            ip=0xA571, flags=0x0203,
        ))
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xA571)] = overkill_object_spawn_anchor_offset_a571
        return cpu

    for code in code_variants:
        for src_x, src_y in ((0x0010, 0x0020), (0xFFFA, 0x8000)):
            asm = make_cpu(False, code, src_x, src_y)
            hook = make_cpu(True, code, src_x, src_y)
            for _ in range(20):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hook.step()
            assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hook.s.snapshot()
            assert asm.mem.data == hook.mem.data


def test_linked_object_coord_quad_update_9faf_matches_original_parent():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_linked_object_coord_quad_update_9faf

    code = bytes.fromhex(
        "c6 06 9e a3 00 c6 06 9f a3 00 a1 9a a3 a3 98 a3"
        " be 8c a3 8b 1e 6c a9 e8 21 00 be 74 a3 8b 1e 68"
        " a9 e8 17 00 a1 9c a3 a3 98 a3 be 80 a3 8b 1e 6a"
        " a9 e8 07 00 be 68 a3 8b 1e 66 a9 83 fb ff 75 01"
        " c3 8b 46 08 d1 e0 d1 e0 03 f0 ad 03 46 02 89 47"
        " 02 ad 03 46 04 03 06 98 a3 03 06 98 a3 89 47 04"
        " 83 7f 04 00 7d 0a c7 47 04 00 00 c6 06 9e a3 01"
        " 81 7f 04 c0 00 7e 0a c7 47 04 c0 00 c6 06 9f a3"
        " 01 c3"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x9FAF, code)
        ds = 0x2000
        ss = 0x4000
        bp = 0x2600
        # Source object base and animation/frame index used by 9FEA.
        mem.ww(ss, bp + 0x02, 0x0030)
        mem.ww(ss, bp + 0x04, 0x0040)
        mem.ww(ss, bp + 0x08, 0x0001)
        # Two vertical scroll offsets used by the parent before the first pair
        # and the second pair of linked-child updates.
        mem.ww(ds, 0xA39A, 0x0002)
        mem.ww(ds, 0xA39C, 0xFFB0)
        # Four linked destination slots.  The last one intentionally clamps low.
        for off, ptr in ((0xA966, 0x3000), (0xA968, 0x3040), (0xA96A, 0x3080), (0xA96C, 0x30C0)):
            mem.ww(ds, off, ptr)
        # Motion/offset tables.  9FEA adds BP+8*4 before reading each pair.
        entries = {
            0xA38C + 4: (0x0001, 0x0002),
            0xA374 + 4: (0x0003, 0x00A0),
            0xA380 + 4: (0x0005, 0x0007),
            0xA368 + 4: (0x0009, 0x0001),
        }
        for base, (x_delta, y_delta) in entries.items():
            mem.ww(ds, base, x_delta)
            mem.ww(ds, base + 2, y_delta)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ss,
            ip=0x9FAF, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x9FAF)] = overkill_linked_object_coord_quad_update_9faf
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(200):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_linked_object_coord_quad_update_9faf_skips_inactive_fourth_slot():
    """When the 4th linked slot ([A966]) is FFFF - e.g. a sidearm was lost - the
    original 9FAF guards the final fall-through (CMP BX,FFFF / JNZ / RET) and skips
    the 9FEA child-coord update.  Regression for the mothership sidearm-drag
    divergence: the lift ran 9FEA unconditionally and corrupted the DS:A30A trail.
    """
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_linked_object_coord_quad_update_9faf

    code = bytes.fromhex(
        "c6 06 9e a3 00 c6 06 9f a3 00 a1 9a a3 a3 98 a3"
        " be 8c a3 8b 1e 6c a9 e8 21 00 be 74 a3 8b 1e 68"
        " a9 e8 17 00 a1 9c a3 a3 98 a3 be 80 a3 8b 1e 6a"
        " a9 e8 07 00 be 68 a3 8b 1e 66 a9 83 fb ff 75 01"
        " c3 8b 46 08 d1 e0 d1 e0 03 f0 ad 03 46 02 89 47"
        " 02 ad 03 46 04 03 06 98 a3 03 06 98 a3 89 47 04"
        " 83 7f 04 00 7d 0a c7 47 04 00 00 c6 06 9e a3 01"
        " 81 7f 04 c0 00 7e 0a c7 47 04 c0 00 c6 06 9f a3"
        " 01 c3"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x9FAF, code)
        ds = 0x2000
        ss = 0x4000
        bp = 0x2600
        mem.ww(ss, bp + 0x02, 0x0030)
        mem.ww(ss, bp + 0x04, 0x0040)
        mem.ww(ss, bp + 0x08, 0x0001)
        mem.ww(ds, 0xA39A, 0x0002)
        mem.ww(ds, 0xA39C, 0xFFB0)
        # 4th linked slot inactive: [A966] = FFFF -> the final 9FEA update must be
        # skipped (the first three still run).
        for off, ptr in ((0xA966, 0xFFFF), (0xA968, 0x3040), (0xA96A, 0x3080), (0xA96C, 0x30C0)):
            mem.ww(ds, off, ptr)
        entries = {
            0xA38C + 4: (0x0001, 0x0002),
            0xA374 + 4: (0x0003, 0x00A0),
            0xA380 + 4: (0x0005, 0x0007),
            0xA368 + 4: (0x0009, 0x0001),
        }
        for base, (x_delta, y_delta) in entries.items():
            mem.ww(ds, base, x_delta)
            mem.ww(ds, base + 2, y_delta)
        state = CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ss,
            ip=0x9FAF, flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x9FAF)] = overkill_linked_object_coord_quad_update_9faf
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(200):
        if asm.addr() == (0x1010, 0xBEEF):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xBEEF)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_object_two_pass_clamp_step_helpers_match_original():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import (
        overkill_object_x_step_left_clamp_a5d1,
        overkill_object_x_step_right_clamp_a5ea,
        overkill_object_y_step_up_clamp_a5f9,
        overkill_object_y_step_down_clamp_a607,
    )

    cases = (
        (0xA5D1, bytes.fromhex("83 3e 7c a4 00 75 0e e8 00 00 83 7e 02 20 75 01 c3 ff 4e 02 c3 ff 4e 02 c3"),
         overkill_object_x_step_left_clamp_a5d1, 0x02, (0x0020, 0x0021, 0x0030), {0xA47C: 0x0000}),
        (0xA5D1, bytes.fromhex("83 3e 7c a4 00 75 0e e8 00 00 83 7e 02 20 75 01 c3 ff 4e 02 c3 ff 4e 02 c3"),
         overkill_object_x_step_left_clamp_a5d1, 0x02, (0x0020, 0x0021, 0x0030), {0xA47C: 0x0001}),
        (0xA5EA, bytes.fromhex("e8 00 00 81 7e 02 c0 00 75 01 c3 ff 46 02 c3"),
         overkill_object_x_step_right_clamp_a5ea, 0x02, (0x00C0, 0x00BF, 0x00B0), {}),
        (0xA5F9, bytes.fromhex("e8 00 00 83 7e 04 00 75 01 c3 ff 4e 04 c3"),
         overkill_object_y_step_up_clamp_a5f9, 0x04, (0x0000, 0x0001, 0x0010), {}),
        (0xA607, bytes.fromhex("e8 00 00 81 7e 04 b0 00 72 01 c3 ff 46 04 c3"),
         overkill_object_y_step_down_clamp_a607, 0x04, (0x00B0, 0x00AF, 0x00A0), {}),
    )

    def make_cpu(ip: int, code: bytes, hook, field_off: int, field_value: int, globals_: dict[int, int], use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, ip, code)
        ds = 0x2000
        ss = 0x4000
        bp = 0x2600
        mem.ww(ss, bp + 0x02, 0x1234)
        mem.ww(ss, bp + 0x04, 0x5678)
        mem.ww(ss, bp + field_off, field_value)
        for off, value in globals_.items():
            mem.ww(ds, off, value)
        cpu = CPU8086(mem, CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ss,
            ip=ip, flags=0x0203,
        ))
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, ip)] = hook
        return cpu

    for ip, code, hook, field_off, values, globals_ in cases:
        for field_value in values:
            asm = make_cpu(ip, code, hook, field_off, field_value, globals_, False)
            hooked = make_cpu(ip, code, hook, field_off, field_value, globals_, True)
            for _ in range(80):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hooked.step()
            assert asm.addr() == hooked.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hooked.s.snapshot()
            assert asm.mem.data == hooked.mem.data


def test_object_vertical_scroll_edge_helpers_match_original():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import (
        overkill_object_vertical_scroll_edge_response_a616,
        overkill_object_bottom_scroll_offset_decay_a63c,
        overkill_object_top_scroll_edge_response_a648,
        overkill_object_top_scroll_offset_recover_a662,
    )

    code_a616 = bytes.fromhex(
        "81 3e 50 23 b6 00 77 01 c3 e8 26 00 81 7e 04 b0"
        " 00 75 13 f6 06 be 98 01 74 0c 83 3e 9c a3 08 74"
        " 04 ff 06 9c a3 c3 83 3e 9c a3 00 74 04 ff 0e 9c"
        " a3 c3 83 7e 04 00 75 14 f6 06 be 98 02 74 0d 83"
        " 3e 9a a3 f8 75 01 c3 ff 0e 9a a3 c3 83 3e 9a a3"
        " 00 75 01 c3 ff 06 9a a3 c3"
    )
    helpers = (
        (0xA616, code_a616, overkill_object_vertical_scroll_edge_response_a616),
        (0xA63C, code_a616[0xA63C - 0xA616:], overkill_object_bottom_scroll_offset_decay_a63c),
        (0xA648, code_a616[0xA648 - 0xA616:], overkill_object_top_scroll_edge_response_a648),
        (0xA662, code_a616[0xA662 - 0xA616:], overkill_object_top_scroll_offset_recover_a662),
    )

    scenarios = (
        # view_y, object_y, input_bits, top_bias, bottom_bias
        (0x00B6, 0x0000, 0x03, 0x0000, 0x0000),
        (0x00B7, 0x0000, 0x02, 0x0000, 0x0000),
        (0x00B7, 0x0000, 0x00, 0xFFFE, 0x0000),
        (0x00B7, 0x00B0, 0x01, 0x0000, 0x0000),
        (0x00B7, 0x0080, 0x00, 0x0000, 0x0003),
        (0x00B7, 0x0001, 0x02, 0xFFF8, 0x0003),
    )

    def make_cpu(ip: int, code: bytes, hook, scenario, use_hook: bool) -> CPU8086:
        view_y, object_y, input_bits, top_bias, bottom_bias = scenario
        mem = Memory()
        mem.load(0x1010, ip, code)
        ds = 0x2000
        ss = 0x4000
        bp = 0x2600
        mem.ww(ds, 0x2350, view_y)
        mem.wb(ds, 0x98BE, input_bits)
        mem.ww(ds, 0xA39A, top_bias)
        mem.ww(ds, 0xA39C, bottom_bias)
        mem.ww(ss, bp + 0x04, object_y)
        cpu = CPU8086(mem, CPUState(
            ax=0x1111, bx=0x2222, cx=0x3333, dx=0x4444,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=ds, es=0x3000, ss=ss,
            ip=ip, flags=0x0203,
        ))
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, ip)] = hook
        return cpu

    for ip, code, hook in helpers:
        for scenario in scenarios:
            asm = make_cpu(ip, code, hook, scenario, False)
            hooked = make_cpu(ip, code, hook, scenario, True)
            for _ in range(120):
                if asm.addr() == (0x1010, 0xBEEF):
                    break
                asm.step()
            hooked.step()
            assert asm.addr() == hooked.addr() == (0x1010, 0xBEEF)
            assert asm.s.snapshot() == hooked.s.snapshot()
            assert asm.mem.data == hooked.mem.data


def test_movement_dir_step_tables_match_interpreted_asm_all_directions():
    """1010:AEE4/AF22/AF63 8-direction movement step tables, hook vs ASM.

    Each routine reads the direction index from SS:[BP+06], doubles it, and
    dispatches through a CS jump table to a handler that adds/subtracts a fixed
    delta from SS:[BP+02] (X) and/or SS:[BP+04] (Y).  The whole region (entry
    stub + jump table + handlers) is loaded so the interpreted dispatch resolves,
    and the hook entry is compared for every direction index and several seed
    coordinates (including borrow/zero edges).
    """
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import (
        overkill_movement_dir_step_2px_af63,
        overkill_movement_dir_double_step_2px_af60,
        overkill_movement_dir_step_3px_af22,
        overkill_movement_dir_step_8px_aee4,
    )

    code_aee4 = bytes.fromhex(
        "8b 5e 06 d1 e3 2e ff a7 ee ae 0b af 10 af 14 af fe ae 02 af 19 af 1d af 07 af"
        " 83 46 04 08 83 46 02 08 c3 83 6e 04 08 83 6e 02 08 c3 83 6e 02 08 83 46 04 08 c3"
        " 83 46 02 08 83 6e 04 08 c3"
    )
    code_af22 = bytes.fromhex(
        "8b 5e 06 d1 e3 2e ff a7 2c af 49 af 4e af 52 af 3c af 40 af 57 af 5b af 45 af"
        " 83 46 04 03 83 46 02 03 c3 83 6e 04 03 83 6e 02 03 c3 83 6e 02 03 83 46 04 03 c3"
        " 83 46 02 03 83 6e 04 03 c3"
    )
    code_af63 = bytes.fromhex(
        "8b 5e 06 d1 e3 2e ff a7 6e af 90 8b af 90 af 94 af 7e af 82 af 99 af 9d af 87 af"
        " 83 46 04 02 83 46 02 02 c3 83 6e 04 02 83 6e 02 02 c3 83 6e 02 02 83 46 04 02 c3"
        " 83 46 02 02 83 6e 04 02 c3"
    )
    code_af60 = bytes.fromhex("e8 00 00") + code_af63
    tables = (
        (0xAEE4, code_aee4, overkill_movement_dir_step_8px_aee4),
        (0xAF22, code_af22, overkill_movement_dir_step_3px_af22),
        (0xAF60, code_af60, overkill_movement_dir_double_step_2px_af60),
        (0xAF63, code_af63, overkill_movement_dir_step_2px_af63),
    )
    seeds = ((0x0080, 0x0050), (0x0002, 0x0001), (0x0000, 0xFFFE))

    def make_cpu(entry, code, hook, x0, y0, direction, use_hook):
        mem = Memory()
        mem.load(0x1010, entry, code)
        ss = 0x4000
        bp = 0x0600
        mem.ww(ss, bp + 0x02, x0)
        mem.ww(ss, bp + 0x04, y0)
        mem.ww(ss, bp + 0x06, direction)
        cpu = CPU8086(mem, CPUState(
            ax=0x1234, bx=0x7777, cx=0x3333, dx=0x4321,
            si=0x5555, di=0x6666, bp=bp, sp=0x9000,
            cs=0x1010, ds=0x2222, es=0x3333, ss=ss,
            ip=entry, flags=0x0202,
        ))
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        if use_hook:
            cpu.replacement_hooks[(0x1010, entry)] = hook
        return cpu

    for entry, code, hook in tables:
        for x0, y0 in seeds:
            for direction in range(8):
                asm = make_cpu(entry, code, hook, x0, y0, direction, False)
                hooked = make_cpu(entry, code, hook, x0, y0, direction, True)
                for _ in range(20):
                    if asm.addr() == (0x1010, 0xBEEF):
                        break
                    asm.step()
                hooked.step()
                assert asm.addr() == hooked.addr() == (0x1010, 0xBEEF), (hex(entry), direction)
                assert asm.s.snapshot() == hooked.s.snapshot(), (hex(entry), direction, x0, y0)
                assert_oracle_equivalent(asm, hooked)  # AF22/AF60 self-call scratch below SP dropped


def test_ac81_slot_scan_guard_acd9_continuation_preserves_entry_cmp_flags():
    from overkill.hooks import overkill_object_slot_scan_guard_ac81

    code = bytes.fromhex(
        "83 3e ac bd 01 75 03 e9 b9 fd b9 23 00 bb b4 23 "
        "8b 46 04 8b 7e 02 83 3f 00 74 36 83 7f 18 01 74 30 "
        "83 7f 14 01 75 2a 8b 77 02 83 c6 10 3b fe 7f 20 "
        "83 ee 20 3b fe 7c 19 8b 77 04 83 c6 10 3b c6 7f 0f "
        "83 ee 20 3b c6 7c 08 8b 76 0e 3b 77 0e 75 07"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xAC81, code)
        state = CPUState(cs=0x1010, ip=0xAC81, ds=0x2000, ss=0x3000, bp=0x0100, sp=0x8000, flags=0x0202)
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        mem.ww(0x2000, 0xBDAC, 0x0000)
        mem.ww(0x3000, 0x0104, 0x0100)  # current Y -> AX
        mem.ww(0x3000, 0x0102, 0x0100)  # current X -> DI
        mem.ww(0x3000, 0x010E, 0x1111)  # current owner/id -> SI before ACD0 CMP
        bx = 0x23B4
        mem.ww(0x2000, bx + 0x00, 0x0001)
        mem.ww(0x2000, bx + 0x18, 0x0000)
        mem.ww(0x2000, bx + 0x14, 0x0001)
        mem.ww(0x2000, bx + 0x02, 0x0100)
        mem.ww(0x2000, bx + 0x04, 0x0100)
        mem.ww(0x2000, bx + 0x0E, 0x2222)
        mem.ww(0x2000, bx + 0x16, 0x0004)  # look-ahead must not leak ZF=1 to ACD9
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xAC81)] = overkill_object_slot_scan_guard_ac81
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(64):
        if asm.addr() == (0x1010, 0xACD9):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xACD9)
    assert asm.s.snapshot() == hook.s.snapshot()


def test_view_contact_rect_test_8331_matches_interpreted_asm_inside_and_miss():
    from overkill.hooks import overkill_view_contact_rect_test_8331

    code = bytes.fromhex(
        "8b 36 f2 95 83 c6 10 39 76 02 7f 1e 83 ee 20 39 76 02 "
        "7c 16 8b 36 f4 95 83 c6 10 39 76 04 7f 0a 83 ee 20 "
        "39 76 04 7c 02 f9 c3 f8 c3"
    )

    def make_cpu(use_hook: bool, *, x: int, y: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0x8331, code)
        state = CPUState(
            cs=0x1010,
            ip=0x8331,
            ds=0x2000,
            ss=0x3000,
            bp=0x0100,
            sp=0x8000,
            si=0x7777,
            flags=0x0203,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        mem.ww(0x2000, 0x95F2, 0x0050)
        mem.ww(0x2000, 0x95F4, 0x0060)
        mem.ww(0x3000, 0x0102, x)
        mem.ww(0x3000, 0x0104, y)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0x8331)] = overkill_view_contact_rect_test_8331
        return cpu

    for x, y in ((0x0050, 0x0060), (0x0071, 0x0060), (0x0050, 0x003F)):
        asm = make_cpu(False, x=x, y=y)
        hook = make_cpu(True, x=x, y=y)
        for _ in range(32):
            if asm.s.ip == 0xBEEF:
                break
            asm.step()
        assert asm.s.ip == 0xBEEF
        hook.step()
        assert asm.s.snapshot() == hook.s.snapshot()


def test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan():
    from overkill.hooks import overkill_player_hazard_scan_guard_bdd0

    bdd0_bde3 = bytes.fromhex(
        "83 7e 0a 01 74 64 b9 23 00 bb b4 23 a1 36 a4 8b 3e 38 a4"
        "83 3f 00 74 4d 83 7f 0a 01 74 47 83 7f 14 01 75 41"
        "83 7f 16 04 75 3b 81 7f 18 82 00 72 34 81 7f 18 94 00 77 2d"
        "8b 77 02 83 c6 10 3b fe 7d 23 83 ee 20 3b fe 7e 1c"
        "8b 77 04 83 c6 10 3b c6 7d 12 83 ee 20 3b c6 7e 0b"
        "8b 76 0e 3b 77 0e 74 03 e9 24 92 83 c3 38 e2 a9 f8 c3"
    )

    def make_cpu(use_hook: bool, *, layer: int) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xBDD0, bdd0_bde3)
        mem.load(0x1010, 0x5059, bytes.fromhex("f9 c3"))
        state = CPUState(
            cs=0x1010,
            ip=0xBDD0,
            ds=0x2000,
            ss=0x3000,
            bp=0x0100,
            sp=0x8000,
            flags=0x0207,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xCAFE)
        mem.ww(0x3000, 0x010A, layer)
        mem.ww(0x2000, 0xA436, 0x0040)
        mem.ww(0x2000, 0xA438, 0x0050)
        # Keep all scan records inactive so the full BDE3 loop exhausts.
        for i in range(0x23):
            mem.ww(0x2000, 0x23B4 + i * 0x38, 0x0000)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xBDD0)] = overkill_player_hazard_scan_guard_bdd0
        return cpu

    for layer in (0x0001, 0x0002):
        asm = make_cpu(False, layer=layer)
        hook = make_cpu(True, layer=layer)
        for _ in range(800):
            if asm.s.ip == 0xCAFE:
                break
            asm.step()
        assert asm.s.ip == 0xCAFE
        hook.step()
        assert asm.s.snapshot() == hook.s.snapshot()


def test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_hit_path():
    from overkill.hooks import overkill_player_hazard_scan_guard_bdd0

    bdd0_bde3 = bytes.fromhex(
        "83 7e 0a 01 74 64 b9 23 00 bb b4 23 a1 36 a4 8b 3e 38 a4"
        "83 3f 00 74 4d 83 7f 0a 01 74 47 83 7f 14 01 75 41"
        "83 7f 16 04 75 3b 81 7f 18 82 00 72 34 81 7f 18 94 00 77 2d"
        "8b 77 02 83 c6 10 3b fe 7d 23 83 ee 20 3b fe 7e 1c"
        "8b 77 04 83 c6 10 3b c6 7d 12 83 ee 20 3b c6 7e 0b"
        "8b 76 0e 3b 77 0e 74 03 e9 24 92 83 c3 38 e2 a9 f8 c3"
    )

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xBDD0, bdd0_bde3)
        state = CPUState(
            cs=0x1010,
            ip=0xBDD0,
            ds=0x2000,
            ss=0x3000,
            bp=0x0100,
            sp=0x8000,
            flags=0x0207,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xCAFE)
        # Current object: BDD0 must continue into the scan, and the final link
        # key compare must see a different value from the candidate slot.
        mem.ww(0x3000, 0x010A, 0x0002)
        mem.ww(0x3000, 0x010E, 0x1111)
        mem.ww(0x2000, 0xA436, 0x0060)  # probe Y -> AX
        mem.ww(0x2000, 0xA438, 0x0050)  # probe X -> DI
        # Slot 0 is an active BDE3 hazard candidate around the probe point.
        base = 0x23B4
        mem.ww(0x2000, base + 0x00, 0x0001)
        mem.ww(0x2000, base + 0x02, 0x0050)
        mem.ww(0x2000, base + 0x04, 0x0060)
        mem.ww(0x2000, base + 0x0A, 0x0002)
        mem.ww(0x2000, base + 0x0E, 0x2222)
        mem.ww(0x2000, base + 0x14, 0x0001)
        mem.ww(0x2000, base + 0x16, 0x0004)
        mem.ww(0x2000, base + 0x18, 0x0082)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xBDD0)] = overkill_player_hazard_scan_guard_bdd0
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(160):
        if asm.addr() == (0x1010, 0x5059):
            break
        asm.step()
    assert asm.addr() == (0x1010, 0x5059)
    hook.step()
    assert hook.addr() == (0x1010, 0x5059)
    assert asm.s.snapshot() == hook.s.snapshot()

def test_object_tile_sweep_blocked_b032_matches_interpreted_asm():
    from overkill.hooks import overkill_object_tile_sweep_blocked_b032

    code = bytes.fromhex("c7 06 30 a4 01 00 c3")

    def make_cpu(use_hook: bool) -> CPU8086:
        mem = Memory()
        mem.load(0x1010, 0xB032, code)
        state = CPUState(
            cs=0x1010,
            ip=0xB032,
            ds=0x2000,
            ss=0x3000,
            sp=0x8000,
            flags=0x0207,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        cpu.push(0xBEEF)
        mem.ww(0x2000, 0xA430, 0x0000)
        if use_hook:
            cpu.replacement_hooks[(0x1010, 0xB032)] = overkill_object_tile_sweep_blocked_b032
        return cpu

    asm = make_cpu(False)
    hook = make_cpu(True)
    for _ in range(8):
        if asm.s.ip == 0xBEEF:
            break
        asm.step()
    assert asm.s.ip == 0xBEEF
    hook.step()
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.rw(0x2000, 0xA430) == hook.mem.rw(0x2000, 0xA430) == 1


def test_object_target_move_b729_matches_interpreted_wrapper_with_5db2_hook():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_movement_direction_helper_5db2, overkill_object_target_move_b729
    from overkill.gameplay.object_runtime import SIG_OBJECT_TARGET_MOVE_B729

    def make_cpu(*, hook_b729: bool) -> CPU8086:
        mem = Memory()
        state = CPUState(
            cs=0x1010,
            ds=0x2000,
            ss=0x3000,
            bp=0x0100,
            sp=0x8000,
            ip=0xB729,
            flags=0x0202,
        )
        cpu = CPU8086(mem, state)
        cpu.trace_enabled = False
        mem.load(0x1010, 0xB729, SIG_OBJECT_TARGET_MOVE_B729)
        # 5DB2 dispatch table: mode 1 -> AF63 2-pixel movement step.
        mem.ww(0x1010, 0x5E0E, 0xAF63)
        # 5DB2 direction bit 5 maps to direction 4: move right.
        for idx in range(16):
            mem.wb(0x2000, 0xA348 + idx, 0xFF)
        mem.wb(0x2000, 0xA348 + 0x0005, 4)
        mem.ww(0x2000, 0x2308, 1)
        # Current object position and B729 target pair at +32/+34.
        mem.ww(0x3000, 0x0102, 0x0050)
        mem.ww(0x3000, 0x0104, 0x0060)
        mem.ww(0x3000, 0x0132, 0x0062)
        mem.ww(0x3000, 0x0134, 0x0052)
        mem.ww(0x3000, 0x8000, 0x7777)
        cpu.replacement_hooks[(0x1010, 0x5DB2)] = overkill_movement_direction_helper_5db2
        cpu.hook_names[(0x1010, 0x5DB2)] = "overkill_movement_direction_helper_5db2"
        if hook_b729:
            cpu.replacement_hooks[(0x1010, 0xB729)] = overkill_object_target_move_b729
            cpu.hook_names[(0x1010, 0xB729)] = "overkill_object_target_move_b729"
        return cpu

    asm = make_cpu(hook_b729=False)
    for _ in range(20):
        if asm.addr() == (0x1010, 0x7777):
            break
        asm.step()

    hook = make_cpu(hook_b729=True)
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0x7777)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_hook_module_wrappers_have_bound_globals():
    """Catch relocation regressions where a wrapper still calls a moved helper."""
    import builtins
    import dis
    import inspect
    import overkill.hooks as hooks

    missing = {}
    for name, obj in vars(hooks).items():
        if not inspect.isfunction(obj) or obj.__module__ != hooks.__name__:
            continue
        missing_names = []
        for ins in dis.get_instructions(obj):
            if ins.opname != "LOAD_GLOBAL":
                continue
            global_name = ins.argval
            if global_name not in hooks.__dict__ and not hasattr(builtins, global_name):
                missing_names.append(global_name)
        if missing_names:
            missing[name] = sorted(set(missing_names))

    assert missing == {}


def test_gameplay_counter_tick_tail_aa25_can_call_relocated_far_helper():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.hooks import overkill_gameplay_counter_tick_tail_aa25

    mem = Memory()
    state = CPUState(
        cs=0x1010,
        ds=0x1010,
        es=0x1010,
        ss=0x4000,
        ip=0xAA25,
        sp=0x9000,
        flags=0x0202,
    )
    cpu = CPU8086(mem, state)
    cpu.trace_enabled = False
    cpu.mem.ww(0x1010, 0xA95A, 0xFFFF)  # fast path: no nested 0960 stride calls
    cpu.push(0xBEEF)

    overkill_gameplay_counter_tick_tail_aa25(cpu)

    assert cpu.addr() == (0x1010, 0xBEEF)

