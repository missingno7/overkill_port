# Overnight endgame execution — the cold-boot VM-less full game (the `/goal` brief)

> **THIS IS THE CANONICAL `/goal` BRIEF. Run `/goal` on this file.** It is an executable,
> unattended brief: an autonomous agent runs it for many hours, one verified slice at a time,
> tested against the demos, committing as it goes, until the cold-boot done-condition in §1 is
> met (and prints `COLD-BOOT ENDGAME REACHED`).
>
> The **lifecycle & vision** (the *why* + the full arc + the equivalence boundaries) is
> [`game_recovery_lifecycle.md`](game_recovery_lifecycle.md); the OVERKILL restatement is
> [`native_game_endgame.md`](native_game_endgame.md).
> The **method** (the *how*, per slice) is
> [`semantic_crystallization_plan.md`](semantic_crystallization_plan.md),
> [`source_port_methodology.md`](source_port_methodology.md), and
> [`native_recovery_goal.md`](native_recovery_goal.md) (the dual-mode slice shape). The **map**
> of what is still ASM vs pure is [`coastline_report.md`](coastline_report.md)
> (regenerate live with `python scripts/source_port_status.py`); live status is
> [`run_status.md`](run_status.md).
>
> This document is the loop that drives all of them. Do not duplicate their content; follow them.
> There is exactly one `/goal` target — this file.

---

## 0. Mission

Two backends, **not two equal renderers** — a transition path from oracle-driven
recovery to a standalone modern port:

```
--backend vm      the recovery/ORACLE backend: original ASM on the VM is the source
                  of truth. Used for oracle verification, hook development, lockstep
                  comparison, ASM recovery, regression, debugging. PERMANENT — as a
                  detachable verification harness, never a required runtime.

--backend native  the future STANDALONE port. Today: partial native path that may
                  still lean on hybrid-produced state. Endgame: the complete recovered
                  game, running from NativeGameState -> recovered systems ->
                  recovered render/audio state -> native backend, with NO VM.
```

The long-term goal is **not** "a VM with a nicer renderer." It is for `--backend native`
to become the complete recovered native game, while `--backend vm` remains available for
verification and historical correctness.

**Scope: the full game, cold-booted.** The destination is not only the gameplay demos
running standalone — it is the *whole game from a cold start*: a native entry that loads
the game's own data files (the EXE as an asset container, no VM), runs the
intro → title → menu → map front-end, loads each level, runs the native gameplay frame with
native render and audio, handles level transitions, and reaches the ending — all with the VM
available only as the optional oracle. The demos-standalone gate (§1.1–1.4) proves the
gameplay core; the cold-boot gate (§1.5–1.8) proves the whole game.

**The one design rule that makes both possible (the dual-mode systems rule):** a recovered
system is written against **source-level state structures the native side owns**, never
against `cpu`/segment:offset. The hybrid path reads VM memory into those structures and
writes results back; the standalone path passes the structures directly. *Same logic,
proven in hybrid, reused unchanged standalone.* The hook wrappers are temporary; the
recovered systems are permanent.

---

## 1. Definition of DONE (the stop condition)

The destination is the **full game, cold-booted, with no VM** — not only the gameplay demos
standalone. Re-derive from metrics + demos each pass; do not guess. Two tiers:

### Gameplay core (the demos run standalone)
1. **Standalone runs the demos with no VM.** `--backend native` in standalone mode
   (the VM is never started) replays every demo in `artifacts/demos/` to completion.
2. **The native state mirrors the oracle.** In verify mode (native + VM oracle side by
   side) the native semantic state — `PlayerState · ObjectPool · ProjectileState ·
   CombatState · CameraState · LevelState · ScoreState · RngState · RenderState` — matches
   the VM-derived state at every checkpoint, across every demo, with zero divergence.
   (Render: byte-exact playfield + frame as already proven by `verify_playfield_compose`,
   extended to the whole frame.)
3. **The runtime path is VM-free.** Standalone needs none of: VM memory, interpreted ASM,
   original framebuffer, hook dispatch, CPU registers, segment addresses, live oracle calls.
4. **The coastline is collapsed.** `scripts/source_port_status.py` shows gameplay logic
   essentially all in `source_pure`/`game_core` (pure % → its ceiling; **30.2% as of
   2026-07-03**, up from 22.0% on 2026-06-30 and 14.3% earlier), the `glue` hook count near
   zero, and `hooks.py` back under its size budget. Remaining hooks are thin adapters used
   only by `--backend vm`.

### Full cold boot (the whole game, from a cold start)
5. **Cold boot, no VM.** A native entry (e.g. `scripts/native_boot.py`) starts the game from
   nothing but its own data files (the EXE as an asset container): it loads + decompresses
   assets, runs the intro → title → menu → map front-end, loads a level, runs the native
   gameplay frame + native render + native audio, handles level transitions, and reaches the
   ending — with no `dos_re` on the runtime path.
6. **Asset/level load is native.** The asset codecs (`0324` RLE / `0615` stream + the loader)
   and the level loader are recovered pure systems that build `NativeGameState`/`LevelState`
   from the data files, byte-exact vs the VM's load.
7. **Audio is native.** Music (the AdLib/OPL driver → the existing Nuked-OPL3 synth) and SFX
   (the PC-speaker driver → PIT square wave) play from recovered drivers feeding the synths
   already present, with no VM mixer.
8. **Playable end-to-end.** A recorded native session boots cold and plays through to the
   ending (not only unit-verified) — the proof that the whole chain composes.

**Print `COLD-BOOT ENDGAME REACHED` on its own line ONLY when every clause 1–8 is literally
true and freshly verified this pass.** Otherwise never print it — keep iterating §2.

**Milestone gate on the way:** a **VM-less single LEVEL** (1–4 + native level load, clause 6)
is the first cold-boot milestone; the full front-end/audio/boot (5, 7, 8) layer on after.

---

## 2. The recovery loop (the core discipline — demand-driven, never top-down)

The native backend is **not** a separate rewrite that guesses how the game works. It is a
**consumer of recovered game state.** Progress is driven by *trying to express a piece of
the game natively*, letting the gap that attempt exposes pull the next recovery — found at
the original boundary, built bottom-up, verified, then lifted into the native source layer.
**Never jump from incomplete knowledge to a native approximation.** If something is missing,
go down, recover it, verify it, lift it.

Each iteration:

```
1. ATTEMPT a piece natively. Try to implement or run one feature on --backend native
   (a render layer, an object/camera/combat behavior, a state field, a timing).

2. IDENTIFY what is missing to make it correct: missing state / behavior / timing /
   render data / object-camera-combat-audio logic. The native attempt IS the probe that
   reveals the gap.

3. GO DOWN to the original boundary: find the ASM routine; find the hook point; map
   inputs/outputs; identify the memory fields and side effects (scripts/dump_world.py,
   trace_world_writes.py, summarize_world_writes.py, disassembly, the hook verifier).

4. BUILD a small recovered version: first a SHADOW implementation (run beside the ASM,
   compare), then a VERIFIED hook replacement, finally a SOURCE-LEVEL system. Reuse
   existing pure helpers; never duplicate a decision (the dedup rule).

5. VERIFY it (§5): against existing demos when available; against captured snapshots/
   checkpoints; against per-routine ASM behavior; against full demo-replay where possible.

6. IF NO DEMO COVERS IT (witness-poor): use disassembly to understand the routine; build
   targeted probes; create synthetic fixtures when appropriate; add a new witness/demo
   when possible; and **clearly mark what is proven vs still witness-poor** (in the
   docstring + island_truth_tables.md). Do NOT promote a witness-poor guess into a pure
   system as if it were proven.

7. LIFT the recovered logic upward: hook wrapper -> adapter/view -> domain/system ->
   native runtime state. The hook is temporary; the recovered logic is permanent.

8. CLOSE the island: recover all required leaves, verify the composed subsystem, and
   replace the ASM boundary only when the whole island is understood well enough. Then
   resume the native attempt (1) with the gap filled.
```

**The discipline in one line:** if the native path needs something it doesn't have, recover
that something at the hybrid/source layer first — never fake it in the renderer or runtime.

Around this sits the unattended operational wrapper:

```
- HEALTH GATE first: a red suite / failing verify gate halts the loop until fixed (§3).
- One verified island-step = one focused commit + push. On ANY failure, REVERT the attempt
  fully (leave the tree exactly as before) and append a short entry to loop_blockers.md
  (what, why it diverged, the repro), then move to the next attempt. Never weaken a
  test/oracle to pass; never leave broken state.
- Self-directing: re-read the metrics + `git log` + the queue (§6) each pass to choose the
  next native attempt; skip anything in loop_blockers.md. No human picks the next item.
- Stop only on the §1 done-condition, on §8 "queue refill" yielding nothing actionable, or
  on an infra failure that blocks the suite.
```

---

## 3. Hard invariants (unattended safety — non-negotiable)

These exist because nobody is watching. Violating any of them silently corrupts the
overnight run.

- **Never commit red.** Every commit is preceded by a green verification (§5). If you
  can't verify it, you can't commit it.
- **Never weaken an oracle, test, or assertion to make a slice pass.** The whole project's
  value is the byte-exact proof. Loosening it to show progress is a regression, not progress.
- **Failed slice ⇒ full revert + document.** Use `git checkout`/`git restore` to return to
  the pre-slice tree, log it in `loop_blockers.md`, move on. Never leave a half-applied
  collapse.
- **One verified slice = one commit + push.** Durable, reviewable, crash-safe. (This repo
  commits to `main`.) The commit log is the overnight progress trail.
- **Fail loud, never fake.** If a recovered assumption breaks, raise — do not add a silent
  fallback, and do not invent missing game knowledge inside the renderer. If the native
  backend needs state the recovered layer doesn't expose yet, recover that state at the
  hybrid/source level first (`native_game_endgame.md` §"native backend's relationship").
- **Conservative names.** `logic_id` not `enemy_type`; `ObjectSlot` not `Enemy`; address-
  anchored helper names until multiple traces prove an archetype (`semantic_crystallization_plan.md`
  §"Evidence standard"). No premature semantic classes.
- **Converge, don't accrete.** When a slice supersedes an old path, DELETE the old path —
  no deprecation shims, aliases, or dead replay loops (see the project's no-compat rule).
  Progress is often deletion.
- **Layer rules hold every commit.** `scripts/audit_recovered_layers.py` + `audit_architecture.py`
  + `lint.py` must stay green; `domain/` and `systems/` never import `cpu`/`mem`/views/adapters.

---

## 4. The per-slice recipe (the unit of work)

Each slice promotes one decision up the ladder
(`ASM → hook → lifted → view → domain record → pure system`) and proves it. Answer the
`semantic_crystallization_plan.md` refactoring checklist, then:

```
1. PICK the boundary: one routine / decision with a stable address and evidence.
2. EVIDENCE: trace it (scripts/dump_world.py, trace_world_writes.py,
   summarize_world_writes.py; the demo replay; the hook verifier). Confirm the inputs,
   outputs, side effects, and which flags/registers are live at the boundary.
3. PURE DECISION: extract the gameplay decision into recovered/systems (or domain record),
   address-anchored name + docstring stating the ASM root + the constants. No cpu/mem.
4. THIN the adapter/hook: read state -> call the pure system -> replay only the original
   CMP/ADD/SUB/flag choreography the verifier needs -> assert agreement. Remove any
   duplicated decision logic (the dedup rule). The hook keeps only the exact continuation.
5. TEST: add a VM-free unit test for the pure function (pattern: tests/test_sprite_layer.py,
   tests/test_playfield.py).
6. VERIFY against demos (§5).
7. METRICS + DOCS (§7), then commit + push.
```

For **render/native-path** slices the same shape applies, with the witness probes
(`overkill/probes/verify_*`) as the byte-exact gate and the §1.2 state-mirror as the
growing native gate.

---

## 5. Verification gates (tested against the demos — all must be green)

```
suite        python -m pytest -q                         (1057 passed / 23 skipped, 2026-07-03)
demo-replay  tests/test_demo_replay_equivalence.py       (bounded)  -> the hybrid byte-exact gate
full demos   OVERKILL_FULL_DEMO_VERIFY=1 ... (the affected demos)    -> deep byte-exact
layers       scripts/audit_recovered_layers.py + audit_architecture.py + lint.py
render       overkill/probes/verify_playfield_compose.py, verify_sprite_layer.py (byte-exact)
metrics      scripts/source_port_status.py               -> pure % must not fall; glue must not rise
```

Two verification flavors:

- **Hybrid collapse (object/gameplay slices):** `--backend vm` with the recovered system in
  the path must stay **byte-exact** vs pure VM on demo-replay. This is the existing, strong
  gate. Use the *full* demo verify for the demos that exercise the touched routine.
- **Native path (standalone/verify slices):** run the demo on `--backend native` with the VM
  oracle in verify mode; the native semantic state (§1.2) must mirror the VM at every
  checkpoint, zero divergence. This gate **grows** as more state is recovered — each native
  slice extends what the mirror covers (a new mirrored field/system), and that coverage must
  never regress.

A slice that cannot be made green on its gate is a **blocker**, not a shortcut: revert,
document, move on.

---

## 6. The work queue — native attempts that pull recovery (prioritized; skip blocked)

These are **features to attempt on `--backend native`**, not a top-down checklist. Each
attempt is the §2 probe: try it, and where it needs missing state/behavior, drop into the
§2 recovery loop to recover that leaf bottom-up, verify, and lift it — then the attempt
completes. Ordered for an unattended run: safest/most-verifiable first (each demo-replay-
gated), building pure mass, before the harder render/standalone integration.

### Bucket A — gameplay/object collapse (the bulk; hybrid byte-exact gate)
The object system is already mature (~30 pure predicates in `systems/objects.py`; surface
behaviors delegate). Continue, decision-by-decision, on the big lifted files (push-down
candidates by size: `object_movement` 1391, `game_state` 1255, `action_spawns` 1247,
`object_behaviors` 1231, `object_runtime` 1095 — `frame_orchestration` is a frame *map*, do
NOT put logic in it).

**Recovered 2026-07-03:** `B73E` (logic_id `0x20`, the waypoint-follower) — was the dominant
remaining object-behavior wall; its `B800` formation-spawn + `B82D` loop are now native and the
`3153` xfail is gone.

**Already recovered (do NOT re-attempt — verify current state before picking any object slice):**
`aed8`/`8d4f` (`object_update_aed8`/`object_update_8d4f` in `systems/objects.py`, wired into the
native dispatch in `systems/object_update.py`), the shared steer/selector helpers `5E42`
(`object_delta_steer_5e42`, `systems/movement.py`) and `B250` (`overlap_contact_box_contains`,
`systems/collision.py`), and `B2CD` (`object_update_b2cd`). The whole object-vs-object collision
island is native too (see Bucket C). These are done; a fresh slice must re-check the code + probes
before assuming anything here is open.

Concrete next slices (each: trace → pure → thin adapter → demo-replay verify → commit):
- Walk each big lifted file, extracting each remaining inline decision into `systems/` and thinning
  its adapter, until the file is decision-free (only continuation glue remains). Confirm a decision
  is not already lifted (grep `systems/`) before recovering it.
- Each promotion that proves a memory layout extends `ObjectSlotView`/`ObjectSlotRecord`
  (only when a verified routine constrains a field — never by guessing).

**Frontier note — disasm groundwork (2026-06-29).** The easy *single-leaf* slices are
exhausted: every remaining candidate is a multi-part **island**, not a clean leaf
(confirmed by disassembling each with `scripts/lindis.py`). The ASM boundaries are mapped
here so a fresh agent recovers the island directly (per §2 step 8: recover the leaves →
verify the composed subsystem → close the boundary):
- `AB99` = a `bp`/`bx`-shuffle wrapper around `BFC7` (already lifted as
  `_run_collision_death_tail_bfc7`). Closing the island = lift the 5-instr wrapper to call
  the lifted `BFC7`. Marginal value; do it only when closing the deactivate island.
- `837A` = a table-dispatcher with an indirect `call ax` over a per-object handler table
  (`ds:[bx+si+2]`, 0..0Ah loop). Needs its whole handler set mapped — a hard island.
- `859E` = the status-cell quad composite: loops 4 cells (`9682/968C/9696/96A0`) via `85D5`,
  gated by `[95BC]`/`[BDAC]`, into the big render routine `511F` — a multi-level render island.
- **HUD score digits (`5F05`→`519A`→`3153` Tandy glyph blit) — DONE (2026-06-29).** The glyph
  blit is native (`native_video/hud_glyph.py`, probe `verify_hud_glyph.py`), and the whole packed-
  B800 HUD text line incl. score digits is `native_video/hud_text.py` (probe
  `verify_native_hud_text.py`). Do NOT re-recover; the only remaining HUD work is folding `hud_text`
  into the standalone backend compose (Bucket C). The `1010:3153` hook is now a thin `--backend vm`
  adapter.
So the next real work is **island recovery**, not single-leaf collapse — best taken by a
fresh agent with clean context, using the boundaries mapped above.

### Bucket B — render self-compose layers (witness byte-exact gate)
Playfield composition is crystallised (`native_video/playfield.compose_playfield_indices`) and now
byte-exact across the WHOLE gameplay demo corpus: both the masked compositor leaves (2E6E/2F81/2FB6)
and the **OR-inverted leaves 2F40/2ECB** (`dest |= ~src`, recovered 2026-07-03 as
`decode_or_inverted_delta` + an `or_inverted` block kind) are modeled, so `verify_playfield_compose`
is 100% on L1–L4 (L3 went 24/29 → 39/39). Remaining:
- **Starfield background layer — RECOVERY DONE + PLATE WIRED (2026-07-03); only the backend-compose
  hookup is open.** The parallax pixel starfield is fully recovered + verified: pure
  `recovered/systems/starfield.py` + `recovered/domain/starfield.py` (move at `1F8F:0922/0960`,
  plot/erase via `4D15`/`4D64`; **NB: the old docs' `4C76` move address is wrong / absent**), probe
  `verify_native_starfield.py`, tests `test_starfield*.py`. **The PLATE is now built VM-free too:**
  `native_video/starfield_plate.py` `render_starfield_plate(state, cursor)` turns `StarfieldState` into
  the `(H,W)` index plate, proven byte-exact vs the VM plate across L1–L4 by
  `verify_native_starfield_plate.py`, and its `compose_playfield_indices(native_plate, sprites)` matches
  the VM playfield (modulo the pre-existing L3 sprite-compose divergence — a `verify_playfield_compose`
  item, not starfield). Do NOT re-recover or re-verify the plate. The only remaining starfield work is
  the last hop: make the standalone `--backend native` frame call `render_starfield_plate` (Bucket C)
  instead of `render_present_page_indices` of the VM page.
- **HUD layer — glyph/text recovery DONE; only the WIRING is open.** The glyph blit + the whole
  packed-B800 HUD text line (incl. score digits) are native (`native_video/hud_glyph.py`,
  `native_video/hud_text.py`; probes `verify_hud_glyph.py`, `verify_native_hud_text.py`). Remaining =
  overlay `hud_text` on the playfield in the standalone backend compose (Bucket C). Gate: byte-exact
  vs B800's HUD band.

### Bucket C — the standalone `NativeGameState` runtime + verify mode (native gate)
The native **frame controller** now exists: `overkill/recovered/systems/frame_loop.py` is the
VM-free counterpart of `9B2E`, sequencing recovered systems over `NativeGameState`. Verified
stages so far: input decode, the movement bits (`native_player_frame_step`), the object pass
(`native_object_pass`, whole-pool), and **world-scroll** (`A66F` gate + `A6FE` forward tick,
`recovered/systems/scroll.py`; wired into `NativeGame.step()` in real 9B2E→A66F→A067→AA0D order
and carried self-sustaining in `verify_native_forward_frames`, 2026-07-03). Grow it stage by
stage and build the loop around it:
- **Finish the gameplay frame** before the loop can run a real level. Most stages are ALREADY
  recovered — the honest remaining gaps are small. Recovered (do NOT re-recover; compose into the
  runtime): spawn machinery (`native_a067` + `object_pool_find_free` 7524/7573 allocator, wired in
  `native_action_fanout_step`; probes `verify_native_a067*`, `verify_native_allocator`) — only the
  FULL-fanout `A970`-family held-action counters remain (declined in `frame_loop.py`); collision-
  death (`object_postmove_bc4b`, `object_collision_death_transition_c037`, the whole object-vs-object
  island in `systems/collision.py`; confirmed native in `loop_blockers.md`); the `9C01`/`A33A`
  coordinate-ring stages (lifted in `game_state.py`). **Genuinely still open:** scripted-input
  (`99F6` — not native; `verify_native_forward_frames` bails on `DS:A47C != 0` ticks) and the
  `A212` view-anchor pre-update (VM-owned per `frame_loop.py`). Verify each against the code before
  attempting — the list of what's left is short.
- Define/grow `NativeGameState` (the source-level state the recovered systems already use as
  their structures) and a standalone loop that runs frame → recovered systems → render/audio
  state → `--backend native`, with NO VM.
- Wire `compose_playfield_indices` (and the starfield/HUD layers) so the backend composes from
  recovered state instead of capturing the VM page — only after the layer it needs exists
  (avoid throwaway plate-capture hooks).
- Implement `--mode verify`: native runtime + VM oracle side by side, comparing the §1.2
  semantic mirrors at checkpoints. This is the native correctness gate; every Bucket-C slice
  extends its coverage.
- Drive toward `--mode standalone` replaying every demo with the VM never started (§1).

### Bucket D — audio (de-risked: the synths already exist)
OVERKILL audio is **OPL/AdLib FM music + PC-speaker SFX** — not PRE2's DMA-PCM streaming, and
the *synthesis* pieces are already present, so this is bounded driver recovery, not research:
- **The synths exist.** `dos_re/dos.py` already captures AdLib register writes
  (`set_adlib_callback`/`_notify_adlib`, ports `0x388`/`0x389`) and routes them to **Nuked-OPL3**
  in the interactive frontend; it also models the PC-speaker path (port `0x61` + PIT `0x42`/`0x43`).
- **What's left = recover the drivers that feed them**, VM-free: the optional AdLib music driver
  (loaded at `2032:0000`, sequenced by the `06E5` timer ISR at ~72.8 Hz) → register-write stream
  → Nuked-OPL3; and the PC-speaker SFX driver (the `06E5`/`2032` path, `DS:BEFE` = sound-active)
  → PIT square wave. Recover each as a pure system that emits the same writes/tones per tick,
  verified produced-vs-VM (capture the VM's `0x388`/`0x389` and speaker-port writes, compare).
Lower priority than A–C/E/F for *playability*, but no longer an unknown.

### Bucket E — the front-end flow (cold-boot §1.5: intro → title → menu → map)
The non-gameplay flow the game shows before/around levels. Like the PRE2 "front-end flow"
recovery, the scenes largely *render over state* already — the work is the native **flow
driver** that sequences them with their input/wait/transition behaviour, VM-free:
- The intro/title/loader scenes, the main menu (the `558B` idle/poll loop), the difficulty/
  planet selectors (`D390`/`D434`/`D445`), and the map. Recover each scene's render + its
  per-scene wait (timer-paced via the `0679`/`06E5` tick) + input + transition as native.
- Build a native scene-flow controller (the front-end counterpart of `frame_loop.py`) that
  runs boot → intro → title → menu → map → level-start → (gameplay) → tally → next, over
  native scene state. Gate: produced-vs-VM at each scene boundary; then a native session that
  reaches the menu, then a level, with no VM.

### Bucket F — native level + asset load (cold-boot §1.6)
So the native game can load its own data instead of inheriting a VM-loaded image:
- **Asset codecs** — promote the already-lifted decoders to pure systems: the `0324` word-pair
  RLE and the `0615` packed-stream reader (and the `02A8` loader dispatcher). Gate: byte-exact
  vs the VM decode on the real asset blobs.
- **Level loader** — recover the routine that turns the decoded level data into game state, as
  a pure system building `NativeGameState`/`LevelState` (tile map, object table seed, palette,
  scroll bounds). Gate: the built state is byte-exact vs the VM's post-load memory.
- Milestone: with Bucket C's frame + this, a **VM-less single LEVEL** loads and plays.

### Bucket G — the native boot backbone + the SEPARATE VM-less standalone (cold-boot §1.5/§1.8)
**Target architecture — mirror `D:\Games\DOS\pre2_port` (the mature sibling; study it directly).**
The VM-less game must be a **separate, self-contained package** that imports ONLY the pure recovered
layer and its own native runtime — never `dos_re`/`cpu`/`mem`/hooks — and ships to `dist/` with the
game data files, running with no emulator at all. Concretely, the pre2 pattern to reproduce:

- **`overkill/native/` package** — the VM-less runtime, separate from the RE workbench. Its modules
  (per pre2's `pre2/native/`): `state.py` (`NativeGameState`), `vga.py` (its OWN screen/present, not
  `dos_re`'s), `boot_data.py` (the game's initialized data segment as **pure constants** — built ONCE
  by a workbench probe using the VM, e.g. `overkill/probes/extract_boot_data.py`; the VM's only
  remaining, BUILD-TIME role, never a runtime dep — so no EXE/boot image at runtime), `cold_boot.py`
  (`native_cold_boot(game_root, level)` → loads the game's own data + boot constants, no VM),
  `front_end.py` (the intro→title→menu→map scene-flow generator, Bucket E), `runtime.py`
  (`native_frame_step`, the gameplay frame, Bucket C), `render.py` (drives `native_video`),
  `audio.py` (Bucket D), `input.py`. It consumes `overkill/recovered/systems` (the pure core).
- **`scripts/play_native.py`** — THE standalone entrypoint (rename `scripts/native_play.py` to this).
  DEFAULT behaviour: **cold-boot the whole game VM-less** from `--game-root` (the game data) + the boot
  constants — intro → menu → level → play — reporting a "not-yet-recovered gap" and holding the last
  frame when it hits one (pre2's `play_native.py` is the exact template). `--snapshot`/`--from-level`
  are DEBUG-only paths. NB: today's `native_play.py` is NOT this — it is a snapshot viewer + the
  `--backend native` *presenter* whose game still runs on a VM child; `--backend native` is HYBRID,
  not the standalone. The standalone is this Bucket-G endgame, built once A–F provide the pieces.
- **`scripts/deploy_native.py`** — the build→`dist/` script (pre2's is the template): compute the
  import closure of `play_native.py`, **deny-list every VM/workbench module** (`dos_re`, `overkill.hooks`,
  `overkill.runtime`, `cpu`/`mem`, the `bridge`/`probes`/`gameplay` VM-facing code), copy the closure +
  a launcher into `dist/overkillnative/`, and **SMOKE-TEST it in a scrubbed subprocess** (sys.path =
  the dist folder only) — cold-boot, run ticks, render a frame, and assert NO VM module was imported.
  That smoke test is the machine-checked proof the shipped game is truly VM-free.
- The timer/tick model (`064A` installs the `06E5` IRQ0 at ~72.8 Hz) becomes a native clock driving
  both the frame loop and the audio drivers.
- **Gate:** `deploy_native.py` builds + smoke-tests green (VM-free), and a recorded native session
  cold-boots and plays through to the ending (§1.8), with `--backend vm` kept only as the oracle.

**Where overkill is vs this target (2026-07-03, updated):** a first real `scripts/play_native.py`
now exists and RUNS: it cold-loads a level (`overkill.native_game.NativeGame`, byte-exact from the
game's own files, no VM), ticks the recovered frame stages (input decode, view-anchor movement,
world-scroll, the object-update pass) with real keyboard input, and presents via pygame — with
**zero `dos_re` imports anywhere on that path** (verified: `sys.modules` has no `dos_re.*` entries
after a full run). `scripts/play.py`'s `--backend native`/`--mp-publish` VM-child machinery (the
thing that made the OLD `native_play.py` a hybrid presenter, not a standalone) has been removed
from `play.py` entirely; `play.py` is now purely the VM/oracle tool. Getting there required fixing
a real separability leak: `overkill/asset_codecs/*` (imported transitively by the level loader)
had six modules importing `dos_re.cpu`'s `CF`/`DF` flag constants and one importing `overkill.asm`
(which itself pulls in `dos_re.cpu`/`dos_re.memory`) — fixed by giving `asset_codecs` its own tiny,
independent `_flags.py` + a local `loop_count`, so it never touches `dos_re` at all now.

**Still open (this is a real render/state placeholder, not the endgame):** the STANDALONE render is
currently a debug marker (black background + a dot at the tracked player position) — the byte-exact
starfield/HUD/sprite visuals are proven correct in isolation (`native_video/*`) but not yet wired
into `play_native.py` (the fresh-level starfield INIT state and the object-pool→sprite-pixel bridge
are the open integration gaps). A handful of per-frame gameplay globals (Bucket C's still-open
`99F6`/full-`A067`/coordinate-ring items) are supplied as the same documented 0/False "normal tick"
defaults the recovered systems' own dataclasses already use, not derived from anywhere — `ref_box_x/y`
(the view-anchor box) IS derived for real. There is also no real level-INIT state yet (Bucket F): the
default spawn is a placeholder, not the verified cold-start position (`--snapshot` seeds a REAL
verified starting state from a captured VM memory dump for this reason — a static file read, still
zero `dos_re` on the default path). No front-end (Bucket E) yet — `--level N` is the only mode, like
pre2's own `--from-level` debug path before its front-end existed. `scripts/deploy_native.py`
(the build→`dist/` + VM-free smoke test) is not built yet — the next concrete slice.

---

## 7. Progress tracking & reporting (each iteration)

- Log, in the commit message and in `run_status.md`: the slice, the gate that proved it, and
  the metric delta (pure %, glue count, demos covered).
- Keep `loop_blockers.md` current: every reverted slice with its repro.
- Update the durable docs the methodology names (`recovered_source_layer.md`,
  `island_truth_tables.md`, `runtime_findings.md`, `symbols.json`) when a slice earns it.
- The single headline metric to watch trend up overnight: **pure % of game-logic mass**
  (`scripts/source_port_status.py`), with **glue hook count** trending down. Neither may
  regress on any commit.

---

## 8. Queue refill (when Bucket A's surface is exhausted)

If no listed slice is actionable, regenerate the frontier instead of stopping:
- Run a representative gameplay demo with fail-fast coverage; the routines that still appear
  as `unknown`/`glue` in coverage are the next candidates.
- Re-run `scripts/source_port_status.py`; target the largest remaining `lifted` file's next
  inline decision.
- Only after Buckets A–G are genuinely exhausted and **all of §1 (1–8) holds** is the run
  complete — i.e. the full game cold-boots and plays through with no VM.

---

## TL;DR for the loop

> **Try a piece natively → see what's missing → go down to the ASM and recover that leaf
> (shadow → verified hook → source system) → verify it against the demos/oracle → lift it
> into native state → close the island.** Never fake a gap in the renderer/runtime; recover
> it first. One verified island-step = one commit + push; never commit red, never weaken the
> oracle, always revert+document a failed attempt. Stop (print `COLD-BOOT ENDGAME REACHED`)
> only when the **full game cold-boots and plays through with no VM** — demos standalone +
> verify-mode zero divergence (§1.1–1.4) **and** boot → front-end → level load → gameplay →
> audio → ending all native (§1.5–1.8). At that point the recovered code **is** the game, and
> `--backend vm` is just the harness that proves it.
