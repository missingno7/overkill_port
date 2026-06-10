# AGENTS.md — OVERKILL AI-driven RE runtime/source-port project

These instructions apply to the entire repository. They are written for Codex/AI agents working locally on this project.

## Project goal

Build a narrow, evidence-driven runtime/source-port framework for one specific 16-bit DOS game: **OVERKILL: The Six-Planet Mega Blast**.

This is **not** a general DOSBox clone and should not become one. The original executable remains the behavioral oracle. The intended workflow is:

1. Execute the original DOS code in the custom 8086 runtime.
2. Trace real control flow, memory, registers, files, ports, and interrupts.
3. Understand one small routine at a time.
4. Replace only well-understood routines with Python hooks.
5. Verify each replacement against interpreted ASM using before/after snapshots and regression tests.
6. Keep running the rest of the original binary until enough behavior has been lifted into clean source code.

The long-term shape is a hybrid source port: original ASM still runs where unknown, while known routines are gradually replaced by readable Python implementations and later possibly by higher-level game code.

## Core philosophy

Correctness beats speed. Traceability beats cleverness. Small verified progress beats large intuitive rewrites.

Do not infer game behavior from what “probably” happens in other DOS games. The oracle is this specific executable and its observed state transitions.

Do not rewrite large systems by intuition. If a routine is not understood, trace it, snapshot it, document it, and only then replace a small part of it.

## Current known status

Use `RUN_STATUS.md` and `docs/runtime_findings.md` as the source of truth for the latest checkpoint.

As of checkpoint 8:

- Target executable: `assets/OVERKILL.UNLZEXE.EXE`.
- Original game data files are in `assets/`.
- Confirmed relocated runtime entrypoint: `1010:95C9`.
- The real menu/game main loop is **not confirmed yet**.
- The earlier suspicious `1010:41DA` renderer state was traced to a DOS heap modeling bug, not forced through with a guess.
- `INT 21h AH=4Ah` PSP resize and `AH=48h` distinct allocations now work well enough for startup to continue.
- Current best next investigation target: overlay/container loader path around `254A:04D7..05FB`.

## Repository layout

```text
overkill_port/
  mz.py             MZ EXE parser/loader helpers
  memory.py         20-bit real-mode memory model
  cpu.py            dependency-free 8086 interpreter core
  dos.py            narrow DOS/BIOS/port services for OVERKILL
  hooks.py          replacement hook registry
  replacements.py  verified OVERKILL-specific Python replacements
  runtime.py        runtime wiring for this game
  snapshot.py       save/load full memory + CPU/DOS state
  cli.py            trace/snapshot/continue-snapshot commands
assets/             unpacked target EXE and original game files
artifacts/          generated oracle snapshots and traces
docs/               design notes and runtime findings
scripts/            convenience runners and RE helper scripts
tests/              CPU and replacement regression tests
symbols.json        known routines, labels, and hypotheses
RUN_STATUS.md       current checkpoint status and next target
```

## Standard commands

Run the test suite before and after meaningful changes:

```bash
python -m pytest -q
```

Print EXE metadata:

```bash
python -m overkill_port.cli info assets/OVERKILL.UNLZEXE.EXE
```

Generate a trace from cold start:

```bash
python -m overkill_port.cli trace assets/OVERKILL.UNLZEXE.EXE --game-root assets --steps 5000 --out trace_start.txt
```

Create a full snapshot from cold start:

```bash
python -m overkill_port.cli snapshot assets/OVERKILL.UNLZEXE.EXE \
  --game-root assets \
  --steps 100000 \
  --trace-tail 200 \
  --out-dir artifacts/snapshot_name
```

Stop at a specific address:

```bash
python -m overkill_port.cli snapshot assets/OVERKILL.UNLZEXE.EXE \
  --game-root assets \
  --stop-at 254A:0585 \
  --steps 40000 \
  --trace-tail 200 \
  --out-dir artifacts/snapshot_stop_254a_0585
```

Continue from an existing snapshot:

```bash
python -m overkill_port.cli continue-snapshot assets/OVERKILL.UNLZEXE.EXE \
  artifacts/snapshot_after_psp_heap_fix_30k \
  --game-root assets \
  --steps 50000 \
  --trace-tail 200 \
  --out-dir artifacts/snapshot_continued
```

## How to add a replacement hook safely

A replacement hook must be treated as a proof obligation.

1. Identify the exact original entry address, for example `1010:ECF2`.
2. Confirm whether it is a real callable routine, a loop body, a tail-jump target, a far routine, or a weird self-call trick.
3. Capture a before snapshot stopped exactly at the candidate address.
4. Run the interpreted ASM path to produce the oracle after-state.
5. Implement the Python replacement in `overkill_port/replacements.py` using `@registry.replace(cs, ip, name)`.
6. Preserve all relevant side effects: registers, flags, stack scratch, segment registers, memory writes, file offsets, port reads, and return address behavior.
7. Add or update tests in `tests/test_replacements.py` comparing hook result against interpreted ASM or a captured snapshot pair.
8. Add/update labels in `symbols.json`.
9. Document the finding in `docs/runtime_findings.md` and summarize current status in `RUN_STATUS.md`.
10. Run `python -m pytest -q`.

Never add a hook only because it “looks right”. Every hook must have oracle evidence.

## Hook mechanics

Hooks are registered in `overkill_port/replacements.py`:

```python
from .hooks import registry

@registry.replace(0x1010, 0xECF2, "overkill_lz_decoder_ecf2")
def overkill_lz_decoder_ecf2(cpu):
    ...
```

A hook runs instead of the original instruction at that exact `CS:IP`. It is responsible for putting the CPU into the same state that the original code would have produced at the replacement boundary.

For a normal near-return routine, end by popping the original return IP:

```python
cpu.s.ip = cpu.pop()
```

For a hook that replaces an internal loop or basic block, jump to the exact original continuation address:

```python
cpu.s.ip = 0x1234
```

Do not assume a target uses `RET`. Some OVERKILL routines are deliberately odd. Example: `1010:ED7A` is a loop body ending in `JMP ED26`, not a helper with `RET`. Treating it as a synthetic call corrupts the stack.

## Verification expectations

A good verification test compares at least:

- all general-purpose registers,
- segment registers,
- `IP`,
- flags affected by the original code,
- stack pointer and any stack scratch words left behind,
- touched memory ranges,
- DOS file offsets/open handles when relevant,
- port IO counters/state when relevant.

For small routines, prefer synthetic inputs plus an interpreted ASM oracle. For larger startup paths, prefer captured full snapshots under `artifacts/`.

If full 1 MiB memory comparison is too large for a unit test, compare the touched ranges and document why that is sufficient.

## CPU interpreter rules

`overkill_port/cpu.py` should remain a narrow 8086 interpreter for this game, not a full x86 museum.

When the runtime hits an unsupported opcode:

1. Decode the exact instruction and addressing mode.
2. Implement only the required 8086 behavior, with correct flags for the observed use.
3. Add a focused test in `tests/test_core.py`.
4. Do not add broad 80186/286/386 behavior unless the original executable demonstrably requires it.

Be especially careful with:

- `LOOP` count wrap (`CX=0000` means 65536 iterations),
- rotate/shift flags,
- `REP` segment wrapping,
- `LES`/`LDS`,
- far calls/returns,
- instructions that leave flags undefined on real hardware. If the game observes those flags, use the oracle.

## DOS/BIOS/port model rules

`overkill_port/dos.py` is a narrow deterministic DOS/BIOS model for OVERKILL.

Do not turn it into a general OS. Add only services that the game actually calls.

Important current details:

- PSP starts at segment `1000h`.
- OVERKILL resizes its PSP-owned memory block using `INT 21h AH=4Ah` early in startup.
- `INT 21h AH=48h` must return distinct paragraph allocations. Returning the same segment causes heap aliasing and false renderer corruption.
- File IO must preserve handle offsets correctly because many asset loaders depend on exact offsets in `assets/OVERKILL`.
- VGA status port `03DAh` has a minimal retrace model. Preserve observed port-read behavior when replacing wait loops.

When adding a DOS or BIOS service, document the exact call site and observed register contract.

## Snapshot and artifact rules

Snapshots are evidence. Name them descriptively:

```text
artifacts/snapshot_stop_<addr>_<purpose>/
artifacts/snapshot_before_<routine>/
artifacts/snapshot_after_<routine>/
```

A snapshot directory should contain:

```text
memory_1mb.bin
state.json
trace_tail.txt
```

Keep snapshots that justify hooks. Do not delete evidence snapshots just because they are large unless the user explicitly asks for cleanup.

## Documentation rules

Keep these files current:

- `RUN_STATUS.md`: concise current checkpoint, commands run, tests, latest snapshot, next target.
- `docs/runtime_findings.md`: accumulated RE findings, address meanings, pitfalls, hook explanations.
- `symbols.json`: known addresses and hypotheses.
- `AGENTS.md`: agent workflow and project rules.

Use explicit segment:offset notation (`1010:95C9`) everywhere. Avoid vague names like “the loader” unless the address is also given.

## Style rules

- Write code and comments in English.
- Prefer simple dependency-free Python.
- Keep replacements readable before making them fast.
- Use clear names that include the original address, for example `overkill_lz_decoder_ecf2`.
- Do not hide weird original behavior behind “clean” abstractions until it is documented.
- Avoid broad refactors during RE work unless tests and snapshots prove no behavior changed.

## Current best next steps

At checkpoint 8, continue here unless `RUN_STATUS.md` says otherwise:

1. Audit overlay/container loader path around `254A:04D7..05FB`.
2. Capture stop snapshots at small candidate subroutines inside that path.
3. Identify deterministic header/signature/decode loops.
4. Replace only a small helper first, not the whole asset loader.
5. Verify file offsets, memory writes, registers, flags, and return state against interpreted ASM.
6. Continue toward confirming the real menu/game main loop.

Good candidate investigation commands:

```bash
python -m overkill_port.cli snapshot assets/OVERKILL.UNLZEXE.EXE \
  --game-root assets \
  --stop-at 254A:0585 \
  --steps 40000 \
  --trace-tail 250 \
  --out-dir artifacts/snapshot_stop_254a_0585_overlay_audit

python -m overkill_port.cli continue-snapshot assets/OVERKILL.UNLZEXE.EXE \
  artifacts/snapshot_after_psp_heap_fix_30k \
  --game-root assets \
  --steps 50000 \
  --trace-tail 250 \
  --out-dir artifacts/snapshot_overlay_loader_audit_continued
```

## Things not to do

- Do not replace the whole overlay/container loader by guessing the file format.
- Do not force suspicious renderer states to continue with arbitrary clamps.
- Do not assume corrupted-looking data is a game quirk before auditing CPU/DOS/hook divergence.
- Do not make the emulator more general than needed for OVERKILL.
- Do not remove old snapshots that explain why a hook is correct.
- Do not silently change already verified hooks without updating tests and findings.
- Do not treat performance as proof of correctness.

## Desired end state

The project should eventually allow this development loop:

1. Run original OVERKILL code until an understood routine is reached.
2. Swap that routine for Python source-port logic.
3. Confirm the same observable state as the original code.
4. Repeat until the menu, game loop, rendering, input, audio, objects, collision, and level logic are source-level and testable.

The original binary should remain available as the oracle throughout the process.
