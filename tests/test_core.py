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


def test_hook_verify_range_diff_keeps_exact_mismatch_report():
    from overkill_port.hook_verify import HookVerifier, MemoryRange

    asm = bytearray(b"\x00" * 64)
    hook = bytearray(asm)
    rng = MemoryRange("probe", 8, 32)

    assert HookVerifier._range_diff(asm, hook, rng) is None

    hook[12] = 0x34
    hook[30] = 0x56
    report = HookVerifier._range_diff(asm, hook, rng)
    assert report is not None
    assert "differing bytes: 2" in report
    assert "first diff: 0000C asm=00 hook=34" in report


def test_hook_verify_defaults_to_full_memory_image():
    from types import SimpleNamespace
    from overkill_port.hook_verify import HookVerifier, HookVerifierConfig

    mem = Memory()
    hv = HookVerifier.__new__(HookVerifier)
    hv.config = HookVerifierConfig()
    rt = SimpleNamespace(
        program=SimpleNamespace(memory=mem),
        cpu=SimpleNamespace(s=CPUState(cs=0x1010, ds=0x2000, es=0x2000, ss=0x2000)),
    )

    ranges = hv._memory_ranges(rt)

    assert len(ranges) == 1
    assert ranges[0].name == "full memory"
    assert ranges[0].start == 0
    assert ranges[0].size == len(mem.data)


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


def test_cbw_sign_extends_al_without_changing_flags():
    cpu = run_bytes(bytes.fromhex("b0 80 98 f4"), 3)
    assert cpu.s.ax == 0xFF80
    assert cpu.s.flags == 0x0202

    cpu = run_bytes(bytes.fromhex("b0 7f 98 f4"), 3)
    assert cpu.s.ax == 0x007F
    assert cpu.s.flags == 0x0202


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


def test_pc_speaker_tracks_pit_channel2_and_gate():
    from pathlib import Path
    from overkill_port.dos import DOSMachine

    mem = Memory()
    cpu = CPU8086(mem, CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    dos = DOSMachine(root=Path('.'))
    events: list[tuple[bool, float]] = []
    dos.speaker_callback = lambda enabled, freq: events.append((enabled, freq))

    dos.port_write(cpu, 0x43, 0xB6, 8)  # channel 2, lobyte/hibyte, square wave
    dos.port_write(cpu, 0x42, 0x34, 8)
    assert events == []
    dos.port_write(cpu, 0x42, 0x12, 8)
    assert dos.pit_channel2_reload == 0x1234
    assert events[-1][0] is False

    dos.port_write(cpu, 0x61, 0x03, 8)
    assert events[-1][0] is True
    assert abs(events[-1][1] - (1193182.0 / 0x1234)) < 0.001
    assert dos.port_read(cpu, 0x61, 8) == 0x03

    dos.port_write(cpu, 0x61, 0x00, 8)
    assert events[-1] == (False, 0.0)


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



def test_key_dispatcher_can_defer_release_after_present_boundary():
    from overkill_port.keyboard import KeyDispatcher
    log: list[int] = []
    d = KeyDispatcher(log.append)

    d.post_down(0x01)
    d.pump()
    assert log == [0x01]

    # The interactive player uses this immediately after a visual present.
    # The physical key-up is recorded, but the game's key table remains pressed
    # until the VM has passed post-present input polling.
    d.post_up(0x01)
    d.pump(allow_release=False)
    assert log == [0x01]

    d.pump_events()
    assert log == [0x01, 0x01 | 0x80]

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


def test_int21_console_input_can_block_without_consuming_instruction():
    from pathlib import Path
    from overkill_port.dos import ConsoleInputWouldBlock, DOSMachine

    cpu = CPU8086(Memory(), CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    dos = DOSMachine(root=Path('.'))
    dos.console_input_fallback = None

    cpu.s.ax = 0x0700
    cpu.s.ip = 0x1236
    try:
        dos.interrupt(cpu, 0x21)
    except ConsoleInputWouldBlock:
        pass
    else:
        raise AssertionError("empty interactive console input should block")

    assert cpu.s.ip == 0x1234
    assert cpu.s.ax == 0x0700


def test_int10_teletype_accepts_high_score_editor_bell():
    from pathlib import Path
    from overkill_port.dos import DOSMachine

    cpu = CPU8086(Memory(), CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    dos = DOSMachine(root=Path('.'))

    cpu.s.ax = 0x0E07
    dos.interrupt(cpu, 0x10)

    assert dos.stdout[-1] == '\x07'
    assert cpu.s.ax == 0x0E07


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
    rt = create_runtime(root / "assets" / "OVERKILL", game_root=root / "assets", command_tail=" /E")
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


def test_coverage_telemetry_counts_interpreted_and_verified_hooks():
    from overkill_port.coverage import CoverageTelemetry, OverkillCoverageClassifier

    cov = CoverageTelemetry(classifier=OverkillCoverageClassifier(), cache_path=None)
    cov.record_interpreted_instruction((0x1010, 0x03A8))
    cov.record_hook_verified((0x1010, 0x03A8), "overkill_vertical_rle_decoder_03a8", 123)
    cov.record_hook_skipped((0x1010, 0xDEAD), "unknown_hook")

    snap = cov.snapshot()
    assert snap["total_interpreted_instructions"] == 1
    assert snap["hook_verified_equiv_instructions"] == 123
    assert snap["total_hook_calls"] == 2
    assert snap["verified_hook_calls"] == 1
    assert snap["skipped_hooks"] == 1
    assert snap["unknown_unmeasured_hook_calls"] == 1
    assert snap["islands"]["asset_codecs"].interpreted_asm == 1
    assert snap["islands"]["asset_codecs"].hooked_verified_equiv == 123


def test_coverage_summary_reports_grouped_interpreted_regions():
    from overkill_port.coverage import CoverageTelemetry, OverkillCoverageClassifier

    cov = CoverageTelemetry(classifier=OverkillCoverageClassifier(), cache_path=None)
    for ip in (0xACD9, 0xACDD, 0xACDF, 0xACE3, 0xACE8, 0xACEC):
        for _ in range(10):
            cov.record_interpreted_instruction((0x1010, ip))
    for _ in range(100):
        cov.record_interpreted_instruction((0x1010, 0xADDF))

    snap = cov.snapshot(top_n=4)
    regions = snap["top_interpreted_regions"]
    assert regions[0]["start"] == (0x1010, 0xADDF)
    assert regions[0]["hits"] == 100
    assert regions[0]["island"] == "gameplay_objects"
    assert any(
        item["start"] == (0x1010, 0xACD9)
        and item["end"] == (0x1010, 0xACEC)
        and item["hits"] == 60
        and item["island"] == "collision"
        for item in regions
    )
    text = cov.format_summary(top_n=4)
    assert "per instruction" in text
    assert "nearby IPs grouped" in text


def test_cpu_emits_coverage_for_generic_asm_and_hook():
    from overkill_port.coverage import CoverageTelemetry, OverkillCoverageClassifier

    mem = Memory()
    # 0000: mov ax,1234 ; hlt.  0010: hook target.
    mem.load(0x1000, 0, bytes.fromhex("b8 34 12 f4"))
    cpu = CPU8086(mem, CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFFE))
    cov = CoverageTelemetry(classifier=OverkillCoverageClassifier(), cache_path=None)
    cpu.coverage_telemetry = cov
    cpu.step()
    assert cov.snapshot()["total_interpreted_instructions"] == 1

    def fake_hook(cpu):
        cpu.s.ip = 0x0004

    cpu.s.ip = 0x0010
    cpu.replacement_hooks[(0x1000, 0x0010)] = fake_hook
    cpu.hook_names[(0x1000, 0x0010)] = "fake_hook"
    cpu.step()
    snap = cov.snapshot()
    assert snap["total_hook_calls"] == 1
    assert snap["unverified_hook_calls"] == 1

def test_coverage_classifier_marks_transient_bootstrap_segment():
    from overkill_port.coverage import OverkillCoverageClassifier

    classifier = OverkillCoverageClassifier()
    assert classifier.classify((0x32FF, 0x0052)) == "bootstrap"
    assert classifier.classify((0x32FF, 0x00C0)) == "bootstrap"



def test_overkill_coverage_exact_address_sets_do_not_overlap():
    import ast
    from pathlib import Path

    source = Path("overkill_port/coverage.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    classifier = next(
        node for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "OverkillCoverageClassifier"
    )
    exact_sets = {}
    for node in classifier.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and (node.target.id.endswith("_ADDRS") or node.target.id == "OVERLAY_ADDRS")
        ):
            exact_sets[node.target.id] = set(ast.literal_eval(node.value))

    owners = {}
    overlaps = []
    for set_name, addrs in exact_sets.items():
        for addr in addrs:
            previous = owners.setdefault(addr, set_name)
            if previous != set_name:
                overlaps.append((addr, previous, set_name))

    assert overlaps == []


def test_all_registered_overkill_hooks_have_non_unknown_island_classification():
    from pathlib import Path

    from overkill_port.coverage import OverkillCoverageClassifier
    from overkill_port.hooks import registry
    import overkill_port.replacements  # noqa: F401  # registers hooks

    classifier = OverkillCoverageClassifier(Path("symbols.json"))
    unknown = [
        (addr, repl.name)
        for addr, repl in sorted(registry.replacements.items())
        if classifier.classify(addr, repl.name) == "unknown"
    ]
    assert unknown == []


def test_cold_start_frontier_manifest_classifies_same_ip_and_bootstrap_leftovers():
    from overkill_port.games.overkill.frontier_manifest import FRONTIER_BY_ADDR, FrontierCategory

    assert FRONTIER_BY_ADDR[(0x1010, 0xD007)].category is FrontierCategory.FINAL_ORCHESTRATOR
    assert FRONTIER_BY_ADDR[(0x1010, 0xD03E)].category is FrontierCategory.SAME_IP_LOOP_GATE
    assert FRONTIER_BY_ADDR[(0x32FF, 0x0052)].category is FrontierCategory.DO_NOT_HOOK_BOOTSTRAP
    assert FRONTIER_BY_ADDR[(0x1010, 0xD03E)].owner == (0x1010, 0xD007)
