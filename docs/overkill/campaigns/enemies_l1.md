# Campaign: ENEMIES & WAVES — L1 (tier: byte-exact)

> Crystallization target for this campaign: [`actor_model.md`](../actor_model.md) — lift each recovered
> handler into a primitive decomposition (tag it in §4 there) so the zoo converges on a verified,
> data-driven step language. Recover against the demo frontier below; tag as you go.

**Scope.** Planet 1's full enemy lifecycle: the 0x1F wave controller, 0x20 enemies
(approach/hold/shoot/dive/re-shuffle), 0x0B enemy shots, 0x01 dying, the type-6 companion, type-5
pickups — spawning, behaving, rendering.

**Done when:** the cold-populate gate (`verify_cold_populate`) PASSES (cold boot → controller
spawns → waves fly, no snapshot) and the 200-frame shadow stays 200/0; enemy hooks verify-only.

**State (2026-07-05):** the whole behavior walk is shadow-proven (200/0) and WIRED into play_native
from --snapshot (enemies render + move). The opening wave (first ~2500 walk frames of a real played
L1) walks byte-perfect. **The full L1 actor list is now KNOWN** — `probes/verify_native_walk_demo`
shadows every A9D3..AA25 frame of the owner's cold-start L1 playthrough and tallies exactly which
behaviors the level exercises that aren't native yet.

**THE L1 FRONTIER (authoritative, from `demo_cold_start_full_20260705_123645`, 8294 walk frames):**
the unrecovered behaviors, by hit frequency (= recovery priority) —

| behavior | hits | handler (CS:EFC4) | note |
|---|---|---|---|
| 0x1a | 480 | 1010:BAD4 | scenery (see scene.md) |
| 0x91 | 383 | 1010:8291 | sprite anim: ax from [2356] diff, cycle on frame ctr [2330]; -> BC45 |
| 0x25 | 367 | 1010:8265 | spawn child (C237 alloc, sprite 0x1A) when [232C]==0x1F; -> BC45 |
| ~~0x27~~ | ~~320~~ | 1010:835D | **RECOVERED** (step_sprite_scroller_27_835d): sprite=base+(2338>>1), x+=1, BC45 |
| 0x12 | 281 | 1010:B2CD | (B2C8 shared-tail family, x9) |
| 0x19 | 256 | 1010:BAF0 | scenery (see scene.md) |
| 0x29 | 182 | 1010:8721 | |
| 0x8c | 108 | 1010:BB80 | scenery-ish (BBxx) |
| 0x28 | 84 | 1010:8676 | alias-group with 0x2A |
| 0x90 | 80 | 1010:8282 | sprite anim (sister of 0x91) |
| ~~0x2f~~ | ~~80~~ | 1010:8820 | **RECOVERED** (step_bounce_scanner_2f): sprite 0x43, B729 seek, target-x drift, blocked→target-y bounce 0↔0xC0 |
| 0x30 | 80 | 1010:8851 | |
| 0x11 | 4 | 1010:B2C3 | (B2C8 shared-tail family) |
| 0x01 key1 latch9 | 32 | (in-walk 0x01) | the dying-morph (BE60 prev 0x24/0x25 -> respawn-as) |

Handlers are THIN (spot-checked 0x25/0x90/0x91: ~20-40 bytes each — read a few record fields + a
global (2330/2338 frame ctr / 2356 diff / 232C timer), set sprite or spawn via C237, then the
recovered BC45 tail). This is small-slice work, not a rewrite. **0x27 is DONE** (the loop is proven:
add the handler → its gap drops to 0 in `verify_native_walk_demo` → the 200/0 free-run shadow holds
→ no new divergence). NOTE: recovering one behavior UNMASKS downstream ones — a gap aborts the whole
frame, so handling 0x27 let the walk reach records that then surfaced 0x8b/0x8c earlier. The gap set
shifts as the frontier peels; drive it to empty.

**Next actors (scouted, by dependency):**
* 0x2f (8820): sprite=0x43, [2308]=2, `call B729` (the 5DB2 seek tail — RECOVERED), then A278 drift
  on +0x34 + a +0x32/+0x34 target flip. No new worker — a good next slice.
* 0x29 (8721): a [2328]==7-gated sprite ramp to 0xA4 (then `call 74E2`), then [2312]=2 + `call 5E42`
  (the delta-steer — RECOVERED). Needs 74E2 decoded (small).
* 0x30 (8851): planet-5 anchor-proximity branch + a [233C]-indexed [96D2] sprite-anim table.
* 0x91/0x90 (8291/8282): sprite=base(2356)+[95EA table, 2330>>5], + a [232C]==0x1F jump table (82CA)
  that spawns via **C237** — pulls in the C237 shared spawn worker (difficulty-gated 7573 alloc +
  a parent-behavior jump table at C2CE). 0x25 (8265) is the simplest C237 consumer.

Shared workers still to recover: **C237** (child-spawn, unlocks 0x25/0x90/0x91), **74E2** (0x29's
ramp action). B729/5DB2/5E42 seek + steer are already recovered.

### C237 child-spawn — TURN-KEY SPEC (empirically traced 2026-07-05, `scratchpad/trace_c237.py`)

Decoded + demo-traced (25x throttled 0x25 calls witnessed; `BEDC=0` throughout L1):
1. **Throttle** on `BEDC`/`DS:A956` (A956 is a SHARED counter ticked by EVERY C237 caller — 0x19,
   0x24, 0x25, 0x90, 0x91 — in walk order): `BEDC==2` always spawn (A956 untouched); `BEDC==1`
   `A956=(A956+1)`, spawn iff `A956&1`; else (`BEDC==0`/other) `A956=(A956+1)`, spawn iff
   `A956&3==0`. The A956 write happens even on no-spawn. **Per-frame shadow starts A956 from the VM
   value, so only within-frame call ORDER matters** (same as the VM's walk order → matches).
2. **Spawn** → `7573` alloc (cursor DS:95DA) → slot or FFFF. Stamp: +00=1, +02=parent_x+4,
   +04=parent_y+4, +06=parent_dir, +08=0x30, +0A=0, +14=0, +16=2, **+18=4** (child is behavior 0x04),
   +1C=FFFF, +1E=0. Then IF `child_x(+02) >= 8` AND `parent_x <= 0xE0` AND `[98C0]`: `BEFF =
   sound[parent_beh & 0xF]` (table 0x0B/0x0C/0x0E/0x11/0x12/0x13/0x14/0x15 for idx 0..7; parent==0x92
   forces idx6=0x14). Return `bx = slot`.
3. **No spawn** (throttle): return `bx = caller's entry bx` (STALE), `al=0`. **Pool-full**: `bx=FFFF`.

**Caller 0x25 (8265)**: `if [232C]==0x1F { bx=C237(); if bx!=FFFF: [bx+8]=0x1A }`. So: spawned →
`[slot+8]=0x1A`; **throttled → bx stale 0x4A → writes `DS:[0x52]=0x1A`** (MUST model — traced 25x);
pool-full → nothing. **Caller 0x30 (8898)** ignores bx, just spawns + `BEFF=0x0E`. **0x90/0x91** call
C237 via their 82CA anim-index jump table (more involved).

**Unmask warning:** recovering C237 makes it spawn behavior-**0x04** children (handler AEBF: on L1
`[2356]!=0` → `jmp AF60`, a variant of the recovered AED8 movement) — so the NEXT frame's walk hits
0x04; recover AEBF/AF60 in the same slice or expect a fresh 0x04 gap. Suggested slice order: C237
pure (throttle + stamp + sound) → 0x25 consumer (incl. the 0x52 stale write) → 0x04/AEBF → then
0x30, then 0x90/0x91's jump table. Gate each on `verify_native_walk_demo` + 200/0 free-run.

plus the **player-death** chain (9EA3; A95C=0 + [9791] + 2384=3 ship-death) ×3, and **type-5 pickup
COLLECT** (AAD3: sound 7 + 5F0D score + AB00 +0x26 dispatch) ×2. Handler addresses via
`scripts/behavior_zoo_xref.py` (149 indices -> 134 handlers; 106 are thin stubs over shared workers
AFD8/AD60/5DB2/7476 already recovered — so most of these are small). Recover HIGH-frequency first;
each lands with a `verify_native_walk_demo` gap-count drop + the 200/0 free-run shadow held.

Two non-gap divergence classes the same instrument surfaced (investigate alongside):
* **2B5C gameplay-pool spawn mismatch** (walk frames 614/6037/6897): the native walk writes FFFF
  where the VM has a live pool object — the 7573 enemy-shot/effect allocation differs on those
  frames (likely a fire-condition/RNG or ordering gap in step_enemy_behavior_20's shot apply).
* **215A derived-scratch drift** (frames 7662+): DS:215A tracks a value the VM updates each frame
  that the native path doesn't; 215A is DERIVED (5073 recomputes it from x) so likely another
  out-of-model scratch OR a symptom of an upstream gap-frame leaving state unset.

**Next:** recover the top actor `0x1a`/`0x19` (scenery, in scene.md) or `0x91`/`0x25`/`0x27` — one
behavior per slice, gap-count drop + shadow held.
