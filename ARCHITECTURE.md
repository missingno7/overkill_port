# OVERKILL port architecture

This project is a behaviour-exact source port grown from verified 8086 ASM
hooks. The code spans a spectrum from "still essentially the original ASM,
proven against the VM" to "clean, backend-agnostic source". This document names
the layers, states the dependency rules, and points at the audits that enforce
them.

The guiding direction: **the VM should become an oracle/test harness, not the
engine.** Higher layers may depend on lower layers; lower (cleaner) layers must
never depend back up on the VM/CPU/segment world. Tandy is the primary backend
target; EGA/CGA are preserved but isolated and do not drive architecture.

## Snapshot model: checkpoints, not hook boundaries

A registered hook address is **not** automatically a permanent source-port
boundary.  Treat the two runtimes differently:

- **The VM (original ASM) stays instruction-level** snapshotable/stepable - it is
  the oracle, and every historical `CS:IP` is observable there.
- **The source-port runtime is checkpoint-level** snapshotable.  It resumes only
  from stable *logical* boundaries - **frame, object-update, render, input** (and
  the hardware/environment waits).  Between two checkpoints, lifted source-like
  code may run as **one atomic deterministic chain**: it does not need to preserve
  every old `CS:IP` bounce or support arbitrary mid-chain resume.  A snapshot
  requested mid-chain is deferred to the next checkpoint, or represented as the
  previous checkpoint + deterministic replay.

So classify every hook by **role**, not address (`overkill/hook_taxonomy.py`,
reported by `scripts/source_port_status.py`):

| Category | Meaning | Direction |
|----------|---------|-----------|
| **checkpoint** | a real logical resume boundary (frame/object-update/render/input) | keep, make explicit |
| **env_wait** | hardware/environment wait (PIT/IRQ0 timer, CRTC retrace, INT9) the interpreter can't satisfy natively | keep hooked, even on the oracle reference |
| **debug_probe** | exists only to observe/verify | keep out of the hot path |
| **glue** | accidental ASM-boundary plumbing: behaviours, tails, helpers, per-object/row scan steps | **collapse** into source-like chains between checkpoints |

Today that split is ~12 checkpoints / ~5 env-waits / ~319 glue.  The glue is the
collapse target.  **Correctness during collapse is protected by the semantic
frame/state verifier against the VM (the demo-replay equivalence suite), not by
preserving every historical hook boundary.**  Per-hook oracle metadata
(`verification.py`) remains the VM-side proof; it does not constrain how the
source-port chain is shaped between checkpoints.

### The frame is already a checkpoint sequence

The gameplay main loop `1010:D007` (and the attract loop `97B2`) is a linear chain
of `CALL`/`RET` phase calls - the frame is *already* decomposed into RET-bounded
systems, each a place where state is consistent:

```
D007  frame top ───────────────── FRAME checkpoint
  0672              clear timer flag                     (env)
  511F  A846        per-frame video setup + layer render  RENDER phase
  5BDC  -> 3354/2750/447B  present dispatch + blit ────── RENDER checkpoint
  A90C  A940  (AA10)  presence scan + state update ────── OBJECT-UPDATE checkpoint
  5F61  073C        score/status, sound                  (sub-systems)
  5160  0679        display-start + timer wait ────────── FRAME-PACING (env waits)
  0162              input poll ───────────────────────── INPUT checkpoint
  jz D007                                                 loop
```

Every phase entry above is already a registered hook.  So the source-port loop
does not need inventing - it is `D007`'s phase sequence, with each phase a native
system entered/exited at its checkpoint, and the behaviours/tails/helpers each
phase calls are the glue to fuse inside it.

### VM-until-checkpoint handoff

A demo or snapshot taken at *any* instruction can run in **VM mode (instruction-
exact) until it reaches the first compatible checkpoint**, then hand off to native
source-like code.  This means oracle snapshots no longer need to be captured at a
behaviour's exact entry to be usable by the source port - capture anywhere, fast-
forward in the VM to the next frame/object-update/render/input checkpoint, and
resume natively from there.  Between checkpoints the native chain is atomic and
deterministic; a snapshot requested mid-chain is the previous checkpoint + replay.

## Layers (high = closest to ASM, low = closest to pure source)

| Layer | Packages | May depend on | Notes |
|-------|----------|---------------|-------|
| **vm / orchestration** | `dos_re` (external), `overkill/` top-level: `runtime`, `verification`, `coverage`, `headless_verification`, `frame_verify`, `launch`, … | anything | Drives the emulator, hook verifier, snapshots, coverage. |
| **hook_boundary** | `overkill/hooks.py`, `overkill/hook_wrappers/*` | lifted, bridge, source, backend, vm | Thin `@registry.replace` glue: registers addresses, sets up CPU/stack/return mechanics, delegates. **No gameplay/render/audio logic.** |
| **lifted** | `overkill/gameplay/*` | bridge, source, backend (constants), vm | VM-aware Python reproducing original behaviour on the original memory layout (object runtime, collision, frame orchestration, action spawns, contact/overlap). |
| **backend** | `overkill/rendering/*`, `overkill/sounds/*`, `overkill/asset_codecs/*`, `overkill/file_io/*` | source, bridge, vm | Backend-specific: Tandy/EGA/CGA rendering, PC-speaker SFX, AdLib/Roland music, timer conductor, asset/overlay loading. **Must not import `gameplay`.** |
| **bridge** | `overkill/recovered/adapters/*`, `overkill/recovered/views/*`, `overkill/recovered/*` facades | source_pure, vm | Projects VM/DOS memory ⇄ portable domain records. The one place CPU/mem may meet domain. |
| **source_pure** | `overkill/recovered/domain/*`, `overkill/recovered/systems/*` | source_pure only | Portable, VM-free game logic primitives. No `cpu`/`mem`/`dos_re`. |
| **game_core** | `overkill/game_core/*` | (nothing in `overkill`) | Backend-agnostic native-core seam: `Video/Input/Audio/Timing` backends + `AssetProvider` protocols and neutral types. Stdlib only. |

The directive's five conceptual buckets map onto these as:
VM/ASM-bound = **vm**; Hook boundary = **hook_boundary**; Lifted/recovered =
**lifted + bridge**; Backend-specific = **backend**; Source-like
backend-agnostic = **source_pure + game_core**.

## Hard dependency rules (enforced — a violation fails the build)

1. **`source_pure` and `game_core` must not import** the VM (`dos_re`),
   `hooks`, `hook_wrappers`, `gameplay`, any backend, or the recovered bridge.
   They must stay reachable without the emulator.
2. **`game_core` must not import any other `overkill` package** — it is a
   standalone, platform-neutral seam. VM-backed *adapters* implement its
   protocols from the outside.
3. **`backend` must not import `gameplay`** — backends sit behind a boundary and
   never reach up into the game systems.
4. The pure recovered layer must not name `cpu`/`mem`/`memory` or import the
   bridge (finer-grained; see `audit_recovered_layers.py`).

Tolerated, documented cross-cut: a lifted gameplay routine may reference a
backend *hardware constant* from its single source of truth
(`gameplay/frame_orchestration.py` → `sounds.loaded_driver`'s 2032 segment id).
Such exceptions are whitelisted explicitly in `audit_architecture.py`.

## Where new code goes

- Reproducing an original routine that still touches CPU/memory → `gameplay/`
  (lifted) with a thin wrapper in `hooks.py`/`hook_wrappers/`.
- Portable rule with no VM concepts → `recovered/domain` or `recovered/systems`.
- Anything a real native engine would call platform code for → a `game_core`
  protocol + a backend adapter (adapters live in `backend`/`vm`, never in
  `game_core`).
- Backend-specific drawing/sound/asset work → `rendering/`, `sounds/`,
  `asset_codecs/`, `file_io/`.

## VM-backed views (the translation layer)

`overkill/recovered/views/*` are the typed lenses between the VM and the
source-like code.  A view is a **live overlay**, never an owned entity: every
field read/write goes straight to the original DOS memory at `seg:base+offset`,
so `slot.x_word += dx` updates the real VM image and the emulator and the
source-like code never disagree.  There is **no parallel native state** — the DOS
image stays the single source of truth.

Current views and the live consumer that introduced each (a view is added **only
when a real hook/adapter uses it** — no speculative/dead overlays):

| View (`recovered/views/…`) | Shape | First live consumer |
|----------------------------|-------|---------------------|
| `object_slots.ObjectSlotView` | one 0x38-byte object/effect slot; named fields + `record_bytes()` | `gameplay/object_bounds.py` AD60 bounds tail |
| `object_slots.ObjectTableView` | a whole object table (effect/gameplay), indexable/iterable slot views | `recovered/adapters/game_snapshot_adapter.py` |
| `frame_timers.FrameTimersView` | the six `DS:2368` countdown counters; read-all / write-one / `address_of` | `gameplay/game_state.py` 61C7 scan |

Rules for this layer:

- **Views may know layout** (segment:offset, strides, table bases) but hold **no
  gameplay decisions** — those live in `recovered/systems` (pure) and are replayed
  by the lifted hook.
- **Keep them explicit and debuggable**: one plain property/method per field, no
  descriptor/decorator magic.
- **Flag/register-exact contracts stay in the hook.** A view replaces the *memory
  access* (`mem.rw(ss, bp+OFF_X)` → `slot.x_word`); it does **not** absorb
  flag-affecting ASM helpers (`_add_mem_word`, `set_sub_flags`, the BX walk in a
  scan loop) — those remain visible in the lifted body so it stays byte-exact.
- **Adding a view is proven, not asserted**: convert the consumer, then show the
  per-hook oracle test (byte/register/flag identity vs interpreted ASM) plus
  `test_demo_replay_equivalence.py` (and `test_recovered_semantics.py` for the
  snapshot path) still pass.

A view is also the **living memory map** of its structure: `OBJECT_RECORD_FIELDS`
in `object_slots.py` catalogs every word of the 0x38 object record with a
discovery status — `known` (role proven), `guessed` (offset proven, role
inferred — names often carry `_OR_`), or `unknown` (a real record word not yet
identified, listed explicitly rather than left as a silent gap). It is the single
status source the dashboard reads (`source_port_status.py` → "Reconstructed
structures"), so "what have we mapped, what's left" is a number, and promoting a
field (`unknown`→named, `guessed`→`known`) is a visible, test-checked step. Offset
*facts* stay single-sourced: the map references the `OFF_*` constants, and the
snapshot is built from the view's named fields (no parallel offset→field decode).

## Status / visibility

- `scripts/source_port_status.py` — read-only dashboard of the ASM→source
  migration: per-layer line mass + `cpu`/`mem` density, the headline "% of
  game-logic mass that is pure source", the pure-rule count, and structural flags
  (oversized hook-boundary files). Run it before deciding *what to clean next* —
  it reuses the enforced `layer_of` map so it never drifts from the build.

## Enforcement

- `scripts/audit_architecture.py` — project-wide layer map + hard rules above.
- `scripts/audit_recovered_layers.py` — cpu/mem name leaks in the pure recovered
  layer.
- `tests/test_game_core_backends.py` — `game_core` import purity + protocol
  contracts.
- `tests/test_architecture_layers.py` — runs the layer audit and checks it is
  not vacuously passing.
- `scripts/audit_hook_oracle.py` — every registered hook keeps oracle metadata
  (behavioural proof is not sacrificed for structure).

## Known-messy / next refactors

- `overkill/gameplay/object_runtime.py` (~1.1k lines, down from 4.5k = −76%) is
  now close to a thin dispatch spine. Carved out: `object_spawns.py`,
  `object_runtime_common.py` (leaf infra), `object_deactivation.py` (death/score/
  clamp tails), `object_movement.py` (~1.4k: steps/clamps/scroll/coord/steer/seek),
  `object_postmove.py` (BC45/BC4B hub), `contact_side_effects.py` (62F6/BEC5/
  9E69), `contact_overlap.py` (B250 selector), `object_behaviors.py` (~1.1k: the
  B73E/B86D/B9F0/ABxx/AED8 behaviour families + AA2B/EFAE logic dispatch), and
  `object_bounds.py` (AD60/AD5A bounds-tile + 5073/505B tile probes). What's left
  in `object_runtime.py`: the candidate-scan infrastructure (`_scan_*`), the
  dispatch-target resolvers (`_*_target_*`), the runtime-patched-steer plumbing,
  the registered-hook wrapper bodies, and the *movement behaviours* that route to
  postmove (drift AE2C/AE7D, chase B1B0, tile-sweep B00D). Next seam: split those
  movement behaviours into `object_movement_behaviors.py`, leaving a pure scan +
  dispatch spine. **9E19 contact side-effect: done** — the `B250` selector's
  `B297` loop now calls the native `run_post_contact_status_helper_9e19` instead
  of interpreting it (Phase-2 collapse, covered by the demo-replay suite); only
  its `61DC`/`511F` display children remain bounded.
- **Next gameplay interpreted target:** `1010:B2CD`, a waypoint path-following
  movement loop (walks the `A45C`/`A43C` coordinate tables, calls the lifted
  `5DB2` per waypoint, sets `logic_id=12h`). Hottest unhooked gameplay routine in
  the L2 coverage dump; reached alongside `BB03`/`BB80`. Needs an oracle capture.
- `overkill/hooks.py` still holds non-EGA inline blits; move them behind thin
  wrappers like the EGA renderer already is. **Done:** `477E`, `41DA` (bodies now
  in `rendering/tandy.py`). **Remaining:** `497A`, `38B7`, `3849`, `41A6`, `447B`,
  presence-stamp, dirty-cell presenter. The 8086 helpers most blits need already
  live in `rendering/tandy.py`; `497A` additionally uses the `SF` flag.
- `game_core` has no live VM-backed adapters yet (Tandy-video→Framebuffer,
  scancode→InputEvent, PC-speaker/OPL→AudioBackend, 0679→TimingBackend,
  overlay→AssetProvider). Building those is how the VM becomes an oracle.
- AdLib music still runs interpreted in real play (timer-ISR early-bail); see
  the sound/music notes.
