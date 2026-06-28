## 2026-06-28 - Recovery: B9F0 target-X wrap extracted to a recovered rule

B9F0 (the EFAE-selected hot follower) wraps its accumulated target X back to the left
edge (``20h``) once it passes the right edge (``> D0h``).  Extracted that as the pure
`b9f0_wrapped_target_x(target_x)` rule + named `B9F0_TARGET_X_WRAP_LIMIT`/`_RESET`; the
adapter delegates the wrap (keeping the CMP flag replay, dead by the next boundary) with
the exact original write condition.  Byte-preserving; lint + the guard + a new unit test
pass, and the bounded demo corpus stays byte-exact.  Worklist: 8/17 object behaviors now
delegate to a recovered rule.  B9F0's larger reached-target / movement-helper branches
remain bounded original calls -- their ax/flag side effects keep them adapter-side.

## 2026-06-28 - Recovery: ABCA frame-phase gate reuses level_disable_threshold_reached

ABCA (the sprite==0Fh collision body, reached from AD04) gated its motion/tile-probe vs
deactivate path on ``DS:2384 < 0003h`` -- the exact inverse of the verified
`level_disable_threshold_reached` rule (``>= 0003h``) that AB10/ABA3/AB77 already use for
the same frame-phase disable threshold.  Made ABCA's gate delegate to it (keeping the
``LEVEL_PHASE_DISABLE_THRESHOLD`` CMP for flag fidelity, though those flags are dead).
Byte-preserving; lint + the undefined-name guard pass and the bounded demo corpus stays
byte-exact.  Worklist: 7/17 object behaviors now delegate to a recovered rule.  The rest
of ABCA stays bounded original calls (AB34/AC28/AC81/AB99/837A/859E) + the
finish_deactivate slot reset -- the next ABCA increment is naming that deactivation-reset
slot state (logic_id=1, hazard_class=4, latch=0, sprite=0).

## 2026-06-28 - Recovery (consolidation): share the near-camera/render-mode gate across A8C7 + AD04

The A8C7 layer-1 scan and the AD04 logic branch both gate on the same global render state
-- DS:BDAC (full-render mode) and DS:2350 (camera near the left edge, ``<= B6h``).  Slice
a8c7 named those ``LAYER1_*``, but they are not layer-1-specific.  Renamed them to the
global ``RENDER_MODE_FULL`` / ``CAMERA_NEAR_THRESHOLD``, extracted the shared
`camera_near_outside_full_render(render_mode, camera_x)` pure predicate (now used by
`layer1_scan_should_draw`), and named AD04's magic numbers in its adapter
(``AD04_SPRITE_COLLISION_STATE = 0Fh`` plus the shared two).  Byte-preserving -- the named
constants keep their values.  Verified: the a8c7 per-hook oracle (byte-exact) + a new
`camera_near_outside_full_render` unit test + the renamed layer1 test + lint (183) + the
undefined-name guard; AD04 (no fast oracle) exercised via a bounded demo-replay.

## 2026-06-28 - Hygiene: collapse blank-line cruft across object_runtime.py + 3 others

Extends the earlier hooks.py blank pass to the rest of the package's removal cruft:
`object_runtime.py` carried a 53-line void (among others), plus minor runs in
`hook_wrappers/sounds.py`, `gameplay/objects.py`, `asm.py`.  Collapsed every run of 3+
blank lines to 2: -185 blank lines (172 from object_runtime.py).  Pure whitespace -- the
diff touches no non-blank line; lint (183) + the undefined-name guard + the 280-test
hooks/semantics suites stay green.

## 2026-06-28 - Guard: add an import*-aware undefined-name (F821) check to the suite

Promoted the one-off scan that found the 375b NameError into a permanent guard,
`scripts/check_undefined_names.py`, enforced by `tests/test_no_undefined_names.py`.  It
walks every function with full per-scope binding (params, locals,
for/with/except/comprehension targets, nested-def names, global/nonlocal, enclosing
closures, module globals, builtins) and resolves ``from X import *`` by importing X for
its real exports -- several modules build ``__all__`` dynamically (e.g.
``runtime_signatures`` does ``[n for n in globals() if n.startswith("_SIG_")]``), so a
static parse won't do.  Zero false positives on the tree; the test also self-proves the
guard fires on a synthetic undefined name and stays quiet on a bound local.  This closes
the lint gap that let both efae's undefined ``slot`` and 375b's unimported helper ship.

## 2026-06-28 - Correctness: fix a NameError in postcopy_scaled_blit_375b (missing _inc import)

A conservative per-function undefined-name scan -- written because `scripts/lint.py` has
no F821-style check (which is how the dead efae predictor's undefined `slot` slipped
through) -- surfaced a *live* bug among 117 wildcard-import false positives:
`rendering/tandy.postcopy_scaled_blit_375b` calls `_inc_reg16_preserve_cf(cpu, 1)`
(``INC CX`` around the scale multiply) but tandy.py never imported it, so the
``cs:[5905] != 0`` scale branch raised `NameError` whenever it executed.  375b has no
per-hook oracle, so nothing caught it.  Added `_inc_reg16_preserve_cf` to the `..asm`
import and dropped the now-redundant local `_dec_reg16_preserve_cf` def (byte-identical
to asm's).  The fix is byte-exact-by-construction -- `_inc_reg16_preserve_cf` *is* the
interpreter's INC-reg-preserve-CF primitive.  Verified: scanner clear + lint (182) + the
full 239-test per-hook oracle suite (no regression from dropping the local duplicate).
375b still lacks a dedicated oracle (pre-existing gap, flagged for future coverage).

## 2026-06-28 - Hygiene/correctness: remove the dead dispatch-target predictor cluster

`object_runtime.py` carried five `_*_dispatch_target_*` / `_*_target_*` predictors
(5a92 present / 5ac8 draw / 7596 layer-draw / aa2b object-logic / efae object-family),
each meant to predict where a dispatch jump-table lands -- but none were ever called.
All five were imported-unused in `hooks.py`, and the efae one was outright broken: it
referenced an undefined name `slot` (instant `NameError` if invoked), ignored its `bp`
argument, and its docstring (``SS:[BP+18]``) contradicted its body
(``cs:[EFC4 + logic_id*2]``).  They were dead parallels of the *live* dispatch hooks
(`_run_object_logic_dispatch_aa2b`, `_run_object_family_dispatch_efae`, ...) that
actually route.  Removed all five defs plus a 41-line blank gap (83 lines out of
object_runtime.py) and the five dead imports.  The table math survives in the live
dispatch hooks and the commit message.  Verified: lint (182) + audit + import + the full
239-test per-hook oracle suite (the live 5a92/aa2b/efae dispatch hooks stay byte-exact).

## 2026-06-28 - Recovery (dual-mode): extract the A8C7 layer-1 draw predicate to recovered/

The 1010:A8C7 layer-1 scan's `should_call()` decision -- inactive-slot skip, the
out-of-full-render-mode near-camera (``<= B6h``) near-layer suppression, and the
foreground-layer draw test -- is now the pure, named, unit-tested
`recovered.systems.objects.layer1_scan_should_draw` (constants `LAYER1_RENDER_MODE_FULL`,
`LAYER1_CAMERA_NEAR_THRESHOLD = B6h`, `LAYER1_LAYER_FOREGROUND`).  The hooks.py adapter
still reads the slot/global words on the original branches and replays each branch's CMP
flags (live at the A8F1/A8F7 boundary), then delegates the draw decision to the rule.
Byte-exact: the `a8c7` per-hook oracle plus the new
`test_recovered_layer1_scan_should_draw_is_pure_and_named` semantics test pass, with lint
(182) + audit.

## 2026-06-28 - Hygiene: collapse blank-line cruft left by the hook relocations

The masked-compositor / blit relocations (plus the earlier menu-hook removals) left ~20
multi-line blank voids in `hooks.py` (runs up to 61 lines).  Normalized every run of 3+
consecutive blank lines to 2 (PEP8 spacing between top-level defs): 374 blank lines
removed, 3706 -> 3332.  Pure whitespace -- the git diff touches no non-blank line, and
the full 239-test per-hook oracle suite stays byte-exact (33s) so no docstring/string
content shifted.

## 2026-06-28 - Coastline (Phase 1b): relocate the 497A scaled column blit to ega.py

Moved the renderer-dispatch scaled column blit/clear at 1010:497A -- the largest of the
compositor family (95-line body; reached from the 58EC dispatcher via the CS:95BC
function-pointer table, scaling rows DS:SI -> ES:DI planar by the
CS:58FD/5901/5903/5905 accumulator) -- out of `hooks.py` into
`rendering/ega.run_ega_blit_scaled_column_block_497a`.  Clean relocation: ega.py
already imports every asm helper and flag the body uses, so no import churn there.  Body
moved programmatically (verbatim) rather than hand-transcribed to eliminate transcription
risk.  Byte-exact: the per-hook oracle `test_blit_scaled_column_block_497a` passes, plus
lint (182) + audit; `hook_inventory.md` regenerated.

## 2026-06-28 - Coastline (Phase 1b): relocate the 41A6 variable-width interlaced blit to tandy.py

Moved the hot variable-width interlaced row blit at 1010:41A6 -- the same interlaced-
addressing family as 447B but with a variable row width (``REP MOVSB`` BP bytes/row,
then the ``+2000h`` / ``test 4000h`` / ``+C050h`` bank wrap) -- out of `hooks.py` into
`rendering/tandy.run_variable_width_interlaced_blit_41a6`, leaving a thin wrapper
(`_rep_movsb` added to tandy.py's asm imports).  Byte-exact: the per-hook oracle
`test_variable_width_interlaced_blit_41a6` passes, plus lint (182) + audit;
`hook_inventory.md` regenerated.

## 2026-06-28 - Coastline (Phase 1b): relocate the 447B frame-present blit to rendering/tandy.py

Moved the mode-0 frame-present blit at 1010:447B -- the single hottest present routine
once the main loop runs (copies the decoded work buffer CS:[9598] to video
CS:[95A4]=B800 in 192 interlaced rows, with the per-row +2000h/test-4000h/+C050h bank
wrap) -- out of `hooks.py` into `rendering/tandy.run_present_frame_blit_447b`, leaving
a thin `@registry.replace` wrapper.  The shared asm helpers (`_rep_movsw`/`_sub_reg16`/
`_add_reg16`/`_test_word`/`_dec_reg16_preserve_cf`) are imported into tandy.py.
Byte-exact: the per-hook oracle `test_present_frame_blit_447b` passes, plus lint (182)
+ audit; `hook_inventory.md` regenerated.

## 2026-06-28 - Coastline (Phase 1b): new rendering/cga.py -- relocate the 3E12/3EFB CGA compositors

Established `rendering/cga.py` (the CGA byte-level masked-compositor backend, parallel
to `ega.py`/`tandy.py`) and relocated the whole 3E12 (two-shift) + 3EFB (six-shift)
family out of `hooks.py`: both `run_masked_cga_composite_3e12`/`_3efb` bodies plus
their shared pure `_rcr_stc_chain_5bytes`/`_shr_rcr_chain_5bytes` 5-byte shift-chain
helpers.  The thin `@registry.replace` wrappers stay in `hooks.py` (3EFB keeps its
overlay signature guard).  Byte-exact: both per-hook oracles
(`test_masked_sprite_composite_3e12`/`_3efb`) pass, plus lint (182) + audit;
`hook_inventory.md` regenerated.  `hooks.py` sheds ~160 lines of render logic into the
backend module.  Phase-1b masked-compositor family (2E6E/2F81/38B7/3849/3E12/3EFB) now
fully out of the hook layer.

## 2026-06-28 - Coastline (Phase 1b): relocate 38B7 + dedup the immediate-add masked compositors

Relocated the 2-column masked sprite compositor at 1010:38B7 out of `hooks.py` and
folded it together with 3849 into one shared
`rendering/tandy.run_masked_sprite_composite_immediate(cpu, *, words_per_row, row_add)`.
Both are the immediate-row-add siblings of the 2E6E/2F81 family (``ADD DI,imm`` leaves
BX untouched, so they cannot use `_masked_word_composite_rows`): 38B7 = (2, 0x30),
3849 = (4, 0x2C).  Byte-exact -- both per-hook oracles
(`test_masked_sprite_composite_38b7`/`_3849`) pass, plus lint + audit;
`hook_inventory.md` regenerated.  `hooks.py` sheds ~58 more lines; one leaf, two
adapters.  Next Phase-1b siblings: 3E12 / 3EFB / 447B.

## 2026-06-28 - Coastline (Phase 1b): relocate the 3849 masked sprite compositor to rendering/tandy.py

Moved the inline 4-column masked sprite composite loop at 1010:3849 out of `hooks.py`
into `rendering/tandy.run_masked_sprite_composite_3849`, leaving a thin
`@registry.replace` wrapper.  Byte-exact -- the body is unchanged; it uses an
*immediate* row add `0x2C` (leaving BX untouched), so unlike the 2E6E/2F81 family it
cannot reuse the `_masked_word_composite_rows` helper and stays standalone.  Verified
by the deterministic per-hook oracle `test_masked_sprite_composite_3849` (+ lint,
audit); `hook_inventory.md` regenerated.  A direct coastline win: `hooks.py` sheds
~38 lines of render logic into the backend module where it belongs.  Next Phase-1b
siblings: 38B7 / 3E12 / 3EFB / 447B.

## 2026-06-28 - Source-purity rescue: B250 contact fan-out count to a pure formula

Pushed the B250 overlap/contact selector's difficulty-scaled fan-out count down to
a pure rule.  The CX loop count (number of 9E19 post-contact iterations) -- 1 for
most objects, but 1/3/5 for logic_id-3 objects scaling with the contact fan-out
selector DS:BEDC (the difficulty counter) -- moved from
`gameplay/contact_overlap.run_overlap_contact_selector_b250` into
`recovered/systems/objects.contact_fanout_count`.  The adapter now sets CX from the
rule and replays the original CMP flag side effects unchanged (the selector
deliberately preserves AX/BX/CX/flags), so the change is byte-exact by construction.
The contact selector is exercised by the corpus.  Gated green: lint (181), audit,
the new pure unit test `test_recovered_contact_fanout_count_is_pure_and_named`,
demo-replay 23/23.  Begins pushing ContactSystem logic toward `recovered/systems`.

## 2026-06-28 - Source-purity rescue: shared level-disable gate (AB10/ABA3/AB77)

Consolidated the `[2384] >= 3` "level frame phase has reached the disable threshold"
gate that AB10 (deactivate), ABA3 (-> ABC0) and AB77 (-> AB8F) each duplicated into
one shared pure leaf `recovered/systems/objects.level_disable_threshold_reached(value)`
(+ `LEVEL_PHASE_DISABLE_THRESHOLD`), replacing the per-behavior
`AB10_PHASE_DISABLE_THRESHOLD` and `ABA3_PHASE_THRESHOLD` constants.  `object_logic_ab10`
and `object_logic_aba3` now call it; the AB77 shared-tail driver's gate adopts it too
(AB77's only behavior-specific logic was this gate -- the rest is AB4F/AC28/AC81
orchestration with exact IP continuations, so AB77 now counts recovered).  Byte-exact
by construction (same 0x0003 threshold, same `>=` check, unchanged CMP flag replays).
AB10 is heavily exercised (1250 calls in L2_full) so demo-replay verifies the shared
leaf directly; ABA3/AB77 are cold.  This is the "one recovered leaf, many adapters"
pattern.  Gated green: lint (181), audit_architecture, pure unit tests, demo-replay
23/23.  Worklist: 6 DONE (`b73e`/`b86d`/`ab10`/`ae09`/`aba3`/`ab77`), 11 TODO.

## 2026-06-28 - Source-purity rescue: ABA3 tracked-object follower gate+formula to a pure rule

Continued the `object_behaviors` coastline. Slice: the 1010:ABA3 tracked-object
follower probe (reached from AD04 when the slot matches a global tracked-object
pointer). The two pure pieces -- the phase gate (branch to ABC0 once the level
frame phase DS:2384 has advanced to `0003h`) and the sprite formula
(`sprite = scroll frame DS:233C + 14h`) -- moved into
`recovered/systems/objects.object_logic_aba3` (+ `Aba3Update` domain record, named
`ABA3_PHASE_THRESHOLD`/`ABA3_SPRITE_OFFSET`).  The adapter keeps the A42E
tracker-pointer store, the gate CMP flag replay (boundary fidelity) and the AC81
CF/IP collision continuations unchanged, so the slice changes no VM op -- byte-exact
by construction.  (ABA3 is a cold path in the corpus -- the gameplay demos do not
spawn its tracked-object follower -- so it is deliberately a no-op-change refactor,
not a flag drop.)  Gated green: lint (181), audit_architecture, the new pure unit
test `test_recovered_aba3_object_logic_is_pure_and_named`, demo-replay 23/23.
Worklist: 5 DONE (`b73e`/`b86d`/`ab10`/`ae09`/`aba3`), 12 TODO.  Next: `aed8`/`ab77`.

## 2026-06-28 - Source-purity rescue: AE09 object behavior pushed to a pure rule

Continued the `object_behaviors` -> ObjectSystem coastline. Slice: the 1010:AE09
EFAE logic_id 0Ch behavior body. The gameplay decision (a countdown timer in slot
`substate` decrements while non-zero, clearing `direction_or_step` on the frame it
reaches zero; the object steps left `x -= 2` on the frame the timer is zero or has
just expired; outgoing sprite = `direction_or_step + 28h`) moved out of the lifted
adapter into the pure VM-free rule `recovered/systems/objects.object_logic_ae09`
(+ `Ae09Update` domain record, named `AE09_SPRITE_OFFSET`). The lifted
`_run_object_behavior_ae09` is now a thin adapter: `ObjectSlotView` reads -> rule
-> slot writes (substate/direction/x/sprite) -> the already-lifted AF22 + AD60
tail. Every CMP/DEC/SUB/ADD flag of the body is dead at the AF22 boundary (AF22's
first ops overwrite them; the disasm and the prior lift that already dropped the
ADD flags both confirm it), so the adapter needs no flag replay. Gated green: lint
(181), audit_architecture, the new pure unit test
`test_recovered_ae09_object_logic_is_pure_and_named`, demo-replay 23/23 bounded,
and an extended L2_full verify exercising AE09 48x byte-exact. Worklist: 4 DONE
(`b73e`/`b86d`/`ab10`/`ae09`), 13 TODO. Next: `aed8`/`aba3`/`ab77`.

## 2026-06-28 - Faithful level-select replay (menu hooks removed + per-poll demo input)

Full-arc demos that cross the level/difficulty-select screen now replay it
faithfully (previously they deadlocked there, then once unblocked they landed on
the wrong planet). The screen samples the keyboard sub-frame through stateful
debounce loops, but demo input was applied at frame granularity, so same-boundary
release+repress pairs collapsed into one tap. Two coupled changes:

- Removed the approximate level-select replacement hooks (1010:D390 fire-release,
  D434 input-release, D445 selector loop) so the original selector runs as raw ASM
  on every runtime; `overkill.input_waits` already resolves the boundary-less spins
  for both the headless verifier and play.py. Net -431 lines (the hooks + their
  `input_menu` lift bodies + 5 per-hook oracle tests + 3 `HookStop` entries; also
  dropped the now-dead `play.py` `is_input_selector_wait`). `hook_inventory.md`
  333 hooks (was 336).
- `overkill.input_waits.pump_demo_frame` schedules demo input by recorded boundary
  (preserving timing) but, on the level-select screen, delivers one event per
  keyboard poll and defers at present/render boundaries so each release is consumed
  before the next press. Used by the demo-replay test and all three play.py demo
  paths; a coarse-burst selector-head scan keeps detection robust under play.py's
  `cpu.run` chunks.

Verified: menu-only demo `004406` full-verifies byte-exact in the dual-runtime
verifier; intro-start demo `231013` navigates to the same planet/difficulty it
recorded; corpus 23/23 bounded; lint/audit/island-drift green. Commits a11a26c +
this cleanup. (Interactive menu *pacing* runs faster than the recording because the
older demos were recorded against the previous menu cadence — cosmetic; the
verifier is frameless so the goal-run gate is unaffected.)

## 2026-06-27 - Source-purity rescue: AB10 object logic pushed to a pure rule

Resumed the rescue (lifted -> pure recovered systems; hooks thin; VM = oracle;
recovered pieces form the native game). Slice: the 1010:AB10 logic_id=6 per-frame
update. The gameplay decision (deactivate when DS:2384 or DS:A47C >= 3, else
sprite = DS:A40C anim byte + 9 and position = DS:A414 anim pair + DS:237C view
box) moved out of the hook into the pure VM-free rule
`recovered/systems/objects.object_logic_ab10` (+ `Ab10Update` domain record,
named `AB10_PHASE_DISABLE_THRESHOLD`/`AB10_SPRITE_BASE_OFFSET`). The lifted
`_run_object_logic_ab10` is now a thin adapter: DOS reads + XLAT/anim-pair
addressing + the original CMP/ADD flag and register boundary, delegating the logic
to the rule. Gated green: lint (181), audit_architecture, the new pure unit test
`test_recovered_ab10_object_logic_is_pure_and_named`, and demo-replay equivalence
21/21 (byte-exact, 2:45). Next: continue the object_behaviors list (the
gameplay_objects -> ObjectSystem coastline).

## 2026-06-19 - Refactor Phase 2: structured (typed-view) access

Following refactor_plan.md Phase 2. **ObjectSlotView is now fully write-complete**
-- every writable object-record word has a setter. Converting raw
`mem.rw/ww((ss|ds), (bp|bx) + OFF_*)` to `slot.field`, byte-exact, gated per
slice. Converted (fully or the high-value functions): object_postmove, collision,
object_deactivation (BD17/BFC7), contact_overlap (B250), action_spawns, objects
(C3BF/C3F1/C4E5 resets), object_runtime (B1B0 chase, AE2C/AE7D drift),
contact_side_effects (62F6 scan -- the open-coded signed-X test became
`slot.x < 0x20`), object_spawns (8209 seed copy). Flag-affecting helpers,
stack-scratch and DS-global accesses left as-is; single-read dispatch helpers
that already use named offsets left as-is. Each slice: oracle 244/244 +
demo-replay 19/19 + lint.

Remaining Phase 2: object_behaviors (~69 accesses, untouched), the rest of
object_spawns/object_runtime/contact_side_effects (the messier mixed-compute
functions), game_state (partial), and the DS-global reconciliation (below).

NOTE (design call for the user): DS-globals already carry **conflicting names**
across modules for the same address (e.g. 0x2380 = OVERLAP_REF_BOX_Y /
POSTMOVE_CONTACT_Y_GUARD / camera_or_view_y_2380; 0xA47C = TILE_COLLISION_GLOBAL_
GATE / phase_gate_a47c). The DS-global part of Phase 2 is a *reconciliation* into
one canonical name per address, not just naming raw hex -- to be done
deliberately. Remaining typed-view files: object_behaviors, object_spawns,
object_runtime, contact_side_effects, objects, game_state (partial).

## 2026-06-19 - Refactor Phase 1: retire dead-stack scratch (gameplay)

Following docs/overkill/refactor_plan.md. The relaxed boundary-contract oracle
(assert_oracle_equivalent + harness dead-stack ignore, _DEAD_STACK_BYTES=0x40)
lets hooks drop the "write the dead CALL return word below SP" fidelity code.
Retired across three commits: the _remember_balanced_push_scratch helper + its 7
uses; ~13 inline `mem.ww(ss, sp-N, <const>)` writes (object_behaviors,
object_bounds, object_deactivation, object_movement, object_runtime,
object_spawns, hooks) with their dead ss/sp precomputes, the
remember_internal_call helper + vestigial ret_ip params, and stale comments.
~10 oracles switched to assert_oracle_equivalent. Real pushes (live return
words) kept; frame_orchestration's 606F write kept (lands at SP, live). Every
slice gated green: oracle 244/244, demo-replay 18/18, lint. Asset-codec
(rle/packed_stream) dead-stack writes also retired (commit 933e756) -- gated by
the codec oracles + snapshot-loading hooks; the live `saved_cx` CX-restore is
kept (an over-eager first pass removed it; the oracle suite caught it, a good
demonstration that the gates protect the relaxation). **Phase 1 complete.** Next:
Phase 2 (structured access -- typed views, named offsets, named DS-globals).

## 2026-06-19 - Standing divergence-diagnosis tool (scripts/trace.py)

Replaced the per-bug throwaway watchpoint scripts with one reusable dual-runtime
tracer.  `scripts/trace.py` replays a demo through reference (ASM oracle) and
candidate (hooked) in lockstep with a probe on each side:
- `watch SEG:OFF`  -- log writes to an address/range on both sides, report the
  first write whose *value* (not IP -- raw-ASM vs lifted-hook IPs differ
  legitimately) diverges. Re-finds the camera-Y `1010:9C55` extra write.
- `observe CS:IP --reg .. --mem ..` -- dump registers/memory at a CS:IP on both
  sides (found the 9C01 `[a47c]` gate divergence).
- `globals SEG:OFF ..` -- diff arbitrary DS/CS globals each frame, report the
  first diverging frame (a fast bisector; flagged `a360` at f66, two frames
  before the verifier's own f68 detection).
Validated by temporarily reverting the camera-Y fix: the tool pinpointed it.
Retired the unreferenced one-off `scripts/_debug_5c74_*` / `_debug_ecf2_ah`
debug scripts (six) it supersedes.

## 2026-06-19 - Fix menu_interaction demo (frame-verifier timer-tick wait)

The standing `menu_interaction` demo-replay failure was a reference-side TIMEOUT
at `1010:CBE4`, not a state divergence (all decoded state matched between sides
through frame 88). Root cause: the menu transition's CB3E delay (5x CALL CBD5)
busy-waits on the timer tick `DS:[54]`, which the frame verifier never advances
because it models time via the 0679/50C9 boundaries and never fires the async
INT 1Ch ISR (`06E5`) that does `inc [54]`. So `[54]` stayed 0 and the oracle
spun. Interactive play fires the ISR, so the live menu was fine. Fix: added
`input_waits.advance_frame_tick_wait`, a verifier-only per-step resolver that
ticks `DS:[54]` when a side is parked in the CBD5 busy-wait (signature-guarded,
only when spinning), letting the delay drain in lockstep on both sides. Whole
demo-replay suite now green (18/18, 0 failures). See loop_blockers.md (RESOLVED).

## 2026-06-19 - Fix mothership camera-Y divergence (9C01 [a47c]==0 guard)

Attended bisection of the standing `mothership_drag_edge_case` demo-replay
failure (camera anchor `DS:2380` +1 at the mothership). Traced via a `2380`
write-watchpoint -> the hook ran `9C01` (camera step) on frames the ASM skipped.
The `9B2E` lift (`frame_orchestration.py`) had dropped the `[a47c]==0` guard on
the `9C01` call: ASM `9BCF jne 9BDF` gates BOTH `9CB6` and `9C01` on `[a47c]==0`,
but the lift gated only `9CB6`, leaving `9C01` gated by `[2350]>0xB6` alone. After
the mothership trigger (`A66F`) sets `[a47c]=1` (scroll lock), the hook kept
stepping the camera. Fix: nest the `[2350]` gate + `9C01` under `if [a47c]==0`.
Demo-replay: 2 failures -> 1 (`menu_interaction` remains); 17/18 green. Added
`phase_gate_a47c`/`level_progress_2350` to the semantic snapshot. Frame-controller
oracles + recovered-semantics still green. See loop_blockers.md (RESOLVED entry).

## 2026-06-19 - Loop slice: oracle-suite scan; remove a missing-data test

Ran the full hook oracle suite to find pre-existing failures now that raw-drains
are done. 4 failed / 241 passed. Triage:
- `b00d_..._direction_table`: bound to `artifacts/repros/demo_divergence_tandy_
  20260616_160515` which is gitignored/gone -> REMOVED the test (same as the
  earlier b1b0 cleanup; the B00D hook stays covered by demo replay). 244 collect.
- `bdd0_..._hit_path`: already logged in loop_blockers.md (jmp-5059 granularity).
- `d434_..._poll_gate`: only FLAGS differ (hook 0202 vs asm 0297) -> a flags-
  replication gap; queued.
- `expand_tandy_list_33af`: control-flow divergence (hook 44AA vs asm 33B2);
  queued.

## 2026-06-19 - Loop slice: final raw-offset sweep (raw-drain complete)

Byte-exact: 10 `bp` (SS:BP object-slot) accesses across 4 files -> named OFF_*.
collision.py (X/Y in the AC81 scan setup), game_state.py (Y in the A60A/A5FC
one-pass Y-step helpers), object_deactivation.py (ACTIVE_WORD, PREVIOUS_LOGIC_ID),
object_runtime.py (ACQUIRED_TARGET_PTR in the B1B0 chase). Dashboard: record
offset accesses 13 -> 3 raw (4% -> 1%).

The raw-drain is now at its floor: the only remaining "raw" hits are the two
genuinely-unnamed words (object_spawns 0x26, object_movement 0x36 - both written
with no lifted reader, so they stay honest unknowns) and a register-arithmetic
false positive (`si = si + 0x0006`). Total drained this run: 138 -> 3 (40% -> 1%).

Verified: fresh imports (all 4 files), lint (151), audit (17 pure), the AC81/
Y-step/BD17/C054/B1B0 oracles, demo-replay (only the logged divergences fail).

## 2026-06-19 - Loop slice: drain contact_side_effects.py raw offsets

Byte-exact raw-offset drain: 22 object-record accesses in contact_side_effects.py
-> named OFF_* constants. `bp` (current slot): COUNTER_20 (x12 in the contact
counter-decrement paths), GATE_OR_LAYER, VARIANT. `bx` (scanned/owner slot in the
contact scan): X / Y / SPRITE_OR_STATE / LOGIC_ID / SUBSTATE / SCAN_ENABLE_OR_SOLID
/ ACQUIRED_TARGET_PTR. The flag-bound bx-walk loop control is untouched; only the
field-access offsets are named. Dashboard: record offset accesses 35 -> 13 raw
(10% -> 4%).

Verified: fresh import, lint (151), audit (17 pure), the bec5/bedc/aa71 contact
oracles (22 pass), demo-replay (only the 2 logged divergences fail; no regression).

DISCOVERED a pre-existing failing oracle while running the contact suite:
`test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_hit_path`. The BDD0
hook returns to the caller (`CAFE`) on the hit path, but the original continues to
`1010:5059`. Confirmed failing at baseline with this drain stashed, so it is NOT
caused by this byte-exact rename (a control-flow difference can't come from an
offset-constant swap). Queued as the next fix slice.

## 2026-06-19 - Loop slice: drain objects.py raw offsets

Byte-exact raw-offset drain: 22 `bp` (SS:BP object-slot) accesses in objects.py's
slot-init/reset loops and the AB4F scroll-sprite helper -> named OFF_* constants
(ACTIVE_WORD / X / Y / DIRECTION_OR_STEP / SPRITE_OR_STATE / GATE_OR_LAYER /
LINK_KEY / HAZARD_CLASS / LOGIC_ID / VARIANT). Dashboard: record offset accesses
57 -> 35 raw (17% -> 10%). The `s.bx +` source reads were left raw (separate
struct, role less certain). Verified: fresh import, lint (151), audit (17 pure),
objects oracles (aa2b/ab4f/...), demo-replay (no new failures; the 2 pre-existing
mothership/menu divergences are logged in loop_blockers.md).

Also: installed capstone and logged loop_blockers.md - disassembled the BFC7
player-death tail and proved its C037 jump-table dispatch is correctly lifted, so
that divergence is elsewhere in BC4B's path (logged for a reproduction trace).

## 2026-06-19 - Loop slice: drain action_spawns.py raw offsets

Byte-exact raw-offset drain: the 6 `bx` slot-stamp accesses in action_spawns.py's
action-spawn tail -> named OFF_* constants (SCAN_FLAG / HAZARD_CLASS / LOGIC_ID /
SUBSTATE / SCAN_ENABLE_OR_SOLID / ACQUIRED_TARGET_PTR). Dashboard: record offset
accesses 63 -> 57 raw (19% -> 17%).

Verified: fresh import, lint (151), recovered-layer audit (17 pure), the
a067/a515/a584 action-spawn oracles, demo-replay (16 pass). The 2 demo failures
(menu_interaction, mothership_drag_edge_case) are pre-existing open divergences -
confirmed by a stash-baseline check that they fail without this change - NOT a
regression from this byte-exact rename. Both go on the open-divergence list.

## 2026-06-18 - Name 4 object-record fields, drain raw offsets, fix the 9FAF sidearm-drag bug

Map-driven slices (the dashboard surfaced unnamed-but-used words; a quick trace
named them), then byte-exact raw-offset drains, then a real edge-case bug fix.

Field discovery (object record now 25/28 mapped: 10 known, 15 guessed, 3 unknown):
- 0x2E -> `move_step_error` (Bresenham movement step accumulator; known).
- 0x2A/0x2C -> `move_delta_x`/`move_delta_y` (signed object-minus-target deltas;
  known) - the 5E1B delta helper computes them, the 5E42 steer consumes them.
- 0x28 -> `linked_counter_index` (guessed): index x16 into the DS:2078 linked-
  counter table (FFFF = unlinked).  Cross-layer rename that removed the `field_28`
  placeholder from the pure domain/system and deleted a duplicate offset constant.
- Each adds a view getter (consumed by a real read), a map row, and a test row.
  The 3 remaining unknowns (0x10/0x26/0x36) lack a lifted reader, so they stay
  honestly `unknown` rather than guessed.

Raw-offset drain (byte-exact, scoped per register to confirmed object records):
- object_spawns.py: 41 `bx`/`si` slot accesses -> named OFF_* constants.
- object_movement.py: 18 `bx`/`s.bp` accesses -> named.
- Left untouched: `bp` caller-frame reads (different struct), table pointers, and
  the unknown 0x26/0x36.  Dashboard: record offset accesses 138 -> 63 raw
  (40% -> 19%).

BUGFIX - mothership sidearm-drag divergence (1010:9FAF): the lift called the final
9FEA child-coord update unconditionally, but the original guards it
(`CMP BX,FFFF / JNZ / RET`) and skips it when the 4th linked slot is inactive -
i.e. a ship carrying fewer than 4 sidearms/drones.  The extra write corrupted the
DS:A30A coord trail (DI off by one entry).  Added the guard + a regression test
for the `[A966]==FFFF` case the original oracle never covered.

Housekeeping: removed `test_object_player_chase_b1b0_*` (bound to the deleted demo
`demo_play_tandy_20260616_000527`); the live B1B0 hook stays covered by demo
replay.  Committed the new short demos as fixtures (L5/L6/menu/mothership/death).

Known open (separate, pre-existing): mothership camera-Y (`DS:2380`) +1 and a
player-death `BC4B`/`BFC7` death-tail divergence - both edge branches in the
still-partial death/deactivation frontier (BFC7/BD17/C054).

Verified: lint (151) + recovered-layer audit (17 pure) + map tests + the
9FAF/5E1B/5E42/5db2/spawn oracles + all demo replays native==VM (non-mothership).

## 2026-06-18 - Living memory map + collapse the triplicated object-record decode

Two slices, each leaving the live path cleaner (not just adding on top).

Living memory map (visibility):
- `OBJECT_RECORD_FIELDS` in `recovered/views/object_slots.py` now catalogs every
  16-bit word of the 0x38 object record with a discovery status: `known` /
  `guessed` / `unknown`.  The seven previously-silent gaps (0x10, 0x26, 0x28,
  0x2A, 0x2C, 0x2E, 0x36) are explicit `unknown` rows; inferred names are marked
  `guessed` instead of reading as settled fact.  Offsets reference the existing
  `OFF_*` constants (no re-typed numbers).
- `scripts/source_port_status.py` now prints struct coverage and the offset-access
  migration runway: `object_record (0x38): 21/28 words named (7 known, 14
  guessed, 7 unknown)` and `record offset accesses in gameplay/: 203 named, 138
  raw hex (40% still raw)`.  Progress is now a number that moves.
- Checked by two new tests (map covers every word once; agrees with the OFF_*
  constants and the documented gaps).

Hygiene collapse (fewer parallel representations):
- The object-record offset->field mapping lived in three places (view properties,
  `ObjectSlotSnapshot` fields, and the adapter's `w(OFF_*)` hand decode).  The
  adapter now builds the snapshot straight from the live `ObjectSlotView` named
  fields + `record_bytes()`, so the layout lives in ONE place (the view).  The
  adapter dropped ~13 `OFF_*` imports and its private `w()` decoder.
- The snapshot's frame-timer read now goes through `FrameTimersView` too, removing
  a second reproduction of the DS:2368 table layout.
- `contact_overlap.OFF_SUBSTATE_1E` was a re-typed `0x1E`; it now aliases the
  canonical `OFF_SCAN_ENABLE_OR_SOLID` (one source for the number).  The local
  name is kept and the naming ambiguity marked: collapse to one name once
  evidence settles whether "skip-overlap" and "scan-enable/solid" are one role.

Verified byte-identical: lint (151) + recovered-layer audit (17 pure) +
recovered-semantics/checkpoint-handoff (39) + all 8 demo replays native==VM +
the B250 overlap/contact + bounds/61C7 oracle suites.

Housekeeping: removed 6 tests that hard-depended on the now-deleted root snapshot
`artifacts/snapshot_play_tandy_20260614_191454`; made the AdLib bundle test skip
(with a regenerate hint) instead of hard-failing if `artifacts/static_runtime_bundle`
is cleared.  All other test data already lives in curated subfolders.

## 2026-06-18 - VM-backed views translation layer, introduced by use

Built the typed translation layer between the VM and the source-like code, with
each view introduced by a real live consumer (no speculative/dead overlays) and
proven byte/register/flag-exact:

- `recovered/views/object_slots.ObjectSlotView`: extended to full field coverage
  (object_type, draw_layer, row_or_phase, substate, scan_enable_or_solid,
  counter_20, variant, acquired_target_ptr, ...) + a `record_bytes()` record read.
  First live use: `gameplay/object_bounds.py` AD60 bounds tail now reads
  `slot.x_word / y_word / draw_layer / logic_id` instead of raw `mem.rw(ss,bp+OFF)`.
  The flag-affecting `_add_mem_word` pre-add stays as visible ASM glue.
- `recovered/views/object_slots.ObjectTableView`: a live lens over a whole
  effect/gameplay table (indexable/iterable slot views, `.active()`). First live
  use: `game_snapshot_adapter._decode_table` iterates it and reads each slot via
  `record_bytes()` (byte-identical to the old per-byte read).
- `recovered/views/frame_timers.FrameTimersView` (new module): the six `DS:2368`
  countdown counters (read-all / write-one / `address_of` / `end`). First live
  use: the 61C7 frame-timer scan in `gameplay/game_state.py`, which now reads
  `timers.values()` and writes `timers[k]`, keeping the exact DI/flag contract.

The layer rule: a view replaces the *memory access* only; flag/register-exact ASM
(`_add_mem_word`, `set_sub_flags`, scan-loop BX walks) stays in the lifted body.
Documented in ARCHITECTURE.md ("VM-backed views (the translation layer)") and the
`recovered/views/__init__.py` package docstring.

Validation:

```text
python scripts/lint.py                      # 151 files
python scripts/audit_recovered_layers.py    # 17 pure files (views are bridge, not pure)
python -m pytest tests/test_overkill_hooks.py -k "b24d or bounds or ad5a or aed8 or b73e or 61c7 or 61f7 or decrement_counter" -q   # oracle: byte/reg/flag identity
python -m pytest tests/test_recovered_semantics.py tests/test_checkpoint_handoff.py tests/test_demo_replay_equivalence.py -q        # snapshot decode + demo-replay native==VM
```

## 2026-06-18 - Phase 1 lift: B73E target-reached 4-way resolution

Lifted the B73E `B7BD/B808` target-reached dispatch (reached once an object is at
its waypoint and past the optional B800 spawn) into the pure
`b73e_target_reached_resolution(a47e, game_counter, value_232e)`
-> `B73ETargetReachedResolution` (`reset_target_check_2324` / `reset_target_direct`
/ `postmove` / `waypoint_loop`).  `_run_object_behavior_b73e` now classifies once
and asserts agreement while replaying the original CMP order at each branch.

Verified by the six `b73e` oracle tests (full-state + full-memory vs interpreted
ASM), a new pure unit test, and the demo-replay equivalence suite (L1/L2/L3 all
native == VM).  This is the first lift proven by the new whole-game proof spine in
addition to the per-hook oracles.

## 2026-06-18 - Whole-picture map of the remaining interpreted ASM

Used fresh L2 + L3 coverage dumps (95-96% hook-covered) to map every hot
interpreted region by disassembly, so we know exactly how the game is wired and
what is left.  Findings written up in `runtime_findings.md` ("Remaining
interpreted-ASM wiring map").  Summary: the engine spine is native; the remaining
gameplay interpreted is a finite queue of structurally-identical object-behavior
bodies (`8xxx`/`Bxxx`/`Fxxx`, all: animate via XLAT sprite table -> move -> maybe
spawn 7476 -> jmp BC45), plus a few collision tails (`BFC7`/`BE3C`/`BEA4`/`BB03`),
plus the frame-loop spine `97C8` (Phase 6, last), plus the sound driver `2032:*`
(~88% of interpreted - the separate OPL long pole).

Disassembled and classified in `symbols.json` (so coverage stops calling them
"unknown"):
- `1010:97C8 main_frame_loop_body_97c8` - the 97B2 per-frame loop body.
- `1010:BB80 object_behavior_sprite_spawn_bb80` - sprite/animate + 2330==57h
  formation-spawn behavior (hot in both L2 and L3).
- (`1010:B2CD` waypoint behavior was classified in the prior note.)

Also confirmed the `9E19` collapse landed: in L3 the `B297` region dropped from a
hot 9E19 loop to ~9.6k (now classified `gameplay_objects`); the remaining L2
`B297-B32A` mass is the separate `B2CD` waypoint behavior.

No behavior change this pass (disassembly + classification + docs only).

## 2026-06-18 - Guard strengthened: semantic snapshot now covers global counters

The checkpoint-collapse strategy proves correctness by frame/state equivalence, so
the snapshot's coverage IS the correctness guard.  It previously decoded only
frame timers + score + object slots, missing the global counters that drive object
lifecycles - exactly the state class the ringlas bug hid in (DS:A972 diverged but
was invisible to the verifier, so it was only caught downstream once it corrupted
object slots).

Widened `GameSnapshot` with `state_globals` (pure: names + values), decoded by
`game_snapshot_adapter.SNAPSHOT_GLOBAL_WORDS` - reusing `world_adapter`'s
evidence-backed globals (camera, allocator cursors, tile-sweep, boss counter, ...)
plus the gameplay counters/gates: action-spawn/weapon-list counters DS:A970..A978,
DS:A97E, formation counter DS:2340, gates 2330/232E/2356, contact fanout BEDC,
mode flag BDAC.  `diff_game_snapshot` reports `globals.<name>` divergences.

No new infrastructure - it extends the existing snapshot/diff and reuses the
address evidence already in `world_adapter` (no parallel state model).  The
verifier now catches a counter divergence at the source frame instead of waiting
for it to manifest in objects/vram.

Verification:

```text
python -m pytest tests/test_recovered_semantics.py -q   # incl. globals diff + decode tests
python scripts/audit_recovered_layers.py                # domain stays pure (17 files)
python -m pytest tests/test_demo_replay_equivalence.py -q -k "ringlas or showcase or L2 or L5_start"
# 4 passed - candidate and VM agree on the new globals (no hidden divergence; broader guard)
```

## 2026-06-18 - Key finding: the frame is ALREADY a native chain inside 97B2

While making the handoff executable, a `cpu.ip`-visit census over ~250 frames of
L5 gameplay revealed how far the collapse already is: the frame-loop hook `97B2`
("lifted as one verified iteration") **composes the whole frame as native Python**.
Most phase/"checkpoint" addresses are never visited as `cpu.ip` because they run as
direct function calls inside that chain:

```text
97B2  1757x   <- the per-frame resume point that IS visited
A940/AA10  3x each      A90C 3354 A846 5BDC 0162  0x   <- composed away
```

Implications:
- The **frame boundary (`97B2`/`D007`) is the real `cpu.ip`-visited resume point**;
  the sub-phase checkpoints (render/object-update) are already fused inside the
  frame chain.  `taxonomy` checkpoints are *logical* boundaries; only the frame
  ones are current handoff points.  (`scripts/capture_demo_snapshot.py
  --at-checkpoint frame` captures there; sub-phase kinds mostly will not match
  because those addresses are not visited.)
- The demo boundary clock (present/timer at 3354/0679) is itself largely composed
  inside 97B2, so it advances slowly under raw single-runtime replay - which is why
  deep `--min-boundary` captures are slow.  The demo-replay verifier installs the
  boundary hooks explicitly, so it is unaffected.
- Re-scopes "collapse 319 glue hooks": the frame loop is **already** a native
  chain; the remaining glue is the gameplay behaviours/tails that chain still
  bounces into (the object-update phase).  So the next real target is collapsing
  the object-update phase's behaviour dispatch, not re-doing the frame loop.

## 2026-06-18 - Untie: VM-until-checkpoint handoff is now executable

Made the checkpoint model runnable code, not just doctrine:

- `overkill/checkpoints.py`: `run_to_next_checkpoint(cpu, kinds=...)` steps the VM
  (instruction-exact oracle) from any position to the next logical checkpoint
  (frame/render/object-update/input), derived from the evidence-based phase map in
  `hook_taxonomy`.  This is the "run in VM until the first compatible checkpoint,
  then hand off" primitive.
- `tests/test_checkpoint_handoff.py`: proves it - from a gameplay snapshot the VM
  fast-forwards to a frame checkpoint, lands exactly on it, the decoded
  `GameSnapshot` is consistent there, and two consecutive frame checkpoints differ
  by exactly one frame of gameplay (a real boundary, not a mid-chain point).
- `scripts/capture_demo_snapshot.py` gained `--at-checkpoint <kind>`: capture an
  oracle snapshot at a stable, resumable checkpoint instead of an exact mid-chain
  `CS:IP`.  This is the *right* shape for oracle capture and fixes why the BB80
  mid-chain capture kept timing out - capture at the object-update checkpoint
  (which occurs every frame) instead.

Why this unties our hands: a snapshot can now be taken anywhere, fast-forwarded in
the VM to a checkpoint, and resumed by native code; and a collapsed chain between
two checkpoints is verified by semantic frame/state equivalence (the demo-replay
suite), with no obligation to reproduce intermediate `CS:IP`s.  Next: collapse one
whole frame phase (render `A846`->`5BDC`->present is the cleanest, vram-verifiable)
into a single native system between the object-update and render checkpoints.

## 2026-06-18 - Strategy: the frame is already a checkpoint sequence (D007)

Inspected the gameplay main loop `1010:D007` (per user direction) and found the
frame is ALREADY a linear chain of `CALL`/`RET` phase calls, each a stable,
verifiable boundary and each already a registered hook:

```text
D007 frame top -> 0672(env) -> 511F/A846 render -> 5BDC/3354 present[RENDER]
     -> A90C/A940/AA10 [OBJECT-UPDATE] -> 5F61/073C -> 5160/0679 wait(env)
     -> 0162 [INPUT] -> jz D007 [FRAME]
```

So the source-port loop does not need inventing: it is D007's phase sequence, each
phase a native system entered/exited at its checkpoint, with the behaviours/tails/
helpers each phase calls being the glue to fuse inside it.

Updated the strategic documents to make checkpoint-first the project strategy:
- `docs/overkill/semantic_crystallization_plan.md` - new top section
  "Checkpoint-first execution model (read this first)": VM = instruction-exact
  oracle; source port = checkpoint-level; VM-until-checkpoint handoff; "promote
  hooks upward" reframed as "collapse glue between checkpoints into source-like
  systems", proven by frame/state verification.
- `ARCHITECTURE.md` - "Snapshot model" section now carries the D007 frame map and
  the VM-until-checkpoint handoff.
- `AGENTS.md` - hooks are candidates for checkpoints, not permanent patch points;
  the per-hook proof obligation is VM-oracle-side only.
- `overkill/hook_taxonomy.py` refined to the evidence-based D007 phase set
  (12 checkpoints / 5 env-waits / 319 glue), locked by `tests/test_hook_taxonomy.py`.

Implication for VM-until-checkpoint handoff: oracle snapshots no longer need
capture at a behaviour's exact entry - capture anywhere, fast-forward in the VM to
the next checkpoint, resume natively.  (This is why the BB80 mid-chain capture was
the wrong shape; capture at the object-update checkpoint instead.)

## 2026-06-18 - Methodology: checkpoint-level snapshots, hooks classified by role

Adopted an explicit model (per user direction): stop treating every hook address
as a permanent source-port boundary.  The VM/original ASM stays instruction-level
snapshotable as the oracle; the source-port runtime is **checkpoint-level**
snapshotable - it resumes only from stable logical boundaries (frame,
object-update, render, input, plus hardware waits).  Between checkpoints, lifted
code may run as one atomic deterministic chain with no obligation to preserve old
`CS:IP` bounces or mid-chain resume; a mid-chain snapshot defers to the next
checkpoint.  Correctness is protected by the semantic frame/state verifier
(the demo-replay equivalence suite), not by historical hook boundaries.

Implemented:
- `overkill/hook_taxonomy.py` classifies hooks by role: `checkpoint` / `env_wait`
  / `debug_probe` / `glue`.  Curated checkpoint + env-wait sets are small and
  explicit; everything else is `glue` (the honest majority).
- `scripts/source_port_status.py` now reports the split: ~8 checkpoint, ~4
  env_wait, ~324 glue.  The glue count is the collapse target and the headline to
  drive down.
- Documented the model in `ARCHITECTURE.md` ("Snapshot model: checkpoints, not
  hook boundaries"); per-hook `verification.py` metadata stays the VM-side proof
  only.

Reframes the BB80 lift (deferred): instead of reproducing BB80's exact `CS:IP`
bounces (the multi-entry dispatch + the BBED tile-probe's mid-chain returns - the
reason it was awkward), treat BB80 as glue between the object-update checkpoint
and the render checkpoint and collapse it into one atomic source-like chain,
verified by frame/state equivalence over the corpus.

## 2026-06-18 - Demo corpus expanded to 8; full-weapon showcase verified clean

The corpus is now 8 demos (L1-L5 + the all-weapons attract showcase), all passing
the bounded native-vs-VM demo-replay equivalence suite.  The
`demo_play_tandy_showcase_*` attract demo (input-free, cycles every weapon and
ship upgrade) ran the divergence hunt to 4000 frames with **zero divergence** -
the strongest equivalence signal so far, independently confirming the ringlas fix
and that no other weapon has a similar lifecycle/deactivation bug.

```text
python -m pytest tests/test_demo_replay_equivalence.py -q   # 8 bounded passed, 8 full skipped
python scripts/find_demo_divergence.py <showcase demo> 4000  # rc=0, no divergence to frame 4000
```

Open frontier (unchanged): a post-input divergence ~1370 frames past the ringlas
demo's recorded end (score delta + `logic_id 0x3B` effect slot) - not reproduced
by the showcase, so it is a narrow post-demo edge case, not a general weapon bug.

## 2026-06-18 - BUGFIX: ringlas (logic_id 9) deactivation cleared the whole list

User-reported: the ringlas (last weapon) misbehaved in heavy L5 play and the game
crashed (`UnsupportedInstruction` at a mid-instruction address - corrupted control
flow, not a missing opcode).  Root-caused with the demo-replay divergence hunt on
the user's short repro demo (`demo_play_tandy_L5_ringlas_divergence_*`):

- First native-vs-VM divergence at frame 70: ~20 `logic_id 9` objects (the ringlas
  projectile column) that the original deactivates but our hooks kept `active=1`.
  Those stale slots accumulated, corrupted memory, and ~frames later caused a bad
  jump -> crash.
- Traced the original deactivation: object scan -> `EFAE` (logic dispatch) ->
  `ADEF` (`jmp AD60`) -> out-of-bounds -> `BD17`.  `BD17` dispatches on `logic_id`,
  and **`logic_id 9` jumps to `BD7A`**, which clears the WHOLE projectile list
  (the `BD82` loop: walk the FFFF-terminated `DS:A3B4` pointer list, set each
  listed object's `active=0`, drain `DS:A972`).
- Our `_run_deactivate_bd17_observed` mis-modeled `logic_id 9` as a single
  `A972--` decrement (same as its sibling counter ids `7/8/6/5/C`, which really
  ARE single decrements - confirmed via `BDAC/BDB8/BDC4`).  Only `9` is the
  clear-loop.

Fix (`overkill/gameplay/object_deactivation.py`): special-case `logic_id 9` to
replay the `BD7A/BD82` clear loop (deactivate every `DS:A3B4` entry, drain
`DS:A972`) instead of a single decrement.  L1-L4 never hit it because ringlas is
the L5 weapon.

Verification:

```text
python -m pytest tests/test_overkill_hooks.py -q -k "b24d or b86d or aed8 or bd17"   # pass (AD60->BD17 oracle)
python scripts/find_demo_divergence.py <ringlas demo>   # frame-70 divergence gone; clean through the whole recorded demo
python -m pytest tests/test_demo_replay_equivalence.py -q -k ringlas   # passed (now a regression guard)
```

New tooling from the hunt: `scripts/capture_demo_snapshot.py` (capture an oracle
snapshot at any CS:IP during demo replay) and `scripts/find_demo_divergence.py`
(replay a demo native-vs-VM and stop at the first diverging frame/field).

Follow-up (separate, lower priority): ~1370 frames PAST the recorded demo's end
(post-input auto-play) a different divergence appears - a score delta and a
`logic_id 0x3B` effect-slot state difference.  Not the ringlas bug; logged as a
frontier.

## 2026-06-18 - Phase 2 collapse: native 9E19 in the B250 contact loop

Acted on a coverage telemetry dump from a full L2 demo run (94.9% hook-covered,
5.0% interpreted).  Investigated the hottest *gameplay* interpreted region,
`1010:B297-B32A` (145,662 hits, mislabelled "unknown"), via disassembly and found
it is two distinct things:

- `B281-B2A0` is the tail of the already-lifted `B250` overlap/contact selector -
  the `B297` loop that does `PUSH CX/BP; CALL 9E19; LOOP` (up to 5x).  But `9E19`
  was run as **interpreted** ASM via an injected near-call ("verifier-visible
  boundary"), even though a verified native helper
  `run_post_contact_status_helper_9e19` already exists.
- `B2CD` is a *separate* unhooked behavior (see the next note).

Phase-2 collapse: the selector now calls the native `9E19` helper instead of
interpreting it.  `run_overlap_contact_selector_b250` takes a
`post_contact_side_effect(cpu)` callable (was `near_call`); the `_run_b250_overlap_contact_selector`
shim binds it to `run_post_contact_status_helper_9e19` (with `_no_patch_guard`,
since 9E19 is static), pushing `B29C` so the helper's near-ret lands back in the
loop exactly like the original `CALL 9E19`.  The hot `B297` loop is now native.

This was safe to collapse precisely because the demo-replay proof spine exists:
per-hook 9E19 visibility is traded for whole-frame/state equivalence.

Verification:

```text
python -m pytest tests/test_overkill_hooks.py -q -k "aed8 or b24d or 9e19"   # 3 passed (vs interpreted ASM)
python scripts/audit_architecture.py / audit_hook_oracle.py                  # pass
python -m pytest tests/test_demo_replay_equivalence.py -q                    # 3 passed (L1/L2/L3 native == VM)
```

Re-run the user's `play.py --demo ... ` coverage command to see the `9E19`
interpreted hits drop.  (`61DC`/`511F` display children inside 9E19 stay bounded
for now.)

## 2026-06-18 - Structure: hook_boundary purity + source-port status dashboard

Whole-project structure pass (no behavior change).  Two parts:

1. Added `scripts/source_port_status.py` - a read-only dashboard of the ASM->source
   migration.  It reuses the enforced `audit_architecture.layer_of` map and reports
   per-layer line mass + `cpu`/`mem` density, the headline "% of game-logic mass
   that is pure source" (currently ~10%), the pure-rule count (44), registered hook
   count (336), and flags oversized hook_boundary files.  Wired into `ARCHITECTURE.md`
   as the "run this before deciding what to clean next" tool.

2. Started restoring `hook_boundary` purity: the documented rule is that
   `overkill/hooks.py` is thin `@registry.replace` glue with no render logic, but it
   held several large inline Tandy blits.  Moved `1010:477E` (9x16 sprite blit) and
   `1010:41DA` (linear row copy) bodies into `overkill/rendering/tandy.py` behind
   thin wrappers (the EGA renderer's existing pattern).  All the 8086 helpers those
   bodies need are already local to `tandy.py`, so the moves needed no new plumbing.

Effect: `hooks.py` 4244 -> 4117 lines; hook_boundary `cpu`/`mem` refs 913 -> 831.

Verification:

```text
python scripts/lint.py / audit_architecture.py / audit_hook_oracle.py   # all pass
python -m pytest tests/test_overkill_hooks.py -k "477e or 41da" -q      # 2 passed (byte-exact vs ASM)
python -m pytest tests/test_demo_replay_equivalence.py -q               # 3 passed (L1/L2/L3 native == VM)
```

Remaining inline blits in `hooks.py` to move next (same pattern): `497A`, `38B7`,
`3849`, `41A6`, plus `447B`/presence-stamp/dirty-cell presenter.  `497A` also uses
the `SF` flag and a couple of helpers - confirm they're available in `tandy.py`
before moving it.

## 2026-06-18 - State ownership: lift the 1010:8209 object-slot spawn template

First "vertical slice by state ownership" toward live source recreation.  Used the
world-write tracer over the L1 gameplay demo to find, per object/global field, the
exact set of routines that write it and which are already native hooks.  Result:
4 fields are already fully native-owned, and a single un-lifted routine -
`1010:8209` - was the lone remaining ASM writer for ~11 core object-record fields.

Lifted `1010:8209`, the shared object-slot spawn-stamp template (reached from the
`81E9`/`81F4` allocate-then-stamp siblings):

- Pure `recovered.systems.objects.object_spawn_seed_8209(source_x, source_y)` ->
  `ObjectSpawnSeed` (domain record): an active `logic_id=0014h` object at the
  caller's source X/Y, position+target both set to the source, with the constant
  fields (direction=4, hazard=4, scan=1, gate=1, counter_20=4, variant=0) and the
  unnamed `+0x28` field cleared to `FFFFh`.
- Hook `overkill_object_spawn_seed_8209` (`gameplay/object_spawns.py` +
  `hook_wrappers/object_runtime_frontiers.py`) owns the DOS slot pointer (BX) and
  write order, leaves `AX` = source Y, and near-returns; guarded by a byte
  signature like the other spawn templates.

Verification:

```text
python -m pytest tests/test_overkill_hooks.py::test_object_spawn_seed_8209_matches_interpreted_asm -q
# 1 passed (byte-exact vs interpreted ASM, full memory + state)

python scripts/audit_hook_oracle.py   # 336 hooks / 336 metadata
python scripts/audit_recovered_layers.py / lint.py   # 17 pure files / 145 files

python -m pytest tests/test_demo_replay_equivalence.py -q
# 3 passed (L1/L2/L3 native == VM with the 8209 hook live)
```

Confirmed live: the hook fired 16 times during the L1 wave with whole-game
equivalence holding, so the spawn template is genuinely running native source in
the live game, not a dead hook.  Those ~11 object fields now have their spawn-path
writer in native Python - measurable progress toward a native object model.

Method note (reusable): "live source" progress is now tracked by the world-write
tracer (`scripts/trace_world_writes.py`) - a field becomes recreated source once
every routine that writes it is a native hook.  Next ownership targets from the
same map: the `1F8F:038E..03A0` overlay spawn/init cluster (writes target_x/y,
logic_id, substate, a47e) and `1010:5033` (camera_or_view globals).

## 2026-06-18 - Demo corpus: L1 enemy-wave -> level-start transition

Added `demo_play_tandy_L1_start_20260618_143947` (sound=adlib, 140 events,
`end_boundary=870`): the level-1 enemy-wave intro playing through into the start
of the actual level phase.  Auto-discovered by `tests/test_demo_replay_equivalence.py`.

Equivalence holds across the whole transition: native (hooked) == VM oracle on
framebuffer + RGB + semantic state for all 870 frames (full run ~38s), and the
bounded CI prefix (150 frames) already covers the wave->level boundary at ~frame 138.

Transition evidence (candidate-runtime DS scan over the demo, step-function words
= state that changes once and settles): the enemy-wave is a consumed table in
roughly `DS:2404..24EC` (record stride ~18h, entries `0020h->0001h`/`0004h->0000h`
draining across frames 74..140); several globals settle at the wave->level
boundary near frame 138 (`DS:2308 0003h->0002h`, the `DS:2376/2378/2379` spawn
publish, `DS:240C`), with a later sub-event at frame 316 (`DS:230C/230E 0->1`).
These are candidate-only; none is yet a proven, named "level phase" global.

Two coverage gaps this demo exposes (the proof is not yet total here):
- The semantic `GameSnapshot` does **not** model wave/level-phase state, so for
  this transition the semantic half currently leans on the vram+RGB comparison.
  Widening it needs RE to interpret the step-words above into a named global.
- **Audio is not verified at all.**  The "different music" at the transition rides
  on the AdLib/OPL register stream, which the frame verifier does not compare; a
  music-only divergence would pass today unless it perturbs snapshot/vram state.
  This is the plan's known longest pole (exact audio == matching the OPL stream).

## 2026-06-18 - Proof spine: automated demo-replay native-vs-VM equivalence test

Stood up the plan's "deterministic demo-replay equivalence" harness as a standing
regression test (`tests/test_demo_replay_equivalence.py`).  This is the proof-spine
keystone: instead of only per-hook oracle checks, it continuously proves the *whole
live hooked game* still matches the original 8086 ASM over real gameplay.

How it works (reuses existing machinery, no new RE):

- For each recorded demo under `artifacts/demos/`, it loads the demo's start
  snapshot into two runtimes and replays the same inputs into both via
  `InputDemoPlayback.apply_to_runtimes`.
- `overkill.frame_verify.run_frame_verifier` makes the **reference** strip every
  replacement hook except the timer/retrace environment waits (so it interprets
  the original ASM) while the **candidate** keeps all native Python hooks.
- Each frame boundary it asserts the two runtimes are identical on the visible
  framebuffer, the rendered RGB pixels, *and* the decoded semantic `GameSnapshot`
  (objects/positions/flags/timers/score).  `source="both"` + `semantic_state_check`.

Scope/cost:

- Default: a bounded 150-frame prefix of each demo (`OVERKILL_DEMO_VERIFY_FRAMES`
  overrides), ~7s/demo.  L2 + L3 currently pass (`2 passed`).
- Opt-in full-length replay to each demo's recorded `end_boundary` via
  `OVERKILL_FULL_DEMO_VERIFY=1` (minutes/demo; use pytest, not the fail-safe runner).
- One zero-arg test is generated per demo so both pytest and
  `scripts/run_tests.py` discover and run them individually.

Verified as a real assertion: a negative-control run that injects an artificial
semantic divergence at frame 25 makes `run_frame_verifier` return non-zero and the
test fail, with a field-level divergence report.

Why this matters for the source port: this is the verification that must get
*stronger* as the VM gets weaker.  It lets Phase 2 (collapse understood hook
chains) proceed safely - we trade per-hook CS:IP granularity for whole-frame/state
equivalence over the demo corpus.  Next: grow the demo corpus (more levels,
bosses, spawn types, RNG paths) and, when addresses are known, widen the
`GameSnapshot` to RNG/lives/level-wave so the semantic half of the proof is total.

Validation:

```text
python -m pytest tests/test_demo_replay_equivalence.py -q
# 2 passed, 2 skipped (full-length opt-in)   ~15s

python scripts/run_tests.py tests/test_demo_replay_equivalence.py
# 4 passed (fail-safe runner; full tests early-return without OVERKILL_FULL_DEMO_VERIFY)
```

## 2026-06-18 - Phase 1 lift: B86D formation-spawn schedule + outgoing-sprite rules

Continued the DS:2340 formation-counter unification into `1010:B86D`.  Its common
path (reached past the B8F8 edge-steer and A7A0 guards) held two pure rules inline:

- `b86d_formation_spawn_tick_index(game_counter)` - the exact-tick formation-spawn
  schedule (`02EFh`/`0159h`/`0079h` -> variant 0/1/2, else no spawn).  This is the
  same DS:2340 global counter that B73E gates on, now a named source-level rule.
- `b86d_outgoing_sprite_for_delta(vertical_delta)` - outgoing sprite from the sign
  of the global vertical delta DS:2342 (`FFFFh` -> rising `0075h`, else falling
  `0076h`).

`_run_object_behavior_b86d` now calls both pure rules and asserts agreement,
keeping the chained CMP/JE order, the NEG/CMP, and the 7476 continuation
addresses (adapter glue) oracle-exact.

The lifted common path is exercised by the existing
`snapshot_stop_1010_b8b0_behavior` oracle (gc=`00CBh` non-trigger, delta=`0001h`
falling), so the change is covered by ASM equivalence, not just the pure unit test.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py -q -k b86d
# 2 passed (b8b0 snapshot drives the lifted 439-464 path vs interpreted ASM)

python -m pytest tests/test_recovered_semantics.py tests/test_architecture_layers.py -q
# 37 passed (adds the B86D common-path pure-rule test)

python scripts/audit_recovered_layers.py   # 17 pure files
python scripts/lint.py                      # 145 files
python scripts/audit_hook_oracle.py         # 335 hooks / 335 metadata
```

Pre-existing/unrelated: two `bfc7` oracle tests error on a missing artifact
(`artifacts/snapshot_play_tandy_20260614_191454`), an environment gap, not a
behavior regression.

DS:2340 unification status: B73E (band gate) and B86D (exact-tick schedule) now
both express their formation-counter decisions as pure named rules.  The
remaining DS:2340 consumer is `B9F0`, still blocked on having no oracle test.

## 2026-06-18 - Phase 1 lift: B73E idle-phase rules become pure systems

Continued the Phase 1 sweep into `1010:B73E`, the substate/idle object behavior.
Two genuinely-pure gameplay rules were tangled inline among the CPU arithmetic on
the no-substate (`FFFFh`) idle path; both are now named pure functions while B73E
keeps its oracle-exact flags.

Implemented:

- `overkill/recovered/systems/objects.py`:
  - `b73e_idle_sprite_frame(timer, y)` - the DS:2338 timer -> animation-frame
    formula (high objects above the `0060h` Y line count down from `007Fh`, low
    objects count up from `007Ah`), with named constants.
  - `b73e_reaches_b808(game_counter)` - the DS:2340 spawn-window gate: inside the
    `[02BCh, 02D0h]` band the B800 formation spawn-pointer advance runs, otherwise
    control reaches B808 and skips it.
- `overkill/gameplay/object_behaviors.py`: `_run_object_behavior_b73e` now calls
  both pure rules and asserts agreement, keeping the inline NEG/ADD and the
  two-step compare order so 8086 flags still match the oracle.

Unification: B73E's `B82D` waypoint loop re-implemented the exact same
`[02BCh, 02D0h]` spawn-window band check as the non-loop path.  That duplicate is
now routed through the single shared `b73e_reaches_b808`, so the one gameplay rule
has one source-of-truth (the existing `b73e` B82D-loop oracle test covers it).

The substate jump table at CS:B74E (the `B754`/`B770`/`B77B` arm dispatch) is
deliberately left inline; it is CS-data-table-driven and belongs to the Phase 3
data-decode pass, not a pure-rule lift.

Frontier note: `1010:B9F0` gates formation spawns on the same DS:2340 counter but
with exact-tick triggers (`02EFh`/`0159h`/`0079h`).  Unifying that into a pure
formation-spawn-schedule rule is the natural next step, but B9F0 has **no oracle
test yet**, so its logic must not be refactored until a B9F0 ASM-equivalence
snapshot/test exists (build that first, then lift).

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 31 passed (adds the B73E idle-phase pure-rule test)

python -m pytest tests/test_overkill_hooks.py -q -k b73e
# 6 passed (full-state + full-memory equivalence vs interpreted ASM)

python -m pytest tests/test_architecture_layers.py -q
# 5 passed
python scripts/audit_recovered_layers.py   # 17 pure files
python scripts/lint.py                      # 145 files
python scripts/audit_hook_oracle.py         # 335 hooks / 335 metadata
```

Note: the original binary lives at `overkill/assets/` in this tree; the tests and
AGENTS.md expect the repo-root `assets/`.  A copy now exists at `assets/`
(gitignored) so the oracle suite resolves `assets/OVERKILL`.

## 2026-06-18 - Phase 1 lift: AD60 bounds/tile branch decision becomes a pure system

Continued the Phase 1 live-hook -> (thin adapter + pure recovered rule) sweep on a
dense gameplay decision.  The shared `1010:AD60` bounds/tile tail
(`_run_object_bounds_tile_tail_ad60`, used by every object behavior that reaches
the postmove bounds check via AD5A/ADC9) had its gameplay rule inlined among the
CPU side effects: the off-screen deactivation predicate and the tile-probe
eligibility gate.

Implemented:

- `overkill/recovered/domain/object_behaviors.py`: added `ObjectBoundsTileDecision`
  (`deactivate` / `skip` / `tile_probe`).
- `overkill/recovered/systems/objects.py`: added the pure
  `object_bounds_tile_decision_ad60(x, y, draw_layer, logic_id, tile_probe_suppressed)`
  plus the recovered constants `OBJECT_BOUNDS_MIN_X=0008h`, `OBJECT_BOUNDS_MAX_X=00E0h`,
  `OBJECT_BOUNDS_MAX_Y=00C8h`, `OBJECT_BOUNDS_TILE_PROBE_DRAW_LAYER=0002h`, and the
  probing `OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS` set.
- `overkill/gameplay/object_bounds.py`: `_run_object_bounds_tile_tail_ad60` now
  computes the pure decision up front and replays the exact CMP order, asserting
  the pure decision agrees at every deactivate/skip/tile-probe boundary.  The
  BD17 deactivate side effect, the 5073/505B tile probe, and the ADC1 sub-deactivate
  are unchanged.

The branch decision is now native: AD60's "left the play-field box -> deactivate"
and "in-bounds probing family -> run tile probe" rules live in a pure function
with no CPU/memory dependency, while the adapter keeps oracle-exact 8086 flags.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 30 passed (adds the AD60 pure decision + adapter-agreement tests)

python -m pytest tests/test_architecture_layers.py -q
# 5 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 17 pure files
python scripts/lint.py
# Lint passed for 145 Python files
python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 335 registered hooks, 335 metadata entries
```

The AD60-reaching oracle tests confirm zero behavioral change against
interpreted original ASM:

```text
python -m pytest tests/test_overkill_hooks.py -q \
  -k "object_behavior or bounds or ad60 or ad5a or deactivate"
# 9 passed

python scripts/play.py --snapshot artifacts/evidence/snapshot_stop_1010_aed8_b250_overlap \
  --video tandy --sound adlib --verify-hook 1010:AED8 --verify-max 1 \
  --verify-step-budget 200000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1   (full-memory + full-state differential)
```

Next Phase 1 candidate: keep sweeping the inline branch decisions in
`object_bounds`/`object_behaviors` postmove tails (e.g. the per-`logic_id` motion
selectors in `_run_object_behavior_b73e`) into pure recovered predicates.

## 2026-06-17 - High-level action layer extraction and sound-driver unification

Performed a structural cleanup pass after the hook-registry split.  The goal was not to lift a new gameplay routine, but to make the emerging source-like gameplay layer more visible and to remove one confusing coverage convention around sound addresses.

Implemented:

- Added `overkill/gameplay/action_spawns.py` and moved the `A067` action-spawn family out of `frame_orchestration.py`.
- `frame_orchestration.py` is now back to frame/controller concerns, while `action_spawns.py` owns the raw `A067/A0E8` action fanout, `A515/A584`, `A3CA/A3FF`, and `A2A0/A2F6/A337` children.
- Added small source-like structures around already-proven behavior:
  - `ActionCounterSnapshot` for the `A970/A972/A976/A974 -> A3A0/A3A2/A3A4/A3A6` counter publish step.
  - `PairSpawnTailPlan` for the duplicated `A2F6/A337` two-slot spawn tail shape.
  - `action_trigger_is_pressed(...)` and `action_latch_allows_repeat(...)` for the raw `98BE & 10h` and `A980/9790/232A` gates.
- Added `overkill/sounds/loaded_driver.py` as the single source of truth for the loaded optional sound-driver segment `2032h`.
- Updated coverage classification, verifier stops, sound wrappers, the static runtime bundle, and sound-driver helpers to use `OPTIONAL_SOUND_DRIVER_SEGMENT` instead of repeating literal `2032h`.
- Updated `scripts/audit_hook_oracle.py` so the static hook audit understands named integer constants in decorators and `HookStop` metadata.

The important sound clarification: the many unhooked calls classified as `sound` share a real unifying element.  They are in the loaded optional AdLib/Roland driver segment `2032:*`, not arbitrary gameplay routines that happen to be near sound code.  The currently lifted driver entrypoints remain explicit in `OPTIONAL_SOUND_DRIVER_HOOK_ADDRS`, while the whole segment stays classified as the `sound` island for coverage purposes.

No new high-level entity semantics were introduced.  In particular, `A067` remains a proven action/object-spawn fanout, not yet a named weapon or player-shooting model.

Validation:

```text
python scripts/lint.py
# Lint passed for 124 Python files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 335 registered hooks, 335 metadata entries

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python -m pytest tests/test_recovered_semantics.py -q
# 25 passed

python -m pytest focused action/frame-controller tests -q
# 5 passed

python -m pytest focused sound-driver tests -q
# 4 passed
```

Next cleanup direction: continue extracting source-like gameplay clusters from the frame/controller layer only when they are already proven at ASM boundaries.  The remaining action-spawn unknown with the highest semantic value is still the out-of-range `44AF` tail observed behind `A958`.

## 2026-06-17 - A2A0/A2F6/A337 action-spawn table tails

Continued the gameplay-logic understanding pass behind `A067/A0E8`.  After `A3CA/A3FF`, the highest-value remaining in-range action fanout was the `A2xx` cluster selected by `DS:A958`: the pre-table `A2A0` path when `A958 == 5`, plus the table tails `A2F6` (`A958 == 4`) and `A337` (`A958 == 3`).

Implemented:

- `1010:A2A0 overkill_frame_action_listed_anchor_spawn_a2a0` as a standalone hook.
- `1010:A2F6 overkill_frame_action_pair_spawn_a2f6` as a standalone hook.
- `1010:A337 overkill_frame_action_pair_spawn_a337` as a standalone hook.
- Local lifted bodies for the shared `A2D6` spawn/list/projection body, `A294` list append, and `A1AE` BP-relative coordinate projection.
- Updated hook metadata, frontier notes, symbols, runtime findings, and island truth-table notes.

Recovered structure:

```text
A2A0:
  gate: A3A2 == 0
  if 98C0 != 0: BEFF = 11
  ES = CS:9596
  A3EA = A3B4
  clear 1Ah words at ES:A3B4 to FFFF
  call A2D6
  stamp first slot +8 = 006A
  subtract 8 from first slot Y
  fall through into A2D6 again

A2D6 body:
  A972++
  call A4EA
  call A294       ; append BX to the A3EA list
  stamp +18 = 9
  call A1AE       ; BP+8 coordinate source + BP+2/BP+4 offsets
  align/offset Y with AND FFF8, +8
  stamp +8 = 006C

A2F6:
  gate: A3A0 == 0
  if 98C0 != 0: BEFF = 17
  allocate/project two slots through A4EA/A1AE
  stamp both +18 = 8, +8 = 35
  add 8 to the second slot X

A337:
  gate: A3A0 == 0
  if 98C0 != 0: BEFF = 16
  allocate/project two slots through A4EA/A1AE
  stamp both +18 = 7, +8 = 37
  add 8 to the second slot X
```

The important quirk in `A2A0` is the same kind of call/fallthrough shape seen in `A3FF/A378`: one local `CALL A2D6`, then first-slot postprocessing at `A2CD`, then fallthrough into `A2D6` again.  So this path deliberately creates two slot actions, not one.

Semantic interpretation remains structural.  These are proven raw action-spawn table tails behind `A067`, with counters (`A970/A972`), `BEFF` event/status bytes, raw slot fields, and the `A3B4`/`A3EA` list.  They are not yet promoted to a named weapon, projectile, player, enemy, or pickup semantic.  The remaining major `A067` action-spawn frontier is now the real out-of-range `A958` target `44AF` observed when `A958 == 5` after the pre-call `A2A0`.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_frame_action_a2xx_spawn_tails_match_interpreted_paths -q
# 1 passed

python -m pytest \
  tests/test_overkill_hooks.py::test_frame_action_a2xx_spawn_tails_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_anchor_dispatch_children_a3ca_a3ff_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_post_contact_status_helper_9e19_matches_interpreted_paths \
  tests/test_recovered_semantics.py -q
# 30 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 335 registered hooks, 335 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:A067 \
  --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1
```

A direct headless `--verify-hook 1010:A2A0` from the bundled gameplay snapshot did not naturally reach the new A2xx child before the existing unrelated text-input DOS read blocked at `5497`; the proof added here is the focused ASM-vs-hook oracle test plus successful parent `A067` verifier coverage.

Next highest-value boundary is `44AF`, because the in-range `A067/A0E8` action-spawn children are now lifted and `44AF` is the remaining table tail that can still hide a larger action variant.

## 2026-06-17 - A3CA/A3FF action-side anchor dispatch hooks

Continued the gameplay-logic understanding pass behind the `A067` action/object-spawn fanout.  The best next boundary was the `A3CA`/`A3FF` pair because both are direct `A067` children, both share the same local `A41A` dispatch body, and together they explain most of the remaining side/mirrored raw slot-spawn behavior before the still-larger `A2A0` path.

Implemented:

- `1010:A3CA overkill_frame_action_side_anchor_spawn_a3ca` as a standalone hook.
- `1010:A3FF overkill_frame_action_mirrored_anchor_spawn_a3ff` as a standalone hook.
- A lifted local `A41A` body used by both hooks.  It dispatches `DS:A958` through the raw `CS:A42C` table: `A4D7`, `A490`, `A499`, `A464`, `A438`.
- A lifted local `A378` follow-up used by `A3FF`.  Important recovered quirk: the open path creates two slots, because the original code `CALL`s `A396`, stamps the first slot's `+18` field to `6`, and then falls through into `A396` a second time.
- Updated `symbols.json`, frontier notes, runtime findings, and island truth-table notes.

Recovered structure:

```text
A3CA:
  A3EC = 7; SI = [A966]; call A41A
  A3EC = 1; SI = [A968]; call A41A
  A3EC = 7; SI = [A96A]; call A41A
  A3EC = 1; SI = [A96C]; call A41A

A3FF:
  A3EC = FFFF
  SI = [A962]; call A41A; call A378
  SI = [A964]; call A41A; call A378

A41A table selected by A958:
  0 -> A4D7 coordinate-copy spawn
  1 -> A490 A4D7 + +8=0033
  2 -> A499 A3EC/direction-stamped spawn
  3 -> A464 gated two-spawn pair, +18=7/+8=37
  4 -> A438 gated two-spawn pair, +18=8/+8=35
```

Semantic interpretation stays deliberately structural.  `A3CA`/`A3FF` look like side/mirrored action-spawn helpers, but they are not yet promoted to a named weapon, projectile, enemy, pickup, or player semantic.  The evidence is raw source pointers, `A3EC` stamps, `A958` table targets, `A970/A976` counters, `BEFF=12` on the `A378/A396` path when `98C0 != 0`, and raw slot fields.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_frame_action_anchor_dispatch_children_a3ca_a3ff_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_post_contact_status_helper_9e19_matches_interpreted_paths \
  tests/test_recovered_semantics.py -q
# 29 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 332 registered hooks, 332 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

A direct headless `--verify-hook 1010:A3CA` from the currently bundled gameplay snapshot did not naturally reach the new hook before an unrelated text-input DOS read blocked, so the proof added here is the focused ASM-vs-hook oracle test plus metadata/audit coverage.  A full repository `pytest -q -x` still stops at the existing coverage-classifier expectation in `tests/test_core.py::test_coverage_summary_reports_grouped_bounded_original_regions` (`input_menu` expected for a synthetic `9B2E` bounded region), which is unrelated to this hook work.

Next highest-value boundary is now `A2A0` behind the `A067/A0E8` action fanout, plus any real out-of-range `A958` table targets observed in traces.

## 2026-06-17 - 9E19 shared post-contact/status helper hook

Continued the gameplay-logic understanding pass from the `9CB6` contact fanout and the `B24D` overlap branch.  The best next boundary was `1010:9E19`, because it is shared by both paths and owns the raw contact/status counters that were still opaque after `9CB6`.

Implemented:

- `1010:9E19 overkill_post_contact_status_helper_9e19` as a standalone hook.
- Kept `9CB6` as a pure fanout parent: it now composes a verifier-visible `9E19` child instead of a bounded-original helper.
- Updated the `B24D` overlap behavior comments/metadata so its `PUSH CX; PUSH BP; CALL 9E19; POP BP; POP CX` loop remains a parent contract around a separate child hook.
- Updated symbols/frontier metadata and runtime findings.

Recovered structure:

```text
guards:
  if A47C == 1      -> RET
  if DS:2384 >= 3   -> RET
  if A95A == FFFF   -> RET

contact-status path:
  DS:23A0 = 8
  if 98C0 != 0: BEFF = 0F
  decrement A95C by:
    BEDC == 0     -> 1 step
    BEDC == 1     -> up to 2 steps
    BEDC other    -> up to 3 steps
  if A95C remains non-zero:
    call 61DC
    if CS:95BC == 1: call 511F, 61DC, 511F
    RET

A95C refill path:
  A95C = 18
  repeat A47C/2384 guards
  if 98C0 != 0: BEFF = 03
  if BEDC == 0:
    A362 = (A362 + 1) & 1
    if A362 != 0: RET
  decrement A95A
  if A95A != FFFF:
    display as above
    RET

A95A expiry path:
  A95C = 0
  if byte 9791 == 1:
    A95A = 3
    A95C = 18
    RET
  DS:2384 = 3
  if 98C0 != 0: BEFF = 19
  display as above
  RET
```

Semantic interpretation remains narrow: `9E19` is a shared raw post-contact/status counter helper.  It looks very damage/hit/cooldown-adjacent because of `A95A/A95C`, `2384`, `A362`, `23A0`, and `BEFF`, but the hook deliberately does not yet rename those fields as health/lives/invulnerability without more cross-routine evidence.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_post_contact_status_helper_9e19_matches_interpreted_paths -q
# 1 passed

python -m pytest tests/test_overkill_hooks.py::test_post_contact_status_helper_9e19_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_contact_probe_fanout_9cb6_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths \
  tests/test_recovered_semantics.py -q
# 28 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:9E19 \
  --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:9CB6 \
  --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 332 registered hooks, 332 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

Next highest-value boundary after `9E19` was the `A3CA`/`A3FF` pair behind the `A067`/`A0E8` action fanout; the follow-up section above records that lift.

## 2026-06-17 - B15A shared candidate-scan hook

Continued the gameplay-logic understanding pass from the `A067`/`A515` action-spawn frontier.  The best next boundary was `1010:B15A`, because it is shared by the already lifted `B1B0` chase-acquisition behavior and by the new `A515` anchored spawn/link helper.

Implemented:

- `1010:B15A overkill_player_chase_candidate_scan_b15a` as a standalone hook.
- Kept the source-like candidate predicate in `overkill.recovered.systems.objects` and the exact cursor/register/flag behavior in the lifted gameplay layer.
- Updated `B1B0` so its `CALL B15A` goes through the real hook boundary via verifier-visible near-call semantics instead of calling the internal helper directly.
- Updated symbols/frontier metadata and runtime findings.

Recovered structure:

```text
CX = 0023h
BX = DS:A43A
if BX >= 2B5Ch: DS:A43A = 23B4h; restart without consuming CX
scan DS:23B4..2B5C in 38h-byte slots
candidate iff:
  active_word != 0
  logic_id not in {0001h, 0026h, 0021h, 0022h}
  x <= 00E0h
  hazard_class == 0004h
success -> DS:A43A = found_bx + 38h, BX = found_bx
failure after 23h slots -> BX = FFFFh
```

Semantic interpretation remains narrow: this is a shared rotating effect/contact-slot candidate scan.  It should not yet be treated as a global enemy/projectile/pickup classifier.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_player_chase_candidate_scan_b15a_matches_interpreted_paths -q
# 1 passed

python -m pytest tests/test_recovered_semantics.py   tests/test_overkill_hooks.py::test_player_chase_candidate_scan_b15a_matches_interpreted_paths   tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths   tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths -q
# 28 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 329 registered hooks, 329 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

A direct headless `--verify-hook 1010:B15A` from the currently bundled gameplay snapshots did not naturally reach `B15A` before unrelated input/menu blocking or timeout, so the proof added here is the focused ASM-vs-hook oracle test plus the verifier-visible child boundary from `B1B0`/`A515` composition.

Next highest-value boundaries remain `A3FF`, `A3CA`, and `A2A0` behind the `A067` action fanout, plus `9E19` behind the `9CB6` contact fanout.

## 2026-06-17 - A515/A584 A067 child spawn-frontier split

Continued the gameplay-logic understanding pass from the lifted `A067` action/object-spawn fanout.  Instead of adding a speculative high-level weapon/player model, this pass split two concrete child frontiers that `A067` had isolated: `1010:A515` and `1010:A584`.

Implemented:

- `1010:A515 overkill_frame_action_linked_anchor_spawn_a515`:
  - gates on raw counters `DS:A960` and `DS:A97E`;
  - allocates one destination slot through `7547`;
  - anchors destination coordinates from the current `SS:BP` slot through `A571`;
  - temporarily switches `BP=BX` and calls the still-separate `B15A` child;
  - if `B15A` returns `BX != FFFF`, stamps the destination slot fields, stores the returned word at `BX+30`, optionally writes `BEFF=11`, increments `A97E`, and decrements `A960`.
- `1010:A584 overkill_frame_action_dual_anchor_spawn_a584`:
  - gates on raw `DS:A95E` and copied counter `DS:A3A4`;
  - increments `A976` before each allocation;
  - creates two destination slots through `A4EA` + `A571`;
  - aligns each spawned slot's Y field with `AND [BX+4], FFFC`;
  - stamps `BX+8 = 8` and `BX+18 = 5/6`.

Semantic interpretation remains deliberately structural.  These are now proven as `A067` child spawn/slot side-effect helpers, but they are not yet named as player weapon, enemy, projectile, or pickup logic.  `B15A`, `A3FF`, `A3CA`, and `A2A0` remain the best next child frontiers behind this action fanout.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths -q
# 1 passed

python -m pytest \
  tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths -q
# 3 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:A067 \
  --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 328 registered hooks, 328 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

Direct headless verification of `A515`/`A584` from the available gameplay snapshot did not naturally hit those routines before unrelated menu/input blocking, so the proof added here is a focused ASM-vs-hook oracle test with explicit child boundaries plus parent `A067` verifier coverage.

## 2026-06-17 - A067 frame action/object-spawn fanout hook

Split the highest-value frontier left under the lifted `1010:9B2E` frame
controller.  The new `1010:A067 overkill_frame_action_spawn_fanout_a067` hook
covers the input-bit-gated action/object-spawn fanout that is also reached from
`1010:D04D`.

Observed structure:

- `DS:98BE & 10h` is the outer gate.  When clear, the routine tails through
  `A060`, clears `DS:A980`, and returns.
- `DS:A980` is a one-shot/repeat latch.  Re-entry is blocked unless `DS:9790`
  equals `1` or `DS:232A` equals `0x000F`.
- Entering the action path sets `DS:A980 = 1`.
- High-view paths copy `A970/A972/A974/A976` into `A3A0/A3A2/A3A6/A3A4` before
  dispatch.
- Low-view `BDAC == 0` paths jump directly to the `A958` action tails:
  `A958 == 2` uses the double-spawn `A1C8` tail; other tested values use
  `A19F`.
- The high-view main path composes bounded child frontiers `A515`, `A584`,
  `A3FF`, `A3CA`, and the `A0E8` sub-dispatch.
- `A0E8` optionally calls `A2A0`, optionally calls the `A114` three-spawn
  helper when `A96E != FFFF`, then jumps through the `A958` table.
- Proven in-hook tails are `A114`, `A175`, `A18A`, `A19F`, `A1AB/A1AE`, and
  `A1C8`.  Out-of-range `A958` table entries still tail-jump to bounded
  original code rather than being guessed.

Validation:

```text
python -m pytest   tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths   tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths   tests/test_overkill_hooks.py::test_frame_contact_probe_fanout_9cb6_matches_interpreted_paths -q
# 3 passed

SDL_VIDEODRIVER=dummy python scripts/play.py   --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042   --video tandy --sound pc --verify-hook 1010:A067   --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 326 registered hooks, 326 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

Important correction found during the lift: calls to `A1AE` inside the `A1C8`
tail intentionally skip the `A1AB` allocation call because the caller already
called `A4EA`.  Treating `A1AE` as if it were `A1AB` doubles the spawned-slot
count and leaves `BX`/stack scratch different from ASM.

Next high-value work is now either the remaining larger children behind this
fanout (`A515/A584/A3FF/A3CA/A2A0`) or the post-contact/status helper `9E19`.
`A067` should still be described as raw action/object-spawn glue, not as a named
weapon/player semantic.

## 2026-06-17 - 9CB6 contact-probe fanout hook

Split the next high-value child frontier exposed by `9B2E`.  The new
`1010:9CB6 overkill_frame_contact_probe_fanout_9cb6` hook is a narrow
frame/collision fanout primitive: it calls the already recovered `4FF9`
tile/contact probe, returns immediately when carry is clear, and on carry-set
preserves `BP` while calling the still-bounded `9E19` post-contact/status helper
according to raw `DS:BEDC`.

Recovered fanout shape:

```text
4FF9 CF clear -> RET
4FF9 CF set, BEDC == 0     -> 9E19, 9E19
4FF9 CF set, BEDC == 1     -> 9E19, 9E19, 9E19
4FF9 CF set, BEDC other    -> 9E19, 9E19, 9E19, 9E19
```

This deliberately does not classify the contact as player/enemy/projectile
semantics.  It only proves that `9CB6` is the frame-controller contact side
effect fanout around the lower tile/contact sampler and the still-separate
`9E19` status/counter helper.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths \
  tests/test_overkill_hooks.py::test_frame_contact_probe_fanout_9cb6_matches_interpreted_paths -q
# 2 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:9CB6 \
  --verify-max 1 --verify-step-budget 200000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_frame_contact_probe_fanout_9cb6_matches_interpreted_paths -q
# 26 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 325 registered hooks, 325 metadata entries, no direct registered child calls detected.

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/lint.py
# Lint passed for 119 Python files
```

Next best frontier is now `A067/A060-A211`, because `9CB6` is no longer a black
box and its remaining unknown child is specifically the bounded `9E19` helper.

## 2026-06-17 - 9B2E frame-controller parent hook

Promoted the next large game-logic frontier from bounded original to a
verifier-visible parent hook without introducing semantic player/enemy names.
The new `1010:9B2E overkill_frame_controller_9b2e` hook composes the existing
children in original order: input poll, `BP=237C` current object/script slot,
direct movement bits, `A66F`, the still-separate `A067` action/helper frontier,
optional `9D4D`, `A616`, `9CB6`, `9C01`, coordinate-ring maintenance, and
`9FAF` linked child-coordinate propagation.

Important recovered fact:

- The backwards branch target `9AFF` is not simply an early return.  Its two
  `JZ +1` instructions mean "skip the RET and continue".  The tail only reaches
  `4DBF` when `DS:2326 == 3` and the incremented `SS:[BP+8] == 0Fh`; then it
  clears `SS:[BP+0]`, sets `DS:A346`, and sets `DS:A342` only when `DS:A97A` is
  zero.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths \
  tests/test_overkill_hooks.py::test_frame_axis_condition_dispatch_9c01_hook_matches_composed_interpreted_snapshot \
  tests/test_recovered_semantics.py -q
# 27 passed

python scripts/lint.py
# Lint passed for 119 Python files

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 324 registered hooks, 324 metadata entries, no direct registered child calls detected.

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:9B2E \
  --verify-max 1 --verify-step-budget 200000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1
```

Next best game-logic frontiers are now smaller and clearer: split `A067/A060-A211`
from direct replay evidence, then split `9CB6/9CBC` instead of treating `9B2E`
as the remaining monolith.

## 2026-06-17 - A5xx/A6xx movement and edge-scroll crystallisation

Continued the game-logic refactor in the recovered source-port direction.  This
pass deliberately avoided new high-level entity names: it promoted only the
source-level value decisions behind already verified low-level movement helpers.

Implemented:

- Added pure movement-domain records for axis-clamp and vertical edge-scroll
  results.
- Promoted the final value logic behind `1010:A5D1`, `A5EA`, `A5F9`, and `A607`
  into `overkill.recovered.systems.movement.two_pass_axis_clamp_step` and
  `one_pixel_axis_step`.
- Promoted the final `DS:A39A/A39C` edge-scroll bias logic behind `1010:A616`,
  `A648`, `A63C`, and `A662` into pure recovered movement helpers.
- Kept the lifted hook path responsible for all ASM-visible behavior: CMP/TEST
  order, INC/DEC flags, CALL-next stack scratch, nested return words, and near
  RET continuation behavior.  The hook path now asserts that its replay agrees
  with the pure system result.
- Added a source-port-safe recovered semantics test for the new pure helpers and
  updated recovered-layer/runtime/island documentation.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 25 passed

python -m pytest \
  tests/test_recovered_semantics.py::test_recovered_axis_clamp_and_vertical_scroll_bias_are_pure_source_port_helpers \
  tests/test_overkill_hooks.py::test_object_two_pass_clamp_step_helpers_match_original \
  tests/test_overkill_hooks.py::test_object_vertical_scroll_edge_helpers_match_original -q
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*vertical_scroll*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*clamp_step*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/lint.py
# Lint passed for 119 Python files
```

Next best crystallisation candidates:

- `9B2E` has now been lifted as a parent; continue with `A067/A060-A211` or
  `9CB6/9CBC` using focused oracle tests, not input-name guesses;
- look for duplicated value decisions in the `B00D` directional tile-response
  path and promote only the pure sampling/plan layer;
- keep `A067`/`A060-A211` bounded until a direct replay snapshot proves the
  exact UI/frame-state side effects.

## 2026-06-16 - Status parent and 9C01 child absorption

Continued from the bounded-original frontier triage by converting two named
frontiers into verifier-visible hooks instead of only classifying their bytes.
The work stayed in the verified lifted-routine layer: no semantic HUD or
movement model was introduced.

Implemented:

- `1010:61DC overkill_status_display_parent_61dc`:
  - clears the six `SS:2368..2372` status/counter words with a local
    `REP STOSW` mirror;
  - runs the existing `61F7/61C7` countdown scan while `DS:A95C` is positive;
  - draws the six counter cells through the existing `6296` child;
  - optionally draws the two trailing marker cells through `5A00`/`5A6C`;
  - preserves the original near-call/dispatch stack shape for all child calls.
- `1010:9C01 overkill_frame_axis_condition_dispatch_9c01`:
  - lifts the child frontier inside the larger bounded `9B2E` frame controller;
  - combines the `DS:98BE` input bits, `A39E/A39F` edge markers, and the
    `A966/A968/A96A/A96C` delayed coordinate-slot counters;
  - preserves the small jump-table dispatch to direct `RET`, `9C82/9C9C`
    guarded tails, and one-pass `A60A`/`A5FC` Y-step bodies.
- Updated hook metadata, `symbols.json`, frontier classification, and coverage
  ownership so `61DC` and `9C01` are no longer only bounded-original frontiers.
- Updated older leaf tests for `61C7`, `61F7`, and `6296` to explicitly expose
  those child boundaries now that `61DC` absorbs them by default.

Validation:

```text
python scripts/run_tests.py tests/test_overkill_hooks.py --name '*61dc*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*9c01*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*97b2*' --timeout 100 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*61c7*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*61f7*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*6296*' --timeout 100 --fail-fast --no-lint --verbose
# 1 passed

python -m pytest tests/test_core.py::test_coverage_classifier_marks_known_bounded_frontier_ranges -q
# 1 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 316 registered hooks, 316 metadata entries,
# no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unknown island hooks: 0

python scripts/lint.py
# Lint passed for 81 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

A 100-step coverage probe from `artifacts/evidence/hook_verify_tandy_20260613_190326`
now reports:

```text
ASM interpreted instructions: 1
Bounded original ASM instructions: 5,436
Unknown / unmeasured hook calls: 1
unknown bounded count 0
unknown interpreted count 0
```

The remaining bounded-original hotspot is now more concentrated around the parent
`1010:9B2E-9BFA` frame controller, with `9C01` removed from that frontier.  The
next useful absorption targets are `A067`/`A060-A06C`, `9CB6-9CBB`, and the
collision tails (`BE3C`, `AAC2`, `8331`) that are still visible as bounded
regions.

## 2026-06-16 - Bounded-original coverage frontier triage

Continued the unknown-instruction cleanup from the uploaded `overkill_port(23)`
snapshot.  The important distinction in this pass is that no gameplay behavior
was replaced: the changes are diagnostic/classification work that makes the
remaining bounded-original ASM visible by semantic island instead of hiding it in
`unknown`.

Implemented:

- Added grouped bounded-original regions to `CoverageTelemetry.format_summary()`.
  The dashboard now reports both per-instruction and nearby-region views for
  `BOUNDED_ORIGINAL`, matching the existing interpreted-ASM region view.  This
  makes parent wrappers such as `9B2E` and rare child tails easier to absorb
  safely because the next frontier is shown as a range, not only as scattered
  IPs.
- Added conservative classifier ranges for already-triaged bounded frontiers:
  - `1010:9B2E-9CBB` input/menu frame-controller child and contact-probe wrapper;
  - `1010:A060-A211` game-state/UI object helper reached from `A067`;
  - `1010:BE3C-BEB6`, `1010:AAC2-AAFB`, `1010:8331-835A`, and
    `1010:AA44-AA70` collision/contact tails;
  - `1010:BD17-BD65`, `1010:C054-C15B`, `1010:8D4F-8D8D`, and
    `1F8F:027A-0451` gameplay-object tails/scripts;
  - `1010:61DC-6295` rare status-display parent reached from object/status
    tails;
  - `1010:5F0D-5F42`, `1010:9D67-9EF2`, and `1010:981D` status/frame-state
    tails;
  - `1010:77DF-77F5` bounded layer/effect wrapper;
  - the tiny `1010:AB0C-AB0D` jump-table tail back into `BD17`.
- Added focused coverage tests proving the new bounded-original region report and
  the known frontier range ownership.  Exact address classifications still win
  before these broad diagnostic ranges, so existing hook/island ownership is not
  weakened.

Validation:

```text
python -m pytest \
  tests/test_core.py::test_coverage_telemetry_counts_interpreted_and_verified_hooks \
  tests/test_core.py::test_coverage_summary_reports_grouped_interpreted_regions \
  tests/test_core.py::test_coverage_summary_reports_grouped_bounded_original_regions \
  tests/test_core.py::test_coverage_classifier_marks_transient_bootstrap_segment \
  tests/test_core.py::test_coverage_classifier_marks_known_bounded_frontier_ranges \
  tests/test_core.py::test_all_registered_overkill_hooks_have_non_unknown_island_classification -q
# 6 passed in 0.93s

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 314 registered hooks, 314 metadata entries,
# no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unknown island hooks: 0

python scripts/lint.py
# Lint passed for 81 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

A 100-step probe from `artifacts/evidence/hook_verify_tandy_20260613_190326`
with coverage telemetry attached now reports:

```text
ASM interpreted instructions: 1
Bounded original ASM instructions: 5,492
Unknown / unmeasured hook calls: 0
unknown bounded count 0
unknown interpreted count 0
```

The one remaining interpreted instruction in that probe is `1010:981D`, now
classified as `game_state`; it is the final frame-loop jump tail after `97B2`,
not a new unknown island.

I also tried the full `scripts/run_tests.py --no-lint --scope all --timeout 20
--fail-fast` runner in this sandbox, but it did not complete before the sandbox
command timeout.  The focused coverage tests, hook-oracle audit, island audit,
lint, and DOS-RE smoke scope all passed.

Next absorption targets are now cleaner:

- lift or further wrap the `1010:9B2E` bounded frame-controller child instead of
  chasing scattered unknown IPs;
- decide whether `1010:61DC` should be lifted as a full status-display parent or
  split into its display/data-table children;
- add missing oracle tests for already-registered but no-test hooks in the open
  `layer_sprites`, `movement`, `collision`, `input_menu`, and `sound` islands;
- only then convert more bounded-original leaves into real hooks.

## 2026-06-15 - Deep hook-oracle blind-spot cleanup: CALL and JMP child boundaries

Continued the verifier-hardening pass after the AA71 false-contact bug.  The
previous audit guaranteed that address wrappers in `overkill/hooks.py` were not
calling registered child hooks through the old raw near-call helper, but it still
missed two important classes:

- registered child hooks called directly from other OVERKILL modules;
- original `JMP`/fall-through child transfers, where no synthetic return word
  should be pushed but the child boundary still needs verifier visibility.

Implemented:

- `dos_re.hooks.jump_installed_hook_boundary()`
  - sibling of `call_installed_hook_like_near_call`;
  - routes original JMP/fall-through transfers through the installed hook table
    and live hook verifier without changing stack semantics;
  - records `cpu.hook_jump_site` for diagnostics.
- `call_installed_hook_like_near_call()` now records `cpu.hook_call_site` as
  `(caller_cs, caller_ip, child_cs, child_ip, return_ip)` while the child runs,
  so interactive wrappers can still identify original call-site context even
  though the helper correctly sets `CS:IP` to the child boundary.
- Strengthened `scripts/audit_hook_oracle.py`:
  - scans all `overkill/**/*.py`, not just `overkill/hooks.py`;
  - counts all 314 registered hooks across hook wrapper modules;
  - fails on any direct Python call to a registered hook function.
- Routed previously hidden child boundaries through installed/verifier-visible
  entry points:
  - `A876 -> 4CED`;
  - `4CED -> 4D15` triplet;
  - `A93C -> 4D64 -> 4D6F`;
  - `A90C -> A90F/A927`;
  - `A858/A870 -> 5AC8`;
  - `A936/A91E -> 5A92`;
  - `A8BE/A8F1 -> 7596`;
  - layer-sprite compositor JMP targets from `75F5/768E/7746`;
  - EGA row-driver child boundaries `2932`, `280D`, `2824`;
  - dirty-cell presenter jump targets `CCAA/CCF0/CCC4` and changed-present
    targets `CD8D/CDAA`;
  - source-cell mode-0 `41A6` call inside the CC7F presenter.
- Completed `1010:38B7` as a full near-return hook.  It now executes the shared
  `38D0` tail (`MOV DS,CS:[9596]; RET`) itself, instead of stopping at the
  fall-through and requiring a private compositor helper.  This removes a
  partial-boundary exception from the layer-sprite path.
- Corrected `CD8D` and `CDAA` hook-stop metadata from `near_ret` to fixed
  continuation `CE02`, matching their original JMP-target shape.
- Updated the frame-verifier test fixture to accept the raw-sample trace argument
  that the runner now passes.

Validation:

```text
python scripts/lint.py
# Lint passed for 81 Python files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 314 registered hooks, 314 metadata entries,
# no direct registered child calls detected.

python scripts/run_tests.py --scope dos-re --verbose --no-lint
# 4 passed, 0 failed, 0 timed out

python scripts/run_tests.py tests/test_core.py --name test_hook_oracle_static_audit_passes --timeout 10 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_frame_verify.py --timeout 20 --fail-fast --no-lint --verbose
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*38b7*' --timeout 20 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*presence*' --timeout 30 --fail-fast --no-lint --verbose
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*scan*' --timeout 30 --fail-fast --no-lint --verbose
# 13 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*dirty*' --timeout 30 --fail-fast --no-lint --verbose
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*27eb*' --timeout 60 --fail-fast --no-lint --verbose
python scripts/run_tests.py tests/test_overkill_hooks.py --name '*280d*' --timeout 60 --fail-fast --no-lint --verbose
python scripts/run_tests.py tests/test_overkill_hooks.py --name '*2824*' --timeout 60 --fail-fast --no-lint --verbose
# 3 focused EGA row-driver tests passed

python scripts/verify_hooks_headless.py --demo artifacts/demos/demo_play_tandy_20260615_132423 --demo-continue --verify-max 5000 --max-steps 1600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

Attempted a 10k headless verifier run in this sandbox, but it exceeded the tool
time budget before completion.  Re-run it on the reference machine after this
patch; the 5k run is clean and now includes newly verifier-visible nested child
boundaries.

Remaining explicit frontier:

- There can still be semantically fused routines that intentionally duplicate a
  child loop for performance, but they should no longer be silent: any complete
  registered original boundary called as a child must now go through either
  `call_installed_hook_like_near_call` or `jump_installed_hook_boundary`, and the
  static audit enforces that across the OVERKILL package.
- Rare allow-listed original compositor leaves in `KNOWN_ORIGINAL_LAYER_COMPOSITE_TARGETS`
  remain bounded-original, not Python source yet.  They are visible frontier
  entries for CGA/EGA cleanup, not hidden hook-oracle holes.

## 2026-06-15 - Hook-oracle blind-spot sweep and AF60 direct-entry hook

Continued the verifier-hardening pass after the AA71 final-boss contact bug proved
that parent hooks can hide child-helper mistakes when they call Python children
directly.  This pass focused on remaining direct child-call blind spots rather
than semantic gameplay modeling.

Implemented:

- `1010:AF60 overkill_movement_dir_double_step_2px_af60`
  - direct-entry hook for the self-call double 2-pixel movement step;
  - original shape is `CALL AF63` followed by the `AF63` step-table body;
  - preserves the `AF63` return-word stack scratch and returns to the real
    caller after the second step;
  - signature-guarded by `E8 00 00` + the full `AF63` entry/table/body bytes.
- Converted remaining hook-composition calls in `overkill/hooks.py` that invoked
  registered child hook functions directly to `call_installed_hook_like_near_call`:
  `306F`, `5A24`, `5A00`, `0162`, `497A`, and `50C9`.
- Converted Tandy renderer child calls to verifier-visible installed boundaries
  for `1010:34C5` and `1010:5A36`.
- Added `scripts/audit_hook_oracle.py`, a static guardrail that fails if:
  - a registered hook lacks `HookStop` metadata;
  - `overkill/hooks.py` directly calls a registered child hook through the old
    raw `_call_hook_like_near_call` helper;
  - Tandy rendering reintroduces direct `5A36` child calls.
- Fixed `scripts/lindis.py` so the linear disassembler actually runs from the
  command line; used it to confirm the `AF60 -> AF63 -> AF63` byte shape.

Validation:

```text
python scripts/lint.py
# Lint passed for 80 Python files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 269 registered hooks, 314 metadata entries,
# no direct registered child calls detected.

python scripts/run_tests.py tests/test_overkill_hooks.py --name test_movement_dir_step_tables_match_interpreted_asm_all_directions --timeout 20 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_core.py --name test_hook_oracle_static_audit_passes --timeout 10 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*aa71*' --timeout 30 --fail-fast --no-lint --verbose
# 5 passed

python scripts/run_tests.py --scope dos-re --verbose --no-lint
# 4 passed

python scripts/verify_hooks_headless.py --demo artifacts/demos/demo_play_tandy_20260615_132423 --demo-continue --verify-max 5000 --max-steps 1600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

Known caveat:

- `1010:2ABC -> object_row_address_mode1_2580` is still a raw direct helper call
  because `2580` is a mode-specific EGA-internal helper, not a registered
  top-level hook boundary in the current Tandy-first pass.  It remains an
  explicit audit-visible exception/future EGA cleanup item, not a silent blind
  spot.

Next useful blind-spot work:

- Move the same static audit style into any future module that composes address
  wrappers outside `overkill/hooks.py`.
- Continue shrinking `metadata w/o hook` frontier entries by either registering
  complete direct-entry hooks or demoting metadata-only partial tails to explicit
  bounded-original/frontier notes.
- Re-run a longer demo/headless verifier on the reference machine to see which
  newly exposed nested child boundaries become hot after the first 5k verified
  calls.

## 2026-06-15 - Movement direction step-table entry hooks (AEE4/AF22/AF63)

Lifted the three 8-direction object movement step tables to exact entry hooks.
Re-profiling was attempted from the recommended demo
(`artifacts/demos/demo_play_tandy_20260615_104031`), but the pure-Python
interpreter is far slower in this sandbox than on the reference machine, so the
candidate was instead confirmed by direct linear disassembly of the demo memory
image and the existing island map.

Finding: `1010:AEE4`, `1010:AF22`, and `1010:AF63` are three sibling
8-direction movement step tables with identical shape
(`MOV BX,SS:[BP+06]; SHL BX,1; JMP CS:[table]`) dispatching to handlers that
add/subtract a fixed per-step delta from `SS:[BP+02]` (X) and `SS:[BP+04]` (Y).
The deltas are 8px (AEE4), 3px (AF22), and 2px (AF63).  Each body was already
lifted and verified as a shared helper used by the 5DB2/5E42/AF60 parents
(`_run_aee4_step_for_direction`, `_run_af22_three_pixel_step_for_direction`,
`_run_af63_step_for_direction`), but the table *entries themselves* were not
registered, so a direct `CALL` to any of them (for example `1010:8A1D -> AF63`)
ran interpreted.

Implemented:

- `1010:AEE4 overkill_movement_dir_step_8px_aee4`
- `1010:AF22 overkill_movement_dir_step_3px_af22`
- `1010:AF63 overkill_movement_dir_step_2px_af63`
  - each is a thin near-return entry wrapper that runs the already-verified
    shared body and then `RET`;
  - each is guarded by the full entry+table+handler byte signature, so a
    runtime-patched dispatch/handler disables the hook (falls back to
    interpretation) instead of silently applying the wrong lift.

Classification: all three are `movement` (AEE4 added to `MOVEMENT_ADDRS`; AF22
and AF63 were already listed as bounded movement and are now hook-covered).

Verification (Python 3.10 sandbox; project targets 3.11):

```text
# focused oracle test: interpreted ASM vs hook, real game region bytes,
# all 8 directions x 3 coordinate seeds (incl. borrow/zero edges) per table
tests/test_overkill_hooks.py::test_movement_dir_step_tables_match_interpreted_asm_all_directions
# PASS (72 cases)

tests/test_overkill_hooks.py::test_live_verify_replacement_hooks_have_continuation_metadata
# PASS (new hooks have near_ret continuation metadata)

# regression cross-section, run via the pytest-free harness under python3.10:
#   41/41 movement+object+collision hook tests passed
#   111/111 every-other hook test passed
```

Honest limitations in this sandbox:

- `scripts/lint.py` and the full `scripts/run_tests.py` could not be run here:
  the repo requires Python >= 3.11 (`overkill/frontier_manifest.py` uses
  `enum.StrEnum`) and only Python 3.10 is available in this environment.  This
  is pre-existing and unrelated to the change; the edited modules
  (`hooks`, `gameplay/object_runtime`, `verification`, `coverage`) import and
  run cleanly under 3.10.
- The live headless hook verifier
  (`scripts/verify_hooks_headless.py --snapshot <demo>`) was started but did not
  finish within the sandbox time budget because the interpreter throughput here
  is ~100x slower than the reference machine.  It should be re-run on the
  reference machine:
  `python scripts/verify_hooks_headless.py --snapshot artifacts/demos/demo_play_tandy_20260615_104031/snapshot --verify-max 200 --max-steps 400000 --fast-ranges`.

Added a small generic linear disassembler helper, `scripts/lindis.py`, that
sweeps a CS:offset range using the project's own decoder (counting fetched code
bytes for instruction length, so jump-table data and branches do not derail the
sweep).  It was used to map the AEE4/AF22/AF63 family.

Next candidates from the same family/profile:

- `1010:AF60` self-call double-step entry (already lifted as
  `_run_af60_double_step_for_direction`; works today via the AF63 hook, but a
  dedicated entry hook would cover the self-call trick directly).
- `1010:89FF-8A20` movement setup that feeds `[BP+06]` then `CALL AF63`.
- `1010:F225-F2AE` / `1010:F263` object-behavior families that set sprite ids
  from `DS:2356` game-state then branch through `AFD8`/`BC45`.

## 2026-06-14 - Tile/contact probe cleanup for collision-system crystallization

Continued the small-target ASM cleanup with a meaning-revealing collision primitive rather than a large controller lift.

Implemented:

- `1010:4FF9 overkill_tile_contact_probe_4ff9`
  - shared object/probe-point tile/contact helper;
  - applies one of three `DS:214E` offset pairs to `SS:[BP+2]/[BP+4]`;
  - calls the already-lifted `5073` coordinate-to-tile-index helper and `505B` tile lookup helper;
  - restores the probe coordinates and returns with `CF=0` for empty space or `CF=1` for contact/blocking tile.

Classification note:

- This is still a raw collision primitive, not a semantic player/enemy/projectile rule.
- It helps separate the future `collision_system` layer from higher object behavior families that currently call into it from `9B2E`, `AC28`, and object movement/update paths.

Validation:

```text
pytest -q tests/test_overkill_hooks.py::test_tile_contact_probe_4ff9_matches_interpreted_asm_paths
# 1 passed

python scripts/lint.py
# Lint passed for 76 Python files

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 200 --max-steps 500000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200
```

Next easy meaning-revealing candidates:

- `1010:4E9F/4EBF`: keyboard ISR install/restore around text input prompts, belongs to `input_menu`.
- `1010:53C9-54BF`: text-entry prompt wrapper around `518C` and the temporary INT 9 hook.
- `1010:C51D-C562`: setup/reset tail that seeds tracked-coordinate/status descriptors before jumping to `859E`.
- Smaller children inside `9C01-9C6B` before lifting the whole `9B2E` controller.

## 2026-06-14 - Frame verifier input-pair skew fix

### 2026-06-14 - Hook verifier nested child-boundary honesty audit

- Fixed an oracle blind spot in composed parent hooks: a lifted parent could call an installed child hook directly, while the ASM-oracle clone also used the same child hook.  That made the child a shared black box inside the parent transaction.
- `call_installed_hook_like_near_call` now routes direct child calls through the active hook verifier when verification is enabled, with original near-CALL stack semantics and the child CS:IP restored before execution.
- Bounded interpreted near/far helpers now keep nested hook verification active by default, so child hook addresses reached by original helper code are verified at that exact VM state.
- Added `verify_nested_hooks` to `HookVerifierConfig`; it defaults to strict nested verification.  `play.py --verify-no-nested` and `verify_hooks_headless.py --no-nested` provide the old faster/shared-child mode for profiling only.
- Added a regression that intentionally makes a child hook wrong and proves the parent verifier catches the nested child divergence instead of passing the parent boundary.

Validation:

```text
python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q tests/test_overkill_hooks.py::test_hook_verifier_recursively_verifies_direct_child_hook_calls tests/test_overkill_hooks.py::test_hook_verifier_live_passthrough_override_can_publish_without_frame_boundary tests/test_overkill_hooks.py::test_hook_verifier_defers_live_passthrough_yield_until_after_diff tests/test_frame_verify.py
# 6 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 300 --max-steps 1000000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=300

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 80 --max-steps 600000
# OK HOOK VERIFY LIMIT REACHED verified=80
```


Fixed a live `--verify-frames --verify-frame-preview` verifier scheduling bug.
The frame verifier used to pump SDL/input events once before the reference ASM
runtime advanced, and then again between the reference and hooked candidate
runtimes.  A key pressed while the reference side was running could therefore be
delivered to the candidate for the current frame after the reference had already
reached its boundary.  That created a false one-frame input skew and visual
divergences during active play.

The generic verifier now samples input only at runtime-pair boundaries: once
before both the reference and candidate advance.  Events collected while the
reference side is running are intentionally deferred to the next pair so both
runtimes see them on the same verified frame.

Verification:

```text
python scripts/lint.py
# Lint passed for 76 Python files

pytest -q tests/test_frame_verify.py tests/test_overkill_hooks.py::test_hook_verifier_defers_live_passthrough_yield_until_after_diff tests/test_overkill_hooks.py::test_hook_verifier_live_passthrough_override_can_publish_without_frame_boundary
# 5 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 100 --max-steps 400000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=100

python scripts/play.py --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-frames --verify-frame-max 30 --verify-frame-source both
# FRAME VERIFY OK frames=30

# Programmatic deterministic key injection at frame boundaries (Right+Space,
# releases, Left, release) matched for 100 Tandy frame/timer boundaries.
```

Full `pytest -q` reached 81% with no visible failures before the sandbox
timeout, so it is not claimed as complete here.

## 2026-06-14 - Interstitial frame-script cleanup and raw status-list seeds

Continued the ASM-noise cleanup around the post-97B2 short-profile path.  This
pass deliberately stayed in the verified lifted-routine layer: it closes repeated
frame glue and raw descriptor setup blocks without naming a concrete menu/screen
or HUD widget yet.

Implemented:

- Captured oracle snapshots:
  - `artifacts/evidence/snapshot_stop_1010_d318_timed_input_loop`
  - `artifacts/evidence/snapshot_stop_1010_8517_status_cell_list_seed`
- `1010:D367 overkill_interstitial_status_cell_d367`
  - small interstitial/status cell blit helper: sets `AX=4703h`, calls `5A00`,
    zeroes `SI`, switches `DS` to `CS:95B6`, dispatches `5A6C`, then restores
    `DS` from `CS:9596`.
- `1010:D318 overkill_interstitial_timed_input_loop_d318`
  - one ASM-shaped iteration of the timed interstitial/input-wait frame script;
  - composes existing frame child hooks, far-calls `1F8F:0922`, increments
    `DS:BED8`, then either loops at `D318` or waits for the input-release bit
    before returning.
- `1010:852B overkill_status_cell_seed_852b`
  - one raw 10-byte status/list cell descriptor seed at `SS:BP`.
- `1010:8517 overkill_status_cell_list_seed_8517`
  - four-entry descriptor builder around `852B`; preserves the odd original
    call shape where the third `CALL 852B` returns to `852B` and the fourth
    descriptor is a fall-through into the same body.

Important proof detail:

- The generic bounded near-call helper cannot be used for the `8517` third
  `CALL 852B`, because the continuation equals the callee entry.  The parent
  hook therefore pushes the return word and invokes the lifted `852B` body
  directly so the same-IP call still executes once and leaves the same scratch
  stack shape.

Validation:

```bash
python -m pytest -q \
  tests/test_overkill_hooks.py::test_status_cell_seed_852b_and_list_8517_match_interpreted_asm_with_child_boundary \
  tests/test_overkill_hooks.py::test_interstitial_status_cell_d367_matches_interpreted_parent_with_child_boundaries \
  tests/test_overkill_hooks.py::test_interstitial_timed_input_loop_d318_matches_interpreted_parent_with_child_boundaries \
  tests/test_overkill_hooks.py::test_status_cell_composite_85d5_matches_interpreted_parent_with_child_boundaries \
  tests/test_overkill_hooks.py::test_status_coord_list_fill_99cd_matches_interpreted_loop \
  tests/test_overkill_hooks.py::test_frame_axis_count_9bfb_9bfe_tiny_leaves_match_interpreted_asm \
  tests/test_overkill_hooks.py::test_live_verify_replacement_hooks_have_continuation_metadata
# 7 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/snapshot_stop_1010_d318_timed_input_loop --verify-max 1 --max-steps 20 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/snapshot_stop_1010_8517_status_cell_list_seed --verify-max 1 --max-steps 20 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 200 --max-steps 400000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200

python scripts/lint.py
# Lint passed for 76 Python files
```

A full `pytest -q` run reached 83% with no displayed failures before the sandbox
timeout, so this package claims the focused tests and live verifier runs above.

Fresh profile result:

- `D318` is now a hook-covered frame-script boundary instead of 200 repeated raw
  interpreted frames.
- `8517` is hook-covered; the former `852B/852D/852E/8531/...` descriptor seed
  noise disappears behind the raw status-list builder.
- The next visible low-count cleanup targets are now `859E-8653`, `6120-613D`,
  and the setup tail around `C51D-C562`.  The larger semantic frontier remains
  `9B2E/9C01-9C6B`.

## 2026-06-14 - Status compositor and tiny frame-controller leaves

Continued the post-97B2 cleanup without entering the large `1010:9B2E` child
controller.  This pass absorbed small, bounded regions that were already exposed
by the profile and that compose existing lower-level hooks.

Implemented:

- Captured oracle snapshot: `artifacts/evidence/snapshot_stop_1010_85d5_status_cell`.
- `1010:85D5 overkill_status_cell_composite_85d5`
  - low-level status/HUD cell compositor parent around the verified
    `613E`/`615A` cursor leaves and the existing `5A6C` source-cell blit
    dispatch;
  - still a raw compositor, not a semantic HUD widget model.
- `1010:99CD overkill_status_coord_list_fill_99cd`
  - compact coordinate-list fill loop that writes `([BP+2]+8,[BP+4]+9)` word
    pairs into `ES:DI` for `CX` entries, then falls through to `99DD`.
- `1010:9BFB overkill_frame_axis_count_inc_ah_9bfb`
- `1010:9BFE overkill_frame_axis_count_inc_al_9bfe`
  - tiny `INC AH/AL; RET` leaves used inside the `9C01` frame-controller child
    before the `9C6B` jump-table dispatch.

Validation:

```bash
python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q \
  tests/test_overkill_hooks.py::test_status_cell_composite_85d5_matches_interpreted_parent_with_child_boundaries \
  tests/test_overkill_hooks.py::test_status_coord_list_fill_99cd_matches_interpreted_loop \
  tests/test_overkill_hooks.py::test_frame_axis_count_9bfb_9bfe_tiny_leaves_match_interpreted_asm \
  tests/test_overkill_hooks.py::test_status_cell_composite_85d5_matches_captured_snapshot \
  tests/test_overkill_hooks.py::test_live_verify_replacement_hooks_have_continuation_metadata
# 5 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 150 --max-steps 300000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=150; final CS:IP=1010:97B2

python scripts/profile_hotspots.py 20000 --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_191454 --top 40
# 85D5 and 99CD now appear as hook-covered call boundaries.
```

A full `pytest -q` run reached 84% with no failures displayed before the sandbox
timeout, so this package claims the focused oracle tests and live verification
above rather than full-suite completion.

Next best targets after this pass:

- classify the caller block around `1010:8517-8545` / `1010:859E-8653`, because
  `85D5` now exposes it as a likely status/HUD object-cell parent;
- classify `1010:9C01-9C6B` before lifting larger parts of `9B2E`; the new
  `9BFB/9BFE` leaves show this area counts four axis/side conditions and jumps
  through a table at `9C70`;
- keep `1010:9B2E-9C6B` as the main bounded-original frame-controller frontier
  until its internal children have a manifest.

## 2026-06-14 - Cursor stride leaves and setup/object-slot reset blocks

Classified and lifted five low-risk regions exposed by the short post-97B2
profile before entering the large `9B2E` controller.

- Added `1010:613E overkill_status_cursor_advance_613e`, the CS:95BC
  video-mode cursor advance dispatch used by status/HUD drawing glue.
- Added `1010:615A overkill_status_cursor_retreat_615a`, the inverse cursor
  retreat dispatch used by the same status draw family.
- Added `1010:C3BF overkill_reset_effect_slot_block_c3bf`, a compact-slot
  reset loop using the `DS:8D12` pointer table and `0040h` present-pointer
  stride.
- Added `1010:C3F1 overkill_reset_object_slot_block_c3f1`, the setup object-slot
  reset loop that preserves slots whose `+16` field is already `0001h`.
- Added `1010:C4E5 overkill_reset_object_slot_block_c4e5`, the sibling setup
  loop reached from `C4DB` that clears selected object-slot fields through the
  `DS:32CA` pointer table, stamps each slot from `CS:C3A2`, advances that
  source pointer by `0280h`, and falls through to `C51D`.
- Kept these as low-level lifted routines: no semantic enemy/player/HUD model
  was introduced.

Validation:

```text
pytest -q tests/test_overkill_hooks.py::test_status_cursor_613e_and_615a_match_interpreted_asm_all_modes tests/test_overkill_hooks.py::test_setup_reset_blocks_c3bf_and_c3f1_match_interpreted_asm tests/test_overkill_hooks.py::test_reset_object_slot_block_c4e5_matches_interpreted_asm
# 3 passed
```

Next likely targets from the same profile are now `1010:861B-864B` / `1010:85D5`
(status/HUD cell composition around the new cursor leaves), then the larger
`1010:9B2E-9C6B` frame-controller child and object/frontier regions such as
`1010:A4D7-A64C`, `1010:A031-A090`, and `1010:AFD8-B01C`.

## 2026-06-14 - BEC5 variant 000A non-owner no-op collision fix

Fixed the fail-fast reported from `BC45 -> BC4B -> 62F6 -> BEC5 variant 000A`
with current object `logic_id=0029h`.  The earlier lift only covered the
owner-linked fallback where `DS:[BX+30h] == BP`; the original ASM also has an
ordinary non-owner case.

- Rechecked the tail of `1010:BEC5`: after the 7/8/0C/9 table and 2/6/5 checks,
  it executes `CMP BP,[BX+30h]`; if the slot is not owner-linked, the next
  instruction is a plain `RET`.
- `_run_collision_handler_bec5_observed` now preserves that no-op contact path,
  including the live flags from the final `CMP`, instead of fail-fasting.
- Added an original-ASM-vs-lift regression for `variant=000Ah` with
  `DS:[BX+30h] != BP`, matching the newly observed collision family.

Validation:

```text
pytest -q tests/test_overkill_hooks.py::test_bec5_variant_000a_non_owner_contact_is_noop_ret_against_asm
# 1 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 100 --max-steps 200000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=100

python scripts/lint.py
# Lint passed for 76 Python files
```

Next hook clues remain the same at the high level: `1010:9B2E-9C6B` is the big
bounded-original controller inside `97B2`, while `1010:A4D7-A64C`,
`1010:A031-A090`, and `1010:AFD8-B01C` look like object/gameplay families that
should be entered with stop snapshots before semantic naming.

## 2026-06-14 - Frame effect/status glue and 97B2 frame-loop lift

Classified and lifted the next low-risk gameplay-loop glue after the allocator pass.
This pass deliberately stopped short of semantic rewrites: `9B2E` is now isolated
as the next larger controller frontier, while the finite frame wrappers around it
are Python-owned and oracle-tested.

- Added `1010:77C5 overkill_frame_effect_gate_77c5`, the per-frame
  slash/effect gate around `DS:A97A/A97C`.  It composes the existing `77F6`
  slash renderer and keeps the EGA-only `511F` page-toggle branch explicit.
- Added `1010:60A2 overkill_frame_effect_status_text_60a2`, a three-call
  status/effect glue block: `77C5`, `5F61`, then `5EDB`.
- Added `1010:97B2 overkill_frame_loop_97b2`, one verified iteration of the
  gameplay/attract frame controller.  It keeps child proof boundaries in the
  original order and intentionally runs `1010:9B2E` as bounded original for now.
- Updated verifier metadata for same-IP loop verification, coverage island
  classification, symbols, and leaf tests that need to bypass the new frame
  parents when verifying nested `5EF9`/`5EDB` boundaries directly.

Validation:

```text
python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 150 --max-steps 300000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=150; final CS:IP=1010:97B2

python scripts/profile_hotspots.py 2000 --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_191454 --top 50
# 97B2 is hook-covered; 60A2 and 77C5 child glue no longer appears as interpreted loop glue

python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q
# 248 passed
```

Next hook clues after this pass:

- `1010:9B2E-9C6B` is now the most important bounded-original child inside
  `97B2`; classify it before lifting because it appears to own input/game-state
  control rather than a pure draw or object leaf.
- After `97B2`, short profiles expose smaller transition/menu/status regions,
  especially `1010:C4E5-C51B`, `1010:613E-6159`, `1010:861B-864B`, and
  `1010:C3BF-C3E5`.
- The previous `60A2/60A5/60A8/60AB` and `77C5/77CA` glue is closed enough to
  leave alone unless a new snapshot proves an unobserved branch.

## 2026-06-14 - Object allocator hooks 7524/7573

Absorbed the smallest high-confidence next target from the remaining gameplay
hotspots: the 38h-byte slot allocators at `1010:7524` and `1010:7573`.

- Added `1010:7524 overkill_find_free_effect_slot_7524` for the compact effect
  pool allocator.  It scans from `DS:[95D8]` through `23B4..2B5A`, wraps at
  `2B5C`, writes the selected free slot back to `DS:[95D8]`, and returns
  `BX=FFFF` on exhaustion.
- Added `1010:7573 overkill_find_free_object_slot_7573` for the main gameplay
  object pool allocator.  It scans from `DS:[95DA]` through `2B5C..32CA`,
  repeats the `32CC -> 2B5C` sentinel wrap check on every iteration, writes the
  selected free slot back to `DS:[95DA]`, and returns `BX=FFFF` on exhaustion.
- Both wrappers are guarded by exact live-code signatures so later overlay reuse
  would fall back to interpretation instead of silently applying the wrong lift.
- Added direct original-ASM-vs-hook tests for wrap, found-slot, and exhausted
  cases.
- Updated hook-verifier metadata, coverage island classification, and symbols.

Validation:

```text
python -m pytest -q tests/test_overkill_hooks.py::test_effect_allocator_7524_hook_matches_original_wrap_and_exhaustion tests/test_overkill_hooks.py::test_object_allocator_7573_hook_wrapper_matches_original
# 2 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 100 --max-steps 200000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=100

python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q
# 245 passed
```

Next hook clues after this pass:

- `1010:9B2E-9C6B` is still the largest remaining interpreted region in the
  long gameplay run and should be classified before lifting.
- `1010:A490-A780` / `1010:AFD8-B01C` remain likely gameplay-object family
  frontiers, but they are larger than the allocator leaf and should be entered
  with a stop snapshot.
- `1010:77C5/77CA` plus `60A2/60A5/60A8/60AB` show up in short profiles as
  frame/status glue around already-hooked `5F61` and `5EDB`; useful, but less
  likely to reveal new object behavior.

## 2026-06-14 - BFC7 logic-0021 collision gate fix

Fixed the fail-fast reported from `artifacts/snapshot_play_tandy_20260614_202217`:
`BC4B -> 62F6 -> BEC5 variant 0005 -> BFC7 logic 0021 -> BFD2`.

- Rechecked the original bytes around `1010:BFC7`: logic id `0021h` is only a
  gate.  If `DS:2356 != 0004h`, the helper returns immediately; if
  `DS:2356 == 0004h`, the `JE` lands at `BFD7` and joins the normal
  death/transition tail.
- Removed the stale fail-fast for the `DS:2356 == 0004h` case and let it reuse
  the already lifted BFD7 path.
- Added an original-ASM-vs-lift regression test seeded from the gameplay memory
  image.  The test starts both CPUs at `1010:BFC7` with logic id `0021h` and
  `DS:2356=0004h`; the interpreted ASM and Python helper now return with
  identical register state and full memory.

Validation:

```text
pytest -q tests/test_overkill_hooks.py::test_bfc7_logic_21_gate_four_joins_normal_death_tail_against_asm
# 1 passed

python scripts/lint.py
# Lint passed for 76 Python files

pytest -q
# 243 passed
```

Next hook clues from the reported coverage:

- `1010:7524-7595`, hottest at `757A`, is probably the best small next target.
  The project already has `_find_free_object_slot_7573` and `_find_free_effect_slot_7524`
  helpers, so this region looks like allocator logic that can be promoted into
  exact hooks with focused oracle tests.
- `1010:9B2E-9C6B` is the largest remaining interpreted region by hits; it
  should be classified before lifting because it may be UI/status or scripted
  gameplay bookkeeping rather than a pure object routine.
- `1010:A490-A780` and `1010:AFD8-B01C` look like gameplay-object family
  frontiers and are better candidates after the allocator leaf is closed.

## 2026-06-14 - Object behavior B24D absorption

Continued the Tandy + AdLib gameplay-loop absorption from
`artifacts/snapshot_play_tandy_20260614_191454`.  The next hot unlifted object
family path was `EFAE -> B24D -> 5E42`.

- Captured evidence snapshot `artifacts/evidence/snapshot_stop_1010_b24d_behavior`.
- Added `1010:B24D overkill_object_behavior_b24d` for the observed object-family
  steering/overlap prelude.
- The hook composes the already verified runtime-patched `1010:5E42` steering
  helper, mirrors the signed/unsigned reference-box checks against `DS:237E`
  and `DS:2380`, and lands on the existing `AD5A`/`ADC9` motion tails.
- The rare overlap side-effect helper `1010:9E19` remains a bounded original
  child call from inside B24D; it should be lifted independently if it becomes a
  real hotspot.
- Updated leaf-hook tests that intentionally target nested `5E42`/`61C7`
  boundaries to disable the newly absorbed `B24D` parent, so those tests still
  exercise the leaf boundary itself.

Validation:

```text
python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/snapshot_stop_1010_b24d_behavior --verify-max 1 --max-steps 20 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=1; final CS:IP=1010:AD5A

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 20 --max-steps 20000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=20

python scripts/profile_hotspots.py 600000 --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_191454 --top 35
# B24D now appears as hook-covered; interpreted B24D body is gone

python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q
# 242 passed
```

## 2026-06-14 - Object behavior B86D absorption

Continued from the Tandy + AdLib gameplay snapshot
`artifacts/snapshot_play_tandy_20260614_191454`, where the current code had
already absorbed several previously unknown frame/game-state regions and the
remaining interpreted hotspot was `1010:B86D-B8EF`.

- Added `1010:B86D overkill_object_behavior_b86d` for the observed logic-id
  `001Dh` object-family behavior.
- The hook covers the hot `B885 -> B729 -> 5DB2 -> BC4B` setup path, the
  adjacent `B8B0 -> BC4B` object-X drift path, and the later
  `B8F8 -> 5E1B -> 5E42 -> BC4B` edge-steering path.
- The hook lands on the existing `1010:BC4B` postmove/collision boundary instead
  of composing that tail, keeping ownership with the verified collision helper.
- Added evidence snapshots:
  `artifacts/evidence/snapshot_stop_1010_b86d_behavior`,
  `artifacts/evidence/snapshot_stop_1010_b8b0_behavior`, and
  `artifacts/evidence/snapshot_stop_1010_b86d_b8f8_edge`.
- Added a full-memory regression for the observed B86D paths.  The B8B0
  evidence state is rewound only to the exact `B86D` entry IP because its
  preceding B86D setup instructions are compare-only.

Validation:

```text
direct original-vs-hook B86D oracle check against both evidence snapshots
# CPU/register state and full memory matched at 1010:BC4B

python scripts/profile_hotspots.py 300000 --snapshot artifacts\snapshot_play_tandy_20260614_191454 --top 30
# B86D now appears as hook-covered; interpreted B86D..B8EF body is gone
```

## 2026-06-14 - Bootstrap LZEXE tail contract correction

- Tightened the `1C43:0069` bootstrap LZEXE hook so the `AL==0` terminator
  path now lands on the oracle continuation with `AX=0000` and `CX=0003` at
  `1C43:00FC` instead of preserving the entry `AH` byte and dropping the
  residual count.
- Added a regression test against `artifacts/evidence/snapshot_stop_1c43_0069`
  that differential-verifies the `1C43:0069` hook and pins the exact `00FC`
  register snapshot.
- Raised bootstrap verification headroom to `asm_max_steps=1_000_000` in the
  play/CLI/headless verifier setup, and added a matching `23AD:0069`
  regression on `artifacts/evidence/snapshot_stop_23ad_0069` so the second
  nested stub does not trip the old 500k ASM ceiling.
- Fixed the loaded AdLib note/frequency helper at `2032:024F` by matching the
  original `mov bl,[si+0749]` register side effect and the `push ax` / `pop ax`
  pair around the first YM3812 write.  Added a direct original-vs-hook
  regression using the static runtime bundle memory image.

Validation:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\verify_hooks_headless.py --snapshot artifacts\evidence\snapshot_stop_1c43_0069 --verify-max 1 --max-steps 500000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=1
```

## 2026-06-14 - Maintenance cleanup pass

- Renamed the headless frame dump tool from the old CGA-only script name to
  `scripts/render_frame.py`.  The tool now clearly owns CGA, EGA, and Tandy
  snapshot rendering, while internal CGA-specific helper names remain
  mode-specific where appropriate.
- Updated imports and documentation references to the new frame-render tool; no
  legacy module alias was kept.
- Added `scripts/clean.py`, a dependency-free cleanup helper for Python caches,
  package build outputs, local Nuked-OPL3 extension artifacts, and optional
  unpromoted generated capture folders.
- Expanded `.gitignore` for package build outputs, default headless frame dumps,
  and Nuked-OPL3 generated C/object/linker files.
- Tightened `scripts/lint.py` with a legacy-reference guard so old moved module
  names such as the former frame renderer, old hook-verifier module path, and
  obsolete replacement-file naming do not creep back into Python/Markdown files.
- Cleaned stale generated `__pycache__` files from the packaged tree.
- Updated Nuked-OPL3 build docs to describe the explicit in-place CFFI build;
  removed stale setup.py wording.

Validation:

```text
python scripts/lint.py
# Lint passed for 75 Python files

python -m pytest -q
# 232 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_maintenance_clean
# reached 1010:D007; steps=19847
```

## 2026-06-14 - Repository cleanup and vendored Nuked-OPL3

- Vendored the optional `nuked_opl3/` CFFI package directly into the repository
  from the supplied archive, keeping only source files, vendor C core, README,
  and LICENSE.  Prebuilt `.pyd` files and `__pycache__` were intentionally not
  imported.
- Updated `.gitignore` so locally built `_opl3_cffi*` extension artifacts stay
  out of version control.
- Updated `pyproject.toml` package discovery so `dos_re`, `overkill`, and the
  vendored `nuked_opl3` package are explicit.
- Updated AdLib documentation: FM PCM no longer depends on an external package;
  build the vendored binding with `python -m nuked_opl3._ffi_build` after
  installing the optional `[adlib]` dependency.
- Added `docs/architecture/third_party.md` and package-boundary rules for
  vendored components.  `nuked_opl3` must not import `dos_re` or `overkill`.
- Extended `scripts/lint.py` to parse/check the vendored package while allowing
  the generated `_opl3_cffi` extension to be absent before local build.
- Promoted the two remaining top-level `artifacts/snapshot_play_*` fixtures used
  by tests into `artifacts/test_oracles/` with descriptive names, then removed
  the stale live snapshot directories from the repository.

Validation:

```text
python scripts/lint.py
# Lint passed for 74 Python files

python -m pytest -q
# 232 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_vendor_clean
# reached 1010:D007; steps=19847
```

## 2026-06-14 - Documentation ownership refactor

Separated documentation by the same role boundary as the code packages.

- `docs/dos_re/` now contains only reusable DOS reverse-engineering methodology.
- `docs/overkill/` owns OVERKILL-specific archaeology, runtime findings, island
  truth tables, status, source-port design, and performance notes.
- `docs/architecture/` owns cross-package dependency and boundary rules.
- Added `docs/README.md` as the documentation map.
- Moved root `RUN_STATUS.md` to `docs/overkill/run_status.md`.
- Moved root `PERFORMANCE_INVESTIGATION.md` to
  `docs/overkill/performance_investigation.md`.
- Added a lint guard preventing new loose durable docs under `docs/` and
  preventing root status/performance docs from reappearing.

Validation:

```text
python scripts/lint.py
python -m pytest -q
python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_docs_refactor
```

## 2026-06-14 - Main-menu AdLib runtime hook lifting

Reduced the remaining main-menu slowdown caused by interpreting the loaded
optional AdLib driver at `2032:*` on every timer IRQ.  This pass targets the
interactive/menu phase rather than cold-start bootstrap.

- Added a `2032:0063` top-level loaded-AdLib timer-tick hook.  It preserves the
  original register-save contract, reentrancy byte `2032:0062`, global countdown
  `2032:000D`, and the nine 32-byte channel records at `05A9..06A9`, but routes
  each channel through smaller lifted boundaries.
- Added a `2032:00CD` channel-idle fast path for the common main-menu case where
  the channel is active but the global countdown has not expired and both
  modulation helpers are disabled.  Non-idle note/command advancement still
  falls back to the original driver body.
- Added `2032:0557` YM3812 register/value write hook.  It emits the same
  `388h/389h` writes for Nuked-OPL3, models the PIT/speaker delay side effects,
  but skips the busy delay instruction stream.
- Added disabled fast paths for `2032:02C9` and `2032:02F6`, the two per-channel
  modulation helpers that often only clear/test AL and return.
- Classified the loaded `2032:*` optional sound driver segment as the `sound`
  island instead of leaving it as `unknown`.

Snapshot measurement from `snapshot_play_tandy_20260614_134931`:

```text
100 delivered INT 08h ticks, with previous hooks disabled: 42,599 interpreted instructions
100 delivered INT 08h ticks, after this pass:              10,365 interpreted instructions
```

Validation:

```text
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 225 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_test
# reached 1010:D007; steps=21,499
```

## 2026-06-14 - Bootstrap LZEXE and AdLib probe lifting

Reduced pure-original Tandy+AdLib cold-start ASM in the dynamic/init layer.

- Added `overkill/bootstrap_lzexe.py` and hooks for the
  observed temporary nested LZEXE/self-relocation stubs at `1B65:0069`,
  `1C43:0069`, and `23AD:0069`. These hooks lift only the hot bitstream copy
  loop and stop at the original relocation/final-transfer tail (`00FC`), keeping
  the bootstrap/runtime boundary explicit.
- Classified the observed temporary unpacker segments as `bootstrap` rather than
  `unknown`; they are not source-port runtime islands.
- Added `overkill/sounds/adlib_driver.py` and a
  `2032:04E9` hook for the loaded Sound Images AdLib/YM3812 hardware probe.
  The hook stays registered at the exact boundary but now defers to the
  interpreted oracle because the remaining stack/branch behavior is still
  evidence-sensitive.
- Tightened `2032:0557` so the helper exits with `AL` copied from `AH`
  (`0001h -> 0000h`, `6004h -> 6060h`) and preserves the `056E` scratch word
  expected by the verifier.
- `scripts/profile_hotspots.py` now accepts `--sound pc|adlib|roland` and uses
  the canonical compact PSP tail builder, so profiling can match `play.py
  --video tandy --sound adlib`.

Validation:

```text
python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_after_hooks_final
# reached 1010:D007; steps=21,499
# memory_1mb.bin SHA256 is unchanged: c9bad83826f22bd144a7dcb3d98d84aaaf732b03527f8702dd4d2b68da57a476
# CPU snapshot is byte-equivalent to the previous interpreted canonical bundle

python scripts/lint.py
# passed

python -m pytest -q
# 225 passed
```

Before this pass, the canonical static bundle reached `1010:D007` in 1,245,977
steps before the LZEXE lift and 95,846 steps after the LZEXE lift alone. With
the AdLib probe lift as well it now reaches the same runtime image in 21,499
steps.

# RUN_STATUS update - zombie cleanup

- Removed one-off diagnostic wrapper/probe scripts that used hardcoded local paths
  or duplicated canonical CLI commands: `trace_start.py`, `make_trace_coverage.py`,
  `make_runtime_snapshot.py`, `run_until_checkpoint.py`, `check_intro_sound_poll.py`,
  `probe_sound_issue.py`, `trace_timer_isr.py`, and `probe_ega_page_offsets.py`.
- Removed deprecated interactive/verification CLI compatibility options:
  `scripts/play.py --fps` and `--verify-full-memory` in both `play.py` and
  `overkill.cli`.  Timing is controlled by `--game-hz`; full-memory hook
  verification remains the default and `--verify-fast-ranges` is the explicit
  opt-out.
- Removed stale hook-name aliases from `overkill.hooks` and updated
  tests to use canonical names: address-suffixed packed/checksum hooks, shared
  layer-sprite names, shared coordinate names, and the `61C7` counter boundary.
- Removed the obsolete `asset_codecs/startup_graphics.py` compatibility shim;
  startup graphics materialization now has a single owner in
  `rendering/startup_graphics.py`.
- Extended `scripts/lint.py` to reject hardcoded local workspace paths in future
  diagnostic scripts, so one-off `/mnt/data/...` probes do not creep back in.

Validation: `python scripts/lint.py` -> 68 Python files; `python -m pytest -q` -> 225 passed.

# RUN_STATUS update - static runtime bundle materializer

- Added `overkill/static_runtime_bundle.py`.
- Added `python -m overkill.cli static-runtime-bundle` to run the original
  bootstrap with compact `--video/--sound` selectors, stop at an inner-runtime
  frontier, and write a canonical initialized snapshot plus
  `static_runtime_bundle.json`.
- Cold-start `trace` and `snapshot` now accept `--video`, `--sound`, and explicit
  `--dos-args` override, so diagnostics can use the same canonical compact tail
  as `scripts/play.py`.
- Materialized Tandy + AdLib bundle from original files reached `1010:D007` in
  1,245,977 steps.  Recorded checks: command tail `0D 02 41`, `CS:95BC=0002`,
  `DS:0055=0001`, `DS:95DA=2B5C`, nonzero `2032:*` optional driver area.
- New tests: `tests/test_static_runtime_bundle.py`.

Validation commands run:

```bash
python -m pytest tests/test_static_runtime_bundle.py -q
python -m overkill.cli static-runtime-bundle assets/OVERKILL \
  --game-root assets --video tandy --sound adlib \
  --steps 3000000 --trace-tail 20 \
  --out-dir artifacts/static_runtime_bundle
```

## 2026-06-14 bootstrap/static-runtime boundary policy

- Added `docs/overkill/bootstrap_static_boundary.md` to make the project rule explicit:
  original startup/bootstrap is an oracle and extraction layer, not the target
  source-port gameplay architecture.
- Added `overkill/bootstrap_boundary.py` as an importable
  manifest for the current boundary: canonical original inputs, noncanonical
  generated files, bootstrap islands, known inner-runtime frontiers, compact PSP
  tails, required initial state, and derived asset classes.
- Added `overkill-port bootstrap-boundary` /
  `python -m overkill.cli bootstrap-boundary` to write the current manifest
  as JSON without executing the game.
- Updated design/methodology/island docs to preserve the rule that
  `assets/OVERKILL` and `assets/OVERKILL.EXE` are the only canonical inputs;
  unpacked images and overlay blobs are deterministic build/evidence artifacts
  only.

Validation: `python scripts/lint.py`; `python -m pytest tests/test_bootstrap_boundary.py tests/test_core.py tests/test_overkill/hooks.py -q` -> 212 passed.

## 2026-06-14 Nuked-OPL3 AdLib audio backend

- Added an optional SDL-side AdLib audio backend that consumes the original
  OVERKILL YM3812 register stream from ports `388h/389h` and renders it through
  the vendored `nuked_opl3.OPL3` binding when its CFFI extension is built.
- `DOSMachine` now exposes `set_adlib_callback(reg, value, emit_current=True)`,
  mirroring the existing PC-speaker callback shape while keeping AdLib detection,
  register state, snapshots, and headless tests deterministic.
- `scripts/play.py --sound adlib` now wires that callback to the SDL viewer.
  `--adlib-audio off` leaves the original driver active but disables PCM output.
- If the vendored `nuked_opl3` extension is not built, the game still runs the original
  AdLib driver and records/register-forwards writes; the viewer reports a clear
  status message and stays silent instead of crashing.
- Validation: `python scripts/lint.py`;
  `python -m pytest tests/test_core.py tests/test_overkill/hooks.py -q` -> 209 passed.

## 2026-06-14 Edrax level-select fire fix

- Fixed `1010:D445` selector hook behavior for FIRE on selector value zero.
- Original ASM at `1010:D46F` is `TEST byte [98BE],10h; JZ D445; RET`, so it
  accepts FIRE for every `DS:BEDA` value.  The lifted hook had added an
  incorrect `BEDA != 0` guard while making the loop UI-yieldable.
- `DS:BEDA == 0` is the first planet slot (Edrax), so the bug only blocked
  Edrax while all other planets still started normally.
- Added a regression case comparing interpreted ASM and hook for
  `buttons=10h, BEDA=0`.

Validation:

```text
python scripts/lint.py
python -m pytest tests/test_core.py tests/test_overkill/hooks.py -q
# 206 passed
```


## 2026-06-14 AdLib compact-tail and OPL probe fix

- Added `overkill.launch.build_command_tail(video, sound)`.
  `--video tandy --sound adlib` now passes compact selector bytes `0D 02 41`:
  Tandy video in `PSP:82`, AdLib driver selector `A` in `PSP:83`.
- Added a narrow YM3812/AdLib port model for `388h/389h`: selected-register
  tracking, register storage, and timer-status bits for the original presence
  probe.
- `DS:0055` can now become `1`; in that mode `1010:06E5` interprets the original
  ISR body so the far call through `2032:0000` runs before the shared timer work.
- Validation: `python scripts/lint.py`; `python -m pytest tests/test_core.py tests/test_overkill/hooks.py -q` -> `206 passed`.

## 2026-06-14 text-mode launcher and BIOS console support

Investigated the missing original startup screens:

- `assets\OVERKILL` remains the large MZ/container used for normal gameplay.
- `assets\OVERKILL.EXE` is a separate text-mode splash/launcher program.  It
  prints the Tech-Noir/registered-version text and the graphics adapter selector.
- The selector was invisible because the VM only kept DOS stdout as a log and
  the SDL viewer always decoded B800h as graphics.

Implemented narrow text-mode support:

- BIOS text modes 00h/01h/02h/03h/07h now track cursor row/column and clear text
  pages.
- BIOS teletype and character writes update B800h/B000h text memory.
- DOS console output (`INT 21h/AH=02h`, `09h`, stdout/stderr writes, and AH=01h
  echo) paints the active text page when a text mode is active.
- SDL can render 80x25 text pages with integer scaling and fixed aspect.
- Graphics presenter hooks mark text mode inactive so Tandy/CGA/EGA gameplay is
  not mistaken for text just because the last BIOS mode is still 03h.
- `INT 10h AH=12h BL=10h` now reports a colour EGA/VGA-style adapter so the
  launcher does not fall into its "must have colour graphics" error path.

Evidence:

```text
assets\OVERKILL.EXE with console_input_fallback=None now blocks at:
  'OverKill'
  Please select video mode:
    1.  CGA 4 colour
    2.  EGA/VGA 16 colour
    3.  Tandy 1000 series
```

AdLib status:

- The original docs mention `/A`, but ASCII switches are launcher/outer
  semantics.  The inner game module reads raw compact PSP bytes, so passing
  ASCII `/A` directly to `assets\OVERKILL` is not a valid AdLib selection.
- Probes through the current Tandy menu startup with several compact selector
  bytes produced no OPL `388h/389h` writes and left `DS:0055` clear.  The proven
  sound path remains the PC-speaker timer ISR.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 211 passed, 0 failed
```

Follow-up correction:

- `scripts/play.py` starts the inner `assets\OVERKILL` game path with
  `text_mode_active=False`; the first visible inner-game screen is graphical
  even though the BIOS mode byte may still be 03h.
- Older snapshots without `text_mode_active` metadata now load as graphics
  active by default.  A real `INT 10h` text-mode switch, such as the F9 boss key,
  still enables text rendering.
- `1010:073C` keeps its hot lifted fast path, but if F9 arms the longer
  platform/text service branch (`DS:9907 == 1`) the wrapper relinquishes that
  branch back to original code instead of trying to force it to return inside
  the hook.
- `scripts/play.py` also recognizes the `1010:55F1` menu select/fire wait as an
  interactive yield boundary, so level-select style screens can receive input
  and F12 snapshot requests can be processed while they are waiting.

---

# 2026-06-13 artifact cleanup checkpoint

Repository cleanup pass after the hook-integrity work.  The runtime/code
behavior was not intentionally changed.

Removed/generated-pruned material:

- old root `artifacts/snapshot_play_*` gameplay snapshots that were not regression fixtures;
- old root `artifacts/play_*` captures that were not regression fixtures;
- `artifacts/tmp_*` stop/verify scratch snapshots that were not regression fixtures;
- generated `artifacts/frame_verify/` PNG/VRAM diff dumps;
- non-test, stale `artifacts/evidence/*` probe snapshots;
- root scratch helpers `dump_at.py` and `headless_coverage.py`.

Kept durable artifacts only:

- `artifacts/test_oracles/*` used by regression tests, including promoted former root snapshots;
- evidence snapshots still referenced by regression tests;
- `artifacts/evidence/hook_verify_tandy_20260613_190326` as the current
  headless hook-verifier seed;
- `artifacts/hook_coverage_cache.json`;
- `artifacts/README.md` with the retention policy.

Validation after cleanup:

```text
python -m pytest -q
185 passed

python -m compileall -q dos_re overkill tests scripts
OK

python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 --verify-max 1000 --fast-ranges
OK HOOK VERIFY LIMIT REACHED verified=1000
```

Size changed from roughly 183 MB to roughly 30 MB while keeping all regression oracles.

---

## 2026-06-13 Tandy hook integrity / C054 cleanup pass

Continued from the `1010:BC4B overkill_object_postmove_bc4b` full-memory
divergence at call 3 on `artifacts\snapshot_play_tandy_20260613_190326`.

Results:

- Added `scripts/verify_hooks_headless.py`, a pygame-free live hook verifier for
  snapshot runs.  It mirrors `play.py --verify-hooks` but can run in CI/minimal
  shells and automatically disables non-CGA interactive hooks such as `1010:58DF`
  for Tandy/EGA snapshots unless explicitly requested.
- Refactored the duplicated `C054:C12D` effect-spawn tail into
  `_run_c054_c12d_effect_spawn_tail`.  The helper preserves the visible dead
  stack scratch from `PUSH BX`, `PUSH BP`, `CALL 7420`, and decrements
  `DS:A47E`, so this is cleanup only, not a behavior change.
- Removed temporary `tmp_*.py` debugging scripts from the working tree after the
  reusable headless verifier replaced them.

Verification:

```text
python -m pytest -q
# 185 passed
python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260613_190326 --verify-max 9000
# HOOK VERIFY LIMIT REACHED verified=9000, no divergence
python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260613_190326 --verify-max 10000 --fast-ranges
# HOOK VERIFY LIMIT REACHED verified=10000, no divergence
```

Note: a full-memory 10k run was attempted too, but it did not finish within the
available sandbox timeout after passing the 9k checkpoint without divergence.

## 2026-06-14 original asset source switch

Switched active runtime/test/script defaults from generated convenience files to
the original OVERKILL assets:

- executable/container: `assets\OVERKILL`
- companion splash/loader data: `assets\OVERKILL.EXE`

Removed generated assets:

- `assets\OVERKILL.UNLZEXE.EXE`
- `assets\OVERKILL.OVERLAY.BIN`

Notes:

- `assets\OVERKILL` is itself an MZ executable with the 467,649-byte overlay
  appended, so the runtime now lets the original unpack/bootstrap path produce
  the in-memory game image.
- `create_runtime()` keeps `OVERKILL.UNLZEXE.EXE` as a legacy alias only when
  that generated file is absent, mapping it to sibling `OVERKILL` so old
  snapshots/commands can still be loaded.
- The original startup path exposed two narrow BIOS/port details that the
  generated file hid: INT 10h/AH=05h active display page selection, and
  monochrome status port `03BAh` polling with bit `80h`.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 207 passed, 0 failed
headless Tandy original-container smoke with --verify-hooks --verify-require-metadata --verify-max 50
# HOOK VERIFY LIMIT REACHED verified=50, no divergence
```

## 2026-06-13 strict hook verifier cold-start cleanup

Followed up on `scripts\play.py --verify-hooks --verify-stop-on-diff` after
full-memory verification became the default.

Fixes:

- `HookVerifier._clone_runtime()` now copies `DOSMachine.console_input_fallback`.
  Interactive play sets this to `None`; the ASM oracle clone was accidentally
  reverting to the default Esc fallback and producing a false DOS/state diff at
  `1010:0FE4`.
- `1010:450C` verifier metadata now treats the lifted routine as the whole
  4-plane list parent ending at `44AA`, not as a single-block loopback to
  `450C`.
- `1010:450C` now preserves the dead-stack scratch word left by the original
  `CALL 44D7` / `RET` path (`SS:SP-2 = 450F`), which full-memory verification
  observes.
- Added verifier metadata for already-understood helpers `41A6`, `41DA`,
  `50C9`, and `58DF`.
- `1010:58DF` now self-disables for non-CGA modes before touching stack,
  registers, or memory.  The previous guard happened after setup side effects,
  which made raw Tandy all-hooks verification diverge.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 185 passed, 0 failed
headless Tandy cold start with command_tail=(0D,02), --verify-hooks, --verify-require-metadata, --verify-max 500
# HOOK VERIFY LIMIT REACHED verified=500, no divergence
```

## 2026-06-13 hook verifier full-state default

Changed live hook verification so full memory comparison is the default instead
of an opt-in mode.  The old named-range verifier can still be requested with
`--verify-fast-ranges` for profiling/debug sessions, but normal
`--verify-hooks` should now catch object/gameplay state divergence immediately
even when the changed byte is not in CS/video/stack helper ranges.

Also broadened DOS/BIOS/runtime-side comparisons to include allocator state,
open file metadata/data, keyboard queues, text output, video/timer counters, and
speaker/port tracking.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 185 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m overkill.cli continue-snapshot assets\OVERKILL.UNLZEXE.EXE artifacts\snapshot_play_tandy_20260613_181804 --game-root assets --steps 50000 --verify-hook 1010:BC45 --verify-hook 1010:BC4B --verify-stop-on-diff --verify-max 20 --out-dir artifacts\tmp_verify_full_memory_smoke
# HOOK VERIFY LIMIT REACHED verified=20, no divergence
```

## 2026-06-13 BEC5 second-counter collision tail fix

Investigated `artifacts\snapshot_play_tandy_20260613_181804`, where enemies
appeared to survive longer than the reference.

Findings:

- Frame verification diverged at frame 42.
- The first gameplay-state difference was `DS:2078`: reference decremented the
  linked counter from `03` to `02`, while the candidate left it at `03`.
- A watchpoint showed the reference write happened at original `1010:BFFE`,
  inside the shared `BFC7` death/transition tail.
- The lifted `BEC5` variant-2, `BEDC=0` path handled the `BF46` "second counter
  zero" branch by leaving `IP=BF46`.  That is not safe inside the composed
  `BC45/BC4B` parent path because the parent unwinds and overwrites the
  continuation.  The original `BF46` branch jumps to `BFC7`, so the lift must
  run the BFC7 tail inline.

Fix:

- `BEC5` now routes the observed second-counter-zero path into the shared BFC7
  tail, matching `BF46 -> BFC7`.
- Added a focused regression for the exact linked-counter decrement at
  `DS:2078`.
- Hook verification now defaults to full-memory comparison, so object/counter
  state is checked even when it lives outside the old named ranges.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 184 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\play.py --snapshot artifacts\snapshot_play_tandy_20260613_181804 --verify-frames --verify-frame-max 60 --verify-frame-source both
# FRAME VERIFY OK frames=60
```

## 2026-06-13 interactive Tandy timer ordering guard

Investigated a hidden level-start issue where the initial enemy sequence played
but the next level phase did not appear to continue in interactive Tandy play.

Findings:

- Long Tandy frame verification from
  `artifacts\test_oracles\snapshot_play_tandy_20260611_152751` stayed clean
  through 500 frames, so the deterministic hooked runtime still matches the ASM
  frame oracle at that level-start snapshot.
- The interactive SDL path had one extra source of timer mutation that the frame
  verifier does not exercise: `present_hook` could call
  `AsyncTimerIrqDriver.poll()` before the normal `1010:0679` frame wait.  If that
  IRQ advanced `CS:[066B]`, the later `0679` hook could return immediately
  instead of delivering the expected frame ISR work at the timer boundary.

Fix:

- Removed async IRQ polling from the presenter boundary.  Async IRQs still run
  in explicit retrace/menu/input wait loops where there is no normal `0679`
  frame wait to service sound.
- After every `0679` timer boundary, re-anchor the async IRQ scheduler by one
  full OVERKILL frame (`2` PIT ticks) instead of using the raw number of ISR
  ticks that happened to run inside that hook.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 171 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 300 --verify-frame-source both
# FRAME VERIFY OK frames=300
```

## 2026-06-13 live frame verifier preview

Added an interactive preview mode for frame verification.

Behavior:

- `python scripts\play.py --verify-frames --verify-frame-preview` now launches
  the normal SDL viewer and publishes the candidate runtime while each frame is
  compared against the reference ASM runtime.
- Keyboard input is delivered to both runtimes before frame boundaries, so the
  verifier can be played like `--verify-hooks`.
- With live preview and the default `--verify-frame-max 60`, the verifier treats
  the run as unbounded so the window does not close almost immediately.  Pass an
  explicit `--verify-frame-max N` for a bounded live run.
- The old "open compare image on divergence" behavior is now
  `--verify-frame-preview-on-diff`.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 173 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 5 --verify-frame-source both
# FRAME VERIFY OK frames=5
```

## 2026-06-13 hook verifier throughput pass

Improved `--verify-hooks` throughput without changing verifier coverage.

Follow-up after an interactive `play.py --verify-hooks --verify-stop-on-diff`
stall report:

- Headless cold-start verification reproduced a real verifier oracle problem:
  raw interpreted ASM for `1010:0679` can spin forever at the timer wait because
  the original busy-loop depends on IRQ0 advancing `CS:[066B]`.
- `HookVerifier._run_asm_to_target` now recognizes the original `0679/067F`
  timer wait and delivers the real installed OVERKILL INT 08h handler
  (`1010:06E5`) when `CS:[066B] == 0`.  This is not a synthetic fallback; it is
  the same game ISR the original wait loop is expecting.
- `scripts/play.py` now passes a verifier progress callback so the SDL status
  line shows the current hook being verified during long oracle runs.

Changes:

- `HookVerifier._clone_runtime` now copies the current memory image directly
  instead of allocating and zeroing a fresh full memory buffer before copying.
- `HookVerifier._range_diff` now uses a C-level `memoryview` equality check for
  identical ranges, and only walks bytes when a range actually diverges.
- Added a regression test proving the optimized range diff still reports a
  clean match, exact differing-byte count, and first differing address/value.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 171 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m overkill.cli snapshot assets\OVERKILL.UNLZEXE.EXE --game-root assets --steps 2000000 --verify-hooks --verify-max 1000 --out-dir artifacts\tmp_verify_hooks_cold_final
# HOOK VERIFY LIMIT REACHED verified=1000
```

Benchmark from `artifacts\snapshot_play_tandy_20260612_151523` with
`--verify-hooks --verify-max 200`:

```text
before: ~4583 ms
after:  ~574 ms
```

## 2026-06-12 PC speaker timing cadence fix

Investigated two sound-related Tandy snapshots:

- `artifacts/snapshot_play_tandy_20260612_151420`: level-select/menu state after
  pressing `D`.
- `artifacts/snapshot_play_tandy_20260612_151523`: gameplay state where Space
  produced firing sound but no visible projectile.

Findings:

- Both snapshots have the optional far sound-driver flag disabled
  (`DS:0055 == 0`), so the observed speaker writes come from the always-run
  timer helper path (`1010:06E5 -> D50E`), not the `[0055] == 1` far sound
  branch at `2032:0000`.
- Old synthetic timer versus new real-ISR timer produced the same video CRC and
  sampled object-table state after the Space input.  The "sound but no
  projectile" state therefore is not introduced by the PC speaker ISR change;
  it remains a gameplay/input-state investigation target.
- The sound-duration issue did expose a pacing mismatch: OVERKILL programs PIT
  divisor `0x4000`, so the ISR cadence is about `72.8 Hz`, and the `0679` wait
  normally releases every two ISR ticks, about `36.4 Hz`.  The interactive
  player default was still `30 Hz`, stretching timer-driven sounds by roughly
  20%.

Fix:

- `CPU8086.timer_ticks_elapsed` records how many real ISR ticks the `0679` hook
  delivered before `CS:066B` advanced.
- `scripts/play.py` now paces gameplay from PIT-tick units rather than assuming
  one synthetic frame tick.
- Default `--game-hz` is now `36.4`, matching the original effective timer
  cadence; internally the pacer runs at `--game-hz * 2` and sleeps for the
  delivered ISR-tick count.

Verification:

```text
python scripts\run_tests.py
# 141 passed, 0 failed
python scripts\play.py --snapshot artifacts\snapshot_play_tandy_20260612_151523 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
```

Note: `snapshot_play_tandy_20260612_151420` times out in the reference frame
verifier after frame 1 because it is in an input/menu wait path at `1010:D439`.

## 2026-06-12 AC97 object-slot scan lift

Absorbed the hot `1010:AC97` scan from
`artifacts/snapshot_play_tandy_20260612_192438` into
`overkill_object_slot_scan_ac97`.

Findings:

- The slowdown is a read-only gameplay object-slot loop body, not asset-codec
  work.
- It walks 35 records at `DS:23B4` with a `0038h` stride, one slot per hook
  call.
- It skips empty records and records with `+24h == 1` or `+20h == 1`.
- It performs the observed signed Y/X window checks and the `SS:[BP+14]`
  compare before advancing `BX/CX` and re-entering `AC97`.

Status:

- Hook lifted.
- Regression test added against `artifacts/evidence/ac97_stop`.

## 2026-06-12 BCB1 clamp leaf lift

Lifted the hot `1010:BCB1` clamp leaf from the BC4B post-move path.

Findings:

- The routine only clamps `SS:[BP+4]` into `0..00C0h`.
- It is a repeated leaf reached from the `BC4B` post-move path.
- The replacement returns to the `BC4E` continuation just like the original.

Status:

- Hook lifted.
- Regression test added against `artifacts/evidence/bc4b_stop`.

## 2026-06-12 BC4B post-move call-site lift

Absorbed the full hot `1010:BC4B` post-move call-site from the same gameplay
snapshot.

Findings:

- The block clamps Y, applies the X bounds, performs the BCCB contact check,
  folds the observed AA71 contact-window helper including the AAAB -> AA44
  upper tail, runs the optional BFC7 death tail, does the 9E69 bookkeeping,
  and finishes with the 62F6 overlap scan.
- The remaining 62F6 early exit for signed `SS:[BP+2] < 0x20` preserves the
  compare flags and incoming `BX`; it does not fall through to the empty-scan
  sentinel.
- The call-site was the last large interpreted block in that path.
- The hook now returns to the outer caller after completing the whole helper.

Status:

- Hook lifted.
- Regression test added against `artifacts/evidence/bc4b_stop`.

## 2026-06-12 AA71 upper contact tail lift

The same BC4B snapshot also hit the higher `1010:AA71` branch that survives
the signed X guard and then takes the `AAAB -> AA44` success tail.

Findings:

- The helper reuses the `SS:[BP+2] + 18h` compare against `DS:237E`.
- The path clears carry and returns without mutating object state.
- The negative X escape now also unwinds the `BCF9` return word after
  delegating to the shared `AA46` helper, matching the original call stack.
- The remaining unobserved AA71 branches stay fail-fast.

Status:

- Lifted into the shared contact-window helper.
- Regression test added against `artifacts/evidence/next_frontier_probe_4`.

## 2026-06-12 BFC7 shared C054 call for logic 003B

`snapshot_play_tandy_20260612_223501` reached `BC4B -> 62F6 -> BEC5 third counter zero -> BFC7` with `logic_id=003Bh`.  The original trace shows this is not a new bespoke branch: `BFC7` calls the shared `C054` selector before the state transition, and `003Bh` simply falls through to the default `AX=A4E4h` selector.  `C01B` then overwrites the flags with the `DS:98C0` compare and `C027` overwrites `AX` with the original logic id.

Status:

- `BFC7` now calls the shared lifted `C054` selector instead of whitelisting only `0012h/002Bh/0031h`.
- `003Bh` completes the same death/transition tail without decrementing `DS:A47E`.
- Regression test added for the `003Bh` path with `DS:98C0 != 0`.

## 2026-06-12 BFC7 no-counter branch lift

The `BFC7` death/transition tail now covers the current observed `0012h`,
`002Bh`, and `0031h` branches from the same BC4B snapshot.

Findings:

- Those branches take the same state transition as the verified death tail.
- None of them decrement `DS:A47E`.
- The replacement now keeps that family in the observed no-counter path instead
  of failing fast.

Status:

- Lifted into the shared collision tail.
- Regression tests cover the three observed logic ids.

## 2026-06-12 BD17/C054 dispatcher lift

The same BC4B tail also reaches `1010:BD17`, whose `C054` dispatcher now
selects the observed `0000h/0013h -> A4E4h` branch and preserves the `BD5F`
stack scratch below the final return word. The newer `draw_layer=5,
logic_id=0000h` path also returns cleanly after clearing the active flag, so it
is no longer a frontier either.

## 2026-06-12 BEC5 variant 000C tail lift

The same shooting path also reached `1010:BEC5` with `variant=000Ch`.

Findings:

- The BEC5 variant table routes `0007h`, `0008h`, `000Ch`, and `0009h` to the
  shared `BFB9` tail.
- Returning to the original interpreter at `BFB9` is enough to preserve the
  live state for that branch.
- The helper now preserves that branch instead of failing fast.

Status:

- Lifted as a shared-tail dispatch.
- Regression test added for the `000Ch` variant.

## 2026-06-12 BEC5 sprite 0033 BF21 continuation

The latest snapshot also hit the `sprite=0033h` branch inside `1010:BEC5`.
That branch falls through into the shared `BF25` counter logic in the original
code instead of failing fast, and the `third counter zero` tail then continues
through the shared `BF4B -> BFC7` score/death path.

Status:

- Hook updated.
- Regression tests added for the observed sprite fallthrough and `BF4B` tail.

Findings:

- The draw-layer-4 / `logic_id=002Bh` path clears the active flag, enters the
  C054 dispatcher, and the observed `0000h`/`0013h` selector branches return
  `A4E4h` without touching `DS:A47E`.
- The stricter fail-fast only belonged to the smaller counter-decrement family,
  not to the current gameplay snapshot.
- This removes the last crash in the current BC4B/BD17 tail without widening
  the hook to a guessed general rewrite.

Status:

- Hook updated.
- Regression test added for the observed `002Ah` fallthrough.

## 2026-06-12 BFC7 002B branch lift

The same BFC7 tail now also handles the observed `logic_id=002Bh` branch
without dropping `DS:A47E`.

Findings:

- The `0020h` branch remains the one that decrements the live counter.
- The current `002Bh` branch follows the same death/transition state update,
  but skips the counter drop.
- This removes the next crash from the current snapshot without guessing at a
  broad rewrite of the whole dispatcher.

Status:

- Hook updated.
- Regression test added for the observed `002Bh` no-counter path.

---

## 2026-06-12 PC speaker timer-ISR enablement

Enabled PC speaker sound during interactive play by letting the `1010:0679`
timer-wait hook run OVERKILL's installed INT 08h handler when the vector points
to the known game ISR at `1010:06E5`.

Findings:

- The speaker backend from the previous pass was correct, but normal play still
  produced no sound because `1010:0679` only synthesized `CS:066B`.
- Delivering the real INT 08h handler from
  `artifacts/play_tandy_main_menu_20260612_132548` produced the expected
  speaker writes: PIT mode `43h=B6h`, divisor bytes through `42h`, and speaker
  enable through `61h=03h`.
- The ISR chains the old BIOS timer every fourth tick via `JMP FAR CS:[0738]`.
  In this VM the saved BIOS vector can be `0000:0000`, so the hook stops at the
  known chain point after the game-side sound/tick work and restores the
  interrupt frame locally.

Changes:

- `1010:0679 overkill_wait_timer_tick_0679` now runs the original game timer ISR
  when INT 08h is installed as `1010:06E5`, delivering bounded real ISR ticks
  until the original `CS:066B` wait flag advances.
- If the expected ISR is absent, the hook fails fast; it no longer invents a
  synthetic `066B` tick.
- Added a regression using the Tandy menu snapshot that proves the timer hook
  emits `42h/43h/61h` speaker writes and safely handles the fourth-tick BIOS
  chain path.

Verification:

```text
python scripts\run_tests.py
# 128 passed, 0 failed
python scripts\play.py --snapshot artifacts\play_tandy_main_menu_20260612_132548 --verify-frames --verify-frame-max 40
# FRAME VERIFY OK frames=40
python scripts\play.py --snapshot artifacts\play_tandy_edrax_orbit_combat_20260611_232258 --verify-frames --verify-frame-max 40
# FRAME VERIFY OK frames=40
```

---

## 2026-06-12 Tandy gameplay rendering regression fix

Investigated `artifacts/snapshot_play_tandy_20260612_141644`, where gameplay
rendering broke after the PC speaker pass.

Findings:

- The PC speaker changes were not on the failing path: a 900K-instruction probe
  from the snapshot saw `0` reads of port `61h` and `0` writes to `42h/43h/61h`.
- Frame verification diverged at frame 48.
- Hook bisection showed the regression was `1010:33AF
  overkill_expand_tandy_list_33af`, not the recent sound/backend code.
- The composed `33AF` parent hook was only verified for the startup/header-table
  mode where `CS:[0BD8] != 0`.  This gameplay materialization snapshot reaches
  `33AF` with `CS:[0BD8] == 0`, where the original parent has different visible
  behavior.

Fix:

- `1010:33AF` now conservatively self-disables and falls back to original ASM
  when `CS:[0BD8] == 0`.
- The verified child block expander `1010:33B2` remains available, so the
  original parent can still dispatch into accelerated block expansion.
- Added hook-verifier metadata for `1010:33AF`.
- Tightened packed-stream/RLE side-effect fidelity found during the audit:
  `0615 -> 0624` nested calls now leave their original stack scratch, and
  `03A8` uses the shared word reader for its header words so `CS:0614` matches
  the interpreted oracle.

Verification:

```text
python scripts\play.py --snapshot artifacts\snapshot_play_tandy_20260612_141644 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
python scripts\run_tests.py
# 127 passed, 0 failed
```

---

## 2026-06-12 PC speaker hardware/backend pass

Added a narrow PC speaker path for interactive play:

- `dos.py` now tracks PIT channel 2 programming through ports
  `43h/42h` and the speaker gate/data bits at port `61h`.
- `scripts/play.py` bridges speaker state changes from the VM thread to SDL via
  a queue.
- `scripts/sdl_view.py` renders those events as a cached mono square wave using
  `pygame.mixer`.
- Added a core regression for the PIT channel 2 + port `61h` callback contract.

Important finding: current Tandy snapshots and the default inner-EXE command
tail still leave the `2032:0000` sound-driver slot as a tiny return stub and do
not emit speaker port writes during a short main-menu run.  The backend is ready
for real speaker writes, but audible game sound still depends on identifying the
sound-driver selection/loading path or lifting the proven `1010:06E5` timer ISR
sound call once that target is non-stub.

Verification:

```text
python -m py_compile dos.py tests\test_core.py scripts\play.py scripts\sdl_view.py
python scripts\run_tests.py
# 126 passed, 0 failed
```

---

## 2026-06-12 Tandy end-screen direct-video publish

Investigated `artifacts/play_tandy_the_end_20260612_001833`, where the
interactive viewer appeared frozen after the ending instead of showing the
high-score/name-entry flow.

Findings:

- Continuing the snapshot headlessly does not crash or remain at the snapshot
  entry.  The game advances from `1010:98FA` through the retrace-delay loop.
- In the following path, video memory changes directly: a 1M-step probe changed
  10,257 bytes in `B800h`.
- The hot path is interpreted text/glyph drawing around `1010:518C -> 3153`,
  which writes to `ES=B800` without hitting the usual Tandy present, timer, or
  retrace hooks after the initial delay.
- Because `scripts/play.py` previously published frames only at known
  present/timer/retrace boundaries, this looked frozen in the viewer even though
  the VM was drawing.

Fix:

- `scripts/play.py` now checks for changed visible video memory when a long run
  reaches the no-boundary frame budget.  If video changed, it publishes a
  "direct video" frame and treats that as a UI boundary.
- `scripts/sdl_view.py` reports the direct-video count in the window caption.
- Printable SDL keydowns are also bridged into the DOS key queue after the first
  direct-video publish, so late DOS character input such as `INT 21h AH=07h`
  name entry can receive typed characters without polluting the queue during
  normal gameplay controls.
- Follow-up from `artifacts/snapshot_play_tandy_20260612_131223`: a snapshot can
  start already inside the high-score/name-entry screen before this viewer
  session has counted any direct-video publish.  The DOS-key bridge is therefore
  also enabled while the CPU is in the observed high-score editor region
  `1010:5300..5650`, with a scancode-to-ASCII fallback for common printable
  keys and control keys when SDL provides no printable `unicode`.
- Follow-up from `artifacts/snapshot_play_tandy_20260612_131602`: the saved
  state is already late in the editor/submission path (`1010:55F1`) with the
  name buffer filled (`gttrfdffgg`), the name pointer at the 10-character limit,
  and the last editor character recorded as Enter (`DS:22B4=000D`).  Continuing
  that snapshot can therefore return to the menu because the name has already
  effectively been submitted, not because the VM has a stuck Enter key.
- Follow-up from `artifacts/snapshot_play_tandy_20260612_131812`: this snapshot
  starts before the high-score screen is fully drawn (`1010:32C5`).  Profiling
  1.5M steps shows the delay is pure interpreted text/direct-video drawing:
  `1010:518C`, `1010:3153`, and callers around `1010:32C5`; no replacement
  hooks fire.  This explains the slow appearance and marks the path as a future
  direct-video/text drawing lift candidate.
- The remaining "cannot type name" issue was caused by the deterministic
  headless DOS console fallback: `INT 21h AH=07h` returned Esc when no queued
  key was available.  In interactive `scripts/play.py`, DOS console input now
  blocks instead: the handler rewinds `IP` to the `INT 21h`, raises a narrow
  `ConsoleInputWouldBlock`, and the viewer yields a UI boundary until a real key
  is queued.
- Name-entry input then exposed the real missing VM service:
  `INT 10h AH=0Eh` BIOS teletype output.  The high-score editor reaches this as
  a bell (`AL=07h`) for rejected input.  `dos.py` now accepts this narrowly by
  recording the character in the stdout log rather than trying to render BIOS
  text over the graphics screen.

Verification:

```text
python -m py_compile dos.py scripts\play.py scripts\sdl_view.py
python scripts\run_tests.py
# 121 passed, 0 failed
```

---

## 2026-06-12 Tandy menu/redefine screen rendering pass

Investigated `artifacts/play_tandy_main_menu_20260612_132548`, where menu
subscreens such as ordering info, instructions, and redefine-keys felt slow.

Changes:

- `scripts/sdl_view.py` no longer treats Esc as a viewer quit key.  Esc is now
  forwarded to OVERKILL like the rest of the keyboard; close the SDL window to
  exit the viewer.
- Added `1010:306F overkill_tandy_rect_copy_306f`, the raw Tandy rectangle copy
  used by menu/high-score text screens.  This is a parent-level replacement for
  the formerly hot `307E` row loop.
- Added `1010:CDAA overkill_tandy_changed_dword_present_8rows_cdaa`, the Tandy
  dirty-present sibling of the existing `CD8D` CGA/EGA-ish changed-word
  presenter.

Verification:

```text
python scripts\run_tests.py
# 123 passed, 0 failed
```

Profiling notes:

- Before `306F`, `1010:307E..3094` dominated the interpreted menu/text copy
  path.  After the hook it disappears from the interpreted hot list.
- Before `CDAA`, `1010:CDAA..CDC8` was the next Tandy dirty-present loop.  After
  the hook it also disappears from the interpreted hot list.
- The remaining top interpreted loop from this snapshot is `1F8F:0960`, a compact
  far-overlay/menu counter loop.  It is not clearly part of the Tandy rendering
  island, so it was left untouched in this pass.

Follow-up from `artifacts/snapshot_play_tandy_20260612_134028`:

- The redefine-keys page itself was not slow because of rendering.  It was
  spinning in a pure keyboard wait:
  `1010:57AB cmp byte ptr DS:[98C3],00h` / `1010:57B0 jz 57AB`.
- `scripts/play.py` now treats this redefine-key wait as an interactive yield
  boundary when `DS:[98C3]` is still zero.  The runner publishes any changed
  video, pumps the UI, and retries after a real key event.
- The same handling covers the immediately following key-release wait at
  `1010:57DD/57E0`, where the game waits for `DS:[98C4 + DS:[98C3]]` to clear.
- This is deliberately not a global replacement hook: headless profiling and
  oracle runs still see the original wait loop.  The fix only prevents the live
  viewer from burning the full `--frame-budget` between redefine-key prompts.

---

## 2026-06-12 Tandy cold-start composition pass

Cold-start profiling with Tandy mode (`scripts/profile_hotspots.py --video
tandy`) showed that the largest remaining startup overhead before the next VM
frontier was not another codec, but the interpreted Tandy startup list driver:

```text
1010:33AF -> call 44D7 header reader -> 1010:33B2 block expander
```

`33B2` was already a verified hook, but startup still interpreted hundreds of
small `44D7` header reads and hook boundaries.  Added:

- `1010:33AF overkill_expand_tandy_list_33af`, a parent-level Tandy startup
  list hook that composes the `44D7` header reader with the existing `33B2`
  block expander until the zero-header terminator jumps to `44AA`.
- Full-memory synthetic oracle coverage for a two-block list plus terminator.
- A stack-scratch correction in the existing `33B2` helper for the nested final
  `344B` call return word (`341B`).

Profiling effect before the same startup frontier:

- before: `33B2` hook called 686 times and the interpreted hot list was dominated
  by `33AF/44D7/450A`;
- after: `33AF` hook called 9 times, `33AF/44D7/33B2` disappeared from the
  interpreted hot list, and total hook invocations before the frontier dropped
  from 1,048 to 371.

The same profile then exposed unsupported 8086 opcode `98h` at `1010:0008`;
implemented narrow `CBW` support in `cpu.py` (sign-extend `AL` into `AX`, flags
unchanged).  With `CBW`, a 1M-step cold Tandy profile reaches normal
menu/gameplay-heavy code.  The remaining top non-hook loop is `1F8F:0960`, which
does not clearly belong to the current asset/rendering islands and was left
untouched.

---

## 2026-06-12 Instructions/order overlay wait

Investigated `artifacts/snapshot_play_tandy_20260612_140352`, captured from the
instructions screen after it appeared slow to load.

Finding:

- The snapshot is already inside the loaded overlay segment (`1F8F:09B7`), not in
  file IO, decompression, or startup materialization.
- Profiling 1M steps showed zero hooks and 100% interpreted time in
  `1F8F:099B..09DF`, a tight key-state wait loop.  It checks menu/action key
  bytes such as `DS:990F`, `990C`, `990D`, `98D2`, `9911`, `9914`, `9915`,
  `98FD`, `98E0`, and `98C5`.
- `scripts/play.py` now recognizes this overlay wait by code signature and
  yields the interactive UI immediately while all watched key bytes are idle.
  This is not a loader hook and not a global replacement; it only prevents the
  live viewer from burning the full frame budget while instructions/order screens
  wait for input.

Verification:

```text
python scripts\run_tests.py
# 125 passed, 0 failed
```

---

## 2026-06-12 Timeless top-level documentation pass

Refactored project-facing docs so durable guidance is separated from living
status:

- `AGENTS.md` now contains stable agent/human workflow rules: project purpose,
  proof obligations, hook mechanics, verification expectations, source-port
  islands, artifact policy, and things not to do.
- `README.md` now reads as stable onboarding: goals, non-goals, local game-file
  expectations, project layout, quick-start commands, verification workflow,
  source-port island model, and documentation map.
- `docs/overkill/design.md` now describes runtime architecture and design pressure
  without embedding old checkpoint progress or tactical next targets.

Current facts, recent commands, and next tactical targets should remain in
`docs/overkill/run_status.md`; durable address-level findings remain in
`docs/overkill/runtime_findings.md`.

---

## 2026-06-12 Existing-island exhaustion audit tooling

Added `scripts/audit_islands.py` to make island closure visible instead of
purely conversational.  The script groups currently registered hooks into the
already-created OverKill islands:

- asset codecs / startup materialization
- overlay loading / overlay decode / overlay directory scan
- startup graphics expansion
- coordinate/address helpers
- shared layer sprite dispatch
- Tandy-specific rendering primitives

For each island it reports hook-verifier metadata coverage, obvious
oracle/regression test mentions, `symbols.json` entries that still advertise a
candidate/frontier/unverified/fallback state, explicit module seam markers such
as bounded original fallbacks, and optional trace hits.

Useful commands:

```text
python scripts\audit_islands.py
python scripts\audit_islands.py --all-hooks
python scripts\audit_islands.py --json
python scripts\audit_islands.py --trace artifacts\some_trace.txt
```

Current audit result:

- `startup_graphics` reports `closed-candidate`: all known hooks in that island
  have verifier metadata and test mentions, and the script found no explicit
  seam markers or open symbols.
- `asset_codecs` now reports `closed-candidate`: the remaining
  `1010:0324` word-pair RLE candidate has been lifted, verified, and marked
  replaced.
- `overlay` remains open because `254A:05A1` and `254A:05D9` need direct test
  mentions and `254A:04D7` is still marked as an active parent-loader
  investigation target.
- `coordinates` remains open because the coordinate module still contains an
  explicit unverified-path seam.
- `layer_sprites` remains open because it still has bounded-original/fail-fast
  seams and an open `1010:75A6` frontier symbol.
- `tandy_rendering` remains open because several hooks lack obvious direct test
  mentions.

Important limitation: `closed-candidate` is a closure signal, not proof that no
unknown behavior exists.  It means the known source-port island has no
script-detected blockers left and should then be checked with live hook
verification and representative Tandy traces.

Hook-verifier metadata was also filled in for the existing-island hooks that now
have clear boundaries, including overlay far-return handling for `254A:0701`.
A small regression pins the far-return stop metadata behavior.

Verification:

```text
python -m py_compile scripts\audit_islands.py overkill/verification.py
python scripts\run_tests.py
# 119 passed, 0 failed
```

---

## 2026-06-12 Asset-codec closure: 1010:0324 word-pair RLE

Closed the last audit blocker in the non-overlay `asset_codecs` island:

- `1010:0324` is a word-pair RLE decoder, sibling to the already lifted
  `1010:0367` byte-linear and `1010:03A8` vertical RLE decoders.
- The stream starts with a sentinel word read through the packed `0615` reader.
  Non-sentinel words are literal two-word pairs.  Sentinel words introduce a
  repeat count; count zero exits to the shared loader continuation at
  `1010:02A8`, and nonzero counts repeat the following two-word pair.
- The implementation lives in
  `overkill/asset_codecs/rle.py` as
  `decode_word_pair_rle`, with a thin `overkill/hooks.py` hook wrapper.
- The shared packed byte reader now preserves the original fast-path carry:
  `0624` does `CMP BX,0610h`, takes the below-buffer branch with `CF=1`, and
  the later `INC word ptr [0610]` preserves that carry.
- The oracle test covers literal, repeat, and terminator paths, including final
  registers, flags, output words, packed-stream scratch, byte count, and stack
  scratch around `SS:SP`.

Audit result after this pass:

```text
asset_codecs      closed-candidate  hooks=10
startup_graphics  closed-candidate  hooks=7
```

Verification:

```text
python scripts\run_tests.py
# 119 passed, 0 failed

python scripts\audit_islands.py --all-hooks
# asset_codecs and startup_graphics report closed-candidate
```

---

## 2026-06-12 Existing-island audit: overlay signature loop

Audited remaining candidates against the already-created OverKill islands
(`asset_codecs` and `rendering`) and intentionally avoided opening new gameplay
areas.

Lifted one clear overlay-loader subloop:

- `254A:0582` belongs to the existing `asset_codecs.overlay` island.  It is the
  bounded header/signature compare loop after the parent loader reads the
  twelve-byte overlay/container header.  The Python implementation now lives in
  `overkill/asset_codecs/overlay.py` as
  `compare_overlay_signature_0582`, with a thin hook wrapper in
  `overkill/hooks.py`.
- Continuations are preserved exactly: full match goes to `254A:058D`; first
  mismatch goes to `254A:0640`.
- Added an interpreted-ASM oracle regression covering both exits.

Audit decisions:

- `254A:04D7` is clearly overlay loading, but it is a larger file-open/read/seek
  parent.  It should not be lifted wholesale until more of its small deterministic
  loops are closed.
- `1010:B73E/BC4B/62F6/BEC5` are gameplay/contact helpers, not part of the six
  requested islands, so they were left alone.
- The remaining CGA/EGA bounded layer compositor allow-list belongs to the shared
  layer-sprite rendering island, but it is not Tandy-specific and would be a
  broad rendering sweep; left untouched in this focused pass.

Verification:

```text
python scripts\run_tests.py
# 117 passed, 0 failed
```

---

## 2026-06-11 Tandy B73E formation/contact continuation

Closed the later formation-change divergence from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

- The original frame-383 path for object `BP=2814` is
  `B73E -> B77B -> BC4B -> BCCB -> AA46/8331 -> BFC7`, not a `62F6`
  overlap collision.  `AA46` sets carry when the object is inside the
  view/contact rectangle; the replacement previously checked only X and always
  cleared carry, so the object stayed alive in logic `20h`.
- `_run_view_window_check_aa46` now mirrors the full X/Y rectangle test and
  preserves the carry-set contact result.
- `_run_object_postmove_bc4b` now composes the carry-set `BCCB` path: optional
  `BFC7` death/logic-transition tail, observed `9E69` bookkeeping, then the
  normal `62F6` call.
- `_run_object_overlap_scan_62f6` now preserves `BX` on the early
  `logic_id == 0001` return, matching the original post-death scan.
- Added an interpreted-ASM regression for the exact `B77B` contact-death tick.

Verification:

```text
python scripts\run_tests.py
# 113 passed, 0 failed

python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 500
# FRAME VERIFY OK frames=500
```

---

## 2026-06-11 B73E/BEC5 gameplay continuation

Closed two user-reported Tandy gameplay stops from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`:

- Shooting enemies reached `B73E -> B7BD -> BC4B -> 62F6 -> BEC5 fourth
  counter zero`.  The observed `BFC7` death/transition tail now handles the
  type-1, no-linked-slot path: score add via the `5F0D` BP/SS decimal helper,
  Y clamp, logic transition `20h -> 1`, previous logic saved in `+1A`, `+22`
  cleared, and the type-1 sprite-zero dispatch.
- Passive play reached `B73E -> B7BD -> B7F3`, then the follow-up
  `B73E -> B7BD -> B82D -> B7BD` waypoint-loop case.  The verified branches now
  cover the `B7F3 -> B7C9` target-reset path, substate-0 `B754` movement path,
  and the bounded `B82D` waypoint-table loop.

Important correction while verifying: the `B7C9` target reset always produces
the observed target Y from `DS:2380 + 8` before alignment; a branch-counting
guess that preserved the old target caused frame-266 divergence.

Verification:

```text
python scripts\run_tests.py
# 111 passed, 0 failed

python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 300
# FRAME VERIFY OK frames=300
```

The key correction for the waypoint loop: `B82D` does not move immediately after
selecting a different waypoint.  It updates `+34/+32` from the table and falls
through to `BC4B`; movement happens on a later target-mismatch tick.

---

## 2026-06-11 Tandy layer-0 scan fix: A894 stops at CALL A8BE

User-reported gameplay from `artifacts/play_tandy_edrax_orbit_combat_20260611_214016`
hit the layer-0 draw scan with an active layer-0 object:

```text
1010:A894: partial scan reached unlifted CALL at A8BE
BP=2884 active=0001 layer=0000 type=0001 draw_layer=0005
```

This was a boundary bug in the shared partial-scan helper.  The `1010:A894`
hook is supposed to skip non-calling iterations and stop immediately before the
real `CALL` for the first drawable object.  Instead, `_scan_loop_until_callable`
still used the older fail-fast behavior.

Fix:

- `_scan_loop_until_callable` now preserves the loop `PUSH CX` scratch and leaves
  `CS:IP` at the real call instruction (`1010:A8BE` for `A894`).
- Added a synthetic interpreted-ASM oracle test for the active layer-0 path,
  comparing the original bytes through `A8BE` against the hook state.

Verification:

```text
python scripts\run_tests.py
# 108 passed, 0 failed

python scripts\play.py --snapshot artifacts\play_tandy_edrax_orbit_combat_20260611_214016 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
```

---

## 2026-06-11 Tandy gameplay crash fix: BEC5 BEDC=0001 collision tail

User-reported manual gameplay from
`artifacts/play_tandy_black_panel_20260611_192528` crashed while shooting spawned
ships:

```text
B73E -> B73E -> B7BD -> BC4B -> 62F6 -> BEC5 BEDC=0001 -> BF5E
```

The branch was real gameplay execution, not a renderer path.  Re-reading the
original bytes showed that `DS:BEDC == 0001` does not return immediately: it
jumps into the tail at `1010:BF4D`, decrements `SS:[BP+20]` once more, writes
`SS:[BP+24]=0005`, compares `DS:A8C2` with `0001`, and then returns at
`1010:BF5E` when `A8C2 != 0001`.

Fix:

- `1010:BEC5` observed variant-2 collision helper now implements the verified
  `BEDC=0001` tail instead of fail-fasting or returning early.
- The remaining zero-counter and `A8C2=0001` branches stay fail-fast with
  concrete target addresses.
- Added a synthetic interpreted-ASM oracle test for the `BEDC=0001` tail.

Verification:

```text
python scripts\run_tests.py
# 107 passed, 0 failed

python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60

python scripts\play.py --snapshot artifacts\play_tandy_black_panel_20260611_192528 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
```

---

## 2026-06-11 frame-verify regression fix: AA2B/EFAE back to dispatch-only

User-reported frame verification diverged at frame 34 from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`:

```text
python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 60
```

Bisecting with `OVERKILL_DISABLE_HOOKS` showed:

- Disabling all non-frame hooks passes 60 frames.
- Disabling only the recent layer/draw hooks did not change the bad CRC.
- Disabling `1010:AA2B,1010:EFAE` alone restores 60-frame verification.

Root cause: `AA2B` and `EFAE` had crossed from dispatch-stub replacements into
inline gameplay behavior execution. Synthetic/local verifier boundaries did not
catch the later frame-level drift.

Fix:

- `1010:AA2B overkill_object_logic_dispatch_aa2b` is now dispatch-only: it
  mirrors `mov bx,ss:[bp+16]; shl bx,1; jmp cs:[bx+AA36]`.
- `1010:EFAE overkill_object_family_dispatch_efae` is now dispatch-only after
  preserving the real prologue writes to `DS:D1FE` and `DS:D200`, then jumps
  through `CS:EFC4`.
- Hook verifier metadata now stops at the selected dispatch target for both
  hooks, not at the caller return.
- Added synthetic ASM oracle coverage for both dispatch boundaries.
- `scripts/run_tests.py` now provides a tiny `pytest.raises` shim when pytest is
  unavailable, keeping the local pytest-free runner usable.

Verification:

```text
python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60

python scripts\run_tests.py
# 106 passed, 0 failed
```

---

## 2026-06-11 island-closure continuation: movement/collision/draw/layer frontier

Continued the fail-fast “close the island before expanding” pass from the previous
object-logic frontier.  The run no longer stops at `5DB2`; the currently opened
Tandy/object island now includes movement, the observed collision branch, more
first-level object logic, and several adjacent Tandy draw/layer targets.

New structural lifts in this pass:

- `1010:5DB2`: target-seeking movement/direction helper, including observed
  `AF60` double 2-pixel step and `AEE4` 8-pixel step modes.
- `1010:8D4F`: observed `logic_id=1Fh` waypoint/target-patrol branch through the
  far-call waypoint reader and `5DB2`.
- `1010:BEC5` observed branch: collision with a `+18h == 0002` object now
  deactivates the collided slot and updates the moving object's `+20h/+24h` state
  instead of stopping at the collision handler.
- `1010:AB10`: first-level AA2B target that updates object sprite/position from
  the `A40C/A414` tables.
- `1010:AED8`: observed `logic_id=2` movement/tile-probe branch, including the
  `AEE4 -> B250 -> AD5A -> 5073/505B` path and the observed out-of-bounds
  deactivation through `BD17`.
- `1010:356C`, `1010:3657`: additional Tandy draw targets reached by the composed
  `A849/A861 -> 5AC8` draw scans.
- `1010:A861`: overlaid `8D12` draw scan now composes verified `5AC8` Tandy draw
  targets instead of stopping before the call.
- `1010:7746` and `1010:2FB6`: compact layer draw setup and its two-word masked
  Tandy compositor, reached by `A87C`.
- `1010:A87C`: active-object scan over `8D12` now composes the verified `7746`
  compact layer draw path.

Current intentional frontier from `artifacts/play_tandy_edrax_orbit_combat_20260611_164810`:

```text
1010:A8C7 -> 7596 -> 75A6
```

This is useful new information: the already-opened layer pipeline now reaches the
`75A6` split/two-destination layer draw helper.  It should be lifted next rather
than adding a fallback.

Verification:

```text
python -m pytest -q                         # 103 passed
python -m compileall -q dos_re overkill scripts tests
python - <<'PY'                              # symbols.json parses
import json; json.load(open('symbols.json'))
PY
```

---

## 2026-06-11 fail-fast object logic frontier

The fail-fast no-fallback pass continued past the previous stop at
`1010:A9E0 -> AA01 -> AA2B`.

New structural lifts:

- `1010:A9E0`: object-logic scan over `DS:32CA`, including `DS:2340` counter side effect.
- `1010:AA10`: object-logic scan over `DS:8D12`.
- `1010:AA2B`: first-level object logic dispatch by `SS:[BP+16]` / `CS:AA36`.
- `1010:EFAE`: second-level object family dispatch by `SS:[BP+18]` / `CS:EFC4`.
- `1010:B73E`: observed `logic_id=20h` branch lifted to the next concrete helper.

Current intentional frontier from `artifacts/play_tandy_edrax_orbit_combat_20260611_164810`:

```text
1010:A9E0 -> AA2B -> EFAE -> B73E -> B85C -> B729 -> 5DB2
```

Verification:

```text
python -m pytest -q                         # 102 passed
python -m compileall -q dos_re overkill scripts tests
python - <<'PY'                              # symbols.json parses
import json; json.load(open('symbols.json'))
PY
```

Next best RE target: `1010:5DB2`, the movement/direction helper that compares the
object position against `DS:2304/2306`, writes `DS:A954` / `DS:230A`, XLATs through
`DS:A348`, and then dispatches via `CS:5E0C` according to `DS:2308`.

---
# Checkpoint: A90F/5A92 present-scan lift (fail-fast follow-up)

Continuing from the no-fallback run, the first exposed target was not worked around.
`1010:A90F` has now been lifted as a real parent present scan over the `DS:8D12`
object table. Active entries compose through `5A92` when their Tandy present target
is verified.

New verified present targets discovered from this path:

- `1010:3542` — 8-row/two-word Tandy present copy with `DI += 0064h`.
- `1010:34AD` — split present copy: optional first `34C5`, then
  `SS:[BP+10]` / `SS:[BP+0E]+0140h` tail into `34C5`.

`A927` now uses the same shared present-scan helper, so both `32CA` and `8D12`
present scans compose known `5A92` targets and fail fast on truly unknown ones.

Validation:

- `python -m pytest -q` -> 102 passed.
- `python -m compileall -q dos_re overkill scripts tests` -> passed.
- `symbols.json` parses.
- Replaying `artifacts/play_tandy_edrax_orbit_combat_20260611_164810` now gets past the
  previous `A90F -> A91E -> 5A92` stop and past the newly discovered `3542`/`34AD`
  present targets. The next intentional fail-fast target is now
  `1010:A9E0 -> AA01 -> AA2B`, object `BP=2734`, `CX=0011`, `type=0001`,
  `draw_layer=0004`, `sprite=007A`.

Next RE target:

- Reverse/lift the `1010:A9E0 -> AA01 -> AA2B` object/gameplay dispatch path.

---

# Checkpoint: fail-fast replacement policy (no ASM fallback masking)

This pass removes the conservative unknown-target fallbacks from composed replacement hooks.
The project goal is reverse engineering, not short-term playability, so unknown dispatch
paths now raise a diagnostic `RuntimeError` instead of returning to the interpreted ASM
pre-call boundary. Runtime-patched hook signatures also fail fast instead of silently
unregistering the hook and continuing through the original bytes.

Changed behavior:

- `1010:A849` now raises on unverified `A849 -> 5AC8 -> target` paths instead of
  stopping at `A858`.
- `1010:A927` now raises on unverified `A927 -> 5A92 -> target` paths instead of
  stopping at `A936`.
- `1010:A8C7` now raises on unverified `A8C7 -> 7596` or nested
  `A8C7 -> 7596 -> 768E -> target` paths instead of stopping at `A8F1`.
- `1010:768E` now raises on unknown Tandy sprite compositor targets instead of
  tail-dispatching to original code.
- Partial scan hooks using `_scan_loop_until_callable` now raise when they reach an
  active object requiring an unlifted call. They still complete skip-only scans.
- `5A36` and shared `5A00/5A24` coordinate dispatch helpers now raise on unverified
  video modes rather than jumping into original target code.

Validation:

- `python -m pytest -q` -> 99 passed.
- `python -m compileall -q dos_re overkill scripts tests` -> passed.
- `symbols.json` parses.
- Continuing `artifacts/play_tandy_edrax_orbit_combat_20260611_164810` now intentionally stops
  after 3 instructions at the next unknown RE target:
  `1010:A90F` partial scan reached unlifted call `A91E` with object `BP=2CAC`,
  `CX=0007`, `type=0000`, `sprite=0032`, `di=537A`, `present_si=9418`.

Next RE target exposed by fail-fast policy:

- Reverse/lift the `1010:A90F -> A91E -> 5A92` present/object scan path instead of
  allowing the old skip hook to fall back into ASM.

---

# Run status — checkpoint 31

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Crash regression snapshot:
`artifacts/play_tandy_edrax_orbit_combat_20260611_164810`.

This pass fixes the gameplay crash at `1010:A8C7` without treating `2F40` as an
unknown fallback case.  The deeper issue was that `1010:768E` is a
setup/tail-dispatch helper, and the crash snapshot exercised a real Tandy
compositor target that had not yet been lifted:

- `1010:2F40 overkill_tandy_or_inverted_mask_2f40`

## Tandy compositor target 2F40

`2F40` is a four-word, 16-row Tandy layer compositor.  It is not the same masked
copy shape as `2F81`: each row consumes four source cells as
`MOV AX,[SI]; NOT AX; OR ES:[DI],AX; ADD SI,4; ADD DI,2`, then advances the
destination by `0060h`.  In game terms this is an inverted-mask OR pass used by
some layer sprites.

The new hook preserves the original `BX=0060h`, `CX` loop, `SI`/`DI` advancement,
final flags from the last row `ADD DI,BX`, `DS=CS:[9596]` restoration, and `RET`
behavior.  `768E` and the composed `A8C7` scan now treat `2F40` as a verified
child target alongside `2F81` and `2E6E`.

`A8C7` still predicts the nested `768E` compositor before composing the scan, but
that fallback is now only for genuinely unverified nested targets; the observed
`2F40` path is executed and verified rather than skipped.

## Verification

- Crash snapshot replay from `play_tandy_edrax_orbit_combat_20260611_164810`: 50,000
  instructions without the old `768E layer draw returned to unexpected IP 2F40`
  crash.
- Synthetic interpreted-ASM oracle now covers `768E -> 2F40`.
- Synthetic `A8C7` parent-scan oracle now covers full composition through
  `7596 -> 768E -> 2F40`.
- Live verifier from the crash snapshot:
  - `A8C7`: 20 real calls, no divergence.
  - `768E`: 1 real nested `2F40` call in the replay window, no divergence.
- Full test suite: `99 passed`.
- `py_compile`: passed.

---

# Run status — checkpoint 30

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Current Tandy gameplay snapshot:
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

This pass moved one level higher in the Tandy layer-1 draw pipeline:

- `1010:768E overkill_tandy_layer_sprite_draw_768e`
- `1010:A8C7 overkill_scan_layer1_draw_a8c7`

## Layer-1 draw composition

`1010:7596` is a small object-type dispatcher.  Its hot Tandy layer-1 path
dispatches object type 1 to `1010:768E`, which sets up the source segment/table,
destination pointer, mode/phase compositor table, row count, and then tail-jumps
to the verified Tandy sprite compositor (`1010:2F81` in the current snapshot).

`768E` is now a verified setup/tail-dispatch helper.  It handles:

- `DI=FFFF` early return.
- Known compositor targets `2F81` and `2E6E` by running verified children.
- Unknown compositor targets by tail-dispatching back to the original target.

`A8C7` now composes the layer-1 scan when the active object's `7596` target is
the verified `768E` path.  It preserves the original layer filter, `PUSH CX`,
`CALL 7596`, `POP CX`, and `LOOP` behavior.  If an active object dispatches to an
unverified `7596` target, the hook falls back before the original call at
`1010:A8F1`.

## Verification

- Added interpreted-ASM oracle tests for `768E` complete, early-return, and
  fallback paths.
- Added interpreted-ASM oracle tests for `A8C7` complete and fallback paths.
- Live hook verifier from `snapshot_play_tandy_20260611_152751` covered:
  - `768E`: 800 real calls, no divergence.
  - `A8C7`: 500 real layer-1 scan calls, no divergence.

## Current profile shape

The layer-1 pipeline no longer appears as repeated interpreted
`A8C7 -> 7596 -> 768E -> 2F81` crossings in the common Tandy path.  The remaining
hot interpreted work is now strongly concentrated in shared object/gameplay code:

- `1010:A9E0 -> AA2B`
- `1010:EFAE` object routine dispatch
- `1010:BC4E` / nearby shared update/collision-style logic

Those should be treated as gameplay/object reconstruction targets rather than
rendering helpers.

---

# Run status — checkpoint 29

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Current Tandy gameplay snapshot:
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

This pass composed two verified small-hook clusters into full object scan passes
for the common Tandy first-level object table.

## Composed object scan hooks

Updated:

- `1010:A927 overkill_scan_objects_call_5a92_a927`
- `1010:A849 overkill_scan_objects_call_5ac8_a849`

Both routines still preserve the old conservative behavior when they encounter
an unverified dispatch target: they stop at the original pre-call boundary
(`A936` for `A927`, `A858` for `A849`).  When all active objects dispatch to the
verified Tandy targets, they now run the whole scan loop and return at the loop
exit (`A93C` / `A85E`).

The composed paths reuse the already verified smaller operations:

- `A927 -> 5A92 -> 34D8/34C5`
- `A849 -> 5AC8 -> 35CC/35AA`

They preserve the original `PUSH CX`, `CALL`, `POP CX`, `LOOP` stack scratch and
flag behavior instead of inventing a higher-level object API.

## Verification

- Added interpreted-ASM oracle tests for complete and fallback paths of both
  composed scan hooks.
- Live hook verifier from `snapshot_play_tandy_20260611_152751` covered:
  - `A927`: 750 real full-scan calls, no divergence.
  - `A849`: 760 real full-scan calls, no divergence.

## Current profile shape

With both 32CA scan passes composed, a 3M-step Tandy first-level profile drops
the repeated `A849/A927 -> 5AC8/5A92 -> 35CC/34D8` interpreter crossings.  The
remaining hot interpreted areas are now mostly shared behavior:

- `1010:AA2B` / `EFAE` object dispatch/update paths.
- `1010:BC4E` and nearby shared gameplay code.
- `1010:A8C7 -> 7596 -> 768E` layer-1 draw pipeline.

These are the next good characterization targets, with preference for lifting a
whole pipeline once the boundary is proven.

---

# Run status — checkpoint 28

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Current Tandy gameplay snapshot:
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

This pass continued from the Tandy first-level snapshot and lifted the next
highest-impact verified Tandy gameplay blocks, favoring parent/block-level hooks
over tiny leaves.

## Tandy gameplay hooks

Added verified hooks:

- `1010:2F81 overkill_tandy_masked_sprite_composite_2f81`
- `1010:2E6E overkill_tandy_masked_sprite_composite_2e6e`
- `1010:34C5 overkill_tandy_strided_copy_34c5`
- `1010:35AA overkill_tandy_source_strided_copy_35aa`
- `1010:34D8 overkill_tandy_small_strided_copy_34d8`
- `1010:35CC overkill_tandy_draw_object_block_35cc`

Also folded the Tandy mode-2 row-address target `1010:30D2` into the existing
`1010:5A36` dispatch hook, so mode 0/1/2 now return at the caller boundary while
unknown modes still dispatch to the original table target.

`35CC` is deliberately a composed parent hook: it calls the verified `5A36`
row-address replacement internally, mirrors the original `CALL 5A36` stack
scratch, then performs the Tandy source-strided copy as one routine.

## Verification

- Added interpreted-ASM oracle tests for all new Tandy gameplay hooks, including
  the composed `35CC -> 5A36 -> 30D2` path.
- Live hook verifier from `snapshot_play_tandy_20260611_152751` covered:
  - `2F81/2E6E/34C5/35AA/5A36`: 2,000 mixed real calls, no divergence.
  - `34D8`: 500 real calls, no divergence.
  - `35CC/34D8/5A36`: 1,500 mixed real calls, no divergence.

## Current profile shape

`python scripts/profile_hotspots.py 3000000 --video tandy --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --top 35`
now shows the Tandy-specific sprite/copy work as hooks. The remaining real
interpreted heat has shifted toward shared object/gameplay logic:

- `1010:AA2B` dispatch/helper path
- `1010:EFAE` object routine dispatcher
- `1010:BC4E` / `BCxx` shared gameplay paths
- smaller draw target work around `1010:768E`

Those are the next best candidates, but they should be lifted only after their
entry/exit contracts and call families are characterized.

---

# Run status — checkpoint 27

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  Local pytest-free runner:
`86 passed, 0 failed`.

This pass switches the interactive/profiling default video mode to Tandy and
adds verified Tandy startup-expander hooks for the slow packed-pixel asset path.

## Tandy default

- `scripts/play.py` now defaults to `--video tandy`.
- `scripts/profile_hotspots.py` now defaults to `--video tandy`.
- `README.md` now documents Tandy as the default interactive path.

## Tandy startup-expander hooks

Profiling showed Tandy startup was spending most of its time in the live-patched
`1010:33B2 -> 33DD -> 344B` packed-pixel block renderer.  This is the Tandy
analog of the already-hooked EGA `4511/4537/45F6` startup expander.

Added:

- `1010:33DD overkill_expand_tandy_cell_33dd`
- `1010:33B2 overkill_expand_tandy_block_33b2`

The `33B2` hook is guarded by live-byte signature because this code region is
runtime-patched.  It preserves the original normal continuation (`1010:33AF`),
terminator branch (`1010:44AA`), `SI`/`DI`/`CX` loop effects, flags, output
writes, and final stack scratch words from the original call frame.

## Verification

- Added interpreted-ASM oracle tests for `33DD`, `33B2`, and the `33B2` zero/
  terminator branch.
- Added hook-verifier continuation metadata for `1010:33B2` and `1010:33DD`.
- Live differential verification covered all 686 real `1010:33B2` calls reached
  in the current Tandy startup profile with no divergence.
- Full local test runner: `86 passed, 0 failed`.

## Profiling note

`python scripts/profile_hotspots.py 6000000 --video tandy --top 10` now shows
`1010:33B2` as 686 block-level hook calls instead of the previous interpreted
`33B2/33DD/344B` loop tree.  After replacing the internal 344B rotate simulation
with direct bit packing, `33B2` is about `0.57s` total / `0.83ms` per block in
the same profile.  The run still stops later at the pre-existing
`Unsupported opcode 98 at 1010:0008`; a control run with `1010:33B2` disabled
hits the same stop, so it is not caused by the new hook.

## Viewer polish

The SDL viewer window is now resizable/maximizable.  Frames are centered at the
largest integer scale that fits the current window, preserving the 320x200 aspect
ratio with black bars as needed.

---

# Run status — checkpoint 26

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `65 passed` *at this checkpoint*.

> **Note:** this checkpoint is not the latest state.  Work after checkpoint 26
> (EGA planar-correctness fixes, the masked-sprite/perf pass, the overkill/hooks.py
> hook de-duplication, and the 2026-06-11 EGA gameplay-profiling passes that added
> the verified `1D1B` and wide `13E7` bit-spread composite hooks — together ~17%
> then a further ~33% faster in-level play) is recorded in
> [`docs/overkill/runtime_findings.md`](runtime_findings.md); the full suite is now
> `82 passed`.

This pass continued profiling the slow planet/difficulty selection screen that is
shown after pressing SPACE in the main menu.  The earlier menu hooks helped, but
profiling showed that this screen was now dominated by overlaid masked-sprite
compositors and object dispatch stubs rather than asset decompression.

## Performance finding

After re-enabling the dirty-copy hooks and adding the previous `4D15` fix, the
next hot interpreted path was the overlaid masked sprite drawing code around
`1010:3EFB`.  This routine is used heavily by the selection highlight/sprite
redraw path and performs many `RCR`/`SHR` chains per row.

The addresses around `3EE1`/`3EFC` are reused by overlays, so hooks in that area
must verify the resident bytes before applying.  A non-guarded row-copy hook can
accidentally intercept a different overlaid compositor body.

## Fixes / hooks

- Added `1010:3E12 overkill_masked_sprite_composite_3e12`, collapsing the hot
  two-shift masked CGA sprite compositor used by the level-selection redraw.
- Added guarded strided-row-copy hooks for `1010:3EE1` and `1010:3EFC`.  These
  only run when the exact row-copy bytes are resident; otherwise they fall back
  to the interpreter for the current overlaid instruction.
- Added `1010:3EFB overkill_masked_sprite_composite_3efb`, collapsing the
  overlaid six-shift masked sprite compositor that became the dominant interpreted
  loop on the selection screen.
- Added fast dispatch hooks for `1010:5AC8` and `1010:5A92`, removing repeated
  interpreted mode/subtype dispatch overhead before the existing draw/present
  hooks take over.
- Added `1010:AA44 overkill_clc_ret_aa44` for the tiny hot success helper.
- Kept the earlier live-player hook policy change: dirty-copy hooks are enabled
  in interactive CGA, while the mode-0-only `58DF` hook remains disabled for
  non-CGA modes.

## Verification

Added oracle tests comparing the new hooks against interpreted ASM snippets:

- `test_masked_sprite_composite_3e12_hook_matches_interpreted_asm`
- `test_strided_row_copy_3ee1_and_3efc_hooks_match_interpreted_asm`
- `test_masked_sprite_composite_3efb_hook_matches_interpreted_asm`
- `test_dispatch_5ac8_and_5a92_hooks_match_interpreted_asm`
- `test_clc_ret_aa44_hook_matches_interpreted_asm`

Full result:

```text
65 passed in 2.95s
```

A 1.5M-step CGA profile now reaches further into the menu/gameplay rendering
path within the same step budget.  `1010:3EFB`, `1010:5AC8`, `1010:5A92`, and
`1010:AA44` are now replacement hooks instead of interpreted hot loops.

---

# Current run status — checkpoint 25

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `56 passed`.

This pass targeted the very slow menu/planet-selection renderer path shown by
profiling the live CGA menu loop after startup.

## Performance finding

With the interactive-safe hook set from checkpoint 24, the hottest interpreted
routine on this screen was `1010:4D15`: the presence/stamp-list helper used by
the menu/planet-selection object/cell bookkeeping.  A 5M-step profile from the
menu loop showed `4D15..4D61` dominating the interpreted address list before the
existing hook was allowed in the live player.

After enabling the fixed hook, `4D15` disappears from the interpreted hotspot
list.  The next interpreted hotspots are now `1010:017E` (keyboard poll bit
loop), `1010:CCAD..CCC0` (dirty-copy mode-1 body when the still-disabled dirty
hooks are off), and `1010:3E12..3E4E`.

## Fixes / hooks

- Reworked `1010:4D15 overkill_presence_stamp_list_4d15` into a faster local-loop
  hook instead of using CPU helper calls for every small operation.
- Fixed an uncovered mode-0 accuracy bug in the older `4D15` hook: the original
  `JNE 4D59` path stamps only the base cell and appends it to `DS:DI`; the stacked
  `+1A/+34/+4E` stores are mode-1 `JMP BP` paths only.
- Removed `4D15` from the interactive disabled-hook set after adding regression
  coverage for the mode-0 and final-skip paths.
- Removed `41A6` from the interactive disabled-hook set as well; it is already
  covered by an interpreted-ASM oracle test and is now the active fast path for
  the variable-width interlaced menu/screen blit.

## Verification

Added `test_presence_stamp_list_4d15_final_skip_and_mode0_flags_match_asm` to
cover the previously missing paths.  Full result:

```text
56 passed in 2.65s
```

---

# Current run status — checkpoint 24

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `55 passed`.

This pass fixes the accuracy regression in the fast 4-plane row expander and
continues the loading/sprite-phase lift where profiling showed the highest
remaining interpreted-instruction density.

## Accuracy fix

- **Fixed `1010:4537` fast row expander final `DX`.**  The optimized
  `_row_4537_core` incorrectly left `DX` as the entry value.  The original ASM
  loads `DL`/`DH` from plane 2/3 and then calls `45F6` four times; each call
  rotates the plane bytes by two bits, so after four calls the bytes return to
  their loaded values.  The hook now exits with `DX = (loaded_DH << 8) | loaded_DL`.
- Reconfirmed the 4537/4511 oracle tests and fuzz tests, then the full suite.

## Loading / sprite-phase performance lifts

- **New overlaid object-scan skip hooks** for the hot repeated loops around
  `A849`, `A861`, `A87C`, `A894`, `A8C7`, `A90F`, `A927`, `A9E0`, and `AA10`.
  These loops mostly scan inactive object slots during loading/render setup.
  The hooks consume skip-only iterations in Python and stop immediately before
  the original CALL when an active/matching object needs the existing ASM logic.
  Stack scratch from the balanced `PUSH CX`/`POP CX` pair is preserved.
- **New `1010:3849` hook** for the 4-column masked sprite composite loop, the
  wider sibling of the existing `38B7` hook.  It composites four mask/data word
  pairs per row and restores `DS` from `CS:[9596]` before returning.
- **New `1010:469F` hook** for the plain 9-byte × 16-row sprite copy loop.
- **New `1010:4D6F` hook** for the presence-list clear loop.

## Verification

Added self-contained oracle tests for the newly risky lifts:

- `test_masked_sprite_composite_3849_hook_matches_interpreted_asm`
- `test_sprite_copy_469f_hook_matches_interpreted_asm`
- `test_overlay_scan_a849_skips_inactive_entries_like_asm`
- `test_overlay_scan_a9e0_counter_and_skip_match_asm`

Full result:

```text
55 passed in 2.50s
```

## Profiling note

A 1.5M-step CGA profile after the new hooks reaches further into the sprite/game
phase within the same interpreted-step budget, so wall-clock numbers are not a
clean apples-to-apples boot benchmark.  The previous `A849`/`A8C7`/`A9E0` scan
addresses disappear from the interpreted-instruction top list; the next visible
hotspots are now the small bit loop at `017E`, the `CD8D` region, and far-call
code at `1F8F:0960`.

---

# Current run status — checkpoint 23

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `49 passed`.

This pass continues the source-port lift of hot routines (the core methodology),
applies the renderer-helper cleanup that was prototyped but not committed last
round, and keeps the focus on performance-relevant code.  CGA and Tandy
correctness preserved; no gameplay logic rewritten.

## What changed

- **New `1010:38B7` hook `overkill_masked_sprite_composite_38b7`.**  Profiling
  after the 477E lift showed this is now the hottest interpreted routine in the
  sprite-render phase (~15k samples per loop-body address).  It is the classic
  masked sprite composite `dest = (dest AND mask) OR data`, two 16-bit columns
  per row over `CX` rows: source row `[mask0,data0,mask1,data1]` (SI += 8/row),
  destination stride `0x34`, read-modify-write of the destination, exit to
  `38D0` with `CX=0` and FLAGS from the final `add di,30h`.  Lifted into a
  verified Python hook (DF-aware, `CX==0 -> 65536` handled).  New self-contained
  oracle test `test_masked_sprite_composite_38b7_hook_matches_interpreted_asm`
  plus a 2000-state differential fuzz: bit-identical to the interpreted loop.

- **`1010:4537` renderer helpers lifted to module level.**  The four per-call
  closures (`rol8`/`ror8`/`rcl8`/`rcl16_mem`) and the `pack_four_pixels` /
  `expand_bits` bodies are now module-level `_r_*` functions instead of being
  rebuilt on every call.  This makes the lifted source clearer and reusable —
  exactly the direction the source port wants — and is verified bit-identical to
  the previous implementation by a 3000-state fuzz and the existing 4537 oracle
  test.  (Note: this did not measurably change raw CPython speed; it was applied
  for source-port clarity and because it is correct, not for a speed number.)

## Impact of the sprite-render lifts (477E + 38B7)

Measured over a 2.5M-step window that reaches the sprite phase: `38B7` fires
~1,089 times and `477E` ~866 times, together removing ~292k interpreted
instructions (each call replaces 90-190 one-at-a-time Python opcode dispatches
with a single hook).  These routines dominate *sprite-heavy gameplay frames*
rather than the boot-to-menu path (which is bound by the already-hooked
`450C`/`4511`/`4537` asset expansion), so the benefit shows up as lighter
per-frame work during play, not as a faster cold boot.

## Honest note on raw boot speed

As measured last checkpoint, no safe micro-optimisation to the CPython
interpreter core moves cold-boot time meaningfully; the high-leverage lever for
overall speed remains running under PyPy (10-50x on this kind of dispatch loop,
zero code change, current path stays as fallback).  The per-routine lifts above
are still worthwhile: they advance the reverse-engineered source port *and* cut
real interpreted work in the hot rendering phase.

## EGA

Unchanged this pass (still the cyan/black plane-2/3-under-fill described in
checkpoint 22).  The diagnosis stands: not a palette problem; planes 2/3 are
under-filled upstream of the verified present/expansion hooks.  A fix needs EGA
planar-memory modelling and/or a corrected EGA source decode, deliberately
deferred to avoid destabilising the working CGA/Tandy modes.  Track it with
`python scripts/diag_video.py --video ega`.

---

# Current run status — checkpoint 22

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  This pass dug into the two open
complaints — "EGA still black/blue" and "performance still poor" — and reports
measured, evidence-based conclusions rather than speculative fixes.  `48 passed`.

## EGA: root cause narrowed (planar plane-fill, not palette)

`scripts/diag_video.py --video ega` now also reports EGA register activity.
Captured across the first several EGA presents:

- plane nonzero bytes stay lopsided every frame: plane0/1 ~1380-1500, but
  plane2/3 ~60-105 (persistent, not just the title frame);
- colour indices in use do grow over frames (up to `0,1,3,4,7,8,9,12,14,15`),
  so the output is not literally two colours — it is dominated by index 0
  (black, ~91%) and index 3 (cyan, ~9%), which reads as "black/blue";
- sequencer map-mask writes (`OUT 03C5h,01/02/04/08h`) are *balanced* across all
  four planes, and there are **zero** attribute-controller (`03C0h`) palette
  writes.

Interpretation: the palette is the fixed default (so colour *mapping* is not the
bug), and all four planes are addressed, yet planes 2 and 3 end up almost empty.
The verified `1010:4537` 4-plane row expander is bit-identical to the original
ASM (re-confirmed this pass by a 3000-state differential fuzz), so the missing
plane-2/3 data is **upstream** of the present/expansion hooks: either the source
bytes fed into the EGA decode, or an EGA-specific decode path, are not
delivering the high planes.  A real fix most likely needs the memory model to
represent EGA planar writes (map-mask routing into the four `A000` shadow
planes) and/or a corrected EGA source-decode — a sizeable feature that is
deliberately **not** attempted here so the working CGA and Tandy modes stay
untouched.  Use `diag_video.py --video ega` to track this as the EGA work
continues.

## Performance: measured ceiling, no free safe win

Clean A/B micro-benchmarks (1.5M boot steps, no profiler overhead) this pass:

- hoisting `4537`'s six per-call closures to module level: ~19.0s vs ~19.6s
  (no improvement — closure creation was not the bottleneck);
- guarding the interpreter's per-instruction disassembly f-strings behind
  `trace_enabled`: ~18.7s vs ~19.0s (within noise).

So the verified micro-optimisations that looked promising do **not** move the
needle and were not applied (to avoid churn/risk).  The interpreter is near its
CPython per-instruction ceiling (~80-140k interpreted-steps/sec) and the loading
path is bound by pure-Python pixel expansion (`450C`/`4511`/`4537`), which is
already a verified hook.  Realistic high-impact options, in order of
safety/leverage:

1. **Run under PyPy** — an interpreter dispatch loop like this typically gets
   10-50x for free with no code change; the current CPython path stays as the
   fallback.  This is the recommended lever for "performance is poor".
2. Skip the one-time ~11-15s asset-decode bootstrap during development with
   `python scripts/play.py --snapshot <dir>` (already supported).
3. Longer term: a dispatch-table interpreter core, or numpy/C vectorisation of
   the 4-plane expansion — both higher risk and deferred per the project's
   correctness-first rules.

The checkpoint-21 changes (the verified `1010:477E` sprite-blit hook, the dead
`prefixes` cleanup, the profiler, and the diagnostics) remain in place.

---

# Current run status — checkpoint 21

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Focus of this pass: profiling the asset-heavy loading path, one safe new
performance hook, and EGA/Tandy diagnostics.  CGA and Tandy correctness are
preserved; no gameplay logic was rewritten.

## What changed

- **New profiler `scripts/profile_hotspots.py`** (rewritten).  It samples the
  executed CS:IP every step and wraps every registered hook with a timing/
  counting shim, then prints a wall-clock breakdown of interpreter vs
  decode-hook vs present/graphics-hook time, the hottest CS:IP addresses, and
  the hooks ranked by cumulative time.  Counters live in the script, so the
  interpreter core stays clean.

      python scripts/profile_hotspots.py 3000000 --top 25
      python scripts/profile_hotspots.py 1500000 --video tandy

- **New `1010:477E` hook `overkill_sprite_blit_9x16_477e`.**  Profiling showed
  the single hottest *interpreted* routine during sprite-heavy loading is the
  fully-unrolled fixed-geometry blit at `1010:477E..480D`: it copies a 9-byte
  wide by 16-row sprite from `DS:SI` (source stride 52) into a packed `ES:DI`
  buffer, with `ES`/source-`DS` loaded from `CS:[9596]`/`CS:[9598]` and `DS`
  restored to `CS:[9596]` on exit.  The hook reproduces that exactly (registers,
  flags from the final `add si,2Bh`, the 144 copied bytes, near RET) and is
  verified against interpreted ASM for both `DF=0` and the `DF=1` fallback in
  `tests/test_overkill/hooks.py::test_sprite_blit_477e_hook_matches_interpreted_asm`.

- **Interpreter micro-cleanup in `cpu.py`.**  Removed a dead
  per-instruction `prefixes` list that was allocated on every `step()` but never
  read, and hoisted the segment-override prefix table to a module-level
  `_SEG_OVERRIDE` dict instead of rebuilding it per prefix byte.  No semantic
  change; the core regression suite still passes.

- **New diagnostics `scripts/diag_video.py`.**  Runs the original code to the
  first frame-present in the requested mode and reports, for EGA, the nonzero
  byte count of each of the four `A000` shadow planes and the full 16-colour
  index histogram; for Tandy/CGA the packed nibble/2bpp histogram.

      python scripts/diag_video.py --video ega
      python scripts/diag_video.py --video tandy

## Profiling finding (loading path)

In a 1.5M-step CGA boot window the wall-clock split was roughly interpreter
31% / decode-hooks 68% / present 1%.  The decode-hook time is dominated by the
already-verified 4-plane expansion driver `1010:450C`
(`overkill_expand_4plane_list_450c`) and the per-block renderer it calls,
`1010:4511`.  The hottest *interpreted* region is the `1010:A849..A9E0` sprite
dispatcher that calls `1010:477E`.  The new 477E hook removes the unrolled-MOVS
body of that dispatcher (~96 interpreted instructions per call) but, because
477E is only ~2-3% of boot steps, the headline boot time is still governed by
the 450C/4511 expansion phase.  Speeding that up further would mean optimising
the existing renderer hook rather than adding new ones, which is deferred to
keep the verified path intact.

## EGA diagnostic finding (supersedes the "only one plane" hypothesis)

`diag_video.py --video ega` at the first EGA present (reached ~2.34M steps,
stopping around `1010:D013`) reports:

- plane 0 nonzero = 1378/8000, plane 1 = 1461/8000, plane 2 = 87/8000,
  plane 3 = 95/8000;
- colour indices actually used = `0, 2, 3, 8, 12, 14` (index 0 = 90.8%,
  index 3 = 8.9%, the rest < 0.3%).

So the renderer *is* combining multiple planes (indices 3/12/14 require more
than one plane), which **refutes** the earlier "only plane 0 / only indices
0,1" theory.  The real symptom is that planes 0 and 1 carry almost all the data
while planes 2 and 3 are nearly empty, so the first presented EGA frame is
cyan(index 3)-on-black - consistent with the "black/blue" report but now
quantified.  Open question: whether planes 2/3 are legitimately sparse for this
particular (title/loading) frame or are being under-filled upstream.  Capturing
several EGA presents with `diag_video.py` is the recommended next EGA step.

## Tests

`48 passed` (was 47; one new self-contained 477E differential test).  Run with:

    python -m pytest -q

Compile check:

    python -m py_compile scripts/profile_hotspots.py scripts/diag_video.py \
        cpu.py overkill/hooks.py

## Still unknown / next

- EGA: are planes 2/3 under-filled, and where (compare several presents)?
- Loading speed is now bounded by the 450C/4511 4-plane expansion hook; any
  further win there must stay a verified transliteration.
- CGA and Tandy remain the correctness oracles and were not changed.

---

# Current run status — checkpoint 20

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Commands used in this pass:

```bash
python -m py_compile scripts/play.py scripts/render_frame.py runtime.py overkill/hooks.py
python -m pytest -q
python scripts/render_frame.py artifacts/play_tandy_edrax_orbit_combat_20260611_214016 --video cga --out artifacts/evidence/test_cga.png
python scripts/render_frame.py artifacts/play_tandy_edrax_orbit_combat_20260611_214016 --video ega --out artifacts/evidence/test_ega.png
```

Result:

- tests pass: `43 passed`,
- `create_runtime(..., command_tail=...)` can now pass a DOS PSP command tail to
  the original executable,
- `scripts/play.py` has `--video cga|ega`; `--video ega` launches the original
  code with the documented `/E` command-line selector,
- EGA mode uses the original mode-1 present path at `1010:2750`, which writes to
  `A000h` through the EGA sequencer map-mask mechanism,
- because the project memory model is a flat bytearray, the new `1010:2750`
  replacement stores the presented EGA frame in explicit shadow planes inside
  the `A000h` aperture (`+0000/+2000/+4000/+6000`),
- `scripts/render_frame.py` and `scripts/play.py` can decode that EGA shadow layout
  as 320x200 16-colour RGBI/EGA output,
- CGA remains the default and still uses the previously stabilized B800h pacing
  path.

Useful commands:

```bash
python scripts/play.py --game-hz 30
python scripts/play.py --video ega --game-hz 30
```

If intro/menu speed needs tuning independently from gameplay, use:

```bash
python scripts/play.py --video ega --game-hz 30 --retrace-hz 60
```

---

# Current run status — checkpoint 19

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Commands used in this pass:

```bash
python -m pytest -q
```

Result:

- tests pass: `41 passed`,
- added 8086 opcode `27h` / `DAA` to `cpu.py`,
- confirmed this is not simply a stray VM/IP leak: the loaded runtime overlay rewrites
  `1010:5F18` from the startup byte `C6` into a legitimate `DAA` sequence, and
  previous snapshots already contain `27` at that address,
- added focused BCD adjust tests for the score/text digit path around
  `1010:5F18`, including `DAA` carry propagation after `ADD AL,imm8`.

The intro/menu retrace pacing from checkpoint 18 remains in place.  If the player
now reaches the same path, it should no longer crash on `Unsupported opcode 27 at
1010:5F18`.

Useful command:

```bash
python scripts/play.py --game-hz 30
```

If intro/menu speed needs tuning independently from gameplay, use:

```bash
python scripts/play.py --game-hz 30 --retrace-hz 60
```

---

# Current run status — checkpoint 18

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Commands used in this pass:

```bash
python -m pytest -q
python scripts/play.py --game-hz 30
```

Result:

- tests pass: `39 passed`,
- the latest player no longer assumes that gameplay's `1010:0679` timer wait is
  the only timing source,
- `1010:50C9` VGA retrace waits are now paced in `scripts/play.py` as well,
  because intro/menu/transition code uses that path for visible delays,
- B800h is checksummed and Tk receives a new immutable snapshot only when the
  visible screen changed, which prevents static retrace delay loops from
  flooding the UI with duplicate frames,
- `1010:58DF` is disabled in interactive play by default so its internal direct
  calls to the 50C9 helper do not bypass the retrace pacing wrapper,
- the previous unsafe dirty/render hooks remain disabled by default:
  `1010:41A6`, `1010:4D15`, `1010:CCAA`, `1010:CCC4`, `1010:CCF0`.

Controls (`scripts/play.py`): **Q up, A down, O left, P right, Z / Space fire, Esc quit.**

Useful command:

```bash
python scripts/play.py --game-hz 30
```

If intro/menu is too slow or too fast, tune the VGA wait pacing separately:

```bash
python scripts/play.py --game-hz 30 --retrace-hz 60
```


## 2026-06-10 EGA performance update

- EGA mode now has additional verified hooks for the hot mode-1 row conversion
  path: `280D`, `2824`, `291C`, and `2932`.
- These are narrow replacements of known loops, not broad renderer guesses.
- The visible EGA output is still using the current A000 shadow-plane renderer;
  the reported blue/black menu suggests there is still more EGA palette/plane
  investigation to do, but the new hooks target the slow startup/menu path.
- Test suite: `47 passed`.

### 2026-06-10 Tandy video mode experiment

`scripts/play.py` now accepts `--video tandy` and passes the original documented
` /T` PSP command-tail selector to the game.  The live player wraps the mode-2
presenter at `1010:3354` as a frame boundary and renders the Tandy/PCjr
320x200x16 packed aperture from `B800h`.

Implemented pieces:

- `1010:3354 overkill_present_tandy_frame_3354` mirrors the original mode-2
  presenter: `52` words (`104` bytes) per row, `192` rows, starting at `00A0h`,
  with the Tandy four-bank row stepping (`+2000h`, wrap with `+80A0h`).
- `render_tandy_ppm()` decodes the Tandy layout as two 4-bit RGBI pixels per byte
  with scanlines split as `(y & 3) * 2000h + (y >> 2) * 160`.
- `scripts/render_frame.py --video tandy` can render snapshots using the same
  decoder.

The regular test suite remains green (`47 passed`).  This is intentionally an
experimental third video mode rather than a replacement for fixing the remaining
EGA plane/palette issue.

### 2026-06-10 Tandy selector fix

The first Tandy experiment passed the documented ASCII `/T` switch directly to
`OVERKILL.UNLZEXE.EXE`.  That is not what the already-unpacked inner executable
expects: its startup parser reads `PSP:82` as a compact binary video selector
(`0=CGA`, `1=EGA`, `2=Tandy`).  ASCII `/T` therefore looked like an out-of-range
selector and fell back to EGA, while `play.py` was watching the Tandy `B800h`
aperture, producing black frames.

`play.py --video ega` and `--video tandy` now pass the inner binary selector
instead:

- EGA: `bytes((0x0D, 0x01))`
- Tandy: `bytes((0x0D, 0x02))`

The `--dos-args` escape hatch remains for raw ASCII PSP-tail experiments.

## 2026-06-13 BEC5 variant 000A owner-linked collision tail

`snapshot_play_tandy_20260613_000648` reached `BC4B -> 62F6 -> BEC5` with a
collided slot whose logic/variant field was `000Ah`.  The original does not
have a dedicated 000A handler; after the 7/8/0C/9 table and the 2/6/5 checks it
compares the current object BP with `DS:[BX+30h]`.  A match marks the collided
slot as linked to the current object, clears `DS:[BX+1Ch]`, clears
`SS:[BP+20h]` when `A8C2 != 1`, and jumps into the shared `BFC7` transition
path.

- `_run_collision_handler_bec5_observed` now models that owner-linked fallback.
- Added a regression that advances the captured snapshot to the 53rd `BC4B`
  call and compares the lifted hook against interpreted original ASM with full
  memory equality.

## 2026-06-13 refactor pass: replacements staging split

- Moved shared OVERKILL 8086-style arithmetic/string helpers out of
  `overkill/hooks.py` into `overkill/asm.py`.
- Moved the large gameplay object/postmove/collision behavior island out of
  `overkill/hooks.py` into `overkill/gameplay/object_runtime.py`.
  The address-facing hook wrappers remain in `overkill/hooks.py` and import the
  lifted game logic back, preserving the hook-registration boundary.
- Added `1010:30BA overkill_tandy_patched_row_copy_30ba`, a signature-guarded
  hook for the runtime-patched Tandy row copier that was showing up as the
  `30C3/30C4/...` unknown hotspot cluster.  The old static bytes at `30BA` are
  not stable; if the patched row-copy signature is not resident, the hook
  interprets the current original instruction instead of guessing.
- Added `1010:30B0 overkill_tandy_interlaced_clear_30b0` for the static startup
  Tandy interlaced clear routine.
- Validation: `python scripts/run_tests.py` => `161 passed, 0 failed`.
- Live verification: `scripts/play.py --verify-hook 1010:30BA --verify-stop-on-diff`
  verified 25 calls before the smoke run timeout, with `1010:30BA` averaging
  about 112.68 ASM-equivalent instructions/call.

## 2026-06-13 video-mode label audit

- Audited CGA-labelled hooks seen during Tandy gameplay.
- Confirmed `1010:5A00`, `1010:5A24`, and `1010:5A36` are shared video-mode dispatch helpers. They select CGA/EGA/Tandy behavior through `CS:[95BC]`, so their registered hook names were changed from `overkill_cga_*` to neutral coordinate names while keeping old aliases for tests/tools.
- Reclassified `1010:4D15` and `1010:4D6F` from `cga_renderer` to `layer_sprites`: these are shared presence/occupancy-list stamp/clear helpers used by Tandy gameplay too. Mode 1 has EGA-style stacked-cell handling; CGA/Tandy share the non-mode-1 base-cell path.
- Short Tandy snapshot coverage smoke now reports zero `cga_renderer` calls for the intro/dirty-cell presenter path; shared hooks show under `coordinates`, `layer_sprites`, or `tandy_renderer` as appropriate.


## 2026-06-13 - Unknown gameplay/collision hook absorption

Absorbed several hot unknown/gameplay instructions without duplicating existing logic:

- `1010:AED8 overkill_object_behavior_aed8` now hooks the observed logic-id 2/3 countdown/movement behavior and reuses a shared `AD60` bounds/tile tail.
- `1010:AD04 overkill_object_logic_branch_ad04` is only a branch selector: it returns or jumps to existing `ABxx` behavior tails, rather than reimplementing those tails.
- `1010:AC81 overkill_object_slot_scan_guard_ac81` is only the guard/setup for the already-lifted `AC97` object-slot scan and directly reuses `run_object_slot_scan_ac97`.
- `1010:AE09 overkill_object_behavior_ae09` handles the observed logic-id `0Ch` timer/3-pixel movement behavior, then reuses the same shared `AD60` tail as `AED8`.

The previous inline `AD60` implementation inside `AED8` was refactored into `_run_object_bounds_tile_tail_ad60` so new behaviors do not clone the same bounds/tile/deactivation logic.

Validation: `python scripts/run_tests.py` => `162 passed, 0 failed`; `python -m compileall -q dos_re overkill tests scripts`; live hook verifier samples were recorded for `AC81`, `AD04`, `AE09`, and `AED8` and added to `artifacts/hook_coverage_cache.json`.

## 2026-06-13 startup renderer table unknown absorption

- Identified the `1010:0F31/0F32/0F37` unknown startup cluster as the inner loop
  of `1010:0F0B`, a renderer coordinate/video lookup-table builder.
- Added `1010:0F0B overkill_startup_coordinate_tables_0f0b` in the renderer
  module.  The hook generates the `DS:99C8..A077` table family and reuses the
  existing `1010:0FA3` lifted helper for the fallthrough table builder, avoiding
  a second implementation of the same `0FA3` logic.
- Regression oracle `snapshot_stop_1010_0f0b_startup_tables` compares the lifted
  hook against fully interpreted ASM through continuation `1010:526A` with full
  CPU and memory equality.
- Validation: `python scripts/run_tests.py` => `163 passed, 0 failed`.
- Live verification: `scripts/play.py --video tandy --verify-hook 1010:0F0B
  --verify-stop-on-diff` verified the cold-start call with no divergence before
  the smoke timeout.
- Remaining cold-start unknowns around `32FF:0052` belong to the transient
  unpack/relocation bootstrap segment, not to a stable game island.  I did not
  hook them because the segment is dynamically loaded and not useful as a game
  module boundary.

## 2026-06-13 documentation/methodology refresh

Updated the project documentation to describe the now-established source-port
method as a reusable system rather than a pile of one-off OVERKILL fixes.

Main documentation changes:

- Added `docs/dos_re/source_port_methodology.md`, the canonical playbook for the
  evidence-driven workflow:
  `observe -> classify -> choose boundary -> build ASM oracle -> implement hook -> verify -> document -> move to island`.
- Updated `AGENTS.md` with the canonical workflow, the current island-module
  layout, the staging rule for `overkill/hooks.py`, and the requirement to search
  for existing tails/helpers before implementing a new hook.
- Removed a duplicated `CPU Interpreter Rules` section from `AGENTS.md`.
- Updated `README.md` with the methodology loop, current island examples, and a
  pointer to the new methodology document.
- Updated `docs/overkill/design.md` with the current `overkill/` module map and the
  migration path from original ASM to staged hook to island module.
- Replaced the stale `docs/overkill/next_steps.md` bootstrap-era TODO list with current
  priorities: meaningful unknown absorption, keeping `overkill/hooks.py` as
  staging, duplicate-code prevention, intentional verification modes, and island
  documentation hygiene.

No runtime code changed in this pass.

## 2026-06-13 logic-pyramid documentation and bootstrap classification

- Added the end-goal source-port pyramid to `docs/dos_re/source_port_methodology.md`,
  `docs/overkill/design.md`, `README.md`, `AGENTS.md`, and `docs/overkill/next_steps.md`:
  original binary oracle -> ASM-compatible hook/runtime -> verified lifted
  routine -> runtime object/data model -> game systems -> gameplay archetypes ->
  semantic game model -> modern/enhanced port layer.
- Clarified that current object work is mostly still layer 4: slots with
  sprite/layer/logic-id/movement/collision fields.  Player/projectile/enemy/boss
  names should emerge only after multiple verified routines support them.
- Added a `bootstrap` coverage island for the transient `32FF:*` cold-start
  unpack/self-relocation segment.  This makes the dashboard more honest: these
  instructions are no longer `unknown`, but they are also not a game-module island
  to hook prematurely.
- Added `32FF:0052 inner_unpack_relocation_bootstrap_32ff_0052` to
  `symbols.json` as `classified-do-not-hook`.
- Validation: `python scripts/run_tests.py`; `python -m compileall -q dos_re overkill tests scripts`.

## 2026-06-13 crystallization methodology integration

Integrated the user-supplied methodology dump into durable project docs.

Updated:

- `docs/overkill/source_port_methodology.md` with the full evidence ladder: original
  oracle, layer ownership, dependency direction, promotion rules, vertical
  slices, definitions of done, AI task framing, and hard anti-chaos rules.
- `docs/overkill/island_truth_tables.md` as the new per-island confidence/evidence index.
- `AGENTS.md` with hard layer boundaries, task framing examples, dependency
  direction, and the requirement that every semantic name remains reversible to
  original ASM evidence.
- `README.md`, `docs/overkill/design.md`, and `docs/overkill/next_steps.md` to point future work at
  the crystallization model and island truth tables.

No runtime behavior changed. Validation: `python -m compileall -q dos_re overkill tests scripts`; `python scripts/run_tests.py`.

## 2026-06-13 unknown/island cleanup continuation

Continued the evidence-driven cleanup after the crystallization-methodology pass.

Runtime changes:

- Added `1010:5A6C overkill_menu_cell_source_blit_dispatch_5a6c`, a shared
  source-cell video-mode dispatch stub used by the dirty-cell presenter.  It is
  classified under `layer_sprites`, not CGA/Tandy-specific rendering, because it
  only reads `CS:[95BC]` and jumps through the mode table.
- Registered/lifted `1010:AB10 overkill_object_logic_ab10` using the live
  runtime-patched byte shape.  The deactivation path through `AC22` is now
  modelled instead of fail-fast.
- Added `1010:AB77 overkill_object_behavior_ab77` as an observed object-behavior
  driver.  It deliberately reuses existing `AB4F`, `AC28`, and `AC81/AC97`
  helpers and preserves original continuations for still-unlifted tails.
- Added `1F8F:0922 overkill_gameplay_counter_tick_1f8f_0922` and the new
  `game_state` coverage island.  This routine lives in an overlay segment but is
  per-frame/game-state counter logic, not asset decoding.
- Moved the `1010:0679` timer wait implementation out of `overkill/hooks.py` into
  the sound/timer island and added the companion `1010:0672` clear-timer-flag
  hook there.
- Added `1010:511F overkill_video_page_toggle_511f`, a shared per-frame video
  page stub.  It is a no-op return in Tandy/CGA but toggles the mode-1 visible
  page state.

Classification changes:

- `1010:D007..D04C` is now classified as the main gameplay frame-loop dispatcher
  under `game_state`, not raw unknown code.
- `1010:A846/A85E/A876` and `1010:4CED..4D14` are classified as layer-sprite /
  presence-list parent frontiers.  They are not hooked yet because they should be
  composed from existing `A849/A861/A87C/4D15` helpers rather than duplicated.

Validation:

- `python -m compileall -q dos_re overkill tests scripts`
- `python scripts/run_tests.py` => `165 passed, 0 failed`
- `scripts/play.py --snapshot artifacts/snapshot_play_tandy_20260613_000648
  --verify-hook 1010:0672 --verify-hook 1010:0679 --verify-hook 1010:511F
  --verify-hook 1F8F:0922 --verify-hook 1010:AB77 --verify-hook 1010:AB10
  --verify-hook 1010:5A6C --verify-stop-on-diff --verify-max 250` reached the
  verifier limit with no divergence.

## 2026-06-13 layer-sprite present parent cleanup

Continued the unknown/island cleanup by absorbing the A90C/A93C/4D64 present-scan
frontier without duplicating the underlying renderer/presence loops.

Runtime changes:

- Added `1010:A90C overkill_present_object_scan_pair_a90c`, the two-table
  present parent.  It sets `CX=22h` and reuses the existing `A90F` scan over
  `DS:8D12`, then sets `CX=24h` and reuses the existing `A927` scan over
  `DS:32CA`.  If either child scan finds an active entry, the hook preserves the
  original partial continuation at the real `CALL 5A92` site.
- Added `1010:A93C overkill_present_scan_clear_presence_a93c`, modelling the
  tiny `CALL 4D64 ; RET` parent.
- Added `1010:4D64 overkill_clear_presence_list_parent_4d64`, the setup parent
  for the already-lifted `4D6F` presence-list clear loop.  It sets
  `ES=CS:[9598]`, `SI=C7B1h`, and `CX=28h`, then tail-runs the existing `4D6F`
  hook.
- Classified the next `D04D..D072` per-frame state/UI cluster under
  `game_state` rather than leaving it as raw unknown.  It is still a larger
  frontier, not a safe small hook.

Validation:

- `python -m compileall -q dos_re overkill tests scripts`
- `python scripts/run_tests.py` => `165 passed, 0 failed`
- `1010:A90C` verified for 50 calls from `artifacts/evidence/snapshot_stop_1010_a90c`.
- `1010:A93C` verified for 10 calls from `artifacts/evidence/snapshot_stop_1010_a93c`.
- `1010:4D64` verified on its direct stop snapshot.

## 2026-06-13 next unknown cleanup: pacing loops, postmove prelude, loading scroll, counters

Continued the evidence-driven unknown cleanup after the A90C/A93C/4D64 layer-sprite pass.
The focus was small, composable hooks that remove meaningful unknown coverage without
collapsing larger orchestration boundaries or duplicating existing lifted logic.

Runtime changes:

- Added `1010:96C5 overkill_intro_retrace_delay_loop_96c5` and companion
  `1010:96C8 overkill_intro_retrace_delay_loop_tail_96c8`.  This is the
  intro/menu fixed-count `CALL 50C9 ; LOOP` delay.  The hook calls the installed
  `50C9` hook instead of the base implementation so interactive `play.py` keeps
  its visual pacing/publish boundary.
- Added `1010:BC45 overkill_object_postmove_prelude_bc45`.  This tiny collision
  prelude adds `DS:[A278]` into `SS:[BP+02]`, then reuses the shared `BC4B`
  postmove/collision chain.  The hook performs the final near return exactly like
  the interpreted fallthrough path.
- Added `1010:4E0D overkill_tandy_loading_scroll_until_4e0d`, the loading-scroll
  parent around the existing lifted `A781` step.  It preserves `SI/DI`, loops
  until `DS:[2350] <= DI` and `DS:[234E] == 0`, then stores `SI` into `DS:[A978]`.
  The nested return IP is intentionally `4E12`, matching the original stack scratch.
- Added `1010:61CA overkill_decrement_first_active_counter_scan_61ca`, the hot
  inner scan over `DS:2368..2372` word counters.  It decrements the first non-zero
  counter and returns when all are zero.  The `1010:61C5` parent remains available
  for callers that enter before loading `DI=2368`, but real hot gameplay calls
  commonly enter directly at `61CA`.

Anti-duplication notes:

- `96C5` does not inline the retrace/publish wait; it composes the installed
  `50C9` hook.
- `BC45` does not copy the postmove/collision chain; it delegates to the existing
  `BC4B` implementation.
- `4E0D` does not clone the loading-scroll step; it calls the existing lifted
  `_loading_scroll_step_a781`.
- `61CA` is the shared scan core used by the `61C5` parent and direct hot callers.

Validation:

- `python -m compileall -q dos_re overkill tests scripts`
- `python scripts/run_tests.py` => `167 passed, 0 failed`
- Live hook verifier coverage was checked for `1010:96C5`, `1010:BC45`,
  `1010:4E0D`, and `1010:61CA` with no divergence in the exercised snapshots.

Remaining useful frontiers:

- `1010:9FEA` appears to be an object/table coordinate update helper.  Build a
  direct oracle before naming it as movement or object-runtime logic.
- `1010:5EF9` looks like a small text/nibble rendering helper around `5F06`.
- `1010:4D95` is likely another presence-list parent and should compose `4D15`.
- `1010:780E` is a Tandy/layer draw sub-loop candidate.
- `1010:8A7E` is object-behavior frontier; do not promote to enemy/projectile
  semantics until child helpers and evidence traces converge.

## 2026-06-13 island classification sanity pass

Goal: keep the current work in the strict first/lifted-routine layer and make
island ownership match observed behavior rather than historical address names or
segment residence.

Corrections made:

- `startup_graphics.py` moved from `asset_codecs/` to `rendering/startup_graphics.py`.
  The routines there materialize renderer/startup tables and graphics buffers;
  they are not asset codecs just because they run during loading.
- `1F8F:0960` moved from overlay/asset ownership to `gameplay/game_state.py` and
  registered as `overkill_gameplay_counter_stride_loop_1f8f_0960`.  It lives in
  an overlay segment, but it updates gameplay counters, so segment residence is
  not the island classifier.
- Coverage now has separate `overlay` and `startup_graphics` dashboard islands.
- Coverage exact-address sets are tested to be non-overlapping, and every
  registered hook is tested to classify to a non-`unknown` island.
- `scripts/audit_islands.py` now uses the same `OverkillCoverageClassifier` as
  the live dashboard, so audit output and runtime coverage cannot silently drift
  apart.

Current first-layer rule reinforced:

- Keep hook names technical and evidence-based.
- Do not introduce semantic names such as concrete enemies/projectiles while we
  are still only proving runtime object-slot behavior.
- Move stable lifted behavior out of `overkill/hooks.py` into the correct island,
  but keep `overkill/hooks.py` as address-facing hook glue and compatibility
  aliases only.

Validation:

```text
python -m compileall -q dos_re overkill tests scripts
python scripts/run_tests.py
169 passed, 0 failed
```

Smoke coverage with dummy SDL now reports cold-start startup materialization as
`startup_graphics` instead of `asset_codecs`/`tandy_renderer`, and `overlay` is
reserved for the real `254A:*` overlay helpers.
## 2026-06-13 - Hook wrapper refactor / naming audit

- Moved asset/loading codec hook wrappers from `overkill/hooks.py` to
  `overkill/hook_wrappers/asset_codecs.py`.
- Kept `overkill.hooks` as the compatibility aggregate import that
  registers all hooks and re-exports existing test imports.
- Normalized registry labels so all 222 registered hooks include an address
  suffix.
- Removed semantic-noise `_fast` from the two asset-codec registry labels where
  it described implementation speed rather than original-game behavior.
- Added `docs/overkill/hook_naming_audit.md` with the current naming rules and next safe
  extraction targets.
- Verification: `python -m pytest -q` => 185 passed;
  `python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 --verify-max 1000 --fast-ranges` => OK.



## 2026-06-13 - Hook wrapper refactor pass 2

- Extracted shared hook-wrapper mechanics from `overkill/hooks.py`
  into `overkill/hook_wrappers/common.py`:
  runtime-patched-code guard plus near-CALL wrapper helpers.
- Moved text-rendering hook wrappers into
  `overkill/hook_wrappers/text.py`.
- Moved timer/PC-speaker hook wrappers into
  `overkill/hook_wrappers/sounds.py`.
- `overkill.hooks` remains the aggregate hook-registration surface.
- Renamed misleading shared layer-sprite registry labels:
  `768E`, `75A6`, and `7746` no longer claim Tandy-only ownership.
- Registered hook count remains 222.
- Verification: `python -m pytest -q` => 185 passed;
  `python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 --verify-max 1000 --fast-ranges` => OK.

Next safe extraction target is still renderer wrappers, but split it carefully:
move Tandy-only wrappers separately from shared layer-sprite scan/dispatch glue.
Do not collapse object behavior names into gameplay semantics until trace evidence
proves the object role.

## 2026-06-13 — hook cleanup pass 3: duplicate pruning and label alignment

- Renamed three asset-codec wrapper functions so decorated Python names match
  the registry labels: `overkill_file_checksum_loop_c916`,
  `overkill_packed_read_byte_0624`, and `overkill_packed_read_word_le_0615`.
- The older unsuffixed compatibility aliases were later removed; use the canonical address-suffixed names.
- The stale duplicate implementation in `overkill/asset_codecs/startup_graphics.py` was first reduced to a shim and later removed; startup graphics helpers now live only in `overkill/rendering/startup_graphics.py`.
- Static hook audit now reports 222 hooks and no function/registry-label
  mismatch.


## 2026-06-13 — runtime-code variant exhaustion policy

- Promoted runtime-patched code from an ad-hoc hook guard into an explicit
  `overkill/runtime_code.py` manifest.
- `1010:5E42` now has named live-byte variants:
  - `gameplay_object_steer_5e42` — hooked/verified movement helper observed in
    `runtime_code_5e42_gameplay_20260613_220042`.
  - `cold_display_helper_5e42_prefix` — known cold executable body at the same
    address, intentionally not valid for the movement hook.
- Removed the previous behavior where the 5E42 hook could silently run the live
  original body when bytes did not match.  Known-wrong or unknown bytes now raise
  `UnknownRuntimeCodeVariant`.
- Added optional `Memory.write_watchers` and `RuntimeCodeWriteTracer` for tracing
  who writes into runtime-code regions without enabling it in normal gameplay.
- Added `scripts/trace_runtime_code_writes.py` with `--no-hooks` and `--all-code`
  for cold-start code-materialization audits.
- Added runtime-code tests proving cold/gameplay variant distinction, unknown
  byte fail-fast behavior, and write-tracer event capture.

Validation:

```text
pytest -q
196 passed
python scripts/verify_hooks_headless.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --verify-max 300 --fast-ranges --coverage
OK HOOK VERIFY LIMIT REACHED verified=300
```

## 2026-06-13 — runtime-code staticization scaffold

- Promoted runtime-code handling from variant fail-fast only to an explicit
  staticization manifest.
- `overkill/runtime_code.py` now models `RuntimeCodeSlot`, accepted/rejected
  `RuntimeCodeVariant` records, and `RuntimeCodeStaticization` targets.
- `1010:5E42` is now recorded as a polyvariant code slot whose accepted gameplay
  body is staticized into
  `gameplay.object_runtime.run_runtime_patched_object_steer_5e42`.
- Added `scripts/audit_runtime_code_staticization.py`:
  - `--check` verifies that accepted runtime-code variants have static Python
    owners.
  - `--strict-installers` additionally requires writer/installer provenance and
    is intended as the final 100% exhaustion gate.
- `trace_runtime_code_writes.py --dump-final-variants` now reports the final live
  digest/variant for registered runtime-code slots after stepping.
- Added `docs/overkill/runtime_code_staticization.md` as the policy/playbook for turning
  runtime self-modifying code into named, flat source-port logic.

Important status:

- Source-port staticization gate passes for the current known slot.
- Strict installer gate intentionally still fails for `1010:5E42` until the
  cold-start writer that materializes the gameplay body is traced and named.

## 2026-06-13 — hot unknown cleanup after runtime-code staticization

- Absorbed two misleading hot/problematic interpreted regions that were not new
  runtime-patched bodies:
  - `1010:61F7` now hooks the hot `CALL 61C7; LOOP 61F7` status-counter glue.
  - `1010:5EDB` now hooks the HUD/status text block that composes `518C`, `5EF9`,
    and `5F06`.
- Corrected the old `1010:61C5` countdown hook metadata: `61C5` is inside the
  preceding CALL immediate in the materialized runtime body.  The real routine
  entry is `1010:61C7` (`MOV DI,2368h`).
- The new `61F7` hook preserves nested CALL stack scratch and leaves FLAGS from
  the final scan, matching interpreted ASM memory/state oracle checks.
- The new `5EDB` hook preserves intermediate CALL return scratch and tail-runs
  the final `5EF9` helper so the caller's original return address is consumed by
  the same boundary as the original code.
- No additional runtime-code slot was identified in this pass; these removals are
  static hot-region absorption, not self-modifying Python behavior.

Validation:

```text
python scripts/audit_runtime_code_staticization.py --check
ok; 1010:5E42 remains the only registered runtime-code slot, staticized with
installer provenance still pending

python -m pytest -q
201 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --verify-max 800 --fast-ranges --coverage
OK HOOK VERIFY LIMIT REACHED verified=800
```

## 2026-06-13 runtime-code census: 5E42 is bootstrap materialization, not video selection

Investigated whether the currently known runtime-patched code is actually a
video/sound/input selector that can be retired by committing to Tandy-first.

Result:

- `1010:5E42` is installed by the transient `32FF:*` inner unpack/self-relocation
  bootstrap, specifically `writer=32FF:009B`.
- The installer writes 211 bytes into `1010:5E42-5F1A`.
- CGA, EGA, and Tandy command tails all receive the same final variant:
  `gameplay_object_steer_5e42`.
- Therefore `5E42` is not a video-card, sound-card, keyboard, joystick, or
  Amstrad-joystick selector.  It is a bootstrapped gameplay/object steering body
  that is already staticized as flat Python.
- The actual video-mode choice observed in the same census is a data/config word
  in the code segment: `CS:95BC = 0000/0001/0002` for CGA/EGA/Tandy.  That can
  be lifted later into high-level Tandy configuration; it is not executable SMC.

Added `scripts/audit_runtime_code_census.py` to make this repeatable:

```bash
python scripts/audit_runtime_code_census.py --video all --steps 250000 --show-bootstrap
```

Updated the runtime-code manifest so strict installer audit now passes:

```bash
python scripts/audit_runtime_code_staticization.py --check --strict-installers
```

Validation:

```bash
python -m pytest -q
# 202 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --verify-max 800 --fast-ranges --coverage
# OK HOOK VERIFY LIMIT REACHED verified=800
```

## 2026-06-14 — menu AdLib/runtime hook lift pass #2

Continued lifting from the Tandy + AdLib main-menu snapshot profile
`snapshot_play_tandy_20260614_134931`.

Added lifted hooks for the remaining high-frequency optional AdLib driver glue:

- `2032:0000` far-call entry (`CALL 0063; RETF`), now used directly by the
  lifted `1010:06E5` timer ISR when `DS:0055 == 1`.
- `2032:0409` page/pause gate hot no-op path.
- `2032:0244` disabled per-channel accumulator helper.
- `2032:02AA` no-pending-note helper.
- Extended `2032:00CD` to cover the common countdown/no-op helper chain:
  `DEC [DI+1]; CALL 0244; CALL 02AA; CALL 02C9; CALL 02F6; RET` when the
  countdown remains non-zero and all helpers are idle.
- Added `1010:558B` as a one-idle-iteration main-menu wait-loop hook so menu
  idle polling no longer burns interpreted ASM on repeated no-key scans.
- `1010:06E5` no longer falls back to the interpreted optional-driver far call;
  it preserves the original far-call stack shape while dispatching through the
  lifted `2032:0000`/`2032:0063` path.

Measured on 100 delivered timer ticks from the supplied main-menu snapshot:

```text
before this pass, after previous AdLib lift: 6,127 interpreted instructions
after this pass:                            2,901 interpreted instructions
```

The remaining interpreted `2032:*` instructions are now mostly actual AdLib
bytecode/music advancement (`2032:00CD-0133` and `2032:0181-0290`), not generic
PIT/YM3812 delay glue.

Validation:

```bash
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 227 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_runtime_check
# reached 1010:D007; steps=21499
```

## 2026-06-14 — AdLib smoothness / pacing pass

Investigated the Tandy + AdLib main-menu path after hook coverage reached ~99%.
At this point the remaining ASM percentage is too small to explain visibly slow
music by itself; the more likely cause was interactive pacing/audio buffering:

- `1010:50C9` is a hardware retrace wait, not the `1010:0679` game-timer frame
  wait.  The live viewer previously defaulted retrace pacing to `--game-hz`
  (~36.4 Hz), which made intro/menu idle paths slower than a real display
  retrace cadence.  The default retrace pacer is now 60 Hz, still overrideable
  with `--retrace-hz` for diagnostics.
- `TimerPacer` now performs a final cooperative poll at the sleep deadline.  This
  keeps the async real `1010:06E5` IRQ0/AdLib ISR from missing a deadline tick
  when a retrace sleep lands exactly on the PIT boundary.
- The optional Nuked-OPL3 SDL backend now uses a slightly larger mixer buffer in
  AdLib mode, starts with current+queued PCM chunks, exposes `--adlib-chunk-ms`,
  and reports underrun counts in the window caption if the SDL queue starves.

Useful runtime knobs:

```bash
python scripts/play.py --video tandy --sound adlib
python scripts/play.py --video tandy --sound adlib --retrace-hz 60
python scripts/play.py --video tandy --sound adlib --adlib-chunk-ms 70
python scripts/play.py --video tandy --sound adlib --adlib-audio off
```

Validation:

```bash
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 227 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_timing
# reached 1010:D007; steps=19847
```

## 2026-06-14 — Intro/menu AdLib handoff timing pass

The remaining Tandy + AdLib stutter was narrowed to the interactive viewer
handoff rather than raw ASM cost: intro/menu paths spend a lot of time publishing
retrace-driven snapshots to SDL and waiting for the UI to consume them.  While
that producer/consumer wait was active, the emulator thread was blocked and did
not deliver asynchronous IRQ0 ticks, so the loaded AdLib driver advanced in small
irregular bursts.  Gameplay sounded normal because it reaches the regular
`1010:0679` timer wait path.

Changes:

- `FrameSync.publish_and_wait` can now run a cooperative wait callback while the
  emulator waits for SDL to display a snapshot.
- Retrace/direct/input-wait publishes pass the async IRQ0 poller into that wait,
  so the original `1010:06E5 -> 2032:0000` AdLib path keeps advancing while the
  UI consumes intro/menu frames.
- Interactive wait sleeps now poll IRQ0 during their short yield instead of
  sleeping with the emulated PIT completely stopped.
- SDL now remembers the last presented frame and redraws it on resize/expose;
  resizing a static screen no longer clears the image until the next emulated
  present.

Validation:

```bash
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 227 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_audio_timing
# reached 1010:D007; steps=19847
```

## 2026-06-14 — Deterministic boss-key wait detection

F9 boss-key display was still intermittent: the VM was correctly inside the
boss-key wait screen, but the SDL viewer could keep showing the last gameplay
frame while the caption/audio underrun counter continued updating.  The root
cause was an instruction-phase race in the interactive wait detector, not the
text renderer itself.

The original boss-key waits are tiny two-instruction loops at `1010:07C4`,
`1010:07D0`, and `1010:07D7`.  `CPU.run(max_steps)` can return after either
instruction in each loop; the old detector only matched the loop heads.  When the
burst ended on the branch instruction instead, the player missed the cooperative
text-frame publish boundary until the large no-boundary budget expired, which
looked like frozen gameplay.

Changes:

- Added explicit boss-key wait instruction windows:
  - `1010:07C4..07CA` F9-release wait
  - `1010:07D0..07D6` any-key wait
  - `1010:07D7..07DD` return-key-release wait
- `is_boss_key_screen_wait()` now classifies the whole instruction window before
  forcing the BIOS text frame to SDL.
- Added regression tests proving the wait detector accepts both loop-head and
  branch-instruction IPs while rejecting neighbouring code.

Validation:

```bash
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 230 passed
```

## 2026-06-14 — Hook verifier metadata sweep and BC4B full-memory scratch fix

Follow-up from an interactive `scripts/play.py --video tandy --sound adlib --verify-hooks --verify-stop-on-diff` run.

Findings:

- Several recently lifted bootstrap, AdLib, menu, and renderer hooks were correct enough for normal play but had no verifier continuation metadata, so live verification printed repeated `HOOK VERIFY SKIP ... no continuation metadata` lines.
- The first real divergence was `1010:BC4B overkill_object_postmove_bc4b`: both ASM and hook returned to `1010:AA04`, but full-memory verification found one stack-scratch byte difference below the restored SP.
- The scratch mismatch was in the `BC4B -> BCCB -> BFC7 -> C054` death/transition tail.  The original `BFC7` materializes the score amount in `BX` (`0030h`/`0060h`) before calling the score-add helper; later selector/effect code can push that `BX` value as freed stack scratch.  The lift left the incoming `BX` live, so one path pushed `000Ch` instead of the expected `0030h`.

Changes:

- `BFC7` lift now explicitly sets `BX` to the selected score amount before the nested score/selector path.
- Added continuation metadata for all currently registered replacement hooks, including:
  - temporary bootstrap LZEXE loops at `1B65:0069`, `1C43:0069`, `23AD:0069`;
  - loaded AdLib driver helpers at `2032:*`;
  - interactive one-iteration menu loops `1010:558B` and `1010:D445`;
  - remaining renderer helpers and the far demo counter tick.
- Added a regression test that checks every registered hook has verifier metadata, so this class of skip should not silently return.
- Kept the runtime-code bootstrap test fast by leaving exact bootstrap/codec hooks installed and disabling only the `1010:5E42` runtime hook being inspected.

Validation:

```bash
python scripts/lint.py
# Lint passed for 75 Python files

python -m pytest -q
# 234 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_verify_metadata_fix2
# reached 1010:D007; steps=19847

python scripts/verify_hooks_headless.py --snapshot artifacts/static_runtime_bundle --verify-max 200 --max-steps 200000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200
```

## 2026-06-14 — 558B verifier expiry fix and 1F8F:081D live-code variant

Follow-up from an interactive Tandy/AdLib run started from
`artifacts/snapshot_play_tandy_20260614_203152`.

Findings:

- `1F8F:081D overkill_demo_counter_tick_1f8f_081d` was not actually patched to a
  different behavior.  The uploaded/live image uses `CMP AX,imm16` encodings
  (`3D xx 00`) where earlier evidence used the shorter `CMP AX,imm8` form
  (`83 F8 xx`).  The threshold values are small positive words, so both streams
  are equivalent for this routine.
- The `1010:558B overkill_main_menu_idle_loop_558b` verifier divergence was a
  real boundary bug.  The hook pre-fell back when `DS:22BF >= 02ED`, executing
  only the first original `CMP` and stopping at `5590`.  Original ASM still runs
  the retrace wait and increments `DS:22BF`; at `02ED` it reaches the valid
  expiry continuation `55FD` with `DS:22BF == 02EE`.
- The same parent should not depend on a nested installed `50C9` replacement to
  be verifier-stable.  Verification/pass-through contexts may restore or remove
  interactive retrace wrappers, but `558B` still has to reproduce the pure
  `50C9` side effects before landing on `558B`, `55FD`, or the near return.

Changes:

- `self_disable_if_patched()` now accepts multiple valid byte signatures for a
  hook entry and reports all accepted variants on mismatch.
- `1F8F:081D` accepts both compact and wide compare encodings.
- `558B` no longer pre-falls back on the `DS:22BF == 02ED` expiry edge; it runs
  the known prelude and stops at `55FD` after reproducing the increment/retrace
  side effects.
- `558B` has a local pure `50C9` fallback body for verifier contexts where the
  nested retrace hook is absent, avoiding one-instruction original fallback at
  the parent entry.
- Added regressions for the wide `1F8F:081D` encoding and the `558B` counter
  expiry boundary without an installed nested retrace hook.

Validation:

```bash
python scripts/lint.py
# Lint passed for 76 Python files

pytest -q \
  tests/test_overkill_hooks.py::test_demo_counter_tick_081d_accepts_wide_cmp_live_code_against_asm \
  tests/test_overkill_hooks.py::test_main_menu_idle_loop_558b_counter_expiry_boundary_without_installed_retrace_hook \
  tests/test_overkill_hooks.py::test_main_menu_idle_loop_558b_matches_interpreted_idle_iteration \
  tests/test_overkill_hooks.py::test_main_menu_idle_loop_558b_returns_on_fire
# 4 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 200 --max-steps 400000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200
```

`python scripts/play.py ...` could not be re-run in the sandbox because pygame is
not installed here.  A full `pytest -q` run reached 82% with no displayed failure
before the sandbox timeout, so the focused regressions and headless verifier are
the completed validation for this patch.

## 2026-06-14 — interactive verifier startup visibility / presenter passthrough

Follow-up from running:

```bash
python scripts/play.py --video tandy --sound adlib \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-hooks --verify-stop-on-diff
```

Finding:

- The black SDL window during interactive hook verification was misleading UI
  starvation, not evidence that the Tandy VRAM was empty.  The uploaded snapshot
  already has non-zero B800h/Tandy contents, but `play.py` only published frames
  after a natural presenter/timer/retrace boundary.  With `--verify-hooks`, a
  large amount of object/frame logic can be differentially verified before the
  next boundary, especially when full-memory diffs are enabled.
- The Tandy/CGA/EGA presenter hooks are also UI pacing boundaries in
  `scripts/play.py`.  Inline-verifying the active presenter on every visible
  frame makes interactive verification much less useful; visual equivalence is
  better checked with `--verify-frames`, while live `--verify-hooks` should keep
  the viewer responsive.

Changes:

- Added `FrameSync.publish_nowait()` so `play.py` can queue the currently loaded
  video snapshot before the emulator thread reaches the next natural boundary.
- `play.py` now publishes the loaded/current snapshot once at startup without
  waiting for the SDL consumer.  This prevents the window from staying black
  while the hook verifier proves the first gameplay slice.
- Interactive presenter verification is now opt-in.  `--verify-hooks` treats the
  active presenter as a passthrough UI boundary; use `--verify-hook 1010:3354`
  or `--verify-frames` when the presenter itself is the target under test.

Validation:

```bash
python scripts/lint.py
# Lint passed for 76 Python files

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 150 --max-steps 600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=150
```

`python scripts/play.py ...` still cannot be visually re-run in the sandbox
because pygame is not installed here.  The supplied snapshot was loaded and the
headless verifier passed from that exact state.

## 2026-06-14 — interactive verify live-publish during verified parent hooks

Follow-up after testing the previous visibility patch:

```bash
python scripts/play.py --video tandy --sound adlib \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-hooks --verify-stop-on-diff
```

Finding:

- Publishing only the loaded snapshot fixed the initial black window, but not the
  real starvation path.  During a differential transaction, the live replacement
  side temporarily restored presenter/timer/retrace hooks to their install-time
  pure hooks.  That kept verification atomic, but it also meant long verified
  parent hooks could execute many visual boundaries without publishing anything
  to SDL.
- The correct split is different for the two sides of the transaction:
  - ASM oracle clone: use install-time pure passthrough hooks.
  - Live hook side: use CPU-equivalent publish-only wrappers that apply the same
    base hook side effects and queue a frame, but do not raise `FramePresented`.

Changes:

- Added `CPU8086.hook_verifier_live_passthrough_overrides`.
- `HookVerifier._LivePassthroughHooks` now prefers those live-only overrides
  while keeping the ASM oracle clone on install-time pure hooks.
- `play.py` installs publish-only live overrides for the active presenter,
  `1010:0679` timer wait, and `1010:50C9` retrace wait.  These wrappers use
  `FrameSync.publish_nowait()` and never break the verified parent routine.
- Added a regression proving live passthrough overrides can run inside a verified
  parent hook without invoking the normal frame-boundary wrapper.

Validation:

```bash
python scripts/lint.py
# Lint passed for 76 Python files

pytest -q \
  tests/test_overkill_hooks.py::test_hook_verifier_uses_base_passthrough_hooks_inside_intro_delay_loop \
  tests/test_overkill_hooks.py::test_hook_verifier_live_passthrough_override_can_publish_without_frame_boundary
# 2 passed

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 200 --max-steps 600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 20 --max-steps 80000
# OK HOOK VERIFY LIMIT REACHED verified=20

SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy timeout 10s \
  python scripts/play.py --video tandy --sound adlib \
    --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
    --verify-hooks --verify-stop-on-diff --scale 1 --no-coverage-summary
# Ran until timeout with no HookVerifyDivergence or crash printed.
```

## 2026-06-14 — interactive hook verifier yield audit

Follow-up from `play.py --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-hooks --verify-stop-on-diff` feeling suspiciously smooth but not reacting to keyboard input.

Root cause: interactive live passthrough wrappers for presenter/timer/retrace correctly avoided raising `FramePresented` inside a verified parent hook, but there was no deferred yield after the parent hook finished its ASM-vs-hook diff. When a large parent such as `1010:97B2` was verified, the live side could publish and pace frames inside the transaction, yet `CPU.run()` did not return to the outer SDL/input pump until the chunk ended. That made keyboard input appear ignored and made interactive verification less honest as a gameplay test.

Fix:

- Added `CPU8086.hook_verifier_live_yield_requested` and `hook_verifier_live_yield_callback`.
- Live-side verifier passthrough wrappers now request a cooperative yield after they publish/pace.
- `HookVerifier.verify()` computes the normal diff first, then invokes the callback. In `play.py` the callback is the normal `stop_cpu_burst()`, so the outer loop pumps SDL/key events only after the verified hook has reached its continuation and compared cleanly.
- The ASM oracle clone still uses install-time pure hooks. The live side still uses publish-only wrappers only inside the verified transaction. The change is scheduler-only, not CPU-visible state.

Validation:

```text
python scripts/lint.py
# Lint passed for 76 Python files

pytest -q \
  tests/test_overkill_hooks.py::test_hook_verifier_live_passthrough_override_can_publish_without_frame_boundary \
  tests/test_overkill_hooks.py::test_hook_verifier_defers_live_passthrough_yield_until_after_diff
# 2 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 200 --max-steps 600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200
```

## 2026-06-14 — Boss-key wait gates lifted out of unknown ASM

The F9 boss-key text screen still left a large interpreted/unknown region in
profiles while the game waited for the user to release F9, press a key, then
release the return key.  The hot part was not the text drawing itself but three
tiny interactive wait gates inside `1010:075F..07EE`:

- `1010:07C4` — `CMP byte DS:9907,01h; JE 07C4`, wait for the original F9 press
  to be released.
- `1010:07D0` — `CMP byte DS:98C3,00h; JE 07D0`, wait for any key to leave the
  fake DOS text screen.  This produced the hot `07D0/07D5` profile pair.
- `1010:07D7` — `CMP byte DS:9907,01h; JE 07D7`, wait for the return key to be
  released before restoring the game video mode.

Changes:

- Added one-iteration state-machine hooks:
  - `overkill_boss_key_f9_release_wait_gate_07c4`
  - `overkill_boss_key_any_key_wait_gate_07d0`
  - `overkill_boss_key_return_key_release_wait_gate_07d7`
- Classified these hooks under `input_menu` rather than leaving the boss-key
  wait loops as `unknown`.
- Added verifier metadata with same-IP-after-step stops for all three gates.
- Added ASM-vs-hook regression tests for both the wait and exit branches.

This deliberately does not lift the whole `075F` boss-key screen routine yet.
The screen drawing/setup executes once and is not the source of the hot loop; the
verified lift removes the runtime ASM noise while preserving the existing
interactive text-frame publishing logic.

Validation:

```bash
python scripts/lint.py
pytest -q \
  tests/test_overkill_hooks.py::test_boss_key_wait_gates_match_interpreted_state_machines \
  tests/test_overkill_hooks.py::test_input_wait_gate_hook_metadata_uses_after_step_for_same_ip_targets \
  tests/test_play_boss_key_wait.py
```

## 2026-06-14 — Object-spawn seeds and coordinate-ring frame helpers lifted

A short interactive Tandy gameplay profile showed the next useful cleanup targets were no longer renderer loops, but small raw object/state helpers:

- `1010:7547` — hot object-slot allocation gate around the existing `7573` free-slot scan, with a rare fall-through to the original `7550/BD0D` reclaim path when no free slot exists.
- `1010:A4EA` — common raw object-spawn seed template after allocation. It initializes the active/type/sprite/layer/logic/substate fields but is not yet a semantic gameplay constructor.
- `1010:A4D7` — `A4EA` plus source-coordinate copy from `DS:SI`, including the original `Y + 4` adjustment.
- `1010:9CD9` — stores the current object center into the frame coordinate ring.
- `1010:9CF1` — advances the four delayed coordinate-ring cursors with wraparound from `A33A` back to `A27A`.
- `1010:A031` — pulls delayed coordinate-ring entries into the tracked object slots referenced by `DS:A962/A964`.

These are deliberately kept as raw memory-backed helpers.  They start to expose an object-spawn/coordinate-tracking layer without naming the specific gameplay entities yet.

Changes:

- Added replacement hooks and verifier metadata for all six addresses.
- Preserved original nested-call stack scratch bytes so full-memory oracle tests match interpreted ASM, including the `CALL 7547` frames inside `A4EA/A4D7`.
- Accepted both observed instruction encodings for equivalent `ADD AX,imm` / `CMP AX,imm` forms where the packed live image differs from the static disassembly form.
- Classified the spawn helpers under `gameplay_objects` and the coordinate-ring helpers under `game_state`.

Validation:

```bash
python scripts/lint.py

python -m pytest -q \
  tests/test_overkill_hooks.py::test_object_slot_allocate_or_reclaim_7547_free_path_matches_original \
  tests/test_overkill_hooks.py::test_object_spawn_seed_a4ea_free_path_matches_original \
  tests/test_overkill_hooks.py::test_object_spawn_seed_from_source_a4d7_free_path_matches_original \
  tests/test_overkill_hooks.py::test_frame_coord_ring_helpers_match_interpreted_asm

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 200 --max-steps 500000 --fast-ranges
```

## 2026-06-14 — Text-entry keyboard-vector helpers and BIOS key flush lifted

A blind-spot pass on the remaining interactive profile showed a large amount of
apparent `unknown` time around the text-entry prompt path.  The high-level prompt
loop at `1010:53C9` remains bounded original because it is an interactive prompt
state machine, but its reusable low-level helpers are now lifted and classified:

- `1010:4E9F` — saves the current INT 09h vector at `DS:213A/213C` and installs
  OVERKILL's temporary keyboard handler at `CS:4ED2`.
- `1010:4EBF` — restores the saved INT 09h vector.
- `1010:5497` — DOS AH=07h key read wrapper used by the text-entry prompt.  It
  temporarily restores the previous INT 9 vector around DOS input, records
  extended-key state in `DS:22B2`, stores the byte in `DS:22B4`, then reinstalls
  the temporary handler.
- `1010:50AB` — clears the 128-byte OVERKILL key-state table at `DS:98C4`.
- `1010:50BA` — synchronizes BIOS keyboard-buffer tail `BDA:041C` to the head at
  `BDA:041A`, effectively flushing pending BIOS keyboard input after prompts.

This starts to separate a concrete `input_menu`/text-prompt layer from the frame
and gameplay-object islands.  The parent `53C9` loop is now documented as a
bounded original text-entry prompt rather than unexplained unknown ASM.

Validation:

```bash
python scripts/lint.py

pytest -q \
  tests/test_overkill_hooks.py::test_keyboard_state_clear_and_bios_tail_sync_50ab_50ba_match_interpreted_asm \
  tests/test_overkill_hooks.py::test_temp_keyboard_vector_install_and_restore_match_interpreted_asm \
  tests/test_overkill_hooks.py::test_text_prompt_key_read_5497_matches_interpreted_asm_regular_and_extended_keys \
  tests/test_overkill_hooks.py::test_live_verify_replacement_hooks_have_continuation_metadata

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 250 --max-steps 700000 --fast-ranges

python scripts/play.py --video tandy --sound adlib \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-frames --verify-frame-max 20 --verify-frame-source both
```

## 2026-06-14 - text-entry prompt loop cleanup

- Replaced `1010:53C9` with `overkill_text_entry_prompt_loop_53c9`, a one-iteration state-machine hook for the DOS text-entry prompt loop.
- The hook composes the already lifted `518C` text string loop and `5497` DOS key-read wrapper, handles the hot printable/ignored-key path locally, and leaves rare edit/finish tails at original branch targets `5408`, `541E`, and `53FC`.
- This removes the large interpreted `53C9-53EA` prompt redraw/input loop from the unknown blind-spot set while keeping the `51AB` finish dispatch visible for later classification.
- Validation: `python scripts/lint.py`; focused prompt/key-read/metadata tests; `verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 200 --max-steps 700000 --fast-ranges`.


### 2026-06-15 status/setup blind-spot cleanup

Added three small meaning-revealing hooks around the remaining status/setup
noise:

- `1010:6120 overkill_status_row_repeat_6120` is a raw repeated status/HUD
  row compositor over `5A6C` and the `613E` cursor-advance leaf.
- `1010:C51D overkill_setup_tracked_status_tail_c51d` clears the tracked
  coordinate/status globals, calls the already-lifted `8517` descriptor seed,
  and jumps into `859E`.
- `1010:859E overkill_status_cell_quad_composite_859e` is the four-cell
  status/HUD descriptor compositor parent.  It preserves the original odd
  `85B5 -> 85D5` fallthrough stack shape instead of inventing a cleaner but
  unproven subroutine boundary.

This moves another chunk of low-count unknown ASM into the `game_state` island
and clarifies the current setup/status stack without assigning higher-level HUD
semantics prematurely.

### Transition/status setup cleanup — C4DB / 9908 / 9928

- `1010:C4DB overkill_reset_object_slot_and_status_setup_c4db` is now the explicit
  transition/setup parent over the already-lifted `C4E5 -> C51D -> 859E` chain.
- `1010:9908 overkill_transition_status_wait_9908` is the frame-controller branch
  reached from the `A346` transition flag. It calls `C4DB`, adjusts `DS:2358`, and
  either returns to the `9773` setup prelude or exposes the existing `9921` wait
  checkpoint.
- `1010:9928 overkill_transition_input_release_tail_9928` closes the small tail
  after the shared `9921` latch wait by optionally writing `DS:BEFF = 02h` and
  jumping back to `9773`.

This separates another piece of the former `97B2/9773` controller blob into a
named transition/status-reset layer without inventing a higher-level game-state
model yet.

## 2026-06-15 cleanup: input release gates and spawn-anchor helper

- Lifted two cold-start / first-level input-menu wait gates that were showing as
  `unknown` in the latest profile:
  - `1010:D390 overkill_menu_fire_release_wait_d390` — one-poll FIRE/SPACE
    release wait before menu/planet transition setup.
  - `1010:D434 overkill_selector_input_release_wait_d434` — one-poll input
    release wait before falling into `D445` selector loop.
- Lifted `1010:A571 overkill_object_spawn_anchor_offset_a571`, a small raw
  object-spawn anchor helper that copies source `SS:BP` coordinates plus
  `+10/+10` into destination object slot `DS:BX`.
- These are deliberately still low-level names: `D390/D434` belong to the
  input/menu wait-state layer, while `A571` belongs to raw object-slot spawning,
  not to a confirmed semantic enemy/projectile constructor.

## 2026-06-15 deterministic input demos

Added an interactive input-demo layer for reproducing human gameplay from a
stable VM state:

- `F11` in `scripts/play.py` starts/stops recording.
- Starting a recording writes a normal snapshot under
  `artifacts/demos/demo_play_<video>_<timestamp>/snapshot`.
- While active, the player records VM-delivered keyboard scan codes and DOS text
  key values by emulated boundary index into `input_demo.json`.
- `--demo <dir-or-json>` replays the recorded input and, unless `--snapshot` is
  explicitly supplied, loads the demo's start snapshot automatically.
- Demo replay is supported by normal play, `--verify-hooks`, headless
  `--verify-frames`, and `--verify-frames --verify-frame-preview`.

Useful commands:

```bash
# Record: press F11, play, press F11 again.
python scripts/play.py --video tandy --sound adlib \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152

# Replay the run normally.
python scripts/play.py --video tandy --sound adlib \
  --demo artifacts/demos/demo_play_tandy_YYYYMMDD_HHMMSS

# Verify the replay at frame level.
python scripts/play.py --video tandy --sound adlib \
  --demo artifacts/demos/demo_play_tandy_YYYYMMDD_HHMMSS \
  --verify-frames --verify-frame-source both

# Verify hooks while the demo plays for the runtime.
python scripts/play.py --video tandy --sound adlib \
  --demo artifacts/demos/demo_play_tandy_YYYYMMDD_HHMMSS \
  --verify-hooks --verify-stop-on-diff
```

The demo stores delivered VM events, not host wall-clock timestamps.  That makes
replay deterministic for oracle/candidate comparison and avoids the one-frame
input skew that can happen when SDL events are sampled independently for the two
sides of frame verification.

### 2026-06-15 demo verification fix: A571 dual ADD encoding

The first recorded gameplay demo exposed a verifier divergence at
`1010:A571 overkill_object_spawn_anchor_offset_a571` during hook verification.
The routine exists in two equivalent encodings:

- static/install-time code uses `ADD AX, imm8` (`83 C0 0A`),
- live runtime/demo snapshots can contain `ADD AX, imm16` (`05 0A 00`).

The hook now accepts both byte signatures and the regression test runs the
same ASM-vs-hook comparison against both encodings.  This keeps `A571` as a
single raw object-spawn anchor helper while avoiding a false runtime-patched-code
fallback when verifying recorded demos.

### 2026-06-15 demo-driven linked-child / movement blind-spot cleanup

Used the recorded Tandy demo `artifacts/demos/demo_play_tandy_20260615_104031`
as a representative input-driven path after the A571 signature fix.  This pass
stayed in the verified lifted-routine layer and deliberately avoided assigning
high-level enemy/projectile names.

Lifted:

- `1010:9FAF overkill_linked_object_coord_quad_update_9faf`
  - frame-controller child parent around four `9FEA` linked-object coordinate
    updates;
  - clears `DS:A39E/A39F`, uses `DS:A39A/A39C` as the two vertical offsets, and
    updates linked slots from `DS:A966/A968/A96A/A96C`;
  - the fourth child is the original fallthrough into `9FEA`, so it returns
    directly to the caller.
- `1010:A5D1/A5EA/A5F9/A607`
  - raw two-pass clamp-step helpers for object X/Y movement;
  - these preserve the odd `CALL next; body; RET back to body; RET caller`
    stack scratch pattern.
- `1010:A616/A63C/A648/A662`
  - raw vertical edge-scroll response helpers around `DS:A39A/A39C`;
  - this starts separating player/object edge-scroll bias from the larger
    object behavior family without naming the owner semantically.

Validation:

```text
python scripts/lint.py
# Lint passed for 77 Python files

pytest -q tests/test_overkill_hooks.py::test_linked_object_coord_quad_update_9faf_matches_original_parent \
  tests/test_overkill_hooks.py::test_object_two_pass_clamp_step_helpers_match_original \
  tests/test_overkill_hooks.py::test_object_vertical_scroll_edge_helpers_match_original \
  tests/test_input_demo.py tests/test_frame_verify.py
# 9 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 300 --max-steps 1000000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=300

python scripts/play.py --video tandy --sound adlib --demo artifacts/demos/demo_play_tandy_20260615_104031 --verify-frames --verify-frame-max 100 --verify-frame-source both
# FRAME VERIFY OK frames=100
```

A demo run with `--verify-hooks --verify-stop-on-diff --verify-fast-ranges` ran
until sandbox timeout without divergence; during that timeout-limited window it
reported no skipped metadata and no unknown/unmeasured hook calls.

Remaining demo/cold-start blind spots are now more concentrated around:

- `1010:9B2E-9C6B` frame-controller child frontier;
- `1010:A6FD-A780` / `1010:A66F-A6B7` larger scroll/transition/object-family
  helpers;
- `1010:F225-F2AE`, `1010:AFD8-B01C`, `1010:89FF-8A20`, `1010:7CA2-7CDD` as
  object/map behavior frontiers;
- `1010:61DC-6295` status display parent, still not lifted as a whole because it
  reaches display/data-table shaped helpers and should be mapped before a parent
  replacement.


### 2026-06-15 input-demo ownership refactor

Moved deterministic input-demo recording/replay out of the OVERKILL package into
`dos_re.input_demo`.  The demo format is now explicitly reusable VM tooling: it
stores a start snapshot plus VM-delivered `scan` / `dos_key` events by emulated
boundary index, with game-specific information kept only as opaque manifest
`metadata`.

OVERKILL-specific code now only integrates the generic layer from `scripts/play.py`:

- `F11` remains the OVERKILL viewer toggle for start/stop recording;
- demo directories keep the existing `demo_play_<video>_<timestamp>` shape;
- the manifest metadata records `program=overkill`, video mode, sound mode, and
  command tail;
- `overkill/input_demo.py` is a compatibility shim that re-exports the generic
  API for older local scripts, but new code should import from `dos_re.input_demo`.

Validation:

```text
python scripts/lint.py
# Lint passed for 78 Python files

python -m pytest -q tests/test_input_demo.py tests/test_frame_verify.py
# 6 passed

python scripts/play.py --video tandy --sound adlib \
  --demo artifacts/demos/demo_play_tandy_20260615_104031 \
  --verify-frames --verify-frame-max 20 --verify-frame-source both
# FRAME VERIFY OK frames=20

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/demos/demo_play_tandy_20260615_104031/snapshot \
  --verify-max 150 --max-steps 600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=150
```

### 2026-06-15 blind-spot cleanup: scroll/tile-sweep layer

Added demo-driven low-level hooks for the remaining movement/collision blind spots around the frame controller:

- `1010:AFD8 overkill_object_tile_sweep_probe_afd8` — shared object tile-sweep wrapper around the direction-specific `B00D` table. This exposes the A430 scratch globals as a raw collision/movement probe instead of anonymous object ASM.
- `1010:A66F overkill_object_scroll_world_progress_gate_a66f` — vertical-scroll/world-progress gate around the `A6FE` scroll tick.
- `1010:A6FE` / `1010:A781` — forward/backward vertical-scroll bookkeeping steps.
- `1010:A74E` / `1010:A7D0` — forward/backward row-advance side effects around the still-bounded `A7EB` display copy.
- `1010:A746` / `1010:A7E3` — tiny source-row pointer wrap leaves.

This starts separating a reusable raw layer:

```text
movement / world-scroll bookkeeping
  ├── A66F world-progress gate
  ├── A6FE/A781 forward/backward scroll ticks
  ├── A74E/A7D0 row advance side effects
  └── A746/A7E3 source-row pointer wraps

collision / tile sweep
  └── AFD8 shared object tile-sweep probe wrapper around B00D
```

No semantic level/camera/enemy names are claimed yet; these are still ASM-shaped roles verified against the DOS oracle.

### 2026-06-16 demo suffix repro tooling and AC81 flag fix

Follow-up from a long `--demo ... --verify-hooks --verify-preview --sound adlib`
run that eventually diverged at `1010:AC81 overkill_object_slot_scan_guard_ac81`
(call 177).  The reported continuation was correct (`1010:ACD9`), but the hook
left `FLAGS=0246` while the ASM oracle had `FLAGS=0206`.

Root cause: the lifted `AC81/AC97` object-slot scan does useful look-ahead when
an overlap candidate reaches the original `ACD9` continuation.  For type-4/type-5
candidate slots the hook correctly stopped at `ACD9`, but it leaked flags from
the look-ahead `CMP [BX+16h],4/5` checks.  The real CPU has not executed any
`ACD9` instruction at that boundary yet; the visible flags must still be from
the `ACD0 CMP SI,[BX+0Eh]` / `JNZ ACD9` decision.  The hook now snapshots those
entry flags and restores them before returning to `ACD9`.

Added reusable long-demo reduction tooling in `dos_re.input_demo`:

- `InputDemoPlayback.remaining_events_from_cursor(boundary=...)` returns only
  not-yet-applied events, rebased to a new boundary-zero snapshot.
- `InputDemoPlayback.write_suffix(...)` writes a new demo directory containing a
  current runtime snapshot plus the remaining input stream.
- This deliberately uses the playback cursor, not `event.boundary > boundary`,
  so same-boundary key-up/key-down events are not duplicated or dropped.

`scripts/play.py` integration:

- `--save-repro-root` controls where suffix/repro demos are written; default is
  `artifacts/repros`.
- While replaying `--demo`, `F11` now saves a suffix demo from the current point
  instead of being disabled.
- If interactive `--verify-hooks --verify-preview` diverges while replaying a
  demo, `play.py` automatically writes a suffix demo under `--save-repro-root`.
- The headless hook verifier path also writes a suffix demo on divergence when a
  demo is active.

Validation:

```text
python -m pytest tests/test_input_demo.py tests/test_overkill_hooks.py::test_ac81_slot_scan_guard_acd9_continuation_preserves_entry_cmp_flags -q
# 6 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*ac81*' --timeout 20
# 1 passed, 0 failed, 0 timed out

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 316 registered hooks, 316 metadata entries, no direct registered child calls detected.

python scripts/lint.py
# Lint passed for 81 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

A full `python scripts/run_tests.py --no-lint --timeout 20` attempt was started
but hit the sandbox command timeout before producing a final suite summary, so
only the focused validations above are claimed.

### 2026-06-16 BC45 / 62F6 logic-26 pre-scan exemption fix

A suffix repro generated by the new long-demo tooling reproduced a strict verifier
mismatch after only a few BC45 calls:

```text
python scripts/play.py --demo artifacts/repros/demo_divergence_tandy_20260616_130609 \
  --verify-hook 1010:BC45 --sound adlib --verify-max 10
# previous failure: BX asm=03C4 hook=32CC, FLAGS asm=0246 hook=0206
```

The hook reached the right continuation (`1010:AA04`) but the lifted `62F6`
overlap scan incorrectly treated logic-id `0026h` as an empty-scan sentinel.
The original path is:

```text
1010:6323  cmp ss:[bp+18],0026h
1010:6327  jnz 632C
1010:6329  jmp 741F
1010:741F  ret
```

So when `[BP+18] == 0026h`, the routine returns immediately through `741F`,
preserving caller `BX` and the zero flags from the `CMP`.  It does **not** run
the `741C ADD BX,0038` sentinel tail.  `_run_object_overlap_scan_62f6` now treats
`0026h` as a pre-scan exemption like the inactive/low-X/zero-layer/logic 0/1
paths.

Regression coverage added:

- `test_object_overlap_scan_62f6_preserves_bx_and_flags_on_logic_26_exemption`
- existing signed-X early-exit preservation test kept as a nearby guard

Validation:

```text
python -m pytest tests/test_input_demo.py \
  tests/test_overkill_hooks.py::test_object_overlap_scan_62f6_preserves_bx_and_flags_on_logic_26_exemption \
  tests/test_overkill_hooks.py::test_object_overlap_scan_62f6_preserves_bx_and_flags_on_signed_x_early_exit -q
# 7 passed

python scripts/play.py --demo artifacts/repros/demo_divergence_tandy_20260616_130609 \
  --verify-hook 1010:BC45 --sound adlib --verify-step-budget 400000 --verify-max 10
# OK HOOK VERIFY LIMIT REACHED verified=10

python scripts/play.py --demo artifacts/repros/demo_divergence_tandy_20260616_130609 \
  --verify-hooks --sound adlib --verify-step-budget 600000 --verify-max 2000
# OK HOOK VERIFY LIMIT REACHED verified=2000

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 316 registered hooks, 316 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 81 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

### 2026-06-16 crash repro snapshots for normal play

Normal interactive crashes are now captured as loadable repro snapshots under
`artifacts/repros` by default.  This covers the case where gameplay reaches an
exception or explicit fail-fast/unverified path without a recording demo.  The
snapshot directory can be passed directly back to the player:

```text
python scripts/play.py --snapshot artifacts/repros/crash_<...> --video tandy --sound adlib
```

Implementation notes:

- new generic helper: `dos_re.repro_artifacts.write_runtime_repro_snapshot`
- interactive `scripts/play.py` exception handler now writes a timestamped
  `crash_<video>_<ExceptionType>_YYYYMMDD_HHMMSS/` directory under
  `--save-repro-root`
- each crash artifact contains the normal snapshot files plus `repro.json` with
  crash context, current boundary counters, source demo/snapshot if any, and a
  traceback tail
- `--no-crash-snapshot` disables this behavior when intentionally fuzzing or
  running a noisy path
- headless hook verification also writes a crash snapshot on unexpected runtime
  exceptions; hook divergences still prefer demo suffixes when a source demo is
  available

Validation:

```text
python -m pytest tests/test_repro_artifacts.py tests/test_input_demo.py -q
# 7 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 316 registered hooks, 316 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 82 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

### 2026-06-16 collision/tile-contact micro-frontier absorption

Continued absorbing gameplay/collision logic from the latest long-demo coverage
frontier instead of spending time on the AdLib interpreted regions.  Three small
raw collision/tile helpers are now verified hooks:

- `1010:B032 overkill_object_tile_sweep_blocked_b032` — shared B00D tile-sweep
  blocked sentinel; writes `DS:A430=1` and returns to the B00D caller.
- `1010:BDD0 overkill_player_hazard_scan_guard_bdd0` — guard/setup parent for
  the existing `BDE3` player/hazard object scan; early `SS:[BP+0Ah] == 1` exits
  through `CLC; RET`, otherwise initializes the BDE3 scan registers from
  `DS:A436/A438`.
- `1010:8331 overkill_view_contact_rect_test_8331` plus tiny `1010:835B` — raw
  object-vs-view rectangle test using prepared `DS:95F2/95F4` centers and
  returning carry set only for in-window contact.

These are deliberately still low-level scratch/register helpers.  No semantic
player/enemy model was introduced.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_object_tile_sweep_blocked_b032_matches_interpreted_asm \
  tests/test_overkill_hooks.py::test_view_contact_rect_test_8331_matches_interpreted_asm_inside_and_miss \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan -q
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*b032*' --timeout 20 --no-lint
# 1 passed, 0 failed, 0 timed out

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*8331*' --timeout 20 --no-lint
# 1 passed, 0 failed, 0 timed out

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*bdd0*' --timeout 20 --no-lint
# 1 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --demo artifacts/demos/demo_play_tandy_20260615_235831 \
  --verify-hooks --sound adlib --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 320 registered hooks, 320 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 82 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

Next gameplay-heavy frontiers after this patch are still the larger directional
B00D table (`B039/B07A/B0CC/B10F` families), object script region
`1010:81F4-83E9`, and the map/object stream builders around `1010:7948` and
`1010:4A65`.

### 2026-06-16 recovered source-layer seed

Started the first conservative semantic crystallisation layer under
`overkill/recovered/`.  This is deliberately not a new engine model; it is a
source-like layer over the original DOS memory image and verified CPU side
effects.

Added:

- `overkill/recovered/object_slots.py`
  - `ObjectSlotView` typed memory overlay for the observed object record.
  - Object table constants: `DS:23B4`, `0x23` records, stride `0x38`.
  - Conservative field names for repeatedly observed offsets: active word,
    X/Y words, gate/layer, link key, scan flag, hazard class, logic id.
- `overkill/recovered/coords.py`
  - small 16-bit signed/unsigned and exact CMP/SI ADD/SUB helpers.
- `overkill/recovered/collision_primitives.py`
  - recovered `8331` signed center-rectangle primitive.
  - recovered `B032` tile-sweep blocked scratch flag primitive.
  - common carry-and-return tail helper for `STC/CLC ; RET` style collision
    leaves.

Wired existing collision hooks through the recovered layer where the evidence is
already strong:

- `1010:8331 overkill_view_contact_rect_test_8331`
- `1010:BDD0 overkill_player_hazard_scan_guard_bdd0`
- `1010:BDE3 overkill_player_hazard_object_scan_bde3`
- `1010:B032 overkill_object_tile_sweep_blocked_b032`
- `1010:835B overkill_collision_clc_ret_835b`

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_view_contact_rect_test_8331_matches_interpreted_asm_inside_and_miss \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan \
  tests/test_overkill_hooks.py::test_object_tile_sweep_blocked_b032_matches_interpreted_asm -q
# 7 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 320 registered hooks, 320 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 86 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --demo artifacts/demos/demo_play_tandy_20260615_235831 \
  --verify-hooks --sound adlib --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

A full `python scripts/run_tests.py --no-lint --timeout 20` command was started,
but the sandbox command timeout fired before a final summary, so this entry only
claims the focused validations above.

## 2026-06-16 - recovered source split-layer seed

Started preparing the recovered source layer for a future native source-port path
instead of only a nicer emulator path.

Added the explicit recovered-layer split:

```text
overkill/recovered/views/       DOS-memory overlays
overkill/recovered/adapters/    CPU/memory projection and ASM flag glue
overkill/recovered/domain/      pure copied source-like records
overkill/recovered/systems/     pure gameplay/system functions
```

The first portable system is now
`overkill.recovered.systems.collision.view_contact_rect_test`, the pure form of
`1010:8331`.  The hook path still uses the adapter to preserve exact `SI` and
FLAGS, but the adapter also validates that the pure system agrees with the
ASM-compatible compare sequence.

Added `ObjectSlotRecord` beside `ObjectSlotView`: the view remains the original
memory overlay; the record is the first CPU/memory-free representation that a
future source port could reuse.

Added boundary enforcement:

```text
python scripts/audit_recovered_layers.py
```

and wired the same pure-layer boundary check into `scripts/lint.py`, so modules
under `overkill.recovered.domain` and `overkill.recovered.systems` cannot import
`dos_re`, views, adapters, hooks, or gameplay code, and cannot introduce obvious
`cpu`/`mem`/`memory` references.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_view_contact_rect_test_8331_matches_interpreted_asm_inside_and_miss \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan \
  tests/test_overkill_hooks.py::test_object_tile_sweep_blocked_b032_matches_interpreted_asm -q
# 9 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 6 pure files

python scripts/audit_hook_oracle.py
# 320 registered hooks, 320 metadata entries, no direct registered child calls

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# passed for 99 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --demo artifacts/demos/demo_play_tandy_20260615_235831 \
  --verify-hooks --sound adlib --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

## 2026-06-16 - BDE3 hazard scan promoted through recovered collision layer

Continued the gradual upward refactor from address-facing hooks toward recovered
source-like gameplay code.  The BDD0/BDE3 player-hazard scan was the best next
candidate because it already repeatedly used the recovered object-slot layout:
active word, gate/layer, scan flag, hazard class, logic id, X/Y words, and link
key.

Changes:

- Added pure collision-domain `ProbePoint`.
- Added pure system helpers:
  - `word_inside_signed_center_window`
  - `slot_contains_probe_point`
  - `is_player_hazard_scan_candidate`
  - `player_hazard_scan_hit`
- Simplified `view_contact_rect_test` so it reuses the same pure centered-window
  primitive instead of carrying a separate duplicate rectangle implementation.
- Added `run_player_hazard_candidate_checks_bde3` in the adapter layer.  This is
  the only place that still performs the exact BDE3 compare sequence and applies
  CPU-visible `SI`/FLAGS side effects.
- Refactored `run_player_hazard_object_scan_bde3` into a scan/continuation shell:
  it now walks `DS:23B4`, delegates one-slot semantics to the recovered adapter,
  and owns only `BX/CX/AX/DI`, table advance, `5059` hit continuation, and final
  `CLC; RET` exhaustion.

Layering consequence:

```text
pure systems:   gameplay decision only, no CPU/memory
adapters:       exact ASM flags/register projection
hooks:          address-facing continuation shell
```

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_hit_path -q
# 9 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 6 pure files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 320 registered hooks, 320 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 99 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --demo artifacts/demos/demo_play_tandy_20260615_235831 \
  --verify-hooks --sound adlib --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

## 2026-06-16 - semantic crystallization documentation anchored

Audited the project documentation after the recovered-layer split and added a
central durable brief so future AI agents can find the intended upward refactor
without relying on chat history.

New durable document:

```text
docs/overkill/semantic_crystallization_plan.md
```

It records the north-star direction:

```text
original binary oracle
  -> interpreted ASM / exact traces
  -> ASM-compatible hooks
  -> lifted game-specific modules
  -> recovered memory views and adapters
  -> pure domain records and systems
  -> native source-port runtime
```

It also makes explicit the anti-duplication rule: once a gameplay decision has a
pure recovered system, that pure function is the canonical decision.  Hooks keep
only address/continuation glue, while adapters project DOS state and preserve
ASM-visible register/flag side effects.

Updated pointer documents:

- `AGENTS.md`
  - source-of-truth list now points to the semantic crystallization plan and
    recovered source-layer document.
  - added recovered source-port promotion rules directly to the agent guardrail
    sheet.
- `README.md`
  - added a recovered source-port direction section.
- `docs/README.md`
  - added the new plan and recovered-source-layer doc to the documentation map.
- `docs/overkill/source_port_methodology.md`
  - added the concrete `views/adapters/domain/systems` split and pointers to the
    detailed plan.
- `docs/overkill/recovered_source_layer.md`
  - added a direct pointer to the plan and an explicit anti-duplication rule.

Validation:

```text
python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 6 pure files

python scripts/lint.py
# Lint passed
```

## 2026-06-16 - B729 target-move wrapper promoted into recovered movement layer

Moved the next gameplay-significant movement frontier upward instead of adding
another isolated hook.  The hot remaining bounded region `1010:B729-B73D` is the
small object target-copy wrapper used by object behaviours before the shared
`5DB2` target-seeking movement helper:

```text
B729: SS:[BP+32h] -> DS:2304   target Y
B72F: SS:[BP+34h] -> DS:2306   target X
B735: CALL 5DB2                target-seeking movement helper
B738: CMP DS:230A,0            blocked/no-direction flag
B73D: RET
```

New hook:

```text
1010:B729 overkill_object_target_move_b729
```

The hook does not duplicate the `5DB2` direction logic.  It copies the target
pair through the recovered movement adapter, calls `5DB2` through the nested hook
boundary so verifier coverage still sees the child routine, then performs the
original `CMP DS:230A,0` and returns with those flags live.

New recovered source-port slice:

```text
overkill/recovered/domain/movement.py
overkill/recovered/systems/movement.py
overkill/recovered/adapters/movement_adapter.py
```

Pure decisions added:

```text
encode_target_seek_bits(slot, target)
choose_target_seek_direction(slot, target, direction_table)
step_delta_for_direction(direction, pixels)
```

`5DB2` now computes the portable decision first, then replays the original
ASM-compatible compare/XLAT/dispatch sequence and asserts that both paths agree.
This keeps the source-port logic canonical without losing register/flag fidelity.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_target_move_b729_matches_interpreted_wrapper_with_5db2_hook \
  tests/test_overkill_hooks.py::test_movement_direction_5db2_hook_matches_interpreted_asm_on_captured_snapshot -q
# 10 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 8 pure files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 321 registered hooks, 321 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 102 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hook 1010:B729 --verify-max 3 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=3

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

Next gameplay-crystallization candidates from the supplied coverage remain:

- `1010:B0CC-B159` / `1010:B00D-B01C`: directional tile-response table family.
- `1010:9B2E-9BFA`: frame/input controller child, useful but larger and less
  isolated.
- `1010:81F4-83E9` and `1010:8B3B-8B6C`: object/script state helpers that need
  more trace classification before promotion.
- `1010:7948-7976` / `1010:7B06-7B12`: likely object/list setup or stream walk;
  classify before abstracting.

Sound/AdLib still dominates interpreted ASM, but it is not the best target for
closing gameplay semantics.

## 2026-06-16 - BFC7 type-dispatch fix for multi-part boss death

A live final-boss replay reached a `1010:BC45` divergence after the recovered
movement refactor. The failing path still returned to the correct continuation
`1010:AA04`, but the full-memory verifier showed `SS:[BP+08]` as `0022h` in the
hook and `0003h` in the ASM oracle, with live `BX=0002` in the hook and
`BX=0004` in ASM.

Disassembling the original `BFC7 -> C037` tail showed the problem: the lift had
hard-coded the type-1 dispatch tail (`C048`, `BX=0002`, `SS:[BP+08]=0000`). The
original code actually loads `BX = SS:[BP+14]`, shifts it, and jumps through the
small table at `C042`. Type-2 objects, which are used by multi-part/final-boss
pieces, take `C04E` instead and set `SS:[BP+08]=0003` while leaving `BX=0004`.

Changes:

- `_run_collision_death_tail_bfc7` now dispatches the final `C037` tail by the
  live object type at `SS:[BP+14]` instead of hard-coding type 1.
- Type 1 still takes the observed `C048` tail and writes sprite/state word `0000`.
- Type 2 takes the `C04E` tail and writes sprite/state word `0003`, matching the
  final-boss/multi-part object path.
- Other object types deliberately raise an unverified path with the original
  jump-table target.
- Added `test_bfc7_type2_death_tail_takes_c04e_dispatch_against_asm`, which runs
  raw ASM from `1010:BFC7` and compares the lifted tail against it.

Validated with focused BFC7/BC4B tests, recovered-layer audit, hook-oracle audit,
lint, and a 5,000-hook verifier pass on `demo_play_tandy_20260616_000527`.

## 2026-06-16 - C054 final-boss group transition fix

The previous `BFC7` type-2 tail fix corrected the final per-object `C037 -> C04E`
transition, but it did not explain the user's visible bug: the final boss still
appeared to die part by part. Re-disassembling `1010:C054` showed that the
`76h/77h/78h/79h` family is not a simple selector family at all.

Original flow:

```text
C054  cmp [bp+18h],0076h / 0077h / 0078h / 0079h
      jmp C15B
C15B  for DS:A8BA, A8BC, A8BE, A8C0:
        if slot != BP: call C194
      DS:A47E = 0
      DS:A8C2 = 0
C194  old_logic = DS:[BX+18h]
      DS:[BX+1Ah] = old_logic
      DS:[BX+18h] = 0001h
      DS:[BX+22h] = 0000h
      DS:[BX+08h] = 0003h
```

So the final boss/multipart death transition is a group operation. The old lift
only changed the current part in the later `BFC7` tail, leaving sibling parts in
their old `76h..79h` logic/state and making the boss visibly die in pieces.

Changes:

- Added `_run_c15b_boss_group_transition` and `_run_c194_boss_group_slot_transition`.
- `run_object_deactivate_logic_dispatch_c054` now runs the real group transition
  for logic ids `0076h..0079h` instead of returning AX selector values.
- The helper writes the nested `CALL C194` return word as freed stack scratch, so
  full-memory hook verification remains honest when C054 is called under BFC7 or
  BD17.
- Added `test_c054_logic_76_79_group_transitions_all_boss_parts_against_asm`,
  which seeds the four boss-part pointers and compares lifted C054 against raw
  original ASM.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_c054_logic_76_79_group_transitions_all_boss_parts_against_asm \
  tests/test_overkill_hooks.py::test_bfc7_type2_death_tail_takes_c04e_dispatch_against_asm \
  tests/test_overkill_hooks.py::test_bd17_deactivate_selector_a83e_tail_matches_interpreted_asm_on_captured_snapshot -q
# 3 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/repros/demo_divergence_tandy_20260616_160515 \
  --verify-hook 1010:BC45 --verify-max 20 --verify-step-budget 1000000
# OK HOOK VERIFY LIMIT REACHED verified=20

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/repros/demo_divergence_tandy_20260616_160515 \
  --verify-hooks --verify-max 1000 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=1000

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/repros/demo_divergence_tandy_20260616_171145 \
  --verify-hooks --verify-max 2000 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=2000
```

Note on repro suffixes: `demo_divergence_tandy_20260616_160515` is the useful
pre-fix repro because it still reaches the failing transition. The later
`demo_divergence_tandy_20260616_171145` was produced from an already-advanced
post-divergence runtime point, so it can be useful as a continuation smoke test
but should not be treated as the canonical pre-hook divergence reproducer.

### 2026-06-16 verifier repros now capture pre-hook/pre-frame state

The hook-verifier divergence repro path now saves from the verifier-owned
pre-hook clone instead of the live runtime after the failing hook has already
mutated state.  This fixes the failure mode where a suffix demo could start from
an already-divergent/post-divergence point and then no longer reproduce the
original mismatch deterministically.

Implementation details:

- `dos_re.verification.HookVerifyDivergence` can now carry `repro_runtime` plus
  `repro_metadata`.
- strict hook verification captures `pre_hook_rt` immediately before executing
  the candidate hook and attaches that clone to the divergence exception.
- both headless hook verification and `--verify-preview` prefer that pre-hook
  clone when writing `demo.write_suffix(...)`; only if unavailable do they fall
  back to the live post-divergence runtime.
- hook divergence without a source demo now also writes a loadable runtime
  snapshot under `--save-repro-root`.
- frame verification gained an `on_divergence` callback.  When enabled from
  `scripts/play.py`, it captures the candidate runtime before the first
  divergent frame and writes either a suffix demo (when replaying `--demo`) or a
  runtime snapshot.

The new repro metadata includes `repro_state` values such as `pre_hook` and
`candidate_pre_divergent_frame`, so later investigations can tell whether an
artifact starts before the bad mutation or is only a live fallback.

Validation:

```text
python -m pytest tests/test_dos_re_smoke.py::test_dos_re_strict_hook_verifier_auto_continuation_catches_bad_hook_without_metadata tests/test_frame_verify.py -q
# 4 passed

python -m pytest tests/test_repro_artifacts.py tests/test_dos_re_smoke.py::test_dos_re_strict_hook_verifier_auto_continuation_catches_bad_hook_without_metadata tests/test_input_demo.py -q
# 8 passed
```

### 2026-06-16 B00D directional tile-sweep dispatcher lifted

The next gameplay-logic crystallisation step lifts `1010:B00D`, the direction
specific tile/object collision sweep called by `AFD8` after it prepares the
`DS:A430/A432/A434/A436/A438` scratch rectangle.

Recovered shape:

```text
AFD8 prepares object probe scratch globals
  -> CALL B00D
     -> CALL 5073 coordinate-to-tile index
     -> dispatch by SS:[BP+06]
        0: left
        1: left, down
        2: down
        3: down, right
        4: right
        5: right, up
        6: up
        7: up, left
     -> each cardinal body probes blocking tiles through 505B
     -> each successful step checks object hazards through BDD0
     -> blocked/contact paths tail-jump to B032, preserving the current CALL frame
```

The pure, portable part is deliberately small: `tile_sweep_plan_for_direction()`
lives in `overkill.recovered.systems.collision` and returns only the recovered
component order.  The address-facing hook keeps the ASM glue: scratch globals,
child hook boundaries (`5073`, `505B`, `BDD0`, `B032`), registers, flags, stack
scratch, and near-return/tail-jump behaviour.

Important nuance: diagonal entries use real `CALL` + fallthrough composition.
If the first cardinal component tail-jumps to `B032`, the `RET` returns to the
second component, not to B00D's external caller.  The lifted hook preserves this
by simulating the internal CALL frame before running the first component.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_tile_sweep_dispatch_b00d_matches_interpreted_direction_table -q
# 10 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 8 pure files

python scripts/audit_hook_oracle.py
# 322 registered hooks, 322 metadata entries, no direct registered child calls detected

python scripts/lint.py
# Lint passed for 102 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 3000 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=3000
```

## 2026-06-16 - Runtime world projection tooling for level/editor evidence

Added a first evidence-gathering layer for future level-editor and source-port
work:

- `overkill/recovered/domain/world.py` defines pure runtime-world projection
  records that do not import the VM.
- `overkill/recovered/adapters/world_adapter.py` projects the DOS runtime into
  those records.
- `scripts/dump_world.py` dumps known object/effect slots, pointer tables,
  boss-group pointers, and important globals from a snapshot or input-demo start
  snapshot.
- `scripts/trace_world_writes.py` traces writes to those recovered world regions
  so we can identify materialisation/setup routines instead of guessing where
  level/object data comes from.

Important clarification discovered while preparing the dump layer:

```text
DS:23B4  0x23 records, stride 0x38  effect/contact slots walked by BDD0/BDE3/AC81
DS:2B5C  0x22 records, stride 0x38  main gameplay object slots before the DS:32CA pointer table
DS:32CA  pointer table used by update/draw/present scans
DS:8D12  compact/effect pointer table used by compact-layer scans
```

The older `ObjectSlotView.table_slot()` constants remain the DS:23B4 scan-family
view for compatibility, but the new world dump explicitly models both slot
families.  This is useful for level-editor work because it separates the live
object/effect record pools from the pointer tables that order update/render
passes.

Example commands:

```text
python scripts/dump_world.py --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --active-only --summary -o artifacts/world_dump_demo_20260616_000527_start.json

python scripts/trace_world_writes.py --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --max-steps 1000 -o artifacts/world_write_trace_demo_start_1000.json
```

## 2026-06-16 - Enriched world-write materialisation traces

Expanded the runtime-world tracing tools so write traces are no longer raw
linear-memory events only:

- `trace_world_writes.py` now decorates each event with writer island/symbol and
  a decoded target (`object_slot_field`, `pointer_table_entry`, `runtime_global`,
  or `boss_group_pointer`).
- `world_adapter.describe_world_write_target()` maps traced region offsets back
  to slot table, slot index, record offset, and currently known field name.
- `world_adapter.resolve_pointer_value()` resolves 16-bit old/new pointer values
  back to recovered slot tables when possible.
- `scripts/summarize_world_writes.py` groups trace events by writer, target, and
  target family, and highlights repeatedly written unknown object fields.
- Added regression tests for target decoding and summary grouping.

Generated example artefacts from `demo_play_tandy_20260616_000527`:

```text
artifacts/world_write_trace_demo_20260616_000527_enriched_20000.json
artifacts/world_write_summary_demo_20260616_000527_enriched_20000.json
```

Early conclusions from that trace:

```text
1010:35CF is Tandy renderer interior writing +0C, so +0C should be treated as draw/address scratch evidence, not level semantics.
1010:5A36 writes +12 from coordinate row-address logic.
1010:5DB2 writes +06 together with x/y from movement direction logic.
1010:AB10 and 1010:B86D write +08 together with x/y/target fields from object behavior code.
1010:7524 advances DS:95D8, strengthening the allocator-cursor interpretation.
```

This is intentionally not a field rename yet.  It gives the next crystallisation
step a stronger evidence map: promote only after the same offset's role converges
across writers, hooks, snapshots, and gameplay observations.

## 2026-06-16 - Gameplay crystallisation: movement step unification and B1B0 chase behavior

Refocused away from level-editor/tooling work and back onto gameplay/source-port
crystallisation.

Movement cleanup:

- Introduced `MovementStepOperation` in `overkill.recovered.domain.movement`.
- Added pure `step_operations_for_direction(direction, pixels)` in
  `overkill.recovered.systems.movement`.
- Moved the repeated AEE4/AF22/AF63 direction-step axis order into that pure
  recovered system.
- Added `apply_direction_step_to_current_object()` in the adapter layer so the
  hook path still materialises the exact original ADD/SUB memory operations and
  preserves live flags.

This removes three copies of the same eight-way movement table logic while
keeping the VM-facing flag/register behavior in the adapter layer.

New gameplay hook:

- Added `1010:B1B0 overkill_object_player_chase_b1b0`.
- Added recovered pure helpers for the player/view-centered chase target and the
  B15A target-candidate predicate.
- The unacquired phase now projects `DS:237E/2380` into the aligned 5DB2 target
  globals, runs the verified 5DB2 seeker, and only enters the B15A acquisition
  scan when movement reports blocked.
- The acquired phase validates `SS:[BP+30h]`, computes deltas through 5E1B,
  steers via runtime-patched 5E42, and rejoins the already lifted AD5A/AD60
  bounds tails.
- The helper `B15A` is modelled as a recovered rotating candidate scan over the
  `DS:23B4` effect/contact slot pool, using `DS:A43A` as the scan cursor.

This closes the hot `1010:B1B0-B1F3` interpreted gameplay cluster while moving
its stable decisions into the recovered source layer rather than adding another
isolated hook body.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_player_chase_b1b0_matches_interpreted_asm_key_paths \
  tests/test_overkill_hooks.py::test_movement_dir_step_tables_match_interpreted_asm_all_directions -q
# 14 passed
```


## 2026-06-16 - B1B0 behavior refactor: canonical chase predicates and adapter glue

Cleaned up the newly lifted B1B0 player/view-centered chase behavior so the
hook body is closer to a recovered source procedure and less like a pile of
inline compare logic.

Refactor details:

- Added `is_player_chase_acquired_target_valid()` in
  `overkill.recovered.systems.objects`.
- Added `run_player_chase_candidate_checks_b15a()` and
  `run_player_chase_acquired_target_validity_b1b0()` in
  `overkill.recovered.adapters.object_behavior_adapter`.
- Moved the B1BF view-target setup into
  `run_player_center_target_setup_b1bf()` in the movement adapter.
- Removed the duplicate inline B15A candidate gate and acquired-target validity
  chain from `overkill.gameplay.object_runtime`.

The source-port ownership is now clearer:

```text
recovered.systems.objects     owns B15A/B1B0 candidate/validity decisions
recovered.systems.movement    owns view/player-center target projection
recovered.adapters.*          replays exact CMP/MOV/ADD/AND order for flags
object_runtime.B1B0           owns behavior control flow and continuations
```

This keeps the pure gameplay decisions canonical while preserving the exact
ASM-visible flags/register/memory behavior in the adapter layer.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 14 passed

python -m pytest \
  tests/test_overkill_hooks.py::test_object_player_chase_b1b0_matches_interpreted_asm_key_paths \
  tests/test_overkill_hooks.py::test_movement_dir_step_tables_match_interpreted_asm_all_directions -q
# 2 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 10 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/lint.py
# Lint passed for 109 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed

timeout 90s env SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 - Recovered layout constants and shared direction crystal

Refactored a set of proven duplicate constants so future gameplay cleanup can
refer to the same recovered source facts instead of scattering magic offsets and
direction tables through hook bodies.

Changes:

- Expanded `overkill.recovered.views.object_slots` into the canonical place for
  recovered 0x38-byte object-slot layout offsets.
- Added context aliases for reused fields, especially the important `+14` / `+16`
  pair:
  - `OFF_SCAN_FLAG` / `OFF_OBJECT_TYPE`
  - `OFF_HAZARD_CLASS` / `OFF_DRAW_LAYER`
- Added named table bounds:
  - `EFFECT_OBJECT_TABLE_END`
  - `GAMEPLAY_OBJECT_LAST_SLOT_BASE`
  - `GAMEPLAY_OBJECT_TABLE_END`
  - `GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL`
- Added `overkill.recovered.domain.directions` as the single pure source for the
  recovered clockwise 8-way direction order.
- Reused that direction crystal from both:
  - `systems.movement.step_operations_for_direction()`
  - `systems.collision.tile_sweep_plan_for_direction()`
- Promoted repeated gameplay predicate constants in:
  - `systems.collision` for BDE3 hazard candidate gates and contact half-extent,
  - `systems.objects` for B1B0/B15A chase target gates,
  - `systems.movement` for B1BF view-center target biases and the 4px grid mask.
- Updated adapters to import these constants while keeping the exact original
  compare order where flags matter.
- Updated world write tracing so newly understood offsets like `+1A`, `+1C`,
  `+22`, `+30`, `+32`, `+34` are no longer reported as unknown pressure.

Important note: this does **not** claim that every table uses the same semantic
meaning for each offset. It records one proven binary layout with context aliases
where the same byte offset has different source-like names in different routines.
That is closer to the likely original C/ASM source shape than parallel magic
numbers in each hook.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py tests/test_world_trace_tools.py \
  tests/test_overkill_hooks.py::test_object_player_chase_b1b0_matches_interpreted_asm_key_paths \
  tests/test_overkill_hooks.py::test_movement_dir_step_tables_match_interpreted_asm_all_directions \
  tests/test_overkill_hooks.py::test_object_tile_sweep_dispatch_b00d_matches_interpreted_direction_table \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan -q
# 21 passed

python -m pytest tests/test_overkill_hooks.py \
  -k '7573 or 7524 or b1b0 or b00d or bdd0 or bde3 or 62f6 or bc45 or bfc7 or c054 or movement_dir_step' -q
# 23 passed, 215 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 11 pure files

python scripts/lint.py
# Lint passed for 110 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 - Tilemap probe/lookup source crystal

Refactored the shared tilemap helpers instead of adding another gameplay hook.
The important cleanup was that `5073` and `505B` existed twice: once as public
collision hooks and once as private in-place mirrors inside object behavior
tails.  Both copies now delegate to one recovered adapter, and that adapter
validates one pure source-like tilemap system.

Changes:

- Added pure records in `overkill.recovered.domain.tilemap`:
  - `TileProbeInput`
  - `TileProbeResult`
  - `TileLookupInput`
  - `TileLookupResult`
- Added pure portable logic in `overkill.recovered.systems.tilemap`:
  - `compute_tile_probe_5073()`
  - `lookup_tile_class_505b()`
- Added adapter glue in `overkill.recovered.adapters.collision_adapter`:
  - `run_tile_probe_5073_body()`
  - `run_tile_lookup_505b_body()`
- Reduced `gameplay.collision.run_tile_probe_5073()` and
  `gameplay.collision.run_tile_lookup_505b()` to patch-guard wrappers.
- Reduced the older private `_run_tile_probe_5073()` / `_run_tile_lookup_505b()`
  mirrors in `gameplay.object_runtime` to delegates, so parent tails no longer
  carry their own copy of tilemap arithmetic.

Recovered source facts made explicit:

```text
5073 adjusted_x = DS:234E + object.x
5073 stores adjusted_x into DS:215A
if adjusted_x is signed-negative: BX = FFFFh
otherwise:
  x_tile = adjusted_x >> 4
  y_tile = (object.y & FFF0h) >> 4
  BX = DS:2350 - x_tile * 13 + y_tile

505B raw_tile = ES:[BX], where ES = CS:[9592]
505B class_byte = DS:C3AA[raw_tile]
```

This gives movement/collision/tile probing one canonical source-like arithmetic
home while preserving the original instruction-shaped flags/register effects in
the adapter.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k '5073 or 505b or 4ff9 or ac28 or b00d or b1b0 or b729 or movement_dir_step' -q
# 23 passed total across the focused runs used during this patch

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/lint.py
# Lint passed for 112 Python files

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 - AC97 overlap-scan source cleanup

Refactored the hot `1010:AC97` object-overlap scan without changing its hook
boundary.  The previous lift already consumed the ACD9->ACD2 non-actionable tail,
but it still kept the slot candidate, rectangle, link-key, and type-4/type-5
decisions inline in `gameplay.collision`.  That duplicated the style of the
already-cleaned `BDE3` hazard scan and made the source-port layer less obvious.

Changes:

- Added pure record `ObjectOverlapScanDecision` in
  `overkill.recovered.domain.collision`.
- Added pure portable logic in `overkill.recovered.systems.collision`:
  - `object_overlap_scan_decision()`
  - `OBJECT_OVERLAP_SCAN_REQUIRED_FLAG`
  - `OBJECT_OVERLAP_INACTIVE_LOGIC_ID`
  - `OBJECT_OVERLAP_ACTIONABLE_CLASSES`
- Added ASM-compatible adapter glue:
  - `run_object_overlap_candidate_checks_ac97()`
- Reduced `gameplay.collision.run_object_slot_scan_ac97()` to the scan shell:
  `BX/CX` loop, final `CLC;RET`, or exact stop at `ACD9` with the pre-ACD9 CMP
  flags restored.

Recovered source facts now live in one place:

```text
AC97 overlap candidate:
  active_word != 0
  logic_id != 0001h
  scan_flag == 0001h
  probe point lies inside signed inclusive +/-16 object window
  current.link_key != slot.link_key

AC97 actionable overlap:
  candidate && hazard_class in {0004h, 0005h}
```

The scan is still deliberately named as an overlap/contact scan, not as a
semantic enemy/player rule.  It uses the same DS:23B4 pool as `BDE3`, but its
candidate gates and actionable classes are distinct and therefore stay separate
from the player-hazard predicate.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_slot_scan_ac97_hook_matches_interpreted_asm_on_captured_snapshot \
  tests/test_overkill_hooks.py::test_object_slot_scan_ac97_absorbs_non_actionable_acd9_continue_tail \
  tests/test_overkill_hooks.py::test_ac81_slot_scan_guard_acd9_continuation_preserves_entry_cmp_flags -q
# 19 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 AA71 post-move contact-window source cleanup

Continued the gameplay crystallization pass by moving the recovered `1010:AA71`
BC4B post-move contact-window decision out of the address-facing gameplay hook
and into the recovered source layer.

Changes:

- Added `PostMoveContactWindow` to `overkill.recovered.domain.collision`.
- Added pure portable logic in `overkill.recovered.systems.collision`:
  - `postmove_contact_window_test_aa71()`
  - `POSTMOVE_CONTACT_Y_UPPER_BIAS/SPAN`
  - `POSTMOVE_CONTACT_X_NORMAL_*`
  - `POSTMOVE_CONTACT_X_BOSS_*`
- Added ASM-compatible adapter glue:
  - `run_postmove_contact_window_aa71_body()`
- Reduced `gameplay.collision.run_postmove_contact_window_aa71()` to an
  address-facing wrapper.

Recovered source facts:

```text
AA71 contact window:
  negative signed X -> miss
  Y uses signed bounds around DS:2380 with +18h / -2Ch shape
  normal X uses unsigned bounds around DS:237E with +18h / -2Ch shape
  final-boss mode DS:A8C2 == 1 narrows only X to +08h / -0Ch
```

This avoids duplicating AA71 contact-window rules in hook code.  The pure system
owns the gameplay decision; the adapter still replays the original compare/add
sequence so `AX`, flags, and `CLC/STC;RET` behavior remain verifier-compatible.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 18 passed

python -m pytest tests/test_overkill_hooks.py -k 'aa71' -q
# 5 passed, 233 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 shared object-centered probe-window adapter cleanup

Continued the collision crystallization pass by deduplicating the verifier-visible
object-centered `+/-16` rectangle compare sequence used by the BDE3 player-hazard
scan and the AC97 object-overlap scan.

Changes:

- Added `run_slot_probe_window_compare_sequence()` in
  `overkill.recovered.adapters.collision_adapter`.
- Rewired:
  - `run_player_hazard_candidate_checks_bde3()`
  - `run_object_overlap_candidate_checks_ac97()`
- Kept the pure gameplay decisions in `overkill.recovered.systems.collision`:
  - `player_hazard_scan_hit()`
  - `object_overlap_scan_decision()`

Recovered source fact:

```text
BDE3 and AC97 use the same object-centered SI compare choreography:
  SI = slot.x + 10h; CMP probe_x, SI
  SI -= 20h;         CMP probe_x, SI
  SI = slot.y + 10h; CMP probe_y, SI
  SI -= 20h;         CMP probe_y, SI

BDE3 is strict:    lower < probe < upper
AC97 is inclusive: lower <= probe <= upper
```

This keeps one canonical adapter implementation for the CPU-visible compare
sequence while leaving the scan-specific gate predicates and pure gameplay
meaning separate.  It also documents a real uncertainty resolution: BDE3 and
AC97 are related contact-window scans, but they intentionally differ at the
edges and should not be collapsed into one gameplay predicate.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_slot_scan_ac97_hook_matches_interpreted_asm_on_captured_snapshot \
  tests/test_overkill_hooks.py::test_object_slot_scan_ac97_absorbs_non_actionable_acd9_continue_tail \
  tests/test_overkill_hooks.py::test_ac81_slot_scan_guard_acd9_continuation_preserves_entry_cmp_flags \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_hit_path -q
# 23 passed
```

Additional validation for this cleanup:

```text
python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 4FF9 tile/contact probe sampling-plan cleanup

Continued the recovered-source cleanup by pulling the remaining source-like
sampling decisions out of the `1010:4FF9` tile/contact probe wrapper.

Changes:

- Added pure tilemap domain/system support:
  - `TileContactProbePlan`
  - `is_tile_contact_side_valid_4ff9()`
  - `tile_contact_probe_plan_4ff9()`
  - `tile_contact_offset_table_byte_offset()`
- Added `run_tile_contact_probe_4ff9_body()` in
  `overkill.recovered.adapters.collision_adapter`.
- Reduced `overkill.gameplay.collision.run_tile_contact_probe_4ff9()` to an
  address-facing patch-guard wrapper.

Recovered source facts now named in one place:

```text
4FF9 tile/contact probe:
  side selector [BP+8] must be < 3
  side selector indexes 4-byte dx/dy pairs at DS:214E
  after 5073, DS:215A low nibble chooses one or two column samples
    <= 0Ah -> one column
    >  0Ah -> two columns
  adjusted Y low nibble controls the optional adjacent-Y lookup
  row delta is the same recovered tile-column stride: 13
```

This removes another long mixed block from `gameplay/collision.py` and keeps the
pure sampling plan portable while the adapter preserves the original stack
restore, BX/CX loop, `505B` calls, and CF result.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_tile_contact_probe_4ff9_matches_interpreted_asm_paths \
  tests/test_recovered_semantics.py::test_recovered_tile_contact_probe_plan_is_pure_4ff9_sampling_shape -q
# 2 passed

python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k '4ff9 or 5073 or 505b or ac28 or b00d or ac97 or bde3 or aa71' -q
# 14 passed, 243 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/audit_islands.py --all-hooks
# passed, no unclassified unknown hooks

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 AC28 tile-collision probe sampling cleanup

Continued the gameplay/source-crystallization cleanup by pulling the remaining
source-like sampling plan out of the `1010:AC28` tile-collision probe.  This is
the ABxx object-behaviour collision helper that reuses the shared `5073` tile
coordinate probe and `505B` tile-class lookup.

Changes:

- Added pure tilemap support:
  - `TileCollisionProbePlan`
  - `tile_collision_probe_plan_ac28()`
- Added `run_tile_collision_probe_ac28_body()` in
  `overkill.recovered.adapters.collision_adapter`.
- Reduced `overkill.gameplay.collision.run_tile_collision_probe_ac28()` to an
  address-facing patch-guard wrapper.
- Added an oracle regression test that loads real AC28/505B/5073 bytes and
  compares interpreted ASM against the hook for clear, direct-blocked, and
  adjacent-Y-blocked paths.

Recovered source facts now named in one place:

```text
AC28 tile-collision probe:
  first checks global gates DS:A47C and DS:BDAC
  calls 5073 for object coordinate -> tile offset
  samples one row below the object using the recovered tile stride 13
  if object Y low nibble is nonzero, also samples the adjacent Y tile
  on collision, writes object +24h = 0005 and decrements object +20h
  when the countdown reaches zero, clears +24h and returns CF set
```

This keeps the gameplay-facing wrapper small while preserving the exact
ASM-visible global gates, `5073`/`505B` calls, stack/return behavior, counter
side effects, and carry result in the adapter.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k 'ac28 or 4ff9 or 5073 or 505b or b00d or ac97 or bde3 or aa71' -q
# 16 passed, 243 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 BCB1/C054 source-cleanup pass

Continued the gameplay/source-crystallization cleanup by targeting two places
where already-understood logic was still duplicated or hidden behind magic
constants in address-facing code.

Changes:

- Added pure post-move Y clamp support:
  - `PostMoveYClampResult`
  - `clamp_postmove_y_bcb1()`
  - shared adapter `run_postmove_y_clamp_bcb1_body(pop_return=...)`
- Replaced the duplicate inline `_run_y_clamp_bcb1` implementation inside the
  larger `BC4B/BFC7` parent chain with the same adapter used by the public
  `1010:BCB1` hook.  The public hook consumes the near return; the composed
  parent path does not.
- Added pure C054 deactivate-dispatch classification:
  - `ObjectDeactivateDispatchDecision`
  - `object_deactivate_dispatch_decision_c054()`
  - named selector families for boss-group transition, counter-drop, and AX
    script-selection paths.
- Kept the original C054 `CMP` order in `overkill.gameplay.collision` so flags
  remain oracle-compatible, while asserting that the pure recovered dispatcher
  classification agrees with the ASM-shaped path.

Recovered source facts now centralized:

```text
BCB1:
  clamp current object Y into signed inclusive 0000h..00C0h

C054:
  logic 0076..0079 -> multi-part boss group transition
  selected logic ids -> decrement DS:A47E counter family
  logic 0093 -> same counter family plus debug/status byte DS:98A8 = 1
  selected logic ids -> AX script address selection for caller follow-up
```

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k 'bcb1 or c054 or bfc7 or bd17 or bc4b or aa71 or ac28 or 4ff9 or ac97 or bde3' -q
# 35 passed, 226 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/lint.py
# Lint passed for 113 Python files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 C054/C15B/C194 boss-group adapter cleanup

Continued source-crystallization cleanup after the BCB1/C054 pass.  The C054
classifier was already pure, but the C15B/C194 boss-group transition itself was
still embedded in `overkill.gameplay.collision` with raw offsets and globals.
This pass moved that ASM/DOS glue into the recovered object-behavior adapter and
kept only the address-facing C054 entry point in gameplay code.

Changes:

- Added live object-slot properties for repeatedly proven transition fields:
  - `sprite_or_state`
  - `logic_id` setter
  - `previous_logic_id`
  - `transition_latch`
- Added pure boss-group transition records/helpers:
  - `BossGroupSlotTransition`
  - `boss_group_transition_targets(...)`
  - `boss_group_slot_transition_c194(...)`
- Added recovered adapter glue:
  - `run_boss_group_slot_transition_c194(...)`
  - `run_boss_group_transition_c15b(...)`
  - `run_object_deactivate_logic_dispatch_c054_body(...)`
- Removed the C194/C15B implementation from `overkill.gameplay.collision`; that
  module now exposes only the address-facing `run_object_deactivate_logic_dispatch_c054(...)` wrapper.
- Fixed a small duplicated `view_contact_centers(cpu)` call in the 8331 wrapper.

Recovered source split is now clearer:

```text
recovered.systems.objects
  owns pure C054/C15B/C194 classification and state-update facts

recovered.adapters.object_behavior_adapter
  owns DOS globals, CMP order, CALL scratch words, AX/debug side effects

gameplay.collision
  owns only the exported address-facing C054 entry point
```

Validation:

```text
python -m pytest tests/test_recovered_semantics.py::test_recovered_boss_group_transition_targets_and_slot_state_are_pure \
  tests/test_recovered_semantics.py::test_recovered_c054_deactivate_dispatch_classification_is_pure_and_named \
  tests/test_overkill_hooks.py::test_c054_deactivate_dispatch_0013_selects_a4e4 \
  tests/test_overkill_hooks.py::test_c054_logic_76_79_group_transitions_all_boss_parts_against_asm -q
# 4 passed

python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k 'c054 or c15b or c194 or bfc7 or bd17 or bcb1 or bc4b or aa71 or ac28 or 4ff9 or ac97 or bde3' -q
# 35 passed, 227 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 113 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 - AA46 view/contact projection cleanup

Continued the gameplay crystallisation cleanup by removing the remaining
hand-written AA46 rectangle-test body from `overkill/gameplay/view_window.py`.
AA46 is the BCCB contact path for object-type-1 records: it projects a selected
DS:214E dx/dy pair from the live view globals (`DS:237E/2380`) into the prepared
contact-center globals (`DS:95F2/95F4`) and then runs the same signed +/-16
rectangle test as `1010:8331`.

Changes:

- Added pure source-like projection
  `recovered.systems.collision.view_contact_center_from_offsets_aa46(...)`.
- Added adapter glue
  `recovered.adapters.collision_adapter.run_view_window_check_aa46_body(...)`.
- Replaced `gameplay/view_window.py` with a thin address-facing compatibility
  wrapper around the recovered adapter.
- AA46 now shares the canonical `run_signed_center_rect_test_8331(...)` adapter
  instead of carrying a second copy of the SI/FLAGS rectangle choreography.

This keeps the semantic claim narrow: AA46 is not a new collision system.  It is
an offset-table contact-center projection followed by the already-recovered 8331
object/contact rectangle test.

Validation:

```bash
python -m pytest tests/test_recovered_semantics.py::test_recovered_aa46_view_window_projection_reuses_8331_adapter -q
python -m pytest tests/test_recovered_semantics.py tests/test_overkill_hooks.py -k 'aa46 or 8331 or aa71 or bc4b or bfc7 or c054' -q
python scripts/audit_recovered_layers.py
python scripts/lint.py
python scripts/audit_hook_oracle.py
python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
SDL_VIDEODRIVER=dummy python scripts/play.py --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 --verify-hooks --verify-max 100 --verify-step-budget 800000
```

Observed result: all focused tests/audits passed and the smoke verifier reached
`OK HOOK VERIFY LIMIT REACHED verified=100`.

## 2026-06-17 - hook registry cleanup: object-runtime frontier split

Refactored the hook-registration layer without changing gameplay behavior.  The
main cleanup was moving the object-slot allocation/spawn/movement and observed
object-family wrappers out of the aggregate `overkill/hooks.py` into:

```text
overkill/hook_wrappers/object_runtime_frontiers.py
```

`overkill/hooks.py` remains the compatibility import surface that registers and
re-exports all known `overkill_*` hook names, but the object-runtime CS:IP glue
now sits next to the other hook-wrapper modules.  Shared overlay-signature
fallback helpers were promoted into `overkill/hook_wrappers/common.py`, so future
wrapper modules do not need to copy the local `_code_matches` / single-step
bounded-original fallback idiom.

Additional cleanup:

- Added explicit `__all__` re-export contracts to the stable wrapper modules.
- Replaced long explicit wrapper import lists in `overkill/hooks.py` with compact
  side-effect/re-export imports.
- Kept the refactor strictly at the wrapper/registry layer; no object semantics,
  hook continuations, or recovered gameplay decisions changed.

Validation:

```bash
python scripts/lint.py
python scripts/audit_hook_oracle.py
python scripts/audit_recovered_layers.py
python scripts/audit_islands.py --all-hooks
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_player_chase_candidate_scan_b15a_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths -q
SDL_VIDEODRIVER=dummy python scripts/play.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --video tandy --sound pc --verify-hook 1010:A067 --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
SDL_VIDEODRIVER=dummy python scripts/play.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --video tandy --sound pc --verify-hook 1010:9B2E --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
```

All focused checks passed.  The broader `tests/test_core.py` still has the known
pre-existing coverage-classifier expectation mismatch for `1010:9B34` / `9B2E`
(`input_menu` expected by the stale test, `game_state` returned by the current
classifier), which was already present before this cleanup.
## 2026-06-17 AED8/B250 overlap-contact branch from crash repro

The interactive Tandy/AdLib repro `crash_tandy_RuntimeError_20260617_201926` hit
the intentionally fail-fast path `AED8 -> B250 -> B254`.  This was not a wrapper
relocation regression; it exposed that AED8 reaches the same B250 overlap/contact
selector previously lifted only inside the B24D frontier.

Cleanup/fix in this pass:

- Extracted `_run_b250_overlap_contact_selector` as the single source of truth
  for the B250..B2A3 selector.
- `B24D` now calls the shared selector and still stops at the selected AD5A/ADC9
  frontier as before.
- `AED8` now calls the same selector and composes the selected tail to its own
  near-return boundary:
  - `AD5A`: add `DS:A278` to X, then run the shared AD60 bounds/tile tail.
  - `ADC9`: set X to `FFFFh`, then run the same AD60 tail without the AD5A
    pre-add.
- Added `artifacts/evidence/snapshot_stop_1010_aed8_b250_overlap` and a focused
  ASM-vs-hook regression test for the repro branch.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_object_behavior_aed8_b250_overlap_branch_matches_interpreted_repro tests/test_overkill_hooks.py::test_object_behavior_b24d_hook_matches_interpreted_observed_path -q
# 2 passed

python scripts/play.py --snapshot artifacts/evidence/snapshot_stop_1010_aed8_b250_overlap --video tandy --sound adlib --verify-hook 1010:AED8 --verify-max 1 --verify-step-budget 200000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1
```


## 2026-06-19 Refactor plan Phases 1-2 complete; Phase 3 started

Driving `docs/overkill/refactor_plan.md` (readable-yet-verifiable reconstruction).

- **Phase 1 (dead-state scratch): done earlier this cycle** — `_remember_balanced_push_scratch` + inline `sp-2` writes retired; live `saved_cx` kept.
- **Phase 2a (typed views): done.** Every raw SS:BP / DS:BX object-record access in
  gameplay now goes through `ObjectSlotView` (`slot`/`dst`/`cand`). Finished
  object_movement (5e1b/9fea/a66f), contact_side_effects (bec5 + 62F6 scan),
  object_runtime (5A92/5AC8/7596/AA2B dispatch helpers), object_spawns (95D8/7573
  free-slot allocators). Only the deliberate `OFF_SUBSTATE_1E` semantic alias
  remains raw by design.
- **Phase 2b (DS-global reconciliation): done.** New `overkill/recovered/ds_globals.py`
  is the single definition site for the 7 cells genuinely shared across subsystems
  (VIEW_TARGET_X/Y, VIDEO_MODE_SELECTOR_OFF, COLLISION_DEBUG_FLAG/CODE,
  BOSS_GROUP_LATCH, CONTACT_DISPATCH_GATE); subsystem modules keep local names as
  `LOCAL = CANONICAL` aliases. Design call: single-subsystem globals stay local;
  same-valued-but-distinct literals (0x00xx) are not merged.
- **Phase 3 (de-transliterate hook bodies): started.** Method: per function, the
  *last* flag-affecting op before each boundary is live; earlier ones overwritten
  before a boundary are dead. Removed dead `_cmp_word`/`set_*_flags` + collapsed
  register-juggling temps in `_run_object_behavior_ae09` and `_run_object_logic_ab10`.
  Each slice verified *exercised* (instrument+count: ae09 951x, ab10 1398x in the
  150-frame demo window) before commit; `_run_object_behavior_8d4f`'s analogous
  removal was **reverted** because it had 0 demo invocations and no oracle — unverifiable.

Gates after each slice: oracle 244/244, demo-replay 19/19, lint 147 files.

## 2026-06-19 (cont.) Phase 3 de-transliteration sweep — object_behaviors + game_state

Method: per function, only the last flag-affecting op before each boundary is
live; earlier `_cmp_word`/`set_*_flags` overwritten before a boundary are dead.
Each slice verified *exercised* via invocation-count instrumentation + 150-frame
demo-replay before commit (the real gate; most behaviors have no per-hook oracle).

object_behaviors (now thoroughly cleaned):
- AE09, AB10, ABA3, B9F0, B73E (idle NEG/ADD + B800-spawn path), AD04, B86D (8
  sites incl. the formation chain whose "preserved for flags" warning was
  over-cautious). Remaining sites are intentional: AB10's live y-ADD (reaches
  RET) and 8D4F's removal (reverted earlier — 0 demo invocations, unverifiable).

game_state:
- 9CD9 tracked-coord store (first +8 ADD dead, second reaches RET), the
  _advance_coord_ring_ptr +4 ADD, 9CF1's 98BE TEST, and 99CD's first coord +8.
- Left live/intentional: _add_bl_ah (helper whose ADD flags ARE its result),
  _inc_reg8_preserve_cf (deliberate preserve-CF), input TEST sites (863/874).

Remaining Phase 3 surface: ~12 more game_state set_*_flags sites (per-site
analysis; several live), frame_orchestration (16), object_spawns (10), plus a
dead-`_cmp_word` sweep. Gates green throughout: oracle 244/244, demo-replay 19/19.
