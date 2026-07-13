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

**THE REAL COLD-BOOT SCREENS, SEEN (2026-07-13, `trace_frontend_flow` to hit the right moment + a
mode-9 B800 decode at the peak-content frame of each scene -- ground truth, captured not guessed):**
- **Scene 0 is a BLUEPRINT / INTRO screen, NOT the OKMENU title.**  The B800 aperture at scene 0's
  richest frame (nz=16827, mode 9) is a coherent 14-colour screen: cyan+yellow **ship SCHEMATICS** (line-
  art, not a bitmap blit) on a **grid** background with several lines of small font text (a stardate/
  briefing).  It differs from `OKMENU.ENC` by 44,593/64,000 px -- i.e. the cold boot does NOT open on
  OKMENU.  **play_native draws OKMENU immediately, so its very first screen is wrong** -- this is the
  "inaccurate menu" the owner sees.  (The grid I earlier mistook for "calibration" is this screen's
  background, and the off-screen `[9598]` work page is its pre-present buffer.)
- **Scenes 1..0x12 are the SELF-PLAYING GAMEPLAY DEMO** (the "demonstration of all upgrades and
  weapons"): captured cleanly in mode 9 -- the ship, starfield, full HUD, cycling weapons (scene 1
  "Scout"/FIREHOSE, scene 0x10 "Ring Laser"/RINGLAS with drone upgrades, enemies).  These render
  through the ALREADY-RECOVERED native gameplay frame, so play_native CAN draw them (it runs the native
  frame for attract scenes >= 8; but note the capture shows scenes 1..7 are ALSO gameplay here, not the
  static "cell screens" the NativeAttract classification assumes -- a discrepancy to resolve).
- So the real flow is: boot -> **scene-0 blueprint/intro** -> **attract gameplay demo (scenes 1..0x12)**
  -> scene 0x13 terminal -> (fire) level-select.  What still needs NATIVE rendering: the scene-0
  blueprint screen (a vector/line-art + grid + font-text compose -- a distinct render system from both
  the bitmap menu compose and the gameplay frame) and the OKMENU-options menu compose (CE97, page
  format still uncracked).  The gameplay-demo half already renders.
- The reference captures live in `artifacts/_fe/` (scene_01/10 = the real attract; real_menu = the
  scene-0 blueprint; L_b800 = the bundle's terminal HUD) -- kept as the recovery oracle, not committed.

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
  **Second attempt (2026-07-13) ALSO failed to converge** and is the reason to stop guessing step
  counts entirely: a joystick-free cold free-run (`build_command_tail`, no demo) settles by ~1.38M raw
  steps into a repeating menu<->attract cycle, all in video_mode=9 (no CGA-4 seen on this path, so
  calibration is plausibly gated on joystick presence). A raw-byte B800 nonzero count recurred
  IDENTICALLY (6728) at IP=558B every ~22K-step cycle, which looked like a strong "freshly composed
  menu" signal -- but a full decode+diff at that exact step (1,400,000) showed near-TOTAL divergence
  from OKMENU (43,622/64,000 px, damage from row 0), not the clean cell-band pattern expected. The
  numeric coincidence in raw bytes did not mean the same visual content -- IP+byte-count is not a
  reliable "this is the composed menu" signal. **Each cold-boot capture costs ~9 minutes** (millions of
  raw interpreted instructions, no snapshot to start from), so step-count guessing does not converge in
  reasonable time and was abandoned rather than continued blindly.
  **What the next attempt needs instead of guessing:** either (a) a disassembly-driven, structurally-
  certain marker for "the composed menu, not attract/hiscore/calibration, is the CURRENT visible
  screen" (trace 558B/D007/CC04's real relationship fully -- what makes the loop show menu vs cycle
  attract -- rather than trapping a single address and hoping), or (b) a one-time reusable
  cold-boot-to-front-end SNAPSHOT (the same reason gameplay demos are fast to probe: they start from a
  captured snapshot, not power-on) so repeated front-end probing stops paying the ~9-minute boot cost
  every attempt.
- **THE CORRECT INSTRUMENT (2026-07-13, owner: "verify on sub-frame level, not guessing from pixels"):
  `overkill/probes/trace_frontend_flow.py`.**  Instead of sampling a decoded framebuffer at a guessed
  step count, it reads the game's OWN control flow: it traps the front-end draw/flow routines (CE97
  menu-compose, CC4F attract, D04D scene-draw, 3354 present, 971A start, D390 level-select, D305 plaque,
  9844 THE END) and emits the RUN-LENGTH-COMPRESSED timeline of `(video_mode, scene [BE06], start
  [98C3])` over a cold-start demo (through the frame verifier, so the real IRQ0 is delivered at boot/
  pacing waits -- no faked timing).  Each transition is a real control-flow event, not a pixel guess.
  Key structural facts it established (all VM-grounded):
  - The front end has **NO 1010:0679 gameplay frame wait** -- so `advance_frames_fast` (keyed on 0679)
    can never advance it (every attempt stalled).  The front end is the **CC04 loop**: `CE97` composes
    the menu, then `CC4F` runs the `D007`/`D04D` attract scene machine, which advances `DS:BE06` 0->0x13
    with a per-scene countdown `DS:BE08`, until `0162` (the input poll: reads the INT9 key table into
    `DS:98BE`, fire bit 0x10) sets the START flag `DS:98C3=0x39` -> `971A` start -> `D390` level-select.
  - The **bundle (`static_runtime_bundle`) is a D007 snapshot** and loads+steps directly (~8K steps/s,
    no acceleration hooks on the front end) -- so front-end iteration no longer needs the ~9-min cold
    boot; BUT it is captured at scene **0x13 (terminal)**, so from it you only see the end-state
    menu<->attract loop, not the full sequence.
  - **The real flow (traced over `demo_cold_start_intro`, VM-grounded):** boot asset-loads -> scene 0
    (setup + menu compose) -> attract scenes **1,2,...,0x12 each ~300 draw-frames** -> scene 0x13
    (START pressed, `98C3=0x39`) -> level-select.  **Scenes 3 and 5 run ~150 frames (HALF)** -- this
    directly CONFIRMS the recovered `attract_frame_step` + the D183 `[BE08]=0x32` countdown override
    against the real VM flow.
- **CALIBRATION claim (2026-07-12) RETRACTED (2026-07-13) -- it was a third pixel-misread.**  The
  `trace_frontend_flow` run with the CORRECT `dos.video_mode` read shows the cold boot is **mode 3
  (boot text) -> mode 9 (Tandy 16-color) for the ENTIRE attract (scenes 0..0x13)** -- there is NO CGA
  mode-4 phase in this demo's front-end at all.  So the earlier "front end switches to CGA mode 4 and
  shows a joystick-calibration grid for most of the cold boot" was wrong on both counts: the mode was
  misidentified (an earlier mode-transition probe reported mode 4, contradicted here by the draw-event-
  accurate read; the source of that stale "4" is not pinned down but the attract-in-mode-9 result is the
  internally-consistent, corroborated one), and the "calibration grid" was the **attract self-playing
  demo** (starfield/objects) in mode 9 decoded through a wrong assumption.  `CALIB.ENC` is a real asset
  but there is no evidence it is shown on the normal cold-boot path.  **Do not build a mode-4 decoder or
  a calibration screen** -- neither is needed for the observed flow.  (Open, low-priority: whether a
  calibration screen exists at all on some joystick-config path -- but it is NOT in the cold-boot flow.)
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
