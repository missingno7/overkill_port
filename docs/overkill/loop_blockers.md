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
