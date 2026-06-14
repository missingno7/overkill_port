"""Materialize OVERKILL's initialized static runtime image.

This is the practical tool behind the bootstrap/static-runtime boundary.  The
original packed game remains the oracle, but the target source port should not
run the outer shell, unpacker, and driver loader on every normal launch.  Instead
we can run that historical startup once, stop at a known inner-runtime frontier,
and write a deterministic bundle containing the initialized memory image plus a
manifest of the state the clean runtime is allowed to depend on.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from dos_re.memory import CPU_MEM_SIZE, linear
from dos_re.runtime import Runtime
from .runtime import create_overkill_runtime
from dos_re.snapshot import run_until, write_snapshot
from .bootstrap_boundary import bootstrap_boundary_manifest
from .launch import build_command_tail


DEFAULT_STATIC_RUNTIME_ENTRY = (0x1010, 0xD007)
STATIC_BUNDLE_MANIFEST_NAME = "static_runtime_bundle.json"


@dataclass(frozen=True)
class StaticMemorySegment:
    """A named byte range captured in the initialized runtime image."""

    name: str
    role: str
    start_phys: int
    size: int
    sha256: str
    nonzero_bytes: int

    @property
    def end_phys_exclusive(self) -> int:
        return self.start_phys + self.size

    def to_manifest(self) -> dict[str, Any]:
        data = asdict(self)
        data["start_phys_hex"] = f"{self.start_phys:05X}"
        data["end_phys_exclusive_hex"] = f"{self.end_phys_exclusive:05X}"
        return data


@dataclass(frozen=True)
class MaterializedGlobal:
    """A small runtime state value that proves bootstrap did its job."""

    name: str
    addr: str
    value: int
    role: str

    def to_manifest(self) -> dict[str, Any]:
        data = asdict(self)
        data["value_hex"] = f"{self.value:04X}"
        return data


def sha256_bytes(data: bytes | bytearray | memoryview) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def _slice_memory(rt: Runtime, start_phys: int, size: int) -> bytes:
    start = start_phys & 0xFFFFF
    if size < 0:
        raise ValueError(f"negative segment size {size}")
    if start + size > CPU_MEM_SIZE:
        raise ValueError(f"static bundle segment crosses 1MB CPU memory: {start:05X}+{size:X}")
    return bytes(rt.program.memory.data[start:start + size])


def _segment(rt: Runtime, *, name: str, role: str, start_phys: int, size: int) -> StaticMemorySegment:
    payload = _slice_memory(rt, start_phys, size)
    return StaticMemorySegment(
        name=name,
        role=role,
        start_phys=start_phys,
        size=size,
        sha256=sha256_bytes(payload),
        nonzero_bytes=sum(1 for b in payload if b),
    )


def static_runtime_segments(rt: Runtime) -> tuple[StaticMemorySegment, ...]:
    """Return the stable ranges currently worth hashing in a static bundle.

    The bundle still includes the full 1 MiB snapshot for replay/debugging.  These
    named hashes are a smaller review surface: they make accidental changes in
    the relocated inner runtime, PSP tail, and optional driver area easy to spot
    without forcing every future test to diff the whole memory image.
    """

    segments: list[StaticMemorySegment] = [
        _segment(
            rt,
            name="psp_and_command_tail",
            role="DOS PSP plus compact selector tail consumed by the inner game",
            start_phys=linear(rt.program.psp_segment, 0x0000),
            size=0x0100,
        ),
        _segment(
            rt,
            name="relocated_inner_runtime_1010",
            role="current relocated inner game code/data segment used by verified hooks",
            start_phys=linear(0x1010, 0x0000),
            size=0x10000,
        ),
    ]

    # Optional sound drivers are loaded by the original startup into 2032:* when
    # AdLib/Roland is selected.  Keep the range broad and hash-based for now; the
    # exact driver ABI can be narrowed when the sound island is lifted further.
    driver = _slice_memory(rt, linear(0x2032, 0x0000), 0x4000)
    if any(driver):
        segments.append(
            _segment(
                rt,
                name="optional_sound_driver_2032",
                role="original optional AdLib/Roland driver materialized by bootstrap",
                start_phys=linear(0x2032, 0x0000),
                size=0x4000,
            )
        )
    return tuple(segments)


def materialized_globals(rt: Runtime) -> tuple[MaterializedGlobal, ...]:
    """Read small bootstrap-produced globals that the source-port boundary tracks."""

    mem = rt.program.memory
    cs = rt.cpu.s.cs & 0xFFFF
    ds = rt.cpu.s.ds & 0xFFFF
    return (
        MaterializedGlobal(
            name="video_selector_word",
            addr=f"{cs:04X}:95BC",
            value=mem.rw(cs, 0x95BC),
            role="0=CGA, 1=EGA, 2=Tandy/PCjr; consumed by runtime rendering branches",
        ),
        MaterializedGlobal(
            name="sound_driver_active_flag",
            addr=f"{ds:04X}:0055",
            value=mem.rb(ds, 0x0055),
            role="set by original sound-driver probe when optional AdLib/Roland driver is active",
        ),
        MaterializedGlobal(
            name="object_allocator_cursor",
            addr=f"{ds:04X}:95DA",
            value=mem.rw(ds, 0x95DA),
            role="runtime object-slot allocator cursor; useful sanity check for gameplay snapshots",
        ),
    )


def build_static_runtime_bundle_manifest(
    rt: Runtime,
    *,
    video: str,
    sound: str,
    status: str,
    steps: int,
    stop_at: tuple[int, int],
    trace_tail: Iterable[str] = (),
) -> dict[str, Any]:
    """Return JSON data describing a materialized static runtime bundle."""

    memory_1mb = bytes(rt.program.memory.data[:CPU_MEM_SIZE])
    command_tail = build_command_tail(video, sound)
    cs, ip = rt.cpu.addr()
    stop_cs, stop_ip = stop_at
    return {
        "schema": "overkill.static_runtime_bundle.v1",
        "boundary_schema": "overkill.static_runtime_boundary.v1",
        "video": video,
        "sound": sound,
        "command_tail_hex": command_tail.hex(" ").upper(),
        "status": status,
        "steps": steps,
        "reached_requested_entry": (cs, ip) == (stop_cs, stop_ip),
        "requested_entry": f"{stop_cs:04X}:{stop_ip:04X}",
        "current_addr": f"{cs:04X}:{ip:04X}",
        "cpu_snapshot": rt.cpu.s.snapshot(),
        "memory_1mb_sha256": sha256_bytes(memory_1mb),
        "segments": [segment.to_manifest() for segment in static_runtime_segments(rt)],
        "materialized_globals": [item.to_manifest() for item in materialized_globals(rt)],
        "source_files": {
            "exe_path": str(rt.program.exe.path),
            "load_module_size": len(rt.program.exe.load_module),
            "overlay_size": len(rt.program.overlay),
        },
        "snapshot_files": {
            "memory": "memory_1mb.bin",
            "state": "state.json",
            "trace_tail": "trace_tail.txt",
        },
        "boundary": bootstrap_boundary_manifest(video=video, sound=sound),
        "derived_assets_status": (
            "Not split into named assets yet.  This bundle captures the canonical "
            "initialized image; future extractor passes should promote screens, "
            "tables, fonts, sprites, level metadata, and sound-driver blobs into "
            "separate deterministic artifacts."
        ),
        "trace_tail": list(trace_tail),
    }


def materialize_static_runtime_bundle(
    exe_path: str | Path,
    out_dir: str | Path,
    *,
    game_root: str | Path | None = None,
    video: str = "tandy",
    sound: str = "pc",
    stop_at: tuple[int, int] = DEFAULT_STATIC_RUNTIME_ENTRY,
    max_steps: int = 3_000_000,
    trace_tail: int = 200,
) -> dict[str, Any]:
    """Run original bootstrap to a frontier and write a static runtime bundle."""

    rt = create_overkill_runtime(exe_path, game_root=game_root, command_tail=build_command_tail(video, sound))
    status, steps, tail = run_until(rt, max_steps=max_steps, stop_at=stop_at, trace_tail=trace_tail)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_snapshot(rt, out, status=status, steps=steps, trace_tail=tail)
    manifest = build_static_runtime_bundle_manifest(
        rt,
        video=video,
        sound=sound,
        status=status,
        steps=steps,
        stop_at=stop_at,
        trace_tail=tail,
    )
    (out / STATIC_BUNDLE_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
