# Loop blockers — divergences/targets that need the user (or better tooling)

Open items the autonomous loop attempted but could not finish byte-exact. Do NOT
re-attempt these in the loop; they need a reproduction trace and/or gameplay
context. Each has the analysis already done so a human can pick up fast.

> Status note (2026-06-19): the byte-exact frontier is effectively closed —
> oracle suite 244/244 and demo-replay 19/19 (bounded) are green, and the
> readability refactor (`refactor_plan.md`) has taken over as the primary driver
> (Phases 1–2 done, Phase 3 in progress). The only genuinely-open correctness
> blocker is the player-death full-demo divergence below.

---

## OPEN — Player-death `BC4B`/`BFC7` divergence (full-demo only)
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

- **View-contact-center divergence `[95F2]`/`[95F4]`** (surfaced 2026-06-28 by the
  full-arc menu-crossing demos now that the level-select replays faithfully): in the
  full (not bounded) demo-replay verify, the decoded globals
  `view_contact_center_x_95f2` / `_y_95f4` diverge between the ASM oracle and the
  hooked runtime mid-gameplay — `demo_play_tandy_20260627_231013` ~frame 934 (3
  frames), `..._start_to_end` ~frame 2635. Same risk class as the player-death
  `BC4B` frontier above: a collision/contact hook computing the contact point
  differently than the original. Needs a single-step trace of the first divergent
  frame to find the writer; not safe to guess unattended.
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
