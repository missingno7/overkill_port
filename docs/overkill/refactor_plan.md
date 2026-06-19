# OVERKILL source-reconstruction refactor — goal & playbook

## North star
Turn the live VM/hook runtime into a **complete reconstruction of the original
source code that is readable, yet still live and byte-verifiable**. All three at
once, none traded away:

- **Readable** — every live-path routine reads like source someone would write:
  named by role, structured control flow, typed access, documented intent. You
  could learn the game's design from the code.
- **Live** — it *is* the game's execution path, not a side document. The code
  runs.
- **Verifiable** — it stays provably identical to the original 8086 behaviour,
  checked every change against the ASM oracle and recorded demos.

This is the successor goal to `loop_plan.md` (which drove the byte-exact frontier:
raw-offset drains, field naming, divergence fixes). Those gains stand; this plan
spends them on readability.

---

## The key that makes it possible: the boundary contract
A routine is **correct** iff, at its continuation boundary, it leaves the exact
*observable* state the original leaves:

- registers, flags, IP — exact;
- all memory **at or above SP**, and all memory outside the stack — exact.

What is **free** (not part of behaviour, so not compared):

- **dead stack scratch** in `SS:[SP-0x40 .. SP)` — the popped CALL return words
  a real CALL/RET leaves below SP, which the calling convention defines as
  undefined (an interrupt may clobber them). Enforced by
  `assert_oracle_equivalent` (tests) and `_range_diff`'s dead-stack ignore
  (`dos_re/verification.py`), kept in sync via `_DEAD_STACK_BYTES`.
- **provably-dead intermediate values** — flags or memory a routine computes but
  overwrites before the boundary. These need no new relaxation: the oracle
  already compares only the *boundary* state, so removing a computation whose
  result never reaches the boundary leaves the comparison unchanged. The oracle
  is self-checking here — if removing it reds the oracle, it was live; revert.

**Readability comes from *how* we produce the boundary state, not from changing
it.** The original's boundary behaviour is law. If a cleaner version would set a
different register/flag/live byte, the cleaner version is wrong — you have
misread the original.

---

## What "readable source-like" means per routine (the target)
- Functions named by **role**, not address (`run_player_hazard_scan`, not
  `run_bdd0`); keep the `CS:IP` in the docstring/alias for traceability.
- **Typed views** over raw offsets: `slot.y_word` not `mem.rw(ds, bx+4)`.
- **Named globals**: every magic `DS:` / `CS:` address resolved to an
  evidenced-role constant.
- **Real control flow and named locals** instead of register juggling and
  goto-style `s.ip = …` — the final register state still matches, but the body
  reads as logic, not transliteration.
- **No transliteration scaffolding** (`_cmp_word`, `set_add_flags`,
  `_add_mem_word`, manual flag sets) where the boundary flags don't depend on it.
- **No dead-state fidelity code** (the `sp-2` scratch writes, balanced-push
  helpers).
- **Docstrings that explain the design**, not just the address it came from.

---

## Gates — must stay green after every slice (the safety net)
1. `tests/test_overkill_hooks.py` — the per-hook ASM oracles (currently 244/244).
2. `tests/test_demo_replay_equivalence.py` — framebuffer + RGB + semantic state,
   the real correctness guarantee (currently 18/18).
3. `scripts/lint.py` — clean.
4. `scripts/play.py --verify-hooks --verify-hook <CS:IP>` — spot-check any hook
   whose body changed (full-memory, strict).
5. `scripts/trace.py {watch,observe,globals}` — the standing tool for diagnosing
   any divergence a slice introduces.

**A cleanup that reds a gate changed observable behaviour, therefore it is wrong
— revert it.** The gates are not obstacles; they are what lets us refactor
aggressively without fear.

---

## Phases — ordered by leverage × safety

**Phase 0 — relaxed-oracle infrastructure (DONE).**
`assert_oracle_equivalent` + harness dead-stack ignore, piloted on the BC4B
clamp. The contract above is now enforceable.

**Phase 1 — retire dead-state scratch (lowest risk, do first). DONE.**
Deleted `_remember_balanced_push_scratch` and its call sites; swept the inline
`mem.ww(ss, sp-2, …)` scratch writes; switched affected oracles to
`assert_oracle_equivalent`. Kept the live `saved_cx` CX-restore in the asset
codecs (it reaches the boundary — not dead). Commits `643e602`, `528cdb8`,
`933e756`.

**Phase 2 — structured access everywhere (pure readability, byte-exact). DONE.**
*2a typed-views:* every raw SS:BP / DS:BX object-record access in gameplay now
goes through `ObjectSlotView` (current-object `slot`, spawned/target `dst`,
scanned-candidate `cand`); fixed-bx handlers use one view, scan loops a
per-iteration view. The view is write-complete (setters for every stamped
field). Only deliberate semantic aliases remain raw (e.g. `OFF_SUBSTATE_1E` in
contact_overlap, documenting that DS:[bp+1E] is read as a substate there).
*2b DS-global reconciliation:* `recovered/ds_globals.py` is the single
definition site for the cells genuinely shared across subsystems (the 7 that had
2–3 divergent adapter names — VIEW_TARGET_X/Y, VIDEO_MODE_SELECTOR_OFF,
COLLISION_DEBUG_FLAG/CODE, BOSS_GROUP_LATCH, CONTACT_DISPATCH_GATE); subsystem
modules keep their local names as thin `LOCAL = CANONICAL` aliases. **Design
call:** single-subsystem globals stay local to their module (locality aids
readability), and same-valued-but-distinct subsystem literals (the `0x00xx`
thresholds/flags/logic-ids) are *not* merged — they are different roles that
share a number. Commits for 2a across object_movement/contact_side_effects/
object_runtime/object_spawns + earlier batches; 2b is the ds_globals commit.

**Phase 3 — de-transliterate hook bodies.**
Per hook: replace register-juggling and goto-IP with named locals and real
control flow that produces the same boundary state; drop `_cmp_word` /
`set_*_flags` whose result is dead at the boundary (gated by the exact
boundary-flag oracle — self-checking); extract repeated idioms into named
helpers. This is where most of the "reads like source" win lives.

**Phase 4 — name & organise.**
Rename `run_*_<addr>` to role names (address preserved in docstring); regroup
modules by subsystem (movement / collision / rendering / menu / …); docstrings
describe behaviour and design, not provenance.

**Phase 5 — lift the interpreted islands (highest effort, last).**
Convert the remaining raw-ASM gameplay regions (the 97C8 frame body, menu core,
block loops, BBB2/BE3C/B2CD/ADC9 …) into source-like Python under the boundary
contract, one region per slice, each fully gated. These are real reverse-
engineering, not mechanical — do them only after the cheap phases are exhausted.

**Phase 6 — completeness pass.**
Audit for any remaining magic numbers, address-named functions, or interpreted
islands. Update the dashboard / living memory map to report **source-complete**.

---

## Per-slice loop (for autonomous or attended runs)
1. Take the **smallest coherent unit** from the current phase.
2. Make the change **and remove the now-unnecessary cruft in the same change**
   (no nicer code layered on old glue).
3. Run the gates for what you touched (oracles + lint always; demo-replay before
   committing a batch; `--verify-hooks` on changed bodies).
4. **Green** → commit with a clear message (what got cleaner, and that behaviour
   is unchanged). **Red** → diagnose with `scripts/trace.py`; if the change moved
   any live state, revert — it was wrong.
5. Log the slice in `run_status.md`; update the dashboard / `loop_blockers.md`.
6. One coherent slice per turn.

---

## Guardrails
- **The boundary contract is the spec.** Never alter observable behaviour to make
  code prettier. The original's register/flag/live-memory state is law.
- **Only dead state is free.** Below-SP scratch and provably-dead intermediates,
  nothing else. If you want to relax a *live* register/flag to pass a test, stop
  — that is a real divergence, not noise.
- **Remove-in-the-same-change.** Every step that makes a path unnecessary deletes
  it then and there.
- **Keep the two relaxation definitions in sync** (`assert_oracle_equivalent` and
  `_range_diff`, via `_DEAD_STACK_BYTES`). Any future extension of "dead state"
  (e.g. dead intermediate flags as a formal category) ships as infrastructure
  first, piloted on one site, before any sweep.
- **No speculative island lifting** (Phase 5) before Phases 1–4 are done; each
  island is genuine risk with no correctness gain until lifted carefully.
- **Readability never costs verifiability.** If a routine can't be made readable
  without breaking a gate, leave it readable-but-honest and mark *why* in a
  comment (what boundary fact forces the shape), so a later pass can revisit.

---

## Definition of done
- No live-path routine is transliterated ASM; every one reads like source.
- No magic offsets, raw addresses, or un-named globals in the live path.
- Interpreted-ASM islands eliminated, or reduced to a documented, justified
  residue with a recorded reason.
- `demo-replay` + hook oracle suite + `--verify-hooks` all green.
- The dashboard / living memory map reports the reconstruction **source-complete**
  — readable, live, and verifiable, all three.
