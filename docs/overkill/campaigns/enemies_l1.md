# Campaign: ENEMIES & WAVES — L1 (tier: byte-exact)

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
| 0x2f | 80 | 1010:8820 | |
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

**Next actor:** 0x91/0x90 (8291/8282, the sprite-anim sisters — sprite=base(2356)+[95EA table >>5 of
2330], with a [232C]==0x1F secondary jump table at 82CA that spawns via C237 — so this pulls in the
C237 shared spawn worker, itself a difficulty-gated 7573 alloc + a parent-behavior jump table at
C2CE). Or 0x25 (8265, the simplest C237 consumer). C237 is the next shared prerequisite.

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
