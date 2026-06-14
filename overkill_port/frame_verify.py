from __future__ import annotations

import os
import json
import sys
import zlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
import webbrowser

from .cpu import CPU8086, HaltExecution, UnsupportedInstruction
from .memory import EGA_APERTURE, EGA_PLANE_STRIDE
from .runtime import Runtime, create_runtime
from .snapshot import load_snapshot

Addr = tuple[int, int]

CGA_PRESENT_HOOK: Addr = (0x1010, 0x447B)
EGA_PRESENT_HOOK: Addr = (0x1010, 0x2750)
TANDY_PRESENT_HOOK: Addr = (0x1010, 0x3354)
TIMER_WAIT_HOOK: Addr = (0x1010, 0x0679)
RETRACE_WAIT_HOOK: Addr = (0x1010, 0x50C9)

B800_BASE = 0xB8000
B800_CGA_SIZE = 0x4000
B800_TANDY_SIZE = 0x8000
EGA_BYTES_PER_ROW = 40
WIDTH = 320
HEIGHT = 200

# Hardware/environment wait hooks that must remain hooked even in the reference
# runtime.  The interpreter has no asynchronous PIT/IRQ0 or real VGA retrace, so
# the original busy-wait ASM at these addresses can otherwise spin forever.  The
# verifier still compares everything around those waits at the next boundary.
REFERENCE_ENV_HOOKS: set[Addr] = {TIMER_WAIT_HOOK, RETRACE_WAIT_HOOK}

# Mirrors scripts/play.py: this lifted loop is only validated for CGA mode.
NON_CGA_INTERACTIVE_DISABLE: set[Addr] = {(0x1010, 0x58DF)}


class FrameBoundary(Exception):
    pass


class FrameVerifyDivergence(RuntimeError):
    pass


@dataclass(frozen=True)
class FrameVerifyConfig:
    video: Literal["cga", "ega", "tandy"] = "tandy"
    palette: str = "1h"
    max_frames: int = 60
    frame_budget: int = 6_000_000
    source: Literal["rgb", "vram", "both"] = "both"
    dump_dir: Path = Path("artifacts/evidence/frame_verify")
    stop_on_diff: bool = True
    preview_on_diff: bool = False
    ega_start_address_units: Literal["byte", "word", "ignore"] = "byte"
    log_every: int = 10


@dataclass
class FrameSample:
    side: str
    frame_no: int
    kind: str
    hook: Addr
    cs: int
    ip: int
    steps_since_start: int
    boundary_steps: int
    display_start: int
    raw_crc: int
    rgb_crc: int
    raw: bytes
    rgb: bytes
    recent_hooks: tuple[str, ...]


def run_frame_verifier(
    *,
    exe: Path,
    assets: Path,
    snapshot: str | None,
    command_tail: bytes | str,
    config: FrameVerifyConfig,
    publish_candidate: Callable[[Runtime, FrameSample], None] | None = None,
    pump_inputs: Callable[[Runtime, Runtime], None] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> int:
    """Run a headless frame-boundary verifier.

    Two runtimes start from the same initial state:
      * reference: normal gameplay/draw replacements disabled, original ASM runs;
        only synthetic hardware wait hooks are kept so PIT/retrace waits progress;
      * candidate: the currently installed replacement hooks run.

    The runners stop at the same semantic frame boundaries (present/timer/retrace),
    then compare normalized video RAM and/or rendered 320x200 RGB frames.
    """
    ref = _load_runtime(exe, assets, snapshot, command_tail)
    cand = _load_runtime(exe, assets, snapshot, command_tail)
    ref.cpu.trace_enabled = False
    cand.cpu.trace_enabled = False

    if config.video != "cga":
        _disable_hooks(ref, NON_CGA_INTERACTIVE_DISABLE)
        _disable_hooks(cand, NON_CGA_INTERACTIVE_DISABLE)

    ref_runner = _BoundaryRunner(ref, config=config, side="reference", reference=True)
    cand_runner = _BoundaryRunner(cand, config=config, side="candidate", reference=False)

    print(
        f"FRAME VERIFY start video={config.video} source={config.source} "
        f"max_frames={config.max_frames} snapshot={snapshot or '<fresh>'}",
        flush=True,
    )

    frame_no = 1
    while config.max_frames <= 0 or frame_no <= config.max_frames:
        if stop_requested is not None and stop_requested():
            return 0
        if pump_inputs is not None:
            pump_inputs(ref, cand)
        try:
            ref_sample = ref_runner.run_to_boundary(frame_no)
            if pump_inputs is not None:
                pump_inputs(ref, cand)
            cand_sample = cand_runner.run_to_boundary(frame_no)
        except (HaltExecution, UnsupportedInstruction) as exc:
            raise FrameVerifyDivergence(f"FRAME VERIFY STOPPED before frame {frame_no}: {type(exc).__name__}: {exc}") from exc

        report = _compare_samples(ref_sample, cand_sample, config)
        if publish_candidate is not None:
            publish_candidate(cand, cand_sample)
        if report is not None:
            _dump_divergence(ref_sample, cand_sample, report, config)
            print(report, flush=True)
            if status_callback is not None:
                status_callback(f"FRAME VERIFY divergence at frame {frame_no}")
            return 1 if config.stop_on_diff else 0

        if config.log_every and (frame_no == 1 or frame_no % config.log_every == 0):
            msg = (
                f"FRAME VERIFY ok frame={frame_no} boundary={ref_sample.kind} "
                f"raw={ref_sample.raw_crc:08X} rgb={ref_sample.rgb_crc:08X}"
            )
            print(msg, flush=True)
            if status_callback is not None:
                status_callback(msg)
        frame_no += 1

    print(f"FRAME VERIFY OK frames={config.max_frames}", flush=True)
    if status_callback is not None:
        status_callback(f"FRAME VERIFY OK frames={config.max_frames}")
    return 0


def _load_runtime(exe: Path, assets: Path, snapshot: str | None, command_tail: bytes | str) -> Runtime:
    if snapshot:
        return load_snapshot(exe, snapshot, game_root=assets)
    return create_runtime(exe, game_root=assets, command_tail=command_tail)


def _disable_hooks(rt: Runtime, keys: set[Addr]) -> None:
    for key in keys:
        rt.cpu.replacement_hooks.pop(key, None)
        rt.cpu.hook_names.pop(key, None)


class _BoundaryRunner:
    def __init__(self, rt: Runtime, *, config: FrameVerifyConfig, side: str, reference: bool) -> None:
        self.rt = rt
        self.config = config
        self.side = side
        self.reference = reference
        self.boundary: tuple[str, Addr, int] | None = None
        self._base_hooks = dict(rt.cpu.replacement_hooks)
        self._base_names = dict(rt.cpu.hook_names)
        self.last_hooks: deque[str] = deque(maxlen=48)
        if reference:
            # Keep only synthetic hardware waits.  All normal gameplay/draw hooks
            # fall back to interpreted ASM in the oracle runtime.
            rt.cpu.replacement_hooks = {
                key: fn for key, fn in self._base_hooks.items() if key in REFERENCE_ENV_HOOKS
            }
            rt.cpu.hook_names = {
                key: name for key, name in self._base_names.items() if key in REFERENCE_ENV_HOOKS
            }
            self._base_hooks = dict(rt.cpu.replacement_hooks)
            self._base_names = dict(rt.cpu.hook_names)
        self._install_boundaries()
        self.rt.cpu.hook_verifier = self._trace_hook


    def _trace_hook(self, cpu: CPU8086, key: Addr, handler: Callable[[CPU8086], None], name: str) -> None:
        self.last_hooks.append(
            f"{cpu.instruction_count:09d} {key[0]:04X}:{key[1]:04X} {name} "
            f"enter={cpu.s.cs:04X}:{cpu.s.ip:04X}"
        )
        handler(cpu)

    def _present_hook(self) -> Addr:
        if self.config.video == "ega":
            return EGA_PRESENT_HOOK
        if self.config.video == "tandy":
            return TANDY_PRESENT_HOOK
        return CGA_PRESENT_HOOK

    def _install_boundaries(self) -> None:
        for key, kind in (
            (self._present_hook(), "present"),
            (TIMER_WAIT_HOOK, "timer"),
            (RETRACE_WAIT_HOOK, "retrace"),
        ):
            self._install_boundary(key, kind)

    def _install_boundary(self, key: Addr, kind: str) -> None:
        base = self.rt.cpu.replacement_hooks.get(key)
        base_name = self.rt.cpu.hook_names.get(key, "replacement")

        def wrapper(cpu: CPU8086, *, _key: Addr = key, _kind: str = kind,
                    _base: Callable[[CPU8086], None] | None = base,
                    _base_name: str = base_name) -> None:
            start_count = cpu.instruction_count
            # In the oracle runtime, present hooks are deliberately absent, so
            # execute the real near-returning ASM routine and stop after it.
            # The two wait hooks remain synthetic in both runtimes because they
            # model external hardware progress rather than game logic.
            if self.reference and _key not in REFERENCE_ENV_HOOKS:
                self._run_original_near_ret(cpu, _key)
            elif _base is not None:
                _base(cpu)
            else:
                self._run_original_near_ret(cpu, _key)
            if _kind == "present":
                self.rt.dos.text_mode_active = False
            self.boundary = (_kind, _key, cpu.instruction_count - start_count)
            raise FrameBoundary()

        self.rt.cpu.replacement_hooks[key] = wrapper
        self.rt.cpu.hook_names[key] = f"frame_verify_{self.side}_{kind}"

    def _run_original_near_ret(self, cpu: CPU8086, key: Addr) -> None:
        target = (cpu.s.cs & 0xFFFF, cpu.mem.rw(cpu.s.ss, cpu.s.sp))
        saved_hook = cpu.replacement_hooks.pop(key, None)
        saved_name = cpu.hook_names.pop(key, None)
        try:
            for _ in range(self.config.frame_budget):
                if cpu.addr() == target:
                    return
                cpu.step()
        finally:
            if saved_hook is not None:
                cpu.replacement_hooks[key] = saved_hook
            if saved_name is not None:
                cpu.hook_names[key] = saved_name
        raise FrameVerifyDivergence(
            f"FRAME VERIFY ASM boundary timeout at {key[0]:04X}:{key[1]:04X}; "
            f"target={target[0]:04X}:{target[1]:04X} now={cpu.s.cs:04X}:{cpu.s.ip:04X}"
        )

    def run_to_boundary(self, frame_no: int) -> FrameSample:
        self.boundary = None
        start = self.rt.cpu.instruction_count
        for _ in range(self.config.frame_budget):
            try:
                self.rt.cpu.step()
            except FrameBoundary:
                if self.boundary is None:
                    raise FrameVerifyDivergence("FRAME VERIFY internal error: boundary raised without metadata")
                kind, hook, boundary_steps = self.boundary
                return _sample(self.rt, self.config, self.side, frame_no, kind, hook, boundary_steps, start, tuple(self.last_hooks))
        cs, ip = self.rt.cpu.addr()
        raise FrameVerifyDivergence(
            f"FRAME VERIFY TIMEOUT side={self.side} frame={frame_no} "
            f"budget={self.config.frame_budget} at={cs:04X}:{ip:04X}"
        )


def _sample(
    rt: Runtime,
    config: FrameVerifyConfig,
    side: str,
    frame_no: int,
    kind: str,
    hook: Addr,
    boundary_steps: int,
    start_count: int,
    recent_hooks: tuple[str, ...],
) -> FrameSample:
    raw = _visible_vram(rt, config)
    rgb = _render_rgb_bytes(rt, config)
    return FrameSample(
        side=side,
        frame_no=frame_no,
        kind=kind,
        hook=hook,
        cs=rt.cpu.s.cs & 0xFFFF,
        ip=rt.cpu.s.ip & 0xFFFF,
        steps_since_start=rt.cpu.instruction_count - start_count,
        boundary_steps=boundary_steps,
        display_start=_display_start(rt, config),
        raw_crc=zlib.crc32(raw) & 0xFFFFFFFF,
        rgb_crc=zlib.crc32(rgb) & 0xFFFFFFFF,
        raw=raw,
        rgb=rgb,
        recent_hooks=recent_hooks,
    )


def _display_start(rt: Runtime, config: FrameVerifyConfig) -> int:
    raw_start = rt.program.memory.ega_display_start & 0xFFFF
    if config.video != "ega":
        return 0
    if config.ega_start_address_units == "ignore":
        return 0
    if config.ega_start_address_units == "word":
        return (raw_start << 1) & 0xFFFF
    return raw_start


def _visible_vram(rt: Runtime, config: FrameVerifyConfig) -> bytes:
    data = rt.program.memory.data
    if config.video == "tandy":
        return bytes(data[B800_BASE:B800_BASE + B800_TANDY_SIZE])
    if config.video == "cga":
        return bytes(data[B800_BASE:B800_BASE + B800_CGA_SIZE])

    # Normalize the EGA visible window from the active CRTC display start rather
    # than comparing the entire shadow store, which includes off-screen pages.
    start = _display_start(rt, config)
    out = bytearray()
    for plane in range(4):
        plane_base = EGA_APERTURE + plane * EGA_PLANE_STRIDE
        for y in range(HEIGHT):
            row = (start + y * EGA_BYTES_PER_ROW) & 0xFFFF
            if row <= 0x10000 - EGA_BYTES_PER_ROW:
                out += data[plane_base + row:plane_base + row + EGA_BYTES_PER_ROW]
            else:
                tail = 0x10000 - row
                out += data[plane_base + row:plane_base + 0x10000]
                out += data[plane_base:plane_base + (EGA_BYTES_PER_ROW - tail)]
    return bytes(out)


def _render_rgb_bytes(rt: Runtime, config: FrameVerifyConfig) -> bytes:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from render_cga import render_ega_ppm, render_ppm, render_tandy_ppm

    mem = bytes(rt.program.memory.data)
    if config.video == "tandy":
        ppm = render_tandy_ppm(mem, 0xB800, 1)[2]
    elif config.video == "ega":
        ppm = render_ega_ppm(mem, 0xA000, 1, _display_start(rt, config))[2]
    else:
        ppm = render_ppm(mem, 0xB800, config.palette, 1)[2]
    return ppm.split(b"255\n", 1)[1]


def _compare_samples(ref: FrameSample, cand: FrameSample, config: FrameVerifyConfig) -> str | None:
    sections: list[str] = []
    if ref.kind != cand.kind or ref.hook != cand.hook:
        sections.append(
            "Boundary differences:\n"
            f"  REF:  {ref.kind} {ref.hook[0]:04X}:{ref.hook[1]:04X}\n"
            f"  HOOK: {cand.kind} {cand.hook[0]:04X}:{cand.hook[1]:04X}"
        )
    if ref.display_start != cand.display_start:
        sections.append(f"Display start differences:\n  REF: {ref.display_start:04X}\n  HOOK: {cand.display_start:04X}")
    if config.source in ("vram", "both") and ref.raw != cand.raw:
        idx = _first_diff(ref.raw, cand.raw)
        sections.append(
            "Raw video differences:\n"
            f"  REF crc:  {ref.raw_crc:08X}\n"
            f"  HOOK crc: {cand.raw_crc:08X}\n"
            f"  first differing byte: {idx}"
        )
    if config.source in ("rgb", "both") and ref.rgb != cand.rgb:
        idx = _first_diff(ref.rgb, cand.rgb)
        pixel = idx // 3 if idx >= 0 else -1
        y, x = divmod(pixel, WIDTH) if pixel >= 0 else (-1, -1)
        sections.append(
            "Rendered RGB differences:\n"
            f"  REF crc:  {ref.rgb_crc:08X}\n"
            f"  HOOK crc: {cand.rgb_crc:08X}\n"
            f"  first differing pixel: x={x} y={y} channel={idx % 3 if idx >= 0 else -1}"
        )
    if not sections:
        return None
    hook_tail = "\n".join(f"  {line}" for line in cand.recent_hooks[-16:]) or "  <none>"
    ref_tail = "\n".join(f"  {line}" for line in ref.recent_hooks[-8:]) or "  <none>"
    return (
        "FRAME VERIFY DIVERGENCE\n"
        f"frame: {ref.frame_no}\n"
        f"video: {config.video}\n"
        f"source: {config.source}\n"
        f"REF continuation:  {ref.cs:04X}:{ref.ip:04X} steps={ref.steps_since_start}\n"
        f"HOOK continuation: {cand.cs:04X}:{cand.ip:04X} steps={cand.steps_since_start}\n"
        + "\n\n".join(sections)
        + "\n\nRecent candidate hooks before divergence:\n" + hook_tail
        + "\n\nRecent reference hooks before divergence:\n" + ref_tail
    )


def _first_diff(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    if len(a) != len(b):
        return n
    return -1


def _dump_divergence(ref: FrameSample, cand: FrameSample, report: str, config: FrameVerifyConfig) -> None:
    out = config.dump_dir
    out.mkdir(parents=True, exist_ok=True)
    stem = f"frame_{ref.frame_no:05d}_{config.video}"
    (out / f"{stem}_report.txt").write_text(report + "\n", encoding="utf-8")
    meta = {
        "frame": ref.frame_no,
        "video": config.video,
        "source": config.source,
        "reference": _sample_meta(ref),
        "candidate": _sample_meta(cand),
    }
    (out / f"{stem}_report.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out / f"{stem}_ref_vram.bin").write_bytes(ref.raw)
    (out / f"{stem}_hook_vram.bin").write_bytes(cand.raw)
    _write_rgb_png(out / f"{stem}_ref.png", ref.rgb)
    _write_rgb_png(out / f"{stem}_hook.png", cand.rgb)
    diff_rgb = _diff_rgb(ref.rgb, cand.rgb)
    _write_rgb_png(out / f"{stem}_diff.png", diff_rgb)
    compare_rgb = _compose_compare_rgb(ref.rgb, cand.rgb, diff_rgb)
    _write_rgb_png(out / f"{stem}_compare.png", compare_rgb, width=WIDTH * 3 + 8)
    compare_path = out / f"{stem}_compare.png"
    print(f"FRAME VERIFY artifacts written to {out / stem}_*", flush=True)
    print(f"FRAME VERIFY compare image: {compare_path}", flush=True)
    if config.preview_on_diff:
        _open_image(compare_path)


def _sample_meta(sample: FrameSample) -> dict[str, object]:
    return {
        "side": sample.side,
        "frame_no": sample.frame_no,
        "kind": sample.kind,
        "hook": f"{sample.hook[0]:04X}:{sample.hook[1]:04X}",
        "continuation": f"{sample.cs:04X}:{sample.ip:04X}",
        "steps_since_start": sample.steps_since_start,
        "boundary_steps": sample.boundary_steps,
        "display_start": f"{sample.display_start:04X}",
        "raw_crc": f"{sample.raw_crc:08X}",
        "rgb_crc": f"{sample.rgb_crc:08X}",
        "recent_hooks": list(sample.recent_hooks),
    }


def _diff_rgb(a: bytes, b: bytes) -> bytes:
    out = bytearray(len(a))
    npx = min(len(a), len(b)) // 3
    for p in range(npx):
        i = p * 3
        changed = a[i:i + 3] != b[i:i + 3]
        if changed:
            out[i:i + 3] = b"\xff\xff\xff"
        else:
            out[i:i + 3] = b"\x00\x00\x00"
    if len(a) != len(b):
        for i in range(npx * 3, len(out)):
            out[i] = 0xFF
    return bytes(out)


def _compose_compare_rgb(ref_rgb: bytes, cand_rgb: bytes, diff_rgb: bytes) -> bytes:
    """Pack reference, candidate, and diff frames into one side-by-side image."""
    if not (len(ref_rgb) == len(cand_rgb) == len(diff_rgb)):
        raise ValueError("compare RGB buffers must be the same length")
    row_bytes = WIDTH * 3
    if len(ref_rgb) != row_bytes * HEIGHT:
        raise ValueError(f"expected {row_bytes * HEIGHT} RGB bytes per frame, got {len(ref_rgb)}")

    separator = b"\x20\x20\x20" * 4
    rows: list[bytearray] = []
    for y in range(HEIGHT):
        off = y * row_bytes
        row = bytearray()
        row.extend(ref_rgb[off:off + row_bytes])
        row.extend(separator)
        row.extend(cand_rgb[off:off + row_bytes])
        row.extend(separator)
        row.extend(diff_rgb[off:off + row_bytes])
        rows.append(row)
    out = bytearray()
    for row in rows:
        out.extend(row)
    return bytes(out)


def _open_image(path: Path) -> None:
    """Best-effort open of a rendered comparison artifact."""
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
            return
        webbrowser.open(path.as_uri())
    except Exception as exc:  # pragma: no cover - best-effort convenience only
        print(f"FRAME VERIFY preview failed for {path}: {type(exc).__name__}: {exc}", flush=True)


def _write_rgb_png(path: Path, rgb: bytes, *, width: int = WIDTH) -> None:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from render_cga import write_png

    expected = width * HEIGHT * 3
    if len(rgb) != expected:
        raise ValueError(f"expected {expected} RGB bytes, got {len(rgb)}")
    row_bytes = width * 3
    rows = [bytearray(rgb[y * row_bytes:(y + 1) * row_bytes]) for y in range(HEIGHT)]
    write_png(path, width, HEIGHT, rows)
