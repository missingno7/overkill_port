# Campaign: CONVERGENCE — play_native as the VM-less game, assets-only, no exe

**Goal (owner, 2026-07-11).** Converge to a single full VM-less game like pre2_port did: `play_native`
is the entry point, it cold-boots the ORIGINAL flow (boot → title/attract → menu → level-select →
play), and it needs **only the game asset container** — no `OVERKILL.EXE`, no exe-derived snapshot,
no host-loop stand-in front-end.

## Where we actually are (measured 2026-07-11) — the honest gap

play_native today is a HYBRID, not the converged game:

1. **It boots from an exe-derived snapshot.** `build_cold_level_start_image(exe_image, level, container)`
   starts from `MutFlatMemory(artifacts/static_runtime_bundle/memory_1mb.bin)` — a 1 MB post-init memory
   image captured from the VM once — then overlays the recovered new-game init and loads the planet's
   level data from the container.  So the runtime needs the bundle, which is derived from the exe.
   - What the bundle actually provides beyond the container: a handful of CS segment/stride constants
     (`9592/9598/959E/95BC/95BE/95C0/95C2`), the game's **embedded data tables** the native frame reads
     (the anim rings `96D2/96C2/95EA/…`, the dispatch tables `AA36`/`EFC4`, the glyph font `1816`, the
     tile class tables, the muzzle offsets, the plaque/level name tables, …), and the initial DGROUP
     scaffolding.  The native frame REIMPLEMENTS the code; it only READS these data tables + constants.
2. **The front-end is host-loop stand-ins.**  `_run_title_menu` / `_run_attract` / `_run_level_select`
   in play_native are hand-rolled pygame loops.  The recovered `NativeFrontEnd` covers only the `558B`
   menu-idle + `D390` level-select DECISIONS; the cold-boot → title path and the attract are NOT
   recovered (attract plays real gameplay — a deep thread), so the app fakes the shell.
3. **The boot chain is VM-only.**  `254A:04D7 → 1010:0D42` (LZEXE self-unpack → container open → video
   init → shared-asset load) is unrecovered; the bundle IS the shortcut around it.

So "it starts on a fake menu instead of the normal cold start" is the same gap as "it needs the exe":
the boot + front-end are not yet native, and the initial state is an exe snapshot.

## The convergence path (three slices, each shadow-gated)

**A. Static ROM data → recovered, checked-in, exe-free.**  Extract the exe's embedded data tables the
frame reads into recovered-data modules (one-time, each table byte-compared to the bundle).  This is
the "recovered ROM" — game constants that are data, not an exe.  Deliverable: a `native_rom` module the
frame reads instead of `CS:[…]` into the bundle.  Gate: every table byte-equals the bundle's.

**B. Asset-built cold image (drop the bundle).**  Replace `MutFlatMemory(bundle)` with a builder that
assembles the initial DGROUP+segments from the recovered ROM (A) + the recovered init
(`new_game_session_init_96ee`, the `0B3E/0E9C/60AC` loads) + the container.  Gate: the built image is
byte-exact vs the current bundle-seeded image for every level (the existing `verify_native_cold_level_data`
/ `verify_cold_populate` become the equivalence proof).  When this passes, `--bundle` is gone; play_native
takes only `--container`.

**C. Native front-end + boot flow (retire the host loops).**  Recover cold-boot → attract → title/menu
→ level-select as the running mode machine (the SPINE campaign's `APP_MODE_GRAPH` edges), driving the
real screens, replacing `_run_title_menu`/`_run_attract`.  The attract's "real gameplay demo" is the
deep sub-thread; until it lands, the attract may replay a recorded demo through the SAME native frame
(already how `_replay_demo` works) — that is VM-free and asset-only, just not yet the ROM's own sequencer.

**Done when:** `python scripts/play_native.py --container assets/OVERKILL` (no bundle, no exe) cold-boots
the original's title/attract, menus natively, and plays — every screen recovered or a fail-loud gap.

## First slice
Slice B's equivalence gate is the highest-leverage start: prove the cold image can be built WITHOUT the
bundle by diffing an asset+ROM-built image against the bundle-seeded one, which produces the exact list
of bundle bytes still unaccounted for — i.e. the precise remaining "recovered ROM" work for slice A.
That converts "converge to assets-only" from a wish into a measured, shrinking byte-count.
