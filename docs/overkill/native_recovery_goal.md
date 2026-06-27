# GOAL: grow the standalone native game, one verified dual-mode slice at a time

> Run this with `/goal`. It is the **executable per-iteration playbook** for the
> recovery. The destination is [`native_game_endgame.md`](native_game_endgame.md)
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
   this iteration.
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

## Backlog (work top-down)

1. **`object_behaviors` → `ObjectSystem` (active).** Push each `_run_object_*` body's
   logic into a pure rule. Order: the self-contained ones first
   (`aed8`/`ae09`/`aba3`/`ab77`/`ab10`✓ + the `aa2b` dispatch), then the bigger
   orchestrators (`b73e`/`b9f0`/`b24d`/`b86d`/`ad04`) — those call other lifted routines,
   so lift the call tree as you go. Each rule dual-mode (takes/returns native object
   state).
2. **Native object-state struct.** Make the object rules take/return `ObjectSlotRecord`
   (exists in `recovered/domain/object_slots`) instead of loose ints, and have adapters
   read/write it — the dual-mode enabler that makes these systems standalone-usable and
   raises verification toward an `ObjectPool` contract.
3. **collision coastline.** Drop the ~49 per-function self-check asserts where the pure
   rule is already live (the ASM replay is dead weight); oracle-gated, watch the cross-fn
   flag traps (`4FF9`/`AC28`, AF survives the RET).
4. **`game_state` → `GameStateSystem`.** Push frame-state fragments to pure rules; keep
   broad controllers (`9b2e`/`d007`) as frame MAPS, never grow them.
5. **Reconstruct state dataclasses** (`PlayerState`/`LevelState`/`CameraState`/
   `RngState`) so verification rises to semantic state mirrors and the standalone runtime
   has real state to own.
6. **(later, attended) standalone skeleton + modes.** A `NativeGameState` + an
   `update_frame()` that calls the recovered systems; wire `--mode standalone` (no VM) and
   `--mode verify`/`record-oracle`/`replay-test` around the same recovered code.

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
