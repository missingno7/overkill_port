# Campaign: ENEMIES & WAVES — L1 (tier: byte-exact)

> Crystallization target for this campaign: [`actor_model.md`](../actor_model.md) — lift each recovered
> handler into a primitive decomposition (tag it in §4 there) so the zoo converges on a verified,
> data-driven step language. Recover against the demo frontier below; tag as you go.

**Scope.** Planet 1's full enemy lifecycle: the 0x1F wave controller, 0x20 enemies
(approach/hold/shoot/dive/re-shuffle), 0x0B enemy shots, 0x01 dying, the type-6 companion, type-5
pickups — spawning, behaving, rendering.

**Done when:** the cold-populate gate (`verify_cold_populate`) PASSES (cold boot → controller
spawns → waves fly, no snapshot) and the 200-frame shadow stays 200/0; enemy hooks verify-only.

**State (2026-07-06): ZERO DIVERGENCE across the ENTIRE demo.** `probes/verify_native_walk_demo` now
reports **8294/8294 walk frames byte-exact** (every frame the walk can natively run, i.e. excluding
only the remaining behavior-gap frames below) — the demo's 3 long-standing divergences (614/6037/
6897) are RESOLVED, not just tolerated. Root causes (both real, both fixed, see run_status.md):
(1) `GAMEPLAY_POOL_WRAP` was a mistranscribed, non-slot-aligned constant that let the C237/7573
allocator's cursor drift past the pool into adjacent memory; (2) `x_word==0xFFFF` was used as an
AMBIGUOUS proxy for "B250 contact happened," but ordinary AD5A drift can coincidentally wrap X to
the same sentinel with no contact at all -- fixed by exposing the actual `contact: bool` decision on
the 3 `*SlotUpdate` dataclasses. The whole behavior walk is shadow-proven (200/0 free-run) and WIRED
into play_native from --snapshot (enemies render + move).

**THE L1 FRONTIER (authoritative, from `demo_cold_start_full_20260705_123645`, 8294 walk frames):**
the unrecovered behaviors, by hit frequency (= recovery priority) —

| behavior | hits | handler (CS:EFC4) | note |
|---|---|---|---|
| 0x1a | 480 | 1010:BAD4 | scenery (see scene.md) |
| ~~0x91~~ | ~~383~~ | 1010:8291 | **RECOVERED** (step_animated_spawner_90_91): animate 95EA@2330 + C237 spawn at X±4 on [232C]==0x1F |
| ~~0x25~~ | ~~367~~ | 1010:8265 | **RECOVERED** (_step_spawn_25 + C237): spawn child when [232C]==0x1F, sprite 0x1A; incl. the throttled-stale [0x52] write |
| ~~0x27~~ | ~~320~~ | 1010:835D | **RECOVERED** (step_sprite_scroller_27_835d): sprite=base+(2338>>1), x+=1, BC45 |
| ~~0x12~~ | ~~281~~ | 1010:B2CD | **RECOVERED** (step_waypoint_follower_11_12): the cold A43C waypoint-path follower, seek+retry loop |
| 0x19 | 256 | 1010:BAF0 | scenery (see scene.md) |
| ~~0x29~~ | ~~182~~ | 1010:8721 | **RECOVERED** (step_ramp_steer_29): sprite ramp -> 74E2 retarget -> 5E42 steer -> Y-bounds BFC7 death |
| 0x8c | 108 | 1010:BB80 | scenery-ish (BBxx) -- ATTEMPTED+REVERTED, see loop_blockers.md (frame-3072 divergence) |
| ~~0x28~~ | ~~84~~ | 1010:8676 | **RECOVERED** (step_spawner_28, alias-group with 0x2A): 96AA-ramp anim gated on [2332]==0; when [A47E]==0 AND the +0x06 counter==7, fire the 81F4 spawn (7524 alloc + enemy_spawn_stamp_8209) with the per-planet child override (planet 1 -> behavior 0x29) |
| ~~0x90~~ | ~~80~~ | 1010:8282 | **RECOVERED** (sister of 0x91, same fn, base 0x88/0x16C) |
| ~~0x2f~~ | ~~80~~ | 1010:8820 | **RECOVERED** (step_bounce_scanner_2f): sprite 0x43, B729 seek, target-x drift, blocked→target-y bounce 0↔0xC0 |
| ~~0x30~~ | ~~80~~ | 1010:8851 | **RECOVERED** (step_spawner_anim_30): animate [96D2]@233C, gate [232A]==0xF -> C237 spawn + sound 0x0E |
| ~~0x11~~ | ~~4~~ | 1010:B2C3 | **RECOVERED**: one-shot morph -- seeds +0x36=A43C, retags behavior 0x12, falls into 0x12's body |
| 0x01 key1 latch9 | 32 | (in-walk 0x01) | the dying-morph (BE60 prev 0x24/0x25 -> respawn-as) |

Handlers are THIN (spot-checked 0x25/0x90/0x91: ~20-40 bytes each — read a few record fields + a
global (2330/2338 frame ctr / 2356 diff / 232C timer), set sprite or spawn via C237, then the
recovered BC45 tail). This is small-slice work, not a rewrite. **0x27 is DONE** (the loop is proven:
add the handler → its gap drops to 0 in `verify_native_walk_demo` → the 200/0 free-run shadow holds
→ no new divergence). NOTE: recovering one behavior UNMASKS downstream ones — a gap aborts the whole
frame, so handling 0x27 let the walk reach records that then surfaced 0x8b/0x8c earlier. The gap set
shifts as the frontier peels; drive it to empty.

**The C237 spawn chain is now FULLY CLOSED**: 0x25/0x30/0x90/0x91 spawn C237 children (behaviour
0x04), and **0x04 is RECOVERED** (`object_update_af60` in systems/objects.py + `_step_child_04` in
the walk) — AEBF on L1 ([2356]!=0, always true) falls into AF60 = step the child 2px in its fixed
direction TWICE (the call/ret-doubled 8-dir step, reusing the already-recovered
`step_operations_for_direction`), then the SAME B250 contact + AD5A/ADC9->AD60 tail every EFAE-family
behavior shares (AED8/B24D/AF60 are now a 3-member family); contact fires the single 9E19 damage
beat (logic_id 4 != 3, exactly one call). Self-contained like 0x02/0x0B -- does NOT fall through
`_postmove_bc45`. Two real bugs the shadow caught while landing this (both fixed, see run_status.md):
DS:A956 is a BYTE counter (word rw/ww was clobbering the adjacent DS:A957), and DS:215A is
promiscuous IRQ/sound/menu scratch (400+ writes from unrelated addresses traced) now excluded from
both shadow probes' EXCLUDED_CELLS, same class as the 230A/230C steer scratch.

**IMPORTANT — the AD60 field-offset bug (fixed 2026-07-05, see run_status.md):** recovering 0x11/0x12
unmasked a genuine bug in the ALREADY-VERIFIED `object_bounds_tile_decision_ad60` family (aed8/b24d/
af60/ae09/ae2c/ae7d): the real AD60 gates its tile-probe branch on **hazard_class (+0x16)**, not
draw_layer/gate_or_layer (+0x0A) as every wired adapter passed. Fixed at the shared-function level
(param renamed `hazard_class`) + the 3 live call sites + routed "deactivate" through `_bd17_deactivate`
for full fidelity. **If you add a NEW behavior that calls any object_update_* function taking a
`hazard_class` parameter, pass `rec+0x16` — NOT `rec+0x0A`.**

**~~0x24~~ RECOVERED** (8248, `_step_spawn_child_sprite`): byte-identical to 0x25 apart from the
sprite constant (0x1E). `_step_spawn_25` generalised into `_step_spawn_child_sprite(parent_beh,
sprite)`, now shared by both.

**Two more deep bugs fixed while landing 0x24/0x29 (both real, both confirmed via forensics, see
run_status.md) — the demo went from 3 unexplained divergences to ZERO:**
1. `GAMEPLAY_POOL_WRAP` was `0x2CA4` (NOT slot-aligned to base+slots*stride) -- the allocator's
   wrap check could never fire, letting the C237/7573 cursor drift past the pool. Fixed by reusing
   the canonical `GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL` from `views/object_slots.py`.
2. `x_word == 0xFFFF` is an AMBIGUOUS proxy for "B250 contact" -- ordinary AD5A drift can
   coincidentally wrap X to the same sentinel with NO contact. The `contact: bool` decision is now
   an explicit field on `Aed8SlotUpdate`/`B24dSlotUpdate`/`Af60SlotUpdate`; callers gate the 9E19
   fan-out on `u.contact`, never on `x_word`.

**Next actors (scouted, by dependency):**
* ~~0x28~~ **RECOVERED 2026-07-06** (`step_spawner_28`): the note below was WRONG about the child --
  `81F4`'s stamp is the already-recovered `enemy_spawn_stamp_8209` (which defaults the child to
  behavior `0x14`), but 8676 then OVERRIDES the child behavior per-planet (`86BB..8704`): planet 1/4
  -> `0x29` (recovered), planet 2 -> `0x2B`, planet 5 -> `0x7A`. On L1 the child is `0x29`, so NO new
  behavior was needed. The only new pure logic was the `8654` sprite anim (`DS:96AA[+0x06 counter] +
  0x1C`, counter advances when `DS:2332==0`, wraps mod 0x18); the spawn is gated on `DS:A47E==0` AND
  counter==7. Byte-exact across all 8294 demo frames. (The planet 2/5 child variants are decoded but
  not L1-exercised; planet 3/0 leave the `0x14` default -- an unrecovered child if ever hit there.)
* 0x01 latch-9 morph (43 hits): the dying object's `+0x1A` previous_logic_id selects a MORPH target
  (`0x24`→direction=6/behavior=0x26/sprite=0x97/Y-=8; `0x25`→direction=2/behavior=0x26/sprite=0x91/
  Y+=8; anything else→BD17 deactivate), then seeds `+0x32/+0x34` (target) to the record's OWN current
  position and `ret`s (skips BC45 entirely THIS frame — the postmove only resumes next frame under
  the new behavior). The morph target, **behavior 0x26** (handler `8302`), needs the ALREADY-
  RECOVERED `contact_probe_afd8` (AFD8, verified) but ALSO an UNSPECIFIED "BDD0 contact predicate"
  callback the pure function's contract calls caller-owned — needs its own investigation before
  0x26 (and thus the latch-9 morph) can be recovered. Deferred, comparable scope to C237.
* type-5 pickup COLLECT (2 hits, `_step_pickup_5`'s declared gap): BOTH demo collections use pickup
  kind `+0x26 == 2` (traced, `scratchpad/trace_pickup.py`) -> the `AB00` jump table's index-2 entry
  (`1010:9D67`) ONLY -- no need to decode the other 7 entries. Decoded: sound 0x1C, then a
  shield/HP-refill state machine (bump `DS:A95A` to 3, then `DS:A95C` to 0x18 -- the SAME globals
  `_shot_hit_9e19`/`_player_hit_9e69` decrement, i.e. this pickup HEALS), calling `9EC2` after each
  step. `9EC2` itself calls the RECOVERED `61DC` (`_energy_redraw_61dc`) plus a CONDITIONAL
  (`cs:[95BC]==1`) pair of calls to `511F` (undecoded -- likely render/palette, not gameplay state,
  but unverified). Needs `511F` scoped (does it touch DGROUP state the shadow compares?) before this
  is safe to compose. Small but 3-deep; not yet a quick slice.

Remaining scenery (0x1a/0x19/0x8c/0x8b/0x89) belongs to scene.md.

### C237 child-spawn — DONE (spec below kept as historical reference; empirically traced 2026-07-05)

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
