from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .cpu import HaltExecution, UnsupportedInstruction
from .runtime import Runtime


def parse_addr(text: str) -> tuple[int, int]:
    cs, ip = text.split(":", 1)
    return int(cs, 16) & 0xFFFF, int(ip, 16) & 0xFFFF


def run_until(
    rt: Runtime,
    *,
    max_steps: int,
    stop_at: tuple[int, int] | None = None,
    trace_tail: int = 0,
) -> tuple[str, int, list[str]]:
    """Run the interpreter and optionally keep only the last N trace lines."""
    tail: deque[str] = deque(maxlen=trace_tail)
    rt.cpu.trace_enabled = trace_tail > 0
    steps = 0
    try:
        for steps in range(1, max_steps + 1):
            if stop_at is not None and rt.cpu.addr() == stop_at:
                return f"reached {stop_at[0]:04X}:{stop_at[1]:04X}", steps - 1, list(tail)
            rt.cpu.step()
            if rt.cpu.trace:
                tail.extend(rt.cpu.trace)
                rt.cpu.trace.clear()
        return "stopped after max steps", steps, list(tail)
    except HaltExecution:
        return "program halted", steps, list(tail)
    except UnsupportedInstruction as e:
        return f"unsupported instruction: {e}", steps, list(tail)
    except Exception as e:  # keep snapshots useful even during emulator bring-up
        return f"exception: {type(e).__name__}: {e}", steps, list(tail)


def write_snapshot(rt: Runtime, out_dir: str | Path, *, status: str, steps: int, trace_tail: Iterable[str] = ()) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "memory_1mb.bin").write_bytes(bytes(rt.program.memory.data))
    (out / "trace_tail.txt").write_text("\n".join(trace_tail) + ("\n" if trace_tail else ""), encoding="utf-8")
    meta = {
        "status": status,
        "steps": steps,
        "cpu": asdict(rt.cpu.s),
        "cpu_snapshot": rt.cpu.s.snapshot(),
        "program": {
            "path": str(rt.program.exe.path),
            "psp_segment": rt.program.psp_segment,
            "load_segment": rt.program.load_segment,
            "entry_cs": rt.program.entry_cs,
            "entry_ip": rt.program.entry_ip,
            "initial_ss": rt.program.initial_ss,
            "initial_sp": rt.program.initial_sp,
            "load_module_size": len(rt.program.exe.load_module),
            "overlay_size": len(rt.program.overlay),
        },
        "dos": {
            "video_mode": rt.dos.video_mode,
            "video_page": rt.dos.video_page,
            "ticks": rt.dos.ticks,
            "vga_status_reads": rt.dos.vga_status_reads,
            "pit_channel2_access": rt.dos._pit_channel2_access,
            "pit_channel2_latch": rt.dos._pit_channel2_latch,
            "pit_channel2_write_low": rt.dos._pit_channel2_write_low,
            "pit_channel2_reload": rt.dos.pit_channel2_reload,
            "speaker_control": rt.dos.speaker_control,
            "ega_planar": rt.program.memory.ega_planar,
            "ega_map_mask": rt.program.memory.ega_map_mask,
            "ega_read_plane": rt.program.memory.ega_read_plane,
            "ega_display_start": rt.program.memory.ega_display_start,
            "next_alloc_segment": rt.dos.next_alloc_segment,
            "allocation_limit_segment": rt.dos.allocation_limit_segment,
            "allocations": {f"{seg:04X}": size for seg, size in sorted(rt.dos.allocations.items())},
            "open_files": {
                str(handle): {"path": str(f.path), "pos": f.pos, "size": len(f.data)}
                for handle, f in rt.dos.files.items()
            },
            "stdout_tail": "".join(rt.dos.stdout)[-4096:],
            "port_log_tail": rt.dos.port_log[-128:],
        },
        "hooks": {
            f"{cs:04X}:{ip:04X}": name for (cs, ip), name in sorted(rt.cpu.hook_names.items())
        },
    }
    (out / "state.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_snapshot(exe_path: str | Path, snapshot_dir: str | Path, *, game_root: str | Path | None = None) -> Runtime:
    """Create a Runtime from an existing snapshot directory.

    This is intentionally a developer/reverse-engineering helper: it restores
    CPU state, full 1MB memory, and simple DOS bookkeeping so investigation can
    continue from a known checkpoint instead of replaying the whole bootstrap.
    """
    from .cpu import CPUState
    from .dos import FileHandle
    from .runtime import create_runtime

    snap = Path(snapshot_dir)
    meta = json.loads((snap / "state.json").read_text(encoding="utf-8"))
    rt = create_runtime(exe_path, game_root=game_root)
    rt.program.memory.data[:] = (snap / "memory_1mb.bin").read_bytes()
    rt.cpu.mem = rt.program.memory
    rt.cpu.s = CPUState(**meta["cpu"])

    dos_meta = meta.get("dos", {})
    rt.dos.video_mode = dos_meta.get("video_mode", rt.dos.video_mode)
    rt.dos.video_page = dos_meta.get("video_page", rt.dos.video_page)
    rt.dos.ticks = dos_meta.get("ticks", rt.dos.ticks)
    rt.dos.vga_status_reads = dos_meta.get("vga_status_reads", rt.dos.vga_status_reads)
    rt.dos._pit_channel2_access = dos_meta.get("pit_channel2_access", rt.dos._pit_channel2_access)
    rt.dos._pit_channel2_latch = dos_meta.get("pit_channel2_latch", rt.dos._pit_channel2_latch)
    rt.dos._pit_channel2_write_low = dos_meta.get("pit_channel2_write_low", rt.dos._pit_channel2_write_low)
    rt.dos.pit_channel2_reload = dos_meta.get("pit_channel2_reload", rt.dos.pit_channel2_reload)
    rt.dos.speaker_control = dos_meta.get("speaker_control", rt.dos.speaker_control)
    if "pit_channel2_reload" not in dos_meta and "port_log_tail" in dos_meta:
        _restore_speaker_from_port_log_tail(rt, dos_meta.get("port_log_tail", ()))
    rt.program.memory.ega_planar = dos_meta.get("ega_planar", rt.program.memory.ega_planar)
    rt.program.memory.ega_map_mask = dos_meta.get("ega_map_mask", rt.program.memory.ega_map_mask)
    rt.program.memory.ega_read_plane = dos_meta.get("ega_read_plane", rt.program.memory.ega_read_plane)
    rt.program.memory.ega_display_start = dos_meta.get("ega_display_start", rt.program.memory.ega_display_start)
    rt.dos.next_alloc_segment = dos_meta.get("next_alloc_segment", rt.dos.next_alloc_segment)
    rt.dos.allocation_limit_segment = dos_meta.get("allocation_limit_segment", rt.dos.allocation_limit_segment)
    rt.dos.allocations = {int(seg, 16): int(size) for seg, size in dos_meta.get("allocations", {}).items()}
    rt.dos.files.clear()
    for handle_text, file_meta in dos_meta.get("open_files", {}).items():
        path = Path(file_meta["path"])
        if not path.is_absolute():
            path = Path(path)
        if not path.exists():
            path = rt.dos.resolve_game_path(Path(file_meta["path"]).name)
        fh = FileHandle(path, bytearray(path.read_bytes()), pos=int(file_meta.get("pos", 0)))
        rt.dos.files[int(handle_text)] = fh
    if rt.dos.files:
        rt.dos.next_handle = max(rt.dos.files) + 1
    _repair_overkill_object_allocator_cursor(rt)
    return rt


def _repair_overkill_object_allocator_cursor(rt: Runtime) -> None:
    """Repair snapshots saved after the old 7573 lift corrupted DS:[95DA].

    DS:[95DA] is the game's free-object scan cursor.  Valid values are the 34
    object slots 2B5C..3294 or the 32CC sentinel that the original 7573 allocator
    wraps back to 2B5C.  Older snapshots can contain values beyond the sentinel
    (for example 3374), which overlaps the Tandy draw buffer and makes newly
    allocated projectiles disappear on the next sprite draw.
    """
    cpu = rt.cpu
    mem = cpu.mem
    ds = cpu.s.ds & 0xFFFF
    if not _looks_like_overkill_runtime_snapshot(rt):
        return
    cursor = mem.rw(ds, 0x95DA)
    if _is_valid_overkill_object_cursor(cursor):
        return
    mem.ww(ds, 0x95DA, 0x32CC)


def _looks_like_overkill_runtime_snapshot(rt: Runtime) -> bool:
    cpu = rt.cpu
    mem = cpu.mem
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    # OVERKILL keeps its keyboard scancode table at DS:213E in captured runtime
    # snapshots.  This guard keeps the invariant repair away from unrelated or
    # very early bootstrap snapshots where DS:[95DA] may be arbitrary data.
    return (
        mem.rb(ds, 0x2140) == 0x2C
        and mem.rb(ds, 0x2141) == 0x39
        and mem.rb(ds, 0x2142) == 0x10
        and mem.rw(cs, 0x95BC) in (0, 1, 2)
    )


def _is_valid_overkill_object_cursor(cursor: int) -> bool:
    cursor &= 0xFFFF
    if cursor == 0x32CC:
        return True
    if cursor < 0x2B5C or cursor > 0x3294:
        return False
    return ((cursor - 0x2B5C) % 0x38) == 0


def _restore_speaker_from_port_log_tail(rt: Runtime, port_log_tail) -> None:
    """Best-effort PC-speaker state recovery for older snapshots.

    Pre-sound-state snapshots only stored the last few OUT instructions.  Replaying
    the speaker-related writes reconstructs the PIT channel-2 reload and port 61h
    gate when the tail contains the most recent tone setup, which is exactly the
    common F12-in-the-menu case.  The replay updates DOS hardware state only; it
    deliberately does not call a frontend speaker callback or append duplicate log
    entries.
    """
    saved_callback = rt.dos.speaker_callback
    rt.dos.speaker_callback = None
    try:
        for entry in port_log_tail or ():
            if not isinstance(entry, (list, tuple)) or len(entry) != 4:
                continue
            direction, port, value, bits = entry
            if direction != "out":
                continue
            port = int(port) & 0xFFFF
            if port not in (0x42, 0x43, 0x61):
                continue
            rt.dos._track_pc_speaker(port, int(value), int(bits))
    finally:
        rt.dos.speaker_callback = saved_callback
