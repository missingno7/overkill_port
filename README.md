# OVERKILL Runtime And Source-Port Scaffold


## Fast Headless Checks

The reusable `dos_re` layer can be smoke-tested without pygame, pytest, or the
original OVERKILL assets:

```bash
python scripts/run_tests.py --scope dos-re
```

That scope runs only target-neutral CPU, memory/MZ-loader, and hook-verifier
checks.  The runner is dependency-free, supports the repository's `tmp_path`
fixture usage, and isolates each test with a per-test timeout so a bad emulator
loop cannot hang the whole run.  For a specific suspicious test:

```bash
python scripts/run_tests.py tests/test_overkill_hooks.py \
  --name test_tandy_text_glyph_3153_hook_verifies_on_gameplay_snapshot \
  --timeout 5 --fail-fast --no-lint
```

The interactive viewer remains optional.  Install it only on machines that need
`play.py`/SDL display support:

```bash
pip install -e .[viewer]
```

## Bootstrap/static-runtime boundary

The project now treats the original startup path as an oracle/extraction layer,
not as the final source-port architecture.  The only canonical game inputs are:

```text
assets/OVERKILL
assets/OVERKILL.EXE
```

Generated convenience files such as `OVERKILL.UNLZEXE.EXE` or
`OVERKILL.OVERLAY.BIN` must stay out of `assets/` as source inputs.  If the port
needs an unpacked image, screen, table, sound driver, or overlay blob, generate it
deterministically from the original files and treat it as a build/evidence
artifact.

The current boundary manifest can be written with:

```bash
python -m overkill.cli bootstrap-boundary --video tandy --sound adlib --out artifacts/static_runtime_boundary.json
```

The next practical step is materializing a canonical initialized runtime bundle
from the original files.  This runs the historical bootstrap once, stops at an
inner-runtime frontier, writes the normal snapshot files, and adds a reviewable
`static_runtime_bundle.json` with hashes of the PSP, relocated runtime segment,
and optional sound-driver area:

```bash
python -m overkill.cli static-runtime-bundle assets/OVERKILL \
  --game-root assets \
  --video tandy \
  --sound adlib \
  --out-dir artifacts/static_runtime_bundle
```

See `docs/overkill/bootstrap_static_boundary.md` for the policy,
`overkill/bootstrap_boundary.py` for the importable boundary
manifest, and `overkill/static_runtime_bundle.py` for the
materializer.


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

New work usually starts as an exact `CS:IP` hook in `overkill/hooks.py`.  Once the
behavior is understood, the implementation moves into a coherent game module
under `overkill/`, while `overkill/hooks.py` keeps only the
address-facing wrapper.  This keeps reverse-engineering flexible without letting
the staging file become the permanent source port.

The full playbook is in `docs/overkill/source_port_methodology.md`, with package
ownership rules in `docs/architecture/package_boundary.md`. The compact project
mantra is: do not write a source port first and hope it matches; exhaust truth
from the original first, then let the source port crystallize from that
evidence.


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

`docs/overkill/island_truth_tables.md` tracks per-island confidence: what is known, what
is verified, what is guessed, what remains unknown, and which tests/snapshots
cover it.

## Repository Layout

The project is split by role. The reusable RE/VM environment is not allowed to
know the game; the game package owns all OVERKILL addresses, assets, islands, and
source-port findings.

```text
dos_re/                 reusable reverse-engineering runtime
  mz.py                 MZ parsing and loading
  memory.py             20-bit real-mode memory model
  cpu.py                dependency-free 8086 interpreter core
  dos.py                narrow DOS/BIOS/port services
  hooks.py              generic replacement hook registry
  interrupts.py         generic interrupt delivery helpers
  keyboard.py           host input -> emulated keyboard state
  runtime.py            generic DOS-program runtime wiring
  snapshot.py           generic memory/state snapshot helpers
  verification.py       reusable differential hook-verifier engine
  frame_verify.py       reusable frame comparison and diff artifact engine

overkill/               OVERKILL-specific reverse-engineered game layer
  runtime.py            canonical OVERKILL launch/snapshot wiring
  cli.py                OVERKILL commands built on top of dos_re
  hooks.py              exact CS:IP hook registration surface
  verification.py       OVERKILL hook-verifier stop metadata and adapters
  frame_verify.py       OVERKILL frame extraction/render adapter
  coverage.py           OVERKILL island classifier and dashboard
  bootstrap_boundary.py bootstrap/static-runtime boundary manifest
  static_runtime_bundle.py deterministic initialized-runtime materializer
  asm.py                shared 8086-style helper functions
  asset_codecs/         asset streams, checksum, RLE/LZ, decoded asset table
  file_io/              overlay/container file orchestration
  gameplay/             objects, movement, collision, game-state counters
  rendering/            startup graphics, coordinates, video primitives, layer sprites
  sounds/               timer, PC speaker, AdLib/YM3812 driver behavior

nuked_opl3/             vendored optional Nuked-OPL3 CFFI binding
  __init__.py           runtime Python wrapper; safe to import before build
  _ffi_build.py         in-place CFFI build helper
  vendor/               LGPL Nuked-OPL3 C core

docs/
  README.md             documentation map
  architecture/         cross-package boundaries and dependency rules
  dos_re/               reusable DOS RE methodology and framework notes
  overkill/             OVERKILL archaeology, findings, status, and game docs

scripts/                convenience runners and RE helpers
assets/                 local user-supplied original game files
artifacts/              generated snapshots, traces, caches, evidence
tests/                  DOS runtime and OVERKILL regression tests
symbols.json            known OVERKILL addresses, names, hypotheses, and status
AGENTS.md               durable workflow and agent instructions
```

See `docs/README.md` for the documentation map. `dos_re` must stay independent
of OVERKILL. Anything that knows specific addresses, islands, command-tail
semantics, sound-driver segments, frame boundaries, or game assets belongs in
`overkill`.

## Quick Start

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

Run tests:

```bash
python scripts/run_tests.py
```

Run the lightweight lint pass directly:

```bash
python scripts/lint.py
```

Remove local caches/build outputs before packaging or sharing a tree:

```bash
python scripts/clean.py
python scripts/clean.py --artifacts   # also remove unpromoted generated captures
```

Launch interactive play/viewer:

```bash
python scripts/play.py
python scripts/play.py --video tandy
python scripts/play.py --video ega
python scripts/play.py --video cga
```

Render a saved frame/snapshot without SDL:

```bash
python scripts/render_frame.py artifacts/test_oracles/snapshot_play_tandy_20260611_152751 --video tandy --out frame.png
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
6. Document the finding in `docs/overkill/runtime_findings.md` and `symbols.json`.

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

Stable game-specific code belongs under `overkill/`.
`overkill/hooks.py` should remain the thin address-facing hook layer.

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

The asset-codec work now lives under `overkill/asset_codecs/`
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
python scripts/play.py \
  --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 \
  --verify-hooks \
  --verify-max 1000
```

## Documentation Map

- `README.md`: stable project overview.
- `AGENTS.md`: durable workflow, guardrails, and agent rules.
- `docs/overkill/run_status.md`: current checkpoint and recent commands.
- `docs/overkill/runtime_findings.md`: accumulated reverse-engineering findings.
- `docs/overkill/design.md`: runtime architecture notes.
- `docs/dos_re/source_port_methodology.md`: reusable DOS RE workflow.
- `docs/overkill/source_port_methodology.md`: OVERKILL-specific source-port playbook.
- `docs/overkill/next_steps.md`: tactical investigation notes when useful.
- `docs/architecture/third_party.md`: vendored third-party component policy.
- `symbols.json`: address labels, hypotheses, and replacement status.

Prefer explicit segment:offset notation (`1010:95C9`) when documenting original
code.

## Development Notes

- Keep the CPU and DOS layers narrow and game-driven.
- Add interpreter instructions only when OVERKILL reaches them.
- Keep hooks readable before making them fast.
- Move verified logic into `overkill/` when it becomes a
  coherent game-specific module.
- Avoid broad refactors unless tests and oracle comparisons prove behavior did
  not change.
- The current state of the project lives in `docs/overkill/run_status.md`, not in this README.

Run:
    python scripts/play.py [--video cga|ega|tandy] [--sound pc|adlib|roland] [--game-hz 30] [--palette 1h] [--scale 2]

AdLib audio:
    python scripts/play.py --video tandy --sound adlib

`--sound adlib` runs OVERKILL's original optional AdLib driver and forwards its
YM3812 register writes to the SDL viewer.  Audible FM output uses the vendored
`nuked_opl3` CFFI binding in this repository; build the extension once before
expecting PCM output:

```bash
python -m pip install -e .[adlib]
python -m nuked_opl3._ffi_build
```

Without the compiled extension, the VM still models AdLib detection and the
register stream, but the SDL frontend stays silent and reports the missing
backend.  Use `--adlib-audio off` to run the original driver without attempting
PCM output.  If SDL underruns on a machine, increase the PCM chunk size, e.g.
`--adlib-chunk-ms 70`; underrun counts are shown in the window caption when they
occur.

Intro/menu code often waits on `1010:50C9`, which is a hardware retrace wait,
not the `1010:0679` game-frame timer wait.  The viewer paces retrace waits at 60
Hz by default while keeping gameplay at `--game-hz` (~36.4 Hz by default).  Use
`--retrace-hz` only when you intentionally want to diagnose or override that
cadence.

SDL viewer note: intro/menu screens can publish frames from retrace-driven code
rather than the gameplay timer wait.  The viewer therefore keeps the emulated
IRQ0/AdLib ISR alive while waiting for SDL to consume those frames; gameplay
still uses the normal `1010:0679` timer pacing.  The viewer also redraws the last
published frame after window resize/expose events, so static screens remain
visible even when no new VM frame is produced.
