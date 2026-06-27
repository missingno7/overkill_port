# Enhanced Tandy renderer + frame interpolation — audit & plan

**Goal:** an *optional* enhanced video backend that draws the game directly to
pygame (modern RGB) with **frame interpolation**, **without the VM in the render
hot path**. Follow the **Tandy** path only (full experience, simpler than EGA's
4-plane model). The VM stays the oracle that proves the native renderer correct.

Modelled on the sibling PRE2 enhanced renderer
(`D:\Games\DOS\pre2_port\docs\pre2\enhanced_renderer_design.md`,
`render_model.md`). See `rescue_refactor.md` for the overall recovery posture.

---

## 1. Audit — where rendering is today

**The render path runs through the VM.** The Tandy renderer
(`overkill/rendering/tandy.py`, ~2100 lines, **68 of 69 functions take `cpu`**)
is a VM-coupled *backend*: it reads/writes the original video memory (the Tandy
banked framebuffer) and is driven by replacement hooks. Frames reach the screen
as: `VM runs → renderer hooks draw into VRAM → present hook (1010:3354 Tandy) →
play.py / frame_verify decode VRAM → RGB → pygame`. The VM is in the loop.

**What already exists (assets in our favour):**
- **A pixel oracle.** `overkill/frame_verify.py:_render_rgb_bytes` decodes VM VRAM
  → RGB and `compare_samples` diffs it. `scripts/render_frame.py` decodes the
  Tandy framebuffer (160 bytes/row, bank stride 0x2000, 320×200). *Any* native
  renderer can be verified pixel-exact against this.
- **The draw intent is present in memory** — just not modelled. Object slots carry
  `sprite_or_state`, `x_word`/`y_word`, `draw_layer`; plus camera/scroll globals,
  the tilemap/background state, and the 16-colour Tandy palette. The A846
  layer-sprite scan already projects on-screen objects into render slots.
- **Assets decode natively.** `overkill/asset_codecs/` (RLE/LZ/packed) is recovered
  — sprite/tile bitmaps are obtainable without the VM.
- **Recovered systems + dataclasses** (`recovered/systems`, `recovered/domain`)
  and the layering audit give us a clean home for VM-free render code.

**The gap (what's missing for BOTH goals):**
1. **No semantic frame-state model.** There is no `FrameSnapshot` capturing *draw
   intent* (sprite list + positions + tilemap/scroll + camera + palette + shake)
   decoupled from VRAM. This is the single prerequisite for a VM-free renderer
   *and* for interpolation (you interpolate the model, not pixels).
2. **No VM-free rasterizer.** All rasterization is the cpu-coupled backend that
   writes VRAM. Nothing turns a semantic state into RGB without the VM.
3. **No interpolation layer / two-clock model.** Today there is one clock (the VM
   present). Interpolation needs prev+current source-frame snapshots presented
   across multiple display subframes.

---

## 2. The two clocks (the core design correction, per PRE2)

The game logic commits a **source frame** far less often than the **display
refresh**. PRE2 measured ~25 source fps (~3 retraces/frame); OVERKILL's per-frame
work is similarly small (frame loop `1010:D007`, present `1010:3354`). We must
**measure OVERKILL's source cadence** (a probe), but the model is fixed:

- **Render the faithful/native base once per SOURCE frame** (~25–35 Hz).
- **Interpolate cheaply per DISPLAY subframe** (60/144/240 Hz): lerp sprite &
  camera positions; **discrete-swap** animation frames and tile ids (never lerp a
  sprite/tile id); palette fades are transition-only.

Re-rasterizing per *display* frame is infeasible/pointless; interpolating the
*model* per display frame is cheap and is the whole win. In active play objects
move nearly every source frame, so **per-object interpolation** (not just camera)
is the real payoff.

---

## 3. Target architecture

```
            SOURCE frame (≈25–35 Hz)                 DISPLAY subframe (60–240 Hz)
 VM memory ─► extractor ─► FrameSnapshot ──┐
 (oracle)    (verify-only  (pure dataclass) │   keep prev+current
              checkpoint)                   ├─► interpolate(prev,cur,t) ─► RGB
                                            │     (lerp pos/camera, swap anim)   │
 native assets ─► native Tandy rasterizer ──┘                                   ▼
 (decoded sprites/tiles/palette)  FrameSnapshot → RGB surface             pygame blit
                                  (verified vs frame_verify RGB oracle)   (no VM)
```

- **`FrameSnapshot`** (pure, `recovered/domain`): camera (x,y), background/tilemap
  ref + scroll/fine-scroll, palette[16] (Tandy RGB), screen-shake, and a **sprite
  draw list** `[(sprite_id, screen_x, screen_y, layer, flip, frame), …]`. This is
  the render model — the only thing the renderer and the interpolator consume.
- **Extractor** (`bridge`): reads VM memory → `FrameSnapshot` at the source-frame
  boundary. Initially a *verify-only* checkpoint (the VM still draws); proven by
  round-trip (re-render the snapshot, match the VM framebuffer).
- **Native Tandy rasterizer** (`recovered`, VM-free): `FrameSnapshot` + decoded
  assets → RGB. Verified **pixel-exact** against `frame_verify`'s RGB oracle. This
  is the "faithful" native renderer — one recovered implementation, used as both
  the source-cadence base and the verification surface (the *one leaf, many
  adapters* rule — not a parallel renderer).
- **Enhanced compositor** (`backend`/new `overkill/enhanced/`): keeps prev+current
  `FrameSnapshot`, interpolates per display subframe, composites RGB → pygame.

This is exactly the rescue methodology applied to rendering: reconstruct the state
dataclass first, then verification rises from VRAM pixel diffs to a **semantic
frame contract**, then the renderer is lifted off the VM.

---

## 4. Phased plan

- **R0 — Freeze the RGB oracle.** Adopt `frame_verify._render_rgb_bytes` (Tandy)
  as the pixel ground truth. *Exists.* Add a small probe to measure OVERKILL's
  **source cadence** (present count vs game-frame commits), like PRE2's
  `measure_source_cadence.py`, to size the interpolation factor.
- **R1 — `FrameSnapshot` semantic model.** Pure dataclass(es) in `recovered/domain`
  for camera/tilemap/palette/shake + the sprite draw list. No VM.
- **R2 — Frame-state extractor + round-trip proof.** A verify-only checkpoint at
  the source-frame boundary: VM memory → `FrameSnapshot`. Prove completeness by
  re-rendering the snapshot through the *existing* Tandy path and matching the VM
  framebuffer over the demo corpus. (If a snapshot field is missing, the
  re-render diverges — that's the gap detector.)
  - *Finding (R1):* the faithful draw list is **not** "every active object slot".
    `run_present_object_scan_pair_a90c` walks two **presence lists** — `DS:8D12`
    (34, A90F scan) and `DS:32CA` (36, A927 scan) — populated by the 4CED
    presence-stamp, dispatched per-object via 5A92. R2 must recover those
    presence-list entries (object ptr + screen position) as the draw list. The R1
    object-table extractor is a scaffold/hypothesis to replace, not the contract.
- **R3 — Native Tandy rasterizer.** VM-free `FrameSnapshot` + decoded assets → RGB,
  verified pixel-exact vs the R0 oracle over the demo corpus. Reuse the recovered
  asset codecs; lift the Tandy sprite/tile blit math out of the cpu-coupled
  backend into pure functions that write an RGB buffer.
- **R4 — Enhanced interpolating compositor.** `overkill/enhanced/`: prev+current
  snapshots, per-display-subframe interpolation (lerp pos/camera, discrete anim
  swap), composite → pygame. Optional backend, VM disabled in the render hot path.
  Verify the *source-frame* outputs still match the oracle; interpolated subframes
  are an enhancement (no oracle, judged visually).

Order is strict: **R1+R2 are the prerequisite** for everything; R3 makes it
VM-free; R4 adds interpolation.

---

## 5. Immediate next best step

**Build R1 + R2: the `FrameSnapshot` model and a verify-only extractor at the
source-frame boundary, proven by round-trip against the VM framebuffer.**

Why this first:
- It is the prerequisite for *both* the VM-free renderer and interpolation.
- It is **fully verifiable now** (round-trip re-render vs the existing frame
  oracle) — no guessing, fits the rescue's "reconstruct state, verify the
  contract" discipline.
- It immediately raises a verification boundary from VRAM pixels to a **semantic
  frame contract** — progress for the whole rescue, not just rendering.
- It de-risks R3/R4: once the snapshot round-trips, the native rasterizer and the
  interpolator have a proven, complete input.

Concretely, start by enumerating the draw list: capture the A846 layer-sprite
scan's output (the on-screen projected sprites: id + screen x/y + layer) plus the
camera/scroll globals and the Tandy palette into the first `FrameSnapshot`, and
stand up the round-trip test on one Tandy demo.

---

## 6. Risks / unknowns

- **Source cadence unmeasured** — R0 probe resolves it; interpolation factor
  depends on it (expected ~2–3 display frames per source frame at 60–70 Hz).
- **Sprite addressing / animation frame** — the `sprite_or_state` field → actual
  bitmap + current animation frame mapping must be reconstructed for the draw list
  (the round-trip will expose any gap).
- **Background/tilemap as history-dependent buffer** — OVERKILL may keep a scroll
  ring / dirty-rect background (PRE2 does). If so the snapshot must model the
  scroll state, not rebuild the background from scratch (a known PRE2 trap).
- **Tandy specifics** — banked 160-byte rows + the pixel-pair lookup; the native
  rasterizer reproduces the palette mapping (render_frame.py is the reference).
