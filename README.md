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
assets/OVERKILL.UNLZEXE.EXE
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
python -m overkill_port.cli info assets/OVERKILL.UNLZEXE.EXE
```

Run a short trace:

```bash
python -m overkill_port.cli trace assets/OVERKILL.UNLZEXE.EXE \
  --game-root assets \
  --steps 5000 \
  --out trace_start.txt
```

Create a snapshot:

```bash
python -m overkill_port.cli snapshot assets/OVERKILL.UNLZEXE.EXE \
  --game-root assets \
  --steps 100000 \
  --trace-tail 128 \
  --out-dir artifacts/evidence/snapshot_after_bootstrap_100k
```

Run tests:

```bash
python scripts/run_tests.py
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

- asset codecs and startup materialization,
- overlay loading and directory scan helpers,
- startup graphics expansion,
- coordinate/address helpers,
- Tandy rendering primitives,
- shared layer sprite dispatch,
- gameplay/object/collision logic once proven.

Use the audit script to see whether an island still has obvious open seams:

```bash
python scripts/audit_islands.py
```

`closed-candidate` means "no known script-detected blockers"; it is a useful
closure signal, not a substitute for oracle evidence.

## Artifacts

`artifacts/` keeps the root focused on live gameplay captures.

Keep the live `play_*` captures in the root of `artifacts/`.
Keep regression-test snapshots in `artifacts/test_oracles/`.
Keep other evidence, scratch traces, and one-off probes in `artifacts/evidence/`
so they stay separate from gameplay snapshots.

Generated scratch traces and one-off probes can be pruned once they stop
carrying evidence value.

Snapshot directories usually contain:

```text
memory_1mb.bin
state.json
trace_tail.txt
```

Do not delete evidence snapshots that justify hooks or findings unless cleanup is
explicitly requested.

## Documentation Map

- `README.md`: stable project overview.
- `AGENTS.md`: durable workflow, guardrails, and agent rules.
- `RUN_STATUS.md`: current checkpoint and recent commands.
- `docs/runtime_findings.md`: accumulated reverse-engineering findings.
- `docs/design.md`: runtime architecture notes.
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
