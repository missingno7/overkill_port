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
  dispatch spine. **Open behavioural target:** 9E19 is still run as bounded
  interpreted ASM inside the B250 selector (`contact_overlap.py`); lifting it
  would absorb the last interpreted contact side-effect, but needs its own oracle.
- `overkill/hooks.py` still holds non-EGA inline blits (`497A`, `477E`, `38B7`,
  `41DA`, `447B`, presence-stamp, dirty-cell presenter); move them behind thin
  wrappers like the EGA renderer already is.
- `game_core` has no live VM-backed adapters yet (Tandy-video→Framebuffer,
  scancode→InputEvent, PC-speaker/OPL→AudioBackend, 0679→TimingBackend,
  overlay→AssetProvider). Building those is how the VM becomes an oracle.
- AdLib music still runs interpreted in real play (timer-ISR early-bail); see
  the sound/music notes.
