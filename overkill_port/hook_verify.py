from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable

from .cpu import CPU8086, CPUState
from .dos import DOSMachine, FileHandle
from .memory import (
    EGA_APERTURE,
    EGA_PLANE_STRIDE,
    EGA_SHADOW_SIZE,
    Memory,
    linear,
)
from .runtime import Runtime


Addr = tuple[int, int]


class HookVerifyDivergence(RuntimeError):
    pass


class HookVerifyLimitReached(RuntimeError):
    pass


@dataclass(frozen=True)
class HookStop:
    kind: str
    ip: int | None = None
    ips: tuple[int, ...] = ()

    def targets(self, cpu: CPU8086, before: CPUState) -> tuple[Addr, ...]:
        cs = before.cs & 0xFFFF
        if self.kind == "near_ret":
            return ((cs, cpu.mem.rw(before.ss, before.sp)),)
        if self.kind == "far_ret":
            return ((cpu.mem.rw(before.ss, (before.sp + 2) & 0xFFFF), cpu.mem.rw(before.ss, before.sp)),)
        if self.kind == "fixed_ip":
            if self.ip is None:
                raise ValueError("fixed_ip hook metadata needs ip")
            return ((cs, self.ip & 0xFFFF),)
        if self.kind == "fixed_ips":
            return tuple((cs, ip & 0xFFFF) for ip in self.ips)
        if self.kind == "ega_2824":
            outer = cpu.mem.rw(before.ss, before.sp)
            return ((cs, 0x27EB if outer > 1 else 0x27D9),)
        if self.kind == "dispatch_5a00":
            mode = cpu.mem.rw(cs, 0x95BC)
            if mode in (0, 1, 2):  # CGA + EGA + Tandy coordinate targets are fully hooked.
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            bx = ((mode & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5A0C + bx) & 0xFFFF)),)
        if self.kind == "dispatch_5a24":
            mode = cpu.mem.rw(cs, 0x95BC)
            if mode in (0, 1, 2):  # CGA + EGA + Tandy coordinate targets are fully hooked.
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            bx = ((mode & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5A30 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_5a36":
            mode = cpu.mem.rw(cs, 0x95BC)
            if mode in (0, 1, 2):
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            bx = ((mode & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5A42 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_5ac8":
            mode = cpu.mem.rw(cs, 0x95BC)
            obj_type = cpu.mem.rw(before.ss, (before.bp + 0x14) & 0xFFFF)
            bx = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5AE2 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_5a92":
            mode = cpu.mem.rw(cs, 0x95BC)
            obj_type = cpu.mem.rw(before.ss, (before.bp + 0x14) & 0xFFFF)
            bx = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5AB6 + bx) & 0xFFFF)),)
        if self.kind in ("scan_present_a927", "scan_present_a90f"):
            cx = before.cx & 0xFFFF
            if cx == 0:
                cx = 0x10000
            ds = before.ds & 0xFFFF
            ss = before.ss & 0xFFFF
            table_base = 0x8D12 if self.kind == "scan_present_a90f" else 0x32CA
            call_ip = 0xA91E if self.kind == "scan_present_a90f" else 0xA936
            done_ip = 0xA924 if self.kind == "scan_present_a90f" else 0xA93C
            while cx:
                bx = ((cx & 0xFFFF) << 1) & 0xFFFF
                bp = cpu.mem.rw(ds, (table_base + bx) & 0xFFFF)
                if cpu.mem.rw(ss, bp & 0xFFFF) != 0:
                    return ((cs, call_ip),)
                cx = (cx - 1) & 0xFFFF
                if cx == 0:
                    break
            return ((cs, done_ip),)
        if self.kind == "scan_draw_a849":
            cx = before.cx & 0xFFFF
            if cx == 0:
                cx = 0x10000
            ds = before.ds & 0xFFFF
            ss = before.ss & 0xFFFF
            while cx:
                bx = ((cx & 0xFFFF) << 1) & 0xFFFF
                bp = cpu.mem.rw(ds, (0x32CA + bx) & 0xFFFF)
                if cpu.mem.rw(ss, bp & 0xFFFF) != 0:
                    return ((cs, 0xA858),)
                cx = (cx - 1) & 0xFFFF
                if cx == 0:
                    break
            return ((cs, 0xA85E),)
        if self.kind == "tandy_layer_sprite_768e":
            ss = before.ss & 0xFFFF
            bp = before.bp & 0xFFFF
            di = cpu.mem.rw(ss, (bp + 0x0C) & 0xFFFF)
            if di == 0xFFFF:
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            bx = cpu.mem.rw(ss, (bp + 0x08) & 0xFFFF)
            if bx >= 0x00FA:
                bx = (bx - 0x00FA) & 0xFFFF
            bx = ((bx << 1) + 0x9192) & 0xFFFF
            mode = cpu.mem.rw(cs, 0x95BC)
            dispatch = (mode << 3) & 0xFFFF
            dispatch = (dispatch + cpu.mem.rw(ss, (bp + 0x12) & 0xFFFF)) & 0xFFFF
            table = 0x7716
            if cpu.mem.rw(ss, (bp + 0x24) & 0xFFFF) == 0:
                table = 0x76E6
            target = cpu.mem.rw(cs, (table + ((dispatch << 1) & 0xFFFF)) & 0xFFFF)
            if target in (
                0x103C, 0x10B7, 0x1AEB, 0x1D1B,
                0x2193, 0x21D6, 0x2223, 0x2285, 0x22FC,
                0x238D, 0x2410, 0x247E,
                0x3849, 0x387C, 0x38B7, 0x38D6, 0x38F9, 0x390E,
                0x409D, 0x40D7, 0x412B,
                0x2F81, 0x2F40, 0x2ECB, 0x2E6E, 0x2FB6,
            ):
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            return ((cs, target),)
        if self.kind == "scan_layer1_a8c7":
            cx = before.cx & 0xFFFF
            if cx == 0:
                cx = 0x10000
            ds = before.ds & 0xFFFF
            ss = before.ss & 0xFFFF
            while cx:
                bx = ((cx & 0xFFFF) << 1) & 0xFFFF
                bp = cpu.mem.rw(ds, (0x32CA + bx) & 0xFFFF)
                if cpu.mem.rw(ss, bp & 0xFFFF) != 0:
                    should_call = True
                    mode = cpu.mem.rw(ds, 0xBDAC)
                    if mode != 1:
                        camera = cpu.mem.rw(ds, 0x2350)
                        if camera <= 0x00B6:
                            layer = cpu.mem.rw(ss, (bp + 0x16) & 0xFFFF)
                            if layer == 1:
                                should_call = False
                    if should_call and cpu.mem.rw(ss, (bp + 0x0A) & 0xFFFF) == 1:
                        return ((cs, 0xA8F1),)
                cx = (cx - 1) & 0xFFFF
                if cx == 0:
                    break
            return ((cs, 0xA8F7),)
        if self.kind == "dispatch_aa2b":
            obj_kind = cpu.mem.rw(before.ss, (before.bp + 0x16) & 0xFFFF)
            bx = ((obj_kind & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0xAA36 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_efae":
            logic_id = cpu.mem.rw(before.ss, (before.bp + 0x18) & 0xFFFF)
            bx = ((logic_id & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0xEFC4 + bx) & 0xFFFF)),)
        raise ValueError(f"unknown hook stop kind {self.kind!r}")


@dataclass
class MemoryRange:
    name: str
    start: int
    size: int


@dataclass
class HookVerifierConfig:
    verify_all: bool = False
    hooks: set[Addr] = field(default_factory=set)
    max_verified: int | None = None
    stop_on_diff: bool = False
    log_diffs: bool = False
    asm_max_steps: int = 500_000
    full_memory: bool = False
    require_metadata: bool = False


DEFAULT_STOPS: dict[Addr, HookStop] = {
    (0x1010, 0x017E): HookStop("fixed_ip", 0x018B),
    (0x254A, 0x05A1): HookStop("fixed_ips", ips=(0x0607, 0x0640)),
    (0x254A, 0x05D9): HookStop("fixed_ips", ips=(0x0607, 0x0637)),
    (0x254A, 0x05BF): HookStop("fixed_ip", 0x05C6),
    (0x254A, 0x0582): HookStop("fixed_ips", ips=(0x058D, 0x0640)),
    (0x254A, 0x0701): HookStop("far_ret"),
    (0x1010, 0x0324): HookStop("fixed_ips", ips=(0x02A8, 0x02B2)),
    (0x1010, 0x0367): HookStop("fixed_ips", ips=(0x02A8, 0x02B2)),
    (0x1010, 0x03A8): HookStop("fixed_ips", ips=(0x02A8, 0x02B2)),
    (0x1010, 0x0615): HookStop("near_ret"),
    (0x1010, 0x0624): HookStop("near_ret"),
    (0x1010, 0x103C): HookStop("near_ret"),
    (0x1010, 0x10B7): HookStop("near_ret"),
    (0x1010, 0x2193): HookStop("near_ret"),
    (0x1010, 0x21D6): HookStop("near_ret"),
    (0x1010, 0x238D): HookStop("near_ret"),
    (0x1010, 0x2410): HookStop("near_ret"),
    (0x1010, 0x247E): HookStop("near_ret"),
    (0x1010, 0x2223): HookStop("near_ret"),
    (0x1010, 0x2285): HookStop("near_ret"),
    (0x1010, 0x22FC): HookStop("near_ret"),
    (0x1010, 0x1AEB): HookStop("near_ret"),
    (0x1010, 0x75A6): HookStop("near_ret"),
    (0x1010, 0xB73E): HookStop("near_ret"),
    (0x1010, 0x13E7): HookStop("near_ret"),
    (0x1010, 0x1D1B): HookStop("near_ret"),
    (0x1010, 0x2750): HookStop("near_ret"),
    (0x1010, 0x29C6): HookStop("near_ret"),
    (0x1010, 0x2AB9): HookStop("near_ret"),
    (0x1010, 0x27EB): HookStop("fixed_ip", 0x27D9),
    (0x1010, 0x280D): HookStop("fixed_ip", 0x2824),
    (0x1010, 0x2824): HookStop("ega_2824"),
    (0x1010, 0x291C): HookStop("near_ret"),
    (0x1010, 0x2932): HookStop("near_ret"),
    (0x1010, 0x2E6E): HookStop("near_ret"),
    (0x1010, 0x2ECB): HookStop("near_ret"),
    (0x1010, 0x2F40): HookStop("near_ret"),
    (0x1010, 0x2F81): HookStop("near_ret"),
    (0x1010, 0x2FB6): HookStop("near_ret"),
    (0x1010, 0x33B2): HookStop("fixed_ips", ips=(0x33AF, 0x44AA)),
    (0x1010, 0x3354): HookStop("near_ret"),
    (0x1010, 0x33DD): HookStop("near_ret"),
    (0x1010, 0x34AD): HookStop("near_ret"),
    (0x1010, 0x34C5): HookStop("near_ret"),
    (0x1010, 0x34D8): HookStop("near_ret"),
    (0x1010, 0x3542): HookStop("near_ret"),
    (0x1010, 0x356C): HookStop("near_ret"),
    (0x1010, 0x375B): HookStop("near_ret"),
    (0x1010, 0x35AA): HookStop("near_ret"),
    (0x1010, 0x35CC): HookStop("near_ret"),
    (0x1010, 0x3657): HookStop("near_ret"),
    (0x1010, 0x3849): HookStop("near_ret"),
    (0x1010, 0x387C): HookStop("near_ret"),
    (0x1010, 0x38D6): HookStop("near_ret"),
    (0x1010, 0x390E): HookStop("near_ret"),
    (0x1010, 0x38B7): HookStop("near_ret"),
    (0x1010, 0x38F9): HookStop("near_ret"),
    (0x1010, 0x409D): HookStop("near_ret"),
    (0x1010, 0x40D7): HookStop("near_ret"),
    (0x1010, 0x412B): HookStop("near_ret"),
    (0x1010, 0x450C): HookStop("fixed_ips", ips=(0x450C, 0x44AA)),
    (0x1010, 0x4511): HookStop("fixed_ip", 0x450C),
    (0x1010, 0x4537): HookStop("near_ret"),
    (0x1010, 0x45CB): HookStop("near_ret"),
    (0x1010, 0x45F6): HookStop("near_ret"),
    (0x1010, 0xC916): HookStop("fixed_ip", 0xC91F),
    (0x1010, 0xECF2): HookStop("near_ret"),
    (0x1010, 0xED7A): HookStop("fixed_ip", 0xED26),
    (0x1010, 0xED97): HookStop("near_ret"),
    (0x1010, 0xEDE9): HookStop("near_ret"),
    (0x1010, 0xCCAA): HookStop("fixed_ip", 0xCD08),
    (0x1010, 0xCCC4): HookStop("fixed_ip", 0xCD08),
    (0x1010, 0xCCF0): HookStop("fixed_ip", 0xCD08),
    (0x1010, 0x4D15): HookStop("near_ret"),
    (0x1010, 0x4D6F): HookStop("near_ret"),
    (0x1010, 0x5827): HookStop("fixed_ip", 0x58A4),
    (0x1010, 0x5A00): HookStop("dispatch_5a00"),
    (0x1010, 0x5A24): HookStop("dispatch_5a24"),
    (0x1010, 0x5A36): HookStop("dispatch_5a36"),
    (0x1010, 0x5AC8): HookStop("dispatch_5ac8"),
    (0x1010, 0x5A92): HookStop("dispatch_5a92"),
    (0x1010, 0x768E): HookStop("tandy_layer_sprite_768e"),
    (0x1010, 0x7746): HookStop("near_ret"),
    (0x1010, 0xA849): HookStop("scan_draw_a849"),
    (0x1010, 0xA861): HookStop("fixed_ips", ips=(0xA870, 0xA876)),
    (0x1010, 0xA87C): HookStop("fixed_ips", ips=(0xA88B, 0xA891)),
    (0x1010, 0xA894): HookStop("fixed_ips", ips=(0xA8BE, 0xA8C4)),
    (0x1010, 0xA8C7): HookStop("scan_layer1_a8c7"),
    (0x1010, 0xA90F): HookStop("scan_present_a90f"),
    (0x1010, 0xA927): HookStop("scan_present_a927"),
    (0x1010, 0xA9E0): HookStop("fixed_ips", ips=(0xAA01, 0xAA07)),
    (0x1010, 0xAA2B): HookStop("dispatch_aa2b"),
    (0x1010, 0xAA10): HookStop("fixed_ips", ips=(0xAA1F, 0xAA25)),
    (0x1010, 0xEFAE): HookStop("dispatch_efae"),
}


def parse_addr(text: str) -> Addr:
    cs, ip = text.split(":", 1)
    return int(cs, 16) & 0xFFFF, int(ip, 16) & 0xFFFF


def install_hook_verifier(rt: Runtime, config: HookVerifierConfig) -> "HookVerifier":
    verifier = HookVerifier(rt, config)
    rt.cpu.hook_verifier = verifier.verify
    return verifier


class HookVerifier:
    def __init__(self, rt: Runtime, config: HookVerifierConfig) -> None:
        self.rt = rt
        self.config = config
        self.counts: dict[Addr, int] = {}
        self.total_verified = 0
        self.skipped: set[Addr] = set()

    def verify(self, cpu: CPU8086, key: Addr, handler: Callable[[CPU8086], None], name: str) -> None:
        if not self._should_verify(key):
            handler(cpu)
            return

        stop = DEFAULT_STOPS.get(key)
        if stop is None:
            msg = f"HOOK VERIFY MISSING METADATA {key[0]:04X}:{key[1]:04X} {name}: no continuation metadata"
            if self.config.require_metadata:
                raise HookVerifyDivergence(msg)
            if key not in self.skipped:
                print(msg.replace("MISSING METADATA", "SKIP"))
                self.skipped.add(key)
            handler(cpu)
            return

        call_no = self.counts.get(key, 0) + 1
        self.counts[key] = call_no
        before = CPUState(**cpu.s.__dict__)
        asm_rt = self._clone_runtime()
        asm_cpu = asm_rt.cpu
        asm_cpu.hook_verifier = None
        asm_cpu.replacement_hooks.pop(key, None)
        asm_cpu.hook_names.pop(key, None)
        targets = stop.targets(asm_cpu, before)

        asm_steps = self._run_asm_to_target(asm_cpu, targets)
        handler(cpu)
        self.total_verified += 1

        report = self._diff_report(
            key=key,
            name=name,
            call_no=call_no,
            targets=targets,
            asm_rt=asm_rt,
            hook_rt=self.rt,
            asm_steps=asm_steps,
        )
        if report:
            if self.config.log_diffs or self.config.stop_on_diff:
                print(report)
            if self.config.stop_on_diff:
                raise HookVerifyDivergence(report)
        if self.config.max_verified is not None and self.total_verified >= self.config.max_verified:
            raise HookVerifyLimitReached(f"HOOK VERIFY LIMIT REACHED verified={self.total_verified}")

    def _should_verify(self, key: Addr) -> bool:
        if self.config.max_verified is not None and self.total_verified >= self.config.max_verified:
            return False
        return self.config.verify_all or key in self.config.hooks

    def _run_asm_to_target(self, cpu: CPU8086, targets: tuple[Addr, ...]) -> int:
        target_set = set(targets)
        for steps in range(self.config.asm_max_steps + 1):
            if cpu.addr() in target_set:
                return steps
            cpu.step()
        labels = ", ".join(f"{cs:04X}:{ip:04X}" for cs, ip in targets)
        raise HookVerifyDivergence(
            f"HOOK VERIFY ASM TIMEOUT target={labels} "
            f"at={cpu.s.cs:04X}:{cpu.s.ip:04X}"
        )

    def _clone_runtime(self) -> Runtime:
        src = self.rt
        mem = Memory()
        mem.data[:] = src.program.memory.data
        mem.ega_planar = src.program.memory.ega_planar
        mem.ega_map_mask = src.program.memory.ega_map_mask
        mem.ega_read_plane = src.program.memory.ega_read_plane
        mem.ega_display_start = src.program.memory.ega_display_start

        dos = DOSMachine(src.dos.root)
        dos.stdout = list(src.dos.stdout)
        dos.files = {
            handle: FileHandle(f.path, bytearray(f.data), f.pos, f.writable)
            for handle, f in src.dos.files.items()
        }
        dos.next_handle = src.dos.next_handle
        dos.next_alloc_segment = src.dos.next_alloc_segment
        dos.allocation_limit_segment = src.dos.allocation_limit_segment
        dos.allocations = dict(src.dos.allocations)
        dos.video_mode = src.dos.video_mode
        dos.ticks = src.dos.ticks
        dos.vga_status_reads = src.dos.vga_status_reads
        dos._seq_index = getattr(src.dos, "_seq_index", 0)
        dos._crtc_index = getattr(src.dos, "_crtc_index", 0)
        dos.current_scancode = src.dos.current_scancode
        dos.key_queue = list(src.dos.key_queue)
        dos.port_log = list(src.dos.port_log)

        cpu = CPU8086(mem, CPUState(**src.cpu.s.__dict__))
        cpu.halted = src.cpu.halted
        cpu.trace_enabled = False
        cpu.call_depth = src.cpu.call_depth
        cpu.instruction_count = src.cpu.instruction_count
        cpu.max_rep_count = src.cpu.max_rep_count
        cpu.replacement_hooks = dict(src.cpu.replacement_hooks)
        cpu.hook_names = dict(src.cpu.hook_names)
        cpu.interrupt_handler = dos.interrupt
        cpu.port_reader = dos.port_read
        cpu.port_writer = dos.port_write

        program = copy.copy(src.program)
        program.memory = mem
        return Runtime(program, cpu, dos)

    def _memory_ranges(self, rt: Runtime) -> list[MemoryRange]:
        if self.config.full_memory:
            return [MemoryRange("full memory", 0, len(rt.program.memory.data))]

        s = rt.cpu.s
        ranges = [
            MemoryRange("CS:0000-FFFF", linear(s.cs, 0), 0x10000),
            MemoryRange("CPU A000:0000-FFFF", 0xA0000, 0x10000),
            MemoryRange("CPU B800:0000-7FFF", 0xB8000, 0x8000),
            MemoryRange("EGA shadow planes", EGA_APERTURE, EGA_SHADOW_SIZE),
            MemoryRange("CS:5B00-5BFF temp rows", linear(s.cs, 0x5B00), 0x0100),
        ]
        sp = s.sp & 0xFFFF
        stack_start = (sp - 0x40) & 0xFFFF
        if stack_start + 0x100 <= 0x10000:
            ranges.append(MemoryRange("stack around SS:SP", linear(s.ss, stack_start), 0x100))
        return ranges

    def _diff_report(
        self,
        *,
        key: Addr,
        name: str,
        call_no: int,
        targets: tuple[Addr, ...],
        asm_rt: Runtime,
        hook_rt: Runtime,
        asm_steps: int,
    ) -> str | None:
        sections: list[str] = []
        asm_cpu = asm_rt.cpu
        hook_cpu = hook_rt.cpu

        if asm_cpu.addr() != hook_cpu.addr():
            sections.append(
                "Continuation differences:\n"
                f"  ASM:  {asm_cpu.s.cs:04X}:{asm_cpu.s.ip:04X}\n"
                f"  HOOK: {hook_cpu.s.cs:04X}:{hook_cpu.s.ip:04X}"
            )

        reg_lines = []
        for field in ("ax", "bx", "cx", "dx", "si", "di", "bp", "sp"):
            av = getattr(asm_cpu.s, field) & 0xFFFF
            hv = getattr(hook_cpu.s, field) & 0xFFFF
            if av != hv:
                reg_lines.append(f"  {field.upper()}: asm={av:04X} hook={hv:04X}")
        if reg_lines:
            sections.append("Register differences:\n" + "\n".join(reg_lines))

        seg_lines = []
        for field in ("cs", "ds", "es", "ss"):
            av = getattr(asm_cpu.s, field) & 0xFFFF
            hv = getattr(hook_cpu.s, field) & 0xFFFF
            if av != hv:
                seg_lines.append(f"  {field.upper()}: asm={av:04X} hook={hv:04X}")
        if seg_lines:
            sections.append("Segment differences:\n" + "\n".join(seg_lines))

        if (asm_cpu.s.flags & 0x0FFF) != (hook_cpu.s.flags & 0x0FFF):
            sections.append(f"Flag differences:\n  FLAGS: asm={asm_cpu.s.flags & 0x0FFF:04X} hook={hook_cpu.s.flags & 0x0FFF:04X}")

        dos_lines = self._dos_diff(asm_rt, hook_rt)
        if dos_lines:
            sections.append("DOS/state differences:\n" + "\n".join(dos_lines))

        mem_sections = []
        for rng in self._memory_ranges(hook_rt):
            diff = self._range_diff(asm_rt.program.memory.data, hook_rt.program.memory.data, rng)
            if diff is not None:
                mem_sections.append(diff)
        if mem_sections:
            sections.append("Memory differences:\n" + "\n".join(mem_sections))

        if not sections:
            return None

        mode = asm_rt.program.memory.rw(asm_cpu.s.cs, 0x95BC)
        header = [
            "HOOK VERIFY DIVERGENCE",
            f"hook: {key[0]:04X}:{key[1]:04X} {name}",
            f"call: {call_no}",
            f"video: {self._video_name(mode)} ({mode:04X})",
            f"expected continuation: {self._format_targets(targets)}",
            f"ASM continuation: {asm_cpu.s.cs:04X}:{asm_cpu.s.ip:04X} after {asm_steps} steps",
            f"HOOK continuation: {hook_cpu.s.cs:04X}:{hook_cpu.s.ip:04X}",
        ]
        return "\n".join(header + ["", *sections])

    @staticmethod
    def _format_targets(targets: tuple[Addr, ...]) -> str:
        return ", ".join(f"{cs:04X}:{ip:04X}" for cs, ip in targets)

    def _dos_diff(self, asm_rt: Runtime, hook_rt: Runtime) -> list[str]:
        lines = []
        if asm_rt.dos.vga_status_reads != hook_rt.dos.vga_status_reads:
            lines.append(f"  vga_status_reads: asm={asm_rt.dos.vga_status_reads} hook={hook_rt.dos.vga_status_reads}")
        if asm_rt.program.memory.ega_map_mask != hook_rt.program.memory.ega_map_mask:
            lines.append(f"  ega_map_mask: asm={asm_rt.program.memory.ega_map_mask:02X} hook={hook_rt.program.memory.ega_map_mask:02X}")
        if asm_rt.program.memory.ega_read_plane != hook_rt.program.memory.ega_read_plane:
            lines.append(f"  ega_read_plane: asm={asm_rt.program.memory.ega_read_plane} hook={hook_rt.program.memory.ega_read_plane}")
        if asm_rt.program.memory.ega_display_start != hook_rt.program.memory.ega_display_start:
            lines.append(
                f"  ega_display_start: asm={asm_rt.program.memory.ega_display_start:04X} "
                f"hook={hook_rt.program.memory.ega_display_start:04X}"
            )
        asm_files = {h: f.pos for h, f in asm_rt.dos.files.items()}
        hook_files = {h: f.pos for h, f in hook_rt.dos.files.items()}
        if asm_files != hook_files:
            lines.append(f"  file offsets: asm={asm_files} hook={hook_files}")
        return lines

    def _range_diff(self, asm: bytearray, hook: bytearray, rng: MemoryRange) -> str | None:
        start = max(0, rng.start)
        end = min(len(asm), len(hook), start + rng.size)
        first = None
        count = 0
        for addr in range(start, end):
            if asm[addr] != hook[addr]:
                count += 1
                if first is None:
                    first = addr
        if first is None:
            return None
        dump_start = max(start, first - 8)
        dump_end = min(end, first + 16)
        asm_hex = " ".join(f"{b:02X}" for b in asm[dump_start:dump_end])
        hook_hex = " ".join(f"{b:02X}" for b in hook[dump_start:dump_end])
        return (
            f"  range {rng.name}:\n"
            f"    differing bytes: {count}\n"
            f"    first diff: {first:05X} asm={asm[first]:02X} hook={hook[first]:02X}\n"
            f"    asm : {asm_hex}\n"
            f"    hook: {hook_hex}"
        )

    @staticmethod
    def _video_name(mode: int) -> str:
        return {0: "cga", 1: "ega", 2: "tandy"}.get(mode & 0xFFFF, "unknown")
