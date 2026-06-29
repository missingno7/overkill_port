# Loop blockers — divergences/targets that need the user (or better tooling)

Open items the autonomous loop attempted but could not finish byte-exact. Do NOT
re-attempt these in the loop; they need a reproduction trace and/or gameplay
context. Each has the analysis already done so a human can pick up fast.

> Status note (2026-06-19): the byte-exact frontier is effectively closed —
> oracle suite 244/244 and demo-replay 19/19 (bounded) are green, and the
> readability refactor (`refactor_plan.md`) has taken over as the primary driver
> (Phases 1–2 done, Phase 3 in progress). The only genuinely-open correctness
> blocker is the player-death full-demo divergence below.
>
> **Update (2026-06-28):** that player-death divergence — long the only open
> correctness blocker — and the `[95F2]`/`[95F4]` view-contact-center divergence
> are both RESOLVED by one fix: the AA46 `si>=3` no-contact branch (`AA54 JAE 0xAA44`).
> Full suite 537 passed / 23 skipped. Newly surfaced: an effect-activation
> timing / ISR-cadence phase offset (see backlog).

---

## OPEN (2026-06-29) — the starfield plate blocks the native frame (`--backend native`)

The standalone native frame is `playfield = starfield plate + sprites` (+ HUD). Every native
leaf is recovered **and proven byte-exact** EXCEPT the **starfield plate** (the sparse
parallax background): sprites (`composite_sprites` / `verify_sprite_layer`), the playfield
compose (`compose_playfield_indices` / `verify_playfield_compose`, 30/30), and the HUD glyph
(`native_video/hud_glyph` / `verify_hud_glyph`, 256/256) are done. So the starfield is THE
critical-path blocker for a self-composed native frame.

- Eluded ~30 probes: the stars are a parallax PIXEL layer — the static-buffer-scroll model
  FAILED (0/60 plates reproduced, 0 colour conflicts → stars scroll at their own rate); a
  traced star byte showed NO writer (not `wb`/`ww`, not the bulk `rep movs/stos` even after the
  bulk-op watcher fix) → the plot is via a path the watchers miss (off-screen scroll-in
  suspected) or at level-load.
- **Next (fresh approach):** a parallax-aware trace at a SCROLL frame (star displacement vs
  the cursor delta → the star scroll counter), or a level-load capture. User noted it's
  pixel-plotted. Until then, the native frame must capture the VM plate (hybrid only).

## NOTE (2026-06-29) — §1.2 state-mirror verifiers DILUTE pure %; at the rounding edge

The Bucket C §1.2 native state-mirror verifiers (`read_X` + `X_mismatches`: CameraState DONE
`5902f25`, HudLayer/Score DONE `fdd4a38`) are **VM-facing adapter code** — they read VM memory
to compare — so each ADDS to the ASM-like mass without adding `source_pure` mass. Pure %
DILUTES (Source flat at 2982; ASM-like grows). Committed Camera + Hud brought pure % to the
rounding edge (raw ~14.45% → displayed 14.5%). A further BackgroundLayer + PresentComposition
mirror slice pushed ASM-like 17650 → 17701 → **14.4% displayed (FELL)**, so it was REVERTED per
§5 (a slice failing the metric gate is a blocker, not a shortcut).

**Implication:** done-condition #2 (build the §1.2 mirrors) conflicts SHORT-TERM with #4
(pure % must not fall) — mirrors are VM-facing infra. They pay off only when the native RUNTIME
(Bucket C producer) is built and the VM-facing adapters/hooks are DELETED (pure % then jumps).
Until then, do NOT add more standalone mirror-verifier slices (they fail the metric gate). The
metric-RAISING vein is inline→pure decision extraction (A4EA-style, `e2bd8d7`), which the
brief's own Bucket-A frontier note marks exhausted (only multi-part islands remain). Confirmed
this session by examining the two unblocked Bucket-A behaviors: `B250`'s only un-pure decision
(the overlap-box test) is flag-coupled at each early return (AX/BX/flags differ per exit), and
`8d4f` is a waypoint read + a trivial `+0x20` offset + mode stamp then delegations to the
already-lifted `5DB2`/`bc4b` — neither yields a meaty gate-compliant pure decision. So the
gate-compliant remaining work is (a) the hard Bucket-A islands (pure-raising but multi-leaf), or
(b) the native-runtime build itself (which collapses the adapters and repays the dilution).

**Update (2026-06-29, later) — clean low-risk pure-raising veins now EXHAUSTED; do NOT re-grind:**
- inline→pure spawn templates: done (A4EA `e2bd8d7`); the rest are single-use (over-engineering).
- faithful recovery of witness-poor `_observed` lifts: 5F0D was the one clean one (`bcd_add_score`
  `332b58d`); the others (`bec5`/`9e69`/`9e98`/`bd17`/`bd0d`/`7476`/`7420`) are the hard
  death/contact/spawn frontier (attended-only — that is *why* they are observed/partial).
- Bucket-A unblocked behaviors (`B250`, `8d4f`): VM-coupled, no meaty pure decision.
The one vein that BOTH raises pure % AND is non-blocked is the **native-runtime build (Bucket C)**.
**Done this session (`9899c12`..`afaadf6`):** `NativeGameState` + the pure verify-mode comparison
core; and the **produced-vs-VM verify-mode** grown to **5 byte-exact producers** across the demo
corpus (`scripts/verify_native_producers.py`, the cross-demo gate): `bcd_add_score`/`advance_hud_score`
(5F0D score), `object_pool_find_free` (7573 alloc), `object_spawn_seed_8209`/`_a4ea` (8209/A4EA
spawn templates), `step_first_active_timer` (61C7 frame timers).  Each probe step-hooks the routine
on the pure-VM side and asserts the native producer matches, for every real event (hundreds/demo,
0 divergence).

**The remaining §1 gap (demand-driven):** rendering a frame standalone needs `FrameSnapshot` built
from `NativeGameState` with **no VM**, which needs the **object pool updated natively** — i.e. the
**standalone per-frame object update**: the scan/dispatch over `NativeGameState`'s pool + each
object's behavior *applied* to native state (the decisions in `systems/objects.py` are already pure;
the per-object read→decide→write **application** + the **scan/dispatch orchestration** + movement/
collision/clamps + side effects are the lifted-only parts that need standalone versions).  This is
the big coupled system (no clean single leaf) — the multi-session build, and once it produces the
pool, the standalone loop (§1.1) and full-state verify (§1.2) follow.  **Pattern to reuse:** each
new producer gets a `verify_native_*` probe added to `verify_native_producers.py`'s `PROBES`.

**Confirmed coupled by inspection (2026-06-29, why no 6th clean producer):** the behaviors are not
slot→slot — `_run_object_behavior_b73e` (and siblings) end every path in `_run_object_postmove_bc4b`
(the collision/contact tail), and the movement helper `_run_movement_direction_5db2` is a compound
target-seek (reads object Y/X vs DS:2304/2306, maps a direction nibble through DS:A348/A954 into the
slot, then dispatches a step through CS:5E0C by DS:2308 — and is verified only for the 2308==2 AF60
double-2px step).  So the object-update producer must bundle target-seek + step + the bc4b
collision/postmove tail; that's the substantial recovery, not a clean leaf.  The path in: lift the
`bc4b` postmove + the target-seek/step into native-state functions, then a per-logic-id native
dispatch over `NativeGameState`'s pool, each verified produced-vs-VM with a `verify_native_*` probe.

**Second gap — the render-side `screen_di` projection (for the native FrameSnapshot sprites):**
building `FrameSnapshot` from `NativeGameState` (no VM) also needs each sprite's `+0C` dest
(`screen_di`), which `frame_snapshot_adapter` currently *reads* from the VM.  It is computed in the
per-object draw `1010:5AC8` (the present scan `A846` loops the 8D12/32CA tables calling 5AC8 per
active slot) — **un-recovered raw ASM**.  The sprite *blit* is already recovered
(`composite_sprites`/`verify_sprite_layer`); the *projection* (object world pos + scroll/camera →
B800 di, or `FFFF` cull) is the missing piece.  **But 5AC8 is NOT a clean leaf** (corrected after
disasm): it is a draw DISPATCHER — `mov bx,ss:[bp+0x14]; add bx,cs:[95BC] x3; shl bx,1; jmp
cs:[bx+0x5AE2]` — indexing a jump table at CS:5AE2 by draw-type + the video mode (`[95BC]`), so the
projection lives in *multiple per-type/per-mode handlers* (the table targets).  Recovering it = map
the 5AE2 table, lift the Tandy handler's project-then-`composite_sprites` path to native state,
verify native di == VM `+0C` across demos.  So the render-projection gap is itself a coupled
**island** (dispatch + handler set), the same risk class as the object-update island.  **Net: both
remaining §1 gaps are coupled islands; no clean `verify_native_*` leaf remains** — the work is
genuine multi-routine recovery, for a fresh, clean-context session.

**Projection observe→derive — ATTEMPTED, needs the handler ASM (2026-06-29):** captured **410**
active-sprite `(obj_x, obj_y, screen_di, camera_x, camera_y)` samples over an L2 demo run
(`scratchpad/capture_projection.py`) and tested whether `decoded_screen − (obj − camera)` is
constant under four page geometries (B800 bank; linear width 0xA0/0x68/0x150).  **None fits** — X
has 49–95 distinct offsets and Y 37–73 across the 410 samples, for every geometry.  (The earlier
2-sample snapshot "X ≈ obj_x − 136" hint was a coincidence, not a real fit.)  So `+0C` is **not** a
simple camera-relative projection in any standard page geometry — it factors something else (a
different reference origin, per-object scaling/anchor, or a non-standard stride/page).  Observation
alone cannot crack it; the recovery requires **disassembling the chosen 5AE2 Tandy draw handler**
(map the table, follow the dispatched handler's `+0C` computation), then implement
`project_object_to_di` and verify native di == VM `+0C` across demos.

**RESOLVED (2026-06-29, `f8cae7a`) — the projection IS a clean leaf after all (go-to-the-ASM won):**
followed the dispatch (5AC8 draw-type → 5A36 video-mode → **30D2** Tandy projection) and the
projection is `di = (obj_y >> 1) + DS:99C8[obj_x]`, cull on `obj_x >= 0xE0` / column entry `FFFFh`.
The reason observe→derive failed: the **X is a table lookup** (`DS:99C8`), not arithmetic.  Recovered
as pure `native_video/projection.py:project_object_to_di`, **verified 4624/4624 byte-exact** vs the
real 30D2 (`verify_native_projection.py`), added to the cross-demo gate (6th producer, first
render-side).  The column table `DS:99C8` is already recovered — the static 0F0B startup builder
(`rendering/tandy.py`: FFFF guard band + X/window table by stride CS:[959E]).  So the render
**leaves are done** (projection + column table + `composite_sprites` blit).  Remaining render work
is **integration, not a leaf**: assemble the native FrameSnapshot sprite list from
`NativeGameState`'s pool via `project_object_to_di`, reconstructing the full slot `+0C`
(= core `+ DS:234C` scroll `+` the one-row present phase `0x68` that the present-hook extraction
sees) — a Bucket-C composition step.  **So of the two §1 gaps, the render one is now leaf-complete;
the object-update island (bc4b/target-seek dual-mode) remains the substantial recovery.**

**RESOLVED (2026-06-29, later) — the full sprite `+0C` composition (`project_object_screen_di`):**
the render-side Bucket-C composition step the projection note left ("reconstruct the full slot
`+0C` = core + DS:234C scroll") is now done + verified.  Disasm of the per-object draw handler
**35CC** settled the exact formula (the projection.py docstrings disagreed on whether DS:99C8 was
already scroll-baked): `35CC call 5A36` (→30D2 core di) → `35CF mov [bp+0C],ax` → `35D8 add
ax,ds:[234C]` → `35DC mov [bp+0C],ax`, i.e. **`+0C = (project_object_to_di(x,y,col) + DS:234C) &
0xFFFF`**, or FFFFh when 30D2 culls (→25B2).  Recovered as pure
`native_video/projection.py:project_object_screen_di` (and `build_native_sprite_layer` now composes
the full `+0C`, not the core), **verified produced-vs-VM byte-exact vs the live slot `+0C`** by
`verify_native_screen_di.py` (7th producer in the cross-demo gate): L2 2191/2191, and L1/L5/L6-boss/
player-death/mothership all 0-divergence (~17k draws).  The `+0x68` "phase" in the earlier note is
NOT part of `+0C` — it is only the present-hook *extraction* boundary artifact (frame_snapshot_adapter
extracts at the draw boundary, where `+0C` is core+234C with no phase term).  **So the native sprite
layer can now place every object's screen di from `NativeGameState` (x/y + column table + DS:234C)
with no VM read.**  Render leaves AND the render composition are done; the object-update island
(the pool *producer*) is the one remaining §1 recovery.

**DONE (2026-06-29, later still) — the native draw-list producer (`native_sprite_draws`):** the
Bucket-C "compose the FrameSnapshot sprites from recovered state" step is built + verified.
`native_video/sprite_compose.py:native_sprite_draws(game_state, column_table, scroll)` walks
`NativeGameState`'s gameplay then effect pools (witnessed-exact present order), takes active slots,
composes each via `project_object_screen_di`, drops culls → the `(sprite, screen_di)` draw list, no
VM read.  **Verified produced-vs-VM** by `verify_native_sprite_draws.py` at the A90C present-scan
return (where `+0C` is fresh): native list == the VM's gameplay+effect slot draws (`+08`/`+0C`,
active + on-screen), **L2/L5/L6-boss/player-death 200/200 0-div** (8th cross-demo producer).

**DONE (2026-06-29, later) — the COMPLETE native draw list (special view-anchor slot):**
`NativeGameState` now carries the leading `special_pool` (DS:237C, drawn first), so
`native_sprite_draws` walks (special, gameplay, effect) → the COMPLETE draw list, no VM read.
Verified the special slot follows the same `project_object_screen_di` (a normal 5AC8 draw) then
wired it through `NativeGameState.special_pool` / `read_native_game_state` / the probe's VM ref:
**L2 300/300, L5/L6-boss/player-death/mothership 250/250 0-div**.  Aliasing fact locked: the
special slot's X/Y (237E/2380) ARE the VIEW_TARGET/camera globals (a camera move drifts both
`camera` and `special_pool`).  `SPECIAL_DRAW_SLOT_BASE/_COUNT` moved to `views/object_slots.py`.
**The render side is now FULLY recovered (leaves + complete composed draw list).**  Remaining §1:
the object-update island (the per-frame pool *producer* — b73e→bc4b/AD60 tails + 5DB2 target-seek)
and, for a full native FRAME, the BLOCKED starfield plate (above).  Next native step: the
standalone-loop scaffolding consuming the verified producers, and/or the object-update recovery.

**Assessed 2026-06-29 — AD60 (shared bounds/tile tail) is NOT a clean native producer either:**
its decision (`object_bounds_tile_decision_ad60`) is already pure + hybrid-verified, but its
*application* funnels into the coupled death frontier — the out-of-bounds + tile-probe-fail paths
both call `BD17` deactivate (`_run_deactivate_bd17_observed`, the attended-only `BFC7`/`BD17`/`C054`
frontier above).  Same for the behaviors via `bc4b`.  So there is no clean produced-vs-VM leaf left
in the object-update island; its native form is the coupled application build (pure ObjectPool→
ObjectPool transforms for the dispatch + movement + bc4b/AD60→BD17 tails), gated by the death
frontier.  The clean render-producer vein is exhausted (render side fully recovered); the object-
update is the substantial coupled §1 recovery, and a full native FRAME additionally needs the
BLOCKED starfield plate.

**§8 queue refill swept (2026-06-29):** confirmed no clean unattended §1-advancing slice remains
outside the attended object-update + blocked starfield. Evidence: (a) `source_port_status` pure %
15.1%, lifted files well-collapsed (94% named record offsets, 71 pure rules) — the remaining lifted
mass is VM-boundary continuation glue, not extractable decisions; (b) the largest lifted file's
candidate decision (`game_state` 9C01's `3*ah+al` axis-dispatch index) is single-use + tangled with
its jump-table control flow = the "single-use over-engineering" cautioned against above; (c)
`hooks.py` (3203 lines, over its 1500 budget — done-condition #4) has no relocatable inline render
video-writes — its size needs hook DELETION via the native runtime, not relocation; (d) the brief's
last-named Bucket-A behavior `aed8` (logic_id=2) decomposes to a trivial substate timer-dec + the
already-recovered AEE4 step + the flag-coupled `B250` contact selector + the `AD60`→`BD17` death tail
— no clean extractable decision (its only un-pure piece is `B250`'s overlap-box test, flag-coupled at
each early return per the note above). So pure %, the
glue/hooks.py budget, AND §1.1/§1.2 all converge on the SAME gate: the native object-update runtime,
which is coupled to the attended-only BD17/bc4b death frontier. That is the demand-driven loop's
honest frontier: the next productive step needs the death-frontier recovery (a reproduction trace +
gameplay context, per §2 "skip loop_blockers items" unattended) or the starfield tooling.

**Death-tail native-build roadmap (read the code 2026-06-29 — the exact leaves a fresh session needs):**
`object_deactivation.py` shows the object-update's death tail (`BD17`/`BFC7`) is recoverable to native
ONLY by recovering this leaf set first (each gated produced-vs-VM, the proven pattern):
- `C054` (`run_object_deactivate_logic_dispatch_c054`, in collision.py) — the logic-id→selector
  dispatch; its pure classification is ALREADY extracted (checked: delegates to the pure object
  system + an adapter), so only its native *application* is needed, not a new decision.
- `C12D` + `7420` (effect-spawn tails) — pure ObjectPool spawns; the spawn *templates* are already
  recovered (`object_spawn_seed_*`), so these are the application over a free slot.
- `BD17` branches: draw_layer 4 (C054+C12D+linked-counter clear), logic_id 9 (BD7A whole-projectile-
  list clear — already lifted), the small counter decrements (lifted), and **logic_id 0xA → BD9E/AC19
  which is INTERPRETED original ASM** (the attract/transition chain — the one genuinely un-lifted
  branch; if the gameplay demos never hit logic_id 0xA, a pure BD17 can fail-loud there and still pass).
- `BFC7`: score-add (`5F0D`/`bcd_add_score` — recovered), Y-clamp (`BCB1` — recovered), `7420` linked
  effect, `C054`+`C12D`, and the `C037` obj_type dispatch (types 1/2 recovered; others fail-loud).
Then a per-logic-id native dispatch over `NativeGameState`'s pool composes them into the object-update
producer → the standalone loop. Substantial but mapped; a fresh clean-context session can execute it.

**CORRECTION (2026-06-29, later) — the object-update is NOT fully death-frontier-blocked; its MOVEMENT
half is a clean recoverable leaf.** Disproved the "no clean object-update leaf" conclusion above by
building one: the per-slot movement transform is *separable* from the global death-tail side-effects.
AD60/BD17 only set the slot's `active` word + global counters — they never touch the five movement
fields (substate +1C, direction +06, sprite +08, x +02, y +04). So each behavior's movement half is a
pure composition of already-verified systems. Shipped `object_movement_step_ae09` (object_logic_ae09 +
the AF22 step), **verified produced-vs-VM byte-exact** (L5_continue 777/777, L5_short 638/638) — 9th
producer, first object-update one. **Revised frontier:** the object-update splits into (a) per-behavior
MOVEMENT producers — clean, demo-demanded, pure-% raising, the next vein to grind (b73e/b86d/b9f0/aba3/
ab77/8d4f/b24d/aed8 movement halves, each a `verify_native_object_update_*` probe); and (b) the global
side-effects (counters/spawns/`BD17` death) — the harder attended island. Only (b) is death-frontier;
(a) is open for the unattended loop.

**Progress (2026-06-29) — 2 movement primitives now native (the bulk of (a)):** AE09's fixed-step
(`object_movement_step_ae09`) AND the SHARED target-seek (`object_target_seek_step_5db2`, the whole
5DB2 — used by b73e/b9f0/8d4f/D281/B729/B1B0). The latter recovered the CS:5E0C mode table (1->AF63
2px, 2->AF60 2px×2, 3->AEE4 8px) and composes `choose_target_seek_direction` + `step_operations_for_
direction`; **verified produced-vs-VM byte-exact** (L2 1257/1257, L6_boss 1957/1957, player_death
1721/1721, L5 240/240; 5175 calls 0-div). So target-seek movement is done for ALL seeker behaviors at
once. Remaining (a): the non-seek behaviors' slot transforms (animation/state for the non-moving
b86d/ab77/aba3/b24d; aed8's AEE4+B250 which is coupled to ADC9 x=FFFF). Remaining (b): the global
death/spawn side-effects (the attended island). Next: compose the per-logic-id native dispatch over
`NativeGameState`'s pool from these movement producers + the existing decisions.

## NOTE (process) — check lifted-status before "recovering" a routine

`519A` / `3153` (HUD text dispatch + Tandy glyph) were ALREADY lifted (`rendering/text.py`,
hook-registered; see `coverage.py`). Grep the hook registry for an address before
disassembling it as if un-recovered. `native_video/hud_glyph` is the NATIVE-standalone form
(index-space, proven byte-exact vs the VM tables), not a re-recovery; future dedup: unify the
glyph core (glyph+colour → 8x8 block) between the VM hook (B800) and the native form (index).

## RESOLVED (2026-06-28) — Player-death `BC4B`/`BFC7` divergence (full-demo only)
**Root cause: the AA46 `si>=3` branch** (same fix as the contact-center item in
the backlog). `AA54 JAE 0xAA44` returns no-contact for a side-selector of 3+; the
lift omitted that branch and indexed the 3-entry DS:214E table out of bounds,
fabricating an 8331 hit — the `SI asm=0003 hook=...` below was exactly that.
`demo_play_tandy_player_death` full verify now passes. Original analysis kept
below for history.

Demo: `demo_play_tandy_player_death`. Passes the **bounded** 150-frame demo-replay,
but diverges deep in the **full** run (`OVERKILL_FULL_DEMO_VERIFY=1`).

- Hook-verify: `1010:BC4B object_postmove_bc4b` call 1691 diverges at continuation
  `AA04`. `AX asm=0000 hook=0060`, `SI asm=0003 hook=00DC`, 2 memory words differ
  (`0x0073→0x00EC`, `0x005E→0x0060`), plus a nearby position-list (`9682/968C/9696`).
- **Ruled out:** the `BFC7` death tail itself. Disassembled the full `BFC7..C054`
  path and the `C037` obj_type jump table @`C042`; the lift in
  `object_deactivation.py` matches exactly. The differing words are NOT `[bp+8]`
  (0/3 in both), and `AX`/`SI` aren't touched by the handlers.
- **So the bug is elsewhere in `BC4B`'s path** — `BD17` deactivate, the
  post-contact `9E69` tail, the contact window `AA46`/`AA71`, or upstream state.
  All of `BD17`/`9E69` are still "partial/observed" lifts.
- **Next step (human/trace):** reproduce, single-step `BC4B` call 1691, bisect
  which child first makes `AX`/`SI`/the position-list diverge, then disassemble
  that child and compare. Tooling ready: capstone installed;
  `artifacts/static_runtime_bundle/memory_1mb.bin` holds the original image
  (`1010:off` → linear `0x10100+off`); `scripts/trace.py` does dual-runtime
  watch/observe/globals.

---

## Resolved (2026-06-19) — kept as a short index; full write-ups in git history / run_status.md
- **Mothership camera-Y divergence** — `9B2E` lift dropped the `[a47c]==0` guard on
  the `9C01` camera-step; nested the `[2350]` poll-gate + `9C01` inside `if
  [a47c]==0`. Added `phase_gate_a47c`/`level_progress_2350` to the snapshot globals.
- **Sidearm-trail "shaking" (mothership drag)** — same root as camera-Y.
- **`menu_interaction` demo TIMEOUT** — verifier-only limitation (async INT 1Ch
  ISR not fired, `DS:[54]` frozen). Fixed with `input_waits.advance_frame_tick_wait`
  ticking `DS:[54]` when parked in the CBD5 busy-wait. Interactive play untouched.
- **BDD0 / D434 / 33AF oracles** — all three were hook/oracle *granularity*
  mismatches, not gameplay bugs (demo-replay green throughout). BDD0: land on the
  real `5059` STC;RET stub + drain it in the child-call wrapper. D434 & 33AF:
  oracle-convention fixes (compare at the hook's actual boundary). Suite 244/244.

---

## Remaining backlog — needs attended judgment (not safe unattended)

- **RESOLVED (2026-06-28) — View-contact-center `[95F2]`/`[95F4]` divergence:**
  root cause was the AA46 `si>=3` branch (`AA54 JAE 0xAA44`).  For a side-selector
  of 3+ the original returns no-contact without touching the DS:214E offset table;
  the lift indexed it out of bounds (`DS:[214E + si*4]`, e.g. DS:215A), wrote a
  bogus DS:95F2/95F4 centre and fabricated an 8331 contact hit — which spuriously
  killed in-window effect objects (`demo_play_tandy_20260627_231013` effect:20 at
  frame 936).  Proven by disasm of AA46 + a dual-runtime trace (all AA46 inputs
  byte-identical on both sides; only the si>=3 output diverged).  Fix in
  `collision_adapter.run_view_window_check_aa46_body`.  Same fix closed the
  player-death blocker above.
- **Effect-activation timing / ISR-cadence phase offset** (surfaced 2026-06-28 once
  the AA46 fix let `demo_play_tandy_20260627_231013` replay past frame 936): the
  full verify now diverges at ~frame 960 where a group of idle effect objects
  (logic 0x80, sprite ~354) begin a bounce one frame earlier in the hooked runtime
  than in the ASM oracle (y +2, sprite +1; it momentarily reconverges at the bounce
  turning points, so it is a phase offset, not corruption).  The effects are gated
  on a per-object countdown (`+0x1C`) decremented by the `1F8F:06C9` timer ISR.
  Traced mechanism: the countdown reaches 0 on the SAME frame in both runtimes
  (f959 for effect:6); the same ISR then transitions the effect idle->moving
  (`1F8F:06DB` target_y, `072B` y, `07AC` sprite).  The hooked runtime performs
  that post-zero transition in the frame the countdown zeroed; the ASM oracle
  lands it one frame later.  So the divergence is the SUB-FRAME position of the
  ISR transition relative to the present/frame boundary, which differs because the
  hooked runtime's instruction timing differs.  `1F8F` runs as raw ASM in BOTH
  runtimes (not a hook), so no hook lift fixes it — same class as the busy-wait/
  IRQ-cadence timing work, a timing-model frontier.  Bounded verify unaffected
  (green).  Needs attended timing-model work (frame-align the PIT/ISR cadence).
  The same signature recurs in `demo_play_tandy_start_to_end_20260627_145115`
  at frame 2271 (68 fields, effect:0..16 all y+2 / sprite+1), confirming it is a
  general timing frontier rather than demo-specific.
- **Unknown object-record fields `0x10`, `0x26`, `0x36`** (map at 25/28, the honest
  floor): each is written with no lifted reader (`0x26` ← DS:237A in object_spawns,
  `0x36` ← ax in object_movement; `0x10` is never accessed). Naming needs the
  reader lifted first — can't be done honestly yet.
- **Death/deactivation frontier:** `BFC7`/`BD17`/`C054` are "partial/observed"
  lifts; completing their full branch tables is the same risk class as the
  player-death blocker above and would likely clear it.
- **Interpreted gameplay islands (refactor_plan Phase 5):** `97C8` frame body,
  menu core, `BBB2`/`BE3C`/`B2CD`/`ADC9` block loops run as raw ASM today and are
  already *correct* in both runtimes — lifting them is real reverse-engineering
  with no correctness gain, best done attended, and only after Phases 3–4.
- **Object-behavior call-tree leaves (the bounded `run_original_near_call` /
  `_run_interpreted_near_call_observed` shims)** — surfaced 2026-06-28 after the
  whole object-behavior *decision/computation* vein was lifted (ab10/ae09/aba3/abca/
  b9f0 = 7 b9f0 rules; the behaviors now delegate every clean pure rule). The
  remaining inline weight in `abca`/`b9f0`/`aed8`/`b24d` is the bounded calls into the
  leaves `5DB2`✓/`5E1B`/`5E42`/`7476`/`837A`/`859E`/`AB99`, run through the interpreter
  *on purpose* so their internal near-CALL return words match byte-for-byte. Spot
  disasm confirms these are NOT simple leaves: `837A` is a dispatcher that does an
  indirect `call ax` through a runtime handler table inside a 10-iteration loop (its
  targets can't be statically resolved); `AB99` is just `call BFC7` (the attended-only
  death frontier above). Lifting them is the same "no correctness gain, attended RE"
  class — the bounded-original approach is already correct in both runtimes. Do NOT
  re-attempt unattended. Tractable filler instead: Phase-1b coastline relocations of
  the remaining genuinely-inline render hooks out of `hooks.py`.

### Cleared from this backlog (done since the last revision)
- ~~Raw-offset drain (objects.py / contact_side_effects.py / action_spawns.py)~~ —
  **done** in refactor Phase 2a: all gameplay record access now goes through
  `ObjectSlotView`; only 3 raw record-offset hex remain (the deliberate
  `OFF_SUBSTATE_1E` semantic alias), per the dashboard.
- ~~DS-global naming (141 addresses)~~ — **partly done** in Phase 2b: the 7 cells
  genuinely *shared* across subsystems are reconciled in
  `overkill/recovered/ds_globals.py`; single-subsystem globals are intentionally
  kept local (locality aids readability), so this is closed for the shared set.
