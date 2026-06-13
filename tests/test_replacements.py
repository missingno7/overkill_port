import pytest

from overkill_port.cpu import CPU8086, CPUState
from overkill_port.memory import Memory
from overkill_port.replacements import overkill_file_checksum_loop


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
    overkill_file_checksum_loop(cpu_b)

    assert cpu_b.s.ax == cpu_a.s.ax
    assert cpu_b.s.dx == cpu_a.s.dx
    assert cpu_b.s.cx == cpu_a.s.cx == 0
    assert cpu_b.s.si == cpu_a.s.si == len(payload)
    assert cpu_b.s.flags == cpu_a.s.flags
    assert cpu_b.s.ip == 0xC91F


def test_expand_bits_45cb_hook_matches_interpreted_asm():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_expand_bits_45cb

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_pack_four_pixels_45f6

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


def test_packed_read_byte_0624_hook_matches_interpreted_asm_no_refill():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_packed_read_byte

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
            cpu.replacement_hooks[(0x1010, 0x0624)] = overkill_packed_read_byte
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
    from overkill_port.cpu import CPU8086, CPUState, CF
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_packed_read_byte

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
            cpu.replacement_hooks[(0x1010, 0x0624)] = overkill_packed_read_byte
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_packed_read_word

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
            cpu.replacement_hooks[(0x1010, 0x0615)] = overkill_packed_read_word
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_vertical_rle_decoder_03a8

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_word_pair_rle_decoder_0324

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
    assert asm.mem.block(0x4000, 0x8FC0, 0x40) == hook.mem.block(0x4000, 0x8FC0, 0x40)
    assert asm.mem.block(0x7000, 0x0100, 0x20) == hook.mem.block(0x7000, 0x0100, 0x20)
    assert asm.mem.rw(0x1010, 0x0244) == hook.mem.rw(0x1010, 0x0244)
    assert asm.mem.rw(0x1010, 0x0610) == hook.mem.rw(0x1010, 0x0610)
    assert asm.mem.rb(0x1010, 0x0614) == hook.mem.rb(0x1010, 0x0614)


def test_expand_4plane_row_4537_hook_matches_interpreted_asm():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_expand_4plane_row_4537

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_expand_4plane_block_4511

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_expand_tandy_cell_33dd

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_expand_tandy_block_33b2

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_expand_tandy_block_33b2

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_expand_tandy_list_33af

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
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0x44AA)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_expand_tandy_list_33af_handles_disabled_header_table_like_asm():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_expand_tandy_list_33af

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_interlaced_clear_3389

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_masked_sprite_composite_2f81

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_masked_sprite_composite_2e6e

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


def test_tandy_strided_copy_34c5_hook_matches_interpreted_asm():
    import random
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_strided_copy_34c5

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_rect_copy_306f

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_source_strided_copy_35aa

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_small_strided_copy_34d8

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_draw_object_block_35cc

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_layer_sprite_draw_768e

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
            cpu.replacement_hooks[(0x1010, 0x768E)] = overkill_tandy_layer_sprite_draw_768e
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_layer_sprite_draw_75a6

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
            cpu.replacement_hooks[(0x1010, 0x75A6)] = overkill_tandy_layer_sprite_draw_75a6
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_scan_layer1_draw_a8c7

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_scan_layer0_draw_a894

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_lz_output_byte_ede9

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
    from overkill_port.cpu import CPU8086, CPUState, CF
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_lz_input_byte_ed97

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_overlay_xor_decode_254a_05bf

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_overlay_signature_compare_254a_0582

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
    from overkill_port.replacements import overkill_overlay_path_normalizer_254a_0701

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
    from overkill_port.replacements import overkill_overlay_entry_name_compare_254a_05d9

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
    from overkill_port.cpu import CF
    from overkill_port.replacements import overkill_overlay_directory_entry_scan_254a_05a1

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_lz_backref_copy_ed7a

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_lz_decoder_ecf2

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_lz_decoder_ecf2

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_expand_4plane_block_4511, overkill_expand_4plane_list_450c

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_linear_byte_rle_decoder_0367

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
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_497a_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:497A is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x497A), None)
    asm.cpu.hook_names.pop((0x1010, 0x497A), None)
    asm.cpu.trace_enabled = False

    for _ in range(10000):
        if asm.cpu.addr() == (0x1010, 0x58F1):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x58F1)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_row_copy_41da_hook_matches_interpreted_asm_on_zero_count_snapshot():
    from pathlib import Path
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_41da_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:41DA is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x41DA), None)
    asm.cpu.hook_names.pop((0x1010, 0x41DA), None)
    asm.cpu.trace_enabled = False

    for _ in range(500000):
        if asm.cpu.addr() == (0x1010, 0xCEB5):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xCEB5)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_ega_copy_5827_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_5827_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:5827 is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x5827), None)
    asm.cpu.hook_names.pop((0x1010, 0x5827), None)
    asm.cpu.trace_enabled = False

    for _ in range(10000):
        if asm.cpu.addr() == (0x1010, 0x58A4):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x58A4)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_vga_wait_50c9_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_50c9_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:50C9 is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x50C9), None)
    asm.cpu.hook_names.pop((0x1010, 0x50C9), None)
    asm.cpu.trace_enabled = False

    ret_ip = asm.cpu.mem.rw(asm.cpu.s.ss, asm.cpu.s.sp)
    for _ in range(100):
        if asm.cpu.addr() == (0x1010, ret_ip):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, ret_ip)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data
    assert asm.dos.vga_status_reads == hook.dos.vga_status_reads


def test_postcopy_loop_58df_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_58df_probe"
    assert snap.exists(), "captured oracle snapshot for 1010:58DF is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    for addr in [(0x1010, 0x58DF)]:
        asm.cpu.replacement_hooks.pop(addr, None)
        asm.cpu.hook_names.pop(addr, None)
    asm.cpu.trace_enabled = False

    for _ in range(5000):
        if asm.cpu.addr() == (0x1010, 0x58F8):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0x58F8)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data
    assert asm.dos.vga_status_reads == hook.dos.vga_status_reads


def test_tandy_postcopy_mode_sweep_5c74_hook_matches_interpreted_asm():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_postcopy_mode_sweep_5c74

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_wait_timer_tick_0679

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
    from overkill_port.replacements import overkill_wait_timer_tick_0679
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "timer_wait_tandy_main_menu_20260612_132548"
    assert snap.exists(), "Tandy menu snapshot with installed INT 08h is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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
    from overkill_port.hook_verify import HookVerifierConfig, install_hook_verifier
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "timer_wait_tandy_main_menu_20260612_132548"
    assert snap.exists(), "Tandy menu snapshot with installed INT 08h is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_present_frame_blit_447b

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_variable_width_interlaced_blit_41a6

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_dirty_copy_mode1_ccaa

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_presence_stamp_list_4d15

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_presence_stamp_list_4d15

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_presence_stamp_list_4d15, overkill_presence_stamp_triplet_4ced

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE
    from overkill_port.replacements import overkill_present_ega_frame_2750

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_ega_temp_row_copy_291c

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE
    from overkill_port.replacements import overkill_ega_temp_row_copy_291c

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import (
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_ega_transparency_mask_2932

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
    from overkill_port.cpu import CPUState
    from overkill_port.hook_verify import HookVerifierConfig, install_hook_verifier
    from overkill_port.runtime import create_runtime

    root = Path(__file__).resolve().parents[1]
    rt = create_runtime(root / "assets" / "OVERKILL.UNLZEXE.EXE", game_root=root / "assets")
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_ega_expand_temp_rows_2824

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_ega_load_temp_rows_280d

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_sprite_blit_9x16_477e

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_masked_sprite_composite_38b7

    # 38B7..38CF: lodsw / and ax,es:[di] / or ax,ds:[si] / add si,2 / stosw  (x2)
    #             add di,30h / loop 38B7 ; falls through to 38D0.
    routine = bytes.fromhex(
        'ad 26 23 05 0b 04 83 c6 02 ab'
        'ad 26 23 05 0b 04 83 c6 02 ab'
        '83 c7 30 e2 e7'.replace(' ', '')
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
            if asm.addr() == (0x1010, 0x38D0):
                break
            asm.step()
        hook.step()
        assert asm.addr() == hook.addr() == (0x1010, 0x38D0)
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

    from overkill_port.replacements import overkill_expand_4plane_row_4537

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

    from overkill_port.replacements import overkill_expand_4plane_block_4511

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
    from overkill_port.replacements import overkill_masked_sprite_composite_3849

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
    from overkill_port.replacements import overkill_ega_spaced_word_composite_1aeb

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
    from overkill_port.replacements import overkill_ega_spread_masked_composite_1d1b

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
    from overkill_port.replacements import overkill_ega_spread_masked_composite_wide_13e7

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
    from overkill_port.replacements import overkill_ega_spaced_copy_29c6

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
    from overkill_port.replacements import overkill_ega_source_spaced_copy_2ab9

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
    from overkill_port.replacements import overkill_sprite_copy_9x16_469f

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
    from overkill_port.replacements import overkill_scan_objects_call_5ac8_a849

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
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data

    asm = make_cpu(False, 0x20)
    hook = make_cpu(True, 0x20)
    for _ in range(300):
        if asm.addr() == (0x1010, 0xA858):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xA858)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_tandy_present_scan_a927_composes_known_targets_like_asm():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_scan_objects_call_5a92_a927

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_scan_objects_call_5a92_a927

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_scan_objects_call_5ac8_a849

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_scan_objects_call_5ac8_a849

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
    from overkill_port.replacements import overkill_scan_objects_call_aa2b_a9e0

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
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data

    asm = make_cpu(False, 0x20)
    hook = make_cpu(True, 0x20)
    for _ in range(500):
        if asm.addr() == (0x1010, 0xAA01):
            break
        asm.step()
    hook.step()
    assert asm.addr() == hook.addr() == (0x1010, 0xAA01)
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_bec5_bedc_one_collision_tail_matches_interpreted_asm():
    from overkill_port.replacements import _run_collision_handler_bec5_observed

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
    from overkill_port.replacements import _run_collision_handler_bec5_observed
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory

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
    from overkill_port.replacements import _run_collision_handler_bec5_observed
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory

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
    from overkill_port.replacements import _run_collision_handler_bec5_observed
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory

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
    assert mem.rw(ss, bp + 0x32) == 0x0000


def test_bec5_sprite_0033_falls_through_into_shared_tail():
    from overkill_port.replacements import _run_collision_handler_bec5_observed
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory

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
    from overkill_port.replacements import _run_collision_handler_bec5_observed
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory

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
    from overkill_port.replacements import _run_collision_handler_bec5_observed

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
    from overkill_port.replacements import _run_object_behavior_b73e

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
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_b73e_b82d_equal_waypoint_loop_matches_interpreted_asm():
    from pathlib import Path
    from overkill_port.replacements import _run_object_behavior_b73e

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
    from overkill_port.replacements import _run_object_behavior_b73e

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
    from overkill_port.replacements import _run_object_behavior_b73e

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
    from overkill_port.replacements import _run_object_behavior_b73e

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
    from overkill_port.replacements import _run_object_behavior_b73e

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import (
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
    from overkill_port.hook_verify import DEFAULT_STOPS

    stop = DEFAULT_STOPS[(0x1010, 0xAA2B)]
    assert stop.kind == "dispatch_aa2b"


def test_hook_verify_far_ret_stop_reads_ip_then_cs_from_stack():
    from overkill_port.hook_verify import HookStop

    mem = Memory()
    ss = 0x3000
    sp = 0x8FFE
    mem.ww(ss, sp, 0x0707)
    mem.ww(ss, (sp + 2) & 0xFFFF, 0x254A)
    state = CPUState(cs=0x254A, ip=0x0701, ss=ss, sp=sp)
    cpu = CPU8086(mem, state)

    assert HookStop("far_ret").targets(cpu, state) == ((0x254A, 0x0707),)


def test_keyboard_poll_bits_017e_hook_matches_interpreted_asm():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_keyboard_poll_bits_017e

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_changed_word_present_8rows_cd8d

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_changed_dword_present_8rows_cdaa

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_cga_object_row_addr_5a36

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
            cpu.replacement_hooks[(0x1010, 0x5A36)] = overkill_cga_object_row_addr_5a36
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_cga_object_row_addr_5a36

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
            cpu.replacement_hooks[(0x1010, 0x5A36)] = overkill_cga_object_row_addr_5a36
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_cga_xy_to_di_5a00, overkill_cga_xy_to_di_5a24

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
        (0x5A00, overkill_cga_xy_to_di_5a00, dispatch_5a00, target_422b, 0x422B, 0x9EE8, 0),
        (0x5A24, overkill_cga_xy_to_di_5a24, dispatch_5a24, target_4251, 0x4251, 0x9D58, 0),
        (0x5A00, overkill_cga_xy_to_di_5a00, dispatch_5a00, target_25b6, 0x25B6, 0x9EE8, 1),
        (0x5A24, overkill_cga_xy_to_di_5a24, dispatch_5a24, target_25d8, 0x25D8, 0x9D58, 1),
        (0x5A00, overkill_cga_xy_to_di_5a00, dispatch_5a00, target_3103, 0x3103, 0x9EE8, 2),
        (0x5A24, overkill_cga_xy_to_di_5a24, dispatch_5a24, target_312d, 0x312D, 0x9D58, 2),
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_masked_sprite_composite_3e12

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_strided_row_copy_3ee1, overkill_strided_row_copy_3efc

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_masked_sprite_composite_3efb

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_dispatch_draw_object_5ac8, overkill_dispatch_present_object_5a92

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_clc_ret_aa44

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
    from overkill_port.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE
    from overkill_port.replacements import _rep_movsb

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE
    from overkill_port.replacements import _rep_stosb

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
    from overkill_port.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE

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
    from overkill_port.memory import Memory, EGA_APERTURE, EGA_PLANE_STRIDE

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_tiny_strided_copy_3542

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_split_present_copy_34ad

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_scan_objects_call_5a92_a90f

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


def test_movement_direction_5db2_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "closure_run_5db2_160415"
    assert snap.exists(), "captured oracle snapshot for 1010:5DB2 is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    asm.cpu.replacement_hooks.pop((0x1010, 0x5DB2), None)
    asm.cpu.hook_names.pop((0x1010, 0x5DB2), None)
    asm.cpu.trace_enabled = False
    for _ in range(100):
        if asm.cpu.addr() == (0x1010, 0xB738):
            break
        asm.cpu.step()

    hook = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    hook.cpu.trace_enabled = False
    hook.cpu.step()

    assert asm.cpu.addr() == hook.cpu.addr() == (0x1010, 0xB738)
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_hook_verifier_verifies_movement_direction_5db2_without_skipping():
    from pathlib import Path
    from overkill_port.hook_verify import HookVerifierConfig, install_hook_verifier
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "closure_run_5db2_160415"
    assert snap.exists(), "captured oracle snapshot for 1010:5DB2 is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _find_free_object_slot_7573

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _find_free_object_slot_7573

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


def test_gameplay_counter_stride_loop_1f8f_0960_matches_interpreted_asm():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_gameplay_counter_stride_loop_1f8f_0960

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
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "ac97_stop"
    assert snap.exists(), "captured oracle snapshot for 1010:AC97 is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_object_slot_scan_ac97

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
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "bc4b_stop"
    assert snap.exists(), "captured oracle snapshot for 1010:BCB1 is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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
    assert asm.cpu.s.snapshot() == hook.cpu.s.snapshot()
    assert asm.program.memory.data == hook.program.memory.data


def test_bd17_deactivate_logic_2a_falls_through_without_counter_drop():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _run_deactivate_bd17_observed

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _run_deactivate_bd17_observed

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
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "bd17_selector_a83e_tail_20260613_125913"
    assert snap.exists(), "captured oracle snapshot for 1010:BD17 selector A83E tail is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.games.overkill.gameplay.collision import run_object_deactivate_logic_dispatch_c054
    from overkill_port.memory import Memory

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _run_collision_death_tail_bfc7

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _run_collision_death_tail_bfc7

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _run_collision_death_tail_bfc7

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


def test_bfc7_logic_3b_uses_c054_default_and_completes_transition():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _run_collision_death_tail_bfc7

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
    from overkill_port.games.overkill.gameplay.collision import run_postmove_contact_window_aa71
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "next_frontier_probe_4"
    assert snap.exists(), "captured oracle snapshot for 1010:AA71 is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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


def test_aa71_upper_contact_tail_forced_upper_branch_matches_interpreted_asm():
    from pathlib import Path
    from overkill_port.games.overkill.gameplay.collision import run_postmove_contact_window_aa71
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "next_frontier_probe_4"
    assert snap.exists(), "captured oracle snapshot for 1010:AA71 is missing"

    def make_runtime():
        rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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


def test_object_postmove_bc4b_hook_matches_interpreted_asm_on_captured_snapshot():
    from pathlib import Path
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "bc4b_stop"
    assert snap.exists(), "captured oracle snapshot for 1010:BC4B is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "bc4b_variant_000a_owner_linked_20260613_000648"
    assert snap.exists(), "captured oracle snapshot for BEC5 variant 000A owner-linked tail is missing"

    def make_runtime(use_hook: bool):
        rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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


def test_object_overlap_scan_62f6_preserves_bx_and_flags_on_signed_x_early_exit():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _run_object_overlap_scan_62f6

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


def test_tandy_text_glyph_3153_hook_verifies_on_gameplay_snapshot():
    from pathlib import Path
    from overkill_port.hook_verify import HookVerifierConfig, HookVerifyLimitReached, install_hook_verifier
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "tandy_text_score_gameplay_20260612_163127"
    assert snap.exists(), "gameplay snapshot for 1010:3153 text glyph verification is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    # Wider text hooks absorb calls before they reach the narrow 3153 glyph
    # hook.  Disable them here so this regression continues to verify the
    # original 3153 boundary directly.
    for key in ((0x1010, 0x518C), (0x1010, 0x519A)):
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
    from overkill_port.hook_verify import HookVerifierConfig, HookVerifyLimitReached, install_hook_verifier
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "tandy_text_score_gameplay_20260612_163127"
    assert snap.exists(), "gameplay snapshot for 1010:5EF9 score-byte text verification is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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


def test_bfc7_linked_slot_decrements_counter_and_completes_transition():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _run_collision_death_tail_bfc7

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import _run_collision_death_tail_bfc7

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_pixel_pair_table_0fe4

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_tandy_video_offset_tables_0fa3

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
    from overkill_port.hook_verify import HookVerifierConfig, HookVerifyLimitReached, install_hook_verifier
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "evidence" / "snapshot_stop_tandy_cc7f"
    assert snap.exists(), "startup snapshot for 1010:CC7F dirty-cell presenter verification is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
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
    from overkill_port.snapshot import load_snapshot

    class FrameBoundary(Exception):
        pass

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "dirty_cell_presenter_pacing_20260612_235139"
    assert snap.exists(), "intro dirty-cell snapshot is missing"

    rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    base_retrace = rt.cpu.replacement_hooks[(0x1010, 0x50C9)]

    def pacing_wrapper(cpu):
        nested_dirty_presenter_call = (cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF) == (0x1010, 0xCD52)
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
    from overkill_port.replacements import overkill_decoded_asset_table_search_c713

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
    from overkill_port.snapshot import load_snapshot
    from overkill_port.replacements import overkill_overlay_container_open_entry_254a_04d7

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "snapshot_stop_254a_04d7_overlay_parent"
    assert snap.exists(), "captured oracle snapshot for 254A:04D7 is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    hook = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")

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
    from overkill_port.snapshot import load_snapshot
    from overkill_port.replacements import overkill_startup_coordinate_tables_0f0b

    root = Path(__file__).resolve().parents[1]
    snap = root / "artifacts" / "test_oracles" / "snapshot_stop_1010_0f0b_startup_tables"
    assert snap.exists(), "captured oracle snapshot for 1010:0F0B is missing"

    asm = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    hook = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_input_poll_0162

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

    from overkill_port.replacements import overkill_input_selector_loop_d445
    from overkill_port.snapshot import load_snapshot

    root = Path(__file__).resolve().parents[1]
    exe = root / "assets" / "OVERKILL.UNLZEXE.EXE"
    snapshot = root / "artifacts" / "evidence" / "bc4b_stop"

    cases = [
        (0x01, 0x00, 0x00, 0x00, 0x03),
        (0x02, 0x04, 0x00, 0x00, 0x01),
        (0x04, 0x04, 0x00, 0x00, 0x05),
        (0x08, 0x04, 0x00, 0x00, 0x03),
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

    # Exercise the "wait once, then continue" branch without hanging forever.
    asm = make_cpu(
        False,
        button_mask=0x00,
        button_masks=[0x00, 0x04],
        beda_seed=0x04,
        bedc_seed=0x00,
        state98e4=0x00,
    )
    hook = make_cpu(
        True,
        button_mask=0x00,
        button_masks=[0x00, 0x04],
        beda_seed=0x04,
        bedc_seed=0x00,
        state98e4=0x00,
    )

    for _ in range(120):
        if asm.addr() == (0x1010, 0xAA04):
            break
        asm.step()
    hook.step()

    assert asm.addr() == hook.addr() == (0x1010, 0xAA04)
    assert asm.mem.rb(asm.s.ds & 0xFFFF, 0xBEDA) == 0x05
    assert asm.s.snapshot() == hook.s.snapshot()
    assert asm.mem.data == hook.mem.data


def test_intro_retrace_delay_loop_96c5_matches_interpreted_asm_with_stubbed_50c9():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_intro_retrace_delay_loop_96c5

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

    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.dos import DOSMachine
    from overkill_port.hook_verify import HookVerifierConfig, install_hook_verifier
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_intro_retrace_delay_loop_96c5
    from overkill_port.runtime import Runtime

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
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_intro_retrace_delay_loop_96c5, overkill_intro_retrace_delay_loop_tail_96c8

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
    from overkill_port.hook_verify import DEFAULT_STOPS

    stop = DEFAULT_STOPS[(0x1010, 0xD007)]
    assert stop.kind == "fixed_ips"
    assert stop.min_steps == 1
    assert 0xD007 in stop.ips
    assert 0xD040 in stop.ips


def test_main_frame_loop_d007_hook_matches_one_interpreted_frame_iteration():
    from pathlib import Path

    from overkill_port.hook_verify import HookVerifier, HookVerifierConfig
    from overkill_port.replacements import registry
    from overkill_port.snapshot import load_snapshot

    root = Path.cwd()
    snap = root / "artifacts" / "test_oracles" / "main_frame_loop_d007"
    rt = load_snapshot(root / "assets" / "OVERKILL.UNLZEXE.EXE", snap, game_root=root / "assets")
    registry.install(rt.cpu)
    verifier = HookVerifier(
        rt,
        HookVerifierConfig(hooks={(0x1010, 0xD007)}, stop_on_diff=True, log_diffs=True, asm_max_steps=1_000_000),
    )
    rt.cpu.hook_verifier = verifier.verify

    rt.cpu.step()

    assert verifier.total_verified == 1
    assert rt.cpu.addr() in {(0x1010, 0xD007), (0x1010, 0xD040)}
