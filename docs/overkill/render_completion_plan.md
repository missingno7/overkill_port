# Plan: complete the Tandy render path (prepare for the enhanced renderer)

**This is the executable playbook.** Run it under `/goal`. The objective: a
*complete, faithful, witnessed-exact* semantic representation of **everything
drawn on screen over the entire Tandy game**, following the **original render
codepath**, so the enhanced renderer can consume it. No enhanced rendering yet.

Companion docs: `render_completeness.md` (the element checklist),
`enhanced_renderer_plan.md` (the two-clock model + R3/R4), `rescue_refactor.md`
(the recovery method). Work on **main**, push each green slice.

## Definition of done

Every on-screen element of the Tandy game — in every scene (gameplay, effects,
transitions, title/menu/intro/tally) — is a field/layer of
`recovered/domain/frame_snapshot.FrameSnapshot`, produced by a recovered method
that follows the original codepath, and **witnessed-exact against the VM** over
the demo corpus. At that point `FrameSnapshot` is the complete render contract.

## Method (every slice)

1. **Follow the original codepath.** Start from the frame dispatch (D007/97B2 →
   the routine that draws the element). Recover it faithfully — *lifted* if it
   must touch VM memory, *pure* (`recovered/systems`) where the logic is
   portable; group sensibly but make the methods compose as the original does.
2. **Model the output** as a `FrameSnapshot` field/layer (pure `recovered/domain`).
3. **Witness-exact.** Instrument the live draw over a demo and compare the model
   to the real output until they match exactly. *Witnessed-exact is the bar* —
   not "looks right".
4. **Gate + land.** `scripts/lint.py`, the frame-snapshot tests + any new test,
   `scripts/audit_architecture.py`; for runtime-touching changes the relevant
   oracle/demo-replay. Commit + push to main. One coherent slice per step.
5. **Track.** Tick the item in `render_completeness.md`; record findings in the
   adapter/docstrings (status ladder GUESS→OBSERVED→ASM_MATCHED→VERIFIED).

## Tools (already built)

- `overkill/probes/inspect_draw_list.py` — dump a snapshot's draw list + memory.
- `overkill/probes/witness_draw_order.py` — run a demo, instrument a render hook
  (via `registry.replacements[(seg,ip)].handler` patched with
  `object.__setattr__`), capture the live per-frame output, compare to the model.
- `frame_verify.run_frame_verifier(... publish_candidate=...)` — per-frame access
  to the candidate (hybrid) runtime. Extract at the **draw boundary** (first 5AC8
  of a render burst) for screen-position parity, not the present hook.
- Demo corpus under `artifacts/demos/demo_play_tandy_*` (gameplay, boss, death,
  mothership, menu, …) — the witnessing/verification set.

## Phases (ordered to unblock the most first)

### Phase A — Projection foundation (the keystone)
- **A1. Recover the `0fa3` video-offset table.** Build a pure `recovered/systems`
  (or `recovered/domain`) Tandy-screen module: `row_offset(y)`, `decode_di(di) ->
  (x, y)`, `encode_screen(x, y) -> di`. Ground it: round-trips the witnessed
  `(world, screen_di)` pairs and matches the table the game builds at 0fa3.
- **A2. Close `CameraState` + the present projection.** Recover the `5A92` present
  routine that writes `screen_di` from world coords; derive the camera as
  `world - decode_di(screen_di)` and confirm it is consistent across all drawn
  sprites every frame. CameraState → VERIFIED.

### Phase B — Complete the gameplay frame
- **B1. Present composition (`5BDC`/`3354`).** Model how the background plane,
  sprites, and HUD compose into the visible page (work page → visible, scroll,
  page flip / dirty regions). This is the "assemble the frame" step.
- **B2. Background plane content.** Model the `[9592]` plane as the background
  content (a reference + the scroll); plan its RGB decode (R3) but capture the
  plane identity/scroll now.
- **B3. Score + screen-shake.** Add the BCD score (`DS:2314`) to `HudLayer` and
  the camera-shake offset (`4C30`) as a `FrameSnapshot` field; witness both.

### Phase C — Effects & transitions
- **C1. Palette / fades.** The Tandy palette + fade transitions as a frame field.
- **C2. Explosions / hit-flashes.** Witness to classify: object-sprites (already
  covered) vs separate effects; model whatever is separate.
- **C3. Level start / transition wipes.** The per-level intro/wipe scene.
- **C4. Score tally / level-end.** The end-of-level tally screen.

### Phase D — Non-gameplay scenes
- **D1. Title / intro.** **D2. Menu / mode select** (confirm it reuses the sprite
  path via 97B2). **D3. Loading / scroll-in** (`60C5`/`36A2`). **D4. Game over /
  continue.** Each: a scene tag on `FrameSnapshot` + its render content, witnessed.

### Phase E — Completeness audit
- **E1. Whole-frame witness.** Across the demo corpus, for each scene, assert the
  model reconstructs *every* on-screen element witnessed-exact.
- **E2. Lock the contract.** `FrameSnapshot` is the complete, verified render
  representation; mark the completeness map done. Ready for R3 (rasterizer) / R4
  (interpolating compositor).

## Findings to carry (don't re-derive)
- Draw list = special view-anchor slot (DS:237C) + active on-screen slots, in
  scan order; **draw order == scan order** (draw_layer is not the z-sort);
  culling = `+0C != 0xFFFF`; `screen_di = +0C`. **Witnessed-exact.**
- HUD = six status counters (DS:2368) drawn by `61DC`, separate from the sprites.
- Background = pre-rendered `[9592]` plane copied scrolled by `DS:2350`; not a
  per-frame tile grid. In steady play it holds still while objects move (so
  interpolation rides on the playfield).
- `screen_di` is the `0fa3` banked offset table, not linear `world - camera`
  (Phase A1).
- Two clocks: render per **source** frame (~render every other display frame),
  interpolate per **display** frame. Extract the snapshot at the **draw boundary**.
