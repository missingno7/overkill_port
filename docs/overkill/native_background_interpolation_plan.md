> **SUPERSEDED (2026-07-07).** This document is a historical plan/report from an earlier phase.
> It is NOT the current direction and may contradict the present state.  The live authorities:
> [`campaigns/README.md`](campaigns/README.md) (the operating model) →
> [`campaigns/demo_lockstep.md`](campaigns/demo_lockstep.md) (THE active campaign) →
> the TOP HEADER of [`run_status.md`](run_status.md) (the current frontier).

# Native background layer + object interpolation — staged plan

**Goal:** the last leg of the native renderer — a regenerable **background layer** so
the renderer composes `background → sprites` into a full faithful frame, and **object
interpolation** so motion is smooth at 120/144/240 Hz (the game still runs at its
native ~66.7 Hz; the renderer synthesizes the in-between frames).

**Why the bg is required (not optional):** the source page `[9598]` is composed
painter's-REVERSE — cleared, sprites drawn first, then the background drawn *around*
them (witness_background_boundary). So there is **no captured background behind a
sprite**; moving a sprite for interpolation would leave a hole. The bg must be
**regenerable** to fill behind moved sprites. It is a **tilemap**: `[9592]` holds tile
indices, expanded from 16×8 tile cells in `[959A]`/`[959C]`, windowed by the bg scroll
`[2350]` (reading the recovered loader `tandy.py:loading_tile_column_copy_36a2`).

**Sprite pipeline (done, verified):** decode (`sprite_textures`), extraction
(`sprite_draw_extractor`), native render (`sprite_layer`, byte-exact placement). The
interpolation primitive `composite_sprites(..., di_shift=)` is built + tested.

**Present clock (done):** decoupled multiprocessing present; the "62.5 Hz" was the
Windows timer resolution (fixed with `perf_counter` + `timeBeginPeriod`). Present
genuinely free-runs to the monitor refresh; `content`-Hz diagnostic shows held frames.

## Stages

- **A — Locate + understand the bg draw.** The per-frame bg composition is in the
  **Tandy mode presenter** dispatched from `5BDC` (`bx=[95BC]; jmp [5BE8+bx*2]`), not a
  top-level D007 call. Find the presenter, then determine the mechanism: per-frame
  **tile-expand** from `[9592]`, or a level-load pre-render into a buffer + per-frame
  **scroll-copy** of the visible window. Probe: `witness_*` capturing `[9598]`/candidate
  buffers with the **present cursor read at the frame top (game DS)**, not the
  compositor DS (= sprite segment → garbage). *(current step)*

- **B — Lift a pure, regenerable background layer.** A VM-free
  `render_background(tilemap, tile_cells, scroll) -> indexed (H,W)` in
  `overkill/recovered/systems/` (+ a bridge that reads `[9592]`/`[959A]`/`[959C]`/`[2350]`).
  VERIFY byte-exact vs the live bg (composed `[9598]` with the sprite regions excluded,
  or a clean pre-sprite capture if Stage A finds one). Mirrors the sprite-decoder slice.

- **C — Starfield.** Determine if the starfield is part of the tilemap or a separate
  parallax layer (a small probe). Recover it as semantic state (positions/generator +
  scroll) or fold it into the bg layer. No pixel capture.

- **D — Snapshot + renderer composition.** Carry the bg layer in `RenderSnapshot`
  (tilemap state or the regenerated indices + scroll). `LayerRenderer` composes
  `background → frame_sprites` (sprites already land correctly via `sprite_layer`).
  Source-boundary parity: at a tick, native == the faithful composed frame.

- **E — Object interpolation.** Between source ticks, hold/scroll the regenerable bg
  and redraw each sprite at `lerp(prev, latest)` by **identity** (the object-record
  address, already grounded; `di_shift` per sprite). Snap/fallback on
  spawned/destroyed/ambiguous identity (no guessing), counted in diagnostics. The bg
  fills behind moved sprites — the thing painter's-reverse made impossible from `[9598]`.

- **F — Controls + diagnostics.** Menu (overlay): **Native (no interp)** vs **120 / 144 /
  240 with interpolation**; persist to config. Diagnostics: `content`-Hz (done),
  interpolated/snapped object counts, interpolation alpha. Faithful (no-interp) stays
  the correctness baseline.

## Verification spine (every stage)
Pure unit tests for the VM-free pieces; a `verify_*` probe asserting byte-exact vs the
live game for the recovered pieces; lint + audit_architecture + the independence test.
Recovery-first: missing semantic state is recovered in the hybrid layer, never faked in
the renderer.
