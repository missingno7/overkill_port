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

## Mothership camera-Y divergence (demos: `mothership_drag_edge_case`, `..._L6_mothership_end`)
- Frame-verify: `globals.camera_or_view_y_2380` +1 in the hooked runtime, dragging
  several effect objects' `y_word` +1. (`mothership_drag_edge_case` fails
  demo-replay at the mothership point.)
- `DS:2380` is written only by still-interpreted ASM (no lifted writer), so a
  lifted hook in the `9B2E` frame-controller subtree is feeding that ASM a
  slightly-off input in the reduced-sidearm case. The separate `9FAF` trail bug
  there is already fixed; this camera-Y one is independent.
- **Next step:** bisect the `9B2E` children on the drag demo to find the first
  lifted hook whose output perturbs the `2380` input.

## `menu_interaction` demo divergence (demo: `demo_play_tandy_menu_interaction`)
- Fails demo-replay (pre-existing, confirmed at baseline). The menu is ~44%
  interpreted (`1F8F:0980` loop); the divergence is a lifted hook in the menu/input
  path, not the interpreted core (both runtimes share that). Not yet bisected — the
  field/object that diverges still needs to be captured with frame-verify.

## BDD0 player-hazard-scan hit-path oracle (`bdd0_..._hit_path`)
- Pre-existing FAILING oracle (red at loop baseline): on a hazard hit the hook
  ends at the caller (`CAFE`) but the original is at `1010:5059`.
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

## D434 selector input-release-wait oracle (`d434_..._poll_gate`)
- Pre-existing FAILING oracle. Only FLAGS differ (asm `0202` vs hook `0297`) in
  the cases where `[98E4]==0`.
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

## 33AF expand-tandy-list oracle (`expand_tandy_list_33af`)
- Pre-existing FAILING oracle: hook IP `44AA` vs asm IP `33B2`.
- **Root cause:** `33AF: CALL 44D7; 33B2: JNE 33B7; 33B4: JMP 44AA`. The oracle
  steps the raw ASM only to `33B2` (just after the 44D7 call returns, before the
  branch), but the hook models 33AF *through* the branch and lands on `44AA`.
- Same collapse-vs-step granularity class.

## NOTE: all three failing oracles (BDD0, D434, 33AF) share one root
These are NOT three separate gameplay bugs -- each is a "the replacement hook
collapses more instructions than the single-step oracle advances the raw ASM," so
they disagree on the intermediate IP/FLAGS even though the full-run end state is
correct (demo-replay passes for all three hooks). Fixing them is a *test-harness
convention* decision (compare at hook-boundary end states, or make each hook stop
at the exact ASM sub-step the oracle expects), best made by a human -- attempting
per-hook IP edits regresses the live runtime (proven with the BDD0 attempt).

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
