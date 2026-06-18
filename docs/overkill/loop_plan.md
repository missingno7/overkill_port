# Source-port advancement loop

Autonomous playbook: **one small, verified, byte-exact slice per iteration.**
The VM is the oracle; every slice must stay provably equivalent to the original.
Read this file at the start of each iteration and do exactly one slice.

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
   push to the **`reconstruction-loop` review branch** (`git push origin
   reconstruction-loop`). **Never push autonomous loop commits straight to
   `reconstruction`** — the user reviews `reconstruction-loop` and merges it.

## Backlog (work top-down)

1. **Open divergences (highest value)** — native must equal the VM oracle:
   - Mothership **camera-Y** (`DS:2380` +1, drags object Ys): bisect with
     `demo_play_tandy_mothership_drag_edge_case` or `..._L6_mothership_end`.
   - **Player-death `BC4B`/`BFC7`** divergence: `demo_play_tandy_player_death`.
   - Any **new `*_edge_case` / divergence demo** added under `artifacts/demos/` —
     run it with `--verify-hooks` and fix what it surfaces.
2. **Complete the death/deactivation frontier.** `BFC7` (death tail), `BD17`
   (deactivate), `C054` (logic dispatch) are still "partial/observed" lifts —
   disassemble their *full* branch tables instead of only the observed paths. Most
   edge-case divergences cluster here; finishing it clears several at once.
3. **Name remaining object-record unknowns** `0x10`, `0x26`, `0x36` — but only if a
   lifted reader pins the meaning. Otherwise leave them `unknown` (the map's
   credibility depends on this).
4. **Drain remaining raw offsets** (`scripts/source_port_status.py` tracks the %):
   `objects.py`, `contact_side_effects.py`, `action_spawns.py`. Attribute each
   access *per register* to the right struct first (object slot vs caller frame vs
   table) — a wrong-but-byte-identical name is worse than a raw offset.
5. **Lift interpreted gameplay hotspots** into pure `recovered/systems` rules:
   `97C8` (main frame body frontier), then `ADC9`, `BBB2`, `BE3C`, `B2CD` waypoint.

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
- **Commit + push every green slice to `reconstruction-loop`** (the review branch,
  NOT `reconstruction`) so progress is saved incrementally; the user reviews and
  merges in the morning. Stay on `reconstruction-loop` the whole run.
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
