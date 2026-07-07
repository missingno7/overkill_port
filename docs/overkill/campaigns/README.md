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
| **DEMO LOCKSTEP (the ACTIVE campaign)** | byte+pixel-exact | opened 2026-07-07 (owner playtest #3) | `demo_lockstep.md` |
| Spine (mode machine + session) | byte-exact | graph described, not executing | `spine.md` |
| Player (move/fire/damage/death) | byte-exact | ~90% | `player.md` |
| Enemies & waves — L1 | byte-exact | ~80%, wired from snapshot | `enemies_l1.md` |
| Combat resolution | byte-exact | pieces recovered, unwired | `combat.md` |
| Scene content (spawn scripts) | byte-exact | **DONE** (2026-07-06): walker + 0x1A/0x19/BB03 native, play_native cold path spawns the wave | `scene.md` |
| Render | pixel-exact | largely done | `render.md` |
| Front-end (title/menu/select) | screen-exact | logic recovered, unwired | `frontend.md` |
| Audio | event-exact | not started | `audio.md` |

`docs/overkill/depth_recovery_plan.md` is SUPERSEDED by this directory (kept for the state
analysis). `run_status.md` is a thin JOURNAL (what happened, 5 lines/entry) — campaign charters hold
the plans and state.
