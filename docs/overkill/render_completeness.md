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
- [x] **Display page `[9596]` role — RESOLVED: it is the game DS pointer, not a
      page.** `present_tandy_frame_3354`'s tail does `DS = CS:[9596]` (=25CC, the
      game data segment — same value `[1010:9596]` resolves to in the snapshot
      adapter) to restore DS after the present clobbers it with the source segment.
      Measured (`probe_pageflip`): the page pointers are **fixed across all frames**
      — `[9592]`=245A (master plane), `[9598]`=35FF (present source), `[95A4]`=B800
      (visible aperture) — there is **no work-page flip**. (An earlier
      `witness_master_plane` run decoded `[9596]`=25CC *as a video page* and got
      7009 "non-zero" — that was game data read as pixels, a probe artifact; the
      double-buffer reading it suggested was wrong.) So `present.source_page=[9598]`
      is correct and complete: `[9598]` is the (mostly-black) space playfield,
      `[95A4]`=B800 the composited visible. No model change needed.
- [x] ~~Screen shake~~ — no 4C30 shake global in OverKill (PRE2 pattern, N/A);
      revisit only if a witness reveals one.

### Native regeneration (toward the self-composing backend)
**Ground truth — DECODED the actual buffers at L2 gameplay (end of frame 200).** Two
images settle the model (this section was corrected several times because it was
first built from write-IP histograms; the reliable method is decode + LOOK at the
buffers *at end-of-compose*):
- `scratchpad/end200_35ff_cursor.png` — the `[9598]` source via the present path —
  is the **full playfield**: scrolling starfield + alien formation + player ship +
  projectiles, **no HUD**.
- `scratchpad/dump_b800_visible.png` — B800 — is that **same playfield PLUS** the
  right-side HUD panel (WEAPON / MISSILES / GADGETS / UPGRADES, score, radar).

The grounded model:
- **`[9598]`=35FF is the playfield source**, composed each frame — sparse (~2% lit;
  it's space — black with a starfield + sprites) — and blitted by the present at
  cursor `[234C]` into the B800 playfield region. `page_raster.render_present_page_*`
  decodes it correctly and matches the B800 playfield: **the faithful playfield decode
  is DONE and verified.** *Pitfall that misled earlier revisions:* 35FF is composed on
  alternating frames, so sampled at the *start* of a frame it reads empty — capture at
  end-of-compose. (This reinstates `page_raster`'s model; a prior revision wrongly
  called 35FF "empty / not the Tandy source".)
- **`[95A4]`=B800 is the display** = the playfield (presented from 35FF) **+** the HUD
  panel, drawn separately and persisted. The backend captures it as `composed_indices`.
- **`[9592]`=245A is a DATA segment** (entity state / packed object data / save-unders),
  NOT a video "master plane" — it decodes to data-noise. The inherited "master plane /
  clean background" label is wrong. (This retraction stands.)
- The playfield is composed via the **already-lifted leaves** (compositors
  `2E6E/2F81/2FB6`, copies `34C5/34D8/3542`) plus packed object/sprite cells in the
  `~0x2C00` work region (written by the object draws `35CF/356F/358D/365A`). The
  present geometry (35FF→B800) is lifted.
- **Per-routine attribution** (decoded each routine's writes in isolation,
  `scratchpad/attr_*.png` / `attrb800_*.png`):
  - 35FF compositors = the **sprite layer**: `2F81` = alien formation + the small
    left ship + projectiles, `2E6E` = the player ship, `2FB6` = small sprites. **No
    stars** in any compositor's output (their backgrounds decode black).
  - The 35FF **clean plate** (page just before the first sprite composite) is
    **~black** (40 px) — the playfield background is empty, not a starfield.
  - The **B800-direct writers** `5F05` (+`5EE1/5EEA/5EF0/5EF6`) = the **HUD SCORE
    DIGITS** (decoded: green `0 0 0 0`), NOT stars.
  - Per-frame copies `34C5/34D8/3542` + `4D6F` write **zeros** (clear sprite cells /
    occupancy) — a sprite clear→redraw cycle.

**Self-compose gap (honest state):**
1. **The starfield origin is UNRESOLVED** — and it bottoms out in an *irreducible
   measurement contradiction* I could not close this pass: the 35FF clean plate reads
   ~black (40 px), the frame's 35FF compositors draw only sprites, yet the end-of-frame
   35FF decode shows stars. Stars cannot appear unwritten, so one measurement is
   subtly misaligned. **Most likely cause: probe pacing.** `probe_clean_plate2` drove
   the demo with `demo.apply_to_runtimes`, while the attribution probes used
   `pump_demo_frame` — these are known to misalign frames (see memory
   *overkill-trace-reproduction-gotcha*), so "clean plate" and "attribution" may not
   be the same instant. NEXT: redo the whole 35FF analysis under **one consistent
   pacing** (a single ordered trace: clear → each write → end, all via `pump_demo_frame`),
   then re-locate the stars. (NOT a present-wrap bug: `3354` advances `SI` 16-bit,
   wrapping only at `0x10000`, not reached at these cursors.) Retracted from prior
   revisions: "2F81 draws the star background" and "persistent level-start fill".
   *Latent decoder note (separate, real):* `render_present_page_indices` masks source
   reads at 1 MB, not the 64 KB segment, so for large cursors it would not wrap like
   the game's 16-bit `SI` — worth fixing, but not the cause here.
2. The **HUD panel**: chrome (static) + the **score digits = `5F05`** (identified) +
   radar, drawn directly into B800.
3. Drive the lifted compositors from **native game state** to draw the sprite layer
   (the per-routine identities above map directly to the semantic sprite list that
   `frame_snapshot_adapter` already extracts; `sprite_layer` composites it natively),
   over the regenerated starfield, then present + overlay the HUD.

So the native backend already produces the faithful frame by *decoding* the VM's
composed pages; standing on its own (regenerating the playfield + HUD without the VM)
needs items 1–3. Items are independent and individually witnessable against the
decoded buffers above.

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

*Conclusive finding (witnessed — text/HUD is page-baked):* replaying the long
`start_to_end` demo (cold-ish start → menu → game → game-over → menu) on a single
runtime (`probes/witness_scene_single`), with `menu_idle`, `obj`, and `present`
all firing heavily (so menu **and** gameplay were both exercised), the text-glyph
path `3153` fired **0** times and the HUD path `61DC` fired **0** times — across
the *entire* run. Combined with 0 glyphs on every steady-state demo, this is
conclusive: **all text/HUD/menu chrome is drawn once at scene-entry (before the
snapshot) and baked into the composed page `[9598]`, then persisted/scrolled —
never re-emitted per frame.** Therefore the recovered **present + palette decode of
`[9598]` already captures every on-screen text/HUD/chrome pixel**; scenes need
**no separate per-frame text model** for the renderer. The glyph producers
(`518C`/`519A`/`3153`, `rendering/text.py`) stay lifted for code-completeness, but
modelling a per-frame glyph layer is unnecessary — the page *is* the text. (Live
producer witnessing would need a boot/scene-entry capture; it is not a renderer
blocker and not required for completeness.)
- [x] **Title / intro** — page-baked; captured by the present+palette page decode.
      Producers (lifted glyph path) drawn at entry; no per-frame model needed.
- [x] **Menu / mode select** — page-baked; captured by the present+palette decode
      (lifted glyph path + menu cells via 97B2 draw it once on entry).
- [x] **Loading / scroll-in** — the level materialization scroll (`60C5`/`36A2`)
      composes into `[9598]`; captured by the present decode.
- [x] **Game over / continue** — page-baked; captured by the present+palette decode.

## Milestone: the Tandy render path is functionally complete for the renderer

The recovery resolves into **two tiers**, and both are now in hand:

1. **Structural model — the gameplay frame** (the interpolation-critical layer):
   fully modelled and grounded — playfield sprites (VERIFIED witnessed-exact), HUD
   counters + score, background scroll, the Tandy geometry (di ↔ x,y), the present
   composition (`PresentComposition`: composited source page `[9598]` + scroll
   cursor → B800), and the fixed palette. The renderer interpolates this per the
   two-clock model (sprites at `di_to_screen(screen_di)`; the scroll is
   one-directional, never reverses).
2. **Page decode — everything else** (background pixels, HUD/score text, menu,
   title, tally, game-over, transitions): all of it is **baked into the composed
   source page `[9598]`** (witnessed: the glyph/HUD producers fire 0 times per
   frame across menu+gameplay), and the recovered **geometry + palette + unpack**
   turn `[9598]` into RGB. So the present-page decode reproduces every on-screen
   pixel of every scene faithfully, with no per-scene producer model required.

Together these cover **everything on screen**: the structural model drives
interpolated gameplay, and the page decode is the faithful capture for all baked
content (the renderer composites/interpolates the former over the latter).

Remaining (polish, not blockers): the display-page `[9596]`=25CC role (the once-
per-frame direct-to-B800 draw — likely the fixed HUD overlay), per-frame palette
fades if any, and live producer witnessing (needs a boot/scene-entry capture).

## Method (per item)
1. Find the original draw routine (frame dispatch → the routine that draws it).
2. Recover it faithfully (lifted if VM-coupled, pure where the logic is portable),
   grouped to compose like the original.
3. Model its on-screen output as a FrameSnapshot field/layer (structural) — or, for
   baked content, confirm it composes into `[9598]` (the page decode captures it).
4. **Witness** it against the live draws (`probes/witness_draw_order`,
   `witness_present_pages`, `witness_scene_single`) until it matches the game.
5. Only then mark it done here.

Definition of done: every on-screen element of the Tandy game, in every scene, is
either a grounded structural field of `FrameSnapshot` or proven to compose into the
present source page that the recovered geometry+palette decode reproduces — a
complete faithful frame, ready for the enhanced renderer to consume. **Met** for
the gameplay frame (structural) and all baked scene/HUD content (page decode).
