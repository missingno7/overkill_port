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

### Slice A DONE + slice B scope pinned (2026-07-11)
- **A landed:** `native_rom` (`overkill/recovered/adapters/native_rom.py`) = the ~580 CS bytes the FRAME
  reads; `tests/test_native_rom.py` gates the reduced-code-segment cold image byte-exact (DGROUP).
- **B scope:** building the cold image over a BLANK base (native_rom + init + container, no bundle)
  fails because the BUILDER reads more exe tables than the frame — `asset_codecs/native_level.py` reads
  the per-level CLASS-OVERRIDE table (a pointer table at `_CLASS_PTR_TABLE_OFFSET` + `FF`-terminated
  index/class pairs) and the TILE-PLANE FOOTER (`_FOOTER_OFFSET`) straight from the exe image, and
  `cold_level_start` keeps the bundle's post-init border rows.  So the full recovered-ROM set =
  native_rom (frame) + this "level ROM" (builder): the class-override table, the footer, the
  `144F/14C0` name tables.  All bounded, all byte-verifiable.  Slice B = extract that level-ROM the
  same way, point the builder at it instead of `exe_image`, gate the blank-base cold image byte-exact
  vs the bundle (`verify_native_cold_level_data`), then delete `--bundle`.

**Level-ROM enumerated (2026-07-11): 384 bytes in 2 ranges** — `DS:C4AA..C5E8` (319 B: the 6-level
class-override pointer table + its `FF`-terminated pair lists) and `DS:D1BC..D1FC` (65 B: the tile-plane
footer).  So the COMPLETE exe dependency for BUILD + GAMEPLAY = `native_rom` (~580 CS bytes) + level-ROM
(384 DGROUP bytes) = **~964 bytes of byte-verifiable tables** (plus the container banks, already
asset-derived, and the post-init tile-plane BORDER ROWS `cold_level_start` keeps — the one remaining
item to enumerate).  The exe-derived 1.3 MB bundle is ~99.9% dead weight for the gameplay engine.  Slice
B is now purely mechanical: extract those ~964 bytes + the border rows into recovered data, rewire the
builder to read them instead of `exe_image`, gate byte-exact, drop `--bundle`.

**Border rows measured (2026-07-11): ~10 KB, 40 ranges in the tile-plane segment** (`CS:[9592]`).
`cold_level_start` keeps the exe's post-init tile-plane BORDER (the container level map fills the
interior; the border tiles come from the exe).  So the COMPLETE byte-exact exe dependency for build +
gameplay = `native_rom` (580 B) + level-ROM (384 B) + the tile-plane border (~10 KB) ≈ **11 KB of the
1.3 MB bundle**.  Settled by probe: the border is a **single SHARED CONSTANT** — the 9,925-byte diff is byte-identical
across all 6 levels (`same_as_prev=True` for levels 1–5), i.e. one fixed level-frame border, NOT
per-level data.  So slice B extracts it ONCE.  **Final recovered-ROM set = `native_rom` (580 B) +
level-ROM (384 B) + the shared border constant (9,925 B) = ~10.9 KB, flat, extract-once,
byte-verified.**  Slice B is then: extract those three into a `recovered_rom` provider, point
`cold_level_start`/`native_level` at it instead of `exe_image`, gate the blank-base cold image
byte-exact vs the bundle for all 6 levels, and drop `--bundle`.  The headline is now exact: the VM-less
engine needs **~10.9 KB of recovered tables + the container**, not the 1.3 MB exe image (99.2% dead
weight).  The one shared border blob is the bulk; whether it ships as recovered data or is further
reduced (it is one constant) is an extraction detail, not a recovery unknown.

## First slice
Slice B's equivalence gate is the highest-leverage start: prove the cold image can be built WITHOUT the
bundle by diffing an asset+ROM-built image against the bundle-seeded one, which produces the exact list
of bundle bytes still unaccounted for — i.e. the precise remaining "recovered ROM" work for slice A.
That converts "converge to assets-only" from a wish into a measured, shrinking byte-count.

**MEASURED (2026-07-11, `scripts/measure_rom_footprint.py`, 600 gameplay frames, read-before-write):**
the frame depends on only **16,409 bytes** of the 1.3 MB bundle — **536 in the CS code+data segment**
(the embedded constants/tables), ~3,780 in the initial DGROUP, and ~12,093 in "other segments" which
are the tile-map / tile-block / sprite banks the CONTAINER already loads (asset-derived, not exe).  So
the genuinely exe-embedded ROM to recover for slice A is on the order of a few KB of tables + constants,
NOT a megabyte.  Convergence is very tractable; the bundle is ~98.4% dead weight for gameplay.

**The 536 CS bytes are 5 ranges (enumerated 2026-07-11):** `8D92..8F91` (512 B — the tile-block lookup
table `table_8d92`), `9592`/`9598..959F` (the tile/block/sprite SEGMENT POINTERS), `95BC..95C3` (the
video-mode flag + the A6FE row-source stride/wrap constants), and `EE6C..EE79` (14 B, a small lookup).
The behaviour dispatch (`AA36`/`EFC4`) and the anim rings are NOT here -- they are already Python /
DGROUP.  So slice A for gameplay = lift those 5 ranges + the DGROUP initial tables (`96D2`… anim,
`1816` font, `C3AA` class, `21D8` hi-scores, the `144F/14C0` name tables) into a byte-verified
`native_rom` module, then slice B rebuilds the cold image from `native_rom` + init + container with the
existing `verify_native_cold_level_data` as the equivalence gate.  A few KB of tables stands between
here and dropping `--bundle`.

**Slice B started (2026-07-13) — the level-ROM (384 B) extracted + WIRED into the live path.**
`overkill/recovered/adapters/level_rom.py`: `extract_level_rom` copies the two measured ranges
(`DS:C4AA..C5E8` the class-override table + all 6 levels' pair lists, `DS:D1BC..D1FC` the tile-plane
footer) out of any data-segment-shaped image; `class_override_pairs_from_rom`/`footer_from_rom` decode
straight from the compact 384-byte blob (no exe_image, no 1 MB scratch buffer).
`asset_codecs.native_level.load_native_level_from_rom` reproduces `load_native_level`'s output
BYTE-IDENTICAL for every level from the ROM + container alone (`tests/test_level_rom.py`, 2 tests).
**Wired into the real cold-start path**: `cold_level_start._load_planet_level_data` now decodes the
class table via `class_override_pairs_from_rom(extract_level_rom(exe_image), planet)` instead of the
raw exe_image byte-walk — full suite green (1405), including the lockstep/gameplay gates that exercise
this path every level.  Still reads the 384 bytes out of the bundle (not yet exe-free): the remaining
Slice B work is the ~9,925-byte shared tile-plane BORDER constant (extract once, same pattern) + a
blank-base builder that assembles the cold image from native_rom + level_rom + the border constant +
the container instead of `MutFlatMemory(exe_image)`, gated byte-exact vs the bundle-seeded image
(`verify_native_cold_level_data`) — then `--bundle` drops.

**Slice B continued (2026-07-13) — the ~9,925-byte border estimate was WRONG (cruder methodology);
the real number is 347 bytes, and TWO more "ROM" tables turned out to need ZERO bytes.**

The earlier ~9,925-byte border figure came from a raw content-diff against a blank baseline -- the
same overcounting trap the CS-segment investigation already burned once ("239 bank bytes diverged...
does not affect game logic").  The RIGHT measurement (read-before-write over 3,000 gameplay frames on
each of the 6 levels, scoped to the tile-plane segment outside the map body) gives **347 bytes across
111 small runs**, plateauing quickly (300 frames already found 259-279 of the 347).  Extracted into
`overkill/recovered/adapters/plane_rom.py` (`extract_plane_rom`/`apply_plane_rom`,
`tests/test_plane_rom.py`) -- **NOT YET WIRED** into the live path (needs the same blank-base
equivalence gate below to close first).  Every byte matches across all 6 levels except ONE
(`0x3A76`), which is exactly the level's own PLANET id -- already computed, not real per-level data.

**Two more tables turned out to be ARITHMETIC, not data -- better than extraction, zero exe bytes:**
chasing the blank-base equivalence gate (below) surfaced that `DS:0x32CA` (the C4DB new-game object
seed's slot table, 36 entries) and `DS:0x8D12` (the C3A6 gameplay-pool seed's slot table, 34 entries)
-- both previously read as exe-derived words -- are exactly `POOL_BASE_EFFECT/POOL_BASE_GAMEPLAY +
i*OBJECT_RECORD_STRIDE` (a compiler-emitted literal for a trivial sequence).  Verified byte-identical
to the live tables for every entry (`tests/test_seed_slot_tables.py`).  `frame_loop.py` gained
`object_seed_slot_table_32ca()`/`gameplay_seed_slot_table_8d12()`; `cold_level_start.py` AND
`native_frame.py`'s `9908` respawn path (the SAME seed re-runs on every in-game death, not just cold
start) both now COMPUTE these tables instead of reading them -- a real simplification, not just a ROM
extraction.  Suite 1409.

**The blank-base equivalence gate found the object-pool table gap (fixed) + a SUBTLER, more important
finding: the bundle's own reference is contaminated, not just the blank base incomplete.**

Fix #3, landed: `DS:0x95D8` (the `7524` allocator's scan cursor for the effect pool -- every
spawn-effect call site in `behavior_walk.py` reads it) was never seeded by the recovered cold-start
init at all; a blank base leaves it 0, so the companion/flame-anchor spawn's allocator scan corrupts
(writes outside the pool). The bundle happens to hold `EFFECT_POOL_BASE` (0x23B4) there -- confirmed
NOT a coincidence (a fresh scan naturally starts at the pool base) -- so `build_cold_level_start_image`
now seeds it explicitly before the companion spawn. `frame_loop.py`'s OWN death-respawn path
(`native_frame.py`'s 9908 handling) does NOT need this: an ongoing game already has a valid cursor
from prior play, only a genuinely fresh session has none.

**Residual (still open, and NOT a simple missing byte): after this fix, the allocator picks the
CORRECT slot in both builds, but three of that slot's fields (`+0x02`/`+0x04`/`+0x08`, x/y/counter-
shaped) still differ -- ref carries VM-witnessed values, blank-base is zero.**  Traced to the ASM
itself: `1010:C453..C460` (the companion stamp) writes only `+0x00/+0x14/+0x16`; `1010:7524` (the
allocator) only ever writes the SUCCESSFUL cursor back to `[95D8]`.  NEITHER touches `+0x02/+0x04/
+0x08` -- so those fields are genuinely never explicitly initialized by the game's own code, for ANY
of the 36 pool slots.  **The bundle's non-zero values there are therefore its OWN residue from the
attract loop's self-playing gameplay demo (which the bundle was captured AFTER running through, at
`1010:D007`) -- not a "true cold boot" value.**  A real DOS EXE's uninitialized data segment is
zero-filled by the loader, so a genuinely fresh boot (no attract first) would ALSO read zero there --
meaning the blank-base build is arguably the MORE faithful one for this field, and the bundle (used as
`exe_image` by every existing test/gate) has quietly been a "warm, post-attract" cold-start reference,
not a pristine one, this whole project.  **Do not patch this by extracting the bundle's garbage as
more ROM bytes** -- that would enshrine contamination as data.  The right next step is verifying a
blank-base cold image against a REAL VM TRUE cold boot (power-on, no attract cycling first, via a
cold-start demo) instead of the bundle, which is the correct oracle this comparison actually needs.
Until that's done, `--bundle` stays; the gate is not closed, but it has narrowed to one well-understood,
correctly-diagnosed question rather than an unknown pile of missing bytes.

**Attempted verification (2026-07-13), INCONCLUSIVE -- do not trust either number yet.** Tried to find
the exact present-frame window where the menu becomes interactive (to inject an immediate FIRE press
before the attract could run any gameplay, giving a genuinely attract-free VM oracle for the disputed
fields). Two measurements CONTRADICTED each other: a per-present-frame video-mode trace found text
mode (mode 3) until frame 447 with the FIRST graphics content only appearing then (the blueprint, not
a menu); `probe_coldstart_frontend --sequence` on the SAME demo classified frames 1-99 as "menu" (by
CS:IP range 0x5500-0x5C50) -- impossible if the screen is still text-mode.  This means
`classify_screen`'s IP-range heuristic is triggering on code execution in that range for a reason
UNRELATED to a visually-drawn menu (an early boot-time call through the same address range, most
likely), not that the menu is genuinely shown from frame 1.  Not resolved -- needs a proper trace of
WHAT reaches 558B-range code that early, not another timing guess.  Left open rather than forced.

**Refinement (2026-07-11) — the rb/rw count is a LOWER BOUND; validated the DGROUP reduction.** Zeroing
the whole 64 KB CS segment except the 5 rb/rw ranges and running 600 frames leaves the **DGROUP
game-logic state byte-exact (0 divergence)** — so the recovered init + those 5 ranges fully determine
the game state.  BUT 239 bank bytes diverged, because the frame also reads CS tables via DIRECT
`mem.data[seg*16:…]` SLICES (the tile plane `CS:[9592]`, the sprite banks `CS:[95AE]`, the glyph font)
that bypass the `rb/rw` tracker.  So the true CS footprint = the 5 rb/rw ranges + those slice-read
graphics tables (mostly the container-loaded banks, already asset-derived, + the embedded font/tile
tables).  Next: extend `measure_rom_footprint.py` to trap the slice reads too, then the footprint is
complete and slice A can enumerate the exact `native_rom` set.  The headline holds: the game STATE is
fully reducible; the remainder is bounded graphics tables, most already in the container.

**Slice-read trap done — the CS "ROM" is complete + tiny.**  Wrapping `mem.data` to record slice reads
over gameplay found **0 CS-segment slice reads**: the frame reads the CS code segment ONLY through
`rb/rw`, i.e. the ~580-byte range set (`8D92..8F91` table, the `9590..95C4` pointer/video block, the
`EE6C` lookup).  So the 239-byte residue from the zero-except-ranges test is NOT a code table — it is
the video/save-under PAGE content (a presentation buffer the present-half writes/reads in the segment
region), which does not affect game logic (DGROUP stays 0-divergence) and is regenerated by rendering.
**Conclusion: the VM-less ENGINE (game logic + state) is fully reducible to the recovered init + ~580
bytes of CS ROM + the container.**  Slice A is therefore: byte-verify those ~580 CS bytes + the DGROUP
init-table remainder into `native_rom`; slice B rebuilds the cold image from `native_rom` + init +
container (gate `verify_native_cold_level_data`) and deletes `--bundle`.  The bundle's remaining role is
only as the seed for the still-blank video pages, which rendering overwrites.
