# Loop blockers — divergences/targets that need the user (or better tooling)

Open items the autonomous loop attempted but could not finish byte-exact. Do NOT
re-attempt these in the loop; they need a reproduction trace and/or gameplay
context. Each has the analysis already done so a human can pick up fast.

---

## Player-death `BC4B`/`BFC7` divergence (demo: `demo_play_tandy_player_death`)
- Hook-verify: `1010:BC4B object_postmove_bc4b` call 1691 diverges at continuation
  `AA04`. `AX asm=0000 hook=0060`, `SI asm=0003 hook=00DC`, 2 memory words differ
  (`0x0073→0x00EC`, `0x005E→0x0060`), plus a nearby position-list (`9682/968C/9696`).
- **Ruled out:** the `BFC7` death tail itself. Disassembled (capstone) the full
  `BFC7..C054` path and the `C037` obj_type jump table @`C042`
  (type1→`C048: mov [bp+8],0; ret`, type2→`C04E: mov [bp+8],3; ret`). The lift in
  `object_deactivation.py:273-289` matches these exactly. The differing words are
  NOT `[bp+8]` (which is 0/3 in both), and `AX`/`SI` aren't touched by the handlers.
- **So the bug is elsewhere in `BC4B`'s path** — `BD17` deactivate, the
  post-contact `9E69` tail, the contact window `AA46`/`AA71`, or upstream state.
  All of `BD17`/`9E69` are still "partial/observed" lifts.
- **Next step for a human/trace:** reproduce, single-step `BC4B` call 1691, and
  bisect which child first makes `AX`/`SI`/the position-list diverge, then
  disassemble that child and compare. Tooling is ready: capstone is installed;
  `artifacts/static_runtime_bundle/memory_1mb.bin` holds the original image
  (`1010:off` → linear `0x10100+off`).

## Mothership camera-Y divergence — RESOLVED 2026-06-19
- Symptom: `globals.camera_or_view_y_2380` +1 in the hooked runtime at the
  mothership (frame 68 of `mothership_drag_edge_case`), dragging several effect
  objects' `y_word` +1. (Was a standing demo-replay failure.)
- **Root cause:** the `9B2E` lift (`frame_orchestration.py`) dropped the
  `[a47c]==0` guard on the `9C01` camera-step call. In the ASM, `9BCF jne 9BDF`
  makes `[a47c]==0` a precondition for BOTH `9CB6` and `9C01`; the lift gated only
  `9CB6` by `[a47c]==0` and gated `9C01` by `[2350]>0xB6` alone. Once the
  mothership trigger (`A66F`) sets `[a47c]=1` (vertical scroll lock), the ASM
  stops calling `9C01` but the hook kept calling it -> one extra `inc [2380]`
  per camera frame (the half-rate `9C01` ran on f65/f67 in the hook, not the ASM).
- **Fix:** nest the `[2350]` poll-gate + `9C01` call inside the `if [a47c]==0`
  block. Demo-replay drag case passes; 17/18 demos green (only `menu_interaction`
  left). Also added `phase_gate_a47c` (DS:A47C) and `level_progress_2350`
  (DS:2350) to `SNAPSHOT_GLOBAL_WORDS` so a future phase/progress divergence is
  caught at its own frame instead of only downstream via the camera anchor.

## `menu_interaction` demo divergence — RESOLVED 2026-06-19
- Symptom: demo-replay TIMEOUT (not a state divergence) -- `side=reference
  frame=89 at=1010:CBE4`. The reference oracle hung; all decoded state matched.
- **Root cause:** a frame-verifier oracle limitation, not a port bug. The menu
  transition runs CB3E, a 5x `CALL CBD5` delay; each CBD5 loads AL=[54] then
  spins `cmp al,[54]; je` until the INT 1Ch timer ISR (`1010:06E5`, tail
  `inc [54]; and [54],3`) advances the tick. The frame verifier models time via
  the `0679`/`50C9` boundaries and never fires that async ISR, so `DS:[54]` is
  frozen at 0 and the busy-wait spins to the frame budget. Interactive play fires
  the real ISR, so the live game/menu was never broken (verified: `[54]/[55]/
  9907/66b` and the loop IP all matched between sides through frame 88).
- **Fix:** `input_waits.advance_frame_tick_wait` -- the verifier-only per-step
  wait handler now ticks `DS:[54]` (one `071D`-equivalent step) when a side is
  parked in the CBD5 busy-wait, so the delay drains in place. Applied to both
  sides identically (lockstep). Interactive play is untouched (it uses
  `title_fire_release_wait`, not `frame_verify_input_wait`). Whole demo-replay
  suite now green: 18/18 (0 failures).

## BDD0 player-hazard-scan hit-path oracle — RESOLVED 2026-06-19
- Fix: the hit-path in `run_player_hazard_object_scan_bde3` (collision.py) now
  lands IP on the `1010:5059` STC;RET stub (the original `JMP 5059`) instead of
  collapsing it with `set_carry_and_return` -- SI and the link-key CMP flags were
  already set by the candidate check, so the snapshot matches the ASM at 5059.
  The child-call path `_call_player_hazard_scan_bdd0` (object_runtime.py) now
  drains the 5059 stub after the wrapper returns, so the near-CALL frame is
  balanced (CF set, popped to return_ip) -- this is what the earlier reverted
  attempt was missing (it regressed demo-replay 2->3). Both BDD0 oracles pass;
  demo-replay stays 18/18; collision oracles green.

  (historical) Pre-existing FAILING oracle: on a hazard hit the hook
  ended at the caller (`CAFE`) but the original is at `1010:5059`.
- **Root cause (confirmed by disasm):** `BE32: JMP 1010:5059`, and `5059` is
  `STC; RET` (`f9 c3`, already has `SIG_COLLISION_STC_RET_5059`). The lift
  (`collision.py run_player_hazard_object_scan_bde3`) collapses the tail-jump into
  `set_carry_and_return(cpu, True)` (STC+RET eagerly) -> lands on the caller.
- **The conflict:** changing the hit-path to `cpu.s.ip = 0x5059` (match the jmp
  granularity) makes the *oracle pass* but REGRESSES a demo — because BDD0 is also
  invoked as a child via `object_runtime.py _call_player_hazard_scan_bdd0` /
  `_call_verified_child_near`, whose continuation logic expects the collapsed
  return, not an IP landing on `5059`. (Verified: that change took demo-replay from
  2 -> 3 failures.) Reverted.
- **Resolution needs a human call:** reconcile the oracle's single-step
  expectation (IP=5059, then the 5059 hook runs STC;RET) with the child-call
  wrapper (which must then step through 5059). Either update the wrapper to run the
  5059 stub, or adjust the oracle to compare the collapsed end state. Both the
  `5059` STC;RET hook and `_call_verified_child_near` need to agree.

## D434 selector input-release-wait oracle — RESOLVED 2026-06-19
- Fix (oracle convention): `run_selector_input_release_wait_d434` models phase 1
  only (the `[98E4]` release-wait) and hands phase 2 (the `[98BE]` button-poll
  loop D43B-D443) to raw ASM -- correct for the live game (demo-replay passes).
  The oracle wrongly stepped the ASM 6 steps *into* phase 2 (and case 3 expected
  `D445`, only reachable via phase 2), comparing two different routines. Updated
  the oracle to compare at the hook's phase-1 exit boundary: `[98E4]==1` loops at
  D434, `[98E4]==0` falls through to D43B (buttons irrelevant to phase 1), both
  with the phase-1 CMP flags. Phase 2 / D445 stays covered by demo-replay.

  (historical) Only FLAGS differed (asm `0202` vs hook `0297`) for `[98E4]==0`.
- **Root cause:** `run_selector_input_release_wait_d434` (input_menu.py) models
  only *phase 1* (the `CMP [98E4],1` release-wait) and leaves IP at `D43B` with
  the phase-1 cmp flags (`0-1` -> CF/PF/AF/SF = 0297). But the oracle steps the
  raw ASM 6 times, *into phase 2* (the `[98BE]` button-poll loop: D43B/D43E/D443),
  so the ASM lands at the same IP with the phase-2 `CMP [98BE],0` flags (0202).
- **Same class as BDD0:** a hook that intentionally collapses/under-models vs an
  oracle that steps further. Real fix = model phase 2 (the [98BE] poll loop) in
  the hook so its flags match, but phase 2 nests the 0162 input-poll hook and the
  hook is "phase-1-only by design" -- extending it risks the live menu path.
  Needs a human decision (extend the hook vs fix the oracle's step granularity).

## 33AF expand-tandy-list oracle — RESOLVED 2026-06-19
- Fix (oracle convention): the hook is now one header-iteration per call
  (`expand_tandy_list_33af` reads the 44D7 header and dispatches to 33B2 or, at
  end-of-list, 44AA; `expand_tandy_block_33b2` processes a block and loops back
  to 33AF), verified independently. The `composes_headers_and_blocks` oracle
  single-stepped the hook (landing at 33B2) but stepped the ASM through the whole
  expansion to 44AA. Updated it to iterate the hook to the 44AA terminator like
  the ASM, so it compares the full multi-block composition (33B2 runs as ASM
  here; its own hook has dedicated oracles at 601/652).

## NOTE: all three failing oracles (BDD0, D434, 33AF) — ALL RESOLVED 2026-06-19
These were NOT three gameplay bugs -- each was a hook/oracle granularity
mismatch (the hook stops at a different sub-step than the oracle stepped the raw
ASM to), with demo-replay green throughout. Resolved per-issue:
- BDD0: hook change -- land on the real 5059 stub + drain it in the child-call
  wrapper (the only one needing production code; demo-replay stays 18/18).
- D434 & 33AF: oracle-convention fixes -- compare at the hook's actual boundary
  (D434 phase-1 exit; 33AF iterated to the 44AA terminator). No production code.
Whole hook oracle suite now green: 244/244.

---

## Remaining playbook backlog -- needs attended judgment (not safe unattended)
The zero-risk, byte-exact autonomous work (raw-offset drain 138->3, object-record
field naming, oracle triage) is exhausted. The rest needs human judgment and is
logged here so the loop neither churns nor risks regressions overnight:

- **Unknown object-record fields `0x10`, `0x26`, `0x36`:** each is written with no
  lifted reader (`0x26` <- DS:237A in object_spawns, `0x36` <- ax in
  object_movement; `0x10` is never accessed). Naming needs the reader lifted first
  -- can't be done honestly now. Map is 25/28, the honest floor.
- **Hotspot lifts (playbook #5):** the interpreted gameplay regions (97C8 frame
  body, ADC9, BBB2, BE3C, B2CD waypoint, ...) run as raw ASM today and are already
  *correct* in both runtimes -- lifting them to Python is pure regression risk with
  no correctness gain, each a substantial reverse-engineer. Best done attended.
- **Death/deactivation frontier (playbook #2):** BFC7/BD17/C054 are "partial/
  observed" lifts; completing their branch tables is the same risk class (see the
  player-death BC4B entry).
- **DS-global naming (future):** 141 distinct magic DS addresses (498 uses) in
  lifted code -- a worthwhile cross-cutting cleanup, but only a handful are clearly
  evidenced (0x98BE input buttons, 0x2380 camera-Y, + those already named in
  world_adapter/game_snapshot_adapter); most roles are unclear. Needs a naming
  convention + per-global evidence -- a design call for the user, like
  OBJECT_RECORD_FIELDS was.
