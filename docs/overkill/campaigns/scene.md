# Campaign: SCENE CONTENT — the spawn scripts (tier: byte-exact)

**Scope.** The 4A65 level-object script walker (DONE: 18/18 all planets, terrain snap included) +
the L1 scenery behaviors it spawns: 0x1A (sprite ramp + the BB03 vertical bounce over the recovered
AFD8), 0x19 (sprite + the C237 projectile emitter), behavior 0x04 (the projectile, an AED8-family
variant), and wiring the walker into the frame flow (caller 1010:A83C).

**Done when:** `verify_cold_populate` PASSES end-to-end and play_native --level 0 (cold) populates.

**State (2026-07-05):** walker recovered + verified; the whole scenery chain DECODED (BB03/C237/
0x04/0x1A in run_status 2026-07-05 entries); nothing implemented yet.

**Next:** implement BB03 + 0x1A (all pieces recovered) → 0x04 via the AED8 machinery → C237 emit →
0x19 → register in the walk → cold gate PASS → wire 4A65 into play_native's cold tick.
