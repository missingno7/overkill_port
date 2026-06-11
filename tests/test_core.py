from overkill_port.memory import Memory
from overkill_port.cpu import CPU8086, CPUState


def run_bytes(code: bytes, steps: int = 10):
    mem = Memory()
    mem.load(0x1000, 0, code)
    cpu = CPU8086(mem, CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    cpu.run(steps)
    return cpu


def test_mov_add_ret():
    cpu = run_bytes(bytes.fromhex("b8 34 12 05 01 00 f4"), 3)
    assert cpu.s.ax == 0x1235


def test_memory_operand_decoded_once():
    # mov [0100],1234 ; add [0100],0001 ; hlt
    cpu = run_bytes(bytes.fromhex("c7 06 00 01 34 12 81 06 00 01 01 00 f4"), 3)
    assert cpu.mem.rw(0x1000, 0x0100) == 0x1235
    assert cpu.s.ip == 0x000D


def test_rep_movsb_backward():
    mem = Memory()
    mem.load(0x1000, 0, bytes([1, 2, 3, 4]))
    code = bytes.fromhex("fd b9 04 00 be 03 00 bf 13 00 f3 a4 f4")
    mem.load(0x2000, 0, code)
    cpu = CPU8086(mem, CPUState(cs=0x2000, ds=0x1000, es=0x1000, ss=0x2000, sp=0xFFFE))
    cpu.run(6)
    assert mem.block(0x1000, 0x10, 4) == bytes([1, 2, 3, 4])


def test_pop_rm16_memory_opcode_8f():
    # mov ax,1234 ; push ax ; pop word [0100] ; hlt
    cpu = run_bytes(bytes.fromhex("b8 34 12 50 8f 06 00 01 f4"), 4)
    assert cpu.mem.rw(0x1000, 0x0100) == 0x1234
    assert cpu.s.sp == 0xFFFE


def test_dos_version_returns_al_major_ah_minor():
    from overkill_port.dos import DOSMachine
    from overkill_port.cpu import CF
    cpu = CPU8086(Memory(), CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    dos = DOSMachine(root=__import__('pathlib').Path('.'))
    cpu.s.ax = 0x3000
    dos.interrupt(cpu, 0x21)
    assert cpu.s.ax == 0x0005
    assert not cpu.get_flag(CF)


def test_ega_crtc_display_start_tracks_indexed_port_writes():
    from overkill_port.dos import DOSMachine

    mem = Memory()
    cpu = CPU8086(mem, CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    dos = DOSMachine(root=__import__('pathlib').Path('.'))

    dos.port_write(cpu, 0x03D4, 0x120C, 16)
    dos.port_write(cpu, 0x03D4, 0x340D, 16)
    assert mem.ega_display_start == 0x1234

    dos.port_write(cpu, 0x03D4, 0x0C, 8)
    dos.port_write(cpu, 0x03D5, 0x20, 8)
    assert mem.ega_display_start == 0x2034


def test_key_dispatcher_holds_tap_for_one_frame():
    from overkill_port.keyboard import KeyDispatcher
    log: list[int] = []
    d = KeyDispatcher(log.append)
    # A tap (down+up) arriving before a frame: make this frame, break next frame.
    d.post_down(0x39)
    d.post_up(0x39)
    d.pump()
    assert log == [0x39]                 # key is down for this whole frame
    d.pump()
    assert log == [0x39, 0x39 | 0x80]    # released only after one full frame
    d.pump()
    assert log == [0x39, 0x39 | 0x80]


def test_key_dispatcher_hold_release_and_autorepeat():
    from overkill_port.keyboard import KeyDispatcher
    log: list[int] = []
    d = KeyDispatcher(log.append)
    d.post_down(0x10)
    d.post_down(0x10)  # OS auto-repeat must not re-deliver a make
    d.pump()
    assert log == [0x10]
    d.pump()
    d.pump()
    assert log == [0x10]                 # still held, no extra events
    d.post_up(0x10)
    d.pump()
    assert log == [0x10, 0x90]           # break delivered on release


def test_key_dispatcher_drains_release_during_long_no_frame_burst():
    from overkill_port.keyboard import KeyDispatcher
    log: list[int] = []
    d = KeyDispatcher(log.append)

    d.post_down(0x39)
    d.pump()
    assert log == [0x39]

    d.post_up(0x39)
    d.pump_events()
    assert log == [0x39, 0x39 | 0x80]


def test_iret_restores_cs_ip_and_flags():
    mem = Memory()
    mem.wb(0x2000, 0x0100, 0xCF)  # IRET
    cpu = CPU8086(mem, CPUState(cs=0x2000, ip=0x0100, ss=0x4000, sp=0x0100))
    cpu.trace_enabled = False
    # An interrupt frame is FLAGS, CS, IP from top of stack downward.
    cpu.push(0x0ABC)  # FLAGS
    cpu.push(0x1234)  # CS
    cpu.push(0x5678)  # IP
    sp_after_push = cpu.s.sp
    cpu.step()
    assert (cpu.s.cs, cpu.s.ip) == (0x1234, 0x5678)
    assert cpu.s.flags == (0x0ABC | 0x0002)
    assert cpu.s.sp == (sp_after_push + 6) & 0xFFFF


def test_set_get_interrupt_vector_roundtrip():
    from pathlib import Path
    from overkill_port.dos import DOSMachine
    cpu = CPU8086(Memory(), CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    dos = DOSMachine(root=Path('.'))

    # AH=25h sets INT 09h vector from DS:DX into the real IVT.
    cpu.s.ax = 0x2509
    cpu.s.ds = 0x1234
    cpu.s.dx = 0x5678
    dos.interrupt(cpu, 0x21)
    assert cpu.mem.rw(0, 0x09 * 4) == 0x5678
    assert cpu.mem.rw(0, 0x09 * 4 + 2) == 0x1234

    # AH=35h reads it back into ES:BX.
    cpu.s.ax = 0x3509
    cpu.s.ds = 0
    cpu.s.dx = 0
    dos.interrupt(cpu, 0x21)
    assert cpu.s.bx == 0x5678
    assert cpu.s.es == 0x1234


def test_deliver_interrupt_runs_isr_to_iret():
    from types import SimpleNamespace
    from overkill_port.interrupts import deliver_interrupt
    mem = Memory()
    # Tiny ISR at 3000:0000 -> inc word ptr [0500]; iret
    mem.load(0x3000, 0x0000, bytes.fromhex('ff 06 00 05 cf'))
    mem.ww(0, 0x40 * 4, 0x0000)      # IVT[40h] offset
    mem.ww(0, 0x40 * 4 + 2, 0x3000)  # IVT[40h] segment
    mem.ww(0x3000, 0x0500, 0)
    cpu = CPU8086(mem, CPUState(cs=0x1010, ip=0x9999, ds=0x3000, ss=0x5000, sp=0x0200))
    cpu.trace_enabled = False
    rt = SimpleNamespace(cpu=cpu)

    cs0, ip0, sp0 = cpu.s.cs, cpu.s.ip, cpu.s.sp
    assert deliver_interrupt(rt, 0x40) is True
    assert mem.rw(0x3000, 0x0500) == 1               # ISR ran
    assert (cpu.s.cs, cpu.s.ip, cpu.s.sp) == (cs0, ip0, sp0)  # returned cleanly

    # No handler installed -> no-op.
    assert deliver_interrupt(rt, 0x41) is False


def test_int16_keyboard_queue_and_headless_fallback():
    from pathlib import Path
    from overkill_port.dos import DOSMachine
    from overkill_port.cpu import ZF
    cpu = CPU8086(Memory(), CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    dos = DOSMachine(root=Path('.'))

    # Empty queue keeps deterministic headless behaviour: AH=01 reports no key,
    # AH=00 returns Esc.
    cpu.s.ax = 0x0100
    dos.interrupt(cpu, 0x16)
    assert cpu.get_flag(ZF)
    cpu.s.ax = 0x0000
    dos.interrupt(cpu, 0x16)
    assert cpu.s.ax == 0x011B

    # A queued key is reported by the check call (ZF=0, AX=key) without consuming
    # it, then consumed by the blocking read.
    dos.key_queue.append(0x1C0D)  # Enter: scan 1C, ASCII 0D
    cpu.s.ax = 0x0100
    dos.interrupt(cpu, 0x16)
    assert not cpu.get_flag(ZF)
    assert cpu.s.ax == 0x1C0D
    cpu.s.ax = 0x0000
    dos.interrupt(cpu, 0x16)
    assert cpu.s.ax == 0x1C0D
    assert dos.key_queue == []
    cpu.s.ax = 0x0100
    dos.interrupt(cpu, 0x16)
    assert cpu.get_flag(ZF)



def test_int21_console_input_uses_keyboard_queue_and_fallback():
    from pathlib import Path
    from overkill_port.dos import DOSMachine

    cpu = CPU8086(Memory(), CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    dos = DOSMachine(root=Path('.'))

    dos.key_queue.append(0x1C0D)  # Enter: scan 1C, ASCII 0D
    cpu.s.ax = 0x0700
    dos.interrupt(cpu, 0x21)
    assert cpu.s.ax == 0x070D
    assert dos.key_queue == []

    cpu.s.ax = 0x0800
    dos.interrupt(cpu, 0x21)
    assert cpu.s.ax == 0x081B

    dos.key_queue.append(0x2041)
    cpu.s.ax = 0x0100
    dos.interrupt(cpu, 0x21)
    assert cpu.s.ax == 0x0141
    assert dos.stdout[-1] == 'A'

def test_dos_seeded_psp_resize_and_distinct_allocations():
    from pathlib import Path
    from overkill_port.dos import DOSMachine
    from overkill_port.cpu import CF
    cpu = CPU8086(Memory(), CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    dos = DOSMachine(root=Path('.'))
    dos.seed_initial_memory_block(0x1000, 0xA000)

    # OVERKILL startup does this: shrink the PSP-owned initial block so the
    # DOS heap starts immediately after the relocated stack/image area.
    cpu.s.es = 0x1000
    cpu.s.bx = 0x22FF
    cpu.s.ax = 0x4A00
    dos.interrupt(cpu, 0x21)
    assert not cpu.get_flag(CF)
    assert dos.allocations[0x1000] == 0x22FF
    assert dos.next_alloc_segment == 0x32FF

    # Subsequent AH=48 allocations must not alias each other.
    cpu.s.ax = 0x4800
    cpu.s.bx = 0x0100
    dos.interrupt(cpu, 0x21)
    first = cpu.s.ax
    assert first == 0x32FF
    assert not cpu.get_flag(CF)

    cpu.s.ax = 0x4800
    cpu.s.bx = 0x0020
    dos.interrupt(cpu, 0x21)
    second = cpu.s.ax
    assert second == 0x33FF
    assert second != first
    assert not cpu.get_flag(CF)


def test_daa_adjusts_bcd_add_and_sets_carry_for_next_digit():
    from overkill_port.cpu import CF, AF, PF, ZF, SF

    # OVERKILL overlay code at 1010:5F18 uses ADD/DAA followed by ADC/DAA
    # while updating packed decimal-looking score/text digits.  This covers the
    # carry behavior that matters for that path: 59 + 73 => 32 with carry.
    cpu = run_bytes(bytes.fromhex("b0 59 04 73 27 f4"), 4)
    assert cpu.s.ax & 0x00FF == 0x32
    assert cpu.get_flag(CF)
    assert cpu.get_flag(AF)
    assert not cpu.get_flag(ZF)
    assert not cpu.get_flag(SF)
    assert not cpu.get_flag(PF)


def test_daa_without_adjust_clears_decimal_carry_flags():
    from overkill_port.cpu import CF, AF

    cpu = run_bytes(bytes.fromhex("b0 12 04 03 27 f4"), 4)
    assert cpu.s.ax & 0x00FF == 0x15
    assert not cpu.get_flag(CF)
    assert not cpu.get_flag(AF)


def test_create_runtime_accepts_command_tail():
    from pathlib import Path
    from overkill_port.runtime import create_runtime

    root = Path(__file__).resolve().parents[1]
    rt = create_runtime(root / "assets" / "OVERKILL.UNLZEXE.EXE", game_root=root / "assets", command_tail=" /E")
    psp = rt.program.psp_segment
    assert rt.program.memory.rb(psp, 0x80) == 3
    assert rt.program.memory.block(psp, 0x81, 4) == b" /E\r"


def test_hook_registry_rejects_duplicate_registration():
    # Two replacements at the same CS:IP must fail loudly.  The map is keyed by
    # CS:IP, so a silent overwrite is exactly how superseded hook bodies used to
    # accrete unnoticed; the guard keeps one address mapped to one replacement.
    from overkill_port.hooks import HookRegistry

    reg = HookRegistry()

    @reg.replace(0x1010, 0x1234, "first")
    def first(cpu):  # pragma: no cover - body never runs in this test
        pass

    raised = False
    try:
        @reg.replace(0x1010, 0x1234, "second")
        def second(cpu):  # pragma: no cover - registration fails before use
            pass
    except ValueError as exc:
        raised = True
        assert "1010:1234" in str(exc)
    assert raised, "duplicate CS:IP registration should raise ValueError"
    # The first registration is intact and a different address still registers.
    assert reg.replacements[(0x1010, 0x1234)].name == "first"

    @reg.replace(0x1010, 0x5678, "other")
    def other(cpu):  # pragma: no cover - body never runs in this test
        pass

    assert (0x1010, 0x5678) in reg.replacements


def test_production_registry_has_no_duplicate_addresses():
    # Importing the real hook table must not trip the duplicate guard, i.e. the
    # shipped replacements.py keeps exactly one replacement per CS:IP.
    import overkill_port.replacements  # noqa: F401  (registers hooks on import)
    from overkill_port.hooks import registry

    assert len(registry.replacements) > 0
