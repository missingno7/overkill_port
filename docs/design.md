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

For the complete reusable workflow, see
`docs/source_port_methodology.md`.  This design document explains the local
architecture that supports that workflow.

## Bootstrap/static-runtime boundary

The original startup path is part of the oracle and extraction layer, not the
final gameplay architecture.  The canonical inputs are the original
`assets/OVERKILL` and `assets/OVERKILL.EXE` files.  Generated conveniences such
as `OVERKILL.UNLZEXE.EXE` and `OVERKILL.OVERLAY.BIN` are noncanonical build or
evidence artifacts only.

The intended source-port shape is:

```text
original files -> bootstrap/extraction -> canonical initialized inner-game image + derived assets -> source-port runtime
```

See `docs/bootstrap_static_boundary.md` and the importable manifest in
`overkill_port/games/overkill/bootstrap_boundary.py`.  Use:

```bash
python -m overkill_port.cli bootstrap-boundary --video tandy --sound adlib --out artifacts/static_runtime_boundary.json
```

to write the current boundary manifest.


## Crystallization Layers

The current runtime intentionally starts below a conventional game engine.  Most
object logic is still represented as verified slot/table behavior: sprites move,
probe tiles, collide, update fields, and call postmove tails.  We do not need to
name every slot as player/enemy/projectile yet.

The intended end state is a layered migration:

```text
8. Modern game / enhanced port layer
7. Semantic game model layer
6. Gameplay archetype layer
5. Game systems layer
4. Runtime object/data model layer
3. Verified lifted routine layer
2. ASM-compatible hook/runtime layer
1. Original binary oracle layer
```

The architecture should let these layers emerge in order.  Do not skip directly
from an address-level hook to a semantic enemy name unless the lower layers have
made that name obvious.  `replacements.py` and hook wrappers live around layers
2-3; `games/overkill/<island>/` modules are mostly layers 3-5; future clean
gameplay models will be layers 6-8.

See `docs/source_port_methodology.md` for the full reusable version of this
pyramid.


## Architectural Layer Rules

A higher layer may only depend on evidence from lower layers. Lower layers must
not import higher layers or interpret their concepts.

```text
asset_codecs        -> bytes and decoded records, never Enemy/Boss
file_io             -> handles, offsets, flags, container records, never gameplay
rendering           -> pixels, planes, cells, sprites, presence lists, never story
collision/runtime   -> slots, fields, probes, overlaps, side effects, never final archetypes
semantic model      -> may read evidence from lower layers
modern layer        -> may use semantic model for enhancements
```

This keeps the source port reversible. A future `EnemyDefinition` must still be
able to point back to the original slot fields, behavior id, verified routine,
and ASM trace that justify it.

Every island should have a compact confidence summary in
`docs/island_truth_tables.md`.

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
  asm.py                 shared 8086-style helper functions
  asset_codecs/          deterministic asset streams and decoders
  file_io/               overlay/container file orchestration
  gameplay/              objects, movement, collision, postmove behavior
  rendering/             coordinates, Tandy/video primitives, layer sprites
  sounds/                timer and PC speaker behavior
```

This split keeps two ideas separate:

- the original binary boundary (`1010:ECF2`),
- the reconstructed game behavior (`decode_lz_asset`, rendering helpers, object
  logic, etc.).

The intended migration path is:

```text
unknown original ASM
  -> staged hook in replacements.py
  -> verified helper in games/overkill/<island>/
  -> thin wrapper remains in replacements.py
```

A module should not grow a parallel copy of behavior that already exists in
another module.  Shared original tails should be factored into helpers named
after their original address, for example `_run_object_bounds_tile_tail_ad60` or
`build_video_offset_tables_0fa3`.

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
