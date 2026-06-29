# OVERKILL Runtime & Evidence-Driven Source Port

> A custom 8086/DOS runtime and reverse-engineering framework for rebuilding
> **OVERKILL: The Six-Planet Mega Blast** from the original executable outward.

This project is not trying to write a new game that merely looks like OVERKILL.
It runs the original 16-bit DOS program, treats the binary as the behavioral
oracle, and gradually replaces proven ASM routines with verified Python code.
Over time, those verified routines are promoted upward into recovered,
source-like game systems that can become the basis of a native source port.

```text
original OVERKILL binary
        ↓
custom 8086 + DOS runtime
        ↓
interpreted ASM oracle traces
        ↓
verified CS:IP Python hooks
        ↓
recovered views/adapters/domain/systems
        ↓
future native source-port core
```

The important rule is simple:

> Do not invent the source port. Let it crystallize from verified evidence.

---

## What makes this project interesting?

- It is a **runtime built for one specific DOS game**, not a general emulator.
- The original executable remains runnable and comparable at every step.
- Each lifted hook can be verified against interpreted original ASM.
- Gameplay logic is being moved upward gradually, not rewritten top-down.
- The project now has a clean split between:
  - low-level VM/runtime code,
  - address-facing hooks,
  - DOS-memory views and adapters,
  - pure recovered gameplay/domain systems.

This means the repo is both a reverse-engineering tool and the beginning of a
source-port scaffold.

---

## Start here

| I want to... | Read / run |
| --- | --- |
| Understand the project goal / vision | `docs/overkill/game_recovery_lifecycle.md` (the lifecycle + the canonical doc map) |
| Know what to do next / run the loop | `docs/overkill/overnight_endgame_execution.md` (the one canonical `/goal` brief) |
| See the latest known state | `docs/overkill/run_status.md` |
| Work as an AI agent | `AGENTS.md` |
| Understand the method | `docs/overkill/source_port_methodology.md` |
| Understand the target architecture | `docs/overkill/semantic_crystallization_plan.md` |
| See recovered source-layer rules | `docs/overkill/recovered_source_layer.md` |
| Check current address knowledge | `symbols.json` and `docs/overkill/island_truth_tables.md` |
| Run fast non-viewer tests | `python scripts/run_tests.py --scope dos-re` |
| Play / verify the game | `python scripts/play.py --video tandy --sound adlib` |

---

## Current direction

The project is moving through two connected migrations:

1. **ASM → verified hooks**
   - Unknown original code still runs through the interpreter.
   - Understood routines become exact `CS:IP` hooks.
   - Hook output is compared against original ASM state: registers, flags,
     memory, stack, files, ports, and continuations.

2. **Verified hooks → recovered source layer**
   - Stable hook logic moves out of address-shaped code.
   - DOS state is projected through views/adapters.
   - Pure gameplay decisions live in `overkill/recovered/domain` and
     `overkill/recovered/systems`.
   - Those pure layers must not depend on `cpu`, `mem`, registers, flags,
     segment offsets, or verifier continuations.

The current crystallization target is deliberately conservative: object slots,
collision primitives, coordinate helpers, HUD/status composition, renderer
commands, and other structures that multiple verified routines already point to.

---

## Repository map

```text
dos_re/                     reusable narrow DOS reverse-engineering runtime
  cpu.py                    dependency-free 8086 interpreter core
  memory.py                 20-bit real-mode memory model
  dos.py                    narrow DOS/BIOS/port services
  hooks.py                  generic replacement hook registry
  runtime.py                generic DOS-program runtime wiring
  snapshot.py               memory/state snapshot helpers
  verification.py           reusable differential hook verifier
  frame_verify.py           reusable frame comparison engine

overkill/                   OVERKILL-specific game/runtime layer
  hooks.py                  exact CS:IP hook registration surface
  runtime.py                canonical launch/snapshot wiring
  cli.py                    command-line helpers built on dos_re
  verification.py           hook verifier stop metadata and game adapters
  coverage.py               island classifier and coverage summaries
  gameplay/                 lifted gameplay helpers still close to ASM shape
  rendering/                startup graphics, sprites, Tandy/CGA/EGA primitives
  sounds/                   timer, PC speaker, AdLib/YM3812 driver behavior
  asset_codecs/             checksum, packed streams, RLE/LZ, asset tables
  file_io/                  overlay/container file orchestration
  recovered/                source-port crystallization layer
    views/                  DOS-memory overlays; may know offsets/segments
    adapters/               CPU/memory projection and ASM flag/register glue
    domain/                 pure copied source-like records
    systems/                pure gameplay/system functions

nuked_opl3/                 optional vendored Nuked-OPL3 CFFI binding

docs/                       documentation map, methodology, findings, status
scripts/                    runners, audits, cleanups, profiling, viewer tools
assets/                     local user-supplied original game files; gitignored
artifacts/                  snapshots, traces, caches, verifier evidence
tests/                      CPU/runtime/hook/recovered-layer regression tests
symbols.json                known addresses, names, hypotheses, statuses
AGENTS.md                   durable guardrails for AI agents and humans
```

`dos_re` must stay game-independent. Anything that knows OVERKILL addresses,
assets, hooks, islands, command-tail behavior, or game-specific frame semantics
belongs under `overkill`.

---

## Recovered source-port layers

The recovered layer exists so the upper game logic can eventually run without the
DOS VM.

```text
hooks        exact original address/continuation wrappers
adapters     project DOS memory/register state into source-like data
views        typed overlays over original memory structures
records      pure copied data structures
systems      pure gameplay decisions
```

Current package boundary:

```text
overkill/recovered/views/       may know original offsets, segments, memory layout
overkill/recovered/adapters/    may know CPU/memory and preserve ASM-visible effects
overkill/recovered/domain/      must be pure; no CPU, memory, hooks, offsets
overkill/recovered/systems/     must be pure; no CPU, memory, hooks, offsets
```

Enforce this with:

```bash
python scripts/audit_recovered_layers.py
python scripts/lint.py
```

The intended shape of a lifted routine is:

```text
hook wrapper
  → adapter reads DOS state
  → pure recovered system makes the gameplay decision
  → adapter writes ASM-compatible registers/flags/memory
  → hook returns to the verified continuation
```

This prevents duplicated gameplay logic while still preserving exact original
behavior.

---

## Quick start

### 1. Install the project

```bash
python -m pip install -e .
```

For the SDL viewer:

```bash
python -m pip install -e .[viewer]
```

For audible AdLib/FM output:

```bash
python -m pip install -e .[adlib]
python -m nuked_opl3._ffi_build
```

Without the compiled AdLib backend, the VM can still model detection and YM3812
register writes, but the SDL frontend remains silent. Use `--adlib-audio off` if
you want to run the original AdLib path without PCM output.

### 2. Add original game files

This repository does **not** ship the original game data.

Place your local copy under `assets/`, for example:

```text
assets/OVERKILL
assets/OVERKILL.EXE
```

The canonical source inputs are the original files. Generated convenience files
such as unpacked executables or overlay blobs must be treated as build/evidence
artifacts, not source assets.

### 3. Run fast checks

```bash
python scripts/run_tests.py --scope dos-re
python scripts/lint.py
```

### 4. Launch the game

```bash
python scripts/play.py --video tandy --sound adlib
```

Other useful variants:

```bash
python scripts/play.py --video tandy
python scripts/play.py --video ega
python scripts/play.py --video cga
python scripts/play.py --snapshot artifacts/evidence/<snapshot-dir>
```

---

## Verification workflow

Every replacement is a proof obligation.

```text
observe
  → classify
  → choose boundary
  → build ASM oracle
  → implement hook
  → verify
  → document
  → move upward when stable
```

For a focused hook:

```bash
python scripts/play.py --verify-hook 1010:ECF2 --verify-stop-on-diff
```

For broad live verification:

```bash
python scripts/play.py --verify-hooks --verify-require-metadata
```

For previewing while verifying:

```bash
python scripts/play.py \
  --demo artifacts/demos/<demo-name> \
  --verify-hooks \
  --verify-preview \
  --sound adlib
```

For frame-level verification:

```bash
python scripts/play.py --snapshot artifacts/evidence/<snapshot-dir> --verify-frames
```

For current island closure signals:

```bash
python scripts/audit_islands.py --all-hooks
```

`closed-candidate` means no known script-detected blockers; it is a useful
signal, not a substitute for oracle evidence.

---

## Repro artifacts and debugging

The runtime can preserve hard-to-reach failures.

When replaying a long demo, hook divergence can create a shorter suffix/repro
demo under:

```text
artifacts/repros/
```

Hook-verifier divergence repros are captured from the verifier's **pre-hook**
clone whenever possible, not from the already-mutated live runtime after the
mismatch.  Frame-verifier divergence repros similarly save the candidate runtime
before the first divergent frame.  Check `input_demo.json`/`repro.json` metadata
for `repro_state` values such as `pre_hook` or
`candidate_pre_divergent_frame`.

Interactive crashes can also save a crash snapshot with enough VM state to retry
from the failure point:

```bash
python scripts/play.py --snapshot artifacts/repros/<crash-dir> --video tandy --sound adlib
```

Typical snapshot contents:

```text
memory_1mb.bin
state.json
trace_tail.txt
repro.json        # for repro/crash artifacts when available
```

---

## Runtime world / level-editor probes

These commands help turn live verified snapshots into source-like evidence for
future level editor and source-port work:

```text
python scripts/dump_world.py --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --active-only --summary -o artifacts/world_dump_demo_20260616_000527_start.json

python scripts/trace_world_writes.py --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --max-steps 20000 --max-events 2000 \
  -o artifacts/world_write_trace_demo_20260616_000527_enriched_20000.json

python scripts/summarize_world_writes.py \
  artifacts/world_write_trace_demo_20260616_000527_enriched_20000.json \
  -o artifacts/world_write_summary_demo_20260616_000527_enriched_20000.json --text
```

`dump_world.py` projects recovered object/effect slots, pointer tables, boss
group pointers, and important globals into JSON.  `trace_world_writes.py` traces
writes to those regions and decorates each event with writer island/symbol plus
a decoded target such as `effect_contact_slots_23b4[3].logic_id`.
`summarize_world_writes.py` groups those events by writer and field so
materialisation/setup routines can be found from evidence instead of guessed.

## Useful commands

Inspect the executable:

```bash
python -m overkill.cli info assets/OVERKILL
```

Run a short trace:

```bash
python -m overkill.cli trace assets/OVERKILL \
  --game-root assets \
  --steps 5000 \
  --out trace_start.txt
```

Create a snapshot:

```bash
python -m overkill.cli snapshot assets/OVERKILL \
  --game-root assets \
  --steps 100000 \
  --trace-tail 128 \
  --out-dir artifacts/evidence/snapshot_after_bootstrap_100k
```

Render a saved frame without SDL:

```bash
python scripts/render_frame.py \
  artifacts/evidence/<snapshot-dir> \
  --video tandy \
  --out frame.png
```

Profile interpreted hotspots:

```bash
python scripts/profile_hotspots.py 2000000
```

Clean generated local outputs:

```bash
python scripts/clean.py
python scripts/clean.py --artifacts
```

---

## Bootstrap/static-runtime boundary

The project treats the original startup path as an oracle/extraction layer, not
as the final source-port architecture.

Write the current bootstrap boundary manifest:

```bash
python -m overkill.cli bootstrap-boundary \
  --video tandy \
  --sound adlib \
  --out artifacts/static_runtime_boundary.json
```

Materialize an initialized runtime bundle from the original files:

```bash
python -m overkill.cli static-runtime-bundle assets/OVERKILL \
  --game-root assets \
  --video tandy \
  --sound adlib \
  --out-dir artifacts/static_runtime_bundle
```

See `docs/overkill/bootstrap_static_boundary.md`,
`overkill/bootstrap_boundary.py`, and `overkill/static_runtime_bundle.py`.

---

## Documentation map

| Document | Purpose |
| --- | --- |
| `AGENTS.md` | Durable workflow and guardrails for AI agents/humans |
| `docs/README.md` | Full documentation index |
| `docs/overkill/run_status.md` | Current checkpoint, recent validations, next work |
| `docs/overkill/semantic_crystallization_plan.md` | Main plan for lifting verified behavior into recovered source layers |
| `docs/overkill/recovered_source_layer.md` | Current `views/adapters/domain/systems` split |
| `docs/overkill/source_port_methodology.md` | OVERKILL-specific source-port playbook |
| `docs/dos_re/source_port_methodology.md` | Reusable DOS RE methodology |
| `docs/overkill/runtime_findings.md` | Accumulated reverse-engineering findings |
| `docs/overkill/island_truth_tables.md` | Per-island evidence, confidence, guesses, frontiers |
| `docs/architecture/package_boundary.md` | Package ownership and dependency rules |
| `docs/architecture/third_party.md` | Vendored third-party policy |
| `symbols.json` | Address labels, hypotheses, hook status |

Prefer explicit segment:offset notation such as `1010:95C9` when documenting
original code.

---

## Development rules

- Fidelity first, readability second, meaning third.
- Do not add high-level gameplay names without evidence.
- Do not duplicate gameplay decisions across hooks and recovered systems.
- Keep `overkill/hooks.py` as a thin address-facing wrapper layer.
- Promote stable behavior upward only when the core decision can be expressed
  without CPU/memory/register/flag dependencies.
- Keep `dos_re` independent of OVERKILL.
- Run verifier, audit, and focused tests after behavioral changes.
- Keep durable policy in docs; keep time-sensitive status in
  `docs/overkill/run_status.md`.

This project should get cleaner because evidence converges, not because a model
was guessed early.
