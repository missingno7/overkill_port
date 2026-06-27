# Tandy render completeness — reveal the whole on-screen codepath

**Goal:** before any enhanced renderer, build a *complete, faithful* semantic
representation of **everything drawn on screen over the entire Tandy game**,
following the **original render codepath** (the recovered methods compose as the
original does; we may group them, but they must fit together). The VM stays the
oracle; the `probes/` witness each piece against live draws. See
`enhanced_renderer_plan.md` for the model and `rescue_refactor.md` for the method.

The output is `recovered/domain/frame_snapshot.FrameSnapshot` (the layered render
intent) + the recovered render methods that produce/consume it.

## The original per-frame render codepath (grounded from D007 / 97B2)

Both main frame loops drive the **same** render path:

| Step | ASM | Role | Status |
|---|---|---|---|
| video page setup | `1010:511F` | select work page / video setup | recovered (lifted) |
| sprite present scan | `1010:A846` → `5AC8` | draw the object sprites (the draw list) | **VERIFIED** (witnessed-exact) |
| present dispatch | `1010:5BDC` → Tandy `3354` | compose + blit the frame (background plane + scroll) to the visible page | lifted; **not yet in the model** |
| object present scan | `1010:A90C` → `5A92` | project objects (write `screen_di` / cull) | recovered (lifted) |
| status / HUD | `1010:61DC` | draw the six status-counter cells | grounded (HudLayer) |

Frame loops (top-level mode dispatch):
- **`1010:D007`** — gameplay frame loop.
- **`1010:97B2`** — attract / menu / gameplay frame loop (same render routines).
- Mode gate: `DS:BE06` (e.g. `==0x13` skips input — a non-interactive scene).

## The layered model (where each on-screen thing lives)

```
FrameSnapshot
├── background : BackgroundLayer       the [9592] master plane + scroll (DS:2350/2356)
├── playfield  : PlayfieldLayer        camera + sprite draw list (5AC8)         VERIFIED
├── hud        : HudLayer              six status counters (61DC)               grounded
└── present    : PresentComposition    source page [9598] + cursor → B800 (3354) grounded
```

The three content layers all composite into `present.source_page` ([9598]); the
Tandy presenter (3354) blits its scrolling window to the visible aperture. So
`present` is the single assemble-to-screen contract — and, because it is the same
for every scene, the faithful-fallback for non-interpolated scenes.

## Completeness checklist — everything that goes on screen (Tandy)

Each item: recover the original draw routine faithfully, model its on-screen
output, and **witness it against the live draws** before marking done.

### Gameplay frame
- [x] **Playfield sprites** — content + positions VERIFIED witnessed-exact.
- [x] **HUD status counters** — grounded.
- [x] **Background scroll position** — grounded (scroll_row/column_index).
- [x] **Tandy screen geometry (di ↔ screen x,y)** — recovered pure
      (`systems/tandy_screen.py`): `di = (y&3)*0x2000 + (y>>2)*160 + (x>>1)`,
      verified vs the framebuffer decode. This is the projection foundation — the
      renderer places sprites at `di_to_screen(screen_di)` and interpolates in
      screen space, so no separate world→camera projection is needed for sprites.
- [x] **Score** — BCD score (`DS:2314`/`2316`) in `HudLayer.score_bcd`.
- [x] **Present composition** — recovered `3354` + witnessed the page map
      (`probes/witness_present_pages.py`): every layer composites into one source
      page `CS:[9598]` (witnessed: the 2E6E/2F81 sprite compositors and 34C5 copies
      all write there, over the scrolled background), and `3354` blits its window
      (cursor `DS:[234C]`, the scroll) → visible `CS:[95A4]`=B800 via the Tandy
      bank geometry. Modelled as `PresentComposition` (source_page/source_cursor/
      video_page); grounded across the whole corpus (B800 aperture, valid source).
- [x] **Background master plane** — the `[9592]` master plane (the pre-render the
      game scrolls *from*) is captured as `BackgroundLayer.plane_segment`. The
      actual on-screen pixels live in `PresentComposition.source_page` (`[9598]`,
      bg + sprites composited); decode either to RGB at R3.
- [ ] **Display page `[9596]` role** — 5AC8 emits one direct-to-B800 draw per
      frame and a display-page (`[9596]`=25CC) scratch exists; classify (likely a
      HUD/overlay page) with a witness. Not blocking the source-page model.
- [x] ~~Screen shake~~ — no 4C30 shake global in OverKill (PRE2 pattern, N/A);
      revisit only if a witness reveals one.

### Effects / transitions
- [x] **Palette** — the fixed PCjr/Tandy 16-colour IRGB palette
      (`systems/tandy_screen.TANDY_PALETTE_RGB` + `unpack_pixel_byte`/`pixel_rgb`).
      OVERKILL never reprograms it (no palette-register writes in the render
      island), so it is the whole colour space; the rasterizer maps each 4-bit
      index straight through. Single source of truth, drift-guarded against the
      verified framebuffer decoder. With the geometry, this is the full mode-2
      RGB decode (`source_page` → pixels).
- [ ] **Fades** — fade-in/out transitions (if any reprogram intensity per-frame;
      witness a transition to classify).
- [x] **Explosions / hit flashes** — **objects, covered**. Witnessed on the
      `player_death` demo (`probes/witness_draw_order`): the death/explosion visuals
      are sprites 263–267 drawn through the standard `5AC8` object path and present
      in both the live draw list and the `FrameSnapshot` playfield — there is no
      separate effect-draw system. (5AC8 also dispatches some offscreen `+0C==FFFF`
      objects that render nothing; the model correctly culls them.)
- [x] **Level-end transition (in-gameplay)** — **covered**. Witnessed on the
      `L5_ending` demo (`witness_draw_order`): the level-end sequence renders through
      the standard `5AC8` object draws + the `[9598]`→`3354` present (drawn vs model
      differ only by the offscreen anchor slot) — no separate transition-draw
      system. The visible frame is the present blit of the composited source page.
- [ ] **Wipe / tally *screens*** — the dedicated per-level intro wipe and the
      end-of-level tally screen are **scene-entry producers** (like the menu, they
      draw once on entry, so steady-state demos can't witness them). They compose
      into `[9598]` and present identically, so the present+palette model is their
      **faithful-fallback**; full producer witnessing needs a scene-entry capture.

### Non-gameplay scenes
*Finding (witnessed):* the menu fires **none** of the gameplay render hooks
(5AC8/5A92/5BDC/61DC/3354/A846 all 0 over the menu demo) and has 0 sprites — the
scenes are a **separate producer** (text via the lifted `518C`/`519A`/`3153` glyph
path + menu cells, not the object-sprite system). But they still compose into the
same source page `[9598]` and present through `3354` — so the now-complete
**present + palette + geometry RGB decode is their faithful-fallback** (decode
`source_page` → RGB), and they do **not** block the enhanced renderer.

*Producer witnessing route (established):* the scene glyph draws happen on
**scene entry** (boot → title → menu), not in steady state — so the mid-scene demo
corpus witnesses **0 glyphs** (confirmed on every demo). The glyph path is already
lifted + oracle-verified (`rendering/text.py`), so the text/scene *model* can be
grounded against those routines directly. A live cold-boot witness (run from
`create_overkill_runtime`, wrap 3153) reaches the title text but is **too slow via
the pure-Python step loop** to capture within an interactive window — a scene-entry
snapshot capture is the practical path. These remain producer-modelling work, not
renderer blockers.
- [ ] **Title / intro** — title screen + intro (lifted glyph path; needs entry capture).
- [ ] **Menu / mode select** — lifted glyph path + menu cells via 97B2 (needs entry capture).
- [ ] **Loading / scroll-in** — the level materialization scroll (`60C5`/`36A2`).
- [ ] **Game over / continue**.

## Milestone: the gameplay frame is complete (enhanced-renderer-ready core)

The interpolation-critical layer — the **gameplay frame** — is fully modelled and
grounded: playfield sprites (VERIFIED witnessed-exact), HUD (counters + score),
background (scroll + master-plane reference), the Tandy screen geometry
(di ↔ x,y), **and now the present composition** (`PresentComposition`: the single
composited source page `[9598]` + scroll cursor → B800, witnessed). The enhanced
renderer can consume this now: decode `present.source_page` from
`present.source_cursor` via the bank geometry for the exact frame, or place
sprites at `di_to_screen(screen_di)` and interpolate in screen space per the
two-clock model, compositing the HUD. The gameplay frame is closed; remaining for
*entire-game* completeness is the separate scene render paths (faithful-fallback
above, which reuses this same present) and the effects/transitions.

## Method (per item)
1. Find the original draw routine (frame dispatch → the routine that draws it).
2. Recover it faithfully (lifted if VM-coupled, pure where the logic is portable),
   grouped to compose like the original.
3. Model its on-screen output as a FrameSnapshot field/layer.
4. **Witness** it against the live draws (`probes/witness_draw_order` and new
   per-scene probes) until the model matches the game exactly.
5. Only then mark it done here.

Definition of done for the whole map: every on-screen element of the Tandy game,
in every scene, is represented in the model and witnessed-exact against the VM —
a complete faithful frame, ready for the enhanced renderer to consume.
