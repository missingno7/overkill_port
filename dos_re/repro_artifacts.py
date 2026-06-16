"""Helpers for reproducible crash/divergence artifacts.

These helpers intentionally live in ``dos_re`` because they are generic runtime
forensics: write a snapshot plus a small manifest explaining why it was captured.
Game-specific code decides when to call them and what metadata to attach.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Any

from .runtime import Runtime
from .snapshot import write_snapshot


def safe_artifact_part(text: str) -> str:
    """Return a filesystem-friendly artifact name component."""
    out = []
    for ch in str(text):
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        elif ch in (" ", ":", "/", "\\", "."):
            out.append("_")
    cleaned = "".join(out).strip("_")
    return cleaned or "artifact"


def write_runtime_repro_snapshot(
    rt: Runtime,
    *,
    root: str | Path,
    name: str,
    status: str,
    metadata: Mapping[str, Any] | None = None,
    trace_tail: Iterable[str] = (),
    timestamp: datetime | None = None,
) -> Path:
    """Write a timestamped runtime snapshot plus a small repro manifest.

    The returned directory is directly loadable with ``scripts/play.py --snapshot``.
    The additional ``repro.json`` file is intentionally best-effort metadata for
    humans/tools; the canonical VM state remains ``state.json`` + ``memory_1mb.bin``.
    """
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    out = Path(root) / f"{safe_artifact_part(name)}_{stamp}"
    write_snapshot(rt, out, status=status, steps=rt.cpu.instruction_count, trace_tail=trace_tail)
    cs, ip = rt.cpu.addr()
    manifest = {
        "version": 1,
        "kind": "runtime_snapshot",
        "status": status,
        "snapshot": ".",
        "created_at": stamp,
        "cpu_addr": f"{cs:04X}:{ip:04X}",
        "steps": rt.cpu.instruction_count,
        "metadata": dict(metadata or {}),
    }
    (out / "repro.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return out
