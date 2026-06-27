# GOAL: grow the standalone native game, one verified dual-mode slice at a time

> Run this with `/goal`. It is the **executable per-iteration playbook** for the
> recovery, designed to run **unattended for long stretches (overnight)** — self-sufficient,
> never-halt, green-at-all-times (see *Unattended / overnight operating mode* below). The
> destination is [`native_game_endgame.md`](native_game_endgame.md)
> (a standalone native game; the VM becomes an optional oracle). The method is
> [`rescue_refactor.md`](rescue_refactor.md) (push lifted → pure recovered). This
> file is *what to do each iteration*.

## The goal

Each iteration, move one piece of OVERKILL from VM-coupled `lifted` code into a
**pure, dual-mode recovered system** that (a) runs in the hybrid runtime today via a
thin adapter, verified byte-exact against the ASM oracle, and (b) is written so it
will run **unchanged in the standalone native game** tomorrow. Progress = hooks get
thinner, `recovered/systems` grows, the native game gets more complete.

**Done overall when:** the gameplay subsystems run from native state structures, the
hooks are thin adapters (or gone), and `--mode standalone` can run the game without the
VM (with `--mode verify` still able to diff against the oracle).

## The dual-mode rule (how every slice is shaped)

Write the recovered system against **source-level state the native side owns**
(`ObjectSlotRecord` + named globals + small result records), **never** `cpu` /
segment:offset / continuation IPs. Then:

```
hybrid:      adapter reads VM memory -> native struct -> recovered system -> adapter writes back + replays the ASM flag/register boundary
standalone:  NativeGameState -> the SAME recovered system -> NativeGameState   (no VM)
```

Template = the AB10 slice (commit 787593f): `recovered/systems/objects.object_logic_ab10`
returns an `Ab10Update`; the thin adapter `gameplay/object_behaviors._run_object_logic_ab10`
does the DOS reads + the boundary fidelity. Prefer rules that take/return
`ObjectSlotRecord` (or an explicit update record) so they drop straight into the future
`ObjectSystem`.

## One iteration (do exactly one slice)

1. **Pick ONE target** from the backlog (top first); keep it finishable + verifiable
   this iteration. Compute the live `object_behaviors` worklist (which bodies already
   delegate to a recovered rule = DONE, which are still inline = TODO) with:
   ```
   python3 -c "import re;f='overkill/gameplay/object_behaviors.py';t=open(f,encoding='utf-8').read();m=re.search(r'from overkill.recovered.systems.objects import \((.*?)\)',t,re.S);syms=[x.strip().rstrip(',') for x in (m.group(1).split() if m else []) if x.strip().rstrip(',')];s=t.splitlines();d=[(i,l) for i,l in enumerate(s) if re.match(r'^def (run_|_run_|_scan_)',l)];[print(('DONE' if [y for y in syms if not y.isupper() and re.search(r'\\b'+y+r'\\b','\\n'.join(s[i:(d[k+1][0] if k+1<len(d) else len(s))]))] else 'TODO'),l.split('(')[0].split()[1]) for k,(i,l) in enumerate(d)]"
   ```
   Today: 3 DONE (`b73e`/`b86d`/`ab10`), 14 TODO. Take the smallest TODO not attended-only.
2. **Diagnose against the oracle, never guess.** Disassemble the original ASM for the
   routine (capstone; image at `artifacts/static_runtime_bundle/memory_1mb.bin`,
   `1010:off` → linear `0x10100+off`) and read the existing lifted body. Identify the
   pure logic (decisions + formulas) vs the boundary fidelity (flags/registers the
   caller relies on).
3. **Recover it dual-mode.** Add the pure rule to `recovered/systems/` (+ a domain
   record in `recovered/domain/` if multi-field), named constants for magic numbers.
   Rewrite the lifted function as a thin adapter: read native state via views → call the
   rule → apply results → replay only the **live** boundary flags/registers → return.
   Remove the now-dead inline logic in the same change.
4. **Verify — all green, never commit red:**
   ```
   PYTHONPATH=. python scripts/lint.py
   PYTHONPATH=. python scripts/audit_architecture.py            # pure layer must not import VM
   PYTHONPATH=. python -m pytest tests/test_recovered_semantics.py -k "<new rule>" -q
   PYTHONPATH=. python -m pytest tests/test_demo_replay_equivalence.py -q   # the real gate (~3 min)
   # collision hooks only: PYTHONPATH=. python -m pytest tests/test_overkill_hooks.py -k "<CS:IP>" -q
   ```
   Behaviour hooks have **no per-hook oracle**, so demo-replay is the proof — and only if
   the path is exercised. If a change could be on a rarely-hit path, confirm it runs:
   patch the function with an invocation counter and run one gameplay demo; commit only
   if count>0 and demo-replay stays green. A byte-exact extraction (same writes + same
   boundary) is low-risk; a dead-flag/register drop must be proven exercised.
5. **Record + ship.** Add a dated entry to `docs/overkill/run_status.md`; regenerate the
   island manifest if you added `@recovered_island` (`scripts/gen_island_manifest.py`).
   Commit (trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`), push to
   `origin/main`. One coherent slice per iteration.

## Unattended / overnight operating mode (self-sufficient — never halt)

This goal is meant to run for **hours unattended** (e.g. overnight). The user is away;
stay productive across the whole window and never stop on the first hard problem.

- **Keep the tree green at all times.** Commit only **code / docs / tests** — ignore
  `artifacts/` (regenerated coverage cache + recorded demos; never part of a slice, don't
  add or revert them). A slice's `git status` should touch only the files it lifts. If a
  slice can't be finished byte-exact (a gate reds and you can't fix it cleanly), **revert
  its changes** (`git restore <files>`) so the next iteration starts clean. Never commit or
  leave a red/partial slice.
- **Skip, don't stop.** If a target is blocked (a divergence you can't resolve byte-exact,
  it would need guessing, or it needs gameplay context), append it to
  `docs/overkill/loop_blockers.md` (what you tried, the exact divergence, why it's blocked /
  what you'd need), then move to the NEXT backlog item. **Read `loop_blockers.md` first each
  iteration and never re-attempt a logged blocker.**
- **Commit + push every green slice** so progress is saved incrementally and the user can
  review in the morning.
- **Pick the next target autonomously.** Top unblocked backlog item; within a subsystem,
  the **smallest / most self-contained** routine not yet recovered and not in
  `loop_blockers.md`; when a subsystem is exhausted, move to the next backlog item. There is
  deliberately plenty of work (see the breadth note) so the queue does not run dry overnight.
- **SKIP the attended-only targets.** `loop_blockers.md` has a *"Remaining backlog — needs
  attended judgment (not safe unattended)"* section — do NOT touch those in an unattended
  run: the **death / deactivation frontier** (`BD17`/`BFC7`/`9E69`/`C054` tails + the
  player-death `BC4B` divergence) and the formation spawns `8d4f`/`7476` (analyzed-dead but
  unexercised in the demo window → unverifiable unattended). They need a human trace; leave
  them for an attended session.
- **Verify against the FULL demo corpus.** `tests/test_demo_replay_equivalence.py` runs the
  whole `artifacts/demos/*` set (~20 demos) — use it as the gate, not a single demo, so
  divergences anywhere are caught. For a possibly-cold path (a dead-flag/register drop),
  prove it is exercised: patch with an invocation counter, run a gameplay demo, commit only
  if count>0. Pure byte-exact extractions (same writes + same boundary) are safe without this.
- **Favor tractable wins** (clean dual-mode rule lifts, named-constant pushes, collision
  assert drops) so the night accumulates many verified slices. If a behaviour proves deep
  after ~2 diagnosis attempts, log it in `loop_blockers.md` and move on — do not grind.
- **Only fully stop** if: the repo is broken and you cannot restore it to green; OR every
  remaining backlog item is already in `loop_blockers.md`; OR a step needs a destructive /
  irreversible / outward-facing action that requires the user. Otherwise keep going. When you
  do stop, leave a one-paragraph summary at the top of `loop_blockers.md`.

## Backlog — the full roadmap to the endgame (deep enough for a very long run)

Order = leverage × tractability: recover the gameplay systems first (they ARE the native
game), reconstruct native state as systems mature, recover the render/audio systems as
game systems, then assemble the standalone runtime. Within a phase, do the smallest
self-contained routine not in `loop_blockers.md` first. Hygiene slices are valid filler
whenever a substantive target is blocked. This queue is intentionally large — it will not
run dry over many nights.

### Phase 1 — gameplay systems: lifted → pure dual-mode recovered (the bulk)
Push each VM-coupled body in `overkill/gameplay/*.py` down into a pure `recovered/systems`
rule (dual-mode, native-state-shaped per the AB10 template), thin the hook to an adapter,
verify byte-exact vs the demo corpus. One subsystem at a time.
- **`object_behaviors` → ObjectSystem** *(active)*: the ~14 `_run_object_*` bodies —
  self-contained `aed8`/`ae09`/`aba3`/`ab77`/`ab10`✓/`aa2b` first, then the orchestrators
  `b73e`/`b9f0`/`b24d`/`b86d`/`ad04`/`8d4f`/`efae` (lift their call trees as you go).
- **`collision` → CollisionSystem**: drop the ~49 self-check asserts where the rule is
  already live (oracle-gated; flag traps `4FF9`/`AC28`, AF survives the RET); lift any
  remaining inline predicates.
- **`object_movement` / `object_postmove` / `object_runtime` / `object_runtime_common`**
  → MovementSystem (clamp/scroll family already live): push the remaining bodies down.
- **`object_spawns` / `action_spawns`** → SpawnSystem.
- **`object_deactivation`** → the deactivate family. `C054` is done; the `BD17`/`BFC7`/
  `9E69` death tails + the player-death `BC4B` divergence are **ATTENDED-ONLY** (in
  `loop_blockers.md`) — **skip them unattended**; they need a human trace.
- **`contact_overlap` / `contact_side_effects`** → ContactSystem.
- **`object_bounds`** → bounds; **`view_window`** → camera.
- **`game_state`** → GameStateSystem (frame fragments; keep `9b2e`/`d007` as frame MAPS,
  never grow them).

### Phase 1b (parallel, very tractable) — thin `hooks.py` (must be registration glue)
`hooks.py` is ~4100 lines; **~47 of its 225 functions have >20-line INLINE LOGIC bodies**
that belong in recovered modules, not the hook layer. Move each body out, leaving a thin
`@registry.replace … def overkill_X(cpu): run_X(cpu, …)` wrapper. They are mostly:
- **render compositors / blits** (`447b`/`3e12`/`3efb`/`38b7`/`3849`/`41a6`/`497a`/`cc7f`)
  — the CGA/EGA/scaled siblings of the already-lifted Tandy `2E6E` family → move to
  `rendering/ega.py` or a new `cga`/`blit` module, mirroring `rendering/tandy.py`. These
  have **per-hook oracles**, so each verifies fast: `pytest tests/test_overkill_hooks.py -k <addr>`.
- **presence / scan / clear glue** (`4d15`/`4d6f`/`a8c7`/`a927`/`5c74`/`5a92` scans) → the
  layer-sprite / object-scan recovered modules (`rendering/layer_sprites.py`).
- **menu input waits** (`cf78`/`ce40`) → `frame_orchestration` / `input_menu`.
Each move is byte-exact (the body is unchanged, just relocated to its system module + a
thin wrapper) — a direct coastline win that drops `hooks.py`'s line count. Enumerate the
fattest hooks with:
`python3 -c "import re;s=open('overkill/hooks.py',encoding='utf-8').read().splitlines();d=[i for i,l in enumerate(s) if re.match(r'^def ',l)];[print(((d[k+1] if k+1<len(d) else len(s))-i), s[i].split('(')[0][4:]) for k,i in enumerate(d)]" | sort -rn | head -30`.
NOTE: the other large files are not anomalies — `gameplay/*` (object_movement/game_state/
action_spawns/object_runtime) are the Phase-1 lift queue; `rendering/tandy.py`/`ega.py` are
the backend where render logic belongs (keep isolated); `coverage.py` is tooling.

### Phase 2 — native state structs (enables semantic verify + standalone)
As each system matures, make its rules take/return native state instead of loose ints:
`ObjectSlotRecord`✓ → `ObjectPool`, then `PlayerState`, `ProjectileState`, `CombatState`,
`CameraState`, `LevelState`, `ScoreState`, `RngState`. Add a semantic state-mirror verifier
per struct (diff the native struct vs the VM view at a checkpoint).

### Phase 3 — render systems as recovered game state (NOT renderer hacks)
Recover the original render path into systems the native backend consumes (see
`native_video_plan.md` + `native_background_interpolation_plan.md`): sprite textures✓,
extraction✓, sprite layer✓; then the **level-scroll renderer** (the bg: tilemap `[9592]`
+ tile cells + scroll), **starfield**, **HUD/chrome**, **palette/fades**, **transitions** —
each verified vs the live page. Then **object interpolation** over the recovered bg + the
menu toggle.

### Phase 4 — audio
Recover the audio command/mixer path (`play_sfx` + the song/MOD path) into a clean native
audio system the backend can drive; verify against the SoundBlaster-emulated output.

### Phase 5 — standalone assembly (later; the wiring is attended)
`NativeGameState` + an `update_frame()` that calls the recovered systems; wire
`--mode standalone` (no VM) and `--mode verify` / `record-oracle` / `replay-test` around the
same recovered code; prove a gameplay demo runs standalone and matches the oracle traces.

### Hygiene tail (valid filler anytime a substantive target is blocked)
Magic numbers → named constants; raw `mem.rw/ww(ds, …)` globals → named `ds_globals`/views;
address-named `run_*_<addr>` → role names (address kept in the docstring). Each a tiny,
safe, byte-exact slice. Enumerate live targets per iteration with e.g.
`grep -nE "^def _run_object" overkill/gameplay/object_behaviors.py`,
`grep -c "assert " overkill/gameplay/collision.py`, minus anything in `loop_blockers.md`.

## Measuring progress (run occasionally, not every slice)

`python scripts/source_port_status.py` — the headline metrics: **% pure-source mass UP**
and **glue-hook count DOWN** (not hook coverage up). `python scripts/gen_hook_inventory.py`
and `python scripts/gen_island_manifest.py` regenerate the coastline + island docs (commit
the regenerated files). The endgame is reached when the gameplay systems run from native
state, the hooks are thin or gone, and `--mode standalone` runs the game without the VM.

## Guardrails

- **The ASM boundary is the spec.** Byte-exact observable state (registers/flags/live
  memory) at the routine boundary; only proven-dead state is free. A cleanup that reds a
  gate changed behaviour — revert it.
- **Recovery-first, no faking.** If the backend (or anything) needs state that isn't
  recovered, recover it at the source layer first; never fake it in the renderer.
- **Recovered pieces are the game, not hook fillers.** Write them dual-mode so they
  outlive the hook. Hooks are scaffolding; deleting/thinning one is progress.
- **No speculative island lifting** beyond the current slice; each piece is real RE with
  no correctness gain until verified.
- **Don't grow `hooks.py` or the broad controllers.** The headline metric is glue-hook
  count DOWN + pure-source mass UP, not hook coverage up.

## Definition of done (per slice)

Pure rule added (dual-mode shaped) + named constants/record · lifted function thinned to
an adapter, dead inline logic removed · pure unit test green · demo-replay green (and the
path proven exercised if the change is dead-flag/register) · lint + audit green ·
`run_status.md` updated · committed + pushed · **the coastline is shorter or more
native than before.**
