from __future__ import annotations

from pathlib import Path

from dos_re.hooks import registry as _dos_re_hook_registry
from dos_re.runtime import Runtime, create_runtime as create_dos_runtime
from dos_re.snapshot import load_snapshot as load_dos_snapshot

from . import hooks as _overkill_hooks  # noqa: F401 - registers OVERKILL hooks

ORIGINAL_CONTAINER_EXE = "OVERKILL"


def resolve_overkill_exe_path(exe_path: str | Path) -> Path:
    """Resolve the canonical OVERKILL executable/container path.

    The normal source of truth is the original extensionless ``OVERKILL`` file.
    Generated unpacked files are intentionally not treated as alternate source
    inputs here; callers that need an old evidence snapshot must pass the exact
    file path they want to inspect.
    """
    return Path(exe_path)


def create_overkill_runtime(
    exe_path: str | Path,
    *,
    game_root: str | Path | None = None,
    command_tail: bytes | str = b"",
    install_replacements: bool = True,
) -> Runtime:
    """Boot a fresh OVERKILL runtime.  ``install_replacements=False`` = the pure-ASM oracle
    (``--no-replacements``): no recovered hooks, the CPU runs the original code verbatim.

    dos_re's own ``create_runtime`` dropped the all-or-nothing
    ``install_replacements`` flag in favor of the finer-grained
    ``DOS_RE_DISABLE_HOOKS`` env var; this reproduces the old OVERKILL-wide
    switch by uninstalling OVERKILL's own registered hooks after boot.
    Framework-level hooks (e.g. the native BIOS INT 9 keyboard ISR) are not
    game replacements and stay installed either way.
    """
    rt = create_dos_runtime(
        resolve_overkill_exe_path(exe_path),
        game_root=game_root,
        command_tail=command_tail,
    )
    if not install_replacements:
        for key in _dos_re_hook_registry.replacements:
            rt.cpu.replacement_hooks.pop(key, None)
            rt.cpu.hook_names.pop(key, None)
    return rt


def load_overkill_snapshot(
    exe_path: str | Path,
    snapshot_dir: str | Path,
    *,
    game_root: str | Path | None = None,
    trace: bool = False,
) -> Runtime:
    """Load a snapshot for oracle/probe work.

    ``trace`` defaults to **False**: ``dos_re``'s ``CPU8086.trace_enabled`` defaults to True, and
    formatting a trace line on every step costs ~1.7x under CPython and -- far worse -- defeats
    PyPy's JIT entirely (measured on this repo, 20M-step steady state: 236k instr/s traced vs
    399k CPython / 16.3M PyPy untraced).  Every probe that loads a snapshot to *drive* the
    original is an untraced workload; the disassembler (``scripts/lindis.py``) and the zoo xref
    turn tracing back on explicitly.  Pass ``trace=True`` when you need the trace text.
    """
    rt = load_dos_snapshot(
        resolve_overkill_exe_path(exe_path),
        snapshot_dir,
        game_root=game_root,
    )
    rt.cpu.trace_enabled = trace
    repair_object_allocator_cursor(rt)
    return rt


def repair_object_allocator_cursor(rt: Runtime) -> None:
    """Repair snapshots saved after the old 7573 lift corrupted DS:[95DA].

    DS:[95DA] is OVERKILL's free-object scan cursor.  Valid values are the 34
    object slots 2B5C..3294 or the 32CC sentinel that the original allocator
    wraps back to 2B5C.  Older snapshots can contain values beyond the sentinel,
    which overlaps the Tandy draw buffer and makes newly allocated projectiles
    disappear on the next sprite draw.
    """
    cpu = rt.cpu
    mem = cpu.mem
    ds = cpu.s.ds & 0xFFFF
    if not looks_like_overkill_runtime_snapshot(rt):
        return
    cursor = mem.rw(ds, 0x95DA)
    if is_valid_object_allocator_cursor(cursor):
        return
    mem.ww(ds, 0x95DA, 0x32CC)


def looks_like_overkill_runtime_snapshot(rt: Runtime) -> bool:
    cpu = rt.cpu
    mem = cpu.mem
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    return (
        mem.rb(ds, 0x2140) == 0x2C
        and mem.rb(ds, 0x2141) == 0x39
        and mem.rb(ds, 0x2142) == 0x10
        and mem.rw(cs, 0x95BC) in (0, 1, 2)
    )


def is_valid_object_allocator_cursor(cursor: int) -> bool:
    cursor &= 0xFFFF
    if cursor == 0x32CC:
        return True
    if cursor < 0x2B5C or cursor > 0x3294:
        return False
    return ((cursor - 0x2B5C) % 0x38) == 0
