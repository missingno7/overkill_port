> **THIS FILE IS A JOURNAL.** The project's plans + state live in
> [`docs/overkill/campaigns/`](campaigns/README.md) — the campaign model (adopted 2026-07-05, the
> pre2 convergence structure): ONE campaign per session, driven toward its done-condition; done
> includes hook retirement; NO re-banking plans. ADR-1: **the DGROUP image is the game state**
> (byte-backed, named views over it; `NativeGameState` is a render projection only).
>
> Orientation for a fresh session: `CLAUDE.md` → `campaigns/README.md` (pick the active campaign) →
> the newest journal entries below (newer wins on conflict). Standing mechanisms (check BEFORE
> building tooling): `timing_fastforward.advance_frames_fast` (never poke CS:066B),
> `recovered/islands.py` (@recovered_island + gen_island_manifest), the state-view names
> (`views/object_slots.py` OFF_* / domain accessors), `adapters/flat_memory.py`,
> `probes/_harness.py`, **`probes/_shadow_cache.py` (2026-07-06: the demo walk shadow auto-records
> per-frame VM states on first run and replays them in ~40s instead of ~5min -- same states, same
> comparison; pass `vm` to force the live oracle; caches live in `artifacts/shadow_cache/`,
> gitignored, keyed on the demo file sha1 + frame budget)**, `scripts/lindis.py` (encoded targets),
> `scripts/behavior_zoo_xref.py`; cold-boot probes MUST pass
> `overkill.launch.build_command_tail("tandy", "pc")`.
> Suite green: 1225 passed / 23 skipped (2026-07-06). **SCENE.MD CAMPAIGN DONE**: `play_native --level
> 0` (cold, no snapshot) now spawns/moves a real enemy wave, VM-free (`verify_play_native_cold` PASS).
> **THE ENTIRE DEMO WALK IS NATIVE (2026-07-06): 8294/8294 frames, ZERO divergence, ZERO gaps.**
> Every actor/spawn/death/pickup in the whole played L1 demo runs natively byte-exact (23 behaviors +
> collect + the 9EA3 death chain; BDD0 wired through AFD8). The enemies_l1 + scene campaigns' walk
> work is COMPLETE for L1. Next frontier: play_native integration polish, other planets' controller
> families (0x1c etc.), the 9734/9902/9908 transition continuations, HUD/menu wiring, audio.

## 2026-07-07 - OWNER PLAYTEST #2 + the NEW VERIFICATION BAR: 1:1 demo frames, native vs VM page

**Owner findings (all real; the state gates saw none of them):** (1) the player ship and its
explosion draw HALF -- FIXED this session: the +0x10 second-slot projection was never computed
on the cold path (the docstring's "+0x10 is always 0" claim was WRONG; the 356C handler projects
the SAME record at ``x + 0x10`` -- 16 units along the flight axis -- with its own cull, and the
rule is now oracle-proven 8293/8293 against the cached VM values, one-present-scan phase);
(2) **the terrain TILES never render** -- play_native's frame = starfield plate + sprites; there
is NO native tile-plane layer (the VM scrolls tile rows into the work page via 0E9C/A781; that
compose is UNRECOVERED) -- the biggest visible gap, top of the queue; (3) a shot deployer
"disappears but keeps deploying" and the shot player ship "disappears" -- likely the ANIM/VARIANT
sprite compositors (`object_sprite_blocks` SKIPS ``anim(+12) != 0`` and ``variant(+24) != 0``
records -- the explosion/hit-flash frames are exactly those); (4) the resizable-window crash --
FIXED (scale to the live window size).

**FRAME-4000 SOLVED: the ship overdraw is the DYING MODE.** ``2326 == 3`` at that frame -- the
ship was mid-death-explosion; during dying the visible anchor sprite is the ``+08`` explosion
counter mapping (the 9AFF death-tail contract play_native's death branch already implements),
NOT the ``+08 sprite cell``s normal read -- the probe's compose lacks that mapping and drew the
normal ship (109 px overdraw) where the VM showed explosion frames.  FIX THE COMPOSE: when
``2326 == 3`` (or A95A==FFFF), map the anchor sprite from the +08 counter exactly as
play_native's dying branch does -- and that same mapping is what the OWNER saw missing
("explosion shows only half / ship disappears when shot").  Remaining at 4000 after the anchor:
~1978 px from the other pools (census next).

**FRAME-4000 ATTRIBUTION (per-record, the One-pool wrapper recipe)**: in the SPECIAL pool only
the ANCHOR produces pixels natively (109 px, ALL overdraw -- the VM page has NO SHIP at frame
4000: the VM suppressed the anchor draw in a state the native ignores -- dying/warp/invisible?
check DS:2384/A95A/2326 at that frame); the remaining ~1978 px must come from the effect/object
pools (finish the census with the same wrapper -- likely the gameplay-pool 7596-vs-7746 size
mismatch).  NOTE the wrapper must wrap ALL pools; the special-pool non-anchor records produced
NO blocks (their pool-view fields differ from the raw record dump -- verify the projected pool's
field mapping while at it).

**THE FULL A846 DRAW ANATOMY (decoded to the loop level)**: A849 loop (32CA?) -> 5AC8 per record
(the ERASE/restore pass) -> A85E loop cx=0x22 over **8D12** -> 5AC8 -> 4CED(?) -> A879 loop
cx=0x22 over **8D12** -> **call 7746 DIRECTLY, unconditionally** (the gameplay pool ALWAYS draws
the 1x1 8px routine -- NOT the 7596 draw-type dispatch!) -> A891 loop cx=0x23 over 32CA -> 7596
when ``+0x0A == 0`` -> A8C4 loop cx=0x24 over 32CA -> 7596 when ``+0x0A == 1`` (+ the A8F7
[9788] outro record when A47C!=0).  NATIVE DIVERGENCE FOUND: object_sprite_blocks applies the
7596 dispatch to ALL pools -- the gameplay pool must use 7746 only.  PHASE-FIX NULL RESULT: the
one-frame page shift changes NOTHING (identical diffs) -- the layer-0 specials are genuinely
absent from the page around frame 4000 despite A891 drawing them; NEXT EXPERIMENT: pattern-search
the VM page for one missing record's sprite pixels (drawn elsewhere? never drawn? check 5AC8's
erase semantics and whether the A849 first loop erases 32CA BEFORE A891 redraws -- and whether
A891's 7596 path bails inside the 768E/75A6 resolvers for those records).

**PHASE PIN (the 97B2 stage order, from native_app.py)**: per tick -- 0672 / 511F / **A846 (the
draw walks: A87C then the A891 0-layer then the A8C4 1-layer)** / 981F / **5BDC (present)** /
**A90C (the projection scan -- AFTER the present!)** / 9B2E (with the A9D3 walk INSIDE).  So at
the cached walk boundary the page was drawn with the PREVIOUS tick's +0x0C cells while the
records carry the FRESH ones -- the native compose (fresh cells) is ONE PRESENT AHEAD of the
page.  Sprites that just entered the screen explain pure-overdraw diffs.  RECONCILE either by
composing with the previous-tick cells (cache the prior frame's +0x0C during iteration) or by
diffing against the NEXT frame's page.  THEN re-measure; only after the phase is exact do the
remaining diffs mean real render gaps (anim/variant compositors, tiles).

**CORRECTION (same night): +0x0A is a DRAW-LAYER, not a suppression.** The 32CA pool is drawn in
TWO passes: A891 (cx=0x23) draws the ``+0x0A == 0`` records FIRST, then A8C4 (cx=0x24) draws the
``+0x0A == 1`` records ON TOP (both through 7596; same BDAC/2350/type-1 skip in each; an A87C
loop precedes them -- read it).  So the walk-boundary page (what the cache stores) is a
MID-COMPOSE state -- the +0x0A==0 records were absent from it for PHASE reasons, not eligibility.
NEXT for the 1:1 instrument: pin the 97B2 stage order (native_app's GAMEPLAY_FRAME_STAGES) to
learn WHICH passes have run at A9D3, and either (a) move the comparison point to a fully-composed
phase, or (b) reproduce the exact mid-compose state.  ALSO adopt the two-pass +0x0A layer ORDER
in the native sprite compose (draw 0-layer under 1-layer) -- ordering affects overlaps.

**THE DRAW-ELIGIBILITY GATE IS FOUND (1010:A8C4..A8F4, the special-pool draw walk)**: per active
32CA record -- skip when ``[BDAC] != 1 AND [2350] <= 0xB6 AND +0x16 == 1`` (a type-1 late-level
suppression), then **skip unless ``+0x0A == 1``** (the confirmed gate), else ``call 7596`` (the
draw dispatch).  Plus A8F7: when ``[A47C] != 0`` also draw the ``[9788]`` outro record.  The
FIRST loop (A894.., the gameplay pool via 7596 at A8BE) has its OWN gates -- read A880..A8BE
next; that likely explains the frame-1000/7000 overdraw.  Wire these gates into
``object_sprite_blocks``/play_native and re-run verify_native_frame_1to1 -- expect the mean to
collapse toward the ~40-px star-phase floor.

**FIRST 1:1 LEAD (2026-07-07, late)**: the overdraw is PARTLY the ``+0x0A == 0`` records --
skipping them in the sprite layer collapses frame 4000 from 2087 to 343 px with ZERO vm-only
regressions (frames 1000/7000 unchanged at 740/1414, a second cause there).  NEXT: confirm the
+0x0A skip in the A90C/5A92 present-scan ASM before adopting it -- 5A92 decoded: es=[9598],
di=+0x0C, si=+0x0E, then ``jmp cs:[5AB6 + (draw_type(+0x14) + 3*mode(95BC))*2]`` -- a
(draw-type x video-mode) HANDLER MATRIX; the Tandy column
(34AD/34D8/3542) decoded: they are GATELESS row blits from ``si = +0x0E`` (34AD = the two-slot
form: 16 rows x 8 movsw from +0x0C, then AGAIN at ``di = +0x10`` / ``si += 0x140`` -- the
half-stride second half).  So the suppression is NOT in the present -- it lives in the 75A6/768E
RESOLVERS that compute ``+0x0E``/``+0x0C`` per record (they run before the present; find their
+0x0A / anim / variant gates there).  Then chase the 1000/7000 overdraw family (native draws records the VM page lacks --
classify via the frame-4000 recipe: dump live-projection records, diff the block sets).

**THE 1:1 INSTRUMENT IS LIVE**: `verify_native_frame_1to1` samples cached frames, composes the
native frame (live VM stars + the pre-state's own pools/projection cells) and diffs the playfield
vs the VM's own page.  FIRST READING (L1 demo, every 1000th frame): mean 1085 px/frame of 39936
(~2.7%), worst 2087 @ frame 4000 -- the diff = the skipped anim/variant sprite routines + the
missing tile layer where terrain scrolls in + residue.  Drive it to ZERO, then flip it to a gate.

**THE OWNER'S BAR (adopt as the standing verification model): play the demo on NATIVE and compare
1:1 vs the hybrid/VM.**  The walk-shadow cache already stores the FULL VM machine state per frame
(including the video pages), so the gate is buildable TODAY: `verify_native_frame_1to1` -- for
every cached frame, compose the native frame from the pre-state and pixel-diff against
`render_present_page_indices` of the VM's own page.  Land it first as a REPORTING probe (the
diff count is the TODO list; the tile layer will dominate), then drive it to zero: tiles ->
anim/variant sprite routines -> any residue.  This replaces "probe the pieces" with "diff the
whole screen", which is what the owner is asking for.

## 2026-07-07 - THE LEVEL-SELECT MENU IS NATIVE: the L1 VERTICAL SLICE IS COMPLETE

play_native's front-end is now the real game flow: title (OKMENU) -> **the LEVEL-SELECT screen**
(LEVSCR + the two D4AA cursors from CHOOSE.ENC) -> the picked level boots (game over returns
title -> menu -> fresh session at the new pick).  `native_video/level_select.py` composes the
page; the cursor cells come from walking the natively-decoded CHOOSE.ENC (six 33x136 planet-cell
frames + three 27x40 difficulty cells) -- `verify_native_level_select` pins the walked offsets
against the live snapshot's runtime-built CS:D37E table (exact), the static DS:BEDE/BEEA xy
tables against the live ones (exact), the stamp positions, and the D424+9744 cell->planet
mapping (cell k == level index k, cell 5 == the mothership).  Movement = the RECOVERED
D476/D480/D488/D490 handlers; fire = the RECOVERED resolve_level_select_fire_d424.  BONUS: the
second (BEDC) cursor turned out to be the DIFFICULTY selector (EASIER/NORMAL/HOLY COW!) -- BEDC
is the difficulty global the C237 spawn throttle reads; the menu's D-key cycles it and the pick
is written into the session image.  **The owner's L1 vertical slice is DONE: cold boot -> title
-> level select -> L1 with full HUD -> death/respawn -> level end -> L2 -> game over -> title ->
again, every screen native.**  Next per the plan: OWNER PLAYTEST, then the L2 zoo one-at-a-time
(0x21 the wave driver first), then L3.

## 2026-07-07 - menu recon: the LEVEL-SELECT loop + cursor draw are fully mapped (wire next)

The D3F0 level-select loop: per frame -- 0672(?) -> 511F -> **D4AA (the cursor draw)** -> 5160 ->
50C9 (frame wait) -> D434 (the 98BE input dispatch: bits 1/2/8/4 -> the RECOVERED
step_level_select_* handlers on BEDA; bit 0x10 FIRE -> the RECOVERED resolve_level_select_fire_d424
-> [2356]).  **D4AA**: (1) restore the saved background patch (a 5A6C cell from ``[9598]:8000`` --
the old-cursor erase); (2) the BEDA cursor: xy from the 6-entry word table ``DS:BEDE[BEDA]`` ->
5A00, cell pointer from ``CS:D37E[BEDA]``, blitted from the ``[9598]`` segment; (3) a SECOND cursor
keyed on ``DS:BEDC`` (xy table ``DS:BEEA``, cells ``CS:D37E[BEDC+6]``).  To wire natively: identify
what the ``[9598]`` segment holds at menu time (the cursor cells' home), decode the two xy tables +
cell pointers from the image, and compose LEVSCR.ENC + cursors in play_native's front-end with the
recovered grid logic (planet = D424's value; level_index = LEVEL_INDEX_TO_PLANET.index(planet)).

## 2026-07-07 - GAME OVER -> TITLE is native: the 98EB flow wired (banner + hold + fresh session)

The last RecoveryGap in play_native's death path is gone.  98EB decoded: 5145 (mode-1 no-op on
Tandy) -> 57E6 (the game-over jingle 5, host audio) -> 5C35 (the banner: the ``CS:[95B2]`` cell at
``(0, 0x4E)`` through the 5C46 wipe -- and [95B2] is **THEND.BIC**, byte-matched to the natively-
decoded asset) -> a 0x96-frame 50C9 hold -> 5283 (score->high-score check + the far 1F8F:0000/0076
entry flow -- NOT recovered, logged + SKIPPED in the native path, never faked) -> jmp 96E0 (the
title flow).  play_native: lives==FFFF now freezes the playfield, overlays the 44x320 THEND banner,
holds 150 ticks, returns to the title screen, and Space starts a FRESH session (the same cold-boot
machinery; 96EE resets score/lives).  ``verify_play_native_gameover`` gates the chain: the banner
asset byte-exact vs the VM segment, the last-life death fires the 98EB condition, the [978D] cheat
guards it, the restart is fresh.  The L1 vertical slice now has: cold boot -> title -> L1 with HUD
-> death/respawn -> level end -> L2 ... -> game over -> title -> again.  Remaining for the slice:
the MENU FLOW polish (level select / options wiring).

## 2026-07-07 - THE HUD IS WIRED: play_native renders the full panel, BYTE-EXACT vs the VM page

`native_video/hud_panel.py` (+ the `adapters/hud_panel_state.py` state reader) composes the WHOLE
right-third panel from the natively-decoded PANEL.ENC: the 5C9A backdrop (see below), the 859E
chrome, the 61DC counters, the 60F3 lives row (ship/empty cells, 8-byte spacing -- 613E's Tandy
step is di+=4 called twice), the 77F6 energy bar (A97A>>1 filled FFCE/C4EE rows growing UP from
(0x1D,0x5F), zero-tail to 0x2C rows), the 5EDB score line and the 60E3 planet digit.
**`verify_native_hud_panel` proves the compose BYTE-EXACT against the L1 cache frame-0 B800 page**
(10400/10400 panel bytes, natively-decoded asset: `deplanarize_tandy(..., sprite_mode=False,
emit_item_headers=True)` == the VM's CS:[95B4] segment exactly).  play_native overlays
`panel_indices_from_page` per frame (~0.9 ms); `verify_play_native_render` now also gates the
panel pixels.  KEY ORACLE FINDS: (1) the 5C46/375B curtain wipe's FINAL state is NOT a plain
cell paste -- scanlines 0..4/194..199 stay black, 5..100 carry cell row y-1 (one LOW), 101..193
carry row y (pinned by driving the ORIGINAL 5C9A on a zeroed B800 and mapping every scanline);
(2) PANEL.ENC == the VM panel segment byte-for-byte.  The L1 vertical slice's HUD step is DONE;
next: game-over -> title (98EB), then the menu flow.

## 2026-07-06 - HUD recon (the L1 vertical slice, step 1): the panel anatomy is mapped

The right-third panel (cols 216..319) at level start decomposes into (validated against the L1
cache frame-0 B800 page as a byte oracle):
- **already-recovered cell composers, verified pixel-exact in place** (3046/3046 px on frame 0):
  `compose_status_cells_859e` (the four WEAPON/MISSILES/GADGETS/UPGRADES rows; descriptors
  SS:9682/968C/9696/96A0, marker [95FA], highlight [BDAC]/[BE16]) + `compose_status_counters_61dc`
  (the ship-status circle cells + the energy strip; counters 2368..2372, marker A95A/2374).
  panel_source = the decoded PANEL segment CS:[95B4]; dir_table = CS:0BE4.  PANEL.ENC decodes
  natively to 51288 bytes of {rows,width} cells (the cell LIBRARY, not a backdrop).
- **decoded-but-unwired dynamic pieces** (the residue's dynamic part): the 6176 per-frame composite
  calls 5EDB (status text, composer exists) -> 60F3 -> 61DC (wired above) -> 60E3.  60E3 = the
  score digits + planet-number draw (bp=235C block, the 2362 planet xlat, via 518C/519A);
  61C7 = the 2368..2372 counter DECAY beat.  The lives-ships row is A95A-driven.
- **the static backdrop is CRACKED: it is ONE PANEL CELL.** ``1010:5C9A`` (called at level entry,
  971D) draws dir-cell **0x25** at ``xy_to_di_5a00(0x1B, 0)`` = di 0x6C (pixel col 216, row 0)
  through the ``5C46`` progressive-wipe blitter (rows in +2 passes -- the wipe-in effect; the END
  state equals a plain ``paste_panel_cell``).  Composing backdrop-0x25 + 859E + 61DC on a blank
  page reproduces the frame-0 panel to ~9.1k exact px of ~11k; the visible remainder is the 60E3
  dynamic draw (the PLANET digit + score digits via 518C/519A, bp=235C, the 2362 planet xlat) plus
  per-frame cell states.  The native HUD compose is therefore: paste 0x25 -> 859E cells -> 61DC
  counters -> 60E3 planet/score digits -> 5EDB text, all from the natively-decoded PANEL.ENC
  (51288 B of {rows,width} cells) + the CS:0BE4 directory.  (5A00's convention: AL = x cell-col,
  AH = y scanline.)  60E3's body is TINY: the 518C zero-terminated string loop over the DS:235C
  block (with 3153's 0x10-colour / 0x11-cursor escapes -- the SAME loop compose_status_text_5edb
  already implements) + ONE planet char from the byte table ``DS:2362[planet 2356]`` via 519A
  (Tandy mode = the recovered 3153 glyph blit; 519A also has a [21A2]-gated deferred-queue path
  via [9594]/[2160] -- gameplay runs the direct path).  The backdrop cell 0x25 BAKES the green
  zeros, so at frame 0 only the planet digit visibly differs -- score redraws matter once play
  starts scoring.
- The dual-page toggle is 511F gated on CS:[95BC]==1; Tandy runs mode 2 (95BC==2, single-page).
- 9773 confirms: lives==FFFF -> jmp **98EB** (the game-over flow) -- the step-2 decode target.

## 2026-07-06 - twelve more L2-zoo behaviors native; OWNER REDIRECT: L1 vertical slice first

Landed one-at-a-time on the 4s cached L2 gate (each individually zero-divergence): **0x8F** (the
[232E]-phased pulser + sprite-0x44 C237 child; the throttled stale-bx artifact writes
DS:[sprite_base+8]), **0x46/0x47** (the [2338]-anim beacons over the shared 87B5 tail -- drift right
above x=0x60, else wait for [2330]==0x7F then dir=4 + C237), **0x2E** (the drift-seeker: target-x
rides [A278], 4D95 sprite, the 8802 x==0x80 one-shot seeds target (anchor_y+8)&~1 / x=0x7530, then
the B729 seek -- NOTE B729 uses the record's OWN +0x32/+0x34 with the LIVE [2308] mode), **0x2B**
(sprite 0xA5+[233C] over the extracted 8744 steer tail), **0x34** (the half-screen-mirrored C237
dropper, planet-keyed sprite), **0x40** (the random-axis jitterer -- the [96EC] cell-offset pair
picks +0x02/+0x04), **0x42** (the [232E] bobber), **0x41/0x43/0x44/0x45/0x4A/0x51** (the 8BC8..8BF5
waypoint-seed stubs -- each seeds its own +0x36 table and retags as the recovered 0x12 follower),
**0x4B** (x==0x40 morph into the 0x33 bounce), **0x4C** (the glide-back), **0x4D** (the x==0x60
morph into the 0x39 faller). Both shadows zero-divergence (L2 cached + L1 8294/8294). The L2 gap
frontier after this batch: 0x22(x127)/0x4F/0x48, the BD17 decay beats (0xc/0x5), pickups 1/3/4,
the 0x06 ADC9 death, object type 1.

**OWNER REDIRECT (mid-batch): stop the L2 zoo here -- complete the L1 VERTICAL SLICE first** (HUD,
menu flow, game-over->title: the cold-starting game with L1 fully playable). The L2 work above is
banked; the zoo grind resumes only after the L1 product loop is closed.

## 2026-07-06 - the WHOLE L2 scenery family is native (all 8) + TWO latent bugs fixed (0x35 wrap, 62F6 field binding)

The reverted batch re-landed ONE AT A TIME on the 4s cached L2 gate -- and both "batch divergences"
turned out to be pre-existing bugs the new handlers merely exposed (details in loop_blockers.md,
RESOLVED entry): **0x35**'s sprite formula missed the 16-bit `inc` wrap (`[2342]==0xFFFF` -> VM 0x71
vs native 0x8071 -- the persistent DS:250D byte), and `_postmove_bc45`'s 62F6 call MIS-BOUND the
scanner fields (`draw_layer` got +0x0A, `object_type` got +0x16; the ASM reads +0x16 for the gate and
+0x14 for the wide key -- exactly the canonical `OFF_DRAW_LAYER`/`OFF_OBJECT_TYPE` aliases; every
other caller was already right). The L2 0x8A scanner (+0x0A==0) was the first record in any demo to
discriminate the binding -- it was being gated out of the shot-collision scan entirely.

Native now: **0x39** (x>=0x80 faller, AF60 double-step), **0x3A** (233C-anim hover, 5E1B/5E42 homing),
**0x3B** (4D95-random glitter), **0x3C->0x3D** (x==0xB0 lurker morph into the 88CF bounce),
**0x3E->0x3F** (x>=0xA0 arm + the shared 8744 steer tail, extracted from 0x29's steer section),
**0x8A** (the 0x89-tail scenery emitter). Gates: the 4s cached L2 shadow AND the full L1 demo shadow,
both zero divergence. The L2 walk's remaining gap frontier (from the gate): object type 1, behaviors
0x2b/0x2e/0x34/0x40/0x42/0x44..0x48/0x4b/0x4c/0x4d/0x4e/0x8f, the 0x0C BD17 decay beat, pickup
kinds 1/4, and 2x "behavior 0x06 ADC9 death".

## 2026-07-06 - MILESTONE: L1 ROLLS INTO L2 -- the 9744 next-level load is native, session carried

play_native's SCRIPTED exit now runs `_load_next_level` instead of stopping: the SAME cold-boot
machinery reloads the next level (the real 9744 -> 9755 tail's full reload) with the SESSION
persisting -- score (2314/2316) and lives (2358) carry over (96EE is fresh-session-only and gets
overwritten). The walk image's BUFFER is replaced in place so every closure keeps its reference;
the sprite context/starfield/game rebind via the `cell` holder; the walk tiles are computed fresh
per tick (the level plane can now CHANGE mid-run). `verify_play_native_levelend` PASSES the whole
chain: scroll the plane -> arm -> outro -> autopilot -> LEVEL COMPLETE -> **planet 2 boots with the
score/lives carried and the L2 wave controller on stage** -- then the L2 walk gaps on its KNOWN zoo
frontier (0x39 scenery spawns in L2's very first script row), the honest boundary: **the L2 zoo
(0x39/0x8A first) is now the direct blocker for continuous L1->L2 play.** (RESOLVED same day -- the
whole scenery family landed; see the newer entry above.)

## 2026-07-06 - MILESTONE: LEVEL COMPLETE fires natively -- the whole outro plays, autopilot and all

The outro PHASES are native (`run_outro_script_99f6` in behavior_walk.py + the pure
`outro_autopilot_bits_9ad1`, CACHE-VERIFIED against the L2_full outro's recorded 98BE values):
phase 1 autopilots the ship to the A358 target (the synthetic 98BE input bits REPLACE the keyboard
in play_native, exactly as the original's scripted input overrides the poll; the screen-edge clamp
is OFF during the scripted phases -- the trace shows the fly-off crossing x=0); arrival spawns the
0x52 outro object ([9788] = its slot) and re-dispatches SAME-frame (the jmp 99F6 tail); phase 2 adds
the recovered A39A/A39C counters and flies to A35C; phase 3 (the recovered `step_a47c_handler_9a16`)
holds the fly-off input while the counters settle, then `A47C = 4` -> the detector's SCRIPTED exit.
play_native reports **LEVEL COMPLETE** (fail-loud hold; the 9744 next-level load is the next slice).
`verify_play_native_levelend` PASSES end-to-end: scroll the whole plane -> arm -> the four 0x53s
animate -> the autopilot flies -> SCRIPTED at tick 4593. Both cached shadows + all play_native
probes green. (Phase 3 completes within the phase-2 tick for an undamaged ship -- the settled-
counter fixed point -- matching the pure contract; the traced 38-frame phase 3 was a damaged ship
refilling.)

## 2026-07-06 - PROCESS BREACH owned + fixed: f1de17d was committed RED (one failing test)

The f1de17d level-end commit went in with `test_native_game_step_scroll_declines_on_milestone...`
FAILING -- the commit command was shell-chained off the gate-output `cat` instead of a verdict
check, so the red suite didn't stop it. The failing test encoded the OLD milestone contract (the
None-decline "stay VM-owned this tick"), which the slice intentionally replaced with the
live-traced apply-and-report contract; the test is UPDATED to assert the new behavior (not
weakened -- the new contract is the VM-traced ground truth, and the test now checks MORE: the tick
applies, the milestone is reported, the row lands on it). Fixed in the follow-up commit with a
freshly green full suite. Lesson recorded: never chain `git commit` after a verification command
whose failure doesn't gate it -- read the verdict first.

## 2026-07-06 - MILESTONE: the LEVEL END arms natively -- the scroll crosses the whole plane, the outro takes the stage

The A66F milestones are composed natively: `step_scroll_with_milestones` (systems/scroll.py) APPLIES
the tick at the two once-per-level rows (live-traced) and REPORTS the milestone instead of the old
None-decline (`ScrollTickOutcome.milestone`; NativeGame.step_scroll switched over -- normal ticks
byte-identical, demo-replay equivalence green). 0x0E52 = the C591 Tandy no-op (nothing to do);
**0x0EA0 = `run_level_end_arm_a680`** (behavior_walk.py): `A47C = 1` (the scroll gate then holds),
the 62AA sweep (sound 8 + every remaining on-screen enemy dies the full BFC7 death, score and all),
and the FOUR A3EE outro objects spawn (behavior 0x53, native). play_native fires it the moment
row_base lands on the plane end.

Landing this exposed + fixed a REAL pacing bug: `advance_object_frame` gated the whole counter
cascade on `A47E != 0` (a smoke-probe shortcut) -- the ASM's 5F61 advances the counters ALWAYS; the
A47E==0 branch only adds the A480 wave-cleared countdown (now modeled; its ==0 music restart stays a
host/audio boundary). Every animation clock used to FREEZE whenever the field was clear.

New probe `verify_play_native_levelend` PASSES: the scroll crosses the ENTIRE plane (no 0xE52
stall), arms at 0xEA0, the four 0x53s animate on stage, the scroll holds. All four play_native
probes + both cached shadows stay green. **Two recorded blockers for the FULL natural playthrough:**
(1) the row-4 script entry spawns the 0x21 wave driver via the 4A65 walker's declared leftover-ax
gap (the probe skips that single entry, documented); (2) the outro PHASES (9A78's 9AD1 autopilot --
DECODED: it drives the ship via synthetic 98BE input bits toward the A358 target -- then 9A3E/9A16,
both partially recovered) -> A344 -> the 9744 advance + next-level load. Those are the next slices.

## 2026-07-06 - the 0x1C/0x1D/0x1E planet-2 controller family native; OBJECT TYPE 1 scoped

The planet-2 wave is native (see the 4417360 commit message for the full decode): 0x1C (the shared
8D4F/027A seek + the 03A6 one-child arrival), 0x1D (the ALREADY-RECOVERED `object_update_b86d` wired
+ its caller-owned ASM extras -- incl. a cached-gate-caught fix: 5E1B WRITES the record's +0x2C/+0x2A
delta cells on the edge path), 0x1E (the vertical patrol: seek own target, on arrival 7476 shot +
Y-target toggle 0<->0xC0). L2 zero-div, L1 8294/8294, free-run 200/0, suite green.

**OBJECT TYPE 1 scoped (the next L2 item, 807 hits -- a TYPE, not a behavior):** the AA36 type table
is `0:BC45(nop) 1:AD04 2/4:EFAE 3:44AF 5:AAC2(pickup) 6:AB10(companion) 7:C3F8`. **AD04 = the
player's FOLLOWER objects**, dispatched by record IDENTITY: `bp == [A966]/[A968]/[A96A]/[A96C]` (the
four flames 9FAF positions) -> AB71/AB69/AB61/AB59; `bp == [A962]/[A964]` (the two ring-delay
followers A031 feeds) -> ABA3; `sprite == 0xF` -> ABCA (the A96E-registered indicator, cf. the 9D91
spawn); with an early-out `BDAC != 1 AND 2350 <= 0xB6 -> ret` (followers act only past row 0xB6 or
in boss mode). Sub-workers to decode for the slice: AB34/AB4F (positioners?), AC28 (the RECOVERED
tile-collision probe plan), AC81 (?), the AB99 BFC7-on-the-follower death indirection, the ABF3
common tail, and the A42C/A42E pointer choreography ([ptr] = FFFF detaches on the dying pose).
The remaining L2 frontier after type 1: 0x3c(571) 0x2b(516) 0x23(440) 0x2e(300) 0x8f(274)
0x21(264, the wave driver -- `wave_driver_dispatch_b556` is already pure!) 0x3e/0x2c/0x8a/0x39/
0x40/0x3a/0x34/0x22/0x47/0x3b/0x4b/0x4c/0x4e/... -- each a small slice on the 4-second cached gate.

## 2026-07-06 - SEVEN behaviors in one pass (the cache pays off) + a 3-bug fix in the 7420 pickup stamp

With the 4-second cached L2 gate, recovered in ONE sitting: **0x52** (the phase-1 outro no-op),
**0x53** (the A3EE outro objects: sprite = [96D2 + (2328 & ~1)] + rec[+0x36]), **0x31** (sprite 0x2E,
x += 3), **0x33** (THREE chained AFD8 steps with BDD0; first block flips the vertical phase, dir ^= 2),
**0x35**/0x22 (the B3BF sprite ((2342+1)>>1)+0x71, x += 1 (+1 on planet 0); at x >= 0xA0 the full
BFC7 death + the B402 8-way radial burst of behavior-3 children -- the recovered AED8 alias),
**0x38** (dir snaps 3/5 at the y rails, sprite 0x6E, one 2px AF63 step), and **0x06** (wired the
ALREADY-RECOVERED `object_update_ae2c` -- the tile-gated scroll-left mover).

The L2 shadow then caught a REAL LATENT BUG the whole L1 demo could never expose: a 2-byte divergence
(frame 4479) forensically traced -- cache-frame inspection -> a native write-trap -> a live-VM
write-watch pinning the writers at 1010:7437/7470 -- to the **7420 pickup stamp**: the real ASM
stamps ``x = [2378] + [A278]`` (the drift IS added), ``y = min([2376], 0xC0)`` (clamped), and
``sprite = [237A] + 0x46`` (KIND-keyed -- L1 only ever drops kind 2 = 0x48, so the old fixed-0x48
model was L1-blind; L2 drops kind 1 -> 0x47). Fixed to the ASM.

**Both cached gates PASS at zero divergence** (L1 8294/8294; L2 6561 frames). The unmasking went
DEEP: the L2 frontier is now the real planet-2 zoo (~30 behaviors incl. the 0x1c/0x1d/0x1e family,
0x39/0x3a/0x3b/0x3c/0x3e, 0x40/0x42/0x44..0x4f, 0x8a/0x8f, object type 1, the 0x0C decay, pickup
kinds 1/3/4) -- each now a small slice with a 4-second gate.

## 2026-07-06 - the WALK-SHADOW CACHE: demo re-verification drops ~5min -> ~40s (the grind fix)

The demo walk shadow's VM side is deterministic per demo, so `verify_native_walk_demo` now
AUTO-RECORDS, during a normal live run, exactly what it consumes per walk frame (the full pre-state,
the post DGROUP window, sp) into `artifacts/shadow_cache/<demo>.walkcache` (delta-encoded: the
between-frame DGROUP writes as sparse runs, the tile plane dedup-by-hash, the static remainder once
from frame 0 -- the 8294-frame cold demo caches in 46MB), and REPLAYS it on subsequent runs: the
SAME states through the SAME `_check_frame` comparison body (refactored so both paths share it --
the verdict logic cannot drift), no VM. Proven: the cached replay reproduces the live run's verdict
identically (8294/8294, diverged=0, combat-exposed=168) in **38s vs ~5min**. `vm` on the CLI forces
the live oracle; the cache is keyed on the demo file's sha1 + the exact frame budget and refuses
mismatches. This is the grind fix agreed with the owner -- the L2..L5 zoo work re-runs this gate
dozens of times.

## 2026-07-06 - FIX: the cold game played INVISIBLY -- the A90C screen projection is now wired (owner-caught)

The owner ran `play_native` and saw only the starfield -- and was right: the game LOGIC ran (the
unpiloted ship was killed + respawned by real enemies in a headless run) but ZERO sprite pixels
reached the screen. Root cause: the sprite compositor places objects from the records' `+0x0C`
screen-projection cells, which only the A90C/5A92 present scan computes -- the cold path never ran
it (the snapshot path worked because the VM had filled the cells, which also hid the gap from every
state-level probe: they verify RECORDS, not pixels -- a real verification blind spot).

Fix: `sync_screen_projection` in native_walk_frame -- the A90C projection half over the SAME tables/
counts as the ASM (cx=0x24 over 32CA incl. the anchor, cx=0x22 over 8D12), computing `+0x0C` via the
ALREADY-RECOVERED, verify_native_screen_di-proven `project_object_screen_di` (DS:99C8 column table +
the DS:234C cursor; 0xFFFF cull sentinel exactly as 35CC leaves it; `+0x10` untouched -- live VM
records carry 0 there on Tandy). play_native syncs `234C = g.row_source` into the image and runs the
projection after each walk. NEW PIXEL GATE `verify_play_native_render`: renders play_native's exact
frames headlessly and asserts the ship is visible from frame 2 (153 px) and the wave lights the
screen (peak ~1567 px) -- PASS. All state probes still PASS; suite green; lint clean.

## 2026-07-06 - the 8D4F controller family + 0x1C decoded (investigation; ready to implement)

The six controller behaviors (0x13/0x15/0x1C/0x1F/0x7D/0x7E) share ONE body: `8D4F -> far 1F8F:027A`
-- the A482-schedule seek (mode 3, exactly the recovered `step_wave_controller_1f`'s front half),
then an ARRIVAL dispatch on `+0x18`: 0x13 -> 1F8F:0432, 0x15 -> 03E6, **0x1C -> 03A6**, 0x1F -> 0368
(the recovered planet-1 burst), 0x7D -> 0309, 0x7E -> 02CB. So each planet's controller = the SAME
seek + a per-behavior arrival body -- the recovered dataclass/adapter structure extends naturally.

**0x1C's arrival body (1F8F:03A6..03E4), fully decoded:** `A482 += 8` (its schedule entries are
8 bytes: waypoint pair + target pair), ONE `81F4` spawn at the controller position (the recovered
`enemy_spawn_stamp_8209`), the entry's 3rd/4th words -> the child's `+0x34/+0x32` target (+0x20 x
bias), child behavior **0x1D** (`+0x1C = 0x14`) -- or **0x1E with sprite 0x43** when the controller's
y == 0 -- then `A47E++` and the shared 0448 en-route tail. So planet 2's enemies are the 0x1D/0x1E
family (which the L2 frontier's 0x06/0x31/0x4d/0x33 hits likely morph from/spawn). NEXT SLICES: lift
0x1C into the walk (reusing the 0x1F adapter shape), then 0x1D/0x1E, then the rest of the L2 list --
each gated on the L2_full shadow (now runnable, see below).

## 2026-07-06 - the walk shadow now runs SNAPSHOT demos; the WHOLE planet-2 frontier mapped (zero divergence)

Extended `verify_native_walk_demo` to snapshot-based demos (the L2/L3/L4/L6 recordings) -- the
cold-start-only guard was the only blocker; the class table is now read fresh per frame too (the
0B3E level-data init REBUILDS it at level transitions/respawns, so the one-shot cache would go stale
on any demo crossing a level end). **The L2_full playthrough (6561 walk frames incl. the full
LEVEL-END sequence): zero divergence on every natively-walkable frame** -- the L1 zoo already covers
most of planet 2. The complete planet-2 + level-end gap frontier: `0x06`(28) `0x1c`(25, the planet-2
wave controller) `0x31`(24) `0x4d`(16) `0x33`(15) **`0x53`(11, the A3EE outro objects)** `0x44`(1)
`0x45`(1) + the `0x0C` BD17 decay beat (9) + pickup collect kinds 1/3/4 (L2's pickup variety).

**Level-end decodes this pass (ready to implement):** `C591` (the 0xE52 milestone) is a TANDY NO-OP
(mode-1 palette DAC only) -- the native scroll gate can stop declining that row. The `A680` 0xEA0
arm: `A47C=1` + `62AA` (sound 8 + BFC7-sweep-kill every remaining live enemy -- ALL pieces already
native) + FOUR outro objects spawned via 7524 from the `A3EE` table ((0x20,0x18,spr 0x10),
(0x20,0x98,0x13), (0x40,0x28,0x16), (0x40,0x88,0x19); stamp: +0x14=2, +0x16=4, +0x18=0x53,
+0x28=FFFF, sprite also into +0x36). The 9A78 phase-1 handler: an A358-table scripted move (the
9AD1 worker) until [98BE] clears, then `A47C=2` + a 7524 spawn (behavior 0x52, sprite 0xF at
(0x20,...)) -- phase 2 (9A3E, scripted-move counters, partially recovered) and phase 3 (9A16,
recovered decision) follow, ending in A344=1.

## 2026-07-06 - THE LEVEL-END CHAIN MAPPED (VM-traced on the L2_full demo) -- the next campaign phase

Traced the complete real level-end sequence (walk-entry sampled A47C/2350/A344/2356/A978/A47E/A480
across all 6561 walk frames of `demo_play_tandy_L2_full`):
1. `walk 5048`: 2350 reaches **0x0E52** (the `C591` milestone -- still unscoped) with A978=3.
2. `walk 6327`: 2350 = **0x0EA0** (the plane END; 0xEA0 is the tile-plane size), A978 wrapped
   NEGATIVE (0xFFFD -- the trigger counter keeps decrementing past 0), A47E/A480 = 0 (all waves
   cleared -- the scroll only gets here once everything is killed, since waves pause it).
3. `walk 6342`: **A47C 0 -> 1** (the recovered `a47c_script_arms_a680` decision fires at 234E==1;
   the arm also spawns the level-end object via 62AA/7524, si=A3EE -- the outro fly-off).
4. `walk 6353`: A47C 1 -> 2 (the 9A78 phase-1 handler); `walk 6523`: 2 -> 3 (the 9A3E scripted-move
   phase, ~170 frames -- the outro animation); `walk 6561`: **A47C 3 -> 0 with A344 = 1** (the
   phase-3 9A16 handler completed -- its recovered gate needs A97A==0x58/A95A==3/A95C==0x18 -- and
   the scripted transition fired).
5. Same frame: **2356 advanced 2 -> 3 (9734 -> 9744, the level ADVANCE)**, the next level loaded
   (2350=0x9C post-warm-up), **A978 = 0x111** (note: the real post-load seed is 0x111, ONE above the
   first trigger row -- the first pulled row decrements it to 0x110 and the script fires; our cold
   model seeds 0x110 directly, firing at tick 0 instead of tick ~16 -- a benign 16-tick offset worth
   aligning when the level-load goes native).

**The native level-end TODO map** (in order): (a) scope C591 (the 0xE52 milestone); (b) the 62AA
level-end spawn (si=A3EE stamp); (c) the A47C phase handlers 9A78/9A3E/9A16 (9A3E/9A16 partially
recovered as pure decisions); (d) the A344 -> 9734 continuation = the 9744 level advance (recovered)
+ a native next-level load -- play_native can rebuild its walk image + NativeGame with level_index+1
using the EXISTING cold-boot machinery. The A66F native gate currently returns None (declines) at
BOTH milestones, so play_native's scroll would freeze at 0xE52 today -- the milestones must be
composed before a full level is playable to its end.

## 2026-07-06 - the respawn is a LEVEL RESTART (VM-traced); the scroll gate goes live

A live-VM trace of the demo's REAL death->respawn moments (walk-entry sampled: A95A/A47E/A480/A47C/
2350/2358/A97A; then an entry-point path trace) corrected the respawn model landed earlier today:
1. **Death RESTARTS the level.** At the 9AFF fire moment, `4DBF -> 0B3E` (the level-data
   initializer, now disassembled) REWINDS all six script cursors to their heads
   (`SCRIPT_CURSOR_HEADS_0B3E` + `rewind_level_scripts_0b3e` in level_object_script.py), rebuilds
   the tile plane/class table, and the scroll lands back at the level start (2350=0x9C); A47E/A480
   are zeroed (the wave state clears). Score/lives persist. So the respawned level REPLAYS from the
   top -- which is also HOW waves come back after a death (the row-0x110 controller entry re-fires).
2. **The scroll is paused nearly the whole level.** The demo's 2350 sat at 0xB6 for thousands of
   frames: the A66F gate (A47C||A47E||A480 all zero) holds while waves are alive. play_native now
   passes the REAL gate inputs live from the image (was a hardcoded (0,0,0)) -- the world scroll
   pauses during waves and resumes when cleared, the real pacing.
3. The bar refill at respawn is a BLOCKING setup-time loop in the VM (A97A 1 -> 0x58 within one walk
   boundary) -- consistent with modeling its fixed point (0x58) in `apply_respawn_seeds`.

`apply_respawn_seeds` now also rewinds the scripts + clears A47E/A480 (no-ops on the cold path);
play_native's DEATH branch resets the dataclass scroll to the level-start cursor. The respawn probe
(re-asserted: the RESTARTED level replays its 0x20 wave) PASSES: die -> explode -> respawn (lives=2,
level restarts) -> the wave returns -> a natural second death -> respawn (lives=1) -> play
continues. Cold + death probes still PASS; suite green; lint clean.

## 2026-07-06 - MILESTONE: the NATIVE DEATH->RESPAWN CYCLE -- die, explode, respawn, keep playing, VM-free

Composed the 9908/9773 respawn continuation into play_native: on the DEATH exit, instead of stopping
fail-loud, the loop runs the native continuation -- `2358--` lives (with the `[978D]` cheat re-inc),
the BEFF=2 respawn-jingle queue, then `apply_respawn_seeds` (NEW in cold_level_start.py: the SHARED
level-start/respawn re-init both the cold boot and the real 9773 run -- C4DB + the C3A6 pool seed +
C461 + C42F + the post-intro bar; the cold builder now delegates to it, so the seed sequence lives in
ONE place) + the B5A9 formation-cursor reset + the A8C2/20A6 re-inits. Score/planet/scroll persist
(no 96EE, no scroll writes -- the level continues where it was). Lives exhausted (`2358 == FFFF`) ->
the 98EB game-over flow stays fail-loud. Audio (5F43) + presentation (6176/C57C/D305/4DBF) stay host
boundaries.

New probe `verify_play_native_respawn` PASSES: forced death -> explosion -> respawn (lives=2, ship at
0xC0/0x58, A95A=3, bar full) -> 463 frames of continued play -> a NATURAL death (the level's own
content killed the unpiloted ship -- exercising the same path unforced) -> respawn (lives=1) -> play
continues. TWO probe-expectation findings recorded on the way (both REAL behavior, not bugs): planet
1's script has its ONLY 0x1F wave-controller entry at row 0x110, so post-respawn content comes from
LATER script rows' other behavior types (0x27/0x11/0x30/0x83...), not fresh 0x20 formations; and the
respawned ship has no grace period in our post-intro model (the real intro script IS the grace).
`verify_play_native_cold` + `verify_play_native_death` still PASS; suite green; lint clean.

**play_native is now: cold boot -> title -> live level -> combat both ways -> death -> respawn ->
... -> game over (fail-loud).** The remaining L1 in-level items: the boss row (62AA at 0xEA0), the
level-end 9734 continuation, HUD wiring.

## 2026-07-06 - play_native: the NATIVE DEATH TAIL is wired -- explosion anim + DEATH exit, VM-free

Composed the 9B61/9AFF death flow into `play_native._advance` (the first half of the death->respawn
plan): when the anchor state is absent (`death_tail_reached_9aff`, live image reads), the player/
scroll/fan-out step is SKIPPED (the ship + scroll freeze, matching 9B61's branch) and the recovered
`step_death_tail_9aff` runs instead -- the anchor's +08 cell (which IS `DS:2384`: 0x237C+8, so the
9EA3 chain's `[2384]=3` death-pose write seeds the explosion counter at 3) counts the explosion
animation sprites 3..0xF on 2326==3 phases, the anchor deactivates at 0x0F, and the already-live
exit detector fires DEATH/GAME_OVER. The object WALK keeps running throughout (the wave stays
live). The 4DBF death-moment call stays a declared host boundary (the loop stops fail-loud at the
exit before any continuation). `sync_player_anchor` is skipped while dying (the anchor is
image-owned; syncing would clobber the counter with a stale sprite).

TWO supporting fixes: (1) **`build_cold_level_start_image` now seeds the health BAR at its
post-intro fixed point** (`A97A=0x58`, `A97C=1`, written AFTER C4DB which zeroes them) -- an empty
bar IS the 9B61 death condition, so the old unseeded 0 would have started the cold level dying the
moment the counter bank cycles (the real intro fills the bar via 77C5 before handing over; same
modeling as `_COLD_ROW_BASE`). (2) The now-dead `_SeededStart` exit-guard fields (a47c/a95a/a97a/
v2326) removed -- the detector reads the image since fb81bc1.

New probe `verify_play_native_death` PASSES: 12 phase-3-clocked +08 advances (sprites 3..0xF
exactly), ship frozen, wave still changing, DEATH exit at 0x0F, anchor deactivated. The cold probe
(`verify_play_native_cold`) still PASSES (no spurious dying at start). Suite green; lint clean.
**Remaining for the full cycle: the 9908/9773 respawn composition** (all pieces scoped, see the
previous entry) -- then a death continues into a respawn instead of stopping fail-loud.

## 2026-07-06 - play_native's gameplay-exit guards read LIVE from the walk image; the death->respawn chain decoded

Wired `detect_gameplay_transition`'s inputs (A47C/A95A/A97A/2326) to LIVE walk-image reads in
`play_native._advance` (was seeded-static) -- ADR-1: the image is the state. A95A is now genuinely
walk-owned (the 9E69/9EA3 chains write it natively), so a real in-game death reaches "anchor state
absent" for real; the other cells take effect the moment their stages go native, no further wiring.
Cold values verified identical to the old seeds (A95A=3, A47C=0, 2326=0, A97A=0 -- same knife-edge
as before on A97A, behavior unchanged).

**The full death->respawn chain is now DECODED (investigation, no code)** -- the next campaign-scale
item, recorded here for the next session:
1. Death detected (9B61: `A95A==FFFF or A97A==0` -> jmp 9AFF) SKIPS player-move/scroll/fanout but the
   OBJECT WALK STILL RUNS (proven: the demo shadow stayed byte-exact through the demo's 5 real death
   beats). The 9AFF tail is ALREADY PURE (`step_death_tail_9aff`): phase 2326==3 -> anchor +08++ ->
   at 0x0F: anchor deactivates, `call 4DBF` (UNKNOWN -- scope it), A346=1 (+ A342 when A97A==0).
2. The 97B2 A346 transition -> **9908** (the death continuation): `call C4DB` (RECOVERED:
   apply_new_game_setup_c4db) + `dec [2358]` lives (`[978D]` = infinite-lives cheat) + a BEFE sound
   drain + BEFF=2 + `jmp 9773`.
3. **9773** (the respawn re-entry into the setup tail): `[2358]==FFFF -> jmp 98EB` (game-over flow);
   else C3A6 (recovered pool seed) -> 77C5 -> 99BF -> 6176 (host HUD) -> 9BE2 -> A940 (recovered) ->
   `[20A6]=20A8` -> C57C -> B5A9 -> `[A8C2]=0` -> 5F43 -> (`[2350]==0x9C` -> D305) -> 97B2.

**ALL SEVEN 9773/9AFF unknowns SCOPED (2026-07-06, disasm-verified) -- the respawn is compose-ready:**
* **77C5** -- the A97A health-BAR refill tick: gated `[A97C]==1` (a "refilling" flag) AND `[2384]<3`;
  `A97A++` toward 0x58 (so A97A is the BAR level; "A97A==0" in the death detector = empty bar) + a
  77F6 draw beat + the mode-1-only 511F pair (Tandy-unreachable, same as 9EC2). Small pure + host.
* **99BF** -- the COORDINATE-RING init (the long-standing "coordinate rings" Bucket-C gap!): fill the
  0x30-pair ring at A27A with (anchor_x+8, anchor_y+9), then seed the four ring pointers
  A33A=A27A / A33C=A2FE / A33E=A2BE / A340=A27E. Pure seed, trivial.
* **9BE2** = 9CD9 + A031 + (BDAC==0 AND 2350>0xB6 -> 9FAF): **9CD9** writes (anchor_x+8, anchor_y+8)
  into the ring slot at [A33A] (the ring TICK); **A031** copies the delayed ring entries at
  [A33C]/[A33E] into the records pointed by A962/A964 -- THE COMPANION-FOLLOW mechanism (the
  companion trails the player via the ring delay). Both pure + tiny. **9FAF** (boss-region only)
  still unscoped.
* **C57C** -- a TANDY NO-OP: palette DAC writes only for cs:[95BC] modes 0 (jmp C565) / 1; mode 2
  returns untouched. Host/presentation.
* **B5A9** -- 3 word writes: A8D0=A8D2 (the formation-schedule cursor reset, matching
  enemy_formation_adapter's note), A8C8=0, A8CC=0. Trivial pure.
* **5F43** -- the level-MUSIC start: al = 4 (row 0x9C level start) / 5 (row 0xEA0 boss) / the
  DS:231E[planet] table, then jmp CB1C (the sound/music dispatch -- AUDIO, host/deferred).
* **4DBF** (the 9AFF death-moment call) -- planet-keyed (a C601-table pointer), a 3x 4DAF loop, then
  0B3E with A978 saved/restored around it -- shape of the death jingle/text; sub-unknowns 4DAF/0B3E.
  Only fires ONCE at anchor-deactivate; can stay a declared host boundary initially.
* **D305** (row-0x9C only) -- unscoped; likely the level-intro presentation.

So the COMPOSE plan for native death->respawn in play_native: on `death_tail_reached` (live A95A/A97A
reads -- already wired), skip player/scroll/fanout, run `step_death_tail_9aff` (pure, exists) with
the +08 counter (the explosion anim the renderer already draws), still run the walk; on fire: C4DB
(recovered) + `2358--` + C3A6 (recovered) + the 99BF ring seed + B5A9/A8C2/20A6 writes + A940
(recovered) + respawn C461/C42F (recovered) -- audio (5F43) and presentation (6176/C57C/D305/4DBF)
declared host boundaries. The remaining true unknowns: 9FAF (boss-region), 4DAF/0B3E, D305, and
where A97C gets SET (the refill trigger).

## 2026-07-06 - **MILESTONE: THE ENTIRE DEMO WALK IS NATIVE -- 8294/8294, zero divergence, ZERO GAPS**

Recovered the 9EA3 player-death chain (the LAST gap in the demo): on the A95A life underflow in
`_player_hit_9e69` -- `A95C = 0`; if the `DS:[9791]` byte is 1 (an invulnerability/refill flag),
A95A/A95C refill to 3/0x18 and return (no beat); else `DS:2384 = 3` (the ship-death pose every pose
gate tests) + sound 0x19, then the 9EC2 energy beat (61DC; the 511F pair stays mode-1-gated,
Tandy-unreachable). `_shot_hit_9e19` funnels its exhaustion into the same 9E69, so one fix covers
both damage beats. The non-death path now also routes through `_hud_energy_beat_9ec2` (fidelity +
the fail-loud mode-1 guard).

**`verify_native_walk_demo`: 8294/8294 walk frames, diverged=0, NO recovery gaps -- the first run in
project history where every frame of the owner's real played demo is natively walkable and
byte-exact.** The A9D3..AA25 object behavior walk -- every enemy, spawner, scenery, shot, child,
death, morph, respawn, and pickup the demo exercises -- is now a complete native system. Suite
green; audits + manifest pass. The remaining 5 "gap frames" from the previous run are all closed:
the demo's 5 player-death beats now run the real death chain (2384=3 + sound) natively.

## 2026-07-06 - the type-5 pickup COLLECT recovered -- ONLY player-death remains in the demo

Recovered the AAD3 collect chain (`_pickup_collect_aad3`): the pose gate (`[2384]>=3` -> no collect),
sound 7, score +0x20 (the recovered 5F0D), the `+0x26`-keyed AB00 kind dispatch -- kind 2 (`9D67`,
both demo collections' kind) = sound 0x1C + the A95A/A95C HEAL (`pickup_heal_9d67` in frame_loop.py:
A95A steps toward 3 one-per-collect, THEN A95C fills to 0x18 -- the same cells the 9E19/9E69 damage
beats decrement and the 9723 init seeds) + ONE 9EC2 HUD-energy beat -- then the BD17 deactivate of
the pickup (the AB0C tail). **Key finding that made this turn-key**: 9EC2's 511F calls are gated on
`cs:[95BC]==1` (mode-1 dual-page video); Tandy is mode 2 (confirmed on both the cold bundle and the
live snapshot), so 511F is UNREACHABLE on this port's path -- 9EC2 reduces to the already-recovered
61DC redraw (a fail-loud guard raises if a mode-1 image ever reaches it). Other pickup kinds
(0/1/3/4) stay fail-loud gaps (not demo-witnessed).

**Demo shadow: PASS, 0 divergence, 8294/8294. The gap frontier is 5 frames -- ONLY the player-death
9EA3 chain remains.** Suite green; audits + manifest pass.

## 2026-07-06 - MILESTONE: the 0x01 latch-9 morph + behavior 0x26 RECOVERED -- the L1 zoo is essentially DONE

Closed the 0x01-latch9/0x26 pair (51 of the 58 remaining gap frames; they close each other). The
latch-9 MORPH (`1010:BE5A/BE60`, inside the dying handler): when a key-1 dying record's latch hits 9,
its previous logic id picks the morph (`0x24` -> dir 6/sprite 0x97/y-=8; `0x25` -> dir 2/sprite
0x91/y+=8; else BD17), stamps behavior 0x26, saves +0x32=new_y / +0x34=x, and RETURNS -- skipping
BC45 that frame (`_step_dying_01` now returns a run-postmove bool; the BD17 tails also skip, since
BD17's paths `ret`). **0x26** (`1010:8302`): the morph target's float-away/respawn loop -- AFD8-step
in the morphed direction (with the wired BDD0 predicate) until BLOCKED or y>=0xC0, then a sprite ramp
(+1, sound 0x1E) to the finished sprite (0x98/0x92), where it waits for `DS:2326==3` to reset y from
+0x32 and drop the sprite back. Also closed the key-2 latch-0xC BD17 deactivate (same slice; it was
in the same gap message).

**Demo shadow: PASS, 0 divergence, 8294/8294. The gap frontier is 7 frames**: player-death 9EA3 (5) +
pickup-collect (2) -- both non-zoo (frame-loop composition work). Native actor set: **23 behaviors**.
Free-run 200/0; suite green; audits + manifest pass.

## 2026-07-06 - MILESTONE: the 0x8C/0x8B ground crawler RECOVERED -- the L1 scenery cluster is DONE

With BDD0 wired, re-added the 0x8C/0x8B ground crawler (the BB80/BB88 pair over the shared BB8E body
+ the BBED terrain-follow: 5073/505B pre-probe of the tile ahead, AFD8 step with the real
`_bdd0_contact_at` predicate, sprite `0x61 + 4*A952 + anim(233C, only-when-moved) + dir`, and the
BBB5 shot gate firing a 7476 child with sprite/X/Y overrides on three DS:2330 phases). The old
frame-3072 divergence is GONE -- BDD0 was indeed the root cause. Landing it unmasked ONE new 1-byte
divergence (frame 3535, `DS:2308` vm=1/nat=2): B2CD (the 0x12 waypoint follower) writes its seek-mode
GLOBAL (`[2308]=1`, overwritten to 2 iff planet==0 or BDAC==1) which the pure fn computed internally
but never exposed -- fixed by adding `seek_mode_2308` to `WaypointFollowerStep` and persisting it in
the adapter (the previous crawler gap frames had masked this omission).

**Demo shadow: PASS, zero divergence across all 8294 walk frames.** The gap frontier COLLAPSED from
1449 frames to **58**: 50x `0x01 latch-9` (needs 0x26), 5x player-death (9EA3), 2x pickup-collect,
1x `0x26` (newly unmasked -- the latch-9 morph target, now reachable AND its AFD8 dependency [the
BDD0 predicate] is already wired). Native actor set: **21 behaviors**. Suite green; audits pass.
Next: 0x26 + the 0x01 latch-9 morph (they close each other; 51 of the remaining 58 gap frames).

## 2026-07-06 - BDD0 contact predicate WIRED into AFD8; behavior 0x89 RECOVERED (the shared blocker, resolved)

Resolved the shared AFD8-blocked mismatch that felled both the 0x8c/0x8b crawler and 0x89 (both had
`contact_probe_afd8` returning not-blocked where the VM blocks). Root cause was the caller-owned BDD0
contact predicate, passed as `lambda: False` by every AFD8 caller. **BDD0 was ALREADY RECOVERED** as
`collision.player_hazard_scan_hit` (+ `is_player_hazard_scan_candidate`, the BDE3 candidate gate) --
only the WIRING was missing (a check-for-an-existing-mechanism win). Changed the AFD8/B022 `contact_at`
callback from no-arg to `contact_at(mirror_dx_x, mirror_dx_y)` so it receives the step's A438/A436
probe deltas; added `_bdd0_contact_at(mem, rec)` in behavior_walk (applies the BDD0 `+0x0A==1` guard,
adds the deltas to the object's own X/Y, scans the 0x23 effect records via the recovered predicate),
and threaded it through `_bb03_bounce`. Updated all `contact_at` call sites (the oracle + unit tests)
to the 2-arg form.

**0x89 re-added and now PASSES the full demo shadow (0 divergence across all 8294 walk frames)** --
proof the wired BDD0 is byte-exact. AFD8's own driven-oracle gate (verify_native_contact_step: 448
step cases + 192 full-AFD8 cases, 0 fails) + the contact-step unit tests stay green; free-run 200/0.
Native actor set now 19 behaviors. 0x89 (was 158 demo hits) off the frontier. **The 0x8c/0x8b crawler
is now re-attemptable with the same `_bdd0_contact_at` predicate** -- the next slice.

## 2026-07-06 - behavior 0x28 RECOVERED (the largest truly-open L1 gap); 0x8c/0x8b crawler attempted+reverted

Recovered **0x28** (`step_spawner_28`, alias-group with 0x2A -- handler 1010:8676 + its 8654 helper),
the largest remaining truly-open enemy gap (488 demo hits). It's an animated spawner: sprite ramps
off `DS:96AA[+0x06 counter] + 0x1C` (counter advances only when `DS:2332==0`, wraps mod 0x18); once
per cycle -- when `DS:A47E==0` (no active enemies) AND the counter hits 7 -- it fires a child via the
81F4 worker, which is `_alloc(7524)` + the ALREADY-RECOVERED `enemy_spawn_stamp_8209` (stamps the
child behavior `0x14` by default), then 8676 OVERRIDES the child per-planet (planet 1 -> behavior
`0x29`, sprite `0xA1`, already recovered). The enemies_l1 note claimed 0x28 needed a new `0x14` child
behavior -- WRONG: on L1 the child is overridden to 0x29, so the whole slice reused recovered pieces;
the only new pure logic was the 8654 sprite anim. **Byte-exact across all 8294 demo walk frames**
(demo shadow PASS, 0 divergence); free-run 200/0; suite green. Native actor set is now 18 behaviors.

Also this pass: **attempted 0x8C/0x8B AND 0x89, both reverted -- and CONVERGED on the shared root
cause.** 0x8c/0x8b (the BB80/BB88 ground-crawler) diverged at demo frame 3072 (`A430` blocked-flag
vm=1/nat=0, X 1px behind); 0x89 (a trivial clone of the recovered 0x19 -- sprite ramp + BAE1 emit +
the shared BB03 bounce, ALL reused verified pieces) diverged at frame 4535 with the IDENTICAL
signature (`A430` vm=1/nat=0, Y off by 1, BB03 phase wrong). Two independent behaviors, same failure:
`contact_probe_afd8` returns blocked=False where the VM blocks, on positions 0x19/0x1A never reach.
Root cause is the **missing BDD0 contact predicate** (AFD8's own island contract flags it caller-owned;
every caller passes `lambda: False`). **Fully decoded 1010:BDD0** (an effect-pool object-overlap scan;
full pseudocode + wiring plan in loop_blockers.md 2026-07-06) -- recovering it + threading it through
AFD8 is the shared unblock for 0x8c/0x8b/0x89 (~1449 gap frames) AND the 0x26/latch-9 morph. That is a
FOCUSED slice on its own (it touches the verified contact_step_b022 interface); flagged as the clear
next high-leverage target, not attempted this pass. Both attempts fully reverted; tree green.

## 2026-07-06 - MILESTONE: scene.md DONE -- play_native's cold path wires the level-object-script + full behaviour walk

Finished the scene.md turn-key wiring (steps c/d/e): `play_native.py`'s cold path (no `--snapshot`)
now builds the object-walk DGROUP image unconditionally via a new `build_cold_level_start_image`
(`overkill/recovered/adapters/cold_level_start.py` -- the raw seeded-write half split out of
`build_cold_level_start`, which now just projects it; both stay byte-identical, locked by a new test),
syncs `rows_to_milestone` into the image each tick, and runs `run_level_object_script_4a65` before
`advance_object_frame` -- so the level's spawn script actually fires from cold data and the whole
behaviour walk drives the resulting enemies. New probe `overkill/probes/verify_play_native_cold.py`
mirrors play_native's exact wiring headlessly (no pygame) and **PASSES**: peak enemies=20, a tracked
enemy moves, 0 gap-frames, at 200 frames on planet 1 (`--level 0`).

**One real, easy-to-miss bug found and fixed via this probe** (not by trial and error -- by comparing
against the OLD `verify_cold_populate`'s working timeline once my probe showed 0 enemies where it
should've shown a live wave): the level-object-script trigger check (`1010:A83C`) runs in the
DRAW/PRESENT half of the original loop ("present last tick's state, then advance"), so it must compare
against `rows_to_milestone` as it stood BEFORE this tick's scroll step, not after. Cold `origin_x=0`
pulls a row (decrementing `rows_to_milestone`) on the very FIRST scroll tick, so syncing the
post-step value silently skipped the exact entry the empirically-confirmed cold seed (`0x110`) was
built to match -- zero spawns, no exception, nothing loud. Fixed in `_advance()` by capturing
`rows_to_milestone` BEFORE calling `g.step(...)` and syncing that pre-step value into the image.

A second smaller fix inside the new probe itself (not a play_native bug): the census only scanned
`object_pool`, but wave controllers (behavior 0x1F) and some early enemies land in `special_pool`/
`effect_pool` -- scanning all three pools (matching how `_render_frame` already does it) revealed the
wave was live the whole time.

**Known, pre-existing, non-blocking limits**: past ~frame 208-248 the ALREADY-DOCUMENTED `0x01 latch-9`
gap surfaces (same one the demo tally lists, 43 hits -- enemies_l1's open item, not new). Planet 2
(`--level 1`) hits behavior `0x1c` (no native handler) immediately -- a DIFFERENT wave-controller
family than planet 1/3's (CLAUDE.md: "the 'formation wave' recovery is planet 3's family only");
cold-populate is proven for planet 1 only, other planets remain open zoo work.

Suite green (see header), lint clean, both layer audits pass, demo shadow still 8294/8294 zero
divergence (this slice touched only play_native.py + a probe + cold_level_start.py's own split, no
behaviour-walk semantics changed). **scene.md's campaign done-condition is now met.**

## 2026-07-06 - MILESTONE: scenery 0x1A/0x19 native, `verify_cold_populate` PASSES, demo stays 0-divergence

Recovered the SHARED `BB03` vertical-bounce tail (over the already-recovered, verified
`contact_probe_afd8`/AFD8 -- 21-caller shared worker, never wired into a live adapter before this)
plus **0x1A** (sprite ramp + BB03) and **0x19** (a different sprite ramp + a periodic C237 emit via
the `1010:BAE1` helper, forcing direction=4 for the spawned child then restoring it) in a new module,
`overkill/recovered/systems/scenery_behaviors.py` (kept separate from `enemy_behaviors.py` -- these
are scene.md's scope, not enemies_l1's). Together the single largest chunk of the L1 frontier
(576+288 = 864 hits). **`verify_cold_populate` now PASSES** (peak enemies=15, a tracked enemy moves,
0 gap-frames, VM-free) -- one of scene.md's TWO done-condition clauses; the demo shadow holds at
**8294/8294 zero divergence**.

Three real bugs surfaced and fixed while landing this (the demo-shadow discipline catching each one
before it could compound):
1. **Caught a wrong AFD8 flag reading BEFORE writing code**, not by trial and error: the recovered
   island's own contract phrasing ("blocked verdict = ZF(cmp A430,0)") is ambiguous about WHICH ZF
   state means blocked; reading the EXISTING verified adapter's plain-English comment
   (`contact_step_dispatch_adapter.py`: "DS:A430 = 1 on block") resolved it correctly on the first
   attempt -- exactly the "verify against existing evidence, don't guess" discipline this session
   has repeatedly needed.
2. **The adapter never wrote AFD8's own observable DGROUP side effects** (`A430` the blocked flag,
   `A432`/`A434` the pre-step snapshot, `A436`/`A438` the post-step mirror) -- these are REAL ASM
   writes every AFD8 call makes, not just internal working state, so omitting them causes a byte
   divergence that, left in place across many frames, would slowly compound (caught immediately via
   the full-DGROUP demo shadow, before it accumulated).
3. **`with_drift=False` was wrong for 0x1A/0x19** -- their disassembled exits are literally
   `jmp BC45` (not `BC4B`), so the shared level-scroll drift (`+= DS:A278`) DOES apply, same as every
   other BC45-tail actor; this produced a slow, GROWING 1px/frame X divergence (VM always exactly 1px
   ahead of native, compounding every frame) that made the root cause obvious once traced.
4. **The C237 sound-selection table (`1010:C2CE`) only had 8 of its 16 real entries** -- every prior
   C237 caller's `parent_beh & 0xF` happened to land in 0-7; 0x19 is the first caller landing at
   index 9, an outright `IndexError` (not a silent divergence) that forced re-dumping the FULL table.

Suite: 1222 passed / 23 skipped; both layer audits pass. Native actor set now 17 behaviors + the
C237 spawn worker + the BB03 bounce. Remaining L1 gaps (demo tally): 0x8c(769, scenery, unmasked
further by this session's fixes) 0x28(488, needs 81F4+0x14) 0x8b(363, scenery) 0x89(46) +
0x01-latch9/0x26(43) + player-death(5) + pickup-collect(2).

## 2026-07-06 - MILESTONE: ZERO divergence across the ENTIRE 8294-frame demo (two deep bugs found+fixed)

Recovering **0x24** (`_step_spawn_child_sprite`, generalised from `_step_spawn_25` -- byte-identical
to 0x25 apart from the sprite constant) and **0x29** (`step_ramp_steer_29` + the new
`retarget_delta_toward_anchor_74e2` primitive: sprite ramp -> 74E2 retarget -> the recovered 5E42
steer -> a signed Y-bounds BFC7 death) unmasked TWO genuine, pre-existing bugs via the demo shadow --
fixing both took the demo from 3 long-standing unexplained divergences (614/6037/6897) to
**RESULT: PASS -- zero divergence on every natively-walkable frame (8294/8294)**.

**Bug 1 -- `GAMEPLAY_POOL_WRAP` was mistranscribed.** `behavior_walk.py` defined
`GAMEPLAY_POOL_WRAP = 0x2CA4`, but `(0x2CA4 - GAMEPLAY_POOL_BASE) / 0x38 = 5.857` -- NOT slot-aligned.
`_alloc`'s wrap check (`if cur == wrap: cur = base`) can therefore never fire via exact equality, so
the C237/7573 allocator's cursor can drift PAST the intended pool into adjacent memory whenever a
scan needs more than ~5 tries to find an inactive slot. The canonical, CORRECTLY slot-aligned
sentinel already existed: `views/object_slots.py`'s `GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL =
GAMEPLAY_OBJECT_TABLE_BASE + GAMEPLAY_OBJECT_TABLE_COUNT * OBJECT_SLOT_STRIDE` (`0x32CC`). Fixed by
importing and reusing it instead of a second, drifted copy -- exactly the "check for an existing
mechanism before building one" rule this repo keeps re-learning. This alone resolved the frame-614/
6037/6897 divergences that had been open since the demo frontier was first established.

**Bug 2 -- `x_word == 0xFFFF` is an AMBIGUOUS proxy for "B250 contact happened."** The real ASM
branches DETERMINISTICALLY at detection time (contact -> ADC9 stamps X=FFFFh, then the 9E19 fan-out;
no-contact -> AD5A drifts X by `+DS:A278`) -- but ordinary AD5A drift can coincidentally WRAP X to
the exact same 0xFFFF sentinel with NO contact at all (witnessed: a C237-spawned child stamped at an
off-screen parent's position, whose own 2px-step-then-drift arithmetic happened to land exactly on
0xFFFF). The adapters (`_step_shot_0b`, `_step_child_04`) inferred "was there contact" AFTER THE
FACT by checking `x_word == 0xFFFF` -- ambiguous, and wrong in this case: native ran the 9E19 damage
beat on a frame the real VM's C237 throttle never even spawned a child for. Fixed by exposing the
ACTUAL `contact: bool` the B250 selector computes as an explicit field on `Aed8SlotUpdate`/
`B24dSlotUpdate`/`Af60SlotUpdate` (the 3 already-shared "EFAE per-object update" dataclasses); the
adapters now gate the 9E19 fan-out on `u.contact`, never re-derived from position.

**Forensic method** (documented since it's reusable): dumped the FULL effect+gameplay pool state at
walk-entry and post-walk on both VM and native to confirm every RECORD matched exactly (ruling out a
position bug) while 4 global cells (23A0/A95C/BEFF/236A -- the 9E19 signature) still diverged; traced
the VM's OWN C237 call sequence for that exact frame (showing all 3 calls throttled, no real spawn);
then instrumented the NATIVE walk's dispatch loop directly to catch a phantom `beh=4` record being
walked from a gameplay slot that both pre- and post-walk snapshots showed inactive -- proving the
child was a genuine same-frame spawn-then-death transient, not spurious record corruption.

Suite: 1222 passed / 23 skipped. Native actor set: 0x1F, 0x20, 0x0B, 0x02, 0x04, 0x11, 0x12, 0x24,
0x25, 0x27, 0x29, 0x2f, 0x30, 0x90, 0x91 (+ the C237 spawn worker) = 15 behaviors. Remaining L1
frontier (demo tally, by freq): 0x1a(576, scenery) 0x8c(562, scenery) 0x8b(363, scenery)
0x28(328, needs the new 81F4 worker + behavior 0x14) 0x19(288, scenery) 0x89(46) + player-death/
pickup-collect/dying-latch9.

## 2026-07-05 - Behaviors 0x11/0x12 native (waypoint follower) UNMASKS a real field-offset bug fixed
   across the whole AD60 family (aed8/b24d/af60/ae09/ae2c/ae7d) -- retroactively affects 0x02/0x0B too

Recovered `step_waypoint_follower_11_12` (systems/enemy_behaviors.py): 0x11 is a one-shot morph
(seed the `+0x36` cursor to the cold `A43C` table, retag the record 0x12) that falls straight into
0x12's body -- the first STATEFUL actor (a per-record path cursor) and the first with an internal
RETRY LOOP (advance the cursor + retry the 5DB2 seek until one succeeds). Also fixed a missed
DS:2304/2306 global write (B2D4/B2D8 -- the seek target globals every retry re-stamps; only the
FINAL survives to the frame boundary) caught by the demo shadow on the first pass.

**Recovering 0x11/0x12 unmasked a genuine, pre-existing field-offset bug** in the ALREADY-VERIFIED
`object_bounds_tile_decision_ad60` family: the real AD60 ASM gates its tile-probe branch on
`cmp ss:[bp+22],0002h` -- **hazard_class (+0x16)**, not draw_layer/gate_or_layer (+0x0A) -- but
EVERY wired adapter call site (`_step_shot_02` for 0x02, `_step_shot_0b` for 0x0B, `_step_child_04`
for 0x04) passed `rec+0x0A`. This never showed up before because 0x0B's logic_id (0x0B) fails the
tile-probe id-membership check regardless of which field gates it (same "skip" outcome, different
reason), and 0x02/0x04 never happened to reach a frame where the REAL tile probe would fire and
differ observably -- until a C237-spawned 0x04 child (hazard_class=2, logic_id=4, BOTH match the
tile-probe family) crossed a class-1 tile at demo frame 3767 and genuinely deactivated via `1010:
BD1C`, while native (gated on the wrong field) never ran the probe at all. Traced with a targeted
CS:IP write-trap (not guessed) before touching any code.

Fixed at the SHARED function level (not papered over per-caller): renamed the misleading
`draw_layer` parameter to `hazard_class` across all 6 `object_bounds_tile_decision_ad60`-family
functions (2 of the 6 -- `ae09`/`ae2c`/`ae7d` -- aren't wired into the walk yet but share the same
bug, fixed for when they are); fixed the 3 live adapter call sites to read `rec+0x16`; routed their
"deactivate" outcome through the existing `_bd17_deactivate` helper (previously they wrote
`active=0` directly, bypassing BD17's hazard_class-keyed extra effects -- a no-op difference for
hazard_class=2 records specifically, but not future-proof). Also fixed the SAME bug's
already-existing but misleadingly-keyworded oracle probe (`verify_native_object_update.py`) and a
downstream import in the `gameplay/object_bounds.py` HOOK layer (which was independently correct via
the `OFF_DRAW_LAYER = OFF_HAZARD_CLASS` alias -- only the constant name needed to follow).

Verified: the demo shadow's 3767/5345 divergences (both `2Bxx`-pool active-word mismatches) are
GONE; the full 8294-frame demo run is back to exactly the 3 known pre-existing pool-spawn
divergences (614/6037/6897, already logged, unrelated); the 200/0 free-run shadow holds; 76 targeted
unit tests + full suite green. This is exactly the kind of bug the demo-shadow discipline exists to
surface: a static disassembly read alone would not have caught it (the bug is silent whenever the
wrong-vs-right field values coincide on outcome), only comparing REAL gameplay frames did.

## 2026-07-05 - Behavior 0x04 native: the C237 spawn chain is CLOSED (+ two real bugs caught and fixed)

`object_update_af60` (systems/objects.py) + `_step_child_04` (the walk): the C237-spawned child's own
movement (double 2px step, fixed direction) + the shared B250 contact / AD5A-ADC9->AD60 tail (the
third EFAE-family member alongside AED8/B24D) + the single 9E19 contact beat. Self-contained (no
BC45), matching 0x02/0x0B's shape. **0x25/0x30/0x90/0x91 now produce ZERO residual gaps** -- the
spawn chain is fully native.

Two REAL bugs surfaced and fixed while landing this (both by the demo shadow, not guesswork):
1. **DS:A956 is a BYTE, not a word** -- the ASM's `inc`/`and` at C245/C253 are FE 06 / 80 26 (byte
   opcodes). My C237 throttle used word rw/ww, clobbering the adjacent DS:A957. Fixed to byte ops.
2. **DS:215A is promiscuous scratch, not object-state** -- traced (`scratchpad/trace_215a.py`) to
   400+ writes from dozens of unrelated IRQ/sound/menu addresses within a few thousand boundaries;
   none from object-behavior code. Added to EXCLUDED_CELLS in both shadow probes (same class as the
   existing 230A/230C steer-scratch exclusion) -- a methodology fact (async writes between the
   shadow's snapshot and AA25 can never be reproduced by re-running only the object walk), not a
   correctness weakening.

Verified: 5397 walk frames, only the pre-existing frame-614 divergence remains; 200/0 free-run holds;
suite 1222 passed / 23 skipped. Native actor set: 0x1F, 0x20, 0x0B, 0x02, 0x04, 0x25, 0x27, 0x2f,
0x30, 0x90, 0x91 (+ C237) = 11 behaviors. Frontier now (demo, by freq): 0x1a(576)/0x8c(510, scenery)
0x12(507) 0x29(310) 0x19(288, scenery) 0x28(201) 0x24(80) 0x8b(16) + player-death/pickup/latch9.

## 2026-07-05 - Spawner actors 0x30 + 0x90 + 0x91 native (the C237 primitive pays off)

With `spawn(C237)` recovered, the C237-consumer actors fell quickly: 0x30 (8851: animate [96D2]@233C
+ gated C237 spawn + sound 0x0E), then 0x90/0x91 (8282/8291: animate [95EA]@2330 + the 82CA "phase
table" that spawns a C237 child at X±4 on [232C]==0x1F -- one shared fn, base 0x88/0x8B). Each: target
demo gap -> 0, NO new divergence (still only frame-614), 200/0 free-run held. Native actor set now:
0x1F, 0x20, 0x0B, 0x02, 0x25, 0x27, 0x2f, 0x30, 0x90, 0x91 (+ the C237 worker) = 10 behaviors.

**IMMEDIATE next: behavior 0x04** (AEBF->AF60) -- now UNMASKED (24+ demo gaps) since the spawners drop
C237 children (which ARE behaviour 0x04). AF60 = the 2px-in-direction step doubled (call/ret trick) +
the recovered B250/AD60 tail; an AED8 variant w/o the substate decrement. Recovering it closes the
spawn chain. Then the scenery set (0x19/0x1a/0x8c/0x8b -> scene.md), 0x29 (needs 74E2), 0x12, plus
player-death + pickup. Frontier (demo, by freq after this turn): 0x8c/0x19/0x1a(scenery) 0x24(80)
0x12(68) 0x04(24) ...

## 2026-07-05 - C237 spawn worker + 0x25 native (the big unlock landed, first-try clean)

The empirical trace paid off: C237 (child_spawn_throttle/seed/sound_c237) + behavior 0x25 verified
first-try -- 0x25 demo gap 208 -> 0, NO new divergence, 200/0 free-run held. The stale-bx write
(DS:[0x52]=0x1A on throttled frames) modelled from the trace was correct. The spawned 0x04 child did
NOT flood (stays masked behind commoner gaps); sibling caller 0x24 newly unmasked. **The `spawn(C237)`
primitive is now recovered**, so the remaining C237 consumers are easy follow-ons: 0x30 (8851: an
`animate`-from-[96D2]-table + C237 spawn + sound 0x0E; on L1 the planet-5 branch is skipped) then
0x90/0x91 (8282/8291: animate from [95EA]@2330 + a 82CA anim-index jump table into C237). Actors
native so far: 0x1F, 0x20, 0x0B, 0x02, 0x27, 0x2f, 0x25 (+ C237). Frontier now (demo, by freq):
0x91(390) 0x19/0x1a/0x8c/0x8b(scenery) 0x90(160) 0x24(80) 0x12(15) 0x11(1) + player-death + pickup.

## 2026-07-05 - ACTOR ZOO recovery begins: 0x27 + 0x2f native, and the actor-model design target

The demo frontier is now being drained one behavior per slice (the proven loop: add handler ->
`verify_native_walk_demo` gap for it drops to 0, NO new divergence, the 200/0 free-run shadow held ->
commit). Landed: **0x27** (835D, sprite scroller) and **0x2f** (8820, patrol-bounce: B729 seek +
target-y bounce when blocked; `_apply_seek` now returns the seek's blocked flag). Recovering each
UNMASKS downstream behaviors (a gap aborts the whole frame), so the gap set shifts as it peels.

New crystallization target: **[`actor_model.md`](actor_model.md)** -- OVERKILL has no behaviour
bytecode-VM, but a real implicit model (data-driven 4A65 cue sheet + schedules; EFC4 dispatch table;
a CLOSED primitive vocabulary the hand-written handlers compose over the 0x38 record). Plan: recover
handlers against the demo, TAG each with its primitive decomposition (actor_model.md Sec 4), let the
step-language schema emerge, then a shadow-gated interpreter -> editor-ready. Each recovered behavior
is now tagged there.

Highest-value next unlock: **C237** (the child-spawn shared worker) -- gates 0x25/0x90/0x91 (~646
demo hits). **Now fully decoded AND empirically demo-traced** -- the turn-key spec + caller reactions
live in [`campaigns/enemies_l1.md`](campaigns/enemies_l1.md#c237-child-spawn). Trace (`trace_c237.py`,
9500 frames) CONFIRMED the two things a static read couldn't: (a) the throttle fires often (0x25
throttled 25x; A956 is a SHARED every-4th counter across all C237 callers, but the per-frame shadow
starts A956 from the VM so only within-frame call order matters), and (b) the stale-bx quirk is REAL
-- a throttled 0x25 call leaves bx=0x4A and writes `DS:[0x52]=0x1A` (must model). Recovering C237
also UNMASKS behavior 0x04 (AEBF -> AF60, an AED8 variant). Suggested slice order: C237 pure -> 0x25
(incl. the 0x52 stale write) -> 0x04 -> 0x30 -> 0x90/0x91. Clean non-C237 alternatives if preferred:
0x12 (B2CD waypoint follower) and 0x29 (needs 74E2).

## 2026-07-05 - THE L1 FRONTIER IS NOW KNOWN: the demo walk-shadow names every unrecovered actor

`probes/verify_native_walk_demo` shadows every A9D3..AA25 walk frame of the owner's played L1 (native
walk on a pre-state copy vs the VM, full-DGROUP diff) and tallies RecoveryGaps as the frontier. Over
**8294 walk frames**: the opening wave (first ~2500) walks BYTE-PERFECT; then the level's actor zoo
appears. **Unrecovered behaviors by frequency** (= recovery order): 0x1a(480) 0x91(383) 0x25(367)
0x27(320) 0x12(281) 0x19(256) 0x29(182) 0x8c(108) 0x28(84) 0x90(80) 0x2f(80) 0x30(80) 0x11(4) +
0x01-key1-latch9(32) + player-death 9EA3(3) + type-5 pickup collect(2). The full table + handler
pointers live in [`campaigns/enemies_l1.md`](campaigns/enemies_l1.md) (the authoritative L1 target
list). Recover HIGH-frequency first; each slice = one behavior + a `verify_native_walk_demo`
gap-count drop + the 200/0 free-run shadow held.

Instrument/oracle hygiene landed with this: (1) the demo shadow flushes incremental progress (gap
set every 500 frames) + live divergence lines -- no more blind long runs; reads the tile plane FRESH
per frame (the level scrolls). (2) **Completed the documented steer-scratch exclusion**: DS:230C/230D
is the 5E42 delta-steer scratch triple with 230E/2310 ("not slot state" per
domain/movement.DeltaSteerStep) -- the attract-wave free run never toggles it so the canonical
exclusion list omitted it; a player-driven session does. Added to BOTH the free-run and demo shadows
(free-run stays 200/0). Two non-gap divergence classes flagged for the campaign: the 2B5C
gameplay-pool spawn mismatch (7573 alloc) and the 215A derived-scratch drift. Full-session cold-start
REPLAY now reaches frame 20639/22923 (past the fixed 12432 all-keys-released deadlock) before a
transition-blit wait at 1010:3273 -- logged in loop_blockers.

## 2026-07-05 - THE CORE CORPUS: a human-played cold-start session (intro -> menu -> full L1 -> L2 start)

`artifacts/demos/demo_cold_start_full_20260705_123645` (commit 13f47bb): the owner played a complete
cold-start session -- near-pacifist (every enemy lifecycle runs uninterrupted; a few kills + firing
give the combat chain real witnesses), finishing L1 and stopping at the L2 start. 1217 events /
22923 boundaries. **This demo is the standing target: drive the native runtime until this session
replays fully VM-less.** Owner's framing to keep (it matches the recovered structure exactly): a
level is a scroll-cued PERFORMANCE -- the 4A65 script fires on trigger_row==A978 (stage position),
controllers are stage managers, behaviors are actors, the player only interrupts. Two replay bugs
the demo exposed, fixed the same day: play.py --demo now cold-boots snapshotless demos with their
recorded boot params, and the 1F8F:024B all-keys-released wait (no frame boundary -> replay
deadlock at frame 12432) joined the shared input_waits detector family (verifier pseudo-boundary +
single-event pump delivery). New instrument: `probes/verify_native_walk_demo` -- the whole-walk
shadow over EVERY A9D3..AA25 frame of the played session, with RecoveryGaps counted as the
evidence-driven frontier.

## 2026-07-05 - COMBAT campaign: the 62F6 chain COMPOSED into the walk's postmove (kill/survive oracle-pinned)

The walk's BC45/BC4B postmove now runs the full object-vs-object combat chain natively:
`object_overlap_scan_62f6` (who overlaps) -> `bec5_moving_object_outcome` (reaction family) ->
`collision_damage_counter_chain_bf25` (damage) -> the existing `_bfc7_touch_death` (the FULL BFC7
death: score, completion drops, C054, sound, the dying stamp). Candidate fates: variant 2 (player
shot) clears active directly; 5/6/7/8/C run the BD17 chain; owner-link/unclassified fail-louds.
Composed from the already-recovered leaves — zero new recovery except one decode fix:

* **`bp+36` in the BF25 survival docstrings is DECIMAL 36 = `+24h`.** The survive case diffed 2
  bytes (vm wrote `+24h := 5`, native wrote `+36h`); lindis prints decimal bp offsets
  (`[bp+22]`=+16h, `[bp+24]`=+18h). Docstrings clarified in systems/domain collision.
* The capstone `resolve_moving_object_collision` was NOT used directly: its died-path computes the
  C037 sprite by +16h object TYPE (raises on the type-4 enemy); the walk's shadow-verified BFC7
  death keys the C042 table on the +14h scan key. Composed the sub-pieces instead — the unverified
  C037-by-type leaf never runs.
* Gate: `probes/verify_native_combat` — a solid player shot (A4EA seed, `+1E=1`) planted against
  the live L1 wave, one whole walk frame VM vs native, full-DGROUP diff: shot-on-enemy (hp 4 -> 0,
  dying stamp, shot consumed), shot-far (no interaction), shot-on-controller (hp 14h -> 10h
  survive + `+24h=5`) — 3/3 zero-diff, WITH fired-assertions (the oracle fails if the chain
  doesn't fire). Walk order note: effect pool HIGH cx -> LOW, so the FIRST-walked record in a
  stacked group eats the hit (cx=7 died, not cx=3 — earlier "no hit" was a wrong-record read).
* The whole-walk shadow stays **200 frames / 0 divergence**; +3 unit tests
  (`test_behavior_walk_combat.py`) on the static bundle.

Enemy shots (`+1E=0`) are invisible to the scan, so free-run corpora can't witness it — the
campaign's remaining gate is a FIRING demo (real fire inputs end-to-end).

## 2026-07-05 - THE WALK SLICE IS FULLY PREREQUISITE-FREE: allocators decoded, 0x0B already pure

Everything the NativeGame behavior-registry walk needs now exists or is decoded:
* ``7524`` (effect alloc): cursor ``[95D8]``, forward scan 0x23 slots with the ``2B5C -> 23B4``
  wrap, first INACTIVE slot -> cursor updated + returned, FFFF when full. Deterministic; trivially
  pure. (``7573`` = the gameplay-pool twin, cursor ``95DA``, plus a 7550 recycle fallback keyed on
  behaviors 9/0xA / type 1 -> BD0D when full.)
* behavior ``0x0B`` (the enemy shot) = ``B24D`` -- **already recovered** (``systems/object_update``,
  ``object_update_b24d`` family, tested).
* the walk shape (A9DD..AA25): effect slots HIGH->LOW (cx 0x23..1 via 32CA), ``inc [2340]``
  (wrap 0x5DC) per effect visit, the A8C2==1 leader-tick call (skip on L1, fail-loud if set),
  ``[2346] = 0`` between pools, gameplay slots HIGH->LOW (cx 0x22..1 via 8D12); the trailing far
  ``1F8F:0922`` is OUTSIDE the compare boundary (compare at AA25).
* per-record: type dispatch (t0 nop, t6 companion, t2/t4 -> behavior dispatch; others fail-loud);
  behaviors present in a 200-frame L1 free-run: 0x1F (controller), 0x20 (enemies), 0x0B (shots).
NEXT SLICE (the /goal milestone): systems walk composition + the NativeGame registry stage + the
``verify_native_behavior_walk`` shadow probe -- trap A9DD per fast-forwarded frame, snapshot, run
the native walk, let the VM run to AA25, diff pools + walk globals; 200 frames, zero divergence.

SHADOW STATUS (first full runs): the walk composition (``adapters/behavior_walk.py``) + the probe
(``probes/verify_native_behavior_walk.py``) EXIST and run 200 frames with only **34 diverged
frames, all classified by write-trace**:
1. ``BEFF = 0x0B`` queued BY ``8209`` ITSELF (first instruction, ungated) per burst spawn -- add to
   the burst application;
2. frame 86 = the WAVE-END BEAT: the controller re-arms via the C115 family ([A482] = **A83E** -- a
   FOURTH schedule base beyond A4E4/A5C0/A82A!), records its position (2376/2378), and spawns the
   type-5 PICKUP via a ``7424`` stamp (fields traced: +0=1, +2=x, +16=5, +26=2 the pickup kind,
   +8=0x48, +28=FFFF...) -- recover the wave-end path (reached from the 0x1F flow when the
   schedule pair hits the FFFF sentinel, presumably);
3. the ``BC45/BC4B`` POSTMOVE TAIL runs after EVERY jmp-exiting handler (0x1F stub, 0x20, 0x01,
   type-5; NOT the ret-exiting companion) -- it is ALREADY PURE: ``object_postmove_bc4b`` (y clamp
   + X-bounds death; frame 87's pickup died exactly there) and the follow-on collision tail
   (``_fold_bc4b_collision`` in object_update: the 62F6 anchor/shot scan -> the C037 death
   transitions; frame 200's behavior-1 came from an enemy touching the anchor) -- apply both in
   the walk after those handlers (decode the tiny BC45-vs-BC4B entry delta first);
4. ``230E/230F/2310/2311`` = the 5E42 steer's direction/axis scratch (flapping with the shots) --
   OUT-OF-MODEL per the 5E42 island contract, add to the probe's documented exclusions beside
   A954/230A. Registered handlers so far: 0x1F, 0x20, 0x0B, 0x01 (partial, fail-loud edges),
   type-5 pickup (drift + the recovered AA46/8331 touch predicate; collect = declared gap),
   type-6 companion; catalog says that IS the complete 200-frame set.

THE BC45 TAIL, FULLY DECODED (implement in the walk after the jmp-exiting handlers):
* entry BC45 = ``[bp+2] += [A278]`` (scroll drift; used by 0x01 + type-5), entry BC4B skips it
  (0x1F stub + 0x20); then ``call BCB1`` = EXACTLY ``clamp_postmove_y_bcb1``; then the X-bounds
  death = EXACTLY ``object_postmove_x_bounds_deactivates_bc4b`` (wide-set + A47C gate as recovered)
  -> on death ``BD17``: ``+0 = 0``; type 4 -> ``BD5C``: ``call C054`` (DECODE NEXT: the kill-count/
  score beat) then the ``+0x28`` linked-counter clear (index*2 + 2078 table walk, per the recovered
  OFF_LINKED_COUNTER_INDEX note); type 1 -> ``BD56``: ``+0x16 = 2``; then the logic-keyed A970
  decay beats (7/8/0xA/0xC -> BDAC/BDB8/BD9E family, already documented).
* survivor + ``A47C == 0`` -> ``call BCCB`` then ``call 62F6``:
  - BCCB (the ANCHOR-TOUCH scan): skip if inactive / type 5 / behavior 0 or 1; ``+0x14 == 1`` ->
    the AA46 predicate (recovered), ``== 2`` -> AA71 (recovered); on touch: if ``A8C2 != 1`` ->
    ``call BFC7`` (the C037-family self death transition + player-damage extras -- DECODE the
    extras) then ``call 9E69`` (an effect spawn -- DECODE; frame 200's event needs BOTH);
  - 62F6 = the recovered ``object_overlap_scan_62f6`` family (vs the gameplay pool candidates).
* the walk exit map: companion AB10 rets (NO tail); B24D's bounds/AD60 tail is INSIDE the pure fn.

STANDING-MECHANISMS CHECK PAID OFF A THIRD TIME: **the native behavior registry already exists** --
``systems/object_update.py`` has ``NATIVE_OBJECT_HANDLERS`` (per-logic_id ``_advance_*`` fns for
ae09/aed8/b86d/b9f0/ae7d/ae2c/b24d/b909/8d4f/b2cd) and ``native_object_pass_in_place`` (the A9E0
walk: iteration order, the DS:2340 inc-per-entry with 0x5DC wrap, LIVE candidate pools for the
collision scans). The milestone therefore EXTENDS it rather than building anew: (a) register the
new 0x1F full controller (the existing ``_advance_8d4f`` models only the waypoint seek -- add the
arrival BURST + schedule/ring cursors), 0x20 (step_enemy_behavior_20 + the seek/shot application)
and the type-6 companion (the walk must TYPE-dispatch before behavior-dispatch: t6 -> companion,
t0 -> nop, t2/t4 -> the behavior registry); (b) add a FAIL-LOUD mode (unknown active type/behavior
raises, replacing the hybrid-tolerant ``continue``); (c) verify the walk ORDER against the VM
(cx 0x23..1 = HIGH record -> LOW; check ObjectPool's slot ordering matches -- same-frame burst
spawns make order observable); (d) the shadow probe drives it all.

## 2026-07-05 - BDD0 DECODED: the AFD8 contact scan is the ALREADY-RECOVERED player-hazard filter

The last AFD8 unknown maps onto existing pure pieces. ``BDD0``: if the caller's ``+0x0A`` == 1 ->
no scan (clc); else walk the 0x23 effect slots against the probe point (``A438``, ``A436`` -- the
AFD8 mirror cells): candidate iff active AND ``+0x0A != 1`` AND ``+0x14 == 1`` AND ``+0x16 == 4``
AND behavior ``0x82..0x94`` -- **exactly ``collision.is_player_hazard_scan_candidate``'s recovered
filter (PLAYER_HAZARD_LOGIC_MIN/MAX)** -- within a +/-0x10 box on both axes (CONTACT_HALF_EXTENT),
excluding same ``+0x0E`` link keys; hit -> ``5059`` (the stc/damage exit). So the BDD0 pure form is
a COMPOSITION of collision.py predicates + the box test; L1 enemies (behaviors 0x1F/0x20) are NOT
in the hazard range, so enemy steps scan against player-hazard objects only -- consistent with the
cleared-pool oracle environments. Compose + oracle as part of the walk slice.

## 2026-07-05 - The type-6 COMPANION (exhaust flame) recovered pure -- driven 120/120 vs AB10

(/goal loop.) ``systems/companion.step_companion_ab10``: hide (deactivate) when the SHIP POSE >= 3
or ``A47C >= 3``; else sprite = ``A40C``[[2336] & 7] + 9 and position = the 237C anchor + the
``A414``[pose*4] (dx, dy) pair. ORACLE (``verify_native_companion``): **120/120** (3 A47C states x
8 dividers x 5 poses). KEY ALIASING LESSON the oracle caught: **``DS:2384`` IS the 237C anchor
record's ``+0x08`` sprite field** (0x237C + 8 = 0x2384) -- the disasm read it as a separate mode
global, the first probe set "both" cells and got contradictory gates; the trace pinned the alias.
Add to the state-view sweep: name 2384 as anchor.sprite, not a global. Islands 35.

## 2026-07-05 - Behavior 0x1F (the WAVE CONTROLLER) recovered pure -- driven 4/4 WHOLE vs 1F8F:027A

(/goal loop.) ``systems/enemy_behaviors.step_wave_controller_1f``: seek the ``A482``-schedule
waypoint (x_raw+0x20/y via the recovered 5DB2, MODE 3 = 8px; seek globals 2304/2306/2308 written
every frame), sprite = direction + 0x3B every frame (the 0448 exit); on ARRIVAL (blocked seek ==
at-waypoint) advance the schedule +4 and burst FIVE spawns (8209 base with leader-context = the
controller's position, formation slots from consecutive ``A844`` ring reads -- cursor +4 each,
**NO wrap in 0368** -- behavior 0x20, substate FFFF, +A47E each). A schedule cold-load adapter was
DRAFTED AND WITHDRAWN: the cold==live pin caught runtime-written words embedded in the A82A region
past the flown prefix (index 6 held A844 cold vs A858 live -- a ring-cursor-like value INSIDE the
stream), so the region is NOT a flat static pair list; the schedule STRUCTURE decode is its own
future slice (the C115 behavior-keyed bases 0x13->A4E4 / 0x15->A5C0 / 0x1F->A82A stand; the
controller only ever consumes the pair at [A482], which the probe reads live). ORACLE
(``verify_native_wave_controller``): drives the far handler whole (fly far/near, the ARRIVAL burst
incl. all 5 spawned records' stamps, and a later-waypoint case) -- **4/4**. Islands 34.

THE PLANET-1 WAVE STACK IS NOW FULLY PURE: controller 0x1F + enemy 0x20 + locomotion AFD8 + seek
5DB2 + shot 7476/0x0B (5E42 steer) + random 4D95 + the schedule/ring/dispatch tables cold-loaded.
REMAINING for the /goal registry milestone: the type-6 companion handler (``AB10``), the BDD0
contact predicate + the walk's collision/touch-death stage (C037), the walk composition itself
(A9DD order + the 2340 tick), then the whole-walk shadow probe over 200 fast-forwarded frames.

AB10 (the TYPE-6 handler -- the type dispatch goes straight there, no behavior table) IS NOW
MAPPED, tiny: if ``[2384] >= 3`` or ``[A47C] >= 3`` -> DEACTIVATE (``AC22``: +0 = 0); else the
exhaust-flame follow: sprite = ``A40C``[``[2336]``] + 9 (the &7 frame divider through an 8-byte
anim table), position = the 237C anchor's x/y + the ``(dx, dy)`` pair at ``A414``[anchor.sprite*4]
(the offset follows the SHIP's animation frame). Both tables likely static -- pin cold==live in
the adapter test. Next small slice after 0x1F lands.

## 2026-07-05 - Behavior 0x20 COMPOSED PURE (ASM_MATCHED): the first zoo resident + the A844 ring cold-loaded

(/goal loop.) ``systems/enemy_behaviors.step_enemy_behavior_20(...)`` -- the planet-1 wave enemy as
a pure per-frame DECISION fn returning ``EnemyBehaviorStep`` (record/global writes + move/shoot
action flags; the caller runs the recovered 5DB2 seek and 7476 shot). Covers the full phase map:
FFFF approach (2338-clock sprite ramp, arrival checks), hold gate (A7A0 >= 0x23), the 2340-window
shoot (4D95 low-bit gate, random consumed only in-window), the dive retarget (A47E <= 3 parity-
gated via B7C7 / the 2340 < 5 ungated B7CE entry; target y = anchor+8 & ~7, [2340]=0x28, substate
0, sprite 0x78, target x 0x20), the 232E==0x3F re-shuffle from the A844 ring (cursor A842, skip-if-
already-there, +0x20 x bias), and the substate exit chain 0->1->2 (re-approach / sprite 0x79 / fly
+X 4px to sprite 0x77). Ring cold-loaded: ``adapters/enemy_slot_ring_adapter`` (20 pairs,
cold==live pinned). 7 unit tests; island **VERIFIED** by the whole-behavior driven oracle
(``verify_native_behavior_20``): drives the ORIGINAL B73E per phase and compares against the pure
decision COMPOSED with the recovered 5DB2 seek (mode 2, DS:A348 table), the 7476 shot stamp and the
4D95 random -- **16/16** across both sprite ramps, the 0x22-vs-0x23 hold boundary (the >= polarity
now ORACLE-pinned), both shoot parities, all three dive variants, both re-shuffle cases and the
full substate chain. Oracle lessons: (a) clear BOTH pools *and* keep the player anchor away from
the cases -- the real seek path includes the player-touch check and the C037 death transition
zeroed a case's sprite (write-trap diagnosed); (b) that touch-death lives in the WALK's collision
stage, outside the behavior decision (a registry-stage concern). Islands 33.

NEXT (frontier (a) continues): behavior 0x1F = far-call 1F8F:027A (the L1 controller -- disassemble
the overlay side), the BDD0 contact predicate leaf, then the NativeGame behavior-registry stage +
the whole-walk shadow probe over 200 fast-forwarded frames (the /goal condition's proof).

FIRST LOOK at 1F8F:027A (the 8D4F ALIAS FAMILY body -- behaviors 13/15/1C/1F/7D/7E are ONE
parametrized handler): si = [DS:A482] (ANOTHER schedule cursor, 8-byte stride); seek target from
the schedule (x+0x20 -> 2306, y -> 2304), step mode [2308] = 3 (the 8px 5DB2 step) via the
**TRAMPOLINE 1010:8D8B** (far-call helper: invokes the near 1010 routine whose offset is in AX --
how the overlay reaches main-segment code; ax=5DB2 here); on 230A != 0 (still seeking) dispatch
per-behavior tails on [bp+0x18] (0x13->0432, 0x15->03E6, 0x1C->03A6, 0x1F->0368, 0x7D->0309); the
default/0x7E path ADVANCES [A482] += 8 and SPAWNS the next enemy from the schedule (ax=81F4 through
the trampoline; stamps the new record's +0x34/+0x32 targets from the schedule pair). So the 0x1F
object IS the L1 wave controller: it flies a scheduled path and spawns the 0x20 enemies -- decode
the per-behavior tails (0368 for 0x1F) + find the A482 schedule table next.

THE 0x1F TAIL (1F8F:0368) CLOSES THE L1 WAVE MECHANISM: on waypoint arrival (230A != 0 after the
mode-3 seek) -> [A482] += 4, then a **burst of FIVE 81F4 spawns** (trampoline; leader-context
+02/+04 from the CONTROLLER's own bp position), each assigned a formation slot from the **A844
ring** ([A842] += 4 per spawn; +0x34 = ring_x+0x20, +0x32 = ring_y), stamped behavior 0x20 +
substate FFFF, inc A47E -- exactly the L1 snapshot's 5x 0x20 + controller, A47E=6. The controller's
sprite = its +0x06 direction + 0x3B (0x41 in the snapshot -> direction 6). The common exit 0448
also writes that sprite every frame. REMAINING for the registry stage: pure-compose 0x1F (waypoint
seek mode 3 + the arrival burst), find the A482 schedule table + its level-setup init (writer
scan), the BDD0 predicate, then the walk + shadow probe.

## 2026-07-05 - The 0x20 behavior's last two callees recovered: 4D95 canned-random + 7476 enemy shot (driven)

(/goal loop.) ``canned_random_next_4d95(cursor, ring)`` (the fixed 16-word ring cold-loaded by
``adapters/canned_random_adapter``; cursor DS:20A6 +2 wrap-at-20C7) and ``enemy_shot_stamp_7476
(shooter_x, shooter_y, leader_group_a8c2, player_x_237e, player_y_2380)`` (muzzle +0x0C/+0x0C or
+0x1C/+0x08 by A8C2; type 2 / behavior 0x0B / sprite 0x31; the 74E2 aim deltas into +0x2A/+0x2C =
the 5E42 steer inputs; DS:BEFF=0x1A sound + 7573 alloc caller-owned). ORACLE
``verify_native_enemy_shot``: 4D95 40/40 across a full wrap; 7476 8/8 (both muzzles x both 98C0
sound-gate states, full stamp + deltas byte-exact on the allocated slot). Islands VERIFIED (31).

WITH THIS, behavior 0x20's every callee is pure: 5DB2 seek (B729/B85C), AFD8 locomotion, 4D95
random, 7476 shot. NEXT: compose ``behavior 0x20`` itself as the pure per-frame handler (the FFFF
approach phase + substates 0..2 + the hold/shoot/dive/re-shuffle logic vs the 2340/232E/A7A0
clocks + the A844 ring) with a fast-forward-driven whole-behavior oracle -- then the behavior
registry stage has its first two natives (0x20 + the shot 0x0B via 5E42).

## 2026-07-05 - AFD8 COMPLETE: the full worker composed pure + driven 192/192 (the x21 mega-worker is DONE)

(Built-in /goal loop, continuing.) ``systems/contact_step.contact_probe_afd8(x, y, direction, a278,
LevelTileContext, contact_at)`` composes the WHOLE worker: A430 clear + A432/A434 snapshots +
A438/A436 step mirrors, the ``x + [A278] - 0x10`` leading-edge bias (cancels in the final position),
the 5073 probe (215A = adjusted x derived), the off-map early-out, the B022 direction step, un-bias.
ORACLE gate 2 (``verify_native_contact_step``): drives the ORIGINAL AFD8 whole, comparing against
the pure composition over a **PURE tile context** (origin/row_base/tile plane read once from the
snapshot -- no VM callbacks): **192/192 byte-exact** (48 blocked incl. forced off-map), on top of
gate 1's 448/448 handler matrix. Islands: contact_step_b022 + contact_probe_afd8 both VERIFIED.

The x21 mega-worker is fully recovered. NEXT (frontier (a) continues): the 21 caller stubs are now
thin parameterizations (direction source + post-step reactions) -- recover the planet-1 spawn-family
behaviors 0x1F (``8D4F``) and 0x20 (``B73E``) first, tracing cadence from L1_start with the
fast-forward; then the BDD0 contact predicate leaf; then the NativeGame behavior-registry stage +
the whole-walk shadow probe (the /goal condition's proof).

FIRST LOOK at those two (disassembled, not yet recovered):
* **0x1F (``8D4F``) is a FAR-CALL STUB into the 1F8F overlay segment** (``call far 1F8F:027A; jmp
  BC4B``) -- and a whole stub family sits beside it (``8D57``->1F8F:0452, ``8D5F``->1F8F:0473 with an
  HP>=0x64 gate + BFC7, ``8D73``->1F8F:069A, ``8D7B``->1F8F:06B5, ``8D83``->1F8F:08AC = the planet-4
  wave family!). The behavior zoo EXTENDS INTO 1F8F; the xref scan only counted CS:1010 workers --
  rerun it over the overlay when sizing that half.
* **0x20 (``B73E``) is a SUBSTATE machine**: ``FFFF``/0/1/2 on ``+0x1C`` (OFF_SUBSTATE) via a 3-entry
  table at ``CS:B74E``. The FFFF approach phase: sprite animated from the ``DS:2338`` clock
  (y < 0x60 -> 0x7F - [2338], else 0x7A + [2338]), arrival test against the formation slot
  ``+0x32``/``+0x34``, another A7A0 threshold (0x23) at arrival, else fall to the SHARED MOVE TAIL
  ``B85C`` -- NOW DECODED, and the chain CLOSES ON RECOVERED CODE: ``B85C`` = ``[2308]=2; call B729;
  [bp+6]=4`` and ``B729`` = ``[2304]=[bp+0x32]; [2306]=[bp+0x34]; call 5DB2; cmp [230A],0; ret`` --
  i.e. **the planet-1 enemy approach movement IS ``object_target_seek_step_5db2`` (already
  VERIFIED)** aimed at the formation slot, with ``2308`` the step mode and ``230A`` the arrived
  flag. Behavior 0x20 is a THIN COMPOSITION of recovered pieces (sprite anim from the 2338 clock +
  arrival substate machine + the 5DB2 seek) -- the pre2 second-pass principle fully vindicated.
  Recover it as the next slice with a driven oracle; its shape is the TEMPLATE for the whole
  approach-movement behavior family. Full phase map now decoded: approach the slot (FFFF phase,
  5DB2-seek, anim from 2338) -> idle at the slot until ``A7A0 >= 0x23`` -> in ``DS:2340`` walk-clock
  windows (0x2BC/0x2D0 thresholds at ``B7F3``, partially decoded) RETARGET AT THE PLAYER
  (``B7C7``: target_y = [2380]+8 &~7 -- the view-anchor Y, gated on the 2324 frame parity;
  [2340]=0x28 reset; substate=0; sprite 0x78; target_x=0x20) -- the dive attack. Substates:
  0 = re-approach checks, 1 = sprite 0x79, 2 = fly +X until x >= 0xA0 (sprite 0x77, the exit?).
  AND the hold-formation loop (``B7F3``): in the 2340 window 0x2BC..0x2D0, ``call 4D95`` (the x4
  worker, likely the RNG) gates ``call 7476`` (the x6 worker -- likely the ENEMY SHOT spawner);
  with ``A47E > 3`` and ``[232E] == 0x3F``, pick a NEW slot from a SECOND position ring
  ``DS:A844..A894`` (cursor ``A842``, (x+0x20, y) pairs, skip-if-already-there) -- the formation
  re-shuffle. So 0x20's remaining unrecovered callees are exactly 4D95 + 7476 -- both already on
  the xref worker list; recover them as leaves first. BOTH NOW DECODED:
  * ``4D95`` = a CANNED pseudo-random source: cursor ``DS:20A6`` += 2 wrapping over the static ring
    ``DS:20A8..20C6`` (16 words); returns the word -- pure + cold-loadable.
  * ``7476`` = the ENEMY SHOT spawner: alloc via ``7573`` (gameplay pool), sound ``[BEFF]=0x1A``
    (gated on ``98C0``), muzzle offset (+0xC,+0xC) or (+0x1C,+0x8) when the leader-group flag
    ``A8C2`` is set, then the stamp ``{+0:1, +6:0, +8:0x31, +0xA:1, +0x14:0, +0x16:2, +0x18:0x0B,
    +0x1C:FFFF, +0x1E:0}`` and ``74E2`` aim deltas AT THE PLAYER into ``+0x2A``/``+0x2C``
    (= OFF_MOVE_DELTA_X/Y, consumed by the RECOVERED object_delta_steer_5e42!) -- shot behavior
    0x0B is the 5E42 steer family. The whole planet-1 enemy stack (approach/hold/shoot/dive/
    re-shuffle + shots) decomposes into recovered pieces + small stamps.

## 2026-07-05 - The B022 contact-step handlers RECOVERED PURE + driven 448/448 (enemy locomotion core)

(Overnight run, continuing the AFD8 slice.) The per-direction step handlers are now a pure system:
``systems/contact_step.contact_step_b022(direction, ContactStepState, tile_class_at, contact_at)``
-- the 4 axis steppers + the 4 diagonal compositions (original control flow: a refused first axis
still attempts the second, ``blocked`` accumulates). Semantics recovered: leading-edge tile checks
(class 0 walkable; ``+/-0xD`` column, ``+/-1`` row), sub-tile STRADDLE checks (X handlers gate
terrain on the 215A column boundary, Y handlers on ``y & 0xF``), the 215A sample counter with
column wraps of the threaded tile offset, 1px step + A438/A436 mirror deltas, contact-scan UNDO.

ORACLE (``verify_native_contact_step``): drives ``B00D`` on live L1 tiles with a synthetic record,
7x8 positions x 8 directions = **448/448 byte-exact** incl. dx read-back, with a COVERAGE GATE
(419 stepped / 47 blocked -- terrain refusals really exercised; pools cleared so BDD0 misses
deterministically; the contact-undo branch is unit-tested pure). KEY ORACLE LESSON captured: the
first probe version seeded ``DS:215A`` as an input and failed 480/600 -- **215A is DERIVED by 5073
from x (written unmasked) on every probe**, not persistent state; the fixed probe captures the
derived value. Unit tests ``test_contact_step`` (7); island VERIFIED; manifest 28.

REMAINING for the full AFD8 island: the top shape (A432/A434 snapshots, the A278-0x10 bias window,
off-map early-out, the final ZF contract) + the pure BDD0 contact predicate -- then the 21 caller
stubs can be recovered as thin parameterizations. NEXT after that: behaviors 0x1F (8D4F) / 0x20
(B73E) -- the planet-1 spawn family -- via the L1 fast-forward.

## 2026-07-05 - AFD8 DECODED: the enemy MOVE-ONE-STEP-WITH-COLLISION worker; its 8-direction dispatch cold-loaded

(Overnight run, heartbeat cron 19656f49.) Completed the AFD8 map from yesterday's characterization:
the ``CS:B022`` table has exactly **8 entries keyed on the record's +0x06 DIRECTION field** -- the 8
movement directions: key 4=``B03C`` step +X, 0=``B07D`` -X, 2=``B0CC`` +Y, 6=``B10F`` -Y, and the
DIAGONALS COMPOSE the axis handlers (3=``B039`` +Y∘+X, 1=``B0C9`` -X∘+Y, 5=``B10C`` +X∘-Y,
7=``B07A`` -Y∘-X -- each is just ``call axis1`` then fall into axis2). Each axis handler: leading-
edge tile-class checks (recovered ``505B``; class 0 = walkable; ``+/-0xD`` = one tile column in the
5073 offset space), the ``DS:215A`` sub-tile sample counter (already named in systems/tilemap), the
1-pixel position step on ``+0x02``/``+0x04`` mirrored to ``A438``/``A436``, the ``BDD0``
contact-slot scan (carry = hit -> undo the step), ``A430 = 1`` on block (``B032``). So
**AFD8(record) = "try to move 1px in direction +0x06 with terrain + contact collision; ZF returns
no-contact"** -- why 21 zoo behaviors call it: it IS enemy locomotion.

COMMITTED this tick: ``adapters/contact_step_dispatch_adapter.load_contact_step_dispatch`` (the
8-entry table, cold==live test-pinned; ``test_contact_step_dispatch``). Check (a) DONE -- the BDD0
scan substrate is ALREADY PURE in ``systems/collision.py``: ``slot_contains_probe_point`` + the
hazard-scan predicates (BDE3 family), and ``CONTACT_HALF_EXTENT = 0x10`` matches AFD8's ``+/-0x10``
bias window exactly -- the stepper slice COMPOSES, it does not re-derive. NEXT (the stepper slice,
fresh context): (b) recover the pure per-direction stepper over the systems/tilemap +
systems/collision substrates (axis fns + diagonal composition, the 215A counter, the A43x mirror
cells); (c) driven oracle: drive AFD8 on live L1 tiles with a synthetic record per direction x
walkable/blocked/contact cases, compare the record step + A430..A438 + ZF; (d) then the top shape
(A278 bias window) and the ``@recovered_island`` annotations.

## 2026-07-04 - AFD8 (the x21 mega-worker) CHARACTERIZED: the enemy terrain-contact probe on the RECOVERED 5073/505B substrate

Opened the AFD8 recovery (the worker 21 zoo handlers call). Disassembly (lindis, correct targets now):
* ``AFD8..B00C`` top shape: ``[A430] = 0`` (the contact flag); snapshot the object's X -> ``A432``/
  ``A438`` and Y -> ``A434``/``A436``; bias ``[bp+2] += [A278] - 0x10``; ``call B00D``; un-bias
  (``+= 0x10``, ``-= [A278]``); ``cmp [A430],0``; ``ret`` -- **the caller branches on the returned
  FLAGS** (contact / no contact), classic probe contract.
* ``B00D``: ``call 5073`` (coordinate->tile offset) -> ``bx``; ``bx == FFFF`` -> return; else
  ``dx = bx``; ``bx = [bp+6] << 1``; ``jmp cs:[bx + B022]`` -- **a THIRD dispatch table at CS:B022,
  keyed on the object's +0x06 field** (NOT the tile class as first guessed -- [bp+6] is the record's
  direction/step field, OFF_DIRECTION_OR_STEP). Entries land in B03C..B1xx handlers.
* The ``B03C`` handler family: ``bx = dx - 0x0D; call 505B`` (tile-class lookup); on class match,
  window checks (``test [bp+4],0xF``), then ``inc [bp+2]``/``inc [A438]`` + ``call BDD0`` (the
  contact-slot scan family) -- stepping the probe point across the contact window.
* SUBSTRATE ALREADY PURE (standing-mechanisms check paid off): ``compute_tile_probe_5073`` +
  ``lookup_tile_class_505b`` (systems/tilemap.py) are verified; BDD0 is the known contact-scan
  family; ``A278`` is already in ``ObjectUpdateGlobals``.
NEXT (the AFD8 slice, fresh context): (a) cold-load the CS:B022 dispatch table (adapter, like
behavior_dispatch_adapter -- count its entries by the +0x06 key range); (b) recover the top shape +
the per-key handlers as pure fns over the tilemap substrate; (c) driven-oracle: drive AFD8 with a
synthetic record over live L1 tiles, compare A430/A432..A438 + the record writes + the returned ZF.
This one routine unlocks 21 zoo behaviors' contact logic.

## 2026-07-04 - Behavior-zoo SIZED by xref scan: 79% thin stubs; the worker set is ~17, several ALREADY recovered

Ran the shared-worker-first sizing (``scripts/behavior_zoo_xref.py``, linear-span xref over every
EFC4 handler on the L1 snapshot). The pre2 second-pass pattern holds DECISIVELY:
* 149 behavior indices -> 134 distinct handler entries (5x BC45 filler; 6 alias groups -- ``8D4F``
  alone serves behaviors 13/15/1C/**1F**/7D/7E, i.e. the L1 controller object's behavior);
* **106/134 handlers are THIN STUBS** (< 0x20 bytes to their flow break);
* shared CALL workers: **``AFD8`` x21 (the mega-worker)**, ``7476`` x6, ``5DB2`` x6 (= the RECOVERED
  ``object_target_seek_step_5db2``!), ``4D95`` x4, ``BAE1``/``B729``/``5E42`` x3 (5E42 = the
  RECOVERED ``object_delta_steer_5e42``), ``BBED``/``B3BF``/``AF63`` x2 (AF63 = the recovered
  step-delta table) + 7 single-use;
* shared TAIL workers (handlers ending ``jmp X``): ``B2C8`` x9, ``AD60`` x5 (= the RECOVERED
  ``object_tile_probe_deactivates_ad60``), ``F779``/``BB03``/``ADC9`` x3, 6 more x2 + 17 single-use;
  common exits BC45 x72 / BC4B x9.
So the TRUE new-recovery surface is roughly: ``AFD8`` (one routine covering 21 behaviors -- the
biggest single lever in the project right now), ``7476``, ``4D95``, ``B2C8``, ``ADC9``, ``BB03``,
``B729``, ``BAE1``, ``B3BF``, ``BBED``, ``F779``, ``F55A``, ``B85C``, ``B2CD``/``B2AC``,
``87B5``/``8744`` -- ~15 workers plus per-behavior stub parameters, NOT 149 routines. CAVEAT: linear
spans only (conditional paths not walked) -- counts are LOWER bounds on sharing.
NEXT (enemy track): disassemble + drive ``AFD8`` first (21 behaviors), then ``B2C8``+``AD60`` tails
(motion/deactivation family), then the planet-1 spawn-family behaviors 0x1F (=8D4F) and 0x20 (B73E)
from the L1 fast-forward trace.

## 2026-07-04 - PLANET NUMBERING pinned by the demo corpus: play order 1,2,3,4,5,0 -- planet 0 is the FINAL boss level

User-prompted check that corrected a fresh wrong claim ("planet 0 = the cold-boot level"). Reading
``DS:2356`` from EVERY demo snapshot: ``L1``->planet 1, ``L2``->2, ``L3``->3, ``L4``->4, ``L5``->5,
**``L6``->planet 0** (L6_begin/boss/continue/defeated_by_boss/different_weapons/mothership_end).
So the PLAY order is planets 1..5 then 0 -- consistent with the recovered pieces: a new game inits
``2356 = 0`` (``new_game_session_init_96ee``) and the setup ADVANCES it 0->1
(``advance_level_index_9744``) before the first level; the 5->0 wrap IS the final level, not a
restart. Consequences:
* the COLD-BOOT FIRST level is **planet 1** -> its enemy wave is the A7A0-phased per-planet family
  (``B574``: ``B615`` spawn < 0xC8, pause < 0xF0, ``B58A`` boss transform) -- the ``L1_start``
  fast-forward observations (behaviors 0x1F/0x20 spawning) were ALREADY the right family;
* the ``B4A2`` leader-group family (driver -> leader 0x78 + escorts 0x76/0x77/0x79) is the FINAL
  level's MOTHERSHIP formation (the L6 demos incl. ``L6_mothership_end`` witness it);
* NO capture session needed -- the corpus covers every planet (planet-0 gameplay: the six L6_*
  snapshots + player_death; the planet=0 A7A0=0 snapshots -- menu_interaction, showcase,
  start_to_end, the two 202606xx -- are PRE-GAMEPLAY captures where 2356 still holds the init 0);
* LATENT MISMATCH to fix when wiring waves: ``build_cold_level_start`` leaves ``2356 = 0`` (the
  session init) while ``play_native --level N`` loads the LEVEL(N+1) assets -- the cold state must
  apply the 9744 advance (or set 2356 = N+1) so the wave driver dispatches the RIGHT family.
Docstrings/CLAUDE.md corrected (wave_driver_dispatch_b556 now records the numbering).

## 2026-07-04 - Five pre2 endgame principles ADOPTED (mined from the pre2_port methodology docs)

A systematic sweep of pre2_port's docs (AGENTS/charter/methodology/recovery_architecture/state_view/
symbol_ledger/second_pass/checkpoints) for principles OVERKILL lacks. Five are adopted as BINDING
guidance (the rest we already practice):

1. **SHARED-WORKER-FIRST for the behavior zoo** (pre2's second-pass collapse): before recovering any
   of the 149 EFC4 behavior handlers one-by-one, map which are THIN WRAPPERS over shared workers
   (pre2: 6 dispatch handlers -> one ``project_entity`` worker; hooking the worker covered all six).
   The zoo's real recovery surface is the WORKER set, not 149 handlers. First step of the enemy
   track: xref-scan the F0xx-F7xx + 7Axx-8Dxx handlers for common call targets (81F4 spawn, the
   movement helpers, 7524 alloc...) and size the true worker set.
2. **VERIFIER MOVES UP as islands merge** (composed-island checkpoint): when leaves compose into a
   subsystem, verify at the SUBSYSTEM boundary (pre2: one checkpoint at the object-walk RET proved
   the whole 12-slot pass, replacing six per-leaf verifiers). For the NativeGame behavior-registry
   stage: gate the WHOLE A9DD..AA2A walk (all slots, one boundary), not per-handler.
3. **PRE-LIVE SHADOW PROBE before wiring a big island**: lockstep the composed native pass against
   the ASM oracle over a full level BEFORE it goes live (pre2's tick-level shadow caught an 8-bit
   dispatch detail per-leaf tests missed). The fast-forward makes this cheap now.
4. **HOOK-ROLE TAXONOMY + collapse audit**: every hook is probe / verifier / replacement-adapter /
   gap-detector, and its role is its LIFETIME. OVERKILL's 318 "glue" hooks need role classification
   and a per-subsystem collapse plan (a hook accumulating logic = logic that belongs in recovered/).
   A ``hook_audit``-style "which hooks still fire on this snapshot" tool guides retirement.
5. **STATE OWNERSHIP is the depth metric, not pure%**: early = ASM owns state (hooks mirror);
   middle = ASM owns state (hooks replace routines); late = NativeGameState owns state, VM verify-
   only. play_native's wired slice is already LATE phase; the hooks-ON runtime is MIDDLE. Report
   progress as "which subsystems' state does the native runtime own" -- pure% saturates, this doesn't.

Also reaffirmed from pre2's warnings: never collapse hooks to a modern invented design (only on the
original call graph's evidence); naming altitude (ObjectSlot is a fact, "Enemy" is an earned
interpretation); a verifier that passes only because a nested hook hides original behavior proves
nothing. Full mined list in the session transcript; these five are the ones that change our plan.

## 2026-07-04 - Up-to-speed plan item 3/4: the confidence taxonomy ALREADY EXISTED (islands.py) -- adopted + extended

LESSON FIRST: I built a duplicate. The pre2 confidence-taxonomy mechanism has been in this repo all
along -- ``overkill/recovered/islands.py`` (the ``@recovered_island`` decorator: asm / contract /
status GUESS->OBSERVED->ASM_MATCHED->VERIFIED->CANONICAL / merge_target / unknowns), with
``scripts/gen_island_manifest.py`` -> ``docs/overkill/recovered_islands.md`` and the
``tests/test_island_registry.py`` drift test -- but only 20 of ~290 recovered functions use it
(movement + tandy_screen), so it was invisible from the docs I read. I wrote a parallel
``oracle_link`` system; the ARCHITECTURE AUDIT failed it (layer classification), which led to
discovering islands.py. The duplicate is fully reverted; the existing mechanism is the standard.
**Check for an existing mechanism before building one** (grep for the pre2 pattern name first).

Adopted: the 7 enemy-wave functions in ``systems/frame_loop`` now carry ``@recovered_island``
(merge_target ``EnemyWaveSystem``): 8209 spawn stamp, B48B phase (VERIFIED), B5E6 formation stamp
(VERIFIED), B556 planet-keyed driver / B468 count / B58A boss transform (VERIFIED, 18/18 driven), and
``formation_wave_next_spawn`` honestly ASM_MATCHED (composition, unknowns field carries the gap) --
the distinction the ladder exists to keep visible. Manifest regenerated: 27 islands.

POLICY (binding): every NEW recovered function in ``systems/`` carries ``@recovered_island`` with a
truthfully-cited status; legacy functions get annotated WHEN TOUCHED -- never bulk-guess statuses.

ITEM 4/4 RESOLVED BY INVENTORY (the lesson applied): the state-view layer ALSO already exists, at
both layers -- ``recovered/views/object_slots.py`` (the memory-layout lens: named OFF_* offsets over
the 0x38 record -- note ``+0x16`` = ``OFF_HAZARD_CLASS`` (the type-dispatch key) and ``+0x18`` =
``OFF_LOGIC_ID`` (the EFC4 behavior-dispatch index; today's discovery gives these names their exact
meaning), table bases, ObjectSlotView) and ``recovered/domain/object_slots.py`` (pure named accessors:
``ObjectPool.logic_id/sprite_word/active_word/substate/move_delta_*``, systems-importable). Remaining
work is ADOPTION coverage (use the names when touching code, like the island sweep), not construction.

**THE UP-TO-SPEED PLAN IS COMPLETE** (1 fast-forward BUILT, 2 lindis fix BUILT, 3 islands taxonomy
ADOPTED, 4 state-view ADOPTED). The frontier returns to the GAME: (a) the planet-0 leader-group
handlers (F762/F758/F75D/F776 + the 0x76..0x79 zoo) via fast-forward traces -- the cold-boot enemy
wave -- then the NativeGame behavior-registry stage; (b) the death->respawn + level-advance edge
compositions (nearly free); (c) the level-select cursor render + menu flow.

## 2026-07-04 - Up-to-speed plan item 2/4: the lindis/CPU branch-target display FIXED at the source

The recurring "lindis mis-displays jz/jnb/loop targets" lesson (burned every disassembly session;
docs are full of oracle-corrected polarities) is fixed where it lived: ``dos_re/cpu.py``'s Jcc /
loop-family / jcxz trace strings printed the POST-EXECUTION IP -- i.e. the FALL-THROUGH address when
the branch was not taken -- which read as a wrong disassembly target. Now the arrow ALWAYS shows the
ENCODED branch target and ``taken``/``not`` reports the execution outcome. Verified on today's known
case: ``B490: 73 03`` now prints ``jnb -> 1010:B495`` (was ``-> B492``, the fall-through), matching
the driven-oracle-pinned B48B thresholds. No trace-string parser exists (grepped); suite-gated.
Disassembly listings no longer need per-branch oracle polarity checks -- but keep pinning DECISIONS
by oracle anyway (the discipline stands; the tool just stopped lying).

## 2026-07-04 - UP-TO-SPEED PLAN started + the TIMING FAST-FORWARD primitive landed (pre2 parity, item 1/4)

Diagnosed why this port runs slower/more chaotic than pre2_port (same author, started 9 days later,
finished in 15 days): pre2's methodology accelerators are missing here. THE PLAN (execute in order,
one gated slice each):
  1. TIMING FAST-FORWARD (this slice -- DONE);
  2. fix lindis branch-target display (recurring mis-read source; always pin polarity by oracle until
     then);
  3. confidence taxonomy (GUESS->OBSERVED->ASM_MATCHED->VERIFIED) as @oracle_link-style metadata on
     recovered fns + a GENERATED manifest doc + drift test (kills the mislabel-rework class);
  4. state-view layer over the 0x38 object record + DGROUP cells (pre2's dgroup_view pattern; offsets
     confined to one module).

THE PRIMITIVE: `overkill/timing_fastforward.advance_frames_fast(cpu, waits, on_frame=...)` -- advance
a hooks-cleared RAW-BYTES runtime by whole `0679` frame-waits, delivering the REAL installed IRQ0 ISR
(1010:06E5) at the game's own wait points (identical semantics to the frame verifier's ASM-side wait
handler; also services the `9921` sound wait). Gates (probes/verify_timing_fastforward, all green over
800 waits from L1_start): (a) CADENCE -- the logic-frame counter bank 601E (frame parity 2324, dividers
2326/2328/2336, wave clock A7A0) advances +1 exactly every ~4.02 waits, no skips -> ONE LOGIC FRAME =
4 WAITS (70Hz tick / ~17.5fps logic; count A7A0 transitions when reasoning in frames); (b) DETERMINISM
-- two runs byte-identical DGROUP; (c) the old `CS:066B=1` poke RETIRED by measurement: loses 314
DGROUP bytes (first DS:20A6) and stalls permanently at the 9926 sound wait -- but its pre-stall
gameplay trajectory matches, so prior poke-based structure findings stand. loop_blockers updated.

Forward traces (enemy waves, menu flows, sustained play, cadence questions) are now cheap AND exact --
use this primitive, never the poke, and only fall back to the demo frame-verifier when input replay or
produced-vs-VM comparison is required.

## 2026-07-04 - Refactor: one shared flat-image memory shape (adapters/flat_memory)

Consolidated the duplicated VM-free flat-image readers -- ``scripts/play_native._FlatMemory``
(read-only) and ``adapters/cold_level_start._MutMem`` (mutable) -- into
``recovered/adapters/flat_memory`` (``FlatMemory`` / ``MutFlatMemory``, tested). Both consumers
switched; also fixed the stale ``_FlatMemory`` docstring claim ("used ONLY by the --snapshot path" --
false since the cold-start path landed). Probes keep their local one-off readers (verification
artifacts, not runtime). Pure behavior identical; suite-gated.

## 2026-07-04 - ENEMY-AI STRUCTURE CRACKED: the object type/behavior dispatch tables + the planet-keyed wave driver (MAJOR MODEL CORRECTION)

Traced the enemy subsystem's actual per-frame structure. The controller path's tail runs an OBJECT
BEHAVIOR WALK (``1010:A9DD..AA2A``): for every ACTIVE record of the effect pool (35 slots via the
pointer table ``DS:32CA``, ``+= DS:2340`` tick inc, wrap 0x5DC) then the gameplay pool (34 slots via
``DS:8D12``), call ``AA2B``:
* ``AA2B`` = the TYPE dispatch: ``bx = [bp+0x16] << 1; jmp cs:[bx+0xAA36]`` (8 entries; types 2 and 4
  -> ``EFAE``; type 0 -> ``BC45`` no-op exit).
* ``EFAE`` = the BEHAVIOR dispatch: mirrors position (``[bp+4]->DS:D1FE``, ``[bp+2]->DS:D200``) then
  ``bx = [bp+0x18] << 1; jmp cs:[bx+0xEFC4]`` -- a **149-entry jump table** (behaviors 0x00..0x94),
  the per-behavior enemy-AI state machines (the "zoo", ``7Axx..8Dxx`` + ``F0xx..F7xx``).
Both tables are static CS data -> COLD-LOADED (``adapters/behavior_dispatch_adapter``, test
``test_behavior_dispatch``). This is WHY enemies don't move/spawn natively: NativeGame.step never runs
the walk (gap now declared in the ``game_state_controller`` stage note).

**MODEL CORRECTION (the wave driver is PLANET-KEYED):** behavior ``0x21`` = the wave-driver object;
its handler ``B556`` dispatches on the PLANET ``DS:2356``, not one global wave machine:
* ``2356==4`` -> ``8D83`` (planet-4 family);  ``2356==3`` -> ``B48B`` = the A7A0 phase machine
  (``wave_spawn_phase_b48b`` + the B5D8/B5E6 24-enemy formation snake -- so the earlier "formation
  wave" recovery is PLANET 3's family, not the cold-boot wave);
* ``2356==0`` (the cold-boot planet!) -> ``B4A2``: when ``B468`` (count of active ``+0x16==4``
  records, mirrors ``DS:A47E``) == 1 -- only the driver itself left -- the driver TRANSFORMS into the
  formation leader (beh ``0x78``, spr 0x22, pos (0,0)) + allocs escorts ``0x76``/``0x77``/``0x79``
  (sprs 0x20/0x21/0x23), regs at ``A8BE``/``A8BA``/``A8C0``;
* any OTHER planet: A7A0-phased -- ``<0xC8`` per-planet spawn (``B615``), ``<0xF0`` pause, ``>=0xF0``
  the driver becomes the PLANET BOSS in place (``B58A``: beh 0x22, spr 0x71, HP = 10*(planet+1)).
Recovered pure: ``wave_driver_dispatch_b556``, ``count_active_enemies_b468``,
``boss_transform_stamp_b58a`` (+ tests). Driven-oracle 18/18 (``verify_native_wave_driver_dispatch``:
the B556 matrix, the B58A stamp read-back, B468 on the pristine L1 pool == live A47E == 6, and the
AA2B->EFAE->B556 chain incl. the D1FE/D200 mirror -- pinning both tables' indexing on original bytes).

Other facts pinned: L1_start snapshot is PLANET 1 (2356=1; its pool: 5x beh-0x20 per-planet enemies +
1x beh-0x1F, so the "formation" trace observations were planet-1 families); behaviors 0x1F/0x20/0x21
are stamped from per-level DATA (no immediate-stamp writer in CS -- the level-setup/config path
creates the wave-driver object); the B5DE exhaustion branch (cursor==A932) transforms the LEADER (beh
0x64, y=[2380], spr 0x8E). NEXT (enemy track): (a) find the per-level spawn config that creates the
wave-driver/initial objects at level setup (the 99BF/A940/C57C tail family) so the cold pool gets a
REAL driver; (b) recover the planet-0 leader-group handlers (F762/F758/F75D/F776 + the 0x76..0x79
zoo entries) -- that IS the cold-boot enemy wave; (c) then wire the walk into NativeGame as a
behavior-registry stage (fail-loud per unrecovered behavior index).

## 2026-07-04 - Level-select GRID layout cold-loaded (2x3 planet grid: positions + sprites)

Toward wiring the level-select flow: recovered the level-select cursor's GRID LAYOUT data. The cursor
draw (``1010:D4BC``) reads, per cell ``DS:BEDA`` (0-5): the position word ``DS:0xBEDE[BEDA]`` (-> the
``5A00`` draw-position setter) + the sprite pointer ``CS:0xD37E[BEDA]`` (-> ``5A6C`` blit). Both static:
* positions = a clean 2x3 grid -- columns X = 0x2E/0x53/0x78, rows Y = 0x02/0x15 (matches the BEDA nav:
  +/-3 = row, +/-1 = column);
* sprite pointers ``CS:0xD37E`` = 6 planet icons stepping 0x8C8 apart (0x4000, 0x48C8, ...) BUT these are
  RUNTIME-populated (0 in the cold bundle, filled at sprite-decode) -- fail-loud caught an initial wrong
  "cold-loadable" claim, so the adapter excludes them (render-time concern).
Cold-loadable now: ``recovered/adapters/level_select_grid_adapter.load_level_select_grid_positions
(exe_image)`` -> 6 ``(x, y)`` positions (the static 2x3 grid; test ``test_level_select_grid``).

So the level-select DATA is recovered (grid layout + the nav/fire LOGIC from systems/menu). NEXT to wire
the title->level-select->cold-start flow: the cursor RENDER (the ``5A00`` draw-position + ``5A6C`` sprite
blit semantics over the LEVSCR background), then drive the recovered nav (step_level_select_*) from arrow
keys + fire (resolve_level_select_fire_d424) -> cold-start the chosen level. play_native integration.

## 2026-07-04 - Front-end render: 5 more full-screen menu screens are already decodable (dialog gap narrowed)

Started the front-end integration (dialog placement). Measured the menu assets' deplanarized sizes and
found the "smaller dialog placement" gap is NARROWER than stated: HISCORE / LEVSCR (level-select) /
WINSCR / CALIB / REDEF each deplanarize to exactly 160*200 = 32000 chunky bytes -- they are FULL-SCREEN
320x200 screens, so ``decode_fullscreen_image`` renders them DIRECTLY (they were mislabelled as smaller
dialogs). Exposed them as ``native_video/front_end.FULLSCREEN_MENU_SCREENS`` (OKMENU + those 5), corrected
the comment, and added ``test_all_fullscreen_menu_screens_decode`` (each -> (200,320) 4-bit).

So the genuinely PLACED sub-screen images are only CHOOSE / PLAQ0..5 / PANEL (deplanarize to <32000B) --
those still need per-scene x/y placement. This unblocks rendering the level-select screen (LEVSCR is
full-screen) for the menu-flow wiring. NEXT: (a) wire LEVSCR + the recovered level-select grid logic
(step_level_select_*) into play_native's front-end (title -> level-select -> cold-start of the chosen
level); (b) recover the CHOOSE/PLAQn placement (their {w,h} header + the VM blit x/y) for the score/choose
dialogs.

## 2026-07-04 - FRONTIER CONSOLIDATED: leaf recovery exhausted; the port is now an INTEGRATION project

Oriented on the front-end (the recommended next track) and confirmed the same shape as the enemy track:
the LOGIC is recovered, the WIRING is the work. Front-end state:
* RECOVERED (pure fns, systems/menu.py): ``step_menu_idle_558b`` (main-menu idle), the level-select grid
  nav ``step_level_select_page_down/up/decrement/increment`` (D476/D480/D488/D490),
  ``resolve_level_select_fire_d424``, ``step_menu_transition_wait_ce40``, ``step_yes_no_choice_989e``,
  ``step_interstitial_tick_d318``, ``advance_level_index_9744``.
* RECOVERED (render): the full-screen images (OKMENU title, PLAQ/HISCORE/THEND) decode byte-exact
  (native_video/front_end.decode_fullscreen_image).
* NOT WIRED: none of the menu logic drives play_native's front-end (it just shows the title image +
  Space->cold-start). Blocked on: the SMALLER-DIALOG PLACEMENT -- the level-select grid / CHOOSE decode to
  centred sub-images but their on-screen x/y layout is not recovered (front_end.py raises for them). Also
  open: the red key-letter overlay on the options screen.

CONSOLIDATED FRONTIER (honest, across all tracks): the clean-decision-LEAF well is now DRY -- gameplay
(movement/collision/objects/fire), the enemy-wave data path, and the front-end menu logic are ALL
recovered + verified as pure fns. What remains toward the pre2-shaped complete game is entirely
INTEGRATION + a few unrecovered RENDER/SUBSYSTEM pieces:
  1. wire the recovered pieces into play_native's native loop (enemy waves w/ the leader model; the menu
     flow) -- multi-file NativeGame/play_native integrations, proven via fast-forward + frame-verifier;
  2. recover the render gaps that block wiring: smaller-dialog placement, the options red overlay;
  3. unrecovered SUBSYSTEMS: endings, audio drivers.
NEXT RUN: pick ONE integration and do it end-to-end with fresh context (the per-slice leaf loop is done;
this is native-runtime GROWTH). Recommended first: smaller-dialog placement (unblocks the menu flow) OR
the enemy-wave NativeGame wiring (gameplay is more visible). Both are self-contained given what's recovered.

## 2026-07-04 - Enemy leader-context pinned via the fast-forward trace; frontier is now INTEGRATION not leaves

Used the new timing fast-forward (loop_blockers) to trace REAL enemy spawns from L1_start cheaply (458
frames free-run). Findings on a spawned enemy's record:
* ``+0x32``/``+0x34`` = the per-enemy POSITION (Y / X) -- the formation offsets (patterns confirmed:
  columns at +0x34 = 0x30/0x40/0x50/0x60, rows stepping in +0x32).
* ``+0x02``/``+0x04`` = the WAVE/LEADER ORIGIN -- SHARED across a wave's enemies, VARIES per wave (seen
  +02 = 0x70 then 0x20; +04 = 0 then 0xC0). So it is per-wave LEADER STATE, not a constant -- confirming
  the enemy wiring needs the leader-object model, not a fixed stamp.
* ``+0x18`` distinguishes the path: ``0x20`` = per-planet (B615), ``0x61`` = formation (B5E6, recovered).
CAVEAT: the fast-forward skips the ISR, so after ~90 frames the drift stopped further spawns (only the
early per-planet waves were clean) -- fine for structure, not for byte-exact cadence.

FRONTIER ASSESSMENT (honest, per brief §8): the enemy-spawn CLEAN-LEAF well is now dry -- table, stamps,
cursor, phase dispatch, clock, and the spawn composition are all recovered + verified; what remains
(leader-object model for +0x02/+0x04, the per-frame cadence, NativeGame wiring) is INTEGRATION, not
extractable leaves. Likewise the other big tracks -- front-end flow (title/attract/menu -> cold-start),
endings, audio -- are integrations/unrecovered subsystems, not clean leaves. So the phase has shifted:
the highest-value work is now GROWING THE NATIVE RUNTIME (wiring recovered pieces + the front-end flow),
using the fast-forward + frame-verifier to prove each integration, toward the pre2-shaped complete game.
NEXT: pick ONE integration -- the front-end title->cold-start->play flow is the most self-contained and
the biggest gap vs pre2's completeness (its pieces -- title image, D007 attract, cold level start, fire --
are all recovered; the wiring is the work).

Composed the recovered enemy-wave DATA path into the pure step ``formation_wave_next_spawn(cursor,
formation_table)`` -> ``(enemy_stamp, next_cursor)``: it stamps the enemy at the cursor
(``formation_enemy_stamp_b5e6`` over the cold-loaded table's ``(x,y)``) and advances the cursor, or
returns ``(None, cursor)`` when the 24-list is exhausted. This is the callable the native wave driver will
walk. Unit-tested (composition + exhaustion).

HONEST SCOPE (deliberately caller-owned, to be verified vs the VM at wire-time, NOT guessed here): WHEN to
spawn -- the ``A7A0`` formation phase (``wave_spawn_phase_b48b``) + the per-frame cadence (how often the
B49F leader dispatches B5E6) -- and the enemy's ``+0x02``/``+0x04`` leader-context fields (from the
formation leader's object frame). Those are the remaining enemy unknowns; everything else (table, base +
formation stamps, cursor walk, phase dispatch, A7A0 clock) is recovered + verified.

So the enemy-wave subsystem is recovered as far as clean leaves allow; the last enemy step is the
NativeGame wiring, which needs the cadence + leader-context traced (a focused forward-trace, cheaper once
the timing fast-forward from pre2 is recovered -- see the pre2 direction entry). Front-end flow + endings
+ audio are the other remaining tracks toward the pre2-shaped complete game.

## 2026-07-04 - Enemy-wave PHASE dispatch recovered (wave_spawn_phase_b48b) -- the wave clock DS:A7A0

Traced the enemy-wave DISPATCH (correcting last pass: it is gated by ``DS:A7A0``, a wave-phase clock, at
``1010:B48B`` -- reached before the B5E6 formation spawn). Recovered ``wave_spawn_phase_b48b(a7a0)``:
``A7A0 < 0x32`` -> ``"per_planet"`` (the B615 per-planet-config spawn); ``0x32 <= A7A0 < 0x5A`` ->
``"none"`` (an inter-wave PAUSE); ``A7A0 >= 0x5A`` -> ``"formation"`` (the B5E6 24-enemy schedule wave).
Driven-oracle 10/10 (``verify_native_wave_spawn_phase``; the oracle pinned the thresholds -- lindis read
the jnb targets the other way, the recurring lesson). So the wave cadence is a PHASE MACHINE on A7A0:
per-planet spawns early, a pause, then the formation.

The A7A0 CLOCK is now characterized (writer scan): ``inc [A7A0]`` once per frame at ``6031`` (a
free-running per-frame wave counter), reset to 0 at ``FA2F`` (a high/init routine -- level or wave-cycle
start). A7A0 is compared at MANY thresholds -- 0x23 (B7BF), 0x28 (B880), 0x31/0x32 (B48B/B97C), 0x5A
(B497), 0xC8 (B576), 0xF0 (B581) -- so the wave schedule is a MULTI-PHASE machine over frame-time (each
threshold gates a different spawn/behaviour beat), of which B48B's per_planet/pause/formation split is one
slice (recovered).

NEXT: (a) the other A7A0-threshold beats (0x23/0x28/0xC8/0xF0 -- more spawn variants) if a full wave
schedule is wanted, OR pragmatically just wire what's recovered; (b) the B615 per-planet spawn stamp; then
the pure ``formation_wave_step`` + NativeGame wiring (A7A0 as a native frame counter -> phase -> spawn from
the cold-loaded formation table). Enemy spawn recovered: table + base/formation stamps + cursor walk +
phase dispatch + the A7A0 clock; remaining = the other beats + the per-planet stamp + wiring.

## 2026-07-04 - DIRECTION: aligned with the sibling pre2_port (a COMPLETE VM-less native port) -- the proven endgame

Studied the sibling `D:\Games\DOS\pre2_port` (Prehistorik 2), a COMPLETE VM-less native port -- exactly
OVERKILL's endgame, further along. Key takeaways to steer OVERKILL (its docs are the reference):

* **Target shape (proven):** ``scripts/play_native.py`` is the PRODUCT -- cold-boots the WHOLE game from
  the initialised data segment (a ``boot_data.py``, no EXE) + assets, driving intro -> titles -> menu ->
  world-map -> gameplay -> endings, all recovered + byte-exact. OVERKILL is on the same path (cold level
  boot + fire done); the FRONT-END (title/attract/menu -> cold start) + endings are the flow gaps.
* **Crystallization intention (the state-view layer):** pre2 moved recovered code from raw offsets
  (``rw(0x6BF6)``) to source-like named fields (``s.wind``, ``slot.x``) via ONE swappable layer
  (``pre2/bridge/dgroup_view.py`` -- StructView/StructArray/_U16 field descriptors; backends: ByteBackend
  for native+memcmp, Overlay/WidthContract for contract islands). OVERKILL's recovered fns currently
  return raw ``{offset: value}`` dicts (enemy_spawn_stamp_8209 &c.) -- that is the EARLY form; the
  intention is to evolve them toward named structs/views. Not urgent mid-recovery (pre2 did it late), but
  it is the direction: "shaped by reconstructed structs + recovered functions, not hundreds of hooks."
* **Technique that unblocks OVERKILL tracing NOW:** pre2 recovered a TIMING FAST-FORWARD primitive
  (``timing_fastforward.advance_frame_fast``) that collapses the VGA-retrace / timer busy-waits in closed
  form -- the exact thing that made my OVERKILL free-run STALL on the ``0679`` timer-wait (so I had to use
  the slow frame-verifier harness). Recovering an OVERKILL equivalent (find/collapse its frame-wait poll)
  would make forward traces (enemy dispatch, sustained play) far cheaper. Worth doing before the next big
  trace-heavy investigation.

No code change this entry -- direction/technique note. Continue the gameplay recovery toward the pre2-shaped
complete cold-boot game.

## 2026-07-04 - Formation-enemy STAMP recovered (frame_loop.formation_enemy_stamp_b5e6) -- iterator step

Recovered the B5E6 iterator's per-enemy stamp: ``formation_enemy_stamp_b5e6(x, y)`` = ``enemy_spawn_stamp_
8209`` + the B5E6 schedule-position overrides (``+0x34 = x+0x20``, ``+0x32 = y``, ``+0x18 = 0x61``,
``+0x08 = 0xE7``; drops ``+0x02``/``+0x04`` = leader-context, not schedule-driven). Driven-oracle 3/3
(``verify_native_formation_enemy_stamp`` drives B5E6 through the 81F4 alloc from a synthetic A8D0 cursor
entry, checks the stamped record + that the cursor advances by 4).

So the enemy-wave data path is now recovered end-to-end as pure fns + a cold-loader: formation table
(``load_enemy_formation_table``) -> per-enemy stamp (``formation_enemy_stamp_b5e6``) -> cursor walk (+4);
CORRECTION on the wave DISPATCH: it is NOT the B86D/7476 path (that is a different formation family).
``B5E6`` is reached via ``jmp B49F -> B5D8 -> B5E6`` -- an OBJECT-BEHAVIOR handler (the formation-LEADER
object). The spawn cadence (how often the leader's behaviour runs B5E6 -- once per frame? a counter?) is
in ``B49F``/``B5D8`` and is NOT yet traced. NEXT (final enemy slice): (a) trace ``B49F``/``B5D8`` to pin
the leader behaviour + spawn cadence + what makes a leader active (the wave TRIGGER); (b) then the pure
``formation_wave_step`` composition (cursor + cadence -> next formation enemy stamp + advance) and wire it
into NativeGame so the cold level populates. The leader-context (+0x02/+0x04) + the enemy's drift
behaviour remain for byte-exact SUSTAINED motion (the SPAWN stamp itself is exact + verified).

## 2026-07-04 - Enemy WAVE fully mapped + formation table cold-loaded (24-enemy 3-col snake)

Completed the enemy-wave structure (the last gameplay subsystem). It is a FIXED FORMATION:
* **Formation table** DS:``A8D2`` -- a static list of ``(x, y)`` word pairs (STATIC game data: identical
  in the cold bundle and a live L1 capture), terminated at ``A932`` = 24 enemies in 3 columns
  (``x`` = 0x50 / 0x38 / 0x20), each an 8-step snake in ``y`` (0x18 apart, 0x00..0xA8). Now COLD-LOADABLE:
  ``recovered/adapters/enemy_formation_adapter.load_enemy_formation_table(exe_image)`` (test
  ``test_enemy_formation``).
* **Cursor** DS:``A8D0`` -- walks the list; reset to ``A8D2`` at ``B5A9`` (start a wave); ``+= 4`` per
  enemy (``B60D``).
* **Iterator** ``B5E6`` -- per spawn tick: ``call 81F4`` (=enemy_spawn_stamp_8209) then schedule
  ``x -> [bx+0x34]`` (biased ``+0x20``), ``y -> [bx+0x32]``, overrides ``[bx+0x18]=0x61`` / ``[bx+8]=0xE7``
  (sprite). NOTE (from the drive): the base stamp's ``+0x02``/``+0x04`` come from the LEADER's ``bp``
  frame, NOT the schedule -- so the formation enemy's position lives in ``+0x34``/``+0x32``; a pure
  ``B5E6`` step can't model ``+0x02/+0x04`` standalone (leader-context).
* **Wave gate** = the B86D formation family on the DS:2340 tick schedule (``b86d_formation_spawn_tick_
  index`` already recovered) -- what dispatches B5E6.

NEXT (final enemy slice): wire it into NativeGame -- a formation-leader with a B86D tick schedule that,
per tick, spawns the next formation enemy (stamp + the B5E6 position/overrides) until the 24-list is
exhausted, cursor reset per wave. Then the cold level POPULATES with the enemy formation. The pieces are
all recovered now (stamp + table + iterator fields + tick schedule); this is composition/wiring.

## 2026-07-04 - Enemy spawn STAMP recovered (frame_loop.enemy_spawn_stamp_8209) -- slice 1 of the wave spawner

Recovered the enemy spawn stamp (``1010:8209..8247``, the field template the level-wave spawner writes
into each 7524-allocated effect-pool slot): ``enemy_spawn_stamp_8209(x, y)`` -> ``+0x00=1`` (active),
``+0x02``/``+0x34 = x``, ``+0x04``/``+0x32 = y``, ``+0x06=4``, ``+0x0A=1``, ``+0x14=1``, ``+0x16=4``,
``+0x18=0x14``, ``+0x20=4``, ``+0x24=0``, ``+0x28=0xFFFF``. Driven-oracle 3/3
(``verify_native_enemy_spawn_stamp`` drives ``81E9`` through the 7524 alloc with a seeded schedule frame
``ss:[bp+2/4]`` and checks the stamped record).

SLICE 2 LOCATED (the formation-schedule iterator @ ``1010:B5E6``): it walks the enemy schedule via the
pointer ``DS:A8D0``: ``si = [A8D0]`` -> ``call 81F4`` (spawn, uses enemy_spawn_stamp_8209) -> ``lodsw``
X -> ``+0x20`` -> ``[bx+0x34]`` -> ``lodsw`` Y -> ``[bx+0x32]`` -> overrides ``[bx+0x18]=0x61``,
``[bx+8]=0xE7`` (sprite) -> ``inc [A47E]`` -> ``[A8D0] += 4`` (one X,Y WORD-PAIR advanced per enemy).
So the LEVEL ENEMY LIST is a stream of ``(x, y)`` word pairs at ``DS:A8D0``, terminated when A8D0 reaches
``A932`` (``B5DE cmp [A8D0],A932``). A parallel path at ``B615``/``B61F`` spawns with per-level config
(gated on ``[2356]`` = planet). This is the wave spawn.

NEXT (slice 3): (a) recover the ``B5E6`` iterator STEP as a pure fn (read x,y; stamp = enemy_spawn_stamp_
8209 + the B5E6 overrides; advance the ptr) -- driven-oracle; (b) find where ``A8D0`` is INITIALISED to
the level's enemy list (level-load / 0E9C) + the WAVE GATE (what runs B5E6 -- the B86D formation-leader
behavior on the DS:2340 tick schedule?). Then wire it + the list into NativeGame so the cold level spawns
enemies on schedule. -- Original caller list: ``81E9`` <- ``81CC``, ``B61F``;
``81F4`` <- ``86A3``, ``B5EB``, ``D13A``, ``F121``. The ``81CC`` caller (``81C9``) is a SINGLE-enemy
wrapper (spawns one, then overrides ``+0x02=0x10`` / ``+0x04=[A40A]``), NOT the formation walk. The
FORMATION-schedule iterator is among the ``B6xx`` callers (``B61F``/``B5EB``) -- the same B86D/B800
formation family already partly recovered (``b86d_formation_spawn_tick_index``/``advance_formation_spawn_
ptr``). So slice 2 = disassemble ``B5EB``/``B61F`` (and the B800 spawn-ptr walk) to find where the per-
enemy x/y (the ``bp`` frame) comes from -- the level enemy-list/formation-table format -- and how the
wave is gated on the scroll (DS:2350/A978/the B86D DS:2340 tick schedule). Wiring that + this stamp into
NativeGame makes the cold level POPULATE with enemies. (The stamp -- slice 1 -- is done + verified.)

## 2026-07-04 - LOCATED the enemy-wave spawner: 1010:81E9..822E (allocate + stamp enemy from schedule X/Y)

Traced it properly (method: run_ref_step_probe on the L1_start demo -- which advances frames, unlike a
free-run that STALLS on the 0679 timer-wait -- + a Memory.ww write-trap gated on ``self is ref_mem`` AND
``seg == DS`` [the seg check is essential: without it the trap catches SPRITE-COMPOSITOR pixel writes at
2F81/3360/35C6 whose framebuffer offsets coincidentally hit object-record offsets in a DIFFERENT
segment]). The clean trap pinned two DS object-activation writers over 150 frames:
* ``IP A4F1`` -> GAMEPLAY pool (0x2B5C..) = PLAYER SHOTS (the A4EA fan-out spawn, expected).
* ``IP ~820E`` -> EFFECT pool (0x23B4..), CONSECUTIVE slots (a 6-enemy formation) = THE ENEMY-WAVE SPAWN.

The enemy-spawn routine ``81E9..822E``: ``call 7524`` (alloc slot -> bx; ret if pool full), then stamp:
``+0x00=1`` (active), ``+0x0A=1``, ``+0x02 & +0x34 = X`` (from ``ss:[bp+2]``), ``+0x04 & +0x32 = Y`` (from
``ss:[bp+4]``), ``+0x06=4``, ``+0x14=1``, ``+0x28=0xFFFF``; a ``98C0``-gated ``BEFF=0x0B`` side write. So
X/Y come from the CALLER's schedule entry (``bp`` frame) -- the caller iterates the level's enemy
schedule and calls this per enemy in a formation.

NEXT-RUN PLAN (bounded, 2 slices): (1) recover ``enemy_spawn_stamp_8209(x,y)`` -- the field template, a
clean driven-oracle leaf like player_companion_spawn (drive through the 7524 alloc, check the stamped
enemy record); (2) find + recover the CALLER (the level enemy-schedule iterator that supplies X/Y and
gates on the scroll/A978) -- disassemble the callers of 81E9/81F4. That is the wave spawner; wiring it +
the schedule read into NativeGame makes the cold level POPULATE with enemies.

## 2026-07-04 - Enemy-spawner scoping: formation CHILDREN recovered; the wave/LEADER trigger is the gap

Investigated the enemy-wave spawner (the pool stays empty at cold start). Findings:
* The formation-CHILD spawn is ALREADY recovered: ``b86d_formation_spawn_tick_index`` (B86D schedules
  spawns on exact DS:2340 counter ticks), ``advance_formation_spawn_ptr`` (B800 spawn-list pointer),
  ``formation_spawn_seed_7476`` (the child stamp). These are OBJECT BEHAVIORS (via the AA2B draw-layer
  dispatch) -- so a formation LEADER object must already be active for children to spawn.
* Where enemies live: NOT the gameplay pool (0x2B5C) as assumed -- scanning the L2_full snapshot, the only
  active non-player object is in the EFFECT pool (``0x23B4`` slot 0, logic(+8)=0xA at 0xD9/0x60). Mid-level
  snapshots are surprisingly quiet (1-2 active objects), so they don't reveal the wave cadence.
* THE GAP: what spawns the formation LEADER / first enemy from the LEVEL SCHEDULE as the world scrolls
  (tied to DS:A978 rows-to-milestone + the level map/Gn data). Not located in the recovered code.

NEXT-RUN PLAN: trace a FIRING/active gameplay demo (e.g. showcase or L2_full played forward, NOT the quiet
start snapshot) and watch for the first EFFECT/gameplay-pool activation -- capture the routine that does
the 7524 alloc + stamp of an enemy, and what gates it (scroll position / A978 / a level enemy list
pointer). That routine is the enemy-wave spawner. It shares the cold tile-probe origin fix (already done).

## 2026-07-04 - MILESTONE: play_native FIRES -- cold-started level shoots real (persisting) player shots, VM-free

Executed the 4-step plan from last pass and it WORKS. play_native's cold start now produces live gameplay:
holding fire spawns player shots that persist + move across frames, no VM, no snapshot.

Two fixes:
* **Cold scroll origin (``_COLD_ROW_BASE = 0x9C``):** pinned the frame-0 level-start ``DS:2350`` from the
  LEVEL-LOAD code -- ``60C5`` sets ``2350 = 0xEA0`` (= tile-plane size), then the ``16x A781`` warm-up
  scroll settles it to ``0x9C`` (``60D5 cmp [2350],0x9C``); ``234E`` stays 0 (``60B3``). So this is
  cold-DERIVED, not guessed. ``_cold_seeded_start`` now uses ``origin_x=0, row_base=0x9C`` (was 0/0, which
  underflowed the object-pass tile probe -> IndexError).
* **Fan-out source = player:** ``_advance`` now passes the player view-anchor position
  (``special_pool.x/y_word(0)`` = 0xC0/0x58) as the fire source (was hardcoded 0,0 -> shots at the origin).

Verified: ``test_cold_start_fires_a_persisting_shot`` (new) -- fresh level has 0 shots; one fire -> 1 shot
at the player; tap-firing accumulates persisting shots. Headless play_native cold run is crash-free.

So the VM-less native runtime now: cold-boots a LEVEL + renders the real frame (player+starfield+sprites)
+ FIRES. Remaining toward "the real game": (1) enemy-WAVE spawner (still populates nothing -- the pool
starts empty; separate track); (2) the FULL fan-out / A970 lifecycle for scroll > 0xB6 (later in the
level); (3) front-end intro/menu -> cold-start wiring; (4) sustained-play divergence (verify vs VM over
many ticks). NEXT: the enemy-wave spawner (trace an L1 demo for the first gameplay-pool activation).

## 2026-07-04 - REFRAME: firing at level start is the EARLY path (works); the real blocker is the cold scroll origin

Investigated "make play_native fire" and REFRAMED both gameplay tracks (this supersedes the A067/A970
framing for LEVEL START -- that FULL-fanout path is for scroll > 0xB6, later in the level):

* **Firing already works on the EARLY path.** At cold start ``scroll_2350 = row_base = 0 <= 0xB6``, so
  the fan-out takes the EARLY path (``native_a19f_tail``), which IS recovered + wired through
  ``NativeGame.step`` -> ``native_action_fanout_step``. Confirmed: with the player position as the fire
  source, ``native_action_fanout_step`` spawns a shot (slot 0 active at 0xC0/0x58). So firing is NOT
  gated on the FULL fan-out / A970 at level start.

* **BUG in play_native (bounded fix):** ``_advance`` passes ``source_x=0, source_y=0`` (hardcoded) to the
  fan-out -- shots spawn at the ORIGIN, not the player. It should pass the player anchor's position
  (``special_pool.x_word(0)``/``y_word(0)`` = 0xC0/0x58) + ``source_index=0``.

* **REAL BLOCKER (deep):** fixing the source to the player position then crashes the object pass with an
  ``IndexError`` in ``object_tile_probe_deactivates_ad60`` -- ``tile_plane[offset]`` out of range. The
  probe offset for an object at (0xC0,0x58) with the cold origin ``origin_x=0``/``row_base=0`` is
  ``0xff69`` (an UNDERFLOW: the probe subtracts against ``row_base``, and ``row_base=0 < obj_y=0x58``).
  So the cold-start scroll origin I chose (0,0) is WRONG for the tile system -- the real level-start
  ``DS:2350``/``234E`` must position the view so objects land inside the 3744-byte tile plane. This gates
  ANY populated gameplay pool (shots AND enemies), so it is the shared blocker for both tracks.

ROOT CAUSE CONFIRMED: the tile-probe underflows because ``row_base = 0 < obj_y``. Any valid ``row_base``
fixes the range; candidates found (all put obj(0xC0,0x58) in-range): level-load writes ``234E = 0``
(``60B3``) + ``2350 = 0x9C`` (``CFD2``, offsets ~0x5) or ``2350 = 0xEA0`` (``60C5`` = 3744 = tile-plane
size, offsets ~0xE09); the L1-start capture has ``234E=0x0F``/``2350=0xB6`` (offsets ~0x1F) but those are
a few scroll-frames in, NOT frame 0. So ``2350`` is a RUNTIME scroll value, not a single level-load
constant -- the frame-0 value must be pinned + tile-alignment-verified before use (a wrong-but-in-range
row_base would deactivate objects on the WRONG tiles -- do NOT guess-commit it).

NEXT-RUN PLAN (bounded): (1) trace a cold->level demo (or the level-load 0E9C/setup-tail path) for the
234E/2350 values at the FIRST gameplay frame; (2) set them in ``_cold_seeded_start`` (currently 0/0);
(3) fix ``_advance`` to pass the player anchor position as the fan-out source (currently 0/0); (4) verify
play_native cold-fires a shot that persists (no IndexError, shot at the player). That makes play_native
FIRE at level start. Only AFTER (later scroll > 0xB6) does the FULL fan-out / A970 lifecycle matter.
Enemy-wave spawner shares the same origin fix (any gameplay-pool object needs the in-range tile context).

## 2026-07-04 - A067 composition step 1: native_a067 now COMPOSES the FULL fan-out (backward-compatible)

Systematic first brick of wiring the A067 FULL fan-out into gameplay. The FULL fan-out
(``native_a067_full_fanout``) was already byte-exact vs the VM (L6 58/58) but ``native_a067`` (the
frame-loop entry) just ``return None``-declined the FULL path. Now ``native_a067`` DELEGATES to it: on the
``FULL_FANOUT`` path, IF the caller threads the extra state (``effect_pool`` + the ``a970``-family
held-action counters + the A515 scan state ``cursor_a43a``/``a960``/``a97e`` + ``a95e``/``a96e`` + the
mirror/side schedules), it runs the capstone and returns an ``A067Result`` whose new ``full_result`` field
carries the threaded counters back for the next frame. Only the plain ``FULL_FANOUT`` path (NOT
``FULL_BDAC_A114``/``A515`` -- unmodelled) delegates; without the threaded state it still returns None
(backward-compatible -- existing callers like ``native_action_fanout_step`` are unchanged).

Verified: ``test_a067_full_fanout`` (7 passed) -- the delegated FULL path matches ``native_a067_full_fanout``
directly (shots + cursor + ``full_result``), and the un-threaded FULL path still declines. Trigger is
DS:98BE bit 4.

NEXT (systematic, step 2): thread the FULL-fanout state through ``FireControlState`` + ``native_action_
fanout_step`` + ``NativeGame`` so the STANDALONE runs the FULL fan-out. **The A970 lifecycle -- the piece
that was "unmodelled" -- is now fully MAPPED (this pass):**
  * GATE: ``a3a0 == 0`` (i.e. ``A970 == 0``) opens the shot (A41A: ``if a3a0 != 0: return None``);
  * RESET: ``respawn_control_reset_c461`` sets A970/A972/A974/A976 = 0 (recovered);
  * INCREMENT: ``add ds:[A970],2`` at ``A440`` / ``A46C`` on a FULL fire (the "caller's += 2");
  * DECAY: dec-if-nonzero (floor 0) per frame -- ``BDAC``(A970) / ``BDB8``(A974) / ``BDC4``(A976) /
    ``BD9E``(A97E), each a trivial 3-instr ``cmp/jz/dec`` leaf; ``BD98`` dec A972 (unconditional, other
    context).
So the step-2 model is: carry A970-family in FireControlState; on a FULL fire add 2; apply the decay;
feed to ``native_a067_full_fanout``.

CORRECTION (this pass -- the decay is NOT a simple per-frame call): the decay handlers BDAC/BDB8/BDC4/
BD9E have NO near-callers (E8) -- they are DISPATCHED (object-behavior/jump-table), and the routine just
above (``BD82``) shows the family is entangled with A3B4-RING processing: BD82 walks the A3B4 coordinate
ring (26 words, the one respawn_control_reset fills with 0xFFFF), and for each non-0xFFFF entry zeroes the
pointed-to object and ``dec [A972]`` -- i.e. the counters track QUEUED objects in the ring, not a plain
cooldown tick. So the A970 decay cadence is tied to the ring/object lifecycle, a deeper investigation
than a per-frame decrement. NEXT-RUN PLAN: trace A970/A972/A974/A976 across a FIRING L1 demo to see the
exact per-frame delta (increment vs decay) empirically, THEN model it; only then is the FireControlState
threading honest (a modelled-decay is required -- a no-decay stub would fire once then never, which is
incomplete, not faked, but not useful). play_native firing is thus 1 investigation + 1 threading slice
away. Enemy-WAVE spawner is still the separate track.

## 2026-07-04 - FRONTIER SCOPING: the two "make gameplay populated" gaps, precisely located

With the VM-less cold LEVEL BOOT landed, the next real target is "enemies + fire actually happen." Scoped
it honestly (no forced slice -- these are multi-slice subsystems, best attacked with fresh context):

* **A067 FULL fan-out (player held-fire spawn actions).** IMPORTANT (verified this pass -- avoid
  re-recovering): the spawn SEEDS and per-shot logic are ALREADY recovered -- ``object_spawn_seed_a4ea``
  (the A4EA type-0x32 shot seed, byte-exact), ``PlayerShotSpawn`` (the A41A single-slot spawn),
  ``A515LinkSpawn``, ``object_spawn_seed_8209/7420``, ``formation_spawn_seed_7476``; the ``A970 += 2``
  counter is documented as "the fanout caller's". So the gap is NOT recovery, it's COMPOSITION:
  ``native_action_fanout_step`` DECLINES the FULL fan-out paths because the A970-family held-action
  counters must be threaded frame-to-frame (their per-child increment isn't wired into the native loop),
  and FULL_BDAC_A114/A515 have no native composition yet. NEXT-RUN PLAN: compose the FULL fan-out over the
  already-recovered seeds + thread the A970 counters through NativeGame, verified vs a firing demo.

* **Enemy-WAVE spawner (populates the 0x2B5C gameplay pool).** DISTINCT from A067 (that's player fire).
  Cold-start leaves the gameplay pool empty (correct -- a fresh level has no live enemies); enemies enter
  as the world scrolls, driven by the level's wave schedule. Its location is NOT yet pinned -- needs a
  demo trace of what activates a ``0x2B5C``-region slot (a ``7524`` alloc + stamp) as ``DS:A978``
  (rows-to-milestone) ticks. NEXT-RUN PLAN: trace an L1 demo for the first gameplay-pool activation, find
  the caller, recover the wave-table read.

Both are the "forward-carry wall" in different guises. The cold boot renders the correct (unpopulated)
level-start frame; these two make it a live game. Front-end (title->attract->level) is the other track.

## 2026-07-04 - MILESTONE: play_native COLD-STARTS a level with NO --snapshot (real VM-less level boot)

Wired ``build_cold_level_start`` into ``scripts/play_native.py``: ``--snapshot`` is now an optional DEBUG
override, and the DEFAULT path cold-starts the level from the recovered seeds. New ``_cold_seeded_start``
builds the ``_SeededStart`` from ``build_cold_level_start`` (game+starfield state) + the cold data image
(sprite half-stride) + the level-post-load scroll origin (origin_x=0, row_base=0, row_source=0x5B00 --
NOT the cold image's mid-scroll live cursor, which wraps the starfield page) + semantic cold exit guards
(A47C=0, A95A=3, 2326=0, so the frame-0 detector cannot spuriously end the level).

Verified headless (SDL dummy): ``python scripts/play_native.py --level 0 --no-title`` cold-loads LEVEL1
(tile_plane 3744B, VM-free) and runs the frame loop with NO snapshot, no crash, no fail-loud gap, past
the old ~35-tick verify wall (standalone play drifts visually but does not fault). First fix needed along
the way: the level-post-load scroll origin (the bundle's live 234C=0xff98 crossed the 64KiB starfield
page -- fail-loud caught it).

**This is the first real VM-less LEVEL BOOT** -- play_native is now the cold entrypoint the user asked
for (start levels first; intro/menu next). Remaining for real gameplay: the forward-carry wall (A067
fan-out / enemy spawning -- currently no enemies spawn natively), then the front-end (title image + D007
attract are native; menu logic gap) to open on intro/menu like the original. NEXT: A067 spawn fan-out, or
the title/menu -> cold-start wiring.

## 2026-07-04 - COLD level-start state assembled VM-free (build_cold_level_start) -- de-stages play_native

First real de-staging step toward the VM-less cold start (per the user: move play_native off its
``--snapshot`` staging toward the real game). New adapter
``recovered/adapters/cold_level_start.build_cold_level_start(exe_image)`` assembles the frame-0
level-start ``(NativeGameState, StarfieldState)`` ENTIRELY from the recovered seeds -- session init
(96EE) + C4DB new-game setup + C3A6 gameplay-pool seed + control reset (C461) + player spawn (C42F) +
cold starfield -- by writing them into a fresh data image and reading back through the EXISTING
VM-verified ``read_native_game_state`` projection. No VM, no capture.

Result (``test_cold_level_start``): player view-anchor active at (0xC0, 0x58); all 34 gameplay + 35 effect
slots FREE (a fresh level has no live enemies); 40-star cold starfield enabled. Every write is an already
byte-exact recovered seed, so the assembly needs no new oracle. Marked omission (not faked): the 7524
companion/flame object needs the runtime allocator, so it is not placed.

**This is the state brick play_native needs to drop --snapshot.** NEXT: wire ``build_cold_level_start``
into play_native as the default cold start (it still also needs the level-start SCROLL cursor
234C/234E/2350 + the sprite half-stride -- both cold-derivable from the level data), then the standalone
boots a level with zero VM. After that: the forward-carry wall (A067 fan-out) for sustained play.

## 2026-07-04 - Bucket F: recovered the GAMEPLAY pool seed (C3B5) -- resolves "where is 0x2B5C seeded"

Recovered the last C3A6 pool re-init: ``frame_loop.object_pool_seed_c3b5`` (``C3B5..C3E5``) -- the seed
for the GAMEPLAY/enemy pool at ``DS:0x2B5C`` (``POOL_BASE_GAMEPLAY``), the one the C4DB new-game seed does
NOT cover. This resolves the open question from the pool-layout slice ("the gameplay table is seeded
elsewhere"): it's seeded HERE, in the respawn/level-start C3A6. 34 slots from table ``DS:0x8D12`` (which
maps to ``0x2B5C`` + i*0x38), template ``+0x00/+0x18/+0x2E=0`` + a back-buffer pointer ``+0x0E`` stepping
``0x8D58 += 0x40``. Driven-oracle **34 records x 4 fields = 136 checks, 0 fails**
(``verify_native_gameplay_pool_seed``). Fixed a docstring cross-ref in object_pool_seed_c4db accordingly.

**Bucket-F level-start is now COMPLETE at the pool level:** C4DB seeds special+effect (36, 0x32CA); C3A6
seeds gameplay (34, 0x8D12/0x2B5C) + re-seeds special+effect + player/companion spawn + control reset +
starfield (cold). Every level-start pool + spawn is byte-exact vs the VM. NEXT: wiring the cold
starfield/level-start into play_native, or a fresh subsystem (score add-points path, audio).

## 2026-07-04 - Bucket F: respawn/level-start control re-init (C461) -- completes the C3A6 memset

Recovered the C3A6 tail's control reset: ``frame_loop.respawn_control_reset_c461`` (``C461..C4AD``) -- the
``A3B4`` coordinate ring (26 words -> 0xFFFF) + ``A95A=3``/``A95C=0x18`` + the zeroed control family
``A970/A972/A974/A976/A97A/A97E`` + the scripted-move counters ``A39A/A39C=0`` + ``9788=0xFFFF`` (37
cells). Byte-exact AND complete vs the VM (``verify_native_respawn_control_reset``, driving C461->C4B3;
the A3B4 ring's ES write lands in DGROUP since SS==DS). The ``9DB9`` game-over-arm call + ``A980``/``20A6``
writes that follow are separate.

**The C3A6 respawn/level-start re-init is now essentially fully recovered:** two pool re-seeds
(``object_pool_seed_c4db`` for the 0x32CA pool; the 34-slot 0x8D12 pool remains), player spawn
(``player_spawn_record_c42f``), companion spawn (``player_companion_spawn_c453``), and this control reset.
NEXT: the 34-slot 0x8D12 pool re-seed, or wiring the cold starfield into play_native.

## 2026-07-04 - Bucket F: player COMPANION spawn (C453) -- the flame/exhaust object stamped at spawn

Continued the C3A6 player-spawn recovery: right after the player record stamp, ``C450`` allocates a
companion object via ``7524`` and stamps it (``C453..C45F``). Recovered as
``frame_loop.player_companion_spawn_c453`` -- the allocated record gets ``+0x00=1`` (active), ``+0x14=1``,
``+0x16=6`` (its logic/sprite type, the player's flame/exhaust anchor). Driven-oracle 3/3
(``verify_native_player_companion_spawn``, driving C450 through the 7524 alloc; the slot lands in the
effect table on the death snapshot). This leaf is the stamp template; the 7524 allocation itself is the
allocator's concern.

Remaining C3A6 tail: the ``A3B4`` coordinate-ring clear (26 words -> 0xFFFF) + the ``A95A=3``/``A95C=0x18``/
``A970..974=0`` counter re-init (a clean memset leaf), and the two pool re-seeds (the 34-slot 0x8D12 pool
is new; the 36-slot 0x32CA one is already object_pool_seed_c4db). NEXT: the A3B4/A95x/A970 respawn
control re-init, or wiring the cold starfield into play_native.

## 2026-07-04 - Bucket F: the STARFIELD init is cold-loadable (no capture) -- proven, gap closed

Acting on the user's steer (a menu->level-start demo shows how the starfield is initialised), settled the
last Bucket-F level-start gap. The starfield is NOT re-seeded per level: scanning the code shows NOTHING
writes the DS:0xC6C1 star stream (the two refs at 4C77/4CF3 are ``mov si,C6C1`` reads for the plot/move),
so the stream is static image data (dx/color fixed) scrolled in place by ``advance_starfield``.

Proven: the level-1 START starfield equals the cold-loaded starfield (``load_starfield_state``, from the
static runtime bundle) ADVANCED by exactly 71 frames (the pre-level screens) -- a FULL 40-star match
(rows+dx+color), and dx/color are static-equal cold-vs-level. New regression test
``test_cold_starfield_advances_to_a_real_level_start`` locks it in (pure, no VM). So the "starfield init
needs --snapshot" framing was WRONG: the init is ``load_starfield_state`` + ``advance_starfield``, no
capture required.

**Bucket F level-start state is now fully cold-loadable / native:** object-pool seed (C4DB), player spawn
(C42F @ 0xC0/0x58), and the starfield -- all recovered. ``scripts/play_native.py`` still READS the
starfield from ``--snapshot`` (``_read_starfield``); wiring it to ``load_starfield_state`` is now a pure
mechanical swap (kept separate since play_native's player/object state is still snapshot-based, so the
frame-phase must line up). NEXT: the 7524 companion/flame spawn (C450), or wiring the cold starfield.

## 2026-07-04 - Bucket F: recovered the PLAYER SPAWN state (C42F, 237C active @ x=0xC0/y=0x58)

Chased the respawn re-init (the 9773 else-branch, ``C3A6``) and found it contains the player spawn --
one of the headline Bucket-F gaps ("player spawn ... needs a captured snapshot"). ``C3A6`` re-inits two
object pools (a 34-slot pool from table ``DS:0x8D12`` + the 36-slot C4DB-style pool from ``0x32CA``) then
STAMPS the player record: ``frame_loop.player_spawn_record_c42f`` -- ``DS:237C`` ``+0x00=1`` (active),
``+0x02=0xC0`` (spawn x), ``+0x04=0x58`` (spawn y), ``+0x0A=1``, ``+0x14=2``, ``+0x16=3``. Driven-oracle
**6/6** (``verify_native_player_spawn``, driving C42F->C450). The player-spawn state is now NATIVE (no
longer needs ``--snapshot``); updated the native_app level-load gap note accordingly.

The C3A6 tail after the stamp: a ``7524`` companion-object spawn (``ds:[bx]=1``, ``+0x14=1``, ``+0x16=6``
-- the player's flame/shot?), an ``A3B4`` coordinate-ring clear (26 words -> 0xFFFF), and the
``A95A=3``/``A95C=0x18``/``A970..974=0`` counter re-init. Remaining Bucket-F GAP: the STARFIELD init
(still needs a capture) and the two pool re-seeds' full byte-exact recovery (the C4DB-style one is already
``object_pool_seed_c4db``; the 34-slot 0x8D12 pool is new). NEXT: the starfield init, or the companion/
flame spawn (7524 at C450).

## 2026-07-04 - Score subsystem mapped (32-bit LE @ 2314); representation corrected

Mapped the score subsystem's structure (boundary, not yet a recovered leaf). The score is a **32-bit
little-endian value at DS:2314..2317** (NOT BCD digits, as the session-init note implied -- corrected):
``532D`` ranks it against the 8-entry high-score table with a 4-byte ``sub``/``sbb`` compare; ``5434``
copies the two score words into the "SCORE:" display buffer; display also via ``5F05``. Operand refs to
2314 are all display/high-score/bonus/init (528D/53A6/5444/5EE2/5F11/9708) -- the ADD-POINTS path is NOT
among them, so points are awarded elsewhere (a ``bp``-relative 32-bit add in the kill/scoring flow, not
yet located = GAP). Corrected ``new_game_session_init_96ee``'s docstring accordingly.

NEXT: locating the add-points routine needs the enemy-kill/scoring path (award value per object type);
alternatively the respawn re-init bodies (C3A6/77C5/99BF at the 9773 else-branch) are a more bounded next
target.

## 2026-07-04 - CAPSTONE: the top-level mode machine as an explicit native graph (APP_MODE_GRAPH)

Folded the whole session's mode-machine recovery into ONE explicit structure: ``native_app.APP_MODE_GRAPH``
-- a node-per-mode graph (``AppMode``/``ModeEdge``) of the top-level control flow, each node + edge tagged
native/gap so the recovered-vs-unknown boundary is machine-readable. Nodes: boot -> title_menu ->
{attract, new_game} ; new_game(96E0) -> level_setup(971A) -> level_play(97B2) ->
{level_end(9734)->level_setup, death(9908), game_over(9902)->death} ; death -> {game_over_seq(2358==0xFFFF),
respawn->level_play} ; game_over_seq(98EB) -> new_game (restart). Test pins well-formedness (no dangling
edges, valid statuses) + the grounded native spine; gap nodes/edges surface in ``describe_gaps()``
(``mode.*``).

Also investigated the outer front-end->game entry: ``96E0`` is reached by fall-through from a video-init
block (``96BC..96DD``) and directly only from game-over restart (``98FF``); NO E8/E9 ref lands in
``9680..96E0`` from the front-end, so the first-start entry is a longer fall-through chain from above
``9680`` (or an indirect) -- left as the marked ``title_menu -> new_game`` GAP edge rather than
rabbit-holed. This is the honest boundary.

**Structure-first status:** the top-level game LOOP + mode/state transitions are now an explicit native
graph with clear fail-loud gaps -- the core of the user's structure-first mandate. The remaining spine
gaps are all edge-of-graph: the boot->title->game FIRST-start wiring, the attract-exit destination, the
98EB game-over tail, and the respawn re-init bodies. NEXT candidates: the score subsystem (2314..2317,
zeroed at session start -- find the increment path) or the respawn re-init routines (C3A6/77C5/99BF).

## 2026-07-04 - Mode spine: found the new-game/session-start init (96E0/96EE) -- top of the mode machine

Located the top of the game-session mode machine. ``1010:96E0`` is the NEW-GAME entry (reached from the
title/menu on "start" AND from the game-over tail ``98EB -> jmp 96E0`` to restart). Its DATA init
(``96EE..9715``, a pure mov block after the ``96E0..96EB`` video/palette glue) is recovered as
``frame_loop.new_game_session_init_96ee``: ``DS:2356=0`` (planet 0), ``DS:2358=3`` (**lives := 3** --
confirms 2358 is the lives/continue counter, matching the death decrement 3->2->..->0xFFFF), ``235A=0``,
``A342=0`` (clears the game-over flag), and the four score bytes ``2314..2317=0``. It flows into the
``971A`` new-game setup (NEW_GAME_SETUP_STAGES). Byte-exact AND complete vs the VM (6 cells, no other
DGROUP writes -- ``verify_native_new_game_session_init``).

**The session mode-graph is now grounded end-to-end:** title/menu -(start)-> 96E0 (session init:
lives=3, planet=0, score=0) -> 971A setup -> per-level loop (scene video config + 97B2) -> exits
(detect_gameplay_transition) -> {level_end -> 9744 next planet, death/game_over -> 2358 lives counter ->
9773: 2358==0xFFFF -> game-over 98EB -> jmp 96E0 (restart), else respawn re-init -> gameplay}. Remaining
GAPs (fail-loud): the OUTER title/menu <-> attract(D007) <-> 96E0 wiring (the boot-to-session selector),
the 98EB game-over presentation tail, and the respawn re-init routine bodies. NEXT: the title/attract ->
96E0 entry edge (how "start game" is reached from the front-end/attract).

## 2026-07-04 - Mode edges: recovered the gameplay-exit targets (level-end / death / game-over) + lives counter

Made the mode-transition EDGES out of the 97B2 gameplay loop explicit -- disassembled the three
gameplay-exit targets ``detect_gameplay_transition`` selects (native_app.GAMEPLAY_EXIT_TARGETS):

* **level_end (9734, flag A344)** = NATIVE: a story branch (2356==0) then CONVERGES at the recovered
  9744 level-advance -> re-enters the level loop at the next planet.
* **game_over (9902, flag A342)** = forces the ``DS:2358`` lives/continue counter to 0, then falls into
  the death handler.
* **death (9908, flag A346)** = re-seeds the object pool (C4DB) + decrements ``DS:2358``.

Recovered the counter update as ``frame_loop.death_continue_counter_update(is_game_over, 2358, 978d)`` --
death decrements the lives counter, the "no-death" flag ``DS:978D`` cancels the loss (net-zero), an
underflow to ``0xFFFF`` is the game-over sentinel, and game-over zeroes it first. Driven-oracle **12/12**
(``verify_native_death_continue_counter``, driving 9908/9902 -> 991A). ``DS:2358`` is thus the
lives/continue counter of the top-level mode machine.

The respawn-vs-game-over branch is also grounded now (``jmp 9773``): ``if DS:2358 == 0xFFFF`` (the lives
underflow sentinel) ``-> jmp 98EB`` (the game-over path); else RESPAWN via a level re-init
(``C3A6``/``77C5``/``99BF``/``6176`` + player record at ``237C`` via ``9BE2`` + ``A940``) back into the
gameplay loop. So the mode graph's death sub-machine is: death/game_over -> ``death_continue_counter_update``
-> ``9773`` -> {``2358==0xFFFF`` -> game-over ``98EB``, else respawn re-init -> gameplay}. Still GAP
(fail-loud): the ``98EB`` game-over tail (return-to-front-end) and the respawn re-init routine bodies.

Recon note for NEXT: ``DS:BEFF`` is NOT the top-level mode spine -- a code-segment scan shows it is
WRITTEN from 80+ sites (``mov byte [BEFF],imm``), i.e. a broadly-set action/event CODE (sound/effect
trigger family), not a single mode selector. The real "top-level mode machine" is the OUTER loop
sequencing boot -> title/menu -> attract (D007) -> new-game -> level-loop -> game-over/front-end; the
next structural step is to locate that outer loop (the caller side that ties front_end <-> D007 <->
gameplay together) rather than a single dispatch variable.

## 2026-07-04 - Structure: recovered the per-planet video/palette dispatch (C565/2356) + a course-correction

Chased the ``1010:C565`` ``jmp cs:[DS:2356*2 + 0xC570]`` dispatch as a candidate for the TOP-LEVEL
game-mode machine. **It is NOT that** -- disassembly shows the six-planet handlers (``4F37``/``4FC3``/
``4F57``) are per-planet VIDEO/PALETTE setup (CGA/Tandy mode port ``0x3D8`` bit 2 + BIOS palette
``int10 AH=0Bh``). So the C570 table is level-load RENDERING config, not the mode spine. Recorded honestly
as ``native_app.PLANET_VIDEO_DISPATCH`` (six planets -> 3 configs, pattern A,B,C,B,A,C) +
``PLANET_VIDEO_HANDLERS``; drive-verified 6/6 (``verify_native_planet_video_dispatch``). Scenes 6+
(``832E``/``BC3E``/...) are distinct special-scene handlers -- a separate GAP, not bounded here.

**Where the REAL top-level mode machine is (next step):** ``DS:2356`` is the planet/scene index, not the
title/attract/menu/game selector. The outer mode machine lives ABOVE the level loop -- it is the
boot -> title/menu (front_end) -> attract (``D007``) -> new-game-setup (``971A``) -> level loop
(scene-dispatch + ``97B2``) -> exit (``detect_gameplay_transition``) graph. That graph, lifted into an
explicit native state machine in ``native_app.py`` with fail-loud edges, is the highest-value structural
target (per the user's structure-first mandate). Next slice: locate the outer mode selector (the caller
side of the front-end <-> attract <-> gameplay transitions) and model it as the mode graph.

## 2026-07-04 - Structure: pinned the object-pool layout the C4DB seed covers (special + effect table)

Investigating how to wire the native level-start into NativeGame surfaced a clean structural fact worth
recording. The C4DB 36-record seed covers EXACTLY the special view-anchor (``DS:0x237C``, record 0, 1
slot) + the effect table (``DS:0x23B4``, records 1..35, 35 slots) -- one contiguous ``0x237C..0x2B24``
block on the ``0x38`` object-record grid. The **gameplay/enemy table (``DS:0x2B5C``) is NOT C4DB-seeded**
-- it sits exactly one stride past the last seeded record (``0x2B24 + 0x38``) and is initialised
elsewhere (per-level). Verified from the real ``DS:0x32CA`` slot table in
``verify_native_c4db_seed_pool_layout`` (5/5 checks) + named constants ``POOL_BASE_SPECIAL/EFFECT/
GAMEPLAY`` + ``POOL_EFFECT_SLOTS``.

This resolves what ``native_new_game_data_setup`` initialises vs leaves (it seeds special+effect, not the
gameplay pool) -- the map the eventual ``NativeGame`` cold-start needs to translate the flat cell-map into
the special/effect/gameplay ObjectPools. NativeGame's pools (special 0x237C, effect 0x23B4, gameplay
0x2B5C) now line up 1:1 with these bases; the gameplay-pool seed is a separate (still-open) piece.

## 2026-07-04 - Bucket F: composed the native new-game DATA setup (9720..9748) + a tight render boundary

Assembled the recovered pieces into the native level-start DATA entry point:
``frame_loop.native_new_game_data_setup(new_level_index, slot_ptr_table)`` = ``apply_new_game_setup_c4db``
(C4DB object-pool seed + control reset) + the ``9723`` counter init (A95A=3, A95C=0x18) + the advanced
level index (DS:2356; caller advances via ``menu.advance_level_index_9744``).

**Verified against the WHOLE 9720..9748 range** (``verify_native_new_game_data_setup``): drives the real
range (C4DB -> counter init -> 6176 panel draw -> level advance) and does a full-DGROUP diff. Result:
**266 data cells byte-exact (wrong=0), and the ONLY other DGROUP writes are exactly the 8 documented
render-glue cells** the ``6176`` panel draw touches (``NEW_GAME_SETUP_RENDER_CELLS`` = 215E/2160/2370/
2372/9682/968A/9696/969E) -- boundary tight (all 8 change, none unmodelled). So the data model misses no
game-data write; the render bookkeeping is cleanly separated into the presentation layer (fail-loud: not
modelled here). This is the single native call a cold level-start uses to build its initial game state.

Bucket-F level-start DATA is now native end-to-end (object seed + control reset + counters + level
index, all byte-exact vs the VM). Remaining Bucket F: the render/presentation glue (5C9A/6176 -- host),
the player-spawn/starfield init (needs a level-load capture), and calling this from a NativeGame
cold-start.

## 2026-07-04 - Skeleton: added NEW_GAME_SETUP_STAGES (the 971A/9734 -> 9744 -> 97B2 bridge map)

Folded the recovered front-end->gameplay bridge into the skeleton as ``native_app.NEW_GAME_SETUP_STAGES``
-- the machine-readable map of the new-game/level-start setup, mirroring ``GAMEPLAY_FRAME_STAGES`` (the
97B2 map). Documents the CONVERGENT structure honestly: TWO entry points meet at the level-advance --
``971A`` (NEW GAME: D390/5C9A/C4DB/counter-init/6176 then ``jmp 9744``) and ``9734`` (LEVEL-END
TRANSITION, the A344 scripted-exit target of ``detect_gameplay_transition``: the ``2356==0`` level-0
story branch, then falls into 9744) -- then the converged per-level setup tail into 97B2.

Each step is tagged native/host/gap from THIS session's disassembly only (conservative, after the A47C
mislabel lesson): ``new_game_setup`` (C4DB) = NATIVE (apply_new_game_setup_c4db, complete);
``level_advance`` (9744) = NATIVE; ``screen_load`` (5C9A) / ``panel_draw`` (6176) = HOST presentation;
``level_select`` (D390) / ``level0_intro`` (9844) / ``setup_tail`` (9755..97B2) = GAP. The GAP entries
now surface in ``describe_gaps()`` (prefixed ``new_game_setup.``), and the Bucket-F gap line is updated
to note C4DB + level-advance are native, with the player-spawn/starfield init + native-cold-level-start
wiring as the remaining work. Tests pin the flow order + the native/host/gap tags.

## 2026-07-04 - Bucket F: COMPOSED the whole C4DB new-game setup + proved it COMPLETE (segment diff)

Composed the two recovered C4DB halves into one native entry point: ``frame_loop.apply_new_game_setup_
c4db(slot_ptr_table)`` = ``object_pool_seed_c4db`` (the 36-record seed) merged with
``level_start_control_reset_c51d`` (the control reset), a flat ``{DGROUP offset: value}`` write-map
(SS==DS on this build, so records + control cells share one segment; 263 cells, no collision).

**Verified CORRECT *and* COMPLETE** (``verify_native_new_game_setup_c4db``): drives the whole C4DB
(C4DB..C55F) and does a full 64K DGROUP before/after diff -- every changed word is one of the 263
predicted cells, none missed. The completeness diff caught a real subtlety first: with SS==DS the STACK
lives in DGROUP, so the routine's push/pop/call churns stack memory (~SP 0xA278, mirrors ``cx``); the
probe now excludes the ``[min_sp, sp_entry)`` stack window, after which C4DB writes EXACTLY the 263 game
cells (its only other write is the out-of-DGROUP ``CS:C3A2`` framebuffer accumulator). This is a genuine
completeness proof, not just per-cell correctness.

The whole C4DB new-game setup is now a single verified native call. NEXT Bucket-F step: wire
``apply_new_game_setup_c4db`` + ``advance_level_index_9744`` into a native cold level-start in
NativeGame (the surrounding 971A integration), plus the player-spawn/starfield init (still needs a
level-load capture).

## 2026-07-04 - Bucket F: recovered the C4DB object-pool SEED (36 records x 7 fields, byte-exact)

Took the integration the last pass pointed to -- the ``C4DB`` object-pool seed loop (``C4E5..C51B``),
the level-start object state (Bucket F). Recovered ``frame_loop.object_pool_seed_c4db(slot_ptr_table)``:
for each of the 36 slots ``cx = 0x24..1`` it reads the object-record offset from the ``DS:0x32CA`` word
table and stamps a fixed template (``+0x00``/``+0x06``/``+0x18``/``+0x24``/``+0x2E`` = 0, ``+0x0A`` = 1)
plus a per-slot framebuffer back-buffer pointer at ``+0x0E`` stepping ``0x3314, +0x280, ...`` in
processing order (the ``CS:C3A2`` accumulator). Modelled as pure LOGIC taking the pointer table as input
(not hard-coding the data table). Driven-oracle **36 records x 7 fields = 252 checks, 0 fails**
(``verify_native_object_pool_seed_c4db``).

Structure confirmed: the pool is 36 records at ``DS:0x237C`` + ``i*0x38`` (the known object stride); the
``DS:0x32CA`` table maps processing slot ``cx`` -> record (``0x237C`` + ``(cx mod 0x24)*0x38`` on this
build); each object owns a distinct ``0x280``-strided framebuffer save area. This + the earlier
``level_start_control_reset_c51d`` together cover the whole C4DB new-game setup (seed loop + control
reset). Remaining Bucket-F level-start work is the surrounding integration (wiring these into a native
cold level-start in NativeGame), plus the player-spawn/starfield init still needing a level-load capture.

## 2026-07-04 - Mapped the 971A new-game/level-start bridge; recovered the six-planet level advance (9744)

Turned to the front-end->gameplay bridge (the largest remaining structural gap) and disassembled the
``971A..97B2`` new-game/level-start setup. Findings (structure-first map growth):
- **``971A`` is the level-start setup** that chains straight into ``97B2`` (the gameplay frame stages):
  calls D390/5C9A/C4DB, **initializes ``DS:A95A := 3`` and ``DS:A95C := 0x18``** (9723/9729), calls
  6176, then flows through the level-advance block into the per-frame setup (5145/5BCA/0B3E/0E9C/60AC/
  C3A6/77C5/99BF/9BE2/**A940**/C57C/B5A9/5F43).
- **``DS:2356`` is the level index (six planets)**; ``9744`` advances it: ``inc [2356]; wrap at 6``.
  Recovered as ``systems/menu.advance_level_index_9744`` (cycle ``0->1->2->3->4->5->0``), driven-oracle
  9/9 (``verify_native_level_advance_9744``). This is the step taken on the SCRIPTED level-end exit
  (``9734``, ``detect_gameplay_transition``'s SCRIPTED target) and by 971A.
- **Independent confirmation of the A47C-rename:** ``A95A``/``A95C`` are INITIALIZED to 3/0x18 by the
  new-game setup (9723/9729) -- they are general new-game counters, exactly as the trace implied, NOT
  death state. This vindicates renaming the ``step_death_*`` A47C functions last pass.

**Follow-up (same pass): the bridge is glue, not decision logic.** Disassembled 971A's children --
``5C9A`` is a full-screen VGA plane blit (rep movsb + 03CE reg writes), ``9844`` is the level-0 story
splash (far-call text + fire-wait), ``C4DB`` is object-pool + control-cell init. None carry pure
decision content; the front-end->gameplay bridge is presentation/init/wait glue, so the clean-leaf
model is largely exhausted here too (as on the gameplay side). Recovered the one cleanly-bounded piece:
``level_start_control_reset_c51d`` (``C51D..C559``) -- the level-start reset of the frame-control cells
(the four delayed-coordinate slots A966/A968/A96A/A96C + neighbours -> 0xFFFF empty-sentinel; A958/A95E/
A960/2384 -> 0), driven-oracle 11/11 byte-exact. Ties into the earlier ``frame_axis_dispatch_offset``
(which counts those slots). **The remaining bridge substance is INTEGRATION-shaped, not leaves:** the
C4DB 36-slot object-record seed (per-slot framebuffer pointer stepping by 0x280 via the DS:3002 pointer
table) is the Bucket-F object-pool seed; the screen blits + story splash are presentation. Next real
progress needs a native-runtime integration (grow NativeGame/level-start), not more leaf extraction.

## 2026-07-04 - CONFIRMED via trace + renamed the A47C-script functions (death->A47C, evidence closed)

**The decisive trace resolved it.** Traced the player_death demo forward recording every ``DS:A47C``
change + every ``1010:A6B9`` (arm) execution: across the ENTIRE run up to the death frame (my 97B2
frame-counter reached 770; the harness reached the death frame 1805 where it hit the known death-frame
budget limit at ``1010:32DB``) -- **A47C stayed 0 the whole time (nonzero frames = 0) and the A680 arm
NEVER fired (0 hits)**. So the A47C scripted-input subsystem is completely dormant through player death:
it is definitively NOT the death mechanism. (Player death = the separate ``9AFF`` +08 anchor counter,
already grounded.) The A47C script is a scroll-position-triggered scripted event that simply never
occurs in this demo.

**Rename pass (the mislabel is now confirmed, not just suspected).** Renamed the three functions whose
A47C linkage I directly established by composition -- the ``A47C==3`` handler + its two sub-steps:
``step_death_handler_9a16`` -> ``step_a47c_handler_9a16``, ``step_game_over_arm_9db9`` ->
``step_a47c_arm_9db9``, ``step_death_seq_9dea`` -> ``step_a47c_seq_9dea`` (+ their probe files
``verify_native_a47c_{handler_9a16,arm_9db9,seq_9dea}.py``), with docstrings stating the "death" label
was UNVERIFIED and why. Chose NEUTRAL A47C-script names, NOT another unproven label ("boss"). All three
probes still PASS byte-exact. GROUNDED death names KEPT as-is (``step_death_tail_9aff``,
``detect_gameplay_transition`` -- demo-witnessed). The countdown leaves (``step_death_countdown_9e69``,
``step_game_over_countdown_9ee4``, ``step_a95c_difficulty_countdown_9e43``) are NOT yet renamed -- their
exact A47C-reachability isn't established, so renaming them would be a fresh guess; deferred with a
loop_blocker note until a trace links them.

## 2026-07-04 - CORRECTION: the "death-script" A47C subsystem is MISLABELED -- it is NOT player death

**Honest walk-back of this session's "death" naming.** While wiring the A680 arm toward play_native I
checked its real trigger and found the whole A47C-script "death" attribution is UNVERIFIED and the
evidence contradicts it. Keeping the record straight (fail loud, never overclaim):

- The A680 ARM (``a47c_script_arms_a680``, was ``death_script_arms_a680``) fires ``A47C=1`` **iff**
  ``A480==0 AND 234E==1 AND 2350==0x0EA0`` -- driven-oracle 40/40, still byte-exact. BUT ``234E``/``2350``
  are the world-SCROLL cursor (origin_x/row_base, per play_native), so the arm fires at a specific
  scroll POSITION and then spawns an entity (``62AA``+``7524`` at A6BF). That is the shape of a scripted
  LEVEL/BOSS event, not collision-death.
- **Demo-seed evidence (sampled 6 demos):** ``A47C == 0`` at EVERY seed incl. player_death AND L6_boss;
  the supposed "death countdown" cells ``A95A==0x0003`` and ``A97A``=nonzero hold the SAME resting
  values in ordinary L1/L2 gameplay. So A95A/A95C/A97A are general per-frame counters, not death state.
- **What IS grounded as death:** the SEPARATE ``9AFF`` ``+08`` anchor counter --
  ``step_death_tail_9aff`` + ``detect_gameplay_transition`` -- which is demo-witnessed on player_death
  (4 real DEATH frames) and does NOT touch A47C. That labeling stands.

**Action taken this pass:** renamed the freshest overclaim (``death_script_arms_a680`` ->
``a47c_script_arms_a680``, ``DEATH_ARM_GATE_2350`` -> ``A47C_ARM_GATE_2350``, probe ->
``verify_native_a47c_arm_a680.py``) and rewrote its docstring to state the trigger semantics are
unverified. The OLDER A47C-script functions (``step_death_handler_9a16``, ``step_death_countdown_9e69``,
``step_death_seq_9dea``, ``step_game_over_arm_9db9``, ``step_scripted_move_counters_9a3e``,
``scripted_input_prologue_99f6``) remain byte-exact and correct AS CODE, but their "death"/"game-over"
NAMES are provisional -- a dedicated rename pass should follow once the decisive trace lands (logged in
loop_blockers.md). NOT renamed en masse this pass to avoid a large risky churn mid-loop.

**Decisive experiment (for a future pass, see loop_blockers):** trace player_death to the actual death
FRAME (~1805) OR any demo forward and record when/if A47C ever goes nonzero + whether A6B9 fires -- that
determines what the A47C script is (boss/cutscene auto-movement vs death). Cheap per-instruction Python
tracing over ~1800 frames timed out; needs a lighter anchor-gated trace or a purpose-recorded demo.

## 2026-07-04 - 9A3E scripted-move counter head recovered; the other death-script steps are spawner islands

Recovered ``systems/frame_loop.step_scripted_move_counters_9a3e`` -- the A47C==2 death-script step's
HEAD (increments A39C / decrements A39A, caps chosen by ``2384``). Driven-oracle 7/7.

**Death-script structure fully mapped now (the 99F6 A47C handlers):** the death sequence steps through
A47C = 1 -> 2 -> 3. **A47C==3 (9A16) = the countdown handler -- COMPOSED native (prior pass).**
**A47C==1/2 (9A78/9A3E) = the death-ENTITY spawn + coordinate-table movement** -- these call the 7524
allocator + stamp a boss/death object (logic 0x52, sprite 0xF at 0x20/0x58) and drive scripted input
(98BE) from a coordinate table (A35C/A358) vs the view anchor DS:237E -- a SPAWNER island, only the
counter head (9A3E) is a clean leaf.

**Honest state / recommendation for the next runs:** the death/scripted-input island's CLEAN pieces are
now done (the countdown leaves + handler, the dispatch, the 9A3E counter head). The rest -- the
death-entity spawn (7524 + stamp + coord-table movement in 9A78/9A3E) and the ARM (the upstream
collision that sets A47C=1 to start the script) -- are SPAWNER/UPSTREAM islands. Combined with the HUD
fold (needs a level-load capture) and the 35-tick forward-carry wall (A067 spawn drift), the frontier
is now THREE big integrations, each needing a dedicated capture/trace + multi-pass focus, not more
per-iteration clean leaves. The per-slice loop has recovered the clean frontier (pure ~32.0%, ~207
rules); the highest-value next move is to pick ONE integration and drive it deliberately.

## 2026-07-04 - COMPOSED the first native death handler (99F6 9A16, A47C==3)

First COMPOSITION (not just a leaf): ``systems/frame_loop.step_death_handler_9a16`` builds the whole
``1010:9A16`` scripted-input death handler (the A47C==3 script step) from the recovered sub-steps --
NO VM/render calls: set scripted input ``98BE := 8``, run ``step_game_over_arm_9db9`` then
``step_death_seq_9dea``, then advance the script ``inc A47C`` only when (post sub-steps) ``A97A == 0x58``
AND ``A95A == 3`` AND ``A95C == 0x18``. Driven-oracle ``verify_native_death_handler_9a16.py`` (drives
the original handler, which itself calls 9DB9+9DEA) **24/24, 0 fails**.

So the 99F6 death-script step for A47C==3 is now fully native. Toward native death FIRING, remaining:
compose the other A47C handlers (9A3E==2, 9A78==1) the same way, then the ARM (the upstream collision
that sets A47C into the death-script range) + running 99F6 in play_native. The composition pattern is
proven; the render calls that blocked earlier composition attempts are NOT in these death handlers.

## 2026-07-04 - 9DB9 game-over ARM recovered; HUD-fold needs a level-load capture

Recovered ``systems/frame_loop.step_game_over_arm_9db9`` (the 99F6-death-handler ARM sub-step): no-op
when ``A97A == 0x58`` or ``A97C == 1``; while ``2384 < 3`` it arms ``A97C := 1`` (+ ``BEFF := 0x0D``
when ``BDAC != 1`` AND ``98C0 != 0``); ``2384 >= 3`` leaves A97C at 0. Driven-oracle
``verify_native_game_over_arm_9db9.py`` **32/32 exhaustive combos, 0 fails**. So the 99F6 death handler's
sub-steps are now largely native (the A95A/A95C/A97A countdowns + 9DEA advance + 9DB9 arm). Metrics:
pure ~31.9% (203 pure rules).

**HUD-fold blocker (recorded so the next run doesn't re-scout):** the full-panel draw is spread across
MANY ``5A6C`` cell-blit callers (5550/612a/62xx/86xx/98xx/cd4f/cf69/d0xx/d2xx/d3xx/d4xx) + boot
(``0x758`` calls 859E); it is NOT a single clean routine, and no current demo captures a LEVEL-LOAD
(the gameplay snapshots are mid-level, HUD already drawn; the cold-start demos stop at attract). To
recover the HUD base panel: capture a cold-start-through-to-level-load demo, trace the B800 HUD-region
writes there to isolate the panel cell-list draw, then compose via the recovered ``paste_panel_cell``.

**Loop-strategy note:** the clean single-leaf frontier is now genuinely worked to the granular tail
(these death-handler sub-steps). The three remaining HIGH-VALUE targets are all multi-iteration
INTEGRATIONS needing focused investigation, not per-iteration clean slices: (1) compose the 99F6 death
handler -> native death firing (needs the arm/upstream + the render calls); (2) the HUD fold (needs the
level-load capture above); (3) the 35-tick forward-carry wall (A067 spawn drift). A future run should
pick ONE and drive it across passes with a dedicated capture/trace.

Recovered another 99F6-death-handler sub-step: ``systems/frame_loop.step_death_seq_9dea`` -- while
``A95C != 0x18`` increment it; at ``A95C == 0x18`` with ``A95A != 3`` advance the anchor (inc A95A,
A95C:=0, BEFF:=0x1C when 98C0!=0); ``A95A == 3`` is the no-op. Driven-oracle
``verify_native_death_seq_9dea.py`` 6/6 (the oracle again pinned a jnz polarity I'd mis-read).

**HUD base-panel grounding (for the HUD-fold integration):** the HUD is entirely CELL-based
(``paste_panel_cell`` from the PANEL asset ``CS:[95B4]`` via the recovered 306F copy). ``859E`` +
``8517``/``852B`` build/draw only the FOUR status cells (WEAPON/MISSILES/GADGETS/UPGRADES descriptors
at DS:9682/968C/9696/96A0); the base panel (frame/scope/gauges/radar -- ~80% of the HUD px) is drawn
by OTHER paste_panel_cell calls at level-load that are NOT yet located. NEXT for the HUD fold: find the
level-load routine that blits the full-panel cell list (grep/trace the 306F/5A6C callers at level
start), then compose it via the already-recovered paste_panel_cell + decode to index space.

## 2026-07-04 - Death machine IS the 99F6 scripted-input sequence; its dispatch entry recovered

**Key finding:** the death state machine ``9E40..9EFC`` has NO near-call callers -- it's a JUMP-TABLE
target of the ``1010:99F6`` scripted-input dispatch (``jmp cs:[A47C*2 + 9A0C]``). So the whole death /
end-of-life sequence is a set of **A47C-driven scripted-input handlers**, not a standalone routine.
This reframes native death firing: it needs the ``99F6`` system (the A47C script that ARMs + drives
the death), not just the countdown leaves -- a multi-iteration integration. Its ARM is upstream
(the collision that sets the death-script A47C).

**Dispatch ENTRY recovered:** ``systems/frame_loop.scripted_input_prologue_99f6`` -- 99F6 clears bit 0
of ``DS:2380`` + the input byte ``DS:98BE``, then dispatches by ``A47C*2`` through the ``CS:9A0C`` code
table.  Driven-oracle verified (``verify_native_scripted_input_dispatch.py``, 5/5) -- the FIRST leaf of
the scripted-input system (which unblocks, eventually, forward-carry on A47C != 0 ticks + native death
firing + boss scripts).

**Frontier note (consolidated):** the clean single-leaf frame-stage / behavior recoveries are
EXHAUSTED -- every remaining gameplay behavior that isn't native (0x21/B556, 0x2a/8676, 0x68, ...) is a
mode-dependent (DS:2356) DISPATCHER/SPAWNER island, and the death path is the 99F6 script system. The
remaining work is BIG INTEGRATIONS: (a) the 99F6 scripted-input handlers -> native death firing;
(b) the HUD base-panel fold (~80% un-recovered); (c) the 35-tick forward-carry wall (A067 spawn drift).
Future runs: pick one integration and drive it across passes (recover its leaves bottom-up), not more
clean single slices.

## 2026-07-04 - GROUNDED the death-firing island (the collision/end-of-life state machine 9E40..9EFC)

Traced the death signals on ``demo_play_tandy_player_death`` (write-watcher on the fixed game DS,
``scratchpad/trace_death.py``) and disassembled the setters -- the death-firing UPSTREAM (what the
now-recovered detector/9AFF-tail need to actually FIRE natively) is a bounded state machine at
**1010:9E40..9EFC**, run once per frame:

- **``A95A`` every-other-frame countdown = STAGE 1 of death.** Entry ``9E69``: gated on ``DS:A47C``
  (``cmp A47C,1`` -> ret when ==1) and ``DS:2384`` (``cmp 2384,3`` -> ret when >= 3); when armed it
  toggles ``DS:A362`` (``inc; and 1``) and on the ``A362==0`` frames ``dec DS:A95A``. When A95A wraps
  ``0 -> FFFF`` (``9E98``, the traced setter) the anchor is "lost" -> the 9AFF tail becomes reachable.
- **STAGE 2** is the already-recovered ``9AFF`` tail (``2384`` counts up to ``0x0F`` -> the DEATH/
  GAME_OVER exit). So death = A95A counts down to FFFF, THEN 2384 counts up to 0x0F.
- Also in the block: the ``A95C`` difficulty-scaled countdown (``9E43..9E61``, dec 1/2/3 by ``DS:BEDC``),
  the ``A97A`` game-over countdown (``9EE4..9EEC`` -> the traced ``C495``/``A97A->0`` game-over setter),
  and per-frame ``61DC``/``511F`` (HUD counters + video) calls. Cells touched: A95A/A95C/A97A/2384/
  A362/BEFF/BEDC/98C0/9791/978C.

This is a multi-iteration ISLAND (recover the leaves bottom-up). NOTE the arm-condition polarity
(JNZ/JB) must be pinned by a demo witness / driven oracle, not manual disasm reading (the A940 attract
oracle already caught one such mis-read this session). Once native, the play_native exit boundary
(already wired) FIRES on a real native death.

**STAGE 1 LEAF RECOVERED this pass:** ``systems/frame_loop.step_death_countdown_9e69`` -- the A95A
anchor-loss countdown (gated off when ``A47C == 1`` or ``2384 >= 3``; else toggle A362, decrement A95A
on the A362==0 frames; ``A95A: 0 -> FFFF`` = anchor lost). **Driven-oracle verified** (force synthetic
``(A47C,2384,A362,A95A)``, drive the original 9E69 to a ret / 9E9C, compare A362+A95A):
``verify_native_death_countdown.py`` **8/8 branches, 0 fails** (the oracle pinned the arm polarity).
**A95C difficulty countdown leaf RECOVERED too:** ``systems/frame_loop.step_a95c_difficulty_countdown_9e43``
-- decrements A95C by 1/2/3 per frame for ``DS:BEDC`` == 0 / == 1 / >= 2, reloading to ``0x18`` at 0.
Driven-oracle ``verify_native_a95c_countdown.py`` 10/10, 0 fails (the oracle pinned that the reload
``mov A95C,0x18`` is at 9E63, so the routine's output is 0x18 -- stop after it at 9E69, not at 9E63).

So ALL THREE death-island countdowns are now native + verified (A95A anchor-loss 9E69, A95C difficulty
9E43, A97A game-over 9EE4) plus the 9AFF tail. Remaining: compose the whole 9E40 state machine
(sequence the countdowns + the 61DC/511F calls + the entry gate) and thread the death cells into
NativeGameState, so play_native's wired exit boundary fires on a real native death.

**A97A game-over countdown leaf RECOVERED (next pass):** ``systems/frame_loop.step_game_over_countdown_9ee4``
-- ``A97A == 0`` no-ops; else decrement, and reaching 0 is the game-over trigger (the ``A97A == 0`` the
GAME_OVER verdict keys on). **Driven-oracle verified** ``verify_native_a97a_game_over.py`` 5/5, 0 fails.
The oracle again earned its keep: it caught that lindis mis-displayed the ``9EF0 jz`` target (dec-to-0
takes the ``9EF5`` game-over-final path with 2384/BEFF, dec-to-nonzero falls to ``9EF2``) -- pin branch
targets by oracle, not by eye.

## 2026-07-04 - A940 attract-mode middle recovered (driven-oracle) -> A940 stage now complete both paths

Recovered A940's ``DS:2356 == 5`` attract-mode counter block (the sub-gap left by the gameplay-path
A940 slice): ``systems/frame_loop.step_a940_attract_middle`` (the 98A2/98A4/98AA negate + the 98A5
countdown / 98A3 reset-or-inc) + ``a940_speed_bucket`` (the A47E reload cascade 0x0A/06/04/01).

**Verified by DRIVEN ORACLE** (``verify_native_a940_attract.py``): no gameplay demo runs 97B2/A940 with
2356==5, so the probe forces ``DS:2356=5`` + synthetic ``(98A2,98AA,98A5,98A3,A47E)`` and drives the
ORIGINAL A940 to its A9E0 exit, comparing all 5 cells -- **8/8 branch combos, 0 fails.** The oracle
earned its keep: it caught that the LIFTED game_state attract branch mis-handles ``98A5 > 1`` (it
should DECREMENT 98A5 + RESET 98A3 to 0 via A9B3, not overwrite/inc) -- a latent bug that no gameplay
demo exercises (logged in loop_blockers). The pure rule is correct.

Frame-controller scouting this pass (recorded so the next run doesn't re-scout): the remaining
gameplay frontier is all ISLANDS -- the object behaviors that AREN'T native (0x2a/8676 etc.) are
mode-dependent SPAWNERS (allocator + child-spawn), 99F6 is a scripted-input jump table, the HUD base
panel (frame/scope/gauges/radar) is ~80% un-recovered (859E draws only the 4 buttons, 2298 of 11391
HUD px), and the death-firing path needs the collision-death upstream. Clean single-leaf frame stages
are done.

## 2026-07-04 - Native 9AFF death-tail STAGE (the stateful counter increment) demo-witnessed on death

Recovered the STATEFUL half of the death exit: ``systems/frame_loop.step_death_tail_9aff(a95a, a97a,
v2326, anchor_counter) -> DeathTailStep(anchor_counter, transition, deactivate_anchor)`` -- reached
only when the anchor state is absent (``A95A==FFFF or A97A==0``, ``death_tail_reached_9aff``); in the
dying mode (``2326==3``) it INCREMENTS the anchor slot's ``+08`` death counter and fires the exit at
``0x0F`` (deactivating the anchor). (``detect_gameplay_transition`` is the stateless verdict given the
already-incremented counter; this owns the increment the detector's input depended on.)

**Demo-witnessed** by ``verify_native_death_tail.py`` on the player_death run-up (1790 frames):
**checked=770, reached=48 (counter counting up), fired=4 (real DEATH exits), 0 fails** -- the counter
transition, the exit verdict, AND the anchor deactivation all reproduce the live 9B2E byte-exact.
Unit tests +1.

So the death exit is now fully recovered end to end: the reached-gate + the stateful counter + the
verdict, all demo-witnessed. Wiring it to actually FIRE from native gameplay still needs the upstream
death-trigger (what sets A95A=FFFF/A97A=0/2326=3 -- the collision-death island) native; that + the
NativeFrameGlobals carrier are the remaining pieces for a self-detecting native death.

## 2026-07-04 - Native A940 frame-state-update stage composed + produced-vs-VM verified (gameplay path)

Closed the skeleton's ``frame_state_update`` gap (GAP -> NATIVE): ``systems/frame_loop
.frame_state_update_a940`` composes the two already-pure A940 halves -- the saturating accumulator
shift (A8CE++, A8C8/A8CC -> A8C6/A8CA, A8CC:=0) + the scan-entry fork (98A8/98A9 edge, A8C2 boss fork)
-- into the whole native gameplay A940 stage (``DS:2356 != 5``). The attract-mode middle (2356 == 5:
the 98A2/98A4/98A5 counters + 1F8F:081D demo tick) is a declared sub-gap that FAILS LOUD.

**Verified byte-exact produced-vs-VM** by ``verify_native_a940.py`` (drive the live A940 on a gameplay
demo, compare the composer's output to the exit cells): **L3 checked=750, fails=0.** The probe also
settled a doc bug empirically: A940 does NOT reset ``DS:A8C8`` (only A8CC) -- exit A8C8 == entry A8C8
across the corpus; corrected ``FrameAccumulatorShiftOutcome``'s docstring. Unit tests +2.

NOTE (same as the transition stage): the composer is verified but its output cells aren't threaded
into the native loop yet -- wiring needs a ``NativeFrameGlobals`` carrier (the recurring
"frame-controller globals not in NativeGameState" plumbing; the next foundational slice that unblocks
A940 + the transition inputs + coord-ring all at once).

## 2026-07-04 - Gameplay-exit boundary WIRED into play_native (fail-loud level-end)

Wired the recovered `detect_gameplay_transition` into the native standalone loop: each frame
`scripts/play_native.py` now runs the gameplay-exit check and raises `RecoveryGap` (holds the frame,
reports) if a death / game-over / scripted level-end fires -- the native runtime stops fail-loud
instead of running blindly past the unrecovered `9734/9902/9908` continuations. `_SeededStart` carries
the trigger cells (A47C/A95A/A97A/2326) read from the snapshot; the anchor +08 death counter is live
(special_pool slot 0). Smoke: on a normal L3 capture (A95A=0x3, A97A=0x57, A47C=0, 2326=1 -> anchor
present) the check returns None for 40+ ticks -- no false exit-fire.

**PARTIAL / honest gap (native_app transition_flags now `GAP`, not `unmonitored`):** the boundary is
wired + fail-loud, but a REAL death isn't yet DETECTED from native gameplay because the native loop
doesn't run the stages that set A95A=FFFF / A97A=0 / 2326=3 (those are the death trigger) -- the
trigger cells are seeded-static. Making the native loop actually reach a death (run the upstream
death-state + the 9AFF stage that increments the counter) is the next slice; this one closes the
"boundary exists in the loop" half fail-loud.

## 2026-07-04 - Gameplay-exit DETECTOR recovered + demo-witnessed against real DEATH events

Composed the two recovered 9B2E exit rules into the whole-frame decision the native loop needs:
``systems/frame_loop.detect_gameplay_transition(a47c, a95a, a97a, v2326, anchor_counter_after_inc) ->
GameplayTransition | None`` (domain: ``GameplayExit`` enum = SCRIPTED ``9734`` / GAME_OVER ``9902`` /
DEATH ``9908``, in the ``97B2`` flag priority A344 > A342 > A346). Pure; composes
``scripted_transition_fires_9b2e`` + ``death_tail_transition_9aff`` + the ``9AFF``-reached gate
(``A95A==FFFF or A97A==0``).

**Witnessed against the live 97B2 verdict** by new probe ``verify_native_gameplay_transition.py``: it
replays a gameplay demo and, at ``1010:97CE`` (post-9B2E, flags hold the frame verdict), compares the
detector (fed the same DS cells) to the flags 97B2 actually tests. On ``player_death`` (run-up to frame
1790): **770 frames checked, 0 fails, and it caught 4 real DEATH-exit frames** -- so the positive path
is grounded on actual death events, not only unit tests. (Harness note in ``loop_blockers.md``: the
death FRAME itself exceeds the frame-verifier per-frame budget at ~1805, so the replay is capped just
before it; the exit fires in the run-up window regardless.) Unit tests in ``test_frame_loop.py``.

``native_app`` transition-flags stage note updated: DECISION recovered+witnessed; still UNMONITORED
because the native model doesn't carry the inputs nor run the 9AFF stage that increments the death
counter -- **that native 9AFF stage (+ threading A47C/A95A/A97A/2326 into NativeGameState) is the next
slice**, after which the native loop can end a level fail-loud via this detector.

## 2026-07-04 - Attract scene machine DEMO-WITNESSED (whole scene range + auto-fire); transition-flag semantics identified

**The pure attract rules are now demo-witnessed, full coverage.** New probe
``overkill/probes/verify_native_attract.py`` replays a cold-start demo on the hooks-stripped ref side
and checks every (D016 pre -> D0CA mid -> next D016) triple against ``attract_frame_step``:
- ``demo_cold_start_attract_interrupt_synthetic``: 546 frames, 399 checked, scenes 0x0..0x5, PASS.
- ``demo_cold_start_wait_synthetic``: 1846 frames, **1699 checked, scenes 0x0..0x12 (ALL), auto-fire
  window 0x8..0x12 fully exercised (891 auto-fire transitions), 0 fails -- PASS.**
The probe reports coverage explicitly (scene range + auto-fire count) so a PASS can't overclaim.
Structural telemetry from the replays: in a full title->attract cold-start session, ``97B2``/``9B2E``
NEVER run -- the attract "gameplay" is entirely the ``D007`` loop driving ``A067`` with injected fire.

**Transition-flag semantics found readable in the lifted 9B2E** (``gameplay/frame_orchestration.py``):
``A346``/``A344`` are cleared at 9B2E entry each frame; **A344=1** when scripted-input mode
``DS:A47C == 4`` (a script "end/transition" command -> 97B2 jumps 9734); **A346=1** in the ``9AFF``
death tail (anchor state absent: ``A95A==FFFF`` or ``A97A==0``, with ``DS:2326==3`` and the slot's
``+08`` counter reaching 0x0F -> slot deactivated + ``4DBF``); **A342=1** additionally when
``A97A==0`` (the game-over variant -> 97B2 jumps 9902). **The transition DECISIONS are now pure:**
``systems/frame_loop.py`` gained ``scripted_transition_fires_9b2e`` + ``death_tail_transition_9aff``,
and the lifted 9B2E adapter delegates BOTH with live cross-check assertions (the zero-risk pattern:
registers/flags/memory writes unchanged, the rule grounded on every demo-replay tick). What remains
for a native level-end: thread ``A47C``/``2326``/``A97A`` + the anchor ``+08`` death counter into the
native model so the native loop can consume ``GameplayTransition`` fail-loudly.

## 2026-07-04 - STRUCTURE PIVOT: the native app skeleton + the recovered top-level design

**Direction change (user):** recover the game's HIGH-LEVEL structure first -- game loop, mode/state
transitions, level flow, orchestration -- with explicit fail-loud gaps; fill behavioural details later
via targeted demos. Stop chasing edge-case leaves.

**New top-level structure recovered this pass (disassembly-grounded, D007/D080..D0EF + 97B2..981D):**
- **`1010:D007` is the attract/story SCENE LOOP**, a scene machine over three DS cells: `BE06` =
  scene id (indexes a 6-byte descriptor table at `DS:BE18` -> the `CS:0BE4` panel directory; each
  scene's graphic cell is drawn every frame at cursor (0x1F,0x18) via `D04D`); `BE08` = per-scene
  countdown (dec per frame; at 0 -> reload 0x64 and `BE06++` = auto-advance); `BE0A` = a mod-0x14
  **demo auto-fire cycle** -- on ticks 0F/11/13 it OVERWRITES the input with FIRE (`98BE=10h`) and
  drives `A067` with `BP=237C` (the attract mode literally plays itself). Gate: scenes >= 8 with
  countdown >= 0x14. Exits on real FIRE / any key (`98C3`) / terminal scene `0x13`; scene 0 branches
  to `D160` (not recovered).
- **`1010:97B2` is the gameplay frame loop** with THREE transition flags out of gameplay:
  `A344 -> jmp 9734`, `A342 -> jmp 9902`, `A346 -> jmp 9908` (death/level-end/game-over family;
  setters live in 9B2E's children -- not yet identified). Full stage order pinned in the skeleton.

**New code:**
- `overkill/native_app.py` -- the VM-less application SKELETON: the recovered top-level flow map
  (module docstring = the design doc), `GAMEPLAY_FRAME_STAGES` (the 97B2 call order as a typed,
  machine-readable stage map: native / host / gap / unmonitored per stage), `describe_gaps()`,
  `GameplayFrameSkeleton` (runs the native stages in the ORIGINAL order: present-then-advance) and
  `AttractSequencer` (the D007 machine; NOT wired into play_native -- scene content unrecovered).
- `recovered/domain/gaps.py` -- `RecoveryGap` (fail-loud, greppable) + `UnmonitoredGap` (a declared
  gap whose trigger state the native model cannot even see yet -- e.g. A342/A344/A346).
- `recovered/domain/attract.py` + `recovered/systems/attract.py` -- the pure D007/D04D scene rules
  (gate/auto-fire/countdown/exit), **disassembly-grounded, NOT yet demo-witnessed** (status in the
  module docstring; witness before shipping a visible attract mode).
- `scripts/play_native.py` ticks through `GameplayFrameSkeleton` in the original 97B2 order now.
- Tests: `test_attract.py` (7), `test_native_app.py` (7). VM-free smoke: 30 skeleton ticks, zero
  `dos_re` imports.

**Next structural steps (in this direction):** witness the attract rules on a cold-start demo probe;
identify the A342/A344/A346 setters (the mode-transition semantics -- what ends a level); recover the
`DS:BE18` scene-descriptor table as data (scene -> graphic/story page); model `9734`/`9902`/`9908`
(the transition targets); grow `NativeGameState` to carry the transition flags so the loop can end a
level fail-loudly instead of unmonitored.

## 2026-07-03 - Collapse: 9C01 axis jump-table offset rule extracted to pure frame_loop.py

Extracted the ``1010:9C01`` axis-condition jump-table index rule out of the lifted
``gameplay/game_state.py`` into ``recovered/systems/frame_loop.py`` as ``frame_axis_dispatch_offset``:
the frame controller counts how many of its four delayed-coordinate slots are live (two feed ``AH`` =
``DS:A966``/``A96A``, two feed ``AL`` = ``DS:A968``/``A96C``, each ``0..2``), then indexes the
``CS:9C70`` word table by ``((al + 3*ah) & 0xFF) << 1`` (``0..16``).  ZERO-RISK form: the adapter
keeps the exact BL/SHL arithmetic (registers/flags unchanged) and now cross-checks it against the
pure rule on every live 9C01 tick (grounds the rule against the VM without changing behaviour). Unit
test in ``test_frame_loop.py`` (the 9 ah/al combinations). Byte-exact preserved; suite green.

## 2026-07-03 - Collapse: coord-ring ADVANCE STAGE (gate + whole-stage) pure; leaf well confirmed dry

Extended ``systems/coord_ring.py`` to the whole ``1010:9CF1`` advance stage: ``coord_ring_advance_gate``
(the ring advances iff the low input nibble ``DS:98BE & 0x0F`` is non-zero **or** the axis-response
flag ``DS:A360`` is non-zero) + ``advance_coord_ring_cursors`` (the 4-cursor lockstep advance, a native
runnable form). The ``run_frame_coord_ring_advance_9cf1`` adapter now delegates the gate (keeping the
A360-CMP flag replay only on the no-input path, byte-exact). Tests in ``test_coord_ring.py`` (7).

**Scouting conclusion (important for the next session): leaf-level pure extraction is essentially
EXHAUSTED.** Walking the collision/movement/behavior surface (``systems/collision.py``,
``systems/objects.py``, ``systems/movement.py``) shows every clean per-slot DECISION is already pure
(overlap ``AC97``/``B250``/``62F6``, tile ``B00D``, post-move ``BC4B``, all the ``*_logic_*`` behavior
rules, seek/step movement, timers, score). What remains "ASM-like" is **orchestration/control-flow**
(pool scans, dispatch, the shared collision/tile-probe tails calling the pure predicates) that only
shrinks by **extending the native runtime** (``systems/frame_loop.py`` + ``native_object_pass`` +
``native_object_update``) to own more of the frame, not by more leaf extraction. So the real
pure-mass lever now is Bucket C (native self-play): wire the still-declined stages (coord-ring
store/advance/pull -- the pure forms now exist -- the ``A212`` chain, the ``A067`` full-fanout/``A970``
counters) into the native loop and push ``verify_native_forward_frames`` past its 35-tick wall.

## 2026-07-03 - Collapse: delayed-coordinate ring wrap extracted to pure systems/coord_ring.py

Extracted the ``1010:9CF1`` coordinate-ring cursor-advance wrap out of the lifted
``gameplay/game_state.py`` into a pure module: ``recovered/systems/coord_ring.py``
(``advance_coord_ring_ptr`` + the ring geometry constants -- base ``DS:A27A``, wrap-at ``DS:A33A``,
step 4, 48 ``(x,y)`` slots). ``_advance_coord_ring_ptr`` is now a thin adapter that owns only the DS
memory writes + dead-CMP-flag replay and delegates the wrap decision to the pure rule; byte-exact
preserved (the 9CF1 demo-replay verify is unchanged). Unit test ``tests/test_coord_ring.py`` (5).
Pure mass 30.4% -> 30.5% (systems modules 37 -> 38).

**Scouting note (why this slice):** the big lifted object files (object_movement/behaviors) are
already thoroughly collapsed -- every clean pure decision is delegated to ``systems/``; what remains
is VM control-flow glue + shared movement/tile tails (islands), matching the brief's "single-leaf
slices exhausted". The coordinate rings (``9CD9``/``9CF1``/``A031``/``99CD`` in game_state.py) are
one of the few remaining places with un-extracted pure arithmetic; the store/pull halves (ring state
model) are the natural follow-ups, and they feed the native frame loop's still-declined coord-ring
stage.

## 2026-07-03 - MILESTONE: FULL object->sprite draw is native + byte-exact (all 3 routines, both slots)

The complete VM-free object->sprite bridge now renders the real gameplay frame -- **player ship WITH
exhaust flames + the top projectile + enemies** -- and is proved byte-exact against the VM's real
draw-type dispatch. Visual + index-space confirmation on the L3 demo: native compose vs the VM
playfield differ by only **54 px, ALL of them starfield** (a separate subsystem); every sprite pixel
matches.

**The real structure (this CORRECTS the earlier "level bank" entry below):** an object is drawn by ONE
of three shared routines, selected by its draw-type word `obj[+14]` through `cs:[75A0]`
(`{0:7746, 1:768E, 2:75A6}`) -- NOT by the sprite-id/bank. Each routine has its own bank, frame table,
id threshold, compositor and slot layout:
- **75A6** (`dtype 2`, e.g. the player): table `cs:[9392]`; id `<0x1C` -> common bank `cs:[95A6]` =
  **MANEXPL.BIC**, else LEVEL bank `cs:[95AE]` = `NativeLevel.graphics` (index `id-0x1C`). Compositor
  **2E6E** (8 words/32px, 16 rows). Draws **TWO slots**: `obj[+0C]` at `off`, then `obj[+10]` at
  `off + (ds:[1028]>>1)` (the cell's second half) -- this is the ship body + exhaust.
- **768E** (`dtype 1`, most effects): table `cs:[9192]`; id `<0xFA` -> `cs:[95AA]` = **2X2.BIC**, else
  `cs:[95AC]` = **2X2C.BIC**. Compositor **2F81** (4 words/16px, 16 rows). ONE slot at `obj[+0C]`.
- **7746** (`dtype 0`, compact): table `cs:[8F92]`; bank `cs:[95A8]` = **1X1.BIC**. Compositor **2FB6**
  (2 words/8px, fixed 8 rows, one unrolled blit). ONE slot at `obj[+0C]`.

Per-row DI advance = `words_per_row*2 + row_add` (`0x68` for both 2E6E & 2F81). The four global banks
(MANEXPL/2X2/2X2C/1X1) were ALREADY recovered + verified in `asset_codecs/shared_assets.py`
(`load_shared_startup_assets`); this work is the **mapping** (which shared asset feeds which
sprite-draw segment) + the dispatch + the two-slot 75A6 split.

- **`overkill/native_video/object_sprites.py`**: `object_slots(sid, dtype, +0C, +10, ctx)` ->
  `list[SpriteSlot]` (the exact compositor blits); `object_sprite_blocks(pool, ctx)` -> decoded
  `SpriteBlock`s via `decode_masked_sprite` (which already supports 2E6E/2F81/2FB6 widths). `ctx` =
  `SpriteDrawContext` (the 5 banks + the 3 tables + `half_stride = ds:[1028]>>1`).
- **Proof: `overkill/probes/verify_native_object_sprites.py`** drives the ORIGINAL draw-type dispatch
  `1010:7596` per active anim-0/non-variant object, captures EVERY 2E6E/2F81/2FB6 blit `(comp_ip, di,
  si)` and asserts `object_slots` reconstructs the identical full per-row sequence. **PASS: L1 8/8,
  L2 2/2, L3 20/20, L4 2/2, L5 9/9.** (The earlier probe checked only the FIRST blit while driving
  75A6 in isolation -- it passed vacuously for objects that actually use 768E; this drives the REAL
  dispatch and the full sequence.)
- Headless unit test: `tests/test_object_sprites.py` (dispatch, per-routine bank/table/threshold, the
  75A6 two-slot split, skip rules).

**Still open (documented, not faked):** `anim(+12)!=0` (a different phase target) and the `obj[+24]`
OR-inverted variant (`2F40`/`2ECB`, decoders already exist in `sprite_textures`) are SKIPPED; wiring
this bridge into `play_native.py` (build `ctx` from the shared banks + level + the boot tables) so the
standalone renders enemies is the next slice. The 54-px starfield diff (top region) is a separate
starfield-plate discrepancy to chase.

## 2026-07-03 - Object->sprite bridge (LEVEL bank) verified byte-exact vs the VM's 75A6 [SUPERSEDED]

> **SUPERSEDED by the entry above (2026-07-03).** This entry's model -- "sprite_id>=0x1C -> LEVEL bank
> via 75A6" -- was **miscategorised**: the routine is chosen by `obj[+14]`, not the sprite id, and the
> effect objects it described actually draw via **768E** (a different bank/table/compositor). The
> verify here drove 75A6 in isolation and checked only the first blit, so it passed without exercising
> the real path. The corrected, full-dispatch bridge above replaces it.

Recovered the VM-free object->sprite bridge for the LEVEL sprite bank and proved it byte-exact
against the original draw:

- **`overkill/native_video/object_sprites.py` -> `level_object_sprite_blocks(pool, level_graphics,
  descriptor_table)`**: for each active object with `sprite_id >= 0x1C` (level bank), `anim == 0`,
  `di != 0xFFFF`, look up `off = descriptor_table[sprite_id-0x1C]` in the real `cs:[9392]` word
  table, slice `level_graphics[off:off+512]` (= `NativeLevel.graphics` = the VM's `cs:[95AE]`), and
  `decode_masked_sprite(src, 8, 16)` -> one `SpriteBlock` at `di`. Common-bank (`<0x1C`), `anim!=0`,
  off-screen slots are **skipped, not faked** (documented follow-ups).
- **Descriptor table is READ, not computed.** The earlier `(sprite_id-0x1C)*0x400` formula was WRONG
  for high ids (L5 sprite `0x162`: linear `0x1800` vs real `table[0x146]=0x1B0`). Fixed to read the
  `cs:[9392]` table; all levels then pass.
- **Proof: `overkill/probes/verify_native_object_sprites.py`** drives the ORIGINAL `75A6` per object
  (hooks cleared; SS:BP = the record) and captures the first `2E6E` blit's `(di, si)`, then asserts
  the bridge computes the identical `di` + bank offset. **PASS: L3 18/18, L5 6/6, L1 6/6, L6 16/16.**
- **`NativeLevel(level=3).graphics == VM cs:[95AE]` byte-exact (diff=0).** (An earlier 54% "bank
  mismatch" scare was a WRONG level index: the "L3" demo is level index **3**, not 2.)
- Headless unit test: `tests/test_object_sprites.py` (selection/skip logic + non-linear descriptor
  lookup, 3 tests).

**Honest gap (why the composed native L3 frame shows only the starfield):** the *visible* sprites in
these snapshots — the player ship + thrusters — are **COMMON-bank** (`sprite_id < 0x1C`, `cs:[95A6]`),
which this level-bank bridge correctly skips. The 16 verified level-bank blocks are enemies that are
off-screen in that frame. **NEXT for a recognizable native frame: recover the COMMON sprite bank
`cs:[95A6]`** (player ship `0x01` + shared effects, built at boot from SHIP.BIC etc.), then wire both
banks into `play_native.py`. `anim!=0` (`7688` no-draw) and the `obj[+24]`->`2ECB` OR-inverted case
are the remaining bridge follow-ups.

## 2026-07-03 - Front-end: real title screen VM-free + scrapped the play_native placeholders

Direction from the user (they ran `play_native.py` and got a WHITE SQUARE): enforce the project's
no-placeholder / fail-loud / no-staging rules, and wire the REAL render toward showing the game.
Reference is `D:\Games\DOS\pre2_port` (a far more mature VM-less port: boot-data-as-constants, full
front-end, real rendering, `deploy_native.py` -> `dist/` + a VM-import smoke test).

Done this pass (all VM-free -- verified zero `dos_re` on the paths):
* **Real title/options screen.** `native_video/front_end.decode_fullscreen_image` decodes `OKMENU.ENC`
  through the recovered codecs (container LZ + `deplanarize_tandy`) to the exact 320x200 title screen --
  a live decode from the game data, not a screenshot. `play_native.py` now OPENS on it (Space starts).
  Byte-exact vs the VM title apart from a 276px overlay = the menu's red first-letter key highlights
  (y[65..128] x[77..182], native white(15) vs VM red(12)) -- a real next front-end slice, not a decode
  error. Unit test `tests/test_front_end_image.py` (checksum-pinned) + probe
  `verify_native_front_end_image.py` (byte-exact-vs-VM, records the 276px overlay).
* **Scrapped the placeholders.** Deleted `_placeholder_starting_state` (the fake spawn) and
  `_render_indices` (the white marker square) from `play_native.py`. Gameplay now REQUIRES `--snapshot`
  (a real captured start state) and **fails loud** without it -- no invented spawn (the cold level-start
  state is still the open Bucket-F level loader).
* **Real starfield background.** Replaced the white square with the recovered parallax starfield
  (`native_video.starfield_plate.render_starfield_plate`, proven byte-exact vs the VM), seeded from the
  snapshot's real star state (`_read_starfield`) and advanced each frame by `advance_starfield`. Verified:
  renders the real 40-star field, gameplay loop steps 8s with no gap/crash, whole path VM-free.

**NEXT (the piece that makes it recognisably the game): the object-record -> sprite-pixel bridge.** The
standalone draws the real background but not yet the player/enemies. The sprite pipeline is recovered
(`sprite_textures.decode_masked_sprite`, `composite_sprites`, `compose_playfield_indices`), and the
level's sprite bank cold-loads (`NativeLevel.graphics`); what's missing is the VM-free mapping from an
object slot (sprite id/anim + position) to its sprite source in the bank + dimensions -- the recovery
the VM draw routines `75A6`/`768E`/`7746` do. Recover that, then compose starfield + sprites (+ HUD) into
the real frame. Do NOT fake sprites in the meantime (rules: fail loud, no placeholder).

## 2026-07-03 - MILESTONE: scripts/play_native.py is a REAL VM-less standalone (zero dos_re imports)

Built the first genuine VM-less standalone entrypoint per the pre2-mirrored direction (below). Replaced
`scripts/native_play.py` (which was NOT standalone — its default mode only presented one captured VM
snapshot, and its `--backend native` support in `play.py` spawned a full VM child process) with
`scripts/play_native.py`:

- Cold-loads a level via `overkill.native_game.NativeGame` (byte-exact from `assets/OVERKILL` + the
  materialized `artifacts/static_runtime_bundle/memory_1mb.bin` — both static files, no VM).
- Runs real gameplay ticks each frame: keyboard input decode, view-anchor movement, native world-scroll
  (A66F/A6FE), the object-update pass — all through the recovered pure systems. `ref_box_x`/`ref_box_y`
  (the view-anchor box the object pass reads) are DERIVED for real (confirmed: DS:237E/2380 ARE the
  view-anchor slot's own X/Y fields, DS:237C+02/+04); the handful of still-open Bucket-C globals get the
  same documented 0/False "normal tick" defaults the recovered dataclasses already use.
- Presents via pygame (indices → Tandy palette → blit); rendering is currently a DEBUG PLACEHOLDER (black
  bg + a marker at the player position) — the real starfield/HUD/sprite visuals are proven correct in
  isolation but not yet wired into this loop (clearly labeled as such in the file, not silently faked).
- `--snapshot DIR`: DEBUG-only, seeds a REAL verified starting state from a captured VM memory dump via a
  10-line local `_FlatMemory` reader (no `dos_re` import) reusing the existing
  `read_native_game_state` projection.
- On any exception from a gameplay stage (a real gap), stops ticking, prints it, holds the last frame.

**Verified VM-free, not just claimed:** `sys.modules` shows zero `dos_re`/`dos_re.*` entries after
importing `play_native`, cold-loading a level, running 10+ real ticks, and running the full pygame
present loop headlessly (SDL dummy driver) — checked explicitly, not assumed.

**A real separability leak found + fixed along the way:** `overkill/asset_codecs/*` (imported
transitively by the level loader) is NOT pure — several modules (`rle.py`, `packed_stream.py`,
`overlay.py`, `lz.py`, `checksum.py`, `asm_adapters.py`) import `dos_re.cpu`'s `CF`/`DF` flag constants
(kept for their VM-hook-body forms, used by `--backend vm`), and `asm_adapters.py` also imported
`overkill.asm` (which itself pulls in `dos_re.cpu`/`dos_re.memory`) just for the trivial 3-line
`loop_count` helper. Since Python always executes a package's `__init__.py` (which eagerly imports every
sibling) when importing ANY submodule, this transitively loaded the whole `dos_re` package the moment
`native_level.py` was imported — even though `native_level.py` itself never touches `dos_re`. Fixed with
a new, dependency-free `overkill/asset_codecs/_flags.py` (just the 2 integer constants, duplicated
rather than shared — they're a stable 8086 register-bit layout, not emulator logic) + a local
`loop_count` copy in `asm_adapters.py`; the 6 files now import from `._flags` instead of `dos_re.cpu`.

**`play.py` pruned to the pure VM/oracle tool**, per the user's explicit "absorb play.py --backend native
into play_native.py": removed `--backend`/`--mp-publish`/`--mp-input` args and both dispatch branches
(the `run_mp`/`run_publisher` spawn-a-VM-child code). `play.py` no longer imports `native_play` at all.

**Verified:** full suite green, **1100 passed / 23 skipped** (unchanged from before — zero regressions);
layers+arch+lint audits green; the standalone loop runs 10 real ticks + a full headless pygame present
loop with zero `dos_re` in `sys.modules`.

**Honest next steps (recorded in the brief's Bucket G too):** wire the real starfield/HUD/sprite
rendering into `play_native.py`'s render step (replacing the debug marker); recover the real level-init
state (Bucket F — the current spawn is a placeholder, not verified); build `scripts/deploy_native.py`
(import-closure → deny-list `dos_re`/workbench modules → copy to `dist/` → smoke-test VM-free in a
scrubbed subprocess, mirroring pre2's `deploy_native.py` exactly); eventually the front-end (Bucket E).

## 2026-07-03 - DIRECTION (user): the VM-less standalone must mirror pre2_port (separate package + deploy→dist)

User set the endgame architecture explicitly and pointed at `D:\Games\DOS\pre2_port` (the mature, nearly
done sibling) as the template. Studied it; the target is now recorded concretely in the brief's **Bucket G**
(`overnight_endgame_execution.md`). Key points:

- The VM-less game is a **separate self-contained package** (`overkill/native/`, mirroring `pre2/native/`)
  that imports ONLY the pure recovered layer + its own native runtime — never `dos_re`/hooks/cpu/mem —
  with its OWN screen (`native/vga.py`), boot state as **pure constants** (`native/boot_data.py`, built
  once by a workbench probe; the VM's only remaining BUILD-TIME role), `native/cold_boot.py`,
  `native/front_end.py`, `native/runtime.py`, `native/render.py`, `native/audio.py`.
- **`scripts/play_native.py`** (rename `native_play.py`) is THE standalone entrypoint: DEFAULT = cold-boot
  the whole game from `--game-root` game data (no snapshot, no VM); `--snapshot`/`--from-level` are DEBUG.
- **`scripts/deploy_native.py`** (pre2 has one): import-closure of play_native.py → deny-list every VM
  module → copy to `dist/overkillnative/` → **smoke-test in a scrubbed subprocess asserting NO VM module
  imports**. That smoke test is the machine-checked VM-free proof. `dist/` = ships with only the game data.

**Correcting the current confusion (the user's exact complaint):** today's `scripts/native_play.py` is NOT
the standalone — its `main()` requires `--snapshot` and just presents one captured frame; and
`play.py --backend native` spawns a VM CHILD (`--mp-publish`) with the "native" part being only the
decoupled *presenter* — so `--backend native` is HYBRID (VM + native present), not VM-less.

**Where overkill actually is vs the target (better than "nothing"):** the pure *systems* exist, and
`overkill/native_game.py` (`NativeGame`) already cold-loads a level from the original files
(`asset_codecs.load_native_level`) and advances the recovered frame stages VM-free — "the standalone
backbone." Missing for a real `play_native.py`: (1) an `overkill/native/` package assembling
state+cold_boot+render+input+present into a runnable level loop (the `--from-level` standalone — closest
to shippable, since `NativeGame` exists), (2) the front-end/cold-boot-from-start flow (Bucket E), (3)
`deploy_native.py`→dist. **Concrete first slice:** stand up `scripts/play_native.py` that runs a level via
`NativeGame` + `native_video` + pygame present, VM-free (holding on the first unrecovered stage-gap, exactly
like pre2's play_native) — a true VM-less-single-level entrypoint — then grow the front-end and the deploy
script. (Note: this session's Bash safety classifier was intermittently unavailable, so the rename + new
entrypoint + deploy script — which need running/verifying — are staged as the next concrete slice, not done
blind; only the durable architecture direction was recorded this turn.)

## 2026-07-03 - VISUAL CONFIRMATION: cold-boot title/options screen renders correctly; found the real bug

Rendered a screenshot from a fresh cold-boot run (dependency-free PNG dump, reusing `scripts/render_frame
.py`'s `render_tandy_ppm`/`write_png`, applied to a hooks-ON + checksum-accelerated boot at ~80K steps)
to visually confirm what phase the earlier menu-advance probes were actually in — the user asked for a
screenshot specifically to help diagnose this. **The result: a perfect, fully legible render of the real
OVERKILL title/options screen** (logo, Keyboard/Amstrad-Joystick/Joystick/Redefine-Keys, Music options,
"FIRE = START", the 1992 Tech-Noir copyright, the Epic MegaGames/PSP logo) — byte-for-byte through the
recovered Tandy decode pipeline. This is strong independent visual proof that the cold-boot render chain
(loader → self-check → video init → Tandy graphics blit → this screen) works end-to-end.

**Root cause of every earlier probe's confusion this session, now found:** those probes booted with
`create_overkill_runtime(..., command_tail=<default/empty>)`. The default/empty tail leaves the PSP video
selector byte unset (`CS:[95BC] == 0`, not Tandy's `2`), so the game ran in a DIFFERENT (non-Tandy) video
path the whole time — explaining why decoding the framebuffer via `render_tandy_ppm` earlier in this
session produced illegible noise (a text-mode/other-mode buffer decoded as if it were Tandy packed
graphics). **Fix: pass `overkill.launch.build_command_tail("tandy", "pc")` as `command_tail`** (already
used correctly by `scripts/play.py`/the recorded demos, just missed in these ad-hoc scratch probes). With
it, `CS:[95BC]` reads `2` and the screen decodes perfectly.

**Consequence:** the "menu idle loop at 1010:558B, unique=1827" observations from the earlier probes this
session (the crash-gap fixes' verification, the milestone finding) were all made with the WRONG tail —
they still proved the crash-fixes work (no exceptions, stable idle cycling) and are NOT invalidated as
functional-correctness evidence, but the SPECIFIC addresses/screen-identity assumptions from those runs
(e.g. "this is definitely the Tandy 558B menu code path") should be re-verified against a
correctly-configured boot before being relied on further. The `558B` menu-idle hypothesis is independently
supported by the recovered `step_menu_idle_558b` system and its own demo-based verify probe
(`verify_native_menu_idle_558b.py`), so it is very likely still correct, but this is worth a fresh,
correctly-configured confirmation pass. Screenshot sent to the user; kept in scratch (`dump_frame.py`,
`frame_menu3.png`) for reuse.

## 2026-07-03 - Diagnosed the menu-advance probe: wrong DS sampled, not a code defect

Follow-up to the menu-idle milestone: attempted to feed a synthetic Space keypress (`dos_re.interrupts
.deliver_scancode`) into the hooks-ON cold boot to advance past the `558B` idle loop into gameplay.
Confirmed the exact target: the recovered `step_menu_idle_558b` (`recovered/systems/menu.py`) exits
when `DS:98BE` bit `0x10` (FIRE) is set, and the recovered keyboard decode
(`recovered/systems/input.DEFAULT_CONTROL_MAP`) confirms scancode `0x39` (Space) maps to
`INPUT_FIRE` — so Space is the right key and the recovered decode tables are internally consistent.

**The probe attempt itself had a bug, now diagnosed (not a code defect):** it read/compared `DS:98BE`
using whatever `DS` happened to be live at the arbitrary instruction boundary where the interrupt was
delivered (a transient loader/boot segment, e.g. observed `DS=35FF`), not the game's actual resident
data segment (the one live whenever `CS:IP` is inside known `1010`-segment game code like the `558B`
idle loop). So the observed `98BE` values (`0x08`, then `0x00`) are not meaningful evidence of a
real vs. expected mismatch — they were read from the wrong memory. Also identified a sequencing bug in
the first attempt: `deliver_scancode` only runs the INT 9 ISR to completion, it does NOT itself run the
game's own poll loop (`0162`/`0169`), so a press+release delivered back-to-back with zero `cpu.step()`
calls between them can never be observed as "held" by the game's next poll — the corrected probe
separates press → hold-for-N-steps → release, but still needs the DS fix to read/verify correctly.

**Concrete next step (well-scoped, not a re-exploration):** sample the resident `DS` at a moment when
`CS:IP` is confirmed inside the idle loop (e.g. exactly at `1010:558B`), and both deliver the keypress
and check `98BE` relative to THAT segment — plus deliver the press while parked in the idle loop
specifically (not at an arbitrary mid-boot instruction) so the timing relative to the poll loop is
well-defined. The recovered decode logic itself is trusted and unchanged; this is purely a test-harness
correctness fix.

**Process note:** kept this exploration properly bounded this time — two Monitor-watched runs, each
under 500K steps with live progress every 25K steps and clean early termination once the needed
information was gathered, no silent long runs. No code was changed (pure investigation); tree stayed
clean throughout.

## 2026-07-03 - MILESTONE: hooks-ON cold boot reaches a stable menu idle loop, zero crashes (600K steps)

With the `519A`/`5A6C` dispatcher fixes (below) + the checksum accelerator (`boot_selfcheck_checksum`,
inlined as a step-hook on `1010:C916` — same technique validated earlier, not yet wired into
`create_overkill_runtime` itself) applied to a hooks-ON boot, ran a bounded, incrementally-logged probe
(scratch `bootcheck4.py`, `Monitor`-watched so progress is visible live instead of silent): **600,000
steps, zero crashes.** The boot goes DOS loader → boot self-check (accelerated) → menu-loading text/cell
render → and settles into a **stable idle loop** cycling `1010:D007 / 1010:4A4x / 1010:558B (the known
menu-idle address) / 1F8F:0253 (a timer-ISR overlay)`, with the unique-`(cs,ip)` working set flat at
**1827** across every 50K-step checkpoint from step 150K to 600K — the signature of a correct poll/wait
loop, not a hang or bug. This is the first time a cold boot has run this far with NO crash and NO
manual intervention.

**What this proves:** the cold-boot render + menu-load path is now substantially working under the
recovered hooks. **What's next to go further:** the idle loop is waiting for input (a keypress to start
a game) — advancing past it needs feeding synthetic keyboard input to the runtime mid-boot (the same
`dos_re` keyboard-state mechanism the demo-input pump uses), the same way a demo drives gameplay. That is
the concrete next step toward a real cold-boot-to-level harness.

**Process note:** the exploratory probe script initially had NO incremental output (wrote its result
only at the very end) and was left running unbounded for ~1 hour with zero visibility before being
killed — a mistake. Rewrote it to flush a progress line to disk every 50K steps and watched it live via
`Monitor` with a bounded step count + a hard timeout, so any future stall is visible within seconds, not
hours. Use this pattern (bounded budget + incremental flush + Monitor) for any further boot-stepping
exploration.

## 2026-07-03 - Cold-boot harness: 519A + 5A6C unlifted-backend dispatch fixed (clears 518C/85D5/5EF9)

Consolidated the cold-boot text/cell hook gaps into two root fixes (both zero gameplay change — only the
non-Tandy/unlifted branch differs, never hit by the Tandy-3153/306F gameplay path):
- **519A (central):** the text dispatcher's unlifted-backend branch now RUNS the backend's original
  bytes until it RETs to the caller's return (instead of leaving `s.ip = target`, which the lifted
  Python callers `518C`/`5F06`/`5EF9` couldn't host). Fixes ALL 519A callers at once. Simplified the
  earlier per-caller `518C` patch back to a clean assertion (`519A` now guarantees the return).
- **5A6C (shared):** `hooks._run_5a6c_dispatched_target` — after 5A6C's JMP dispatch, run the selected
  target's lifted hook, or (unlifted cold-boot blit backend) its original bytes until return. Used by
  the `61DC`/`6120`/`85D5` `call_5a6c` closures (previously their unlifted branch did nothing → the
  caller asserted).

**Verified:** the hooks-ON cold-boot now runs **60,000 steps with no crash** (was crashing at ~18K on
`518C`, ~18K on `85D5`, ~22K on `5EF9`), advancing well past all three text/cell gaps to `1010:4A52`.
Full suite green (gameplay unchanged). Each fix also closes a real latent coverage gap in the recovered
text/cell render. The iterative harness keeps working: the next crash (past 60K steps) is the next gap;
the boot is steadily marching toward the render/menu.

## 2026-07-03 - Cold-boot harness: first hook gap FIXED (519A/518C); boot advances to the next (85D5)

Started the iterative hooks-ON cold-boot harness. Fixed the first cold-boot-path hook gap: the lifted
`518C` NUL-text loop couldn't host `519A` dispatching to an unlifted non-Tandy text backend (the
cold-boot intro/title text mode) — `519A` JMPs there (`s.ip` off `0x5197`) and the Python loop raised
before the VM ran it. Fix (`rendering/text.py`): when `s.ip != 0x5197` after `519A`, run the backend's
original bytes until they RET to `0x5197` (`_run_original_text_backend_until_return`, the bounded
nested-step pattern already used in `layer_sprites.py`). **Zero gameplay change** — the Tandy-3153 path
always returns to `0x5197`, so the new branch never triggers for it (full suite stays green).

**Verified:** the hooks-ON cold-boot now runs PAST `518C` (fires 4×) to the NEXT gap — `85D5 expected
5A6C to return to 8628, got 1010:4199` at ~17.9K steps (same pattern, the cold-boot cell blit dispatches
to an unlifted backend). Logged in `loop_blockers.md`. This confirms the harness loop works: each fixed
gap advances the boot to the next, closing real latent coverage gaps in the recovered code as it goes.
The cold-boot is now a **tractable, iterative build** (fix gap → rerun → next gap) rather than a wall.

## 2026-07-03 - Cold-boot harness: hooks-on boot is ~90x faster but hits a 519A cold-boot hook gap

Explored the cold-boot witness harness from the hooks-ON angle (`create_overkill_runtime(...,
install_replacements=True)`): the recovered hooks run native Python, so the boot is **~90x faster**
than pure-ASM stepping — it reached `1010:4277` in **17.7K steps** (vs ~1.5M hooks-off to reach the
game code). BUT a recovered hook raises on the cold-boot path: the `518C` NUL-text loop calls the
lifted `519A` text dispatcher and asserts it returns to `0x5197`, but on the cold-boot intro/title text
it returns to `0x4277` (see `loop_blockers.md`). So neither harness mode reaches the render cleanly:
hooks-OFF is slow (compute walls — checksum accel'd, gfx-decode still), hooks-ON is fast but hits
cold-boot-path hook-coverage gaps (`519A`, and likely others tuned for gameplay).

**Cold-boot harness strategy (updated):** the fast path is hooks-ON + fixing each cold-boot-path hook
gap as it surfaces (`519A` text dispatch first) — a bounded, iterative "run → hit a gap → fix the hook
for the cold-boot case → rerun" loop, much faster to iterate than accelerating every compute wall
hooks-off. Each fix also closes a real latent coverage gap in the recovered code (these hooks currently
raise on valid cold-boot paths). This is the concrete way in to the whole cold-boot phase (front-end
text/scenes, load-time chrome, level load) — a substantial but now-well-characterized fresh-context
build.

## 2026-07-03 - BOUNDARY: all PER-PRESENT HUD chrome recovered; remaining chrome is load-time-only

Gap analysis + `D104` trace establish a clean boundary for the snapshot-driven recovery. The
**per-present** HUD chrome — everything the per-frame render (`D104`) re-blits — is now fully
recovered + byte-exact-verified: `compose_status_cells_859e` (859E icon/box cells), `compose_status_counters_61dc`
(61DC counters + trailing panel cell), and `hud_text.compose_status_text_5edb` (5EDB score, earlier).
Alongside the byte-exact playfield self-compose, that's the complete **snapshot-witnessable** frame.

**What's left is load-time-only.** Composing the recovered chrome onto a blank page vs the VM B800:
1846 bytes reproduced-and-matching; the ~5068 VM-nonzero bytes not reproduced are the **playfield**
(dynamic gameplay content, a separate layer) + the **static labels/borders/panel-frame**. Those static
elements are drawn ONCE at level-load and are NOT re-blit per present (confirmed: `D104` re-draws only
the dynamic cells/counters/score; the gap regions stay as loaded), so they **cannot be driven on a
gameplay snapshot** — recovering them needs a snapshot taken at level-load, or the cold-boot/load path
(the deferred witness harness; the boot self-check accelerator + drive-on-snapshot oracle are the
enablers already in place).

**Net:** the snapshot-witnessable render is essentially complete (playfield + all per-present chrome +
score, all byte-exact). The next frontier — the load-time static chrome, the front-end flow, native
level/asset load, audio, and the cold-boot backbone — all live on the cold-boot path and are the
fresh-context cold-boot phase. The reusable bricks (playfield compose, `paste_panel_cell`, the three
HUD composers, `boot_selfcheck_checksum` + its acceleration, the drive-on-snapshot oracle) are banked.

## 2026-07-03 - HUD status-COUNTER composer (61DC) RECOVERED too, byte-exact vs the VM

Extended the HUD-chrome recovery to `1010:61DC` (the status-counter display). Same snapshot-driven
oracle. Recovered its composition: 6 counter cells from `xy_to_di_5a00(0x1F,0x40)=0x0A7C` stepping
`di+=4`, each cell `dir[counter_value + 0x19]` (`6296`); plus 2 trailing cells gated on `[A95A] !=
[2374]` — at `(0x1F,0x0C)` `dir[(a95a==FFFF?0:a95a) + 0x20]` and at `(0x21,0x18)` `dir[0x1E]`. Also
recovered `5A00` xy→di: `(y&3)*0x2000 + (y>>2)*0xA0 + x*4` (Tandy 4-bank interleave; confirmed on 3
witnessed samples). Added `native_video/hud_chrome.compose_status_counters_61dc` + `xy_to_di_5a00`.

**Gate:** `verify_native_hud_chrome.py` now drives BOTH `859E` and `61DC` on a snapshot and asserts each
composer reproduces its B800 byte-exact — **PASS diff=0 on L2/L4/L5** (both). 3 more VM-free unit tests.
NOTE: on these snapshots the 6 counters are all 0, so the value→cell map `dir[value+0x19]` is witnessed
only for value 0 (the nonzero path is read straight from `6296`'s `add si,0x19; dir[si]` but is
witness-poor). Suite green; layers+arch+lint green.

**Cold-boot chrome status:** `paste_panel_cell` (306F) ✓, `compose_status_cells_859e` (859E cells) ✓,
`compose_status_counters_61dc` (61DC counters) ✓ — all byte-exact-verified. The remaining static chrome
is the panel/border **background** (the big 40×6 `dir[a95a+0x20]` cell 61DC draws is part of it, now
covered) + any borders drawn by other load-time routines. Next: find/verify the remaining background
draw(s) via the same drive-on-snapshot oracle, then assemble the full static-HUD layer for the frame.

## 2026-07-03 - HUD status-cell composer (859E) RECOVERED, byte-exact vs the VM across 5 snapshots

Built + verified `native_video/hud_chrome.compose_status_cells_859e` — the native form of the `859E`
HUD status-cell render (the WEAPON/MISSILES/DRONE/GADGETS icon caps + boxes). Recovered `85D5`'s exact
per-descriptor derivation: for each of the 4 descriptors (`SS:9682/968C/9696/96A0`; fields `+0`
color-idx, `+2` di_base, `+4` src_idx) it blits 3 PANEL cells via `paste_panel_cell` — A(icon)
`di=di_base+0x14, dir[src_idx+match]`; B `di=di_base-0x04, dir[0x17+match]`; C(box) `di=di_base,
dir[color_idx]` — where `dir` is the `CS:0BE4` cell-offset table, `match` the `[95FA]` marker hit, and
color-idx swaps to `[BE16]` under the `[BDAC]` highlight.

**Gate:** `overkill/probes/verify_native_hud_chrome.py` drives the ORIGINAL `859E` on a snapshot (the
`cpu.replacement_hooks.clear()` trick) and asserts `compose_status_cells_859e` reproduces its B800
byte-exact. **PASS, diff=0 on L2/L3/L4/L5/L1-hard** (all `marker=0xFFFF`, so the match=0 path is
witnessed; the match=1 highlight path is derived from `85D5` but witness-poor — noted). 2 VM-free unit
tests pin the composition (`tests/test_hud_chrome.py`). Suite green; layers+arch+lint green.

**Cold-boot chrome status:** `paste_panel_cell` (306F blit) ✓ + `compose_status_cells_859e` (859E cells)
✓ are both recovered + verified. Remaining chrome pieces: `61DC` (the counter cells + WEAPON/MISSILES
label text) and the borders/panel background — then the full static-HUD-chrome layer composes for the
cold-boot frame. Both are now reachable by the same "drive the original on a snapshot, diff=0" oracle.

## 2026-07-03 - Composer oracle VALIDATED: drive original 859E on a snapshot, 12 blits, diff=0

Established the oracle harness for the `859E` HUD-chrome composer (scratch `probe_run_859e.py`), the
concrete enabler for building the native composer. Mechanism: `load_overkill_snapshot`, then
`cpu.replacement_hooks.clear(); cpu.hook_verifier=None` (the lindis trick) to run ORIGINAL bytes, push
a return sentinel, set `CS:IP=1010:859E`, and step to the ret. Result on the L2 snapshot: 859E runs the
full render tree in **1285 steps, fires exactly 12 `306F` blits** (4 descriptors × 3 subcells), and
**re-blits the chrome byte-identically (B800 diff=0)** — proving the render is deterministic from the
loaded data and that I can drive + observe it on any snapshot. (Note: `load_overkill_snapshot` installs
hooks; without the clear, 859E runs the lifted hook in 1 step and bypasses 306F.)

**Captured the exact composition** (di / PANEL src_off / rows×width), PANEL seg `CS:[95B4]=0x6BE1`,
`CS:[0BE4]` dir = `idx*0x90`:
```
descriptor i (di_base D = 0x7510, 0x7790, 0x7A10, 0x7C90; step 0x280):
  subcell A (icon):  di = D + 0x14, src = per-descriptor (0x0870,0x0A00,0x0B90,0x0D20; step 0x190) 7x7
  subcell B:         di = D - 0x04, src = 0x0EB0 (fixed)                                          8x1
  subcell C (box):   di = D,        src = 0x1FC4 (fixed)                                          7x5
```
So the composer = 12 `paste_panel_cell` calls; the labels (WEAPON/MISSILES/...) are NOT 859E's — they're
61DC's. **Next:** build `compose_status_cells_859e` by recovering `85D5`'s derivation of those 3 (di,
src) per descriptor from the descriptor fields (`SS:9682+`: color/di/src_idx) + the `CS:0BE4` dir — then
gate it byte-exact vs this driven-859E oracle (diff=0). The harness + captured data make it a bounded,
well-specified slice; `85D5`'s exact index math is the one remaining piece to read.

## 2026-07-03 - KEY REALIZATION: synthetic-ASM oracles recover cold-boot leaves WITHOUT the harness

Investigating cold-boot wall 2 (`1010:45D0-4624`) showed it is a **bounded graphics de-planarization
decode** (`shl al,1` runs + `mov ax,[45E4]; stosw` pixel writes; `cs:[0BD6]` is a gfx-mode flag set by
the load dispatcher at `0CB9/0CC9/0CD9/0CE9`), not an env wait — the boot is a *sequence of bounded
compute phases* (checksum, gfx decodes), not env-blocked here.

**The important insight (reframes the whole cold-boot phase):** the **synthetic-ASM oracle** pattern —
proven this session on `306F` (`paste_panel_cell`) and the boot checksum (`boot_selfcheck_checksum`) —
verifies a witness-poor routine against its own opcodes on synthetic input, **without running the boot
at all**. So the slow cold-boot *witness harness is NOT a prerequisite* for recovering + verifying the
cold-boot render leaves (the `859E` cell composer, `85D5` cell selection, the `CS:0BE4` cell directory,
the gfx decoders). Each can be recovered independently, in any order, via a synthetic oracle (load the
routine's code from any snapshot memory image, set up synthetic inputs, run from its entry to its ret,
compare to the pure form). The harness is only needed for the FINAL end-to-end cold-boot proof (§1.8),
not for the piece-by-piece recovery.

**Revised plan for the cold-boot render (do these in any order, each oracle-gated, no harness):**
1. `859E` composer → pure `compose_status_cells_859e(page, panel_source, cell_dir, descriptors)` over
   `paste_panel_cell`; oracle = run `859E→85D5→5A6C→306F` on synthetic descriptors/dir/source, compare
   the B800 page. (Bigger: a multi-routine call-tree oracle.)
2. `CS:0BE4` cell directory ← walk the decoded PANEL item headers (`planar.py`), gate vs the live
   `CS:0BE4` words from a snapshot.
3. The gfx decoders (`45D0` family) — check first whether `planar.py`'s 33AF/0CB8 load already covers
   them before re-recovering.
The boot checksum accelerator (committed) + this realization mean the harness itself is deferrable to
the end; recovery can proceed leaf-by-leaf now.

**Follow-up (2026-07-03): the three leaves share one root — the `526A` graphics decode.** Traced the
PANEL-load dispatcher: `0CB8/0CC8/0CD8/0CE8` are the 4 load modes (block/sprite × directory) that set
`cs:[0BD6]/[0BD8]` then `call 526A` (the real decode). The `CS:0BE4` cell directory (item 2) is
populated *inside* `526A`, and the `859E` composer (item 1) sits on top of the decoded PANEL + that
directory. So none of the three has a clean isolated entry point — they all need the `526A` decode
internals understood first. **Conclusion:** the cold-boot render is a genuinely entangled multi-routine
recovery rooted at `526A`, not a set of quick independent leaves — a substantial, focused undertaking
best begun with FRESH context (start at `526A`: map the decode + how it fills `CS:0BE0/0BE4`, gate the
decoded PANEL + directory vs a snapshot, then the `859E` composer over `paste_panel_cell`). The clean,
independently-verifiable pieces this session already banked (`paste_panel_cell`, `boot_selfcheck_checksum`,
both oracle-gated) remain the reusable bricks for that effort.

## 2026-07-03 - Cold-boot: boot self-check checksum recovered + ACCELERATION proven to clear wall 1

Built the first real piece of the cold-boot witness harness and proved the strategy. The boot
self-check (`1010:C8DC-C923`) reads a file in 5120-byte blocks and runs a read-only running checksum
(`C916` loop) over it — millions of interpreted instructions. Recovered the checksum as pure
`asset_codecs/boot_selfcheck.boot_selfcheck_checksum(seed_ax, data)`, verified byte-exact vs the
original `C916` opcodes by a synthetic-ASM oracle (`tests/test_boot_selfcheck.py`, 6 cases).

**Acceleration proven (scratch `probe_coldboot_accel.py`):** installing a step-hook that computes the
block checksum via the pure function and skips the interpreted `C916` loop (→ C91F with AX/SI/CX set)
gets a fresh cold-boot **past the self-check** — 111 blocks accelerated, execution advanced from the
frozen `C918` to new game code (unique IPs 784→1743). So the cold-boot-witness performance strategy
WORKS.

**Wall 2 mapped:** after the self-check, boot reaches a bit-shift/graphics-decode loop around
`1010:45D0-4624` (planar→chunky shift sequence + `cmp cs:[0BD6]` branch) and cycles there (unique IPs
frozen ~1755 from 2M→3M steps) — the next thing to accelerate or step through (likely intro/title art
decode) before the render (`306F`/`859E`/`33AF` still 0). The harness path is now: accel `C916` (done) →
handle wall 2 (45D0 decode) → env-wait + demo-input machinery → title→menu→level → witness the render.
Each obstacle is being knocked down in order; the checksum accelerator is the first reusable brick.

## 2026-07-03 - Cold-boot witness investigation: characterized the boot self-check wall

Investigated the recorded next step (a cold-boot witness harness). Concrete findings (boot a fresh
pure-ASM runtime via `create_overkill_runtime(..., install_replacements=False)` and single-step):
- Boot works. The DOS loader runs ~1.5M instructions in loader segments (`1B65`, `23AD`), then
  execution reaches the game code at `CS=1010`.
- It then enters a **compute-heavy boot self-check / decrypt phase**: a 65535-iteration checksum loop
  at `1010:C916–C91D` (`mov dl,[si]; add ax,dx; add ah,al; inc si; loop C916`) with `C923: jmp C8DC`
  forming an outer loop over lots of data. From 1.5M→4M steps execution stayed in this loop
  (unique_ips frozen at 784) — it's bounded computation, not an env wait, but it's MANY millions of
  instructions and **impractically slow to grind through in pure-Python stepping**.
- `306F`/`859E`/`85D5`/`33AF` (the chrome/graphics render) fire **0 times** before/through this phase —
  the render is past the self-check AND past the title (which will also need timer/input env handling).

**Implication for the cold-boot harness (refines the plan):** a naive input-less step-to-render is not
viable (the boot self-check is too slow in Python, then title/menu waits need env+input). The harness
needs a **performance + env strategy**, in order: (a) get past the boot self-check cheaply — hook/skip
`C8DC`-`C923` (a checksum/decrypt with no gameplay state) or capture a "just-booted" snapshot taken
once past it; (b) reuse the frame-verifier's env-wait + demo-input machinery to drive the fresh runtime
through title→menu→level; (c) then wrap/step `306F`/`859E`/the loader/the front-end scenes as the
produced-vs-VM witness. This is a substantial, fresh-context undertaking — the first obstacle (the boot
self-check) is now mapped so a fresh session can start on the performance strategy rather than
rediscover it. (Scratch probe: `probe_coldboot_306f.py`.)

## 2026-07-03 - Native 306F PANEL-cell blit recovered + verified via a synthetic-ASM oracle

Re-landed the static-HUD-chrome first leaf that the prior pass reverted (witness-poor in demos), now
proven the right way. `native_video/hud_chrome.paste_panel_cell` is the pure page-writer form of the
`1010:306F` Tandy PANEL-cell blit (`{rows,width}` header → per-row `rep movsb` of `width*4` bytes into
the packed B800 page, `DI += 0x2000` / wrap `+0x80A0`; raw copy, no colour mask). Since 306F runs only
at cold-boot/level-load (no snapshot-demo witness), it's gated by a **synthetic-ASM oracle**
(`tests/test_hud_chrome.py`): it assembles the exact 306F opcodes, runs them on a real `CPU8086` over
synthetic cells, and asserts the B800 page is byte-identical to `paste_panel_cell` — the same
"synthetic fixtures + interpreted ASM" gate the asset codecs use (6 cases: single/multi/wide cell,
bank-wrap, single-row, many cursors). This is a verified recovered blit awaiting its consumer (the
cold-boot native frame), exactly like the Bucket-F codecs sit verified ahead of the loader.

Suite green; layers+arch+lint green. `loop_blockers.md` 306F item moved OPEN→RESOLVED (verified via
oracle path #2). The witness-poor probe was NOT re-added (it always sees 0 calls in gameplay). Next:
the remaining chrome pieces (85D5 cell selection, 859E's 4-descriptor loop, 61DC counters) compose over
this blit — but they, and the full-frame compose that consumes them, belong with the **cold-boot
runtime** phase (Bucket E/G) where the render actually executes.

## 2026-07-03 - Attempted static-HUD-chrome native leaf (306F blit) → REVERTED (witness-poor)

Used a fresh-context subagent to map the static-HUD-chrome render island; it correctly traced the path
to `859E→85D5→5A6C→306F` (306F = a raw `rep movsb` PANEL-cell blit) and proposed `paste_panel_cell` as
the first leaf. Implemented it (disasm-accurate) + a produced-vs-VM probe — but **306F fires 0 times in
EVERY snapshot demo** (the chrome is drawn once at cold-boot/level-load, before the snapshots; that's why
it reads ~99.5% static in gameplay). No demo witness ⇒ can't gate it byte-exact ⇒ **fully reverted** (per
the invariants; never commit unverified / don't promote witness-poor as proven). Corrected the subagent's
wrong "859E fires every present via D104" claim. Full analysis + the two real paths to do this later
(a cold-boot fresh-runtime run, or a synthetic 306F ASM oracle) recorded in `loop_blockers.md`. Net: a
mapped-and-understood-but-not-yet-witnessable island; tree green, no code change committed.

**Implication for the loop:** the static-HUD-chrome (and the full-frame compose that needs it) is gated on
the **cold-boot path**, not gameplay demos — so it belongs with the Bucket-E/G cold-boot work (a fresh
focused session that stands up the cold-boot runtime), not a mid-gameplay slice.

## 2026-07-03 - Bucket A: B800 formation spawn-pointer wrap promoted to a pure system

Small Bucket-A promotion of genuine spawn-*sequencing* logic (not a data-prep constant): extracted
the `B800` formation-spawn list-pointer advance from the `b73e` behavior's `run_b800_spawn_pointer_advance`
closure into pure `recovered/systems/objects.advance_formation_spawn_ptr(ptr)` — advance DS:20A6 by one
2-byte entry, wrapping at 0x20C7 back to 0x20A8 (which formation slot spawns next). The adapter now
writes the final pointer once (the intermediate pre-wrap write is unobservable — the wrap CMP + AND
BX,1 flags are dead before any boundary, per the existing comment). 3 unit tests
(`tests/test_formation_spawn_seed_7476.py`: step-by-two + both wrap edges). Gate: b73e IS demo-exercised
(recovered this session), so demo-replay equivalence covers it byte-exact. Suite green; layers+arch+lint
green. Tiny pure-mass nudge; glue unchanged.

**Frontier note for the next run:** the readily-sliceable Bucket-A decisions are essentially exhausted —
a subagent scan found `9FEA` (done) and this `B800` wrap as the last clean un-delegated decisions; the
other candidates are either already pure or trivial data-prep constants (e.g. the `9CD9`/`99CD` +8
coord-center offset — NOT worth promoting, it would just inflate pure% without real crystallization).
The genuinely valuable remaining work is the **Bucket-C integration islands** (chrome-layer promotion via
the lifted `859E→85D5→5A6C` path; the native sprite-draw-list) and the large Buckets D–G — all multi-part
and **best taken with fresh, focused context** per the brief, not rapid auto-loop micro-ticks.

## 2026-07-03 - Bucket A: 9FEA child-coord clamp decision promoted to a pure system (pure% 30.2->30.3)

Bread-and-butter Bucket-A promotion (chosen via a subagent frontier scan of the big lifted files —
most were already delegated to `systems/`; `9FEA` was the cleanest remaining un-delegated decision).
Extracted `1010:9FEA`'s child/linked-object coordinate decision (child X = parent X + table dX; child
Y = parent Y + table dY + 2x vertical scroll bias DS:A398, clamped 0..0x00C0 with the lower/upper
clamp setting DS:A39E/A39F) into pure `recovered/systems/movement.object_child_coord_update_9fea`
(+ `domain/movement.ChildCoordUpdate`). Thinned the adapter
(`gameplay/object_movement.run_object_child_coord_update_9fea`) to read state -> call the pure
decision -> replay only the ASM register/flag choreography (SI advance, AX = pre-clamp Y, the two
CMPs, the A39E/A39F writes), preserving **exact** memory-access order so it's state-identical by
construction.

**Gates:** 12 VM-free unit tests (`tests/test_child_coord_9fea.py`) — 8 pin the pure clamp decision,
4 run the real hook on a `CPU8086`+`Memory` and assert the full CPU contract (child X/Y, AX, SI,
A39E/A39F, near-ret) per branch (null-link / no-clamp / lower / upper). Demo-replay equivalence green
(23 passed). **Honest note:** `9FEA` is *witness-poor* in the current demos (0 invocations across
L2/120f — it's a linked/child-object routine), so the primary proof is the adapter CPU-contract test
+ the by-construction state preservation (I derived the contract from the lifted ASM directly), NOT
demo coverage. Layers+arch+lint green. Metric: pure% **30.2% -> 30.3%**, glue unchanged (318).

## 2026-07-03 - Finding: the HUD/border chrome is ~99.5% STATIC (scopes the Bucket-C full frame)

Reconnaissance for the Bucket-C standalone full-frame compose (no code change). Decoded the full
B800 aperture at every present across L1–L4 and accumulated which pixels OUTSIDE the playfield window
(`y∈[4,196), x∈[0,208)`) ever change vs frame 0:
- **L1 80/24064 (0.3%)**, **L2 152 (0.6%)**, **L3 59 (0.2%)**, **L4 160 (0.7%)** — the HUD/border is
  **99.3–99.8% static** during gameplay. The only dynamic pixels are tiny bands: the score digit
  column (`x[232..239] y[27..65]`) and a secondary counter (`x[273..286] y[104..110]`).
- Those dynamic bands are exactly the score/status counters **already recovered** (the
  `5F05→519A→3153` glyph path / `native_video/hud_text.py`, proven by `verify_native_hud_text`).

**Implication for the full-frame compose (the next Bucket-C slice):** the per-frame full frame =
**playfield self-compose (DONE, byte-exact corpus-wide)** + **the recovered dynamic HUD counters
(DONE)** overlaid on a **static HUD/border chrome layer**. No new *per-frame* HUD recovery is needed.
The one remaining leaf is the static chrome itself — since it never changes during play it is a
**load-time draw**, so recover its generation as a load-time layer, NOT a per-frame capture (avoid
the throwaway plate-capture the brief warns against). Probe kept in scratch (`probe_hud_static.py`).

**Traced the chrome to its draw path (2026-07-03, same iteration):** the static HUD panel (the
WEAPON/MISSILES/DRONE/GADGETS/UPGRADES cells + borders) is drawn by the status-cell render island,
which is **already lifted (VM-aware)**: `859E` (`run_status_cell_quad_composite_859e`, the 4-cell
`9682/968C/9696/96A0` parent) → `85D5` (`run_status_cell_composite_85d5`) → the `5A6C` cell blitter,
with `511F` as the mode-1 page toggle (reached via `859E`'s `call_video_page_toggle`). So the chrome
is NOT unrecovered raw ASM — the remaining work is a **promotion + integration**, not fresh recovery:
lift the `859E→85D5→5A6C` render to a **pure native chrome-layer generator** (produce the static
HUD/border `(H,W)` indices once, VM-free) so the standalone full frame = chrome-layer ⊕ playfield
self-compose ⊕ the recovered HUD counters. This + the native **sprite draw list** (drive sprites from
the native object pass instead of the VM-bound `SpriteDrawCollector`) are the two remaining Bucket-C
integration efforts; both are multi-part and best taken with focused context. **NEXT SLICE:** begin
the chrome-layer promotion (a pure generator that runs the recovered cell descriptors into an `(H,W)`
chrome image, gated byte-exact vs the VM's static HUD/border region).

## 2026-07-03 - OR-inverted compositor leaves (2F40/2ECB) modeled: native compose now 100% on L3

**Bucket B (render self-compose) — closed the L3 sprite-compose gap.** The native compose modeled
only the masked compositor leaves (2E6E/2F81/2FB6); the **OR-inverted leaves 2F40/2ECB**
(`dest_word |= ~src_word`, a background-dependent bitwise-OR of the inverted source) were unmodeled,
so objects they draw were missing (an L3 16×16 white block: `native=0` where `vm=15`). This was the
5-frame L3 divergence logged (and freshly root-caused) this session.

Recovered end-to-end: pure `sprite_textures.decode_or_inverted_delta` (the `0xF ^ src` OR delta) +
`OR_INVERTED_COMPOSITORS` table; an `or_inverted` block kind in `native_video` (`SpriteBlock.kind`,
`sprite_layer.paste_or_inverted_block`, `composite_sprites` dispatch); and extractor capture
(`_make_or_inverted_hook`, `to_snapshot_sprites` emits the OR block, `stats.or_inverted_blocks`).

**Gate:** `verify_playfield_compose` now **L3 39/39** (was 24/29) and stays 100% on L1/L2/L4;
`verify_native_starfield_plate` self-compose L3 **39/39** too (was 24/29). 6 VM-free unit tests
(`test_sprite_textures.py` decode + geometry, `test_sprite_layer.py` OR paste + dispatch). Suite
green; layers+arch+lint green. `loop_blockers.md` L3 item moved OPEN→RESOLVED. Commit: (this pass).

**Metrics:** pure% 30.2% (the decode is pure/source; the compose+extractor are backend/bridge, so the
render-fidelity win doesn't move the headline). The render self-compose gate is now byte-exact across
the whole gameplay demo corpus — no known sprite-compose divergence remains.

## 2026-07-03 - Native starfield PLATE wired: standalone playfield needs no VM page

**Bucket B/C (render self-compose) — the starfield plate is now built from recovered state, VM-free.**
The playfield is `background plate + sprites`; the sprite layer + compose were already native, but the
*plate* (the sparse parallax pixel starfield) was still captured from the VM page — the last VM
dependency in the standalone playfield. Closed it: `native_video/starfield_plate.py`
`render_starfield_plate(state, cursor)` builds the `(H,W)` index plate purely from the recovered
`StarfieldState` — plot each star at `row*0x68 + cursor + dx` (`1010:4D15`, skip-occupied for
star-on-star overlaps) onto an otherwise-zero page, then decode through the verified present-blit
geometry (`render_present_page_indices`). Fails loud if the scroll cursor would push the star window
across a 64KiB page boundary (unmodelled segment wrap) rather than truncate silently.

**Gate:** `overkill/probes/verify_native_starfield_plate.py` (produced-vs-VM). Plate byte-exact vs the
VM plate on **every** frame across L1/L1-hard/L2/L3/L4 (e.g. L2 40/40, L3 39/39, L4 40/40, 0 diff). It
also reports the full self-compose `compose_playfield_indices(native_plate, sprites)` vs the VM
`[9598]` playfield: identical to `verify_playfield_compose`'s numbers over a VM-captured plate (since
the native plate is byte-identical), so L3's 5/39 compose shortfall is the **pre-existing sprite-compose
divergence that baseline probe already shows** (confirmed: baseline is also 24/29), NOT a plate defect —
so PASS is gated on the plate proof only. Unit test `tests/test_starfield_plate.py` (6 cases, VM-free)
pins the geometry + skip/guard rules. Commit: (this pass).

**Metrics:** pure% unchanged at **30.2%**, glue **318** (a backend render leaf, not an object collapse —
correctly lands in `native_video`/backend, not `source_pure`). Suite green. **Next Bucket-C step:** feed
`render_starfield_plate` into the standalone `--backend native` compose so the backend composes the plate
from recovered state instead of `render_present_page_indices` of the VM page (the HUD `hud_text` overlay
is the remaining background-layer wire). The L3 sprite-compose 5-frame divergence is a *separate*
pre-existing item (in `verify_playfield_compose`), not starfield.

## 2026-07-03 - Pre-loop readiness pass: status-metrics tooling fix

Orientation/handoff-readiness pass before launching the unattended loop. Suite re-confirmed green
(**1057 passed / 23 skipped**, exit 0); `audit_recovered_layers` + `audit_architecture` + `lint` all
green; tree clean and pushed.

**Fix (commit `db7a18c`):** `scripts/source_port_status.py` printed `<unavailable: ModuleNotFoundError>`
for two metrics — the object_record field-naming coverage and the **hook taxonomy / glue count** —
because run-as-a-script left `sys.path[0] = scripts/` with the repo root absent, so `import overkill.*`
failed. Added `sys.path.insert(0, ROOT)`. Both metrics now resolve: struct coverage **25/28 words named**
(10 known / 15 guessed / 3 unknown), **335 registered hooks → 318 glue** (12 checkpoint, 5 env_wait, 0
debug_probe). This matters because the glue count is the §7 secondary metric the loop must watch trend
down; it was previously invisible. Headline pure% unchanged at **30.2%**.

## 2026-07-03 - B73E logic_id 0x20 recovered + world-scroll subsystem native

**Bucket A (object collapse) — the dominant remaining wall fell.** `B73E` (logic_id `0x20`, the
waypoint-follower) is recovered: its `B800` formation-spawn gap + a follow-up double-spawn bug in the
`B82D` waypoint loop (a redundant per-iteration spawn-check; real ASM's loop-back `B857: jz -> B826`
skips it). Root-caught via the write-watcher playbook (whole-corpus `DS:20A6` BP-tagged sweep + a
redirect-into-real-bytes trace off the 3153 snapshot). The `test_tandy_text_glyph_3153` xfail is removed
(passes for real). Forward-carry endurance on L1 jumped 3188 -> 8540 ticks. Commits `2747255`, `b4c30ae`.

**Bucket C (native frame loop) — the world-scroll subsystem is now native + self-sustaining.** Ported
`A66F` (world-progress gate) + `A6FE`/`A74E`/`A746` (forward scroll tick) to pure systems
(`recovered/systems/scroll.py` + `domain/scroll.py`), byte-exact vs VM across L2/L4/L6 (two probes:
`verify_native_scroll_forward_a6fe`, `verify_native_scroll_gate_a66f`; 0 failures). Wired into
`NativeGame.step_scroll()` and threaded into the composed `NativeGame.step()` (real 9B2E -> A66F -> A067
-> AA0D order). `verify_native_forward_frames` now carries scroll as a first-class quantity: endurance
baselines UNCHANGED (L2 114, L3 70, L6_begin 40, L6_mothership_end 60) with zero scroll-caused
divergence, and boss-milestone declines gracefully shadow-defer to the VM. Commits `ebc3373`, `eefdbb1`,
`804127e`. Declined (own tasks): backward-scroll chain (A781/A7D0/A7E3), A7EB/CB1C (render/audio).

**Metrics:** pure % of game-logic mass = **30.2%** (up from 22.0% on 2026-06-30). Suite green: 1057
passed / 23 skipped. Next forward-carry walls are unrelated: effect-pool timing skew (L4/L5) + harness
step budget (L1/L5).

**Doc-staleness sweep (2026-07-03).** Audited the `/goal` docs for outdated claims that would misdirect
the loop and corrected them: the brief §6 (`overnight_endgame_execution.md`) no longer lists already-
recovered work as to-do (`aed8`/`8d4f`/`5e42`/`b250`/`b2cd`, the `3153` HUD glyph + `hud_text`, the
`BC4B`/`BFC7`→`C037` collision island, `9C01`/`A33A`); Bucket B starfield + HUD are marked
recovery-DONE with only backend WIRING open. **Correction to the "starfield CRACKED" entry below (2026-
06-30): the starfield is now FULLY recovered + verified** — `recovered/systems/starfield.py` +
`domain/starfield.py`, `verify_native_starfield.py`, `test_starfield*.py`. Its "Next: recover…" tail is
DONE; only wiring into `compose_playfield_indices` remains. The move address is `1F8F:0922/0960` (the
old `4C76` is wrong/absent). `loop_blockers.md` starfield section moved OPEN→RESOLVED; the `0x1c`/`8D4F`
whole-scan blocker flagged partially-superseded (`0x1c`→`_advance_8d4f` now dispatched). Stale headline
metrics in `coastline_report.md` (10.7%), `native_recovery_goal.md` (13.9%), `game_recovery_lifecycle.md`
(22%), and `loop_plan.md` backlog banner updated to point at the live `source_port_status.py` figure.
Genuinely still open (unchanged): `99F6` scripted-input, `A212` view-anchor, the FULL-fanout `A970`
held-action counters, `BD17` global death side-effects, and the render-layer backend wiring.

## 2026-06-30 - CORRECTION + the starfield blocker CRACKED

**Correction (supersedes the "Native terrain compositor" + "Controllable cold level" entries below):**
OVERKILL is a vertical **space shooter** (black space, sparse parallax starfield, ship at the bottom,
enemies above).  Those two entries' `native_video/terrain.py` rendered the level data as a dense "biomech
terrain" -- a **mis-decode** (wrong orientation + it skipped the cs:8D92 cell-offset indirection, and the
game's background is the starfield, not that).  Empirically refuted: of the 426 lit background pixels in
a live L1 frame, **0** come from the tilemap expansion.  Removed `native_video/terrain.py`,
`tests/test_terrain.py`, and the staged `scripts/native_play_cold.py` / `native_demo.py` (the "staged
testing thing").  The native render itself is faithful GIVEN the VM page (decode/colorize/sprites/HUD/
compose/present all byte-exact); the only render gap is generating the **starfield bg** standalone.

**Breakthrough:** that starfield bg is the documented #1 native-render blocker (loop_blockers: "eluded
~30 probes, no writer found").  It is now **cracked -- deterministic + recoverable, no RNG.**  Found with
`dos_re` `mem.write_watchers` (catches ALL write paths): over one frame, 7 sites write the present source
page; six are sprite blocks, and `1010:4D6F` writes **40 scattered single bytes = the ~40-px starfield**.
Routines (CS=1010): **erase 4D64** (clears the 40-entry working list `DS:0xC7B1`), **plot 4D15** (set up
by 4CED: stream `DS:0xC6C1`, list `DS:0xC7B1`), **move 4C76** (advances the stream per a video-mode jump
table, Tandy = shr1, parallax tables `DS:0xC803/C807/C80F` + counter `DS:0xC818`).  A star is 3 words
`{row, dx, color}`; page offset = `row*0x68 + cursor[DS:0x234C] + dx` (base table `DS:0x9A08 = row*0x68`,
the 0x68=208px page row stride); the plotter **skips already-occupied pixels** -- which is exactly why a
fixed watched byte was usually never written and prior probes found "no writer."  Next: recover
erase/move/plot as pure systems + verify produced-vs-VM byte-exact (probe step-hooking 4D64/4D15/4C76).
See `loop_blockers.md` and the `overkill-starfield-render` memory.

## 2026-06-30 - Pivot to Bucket F (cold-boot asset load): pure word-pair RLE codec

With the object-pass whole-scan parked on the deep 0x1c/0x1e behaviors (logged), pivoted to a clean
cold-boot-critical-path win: the asset codecs the standalone loader needs.  The codecs live in
`overkill/asset_codecs/` but are cpu/VM hook bodies (e.g. `decode_word_pair_rle(cpu)`), not usable by a
VM-free loader.

Added `asset_codecs.decode_word_pair_rle_words(words) -> list[int]` -- the pure (VM-free) dual-mode form
of the 1010:0324 hook: input word stream -> decoded word list, with the VM mechanics (ES:DI STOSW, the
packed-stream/DOS refill, error-IP) stripped.  Algorithm is the hook's (sentinel marker; non-marker =
literal pair; marker = repeat count, 0 terminates).  Unit coverage in tests/test_asset_codec_rle.py (8
cases: empty/literal/repeat/mixed/masking/count-1).  Verification: the hook it mirrors is verified
against the ASM (the load-time hook-verifier); the load codecs don't run in the snapshot demos, so the
pure form is unit-tested against that verified algorithm rather than produced-vs-VM.  No hook touched;
lint + both audits green.

This is the first of the loader codecs promoted to a pure VM-free form (Bucket F).  Next: the linear
byte RLE (0367) and vertical RLE (03A8) pure forms, then the level loader that drives them into
NativeGameState/LevelState -- the data path for a cold-boot level.

**Byte RLE done too:** added `asset_codecs.decode_linear_byte_rle_bytes(stream) -> bytes`, the pure
form of the 1010:0367 hook (control < 0x80 -> literal run of control+1; == 0x80 -> terminate; > 0x80 ->
repeat ((-control)&0xFF)+1 copies of the next byte).  9 unit tests (tests/test_asset_codec_byte_rle.py),
green.

**Vertical RLE done -- RLE family complete:** added `asset_codecs.decode_vertical_rle_columns_writes
(stream) -> [(offset, byte)]`, the pure form of the 1010:03A8 hook: a 3-word header (word1 = vertical
stride AND column count) then per-column control bytes, filling each column *down* (row r at offset
c + r*stride) with the byte-RLE control scheme, 0x80 ending a column.  Returns the strided writes
relative to di=0.  8 unit tests (tests/test_asset_codec_vertical_rle.py).  So all 3 loader RLE codecs
now have pure VM-free forms.

**Verification upgraded to airtight (all 3 codecs):** added tests/test_asset_codec_hook_crosscheck.py,
which drives the *actual oracle-verified hook bodies* (decode_word_pair_rle / decode_linear_byte_rle /
decode_vertical_rle_columns) on a synthetic 512-byte packed buffer and compares ES:DI output to the
pure form -- the same "predicted vs interpreted-ASM" gate the BF25 collision chain uses, lifted to the
loader codecs.  All pass byte-for-byte (incl. DI-advance counts), so the pure forms are now transitively
VM-verified, not merely unit-tested against my reading of the hooks.  28 codec tests total, green;
lint 233 + both audits green; no hook touched.

**Loader dispatcher mapped + the last 2 codecs done -- ALL 5 loader codecs now pure:** disassembled
the per-asset loader (entry 1010:0248: DS=CS, clear byte-counter [0244], set stream-ptr empty so the
first read refills from the file, filename from [023E], dest ES:DI from [023A]/[023C]).  At 1010:0283 it
reads a one-byte asset *type* and dispatches to one of five codecs, each decoding into the destination
until its terminator then jumping to the shared dispatch continuation (1010:02A8):

    type 0 -> 02C3  byte marker-RLE   (inline)   decode_byte_single_marker_rle
    type 1 -> 02F2  word marker-RLE   (inline)   decode_word_single_marker_rle_words
    type 2 -> 0324  word-pair RLE                decode_word_pair_rle_words
    type 3 -> 0367  linear byte RLE              decode_linear_byte_rle_bytes
    type 4 -> 03A8  vertical RLE                 decode_vertical_rle_columns_writes
    type >=5        -> AX=FFFF error (02B2)

Added pure forms for the two inline codecs (types 0/1): a sentinel marker byte/word, then literals, or
on a marker match a run (next byte/word = count, 0 terminates; following byte/word repeated count times)
-- type 1 is the single-word sibling of the type-2 word-pair codec.  The inline codecs have no
standalone hook, so they are verified by stepping the **real game ASM out of the 1MB runtime image**
from 02C3/02F2 to the 02A8 dispatch and comparing ES:DI output + DI-advance to the pure form (the gold
standard, image-sourced).  tests/test_asset_codec_marker_rle.py: 12 (10 unit + 2 real-ASM), green.

So all five loader codecs now have pure VM-free forms, every one airtight-verified (three vs their
oracle hook bodies, two vs the real image ASM).

**Pure dispatcher done -- the per-asset decode entry:** added `asset_codecs.decode_asset(stream) ->
bytes` (overkill/asset_codecs/loader.py), the VM-free twin of the loader dispatcher at 1010:0283: read
the leading asset-type byte, run the matching pure codec over the rest, return the decoded bytes as the
VM loader would leave them in a freshly-zeroed ES:DI destination (word codecs -> LE bytes; vertical ->
strided writes applied to a zero buffer); unknown type raises (the AX=FFFF error path).  Verified
end-to-end against the **real dispatcher ASM** stepped from 0283 to the 02A8 continuation for the
byte/word codecs (types 0-3, DS=25CC); type 4 (vertical, needs DS==CS) is checked at dispatch level
(routes to the already-airtight vertical codec) + the error path.  tests/test_asset_loader_dispatch.py:
8 tests; full codec suite 48 green; lint 234 + both audits green.

**LZ codec done -- ALL SIX asset codecs now pure + airtight:** added `asset_codecs.decode_lz_bytes
(stream) -> bytes` (overkill/asset_codecs/lz.py), the VM-free twin of the 1010:ECF2 LZ decoder -- the
4 KiB-window LZSS used for the bulk of OVERKILL's compressed assets (the big one, separate from the
0283 type-dispatch).  Machine mechanics stripped (1 KiB DS:D8B8 input ring + DOS refill, ES:DI segment
wrap, CS-relative counters, stack scratch); what's left is the codec: an 8-bit flag word fed LSB-first
(refilled every 8 items, 0xFF00 marker), 1-bit = literal, 0-bit = back-reference (two bytes -> 12-bit
offset + length (n>>12)+3), ax==0 then a byte (0 terminates, else resync), window write cursor starting
0x0FEE.  Verified against the ECF2 hook body on a blank Memory across literal runs, the flag-refill
boundary, back-reference copy, terminator, the rare ax==0/extra!=0 resync, and multi-flag-group streams
(tests/test_asset_codec_lz.py: 5 tests).  Full codec+loader suite 53 green; lint 234 + both audits green.

So the **entire asset decode layer is now VM-free and airtight**: six codecs (five 0283-dispatch RLE
codecs + decode_asset over them, plus the standalone LZ), every one verified against the real ASM (hook
body or image-stepped).

## 2026-06-30 - Container reader: the WHOLE cold-boot asset path is now VM-free end to end

Disassembled the container open 254A:04D7 and built `overkill/asset_codecs/container.py` -- the pure
reader for assets/OVERKILL (518 KB, an MZ exe + appended overlay pack).  Format (from the disasm):

    overlay base = (e_cp-1)*512 + e_cblp for an MZ file, else 0   (CS:07AA/07AC @ 254A:053C)
    overlay header @base: count u16 @0, XOR seed u16 @2, b"SHADOW" @4..10, entry-size u16 @10
    directory @base+12: count entries of entry-size bytes, XOR-decrypted with a key that ROLLS across
        the whole directory (al ^= byte; al += ah, ah=seed>>8 constant; the 05BF/05A1 stream cipher)
    entry (decrypted): payload offset u32 @+5 (relative to base), length u32 @+9, name @+0x0D (NUL-term)

API: `parse_overkill_container(data) -> [OverkillContainerEntry(name, offset, length)]`,
`read_container_asset(data, name) -> raw blob`, `load_container_asset(data, name) -> decoded bytes`
(codec by extension, the observed convention: `.ENC` -> LZ decode_lz_bytes, else `.BIC` -> decode_asset).

**Verified against the real file (the strong proof):** all **58** entries parse; every payload abuts
the next and fits the file (a wrong seed/entry-size/field-offset would scramble the offsets -> abut
fails); signature is `SHADOW`; and **every one of the 58 assets decodes** (27 `.BIC` via the type
dispatch -- types 0/3/4; 31 `.ENC` via LZ -- 0 failures).  Plus synthetic round-trip unit tests for the
parser logic (MZ base, rolling XOR, field layout).  tests/test_asset_container.py: 6 tests; lint 235 +
both audits green.  (Not ASM-cross-checked against 254A:04D7 -- that needs DOS file-I/O emulation -- but
the format is derived from its disasm and the all-58 abut+decode is conclusive structural proof.)

So the **complete cold-boot asset path is VM-free end to end**: `assets/OVERKILL` -> container directory
-> raw blob by name -> decoded bytes, every step pure and verified.  Assets discovered: level tiles/maps
(LEV0..5 BLX/MAP.BIC), sprite/graphic banks (*.BIC), intro/menu/score screens (*PAGE*/OKMENU/HISCORE/
... .ENC), and the music banks **ADLIB.ENC / ROLAND.ENC**.

## 2026-06-30 - Level loader scouted; per-level asset mapping landed (verified vs container)

Traced the level-load chain from the loader up.  The reusable per-asset load wrapper is **1010:C6DC**:
it reads a request block -- name ptr `DS:[21AA]` -> `[023E]`, dest seg `DS:[21A4]` -> `[023A]`, dest off
`DS:[21A6]` -> `[023C]` -- closes the previous handle, calls the container loader **0248**, and stores
the decoded length `[0244]` -> `[21A8]`; with a resident-asset cache check (`C710`/`C713` scanning the
`DS:14D0` word list, the recovered `search_decoded_asset_table_c713`).

The **per-level loader is 1010:0E9C** (called from level-init `976D`).  It indexes data tables by the
level number `DS:[2356]`:
- MAP-pointer table **`DS:14C0`** = `LEV0MAP.BIC`..`LEV7MAP.BIC` (8 words).
- `{graphics, blocks}` list **`DS:14E8`** (4 bytes/level): word0 -> `G{n}.BIC`, word1 -> `LEV{n}BLX.BIC`.
- dest segments: blocks -> `CS:[959A]`=8502, graphics -> `CS:[95AE]`=5FE6, a 3rd slot -> `CS:[95B6]`=7886
  (its name table `DS:5384` is empty in this snapshot).
- (DS=25CC, CS=1010 in the runtime image; the name-string table itself is at `DS:1176`.)

So for the six real levels the per-level set is `LEV{n}MAP.BIC` (tile map) + `LEV{n}BLX.BIC` (blocks) +
`G{n}.BIC` (graphics); slots 6/7 alias earlier levels.  **Landed** `asset_codecs.overkill_level_assets
(level) -> [LevelAsset(name, role)]` encoding exactly this, verified against the real container: every
per-level name for all 6 levels resolves to an asset that decodes (tests/test_level_assets.py: 3).
lint 236 + both audits green.

Level-init `974F`/`976D` is a ~20-call sequence (0E9C asset load is one step; player/object/state init
are the others: 5145/5BCA/6176/0B3E/60AC/C3A6/77C5/99BF/9BE2/A940/...); the MAP comes from the 14C0 table
via one of those sub-calls.  **Next** (the bigger build): the full pure level loader -- run the per-level
list through load_container_asset and place the decoded blobs where the dest segments point, mapping
those to NativeGameState/LevelState buffers (tile map / block defs / graphics bank).

## 2026-06-30 - First destination wired end to end: the level TILE MAP (byte-for-byte vs snapshots)

Took one destination all the way through and proved it.  The **MAP loader is 1010:0B3E**: it reads the
name from the `DS:14C0` table (`LEV{n}MAP.BIC`) and decodes it via `C679` -> `0248` straight into the
tile-map buffer **`CS:[9592]:0`** (dest off 0, a flat copy of the decode output).

Landed `asset_codecs.decode_level_tile_map(container, level) -> bytes` (= the decoded `LEV{n}MAP.BIC`,
a fixed `TILE_MAP_SIZE` = 3744 = 96x39 grid).  **Verified byte-for-byte against the runtime:** across
fresh level-load snapshots for all six levels, the decoded map *body* `[12:3682]` is byte-exact at
`CS:[9592]` (tests/test_level_map_placement.py).  Findings that pin it:
- Every cell is written (no codec gaps); the loader copies decode output to dest:0 by construction, so
  decode (already airtight) + placement is correct.  The body matches across L0..L5.
- The map's first row (`[0:12]`) and a trailing footer (`[3682:3744]`) are rewritten by post-load init
  (a border -- the footer is identical across levels), so they are excluded from the body check.
- Mid-gameplay snapshots mutate the body too (destructible terrain) -- the proof uses fresh-load
  snapshots (`*_start`/`*_full`/`*_begin`).

**BLOCKS/GRAPHICS are NOT a flat copy** (only ~10-17% match at their dest segs): they load via a
different path -- `1010:0E9C` calls `0CC8`/`0CD8` reading `[0BDC]`(dest seg)/`[0BDE]`(name), not the
`[023A]/[023C]` flat-decode the MAP uses.  So `LEV{n}BLX.BIC` (blocks) + `G{n}.BIC` (graphics) get a
transform/relayout on load (likely de-planarize / block-table expansion).  **Next:** RE `0CC8`/`0CD8`
to recover the blocks + graphics placement, the remaining two per-level destinations.

## 2026-06-30 - Blocks/graphics placement fully scouted: it's a planar->chunky de-planarize transform

Traced `0CC8`/`0CD8` to the bottom.  They are mode-setters for two flags `CS:[0BD6]`/`CS:[0BD8]` (BLX =
0/0, G = 1/0, the 3rd-slot 0CB8 = 0/1), then fall into common code at `0CF6`:
1. load the asset to the **temp buffer** `CS:[9598]:0` (=seg 35FF) via the same `C679` -> `0248`
   container loader (so the decode is unchanged -- already airtight), then
2. `jmp 5BAC` -- the placement **transform** copying temp -> final dest `CS:[0BDC]` (BLX 8502 / G 5FE6).

`5BAC` is **video-mode dispatched**: `bx = CS:[95BC]*2; jmp CS:[bx+5BC4]` (the demos run Tandy, mode 2;
table `5BC4` = {450C, 27D9, **33AF**, 8B2E}).  The Tandy handler **`33AF`** is a **4-plane de-planarize**:
a nested loop (`CS:[5B9E]` outer, `CS:[5B9C]` inner = plane stride) whose core `33DD` reads four plane
bytes -- `[si]`, `[bx+si]`, `[2*bx+si]`, `[3*bx+si]` with `bx = CS:[5B9C]` -- and calls **`344B`**, a
bit-interleaver that ROLs the 4 plane bytes (dh/dl/ah/al) into `cl`/`ch` 2 pixels at a time = classic
4-plane planar -> 4bpp chunky packing (with a mode-flag tail at `3473` gated on `CS:[0BD6]`).

So: blocks + graphics are stored 4-plane and **de-planarized into Tandy chunky on load** (that is why the
final dest only ~10-17% matched a flat decode -- the bytes are bit-reorganized).  The transform is
well-defined; recovering it is a focused multi-routine slice (the `33AF` loop geometry + `344B`
interleave + the `CS:[5B9C]/5B9E` stride/count + output addressing + the `[0BD6]/[0BD8]` mode tail),
with the clean verification `tandy_deplanarize(decode(G{n})) == image[CS:[95AE]]` against a gameplay
snapshot.  **Next slice:** recover that pure planar->chunky transform and verify it.

## 2026-06-30 - Planar->chunky packer (344B) recovered + verified vs real ASM

Recovered the bit-interleave core of the graphics load transform: `asset_codecs.pack_planes_344b`
(overkill/asset_codecs/planar.py), the pure form of 1010:344B.  It takes four plane bytes (LSB..MSB
order) and packs **bit 0 and bit 1** of each into two 4bpp chunky pixels -- the 33AF loop rotates the
planes by two between calls to walk the columns.  Output: the two pixels packed (pixel1 high nibble,
pixel0 low, per the closing `ROR cl,4`); in **block mode** (`CS:[0BD6]==0`, the 347B early return,
opaque) the mask passes through, in **sprite mode** (`!=0`, the 347C..34AC tail) each nibble equal to
the transparent colour is zeroed and flagged in a per-nibble mask.

Caught the mode polarity from the ASM: `75 01` at 3479 targets `347C` (sprite tail), not 347B -- so
`CS:[0BD6]!=0` is the masked/sprite path and `==0` is opaque/block (matching the 33DD output gating:
sprites emit cl+ch, blocks emit cl only).  Verified byte-for-byte against the interpreted ASM stepped
out of the image: **500/500** random cases across both modes / transparency / passed-in mask, plus unit
cases (tests/test_asset_planar.py).  lint 237 + both audits green.

So the trickiest piece of the transform is now recovered + airtight.

## 2026-06-30 - Full de-planarize DONE: all THREE per-level destinations placed + verified

Recovered the rest of the transform on top of the verified packer: `asset_codecs.deplanarize_tandy`
(the full 1010:33AF Tandy handler).  `44D7` parses a per-item `{width, stride}` 2-word header
(terminator `{0,0}`); for each of `width` rows the inner loop runs `stride` columns, each reading one
byte from four planes (`si`, `+stride`, `+2*stride`, `+3*stride`), de-planarizing the 8 pixels via the
344B packer four times (planes rotated by two per call), advancing `si` by 1 and then `+3*stride` after
the row; emitted in the mode-gated byte order (block: `cl4,cl3,cl2,cl1`; sprite: `ch4,ch3,cl4,cl3,
ch2,ch1,cl2,cl1`).  The `{width,stride}` headers come straight out of the decoded asset.

**Verified byte-for-byte against the live VM buffers for ALL SIX levels x BOTH assets** (12/12 exact):
`decode_level_blocks(n)` == `image[CS:[959A]]` (LEV{n}BLX, 28k buffers) and `decode_level_graphics(n)`
== `image[CS:[95AE]]` (G{n}, sprite bank + mask).  Added `decode_level_blocks` / `decode_level_graphics`
+ the capstone `load_level_data(container, level) -> LevelData(tile_map, blocks, graphics)`.
tests/test_level_graphics_placement.py + test_asset_planar.py; 72 asset/level tests; lint 237 + audits.

So the **whole per-level data load is now VM-free and verified end to end**: container -> decode ->
(map flat-copy | blocks/graphics de-planarize) -> the three native buffers, every byte checked against
the real game.  The cold-boot data path is essentially complete (assets -> LevelData).  Remaining for a
cold-boot level: the SHARED (non-per-level) assets (1X1/2X2/sprites/screens loaded once at startup) and
wiring `LevelData` into the native gameplay/render state (the dest segments -> NativeGameState fields).

## 2026-06-30 - MAP post-processing recovered: tile plane now byte-PERFECT + the class table

Wiring step toward `LevelTileContext` (the recovered tile-probe seam, whose fields are exactly a
tile_plane + class_table + scroll).  Recovered the MAP loader's post-decode processing (1010:0B8E-0BD2),
which is what produced the tile-map head/footer "border" the earlier body-only check had to exclude:

- `finalize_level_tile_plane(tile_map, footer)` (0BB9-0BD2): overwrite `[0:26]` with `0x01` and copy a
  65-byte footer (the `DS:D1BC` constant) over `[0x0E5F:0x0EA0]`.  With this the decoded map matches the
  live `CS:[9592]` buffer **byte-for-byte over the full 3744** (head + body + footer), all six levels.
- `build_level_class_table(override_pairs)` (0B8E-0BB7): 256 entries default `0x01`, then a per-level
  `{index,class}` override list (the `C4AA[level]` table, `0xFF`-terminated) -- matches the live
  `DS:C3AA` raw-tile->class map byte-for-byte, all six levels.

tests/test_level_tile_init.py (3); lint 237 + both audits green.  The footer (`DS:D1BC`) and the override
list (`DS:C4AA[level]`) are game data-segment constants -- passed in as params (the functions stay pure);
the test reads them from the snapshot image.

So the static level tile state (byte-perfect tile_plane + class_table) is now recovered + verified.
**Next toward wiring:** assemble a `LevelTileContext` (tile_plane + class_table + the dynamic scroll
`DS:234E/2350`) from this in an adapter, driving the recovered 5073/505B/AD60 tile probe on cold-loaded
data; and (foundational, recurring) extract the level-init data-segment constants (footer, overrides,
dest segments) from `OVERKILL.EXE` so the path is EXE-pure rather than image-read.

## 2026-06-30 - Cold-boot level loader capstone: `load_native_level` (a whole level, VM-verified)

Tied the per-level data load together into one call: `asset_codecs.load_native_level(exe_image,
container, level) -> NativeLevel(tile_plane, class_table, blocks, graphics)` (overkill/asset_codecs/
native_level.py).  `exe_image` is the unpacked OVERKILL EXE image (the level-init data-segment constants
-- the footer `DS:D1BC`, the per-level class overrides `DS:C4AA[level]`; the same bytes a real boot has
once the self-extracting EXE unpacks, i.e. memory_1mb.bin / unpack(OVERKILL.EXE)); `container` is
assets/OVERKILL.  It composes the verified pieces: decode + border the map, build the class table, decode
+ de-planarize blocks and graphics.

**Verified byte-for-byte against the live VM for all six levels** (tests/test_native_level.py): every one
of the four buffers equals its live VM buffer (`CS:[9592]` tile plane, `DS:C3AA` class table, `CS:[959A]`
blocks, `CS:[95AE]` graphics) -- the same image supplies both the EXE constants and the live buffers, so
the test proves the assembly composes correctly.  lint 238 + both audits green.

So a level's **entire static data is now cold-loadable into native buffers, VM-free and byte-exact**:
`(exe_image, container, level) -> NativeLevel`.  The recovered tile probe consumes a `LevelTileContext`
built from `tile_plane` + `class_table` + the per-frame scroll -- this loader owns the static half.
Remaining toward a running native level: the dynamic scroll/camera init + handing `NativeLevel` to the
recovered frame loop + renderer (game_core), the SHARED startup assets, and -- to drop the image
dependency -- unpacking `OVERKILL.EXE` (self-extracting) to produce `exe_image`.

## 2026-06-30 - Wiring proven: cold NativeLevel drives the recovered tile probe == the VM

First demonstration of the cold-loaded data driving a recovered gameplay system end to end.  Added the
adapter `recovered/adapters/cold_level_adapter.py::level_tile_context_from_native(native_level, origin_x,
row_base)` -> the recovered `LevelTileContext` (tile_plane + class_table straight from the cold
`NativeLevel`; scroll `DS:234E/2350` passed in as the dynamic half).  Adapters are outside the pure-layer
audit, so this can bridge `asset_codecs` -> `recovered.domain`.

`tests/test_cold_level_wiring.py`: builds the context from `load_native_level` and runs the recovered
AD60 tile probe (`object_tile_probe_deactivates_ad60`, the 5073 offset + 505B class lookup) over a grid
of object positions, asserting it matches the same probe over the **live VM tile segment** read from the
snapshot -- 500+ in-map positions, deactivations firing, all equal.  Since the cold buffers are
byte-identical to the VM (proven separately) and the recovered probe is itself VM-verified, this closes
the chain: **cold (exe_image, container, level) -> NativeLevel -> LevelTileContext -> recovered AD60
== the real game.**  lint 239 + both audits green.

So cold-loaded level data now provably feeds the recovered logic.  Next toward a *running* native level:
extend the same wiring to the whole per-frame object pass / player step / renderer over a cold
`NativeLevel` (game_core), plus the scroll/camera init; then the SHARED startup assets and the EXE
unpack.

## 2026-06-30 - Shared startup graphics banks cold-loaded + verified

(Re-extending the cold load to the non-per-level data; note the recovered systems already provably
consume cold level data, and the cold buffers are byte-identical to the VM, so re-running each recovered
system on cold data is tautological -- the remaining real progress is cold-loading NEW data.)  Found the
startup shared-asset loader at 1010:0D42-0DA3: six loads, each setting a name ptr + dest seg and calling
0CD8/0CB8.  The four 0CD8 loads are the shared graphics banks -- **`1X1.BIC`, `2X2.BIC`, `2X2C.BIC`,
`MANEXPL.BIC`** -- decoded then sprite-de-planarized (the same transform as per-level `G{n}`) into
`CS:[95A8/95AA/95AC/95A6]`.

`asset_codecs.load_shared_sprite_banks(container)` decodes + de-planarizes all four; **each matches its
live VM buffer byte-for-byte** in the menu-state bundle (tests/test_shared_assets.py: 2; lint 240 +
audits green).  Interesting: the last two startup loads are `THEND.BIC` and `PANEL.ENC` (an `.ENC` ->
LZ-decoded then de-planarized) via the 0CB8 `bd8` mode, which additionally emits a per-item dimension
directory (`CS:[0BE0]` table) -- that variant is the next transform to recover.

So the shared graphics banks now also load cold + verified.  Remaining shared/data: the `bd8`
directory-mode transform (THEND/PANEL + the per-level 3rd slot), the menu/intro/score screens (the other
`.ENC` loads), then the gameplay-state init (object spawns) for a from-scratch cold level, and the EXE
unpack.

## 2026-06-30 - bd8 directory-mode de-planarize: THEND/PANEL cold-loaded; transform family complete

Recovered the third de-planarize variant -- the 0CB8 `bd8` directory mode.  It is the block-mode
de-planarize with each item's `{width, stride}` (LE words) written into the output ahead of its data, so
the buffer is self-describing (the original also records each item's offset in a separate `CS:[0BE0]`
directory, derivable from the headers and not produced).  Added `emit_item_headers` to
`deplanarize_tandy` and `asset_codecs.load_shared_directory_asset`; `THEND.BIC` (7044 B) and `PANEL.ENC`
(51636 B, an `.ENC` -> LZ then de-planarize) match their live buffers `CS:[95B2]/[95B4]` byte-for-byte
(tests/test_shared_assets.py; existing block/sprite tests unaffected -- the new flag defaults off).  lint
240 + audits green.

So the **Tandy graphics load transform is fully recovered (all three modes: block / sprite / directory)**
and all six startup graphics loads (0D42-0DA3) now cold-load byte-exact.  The cold-boot **data** pillar is
essentially complete: per-level (map/blocks/graphics/class) + shared (sprite banks + directory assets),
every buffer byte-verified vs the VM.  Pivot note: object pools are **empty at level start** (verified in
the L*_start snapshots) -- enemies spawn dynamically via a scrolling spawner, so there is no bulk object
state to cold-load; the remaining gameplay-state init is the player + the scrolling spawn list (a deeper
gameplay-logic thread).  Remaining toward the running game: the spawn system, the menu/intro/score
screens, the full frame-loop integration over a cold `NativeLevel`, front-end flow, audio, EXE unpack.

## 2026-06-30 - All EIGHT startup shared assets cold-loaded (unified model)

Finished the startup shared-asset cluster (1010:0D42-0E0E).  Found the last two loads after the sprite
banks: `SHIP.BIC` (0CC8 block mode -> `CS:[959C]`) and `BLUEBITS.BIC` (0CB8 directory mode -> `CS:[95B8]`).
Refactored `asset_codecs/shared_assets.py` to one model -- `SHARED_STARTUP_ASSETS` (the 8 loads in order,
each tagged sprite/directory/block) + `load_shared_asset(container, name, mode)` +
`load_shared_startup_assets(container)` (replacing the earlier per-category helpers, per the converge
rule).  All **eight** match their live buffers byte-for-byte (tests/test_shared_assets.py): sprite
`1X1/2X2/2X2C/MANEXPL` (`CS:[95A6..AC]`), directory `THEND/PANEL/BLUEBITS` (`CS:[95B2/B4/B8]`), block
`SHIP` (`CS:[959C]`).  lint 240 + both audits green.

So every per-level asset and every startup shared asset now cold-loads + byte-verified.  The remaining
container assets (`LOGO`, `WINDOW`, the `*PAGE*`/menu/score `.ENC` screens, and the `ADLIB`/`ROLAND`
music banks) are loaded by the **front-end / audio** code paths, not the startup cluster -- the screens
de-planarize to banked display VRAM (renderer-bound), and the music banks feed the audio driver.  Those
are the next loading sites to trace (front-end + audio pillars).

## 2026-06-30 - EXE bootstrap scouted: OVERKILL.EXE is LZEXE 0.91 (unpacker WIP)

To drop the `memory_1mb.bin` dependency (so `exe_image` comes from the real `OVERKILL.EXE`), looked at
the EXE itself.  It is a **self-extracting LZEXE 0.91** EXE (MZ, e_crlc=0, no standard signature, a
decompressor stub at e_cs:e_ip = 0A3F:000E = file offset 42494).  Traced the full decompressor (byte-flag
stream, `bp`/`dx` bit buffer): bit=1 -> literal `movsb`; bit=0 -> match, then a sub-bit: 0 = short
(2-bit length+2, 1-byte offset `0xFF00|b`), 1 = long (2 bytes -> 13-bit signed offset `((b1>>3)|0xE0)<<8|b0`,
length `(b1&7)+2`; if `b1&7==0`, read a byte L: 0=END, 1=segment-continue, else length L+1).  Found via
capstone (the project's recovered systems run on the already-unpacked image, so there was no unpacker).

Scratch unpacker over `exe[512:]` decompresses plausible code but diverges from the live image by ~25
bytes and the output isn't found in `memory_1mb.bin` -- so the compressed-data start offset (or a stream
detail) is still off.  Parked as a focused next slice: fix the unpacker to reproduce the `CS:[1010]` image
byte-for-byte, then `exe_image = unlzexe(OVERKILL.EXE)` makes the whole cold boot run from the two
original files (`OVERKILL.EXE` + `OVERKILL`) with no snapshot dependency.  (Notes/disasm in scratch.)

**Load layout cracked (info block at stub cs:0 = file 42480):** the restored original-EXE header is
`e_ip=000E, e_cs=09AA, e_sp=0080, e_ss=0B10`; move params `[08]=0A3F` (compressed paras), `[0A]=001F`,
`[0C]=015B`.  So with runtime `CS=1010` the unpacked **load segment = 1010 - 09AA = 0x666**: the
decompressed load module byte 0 maps to `img[0x6660]`, and the code segment (`CS:1010`) is at byte offset
`09AA*16 = 0x9AA0` into the decompressed output.  **Verification target:** the decompressed output at
`0x9AA0` must equal `img[0x10100]` (the static code; `img[0x6660]` is runtime-zeroed BSS/PSP-adjacent
data, so unverifiable early).  Progress: modelling the output as a zeroed 64 KiB segment with 16-bit
offset wrap (out-of-range back-refs read 0) **fixed the byte-25 crash** -- it now decompresses cleanly to
`di=0x3ED4` (~16 KiB) and stops at an END marker.  But that is BEFORE the code at `0x9AA0`, so the stream
still misaligns to a **premature END** somewhere in the first 16 KiB.  Since the stream position is
content-independent (si advances by flag bits + literal/offset bytes only), this is a genuine bit/byte
misalignment in the decode, not an output-model issue.  **Definitive next step:** step the real stub in
the VM (load the EXE, run from `0A3F:000E`, trace its LODSB/STOSB) and diff token-by-token against the
pure decode to find the divergence -- then `exe_image = unlzexe(OVERKILL.EXE)`.

**Stub-stepping done -- two more bugs found, one residual.**  Ran the real decompressor in a CPU8086
(stub code at CODESEG:0, blob at INSEG, output at OUTSEG, entry 0x5A) and diffed per output byte:
1. **Eager flag-word reload (FIXED):** the stub reloads the 16-bit flag word *the moment* the bit counter
   hits 0 (inside that get-bit), i.e. BEFORE the subsequent literal byte -- my lazy reload read the literal
   one position early.  Confirmed at out[14]: stub si jumps +3 (reload+byte) -> `blob[0x10]=0xE3`, mine
   gave `blob[0x0E]=0xFF`.  Fix: init `bits=word0` + reload eagerly after each decrement.
2. **Segment-change re-base (0CB8/cx==1, MAPPED):** the `L==1` token is NOT a no-op -- it re-bases es:di
   and ds:si (`es += (di>>4)-0x200; di = (di&0xF)+0x2000`, same for ds:si), linearly identity but keeping
   `di>=~0x2000` so back-ref offsets never underflow.  Fires often (first at di=0xC1C, ~3 KiB), not at 64
   KiB.  Modelled as a flat-buffer base shift.
With (1)+(2) the unpacker reaches di=0x9BFB but still hits a **premature END at ~0x9AA0** (then reads the
trailing info-block + stub as literals), so the segment-change re-base is still not byte-exact.  Residual
work: validate the re-base formula against a full stub trace (capture across the stub's own seg-changes)
to kill the last misalignment.  This LZEXE unpacker is genuinely intricate (3 compounding decode details);
it is ~95% and parked -- the verified asset/data loading stands and does not depend on it.

The verified data work stands: all per-level + all 8 startup shared assets cold-load byte-exact.

## 2026-06-30 - Native game runner: the two halves meet (cold level -> recovered frames, VM-free)

Built `overkill/native_game.py::NativeGame` -- the standalone backbone where the cold-loaded level data
meets the recovered per-frame systems.  A `NativeGame` pairs a cold-loaded `NativeLevel`
(load_native_level: tile_plane/class_table/blocks/graphics, all byte-verified) with the evolving
`NativeGameState`, and advances it with the recovered 9B2E stages and NO VM:

- `NativeGame.load_level(exe_image, container, level_num, state)` -- cold-load a level + a starting state.
- `.tile_context` -- the recovered LevelTileContext over the level's cold tile plane + class table
  (via the cold_level_adapter; byte-identical to the VM's, proven by test_cold_level_wiring).
- `.step_player(frame_input)` -- the player stage (input decode + view-anchor movement bits, 9B2E).
- `.step_objects(globals)` -- the object-update pass over both pools, sampling the cold tile context.

tests/test_native_game.py: loads level 0 entirely from the original files (EXE image + container), steps
a player frame (move right -> view anchor Y advances, the recovered movement bits) and an object frame
(over the cold tile context).  2 tests; 14 across native_game+frame_loop+native_level+cold_level_wiring;
lint 241 + both audits green.  (Distinct from `overkill/game_core/`, the backend-protocol seam.)

So a level now **loads cold and runs recovered gameplay frames over it, VM-free** -- the standalone
half of the hybrid->native model is wired for the stages that are recovered.  Toward the full running
game, the remaining stages join `NativeGame` as each becomes a pure system (scripted input 99F6, action
fan-out A067, contact 9CB6, the coordinate rings, the scrolling spawn), plus the render path (compose
the playfield from the cold blocks/graphics + objects -> the verified colorize/present) and the front-end
/ audio.  The cold data + recovered-systems foundation under all of it is now in place and verified.

## 2026-06-30 - Native terrain compositor: the cold level renders natively (no VM)

First piece of the native compositor (the render-from-cold-data the standalone game needs instead of
decoding the VM-baked page).  `overkill/native_video/terrain.py::render_terrain_indices(tile_plane,
blocks)` composes a level's terrain VM-free: the cold tile map (13-col block-index grid) indexes the cold
block bank (16x16 4bpp tiles -- geometry confirmed from the BLX item header `{width=16, stride=2}` = a
128-byte block; 224 blocks in L0) -> an `(rows*16, 13*16)` 4-bit index image, colorized via the recovered
Tandy palette.  `scripts/native_demo.py` now renders the **actual level terrain** (was the tile-id map);
the result is recognisably OVERKILL's level-1 biomech terrain (wall texture, structures, a wall-creature,
open lanes).  tests/test_terrain.py (3: nibble order, out-of-range, placement); lint 243 + audits green.

So the cold level's **terrain** now draws natively.  Remaining for the standalone render: the **sprite
compositor** (player + objects -> the page, from the cold graphics bank), the **starfield**, the **HUD**
(from PANEL.ENC), and **scroll** -- composed into the page the verified present/decode already consumes;
then wire keyboard input + a loop so `NativeGame` drives it.  Built on verified pieces (blocks +
tile map byte-exact, block geometry from the header); a full byte-exact-vs-VM terrain check is confounded
by the VM baking starfield+sprites into its page, so that is a later cross-check at a fixed scroll.

## 2026-06-30 - Controllable cold level: fly through the real terrain (VM-free)

First *playable* cold-start build: `scripts/native_play_cold.py [level]` flies a ship through a level
loaded + composited entirely from the original files -- no VM.  It cold-loads the level
(load_native_level), composites the terrain (render_terrain_indices), and runs a real-time pygame loop:
arrow keys move the ship, the level auto-scrolls, the visible 208x192 playfield window is colorized with
the recovered palette each frame.  A headless `--gif out.gif` mode renders a scrolling clip without a
display (used to verify the render here).  `playfield_frame(terrain, scroll, ship) -> RGB` is the testable
core (tests/test_native_play_cold.py: shape, window, ship marker, scroll clamp).  lint 244 + audits green.

So you can now **run a level from cold start and steer through the real terrain** -- the data, terrain
compositing, and movement are all VM-free.  The player is a placeholder marker; remaining for full
gameplay: the **sprite compositor** (the real ship + enemies from the cold graphics bank / SHIP.BIC),
the **scrolling spawn** (enemies entering), the **HUD** (PANEL.ENC), and wiring `NativeGame`'s recovered
step into the loop (it currently auto-scrolls + moves the marker; the recovered movement/object stages
plug in next).  Then the front-end + audio for a complete standalone game.

## 2026-06-30 - Whole-scan attempt 2 (shared store): real blocker is a variant-2 candidate kill (logged)

Built the corrected shared-store whole scan (one contiguous 0x45-slot store, both pointer-table loops
in place -- the design from the previous entry) and verified at AA25.  The shared store was the right
model (the effect loop now feeds the gameplay loop), but a **separate** ~2-slot/frame divergence
remained that neither separate-pools nor the shared store fixed -- so it was reverted (red) and logged
in loop_blockers.md (OPEN 2026-06-30).

Root cause (pinned, not yet fixed): a `logic_id=2` (AED8) gameplay slot the VM **deactivates in the
effect loop as a collision candidate** (active->0, substate untouched) but my effect-loop collision
does not kill, so my gameplay loop AED8-processes it (active=1, moved).  Confirmed NOT AED8 timer-death
(substate far from 0) and NOT a tables-overlap bug.  Needs a VM trace of one failing slot (L2 0x2ce4)
to find the scanner + BEC5 path that kills it -- likely an order-dependent candidate interaction or a
candidate-deactivation path not yet modelled (owner-link, or a BD0D/BD17 neighbour effect).

Per discipline: reverted, logged, moving on.  Everything else stays verified + committed -- the
per-slot driver (incl. collision death), the effect-loop in-place pass, the gameplay snapshot, and all
the collision systems.  Only the *combined* whole-scan is open; it is the last assembly step for a
fully VM-free object pass and is now precisely scoped in loop_blockers.

## 2026-06-30 - Whole-scan attempt: the 32CA/8D12 walks SHARE slots (model correction, reverted)

Attempted to compose the whole object scan (`native_object_scan` = the effect in-place pass + the
gameplay snapshot pass) and verify it end-to-end at AA25.  The gate caught a real model error, so it
was reverted (not committed red) -- but the finding corrects the mental model for the next attempt:

The effect loop (32CA pointer table) and the gameplay loop (8D12) are **NOT disjoint** -- some DS:2B5C
gameplay slots are visited by the 32CA effect walk too.  In the VM those shared slots are processed in
the effect loop (moved / deactivated by a collision) and so are inactive by the gameplay loop, which
skips them.  My `native_object_scan` captured the effect walk and the gameplay pool as SEPARATE pools,
so the effect loop's update/deactivation of a shared slot did not propagate to the gameplay pool -- the
gameplay loop then re-processed a slot the VM had already handled in the effect loop.  Symptom: effect
1170/1170 (perfect) but ~2 gameplay slots/frame off by exactly one move (x +8, substate +1, active 1 vs
0) on L2 and L3 -- the tell-tale "processed in the wrong loop" signature.

(Why verify_native_object_pass still passes: it captures the gameplay pool at AA0D = the VM's *actual*
post-effect state, where those shared slots are already inactive, so its snapshot correctly skips them.
The bug is only in re-deriving that post-effect state from separate pools.)

**Corrected design for the whole scan:** a single offset-keyed slot store both loops mutate in place --
the effect loop walks 32CA, the gameplay loop walks 8D12, both reading/writing the SAME slots by
offset, so a shared slot's effect-loop result is what the gameplay loop sees (and skips if dead).  The
per-loop pieces are unchanged and still verified (native_object_pass_in_place effect scan; the gameplay
snapshot); only the composition needs the shared store.  That is the next focused build.

## 2026-06-30 - The VM-free ORDER-DEPENDENT object pass (effect scan, verified incl. collision)

Built the order-dependent in-place object pass -- the integration the per-slot driver could not be:
the runnable VM-free object scan. `object_update.native_object_pass_in_place(walk_pool, candidate_pool,
globals, entry_tick)` mirrors the VM's A9E0 loop faithfully for collision -- it walks the slots in the
DS:32CA pointer-table order, advances each active native slot with its per-entry tick (DS:2340 inc +
wrap at 5DCh, one per walk entry), runs the 62F6 collision against the LIVE candidate pool, and clears
a killed candidate's active word in place so later scanners skip it. Refactored the driver's collision
fold into `_collide_post_move` (returns the scanner updates + the full result) so the candidate
deactivation flows out to the pass; the per-slot `_fold_bc4b_collision` is now a thin wrapper.

VERIFIED produced-vs-VM by `overkill.probes.verify_native_object_pass_in_place` (capture the 32CA walk
order + entry tick + the live DS:2B5C candidates at the first A9E0, run the pass, compare every visited
active native slot's 6-tuple + logic_id at the scan exit AA07): L2_full 1170/1170, L3_full 1723/1723,
0 divergence -- 2893 effect-scan slots incl. the order-dependent collisions/deaths (L6_boss is
NO-EVENTS: its effect loop has no native slots). The per-slot driver + the snapshot pass are unaffected
(refactor verified: driver L3 1365/1365 sprite_deferred 0); 8 collision-fold unit tests + lint + audits
green. No hook touched.

So the THREE forms of the native object update are now all proven: per-slot driver (handler boundary),
snapshot pass (movement whole-pool), and now the order-dependent in-place pass (the VM's actual A9E0
loop incl. collision). The remaining wiring is to make frame_loop.native_object_pass run the in-place
pass over both pointer-table loops (effect 32CA then gameplay 8D12) so the standalone runtime's object
update is a single VM-free call. The hard semantics + the order-dependence are done.

## 2026-06-30 - Collision candidate side: which enemy dies (the in-place-pass prerequisite)

The whole-pool VM-free object pass needs the CANDIDATE (enemy) side: when a scanner kills an enemy,
that enemy must deactivate so later scanners in the same pass see it gone. Recovered that: the BEC5
reaction deactivates the struck candidate for logic ids 5/6/7/8/Ch (BD0D -> BD17 active:=0) and 2 (the
active-clear), but NOT 9 (the scanner is hurt, the candidate survives).

`collision.bec5_candidate_deactivated(candidate_logic_id) -> bool` names that set, and
resolve_moving_object_collision now also reports `hit_index` (which gameplay candidate was struck) and
`candidate_deactivated` -- so both objects' fates are characterized: the scanner's counter/death/sprite
AND the candidate's deactivation.

VERIFIED produced-vs-VM by extending `verify_native_moving_object_collision` to also compare the struck
candidate's active word at the scan return (0 when deactivated, unchanged otherwise): L2 cand 31/31
(deact 31), L6_boss cand 158/158 (deact 158), 0 fail -- alongside the scanner checks (3394/3394,
3268/3268). Unit coverage in tests/test_bec5_outcome.py + tests/test_moving_object_collision.py (48
collision tests green). No hook touched; lint + both audits + manifest green.

So the object-vs-object collision is now fully characterized for BOTH objects. This is the last piece
the order-dependent whole-pool object pass needs: walk the gameplay pool in place, and when a scanner
kills a candidate, clear `hit_index`'s active so later scanners skip it. That in-place walk (+ the
effect-loop per-entry tick + the candidate's full BD17 cleanup) is the remaining integration for a
VM-free object PASS; the per-slot driver + both-object collision semantics are done.

## 2026-06-30 - DEFERRAL RETIRED: the object-update driver now folds the collision death (native)

Wired resolve_moving_object_collision into the object-update driver -- the integration the
convergence-point entry teed up -- and it landed cleanly. The key insight that made it tractable: the
collision deaths that the per-slot driver gate was deferring (`sprite_deferred` 7 on L2, 19 on L3) are
**effect-loop** scanners, and an effect scanner's 62F6 candidates are the **gameplay pool**, which is
*stable* during the effect loop (the gameplay loop runs after). So those deaths have stable candidates
and no self-overlap -- exactly the case the snapshot driver could not see but the per-slot path can.

`object_update._fold_bc4b_collision` folds resolve_moving_object_collision into a B86D/B9F0 slot's
post-move updates: when the per-frame `candidate_pool` is provided (and DS:A47C==0, the BC4B contact
gate), a classified collision death overrides the slot's sprite + logic_id (1) + counter_20, and a
damage-survive folds the new counter. It is OPT-IN (candidate_pool defaults None) so the snapshot
native_object_pass and the hybrid runtime are untouched; no hook uses the driver with a candidate pool.

VERIFIED by tightening `verify_native_object_update_driver` (capture the DS:2B5C pool + DS:A8C2 + BEDC
at each B86D/B9F0 entry, fold the collision, and compare the FULL slot incl. the death sprite + the
contact-set logic_id -- no more sprite deferral): **L2 1449/1449 sprite_deferred 7->0, L3 1655/1655
19->0, L6_boss 6596/6596 0**, all fail=0. The snapshot pass is unaffected (verify_native_object_pass
still 662/662), 29 unit tests green incl. the new tests/test_object_update_collision_fold.py. The
remaining deferral is only the owner-link / unclassified contact death (0 in these demos).

**So the per-slot native object-update driver is now complete incl. object-vs-object contact death** --
movement + tile + bounds + collision, byte-exact vs the VM. The collision island is fully integrated
into the object driver. Remaining for a VM-free object PASS (whole-pool): the order-dependent gameplay
loop (collision candidates evolve there) + the effect-loop per-entry tick; the per-slot path is done.

## 2026-06-30 - Convergence point: gameplay-frame leaves are recovered; the order-dependent pass is next

After the collision capstone, surveyed what's left of the gameplay frame and found a clear
convergence. **Both major stateful subsystems now have their leaves recovered AND verified
produced-vs-VM:**
- **Collision** (this session): the whole moving-object fate -- object_overlap_scan_62f6 (which
  candidate) + bec5_moving_object_outcome (reaction) + resolve_collision_hit (damage->C037 death),
  merged into resolve_moving_object_collision, verified end-to-end (6662 collisions, 0 divergence).
- **Spawn** (already done): the allocator object_pool_find_free (7573) + all four spawn seeds
  (8209/a4ea/7420/7476) each have produced-vs-VM probes (verify_native_allocator / _spawn_seed*).

So the remaining gameplay-frame work is **not more leaves -- it is one integration**: an
**order-dependent native object pass**. The current native_object_pass is snapshot-based (it projects
the pool once, advances each slot independently with frozen globals), which is exactly right for
movement (verified whole-pass) but **cannot** carry collision or spawn, because:
1. the collision scan (62F6) reads the *evolving* pool -- a later slot sees earlier slots' new
   positions/deaths; a frozen snapshot is stale;
2. spawns mutate the pool mid-walk (new slots appear for later iterations);
3. the per-slot driver gate predicts from the slot's *handler-entry* state, but 62F6 runs *after*
   that slot's movement -- so even per-slot, the candidate pool must be the post-move-time one.

The faithful native object pass must therefore walk the pool **in order, mutating it in place**, so
each slot's collision/spawn sees the prior slots' updates -- matching the VM's A9E0 walk. That is the
next major integration (and what finally retires the object pass's death-sprite deferral). Open
questions to resolve when building it: whether the moving-object scanner self-overlaps (depends on the
projectile's +1Eh scan_enable_or_solid -- the boss demo's 101 "unclassified" reactions are either
self-hits or owner-linked), and the effect-loop's per-entry DS:2340 tick evolution (the gameplay loop
froze cleanly because only the effect loop increments it). No code this entry -- it records the
convergence so the integration is built deliberately rather than bolted onto the snapshot pass.

## 2026-06-30 - Collision island CAPSTONE: the whole moving-object collision, verified end-to-end

Merged the three recovered collision systems into the moving object's complete BC4B contact result.
`collision.resolve_moving_object_collision(scanner fields, candidates, a8c2_boss_mode, bedc) ->
MovingObjectCollisionResult` chains them the way BC4B does: object_overlap_scan_62f6 (which gameplay
candidate) -> bec5_moving_object_outcome (damage vs instant death) -> resolve_collision_hit (the
BF25 chain -> C037 death) or a direct counter_20:=0 + C037 for the instant-death case. Returns the
scanner's post-collision counter / died / death-transition; ``unclassified`` flags the owner-link
fallback (left to the VM).

VERIFIED produced-vs-VM END-TO-END by `overkill.probes.verify_native_moving_object_collision`: at
each 62F6 scan it projects the scanner (SS:BP) + the whole gameplay pool + globals, runs the composed
system, and compares the scanner's actual post-state (counter_20, logic_id, sprite) at the scan's
return -- L2 3394/3394 (30 died, 1 survived, 3363 no-collision), L6_boss 3268/3268 (23 died, 135
survived, 3110 no-collision, 101 owner-link unclassified) -- 6662 collisions, 53 deaths + 136
survives, 0 divergence, and bad_type=0 (the projectile object types are 1/2, so C037 covers every
death). Unit coverage in tests/test_moving_object_collision.py.

This is the collision-island capstone: a moving object's WHOLE object-vs-object collision -- which
enemy it hits, the reaction, and its resulting counter/death/sprite -- is now one pure system proven
against the VM's real slot mutations. It is exactly the death sprite the object pass currently defers,
so the next slice wires `resolve_moving_object_collision` into the B86D/B9F0 driver advance (after
object_postmove_bc4b) to retire `verify_native_object_update_driver`'s sprite_deferred. Remaining for
the full system (the CANDIDATE/enemy side): the BD0D wrapper (-> the already-lifted BD17 deactivation),
the variant-2 active clear, the A8C2 boss-group mark, and the owner-link path. No hook touched; lint +
both audits + manifest green.

## 2026-06-30 - Collision pass: the BEC5 reaction outcome -> the moving object's fate is now native

The bridge between the 62F6 scan and the per-object hit outcome. When the scan finds an overlap it
enters BEC5, which decides the SCANNING object's fate by the collided candidate's logic id. Recovered
that decision as `collision.bec5_moving_object_outcome(candidate_logic_id, a8c2_boss_mode,
candidate_sprite) -> Bec5MovingObjectOutcome`:
- candidate logic id {5,6,7,8,9,Ch}: BF25 damage in final-boss mode (DS:A8C2==1), else instant death
  (counter_20:=0 -> BFC7);
- candidate logic id 2: always damage, entering at BF25 (two decs) when its sprite is 33h else BF2D;
- any other logic id: the owner-link / no-op fallback (left unclassified -- the moving object's
  fate there depends on the +30h owner pointer, a separate path).

VERIFIED produced-vs-VM by `overkill.probes.verify_native_bec5_outcome` (project the candidate +
A8C2 at BEC5 entry, classify, then watch the VM: predicted damage -> reaches BF25/BF2D with the
matching entry; instant_death -> reaches BFC7 without the chain): L2 31/31 (all damage), L6_boss
158/158 (152 damage + 6 instant_death), with 101 owner-link cases correctly reported unclassified --
189 classified reactions, 0 divergence (both paths + the enter_at_bf25 flag). Unit coverage in
tests/test_bec5_outcome.py.

**Milestone: the moving object's whole collision fate is now native + verified** -- the three pieces
compose end to end: `object_overlap_scan_62f6` (which candidate) -> `bec5_moving_object_outcome`
(damage vs instant-death) -> `resolve_collision_hit` (the damage chain -> C037 death). What remains
for the full object-vs-object system is the CANDIDATE side (BD0D family counters, the variant-2
active clear, the A8C2 boss-group mark) + the owner-link path; those feed retiring the object pass's
death-sprite deferral. No hook touched (pure adds over verified leaves); lint + both audits + manifest
green.

## 2026-06-30 - Collision pass: the 62F6 object-vs-object overlap scan (which candidate is hit)

Continuing the collision pass toward a VM-free collision stage. After merging the per-object
hit->death outcome, the next piece is the SCAN that decides *which* candidate is hit. 62F6 is the
object-vs-object overlap scan: a moving object (the scanner at SS:BP, reached via BC4B) walks the
gameplay pool (DS:2B5C) and, on the first overlapping candidate, jumps to BEC5 with BX at that
slot; none -> returns without BEC5. The overlap *predicate* (object_grid_overlap_62f6) was already
recovered; this composes it into the whole scan.

`collision.object_overlap_scan_62f6(scanner fields, candidates) -> int | None`: the pre-scan gates
(inactive scanner / X < 20h signed / zero draw-layer or logic-id / dying-1 / exempt-26h all -> None),
then walk the pool and return the first active + solid (scan_enable_or_solid +1Eh != 0) candidate
whose 8px cell the scanner overlaps -- the slot the original routes to BEC5.

VERIFIED produced-vs-VM by `overkill.probes.verify_native_overlap_scan_62f6` (project the scanner +
the whole gameplay pool at 62F6 entry, scan, then compare: predicted hit index i -> the VM reaches
BEC5 with BX == 2B5C + i*38h; predicted None -> the VM returns without BEC5): L2 3076/3076 (26 hits),
L6_boss 3369/3369 (259 hits), player_death 6996/6996 (0 hits) -- 13441 scans, 285 real collisions,
0 divergence (both the hit and empty paths). Unit coverage in tests/test_overlap_scan_62f6.py.

So the native collision pass now has: the SCAN (62F6, which candidate) + the per-object hit OUTCOME
(resolve_collision_hit, BF25+C037). Remaining for a VM-free collision stage: the BEC5 reaction
DISPATCH that connects them (variant family -> BD0D/A8C2/damage), then wiring it over the pool. No
hook touched (pure add over the verified overlap predicate); lint + both audits + manifest green.

## 2026-06-30 - Collision island-merge: the per-object hit -> death outcome (BF25 + C037)

Resuming the gameplay frame (Bucket A) after the docs reconciliation. Scouted the remaining
stages and confirmed they're deep native-izations of *already-lifted* stateful systems, not
clean new native stages: the spawn fan-out (A067/A958 + the 7524 allocator) is heavily lifted
already (children compose); the collision-death contact path (BC4B -> BCCB + the 62F6
object-vs-object scan) is a stateful pool interaction, lifted in object_postmove.py /
contact_side_effects.py. So the clean move here is a **Phase-7 island merge**, not a new stage.

The two per-object collision leaves were recovered but lived in *separate* adapters -- the BF25
damage chain (`collision_damage_counter_chain_bf25`, used in contact_side_effects.py) and the
BFC7/C037 death transition (`object_collision_death_transition_c037`, used in
object_deactivation.py). Merged them into the single per-object outcome a hit produces:
`collision.resolve_collision_hit(counter_20, bedc, object_type, logic_id, enter_at_bf25)` ->
`CollisionHitOutcome(new_counter_20, died, death_transition)`. It runs the decrement chain and,
exactly as BF25 jumps to BFC7 the instant a decrement hits zero, stamps the C037 dying state
(logic_id -> 1 + death sprite) on death, else None. Survival's hit-react (`bp+36=5`) and the
A8C2 boss-group fan-out are pool/adapter side effects, explicitly out of this per-object outcome;
the non-1/2-type death path inherits C037's unverified-type raise.

Verification: both leaves are already demo-replay-verified in their adapters, and the merge
composes them in the exact BF25 -> (jz) BFC7 -> C037 order read from the disasm; sealed with
tests/test_collision_hit_outcome.py (10 cases: base/variant-2 decrement counts, the BEDC 0/1/2
gates, the 16-bit-wrap of a 0 counter, the death-transition fields + sprite-by-type, and that a
survivor never consults C037). This is the native-side per-object collision outcome the VM-free
collision pass will use; the hybrid adapters keep their ASM-faithful split. No hook touched, so
demo-replay is unaffected; lint + both audits + manifest (unchanged) green.

## 2026-06-30 - Finish-the-gameplay-frame: recover the contact tile-collision probe (4FF9)

User chose "finish the gameplay frame" toward cold boot.  Scouted the remaining 9B2E stages and the
cleanest was the contact probe -- another compose-verified-leaves win: 1010:4FF9 (the 9CB6 contact
stage's worker) is a non-destructive tile-collision probe whose leaves were ALREADY recovered in
tilemap.py (compute_tile_probe_5073, lookup_tile_class_505b, the side gate + sampling plan).  It just
needed the composition.

`tilemap.probe_tile_contact_4ff9(object_x, object_y, side_index, offset_table, tiles) -> bool`: gate
side >= 3 -> contact; apply the side's DS:214E dx/dy offset; map through 5073; sample one or two tile
columns (each optionally with its neighbouring Y tile when Y isn't 16-aligned) through the C3AA class
table; return CF (set = a non-zero tile class was hit).  Non-destructive (the original saves/restores
the slot coords), so only the boolean is observable.

VERIFIED produced-vs-VM by `overkill.probes.verify_native_tile_contact` (project slot + DS:214E + the
tile context at 4FF9 entry, probe, compare the VM's CF at the return): L2 600/600, mothership 32/32,
**L5_ringlas 553/553 including 81 actual contacts** -- 0 divergence, so BOTH the clear and the blocked
paths are byte-exact.  Unit coverage in tests/test_tile_contact_probe.py (side gate, clear/blocked,
single vs second column, adjacent-Y, the offset table).  No hook touched (pure add over existing
leaves); lint + both audits + the manifest (unchanged -- tilemap.py opts out of @recovered_island) green.

Note: the 9CB6 stage itself discards 4FF9's CF (both branches RET), so the value of this recovery is as
the shared tile-collision PRIMITIVE the native movement/collision paths need -- not a state mutation in
9CB6.  Remaining frame stages are still the deep spawn/script islands (A067 A958 table, 99F6, A212, rings).

## 2026-06-29 - Native frame controller stage: the object pass, verified WHOLE-POOL (not just per-slot)

Added the controller's object-update stage and lifted its verification from per-slot to whole-pass.
The VM's object scan is at A9E0 (in A940, after 9B2E): two loops -- the effect table (DS:32CA
pointers) then the gameplay table (DS:8D12 pointers) -- each active slot dispatched via AA2B to the
behaviour handlers the driver already reproduces per-slot.

`frame_loop.native_object_pass(state, globals)` runs the object-update driver over the gameplay +
effect pools (not the view-anchor -- that is the player stage's), the controller's counterpart of
the A9E0 scan.  New `overkill.probes.verify_native_object_pass` proves it at the gameplay-scan
boundary: at AA0D it projects DS:2B5C + the frozen per-frame globals, runs the driver ONCE, and at
the scan exit (AA25) compares every slot that was active with a native logic id at entry -- L2_full
`1203/1203`, L6_boss `6596/6596`, 0 divergence (player_death has no native gameplay slot ->
NO-EVENTS).  So the driver is now a verified PASS, not just verified handlers.

Why the gameplay loop can be frozen-projected (and the effect loop cannot, yet): the first/effect
loop increments the tick DS:2340 once per entry, so its globals evolve per slot; but DS:2346 is reset
at AA07 and the gameplay loop never touches DS:2340, so across the gameplay scan the globals are
constant.  A whole-pass effect verify needs per-step tick evolution in the driver first -- noted.

Reconnaissance (so the remaining 9B2E stages are not re-scouted): the clean compose-verified-leaves
wins are done; every other frame stage delegates to a deep subsystem -- **99F6** = the scripted-input
ENGINE (A47C jump table, object spawn via 7524, per-state scripted DS:98BE + counters; drives
boss/cutscene auto-movement); **A212** = the linked sidearm/satellite chain coord updater (A3B4
FFFF-lists); **A067** = the action/fire fan-out (gates already pure; the A958 spawn jump table is the
frontier); **8546** = secondary-fire spawn; **9CB6** = `call 4FF9` contact; **9C01 + A33A/A33C** =
sidearm auto-fire axis + the player-position ring buffers.  Each is a multi-part island, not a compose.

No hook touched (pure composition over verified leaves), so demo-replay is unaffected; lint + both
audits green; unit coverage in tests/test_frame_loop.py.

## 2026-06-29 - The native frame controller: the recovered systems sequence themselves (pillar 3)

First time the recovered systems run a frame *without the VM sequencing them*.  New module
`overkill.recovered.systems.frame_loop` is the VM-free counterpart of 9B2E: it sequences the
recovered systems over the native state, the same order, no VM.  `native_player_frame_step`
composes the two native stages that share a data flow -- decode the input from the raw key
state itself (not the VM's DS:98BE), then apply the movement bits to the view-anchor pool
(DS:237C = NativeGameState.special_pool slot 0, confirmed via the adapter).  Returns the updated
pool + the decoded flags the later fire/action stages will consume.  (`native_play.py` is the
render presenter; this is the missing game-logic seam.)

VERIFIED produced-vs-VM by `overkill.probes.verify_native_frame_loop` -- and this one verifies
the *composition*, not just the stages separately: at 9B6F it builds the native FrameInput from
the raw DS:98C4 key table + the control map, runs the controller, and asserts BOTH the decoded
flags == the VM's DS:98BE AND the stepped anchor == the VM at 9B97.  L2_full `750/750`,
player_death `583/583`, L6_boss `641/641` -- 0 divergence.

The gate earned its keep: the first L6_boss run FAILED 109/750 where the separate input and
movement probes each passed.  Root cause (a real find): when DS:A47C != 0 (boss/cutscene mode)
9B2E first runs **1010:99F6**, a SCRIPTED-INPUT OVERRIDE -- `mov [98BE],0` then a jump table on
A47C that writes scripted values (e.g. `mov [98BE],08h` auto-up).  So in those frames the input
is a script, not the keyboard.  The composition probe now scopes to the normal path (A47C == 0)
and reports the scripted frames (L6_boss: exactly the 109).  The no-clamp movement path is still
covered by the standalone movement-bits probe (which reads the VM's real DS:98BE).

Next: **99F6 is the next 9B2E stage** -- the scripted-input state machine (A47C jump table,
9DB9/9DEA, the A47C advance) that drives boss/cutscene auto-movement.  Recover it and the
controller's input stage covers boss mode too; then the 8546 secondary fire and the A067 fan-out.

## 2026-06-29 - Native frame loop stage 2: the 9B2E movement-bits stage (compose, don't re-recover)

With the input poll native, the next 9B2E stage fell out of already-recovered pieces.  Frames
9B6F..9B94 test the four DS:98BE direction bits and step the player-controlled view-anchor slot
(DS:237C, SS:BP) via A5D1/A5EA/A5F9/A607 -- which were already VERIFIED pure systems
(two_pass_axis_clamp_step / one_pixel_axis_step).  So this stage is a *composition*, not a new
recovery: `overkill.recovered.systems.movement.step_view_anchor_by_input(x, y, input_flags, *,
no_clamp)` applies the four bits in the original order onto the slot's X/Y.

Pinned the mapping from the 9B2E dispatch + the A5xx disasm (the screen axes are transposed vs the
controls): up(0x08)->X toward 0x20 (or one unclamped pixel when DS:A47C set), down(0x04)->X toward
0xC0, right(0x01)->Y toward 0xB0 (unsigned below test), left(0x02)->Y toward 0x00.  Only A5D1
consults the no-clamp gate.  (The "x_step_left" handler names are screen-oriented misnomers; the
field/limit/direction contract is what's verified.)

VERIFIED produced-vs-VM by the new `overkill.probes.verify_native_movement_bits` (project slot+input
at 9B6F, step, compare SS:BP X/Y at the stage exit 9B97): L2_full `600/600` (396 moved), L6_boss
`700/700` (510 moved), player_death `583/583` (130 moved) -- 0 divergence (showcase is an attract
path that never reaches the stage -> NO-EVENTS).  Unit coverage in tests/test_movement_bits_stage.py
(clamps, opposed-bit ordering, the below-condition, diagonals).  No hook touched, so demo-replay is
unaffected; lint + both audits + the island manifest green.  merge_target=FrameLoop (the first stage
tagged for the native frame controller rather than a per-object system).

Next: the remaining 9B2E stages after the movement bits -- the secondary-fire branch (8546, gated on
[2350]>B6 + bit 0x20), then A66F, the A067 action fan-out (gates already pure), and the coordinate-ring
maintenance (A616/9D4D) -> toward a native frame controller that sequences input -> object-update ->
movement -> action.

## 2026-06-29 - Recover the input poll (0162/017E) as the canonical pure decode + native source

The frame loop's first stage is now native.  The 0162 keyboard path is a pure decode of two inputs --
the eight-scancode control map (DS:213E, or DS:2146 when DS:[0010]==2) and the 256-byte INT 9 key-state
table (DS:98C4) -- so it became one canonical rule in `overkill.recovered.systems.input`:

* `pack_control_map_bits` -- the 017E core (MSB-first pack: first map entry -> bit 7).
* `decode_keyboard_input_flags` -- the full 0162 keyboard decode (control-map pack OR the six hardwired
  arrow/Space/Tab keys) -> the DS:98BE button byte (01 right, 02 left, 04 down, 08 up, 10 fire, 20 secondary).
* `key_state_from_pressed` -- the native input source: a host pressed-scancode set -> the key-state table
  the decode consumes, replacing the INT 9 ISR.  No VM, one rule, shared by both hosts.

The lifted hook (`input_menu.run_input_poll_0162` keyboard branch) is now a thin adapter: it replays the
original register/SI/flag mechanics (017E pack + a CMP+OR per fixed key) for verifier-compat, then **stamps
DS:98BE from `decode_keyboard_input_flags`** so the VM path and the native path cannot drift.  The fixed-key
table is now imported from the one definition (dedup).

VERIFIED produced-vs-VM by the new `overkill.probes.verify_native_input_poll`: at every 0162 keyboard entry
on the oracle side it projects the control map + key state, runs the pure decode, and compares DS:98BE at the
return -- L2_full `600/600`, L6_boss `750/750`, player_death `751/751`, 0 divergence (joystick path is a host
port concern, skipped).  Byte-exactness of the rewired hook itself is held by test_demo_replay_equivalence
(23 passed) + unit tests (tests/test_input_decode.py).  Lint + both layer/arch audits green.

(Also fixed a pre-existing red: regenerated docs/overkill/recovered_islands.md, stale since 9dcd0b7 added
@recovered_island to object_delta_5e1b without rerunning gen_island_manifest.py.)

Next concrete stage: continue decomposing 9B2E -- the object-slot bookkeeping and the four direct movement
bits after the input poll -> toward a native frame loop that drives the (already native) object-update pass.

## 2026-06-29 - Open the VM-free frame-loop pillar: the 9B2E/97B2 stage map + next targets

Mapped the frame loop (the object-update pillar being essentially complete).  The frame is two nested
controllers, and the VM-free frame loop = decomposing their stages into native systems (the same
decompose-and-verify pattern the object-update followed):

`1010:97B2` (frame loop) calls, in order: 0672, **511F** video page-toggle (lifted ✓), A846, 981F (cond),
5BDC, **A90C present/render scan** (native_video composes this ✓), **9B2E** (the game-state controller --
the bulk), the A344/A342/A346 mode-transition branches, A940, 073C service gate, 60A2 status text.

`1010:9B2E` (game-state controller) stages (per its own contract): **0162 input poll** (first stage) ->
the current BP object slot + the per-slot object-update (**the native driver ✓**) -> four direct movement
bits -> the **A067** action/helper fan-out (its trigger/latch gates are pure ✓) -> the optional **9CB6**
contact probe -> coordinate-ring maintenance -> linked child-coordinate propagation.

Native status across the frame: object-update ✓ (driver), render/present ✓ (native_video), video toggle ✓
(511F), A067 input gates ✓ (partial).  NOT yet native: **input (0162/017E keyboard decode)**, the 9B2E
game-state stages (object-slot bookkeeping, movement bits, 9CB6 contact, coordinate rings, linked-child),
the status text (60A2), and the mode transitions.

Next concrete stage: **the input poll (0162 + the 017E 8-key bit-packer)** -- the frame's first stage and
a bounded keyboard/joystick decode (DS:213E/2146 tables -> the input flags DS:98BE that the A067 gates
already consume).  Recover it as a pure decode (keyboard state + table -> flags) + a native input source,
verified produced-vs-VM like the handlers.  This is a fresh subsystem (input), best started fresh.

## 2026-06-29 - Tighten the driver-verify: sprite confirmed for non-death; contact path bounded to ~1%

Before recovering the BC4B contact path, measured how much it actually matters.  The contact path's only
slot-field effect is the collision death (BFC7 -> C037 sets logic_id 1 + the death sprite), so the
driver-verify now compares the sprite for B86D/B9F0 on EVERY slot and defers it only when the VM's post
logic_id == 1 (an actual death), instead of skipping sprite blanket.

Result, PASS 0 divergence: L2_full 700f `1440/1440 ok, sprite_deferred=7`; L3_full 800f `1651/1651 ok,
sprite_deferred=19`.  So the driver's movement sprite is now VERIFIED correct for every non-death slot
(~99% of B86D/B9F0), and the remaining BC4B contact-path work is precisely bounded + quantified: just the
collision-death sprite/logic_id on ~1% of slots.  lint 221.

Implication for priorities: the contact path (62F6/BFC7 -- a stateful object-vs-object scan, the hardest
remaining object-update piece) affects only ~1% of slots, so it is lower-value than the next pillar.  The
VM-free **frame loop** around the now-substantially-complete driver is the higher-value next step; the
contact path's pieces (the recovered collision island) are ready to compose when we do tackle it.

## 2026-06-29 - B9F0 added to the VM-free driver -> it now runs all 4 handlers across L2/L3/L5

Wired B9F0 into the native object-update driver (the B86D recipe): `_advance_b9f0` composes
`object_update_b9f0` (movement half) + `object_postmove_bc4b` (post-move y/active).  Extended
`ObjectUpdateGlobals` with B9F0's DS globals (default-safe) and added `ObjectPool` accessors
(move_delta_x/y).  Extended the driver-verify probe to B9F0 (its chain RETs to the walk like B86D; the
skip-sprite set is now {B86D, B9F0} since both defer the contact-path sprite).

Driver-verified PASS, zero divergence:
- L2_full 700f: 1440/1440 (B86D + AED8)
- L3_full 800f: 1651/1651 (B9F0 + AED8)
- L5_continue 400f: 2226/2226 (AE09 + AED8)

So the VM-free object-update driver now runs **all four wired handlers (AE09 / AED8 / B86D / B9F0)**
across all three levels, reproducing the VM byte-for-byte on the fields it owns.  unit tests 2; lint 221;
audits pass (27 pure files).  Next: the BC4B contact path (62F6/BFC7 -> removes the deferred-sprite
caveat), the VM-free frame loop around the driver, then the raw-ASM handlers.

## 2026-06-29 - Decouple B9F0's movement half into a canonical pure system (driver-ready)

Same decouple-and-reuse as B86D: moved B9F0's branch logic out of the coverage-gate probe arm into the
canonical pure system `object_update_b9f0` (+ domain `B9f0MovementResult`) -- all four paths (Path A
sprite-refresh / the reached-target BA5A helper or plain refresh / the overshoot 5E42 step / the 5DB2
target seek), producing the slot at the BC4B handoff.  The gate's `_arm_b9f0` is now a thin adapter that
projects the slot fields + B9F0 DS globals and calls it; removed the now-unused movement imports
(`object_delta_5e1b`/`5e42`/`5db2`/`MovementTarget`) and the duplicated constants from the probe.

This is the reuse opportunity made concrete: the gate arms were correct logic only VM-coupled at the
input edges, so a small refactor turns them into pure systems both the gate and the driver use.  Both
B86D and B9F0 movement halves now live in `systems`; the probe arms are pure projection.  Gate-verified
byte-exact: B9F0 `1723/1723`, AED8 `735/735` on L3 (behaviour preserved).  lint 221; audits pass (27 pure
files).  Next: add B9F0 to the driver (the B86D recipe -- `_advance_b9f0` = object_update_b9f0 + object_postmove_bc4b).

## 2026-06-29 - B86D added to the VM-free driver (movement + BC4B), driver-verified on L2

Wired B86D into the native object-update driver: `_advance_b86d` composes `object_update_b86d` (the
movement half -> BC4B handoff) with `object_postmove_bc4b` (the post-move y/active).  Extended
`ObjectUpdateGlobals` with B86D's DS globals (default-safe: AE09/AED8 ignore them) and added `ObjectPool`
accessors (target_x/y, move_step_error).  Extended the driver-verify probe to B86D: its final slot is
captured at the chain return (B86D -> BC4B -> RET to the walk, the same return-address boundary AE09 uses);
per the verified BC4B invariant the deferred contact path only touches sprite/logic_id, so the compare
checks the five fields the driver owns (substate/dir/x/y/active) and skips sprite (the gate still verifies
sprite at the handoff).

Verified PASS, 0 divergence: L2_full 800f `1440/1440 ok, 392 skip` (the skips are AED8's deferred
death/oob).  So the VM-free driver now runs the two biggest L2 handlers (B86D + AED8), reproducing the
VM.  unit tests 9; lint 221; audits pass (27 pure files).  Next: B9F0 into the driver (extract its
movement half the same way), the BC4B contact path, then the frame loop.

## 2026-06-29 - Extract B86D's movement half to a canonical pure system (driver-ready)

Moved B86D's branch logic out of the coverage-gate probe arm into the canonical pure system
`object_update_b86d` (+ domain `B86dMovementResult`): the whole movement half producing the slot at the
BC4B handoff -- B8F8 edge-steer (5E1B->5E42), the A7A0 5DB2 phase seek, and the fall-through drift.  The
gate's `_arm_b86d` is now a thin adapter that projects the slot fields + B86D DS globals and calls it
(removed the duplicated logic constants from the probe).  Brief-aligned: canonical gameplay logic lives
in `systems`, the probe is just projection.

Gate-verified the extraction is byte-exact: B86D `1170/1170 fail=0`, AED8 `662/662` on L2 (behaviour
preserved).  lint 221; audits pass (27 pure files).  This makes B86D driver-ready: the native driver can
now compose `object_update_b86d` (movement) + `object_postmove_bc4b` (post-move y/active) for B86D's
final slot.  Next: add B86D to the driver (extend ObjectUpdateGlobals + pool accessors for target/
step-error); its whole-slot driver-verify needs a post-BC4B boundary (B86D tail-jumps, doesn't RET).

## 2026-06-29 - Whole-driver VM-verify: the VM-free driver reproduces the VM end-to-end

Upgraded the pillar-2 driver from unit-tested wiring to a VM-VERIFIED runtime piece.  New probe
`overkill/probes/verify_native_object_update_driver.py`: at each AE09/AED8 handler entry on the oracle
side it projects the slot's full record (SS:BP) into a 1-slot `ObjectPool` + the per-frame
`ObjectUpdateGlobals` (DS), runs the driver (`native_object_update_pool`), and asserts the driven slot's
post-frame fields equal the VM's at the handler RET -- grounding the cpu->ObjectPool projection, the pool
field accessors, the dispatch, and the write-back against the VM (the handler arithmetic is already
gate-proven; both AE09 and AED8 produce the complete slot at their RET).

Verified PASS, zero divergence: L3_full 800f `735/735`, L5_continue 400f `2226/2226` (AE09 + AED8) --
the VM-free driver reproduces the VM for every native slot.  lint 221.  So the "native runtime is a
second host for recovered systems" thesis is now demonstrated AND verified as running code: project VM
state -> drive natively -> matches the oracle.

Next: project `ObjectUpdateGlobals` for a whole-frame driver run (drive all native slots in one pass,
compare the pool); add B86D/B9F0 (extract movement halves + compose `object_postmove_bc4b`); then the
VM-free frame loop around the driver.

## 2026-06-29 - Pillar 2 skeleton: the VM-free native object-update DRIVER

Stood up the first piece of the native runtime that *drives* the recovered systems instead of the gate
merely checking them: `overkill/recovered/systems/object_update.py` -- `native_object_update(state,
globals)` / `native_object_update_pool(pool, globals)`.  It walks each `NativeGameState` object pool and,
for every active slot whose logic_id has a native whole-slot transform, produces the slot's next record
with NO VM; slots without a native handler are left unchanged (hybrid).  Wired: AE09 (0x0C) + AED8 (0x02)
-- the handlers with complete pure systems.  Added `domain/object_update.py::ObjectUpdateGlobals` (the
per-frame DS values handlers need) and named `ObjectPool` accessors (logic_id/substate/direction/
draw_layer/substate_1e).  Pure (source_pure, imports only domain+systems); 2 unit tests.

This is correct by composition: the per-slot handlers are proven byte-exact vs the VM by the coverage
gate, and the driver's walk/dispatch/write-back is unit-tested.  Next: project `ObjectUpdateGlobals`
from the VM + a whole-pool verify (driver output vs VM post-state across a demo); then extract the
B86D/B9F0 movement halves to pure systems and compose with `object_postmove_bc4b` to add them to the
driver.  audit_recovered_layers 27 pure files; audit_architecture + lint 220 pass.

## 2026-06-29 - Pure shared BC4B post-move (y/active half) -- the driver's post-move stage

Recovered the pure shared `object_postmove_bc4b` (+ domain `PostmoveBc4bResult`, 7 unit tests): the
deterministic y/active outcome EVERY object gets after moving, composing the two already-VM-verified
pieces -- the BCB1 Y clamp (`clamp_postmove_y_bcb1`) + the X-bounds death
(`object_postmove_x_bounds_deactivates_bc4b`).  Per the verified BC4B invariant the collision/contact
path that follows sets logic_id/sprite, NOT active/y, so these two fields are COMPLETE here;
`contact_path_runs` (global gate DS:A47C clear + survived bounds) flags the slots that then enter the
deferred BCCB/62F6/BFC7 collision tail where the sprite/logic_id may change.

Why this matters: it is the **post-move half a VM-free driver composes after each behaviour's movement
half** (handler -> BC4B), so the driver can now produce each slot's final y/active VM-free.  Pieces are
individually VM-verified; the composition mirrors the lifted BC4B and is unit-tested.  Remaining BC4B:
the contact path (62F6 object-vs-object overlap + BFC7 death -> sprite/logic_id) and a whole-BC4B VM
probe.  lint 218; audits pass.

## 2026-06-29 - Inflection: lifted-handler vein exhausted; next = pure BC4B + raw-ASM state machines

Assessed the remaining object-update handlers (disassembled BE3C/8B3B, read 8D4F).  The cheap vein
the session mined -- LIFTED handlers that tail-jump to BC4B, so the native transform is verifiable AT
the BC4B handoff (B86D/AED8/B9F0) -- is now exhausted for the big handlers.  What remains is harder:

- **BE3C (0x01, L2 521 + L3 558)**: a jump-table STATE MACHINE (dispatch on +14 through CS:BE54, many
  sub-states, mixed BC45/BD17/ret tails).  A multi-state recovery, not a single transform.
- **8B3B (0x40, L2 916)**: raw ASM pulling in the unrecovered 4D95 helper + DS:96D2/96EC tables.
- **8D4F (target-patrol, lifted, multi-level)**: INTERNALIZES BC4B (calls it then RETs), so its final
  slot can't be predicted without a fully-pure BC4B.
- **BC4B itself** (the shared post-move stage EVERY object passes through) is only PARTIALLY pure
  (`clamp_postmove_y_bcb1` + `object_postmove_x_bounds_deactivates_bc4b`); its collision path is lifted.

Highest-leverage next recoveries (fresh focused efforts -- raw-ASM/state-machine work is error-prone
to attempt at the tail of a long run): (1) **the full pure BC4B post-move** -- shared by every handler,
unblocks 8D4F, and is a prerequisite for a VM-free driver that composes handler -> BC4B; (2) the
raw-ASM state machines (BE3C is highest-value, multi-level); (3) the non-object pillars (frame loop,
audio, modes, starfield).

Session result (the "continue" run): AE09 + **B86D + AED8 + B9F0 fully native** (3 complex multi-branch
handlers) + 5E1B recovered; **L2 object-update 53% native, L3 ~60%**; every slice byte-exact vs the VM
(0 divergence), all pushed; the incremental compose-and-gate method proven and handlers shown to
generalize across levels.  No code changed this turn (terrain assessment only).

## 2026-06-29 - B9F0 FULLY NATIVE (all 4 paths) -- 3rd complete complex handler; L3 ~60%

Final B9F0 slice: the two 5E42 paths.  Path C overshoot (not reached, x > target): 5E42 with the slot's
existing +2A/+2C deltas, then `b9f0_wrapped_x_on_overflow`.  BA5A motion helper (reached + low counter
or periodic tick): 5E1B deltas toward the DS:237C box -> 5E42 -> X += 2 -> the BA67 sprite-refresh.  The
optional 7476 formation spawns are global side effects (new slots), out of the 6-field prediction.

**B9F0 (logic_id 0x14) is now FULLY native** -- all four paths (sprite-refresh / 5DB2 seek / 5E42
overshoot / BA5A helper), pure composition of the recovered primitives (5DB2/5E1B/5E42 + the b9f0_*
decision helpers).  Verified on the FULL L3_full demo (1400 frames, FRAME VERIFY OK, zero divergence):
B9F0 `1723/1723 fail=0`, AED8 `1323/1323 fail=0` -> L3 object-update **~60% native** (4 handlers).
B9F0 is the 3rd fully-native complex handler (after B86D, AED8) and the hardest (4 paths + target-state).
Gate-only change; lint 218; audits + gate unit test pass.

Next: the remaining L3 handlers (0x01->BE3C raw-ASM, 0x89->B2A6, 0x59->F225) and pushing other levels;
or stand up pillar 2 (the VM-free frame loop) to start *driving* these verified producers.

## 2026-06-29 - B9F0 Path D (5DB2 seek) -> B9F0 92% native, L3 -> 65.9%

Second B9F0 slice: the A482==A4E4 pre-step (target deltas +32/+34 += DS:2342/2346, X-wrap via
`b9f0_wrapped_target_x`, the `b9f0_reached_target` decision) + **Path D, the 5DB2 seek** (not reached,
x <= target: align to even pixels, seek toward the updated target via the pure `object_target_seek_step_5db2`,
mode 1) + Path B-no-helper (reached, BA5A doesn't fire -> the BA67 sprite-refresh).  The two 5E42 paths
(Path C overshoot, the BA5A motion helper) still return None.

Verified on L3_full (800f): B9F0 `native OK 1592/1723 fail=0` (up from 810 -> ~92% of B9F0), zero
divergence.  L3 NATIVE COVERAGE 43.7% -> **65.9%** (4 handlers).  lint 218; audits + gate unit test pass.
Remaining: the 131 5E42-path B9F0 slots (Path C + BA5A) -- the final B9F0 slice (5E1B/5E42 compose, like
B86D's B8F8).

## 2026-06-29 - B9F0 (0x14) started incrementally: the sprite-refresh path native (L3 -> 43.7%)

Began B9F0 (L3's #1, ~49%) the B86D way -- incrementally, branch by branch.  First slice: the
sprite-refresh path (A482 != A4E4 -> the BA67 tail), where the slot's sprite becomes DS:233C frame + 1Ch
and nothing else changes (`b9f0_sprite_from_frame`, already pure).  Wired as a gate arm (compared at the
BC4B handoff); the A482 == A4E4 movement paths (5DB2 seek / 5E42 overshoot / BA5A 5E1B+5E42 helper) return
None (fallback) for now.

Verified on L3_full (800f): B9F0 `native OK 810/1723 fail=0` -- the sprite-refresh path is ~47% of B9F0,
zero divergence.  L3 NATIVE COVERAGE 20.8% -> **43.7%** with 4 handlers (AE09/B86D/AED8/B9F0-partial).
lint 218; gate unit test passes.  Next B9F0 slices: the A482==A4E4 movement paths (Path D 5DB2 seek is
the cleanest, then Path C 5E42 overshoot, then the BA5A helper on the reached-target path).

## 2026-06-29 - Cross-level backlog map: handlers generalize; B9F0 (0x14) is the next big lifted target

Ran the coverage gate per level to map the cross-level backlog.  Key finding: **the native handlers
generalize across levels** -- AED8 (recovered for L2) is also L3's #2, native OK 735/735, ~21% of L3
already with zero extra work.  So each handler recovery compounds across every level it appears on.

L3 backlog (800f): logic_id 0x14 -> B9F0 (1723 slots, ~49% of L3) is #1 and is LIFTED (its near-calls
were composed earlier this session); then 0x01->BE3C (558), 0x89->B2A6 (227), 0x59->F225 (131),
0x13->8D4F (65), 0x0B->B24D (55).

The remaining hot handlers split two ways:
- **Lifted (compose existing pure primitives, the proven cheap path):** B9F0 (0x14), 8D4F (target-patrol),
  B24D -- B9F0 is by far the biggest (~49% of L3).
- **Raw ASM (need disassembly + new helpers/tables, a heavier recovery):** L2 0x40->8B3B (916; pulls in
  the unrecovered 4D95 helper + DS:96D2/96EC tables), 0x01->BE3C, 0x8A->8C1F; L3 B2A6, F225.

Next: recover **B9F0** as a pure whole-slot transform -- bigger/multi-branch (target-delta tracking +
X-wrap [`b9f0_wrapped_target_x` already pure] + reached-target decision + 5E1B/5E42/5DB2/7476 sub-paths,
all available), so best done incrementally (branch-by-branch) like B86D was.  No code changed this turn
(read-only gate runs); the value is the cross-level map.

## 2026-06-29 - AED8 FULLY NATIVE -> L2 object-update is now MAJORITY native (53%, 3 handlers)

Recovered AED8 (EFAE logic_id 0x02, the #2 L2 handler) as the pure `object_update_aed8` -- again pure
composition of EXISTING recovered systems, no new primitive: substate timer + AEE4 8px step
(`step_operations_for_direction(dir, 8)`) + the B250 overlap-contact selection
(`overlap_contact_box_contains` + the +1E skip rule) + the AD60 bounds tail (AD5A adds DS:A278, ADC9
sets X=FFFFh).  Key realisation: the B250 selector's slot-relevant output (AD5A vs ADC9) is purely the
box predicate (the lifted code already cross-checks it); the 9E19 fan-out is global side-effect only.
Domain `Aed8SlotUpdate` + unit test (5).  Also factored `_read_level_tile_context` (de-dup AE09/AED8).

Verified on the full L2_full demo (1400 frames, FRAME VERIFY OK, zero divergence): AED8 `1423/1423
fail=0`, B86D `1170/1170 fail=0` -> **NATIVE COVERAGE 53% of all L2 per-slot object updates** with 3
handlers wired (72.7% over the denser first 800 frames).  AE09 regression 353/353 on L5 (the tile-context
refactor is behaviour-preserving).  lint 218; audits + gate unit test pass.

Next levers: L2's remaining handlers (0x40->? , 0x8A->8C1F, 0x01->BE3C) and the L3/L6 per-level
backlogs (run the gate per level).  The pattern holds: each handler = compose recovered primitives,
gated byte-exact via exit_ip.

## 2026-06-29 - B86D FULLY NATIVE (all 3 branches) -- first complete complex handler, ~46% of L2

Composed B86D's dominant A7A0 phase branch in the coverage gate, completing the handler.  Key
finding: B729 (the A7A0 target move) is a thin wrapper over the ALREADY-pure
`object_target_seek_step_5db2` -- publish the slot's +32/+34 target to the 5DB2 globals then seek --
so **no new pure system was needed**; the gate arm builds a `MovementTarget` from the slot's (low-bit-
masked) target and calls 5DB2 (mode 1), forcing sprite 0x75 and direction 4 when the seek is blocked.

**B86D (logic_id 0x1D) is now FULLY native** -- all three branches: fall-through (object_update_b86d_drift)
+ B8F8 edge-steer (5E1B -> 5E42) + A7A0 phase block (5DB2).  Verified `native OK 1170/1170 fail=0`
across the FULL L2_full demo (1400 frames, FRAME VERIFY OK, zero divergence).  It is pure composition
of recovered primitives -- the "native runtime is a second host for recovered systems" thesis proven on
a complex handler.  Coverage: B86D alone is ~24-46% of L2 per-slot updates (density-dependent).

B86D is L2-specific (NO-EVENTS on L3/L6 -- their hot handlers differ).  Next levers: AED8 (0x02, the #2
on L2) and the L3/L6 hot handlers (re-run the gate per level for the backlog).  Only the gate changed
this turn (probe); lint 218; gate unit test + audits pass.

## 2026-06-29 - 5E1B recovered pure + B86D B8F8 edge-steer composed (and the A7A0/B729 finding)

Recovered the 1010:5E1B object-delta helper as the pure `object_delta_5e1b` (+ domain `ObjectDelta5e1b`,
unit test): per-axis `delta = slot - (target + pad)`, pad 4px when the target is solid (scan +14==1)
else 12px -- the input `object_delta_steer_5e42` consumes.  Then composed B86D's **B8F8 edge-steer**
branch in the coverage gate: 5E1B deltas toward the DS:237C box -> 5E42 steer -> force sprite 0x76,
compared at the BC4B handoff.

Verified on L2_full: B86D `native OK 55/1170 fail=0` (up from 12; B8F8 added ~43), zero divergence.
**Honest finding: B86D's dominant branch is the A7A0 phase block (~95% of its 1170 slots), which needs
the cpu-bound B729 target-move as pure.**  So B729 -- not 5E1B -- is the key that lights up the B86D
bulk (~44% of ALL per-slot updates).  5E1B is still a clean win (a shared steering primitive: B8F8 +
other edge/target branches).

Next: recover B729 (1010:B729 target move) as a pure system, then drop the A7A0 branch into the
exit_ip-capable gate.  Units (5E1B 4 + b86d-drift 4 + gate 4) pass; lint 218; audits pass.

## 2026-06-29 - B86D fall-through native + the coverage-gate exit_ip generalization

Attempted B86D (logic_id 0x1D, the 46%-of-dispatches target) as a pure whole-slot transform.
Honest result: B86D has 3 branches and **tail-jumps to the shared BC4B post-move stage** rather than
RETurning like AE09.  Only the FALL-THROUGH (formation-drift) path is pure-composable today (X += -delta
DS:2342, +1 when DS:2328==7, outgoing sprite) -- recovered as `object_update_b86d_drift`
(+ domain `B86dDriftUpdate`, unit test).  The B8F8 edge-steer and A7A0 branches need the still-cpu-bound
5E1B (delta helper) and B729 (target move) as pure first.

Generalized the coverage gate: a handler's compare boundary is now `exit_ip` (a fixed tail-jump target
like BC4B) OR a return address (AE09).  **This is the real unlock** -- most handlers tail-jump to BC4B,
so they could not be gated under the RET-only model; now they can.  Also de-duped the 6-field slot read
(`_read_slot_6tuple`).

Verified: gate run on L2_full -- B86D fall-through `native OK 12/12 fail=0` (the fall-through is rare here,
~1% of B86D's 1170 slots; the bulk is edge-steer/phase).  Units 8 passed; lint 218; audits pass.  **Next
for the B86D bulk: recover 5E1B + B729 as pure primitives** (5E42 already is), then the B8F8/A7A0 arms.

## 2026-06-29 - Architecture cleanup: decouple the native render host + lock it + the staged plan

Major-cleanup pass toward "one game core, two hosts".  Grounded finding: the architecture is already
~70-80% at the target (dependency audits green, pure systems canonical, adapters cross-check not
duplicate, native path proven to run recovered code).  Concrete slice + guardrail this pass:

- Decoupled the native render host: `native_video/sprite_compose.py` was the ONE native-runtime
  module importing a VM-facing `recovered.views` (for field offsets).  Added named accessors
  (`x_word/y_word/sprite_word`) to the domain `ObjectPool` and repointed the renderer to them, so
  `native_video` now imports only `recovered.{domain,systems}` (+self) and `game_core` imports
  nothing external -- the native runtime depends solely on recovered code.
- Locked it: new `native_render` layer in `audit_architecture.py` forbids `native_video/*` from
  importing vm/hooks/lifted/bridge (the brief's "second host, not second implementation").  Fixed a
  latent package-name classification edge (`overkill.native_video` -> was mis-tagged `vm`).
  Non-vacuous test cases added to `tests/test_architecture_layers.py`.
- Wrote `docs/overkill/architecture_cleanup_plan.md`: the honest scorecard, the staged per-rule
  migration recipe, the measured priority order (B86D 46% first, via the coverage gate), the enforced
  guardrails + gaps, and the VM-bound/missing-systems list (deliverable #8).

Verification: audit_architecture + audit_recovered_layers pass; lint 218; architecture/native/sprite
tests 11 passed.

## 2026-06-29 - Unify the produced-vs-VM probe harness (absorb copy-pasted scaffolding)

Survey of "is the code unified enough": the gameplay pure/lifted/adapter layers are actually
well-unified (decisions route through shared pure systems; the audit found minimal duplication).
The real duplication was in the VERIFY TOOLING: 19 `overkill/probes/verify_native_*.py` each
copy-pasted the same ~45 lines of frame-verifier scaffolding (the `fv._load_runtime` side-tagging
patch, the `sides` iterator, `pump_inputs` wiring, the ref-side `CPU8086.step` hook) + a private
`_Bytes` lazy view.

Extracted `overkill/probes/_harness.py` (`run_ref_step_probe(demo, max_frames, on_ref_step)` +
`LazyBytes` + `load_demo`) -- the single verify framework the native runtime's coverage gate and
per-routine probes share.  Migrated 2 probes as proof: the coverage driver
(`verify_native_object_update`) and the canonical `verify_native_object_update_ae09`.  Each now is
just its capture/predict/compare callback.  **Proven byte-identical**: both on L5_continue 500f give
AE09 610/610 fail=0 (driver 12.8% coverage) -- unchanged from pre-migration, and the two 610 counts
cross-validate.  lint 218, gate test 4, both layer audits pass.

Remaining (mechanical follow-up, each needs a demo re-run to confirm identical): migrate the other
17 probes to the harness (drop ~45 lines each).  Minor dead code to absorb later: the near-dead
`recovered/{coords,object_slots,collision_primitives}.py` root facades (~68 lines, tests-only).

## 2026-06-29 - Native object-update coverage gate (the VM-free state-runtime scaffold, step 1)

Built `overkill/probes/verify_native_object_update.py` -- the seed of the VM-free state producer
(§1.2/§1.3).  It walks a real demo and, at the per-slot behaviour dispatch (EFAE -> `CS:[0xEFC4 +
logic_id*2]`), classifies **every** per-slot object update as native (a wired pure whole-slot
transform, checked byte-exact vs the VM at the handler's return -- the AE09 produced-vs-VM mechanism,
generalised) or fallback (no transform yet, counted).  One run yields three things: a zero-divergence
**gate**, a **coverage %**, and a prioritised **backlog**.  Wire a new transform = one `NATIVE_HANDLERS`
entry.  Gate semantics PASS / NO-EVENTS / FAIL (divergence-only failure -- the rare-event convention,
safe in a cross-demo sweep).  Test: `tests/test_native_object_update_gate.py` (4).

Proven end-to-end: L5_continue logic_id 0x0C (AE09) `native OK 777/777` (1200f) byte-exact = 13.2%
coverage from a single handler; PASS.  AE09 is L5-only (NO-EVENTS on L2/L3/L4/L6) -- so it is a proof
of the mechanism, not a high-value handler.

**Prioritised backlog (L2_full, 800f, IP-resolved -- the next pure whole-slot transforms to recover):**
```
logic_id 0x1D -> B86D  1170 slots (46%)   <- #1; near-calls already composed this session
logic_id 0x02 -> AED8   662               <- #2; _run_object_behavior_aed8 already lifted
logic_id 0x01 -> BE3C   296
logic_id 0x8A -> 8C1F   112
logic_id 0x1C -> 8D4F    91  (target-patrol, lifted)
logic_id 0x39 -> 8A23    76
logic_id 0x0B -> B24D    61  (delta-steer, lifted)
logic_id 0x1E -> B909    51
```
Next steps: (1) recover B86D (0x1D) as a pure whole-slot transform (AE09 pattern) -- biggest single
coverage win; (2) AED8 (0x02); (3) recover the EFC4 dispatch as a pure routing fn; (4) aggregate the
histogram across all demos for the authoritative ranking; (5) optionally fold the driver into
`scripts/verify_native_producers.py` as a standing gate.  Verification: gate test 4 passed; lint 217;
both layer audits pass.

## 2026-06-29 - High-level refactor audit + A067 action-gate promotion + stronger pure-layer audit

Architecture-refactor pass (toward VM-independent recovered source).  Findings (full audit in
`docs/overkill/high_level_refactor_audit.md`, machine form `artifacts/high_level_refactor_gaps.json`):
the lifted/adapter/pure split is already healthy -- pure layers clean of layout constants, 49 adapter
`...disagrees...` cross-check asserts (the sanctioned guarded duplication), and an AST scan found only
the two A067 action gates stranded-pure in the lifted layer.

Shipped (one proven slice + tooling, behaviour-preserving):
- Promoted `action_trigger_is_pressed` + `action_latch_allows_repeat` from `gameplay/action_spawns.py`
  to the new pure system `overkill/recovered/systems/action_spawns.py` (evidence root 1010:A067; the
  lifted hook now only projects DS state + replays the TEST/CMP flags).  New `tests/test_action_spawn_gates.py`.
- Strengthened `scripts/audit_recovered_layers.py`: now also bans capitalised VM/CPU *types*
  (CPU/CPUState/Memory/Mem/Registers/...) and memory-layout/segment constants (0x1010/0x23B4/0x2B5C/
  0x32CA/0x8D12/0x95D8) in pure layers, with a `# layout-justified` escape hatch.  Negative tests in
  `tests/test_audit_recovered_layers.py` prove it is not vacuous.

Verification run: `audit_recovered_layers.py` (25 pure files) + `audit_architecture.py` pass;
`lint.py` 216 files; `pytest tests/test_action_spawn_gates.py tests/test_audit_recovered_layers.py` 9
passed; A067 hook tests 5 passed; `tests/test_demo_replay_equivalence.py` 23 passed / 23 skipped
(0 divergence).  Frontier unchanged: object_behaviors (17) + object_movement (12) bounded-original
seams remain the promotion frontier; `overkill/hooks.py` (3203 lines) is the next structural thinning.

## 2026-06-29 - Frontier consolidation: 511F is lifted (3rd disproven "gate"); §1 remaining scoped

Check-registry-first again: the "511F render island" I named last turn as the status-render gate is
ALREADY lifted -- `run_video_page_toggle_511f` (rendering/layer_sprites.py) is a tiny page-toggle stub
(a no-op CMP/RET on Tandy mode 2, the page flip only on mode 1), and 61DC is lifted too
(`run_status_display_parent_61dc`).  So that "gate" doesn't exist.  Surveyed the remaining interpreted
near-calls: the object-update STATE near-calls (7476/5E1B/5E42) are composed (B86D/B9F0); the rest are
the RENDER/scroll path (511F/61DC/9Exx/A7EB display-shift + the A6xx scroll subcalls C591/62AA/7524/
CB1C/D2A4), i.e. §1.1 frame work that is starfield-gated anyway.

**Three "gates" disproven this session -- camera (already an object), stack-fidelity (recovered hooks
ARE faithful), 511F render (lifted page-toggle).  The accurate §1 remaining:**
- **§1.2/1.3 (VM-free state runtime):** the gameplay DECISIONS are comprehensively recovered (21 pure
  leaves + the whole collision island), but the per-logic-id HANDLERS are still LIFTED cpu-hooks, not
  PURE NativeGameState transforms.  The runtime needs each handler re-expressed as a pure slot transform
  (composing the already-recovered decisions) + the pool-walk/dispatch + verify mode.  Big multi-slice,
  but UN-gated (AE09's full pure transform is the template; the pieces exist).
- **§1.1 (full native frame):** playfield/sprites/HUD compose natively; the **starfield parallax layer
  is the one true hard blocker** (needs the off-screen parallax trace tooling).
- **§1.4 (pure % ceiling):** decisions largely harvested (18.2%); coastline collapsing via the near-call
  compositions.
So the loop's recovery phase has comprehensively succeeded; what remains is the pure-handler runtime
build (Bucket C, un-gated) and the blocked starfield.

## 2026-06-29 - Bucket A: B86D's 7476 composed natively -- the "stack-fidelity gate" was UNFOUNDED

Tested (not reasoned) the handler-composition I'd repeatedly deferred as "stack-fidelity-gated": rewired
B86D's `call_7476` from the interpreted near-call to the recovered `_run_formation_spawn_7476_observed`
(the same hook B73E already calls directly), resuming at the return IP.  I had REASONED this would fail
the full-memory test on 7476's internal 7573 CALL scratch -- but the B86D hook-equivalence test (full
CPU state + memory) PASSES, and the hybrid frame-verifier on L2_full + L3_full (1400 frames each) shows
0 divergence.  So the recovered hooks ARE faithful drop-in replacements for the interpreted near-calls;
the "stack-fidelity gate" does not exist.  Coastline -1 (one interpreted-near-call bounce -> native);
pure % flat at 18.2 (composition, not new pure logic).  **This opens the handler-composition path** --
the other interpreted near-calls (B9F0's 7476/5E1B/5E42, B86D's B729, ...) can be rewired to their
recovered hooks the same way, collapsing the object-update toward a native dispatch.  LESSON (again):
do not declare a slice gated from REASONING about stack scratch -- attempt it and let the full-memory
test decide; my reasoning was wrong.  Both audits + lint pass; full suite green (639 passed).

## 2026-06-29 - Bucket A: native BEC5 variant dispatch -- the collision island is COMPLETE (pure % 18.2)

Recovered the last BEC5 piece: the variant-dispatch family classifier.  `bec5_collision_variant_family`
(systems/collision.py) classifies the collided candidate's logic id into the reaction family BEC5 routes
to -- `bd0d_then_a8c2` (05/06/07/08/0C), `a8c2_no_bd0d` (09), `sprite_variant_2` (02), or
`owner_linked_or_noop` (any other id, the runtime owner-link fallback).  The BEC5 hook keeps its
per-variant BD0D returns + the runtime owner test and cross-checks the pure family at the fallback (the
C054 adapter pattern).  **Verified**: VM-free unit tests (all families) + the hybrid frame-verifier on
L6_boss + L2_full (1300 frames each, 0 divergence; the cand-side fallback cross-check held on every real
collision).  21st pure recovery; pure % 18.2.

**MILESTONE -- the object-vs-object collision island is now COMPLETE in native source:** detection
(62F6 grid overlap) + variant dispatch (BEC5) + damage (BF25 counter chain) + the death/spawn tails
(BFC7 + score-add/7420/C054/C037 transition) are all recovered + verified.  This was the early-session
"attended frontier" (the bc4b collision-death I handed off); re-attempting it after the tails landed
yielded the whole island, decision by decision.  Both audits + lint (215) pass; full suite green (639).

## 2026-06-29 - Bucket A: native 62F6 object-vs-object grid overlap predicate -- pure % 18.1 (20th recovery)

Continued reopening the "attended" collision island: recovered the 1010:62F6 overlap DETECTION (the
object-vs-object scan that feeds BEC5).  `object_grid_overlap_62f6` (systems/collision.py) is the pure
grid-cell match: the scanning object's 8px-aligned cell (x&FFF8, y&FFF8) hits a candidate when its cell
falls in the candidate's occupied footprint -- a vertical cell run (two cells when the candidate Y is not
8px-aligned, else one, always plus the cell above; two more above for a wide object_type-2 scanner) and a
horizontal run (cell + one left; two more left for a wide scanner unless logic id 78h/79h).  The 62F6
scan hook keeps its unrolled per-candidate loop + register side effects and cross-checks the pure
predicate at the BEC5-dispatch match point (the C054 adapter pattern).  **Verified**: VM-free unit tests
(the cell runs + the wide/narrow widening) + the hybrid frame-verifier on L6_boss + L2_full (1300 frames
each, 0 divergence; the cand-side cross-check held on every real collision).  20th pure recovery; pure %
crosses 18%.  The collision island is now mostly native -- detection (62F6) + damage (BF25) + death tails
(BFC7/score/7420/C054/C037) all recovered; the last BEC5 piece is the variant dispatch (07/08/0C,
sprite-0033 variant-2, 5/6).  Both audits + lint (215) pass; full suite green (636 passed).

## 2026-06-29 - Bucket A: native BF25 collision-damage counter chain (reopening "attended" BEC5) -- pure % 17.9

Re-attempted the BEC5 object-vs-object collision handler that I handed off early this session as "the
attended frontier" -- now that ALL its death tails are recovered (BFC7 + score-add/7420/C054/C037 this
session), its counter chain is a clean pure decision.  `collision_damage_counter_chain_bf25`
(systems/collision.py) is the difficulty-gated hit-counter decrement: one decrement for the BF25 entry
(skipped on the variant-2 sprite path that enters at BF2D), one at BF2D, then +1 if DS:BEDC==1 / +3 if
DS:BEDC==0 / none otherwise, dying the instant a decrement reaches zero (-> the recovered BFC7 death
tail; survivors continue to the variant=5 / A8C2-mark tail).  Returns the post-chain counter + ``died``.
The BEC5 hook (`run_bf25_counter_chain`) keeps its per-step DOS writes and cross-checks the pure decision
at the survive point (the C054 adapter pattern).  **Verified**: VM-free unit tests + an assembled-ASM
oracle (`test_chain_matches_interpreted_asm_bf25` runs the real BF25..BF52 chain, stopping at BFC7 on
death / BF52 on survive, for both entries and all BEDC cases) -- the §5 per-routine-ASM gate -- plus the
hybrid frame-verifier on L6_boss + L2_full (1300 frames each, 0 divergence; the cand-side cross-check held
on real collisions).  19th pure recovery.  Remaining for BEC5: the variant dispatch (07/08/0C, sprite-0033
variant-2, 5/6) + the 62F6 overlap scan that feeds it.  Both audits + lint (215) pass; full suite green
(632 passed).

## 2026-06-29 - Camera pieces are ALREADY RECOVERED -- roadmap #2 is done; check-registry-first

Followed up the "recover 5010 / the view-anchor movement" plan and found 5010 is the body of 1010:4FF9
-- which is ALREADY FULLY RECOVERED: `run_tile_contact_probe_4ff9_body` (collision_adapter.py) composes
`is_tile_contact_side_valid_4ff9` + `tile_contact_probe_plan_4ff9` + `tile_contact_offset_table_byte_offset`
+ 5073/505B and cross-checks them against the ASM-compatible body.  4FF9 is a directional tile-contact
PROBE (move by the DS:214E delta, scan the plan, ALWAYS restore x/y, return carry = blocked) -- not a
committed move.  Its caller 9CB9 is a lifted frame-controller.  So ALL the camera-object's pieces are
already recovered/lifted: the 4FF9 contact probe, the a5d1/a5ea/a5f9/a607 clamp-STEP moves
(`_run_two_pass_word_clamp_step`, the committed view moves), the 5073/505B tile probe, and the 9CB9
controller.  **roadmap #2 ("camera") is effectively done** -- the camera is the 237C special_pool object,
advanced by these recovered routines; what remains for it is the same lifted->native composition frontier
as every other object handler (make 9CB9 + its pieces a native pure update), NOT a separate island.
**Process note (check-registry-first):** I nearly re-recovered 4FF9 and spent three turns recon-ing a
camera system that was already recovered.  The [[overkill-check-hook-registry-first]] rule applies: grep
the recovered/ + gameplay/ layers for a CS:IP (and its neighbors) BEFORE disassembling it as if
un-recovered.  No code was written (investigation only); nothing to revert.

## 2026-06-29 - Recon RESOLVED: the "camera" is an OBJECT -- roadmap #2 folds into the object-update

Resolved the multi-turn camera mystery by instrumenting the demo to find what writes the view target
(DS:237E/2380): the writers are 3586/3590, 5010/5014, and the scroll-edge clamps A5E2/A603/A612.  But
they all write **`ss:[bp+2]` / `ss:[bp+4]`** (an object slot's X/Y at OFF_X/OFF_Y) -- they only touch
237E/2380 because **the view target is itself an object record**: the struct at DS:237C is a slot, and
SS:BP points to it when the object-update processes it (237E = [237C+2] = its X, 2380 = [237C+4] = its Y).
So there is NO separate camera system:
- The camera is an OBJECT, advanced by the generic per-frame object-update -- `5010` is a path-follow
  movement step (`lodsw; add [bp+2],dx; lodsw; add [bp+4],dy; call 5073 tile-probe; loop`), `3586/3590`
  is a transient +/-10h collision probe (net no-op on position), and the level-edge clamps (a5d1/a5ea/
  a5f9/a607) are ALREADY recovered hooks (the `_run_two_pass_word_clamp_step` family).
- The view target IS dynamic in gameplay (16-18 distinct X, 84-88 distinct Y over 600 frames) -- so the
  camera-object moves; it is not the static intro-script value.
**The 237C slot is the special_pool object already in NativeGameState** (the leading "view-anchor slot"
at SPECIAL_DRAW_SLOT_BASE=0x237C, modelled since the sprite-compose work).  So CameraState (DS:237E/2380)
is literally that slot's X/Y ([237C+2]/[+4]) -- the camera and the special-pool object are the SAME thing,
already mirrored in NativeGameState; no separate CameraState producer is needed.
**Consequence:** roadmap #2 ("camera/scroll island") is NOT a separate island -- it collapses into the
object-update (Bucket A): recover the special/view-anchor object's behavior (its movement helper `5010`
path-follow + tile, demo-reached x30/60 frames) like the other object handlers, and the camera position
follows for free.  Next slice: recover `5010` (the path-follow movement+tile helper) as a producer.
(Three camera-recon turns -> the "camera" is the object system itself, on the already-modelled 237C slot.)

## 2026-06-29 - Bucket A: native scroll-script interpreter step (level-script island) -- pure % 17.8

Reopened last turn's "gated on 859E" assessment by separating the pure state step from the render side
effect (the recurring lesson).  `scroll_script_step` (new systems/level_script.py) is the pure 1010:D0D4
state transition: count down the per-command delay DS:BE08; while running, just decrement; on expiry,
reload (0x64), advance the script index DS:BE06, read the 6-byte entry at DS:BE1A[index*6] and publish
its two words to DS:95FA / BE16 (skipped at the FFFFh end marker).  The 859E status render and the
per-index command dispatch (cs:[D112+index*2]) are side effects the adapter owns -- so the 859E gate
does NOT block the script-STATE recovery.
**KEY FINDING:** D0D4 is the level-INTRO / scripted-event interpreter -- it runs at level start (before
the demo snapshots), so it is NOT demo-reached (the probe `verify_native_scroll_script_step` saw 0 events
across L2/L6_boss/L3/start_to_end; kept as the harness, NOT added to the cross-demo gate).  So verified
via an **assembled-ASM oracle** (`test_scroll_script_step_matches_interpreted_asm_d0d4` runs the real
D0D4 up to D0DA/D104 and compares BE08/BE06/95FA/BE16) -- the §5 "per-routine ASM" gate -- plus synthetic
unit tests.  Corollary: the gameplay camera-SCROLL writer is STILL elsewhere (separate from this intro
script), so roadmap #2's gameplay-camera search continues.  18th pure recovery; both audits + lint (215)
pass; full suite green (628 passed).

## 2026-06-29 - Recon LOCATED: the camera/level-event "scroll-script" island (roadmap #2 mapped)

Followed last turn's redirect and FOUND the view-target writer: it is the **scroll-script / level-event
system**, now fully mapped.  The view target (DS:237E/2380) is moved by a scroll-script COMMAND, not a
standalone camera routine:
- **Interpreter @ 1010:D0D4**: counts down the per-command delay DS:BE08; on expiry resets it (0x64) and
  advances the script index DS:BE06; reads the 6-byte script entry at DS:BE1A[index*6] (word0 -> DS:95FA,
  word1 -> DS:BE16; FFFFh = end); calls **859E** (the status-cell render); then dispatches the command via
  `jmp cs:[D112 + index*2]`.
- **Command table @ CS:D112**; **command handlers @ 1010:D14D..D2xx** -- tiny routines that set level
  flags (D14D `inc [A958]`, D152/D159), step the view (**D160**: `dec [237E]` toward 0x60 = the camera
  scroll step), reset the delay (D17C), and spawn objects (D199/D1AB via 7524/8209, D1DC/D1F8 via 9F1A).
- **The script data is at DS:BE1A** (6 bytes/entry); the interpreter walks it per frame.

So roadmap #2 "camera" = recover the scroll-script interpreter (D0D4) + its command handlers (D14D..D2xx)
+ the BE1A script format.  **GATE**: the interpreter calls **859E** (the status-cell quad render island,
per the §6 frontier note) every step, so a native interpreter needs 859E native first (or keeps it as a
near-call with the stack-scratch fidelity the full-memory tests require).  This is a bounded but
multi-slice island, no longer an "unlocated writer".  (Two camera-recon turns -> located + mapped.)

## 2026-06-29 - Recon: camera view-target writer redirect + the clean pure-leaf veins are scarce

A recon turn (no clean single-leaf slice found; the easy producers are harvested) that sharpens two
frontiers with concrete findings:
- **Camera view target (DS:237E/2380) writer is NOT direct-MOV and NOT via a 237C-base load.**  All
  four `mov bx,237C` sites (8A72, AB34, B8F8, BA5A) READ the view target as the steer/motion reference
  (5E42 steers objects TOWARD it; AB34 positions an object as view + a motion-table delta), none writes
  it.  So roadmap #2 must trace the writer through a different addressing mode (a DI/SI `stosw`/store, or
  the player/scroll init computing it into a register first), not the operand scans already tried.
- **Composable movement-handler targets found:** 8A72 (`bx=237C; 5E1B; 5E42; jmp BC45`) and BA5A
  (`bx=237C; 5E1B; 5E42; x+=2; sprite=233C+1Ch; jmp BC4B`) are UNHOOKED movement handlers built entirely
  from recovered pieces (5E1B `_run_object_delta_helper_5e1b`, 5E42 `run_runtime_patched_object_steer_5e42`,
  the BC45/BC4B postmove) -- candidate from-scratch native handler hooks (verify they are demo-reached
  first; they are not direct EFC4 entries).  AB4F is a trivial one-liner (`sprite = DS:233C + 18h`) -- not
  worth a single-use extraction.
- **State:** the clean pure-leaf veins (shared selectors/spawn templates/decisions) are largely harvested
  over this session (17 producers); the remaining is the harder tail -- from-scratch handler hooks (with
  near-call/stack-scratch fidelity), the elusive camera writer, the VM-free runtime loop, and the two hard
  blockers (starfield, BEC5).

## 2026-06-29 - Bucket A: native 7476 formation child spawn template -- pure % 17.5

Recovered the shared 7476 formation child spawn (reached from B800/B73E) as a pure source-level
template, the 7420 pattern again.  `formation_spawn_seed_7476` (systems/objects.py) returns the new
`FormationSpawnSeed7476`: the child is placed relative to the parent (`y = slot_y + 1Ch`/`0Ch`,
`x = slot_x + 08h`/`0Ch` -- the wider-Y/narrower-X pair in final-boss mode DS:A8C2==1), stamped as an
active `logic_id=0Bh` / `hazard_class=2` / `sprite_or_state=31h` child, and given view-relative move
deltas (`move_delta_y = y - (DS:2380 + 9)`, `move_delta_x = x - DS:237E`).  The hook
`_run_formation_spawn_7476_observed` now sources every child field from the seed, keeping the 7573
allocation, the DS:98C0 -> BEFF side effect, and the original AX/CX/DX register + flag choreography.
**Verified**: a VM-free synthetic oracle (`tests/test_formation_spawn_seed_7476.py` -- normal + boss
offsets + 16-bit delta wrap) + the produced-vs-VM probe `verify_native_formation_spawn_seed_7476`
(predicts the seed from parent slot + A8C2 + view globals, compares the allocated child slot) -- **33
formation spawns across L2/L6_boss/L3/start_to_end, 0 divergence** (L6_boss's 29 exercise the boss-mode
offsets).  17th cross-demo producer; the B73E formation path now uses it.  (b86d/b9f0 still reach 7476
through the interpreter; rewiring them to this now-pure helper is a follow-on, gated by demo-replay.)
Both audits + lint (212) pass; full suite green (623 passed).

## 2026-06-29 - Bucket A: B24D fully composed (5E42 + B250 + AD60 tail) -- coastline -1 interpreted frontier

Direct follow-on to the B250 recovery: B24D (EFAE logic_id 11) was lifted only up to the B250
"AD5A/ADC9 frontier" -- it set `cpu.s.ip = tail` and bounced into the interpreted tail.  Now that the
B250 overlap predicate is pure, B24D composes its tail natively exactly like the already-composed AED8:
B250 -> AD5A routes to the recovered AD60 bounds/tile tail (add DS:A278 to X), B250 -> ADC9 forces
X = FFFFh then AD60.  So B24D is now a full native composition -- 5E42 steer + B250 overlap + AD60
bounds/tile -- with no interpreter bounce (one fewer coastline frontier; pure % flat at 17.2 since this
is composition, not new pure logic).  **Verified**: the B24D hook-equivalence test was STRENGTHENED from
"stops at AD5A" to the AED8 pattern (run the ASM through the whole tail to the caller return, assert the
composed hook matches state + memory byte-exact), and the hybrid frame-verifier on L6_boss + L2_full
(1300 frames each, semantic + raw/RGB, 0 divergence).  Both audits + lint (211) pass; full suite green
(620 passed).  The AED8/B24D composition pattern now extends to any remaining B250-using handler.

## 2026-06-29 - Bucket A: native B250 overlap/contact predicate -- unblocks the b24d/aed8 handlers (pure % 17.2)

Reopened a prior "blocked" assessment by attempting it (the recurring lesson): loop_blockers had B250's
overlap test marked "flag-coupled at each early return, no meaty pure decision."  But the *decision* is
cleanly separable from the flag mechanics.  Recovered `overlap_contact_box_contains` (systems/collision.py):
the slot's (X, Y) is inside the reference box (anchored at the view target DS:237E/2380) when X is in the
signed window [ref_x-2, ref_x-2+0x14] and Y in the unsigned window [ref_y, ref_y+0x14] -- the 1010:B256..B278
predicate, native-forward.  The B250 hook keeps its staged SUB/ADD/CMP arithmetic for the exact AX/BX/flag
side effects (the AD5A/ADC9 tails run from the selected IP with that register state) and cross-checks the
pure predicate against the staged path (the C054 adapter pattern).  **Verified**: a VM-free synthetic oracle
(`tests/test_overlap_contact_box_contains.py` -- signed-X / unsigned-Y windows + edges) + the produced-vs-VM
probe `verify_native_overlap_contact_box_b250` (predicts the selector's tail from the slot/box/substate,
compares to the AD5A/ADC9 the ASM reaches) -- **10,767 B250 calls across L2/L6_boss/L3, 0 divergence** (the
cand-side cross-check assertion also held throughout).  16th cross-demo producer.  This is the shared
overlap coupling that blocked the b24d/aed8 EFAE handlers -- their native slot-transforms can now compose
this pure predicate instead of bouncing to B250's ASM.  Both audits + lint (211) pass; full suite green
(620 passed).

## 2026-06-29 - Integration-phase recon: small dispatch slices exhausted -> handler-by-handler + runtime

Three concrete investigations this turn confirm the demand-driven loop's small clean slices are
exhausted; the remaining §1 work is the larger integration, with sharper findings recorded so the next
phase is well-guided:
- **EFAE 2nd-level per-logic-id dispatch (CS:EFC4) is a LARGE jump table** -- coherent through logic_id
  0x53+ (84+ entries, ~40 distinct handlers: AED8/B1B0/B24D/B9F0/B73E/B86D/8D4F/B556/B3DF/...).  NOT a
  clean hand-transcribable slice like AA2B (8 entries).  Its native form must be built HANDLER-BY-HANDLER
  (logic_id -> native handler, as each behavior becomes native), not wholesale -- a wholesale IP table is
  faithful-to-VM but not native-forward.  The SMALL dispatch tables (AA2B draw_layer/8, B00D direction/8,
  C054, 5E0C) are all recovered; EFC4 is the big one, tied to the handlers.
- **The camera view target (DS:237E/2380) has no direct-MOV writer** in the code; it is written via
  indexed addressing through the DS:237C struct ([237C+2]/[+4]).  So roadmap #2 must start with a
  base-register (237C/SI/DI) trace to locate the scroll/view-update writer, not a direct-operand scan.
- **The remaining EFAE handlers have recovered movement halves but coupled animation/state/interpreted
  halves** (per loop_blockers); completing one to a FULL native slot-transform is the real per-handler
  work (AE09 / logic_id 12 is the one already done end-to-end).
Next work: (a) complete a coupled handler's native slot-transform (per-handler), or (b) start the VM-free
object-update composition over the already-native pieces (AE09 + bc4b postmove) with a per-slot verify
harness -- the first runtime slice.  Both are larger than the per-routine producers harvested this session.

## 2026-06-29 - Bucket C: native AA2B first-level object-logic dispatch routing (integration slice #1) -- pure % 17.1

The first integration slice from the roadmap below: the object-update dispatch skeleton.  AA2B selects
the per-frame object handler from the slot's draw_layer (0-7) through the CS:AA36 jump table; recovered
the draw-layer -> handler routing as the pure `object_logic_dispatch_aa2b` (systems/objects.py) returning
`ObjectLogicDispatchAA2B(kind)` -- the 8 address-rooted handler kinds (postmove_prelude_bc45 / tracked_
logic_ad04 / family_dispatch_efae[layers 2,4] / action_44af / collision_tail_aac2 / logic_ab10 /
handler_c3f8), mirroring the existing C054 dispatch-classifier pattern.  The hook keeps the live CS:AA36
read authoritative and cross-checks the pure decision against it (the C054 adapter pattern), so it stays
robust for any draw layer outside the recovered set; the adapter owns the kind -> IP map.  **Verified**:
a VM-free synthetic oracle (`tests/test_object_logic_dispatch_aa2b.py`) + the produced-vs-VM probe
`verify_native_object_logic_dispatch_aa2b` (reads each dispatch's draw_layer, asserts the recovered
routing's IP == the live CS:AA36 entry) -- **29,970 dispatches across L2/L6_boss/L3/start_to_end, 0
divergence, 0 out-of-range** (draw_layers 1/2/4/5/6 observed; the range stays <=7, confirming the 8-entry
table).  15th cross-demo producer.  This is the routing skeleton the native object-update will dispatch
through; the per-handler native slot-transforms (roadmap #1) remain.  Both audits + lint (210) pass; full
suite green (616 passed).

## 2026-06-29 - Phase transition: per-routine producer leaves harvested -> Bucket-C integration roadmap

This session harvested the demand-driven loop's per-routine producer leaves: pure % 15.1 -> 17.0 (14
cross-demo producers; the full B800 HUD text render layer; the BFC7 death/spawn island's 5 computational
leaves -- score add, y-clamp, 7420 spawn, C054 classifier, C037 transition -- all now pure).  Examining
the §6 queue + the dispatch/runtime this turn shows the clean ISOLATED producer slices are now exhausted:
every remaining piece is INTEGRATION (its value gated on the VM-free runtime + native handlers), plus two
hard blockers.  The path to §1, scoped:

RECOVERED native building blocks:
- Render: playfield compose (30/30), sprite layer, HUD glyph + the full B800 HUD text line, projection.
- State producers: score (5F0D), 3 movement primitives (AE09/5DB2/5E42), bc4b bounds, the death/spawn
  leaves, frame timers, allocator + spawn seeds (8209/A4EA/7420).
- §1.2 mirror: NativeGameState (special/object/effect pools + camera + hud) + native_game_state_mismatches
  + the VM-projection adapter.

REMAINING to §1 (integration, recommended order):
1. Native object handlers.  AA2B is the 1st-level dispatch by draw_layer (0-7) through CS:AA36 -> 8 handlers
   (BC45 postmove / AD04 tracked / EFAE family-dispatch[layers 2,4] / 44AF / AAC2 / AB10 / C3F8).  The
   **routing is now recovered + verified** (`object_logic_dispatch_aa2b`, integration slice #1, 29,970
   dispatches 0 div).  What REMAINS: each handler's FULL slot-transform native (movement halves done; the
   animation/state/interpreted halves remain) + the EFAE second-level dispatch, then a pure object-update
   that walks the pool and dispatches through the recovered routing to the native handlers.
2. Camera/scroll island.  The view target (DS:237E/2380 -> NativeGameState.camera) is currently only READ
   in the lifted layer (object_behaviors/object_spawns) + the snapshot adapter; its WRITER is not lifted
   yet (the scroll/view-update island, alongside the recovered scroll hubs a5d1/a63c/a662/a66f/a74e/a6fe/
   a616/...).  So this slice first LOCATES + recovers the 237E/2380 advance, then composes a pure
   advance_camera producer gated produced-vs-VM on camera x/y -- a real NativeGameState producer.
3. Grow NativeGameState with the globals the runtime advances (BFC7/spawn/counter globals: DS:2078 linked
   counters, A47E/A482, 98C0, the spawn-stage 2376/2378/237A).
4. The VM-free loop: frame -> recovered systems advance NativeGameState -> render/audio state -> --backend
   native, NO VM; then --mode verify (compare to the VM-projected NativeGameState at every checkpoint),
   extending coverage slice by slice, toward --mode standalone (every demo, VM never started).
Residual producer-style work: walking the big lifted files (object_movement/game_state/action_spawns/
object_behaviors/object_runtime) for any leftover inline decision -- prior assessment found the remainder
are multi-part islands, but re-checkable per the attempt-don't-declare rule.

HARD BLOCKERS (skip per loop_blockers):
- BEC5 collision-overlap decision (62F6 -> BEC5): the attended multi-variant handler that DECIDES which
  object dies (its death TAILS are now pure; the variant/counter-chain dispatch is the frontier).
- Starfield parallax layer: needs the off-screen parallax trace (tooling); blocks the full native frame.

## 2026-06-29 - Bucket A: native BFC7/C037 collision-death transition -- pure % 16.8 -> 17.0; BFC7's 5 leaves all pure

Recovered the long-cited "logic_id=1 + C037 sprite + latch" collision-death transition as a pure leaf, and
in doing so confirmed BFC7's third sub-leaf (C054) was ALREADY pure (the classifier
`object_deactivate_dispatch_decision_c054`) -- so all FIVE of BFC7's computational leaves are now pure
(score add, y-clamp, 7420 spawn, C054 classifier, C037 transition).  `object_collision_death_transition_c037`
(systems/collision.py) returns the new `CollisionDeathTransition`: previous_logic_id = the old logic id,
logic_id = 1 (the dying state), transition_latch = 0, and the death sprite from the object type via the C037
table (type 1 -> 0, type 2 -> 3; other types fail loud -- the original's other C037 entries stay an adapter
unverified-path tail).  The BFC7 hook now sources the death sprite from this pure fn, keeping the original
unconditional prev/logic/latch order + the BX = type*2 C037 index.  **Verified**: a VM-free synthetic oracle
(`tests/test_collision_death_transition_c037.py`) + the hybrid frame-verifier on L3_full (1600 frames, pure-VM
vs hooked, semantic state + raw/RGB, **0 divergence** -- a combat level exercises the transition on every
type-1/2 kill).  Unlike 7420 this fires constantly, so the frame-verifier is the strong demo gate.  What
remains of BFC7 is pure GLUE, not transforms: C12D (stages 7420 + DS:A482/A842/A47E) and the orchestration
(the 0021h gate, counter chain, DS:98C0 gate) -- so composing BFC7 as one transform is a Bucket-C
integration over its 5 now-pure leaves.  Both audits + lint (209) pass; full suite green (612 passed).

## 2026-06-29 - Bucket A: native 7420 linked-effect spawn template (BFC7 sub-leaf 2/3) -- raises pure % to 16.8%

Recovered the 2nd of BFC7's 3 death/spawn sub-leaves as a pure source-level template, the first pure-%
gain in a while (16.5 -> 16.8%; source_pure +74 lines, 78 pure fns).  `object_spawn_seed_7420`
(systems/objects.py) returns the new `LinkedEffectSpawnSeed7420` field values 7420 stamps into a freshly
allocated effect slot when a linked-counter group's last member dies: `x = source_x + DS:A278` (scroll
offset), `y = min(source_y, 00C0h)` (floor clamp), `sprite_or_state = source_type + 46h`, the raw source
type also at the record's +26h word, and the constants (active=1/scan=1/hazard=5/logic=0/latch=0/
linked=FFFF/variant=0/layer=0).  Follows the existing 8209/A4EA spawn-template precedent exactly; the
hook `_run_linked_effect_spawn_7420_observed` is now a thin adapter (7524 allocation + DOS write order +
the register/flag choreography), sourcing every field value from the pure seed.  **Verified two ways**: a
VM-free synthetic oracle (`tests/test_object_spawn_seed_7420.py` -- the X offset, the strict `>00C0h` Y
clamp, the sprite bias, 16-bit wrap) and the produced-vs-VM probe `verify_native_object_spawn_seed_7420`
(hooks 7420 on the pure-VM side, predicts the seed from the staged DS globals, compares the allocated
slot's fields at the routine's return).  The linked-counter->0 event is rare (as predicted), but across
the corpus it fired **34 times -- L5_continue 20 / L3 10 / L2 2 / start_to_end 1 / L4 1 -- 0 divergence**
(L6 boss/mothership/showcase have 0, confirming those bosses aren't linked-counter groups).  14th
cross-demo producer (added to `verify_native_producers`; rare-event probes report NO-EVENTS, not failure,
on demos that don't reach them).  Both audits + lint (209) pass; full suite green (608 passed).  BFC7's
last sub-leaf is the C054 deactivate selector; then the BFC7 death/spawn island composes.

## 2026-06-29 - Convergence: death-tail score add -> the verified pure bcd_add_score (1 of BFC7's 3 sub-leaves)

Coastline-shortening on the attended death/spawn island.  `_run_score_add_5f0d_observed` (the BFC7
death-tail score add) was a witness-poor hand-rolled 5-byte BCD loop (it added an 8-bit amount and wrote
a spurious 5th byte at DS:2318, the label byte the real 5F0D only `INC BP`s past).  Converged it onto the
already-verified pure `score.bcd_add_score`: since BFC7 passes the amount in BX with BH==0, `bcd_add_score`
is identical to the real 5F0D (proven across the demos by `verify_native_score`, the death-tail's own adds
among those 5F0D calls), so now there is a single verified score producer and the spurious 2318 write is
gone.  **Re-verified two ways**: a new assembled-ASM test (`test_run_score_add_5f0d_observed_matches_asm_
and_leaves_2318` -- the hook == 5F0D for the 0030h/0060h death amounts incl. overflow, 2318 untouched) and
the hybrid frame-verifier on L2_full (1300 frames, pure-VM vs hooked, semantic state + raw/RGB checks, **0
divergence**) -- closing score.py's "needs death-tail demo re-verified" note.  This recovers 1 of the 3
BFC7 sub-leaf prerequisites (the other two -- the 7420 linked-counter spawn and the C054 selector --
remain).  Both audits + lint (208) pass; full suite green (605 passed).

## 2026-06-29 - Bucket B: native HUD/status text composer byte-exact vs the VM's B800 digit band

Closed the brief's named "clean fresh-session slice" -- the HUD score digits -- as a real native render
layer.  The glyph *leaf* (1010:3153) and the BCD score (5F0D / DS:2314) were already recovered; the
missing piece was composing them into the **packed Tandy B800 page** (the gate is "byte-exact vs B800's
digit band", which the index-space `hud_glyph` could not witness).  New `native_video/hud_text.py`
composes the whole `1010:5EDB` HUD line natively -- the label string at DS:2318 through the 518C/519A
char path (with 3153's inline `0x10 colour` / `0x11 row,col` escapes) then the four DS:2314 score bytes
as eight most-significant-first BCD digits -- writing the four-bank B800 geometry exactly as 3153
(`expand[glyph] & colour`, di += 0x2000/row wrap +0x80A0, col += 4 wrap 0xA0 -> row += 0x140).  All
geometry mirrors the already-lifted hybrid hooks in `rendering/text.py`; no VM (dual-mode -- reads the
recovered font/score/cursor, composes a flat page).  **Verified produced-vs-VM byte-exact** by
`verify_native_hud_text.py` (hooks 5EDB entry on the pure-VM side, composes natively into a copy of the
live visible page CS:[95A4], compares the whole page at 5EDB's return): **L2 600/600, L5_ending 600/600,
L3 600/600 -- 1800 real HUD lines, 0 divergence**.  13th cross-demo producer; the brief's HUD-digit gate
is now met.  6 new VM-free unit tests (`tests/test_hud_text.py`) pin the geometry/escapes/digit order.
Both audits pass; full suite green (604 passed).  Remaining Bucket B: the starfield parallax layer
(blocked) and folding this HUD layer + playfield into the standalone backend compose (Bucket C).

## 2026-06-29 - Bucket C: SHARED native target-seek movement (5DB2) byte-exact vs VM

The highest-value object-update producer yet: the whole 1010:5DB2 target-seek movement, SHARED by
every seeker (B729/D281/B1B0 + the b73e/b9f0/8d4f behaviors).  `object_target_seek_step_5db2`
(systems/movement.py) composes the two already-VERIFIED recovered systems -- the 5DB2 direction
decision (`choose_target_seek_direction`) and the 8-way step (`step_operations_for_direction`) -- with
the recovered CS:5E0C mode table (dumped from the image: mode 1 -> AF63 one 2px step, 2 -> AF60 two 2px
steps, 3 -> AEE4 one 8px step; mode 0/AFA2 + >=4 fail loud, matching the lift).  Returns the slot's
post fields `TargetSeekStep` (direction_or_step +06, x +02, y +04); the blocked branch (table -> FFh)
leaves them untouched.  The AD60/BD17 tail (run by callers) + the DS:A954/230A globals are out of
scope.  **Verified produced-vs-VM byte-exact** by `verify_native_object_seek_step_5db2.py` (hooks 5DB2
entry + its return address): **L2 1257/1257, L6_boss 1957/1957, player_death 1721/1721, L5 240/240 --
5175 calls, 0 divergence**.  10th cross-demo producer.  Lint (204) + both audits pass; full suite
green.  With AE09 (fixed-step) + 5DB2 (target-seek), the two movement primitives behind the object
behaviors are now native; remaining object-update work is the global side-effects (counters/spawns/
BD17 death) + composing the per-logic-id dispatch.

## 2026-06-29 - Bucket C: native BC4B post-move bounds (y-clamp + X-bounds death) byte-exact vs VM

Recovered the bounds/clamp half of the shared BC4B post-move (the tail every seeker + several behaviors
run after moving).  `object_postmove_x_bounds_deactivates_bc4b` (systems/collision.py) is the X-bounds
death: the object deactivates (-> BD17, active=0) when its post-move X leaves the play box -- the
precise box [-C0h, F0h) unless DS:A47C is set or the logic id is a wide-box exempt family (then
[-14h, F0h)).  Composed with the recovered `clamp_postmove_y_bcb1` (Y into [0, C0h]), this gives the
BC4B slot fields **y + active**.  **Verified produced-vs-VM byte-exact** by
`verify_native_object_postmove_bounds_bc4b.py`: **L2 1498/1498, L6_boss 2257/2257, player_death
2181/2181 -- 5936 calls, 0 divergence**.  12th cross-demo producer.  The pass also CONFIRMS three
hypotheses: (a) the collision death (BFC7) sets logic_id, not active (else collision objects would
diverge on active); (b) BC4B's observed sub-routines 9E69/62F6 are slot-neutral for y/active (else
divergence); (c) y is always the clamp regardless of collision.  Scope: the y/active half; the
collision-death logic_id/sprite half (BCCB -> AA46/AA71 -> BFC7 transition) is the next fresh-session
producer.  Lint (206) + both audits pass; full suite green.

## 2026-06-29 - Bucket C: native delta-steer (5E42) byte-exact vs VM -- the 3rd movement primitive

Recovered the runtime-patched 1010:5E42 delta-steer (used by the b24d/b86d behaviors), the 3rd object
movement primitive after AE09 (fixed step) + 5DB2 (target-seek).  `object_delta_steer_5e42`
(systems/movement.py) converts the slot's signed Y/X movement deltas (+2C/+2A) into a direction via a
Bresenham axis pick against the `move_step_error` accumulator (+2E): the larger-magnitude axis always
steps, the minor axis steps when the accumulator overflows the major magnitude (then the accumulator is
reduced); the per-axis sign bits index the DS:A348 table to a direction (or FFh = blocked, which leaves
direction + x/y untouched but still advances the accumulator); then it steps x/y by that direction
(AF22 3px when DS:2312==3 else AF63 2px, composing the recovered `step_operations_for_direction`).
**Verified produced-vs-VM byte-exact** by `verify_native_object_steer_5e42.py` (hooks 5E42 entry + its
return address; checks direction +06 / move_step_error +2E / x +02 / y +04): **L2 64/64, L6_boss
121/121, 0 divergence** (NO-EVENTS on demos without the steer behaviors).  11th cross-demo producer.
VM-free unit test locks the Bresenham branches + sign bits + blocked sentinel + step-mode dispatch.
Lint (205) + both audits pass; manifest regenerated; full suite green.  All THREE object movement
primitives (fixed-step AE09, target-seek 5DB2, delta-steer 5E42) are now native; remaining
object-update: the bc4b postmove (collision/death) + the global death/spawn side-effects + the dispatch.

## 2026-06-29 - Bucket C: COMPLETE native AE09 slot transform (movement + tile-collision death) vs VM

Completed the first WHOLE per-slot object-update transform -- the template for the per-logic-id native
dispatch.  `object_update_ae09` (systems/objects.py) composes the AE09 movement
(`object_movement_step_ae09`) with the AD60 bounds/tile decision -> the slot's `active`: out of play
bounds -> deactivate; the tile-probe family (draw_layer 2) -> deactivate when the tile one map row
below has class 1; else survive.  This required the **tile-collision composition**
`object_tile_probe_deactivates_ad60` (5073 offset + the 13-col row stride -> 505B class == 1), which
revealed the earlier "needs LevelState from scratch" revert was wrong: the tile probe/lookup were
**already pure-recovered** (`systems/tilemap.py`); only the tile-map INPUTS were missing, now modeled
as `LevelTileContext` (DS:234E origin, DS:2350 row base, the CS:[9592] tile plane, the DS:C3AA class
table) -- a seed of the native LevelState.  **Verified produced-vs-VM byte-exact** by the extended
`verify_native_object_update_ae09.py` (now movement+active, tile-probe included, no skips):
**L5_continue 353/353, L5_short 342/342, 0 divergence**.  (Probe perf: snapshot the static class table
once -- avoids 256 reads/call.)  Lint (204) + both audits pass; full suite green.  This is the complete
AE09 object-update except the BD17 global counter/spawn writes (separate state); it proves the per-slot
transform pattern (movement primitive + bounds/tile -> next slot) end-to-end.

## 2026-06-29 - Bucket C: FIRST native object-update producer (AE09 movement) byte-exact vs VM

Breakthrough on the object-update island: the earlier "fully coupled to the attended-only death
frontier" conclusion was WRONG.  The per-slot MOVEMENT transform is *separable* from the global
death-tail side-effects -- AD60/BD17 only set the slot's `active` word + global counters, they never
touch the five movement fields (substate +1C, direction +06, sprite +08, x +02, y +04).  So a slot's
post-frame movement is a pure composition of already-VERIFIED recovered systems.
`object_movement_step_ae09` (systems/objects.py) composes `object_logic_ae09` (the AE09 timer/step
decision) + `step_operations_for_direction` (the AF22 3px step) in the lifted order, returning the
new `Ae09MovementStep` (substate, direction_or_step, sprite_or_state, x, y).  **Verified
produced-vs-VM byte-exact** by `verify_native_object_update_ae09.py` (hooks AE09 entry + the return
address; reads the slot's five post-frame fields at AE09's RET): **L5_continue 777/777, L5_short
638/638, 0 divergence** (NO-EVENTS on demos without logic_id 0xC).  9th cross-demo producer, the
FIRST object-update one.  VM-free unit test locks the composition (timer/direction/sprite + the
optional x-=2 + step order).  Lint (203) + both audits pass; full suite green.  This opens the
object-update recovery: each behavior's movement half is a clean per-slot producer (decision + step),
leaving only the global counter/spawn/death side-effects (the bc4b/BD17 tail) as the harder island.

## 2026-06-29 - Bucket C: COMPLETE native draw list (special view-anchor slot) byte-exact vs VM

Completed the native draw list: `NativeGameState` now carries the leading view-anchor `special_pool`
(DS:237C, the slot the present scan draws FIRST/back-most), so `native_sprite_draws` composes the
COMPLETE draw list (special, then gameplay, then effect -- the witnessed-exact present order) from
recovered state with no VM read.  Verified the special slot follows the same `project_object_screen_di`
projection (it is a normal 5AC8 draw) by a probe experiment first, then wired it in:
`NativeGameState.special_pool` (+ its `_pool_mismatches` comparison), `read_native_game_state` reads
DS:237C (1-slot table), `native_sprite_draws` walks it first, and `verify_native_sprite_draws.py`'s
VM reference prepends it.  **Verified produced-vs-VM byte-exact**: L2 300/300, L5/L6-boss/
player-death/mothership 250/250 -- 0 divergence, the COMPLETE draw list.  Surfaced + locked a real
aliasing fact: the special slot's X/Y (237E/2380) ARE the VIEW_TARGET/camera globals, so a camera
move drifts both `camera` and `special_pool` (same memory) -- the byte-faithful mirror reports both
(test updated).  `SPECIAL_DRAW_SLOT_BASE/_COUNT` now live in `views/object_slots.py` (canonical
layout source).  Lint (202) + both audits pass; full suite green.  The render side is now fully
recovered (leaves + complete composed draw list); the object-update island (pool producer) is the
one remaining §1 recovery.

## 2026-06-29 - Bucket C: native draw-list producer (native_sprite_draws) byte-exact vs VM

The first **composed native render producer**: `native_sprite_draws(game_state, column_table,
scroll)` builds the FrameSnapshot sprite list straight from `NativeGameState` -- walks the gameplay
then effect pools (the witnessed-exact present order), takes the active slots, and composes each
through the verified `project_object_screen_di` (35CC `+0C`), dropping culls -- returning the
`(sprite, screen_di)` draw list the backend blits, with **no VM read of `+0C`** (reuses
`build_native_sprite_layer`; pure, `native_video/sprite_compose.py`).  **Verified produced-vs-VM
byte-exact** by new probe `verify_native_sprite_draws.py`: at the A90C present-scan return (where
`+0C` is fresh) it compares the native list against the VM's gameplay+effect draw list read from the
slots (`+08`/`+0C`, active + on-screen) -- L2/L5/L6-boss/player-death all **200/200, 0 divergence**.
8th producer in the cross-demo gate; the first to mirror RenderState's composed *draw list* (not
just one field).  VM-free unit test covers the walk/active-filter/order/cull.  Lint (202) + both
audits pass; full suite green.  Scope: gameplay+effect pools; the single leading view-anchor
"special" slot (DS:237C) needs `NativeGameState` to carry it -- the next render-composition slice.

## 2026-06-29 - Render composition RECOVERED: full sprite `+0C` screen-di (35CC) byte-exact vs VM

Closed the render-side Bucket-C composition gap: the native sprite layer now computes each object's
final slot `+0C` (the `screen_di` the FrameSnapshot uses) from `NativeGameState` with **no VM read**.
The projection note left the full `+0C` as "core + DS:234C scroll" but the two projection.py
docstrings disagreed on whether DS:99C8 was already scroll-baked; disasm of the per-object draw
handler **35CC** settled it exactly: `35CC call 5A36` (→30D2 core di `(obj_y>>1)+DS:99C8[obj_x]`) →
`35CF mov [bp+0C],ax` → `35D8 add ax,ds:[234C]` → `35DC mov [bp+0C],ax`, i.e.
**`+0C = (project_object_to_di(x,y,col) + DS:234C) & 0xFFFF`**, or FFFFh when 30D2 culls (→25B2).
Recovered as pure `native_video/projection.py:project_object_screen_di`; `build_native_sprite_layer`
now composes the full `+0C` (takes the DS:234C scroll), not the core.  **Verified produced-vs-VM
byte-exact vs the live slot `+0C`** by new probe `verify_native_screen_di.py` (hooks 35CC's final
write 35DF + cull return 35D7): L2 **2191/2191**, and L1 2933 / L5 3851 / L6-boss 3417 /
player-death 3556 / mothership 977 -- **~17k draws, 0 divergence** across every level type.  Added
to the cross-demo gate's `PROBES` (7th producer).  The earlier note's `+0x68` "phase" is NOT part of
`+0C` -- it's only the present-hook *extraction* boundary artifact.  Lint (200) + both audits pass;
full suite green.  Both render gaps (leaves + composition) are now done; the object-update island
(the pool *producer*) is the one remaining §1 recovery.

## 2026-06-29 - Bucket C: NativeGameState grows to both object pools (gameplay + effect)

Extended the native aggregate state toward full object coverage: `NativeGameState` now carries the
`effect_pool` (the 2nd 0x38-stride object table the present scan walks) alongside the gameplay
`object_pool`.  `read_native_game_state` snapshots both (`read_object_pool` for the GAMEPLAY +
EFFECT tables); `native_game_state_mismatches` compares both via a shared `_pool_mismatches` helper
(byte-faithful per slot/word).  Tests cover the effect-pool round-trip + per-slot drift.  Full suite
green; lint (199) + recovered-layer + architecture audits pass.  Grows the §1.2 verify-mode state
coverage (both object tables) toward the native sprite composition (which projects both pools'
active objects).

## 2026-06-29 - Bucket C: native sprite-layer composition (build_native_sprite_layer)

First FrameSnapshot-composition piece, wiring the recovered render leaves into the brief's "compose
from recovered state instead of capturing the VM page": `build_native_sprite_layer(objects,
column_table)` projects each active pool object through the recovered 30D2 projection
(`project_object_to_di`) into the native sprite draw list `[(sprite, di)]`, dropping culled
(off-screen) objects -- the native sprite placement **computed** from `NativeGameState`'s pool
instead of read from the VM's `+0C`.  Pure (`native_video/projection.py`); unit-tested (compose +
per-cull + empty).  The di's are byte-exact by the 30D2 projection verify (4624/4624); this composes
them into the layer the backend blits via `composite_sprites`.  Lint (199) + architecture audit pass.

## 2026-06-29 - Render leaf RECOVERED: native object screen-di projection (30D2) byte-exact vs VM

Recovered the object `screen_di` projection -- the first **render-side** native producer, and the
§1.2 gap that blocked building `FrameSnapshot` sprites from `NativeGameState` (the `+0C` dest the
adapter had only *read* from the VM).  Found by going to the ASM (5AC8 draw dispatch → 5A36
video-mode dispatch → **30D2** Tandy projection): `di = (obj_y >> 1) + DS:99C8[obj_x]` -- a
per-column, scroll-dependent **word table** (the X is a TABLE LOOKUP, which is exactly why the
earlier observe→derive failed), with a cull when `obj_x >= 0xE0` or the column entry is `FFFFh`.
Pure `overkill/native_video/projection.py` (`project_object_to_di`).  Verified **byte-exact vs the
real 30D2**: probe `verify_native_projection.py` on `demo_play_tandy_L2_full` -> **4624 projections,
4624/4624, 0 divergence** (+ a VM-free unit test).  Added to the cross-demo gate's `PROBES` (6th
producer, first render-side).  Lint (199) + architecture audit pass.  This unblocks the native
sprite layer (place objects from `NativeGameState`'s pool via `project_object_to_di` rather than
reading the VM `+0C`); remaining for a native FrameSnapshot: the native column table (DS:99C8) +
the per-handler `+234C`/present phase.

## 2026-06-29 - §1.2 frame-timer verify: native step_first_active_timer byte-exact vs VM 61C7

Fifth native producer in the cross-demo §1.2 gate -- the first **distinct state** beyond the
object lifecycle + score: the frame-timer countdown table (DS:2368, 6 counters; 1010:61C7
decrements the first non-zero).  New probe `overkill/probes/verify_native_frame_timer.py`:
step-hooks 61C7 on the pure-VM side, predicts the next table via `step_first_active_timer` at
entry, and asserts it matches at the RET (61D1/61DB).  Result: **L4 24/24 byte-exact**; L2
NO-EVENTS (61C7 is demo-dependent -- reached when its trigger fires, not every gameplay frame, so
the gate's NO-EVENTS handling covers demos where it isn't hit).  Added to `PROBES`.  Lint (197)
green; standalone gate.

## 2026-06-29 - §1.2 A4EA spawn verify: native object_spawn_seed_a4ea byte-exact vs VM A4EA

Fourth native producer in the cross-demo §1.2 gate, completing the spawn-template coverage (the
logic=2 A4EA template, distinct from 8209's logic=14h effect).  New probe
`overkill/probes/verify_native_spawn_seed_a4ea.py`: step-hooks A4EA's terminal RET (A514) on the
pure-VM side -- BX = the allocated+stamped slot -- and asserts its 8 stamped fields equal the
constant `object_spawn_seed_a4ea()`, for every real A4EA spawn.  Result: **L2 67/67, L4 78/78
byte-exact** (frequent -- 145 spawns across 2 demos, 0 divergence).  Added to `PROBES`; the
cross-demo gate now covers score + allocation + both spawn templates.  Lint (196) green;
standalone gate.

## 2026-06-29 - §1.2 spawn-stamp verify: native object_spawn_seed_8209 byte-exact vs VM 8209

Third native producer in the cross-demo §1.2 gate (after score + allocator), extending it to object
**creation**.  New probe `overkill/probes/verify_native_spawn_seed.py`: step-hooks the real
1010:8209 (effect-spawn template) on the pure-VM side, captures the allocated slot + the caller's
source position, predicts the stamped record via `object_spawn_seed_8209`, and asserts all 13
stamped fields match the VM for every real effect spawn.  Result on L2: **17 spawns, 17/17
byte-exact**.  Added to `scripts/verify_native_producers.py`'s `PROBES`, so the cross-demo gate now
covers the object lifecycle (score + allocation + creation) produced-vs-VM.  Lint (195) green;
standalone gate.

## 2026-06-29 - §1.2 cross-demo gate: native producers byte-exact vs the VM across the corpus

Added `scripts/verify_native_producers.py` -- the §1.2 "across every demo" gate: runs each native
producer verify (score, allocator) across the gameplay demo corpus and reports PASS / NO-EVENTS /
DIVERGENCE per (demo, producer), failing only on a real divergence.  Confirmed the two producers
byte-exact across five demos (L1_start, L1_hard_start, L2_full, L3_full, L4_full): **113 score
events + 367 allocations, all produced-vs-VM byte-exact, 0 divergence**.  This is the §1.2
"matches at every checkpoint across every demo" requirement for the producers recovered so far;
the gate grows as more producers land (add their probe to `PROBES`).  Lint (194) green; standalone
gate (slow; not the fast suite).

## 2026-06-29 - §1.2 allocator verify: native object_pool_find_free byte-exact vs VM 7573

Second produced-vs-VM verification (after the score), extending the verify-mode from a scalar to
the **object pool** (the core §1.2 state).  New standalone probe
`overkill/probes/verify_native_allocator.py`: step-hooks the real 1010:7573 on the pure-VM side,
snapshots the pool + allocator cursor (DS:95DA), predicts the allocation via `object_pool_find_free`,
and asserts it matches the VM's result (BX offset, or FFFF when full, + the updated cursor) for
every real in-game allocation.  Result on `demo_play_tandy_L2_full` (1200 frames): **71
allocations, 71/71 byte-exact, 0 divergence**.  Confirms the verify-mode pattern generalises from
a scalar (score) to a table (object pool) on real inputs.  Lint (193) green; standalone gate
(additive probe; the suite is unaffected, as established by the score-probe run).

## 2026-06-29 - §1.2 score verify: native advance_hud_score byte-exact vs VM 5F0D across a demo

The first **produced-vs-VM** verification of a native producer (the §1.2 native-state-mirror
check, end-to-end -- beyond the synthetic per-routine oracle).  New standalone probe
`overkill/probes/verify_native_score.py`: step-hooks the real 1010:5F0D on the pure-VM side and,
for every in-game score event, predicts the next score natively via `advance_hud_score` (through
`HudLayer.score_bcd`, the representation `NativeGameState` carries) and asserts it equals the VM's
actual score after the add.  Result on `demo_play_tandy_L2_full` (1200 frames): **26 score
events, 26/26 byte-exact, 0 divergence**.  This is the pattern the full verify-mode extends as
more producers land (a producer proven against the VM on real demo inputs, not just synthetic
fixtures).  Lint (192) green; standalone gate like `verify_playfield_compose` (not in the fast
suite).

## 2026-06-29 - Bucket C: native score producer advance_hud_score (wires bcd_add_score)

The first native state **producer**: `advance_hud_score(hud, delta) -> HudLayer` advances the
packed-decimal score (`HudLayer.score_bcd`, the two words = 5F0D's four bytes) via the faithful
`bcd_add_score`, counters unchanged.  Pure -- the standalone runtime advances `NativeGameState`'s
score through this with no VM (the dual-mode rule), and verify mode checks the result against the
VM-projected HUD.  Unit-tested (incl. carry across the word boundary, 9990+10=10000).  Full suite
green; lint (191) + recovered-layer + architecture audits pass; pure % 15.0 -> 15.1.  This closes
the `bcd_add_score` leaf into a wired producer (no longer test-only).

## 2026-06-29 - Recover the faithful 5F0D score BCD-add as a pure system (bcd_add_score)

Recovered the byte-exact packed-decimal score add at 1010:5F0D as a pure system
(`systems/score.py`): adds the 16-bit BCD delta in BX (BL->byte0, BH->byte1) into the 4-byte
score (2314..2317) with a DAA carry chain, dropping the top carry like the ASM.  Oracle-verified
**byte-exact vs the real 5F0D** over 7 cases (basic add, carry, BH!=0, mixed, overflow).  This is
the faithful score producer the native runtime will advance `NativeGameState`'s score with; the
death-tail `_run_score_add_5f0d_observed` remains a witness-poor single-byte approximation
(converging it onto `bcd_add_score`, resolving its 5-byte vs the ASM's 4-byte write, is a
follow-up that needs the death-tail demo re-verified).  Full suite green; lint (191) +
recovered-layer (22 pure) + architecture audits pass; pure % 14.8 -> 15.0.

## 2026-06-29 - Bucket C: NativeGameState aggregate + pure verify-mode comparison core

The first VM-free native-runtime step, and the first to **raise** pure % (14.5 -> 14.8) rather
than dilute it (unlike the per-state mirrors).  Defined `NativeGameState`
(`domain/native_game_state.py`, source_pure) -- the aggregate state the standalone runtime owns:
the gameplay `object_pool` + `camera` + `hud`/score (the three states whose native mirrors are
proven byte-faithful).  Added the PURE `native_game_state_mismatches(native, reference)`
comparison core: a field-by-field native-vs-native diff (byte-faithful per object-slot word),
VM-free -- the §1.2 verify gate that compares the standalone runtime's output to a VM-projected
reference.  The VM projection `read_native_game_state` (`adapters/native_game_state_adapter.py`)
composes the recovered per-state readers (`read_object_pool`/`read_camera_state`/`read_hud_layer`).
Tests: the pure comparison (per-substate + pool layout/word diffs) + VM round-trip + drift
detection.  Full suite green; lint (190) + recovered-layer (21 pure) + architecture audits pass;
pure % 14.5 -> 14.8 (the pure comparison core + aggregate outweigh the small adapter read).
**Next:** a native PRODUCER (run a recovered per-frame system on `NativeGameState` with no VM) so
verify compares produced-vs-VM rather than VM-vs-VM; then grow the aggregate (Projectile/Combat/
Rng states).

## 2026-06-29 - Bucket C §1.2: HudLayer / ScoreState native state-mirror

Third §1.2 native state-mirror (after `ObjectPool` + `CameraState`): the status panel + score.
Lifted the inline `HudLayer` read in the FrameSnapshot extractor to `read_hud_layer(mem, ds)`
plus `hud_layer_mismatches(hud, mem, ds)`, modelled on the ObjectPool/Camera verifiers -- the
`score_bcd` (DS:2314 low / 2316 high) is the §1.2 ScoreState; the `FRAME_TIMER_COUNT` status
counters (DS:2368..) round it out.  Returns every `(field, native, vm)` divergence; empty =
byte-faithful at the checkpoint.  The extractor routes through `read_hud_layer` (byte-identical;
the frame_snapshot corpus stays green).  Fidelity + per-field drift tests added to
`test_frame_snapshot`.  Full suite green; lint (188) + recovered-layer + architecture audits
pass; pure % held at 14.5%, glue not raised.

## 2026-06-29 - Bucket C §1.2: CameraState native state-mirror (read_camera_state + verifier)

Second §1.2 native state-mirror after `ObjectPool`, extending the verify-mode coverage toward
the standalone-runtime gate.  The camera view origin (the `VIEW_TARGET` globals DS:237E/2380,
signed) was read inline in the FrameSnapshot extractor; lifted it to a named
`read_camera_state(mem, ds) -> CameraState` projection plus a
`camera_state_mismatches(camera, mem, ds)` verifier modelled on `object_pool_mirror_mismatches`
-- it returns every `(field, native, vm)` where the native CameraState diverges from the live
VM globals; empty = byte-faithful at the checkpoint (the invariant a standalone runtime must
preserve).  The extractor now routes through `read_camera_state` (byte-identical; the
frame_snapshot corpus stays green).  Fidelity tests (signed read, per-field divergence, i16
boundary) added to `test_frame_snapshot`.  Full suite green; lint (188) + recovered-layer +
architecture audits pass; pure % held at 14.5%, glue not raised.  Next §1.2 mirrors to add:
ScoreState (DS:2314 BCD) and LevelState (DS:2350 scroll / 2356 column).

## 2026-06-29 - Lift the A4EA spawn template into the pure layer (object_spawn_seed_a4ea)

The 1010:A4EA object-spawn seed (allocate a slot via 7573, then stamp a fixed `logic=2`
template) was already a recovered+hooked routine, but it stamped its 8 constant fields
*inline*, and the sibling A4D7 lift (A4EA seed + source-coordinate copy) duplicated that same
inline block.  Lifted the template into the pure layer: new `ObjectSpawnSeedA4EA` (domain) +
`object_spawn_seed_a4ea()` (systems/objects), matching the 8209 seed pattern, applied through
a shared `_stamp_object_spawn_seed_a4ea` helper so both the A4EA and A4D7 adapters read the
values from one pure source instead of 16 inline magic constants.  Byte-exact: the existing
A4EA + A4D7 oracle tests stay green (`assert_oracle_equivalent`), plus a new pure-layer value
test (`test_object_spawn_seed_a4ea_template_values`).  Full suite + lint (188) + architecture
audit pass.  (Process note: A4EA was already hooked -- caught a near-duplicate recovery by
grepping the hook registry; the net change is the inline->pure refinement, not a new island.)

## 2026-06-29 - HUD-digit island: native glyph blit byte-exact vs 1010:3153

The HUD char-output leaf recovered native + proven byte-exact. `519A`'s Tandy dispatch
(`[95BC]=2`) -> `3153` is an 8x8 glyph blit (font `DS:1816`, bit->4bpp expand `DS:1514`,
colour `DS:215C`, B800 bank geometry). In the renderer's index space this collapses to a
plain pixel write, and `DS:1514` is a pure bit->0xF-nibble spread. Recovered as
`overkill/native_video/hud_glyph.py` (`draw_glyph` + dual-mode `read_glyph_font` over the
`DS:1816` font). Byte-exact witness `overkill/probes/verify_hud_glyph.py`: the VM's *actual*
`DS:1514` expand table == the native bit-spread (256/256) AND per-char
`draw_glyph(font[char], colour)` == the VM cell built from the real tables (256/256) -> the
native glyph rendering is byte-identical to `3153`. VM-free unit tests (`test_hud_glyph`, 5);
lint (188) + recovered-layer audit green. The score state (`score_bcd` DS:2314) is already
recovered. Remaining to close the island: the score-digit placement layer (positions from
the score-display routine) + composing the digits into the HUD region of the native frame.

## 2026-06-28 - Phase 2: native ObjectPool allocator (object_pool_find_free) == VM 7573

First native game-logic *system* on ObjectPool (beyond the struct + state-mirror):
`object_pool_find_free` is the pure 1010:7573 object-slot allocator -- scans up to
`len(pool)` slots from the cursor DS:95DA, wraps at the table end every iteration (the
ASM's 757A loop target), and returns the first `active_word == 0` slot plus the parked
cursor, or `offset=None` when full (new `FreeSlotAllocation` record; `ObjectPool` gained an
`active_word(index)` accessor).  Verified by an **equivalence test**: across first-free /
mid-table / wrap / all-occupied scenarios it returns exactly what the VM
`_find_free_object_slot_7573` returns (offset + the new DS:95DA).  The rule is pure
(recovered-layer audit clean, no VM) and pure-additive (the VM allocator is untouched, so
no demo-replay needed); lint + both architecture audits pass.  This is the pattern for
recovering the allocation/scan systems natively before standalone owns them.

## 2026-06-28 - Phase 2: migrate b9f0_reached_target to take a native ObjectSlotRecord

Closes the enrichment loop: `b9f0_reached_target` now takes the slot's `ObjectSlotRecord`
plus the global vertical delta and reads `slot.y_word` / `slot.target_y_word` /
`slot.x_word` / `slot.target_x_word` (the target fields the previous slice added) instead
of five loose ints.  The B9F0 adapter builds the record via `read_object_slot_record(slot)`
and replays its AX writes / CMP flags from the record's fields.  Byte-exact: the migrated
unit test passes and the bounded demo corpus stays byte-exact (B9F0 has no per-hook oracle,
so the demo corpus is the gate); lint + audit + the guard pass.  Second rule on the native
path (after layer1) and the first to consume the enriched target fields.

## 2026-06-28 - Phase 2: enrich ObjectSlotRecord with the slot target position

Grew the native `ObjectSlotRecord` toward the full slot state: added `target_x_word` /
`target_y_word` (offsets 34h/32h) with signed `target_x` / `target_y` properties, defaulted
so the ~20 existing 8-field constructors stay valid.  Both projections now populate them --
`object_slot_adapter.read_object_slot_record` (from the view) and `object_pool_slot_record`
(from the pool).  This unblocks migrating the target-position rules (b9f0 reached-target,
b73e) to native state next.  Byte-exact / pure-additive: the extra reads are pure, so the
a8c7 oracle + the rules' unit tests + the bounded demo corpus (the live collision/movement
paths through `read_object_slot_record`) stay green; lint + both audits + the guard pass.

## 2026-06-28 - Phase 2: migrate layer1_scan_should_draw to take a native ObjectSlotRecord

The goal doc's core Phase-2 move ("rules take native state instead of loose ints"),
demonstrated on `layer1_scan_should_draw`: it now takes the slot's `ObjectSlotRecord` plus
the two globals (`render_mode`, `camera_x`) and reads `slot.active_word` /
`slot.hazard_class` (the near-layer flag, SS:[bp+16h]) / `slot.gate_or_layer` (the object
layer, SS:[bp+0Ah]) instead of five loose ints.  The A8C7 adapter builds that record via
`read_current_object_slot_record(cpu)` and replays the per-branch CMP flags from its
fields.  Byte-exact: the `a8c7` per-hook oracle stays green (the extra faithful reads are
pure), the migrated unit test passes, and the bounded demo corpus stays byte-exact; lint +
audit + the guard pass.  This is the pattern the remaining rules follow as the lifted
adapters thin toward pure source.

## 2026-06-28 - Phase 2: native ObjectPool struct + VM state-mirror verifier

First Phase-2 slice (native state structs).  Added `domain.ObjectPool` -- the VM-free
native snapshot of an OVERKILL object-slot table: every 0x38-byte record as 28 words
(including the still-unknown bytes, so it is byte-faithful), frozen with a functional
`with_word`.  It is the counterpart of the DS:23B4 effect / DS:2B5C gameplay tables a
standalone runtime will own.  Added the views bridge: `read_object_pool` (snapshot a VM
table), `object_pool_mirror_mismatches` (the state-mirror verifier the goal doc asks for
-- returns every ``(slot, byte_offset, native, vm)`` divergence; empty = byte-faithful),
and `object_pool_slot_record` (project the named fields, leaving unknown bytes in
`words()`).  Five tests including a real-image checkpoint: the snapshot of the live
gameplay object table in `memory_1mb.bin` mirrors byte-for-byte, a planted mutation is
detected, and a record projects.  Pure-additive (no live hook/rule path touched) so no
demo-replay needed; lint (184) + both architecture audits + the undefined-name guard pass.
`ObjectPool`✓ -> next: more state structs (PlayerState / CameraState / ...) and migrating
rules to take native state.

## 2026-06-28 - Hygiene tail: name the object-movement clamp playfield bounds

The four A5D1/A5EA/A5F9/A607 axis step-clamp helpers passed raw limits to
`two_pass_axis_clamp_step`; named them in `recovered/systems/movement.py` --
`OBJECT_CLAMP_X_MIN` (20h) / `_X_MAX` (C0h) / `_Y_MIN` (00h) / `_Y_MAX` (B0h), i.e. objects
are confined to X in [20h, C0h], Y in [00h, B0h] -- and used them at the four call sites in
object_movement.py.  Byte-exact (same values); lint (183) + guard + audit pass and the
bounded demo corpus stays byte-exact.

This is the hygiene-tail filler the goal doc sanctions now that the Phase-1 extraction and
Phase-1b relocation veins are exhausted (the substantive remainder is the attended-only
call-tree leaves / death frontier and the Phase 2-5 endgame).

## 2026-06-28 - Coastline (Phase 1b): relocate the CD8D CGA changed-word presenter to cga.py

Moved the changed-word CGA presenter loop at 1010:CD8D (copies one word from the work
buffer to the visible CGA aperture across 8 interlaced scanlines: +2000h/row, +C050h bank
wrap when DI clears bit 14; ends at CE02) out of hooks.py into
`rendering/cga.run_changed_word_present_8rows_cd8d` (ZF + `_test_word` added to cga.py's
imports), leaving a thin wrapper.  Programmatic verbatim move; lint (183) + the guard pass
and the bounded demo corpus stays byte-exact; `hook_inventory.md` regenerated.  Like 38F9,
CD8D is a CGA path the Tandy demos don't exercise, so the move is faithful by construction
(demo-replay confirms no Tandy regression).

This exhausts the cleanly-relocatable inline-render vein: the remaining inline `@registry`
bodies are hook-layer orchestrators (nested `call_X` closures dispatching to other hooks --
correctly in the hook layer) or the entangled 4D15 presence-stamp dispatcher.

## 2026-06-28 - Coastline (Phase 1b): relocate the 4D6F presence-list clear to layer_sprites.py

Moved the hot presence/occupancy-list clear at 1010:4D6F (walks CX word entries from DS:SI,
stops on FFFF, clears the ES occupancy byte; mode CS:[95BC]==1 also clears the stacked
+1A/+34/+4E cells) out of hooks.py into `rendering/layer_sprites.run_clear_presence_list_4d6f`
(DF added to its `dos_re.cpu` import; its local `_cmp_word` is byte-identical to asm's).
Programmatic verbatim move; lint (183) + the guard pass and the bounded demo corpus stays
byte-exact; `hook_inventory.md` regenerated.  Demo-verified (the occupancy grid is
stamped/cleared during gameplay).

## 2026-06-28 - Coastline (Phase 1b): relocate the 469F sprite copy to tandy.py

Moved the hot 9-byte-wide x 16-row plain sprite copy at 1010:469F (DF=0 forward 9 bytes/row
then DI += 2Bh; DF=1 backward as 4 words + 1 byte; clears CX, sets final ADD DI flags) out
of hooks.py into `rendering/tandy.sprite_copy_9x16_469f`, the sibling of the already-lifted
`sprite_blit_9x16_477e`.  Programmatic verbatim move; lint (183) + the undefined-name guard
pass and the bounded demo corpus stays byte-exact; `hook_inventory.md` regenerated.  Unlike
38F9 this one is exercised by the (Tandy) gameplay demos, so the relocation is demo-verified.

## 2026-06-28 - Coastline (Phase 1b): relocate the 38F9 CGA compositor to cga.py

Moved the compact 1-column CGA masked compositor at 1010:38F9 (reached from the compact
layer helper 7746 in mode 0; AND/OR composite one word/row, DI += 32h after STOSW, restore
DS from CS:[9596]) out of hooks.py into `rendering/cga.run_masked_cga_composite_38f9` (DF
added to cga.py's `dos_re.cpu` import), leaving a thin wrapper.  Programmatic verbatim move
(byte-identical body); lint (183) + the undefined-name guard pass and the bounded demo
corpus stays byte-exact; `hook_inventory.md` regenerated.  38F9 has no per-hook oracle and
is a CGA path the Tandy demo corpus may not exercise, but the move is faithful by
construction (the body was relocated, not rewritten).

## 2026-06-28 - Recovery: B9F0 live-X overflow wrap -> recovered rule (+ shared right edge)

The last B9F0 gate: on the overshoot path the live X also wraps once it passes the right
edge (``> D0h -> 10h``, a tighter left margin than the target-X wrap's 20h).  Extracted as
`b9f0_wrapped_x_on_overflow`, and consolidated the shared D0h boundary by renaming
`B9F0_TARGET_X_WRAP_LIMIT -> B9F0_X_RIGHT_EDGE` (now used by both X wraps) with per-wrap
resets `B9F0_TARGET_X_WRAP_RESET` (20h) / `B9F0_X_OVERFLOW_RESET` (10h).  Byte-preserving;
lint + the guard + unit tests pass and the bounded demo corpus stays byte-exact.  B9F0's
decision/computation logic is now fully lifted into seven recovered rules -- what remains
inside it is the bounded original near-calls (5DB2/5E1B/5E42/7476) deliberately run
through the interpreter for stack-scratch fidelity (the call-tree-leaf phase).

## 2026-06-28 - Recovery: B9F0 overshoot spawn gate + BA67 sprite formula -> recovered rules

Two more B9F0 pieces, batched: the overshoot-path formation-spawn trigger
(`b9f0_spawn_counter_ready` -- DS:232E == 3Fh, the top of its 0..3Fh cycle, gating the
7476 spawn) and the BA67 tail sprite/animation word (`b9f0_sprite_from_frame` -- the
global frame DS:233C + 1Ch), with named constants `B9F0_SPAWN_COUNTER_TRIGGER` /
`B9F0_SPRITE_FRAME_OFFSET`.  Byte-preserving (the gate keeps its CMP replay; the sprite
keeps the AX add for fidelity).  Lint + the guard + two unit tests pass and the bounded
demo corpus stays byte-exact.  B9F0 now delegates six rules; the remaining overshoot
`x_word > D0h -> 10h` overflow wrap is the last small gate (shares the D0h right edge with
the target-X wrap -- a future consolidation).

## 2026-06-28 - Recovery: B9F0 periodic-tick helper mask -> recovered rule (+ branch unify)

B9F0's BA5A helper also fires on a periodic tick of DS:2340 -- every 128th tick on the
fast difficulty (DS:BEDC == 2, mask 7Fh), else every 256th (mask FFh).  The original spelt
this as two byte-identical branches differing only in the mask; unified them via a
computed mask owned by the new pure `b9f0_periodic_helper_mask(difficulty)` rule (+
`B9F0_HELPER_DIFFICULTY_FAST`/`_TICK_MASK_FAST`/`_SLOW`).  Byte-exact-by-construction (same
AX masking, CMP flags, and inc/helper side effects); lint + the guard + a unit test pass
and the bounded demo corpus stays byte-exact.  Next b9f0 gate: the `232E == 3Fh` spawn
trigger in the overshoot branch.

## 2026-06-28 - Recovery: B9F0 low-counter helper gate (shared, 2 sites) -> recovered rule

B9F0 runs its BA5A motion helper unconditionally while the level counter DS:A47E is below
6 (otherwise the periodic difficulty-tick test decides).  Extracted that shared gate --
used in both the reached-target and overshoot branches -- as the pure
`b9f0_low_counter_runs_helper(counter)` rule + `B9F0_HELPER_COUNTER_LIMIT = 6`; both sites
delegate (keeping the CMP flag replay).  Byte-preserving; lint + the guard + a unit test
pass and the bounded demo corpus stays byte-exact.  Also corrected the prior goal-doc note
that prematurely declared the behavior decision vein "exhausted" -- b9f0's periodic-tick /
232E gates and aed8's timer/tail selection are still extractable (a8c7 pattern) before the
deep call-tree-leaf phase.

## 2026-06-28 - Recovery: B9F0 reached-target decision extracted to a recovered rule

Recovered B9F0's central branch (1010:BA1F): the follower has reached its target when its
Y plus the vertical delta DS:2342 equals the target Y *and* its X already equals the
target X -- on a hit it refreshes the sprite / runs the movement helper, otherwise it
routes to BA99.  Extracted as the pure `b9f0_reached_target(y, vertical_delta, target_y,
x, target_x)` rule; the adapter keeps the exact AX writes and CMP-flag replays around it
(a8c7 pattern).  Byte-preserving; lint + the guard + a new unit test pass and the bounded
demo corpus stays byte-exact.  B9F0 now delegates two rules (target-X wrap + reached
target); the remaining helper-leaf branches stay bounded original calls.

## 2026-06-28 - Recovery: B9F0 target-X wrap extracted to a recovered rule

B9F0 (the EFAE-selected hot follower) wraps its accumulated target X back to the left
edge (``20h``) once it passes the right edge (``> D0h``).  Extracted that as the pure
`b9f0_wrapped_target_x(target_x)` rule + named `B9F0_TARGET_X_WRAP_LIMIT`/`_RESET`; the
adapter delegates the wrap (keeping the CMP flag replay, dead by the next boundary) with
the exact original write condition.  Byte-preserving; lint + the guard + a new unit test
pass, and the bounded demo corpus stays byte-exact.  Worklist: 8/17 object behaviors now
delegate to a recovered rule.  B9F0's larger reached-target / movement-helper branches
remain bounded original calls -- their ax/flag side effects keep them adapter-side.

## 2026-06-28 - Recovery: ABCA frame-phase gate reuses level_disable_threshold_reached

ABCA (the sprite==0Fh collision body, reached from AD04) gated its motion/tile-probe vs
deactivate path on ``DS:2384 < 0003h`` -- the exact inverse of the verified
`level_disable_threshold_reached` rule (``>= 0003h``) that AB10/ABA3/AB77 already use for
the same frame-phase disable threshold.  Made ABCA's gate delegate to it (keeping the
``LEVEL_PHASE_DISABLE_THRESHOLD`` CMP for flag fidelity, though those flags are dead).
Byte-preserving; lint + the undefined-name guard pass and the bounded demo corpus stays
byte-exact.  Worklist: 7/17 object behaviors now delegate to a recovered rule.  The rest
of ABCA stays bounded original calls (AB34/AC28/AC81/AB99/837A/859E) + the
finish_deactivate slot reset -- the next ABCA increment is naming that deactivation-reset
slot state (logic_id=1, hazard_class=4, latch=0, sprite=0).

## 2026-06-28 - Recovery (consolidation): share the near-camera/render-mode gate across A8C7 + AD04

The A8C7 layer-1 scan and the AD04 logic branch both gate on the same global render state
-- DS:BDAC (full-render mode) and DS:2350 (camera near the left edge, ``<= B6h``).  Slice
a8c7 named those ``LAYER1_*``, but they are not layer-1-specific.  Renamed them to the
global ``RENDER_MODE_FULL`` / ``CAMERA_NEAR_THRESHOLD``, extracted the shared
`camera_near_outside_full_render(render_mode, camera_x)` pure predicate (now used by
`layer1_scan_should_draw`), and named AD04's magic numbers in its adapter
(``AD04_SPRITE_COLLISION_STATE = 0Fh`` plus the shared two).  Byte-preserving -- the named
constants keep their values.  Verified: the a8c7 per-hook oracle (byte-exact) + a new
`camera_near_outside_full_render` unit test + the renamed layer1 test + lint (183) + the
undefined-name guard; AD04 (no fast oracle) exercised via a bounded demo-replay.

## 2026-06-28 - Hygiene: collapse blank-line cruft across object_runtime.py + 3 others

Extends the earlier hooks.py blank pass to the rest of the package's removal cruft:
`object_runtime.py` carried a 53-line void (among others), plus minor runs in
`hook_wrappers/sounds.py`, `gameplay/objects.py`, `asm.py`.  Collapsed every run of 3+
blank lines to 2: -185 blank lines (172 from object_runtime.py).  Pure whitespace -- the
diff touches no non-blank line; lint (183) + the undefined-name guard + the 280-test
hooks/semantics suites stay green.

## 2026-06-28 - Guard: add an import*-aware undefined-name (F821) check to the suite

Promoted the one-off scan that found the 375b NameError into a permanent guard,
`scripts/check_undefined_names.py`, enforced by `tests/test_no_undefined_names.py`.  It
walks every function with full per-scope binding (params, locals,
for/with/except/comprehension targets, nested-def names, global/nonlocal, enclosing
closures, module globals, builtins) and resolves ``from X import *`` by importing X for
its real exports -- several modules build ``__all__`` dynamically (e.g.
``runtime_signatures`` does ``[n for n in globals() if n.startswith("_SIG_")]``), so a
static parse won't do.  Zero false positives on the tree; the test also self-proves the
guard fires on a synthetic undefined name and stays quiet on a bound local.  This closes
the lint gap that let both efae's undefined ``slot`` and 375b's unimported helper ship.

## 2026-06-28 - Correctness: fix a NameError in postcopy_scaled_blit_375b (missing _inc import)

A conservative per-function undefined-name scan -- written because `scripts/lint.py` has
no F821-style check (which is how the dead efae predictor's undefined `slot` slipped
through) -- surfaced a *live* bug among 117 wildcard-import false positives:
`rendering/tandy.postcopy_scaled_blit_375b` calls `_inc_reg16_preserve_cf(cpu, 1)`
(``INC CX`` around the scale multiply) but tandy.py never imported it, so the
``cs:[5905] != 0`` scale branch raised `NameError` whenever it executed.  375b has no
per-hook oracle, so nothing caught it.  Added `_inc_reg16_preserve_cf` to the `..asm`
import and dropped the now-redundant local `_dec_reg16_preserve_cf` def (byte-identical
to asm's).  The fix is byte-exact-by-construction -- `_inc_reg16_preserve_cf` *is* the
interpreter's INC-reg-preserve-CF primitive.  Verified: scanner clear + lint (182) + the
full 239-test per-hook oracle suite (no regression from dropping the local duplicate).
375b still lacks a dedicated oracle (pre-existing gap, flagged for future coverage).

## 2026-06-28 - Hygiene/correctness: remove the dead dispatch-target predictor cluster

`object_runtime.py` carried five `_*_dispatch_target_*` / `_*_target_*` predictors
(5a92 present / 5ac8 draw / 7596 layer-draw / aa2b object-logic / efae object-family),
each meant to predict where a dispatch jump-table lands -- but none were ever called.
All five were imported-unused in `hooks.py`, and the efae one was outright broken: it
referenced an undefined name `slot` (instant `NameError` if invoked), ignored its `bp`
argument, and its docstring (``SS:[BP+18]``) contradicted its body
(``cs:[EFC4 + logic_id*2]``).  They were dead parallels of the *live* dispatch hooks
(`_run_object_logic_dispatch_aa2b`, `_run_object_family_dispatch_efae`, ...) that
actually route.  Removed all five defs plus a 41-line blank gap (83 lines out of
object_runtime.py) and the five dead imports.  The table math survives in the live
dispatch hooks and the commit message.  Verified: lint (182) + audit + import + the full
239-test per-hook oracle suite (the live 5a92/aa2b/efae dispatch hooks stay byte-exact).

## 2026-06-28 - Recovery (dual-mode): extract the A8C7 layer-1 draw predicate to recovered/

The 1010:A8C7 layer-1 scan's `should_call()` decision -- inactive-slot skip, the
out-of-full-render-mode near-camera (``<= B6h``) near-layer suppression, and the
foreground-layer draw test -- is now the pure, named, unit-tested
`recovered.systems.objects.layer1_scan_should_draw` (constants `LAYER1_RENDER_MODE_FULL`,
`LAYER1_CAMERA_NEAR_THRESHOLD = B6h`, `LAYER1_LAYER_FOREGROUND`).  The hooks.py adapter
still reads the slot/global words on the original branches and replays each branch's CMP
flags (live at the A8F1/A8F7 boundary), then delegates the draw decision to the rule.
Byte-exact: the `a8c7` per-hook oracle plus the new
`test_recovered_layer1_scan_should_draw_is_pure_and_named` semantics test pass, with lint
(182) + audit.

## 2026-06-28 - Hygiene: collapse blank-line cruft left by the hook relocations

The masked-compositor / blit relocations (plus the earlier menu-hook removals) left ~20
multi-line blank voids in `hooks.py` (runs up to 61 lines).  Normalized every run of 3+
consecutive blank lines to 2 (PEP8 spacing between top-level defs): 374 blank lines
removed, 3706 -> 3332.  Pure whitespace -- the git diff touches no non-blank line, and
the full 239-test per-hook oracle suite stays byte-exact (33s) so no docstring/string
content shifted.

## 2026-06-28 - Coastline (Phase 1b): relocate the 497A scaled column blit to ega.py

Moved the renderer-dispatch scaled column blit/clear at 1010:497A -- the largest of the
compositor family (95-line body; reached from the 58EC dispatcher via the CS:95BC
function-pointer table, scaling rows DS:SI -> ES:DI planar by the
CS:58FD/5901/5903/5905 accumulator) -- out of `hooks.py` into
`rendering/ega.run_ega_blit_scaled_column_block_497a`.  Clean relocation: ega.py
already imports every asm helper and flag the body uses, so no import churn there.  Body
moved programmatically (verbatim) rather than hand-transcribed to eliminate transcription
risk.  Byte-exact: the per-hook oracle `test_blit_scaled_column_block_497a` passes, plus
lint (182) + audit; `hook_inventory.md` regenerated.

## 2026-06-28 - Coastline (Phase 1b): relocate the 41A6 variable-width interlaced blit to tandy.py

Moved the hot variable-width interlaced row blit at 1010:41A6 -- the same interlaced-
addressing family as 447B but with a variable row width (``REP MOVSB`` BP bytes/row,
then the ``+2000h`` / ``test 4000h`` / ``+C050h`` bank wrap) -- out of `hooks.py` into
`rendering/tandy.run_variable_width_interlaced_blit_41a6`, leaving a thin wrapper
(`_rep_movsb` added to tandy.py's asm imports).  Byte-exact: the per-hook oracle
`test_variable_width_interlaced_blit_41a6` passes, plus lint (182) + audit;
`hook_inventory.md` regenerated.

## 2026-06-28 - Coastline (Phase 1b): relocate the 447B frame-present blit to rendering/tandy.py

Moved the mode-0 frame-present blit at 1010:447B -- the single hottest present routine
once the main loop runs (copies the decoded work buffer CS:[9598] to video
CS:[95A4]=B800 in 192 interlaced rows, with the per-row +2000h/test-4000h/+C050h bank
wrap) -- out of `hooks.py` into `rendering/tandy.run_present_frame_blit_447b`, leaving
a thin `@registry.replace` wrapper.  The shared asm helpers (`_rep_movsw`/`_sub_reg16`/
`_add_reg16`/`_test_word`/`_dec_reg16_preserve_cf`) are imported into tandy.py.
Byte-exact: the per-hook oracle `test_present_frame_blit_447b` passes, plus lint (182)
+ audit; `hook_inventory.md` regenerated.

## 2026-06-28 - Coastline (Phase 1b): new rendering/cga.py -- relocate the 3E12/3EFB CGA compositors

Established `rendering/cga.py` (the CGA byte-level masked-compositor backend, parallel
to `ega.py`/`tandy.py`) and relocated the whole 3E12 (two-shift) + 3EFB (six-shift)
family out of `hooks.py`: both `run_masked_cga_composite_3e12`/`_3efb` bodies plus
their shared pure `_rcr_stc_chain_5bytes`/`_shr_rcr_chain_5bytes` 5-byte shift-chain
helpers.  The thin `@registry.replace` wrappers stay in `hooks.py` (3EFB keeps its
overlay signature guard).  Byte-exact: both per-hook oracles
(`test_masked_sprite_composite_3e12`/`_3efb`) pass, plus lint (182) + audit;
`hook_inventory.md` regenerated.  `hooks.py` sheds ~160 lines of render logic into the
backend module.  Phase-1b masked-compositor family (2E6E/2F81/38B7/3849/3E12/3EFB) now
fully out of the hook layer.

## 2026-06-28 - Coastline (Phase 1b): relocate 38B7 + dedup the immediate-add masked compositors

Relocated the 2-column masked sprite compositor at 1010:38B7 out of `hooks.py` and
folded it together with 3849 into one shared
`rendering/tandy.run_masked_sprite_composite_immediate(cpu, *, words_per_row, row_add)`.
Both are the immediate-row-add siblings of the 2E6E/2F81 family (``ADD DI,imm`` leaves
BX untouched, so they cannot use `_masked_word_composite_rows`): 38B7 = (2, 0x30),
3849 = (4, 0x2C).  Byte-exact -- both per-hook oracles
(`test_masked_sprite_composite_38b7`/`_3849`) pass, plus lint + audit;
`hook_inventory.md` regenerated.  `hooks.py` sheds ~58 more lines; one leaf, two
adapters.  Next Phase-1b siblings: 3E12 / 3EFB / 447B.

## 2026-06-28 - Coastline (Phase 1b): relocate the 3849 masked sprite compositor to rendering/tandy.py

Moved the inline 4-column masked sprite composite loop at 1010:3849 out of `hooks.py`
into `rendering/tandy.run_masked_sprite_composite_3849`, leaving a thin
`@registry.replace` wrapper.  Byte-exact -- the body is unchanged; it uses an
*immediate* row add `0x2C` (leaving BX untouched), so unlike the 2E6E/2F81 family it
cannot reuse the `_masked_word_composite_rows` helper and stays standalone.  Verified
by the deterministic per-hook oracle `test_masked_sprite_composite_3849` (+ lint,
audit); `hook_inventory.md` regenerated.  A direct coastline win: `hooks.py` sheds
~38 lines of render logic into the backend module where it belongs.  Next Phase-1b
siblings: 38B7 / 3E12 / 3EFB / 447B.

## 2026-06-28 - Source-purity rescue: B250 contact fan-out count to a pure formula

Pushed the B250 overlap/contact selector's difficulty-scaled fan-out count down to
a pure rule.  The CX loop count (number of 9E19 post-contact iterations) -- 1 for
most objects, but 1/3/5 for logic_id-3 objects scaling with the contact fan-out
selector DS:BEDC (the difficulty counter) -- moved from
`gameplay/contact_overlap.run_overlap_contact_selector_b250` into
`recovered/systems/objects.contact_fanout_count`.  The adapter now sets CX from the
rule and replays the original CMP flag side effects unchanged (the selector
deliberately preserves AX/BX/CX/flags), so the change is byte-exact by construction.
The contact selector is exercised by the corpus.  Gated green: lint (181), audit,
the new pure unit test `test_recovered_contact_fanout_count_is_pure_and_named`,
demo-replay 23/23.  Begins pushing ContactSystem logic toward `recovered/systems`.

## 2026-06-28 - Source-purity rescue: shared level-disable gate (AB10/ABA3/AB77)

Consolidated the `[2384] >= 3` "level frame phase has reached the disable threshold"
gate that AB10 (deactivate), ABA3 (-> ABC0) and AB77 (-> AB8F) each duplicated into
one shared pure leaf `recovered/systems/objects.level_disable_threshold_reached(value)`
(+ `LEVEL_PHASE_DISABLE_THRESHOLD`), replacing the per-behavior
`AB10_PHASE_DISABLE_THRESHOLD` and `ABA3_PHASE_THRESHOLD` constants.  `object_logic_ab10`
and `object_logic_aba3` now call it; the AB77 shared-tail driver's gate adopts it too
(AB77's only behavior-specific logic was this gate -- the rest is AB4F/AC28/AC81
orchestration with exact IP continuations, so AB77 now counts recovered).  Byte-exact
by construction (same 0x0003 threshold, same `>=` check, unchanged CMP flag replays).
AB10 is heavily exercised (1250 calls in L2_full) so demo-replay verifies the shared
leaf directly; ABA3/AB77 are cold.  This is the "one recovered leaf, many adapters"
pattern.  Gated green: lint (181), audit_architecture, pure unit tests, demo-replay
23/23.  Worklist: 6 DONE (`b73e`/`b86d`/`ab10`/`ae09`/`aba3`/`ab77`), 11 TODO.

## 2026-06-28 - Source-purity rescue: ABA3 tracked-object follower gate+formula to a pure rule

Continued the `object_behaviors` coastline. Slice: the 1010:ABA3 tracked-object
follower probe (reached from AD04 when the slot matches a global tracked-object
pointer). The two pure pieces -- the phase gate (branch to ABC0 once the level
frame phase DS:2384 has advanced to `0003h`) and the sprite formula
(`sprite = scroll frame DS:233C + 14h`) -- moved into
`recovered/systems/objects.object_logic_aba3` (+ `Aba3Update` domain record, named
`ABA3_PHASE_THRESHOLD`/`ABA3_SPRITE_OFFSET`).  The adapter keeps the A42E
tracker-pointer store, the gate CMP flag replay (boundary fidelity) and the AC81
CF/IP collision continuations unchanged, so the slice changes no VM op -- byte-exact
by construction.  (ABA3 is a cold path in the corpus -- the gameplay demos do not
spawn its tracked-object follower -- so it is deliberately a no-op-change refactor,
not a flag drop.)  Gated green: lint (181), audit_architecture, the new pure unit
test `test_recovered_aba3_object_logic_is_pure_and_named`, demo-replay 23/23.
Worklist: 5 DONE (`b73e`/`b86d`/`ab10`/`ae09`/`aba3`), 12 TODO.  Next: `aed8`/`ab77`.

## 2026-06-28 - Source-purity rescue: AE09 object behavior pushed to a pure rule

Continued the `object_behaviors` -> ObjectSystem coastline. Slice: the 1010:AE09
EFAE logic_id 0Ch behavior body. The gameplay decision (a countdown timer in slot
`substate` decrements while non-zero, clearing `direction_or_step` on the frame it
reaches zero; the object steps left `x -= 2` on the frame the timer is zero or has
just expired; outgoing sprite = `direction_or_step + 28h`) moved out of the lifted
adapter into the pure VM-free rule `recovered/systems/objects.object_logic_ae09`
(+ `Ae09Update` domain record, named `AE09_SPRITE_OFFSET`). The lifted
`_run_object_behavior_ae09` is now a thin adapter: `ObjectSlotView` reads -> rule
-> slot writes (substate/direction/x/sprite) -> the already-lifted AF22 + AD60
tail. Every CMP/DEC/SUB/ADD flag of the body is dead at the AF22 boundary (AF22's
first ops overwrite them; the disasm and the prior lift that already dropped the
ADD flags both confirm it), so the adapter needs no flag replay. Gated green: lint
(181), audit_architecture, the new pure unit test
`test_recovered_ae09_object_logic_is_pure_and_named`, demo-replay 23/23 bounded,
and an extended L2_full verify exercising AE09 48x byte-exact. Worklist: 4 DONE
(`b73e`/`b86d`/`ab10`/`ae09`), 13 TODO. Next: `aed8`/`aba3`/`ab77`.

## 2026-06-28 - Faithful level-select replay (menu hooks removed + per-poll demo input)

Full-arc demos that cross the level/difficulty-select screen now replay it
faithfully (previously they deadlocked there, then once unblocked they landed on
the wrong planet). The screen samples the keyboard sub-frame through stateful
debounce loops, but demo input was applied at frame granularity, so same-boundary
release+repress pairs collapsed into one tap. Two coupled changes:

- Removed the approximate level-select replacement hooks (1010:D390 fire-release,
  D434 input-release, D445 selector loop) so the original selector runs as raw ASM
  on every runtime; `overkill.input_waits` already resolves the boundary-less spins
  for both the headless verifier and play.py. Net -431 lines (the hooks + their
  `input_menu` lift bodies + 5 per-hook oracle tests + 3 `HookStop` entries; also
  dropped the now-dead `play.py` `is_input_selector_wait`). `hook_inventory.md`
  333 hooks (was 336).
- `overkill.input_waits.pump_demo_frame` schedules demo input by recorded boundary
  (preserving timing) but, on the level-select screen, delivers one event per
  keyboard poll and defers at present/render boundaries so each release is consumed
  before the next press. Used by the demo-replay test and all three play.py demo
  paths; a coarse-burst selector-head scan keeps detection robust under play.py's
  `cpu.run` chunks.

Verified: menu-only demo `004406` full-verifies byte-exact in the dual-runtime
verifier; intro-start demo `231013` navigates to the same planet/difficulty it
recorded; corpus 23/23 bounded; lint/audit/island-drift green. Commits a11a26c +
this cleanup. (Interactive menu *pacing* runs faster than the recording because the
older demos were recorded against the previous menu cadence — cosmetic; the
verifier is frameless so the goal-run gate is unaffected.)

## 2026-06-27 - Source-purity rescue: AB10 object logic pushed to a pure rule

Resumed the rescue (lifted -> pure recovered systems; hooks thin; VM = oracle;
recovered pieces form the native game). Slice: the 1010:AB10 logic_id=6 per-frame
update. The gameplay decision (deactivate when DS:2384 or DS:A47C >= 3, else
sprite = DS:A40C anim byte + 9 and position = DS:A414 anim pair + DS:237C view
box) moved out of the hook into the pure VM-free rule
`recovered/systems/objects.object_logic_ab10` (+ `Ab10Update` domain record,
named `AB10_PHASE_DISABLE_THRESHOLD`/`AB10_SPRITE_BASE_OFFSET`). The lifted
`_run_object_logic_ab10` is now a thin adapter: DOS reads + XLAT/anim-pair
addressing + the original CMP/ADD flag and register boundary, delegating the logic
to the rule. Gated green: lint (181), audit_architecture, the new pure unit test
`test_recovered_ab10_object_logic_is_pure_and_named`, and demo-replay equivalence
21/21 (byte-exact, 2:45). Next: continue the object_behaviors list (the
gameplay_objects -> ObjectSystem coastline).

## 2026-06-19 - Refactor Phase 2: structured (typed-view) access

Following refactor_plan.md Phase 2. **ObjectSlotView is now fully write-complete**
-- every writable object-record word has a setter. Converting raw
`mem.rw/ww((ss|ds), (bp|bx) + OFF_*)` to `slot.field`, byte-exact, gated per
slice. Converted (fully or the high-value functions): object_postmove, collision,
object_deactivation (BD17/BFC7), contact_overlap (B250), action_spawns, objects
(C3BF/C3F1/C4E5 resets), object_runtime (B1B0 chase, AE2C/AE7D drift),
contact_side_effects (62F6 scan -- the open-coded signed-X test became
`slot.x < 0x20`), object_spawns (8209 seed copy). Flag-affecting helpers,
stack-scratch and DS-global accesses left as-is; single-read dispatch helpers
that already use named offsets left as-is. Each slice: oracle 244/244 +
demo-replay 19/19 + lint.

Remaining Phase 2: object_behaviors (~69 accesses, untouched), the rest of
object_spawns/object_runtime/contact_side_effects (the messier mixed-compute
functions), game_state (partial), and the DS-global reconciliation (below).

NOTE (design call for the user): DS-globals already carry **conflicting names**
across modules for the same address (e.g. 0x2380 = OVERLAP_REF_BOX_Y /
POSTMOVE_CONTACT_Y_GUARD / camera_or_view_y_2380; 0xA47C = TILE_COLLISION_GLOBAL_
GATE / phase_gate_a47c). The DS-global part of Phase 2 is a *reconciliation* into
one canonical name per address, not just naming raw hex -- to be done
deliberately. Remaining typed-view files: object_behaviors, object_spawns,
object_runtime, contact_side_effects, objects, game_state (partial).

## 2026-06-19 - Refactor Phase 1: retire dead-stack scratch (gameplay)

Following docs/overkill/refactor_plan.md. The relaxed boundary-contract oracle
(assert_oracle_equivalent + harness dead-stack ignore, _DEAD_STACK_BYTES=0x40)
lets hooks drop the "write the dead CALL return word below SP" fidelity code.
Retired across three commits: the _remember_balanced_push_scratch helper + its 7
uses; ~13 inline `mem.ww(ss, sp-N, <const>)` writes (object_behaviors,
object_bounds, object_deactivation, object_movement, object_runtime,
object_spawns, hooks) with their dead ss/sp precomputes, the
remember_internal_call helper + vestigial ret_ip params, and stale comments.
~10 oracles switched to assert_oracle_equivalent. Real pushes (live return
words) kept; frame_orchestration's 606F write kept (lands at SP, live). Every
slice gated green: oracle 244/244, demo-replay 18/18, lint. Asset-codec
(rle/packed_stream) dead-stack writes also retired (commit 933e756) -- gated by
the codec oracles + snapshot-loading hooks; the live `saved_cx` CX-restore is
kept (an over-eager first pass removed it; the oracle suite caught it, a good
demonstration that the gates protect the relaxation). **Phase 1 complete.** Next:
Phase 2 (structured access -- typed views, named offsets, named DS-globals).

## 2026-06-19 - Standing divergence-diagnosis tool (scripts/trace.py)

Replaced the per-bug throwaway watchpoint scripts with one reusable dual-runtime
tracer.  `scripts/trace.py` replays a demo through reference (ASM oracle) and
candidate (hooked) in lockstep with a probe on each side:
- `watch SEG:OFF`  -- log writes to an address/range on both sides, report the
  first write whose *value* (not IP -- raw-ASM vs lifted-hook IPs differ
  legitimately) diverges. Re-finds the camera-Y `1010:9C55` extra write.
- `observe CS:IP --reg .. --mem ..` -- dump registers/memory at a CS:IP on both
  sides (found the 9C01 `[a47c]` gate divergence).
- `globals SEG:OFF ..` -- diff arbitrary DS/CS globals each frame, report the
  first diverging frame (a fast bisector; flagged `a360` at f66, two frames
  before the verifier's own f68 detection).
Validated by temporarily reverting the camera-Y fix: the tool pinpointed it.
Retired the unreferenced one-off `scripts/_debug_5c74_*` / `_debug_ecf2_ah`
debug scripts (six) it supersedes.

## 2026-06-19 - Fix menu_interaction demo (frame-verifier timer-tick wait)

The standing `menu_interaction` demo-replay failure was a reference-side TIMEOUT
at `1010:CBE4`, not a state divergence (all decoded state matched between sides
through frame 88). Root cause: the menu transition's CB3E delay (5x CALL CBD5)
busy-waits on the timer tick `DS:[54]`, which the frame verifier never advances
because it models time via the 0679/50C9 boundaries and never fires the async
INT 1Ch ISR (`06E5`) that does `inc [54]`. So `[54]` stayed 0 and the oracle
spun. Interactive play fires the ISR, so the live menu was fine. Fix: added
`input_waits.advance_frame_tick_wait`, a verifier-only per-step resolver that
ticks `DS:[54]` when a side is parked in the CBD5 busy-wait (signature-guarded,
only when spinning), letting the delay drain in lockstep on both sides. Whole
demo-replay suite now green (18/18, 0 failures). See loop_blockers.md (RESOLVED).

## 2026-06-19 - Fix mothership camera-Y divergence (9C01 [a47c]==0 guard)

Attended bisection of the standing `mothership_drag_edge_case` demo-replay
failure (camera anchor `DS:2380` +1 at the mothership). Traced via a `2380`
write-watchpoint -> the hook ran `9C01` (camera step) on frames the ASM skipped.
The `9B2E` lift (`frame_orchestration.py`) had dropped the `[a47c]==0` guard on
the `9C01` call: ASM `9BCF jne 9BDF` gates BOTH `9CB6` and `9C01` on `[a47c]==0`,
but the lift gated only `9CB6`, leaving `9C01` gated by `[2350]>0xB6` alone. After
the mothership trigger (`A66F`) sets `[a47c]=1` (scroll lock), the hook kept
stepping the camera. Fix: nest the `[2350]` gate + `9C01` under `if [a47c]==0`.
Demo-replay: 2 failures -> 1 (`menu_interaction` remains); 17/18 green. Added
`phase_gate_a47c`/`level_progress_2350` to the semantic snapshot. Frame-controller
oracles + recovered-semantics still green. See loop_blockers.md (RESOLVED entry).

## 2026-06-19 - Loop slice: oracle-suite scan; remove a missing-data test

Ran the full hook oracle suite to find pre-existing failures now that raw-drains
are done. 4 failed / 241 passed. Triage:
- `b00d_..._direction_table`: bound to `artifacts/repros/demo_divergence_tandy_
  20260616_160515` which is gitignored/gone -> REMOVED the test (same as the
  earlier b1b0 cleanup; the B00D hook stays covered by demo replay). 244 collect.
- `bdd0_..._hit_path`: already logged in loop_blockers.md (jmp-5059 granularity).
- `d434_..._poll_gate`: only FLAGS differ (hook 0202 vs asm 0297) -> a flags-
  replication gap; queued.
- `expand_tandy_list_33af`: control-flow divergence (hook 44AA vs asm 33B2);
  queued.

## 2026-06-19 - Loop slice: final raw-offset sweep (raw-drain complete)

Byte-exact: 10 `bp` (SS:BP object-slot) accesses across 4 files -> named OFF_*.
collision.py (X/Y in the AC81 scan setup), game_state.py (Y in the A60A/A5FC
one-pass Y-step helpers), object_deactivation.py (ACTIVE_WORD, PREVIOUS_LOGIC_ID),
object_runtime.py (ACQUIRED_TARGET_PTR in the B1B0 chase). Dashboard: record
offset accesses 13 -> 3 raw (4% -> 1%).

The raw-drain is now at its floor: the only remaining "raw" hits are the two
genuinely-unnamed words (object_spawns 0x26, object_movement 0x36 - both written
with no lifted reader, so they stay honest unknowns) and a register-arithmetic
false positive (`si = si + 0x0006`). Total drained this run: 138 -> 3 (40% -> 1%).

Verified: fresh imports (all 4 files), lint (151), audit (17 pure), the AC81/
Y-step/BD17/C054/B1B0 oracles, demo-replay (only the logged divergences fail).

## 2026-06-19 - Loop slice: drain contact_side_effects.py raw offsets

Byte-exact raw-offset drain: 22 object-record accesses in contact_side_effects.py
-> named OFF_* constants. `bp` (current slot): COUNTER_20 (x12 in the contact
counter-decrement paths), GATE_OR_LAYER, VARIANT. `bx` (scanned/owner slot in the
contact scan): X / Y / SPRITE_OR_STATE / LOGIC_ID / SUBSTATE / SCAN_ENABLE_OR_SOLID
/ ACQUIRED_TARGET_PTR. The flag-bound bx-walk loop control is untouched; only the
field-access offsets are named. Dashboard: record offset accesses 35 -> 13 raw
(10% -> 4%).

Verified: fresh import, lint (151), audit (17 pure), the bec5/bedc/aa71 contact
oracles (22 pass), demo-replay (only the 2 logged divergences fail; no regression).

DISCOVERED a pre-existing failing oracle while running the contact suite:
`test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_hit_path`. The BDD0
hook returns to the caller (`CAFE`) on the hit path, but the original continues to
`1010:5059`. Confirmed failing at baseline with this drain stashed, so it is NOT
caused by this byte-exact rename (a control-flow difference can't come from an
offset-constant swap). Queued as the next fix slice.

## 2026-06-19 - Loop slice: drain objects.py raw offsets

Byte-exact raw-offset drain: 22 `bp` (SS:BP object-slot) accesses in objects.py's
slot-init/reset loops and the AB4F scroll-sprite helper -> named OFF_* constants
(ACTIVE_WORD / X / Y / DIRECTION_OR_STEP / SPRITE_OR_STATE / GATE_OR_LAYER /
LINK_KEY / HAZARD_CLASS / LOGIC_ID / VARIANT). Dashboard: record offset accesses
57 -> 35 raw (17% -> 10%). The `s.bx +` source reads were left raw (separate
struct, role less certain). Verified: fresh import, lint (151), audit (17 pure),
objects oracles (aa2b/ab4f/...), demo-replay (no new failures; the 2 pre-existing
mothership/menu divergences are logged in loop_blockers.md).

Also: installed capstone and logged loop_blockers.md - disassembled the BFC7
player-death tail and proved its C037 jump-table dispatch is correctly lifted, so
that divergence is elsewhere in BC4B's path (logged for a reproduction trace).

## 2026-06-19 - Loop slice: drain action_spawns.py raw offsets

Byte-exact raw-offset drain: the 6 `bx` slot-stamp accesses in action_spawns.py's
action-spawn tail -> named OFF_* constants (SCAN_FLAG / HAZARD_CLASS / LOGIC_ID /
SUBSTATE / SCAN_ENABLE_OR_SOLID / ACQUIRED_TARGET_PTR). Dashboard: record offset
accesses 63 -> 57 raw (19% -> 17%).

Verified: fresh import, lint (151), recovered-layer audit (17 pure), the
a067/a515/a584 action-spawn oracles, demo-replay (16 pass). The 2 demo failures
(menu_interaction, mothership_drag_edge_case) are pre-existing open divergences -
confirmed by a stash-baseline check that they fail without this change - NOT a
regression from this byte-exact rename. Both go on the open-divergence list.

## 2026-06-18 - Name 4 object-record fields, drain raw offsets, fix the 9FAF sidearm-drag bug

Map-driven slices (the dashboard surfaced unnamed-but-used words; a quick trace
named them), then byte-exact raw-offset drains, then a real edge-case bug fix.

Field discovery (object record now 25/28 mapped: 10 known, 15 guessed, 3 unknown):
- 0x2E -> `move_step_error` (Bresenham movement step accumulator; known).
- 0x2A/0x2C -> `move_delta_x`/`move_delta_y` (signed object-minus-target deltas;
  known) - the 5E1B delta helper computes them, the 5E42 steer consumes them.
- 0x28 -> `linked_counter_index` (guessed): index x16 into the DS:2078 linked-
  counter table (FFFF = unlinked).  Cross-layer rename that removed the `field_28`
  placeholder from the pure domain/system and deleted a duplicate offset constant.
- Each adds a view getter (consumed by a real read), a map row, and a test row.
  The 3 remaining unknowns (0x10/0x26/0x36) lack a lifted reader, so they stay
  honestly `unknown` rather than guessed.

Raw-offset drain (byte-exact, scoped per register to confirmed object records):
- object_spawns.py: 41 `bx`/`si` slot accesses -> named OFF_* constants.
- object_movement.py: 18 `bx`/`s.bp` accesses -> named.
- Left untouched: `bp` caller-frame reads (different struct), table pointers, and
  the unknown 0x26/0x36.  Dashboard: record offset accesses 138 -> 63 raw
  (40% -> 19%).

BUGFIX - mothership sidearm-drag divergence (1010:9FAF): the lift called the final
9FEA child-coord update unconditionally, but the original guards it
(`CMP BX,FFFF / JNZ / RET`) and skips it when the 4th linked slot is inactive -
i.e. a ship carrying fewer than 4 sidearms/drones.  The extra write corrupted the
DS:A30A coord trail (DI off by one entry).  Added the guard + a regression test
for the `[A966]==FFFF` case the original oracle never covered.

Housekeeping: removed `test_object_player_chase_b1b0_*` (bound to the deleted demo
`demo_play_tandy_20260616_000527`); the live B1B0 hook stays covered by demo
replay.  Committed the new short demos as fixtures (L5/L6/menu/mothership/death).

Known open (separate, pre-existing): mothership camera-Y (`DS:2380`) +1 and a
player-death `BC4B`/`BFC7` death-tail divergence - both edge branches in the
still-partial death/deactivation frontier (BFC7/BD17/C054).

Verified: lint (151) + recovered-layer audit (17 pure) + map tests + the
9FAF/5E1B/5E42/5db2/spawn oracles + all demo replays native==VM (non-mothership).

## 2026-06-18 - Living memory map + collapse the triplicated object-record decode

Two slices, each leaving the live path cleaner (not just adding on top).

Living memory map (visibility):
- `OBJECT_RECORD_FIELDS` in `recovered/views/object_slots.py` now catalogs every
  16-bit word of the 0x38 object record with a discovery status: `known` /
  `guessed` / `unknown`.  The seven previously-silent gaps (0x10, 0x26, 0x28,
  0x2A, 0x2C, 0x2E, 0x36) are explicit `unknown` rows; inferred names are marked
  `guessed` instead of reading as settled fact.  Offsets reference the existing
  `OFF_*` constants (no re-typed numbers).
- `scripts/source_port_status.py` now prints struct coverage and the offset-access
  migration runway: `object_record (0x38): 21/28 words named (7 known, 14
  guessed, 7 unknown)` and `record offset accesses in gameplay/: 203 named, 138
  raw hex (40% still raw)`.  Progress is now a number that moves.
- Checked by two new tests (map covers every word once; agrees with the OFF_*
  constants and the documented gaps).

Hygiene collapse (fewer parallel representations):
- The object-record offset->field mapping lived in three places (view properties,
  `ObjectSlotSnapshot` fields, and the adapter's `w(OFF_*)` hand decode).  The
  adapter now builds the snapshot straight from the live `ObjectSlotView` named
  fields + `record_bytes()`, so the layout lives in ONE place (the view).  The
  adapter dropped ~13 `OFF_*` imports and its private `w()` decoder.
- The snapshot's frame-timer read now goes through `FrameTimersView` too, removing
  a second reproduction of the DS:2368 table layout.
- `contact_overlap.OFF_SUBSTATE_1E` was a re-typed `0x1E`; it now aliases the
  canonical `OFF_SCAN_ENABLE_OR_SOLID` (one source for the number).  The local
  name is kept and the naming ambiguity marked: collapse to one name once
  evidence settles whether "skip-overlap" and "scan-enable/solid" are one role.

Verified byte-identical: lint (151) + recovered-layer audit (17 pure) +
recovered-semantics/checkpoint-handoff (39) + all 8 demo replays native==VM +
the B250 overlap/contact + bounds/61C7 oracle suites.

Housekeeping: removed 6 tests that hard-depended on the now-deleted root snapshot
`artifacts/snapshot_play_tandy_20260614_191454`; made the AdLib bundle test skip
(with a regenerate hint) instead of hard-failing if `artifacts/static_runtime_bundle`
is cleared.  All other test data already lives in curated subfolders.

## 2026-06-18 - VM-backed views translation layer, introduced by use

Built the typed translation layer between the VM and the source-like code, with
each view introduced by a real live consumer (no speculative/dead overlays) and
proven byte/register/flag-exact:

- `recovered/views/object_slots.ObjectSlotView`: extended to full field coverage
  (object_type, draw_layer, row_or_phase, substate, scan_enable_or_solid,
  counter_20, variant, acquired_target_ptr, ...) + a `record_bytes()` record read.
  First live use: `gameplay/object_bounds.py` AD60 bounds tail now reads
  `slot.x_word / y_word / draw_layer / logic_id` instead of raw `mem.rw(ss,bp+OFF)`.
  The flag-affecting `_add_mem_word` pre-add stays as visible ASM glue.
- `recovered/views/object_slots.ObjectTableView`: a live lens over a whole
  effect/gameplay table (indexable/iterable slot views, `.active()`). First live
  use: `game_snapshot_adapter._decode_table` iterates it and reads each slot via
  `record_bytes()` (byte-identical to the old per-byte read).
- `recovered/views/frame_timers.FrameTimersView` (new module): the six `DS:2368`
  countdown counters (read-all / write-one / `address_of` / `end`). First live
  use: the 61C7 frame-timer scan in `gameplay/game_state.py`, which now reads
  `timers.values()` and writes `timers[k]`, keeping the exact DI/flag contract.

The layer rule: a view replaces the *memory access* only; flag/register-exact ASM
(`_add_mem_word`, `set_sub_flags`, scan-loop BX walks) stays in the lifted body.
Documented in ARCHITECTURE.md ("VM-backed views (the translation layer)") and the
`recovered/views/__init__.py` package docstring.

Validation:

```text
python scripts/lint.py                      # 151 files
python scripts/audit_recovered_layers.py    # 17 pure files (views are bridge, not pure)
python -m pytest tests/test_overkill_hooks.py -k "b24d or bounds or ad5a or aed8 or b73e or 61c7 or 61f7 or decrement_counter" -q   # oracle: byte/reg/flag identity
python -m pytest tests/test_recovered_semantics.py tests/test_checkpoint_handoff.py tests/test_demo_replay_equivalence.py -q        # snapshot decode + demo-replay native==VM
```

## 2026-06-18 - Phase 1 lift: B73E target-reached 4-way resolution

Lifted the B73E `B7BD/B808` target-reached dispatch (reached once an object is at
its waypoint and past the optional B800 spawn) into the pure
`b73e_target_reached_resolution(a47e, game_counter, value_232e)`
-> `B73ETargetReachedResolution` (`reset_target_check_2324` / `reset_target_direct`
/ `postmove` / `waypoint_loop`).  `_run_object_behavior_b73e` now classifies once
and asserts agreement while replaying the original CMP order at each branch.

Verified by the six `b73e` oracle tests (full-state + full-memory vs interpreted
ASM), a new pure unit test, and the demo-replay equivalence suite (L1/L2/L3 all
native == VM).  This is the first lift proven by the new whole-game proof spine in
addition to the per-hook oracles.

## 2026-06-18 - Whole-picture map of the remaining interpreted ASM

Used fresh L2 + L3 coverage dumps (95-96% hook-covered) to map every hot
interpreted region by disassembly, so we know exactly how the game is wired and
what is left.  Findings written up in `runtime_findings.md` ("Remaining
interpreted-ASM wiring map").  Summary: the engine spine is native; the remaining
gameplay interpreted is a finite queue of structurally-identical object-behavior
bodies (`8xxx`/`Bxxx`/`Fxxx`, all: animate via XLAT sprite table -> move -> maybe
spawn 7476 -> jmp BC45), plus a few collision tails (`BFC7`/`BE3C`/`BEA4`/`BB03`),
plus the frame-loop spine `97C8` (Phase 6, last), plus the sound driver `2032:*`
(~88% of interpreted - the separate OPL long pole).

Disassembled and classified in `symbols.json` (so coverage stops calling them
"unknown"):
- `1010:97C8 main_frame_loop_body_97c8` - the 97B2 per-frame loop body.
- `1010:BB80 object_behavior_sprite_spawn_bb80` - sprite/animate + 2330==57h
  formation-spawn behavior (hot in both L2 and L3).
- (`1010:B2CD` waypoint behavior was classified in the prior note.)

Also confirmed the `9E19` collapse landed: in L3 the `B297` region dropped from a
hot 9E19 loop to ~9.6k (now classified `gameplay_objects`); the remaining L2
`B297-B32A` mass is the separate `B2CD` waypoint behavior.

No behavior change this pass (disassembly + classification + docs only).

## 2026-06-18 - Guard strengthened: semantic snapshot now covers global counters

The checkpoint-collapse strategy proves correctness by frame/state equivalence, so
the snapshot's coverage IS the correctness guard.  It previously decoded only
frame timers + score + object slots, missing the global counters that drive object
lifecycles - exactly the state class the ringlas bug hid in (DS:A972 diverged but
was invisible to the verifier, so it was only caught downstream once it corrupted
object slots).

Widened `GameSnapshot` with `state_globals` (pure: names + values), decoded by
`game_snapshot_adapter.SNAPSHOT_GLOBAL_WORDS` - reusing `world_adapter`'s
evidence-backed globals (camera, allocator cursors, tile-sweep, boss counter, ...)
plus the gameplay counters/gates: action-spawn/weapon-list counters DS:A970..A978,
DS:A97E, formation counter DS:2340, gates 2330/232E/2356, contact fanout BEDC,
mode flag BDAC.  `diff_game_snapshot` reports `globals.<name>` divergences.

No new infrastructure - it extends the existing snapshot/diff and reuses the
address evidence already in `world_adapter` (no parallel state model).  The
verifier now catches a counter divergence at the source frame instead of waiting
for it to manifest in objects/vram.

Verification:

```text
python -m pytest tests/test_recovered_semantics.py -q   # incl. globals diff + decode tests
python scripts/audit_recovered_layers.py                # domain stays pure (17 files)
python -m pytest tests/test_demo_replay_equivalence.py -q -k "ringlas or showcase or L2 or L5_start"
# 4 passed - candidate and VM agree on the new globals (no hidden divergence; broader guard)
```

## 2026-06-18 - Key finding: the frame is ALREADY a native chain inside 97B2

While making the handoff executable, a `cpu.ip`-visit census over ~250 frames of
L5 gameplay revealed how far the collapse already is: the frame-loop hook `97B2`
("lifted as one verified iteration") **composes the whole frame as native Python**.
Most phase/"checkpoint" addresses are never visited as `cpu.ip` because they run as
direct function calls inside that chain:

```text
97B2  1757x   <- the per-frame resume point that IS visited
A940/AA10  3x each      A90C 3354 A846 5BDC 0162  0x   <- composed away
```

Implications:
- The **frame boundary (`97B2`/`D007`) is the real `cpu.ip`-visited resume point**;
  the sub-phase checkpoints (render/object-update) are already fused inside the
  frame chain.  `taxonomy` checkpoints are *logical* boundaries; only the frame
  ones are current handoff points.  (`scripts/capture_demo_snapshot.py
  --at-checkpoint frame` captures there; sub-phase kinds mostly will not match
  because those addresses are not visited.)
- The demo boundary clock (present/timer at 3354/0679) is itself largely composed
  inside 97B2, so it advances slowly under raw single-runtime replay - which is why
  deep `--min-boundary` captures are slow.  The demo-replay verifier installs the
  boundary hooks explicitly, so it is unaffected.
- Re-scopes "collapse 319 glue hooks": the frame loop is **already** a native
  chain; the remaining glue is the gameplay behaviours/tails that chain still
  bounces into (the object-update phase).  So the next real target is collapsing
  the object-update phase's behaviour dispatch, not re-doing the frame loop.

## 2026-06-18 - Untie: VM-until-checkpoint handoff is now executable

Made the checkpoint model runnable code, not just doctrine:

- `overkill/checkpoints.py`: `run_to_next_checkpoint(cpu, kinds=...)` steps the VM
  (instruction-exact oracle) from any position to the next logical checkpoint
  (frame/render/object-update/input), derived from the evidence-based phase map in
  `hook_taxonomy`.  This is the "run in VM until the first compatible checkpoint,
  then hand off" primitive.
- `tests/test_checkpoint_handoff.py`: proves it - from a gameplay snapshot the VM
  fast-forwards to a frame checkpoint, lands exactly on it, the decoded
  `GameSnapshot` is consistent there, and two consecutive frame checkpoints differ
  by exactly one frame of gameplay (a real boundary, not a mid-chain point).
- `scripts/capture_demo_snapshot.py` gained `--at-checkpoint <kind>`: capture an
  oracle snapshot at a stable, resumable checkpoint instead of an exact mid-chain
  `CS:IP`.  This is the *right* shape for oracle capture and fixes why the BB80
  mid-chain capture kept timing out - capture at the object-update checkpoint
  (which occurs every frame) instead.

Why this unties our hands: a snapshot can now be taken anywhere, fast-forwarded in
the VM to a checkpoint, and resumed by native code; and a collapsed chain between
two checkpoints is verified by semantic frame/state equivalence (the demo-replay
suite), with no obligation to reproduce intermediate `CS:IP`s.  Next: collapse one
whole frame phase (render `A846`->`5BDC`->present is the cleanest, vram-verifiable)
into a single native system between the object-update and render checkpoints.

## 2026-06-18 - Strategy: the frame is already a checkpoint sequence (D007)

Inspected the gameplay main loop `1010:D007` (per user direction) and found the
frame is ALREADY a linear chain of `CALL`/`RET` phase calls, each a stable,
verifiable boundary and each already a registered hook:

```text
D007 frame top -> 0672(env) -> 511F/A846 render -> 5BDC/3354 present[RENDER]
     -> A90C/A940/AA10 [OBJECT-UPDATE] -> 5F61/073C -> 5160/0679 wait(env)
     -> 0162 [INPUT] -> jz D007 [FRAME]
```

So the source-port loop does not need inventing: it is D007's phase sequence, each
phase a native system entered/exited at its checkpoint, with the behaviours/tails/
helpers each phase calls being the glue to fuse inside it.

Updated the strategic documents to make checkpoint-first the project strategy:
- `docs/overkill/semantic_crystallization_plan.md` - new top section
  "Checkpoint-first execution model (read this first)": VM = instruction-exact
  oracle; source port = checkpoint-level; VM-until-checkpoint handoff; "promote
  hooks upward" reframed as "collapse glue between checkpoints into source-like
  systems", proven by frame/state verification.
- `ARCHITECTURE.md` - "Snapshot model" section now carries the D007 frame map and
  the VM-until-checkpoint handoff.
- `AGENTS.md` - hooks are candidates for checkpoints, not permanent patch points;
  the per-hook proof obligation is VM-oracle-side only.
- `overkill/hook_taxonomy.py` refined to the evidence-based D007 phase set
  (12 checkpoints / 5 env-waits / 319 glue), locked by `tests/test_hook_taxonomy.py`.

Implication for VM-until-checkpoint handoff: oracle snapshots no longer need
capture at a behaviour's exact entry - capture anywhere, fast-forward in the VM to
the next checkpoint, resume natively.  (This is why the BB80 mid-chain capture was
the wrong shape; capture at the object-update checkpoint instead.)

## 2026-06-18 - Methodology: checkpoint-level snapshots, hooks classified by role

Adopted an explicit model (per user direction): stop treating every hook address
as a permanent source-port boundary.  The VM/original ASM stays instruction-level
snapshotable as the oracle; the source-port runtime is **checkpoint-level**
snapshotable - it resumes only from stable logical boundaries (frame,
object-update, render, input, plus hardware waits).  Between checkpoints, lifted
code may run as one atomic deterministic chain with no obligation to preserve old
`CS:IP` bounces or mid-chain resume; a mid-chain snapshot defers to the next
checkpoint.  Correctness is protected by the semantic frame/state verifier
(the demo-replay equivalence suite), not by historical hook boundaries.

Implemented:
- `overkill/hook_taxonomy.py` classifies hooks by role: `checkpoint` / `env_wait`
  / `debug_probe` / `glue`.  Curated checkpoint + env-wait sets are small and
  explicit; everything else is `glue` (the honest majority).
- `scripts/source_port_status.py` now reports the split: ~8 checkpoint, ~4
  env_wait, ~324 glue.  The glue count is the collapse target and the headline to
  drive down.
- Documented the model in `ARCHITECTURE.md` ("Snapshot model: checkpoints, not
  hook boundaries"); per-hook `verification.py` metadata stays the VM-side proof
  only.

Reframes the BB80 lift (deferred): instead of reproducing BB80's exact `CS:IP`
bounces (the multi-entry dispatch + the BBED tile-probe's mid-chain returns - the
reason it was awkward), treat BB80 as glue between the object-update checkpoint
and the render checkpoint and collapse it into one atomic source-like chain,
verified by frame/state equivalence over the corpus.

## 2026-06-18 - Demo corpus expanded to 8; full-weapon showcase verified clean

The corpus is now 8 demos (L1-L5 + the all-weapons attract showcase), all passing
the bounded native-vs-VM demo-replay equivalence suite.  The
`demo_play_tandy_showcase_*` attract demo (input-free, cycles every weapon and
ship upgrade) ran the divergence hunt to 4000 frames with **zero divergence** -
the strongest equivalence signal so far, independently confirming the ringlas fix
and that no other weapon has a similar lifecycle/deactivation bug.

```text
python -m pytest tests/test_demo_replay_equivalence.py -q   # 8 bounded passed, 8 full skipped
python scripts/find_demo_divergence.py <showcase demo> 4000  # rc=0, no divergence to frame 4000
```

Open frontier (unchanged): a post-input divergence ~1370 frames past the ringlas
demo's recorded end (score delta + `logic_id 0x3B` effect slot) - not reproduced
by the showcase, so it is a narrow post-demo edge case, not a general weapon bug.

## 2026-06-18 - BUGFIX: ringlas (logic_id 9) deactivation cleared the whole list

User-reported: the ringlas (last weapon) misbehaved in heavy L5 play and the game
crashed (`UnsupportedInstruction` at a mid-instruction address - corrupted control
flow, not a missing opcode).  Root-caused with the demo-replay divergence hunt on
the user's short repro demo (`demo_play_tandy_L5_ringlas_divergence_*`):

- First native-vs-VM divergence at frame 70: ~20 `logic_id 9` objects (the ringlas
  projectile column) that the original deactivates but our hooks kept `active=1`.
  Those stale slots accumulated, corrupted memory, and ~frames later caused a bad
  jump -> crash.
- Traced the original deactivation: object scan -> `EFAE` (logic dispatch) ->
  `ADEF` (`jmp AD60`) -> out-of-bounds -> `BD17`.  `BD17` dispatches on `logic_id`,
  and **`logic_id 9` jumps to `BD7A`**, which clears the WHOLE projectile list
  (the `BD82` loop: walk the FFFF-terminated `DS:A3B4` pointer list, set each
  listed object's `active=0`, drain `DS:A972`).
- Our `_run_deactivate_bd17_observed` mis-modeled `logic_id 9` as a single
  `A972--` decrement (same as its sibling counter ids `7/8/6/5/C`, which really
  ARE single decrements - confirmed via `BDAC/BDB8/BDC4`).  Only `9` is the
  clear-loop.

Fix (`overkill/gameplay/object_deactivation.py`): special-case `logic_id 9` to
replay the `BD7A/BD82` clear loop (deactivate every `DS:A3B4` entry, drain
`DS:A972`) instead of a single decrement.  L1-L4 never hit it because ringlas is
the L5 weapon.

Verification:

```text
python -m pytest tests/test_overkill_hooks.py -q -k "b24d or b86d or aed8 or bd17"   # pass (AD60->BD17 oracle)
python scripts/find_demo_divergence.py <ringlas demo>   # frame-70 divergence gone; clean through the whole recorded demo
python -m pytest tests/test_demo_replay_equivalence.py -q -k ringlas   # passed (now a regression guard)
```

New tooling from the hunt: `scripts/capture_demo_snapshot.py` (capture an oracle
snapshot at any CS:IP during demo replay) and `scripts/find_demo_divergence.py`
(replay a demo native-vs-VM and stop at the first diverging frame/field).

Follow-up (separate, lower priority): ~1370 frames PAST the recorded demo's end
(post-input auto-play) a different divergence appears - a score delta and a
`logic_id 0x3B` effect-slot state difference.  Not the ringlas bug; logged as a
frontier.

## 2026-06-18 - Phase 2 collapse: native 9E19 in the B250 contact loop

Acted on a coverage telemetry dump from a full L2 demo run (94.9% hook-covered,
5.0% interpreted).  Investigated the hottest *gameplay* interpreted region,
`1010:B297-B32A` (145,662 hits, mislabelled "unknown"), via disassembly and found
it is two distinct things:

- `B281-B2A0` is the tail of the already-lifted `B250` overlap/contact selector -
  the `B297` loop that does `PUSH CX/BP; CALL 9E19; LOOP` (up to 5x).  But `9E19`
  was run as **interpreted** ASM via an injected near-call ("verifier-visible
  boundary"), even though a verified native helper
  `run_post_contact_status_helper_9e19` already exists.
- `B2CD` is a *separate* unhooked behavior (see the next note).

Phase-2 collapse: the selector now calls the native `9E19` helper instead of
interpreting it.  `run_overlap_contact_selector_b250` takes a
`post_contact_side_effect(cpu)` callable (was `near_call`); the `_run_b250_overlap_contact_selector`
shim binds it to `run_post_contact_status_helper_9e19` (with `_no_patch_guard`,
since 9E19 is static), pushing `B29C` so the helper's near-ret lands back in the
loop exactly like the original `CALL 9E19`.  The hot `B297` loop is now native.

This was safe to collapse precisely because the demo-replay proof spine exists:
per-hook 9E19 visibility is traded for whole-frame/state equivalence.

Verification:

```text
python -m pytest tests/test_overkill_hooks.py -q -k "aed8 or b24d or 9e19"   # 3 passed (vs interpreted ASM)
python scripts/audit_architecture.py / audit_hook_oracle.py                  # pass
python -m pytest tests/test_demo_replay_equivalence.py -q                    # 3 passed (L1/L2/L3 native == VM)
```

Re-run the user's `play.py --demo ... ` coverage command to see the `9E19`
interpreted hits drop.  (`61DC`/`511F` display children inside 9E19 stay bounded
for now.)

## 2026-06-18 - Structure: hook_boundary purity + source-port status dashboard

Whole-project structure pass (no behavior change).  Two parts:

1. Added `scripts/source_port_status.py` - a read-only dashboard of the ASM->source
   migration.  It reuses the enforced `audit_architecture.layer_of` map and reports
   per-layer line mass + `cpu`/`mem` density, the headline "% of game-logic mass
   that is pure source" (currently ~10%), the pure-rule count (44), registered hook
   count (336), and flags oversized hook_boundary files.  Wired into `ARCHITECTURE.md`
   as the "run this before deciding what to clean next" tool.

2. Started restoring `hook_boundary` purity: the documented rule is that
   `overkill/hooks.py` is thin `@registry.replace` glue with no render logic, but it
   held several large inline Tandy blits.  Moved `1010:477E` (9x16 sprite blit) and
   `1010:41DA` (linear row copy) bodies into `overkill/rendering/tandy.py` behind
   thin wrappers (the EGA renderer's existing pattern).  All the 8086 helpers those
   bodies need are already local to `tandy.py`, so the moves needed no new plumbing.

Effect: `hooks.py` 4244 -> 4117 lines; hook_boundary `cpu`/`mem` refs 913 -> 831.

Verification:

```text
python scripts/lint.py / audit_architecture.py / audit_hook_oracle.py   # all pass
python -m pytest tests/test_overkill_hooks.py -k "477e or 41da" -q      # 2 passed (byte-exact vs ASM)
python -m pytest tests/test_demo_replay_equivalence.py -q               # 3 passed (L1/L2/L3 native == VM)
```

Remaining inline blits in `hooks.py` to move next (same pattern): `497A`, `38B7`,
`3849`, `41A6`, plus `447B`/presence-stamp/dirty-cell presenter.  `497A` also uses
the `SF` flag and a couple of helpers - confirm they're available in `tandy.py`
before moving it.

## 2026-06-18 - State ownership: lift the 1010:8209 object-slot spawn template

First "vertical slice by state ownership" toward live source recreation.  Used the
world-write tracer over the L1 gameplay demo to find, per object/global field, the
exact set of routines that write it and which are already native hooks.  Result:
4 fields are already fully native-owned, and a single un-lifted routine -
`1010:8209` - was the lone remaining ASM writer for ~11 core object-record fields.

Lifted `1010:8209`, the shared object-slot spawn-stamp template (reached from the
`81E9`/`81F4` allocate-then-stamp siblings):

- Pure `recovered.systems.objects.object_spawn_seed_8209(source_x, source_y)` ->
  `ObjectSpawnSeed` (domain record): an active `logic_id=0014h` object at the
  caller's source X/Y, position+target both set to the source, with the constant
  fields (direction=4, hazard=4, scan=1, gate=1, counter_20=4, variant=0) and the
  unnamed `+0x28` field cleared to `FFFFh`.
- Hook `overkill_object_spawn_seed_8209` (`gameplay/object_spawns.py` +
  `hook_wrappers/object_runtime_frontiers.py`) owns the DOS slot pointer (BX) and
  write order, leaves `AX` = source Y, and near-returns; guarded by a byte
  signature like the other spawn templates.

Verification:

```text
python -m pytest tests/test_overkill_hooks.py::test_object_spawn_seed_8209_matches_interpreted_asm -q
# 1 passed (byte-exact vs interpreted ASM, full memory + state)

python scripts/audit_hook_oracle.py   # 336 hooks / 336 metadata
python scripts/audit_recovered_layers.py / lint.py   # 17 pure files / 145 files

python -m pytest tests/test_demo_replay_equivalence.py -q
# 3 passed (L1/L2/L3 native == VM with the 8209 hook live)
```

Confirmed live: the hook fired 16 times during the L1 wave with whole-game
equivalence holding, so the spawn template is genuinely running native source in
the live game, not a dead hook.  Those ~11 object fields now have their spawn-path
writer in native Python - measurable progress toward a native object model.

Method note (reusable): "live source" progress is now tracked by the world-write
tracer (`scripts/trace_world_writes.py`) - a field becomes recreated source once
every routine that writes it is a native hook.  Next ownership targets from the
same map: the `1F8F:038E..03A0` overlay spawn/init cluster (writes target_x/y,
logic_id, substate, a47e) and `1010:5033` (camera_or_view globals).

## 2026-06-18 - Demo corpus: L1 enemy-wave -> level-start transition

Added `demo_play_tandy_L1_start_20260618_143947` (sound=adlib, 140 events,
`end_boundary=870`): the level-1 enemy-wave intro playing through into the start
of the actual level phase.  Auto-discovered by `tests/test_demo_replay_equivalence.py`.

Equivalence holds across the whole transition: native (hooked) == VM oracle on
framebuffer + RGB + semantic state for all 870 frames (full run ~38s), and the
bounded CI prefix (150 frames) already covers the wave->level boundary at ~frame 138.

Transition evidence (candidate-runtime DS scan over the demo, step-function words
= state that changes once and settles): the enemy-wave is a consumed table in
roughly `DS:2404..24EC` (record stride ~18h, entries `0020h->0001h`/`0004h->0000h`
draining across frames 74..140); several globals settle at the wave->level
boundary near frame 138 (`DS:2308 0003h->0002h`, the `DS:2376/2378/2379` spawn
publish, `DS:240C`), with a later sub-event at frame 316 (`DS:230C/230E 0->1`).
These are candidate-only; none is yet a proven, named "level phase" global.

Two coverage gaps this demo exposes (the proof is not yet total here):
- The semantic `GameSnapshot` does **not** model wave/level-phase state, so for
  this transition the semantic half currently leans on the vram+RGB comparison.
  Widening it needs RE to interpret the step-words above into a named global.
- **Audio is not verified at all.**  The "different music" at the transition rides
  on the AdLib/OPL register stream, which the frame verifier does not compare; a
  music-only divergence would pass today unless it perturbs snapshot/vram state.
  This is the plan's known longest pole (exact audio == matching the OPL stream).

## 2026-06-18 - Proof spine: automated demo-replay native-vs-VM equivalence test

Stood up the plan's "deterministic demo-replay equivalence" harness as a standing
regression test (`tests/test_demo_replay_equivalence.py`).  This is the proof-spine
keystone: instead of only per-hook oracle checks, it continuously proves the *whole
live hooked game* still matches the original 8086 ASM over real gameplay.

How it works (reuses existing machinery, no new RE):

- For each recorded demo under `artifacts/demos/`, it loads the demo's start
  snapshot into two runtimes and replays the same inputs into both via
  `InputDemoPlayback.apply_to_runtimes`.
- `overkill.frame_verify.run_frame_verifier` makes the **reference** strip every
  replacement hook except the timer/retrace environment waits (so it interprets
  the original ASM) while the **candidate** keeps all native Python hooks.
- Each frame boundary it asserts the two runtimes are identical on the visible
  framebuffer, the rendered RGB pixels, *and* the decoded semantic `GameSnapshot`
  (objects/positions/flags/timers/score).  `source="both"` + `semantic_state_check`.

Scope/cost:

- Default: a bounded 150-frame prefix of each demo (`OVERKILL_DEMO_VERIFY_FRAMES`
  overrides), ~7s/demo.  L2 + L3 currently pass (`2 passed`).
- Opt-in full-length replay to each demo's recorded `end_boundary` via
  `OVERKILL_FULL_DEMO_VERIFY=1` (minutes/demo; use pytest, not the fail-safe runner).
- One zero-arg test is generated per demo so both pytest and
  `scripts/run_tests.py` discover and run them individually.

Verified as a real assertion: a negative-control run that injects an artificial
semantic divergence at frame 25 makes `run_frame_verifier` return non-zero and the
test fail, with a field-level divergence report.

Why this matters for the source port: this is the verification that must get
*stronger* as the VM gets weaker.  It lets Phase 2 (collapse understood hook
chains) proceed safely - we trade per-hook CS:IP granularity for whole-frame/state
equivalence over the demo corpus.  Next: grow the demo corpus (more levels,
bosses, spawn types, RNG paths) and, when addresses are known, widen the
`GameSnapshot` to RNG/lives/level-wave so the semantic half of the proof is total.

Validation:

```text
python -m pytest tests/test_demo_replay_equivalence.py -q
# 2 passed, 2 skipped (full-length opt-in)   ~15s

python scripts/run_tests.py tests/test_demo_replay_equivalence.py
# 4 passed (fail-safe runner; full tests early-return without OVERKILL_FULL_DEMO_VERIFY)
```

## 2026-06-18 - Phase 1 lift: B86D formation-spawn schedule + outgoing-sprite rules

Continued the DS:2340 formation-counter unification into `1010:B86D`.  Its common
path (reached past the B8F8 edge-steer and A7A0 guards) held two pure rules inline:

- `b86d_formation_spawn_tick_index(game_counter)` - the exact-tick formation-spawn
  schedule (`02EFh`/`0159h`/`0079h` -> variant 0/1/2, else no spawn).  This is the
  same DS:2340 global counter that B73E gates on, now a named source-level rule.
- `b86d_outgoing_sprite_for_delta(vertical_delta)` - outgoing sprite from the sign
  of the global vertical delta DS:2342 (`FFFFh` -> rising `0075h`, else falling
  `0076h`).

`_run_object_behavior_b86d` now calls both pure rules and asserts agreement,
keeping the chained CMP/JE order, the NEG/CMP, and the 7476 continuation
addresses (adapter glue) oracle-exact.

The lifted common path is exercised by the existing
`snapshot_stop_1010_b8b0_behavior` oracle (gc=`00CBh` non-trigger, delta=`0001h`
falling), so the change is covered by ASM equivalence, not just the pure unit test.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py -q -k b86d
# 2 passed (b8b0 snapshot drives the lifted 439-464 path vs interpreted ASM)

python -m pytest tests/test_recovered_semantics.py tests/test_architecture_layers.py -q
# 37 passed (adds the B86D common-path pure-rule test)

python scripts/audit_recovered_layers.py   # 17 pure files
python scripts/lint.py                      # 145 files
python scripts/audit_hook_oracle.py         # 335 hooks / 335 metadata
```

Pre-existing/unrelated: two `bfc7` oracle tests error on a missing artifact
(`artifacts/snapshot_play_tandy_20260614_191454`), an environment gap, not a
behavior regression.

DS:2340 unification status: B73E (band gate) and B86D (exact-tick schedule) now
both express their formation-counter decisions as pure named rules.  The
remaining DS:2340 consumer is `B9F0`, still blocked on having no oracle test.

## 2026-06-18 - Phase 1 lift: B73E idle-phase rules become pure systems

Continued the Phase 1 sweep into `1010:B73E`, the substate/idle object behavior.
Two genuinely-pure gameplay rules were tangled inline among the CPU arithmetic on
the no-substate (`FFFFh`) idle path; both are now named pure functions while B73E
keeps its oracle-exact flags.

Implemented:

- `overkill/recovered/systems/objects.py`:
  - `b73e_idle_sprite_frame(timer, y)` - the DS:2338 timer -> animation-frame
    formula (high objects above the `0060h` Y line count down from `007Fh`, low
    objects count up from `007Ah`), with named constants.
  - `b73e_reaches_b808(game_counter)` - the DS:2340 spawn-window gate: inside the
    `[02BCh, 02D0h]` band the B800 formation spawn-pointer advance runs, otherwise
    control reaches B808 and skips it.
- `overkill/gameplay/object_behaviors.py`: `_run_object_behavior_b73e` now calls
  both pure rules and asserts agreement, keeping the inline NEG/ADD and the
  two-step compare order so 8086 flags still match the oracle.

Unification: B73E's `B82D` waypoint loop re-implemented the exact same
`[02BCh, 02D0h]` spawn-window band check as the non-loop path.  That duplicate is
now routed through the single shared `b73e_reaches_b808`, so the one gameplay rule
has one source-of-truth (the existing `b73e` B82D-loop oracle test covers it).

The substate jump table at CS:B74E (the `B754`/`B770`/`B77B` arm dispatch) is
deliberately left inline; it is CS-data-table-driven and belongs to the Phase 3
data-decode pass, not a pure-rule lift.

Frontier note: `1010:B9F0` gates formation spawns on the same DS:2340 counter but
with exact-tick triggers (`02EFh`/`0159h`/`0079h`).  Unifying that into a pure
formation-spawn-schedule rule is the natural next step, but B9F0 has **no oracle
test yet**, so its logic must not be refactored until a B9F0 ASM-equivalence
snapshot/test exists (build that first, then lift).

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 31 passed (adds the B73E idle-phase pure-rule test)

python -m pytest tests/test_overkill_hooks.py -q -k b73e
# 6 passed (full-state + full-memory equivalence vs interpreted ASM)

python -m pytest tests/test_architecture_layers.py -q
# 5 passed
python scripts/audit_recovered_layers.py   # 17 pure files
python scripts/lint.py                      # 145 files
python scripts/audit_hook_oracle.py         # 335 hooks / 335 metadata
```

Note: the original binary lives at `overkill/assets/` in this tree; the tests and
AGENTS.md expect the repo-root `assets/`.  A copy now exists at `assets/`
(gitignored) so the oracle suite resolves `assets/OVERKILL`.

## 2026-06-18 - Phase 1 lift: AD60 bounds/tile branch decision becomes a pure system

Continued the Phase 1 live-hook -> (thin adapter + pure recovered rule) sweep on a
dense gameplay decision.  The shared `1010:AD60` bounds/tile tail
(`_run_object_bounds_tile_tail_ad60`, used by every object behavior that reaches
the postmove bounds check via AD5A/ADC9) had its gameplay rule inlined among the
CPU side effects: the off-screen deactivation predicate and the tile-probe
eligibility gate.

Implemented:

- `overkill/recovered/domain/object_behaviors.py`: added `ObjectBoundsTileDecision`
  (`deactivate` / `skip` / `tile_probe`).
- `overkill/recovered/systems/objects.py`: added the pure
  `object_bounds_tile_decision_ad60(x, y, draw_layer, logic_id, tile_probe_suppressed)`
  plus the recovered constants `OBJECT_BOUNDS_MIN_X=0008h`, `OBJECT_BOUNDS_MAX_X=00E0h`,
  `OBJECT_BOUNDS_MAX_Y=00C8h`, `OBJECT_BOUNDS_TILE_PROBE_DRAW_LAYER=0002h`, and the
  probing `OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS` set.
- `overkill/gameplay/object_bounds.py`: `_run_object_bounds_tile_tail_ad60` now
  computes the pure decision up front and replays the exact CMP order, asserting
  the pure decision agrees at every deactivate/skip/tile-probe boundary.  The
  BD17 deactivate side effect, the 5073/505B tile probe, and the ADC1 sub-deactivate
  are unchanged.

The branch decision is now native: AD60's "left the play-field box -> deactivate"
and "in-bounds probing family -> run tile probe" rules live in a pure function
with no CPU/memory dependency, while the adapter keeps oracle-exact 8086 flags.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 30 passed (adds the AD60 pure decision + adapter-agreement tests)

python -m pytest tests/test_architecture_layers.py -q
# 5 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 17 pure files
python scripts/lint.py
# Lint passed for 145 Python files
python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 335 registered hooks, 335 metadata entries
```

The AD60-reaching oracle tests confirm zero behavioral change against
interpreted original ASM:

```text
python -m pytest tests/test_overkill_hooks.py -q \
  -k "object_behavior or bounds or ad60 or ad5a or deactivate"
# 9 passed

python scripts/play.py --snapshot artifacts/evidence/snapshot_stop_1010_aed8_b250_overlap \
  --video tandy --sound adlib --verify-hook 1010:AED8 --verify-max 1 \
  --verify-step-budget 200000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1   (full-memory + full-state differential)
```

Next Phase 1 candidate: keep sweeping the inline branch decisions in
`object_bounds`/`object_behaviors` postmove tails (e.g. the per-`logic_id` motion
selectors in `_run_object_behavior_b73e`) into pure recovered predicates.

## 2026-06-17 - High-level action layer extraction and sound-driver unification

Performed a structural cleanup pass after the hook-registry split.  The goal was not to lift a new gameplay routine, but to make the emerging source-like gameplay layer more visible and to remove one confusing coverage convention around sound addresses.

Implemented:

- Added `overkill/gameplay/action_spawns.py` and moved the `A067` action-spawn family out of `frame_orchestration.py`.
- `frame_orchestration.py` is now back to frame/controller concerns, while `action_spawns.py` owns the raw `A067/A0E8` action fanout, `A515/A584`, `A3CA/A3FF`, and `A2A0/A2F6/A337` children.
- Added small source-like structures around already-proven behavior:
  - `ActionCounterSnapshot` for the `A970/A972/A976/A974 -> A3A0/A3A2/A3A4/A3A6` counter publish step.
  - `PairSpawnTailPlan` for the duplicated `A2F6/A337` two-slot spawn tail shape.
  - `action_trigger_is_pressed(...)` and `action_latch_allows_repeat(...)` for the raw `98BE & 10h` and `A980/9790/232A` gates.
- Added `overkill/sounds/loaded_driver.py` as the single source of truth for the loaded optional sound-driver segment `2032h`.
- Updated coverage classification, verifier stops, sound wrappers, the static runtime bundle, and sound-driver helpers to use `OPTIONAL_SOUND_DRIVER_SEGMENT` instead of repeating literal `2032h`.
- Updated `scripts/audit_hook_oracle.py` so the static hook audit understands named integer constants in decorators and `HookStop` metadata.

The important sound clarification: the many unhooked calls classified as `sound` share a real unifying element.  They are in the loaded optional AdLib/Roland driver segment `2032:*`, not arbitrary gameplay routines that happen to be near sound code.  The currently lifted driver entrypoints remain explicit in `OPTIONAL_SOUND_DRIVER_HOOK_ADDRS`, while the whole segment stays classified as the `sound` island for coverage purposes.

No new high-level entity semantics were introduced.  In particular, `A067` remains a proven action/object-spawn fanout, not yet a named weapon or player-shooting model.

Validation:

```text
python scripts/lint.py
# Lint passed for 124 Python files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 335 registered hooks, 335 metadata entries

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python -m pytest tests/test_recovered_semantics.py -q
# 25 passed

python -m pytest focused action/frame-controller tests -q
# 5 passed

python -m pytest focused sound-driver tests -q
# 4 passed
```

Next cleanup direction: continue extracting source-like gameplay clusters from the frame/controller layer only when they are already proven at ASM boundaries.  The remaining action-spawn unknown with the highest semantic value is still the out-of-range `44AF` tail observed behind `A958`.

## 2026-06-17 - A2A0/A2F6/A337 action-spawn table tails

Continued the gameplay-logic understanding pass behind `A067/A0E8`.  After `A3CA/A3FF`, the highest-value remaining in-range action fanout was the `A2xx` cluster selected by `DS:A958`: the pre-table `A2A0` path when `A958 == 5`, plus the table tails `A2F6` (`A958 == 4`) and `A337` (`A958 == 3`).

Implemented:

- `1010:A2A0 overkill_frame_action_listed_anchor_spawn_a2a0` as a standalone hook.
- `1010:A2F6 overkill_frame_action_pair_spawn_a2f6` as a standalone hook.
- `1010:A337 overkill_frame_action_pair_spawn_a337` as a standalone hook.
- Local lifted bodies for the shared `A2D6` spawn/list/projection body, `A294` list append, and `A1AE` BP-relative coordinate projection.
- Updated hook metadata, frontier notes, symbols, runtime findings, and island truth-table notes.

Recovered structure:

```text
A2A0:
  gate: A3A2 == 0
  if 98C0 != 0: BEFF = 11
  ES = CS:9596
  A3EA = A3B4
  clear 1Ah words at ES:A3B4 to FFFF
  call A2D6
  stamp first slot +8 = 006A
  subtract 8 from first slot Y
  fall through into A2D6 again

A2D6 body:
  A972++
  call A4EA
  call A294       ; append BX to the A3EA list
  stamp +18 = 9
  call A1AE       ; BP+8 coordinate source + BP+2/BP+4 offsets
  align/offset Y with AND FFF8, +8
  stamp +8 = 006C

A2F6:
  gate: A3A0 == 0
  if 98C0 != 0: BEFF = 17
  allocate/project two slots through A4EA/A1AE
  stamp both +18 = 8, +8 = 35
  add 8 to the second slot X

A337:
  gate: A3A0 == 0
  if 98C0 != 0: BEFF = 16
  allocate/project two slots through A4EA/A1AE
  stamp both +18 = 7, +8 = 37
  add 8 to the second slot X
```

The important quirk in `A2A0` is the same kind of call/fallthrough shape seen in `A3FF/A378`: one local `CALL A2D6`, then first-slot postprocessing at `A2CD`, then fallthrough into `A2D6` again.  So this path deliberately creates two slot actions, not one.

Semantic interpretation remains structural.  These are proven raw action-spawn table tails behind `A067`, with counters (`A970/A972`), `BEFF` event/status bytes, raw slot fields, and the `A3B4`/`A3EA` list.  They are not yet promoted to a named weapon, projectile, player, enemy, or pickup semantic.  The remaining major `A067` action-spawn frontier is now the real out-of-range `A958` target `44AF` observed when `A958 == 5` after the pre-call `A2A0`.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_frame_action_a2xx_spawn_tails_match_interpreted_paths -q
# 1 passed

python -m pytest \
  tests/test_overkill_hooks.py::test_frame_action_a2xx_spawn_tails_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_anchor_dispatch_children_a3ca_a3ff_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_post_contact_status_helper_9e19_matches_interpreted_paths \
  tests/test_recovered_semantics.py -q
# 30 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 335 registered hooks, 335 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:A067 \
  --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1
```

A direct headless `--verify-hook 1010:A2A0` from the bundled gameplay snapshot did not naturally reach the new A2xx child before the existing unrelated text-input DOS read blocked at `5497`; the proof added here is the focused ASM-vs-hook oracle test plus successful parent `A067` verifier coverage.

Next highest-value boundary is `44AF`, because the in-range `A067/A0E8` action-spawn children are now lifted and `44AF` is the remaining table tail that can still hide a larger action variant.

## 2026-06-17 - A3CA/A3FF action-side anchor dispatch hooks

Continued the gameplay-logic understanding pass behind the `A067` action/object-spawn fanout.  The best next boundary was the `A3CA`/`A3FF` pair because both are direct `A067` children, both share the same local `A41A` dispatch body, and together they explain most of the remaining side/mirrored raw slot-spawn behavior before the still-larger `A2A0` path.

Implemented:

- `1010:A3CA overkill_frame_action_side_anchor_spawn_a3ca` as a standalone hook.
- `1010:A3FF overkill_frame_action_mirrored_anchor_spawn_a3ff` as a standalone hook.
- A lifted local `A41A` body used by both hooks.  It dispatches `DS:A958` through the raw `CS:A42C` table: `A4D7`, `A490`, `A499`, `A464`, `A438`.
- A lifted local `A378` follow-up used by `A3FF`.  Important recovered quirk: the open path creates two slots, because the original code `CALL`s `A396`, stamps the first slot's `+18` field to `6`, and then falls through into `A396` a second time.
- Updated `symbols.json`, frontier notes, runtime findings, and island truth-table notes.

Recovered structure:

```text
A3CA:
  A3EC = 7; SI = [A966]; call A41A
  A3EC = 1; SI = [A968]; call A41A
  A3EC = 7; SI = [A96A]; call A41A
  A3EC = 1; SI = [A96C]; call A41A

A3FF:
  A3EC = FFFF
  SI = [A962]; call A41A; call A378
  SI = [A964]; call A41A; call A378

A41A table selected by A958:
  0 -> A4D7 coordinate-copy spawn
  1 -> A490 A4D7 + +8=0033
  2 -> A499 A3EC/direction-stamped spawn
  3 -> A464 gated two-spawn pair, +18=7/+8=37
  4 -> A438 gated two-spawn pair, +18=8/+8=35
```

Semantic interpretation stays deliberately structural.  `A3CA`/`A3FF` look like side/mirrored action-spawn helpers, but they are not yet promoted to a named weapon, projectile, enemy, pickup, or player semantic.  The evidence is raw source pointers, `A3EC` stamps, `A958` table targets, `A970/A976` counters, `BEFF=12` on the `A378/A396` path when `98C0 != 0`, and raw slot fields.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_frame_action_anchor_dispatch_children_a3ca_a3ff_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_post_contact_status_helper_9e19_matches_interpreted_paths \
  tests/test_recovered_semantics.py -q
# 29 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 332 registered hooks, 332 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

A direct headless `--verify-hook 1010:A3CA` from the currently bundled gameplay snapshot did not naturally reach the new hook before an unrelated text-input DOS read blocked, so the proof added here is the focused ASM-vs-hook oracle test plus metadata/audit coverage.  A full repository `pytest -q -x` still stops at the existing coverage-classifier expectation in `tests/test_core.py::test_coverage_summary_reports_grouped_bounded_original_regions` (`input_menu` expected for a synthetic `9B2E` bounded region), which is unrelated to this hook work.

Next highest-value boundary is now `A2A0` behind the `A067/A0E8` action fanout, plus any real out-of-range `A958` table targets observed in traces.

## 2026-06-17 - 9E19 shared post-contact/status helper hook

Continued the gameplay-logic understanding pass from the `9CB6` contact fanout and the `B24D` overlap branch.  The best next boundary was `1010:9E19`, because it is shared by both paths and owns the raw contact/status counters that were still opaque after `9CB6`.

Implemented:

- `1010:9E19 overkill_post_contact_status_helper_9e19` as a standalone hook.
- Kept `9CB6` as a pure fanout parent: it now composes a verifier-visible `9E19` child instead of a bounded-original helper.
- Updated the `B24D` overlap behavior comments/metadata so its `PUSH CX; PUSH BP; CALL 9E19; POP BP; POP CX` loop remains a parent contract around a separate child hook.
- Updated symbols/frontier metadata and runtime findings.

Recovered structure:

```text
guards:
  if A47C == 1      -> RET
  if DS:2384 >= 3   -> RET
  if A95A == FFFF   -> RET

contact-status path:
  DS:23A0 = 8
  if 98C0 != 0: BEFF = 0F
  decrement A95C by:
    BEDC == 0     -> 1 step
    BEDC == 1     -> up to 2 steps
    BEDC other    -> up to 3 steps
  if A95C remains non-zero:
    call 61DC
    if CS:95BC == 1: call 511F, 61DC, 511F
    RET

A95C refill path:
  A95C = 18
  repeat A47C/2384 guards
  if 98C0 != 0: BEFF = 03
  if BEDC == 0:
    A362 = (A362 + 1) & 1
    if A362 != 0: RET
  decrement A95A
  if A95A != FFFF:
    display as above
    RET

A95A expiry path:
  A95C = 0
  if byte 9791 == 1:
    A95A = 3
    A95C = 18
    RET
  DS:2384 = 3
  if 98C0 != 0: BEFF = 19
  display as above
  RET
```

Semantic interpretation remains narrow: `9E19` is a shared raw post-contact/status counter helper.  It looks very damage/hit/cooldown-adjacent because of `A95A/A95C`, `2384`, `A362`, `23A0`, and `BEFF`, but the hook deliberately does not yet rename those fields as health/lives/invulnerability without more cross-routine evidence.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_post_contact_status_helper_9e19_matches_interpreted_paths -q
# 1 passed

python -m pytest tests/test_overkill_hooks.py::test_post_contact_status_helper_9e19_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_contact_probe_fanout_9cb6_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths \
  tests/test_recovered_semantics.py -q
# 28 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:9E19 \
  --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:9CB6 \
  --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 332 registered hooks, 332 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

Next highest-value boundary after `9E19` was the `A3CA`/`A3FF` pair behind the `A067`/`A0E8` action fanout; the follow-up section above records that lift.

## 2026-06-17 - B15A shared candidate-scan hook

Continued the gameplay-logic understanding pass from the `A067`/`A515` action-spawn frontier.  The best next boundary was `1010:B15A`, because it is shared by the already lifted `B1B0` chase-acquisition behavior and by the new `A515` anchored spawn/link helper.

Implemented:

- `1010:B15A overkill_player_chase_candidate_scan_b15a` as a standalone hook.
- Kept the source-like candidate predicate in `overkill.recovered.systems.objects` and the exact cursor/register/flag behavior in the lifted gameplay layer.
- Updated `B1B0` so its `CALL B15A` goes through the real hook boundary via verifier-visible near-call semantics instead of calling the internal helper directly.
- Updated symbols/frontier metadata and runtime findings.

Recovered structure:

```text
CX = 0023h
BX = DS:A43A
if BX >= 2B5Ch: DS:A43A = 23B4h; restart without consuming CX
scan DS:23B4..2B5C in 38h-byte slots
candidate iff:
  active_word != 0
  logic_id not in {0001h, 0026h, 0021h, 0022h}
  x <= 00E0h
  hazard_class == 0004h
success -> DS:A43A = found_bx + 38h, BX = found_bx
failure after 23h slots -> BX = FFFFh
```

Semantic interpretation remains narrow: this is a shared rotating effect/contact-slot candidate scan.  It should not yet be treated as a global enemy/projectile/pickup classifier.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_player_chase_candidate_scan_b15a_matches_interpreted_paths -q
# 1 passed

python -m pytest tests/test_recovered_semantics.py   tests/test_overkill_hooks.py::test_player_chase_candidate_scan_b15a_matches_interpreted_paths   tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths   tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths -q
# 28 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 329 registered hooks, 329 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

A direct headless `--verify-hook 1010:B15A` from the currently bundled gameplay snapshots did not naturally reach `B15A` before unrelated input/menu blocking or timeout, so the proof added here is the focused ASM-vs-hook oracle test plus the verifier-visible child boundary from `B1B0`/`A515` composition.

Next highest-value boundaries remain `A3FF`, `A3CA`, and `A2A0` behind the `A067` action fanout, plus `9E19` behind the `9CB6` contact fanout.

## 2026-06-17 - A515/A584 A067 child spawn-frontier split

Continued the gameplay-logic understanding pass from the lifted `A067` action/object-spawn fanout.  Instead of adding a speculative high-level weapon/player model, this pass split two concrete child frontiers that `A067` had isolated: `1010:A515` and `1010:A584`.

Implemented:

- `1010:A515 overkill_frame_action_linked_anchor_spawn_a515`:
  - gates on raw counters `DS:A960` and `DS:A97E`;
  - allocates one destination slot through `7547`;
  - anchors destination coordinates from the current `SS:BP` slot through `A571`;
  - temporarily switches `BP=BX` and calls the still-separate `B15A` child;
  - if `B15A` returns `BX != FFFF`, stamps the destination slot fields, stores the returned word at `BX+30`, optionally writes `BEFF=11`, increments `A97E`, and decrements `A960`.
- `1010:A584 overkill_frame_action_dual_anchor_spawn_a584`:
  - gates on raw `DS:A95E` and copied counter `DS:A3A4`;
  - increments `A976` before each allocation;
  - creates two destination slots through `A4EA` + `A571`;
  - aligns each spawned slot's Y field with `AND [BX+4], FFFC`;
  - stamps `BX+8 = 8` and `BX+18 = 5/6`.

Semantic interpretation remains deliberately structural.  These are now proven as `A067` child spawn/slot side-effect helpers, but they are not yet named as player weapon, enemy, projectile, or pickup logic.  `B15A`, `A3FF`, `A3CA`, and `A2A0` remain the best next child frontiers behind this action fanout.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths -q
# 1 passed

python -m pytest \
  tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths -q
# 3 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:A067 \
  --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 328 registered hooks, 328 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

Direct headless verification of `A515`/`A584` from the available gameplay snapshot did not naturally hit those routines before unrelated menu/input blocking, so the proof added here is a focused ASM-vs-hook oracle test with explicit child boundaries plus parent `A067` verifier coverage.

## 2026-06-17 - A067 frame action/object-spawn fanout hook

Split the highest-value frontier left under the lifted `1010:9B2E` frame
controller.  The new `1010:A067 overkill_frame_action_spawn_fanout_a067` hook
covers the input-bit-gated action/object-spawn fanout that is also reached from
`1010:D04D`.

Observed structure:

- `DS:98BE & 10h` is the outer gate.  When clear, the routine tails through
  `A060`, clears `DS:A980`, and returns.
- `DS:A980` is a one-shot/repeat latch.  Re-entry is blocked unless `DS:9790`
  equals `1` or `DS:232A` equals `0x000F`.
- Entering the action path sets `DS:A980 = 1`.
- High-view paths copy `A970/A972/A974/A976` into `A3A0/A3A2/A3A6/A3A4` before
  dispatch.
- Low-view `BDAC == 0` paths jump directly to the `A958` action tails:
  `A958 == 2` uses the double-spawn `A1C8` tail; other tested values use
  `A19F`.
- The high-view main path composes bounded child frontiers `A515`, `A584`,
  `A3FF`, `A3CA`, and the `A0E8` sub-dispatch.
- `A0E8` optionally calls `A2A0`, optionally calls the `A114` three-spawn
  helper when `A96E != FFFF`, then jumps through the `A958` table.
- Proven in-hook tails are `A114`, `A175`, `A18A`, `A19F`, `A1AB/A1AE`, and
  `A1C8`.  Out-of-range `A958` table entries still tail-jump to bounded
  original code rather than being guessed.

Validation:

```text
python -m pytest   tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths   tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths   tests/test_overkill_hooks.py::test_frame_contact_probe_fanout_9cb6_matches_interpreted_paths -q
# 3 passed

SDL_VIDEODRIVER=dummy python scripts/play.py   --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042   --video tandy --sound pc --verify-hook 1010:A067   --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 326 registered hooks, 326 metadata entries
python scripts/audit_recovered_layers.py
# passed
python scripts/lint.py
# passed
```

Important correction found during the lift: calls to `A1AE` inside the `A1C8`
tail intentionally skip the `A1AB` allocation call because the caller already
called `A4EA`.  Treating `A1AE` as if it were `A1AB` doubles the spawned-slot
count and leaves `BX`/stack scratch different from ASM.

Next high-value work is now either the remaining larger children behind this
fanout (`A515/A584/A3FF/A3CA/A2A0`) or the post-contact/status helper `9E19`.
`A067` should still be described as raw action/object-spawn glue, not as a named
weapon/player semantic.

## 2026-06-17 - 9CB6 contact-probe fanout hook

Split the next high-value child frontier exposed by `9B2E`.  The new
`1010:9CB6 overkill_frame_contact_probe_fanout_9cb6` hook is a narrow
frame/collision fanout primitive: it calls the already recovered `4FF9`
tile/contact probe, returns immediately when carry is clear, and on carry-set
preserves `BP` while calling the still-bounded `9E19` post-contact/status helper
according to raw `DS:BEDC`.

Recovered fanout shape:

```text
4FF9 CF clear -> RET
4FF9 CF set, BEDC == 0     -> 9E19, 9E19
4FF9 CF set, BEDC == 1     -> 9E19, 9E19, 9E19
4FF9 CF set, BEDC other    -> 9E19, 9E19, 9E19, 9E19
```

This deliberately does not classify the contact as player/enemy/projectile
semantics.  It only proves that `9CB6` is the frame-controller contact side
effect fanout around the lower tile/contact sampler and the still-separate
`9E19` status/counter helper.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths \
  tests/test_overkill_hooks.py::test_frame_contact_probe_fanout_9cb6_matches_interpreted_paths -q
# 2 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:9CB6 \
  --verify-max 1 --verify-step-budget 200000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1

python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_frame_contact_probe_fanout_9cb6_matches_interpreted_paths -q
# 26 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 325 registered hooks, 325 metadata entries, no direct registered child calls detected.

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/lint.py
# Lint passed for 119 Python files
```

Next best frontier is now `A067/A060-A211`, because `9CB6` is no longer a black
box and its remaining unknown child is specifically the bounded `9E19` helper.

## 2026-06-17 - 9B2E frame-controller parent hook

Promoted the next large game-logic frontier from bounded original to a
verifier-visible parent hook without introducing semantic player/enemy names.
The new `1010:9B2E overkill_frame_controller_9b2e` hook composes the existing
children in original order: input poll, `BP=237C` current object/script slot,
direct movement bits, `A66F`, the still-separate `A067` action/helper frontier,
optional `9D4D`, `A616`, `9CB6`, `9C01`, coordinate-ring maintenance, and
`9FAF` linked child-coordinate propagation.

Important recovered fact:

- The backwards branch target `9AFF` is not simply an early return.  Its two
  `JZ +1` instructions mean "skip the RET and continue".  The tail only reaches
  `4DBF` when `DS:2326 == 3` and the incremented `SS:[BP+8] == 0Fh`; then it
  clears `SS:[BP+0]`, sets `DS:A346`, and sets `DS:A342` only when `DS:A97A` is
  zero.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_frame_controller_9b2e_matches_interpreted_parent_paths \
  tests/test_overkill_hooks.py::test_frame_axis_condition_dispatch_9c01_hook_matches_composed_interpreted_snapshot \
  tests/test_recovered_semantics.py -q
# 27 passed

python scripts/lint.py
# Lint passed for 119 Python files

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 324 registered hooks, 324 metadata entries, no direct registered child calls detected.

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 \
  --video tandy --sound pc --verify-hook 1010:9B2E \
  --verify-max 1 --verify-step-budget 200000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1
```

Next best game-logic frontiers are now smaller and clearer: split `A067/A060-A211`
from direct replay evidence, then split `9CB6/9CBC` instead of treating `9B2E`
as the remaining monolith.

## 2026-06-17 - A5xx/A6xx movement and edge-scroll crystallisation

Continued the game-logic refactor in the recovered source-port direction.  This
pass deliberately avoided new high-level entity names: it promoted only the
source-level value decisions behind already verified low-level movement helpers.

Implemented:

- Added pure movement-domain records for axis-clamp and vertical edge-scroll
  results.
- Promoted the final value logic behind `1010:A5D1`, `A5EA`, `A5F9`, and `A607`
  into `overkill.recovered.systems.movement.two_pass_axis_clamp_step` and
  `one_pixel_axis_step`.
- Promoted the final `DS:A39A/A39C` edge-scroll bias logic behind `1010:A616`,
  `A648`, `A63C`, and `A662` into pure recovered movement helpers.
- Kept the lifted hook path responsible for all ASM-visible behavior: CMP/TEST
  order, INC/DEC flags, CALL-next stack scratch, nested return words, and near
  RET continuation behavior.  The hook path now asserts that its replay agrees
  with the pure system result.
- Added a source-port-safe recovered semantics test for the new pure helpers and
  updated recovered-layer/runtime/island documentation.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 25 passed

python -m pytest \
  tests/test_recovered_semantics.py::test_recovered_axis_clamp_and_vertical_scroll_bias_are_pure_source_port_helpers \
  tests/test_overkill_hooks.py::test_object_two_pass_clamp_step_helpers_match_original \
  tests/test_overkill_hooks.py::test_object_vertical_scroll_edge_helpers_match_original -q
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*vertical_scroll*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*clamp_step*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/lint.py
# Lint passed for 119 Python files
```

Next best crystallisation candidates:

- `9B2E` has now been lifted as a parent; continue with `A067/A060-A211` or
  `9CB6/9CBC` using focused oracle tests, not input-name guesses;
- look for duplicated value decisions in the `B00D` directional tile-response
  path and promote only the pure sampling/plan layer;
- keep `A067`/`A060-A211` bounded until a direct replay snapshot proves the
  exact UI/frame-state side effects.

## 2026-06-16 - Status parent and 9C01 child absorption

Continued from the bounded-original frontier triage by converting two named
frontiers into verifier-visible hooks instead of only classifying their bytes.
The work stayed in the verified lifted-routine layer: no semantic HUD or
movement model was introduced.

Implemented:

- `1010:61DC overkill_status_display_parent_61dc`:
  - clears the six `SS:2368..2372` status/counter words with a local
    `REP STOSW` mirror;
  - runs the existing `61F7/61C7` countdown scan while `DS:A95C` is positive;
  - draws the six counter cells through the existing `6296` child;
  - optionally draws the two trailing marker cells through `5A00`/`5A6C`;
  - preserves the original near-call/dispatch stack shape for all child calls.
- `1010:9C01 overkill_frame_axis_condition_dispatch_9c01`:
  - lifts the child frontier inside the larger bounded `9B2E` frame controller;
  - combines the `DS:98BE` input bits, `A39E/A39F` edge markers, and the
    `A966/A968/A96A/A96C` delayed coordinate-slot counters;
  - preserves the small jump-table dispatch to direct `RET`, `9C82/9C9C`
    guarded tails, and one-pass `A60A`/`A5FC` Y-step bodies.
- Updated hook metadata, `symbols.json`, frontier classification, and coverage
  ownership so `61DC` and `9C01` are no longer only bounded-original frontiers.
- Updated older leaf tests for `61C7`, `61F7`, and `6296` to explicitly expose
  those child boundaries now that `61DC` absorbs them by default.

Validation:

```text
python scripts/run_tests.py tests/test_overkill_hooks.py --name '*61dc*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*9c01*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*97b2*' --timeout 100 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*61c7*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*61f7*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*6296*' --timeout 100 --fail-fast --no-lint --verbose
# 1 passed

python -m pytest tests/test_core.py::test_coverage_classifier_marks_known_bounded_frontier_ranges -q
# 1 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 316 registered hooks, 316 metadata entries,
# no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unknown island hooks: 0

python scripts/lint.py
# Lint passed for 81 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

A 100-step coverage probe from `artifacts/evidence/hook_verify_tandy_20260613_190326`
now reports:

```text
ASM interpreted instructions: 1
Bounded original ASM instructions: 5,436
Unknown / unmeasured hook calls: 1
unknown bounded count 0
unknown interpreted count 0
```

The remaining bounded-original hotspot is now more concentrated around the parent
`1010:9B2E-9BFA` frame controller, with `9C01` removed from that frontier.  The
next useful absorption targets are `A067`/`A060-A06C`, `9CB6-9CBB`, and the
collision tails (`BE3C`, `AAC2`, `8331`) that are still visible as bounded
regions.

## 2026-06-16 - Bounded-original coverage frontier triage

Continued the unknown-instruction cleanup from the uploaded `overkill_port(23)`
snapshot.  The important distinction in this pass is that no gameplay behavior
was replaced: the changes are diagnostic/classification work that makes the
remaining bounded-original ASM visible by semantic island instead of hiding it in
`unknown`.

Implemented:

- Added grouped bounded-original regions to `CoverageTelemetry.format_summary()`.
  The dashboard now reports both per-instruction and nearby-region views for
  `BOUNDED_ORIGINAL`, matching the existing interpreted-ASM region view.  This
  makes parent wrappers such as `9B2E` and rare child tails easier to absorb
  safely because the next frontier is shown as a range, not only as scattered
  IPs.
- Added conservative classifier ranges for already-triaged bounded frontiers:
  - `1010:9B2E-9CBB` input/menu frame-controller child and contact-probe wrapper;
  - `1010:A060-A211` game-state/UI object helper reached from `A067`;
  - `1010:BE3C-BEB6`, `1010:AAC2-AAFB`, `1010:8331-835A`, and
    `1010:AA44-AA70` collision/contact tails;
  - `1010:BD17-BD65`, `1010:C054-C15B`, `1010:8D4F-8D8D`, and
    `1F8F:027A-0451` gameplay-object tails/scripts;
  - `1010:61DC-6295` rare status-display parent reached from object/status
    tails;
  - `1010:5F0D-5F42`, `1010:9D67-9EF2`, and `1010:981D` status/frame-state
    tails;
  - `1010:77DF-77F5` bounded layer/effect wrapper;
  - the tiny `1010:AB0C-AB0D` jump-table tail back into `BD17`.
- Added focused coverage tests proving the new bounded-original region report and
  the known frontier range ownership.  Exact address classifications still win
  before these broad diagnostic ranges, so existing hook/island ownership is not
  weakened.

Validation:

```text
python -m pytest \
  tests/test_core.py::test_coverage_telemetry_counts_interpreted_and_verified_hooks \
  tests/test_core.py::test_coverage_summary_reports_grouped_interpreted_regions \
  tests/test_core.py::test_coverage_summary_reports_grouped_bounded_original_regions \
  tests/test_core.py::test_coverage_classifier_marks_transient_bootstrap_segment \
  tests/test_core.py::test_coverage_classifier_marks_known_bounded_frontier_ranges \
  tests/test_core.py::test_all_registered_overkill_hooks_have_non_unknown_island_classification -q
# 6 passed in 0.93s

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 314 registered hooks, 314 metadata entries,
# no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unknown island hooks: 0

python scripts/lint.py
# Lint passed for 81 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

A 100-step probe from `artifacts/evidence/hook_verify_tandy_20260613_190326`
with coverage telemetry attached now reports:

```text
ASM interpreted instructions: 1
Bounded original ASM instructions: 5,492
Unknown / unmeasured hook calls: 0
unknown bounded count 0
unknown interpreted count 0
```

The one remaining interpreted instruction in that probe is `1010:981D`, now
classified as `game_state`; it is the final frame-loop jump tail after `97B2`,
not a new unknown island.

I also tried the full `scripts/run_tests.py --no-lint --scope all --timeout 20
--fail-fast` runner in this sandbox, but it did not complete before the sandbox
command timeout.  The focused coverage tests, hook-oracle audit, island audit,
lint, and DOS-RE smoke scope all passed.

Next absorption targets are now cleaner:

- lift or further wrap the `1010:9B2E` bounded frame-controller child instead of
  chasing scattered unknown IPs;
- decide whether `1010:61DC` should be lifted as a full status-display parent or
  split into its display/data-table children;
- add missing oracle tests for already-registered but no-test hooks in the open
  `layer_sprites`, `movement`, `collision`, `input_menu`, and `sound` islands;
- only then convert more bounded-original leaves into real hooks.

## 2026-06-15 - Deep hook-oracle blind-spot cleanup: CALL and JMP child boundaries

Continued the verifier-hardening pass after the AA71 false-contact bug.  The
previous audit guaranteed that address wrappers in `overkill/hooks.py` were not
calling registered child hooks through the old raw near-call helper, but it still
missed two important classes:

- registered child hooks called directly from other OVERKILL modules;
- original `JMP`/fall-through child transfers, where no synthetic return word
  should be pushed but the child boundary still needs verifier visibility.

Implemented:

- `dos_re.hooks.jump_installed_hook_boundary()`
  - sibling of `call_installed_hook_like_near_call`;
  - routes original JMP/fall-through transfers through the installed hook table
    and live hook verifier without changing stack semantics;
  - records `cpu.hook_jump_site` for diagnostics.
- `call_installed_hook_like_near_call()` now records `cpu.hook_call_site` as
  `(caller_cs, caller_ip, child_cs, child_ip, return_ip)` while the child runs,
  so interactive wrappers can still identify original call-site context even
  though the helper correctly sets `CS:IP` to the child boundary.
- Strengthened `scripts/audit_hook_oracle.py`:
  - scans all `overkill/**/*.py`, not just `overkill/hooks.py`;
  - counts all 314 registered hooks across hook wrapper modules;
  - fails on any direct Python call to a registered hook function.
- Routed previously hidden child boundaries through installed/verifier-visible
  entry points:
  - `A876 -> 4CED`;
  - `4CED -> 4D15` triplet;
  - `A93C -> 4D64 -> 4D6F`;
  - `A90C -> A90F/A927`;
  - `A858/A870 -> 5AC8`;
  - `A936/A91E -> 5A92`;
  - `A8BE/A8F1 -> 7596`;
  - layer-sprite compositor JMP targets from `75F5/768E/7746`;
  - EGA row-driver child boundaries `2932`, `280D`, `2824`;
  - dirty-cell presenter jump targets `CCAA/CCF0/CCC4` and changed-present
    targets `CD8D/CDAA`;
  - source-cell mode-0 `41A6` call inside the CC7F presenter.
- Completed `1010:38B7` as a full near-return hook.  It now executes the shared
  `38D0` tail (`MOV DS,CS:[9596]; RET`) itself, instead of stopping at the
  fall-through and requiring a private compositor helper.  This removes a
  partial-boundary exception from the layer-sprite path.
- Corrected `CD8D` and `CDAA` hook-stop metadata from `near_ret` to fixed
  continuation `CE02`, matching their original JMP-target shape.
- Updated the frame-verifier test fixture to accept the raw-sample trace argument
  that the runner now passes.

Validation:

```text
python scripts/lint.py
# Lint passed for 81 Python files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 314 registered hooks, 314 metadata entries,
# no direct registered child calls detected.

python scripts/run_tests.py --scope dos-re --verbose --no-lint
# 4 passed, 0 failed, 0 timed out

python scripts/run_tests.py tests/test_core.py --name test_hook_oracle_static_audit_passes --timeout 10 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_frame_verify.py --timeout 20 --fail-fast --no-lint --verbose
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*38b7*' --timeout 20 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*presence*' --timeout 30 --fail-fast --no-lint --verbose
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*scan*' --timeout 30 --fail-fast --no-lint --verbose
# 13 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*dirty*' --timeout 30 --fail-fast --no-lint --verbose
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*27eb*' --timeout 60 --fail-fast --no-lint --verbose
python scripts/run_tests.py tests/test_overkill_hooks.py --name '*280d*' --timeout 60 --fail-fast --no-lint --verbose
python scripts/run_tests.py tests/test_overkill_hooks.py --name '*2824*' --timeout 60 --fail-fast --no-lint --verbose
# 3 focused EGA row-driver tests passed

python scripts/verify_hooks_headless.py --demo artifacts/demos/demo_play_tandy_20260615_132423 --demo-continue --verify-max 5000 --max-steps 1600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

Attempted a 10k headless verifier run in this sandbox, but it exceeded the tool
time budget before completion.  Re-run it on the reference machine after this
patch; the 5k run is clean and now includes newly verifier-visible nested child
boundaries.

Remaining explicit frontier:

- There can still be semantically fused routines that intentionally duplicate a
  child loop for performance, but they should no longer be silent: any complete
  registered original boundary called as a child must now go through either
  `call_installed_hook_like_near_call` or `jump_installed_hook_boundary`, and the
  static audit enforces that across the OVERKILL package.
- Rare allow-listed original compositor leaves in `KNOWN_ORIGINAL_LAYER_COMPOSITE_TARGETS`
  remain bounded-original, not Python source yet.  They are visible frontier
  entries for CGA/EGA cleanup, not hidden hook-oracle holes.

## 2026-06-15 - Hook-oracle blind-spot sweep and AF60 direct-entry hook

Continued the verifier-hardening pass after the AA71 final-boss contact bug proved
that parent hooks can hide child-helper mistakes when they call Python children
directly.  This pass focused on remaining direct child-call blind spots rather
than semantic gameplay modeling.

Implemented:

- `1010:AF60 overkill_movement_dir_double_step_2px_af60`
  - direct-entry hook for the self-call double 2-pixel movement step;
  - original shape is `CALL AF63` followed by the `AF63` step-table body;
  - preserves the `AF63` return-word stack scratch and returns to the real
    caller after the second step;
  - signature-guarded by `E8 00 00` + the full `AF63` entry/table/body bytes.
- Converted remaining hook-composition calls in `overkill/hooks.py` that invoked
  registered child hook functions directly to `call_installed_hook_like_near_call`:
  `306F`, `5A24`, `5A00`, `0162`, `497A`, and `50C9`.
- Converted Tandy renderer child calls to verifier-visible installed boundaries
  for `1010:34C5` and `1010:5A36`.
- Added `scripts/audit_hook_oracle.py`, a static guardrail that fails if:
  - a registered hook lacks `HookStop` metadata;
  - `overkill/hooks.py` directly calls a registered child hook through the old
    raw `_call_hook_like_near_call` helper;
  - Tandy rendering reintroduces direct `5A36` child calls.
- Fixed `scripts/lindis.py` so the linear disassembler actually runs from the
  command line; used it to confirm the `AF60 -> AF63 -> AF63` byte shape.

Validation:

```text
python scripts/lint.py
# Lint passed for 80 Python files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 269 registered hooks, 314 metadata entries,
# no direct registered child calls detected.

python scripts/run_tests.py tests/test_overkill_hooks.py --name test_movement_dir_step_tables_match_interpreted_asm_all_directions --timeout 20 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_core.py --name test_hook_oracle_static_audit_passes --timeout 10 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*aa71*' --timeout 30 --fail-fast --no-lint --verbose
# 5 passed

python scripts/run_tests.py --scope dos-re --verbose --no-lint
# 4 passed

python scripts/verify_hooks_headless.py --demo artifacts/demos/demo_play_tandy_20260615_132423 --demo-continue --verify-max 5000 --max-steps 1600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

Known caveat:

- `1010:2ABC -> object_row_address_mode1_2580` is still a raw direct helper call
  because `2580` is a mode-specific EGA-internal helper, not a registered
  top-level hook boundary in the current Tandy-first pass.  It remains an
  explicit audit-visible exception/future EGA cleanup item, not a silent blind
  spot.

Next useful blind-spot work:

- Move the same static audit style into any future module that composes address
  wrappers outside `overkill/hooks.py`.
- Continue shrinking `metadata w/o hook` frontier entries by either registering
  complete direct-entry hooks or demoting metadata-only partial tails to explicit
  bounded-original/frontier notes.
- Re-run a longer demo/headless verifier on the reference machine to see which
  newly exposed nested child boundaries become hot after the first 5k verified
  calls.

## 2026-06-15 - Movement direction step-table entry hooks (AEE4/AF22/AF63)

Lifted the three 8-direction object movement step tables to exact entry hooks.
Re-profiling was attempted from the recommended demo
(`artifacts/demos/demo_play_tandy_20260615_104031`), but the pure-Python
interpreter is far slower in this sandbox than on the reference machine, so the
candidate was instead confirmed by direct linear disassembly of the demo memory
image and the existing island map.

Finding: `1010:AEE4`, `1010:AF22`, and `1010:AF63` are three sibling
8-direction movement step tables with identical shape
(`MOV BX,SS:[BP+06]; SHL BX,1; JMP CS:[table]`) dispatching to handlers that
add/subtract a fixed per-step delta from `SS:[BP+02]` (X) and `SS:[BP+04]` (Y).
The deltas are 8px (AEE4), 3px (AF22), and 2px (AF63).  Each body was already
lifted and verified as a shared helper used by the 5DB2/5E42/AF60 parents
(`_run_aee4_step_for_direction`, `_run_af22_three_pixel_step_for_direction`,
`_run_af63_step_for_direction`), but the table *entries themselves* were not
registered, so a direct `CALL` to any of them (for example `1010:8A1D -> AF63`)
ran interpreted.

Implemented:

- `1010:AEE4 overkill_movement_dir_step_8px_aee4`
- `1010:AF22 overkill_movement_dir_step_3px_af22`
- `1010:AF63 overkill_movement_dir_step_2px_af63`
  - each is a thin near-return entry wrapper that runs the already-verified
    shared body and then `RET`;
  - each is guarded by the full entry+table+handler byte signature, so a
    runtime-patched dispatch/handler disables the hook (falls back to
    interpretation) instead of silently applying the wrong lift.

Classification: all three are `movement` (AEE4 added to `MOVEMENT_ADDRS`; AF22
and AF63 were already listed as bounded movement and are now hook-covered).

Verification (Python 3.10 sandbox; project targets 3.11):

```text
# focused oracle test: interpreted ASM vs hook, real game region bytes,
# all 8 directions x 3 coordinate seeds (incl. borrow/zero edges) per table
tests/test_overkill_hooks.py::test_movement_dir_step_tables_match_interpreted_asm_all_directions
# PASS (72 cases)

tests/test_overkill_hooks.py::test_live_verify_replacement_hooks_have_continuation_metadata
# PASS (new hooks have near_ret continuation metadata)

# regression cross-section, run via the pytest-free harness under python3.10:
#   41/41 movement+object+collision hook tests passed
#   111/111 every-other hook test passed
```

Honest limitations in this sandbox:

- `scripts/lint.py` and the full `scripts/run_tests.py` could not be run here:
  the repo requires Python >= 3.11 (`overkill/frontier_manifest.py` uses
  `enum.StrEnum`) and only Python 3.10 is available in this environment.  This
  is pre-existing and unrelated to the change; the edited modules
  (`hooks`, `gameplay/object_runtime`, `verification`, `coverage`) import and
  run cleanly under 3.10.
- The live headless hook verifier
  (`scripts/verify_hooks_headless.py --snapshot <demo>`) was started but did not
  finish within the sandbox time budget because the interpreter throughput here
  is ~100x slower than the reference machine.  It should be re-run on the
  reference machine:
  `python scripts/verify_hooks_headless.py --snapshot artifacts/demos/demo_play_tandy_20260615_104031/snapshot --verify-max 200 --max-steps 400000 --fast-ranges`.

Added a small generic linear disassembler helper, `scripts/lindis.py`, that
sweeps a CS:offset range using the project's own decoder (counting fetched code
bytes for instruction length, so jump-table data and branches do not derail the
sweep).  It was used to map the AEE4/AF22/AF63 family.

Next candidates from the same family/profile:

- `1010:AF60` self-call double-step entry (already lifted as
  `_run_af60_double_step_for_direction`; works today via the AF63 hook, but a
  dedicated entry hook would cover the self-call trick directly).
- `1010:89FF-8A20` movement setup that feeds `[BP+06]` then `CALL AF63`.
- `1010:F225-F2AE` / `1010:F263` object-behavior families that set sprite ids
  from `DS:2356` game-state then branch through `AFD8`/`BC45`.

## 2026-06-14 - Tile/contact probe cleanup for collision-system crystallization

Continued the small-target ASM cleanup with a meaning-revealing collision primitive rather than a large controller lift.

Implemented:

- `1010:4FF9 overkill_tile_contact_probe_4ff9`
  - shared object/probe-point tile/contact helper;
  - applies one of three `DS:214E` offset pairs to `SS:[BP+2]/[BP+4]`;
  - calls the already-lifted `5073` coordinate-to-tile-index helper and `505B` tile lookup helper;
  - restores the probe coordinates and returns with `CF=0` for empty space or `CF=1` for contact/blocking tile.

Classification note:

- This is still a raw collision primitive, not a semantic player/enemy/projectile rule.
- It helps separate the future `collision_system` layer from higher object behavior families that currently call into it from `9B2E`, `AC28`, and object movement/update paths.

Validation:

```text
pytest -q tests/test_overkill_hooks.py::test_tile_contact_probe_4ff9_matches_interpreted_asm_paths
# 1 passed

python scripts/lint.py
# Lint passed for 76 Python files

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 200 --max-steps 500000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200
```

Next easy meaning-revealing candidates:

- `1010:4E9F/4EBF`: keyboard ISR install/restore around text input prompts, belongs to `input_menu`.
- `1010:53C9-54BF`: text-entry prompt wrapper around `518C` and the temporary INT 9 hook.
- `1010:C51D-C562`: setup/reset tail that seeds tracked-coordinate/status descriptors before jumping to `859E`.
- Smaller children inside `9C01-9C6B` before lifting the whole `9B2E` controller.

## 2026-06-14 - Frame verifier input-pair skew fix

### 2026-06-14 - Hook verifier nested child-boundary honesty audit

- Fixed an oracle blind spot in composed parent hooks: a lifted parent could call an installed child hook directly, while the ASM-oracle clone also used the same child hook.  That made the child a shared black box inside the parent transaction.
- `call_installed_hook_like_near_call` now routes direct child calls through the active hook verifier when verification is enabled, with original near-CALL stack semantics and the child CS:IP restored before execution.
- Bounded interpreted near/far helpers now keep nested hook verification active by default, so child hook addresses reached by original helper code are verified at that exact VM state.
- Added `verify_nested_hooks` to `HookVerifierConfig`; it defaults to strict nested verification.  `play.py --verify-no-nested` and `verify_hooks_headless.py --no-nested` provide the old faster/shared-child mode for profiling only.
- Added a regression that intentionally makes a child hook wrong and proves the parent verifier catches the nested child divergence instead of passing the parent boundary.

Validation:

```text
python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q tests/test_overkill_hooks.py::test_hook_verifier_recursively_verifies_direct_child_hook_calls tests/test_overkill_hooks.py::test_hook_verifier_live_passthrough_override_can_publish_without_frame_boundary tests/test_overkill_hooks.py::test_hook_verifier_defers_live_passthrough_yield_until_after_diff tests/test_frame_verify.py
# 6 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 300 --max-steps 1000000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=300

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 80 --max-steps 600000
# OK HOOK VERIFY LIMIT REACHED verified=80
```


Fixed a live `--verify-frames --verify-frame-preview` verifier scheduling bug.
The frame verifier used to pump SDL/input events once before the reference ASM
runtime advanced, and then again between the reference and hooked candidate
runtimes.  A key pressed while the reference side was running could therefore be
delivered to the candidate for the current frame after the reference had already
reached its boundary.  That created a false one-frame input skew and visual
divergences during active play.

The generic verifier now samples input only at runtime-pair boundaries: once
before both the reference and candidate advance.  Events collected while the
reference side is running are intentionally deferred to the next pair so both
runtimes see them on the same verified frame.

Verification:

```text
python scripts/lint.py
# Lint passed for 76 Python files

pytest -q tests/test_frame_verify.py tests/test_overkill_hooks.py::test_hook_verifier_defers_live_passthrough_yield_until_after_diff tests/test_overkill_hooks.py::test_hook_verifier_live_passthrough_override_can_publish_without_frame_boundary
# 5 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 100 --max-steps 400000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=100

python scripts/play.py --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-frames --verify-frame-max 30 --verify-frame-source both
# FRAME VERIFY OK frames=30

# Programmatic deterministic key injection at frame boundaries (Right+Space,
# releases, Left, release) matched for 100 Tandy frame/timer boundaries.
```

Full `pytest -q` reached 81% with no visible failures before the sandbox
timeout, so it is not claimed as complete here.

## 2026-06-14 - Interstitial frame-script cleanup and raw status-list seeds

Continued the ASM-noise cleanup around the post-97B2 short-profile path.  This
pass deliberately stayed in the verified lifted-routine layer: it closes repeated
frame glue and raw descriptor setup blocks without naming a concrete menu/screen
or HUD widget yet.

Implemented:

- Captured oracle snapshots:
  - `artifacts/evidence/snapshot_stop_1010_d318_timed_input_loop`
  - `artifacts/evidence/snapshot_stop_1010_8517_status_cell_list_seed`
- `1010:D367 overkill_interstitial_status_cell_d367`
  - small interstitial/status cell blit helper: sets `AX=4703h`, calls `5A00`,
    zeroes `SI`, switches `DS` to `CS:95B6`, dispatches `5A6C`, then restores
    `DS` from `CS:9596`.
- `1010:D318 overkill_interstitial_timed_input_loop_d318`
  - one ASM-shaped iteration of the timed interstitial/input-wait frame script;
  - composes existing frame child hooks, far-calls `1F8F:0922`, increments
    `DS:BED8`, then either loops at `D318` or waits for the input-release bit
    before returning.
- `1010:852B overkill_status_cell_seed_852b`
  - one raw 10-byte status/list cell descriptor seed at `SS:BP`.
- `1010:8517 overkill_status_cell_list_seed_8517`
  - four-entry descriptor builder around `852B`; preserves the odd original
    call shape where the third `CALL 852B` returns to `852B` and the fourth
    descriptor is a fall-through into the same body.

Important proof detail:

- The generic bounded near-call helper cannot be used for the `8517` third
  `CALL 852B`, because the continuation equals the callee entry.  The parent
  hook therefore pushes the return word and invokes the lifted `852B` body
  directly so the same-IP call still executes once and leaves the same scratch
  stack shape.

Validation:

```bash
python -m pytest -q \
  tests/test_overkill_hooks.py::test_status_cell_seed_852b_and_list_8517_match_interpreted_asm_with_child_boundary \
  tests/test_overkill_hooks.py::test_interstitial_status_cell_d367_matches_interpreted_parent_with_child_boundaries \
  tests/test_overkill_hooks.py::test_interstitial_timed_input_loop_d318_matches_interpreted_parent_with_child_boundaries \
  tests/test_overkill_hooks.py::test_status_cell_composite_85d5_matches_interpreted_parent_with_child_boundaries \
  tests/test_overkill_hooks.py::test_status_coord_list_fill_99cd_matches_interpreted_loop \
  tests/test_overkill_hooks.py::test_frame_axis_count_9bfb_9bfe_tiny_leaves_match_interpreted_asm \
  tests/test_overkill_hooks.py::test_live_verify_replacement_hooks_have_continuation_metadata
# 7 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/snapshot_stop_1010_d318_timed_input_loop --verify-max 1 --max-steps 20 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/snapshot_stop_1010_8517_status_cell_list_seed --verify-max 1 --max-steps 20 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=1

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 200 --max-steps 400000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200

python scripts/lint.py
# Lint passed for 76 Python files
```

A full `pytest -q` run reached 83% with no displayed failures before the sandbox
timeout, so this package claims the focused tests and live verifier runs above.

Fresh profile result:

- `D318` is now a hook-covered frame-script boundary instead of 200 repeated raw
  interpreted frames.
- `8517` is hook-covered; the former `852B/852D/852E/8531/...` descriptor seed
  noise disappears behind the raw status-list builder.
- The next visible low-count cleanup targets are now `859E-8653`, `6120-613D`,
  and the setup tail around `C51D-C562`.  The larger semantic frontier remains
  `9B2E/9C01-9C6B`.

## 2026-06-14 - Status compositor and tiny frame-controller leaves

Continued the post-97B2 cleanup without entering the large `1010:9B2E` child
controller.  This pass absorbed small, bounded regions that were already exposed
by the profile and that compose existing lower-level hooks.

Implemented:

- Captured oracle snapshot: `artifacts/evidence/snapshot_stop_1010_85d5_status_cell`.
- `1010:85D5 overkill_status_cell_composite_85d5`
  - low-level status/HUD cell compositor parent around the verified
    `613E`/`615A` cursor leaves and the existing `5A6C` source-cell blit
    dispatch;
  - still a raw compositor, not a semantic HUD widget model.
- `1010:99CD overkill_status_coord_list_fill_99cd`
  - compact coordinate-list fill loop that writes `([BP+2]+8,[BP+4]+9)` word
    pairs into `ES:DI` for `CX` entries, then falls through to `99DD`.
- `1010:9BFB overkill_frame_axis_count_inc_ah_9bfb`
- `1010:9BFE overkill_frame_axis_count_inc_al_9bfe`
  - tiny `INC AH/AL; RET` leaves used inside the `9C01` frame-controller child
    before the `9C6B` jump-table dispatch.

Validation:

```bash
python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q \
  tests/test_overkill_hooks.py::test_status_cell_composite_85d5_matches_interpreted_parent_with_child_boundaries \
  tests/test_overkill_hooks.py::test_status_coord_list_fill_99cd_matches_interpreted_loop \
  tests/test_overkill_hooks.py::test_frame_axis_count_9bfb_9bfe_tiny_leaves_match_interpreted_asm \
  tests/test_overkill_hooks.py::test_status_cell_composite_85d5_matches_captured_snapshot \
  tests/test_overkill_hooks.py::test_live_verify_replacement_hooks_have_continuation_metadata
# 5 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 150 --max-steps 300000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=150; final CS:IP=1010:97B2

python scripts/profile_hotspots.py 20000 --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_191454 --top 40
# 85D5 and 99CD now appear as hook-covered call boundaries.
```

A full `pytest -q` run reached 84% with no failures displayed before the sandbox
timeout, so this package claims the focused oracle tests and live verification
above rather than full-suite completion.

Next best targets after this pass:

- classify the caller block around `1010:8517-8545` / `1010:859E-8653`, because
  `85D5` now exposes it as a likely status/HUD object-cell parent;
- classify `1010:9C01-9C6B` before lifting larger parts of `9B2E`; the new
  `9BFB/9BFE` leaves show this area counts four axis/side conditions and jumps
  through a table at `9C70`;
- keep `1010:9B2E-9C6B` as the main bounded-original frame-controller frontier
  until its internal children have a manifest.

## 2026-06-14 - Cursor stride leaves and setup/object-slot reset blocks

Classified and lifted five low-risk regions exposed by the short post-97B2
profile before entering the large `9B2E` controller.

- Added `1010:613E overkill_status_cursor_advance_613e`, the CS:95BC
  video-mode cursor advance dispatch used by status/HUD drawing glue.
- Added `1010:615A overkill_status_cursor_retreat_615a`, the inverse cursor
  retreat dispatch used by the same status draw family.
- Added `1010:C3BF overkill_reset_effect_slot_block_c3bf`, a compact-slot
  reset loop using the `DS:8D12` pointer table and `0040h` present-pointer
  stride.
- Added `1010:C3F1 overkill_reset_object_slot_block_c3f1`, the setup object-slot
  reset loop that preserves slots whose `+16` field is already `0001h`.
- Added `1010:C4E5 overkill_reset_object_slot_block_c4e5`, the sibling setup
  loop reached from `C4DB` that clears selected object-slot fields through the
  `DS:32CA` pointer table, stamps each slot from `CS:C3A2`, advances that
  source pointer by `0280h`, and falls through to `C51D`.
- Kept these as low-level lifted routines: no semantic enemy/player/HUD model
  was introduced.

Validation:

```text
pytest -q tests/test_overkill_hooks.py::test_status_cursor_613e_and_615a_match_interpreted_asm_all_modes tests/test_overkill_hooks.py::test_setup_reset_blocks_c3bf_and_c3f1_match_interpreted_asm tests/test_overkill_hooks.py::test_reset_object_slot_block_c4e5_matches_interpreted_asm
# 3 passed
```

Next likely targets from the same profile are now `1010:861B-864B` / `1010:85D5`
(status/HUD cell composition around the new cursor leaves), then the larger
`1010:9B2E-9C6B` frame-controller child and object/frontier regions such as
`1010:A4D7-A64C`, `1010:A031-A090`, and `1010:AFD8-B01C`.

## 2026-06-14 - BEC5 variant 000A non-owner no-op collision fix

Fixed the fail-fast reported from `BC45 -> BC4B -> 62F6 -> BEC5 variant 000A`
with current object `logic_id=0029h`.  The earlier lift only covered the
owner-linked fallback where `DS:[BX+30h] == BP`; the original ASM also has an
ordinary non-owner case.

- Rechecked the tail of `1010:BEC5`: after the 7/8/0C/9 table and 2/6/5 checks,
  it executes `CMP BP,[BX+30h]`; if the slot is not owner-linked, the next
  instruction is a plain `RET`.
- `_run_collision_handler_bec5_observed` now preserves that no-op contact path,
  including the live flags from the final `CMP`, instead of fail-fasting.
- Added an original-ASM-vs-lift regression for `variant=000Ah` with
  `DS:[BX+30h] != BP`, matching the newly observed collision family.

Validation:

```text
pytest -q tests/test_overkill_hooks.py::test_bec5_variant_000a_non_owner_contact_is_noop_ret_against_asm
# 1 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 100 --max-steps 200000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=100

python scripts/lint.py
# Lint passed for 76 Python files
```

Next hook clues remain the same at the high level: `1010:9B2E-9C6B` is the big
bounded-original controller inside `97B2`, while `1010:A4D7-A64C`,
`1010:A031-A090`, and `1010:AFD8-B01C` look like object/gameplay families that
should be entered with stop snapshots before semantic naming.

## 2026-06-14 - Frame effect/status glue and 97B2 frame-loop lift

Classified and lifted the next low-risk gameplay-loop glue after the allocator pass.
This pass deliberately stopped short of semantic rewrites: `9B2E` is now isolated
as the next larger controller frontier, while the finite frame wrappers around it
are Python-owned and oracle-tested.

- Added `1010:77C5 overkill_frame_effect_gate_77c5`, the per-frame
  slash/effect gate around `DS:A97A/A97C`.  It composes the existing `77F6`
  slash renderer and keeps the EGA-only `511F` page-toggle branch explicit.
- Added `1010:60A2 overkill_frame_effect_status_text_60a2`, a three-call
  status/effect glue block: `77C5`, `5F61`, then `5EDB`.
- Added `1010:97B2 overkill_frame_loop_97b2`, one verified iteration of the
  gameplay/attract frame controller.  It keeps child proof boundaries in the
  original order and intentionally runs `1010:9B2E` as bounded original for now.
- Updated verifier metadata for same-IP loop verification, coverage island
  classification, symbols, and leaf tests that need to bypass the new frame
  parents when verifying nested `5EF9`/`5EDB` boundaries directly.

Validation:

```text
python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 150 --max-steps 300000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=150; final CS:IP=1010:97B2

python scripts/profile_hotspots.py 2000 --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_191454 --top 50
# 97B2 is hook-covered; 60A2 and 77C5 child glue no longer appears as interpreted loop glue

python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q
# 248 passed
```

Next hook clues after this pass:

- `1010:9B2E-9C6B` is now the most important bounded-original child inside
  `97B2`; classify it before lifting because it appears to own input/game-state
  control rather than a pure draw or object leaf.
- After `97B2`, short profiles expose smaller transition/menu/status regions,
  especially `1010:C4E5-C51B`, `1010:613E-6159`, `1010:861B-864B`, and
  `1010:C3BF-C3E5`.
- The previous `60A2/60A5/60A8/60AB` and `77C5/77CA` glue is closed enough to
  leave alone unless a new snapshot proves an unobserved branch.

## 2026-06-14 - Object allocator hooks 7524/7573

Absorbed the smallest high-confidence next target from the remaining gameplay
hotspots: the 38h-byte slot allocators at `1010:7524` and `1010:7573`.

- Added `1010:7524 overkill_find_free_effect_slot_7524` for the compact effect
  pool allocator.  It scans from `DS:[95D8]` through `23B4..2B5A`, wraps at
  `2B5C`, writes the selected free slot back to `DS:[95D8]`, and returns
  `BX=FFFF` on exhaustion.
- Added `1010:7573 overkill_find_free_object_slot_7573` for the main gameplay
  object pool allocator.  It scans from `DS:[95DA]` through `2B5C..32CA`,
  repeats the `32CC -> 2B5C` sentinel wrap check on every iteration, writes the
  selected free slot back to `DS:[95DA]`, and returns `BX=FFFF` on exhaustion.
- Both wrappers are guarded by exact live-code signatures so later overlay reuse
  would fall back to interpretation instead of silently applying the wrong lift.
- Added direct original-ASM-vs-hook tests for wrap, found-slot, and exhausted
  cases.
- Updated hook-verifier metadata, coverage island classification, and symbols.

Validation:

```text
python -m pytest -q tests/test_overkill_hooks.py::test_effect_allocator_7524_hook_matches_original_wrap_and_exhaustion tests/test_overkill_hooks.py::test_object_allocator_7573_hook_wrapper_matches_original
# 2 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 100 --max-steps 200000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=100

python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q
# 245 passed
```

Next hook clues after this pass:

- `1010:9B2E-9C6B` is still the largest remaining interpreted region in the
  long gameplay run and should be classified before lifting.
- `1010:A490-A780` / `1010:AFD8-B01C` remain likely gameplay-object family
  frontiers, but they are larger than the allocator leaf and should be entered
  with a stop snapshot.
- `1010:77C5/77CA` plus `60A2/60A5/60A8/60AB` show up in short profiles as
  frame/status glue around already-hooked `5F61` and `5EDB`; useful, but less
  likely to reveal new object behavior.

## 2026-06-14 - BFC7 logic-0021 collision gate fix

Fixed the fail-fast reported from `artifacts/snapshot_play_tandy_20260614_202217`:
`BC4B -> 62F6 -> BEC5 variant 0005 -> BFC7 logic 0021 -> BFD2`.

- Rechecked the original bytes around `1010:BFC7`: logic id `0021h` is only a
  gate.  If `DS:2356 != 0004h`, the helper returns immediately; if
  `DS:2356 == 0004h`, the `JE` lands at `BFD7` and joins the normal
  death/transition tail.
- Removed the stale fail-fast for the `DS:2356 == 0004h` case and let it reuse
  the already lifted BFD7 path.
- Added an original-ASM-vs-lift regression test seeded from the gameplay memory
  image.  The test starts both CPUs at `1010:BFC7` with logic id `0021h` and
  `DS:2356=0004h`; the interpreted ASM and Python helper now return with
  identical register state and full memory.

Validation:

```text
pytest -q tests/test_overkill_hooks.py::test_bfc7_logic_21_gate_four_joins_normal_death_tail_against_asm
# 1 passed

python scripts/lint.py
# Lint passed for 76 Python files

pytest -q
# 243 passed
```

Next hook clues from the reported coverage:

- `1010:7524-7595`, hottest at `757A`, is probably the best small next target.
  The project already has `_find_free_object_slot_7573` and `_find_free_effect_slot_7524`
  helpers, so this region looks like allocator logic that can be promoted into
  exact hooks with focused oracle tests.
- `1010:9B2E-9C6B` is the largest remaining interpreted region by hits; it
  should be classified before lifting because it may be UI/status or scripted
  gameplay bookkeeping rather than a pure object routine.
- `1010:A490-A780` and `1010:AFD8-B01C` look like gameplay-object family
  frontiers and are better candidates after the allocator leaf is closed.

## 2026-06-14 - Object behavior B24D absorption

Continued the Tandy + AdLib gameplay-loop absorption from
`artifacts/snapshot_play_tandy_20260614_191454`.  The next hot unlifted object
family path was `EFAE -> B24D -> 5E42`.

- Captured evidence snapshot `artifacts/evidence/snapshot_stop_1010_b24d_behavior`.
- Added `1010:B24D overkill_object_behavior_b24d` for the observed object-family
  steering/overlap prelude.
- The hook composes the already verified runtime-patched `1010:5E42` steering
  helper, mirrors the signed/unsigned reference-box checks against `DS:237E`
  and `DS:2380`, and lands on the existing `AD5A`/`ADC9` motion tails.
- The rare overlap side-effect helper `1010:9E19` remains a bounded original
  child call from inside B24D; it should be lifted independently if it becomes a
  real hotspot.
- Updated leaf-hook tests that intentionally target nested `5E42`/`61C7`
  boundaries to disable the newly absorbed `B24D` parent, so those tests still
  exercise the leaf boundary itself.

Validation:

```text
python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/snapshot_stop_1010_b24d_behavior --verify-max 1 --max-steps 20 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=1; final CS:IP=1010:AD5A

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 20 --max-steps 20000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=20

python scripts/profile_hotspots.py 600000 --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_191454 --top 35
# B24D now appears as hook-covered; interpreted B24D body is gone

python scripts/lint.py
# Lint passed for 76 Python files

python -m pytest -q
# 242 passed
```

## 2026-06-14 - Object behavior B86D absorption

Continued from the Tandy + AdLib gameplay snapshot
`artifacts/snapshot_play_tandy_20260614_191454`, where the current code had
already absorbed several previously unknown frame/game-state regions and the
remaining interpreted hotspot was `1010:B86D-B8EF`.

- Added `1010:B86D overkill_object_behavior_b86d` for the observed logic-id
  `001Dh` object-family behavior.
- The hook covers the hot `B885 -> B729 -> 5DB2 -> BC4B` setup path, the
  adjacent `B8B0 -> BC4B` object-X drift path, and the later
  `B8F8 -> 5E1B -> 5E42 -> BC4B` edge-steering path.
- The hook lands on the existing `1010:BC4B` postmove/collision boundary instead
  of composing that tail, keeping ownership with the verified collision helper.
- Added evidence snapshots:
  `artifacts/evidence/snapshot_stop_1010_b86d_behavior`,
  `artifacts/evidence/snapshot_stop_1010_b8b0_behavior`, and
  `artifacts/evidence/snapshot_stop_1010_b86d_b8f8_edge`.
- Added a full-memory regression for the observed B86D paths.  The B8B0
  evidence state is rewound only to the exact `B86D` entry IP because its
  preceding B86D setup instructions are compare-only.

Validation:

```text
direct original-vs-hook B86D oracle check against both evidence snapshots
# CPU/register state and full memory matched at 1010:BC4B

python scripts/profile_hotspots.py 300000 --snapshot artifacts\snapshot_play_tandy_20260614_191454 --top 30
# B86D now appears as hook-covered; interpreted B86D..B8EF body is gone
```

## 2026-06-14 - Bootstrap LZEXE tail contract correction

- Tightened the `1C43:0069` bootstrap LZEXE hook so the `AL==0` terminator
  path now lands on the oracle continuation with `AX=0000` and `CX=0003` at
  `1C43:00FC` instead of preserving the entry `AH` byte and dropping the
  residual count.
- Added a regression test against `artifacts/evidence/snapshot_stop_1c43_0069`
  that differential-verifies the `1C43:0069` hook and pins the exact `00FC`
  register snapshot.
- Raised bootstrap verification headroom to `asm_max_steps=1_000_000` in the
  play/CLI/headless verifier setup, and added a matching `23AD:0069`
  regression on `artifacts/evidence/snapshot_stop_23ad_0069` so the second
  nested stub does not trip the old 500k ASM ceiling.
- Fixed the loaded AdLib note/frequency helper at `2032:024F` by matching the
  original `mov bl,[si+0749]` register side effect and the `push ax` / `pop ax`
  pair around the first YM3812 write.  Added a direct original-vs-hook
  regression using the static runtime bundle memory image.

Validation:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\verify_hooks_headless.py --snapshot artifacts\evidence\snapshot_stop_1c43_0069 --verify-max 1 --max-steps 500000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=1
```

## 2026-06-14 - Maintenance cleanup pass

- Renamed the headless frame dump tool from the old CGA-only script name to
  `scripts/render_frame.py`.  The tool now clearly owns CGA, EGA, and Tandy
  snapshot rendering, while internal CGA-specific helper names remain
  mode-specific where appropriate.
- Updated imports and documentation references to the new frame-render tool; no
  legacy module alias was kept.
- Added `scripts/clean.py`, a dependency-free cleanup helper for Python caches,
  package build outputs, local Nuked-OPL3 extension artifacts, and optional
  unpromoted generated capture folders.
- Expanded `.gitignore` for package build outputs, default headless frame dumps,
  and Nuked-OPL3 generated C/object/linker files.
- Tightened `scripts/lint.py` with a legacy-reference guard so old moved module
  names such as the former frame renderer, old hook-verifier module path, and
  obsolete replacement-file naming do not creep back into Python/Markdown files.
- Cleaned stale generated `__pycache__` files from the packaged tree.
- Updated Nuked-OPL3 build docs to describe the explicit in-place CFFI build;
  removed stale setup.py wording.

Validation:

```text
python scripts/lint.py
# Lint passed for 75 Python files

python -m pytest -q
# 232 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_maintenance_clean
# reached 1010:D007; steps=19847
```

## 2026-06-14 - Repository cleanup and vendored Nuked-OPL3

- Vendored the optional `nuked_opl3/` CFFI package directly into the repository
  from the supplied archive, keeping only source files, vendor C core, README,
  and LICENSE.  Prebuilt `.pyd` files and `__pycache__` were intentionally not
  imported.
- Updated `.gitignore` so locally built `_opl3_cffi*` extension artifacts stay
  out of version control.
- Updated `pyproject.toml` package discovery so `dos_re`, `overkill`, and the
  vendored `nuked_opl3` package are explicit.
- Updated AdLib documentation: FM PCM no longer depends on an external package;
  build the vendored binding with `python -m nuked_opl3._ffi_build` after
  installing the optional `[adlib]` dependency.
- Added `docs/architecture/third_party.md` and package-boundary rules for
  vendored components.  `nuked_opl3` must not import `dos_re` or `overkill`.
- Extended `scripts/lint.py` to parse/check the vendored package while allowing
  the generated `_opl3_cffi` extension to be absent before local build.
- Promoted the two remaining top-level `artifacts/snapshot_play_*` fixtures used
  by tests into `artifacts/test_oracles/` with descriptive names, then removed
  the stale live snapshot directories from the repository.

Validation:

```text
python scripts/lint.py
# Lint passed for 74 Python files

python -m pytest -q
# 232 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_vendor_clean
# reached 1010:D007; steps=19847
```

## 2026-06-14 - Documentation ownership refactor

Separated documentation by the same role boundary as the code packages.

- `docs/dos_re/` now contains only reusable DOS reverse-engineering methodology.
- `docs/overkill/` owns OVERKILL-specific archaeology, runtime findings, island
  truth tables, status, source-port design, and performance notes.
- `docs/architecture/` owns cross-package dependency and boundary rules.
- Added `docs/README.md` as the documentation map.
- Moved root `RUN_STATUS.md` to `docs/overkill/run_status.md`.
- Moved root `PERFORMANCE_INVESTIGATION.md` to
  `docs/overkill/performance_investigation.md`.
- Added a lint guard preventing new loose durable docs under `docs/` and
  preventing root status/performance docs from reappearing.

Validation:

```text
python scripts/lint.py
python -m pytest -q
python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_docs_refactor
```

## 2026-06-14 - Main-menu AdLib runtime hook lifting

Reduced the remaining main-menu slowdown caused by interpreting the loaded
optional AdLib driver at `2032:*` on every timer IRQ.  This pass targets the
interactive/menu phase rather than cold-start bootstrap.

- Added a `2032:0063` top-level loaded-AdLib timer-tick hook.  It preserves the
  original register-save contract, reentrancy byte `2032:0062`, global countdown
  `2032:000D`, and the nine 32-byte channel records at `05A9..06A9`, but routes
  each channel through smaller lifted boundaries.
- Added a `2032:00CD` channel-idle fast path for the common main-menu case where
  the channel is active but the global countdown has not expired and both
  modulation helpers are disabled.  Non-idle note/command advancement still
  falls back to the original driver body.
- Added `2032:0557` YM3812 register/value write hook.  It emits the same
  `388h/389h` writes for Nuked-OPL3, models the PIT/speaker delay side effects,
  but skips the busy delay instruction stream.
- Added disabled fast paths for `2032:02C9` and `2032:02F6`, the two per-channel
  modulation helpers that often only clear/test AL and return.
- Classified the loaded `2032:*` optional sound driver segment as the `sound`
  island instead of leaving it as `unknown`.

Snapshot measurement from `snapshot_play_tandy_20260614_134931`:

```text
100 delivered INT 08h ticks, with previous hooks disabled: 42,599 interpreted instructions
100 delivered INT 08h ticks, after this pass:              10,365 interpreted instructions
```

Validation:

```text
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 225 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_test
# reached 1010:D007; steps=21,499
```

## 2026-06-14 - Bootstrap LZEXE and AdLib probe lifting

Reduced pure-original Tandy+AdLib cold-start ASM in the dynamic/init layer.

- Added `overkill/bootstrap_lzexe.py` and hooks for the
  observed temporary nested LZEXE/self-relocation stubs at `1B65:0069`,
  `1C43:0069`, and `23AD:0069`. These hooks lift only the hot bitstream copy
  loop and stop at the original relocation/final-transfer tail (`00FC`), keeping
  the bootstrap/runtime boundary explicit.
- Classified the observed temporary unpacker segments as `bootstrap` rather than
  `unknown`; they are not source-port runtime islands.
- Added `overkill/sounds/adlib_driver.py` and a
  `2032:04E9` hook for the loaded Sound Images AdLib/YM3812 hardware probe.
  The hook stays registered at the exact boundary but now defers to the
  interpreted oracle because the remaining stack/branch behavior is still
  evidence-sensitive.
- Tightened `2032:0557` so the helper exits with `AL` copied from `AH`
  (`0001h -> 0000h`, `6004h -> 6060h`) and preserves the `056E` scratch word
  expected by the verifier.
- `scripts/profile_hotspots.py` now accepts `--sound pc|adlib|roland` and uses
  the canonical compact PSP tail builder, so profiling can match `play.py
  --video tandy --sound adlib`.

Validation:

```text
python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_after_hooks_final
# reached 1010:D007; steps=21,499
# memory_1mb.bin SHA256 is unchanged: c9bad83826f22bd144a7dcb3d98d84aaaf732b03527f8702dd4d2b68da57a476
# CPU snapshot is byte-equivalent to the previous interpreted canonical bundle

python scripts/lint.py
# passed

python -m pytest -q
# 225 passed
```

Before this pass, the canonical static bundle reached `1010:D007` in 1,245,977
steps before the LZEXE lift and 95,846 steps after the LZEXE lift alone. With
the AdLib probe lift as well it now reaches the same runtime image in 21,499
steps.

# RUN_STATUS update - zombie cleanup

- Removed one-off diagnostic wrapper/probe scripts that used hardcoded local paths
  or duplicated canonical CLI commands: `trace_start.py`, `make_trace_coverage.py`,
  `make_runtime_snapshot.py`, `run_until_checkpoint.py`, `check_intro_sound_poll.py`,
  `probe_sound_issue.py`, `trace_timer_isr.py`, and `probe_ega_page_offsets.py`.
- Removed deprecated interactive/verification CLI compatibility options:
  `scripts/play.py --fps` and `--verify-full-memory` in both `play.py` and
  `overkill.cli`.  Timing is controlled by `--game-hz`; full-memory hook
  verification remains the default and `--verify-fast-ranges` is the explicit
  opt-out.
- Removed stale hook-name aliases from `overkill.hooks` and updated
  tests to use canonical names: address-suffixed packed/checksum hooks, shared
  layer-sprite names, shared coordinate names, and the `61C7` counter boundary.
- Removed the obsolete `asset_codecs/startup_graphics.py` compatibility shim;
  startup graphics materialization now has a single owner in
  `rendering/startup_graphics.py`.
- Extended `scripts/lint.py` to reject hardcoded local workspace paths in future
  diagnostic scripts, so one-off `/mnt/data/...` probes do not creep back in.

Validation: `python scripts/lint.py` -> 68 Python files; `python -m pytest -q` -> 225 passed.

# RUN_STATUS update - static runtime bundle materializer

- Added `overkill/static_runtime_bundle.py`.
- Added `python -m overkill.cli static-runtime-bundle` to run the original
  bootstrap with compact `--video/--sound` selectors, stop at an inner-runtime
  frontier, and write a canonical initialized snapshot plus
  `static_runtime_bundle.json`.
- Cold-start `trace` and `snapshot` now accept `--video`, `--sound`, and explicit
  `--dos-args` override, so diagnostics can use the same canonical compact tail
  as `scripts/play.py`.
- Materialized Tandy + AdLib bundle from original files reached `1010:D007` in
  1,245,977 steps.  Recorded checks: command tail `0D 02 41`, `CS:95BC=0002`,
  `DS:0055=0001`, `DS:95DA=2B5C`, nonzero `2032:*` optional driver area.
- New tests: `tests/test_static_runtime_bundle.py`.

Validation commands run:

```bash
python -m pytest tests/test_static_runtime_bundle.py -q
python -m overkill.cli static-runtime-bundle assets/OVERKILL \
  --game-root assets --video tandy --sound adlib \
  --steps 3000000 --trace-tail 20 \
  --out-dir artifacts/static_runtime_bundle
```

## 2026-06-14 bootstrap/static-runtime boundary policy

- Added `docs/overkill/bootstrap_static_boundary.md` to make the project rule explicit:
  original startup/bootstrap is an oracle and extraction layer, not the target
  source-port gameplay architecture.
- Added `overkill/bootstrap_boundary.py` as an importable
  manifest for the current boundary: canonical original inputs, noncanonical
  generated files, bootstrap islands, known inner-runtime frontiers, compact PSP
  tails, required initial state, and derived asset classes.
- Added `overkill-port bootstrap-boundary` /
  `python -m overkill.cli bootstrap-boundary` to write the current manifest
  as JSON without executing the game.
- Updated design/methodology/island docs to preserve the rule that
  `assets/OVERKILL` and `assets/OVERKILL.EXE` are the only canonical inputs;
  unpacked images and overlay blobs are deterministic build/evidence artifacts
  only.

Validation: `python scripts/lint.py`; `python -m pytest tests/test_bootstrap_boundary.py tests/test_core.py tests/test_overkill/hooks.py -q` -> 212 passed.

## 2026-06-14 Nuked-OPL3 AdLib audio backend

- Added an optional SDL-side AdLib audio backend that consumes the original
  OVERKILL YM3812 register stream from ports `388h/389h` and renders it through
  the vendored `nuked_opl3.OPL3` binding when its CFFI extension is built.
- `DOSMachine` now exposes `set_adlib_callback(reg, value, emit_current=True)`,
  mirroring the existing PC-speaker callback shape while keeping AdLib detection,
  register state, snapshots, and headless tests deterministic.
- `scripts/play.py --sound adlib` now wires that callback to the SDL viewer.
  `--adlib-audio off` leaves the original driver active but disables PCM output.
- If the vendored `nuked_opl3` extension is not built, the game still runs the original
  AdLib driver and records/register-forwards writes; the viewer reports a clear
  status message and stays silent instead of crashing.
- Validation: `python scripts/lint.py`;
  `python -m pytest tests/test_core.py tests/test_overkill/hooks.py -q` -> 209 passed.

## 2026-06-14 Edrax level-select fire fix

- Fixed `1010:D445` selector hook behavior for FIRE on selector value zero.
- Original ASM at `1010:D46F` is `TEST byte [98BE],10h; JZ D445; RET`, so it
  accepts FIRE for every `DS:BEDA` value.  The lifted hook had added an
  incorrect `BEDA != 0` guard while making the loop UI-yieldable.
- `DS:BEDA == 0` is the first planet slot (Edrax), so the bug only blocked
  Edrax while all other planets still started normally.
- Added a regression case comparing interpreted ASM and hook for
  `buttons=10h, BEDA=0`.

Validation:

```text
python scripts/lint.py
python -m pytest tests/test_core.py tests/test_overkill/hooks.py -q
# 206 passed
```


## 2026-06-14 AdLib compact-tail and OPL probe fix

- Added `overkill.launch.build_command_tail(video, sound)`.
  `--video tandy --sound adlib` now passes compact selector bytes `0D 02 41`:
  Tandy video in `PSP:82`, AdLib driver selector `A` in `PSP:83`.
- Added a narrow YM3812/AdLib port model for `388h/389h`: selected-register
  tracking, register storage, and timer-status bits for the original presence
  probe.
- `DS:0055` can now become `1`; in that mode `1010:06E5` interprets the original
  ISR body so the far call through `2032:0000` runs before the shared timer work.
- Validation: `python scripts/lint.py`; `python -m pytest tests/test_core.py tests/test_overkill/hooks.py -q` -> `206 passed`.

## 2026-06-14 text-mode launcher and BIOS console support

Investigated the missing original startup screens:

- `assets\OVERKILL` remains the large MZ/container used for normal gameplay.
- `assets\OVERKILL.EXE` is a separate text-mode splash/launcher program.  It
  prints the Tech-Noir/registered-version text and the graphics adapter selector.
- The selector was invisible because the VM only kept DOS stdout as a log and
  the SDL viewer always decoded B800h as graphics.

Implemented narrow text-mode support:

- BIOS text modes 00h/01h/02h/03h/07h now track cursor row/column and clear text
  pages.
- BIOS teletype and character writes update B800h/B000h text memory.
- DOS console output (`INT 21h/AH=02h`, `09h`, stdout/stderr writes, and AH=01h
  echo) paints the active text page when a text mode is active.
- SDL can render 80x25 text pages with integer scaling and fixed aspect.
- Graphics presenter hooks mark text mode inactive so Tandy/CGA/EGA gameplay is
  not mistaken for text just because the last BIOS mode is still 03h.
- `INT 10h AH=12h BL=10h` now reports a colour EGA/VGA-style adapter so the
  launcher does not fall into its "must have colour graphics" error path.

Evidence:

```text
assets\OVERKILL.EXE with console_input_fallback=None now blocks at:
  'OverKill'
  Please select video mode:
    1.  CGA 4 colour
    2.  EGA/VGA 16 colour
    3.  Tandy 1000 series
```

AdLib status:

- The original docs mention `/A`, but ASCII switches are launcher/outer
  semantics.  The inner game module reads raw compact PSP bytes, so passing
  ASCII `/A` directly to `assets\OVERKILL` is not a valid AdLib selection.
- Probes through the current Tandy menu startup with several compact selector
  bytes produced no OPL `388h/389h` writes and left `DS:0055` clear.  The proven
  sound path remains the PC-speaker timer ISR.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 211 passed, 0 failed
```

Follow-up correction:

- `scripts/play.py` starts the inner `assets\OVERKILL` game path with
  `text_mode_active=False`; the first visible inner-game screen is graphical
  even though the BIOS mode byte may still be 03h.
- Older snapshots without `text_mode_active` metadata now load as graphics
  active by default.  A real `INT 10h` text-mode switch, such as the F9 boss key,
  still enables text rendering.
- `1010:073C` keeps its hot lifted fast path, but if F9 arms the longer
  platform/text service branch (`DS:9907 == 1`) the wrapper relinquishes that
  branch back to original code instead of trying to force it to return inside
  the hook.
- `scripts/play.py` also recognizes the `1010:55F1` menu select/fire wait as an
  interactive yield boundary, so level-select style screens can receive input
  and F12 snapshot requests can be processed while they are waiting.

---

# 2026-06-13 artifact cleanup checkpoint

Repository cleanup pass after the hook-integrity work.  The runtime/code
behavior was not intentionally changed.

Removed/generated-pruned material:

- old root `artifacts/snapshot_play_*` gameplay snapshots that were not regression fixtures;
- old root `artifacts/play_*` captures that were not regression fixtures;
- `artifacts/tmp_*` stop/verify scratch snapshots that were not regression fixtures;
- generated `artifacts/frame_verify/` PNG/VRAM diff dumps;
- non-test, stale `artifacts/evidence/*` probe snapshots;
- root scratch helpers `dump_at.py` and `headless_coverage.py`.

Kept durable artifacts only:

- `artifacts/test_oracles/*` used by regression tests, including promoted former root snapshots;
- evidence snapshots still referenced by regression tests;
- `artifacts/evidence/hook_verify_tandy_20260613_190326` as the current
  headless hook-verifier seed;
- `artifacts/hook_coverage_cache.json`;
- `artifacts/README.md` with the retention policy.

Validation after cleanup:

```text
python -m pytest -q
185 passed

python -m compileall -q dos_re overkill tests scripts
OK

python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 --verify-max 1000 --fast-ranges
OK HOOK VERIFY LIMIT REACHED verified=1000
```

Size changed from roughly 183 MB to roughly 30 MB while keeping all regression oracles.

---

## 2026-06-13 Tandy hook integrity / C054 cleanup pass

Continued from the `1010:BC4B overkill_object_postmove_bc4b` full-memory
divergence at call 3 on `artifacts\snapshot_play_tandy_20260613_190326`.

Results:

- Added `scripts/verify_hooks_headless.py`, a pygame-free live hook verifier for
  snapshot runs.  It mirrors `play.py --verify-hooks` but can run in CI/minimal
  shells and automatically disables non-CGA interactive hooks such as `1010:58DF`
  for Tandy/EGA snapshots unless explicitly requested.
- Refactored the duplicated `C054:C12D` effect-spawn tail into
  `_run_c054_c12d_effect_spawn_tail`.  The helper preserves the visible dead
  stack scratch from `PUSH BX`, `PUSH BP`, `CALL 7420`, and decrements
  `DS:A47E`, so this is cleanup only, not a behavior change.
- Removed temporary `tmp_*.py` debugging scripts from the working tree after the
  reusable headless verifier replaced them.

Verification:

```text
python -m pytest -q
# 185 passed
python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260613_190326 --verify-max 9000
# HOOK VERIFY LIMIT REACHED verified=9000, no divergence
python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260613_190326 --verify-max 10000 --fast-ranges
# HOOK VERIFY LIMIT REACHED verified=10000, no divergence
```

Note: a full-memory 10k run was attempted too, but it did not finish within the
available sandbox timeout after passing the 9k checkpoint without divergence.

## 2026-06-14 original asset source switch

Switched active runtime/test/script defaults from generated convenience files to
the original OVERKILL assets:

- executable/container: `assets\OVERKILL`
- companion splash/loader data: `assets\OVERKILL.EXE`

Removed generated assets:

- `assets\OVERKILL.UNLZEXE.EXE`
- `assets\OVERKILL.OVERLAY.BIN`

Notes:

- `assets\OVERKILL` is itself an MZ executable with the 467,649-byte overlay
  appended, so the runtime now lets the original unpack/bootstrap path produce
  the in-memory game image.
- `create_runtime()` keeps `OVERKILL.UNLZEXE.EXE` as a legacy alias only when
  that generated file is absent, mapping it to sibling `OVERKILL` so old
  snapshots/commands can still be loaded.
- The original startup path exposed two narrow BIOS/port details that the
  generated file hid: INT 10h/AH=05h active display page selection, and
  monochrome status port `03BAh` polling with bit `80h`.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 207 passed, 0 failed
headless Tandy original-container smoke with --verify-hooks --verify-require-metadata --verify-max 50
# HOOK VERIFY LIMIT REACHED verified=50, no divergence
```

## 2026-06-13 strict hook verifier cold-start cleanup

Followed up on `scripts\play.py --verify-hooks --verify-stop-on-diff` after
full-memory verification became the default.

Fixes:

- `HookVerifier._clone_runtime()` now copies `DOSMachine.console_input_fallback`.
  Interactive play sets this to `None`; the ASM oracle clone was accidentally
  reverting to the default Esc fallback and producing a false DOS/state diff at
  `1010:0FE4`.
- `1010:450C` verifier metadata now treats the lifted routine as the whole
  4-plane list parent ending at `44AA`, not as a single-block loopback to
  `450C`.
- `1010:450C` now preserves the dead-stack scratch word left by the original
  `CALL 44D7` / `RET` path (`SS:SP-2 = 450F`), which full-memory verification
  observes.
- Added verifier metadata for already-understood helpers `41A6`, `41DA`,
  `50C9`, and `58DF`.
- `1010:58DF` now self-disables for non-CGA modes before touching stack,
  registers, or memory.  The previous guard happened after setup side effects,
  which made raw Tandy all-hooks verification diverge.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 185 passed, 0 failed
headless Tandy cold start with command_tail=(0D,02), --verify-hooks, --verify-require-metadata, --verify-max 500
# HOOK VERIFY LIMIT REACHED verified=500, no divergence
```

## 2026-06-13 hook verifier full-state default

Changed live hook verification so full memory comparison is the default instead
of an opt-in mode.  The old named-range verifier can still be requested with
`--verify-fast-ranges` for profiling/debug sessions, but normal
`--verify-hooks` should now catch object/gameplay state divergence immediately
even when the changed byte is not in CS/video/stack helper ranges.

Also broadened DOS/BIOS/runtime-side comparisons to include allocator state,
open file metadata/data, keyboard queues, text output, video/timer counters, and
speaker/port tracking.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 185 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m overkill.cli continue-snapshot assets\OVERKILL.UNLZEXE.EXE artifacts\snapshot_play_tandy_20260613_181804 --game-root assets --steps 50000 --verify-hook 1010:BC45 --verify-hook 1010:BC4B --verify-stop-on-diff --verify-max 20 --out-dir artifacts\tmp_verify_full_memory_smoke
# HOOK VERIFY LIMIT REACHED verified=20, no divergence
```

## 2026-06-13 BEC5 second-counter collision tail fix

Investigated `artifacts\snapshot_play_tandy_20260613_181804`, where enemies
appeared to survive longer than the reference.

Findings:

- Frame verification diverged at frame 42.
- The first gameplay-state difference was `DS:2078`: reference decremented the
  linked counter from `03` to `02`, while the candidate left it at `03`.
- A watchpoint showed the reference write happened at original `1010:BFFE`,
  inside the shared `BFC7` death/transition tail.
- The lifted `BEC5` variant-2, `BEDC=0` path handled the `BF46` "second counter
  zero" branch by leaving `IP=BF46`.  That is not safe inside the composed
  `BC45/BC4B` parent path because the parent unwinds and overwrites the
  continuation.  The original `BF46` branch jumps to `BFC7`, so the lift must
  run the BFC7 tail inline.

Fix:

- `BEC5` now routes the observed second-counter-zero path into the shared BFC7
  tail, matching `BF46 -> BFC7`.
- Added a focused regression for the exact linked-counter decrement at
  `DS:2078`.
- Hook verification now defaults to full-memory comparison, so object/counter
  state is checked even when it lives outside the old named ranges.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 184 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\play.py --snapshot artifacts\snapshot_play_tandy_20260613_181804 --verify-frames --verify-frame-max 60 --verify-frame-source both
# FRAME VERIFY OK frames=60
```

## 2026-06-13 interactive Tandy timer ordering guard

Investigated a hidden level-start issue where the initial enemy sequence played
but the next level phase did not appear to continue in interactive Tandy play.

Findings:

- Long Tandy frame verification from
  `artifacts\test_oracles\snapshot_play_tandy_20260611_152751` stayed clean
  through 500 frames, so the deterministic hooked runtime still matches the ASM
  frame oracle at that level-start snapshot.
- The interactive SDL path had one extra source of timer mutation that the frame
  verifier does not exercise: `present_hook` could call
  `AsyncTimerIrqDriver.poll()` before the normal `1010:0679` frame wait.  If that
  IRQ advanced `CS:[066B]`, the later `0679` hook could return immediately
  instead of delivering the expected frame ISR work at the timer boundary.

Fix:

- Removed async IRQ polling from the presenter boundary.  Async IRQs still run
  in explicit retrace/menu/input wait loops where there is no normal `0679`
  frame wait to service sound.
- After every `0679` timer boundary, re-anchor the async IRQ scheduler by one
  full OVERKILL frame (`2` PIT ticks) instead of using the raw number of ISR
  ticks that happened to run inside that hook.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 171 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 300 --verify-frame-source both
# FRAME VERIFY OK frames=300
```

## 2026-06-13 live frame verifier preview

Added an interactive preview mode for frame verification.

Behavior:

- `python scripts\play.py --verify-frames --verify-frame-preview` now launches
  the normal SDL viewer and publishes the candidate runtime while each frame is
  compared against the reference ASM runtime.
- Keyboard input is delivered to both runtimes before frame boundaries, so the
  verifier can be played like `--verify-hooks`.
- With live preview and the default `--verify-frame-max 60`, the verifier treats
  the run as unbounded so the window does not close almost immediately.  Pass an
  explicit `--verify-frame-max N` for a bounded live run.
- The old "open compare image on divergence" behavior is now
  `--verify-frame-preview-on-diff`.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 173 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 5 --verify-frame-source both
# FRAME VERIFY OK frames=5
```

## 2026-06-13 hook verifier throughput pass

Improved `--verify-hooks` throughput without changing verifier coverage.

Follow-up after an interactive `play.py --verify-hooks --verify-stop-on-diff`
stall report:

- Headless cold-start verification reproduced a real verifier oracle problem:
  raw interpreted ASM for `1010:0679` can spin forever at the timer wait because
  the original busy-loop depends on IRQ0 advancing `CS:[066B]`.
- `HookVerifier._run_asm_to_target` now recognizes the original `0679/067F`
  timer wait and delivers the real installed OVERKILL INT 08h handler
  (`1010:06E5`) when `CS:[066B] == 0`.  This is not a synthetic fallback; it is
  the same game ISR the original wait loop is expecting.
- `scripts/play.py` now passes a verifier progress callback so the SDL status
  line shows the current hook being verified during long oracle runs.

Changes:

- `HookVerifier._clone_runtime` now copies the current memory image directly
  instead of allocating and zeroing a fresh full memory buffer before copying.
- `HookVerifier._range_diff` now uses a C-level `memoryview` equality check for
  identical ranges, and only walks bytes when a range actually diverges.
- Added a regression test proving the optimized range diff still reports a
  clean match, exact differing-byte count, and first differing address/value.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 171 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m overkill.cli snapshot assets\OVERKILL.UNLZEXE.EXE --game-root assets --steps 2000000 --verify-hooks --verify-max 1000 --out-dir artifacts\tmp_verify_hooks_cold_final
# HOOK VERIFY LIMIT REACHED verified=1000
```

Benchmark from `artifacts\snapshot_play_tandy_20260612_151523` with
`--verify-hooks --verify-max 200`:

```text
before: ~4583 ms
after:  ~574 ms
```

## 2026-06-12 PC speaker timing cadence fix

Investigated two sound-related Tandy snapshots:

- `artifacts/snapshot_play_tandy_20260612_151420`: level-select/menu state after
  pressing `D`.
- `artifacts/snapshot_play_tandy_20260612_151523`: gameplay state where Space
  produced firing sound but no visible projectile.

Findings:

- Both snapshots have the optional far sound-driver flag disabled
  (`DS:0055 == 0`), so the observed speaker writes come from the always-run
  timer helper path (`1010:06E5 -> D50E`), not the `[0055] == 1` far sound
  branch at `2032:0000`.
- Old synthetic timer versus new real-ISR timer produced the same video CRC and
  sampled object-table state after the Space input.  The "sound but no
  projectile" state therefore is not introduced by the PC speaker ISR change;
  it remains a gameplay/input-state investigation target.
- The sound-duration issue did expose a pacing mismatch: OVERKILL programs PIT
  divisor `0x4000`, so the ISR cadence is about `72.8 Hz`, and the `0679` wait
  normally releases every two ISR ticks, about `36.4 Hz`.  The interactive
  player default was still `30 Hz`, stretching timer-driven sounds by roughly
  20%.

Fix:

- `CPU8086.timer_ticks_elapsed` records how many real ISR ticks the `0679` hook
  delivered before `CS:066B` advanced.
- `scripts/play.py` now paces gameplay from PIT-tick units rather than assuming
  one synthetic frame tick.
- Default `--game-hz` is now `36.4`, matching the original effective timer
  cadence; internally the pacer runs at `--game-hz * 2` and sleeps for the
  delivered ISR-tick count.

Verification:

```text
python scripts\run_tests.py
# 141 passed, 0 failed
python scripts\play.py --snapshot artifacts\snapshot_play_tandy_20260612_151523 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
```

Note: `snapshot_play_tandy_20260612_151420` times out in the reference frame
verifier after frame 1 because it is in an input/menu wait path at `1010:D439`.

## 2026-06-12 AC97 object-slot scan lift

Absorbed the hot `1010:AC97` scan from
`artifacts/snapshot_play_tandy_20260612_192438` into
`overkill_object_slot_scan_ac97`.

Findings:

- The slowdown is a read-only gameplay object-slot loop body, not asset-codec
  work.
- It walks 35 records at `DS:23B4` with a `0038h` stride, one slot per hook
  call.
- It skips empty records and records with `+24h == 1` or `+20h == 1`.
- It performs the observed signed Y/X window checks and the `SS:[BP+14]`
  compare before advancing `BX/CX` and re-entering `AC97`.

Status:

- Hook lifted.
- Regression test added against `artifacts/evidence/ac97_stop`.

## 2026-06-12 BCB1 clamp leaf lift

Lifted the hot `1010:BCB1` clamp leaf from the BC4B post-move path.

Findings:

- The routine only clamps `SS:[BP+4]` into `0..00C0h`.
- It is a repeated leaf reached from the `BC4B` post-move path.
- The replacement returns to the `BC4E` continuation just like the original.

Status:

- Hook lifted.
- Regression test added against `artifacts/evidence/bc4b_stop`.

## 2026-06-12 BC4B post-move call-site lift

Absorbed the full hot `1010:BC4B` post-move call-site from the same gameplay
snapshot.

Findings:

- The block clamps Y, applies the X bounds, performs the BCCB contact check,
  folds the observed AA71 contact-window helper including the AAAB -> AA44
  upper tail, runs the optional BFC7 death tail, does the 9E69 bookkeeping,
  and finishes with the 62F6 overlap scan.
- The remaining 62F6 early exit for signed `SS:[BP+2] < 0x20` preserves the
  compare flags and incoming `BX`; it does not fall through to the empty-scan
  sentinel.
- The call-site was the last large interpreted block in that path.
- The hook now returns to the outer caller after completing the whole helper.

Status:

- Hook lifted.
- Regression test added against `artifacts/evidence/bc4b_stop`.

## 2026-06-12 AA71 upper contact tail lift

The same BC4B snapshot also hit the higher `1010:AA71` branch that survives
the signed X guard and then takes the `AAAB -> AA44` success tail.

Findings:

- The helper reuses the `SS:[BP+2] + 18h` compare against `DS:237E`.
- The path clears carry and returns without mutating object state.
- The negative X escape now also unwinds the `BCF9` return word after
  delegating to the shared `AA46` helper, matching the original call stack.
- The remaining unobserved AA71 branches stay fail-fast.

Status:

- Lifted into the shared contact-window helper.
- Regression test added against `artifacts/evidence/next_frontier_probe_4`.

## 2026-06-12 BFC7 shared C054 call for logic 003B

`snapshot_play_tandy_20260612_223501` reached `BC4B -> 62F6 -> BEC5 third counter zero -> BFC7` with `logic_id=003Bh`.  The original trace shows this is not a new bespoke branch: `BFC7` calls the shared `C054` selector before the state transition, and `003Bh` simply falls through to the default `AX=A4E4h` selector.  `C01B` then overwrites the flags with the `DS:98C0` compare and `C027` overwrites `AX` with the original logic id.

Status:

- `BFC7` now calls the shared lifted `C054` selector instead of whitelisting only `0012h/002Bh/0031h`.
- `003Bh` completes the same death/transition tail without decrementing `DS:A47E`.
- Regression test added for the `003Bh` path with `DS:98C0 != 0`.

## 2026-06-12 BFC7 no-counter branch lift

The `BFC7` death/transition tail now covers the current observed `0012h`,
`002Bh`, and `0031h` branches from the same BC4B snapshot.

Findings:

- Those branches take the same state transition as the verified death tail.
- None of them decrement `DS:A47E`.
- The replacement now keeps that family in the observed no-counter path instead
  of failing fast.

Status:

- Lifted into the shared collision tail.
- Regression tests cover the three observed logic ids.

## 2026-06-12 BD17/C054 dispatcher lift

The same BC4B tail also reaches `1010:BD17`, whose `C054` dispatcher now
selects the observed `0000h/0013h -> A4E4h` branch and preserves the `BD5F`
stack scratch below the final return word. The newer `draw_layer=5,
logic_id=0000h` path also returns cleanly after clearing the active flag, so it
is no longer a frontier either.

## 2026-06-12 BEC5 variant 000C tail lift

The same shooting path also reached `1010:BEC5` with `variant=000Ch`.

Findings:

- The BEC5 variant table routes `0007h`, `0008h`, `000Ch`, and `0009h` to the
  shared `BFB9` tail.
- Returning to the original interpreter at `BFB9` is enough to preserve the
  live state for that branch.
- The helper now preserves that branch instead of failing fast.

Status:

- Lifted as a shared-tail dispatch.
- Regression test added for the `000Ch` variant.

## 2026-06-12 BEC5 sprite 0033 BF21 continuation

The latest snapshot also hit the `sprite=0033h` branch inside `1010:BEC5`.
That branch falls through into the shared `BF25` counter logic in the original
code instead of failing fast, and the `third counter zero` tail then continues
through the shared `BF4B -> BFC7` score/death path.

Status:

- Hook updated.
- Regression tests added for the observed sprite fallthrough and `BF4B` tail.

Findings:

- The draw-layer-4 / `logic_id=002Bh` path clears the active flag, enters the
  C054 dispatcher, and the observed `0000h`/`0013h` selector branches return
  `A4E4h` without touching `DS:A47E`.
- The stricter fail-fast only belonged to the smaller counter-decrement family,
  not to the current gameplay snapshot.
- This removes the last crash in the current BC4B/BD17 tail without widening
  the hook to a guessed general rewrite.

Status:

- Hook updated.
- Regression test added for the observed `002Ah` fallthrough.

## 2026-06-12 BFC7 002B branch lift

The same BFC7 tail now also handles the observed `logic_id=002Bh` branch
without dropping `DS:A47E`.

Findings:

- The `0020h` branch remains the one that decrements the live counter.
- The current `002Bh` branch follows the same death/transition state update,
  but skips the counter drop.
- This removes the next crash from the current snapshot without guessing at a
  broad rewrite of the whole dispatcher.

Status:

- Hook updated.
- Regression test added for the observed `002Bh` no-counter path.

---

## 2026-06-12 PC speaker timer-ISR enablement

Enabled PC speaker sound during interactive play by letting the `1010:0679`
timer-wait hook run OVERKILL's installed INT 08h handler when the vector points
to the known game ISR at `1010:06E5`.

Findings:

- The speaker backend from the previous pass was correct, but normal play still
  produced no sound because `1010:0679` only synthesized `CS:066B`.
- Delivering the real INT 08h handler from
  `artifacts/play_tandy_main_menu_20260612_132548` produced the expected
  speaker writes: PIT mode `43h=B6h`, divisor bytes through `42h`, and speaker
  enable through `61h=03h`.
- The ISR chains the old BIOS timer every fourth tick via `JMP FAR CS:[0738]`.
  In this VM the saved BIOS vector can be `0000:0000`, so the hook stops at the
  known chain point after the game-side sound/tick work and restores the
  interrupt frame locally.

Changes:

- `1010:0679 overkill_wait_timer_tick_0679` now runs the original game timer ISR
  when INT 08h is installed as `1010:06E5`, delivering bounded real ISR ticks
  until the original `CS:066B` wait flag advances.
- If the expected ISR is absent, the hook fails fast; it no longer invents a
  synthetic `066B` tick.
- Added a regression using the Tandy menu snapshot that proves the timer hook
  emits `42h/43h/61h` speaker writes and safely handles the fourth-tick BIOS
  chain path.

Verification:

```text
python scripts\run_tests.py
# 128 passed, 0 failed
python scripts\play.py --snapshot artifacts\play_tandy_main_menu_20260612_132548 --verify-frames --verify-frame-max 40
# FRAME VERIFY OK frames=40
python scripts\play.py --snapshot artifacts\play_tandy_edrax_orbit_combat_20260611_232258 --verify-frames --verify-frame-max 40
# FRAME VERIFY OK frames=40
```

---

## 2026-06-12 Tandy gameplay rendering regression fix

Investigated `artifacts/snapshot_play_tandy_20260612_141644`, where gameplay
rendering broke after the PC speaker pass.

Findings:

- The PC speaker changes were not on the failing path: a 900K-instruction probe
  from the snapshot saw `0` reads of port `61h` and `0` writes to `42h/43h/61h`.
- Frame verification diverged at frame 48.
- Hook bisection showed the regression was `1010:33AF
  overkill_expand_tandy_list_33af`, not the recent sound/backend code.
- The composed `33AF` parent hook was only verified for the startup/header-table
  mode where `CS:[0BD8] != 0`.  This gameplay materialization snapshot reaches
  `33AF` with `CS:[0BD8] == 0`, where the original parent has different visible
  behavior.

Fix:

- `1010:33AF` now conservatively self-disables and falls back to original ASM
  when `CS:[0BD8] == 0`.
- The verified child block expander `1010:33B2` remains available, so the
  original parent can still dispatch into accelerated block expansion.
- Added hook-verifier metadata for `1010:33AF`.
- Tightened packed-stream/RLE side-effect fidelity found during the audit:
  `0615 -> 0624` nested calls now leave their original stack scratch, and
  `03A8` uses the shared word reader for its header words so `CS:0614` matches
  the interpreted oracle.

Verification:

```text
python scripts\play.py --snapshot artifacts\snapshot_play_tandy_20260612_141644 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
python scripts\run_tests.py
# 127 passed, 0 failed
```

---

## 2026-06-12 PC speaker hardware/backend pass

Added a narrow PC speaker path for interactive play:

- `dos.py` now tracks PIT channel 2 programming through ports
  `43h/42h` and the speaker gate/data bits at port `61h`.
- `scripts/play.py` bridges speaker state changes from the VM thread to SDL via
  a queue.
- `scripts/sdl_view.py` renders those events as a cached mono square wave using
  `pygame.mixer`.
- Added a core regression for the PIT channel 2 + port `61h` callback contract.

Important finding: current Tandy snapshots and the default inner-EXE command
tail still leave the `2032:0000` sound-driver slot as a tiny return stub and do
not emit speaker port writes during a short main-menu run.  The backend is ready
for real speaker writes, but audible game sound still depends on identifying the
sound-driver selection/loading path or lifting the proven `1010:06E5` timer ISR
sound call once that target is non-stub.

Verification:

```text
python -m py_compile dos.py tests\test_core.py scripts\play.py scripts\sdl_view.py
python scripts\run_tests.py
# 126 passed, 0 failed
```

---

## 2026-06-12 Tandy end-screen direct-video publish

Investigated `artifacts/play_tandy_the_end_20260612_001833`, where the
interactive viewer appeared frozen after the ending instead of showing the
high-score/name-entry flow.

Findings:

- Continuing the snapshot headlessly does not crash or remain at the snapshot
  entry.  The game advances from `1010:98FA` through the retrace-delay loop.
- In the following path, video memory changes directly: a 1M-step probe changed
  10,257 bytes in `B800h`.
- The hot path is interpreted text/glyph drawing around `1010:518C -> 3153`,
  which writes to `ES=B800` without hitting the usual Tandy present, timer, or
  retrace hooks after the initial delay.
- Because `scripts/play.py` previously published frames only at known
  present/timer/retrace boundaries, this looked frozen in the viewer even though
  the VM was drawing.

Fix:

- `scripts/play.py` now checks for changed visible video memory when a long run
  reaches the no-boundary frame budget.  If video changed, it publishes a
  "direct video" frame and treats that as a UI boundary.
- `scripts/sdl_view.py` reports the direct-video count in the window caption.
- Printable SDL keydowns are also bridged into the DOS key queue after the first
  direct-video publish, so late DOS character input such as `INT 21h AH=07h`
  name entry can receive typed characters without polluting the queue during
  normal gameplay controls.
- Follow-up from `artifacts/snapshot_play_tandy_20260612_131223`: a snapshot can
  start already inside the high-score/name-entry screen before this viewer
  session has counted any direct-video publish.  The DOS-key bridge is therefore
  also enabled while the CPU is in the observed high-score editor region
  `1010:5300..5650`, with a scancode-to-ASCII fallback for common printable
  keys and control keys when SDL provides no printable `unicode`.
- Follow-up from `artifacts/snapshot_play_tandy_20260612_131602`: the saved
  state is already late in the editor/submission path (`1010:55F1`) with the
  name buffer filled (`gttrfdffgg`), the name pointer at the 10-character limit,
  and the last editor character recorded as Enter (`DS:22B4=000D`).  Continuing
  that snapshot can therefore return to the menu because the name has already
  effectively been submitted, not because the VM has a stuck Enter key.
- Follow-up from `artifacts/snapshot_play_tandy_20260612_131812`: this snapshot
  starts before the high-score screen is fully drawn (`1010:32C5`).  Profiling
  1.5M steps shows the delay is pure interpreted text/direct-video drawing:
  `1010:518C`, `1010:3153`, and callers around `1010:32C5`; no replacement
  hooks fire.  This explains the slow appearance and marks the path as a future
  direct-video/text drawing lift candidate.
- The remaining "cannot type name" issue was caused by the deterministic
  headless DOS console fallback: `INT 21h AH=07h` returned Esc when no queued
  key was available.  In interactive `scripts/play.py`, DOS console input now
  blocks instead: the handler rewinds `IP` to the `INT 21h`, raises a narrow
  `ConsoleInputWouldBlock`, and the viewer yields a UI boundary until a real key
  is queued.
- Name-entry input then exposed the real missing VM service:
  `INT 10h AH=0Eh` BIOS teletype output.  The high-score editor reaches this as
  a bell (`AL=07h`) for rejected input.  `dos.py` now accepts this narrowly by
  recording the character in the stdout log rather than trying to render BIOS
  text over the graphics screen.

Verification:

```text
python -m py_compile dos.py scripts\play.py scripts\sdl_view.py
python scripts\run_tests.py
# 121 passed, 0 failed
```

---

## 2026-06-12 Tandy menu/redefine screen rendering pass

Investigated `artifacts/play_tandy_main_menu_20260612_132548`, where menu
subscreens such as ordering info, instructions, and redefine-keys felt slow.

Changes:

- `scripts/sdl_view.py` no longer treats Esc as a viewer quit key.  Esc is now
  forwarded to OVERKILL like the rest of the keyboard; close the SDL window to
  exit the viewer.
- Added `1010:306F overkill_tandy_rect_copy_306f`, the raw Tandy rectangle copy
  used by menu/high-score text screens.  This is a parent-level replacement for
  the formerly hot `307E` row loop.
- Added `1010:CDAA overkill_tandy_changed_dword_present_8rows_cdaa`, the Tandy
  dirty-present sibling of the existing `CD8D` CGA/EGA-ish changed-word
  presenter.

Verification:

```text
python scripts\run_tests.py
# 123 passed, 0 failed
```

Profiling notes:

- Before `306F`, `1010:307E..3094` dominated the interpreted menu/text copy
  path.  After the hook it disappears from the interpreted hot list.
- Before `CDAA`, `1010:CDAA..CDC8` was the next Tandy dirty-present loop.  After
  the hook it also disappears from the interpreted hot list.
- The remaining top interpreted loop from this snapshot is `1F8F:0960`, a compact
  far-overlay/menu counter loop.  It is not clearly part of the Tandy rendering
  island, so it was left untouched in this pass.

Follow-up from `artifacts/snapshot_play_tandy_20260612_134028`:

- The redefine-keys page itself was not slow because of rendering.  It was
  spinning in a pure keyboard wait:
  `1010:57AB cmp byte ptr DS:[98C3],00h` / `1010:57B0 jz 57AB`.
- `scripts/play.py` now treats this redefine-key wait as an interactive yield
  boundary when `DS:[98C3]` is still zero.  The runner publishes any changed
  video, pumps the UI, and retries after a real key event.
- The same handling covers the immediately following key-release wait at
  `1010:57DD/57E0`, where the game waits for `DS:[98C4 + DS:[98C3]]` to clear.
- This is deliberately not a global replacement hook: headless profiling and
  oracle runs still see the original wait loop.  The fix only prevents the live
  viewer from burning the full `--frame-budget` between redefine-key prompts.

---

## 2026-06-12 Tandy cold-start composition pass

Cold-start profiling with Tandy mode (`scripts/profile_hotspots.py --video
tandy`) showed that the largest remaining startup overhead before the next VM
frontier was not another codec, but the interpreted Tandy startup list driver:

```text
1010:33AF -> call 44D7 header reader -> 1010:33B2 block expander
```

`33B2` was already a verified hook, but startup still interpreted hundreds of
small `44D7` header reads and hook boundaries.  Added:

- `1010:33AF overkill_expand_tandy_list_33af`, a parent-level Tandy startup
  list hook that composes the `44D7` header reader with the existing `33B2`
  block expander until the zero-header terminator jumps to `44AA`.
- Full-memory synthetic oracle coverage for a two-block list plus terminator.
- A stack-scratch correction in the existing `33B2` helper for the nested final
  `344B` call return word (`341B`).

Profiling effect before the same startup frontier:

- before: `33B2` hook called 686 times and the interpreted hot list was dominated
  by `33AF/44D7/450A`;
- after: `33AF` hook called 9 times, `33AF/44D7/33B2` disappeared from the
  interpreted hot list, and total hook invocations before the frontier dropped
  from 1,048 to 371.

The same profile then exposed unsupported 8086 opcode `98h` at `1010:0008`;
implemented narrow `CBW` support in `cpu.py` (sign-extend `AL` into `AX`, flags
unchanged).  With `CBW`, a 1M-step cold Tandy profile reaches normal
menu/gameplay-heavy code.  The remaining top non-hook loop is `1F8F:0960`, which
does not clearly belong to the current asset/rendering islands and was left
untouched.

---

## 2026-06-12 Instructions/order overlay wait

Investigated `artifacts/snapshot_play_tandy_20260612_140352`, captured from the
instructions screen after it appeared slow to load.

Finding:

- The snapshot is already inside the loaded overlay segment (`1F8F:09B7`), not in
  file IO, decompression, or startup materialization.
- Profiling 1M steps showed zero hooks and 100% interpreted time in
  `1F8F:099B..09DF`, a tight key-state wait loop.  It checks menu/action key
  bytes such as `DS:990F`, `990C`, `990D`, `98D2`, `9911`, `9914`, `9915`,
  `98FD`, `98E0`, and `98C5`.
- `scripts/play.py` now recognizes this overlay wait by code signature and
  yields the interactive UI immediately while all watched key bytes are idle.
  This is not a loader hook and not a global replacement; it only prevents the
  live viewer from burning the full frame budget while instructions/order screens
  wait for input.

Verification:

```text
python scripts\run_tests.py
# 125 passed, 0 failed
```

---

## 2026-06-12 Timeless top-level documentation pass

Refactored project-facing docs so durable guidance is separated from living
status:

- `AGENTS.md` now contains stable agent/human workflow rules: project purpose,
  proof obligations, hook mechanics, verification expectations, source-port
  islands, artifact policy, and things not to do.
- `README.md` now reads as stable onboarding: goals, non-goals, local game-file
  expectations, project layout, quick-start commands, verification workflow,
  source-port island model, and documentation map.
- `docs/overkill/design.md` now describes runtime architecture and design pressure
  without embedding old checkpoint progress or tactical next targets.

Current facts, recent commands, and next tactical targets should remain in
`docs/overkill/run_status.md`; durable address-level findings remain in
`docs/overkill/runtime_findings.md`.

---

## 2026-06-12 Existing-island exhaustion audit tooling

Added `scripts/audit_islands.py` to make island closure visible instead of
purely conversational.  The script groups currently registered hooks into the
already-created OverKill islands:

- asset codecs / startup materialization
- overlay loading / overlay decode / overlay directory scan
- startup graphics expansion
- coordinate/address helpers
- shared layer sprite dispatch
- Tandy-specific rendering primitives

For each island it reports hook-verifier metadata coverage, obvious
oracle/regression test mentions, `symbols.json` entries that still advertise a
candidate/frontier/unverified/fallback state, explicit module seam markers such
as bounded original fallbacks, and optional trace hits.

Useful commands:

```text
python scripts\audit_islands.py
python scripts\audit_islands.py --all-hooks
python scripts\audit_islands.py --json
python scripts\audit_islands.py --trace artifacts\some_trace.txt
```

Current audit result:

- `startup_graphics` reports `closed-candidate`: all known hooks in that island
  have verifier metadata and test mentions, and the script found no explicit
  seam markers or open symbols.
- `asset_codecs` now reports `closed-candidate`: the remaining
  `1010:0324` word-pair RLE candidate has been lifted, verified, and marked
  replaced.
- `overlay` remains open because `254A:05A1` and `254A:05D9` need direct test
  mentions and `254A:04D7` is still marked as an active parent-loader
  investigation target.
- `coordinates` remains open because the coordinate module still contains an
  explicit unverified-path seam.
- `layer_sprites` remains open because it still has bounded-original/fail-fast
  seams and an open `1010:75A6` frontier symbol.
- `tandy_rendering` remains open because several hooks lack obvious direct test
  mentions.

Important limitation: `closed-candidate` is a closure signal, not proof that no
unknown behavior exists.  It means the known source-port island has no
script-detected blockers left and should then be checked with live hook
verification and representative Tandy traces.

Hook-verifier metadata was also filled in for the existing-island hooks that now
have clear boundaries, including overlay far-return handling for `254A:0701`.
A small regression pins the far-return stop metadata behavior.

Verification:

```text
python -m py_compile scripts\audit_islands.py overkill/verification.py
python scripts\run_tests.py
# 119 passed, 0 failed
```

---

## 2026-06-12 Asset-codec closure: 1010:0324 word-pair RLE

Closed the last audit blocker in the non-overlay `asset_codecs` island:

- `1010:0324` is a word-pair RLE decoder, sibling to the already lifted
  `1010:0367` byte-linear and `1010:03A8` vertical RLE decoders.
- The stream starts with a sentinel word read through the packed `0615` reader.
  Non-sentinel words are literal two-word pairs.  Sentinel words introduce a
  repeat count; count zero exits to the shared loader continuation at
  `1010:02A8`, and nonzero counts repeat the following two-word pair.
- The implementation lives in
  `overkill/asset_codecs/rle.py` as
  `decode_word_pair_rle`, with a thin `overkill/hooks.py` hook wrapper.
- The shared packed byte reader now preserves the original fast-path carry:
  `0624` does `CMP BX,0610h`, takes the below-buffer branch with `CF=1`, and
  the later `INC word ptr [0610]` preserves that carry.
- The oracle test covers literal, repeat, and terminator paths, including final
  registers, flags, output words, packed-stream scratch, byte count, and stack
  scratch around `SS:SP`.

Audit result after this pass:

```text
asset_codecs      closed-candidate  hooks=10
startup_graphics  closed-candidate  hooks=7
```

Verification:

```text
python scripts\run_tests.py
# 119 passed, 0 failed

python scripts\audit_islands.py --all-hooks
# asset_codecs and startup_graphics report closed-candidate
```

---

## 2026-06-12 Existing-island audit: overlay signature loop

Audited remaining candidates against the already-created OverKill islands
(`asset_codecs` and `rendering`) and intentionally avoided opening new gameplay
areas.

Lifted one clear overlay-loader subloop:

- `254A:0582` belongs to the existing `asset_codecs.overlay` island.  It is the
  bounded header/signature compare loop after the parent loader reads the
  twelve-byte overlay/container header.  The Python implementation now lives in
  `overkill/asset_codecs/overlay.py` as
  `compare_overlay_signature_0582`, with a thin hook wrapper in
  `overkill/hooks.py`.
- Continuations are preserved exactly: full match goes to `254A:058D`; first
  mismatch goes to `254A:0640`.
- Added an interpreted-ASM oracle regression covering both exits.

Audit decisions:

- `254A:04D7` is clearly overlay loading, but it is a larger file-open/read/seek
  parent.  It should not be lifted wholesale until more of its small deterministic
  loops are closed.
- `1010:B73E/BC4B/62F6/BEC5` are gameplay/contact helpers, not part of the six
  requested islands, so they were left alone.
- The remaining CGA/EGA bounded layer compositor allow-list belongs to the shared
  layer-sprite rendering island, but it is not Tandy-specific and would be a
  broad rendering sweep; left untouched in this focused pass.

Verification:

```text
python scripts\run_tests.py
# 117 passed, 0 failed
```

---

## 2026-06-11 Tandy B73E formation/contact continuation

Closed the later formation-change divergence from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

- The original frame-383 path for object `BP=2814` is
  `B73E -> B77B -> BC4B -> BCCB -> AA46/8331 -> BFC7`, not a `62F6`
  overlap collision.  `AA46` sets carry when the object is inside the
  view/contact rectangle; the replacement previously checked only X and always
  cleared carry, so the object stayed alive in logic `20h`.
- `_run_view_window_check_aa46` now mirrors the full X/Y rectangle test and
  preserves the carry-set contact result.
- `_run_object_postmove_bc4b` now composes the carry-set `BCCB` path: optional
  `BFC7` death/logic-transition tail, observed `9E69` bookkeeping, then the
  normal `62F6` call.
- `_run_object_overlap_scan_62f6` now preserves `BX` on the early
  `logic_id == 0001` return, matching the original post-death scan.
- Added an interpreted-ASM regression for the exact `B77B` contact-death tick.

Verification:

```text
python scripts\run_tests.py
# 113 passed, 0 failed

python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 500
# FRAME VERIFY OK frames=500
```

---

## 2026-06-11 B73E/BEC5 gameplay continuation

Closed two user-reported Tandy gameplay stops from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`:

- Shooting enemies reached `B73E -> B7BD -> BC4B -> 62F6 -> BEC5 fourth
  counter zero`.  The observed `BFC7` death/transition tail now handles the
  type-1, no-linked-slot path: score add via the `5F0D` BP/SS decimal helper,
  Y clamp, logic transition `20h -> 1`, previous logic saved in `+1A`, `+22`
  cleared, and the type-1 sprite-zero dispatch.
- Passive play reached `B73E -> B7BD -> B7F3`, then the follow-up
  `B73E -> B7BD -> B82D -> B7BD` waypoint-loop case.  The verified branches now
  cover the `B7F3 -> B7C9` target-reset path, substate-0 `B754` movement path,
  and the bounded `B82D` waypoint-table loop.

Important correction while verifying: the `B7C9` target reset always produces
the observed target Y from `DS:2380 + 8` before alignment; a branch-counting
guess that preserved the old target caused frame-266 divergence.

Verification:

```text
python scripts\run_tests.py
# 111 passed, 0 failed

python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 300
# FRAME VERIFY OK frames=300
```

The key correction for the waypoint loop: `B82D` does not move immediately after
selecting a different waypoint.  It updates `+34/+32` from the table and falls
through to `BC4B`; movement happens on a later target-mismatch tick.

---

## 2026-06-11 Tandy layer-0 scan fix: A894 stops at CALL A8BE

User-reported gameplay from `artifacts/play_tandy_edrax_orbit_combat_20260611_214016`
hit the layer-0 draw scan with an active layer-0 object:

```text
1010:A894: partial scan reached unlifted CALL at A8BE
BP=2884 active=0001 layer=0000 type=0001 draw_layer=0005
```

This was a boundary bug in the shared partial-scan helper.  The `1010:A894`
hook is supposed to skip non-calling iterations and stop immediately before the
real `CALL` for the first drawable object.  Instead, `_scan_loop_until_callable`
still used the older fail-fast behavior.

Fix:

- `_scan_loop_until_callable` now preserves the loop `PUSH CX` scratch and leaves
  `CS:IP` at the real call instruction (`1010:A8BE` for `A894`).
- Added a synthetic interpreted-ASM oracle test for the active layer-0 path,
  comparing the original bytes through `A8BE` against the hook state.

Verification:

```text
python scripts\run_tests.py
# 108 passed, 0 failed

python scripts\play.py --snapshot artifacts\play_tandy_edrax_orbit_combat_20260611_214016 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
```

---

## 2026-06-11 Tandy gameplay crash fix: BEC5 BEDC=0001 collision tail

User-reported manual gameplay from
`artifacts/play_tandy_black_panel_20260611_192528` crashed while shooting spawned
ships:

```text
B73E -> B73E -> B7BD -> BC4B -> 62F6 -> BEC5 BEDC=0001 -> BF5E
```

The branch was real gameplay execution, not a renderer path.  Re-reading the
original bytes showed that `DS:BEDC == 0001` does not return immediately: it
jumps into the tail at `1010:BF4D`, decrements `SS:[BP+20]` once more, writes
`SS:[BP+24]=0005`, compares `DS:A8C2` with `0001`, and then returns at
`1010:BF5E` when `A8C2 != 0001`.

Fix:

- `1010:BEC5` observed variant-2 collision helper now implements the verified
  `BEDC=0001` tail instead of fail-fasting or returning early.
- The remaining zero-counter and `A8C2=0001` branches stay fail-fast with
  concrete target addresses.
- Added a synthetic interpreted-ASM oracle test for the `BEDC=0001` tail.

Verification:

```text
python scripts\run_tests.py
# 107 passed, 0 failed

python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60

python scripts\play.py --snapshot artifacts\play_tandy_black_panel_20260611_192528 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
```

---

## 2026-06-11 frame-verify regression fix: AA2B/EFAE back to dispatch-only

User-reported frame verification diverged at frame 34 from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`:

```text
python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 60
```

Bisecting with `OVERKILL_DISABLE_HOOKS` showed:

- Disabling all non-frame hooks passes 60 frames.
- Disabling only the recent layer/draw hooks did not change the bad CRC.
- Disabling `1010:AA2B,1010:EFAE` alone restores 60-frame verification.

Root cause: `AA2B` and `EFAE` had crossed from dispatch-stub replacements into
inline gameplay behavior execution. Synthetic/local verifier boundaries did not
catch the later frame-level drift.

Fix:

- `1010:AA2B overkill_object_logic_dispatch_aa2b` is now dispatch-only: it
  mirrors `mov bx,ss:[bp+16]; shl bx,1; jmp cs:[bx+AA36]`.
- `1010:EFAE overkill_object_family_dispatch_efae` is now dispatch-only after
  preserving the real prologue writes to `DS:D1FE` and `DS:D200`, then jumps
  through `CS:EFC4`.
- Hook verifier metadata now stops at the selected dispatch target for both
  hooks, not at the caller return.
- Added synthetic ASM oracle coverage for both dispatch boundaries.
- `scripts/run_tests.py` now provides a tiny `pytest.raises` shim when pytest is
  unavailable, keeping the local pytest-free runner usable.

Verification:

```text
python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60

python scripts\run_tests.py
# 106 passed, 0 failed
```

---

## 2026-06-11 island-closure continuation: movement/collision/draw/layer frontier

Continued the fail-fast “close the island before expanding” pass from the previous
object-logic frontier.  The run no longer stops at `5DB2`; the currently opened
Tandy/object island now includes movement, the observed collision branch, more
first-level object logic, and several adjacent Tandy draw/layer targets.

New structural lifts in this pass:

- `1010:5DB2`: target-seeking movement/direction helper, including observed
  `AF60` double 2-pixel step and `AEE4` 8-pixel step modes.
- `1010:8D4F`: observed `logic_id=1Fh` waypoint/target-patrol branch through the
  far-call waypoint reader and `5DB2`.
- `1010:BEC5` observed branch: collision with a `+18h == 0002` object now
  deactivates the collided slot and updates the moving object's `+20h/+24h` state
  instead of stopping at the collision handler.
- `1010:AB10`: first-level AA2B target that updates object sprite/position from
  the `A40C/A414` tables.
- `1010:AED8`: observed `logic_id=2` movement/tile-probe branch, including the
  `AEE4 -> B250 -> AD5A -> 5073/505B` path and the observed out-of-bounds
  deactivation through `BD17`.
- `1010:356C`, `1010:3657`: additional Tandy draw targets reached by the composed
  `A849/A861 -> 5AC8` draw scans.
- `1010:A861`: overlaid `8D12` draw scan now composes verified `5AC8` Tandy draw
  targets instead of stopping before the call.
- `1010:7746` and `1010:2FB6`: compact layer draw setup and its two-word masked
  Tandy compositor, reached by `A87C`.
- `1010:A87C`: active-object scan over `8D12` now composes the verified `7746`
  compact layer draw path.

Current intentional frontier from `artifacts/play_tandy_edrax_orbit_combat_20260611_164810`:

```text
1010:A8C7 -> 7596 -> 75A6
```

This is useful new information: the already-opened layer pipeline now reaches the
`75A6` split/two-destination layer draw helper.  It should be lifted next rather
than adding a fallback.

Verification:

```text
python -m pytest -q                         # 103 passed
python -m compileall -q dos_re overkill scripts tests
python - <<'PY'                              # symbols.json parses
import json; json.load(open('symbols.json'))
PY
```

---

## 2026-06-11 fail-fast object logic frontier

The fail-fast no-fallback pass continued past the previous stop at
`1010:A9E0 -> AA01 -> AA2B`.

New structural lifts:

- `1010:A9E0`: object-logic scan over `DS:32CA`, including `DS:2340` counter side effect.
- `1010:AA10`: object-logic scan over `DS:8D12`.
- `1010:AA2B`: first-level object logic dispatch by `SS:[BP+16]` / `CS:AA36`.
- `1010:EFAE`: second-level object family dispatch by `SS:[BP+18]` / `CS:EFC4`.
- `1010:B73E`: observed `logic_id=20h` branch lifted to the next concrete helper.

Current intentional frontier from `artifacts/play_tandy_edrax_orbit_combat_20260611_164810`:

```text
1010:A9E0 -> AA2B -> EFAE -> B73E -> B85C -> B729 -> 5DB2
```

Verification:

```text
python -m pytest -q                         # 102 passed
python -m compileall -q dos_re overkill scripts tests
python - <<'PY'                              # symbols.json parses
import json; json.load(open('symbols.json'))
PY
```

Next best RE target: `1010:5DB2`, the movement/direction helper that compares the
object position against `DS:2304/2306`, writes `DS:A954` / `DS:230A`, XLATs through
`DS:A348`, and then dispatches via `CS:5E0C` according to `DS:2308`.

---
# Checkpoint: A90F/5A92 present-scan lift (fail-fast follow-up)

Continuing from the no-fallback run, the first exposed target was not worked around.
`1010:A90F` has now been lifted as a real parent present scan over the `DS:8D12`
object table. Active entries compose through `5A92` when their Tandy present target
is verified.

New verified present targets discovered from this path:

- `1010:3542` — 8-row/two-word Tandy present copy with `DI += 0064h`.
- `1010:34AD` — split present copy: optional first `34C5`, then
  `SS:[BP+10]` / `SS:[BP+0E]+0140h` tail into `34C5`.

`A927` now uses the same shared present-scan helper, so both `32CA` and `8D12`
present scans compose known `5A92` targets and fail fast on truly unknown ones.

Validation:

- `python -m pytest -q` -> 102 passed.
- `python -m compileall -q dos_re overkill scripts tests` -> passed.
- `symbols.json` parses.
- Replaying `artifacts/play_tandy_edrax_orbit_combat_20260611_164810` now gets past the
  previous `A90F -> A91E -> 5A92` stop and past the newly discovered `3542`/`34AD`
  present targets. The next intentional fail-fast target is now
  `1010:A9E0 -> AA01 -> AA2B`, object `BP=2734`, `CX=0011`, `type=0001`,
  `draw_layer=0004`, `sprite=007A`.

Next RE target:

- Reverse/lift the `1010:A9E0 -> AA01 -> AA2B` object/gameplay dispatch path.

---

# Checkpoint: fail-fast replacement policy (no ASM fallback masking)

This pass removes the conservative unknown-target fallbacks from composed replacement hooks.
The project goal is reverse engineering, not short-term playability, so unknown dispatch
paths now raise a diagnostic `RuntimeError` instead of returning to the interpreted ASM
pre-call boundary. Runtime-patched hook signatures also fail fast instead of silently
unregistering the hook and continuing through the original bytes.

Changed behavior:

- `1010:A849` now raises on unverified `A849 -> 5AC8 -> target` paths instead of
  stopping at `A858`.
- `1010:A927` now raises on unverified `A927 -> 5A92 -> target` paths instead of
  stopping at `A936`.
- `1010:A8C7` now raises on unverified `A8C7 -> 7596` or nested
  `A8C7 -> 7596 -> 768E -> target` paths instead of stopping at `A8F1`.
- `1010:768E` now raises on unknown Tandy sprite compositor targets instead of
  tail-dispatching to original code.
- Partial scan hooks using `_scan_loop_until_callable` now raise when they reach an
  active object requiring an unlifted call. They still complete skip-only scans.
- `5A36` and shared `5A00/5A24` coordinate dispatch helpers now raise on unverified
  video modes rather than jumping into original target code.

Validation:

- `python -m pytest -q` -> 99 passed.
- `python -m compileall -q dos_re overkill scripts tests` -> passed.
- `symbols.json` parses.
- Continuing `artifacts/play_tandy_edrax_orbit_combat_20260611_164810` now intentionally stops
  after 3 instructions at the next unknown RE target:
  `1010:A90F` partial scan reached unlifted call `A91E` with object `BP=2CAC`,
  `CX=0007`, `type=0000`, `sprite=0032`, `di=537A`, `present_si=9418`.

Next RE target exposed by fail-fast policy:

- Reverse/lift the `1010:A90F -> A91E -> 5A92` present/object scan path instead of
  allowing the old skip hook to fall back into ASM.

---

# Run status — checkpoint 31

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Crash regression snapshot:
`artifacts/play_tandy_edrax_orbit_combat_20260611_164810`.

This pass fixes the gameplay crash at `1010:A8C7` without treating `2F40` as an
unknown fallback case.  The deeper issue was that `1010:768E` is a
setup/tail-dispatch helper, and the crash snapshot exercised a real Tandy
compositor target that had not yet been lifted:

- `1010:2F40 overkill_tandy_or_inverted_mask_2f40`

## Tandy compositor target 2F40

`2F40` is a four-word, 16-row Tandy layer compositor.  It is not the same masked
copy shape as `2F81`: each row consumes four source cells as
`MOV AX,[SI]; NOT AX; OR ES:[DI],AX; ADD SI,4; ADD DI,2`, then advances the
destination by `0060h`.  In game terms this is an inverted-mask OR pass used by
some layer sprites.

The new hook preserves the original `BX=0060h`, `CX` loop, `SI`/`DI` advancement,
final flags from the last row `ADD DI,BX`, `DS=CS:[9596]` restoration, and `RET`
behavior.  `768E` and the composed `A8C7` scan now treat `2F40` as a verified
child target alongside `2F81` and `2E6E`.

`A8C7` still predicts the nested `768E` compositor before composing the scan, but
that fallback is now only for genuinely unverified nested targets; the observed
`2F40` path is executed and verified rather than skipped.

## Verification

- Crash snapshot replay from `play_tandy_edrax_orbit_combat_20260611_164810`: 50,000
  instructions without the old `768E layer draw returned to unexpected IP 2F40`
  crash.
- Synthetic interpreted-ASM oracle now covers `768E -> 2F40`.
- Synthetic `A8C7` parent-scan oracle now covers full composition through
  `7596 -> 768E -> 2F40`.
- Live verifier from the crash snapshot:
  - `A8C7`: 20 real calls, no divergence.
  - `768E`: 1 real nested `2F40` call in the replay window, no divergence.
- Full test suite: `99 passed`.
- `py_compile`: passed.

---

# Run status — checkpoint 30

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Current Tandy gameplay snapshot:
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

This pass moved one level higher in the Tandy layer-1 draw pipeline:

- `1010:768E overkill_tandy_layer_sprite_draw_768e`
- `1010:A8C7 overkill_scan_layer1_draw_a8c7`

## Layer-1 draw composition

`1010:7596` is a small object-type dispatcher.  Its hot Tandy layer-1 path
dispatches object type 1 to `1010:768E`, which sets up the source segment/table,
destination pointer, mode/phase compositor table, row count, and then tail-jumps
to the verified Tandy sprite compositor (`1010:2F81` in the current snapshot).

`768E` is now a verified setup/tail-dispatch helper.  It handles:

- `DI=FFFF` early return.
- Known compositor targets `2F81` and `2E6E` by running verified children.
- Unknown compositor targets by tail-dispatching back to the original target.

`A8C7` now composes the layer-1 scan when the active object's `7596` target is
the verified `768E` path.  It preserves the original layer filter, `PUSH CX`,
`CALL 7596`, `POP CX`, and `LOOP` behavior.  If an active object dispatches to an
unverified `7596` target, the hook falls back before the original call at
`1010:A8F1`.

## Verification

- Added interpreted-ASM oracle tests for `768E` complete, early-return, and
  fallback paths.
- Added interpreted-ASM oracle tests for `A8C7` complete and fallback paths.
- Live hook verifier from `snapshot_play_tandy_20260611_152751` covered:
  - `768E`: 800 real calls, no divergence.
  - `A8C7`: 500 real layer-1 scan calls, no divergence.

## Current profile shape

The layer-1 pipeline no longer appears as repeated interpreted
`A8C7 -> 7596 -> 768E -> 2F81` crossings in the common Tandy path.  The remaining
hot interpreted work is now strongly concentrated in shared object/gameplay code:

- `1010:A9E0 -> AA2B`
- `1010:EFAE` object routine dispatch
- `1010:BC4E` / nearby shared update/collision-style logic

Those should be treated as gameplay/object reconstruction targets rather than
rendering helpers.

---

# Run status — checkpoint 29

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Current Tandy gameplay snapshot:
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

This pass composed two verified small-hook clusters into full object scan passes
for the common Tandy first-level object table.

## Composed object scan hooks

Updated:

- `1010:A927 overkill_scan_objects_call_5a92_a927`
- `1010:A849 overkill_scan_objects_call_5ac8_a849`

Both routines still preserve the old conservative behavior when they encounter
an unverified dispatch target: they stop at the original pre-call boundary
(`A936` for `A927`, `A858` for `A849`).  When all active objects dispatch to the
verified Tandy targets, they now run the whole scan loop and return at the loop
exit (`A93C` / `A85E`).

The composed paths reuse the already verified smaller operations:

- `A927 -> 5A92 -> 34D8/34C5`
- `A849 -> 5AC8 -> 35CC/35AA`

They preserve the original `PUSH CX`, `CALL`, `POP CX`, `LOOP` stack scratch and
flag behavior instead of inventing a higher-level object API.

## Verification

- Added interpreted-ASM oracle tests for complete and fallback paths of both
  composed scan hooks.
- Live hook verifier from `snapshot_play_tandy_20260611_152751` covered:
  - `A927`: 750 real full-scan calls, no divergence.
  - `A849`: 760 real full-scan calls, no divergence.

## Current profile shape

With both 32CA scan passes composed, a 3M-step Tandy first-level profile drops
the repeated `A849/A927 -> 5AC8/5A92 -> 35CC/34D8` interpreter crossings.  The
remaining hot interpreted areas are now mostly shared behavior:

- `1010:AA2B` / `EFAE` object dispatch/update paths.
- `1010:BC4E` and nearby shared gameplay code.
- `1010:A8C7 -> 7596 -> 768E` layer-1 draw pipeline.

These are the next good characterization targets, with preference for lifting a
whole pipeline once the boundary is proven.

---

# Run status — checkpoint 28

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Current Tandy gameplay snapshot:
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

This pass continued from the Tandy first-level snapshot and lifted the next
highest-impact verified Tandy gameplay blocks, favoring parent/block-level hooks
over tiny leaves.

## Tandy gameplay hooks

Added verified hooks:

- `1010:2F81 overkill_tandy_masked_sprite_composite_2f81`
- `1010:2E6E overkill_tandy_masked_sprite_composite_2e6e`
- `1010:34C5 overkill_tandy_strided_copy_34c5`
- `1010:35AA overkill_tandy_source_strided_copy_35aa`
- `1010:34D8 overkill_tandy_small_strided_copy_34d8`
- `1010:35CC overkill_tandy_draw_object_block_35cc`

Also folded the Tandy mode-2 row-address target `1010:30D2` into the existing
`1010:5A36` dispatch hook, so mode 0/1/2 now return at the caller boundary while
unknown modes still dispatch to the original table target.

`35CC` is deliberately a composed parent hook: it calls the verified `5A36`
row-address replacement internally, mirrors the original `CALL 5A36` stack
scratch, then performs the Tandy source-strided copy as one routine.

## Verification

- Added interpreted-ASM oracle tests for all new Tandy gameplay hooks, including
  the composed `35CC -> 5A36 -> 30D2` path.
- Live hook verifier from `snapshot_play_tandy_20260611_152751` covered:
  - `2F81/2E6E/34C5/35AA/5A36`: 2,000 mixed real calls, no divergence.
  - `34D8`: 500 real calls, no divergence.
  - `35CC/34D8/5A36`: 1,500 mixed real calls, no divergence.

## Current profile shape

`python scripts/profile_hotspots.py 3000000 --video tandy --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --top 35`
now shows the Tandy-specific sprite/copy work as hooks. The remaining real
interpreted heat has shifted toward shared object/gameplay logic:

- `1010:AA2B` dispatch/helper path
- `1010:EFAE` object routine dispatcher
- `1010:BC4E` / `BCxx` shared gameplay paths
- smaller draw target work around `1010:768E`

Those are the next best candidates, but they should be lifted only after their
entry/exit contracts and call families are characterized.

---

# Run status — checkpoint 27

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  Local pytest-free runner:
`86 passed, 0 failed`.

This pass switches the interactive/profiling default video mode to Tandy and
adds verified Tandy startup-expander hooks for the slow packed-pixel asset path.

## Tandy default

- `scripts/play.py` now defaults to `--video tandy`.
- `scripts/profile_hotspots.py` now defaults to `--video tandy`.
- `README.md` now documents Tandy as the default interactive path.

## Tandy startup-expander hooks

Profiling showed Tandy startup was spending most of its time in the live-patched
`1010:33B2 -> 33DD -> 344B` packed-pixel block renderer.  This is the Tandy
analog of the already-hooked EGA `4511/4537/45F6` startup expander.

Added:

- `1010:33DD overkill_expand_tandy_cell_33dd`
- `1010:33B2 overkill_expand_tandy_block_33b2`

The `33B2` hook is guarded by live-byte signature because this code region is
runtime-patched.  It preserves the original normal continuation (`1010:33AF`),
terminator branch (`1010:44AA`), `SI`/`DI`/`CX` loop effects, flags, output
writes, and final stack scratch words from the original call frame.

## Verification

- Added interpreted-ASM oracle tests for `33DD`, `33B2`, and the `33B2` zero/
  terminator branch.
- Added hook-verifier continuation metadata for `1010:33B2` and `1010:33DD`.
- Live differential verification covered all 686 real `1010:33B2` calls reached
  in the current Tandy startup profile with no divergence.
- Full local test runner: `86 passed, 0 failed`.

## Profiling note

`python scripts/profile_hotspots.py 6000000 --video tandy --top 10` now shows
`1010:33B2` as 686 block-level hook calls instead of the previous interpreted
`33B2/33DD/344B` loop tree.  After replacing the internal 344B rotate simulation
with direct bit packing, `33B2` is about `0.57s` total / `0.83ms` per block in
the same profile.  The run still stops later at the pre-existing
`Unsupported opcode 98 at 1010:0008`; a control run with `1010:33B2` disabled
hits the same stop, so it is not caused by the new hook.

## Viewer polish

The SDL viewer window is now resizable/maximizable.  Frames are centered at the
largest integer scale that fits the current window, preserving the 320x200 aspect
ratio with black bars as needed.

---

# Run status — checkpoint 26

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `65 passed` *at this checkpoint*.

> **Note:** this checkpoint is not the latest state.  Work after checkpoint 26
> (EGA planar-correctness fixes, the masked-sprite/perf pass, the overkill/hooks.py
> hook de-duplication, and the 2026-06-11 EGA gameplay-profiling passes that added
> the verified `1D1B` and wide `13E7` bit-spread composite hooks — together ~17%
> then a further ~33% faster in-level play) is recorded in
> [`docs/overkill/runtime_findings.md`](runtime_findings.md); the full suite is now
> `82 passed`.

This pass continued profiling the slow planet/difficulty selection screen that is
shown after pressing SPACE in the main menu.  The earlier menu hooks helped, but
profiling showed that this screen was now dominated by overlaid masked-sprite
compositors and object dispatch stubs rather than asset decompression.

## Performance finding

After re-enabling the dirty-copy hooks and adding the previous `4D15` fix, the
next hot interpreted path was the overlaid masked sprite drawing code around
`1010:3EFB`.  This routine is used heavily by the selection highlight/sprite
redraw path and performs many `RCR`/`SHR` chains per row.

The addresses around `3EE1`/`3EFC` are reused by overlays, so hooks in that area
must verify the resident bytes before applying.  A non-guarded row-copy hook can
accidentally intercept a different overlaid compositor body.

## Fixes / hooks

- Added `1010:3E12 overkill_masked_sprite_composite_3e12`, collapsing the hot
  two-shift masked CGA sprite compositor used by the level-selection redraw.
- Added guarded strided-row-copy hooks for `1010:3EE1` and `1010:3EFC`.  These
  only run when the exact row-copy bytes are resident; otherwise they fall back
  to the interpreter for the current overlaid instruction.
- Added `1010:3EFB overkill_masked_sprite_composite_3efb`, collapsing the
  overlaid six-shift masked sprite compositor that became the dominant interpreted
  loop on the selection screen.
- Added fast dispatch hooks for `1010:5AC8` and `1010:5A92`, removing repeated
  interpreted mode/subtype dispatch overhead before the existing draw/present
  hooks take over.
- Added `1010:AA44 overkill_clc_ret_aa44` for the tiny hot success helper.
- Kept the earlier live-player hook policy change: dirty-copy hooks are enabled
  in interactive CGA, while the mode-0-only `58DF` hook remains disabled for
  non-CGA modes.

## Verification

Added oracle tests comparing the new hooks against interpreted ASM snippets:

- `test_masked_sprite_composite_3e12_hook_matches_interpreted_asm`
- `test_strided_row_copy_3ee1_and_3efc_hooks_match_interpreted_asm`
- `test_masked_sprite_composite_3efb_hook_matches_interpreted_asm`
- `test_dispatch_5ac8_and_5a92_hooks_match_interpreted_asm`
- `test_clc_ret_aa44_hook_matches_interpreted_asm`

Full result:

```text
65 passed in 2.95s
```

A 1.5M-step CGA profile now reaches further into the menu/gameplay rendering
path within the same step budget.  `1010:3EFB`, `1010:5AC8`, `1010:5A92`, and
`1010:AA44` are now replacement hooks instead of interpreted hot loops.

---

# Current run status — checkpoint 25

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `56 passed`.

This pass targeted the very slow menu/planet-selection renderer path shown by
profiling the live CGA menu loop after startup.

## Performance finding

With the interactive-safe hook set from checkpoint 24, the hottest interpreted
routine on this screen was `1010:4D15`: the presence/stamp-list helper used by
the menu/planet-selection object/cell bookkeeping.  A 5M-step profile from the
menu loop showed `4D15..4D61` dominating the interpreted address list before the
existing hook was allowed in the live player.

After enabling the fixed hook, `4D15` disappears from the interpreted hotspot
list.  The next interpreted hotspots are now `1010:017E` (keyboard poll bit
loop), `1010:CCAD..CCC0` (dirty-copy mode-1 body when the still-disabled dirty
hooks are off), and `1010:3E12..3E4E`.

## Fixes / hooks

- Reworked `1010:4D15 overkill_presence_stamp_list_4d15` into a faster local-loop
  hook instead of using CPU helper calls for every small operation.
- Fixed an uncovered mode-0 accuracy bug in the older `4D15` hook: the original
  `JNE 4D59` path stamps only the base cell and appends it to `DS:DI`; the stacked
  `+1A/+34/+4E` stores are mode-1 `JMP BP` paths only.
- Removed `4D15` from the interactive disabled-hook set after adding regression
  coverage for the mode-0 and final-skip paths.
- Removed `41A6` from the interactive disabled-hook set as well; it is already
  covered by an interpreted-ASM oracle test and is now the active fast path for
  the variable-width interlaced menu/screen blit.

## Verification

Added `test_presence_stamp_list_4d15_final_skip_and_mode0_flags_match_asm` to
cover the previously missing paths.  Full result:

```text
56 passed in 2.65s
```

---

# Current run status — checkpoint 24

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `55 passed`.

This pass fixes the accuracy regression in the fast 4-plane row expander and
continues the loading/sprite-phase lift where profiling showed the highest
remaining interpreted-instruction density.

## Accuracy fix

- **Fixed `1010:4537` fast row expander final `DX`.**  The optimized
  `_row_4537_core` incorrectly left `DX` as the entry value.  The original ASM
  loads `DL`/`DH` from plane 2/3 and then calls `45F6` four times; each call
  rotates the plane bytes by two bits, so after four calls the bytes return to
  their loaded values.  The hook now exits with `DX = (loaded_DH << 8) | loaded_DL`.
- Reconfirmed the 4537/4511 oracle tests and fuzz tests, then the full suite.

## Loading / sprite-phase performance lifts

- **New overlaid object-scan skip hooks** for the hot repeated loops around
  `A849`, `A861`, `A87C`, `A894`, `A8C7`, `A90F`, `A927`, `A9E0`, and `AA10`.
  These loops mostly scan inactive object slots during loading/render setup.
  The hooks consume skip-only iterations in Python and stop immediately before
  the original CALL when an active/matching object needs the existing ASM logic.
  Stack scratch from the balanced `PUSH CX`/`POP CX` pair is preserved.
- **New `1010:3849` hook** for the 4-column masked sprite composite loop, the
  wider sibling of the existing `38B7` hook.  It composites four mask/data word
  pairs per row and restores `DS` from `CS:[9596]` before returning.
- **New `1010:469F` hook** for the plain 9-byte × 16-row sprite copy loop.
- **New `1010:4D6F` hook** for the presence-list clear loop.

## Verification

Added self-contained oracle tests for the newly risky lifts:

- `test_masked_sprite_composite_3849_hook_matches_interpreted_asm`
- `test_sprite_copy_469f_hook_matches_interpreted_asm`
- `test_overlay_scan_a849_skips_inactive_entries_like_asm`
- `test_overlay_scan_a9e0_counter_and_skip_match_asm`

Full result:

```text
55 passed in 2.50s
```

## Profiling note

A 1.5M-step CGA profile after the new hooks reaches further into the sprite/game
phase within the same interpreted-step budget, so wall-clock numbers are not a
clean apples-to-apples boot benchmark.  The previous `A849`/`A8C7`/`A9E0` scan
addresses disappear from the interpreted-instruction top list; the next visible
hotspots are now the small bit loop at `017E`, the `CD8D` region, and far-call
code at `1F8F:0960`.

---

# Current run status — checkpoint 23

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `49 passed`.

This pass continues the source-port lift of hot routines (the core methodology),
applies the renderer-helper cleanup that was prototyped but not committed last
round, and keeps the focus on performance-relevant code.  CGA and Tandy
correctness preserved; no gameplay logic rewritten.

## What changed

- **New `1010:38B7` hook `overkill_masked_sprite_composite_38b7`.**  Profiling
  after the 477E lift showed this is now the hottest interpreted routine in the
  sprite-render phase (~15k samples per loop-body address).  It is the classic
  masked sprite composite `dest = (dest AND mask) OR data`, two 16-bit columns
  per row over `CX` rows: source row `[mask0,data0,mask1,data1]` (SI += 8/row),
  destination stride `0x34`, read-modify-write of the destination, exit to
  `38D0` with `CX=0` and FLAGS from the final `add di,30h`.  Lifted into a
  verified Python hook (DF-aware, `CX==0 -> 65536` handled).  New self-contained
  oracle test `test_masked_sprite_composite_38b7_hook_matches_interpreted_asm`
  plus a 2000-state differential fuzz: bit-identical to the interpreted loop.

- **`1010:4537` renderer helpers lifted to module level.**  The four per-call
  closures (`rol8`/`ror8`/`rcl8`/`rcl16_mem`) and the `pack_four_pixels` /
  `expand_bits` bodies are now module-level `_r_*` functions instead of being
  rebuilt on every call.  This makes the lifted source clearer and reusable —
  exactly the direction the source port wants — and is verified bit-identical to
  the previous implementation by a 3000-state fuzz and the existing 4537 oracle
  test.  (Note: this did not measurably change raw CPython speed; it was applied
  for source-port clarity and because it is correct, not for a speed number.)

## Impact of the sprite-render lifts (477E + 38B7)

Measured over a 2.5M-step window that reaches the sprite phase: `38B7` fires
~1,089 times and `477E` ~866 times, together removing ~292k interpreted
instructions (each call replaces 90-190 one-at-a-time Python opcode dispatches
with a single hook).  These routines dominate *sprite-heavy gameplay frames*
rather than the boot-to-menu path (which is bound by the already-hooked
`450C`/`4511`/`4537` asset expansion), so the benefit shows up as lighter
per-frame work during play, not as a faster cold boot.

## Honest note on raw boot speed

As measured last checkpoint, no safe micro-optimisation to the CPython
interpreter core moves cold-boot time meaningfully; the high-leverage lever for
overall speed remains running under PyPy (10-50x on this kind of dispatch loop,
zero code change, current path stays as fallback).  The per-routine lifts above
are still worthwhile: they advance the reverse-engineered source port *and* cut
real interpreted work in the hot rendering phase.

## EGA

Unchanged this pass (still the cyan/black plane-2/3-under-fill described in
checkpoint 22).  The diagnosis stands: not a palette problem; planes 2/3 are
under-filled upstream of the verified present/expansion hooks.  A fix needs EGA
planar-memory modelling and/or a corrected EGA source decode, deliberately
deferred to avoid destabilising the working CGA/Tandy modes.  Track it with
`python scripts/diag_video.py --video ega`.

---

# Current run status — checkpoint 22

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  This pass dug into the two open
complaints — "EGA still black/blue" and "performance still poor" — and reports
measured, evidence-based conclusions rather than speculative fixes.  `48 passed`.

## EGA: root cause narrowed (planar plane-fill, not palette)

`scripts/diag_video.py --video ega` now also reports EGA register activity.
Captured across the first several EGA presents:

- plane nonzero bytes stay lopsided every frame: plane0/1 ~1380-1500, but
  plane2/3 ~60-105 (persistent, not just the title frame);
- colour indices in use do grow over frames (up to `0,1,3,4,7,8,9,12,14,15`),
  so the output is not literally two colours — it is dominated by index 0
  (black, ~91%) and index 3 (cyan, ~9%), which reads as "black/blue";
- sequencer map-mask writes (`OUT 03C5h,01/02/04/08h`) are *balanced* across all
  four planes, and there are **zero** attribute-controller (`03C0h`) palette
  writes.

Interpretation: the palette is the fixed default (so colour *mapping* is not the
bug), and all four planes are addressed, yet planes 2 and 3 end up almost empty.
The verified `1010:4537` 4-plane row expander is bit-identical to the original
ASM (re-confirmed this pass by a 3000-state differential fuzz), so the missing
plane-2/3 data is **upstream** of the present/expansion hooks: either the source
bytes fed into the EGA decode, or an EGA-specific decode path, are not
delivering the high planes.  A real fix most likely needs the memory model to
represent EGA planar writes (map-mask routing into the four `A000` shadow
planes) and/or a corrected EGA source-decode — a sizeable feature that is
deliberately **not** attempted here so the working CGA and Tandy modes stay
untouched.  Use `diag_video.py --video ega` to track this as the EGA work
continues.

## Performance: measured ceiling, no free safe win

Clean A/B micro-benchmarks (1.5M boot steps, no profiler overhead) this pass:

- hoisting `4537`'s six per-call closures to module level: ~19.0s vs ~19.6s
  (no improvement — closure creation was not the bottleneck);
- guarding the interpreter's per-instruction disassembly f-strings behind
  `trace_enabled`: ~18.7s vs ~19.0s (within noise).

So the verified micro-optimisations that looked promising do **not** move the
needle and were not applied (to avoid churn/risk).  The interpreter is near its
CPython per-instruction ceiling (~80-140k interpreted-steps/sec) and the loading
path is bound by pure-Python pixel expansion (`450C`/`4511`/`4537`), which is
already a verified hook.  Realistic high-impact options, in order of
safety/leverage:

1. **Run under PyPy** — an interpreter dispatch loop like this typically gets
   10-50x for free with no code change; the current CPython path stays as the
   fallback.  This is the recommended lever for "performance is poor".
2. Skip the one-time ~11-15s asset-decode bootstrap during development with
   `python scripts/play.py --snapshot <dir>` (already supported).
3. Longer term: a dispatch-table interpreter core, or numpy/C vectorisation of
   the 4-plane expansion — both higher risk and deferred per the project's
   correctness-first rules.

The checkpoint-21 changes (the verified `1010:477E` sprite-blit hook, the dead
`prefixes` cleanup, the profiler, and the diagnostics) remain in place.

---

# Current run status — checkpoint 21

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Focus of this pass: profiling the asset-heavy loading path, one safe new
performance hook, and EGA/Tandy diagnostics.  CGA and Tandy correctness are
preserved; no gameplay logic was rewritten.

## What changed

- **New profiler `scripts/profile_hotspots.py`** (rewritten).  It samples the
  executed CS:IP every step and wraps every registered hook with a timing/
  counting shim, then prints a wall-clock breakdown of interpreter vs
  decode-hook vs present/graphics-hook time, the hottest CS:IP addresses, and
  the hooks ranked by cumulative time.  Counters live in the script, so the
  interpreter core stays clean.

      python scripts/profile_hotspots.py 3000000 --top 25
      python scripts/profile_hotspots.py 1500000 --video tandy

- **New `1010:477E` hook `overkill_sprite_blit_9x16_477e`.**  Profiling showed
  the single hottest *interpreted* routine during sprite-heavy loading is the
  fully-unrolled fixed-geometry blit at `1010:477E..480D`: it copies a 9-byte
  wide by 16-row sprite from `DS:SI` (source stride 52) into a packed `ES:DI`
  buffer, with `ES`/source-`DS` loaded from `CS:[9596]`/`CS:[9598]` and `DS`
  restored to `CS:[9596]` on exit.  The hook reproduces that exactly (registers,
  flags from the final `add si,2Bh`, the 144 copied bytes, near RET) and is
  verified against interpreted ASM for both `DF=0` and the `DF=1` fallback in
  `tests/test_overkill/hooks.py::test_sprite_blit_477e_hook_matches_interpreted_asm`.

- **Interpreter micro-cleanup in `cpu.py`.**  Removed a dead
  per-instruction `prefixes` list that was allocated on every `step()` but never
  read, and hoisted the segment-override prefix table to a module-level
  `_SEG_OVERRIDE` dict instead of rebuilding it per prefix byte.  No semantic
  change; the core regression suite still passes.

- **New diagnostics `scripts/diag_video.py`.**  Runs the original code to the
  first frame-present in the requested mode and reports, for EGA, the nonzero
  byte count of each of the four `A000` shadow planes and the full 16-colour
  index histogram; for Tandy/CGA the packed nibble/2bpp histogram.

      python scripts/diag_video.py --video ega
      python scripts/diag_video.py --video tandy

## Profiling finding (loading path)

In a 1.5M-step CGA boot window the wall-clock split was roughly interpreter
31% / decode-hooks 68% / present 1%.  The decode-hook time is dominated by the
already-verified 4-plane expansion driver `1010:450C`
(`overkill_expand_4plane_list_450c`) and the per-block renderer it calls,
`1010:4511`.  The hottest *interpreted* region is the `1010:A849..A9E0` sprite
dispatcher that calls `1010:477E`.  The new 477E hook removes the unrolled-MOVS
body of that dispatcher (~96 interpreted instructions per call) but, because
477E is only ~2-3% of boot steps, the headline boot time is still governed by
the 450C/4511 expansion phase.  Speeding that up further would mean optimising
the existing renderer hook rather than adding new ones, which is deferred to
keep the verified path intact.

## EGA diagnostic finding (supersedes the "only one plane" hypothesis)

`diag_video.py --video ega` at the first EGA present (reached ~2.34M steps,
stopping around `1010:D013`) reports:

- plane 0 nonzero = 1378/8000, plane 1 = 1461/8000, plane 2 = 87/8000,
  plane 3 = 95/8000;
- colour indices actually used = `0, 2, 3, 8, 12, 14` (index 0 = 90.8%,
  index 3 = 8.9%, the rest < 0.3%).

So the renderer *is* combining multiple planes (indices 3/12/14 require more
than one plane), which **refutes** the earlier "only plane 0 / only indices
0,1" theory.  The real symptom is that planes 0 and 1 carry almost all the data
while planes 2 and 3 are nearly empty, so the first presented EGA frame is
cyan(index 3)-on-black - consistent with the "black/blue" report but now
quantified.  Open question: whether planes 2/3 are legitimately sparse for this
particular (title/loading) frame or are being under-filled upstream.  Capturing
several EGA presents with `diag_video.py` is the recommended next EGA step.

## Tests

`48 passed` (was 47; one new self-contained 477E differential test).  Run with:

    python -m pytest -q

Compile check:

    python -m py_compile scripts/profile_hotspots.py scripts/diag_video.py \
        cpu.py overkill/hooks.py

## Still unknown / next

- EGA: are planes 2/3 under-filled, and where (compare several presents)?
- Loading speed is now bounded by the 450C/4511 4-plane expansion hook; any
  further win there must stay a verified transliteration.
- CGA and Tandy remain the correctness oracles and were not changed.

---

# Current run status — checkpoint 20

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Commands used in this pass:

```bash
python -m py_compile scripts/play.py scripts/render_frame.py runtime.py overkill/hooks.py
python -m pytest -q
python scripts/render_frame.py artifacts/play_tandy_edrax_orbit_combat_20260611_214016 --video cga --out artifacts/evidence/test_cga.png
python scripts/render_frame.py artifacts/play_tandy_edrax_orbit_combat_20260611_214016 --video ega --out artifacts/evidence/test_ega.png
```

Result:

- tests pass: `43 passed`,
- `create_runtime(..., command_tail=...)` can now pass a DOS PSP command tail to
  the original executable,
- `scripts/play.py` has `--video cga|ega`; `--video ega` launches the original
  code with the documented `/E` command-line selector,
- EGA mode uses the original mode-1 present path at `1010:2750`, which writes to
  `A000h` through the EGA sequencer map-mask mechanism,
- because the project memory model is a flat bytearray, the new `1010:2750`
  replacement stores the presented EGA frame in explicit shadow planes inside
  the `A000h` aperture (`+0000/+2000/+4000/+6000`),
- `scripts/render_frame.py` and `scripts/play.py` can decode that EGA shadow layout
  as 320x200 16-colour RGBI/EGA output,
- CGA remains the default and still uses the previously stabilized B800h pacing
  path.

Useful commands:

```bash
python scripts/play.py --game-hz 30
python scripts/play.py --video ega --game-hz 30
```

If intro/menu speed needs tuning independently from gameplay, use:

```bash
python scripts/play.py --video ega --game-hz 30 --retrace-hz 60
```

---

# Current run status — checkpoint 19

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Commands used in this pass:

```bash
python -m pytest -q
```

Result:

- tests pass: `41 passed`,
- added 8086 opcode `27h` / `DAA` to `cpu.py`,
- confirmed this is not simply a stray VM/IP leak: the loaded runtime overlay rewrites
  `1010:5F18` from the startup byte `C6` into a legitimate `DAA` sequence, and
  previous snapshots already contain `27` at that address,
- added focused BCD adjust tests for the score/text digit path around
  `1010:5F18`, including `DAA` carry propagation after `ADD AL,imm8`.

The intro/menu retrace pacing from checkpoint 18 remains in place.  If the player
now reaches the same path, it should no longer crash on `Unsupported opcode 27 at
1010:5F18`.

Useful command:

```bash
python scripts/play.py --game-hz 30
```

If intro/menu speed needs tuning independently from gameplay, use:

```bash
python scripts/play.py --game-hz 30 --retrace-hz 60
```

---

# Current run status — checkpoint 18

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Commands used in this pass:

```bash
python -m pytest -q
python scripts/play.py --game-hz 30
```

Result:

- tests pass: `39 passed`,
- the latest player no longer assumes that gameplay's `1010:0679` timer wait is
  the only timing source,
- `1010:50C9` VGA retrace waits are now paced in `scripts/play.py` as well,
  because intro/menu/transition code uses that path for visible delays,
- B800h is checksummed and Tk receives a new immutable snapshot only when the
  visible screen changed, which prevents static retrace delay loops from
  flooding the UI with duplicate frames,
- `1010:58DF` is disabled in interactive play by default so its internal direct
  calls to the 50C9 helper do not bypass the retrace pacing wrapper,
- the previous unsafe dirty/render hooks remain disabled by default:
  `1010:41A6`, `1010:4D15`, `1010:CCAA`, `1010:CCC4`, `1010:CCF0`.

Controls (`scripts/play.py`): **Q up, A down, O left, P right, Z / Space fire, Esc quit.**

Useful command:

```bash
python scripts/play.py --game-hz 30
```

If intro/menu is too slow or too fast, tune the VGA wait pacing separately:

```bash
python scripts/play.py --game-hz 30 --retrace-hz 60
```


## 2026-06-10 EGA performance update

- EGA mode now has additional verified hooks for the hot mode-1 row conversion
  path: `280D`, `2824`, `291C`, and `2932`.
- These are narrow replacements of known loops, not broad renderer guesses.
- The visible EGA output is still using the current A000 shadow-plane renderer;
  the reported blue/black menu suggests there is still more EGA palette/plane
  investigation to do, but the new hooks target the slow startup/menu path.
- Test suite: `47 passed`.

### 2026-06-10 Tandy video mode experiment

`scripts/play.py` now accepts `--video tandy` and passes the original documented
` /T` PSP command-tail selector to the game.  The live player wraps the mode-2
presenter at `1010:3354` as a frame boundary and renders the Tandy/PCjr
320x200x16 packed aperture from `B800h`.

Implemented pieces:

- `1010:3354 overkill_present_tandy_frame_3354` mirrors the original mode-2
  presenter: `52` words (`104` bytes) per row, `192` rows, starting at `00A0h`,
  with the Tandy four-bank row stepping (`+2000h`, wrap with `+80A0h`).
- `render_tandy_ppm()` decodes the Tandy layout as two 4-bit RGBI pixels per byte
  with scanlines split as `(y & 3) * 2000h + (y >> 2) * 160`.
- `scripts/render_frame.py --video tandy` can render snapshots using the same
  decoder.

The regular test suite remains green (`47 passed`).  This is intentionally an
experimental third video mode rather than a replacement for fixing the remaining
EGA plane/palette issue.

### 2026-06-10 Tandy selector fix

The first Tandy experiment passed the documented ASCII `/T` switch directly to
`OVERKILL.UNLZEXE.EXE`.  That is not what the already-unpacked inner executable
expects: its startup parser reads `PSP:82` as a compact binary video selector
(`0=CGA`, `1=EGA`, `2=Tandy`).  ASCII `/T` therefore looked like an out-of-range
selector and fell back to EGA, while `play.py` was watching the Tandy `B800h`
aperture, producing black frames.

`play.py --video ega` and `--video tandy` now pass the inner binary selector
instead:

- EGA: `bytes((0x0D, 0x01))`
- Tandy: `bytes((0x0D, 0x02))`

The `--dos-args` escape hatch remains for raw ASCII PSP-tail experiments.

## 2026-06-13 BEC5 variant 000A owner-linked collision tail

`snapshot_play_tandy_20260613_000648` reached `BC4B -> 62F6 -> BEC5` with a
collided slot whose logic/variant field was `000Ah`.  The original does not
have a dedicated 000A handler; after the 7/8/0C/9 table and the 2/6/5 checks it
compares the current object BP with `DS:[BX+30h]`.  A match marks the collided
slot as linked to the current object, clears `DS:[BX+1Ch]`, clears
`SS:[BP+20h]` when `A8C2 != 1`, and jumps into the shared `BFC7` transition
path.

- `_run_collision_handler_bec5_observed` now models that owner-linked fallback.
- Added a regression that advances the captured snapshot to the 53rd `BC4B`
  call and compares the lifted hook against interpreted original ASM with full
  memory equality.

## 2026-06-13 refactor pass: replacements staging split

- Moved shared OVERKILL 8086-style arithmetic/string helpers out of
  `overkill/hooks.py` into `overkill/asm.py`.
- Moved the large gameplay object/postmove/collision behavior island out of
  `overkill/hooks.py` into `overkill/gameplay/object_runtime.py`.
  The address-facing hook wrappers remain in `overkill/hooks.py` and import the
  lifted game logic back, preserving the hook-registration boundary.
- Added `1010:30BA overkill_tandy_patched_row_copy_30ba`, a signature-guarded
  hook for the runtime-patched Tandy row copier that was showing up as the
  `30C3/30C4/...` unknown hotspot cluster.  The old static bytes at `30BA` are
  not stable; if the patched row-copy signature is not resident, the hook
  interprets the current original instruction instead of guessing.
- Added `1010:30B0 overkill_tandy_interlaced_clear_30b0` for the static startup
  Tandy interlaced clear routine.
- Validation: `python scripts/run_tests.py` => `161 passed, 0 failed`.
- Live verification: `scripts/play.py --verify-hook 1010:30BA --verify-stop-on-diff`
  verified 25 calls before the smoke run timeout, with `1010:30BA` averaging
  about 112.68 ASM-equivalent instructions/call.

## 2026-06-13 video-mode label audit

- Audited CGA-labelled hooks seen during Tandy gameplay.
- Confirmed `1010:5A00`, `1010:5A24`, and `1010:5A36` are shared video-mode dispatch helpers. They select CGA/EGA/Tandy behavior through `CS:[95BC]`, so their registered hook names were changed from `overkill_cga_*` to neutral coordinate names while keeping old aliases for tests/tools.
- Reclassified `1010:4D15` and `1010:4D6F` from `cga_renderer` to `layer_sprites`: these are shared presence/occupancy-list stamp/clear helpers used by Tandy gameplay too. Mode 1 has EGA-style stacked-cell handling; CGA/Tandy share the non-mode-1 base-cell path.
- Short Tandy snapshot coverage smoke now reports zero `cga_renderer` calls for the intro/dirty-cell presenter path; shared hooks show under `coordinates`, `layer_sprites`, or `tandy_renderer` as appropriate.


## 2026-06-13 - Unknown gameplay/collision hook absorption

Absorbed several hot unknown/gameplay instructions without duplicating existing logic:

- `1010:AED8 overkill_object_behavior_aed8` now hooks the observed logic-id 2/3 countdown/movement behavior and reuses a shared `AD60` bounds/tile tail.
- `1010:AD04 overkill_object_logic_branch_ad04` is only a branch selector: it returns or jumps to existing `ABxx` behavior tails, rather than reimplementing those tails.
- `1010:AC81 overkill_object_slot_scan_guard_ac81` is only the guard/setup for the already-lifted `AC97` object-slot scan and directly reuses `run_object_slot_scan_ac97`.
- `1010:AE09 overkill_object_behavior_ae09` handles the observed logic-id `0Ch` timer/3-pixel movement behavior, then reuses the same shared `AD60` tail as `AED8`.

The previous inline `AD60` implementation inside `AED8` was refactored into `_run_object_bounds_tile_tail_ad60` so new behaviors do not clone the same bounds/tile/deactivation logic.

Validation: `python scripts/run_tests.py` => `162 passed, 0 failed`; `python -m compileall -q dos_re overkill tests scripts`; live hook verifier samples were recorded for `AC81`, `AD04`, `AE09`, and `AED8` and added to `artifacts/hook_coverage_cache.json`.

## 2026-06-13 startup renderer table unknown absorption

- Identified the `1010:0F31/0F32/0F37` unknown startup cluster as the inner loop
  of `1010:0F0B`, a renderer coordinate/video lookup-table builder.
- Added `1010:0F0B overkill_startup_coordinate_tables_0f0b` in the renderer
  module.  The hook generates the `DS:99C8..A077` table family and reuses the
  existing `1010:0FA3` lifted helper for the fallthrough table builder, avoiding
  a second implementation of the same `0FA3` logic.
- Regression oracle `snapshot_stop_1010_0f0b_startup_tables` compares the lifted
  hook against fully interpreted ASM through continuation `1010:526A` with full
  CPU and memory equality.
- Validation: `python scripts/run_tests.py` => `163 passed, 0 failed`.
- Live verification: `scripts/play.py --video tandy --verify-hook 1010:0F0B
  --verify-stop-on-diff` verified the cold-start call with no divergence before
  the smoke timeout.
- Remaining cold-start unknowns around `32FF:0052` belong to the transient
  unpack/relocation bootstrap segment, not to a stable game island.  I did not
  hook them because the segment is dynamically loaded and not useful as a game
  module boundary.

## 2026-06-13 documentation/methodology refresh

Updated the project documentation to describe the now-established source-port
method as a reusable system rather than a pile of one-off OVERKILL fixes.

Main documentation changes:

- Added `docs/dos_re/source_port_methodology.md`, the canonical playbook for the
  evidence-driven workflow:
  `observe -> classify -> choose boundary -> build ASM oracle -> implement hook -> verify -> document -> move to island`.
- Updated `AGENTS.md` with the canonical workflow, the current island-module
  layout, the staging rule for `overkill/hooks.py`, and the requirement to search
  for existing tails/helpers before implementing a new hook.
- Removed a duplicated `CPU Interpreter Rules` section from `AGENTS.md`.
- Updated `README.md` with the methodology loop, current island examples, and a
  pointer to the new methodology document.
- Updated `docs/overkill/design.md` with the current `overkill/` module map and the
  migration path from original ASM to staged hook to island module.
- Replaced the stale `docs/overkill/next_steps.md` bootstrap-era TODO list with current
  priorities: meaningful unknown absorption, keeping `overkill/hooks.py` as
  staging, duplicate-code prevention, intentional verification modes, and island
  documentation hygiene.

No runtime code changed in this pass.

## 2026-06-13 logic-pyramid documentation and bootstrap classification

- Added the end-goal source-port pyramid to `docs/dos_re/source_port_methodology.md`,
  `docs/overkill/design.md`, `README.md`, `AGENTS.md`, and `docs/overkill/next_steps.md`:
  original binary oracle -> ASM-compatible hook/runtime -> verified lifted
  routine -> runtime object/data model -> game systems -> gameplay archetypes ->
  semantic game model -> modern/enhanced port layer.
- Clarified that current object work is mostly still layer 4: slots with
  sprite/layer/logic-id/movement/collision fields.  Player/projectile/enemy/boss
  names should emerge only after multiple verified routines support them.
- Added a `bootstrap` coverage island for the transient `32FF:*` cold-start
  unpack/self-relocation segment.  This makes the dashboard more honest: these
  instructions are no longer `unknown`, but they are also not a game-module island
  to hook prematurely.
- Added `32FF:0052 inner_unpack_relocation_bootstrap_32ff_0052` to
  `symbols.json` as `classified-do-not-hook`.
- Validation: `python scripts/run_tests.py`; `python -m compileall -q dos_re overkill tests scripts`.

## 2026-06-13 crystallization methodology integration

Integrated the user-supplied methodology dump into durable project docs.

Updated:

- `docs/overkill/source_port_methodology.md` with the full evidence ladder: original
  oracle, layer ownership, dependency direction, promotion rules, vertical
  slices, definitions of done, AI task framing, and hard anti-chaos rules.
- `docs/overkill/island_truth_tables.md` as the new per-island confidence/evidence index.
- `AGENTS.md` with hard layer boundaries, task framing examples, dependency
  direction, and the requirement that every semantic name remains reversible to
  original ASM evidence.
- `README.md`, `docs/overkill/design.md`, and `docs/overkill/next_steps.md` to point future work at
  the crystallization model and island truth tables.

No runtime behavior changed. Validation: `python -m compileall -q dos_re overkill tests scripts`; `python scripts/run_tests.py`.

## 2026-06-13 unknown/island cleanup continuation

Continued the evidence-driven cleanup after the crystallization-methodology pass.

Runtime changes:

- Added `1010:5A6C overkill_menu_cell_source_blit_dispatch_5a6c`, a shared
  source-cell video-mode dispatch stub used by the dirty-cell presenter.  It is
  classified under `layer_sprites`, not CGA/Tandy-specific rendering, because it
  only reads `CS:[95BC]` and jumps through the mode table.
- Registered/lifted `1010:AB10 overkill_object_logic_ab10` using the live
  runtime-patched byte shape.  The deactivation path through `AC22` is now
  modelled instead of fail-fast.
- Added `1010:AB77 overkill_object_behavior_ab77` as an observed object-behavior
  driver.  It deliberately reuses existing `AB4F`, `AC28`, and `AC81/AC97`
  helpers and preserves original continuations for still-unlifted tails.
- Added `1F8F:0922 overkill_gameplay_counter_tick_1f8f_0922` and the new
  `game_state` coverage island.  This routine lives in an overlay segment but is
  per-frame/game-state counter logic, not asset decoding.
- Moved the `1010:0679` timer wait implementation out of `overkill/hooks.py` into
  the sound/timer island and added the companion `1010:0672` clear-timer-flag
  hook there.
- Added `1010:511F overkill_video_page_toggle_511f`, a shared per-frame video
  page stub.  It is a no-op return in Tandy/CGA but toggles the mode-1 visible
  page state.

Classification changes:

- `1010:D007..D04C` is now classified as the main gameplay frame-loop dispatcher
  under `game_state`, not raw unknown code.
- `1010:A846/A85E/A876` and `1010:4CED..4D14` are classified as layer-sprite /
  presence-list parent frontiers.  They are not hooked yet because they should be
  composed from existing `A849/A861/A87C/4D15` helpers rather than duplicated.

Validation:

- `python -m compileall -q dos_re overkill tests scripts`
- `python scripts/run_tests.py` => `165 passed, 0 failed`
- `scripts/play.py --snapshot artifacts/snapshot_play_tandy_20260613_000648
  --verify-hook 1010:0672 --verify-hook 1010:0679 --verify-hook 1010:511F
  --verify-hook 1F8F:0922 --verify-hook 1010:AB77 --verify-hook 1010:AB10
  --verify-hook 1010:5A6C --verify-stop-on-diff --verify-max 250` reached the
  verifier limit with no divergence.

## 2026-06-13 layer-sprite present parent cleanup

Continued the unknown/island cleanup by absorbing the A90C/A93C/4D64 present-scan
frontier without duplicating the underlying renderer/presence loops.

Runtime changes:

- Added `1010:A90C overkill_present_object_scan_pair_a90c`, the two-table
  present parent.  It sets `CX=22h` and reuses the existing `A90F` scan over
  `DS:8D12`, then sets `CX=24h` and reuses the existing `A927` scan over
  `DS:32CA`.  If either child scan finds an active entry, the hook preserves the
  original partial continuation at the real `CALL 5A92` site.
- Added `1010:A93C overkill_present_scan_clear_presence_a93c`, modelling the
  tiny `CALL 4D64 ; RET` parent.
- Added `1010:4D64 overkill_clear_presence_list_parent_4d64`, the setup parent
  for the already-lifted `4D6F` presence-list clear loop.  It sets
  `ES=CS:[9598]`, `SI=C7B1h`, and `CX=28h`, then tail-runs the existing `4D6F`
  hook.
- Classified the next `D04D..D072` per-frame state/UI cluster under
  `game_state` rather than leaving it as raw unknown.  It is still a larger
  frontier, not a safe small hook.

Validation:

- `python -m compileall -q dos_re overkill tests scripts`
- `python scripts/run_tests.py` => `165 passed, 0 failed`
- `1010:A90C` verified for 50 calls from `artifacts/evidence/snapshot_stop_1010_a90c`.
- `1010:A93C` verified for 10 calls from `artifacts/evidence/snapshot_stop_1010_a93c`.
- `1010:4D64` verified on its direct stop snapshot.

## 2026-06-13 next unknown cleanup: pacing loops, postmove prelude, loading scroll, counters

Continued the evidence-driven unknown cleanup after the A90C/A93C/4D64 layer-sprite pass.
The focus was small, composable hooks that remove meaningful unknown coverage without
collapsing larger orchestration boundaries or duplicating existing lifted logic.

Runtime changes:

- Added `1010:96C5 overkill_intro_retrace_delay_loop_96c5` and companion
  `1010:96C8 overkill_intro_retrace_delay_loop_tail_96c8`.  This is the
  intro/menu fixed-count `CALL 50C9 ; LOOP` delay.  The hook calls the installed
  `50C9` hook instead of the base implementation so interactive `play.py` keeps
  its visual pacing/publish boundary.
- Added `1010:BC45 overkill_object_postmove_prelude_bc45`.  This tiny collision
  prelude adds `DS:[A278]` into `SS:[BP+02]`, then reuses the shared `BC4B`
  postmove/collision chain.  The hook performs the final near return exactly like
  the interpreted fallthrough path.
- Added `1010:4E0D overkill_tandy_loading_scroll_until_4e0d`, the loading-scroll
  parent around the existing lifted `A781` step.  It preserves `SI/DI`, loops
  until `DS:[2350] <= DI` and `DS:[234E] == 0`, then stores `SI` into `DS:[A978]`.
  The nested return IP is intentionally `4E12`, matching the original stack scratch.
- Added `1010:61CA overkill_decrement_first_active_counter_scan_61ca`, the hot
  inner scan over `DS:2368..2372` word counters.  It decrements the first non-zero
  counter and returns when all are zero.  The `1010:61C5` parent remains available
  for callers that enter before loading `DI=2368`, but real hot gameplay calls
  commonly enter directly at `61CA`.

Anti-duplication notes:

- `96C5` does not inline the retrace/publish wait; it composes the installed
  `50C9` hook.
- `BC45` does not copy the postmove/collision chain; it delegates to the existing
  `BC4B` implementation.
- `4E0D` does not clone the loading-scroll step; it calls the existing lifted
  `_loading_scroll_step_a781`.
- `61CA` is the shared scan core used by the `61C5` parent and direct hot callers.

Validation:

- `python -m compileall -q dos_re overkill tests scripts`
- `python scripts/run_tests.py` => `167 passed, 0 failed`
- Live hook verifier coverage was checked for `1010:96C5`, `1010:BC45`,
  `1010:4E0D`, and `1010:61CA` with no divergence in the exercised snapshots.

Remaining useful frontiers:

- `1010:9FEA` appears to be an object/table coordinate update helper.  Build a
  direct oracle before naming it as movement or object-runtime logic.
- `1010:5EF9` looks like a small text/nibble rendering helper around `5F06`.
- `1010:4D95` is likely another presence-list parent and should compose `4D15`.
- `1010:780E` is a Tandy/layer draw sub-loop candidate.
- `1010:8A7E` is object-behavior frontier; do not promote to enemy/projectile
  semantics until child helpers and evidence traces converge.

## 2026-06-13 island classification sanity pass

Goal: keep the current work in the strict first/lifted-routine layer and make
island ownership match observed behavior rather than historical address names or
segment residence.

Corrections made:

- `startup_graphics.py` moved from `asset_codecs/` to `rendering/startup_graphics.py`.
  The routines there materialize renderer/startup tables and graphics buffers;
  they are not asset codecs just because they run during loading.
- `1F8F:0960` moved from overlay/asset ownership to `gameplay/game_state.py` and
  registered as `overkill_gameplay_counter_stride_loop_1f8f_0960`.  It lives in
  an overlay segment, but it updates gameplay counters, so segment residence is
  not the island classifier.
- Coverage now has separate `overlay` and `startup_graphics` dashboard islands.
- Coverage exact-address sets are tested to be non-overlapping, and every
  registered hook is tested to classify to a non-`unknown` island.
- `scripts/audit_islands.py` now uses the same `OverkillCoverageClassifier` as
  the live dashboard, so audit output and runtime coverage cannot silently drift
  apart.

Current first-layer rule reinforced:

- Keep hook names technical and evidence-based.
- Do not introduce semantic names such as concrete enemies/projectiles while we
  are still only proving runtime object-slot behavior.
- Move stable lifted behavior out of `overkill/hooks.py` into the correct island,
  but keep `overkill/hooks.py` as address-facing hook glue and compatibility
  aliases only.

Validation:

```text
python -m compileall -q dos_re overkill tests scripts
python scripts/run_tests.py
169 passed, 0 failed
```

Smoke coverage with dummy SDL now reports cold-start startup materialization as
`startup_graphics` instead of `asset_codecs`/`tandy_renderer`, and `overlay` is
reserved for the real `254A:*` overlay helpers.
## 2026-06-13 - Hook wrapper refactor / naming audit

- Moved asset/loading codec hook wrappers from `overkill/hooks.py` to
  `overkill/hook_wrappers/asset_codecs.py`.
- Kept `overkill.hooks` as the compatibility aggregate import that
  registers all hooks and re-exports existing test imports.
- Normalized registry labels so all 222 registered hooks include an address
  suffix.
- Removed semantic-noise `_fast` from the two asset-codec registry labels where
  it described implementation speed rather than original-game behavior.
- Added `docs/overkill/hook_naming_audit.md` with the current naming rules and next safe
  extraction targets.
- Verification: `python -m pytest -q` => 185 passed;
  `python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 --verify-max 1000 --fast-ranges` => OK.



## 2026-06-13 - Hook wrapper refactor pass 2

- Extracted shared hook-wrapper mechanics from `overkill/hooks.py`
  into `overkill/hook_wrappers/common.py`:
  runtime-patched-code guard plus near-CALL wrapper helpers.
- Moved text-rendering hook wrappers into
  `overkill/hook_wrappers/text.py`.
- Moved timer/PC-speaker hook wrappers into
  `overkill/hook_wrappers/sounds.py`.
- `overkill.hooks` remains the aggregate hook-registration surface.
- Renamed misleading shared layer-sprite registry labels:
  `768E`, `75A6`, and `7746` no longer claim Tandy-only ownership.
- Registered hook count remains 222.
- Verification: `python -m pytest -q` => 185 passed;
  `python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 --verify-max 1000 --fast-ranges` => OK.

Next safe extraction target is still renderer wrappers, but split it carefully:
move Tandy-only wrappers separately from shared layer-sprite scan/dispatch glue.
Do not collapse object behavior names into gameplay semantics until trace evidence
proves the object role.

## 2026-06-13 — hook cleanup pass 3: duplicate pruning and label alignment

- Renamed three asset-codec wrapper functions so decorated Python names match
  the registry labels: `overkill_file_checksum_loop_c916`,
  `overkill_packed_read_byte_0624`, and `overkill_packed_read_word_le_0615`.
- The older unsuffixed compatibility aliases were later removed; use the canonical address-suffixed names.
- The stale duplicate implementation in `overkill/asset_codecs/startup_graphics.py` was first reduced to a shim and later removed; startup graphics helpers now live only in `overkill/rendering/startup_graphics.py`.
- Static hook audit now reports 222 hooks and no function/registry-label
  mismatch.


## 2026-06-13 — runtime-code variant exhaustion policy

- Promoted runtime-patched code from an ad-hoc hook guard into an explicit
  `overkill/runtime_code.py` manifest.
- `1010:5E42` now has named live-byte variants:
  - `gameplay_object_steer_5e42` — hooked/verified movement helper observed in
    `runtime_code_5e42_gameplay_20260613_220042`.
  - `cold_display_helper_5e42_prefix` — known cold executable body at the same
    address, intentionally not valid for the movement hook.
- Removed the previous behavior where the 5E42 hook could silently run the live
  original body when bytes did not match.  Known-wrong or unknown bytes now raise
  `UnknownRuntimeCodeVariant`.
- Added optional `Memory.write_watchers` and `RuntimeCodeWriteTracer` for tracing
  who writes into runtime-code regions without enabling it in normal gameplay.
- Added `scripts/trace_runtime_code_writes.py` with `--no-hooks` and `--all-code`
  for cold-start code-materialization audits.
- Added runtime-code tests proving cold/gameplay variant distinction, unknown
  byte fail-fast behavior, and write-tracer event capture.

Validation:

```text
pytest -q
196 passed
python scripts/verify_hooks_headless.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --verify-max 300 --fast-ranges --coverage
OK HOOK VERIFY LIMIT REACHED verified=300
```

## 2026-06-13 — runtime-code staticization scaffold

- Promoted runtime-code handling from variant fail-fast only to an explicit
  staticization manifest.
- `overkill/runtime_code.py` now models `RuntimeCodeSlot`, accepted/rejected
  `RuntimeCodeVariant` records, and `RuntimeCodeStaticization` targets.
- `1010:5E42` is now recorded as a polyvariant code slot whose accepted gameplay
  body is staticized into
  `gameplay.object_runtime.run_runtime_patched_object_steer_5e42`.
- Added `scripts/audit_runtime_code_staticization.py`:
  - `--check` verifies that accepted runtime-code variants have static Python
    owners.
  - `--strict-installers` additionally requires writer/installer provenance and
    is intended as the final 100% exhaustion gate.
- `trace_runtime_code_writes.py --dump-final-variants` now reports the final live
  digest/variant for registered runtime-code slots after stepping.
- Added `docs/overkill/runtime_code_staticization.md` as the policy/playbook for turning
  runtime self-modifying code into named, flat source-port logic.

Important status:

- Source-port staticization gate passes for the current known slot.
- Strict installer gate intentionally still fails for `1010:5E42` until the
  cold-start writer that materializes the gameplay body is traced and named.

## 2026-06-13 — hot unknown cleanup after runtime-code staticization

- Absorbed two misleading hot/problematic interpreted regions that were not new
  runtime-patched bodies:
  - `1010:61F7` now hooks the hot `CALL 61C7; LOOP 61F7` status-counter glue.
  - `1010:5EDB` now hooks the HUD/status text block that composes `518C`, `5EF9`,
    and `5F06`.
- Corrected the old `1010:61C5` countdown hook metadata: `61C5` is inside the
  preceding CALL immediate in the materialized runtime body.  The real routine
  entry is `1010:61C7` (`MOV DI,2368h`).
- The new `61F7` hook preserves nested CALL stack scratch and leaves FLAGS from
  the final scan, matching interpreted ASM memory/state oracle checks.
- The new `5EDB` hook preserves intermediate CALL return scratch and tail-runs
  the final `5EF9` helper so the caller's original return address is consumed by
  the same boundary as the original code.
- No additional runtime-code slot was identified in this pass; these removals are
  static hot-region absorption, not self-modifying Python behavior.

Validation:

```text
python scripts/audit_runtime_code_staticization.py --check
ok; 1010:5E42 remains the only registered runtime-code slot, staticized with
installer provenance still pending

python -m pytest -q
201 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --verify-max 800 --fast-ranges --coverage
OK HOOK VERIFY LIMIT REACHED verified=800
```

## 2026-06-13 runtime-code census: 5E42 is bootstrap materialization, not video selection

Investigated whether the currently known runtime-patched code is actually a
video/sound/input selector that can be retired by committing to Tandy-first.

Result:

- `1010:5E42` is installed by the transient `32FF:*` inner unpack/self-relocation
  bootstrap, specifically `writer=32FF:009B`.
- The installer writes 211 bytes into `1010:5E42-5F1A`.
- CGA, EGA, and Tandy command tails all receive the same final variant:
  `gameplay_object_steer_5e42`.
- Therefore `5E42` is not a video-card, sound-card, keyboard, joystick, or
  Amstrad-joystick selector.  It is a bootstrapped gameplay/object steering body
  that is already staticized as flat Python.
- The actual video-mode choice observed in the same census is a data/config word
  in the code segment: `CS:95BC = 0000/0001/0002` for CGA/EGA/Tandy.  That can
  be lifted later into high-level Tandy configuration; it is not executable SMC.

Added `scripts/audit_runtime_code_census.py` to make this repeatable:

```bash
python scripts/audit_runtime_code_census.py --video all --steps 250000 --show-bootstrap
```

Updated the runtime-code manifest so strict installer audit now passes:

```bash
python scripts/audit_runtime_code_staticization.py --check --strict-installers
```

Validation:

```bash
python -m pytest -q
# 202 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --verify-max 800 --fast-ranges --coverage
# OK HOOK VERIFY LIMIT REACHED verified=800
```

## 2026-06-14 — menu AdLib/runtime hook lift pass #2

Continued lifting from the Tandy + AdLib main-menu snapshot profile
`snapshot_play_tandy_20260614_134931`.

Added lifted hooks for the remaining high-frequency optional AdLib driver glue:

- `2032:0000` far-call entry (`CALL 0063; RETF`), now used directly by the
  lifted `1010:06E5` timer ISR when `DS:0055 == 1`.
- `2032:0409` page/pause gate hot no-op path.
- `2032:0244` disabled per-channel accumulator helper.
- `2032:02AA` no-pending-note helper.
- Extended `2032:00CD` to cover the common countdown/no-op helper chain:
  `DEC [DI+1]; CALL 0244; CALL 02AA; CALL 02C9; CALL 02F6; RET` when the
  countdown remains non-zero and all helpers are idle.
- Added `1010:558B` as a one-idle-iteration main-menu wait-loop hook so menu
  idle polling no longer burns interpreted ASM on repeated no-key scans.
- `1010:06E5` no longer falls back to the interpreted optional-driver far call;
  it preserves the original far-call stack shape while dispatching through the
  lifted `2032:0000`/`2032:0063` path.

Measured on 100 delivered timer ticks from the supplied main-menu snapshot:

```text
before this pass, after previous AdLib lift: 6,127 interpreted instructions
after this pass:                            2,901 interpreted instructions
```

The remaining interpreted `2032:*` instructions are now mostly actual AdLib
bytecode/music advancement (`2032:00CD-0133` and `2032:0181-0290`), not generic
PIT/YM3812 delay glue.

Validation:

```bash
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 227 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_runtime_check
# reached 1010:D007; steps=21499
```

## 2026-06-14 — AdLib smoothness / pacing pass

Investigated the Tandy + AdLib main-menu path after hook coverage reached ~99%.
At this point the remaining ASM percentage is too small to explain visibly slow
music by itself; the more likely cause was interactive pacing/audio buffering:

- `1010:50C9` is a hardware retrace wait, not the `1010:0679` game-timer frame
  wait.  The live viewer previously defaulted retrace pacing to `--game-hz`
  (~36.4 Hz), which made intro/menu idle paths slower than a real display
  retrace cadence.  The default retrace pacer is now 60 Hz, still overrideable
  with `--retrace-hz` for diagnostics.
- `TimerPacer` now performs a final cooperative poll at the sleep deadline.  This
  keeps the async real `1010:06E5` IRQ0/AdLib ISR from missing a deadline tick
  when a retrace sleep lands exactly on the PIT boundary.
- The optional Nuked-OPL3 SDL backend now uses a slightly larger mixer buffer in
  AdLib mode, starts with current+queued PCM chunks, exposes `--adlib-chunk-ms`,
  and reports underrun counts in the window caption if the SDL queue starves.

Useful runtime knobs:

```bash
python scripts/play.py --video tandy --sound adlib
python scripts/play.py --video tandy --sound adlib --retrace-hz 60
python scripts/play.py --video tandy --sound adlib --adlib-chunk-ms 70
python scripts/play.py --video tandy --sound adlib --adlib-audio off
```

Validation:

```bash
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 227 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_timing
# reached 1010:D007; steps=19847
```

## 2026-06-14 — Intro/menu AdLib handoff timing pass

The remaining Tandy + AdLib stutter was narrowed to the interactive viewer
handoff rather than raw ASM cost: intro/menu paths spend a lot of time publishing
retrace-driven snapshots to SDL and waiting for the UI to consume them.  While
that producer/consumer wait was active, the emulator thread was blocked and did
not deliver asynchronous IRQ0 ticks, so the loaded AdLib driver advanced in small
irregular bursts.  Gameplay sounded normal because it reaches the regular
`1010:0679` timer wait path.

Changes:

- `FrameSync.publish_and_wait` can now run a cooperative wait callback while the
  emulator waits for SDL to display a snapshot.
- Retrace/direct/input-wait publishes pass the async IRQ0 poller into that wait,
  so the original `1010:06E5 -> 2032:0000` AdLib path keeps advancing while the
  UI consumes intro/menu frames.
- Interactive wait sleeps now poll IRQ0 during their short yield instead of
  sleeping with the emulated PIT completely stopped.
- SDL now remembers the last presented frame and redraws it on resize/expose;
  resizing a static screen no longer clears the image until the next emulated
  present.

Validation:

```bash
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 227 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_audio_timing
# reached 1010:D007; steps=19847
```

## 2026-06-14 — Deterministic boss-key wait detection

F9 boss-key display was still intermittent: the VM was correctly inside the
boss-key wait screen, but the SDL viewer could keep showing the last gameplay
frame while the caption/audio underrun counter continued updating.  The root
cause was an instruction-phase race in the interactive wait detector, not the
text renderer itself.

The original boss-key waits are tiny two-instruction loops at `1010:07C4`,
`1010:07D0`, and `1010:07D7`.  `CPU.run(max_steps)` can return after either
instruction in each loop; the old detector only matched the loop heads.  When the
burst ended on the branch instruction instead, the player missed the cooperative
text-frame publish boundary until the large no-boundary budget expired, which
looked like frozen gameplay.

Changes:

- Added explicit boss-key wait instruction windows:
  - `1010:07C4..07CA` F9-release wait
  - `1010:07D0..07D6` any-key wait
  - `1010:07D7..07DD` return-key-release wait
- `is_boss_key_screen_wait()` now classifies the whole instruction window before
  forcing the BIOS text frame to SDL.
- Added regression tests proving the wait detector accepts both loop-head and
  branch-instruction IPs while rejecting neighbouring code.

Validation:

```bash
python scripts/lint.py
# Lint passed for 70 Python files

python -m pytest -q
# 230 passed
```

## 2026-06-14 — Hook verifier metadata sweep and BC4B full-memory scratch fix

Follow-up from an interactive `scripts/play.py --video tandy --sound adlib --verify-hooks --verify-stop-on-diff` run.

Findings:

- Several recently lifted bootstrap, AdLib, menu, and renderer hooks were correct enough for normal play but had no verifier continuation metadata, so live verification printed repeated `HOOK VERIFY SKIP ... no continuation metadata` lines.
- The first real divergence was `1010:BC4B overkill_object_postmove_bc4b`: both ASM and hook returned to `1010:AA04`, but full-memory verification found one stack-scratch byte difference below the restored SP.
- The scratch mismatch was in the `BC4B -> BCCB -> BFC7 -> C054` death/transition tail.  The original `BFC7` materializes the score amount in `BX` (`0030h`/`0060h`) before calling the score-add helper; later selector/effect code can push that `BX` value as freed stack scratch.  The lift left the incoming `BX` live, so one path pushed `000Ch` instead of the expected `0030h`.

Changes:

- `BFC7` lift now explicitly sets `BX` to the selected score amount before the nested score/selector path.
- Added continuation metadata for all currently registered replacement hooks, including:
  - temporary bootstrap LZEXE loops at `1B65:0069`, `1C43:0069`, `23AD:0069`;
  - loaded AdLib driver helpers at `2032:*`;
  - interactive one-iteration menu loops `1010:558B` and `1010:D445`;
  - remaining renderer helpers and the far demo counter tick.
- Added a regression test that checks every registered hook has verifier metadata, so this class of skip should not silently return.
- Kept the runtime-code bootstrap test fast by leaving exact bootstrap/codec hooks installed and disabling only the `1010:5E42` runtime hook being inspected.

Validation:

```bash
python scripts/lint.py
# Lint passed for 75 Python files

python -m pytest -q
# 234 passed

python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_verify_metadata_fix2
# reached 1010:D007; steps=19847

python scripts/verify_hooks_headless.py --snapshot artifacts/static_runtime_bundle --verify-max 200 --max-steps 200000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200
```

## 2026-06-14 — 558B verifier expiry fix and 1F8F:081D live-code variant

Follow-up from an interactive Tandy/AdLib run started from
`artifacts/snapshot_play_tandy_20260614_203152`.

Findings:

- `1F8F:081D overkill_demo_counter_tick_1f8f_081d` was not actually patched to a
  different behavior.  The uploaded/live image uses `CMP AX,imm16` encodings
  (`3D xx 00`) where earlier evidence used the shorter `CMP AX,imm8` form
  (`83 F8 xx`).  The threshold values are small positive words, so both streams
  are equivalent for this routine.
- The `1010:558B overkill_main_menu_idle_loop_558b` verifier divergence was a
  real boundary bug.  The hook pre-fell back when `DS:22BF >= 02ED`, executing
  only the first original `CMP` and stopping at `5590`.  Original ASM still runs
  the retrace wait and increments `DS:22BF`; at `02ED` it reaches the valid
  expiry continuation `55FD` with `DS:22BF == 02EE`.
- The same parent should not depend on a nested installed `50C9` replacement to
  be verifier-stable.  Verification/pass-through contexts may restore or remove
  interactive retrace wrappers, but `558B` still has to reproduce the pure
  `50C9` side effects before landing on `558B`, `55FD`, or the near return.

Changes:

- `self_disable_if_patched()` now accepts multiple valid byte signatures for a
  hook entry and reports all accepted variants on mismatch.
- `1F8F:081D` accepts both compact and wide compare encodings.
- `558B` no longer pre-falls back on the `DS:22BF == 02ED` expiry edge; it runs
  the known prelude and stops at `55FD` after reproducing the increment/retrace
  side effects.
- `558B` has a local pure `50C9` fallback body for verifier contexts where the
  nested retrace hook is absent, avoiding one-instruction original fallback at
  the parent entry.
- Added regressions for the wide `1F8F:081D` encoding and the `558B` counter
  expiry boundary without an installed nested retrace hook.

Validation:

```bash
python scripts/lint.py
# Lint passed for 76 Python files

pytest -q \
  tests/test_overkill_hooks.py::test_demo_counter_tick_081d_accepts_wide_cmp_live_code_against_asm \
  tests/test_overkill_hooks.py::test_main_menu_idle_loop_558b_counter_expiry_boundary_without_installed_retrace_hook \
  tests/test_overkill_hooks.py::test_main_menu_idle_loop_558b_matches_interpreted_idle_iteration \
  tests/test_overkill_hooks.py::test_main_menu_idle_loop_558b_returns_on_fire
# 4 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_191454 --verify-max 200 --max-steps 400000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200
```

`python scripts/play.py ...` could not be re-run in the sandbox because pygame is
not installed here.  A full `pytest -q` run reached 82% with no displayed failure
before the sandbox timeout, so the focused regressions and headless verifier are
the completed validation for this patch.

## 2026-06-14 — interactive verifier startup visibility / presenter passthrough

Follow-up from running:

```bash
python scripts/play.py --video tandy --sound adlib \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-hooks --verify-stop-on-diff
```

Finding:

- The black SDL window during interactive hook verification was misleading UI
  starvation, not evidence that the Tandy VRAM was empty.  The uploaded snapshot
  already has non-zero B800h/Tandy contents, but `play.py` only published frames
  after a natural presenter/timer/retrace boundary.  With `--verify-hooks`, a
  large amount of object/frame logic can be differentially verified before the
  next boundary, especially when full-memory diffs are enabled.
- The Tandy/CGA/EGA presenter hooks are also UI pacing boundaries in
  `scripts/play.py`.  Inline-verifying the active presenter on every visible
  frame makes interactive verification much less useful; visual equivalence is
  better checked with `--verify-frames`, while live `--verify-hooks` should keep
  the viewer responsive.

Changes:

- Added `FrameSync.publish_nowait()` so `play.py` can queue the currently loaded
  video snapshot before the emulator thread reaches the next natural boundary.
- `play.py` now publishes the loaded/current snapshot once at startup without
  waiting for the SDL consumer.  This prevents the window from staying black
  while the hook verifier proves the first gameplay slice.
- Interactive presenter verification is now opt-in.  `--verify-hooks` treats the
  active presenter as a passthrough UI boundary; use `--verify-hook 1010:3354`
  or `--verify-frames` when the presenter itself is the target under test.

Validation:

```bash
python scripts/lint.py
# Lint passed for 76 Python files

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 150 --max-steps 600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=150
```

`python scripts/play.py ...` still cannot be visually re-run in the sandbox
because pygame is not installed here.  The supplied snapshot was loaded and the
headless verifier passed from that exact state.

## 2026-06-14 — interactive verify live-publish during verified parent hooks

Follow-up after testing the previous visibility patch:

```bash
python scripts/play.py --video tandy --sound adlib \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-hooks --verify-stop-on-diff
```

Finding:

- Publishing only the loaded snapshot fixed the initial black window, but not the
  real starvation path.  During a differential transaction, the live replacement
  side temporarily restored presenter/timer/retrace hooks to their install-time
  pure hooks.  That kept verification atomic, but it also meant long verified
  parent hooks could execute many visual boundaries without publishing anything
  to SDL.
- The correct split is different for the two sides of the transaction:
  - ASM oracle clone: use install-time pure passthrough hooks.
  - Live hook side: use CPU-equivalent publish-only wrappers that apply the same
    base hook side effects and queue a frame, but do not raise `FramePresented`.

Changes:

- Added `CPU8086.hook_verifier_live_passthrough_overrides`.
- `HookVerifier._LivePassthroughHooks` now prefers those live-only overrides
  while keeping the ASM oracle clone on install-time pure hooks.
- `play.py` installs publish-only live overrides for the active presenter,
  `1010:0679` timer wait, and `1010:50C9` retrace wait.  These wrappers use
  `FrameSync.publish_nowait()` and never break the verified parent routine.
- Added a regression proving live passthrough overrides can run inside a verified
  parent hook without invoking the normal frame-boundary wrapper.

Validation:

```bash
python scripts/lint.py
# Lint passed for 76 Python files

pytest -q \
  tests/test_overkill_hooks.py::test_hook_verifier_uses_base_passthrough_hooks_inside_intro_delay_loop \
  tests/test_overkill_hooks.py::test_hook_verifier_live_passthrough_override_can_publish_without_frame_boundary
# 2 passed

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 200 --max-steps 600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 20 --max-steps 80000
# OK HOOK VERIFY LIMIT REACHED verified=20

SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy timeout 10s \
  python scripts/play.py --video tandy --sound adlib \
    --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
    --verify-hooks --verify-stop-on-diff --scale 1 --no-coverage-summary
# Ran until timeout with no HookVerifyDivergence or crash printed.
```

## 2026-06-14 — interactive hook verifier yield audit

Follow-up from `play.py --video tandy --sound adlib --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-hooks --verify-stop-on-diff` feeling suspiciously smooth but not reacting to keyboard input.

Root cause: interactive live passthrough wrappers for presenter/timer/retrace correctly avoided raising `FramePresented` inside a verified parent hook, but there was no deferred yield after the parent hook finished its ASM-vs-hook diff. When a large parent such as `1010:97B2` was verified, the live side could publish and pace frames inside the transaction, yet `CPU.run()` did not return to the outer SDL/input pump until the chunk ended. That made keyboard input appear ignored and made interactive verification less honest as a gameplay test.

Fix:

- Added `CPU8086.hook_verifier_live_yield_requested` and `hook_verifier_live_yield_callback`.
- Live-side verifier passthrough wrappers now request a cooperative yield after they publish/pace.
- `HookVerifier.verify()` computes the normal diff first, then invokes the callback. In `play.py` the callback is the normal `stop_cpu_burst()`, so the outer loop pumps SDL/key events only after the verified hook has reached its continuation and compared cleanly.
- The ASM oracle clone still uses install-time pure hooks. The live side still uses publish-only wrappers only inside the verified transaction. The change is scheduler-only, not CPU-visible state.

Validation:

```text
python scripts/lint.py
# Lint passed for 76 Python files

pytest -q \
  tests/test_overkill_hooks.py::test_hook_verifier_live_passthrough_override_can_publish_without_frame_boundary \
  tests/test_overkill_hooks.py::test_hook_verifier_defers_live_passthrough_yield_until_after_diff
# 2 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 200 --max-steps 600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=200
```

## 2026-06-14 — Boss-key wait gates lifted out of unknown ASM

The F9 boss-key text screen still left a large interpreted/unknown region in
profiles while the game waited for the user to release F9, press a key, then
release the return key.  The hot part was not the text drawing itself but three
tiny interactive wait gates inside `1010:075F..07EE`:

- `1010:07C4` — `CMP byte DS:9907,01h; JE 07C4`, wait for the original F9 press
  to be released.
- `1010:07D0` — `CMP byte DS:98C3,00h; JE 07D0`, wait for any key to leave the
  fake DOS text screen.  This produced the hot `07D0/07D5` profile pair.
- `1010:07D7` — `CMP byte DS:9907,01h; JE 07D7`, wait for the return key to be
  released before restoring the game video mode.

Changes:

- Added one-iteration state-machine hooks:
  - `overkill_boss_key_f9_release_wait_gate_07c4`
  - `overkill_boss_key_any_key_wait_gate_07d0`
  - `overkill_boss_key_return_key_release_wait_gate_07d7`
- Classified these hooks under `input_menu` rather than leaving the boss-key
  wait loops as `unknown`.
- Added verifier metadata with same-IP-after-step stops for all three gates.
- Added ASM-vs-hook regression tests for both the wait and exit branches.

This deliberately does not lift the whole `075F` boss-key screen routine yet.
The screen drawing/setup executes once and is not the source of the hot loop; the
verified lift removes the runtime ASM noise while preserving the existing
interactive text-frame publishing logic.

Validation:

```bash
python scripts/lint.py
pytest -q \
  tests/test_overkill_hooks.py::test_boss_key_wait_gates_match_interpreted_state_machines \
  tests/test_overkill_hooks.py::test_input_wait_gate_hook_metadata_uses_after_step_for_same_ip_targets \
  tests/test_play_boss_key_wait.py
```

## 2026-06-14 — Object-spawn seeds and coordinate-ring frame helpers lifted

A short interactive Tandy gameplay profile showed the next useful cleanup targets were no longer renderer loops, but small raw object/state helpers:

- `1010:7547` — hot object-slot allocation gate around the existing `7573` free-slot scan, with a rare fall-through to the original `7550/BD0D` reclaim path when no free slot exists.
- `1010:A4EA` — common raw object-spawn seed template after allocation. It initializes the active/type/sprite/layer/logic/substate fields but is not yet a semantic gameplay constructor.
- `1010:A4D7` — `A4EA` plus source-coordinate copy from `DS:SI`, including the original `Y + 4` adjustment.
- `1010:9CD9` — stores the current object center into the frame coordinate ring.
- `1010:9CF1` — advances the four delayed coordinate-ring cursors with wraparound from `A33A` back to `A27A`.
- `1010:A031` — pulls delayed coordinate-ring entries into the tracked object slots referenced by `DS:A962/A964`.

These are deliberately kept as raw memory-backed helpers.  They start to expose an object-spawn/coordinate-tracking layer without naming the specific gameplay entities yet.

Changes:

- Added replacement hooks and verifier metadata for all six addresses.
- Preserved original nested-call stack scratch bytes so full-memory oracle tests match interpreted ASM, including the `CALL 7547` frames inside `A4EA/A4D7`.
- Accepted both observed instruction encodings for equivalent `ADD AX,imm` / `CMP AX,imm` forms where the packed live image differs from the static disassembly form.
- Classified the spawn helpers under `gameplay_objects` and the coordinate-ring helpers under `game_state`.

Validation:

```bash
python scripts/lint.py

python -m pytest -q \
  tests/test_overkill_hooks.py::test_object_slot_allocate_or_reclaim_7547_free_path_matches_original \
  tests/test_overkill_hooks.py::test_object_spawn_seed_a4ea_free_path_matches_original \
  tests/test_overkill_hooks.py::test_object_spawn_seed_from_source_a4d7_free_path_matches_original \
  tests/test_overkill_hooks.py::test_frame_coord_ring_helpers_match_interpreted_asm

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 200 --max-steps 500000 --fast-ranges
```

## 2026-06-14 — Text-entry keyboard-vector helpers and BIOS key flush lifted

A blind-spot pass on the remaining interactive profile showed a large amount of
apparent `unknown` time around the text-entry prompt path.  The high-level prompt
loop at `1010:53C9` remains bounded original because it is an interactive prompt
state machine, but its reusable low-level helpers are now lifted and classified:

- `1010:4E9F` — saves the current INT 09h vector at `DS:213A/213C` and installs
  OVERKILL's temporary keyboard handler at `CS:4ED2`.
- `1010:4EBF` — restores the saved INT 09h vector.
- `1010:5497` — DOS AH=07h key read wrapper used by the text-entry prompt.  It
  temporarily restores the previous INT 9 vector around DOS input, records
  extended-key state in `DS:22B2`, stores the byte in `DS:22B4`, then reinstalls
  the temporary handler.
- `1010:50AB` — clears the 128-byte OVERKILL key-state table at `DS:98C4`.
- `1010:50BA` — synchronizes BIOS keyboard-buffer tail `BDA:041C` to the head at
  `BDA:041A`, effectively flushing pending BIOS keyboard input after prompts.

This starts to separate a concrete `input_menu`/text-prompt layer from the frame
and gameplay-object islands.  The parent `53C9` loop is now documented as a
bounded original text-entry prompt rather than unexplained unknown ASM.

Validation:

```bash
python scripts/lint.py

pytest -q \
  tests/test_overkill_hooks.py::test_keyboard_state_clear_and_bios_tail_sync_50ab_50ba_match_interpreted_asm \
  tests/test_overkill_hooks.py::test_temp_keyboard_vector_install_and_restore_match_interpreted_asm \
  tests/test_overkill_hooks.py::test_text_prompt_key_read_5497_matches_interpreted_asm_regular_and_extended_keys \
  tests/test_overkill_hooks.py::test_live_verify_replacement_hooks_have_continuation_metadata

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-max 250 --max-steps 700000 --fast-ranges

python scripts/play.py --video tandy --sound adlib \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152 \
  --verify-frames --verify-frame-max 20 --verify-frame-source both
```

## 2026-06-14 - text-entry prompt loop cleanup

- Replaced `1010:53C9` with `overkill_text_entry_prompt_loop_53c9`, a one-iteration state-machine hook for the DOS text-entry prompt loop.
- The hook composes the already lifted `518C` text string loop and `5497` DOS key-read wrapper, handles the hot printable/ignored-key path locally, and leaves rare edit/finish tails at original branch targets `5408`, `541E`, and `53FC`.
- This removes the large interpreted `53C9-53EA` prompt redraw/input loop from the unknown blind-spot set while keeping the `51AB` finish dispatch visible for later classification.
- Validation: `python scripts/lint.py`; focused prompt/key-read/metadata tests; `verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 200 --max-steps 700000 --fast-ranges`.


### 2026-06-15 status/setup blind-spot cleanup

Added three small meaning-revealing hooks around the remaining status/setup
noise:

- `1010:6120 overkill_status_row_repeat_6120` is a raw repeated status/HUD
  row compositor over `5A6C` and the `613E` cursor-advance leaf.
- `1010:C51D overkill_setup_tracked_status_tail_c51d` clears the tracked
  coordinate/status globals, calls the already-lifted `8517` descriptor seed,
  and jumps into `859E`.
- `1010:859E overkill_status_cell_quad_composite_859e` is the four-cell
  status/HUD descriptor compositor parent.  It preserves the original odd
  `85B5 -> 85D5` fallthrough stack shape instead of inventing a cleaner but
  unproven subroutine boundary.

This moves another chunk of low-count unknown ASM into the `game_state` island
and clarifies the current setup/status stack without assigning higher-level HUD
semantics prematurely.

### Transition/status setup cleanup — C4DB / 9908 / 9928

- `1010:C4DB overkill_reset_object_slot_and_status_setup_c4db` is now the explicit
  transition/setup parent over the already-lifted `C4E5 -> C51D -> 859E` chain.
- `1010:9908 overkill_transition_status_wait_9908` is the frame-controller branch
  reached from the `A346` transition flag. It calls `C4DB`, adjusts `DS:2358`, and
  either returns to the `9773` setup prelude or exposes the existing `9921` wait
  checkpoint.
- `1010:9928 overkill_transition_input_release_tail_9928` closes the small tail
  after the shared `9921` latch wait by optionally writing `DS:BEFF = 02h` and
  jumping back to `9773`.

This separates another piece of the former `97B2/9773` controller blob into a
named transition/status-reset layer without inventing a higher-level game-state
model yet.

## 2026-06-15 cleanup: input release gates and spawn-anchor helper

- Lifted two cold-start / first-level input-menu wait gates that were showing as
  `unknown` in the latest profile:
  - `1010:D390 overkill_menu_fire_release_wait_d390` — one-poll FIRE/SPACE
    release wait before menu/planet transition setup.
  - `1010:D434 overkill_selector_input_release_wait_d434` — one-poll input
    release wait before falling into `D445` selector loop.
- Lifted `1010:A571 overkill_object_spawn_anchor_offset_a571`, a small raw
  object-spawn anchor helper that copies source `SS:BP` coordinates plus
  `+10/+10` into destination object slot `DS:BX`.
- These are deliberately still low-level names: `D390/D434` belong to the
  input/menu wait-state layer, while `A571` belongs to raw object-slot spawning,
  not to a confirmed semantic enemy/projectile constructor.

## 2026-06-15 deterministic input demos

Added an interactive input-demo layer for reproducing human gameplay from a
stable VM state:

- `F11` in `scripts/play.py` starts/stops recording.
- Starting a recording writes a normal snapshot under
  `artifacts/demos/demo_play_<video>_<timestamp>/snapshot`.
- While active, the player records VM-delivered keyboard scan codes and DOS text
  key values by emulated boundary index into `input_demo.json`.
- `--demo <dir-or-json>` replays the recorded input and, unless `--snapshot` is
  explicitly supplied, loads the demo's start snapshot automatically.
- Demo replay is supported by normal play, `--verify-hooks`, headless
  `--verify-frames`, and `--verify-frames --verify-frame-preview`.

Useful commands:

```bash
# Record: press F11, play, press F11 again.
python scripts/play.py --video tandy --sound adlib \
  --snapshot artifacts/snapshot_play_tandy_20260614_203152

# Replay the run normally.
python scripts/play.py --video tandy --sound adlib \
  --demo artifacts/demos/demo_play_tandy_YYYYMMDD_HHMMSS

# Verify the replay at frame level.
python scripts/play.py --video tandy --sound adlib \
  --demo artifacts/demos/demo_play_tandy_YYYYMMDD_HHMMSS \
  --verify-frames --verify-frame-source both

# Verify hooks while the demo plays for the runtime.
python scripts/play.py --video tandy --sound adlib \
  --demo artifacts/demos/demo_play_tandy_YYYYMMDD_HHMMSS \
  --verify-hooks --verify-stop-on-diff
```

The demo stores delivered VM events, not host wall-clock timestamps.  That makes
replay deterministic for oracle/candidate comparison and avoids the one-frame
input skew that can happen when SDL events are sampled independently for the two
sides of frame verification.

### 2026-06-15 demo verification fix: A571 dual ADD encoding

The first recorded gameplay demo exposed a verifier divergence at
`1010:A571 overkill_object_spawn_anchor_offset_a571` during hook verification.
The routine exists in two equivalent encodings:

- static/install-time code uses `ADD AX, imm8` (`83 C0 0A`),
- live runtime/demo snapshots can contain `ADD AX, imm16` (`05 0A 00`).

The hook now accepts both byte signatures and the regression test runs the
same ASM-vs-hook comparison against both encodings.  This keeps `A571` as a
single raw object-spawn anchor helper while avoiding a false runtime-patched-code
fallback when verifying recorded demos.

### 2026-06-15 demo-driven linked-child / movement blind-spot cleanup

Used the recorded Tandy demo `artifacts/demos/demo_play_tandy_20260615_104031`
as a representative input-driven path after the A571 signature fix.  This pass
stayed in the verified lifted-routine layer and deliberately avoided assigning
high-level enemy/projectile names.

Lifted:

- `1010:9FAF overkill_linked_object_coord_quad_update_9faf`
  - frame-controller child parent around four `9FEA` linked-object coordinate
    updates;
  - clears `DS:A39E/A39F`, uses `DS:A39A/A39C` as the two vertical offsets, and
    updates linked slots from `DS:A966/A968/A96A/A96C`;
  - the fourth child is the original fallthrough into `9FEA`, so it returns
    directly to the caller.
- `1010:A5D1/A5EA/A5F9/A607`
  - raw two-pass clamp-step helpers for object X/Y movement;
  - these preserve the odd `CALL next; body; RET back to body; RET caller`
    stack scratch pattern.
- `1010:A616/A63C/A648/A662`
  - raw vertical edge-scroll response helpers around `DS:A39A/A39C`;
  - this starts separating player/object edge-scroll bias from the larger
    object behavior family without naming the owner semantically.

Validation:

```text
python scripts/lint.py
# Lint passed for 77 Python files

pytest -q tests/test_overkill_hooks.py::test_linked_object_coord_quad_update_9faf_matches_original_parent \
  tests/test_overkill_hooks.py::test_object_two_pass_clamp_step_helpers_match_original \
  tests/test_overkill_hooks.py::test_object_vertical_scroll_edge_helpers_match_original \
  tests/test_input_demo.py tests/test_frame_verify.py
# 9 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260614_203152 --verify-max 300 --max-steps 1000000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=300

python scripts/play.py --video tandy --sound adlib --demo artifacts/demos/demo_play_tandy_20260615_104031 --verify-frames --verify-frame-max 100 --verify-frame-source both
# FRAME VERIFY OK frames=100
```

A demo run with `--verify-hooks --verify-stop-on-diff --verify-fast-ranges` ran
until sandbox timeout without divergence; during that timeout-limited window it
reported no skipped metadata and no unknown/unmeasured hook calls.

Remaining demo/cold-start blind spots are now more concentrated around:

- `1010:9B2E-9C6B` frame-controller child frontier;
- `1010:A6FD-A780` / `1010:A66F-A6B7` larger scroll/transition/object-family
  helpers;
- `1010:F225-F2AE`, `1010:AFD8-B01C`, `1010:89FF-8A20`, `1010:7CA2-7CDD` as
  object/map behavior frontiers;
- `1010:61DC-6295` status display parent, still not lifted as a whole because it
  reaches display/data-table shaped helpers and should be mapped before a parent
  replacement.


### 2026-06-15 input-demo ownership refactor

Moved deterministic input-demo recording/replay out of the OVERKILL package into
`dos_re.input_demo`.  The demo format is now explicitly reusable VM tooling: it
stores a start snapshot plus VM-delivered `scan` / `dos_key` events by emulated
boundary index, with game-specific information kept only as opaque manifest
`metadata`.

OVERKILL-specific code now only integrates the generic layer from `scripts/play.py`:

- `F11` remains the OVERKILL viewer toggle for start/stop recording;
- demo directories keep the existing `demo_play_<video>_<timestamp>` shape;
- the manifest metadata records `program=overkill`, video mode, sound mode, and
  command tail;
- `overkill/input_demo.py` is a compatibility shim that re-exports the generic
  API for older local scripts, but new code should import from `dos_re.input_demo`.

Validation:

```text
python scripts/lint.py
# Lint passed for 78 Python files

python -m pytest -q tests/test_input_demo.py tests/test_frame_verify.py
# 6 passed

python scripts/play.py --video tandy --sound adlib \
  --demo artifacts/demos/demo_play_tandy_20260615_104031 \
  --verify-frames --verify-frame-max 20 --verify-frame-source both
# FRAME VERIFY OK frames=20

python scripts/verify_hooks_headless.py \
  --snapshot artifacts/demos/demo_play_tandy_20260615_104031/snapshot \
  --verify-max 150 --max-steps 600000 --fast-ranges
# OK HOOK VERIFY LIMIT REACHED verified=150
```

### 2026-06-15 blind-spot cleanup: scroll/tile-sweep layer

Added demo-driven low-level hooks for the remaining movement/collision blind spots around the frame controller:

- `1010:AFD8 overkill_object_tile_sweep_probe_afd8` — shared object tile-sweep wrapper around the direction-specific `B00D` table. This exposes the A430 scratch globals as a raw collision/movement probe instead of anonymous object ASM.
- `1010:A66F overkill_object_scroll_world_progress_gate_a66f` — vertical-scroll/world-progress gate around the `A6FE` scroll tick.
- `1010:A6FE` / `1010:A781` — forward/backward vertical-scroll bookkeeping steps.
- `1010:A74E` / `1010:A7D0` — forward/backward row-advance side effects around the still-bounded `A7EB` display copy.
- `1010:A746` / `1010:A7E3` — tiny source-row pointer wrap leaves.

This starts separating a reusable raw layer:

```text
movement / world-scroll bookkeeping
  ├── A66F world-progress gate
  ├── A6FE/A781 forward/backward scroll ticks
  ├── A74E/A7D0 row advance side effects
  └── A746/A7E3 source-row pointer wraps

collision / tile sweep
  └── AFD8 shared object tile-sweep probe wrapper around B00D
```

No semantic level/camera/enemy names are claimed yet; these are still ASM-shaped roles verified against the DOS oracle.

### 2026-06-16 demo suffix repro tooling and AC81 flag fix

Follow-up from a long `--demo ... --verify-hooks --verify-preview --sound adlib`
run that eventually diverged at `1010:AC81 overkill_object_slot_scan_guard_ac81`
(call 177).  The reported continuation was correct (`1010:ACD9`), but the hook
left `FLAGS=0246` while the ASM oracle had `FLAGS=0206`.

Root cause: the lifted `AC81/AC97` object-slot scan does useful look-ahead when
an overlap candidate reaches the original `ACD9` continuation.  For type-4/type-5
candidate slots the hook correctly stopped at `ACD9`, but it leaked flags from
the look-ahead `CMP [BX+16h],4/5` checks.  The real CPU has not executed any
`ACD9` instruction at that boundary yet; the visible flags must still be from
the `ACD0 CMP SI,[BX+0Eh]` / `JNZ ACD9` decision.  The hook now snapshots those
entry flags and restores them before returning to `ACD9`.

Added reusable long-demo reduction tooling in `dos_re.input_demo`:

- `InputDemoPlayback.remaining_events_from_cursor(boundary=...)` returns only
  not-yet-applied events, rebased to a new boundary-zero snapshot.
- `InputDemoPlayback.write_suffix(...)` writes a new demo directory containing a
  current runtime snapshot plus the remaining input stream.
- This deliberately uses the playback cursor, not `event.boundary > boundary`,
  so same-boundary key-up/key-down events are not duplicated or dropped.

`scripts/play.py` integration:

- `--save-repro-root` controls where suffix/repro demos are written; default is
  `artifacts/repros`.
- While replaying `--demo`, `F11` now saves a suffix demo from the current point
  instead of being disabled.
- If interactive `--verify-hooks --verify-preview` diverges while replaying a
  demo, `play.py` automatically writes a suffix demo under `--save-repro-root`.
- The headless hook verifier path also writes a suffix demo on divergence when a
  demo is active.

Validation:

```text
python -m pytest tests/test_input_demo.py tests/test_overkill_hooks.py::test_ac81_slot_scan_guard_acd9_continuation_preserves_entry_cmp_flags -q
# 6 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*ac81*' --timeout 20
# 1 passed, 0 failed, 0 timed out

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 316 registered hooks, 316 metadata entries, no direct registered child calls detected.

python scripts/lint.py
# Lint passed for 81 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

A full `python scripts/run_tests.py --no-lint --timeout 20` attempt was started
but hit the sandbox command timeout before producing a final suite summary, so
only the focused validations above are claimed.

### 2026-06-16 BC45 / 62F6 logic-26 pre-scan exemption fix

A suffix repro generated by the new long-demo tooling reproduced a strict verifier
mismatch after only a few BC45 calls:

```text
python scripts/play.py --demo artifacts/repros/demo_divergence_tandy_20260616_130609 \
  --verify-hook 1010:BC45 --sound adlib --verify-max 10
# previous failure: BX asm=03C4 hook=32CC, FLAGS asm=0246 hook=0206
```

The hook reached the right continuation (`1010:AA04`) but the lifted `62F6`
overlap scan incorrectly treated logic-id `0026h` as an empty-scan sentinel.
The original path is:

```text
1010:6323  cmp ss:[bp+18],0026h
1010:6327  jnz 632C
1010:6329  jmp 741F
1010:741F  ret
```

So when `[BP+18] == 0026h`, the routine returns immediately through `741F`,
preserving caller `BX` and the zero flags from the `CMP`.  It does **not** run
the `741C ADD BX,0038` sentinel tail.  `_run_object_overlap_scan_62f6` now treats
`0026h` as a pre-scan exemption like the inactive/low-X/zero-layer/logic 0/1
paths.

Regression coverage added:

- `test_object_overlap_scan_62f6_preserves_bx_and_flags_on_logic_26_exemption`
- existing signed-X early-exit preservation test kept as a nearby guard

Validation:

```text
python -m pytest tests/test_input_demo.py \
  tests/test_overkill_hooks.py::test_object_overlap_scan_62f6_preserves_bx_and_flags_on_logic_26_exemption \
  tests/test_overkill_hooks.py::test_object_overlap_scan_62f6_preserves_bx_and_flags_on_signed_x_early_exit -q
# 7 passed

python scripts/play.py --demo artifacts/repros/demo_divergence_tandy_20260616_130609 \
  --verify-hook 1010:BC45 --sound adlib --verify-step-budget 400000 --verify-max 10
# OK HOOK VERIFY LIMIT REACHED verified=10

python scripts/play.py --demo artifacts/repros/demo_divergence_tandy_20260616_130609 \
  --verify-hooks --sound adlib --verify-step-budget 600000 --verify-max 2000
# OK HOOK VERIFY LIMIT REACHED verified=2000

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 316 registered hooks, 316 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 81 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

### 2026-06-16 crash repro snapshots for normal play

Normal interactive crashes are now captured as loadable repro snapshots under
`artifacts/repros` by default.  This covers the case where gameplay reaches an
exception or explicit fail-fast/unverified path without a recording demo.  The
snapshot directory can be passed directly back to the player:

```text
python scripts/play.py --snapshot artifacts/repros/crash_<...> --video tandy --sound adlib
```

Implementation notes:

- new generic helper: `dos_re.repro_artifacts.write_runtime_repro_snapshot`
- interactive `scripts/play.py` exception handler now writes a timestamped
  `crash_<video>_<ExceptionType>_YYYYMMDD_HHMMSS/` directory under
  `--save-repro-root`
- each crash artifact contains the normal snapshot files plus `repro.json` with
  crash context, current boundary counters, source demo/snapshot if any, and a
  traceback tail
- `--no-crash-snapshot` disables this behavior when intentionally fuzzing or
  running a noisy path
- headless hook verification also writes a crash snapshot on unexpected runtime
  exceptions; hook divergences still prefer demo suffixes when a source demo is
  available

Validation:

```text
python -m pytest tests/test_repro_artifacts.py tests/test_input_demo.py -q
# 7 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 316 registered hooks, 316 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 82 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

### 2026-06-16 collision/tile-contact micro-frontier absorption

Continued absorbing gameplay/collision logic from the latest long-demo coverage
frontier instead of spending time on the AdLib interpreted regions.  Three small
raw collision/tile helpers are now verified hooks:

- `1010:B032 overkill_object_tile_sweep_blocked_b032` — shared B00D tile-sweep
  blocked sentinel; writes `DS:A430=1` and returns to the B00D caller.
- `1010:BDD0 overkill_player_hazard_scan_guard_bdd0` — guard/setup parent for
  the existing `BDE3` player/hazard object scan; early `SS:[BP+0Ah] == 1` exits
  through `CLC; RET`, otherwise initializes the BDE3 scan registers from
  `DS:A436/A438`.
- `1010:8331 overkill_view_contact_rect_test_8331` plus tiny `1010:835B` — raw
  object-vs-view rectangle test using prepared `DS:95F2/95F4` centers and
  returning carry set only for in-window contact.

These are deliberately still low-level scratch/register helpers.  No semantic
player/enemy model was introduced.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_object_tile_sweep_blocked_b032_matches_interpreted_asm \
  tests/test_overkill_hooks.py::test_view_contact_rect_test_8331_matches_interpreted_asm_inside_and_miss \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan -q
# 3 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*b032*' --timeout 20 --no-lint
# 1 passed, 0 failed, 0 timed out

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*8331*' --timeout 20 --no-lint
# 1 passed, 0 failed, 0 timed out

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*bdd0*' --timeout 20 --no-lint
# 1 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --demo artifacts/demos/demo_play_tandy_20260615_235831 \
  --verify-hooks --sound adlib --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 320 registered hooks, 320 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 82 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out
```

Next gameplay-heavy frontiers after this patch are still the larger directional
B00D table (`B039/B07A/B0CC/B10F` families), object script region
`1010:81F4-83E9`, and the map/object stream builders around `1010:7948` and
`1010:4A65`.

### 2026-06-16 recovered source-layer seed

Started the first conservative semantic crystallisation layer under
`overkill/recovered/`.  This is deliberately not a new engine model; it is a
source-like layer over the original DOS memory image and verified CPU side
effects.

Added:

- `overkill/recovered/object_slots.py`
  - `ObjectSlotView` typed memory overlay for the observed object record.
  - Object table constants: `DS:23B4`, `0x23` records, stride `0x38`.
  - Conservative field names for repeatedly observed offsets: active word,
    X/Y words, gate/layer, link key, scan flag, hazard class, logic id.
- `overkill/recovered/coords.py`
  - small 16-bit signed/unsigned and exact CMP/SI ADD/SUB helpers.
- `overkill/recovered/collision_primitives.py`
  - recovered `8331` signed center-rectangle primitive.
  - recovered `B032` tile-sweep blocked scratch flag primitive.
  - common carry-and-return tail helper for `STC/CLC ; RET` style collision
    leaves.

Wired existing collision hooks through the recovered layer where the evidence is
already strong:

- `1010:8331 overkill_view_contact_rect_test_8331`
- `1010:BDD0 overkill_player_hazard_scan_guard_bdd0`
- `1010:BDE3 overkill_player_hazard_object_scan_bde3`
- `1010:B032 overkill_object_tile_sweep_blocked_b032`
- `1010:835B overkill_collision_clc_ret_835b`

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_view_contact_rect_test_8331_matches_interpreted_asm_inside_and_miss \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan \
  tests/test_overkill_hooks.py::test_object_tile_sweep_blocked_b032_matches_interpreted_asm -q
# 7 passed

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 320 registered hooks, 320 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 86 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --demo artifacts/demos/demo_play_tandy_20260615_235831 \
  --verify-hooks --sound adlib --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

A full `python scripts/run_tests.py --no-lint --timeout 20` command was started,
but the sandbox command timeout fired before a final summary, so this entry only
claims the focused validations above.

## 2026-06-16 - recovered source split-layer seed

Started preparing the recovered source layer for a future native source-port path
instead of only a nicer emulator path.

Added the explicit recovered-layer split:

```text
overkill/recovered/views/       DOS-memory overlays
overkill/recovered/adapters/    CPU/memory projection and ASM flag glue
overkill/recovered/domain/      pure copied source-like records
overkill/recovered/systems/     pure gameplay/system functions
```

The first portable system is now
`overkill.recovered.systems.collision.view_contact_rect_test`, the pure form of
`1010:8331`.  The hook path still uses the adapter to preserve exact `SI` and
FLAGS, but the adapter also validates that the pure system agrees with the
ASM-compatible compare sequence.

Added `ObjectSlotRecord` beside `ObjectSlotView`: the view remains the original
memory overlay; the record is the first CPU/memory-free representation that a
future source port could reuse.

Added boundary enforcement:

```text
python scripts/audit_recovered_layers.py
```

and wired the same pure-layer boundary check into `scripts/lint.py`, so modules
under `overkill.recovered.domain` and `overkill.recovered.systems` cannot import
`dos_re`, views, adapters, hooks, or gameplay code, and cannot introduce obvious
`cpu`/`mem`/`memory` references.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_view_contact_rect_test_8331_matches_interpreted_asm_inside_and_miss \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan \
  tests/test_overkill_hooks.py::test_object_tile_sweep_blocked_b032_matches_interpreted_asm -q
# 9 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 6 pure files

python scripts/audit_hook_oracle.py
# 320 registered hooks, 320 metadata entries, no direct registered child calls

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# passed for 99 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --demo artifacts/demos/demo_play_tandy_20260615_235831 \
  --verify-hooks --sound adlib --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

## 2026-06-16 - BDE3 hazard scan promoted through recovered collision layer

Continued the gradual upward refactor from address-facing hooks toward recovered
source-like gameplay code.  The BDD0/BDE3 player-hazard scan was the best next
candidate because it already repeatedly used the recovered object-slot layout:
active word, gate/layer, scan flag, hazard class, logic id, X/Y words, and link
key.

Changes:

- Added pure collision-domain `ProbePoint`.
- Added pure system helpers:
  - `word_inside_signed_center_window`
  - `slot_contains_probe_point`
  - `is_player_hazard_scan_candidate`
  - `player_hazard_scan_hit`
- Simplified `view_contact_rect_test` so it reuses the same pure centered-window
  primitive instead of carrying a separate duplicate rectangle implementation.
- Added `run_player_hazard_candidate_checks_bde3` in the adapter layer.  This is
  the only place that still performs the exact BDE3 compare sequence and applies
  CPU-visible `SI`/FLAGS side effects.
- Refactored `run_player_hazard_object_scan_bde3` into a scan/continuation shell:
  it now walks `DS:23B4`, delegates one-slot semantics to the recovered adapter,
  and owns only `BX/CX/AX/DI`, table advance, `5059` hit continuation, and final
  `CLC; RET` exhaustion.

Layering consequence:

```text
pure systems:   gameplay decision only, no CPU/memory
adapters:       exact ASM flags/register projection
hooks:          address-facing continuation shell
```

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_hit_path -q
# 9 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 6 pure files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 320 registered hooks, 320 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 99 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --demo artifacts/demos/demo_play_tandy_20260615_235831 \
  --verify-hooks --sound adlib --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

## 2026-06-16 - semantic crystallization documentation anchored

Audited the project documentation after the recovered-layer split and added a
central durable brief so future AI agents can find the intended upward refactor
without relying on chat history.

New durable document:

```text
docs/overkill/semantic_crystallization_plan.md
```

It records the north-star direction:

```text
original binary oracle
  -> interpreted ASM / exact traces
  -> ASM-compatible hooks
  -> lifted game-specific modules
  -> recovered memory views and adapters
  -> pure domain records and systems
  -> native source-port runtime
```

It also makes explicit the anti-duplication rule: once a gameplay decision has a
pure recovered system, that pure function is the canonical decision.  Hooks keep
only address/continuation glue, while adapters project DOS state and preserve
ASM-visible register/flag side effects.

Updated pointer documents:

- `AGENTS.md`
  - source-of-truth list now points to the semantic crystallization plan and
    recovered source-layer document.
  - added recovered source-port promotion rules directly to the agent guardrail
    sheet.
- `README.md`
  - added a recovered source-port direction section.
- `docs/README.md`
  - added the new plan and recovered-source-layer doc to the documentation map.
- `docs/overkill/source_port_methodology.md`
  - added the concrete `views/adapters/domain/systems` split and pointers to the
    detailed plan.
- `docs/overkill/recovered_source_layer.md`
  - added a direct pointer to the plan and an explicit anti-duplication rule.

Validation:

```text
python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 6 pure files

python scripts/lint.py
# Lint passed
```

## 2026-06-16 - B729 target-move wrapper promoted into recovered movement layer

Moved the next gameplay-significant movement frontier upward instead of adding
another isolated hook.  The hot remaining bounded region `1010:B729-B73D` is the
small object target-copy wrapper used by object behaviours before the shared
`5DB2` target-seeking movement helper:

```text
B729: SS:[BP+32h] -> DS:2304   target Y
B72F: SS:[BP+34h] -> DS:2306   target X
B735: CALL 5DB2                target-seeking movement helper
B738: CMP DS:230A,0            blocked/no-direction flag
B73D: RET
```

New hook:

```text
1010:B729 overkill_object_target_move_b729
```

The hook does not duplicate the `5DB2` direction logic.  It copies the target
pair through the recovered movement adapter, calls `5DB2` through the nested hook
boundary so verifier coverage still sees the child routine, then performs the
original `CMP DS:230A,0` and returns with those flags live.

New recovered source-port slice:

```text
overkill/recovered/domain/movement.py
overkill/recovered/systems/movement.py
overkill/recovered/adapters/movement_adapter.py
```

Pure decisions added:

```text
encode_target_seek_bits(slot, target)
choose_target_seek_direction(slot, target, direction_table)
step_delta_for_direction(direction, pixels)
```

`5DB2` now computes the portable decision first, then replays the original
ASM-compatible compare/XLAT/dispatch sequence and asserts that both paths agree.
This keeps the source-port logic canonical without losing register/flag fidelity.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_target_move_b729_matches_interpreted_wrapper_with_5db2_hook \
  tests/test_overkill_hooks.py::test_movement_direction_5db2_hook_matches_interpreted_asm_on_captured_snapshot -q
# 10 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 8 pure files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 321 registered hooks, 321 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 102 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hook 1010:B729 --verify-max 3 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=3

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000
```

Next gameplay-crystallization candidates from the supplied coverage remain:

- `1010:B0CC-B159` / `1010:B00D-B01C`: directional tile-response table family.
- `1010:9B2E-9BFA`: frame/input controller child, useful but larger and less
  isolated.
- `1010:81F4-83E9` and `1010:8B3B-8B6C`: object/script state helpers that need
  more trace classification before promotion.
- `1010:7948-7976` / `1010:7B06-7B12`: likely object/list setup or stream walk;
  classify before abstracting.

Sound/AdLib still dominates interpreted ASM, but it is not the best target for
closing gameplay semantics.

## 2026-06-16 - BFC7 type-dispatch fix for multi-part boss death

A live final-boss replay reached a `1010:BC45` divergence after the recovered
movement refactor. The failing path still returned to the correct continuation
`1010:AA04`, but the full-memory verifier showed `SS:[BP+08]` as `0022h` in the
hook and `0003h` in the ASM oracle, with live `BX=0002` in the hook and
`BX=0004` in ASM.

Disassembling the original `BFC7 -> C037` tail showed the problem: the lift had
hard-coded the type-1 dispatch tail (`C048`, `BX=0002`, `SS:[BP+08]=0000`). The
original code actually loads `BX = SS:[BP+14]`, shifts it, and jumps through the
small table at `C042`. Type-2 objects, which are used by multi-part/final-boss
pieces, take `C04E` instead and set `SS:[BP+08]=0003` while leaving `BX=0004`.

Changes:

- `_run_collision_death_tail_bfc7` now dispatches the final `C037` tail by the
  live object type at `SS:[BP+14]` instead of hard-coding type 1.
- Type 1 still takes the observed `C048` tail and writes sprite/state word `0000`.
- Type 2 takes the `C04E` tail and writes sprite/state word `0003`, matching the
  final-boss/multi-part object path.
- Other object types deliberately raise an unverified path with the original
  jump-table target.
- Added `test_bfc7_type2_death_tail_takes_c04e_dispatch_against_asm`, which runs
  raw ASM from `1010:BFC7` and compares the lifted tail against it.

Validated with focused BFC7/BC4B tests, recovered-layer audit, hook-oracle audit,
lint, and a 5,000-hook verifier pass on `demo_play_tandy_20260616_000527`.

## 2026-06-16 - C054 final-boss group transition fix

The previous `BFC7` type-2 tail fix corrected the final per-object `C037 -> C04E`
transition, but it did not explain the user's visible bug: the final boss still
appeared to die part by part. Re-disassembling `1010:C054` showed that the
`76h/77h/78h/79h` family is not a simple selector family at all.

Original flow:

```text
C054  cmp [bp+18h],0076h / 0077h / 0078h / 0079h
      jmp C15B
C15B  for DS:A8BA, A8BC, A8BE, A8C0:
        if slot != BP: call C194
      DS:A47E = 0
      DS:A8C2 = 0
C194  old_logic = DS:[BX+18h]
      DS:[BX+1Ah] = old_logic
      DS:[BX+18h] = 0001h
      DS:[BX+22h] = 0000h
      DS:[BX+08h] = 0003h
```

So the final boss/multipart death transition is a group operation. The old lift
only changed the current part in the later `BFC7` tail, leaving sibling parts in
their old `76h..79h` logic/state and making the boss visibly die in pieces.

Changes:

- Added `_run_c15b_boss_group_transition` and `_run_c194_boss_group_slot_transition`.
- `run_object_deactivate_logic_dispatch_c054` now runs the real group transition
  for logic ids `0076h..0079h` instead of returning AX selector values.
- The helper writes the nested `CALL C194` return word as freed stack scratch, so
  full-memory hook verification remains honest when C054 is called under BFC7 or
  BD17.
- Added `test_c054_logic_76_79_group_transitions_all_boss_parts_against_asm`,
  which seeds the four boss-part pointers and compares lifted C054 against raw
  original ASM.

Validation:

```text
python -m pytest \
  tests/test_overkill_hooks.py::test_c054_logic_76_79_group_transitions_all_boss_parts_against_asm \
  tests/test_overkill_hooks.py::test_bfc7_type2_death_tail_takes_c04e_dispatch_against_asm \
  tests/test_overkill_hooks.py::test_bd17_deactivate_selector_a83e_tail_matches_interpreted_asm_on_captured_snapshot -q
# 3 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/repros/demo_divergence_tandy_20260616_160515 \
  --verify-hook 1010:BC45 --verify-max 20 --verify-step-budget 1000000
# OK HOOK VERIFY LIMIT REACHED verified=20

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/repros/demo_divergence_tandy_20260616_160515 \
  --verify-hooks --verify-max 1000 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=1000

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/repros/demo_divergence_tandy_20260616_171145 \
  --verify-hooks --verify-max 2000 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=2000
```

Note on repro suffixes: `demo_divergence_tandy_20260616_160515` is the useful
pre-fix repro because it still reaches the failing transition. The later
`demo_divergence_tandy_20260616_171145` was produced from an already-advanced
post-divergence runtime point, so it can be useful as a continuation smoke test
but should not be treated as the canonical pre-hook divergence reproducer.

### 2026-06-16 verifier repros now capture pre-hook/pre-frame state

The hook-verifier divergence repro path now saves from the verifier-owned
pre-hook clone instead of the live runtime after the failing hook has already
mutated state.  This fixes the failure mode where a suffix demo could start from
an already-divergent/post-divergence point and then no longer reproduce the
original mismatch deterministically.

Implementation details:

- `dos_re.verification.HookVerifyDivergence` can now carry `repro_runtime` plus
  `repro_metadata`.
- strict hook verification captures `pre_hook_rt` immediately before executing
  the candidate hook and attaches that clone to the divergence exception.
- both headless hook verification and `--verify-preview` prefer that pre-hook
  clone when writing `demo.write_suffix(...)`; only if unavailable do they fall
  back to the live post-divergence runtime.
- hook divergence without a source demo now also writes a loadable runtime
  snapshot under `--save-repro-root`.
- frame verification gained an `on_divergence` callback.  When enabled from
  `scripts/play.py`, it captures the candidate runtime before the first
  divergent frame and writes either a suffix demo (when replaying `--demo`) or a
  runtime snapshot.

The new repro metadata includes `repro_state` values such as `pre_hook` and
`candidate_pre_divergent_frame`, so later investigations can tell whether an
artifact starts before the bad mutation or is only a live fallback.

Validation:

```text
python -m pytest tests/test_dos_re_smoke.py::test_dos_re_strict_hook_verifier_auto_continuation_catches_bad_hook_without_metadata tests/test_frame_verify.py -q
# 4 passed

python -m pytest tests/test_repro_artifacts.py tests/test_dos_re_smoke.py::test_dos_re_strict_hook_verifier_auto_continuation_catches_bad_hook_without_metadata tests/test_input_demo.py -q
# 8 passed
```

### 2026-06-16 B00D directional tile-sweep dispatcher lifted

The next gameplay-logic crystallisation step lifts `1010:B00D`, the direction
specific tile/object collision sweep called by `AFD8` after it prepares the
`DS:A430/A432/A434/A436/A438` scratch rectangle.

Recovered shape:

```text
AFD8 prepares object probe scratch globals
  -> CALL B00D
     -> CALL 5073 coordinate-to-tile index
     -> dispatch by SS:[BP+06]
        0: left
        1: left, down
        2: down
        3: down, right
        4: right
        5: right, up
        6: up
        7: up, left
     -> each cardinal body probes blocking tiles through 505B
     -> each successful step checks object hazards through BDD0
     -> blocked/contact paths tail-jump to B032, preserving the current CALL frame
```

The pure, portable part is deliberately small: `tile_sweep_plan_for_direction()`
lives in `overkill.recovered.systems.collision` and returns only the recovered
component order.  The address-facing hook keeps the ASM glue: scratch globals,
child hook boundaries (`5073`, `505B`, `BDD0`, `B032`), registers, flags, stack
scratch, and near-return/tail-jump behaviour.

Important nuance: diagonal entries use real `CALL` + fallthrough composition.
If the first cardinal component tail-jumps to `B032`, the `RET` returns to the
second component, not to B00D's external caller.  The lifted hook preserves this
by simulating the internal CALL frame before running the first component.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_tile_sweep_dispatch_b00d_matches_interpreted_direction_table -q
# 10 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 8 pure files

python scripts/audit_hook_oracle.py
# 322 registered hooks, 322 metadata entries, no direct registered child calls detected

python scripts/lint.py
# Lint passed for 102 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 3000 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=3000
```

## 2026-06-16 - Runtime world projection tooling for level/editor evidence

Added a first evidence-gathering layer for future level-editor and source-port
work:

- `overkill/recovered/domain/world.py` defines pure runtime-world projection
  records that do not import the VM.
- `overkill/recovered/adapters/world_adapter.py` projects the DOS runtime into
  those records.
- `scripts/dump_world.py` dumps known object/effect slots, pointer tables,
  boss-group pointers, and important globals from a snapshot or input-demo start
  snapshot.
- `scripts/trace_world_writes.py` traces writes to those recovered world regions
  so we can identify materialisation/setup routines instead of guessing where
  level/object data comes from.

Important clarification discovered while preparing the dump layer:

```text
DS:23B4  0x23 records, stride 0x38  effect/contact slots walked by BDD0/BDE3/AC81
DS:2B5C  0x22 records, stride 0x38  main gameplay object slots before the DS:32CA pointer table
DS:32CA  pointer table used by update/draw/present scans
DS:8D12  compact/effect pointer table used by compact-layer scans
```

The older `ObjectSlotView.table_slot()` constants remain the DS:23B4 scan-family
view for compatibility, but the new world dump explicitly models both slot
families.  This is useful for level-editor work because it separates the live
object/effect record pools from the pointer tables that order update/render
passes.

Example commands:

```text
python scripts/dump_world.py --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --active-only --summary -o artifacts/world_dump_demo_20260616_000527_start.json

python scripts/trace_world_writes.py --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --max-steps 1000 -o artifacts/world_write_trace_demo_start_1000.json
```

## 2026-06-16 - Enriched world-write materialisation traces

Expanded the runtime-world tracing tools so write traces are no longer raw
linear-memory events only:

- `trace_world_writes.py` now decorates each event with writer island/symbol and
  a decoded target (`object_slot_field`, `pointer_table_entry`, `runtime_global`,
  or `boss_group_pointer`).
- `world_adapter.describe_world_write_target()` maps traced region offsets back
  to slot table, slot index, record offset, and currently known field name.
- `world_adapter.resolve_pointer_value()` resolves 16-bit old/new pointer values
  back to recovered slot tables when possible.
- `scripts/summarize_world_writes.py` groups trace events by writer, target, and
  target family, and highlights repeatedly written unknown object fields.
- Added regression tests for target decoding and summary grouping.

Generated example artefacts from `demo_play_tandy_20260616_000527`:

```text
artifacts/world_write_trace_demo_20260616_000527_enriched_20000.json
artifacts/world_write_summary_demo_20260616_000527_enriched_20000.json
```

Early conclusions from that trace:

```text
1010:35CF is Tandy renderer interior writing +0C, so +0C should be treated as draw/address scratch evidence, not level semantics.
1010:5A36 writes +12 from coordinate row-address logic.
1010:5DB2 writes +06 together with x/y from movement direction logic.
1010:AB10 and 1010:B86D write +08 together with x/y/target fields from object behavior code.
1010:7524 advances DS:95D8, strengthening the allocator-cursor interpretation.
```

This is intentionally not a field rename yet.  It gives the next crystallisation
step a stronger evidence map: promote only after the same offset's role converges
across writers, hooks, snapshots, and gameplay observations.

## 2026-06-16 - Gameplay crystallisation: movement step unification and B1B0 chase behavior

Refocused away from level-editor/tooling work and back onto gameplay/source-port
crystallisation.

Movement cleanup:

- Introduced `MovementStepOperation` in `overkill.recovered.domain.movement`.
- Added pure `step_operations_for_direction(direction, pixels)` in
  `overkill.recovered.systems.movement`.
- Moved the repeated AEE4/AF22/AF63 direction-step axis order into that pure
  recovered system.
- Added `apply_direction_step_to_current_object()` in the adapter layer so the
  hook path still materialises the exact original ADD/SUB memory operations and
  preserves live flags.

This removes three copies of the same eight-way movement table logic while
keeping the VM-facing flag/register behavior in the adapter layer.

New gameplay hook:

- Added `1010:B1B0 overkill_object_player_chase_b1b0`.
- Added recovered pure helpers for the player/view-centered chase target and the
  B15A target-candidate predicate.
- The unacquired phase now projects `DS:237E/2380` into the aligned 5DB2 target
  globals, runs the verified 5DB2 seeker, and only enters the B15A acquisition
  scan when movement reports blocked.
- The acquired phase validates `SS:[BP+30h]`, computes deltas through 5E1B,
  steers via runtime-patched 5E42, and rejoins the already lifted AD5A/AD60
  bounds tails.
- The helper `B15A` is modelled as a recovered rotating candidate scan over the
  `DS:23B4` effect/contact slot pool, using `DS:A43A` as the scan cursor.

This closes the hot `1010:B1B0-B1F3` interpreted gameplay cluster while moving
its stable decisions into the recovered source layer rather than adding another
isolated hook body.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_player_chase_b1b0_matches_interpreted_asm_key_paths \
  tests/test_overkill_hooks.py::test_movement_dir_step_tables_match_interpreted_asm_all_directions -q
# 14 passed
```


## 2026-06-16 - B1B0 behavior refactor: canonical chase predicates and adapter glue

Cleaned up the newly lifted B1B0 player/view-centered chase behavior so the
hook body is closer to a recovered source procedure and less like a pile of
inline compare logic.

Refactor details:

- Added `is_player_chase_acquired_target_valid()` in
  `overkill.recovered.systems.objects`.
- Added `run_player_chase_candidate_checks_b15a()` and
  `run_player_chase_acquired_target_validity_b1b0()` in
  `overkill.recovered.adapters.object_behavior_adapter`.
- Moved the B1BF view-target setup into
  `run_player_center_target_setup_b1bf()` in the movement adapter.
- Removed the duplicate inline B15A candidate gate and acquired-target validity
  chain from `overkill.gameplay.object_runtime`.

The source-port ownership is now clearer:

```text
recovered.systems.objects     owns B15A/B1B0 candidate/validity decisions
recovered.systems.movement    owns view/player-center target projection
recovered.adapters.*          replays exact CMP/MOV/ADD/AND order for flags
object_runtime.B1B0           owns behavior control flow and continuations
```

This keeps the pure gameplay decisions canonical while preserving the exact
ASM-visible flags/register/memory behavior in the adapter layer.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 14 passed

python -m pytest \
  tests/test_overkill_hooks.py::test_object_player_chase_b1b0_matches_interpreted_asm_key_paths \
  tests/test_overkill_hooks.py::test_movement_dir_step_tables_match_interpreted_asm_all_directions -q
# 2 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 10 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/lint.py
# Lint passed for 109 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed

timeout 90s env SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 - Recovered layout constants and shared direction crystal

Refactored a set of proven duplicate constants so future gameplay cleanup can
refer to the same recovered source facts instead of scattering magic offsets and
direction tables through hook bodies.

Changes:

- Expanded `overkill.recovered.views.object_slots` into the canonical place for
  recovered 0x38-byte object-slot layout offsets.
- Added context aliases for reused fields, especially the important `+14` / `+16`
  pair:
  - `OFF_SCAN_FLAG` / `OFF_OBJECT_TYPE`
  - `OFF_HAZARD_CLASS` / `OFF_DRAW_LAYER`
- Added named table bounds:
  - `EFFECT_OBJECT_TABLE_END`
  - `GAMEPLAY_OBJECT_LAST_SLOT_BASE`
  - `GAMEPLAY_OBJECT_TABLE_END`
  - `GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL`
- Added `overkill.recovered.domain.directions` as the single pure source for the
  recovered clockwise 8-way direction order.
- Reused that direction crystal from both:
  - `systems.movement.step_operations_for_direction()`
  - `systems.collision.tile_sweep_plan_for_direction()`
- Promoted repeated gameplay predicate constants in:
  - `systems.collision` for BDE3 hazard candidate gates and contact half-extent,
  - `systems.objects` for B1B0/B15A chase target gates,
  - `systems.movement` for B1BF view-center target biases and the 4px grid mask.
- Updated adapters to import these constants while keeping the exact original
  compare order where flags matter.
- Updated world write tracing so newly understood offsets like `+1A`, `+1C`,
  `+22`, `+30`, `+32`, `+34` are no longer reported as unknown pressure.

Important note: this does **not** claim that every table uses the same semantic
meaning for each offset. It records one proven binary layout with context aliases
where the same byte offset has different source-like names in different routines.
That is closer to the likely original C/ASM source shape than parallel magic
numbers in each hook.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py tests/test_world_trace_tools.py \
  tests/test_overkill_hooks.py::test_object_player_chase_b1b0_matches_interpreted_asm_key_paths \
  tests/test_overkill_hooks.py::test_movement_dir_step_tables_match_interpreted_asm_all_directions \
  tests/test_overkill_hooks.py::test_object_tile_sweep_dispatch_b00d_matches_interpreted_direction_table \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan -q
# 21 passed

python -m pytest tests/test_overkill_hooks.py \
  -k '7573 or 7524 or b1b0 or b00d or bdd0 or bde3 or 62f6 or bc45 or bfc7 or c054 or movement_dir_step' -q
# 23 passed, 215 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 11 pure files

python scripts/lint.py
# Lint passed for 110 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 - Tilemap probe/lookup source crystal

Refactored the shared tilemap helpers instead of adding another gameplay hook.
The important cleanup was that `5073` and `505B` existed twice: once as public
collision hooks and once as private in-place mirrors inside object behavior
tails.  Both copies now delegate to one recovered adapter, and that adapter
validates one pure source-like tilemap system.

Changes:

- Added pure records in `overkill.recovered.domain.tilemap`:
  - `TileProbeInput`
  - `TileProbeResult`
  - `TileLookupInput`
  - `TileLookupResult`
- Added pure portable logic in `overkill.recovered.systems.tilemap`:
  - `compute_tile_probe_5073()`
  - `lookup_tile_class_505b()`
- Added adapter glue in `overkill.recovered.adapters.collision_adapter`:
  - `run_tile_probe_5073_body()`
  - `run_tile_lookup_505b_body()`
- Reduced `gameplay.collision.run_tile_probe_5073()` and
  `gameplay.collision.run_tile_lookup_505b()` to patch-guard wrappers.
- Reduced the older private `_run_tile_probe_5073()` / `_run_tile_lookup_505b()`
  mirrors in `gameplay.object_runtime` to delegates, so parent tails no longer
  carry their own copy of tilemap arithmetic.

Recovered source facts made explicit:

```text
5073 adjusted_x = DS:234E + object.x
5073 stores adjusted_x into DS:215A
if adjusted_x is signed-negative: BX = FFFFh
otherwise:
  x_tile = adjusted_x >> 4
  y_tile = (object.y & FFF0h) >> 4
  BX = DS:2350 - x_tile * 13 + y_tile

505B raw_tile = ES:[BX], where ES = CS:[9592]
505B class_byte = DS:C3AA[raw_tile]
```

This gives movement/collision/tile probing one canonical source-like arithmetic
home while preserving the original instruction-shaped flags/register effects in
the adapter.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k '5073 or 505b or 4ff9 or ac28 or b00d or b1b0 or b729 or movement_dir_step' -q
# 23 passed total across the focused runs used during this patch

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/lint.py
# Lint passed for 112 Python files

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 - AC97 overlap-scan source cleanup

Refactored the hot `1010:AC97` object-overlap scan without changing its hook
boundary.  The previous lift already consumed the ACD9->ACD2 non-actionable tail,
but it still kept the slot candidate, rectangle, link-key, and type-4/type-5
decisions inline in `gameplay.collision`.  That duplicated the style of the
already-cleaned `BDE3` hazard scan and made the source-port layer less obvious.

Changes:

- Added pure record `ObjectOverlapScanDecision` in
  `overkill.recovered.domain.collision`.
- Added pure portable logic in `overkill.recovered.systems.collision`:
  - `object_overlap_scan_decision()`
  - `OBJECT_OVERLAP_SCAN_REQUIRED_FLAG`
  - `OBJECT_OVERLAP_INACTIVE_LOGIC_ID`
  - `OBJECT_OVERLAP_ACTIONABLE_CLASSES`
- Added ASM-compatible adapter glue:
  - `run_object_overlap_candidate_checks_ac97()`
- Reduced `gameplay.collision.run_object_slot_scan_ac97()` to the scan shell:
  `BX/CX` loop, final `CLC;RET`, or exact stop at `ACD9` with the pre-ACD9 CMP
  flags restored.

Recovered source facts now live in one place:

```text
AC97 overlap candidate:
  active_word != 0
  logic_id != 0001h
  scan_flag == 0001h
  probe point lies inside signed inclusive +/-16 object window
  current.link_key != slot.link_key

AC97 actionable overlap:
  candidate && hazard_class in {0004h, 0005h}
```

The scan is still deliberately named as an overlap/contact scan, not as a
semantic enemy/player rule.  It uses the same DS:23B4 pool as `BDE3`, but its
candidate gates and actionable classes are distinct and therefore stay separate
from the player-hazard predicate.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_slot_scan_ac97_hook_matches_interpreted_asm_on_captured_snapshot \
  tests/test_overkill_hooks.py::test_object_slot_scan_ac97_absorbs_non_actionable_acd9_continue_tail \
  tests/test_overkill_hooks.py::test_ac81_slot_scan_guard_acd9_continuation_preserves_entry_cmp_flags -q
# 19 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 AA71 post-move contact-window source cleanup

Continued the gameplay crystallization pass by moving the recovered `1010:AA71`
BC4B post-move contact-window decision out of the address-facing gameplay hook
and into the recovered source layer.

Changes:

- Added `PostMoveContactWindow` to `overkill.recovered.domain.collision`.
- Added pure portable logic in `overkill.recovered.systems.collision`:
  - `postmove_contact_window_test_aa71()`
  - `POSTMOVE_CONTACT_Y_UPPER_BIAS/SPAN`
  - `POSTMOVE_CONTACT_X_NORMAL_*`
  - `POSTMOVE_CONTACT_X_BOSS_*`
- Added ASM-compatible adapter glue:
  - `run_postmove_contact_window_aa71_body()`
- Reduced `gameplay.collision.run_postmove_contact_window_aa71()` to an
  address-facing wrapper.

Recovered source facts:

```text
AA71 contact window:
  negative signed X -> miss
  Y uses signed bounds around DS:2380 with +18h / -2Ch shape
  normal X uses unsigned bounds around DS:237E with +18h / -2Ch shape
  final-boss mode DS:A8C2 == 1 narrows only X to +08h / -0Ch
```

This avoids duplicating AA71 contact-window rules in hook code.  The pure system
owns the gameplay decision; the adapter still replays the original compare/add
sequence so `AX`, flags, and `CLC/STC;RET` behavior remain verifier-compatible.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py -q
# 18 passed

python -m pytest tests/test_overkill_hooks.py -k 'aa71' -q
# 5 passed, 233 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-16 shared object-centered probe-window adapter cleanup

Continued the collision crystallization pass by deduplicating the verifier-visible
object-centered `+/-16` rectangle compare sequence used by the BDE3 player-hazard
scan and the AC97 object-overlap scan.

Changes:

- Added `run_slot_probe_window_compare_sequence()` in
  `overkill.recovered.adapters.collision_adapter`.
- Rewired:
  - `run_player_hazard_candidate_checks_bde3()`
  - `run_object_overlap_candidate_checks_ac97()`
- Kept the pure gameplay decisions in `overkill.recovered.systems.collision`:
  - `player_hazard_scan_hit()`
  - `object_overlap_scan_decision()`

Recovered source fact:

```text
BDE3 and AC97 use the same object-centered SI compare choreography:
  SI = slot.x + 10h; CMP probe_x, SI
  SI -= 20h;         CMP probe_x, SI
  SI = slot.y + 10h; CMP probe_y, SI
  SI -= 20h;         CMP probe_y, SI

BDE3 is strict:    lower < probe < upper
AC97 is inclusive: lower <= probe <= upper
```

This keeps one canonical adapter implementation for the CPU-visible compare
sequence while leaving the scan-specific gate predicates and pure gameplay
meaning separate.  It also documents a real uncertainty resolution: BDE3 and
AC97 are related contact-window scans, but they intentionally differ at the
edges and should not be collapsed into one gameplay predicate.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_object_slot_scan_ac97_hook_matches_interpreted_asm_on_captured_snapshot \
  tests/test_overkill_hooks.py::test_object_slot_scan_ac97_absorbs_non_actionable_acd9_continue_tail \
  tests/test_overkill_hooks.py::test_ac81_slot_scan_guard_acd9_continuation_preserves_entry_cmp_flags \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_hit_path -q
# 23 passed
```

Additional validation for this cleanup:

```text
python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 4FF9 tile/contact probe sampling-plan cleanup

Continued the recovered-source cleanup by pulling the remaining source-like
sampling decisions out of the `1010:4FF9` tile/contact probe wrapper.

Changes:

- Added pure tilemap domain/system support:
  - `TileContactProbePlan`
  - `is_tile_contact_side_valid_4ff9()`
  - `tile_contact_probe_plan_4ff9()`
  - `tile_contact_offset_table_byte_offset()`
- Added `run_tile_contact_probe_4ff9_body()` in
  `overkill.recovered.adapters.collision_adapter`.
- Reduced `overkill.gameplay.collision.run_tile_contact_probe_4ff9()` to an
  address-facing patch-guard wrapper.

Recovered source facts now named in one place:

```text
4FF9 tile/contact probe:
  side selector [BP+8] must be < 3
  side selector indexes 4-byte dx/dy pairs at DS:214E
  after 5073, DS:215A low nibble chooses one or two column samples
    <= 0Ah -> one column
    >  0Ah -> two columns
  adjusted Y low nibble controls the optional adjacent-Y lookup
  row delta is the same recovered tile-column stride: 13
```

This removes another long mixed block from `gameplay/collision.py` and keeps the
pure sampling plan portable while the adapter preserves the original stack
restore, BX/CX loop, `505B` calls, and CF result.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_tile_contact_probe_4ff9_matches_interpreted_asm_paths \
  tests/test_recovered_semantics.py::test_recovered_tile_contact_probe_plan_is_pure_4ff9_sampling_shape -q
# 2 passed

python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k '4ff9 or 5073 or 505b or ac28 or b00d or ac97 or bde3 or aa71' -q
# 14 passed, 243 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/audit_islands.py --all-hooks
# passed, no unclassified unknown hooks

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 AC28 tile-collision probe sampling cleanup

Continued the gameplay/source-crystallization cleanup by pulling the remaining
source-like sampling plan out of the `1010:AC28` tile-collision probe.  This is
the ABxx object-behaviour collision helper that reuses the shared `5073` tile
coordinate probe and `505B` tile-class lookup.

Changes:

- Added pure tilemap support:
  - `TileCollisionProbePlan`
  - `tile_collision_probe_plan_ac28()`
- Added `run_tile_collision_probe_ac28_body()` in
  `overkill.recovered.adapters.collision_adapter`.
- Reduced `overkill.gameplay.collision.run_tile_collision_probe_ac28()` to an
  address-facing patch-guard wrapper.
- Added an oracle regression test that loads real AC28/505B/5073 bytes and
  compares interpreted ASM against the hook for clear, direct-blocked, and
  adjacent-Y-blocked paths.

Recovered source facts now named in one place:

```text
AC28 tile-collision probe:
  first checks global gates DS:A47C and DS:BDAC
  calls 5073 for object coordinate -> tile offset
  samples one row below the object using the recovered tile stride 13
  if object Y low nibble is nonzero, also samples the adjacent Y tile
  on collision, writes object +24h = 0005 and decrements object +20h
  when the countdown reaches zero, clears +24h and returns CF set
```

This keeps the gameplay-facing wrapper small while preserving the exact
ASM-visible global gates, `5073`/`505B` calls, stack/return behavior, counter
side effects, and carry result in the adapter.

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k 'ac28 or 4ff9 or 5073 or 505b or b00d or ac97 or bde3 or aa71' -q
# 16 passed, 243 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 13 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/lint.py
# Lint passed for 112 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 BCB1/C054 source-cleanup pass

Continued the gameplay/source-crystallization cleanup by targeting two places
where already-understood logic was still duplicated or hidden behind magic
constants in address-facing code.

Changes:

- Added pure post-move Y clamp support:
  - `PostMoveYClampResult`
  - `clamp_postmove_y_bcb1()`
  - shared adapter `run_postmove_y_clamp_bcb1_body(pop_return=...)`
- Replaced the duplicate inline `_run_y_clamp_bcb1` implementation inside the
  larger `BC4B/BFC7` parent chain with the same adapter used by the public
  `1010:BCB1` hook.  The public hook consumes the near return; the composed
  parent path does not.
- Added pure C054 deactivate-dispatch classification:
  - `ObjectDeactivateDispatchDecision`
  - `object_deactivate_dispatch_decision_c054()`
  - named selector families for boss-group transition, counter-drop, and AX
    script-selection paths.
- Kept the original C054 `CMP` order in `overkill.gameplay.collision` so flags
  remain oracle-compatible, while asserting that the pure recovered dispatcher
  classification agrees with the ASM-shaped path.

Recovered source facts now centralized:

```text
BCB1:
  clamp current object Y into signed inclusive 0000h..00C0h

C054:
  logic 0076..0079 -> multi-part boss group transition
  selected logic ids -> decrement DS:A47E counter family
  logic 0093 -> same counter family plus debug/status byte DS:98A8 = 1
  selected logic ids -> AX script address selection for caller follow-up
```

Validation:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k 'bcb1 or c054 or bfc7 or bd17 or bc4b or aa71 or ac28 or 4ff9 or ac97 or bde3' -q
# 35 passed, 226 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/lint.py
# Lint passed for 113 Python files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 C054/C15B/C194 boss-group adapter cleanup

Continued source-crystallization cleanup after the BCB1/C054 pass.  The C054
classifier was already pure, but the C15B/C194 boss-group transition itself was
still embedded in `overkill.gameplay.collision` with raw offsets and globals.
This pass moved that ASM/DOS glue into the recovered object-behavior adapter and
kept only the address-facing C054 entry point in gameplay code.

Changes:

- Added live object-slot properties for repeatedly proven transition fields:
  - `sprite_or_state`
  - `logic_id` setter
  - `previous_logic_id`
  - `transition_latch`
- Added pure boss-group transition records/helpers:
  - `BossGroupSlotTransition`
  - `boss_group_transition_targets(...)`
  - `boss_group_slot_transition_c194(...)`
- Added recovered adapter glue:
  - `run_boss_group_slot_transition_c194(...)`
  - `run_boss_group_transition_c15b(...)`
  - `run_object_deactivate_logic_dispatch_c054_body(...)`
- Removed the C194/C15B implementation from `overkill.gameplay.collision`; that
  module now exposes only the address-facing `run_object_deactivate_logic_dispatch_c054(...)` wrapper.
- Fixed a small duplicated `view_contact_centers(cpu)` call in the 8331 wrapper.

Recovered source split is now clearer:

```text
recovered.systems.objects
  owns pure C054/C15B/C194 classification and state-update facts

recovered.adapters.object_behavior_adapter
  owns DOS globals, CMP order, CALL scratch words, AX/debug side effects

gameplay.collision
  owns only the exported address-facing C054 entry point
```

Validation:

```text
python -m pytest tests/test_recovered_semantics.py::test_recovered_boss_group_transition_targets_and_slot_state_are_pure \
  tests/test_recovered_semantics.py::test_recovered_c054_deactivate_dispatch_classification_is_pure_and_named \
  tests/test_overkill_hooks.py::test_c054_deactivate_dispatch_0013_selects_a4e4 \
  tests/test_overkill_hooks.py::test_c054_logic_76_79_group_transitions_all_boss_parts_against_asm -q
# 4 passed

python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py -k 'c054 or c15b or c194 or bfc7 or bd17 or bcb1 or bc4b or aa71 or ac28 or 4ff9 or ac97 or bde3' -q
# 35 passed, 227 deselected

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 14 pure files

python scripts/audit_hook_oracle.py
# 323 registered hooks, 323 metadata entries, no direct registered child calls detected

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 113 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --verify-hooks --verify-max 100 --verify-step-budget 800000
# OK HOOK VERIFY LIMIT REACHED verified=100
```

## 2026-06-17 - AA46 view/contact projection cleanup

Continued the gameplay crystallisation cleanup by removing the remaining
hand-written AA46 rectangle-test body from `overkill/gameplay/view_window.py`.
AA46 is the BCCB contact path for object-type-1 records: it projects a selected
DS:214E dx/dy pair from the live view globals (`DS:237E/2380`) into the prepared
contact-center globals (`DS:95F2/95F4`) and then runs the same signed +/-16
rectangle test as `1010:8331`.

Changes:

- Added pure source-like projection
  `recovered.systems.collision.view_contact_center_from_offsets_aa46(...)`.
- Added adapter glue
  `recovered.adapters.collision_adapter.run_view_window_check_aa46_body(...)`.
- Replaced `gameplay/view_window.py` with a thin address-facing compatibility
  wrapper around the recovered adapter.
- AA46 now shares the canonical `run_signed_center_rect_test_8331(...)` adapter
  instead of carrying a second copy of the SI/FLAGS rectangle choreography.

This keeps the semantic claim narrow: AA46 is not a new collision system.  It is
an offset-table contact-center projection followed by the already-recovered 8331
object/contact rectangle test.

Validation:

```bash
python -m pytest tests/test_recovered_semantics.py::test_recovered_aa46_view_window_projection_reuses_8331_adapter -q
python -m pytest tests/test_recovered_semantics.py tests/test_overkill_hooks.py -k 'aa46 or 8331 or aa71 or bc4b or bfc7 or c054' -q
python scripts/audit_recovered_layers.py
python scripts/lint.py
python scripts/audit_hook_oracle.py
python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
SDL_VIDEODRIVER=dummy python scripts/play.py --sound adlib --demo artifacts/demos/demo_play_tandy_20260616_000527 --verify-hooks --verify-max 100 --verify-step-budget 800000
```

Observed result: all focused tests/audits passed and the smoke verifier reached
`OK HOOK VERIFY LIMIT REACHED verified=100`.

## 2026-06-17 - hook registry cleanup: object-runtime frontier split

Refactored the hook-registration layer without changing gameplay behavior.  The
main cleanup was moving the object-slot allocation/spawn/movement and observed
object-family wrappers out of the aggregate `overkill/hooks.py` into:

```text
overkill/hook_wrappers/object_runtime_frontiers.py
```

`overkill/hooks.py` remains the compatibility import surface that registers and
re-exports all known `overkill_*` hook names, but the object-runtime CS:IP glue
now sits next to the other hook-wrapper modules.  Shared overlay-signature
fallback helpers were promoted into `overkill/hook_wrappers/common.py`, so future
wrapper modules do not need to copy the local `_code_matches` / single-step
bounded-original fallback idiom.

Additional cleanup:

- Added explicit `__all__` re-export contracts to the stable wrapper modules.
- Replaced long explicit wrapper import lists in `overkill/hooks.py` with compact
  side-effect/re-export imports.
- Kept the refactor strictly at the wrapper/registry layer; no object semantics,
  hook continuations, or recovered gameplay decisions changed.

Validation:

```bash
python scripts/lint.py
python scripts/audit_hook_oracle.py
python scripts/audit_recovered_layers.py
python scripts/audit_islands.py --all-hooks
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_player_chase_candidate_scan_b15a_matches_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_children_a515_a584_match_interpreted_paths \
  tests/test_overkill_hooks.py::test_frame_action_spawn_fanout_a067_matches_interpreted_paths -q
SDL_VIDEODRIVER=dummy python scripts/play.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --video tandy --sound pc --verify-hook 1010:A067 --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
SDL_VIDEODRIVER=dummy python scripts/play.py --snapshot artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042 --video tandy --sound pc --verify-hook 1010:9B2E --verify-max 1 --verify-step-budget 300000 --no-coverage-summary
```

All focused checks passed.  The broader `tests/test_core.py` still has the known
pre-existing coverage-classifier expectation mismatch for `1010:9B34` / `9B2E`
(`input_menu` expected by the stale test, `game_state` returned by the current
classifier), which was already present before this cleanup.
## 2026-06-17 AED8/B250 overlap-contact branch from crash repro

The interactive Tandy/AdLib repro `crash_tandy_RuntimeError_20260617_201926` hit
the intentionally fail-fast path `AED8 -> B250 -> B254`.  This was not a wrapper
relocation regression; it exposed that AED8 reaches the same B250 overlap/contact
selector previously lifted only inside the B24D frontier.

Cleanup/fix in this pass:

- Extracted `_run_b250_overlap_contact_selector` as the single source of truth
  for the B250..B2A3 selector.
- `B24D` now calls the shared selector and still stops at the selected AD5A/ADC9
  frontier as before.
- `AED8` now calls the same selector and composes the selected tail to its own
  near-return boundary:
  - `AD5A`: add `DS:A278` to X, then run the shared AD60 bounds/tile tail.
  - `ADC9`: set X to `FFFFh`, then run the same AD60 tail without the AD5A
    pre-add.
- Added `artifacts/evidence/snapshot_stop_1010_aed8_b250_overlap` and a focused
  ASM-vs-hook regression test for the repro branch.

Validation:

```text
python -m pytest tests/test_overkill_hooks.py::test_object_behavior_aed8_b250_overlap_branch_matches_interpreted_repro tests/test_overkill_hooks.py::test_object_behavior_b24d_hook_matches_interpreted_observed_path -q
# 2 passed

python scripts/play.py --snapshot artifacts/evidence/snapshot_stop_1010_aed8_b250_overlap --video tandy --sound adlib --verify-hook 1010:AED8 --verify-max 1 --verify-step-budget 200000 --no-coverage-summary
# OK HOOK VERIFY LIMIT REACHED verified=1
```


## 2026-06-19 Refactor plan Phases 1-2 complete; Phase 3 started

Driving `docs/overkill/refactor_plan.md` (readable-yet-verifiable reconstruction).

- **Phase 1 (dead-state scratch): done earlier this cycle** — `_remember_balanced_push_scratch` + inline `sp-2` writes retired; live `saved_cx` kept.
- **Phase 2a (typed views): done.** Every raw SS:BP / DS:BX object-record access in
  gameplay now goes through `ObjectSlotView` (`slot`/`dst`/`cand`). Finished
  object_movement (5e1b/9fea/a66f), contact_side_effects (bec5 + 62F6 scan),
  object_runtime (5A92/5AC8/7596/AA2B dispatch helpers), object_spawns (95D8/7573
  free-slot allocators). Only the deliberate `OFF_SUBSTATE_1E` semantic alias
  remains raw by design.
- **Phase 2b (DS-global reconciliation): done.** New `overkill/recovered/ds_globals.py`
  is the single definition site for the 7 cells genuinely shared across subsystems
  (VIEW_TARGET_X/Y, VIDEO_MODE_SELECTOR_OFF, COLLISION_DEBUG_FLAG/CODE,
  BOSS_GROUP_LATCH, CONTACT_DISPATCH_GATE); subsystem modules keep local names as
  `LOCAL = CANONICAL` aliases. Design call: single-subsystem globals stay local;
  same-valued-but-distinct literals (0x00xx) are not merged.
- **Phase 3 (de-transliterate hook bodies): started.** Method: per function, the
  *last* flag-affecting op before each boundary is live; earlier ones overwritten
  before a boundary are dead. Removed dead `_cmp_word`/`set_*_flags` + collapsed
  register-juggling temps in `_run_object_behavior_ae09` and `_run_object_logic_ab10`.
  Each slice verified *exercised* (instrument+count: ae09 951x, ab10 1398x in the
  150-frame demo window) before commit; `_run_object_behavior_8d4f`'s analogous
  removal was **reverted** because it had 0 demo invocations and no oracle — unverifiable.

Gates after each slice: oracle 244/244, demo-replay 19/19, lint 147 files.

## 2026-06-19 (cont.) Phase 3 de-transliteration sweep — object_behaviors + game_state

Method: per function, only the last flag-affecting op before each boundary is
live; earlier `_cmp_word`/`set_*_flags` overwritten before a boundary are dead.
Each slice verified *exercised* via invocation-count instrumentation + 150-frame
demo-replay before commit (the real gate; most behaviors have no per-hook oracle).

object_behaviors (now thoroughly cleaned):
- AE09, AB10, ABA3, B9F0, B73E (idle NEG/ADD + B800-spawn path), AD04, B86D (8
  sites incl. the formation chain whose "preserved for flags" warning was
  over-cautious). Remaining sites are intentional: AB10's live y-ADD (reaches
  RET) and 8D4F's removal (reverted earlier — 0 demo invocations, unverifiable).

game_state:
- 9CD9 tracked-coord store (first +8 ADD dead, second reaches RET), the
  _advance_coord_ring_ptr +4 ADD, 9CF1's 98BE TEST, and 99CD's first coord +8.
- Left live/intentional: _add_bl_ah (helper whose ADD flags ARE its result),
  _inc_reg8_preserve_cf (deliberate preserve-CF), input TEST sites (863/874).

Remaining Phase 3 surface: ~12 more game_state set_*_flags sites (per-site
analysis; several live), frame_orchestration (16), object_spawns (10), plus a
dead-`_cmp_word` sweep. Gates green throughout: oracle 244/244, demo-replay 19/19.
