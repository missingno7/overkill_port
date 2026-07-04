# Loop blockers — divergences/targets that need the user (or better tooling)

Open items the autonomous loop attempted but could not finish byte-exact. Do NOT
re-attempt these in the loop; they need a reproduction trace and/or gameplay
context. Each has the analysis already done so a human can pick up fast.

> Status note (2026-06-19): the byte-exact frontier is effectively closed —
> oracle suite 244/244 and demo-replay 19/19 (bounded) are green. The primary driver is now
> the cold-boot endgame `/goal` brief ([`overnight_endgame_execution.md`](overnight_endgame_execution.md));
> the readability refactor (`refactor_plan.md`) is a sub-means to it. The only genuinely-open
> correctness blocker was the player-death full-demo divergence below.
>
> **Update (2026-06-28):** that player-death divergence — long the only open
> correctness blocker — and the `[95F2]`/`[95F4]` view-contact-center divergence
> are both RESOLVED by one fix: the AA46 `si>=3` no-contact branch (`AA54 JAE 0xAA44`).
> Full suite 537 passed / 23 skipped. Newly surfaced: an effect-activation
> timing / ISR-cadence phase offset (see backlog).

---

## 2026-07-04 — What is the A47C scripted-input script? (PARTLY RESOLVED: it is NOT player death)

**UPDATE (resolved half):** traced the player_death demo forward recording `DS:A47C` changes + `A6B9`
executions — across the WHOLE run up to the death frame (1805), A47C stayed 0 and the arm never fired.
So the A47C script is definitively NOT player death (death = the separate `9AFF` +08 anchor counter).
The three directly-A47C-linked functions were renamed `step_death_*`/`step_game_over_*` ->
`step_a47c_*` (byte-exact, probes pass). **Residual open:** (1) what the A47C script POSITIVELY is
(boss/cutscene/scripted-event) — needs a demo that actually drives A47C nonzero (e.g. a scroll-to-
position or boss-intro capture); (2) whether the countdown leaves `step_death_countdown_9e69` /
`step_game_over_countdown_9ee4` / `step_a95c_difficulty_countdown_9e43` are reachable only via the A47C
script (they were NOT renamed pending that link). Original analysis retained below.

**Blocker (original):** the A47C-indexed scripted-input subsystem (armed at `1010:A680` -> `A6B9` `mov [A47C],1`;
dispatched by `99F6`; handlers 1=9A78, 2=9A3E, 3=9A16; counters A95A/A95C/A97A/2384) was recovered
byte-exact this session and LABELED "death"/"game-over", but that semantic label is an assumption and the
evidence points elsewhere:
- the A680 arm gate is `A480==0 AND 234E==1 AND 2350==0x0EA0` — `234E`/`2350` are the world-scroll cursor,
  so it fires at a scroll POSITION and spawns an entity (`62AA`+`7524`): a scripted level/boss event
  shape, not collision-death;
- `A47C==0` at all 6 sampled demo seeds (incl. player_death and L6_boss); `A95A==3` / `A97A`!=0 are normal
  L1/L2 resting values, not death countdowns;
- the GROUNDED player-death path is the separate `9AFF` +08 anchor counter
  (`step_death_tail_9aff`/`detect_gameplay_transition`), demo-witnessed, which never touches A47C.

**Decisive experiment (before any rename pass or before wiring 99F6 into play_native as "death"):** trace
a demo forward and record every frame where `DS:A47C` changes and whether `1010:A6B9` executes. The
player_death demo's death frame is ~1805; a naive per-instruction Python step-callback over that many
frames TIMED OUT (>2 min). Need either (a) a lighter trace sampling at a single per-frame anchor IP with
near-zero work, (b) a purpose-recorded short demo that drives A47C nonzero (a scripted level-event/
boss-intro capture), or (c) instrumenting the VM memory-write path to log writes to A47C. Outcome
determines whether to rename the `step_death_*`/`step_game_over_*` functions to their true (scripted-
input/event) meaning. Functions are byte-exact regardless — a NAMING/semantics blocker, not correctness.

---

## RESOLVED (2026-07-03) — the 519A/5A6C unlifted-backend cold-boot gaps (518C/85D5/5EF9 cleared)

> **Fixed centrally.** `519A`'s unlifted-text-backend branch now runs the backend to its RET (fixes
> `518C`/`5F06`/`5EF9`); `hooks._run_5a6c_dispatched_target` does the same for `5A6C`'s unlifted blit
> backend (fixes `61DC`/`6120`/`85D5`). Both zero-gameplay-change (non-Tandy branch only). The hooks-ON
> cold-boot now runs 60K steps with no crash (past all three gaps) to `1010:4A52`; next crash beyond
> that is the next gap. See run_status. The dated per-gap notes below are kept as provenance.

## (historical) RESOLVED (2026-07-03) — the 519A cold-boot text gap; next hooks-ON gap is 85D5

> **Fixed:** the `518C` loop now handles `519A` dispatching to an unlifted non-Tandy text backend —
> when `519A` JMPs to the backend (`s.ip != 0x5197`), `518C` runs its original bytes until they RET
> to `0x5197` (`_run_original_text_backend_until_return`) instead of raising. Gameplay's Tandy-3153
> path always returns to `0x5197`, so it's unchanged. Verified: the hooks-ON cold-boot now runs PAST
> `518C` (fires 4×) to the **next** gap. The dated analysis below is kept as provenance.
>
> **NEXT hooks-ON cold-boot gap (2026-07-03):** `85D5 expected 5A6C to return to 8628, got 1010:4199`
> (at `1010:C4DB`, ~17.9K steps). Same pattern: on cold-boot the `5A6C` cell blit dispatches to an
> unlifted backend (`0x4199`, not the Tandy `306F`). Fix analogously — when `85D5`'s `call_cell_blit`
> lands `s.ip` off `0x8628`/`0x863D`/`0x864E`, run the original blit backend until it returns. Then
> rerun and take the following gap; this iterative loop is the cold-boot witness harness.

## (historical) OPEN (2026-07-03) — the 519A text dispatch raises on the cold-boot intro/title text path

Surfaced while testing a hooks-ON cold-boot (`install_replacements=True`, fast). The lifted `518C`
NUL-text loop (`rendering/text.py`) calls `run_text_dispatch_519a` and asserts it returns to `0x5197`;
on the cold-boot intro/title text it instead returns to **`0x4277`**, so the hook raises
("519A returned to unexpected IP 4277 inside 518C text loop") and halts the boot at `1010:4277`.

Root: `519A` dispatches through the video-mode text table (`CS:[95BC]` + backend flag `DS:21A2`); the
cold-boot text is drawn in a mode/backend the lifted `519A` doesn't model (it was verified for the
gameplay HUD text path). Not a gameplay regression (all gameplay tests + demos are green) — a latent
coverage gap only reached on the cold-boot path.

**To fix (a real cold-boot enabler):** trace what handler `519A` dispatches to at cold-boot (why the
`0x4277` continuation), extend the lifted `519A`/`518C` to model that text mode, gate it produced-vs-VM
(drive the intro/title text on a fresh hooks-on boot; or a synthetic-ASM oracle for the `519A` dispatch
table). This is the first of the hooks-ON cold-boot-path gaps; fixing them one by one is the fast route
to a cold-boot witness harness (see run_status). Repro: `create_overkill_runtime(exe, game_root,
install_replacements=True)` then step — halts at `1010:4277` within ~18K steps.

## RESOLVED (2026-07-03) — the 306F blit leaf is now verified via a synthetic-ASM oracle

> **Update (2026-07-03): the blit itself is DONE via oracle path #2.** `native_video/hud_chrome.paste_panel_cell`
> is byte-exact to the original 306F opcodes, proven by `tests/test_hud_chrome.py` (assembles the exact
> 306F bytes, runs them on a `CPU8086` over synthetic cells, compares). The demo witness-poverty below is
> unchanged and still applies to the FULL render path (85D5/859E cell selection + descriptor loop), which
> stays for the cold-boot phase — but the raw blit no longer needs a demo witness. The analysis below is
> kept for the remaining cell-selection/composer work.

## OPEN (2026-07-03) — static-HUD-chrome render (859E→306F) is WITNESS-POOR in all snapshot demos

Attempted the first native leaf of the static-HUD-chrome layer (Bucket C): `paste_panel_cell`, the
pure form of the `1010:306F` Tandy PANEL-cell blit (`lodsw` rows → `lodsw` width×4 stride → per-row
`rep movsb` into the packed B800 page, `DI += 0x2000` / wrap `+0x80A0`; a raw copy, no colour mask —
disasm-accurate, transcribed instruction-by-instruction). **Reverted (unverifiable):** the whole cell
render path `859E→85D5→5A6C→306F` fires **0 times** across EVERY snapshot demo checked — L2 (150f),
`start_to_end`, `L1_start` all show `306F=0`, `859E=0`. The HUD chrome is drawn **once at
cold-boot/level-load, BEFORE the demo snapshots are taken** (which is exactly why the earlier probe
found it ~99.5% static during gameplay — it's never re-blit). So there is **no demo witness** to gate a
native `306F` blit against.

**Correction to the prior run_status plan:** the "859E fires every present via D104" claim (from a
static byte-scan) is WRONG — D104/859E are not reached during snapshot-replay gameplay. Do NOT re-derive
the plan from that.

**To actually do this slice, a future run needs one of:**
1. a **cold-boot run** (fresh runtime via the `.is_cold_start` demo path — `demo_cold_start_*` has no
   snapshot; "boot a fresh runtime and replay") that executes the level-load HUD render, then wrap/step
   `306F` there; or
2. a **synthetic `306F` ASM oracle** (run the original `306F` bytes on a controlled CPU8086+Memory with a
   small synthetic cell, compare to `paste_panel_cell`) — the AGENTS.md "synthetic fixtures + interpreted
   ASM" path for witness-poor small routines.
The `paste_panel_cell` design + the `verify_native_hud_text` handler/step patterns are recorded above and
in this session's transcript; the blit mechanics are fully understood, only the witness is missing. Also
note `306F` is a registered hook that the **lifted parents bypass** (859E/85D5/5A6C run their Python lifts
and never jump to `306F`), and it's kept (not stripped) on the frame-verifier ref side — so neither a
handler-wrap nor a ref-side step-hook observes it via the lifted gameplay path; the cold-boot path is the
real witness.

---

## RESOLVED (2026-07-03) — L3 sprite-compose: was the unmodeled OR-inverted 2F40/2ECB leaves

> **Fixed same day.** Root cause: the native compose modeled only the masked compositor leaves
> (2E6E/2F81/2FB6); the OR-inverted leaves **2F40/2ECB** (`dest_word |= ~src_word`) were not
> captured, so the objects they draw (e.g. an L3 16×16 white block) were missing → `native=0`
> where `vm=15`. Recovered `decode_or_inverted_delta` (pure, `0xF ^ src` OR delta) + an
> `or_inverted` block kind in the native sprite layer + extractor capture. `verify_playfield_compose`
> is now **39/39 on L3** (was 24/29) and stays 100% on L1/L2/L4; `verify_native_starfield_plate`
> self-compose L3 39/39 too. The dated analysis below is kept as provenance.

## (historical) OPEN (2026-07-03) — L3 sprite-compose: 5/29 playfield frames diverge (plate-independent)

Surfaced while wiring the native starfield plate (not caused by it). `verify_playfield_compose`
— `playfield = plate + composite_sprites(blocks)` vs the VM's decoded `[9598]` playfield — is
byte-exact on **L1/L2/L4** (PASS) but **CHECK on L3**: 24/29 byte-exact, **5 frames diverge**.

- **Plate-independent.** `verify_native_starfield_plate` shows the starfield plate is byte-exact
  vs the VM on all 29 L3 frames; the 5 failures are identical whether the plate is VM-captured
  (`verify_playfield_compose`) or native (`verify_native_starfield_plate` self-compose = 24/29
  too). So the defect is in the **masked-sprite composite** (`composite_sprites` /
  `decode_masked_sprite` / the `MASKED_COMPOSITORS` block capture), not the background.
- **L3-specific in the current corpus** — L1/L2/L4 full-demos compose clean. Suspect an L3 sprite
  path the block-capture models slightly wrong (a compositor variant / `row_add` / opaque-mask
  edge case, or a block whose DF/rows differ). Not a `DF`-skip frame (skipped(DF)=0).
- **Repro:** `python -m overkill.probes.verify_playfield_compose artifacts/demos/demo_play_tandy_L3_full_20260617_202520 60`
  → `byte-exact=24 fail=5`. Next step for a fresh agent: dump the 5 diverging frames' per-block
  draw list (which compositor IP / di / rows) and diff the native vs VM playfield pixels to
  localize the offending block. Low urgency (render-fidelity, not a gameplay-logic gate), but it
  caps the render self-compose gate at <100% on L3.

---

## RESOLVED (2026-07-03) — the starfield is fully recovered; only backend WIRING remains

> **Update (2026-07-03): recovery DONE, this is no longer a blocker.** The starfield is a recovered,
> verified pure system — `recovered/systems/starfield.py` + `recovered/domain/starfield.py` (move at
> `1F8F:0922/0960`), probe `verify_native_starfield.py`, tests `test_starfield.py`/`test_starfield_cold.py`.
> Do NOT re-trace or re-recover it, and ignore the "Next: recover…" tails below (they are completed).
> The `4C76` "move" address cited below is WRONG — it is absent from the code; the move is `1F8F:0922/0960`.
> The ONLY remaining starfield work is wiring the pure system into `compose_playfield_indices` for the
> standalone `--backend native` frame (Bucket C). The dated analysis below is kept as historical provenance.

## (historical, 2026-06-29) — the starfield plate blocked the native frame (`--backend native`)

The standalone native frame is `playfield = starfield plate + sprites` (+ HUD). Every native
leaf is recovered **and proven byte-exact** EXCEPT the **starfield plate** (the sparse
parallax background): sprites (`composite_sprites` / `verify_sprite_layer`), the playfield
compose (`compose_playfield_indices` / `verify_playfield_compose`, 30/30), the HUD glyph
(`native_video/hud_glyph` / `verify_hud_glyph`, 256/256), and now the **full HUD/status text
line in packed B800** (`native_video/hud_text` / `verify_native_hud_text` — the whole 5EDB
line incl. score digits, 1800/1800 across L2/L5/L3) are done. So the starfield is THE
critical-path blocker for a self-composed native frame. **HUD digit band: DONE (2026-06-29)**
— the brief's "clean fresh-session slice" (3153 glyph + B800 composition) is closed; do not
re-attempt, only fold `hud_text` into the standalone backend compose (Bucket C).

- Eluded ~30 probes: the stars are a parallax PIXEL layer — the static-buffer-scroll model
  FAILED (0/60 plates reproduced, 0 colour conflicts → stars scroll at their own rate); a
  traced star byte showed NO writer (not `wb`/`ww`, not the bulk `rep movs/stos` even after the
  bulk-op watcher fix) → the plot is via a path the watchers miss (off-screen scroll-in
  suspected) or at level-load.
- **Next (fresh approach):** a parallax-aware trace at a SCROLL frame (star displacement vs
  the cursor delta → the star scroll counter), or a level-load capture. User noted it's
  pixel-plotted. Until then, the native frame must capture the VM plate (hybrid only).

**RESOLVED (mechanism) 2026-06-30 — the starfield is deterministic + recoverable.** Found with
`dos_re` `mem.write_watchers` (fires on ALL write paths). Over one frame, 7 sites write the present
source page (`CS:[9598]`); six are sprite blocks, and **`1010:4D6F` writes 40 scattered single bytes =
the ~40-px starfield**. The prior "NO writer" was a probe gap: the plotter **skips already-occupied page
pixels** (`4D2C jne`), so a fixed watched byte is usually never written. Routines (CS=1010): **erase
`4D64`** (zeroes the 40-entry working list `DS:0xC7B1`; Tandy single-byte `es:[di]`), **plot `4D15`** (set
up by `4CED`: stream `DS:0xC6C1`, list `DS:0xC7B1`, `bp=0x4D4D`), **move `4C76`** (advances the stream
per a video-mode jump table `cs:[0x4C8A+[95BC]*2]`, Tandy=shr1, parallax tables `DS:0xC803/C807/C80F` +
wrap counter `DS:0xC818`). A star is 3 words `{row, dx, color}`; page offset = `row*0x68 +
DS:[0x234C](cursor) + dx` (base table `DS:0x9A08 = row*0x68`; page row stride `0x68`=208px; present 3354
does the Tandy bank interleave). New-star ring `DS:0x20A8..0x20C7` via ptr `DS:0x20A6` (`4D95`);
level→initial-stream `DS:0xC601[level]`. Tables are DS-relative (DS=0x25CC). **Next: recover
erase/move/plot as pure systems; verify produced-vs-VM byte-exact (step-hook `4D64/4D15/4C76`); per-level
initial stream from a level-start snapshot.** Full detail in the `overkill-starfield-render` memory.

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
this session by examining the two unblocked Bucket-A behaviors: `B250`'s overlap-box test is
flag-coupled at each early return (AX/BX/flags differ per exit), and `8d4f` is a waypoint read +
a trivial `+0x20` offset + mode stamp then delegations to the already-lifted `5DB2`/`bc4b`.
**CORRECTION (2026-06-29, later): `B250`'s box DECISION was recovered after all** -- the
flag-coupling is only in the staged arithmetic; the predicate `overlap_contact_box_contains`
(systems/collision.py) is pure + verified produced-vs-VM (10,767 calls, 0 div), with the hook
keeping the staged arithmetic for AX/BX/flags + cross-checking.  (The lesson again: attempt the
leaf, separate the decision from the flag mechanics.)  `8d4f` remains mostly delegation glue.  So the
gate-compliant remaining work is (a) the hard Bucket-A islands (pure-raising but multi-leaf), or
(b) the native-runtime build itself (which collapses the adapters and repays the dilution).

**Update (2026-06-29, later) — clean low-risk pure-raising veins now EXHAUSTED; do NOT re-grind:**
- inline→pure spawn templates: done (A4EA `e2bd8d7`); the rest are single-use (over-engineering).
- faithful recovery of witness-poor `_observed` lifts: 5F0D was the one clean one (`bcd_add_score`
  `332b58d`); the others (`bec5`/`9e69`/`9e98`/`bd17`/`bd0d`/`7476`/`7420`) are the hard
  death/contact/spawn frontier (attended-only — that is *why* they are observed/partial).
- Bucket-A unblocked behaviors: `B250`'s box predicate is now RECOVERED (`overlap_contact_box_contains`,
  16th producer) -- it unblocks the b24d/aed8 EFAE handlers; `8d4f` remains delegation glue.
The one vein that BOTH raises pure % AND is non-blocked is the **native-runtime build (Bucket C)**;
per-handler native slot-transforms (now that B250 is pure, b24d/aed8 are the nearest) feed it.
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

**Behavior survey (2026-06-29) — the clean MOVEMENT producers (AE09 + 5DB2) are the harvest of this
vein; the rest need harder pieces.** Read each behavior's body: AE09 = clean fixed-step (done); the
seekers b73e/b9f0/8d4f = 5DB2 (done) + bc4b; b86d = interpreted `7476` near-call + the `5E42`
delta-steer (Bresenham) + bc4b (coupled); aed8 = AEE4 + `B250`->ADC9 (x=FFFF coupling); b9f0 = the
follower (5DB2 + its own ~7 decisions + bc4b). So the next object-update producers, in rough order of
tractability: (1) **bc4b Y-clamp** (clean, always-runs; completes the post-move Y of every behavior),
(2) **`5E42` delta-steer** (delta->direction->AF22/AF63 step; composable but has the 5EB5/5EC8 + the
move_step_error Bresenham accumulator; covers b86d's steering), (3) the **global death/spawn
side-effects** (`BD17`/`BFC7` -> counters/spawns -- the attended island), then (4) the per-logic-id
native dispatch composing them.  The two highest-frequency movement primitives are already native.

**Attempted + reverted (2026-06-29) — the full AE09 slot transform (movement + active) needs the
tile-collision path / LevelState.** Tried extending the AE09 producer with the `active` field via the
AD60 bounds decision (`object_update_ae09` = movement + AD60 -> active).  It VERIFIED for the non-tile-
probe cases (L5_continue 22/22, L5_short 21/21) but **SKIPPED the majority** (755 + 617): most AE09
objects hit AD60's **tile-probe** branch (the draw_layer-2 family), whose deactivation depends on the
under-object tile sample (`5073` offset -> `505B` class -> ADC1 check).  So a slot's `active`/death for
the tile-probe behaviors is gated on the **level tile map** — i.e. it needs a recovered **LevelState**
(the tile grid) + pure `5073`/`505B`.  Reverted the partial (skip-heavy) producer per §3; the clean
movement producer stands.  **Next substantial recovery: LevelState's tile map + the pure tile probe/
lookup** — that unblocks the per-slot active/death for AE09 and the whole tile-probe family, and is the
§1.2 ``LevelState`` mirror besides.  (The movement halves are done; this is the death/bounds half's
dependency.)

**DONE (2026-06-29, later) — the full AE09 slot transform IS complete; the revert's premise was wrong.**
The tile probe/lookup (5073/505B) were ALREADY pure-recovered (`systems/tilemap.py`); only the tile-map
INPUTS were missing.  Modeled them as `LevelTileContext` (DS:234E origin, DS:2350 row base, CS:[9592]
tile plane, DS:C3AA class table -- a LevelState seed), recovered the AD60 tile-collision composition
`object_tile_probe_deactivates_ad60` (5073 +13 row -> 505B -> class==1 -> deactivate), and shipped
`object_update_ae09` (movement + AD60 bounds/tile -> active).  **Verified produced-vs-VM byte-exact**
L5_continue 353/353, L5_short 342/342, 0-div, NO skips (tile-probe included).  So the COMPLETE AE09
slot transform is native (everything but the BD17 global counter/spawn side-effects).  **Pattern proven:
movement primitive + AD60 bounds/tile -> the next slot.**  Remaining object-update: apply this template
to the other behaviors (the seekers via 5DB2 + bc4b; the 5E42-steer b86d), and the global death/spawn
side-effects (BD17/BFC7), then the per-logic-id dispatch.

**Clean low-risk producers exhausted (2026-06-29) — remaining object-update = 2 complex primitives.**
Checked the last short behaviors: `b24d` = `5E42` steer + `B250` selector (coupled); `aba3` = a 1-field
sprite (`object_logic_aba3` ALREADY recovered + the AC81 collision tail) = marginal/re-verification.
So after AE09 (fixed-step + full transform incl. tile-collision) + 5DB2 (target-seek), the two
remaining MOVEMENT/postmove primitives are both complex multi-part recoveries, best done with fresh
context: (1) **`5E42` delta-steer** -- delta_x/y (+2A/+2C) -> direction via the `5EB5`/`5EC8` sign bits
+ the `move_step_error` (+2E) Bresenham accumulator + `A348` table -> `AF22`(DS:2312==3)/`AF63` step;
the 3rd movement primitive (covers b24d/b86d steering).  (2) **`bc4b` postmove slot transform** --
y-clamp (`clamp_postmove_y_bcb1` ✅) + x-bounds death (`BD17` -> active=0) + the collision path
(BCCB -> `AA46`/`AA71` view-window ✅ -> `BFC7` death: logic_id=1 + C037 sprite + latch); the shared
postmove for the seekers (b73e/b9f0/8d4f), composable from recovered pieces but multi-branch.  The
template (movement primitive + bounds/tile -> next slot) extends to both; then the global death/spawn
side-effects + the per-logic-id dispatch.

**BFC7 death tail RE-READ (2026-06-29) — confirmed attended, with 3 observed sub-leaf prerequisites.**
Applied the attempt-don't-declare rule to `_run_collision_death_tail_bfc7` (object_deactivation.py:156):
the "clean" final transition (logic_id=1 + C037 sprite + latch) is buried *under* the global death/spawn
machinery, and the routine CALLs three still-observed sub-leaves that must be recovered first: (a)
`_run_score_add_5f0d_observed` — **DONE (2026-06-29)**: converged onto the verified `score.bcd_add_score`
(re-verified byte-exact vs the assembled 5F0D + a full kill-heavy demo, 0 divergence); (b) `_run_linked_effect_spawn_7420_observed`
(the linked-counter spawn) — **DONE (2026-06-29)**: recovered the field-init as the pure
`object_spawn_seed_7420` (systems/objects.py) returning `LinkedEffectSpawnSeed7420` (x = DS:2378 + DS:A278;
y = min(DS:2376, 0xC0); sprite = DS:237A + 0x46; raw type at +26h; constants active=1/scan=1/hazard=5/
logic=0/latch=0/linked=FFFF/variant=0/layer=0), with the hook a thin adapter (7524 alloc + write order +
register/flag choreography).  Verified: a VM-free synthetic oracle (`test_object_spawn_seed_7420`) + the
produced-vs-VM probe `verify_native_object_spawn_seed_7420` (rare event, as predicted) — **34 spawns across
L5_continue 20 / L3 10 / L2 2 / start_to_end 1 / L4 1, 0 divergence** (L6_boss/mothership/showcase have 0,
confirming they aren't linked-counter groups).  (c) the **C054** selector — **already pure** (the classifier
`object_deactivate_dispatch_decision_c054`, systems/objects.py, with a self-verifying adapter); I mis-stated
it as pending in the 7420 note above.

**BFC7 island status corrected (2026-06-29): all 5 COMPUTATIONAL leaves are now pure.** Reading the whole
BFC7 body (object_deactivation.py:156-274) shows it is: the 0021h/DS:2356 gate; the score add (✓
`bcd_add_score`); the y-clamp (✓ `clamp_postmove_y_bcb1`); the linked-counter chain -> 7420 spawn (✓
`object_spawn_seed_7420`); the C054 selector (✓ classifier) + its C12D effect tail; and the final C037
death transition (✓ NEW `object_collision_death_transition_c037`: prev_logic_id=old, logic_id=1, latch=0,
sprite by type 1->0/2->3).  What REMAINS is pure GLUE, not transforms: **C12D** (`_run_c054_c12d_effect_
spawn_tail` — stages 7420's inputs from the slot + writes DS:A482/A842 + decrements DS:A47E around the now-
pure 7420; no extractable computation) and the **BFC7 orchestration** itself (the gate, the counter-chain
decrement, the DS:98C0->BEFF gate, the stack-scratch).  So BFC7's coastline is now shortened to its leaves;
fully composing BFC7 as one pure transform = a multi-output orchestration over the 5 pure leaves (a Bucket-C
integration).  The non-blocked pure-%-raising vein remains the **Bucket-C native runtime**.

**DONE (2026-06-29) — 5E42 delta-steer recovered (the 3rd movement primitive).**
`object_delta_steer_5e42` (systems/movement.py): signed deltas (+2C/+2A) -> Bresenham axis pick vs the
`move_step_error` accumulator (+2E) -> A348 sign bits -> direction (FFh=blocked) -> AF22/AF63 step by
DS:2312.  Verified produced-vs-VM byte-exact L2 64/64 + L6_boss 121/121 (11th producer).  So ALL three
object movement primitives are native: AE09 fixed-step, 5DB2 target-seek, 5E42 delta-steer.  The ONE
remaining movement/postmove primitive is **bc4b** (the shared seeker postmove): y-clamp ✅ + x-bounds
death (BD17 active=0) + the BCCB -> AA46/AA71 (✅ recovered) -> BFC7 collision-death (logic_id=1 + C037
sprite + latch) -- multi-branch but composable from recovered pieces.  After bc4b: the global
death/spawn side-effects (BD17/BFC7 counters/spawns/C12D effect scripts) + the per-logic-id native
dispatch over `NativeGameState`'s pool, then the standalone loop.

**bc4b assessed (2026-06-29) — the most intricate piece; the SLOT transform is composable but its
collision path has observed sub-routines (global effects to scope out).** Read the full bc4b lift
(`object_postmove.py`): the slot-affecting parts are y-clamp ✅ + the x-bounds death + the BCCB
collision (`AA46` type1 / `AA71` type2, both ✅ -> CF, gated by global_disable/+0x16/+0x18/obj_type/
DS:A8C2) -> `BFC7` death (the SLOT side = logic_id=1 + previous_logic_id + transition_latch=0 + C037
sprite for obj_type 1/2; recoverable).  BUT the collision path ALSO runs `9E69` (post-contact ->
9E98/61DC DISPLAY tail) and `62F6` (object overlap scan) -- both "observed"/interpreted, NOT pure;
they appear to be GLOBAL/other-slot effects (display, cross-object scan), so a SLOT-scoped bc4b
transform can likely scope them out (as AE09 scoped out BD17's globals) -- but that must be VERIFIED
(confirm 9E69/62F6 don't write the current slot's y/active/logic_id/sprite).  Collision inputs: the
view-contact center (DS:95F2/95F4, from the view target) + the contact window.  So bc4b is a clean
fresh-session slice IF 9E69/62F6 are confirmed slot-neutral; the gate (produced-vs-VM at bc4b RET)
will catch it either way.  This is the LAST movement/postmove primitive before the global
death/spawn side-effects + the dispatch.

**DONE (2026-06-29) — the BC4B bounds half (y + active); 9E69/62F6 CONFIRMED slot-neutral.**
Shipped `object_postmove_x_bounds_deactivates_bc4b` (the X-bounds death: precise box [-C0h, F0h)
unless DS:A47C set / wide-exempt logic id -> [-14h, F0h)) composed with the recovered
`clamp_postmove_y_bcb1` -> the BC4B slot fields y + active.  **Verified produced-vs-VM byte-exact**
L2 1498/1498, L6_boss 2257/2257, player_death 2181/2181 (5936 calls, 0-div) -- which PROVES (a) the
collision death (BFC7) sets logic_id, not active; (b) 9E69/62F6 are slot-neutral for y/active.  So the
remaining BC4B work is just the **collision-death logic_id/sprite half** (BCCB -> AA46/AA71 (recovered)
-> BFC7 transition: logic_id=1 + previous_logic_id + transition_latch=0 + C037 sprite for obj_type 1/2)
-- verify those slot fields at BC4B RET on the collision-hit objects.  After that: the global
death/spawn side-effects (counters/spawns) + the per-logic-id native dispatch.

**Collision-death half recipe (assessed 2026-06-29 — the recovered pieces are all pure; compose +
verify).** The BC4B collision-death transition fires when (read object_postmove.py 100-155):
global_disable(DS:A47C)==0 AND active AND hazard_class(+16)!=5 AND logic_id(+18) not in {0,1} AND
obj_type(+14) in {1,2} AND the contact test hits AND DS:A8C2 != 1.  The contact test: obj_type 1 ->
AA46 = `view_contact_center_from_offsets_aa46`(view center + the DS:214E[DS:2384*4] dx/dy offset, with
the si>=3 -> no-contact guard) then `view_contact_rect_test`(slot, center, half-extent 0x10); obj_type
2 -> `postmove_contact_window_test_aa71`(slot, window from DS:237E/2380 + the spans, narrowed by the
DS:A8C2 boss flag).  On a hit, BFC7's slot transition = previous_logic_id := old logic_id; logic_id :=
1; transition_latch := 0; sprite_or_state := C037[obj_type] (type 1 -> 0, type 2 -> 3).  All those
helpers are recovered pure (systems/collision.py).  OPEN to confirm when building: the exact AA46
view-center source (DS:237E/2380 vs DS:95F2/95F4) + the AA71 X-window bounds -- read
`collision_adapter.run_view_window_check_aa46` + the AA71 adapter.  Probe: at BC4B RET, verify
logic_id/previous_logic_id/transition_latch/sprite for the collision-hit objects (the gate catches any
mismatch).  This is a clean fresh-session slice; it just composes more pieces than the bounds half.

**ATTEMPTED + REVERTED (2026-06-29) — the collision-death has a SECOND source: the 62F6 overlap scan
(NOT just AA46/AA71).** Built `object_postmove_collision_death_bc4b` = the AA46/AA71 view-contact ->
BFC7 transition (logic_id=1 + previous_logic_id + latch=0 + C037 sprite), composing the recovered pure
contact tests, and probed it.  Result: **1483/1498 byte-exact, 15 fails** -- all one obj_type-1 object
(logic_id 0x1d).  Diagnostic proved the AA46/AA71 model is structurally INCOMPLETE: the failing object
(slot x=0x6c, y=0x8c) transitioned (logic_id 0x1d->1, sprite->0) but its X is 0x4B from the AA46 center
(0xb7) -- WAY outside the +/-0x10 rectangle, so AA46 correctly does not hit.  The transition came from
`62F6` (the BC4B object-OVERLAP scan, object-vs-object collision -- run after BCCB), which is
observed/interpreted, NOT a clean recovered leaf, and CANNOT be scoped out (it depends on the scan over
*other* objects).  Reverted per §3 (15-fail = red).  So the FULL BC4B collision-death needs `62F6`
recovered too (an object-vs-object overlap scan + its transition) -- that is the genuinely-hard,
attended part; the AA46/AA71 view-contact half is correct (1483) but insufficient alone.  Corrected
fact: the BC4B collision death = AA46/AA71 view-contact OR the 62F6 overlap scan; both -> BFC7-style
transition.

**62F6 internals assessed (2026-06-29) — a grid overlap scan (recoverable) -> BEC5 (observed handler).**
Read `contact_side_effects.py:_run_object_overlap_scan_62f6`: after pre-scan exemptions (inactive,
x<20h, draw_layer +16 ==0, logic_id +18 in {0,1,26h}), it scans the gameplay object table for an
active + solid (`scan_enable_or_solid` +1E) candidate sharing the current object's 8px grid cell --
`dx = y & FFF8`, `cx = x & FFF8`, with obj_type-dependent extra y/x candidate cells (type 2 adds
two more rows, and X cells unless logic_id in {78h,79h}).  On a grid match it jumps to **`BEC5`**
(`_run_collision_handler_bec5_observed`), the collision handler that performs the transition -- and
**BEC5 is observed/unlifted** (the genuinely-attended part).  So the 62F6 path = a recoverable pure
grid-overlap scan over `NativeGameState`'s pool (the cell-match decision) + the UNRECOVERED BEC5
transition handler.  Fresh-session plan: recover BEC5 (the handler), then the 62F6 scan composes the
recovered AA46/AA71 + BEC5 + the grid test into the full BC4B collision death.  This is the genuine
object-vs-object collision island -- a cross-object scan + an observed handler, the attended frontier.

**BEC5 internals assessed (2026-06-29) — a deeply multi-variant handler, NOT a quick leaf.** Read
`contact_side_effects.py:_run_collision_handler_bec5_observed`: it dispatches on the COLLIDED
candidate's logic_id (variants 07h/08h/0Ch, the sprite-0033 variant-2, the 5/6 and 7/8/0C
continuations), runs `counter_20` (+20) decrement chains gated by `BEDC` (difficulty) and `A8C2`
(boss), and branches into `BFC7` (death transition), `BD0D` (cleanup -> BD17), and `BF5F` (the A8C2
mark tail) -- and it is itself "observed"/partial ("currently verified branches").  So recovering it
is a meaty multi-variant island (the per-variant counter/death/mark machinery), not a single leaf --
the genuine attended object-vs-object collision work.  Full bc4b collision-death = AA46/AA71 (done) +
the 62F6 grid scan (recoverable) + BEC5 (this multi-variant handler) -> a fresh-session island.

**RESOLVED (2026-06-29) — the ENTIRE object-vs-object collision island is now native source.** The
"attended frontier" above fell decision-by-decision once the death tails landed: `62F6` grid overlap
(`object_grid_overlap_62f6`), the BEC5 variant dispatch (`bec5_collision_variant_family`), the BF25
damage counter chain (`collision_damage_counter_chain_bf25`), and the death/spawn tails (BFC7 +
`bcd_add_score`/`object_spawn_seed_7420`/`object_deactivate_dispatch_decision_c054`/
`object_collision_death_transition_c037`) are ALL recovered + verified (synthetic + assembled-ASM
oracles + the BEC5/62F6 hook cross-checks, with frame-verifier 0-divergence on L6_boss/L2_full).  Do
NOT re-investigate this as a blocker.  LESSON: an "attended/observed multi-variant island" is not
permanently blocked -- it unblocks as its leaf dependencies (here the tails) get recovered, then the
dispatch/decisions extract cleanly.  Remaining collision composition: folding these pure pieces into a
single native BEC5 transform is a Bucket-C runtime task, not a recovery.

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

---

## PARTIALLY SUPERSEDED (2026-07-03) — the whole object scan diverges on ~2 variant-2 gameplay slots/frame

> **Update (2026-07-03): the `0x1c`/`8D4F` premise below is STALE.** `object_update_8d4f` now exists
> (`systems/objects.py`) and the native dispatch DOES handle `0x1c` (`_advance_8d4f`, `systems/object_update.py`),
> so "my driver only dispatches 0x0C/0x02/0x1D/0x14, skips 0x1c" no longer holds. Re-derive this
> divergence against the CURRENT driver before acting on it; the remaining un-dispatched scanner may be
> only `0x1e` (`B909`, a spawner). Do not re-attempt from the stale analysis; re-trace first.

`native_object_scan` (the VM-free A9E0 object pass over one contiguous 0x45-slot store, both
pointer-table loops in place) was attempted and reverted (red). The effect loop is byte-exact
(1170/1170 L2, 1723/1723 L3), but ~2 gameplay slots/frame diverge and **neither separate pools
nor the shared store fixed them**. Confirmed not a tables-overlap bug and not AED8 timer-death.

- **Symptom (stable across L2/L3):** a `logic_id=2` (AED8) gameplay slot — VM has it
  `active=0`, substate UNCHANGED (e.g. 0xfff9); my pass has it `active=1`, AED8-processed
  (substate−1, x−8). So the VM **deactivates it in the EFFECT loop as a collision candidate**
  (active→0, substate untouched), then the gameplay loop skips it; my effect-loop collision
  does **not** kill it, so my gameplay loop AED8-processes it. (Slots: L2 0x2ce4/0x3064,
  L3 0x2c3c/0x2c74.)
- **ROOT CAUSE (traced 2026-06-30, RESOLVED the mystery):** NOT an order/path bug. A trace of the
  effect-loop kills (`scratchpad/trace_effect_loop_kills.py`) shows all 17 effect-loop deactivations on
  L2 are variant-2 candidates cleared at `BF1B` -- and the SCANNER logic_ids that trigger them are
  `0x1d` (B86D, native: 15) and **`0x1c` (1) + `0x1e` (1) -- NOT native handlers**.  My driver only
  dispatches `0x0C/0x02/0x1D/0x14`, so it skips the `0x1c`/`0x1e` scanners entirely, never runs their
  BC4B/62F6 collision, and so never kills the 2 candidates -> the gameplay loop re-processes them.
- **The whole-scan is blocked on the `0x1c` and `0x1e` behaviors** (via the EFAE table at CS:EFC4,
  indexed by logic_id*2: `[0x1c]=8D4F`, `[0x1d]=B86D`, `[0x1e]=B909`).  Both are NON-trivial (deeper
  than B86D/B9F0), so this is not a quick handler slice:
  - `8D4F` (0x1c) is a **far-segment dispatch** -- `call far 1F8F:027A` (the movement is in the 1F8F
    overlay, outside the 1010 code) then `jmp BC4B`; 8D4F is itself a multi-entry table of
    `call far 1F8F:0xxx; jmp BC4B` sub-behaviors.  Recovering it means reversing the 1F8F routine(s).
  - `B909` (0x1e) is a **spawning** behavior -- sets DS:2308, calls the `B729` seek, conditionally
    calls `7476` (the formation spawn) and stamps `bp+50`, then `jmp BC4B`.
  Each needs its post-movement position for the BC4B/62F6 collision, so the movement half can't be
  skipped.  Recover each (1F8F:027A for 8D4F; B729+7476 compose for B909), verify per-slot with
  `verify_native_object_update_driver`, then rebuild the shared-store `native_object_scan`.  Lower
  priority than a fresh clean pillar (these are rare behaviors; the whole-scan's last ~2 slots/frame).
- **What IS verified + committed (do NOT re-derive):** the per-slot driver incl. collision
  death (`verify_native_object_update_driver`, sprite_deferred 0); the effect-loop in-place
  pass (`verify_native_object_pass_in_place`, L2/L3 0-div); the gameplay snapshot
  (`verify_native_object_pass`). Only the *combined whole-scan* is open.
- **Next (now precise):** recover the `0x1c` and `0x1e` object behaviors as native whole-slot
  handlers (movement + BC4B contact, like B86D/B9F0), via the EFAE/EFC4 behaviour dispatch; verify
  each per-slot with `verify_native_object_update_driver`; then rebuild the shared-store
  `native_object_scan` + `verify_native_object_scan` (the design is correct, only the missing
  scanners blocked it) and it should go byte-exact.

## 2026-07-04 — death/level-end FRAME exceeds the frame-verifier per-frame budget (replay caveat, not a bug)

Replaying `demo_play_tandy_player_death_20260618_233821` under the frame verifier TIMES OUT at
**frame 1805, IP 1010:32DB** (`FrameVerifyDivergence: FRAME VERIFY TIMEOUT ... budget=6000000`): the
death/explosion+scene FRAME runs >6M instructions. Not a recovery defect — a harness per-frame budget
limit at the transition frame. **Workaround:** witness transitions via the run-up (cap `max_frames`
just before the heavy frame). `verify_native_gameplay_transition.py` already caught the 4 DEATH-exit
frames at frames <1790. If a future slice needs to replay THROUGH a death/ending transition, raise the
`frame_budget` for that run rather than treating the timeout as a divergence.

## 2026-07-04 — lifted A940 attract branch (game_state.py ~150-154) mis-handles 98A5 > 1 (untested path)

The lifted ``run_frame_game_state_update_a940`` attract-mode branch (``DS:2356 == 5``) writes 98A5/98A3
unconditionally in the ``98A5 != 0`` arm, so for ``98A5 > 1`` it sets 98A5:=CL(0) + inc 98A3. The
ORIGINAL (driven-oracle, ``verify_native_a940_attract.py``) instead DECREMENTS 98A5 to 98A5-1 and
RESETS 98A3 to 0 (the ``1010:A9B3`` branch). This lifted bug is latent — NO gameplay demo runs 97B2
with ``2356 == 5`` (the in-game demo-playback mode), so it's never exercised in the suite. The PURE
``step_a940_attract_middle`` is correct (matches the original on all branches). If the lifted attract
branch is ever put on a witnessed path, fix it to match the pure rule (or delegate the lifted adapter
to ``step_a940_attract_middle`` + ``a940_speed_bucket``). Low priority (attract-only).
