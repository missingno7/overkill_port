# The endgame: a standalone native game, with the VM as an optional oracle

> User-set, 2026-06-27. This is the top-level destination that
> [`rescue_refactor.md`](rescue_refactor.md) (push lifted → pure recovered) and the
> [`native_video_plan.md`](native_video_plan.md) (the native backend) both serve.
> It supersedes any framing where the VM is a permanent runtime.
>
> **The executable, unattended loop that drives toward this destination is
> [`overnight_endgame_execution.md`](overnight_endgame_execution.md)** — the overnight
> brief: one verified slice at a time, tested against the demos, until standalone
> `--backend native` runs every demo with the VM as an optional oracle only.

## The destination

The final goal is **not** a hybrid that always needs the VM, and **not** a nicer
renderer bolted onto the VM. It is a **recovered native game that runs completely on
its own**, with the original VM/ASM kept available only as an **optional oracle** for
verification — a *detachable* harness, never a hidden runtime dependency.

```
verification enabled:   run the native game with oracle comparison
verification disabled:  run as a standalone native game (no VM started)
```

That toggle is the endgame. Not: `VM with a nicer renderer`. Not: `a pile of hooks
forever`. Not: `a renderer hacking around incomplete state`. But: **a recovered native
game with an optional oracle harness — switched on for confidence, off for standalone
play.**

## Mental model

```
recovered code        is the game
VM / original binary  is the oracle (debug reference, regression source, harness)
hooks                 are temporary scaffolding (disappear from the runtime path)
state mirrors         are test/debug bridges
native backend        is the future runtime / presentation layer
```

## Ideal final architecture

```
NativeGame:        recovered gameplay logic + game state + render/audio state; runs independently
NativeBackend:     renders/presents the native game; needs NO VM memory or original framebuffer
OracleVerification: OPTIONAL; runs the VM/ASM in parallel, compares native vs original, reports divergence
```

## Runtime modes

```
--mode standalone     run only the recovered native game (the VM is never started)
--mode hybrid         VM runs the original; recovered systems are called through hooks
                      (incremental replacement + debugging — the current default)
--mode verify         native runtime + VM oracle side by side; checkpoints compare native vs ASM
--mode record-oracle  run the VM/original and record expected semantic state traces
--mode replay-test    run the native game from recorded inputs, compare against the oracle traces
```

In **standalone** mode the game must NOT need any of: VM memory · interpreted ASM ·
original framebuffer · hook dispatch · CPU registers · segment addresses · live oracle
calls. In **verify** mode the *same* native code runs, wrapped in the oracle harness.

## The three layers and the direction of travel

```
Address / hook layer    CS:IP, registers, segments, VM memory, exact hook boundaries.
                        Temporary scaffolding replacing original ASM in the hybrid runtime.
Adapter / view layer    Maps VM memory layouts <-> structured state. Transitional glue.
Domain / system layer   Recovered game logic in source form (player FSM, object AI, combat,
                        collision, projectiles, pickups, camera, score, RNG). The PERMANENT
                        native game code.
```

The travel is always one way, and at every stage the piece stays verifiable vs the ASM:

```
ASM routine -> hook wrapper -> adapter/view -> recovered routine -> native system -> standalone game system
```

As recovery progresses: **hooks become thinner · adapters become smaller · domain/system
code grows · VM access becomes more structured · native state becomes the primary
representation.** Eventually the hook wrapper leaves the runtime path; the oracle remains
available only for verification.

## Dual-mode recovered systems (the key design rule)

A recovered routine should be usable in BOTH paths from the *same* source logic:

```
Hybrid:      VM memory/CPU -> adapter/view -> recovered system -> adapter writes back to VM memory
Standalone:  NativeGameState -> the SAME recovered system -> NativeGameState
```

So recovered systems are written against **source-level state structures the native side
owns**, not against `cpu`/segment:offset. The hybrid adapter reads VM memory into those
structures and writes results back; the standalone runtime passes the structures directly.
The same logic, tested in hybrid, is later used unchanged standalone.

## Verification compares semantic state, not raw memory

Early checks diff registers/memory at a routine boundary; as systems grow, verification
moves to **semantic state mirrors** the native side owns and the VM exposes via views/
adapters:

```
PlayerState · ObjectPool · ProjectileState · CombatState · CameraState ·
LevelState · ScoreState · RngState · RenderState
```

## The native backend's relationship

The native backend is the **presentation/runtime layer of the recovered game**, not a
clever renderer over incomplete VM state. It consumes recovered `GameState` /
`RenderState`, never the old framebuffer as its normal input. **If the backend needs state
that the recovered layer does not yet expose, recover that state properly at the
hybrid/source level first — do not fake missing game knowledge inside the renderer.** The
renderer naturally benefits from source recovery.

## The endgame chain

```
verified recovered systems -> complete native game runtime -> native backend over recovered state -> optional VM oracle for verification
```

The recovered code becomes the game. The VM/ASM stays valuable — as oracle, debug
reference, regression-test source, verification harness — but not as the required runtime.
