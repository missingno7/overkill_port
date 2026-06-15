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
