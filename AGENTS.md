# AGENTS.md - OVERKILL evidence-driven source-port project

These instructions apply to the entire repository. They are written for AI
agents and humans working locally on the OVERKILL runtime/source-port project.

## Project Purpose

Build a narrow, evidence-driven runtime and source-port framework for one
specific 16-bit DOS game: **OVERKILL: The Six-Planet Mega Blast**.

This project is not a general DOS emulator and should not drift into one. The
original executable remains the behavioral oracle. The long-term shape is a
hybrid source port:

1. Run the original DOS code in the custom 8086 runtime.
2. Trace real control flow, memory, registers, files, ports, and interrupts.
3. Understand one bounded routine or subsystem at a time.
4. Replace only proven behavior with Python hooks.
5. Verify each replacement against interpreted original ASM.
6. Move stable replacements into readable game-specific modules.
7. Keep the original binary available as the oracle until the source port is
   complete enough to stand on its own.

## Working Principles

Correctness beats speed. Traceability beats cleverness. Small verified progress
beats large intuitive rewrites.

Do not infer behavior from what "probably" happens in other DOS games. The only
oracle is this executable and its observed state transitions.

Do not replace large systems by intuition. If a routine is not understood, trace
it, snapshot it, document it, and replace the smallest coherent unit whose
boundary is proven.

Performance work is welcome only when it preserves oracle equivalence. A faster
wrong replacement is a regression.

## Sources of Truth

Use these files for different kinds of truth:

- `RUN_STATUS.md`: current checkpoint, latest commands, recent decisions, and
  near-term work.
- `docs/runtime_findings.md`: accumulated reverse-engineering findings,
  address meanings, pitfalls, and hook explanations.
- `symbols.json`: known addresses, names, hypotheses, and replacement status.
- `tests/`: executable proof for CPU behavior and replacement equivalence.
- `artifacts/`: evidence snapshots and traces used by tests or findings.

Keep durable policy here. Keep time-sensitive status in `RUN_STATUS.md`.

## Repository Layout

```text
overkill_port/
  mz.py                 MZ EXE parser/loader helpers
  memory.py             20-bit real-mode memory model
  cpu.py                dependency-free 8086 interpreter core
  dos.py                narrow DOS/BIOS/port services for OVERKILL
  hooks.py              replacement hook registry
  replacements.py       exact CS:IP hook wrappers and staging area
  runtime.py            runtime wiring for this game
  snapshot.py           save/load full memory + CPU/DOS state
  hook_verify.py        live differential hook verifier
  frame_verify.py       frame-level oracle comparison helpers
  games/overkill/       lifted game-specific source-port logic
assets/                 user-supplied original game files
artifacts/              generated oracle snapshots, traces, and evidence
docs/                   design notes and runtime findings
scripts/                convenience runners and RE helpers
tests/                  CPU and replacement regression tests
symbols.json            known routines, labels, and hypotheses
RUN_STATUS.md           current checkpoint and next useful work
```

## Standard Commands

Run the project test suite:

```bash
python scripts/run_tests.py
```

Print executable metadata:

```bash
python -m overkill_port.cli info assets/OVERKILL.UNLZEXE.EXE
```

Generate a trace from cold start:

```bash
python -m overkill_port.cli trace assets/OVERKILL.UNLZEXE.EXE \
  --game-root assets \
  --steps 5000 \
  --out trace_start.txt
```

Create a full snapshot from cold start:

```bash
python -m overkill_port.cli snapshot assets/OVERKILL.UNLZEXE.EXE \
  --game-root assets \
  --steps 100000 \
  --trace-tail 200 \
  --out-dir artifacts/evidence/snapshot_name
```

Stop at a specific address:

```bash
python -m overkill_port.cli snapshot assets/OVERKILL.UNLZEXE.EXE \
  --game-root assets \
  --stop-at 1010:ECF2 \
  --steps 40000 \
  --trace-tail 200 \
  --out-dir artifacts/evidence/snapshot_stop_1010_ecf2
```

Continue from an existing snapshot:

```bash
python -m overkill_port.cli continue-snapshot assets/OVERKILL.UNLZEXE.EXE \
  artifacts/evidence/snapshot_name \
  --game-root assets \
  --steps 50000 \
  --trace-tail 200 \
  --out-dir artifacts/evidence/snapshot_continued
```

Run the island closure audit:

```bash
python scripts/audit_islands.py --all-hooks
```

## Replacement Hook Rules

A replacement hook is a proof obligation.

Before adding or changing a hook:

1. Identify the exact original entry address, for example `1010:ECF2`.
2. Confirm the boundary type: near routine, far routine, loop body, tail-jump
   target, dispatch stub, self-call trick, or parent block.
3. Understand entry state, exit IP, stack behavior, flags, registers, segment
   registers, memory writes, file offsets, port effects, and DOS/BIOS effects.
4. Produce an oracle by running the interpreted original ASM.
5. Implement the replacement as a thin hook wrapper in `replacements.py` and put
   stable game-specific behavior under `overkill_port/games/overkill/` when it
   belongs to an established island.
6. Add or update hook-verifier metadata in `hook_verify.py`.
7. Add an oracle/regression test in `tests/`.
8. Update `symbols.json` and `docs/runtime_findings.md`.
9. Run the test suite.

Never add a hook because it looks right. Every hook must have oracle evidence.

## Hook Mechanics

Hooks are registered by exact runtime `CS:IP`:

```python
from .hooks import registry

@registry.replace(0x1010, 0xECF2, "overkill_lz_decoder_ecf2")
def overkill_lz_decoder_ecf2(cpu):
    ...
```

A hook runs instead of the original instruction at that address. It must leave
the CPU and observable machine state exactly where the original code would have
left them at the chosen boundary.

For a normal near-return routine:

```python
cpu.s.ip = cpu.pop()
```

For a far-return routine:

```python
cpu.s.ip = cpu.pop()
cpu.s.cs = cpu.pop()
```

For an internal block or loop replacement:

```python
cpu.s.ip = 0x1234
```

Do not assume a target returns. Some OVERKILL routines are loop bodies, jump
targets, dispatch stubs, or deliberately odd self-call routines.

## Verification Expectations

Good replacement tests compare the original interpreted ASM against the hook.
Compare as much as the boundary can observe:

- general-purpose registers,
- segment registers,
- `CS:IP`,
- flags,
- stack pointer and stack scratch around `SS:SP`,
- touched memory ranges,
- DOS handles and file offsets,
- port counters/state,
- video memory or rendered frames when appropriate.

For small routines, prefer synthetic fixtures plus interpreted ASM. For larger
paths, use captured snapshots under `artifacts/`. If full memory comparison is
too expensive, compare named touched ranges and document why that is enough.

Use live hook verification when exercising real gameplay or startup paths:

```bash
python scripts/play.py --verify-hook 1010:ECF2 --verify-stop-on-diff
python scripts/play.py --verify-hooks --verify-require-metadata
```

## Source-Port Islands

As behavior becomes stable, move it out of `replacements.py` into established
game-specific modules under `overkill_port/games/overkill/`. Keep
`replacements.py` as the exact address-facing wrapper layer.

When closing an island, look for:

- hook-verifier metadata coverage,
- direct oracle/regression tests,
- no open candidate/frontier symbols,
- no bounded-original or fail-fast seams in the module,
- no unknown original-code paths in representative traces.

Use `scripts/audit_islands.py` as a closure signal, not as proof. The original
binary and tests remain the proof.

## CPU Interpreter Rules

`overkill_port/cpu.py` should remain a narrow 8086 interpreter for this game.

When the runtime hits an unsupported opcode:

1. Decode the exact instruction and addressing mode.
2. Implement only the required 8086 behavior.
3. Match flags for the observed use.
4. Add a focused test in `tests/test_core.py`.
5. Avoid broad 80186/286/386 behavior unless the executable proves it is needed.

Be especially careful with:

- `LOOP` count wrap (`CX=0000` means 65536 iterations),
- rotate/shift flags,
- `REP` segment wrapping,
- `LES` / `LDS`,
- far calls and returns,
- undefined flags if the game observes them.

## DOS, BIOS, And Port Rules

`overkill_port/dos.py` is a narrow deterministic model for OVERKILL.

Do not turn it into a general OS. Add only services the game actually calls.
When adding a DOS, BIOS, or port behavior, document the exact call site and the
observed register contract.

Important invariants:

- PSP starts at segment `1000h` unless loader design changes intentionally.
- DOS allocation and resize calls must preserve distinct memory blocks.
- File IO must preserve handle offsets exactly.
- Port behavior should be deterministic and tied to observed game needs.
- Timer/input/video shortcuts must be verified against observed behavior.

## Snapshot And Artifact Rules

Snapshots are evidence. Name them descriptively:

```text
artifacts/evidence/snapshot_stop_<addr>_<purpose>/
artifacts/evidence/snapshot_before_<routine>/
artifacts/evidence/snapshot_after_<routine>/
```

A snapshot directory normally contains:

```text
memory_1mb.bin
state.json
trace_tail.txt
```

Keep artifacts that justify hooks, tests, or findings. Do not delete evidence
snapshots simply because they are large unless the user explicitly asks for
cleanup. Generated scratch traces that are not referenced by tests or docs may
be pruned.

## Documentation Rules

Use explicit segment:offset notation (`1010:95C9`) when discussing original
addresses. Avoid vague names like "the loader" unless the address is also
given.

Update documentation with the same discipline as code:

- `symbols.json` for names and status.
- `docs/runtime_findings.md` for durable reverse-engineering facts.
- `RUN_STATUS.md` for current progress and recently run commands.
- `README.md` for project overview and contributor onboarding.
- `AGENTS.md` for durable agent workflow and guardrails.

## Style Rules

- Write code and comments in English.
- Prefer simple dependency-free Python.
- Keep replacements readable before making them fast.
- Use names that include original addresses, such as
  `overkill_lz_decoder_ecf2`.
- Do not hide weird original behavior behind clean abstractions until it is
  documented.
- Avoid broad refactors during RE work unless tests and oracle snapshots prove
  behavior did not change.
- Preserve user or generated work in the tree unless explicitly asked to clean
  it up.

## Things Not To Do

- Do not replace whole systems by guessing formats or intent.
- Do not force suspicious states forward with arbitrary clamps.
- Do not treat corrupted-looking data as a game quirk before checking CPU,
  DOS, memory, and hook divergence.
- Do not make the emulator more general than OVERKILL requires.
- Do not remove evidence snapshots that explain a hook.
- Do not silently change verified hooks without updating tests and findings.
- Do not treat performance as proof of correctness.

## Desired End State

The project should support this loop:

1. Run original OVERKILL code until an understood boundary is reached.
2. Swap that boundary for Python source-port logic.
3. Confirm the same observable state as the original code.
4. Repeat until menu, gameplay, rendering, input, audio, objects, collision,
   level transitions, and resource loading are source-level and testable.

The original binary remains the oracle throughout the migration.
