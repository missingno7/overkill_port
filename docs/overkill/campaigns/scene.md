# Campaign: SCENE CONTENT — the spawn scripts (tier: byte-exact)

**Scope.** The 4A65 level-object script walker (DONE: 18/18 all planets, terrain snap included) +
the L1 scenery behaviors it spawns: 0x1A (sprite ramp + the BB03 vertical bounce over the recovered
AFD8), 0x19 (sprite + the C237 projectile emitter), behavior 0x04 (the projectile, an AED8-family
variant), and wiring the walker into the frame flow (caller 1010:A83C).

**Done when:** `verify_cold_populate` PASSES end-to-end and play_native --level 0 (cold) populates.

**State (2026-07-06): `verify_cold_populate` PASSES.** `0x1A`, `0x19`, and the shared `BB03` vertical
bounce (over the already-recovered `contact_probe_afd8`/AFD8) are ALL native
(`overkill/recovered/systems/scenery_behaviors.py` + `_step_scenery_1a`/`_step_scenery_19`/
`_bb03_bounce` in behavior_walk.py). The demo shadow is back to **zero divergence across all 8294
walk frames** with both behaviors removed from the gap list (0x1a was 576 hits, 0x19 was 288 --
together the single largest chunk of the L1 frontier). `verify_cold_populate`: peak enemies=15, a
tracked enemy moves, 0 gap-frames, PASS. `python -m overkill.native_app.play_native`-style cold
wiring is the ONLY remaining item for this campaign's done-condition.

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

**Turn-key steps:** (a) parameterise `build_cold_level_start(exe_image, level_index)` to use
`native_new_game_data_setup` (or override `DS:2356` after the existing pipeline) instead of the
hardcoded-planet-0 `new_game_session_init_96ee`; (b) confirm/derive A978's correct cold value for
planet 1; (c) build `walk_image` unconditionally in `play_native.py` (not just `--snapshot`), seeded
via `build_cold_level_start`; (d) each tick, sync `A978 = g.rows_to_milestone` into the image
(one line, same pattern as the existing row_base sync) BEFORE calling
`run_level_object_script_4a65(walk_image)`, then `advance_object_frame` as today; (e) new
end-to-end verification: cold `play_native --level 0` actually renders a moving enemy wave (extend
`verify_cold_populate`-style census into an interactive/headless play_native smoke).

Remaining L1 scenery gaps (0x8c/0x8b/0x89, per the demo tally) are a SEPARATE, smaller mop-up; not
blocking this campaign's done-condition.
