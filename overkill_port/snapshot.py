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
            "ticks": rt.dos.ticks,
            "vga_status_reads": rt.dos.vga_status_reads,
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
    rt.dos.ticks = dos_meta.get("ticks", rt.dos.ticks)
    rt.dos.vga_status_reads = dos_meta.get("vga_status_reads", rt.dos.vga_status_reads)
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
    return rt
