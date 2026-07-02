# DOS Game Recovery Lifecycle

> **This is the canonical lifecycle & vision for the whole effort** — game-agnostic, built on
> the shared `dos_re` foundation (it applies equally to the PRE2 sibling project). It is the
> *why* and the *full arc*. For *what to do next*, see the executable plan.
>
> ## Canonical doc map (read this to avoid confusion)
>
> | Doc | Role |
> |---|---|
> | **game_recovery_lifecycle.md** (this) | The lifecycle & vision: the full arc + the equivalence boundaries. |
> | **overnight_endgame_execution.md** | **THE executable `/goal` brief** — the cold-boot done-condition (§1), the loop, the work buckets. **Run `/goal` on this one.** |
> | **native_game_endgame.md** | The OVERKILL endgame statement (a subset/restatement of this lifecycle). |
> | **source_port_methodology.md**, **semantic_crystallization_plan.md**, **native_recovery_goal.md** | The per-slice method (how one slice is shaped + verified). |
> | **loop_plan.md** | The per-divergence fix procedure. |
> | **run_status.md**, **coastline_report.md**, **loop_blockers.md** | Live status / map / blocker log. |
>
> The destination in one line: **a complete, VM-less, faithful source port — the full game
> cold-booted from its own data files, with the VM kept only as an optional oracle.**

## Purpose

This document describes the full lifecycle of a DOS game recovery project built on top of a shared `dos_re` foundation.

The goal is not to end with an emulator that has a nicer renderer.

The goal is to use the VM as an extraction, verification, and debugging environment, gradually recover the original game into high-level source code, and eventually produce a standalone VM-less faithful source port.

The VM starts as the place where the original game runs.

It ends as the oracle.

The faithful native port starts as a destination for recovered code.

It ends as the standalone product.

```text
original DOS game
    -> boot in VM
    -> run original ASM
    -> hook hot routines
    -> make hybrid playable
    -> record snapshots/demos
    -> recover verified islands
    -> merge islands into a recovered core
    -> lift recovered code into VM-less faithful runtime
    -> keep VM as optional oracle
    -> extract standalone faithful product
```

## Core idea

A new game recovery project begins by taking an existing DOS executable and making it run inside the shared VM foundation.

At the beginning, the VM executes the original game almost exactly as the DOS machine would:

```text
original executable
original assets
original CPU execution
original memory layout
original video/audio/input behavior
original platform quirks
```

This gives the project a running reference.

The first version may be slow, incomplete, or barely playable.

That is acceptable.

The first goal is not performance.

The first goal is truth.

```text
first make the game run
then make it observable
then make it fast enough
then make it understandable
then make it native
```

The VM is the transplanted DOS world.

The hybrid runtime is the recovery workshop.

The faithful native port is the final product.

## Final architecture

The desired final architecture is:

```text
Original game executable:
    oracle/reference only

dos_re VM:
    shared recovery foundation
    runs original ASM
    supports tracing, debugging, and verification

Hybrid runtime:
    staging area
    runs original game with recovered hooks
    prepares and verifies source-port code

Recovered islands:
    high-level verified systems
    initially connected through hooks
    later connected to native state

Faithful native core:
    VM-less recovered source port
    owns game state and tick behavior
    built from recovered islands

Faithful renderer/audio/input:
    modern implementations of original game-visible contracts
    faithful at the output/semantic boundary

Enhanced layer:
    optional modern presentation/audio
    no gameplay fork

Verification layer:
    optional VM oracle comparison
    removable from normal runtime
```

The endgame is not:

```text
VM with a nicer renderer
```

The endgame is:

```text
complete recovered native source port
with the VM available only as an oracle
```

## Development principle

The most important rule is:

```text
do not write code only for hooks
write recovered systems that can first run through hooks,
then later run directly inside the VM-less faithful core
```

A hook is scaffolding.

Recovered source code is the permanent artifact.

A good recovered system should be usable in two forms:

```text
VM memory/registers
    -> adapter/view
    -> recovered function
    -> write back to VM memory/registers
```

and later:

```text
NativeGameState
    -> recovered function
    -> NativeGameState
```

The same recovered behavior should survive the transition from hybrid to native faithful.

## Phase 0: Shared foundation

Before starting a new game, the project should have a reusable DOS recovery foundation.

This foundation may include:

```text
MZ/COM executable loading
PSP/environment setup
8086/286 CPU interpreter
memory model
interrupt handling
BIOS/DOS service stubs
timer support
keyboard input support
video modes
audio device stubs or emulation
trace tools
snapshot tools
hook dispatch
verification utilities
demo/input replay tools
```

The point is not to copy one previous project wholesale.

The point is to extract reusable infrastructure into a shared `dos_re` base, then build each game-specific recovery project on top of it.

## Phase 1: Transplant the game into the VM

The first real phase is to make the new original game start inside the VM.

This usually requires:

```text
load the executable
load required assets
support its memory layout
support required CPU instructions
support required DOS/BIOS calls
support its video mode
support keyboard/input reads
support timer behavior
stub or emulate audio enough to avoid crashes
```

The objective is simple:

```text
the original executable reaches its own code
the menu appears if possible
the first level starts if possible
the game can execute original ASM
```

At this stage, the VM may be slow.

That is fine.

The goal is to establish the original game as a living oracle.

## Phase 2: Make it runnable and observable

Once the executable starts, the next goal is runtime stability.

The game should be able to:

```text
boot
load assets
enter gameplay
draw frames
accept input
advance time
avoid crashes
produce repeatable behavior
```

The project should then collect evidence:

```text
execution traces
hot routine profiles
memory maps
interrupt usage
video access patterns
asset loading patterns
audio calls
input polling locations
main loop structure
frame boundaries
timer behavior
```

This phase answers the first important question:

```text
what does the original game actually do?
```

## Phase 3: Hook hot and bounded routines

The first recovered hooks should target code that is both expensive and reasonably bounded.

Good early targets are usually:

```text
asset decompression
file loading wrappers
graphics blitters
tile drawing
sprite drawing
screen copy/page flip routines
palette updates
audio command submission
checksums/helper routines
tight memory operations
```

These routines are useful because they are called often, cost a lot in interpretation, and often have clear inputs and outputs.

Replacing them can move the game from:

```text
technically running
```

to:

```text
somewhat playable
```

The first hooks are not the source port.

They are performance and observability footholds.

A routine is a good early hook candidate when it is:

```text
hot
well-bounded
easy to verify
not deeply entangled with unknown game state
```

A routine may be a bad early hook candidate if it is expensive but semantically huge, such as a whole main update loop with many unknown side effects.

## Phase 4: Reach playable hybrid mode

Hybrid mode means:

```text
the VM still owns the original execution
some expensive or understood routines are replaced by recovered hooks
the original game remains the behavioral reference
the game becomes playable enough to explore
```

The purpose of playable hybrid mode is not only convenience.

It allows the project to collect real gameplay evidence.

At this point, the project should support:

```text
snapshot capture
demo recording
input replay
frame dumps
state checkpoints
hook verification
routine comparison
divergence reports
```

The game becomes a laboratory.

## Phase 5: Use snapshots and demos as evidence

Once the game is playable, users and developers can record evidence from real gameplay.

Useful artifacts include:

```text
startup snapshots
menu snapshots
level-entry snapshots
gameplay snapshots
boss snapshots
death/restart snapshots
transition snapshots
user-recorded demos
deterministic input replays
known tricky situations
```

These recordings become regression anchors.

The project can then ask:

```text
does the recovered routine produce the same result here?
does the same input history produce the same state?
does the same level transition happen?
does the same object spawn?
does the same collision happen?
does the same frame appear?
does the same sound event happen?
```

Snapshots and demos are important because they capture behavior that static disassembly alone may miss.

They turn the original game into a measurable oracle.

## Phase 6: Recover behavior islands

The main recovery strategy is island-based.

A behavior island is a connected piece of original behavior that has been understood, recovered, and verified well enough to stand on its own.

Examples:

```text
asset decompression island
tile renderer island
sprite renderer island
palette/fade island
input sampling island
camera/scroll island
player movement island
collision island
object update island
enemy AI island
pickup/combat island
scene transition island
menu/map/tally island
audio event island
```

An island usually starts as:

```text
ASM routine
    -> traced boundary
    -> hook
    -> memory/register adapter
    -> recovered source function
    -> verification
```

Then it grows into:

```text
structured state
    -> source-level behavior
    -> local tests
    -> replay verification
    -> hybrid replacement
```

The important rule is:

```text
hooks are scaffolding
recovered islands are permanent code
```

A hook should not become the final architecture.

A hook should be a temporary connection between the VM world and the recovered source world.

## Phase 7: Merge islands

At first, islands are separate.

That is expected.

The project may have independent islands for:

```text
decompression
rendering
input
camera
objects
collisions
audio
scene flow
```

But the long-term goal is for islands to touch and merge.

For example:

```text
object state
    -> sprite selection
    -> render state
    -> faithful frame

player state
    -> collision
    -> camera
    -> level transition

pickup state
    -> score/lives
    -> audio event
    -> HUD update
```

As boundaries become understood, islands should merge.

The project should gradually move from:

```text
many small verified islands
```

to:

```text
fewer larger source-level systems
```

and eventually to:

```text
one coherent recovered game core
```

This is the island collapse phase.

The coastline between ASM and recovered code shrinks until it disappears from normal runtime.

## Phase 8: Separate recovered logic from VM adapters

During hybrid recovery, recovered functions may still be connected directly to VM memory.

That is acceptable temporarily.

But recovered logic should not remain trapped in VM-shaped APIs.

The architecture should separate:

```text
recovered behavior:
    permanent high-level source code

VM adapter:
    temporary bridge to original memory/registers

native adapter:
    bridge to VM-less faithful state
```

The same logic should support both paths:

```text
VM adapter path:
    VM state
        -> recovered behavior
        -> VM state

Native adapter path:
    NativeGameState
        -> recovered behavior
        -> NativeGameState
```

This is what makes the later VM-less port possible.

If recovered code is too deeply tied to segment addresses, CPU registers, or original framebuffer memory, it has not yet been lifted far enough.

## Phase 9: Define equivalence boundaries

The faithful native port does not need to preserve every DOS-era mechanism.

It needs to preserve the original game.

The key distinction is:

```text
the VM preserves the original machine
the faithful source port preserves the original game
```

Different systems have different equivalence rules.

### Gameplay simulation

Gameplay logic is strict.

This includes:

```text
player movement
object updates
enemy AI
collisions
physics
damage
pickups
score/lives
RNG
timers
scene progression
level progression
input semantics as seen by the game tick
```

The contract is:

```text
same initial state
same input history
same tick number
    -> same game state
```

For gameplay, close enough is not faithful.

### Rendering

Rendering is pixel-exact, but mechanism-flexible.

A native faithful renderer does not need to literally preserve:

```text
EGA bitplanes
VGA latches
hardware write modes
sequencer registers
graphics controller side effects
segment A000h behavior
CRTC tricks
DOS-era page flipping machinery
```

Those details matter in the VM/oracle and during recovery.

But the native faithful renderer may use:

```text
tile maps
sprite records
decoded assets
indexed framebuffers
explicit palettes
render command lists
modern textures
```

The contract is:

```text
given the same recovered render state
produce the same visible pixels
with the same palette result
at the same frame boundary
```

### Audio

Audio is event/timing exact, but mixer-flexible.

The recovered game should preserve:

```text
which music starts
which sound effect triggers
when it triggers
whether it interrupts or overlaps
which priority/order rules apply
which gameplay event caused it
```

But the final mixer may be modern.

The contract is:

```text
same game-visible audio events
same timing relative to the game tick
no gameplay dependency on host mixer latency or buffer state
```

Enhanced audio may improve quality, buffering, or mixing, as long as it does not feed back into gameplay.

### Input

Input is semantic/timing exact, but hardware-path flexible.

The VM/oracle may care about:

```text
keyboard IRQs
BIOS keyboard buffer
scan codes
port reads
DOS polling loops
repeat behavior
```

The native faithful game should preserve what the game actually observes:

```text
which buttons are down at this tick
which presses are newly observed
when input is sampled
how pause/menu/input gating behaves
```

The contract is:

```text
hardware mechanism may differ
game-visible input state at tick boundaries must match
```

### Timing and idle loops

The native faithful port should not preserve DOS waiting machinery for its own sake.

It should not need to reproduce:

```text
busy waits
vertical retrace polling
host-speed delay loops
DOSBox-sensitive timing artifacts
hardware polling loops
```

It should preserve:

```text
game tick cadence
input sampling cadence
animation cadence
physics/update cadence
scene transition timing
music/sound trigger timing
frame presentation boundaries
```

The contract is:

```text
same logical heartbeat
not same waiting machinery
```

### Data structures

Native data structures may be clean.

They do not need to keep every original segment-offset layout.

The native core may use:

```text
NativeGameState
PlayerState
ObjectState
LevelState
CameraState
RendererState
AudioState
InputState
SceneState
```

But the meaning must match the original game state.

For verification, projection layers may map native state back to oracle-style checkpoints.

The contract is:

```text
native layout may differ
state meaning must match
verification projection must be possible
```

## Phase 10: Recover the oracle heartbeat

Removing DOS timing machinery creates a major verification problem.

The native faithful port should not emulate every IRQ, wait loop, or retrace poll.

But it still needs to be verifiable against the original game.

The solution is to recover the original game-visible heartbeat.

The original heartbeat may be hidden inside:

```text
timer IRQs
main loop iterations
vertical retrace waits
input polling moments
frame flips
music ticks
animation/update cadence
```

The VM/oracle preserves the original machinery.

The native faithful port should expose the recovered heartbeat explicitly:

```text
GameTick
FrameBoundary
InputSampleBoundary
RenderBoundary
AudioEventBoundary
SceneTransitionBoundary
```

The contract becomes:

```text
same initial state
same input history
same recovered heartbeat
    -> same game-visible state
    -> same faithful frame/audio events
```

The faithful port should not emulate the old waiting machinery.

It should match what the game becomes at each heartbeat.

## Phase 11: Verify at explicit boundaries

The VM-less faithful port must be independent internally, but comparable externally.

Therefore the project needs explicit verification boundaries.

The most practical boundaries are usually:

```text
game tick boundary
frame boundary
input sample boundary
render boundary
audio event boundary
scene transition boundary
```

At these boundaries, the verifier can compare:

```text
PlayerState
ObjectState
LevelState
CameraState
SceneState
RNG state
score/lives
timers
active animations
spawn/despawn state
render state
audio event queue
final faithful pixels where appropriate
```

Early comparison may happen at low-level boundaries:

```text
registers
flags
memory ranges
routine outputs
framebuffer bytes
```

Later comparison should rise to source-level checkpoints:

```text
NativeGameState
    <-> VM oracle checkpoint

RendererState
    <-> oracle-derived render checkpoint

AudioEventState
    <-> oracle-derived audio checkpoint
```

The final faithful port should be tested at the level of game meaning, not at the level of DOS implementation trivia.

## Phase 12: Build state mirrors

To compare the faithful native runtime against the oracle, the project needs optional state mirrors or projection layers.

A useful shape is:

```text
faithful native state
    -> oracle-style projection
    -> checkpoint comparison
    -> divergence report
```

Or, when running side by side:

```text
same input replay
        |
        v
VM oracle --------------> oracle checkpoint
        |
        compare at heartbeat boundary
        |
faithful native --------> native checkpoint
```

The mirror exists only for verification.

It must not be required for normal gameplay.

```text
verification on:
    run VM oracle
    feed the same input history
    advance to the same heartbeat boundary
    produce checkpoints
    compare state mirrors
    compare render/audio outputs where appropriate

verification off:
    do not start VM
    do not maintain oracle projections
    run faithful native directly
```

The mirror verifies faithful.

It does not power faithful.

## Phase 13: Build the faithful native core

Once enough islands have been recovered and their boundaries are understood, they can be plugged into the VM-less faithful core.

The faithful core should contain:

```text
NativeGameState
InputState
PlayerState
ObjectState
LevelState
CameraState
SceneState
RendererState
AudioState
TimingState
```

The faithful runtime should run like a normal native game:

```text
read modern platform input
sample it into faithful InputState
advance fixed-step game simulation
produce render state
produce audio events
draw faithful frame
play faithful audio
```

The result should be behaviorally identical to the original game, but not architecturally trapped inside DOS emulation.

The faithful core is built from code prepared and verified in hybrid.

```text
hybrid prepares the code
faithful plugs it in
```

## Phase 14: Add faithful and enhanced presentation

Faithful and enhanced should not be separate gameplay forks.

They should be different presentation layers over the same native simulation.

```text
faithful core:
    owns game state and tick correctness

faithful presentation:
    original-style pixels/audio/input behavior

enhanced presentation:
    smoother or cleaner modern output
```

Enhanced may provide:

```text
object interpolation
camera interpolation
smooth scrolling presentation
smooth transitions
smooth palette fades
modern scaling
presentation-time effects
cleaner audio output
lower-latency audio buffering
improved mixing quality
```

But enhanced must not change:

```text
gameplay tick accuracy
input semantics
collision behavior
RNG sequence
object state
score/lives
level progression
scene progression
```

Enhanced is allowed to improve how the game is presented.

It is not allowed to become a different game.

## Phase 15: Extract the standalone product

At the end of the process, the source port should be extractable from the recovery machinery.

The full recovery repository may still contain:

```text
VM
hybrid runtime
ASM hooks
trace tools
snapshot tools
demo replay tools
state mirrors
checkpoint verifiers
debug dashboards
oracle comparison
```

But the standalone faithful product should need only:

```text
game assets
recovered faithful core
modern platform layer
modern input
faithful renderer
faithful audio
optional enhanced presentation/audio
```

The final product should be playable without VM execution.

The VM remains available for:

```text
debugging
regression testing
historical verification
future recovery work
development tooling
```

But it is no longer part of ordinary gameplay.

## Phase 16: Keep the VM as oracle

Even after the faithful source port is complete, the VM remains valuable.

It should be kept for:

```text
historical reference
bug investigation
regression tests
differential verification
trace generation
future recovery work
confidence in edge cases
```

The key runtime distinction is:

```text
verification enabled:
    VM oracle may run beside the recovered native game

verification disabled:
    no VM is started
    faithful/native game runs by itself
```

This lets the project be both:

```text
VM-less as a product
oracle-verified as a recovery effort
```

## What success looks like

The project succeeds when:

```text
the original game runs in VM/oracle mode
the hybrid runtime can replace original routines with verified recovered code
snapshots and demos can detect divergence
behavior islands have collapsed into a coherent recovered core
the faithful native runtime can run without VM execution
the native runtime can still be verified against the oracle
faithful output matches the original game-visible behavior
enhanced output improves presentation without changing gameplay
the standalone product can be separated from the recovery machinery
```

## Short version

The full lifecycle is:

```text
1. Build or reuse the shared dos_re foundation.
2. Put the original game into the VM.
3. Make it boot and run as original ASM.
4. Accept that it may be slow.
5. Make it observable.
6. Profile the hot paths.
7. Hook expensive and well-bounded routines first.
8. Make hybrid mode playable.
9. Record snapshots, demos, and replay evidence.
10. Recover behavior islands one by one.
11. Verify each island against the VM oracle.
12. Merge islands until the coastline collapses.
13. Separate recovered logic from VM adapters.
14. Define equivalence boundaries for gameplay/render/audio/input/timing.
15. Recover the original game heartbeat explicitly.
16. Compare native and oracle state at stable boundaries.
17. Build optional state mirrors and projections.
18. Plug recovered systems into the VM-less faithful core.
19. Keep faithful and enhanced as presentation layers over the same simulation.
20. Disable verification with one switch for normal native runtime.
21. Extract the standalone faithful product.
22. Keep the VM as oracle/debug infrastructure.
```

The shortest summary is:

```text
VM runs the original game.
Hybrid makes it recoverable.
Hooks make it fast and observable.
Snapshots and demos make it provable.
Islands make it understandable.
Island collapse makes it complete.
Faithful makes it standalone.
Enhanced makes it nicer without forking gameplay.
State mirrors keep it verifiable.
VM remains the oracle.
```

## Project mantra

```text
The VM preserves the original machine.
The faithful source port preserves the original game.

Hybrid prepares the code.
Faithful plugs it in.
Enhanced presents it better.
The oracle proves it did not drift.
```

## Where OVERKILL is on this lifecycle (2026-06-30)

A live snapshot so this generic lifecycle has a concrete position (re-derive from
`run_status.md` + `scripts/source_port_status.py`; this is a marker, not the source of truth):

- **Phases 0–5 (foundation → playable hybrid → snapshots/demos): DONE.** `dos_re` runs OVERKILL;
  hybrid is playable; demos under `artifacts/demos/` are the regression anchors.
- **Phase 6–7 (recover islands → merge): well advanced.** ~30.2% of game-logic mass is pure
  (`source_port_status.py`, 2026-07-03; was ~22% on 2026-06-30), 178 pure rules. The gameplay-frame
  mechanics are native and produced-vs-VM verified: input decode, player movement, world-scroll
  (`A66F`/`A6FE`), the whole object pass (all enemy/
  projectile behaviours, whole-pool), the tile-contact probe; plus render (native_video).
- **Phase 8–9 (separate logic from VM adapters / equivalence boundaries): in progress.** The
  layered architecture (views/bridge/domain/systems + the audits) enforces it; equivalence
  boundaries below are now the explicit contract.
- **Phase 10–13 (heartbeat, boundary verification, state mirrors, faithful core): started.**
  `NativeGameState` + `native_game_state_mismatches` (the mirror) exist; the native **frame
  controller** `systems/frame_loop.py` sequences the native stages VM-free; the heartbeat is the
  recovered ~72.8 Hz timer (`064A`/`06E5`).
- **NOT yet native (the remaining work — see `overnight_endgame_execution.md` §6 buckets):**
  the gameplay-frame spawn/death machinery (Bucket A/C), the front-end flow (E), native level +
  asset load (F), audio drivers (D — synths already exist: Nuked-OPL3 + PC-speaker), and the
  cold-boot backbone (G). Closing these = the VM-less full game.

### Equivalence boundaries applied to OVERKILL (the per-domain contracts)

Per Phase 9, each domain has its own faithfulness rule — these are the contracts the probes gate:

- **Gameplay (strict):** same initial state + same input history + same tick → same
  `NativeGameState`. Byte/state-exact vs the VM oracle at every checkpoint (the produced-vs-VM
  probes). Close enough is not faithful.
- **Render (pixel-exact, mechanism-flexible):** the native renderer need not reproduce Tandy/EGA
  bank tricks — given the same recovered render state it must produce the same visible pixels +
  palette at the frame boundary (the `verify_playfield_compose`/sprite-layer gates).
- **Audio (event/timing-exact, mixer-flexible):** same music/SFX events at the same tick; the
  mixer is modern (Nuked-OPL3 for FM, a square-wave PC-speaker). No gameplay dependency on host
  audio latency.
- **Input (semantic/timing-exact, path-flexible):** the host keyboard path may differ; the
  game-visible button state at each tick boundary must match (the input-decode gate).
- **Timing (logical heartbeat, not waiting machinery):** reproduce the ~72.8 Hz game tick +
  frame/input/audio cadence, **not** the DOS busy-waits/retrace polls.
