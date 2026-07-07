# Campaigns — the project's operating system (the pre2 convergence model)

> Adopted 2026-07-05. **The unit of work is a CAMPAIGN, not a slice.** pre2_port converged in 15
> days because it drove bounded subsystems to DONE (its island docs); this project meandered because
> it produced verified slices + re-banked plans. This directory replaces the frontier queue.

## The rules

1. **A session picks ONE campaign and pushes it toward its done-condition.** No hopping. Micro-work
   for other campaigns is allowed only when the active one is blocked on it.
2. **Done includes retirement.** A campaign is DONE when: its done-condition clauses are literally
   true, its oracles/probes are green, its VM hooks are retired to verify-only, and its charter is
   frozen (marked DONE, no longer edited).
3. **No re-banking.** A session must not end by writing a plan for work it didn't do. It ends by
   moving a campaign's state, or by explicitly closing/blocking one. (Discovered follow-ups go in
   the campaign charter's `next`, one line, not in new plan documents.)
4. **Equivalence tier is declared per campaign** and never silently changed: gameplay = byte-exact;
   render = pixel-exact (mechanism-flexible); front-end = screen-exact; audio = event-exact.
5. **The architecture decision (ADR-1): THE IMAGE IS THE GAME STATE.** One `MutFlatMemory` DGROUP
   image is the authoritative runtime state (byte-backed ≠ VM-backed); recovered memory-shaped
   systems read/write it (through the named object-record view as it grows); `NativeGameState` is a
   RENDER PROJECTION, never a second authority. Any code holding game state outside the image is
   transitional and must flow into the image within the tick that mutates it.

## The campaigns (the whole roadmap — L1-playable = Spine + Player + Enemies-L1 + Combat + Scene)

| campaign | tier | state | file |
|---|---|---|---|
| **DEMO LOCKSTEP (the ACTIVE campaign — all integration flows through it)** | byte+pixel-exact | ~5150/8292 L1 frames byte-exact; frontier in the charter | `demo_lockstep.md` |
| Spine (mode machine + session) | byte-exact | the gameplay frame is native (native_frame.py); the mode graph around it still hybrid | `spine.md` |
| Player (move/fire/damage/death) | byte-exact | **native in the lockstep frame** (moves/fire/death verified per-frame) | `player.md` |
| Enemies & waves — L1..L3 | byte-exact | **DONE for L1/L2/L3 demos** (the walk: zero divergence, zero gaps); L4 residue listed in run_status | `enemies_l1.md` |
| Combat resolution | byte-exact | native inside the walk (62F6/BEC5/BF25/BFC7 verified) | `combat.md` |
| Scene content (spawn scripts) | byte-exact | **DONE** + now runs at the REAL position (inside the scroll row pull) | `scene.md` |
| Render | pixel-exact | composers verified; the star-list mid-present occupancy is the open piece | `render.md` |
| Front-end (title/menu/select) | screen-exact | logic recovered, unwired | `frontend.md` |
| Audio | event-exact | the D50E DGROUP engine is native (lockstep-verified); host sound OUTPUT not started | `audio.md` |

`docs/overkill/depth_recovery_plan.md` is SUPERSEDED by this directory (kept for the state
analysis). `run_status.md` is a thin JOURNAL (what happened, 5 lines/entry) — campaign charters hold
the plans and state.
