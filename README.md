# OVERKILL Runtime And Source-Port Scaffold

This repository is an evidence-driven runtime/source-port project for
**OVERKILL: The Six-Planet Mega Blast**, a 16-bit DOS game.

The project runs the original executable in a custom 8086 runtime, observes real
state transitions, and gradually replaces understood original routines with
verified Python implementations. The original binary remains the behavioral
oracle throughout the migration.

This is intentionally **not** a general DOS emulator. The runtime implements the
DOS, BIOS, CPU, video, file, timer, and input behavior needed by OVERKILL, and no
more unless the game proves it is required.

## Goals

- Execute the original game deterministically enough to trace and verify it.
- Preserve the original executable as an oracle for every lifted routine.
- Replace small, understood routines with Python hooks.
- Compose proven hooks into larger source-port-like modules over time.
- Keep reverse-engineering findings documented by address and evidence.
- Build toward a readable, testable source-level version of the game.

## Non-Goals

- This is not DOSBox.
- This is not a general x86 emulator.
- This is not a clean-room rewrite from memory or intuition.
- This is not a place for speculative high-level gameplay rewrites.
- Performance improvements are not accepted as proof of correctness.

## Game Files

The repository does **not** ship the original game data.

`assets/` is intended for your local copy of the original files and is ignored by
git. To run the runtime locally, place the expected OVERKILL files there,
including:

```text
assets/OVERKILL
```

and the companion game data files opened by the original loader.

## Project Shape

The runtime is a hybrid:

- unknown original code still executes through the 8086 interpreter,
- known routines are replaced by exact `CS:IP` hooks,
- stable hooks move into game-specific Python modules,
- tests and snapshots keep the original ASM as the oracle.

The important boundary is not "Python versus ASM"; it is "verified versus not
verified".

## Methodology In One Loop

The reusable workflow for this project is:

```text
observe -> classify -> choose boundary -> build ASM oracle -> implement hook -> verify -> document -> move to island
```

New work usually starts as an exact `CS:IP` hook in `replacements.py`.  Once the
behavior is understood, the implementation moves into a coherent game module
under `overkill_port/games/overkill/`, while `replacements.py` keeps only the
address-facing wrapper.  This keeps reverse-engineering flexible without letting
the staging file become the permanent source port.

The full playbook is in `docs/source_port_methodology.md`. The compact project mantra is: do not write a source port first and hope it matches; exhaust truth from the original first, then let the source port crystallize from that evidence.


## Long-Term Shape

The source port is expected to crystallize upward through layers rather than be
rewritten top-down.  Today many gameplay paths are still verified object-slot
logic: fields, sprites, movement, collision, postmove tails, and renderer
presenters.  Over time these should form clearer systems, then archetypes, then
a semantic game model.

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

The rule is: let high-level meaning emerge from verified lower-level evidence.
Do not guess a semantic model just because a sprite or behavior looks familiar.


## Crystallization Rules

The project uses a strict evidence ladder. A higher layer may only be created
from proof in the layer below it. It is fine to investigate rendering, asset
loading, collision, input, and sound in parallel, but their outputs must remain
separate until the evidence converges.

Practical consequences:

- `ObjectSlot` comes before `Enemy`.
- `ObjectKindCandidate` comes before a definitive archetype name.
- Refactors must not change behavior.
- Fixes must not introduce semantic models.
- Lower layers must not import higher layers.
- Every semantic name must be traceable back to original slots, behavior IDs,
  verified routines, and snapshots/traces.

`docs/island_truth_tables.md` tracks per-island confidence: what is known, what
is verified, what is guessed, what remains unknown, and which tests/snapshots
cover it.

## Repository Layout

```text
overkill_port/
  mz.py                 MZ parsing and loading
  memory.py             20-bit real-mode memory model
  cpu.py                dependency-free 8086 interpreter core
  dos.py                narrow DOS/BIOS/port services
  hooks.py              replacement hook registry
  replacements.py       exact CS:IP hook wrappers and staging area
  runtime.py            OVERKILL runtime wiring
  snapshot.py           memory/state snapshot helpers
  hook_verify.py        live differential hook verifier
  frame_verify.py       frame-level oracle comparison helpers
  games/overkill/       lifted game-specific source-port logic
    asm.py              shared 8086-style helper functions
    asset_codecs/       asset streams, checksum, RLE/LZ, decoded asset table
    file_io/            overlay/container file orchestration
    gameplay/           objects, movement, collision, game-state counters
    rendering/          startup graphics, coordinates, video primitives, layer sprites
    sounds/             timer and PC speaker behavior
assets/                 local user-supplied original game files
artifacts/              root kept for live `play_*` captures
  evidence/             non-play evidence snapshots, traces, and probes
  test_oracles/         snapshots used directly by regression tests
docs/                   design notes and reverse-engineering findings
scripts/                convenience runners and RE helpers
tests/                  CPU and replacement regression tests
symbols.json            known addresses, names, hypotheses, and status
RUN_STATUS.md           current checkpoint and recent work
AGENTS.md               durable workflow and agent instructions
```

## Quick Start

Inspect the executable:

```bash
python -m overkill_port.cli info assets/OVERKILL
```

Run a short trace:

```bash
python -m overkill_port.cli trace assets/OVERKILL \
  --game-root assets \
  --steps 5000 \
  --out trace_start.txt
```

Create a snapshot:

```bash
python -m overkill_port.cli snapshot assets/OVERKILL \
  --game-root assets \
  --steps 100000 \
  --trace-tail 128 \
  --out-dir artifacts/evidence/snapshot_after_bootstrap_100k
```

Run tests:

```bash
python scripts/run_tests.py
```

Run the lightweight lint pass directly:

```bash
python scripts/lint.py
```

Launch interactive play/viewer:

```bash
python scripts/play.py
python scripts/play.py --video tandy
python scripts/play.py --video ega
python scripts/play.py --video cga
```

Profile interpreted hotspots:

```bash
python scripts/profile_hotspots.py 2000000
```

Audit source-port island closure signals:

```bash
python scripts/audit_islands.py --all-hooks
```

## Verification Workflow

Every replacement is treated as a proof obligation.

1. Identify the exact original address, such as `1010:ECF2`.
2. Understand the original boundary: entry state, exit IP, stack behavior,
   flags, registers, segment state, memory writes, file offsets, and port
   effects.
3. Run the interpreted original ASM to produce an oracle.
4. Implement a Python replacement hook.
5. Compare hook output against the oracle in tests or live hook verification.
6. Document the finding in `docs/runtime_findings.md` and `symbols.json`.

For focused hook tests, compare registers, flags, segment registers, stack
scratch, touched memory, DOS state, and relevant video/file/port state.

For real runtime paths, use the live verifier:

```bash
python scripts/play.py --verify-hook 1010:ECF2 --verify-stop-on-diff
python scripts/play.py --verify-hooks --verify-require-metadata
```

For rendered behavior, use frame verification where appropriate:

```bash
python scripts/play.py --snapshot artifacts/evidence/snapshot_name --verify-frames
```

## Source-Port Islands

Stable game-specific code belongs under `overkill_port/games/overkill/`.
`replacements.py` should remain the thin address-facing hook layer.

Examples of source-port islands include:

- `asset_codecs`: packed streams, checksum, RLE/LZ, decoded asset tables,
- `overlay`: overlay signature/directory/name/path/XOR helpers,
- `file_io`: overlay/container open/read/seek orchestration,
- `startup_graphics`: startup renderer table and graphics materialization helpers,
- `rendering`: coordinate/address helpers, Tandy/CGA/EGA primitives, layer sprites,
- `gameplay`: object scan, movement, object behavior, postmove, collision tails,
- `sounds`: timer ISR and PC speaker behavior,
- `input_menu`: keyboard polling and interactive wait/yield points.

Use the audit script to see whether an island still has obvious open seams:

```bash
python scripts/audit_islands.py
```

`closed-candidate` means "no known script-detected blockers"; it is a useful
closure signal, not a substitute for oracle evidence.

The asset-codec work now lives under `overkill_port/games/overkill/asset_codecs/`
and is limited to bytes becoming decoded asset data. Overlay helpers, file I/O,
renderer startup materialization, and gameplay counters are separate islands even
when their original addresses are physically near loader or overlay code.

## Artifacts

`artifacts/` is kept intentionally small. It should contain only durable oracle
data, compact caches, and snapshots that are still used by tests, documented
findings, or the current verifier workflow.

Current layout:

```text
artifacts/
  README.md                         retention policy
  hook_coverage_cache.json          compact hook coverage/cost cache
  test_oracles/                     snapshots loaded directly by regression tests
  evidence/                         minimal non-test evidence still in active use
```

Generated local captures should not stay in the repository by default:

```text
artifacts/snapshot_play_*/          live snapshots from scripts/play.py
artifacts/play_*/                   gameplay captures
artifacts/tmp_*/                    one-off stop/verify snapshots
artifacts/frame_verify/             PNG/VRAM frame diff dumps
```

Promote a generated snapshot into `test_oracles/` or `evidence/` only when a
test, documented finding, or active verifier command depends on it. Prune it
once that evidence value is gone.

Snapshot directories usually contain:

```text
memory_1mb.bin
state.json
trace_tail.txt
```

The current headless hook-verifier seed is:

```bash
python scripts/verify_hooks_headless.py \
  --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 \
  --verify-max 1000
```

## Documentation Map

- `README.md`: stable project overview.
- `AGENTS.md`: durable workflow, guardrails, and agent rules.
- `RUN_STATUS.md`: current checkpoint and recent commands.
- `docs/runtime_findings.md`: accumulated reverse-engineering findings.
- `docs/design.md`: runtime architecture notes.
- `docs/source_port_methodology.md`: reusable evidence-driven porting workflow.
- `docs/next_steps.md`: tactical investigation notes when useful.
- `symbols.json`: address labels, hypotheses, and replacement status.

Prefer explicit segment:offset notation (`1010:95C9`) when documenting original
code.

## Development Notes

- Keep the CPU and DOS layers narrow and game-driven.
- Add interpreter instructions only when OVERKILL reaches them.
- Keep hooks readable before making them fast.
- Move verified logic into `overkill_port/games/overkill/` when it becomes a
  coherent game-specific module.
- Avoid broad refactors unless tests and oracle comparisons prove behavior did
  not change.
- The current state of the project lives in `RUN_STATUS.md`, not in this README.
