from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cpu import CPU8086, CPUState
from .dos import DOSMachine
from .memory import LoadedProgram, load_mz_program
from .hooks import registry
from . import replacements  # noqa: F401 - registers built-in OVERKILL hooks


LEGACY_UNPACKED_EXE = "OVERKILL.UNLZEXE.EXE"
ORIGINAL_CONTAINER_EXE = "OVERKILL"


@dataclass
class Runtime:
    program: LoadedProgram
    cpu: CPU8086
    dos: DOSMachine


def resolve_exe_path(exe_path: str | Path) -> Path:
    """Resolve OVERKILL's canonical original executable/container.

    Older project commands and snapshots refer to the generated
    ``OVERKILL.UNLZEXE.EXE`` convenience file.  The source of truth is now the
    original extensionless ``OVERKILL`` MZ/container.  Keep the legacy spelling
    as an alias when the generated file is absent so old evidence can still be
    loaded without reintroducing that generated asset.
    """
    path = Path(exe_path)
    if path.name.upper() == LEGACY_UNPACKED_EXE and not path.exists():
        candidate = path.with_name(ORIGINAL_CONTAINER_EXE)
        if candidate.exists():
            return candidate
    return path


def create_runtime(
    exe_path: str | Path,
    *,
    game_root: str | Path | None = None,
    command_tail: bytes | str = b"",
) -> Runtime:
    exe_path = resolve_exe_path(exe_path)
    if isinstance(command_tail, str):
        command_tail = command_tail.encode("ascii")
    program = load_mz_program(exe_path, command_tail=command_tail)
    state = CPUState(
        ax=0,
        bx=0,
        cx=0,
        dx=0,
        sp=program.initial_sp,
        bp=0,
        si=0,
        di=0,
        cs=program.entry_cs,
        ip=program.entry_ip,
        ds=program.psp_segment,
        es=program.psp_segment,
        ss=program.initial_ss,
    )
    cpu = CPU8086(program.memory, state)
    root = Path(game_root) if game_root else Path(exe_path).parent
    dos = DOSMachine(root)
    dos.seed_initial_memory_block(program.psp_segment)
    cpu.interrupt_handler = dos.interrupt
    cpu.port_reader = dos.port_read
    cpu.port_writer = dos.port_write
    registry.install(cpu)
    return Runtime(program, cpu, dos)
