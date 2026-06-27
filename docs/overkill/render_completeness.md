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
├── background : BackgroundLayer   the [9592] pre-rendered plane + scroll (DS:2350/2356)
├── playfield  : PlayfieldLayer    camera + sprite draw list (5AC8)         VERIFIED
└── hud        : HudLayer          six status counters (61DC)               grounded
```

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
- [ ] **Background plane content** — the `[9592]` plane → RGB (the actual level
      pixels). The present (`5BDC`/`3354`) copies it scrolled; model the plane
      identity + scroll now, decode to RGB at R3.
- [ ] **Present composition** — recover `5BDC`/`3354`: how the background plane,
      sprites, and HUD compose into the visible page (page flip / dirty regions).
- [x] ~~Screen shake~~ — no 4C30 shake global in OverKill (PRE2 pattern, N/A);
      revisit only if a witness reveals one.

### Effects / transitions
- [ ] **Palette / fades** — Tandy palette + fade transitions.
- [ ] **Explosions / hit flashes** — are these objects (covered by sprites) or
      separate effects? (witness to classify).
- [ ] **Level start / transition screens** — the per-level intro/wipe.
- [ ] **Score tally / level-end** — the end-of-level tally screen.

### Non-gameplay scenes
- [ ] **Title / intro** — the title screen + intro sequence.
- [ ] **Menu / mode select** — the menu (uses the same sprite path via 97B2;
      confirm the menu content is in the object tables).
- [ ] **Loading / scroll-in** — the level materialization scroll (`60C5`/`36A2`).
- [ ] **Game over / continue**.

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
