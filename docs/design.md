# OVERKILL Runtime Architecture

This document describes the durable architecture of the OVERKILL runtime and
source-port scaffold. Current progress belongs in `RUN_STATUS.md`; accumulated
address-level findings belong in `docs/runtime_findings.md`.

## Architectural Goal

The runtime exists to migrate one original DOS game into verified source-level
Python one boundary at a time.

The original executable is always the oracle. The runtime should be capable of:

1. loading the original program,
2. executing unknown 8086 code directly,
3. tracing and snapshotting observable state,
4. replacing proven routines with hooks,
5. verifying hooks against interpreted ASM,
6. moving stable behavior into game-specific source-port modules.

The design should remain narrow. Generic emulator completeness is not a goal.

## Runtime Components

- `mz.py`: DOS MZ parsing, relocation handling, and load-module extraction.
- `memory.py`: 20-bit real-mode memory model, PSP setup, and video-memory
  backing stores.
- `cpu.py`: dependency-free 8086 interpreter for instructions OVERKILL reaches.
- `dos.py`: deterministic DOS, BIOS, file, port, timer, and input services used
  by OVERKILL.
- `hooks.py`: replacement-hook registry keyed by exact runtime `CS:IP`.
- `replacements.py`: thin hook wrappers and staging area for newly lifted code.
- `runtime.py`: wiring for CPU, memory, DOS services, and hook installation.
- `snapshot.py`: full memory/state snapshot save and load helpers.
- `hook_verify.py`: live differential verifier that runs original ASM and hook
  side by side at a replacement boundary.
- `frame_verify.py`: frame-level comparison helpers for video-output behavior.
- `overkill_port/games/overkill/`: game-specific source-port modules for stable
  lifted behavior.

## Address Model

Runtime addresses are written as `CS:IP`.

The DOS loader creates a PSP segment and loads the MZ image after it. Static MZ
`CS:IP` values are relative to the load segment; runtime tracing observes the
relocated real-mode segment.

The general relationship is:

```text
runtime_segment = load_segment + mz_relative_segment
physical        = runtime_segment * 16 + offset
```

Many routines are unpacked, relocated, or patched after load. For executed code,
the runtime memory snapshot is more authoritative than the original file bytes.

## Hook Boundary Model

A replacement hook is registered at the exact runtime address where original
execution would enter the replaced boundary:

```python
@registry.replace(0x1010, 0xECF2, "overkill_lz_decoder_ecf2")
def overkill_lz_decoder_ecf2(cpu):
    ...
```

The hook must leave the same observable state as interpreted ASM at the chosen
continuation:

- registers and segment registers,
- flags,
- `CS:IP`,
- stack pointer and stack scratch,
- touched memory,
- DOS/file/port/video side effects.

Boundaries may be normal routines, far routines, dispatch stubs, loop bodies,
tail jumps, or self-call tricks. The boundary type must be understood before a
hook is added.

## Source-Port Module Model

`replacements.py` is the address-facing layer. It should contain the exact
`@registry.replace(...)` wrappers and any short staging code that still needs
close oracle comparison.

Stable game-specific behavior should move into modules under:

```text
overkill_port/games/overkill/
```

This split keeps two ideas separate:

- the original binary boundary (`1010:ECF2`),
- the reconstructed game behavior (`decode_lz_asset`, rendering helpers, object
  logic, etc.).

## Verification Layers

The project uses several verification layers:

- synthetic interpreted-ASM tests for small routines,
- captured snapshot tests for larger or stateful paths,
- live hook verification during startup or gameplay,
- frame verification for rendered output,
- island audits for closure signals across related modules.

The strongest proof is still oracle equivalence against the original executable.
Audit scripts and coverage reports are triage tools, not proof by themselves.

## DOS And Hardware Model

The DOS/BIOS/port layer should model only behavior OVERKILL observes.

Additions should be driven by an observed call site or port access. Each new
service should document:

- where the original game calls it,
- input registers or port values,
- output registers, flags, memory, or device state,
- any deterministic simplification used by the runtime.

Avoid building a general OS or hardware emulator unless the game requires that
specific behavior.

## Snapshots

Snapshots capture the full machine state needed to resume or compare execution:

```text
memory_1mb.bin
state.json
trace_tail.txt
```

Snapshots are evidence. Keep the ones referenced by tests, findings, or active
investigations. Ad hoc generated traces and probes can be pruned after they stop
serving as evidence.

## Design Pressure

The runtime should gradually move upward:

1. interpreter support for instructions the game reaches,
2. small verified hooks,
3. larger coherent parent-level replacements,
4. source-port islands with closed boundaries,
5. readable game systems that no longer look like isolated hook bodies.

At every stage, preserve the ability to compare back to the original executable.
