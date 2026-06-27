# Native video backend — modern presentation layer

**Goal:** a VM-independent presentation backend that draws with native pygame/SDL
surfaces driven by the **monitor clock** (e.g. 240 Hz), while the original/hybrid
runtime keeps producing game state at its own cadence. The game must *behave and
look the same* at source-frame boundaries; only presentation runs at refresh.
Optional, opt-in interpolation makes motion smoother without changing gameplay.

```
original/hybrid runtime
  → semantic FrameSnapshot / PresentComposition + page decode   (game cadence)
  → NativeSourceFrame                                            (the seam)
  → NativeOverkillVideoBackend                                   (display cadence)
  → pygame/SDL display at monitor refresh
```

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
- `page_raster.py` — the VM-independent visual source: replays the present blit
  (3354) from the composited source page `[9598]` at cursor `[234C]` and decodes
  via the recovered geometry + palette. Grounded vs the live framebuffer.
- `frame.py` — the seam: `NativeSourceFrame` (one game-cadence frame: baseline RGB
  + source cursor + semantic `FrameSnapshot`), `PresentedFrame`, `BackendConfig`
  (opt-in flags), `BackendDiagnostics`.
- `backend.py` — `NativeOverkillVideoBackend`: display-independent present logic.

## Stages
- **Stage 0 — seam.** `NativeSourceFrame` / backend protocol / diagnostics. ✅
- **Stage 1 — native passthrough.** Backend holds the latest source frame's faithful
  playfield baseline; source-boundary parity. ✅ (logic + tests; the playfield
  rasterizer is grounded vs B800). Remaining: the pygame surface-blit adapter
  (display) + wiring into the viewer.
- **Stage 2 — presentation clock.** `present(now)` is wall-clock driven and fully
  decoupled from the source cadence; re-holds when no new source frame. ✅ (logic).
- **Stage 3 — camera/scroll interpolation.** Interpolate the present source offset
  between frames. The cursor `[234C]` is monotonic / never reverses, so this is a
  simple forward-or-stationary lerp (no scroll pops). Flag `camera_interpolation`.
- **Stage 4 — object-wise interpolation.** Lerp sprites between source snapshots by
  semantic identity; snap/fallback per-object on ambiguous identity, report in
  diagnostics. Flag `object_interpolation`.
- **Stage 5 — optional features + debug compare.** Per-feature flags (default
  conservative); `debug_compare` diffs native output vs the faithful frame at source
  boundaries.

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
