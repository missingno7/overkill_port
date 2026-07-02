# Source-port advancement playbook

> **Role (so there's no confusion):** this file is the **per-divergence FIX procedure** (the
> disassemble-and-compare loop in step 2) + the unattended-mode operating rules. It is **not**
> the goal brief. The canonical `/goal` brief (what to build next + the cold-boot done-condition)
> is [`overnight_endgame_execution.md`](overnight_endgame_execution.md); the vision is
> [`game_recovery_lifecycle.md`](game_recovery_lifecycle.md).
>
> **Status (2026-06-19):** the byte-exact *frontier* this playbook drove is now
> effectively closed — divergences fixed, raw-offset drain and field naming
> largely done (see the backlog markers below). Keep using THIS file as the **procedure for
> fixing any new divergence** a demo surfaces (step 2's disassemble-and-compare loop is
> still exactly right), and as the unattended-mode operating rules.
>
> **STALE BACKLOG WARNING (2026-07-03):** the specific backlog items below are a 2026-06-19
> snapshot and several are now DONE — e.g. `B2CD` (`object_update_b2cd`), the `BFC7`→`C037`
> collision-death transition, and the whole object-vs-object collision island are recovered as
> pure systems. Do NOT treat the backlog as a live to-do list; the authoritative queue is
> `overnight_endgame_execution.md` §6. `BD17`'s global death/counter side-effects may remain
> partial — verify against `recovered/systems/` + `loop_blockers.md` before acting on any item here.

**Goal:** drive OVERKILL toward clean, complete, *source-like* code that stays
byte-exact with the original — gradually, one verified slice at a time. Progress
is measured by `scripts/source_port_status.py` (% pure source up, raw offsets and
divergences down) and by demo-replay staying native==VM.

Works with `/loop` or any goal-directed autonomous mode: **one small, verified,
byte-exact slice per iteration.** The VM is the oracle; every slice must stay
provably equivalent to the original. Read this file at the start of each
iteration and do exactly one slice.

**Default operating mode:** an autonomous run is *unattended* — follow **Unattended mode**
(below) without being told: **commit + push each green slice to `main`** (this repo works on
`main`), verify every slice, and skip-and-log blockers in `docs/overkill/loop_blockers.md`.
Never halt, never commit red. (The autonomous *driver* is the `/goal` brief
[`overnight_endgame_execution.md`](overnight_endgame_execution.md); this file is the
per-divergence fix procedure it uses when a demo surfaces a mismatch.)

## The loop (do this once per iteration)

1. **Pick ONE target** from the backlog below (top priority first). One slice =
   one hook fixed, OR one field named, OR one file's raw offsets drained. Keep it
   small enough to finish and verify in this iteration.

2. **Diagnose against the oracle.** Never guess.
   - For a divergence: reproduce headlessly
     (`SDL_VIDEODRIVER=dummy PYTHONPATH=. python scripts/play.py --demo artifacts/demos/<demo> --verify-hooks`),
     read which hook + registers/memory diverge, then **disassemble the original
     ASM** for that address and compare it line-by-line to the lifted Python. The
     bug is almost always a branch/guard the lift dropped that the per-hook oracle
     never exercised (see the 9FAF `CMP BX,FFFF / JNZ / RET` fix as the template).
   - For a field: confirm a real lifted reader/writer and a clear access pattern
     before naming it.

3. **Implement byte-exact.** Match the original's flags, registers, and memory.
   Keep flag-affecting ASM helpers (`_cmp_word`, `_add_mem_word`, `set_sub_flags`,
   scan-loop register walks) visible in the lifted body; a view/named-constant
   only replaces the *memory access*, never the flag/branch logic.

4. **Verify — ALL must pass (never leave red):**
   ```
   PYTHONPATH=. python scripts/lint.py
   PYTHONPATH=. python scripts/audit_recovered_layers.py
   PYTHONPATH=. python -m pytest tests/test_recovered_semantics.py tests/test_checkpoint_handoff.py -q
   PYTHONPATH=. python -m pytest tests/test_demo_replay_equivalence.py -q          # the proof spine
   PYTHONPATH=. python -m pytest tests/test_overkill_hooks.py -k "<relevant hook>" -q
   ```
   - **lint does NOT catch undefined names.** After any import/raw-drain edit, also
     do a fresh `python -c "import <module>"` or an AST used-but-not-imported check
     (a stale-cache NameError on a rare code path is the failure mode to avoid).
   - For a divergence fix, add a focused regression test for the exact edge case
     the original oracle missed (e.g. the `[A966]==FFFF` 9FAF test).
   - For a field naming, update `OBJECT_RECORD_FIELDS` + the map tests in
     `tests/test_recovered_semantics.py`.

5. **Leave the live path cleaner** (hygiene): fewer raw offsets, no dead code, no
   parallel representations, honest `unknown`s (never fabricate a name). If
   something ugly must stay, add a comment with *why* and the condition to remove
   it later.

6. **Record + ship.** Prepend a dated entry to `docs/overkill/run_status.md`. Run
   `PYTHONPATH=. python scripts/source_port_status.py` and note the numbers moving.
   If everything is green, `git add` the code/docs/tests (NOT `artifacts/repros` or
   `frame_verify` — they are gitignored), commit with a descriptive message ending
   in the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer, and
   **push to `main`** (this repo works on `main`; one verified slice = one commit + push).

## Backlog (work top-down)

1. **Open divergences (highest value)** — native must equal the VM oracle:
   - ~~Mothership **camera-Y** (`DS:2380` +1)~~ — **RESOLVED 2026-06-19**
     (`9B2E` `[a47c]==0` guard; see `loop_blockers.md`).
   - **Player-death `BC4B`/`BFC7`** divergence: `demo_play_tandy_player_death` —
     still OPEN, full-demo only (bounded 150f passes). See `loop_blockers.md`.
   - Any **new `*_edge_case` / divergence demo** added under `artifacts/demos/` —
     run it with `--verify-hooks` and fix what it surfaces.
2. **Complete the death/deactivation frontier.** `BFC7` (death tail), `BD17`
   (deactivate), `C054` (logic dispatch) are still "partial/observed" lifts —
   disassemble their *full* branch tables instead of only the observed paths. Most
   edge-case divergences cluster here; finishing it likely clears the player-death
   blocker too.
3. **Name remaining object-record unknowns** `0x10`, `0x26`, `0x36` — but only if a
   lifted reader pins the meaning. Otherwise leave them `unknown` (the map's
   credibility depends on this). Map stands at 25/28 — the honest floor.
4. ~~**Drain remaining raw offsets**~~ — **DONE 2026-06-19** (refactor Phase 2a):
   `objects.py`, `contact_side_effects.py`, `action_spawns.py` and the rest of
   gameplay now access records through `ObjectSlotView`; the dashboard shows
   50 named vs 3 raw (the deliberate `OFF_SUBSTATE_1E` alias).
5. **Lift interpreted gameplay hotspots** into pure `recovered/systems` rules:
   `97C8` (main frame body frontier), then `ADC9`, `BBB2`, `BE3C`, `B2CD` waypoint.
   (This is refactor_plan Phase 5 — do it *after* Phases 3–4, attended.)

## Hard guardrails

- The **VM is the oracle**; every change is byte-exact vs the interpreted ASM.
- **Verify every slice**; never commit with a failing check or a regressed demo.
- **Don't guess.** No fabricated field names, no speculative abstractions, no view
  added without a live consumer ("introduced by use").
- **Don't build a parallel runtime / detached GameState.** Source-like code mutates
  the real VM memory through views; there is one source of truth.
- **When blocked** (a verify step fails and you can't make it green byte-exactly, a
  fix would require guessing, or a divergence needs gameplay context): if running
  *attended*, stop and report. If running *unattended*, follow **Unattended mode**
  below — revert, log, move on. Never commit a red or partial slice either way.

## Unattended (overnight) mode

When the user is away and wants the loop to run for hours, stay productive across
the whole window instead of halting on the first hard problem:

- **Keep the tree green at all times.** Start each iteration from a clean
  `git status`. If a slice can't be finished byte-exact, **revert all its changes**
  (`git restore <files>` / `git checkout -- <files>`) so the next iteration starts
  clean. Never commit or leave a red/partial slice.
- **Skip, don't stop.** If a target is blocked, append it to
  `docs/overkill/loop_blockers.md` (what you tried, the exact divergence, why it's
  blocked / what you'd need), then move to the NEXT backlog item.
- **Never re-attempt a logged blocker.** Read `loop_blockers.md` first each
  iteration and pick a target not already listed there.
- **Commit + push every green slice to `main`** so progress is saved incrementally
  (one verified slice = one commit + push).
- **Favor tractable wins** (9FAF-style missing-guard divergence fixes, field
  naming, raw-offset drain) so the night accumulates many verified improvements;
  if a divergence proves deep after ~2 trace attempts, log it and move on.
- **Only fully stop** if the repo is broken and you cannot restore it to green, or
  every remaining backlog item is already in `loop_blockers.md`. Leave a final
  summary at the top of `loop_blockers.md`.

## One-iteration definition of done

Lint + audit + recovered-semantics + checkpoint-handoff + demo-replay all green,
the touched hook's oracle green, a regression/map test added, `run_status.md`
updated, dashboard numbers recorded, and (if green) committed + pushed.
