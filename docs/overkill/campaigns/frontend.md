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

**Screens + who owns them:**
- **intro** — IPAGE1..5 story pages (the recorded demo skips them via the `\r` command tail; the real
  cold start shows them).  play_native: `_run_intro` (present) — verify order/trigger.
- **title/menu** — `OKMENU.ENC` background + **CE97 composes menu cells** (title cell 0x0F, an 18-cell
  block, 0x10, 0x11 from the CS:0C92 table via 5A24 blit-setup + 5A5A cell-copy) + **558B menu-idle**
  navigation (recovered, `systems/menu` + `native_front_end`).  play_native: `_run_title_screen` shows
  only the static OKMENU with a fire-wait — MISSING the composed menu cells + navigation.  **GAP.**
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
1. **Menu (CE97 + 558B):** compose the real menu screen (cells from CS:0C92) + wire 558B navigation, so
   the menu is the original's, not a static OKMENU fire-wait.
2. **Attract:** drive `_run_attract` from the recovered `attract_frame_step` scene machine (order +
   timing + the demo scenes), looping to the menu on start — the faithful "demo after intro".
3. **Intro:** confirm the IPAGE order/trigger vs the original.
4. **Transitions:** the inter-screen palette fades (C57C/5BDC) the original does, which play_native
   hard-cuts.

**State (2026-07-05, superseded above):** full-screen images decode byte-exact; menu logic pure
(systems/menu); nothing wired beyond the title splash.
