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

**Next:** wire the already-recovered `4A65` level-object-script walker into `play_native`'s cold
tick (the walker itself has been DONE and demo-driven for 18/18 planets since earlier this
session/project) -- the LAST piece for this campaign's own done-condition, now that populate PASSES
VM-free. Remaining L1 scenery gaps (0x8c/0x8b/0x89, per the demo tally) are a SEPARATE, smaller
mop-up; not blocking the done-condition.
