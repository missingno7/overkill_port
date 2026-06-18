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
