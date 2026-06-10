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
    snap = root / "artifacts" / "snapshot_stop_497a_probe"
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
    snap = root / "artifacts" / "snapshot_stop_41da_probe"
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
    snap = root / "artifacts" / "snapshot_stop_5827_probe"
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
    snap = root / "artifacts" / "snapshot_stop_50c9_probe"
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
    snap = root / "artifacts" / "snapshot_stop_58df_probe"
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


def test_wait_timer_tick_0679_hook_matches_interpreted_asm():
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

    # Case A: flag starts at 0.  The hook models one elapsed ISR tick (066B->1);
    # the oracle is the same loop with the tick already delivered (066B preset
    # to 1) so the interpreted ASM actually terminates.  Both must agree.
    hook = make_cpu(True, 0)
    oracle = make_cpu(False, 1)
    hook.step()
    for _ in range(10):
        if oracle.addr() == (0x1010, 0xBEEF):
            break
        oracle.step()
    assert hook.addr() == oracle.addr() == (0x1010, 0xBEEF)
    assert hook.s.snapshot() == oracle.s.snapshot()
    assert hook.mem.rb(0x1010, 0x066B) == oracle.mem.rb(0x1010, 0x066B) == 1

    # Case B: flag already non-zero.  The loop exits immediately without changing
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


def test_present_ega_frame_2750_hook_writes_shadow_planes():
    from overkill_port.cpu import CPU8086, CPUState
    from overkill_port.memory import Memory
    from overkill_port.replacements import overkill_present_ega_frame_2750

    mem = Memory()
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

    # First output row starts at A000:00A0.  The four source plane chunks are
    # stored in the explicit shadow planes at +0000/+2000/+4000/+6000.
    assert mem.block(0xA000, 0x00A0, 26) == mem.block(0x6000, 0x0100, 26)
    assert mem.block(0xA000, 0x20A0, 26) == mem.block(0x6000, 0x0100 + 26, 26)
    assert mem.block(0xA000, 0x40A0, 26) == mem.block(0x6000, 0x0100 + 52, 26)
    assert mem.block(0xA000, 0x60A0, 26) == mem.block(0x6000, 0x0100 + 78, 26)


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

    def make_cpu(use_hook: bool, outer_count: int, transparent: bool) -> CPU8086:
        mem = Memory()
        mem.data[0x1010 * 16 + 0x2824:0x1010 * 16 + 0x2824 + len(code)] = code
        mem.ww(0x1010, 0x5B9C, 0x0003)
        mem.ww(0x1010, 0x0BD6, 1 if transparent else 0)
        mem.wb(0x1010, 0x0000, 0x05)
        mem.wb(0x1010, 0xC5B0, 0)
        mem.ww(0x1010, 0x5BA6, 0x0120)
        for i in range(0xA0):
            mem.wb(0x1010, 0x5AF4 + i, (0x17 + i * 23) & 0xFF)
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

    for outer_count, transparent in ((1, False), (2, True)):
        asm = make_cpu(False, outer_count, transparent)
        hook = make_cpu(True, outer_count, transparent)
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
