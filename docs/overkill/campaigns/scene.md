# Campaign: SCENE CONTENT — the spawn scripts (tier: byte-exact)

**Scope.** The 4A65 level-object script walker (DONE: 18/18 all planets, terrain snap included) +
the L1 scenery behaviors it spawns: 0x1A (sprite ramp + the BB03 vertical bounce over the recovered
AFD8), 0x19 (sprite + the C237 projectile emitter), behavior 0x04 (the projectile, an AED8-family
variant), and wiring the walker into the frame flow (caller 1010:A83C).

**Done when:** `verify_cold_populate` PASSES end-to-end and play_native --level 0 (cold) populates.
**BOTH MET (2026-07-06).**

**State (2026-07-06): DONE.** `0x1A`, `0x19`, and the shared `BB03` vertical bounce (over the
already-recovered `contact_probe_afd8`/AFD8) are ALL native (`overkill/recovered/systems/
scenery_behaviors.py` + `_step_scenery_1a`/`_step_scenery_19`/`_bb03_bounce` in behavior_walk.py). The
demo shadow is **zero divergence across all 8294 walk frames** with both behaviors off the gap list
(0x1a was 576 hits, 0x19 was 288). `verify_cold_populate`: peak enemies=15, a tracked enemy moves, 0
gap-frames, PASS. **`play_native.py`'s cold path now wires the level-object-script walker + the whole
behaviour walk over a properly-seeded DGROUP image** (see the turn-key steps below) -- `verify_
play_native_cold` confirms peak enemies=20, a tracked enemy moves, 0 gap-frames, PASS, at 200 frames
on planet 1. This campaign's done-condition is met for the cold-boot first level; see "Known,
pre-existing limits" below for what's still open (not blocking).

Three real bugs surfaced landing this (all confirmed via the demo shadow, all fixed -- see
run_status.md): (1) my ORIGINAL `@recovered_island`'s docstring had AFD8's blocked-flag backwards
(caught by reading the EXISTING verified adapter's own comment -- `DS:A430=1` means BLOCKED --
before writing any code, not by trial and error); (2) the adapter never wrote AFD8's own observable
DGROUP scratch cells (`A430`/`A432`/`A434`/`A436`/`A438`), causing a slow compounding 1px/frame
drift; (3) `with_drift=False` was wrong for BOTH behaviors -- their disassembled exits are literally
`jmp BC45` (not `BC4B`), so the shared level-scroll drift (`+=DS:A278`) DOES apply, same as every
other BC45-tail actor. Also extended the `C237` child-spawn sound table from 8 to the full 16
entries (`1010:C2CE`) -- 0x19 is the first caller whose `parent_beh & 0xF` (9) falls outside the
previously-observed 0-7 range.

**Next: wire `4A65` into `play_native`'s cold tick — SCOPED, de-risked, turn-key.** The walker itself
has been DONE and demo-driven for 18/18 planets since earlier this project. Traced the full
integration (no code changed, investigation only):

1. **`NativeGame` already tracks `DS:A978` live** as `rows_to_milestone` (`native_game.py`, wired
   into `ScrollState`/`step_scroll_forward_a6fe` -- the ALREADY-RECOVERED, VERIFIED forward-scroll
   tick). No new scroll recovery needed -- just sync it into the image each tick, exactly like
   `walk_image.ww(0x25CC, 0x2350, g.row_base)` already does for row_base
   (`scripts/play_native.py` `_advance()`).
2. **`build_cold_level_start` currently hardcodes planet 0** via `new_game_session_init_96ee()`
   (`DS:2356 = 0` unconditionally) -- but planet 0 is the FINAL BOSS level, not planet 1 (the
   cold-boot first level)! The ALREADY-RECOVERED `native_new_game_data_setup(new_level_index,
   slot_ptr_table)` (`systems/frame_loop.py`) takes a level index and sets `DS:2356` correctly, but
   `build_cold_level_start` doesn't call it -- this is why `play_native.py`'s `--level` argument
   doesn't currently reach the planet field at all.
3. **Genuinely open:** what `DS:A978`'s CORRECT cold-start value is for planet 1 (the
   `verify_cold_populate` smoke just uses `0x110` as a stand-in, not derived from a recovered
   cold-seed -- needs checking against the cold bundle/a real snapshot's frame-0 value).

**Turn-key steps (a)-(e): ALL DONE. Campaign done-condition MET for planet 1 (play_native --level 0).**
(a) **DONE**: `build_cold_level_start(exe_image, level_index=0)` takes the level index and overrides
`DS:2356` via `LEVEL_INDEX_TO_PLANET = (1,2,3,4,5,0)` after the session-init's hardcoded planet-0
write (existing callers unaffected -- default `level_index=0` now correctly seeds planet 1, verified
against `test_cold_level_start.py` + full suite).
(b) **DONE**: A978's cold value for planet 1 is `0x110`, confirmed empirically (the C5E9->cursor-cell
->script-head->first-trigger-row chain, all six planets) and now proven functionally correct end-to-end
by (e) below -- the cold wave actually spawns/bursts/moves using this exact seed.
(c) **DONE**: `walk_image` is built unconditionally in `play_native.py` (`scripts/play_native.py`), via
a NEW `build_cold_level_start_image(exe_image, level_index)` in `cold_level_start.py` -- the raw seeded
DGROUP image split out of `build_cold_level_start` (which now just projects it), so the walk image and
`NativeGame`'s projected state are seeded IDENTICALLY without duplicating the write sequence.
(d) **DONE**, with one real bug found and fixed along the way: each tick syncs `A978` into the image
BEFORE `run_level_object_script_4a65`, then `advance_object_frame`. **The bug**: the level-object-script
check (`1010:A83C`) runs in the DRAW/PRESENT half of the original loop -- "present last tick's state,
then advance" -- so it must compare against `rows_to_milestone` AS IT STOOD BEFORE this tick's scroll
step, not after. A cold `origin_x=0` pulls a row (decrementing `rows_to_milestone`) on the FRAME-0
scroll tick itself, so syncing the POST-step value silently skipped the exact entry the cold seed
(`0x110`) was built to match -- zero spawns, no exception, easy to miss. Fixed in `_advance()` by
capturing `rows_to_milestone` before calling `g.step(...)` and syncing that pre-step value.
(e) **DONE**: `overkill/probes/verify_play_native_cold.py` -- a new headless probe mirroring
`play_native.py`'s exact cold wiring (no pygame), tick-for-tick: cold-seed `NativeGame` +
`build_cold_level_start_image`, step both in lockstep, census all three pools (controllers/enemies
live in `special_pool`/`effect_pool`, not just `object_pool`). **PASS** at 200 frames: peak enemies=20,
tracked enemy moves, 0 gap-frames -- a live, cold-booted, VM-free wave for planet 1.

**Known, pre-existing limits (not regressions, not blocking this campaign):** (1) past frame ~208-248,
the SAME already-documented `0x01 key 1 latch 0x9` gap the demo tally lists (43 hits) surfaces --
that's the enemies_l1 campaign's open item, not new. (2) planet 2 (level_index=1) hits behavior `0x1c`
(no native handler) immediately at frame 0 -- a DIFFERENT wave-controller family than planet 1/3's
(per CLAUDE.md: "the 'formation wave' recovery is planet 3's family only"); cold-populate is proven for
planet 1 only, other planets' controller families remain open zoo work.

Remaining L1 scenery gaps (0x8c/0x8b/0x89, per the demo tally) are a SEPARATE, smaller mop-up; not
blocking this campaign's done-condition.
