# OVERKILL recovery architecture — the rescue north star

> The ultimate **destination** is [`native_game_endgame.md`](native_game_endgame.md):
> a standalone native game that runs without the VM, with the VM/ASM kept only as an
> *optional, detachable oracle* (modes: standalone / hybrid / verify / record-oracle /
> replay-test). This doc (the rescue) is *how we get there* — pushing lifted code down
> into pure recovered systems that become the native game; recovered systems are written
> dual-mode (the same source logic runs in hybrid via adapters AND standalone over native
> state). The [`native_video_plan.md`](native_video_plan.md) backend is that game's
> presentation layer, not a renderer over VM state.
>
> Modelled on the sibling **PRE2** project (`missingno7/pre2_port`,
> `D:\Games\DOS\pre2_port`), which is this method done right. This doc is the
> top-level direction; `refactor_plan.md` (de-transliteration) and `loop_plan.md`
> (divergence-fixing) are *means* to it. Framework method lives in
> `dos_re/AI_PORTING_CHARTER.md` + `docs/overkill/source_port_methodology.md`.

## The strongest principle

> We do **not** want the final project shaped by hundreds of low-level hooks. We
> want it shaped by **reconstructed structs, recovered functions, and high-level
> systems**. Hooks and checkpoints are temporary contact points; dataclasses and
> recovered functions are the source port crystallizing out of the original game.

OVERKILL's pilot mistake was the opposite: it hooked too many things at too low a
level until the **hooks became the architecture** — a tight hybrid of part ASM,
part Python hooks, part guessed high-level logic. The rescue is not another
abstraction on top of that forest. It is to turn the forest into a smaller number
of **verified recovered islands** and merge them upward into clean native
subsystems. **Hook removal is progress.** The VM is the oracle, not the engine.

## Hooks are scaffolding — thin, with a role and a lifetime

A hook is a **minimal boundary adapter between the ASM/VM world and recovered
code. It contains no game logic.** A good hook only:

1. reads the relevant original memory/registers (via a **memory view**),
2. translates it into reconstructed **dataclasses**,
3. calls a clean **recovered function** (which knows nothing about CPU /
   segment:offset / pygame / raw memory),
4. compares/checkpoints against the ASM oracle when asked,
5. writes results back only when it is *replacing* that ASM path,
6. returns to the original control flow (exact return mechanics).

Every hook declares **which of four roles** it plays — and the role is its
intended *lifetime*, not a permanent fixture:

- **probe** — observe the original ASM (tracing, capturing oracles);
- **verifier / checkpoint** — diff a recovered island against the original;
- **replacement adapter** — replace a known ASM path in the hybrid runtime;
- **gap detector** — fail *loud* on unrecovered behaviour.

*A hook without a lifetime is suspicious; a hook without a merge target is
suspicious.* If movement/collision/object-behaviour/sprite/animation/asset-decode
logic is accumulating inside a hook, it belongs in a recovered function **outside**
the VM layer. The inventory of all 336 hooks (role + subsystem + merge target +
shrinking path) is generated in `hook_inventory.md`; today it is **12 checkpoint +
5 env_wait + 319 glue** — the 319 glue hooks are the coastline to collapse.

## One recovered leaf, many adapters — convergence, NOT parallelism

This is the principle OVERKILL most violated. The goal is **one verified recovered
function per behaviour**, with several *thin adapters* pointing at it — never a
second copy that can drift:

```
                 recovered/systems/<leaf>      ← the ONE implementation
                       ▲     ▲     ▲
   replacement adapter ┘     │     └─ (later) enhanced backend
   (hybrid runtime: skip      │
    the ASM, run the leaf)    └─ verifier / checkpoint (oracle diff at the boundary)
```

When a hook takes over a routine, the game still *triggers* it, but the recovered
leaf runs and the ASM body is skipped (`cpu.s.ip = cpu.pop()`): the game gets
faster **and** we gain proof we understood it. We do **NOT** want three copies of
a behaviour — a hook version + a faithful version + an enhanced version.

**The OVERKILL anti-pattern (now being deleted):** the "checker" — a hook that
calls the pure recovered function only to *assert agreement* while a full
ASM-shaped replay is still the real implementation. That is two copies; the replay
is dead weight and a drift risk. The fix is to make the recovered leaf **live**
(it produces the result; the adapter writes it back) and delete the replay. (Done
for the movement clamp/scroll family; in progress for collision.)

## Islands declare their merge target — and collapse into bigger islands

Early on the project is many small verified islands behind thin hooks. That shape
is scaffolding, not the destination. Each island is written as real recovered
source from the start and declares the larger system it merges into:

| Island (now) | Merges into (later) |
|---|---|
| codec (RLE/LZ/packed) | asset loader |
| masked blit / layer sprite | renderer backend |
| collision query / tile probe | CollisionSystem |
| movement clamp / scroll-edge | MovementSystem |
| object-behaviour fragment | ObjectSystem |
| frame-state fragment | GameStateSystem → `update_frame()` |

Neighbouring islands coalesce into subsystems; subsystems into a single native
`update_frame()`. **Collapse rule:** collapse several leaves into one larger
island **only with evidence from the real original call graph** (they genuinely
belong to one original routine/controller). *Never* collapse to a modern invented
design. Verification boundaries rise as islands merge (see below).

## Dataclasses are the bidirectional bridge — reconstruct structs first

Our dataclasses are **not arbitrary modern abstractions** — they are our
reconstruction of the original C-like structs and runtime state: `ObjectSlot`
(have), then `PlayerState`, `LevelState`, `CameraState`, `RendererState`,
`GameState`, asset records. They are the **main translation layer**, connecting in
both directions:

- **ASM memory → dataclass** — read from live VM memory through a *memory view*
  (the real byte layout / field offsets);
- **recovered logic → memory** — the same dataclass is consumed/produced by clean
  recovered functions and written back when an ASM path is being replaced.

```
original ASM memory
  → memory views (recovered/views)
    → reconstructed dataclasses (recovered/domain)
      → clean recovered functions (recovered/systems)
        → semantic state comparison
          → (optional) write-back to original memory when replacing ASM
```

Reconstructing these factual state structures **first** is what lets verification
rise from address-level to state-level.

## Verification compares contracts, not accidental ASM shape

We want exact behaviour, but not permanent dependence on every tiny accidental ASM
boundary. The contract level rises as understanding improves:

- **Early:** register/flag/memory diffs at individual ASM routine boundaries
  (the per-hook oracle + `--verify-hooks`).
- **Later:** **semantic state contracts** — `ObjectSlot` state after an update,
  `PlayerState` after movement, renderer output after a draw phase, eventually
  whole-frame state after `update_frame()`.

Per-hook address diffing is an early scaffold; as islands merge, checkpoints
become fewer and move **up** to clean semantic boundaries. **Relax a low-level
oracle when it forces ASM-shaped code to exist** (a proven-dead flag/scratch is
not part of the contract) — demo-replay at the higher boundary is the real proof.

## Status taxonomy — every recovered piece is exactly one of these

1. **recovered + live** — recovered leaf + replacement adapter + verifier (runs in
   the hybrid runtime; the ASM body is skipped).
2. **recovered, verify-only** — leaf + checkpoint diff, but the ASM still runs (no
   live skip yet).
3. **checker-only (transitional, to fix)** — the leaf is computed but only asserts
   against an ASM replay that's still the real impl. NOT an endpoint — make it
   live or delete the replay.
4. **known gap** — not recovered; fail loud, no silent ASM fallback.
5. **blocked — history-dependent state** — the real game keeps stateful buffers; a
   from-scratch rebuild is wrong; needs the real stateful model.
6. **not worth hooking** — a pure controller/setup/present wrapper with no hot or
   reusable behaviour (keep as a thin checkpoint/map, don't grow it).

## Two runtime modes — no silent fallback

- **hybrid (default)** — recovered native code runs **in place of** the ASM, no
  per-step verification; the real runtime. If it reaches unrecovered behaviour it
  **fails loud** (a precise gap), never secretly runs the ASM.
- **verify** — separate, demo/snapshot-driven: replay the same inputs through the
  ASM oracle and the recovered path, diff at the current contract boundaries,
  report the first divergence. Not a permanent lockstep straitjacket.

## The rescue, subsystem by subsystem (not a big-bang rewrite)

Pick one subsystem from `hook_inventory.md`, gather its hooks, and run the loop —
**each pass must do at least one of:** move logic out of a hook into a recovered
function · replace raw memory with a view/dataclass · merge two duplicated hook
tails into one recovered helper · add a verifier / state contract · raise a
checkpoint to a semantic boundary · delete a probe or a glue hook · remove
hook-owned gameplay logic · reduce dependence on registers/segment-offsets/
continuation IPs.

Order (glue density × leverage; **backends stay isolated**, never merged into game
logic):

- **movement** — *done*: clamp/scroll hooks thinned, MovementSystem live.
- **collision** — *in progress*: pure rules live; delete the ~49 checker asserts
  per-function (full oracle each — cross-fn flag traps, e.g. AF survives the RET).
- **gameplay_objects** (55 glue) → ObjectSystem (behaviour bodies → pure rules).
- **game_state** (45) → GameStateSystem; keep broad controllers (`9b2e`/`d007`)
  as **frame MAPS / oracle-composition scaffolds**, never grow them.
- Reconstruct state dataclasses (slot ✓ → player/level/camera/input) so
  verification can rise to semantic contracts.
- Backends (`*_renderer`, `layer_sprites`, `sound`, `asset_codecs`, `file_io`,
  `overlay`) — thin their hooks, keep isolated.
- Classify the 4 `unknown` hooks; give each a merge target.
- Create `overkill/probes/` + `overkill/evidence/`; move investigation tools and
  heavy one-off traces out of the live tree. Keep `hooks.py` thin; never grow it.

## Layers (enforced) and self-describing islands

`scripts/audit_architecture.py` enforces dependency direction (upward only; the
**pure** layer must not import the VM/hooks/backends/bridge):

```
overkill/recovered/views/      memory views over VM memory          [bridge]
overkill/recovered/adapters/   translation adapters                 [bridge]
overkill/recovered/domain/     reconstructed dataclasses (pure)     [source_pure]
overkill/recovered/systems/    clean recovered functions (pure)     [source_pure]
overkill/recovered/islands.py  @recovered_island metadata (pure)    [source_pure]
overkill/gameplay/             VM-aware adapters (must become THIN)  [lifted]
overkill/hook_wrappers/, hooks.py  thin registration glue            [hook_boundary]
```

Each recovered leaf self-describes via `@recovered_island(asm=…, contract=…,
status=…, merge_target=…)` (status: GUESS < OBSERVED < ASM_MATCHED < VERIFIED <
CANONICAL). `scripts/gen_island_manifest.py` → `recovered_islands.md`;
`tests/test_island_registry.py` is the drift check. Code is the source of truth.

## Definition of done (per slice)

- a reconstructed dataclass / state contract exists;
- the recovered function is **live** (it produces the result) and VM-free;
- the hook is a thin adapter: read view → call recovered fn → write/check → return;
- no second copy of the behaviour remains (no checker beside a live ASM replay);
- duplicated tails merged into one recovered helper;
- a verifier exists (per-hook oracle and/or a higher semantic contract);
- `@recovered_island` metadata + manifest regenerate clean (drift test passes);
- **the coastline is shorter or higher-level than before** (a glue hook thinned,
  merged, or deleted).
