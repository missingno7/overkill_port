# Campaign: ENEMIES & WAVES — L1 (tier: byte-exact)

**Scope.** Planet 1's full enemy lifecycle: the 0x1F wave controller, 0x20 enemies
(approach/hold/shoot/dive/re-shuffle), 0x0B enemy shots, 0x01 dying, the type-6 companion, type-5
pickups — spawning, behaving, rendering.

**Done when:** the cold-populate gate (`verify_cold_populate`) PASSES (cold boot → controller
spawns → waves fly, no snapshot) and the 200-frame shadow stays 200/0; enemy hooks verify-only.

**State (2026-07-05):** the whole behavior walk is shadow-proven (200/0) and WIRED into play_native
from --snapshot (enemies render + move). Cold populate spawns the controller but blocks on the
scenery behaviors (see scene.md). Remaining fail-loud edges: dying latch-9 morphs, pickup collect,
C15B escort chain.

**Next:** blocked on scene.md's scenery behaviors for cold; the fail-loud edges as they trigger.
