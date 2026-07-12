# Campaign: FRONT-END (tier: SCREEN-exact)

**Scope.** Reproduce the original's cold-start front-end faithfully in play_native: intro → title/menu
→ attract (the demo-after-idle) → level-select → level-start plaque → gameplay, each screen and
transition matching the original — replacing play_native's app-layer approximations.

**Done when:** play_native cold-starts through the original's real flow, driven by the recovered
decisions, matched to the cold-start demo.

## The exact cold-start flow (mapped 2026-07-11)

Traced from `demo_cold_start_full` (the C679 file-open trap gives the asset order) + disassembly:

```
boot: LZEXE unpack -> video init -> load shared banks (1X1/2X2/2X2C/MANEXPL/THEND.BIC, PANEL.ENC,
      BLUEBITS/SHIP/WINDOW.BIC)
  -> 96C5: set video mode (int10 from CS:99C4[95BC]) ; 5BEE ; CBE8
  -> CBE8 -> CC04: the FRONT-END LOOP
       5BEE ; 4F57 (video) ; CE97 (compose the MENU screen) ; 5C04
       loop, checking [98C3] (the "START pressed" flag) between steps:
         CE40 (delay) ; CE5F ; CC4F (attract scene player) x3
       until [98C3] != 0  -> return (start a game)
  -> (start) 971A: D390 level-select (LEVSCR + CHOOSE, grid D476/D480/D488/D490 + D424 fire)
       -> level data (LEV{n}MAP/BLX + G{n}) -> plaq{n}.enc PLAQUE -> 97B2 gameplay
```

**Ground truth confirmed (2026-07-12, owner playtest + container dump + cold-boot sequence probe):**
- There is **NO standalone intro/title asset** in the container (58 assets; no TITLE/INTRO/LOGO.ENC --
  only `LOGO.BIC` 7377 B).  The cold-boot "intro" the owner expects IS the ATTRACT.  So `IPAGE1..5` are
  the menu 'I' INSTRUCTIONS only, NOT a cold-start story intro (correcting the older bullet below).
- The cold-boot screen sequence (probe, first 1400 frames of `demo_cold_start_intro`):
  `boot -> menu -> front-end@5Cxx -> front-end@96xx -> attract:initial` (953+ frames) -- i.e. straight
  into the **CC04 front-end loop** (menu compose + the CC4F attract cycling), no separate intro screen.
- **play_native CLI fixed (2026-07-12):** `--intro`/`--ending` were aliased BACKWARDS to
  instructions/ordering; now `--ending` -> THE END (WINSCR.ENC) and `--intro` -> the attract; the
  IPAGE/OPAGE screens keep `--instructions`/`--ordering`.

**Screens + who owns them:**
- **intro** — SUPERSEDED: there is no separate intro; the cold-boot intro is the attract (above).
  IPAGE1..5 are the menu's INSTRUCTIONS (`--instructions`), reached only from 558B 'I'.
- **title/menu** — `OKMENU.ENC` background + **CE97 composes menu cells** + **558B menu-idle**
  navigation (recovered, `systems/menu` + `native_front_end`).  play_native: `_run_title_menu` shows
  only the static OKMENU with a fire-wait — MISSING the composed menu cells.  **GAP, still open.**
  **RETRACTED (2026-07-12):** an earlier pass this session called CE97 "fully decoded, ready to build"
  from the static disassembly alone (cells 0x0F/0x10x18/0x11 via `CS:[9598]` work page + `CS:[0C92]`
  directory + `CS:[95B8]` bank, landing at `DS:0x7D00`).  Grounding it against the VM directly
  CONTRADICTED that reading: (1) the `static_runtime_bundle`'s `[9598]` segment is entirely ZERO --
  the bundle's capture point (`1010:D007`) is BEFORE the compose ever runs, so `DS:0x7D00` in the
  bundle is not the composed-menu oracle it looked like; (2) live-VM capture at the CE97 RETURN address
  (`1010:CC12`, trapped directly, ~16.7K steps into a fresh boot) shows `CS:[9598]` holding only 13,562
  nonzero pixels that do NOT match `OKMENU.ENC` (44,405/64,000 px differ) -- so the segment's content at
  that instant is neither blank nor the expected composed page, meaning the disassembly-only reading of
  which segment holds what, and when it becomes the final visible page, is not yet resolved. **No
  verified oracle for the composed menu exists yet.** Do not build against the retracted reading; the
  next attempt needs the VM's B800 physical page decoded READING THE ACTIVE VIDEO MODE (see the
  calibration-screen finding below -- a plain always-mode-9 decode is not safe to assume), likely via a
  trap on the actual PRESENT/page-flip call rather than CE97's own return.
- **NEW FINDING (2026-07-12): a JOYSTICK CALIBRATION screen exists and is completely unhandled.** The
  container has a `CALIB.ENC` asset (`native_video.front_end.decode_fullscreen_image` renders it
  cleanly: "Joystick Calibration -- Move stick to upper left and push FIRE", matches a standard
  early-90s DOS calibration screen).  Live-VM capture of `demo_cold_start_intro` shows the front end
  switching **from text mode to CGA MODE 4** (2bpp, 2 interlaced 8000-byte banks -- NOT the Tandy 16-
  color 4bpp/4-bank layout `decode_tandy_b800_indices` assumes) at present-frame 447, then displaying a
  calibration-grid pattern (a moving-crosshair grid, the classic joystick-range visualization) for the
  ENTIRE rest of the captured span (present-frame 6280+, i.e. most of the owner's observed
  "~6174 frames of automatic intro+attract" -- much of that is actually this calibration loop, not
  attract).  This was invisible to `classify_screen` (address-range-only, blind to video mode) and to
  `verify_native_front_end_image`'s no-input free-run (which reaches mode 9 quickly, so likely takes a
  no-joystick-detected path that skips calibration).  **play_native has zero handling for this screen**
  -- not rendered, not skipped, not documented before now.  Whether real players usually see it (i.e.
  whether it is gated on joystick presence, which dos_re's unmodeled-port-read policy would report as
  absent) is still open.  Recovering it needs: the CGA mode-4 decode (none exists in the codebase yet),
  the calibration screen's own logic (grid/crosshair drawing, joystick-poll, skip condition), and the
  transition points into/out of it -- a real, scoped, but non-trivial next slice.
- **attract** — the `D007`/`D04D` scene machine (scenes 0x0..0x12, incl. the gameplay DEMO at 0x8..0x12
  with auto-fire).  Rules recovered + demo-witnessed (`systems/attract`); scene-0 `D160` + the `D0DB`
  scene-entry actions + the per-scene CONTENT (which asset/demo each scene shows) are gaps.  play_native:
  `_run_attract` approximates title(6s)/hiscore(5s)/demo(15s).  **Partial.**
- **level-select** — `LEVSCR`+`CHOOSE` + recovered grid handlers + D424 fire.  play_native:
  `_run_level_select` (faithful decisions; host screen loop).  **Mostly done.**
- **plaque** — `plaq{n}.enc` at D367 (24,0x47) over the D305 wait.  **DONE (2026-07-11):**
  `native_video/plaque.py` + `_run_level_start_plaque`.

**[98C3]** is the front-end "START" flag the menu/attract loop polls; setting it exits the loop into a
new game.

## Next slices (in order)
1. **Menu (558B):** ✅ DONE (2026-07-11, `_run_title_menu`): M sound-mode, K/A control, idle→attract,
   FIRE→start; **R REDEFINE KEYS** (2026-07-11, `_run_redefine_keys`: captures six keys into the control
   map DS:[2140-2145] + forces keyboard mode, mirroring 5732/5797); I/O instructions/ordering pages; J
   declined (keyboard-only).  `tests/test_native_menu.py`.  **F9 BOSS KEY** ✅ DONE (2026-07-11,
   `_run_boss_key` + `native_video/boss_key.py`): paints the fake "SNAFU V4.2" file-manager decoy screen
   (the 80x25 char/attr image at seg 0x25CC:0x0056, rendered with the CGA text palette) and freezes
   until any key, wired into BOTH the menu and the gameplay loops.  `tests/test_native_boss_key.py`.
2. **The shared TEXT-PAGE renderer (`1010:D2B8`):** the menu's **O/I** ordering/instructions screens
   AND **THE END** all render text through `1F8F:0980` — which is only a scrollable page VIEWER (up/down
   scroll + exit) that calls `1010:8D8B(ax=D2B8)` → **`1010:D2B8`**, the real font/glyph page renderer.
   Recovering D2B8 (+ 8D8B's `call ax` dispatch) unblocks the I/O menu screens and makes THE END's
   pixels byte-exact in one go.  Substantial (glyph render + page layout); highest shared value.
3. **Attract:** functional now (menu idle → high scores + a byte-exact gameplay demo).  Fidelity slice:
   drive it from the recovered `attract_frame_step` (D007/D04D) scene order/timing.
4. **Intro:** confirm the IPAGE order/trigger vs the original.
5. **Transitions:** the inter-screen palette fades (C57C/5BDC) the original does, which play_native
   hard-cuts.

**State (2026-07-05, superseded above):** full-screen images decode byte-exact; menu logic pure
(systems/menu); nothing wired beyond the title splash.

## Slice C — the native cold boot (decoded 2026-07-11)

Recovering play_native's cold boot so it runs the ORIGINAL front-end (not the host-loop stand-in).
What's recovered vs the gaps, from the disassembly:

**Boot (`1010:0D42`)** = the shared-startup-asset loads: it loads a fixed list of banks (filename ptrs
`1298/12A4/12B0/12BD/12DA/12E8`) into the segments `CS:[95A8/95AA/95AC/95A6/95B2/95B4]` via `0CD8/0CB8`.
This is DATA (already `load_shared_startup_assets`); the LZEXE unpack before it is exe-only and the
VM-less port skips it (it starts from the recovered image, not the packed exe).

**Attract (`1010:D007`/`D04D`)** -- the scene machine, `attract_frame_step` recovered + demo-witnessed:
- `DS:BE06` scene id -> a 6-byte descriptor at `DS:BE18 + scene*6`; word0 links into the `CS:0BE4`
  panel-cell directory (a cell drawn each frame at cursor (0x1F,0x18)).  Scenes 0..7 are cell screens
  (100 frames each); scenes >= 8 are the auto-fire GAMEPLAY demo (the attract plays the game via the
  `BE0A` mod-0x14 fire cycle on ticks 0x0F/0x11/0x13, `A067` fanout, BP=237C); scene 0x13 is terminal.
- **Scene 0 (`D160`) decoded (2026-07-11):** it is the attract's GAMEPLAY-SETUP, not a screen -- it
  counts `[237E]` (the player view-anchor) down toward 0x60, runs the `9BE2` object-chain pre-update
  (bp=237C), reloads the scene countdown `[BE08]=0x32`, and its sub-branches spawn via `7524` / emit
  sound.  So scene 0 initialises the self-playing attract game; recoverable but it composes the object
  system (9BE2/7524), not the cell blit -- RECOVERED as `native_frame.attract_scene0_setup_d160`.
- **`D0DB` per-scene entry-draws DECODED (2026-07-11):** on each scene advance it reloads `[BE08]=0x64`
  + `inc [BE06]` (the advance -- already done by `attract_frame_step`), conditionally runs the `859E`
  panel compose (descriptor word1 != FFFF -> `[95FA]`/`[BE16]`), then a per-scene JUMP TABLE
  (`D10B: jmp cs:[bx-12014]`) to small entry actions -- flag sets (`[A958]`/`[A95E]`/`[A960]`) + an
  `81F4` spawn.  The attract runs WITHOUT these (scenes render + the game plays); they are per-scene
  state polish, and the jump table wants the lifter's indirect-jump treatment.  This is the last
  cold-boot piece; every other part is recovered + wired into play_native.
- **Cell directory:** RESOLVED -- populated in the bundle (see step 1).

**Menu (`558B`)** -- the option dispatch (M/K/A/I/O + idle + fire) is recovered and already in
play_native; `NativeFrontEnd` carries the 558B idle + D390 level-select decisions.

### Recovery order (each shadow-gated)
1. ~~Capture a populated attract snapshot~~ **RESOLVED (2026-07-11): the `static_runtime_bundle`
   already has `CS:0BE4` populated** (the 16-entry cell directory, offsets at 0x90 stride) + the `BE18`
   scene descriptors -- no fresh snapshot needed; the scene-cell render builds straight from the bundle
   (or, post-convergence, from `native_rom`).  The `boot_1010_entry` snapshot was just pre-panel-load.
2. **Scene-cell render -- fully decoded (2026-07-11), ready to build.**  `D04D` draws each scene's
   cell: `5A00` sets the cursor to `(al=0x1F, ah=0x18)`; `cellid = [DS:BE18 + scene*6]` (descriptor
   word0); `offset = CS:[0BE4 + cellid*2]` (the directory lookup); then `5A6C` blits the cell from the
   `CS:[95B4]` bank at the cursor.  This is EXACTLY the 5A00/5A6C cell blit play_native already runs for
   the plaque + the level-select cursors -- so the render is a mechanical compose: read the `[95B4]`
   bank, look the cell up through the directory, blit it, drive the scene id/countdown with
   `attract_frame_step`.  No new decode work; the structure is complete.
3. **Wire `attract_frame_step` as the driver**: run it per frame, draw the scene cell (2), and for
   scenes >= 8 run the NATIVE frame with the recovered auto-fire injection -- the game playing itself,
   VM-free.  Recover scene 0's `D160` + the `D0DB` entry draws to close the gaps.
4. **Compose boot -> attract -> 558B menu -> level-select** into a `NativeColdBoot` driver play_native
   runs instead of `_run_title_menu`.  Then the "fake menu" is gone.

Until then: the authentic front-end is the reference VM (`python scripts/play.py --video tandy`).
