# Native video backend — modern presentation layer

**Goal:** a VM-independent presentation backend that draws with native pygame/SDL
surfaces driven by the **monitor clock** (e.g. 240 Hz), while the original/hybrid
runtime keeps producing game state at its own cadence. The game must *behave and
look the same* at source-frame boundaries; only presentation runs at refresh.
Optional, opt-in interpolation makes motion smoother without changing gameplay.

```
game / hybrid runtime  (game cadence)
  → publishes an immutable RenderSnapshot per game tick:
      scene kind · indexed playfield layer (palette-independent) · playfield_version
      · palette + palette_version · scroll/camera · semantic sprites
      · (lifted as available) HUD/chrome layer · transition/fade state
  → NativeOverkillVideoBackend  (display cadence) — OWNS rendering:
      colorize indexed layers via palette (cached) · compose layers · draw sprites
      · interpolate (camera/objects) · present at monitor refresh
  → pygame/SDL display
```

**The backend owns the render pipeline.** It does *not* receive a finished RGB
frame and present it faster — it receives semantic, palette-independent render
state and renders the image itself, with caches. It must NOT depend on: the VM
framebuffer, the old B800/Tandy presentation timing/Hz, per-display-frame
deplanarization of VM memory, or a full faithful RGB frame as its normal input.
(It *may* consume normalized render-state layers the extractor produces — including
page-baked/chrome layers the original game baked — but as cached **render inputs**,
never as a live framebuffer fallback.)

## Render ownership & cache model (tailored to OVERKILL)
- **Playfield** = the composited source page `[9598]` decoded to 4-bit **indices**
  (palette-independent, the L1 layer); the backend colorizes via the palette and
  caches the result. The page content changes per tick (scroll + baked sprites), so
  the playfield re-renders per tick — but **held presents** of the same tick at high
  refresh are served from the colorized-frame cache (`(playfield_version,
  palette_version)` key) — the main high-refresh win.
- **Palette** is fixed for OVERKILL → `palette_version` is constant (LUT cached once);
  the structure still supports `smooth_palette_fades` (a version bump invalidates L2).
- **HUD/chrome** = a persisted page-baked layer (static; caches well once lifted).
- **Sprites/effects** = carried semantically (`SpriteDraw` + `screen_di`) for future
  object interpolation; today they are baked into the playfield page (so camera/scroll
  interpolation comes first; per-object interpolation needs the sprite-bitmap lift).
- Caches: **L1** palette-independent indexed layers/masks · **L2** colorized RGB keyed
  by `palette_version` · **presentation** uploaded SDL textures (display adapter),
  invalidated only on source-asset / palette / state change.

## Selection & configuration (no flag sprawl)
- One selector: **`play.py --backend vm|native`** (default `vm`). `vm` = the
  current faithful SDL/oracle viewer; `native` = this backend. No per-feature
  ``play.py`` flags.
- The native backend is a **self-contained presentation app** that owns:
  - a **config file** — its persisted settings (`native_video/config.py`:
    `load_config`/`save_config`, default `…/overkill/native_video.json`, override
    via `OVERKILL_CONFIG_DIR`; unknown keys ignored, missing defaulted);
  - an **in-game settings overlay** (native-only UI, drawn by the native renderer)
    that toggles interpolation/options live and **writes changes back to the
    config file**.
- **Future:** the native backend also absorbs **audio**, becoming the full modern
  presentation layer (video + audio + settings) over the VM game-logic/oracle.
  `BackendConfig` grows audio settings then; the overlay grows an audio section.

## Hard rules
- No VM framebuffer in the native hot path; no VM imports in `native_video`
  (enforced: `tests/test_native_video_independence.py`).
- No invented game state, no gameplay-timing changes, no broad refactor, no
  deleting the existing renderer, **no silent fallback** — unsupported cases are
  explicit and diagnostic-visible.
- Source-boundary parity stays testable: at a source frame's arrival the presented
  RGB *is* that frame's faithful baseline.
- When a gap in the model is found, fill it at the hybrid-runtime level and **lift**
  it to the high-level representation the native backend consumes.

## Module map (`overkill/native_video/`, backend layer)
- `page_raster.py` — the VM-independent decode: replays the present blit (3354)
  from `[9598]`@`[234C]` to **indexed** pixels (`decode_*_indices`), and `colorize`
  applies the palette. Grounded vs the live framebuffer. ✅
- `frame.py` — the seam: `RenderSnapshot` (semantic render-state: indexed playfield
  + versions + palette + scroll + sprites + `SceneKind`), `PresentedFrame`,
  `BackendConfig` (persisted settings), `BackendDiagnostics` (incl. cache/cost). ✅
- `renderer.py` — `LayerRenderer`: the backend's render core — colorize (palette LUT
  cache) + compose, with a colorized-frame cache keyed by version. ✅
- `config.py` — load/save the settings file (overlay + `--backend native` share it). ✅
- `backend.py` — `NativeOverkillVideoBackend`: display-independent, **thread-safe**
  present logic (game thread produces via `submit_source_frame`; present thread
  consumes via `present`; keeps the previous frame for interpolation). ✅
- `loop.py` — `PresentationLoop`: the **independent presentation thread** that
  drives `present` at the display cadence, decoupled from the game loop (re-holds /
  later interpolates between source frames). ✅
- `overlay.py` *(planned)* — the in-game settings overlay (native-only UI; toggles
  `BackendConfig` live and persists via `config.save_config`).

Bridge + display (outside the VM-independent package):
- `recovered/adapters/render_snapshot_adapter.py` — `extract_render_snapshot(mem,ds)`
  builds a `RenderSnapshot` from VM memory (game-thread extractor). ✅
- `scripts/native_play.py` — the pygame display adapter (`PygameDisplay`: blit/scale/
  vsync flip) + session runner: `--snapshot` (static), `--demo` (game-thread live),
  `--cold` (cold-boot intro→title→menu→attract). `play.py --backend native` delegates
  here (no source → cold boot). ✅ (pygame lives here, not in the VM-independent
  package). Snapshots are published throttled (~70 Hz) at any boundary IP (3354/
  timer/retrace) so **every scene** is captured — the menu/title/tally don't fire the
  gameplay present, so they advance via the timer/retrace waits.

Scenes & cold start: every scene renders via `composed_indices` (the page-baked
decode), so the menu/title/game-over already appear faithfully under the native
backend. A *semantic native menu* (menu items/selection drawn natively, crisp text)
is a future lift; cold boot is slow (interpreter-speed asset decode) and input is
not forwarded yet (the game runs autonomously) — both future refinements.

## Stages
- **Stage 0 — seam.** `NativeSourceFrame` / backend protocol / diagnostics. ✅
- **Stage 1 — native passthrough.** Backend holds the latest source frame's faithful
  playfield baseline; source-boundary parity. ✅ (logic + tests; the playfield
  rasterizer is grounded vs B800). Remaining: the pygame surface-blit adapter
  (display) + wiring into the viewer.
- **Stage 2 — presentation clock.** `present(now)` is wall-clock driven and fully
  decoupled from the source cadence; re-holds when no new source frame. ✅ (logic).
- **Stage 3 — camera/scroll interpolation.** ✅ The present cursor is monotonic, so
  the backend *extrapolates* the scroll forward past the latest tick (alpha ∈ [0,1])
  and shifts the playfield sublayer by `round(alpha × per-tick scroll)` rows —
  forward-only, no reversal/pop. Off → exact faithful parity. Flag
  `camera_interpolation`. NOTE: OVERKILL's witnessed scroll is ~1 row (~1 px) per
  tick, so the visual gain here is modest; the bigger win is Stage 4 object
  interpolation (fast sprites) — which needs the sprite-bitmap lift.
- **Stage 4 — object-wise interpolation.** Lerp sprites between source snapshots by
  semantic identity; snap/fallback per-object on ambiguous identity, report in
  diagnostics. Flag `object_interpolation`.
- **Stage 5 — optional features + debug compare.** Settings (default conservative)
  live in the config file + overlay, not `play.py` flags; `debug_compare` diffs
  native output vs the faithful frame at source boundaries.
- **Stage 6 — in-game settings overlay.** Native-only UI to toggle interpolation/
  options live, persisting to the config file (`overlay.py`).
- **Stage 7 — audio absorption (future).** Fold sound into the native backend so it
  is the full modern presentation layer (video + audio + settings).

## Known gaps to fill (lift to the model as we go)
- **HUD/border layer.** The present blit covers only the playfield
  (`x∈[0,208), y∈[4,196)`); the surrounding HUD (top strip, right 112 px panel,
  bottom strip) is page-baked in the visible page. *Witnessed:* the HUD region is
  **not** a plain decode of `[9596]`/`[9598]`/`[9592]` at offset 0 (best ~54 %),
  so it is drawn straight into the visible aperture and persisted — it must be
  modelled as a **persisted HUD overlay**: capture the HUD region from the grounded
  pipeline once (it is static / page-baked, changing only on score/lives updates)
  and composite it over the playfield, then lift its producer (`61DC` status
  display + right-panel chrome) so it is fully VM-independent. Next concrete step.
- **Object screen positions for interpolation.** `SpriteDraw.screen_di` →
  `di_to_screen` gives screen-space positions; ground identity continuity across
  source frames before enabling Stage 4.

## Diagnostics (required, in `BackendDiagnostics`)
source/present fps, frame hold count, interpolation alpha, source snapshot age,
camera/object interpolation active, interpolated/snapped object counts, native
render time, compare-diff at source boundaries.
