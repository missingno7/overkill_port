# Campaign: SPINE — the executing mode machine (tier: byte-exact)

**Scope.** `APP_MODE_GRAPH` (native_app.py) becomes a running `NativeSession` that OWNS the game
flow over the authoritative DGROUP image (ADR-1): mode + planet + lives + score, walking the edges
boot → title → level-setup → gameplay → {death → respawn | level-end → next level | game-over →
title}, fail-loud per unrecovered edge.

**Done when:** play_native runs a whole session natively — die and respawn, lose all lives to
game-over and return to the title, finish a level and advance — with each edge either recovered or
an explicit fail-loud gap, and the mode graph is THE loop (no ad-hoc cell dict in play_native).

**State (2026-07-05):** graph + stages described; `GameplayFrameSkeleton`/`AttractSequencer`
execute; the mode edges do NOT. The edge bodies are recovered pieces (death_continue_counter_update,
C4DB reseed, C461 reset, player spawn, advance_level_index_9744) awaiting composition.

**Next:** compose the death→respawn edge over the image; then level-end→advance; then NativeSession
owning the loop.
