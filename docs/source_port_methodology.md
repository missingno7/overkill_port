# Evidence-Driven Source-Port Methodology

This document describes the reusable workflow behind this project. It is written
for OVERKILL today, but the same system should apply to other old games that can
be run inside a narrow interpreter/runtime and gradually lifted into source-level
code.

The method is not "rewrite the game from vibes". The method is:

```text
original executable -> trace/snapshot -> exact boundary -> verified hook -> island module -> source-port code
```

The most important sentence for the whole project is:

```text
Do not write a source port first and hope it matches.
Exhaust truth from the original first, then let the source port crystallize from that evidence.
```

## Core Principle

Every higher layer may only be created from evidence in the layer below it. Some
layers and islands can be investigated in parallel, but their outputs must stay
separate until the evidence supports merging them.

Until a subsystem is explicitly declared a closed candidate, the original
executable remains the oracle:

```text
original ASM / EXE has the final say
Python hooks must justify themselves against ASM
semantic models must not overwrite observed reality
```

For example, do **not** claim:

```text
this is definitely an enemy projectile
```

when the current evidence only proves:

```text
a slot moves right and draws a sprite
```

The correct intermediate state is:

```text
candidate: moving harmful object
evidence: collides with player, deactivates on impact, spawned by enemy behavior
```

Correctness comes first, readability second, semantic meaning third.

## Logic Crystallization Pyramid

The project intentionally starts with very low-level facts and lets higher-level
meaning emerge over time. Early hooks do not need to know whether a slot is a
player, projectile, boss, or specific enemy. They only need to prove what the
original code did at that boundary.

The long-term mental model is a pyramid:

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

### Layer 1 — Original Binary Oracle

The original executable, original data files, interpreted ASM execution,
snapshots, traces, frame captures, sound/port captures, and file-offset state.
This layer answers: "what really happened?"

### Layer 2 — ASM-Compatible Hook/Runtime Layer

Exact `CS:IP` hook wrappers, CPU/DOS/video/input/sound scaffolding, and weird
8086 side effects. This layer still thinks in registers, flags, memory offsets,
stack shape, file handles, continuation IPs, and resident patched bytes.

### Layer 3 — Verified Lifted Routine Layer

Source-level implementations of bounded original routines that have passed
ASM-oracle comparison. A routine at this layer may still have names like
`BC4B postmove tail`, `AC97 slot scan`, or `0FA3 table builder`; that is fine.
Correctness comes before semantic naming.

### Layer 4 — Runtime Object/Data Model Layer

Stable structures begin to emerge: object slots, fields, pointer tables, asset
records, presence lists, tile probes, dirty cells, sound state, input state, and
renderer buffers. At this layer an object may still be just "a moving slot with
sprite, layer, logic id, coordinates, and collision fields".

### Layer 5 — Game Systems Layer

Repeated routines form coherent systems: asset loading, overlay/file I/O,
renderer, layer/sprite presenter, input/menu waits, sound/timer, object update,
postmove/collision, level state, camera/state transitions.

### Layer 6 — Gameplay Archetype Layer

Only after enough object logic paths are mapped should we name archetypes such as
player, enemy, projectile, pickup, reward fountain, boss part, hazard, spawner,
or level trigger. These names must be backed by observed logic-id tables, field
usage, sprite ids, collision behavior, and call sites.

### Layer 7 — Semantic Game Model Layer

A clean model of the actual game rules: levels, waves, enemies, projectiles,
weapons, powerups, scoring, boss phases, transitions, difficulty, UI, and
resource lifetimes. This is where the source port starts to look like a game
engine rather than a collection of lifted routines.

### Layer 8 — Modern Game / Enhanced Port Layer

Optional improvements that intentionally sit above the verified vanilla model:
modern input/gamepad support, widescreen/UI options, interpolation, better
configuration, debugging overlays, accessibility, and non-vanilla enhancements.
These should depend on the semantic model instead of replacing oracle work.

The workflow climbs the pyramid by crystallization, not by guessing. A new
high-level name is earned when multiple verified lower-level facts point to the
same concept.

## Layer Ownership And Dependency Direction

Every new function should have a clear layer. If a function mixes three layers,
it is suspicious.

```text
ASM-compatible hook      -> works with cpu, registers, flags, memory
Verified lifted routine  -> still faithful to ASM, but named and tested
Runtime data model       -> ObjectSlot, SpriteRef, AnimationState, AssetRecord
Game system              -> collision system, renderer, object system
Semantic model           -> Enemy, Projectile, Pickup, Boss
Modern layer             -> gamepad, interpolation, debug UI
```

Bad shape:

```python
def run_enemy_ai_from_cpu_memory_and_draw_sprite(cpu):
    ...
```

Better shape:

```python
def run_object_behavior_aa2b(cpu): ...
def decode_object_slot(memory, bp) -> ObjectSlot: ...
def classify_object(slot, evidence) -> ObjectKindCandidate: ...
def update_enemy(enemy, world): ...
```

Lower layers must not import higher layers:

```text
asset_codecs        must not know Enemy
rendering           must not know Boss
collision           must not know level story
object_runtime      must not know modern UI
semantic model      may read lower-layer evidence
modern renderer     may read semantic model
```

Dependency direction is upward only:

```text
original oracle -> ASM runtime -> lifted routines -> runtime model -> systems -> semantic entities -> modern port
```

Never the other way around.

## Promotion Rules

### Phase A — Unknown ASM

State examples:

```text
1010:B73E
1010:5DB2
1010:AA2B
```

Use technical names only. Allowed names:

```text
object behavior dispatch
movement helper
sprite compositor
tile probe
```

Avoid names like:

```text
enemy_ai
gorilla_logic
player_bullet
```

unless the evidence already proves those meanings.

### Phase B — Verified Lifted Routine

A routine may move from hook/staging code to a lifted module when:

```text
it has clear inputs and outputs
it has a snapshot or verifier test
registers/flags/memory/stack match ASM
side effects are named and documented
it has no silent speculative fallback
```

Example:

```text
1010:5DB2 -> movement_direction_helper
```

This is still a lifted ASM helper, not `EnemyMovement`.

### Phase C — Runtime Model

Create a runtime model only when repeated evidence establishes the data layout.
For `ObjectSlot`, that means evidence for fields such as:

```text
active flag
x/y coordinates
behavior index or pointer
sprite reference
state bytes
movement-updated fields
collision-updated fields
```

At this phase, write:

```python
class ObjectSlot:
    ...
```

not:

```python
class Enemy:
    ...
```

`ObjectSlot` is a fact from memory. `Enemy` is an interpretation.

### Phase D — Game System

A system emerges when several verified routines repeatedly operate on the same
runtime model. For example, a collision system becomes legitimate after evidence
for:

```text
tile lookup
tile probe
object overlap scan
hazard scan
post-contact logic
death/damage side effects
```

Then the system may become:

```python
class CollisionSystem:
    def probe_tiles(...): ...
    def scan_object_overlaps(...): ...
    def apply_contact_effects(...): ...
```

It still does not need to know concrete enemy types.

### Phase E — Semantic Archetype

Introduce archetypes such as `Enemy`, `Projectile`, or `Pickup` only when there
is evidence across multiple systems. Useful evidence includes:

```text
spawn source matches an enemy list or enemy behavior
hostile collision with player
changes player health/death state
enemy-like movement behavior
death effect
score/reward/drop logic
sprite group repeated across levels
```

Until then, prefer:

```text
ObjectKindCandidate.HOSTILE_MOVING_OBJECT
```

### Phase F — Concrete Entity

Concrete entities such as `GorillaBoss`, `Firefly`, or `PlayerBullet` require
known evidence for:

```text
spawn
sprite set
animation
movement
collision
damage
death/cleanup
sound
reward/progression side effects
level-specific behavior
```

Otherwise the name is premature.

## Parallel Work And Vertical Slices

The whole lower layer does not need to be finished before a higher slice is
explored. Vertical slices are allowed when their outputs remain evidence-based.

Example slice:

```text
asset decode
-> sprite data
-> draw routine
-> object slot using sprite
-> animation/frame selection
-> candidate enemy type
```

Another slice:

```text
object movement
-> tile collision
-> player damage
-> death state
-> hazard archetype
```

Parallel exploration is good:

```text
rendering
object runtime
collision
sound
asset loading
```

but final abstractions should not be made in parallel before the islands meet.

```text
Parallel island investigation: yes.
Parallel final semantic modeling: no, unless evidence converges.
```

## Hook Lifecycle

Use this lifecycle for every candidate routine.

### 1. Observe

Collect evidence first:

- coverage dashboard,
- profiler hotspots,
- executed-address traces,
- snapshots at or before a target address,
- frame-verifier failures,
- hook-verifier divergence reports,
- crash/fail-fast context dumps.

Do not choose a hook only because the address is hot. Determine what role it
plays.

### 2. Classify

Classify the routine before implementing it:

- asset decoder or materialization helper,
- file/overlay/container I/O,
- renderer primitive,
- coordinate/address helper,
- layer/sprite scan or presenter,
- input/menu wait,
- timer/sound path,
- gameplay object behavior,
- collision or postmove tail,
- startup table builder,
- dynamic/bootstrap/relocation code that may not be a stable game island.

If the category is unclear, keep it as a candidate/frontier and gather more
evidence.

### 3. Choose a Boundary

Prefer the smallest coherent boundary that can be verified:

- leaf loops with deterministic inputs/outputs,
- routine bodies with a normal near/far return,
- repeated inner loops with clear continuation IP,
- parent blocks that only compose already-verified child hooks,
- dispatch stubs only when the dispatch effect is understood.

Avoid broad parent hooks if they hide unverified behavior. Avoid dynamically
loaded/transient bootstrap segments unless their resident code signature and
caller contract are stable.

### 4. Build an Oracle

Run the original interpreted ASM for the same entry state. The oracle should
record every observable effect required by the boundary:

- registers and segment registers,
- `CS:IP` continuation,
- flags,
- stack pointer and stack scratch,
- touched memory ranges or full memory when practical,
- DOS handle state and file offsets,
- port and timer state,
- video memory or rendered frames,
- input/sound side effects.

### 5. Implement The Hook

Start in the staging layer. Keep the wrapper address-facing and explicit:

```python
@registry.replace(0x1010, 0xECF2, "overkill_lz_decoder_ecf2")
def overkill_lz_decoder_ecf2(cpu):
    ...
```

Preserve exact return mechanics:

- near routine: `cpu.s.ip = cpu.pop()`
- far routine: `cpu.s.ip = cpu.pop(); cpu.s.cs = cpu.pop()`
- internal block: set the exact continuation IP
- hybrid boundary: document every allowed continuation

Model ugly original side effects when the oracle observes them. Examples are
balanced call-stack scratch, temporary memory stores, flag results from final
comparisons, and runtime-patched instruction bytes.

### 6. Verify

Use more than one verification mode when possible:

- focused synthetic oracle tests,
- snapshot oracle tests,
- live hook verifier from real startup/gameplay,
- frame verifier for visual paths,
- runtime smoke tests with fail-fast enabled.

A hook that passes only because a nested hook hides original behavior is not
fully proven. For composed hooks, either verify against interpreted children or
intentionally call the installed child hook when that child represents an
external runtime boundary such as frame pacing.

### 7. Document

Update the durable evidence:

- `symbols.json` with name, island, and status,
- `docs/runtime_findings.md` with the actual finding,
- `docs/island_truth_tables.md` with the island status when relevant,
- `RUN_STATUS.md` with the current checkpoint and validation commands,
- hook coverage cache when live verification establishes a stable cost,
- tests that make the finding executable.

### 8. Move To An Island

Once a hook is stable and its subsystem is clear, move the behavior from the
staging layer into a game-specific module. Keep the exact `CS:IP` wrapper in
`replacements.py`.

Good pattern:

```text
replacements.py                         exact hook address wrappers only
  -> games/<game>/<island>/<module>.py   stable lifted behavior
  -> games/<game>/asm.py                 shared 8086-style helper functions
```

Do not create a second implementation of an existing tail or helper. Factor the
shared behavior and have new hooks call it.

## Definition Of Done By Layer

### Hook / ASM Replacement Done

```text
passes verifier or oracle comparison
known call context
clear register/flag/stack/memory side effects
no silent fallback into speculative behavior
technical name based on actual function
implementation moved from replacements.py when stable
```

### Island Done / Closed Candidate

```text
all hot paths are lifted or intentionally left original
representative test snapshots exist
memory layout is documented
inputs/outputs are known
unknown edge cases are listed
minimal dependencies on other islands
no duplicate helper/tail implementations
```

`closed-candidate` means no currently known blocker. It is not a mathematical
proof of completeness.

### Runtime Model Done

```text
can read original memory
can write back original memory when needed
has offset mapping
uses non-speculative names
has debug dump support
can be compared with ASM/runtime state
```

### Game System Done

```text
uses runtime model instead of raw offsets where practical
still supports oracle verification
can run as a coherent logical unit
has clear interfaces to other systems
contains no concrete level/enemy hacks
```

### Semantic Entity Done

```text
derived from multiple evidence sources
linked to original object/behavior ids
known assets, animations, collisions, sounds, and behavior
fallback path to original runtime model exists
evidence can explain why it is enemy/projectile/pickup/etc.
```

## AI / Agent Task Framing

Every task should state the layer being worked on. This prevents one step from
mixing an ASM refactor, renderer cleanup, semantic rename, and gameplay hack.

Examples:

```text
Work only in the verified lifted routine layer.
Do not introduce high-level gameplay abstractions.
Preserve CPU-visible side effects exactly.
Move implementation out of replacements.py into rendering/ega.py.
Keep replacements.py as registry glue only.
```

```text
Work in the runtime object model layer.
Do not classify enemies yet.
Extract object slot field accessors and produce debug dumps showing active slots,
coordinates, sprite refs, and behavior ids.
```

```text
Work in the semantic classification layer.
Use existing object traces only.
Do not change runtime behavior.
Produce candidate classifications with evidence, not hardcoded gameplay logic.
```

Treat these as hard boundaries. A refactor task is not a fix task. A fix task is
not a semantic-modeling task. A semantic task is not a renderer cleanup task.

## Hard Rules Against Chaos

1. **No high-level names without evidence.**
   - Bad: `enemy_bullet`.
   - Good: `candidate enemy projectile: spawned from behavior X, damages player,
     deactivates on contact`.
2. **No behavior changes during refactor.** Refactor tasks must preserve oracle
   behavior.
3. **Every promotion upward must be reversible.** The semantic model must still
   let us ask: original slot? behavior id? ASM routine? evidence trace?
4. **`replacements.py` should gradually die.** It should become registry glue,
   not the home of rendering loops, object behavior, collision algorithms, asset
   decoding, sound logic, or ASM micro helpers.
5. **Every island gets a truth table.** Each island should say what is known,
   verified, guessed, unknown, which routines belong there, which routines are
   still staged, and which tests/snapshots cover it.
6. **Lower layers must not import higher layers.** Dependencies only point up the
   pyramid.
7. **Candidate before definitive semantic name.** Use confidence and evidence
   when meaning is emerging.
8. **Parallel island work is allowed; premature final abstraction is not.**

## Practical Roadmap

### Step 1 — Keep Cleaning `replacements.py`

Priority order:

```text
1. EGA rendering module
2. packed/CGA/shared blitter modules
3. object_runtime module
4. asm_helpers / hook_bridge module
5. present/timing/input module
```

Goal:

```text
replacements.py is no longer where logic lives
```

### Step 2 — Add Evidence Traces For Object Slots

Do not start with `Enemy`. Start with:

```text
slot id
active flag
x/y
sprite ref
behavior id
spawn source
collision partner
state changes
sound triggers
deactivation reason
```

### Step 3 — Candidate Classification

Use a candidate model, not hardcoded behavior:

```python
class ObjectClassification:
    kind_candidate: str
    confidence: float
    evidence: list[str]
```

Example:

```text
slot 12 -> candidate: enemy_projectile, confidence 0.72
evidence:
- spawned from enemy behavior AED8
- damages player
- deactivates on collision
- uses small moving sprite
```

### Step 4 — Semantic Model

Only after repeated patterns converge should we introduce:

```text
ProjectileDefinition
EnemyDefinition
PickupDefinition
BossDefinition
```

## Good Next-Hook Candidates

Prioritize hooks that improve understanding and modularity:

- a hot loop whose role is already clear,
- a small file/overlay or asset-loader parent around verified child loops,
- a renderer or coordinate helper that removes mislabeled shared code,
- a gameplay behavior tail repeatedly reached from fail-fast reports,
- a parent composition that removes interpreter overhead while reusing verified
  child helpers,
- a deterministic startup table builder.

## Bad Hook Candidates

Defer or avoid hooks when:

- the code lives in a transient/dynamically relocated segment and has no stable
  game-module boundary,
- the only motivation is reducing a small interpreted count,
- the routine contains unclassified dispatch into many unknown targets,
- visual pacing/input/timer side effects would be bypassed,
- the hook would duplicate a tail already implemented elsewhere,
- the original code is self-modified and no resident signature guard exists.

## Fail-Fast Policy

Fail-fast paths are useful. They turn unknown behavior into a precise snapshot
and state dump. Do not replace them with guessed fallbacks merely to keep the
game running.

When a fail-fast triggers:

1. treat the dump as a new oracle candidate,
2. reproduce the path from the snapshot,
3. compare original ASM against the current lift,
4. add the smallest missing branch or split the hook boundary,
5. keep the failure message specific if the branch remains unknown.

## Duplication Control

The most common long-term risk is code bloat: adding a new hook that reimplements
an existing tail with slightly different behavior. Before implementing a new
hook, search for:

- same original address suffix in function names,
- same continuation IP,
- same field offsets, especially object-slot offsets,
- same memory tables,
- same helper names in the island module,
- existing tests for nearby paths.

Prefer shared helpers named after original addresses, for example:

```text
_run_object_bounds_tile_tail_ad60
run_object_slot_scan_ac97
build_video_offset_tables_0fa3
```

Keeping original addresses in helper names makes it obvious when two hooks want
the same tail.

## OVERKILL Current Island Map

Current mature or emerging OVERKILL islands:

- `asset_codecs`: checksum, packed stream reads, RLE/LZ decode, and decoded-asset
  table search. It should not own renderer startup materialization or gameplay
  counters merely because those routines live near loader code.
- `overlay`: overlay directory/signature/name/path/XOR helpers.
- `file_io`: overlay/container open/read/seek orchestration around the asset
  loader.
- `startup_graphics`: startup renderer table and graphics materialization
  helpers.
- `rendering`: Tandy/CGA/EGA renderer primitives, shared coordinate/address
  helpers, layer/presence lists, and text helpers.
- `gameplay`: object scan, object behavior, postmove/collision tails, movement
  helpers.
- `sound`: timer ISR and PC speaker hardware/backend path.
- `input_menu`: keyboard polling and interactive wait/yield points.
- `bootstrap`: transient unpack/relocation loader code. This is a coverage
  classification, not a game-module island; leave it interpreted unless boot
  performance or correctness requires a verified bootstrap hook.

The exact list changes as unknown code is identified. The method should not.

## Short Rules

```text
1. Fidelity first, readability second, meaning third.
2. No higher abstraction without evidence from lower layers.
3. Refactor must not change behavior.
4. Fix must not introduce a semantic model.
5. replacements.py should be registry glue only.
6. ObjectSlot before Enemy.
7. Candidate before definitive name.
8. Every semantic name needs an evidence trace.
9. Lower layers must not import higher layers.
10. Islands may be explored in parallel; final abstractions wait for convergence.
```
