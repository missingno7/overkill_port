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
