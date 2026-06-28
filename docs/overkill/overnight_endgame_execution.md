# Overnight endgame execution — make `--backend native` the complete recovered port

> **This is an executable, unattended brief.** It is meant to be run by an autonomous
> agent for many hours overnight, one verified slice at a time, tested against the
> demos, committing as it goes, until the done-condition in §1 is met.
>
> The **destination** (the *why*) is [`native_game_endgame.md`](native_game_endgame.md).
> The **method** (the *how*, per slice) is
> [`semantic_crystallization_plan.md`](semantic_crystallization_plan.md) and
> [`source_port_methodology.md`](source_port_methodology.md). The **map** of what is
> still ASM vs pure is [`coastline_report.md`](coastline_report.md)
> (regenerate live with `python scripts/source_port_status.py`).
>
> This document is the loop that drives all of them. Do not duplicate their content;
> follow them.

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

**The one design rule that makes both possible (the dual-mode systems rule):** a recovered
system is written against **source-level state structures the native side owns**, never
against `cpu`/segment:offset. The hybrid path reads VM memory into those structures and
writes results back; the standalone path passes the structures directly. *Same logic,
proven in hybrid, reused unchanged standalone.* The hook wrappers are temporary; the
recovered systems are permanent.

---

## 1. Definition of DONE (the stop condition)

Stop when **all** hold (re-derive from metrics + demos each pass; do not guess):

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
   essentially all in `source_pure`/`game_core` (pure %  → its ceiling; today 14.3%), the
   `glue` hook count near zero, and `hooks.py` back under its size budget. Remaining hooks
   are thin adapters used only by `--backend vm`.

Until then, keep iterating §2.

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
suite        python -m pytest -q                         (550+ passed / 23 skipped today)
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

Concrete next slices (each: trace → pure → thin adapter → demo-replay verify → commit):
- The un-collapsed behaviors with no pure counterpart: `aed8`, `8d4f`.
- The shared helpers behind several behaviors: `5E42` steer, `B250` overlap/contact selector.
- Then walk each big lifted file, extracting each inline decision into `systems/` and thinning
  its adapter, until the file is decision-free (only continuation glue remains).
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
- **HUD score digits** = `5F05` (pop digit → ASCII `+30h` → `jmp 519A`) → `519A` (mode
  dispatch `jmp cs:[95BC*2 + 0x51B2]`; for Tandy `[95BC]=2` → **`1010:3153`**) → **`3153`
  is an 8×8 Tandy glyph blit — THE recoverable leaf, in the rasterizer's wheelhouse:**
  per char, `si = char*8 + DS:1816` (the 8-byte/char font); for each of 8 rows `lodsb` →
  `DS:1514[byte*4]` (the bit→4bpp pixel-expand table, 2 words) `& DS:215C` (the colour
  mask) → write to `CS:[95A4]` (the visible page) at cursor `DS:215E + DS:2160`, advancing
  `di` by the Tandy bank geometry (`+0x2000`, wrap `+0x80A0`) = the rasterizer's
  `tandy_b800_next_row`. (`al`=0x10/0x11 are cursor-control escapes → `333D`/`3322`.) The
  BCD `score_bcd` (DS:2314) is **already recovered**. **Clean fresh-session slice:** lift
  `3153` to a native glyph blit over the rasterizer geometry + extract the `1816`/`1514`
  tables, witnessed byte-exact vs B800's digit band — then the HUD digits compose natively.
So the next real work is **island recovery**, not single-leaf collapse — best taken by a
fresh agent with clean context, using the boundaries mapped above.

### Bucket B — render self-compose layers (witness byte-exact gate)
Playfield composition is crystallised (`native_video/playfield.compose_playfield_indices`,
proven 30/30). Remaining:
- **Starfield background layer.** It is a **parallax PIXEL layer** (confirmed: the
  static-buffer-scroll model fails 0/60; stars scroll at their own rate). Recover it as a
  pixel star set + independent parallax scroll. The per-frame plot writes the off-screen
  scroll-in region — locate it with a parallax-aware / off-screen-window trace (it dodged
  the watcher-based probes; the `rep movs/stos` watcher blind-spot is now fixed, so re-run
  attribution with watchers active). Gate: `compose_playfield_indices(starfield, sprites)`
  byte-exact vs the VM playfield across demos.
- **HUD layer.** Score digits already pinned to `5F05`; the right-panel chrome is static.
  Recover it as a native HUD layer overlaid on the playfield. Gate: byte-exact vs B800's
  HUD band.

### Bucket C — the standalone `NativeGameState` runtime + verify mode (native gate)
Once enough systems are pure, build the VM-free runtime and its oracle harness:
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

### Bucket D — audio (later)
Recover the audio command/state into source systems consumed by the native backend
(`play_sfx`/song state), so standalone has sound without the VM mixer. Lower priority than
A–C; do after the gameplay+render state mirrors are solid.

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
- Only after Buckets A–D are genuinely exhausted and §1 holds is the run complete.

---

## TL;DR for the loop

> **Try a piece natively → see what's missing → go down to the ASM and recover that leaf
> (shadow → verified hook → source system) → verify it against the demos/oracle → lift it
> into native state → close the island.** Never fake a gap in the renderer/runtime; recover
> it first. One verified island-step = one commit + push; never commit red, never weaken the
> oracle, always revert+document a failed attempt. Stop when `--backend native` runs every
> demo standalone and verify-mode shows zero divergence from the VM oracle. At that point the
> recovered code **is** the game, and `--backend vm` is just the harness that proves it.
