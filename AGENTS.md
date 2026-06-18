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

- `docs/overkill/run_status.md`: current checkpoint, latest commands, recent decisions, and
  near-term work.
- `docs/overkill/semantic_crystallization_plan.md`: durable target architecture
  for promoting verified hooks upward into recovered source-port code. Start here
  before refactoring gameplay logic across layers.
- `docs/overkill/recovered_source_layer.md`: current `views`/`adapters`/`domain`/`systems`
  split and the already crystallized source-like seed.
- `docs/overkill/runtime_findings.md`: accumulated reverse-engineering findings,
  address meanings, pitfalls, and hook explanations.
- `docs/overkill/island_truth_tables.md`: per-island confidence, known facts, guesses,
  frontiers, staged hooks, and test/snapshot coverage.
- `symbols.json`: known addresses, names, hypotheses, and replacement status.
- `tests/`: executable proof for CPU behavior and replacement equivalence.
- `artifacts/`: evidence snapshots and traces used by tests or findings.

Keep durable policy here. Keep time-sensitive status in `docs/overkill/run_status.md`.

## Canonical Workflow

Use the same loop for OVERKILL and for any future game handled by this
runtime-first source-port method:

```text
observe -> classify -> choose boundary -> build ASM oracle -> implement hook -> verify -> document -> move to island
```

The reusable DOS RE process is documented in
`docs/dos_re/source_port_methodology.md`.  The OVERKILL-specific playbook is in
`docs/overkill/source_port_methodology.md`. Treat those files as the project
methodology and this `AGENTS.md` as the local guardrail sheet.

Important staging rule:

- new, uncertain, or address-shape-sensitive replacements may start in
  `overkill/hooks.py`;
- once the subsystem is understood, move the behavior into
  `overkill/<island>/`;
- leave only the exact `CS:IP` registration wrapper in `overkill/hooks.py`;
- before adding a helper, search for an existing tail/helper with the same
  original address or continuation so the code does not grow duplicate
  implementations.



## Logic Crystallization Rule

The project grows upward through layers.  Do not force a high-level game model
before the lower layers prove it.  The useful end-state pyramid is:

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

When working on objects, it is acceptable and often correct to describe them as
slots with sprite/layer/logic-id/movement/collision fields.  Promote them to
player/enemy/projectile/pickup/boss archetypes only when multiple verified
routines make that identity stable.

A semantic name must be reversible back to evidence:

```text
semantic name -> runtime slot/fields -> verified lifted routine -> original ASM trace/snapshot
```

If that chain does not exist, use a candidate name with evidence and confidence
instead of a definitive gameplay entity.

### Layer Boundaries For Tasks

Every non-trivial task should state which layer it is working in. Examples:

```text
Work only in the verified lifted routine layer.
Do not introduce high-level gameplay abstractions.
Preserve CPU-visible side effects exactly.
Move implementation out of overkill/hooks.py into rendering/ega.py.
```

```text
Work in the runtime object model layer.
Do not classify enemies yet.
Extract object slot accessors and debug dumps showing active slots,
coordinates, sprite refs, behavior ids, and state changes.
```

```text
Work in the semantic classification layer.
Use existing traces only.
Do not change runtime behavior.
Produce candidate classifications with evidence, not hardcoded gameplay logic.
```

Hard separation:

```text
refactor task != fix task
fix task != semantic modeling task
semantic task != renderer cleanup task
```

### Dependency Direction

Lower layers must not import higher layers:

```text
asset_codecs        must not know Enemy
rendering           must not know Boss
collision           must not know level story
object_runtime      must not know modern UI
semantic model      may read lower-layer evidence
modern renderer     may read semantic model
```

Dependencies point upward only:

```text
original oracle -> ASM runtime -> lifted routines -> runtime model -> systems -> semantic entities -> modern port
```



## Recovered Source-Port Promotion Rules

The project is now explicitly promoting verified behavior upward into recovered
source-port layers. Treat this as a gradual crystallization of the original
source-code shape, not as a top-down rewrite.

Current recovered package boundary:

```text
overkill/recovered/views/       DOS-memory overlays; may know offsets/segments
overkill/recovered/adapters/    CPU/memory projection and ASM flag glue
overkill/recovered/domain/      pure copied source-like records
overkill/recovered/systems/     pure gameplay/system functions
```

Hard rule: `overkill.recovered.domain` and `overkill.recovered.systems` must not
import or refer to CPU, memory, `dos_re`, hooks, views, adapters, original
segment offsets, or verifier continuations. The pure layers are the future
native source-port core. Their boundary is enforced by:

```bash
python scripts/audit_recovered_layers.py
python scripts/lint.py
```

Do not duplicate gameplay decisions. Once a decision has a pure system function,
the hook should only be address/continuation glue and the adapter should only
project DOS state, call the pure function, and preserve ASM-visible
register/flag side effects. If the adapter replays the old compare sequence for
verifier compatibility, it should assert that the pure system agrees.

Promotion direction:

```text
ASM trace -> verified hook -> lifted island helper -> view/adapter -> domain record -> pure system
```

Only promote code upward when the core decision can be expressed without
`cpu`/`mem`/registers/flags and the behavior has an evidence root in exact ASM
addresses, tests, snapshots, or repeated memory-layout observations.

See `docs/overkill/semantic_crystallization_plan.md` before any non-trivial
refactor in gameplay, collision, rendering, HUD, input, or object runtime.


## Hard Anti-Chaos Rules

1. Fidelity first, readability second, meaning third.
2. Do not add high-level gameplay names without evidence.
3. Refactors must not change behavior.
4. Fixes must not introduce semantic models.
5. `overkill/hooks.py` should become registry glue only.
6. `ObjectSlot` before `Enemy`; candidate before definitive name.
7. Every semantic name needs an evidence trace.
8. Lower layers must not import higher layers.
9. Parallel island investigation is allowed; premature final abstraction is not.
10. Every island should maintain a truth table in `docs/overkill/island_truth_tables.md`.

## Repository Layout

```text
dos_re/                 reusable DOS reverse-engineering environment
  cpu.py                dependency-free 8086 interpreter core
  memory.py             20-bit real-mode memory model
  mz.py                 MZ EXE parser/loader helpers
  dos.py                narrow DOS/BIOS/port services
  hooks.py              generic replacement hook registry
  interrupts.py         generic interrupt delivery helpers
  keyboard.py           host input -> emulated keyboard state
  runtime.py            generic DOS-program runtime wiring
  snapshot.py           generic memory/state snapshot helpers
  verification.py       reusable differential hook-verifier engine
  frame_verify.py       reusable frame comparison/diff artifact engine

overkill/               OVERKILL-specific reverse-engineered game layer
  runtime.py            canonical OVERKILL launch/snapshot wiring
  cli.py                OVERKILL commands built on top of dos_re
  hooks.py              exact CS:IP hook registration surface
  verification.py       OVERKILL verifier stop metadata and adapters
  frame_verify.py       OVERKILL frame extraction/render adapter
  coverage.py           OVERKILL island classifier and dashboard
  bootstrap_boundary.py bootstrap/static-runtime boundary manifest
  static_runtime_bundle.py deterministic initialized-runtime materializer
  asm.py                shared 8086-style helper functions for lifted code
  asset_codecs/         asset streams, checksum, RLE/LZ, decoded asset table
  file_io/              overlay/container file orchestration
  gameplay/             objects, movement, collision, game-state counters
  rendering/            startup graphics, coordinates, video primitives, layer sprites
  sounds/               timer, PC speaker, AdLib/YM3812 driver behavior

nuked_opl3/             vendored optional Nuked-OPL3 CFFI binding
  __init__.py           runtime wrapper; importable even before the C extension is built
  _ffi_build.py         local in-place CFFI build helper
  vendor/               LGPL Nuked-OPL3 C core

docs/
  README.md             documentation map
  architecture/         cross-package architecture and boundary documents
  dos_re/               reusable DOS RE methodology and framework notes
  overkill/             OVERKILL archaeology, findings, status, and game docs

scripts/                convenience runners and RE helpers
assets/                 local user-supplied original game files
artifacts/              generated oracle snapshots, traces, caches, evidence
tests/                  DOS runtime and OVERKILL regression tests
symbols.json            known OVERKILL routines, labels, and hypotheses
```

## Documentation Ownership

Keep docs in the same ownership direction as code:

- `docs/dos_re/`: reusable methodology or tooling that should still make sense for another DOS game.
- `docs/overkill/`: anything with OVERKILL addresses, islands, assets, command tails, screenshots, current status, or game-specific RE findings.
- `docs/architecture/`: explicit cross-package boundaries, dependency-direction rules, and vendored third-party policy.

Do not leave new durable notes directly in `docs/`; add them to one of the owner folders and update `docs/README.md` when a new document becomes important.

## Standard Commands

Run the project test suite:

```bash
python scripts/run_tests.py
```

Clean local Python/build/viewer outputs before packaging or sharing a tree:

```bash
python scripts/clean.py
```

Print executable metadata:

```bash
python -m overkill.cli info assets/OVERKILL
```

Generate a trace from cold start:

```bash
python -m overkill.cli trace assets/OVERKILL \
  --game-root assets \
  --steps 5000 \
  --out trace_start.txt
```

Create a full snapshot from cold start:

```bash
python -m overkill.cli snapshot assets/OVERKILL \
  --game-root assets \
  --steps 100000 \
  --trace-tail 200 \
  --out-dir artifacts/evidence/snapshot_name
```

Stop at a specific address:

```bash
python -m overkill.cli snapshot assets/OVERKILL \
  --game-root assets \
  --stop-at 1010:ECF2 \
  --steps 40000 \
  --trace-tail 200 \
  --out-dir artifacts/evidence/snapshot_stop_1010_ecf2
```

Continue from an existing snapshot:

```bash
python -m overkill.cli continue-snapshot assets/OVERKILL \
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
5. Implement the replacement as a thin hook wrapper in `overkill/hooks.py` and put
   stable game-specific behavior under `overkill/` when it
   belongs to an established island.
6. Add or update hook-verifier metadata in `overkill/verification.py`.
7. Add an oracle/regression test in `tests/`.
8. Update `symbols.json` and `docs/overkill/runtime_findings.md`.
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

Beyond per-hook checks, the standing whole-game proof is the demo-replay
equivalence suite (`tests/test_demo_replay_equivalence.py`). It replays each
recorded demo under `artifacts/demos/` into a reference runtime (original ASM,
hooks stripped) and a candidate runtime (all native hooks) and asserts they stay
identical on framebuffer + RGB + decoded semantic `GameSnapshot` every frame. This
is the verification that must grow stronger as the VM is hollowed out, so collapse
or chain-fusion work is trusted only when this stays green:

```bash
python -m pytest tests/test_demo_replay_equivalence.py -q            # bounded prefix
OVERKILL_FULL_DEMO_VERIFY=1 python -m pytest tests/test_demo_replay_equivalence.py -q  # full demos
```

When adding gameplay coverage, prefer extending the demo corpus (record new demos
with F11) and, when an address is proven, widening the `GameSnapshot` decoder so a
divergence cannot hide in unmodeled state.

## Source-Port Islands

As behavior becomes stable, move it out of `overkill/hooks.py` into established
game-specific modules under `overkill/`. Keep
`overkill/hooks.py` as the exact address-facing wrapper layer.

When closing an island, look for:

- hook-verifier metadata coverage,
- direct oracle/regression tests,
- no open candidate/frontier symbols,
- no bounded-original or fail-fast seams in the module,
- no unknown original-code paths in representative traces.

Use `scripts/audit_islands.py` as a closure signal, not as proof. The original
binary and tests remain the proof.

## CPU Interpreter Rules

`cpu.py` should remain a narrow 8086 interpreter for this game.

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

`dos.py` is a narrow deterministic model for OVERKILL.

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
- `docs/overkill/runtime_findings.md` for durable reverse-engineering facts.
- `docs/overkill/run_status.md` for current progress and recently run commands.
- `README.md` for project overview and contributor onboarding.
- `docs/dos_re/source_port_methodology.md` for the reusable DOS RE workflow.
- `docs/overkill/source_port_methodology.md` for the OVERKILL-specific playbook.
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
