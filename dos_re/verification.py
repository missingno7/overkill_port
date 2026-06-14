from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .cpu import CPU8086, CPUState
from .dos import DOSMachine, FileHandle
from .memory import (
    EGA_APERTURE,
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


class StopRule(Protocol):
    min_steps: int

    def targets(self, cpu: CPU8086, before: CPUState) -> tuple[Addr, ...]: ...


@dataclass(frozen=True)
class GenericHookStop:
    kind: str
    ip: int | None = None
    ips: tuple[int, ...] = ()
    min_steps: int = 0

    @classmethod
    def after_step(cls, kind: str, ip: int | None = None, ips: tuple[int, ...] = ()) -> "GenericHookStop":
        return cls(kind, ip=ip, ips=ips, min_steps=1)

    def targets(self, cpu: CPU8086, before: CPUState) -> tuple[Addr, ...]:
        cs = before.cs & 0xFFFF
        if self.kind == "near_ret":
            return ((cs, cpu.mem.rw(before.ss, before.sp)),)
        if self.kind == "near_ret_or_fixed_ip":
            if self.ip is None:
                raise ValueError("near_ret_or_fixed_ip hook metadata needs ip")
            return ((cs, cpu.mem.rw(before.ss, before.sp)), (cs, self.ip & 0xFFFF))
        if self.kind == "near_ret_or_fixed_ips":
            return ((cs, cpu.mem.rw(before.ss, before.sp)),) + tuple((cs, ip & 0xFFFF) for ip in self.ips)
        if self.kind == "far_ret":
            return ((cpu.mem.rw(before.ss, (before.sp + 2) & 0xFFFF), cpu.mem.rw(before.ss, before.sp)),)
        if self.kind == "iret":
            return ((cpu.mem.rw(before.ss, (before.sp + 2) & 0xFFFF), cpu.mem.rw(before.ss, before.sp)),)
        if self.kind == "fixed_ip":
            if self.ip is None:
                raise ValueError("fixed_ip hook metadata needs ip")
            return ((cs, self.ip & 0xFFFF),)
        if self.kind == "fixed_ips":
            return tuple((cs, ip & 0xFFFF) for ip in self.ips)
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
    full_memory: bool = True
    require_metadata: bool = False
    progress_callback: Callable[[str], None] | None = None


def parse_addr(text: str) -> Addr:
    cs, ip = text.split(":", 1)
    return int(cs, 16) & 0xFFFF, int(ip, 16) & 0xFFFF


def install_hook_verifier(
    rt: Runtime,
    config: HookVerifierConfig,
    stops: dict[Addr, StopRule],
    *,
    asm_wait_handler: Callable[[CPU8086, set[Addr]], bool] | None = None,
    context_lines: Callable[[Runtime], list[str]] | None = None,
) -> "HookVerifier":
    verifier = HookVerifier(
        rt,
        config,
        stops,
        asm_wait_handler=asm_wait_handler,
        context_lines=context_lines,
    )
    rt.cpu.hook_verifier = verifier.verify
    return verifier


class HookVerifier:
    def __init__(
        self,
        rt: Runtime,
        config: HookVerifierConfig,
        stops: dict[Addr, StopRule],
        *,
        asm_wait_handler: Callable[[CPU8086, set[Addr]], bool] | None = None,
        context_lines: Callable[[Runtime], list[str]] | None = None,
    ) -> None:
        self.rt = rt
        self.config = config
        self.stops = stops
        self._asm_wait_handler = asm_wait_handler
        self._context_lines = context_lines or (lambda _rt: [])
        # Keep the hook table as it looked when verification was installed.
        # scripts/play.py installs UI pacing wrappers for a few hardware/boundary
        # hooks (50C9 retrace wait, 0679 timer wait, present blits) after creating
        # the verifier.  Those wrappers sleep, publish frames and raise control-flow
        # exceptions, which is correct for interactive execution but wrong inside a
        # differential hook transaction.  During verification, any hook listed in
        # cpu.hook_verifier_passthrough is restored from this table on both the
        # ASM oracle clone and the live hook side, so nested CALLs see the pure
        # environment hook instead of the UI wrapper.
        self._install_time_hooks = dict(rt.cpu.replacement_hooks)
        self._install_time_names = dict(rt.cpu.hook_names)
        self.counts: dict[Addr, int] = {}
        self.total_verified = 0
        self.skipped: set[Addr] = set()

    def verify(self, cpu: CPU8086, key: Addr, handler: Callable[[CPU8086], None], name: str) -> None:
        if not self._should_verify(key):
            try:
                handler(cpu)
            finally:
                if cpu.coverage_telemetry is not None:
                    cpu.coverage_telemetry.record_hook_unverified(key, name)
            return

        stop = self.stops.get(key)
        if stop is None:
            msg = f"HOOK VERIFY MISSING METADATA {key[0]:04X}:{key[1]:04X} {name}: no continuation metadata"
            if self.config.require_metadata:
                raise HookVerifyDivergence(msg)
            if key not in self.skipped:
                print(msg.replace("MISSING METADATA", "SKIP"))
                self.skipped.add(key)
            try:
                handler(cpu)
            finally:
                if cpu.coverage_telemetry is not None:
                    cpu.coverage_telemetry.record_hook_skipped(key, name)
            return

        call_no = self.counts.get(key, 0) + 1
        self.counts[key] = call_no
        before = CPUState(**cpu.s.__dict__)
        if self.config.progress_callback is not None:
            self.config.progress_callback(f"verifying {key[0]:04X}:{key[1]:04X} {name} call {call_no}")
        asm_rt = self._clone_runtime()
        asm_cpu = asm_rt.cpu
        asm_cpu.hook_verifier = None
        asm_cpu.replacement_hooks.pop(key, None)
        asm_cpu.hook_names.pop(key, None)
        targets = stop.targets(asm_cpu, before)

        self._restore_passthrough_hooks(asm_cpu)
        asm_steps = self._run_asm_to_target(asm_cpu, targets, min_steps=stop.min_steps)
        with self._live_passthrough_hooks(cpu):
            handler(cpu)
        self.total_verified += 1
        if cpu.coverage_telemetry is not None:
            cpu.coverage_telemetry.record_hook_verified(key, name, asm_steps)

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

    def _restore_passthrough_hooks(self, cpu: CPU8086) -> None:
        """Replace interactive passthrough wrappers with install-time base hooks.

        The pass-through set is owned by the live CPU and may be populated after
        this verifier is constructed.  That is intentional: play.py knows which
        hooks are UI pacing boundaries only after it has chosen the active video
        backend.
        """
        for key in getattr(cpu, "hook_verifier_passthrough", set()):
            if key in self._install_time_hooks:
                cpu.replacement_hooks[key] = self._install_time_hooks[key]
                if key in self._install_time_names:
                    cpu.hook_names[key] = self._install_time_names[key]
            else:
                cpu.replacement_hooks.pop(key, None)
                cpu.hook_names.pop(key, None)

    class _LivePassthroughHooks:
        def __init__(self, verifier: "HookVerifier", cpu: CPU8086) -> None:
            self.verifier = verifier
            self.cpu = cpu
            self.saved_hooks: dict[Addr, Callable[[CPU8086], None] | None] = {}
            self.saved_names: dict[Addr, str | None] = {}

        def __enter__(self) -> None:
            for key in getattr(self.cpu, "hook_verifier_passthrough", set()):
                self.saved_hooks[key] = self.cpu.replacement_hooks.get(key)
                self.saved_names[key] = self.cpu.hook_names.get(key)
                if key in self.verifier._install_time_hooks:
                    self.cpu.replacement_hooks[key] = self.verifier._install_time_hooks[key]
                    if key in self.verifier._install_time_names:
                        self.cpu.hook_names[key] = self.verifier._install_time_names[key]
                else:
                    self.cpu.replacement_hooks.pop(key, None)
                    self.cpu.hook_names.pop(key, None)

        def __exit__(self, exc_type, exc, tb) -> bool:
            for key, hook in self.saved_hooks.items():
                if hook is None:
                    self.cpu.replacement_hooks.pop(key, None)
                else:
                    self.cpu.replacement_hooks[key] = hook
            for key, name in self.saved_names.items():
                if name is None:
                    self.cpu.hook_names.pop(key, None)
                else:
                    self.cpu.hook_names[key] = name
            return False

    def _live_passthrough_hooks(self, cpu: CPU8086) -> "HookVerifier._LivePassthroughHooks":
        return HookVerifier._LivePassthroughHooks(self, cpu)

    def _run_asm_to_target(self, cpu: CPU8086, targets: tuple[Addr, ...], *, min_steps: int = 0) -> int:
        target_set = set(targets)
        min_steps = max(0, int(min_steps))
        for steps in range(self.config.asm_max_steps + 1):
            if steps >= min_steps and cpu.addr() in target_set:
                return steps
            if self._asm_wait_handler is not None and self._asm_wait_handler(cpu, target_set):
                if steps >= min_steps and cpu.addr() in target_set:
                    return steps
                continue
            cpu.step()
        labels = ", ".join(f"{cs:04X}:{ip:04X}" for cs, ip in targets)
        raise HookVerifyDivergence(
            f"HOOK VERIFY ASM TIMEOUT target={labels} "
            f"at={cpu.s.cs:04X}:{cpu.s.ip:04X}"
        )

    def _clone_runtime(self) -> Runtime:
        src = self.rt
        mem = Memory(0)
        mem.data = src.program.memory.data.copy()
        mem.size = src.program.memory.size
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
        dos.video_page = src.dos.video_page
        dos.text_mode_active = src.dos.text_mode_active
        dos.cursor_row = src.dos.cursor_row
        dos.cursor_col = src.dos.cursor_col
        dos.ticks = src.dos.ticks
        dos.vga_status_reads = src.dos.vga_status_reads
        dos._pit_channel2_access = getattr(src.dos, "_pit_channel2_access", 3)
        dos._pit_channel2_latch = getattr(src.dos, "_pit_channel2_latch", 0)
        dos._pit_channel2_write_low = getattr(src.dos, "_pit_channel2_write_low", True)
        dos.pit_channel2_reload = src.dos.pit_channel2_reload
        dos.speaker_control = src.dos.speaker_control
        dos.opl_selected_register = getattr(src.dos, "opl_selected_register", 0)
        dos.opl_status = getattr(src.dos, "opl_status", 0)
        dos.opl_registers = dict(getattr(src.dos, "opl_registers", {}))
        dos._seq_index = getattr(src.dos, "_seq_index", 0)
        dos._crtc_index = getattr(src.dos, "_crtc_index", 0)
        dos.current_scancode = src.dos.current_scancode
        dos.console_input_fallback = src.dos.console_input_fallback
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
        cpu.hook_verifier_passthrough = set(src.cpu.hook_verifier_passthrough)
        self._restore_passthrough_hooks(cpu)
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
        ranges = []

        def add_range(name: str, start: int, size: int) -> None:
            start = max(0, start)
            size = max(0, size)
            if any(existing.start == start and existing.size == size for existing in ranges):
                return
            ranges.append(MemoryRange(name, start, size))

        add_range("CS:0000-FFFF", linear(s.cs, 0), 0x10000)
        add_range("DS:0000-FFFF", linear(s.ds, 0), 0x10000)
        add_range("SS:0000-FFFF", linear(s.ss, 0), 0x10000)
        add_range("CPU A000:0000-FFFF", 0xA0000, 0x10000)
        add_range("CPU B800:0000-7FFF", 0xB8000, 0x8000)
        add_range("EGA shadow planes", EGA_APERTURE, EGA_SHADOW_SIZE)
        add_range("CS:5B00-5BFF temp rows", linear(s.cs, 0x5B00), 0x0100)
        sp = s.sp & 0xFFFF
        stack_start = (sp - 0x40) & 0xFFFF
        if stack_start + 0x100 <= 0x10000:
            add_range("stack around SS:SP", linear(s.ss, stack_start), 0x100)
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

        header = [
            "HOOK VERIFY DIVERGENCE",
            f"hook: {key[0]:04X}:{key[1]:04X} {name}",
            f"call: {call_no}",
            *self._context_lines(asm_rt),
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
        for field in (
            "next_handle",
            "next_alloc_segment",
            "allocation_limit_segment",
            "video_mode",
            "video_page",
            "text_mode_active",
            "cursor_row",
            "cursor_col",
            "ticks",
            "vga_status_reads",
            "_seq_index",
            "_crtc_index",
            "current_scancode",
            "console_input_fallback",
        ):
            av = getattr(asm_rt.dos, field)
            hv = getattr(hook_rt.dos, field)
            if av != hv:
                lines.append(f"  {field}: asm={av!r} hook={hv!r}")
        for field in ("allocations", "key_queue", "stdout"):
            av = getattr(asm_rt.dos, field)
            hv = getattr(hook_rt.dos, field)
            if av != hv:
                lines.append(f"  {field}: asm={av!r} hook={hv!r}")
        if asm_rt.program.memory.ega_map_mask != hook_rt.program.memory.ega_map_mask:
            lines.append(f"  ega_map_mask: asm={asm_rt.program.memory.ega_map_mask:02X} hook={hook_rt.program.memory.ega_map_mask:02X}")
        if asm_rt.program.memory.ega_read_plane != hook_rt.program.memory.ega_read_plane:
            lines.append(f"  ega_read_plane: asm={asm_rt.program.memory.ega_read_plane} hook={hook_rt.program.memory.ega_read_plane}")
        if asm_rt.program.memory.ega_display_start != hook_rt.program.memory.ega_display_start:
            lines.append(
                f"  ega_display_start: asm={asm_rt.program.memory.ega_display_start:04X} "
                f"hook={hook_rt.program.memory.ega_display_start:04X}"
            )
        for field in (
            "_pit_channel2_access",
            "_pit_channel2_latch",
            "_pit_channel2_write_low",
            "pit_channel2_reload",
            "speaker_control",
            "opl_selected_register",
            "opl_status",
            "opl_registers",
        ):
            av = getattr(asm_rt.dos, field)
            hv = getattr(hook_rt.dos, field)
            if av != hv:
                lines.append(f"  {field}: asm={av!r} hook={hv!r}")
        if asm_rt.dos.port_log != hook_rt.dos.port_log:
            lines.append(
                "  port_log_tail:\n"
                f"    asm={asm_rt.dos.port_log[-8:]}\n"
                f"    hook={hook_rt.dos.port_log[-8:]}"
            )
        lines.extend(self._file_diff(asm_rt, hook_rt))
        return lines

    @staticmethod
    def _file_diff(asm_rt: Runtime, hook_rt: Runtime) -> list[str]:
        lines = []
        asm_handles = set(asm_rt.dos.files)
        hook_handles = set(hook_rt.dos.files)
        if asm_handles != hook_handles:
            lines.append(f"  file handles: asm={sorted(asm_handles)} hook={sorted(hook_handles)}")
        for handle in sorted(asm_handles & hook_handles):
            af = asm_rt.dos.files[handle]
            hf = hook_rt.dos.files[handle]
            for field in ("path", "pos", "writable"):
                av = getattr(af, field)
                hv = getattr(hf, field)
                if av != hv:
                    lines.append(f"  file[{handle}].{field}: asm={av!r} hook={hv!r}")
            if len(af.data) != len(hf.data):
                lines.append(f"  file[{handle}].data length: asm={len(af.data)} hook={len(hf.data)}")
                continue
            if af.data != hf.data:
                first = next(i for i, (a, h) in enumerate(zip(af.data, hf.data)) if a != h)
                lines.append(
                    f"  file[{handle}].data: first diff at {first} "
                    f"asm={af.data[first]:02X} hook={hf.data[first]:02X}"
                )
        return lines

    @staticmethod
    def _range_diff(asm: bytearray, hook: bytearray, rng: MemoryRange) -> str | None:
        start = max(0, rng.start)
        end = min(len(asm), len(hook), start + rng.size)
        asm_view = memoryview(asm)[start:end]
        hook_view = memoryview(hook)[start:end]
        if asm_view == hook_view:
            return None
        first = None
        count = 0
        for rel, (asm_byte, hook_byte) in enumerate(zip(asm_view, hook_view)):
            if asm_byte != hook_byte:
                count += 1
                if first is None:
                    first = start + rel
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

