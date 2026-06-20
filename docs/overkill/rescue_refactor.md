# OVERKILL rescue refactor — toward a recovered-source architecture

> **This is the current top-level direction for the project.** It supersedes the
> hook-expansion mindset. `refactor_plan.md` (Phase 3 de-transliteration) is now a
> *means to this end* — cleaner lifted code is easier to push down into pure
> recovered systems. `loop_plan.md` remains only the procedure for fixing a new
> divergence.

## Why

The pilot proved the VM-as-oracle method but accumulated a long, jagged
**coastline**: ~336 low-level hooks and a 10k-line VM-coupled `gameplay/` (lifted)
layer. A working tangled hybrid is not the goal. The goal is a clean recovered
source port shaped like the sibling **PRE2** project
(`missingno7/pre2_port`, de-overkilled fork at `D:\Games\DOS\pre2_port`):

```
original VM memory (dos_re = oracle)
  → bridge / memory views        translate raw game memory
  → recovered dataclasses         reconstruct the original C-like structs
  → pure recovered functions      the game logic, no VM
  → larger source-like systems    MovementSystem / ObjectSystem / ...
  → checkpoints / verify mode     compare recovered vs oracle at boundaries
```

**Hooks are not the architecture — they are temporary contact points.** Recovered
code should read like future source code.

## The good news: the bones already exist

OVERKILL already has the clean layers (enforced by `scripts/audit_architecture.py`):

| Layer | Path | Purity |
|---|---|---|
| memory views | `overkill/recovered/views/` | over live VM memory |
| bridge / adapters | `overkill/recovered/adapters/` | DOS-mem ⇄ domain |
| domain dataclasses | `overkill/recovered/domain/` | **pure** (no VM) |
| pure systems | `overkill/recovered/systems/` | **pure** (verified: 0 VM imports) |
| islands metadata | `overkill/recovered/islands.py` | **pure**, self-describing |
| checkpoints | `overkill/checkpoints.py` | verification boundaries |

`recovered/systems` is already pure (44 functions, no `dos_re`/cpu/pygame), and
the lifted layer already *calls* these pure functions. What was missing — and is
now being added — is the **self-describing island layer**, the **coastline
discipline**, explicit **quarantine/evidence** separation, and **mode-controlled
verification** (no silent ASM fallback).

## The pattern (proven on the first slice: MovementSystem)

Each pure recovered function carries its own provenance — *code is the source of
truth*, docs are generated from it:

```python
@recovered_island(
    asm=("1010:A5D1", "1010:A5EA", "1010:A5F9", "1010:A607"),
    contract="two-pass clamp/step of an axis word toward a boundary",
    status="VERIFIED",            # GUESS < OBSERVED < ASM_MATCHED < VERIFIED < CANONICAL
    merge_target="MovementSystem",
)
def two_pass_axis_clamp_step(value_word, *, limit_word, increment, below_condition=False):
    ...
```

- `python scripts/gen_island_manifest.py` regenerates
  `docs/overkill/recovered_islands.md`.
- `tests/test_island_registry.py` fails if the manifest drifts from the code.
- The decorator returns the function unchanged — never a runtime dependency, never
  an ASM dispatcher. High-level code stays readable.

The 13 movement functions are now annotated as the first proven slice.

## Coastline discipline (the core rule)

The **coastline** is the active boundary between original ASM and recovered code.
OVERKILL has too much of it. Every change must *shorten or raise* it:

```
GOOD:  many low-level hooks → fewer verified pure functions → systems calling
       systems → larger subsystems → higher-level checkpoints
BAD:   more hooks, more adapters, more special cases, more broad parent hooks,
       more hidden fallback behaviour
```

For each recovered/hooked area, ask: can it become a pure function? a dataclass
contract? a thinner / verify-only hook? can two islands merge? can native code
call another *verified native* function instead of bouncing back to ASM? can a
probe be deleted or replaced by a regression test?

**Do not expand the hook forest.** Do not add a gameplay hook just because an ASM
address is reachable. Clean and consolidate what exists first. **Hook removal is
progress** — the goal is not to preserve every original ASM boundary forever.

## Hook inventory & classification (turn the forest into islands)

The pilot's core mistake was hooking too many things at too low a level until the
hooks *became* the architecture. The fix is not another abstraction on top — it
is to inventory every hook, classify it, and give each one a **lifetime** and a
**merge target**. *A hook without an intended lifetime is suspicious; a hook
without a merge target is suspicious.*

`docs/overkill/hook_inventory.md` is generated from the live registry +
`hook_taxonomy` + the coverage classifier (`python scripts/gen_hook_inventory.py`).
For every hook it records:

- **role** — `checkpoint` (real frame/object-update/render/input boundary, keep),
  `env_wait` (hardware wait, keep hooked), `debug_probe` (delete when done), or
  `glue` (the collapse target — accidental ASM plumbing);
- **subsystem** — codec / renderer / object-runtime / collision / input / sound /
  menu / bootstrap / frame / game-state;
- **verifier** — does it carry continuation metadata / an oracle (all 336 do);
- **merge target** — the recovered subsystem it should fold into;
- **shrinking path** — how it gets thinner or deleted.

Current state: **336 hooks = 12 checkpoint + 5 env_wait + 319 glue.** The 319
glue hooks are the coastline length. The headline metric is **glue-hook count
trending down** as their logic moves into recovered systems — not hook coverage
trending up.

## Reconstruct state structures first; move verification upward

Per the PRE2 charter/methodology (`dos_re/AI_PORTING_CHARTER.md`,
`docs/dos_re/source_port_methodology.md`): the bridge is **reconstructed
dataclasses**, our best guess at the original C-like structs and runtime state —
object slots, player state, level state, renderer state, camera state, input
state — not arbitrary modern abstractions. Build these factual state mirrors
first; they are the translation layer between ASM memory and recovered code.

Once that layer exists, **verification climbs**: instead of forever diffing tiny
low-level ASM boundaries, compare **semantic state contracts** — object-slot
state after an update, player state after movement, renderer output after a draw
phase, eventually whole-frame state after `update_frame()`. Low-level per-hook
ASM diffs remain the oracle for un-lifted glue; the proof spine moves up as
subsystems are reconstructed.

## Verification posture (modes, no silent fallback)

1. **Recovered/hybrid run** — runs recovered code directly; fails *loudly* on an
   unrecovered gap; never silently falls back to ASM.
2. **Verify mode** — replay demos/snapshots, run oracle + recovered path, compare
   at checkpoint boundaries, report first divergence. (Today: the per-hook oracle
   suite + `test_demo_replay_equivalence`.)
3. **Probe/evidence mode** — may observe original ASM; for discovery only; must
   never be confused with the recovered runtime.

If original ASM is used from a recovered path, it must be explicit, logged, and
mode-controlled — not a hidden fallback.

## Target layout (some dirs are aspirational)

```
overkill/recovered/views/      memory views over VM memory          [exists]
overkill/recovered/adapters/   bridge / translation adapters        [exists]
overkill/recovered/domain/     pure dataclasses / value objects     [exists]
overkill/recovered/systems/    pure recovered game systems          [exists]
overkill/recovered/islands.py  self-describing island metadata      [exists, new]
overkill/checkpoints.py        verification boundaries              [exists]
overkill/gameplay/             VM-aware lifted adapters (coastline)  [shrinking]
overkill/hook_wrappers/, hooks.py  thin hook registration glue       [keep thin]
overkill/probes/               temporary investigation tools         [to create]
overkill/evidence/             archived pilot evidence/traces/maps   [to create]
```

Pure systems/domain/islands MUST NOT import CPU, VM, registers, segments, raw
memory, hook dispatchers, or pygame/UI (enforced by `audit_architecture.py`).

## Work subsystem by subsystem (not a big-bang rewrite)

Never rewrite the whole runtime in one pass. Pick **one subsystem** from the
inventory, gather all its hooks, and run the per-subsystem cleanup loop:

1. Gather all hooks for the subsystem (from `hook_inventory.md`).
2. Separate **VM glue** (register/memory/return mechanics) from **real logic**
   (movement, collision, object behaviour, sprite/animation rules, asset decode).
3. Extract the real logic into clean recovered functions (`recovered/systems`),
   no `cpu`/`mem`/`dos_re`.
4. Introduce memory views + reconstructed dataclasses where the hook pokes raw
   memory.
5. Add contract-level verification (move the checkpoint up to a semantic state
   contract where you can).
6. Merge duplicated hook tails/helpers into one recovered helper.
7. **Delete or shrink at least one old hook.** A cleanup step that doesn't move
   logic out, replace raw memory with a view/dataclass, merge a duplicate, add a
   verifier, raise a checkpoint, or remove a hook is not a cleanup step.

Subsystem order (by glue density / leverage; backends stay isolated, not merged
into game logic):

- **[done]** `movement` — clamp/scroll hooks thinned, MovementSystem live.
- **[in progress]** `collision` — pure rules live; drop the ~49 self-check
  asserts per-function (each gated with the full oracle for cross-fn flags).
- `gameplay_objects` (55 glue) — behaviour bodies → pure ObjectSystem rules.
- `game_state` (45) — frame/state update → pure rules; keep broad controllers
  (`9b2e`/`d007`) as **frame MAPS / oracle-composition scaffolds**, never grow.
- Reconstruct the state dataclasses (object slot ✓, then player/level/camera/
  input) so verification can rise to semantic contracts.
- Backends (`*_renderer`, `layer_sprites`, `sound`, `asset_codecs`, `file_io`,
  `overlay`) — keep isolated; thin their hooks but don't merge into game logic.
- Classify the 4 `unknown` hooks and give each a merge target.
- Create `overkill/probes/` + `overkill/evidence/`; move investigation tools and
  heavy one-off traces out of the live tree.
- Keep `hooks.py` thin; move fat bodies down; never grow it.

## Definition of done (per slice)

- a pure dataclass/state contract exists;
- pure system functions exist with no VM imports;
- the hook adapter only reads memory → calls pure code → writes/checks;
- old duplicate ASM-shaped helpers are removed or quarantined;
- tests verify the pure logic and the adapter;
- `@recovered_island` metadata states VERIFIED/OBSERVED/GUESS + merge target;
- the manifest regenerates clean and the drift test passes;
- **the coastline is shorter or higher-level than before.**
